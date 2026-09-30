"""Command line entry point: gitmole <path | owner/repo | url> [--out DIR] [--no-run], gitmole --clean [DIR], gitmole --doctor, or gitmole --install-tools."""
from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import os
import shutil
import signal
import sys
import tempfile
import threading
import time

from rich.console import Console, Group
from rich.live import Live
from rich.spinner import Spinner
from rich.text import Text

from . import __version__, banner, blame, filetypes, findings, load, loss, run, scope, tools

INSTALL_URL = "https://github.com/antvinni/gitmole/blob/main/docs/install.md"
# what to do about a missing or moved required tool, said by a run and by --doctor alike
INSTALL_HINT = "gitmole --install-tools downloads the pinned set; brew install gitmole brings it with it; without either, see"


DOCS_URL = "https://github.com/antvinni/gitmole/blob/main/docs"

EPILOG = f"""\
examples:
  gitmole .                            the clone you are in
  gitmole owner/repo                   clone into a temp dir, then report
  gitmole . --full                     every section, row and column
  gitmole . --markdown report.md       the report as a Markdown document
  gitmole . --fail-on warning          exit 3 on a warning or worse
  gitmole . --risk main --risk-threshold 10
                                       exit 3 if the change since main is risky
  gitmole analysis-repo --no-run --json -
                                       re-render an earlier run as JSON
  gitmole --install-tools              download the three pinned tools
  gitmole --doctor                     check the tools against their pins

every option in detail:
  {DOCS_URL}/cli.md
reading your first report:
  {DOCS_URL}/first-report.md
"""


USAGE = """gitmole [options] [target]
       gitmole --doctor | --install-tools | --clean [DIR]"""


def build_parser() -> argparse.ArgumentParser:
    """The command line, in groups, one line per option; the prose for each lives in docs/cli.md."""
    p = argparse.ArgumentParser(prog="gitmole", usage=USAGE, description="Analyse a git repository offline and print a report.",
                                epilog=EPILOG, formatter_class=argparse.RawDescriptionHelpFormatter, add_help=False)
    p.add_argument("target", nargs="?", help="a clone, owner/repo, 'owner/*' or a git URL; with --no-run, an output "
                                             "directory; with --clean, where to look (default .)")

    run_ = p.add_argument_group("run")
    run_.add_argument("--out", metavar="DIR", help="output directory (default analysis-<repo>)")
    run_.add_argument("--no-run", action="store_true", help="re-render the report from an output directory")
    run_.add_argument("--workers", type=int, default=6, metavar="N", help="how many tools run at once (default 6)")
    run_.add_argument("--timeout", type=float, default=900, metavar="SECONDS", help="kill a tool after this long (default 900)")
    run_.add_argument("--time-budget", type=float, default=60, metavar="SECONDS",
                      help="skip code age projected past this (default 60)")
    run_.add_argument("--budget", type=int, default=50000, metavar="N", help="skip --plots over N blames (default 50000)")
    run_.add_argument("--deep", action="store_true", help="run code age and plots past budget")
    run_.add_argument("--plots", action="store_true", help="also draw the code-age and survival plots")
    run_.add_argument("--duplicates", action="store_true", help=argparse.SUPPRESS)   # the duplicates step is gone (0.39.0); kept so older scripts still parse

    scope = p.add_argument_group("scope")
    scope.add_argument("--since", metavar="WHEN", help="only history newer than 2y, 18m, 90d or a date")
    scope.add_argument("--path", action="append", default=[], metavar="DIR",
                       help="describe only the files under DIR (repeatable)")
    scope.add_argument("--gone", type=int, default=loss.DEFAULT_MONTHS, metavar="MONTHS",
                       help="months without a commit that count as gone (12)")
    scope.add_argument("--file-types", metavar="LIST", help="extensions that count as code, comma-separated, or all")
    scope.add_argument("--ignore-data", action="store_true", help="leave csv, json, lock, minified and vendored out")
    scope.add_argument("--ignore", action="append", default=[], metavar="GLOB", help="another pattern to leave out (repeatable)")

    report = p.add_argument_group("report and exports")
    report.add_argument("--full", action="store_true", help="print the report with every section, row and column")
    report.add_argument("--json", metavar="PATH", help="write report and findings as JSON (- for stdout)")
    report.add_argument("--markdown", metavar="PATH", help="write the report as Markdown (- for stdout)")
    report.add_argument("--sarif", metavar="PATH", help="write the findings as SARIF 2.1.0 (- for stdout)")
    report.add_argument("--sarif-scope", choices=["head", "history"], default="head", metavar="SCOPE",
                        help="with --sarif: head (default) or history")
    report.add_argument("--sbom", metavar="PATH", help="write a CycloneDX 1.6 SBOM of the locked packages")
    report.add_argument("--compare", metavar="BEFORE.json", help="add what changed since an earlier --json export")
    report.add_argument("--feedback", action="store_true", help="ask five questions about the findings; sends nothing")

    gates = p.add_argument_group("gates")
    gates.add_argument("--fail-on", choices=findings.SEVERITIES, metavar="LEVEL",
                       help="exit 3 at LEVEL or worse; 4 if a step failed")
    gates.add_argument("--baseline", metavar="BEFORE.json", help="gate only on findings not in that earlier export")
    gates.add_argument("--require-vuln-db", action="store_true",
                       help="exit 4 if no vulnerability database was found")
    gates.add_argument("--risk", metavar="BASE", help="score the files changed since BASE (a local clone)")
    gates.add_argument("--risk-threshold", type=float, metavar="N", help="with --risk or --hook: fail over N percent")
    gates.add_argument("--hook", action="store_true", help="with --no-run: score the files an agent hook names")

    other = p.add_argument_group("tools and housekeeping")
    other.add_argument("--doctor", action="store_true", help="check the tools against their pinned versions")
    other.add_argument("--install-tools", action="store_true", help="download the three pinned tools, then exit")
    other.add_argument("--list-file-types", action="store_true", help="list the file types and which count as code")
    other.add_argument("--clean", action="store_true", help="list what gitmole left behind; delete on a yes")
    other.add_argument("--yes", action="store_true", help="with --clean: delete without asking")
    other.add_argument("--version", action="version", version=f"gitmole {__version__}",
                       help="print gitmole's version and exit")
    other.add_argument("-h", "--help", action="help", help="show this help and exit")
    return p


def parse_args(argv):
    p = build_parser()
    # --hook takes the files to score after --, pre-commit's way. Split them off here: Python 3.9's argparse
    # cannot give a second positional a value once optionals sit between it and the first.
    argv = list(argv)
    files = argv[argv.index("--") + 1:] if "--" in argv else []
    args = p.parse_args(argv[:argv.index("--")] if "--" in argv else argv)
    args.files = files
    return args


_control = run.Control()


def interrupt(*_):
    """Ctrl-C: kill every running step's process group; the run loop then exits 130."""
    _control.cancel()


@contextlib.contextmanager
def _interruptible():
    """Ctrl-C ends a question or a download the way it ends any Python program: the run's own SIGINT handler
    only cancels step processes, and there are none while the tools are being fetched. Off the main thread
    (tests) signals cannot be set, and KeyboardInterrupt reaches the caller anyway."""
    if threading.current_thread() is not threading.main_thread():
        yield
        return
    previous = signal.signal(signal.SIGINT, signal.default_int_handler)
    try:
        yield
    finally:
        signal.signal(signal.SIGINT, previous)


def main(argv=None, console: Console = None, tool_check=run.missing_tools, planner=run.plan, estimator=run.estimate_blames,
         lister=run.list_repos, cloner=run.clone, lizard_check=run.has_lizard, ask=None, stdin=None,
         structure_check=run.has_structure, version_note=tools.note, installer=None, isatty=None) -> int:
    global _control
    _control = run.Control()
    if threading.current_thread() is threading.main_thread():
        signal.signal(signal.SIGINT, interrupt)
    args = parse_args(sys.argv[1:] if argv is None else argv)
    console = console or Console()
    err = Console(stderr=True) if console.file is sys.stdout else console
    rc = _check_args(args, err)
    if rc is not None:
        return rc
    if args.doctor:
        from . import doctor
        return doctor.main(console)
    if args.install_tools:
        return _install_tools(console, installer)
    if args.clean:
        return _clean(args, console, ask)
    # When an export goes to stdout, everything else (banner, progress, report) moves to stderr.
    quiet = "-" in (args.json, args.markdown, args.sarif, args.sbom)
    ui = Console(stderr=True) if quiet else console

    rc, now = _resolve_time(args, err, ui)
    if rc is not None:
        return rc

    if args.no_run:
        return _no_run(args, console, ui, err, stdin)

    try:
        kind, target = run.classify_target(args.target)
    except ValueError as e:
        err.print(f"[red]{e}[/red]")
        return 2
    rc = _check_args(args, err, kind)
    if rc is not None:
        return rc

    args.now = now
    if args.since_date:
        ui.print(f"[dim]history bounded: since {args.since_date}[/dim]")

    if args.list_file_types:
        return _list_file_types(target, args, console)

    rc = _tools(args, ui, err, ask, installer, tool_check, isatty)
    if rc is not None:
        return rc
    moved = version_note({name: run.tool_version(name) for name in run.REQUIRED_TOOLS} | {"lizard": run.lizard_version()})
    if moved:   # a tool's own rules decide part of the report, so a toolchain that is not the pinned one is said once
        err.print(f"[yellow]{moved}[/yellow]")
    args.lizard = lizard_check()   # decided once, for every repository this run analyses
    args.structure = structure_check()

    rc, repo_dir, out_dir = _resolve_target(kind, target, args, console, ui, err, planner, estimator, lister, cloner)
    if rc is not None:
        return rc

    try:
        _analyse(repo_dir, out_dir, args, ui, planner, estimator)
    except Interrupted:
        return 130
    except NoCommits as e:
        err.print(f"[red]{e}[/red]")
        return 2
    finally:
        if kind == "remote":
            shutil.rmtree(os.path.dirname(repo_dir), ignore_errors=True)   # the temp clone; nothing reads it after the run
    return _render(out_dir, console, ui, args, err)


def _check_args(args, err, kind=None) -> int | None:
    """The argument combinations that cannot work, in one place: 2 and a message, or None. Called
    once on the arguments alone, then again with the target's `kind` for the checks that need it."""
    if args.doctor or args.install_tools:   # each exits before any analysis: a target is refused and every other option ignored
        if args.doctor and args.install_tools:
            err.print("[red]--doctor and --install-tools are two commands;[/red] run --install-tools, then --doctor")
            return 2
        if args.target is not None:
            err.print(f"[red]{'--doctor' if args.doctor else '--install-tools'} takes no target[/red]")
            return 2
        return None
    if kind is None:
        bad = ("--yes needs --clean" if args.yes and not args.clean else
               "target required" if args.target is None and not args.clean else
               "--hook needs --no-run and an output directory" if args.hook and not args.no_run else
               "--risk-threshold needs --risk" if args.risk_threshold is not None and not args.risk and not args.hook else
               "--compare: no such file: " + args.compare if args.compare and not os.path.isfile(args.compare) else
               "--path needs a run: a re-render cannot narrow an earlier analysis" if args.path and args.no_run else
               "--plots cannot be narrowed by --path: git-of-theseus reads the whole tree" if args.path and args.plots else
               "--baseline: no such file: " + args.baseline if args.baseline and not os.path.isfile(args.baseline) else None)
        if not bad and args.path:
            try:
                args.path = scope.clean(args.path)
            except ValueError as e:
                bad = str(e)
    elif kind == "path":
        bad = None
    else:
        bad = ("--compare needs one repository, not owner/*" if args.compare and kind == "org" else
               "--baseline needs one repository, not owner/*" if args.baseline and kind == "org" else
               "--sbom needs one repository, not owner/*" if args.sbom and kind == "org" else
               "--path needs one repository, not owner/*" if args.path and kind == "org" else
               "--risk needs a local path" if args.risk else
               "--list-file-types needs a local path" if args.list_file_types else None)
    if bad:
        err.print(f"[red]{bad}[/red]")
        return 2
    return None


def _resolve_time(args, err, ui):
    """Resolve GITMOLE_NOW and --since into (None, now) and args.since_date, or (rc, None) on bad input."""
    now = os.environ.get("GITMOLE_NOW") or None
    if now:
        from . import maat
        try:
            maat.validate_now(now)
        except ValueError as e:
            err.print(f"[red]GITMOLE_NOW:[/red] {e}")
            return 2, None
        # A notice about the run, not part of the report: never on a stdout that carries something a program
        # parses (--hook's JSON, an export to -). ui is already stderr for an export; otherwise err is.
        (ui if ui.stderr else err).print(f"[yellow]reference date fixed by GITMOLE_NOW:[/yellow] {now}")
    args.since_date = None
    if args.since:
        import datetime as _dt
        try:
            args.since_date = run.parse_since(args.since, now or _dt.date.today().isoformat())
        except ValueError as e:
            err.print(f"[red]{e}[/red]")
            return 2, None
    return None, now


def _no_run_hint(args, out_dir: str) -> list:
    """What to say when --no-run is pointed at something that is not an output directory. With --no-run
    the target is the directory a run wrote, not the clone, and --out has no part in it - which is easy
    to get the wrong way round, since every other invocation takes the clone. If the directory a run
    would have written is there, name it: the fix is then one line rather than a hunt."""
    lines = ["--no-run re-renders a directory a run wrote, so the target is that directory, not the clone."]
    if args.out:
        lines.append(f"--out is not read with --no-run; pass the directory as the target instead of --out {args.out}.")
    candidates = [os.path.abspath(args.out)] if args.out else []
    candidates += [run.output_dir("path", out_dir, None), os.path.join(out_dir, f"analysis-{run.repo_name(out_dir)}")]
    for cand in dict.fromkeys(candidates):
        if cand != out_dir and os.path.isfile(os.path.join(cand, "meta.json")):
            lines.append(f"Did you mean: gitmole {cand} --no-run")
            break
    return lines


def _no_run(args, console, ui, err, stdin=None) -> int:
    """Handle --no-run: re-render an existing output directory instead of running the pipeline, or,
    with --hook, score the files an agent's hook names against it."""
    if args.since:
        err.print("[red]--since needs a run:[/red] a re-render cannot narrow an earlier analysis")
        return 2
    out_dir = os.path.abspath(args.target)
    if args.hook and not os.path.isfile(os.path.join(out_dir, "meta.json")):
        from . import hook
        err.print(hook.setup_hint(args.target), soft_wrap=True, markup=False, highlight=False)
        return 0   # an agent reads 2 as "block": a hook set up before its first run must not stop every edit
    if not os.path.isfile(os.path.join(out_dir, "meta.json")):
        err.print(f"[red]no gitmole output found in {out_dir}[/red] (expected meta.json)")
        for line in _no_run_hint(args, out_dir):
            err.print(line, highlight=False, soft_wrap=True)   # a command wrapped mid-path cannot be pasted
        return 2
    if args.hook:
        return _hook(out_dir, args, console, err, sys.stdin if stdin is None else stdin)
    if ui.is_terminal:
        ui.print(banner.neon(version=__version__))
    return _render(out_dir, console, ui, args, err)


def _hook(out_dir: str, args, console: Console, err: Console, stdin) -> int:
    """The agent-hook gate (see hook.py): 2 over the threshold, 0 otherwise, silent when the event
    names no file in the repository. An analysis older than HEAD is said on stderr, with the gap."""
    from . import gate, hook, watch
    try:
        report = load.load_report(out_dir)
    except load.Unreadable as e:
        err.print(f"[red]{e}[/red]", soft_wrap=True)
        return 0   # a broken output directory must not block an edit
    repo = report["meta"].get("path") or os.getcwd()
    event = {} if args.files else hook.read_event(stdin)
    files = [os.path.relpath(os.path.abspath(f), os.path.realpath(repo)) if os.path.isabs(f) else f for f in args.files] or hook.paths_in(event, repo)
    if not files:
        return 0
    commit = (report["meta"].get("run") or {}).get("commit")
    gap = hook.behind(repo, commit)
    if gap:   # stderr: never on the stdout the agent parses; the exit code is the scores', not the notice's
        err.print(hook.stale_line(args.target, repo, commit, gap), soft_wrap=True, markup=False, highlight=False)
    risk = watch.change_risk(report, files)
    lines = hook.summary(risk, args.risk_threshold)
    if args.files:
        console.print("\n".join(lines), soft_wrap=True, markup=False, highlight=False)
    else:
        console.print(hook.hook_output(event, lines), soft_wrap=True, markup=False, highlight=False)
    if args.risk_threshold is not None and risk["total"] > args.risk_threshold:
        err.print("\n".join(lines), soft_wrap=True, markup=False, highlight=False)   # exit 2: what the agent is told
        return 2
    missing = gate.unfinished(report, gate.RISK_STEPS) if args.risk_threshold is not None else []
    if missing:   # every file scores 0 without the log or the sizes: under the threshold, and not because it is safe
        err.print(f"gate incomplete: {gate.describe(missing)} in the run {out_dir} holds, so these scores are not the files' "
                  f"and --risk-threshold could not check them (exit {gate.EXIT_INCOMPLETE})", soft_wrap=True, markup=False, highlight=False)
        return gate.EXIT_INCOMPLETE
    return 0


def _clean(args, console: Console, ask) -> int:
    """Handle --clean: list what gitmole left behind, ask once, remove. ask(prompt) returns the answer."""
    from . import clean, feedback, render

    tmp = clean.temp_dir()
    found = clean.find(args.target or ".", tmp)
    if not found:
        console.print("nothing to clean")
        return 0
    total = sum(size for _, size, _ in found)
    columns = [("directory", {"no_wrap": True}), ("size", render.RIGHT), ("modified", {})]
    clones = [r for r in found if os.path.dirname(r[0]) == tmp]
    listed = found
    if clones and not args.full:
        # one row for the temp folder: the clones differ only in their random suffix; --full lists them all
        label = f"{clean.TEMP_PREFIX}* ({len(clones)} temp clone{'s' if len(clones) > 1 else ''})"
        listed = [(os.path.join(tmp, label), sum(s for _, s, _ in clones), max(m for _, _, m in clones))]
        listed += [r for r in found if os.path.dirname(r[0]) != tmp]
    rows = [(path, clean.human(size), time.strftime("%Y-%m-%d", time.localtime(mtime))) for path, size, mtime in listed]
    rows = render._shorten(rows, console.width, columns)   # middle-elided paths, one line per row; the last segment stays whole
    sec = render._section("Left behind", columns, rows, caption=f"{_dirs(len(found))}, {clean.human(total)} in all")
    render.print_section(console, sec)
    console.print(Text(""))
    if not args.yes:
        # an injected ask (tests) stands in for the person; the real one needs real terminals, not FORCE_COLOR's
        if not console.is_terminal or (ask is None and not feedback.on_terminal(console.file)):
            console.print("[red]--clean needs a terminal to confirm;[/red] pass --yes to skip the question")
            return 2
        try:
            with _interruptible():
                agreed = _yes(ask or (lambda q: console.input(q, markup=False)), f"Delete {_dirs(len(found))} ({clean.human(total)})? [y/N] ")
        except KeyboardInterrupt:
            console.print("interrupted")
            return 130
        if not agreed:
            console.print("kept")
            return 0
    failed = clean.remove([p for p, _, _ in found])
    removed = [(p, size) for p, size, _ in found if p not in failed]
    console.print(f"removed {_dirs(len(removed))} ({clean.human(sum(s for _, s in removed))})")
    for p in failed:
        console.print(f"[red]could not remove[/red] {p}", soft_wrap=True)
    return 1 if failed else 0


def _yes(ask, question: str) -> bool:
    """Ask a y/N question; only y or yes agrees, and end of input is a no."""
    try:
        answer = ask(question)
    except EOFError:
        answer = ""
    return (answer or "").strip().lower() in ("y", "yes")


def _install_tools(console: Console, installer) -> int:
    """Handle --install-tools: every required tool, one line per step; 0 when all of them landed, 1 otherwise,
    130 on Ctrl-C during the download (a tool already placed stays, one being written is left under no name).
    Downloads whether or not a copy is already on PATH: the point is a set gitmole owns, at the pins."""
    from . import install
    installer = installer or install.install
    say = lambda line: console.print(line, markup=False, highlight=False, soft_wrap=True)   # urls and paths stay one pasteable line
    try:
        with _interruptible():
            done = installer(run.REQUIRED_TOOLS, say=say)
    except KeyboardInterrupt:
        say("interrupted")
        return 130
    left = [t for t in run.REQUIRED_TOOLS if t not in done]
    if left:
        say(f"not installed: {', '.join(left)}; see {INSTALL_URL}")
        return 1
    say(f"{len(done)} tools installed into {install.tools_dir()}")
    return 0


def _tools(args, ui: Console, err: Console, ask, installer, tool_check, isatty=None) -> int | None:
    """The tool check before a run: None when every tool is there, else 2 and what to do. When a person is
    there to answer, a missing required tool is offered as a download first: here, before any analysis, only
    after a yes. A person means real terminals on stdin and on the stream the question is written to, and no
    sign of a pipeline (feedback.unattended: a CI variable, an export, a gate, the hook), since CI can run on a
    pseudo-terminal. Ctrl-C at the question or during the download exits 130; a tool already placed stays.
    Otherwise nothing is asked or fetched and the command is named, so an unattended run behaves as it always did."""
    from . import feedback, install
    missing = tool_check(plots=args.plots)
    if not missing:
        return None
    err.print("[red]missing tools:[/red] " + ", ".join(missing))
    wanted = install.downloadable([t for t in run.REQUIRED_TOOLS if t in missing])
    nowhere = install.writable(None) if wanted and install.tools_dir() is None else None
    if nowhere:   # a relative GITMOLE_TOOLS or no home: an offer could only fail after the yes
        err.print(nowhere, markup=False, highlight=False)
        wanted = []
    isatty = isatty or (lambda: feedback.on_terminal(ui.file))
    if wanted and not feedback.unattended(args) and isatty():
        ask = ask or (lambda q: ui.input(Text(q)))   # Text: no markup, and no highlighting of the versions
        installer = installer or install.install
        try:
            with _interruptible():
                if _yes(ask, install.offer(wanted)):
                    installer(wanted, say=lambda line: err.print(line, markup=False, highlight=False, soft_wrap=True))
                    missing = tool_check(plots=args.plots)
                    if not missing:
                        return None
                    err.print("[red]still missing:[/red] " + ", ".join(missing))
        except KeyboardInterrupt:
            err.print("interrupted")
            return 130
    if set(missing) & set(run.REQUIRED_TOOLS):
        # gitmole's own directory and the formula's libexec/tools both hold the pinned versions; separate formulae
        # are whatever version Homebrew has that day, and their report lands in run.tools_moved
        err.print(INSTALL_HINT)
        err.print(INSTALL_URL)
    if set(missing) & set(run.PLOT_TOOLS):   # not in the formula and not in the table: git-of-theseus is the opt-in extra
        err.print("--plots needs git-of-theseus: pipx install 'gitmole[plots]'", markup=False)
    return 2


def _dirs(n: int) -> str:
    return f"{n} director{'y' if n == 1 else 'ies'}"


def _resolve_target(kind, target, args, console, ui, err, planner, estimator, lister, cloner):
    """Resolve the classified target to (repo_dir, out_dir) for _analyse, or a final return code for the
    org and clone-failure paths. Returns (rc, repo_dir, out_dir); rc is None unless main should return early."""
    if kind == "org":
        return _portfolio(target, args, console, ui, planner, estimator, lister, cloner), None, None

    if kind == "remote":
        parent = tempfile.mkdtemp(prefix="gitmole-", dir=os.environ.get("TMPDIR"))
        ui.print(f"[dim]cloning {target} into {parent}[/dim]")
        try:
            repo_dir = cloner(target, parent)
        except run.GhError as e:
            shutil.rmtree(parent, ignore_errors=True)
            err.print(f"[red]could not clone {target}:[/red] {e}", soft_wrap=True)
            return 2, None, None
    else:
        repo_dir = target

    out_dir = run.output_dir(kind, repo_dir, args.out, scope=args.path)
    return None, repo_dir, out_dir


class Interrupted(Exception):
    pass


class NoCommits(Exception):
    pass


def _types_spec(spec):
    """Normalise --file-types for the planner: None for the default, 'all', or a sorted comma list."""
    if spec is None:
        return None
    parsed = filetypes.parse(spec)
    return "all" if parsed is None else ",".join(sorted(parsed))


def _list_file_types(repo_dir: str, args, console: Console) -> int:
    from . import render

    try:
        scope.validate(repo_dir, args.path)
    except ValueError as e:
        console.print(f"[red]{e}[/red]", soft_wrap=True)
        return 2
    rows = [(k, n, "yes" if inc else "no") for k, n, inc in filetypes.discover(repo_dir, filetypes.parse(args.file_types), args.path)]
    sec = render._section("File types", [("type", {}), ("files", render.RIGHT), ("code", {})], rows, note="no tracked files",
                          caption="code = analysed for hotspots, coupling and code age")
    render.print_section(console, sec)
    return 0


def _budgets(args, estimate, ui) -> tuple[bool, bool, float]:
    """Decide whether code age and plots fit their time budgets, printing a
    skip notice for each one cut. The projected blame time comes back with them: meta.json records it."""
    projected = float(estimate.get("seconds", 0.0))
    age_ok = args.deep or projected <= args.time_budget
    plots_ok = args.plots and (args.deep or estimate["blames"] <= args.budget)
    if not age_ok:
        # a partial estimate stopped at the first value over the budget, so its number only restates the budget
        took = (f"more than the {args.time_budget:,.0f}s time budget" if estimate.get("partial")
                else f"about {projected:,.0f}s, over the {args.time_budget:,.0f}s time budget")
        ui.print(f"[yellow]code age skipped:[/yellow] a blame pass over {estimate.get('code_files', estimate['files']):,} files is projected "
                 f"to take {took}. Rerun with --deep to force it, raise --time-budget, or --ignore-data to shrink it.")
    if args.plots and not plots_ok:
        ui.print(f"[yellow]plots skipped:[/yellow] about {estimate['blames']:,} git blames "
                 f"({estimate['files']:,} files × {estimate['samples']} samples) exceeds the budget of {args.budget:,}. "
                 f"Rerun with --deep to force them, or --ignore-data to shrink them.")
    return age_ok, plots_ok, projected


def _meta_for_run(repo_dir: str, args, estimate, age_ok: bool, plots_ok: bool, projected: float,
                  tracked: list = None) -> tuple[dict, str | None]:
    """Collect this run's meta.json: repo facts plus a planned status record for every optional step.
    Raises NoCommits when --since leaves no commits to analyse."""
    types_spec = _types_spec(args.file_types)

    meta = run.collect_meta(repo_dir, since=args.since_date, scope=args.path)
    meta["run"] = run.manifest(repo_dir, args)   # what produced this report: commit, gitmole and tool versions, the options
    meta["file_types"] = types_spec   # the loader filters scc's size data the way every other step was filtered
    meta["gone_months"] = args.gone
    tracked = blame.text_files(repo_dir) if tracked is None else tracked   # every tracked text file: --ignore shapes blame and functions, never what a file is
    attrs = filetypes.attributes(repo_dir, tracked)   # one git check-attr pass, shared by the two lists below
    meta["generated"] = filetypes.generated_files(repo_dir, tracked, attrs=attrs)   # hidden from the tables, out of the findings
    meta["vendored"] = filetypes.vendored_paths(repo_dir, tracked, attrs=attrs)    # somebody else's code, by the licence it carries or the attribute it declares
    meta["credential_files"] = filetypes.credential_files(filetypes.git_paths(repo_dir, "ls-files"))   # by name, over every tracked file
    if args.since_date and meta["commits"] == 0:
        raise NoCommits(f"no commits since {args.since_date}" + (f" under {', '.join(args.path)}" if args.path else "") + "; widen --since")
    if args.now:
        meta["now"] = args.now
    meta["age"] = {"status": "run" if age_ok else "skipped", "method": "blame", "files": estimate.get("code_files", estimate["files"]),
                   "projected_seconds": projected, "time_budget": args.time_budget}
    if estimate.get("partial"):
        meta["age"]["projected_partial"] = True   # projected_seconds is a lower bound: the sample stopped once it was over
    if args.plots:
        meta["plots"] = {"status": "run" if plots_ok else "skipped", "blames": estimate["blames"], "samples": estimate["samples"], "budget": args.budget}
    lizard_ok = args.lizard
    meta["functions"] = {"status": "planned" if lizard_ok else "skipped"}   # "run" only once the step has finished
    meta["structure"] = ({"status": "planned"} if getattr(args, "structure", False)
                         else {"status": "skipped", "install": "the grammars need Python 3.10 or newer; reinstall gitmole on 3.10+"})
    meta["trend"] = {"status": "planned"}
    from . import maat as _maat
    cut = _maat.months_before(meta["last_date"], 6) if meta["last_date"] else None
    first = meta.get("first_date_all") or meta["first_date"]   # the backtest reads the whole history, window or not
    if cut and first and first <= _maat.months_before(cut, 6):
        meta["backtest"] = {"status": "planned", "until": cut}
    else:
        cut = None
        meta["backtest"] = {"status": "skipped", "reason": "too little history to backtest"}
    return meta, cut


def _record_statuses(meta, results, age_ok: bool, plots_ok: bool, lizard_ok: bool, cut) -> None:
    """Turn each step's exit code into its final status: run, skipped, timeout or failed."""
    def status(step, default="run"):
        rc = results.get(step, 0)
        return default if rc == 0 else ("timeout" if rc == "timeout" else "failed")
    if age_ok:
        meta["age"]["status"] = status("code age")
    if plots_ok:
        meta["plots"]["status"] = status("git-of-theseus")
    if lizard_ok:
        meta["functions"]["status"] = status("functions")
    if (meta.get("structure") or {}).get("status") == "planned":
        meta["structure"]["status"] = status("structure")
    if "trend" in results:
        meta["trend"]["status"] = status("trend")
    if cut and "backtest" in results:
        meta["backtest"]["status"] = status("backtest")
    # every step, not only the optional ones above: a killed scc is otherwise a report of "0 lines" with no reason
    meta["steps"] = {name: "run" if rc == 0 else (rc if isinstance(rc, str) else "failed") for name, rc in results.items()}


def _coverage(repo_dir: str, out_dir: str, tracked: list = None) -> dict:
    """How many tracked text files each reason claims, from the report as the steps left it. An
    unreadable output directory (a killed run) records nothing rather than failing the run."""
    from . import classify
    try:
        report = load.load_report(out_dir, nested=False)
    except load.Unreadable:
        return {}
    return classify.coverage(classify.Classifier(report), blame.text_files(repo_dir) if tracked is None else tracked)


def _analyse(repo_dir: str, out_dir: str, args, ui: Console, planner, estimator) -> None:
    """Run the whole pipeline for one repository into out_dir. Raises NoCommits for a repository with
    no commit yet, before anything reads its history."""
    if not run.has_commits(repo_dir):
        raise NoCommits("no commits yet: there is nothing to analyse")
    try:
        scope.validate(repo_dir, args.path)   # before anything is written: a mistyped --path leaves no output directory behind
    except ValueError as e:
        raise NoCommits(str(e)) from None
    os.makedirs(os.path.join(out_dir, "theseus"), exist_ok=True)
    log_path = os.path.join(out_dir, "run.log")
    open(log_path, "w").close()

    ignore = list(run.DATA_IGNORES if args.ignore_data else []) + list(args.ignore)
    tracked = blame.text_files(repo_dir)   # read the index once: the steps below do not change it
    estimate = estimator(repo_dir, run.MONTH, ignore=ignore, types=filetypes.parse(args.file_types),
                         budget=None if args.deep else args.time_budget, tracked=tracked, **({"scope": args.path} if args.path else {}))
    age_ok, plots_ok, projected = _budgets(args, estimate, ui)

    meta, cut = _meta_for_run(repo_dir, args, estimate, age_ok, plots_ok, projected, tracked=tracked)
    types_spec = meta["file_types"]
    if run.is_shallow(repo_dir):
        meta["shallow"] = True   # the history stops at the graft
    lizard_ok = args.lizard
    run.clear_outputs(out_dir)
    steps = planner(repo_dir, out_dir, branch=meta["branch"], age=age_ok, plots=plots_ok, ignore=ignore, types=types_spec, now=args.now,
                    since=args.since_date, lizard=lizard_ok, backtest=cut, ignore_revs=run.ignore_revs_files(repo_dir),
                    structure=getattr(args, "structure", False),
                    **({"scope": args.path} if args.path else {}))
    run.save_meta(meta, out_dir)
    stats = {}
    results = _execute(steps, log_path, repo_dir, args.workers, ui, timeout=args.timeout, stats=stats)
    if _control.cancelled.is_set():
        killed = [n for n, rc in results.items() if rc == "cancelled"]
        ui.print(f"[red]interrupted:[/red] killed {len(killed)} step(s)")
        raise Interrupted()

    _record_statuses(meta, results, age_ok, plots_ok, lizard_ok, cut)
    # what each step cost, for the measurement harness's runtime guard; they vary, so --json keeps them in its envelope
    meta["step_seconds"] = {n: s["seconds"] for n, s in sorted(stats.items())}
    meta["step_peak_mb"] = {n: s["peak_mb"] for n, s in sorted(stats.items())}
    meta["coverage"] = _coverage(repo_dir, out_dir, scope.keep(tracked, args.path))
    run.save_meta(meta, out_dir)

    failed = [n for n, rc in results.items() if rc != 0]
    if failed:
        ui.print(f"[yellow]{len(failed)} step(s) did not complete:[/yellow] " + ", ".join(f"{n} ({results[n]})" for n in failed))
        ui.print(f"[dim]details in {log_path}[/dim]\n")


def _portfolio(owner: str, args, console: Console, ui: Console, planner, estimator, lister, cloner) -> int:
    """Analyse every non-archived repository of an owner and summarise them in one table."""
    import json

    from . import render

    base = os.path.abspath(args.out) if args.out else os.path.join(os.getcwd(), f"analysis-{owner}")
    try:
        repos = lister(owner)
    except run.GhError as e:
        ui.print(f"[red]could not list repositories for {owner}:[/red] {e}", soft_wrap=True)
        return 2
    if not repos:
        ui.print(f"[red]no repositories found for {owner}[/red]")
        return 2
    parent = tempfile.mkdtemp(prefix="gitmole-", dir=os.environ.get("TMPDIR"))
    reports = []
    try:
        for i, name in enumerate(repos, 1):
            ui.print(f"[bold]{name}[/bold] [dim]({i}/{len(repos)})[/dim]")
            try:
                repo_dir = cloner(f"{owner}/{name}", parent)
            except run.GhError as e:
                ui.print(f"[red]could not clone {owner}/{name}:[/red] {e}", soft_wrap=True)
                continue
            out_dir = os.path.join(base, name)
            try:
                _analyse(repo_dir, out_dir, args, ui, planner, estimator)
            except Interrupted:
                return 130
            except NoCommits as e:
                ui.print(f"[yellow]{name}:[/yellow] {e}; skipped")
                continue
            try:
                report = load.load_report(out_dir)
            except load.Unreadable as e:
                ui.print(f"[yellow]{name}:[/yellow] {e}; skipped", soft_wrap=True)
                continue
            reports.append((name, report, findings.evaluate(report)))
    finally:
        shutil.rmtree(parent, ignore_errors=True)   # the temp clones; nothing reads them after the run

    def export_path(p):
        return p if p == "-" or os.path.isabs(p) else os.path.join(base, p)

    if args.json:
        _write(json.dumps(render.portfolio_json(owner, reports), indent=2) + "\n", export_path(args.json), console)
    if args.markdown:
        _write(render.portfolio_markdown(owner, reports), export_path(args.markdown), console)
    if "-" not in (args.json, args.markdown):
        render.print_section(console, render.portfolio_section(reports))
        console.print(Text(f"\nPer-repository results in {base}", style="dim"), soft_wrap=True)
    if not args.fail_on and not args.require_vuln_db:
        return 0
    from . import gate
    if args.fail_on and gate.tripped([f for _, _, found in reports for f in found], args.fail_on):
        return gate.EXIT_FOUND
    blind = [name for name, report, _ in reports if gate.no_database(report)]
    if blind:
        ui.print(f"{gate.NO_DATABASE_NOTE}: {', '.join(blind)}", soft_wrap=True, markup=False, highlight=False)
    missing = [(name, gate.describe(gate.unfinished(report))) for name, report, _ in reports if gate.unfinished(report)] if args.fail_on else []
    if args.require_vuln_db:
        missing += [(name, "no vulnerability database") for name in blind]
    if missing:
        ui.print(f"[red]gate incomplete:[/red] {'; '.join(f'{name}: {what}' for name, what in missing)}, so the gate could not check "
                 f"what those steps would have found (exit {gate.EXIT_INCOMPLETE})", soft_wrap=True)
        return gate.EXIT_INCOMPLETE
    return 0


def _execute(steps, log_path, repo_dir, workers, console, timeout=None, stats: dict = None) -> dict:
    """Run the steps under a Live display: the banner pulsing above a status line."""
    active, lock = set(), threading.Lock()
    started = time.monotonic()
    spinner = Spinner("dots", style="cyan")
    frame = banner.frames(version=__version__)

    def label() -> str:
        with lock:
            names = ", ".join(sorted(active))
        return f"running {names}" if names else "finishing"

    def view():
        if not console.is_terminal:
            return Text(label())
        status = Group(spinner, Text(" " + label(), style="dim"))
        return Group(next(frame), status)

    def on_start(name):
        with lock:
            active.add(name)

    def on_done(name, rc):
        with lock:
            active.discard(name)

    results = {}
    with Live(view(), console=console, refresh_per_second=10, transient=False) as live:
        worker = threading.Thread(
            target=lambda: results.update(run.execute(steps, log_path=log_path, cwd=repo_dir, workers=workers, on_start=on_start, on_done=on_done, timeout=timeout, control=_control, stats=stats)))
        worker.start()
        while worker.is_alive():
            live.update(view())
            worker.join(0.1)
        live.update(Group(banner.neon(version=__version__), Text("")) if console.is_terminal else Text(""))
    console.print(f"[dim]{len(steps)} steps in {time.monotonic() - started:.1f}s[/dim]\n")
    return results


def _write(text: str, target: str, console: Console) -> None:
    if target == "-":
        console.print(Text(text), soft_wrap=True, end="")
    else:
        with open(target, "w") as fh:
            fh.write(text)


def _render(out_dir: str, console: Console, ui: Console, args, err: Console) -> int:
    from . import render

    try:
        report = load.load_report(out_dir)
    except load.Unreadable as e:
        err.print(f"[red]{e}[/red]", soft_wrap=True)
        return 2
    found = findings.evaluate(report)
    risk = None
    if args.risk:
        try:
            stats = run.change_stats(report["meta"].get("path") or os.getcwd(), args.risk)
        except ValueError as e:
            err.print(f"[red]--risk {args.risk}:[/red] {e}", soft_wrap=True)
            return 2
        from . import watch
        risk = {"base": args.risk, **watch.change_risk(report, stats["files"], stats)}
    comparison = None
    if args.compare:
        from . import compare as _compare
        before = _export(args.compare, "--compare", report, err)
        if before is None:
            return 2
        if scope.of(before["meta"]) != scope.of(report["meta"]):
            def said(m):
                return scope.label(scope.of(m)) if scope.of(m) else "the whole repository"
            err.print(f"[red]--compare {args.compare}:[/red] it describes {said(before['meta'])}, this run describes {said(report['meta'])}; "
                      "compare two runs over the same --path", soft_wrap=True)
            return 2
        comparison = _compare.compare(before, report, found)
    counted = found
    if args.baseline:
        before = _export(args.baseline, "--baseline", report, err)
        if before is None:
            return 2
        from . import gate
        counted = gate.against_baseline(report, found, before)
    if args.json:
        _write(render.dumps_json(report, found, risk=risk, compare=comparison), args.json, console)
    if args.markdown:
        _write(render.markdown(report, found, full=args.full, risk=risk, base=args.risk, compare=comparison), args.markdown, console)
    if args.sarif:
        from . import sarif
        _write(sarif.dumps(report, found, scope=args.sarif_scope), args.sarif, console)
    if args.sbom:
        from . import sbom
        packages = sbom.read_packages(out_dir)
        if packages is None:
            err.print("[red]--sbom:[/red] no package list in the output directory; the osv-scanner step writes it, and did not "
                      f"(dependencies: {(report.get('dependencies') or {}).get('status', 'not-run')}; run.log says why)", soft_wrap=True)
            return 2
        _write(sbom.dumps(report, packages), args.sbom, console)
    if "-" not in (args.json, args.markdown, args.sarif, args.sbom):
        render.report(report, found, console, full=args.full, risk=risk, base=args.risk, compare=comparison)
    _feedback(report, found, args, console, err)
    if args.baseline and args.fail_on:
        from . import gate
        known = [f for f in found if f.get("baseline") == "in the baseline" and gate.tripped([f], args.fail_on)]
        if known:
            err.print(f"[dim]--baseline: {len(known)} finding(s) at {args.fail_on} or worse were in {args.baseline} and do not count toward "
                      f"--fail-on: {', '.join(dict.fromkeys(f['rule']['id'] for f in known))}[/dim]", soft_wrap=True)
    return _gate_exit(report, counted, risk, args, err)


def _export(path: str, flag: str, report: dict, err: Console):
    """An earlier --json export of the same clone, or None after saying why not."""
    import json

    from . import compare as _compare
    try:
        with open(path, encoding="utf-8") as fh:
            before = json.load(fh)
    except (OSError, ValueError) as e:
        err.print(f"[red]{flag} {path}:[/red] {e}", soft_wrap=True)
        return None
    if not _compare.is_export(before):
        err.print(f"[red]{flag} {path}:[/red] not a gitmole --json export (it needs meta, findings with rule ids, and watch; "
                  "exports from before 0.8.0 have no rule ids)", soft_wrap=True)
        return None
    if before["meta"].get("name") != report["meta"].get("name"):
        err.print(f"[red]{flag} {path}:[/red] it describes {before['meta'].get('name')}, this run describes {report['meta'].get('name')}; "
                  "the two exports must be of the same clone", soft_wrap=True)
        return None
    return before


def _gate_exit(report: dict, found: list, risk, args, err: Console) -> int:
    """The exit code of the gates asked for: 3 when one found what it stops on; 4 when none did and a step
    one of them reads did not complete, so it could not check (gate.py), or when --require-vuln-db was asked
    for and the dependency scan had no database; 0 otherwise, and always without a gate."""
    from . import gate
    code, missing, flags = 0, [], []
    if args.fail_on:
        missing, flags = gate.unfinished(report), ["--fail-on"]
        if gate.tripped(found, args.fail_on):
            code = gate.EXIT_FOUND
    if risk is not None and args.risk_threshold is not None:
        short = gate.unfinished(report, gate.RISK_STEPS)
        missing, flags = sorted(set(missing) | set(short)), flags + (["--risk-threshold"] if short else [])
        if risk["total"] > args.risk_threshold:
            code = gate.EXIT_FOUND
    if gate.no_database(report) and (args.fail_on or args.require_vuln_db):
        err.print(gate.NO_DATABASE_NOTE + ("" if code or not args.require_vuln_db else f" (exit {gate.EXIT_INCOMPLETE}: --require-vuln-db)"),
                  soft_wrap=True, markup=False, highlight=False)
        if args.require_vuln_db and not missing:
            code = code or gate.EXIT_INCOMPLETE
    if missing:
        flags = " and ".join(flags)
        err.print(f"[red]gate incomplete:[/red] {gate.describe(missing)}, so {flags} could not check what "
                  f"{'that step' if len(missing) == 1 else 'those steps'} would have found"
                  + ("" if code else f" (exit {gate.EXIT_INCOMPLETE}); run.log in the output directory says why"), soft_wrap=True)
        code = code or gate.EXIT_INCOMPLETE
    return code


def _feedback(report: dict, found: list, args, console: Console, err: Console, ask=None) -> None:
    """Ask the reader whether these findings were worth acting on, where asking is allowed (feedback.py).
    Everything here goes to stderr after the report, so no export and no golden file can hold a word of it,
    and any failure is silent: a question is never worth breaking a run over."""
    from . import feedback
    try:
        path = feedback.state_path()
        state = feedback.read_state(path) if path else {}
        today = dt.date.today().isoformat()
        if not feedback.should_ask(args, state, today):
            return
        with _interruptible():   # Ctrl-C at a question ends the questions, not only the (finished) steps
            answers = (ask or feedback.ask)(found, err.print, lambda text: input(text))
        if path:
            feedback.write_state(path, {**state, "asked": today, **({"answered": today} if answers else {"declined": True})})
        if not answers:
            return
        target = os.path.join(os.path.abspath(args.out or "."), feedback.FILE_NAME) if getattr(args, "out", None) \
            else os.path.abspath(feedback.FILE_NAME)
        feedback.write(target, feedback.payload(answers, report, today, __version__))
        for line in feedback.how_to_send(target, __version__):
            err.print(f"[dim]{line}[/dim]", soft_wrap=True)
    except (EOFError, KeyboardInterrupt):
        pass          # no terminal after all, or the reader pressed ctrl-c: the run is already done
    except Exception:   # noqa: BLE001 - a question is never worth breaking a finished run over
        pass


if __name__ == "__main__":
    sys.exit(main())

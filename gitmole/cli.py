"""Command line entry point: gitmole <path | owner/repo | url> [--out DIR] [--no-run]."""
from __future__ import annotations

import argparse
import os
import signal
import sys
import tempfile
import threading
import time

from rich.console import Console, Group
from rich.live import Live
from rich.spinner import Spinner
from rich.text import Text

from . import __version__, banner, filetypes, findings, load, run


def parse_args(argv):
    p = argparse.ArgumentParser(prog="gitmole", description="Analyse a git repository offline and print a report.")
    p.add_argument("target", help="local clone path, owner/repo, or git URL")
    p.add_argument("--out", help="output directory (default: analysis-<repo> next to the clone, or in cwd for remote targets)")
    p.add_argument("--no-run", action="store_true", help="skip the tools; re-render the report from an existing output directory")
    p.add_argument("--workers", type=int, default=6, help="how many tools to run at once")
    p.add_argument("--plots", action="store_true", help="also run git-of-theseus for the code-age and survival plots")
    p.add_argument("--deep", action="store_true", help="run code age and plots even when the repo exceeds the blame budget")
    p.add_argument("--time-budget", type=float, default=60, metavar="SECONDS", help="skip code age when its projected time exceeds this (default 60)")
    p.add_argument("--budget", type=int, default=50000, help="max git blames before plots are skipped (default 50000)")
    p.add_argument("--timeout", type=float, default=900, help="seconds any single tool may run before being killed (default 900)")
    p.add_argument("--ignore-data", action="store_true", help="exclude data-like files (csv, json, lock, minified, vendored) from code age, function metrics and plots")
    p.add_argument("--ignore", action="append", default=[], metavar="GLOB", help="extra ignore pattern for code age, function metrics and plots (repeatable)")
    p.add_argument("--since", metavar="WHEN", help="only analyse history newer than this: 2y, 18m, 90d or YYYY-MM-DD (code age is always the whole tree)")
    p.add_argument("--gone", type=int, default=12, metavar="MONTHS", help="a person with no commits this many months before the last commit counts as gone (default 12)")
    p.add_argument("--file-types", metavar="LIST", help="comma-separated extensions to treat as code (default: a built-in source list), or 'all'")
    p.add_argument("--list-file-types", action="store_true", help="list the file types in the repository, with counts and whether they count as code, then exit")
    p.add_argument("--duplicates", action="store_true", help="also look for duplicated code blocks (minutes and gigabytes on a large repo; function metrics alone take seconds)")
    p.add_argument("--full", action="store_true", help="every column and every row in the terminal report (the default is the tighter, readable one)")
    p.add_argument("--json", metavar="PATH", help="write the report and findings as JSON to PATH, or - for stdout")
    p.add_argument("--markdown", metavar="PATH", help="write the report as Markdown to PATH, or - for stdout")
    p.add_argument("--fail-on", choices=findings.SEVERITIES, help="exit 3 if any finding is at this severity or worse")
    p.add_argument("--risk", metavar="BASE", help="score the files changed since BASE (merge base with HEAD) with the watch list's score; needs a local path")
    p.add_argument("--version", action="version", version=f"gitmole {__version__}")
    return p.parse_args(argv)


_control = run.Control()


def interrupt(*_):
    """Ctrl-C: kill every running step's process group; the run loop then exits 130."""
    _control.cancel()


def main(argv=None, console: Console = None, tool_check=run.missing_tools, planner=run.plan, estimator=run.estimate_blames,
         lister=run.list_repos, cloner=run.clone, lizard_check=run.has_lizard) -> int:
    global _control
    _control = run.Control()
    if threading.current_thread() is threading.main_thread():
        signal.signal(signal.SIGINT, interrupt)
    args = parse_args(sys.argv[1:] if argv is None else argv)
    console = console or Console()
    err = Console(stderr=True) if console.file is sys.stdout else console
    # When an export goes to stdout, everything else (banner, progress, report) moves to stderr.
    quiet = "-" in (args.json, args.markdown)
    ui = Console(stderr=True) if quiet else console

    now = os.environ.get("GITMOLE_NOW") or None
    if now:
        from . import maat
        try:
            maat.validate_now(now)
        except ValueError as e:
            err.print(f"[red]GITMOLE_NOW:[/red] {e}")
            return 2
        ui.print(f"[yellow]reference date fixed by GITMOLE_NOW:[/yellow] {now}")
    args.since_date = None
    if args.since:
        import datetime as _dt
        try:
            args.since_date = run.parse_since(args.since, now or _dt.date.today().isoformat())
        except ValueError as e:
            err.print(f"[red]{e}[/red]")
            return 2

    if args.no_run:
        if args.since:
            err.print("[red]--since needs a run:[/red] a re-render cannot narrow an earlier analysis")
            return 2
        out_dir = os.path.abspath(args.target)
        if not os.path.isfile(os.path.join(out_dir, "meta.json")):
            err.print(f"[red]no gitmole output found in {out_dir}[/red] (expected meta.json)")
            return 2
        if ui.is_terminal:
            ui.print(banner.neon())
        return _render(out_dir, console, ui, args)

    try:
        kind, target = run.classify_target(args.target)
    except ValueError as e:
        err.print(f"[red]{e}[/red]")
        return 2
    if args.risk and kind != "path":
        err.print("[red]--risk needs a local path[/red]")
        return 2

    args.now = now
    if args.since_date:
        ui.print(f"[dim]history bounded: since {args.since_date}[/dim]")

    if args.list_file_types:
        if kind != "path":
            err.print("[red]--list-file-types needs a local path[/red]")
            return 2
        return _list_file_types(target, args, console)

    missing = tool_check(plots=args.plots)
    if missing:
        err.print("[red]missing tools:[/red] " + ", ".join(missing))
        err.print("run bin/install.sh from the gitmole checkout")
        return 2
    args.lizard = lizard_check()   # decided once, for every repository this run analyses

    if kind == "org":
        return _portfolio(target, args, console, ui, planner, estimator, lister, cloner)

    if kind == "remote":
        parent = tempfile.mkdtemp(prefix="gitmole-", dir=os.environ.get("TMPDIR"))
        ui.print(f"[dim]cloning {target} into {parent}[/dim]")
        try:
            repo_dir = cloner(target, parent)
        except run.GhError as e:
            err.print(f"[red]could not clone {target}:[/red] {e}", soft_wrap=True)
            return 2
    else:
        repo_dir = target

    out_dir = run.output_dir(kind, repo_dir, args.out)
    try:
        _analyse(repo_dir, out_dir, args, ui, planner, estimator)
    except Interrupted:
        return 130
    except NoCommits as e:
        err.print(f"[red]{e}[/red]")
        return 2
    return _render(out_dir, console, ui, args)


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

    rows = [(k, n, "yes" if inc else "no") for k, n, inc in filetypes.discover(repo_dir, filetypes.parse(args.file_types))]
    sec = render._section("File types", [("type", {}), ("files", render.RIGHT), ("code", {})], rows, note="no tracked files",
                          caption="code = analysed for hotspots, coupling and code age")
    render.print_section(console, sec)
    return 0


def _analyse(repo_dir: str, out_dir: str, args, ui: Console, planner, estimator) -> None:
    """Run the whole pipeline for one repository into out_dir."""
    os.makedirs(os.path.join(out_dir, "theseus"), exist_ok=True)
    log_path = os.path.join(out_dir, "run.log")
    open(log_path, "w").close()

    ignore = list(run.DATA_IGNORES if args.ignore_data else []) + list(args.ignore)
    estimate = estimator(repo_dir, run.MONTH, ignore=ignore, types=filetypes.parse(args.file_types))
    projected = float(estimate.get("seconds", 0.0))
    age_ok = args.deep or projected <= args.time_budget
    plots_ok = args.plots and (args.deep or estimate["blames"] <= args.budget)
    if not age_ok:
        ui.print(f"[yellow]code age skipped:[/yellow] a blame pass over {estimate.get('code_files', estimate['files']):,} files is projected "
                 f"to take about {projected:,.0f}s, over the {args.time_budget:,.0f}s time budget. "
                 f"Rerun with --deep to force it, raise --time-budget, or --ignore-data to shrink it.")
    if args.plots and not plots_ok:
        ui.print(f"[yellow]plots skipped:[/yellow] about {estimate['blames']:,} git blames "
                 f"({estimate['files']:,} files × {estimate['samples']} samples) exceeds the budget of {args.budget:,}. "
                 f"Rerun with --deep to force them, or --ignore-data to shrink them.")
    ignore = list(run.DATA_IGNORES if args.ignore_data else []) + list(args.ignore)
    types_spec = _types_spec(args.file_types)

    meta = run.collect_meta(repo_dir, since=args.since_date)
    meta["file_types"] = types_spec   # the loader filters scc's size data the way every other step was filtered
    meta["gone_months"] = args.gone
    if args.since_date and meta["commits"] == 0:
        raise NoCommits(f"no commits since {args.since_date}; widen --since")
    if args.now:
        meta["now"] = args.now
    meta["age"] = {"status": "run" if age_ok else "skipped", "method": "blame", "files": estimate.get("code_files", estimate["files"]),
                   "projected_seconds": projected, "time_budget": args.time_budget}
    if args.plots:
        meta["plots"] = {"status": "run" if plots_ok else "skipped", "blames": estimate["blames"], "samples": estimate["samples"], "budget": args.budget}
    lizard_ok = args.lizard
    meta["functions"] = {"status": "planned" if lizard_ok else "skipped"}   # "run" only once the step has finished
    meta["trend"] = {"status": "planned"}
    run.clear_outputs(out_dir)
    steps = planner(repo_dir, out_dir, branch=meta["branch"], age=age_ok, plots=plots_ok, ignore=ignore, types=types_spec, now=args.now,
                    since=args.since_date, lizard=lizard_ok, duplicates=args.duplicates)
    run.save_meta(meta, out_dir)
    results = _execute(steps, log_path, repo_dir, args.workers, ui, timeout=args.timeout)
    if _control.cancelled.is_set():
        killed = [n for n, rc in results.items() if rc == "cancelled"]
        ui.print(f"[red]interrupted:[/red] killed {len(killed)} step(s)")
        raise Interrupted()

    def status(step, default="run"):
        rc = results.get(step, 0)
        return default if rc == 0 else ("timeout" if rc == "timeout" else "failed")
    if age_ok:
        meta["age"]["status"] = status("code age")
    if args.plots and plots_ok:
        meta["plots"]["status"] = status("git-of-theseus")
    if lizard_ok:
        meta["functions"]["status"] = status("functions")
    meta["trend"]["status"] = status("trend")
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
        report = load.load_report(out_dir)
        reports.append((name, report, findings.evaluate(report)))

    def export_path(p):
        return p if p == "-" or os.path.isabs(p) else os.path.join(base, p)

    if args.json:
        _write(json.dumps(render.portfolio_json(owner, reports), indent=2) + "\n", export_path(args.json), console)
    if args.markdown:
        _write(render.portfolio_markdown(owner, reports), export_path(args.markdown), console)
    if "-" not in (args.json, args.markdown):
        render.print_section(console, render.portfolio_section(reports))
        console.print(Text(f"\nPer-repository results in {base}", style="dim"), soft_wrap=True)
    all_found = [f for _, _, found in reports for f in found]
    if args.fail_on and any(findings.SEVERITIES.index(f["severity"]) <= findings.SEVERITIES.index(args.fail_on) for f in all_found):
        return 3
    return 0


def _execute(steps, log_path, repo_dir, workers, console, timeout=None) -> dict:
    """Run the steps under a Live display: the banner pulsing above a status line."""
    active, lock = set(), threading.Lock()
    started = time.monotonic()
    spinner = Spinner("dots", style="cyan")
    frame = banner.frames()

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
            target=lambda: results.update(run.execute(steps, log_path=log_path, cwd=repo_dir, workers=workers, on_start=on_start, on_done=on_done, timeout=timeout, control=_control)))
        worker.start()
        while worker.is_alive():
            live.update(view())
            worker.join(0.1)
        live.update(Group(banner.neon(), Text("")) if console.is_terminal else Text(""))
    console.print(f"[dim]{len(steps)} steps in {time.monotonic() - started:.1f}s[/dim]\n")
    return results


def _write(text: str, target: str, console: Console) -> None:
    if target == "-":
        console.print(Text(text), soft_wrap=True, end="")
    else:
        with open(target, "w") as fh:
            fh.write(text)


def _render(out_dir: str, console: Console, ui: Console, args) -> int:
    import json

    from . import render

    report = load.load_report(out_dir)
    found = findings.evaluate(report)
    risk = None
    if args.risk:
        try:
            files = run.changed_files(report["meta"].get("path") or os.getcwd(), args.risk)
        except ValueError as e:
            (Console(stderr=True) if console.file is sys.stdout else console).print(f"[red]--risk {args.risk}:[/red] {e}", soft_wrap=True)
            return 2
        from . import watch
        risk = {"base": args.risk, **watch.change_risk(report, files)}
    if args.json:
        _write(json.dumps(render.to_json(report, found, risk=risk), indent=2) + "\n", args.json, console)
    if args.markdown:
        _write(render.markdown(report, found, full=args.full, risk=risk, base=args.risk), args.markdown, console)
    if "-" not in (args.json, args.markdown):
        render.report(report, found, console, full=args.full, risk=risk, base=args.risk)
    if args.fail_on and any(findings.SEVERITIES.index(f["severity"]) <= findings.SEVERITIES.index(args.fail_on) for f in found):
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())

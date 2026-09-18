"""Resolve the target, plan the tool invocations, and run them concurrently."""
from __future__ import annotations

import calendar
import datetime as dt
import functools
import importlib.util
import json
import os
import re
import signal
import subprocess
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED

from . import blame, filetypes, identity

MAAT_SCRIPT = os.path.join(os.path.dirname(os.path.realpath(__file__)), "maat.py")
BLAME_SCRIPT = os.path.join(os.path.dirname(os.path.realpath(__file__)), "blame.py")
FUNCTIONS_SCRIPT = os.path.join(os.path.dirname(os.path.realpath(__file__)), "functions.py")
DUPLICATES_SCRIPT = os.path.join(os.path.dirname(os.path.realpath(__file__)), "duplicates.py")
LEAKS_SCRIPT = os.path.join(os.path.dirname(os.path.realpath(__file__)), "leaks.py")
DEPS_SCRIPT = os.path.join(os.path.dirname(os.path.realpath(__file__)), "deps.py")
# jscpd holds every token of every file it scans: about a gigabyte of memory per 25 MB of tracked text
# (a 34 MB tree took 0.9 GB, a 171 MB tree of generated SQL took 4 GB, both in seconds). Past this much
# text the duplicates step is skipped unless --deep asks for it.
DUPLICATES_BUDGET_MB = 80

MONTH = 30 * 24 * 3600  # git-of-theseus sampling interval in seconds

# Data-like files that inflate git-of-theseus without saying anything about code age.
DATA_IGNORES = ["*.csv", "*.json", "*.lock", "*.min.js", "*.min.css", "*.svg", "*.map",
                "vendor/**", "node_modules/**", "third_party/**", "dist/**", "build/**"]

_ORG = re.compile(r"^[\w.-]+/\*$")
_OWNER_REPO = re.compile(r"^[\w.-]+/[\w.-]+$")
_URL = re.compile(r"^(https?://|git@|ssh://)")


def classify_target(target: str) -> tuple:
    if os.path.isdir(target):
        probe = subprocess.run(["git", "-C", target, "rev-parse", "--git-dir"], capture_output=True, text=True)
        if probe.returncode != 0:
            raise ValueError(f"{target} is not a git repository; pass a clone, owner/repo or owner/*")
        return ("path", os.path.abspath(target))
    if _ORG.match(target):
        return ("org", target[:-2])
    if _URL.match(target) or _OWNER_REPO.match(target):
        return ("remote", target)
    raise ValueError(f"{target!r} is neither a directory, owner/repo, nor a git URL")


def repo_name(target: str) -> str:
    tail = target.rstrip("/").rsplit("/", 1)[-1]
    return tail[:-4] if tail.endswith(".git") else tail


def output_dir(kind: str, repo_dir: str, explicit, cwd: str = None) -> str:
    if explicit:
        return os.path.abspath(explicit)
    name = f"analysis-{repo_name(repo_dir)}"
    base = os.path.dirname(repo_dir) if kind == "path" else (cwd or os.getcwd())
    return os.path.join(base, name)


class GhError(RuntimeError):
    """gh failed; the message is its stderr."""


def _gh(argv: list) -> str:
    return subprocess.run(argv, check=True, capture_output=True, text=True).stdout


def _wrap(fn, argv):
    try:
        return fn(argv)
    except subprocess.CalledProcessError as e:
        raise GhError((e.stderr or "").strip() or f"{' '.join(argv)} exited {e.returncode}") from None
    except FileNotFoundError:
        raise GhError("gh is not installed or not on PATH") from None


def list_repos(owner: str, lister=_gh) -> list:
    """Names of the owner's non-archived repositories via gh's REST calls. Raises GhError.

    Your own account lists private repos too; an organisation uses the org endpoint
    (private repos included where the token allows); anyone else gets public repos."""
    me = _wrap(lister, ["gh", "api", "user", "--jq", ".login"]).strip()
    if me == owner:
        path = "user/repos?affiliation=owner&per_page=100"
    else:
        try:
            _wrap(lister, ["gh", "api", f"orgs/{owner}", "--jq", ".login"])
            path = f"orgs/{owner}/repos?per_page=100"
        except GhError:
            path = f"users/{owner}/repos?per_page=100"
    out = _wrap(lister, ["gh", "api", "--paginate", path, "--jq", ".[] | select(.archived | not) | .name"])
    return sorted(set(out.split()))


def clone_url(target: str) -> str:
    """The URL plain git can clone: a URL as given, owner/repo on github.com."""
    return target if _URL.match(target) else f"https://github.com/{target}.git"


def clone(target: str, dest_parent: str, runner=_gh, git_runner=_gh) -> str:
    """Clone a remote target with gh (so private repos use the existing auth), or with plain git when
    gh is missing or fails: a public repository needs no token. Raises GhError naming both failures."""
    dest = os.path.join(dest_parent, repo_name(target))
    try:
        _wrap(runner, ["gh", "repo", "clone", target, dest, "--", "--quiet"])
    except GhError as gh_error:
        try:
            _wrap(git_runner, [*filetypes.GIT, "clone", "--quiet", clone_url(target), dest])
        except GhError as git_error:
            raise GhError(f"{gh_error}; git clone also failed: {git_error}") from None
    return dest


def env_path() -> str:
    """PATH with pip's user bin dirs added."""
    parts = []
    lib = os.path.expanduser("~/Library/Python")
    if os.path.isdir(lib):
        parts += [os.path.join(lib, v, "bin") for v in sorted(os.listdir(lib), reverse=True)]
    return os.pathsep.join(parts + [os.environ.get("PATH", "")])


REQUIRED_TOOLS = ["scc", "git-sizer", "betterleaks", "jscpd", "osv-scanner"]
PLOT_TOOLS = ["git-of-theseus-analyze"]


def has_tool(name: str, path: str = None) -> bool:
    path = env_path() if path is None else path
    return any(os.access(os.path.join(d, name), os.X_OK) for d in path.split(os.pathsep) if d)


def missing_tools(plots: bool = False, path: str = None) -> list:
    path = env_path() if path is None else path
    wanted = REQUIRED_TOOLS + (PLOT_TOOLS if plots else [])
    return [t for t in wanted if not has_tool(t, path)]


def has_structure() -> bool:
    """tree-sitter and at least one grammar wheel: the optional gitmole[structure] extra."""
    from . import structure
    return structure.available()


def has_lizard(finder=importlib.util.find_spec) -> bool:
    """lizard is a Python module run with this interpreter, so PATH says nothing about it."""
    return finder("lizard") is not None


_VERSION_TOKEN = re.compile(r"\d+\.\d+[\w.-]*")


@functools.lru_cache(maxsize=None)
def tool_version(name: str, path: str = None) -> str | None:
    """The version a tool prints for --version: the last version-shaped token on its first line
    ("scc version 4.1.0", "git-sizer release 1.5.0", "osv-scanner version: 2.6.0"). None when the tool is
    missing, hangs or prints none. Cached: a tool's version cannot change within a process, so a run with
    several steps (or a test calling manifest() often) pays for one --version per tool, not one per call."""
    try:
        proc = subprocess.run([name, "--version"], capture_output=True, text=True, timeout=10, env=dict(os.environ, PATH=path or env_path()))
    except (OSError, subprocess.TimeoutExpired):
        return None
    first = next((l for l in (proc.stdout + "\n" + proc.stderr).splitlines() if l.strip()), "")
    found = _VERSION_TOKEN.findall(first)
    return found[-1] if found else None


def lizard_version() -> str | None:
    """lizard is a module of this interpreter, so its version comes from the package metadata."""
    from importlib.metadata import PackageNotFoundError, version
    try:
        return version("lizard")
    except PackageNotFoundError:
        return None


def manifest(repo_dir: str, args, version_of=tool_version) -> dict:
    """What produced this report: the commit analysed, gitmole's version, every tool's, and the options
    that change what the steps see without being recorded elsewhere in meta.json (--since, --file-types,
    --now and --gone are top-level fields already). Two reports that differ can then be told apart by cause."""
    from . import __version__
    names = ["git", *REQUIRED_TOOLS] + (PLOT_TOOLS if getattr(args, "plots", False) else [])
    tools = {name: version_of(name) for name in names}
    tools["lizard"] = lizard_version()
    return {"commit": _git(repo_dir, "rev-parse", "HEAD").strip(), "gitmole": __version__, "tools": tools,
            "options": {"ignore": list(args.ignore), "ignore_data": bool(args.ignore_data), "deep": bool(args.deep)}}


# Everything a run writes besides meta.json and run.log. Removed before each run so a reused
# --out directory never shows a previous run's data as this run's (a step skipped or killed
# this time would otherwise leave last time's file in place).
OUTPUTS = ["size.json", "repo-health.txt", "secrets.json", "dependencies.json", "log.txt", "activity.json", "functions.csv", "signing.json", "hygiene.json", "unreachable.json", "structure.json", "provenance.json",
           "duplicates.json", "duplicates.txt",   # duplicates.txt: what lizard's finder wrote before jscpd
           "theseus/cohorts.json", "theseus/authors.json", "theseus/survival.json", "code-age.png", "survival.png", "trend.json"]
OUTPUT_GLOBS = ["maat-*.csv"]
# directories a run writes: the backtest sub-report, and the temporary checkouts the trend and
# backtest steps make under the output directory, and jscpd's raw report (a SIGKILL leaves those behind).
OUTPUT_DIR_GLOBS = ["backtest", ".backtest-tree-*", ".trend-*", ".jscpd-*"]


def clear_outputs(out_dir: str) -> None:
    import glob
    import shutil
    paths = [os.path.join(out_dir, n) for n in OUTPUTS]
    for g in OUTPUT_GLOBS:
        paths += glob.glob(os.path.join(out_dir, g))
    for g in OUTPUT_DIR_GLOBS:
        paths += glob.glob(os.path.join(out_dir, g))
    for path in paths:
        if os.path.isdir(path):
            shutil.rmtree(path, ignore_errors=True)
        elif os.path.isfile(path):
            os.remove(path)


LOG_FORMAT = "--%h--%ad--%aN--%s%x1f%(trailers:key=Co-authored-by,valueonly,unfold,separator=%x1f)"   # the subject, then each co-author, unit-separated


def ignore_revs_files(repo_dir: str) -> list:
    """The files in which the repository declares commits uninteresting: .git-blame-ignore-revs at the
    root, the convention GitHub and the formatters' docs follow, and whatever blame.ignoreRevsFile
    names (relative to the root), each once, only those that exist."""
    out = []
    conventional = os.path.join(repo_dir, ".git-blame-ignore-revs")
    if os.path.isfile(conventional):
        out.append(conventional)
    proc = subprocess.run(["git", "config", "--get", "blame.ignoreRevsFile"], cwd=repo_dir, capture_output=True, text=True)
    configured = proc.stdout.strip() if proc.returncode == 0 else ""
    if configured:
        path = os.path.normpath(configured if os.path.isabs(configured) else os.path.join(repo_dir, configured))
        if os.path.isfile(path) and path not in out:
            out.append(path)
    return out


def plan(repo_dir: str, out_dir: str, branch: str = "HEAD", age: bool = True, plots: bool = False,
         procs: int = None, interval: int = MONTH, ignore=(), types: str = None, now: str = None, since: str = None,
         lizard: bool = False, duplicates: bool = True, trend: bool = True, samples: int = 12, backtest: str = None,
         ignore_revs=(), structure: bool = False, duplicates_then: str = None) -> list:
    o = lambda name: os.path.join(out_dir, name)  # noqa: E731
    log = o("log.txt")
    ignores = [x for pattern in ignore for x in ("--ignore", pattern)]
    type_args = ["--types", types] if types else []
    revs_args = [x for path in ignore_revs for x in ("--ignore-revs", path)]
    blame_argv = [sys.executable, BLAME_SCRIPT, repo_dir, out_dir, "--procs", str(procs or blame.default_procs()), *ignores, *type_args, "--aliases", o("meta.json"), "--log", log]
    theseus_argv = ["git-of-theseus-analyze", ".", "--branch", branch, "--outdir", o("theseus"),
                    "--procs", str(procs or os.cpu_count() or 2), "--interval", str(interval), *ignores]
    steps = [
        {"name": "scc", "argv": ["scc", "--by-file", "--format", "json"], "stdout": o("size.json"), "deps": []},
        {"name": "git-sizer", "argv": ["git-sizer", "--verbose"], "stdout": o("repo-health.txt"), "deps": []},
        {"name": "betterleaks", "argv": [sys.executable, LEAKS_SCRIPT, o("secrets.json")], "stdout": None, "deps": []},   # hashes the values before anything is written
        {"name": "osv-scanner", "argv": [sys.executable, DEPS_SCRIPT, o("dependencies.json")], "stdout": None, "deps": []},   # offline, against the local database
        # -M: a move is not an edit; -w --ignore-blank-lines: a whitespace-only hunk is not a changed line, so a reformat that only
        # re-indents a file is not a revision of it; HEAD, not --all: a backport on a release branch is not a second fix, and the
        # stash is not a commit
        {"name": "git-log", "argv": [*filetypes.GIT, "log", "HEAD", "--use-mailmap", "--numstat", "--date=iso-strict", f"--pretty=format:{LOG_FORMAT}", "-M", "-w", "--ignore-blank-lines"], "stdout": log, "deps": []},
        {"name": "change analysis", "argv": [sys.executable, MAAT_SCRIPT, log, out_dir, *type_args, *(["--now", now] if now else []), *(["--since", since] if since else []), "--aliases", o("meta.json"), *revs_args], "stdout": None, "deps": ["git-log"]},
        {"name": "signing", "argv": [sys.executable, "-m", "gitmole.signing", out_dir], "stdout": None, "deps": []},   # the gpgsig headers, no keyring
        {"name": "hygiene", "argv": [sys.executable, "-m", "gitmole.hygiene", out_dir], "stdout": None, "deps": []},   # the Scorecard checks, from the clone
        {"name": "provenance", "argv": [sys.executable, "-m", "gitmole.provenance", out_dir], "stdout": None, "deps": []},   # trailers, cohorts, agent files
    ]
    workers = procs or blame.default_procs()
    if lizard:
        steps.append({"name": "functions", "argv": [sys.executable, FUNCTIONS_SCRIPT, repo_dir, out_dir, "--procs", str(workers), *ignores, *type_args],
                      "stdout": None, "deps": []})
    if structure:   # tree-sitter: nesting, cognitive complexity, debt markers, the import graph; gitmole[structure] only
        steps.append({"name": "structure", "argv": [sys.executable, "-m", "gitmole.structure", out_dir, "--procs", str(workers)], "stdout": None, "deps": []})
    if duplicates:
        steps.append({"name": "duplicates", "argv": [sys.executable, DUPLICATES_SCRIPT, repo_dir, out_dir, "--procs", str(workers), *ignores, *type_args,
                                                    *(["--then", duplicates_then] if duplicates_then else [])],   # the rate a year back: a direction
                      "stdout": None, "deps": []})
    if trend:
        steps.append({"name": "trend", "argv": [sys.executable, "-m", "gitmole.trend", out_dir, "--samples", str(samples)],
                      "stdout": None, "deps": ["scc", "change analysis"]})
    if backtest:
        steps.append({"name": "backtest", "argv": [sys.executable, "-m", "gitmole.backtest", out_dir, "--until", backtest],
                      "stdout": None, "deps": ["git-log", "change analysis"]})
    if age:
        steps.append({"name": "code age", "argv": blame_argv, "stdout": None, "deps": ["git-log"]})   # the log names the co-authors a line is shared with
    if plots:
        steps += [
            {"name": "git-of-theseus", "argv": theseus_argv, "stdout": None, "deps": ["code age"] if age else []},
            {"name": "theseus stack plot", "argv": ["git-of-theseus-stack-plot", o("theseus/cohorts.json"), "--outfile", o("code-age.png")], "stdout": None, "deps": ["git-of-theseus"]},
            {"name": "theseus survival plot", "argv": ["git-of-theseus-survival-plot", o("theseus/survival.json"), "--outfile", o("survival.png")], "stdout": None, "deps": ["git-of-theseus"]},
        ]
    return steps


_RELATIVE = re.compile(r"^(\d+)([ymd])$")


def parse_since(spec: str, today: str) -> str:
    """'2y' | '18m' | '90d' | 'YYYY-MM-DD' -> 'YYYY-MM-DD', relative to `today`. Raises ValueError."""
    from . import maat

    hint = "--since wants 2y, 18m, 90d or YYYY-MM-DD"
    spec = (spec or "").strip().lower()
    m = _RELATIVE.match(spec)
    try:
        if not m:
            date = dt.date.fromisoformat(maat.validate_now(spec))
        else:
            n, unit = int(m.group(1)), m.group(2)
            base = dt.date.fromisoformat(today)
            if unit == "d":
                date = base - dt.timedelta(days=n)
            else:
                months = n * 12 if unit == "y" else n
                y, mo = base.year, base.month - months
                while mo <= 0:
                    y, mo = y - 1, mo + 12
                date = dt.date(y, mo, min(base.day, calendar.monthrange(y, mo)[1]))
    except (ValueError, OverflowError):
        raise ValueError(f"{hint}, got {spec!r}") from None
    if date.year < 1970:
        raise ValueError(f"{hint}; git cannot represent dates before 1970, got {spec!r}")
    return date.isoformat()


class Control:
    """Shared cancellation state: tracks running process groups so Ctrl-C can kill them all."""

    def __init__(self):
        self.cancelled = threading.Event()
        self._procs = set()
        self._lock = threading.Lock()

    def register(self, proc):
        with self._lock:
            self._procs.add(proc)

    def unregister(self, proc):
        with self._lock:
            self._procs.discard(proc)

    def cancel(self):
        self.cancelled.set()
        with self._lock:
            procs = list(self._procs)
        for proc in procs:
            _killpg(proc)


def _killpg(proc):
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass


def _run_step(argv, cwd, env, stdout, stderr, timeout, control: Control = None):
    """Run one command in its own process group so a timeout or Ctrl-C can kill its children too.

    stdin is /dev/null: these tools never need input, and letting them inherit an
    interactive terminal as a new session leader corrupts the parent's tty (EIO)."""
    proc = subprocess.Popen(argv, cwd=cwd, env=env, stdin=subprocess.DEVNULL,
                            stdout=stdout, stderr=stderr, start_new_session=True)
    if control:
        control.register(proc)
    try:
        rc = proc.wait(timeout=timeout)
        return "cancelled" if control and control.cancelled.is_set() else rc
    except subprocess.TimeoutExpired:
        _killpg(proc)
        proc.wait()
        return "timeout"
    finally:
        if control:
            control.unregister(proc)


def execute(steps: list, log_path: str, cwd: str = None, workers: int = 6, on_start=None, on_done=None,
            timeout: float = None, control: Control = None) -> dict:
    """Run steps concurrently, honouring deps. Returns {name: returncode | 'skipped' | 'timeout' | 'cancelled'}."""
    results = {}
    lock = threading.Lock()
    package_parent = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
    env = dict(os.environ, PATH=env_path(),
               PYTHONPATH=os.pathsep.join([package_parent] + [p for p in [os.environ.get("PYTHONPATH", "")] if p]))
    pending = {s["name"]: s for s in steps}

    def run_one(step):
        if on_start:
            on_start(step["name"])
        with open(log_path, "a") as log:
            log.write(f"\n==> {step['name']}: {' '.join(step['argv'])}\n")
            log.flush()
            out = open(step["stdout"], "w") if step["stdout"] else log
            try:
                rc = _run_step(step["argv"], cwd, env, out, log, timeout, control)
                if rc == "timeout":
                    log.write(f"==> {step['name']}: killed after {timeout}s timeout\n")
            finally:
                if step["stdout"]:
                    out.close()
        return step["name"], rc

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = set()
        while pending or futures:
            for name in list(pending):
                step = pending[name]
                if control and control.cancelled.is_set():
                    results[name] = "cancelled"
                    del pending[name]
                    if on_done:
                        on_done(name, "cancelled")
                elif any(results.get(d) not in (None, 0) for d in step["deps"]):
                    results[name] = "skipped"
                    del pending[name]
                    if on_done:
                        on_done(name, "skipped")
                elif all(results.get(d) == 0 for d in step["deps"]):
                    futures.add(pool.submit(run_one, step))
                    del pending[name]
            if not futures:
                continue
            done, futures = wait(futures, return_when=FIRST_COMPLETED)
            for f in done:
                name, rc = f.result()
                with lock:
                    results[name] = rc
                if on_done:
                    on_done(name, rc)
    return results


def _git(repo_dir: str, *args) -> str:
    # bytes, decoded with replacement: an author name that is not UTF-8 (laravel has one) must not abort the run
    return subprocess.run(["git", *args], cwd=repo_dir, check=True, capture_output=True).stdout.decode("utf-8", "replace")


def estimate_blames(repo_dir: str, interval: int = MONTH, ignore=(), sample: int = 25, types=filetypes.DEFAULT) -> dict:
    """Cost of the blame passes: a timed projection for the HEAD pass (seconds) and tracked files times
    sampled commits for git-of-theseus (blames); and the bytes of tracked text jscpd would hold (text_bytes)."""
    files = len(_git(repo_dir, "ls-files").splitlines())
    times = [int(t) for t in _git(repo_dir, "log", "--format=%ct").split()]
    span = (max(times) - min(times)) if times else 0
    samples = min(len(times), span // interval + 1) if times else 0
    projection = blame.estimate(repo_dir, ignore=ignore, sample=sample, types=types)
    return {"files": files, "samples": samples, "blames": files * samples,
            "seconds": projection["seconds"], "code_files": projection["files"], "text_bytes": text_bytes(repo_dir, ignore)}


def text_bytes(repo_dir: str, ignore=()) -> int:
    """Size on disk of the tracked text files, after the ignore globs: what the duplicates step scans."""
    total = 0
    for f in blame.text_files(repo_dir, ignore):
        try:
            total += os.path.getsize(os.path.join(repo_dir, f))
        except OSError:
            pass
    return total


_TRAILER_ID = re.compile(r"^\s*(?P<name>[^<]*?)\s*(?:<(?P<email>[^>]*)>)?\s*$")


def _mailmap(repo_dir: str, pairs: list) -> dict:
    """(name, email) -> (name, email) as .mailmap has it, for the identities git's --use-mailmap does
    not touch (the trailers), through one git check-mailmap call. Nothing declared: each maps to itself."""
    out = {p: p for p in pairs}
    if not pairs:
        return out
    stdin = "".join(f"{n} <{e}>\n" for n, e in pairs).encode("utf-8", "surrogateescape")
    proc = subprocess.run(["git", "check-mailmap", "--stdin"], cwd=repo_dir, input=stdin, capture_output=True)
    if proc.returncode != 0:
        return out
    for pair, line in zip(pairs, proc.stdout.decode("utf-8", "replace").split("\n")):
        m = _TRAILER_ID.match(line)
        if m and m.group("name"):
            out[pair] = (m.group("name"), m.group("email") or "")
    return out


def _co_author_rows(repo_dir: str, lines: list) -> tuple:
    """The (date, name, email) rows of the people the Co-authored-by trailers name, through .mailmap,
    and the alias map from a trailer's own spelling to the name git would show for it. Each is a row
    per commit it is named on, like an author's, so the identity table counts the commits they share."""
    raw = []
    for line in lines:
        if "\t" not in line:
            continue
        head, _, trailers = line.partition("\x1f")
        date = head.split("\t", 1)[0]
        for value in trailers.split("\x1f"):
            m = _TRAILER_ID.match(value)
            if m and m.group("name"):
                raw.append((date, m.group("name"), m.group("email") or ""))
    mapped = _mailmap(repo_dir, sorted({(n, e) for _, n, e in raw}))
    rows = [[d, *mapped[(n, e)]] for d, n, e in raw]
    renamed = {n: mapped[(n, e)][0] for n, e in mapped if mapped[(n, e)][0] != n}
    return rows, renamed


def collect_meta(repo_dir: str, since: str = None) -> dict:
    """Repository facts from git. The window (author date >= since) bounds the commit count, the
    date range and the identity table; aliases are merged over the whole history so blame and
    ownership keep merging people who have no commits in the window, and `first_date_all` keeps the
    date of the first commit of all so the backtest can still measure the whole history. Bots
    (anything named *[bot], anything merging with such a name, and names that say bot, CI, deploy
    or automation) are counted apart under "bots", not as identities. The people the Co-authored-by
    trailers name are identities too, credited with the commits they are named on; a bot named only
    in a trailer is nobody."""
    from collections import Counter

    from .load import parse_authors_log

    lines = _git(repo_dir, "log", "HEAD", "--use-mailmap", "--format=%ad\t%aN\t%aE%x1f%(trailers:key=Co-authored-by,valueonly,unfold,separator=%x1f)",
                 "--date=short").split("\n")
    all_rows = [l.partition("\x1f")[0].split("\t", 2) for l in lines if l.partition("\x1f")[0].count("\t") == 2]
    co_rows, renamed = _co_author_rows(repo_dir, lines)
    bot_names = identity.bot_names(parse_authors_log("\n".join(f"{n}\t{e}" for _, n, e in all_rows + co_rows)))
    rows = [r for r in all_rows + co_rows if r[1] not in bot_names]
    all_windowed = [r for r in all_rows if not since or r[0] >= since]
    windowed = [r for r in all_windowed + [r for r in co_rows if not since or r[0] >= since] if r[1] not in bot_names]
    dates = [r[0] for r in all_windowed]
    all_dates = [r[0] for r in all_rows]
    bots = Counter(n for _, n, e in all_windowed if n in bot_names)
    all_identities = identity.merge(parse_authors_log("\n".join(f"{n}\t{e}" for _, n, e in rows)))
    aliases = {a["name"]: i["name"] for i in all_identities for a in i.get("aliases", [])}
    canonical = {i["name"]: i["name"] for i in all_identities} | aliases
    for spelling, name in renamed.items():   # a trailer's own spelling, to the name .mailmap gives it, to whatever that merged into
        aliases.setdefault(spelling, canonical.get(name, name))
    meta = {
        "name": repo_name(repo_dir),
        "path": repo_dir,
        "branch": _git(repo_dir, "rev-parse", "--abbrev-ref", "HEAD").strip(),
        "commits": len(dates),
        "merges": int(_git(repo_dir, "rev-list", "--count", "--merges", "HEAD").strip() or 0),   # the merge regime: squash, merge commits or linear
        "first_date": min(dates) if dates else "",
        "first_date_all": min(all_dates) if all_dates else "",   # unwindowed: the backtest asks how long the history is
        "last_date": max(dates) if dates else "",
        "identities": identity.merge(parse_authors_log("\n".join(f"{n}\t{e}" for _, n, e in windowed))),
        "bots": [{"name": n, "commits": c} for n, c in sorted(bots.items(), key=lambda kv: (-kv[1], kv[0]))],
        "aliases": aliases,
    }
    if since:
        meta["since"] = since
    return meta


def changed_files(repo_dir: str, base: str) -> list:
    """Paths that differ between the merge base with `base` and HEAD, sorted. ValueError when git refuses."""
    proc = subprocess.run([*filetypes.GIT, "diff", "-z", "--name-only", f"{base}...HEAD"], cwd=repo_dir, capture_output=True)
    if proc.returncode != 0:
        raise ValueError((proc.stderr.decode("utf-8", "replace").strip() or f"git diff {base}...HEAD failed"))
    return sorted(p.decode("utf-8", "surrogateescape") for p in proc.stdout.split(b"\0") if p)


def change_stats(repo_dir: str, base: str) -> dict:
    """What a change is, for the Kamei factors: the files that differ between the merge base with
    `base` and HEAD, lines added and deleted per file (whitespace ignored, as the change log is), the
    author of HEAD and how many commits the change spans. ValueError when git refuses."""
    files = changed_files(repo_dir, base)
    proc = subprocess.run([*filetypes.GIT, "diff", "--numstat", "-w", "--ignore-blank-lines", f"{base}...HEAD"], cwd=repo_dir, capture_output=True)
    if proc.returncode != 0:
        raise ValueError((proc.stderr.decode("utf-8", "replace").strip() or f"git diff {base}...HEAD failed"))
    added, deleted = {f: 0 for f in files}, {f: 0 for f in files}
    for line in proc.stdout.decode("utf-8", "surrogateescape").split("\n"):
        parts = line.split("\t", 2)
        if len(parts) != 3:
            continue
        a, d, path = parts
        path = filetypes.unquote(path)
        if " => " in path:
            path = path.split(" => ", 1)[1].rstrip("}") if "{" not in path else path
        added[path] = int(a) if a.isdigit() else 0
        deleted[path] = int(d) if d.isdigit() else 0
    author = subprocess.run(["git", "log", "-1", "--use-mailmap", "--format=%aN", "HEAD"], cwd=repo_dir, capture_output=True).stdout.decode("utf-8", "replace").strip()
    count = subprocess.run(["git", "rev-list", "--count", f"{base}..HEAD"], cwd=repo_dir, capture_output=True, text=True).stdout.strip()
    return {"files": files, "added": {f: added.get(f, 0) for f in files}, "deleted": {f: deleted.get(f, 0) for f in files},
            "author": author, "commits": int(count) if count.isdigit() else 0}


def save_meta(meta: dict, out_dir: str) -> None:
    with open(os.path.join(out_dir, "meta.json"), "w") as fh:
        json.dump(meta, fh, indent=2)


def write_meta(repo_dir: str, out_dir: str) -> dict:
    meta = collect_meta(repo_dir)
    save_meta(meta, out_dir)
    return meta

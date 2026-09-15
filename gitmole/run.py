"""Resolve the target, plan the tool invocations, and run them concurrently."""
from __future__ import annotations

import json
import os
import re
import signal
import subprocess
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED

from . import blame, identity

MAAT_SCRIPT = os.path.join(os.path.dirname(os.path.realpath(__file__)), "maat.py")
BLAME_SCRIPT = os.path.join(os.path.dirname(os.path.realpath(__file__)), "blame.py")

MONTH = 30 * 24 * 3600  # git-of-theseus sampling interval in seconds

# Data-like files that inflate git-of-theseus without saying anything about code age.
DATA_IGNORES = ["*.csv", "*.json", "*.lock", "*.min.js", "*.min.css", "*.svg", "*.map",
                "vendor/**", "node_modules/**", "third_party/**", "dist/**", "build/**"]

_ORG = re.compile(r"^[\w.-]+/\*$")
_OWNER_REPO = re.compile(r"^[\w.-]+/[\w.-]+$")
_URL = re.compile(r"^(https?://|git@|ssh://)")


def classify_target(target: str) -> tuple:
    if os.path.isdir(target):
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


def clone(target: str, dest_parent: str, runner=_gh) -> str:
    """Clone a remote target with gh (so private repos use the existing auth). Raises GhError."""
    dest = os.path.join(dest_parent, repo_name(target))
    _wrap(runner, ["gh", "repo", "clone", target, dest, "--", "--quiet"])
    return dest


def env_path() -> str:
    """PATH with pip's user bin dirs added."""
    parts = []
    lib = os.path.expanduser("~/Library/Python")
    if os.path.isdir(lib):
        parts += [os.path.join(lib, v, "bin") for v in sorted(os.listdir(lib), reverse=True)]
    return os.pathsep.join(parts + [os.environ.get("PATH", "")])


REQUIRED_TOOLS = ["scc", "git-sizer", "gitleaks"]
PLOT_TOOLS = ["git-of-theseus-analyze"]


def missing_tools(plots: bool = False, path: str = None) -> list:
    path = env_path() if path is None else path
    wanted = REQUIRED_TOOLS + (PLOT_TOOLS if plots else [])
    return [t for t in wanted if not any(os.access(os.path.join(d, t), os.X_OK) for d in path.split(os.pathsep) if d)]


def plan(repo_dir: str, out_dir: str, branch: str = "HEAD", age: bool = True, plots: bool = False,
         procs: int = None, interval: int = MONTH, ignore=()) -> list:
    o = lambda name: os.path.join(out_dir, name)  # noqa: E731
    log = o("log.txt")
    ignores = [x for pattern in ignore for x in ("--ignore", pattern)]
    blame_argv = [sys.executable, BLAME_SCRIPT, repo_dir, out_dir, "--procs", str(procs or blame.default_procs()), *ignores, "--aliases", o("meta.json")]
    theseus_argv = ["git-of-theseus-analyze", ".", "--branch", branch, "--outdir", o("theseus"),
                    "--procs", str(procs or os.cpu_count() or 2), "--interval", str(interval), *ignores]
    steps = [
        {"name": "scc", "argv": ["scc", "--by-file", "--format", "json"], "stdout": o("size.json"), "deps": []},
        {"name": "git-sizer", "argv": ["git-sizer", "--verbose"], "stdout": o("repo-health.txt"), "deps": []},
        {"name": "gitleaks", "argv": ["gitleaks", "git", "--no-banner", "--report-path", o("secrets.json"), "--exit-code", "0"], "stdout": None, "deps": []},
        {"name": "git-log", "argv": ["git", "log", "--all", "--use-mailmap", "--numstat", "--date=iso-strict", "--pretty=format:--%h--%ad--%aN", "--no-renames"], "stdout": log, "deps": []},
        {"name": "change analysis", "argv": [sys.executable, MAAT_SCRIPT, log, out_dir, "--aliases", o("meta.json")], "stdout": None, "deps": ["git-log"]},
    ]
    if age:
        steps.append({"name": "code age", "argv": blame_argv, "stdout": None, "deps": []})
    if plots:
        steps += [
            {"name": "git-of-theseus", "argv": theseus_argv, "stdout": None, "deps": ["code age"] if age else []},
            {"name": "theseus stack plot", "argv": ["git-of-theseus-stack-plot", o("theseus/cohorts.json"), "--outfile", o("code-age.png")], "stdout": None, "deps": ["git-of-theseus"]},
            {"name": "theseus survival plot", "argv": ["git-of-theseus-survival-plot", o("theseus/survival.json"), "--outfile", o("survival.png")], "stdout": None, "deps": ["git-of-theseus"]},
        ]
    return steps


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
    env = dict(os.environ, PATH=env_path())
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
    return subprocess.run(["git", *args], cwd=repo_dir, check=True, capture_output=True, text=True).stdout


def estimate_blames(repo_dir: str, interval: int = MONTH, ignore=(), sample: int = 25) -> dict:
    """Cost of the blame passes: a timed projection for the HEAD pass (seconds) and
    tracked files times sampled commits for git-of-theseus (blames)."""
    files = len(_git(repo_dir, "ls-files").splitlines())
    times = [int(t) for t in _git(repo_dir, "log", "--format=%ct").split()]
    span = (max(times) - min(times)) if times else 0
    samples = min(len(times), span // interval + 1) if times else 0
    projection = blame.estimate(repo_dir, ignore=ignore, sample=sample)
    return {"files": files, "samples": samples, "blames": files * samples,
            "seconds": projection["seconds"], "code_files": projection["files"]}


def collect_meta(repo_dir: str) -> dict:
    from .load import parse_authors_log

    dates = _git(repo_dir, "log", "--all", "--use-mailmap", "--format=%ad", "--date=short").split()
    return {
        "name": repo_name(repo_dir),
        "path": repo_dir,
        "branch": _git(repo_dir, "rev-parse", "--abbrev-ref", "HEAD").strip(),
        "commits": len(dates),
        "first_date": min(dates) if dates else "",
        "last_date": max(dates) if dates else "",
        "identities": identity.merge(parse_authors_log(_git(repo_dir, "log", "--all", "--use-mailmap", "--format=%aN\t%aE"))),
    }


def save_meta(meta: dict, out_dir: str) -> None:
    with open(os.path.join(out_dir, "meta.json"), "w") as fh:
        json.dump(meta, fh, indent=2)


def write_meta(repo_dir: str, out_dir: str) -> dict:
    meta = collect_meta(repo_dir)
    save_meta(meta, out_dir)
    return meta

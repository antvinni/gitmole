"""Command line entry point: gitmole <path | owner/repo | url> [--out DIR] [--no-run]."""
from __future__ import annotations

import argparse
import os
import sys
import tempfile
import threading
import time

from rich.console import Console

from . import __version__, banner, findings, load, run


def parse_args(argv):
    p = argparse.ArgumentParser(prog="gitmole", description="Analyse a git repository offline and print a report.")
    p.add_argument("target", help="local clone path, owner/repo, or git URL")
    p.add_argument("--out", help="output directory (default: analysis-<repo> next to the clone, or in cwd for remote targets)")
    p.add_argument("--no-run", action="store_true", help="skip the tools; re-render the report from an existing output directory")
    p.add_argument("--jar", default=os.path.expanduser("~/bin/code-maat.jar"), help="path to the code-maat standalone jar")
    p.add_argument("--workers", type=int, default=6, help="how many tools to run at once")
    p.add_argument("--version", action="version", version=f"gitmole {__version__}")
    return p.parse_args(argv)


def main(argv=None, console: Console = None, tool_check=run.missing_tools) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    console = console or Console()
    err = Console(stderr=True) if console.file is sys.stdout else console
    if console.is_terminal:
        console.print(banner.neon())

    if args.no_run:
        out_dir = os.path.abspath(args.target)
        if not os.path.isfile(os.path.join(out_dir, "meta.json")):
            err.print(f"[red]no gitmole output found in {out_dir}[/red] (expected meta.json)")
            return 2
        return _render(out_dir, console)

    try:
        kind, target = run.classify_target(args.target)
    except ValueError as e:
        err.print(f"[red]{e}[/red]")
        return 2

    missing = tool_check(args.jar)
    if missing:
        err.print("[red]missing tools:[/red] " + ", ".join(missing))
        err.print("run bin/install.sh from the gitmole checkout")
        return 2

    if kind == "remote":
        parent = tempfile.mkdtemp(prefix="gitmole-", dir=os.environ.get("TMPDIR"))
        console.print(f"[dim]cloning {target} into {parent}[/dim]")
        repo_dir = run.clone(target, parent)
    else:
        repo_dir = target

    out_dir = run.output_dir(kind, repo_dir, args.out)
    os.makedirs(os.path.join(out_dir, "theseus"), exist_ok=True)
    log_path = os.path.join(out_dir, "run.log")
    open(log_path, "w").close()

    meta = run.write_meta(repo_dir, out_dir)
    results = _execute(run.plan(repo_dir, out_dir, args.jar, branch=meta["branch"]), log_path, repo_dir, args.workers, console)

    failed = [n for n, rc in results.items() if rc != 0]
    if failed:
        console.print(f"[yellow]{len(failed)} step(s) did not complete:[/yellow] " + ", ".join(f"{n} ({results[n]})" for n in failed))
        console.print(f"[dim]details in {log_path}[/dim]\n")
    return _render(out_dir, console)


def _execute(steps, log_path, repo_dir, workers, console) -> dict:
    active, lock = set(), threading.Lock()
    started = time.monotonic()

    def label():
        with lock:
            names = ", ".join(sorted(active))
        return f"running {names}" if names else "finishing"

    with console.status(label()) as status:
        def on_start(name):
            with lock:
                active.add(name)
            status.update(label())

        def on_done(name, rc):
            with lock:
                active.discard(name)
            status.update(label())

        results = run.execute(steps, log_path=log_path, cwd=repo_dir, workers=workers, on_start=on_start, on_done=on_done)
    console.print(f"[dim]{len(steps)} steps in {time.monotonic() - started:.1f}s[/dim]\n")
    return results


def _render(out_dir: str, console: Console) -> int:
    from . import render

    report = load.load_report(out_dir)
    render.report(report, findings.evaluate(report), console)
    return 0


if __name__ == "__main__":
    sys.exit(main())

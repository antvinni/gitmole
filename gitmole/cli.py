"""Command line entry point: gitmole <path | owner/repo | url> [--out DIR] [--no-run]."""
from __future__ import annotations

import argparse
import os
import sys
import tempfile
import threading
import time

from rich.console import Console, Group
from rich.live import Live
from rich.spinner import Spinner
from rich.text import Text

from . import __version__, banner, findings, load, run


def parse_args(argv):
    p = argparse.ArgumentParser(prog="gitmole", description="Analyse a git repository offline and print a report.")
    p.add_argument("target", help="local clone path, owner/repo, or git URL")
    p.add_argument("--out", help="output directory (default: analysis-<repo> next to the clone, or in cwd for remote targets)")
    p.add_argument("--no-run", action="store_true", help="skip the tools; re-render the report from an existing output directory")
    p.add_argument("--workers", type=int, default=6, help="how many tools to run at once")
    p.add_argument("--plots", action="store_true", help="also run git-of-theseus for the code-age and survival plots")
    p.add_argument("--deep", action="store_true", help="run code age and plots even when the repo exceeds the blame budget")
    p.add_argument("--budget", type=int, default=50000, help="max git blames before code age or plots are skipped (default 50000)")
    p.add_argument("--timeout", type=float, default=900, help="seconds any single tool may run before being killed (default 900)")
    p.add_argument("--ignore-data", action="store_true", help="exclude data-like files (csv, json, lock, minified, vendored) from code age and plots")
    p.add_argument("--ignore", action="append", default=[], metavar="GLOB", help="extra ignore pattern for code age and plots (repeatable)")
    p.add_argument("--version", action="version", version=f"gitmole {__version__}")
    return p.parse_args(argv)


def main(argv=None, console: Console = None, tool_check=run.missing_tools, planner=run.plan, estimator=run.estimate_blames) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    console = console or Console()
    err = Console(stderr=True) if console.file is sys.stdout else console

    if args.no_run:
        if console.is_terminal:
            console.print(banner.neon())
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

    missing = tool_check()
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

    estimate = estimator(repo_dir, run.MONTH)
    age_ok = args.deep or estimate["files"] <= args.budget
    plots_ok = args.plots and (args.deep or estimate["blames"] <= args.budget)
    if not age_ok:
        console.print(f"[yellow]code age skipped:[/yellow] about {estimate['files']:,} files to blame exceeds the budget of {args.budget:,}. "
                      f"Rerun with --deep to force it, or --ignore-data to shrink it.")
    if args.plots and not plots_ok:
        console.print(f"[yellow]plots skipped:[/yellow] about {estimate['blames']:,} git blames "
                      f"({estimate['files']:,} files × {estimate['samples']} samples) exceeds the budget of {args.budget:,}. "
                      f"Rerun with --deep to force them, or --ignore-data to shrink them.")
    ignore = list(run.DATA_IGNORES if args.ignore_data else []) + list(args.ignore)

    meta = run.collect_meta(repo_dir)
    meta["age"] = {"status": "run" if age_ok else "skipped", "method": "blame", "files": estimate["files"], "budget": args.budget}
    if args.plots:
        meta["plots"] = {"status": "run" if plots_ok else "skipped", "blames": estimate["blames"], "samples": estimate["samples"], "budget": args.budget}
    steps = planner(repo_dir, out_dir, branch=meta["branch"], age=age_ok, plots=plots_ok, ignore=ignore)
    run.save_meta(meta, out_dir)
    results = _execute(steps, log_path, repo_dir, args.workers, console, timeout=args.timeout)

    if results.get("code age") == "timeout":
        meta["age"]["status"] = "timeout"
    if results.get("git-of-theseus") == "timeout":
        meta["plots"]["status"] = "timeout"
    run.save_meta(meta, out_dir)
    failed = [n for n, rc in results.items() if rc != 0]
    if failed:
        console.print(f"[yellow]{len(failed)} step(s) did not complete:[/yellow] " + ", ".join(f"{n} ({results[n]})" for n in failed))
        console.print(f"[dim]details in {log_path}[/dim]\n")
    return _render(out_dir, console)


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
            target=lambda: results.update(run.execute(steps, log_path=log_path, cwd=repo_dir, workers=workers, on_start=on_start, on_done=on_done, timeout=timeout)))
        worker.start()
        while worker.is_alive():
            live.update(view())
            worker.join(0.1)
        live.update(Group(banner.neon(), Text("")) if console.is_terminal else Text(""))
    console.print(f"[dim]{len(steps)} steps in {time.monotonic() - started:.1f}s[/dim]\n")
    return results


def _render(out_dir: str, console: Console) -> int:
    from . import render

    report = load.load_report(out_dir)
    render.report(report, findings.evaluate(report), console)
    return 0


if __name__ == "__main__":
    sys.exit(main())

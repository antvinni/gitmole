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

from . import __version__, banner, findings, load, run


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
    p.add_argument("--ignore-data", action="store_true", help="exclude data-like files (csv, json, lock, minified, vendored) from code age and plots")
    p.add_argument("--ignore", action="append", default=[], metavar="GLOB", help="extra ignore pattern for code age and plots (repeatable)")
    p.add_argument("--json", metavar="PATH", help="write the report and findings as JSON to PATH, or - for stdout")
    p.add_argument("--markdown", metavar="PATH", help="write the report as Markdown to PATH, or - for stdout")
    p.add_argument("--fail-on", choices=findings.SEVERITIES, help="exit 3 if any finding is at this severity or worse")
    p.add_argument("--version", action="version", version=f"gitmole {__version__}")
    return p.parse_args(argv)


_control = run.Control()


def interrupt(*_):
    """Ctrl-C: kill every running step's process group; the run loop then exits 130."""
    _control.cancel()


def main(argv=None, console: Console = None, tool_check=run.missing_tools, planner=run.plan, estimator=run.estimate_blames,
         lister=run.list_repos, cloner=run.clone) -> int:
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

    if args.no_run:
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

    missing = tool_check(plots=args.plots)
    if missing:
        err.print("[red]missing tools:[/red] " + ", ".join(missing))
        err.print("run bin/install.sh from the gitmole checkout")
        return 2

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
    return _render(out_dir, console, ui, args)


class Interrupted(Exception):
    pass


def _analyse(repo_dir: str, out_dir: str, args, ui: Console, planner, estimator) -> None:
    """Run the whole pipeline for one repository into out_dir."""
    os.makedirs(os.path.join(out_dir, "theseus"), exist_ok=True)
    log_path = os.path.join(out_dir, "run.log")
    open(log_path, "w").close()

    estimate = estimator(repo_dir, run.MONTH)
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

    meta = run.collect_meta(repo_dir)
    meta["age"] = {"status": "run" if age_ok else "skipped", "method": "blame", "files": estimate.get("code_files", estimate["files"]),
                   "projected_seconds": projected, "time_budget": args.time_budget}
    if args.plots:
        meta["plots"] = {"status": "run" if plots_ok else "skipped", "blames": estimate["blames"], "samples": estimate["samples"], "budget": args.budget}
    steps = planner(repo_dir, out_dir, branch=meta["branch"], age=age_ok, plots=plots_ok, ignore=ignore)
    run.save_meta(meta, out_dir)
    results = _execute(steps, log_path, repo_dir, args.workers, ui, timeout=args.timeout)
    if _control.cancelled.is_set():
        killed = [n for n, rc in results.items() if rc == "cancelled"]
        ui.print(f"[red]interrupted:[/red] killed {len(killed)} step(s)")
        raise Interrupted()

    if results.get("code age") == "timeout":
        meta["age"]["status"] = "timeout"
    if results.get("git-of-theseus") == "timeout":
        meta["plots"]["status"] = "timeout"
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
        report = load.load_report(out_dir)
        reports.append((name, report, findings.evaluate(report)))

    def export_path(p):
        return p if p == "-" or os.path.isabs(p) else os.path.join(base, p)

    if args.json:
        _write(json.dumps(render.portfolio_json(owner, reports), indent=2) + "\n", export_path(args.json), console)
    if args.markdown:
        _write(render.portfolio_markdown(owner, reports), export_path(args.markdown), console)
    if "-" not in (args.json, args.markdown):
        console.print(render.rich_table(render.portfolio_section(reports)))
        console.print(Text(f"\nPer-repository results in {base}", style="dim"))
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
    if args.json:
        _write(json.dumps(render.to_json(report, found), indent=2) + "\n", args.json, console)
    if args.markdown:
        _write(render.markdown(report, found), args.markdown, console)
    if "-" not in (args.json, args.markdown):
        render.report(report, found, console)
    if args.fail_on and any(findings.SEVERITIES.index(f["severity"]) <= findings.SEVERITIES.index(args.fail_on) for f in found):
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())

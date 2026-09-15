"""Draw the terminal report with rich."""
from __future__ import annotations

from rich import box
from rich.console import Console, Group
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

SEVERITY_STYLE = {"critical": "bold red", "warning": "yellow", "info": "cyan"}
SEVERITY_MARK = {"critical": "✖", "warning": "▲", "info": "●"}


def _table(title: str, *columns, rows=(), empty: str = None, **kw):
    if not rows and empty:
        return Group(Text(title, style="table.title"), Text(empty, style="dim"), Text(""))
    t = Table(title=title, title_justify="left", box=box.SIMPLE_HEAD, show_edge=False, pad_edge=False, **kw)
    for col in columns:
        name, opts = (col, {}) if isinstance(col, str) else col
        t.add_column(name, **opts)
    for row in rows:
        t.add_row(*[str(c) for c in row])
    return t


def _pct(part, whole) -> str:
    return f"{100 * part / whole:.0f}%" if whole else "-"


def header(report: dict) -> Panel:
    m = report["meta"]
    langs = ", ".join(l["name"] for l in report["size"]["languages"][:4]) or "unknown"
    ids = m.get("identities") or []
    body = Text()
    body.append(f"{m.get('commits', 0)} commits", style="bold")
    body.append(f"  ·  {m.get('first_date', '?')} → {m.get('last_date', '?')}")
    body.append(f"  ·  {len(ids)} {'identity' if len(ids) == 1 else 'identities'}  ·  branch {m.get('branch', '?')}\n")
    body.append(f"{report['size']['total_code']:,} lines in {report['size']['total_files']} files  ·  {langs}")
    return Panel(body, title=f"[bold]{m.get('name', 'repo')}[/bold]", title_align="left", border_style="blue")


def findings_panel(findings: list) -> Panel:
    if not findings:
        return Panel(Text("Nothing flagged.", style="green"), title="Findings", title_align="left", border_style="green")
    grid = Table.grid(padding=(0, 1))
    grid.add_column(no_wrap=True)
    grid.add_column(overflow="fold")
    for f in findings:
        style = SEVERITY_STYLE[f["severity"]]
        body = Text(f["title"], style=style)
        body.append(f"\n{f['detail']}", style="dim")
        grid.add_row(Text(SEVERITY_MARK[f["severity"]], style=style), body)
    worst = findings[0]["severity"]
    return Panel(grid, title=f"Findings ({len(findings)})", title_align="left", border_style=SEVERITY_STYLE[worst])


def size_table(report: dict) -> Table:
    langs = report["size"]["languages"][:8]
    total = report["size"]["total_code"]
    return _table("Size by language", "language", ("files", {"justify": "right"}), ("code", {"justify": "right"}), ("share", {"justify": "right"}), ("complexity", {"justify": "right"}),
                  rows=[(l["name"], l["files"], f"{l['code']:,}", _pct(l["code"], total), l["complexity"]) for l in langs])


def people_table(report: dict) -> Table:
    ids = report["meta"].get("identities") or []
    total_commits = sum(i["commits"] for i in ids)
    surviving = report.get("theseus_authors") or {}
    total_lines = sum(surviving.values())
    rows = [(i["name"], i["email"], i["commits"], _pct(i["commits"], total_commits), _pct(surviving.get(i["name"], 0), total_lines)) for i in ids[:8]]
    return _table("People", "author", ("email", {"style": "dim", "overflow": "fold"}), ("commits", {"justify": "right"}), ("share", {"justify": "right"}), ("surviving code", {"justify": "right"}), rows=rows)


def hotspots_table(report: dict) -> Table:
    authors = {a["entity"]: a["n-authors"] for a in report.get("authors") or []}
    ages = {a["entity"]: a["age-months"] for a in report.get("age") or []}
    rows = sorted(report.get("revisions") or [], key=lambda r: -r["n-revs"])[:10]
    return _table("Hotspots (most revised files)", ("file", {"overflow": "fold"}), ("revisions", {"justify": "right"}), ("authors", {"justify": "right"}), ("months idle", {"justify": "right"}),
                  rows=[(r["entity"], r["n-revs"], authors.get(r["entity"], "-"), ages.get(r["entity"], "-")) for r in rows])


def coupling_table(report: dict) -> Table:
    rows = sorted((p for p in report.get("coupling") or [] if p["average-revs"] >= 5), key=lambda p: (-p["degree"], -p["average-revs"]))[:10]
    return _table("Change coupling", ("file", {"overflow": "fold"}), ("changes with", {"overflow": "fold"}), ("degree", {"justify": "right"}), ("avg revs", {"justify": "right"}),
                  rows=[(p["entity"], p["coupled"], f"{p['degree']}%", p["average-revs"]) for p in rows], empty="no pairs with 5+ shared revisions")


def _bar(part, whole, width=30) -> str:
    return "█" * int(width * part / whole) if whole else ""


def age_fallback_table(report: dict):
    """When git-of-theseus did not run, show files by the year they were last changed (from code-maat)."""
    status = (report["meta"].get("theseus") or {}).get("status", "skipped")
    reason = {"timeout": "git-of-theseus timed out", "skipped": "git-of-theseus skipped"}.get(status, f"git-of-theseus {status}")
    last = report["meta"].get("last_date") or ""
    try:
        end_year, end_month = int(last[:4]), int(last[5:7])
    except ValueError:
        return _table("Paths in history by year last changed", "year", rows=(), empty=f"no age data ({reason})")
    counts = {}
    for row in report.get("age") or []:
        months_back = end_month - 1 - int(row["age-months"])
        year = end_year + months_back // 12
        counts[year] = counts.get(year, 0) + 1
    total = sum(counts.values())
    rows = [(str(y), n, _pct(n, total), _bar(n, total)) for y, n in sorted(counts.items(), reverse=True)]
    return _table("Paths in history by year last changed", "year", ("paths", {"justify": "right"}), ("share", {"justify": "right"}), ("", {"style": "blue"}),
                  rows=rows, empty=f"no age data ({reason})", caption=reason, caption_justify="left", caption_style="dim")


def age_table(report: dict):
    cohorts = report.get("cohorts") or {}
    if not cohorts and report["meta"].get("theseus", {}).get("status", "run") != "run":
        return age_fallback_table(report)
    total = sum(cohorts.values())
    rows = []
    for label, lines in cohorts.items():
        rows.append((label.replace("Code added in ", ""), f"{lines:,}", _pct(lines, total), _bar(lines, total)))
    return _table("Surviving code by year written", "year", ("lines", {"justify": "right"}), ("share", {"justify": "right"}), ("", {"style": "blue"}), rows=rows)


def health_table(report: dict) -> Table:
    rows = [(r["name"], r["value"], "*" * r["concern"], r["ref"]) for r in report.get("sizer") or []]
    return _table("Repo health (git-sizer concerns)", "metric", ("value", {"justify": "right"}), "concern", ("object", {"overflow": "fold"}), rows=rows, empty="nothing flagged")


def report(report: dict, findings: list, console: Console) -> None:
    console.print(header(report))
    console.print(findings_panel(findings))
    console.print(size_table(report))
    console.print(people_table(report))
    console.print(hotspots_table(report))
    console.print(coupling_table(report))
    console.print(age_table(report))
    console.print(health_table(report))
    secrets = report.get("secrets") or []
    console.print(Text(f"Secrets: {len(secrets)} found" if secrets else "Secrets: none found", style="red" if secrets else "green"))
    console.print(Text(f"\nFull results and plots in {report['out_dir']}", style="dim"))

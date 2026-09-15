"""Turn a loaded report into sections, then draw them with rich or as Markdown/JSON."""
from __future__ import annotations

from rich import box
from rich.console import Console, Group
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

SEVERITY_STYLE = {"critical": "bold red", "warning": "yellow", "info": "cyan"}
SEVERITY_MARK = {"critical": "✖", "warning": "▲", "info": "●"}
RIGHT = {"justify": "right"}
FOLD = {"overflow": "fold"}


def _pct(part, whole) -> str:
    return f"{100 * part / whole:.0f}%" if whole else "-"


def _bar(part, whole, width=30) -> str:
    return "█" * int(width * part / whole) if whole else ""


def _section(title, columns, rows, note=None, caption=None) -> dict:
    """columns: list of (name, rich column options). rows: lists of already-formatted cells."""
    return {"title": title, "columns": [c[0] for c in columns], "col_opts": [c[1] for c in columns],
            "rows": [[str(c) for c in r] for r in rows], "note": note, "caption": caption}


# --- data ------------------------------------------------------------------

def summary(report: dict) -> dict:
    m = report["meta"]
    ids = m.get("identities") or []
    return {
        "name": m.get("name", "repo"), "commits": m.get("commits", 0),
        "first_date": m.get("first_date", "?"), "last_date": m.get("last_date", "?"),
        "identities": len(ids), "branch": m.get("branch", "?"),
        "lines": report["size"]["total_code"], "files": report["size"]["total_files"],
        "languages": [l["name"] for l in report["size"]["languages"][:4]],
    }


def size_section(report: dict) -> dict:
    langs = report["size"]["languages"][:8]
    total = report["size"]["total_code"]
    return _section("Size by language", [("language", {}), ("files", RIGHT), ("code", RIGHT), ("share", RIGHT), ("complexity", RIGHT)],
                    [(l["name"], l["files"], f"{l['code']:,}", _pct(l["code"], total), l["complexity"]) for l in langs])


def people_section(report: dict) -> dict:
    ids = report["meta"].get("identities") or []
    total_commits = sum(i["commits"] for i in ids)
    surviving = report.get("theseus_authors") or {}
    total_lines = sum(surviving.values())
    rows = [(i["name"], i["email"], i["commits"], _pct(i["commits"], total_commits), _pct(surviving.get(i["name"], 0), total_lines)) for i in ids[:8]]
    return _section("People", [("author", {}), ("email", {"style": "dim", "overflow": "fold"}), ("commits", RIGHT), ("share", RIGHT), ("surviving code", RIGHT)], rows)


WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def activity_section(report: dict) -> dict:
    act = report.get("activity") or {}
    columns = [("weekday", {}), ("commits", RIGHT), ("share", RIGHT), ("", {"style": "blue"})]
    if not act.get("by_weekday"):
        return _section("Activity", columns, [], note="no activity data")
    total = sum(act["by_weekday"])
    rows = [(WEEKDAYS[i], n, _pct(n, total), _bar(n, total, 20)) for i, n in enumerate(act["by_weekday"])]
    hours = act.get("by_hour") or []
    caption = None
    if hours and max(hours):
        h = max(range(24), key=lambda i: hours[i])
        caption = f"busiest hour {h:02d}:00 ({hours[h]} commits)"
    return _section("Activity", columns, rows, caption=caption)


MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def _month_range(last: str, n: int = 12) -> list:
    """The n months ending at 'YYYY-MM', oldest first."""
    y, m = int(last[:4]), int(last[5:7])
    out = []
    for _ in range(n):
        out.append(f"{y:04d}-{m:02d}")
        m -= 1
        if m == 0:
            y, m = y - 1, 12
    return out[::-1]


def _month_label(ym: str) -> str:
    return f"{MONTHS[int(ym[5:7]) - 1]} {ym[:4]}"


def timeline_section(report: dict, months: int = 12, authors: int = 8) -> dict:
    tl = (report.get("activity") or {}).get("timeline") or {}
    if not tl:
        return _section("Timeline", [("author", {})], [], note="no timeline data")
    last = max(m for per in tl.values() for m in per)
    span = _month_range(last, months)
    columns = [("author", {"overflow": "fold"})] + [(MONTHS[int(m[5:7]) - 1], RIGHT) for m in span]
    in_window = {a: sum(per.get(m, 0) for m in span) for a, per in tl.items()}
    ranked = [a for a in sorted(in_window, key=lambda a: -in_window[a]) if in_window[a] > 0][:authors]
    rows = [(a, *[tl[a].get(m) or "·" for m in span]) for a in ranked]
    return _section(f"Timeline ({_month_label(span[0])} → {_month_label(span[-1])})", columns, rows)


def hotspots_section(report: dict) -> dict:
    """Change frequency times size, Tornhill-style. Files no longer in the tree sort last."""
    authors = {a["entity"]: a["n-authors"] for a in report.get("authors") or []}
    ages = {a["entity"]: a["age-months"] for a in report.get("age") or []}
    files = report["size"].get("files") or {}
    scored = []
    for r in report.get("revisions") or []:
        info = files.get(r["entity"])
        scored.append((r["n-revs"] * info["code"] if info else -1, r, info))
    scored.sort(key=lambda t: (-t[0], -t[1]["n-revs"], t[1]["entity"]))
    rows = [(r["entity"], r["n-revs"], f"{info['code']:,}" if info else "-", info["complexity"] if info else "-",
             f"{score:,}" if info else "-", authors.get(r["entity"], "-"), ages.get(r["entity"], "-"))
            for score, r, info in scored[:10]]
    return _section("Hotspots (score = revisions × lines of code)",
                    [("file", {"overflow": "fold", "ratio": 3}), ("revs", RIGHT), ("lines", RIGHT), ("cplx", RIGHT), ("score", RIGHT), ("authors", RIGHT), ("idle", RIGHT)], rows)


def coupling_section(report: dict) -> dict:
    pairs = sorted((p for p in report.get("coupling") or [] if p["average-revs"] >= 5), key=lambda p: (-p["degree"], -p["average-revs"]))[:10]
    return _section("Change coupling", [("file", FOLD), ("changes with", FOLD), ("degree", RIGHT), ("avg revs", RIGHT)],
                    [(p["entity"], p["coupled"], f"{p['degree']}%", p["average-revs"]) for p in pairs],
                    note=None if pairs else "no pairs with 5+ shared revisions")


def age_section(report: dict) -> dict:
    cohorts = report.get("cohorts") or {}
    if not cohorts and report["meta"].get("age", {}).get("status", "run") != "run":
        return age_fallback_section(report)
    total = sum(cohorts.values())
    rows = [(label.replace("Code added in ", ""), f"{lines:,}", _pct(lines, total), _bar(lines, total)) for label, lines in cohorts.items()]
    return _section("Surviving code by year written", [("year", {}), ("lines", RIGHT), ("share", RIGHT), ("", {"style": "blue"})], rows,
                    note=None if rows else "no age data")


def age_fallback_section(report: dict) -> dict:
    """When the blame pass did not run: net lines added per year from the log, or failing that,
    paths by the year they were last changed."""
    status = (report["meta"].get("age") or {}).get("status", "skipped")
    reason = {"timeout": "code age timed out", "skipped": "code age skipped"}.get(status, f"code age {status}")
    net = (report.get("activity") or {}).get("net_by_year") or {}
    if net:
        total = sum(v for v in net.values() if v > 0)
        rows = [(y, f"{v:,}", _pct(v, total) if v > 0 else "-", _bar(v, total) if v > 0 else "") for y, v in net.items()]
        return _section("Net lines added by year", [("year", {}), ("net lines", RIGHT), ("share", RIGHT), ("", {"style": "blue"})], rows,
                        caption=f"{reason}; approximation from the log, not a blame")
    last = report["meta"].get("last_date") or ""
    columns = [("year", {}), ("paths", RIGHT), ("share", RIGHT), ("", {"style": "blue"})]
    try:
        end_year, end_month = int(last[:4]), int(last[5:7])
    except ValueError:
        return _section("Paths in history by year last changed", columns, [], note=f"no age data ({reason})")
    counts = {}
    for row in report.get("age") or []:
        months_back = end_month - 1 - int(row["age-months"])
        year = end_year + months_back // 12
        counts[year] = counts.get(year, 0) + 1
    total = sum(counts.values())
    rows = [(str(y), n, _pct(n, total), _bar(n, total)) for y, n in sorted(counts.items(), reverse=True)]
    return _section("Paths in history by year last changed", columns, rows, note=None if rows else f"no age data ({reason})", caption=reason)


def health_section(report: dict) -> dict:
    rows = [(r["name"], r["value"], "*" * r["concern"], r["ref"]) for r in report.get("sizer") or []]
    return _section("Repo health (git-sizer concerns)", [("metric", {}), ("value", RIGHT), ("concern", {}), ("object", FOLD)], rows,
                    note=None if rows else "nothing flagged")


def sections(report: dict) -> list:
    return [size_section(report), people_section(report), activity_section(report), timeline_section(report), hotspots_section(report), coupling_section(report), age_section(report), health_section(report)]


def secrets_line(report: dict) -> str:
    n = len(report.get("secrets") or [])
    return f"Secrets: {n} found" if n else "Secrets: none found"


# --- rich ------------------------------------------------------------------

def header(report: dict) -> Panel:
    s = summary(report)
    body = Text()
    body.append(f"{s['commits']} commits", style="bold")
    body.append(f"  ·  {s['first_date']} → {s['last_date']}")
    body.append(f"  ·  {s['identities']} {'identity' if s['identities'] == 1 else 'identities'}  ·  branch {s['branch']}\n")
    body.append(f"{s['lines']:,} lines in {s['files']} files  ·  {', '.join(s['languages']) or 'unknown'}")
    return Panel(body, title=f"[bold]{s['name']}[/bold]", title_align="left", border_style="blue")


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
    return Panel(grid, title=f"Findings ({len(findings)})", title_align="left", border_style=SEVERITY_STYLE[findings[0]["severity"]])


def rich_table(sec: dict):
    if not sec["rows"] and sec["note"]:
        return Group(Text(sec["title"], style="table.title"), Text(sec["note"], style="dim"), Text(""))
    kw = {}
    if sec.get("caption"):
        kw = {"caption": sec["caption"], "caption_justify": "left", "caption_style": "dim"}
    t = Table(title=sec["title"], title_justify="left", box=box.SIMPLE_HEAD, show_edge=False, pad_edge=False, **kw)
    for name, opts in zip(sec["columns"], sec["col_opts"]):
        t.add_column(name, **opts)
    for row in sec["rows"]:
        t.add_row(*row)
    return t


def report(report: dict, findings: list, console: Console) -> None:
    console.print(header(report))
    console.print(findings_panel(findings))
    for sec in sections(report):
        console.print(rich_table(sec))
    console.print(Text(secrets_line(report), style="red" if report.get("secrets") else "green"))
    console.print(Text(f"\nFull results and plots in {report['out_dir']}", style="dim"))


# --- markdown / json -------------------------------------------------------

def _md_cell(cell: str) -> str:
    return cell.replace("|", "\\|").replace("\n", " ")


def markdown(report: dict, findings: list) -> str:
    s = summary(report)
    out = [f"# {s['name']}", "",
           f"{s['commits']} commits · {s['first_date']} → {s['last_date']} · {s['identities']} {'identity' if s['identities'] == 1 else 'identities'} · branch {s['branch']}  ",
           f"{s['lines']:,} lines in {s['files']} files · {', '.join(s['languages']) or 'unknown'}", "",
           "## Findings", ""]
    if findings:
        out += [f"- **{f['severity']}** {f['title']} — {f['detail']}" for f in findings]
    else:
        out.append("Nothing flagged.")
    for sec in sections(report):
        out += ["", f"## {sec['title']}", ""]
        if not sec["rows"]:
            out.append(f"_{sec['note'] or 'nothing'}_")
            continue
        out.append("| " + " | ".join(sec["columns"]) + " |")
        out.append("| " + " | ".join("---:" if o.get("justify") == "right" else "---" for o in sec["col_opts"]) + " |")
        out += ["| " + " | ".join(_md_cell(c) for c in row) + " |" for row in sec["rows"]]
        if sec.get("caption"):
            out += ["", f"_{sec['caption']}_"]
    out += ["", secrets_line(report), "", f"Full results and plots in {report['out_dir']}", ""]
    return "\n".join(out)


def to_json(report: dict, findings: list) -> dict:
    return {**{k: v for k, v in report.items()}, "findings": findings}


# --- portfolio -------------------------------------------------------------

def portfolio_section(reports: list) -> dict:
    """reports: [(name, report, findings)] -> one row per repository."""
    rows = []
    for name, rep, found in reports:
        s = summary(rep)
        surviving = rep.get("theseus_authors") or {}
        total = sum(surviving.values())
        bus = _pct(max(surviving.values()), total) if surviving else "-"
        worst = f"{found[0]['severity']}: {found[0]['title']}" if found else "-"
        rows.append((name, s["commits"], s["identities"], bus, len(rep.get("secrets") or []), f"{s['lines']:,}", worst))
    return _section(f"Portfolio ({len(reports)} repositories)",
                    [("repo", {"overflow": "fold"}), ("commits", RIGHT), ("people", RIGHT), ("top author", RIGHT),
                     ("secrets", RIGHT), ("lines", RIGHT), ("worst finding", {"overflow": "fold", "ratio": 2})], rows,
                    note=None if rows else "no repositories")


def portfolio_markdown(owner: str, reports: list) -> str:
    sec = portfolio_section(reports)
    out = [f"# {owner}", "", f"{len(reports)} repositories analysed with gitmole.", "", f"## {sec['title']}", ""]
    if sec["rows"]:
        out.append("| " + " | ".join(sec["columns"]) + " |")
        out.append("| " + " | ".join("---:" if o.get("justify") == "right" else "---" for o in sec["col_opts"]) + " |")
        out += ["| " + " | ".join(_md_cell(c) for c in row) + " |" for row in sec["rows"]]
    else:
        out.append(f"_{sec['note']}_")
    for name, rep, found in reports:
        out += ["", f"## {name}", ""]
        out += [f"- **{f['severity']}** {f['title']} — {f['detail']}" for f in found] or ["Nothing flagged."]
    return "\n".join(out) + "\n"


def portfolio_json(owner: str, reports: list) -> dict:
    return {"owner": owner, "repos": [{"name": n, "summary": summary(r), "findings": f, "out_dir": r["out_dir"]} for n, r, f in reports]}

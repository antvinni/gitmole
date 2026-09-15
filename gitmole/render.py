"""Turn a loaded report into sections, then draw them with rich or as Markdown/JSON.

The default report is the tighter one: the columns you actually read, capped rows, elided
paths. `full` restores every column and row (Markdown export is always full)."""
from __future__ import annotations

from rich import box
from rich.columns import Columns
from rich.console import Console, Group
from rich.padding import Padding
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from . import knowledge, textfmt

SEVERITY_STYLE = {"critical": "bold red", "warning": "yellow", "info": "cyan"}

# section styling: the banner's palette carried into the tables
ACCENT = "#5ad0ff"          # section titles
HEADER = "bold #c86cff"     # column headers
BAR = "#5ad0ff"             # inline share bars
HOT = "bold #ff5cc8"        # values past a threshold
WARM = "#ff9ee0"            # values worth a glance
ROW_STYLES = ["", "on #1c2230"]
SIDE_BY_SIDE_MIN_WIDTH = 100

SYMBOLS = {"Size by language": "▤", "People": "◉", "Activity": "◔", "Timeline": "▦", "Hotspots": "◆", "Change coupling": "⟷",
           "Surviving code by year written": "◷", "Net lines added by year": "◷", "Paths in history by year last changed": "◷",
           "Knowledge map": "⌂", "Repo health": "✚", "Portfolio": "▣", "File types": "▥"}
# the one column to read first in each table; the rest are dimmed
KEY_METRIC = {"Size by language": "code", "People": "commits", "Hotspots": "revs", "Change coupling": "degree",
              "Knowledge map": "lines added", "Surviving code by year written": "lines", "Net lines added by year": "net lines",
              "Paths in history by year last changed": "paths", "Activity": "commits", "Portfolio": "commits"}
SEVERITY_MARK = {"critical": "✖", "warning": "▲", "info": "●"}
RIGHT = {"justify": "right"}
FOLD = {"overflow": "fold"}
PATH = {"overflow": "fold", "no_wrap": False}

# rows shown by default; `full` lifts the caps. Markdown gets a looser cap of its own.
CAPS = {"People": 6, "Hotspots": 8, "Change coupling": 5, "Knowledge map": 6, "Size by language": 8, "Timeline": 8}
MARKDOWN_CAP = 50


def _pct(part, whole) -> str:
    return f"{100 * part / whole:.0f}%" if whole else "-"


def _bar(part, whole, width=30) -> str:
    return "█" * int(width * part / whole) if whole else ""


def _section(title, columns, rows, note=None, caption=None) -> dict:
    """columns: list of (name, rich column options). rows: lists of already-formatted cells."""
    return {"title": title, "columns": [c[0] for c in columns], "col_opts": [c[1] for c in columns],
            "rows": [[str(c) for c in r] for r in rows], "note": note, "caption": caption}


def _limit(title: str, full, cap=None):
    """How many rows to keep: None for all. `full` may be False (terminal default), True, or 'markdown'."""
    if full is True:
        return None
    if full == "markdown":
        return MARKDOWN_CAP
    return cap if cap is not None else CAPS.get(title)


def _more(total: int, limit) -> str:
    return f"and {total - limit} more" if limit is not None and total > limit else None


def _keep(columns: list, rows: list, names) -> tuple:
    """Keep only the columns called `names`, in the given order, for both header and rows."""
    index = {c[0]: i for i, c in enumerate(columns)}
    picked = [index[n] for n in names]
    return [columns[i] for i in picked], [tuple(r[i] for i in picked) for r in rows]


def _path_room(width, rows: list, columns: list, path_columns: int = 1) -> int:
    """Characters available to each path column once the other cells and rich's padding are counted."""
    if width is None:
        return None
    other = [i for i, c in enumerate(columns) if i >= path_columns]
    widest = sum(max([len(str(r[i])) for r in rows] + [len(columns[i][0])]) for i in other)
    padding = 3 * (len(columns) - 1)
    return max(16, (width - widest - padding) // path_columns)


def _shorten(rows: list, width, columns: list, path_columns: int = 1) -> list:
    room = _path_room(width, rows, columns, path_columns)
    if room is None:
        return rows
    return [tuple(textfmt.shorten_path(str(c), room) if i < path_columns else c for i, c in enumerate(r)) for r in rows]


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
        "since": m.get("since"),
    }


def size_section(report: dict, full: bool = True, width=None) -> dict:
    langs = report["size"]["languages"]
    total = report["size"]["total_code"]
    limit = _limit("Size by language", full)
    rows = [(l["name"], l["files"], f"{l['code']:,}", _pct(l["code"], total), l["complexity"]) for l in langs[:limit]]
    columns = [("language", {}), ("files", RIGHT), ("code", RIGHT), ("share", RIGHT), ("complexity", RIGHT)]
    if full is not True:
        columns, rows = _keep(columns, rows, ["language", "files", "code", "share"])
    return _section("Size by language", columns, rows, caption=_more(len(langs), limit))


def people_section(report: dict, full: bool = True, width=None) -> dict:
    ids = report["meta"].get("identities") or []
    total_commits = sum(i["commits"] for i in ids)
    surviving = report.get("theseus_authors") or {}
    total_lines = sum(surviving.values())
    limit = _limit("People", full)
    rows = [(i["name"], i["email"], i["commits"], _pct(i["commits"], total_commits), _pct(surviving.get(i["name"], 0), total_lines)) for i in ids[:limit]]
    columns = [("author", {}), ("email", {"style": "dim", "overflow": "fold"}), ("commits", RIGHT), ("share", RIGHT), ("surviving code", RIGHT)]
    if full is not True:
        columns, rows = _keep(columns, rows, ["author", "commits", "share", "surviving code"])
    since = report["meta"].get("since")
    notes = [f"commits since {since}; surviving code is for the whole tree"] if since else []
    more = _more(len(ids), limit)
    if more:
        notes.append(more)
    return _section("People", columns, rows, caption="\n".join(notes) or None)


WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def activity_section(report: dict, full: bool = True, width=None) -> dict:
    act = report.get("activity") or {}
    columns = [("weekday", {}), ("commits", RIGHT), ("share", RIGHT), ("", {"style": "blue"})]
    if not act.get("by_weekday"):
        return _section("Activity", columns, [], note="no activity data")
    total = sum(act["by_weekday"])
    rows = [(WEEKDAYS[i], n, _pct(n, total), _bar(n, total, 20)) for i, n in enumerate(act["by_weekday"])]
    hours = act.get("by_hour") or []
    notes = []
    if hours and max(hours):
        h = max(range(24), key=lambda i: hours[i])
        notes.append(f"busiest hour {h:02d}:00 ({hours[h]} commits)")
    if act.get("fix_commits") is not None and total:
        notes.append(f"{_pct(act['fix_commits'], total)} of commits are fixes")
    return _section("Activity", columns, rows, caption="\n".join(notes) or None)


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


def timeline_section(report: dict, full: bool = True, width=None, months: int = 12) -> dict:
    tl = (report.get("activity") or {}).get("timeline") or {}
    if not tl:
        return _section("Timeline", [("author", {})], [], note="no timeline data")
    last = max(m for per in tl.values() for m in per)
    span = _month_range(last, months)
    since = report["meta"].get("since")
    if since:
        span = [m for m in span if m >= since[:7]] or span[-1:]
    columns = [("author", {"overflow": "fold"})] + [(MONTHS[int(m[5:7]) - 1], RIGHT) for m in span]
    in_window = {a: sum(per.get(m, 0) for m in span) for a, per in tl.items()}
    ranked = [a for a in sorted(in_window, key=lambda a: -in_window[a]) if in_window[a] > 0]
    limit = _limit("Timeline", full)
    rows = [(a, *[tl[a].get(m) or "·" for m in span]) for a in ranked[:limit]]
    return _section(f"Timeline ({_month_label(span[0])} → {_month_label(span[-1])})", columns, rows, caption=_more(len(ranked), limit))


def hotspots_section(report: dict, full: bool = True, width=None) -> dict:
    """Change frequency times size, Tornhill-style. Files no longer in the tree sort last."""
    authors = {a["entity"]: a["n-authors"] for a in report.get("authors") or []}
    ages = {a["entity"]: a["age-months"] for a in report.get("age") or []}
    fixes = {f["entity"]: f["n-fixes"] for f in report.get("fixes") or []}
    files = report["size"].get("files") or {}
    scored = []
    for r in report.get("revisions") or []:
        info = files.get(r["entity"])
        scored.append((r["n-revs"] * info["code"] if info else -1, r, info))
    scored.sort(key=lambda t: (-t[0], -t[1]["n-revs"], t[1]["entity"]))
    title = "Hotspots (score = revisions × lines of code)" if full is True else "Hotspots"
    limit = _limit("Hotspots", full)
    rows = []
    for score, r, info in scored[:limit]:
        rows.append((r["entity"], r["n-revs"], f"{info['code']:,}" if info else "-", info["complexity"] if info else "-",
                     f"{score:,}" if info else "-", fixes.get(r["entity"], 0), authors.get(r["entity"], "-"), ages.get(r["entity"], "-")))
    columns = [("file", PATH), ("revs", RIGHT), ("lines", RIGHT), ("cplx", RIGHT), ("score", RIGHT), ("fixes", RIGHT), ("authors", RIGHT), ("idle", RIGHT)]
    if full is not True:
        columns, rows = _keep(columns, rows, ["file", "revs", "lines", "fixes", "authors"])
        rows = _shorten(rows, width, columns)
    return _section(title, columns, rows, caption=_more(len(scored), limit))


def coupling_section(report: dict, full: bool = True, width=None) -> dict:
    pairs = sorted((p for p in report.get("coupling") or [] if p["average-revs"] >= 5), key=lambda p: (-p["degree"], -p["average-revs"]))
    limit = _limit("Change coupling", full)
    rows = [(p["entity"], p["coupled"], f"{p['degree']}%", p["average-revs"]) for p in pairs[:limit]]
    columns = [("file", PATH), ("changes with", PATH), ("degree", RIGHT), ("avg revs", RIGHT)]
    if full is not True:
        columns, rows = _keep(columns, rows, ["file", "changes with", "degree"])
        rows = _shorten(rows, width, columns, path_columns=2)
    return _section("Change coupling", columns, rows, note=None if rows else "no pairs with 5+ shared revisions", caption=_more(len(pairs), limit))


def age_section(report: dict, full: bool = True, width=None) -> dict:
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


def knowledge_section(report: dict, full: bool = True, width=None) -> dict:
    """Ownership by area of the tree: who wrote most of each directory."""
    areas = knowledge.areas(report.get("ownership") or [])
    limit = _limit("Knowledge map", full)
    rows = []
    for a in areas[:limit]:
        owners = [f"{name} ({_pct(n, a['lines'])})" for name, n in a["owners"][:2]] + ["-"]
        rows.append((a["area"], f"{a['lines']:,}", a["authors"], owners[0], owners[1]))
    columns = [("area", PATH), ("lines added", RIGHT), ("authors", RIGHT), ("main owner", {}), ("second", {})]
    if full is not True:
        columns, rows = _keep(columns, rows, ["area", "lines added", "main owner", "second"])
    return _section("Knowledge map", columns, rows, note=None if rows else "no ownership data", caption=_more(len(areas), limit))


def health_section(report: dict, full: bool = True, width=None) -> dict:
    rows = [(r["name"], r["value"], "*" * r["concern"], r["ref"]) for r in report.get("sizer") or []]
    return _section("Repo health (git-sizer concerns)", [("metric", {}), ("value", RIGHT), ("concern", {}), ("object", FOLD)], rows,
                    note=None if rows else "nothing flagged")


BUILDERS = [size_section, people_section, activity_section, timeline_section, hotspots_section,
            coupling_section, age_section, knowledge_section, health_section]


def sections(report: dict, full: bool = True, width=None) -> list:
    return [b(report, full, width) for b in BUILDERS]


def secrets_line(report: dict) -> str:
    n = len(report.get("secrets") or [])
    return f"Secrets: {n} found" if n else "Secrets: none found"


# --- rich ------------------------------------------------------------------

def header(report: dict, findings: list = ()) -> Panel:
    s = summary(report)
    body = Text()
    body.append(f"{s['commits']} commits", style="bold")
    body.append(f"  ·  {s['first_date']} → {s['last_date']}")
    if s["since"]:
        body.append(f"  ·  since {s['since']}", style="yellow")
    body.append(f"  ·  {s['identities']} {'identity' if s['identities'] == 1 else 'identities'}  ·  branch {s['branch']}\n")
    body.append(f"{s['lines']:,} lines in {s['files']} files  ·  {', '.join(s['languages']) or 'unknown'}\n")
    tally = textfmt.tally(list(findings))
    worst = next((f["severity"] for f in findings), None)
    body.append(tally, style=SEVERITY_STYLE.get(worst, "green"))
    return Panel(body, title=f"[bold]{s['name']}[/bold]", title_align="left", border_style="blue")


def findings_panel(findings: list) -> Panel:
    if not findings:
        return Panel(Text("Nothing flagged.", style="green"), title="Findings", title_align="left", border_style="green")
    grid = Table.grid(padding=(0, 1))
    grid.add_column(no_wrap=True)
    grid.add_column(overflow="fold")
    for g in textfmt.group_findings(findings):
        style = SEVERITY_STYLE[g["severity"]]
        body = Text(g["title"], style=style)
        for item in g["items"]:
            body.append(f"\n{item}", style="dim" if len(g["items"]) == 1 else "")
        if g["advice"]:
            body.append(f"\n↳ {g['advice']}", style="dim italic")
        grid.add_row(Text(SEVERITY_MARK[g["severity"]], style=style), body)
    return Panel(grid, title=f"Findings ({len(findings)})", title_align="left", border_style=SEVERITY_STYLE[findings[0]["severity"]])


def cell_style(column: str, value: str):
    """A style for values that crossed a threshold, or None."""
    try:
        if column == "share":
            n = int(value.rstrip("%"))
            return HOT if n >= 50 else (WARM if n >= 20 else None)
        if column == "degree" and int(value.rstrip("%")) >= 90:
            return HOT
        if column == "fixes" and int(value) >= 5:
            return HOT
    except ValueError:
        pass
    return None


def _base_title(title: str) -> str:
    return title.split(" (")[0]


def _cell(column: str, value: str, bars: bool) -> Text:
    style = cell_style(column, value) or ""
    if bars and column == "share" and value.endswith("%"):
        n = int(value[:-1])
        return Text(f"{value:>4} ", style=style) + Text("▰" * max(1, n // 10) if n else "", style=BAR)
    return Text(value, style=style)


def rich_table(sec: dict):
    """A table for a section: no title (the caller prints the heading), caption underneath,
    coloured headers, bold key column, dimmed secondary columns, zebra rows, threshold colours."""
    key = KEY_METRIC.get(_base_title(sec["title"]))
    kw = {}
    if sec.get("caption"):
        kw = {"caption": sec["caption"], "caption_justify": "left", "caption_style": "dim italic"}
    fits = max((len(line) for line in (sec.get("caption") or "").split("\n")), default=0)
    bars = "share" in sec["columns"] and "" not in sec["columns"]   # inline bars only where there is no bar column
    t = Table(box=box.SIMPLE_HEAD, show_edge=False, pad_edge=False, min_width=fits, header_style=HEADER,
              row_styles=ROW_STYLES, border_style="#3a4150", **kw)
    for i, (name, opts) in enumerate(zip(sec["columns"], sec["col_opts"])):
        o = dict(opts)
        o.setdefault("style", "bold" if i == 0 else ("" if name in (key, "share", "") else "dim"))
        if bars and name == "share":
            o["justify"] = "left"   # the percentage is padded to four characters, so the bars line up
        t.add_column(name, **o)
    for row in sec["rows"]:
        t.add_row(*[_cell(col, cell, bars) for col, cell in zip(sec["columns"], row)])
    return t


def heading(sec: dict) -> Text:
    symbol = SYMBOLS.get(_base_title(sec["title"]), "•")
    return Text(f"{symbol} ", style=ACCENT) + Text(sec["title"], style=f"bold {ACCENT}")


def section_block(sec: dict):
    """Heading plus table, or heading plus a dim note for an empty section."""
    if not sec["rows"] and sec["note"]:
        return heading(sec) + Text(f": {sec['note']}", style="dim")
    return Group(heading(sec), Padding(rich_table(sec), (0, 0, 0, 2)))


def print_section(console: Console, sec: dict) -> None:
    """Blank line, then the section's heading and table (or note)."""
    console.print(Text(""))
    console.print(section_block(sec))


PAIRS = [(0, 1), (2, 6)]   # size | people, activity | code age, when the terminal is wide enough
PAIR_GAP = 3


def report(report: dict, findings: list, console: Console, full: bool = False) -> None:
    console.print(header(report, findings))
    console.print(findings_panel(findings))
    secs = sections(report, full=full, width=console.width)
    order = list(range(len(secs)))
    if console.width >= SIDE_BY_SIDE_MIN_WIDTH:
        for a, b in PAIRS:
            left, right = section_block(secs[a]), section_block(secs[b])
            needed = console.measure(left).maximum + PAIR_GAP + console.measure(right).maximum
            if needed > console.width:
                continue   # stacked, with the usual blank line between them
            console.print(Text(""))
            console.print(Columns([left, right], padding=(0, PAIR_GAP), equal=False, expand=False))
            order = [i for i in order if i not in (a, b)]
    for i in order:
        print_section(console, secs[i])
    console.print(Text(""))
    console.print(Text(secrets_line(report), style="red" if report.get("secrets") else "green"))
    console.print(Text(f"Full results and plots in {report['out_dir']}", style="dim"), soft_wrap=True)


# --- markdown / json -------------------------------------------------------

def _md_cell(cell: str) -> str:
    return cell.replace("|", "\\|").replace("\n", " ")


def _md_findings(findings: list) -> list:
    if not findings:
        return ["Nothing flagged."]
    out = []
    for g in textfmt.group_findings(findings):
        line = f"- **{g['severity']}** {g['title']} — " + "; ".join(g["items"])
        if g["advice"]:
            line += f" _{g['advice']}_"
        out.append(line)
    return out


def markdown(report: dict, findings: list, full: bool = False) -> str:
    s = summary(report)
    out = [f"# {s['name']}", "",
           f"{s['commits']} commits · {s['first_date']} → {s['last_date']}" + (f" · since {s['since']}" if s["since"] else "") + f" · {s['identities']} {'identity' if s['identities'] == 1 else 'identities'} · branch {s['branch']}  ",
           f"{s['lines']:,} lines in {s['files']} files · {', '.join(s['languages']) or 'unknown'}", "",
           "## Findings", ""]
    out += _md_findings(findings)
    for sec in sections(report, full=True if full else "markdown"):
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
        out += _md_findings(found)
    return "\n".join(out) + "\n"


def portfolio_json(owner: str, reports: list) -> dict:
    return {"owner": owner, "repos": [{"name": n, "summary": summary(r), "findings": f, "out_dir": r["out_dir"]} for n, r, f in reports]}

"""Turn a loaded report into sections, then draw them with rich or as Markdown/JSON.

The default report is the tighter one: the columns you actually read, capped rows, elided
paths. `full` restores every column and row (Markdown export is always full)."""
from __future__ import annotations

import json

from rich import box
from rich.columns import Columns
from rich.console import Console, Group
from rich.markup import escape
from rich.padding import Padding
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from . import classify, coupling, filetypes, hotspots, identity, knowledge, leaks, loss, textfmt, trend, watch

SEVERITY_STYLE = {"critical": "bold red", "warning": "yellow", "info": "cyan"}

# section styling: the banner's palette carried into the tables
ACCENT = "#5ad0ff"          # section titles
HEADER = "bold #c86cff"     # column headers
BAR = "#5ad0ff"             # inline share bars
HOT = "bold #ff5cc8"        # values past a threshold
WARM = "#ff9ee0"            # values worth a glance
ROW_STYLES = ["", "on #1c2230"]
SIDE_BY_SIDE_MIN_WIDTH = 100

# the Timeline's month columns: each is 3 characters wide plus 2 of column padding, plus the 1-column
# gap rich reserves between every pair of columns even with the box's edges hidden (verified against
# rich.table.Table._calculate_column_widths, whose "n columns - 1" extra width cancels the gap saved
# on the last column, leaving a clean 6 per month). The section itself is indented by 2. FLOOR is the
# fewest months shown even when a name leaves almost no room. Once FLOOR is reached the months keep
# their full width and the name gives way instead, cut to whatever room is left; NAME_FLOOR is the
# fewest characters of a name still shown before the ellipsis, even if the months leave less room than
# that (eight is enough to keep most short names, and the start of longer ones, still recognisable).
# The section needs INDENT + NAME_FLOOR + FLOOR × MONTH_WIDTH = 28 columns; below that rich starves
# the month cells, which no real terminal reaches.
MONTH_WIDTH, INDENT, FLOOR, NAME_FLOOR = 6, 2, 3, 8

SYMBOLS = {"Size by language": "▤", "People": "◉", "Activity": "◔", "Timeline": "▦", "Hotspots": "◆", "Change coupling": "⟷",
           "Surviving code by year written": "◷", "Net lines added by year": "◷", "Paths in history by year last changed": "◷",
           "Knowledge map": "⌂", "Repo health": "✚", "Portfolio": "▣", "File types": "▥", "Complex functions": "λ", "Watch list": "◎",
           "Change risk": "◈", "Since last report": "⇄"}
# the one column to read first in each table; the rest are dimmed
KEY_METRIC = {"Size by language": "code", "People": "commits", "Hotspots": "revs", "Change coupling": "degree",
              "Knowledge map": "lines added", "Surviving code by year written": "lines", "Net lines added by year": "net lines",
              "Paths in history by year last changed": "paths", "Activity": "commits", "Portfolio": "commits", "Complex functions": "ccn",
              "Watch list": "why", "Change risk": "risk"}
SEVERITY_MARK = {"critical": "✖", "warning": "▲", "info": "●"}
RIGHT = {"justify": "right"}
FOLD = {"overflow": "fold"}
PATH = {"overflow": "fold", "no_wrap": False}

# rows shown by default; `full` lifts the caps. Markdown gets a looser cap of its own. Hotspots has
# no entry: it is `--full`/Markdown only now, so its row count is never decided by this table.
CAPS = {"People": 6, "Change coupling": 5, "Knowledge map": 6, "Size by language": 8, "Timeline": 8, "Complex functions": 8}
MARKDOWN_CAP = 50
TREND_TOP = 10   # the trend step's own --top default: only those files have samples
WATCH_CAP = 5   # the watch list is a short list by design; `full` and Markdown get a longer one, never all files
WATCH_FULL = watch.WATCH_TOP   # tied to watch's own cap: the --compare before side is sliced by what to_json wrote


WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def _pct(part, whole) -> str:
    return f"{100 * part / whole:.0f}%" if whole else "-"


def _bar(part, whole, width=30) -> str:
    return "█" * int(width * part / whole) if whole else ""


def _section(title, columns, rows, note=None, caption=None) -> dict:
    """columns: list of (name, rich column options). rows: lists of already-formatted cells."""
    return {"title": title, "columns": [c[0] for c in columns], "col_opts": [c[1] for c in columns],
            "rows": [[str(c) for c in r] for r in rows], "note": note, "caption": caption}


def _limit(title: str, full, cap=None):
    """How many rows to keep: None for all. `full` may be False (terminal default), True, or 'markdown'.
    An explicit `cap` is the section's own cap and holds for Markdown too."""
    if full is True:
        return None
    if cap is not None:
        return cap
    return MARKDOWN_CAP if full == "markdown" else CAPS.get(title)


def _more(total: int, limit) -> str:
    return f"and {total - limit} more" if limit is not None and total > limit else None


HIDDEN_SUFFIX = "; --full shows them"


def _hide_rows(rows: list, path_of, full, pred, noun: str, plural=None) -> tuple:
    """Drop rows whose path (or any of whose paths) satisfies `pred`, unless `full` is True.
    `path_of(row)` returns a single path or a tuple of paths to check. `noun` names one hidden row
    and `plural` names several, `noun + "s"` by default (a multi-word noun gives its own plural:
    "function in a test file" -> "functions in test files"). Returns (rows, note), `note` being
    the caption note for the hidden count, or None."""
    if full is True:
        return rows, None
    kept, hidden = [], 0
    for row in rows:
        paths = path_of(row)
        paths = (paths,) if isinstance(paths, str) else paths
        if any(pred(p) for p in paths):
            hidden += 1
        else:
            kept.append(row)
    note = f"{hidden} {noun if hidden == 1 else plural or noun + 's'} hidden{HIDDEN_SUFFIX}" if hidden else None
    return kept, note


def _hide_by(rows: list, path_of, full, classifier, reasons, noun: str, plural=None) -> tuple:
    """_hide_rows through the classifier: a row goes when any of its path's reasons is one the table hides."""
    return _hide_rows(rows, path_of, full, lambda p: classifier.excluded(p, reasons), noun, plural)


def _hide_tests(rows: list, path_of, full, noun="test file", plural=None, classifier=None) -> tuple:
    """Test files: they change with every fix, so they are not a signal on their own."""
    return _hide_by(rows, path_of, full, classifier or classify.Classifier({}), {"test file"}, noun, plural)


def _hide_vendor(rows: list, path_of, full, noun="file in vendored code", plural="files in vendored code", report: dict = None, classifier=None) -> tuple:
    """Vendored trees, by name, by the licence the run found or by the attribute the repository declares:
    somebody else's code, not this repository's risk."""
    return _hide_by(rows, path_of, full, classifier or classify.Classifier(report or {}), {"vendored"}, noun, plural)


def _hide_generated(rows: list, path_of, report: dict, full, noun="generated file", plural=None, classifier=None) -> tuple:
    """Generated files (a header marker or a linguist-generated attribute, found at run time) and
    amalgamations (other files pasted together, found from the function metrics): the generator's
    churn and complexity, not the repository's."""
    return _hide_by(rows, path_of, full, classifier or classify.Classifier(report or {}), {"generated", "amalgamation"}, noun, plural)


def _hide_release(pairs: list, full) -> tuple:
    """Coupled pairs where both files are release plumbing (version files, manifests, lock files,
    changelogs): they change together because a release touches them all, not because one depends on
    the other. A version file paired with real code stays."""
    if full is True:
        return pairs, None
    kept = [p for p in pairs if not (filetypes.is_release_path(p["entity"]) and filetypes.is_release_path(p["coupled"]))]
    hidden = len(pairs) - len(kept)
    return kept, (f"{hidden} release pair{'s' if hidden != 1 else ''} hidden{HIDDEN_SUFFIX}" if hidden else None)


def _hide_example_pairs(pairs: list, full) -> tuple:
    """Coupled pairs where both files are example or documentation material. curl's
    docs/examples/imap-ssl.c and docs/examples/pop3-ssl.c show one technique for two protocols, and
    smtp-expn.c and smtp-vrfy.c two commands of one: each is a copy of its sibling, so they change
    together by design and told the table's top two rows nothing. An example paired with the code it
    demonstrates stays, since that pair says the example tracks the API."""
    if full is True:
        return pairs, None

    def specimen(path):
        return filetypes.is_sample_path(path) or filetypes.is_doc_path(path)

    kept = [p for p in pairs if not (specimen(p["entity"]) and specimen(p["coupled"]))]
    hidden = len(pairs) - len(kept)
    return kept, (f"{hidden} example pair{'s' if hidden != 1 else ''} hidden{HIDDEN_SUFFIX}" if hidden else None)


def _hide_header_pairs(pairs: list, full) -> tuple:
    """A C-family source file and its own header change together by construction."""
    if full is True:
        return pairs, None
    kept = [p for p in pairs if not filetypes.is_header_pair(p["entity"], p["coupled"])]
    hidden = len(pairs) - len(kept)
    return kept, (f"{hidden} header pair{'s' if hidden != 1 else ''} hidden{HIDDEN_SUFFIX}" if hidden else None)


def _join_hidden(*notes) -> str:
    """Several hidden-row notes as one caption phrase: 'A hidden; B hidden; --full shows them'."""
    parts = [n[:-len(HIDDEN_SUFFIX)] if n.endswith(HIDDEN_SUFFIX) else n for n in notes if n]
    return "; ".join(parts) + HIDDEN_SUFFIX if parts else None


def _hide_deleted(rows: list, report: dict, full, classifier=None) -> tuple:
    """Drop hotspot rows for files no longer in the tree, unless `full` is True: a deleted file's churn
    is history. The classifier judges nothing as gone without a tree listing, so a killed scc hides
    nothing. Returns (rows, note) like _hide_tests."""
    if full is True:
        return rows, None
    cls = classifier or classify.Classifier(report or {})
    kept = [h for h in rows if not cls.excluded(h["entity"], {"not in the tree"})]
    hidden = len(rows) - len(kept)
    return kept, (f"{hidden} deleted file{'s' if hidden != 1 else ''} hidden{HIDDEN_SUFFIX}" if hidden else None)


def _hide_gone(pairs: list, report: dict, full, classifier=None) -> tuple:
    """Drop coupled pairs where either file is no longer in the tree, unless `full` is True: they
    describe a layout that no longer exists. Returns (pairs, note) like _hide_tests."""
    if full is True:
        return pairs, None
    cls = classifier or classify.Classifier(report or {})
    kept = [p for p in pairs if not (cls.excluded(p["entity"], {"not in the tree"}) or cls.excluded(p["coupled"], {"not in the tree"}))]
    hidden = len(pairs) - len(kept)
    return kept, (f"{hidden} historical pair{'s' if hidden != 1 else ''} hidden; --full shows them" if hidden else None)


def _empty_note(base, hidden_note, source_base=None) -> str:
    """The note that replaces a table with no rows left. When test rows were hidden the note has to
    carry the count, since the caption goes with the table, and what is left is the source rows."""
    return f"{source_base or base}; {hidden_note}" if hidden_note else base


def _keep(columns: list, rows: list, names) -> tuple:
    """Keep only the columns called `names`, in the given order, for both header and rows."""
    index = {c[0]: i for i, c in enumerate(columns)}
    picked = [index[n] for n in names]
    return [columns[i] for i in picked], [tuple(r[i] for i in picked) for r in rows]


FOLD_BUDGET = 24   # the most a non-path folding column (a function name, say) may take from the paths' room


def _path_indices(path_columns) -> tuple:
    """path_columns: the first N columns (an int) or explicit column indices."""
    return tuple(range(path_columns)) if isinstance(path_columns, int) else tuple(path_columns)


def _path_room(width, rows: list, columns: list, path_columns=1) -> int:
    """Characters available to each path column once the other cells and rich's padding are counted."""
    if width is None:
        return None
    paths = _path_indices(path_columns)
    other = [i for i in range(len(columns)) if i not in paths]
    def charged(i):
        widest = max([len(str(r[i])) for r in rows] + [len(columns[i][0])])
        return min(widest, FOLD_BUDGET) if columns[i][1].get("overflow") == "fold" else widest   # a folding column wraps instead
    widest = sum(charged(i) for i in other)
    padding = 3 * (len(columns) - 1)
    return max(16, (width - widest - padding) // len(paths))


def _shorten(rows: list, width, columns: list, path_columns=1) -> list:
    room = _path_room(width, rows, columns, path_columns)
    if room is None:
        return rows
    paths = _path_indices(path_columns)
    return [tuple(textfmt.shorten_path(str(c), room) if i in paths else c for i, c in enumerate(r)) for r in rows]


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
        "pulse": pulse(report),
        "coverage": m.get("coverage") or {},
        "commit": (m.get("run") or {}).get("commit"),
    }


# The steps every table leans on, by what the reader loses without them. The optional steps (code age,
# functions, duplicates, trend, backtest) say so in their own sections; the structure step has none, so pulse names it.
CORE_STEPS = {"scc": "size", "git-sizer": "repo health", "git-log": "change log", "change analysis": "change analysis",
              "betterleaks": "secrets scan", "osv-scanner": "dependency scan"}


# "cancelled" is kept for completeness, though an interrupted run never records its steps; "planned" is what
# an interrupted run leaves on an optional step's own status, which is a step that did not complete.
STEP_WORDS = {"timeout": "timed out", "failed": "failed", "skipped": "skipped", "cancelled": "cancelled", "planned": "did not complete"}


def _step_phrase(label: str, status: str) -> str:
    return f"{label} {STEP_WORDS.get(status, status)}"


def _structure_status(report: dict) -> str:
    """What the structure step's rules would find: the run's own status for the step, and "run" only if the
    step also left a readable structure.json that says so — the field the seven rules key on (findings._structure),
    so the header never vouches for checks the rules did not make."""
    planned = report["meta"].get("structure")
    if not planned:
        return "run"   # an output directory from before the step existed: nothing was promised, nothing to say
    status = planned.get("status", "run")
    if status == "run" and "structure" in report and (report["structure"] or {}).get("status") != "run":
        status = (report["structure"] or {}).get("status") or "failed"   # the step said run, its file does not: the rules found nothing
    return status


def _unfinished(report: dict) -> list:
    """The steps a missing table came from, first on the header's second line so a reader knows the numbers
    after them may be missing. The structure step has no section of its own, so its seven rules going missing
    shows here too — but not a skip, which is the interpreter's (Python before 3.10 has no grammars): that is
    said at install time and on --full, and a header phrase that differs by Python version would make one
    commit render two reports."""
    steps = report["meta"].get("steps") or {}
    out = [_step_phrase(label, steps[name]) for name, label in CORE_STEPS.items() if steps.get(name) not in (None, "run")]
    structure = _structure_status(report)
    if structure not in ("run", "skipped", "not-installed"):
        out.append(_step_phrase("structure checks", structure))
    return out


def pulse(report: dict) -> list:
    """One phrase each for the descriptive tables the default report leaves out."""
    out = _unfinished(report)   # first: every number below may be missing because of it
    act = report.get("activity") or {}
    days, hours = act.get("by_weekday") or [], act.get("by_hour") or []
    if days and max(days):
        day = WEEKDAYS[max(range(7), key=lambda i: days[i])]
        when = f" at {max(range(24), key=lambda i: hours[i]):02d}:00" if hours and max(hours) else ""
        out.append(f"most commits on {day}{when}")
    total = sum(days)
    if act.get("fix_commits") is not None and total:
        out.append(f"{_pct(act['fix_commits'], total)} of commits are fixes")
    if act.get("revert_commits") and total:
        pct = _pct(act['revert_commits'], total)
        if pct == "0%":
            reverts = act['revert_commits']
            out.append(f"{reverts} revert" if reverts == 1 else f"{reverts} reverts")
        else:
            out.append(f"{pct} of commits are reverts")
    cohorts = report.get("cohorts") or {}
    if cohorts:
        label, lines = max(cohorts.items(), key=lambda kv: kv[1])
        out.append(f"{_pct(lines, sum(cohorts.values()))} of surviving code from {label.replace('Code added in ', '')}")
    elif _age_status(report) != "run":
        out.append(_age_reason(report))   # the age table is --full only, so this is where a timeout shows
    signed = signing_phrase(report)
    if signed:
        out.append(signed)
    dup = report.get("duplicates") or {}
    then = dup.get("then") or {}
    if dup.get("rate") is not None and then.get("rate") is not None and max(dup["rate"], then["rate"]) >= 0.5:
        now, before = dup["rate"], then["rate"]
        way = "as a year before" if round(now, 1) == round(before, 1) else f"{'up' if now > before else 'down'} from {before:.1f}% a year before"
        out.append(f"{now:.1f}% of lines duplicated, {way}")
    return out


def signing_phrase(report: dict):
    """'33% of commits signed (ssh 28%, gpg 6%), 50% of the last year's', or 'no commits signed'; None
    without the step. Read from the commit objects, nothing verified: evidence, not a level."""
    sig = report.get("signing") or {}
    if not sig.get("commits"):
        return None
    if not sig.get("signed"):
        return "no commits signed"
    mix = ", ".join(f"{k} {_pct(v, sig['commits'])}" for k, v in sorted((sig.get("mechanisms") or {}).items(), key=lambda kv: (-kv[1], kv[0])))
    last = sig.get("last_year") or {}
    tail = f", {_pct(last['signed'], last['commits'])} of the last year's" if last.get("commits") else ""
    return f"{_pct(sig['signed'], sig['commits'])} of commits signed ({mix}){tail}"


def _age_status(report: dict) -> str:
    return (report["meta"].get("age") or {}).get("status", "run")


def _age_reason(report: dict) -> str:
    return _step_phrase("code age", _age_status(report))


def watch_section(report: dict, full: bool = True, width=None) -> dict:
    """The files to keep an eye on, with the reasons in words. Paths stay whole here."""
    ranked = watch.risks(report)
    limit = WATCH_CAP if full is False else WATCH_FULL
    shown = watch.REASONS_SHOWN if full is False else None   # the default terminal view keeps each row readable
    rows = [(r["file"], " · ".join(r["reasons"][:shown]) + (f" · {len(r['reasons']) - shown} more" if shown and len(r["reasons"]) > shown else ""))
            for r in ranked[:limit]]
    columns = [("file", PATH), ("why", {"overflow": "fold", "ratio": 3})]
    since = report["meta"].get("since")
    # "alone": the reasons never move a file; a reader who sees fixes and ownership beside each row
    # would otherwise take them for the ranking
    notes = ["ranked by revisions × lines of code alone; the reasons say what to look at there" + (f"; commits since {since}" if since else "")]
    bt = watch.backtest(report)
    status = report["meta"].get("backtest") or {}
    if bt and not bt["fixed"]:
        notes.append("nothing has been fixed since the cut-off six months ago, so there is nothing to score the list against")
    elif bt:
        notes.append(f"6 months ago this list would have named {bt['hits']} of the {bt['fixed']} files fixed since "
                     f"(a random {bt['listed']} of the {bt['pool']} files that had changed more than once would name {bt['expected']}; "
                     f"the {bt['listed']} most changed would name {bt['baselines']['churn']})"
                     + ("; whole history" if since else ""))   # the backtest ignores the window
    elif status.get("reason"):
        notes.append(status["reason"])
    elif status.get("status") in ("failed", "timeout"):
        notes.append(f"backtest {status['status']}")
    left_out = sweeps_note(report)
    if left_out:
        notes.append(left_out)
    caption = "\n".join(notes)
    return _section("Watch list", columns, rows, note=None if rows else watch.why_empty(report), caption=caption if rows else None)


def sweeps_note(report: dict):
    """'2 sweeping commits (...) and 3 declared in .git-blame-ignore-revs are left out of every count', or
    None when the change analysis left nothing out (or predates the record)."""
    act = report.get("activity") or {}
    swept, declared = [c for c in act.get("sweeping") or [] if not c.get("declared")], act.get("ignored_revs") or 0
    parts = []
    if swept:
        parts.append(f"{len(swept)} sweeping commit{'s' if len(swept) != 1 else ''} (a formatter run, a rename across the tree)")
    if declared:
        parts.append(f"{declared} declared in .git-blame-ignore-revs")
    if not parts:
        return None
    return " and ".join(parts) + (" are" if swept and declared or len(swept) > 1 or declared > 1 else " is") + " left out of every count"


RISK_CAP = 15


def risk_section(risk: dict, base: str, full=True) -> dict:
    """The files a change touches, each with its watch score as a bar scaled to the repo's worst file."""
    rows_all = risk["files"]
    limit = _limit("Change risk", full, cap=RISK_CAP)
    top = risk["max_score"] or 1.0
    rows = [(r["file"], "▰" * round(10 * r["score"] / top) if r["score"] else "", " · ".join(r["reasons"])) for r in rows_all[:limit]]
    columns = [("file", PATH), ("risk", {}), ("why", {"overflow": "fold", "ratio": 3})]
    watched = risk["watched"]
    notes = [f"total {risk['total']:.1f}% of the repository's revisions × lines of code; "
             f"{watched} of these files {'is' if watched == 1 else 'are'} on the watch list"] if rows else []
    more = _more(len(rows_all), limit)
    if more:
        notes.append(more)
    factors = (risk.get("change") or {}).get("reasons") or []
    if rows and factors:
        notes.append("; ".join(factors))
    gaps = risk.get("coupling_gaps") or []
    if rows and gaps:
        notes.append(gaps_line(gaps))
    return _section(f"Change risk ({len(rows_all)} files since {base})", columns, rows,
                    note=None if rows else f"no files changed since {base}", caption="\n".join(notes) or None)


def gaps_line(gaps: list) -> str:
    """'not touched: core/ast.py, which moved in 72% of core/parser.py's changes, and core/lexer.py (70%)':
    the companions a change left out, strongest first."""
    first = gaps[0]
    rest = [f"{g['companion']} ({g['degree']}%)" for g in gaps[1:4]]
    line = f"not touched: {first['companion']}, which moved in {first['degree']}% of {first['file']}'s changes"
    return line + (", and " + textfmt.join_and(rest) if rest else "") + (f" and {len(gaps) - 4} more" if len(gaps) > 4 else "")


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
    merges = any(i.get("merges") for i in ids)   # merges apart: merging every pull request is not writing the code
    ids = sorted(ids, key=lambda i: -(i["commits"] - i.get("merges", 0))) if merges else ids
    total_commits = sum(i["commits"] - i.get("merges", 0) for i in ids)
    surviving = report.get("theseus_authors") or {}
    total_lines = sum(surviving.values())
    limit = _limit("People", full)
    rows = [(i["name"], i["email"], i["commits"] - i.get("merges", 0), *((i.get("merges", 0),) if merges else ()),
             _pct(i["commits"] - i.get("merges", 0), total_commits), _pct(surviving.get(i["name"], 0), total_lines)) for i in ids[:limit]]
    columns = [("author", {}), ("email", {"style": "dim", "overflow": "fold"}), ("commits", RIGHT), *((("merges", RIGHT),) if merges else ()),
               ("share", RIGHT), ("surviving code", RIGHT)]
    if full is not True:
        columns, rows = _keep(columns, rows, ["author", "commits", *(["merges"] if merges else []), "share", "surviving code"])
    since = report["meta"].get("since")
    notes = [f"commits since {since}; surviving code is for the whole tree"] if since else []
    if merges:
        notes.append(f"commits and share leave out merges, which are counted apart ({sum(i.get('merges', 0) for i in ids):,} in all)")
    more = _more(len(ids), limit)
    if more:
        notes.append(more)
    bots = report["meta"].get("bots") or []
    if bots:
        notes.append("bots left out: " + ", ".join(f"{b['name']} ({b['commits']}{' commits' if i == 0 else ''})" for i, b in enumerate(bots[:3]))
                     + (f" and {len(bots) - 3} more" if len(bots) > 3 else ""))
    merged = [i["name"] for i in ids if i.get("aliases")]
    if merged:
        who = ", ".join(merged[:3]) + (f" and {len(merged) - 3} more" if len(merged) > 3 else "")
        notes.append(f"aliases merged for {who}; a .mailmap makes that permanent")
    return _section("People", columns, rows, caption="\n".join(notes) or None)


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
    """Commits per author, one column per month. Names never fold: when the year does not fit the
    terminal width, the oldest months are dropped (down to FLOOR) instead. If a name is still too long
    for the room FLOOR leaves, the name gives way, not the months: it is shown cut with an ellipsis
    (never fewer than NAME_FLOOR characters), so the months a reader came for stay full width. The
    title names the months actually shown; ranking, bots filtering and the row's key are all still the
    real name, only the displayed cell is cut. With no width (the Markdown export) nothing is trimmed."""
    tl = (report.get("activity") or {}).get("timeline") or {}
    if not tl:
        return _section("Timeline", [("author", {})], [], note="no timeline data")
    last = max(m for per in tl.values() for m in per)
    span = _month_range(last, months)
    since = report["meta"].get("since")
    if since:
        span = [m for m in span if m >= since[:7]] or span[-1:]
    # the run decided who is a bot from name and email; the timeline only has the name, so it asks the run
    bots = {b["name"] for b in report["meta"].get("bots") or []}

    def active(shown):
        """Who to list and in what order: commits inside the months actually shown, most first."""
        totals = {a: sum(per.get(m, 0) for m in shown) for a, per in tl.items()}
        return [a for a in sorted(totals, key=lambda a: -totals[a])
                if totals[a] > 0 and a not in bots and not identity.is_bot(a)]

    ranked = active(span)
    limit = _limit("Timeline", full)
    if width:
        name = max([len("author")] + [len(a) for a in ranked[:limit]])
        span = span[-max(FLOOR, min(len(span), (width - INDENT - name) // MONTH_WIDTH)):]
        # The months that fit are the months that decide who is listed. Ranking over the wider span and
        # printing the narrower one gave curl a row for Xiaoke Wang and react one for Sebastian Markbåge,
        # a dot in every column shown: their commits were all in the months the width dropped. The name
        # column is measured before this, so a longer name here is cut by `room` below, as always.
        ranked = active(span)
    columns = [("author", {"no_wrap": True})] + [(MONTHS[int(m[5:7]) - 1], RIGHT) for m in span]
    room = width - INDENT - MONTH_WIDTH * len(span) if width else None
    rows = [(textfmt.cut(a, max(NAME_FLOOR, room)) if width else a, *[tl[a].get(m) or "·" for m in span]) for a in ranked[:limit]]
    return _section(f"Timeline ({_month_label(span[0])} → {_month_label(span[-1])})", columns, rows, caption=_more(len(ranked), limit))


def signing_section(report: dict, full: bool = True, width=None) -> dict:
    """Signed commits per year, from the gpgsig headers: --full and Markdown only."""
    sig = report.get("signing") or {}
    columns = [("year", {}), ("commits", RIGHT), ("signed", RIGHT), ("share", RIGHT)]
    if not sig.get("commits"):
        return _section("Signing by year", columns, [], note="no signing data")
    rows = [(year, y["commits"], y["signed"], _pct(y["signed"], y["commits"])) for year, y in sorted((sig.get("by_year") or {}).items())]
    humans, bots = sig.get("humans") or {}, sig.get("bots") or {}
    parts = []
    if humans.get("commits"):
        parts.append(f"humans {_pct(humans['signed'], humans['commits'])} signed" + (f", bots {_pct(bots['signed'], bots['commits'])}" if bots.get("commits") else ""))
    people = [i for i in (sig.get("by_identity") or [])[:5]]
    if people:
        parts.append(", ".join(f"{i['name']} {_pct(i['signed'], i['commits'])}" for i in people))
    parts.append("read from the commit objects, nothing verified")
    return _section("Signing by year", columns, rows, caption="; ".join(parts))


def watch_by_component_section(report: dict, full: bool = True, width=None) -> dict:
    """The watch list's top files within each component: --full and Markdown only."""
    groups = watch.by_component(watch.risks(report))
    rows = [(g["component"], f"{g['share']:.0f}%", " · ".join(x["file"] for x in g["files"]))
            for g in groups]
    columns = [("component", PATH), ("share", RIGHT), ("top files", {"overflow": "fold", "ratio": 3})]
    return _section("Watch list by component", columns, rows, note=None if rows else "no component holds 5% of the list's score",
                    caption="each component's share of the watch list's revisions × lines of code, and its own top files" if rows else None)


def trailers_section(report: dict, full: bool = True, width=None) -> dict:
    """The trailer keys the history carries, with the cohort comparison and the neutral commit-shape
    descriptors below: --full and Markdown only. Read, never inferred; nothing is labelled."""
    prov = report.get("provenance") or {}
    tr, co, sh = prov.get("trailers") or {}, prov.get("cohort") or {}, prov.get("shape") or {}
    columns = [("trailer", {}), ("commits", RIGHT), ("share", RIGHT)]
    total = tr.get("commits") or 0
    rows = [(k, n, _pct(n, total)) for k, n in (tr.get("keys") or {}).items()]
    notes = []
    marked, rest = co.get("cohort") or {}, co.get("rest") or {}
    if marked.get("commits"):
        def pair(key):
            return f"{_pct(marked.get(key, 0), marked['commits'])} against {_pct(rest.get(key, 0), rest.get('commits') or 0)}"
        watch_part = f", touched a file on the watch list's top {co['watch_top']} {pair('watch')}" if co.get("watch_top") else ""
        notes.append(f"marked commits ({co.get('definition')}): {marked['commits']:,}, {round(100 * co.get('share', 0))}% of the history; "
                     f"reverted {pair('reverted')} for the rest, fixes {pair('fixes')}, a file changed again within two weeks {pair('retouched')}{watch_part}")
    if sh:
        notes.append(f"{round(100 * sh.get('burst_share', 0))}% of commits land in bursts of five or more within ten minutes; "
                     f"{round(100 * sh.get('conventional_share', 0))}% have conventional-commit subjects; commits come in {sh.get('hours_used', 0)} hours of the day")
    return _section("Trailers", columns, rows, note=None if rows else "no trailers", caption="\n".join(notes) or None)


def lines_section(report: dict, full: bool = True, width=None) -> dict:
    """Lines added to code files in the last year and the year before, the share git marks as moved and
    the share deleted again within two weeks, and the same for the marked cohort against the rest:
    --full and Markdown only. A direction for this repository, not a score."""
    ln = (report.get("provenance") or {}).get("lines") or {}

    def share(x):
        return "-" if x is None else f"{100 * x:.1f}%"
    rows = [(f"{w['label']} ({w['from']} to {w['to']})", w["commits"], w["added"], share(w.get("moved_share")), share(w.get("churn_share")))
            for w in ln.get("windows") or []]
    co = ln.get("cohort") or {}
    if (co.get("marked") or {}).get("commits"):
        rows += [(label, c["commits"], c["added"], share(c.get("moved_share")), share(c.get("churn_share")))
                 for label, c in (("marked commits, both years", co["marked"]), ("the rest, both years", co["rest"]))]
    columns = [("period", {"overflow": "fold"}), ("commits", RIGHT), ("lines added", RIGHT), ("moved", RIGHT), (f"churned in {ln.get('churn_days', 14)} days", RIGHT)]
    return _section("Changed lines", columns, rows, note=None if rows else "no history in the last two years",
                    caption="code files only; moved: lines git's moved-code detection marks (--color-moved=blocks); churned: deleted again "
                            "within two weeks from the same file with the same text" if rows else None)


def hotspots_section(report: dict, full: bool = True, width=None) -> dict:
    """Change frequency times size, Tornhill-style. Files no longer in the tree sort last. Drawn
    under `--full` and in the Markdown export only; the default terminal report leaves it to the
    watch list, which ranks the same files. Built only for those two, it has no row cap of its
    own outside Markdown's."""
    authors = {a["entity"]: a["n-authors"] for a in report.get("authors") or []}
    minors = {a["entity"]: a.get("minor", 0) for a in report.get("authors") or []}
    partners = {a["entity"]: a.get("partners", 0) for a in report.get("soc") or []}
    ages = {a["entity"]: a["age-months"] for a in report.get("age") or []}
    fixes = {f["entity"]: f["n-fixes"] for f in report.get("fixes") or []}
    cls = classify.Classifier(report)
    scored = hotspots.ranked(report)
    scored, hidden_note = _hide_tests(scored, lambda h: h["entity"], full, classifier=cls)
    scored, deleted_note = _hide_deleted(scored, report, full, classifier=cls)
    scored, generated_note = _hide_generated(scored, lambda h: h["entity"], report, full, classifier=cls)
    scored, release_note = _hide_by(scored, lambda h: h["entity"], full, cls, {"release file"}, "release file")
    hidden_note = _join_hidden(hidden_note, deleted_note, generated_note, release_note)
    title = "Hotspots (score = revisions × lines of code)" if full is True else "Hotspots"
    limit = _limit("Hotspots", full)
    series = (report.get("trend") or {}).get("files") or {}
    last = report["meta"].get("last_date") or ""
    def trend_cell(path):
        s = series.get(path) or []
        if full is True:
            return trend.sparkline(s) or "-"
        return trend.change_over_year(s, last) if last else "-"
    rows = []
    for h in scored[:limit]:
        gone = h["code"] is None
        rows.append((h["entity"], h["revs"], "-" if gone else f"{h['code']:,}", "-" if gone else h["complexity"],
                     "-" if gone else f"{h['score']:,}", fixes.get(h["entity"], 0), authors.get(h["entity"], "-"), minors.get(h["entity"], "-"),
                     partners.get(h["entity"], "-"), ages.get(h["entity"], "-"), trend_cell(h["entity"])))
    # minors: contributors with under 5% of the file's commits; co-changes: files it shares five or more commits with (sum of coupling)
    columns = [("file", PATH), ("revs", RIGHT), ("lines", RIGHT), ("cplx", RIGHT), ("score", RIGHT), ("fixes", RIGHT), ("authors", RIGHT),
               ("minors", RIGHT), ("co-changes", RIGHT), ("idle", RIGHT), ("trend", RIGHT)]
    if full is not True:
        columns, rows = _keep(columns, rows, ["file", "revs", "lines", "fixes", "authors", "trend"])
    note = None if rows else _empty_note(None, hidden_note, "no source hotspots")
    notes = [c for c in (_more(len(scored), limit), None if note else hidden_note) if c]
    if series:
        notes.append(f"trend sampled for the top {TREND_TOP} hotspots")   # the rest of the column is empty by design
    return _section(title, columns, rows, note=note, caption="; ".join(notes) or None)


def coupling_section(report: dict, full: bool = True, width=None) -> dict:
    cls = classify.Classifier(report)
    pairs = sorted((p for p in report.get("coupling") or [] if p["average-revs"] >= 5), key=lambda p: (-p["degree"], -p["average-revs"]))
    pairs, hidden_note = _hide_tests(pairs, lambda p: (p["entity"], p["coupled"]), full, noun="test pair", classifier=cls)
    pairs, gone_note = _hide_gone(pairs, report, full, classifier=cls)
    pairs, release_note = _hide_release(pairs, full)
    pairs, example_note = _hide_example_pairs(pairs, full)
    pairs, header_note = _hide_header_pairs(pairs, full)
    pairs, vendor_note = _hide_vendor(pairs, lambda p: (p["entity"], p["coupled"]), full, noun="vendored pair", plural="vendored pairs", report=report, classifier=cls)
    pairs, generated_note = _hide_generated(pairs, lambda p: (p["entity"], p["coupled"]), report, full, noun="generated pair", plural="generated pairs", classifier=cls)
    gone_note = _join_hidden(gone_note, release_note, example_note, header_note, vendor_note, generated_note)
    groups, cluster_note = [], None
    if full is not True:
        # a directory whose files all change together is one row; --full lists every pair
        groups, pairs = coupling.clusters(pairs)
        if groups:
            n_pairs, n_dirs = sum(g["pairs"] for g in groups), len(groups)
            cluster_note = (f"{n_pairs} pairs in {n_dirs} director{'y' if n_dirs == 1 else 'ies'} shown as "
                            f"{'one row' if n_dirs == 1 else 'one row each'}{HIDDEN_SUFFIX}")
    hidden_note = _join_hidden(hidden_note, gone_note, cluster_note)
    limit = _limit("Change coupling", full)
    rows = [(f"{g['dir']} ({g['files']} files)", "each other", f"≥{g['degree']}%", g["average-revs"]) for g in groups]
    rows += [(p["entity"], p["coupled"], f"{p['degree']}%", p["average-revs"]) for p in pairs[:max(limit - len(groups), 0) if limit else None]]
    columns = [("file", PATH), ("changes with", PATH), ("degree", RIGHT), ("avg revs", RIGHT)]
    if full is not True:
        columns, rows = _keep(columns, rows, ["file", "changes with", "degree"])
        rows = _shorten(rows, width, columns, path_columns=2)
    note = None if rows else _empty_note("no pairs with 5+ shared revisions", hidden_note, "no source pairs with 5+ shared revisions")
    notes = [c for c in (_more(len(pairs), limit), None if note else hidden_note) if c]
    caveat = coupling.regime(report)[1]   # what a pair means here: a pull request under squash merging, an edit otherwise
    if rows and caveat:
        notes.append(caveat)
    return _section("Change coupling", columns, rows, note=note, caption="; ".join(notes) or None)


def age_section(report: dict, full: bool = True, width=None) -> dict:
    cohorts = report.get("cohorts") or {}
    if not cohorts and _age_status(report) != "run":
        return age_fallback_section(report)
    total = sum(cohorts.values())
    rows = [(label.replace("Code added in ", ""), f"{lines:,}", _pct(lines, total), _bar(lines, total)) for label, lines in cohorts.items()]
    return _section("Surviving code by year written", [("year", {}), ("lines", RIGHT), ("share", RIGHT), ("", {"style": "blue"})], rows,
                    note=None if rows else "no age data")


def age_fallback_section(report: dict) -> dict:
    """When the blame pass did not run: net lines added per year from the log, or failing that,
    paths by the year they were last changed."""
    reason = _age_reason(report)
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


CCN_FLOOR = 10  # lizard's own "complex" threshold; below it a function is not worth a row


def functions_section(report: dict, full: bool = True, width=None) -> dict:
    """Functions at or over the complexity floor, worst first, from lizard when it is installed."""
    cls = classify.Classifier(report)
    measured = report.get("functions") or []
    funcs = sorted((f for f in measured if f["ccn"] >= CCN_FLOOR), key=lambda f: (-f["ccn"], -f["nloc"], f["file"], f["function"], f["start"]))
    funcs, hidden_note = _hide_tests(funcs, lambda f: f["file"], full, noun="function in a test file", plural="functions in test files", classifier=cls)
    funcs, vendor_note = _hide_vendor(funcs, lambda f: f["file"], full, noun="function in vendored code", plural="functions in vendored code", report=report, classifier=cls)
    funcs, sample_note = _hide_by(funcs, lambda f: f["file"], full, cls, {"example code"}, "function in example code", "functions in example code")
    funcs, generated_note = _hide_generated(funcs, lambda f: f["file"], report, full, noun="function in a generated file", plural="functions in generated files", classifier=cls)
    hidden_note = _join_hidden(hidden_note, vendor_note, sample_note, generated_note)
    limit = _limit("Complex functions", full)
    shown = funcs[:limit]
    rows = [(f["function"], _where(f), f"{f['ccn']}{SUSPECT_MARK}" if f.get("suspect") else f["ccn"], f["nloc"], f["params"]) for f in shown]
    suspects = sum(1 for f in shown if f.get("suspect"))
    suspect_note = f"{SUSPECT_MARK} marks {suspects} span{'s' if suspects != 1 else ''} lizard may have mis-parsed" if suspects else None
    columns = [("function", {"overflow": "fold"}), ("file", PATH), ("ccn", RIGHT), ("lines", RIGHT), ("params", RIGHT)]
    if full is not True:
        rows = _shorten(rows, width, columns, path_columns=(1,))
    status = (report["meta"].get("functions") or {}).get("status", "skipped" if not measured else "run")
    reason = {"timeout": "function metrics timed out", "failed": "function metrics failed (see run.log)",
              "skipped": "no function metrics (install lizard)"}.get(status, "function metrics did not complete")
    partial = f"partial: {reason}" if measured and status in ("timeout", "failed") else None   # the step streams rows, so a stopped one leaves some
    if not measured and status != "run":
        note = reason
    elif not measured:
        note = "no functions found in the code files"
    elif not rows:
        counted = f"({len(measured):,} function{'s' if len(measured) != 1 else ''} measured{'; ' + partial if partial else ''})"
        note = _empty_note(f"nothing over complexity {CCN_FLOOR} {counted}", hidden_note,
                           f"nothing over complexity {CCN_FLOOR} in source files {counted}")
    else:
        note = None
    caption = "; ".join(c for c in (_more(len(funcs), limit), None if note else hidden_note, partial, suspect_note) if c) or None
    return _section("Complex functions", columns, rows, note=note, caption=caption)


SUSPECT_MARK = "?"


def _where(f: dict) -> str:
    """A named function is found by its name in its file; a nameless one goes by its start line's text,
    so the row says which line."""
    return f"{f['file']}:{f['start']}" if f.get("anonymous") else f["file"]


def knowledge_section(report: dict, full: bool = True, width=None) -> dict:
    """Ownership by area of the tree: who wrote most of each directory, gone owners marked."""
    months = report["meta"].get("gone_months", loss.DEFAULT_MONTHS)
    gone = {g["name"] for g in loss.gone(report, months)}
    rows_all = report.get("ownership") or []   # every area the map showed before, tests included
    areas = loss.areas(rows_all, gone)
    hidden_note = None
    tree = (report.get("size") or {}).get("files") or {}
    if full is not True and tree:
        # a directory the history knows but HEAD does not is a layout that no longer exists; the rows are
        # filtered before the areas are built so a vanished layout cannot hide that one directory now dominates
        areas = [a for a in loss.areas(knowledge.present_rows(rows_all, tree), gone) if knowledge.in_tree(a["area"], tree)]
        hidden = len({knowledge.top_area(r["entity"]) for r in rows_all if not knowledge.in_tree(knowledge.top_area(r["entity"]), tree)})
        hidden_note = f"{hidden} historical area{'s' if hidden != 1 else ''} hidden{HIDDEN_SUFFIX}" if hidden else None
    limit = _limit("Knowledge map", full)
    rows = []
    for a in areas[:limit]:
        owners = [f"{name}{' (gone)' if name in gone else ''} ({_pct(n, a['lines'])})" for name, n in a["owners"][:2]] + ["-"]
        lost = f"{100 * a['lost_share']:.0f}%" if a["lines"] else "-"
        rows.append((a["area"], f"{a['lines']:,}", a["authors"], lost if gone else "-", owners[0], owners[1]))
    columns = [("area", PATH), ("lines added", RIGHT), ("authors", RIGHT), ("lost", RIGHT), ("main owner", {}), ("second", {})]
    if full is not True:
        columns, rows = _keep(columns, rows, ["area", "lines added", "main owner", "second"])
    notes = [c for c in (_more(len(areas), limit), hidden_note) if c]
    if gone:
        notes.append(f"gone = no commits in the {months} months before {report['meta'].get('last_date')}"
                     + ("; gone and lost are measured over the whole history" if report["meta"].get("since") else ""))
    return _section("Knowledge map", columns, rows, note=None if rows else "no ownership data", caption="\n".join(notes) or None)


def health_section(report: dict, full: bool = True, width=None) -> dict:
    rows = [(r["name"], r["value"], "*" * r["concern"], r["ref"]) for r in report.get("sizer") or []]
    note = None if rows else ("not measured: git-sizer needs a full clone, and this one is shallow" if (report.get("meta") or {}).get("shallow")
                              else "nothing flagged")
    return _section("Repo health (git-sizer concerns)", [("metric", {}), ("value", RIGHT), ("concern", {}), ("object", FOLD)], rows, note=note)


def osps_section(report: dict, full: bool = True, width=None) -> dict:
    """The OSPS Baseline controls a clone can show, each with its result here: --full and Markdown only."""
    from . import findings, osps
    rows = [(r["control"], r["requirement"], r["result"], r["evidence"]) for r in osps.coverage(report, findings.evaluate(report))]
    return _section("OSPS Baseline", [("control", {"no_wrap": True}), ("asks", {"overflow": "fold", "ratio": 2}), ("result", {}), ("evidence", {"overflow": "fold", "ratio": 3})],
                    rows, caption=f"the controls a clone can show evidence for, from the {osps.BASELINE}; access control and most of vulnerability management need the forge")


def _tally_words(counts: dict) -> str:
    return textfmt.tally([{"severity": s} for s, n in counts.items() for _ in range(n)])


def _changed_words(changed) -> str:
    """ (values 16 → 1; places 40 → 2): the counts that moved under a persisting finding, first four."""
    if not changed:
        return ""
    fmt = lambda v: f"{v:,}" if isinstance(v, int) else f"{v:,.1f}"   # noqa: E731
    words = [f"{field.replace('_', ' ')} {fmt(b)} → {fmt(a)}" for field, b, a in changed[:4]]
    return " (" + "; ".join(words) + (f"; {len(changed) - 4} more" if len(changed) > 4 else "") + ")"


def compare_section(result: dict) -> dict:
    """Since last report: the findings that are new, resolved or persisting (with the severity they had),
    and the files that entered or left the watch list."""
    rows = [("new", f"{f['severity']} · {f['title']}") for f in result["new"]]
    rows += [("resolved", f"{f['severity']} · {f['title']}") for f in result["resolved"]]
    rows += [("persisting", (f"{f['was']} → {f['severity']}" if f["was"] != f["severity"] else f["severity"]) + f" · {f['title']}" + _changed_words(f.get("changed")))
             for f in result["persisting"]]
    rows += [("entered the watch list", p) for p in result["watch_entered"]] + [("left the watch list", p) for p in result["watch_left"]]
    before = result["before"]
    against = f"against {before['commit'][:8]}" if before.get("commit") else "against an export without a run manifest"
    lines = []
    if before.get("options_differ"):
        lines.append(f"options differ: {', '.join(before['options_differ'])}; the changes partly reflect them")
    ver = before.get("gitmole")
    if ver:
        lines.append(f"the earlier export was written by gitmole {ver['before']}, this one by {ver['after']}: "
                     "a rule changed between them moves a finding with no change to the code")
    tools = before.get("tools") or {}
    if tools:
        moved = ", ".join(f"{name} {v['before']} → {v['after']}" for name, v in sorted(tools.items()))
        lines.append(f"a tool moved between the runs ({moved}), so its counts can move with no change to the code")
    db = before.get("database")
    if db:
        lines.append(f"the vulnerability database changed between the runs ({db.get('before') or '?'} to {db.get('after') or '?'}), "
                     "so a dependency finding can move with no change to the code")
    lines.append(f"{against}, {before.get('date') or '?'} · {_tally_words(result['tally']['before'])} → {_tally_words(result['tally']['after'])}")
    columns = [("change", {}), ("what", {"overflow": "fold", "ratio": 3})]
    # an empty section prints heading + note and drops the caption (section_block, _md_section), so when
    # there is nothing to show, the caption's own lines fold into the note instead of vanishing with it
    note = None if rows else "; ".join(["nothing changed"] + lines)
    return _section("Since last report", columns, rows, note=note, caption="\n".join(lines))


BUILDERS = [watch_section, watch_by_component_section, size_section, people_section, knowledge_section, activity_section, timeline_section,
            hotspots_section, coupling_section, signing_section, trailers_section, lines_section, age_section, functions_section, health_section, osps_section]
# `--full` and Markdown only: Size, Activity and Code age are interesting once and rarely change what you
# do next; Hotspots ranks the files the watch list already leads with, by the same product.
FULL_ONLY = {"size", "activity", "age", "hotspots", "signing", "trailers", "lines", "watch_by_component", "osps"}


def sections(report: dict, full: bool = True, width=None) -> list:
    """Every section as a dict with an `id` (the builder's name without _section). The default terminal
    report (`full` False) leaves out the sections in FULL_ONLY (size, activity, code age and
    hotspots); `full` True and Markdown keep them."""
    out = []
    for b in BUILDERS:
        sid = b.__name__[:-len("_section")]
        if full is False and sid in FULL_ONLY:
            continue
        sec = b(report, full, width)
        sec["id"] = sid
        out.append(sec)
    return out


def secrets_line(report: dict) -> str:
    rows = report.get("secrets") or []
    groups = leaks.group(rows)
    places = sum(g["places"] for g in groups)
    line = (f"Secrets: {len(groups)} distinct value{'s' if len(groups) != 1 else ''} in {places} place{'s' if places != 1 else ''}"
            if groups else "Secrets: none found")
    skipped = leaks.placeholders(rows)
    if skipped:
        line += f"; {skipped} placeholder-shaped hit{'s' if skipped != 1 else ''} left out"
    loose = report.get("unreachable") or {}
    if loose and not loose.get("objects"):
        line += "; no unreachable objects (a fresh clone fetches only what a ref reaches)"
    elif loose.get("scanned"):
        line += f"; {loose['scanned']:,} unreachable blob{'s' if loose['scanned'] != 1 else ''} scanned too"
    return line


def secrets_pass(report: dict):
    """A check worth saying out loud when it passes: (title, detail) when the scan ran and found no
    secret value, else None. Found values are findings already; a scan that did not run says nothing."""
    rows = report.get("secrets") or []
    if not report.get("secrets_scanned") or leaks.group(rows):
        return None
    detail = "betterleaks scanned every commit HEAD reaches"
    skipped = leaks.placeholders(rows)
    if skipped:
        detail += f"; {skipped} placeholder-shaped hit{'s' if skipped != 1 else ''} left out"
    return "No secrets in history", detail


def dependencies_pass(report: dict):
    """(title, detail) when the lock files were scanned and no package has a known vulnerability, else None."""
    deps = report.get("dependencies") or {}
    if deps.get("status") != "scanned" or deps.get("vulnerable") or not deps.get("packages"):
        return None
    n = len(deps.get("sources") or [])
    detail = f"osv-scanner checked {deps['packages']:,} packages in {n} lock file{'s' if n != 1 else ''} against the local database"
    if deps.get("database_date"):
        detail += f" from {deps['database_date']}"
    return "No known vulnerabilities in dependencies", detail


def run_line(report: dict):
    """'gitmole 0.10.0 · git 2.55.0 · scc 4.1.0 · … · --ignore-data': what produced the report, from the run
    manifest; None for an output directory written before it existed. A tool without a version is left out."""
    manifest = (report.get("meta") or {}).get("run")
    if not manifest:
        return None
    parts = [f"gitmole {manifest.get('gitmole', '?')}"] + [f"{n} {v}" for n, v in (manifest.get("tools") or {}).items() if v]
    opts = manifest.get("options") or {}
    flags = [f"--ignore {g}" for g in opts.get("ignore") or []] + (["--ignore-data"] if opts.get("ignore_data") else []) + (["--deep"] if opts.get("deep") else [])
    return " · ".join(parts + ([" ".join(flags)] if flags else []))


def checks_passed(report: dict) -> list:
    """The checks that ran and passed, secrets first: said out loud rather than left to silence."""
    return [p for p in (secrets_pass(report), dependencies_pass(report)) if p]


def dependencies_line(report: dict):
    """(text, style) for the footer: what the osv-scanner step found, or why it found nothing; None
    for an output directory from before the step existed."""
    deps = report.get("dependencies") or {}
    status = deps.get("status")
    if status == "scanned":
        n = len(deps.get("sources") or [])
        bad = len(deps.get("vulnerable") or [])
        line = f"Dependencies: {deps.get('packages', 0):,} packages in {n} lock file{'s' if n != 1 else ''}, "
        line += f"{bad} vulnerable" if bad else "none vulnerable"
        if deps.get("database_date"):
            line += f" (database from {deps['database_date']})"
        return line, ("red" if bad else "green")
    if status == "no-sources":
        return "Dependencies: no lock files found", "dim"
    if status == "no-database":
        from . import deps as _deps
        return f"Dependencies: not scanned, no offline vulnerability database; run once in the clone: {deps.get('download') or _deps.DOWNLOAD}", "yellow"
    return None


# --- rich ------------------------------------------------------------------

def header(report: dict, findings: list = (), full: bool = False) -> Panel:
    s = summary(report)
    body = Text()
    body.append(f"{s['commits']} commits", style="bold")
    body.append(f"  ·  {s['first_date']} → {s['last_date']}")
    if s["since"]:
        body.append(f"  ·  since {s['since']}", style="yellow")
    body.append(f"  ·  {s['identities']} {'identity' if s['identities'] == 1 else 'identities'}"
                f"  ·  branch {s['branch']}" + (f" @ {s['commit'][:8]}" if s["commit"] else "") + "\n")
    body.append(f"{s['lines']:,} lines in {s['files']} files  ·  {', '.join(s['languages']) or 'unknown'}\n")
    if full and s["coverage"]:
        body.append(classify.coverage_line(s["coverage"]) + "\n", style="dim")
    if s["pulse"]:
        body.append("  ·  ".join(s["pulse"]) + "\n", style="dim")
    tally = textfmt.tally(list(findings))
    worst = next((f["severity"] for f in findings), None)
    body.append(tally, style=SEVERITY_STYLE.get(worst, "green"))
    return Panel(body, title=f"[bold]{s['name']}[/bold]", title_align="left", border_style="blue")


def summary_line(findings: list) -> str:
    """'7 more, true but seldom acted on: Knowledge loss, Repo health (3) and Reverts; --full lists them':
    the findings of the rules the labels found never actionable, in one line of the default report."""
    names = [g["title"] for g in textfmt.group_findings(findings)]   # a repeated title already reads "Repo health (3)"
    return f"{len(findings)} more, true but seldom acted on: {textfmt.join_and(names)}; --full lists them"


def unjudged_line(findings: list) -> str:
    """'4 more from the structure step, not labelled yet: Deep nesting and Debt in hotspots; --full lists them':
    the rules whose worth nobody has judged (findings.UNJUDGED), kept out of the default report's entries."""
    names = [g["title"] for g in textfmt.group_findings(findings)]
    return f"{len(findings)} more from the structure step, not labelled yet: {textfmt.join_and(names)}; --full lists them"


def findings_panel(findings: list, report: dict = None, full: bool = True) -> Panel:
    passed = checks_passed(report or {})
    if not findings and not passed:
        return Panel(Text("Nothing flagged.", style="green"), title="Findings", title_align="left", border_style="green")
    brief = [] if full else [f for f in findings if f.get("summary") and not f.get("unjudged")]
    unjudged = [] if full else [f for f in findings if f.get("unjudged")]
    shown = [f for f in findings if f not in brief and f not in unjudged]
    grid = Table.grid(padding=(0, 1))
    grid.add_column(no_wrap=True)
    grid.add_column(overflow="fold")
    for g in textfmt.group_findings(shown):
        style = SEVERITY_STYLE[g["severity"]]
        body = Text(g["title"], style=style)
        for item in g["items"]:
            body.append(f"\n{item}", style="dim" if len(g["items"]) == 1 else "")
        for advice in g["advice"]:
            body.append(f"\n↳ {advice}", style="dim italic")
        grid.add_row(Text(SEVERITY_MARK[g["severity"]], style=style), body)
    if brief:
        grid.add_row(Text("·", style="dim"), Text(summary_line(brief), style="dim"))
    if unjudged:
        grid.add_row(Text("·", style="dim"), Text(unjudged_line(unjudged), style="dim"))
    if passed:   # last: problems first, then the checks that passed
        if not findings:
            grid.add_row(Text(""), Text("Nothing flagged.", style="green"))
        for title, detail in passed:
            grid.add_row(Text("✔", style="green"), Text(title, style="green").append(f"\n{detail}", style="dim"))
    title = f"Findings ({len(findings)})" if findings else "Findings"
    return Panel(grid, title=title, title_align="left", border_style=SEVERITY_STYLE[findings[0]["severity"]] if findings else "green")


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
        kw = {"caption": escape(sec["caption"]), "caption_justify": "left", "caption_style": "dim italic"}   # a name like renovate[bot] is not markup
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


# small tables that sit side by side when the terminal is wide enough, by section id; a section pairs at most once
PAIRS = [("size", "people"), ("activity", "age"), ("people", "knowledge")]
PAIR_GAP = 3


def _partners(secs: list) -> dict:
    present, taken, out = {s["id"] for s in secs}, set(), {}
    for a, b in PAIRS:
        if a in present and b in present and a not in taken and b not in taken:
            out[a], out[b] = b, a
            taken.update((a, b))
    return out


def report(report: dict, findings: list, console: Console, full: bool = False, risk: dict = None, base: str = None, compare: dict = None) -> None:
    console.print(header(report, findings, full=full))
    console.print(findings_panel(findings, report, full=full))
    if compare is not None:
        print_section(console, compare_section(compare))
    secs = sections(report, full=full, width=console.width)
    by_id = {s["id"]: s for s in secs}
    partners = _partners(secs) if console.width >= SIDE_BY_SIDE_MIN_WIDTH else {}
    done = set()
    for sec in secs:
        if sec["id"] in done:
            continue
        other = partners.get(sec["id"])
        if other and other not in done:
            left, right = section_block(sec), section_block(by_id[other])
            if console.measure(left).maximum + PAIR_GAP + console.measure(right).maximum <= console.width:
                console.print(Text(""))
                console.print(Columns([left, right], padding=(0, PAIR_GAP), equal=False, expand=False))
                done.update((sec["id"], other))
                continue
        print_section(console, sec)   # stacked, with the usual blank line before it
        done.add(sec["id"])
        if risk is not None and sec["id"] == "watch":
            print_section(console, risk_section(risk, base, full))   # the change, right under the list it is scored against
    console.print(Text(""))
    console.print(Text(secrets_line(report), style="red" if leaks.group(report.get("secrets") or []) else "green"))
    deps_line = dependencies_line(report)
    if deps_line:
        console.print(Text(deps_line[0], style=deps_line[1]))
    if full and (line := run_line(report)):
        console.print(Text(line, style="dim"), soft_wrap=True)
    console.print(Text(f"Full results and plots in {report['out_dir']}", style="dim"), soft_wrap=True)


def excerpt(report: dict, findings: list, console: Console, full: bool = False) -> None:
    """The report's opening on its own: the header, whose tally counts the findings, and the watch
    list. What the README's text block shows; the findings themselves are in the full report."""
    console.print(header(report, findings))
    print_section(console, watch_section(report, full=full, width=console.width))


# --- markdown / json -------------------------------------------------------

def _md_cell(cell: str) -> str:
    return cell.replace("|", "\\|").replace("\n", " ")


def _md_findings(findings: list, report: dict = None) -> list:
    out = [] if findings else ["Nothing flagged."]
    for g in textfmt.group_findings(findings):
        line = f"- **{g['severity']}** {g['title']} — " + "; ".join(g["items"])
        line += "".join(f" _{advice}_" for advice in g["advice"])
        out.append(line)
    for title, detail in checks_passed(report or {}):
        out.append(f"- **ok** {title} — {detail}")
    return out


def _md_section(sec: dict) -> list:
    """A section's Markdown: the heading, then its table (or note), then its caption."""
    out = ["", f"## {sec['title']}", ""]
    if not sec["rows"]:
        out.append(f"_{sec['note'] or 'nothing'}_")
        return out
    out.append("| " + " | ".join(sec["columns"]) + " |")
    out.append("| " + " | ".join("---:" if o.get("justify") == "right" else "---" for o in sec["col_opts"]) + " |")
    out += ["| " + " | ".join(_md_cell(c) for c in row) + " |" for row in sec["rows"]]
    if sec.get("caption"):
        out += ["", f"_{sec['caption']}_"]
    return out


def markdown(report: dict, findings: list, full: bool = False, risk: dict = None, base: str = None, compare: dict = None) -> str:
    s = summary(report)
    out = [f"# {s['name']}", "",
           f"{s['commits']} commits · {s['first_date']} → {s['last_date']}" + (f" · since {s['since']}" if s["since"] else "")
           + f" · {s['identities']} {'identity' if s['identities'] == 1 else 'identities'} · branch {s['branch']}"
           + (f" @ {s['commit'][:8]}" if s["commit"] else "") + "  ",
           f"{s['lines']:,} lines in {s['files']} files · {', '.join(s['languages']) or 'unknown'}" + ("  " if s["coverage"] or s["pulse"] else ""),
           *([classify.coverage_line(s["coverage"]) + ("  " if s["pulse"] else "")] if s["coverage"] else []),
           *([" · ".join(s["pulse"])] if s["pulse"] else []), "",
           "## Findings", ""]
    out += _md_findings(findings, report)
    if compare is not None:
        out += _md_section(compare_section(compare))
    secs = sections(report, full=True if full else "markdown")
    if risk is not None:
        after = next((i for i, sec in enumerate(secs) if sec["id"] == "watch"), len(secs) - 1)
        secs = secs[:after + 1] + [risk_section(risk, base, full=True if full else "markdown")] + secs[after + 1:]
    for sec in secs:
        out += _md_section(sec)
    deps_line = dependencies_line(report)
    rl = run_line(report)
    out += ["", secrets_line(report) + ("  " if deps_line else ""), *([deps_line[0]] if deps_line else []), "",
            *([rl + "  "] if rl else []), f"Full results and plots in {report['out_dir']}", ""]
    return "\n".join(out)


def _envelope(out: dict) -> dict:
    """Move what differs between two runs of the same clone into `envelope`: the blame pass's measured
    projection, the machine-local output directory, the structure cache's hits, the unreachable objects
    this clone happens to hold. Everything outside it is the same bytes for the same commit and options,
    which the CI determinism job checks."""
    import copy
    out = copy.deepcopy(out)
    env = {"out_dir": out.pop("out_dir", None)}
    meta = out.get("meta") or {}
    if "path" in meta:   # where the clone sits on this machine
        env["path"] = meta.pop("path")
    for key in ("step_seconds", "step_peak_mb"):   # what each step cost on this machine, this time
        if key in meta:
            env[key] = meta.pop(key)
    age = meta.get("age")
    if isinstance(age, dict) and "projected_seconds" in age:
        env["projected_seconds"] = age.pop("projected_seconds")
    struct = out.get("structure")
    if isinstance(struct, dict) and "cached" in struct:
        env["structure_cached"] = struct.pop("cached")
    if "unreachable" in out:
        # What no ref reaches is a property of this clone's object database, not of the commit: a reflog,
        # a dropped stash, a fetch that left objects behind, whatever gc has not collected yet. Two clones
        # of one commit hold different sets, which is why the CI job comparing macOS with Linux began
        # failing on this key the day actions/checkout changed how it fetches.
        env["unreachable"] = out.pop("unreachable")
    # the value hashes use a key made for each run; the same value gets the same label within an export
    labels = {}
    if isinstance(out.get("secrets"), list):
        out["secrets"].sort(key=lambda r: (r.get("file") or "", r.get("commit") or "", r.get("line") or 0, r.get("rule") or "", r.get("fingerprint") or ""))
    for row in out.get("secrets") or []:
        if row.get("value"):
            row["value"] = labels.setdefault(row["value"], f"v{len(labels) + 1}")
    out["envelope"] = env
    return out


def dumps_json(report: dict, findings: list, risk: dict = None, compare: dict = None) -> str:
    """The --json export as text: keys sorted, the run-specific values in `envelope`."""
    return json.dumps(_envelope(to_json(report, findings, risk=risk, compare=compare)), indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def to_json(report: dict, findings: list, risk: dict = None, compare: dict = None) -> dict:
    out = {**{k: v for k, v in report.items() if k != "backtest"}, "findings": findings,   # the sub-report is a report of its own
           "watch": [{k: v for k, v in r.items() if k != "function"} | {"function": r["function"]["function"] if r["function"] else None}
                     for r in watch.risks(report)[:WATCH_FULL]]}
    out["watch_by_component"] = [{"component": g["component"], "share": round(g["share"], 3), "files": [x["file"] for x in g["files"]]}
                                 for g in watch.by_component(watch.risks(report))]
    from . import osps
    out["osps"] = {"baseline": osps.BASELINE, "controls": osps.coverage(report, findings)}
    bt = watch.backtest(report)
    if bt is not None:
        out["watch_backtest"] = bt
    if risk is not None:
        out["change_risk"] = risk
    if compare is not None:
        out["compare"] = compare
    return out


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
        rows.append((name, s["commits"], s["identities"], bus, len(leaks.group(rep.get("secrets") or [])), f"{s['lines']:,}", worst))
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
        out += _md_findings(found, rep)
    return "\n".join(out) + "\n"


def portfolio_json(owner: str, reports: list) -> dict:
    return {"owner": owner, "repos": [{"name": n, "summary": summary(r), "findings": f, "out_dir": r["out_dir"]} for n, r, f in reports]}

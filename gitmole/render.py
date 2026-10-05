"""Turn a loaded report into sections, then draw them with rich or as Markdown/JSON.

The default report is the tighter one: the columns you actually read, capped rows, elided
paths. `full` restores every column and row (Markdown export is always full)."""
from __future__ import annotations

import json
import os

from rich import box
from rich.columns import Columns
from rich.console import Console, Group
from rich.markup import escape
from rich.padding import Padding
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from . import classify, coupling, deps, filetypes, hotspots, identity, knowledge, leaks, loss, provenance, scope, textfmt, trend, watch

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
           "Change risk": "◈", "Since last report": "⇄", "Most-changed documents": "✎"}
# the one column to read first in each table; the rest are dimmed
# keyed on the head as printed: "changes", "together" and "complexity" are the report's words for what the JSON calls revs, degree and ccn
KEY_METRIC = {"Size by language": "code", "People": "commits", "Hotspots": "changes", "Change coupling": "together",
              "Knowledge map": "lines added", "Surviving code by year written": "lines", "Net lines added by year": "net lines",
              "Paths in history by year last changed": "paths", "Activity": "commits", "Portfolio": "commits", "Complex functions": "complexity",
              "Watch list": "why", "Change risk": "risk", "Most-changed documents": "changes"}
SEVERITY_MARK = {"critical": "✖", "warning": "▲", "info": "●"}
RIGHT = {"justify": "right"}
FOLD = {"overflow": "fold"}
PATH = {"overflow": "fold", "no_wrap": False, "kind": "path"}   # "kind" (and "spare") are fit()'s, not rich's

# rows shown by default; `full` lifts the caps. Markdown gets a looser cap of its own. Hotspots has
# no entry: it is `--full`/Markdown only now, so its row count is never decided by this table.
CAPS = {"Most-changed documents": 5, "People": 6, "Change coupling": 5, "Knowledge map": 6, "Size by language": 8, "Timeline": 8, "Complex functions": 8}
MARKDOWN_CAP = 50
# The default report's rows about a person need this many commits, the rest are counted in "and N more": the
# floor the coupling table and the sum of coupling already use for "enough commits to say anything" (five
# shared revisions). Absolute, since a share of the commits would cut rows on a large repository that a
# reader came for; and never fewer than ROWS_KEPT rows, so a three-person repository still shows its people.
ROW_MIN_COMMITS = 5
ROWS_KEPT = 3
TREND_TOP = 10   # the trend step's own --top default: only those files have samples
WATCH_CAP = 5   # the watch list is a short list by design; `full` and Markdown get a longer one, never all files
WATCH_FULL = watch.WATCH_TOP   # tied to watch's own cap: the --compare before side is sliced by what to_json wrote


WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def _pct(part, whole) -> str:
    return f"{100 * part / whole:.0f}%" if whole else "-"


def _bar(part, whole, width=30) -> str:
    return "█" * int(width * part / whole) if whole else ""


def _number(c) -> str:
    """A cell as text: a count takes its thousands separator here, once for every table, so 1061 commits in
    People and 18647 in the header no longer sit beside 357,025 lines (prometheus). Zero is 0. A year, a
    line number or anything else that is not a count reaches a table as text already."""
    return f"{c:,}" if isinstance(c, int) and not isinstance(c, bool) else str(c)


def _section(title, columns, rows, note=None, caption=None) -> dict:
    """columns: list of (name, rich column options). rows: lists of cells, a count as an int (see _number)."""
    return {"title": title, "columns": [c[0] for c in columns], "col_opts": [c[1] for c in columns],
            "rows": [[_number(c) for c in r] for r in rows], "note": note, "caption": caption}


def _limit(title: str, full, cap=None):
    """How many rows to keep: None for all. `full` may be False (terminal default), True, or 'markdown'.
    An explicit `cap` is the section's own cap and holds for Markdown too."""
    if full is True:
        return None
    if cap is not None:
        return cap
    return MARKDOWN_CAP if full == "markdown" else CAPS.get(title)


def _more(total: int, limit) -> str:
    return f"and {total - limit:,} more" if limit is not None and total > limit else None


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
    note = f"{hidden:,} {noun if hidden == 1 else plural or noun + 's'} hidden{HIDDEN_SUFFIX}" if hidden else None
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
    return kept, (f"{hidden:,} release pair{'s' if hidden != 1 else ''} hidden{HIDDEN_SUFFIX}" if hidden else None)


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
    return kept, (f"{hidden:,} example pair{'s' if hidden != 1 else ''} hidden{HIDDEN_SUFFIX}" if hidden else None)


def _hide_header_pairs(pairs: list, full) -> tuple:
    """A C-family source file and its own header change together by construction."""
    if full is True:
        return pairs, None
    kept = [p for p in pairs if not filetypes.is_header_pair(p["entity"], p["coupled"])]
    hidden = len(pairs) - len(kept)
    return kept, (f"{hidden:,} header pair{'s' if hidden != 1 else ''} hidden{HIDDEN_SUFFIX}" if hidden else None)


def _hide_locale_pairs(pairs: list, full) -> tuple:
    """Coupled pairs where both files are translations (filetypes.is_locale_path): a message added in one
    locale is added in all of them, so they change together by construction. A locale paired with the code
    that uses it stays."""
    if full is True:
        return pairs, None
    kept = [p for p in pairs if not (filetypes.is_locale_path(p["entity"]) and filetypes.is_locale_path(p["coupled"]))]
    hidden = len(pairs) - len(kept)
    return kept, (f"{hidden:,} locale pair{'s' if hidden != 1 else ''} hidden{HIDDEN_SUFFIX}" if hidden else None)


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
    return kept, (f"{hidden:,} deleted file{'s' if hidden != 1 else ''} hidden{HIDDEN_SUFFIX}" if hidden else None)


def _hide_gone(pairs: list, report: dict, full, classifier=None) -> tuple:
    """Drop coupled pairs where either file is no longer in the tree, unless `full` is True: they
    describe a layout that no longer exists. Returns (pairs, note) like _hide_tests."""
    if full is True:
        return pairs, None
    cls = classifier or classify.Classifier(report or {})
    kept = [p for p in pairs if not (cls.excluded(p["entity"], {"not in the tree"}) or cls.excluded(p["coupled"], {"not in the tree"}))]
    hidden = len(pairs) - len(kept)
    return kept, (f"{hidden:,} historical pair{'s' if hidden != 1 else ''} hidden; --full shows them" if hidden else None)


def _empty_note(base, hidden_note, source_base=None) -> str:
    """The note that replaces a table with no rows left. When test rows were hidden the note has to
    carry the count, since the caption goes with the table, and what is left is the source rows."""
    return f"{source_base or base}; {hidden_note}" if hidden_note else base


def _keep(columns: list, rows: list, names) -> tuple:
    """Keep only the columns called `names`, in the given order, for both header and rows."""
    index = {c[0]: i for i, c in enumerate(columns)}
    picked = [index[n] for n in names]
    return [columns[i] for i in picked], [tuple(r[i] for i in picked) for r in rows]


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
        "scope": scope.of(m),   # --path's directories; [] for the whole repository
        "pulse": pulse(report),
        "coverage": m.get("coverage") or {},
        "commit": (m.get("run") or {}).get("commit"),
    }


# The steps every table leans on, by what the reader loses without them. The optional steps (code age,
# functions, trend, backtest) say so in their own sections; the structure step has none, so pulse names it.
CORE_STEPS = {"scc": "size", "git-log": "change log", "change analysis": "change analysis",
              "betterleaks": "secrets scan", "osv-scanner": "dependency scan"}


# "cancelled" is kept for completeness, though an interrupted run never records its steps; "planned" is what
# an interrupted run leaves on an optional step's own status, which is a step that did not complete.
STEP_WORDS = {"timeout": "timed out", "failed": "failed", "skipped": "skipped", "cancelled": "cancelled", "planned": "did not complete"}


def _step_phrase(label: str, status: str) -> str:
    return f"{label} {STEP_WORDS.get(status, status)}"


def _structure_status(report: dict) -> str:
    """What the structure step's rules would find: the run's own status for the step, and "run" only if the
    step also left a readable structure.json that says so — the field the eight rules key on (findings._structure),
    so the header never vouches for checks the rules did not make."""
    planned = report["meta"].get("structure")
    if not planned:
        return "run"   # an output directory from before the step existed: nothing was promised, nothing to say
    status = planned.get("status", "run")
    if status == "run" and "structure" in report and (report["structure"] or {}).get("status") != "run":
        status = (report["structure"] or {}).get("status") or "failed"   # the step said run, its file does not: the rules found nothing
    return status


def _unfinished(report: dict) -> list:
    """The steps a missing table came from, first on the header's pulse line so a reader knows the numbers
    after them may be missing. The structure step has no section of its own, so its eight rules going missing
    shows here too — but not a skip, which is the interpreter's (Python before 3.10 has no grammars): that is
    recorded only in meta.json (structure.install), and a header phrase that differs by Python version would make one
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
    days = act.get("by_weekday") or []   # the busiest weekday and hour are the Activity table's (--full), not a header phrase
    total = sum(days)
    if act.get("fix_commits") is not None and total:
        out.append(f"{_pct(act['fix_commits'], total)} of commits are fixes")
    if act.get("revert_commits") and total:
        pct = _pct(act['revert_commits'], total)
        if pct == "0%":
            reverts = act['revert_commits']
            out.append(textfmt.count(reverts, "revert"))
        else:
            out.append(f"{pct} of commits are reverts")
    cohorts = report.get("cohorts") or {}
    if cohorts:
        label, lines = max(cohorts.items(), key=lambda kv: kv[1])
        out.append(f"{_pct(lines, sum(cohorts.values()))} of surviving code from {label.replace('Code added in ', '')}{_by_source(report)}")
    elif _age_status(report) != "run":
        out.append(_age_reason(report))   # the age table is --full only, so this is where a timeout shows
    signed = signing_phrase(report)
    if signed:
        out.append(signed)
    return out


SURVIVING_SOURCES = {"blame": "blame", "survival": "git-of-theseus"}


def surviving_source(report: dict):
    """Which step the surviving-code figures came from: "blame" (gitmole's own pass, one git blame per file at
    HEAD), "survival" (git-of-theseus, which --plots runs after it into the same two files, sampling the
    history) or None for an output directory that records neither. prometheus read 23% from 2026 with Julien
    Pivotto's the largest share in the default run and 24% with Bartlomiej Plotka's under --plots, and nothing
    on either report said the two were different measurements."""
    meta = report.get("meta") or {}
    steps = meta.get("steps") or {}
    if steps.get("git-of-theseus") == "run":
        return "survival"
    if (meta.get("age") or {}).get("method") == "blame" or steps.get("code age") == "run":
        return "blame"
    return None


def _by_source(report: dict) -> str:
    """', by blame' or ', by git-of-theseus', after a surviving-code figure; '' when the run does not say."""
    source = surviving_source(report)
    return f", by {SURVIVING_SOURCES[source]}" if source else ""


def plots_written(report: dict) -> bool:
    """Whether the output directory holds a plot: the two .png files only --plots draws (run.plan). The last
    line named plots on every run, and prometheus's default directory has none."""
    try:
        return any(name.endswith(".png") for name in os.listdir(report.get("out_dir") or ""))
    except OSError:
        return False


def results_line(report: dict) -> str:
    """The report's last line: where the output directory is, naming plots only when some were written."""
    return f"Full results{' and plots' if plots_written(report) else ''} in {report['out_dir']}"


def signing_phrase(report: dict):
    """'33% of commits signed (ssh 28%, gpg 6%), 50% of the last year's', or 'no commits signed'; None
    without the step. Read from the commit objects, nothing verified: evidence, not a level. When the
    forge committed and signed some of them itself (a merge from the web), those are named apart: its
    signature says nothing about who wrote the change."""
    sig = report.get("signing") or {}
    if not sig.get("commits"):
        return None
    if not sig.get("signed"):
        return "no commits signed"
    forge = sig.get("forge") or {}
    by_forge, forge_mix = forge.get("signed") or 0, forge.get("mechanisms") or {}
    last = sig.get("last_year") or {}
    own = sig["signed"] - by_forge
    mechanisms = {k: v - forge_mix.get(k, 0) for k, v in (sig.get("mechanisms") or {}).items()} if by_forge else (sig.get("mechanisms") or {})
    mix = ", ".join(f"{k} {_pct(v, sig['commits'])}" for k, v in sorted(mechanisms.items(), key=lambda kv: (-kv[1], kv[0])) if v > 0)
    tail = f", {_pct(last['signed'] - (last.get('forge_signed') or 0) if by_forge else last['signed'], last['commits'])} of the last year's" if last.get("commits") else ""
    if not by_forge:
        return f"{_pct(sig['signed'], sig['commits'])} of commits signed ({mix}){tail}"
    head = f"{_pct(own, sig['commits'])} of commits signed by their authors ({mix}){tail}" if own else "no commits signed by their authors"
    share = _pct(by_forge, sig['commits'])
    return head if share == "0%" else f"{head}; {share} signed by the forge on merge"


def _age_status(report: dict) -> str:
    return (report["meta"].get("age") or {}).get("status", "run")


def _age_reason(report: dict) -> str:
    return _step_phrase("code age", _age_status(report))


def _p_words(p: float) -> str:
    if p < 0.001:
        return "p < 0.001"
    shown = f"{p:.2g}"
    if (p < watch.CHANCE_ALPHA) != (float(shown) < watch.CHANCE_ALPHA):   # rounding must not carry p across the line
        shown = f"{p:.3g}"
    return f"p = {shown}"


def backtest_words(bt: dict) -> str:
    """The backtest in one sentence, every count out of the same pool: the files that had changed more
    than once by the cut-off, of which `positives` were fixed after it. Then what the numbers mean, in
    words: against the same number of most-changed files, and against a random pick, by the one-sided
    hypergeometric test at 5% (watch.p_by_chance). A backtest from before `positives` was recorded
    says the old sentence rather than guess."""
    n, k, churn = bt["listed"], bt["hits"], bt["baselines"]["churn"]
    if "positives" not in bt:
        return (f"6 months ago this list would have named {k:,} of the {bt['fixed']:,} files fixed since "
                f"(a random {n} of the {bt['pool']:,} files that had changed more than once would name {bt['expected']}; "
                f"the {n} most changed would name {churn:,})")
    if not bt["positives"]:
        return (f"none of the {bt['fixed']:,} files fixed since the cut-off 6 months ago had changed more than once by then, "
                f"so there is nothing to score the list against")
    p = bt.get("p_by_chance")
    p = watch.p_by_chance(bt["pool"], bt["positives"], n, k) if p is None else p
    versus = (f"fewer than the {n} most changed ({churn})" if k < churn else f"no more than the {n} most changed" if k == churn
              else f"more than the {n} most changed ({churn})")
    chance = (f"not distinguishable from a random {n}" if p >= watch.CHANCE_ALPHA else f"more than a random {n} would by chance")
    return (f"6 months ago this list's top {n} would have named {k:,} of the {bt['positives']:,} file{'s' if bt['positives'] != 1 else ''} fixed since among the "
            f"{bt['pool']:,} that had changed more than once: {versus}; {chance} ({bt['expected']} expected, {_p_words(p)})")


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
    notes = ["ranked by changes × lines of code alone; the reasons say what to look at there" + (f"; commits since {since}" if since else "")]
    bt = watch.backtest(report)
    status = report["meta"].get("backtest") or {}
    if bt and not bt["fixed"]:
        notes.append("nothing has been fixed since the cut-off 6 months ago, so there is nothing to score the list against")
    elif bt:
        notes.append(backtest_words(bt) + ("; whole history" if since else ""))   # the backtest ignores the window
    elif status.get("reason"):
        notes.append(status["reason"])
    elif status.get("status") in ("failed", "timeout"):
        notes.append(f"backtest {status['status']}")
    left_out = sweeps_note(report)
    if left_out:
        notes.append(left_out)
    caption = "\n".join(notes)
    return _section("Watch list", columns, rows, note=None if rows else watch.why_empty(report), caption=caption if rows else None)


def scored_phrase(report: dict):
    """'17 of 227 files scored', when the files no table carries outnumber the scored ones (classify.unseen)
    or hold more lines (classify.unranked); None otherwise. It opens the header's coverage line when there is
    one and otherwise closes the tally, a line that is already there and always short: curl's 1,095 files of
    other types against 581 scored cost its report no line."""
    cov = report.get("coverage") or {}
    files = cov.get("files") or {}
    if not files or not (cov.get("unranked") or classify.unseen(files)):
        return None
    return f"{files.get('scored', 0):,} of {sum(files.values()):,} files scored"


def coverage_phrases(report: dict) -> list:
    """What the header adds when the files the type filter left out hold more lines than the scored ones
    (classify.unranked): what share of the tree's lines is documentation or other types nothing ranks, and how
    many commits, and fixes, changed only files that are not scored. The last is the population label:
    "N% of commits are fixes" is over every commit, the bug magnets over scored files. [] otherwise, which
    is most repositories."""
    cov = report.get("coverage") or {}
    if not cov.get("unranked"):
        return []
    lines = cov["lines"]
    out = []
    doc, other = lines["documentation"], lines["other_types"]
    what = (f"{_pct(doc, lines['tracked'])} of tracked lines are documentation, not ranked" if doc >= other
            else f"{_pct(doc + other, lines['tracked'])} of tracked lines are in file types that are not ranked")
    out += [what, "--file-types all includes them"]   # two facts: together they are longer than an 80-column header line
    c = cov.get("commits") or {}
    if c.get("commits"):
        fixes = f" and {_pct(c['fixes_outside'], c['fixes'])} of fixes" if c.get("fixes") else ""
        out.append(f"{_pct(c['outside'], c['commits'])} of commits{fixes} change only unscored files")
    return out


def documents_section(report: dict, full: bool = True, width=None):
    """The most-revised documents, when documentation is most of the tree's lines and none of it is ranked:
    a count from the log, not a score, a ranking claim or a finding. None otherwise, and no section."""
    docs = (report.get("coverage") or {}).get("documents") or []
    if not docs:
        return None
    limit = _limit("Most-changed documents", full)
    rows = [(d["file"], d["revisions"]) for d in docs[:limit]]
    since = report["meta"].get("since")
    notes = ["by changes alone: documentation is not scored, so this says where it changed most, not where a fix is likely"
             + (f"; commits since {since}" if since else "")]
    return _section("Most-changed documents", [("document", PATH), ("changes", RIGHT)], rows, caption="\n".join(notes))


def not_computed_line(report: dict):
    """'truck factor not computed: 17 source files, needs 20', or None: the measures that have no section of
    their own to say why they are missing. The backtest's reason stays under the watch list it would judge."""
    from . import findings
    parts = [f"{a['label']} not computed: {a['reason']}" for a in findings.not_computed(report) if not a.get("said")]
    return "; ".join(parts) or None


def sweeps_note(report: dict):
    """'2 sweeping commits and 3 declared in .git-blame-ignore-revs are left out of every count', or
    None when the change analysis left nothing out (or predates the record)."""
    act = report.get("activity") or {}
    swept, declared = [c for c in act.get("sweeping") or [] if not c.get("declared")], act.get("ignored_revs") or 0
    parts = []
    if swept:
        parts.append(textfmt.count(len(swept), "sweeping commit"))
    if declared:
        parts.append(f"{declared:,} declared in .git-blame-ignore-revs")
    if not parts:
        return None
    return " and ".join(parts) + (" are" if swept and declared or len(swept) > 1 or declared > 1 else " is") + " left out of every count"


RISK_CAP = 15


def risk_section(risk: dict, base: str, full=True) -> dict:
    """The files a change touches, each with its watch score as a bar scaled to the repo's worst file."""
    rows_all = risk["files"]
    limit = _limit("Change risk", full, cap=RISK_CAP)
    top = risk["max_score"] or 1.0
    rows = []
    for r in rows_all[:limit]:
        imported = watch.dependents_phrase(r.get("dependents"))
        rows.append((r["file"], "▰" * round(10 * r["score"] / top) if r["score"] else "", " · ".join(r["reasons"] + ([imported] if imported else []))))
    columns = [("file", PATH), ("risk", {}), ("why", {"overflow": "fold", "ratio": 3})]
    watched = risk["watched"]
    notes = [f"total {risk['total']:.1f}% of the repository's changes × lines of code; "
             f"{watched:,} of these files {'is' if watched == 1 else 'are'} on the watch list"] if rows else []
    more = _more(len(rows_all), limit)
    if more:
        notes.append(more)
    factors = (risk.get("change") or {}).get("reasons") or []
    if rows and factors:
        notes.append("; ".join(factors))
    gaps = risk.get("coupling_gaps") or []
    if rows and gaps:
        notes.append(gaps_line(gaps))
    return _section(f"Change risk ({len(rows_all):,} files since {base})", columns, rows,
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


def _tools_left_out(report: dict, tools: set) -> str:
    """'3 coding-tool names left out (7 with aliases, sharing 1 no-reply address, 32 commits)': what the rows
    kept out of the People table are, counted as what git records. They are names, and several names on one
    vendor address are one assistant signing each model version differently, so "4 coding tools" for four rows
    on one address counted spellings as tools. The first number is the rows left out, which is what the export's
    `tools.names` holds and what the table's count is short by; every spelling, the ones merged into a row too,
    is the number with aliases, said only when it differs. prometheus's caption gave the 7 alone, beside a JSON
    key holding 3 names and 32 commits, and the two could not be told to be one fact. The commits are the
    export's `tools.commits`. The same sentence in the default report, --full and Markdown."""
    rows, names, addresses = 0, set(), set()
    for i in report["meta"].get("identities") or []:
        if i["name"] in tools:
            rows += 1
            for v in [i, *(i.get("aliases") or [])]:
                names.add(v.get("name"))
                if identity.NO_REPLY_MAILBOX.match(v.get("email") or ""):
                    addresses.add(v["email"].lower())
    commits = (report.get("tools") or {}).get("commits")
    detail = [f"{len(names):,} with aliases"] if len(names) != rows else []
    if addresses:
        detail.append(f"{'sharing ' if rows > 1 or len(names) > 1 else 'on '}{textfmt.count(len(addresses), 'no-reply address', 'no-reply addresses')}")
    if commits:
        detail.append(textfmt.count(commits, "commit"))
    return f"{textfmt.count(rows, 'coding-tool name')} left out" + (f" ({', '.join(detail)})" if detail else "")


def people_section(report: dict, full: bool = True, width=None) -> dict:
    tools = set((report.get("tools") or {}).get("names") or [])   # load.py keeps them out of the tables about people
    ids = [i for i in report["meta"].get("identities") or [] if i["name"] not in tools]
    apart = len(tools & {i["name"] for i in report["meta"].get("identities") or []})
    merges = any(i.get("merges") for i in ids)   # merges apart: merging every pull request is not writing the code

    def own(i):   # the commits they authored: a Co-authored-by credit is shown apart, not as a commit of theirs
        return max(0, i.get("authored", i["commits"]) - i.get("merges", 0))

    def credit(i):
        return i["commits"] - i.get("authored", i["commits"])
    ids = sorted(ids, key=lambda i: -own(i)) if merges or any(credit(i) for i in ids) else ids
    total_commits = sum(own(i) for i in ids)
    surviving = report.get("theseus_authors") or {}
    total_lines = sum(surviving.values())
    # each row's own lines, by its name and address; a report built without them reads by name
    mine = report.get("surviving_by_identity")
    lines_of = (lambda i: mine.get(identity.row_label(i), 0)) if mine is not None else (lambda i: surviving.get(i["name"], 0))
    limit = _limit("People", full)
    listed = ids[:limit]
    if full is False:   # a row for two commits says little: under the floor they are counted, not listed
        listed = [i for n, i in enumerate(listed) if n < ROWS_KEPT or own(i) >= ROW_MIN_COMMITS]
    credited = any(credit(i) for i in listed)   # a column only when a row shown has any
    # No address in any rendering, at any width: the Markdown is what the README says to post to a public job
    # summary, and prometheus's --full printed 1,324 addresses beside commit counts. The JSON keeps them, under
    # meta.identities, for whoever has the clone anyway.
    rows = [(i["name"], own(i), *((i.get("merges", 0),) if merges else ()), *((credit(i),) if credited else ()),
             _pct(own(i), total_commits), _pct(lines_of(i), total_lines)) for i in listed]
    columns = [("author", {}), ("commits", RIGHT), *((("merges", RIGHT),) if merges else ()),
               *((("co-authored", RIGHT),) if credited else ()), ("share", RIGHT), ("surviving code", RIGHT)]
    since = report["meta"].get("since")
    by = _by_source(report) if total_lines else ""   # the source of the column, said where the column is: the two steps give different shares
    notes = [f"commits since {since}; surviving code is for the whole tree{by}"] if since else []
    if merges:
        notes.append(f"commits and share leave out merges, which are counted apart ({sum(i.get('merges', 0) for i in ids):,} in all)")
    more = f"and {len(ids) - len(listed):,} more" if len(ids) > len(listed) else None
    left = _tools_left_out(report, tools) if apart else None
    if more or left:
        notes.append("; ".join(x for x in (more, left) if x))
    bots = report["meta"].get("bots") or []
    if bots:
        notes.append("bots left out: " + ", ".join(f"{b['name']} ({b['commits']:,}{' commits' if i == 0 else ''})" for i, b in enumerate(bots[:3]))
                     + (f" and {len(bots) - 3:,} more" if len(bots) > 3 else ""))
    merged = [i["name"] for i in ids if i.get("aliases")]
    if merged:
        who = ", ".join(merged[:3]) + (f" and {len(merged) - 3:,} more" if len(merged) > 3 else "")
        notes.append(f"aliases merged for {who}; a .mailmap makes that permanent")
    if by and not since:
        notes.append(f"surviving code is counted{by[1:]}")
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
        notes.append(f"busiest hour {h:02d}:00 ({hours[h]:,} commits)")
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
    """Commits each person authored, one column per month. Names never fold: when the year does not fit the
    terminal width, the oldest months are dropped (down to FLOOR) instead. If a name is still too long
    for the room FLOOR leaves, the name gives way, not the months: it is shown cut with an ellipsis
    (never fewer than NAME_FLOOR characters), so the months a reader came for stay full width. The
    title names the months actually shown; ranking, bots filtering and the row's key are all still the
    real name, only the displayed cell is cut. With no width (the Markdown export) nothing is trimmed."""
    tl = (report.get("activity") or {}).get("timeline") or {}
    if not tl:
        return _section("Timeline", [("author", {})], [], note="no timeline data")
    last = max(m for per in tl.values() for m in per)
    first = min(m for per in tl.values() for m in per)
    span = [m for m in _month_range(last, months) if m >= first]   # no columns for months before the history began
    since = report["meta"].get("since")
    if since:
        span = [m for m in span if m >= since[:7]] or span[-1:]
    # the run decided who is a bot from name and email; the timeline only has the name, so it asks the run
    bots = {b["name"] for b in report["meta"].get("bots") or []}
    # an older run counted a Co-authored-by credit here as a commit; a person with no commit of their own is not listed
    credit_only = {n for n, a in ((report.get("activity") or {}).get("authors") or {}).items() if a.get("authored", 1) == 0}

    def active(shown):
        """Who to list and in what order: commits inside the months actually shown, most first."""
        totals = {a: sum(per.get(m, 0) for m in shown) for a, per in tl.items()}
        return [a for a in sorted(totals, key=lambda a: -totals[a])
                if totals[a] > 0 and a not in bots and a not in credit_only and not identity.is_bot(a)]

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
    listed = ranked[:limit]
    if full is False:   # as the People table: a row needs ROW_MIN_COMMITS commits in the months shown, the top ROWS_KEPT stay
        listed = [a for n, a in enumerate(listed) if n < ROWS_KEPT or sum(tl[a].get(m, 0) for m in span) >= ROW_MIN_COMMITS]
    # a month without a commit is 0, as zero is in every table: the dot it used to be is the report's separator
    rows = [(textfmt.cut(a, max(NAME_FLOOR, room)) if width else a, *[tl[a].get(m) or 0 for m in span]) for a in listed]
    months_shown = _month_label(span[0]) if len(span) == 1 else f"{_month_label(span[0])} → {_month_label(span[-1])}"
    return _section(f"Timeline ({months_shown})", columns, rows, caption=f"and {len(ranked) - len(listed):,} more" if len(ranked) > len(listed) else None)


def signing_section(report: dict, full: bool = True, width=None) -> dict:
    """Signed commits per year, from the gpgsig headers: --full and Markdown only. Humans against bots as two
    totals and no rate per person: prometheus's caption ranked four named people by how often they sign, a
    score of a person, which the project's own rule keeps out of every report (the export keeps `by_identity`)."""
    sig = report.get("signing") or {}
    columns = [("year", {}), ("commits", RIGHT), ("signed", RIGHT), ("share", RIGHT)]
    if not sig.get("commits"):
        return _section("Signing by year", columns, [], note="no signing data")
    rows = [(year, y["commits"], y["signed"], _pct(y["signed"], y["commits"])) for year, y in sorted((sig.get("by_year") or {}).items())]
    humans, bots = sig.get("humans") or {}, sig.get("bots") or {}
    parts = []
    if humans.get("commits"):
        parts.append(f"humans {_pct(humans['signed'], humans['commits'])} signed" + (f", bots {_pct(bots['signed'], bots['commits'])}" if bots.get("commits") else ""))
    forge = sig.get("forge") or {}
    if forge.get("signed"):
        parts.append(f"{forge['signed']:,} of the signed commits were committed and signed by the forge on merge, not by their authors")
    parts.append("read from the commit objects, nothing verified")
    return _section("Signing by year", columns, rows, caption="; ".join(parts))


def watch_by_component_section(report: dict, full: bool = True, width=None) -> dict:
    """The watch list's top files within each component: --full and Markdown only."""
    groups = watch.by_component(watch.risks(report), base=scope.report_base(report))
    rows = [(g["component"], f"{g['share']:.0f}%", " · ".join(x["file"] for x in g["files"]))
            for g in groups]
    columns = [("component", PATH), ("share", RIGHT), ("top files", {"overflow": "fold", "ratio": 3})]
    return _section("Watch list by component", columns, rows, note=None if rows else "no component holds 5% of the list's score",
                    caption="each component's share of the watch list's changes × lines of code, and its own top files" if rows else None)


def trailers_section(report: dict, full: bool = True, width=None) -> dict:
    """The trailer keys the history carries, with the cohort comparison and the neutral commit-shape
    descriptors below: --full and Markdown only. Read, never inferred; nothing is labelled."""
    prov = report.get("provenance") or {}
    tr, co, sh = prov.get("trailers") or {}, prov.get("cohort") or {}, prov.get("shape") or {}
    columns = [("trailer", {}), ("commits", RIGHT), ("share", RIGHT)]
    total = tr.get("commits") or 0
    rows = [(k, min(n, total) if total else n, _pct(min(n, total), total)) for k, n in provenance.fold_keys(tr.get("keys") or {}).items()]
    notes = []
    marked, rest = co.get("cohort") or {}, co.get("rest") or {}
    if marked.get("commits"):
        def pair(key):
            return f"{_pct(marked.get(key, 0), marked['commits'])} against {_pct(rest.get(key, 0), rest.get('commits') or 0)}"
        watch_part = f", touched a file on the watch list's top {co['watch_top']} {pair('watch')}" if co.get("watch_top") else ""
        notes.append(f"declared commits ({co.get('definition')}): {marked['commits']:,}, {round(100 * co.get('share', 0))}% of the history; "
                     f"reverted {pair('reverted')} for the rest (every commit that declares nothing, undisclosed agent use included), fixes {pair('fixes')}, a file changed again within 2 weeks {pair('retouched')}{watch_part}")
    if sh:
        notes.append(f"{round(100 * sh.get('burst_share', 0))}% of commits land in bursts of 5 or more within 10 minutes; "
                     f"{round(100 * sh.get('conventional_share', 0))}% have conventional-commit subjects; commits come in {sh.get('hours_used', 0)} hours of the day")
    return _section("Trailers", columns, rows, note=None if rows else "no trailers", caption="\n".join(notes) or None)


def lines_section(report: dict, full: bool = True, width=None) -> dict:
    """Lines added to code files in the last year and the year before, the share git marks as moved and
    the share deleted again within two weeks, and the same for the declared commits against the rest (which is not
    "humans": it holds any agent use nobody declared):
    --full and Markdown only. A direction for this repository, not a score."""
    ln = (report.get("provenance") or {}).get("lines") or {}

    def share(x):
        return "-" if x is None else f"{100 * x:.1f}%"
    rows = [(f"{w['label']} ({w['from']} to {w['to']})", w["commits"], w["added"], share(w.get("moved_share")), share(w.get("churn_share")))
            for w in ln.get("windows") or []]
    co = ln.get("cohort") or {}
    if (co.get("marked") or {}).get("commits"):
        rows += [(label, c["commits"], c["added"], share(c.get("moved_share")), share(c.get("churn_share")))
                 for label, c in (("declared commits, both years", co["marked"]), ("the rest, both years", co["rest"]))]
    columns = [("period", {"overflow": "fold"}), ("commits", RIGHT), ("lines added", RIGHT), ("moved", RIGHT), (f"churned in {ln.get('churn_days', 14)} days", RIGHT)]
    return _section("Changed lines", columns, rows, note=None if rows else "no history in the last 2 years",
                    caption="code files only; moved: lines git's moved-code detection marks (--color-moved=blocks); churned: deleted again "
                            "within 2 weeks from the same file with the same text"
                            + ("; the rest is every commit that declares no coding tool, undisclosed agent use included" if (co.get("marked") or {}).get("commits") else "")
                    if rows else None)


def hotspots_section(report: dict, full: bool = True, width=None) -> dict:
    """Change frequency times size, Tornhill-style. Drawn under `--full` and in the Markdown export
    only; the default terminal report leaves it to the watch list, which ranks the same files. Built
    only for those two, it has no row cap of its own outside Markdown's. Files no longer in the tree
    have nothing to score: Markdown hides them like any hidden row, `--full` counts them in one line."""
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
    removed_note = None
    tracked = report.get("tree") or (report.get("size") or {}).get("files") or {}
    if full is True and tracked:
        # --full hides nothing, but a file that is no longer tracked has no lines, no complexity and no score:
        # its row is three dashes. superpowers spent 412 of 483 rows on them, 318 from an import later removed.
        removed = [h for h in scored if h["code"] is None and h["entity"] not in tracked]
        if removed:
            scored = [h for h in scored if not (h["code"] is None and h["entity"] not in tracked)]
            imported = report.get("imported") or ()
            brought = sum(1 for h in removed if h["entity"] in imported)
            removed_note = (f"{len(removed):,} removed file{'s' if len(removed) != 1 else ''} not listed"
                            + (f", {brought:,} from left-out imports" if brought else "") + " (maat-revisions.csv has them)")
    title = "Hotspots (score = changes × lines of code)" if full is True else "Hotspots"
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
    columns = [("file", PATH), ("changes", RIGHT), ("lines", RIGHT), ("complexity", RIGHT), ("score", RIGHT), ("fixes", RIGHT), ("authors", RIGHT),
               ("minors", RIGHT), ("co-changes", RIGHT), ("idle", RIGHT), ("trend", RIGHT)]
    if full is not True:
        columns, rows = _keep(columns, rows, ["file", "changes", "lines", "fixes", "authors", "trend"])
    note = None if rows else _empty_note(None, hidden_note, "no source hotspots")
    notes = [c for c in (_more(len(scored), limit), None if note else hidden_note, removed_note) if c]
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
    pairs, locale_note = _hide_locale_pairs(pairs, full)
    pairs, vendor_note = _hide_vendor(pairs, lambda p: (p["entity"], p["coupled"]), full, noun="vendored pair", plural="vendored pairs", report=report, classifier=cls)
    pairs, generated_note = _hide_generated(pairs, lambda p: (p["entity"], p["coupled"]), report, full, noun="generated pair", plural="generated pairs", classifier=cls)
    gone_note = _join_hidden(gone_note, release_note, example_note, header_note, locale_note, vendor_note, generated_note)
    groups, cluster_note = [], None
    if full is not True:
        # a directory whose files all change together is one row; --full lists every pair
        groups, pairs = coupling.clusters(pairs)
        if groups:
            n_pairs, n_dirs = sum(g["pairs"] for g in groups), len(groups)
            cluster_note = (f"{n_pairs:,} pairs in {n_dirs:,} director{'y' if n_dirs == 1 else 'ies'} shown as "
                            f"{'one row' if n_dirs == 1 else 'one row each'}{HIDDEN_SUFFIX}")
    hidden_note = _join_hidden(hidden_note, gone_note, cluster_note)
    limit = _limit("Change coupling", full)
    rows = [(f"{g['dir']} ({g['files']:,} files)", "each other", f"≥{g['degree']}%", g["average-revs"]) for g in groups]
    rows += [(p["entity"], p["coupled"], f"{p['degree']}%", p["average-revs"]) for p in pairs[:max(limit - len(groups), 0) if limit else None]]
    # "together" is the share of their changes the two files made in one commit, the JSON's `degree`; "avg changes" its `average-revs`
    columns = [("file", PATH), ("changes with", PATH), ("together", RIGHT), ("avg changes", RIGHT)]
    if full is not True:
        columns, rows = _keep(columns, rows, ["file", "changes with", "together"])
    note = None if rows else _empty_note("no pairs with 5 or more shared changes", hidden_note, "no source pairs with 5 or more shared changes")
    notes = [c for c in (_more(len(pairs), limit), None if note else hidden_note) if c]
    caveat = coupling.regime(report)[1]   # what a pair means here: a pull request under squash merging, an edit otherwise
    if rows and caveat:
        notes.append(caveat)
    # A table of one pair that the watch list's rows already give, with its degree, says nothing twice. Only
    # test pairs may have been hidden on the way: a count of historical or vendored pairs is said nowhere else.
    if full is False and not groups and not gone_note and len(pairs) == 1 and _watch_shows(report, pairs[0]):
        return None
    return _section("Change coupling", columns, rows, note=note, caption="; ".join(notes) or None)


def _watch_shows(report: dict, pair: dict) -> bool:
    """Whether the default watch list already prints this coupled pair: one of its files is a row shown there
    and a reason shown on that row is that it changes with the other."""
    for r in watch.risks(report)[:WATCH_CAP]:
        other = pair["coupled"] if r["file"] == pair["entity"] else pair["entity"] if r["file"] == pair["coupled"] else None
        if other and any(reason.startswith(f"changes with {other} (") for reason in r["reasons"][:watch.REASONS_SHOWN]):
            return True
    return False


def age_section(report: dict, full: bool = True, width=None) -> dict:
    cohorts = report.get("cohorts") or {}
    if not cohorts and _age_status(report) != "run":
        return age_fallback_section(report)
    total = sum(cohorts.values())
    rows = [(label.replace("Code added in ", ""), f"{lines:,}", _pct(lines, total), _bar(lines, total)) for label, lines in cohorts.items()]
    return _section("Surviving code by year written", [("year", {}), ("lines", RIGHT), ("share", RIGHT), ("", {"style": "blue"})], rows,
                    note=None if rows else "no age data", caption=f"counted{_by_source(report)[1:]}" if rows and _by_source(report) else None)


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
    # a span lizard may have mis-parsed goes after every one it did not: its complexity may be the next function's too
    funcs = sorted((f for f in measured if f["ccn"] >= CCN_FLOOR), key=lambda f: (bool(f.get("suspect")), -f["ccn"], -f["nloc"], f["file"], f["function"], f["start"]))
    funcs, hidden_note = _hide_tests(funcs, lambda f: f["file"], full, noun="function in a test file", plural="functions in test files", classifier=cls)
    funcs, vendor_note = _hide_vendor(funcs, lambda f: f["file"], full, noun="function in vendored code", plural="functions in vendored code", report=report, classifier=cls)
    funcs, sample_note = _hide_by(funcs, lambda f: f["file"], full, cls, {"example code"}, "function in example code", "functions in example code")
    funcs, generated_note = _hide_generated(funcs, lambda f: f["file"], report, full, noun="function in a generated file", plural="functions in generated files", classifier=cls)
    hidden_note = _join_hidden(hidden_note, vendor_note, sample_note, generated_note)
    limit = _limit("Complex functions", full)
    shown = funcs[:limit]
    rows = [(textfmt.ANONYMOUS if _nameless(f) else f["function"], _where(f), _ccn_cell(f), f["nloc"], f["params"]) for f in shown]
    suspects = sum(1 for f in shown if f.get("suspect"))
    suspect_note = f"{SUSPECT_MARK} marks {suspects:,} span{'s' if suspects != 1 else ''} lizard may have mis-parsed" if suspects else None
    cut = sum(1 for f in shown if f.get("lizard_span"))
    cut_note = (f"{FLOOR_MARK} marks {cut:,} function{'s' if cut != 1 else ''} lizard ended early: the lines are the structure step's, "
                f"the complexity what lizard counted before it stopped") if cut else None
    columns = [("function", {"overflow": "fold"}), ("file", PATH), ("complexity", RIGHT), ("lines", RIGHT), ("params", RIGHT)]
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
        note = _empty_note(f"nothing at complexity {CCN_FLOOR} or more {counted}", hidden_note,
                           f"nothing at complexity {CCN_FLOOR} or more in source files {counted}")
    else:
        note = None
    if rows and full is False and len(funcs) <= (limit or 0):
        from .findings import brain_rows
        if not brain_rows(report):
            # No function is both long and complex by the brain-methods rule itself, and the whole list fits the
            # table, so nothing lies behind an "and N more": one line, naming the most complex it would lead with.
            # A longer list stays a table whatever the rule says of it: gitmole's own has 166 functions at 10 or
            # over, led by one of complexity 55 in 89 lines, and no brain method.
            top = next((f for f in funcs if not f.get("suspect")), funcs[0])
            mark = "at most " if top.get("suspect") else "at least " if top.get("lizard_span") else ""
            note = (f"no long, complex functions; highest complexity {mark}{top['ccn']} "
                    f"({_where(top) if _nameless(top) else top['function']})"
                    + (f"; {partial}" if partial else "") + f"; --full lists {len(funcs):,} at {CCN_FLOOR} or more")
            rows = []
    caption = "; ".join(c for c in (_more(len(funcs), limit), None if note else hidden_note, partial, suspect_note, cut_note) if c) or None
    # the head was lizard's "ccn"; the word needs its measure said once, where the column is
    caption = "\n".join(c for c in (caption, COMPLEXITY_DEFINITION) if c)
    return _section("Complex functions", columns, rows, note=note, caption=caption if rows else None)


COMPLEXITY_DEFINITION = "complexity = cyclomatic: the function's branch points plus 1"
SUSPECT_MARK = "?"
FLOOR_MARK = "+"   # at least this: lizard counted only the part of the function it read (load.cross_check)


def _ccn_cell(f: dict):
    if f.get("suspect"):
        return f"{f['ccn']}{SUSPECT_MARK}"
    return f"{f['ccn']}{FLOOR_MARK}" if f.get("lizard_span") else f["ccn"]


def _nameless(f: dict) -> bool:
    return bool(f.get("anonymous")) or textfmt.nameless(f["function"])


def _where(f: dict) -> str:
    """A named function is found by its name in its file; a nameless one is shown as <anonymous>, so the
    row says which line."""
    return f"{f['file']}:{f['start']}" if _nameless(f) else f["file"]


def _owner_cells(area: dict, gone: set) -> list:
    """The main owner and the second of an area, as the knowledge map prints them. When several people hold
    exactly the top share there is no main owner to name and no second: the cell counts them and gives the
    share each of them holds ("shared by 12 (8%)", short enough for the column at 80), since the name the
    sort put first is the alphabet's. A second place that several hold equally is counted the same way."""
    held = area["owners"]

    def cell(at):
        if at >= len(held):
            return "-"
        level = knowledge.tied(held, at)
        name, n = held[at]
        if level > 1:
            return f"shared by {level} ({_pct(n, area['lines'])})"
        return f"{name}{' (gone)' if name in gone else ''} ({_pct(n, area['lines'])})"
    return [cell(0), "-" if knowledge.tied(held) > 1 else cell(1)]


def _declared_text(declared: dict) -> str:
    """Where the project's name was read, as the manifest writes it: package.json "name": "univer"."""
    name, path = declared["name"], declared["file"]
    if path.endswith(".json"):
        return f'{path} "{declared["field"]}": "{name}"'
    if path.endswith(".toml"):
        return f'{path} {declared["field"]} = "{name}"'
    return f"{path} {declared['field']} …/{name}"


def named_like_project(report: dict, areas: list):
    """A caption for an owner the report already names, in a knowledge-map row shown or as the one author of a
    truck-factor-one area in that finding, whose name run together is the name the root manifest gives the
    project (meta.declared): "Univer is named like the project (package.json "name": "univer"); git does not
    record whether one person or several commit under it." It says how the identity is recorded and nothing
    about who is behind it, and it changes no number; None when no owner shown is named so."""
    declared = report["meta"].get("declared") or {}
    target = identity._squash(declared.get("name") or "")
    if not target:
        return None
    named = set()
    for a in areas:
        held = a["owners"]
        if held and knowledge.tied(held, 0) == 1:
            named.add(held[0][0])
            if len(held) > 1 and knowledge.tied(held, 1) == 1:
                named.add(held[1][0])
    hit = sorted(n for n in named if identity._squash(n) == target)
    if not hit and any(identity._squash(i.get("name") or "") == target for i in report["meta"].get("identities") or []):
        from .findings import truck_factor   # only when someone is named so: the finding is not computed twice for nothing
        lone = [a["author"] for f in truck_factor(report) for a in f["evidence"].get("areas", [])[:5]]
        hit = sorted({n for n in lone if identity._squash(n) == target})
    if not hit:
        return None
    return (f"{textfmt.join_and(hit)} {'is' if len(hit) == 1 else 'are'} named like the project ({_declared_text(declared)}); "
            "git does not record whether one person or several commit under it")


def knowledge_section(report: dict, full: bool = True, width=None) -> dict:
    """Ownership by area of the tree: who wrote most of each directory, gone owners marked."""
    months = report["meta"].get("gone_months", loss.DEFAULT_MONTHS)
    gone = {g["name"] for g in loss.gone(report, months)}
    rows_all = report.get("ownership") or []   # every area the map showed before, tests included
    base = scope.report_base(report)   # a --path run's areas are the directories below the ones it names
    dated = bool(report["meta"].get("ownership_recent")) and full is True   # the change analysis counted `recent` (0.45 on)
    areas = loss.areas(rows_all, gone, base, dated)
    hidden_note = None
    tree = (report.get("size") or {}).get("files") or {}
    # the two views count different files, and tests/ at 9,568 lines here and 10,765 there read as a
    # contradiction until the heading says which: the default keeps the files HEAD still has, --full every
    # file the history (or the --since window) changed. In the heading, so the report is no line longer.
    since = report["meta"].get("since")
    counted = "files in the tree now" if full is not True and tree else f"every file in the history{f' since {since}' if since else ''}"
    if full is not True and tree:
        # a directory the history knows but HEAD does not is a layout that no longer exists; the rows are
        # filtered before the areas are built so a vanished layout cannot hide that one directory now dominates
        areas = [a for a in loss.areas(knowledge.present_rows(rows_all, tree), gone, base, dated) if knowledge.in_tree(a["area"], tree, base)]
        hidden = sum(1 for top in {knowledge.top_area(r["entity"], base) for r in rows_all} if not knowledge.in_tree(top, tree, base))
        hidden_note = f"{hidden:,} historical area{'s' if hidden != 1 else ''} hidden{HIDDEN_SUFFIX}" if hidden else None
    limit = _limit("Knowledge map", full)
    # the lines Co-authored-by trailers credit to a coding tool are not anyone's to own: the owners' shares are
    # of the people's lines, and the tools' part of each area is shown on its own
    assisted = ((report.get("tools") or {}).get("added") or {})
    if full is not True and tree:
        assisted = {e: n for e, n in assisted.items() if e in tree}
    rows, shares, outrank = [], [], False
    # how many of an area's authors committed to it in the --gone window, as "recent/all" in the authors cell: a
    # count with no names, from the change analysis of 0.45 on (meta's ownership_recent); an output directory from before has no such count,
    # and its --full map is the one it always was. In the cell, not a column of its own, so the owners keep their width
    recent = dated
    for a in areas[:limit]:
        owners = _owner_cells(a, gone)
        lost = f"{100 * a['lost_share']:.0f}%" if a["lines"] else "-"
        theirs = sum(n for e, n in assisted.items() if knowledge.in_area(e, a["area"], base))
        shares.append(round(100 * theirs / (a["lines"] + theirs)) if a["lines"] + theirs else 0)
        outrank = outrank or (theirs > 0 and theirs >= (a["owners"][1][1] if len(a["owners"]) > 1 else 0))
        authors = f"{a.get('recent', 0):,}/{a['authors']:,}" if recent else a["authors"]
        rows.append((a["area"], f"{a['lines']:,}", authors, lost if gone else "-", owners[0], owners[1], f"{shares[-1]}%"))
    columns = [("area", PATH), ("lines added", RIGHT), ("authors", RIGHT), ("lost", RIGHT), ("main owner", {}), ("second", {}), ("agents", RIGHT)]
    # a column only when a row shown has a whole percent of it; in the default report only when the tools
    # together hold as much of an area as its second owner, where naming them apart changes who is listed
    shown = any(shares) and (full is True or outrank)
    if full is not True:
        columns, rows = _keep(columns, rows, ["area", "lines added", "main owner", "second", *(["agents"] if shown else [])])
    elif not shown:
        columns, rows = _keep(columns, rows, [c[0] for c in columns[:-1]])
    notes = [c for c in (_more(len(areas), limit), hidden_note) if c]
    from .findings import imports_gone_note
    if (left := imports_gone_note(report)):   # an import that is gone is no finding: said here, where ownership is read
        notes.append(left)
    if shown:
        notes.append("agents: the lines trailers credit to coding tools, told by their no-reply address (identity.tools)")
    if rows and (left := named_like_project(report, areas[:limit])):
        notes.append(left)
    if gone:
        notes.append(f"gone = no commits in the {months} months before {report['meta'].get('last_date')}"
                     + ("; gone and lost are measured over the whole history" if report["meta"].get("since") else ""))
    if recent:
        notes.append(f"authors = recent/all; recent = a commit to the area in the {months} months before {report['meta'].get('last_date')}")
    return _section(f"Knowledge map ({counted})" if rows else "Knowledge map", columns, rows, note=None if rows else "no ownership data", caption="\n".join(notes) or None)


def osps_section(report: dict, full: bool = True, width=None) -> dict:
    """The OSPS Baseline controls a clone can show, each with its result here: --full and Markdown only."""
    from . import findings, osps
    rows = [(r["control"], r["requirement"], r["result"], r["evidence"]) for r in osps.coverage(report, findings.evaluate(report))]
    return _section("OSPS Baseline", [("control", {"no_wrap": True}), ("asks", {"overflow": "fold", "ratio": 2}), ("result", {}), ("evidence", {"overflow": "fold", "ratio": 3})],
                    rows, caption=f"the controls a clone can show evidence for, from the {osps.BASELINE}; access control and most of vulnerability management need the forge")


def agent_surface_section(report: dict, full: bool = True, width=None):
    """What the tree declares for coding agents (provenance.agents), listed and not judged: the instruction files,
    the skills by the directory that holds them, each hook command with the tracked script it runs, and the plugin
    manifests by their directory. --full and Markdown only; None, and so no section, for a tree that declares none."""
    ag = (report.get("provenance") or {}).get("agents") or {}
    rows = []
    for r in ag.get("instructions") or []:
        if r.get("kind") == "skill":
            continue   # counted with the skills below
        what = f"last changed {r['last']}, {r['commits_behind']:,} commit{'' if r['commits_behind'] == 1 else 's'} before the last"
        rows.append((r.get("kind") or "instructions", r["file"], what + (f"; points at {textfmt.join_and(r['points_to'])}" if r.get("points_to") else "")))
    skills = ag.get("skills") or {}
    homes = {}
    for path in skills.get("files") or []:
        home, name = path.rsplit("/", 2)[0], path.rsplit("/", 2)[1]
        homes.setdefault(home, []).append(name)
    listed = sum(len(v) for v in homes.values())
    for home, names in sorted(homes.items()):
        rows.append(("skills", home + "/", f"{len(names)} with a name and a description: {', '.join(names[:5])}" + (f" and {len(names) - 5} more" if len(names) > 5 else "")))
    if skills.get("count", 0) > listed:
        rows.append(("skills", "", f"and {skills['count'] - listed:,} more"))
    for h in ag.get("hooks") or []:
        chain = "".join(f" → {h[k]}" for k in ("script", "runs") if h.get(k)) or (f" (names {h['names']})" if h.get("names") else "")
        rows.append(("hook", h["file"], f"{h['event'] or 'hook'}: {h['command']}{chain}"))
    if ag.get("hooks_count", 0) > len(ag.get("hooks") or []):
        rows.append(("hook", "", f"and {ag['hooks_count'] - len(ag['hooks']):,} more"))
    plugins = {}
    for path in ag.get("plugin_manifests") or []:
        plugins.setdefault(path.split("/", 1)[0], []).append(path.split("/", 1)[1])
    rows += [("plugin manifest", home + "/", ", ".join(names)) for home, names in sorted(plugins.items())]
    if not rows:
        return None
    counts = [(sum(1 for r in ag.get("instructions") or [] if not r.get("kind")), "instruction file"), (skills.get("count", 0), "skill"),
              (ag.get("hooks_count", 0), "hook command"), (ag.get("plugin_manifests_count", len(ag.get("plugin_manifests") or [])), "plugin manifest")]
    caption = (", ".join(f"{n:,} {word}{'' if n == 1 else 's'}" for n, word in counts if n)
               + "; read from the tree by path convention and shape, listed and not judged"
               + ("; → names the tracked script a hook command runs, and the one that script hands over to" if any(h.get("script") for h in ag.get("hooks") or []) else ""))
    return _section("Agent surface", [("kind", {"no_wrap": True}), ("where", {"overflow": "fold", "ratio": 1}), ("what", {"overflow": "fold", "ratio": 2})], rows, caption=caption)   # a path here folds whole rather than losing its middle: the list is what the section is for


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
    word = textfmt.severity_word   # "note" for the JSON's `info`, as the tally and the marks' legend say it
    rows = [("new", f"{word(f['severity'])} · {f['title']}") for f in result["new"]]
    rows += [("resolved", f"{word(f['severity'])} · {f['title']}") for f in result["resolved"]]
    rows += [("persisting", (f"{word(f['was'])} → {word(f['severity'])}" if f["was"] != f["severity"] else word(f["severity"])) + f" · {f['title']}" + _changed_words(f.get("changed")))
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


BUILDERS = [watch_section, documents_section, watch_by_component_section, size_section, people_section, knowledge_section, activity_section, timeline_section,
            hotspots_section, coupling_section, signing_section, trailers_section, lines_section, age_section, functions_section, agent_surface_section,
            osps_section]
# `--full` and Markdown only: Size, Activity and Code age are interesting once and rarely change what you
# do next; Hotspots ranks the files the watch list already leads with, by the same product.
FULL_ONLY = {"size", "activity", "age", "hotspots", "signing", "trailers", "lines", "watch_by_component", "agent_surface", "osps"}


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
        if sec is None:   # a section that exists only for some repositories (documents_section, agent_surface), or one another table already gives (coupling)
            continue
        sec["id"] = sid
        out.append(sec)
    if width is not None:
        homes = _homes(report, out)
        for sec in out:
            sec["homes"] = homes
    return out


def _homes(report: dict, secs: list) -> dict:
    """The tracked paths by file name, for the names the path columns show that two or more paths share: what
    fit() must not shorten one of them into. One pass over the tree listing (the size step's files for a run
    from before it), and only when a table's path is cut would a reader take it for another."""
    names = set()
    for sec in secs:
        for i, o in enumerate(sec["col_opts"]):
            if o.get("kind") == "path":
                names.update(_base(r[i]) for r in sec["rows"])
    tracked = report.get("tree") or ((report.get("size") or {}).get("files") or {}).keys()
    homes = {}
    for p in tracked:
        name = p.rsplit("/", 1)[-1]
        if name in names:
            homes.setdefault(name, []).append(p)
    return {k: v for k, v in homes.items() if len(v) > 1}


SECRET_FINDINGS = ("secrets_in_source", "secrets_possible", "secrets_declared", "secrets_local")


DEPENDENCY_FINDINGS = ("vulnerable_dependencies", "vulnerable_dependencies_aside")


def footer_style(findings: list, rules: tuple, otherwise: str) -> str:
    """The colour of a footer line: the severity of the worst finding among `rules`, else `otherwise` (green
    for a scan that found nothing, none for a count no finding holds). The Secrets line was red whenever the
    scan counted a value and the Dependencies line whenever a package was vulnerable, so prometheus's 44 values,
    every one outside source and in no finding, were printed in the colour of a critical."""
    behind = [f["severity"] for f in findings or [] if (f.get("rule") or {}).get("id") in rules]
    return SEVERITY_STYLE[min(behind, key=["critical", "warning", "info"].index)] if behind else otherwise


def secrets_line(report: dict) -> str:
    """The scan's totals, and how many of them no finding holds: since 0.39.0 a value only in test, example,
    vendored, generated or documentation files is no finding, so VoiceStudio's footer counted 4 values
    beside a finding of 2 with nothing to say where the other 2 went. Saying so costs a wrapped line at
    80 columns on every development repository, which the report-length ceiling does not allow; it is
    paid for by the unreachable sweep's parenthetical, kept only on a line with no values to report."""
    from .findings import secrets_found
    rows = report.get("secrets") or []
    groups = leaks.group(rows)
    places = sum(g["places"] for g in groups)
    line = (f"Secrets: {textfmt.count(len(groups), 'distinct value')} in {textfmt.count(places, 'place')}"
            if groups else "Secrets: none found")
    if groups:
        held = sum((f.get("evidence") or {}).get("values", 0) for f in secrets_found(report) if f["rule"]["id"] in SECRET_FINDINGS)
        if len(groups) > held:   # the rest are only in test, example, vendored, generated or documentation files
            line += f", {len(groups) - held:,} never in source (secrets.json)"
    skipped = leaks.placeholders(rows)
    if skipped:
        line += f"; {skipped:,} placeholder-shaped hit{'s' if skipped != 1 else ''} left out"
    return line + _unreachable_words(report, bool(groups))


def secrets_pass(report: dict):
    """A check worth saying out loud when it passes: (title, detail) when the scan ran and found no
    secret value, else None. Found values are findings already, or, when every copy is in test, example, vendored,
    generated or documentation files, counted in the footer's Secrets line; a scan that did not run says nothing."""
    rows = report.get("secrets") or []
    if not report.get("secrets_scanned") or leaks.group(rows):
        return None
    detail = "betterleaks scanned every commit HEAD reaches"
    skipped = leaks.placeholders(rows)
    if skipped:
        detail += f"; {skipped:,} placeholder-shaped hit{'s' if skipped != 1 else ''} left out"
    return "No secrets in history", detail


def _dependency_files(scan: dict) -> str:
    """'61 lock files', or '58 lock files and 3 requirement files': osv-scanner reads both, and only one locks.
    A single file is named ('1 lock file (tests/server/package-lock.json)'): superpowers' report said "1 lock
    file" beside a finding that package.json had none, and nothing said which lock was meant."""
    paths = {s.get("path") or "" for s in scan.get("sources") or []}
    only = next(iter(paths)) if len(paths) == 1 else ""
    return deps.files_phrase(paths) + (f" ({only})" if only else "")


def _packages(n: int) -> str:
    return f"{n:,} package{'' if n == 1 else 's'}"


def dependencies_pass(report: dict):
    """(title, detail) when the lock files were scanned and no package has a known vulnerability, else None."""
    deps = report.get("dependencies") or {}
    if deps.get("status") != "scanned" or deps.get("vulnerable") or not deps.get("packages"):
        return None
    detail = f"osv-scanner checked {_packages(deps['packages'])} in {_dependency_files(deps)} against the local database"
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


def checks_passed(report: dict, footer: bool = True) -> list:
    """The checks that ran and passed, secrets first: said out loud rather than left to silence. Without
    the footer's two lines (footer_said) the secrets line also carries what only the footer said, the
    unreachable sweep."""
    passed = [p for p in (secrets_pass(report), dependencies_pass(report)) if p]
    if not footer and passed:
        passed[0] = (passed[0][0], passed[0][1] + _unreachable_words(report, True))
    return passed


def _unreachable_words(report: dict, short: bool) -> str:
    """'; no unreachable objects…' or '; 3 unreachable blobs scanned too', or '' for a run without the sweep."""
    loose = report.get("unreachable") or {}
    if loose and not loose.get("objects"):
        return "; no unreachable objects" + ("" if short else " (a fresh clone fetches only what a ref reaches)")
    if loose.get("scanned"):
        return f"; {loose['scanned']:,} unreachable blob{'s' if loose['scanned'] != 1 else ''} scanned too"
    return ""


def footer_said(report: dict) -> bool:
    """Whether the Findings panel's two ✔ lines already say everything the footer's Secrets and Dependencies
    lines would: both scans ran and found nothing, and no package carries an informational advisory, which
    only the footer names. The default report then leaves the two lines out."""
    return bool(secrets_pass(report) and dependencies_pass(report) and not (report.get("dependencies") or {}).get("informational"))


def dependencies_line(report: dict):
    """(text, style) for the footer: what the osv-scanner step found, or why it found nothing; None
    for an output directory from before the step existed."""
    deps = report.get("dependencies") or {}
    status = deps.get("status")
    if status == "scanned":
        rows = deps.get("vulnerable") or []
        bad = len({r.get("name") for r in rows})
        line = f"Dependencies: {_packages(deps.get('packages', 0))} in {_dependency_files(deps)}, "
        line += (f"{bad:,} vulnerable" + (f" in {len(rows):,} places" if len(rows) != bad else "")) if bad else "none vulnerable"
        notes = deps.get("informational") or []
        if notes:   # RustSec's unmaintained, unsound and notice advisories: said, not counted as vulnerable
            first = notes[0]
            line += (f"; {len(notes):,} with an informational advisory ({first.get('name')} {first.get('version')}, "
                     f"{' and '.join(first.get('kinds') or [])}" + (f", and {len(notes) - 1:,} more" if len(notes) > 1 else "") + ")")
        if deps.get("database_date"):
            line += f" (database from {deps['database_date']})"
        return line, ("" if bad else "green")   # a count is not a verdict: footer_style colours it when a finding is behind it
    if status == "no-sources":
        return "Dependencies: no lock files found", "dim"
    if status == "no-database":
        return "Dependencies: not scanned, no offline vulnerability database; fetch it once: gitmole --fetch-vuln-db CLONE", "yellow"
    return None


# --- rich ------------------------------------------------------------------

def _facts(body: Text, facts: list, sep: str, width) -> None:
    """Append (text, style) facts joined by `sep`, starting a new line before a fact that would not fit
    in `width`, so that no fact ("branch main @ eef0e230") is split across two lines unless it is longer
    than a line on its own. `width` None joins them all on one line, as before."""
    used = 0
    for i, (text, style) in enumerate(facts):
        if i:
            if width is not None and used + len(sep) + len(text) > width and len(text) <= width:   # a fact longer than a line wraps where it is
                body.append("\n")
                used = 0
            else:
                body.append(sep)
                used += len(sep)
        body.append(text, style=style)
        used = (used + len(text)) % width if width is not None and used + len(text) > width else used + len(text)
    body.append("\n")


PANEL_EDGES = 4   # a panel's two borders and its padding of one either side


def header(report: dict, findings: list = (), full: bool = False, width=None) -> Panel:
    s = summary(report)
    inner = width - PANEL_EDGES if width else None
    body = Text()
    first = [(f"{s['commits']:,} commits", "bold"), (f"{s['first_date']} → {s['last_date']}", "")]
    if s["since"]:
        first.append((f"since {s['since']}", "yellow"))
    first += [(textfmt.count(s["identities"], "identity", "identities"), ""),
              (f"branch {s['branch']}" + (f" @ {s['commit'][:8]}" if s["commit"] else ""), "")]
    _facts(body, first, "  ·  ", inner)
    if s["scope"]:
        body.append(scope.label(s["scope"]), style="bold yellow")
        body.append(f"  ·  {scope.REPOSITORY_WIDE}\n", style="dim")
    scored = None if full and s["coverage"] else scored_phrase(report)   # --full's coverage line counts every bucket
    _facts(body, [(f"{s['lines']:,} lines in {s['files']:,} files", ""), (", ".join(s["languages"]) or "unknown", "")], "  ·  ", inner)
    if full and s["coverage"]:
        _facts(body, [(part, "dim") for part in classify.coverage_line(s["coverage"]).split(" · ")], " · ", inner)
    unranked = coverage_phrases(report)
    if unranked:   # not dim: the tables below describe the smaller part of this tree
        _facts(body, [(part, "") for part in ([scored] if scored else []) + unranked], "  ·  ", inner)
    if s["pulse"]:
        _facts(body, [(part, "dim") for part in s["pulse"]], "  ·  ", inner)
    tally = textfmt.tally(list(findings))
    worst = next((f["severity"] for f in findings), None)
    body.append(tally, style=SEVERITY_STYLE.get(worst, "green"))
    if scored and not unranked:   # what the tally is a tally of
        body.append(f"  ·  {scored}")
    return Panel(body, title=f"[bold]{s['name']}[/bold]", title_align="left", border_style="blue")


def unjudged_line(findings: list) -> str:
    """'4 more from the structure step, not labelled yet (1 warning, 3 notes): Deep nesting and Debt in hotspots;
    --full lists them': the rules whose worth nobody has judged (findings.UNJUDGED), kept out of the default
    report's entries. Their severities are said, since the header's tally, the JSON and the gate count them."""
    names = [g["title"] for g in textfmt.group_findings(findings)]
    return (f"{len(findings):,} more from the structure step, not labelled yet ({textfmt.tally(findings)}): "
            f"{textfmt.join_and(names)}; --full lists them")


def findings_panel(findings: list, report: dict = None, full: bool = True) -> Panel:
    passed = checks_passed(report or {}, footer=bool(full) or not footer_said(report or {}))
    absent = not_computed_line(report) if report else None
    if not findings and not passed and not absent:
        return Panel(Text("Nothing flagged.", style="green"), title="Findings", title_align="left", border_style="green")
    unjudged = [] if full else [f for f in findings if f.get("unjudged")]
    shown = [f for f in findings if f not in unjudged]
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
    if unjudged:
        grid.add_row(Text("·", style="dim"), Text(unjudged_line(unjudged), style="dim"))
    if (passed or absent) and not findings:
        grid.add_row(Text(""), Text("Nothing flagged.", style="green"))
    for title, detail in passed:   # problems first, then the checks that passed
        grid.add_row(Text("✔", style="green"), Text(title, style="green").append(f"\n{detail}", style="dim"))
    if absent:   # last: what was found, what passed, then what was never measured, so its silence is not a pass
        grid.add_row(Text("·", style="dim"), Text(absent, style="dim"))
    title = f"Findings ({len(findings):,})" if findings else "Findings"
    return Panel(grid, title=title, title_align="left", border_style=SEVERITY_STYLE[findings[0]["severity"]] if findings else "green")


def cell_style(column: str, value: str):
    """A style for values that crossed a threshold, or None."""
    try:
        if column == "share":
            n = int(value.rstrip("%"))
            return HOT if n >= 50 else (WARM if n >= 20 else None)
        if column == "together" and int(value.rstrip("%")) >= 90:   # the coupling table's share, the JSON's `degree`
            return HOT
        if column == "fixes" and int(value.replace(",", "")) >= 5:
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


# fit(): how far a column may give way before anything else does. A path keeps its file name whole (the directories
# go first, textfmt.shorten_path), a name or label keeps NAME_KEEP characters, prose wraps at words down to
# PROSE_FLOOR; only then are names and file names cut in the middle, never below CUT_FLOOR.
# Columns are left out only when even less does not fit: a file name cut at PATH_LEAST, a name at NAME_LEAST, prose
# folded at PROSE_FLOOR; a column marked "spare" goes first, then the rightmost.
# Prose keeps PROSE_KEEP characters before a path loses a directory, so a long path does not squeeze the reasons
# beside it into a column of single words.
NAME_KEEP, PROSE_KEEP, PROSE_FLOOR, CUT_FLOOR, PATH_LEAST, NAME_LEAST = 32, 40, 20, 12, 24, 16
GAP = 3   # rich's padding either side of a column plus the SIMPLE_HEAD box's divider between two


def _kind(name: str, opts: dict) -> str:
    """How a column may give way: "path" (directories elided), "name" (cut in the middle), "prose" (wraps at
    words) or "fixed" (a number, a bar: never cut)."""
    if opts.get("kind"):
        return opts["kind"]
    if opts.get("justify") == "right" or name == "":
        return "fixed"
    return "prose" if opts.get("ratio") else "name"


def _fit_cell(kind: str, text: str, width: int, others=()) -> str:
    if len(text) <= width:
        return text
    if kind == "path":
        return textfmt.cut_path(text, width, others)
    return textfmt.cut_middle(text, width)


def _base(cell: str) -> str:
    return textfmt.LINE_SUFFIX.sub("", cell).rstrip("/").rsplit("/", 1)[-1]


def _namesakes(sec: dict, i: int) -> list:
    """For each row, the paths its cell in column `i` must not be shortened into: the column's other paths
    and the tracked files (sec["homes"], from sections) with the same name."""
    homes = sec.get("homes") or {}
    column = [textfmt.LINE_SUFFIX.sub("", r[i]) for r in sec["rows"]]
    same = {}
    for p in column:
        same.setdefault(_base(p), set()).add(p)
    return [sorted(same[_base(p)] | set(homes.get(_base(p), ()))) if len(same[_base(p)]) > 1 or len(homes.get(_base(p), ())) > 1 else []
            for p in column]


def fit(sec: dict, width) -> dict:
    """The section with its columns sized to `width` from their content, so that no cell is split across
    lines: a name, an identifier, a path or a number stays on one line. When the columns do not fit, the
    table gives way in this order: prose columns wrap at words, a header of several words wraps at its
    spaces, paths lose directories and long names their middle (widest column first), and last the
    rightmost columns are left out, which the caption says. Rows and captions are otherwise unchanged; a
    table that fits is returned as it came. `width` None (Markdown) fits nothing."""
    from rich.cells import cell_len
    if width is None or not sec["rows"]:
        return sec
    cols, opts = sec["columns"], sec["col_opts"]
    bars = "share" in cols and "" not in cols
    kinds = [_kind(c, o) for c, o in zip(cols, opts)]
    rows = sec["rows"]
    cells = [max(_cell(c, r[i], bars).cell_len for r in rows) for i, c in enumerate(cols)]
    heads = [cell_len(c) for c in cols]
    head_word = [max((cell_len(w) for w in c.split()), default=0) for c in cols]
    want = [max(a, b) for a, b in zip(cells, heads)]

    def room(keep):
        return width - INDENT - GAP * (len(keep) - 1)
    keep = list(range(len(cols)))
    if sum(want) <= room(keep):
        return sec

    def longest_word(i):
        return max(cell_len(w) for r in rows for w in (r[i].split() or [""]))

    # the paths a cut path must not read as; they change what a cell shows within its width, never the widths,
    # so keeping two files apart costs no column its room and no row a line
    namesakes = {i: _namesakes(sec, i) for i, k in enumerate(kinds) if k == "path"}

    def name_floor(i):   # what a column keeps before anything is cut: whole file names, NAME_KEEP of a name
        if kinds[i] == "path":
            return min(want[i], max(head_word[i], max(cell_len(textfmt.shorten_path(r[i], 0)) for r in rows)))
        return min(want[i], max(head_word[i], NAME_KEEP))

    # the least each column can take: a number whole, a name or path cut to CUT_FLOOR, prose folded at PROSE_FLOOR
    least = [min(want[i], max(head_word[i], PROSE_FLOOR if k == "prose" else CUT_FLOOR)) if k != "fixed" else max(cells[i], head_word[i])
             for i, k in enumerate(kinds)]

    def needs(i):   # what a column must have to stay in the table
        if kinds[i] == "path":
            return min(name_floor(i), max(head_word[i], PATH_LEAST))
        return min(want[i], max(head_word[i], NAME_LEAST)) if kinds[i] == "name" else least[i]
    dropped = []
    while len(keep) > 1 and sum(needs(i) for i in keep) > room(keep):
        spare = [i for i in keep[1:] if opts[i].get("spare")]
        gone = spare[0] if spare else keep[-1]
        keep.remove(gone)
        dropped.append(gone)
    dropped = [cols[i] for i in sorted(dropped)]
    floor = []   # what each column keeps before anything is cut: prose wraps at words, file names and NAME_KEEP of a name stay whole
    for i, k in enumerate(kinds):
        if k == "prose":
            floor.append(min(want[i], max(PROSE_FLOOR, longest_word(i), head_word[i])))
        elif k in ("path", "name"):
            floor.append(name_floor(i))
        else:
            floor.append(least[i])
    widths = {i: want[i] for i in keep}

    def excess():
        return sum(widths.values()) - room(keep)
    for i in keep:   # prose first, down to PROSE_KEEP; then headers; then the columns that are cut; then prose again
        if kinds[i] == "prose" and excess() > 0:
            widths[i] = max(floor[i], min(want[i], PROSE_KEEP), widths[i] - excess())
    for i in sorted(keep, key=lambda i: cells[i] - heads[i]):   # a header wider than its cells wraps at its spaces
        if kinds[i] != "prose" and heads[i] > cells[i] and excess() > 0:
            widths[i] = max(cells[i], head_word[i], widths[i] - excess())
            floor[i] = min(floor[i], widths[i])
    # a column of directories (the knowledge map's areas) is cut below its names only after every other column
    # has given what it can: an area is the row's subject, an owner's name is its detail
    dirs = {i for i in keep if kinds[i] == "path" and any(r[i].endswith("/") for r in rows)
            and all(r[i].endswith("/") or "/" not in r[i] for r in rows)}   # "(root files)" sits among them
    for floors, give, among in ((floor, ("path", "name"), keep), (floor, ("prose",), keep),
                                (least, ("path", "name", "prose"), [i for i in keep if i not in dirs]), (least, ("path",), dirs)):
        while excess() > 0:
            cand = [i for i in among if kinds[i] in give and widths[i] > floors[i]]
            if not cand:
                break
            widths[max(cand, key=lambda i: widths[i])] -= 1
    fitted = [tuple(_fit_cell(kinds[i], r[i], widths[i], namesakes[i][n] if i in namesakes else ()) if kinds[i] in ("path", "name") else r[i] for i in keep)
              for n, r in enumerate(rows)]
    col_opts = [dict(opts[i], width=widths[i]) for i in keep]
    caption = sec.get("caption")
    if dropped:
        left = f"{textfmt.join_and(dropped)} left out at {width} columns; a wider terminal or --markdown shows {'it' if len(dropped) == 1 else 'them'}"
        caption = f"{caption}\n{left}" if caption else left
    return dict(sec, columns=[cols[i] for i in keep], col_opts=col_opts, rows=fitted, caption=caption)


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
        o = {k: v for k, v in opts.items() if k not in ("kind", "spare")}   # fit()'s, not rich's
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


def section_block(sec: dict, width=None):
    """Heading plus table, or heading plus a dim note for an empty section. With a `width`, the table is
    fitted to it first (fit)."""
    if not sec["rows"] and sec["note"]:
        return heading(sec) + Text(f": {sec['note']}", style="dim")
    return Group(heading(sec), Padding(rich_table(fit(sec, width)), (0, 0, 0, INDENT)))


def print_section(console: Console, sec: dict) -> None:
    """Blank line, then the section's heading and table (or note), fitted to the console's width."""
    console.print(Text(""))
    console.print(section_block(sec, console.width))


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
    console.print(header(report, findings, full=full, width=console.width))
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
    if full or not footer_said(report):   # the default report does not repeat what the two ✔ lines said
        console.print(Text(secrets_line(report), style=footer_style(findings, SECRET_FINDINGS, "" if leaks.group(report.get("secrets") or []) else "green")))
        deps_line = dependencies_line(report)
        if deps_line:
            console.print(Text(deps_line[0], style=footer_style(findings, DEPENDENCY_FINDINGS, deps_line[1])))
    if full and (line := run_line(report)):
        console.print(Text(line, style="dim"), soft_wrap=True)
    console.print(Text(results_line(report), style="dim"), soft_wrap=True)


def excerpt(report: dict, findings: list, console: Console, full: bool = False) -> None:
    """The report's opening on its own: the header, whose tally counts the findings, and the watch
    list. What the README's text block shows; the findings themselves are in the full report."""
    console.print(header(report, findings, width=console.width))
    print_section(console, watch_section(report, full=full, width=console.width))


# --- markdown / json -------------------------------------------------------

def _md_cell(cell: str) -> str:
    return cell.replace("|", "\\|").replace("\n", " ")


def _md_findings(findings: list, report: dict = None) -> list:
    out = [] if findings else ["Nothing flagged."]
    for g in textfmt.group_findings(findings):
        line = f"- **{textfmt.severity_word(g['severity'])}** {g['title']} — " + "; ".join(g["items"])
        line += "".join(f" _{advice}_" for advice in g["advice"])
        out.append(line)
    for title, detail in checks_passed(report or {}):
        out.append(f"- **ok** {title} — {detail}")
    absent = not_computed_line(report) if report else None
    if absent:
        out.append(f"- **not computed** {absent}")
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
    unranked = coverage_phrases(report)
    out = [f"# {s['name']}", "",
           f"{s['commits']:,} commits · {s['first_date']} → {s['last_date']}" + (f" · since {s['since']}" if s["since"] else "")
           + f" · {textfmt.count(s['identities'], 'identity', 'identities')} · branch {s['branch']}"
           + (f" @ {s['commit'][:8]}" if s["commit"] else "") + "  ",
           *([f"{scope.label(s['scope'])} · {scope.REPOSITORY_WIDE}  "] if s["scope"] else []),
           f"{s['lines']:,} lines in {s['files']:,} files · {', '.join(s['languages']) or 'unknown'}" + ("  " if s["coverage"] or s["pulse"] else ""),
           *([classify.coverage_line(s["coverage"]) + ("  " if s["pulse"] or unranked else "")] if s["coverage"] else []),
           *([" · ".join(unranked) + ("  " if s["pulse"] else "")] if unranked else []),
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
            *([rl + "  "] if rl else []), results_line(report), ""]
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
    # The projection is priced from a count of work, the same for the same commit, but it stays in the
    # envelope, where exports up to 0.43.0 put a timed one, so an export's shape does not change.
    if isinstance(age, dict) and "projected_seconds" in age:
        env["projected_seconds"] = age.pop("projected_seconds")
    if isinstance(age, dict) and "projected_partial" in age:
        env["projected_partial"] = age.pop("projected_partial")
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
    out = {**{k: v for k, v in report.items() if k not in ("backtest", "tree", "imported", "arrivals")}, "findings": findings,   # the sub-report is a report of its own; the listing is the clone's; the arrivals live on as the truck factor's new_since
           "watch": [{k: v for k, v in r.items() if k != "function"} | {"function": r["function"]["function"] if r["function"] else None}
                     for r in watch.risks(report)[:WATCH_FULL]]}
    out["watch_by_component"] = [{"component": g["component"], "share": round(g["share"], 3), "files": [x["file"] for x in g["files"]]}
                                 for g in watch.by_component(watch.risks(report), base=scope.report_base(report))]
    from . import osps
    out["osps"] = {"baseline": osps.BASELINE, "controls": osps.coverage(report, findings)}
    from . import findings as rules
    out["not_computed"] = rules.not_computed(report)   # the measures the run could not make, each with why
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
        worst = f"{textfmt.severity_word(found[0]['severity'])}: {found[0]['title']}" if found else "-"
        rows.append((name, s["commits"], s["identities"], bus, len(leaks.group(rep.get("secrets") or [])), f"{s['lines']:,}", worst))
    return _section(f"Portfolio ({len(reports)} repositories)",
                    [("repo", {"overflow": "fold"}), ("commits", RIGHT), ("people", RIGHT), ("top author", RIGHT),
                     ("secrets", RIGHT), ("lines", RIGHT), ("worst finding", {"overflow": "fold", "ratio": 2})], rows,
                    note=None if rows else "no repositories")


def portfolio_markdown(owner: str, reports: list) -> str:
    sec = portfolio_section(reports)
    out = [f"# {owner}", "", f"{len(reports):,} repositories analysed with gitmole.", "", f"## {sec['title']}", ""]
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

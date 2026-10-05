"""Turn a loaded report into sections, then draw them with rich or as Markdown/JSON.

The default report is the tighter one: the columns you actually read, capped rows, elided
paths. `full` restores every column and row (Markdown export is always full)."""
from __future__ import annotations

import json
import os

from rich import box
from rich.console import Console, Group
from rich.markup import escape
from rich.padding import Padding
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from . import brief, classify, coupling, deps, filetypes, hotspots, identity, knowledge, leaks, loss, provenance, scope, textfmt, trend, watch

SEVERITY_STYLE = {"critical": "bold red", "warning": "yellow", "info": "cyan"}

# section styling: the banner's palette carried into the tables
ACCENT = "#5ad0ff"          # section titles
HEADER = "bold #c86cff"     # column headers
BAR = "#5ad0ff"             # inline share bars
HOT = "bold #ff5cc8"        # values past a threshold
WARM = "#ff9ee0"            # values worth a glance
ROW_STYLES = ["", "on #1c2230"]

# the Timeline's month columns: each is 3 characters wide plus the 2 of GAP between every pair of columns
# (verified against rich.table.Table._calculate_column_widths, whose "n columns - 1" extra width cancels the
# gap saved on the last column, leaving a clean 5 per month). The section itself is indented by 2. The twelve
# months are the table at every width: when a name leaves them no room the name gives way, cut to what is left,
# and NAME_FLOOR is the fewest characters of it still shown before the ellipsis (eight keeps most short names,
# and the start of longer ones, recognisable). The year needs INDENT + NAME_FLOOR + 12 × MONTH_WIDTH = 70 columns.
MONTH_WIDTH, INDENT, NAME_FLOOR = 5, 2, 8

SYMBOLS = {"Size by language": "▤", "People": "◉", "Activity": "◔", "Timeline": "▦", "Hotspots": "◆", "Change coupling": "⟷",
           "Surviving code by year written": "◷", "Net lines added by year": "◷", "Paths in history by year last changed": "◷",
           "Knowledge map": "⌂", "Repo health": "✚", "Portfolio": "▣", "File types": "▥", "Complex functions": "λ", "Watch list": "◎",
           "Change risk": "◈", "Since last report": "⇄", "Most-changed documents": "✎"}
# the one column to read first in each table; the rest are dimmed
# keyed on the head as printed: "changes", "together" and "complexity" are the report's words for what the JSON calls revs, degree and ccn
KEY_METRIC = {"Size by language": "code", "People": "commits", "Hotspots": "changes", "Change coupling": "together",
              "Knowledge map": "added", "Surviving code by year written": "lines", "Net lines added by year": "net lines",
              "Paths in history by year last changed": "paths", "Activity": "commits", "Portfolio": "commits", "Complex functions": "complexity",
              "Watch list": "changes", "Change risk": "risk", "Most-changed documents": "changes"}
SEVERITY_MARK = {"critical": "✖", "warning": "▲", "info": "●"}
RIGHT = {"justify": "right"}
FOLD = {"overflow": "fold"}
PATH = {"overflow": "fold", "no_wrap": False, "kind": "path"}   # "kind" (and "spare") are fit()'s, not rich's
WHOLE = {"kind": "fixed"}   # a short text cell that is never cut, as a number is not: a share with "gone" after it
TAIL = {"kind": "tail", "no_wrap": True}   # the last text cell of a row: cut at its end with an ellipsis once every path has given its directories

# rows shown by default; `full` lifts the caps. Markdown gets a looser cap of its own. Hotspots has
# no entry: it is `--full`/Markdown only now, so its row count is never decided by this table.
CAPS = {"Most-changed documents": 5, "People": 6, "Change coupling": 5, "Knowledge map": 6, "Size by language": 8, "Complex functions": 8}
MARKDOWN_CAP = 50
# The default report's rows about a person need this many commits, the rest are counted in the title: the
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


def _section(title, columns, rows, note=None, caption=None, under=None, loose=False) -> dict:
    """columns: list of (name, rich column options). rows: lists of cells, a count as an int (see _number).
    `caption` is one paragraph a line, each wrapped at its separators when it is drawn. `under` is one line of
    text per row, drawn indented beneath it on a terminal and as a last column in Markdown ("under_head" names
    it). `loose` keeps the drawing from before the default report's grid (LOOSE_GAP)."""
    sec = {"title": title, "columns": [c[0] for c in columns], "col_opts": [c[1] for c in columns],
           "rows": [[_number(c) for c in r] for r in rows], "note": note, "caption": caption}
    if under is not None:
        sec["under"] = list(under)
    if loose:
        sec["loose"] = True
    return sec


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


def _hide_rows(rows: list, path_of, full, pred, kind: str) -> tuple:
    """Drop rows whose path (or any of whose paths) satisfies `pred`, unless `full` is True.
    `path_of(row)` returns a single path or a tuple of paths to check. Returns (rows, hidden), `hidden` being
    (count, kind) for the caption's sum (_hidden), `kind` the one word the breakdown gives the class ("test",
    "vendored"), or None when nothing was hidden."""
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
    return kept, ((hidden, kind) if hidden else None)


def _hidden(noun: str, plural: str, *counts):
    """What a table hides, as one phrase: the sum with its breakdown, largest class first ('501 pairs hidden:
    289 test, 192 historical, 10 vendored, 8 generated, 2 example'), or the one class there is ('34 historical
    areas hidden'); None when nothing is. prometheus's coupling caption gave the five counts as five clauses
    between semicolons, each ending "hidden", and a reader had to add them. The classes are disjoint, since a
    row leaves at the first rule that takes it. No "--full shows them": the report says that once, at its end."""
    by_kind = {}
    for c in counts:
        if c and c[0]:
            by_kind[c[1]] = by_kind.get(c[1], 0) + c[0]
    if not by_kind:
        return None
    total = sum(by_kind.values())
    if len(by_kind) == 1:
        kind = next(iter(by_kind))
        return f"{total:,} {kind} {noun if total == 1 else plural} hidden"
    return f"{total:,} {plural} hidden: " + ", ".join(f"{n:,} {kind}" for kind, n in sorted(by_kind.items(), key=lambda kv: (-kv[1], kv[0])))


def _hide_by(rows: list, path_of, full, classifier, reasons, kind: str) -> tuple:
    """_hide_rows through the classifier: a row goes when any of its path's reasons is one the table hides."""
    return _hide_rows(rows, path_of, full, lambda p: classifier.excluded(p, reasons), kind)


def _hide_tests(rows: list, path_of, full, classifier=None) -> tuple:
    """Test files: they change with every fix, so they are not a signal on their own."""
    return _hide_by(rows, path_of, full, classifier or classify.Classifier({}), {"test file"}, "test")


def _hide_vendor(rows: list, path_of, full, report: dict = None, classifier=None) -> tuple:
    """Vendored trees, by name, by the licence the run found or by the attribute the repository declares:
    somebody else's code, not this repository's risk."""
    return _hide_by(rows, path_of, full, classifier or classify.Classifier(report or {}), {"vendored"}, "vendored")


def _hide_generated(rows: list, path_of, report: dict, full, classifier=None) -> tuple:
    """Generated files (a header marker or a linguist-generated attribute, found at run time) and
    amalgamations (other files pasted together, found from the function metrics): the generator's
    churn and complexity, not the repository's."""
    return _hide_by(rows, path_of, full, classifier or classify.Classifier(report or {}), {"generated", "amalgamation"}, "generated")


def _hide_pairs(pairs: list, full, both, kind: str) -> tuple:
    """Drop the coupled pairs `both(entity, coupled)` accepts, unless `full` is True; (pairs, hidden) like _hide_rows."""
    if full is True:
        return pairs, None
    kept = [p for p in pairs if not both(p["entity"], p["coupled"])]
    hidden = len(pairs) - len(kept)
    return kept, ((hidden, kind) if hidden else None)


def _hide_release(pairs: list, full) -> tuple:
    """Coupled pairs where both files are release plumbing (version files, manifests, lock files,
    changelogs): they change together because a release touches them all, not because one depends on
    the other. A version file paired with real code stays."""
    return _hide_pairs(pairs, full, lambda a, b: filetypes.is_release_path(a) and filetypes.is_release_path(b), "release")


def _hide_example_pairs(pairs: list, full) -> tuple:
    """Coupled pairs where both files are example or documentation material. curl's
    docs/examples/imap-ssl.c and docs/examples/pop3-ssl.c show one technique for two protocols, and
    smtp-expn.c and smtp-vrfy.c two commands of one: each is a copy of its sibling, so they change
    together by design and told the table's top two rows nothing. An example paired with the code it
    demonstrates stays, since that pair says the example tracks the API."""
    def specimen(path):
        return filetypes.is_sample_path(path) or filetypes.is_doc_path(path)
    return _hide_pairs(pairs, full, lambda a, b: specimen(a) and specimen(b), "example")


def _hide_header_pairs(pairs: list, full) -> tuple:
    """A C-family source file and its own header change together by construction."""
    return _hide_pairs(pairs, full, filetypes.is_header_pair, "header")


def _hide_locale_pairs(pairs: list, full) -> tuple:
    """Coupled pairs where both files are translations (filetypes.is_locale_path): a message added in one
    locale is added in all of them, so they change together by construction. A locale paired with the code
    that uses it stays."""
    return _hide_pairs(pairs, full, lambda a, b: filetypes.is_locale_path(a) and filetypes.is_locale_path(b), "locale")


def _hide_deleted(rows: list, report: dict, full, classifier=None) -> tuple:
    """Drop hotspot rows for files no longer in the tree, unless `full` is True: a deleted file's churn
    is history. The classifier judges nothing as gone without a tree listing, so a killed scc hides
    nothing. Returns (rows, hidden) like _hide_tests."""
    cls = classifier or classify.Classifier(report or {})
    return _hide_rows(rows, lambda h: h["entity"], full, lambda p: cls.excluded(p, {"not in the tree"}), "deleted")


def _hide_gone(pairs: list, report: dict, full, classifier=None) -> tuple:
    """Drop coupled pairs where either file is no longer in the tree, unless `full` is True: they
    describe a layout that no longer exists. Returns (pairs, hidden) like _hide_tests."""
    cls = classifier or classify.Classifier(report or {})
    return _hide_pairs(pairs, full, lambda a, b: cls.excluded(a, {"not in the tree"}) or cls.excluded(b, {"not in the tree"}), "historical")


SEP = " · "   # between two fragments of a caption or two facts of the header: the report's one inline separator


def _fragments(*parts) -> str:
    """The fragments there are, joined by the separator: one paragraph of a caption. None for none."""
    return SEP.join(p for p in parts if p) or None


def _paragraphs(*parts) -> str:
    """A caption of several paragraphs, each on its own line; None for none."""
    return "\n".join(p for p in parts if p) or None


def _shown(n: int, total: int) -> str:
    """'5 of 96' for a table that shows part of its rows, 'all 96' for one that shows them all: a title's count."""
    return f"{n:,} of {total:,}" if n < total else f"all {total:,}"


def _empty_note(base, hidden_note, source_base=None) -> str:
    """The note that replaces a table with no rows left. When rows were hidden the note has to carry the
    count, since the caption goes with the table, and what is left is the source rows."""
    return f"{source_base or base}{SEP}{hidden_note}" if hidden_note else base


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


def backtest_words(bt: dict, detail: bool = False) -> str:
    """The backtest in two plain sentences, every count out of the same pool, the files that had changed more
    than once by the cut-off, of which `positives` were fixed after it: what the top of the ranking held, then
    what the same number of most-changed files held and what a random pick would. A result a random pick could
    have given says so, by the one-sided hypergeometric test at 5% (watch.p_by_chance), with its p. `detail`
    (--full, Markdown) adds the pool, the fixed files outside it and the p of a result that is not chance.
    prometheus's caption was one sentence of four lines with the three comparisons in brackets. A backtest from
    before `positives` was recorded keeps to the counts it has, and one with nothing in the pool fixed says so."""
    n, k, churn = bt["listed"], bt["hits"], bt["baselines"]["churn"]
    most = "The most-changed file" if n == 1 else f"The {n} most-changed files"
    random = "1 random file" if n == 1 else f"{n} random files"
    if "positives" not in bt:
        return (f"6 months ago the top {n} of this ranking held {k:,} of the {bt['fixed']:,} files fixed since. "
                f"{most} held {churn:,}; {random} of the {bt['pool']:,} that had changed more than once would hold {bt['expected']}.")
    if not bt["positives"]:
        return (f"None of the {bt['fixed']:,} files fixed since the cut-off 6 months ago had changed more than once by then, "
                f"so there is nothing to score this ranking against.")
    p = bt.get("p_by_chance")
    p = watch.p_by_chance(bt["pool"], bt["positives"], n, k) if p is None else p
    by_chance = p >= watch.CHANCE_ALPHA
    versus = (f"held {churn:,}, more than this ranking" if k < churn else f"also held {churn:,}" if k == churn
              else f"held {churn:,}, fewer than this ranking")
    chance = f"{random} would hold {bt['expected']}" + (f", and {k:,} is not distinguishable from that ({_p_words(p)})" if by_chance else "")
    out = (f"6 months ago the top {n} of this ranking held {k:,} of the {textfmt.count(bt['positives'], 'file')} fixed since. "
           f"{most} {versus}; {chance}.")
    if detail:
        outside = bt["fixed"] - bt["positives"]
        out += (f" Counted over the {bt['pool']:,} files that had changed more than once by then"
                + (f"; {textfmt.count(outside, 'more file')} fixed since had not" if outside > 0 else "")
                + ("" if by_chance else f"; {_p_words(p)}") + ".")
    return out


FIX_MONTHS = 6   # the window of maat's recent-fixes column, which the watch list's "fixes" and the bug magnets count in


def _window(months: int, last: str) -> str:
    """'the 6 months to 2026-09-18', or 'the last 6 months' for a report without its last date."""
    return f"the {months} months to {last}" if last else f"the last {months} months"


def _gone_names(report: dict) -> tuple:
    """(the names with no commit in the --gone window, that window in months)."""
    months = report["meta"].get("gone_months", loss.DEFAULT_MONTHS)
    return {g["name"] for g in loss.gone(report, months)}, months


def gone_definition(report: dict) -> str:
    """'gone = no commit in the 12 months to 2026-09-18': the one definition of the word. A section whose rows
    carry it holds this under `gone`, and sections() puts it in the caption of the first of them."""
    return f"gone = no commit in {_window(_gone_names(report)[1], report['meta'].get('last_date') or '')}"


def _define_gone(secs: list) -> None:
    """Add the definition of "gone" to the first paragraph of the first section that prints the word: it is
    defined once, where first tabled. prometheus's Knowledge map defined it and its Watch list, four of whose
    five rows carry it, did not."""
    said = False
    for sec in secs:
        text = sec.pop("gone", None)
        if text and not said and sec["rows"]:
            first, _, rest = (sec.get("caption") or "").partition("\n")
            sec["caption"] = _paragraphs(_fragments(first, text), rest)
            said = True


def _share_cells(shares: list, gone: list) -> list:
    """A column of shares, each with "gone" after it when its person is: the percentage right-aligned in a
    field as wide as the column's widest, so the word starts in one place (" 9% gone" under "23% gone"), and
    "-" for a row with no share. One space, no comma, no brackets; blank means active."""
    wide = max((len(x) for x in shares if x), default=0)
    return [(f"{x:>{wide}}" + (" gone" if g else "")) if x else "-" for x, g in zip(shares, gone)]


WATCH_ALSO = "also"   # the Markdown column for what --full prints under a watch-list row


def watch_section(report: dict, full: bool = True, width=None) -> dict:
    """The files to keep an eye on, one line each with its numbers in columns: how often it changed, how often
    it was fixed lately, the share of its largest author (and whether that person is gone) and the one function
    to open first (watch.first_look). prometheus's five files took 21 lines of reasons wrapped in one cell, the
    same "N of M authors are minor contributors" on every row. The reasons themselves are unchanged in the
    JSON, the --hook context and the --risk section; the ones the columns do not hold are printed under each
    row by --full and in a last column by Markdown. The share is printed and the name is not: a bare "gone"
    read as the file's only author, where prometheus's web/api/v1/api.go has 10% from its largest."""
    ranked = watch.risks(report)
    limit = WATCH_CAP if full is False else WATCH_FULL
    listed = ranked[:limit]
    gone, months = _gone_names(report)
    last = report["meta"].get("last_date") or ""
    since = report["meta"].get("since")
    looks = [watch.first_look(r) for r in listed]
    owners = _share_cells([f"{100 * r['owner_share']:.0f}%" if r["owner"] else "" for r in listed], [r["owner"] in gone for r in listed])
    rows = [(r["file"], r["revs"], r["recent_fixes"], owner, look[0] if look else "") for r, owner, look in zip(listed, owners, looks)]
    columns = [("file", PATH), ("changes", RIGHT), ("fixes", RIGHT), ("top author", WHOLE), ("look at first", TAIL)]
    if not any(looks):   # no function at either floor in any row shown: an empty column is not a column
        columns, rows = _keep(columns, rows, [c[0] for c in columns[:-1]])
    pool = min(len(ranked), WATCH_FULL)   # the list is short by design: its top, never every scored file
    title = (f"Watch list · {f'{len(rows):,} of {pool:,}' if len(rows) < pool else f'all {pool:,}'}, ranked by changes × lines of code"
             if rows else "Watch list")
    notes = [_fragments(f"changes = commits since {since}" if since else None, f"fixes = in {_window(FIX_MONTHS, last)}",
                        "top author = largest share of the lines added to the file")]
    bt = watch.backtest(report)
    status = report["meta"].get("backtest") or {}
    check = "Check, over the whole history: " if since else "Check: "   # the backtest ignores the window
    if bt and not bt["fixed"]:
        notes.append("Check: nothing has been fixed since the cut-off 6 months ago, so there is nothing to score this ranking against.")
    elif bt:
        notes.append(check + backtest_words(bt, detail=full is not False))
    elif status.get("reason"):
        notes.append(f"Check: none, {status['reason']}")
    elif status.get("status") in ("failed", "timeout"):
        notes.append(f"Check: none, backtest {STEP_WORDS[status['status']]}")
    caption = "\n".join(notes)   # the sweeping commits left out of these counts are the header's to say, once for every table
    under = None if full is False else [" · ".join(watch.beyond_columns(r)) for r in listed]
    sec = _section(title, columns, rows, note=None if rows else watch.why_empty(report), caption=caption if rows else None, under=under)
    sec["under_head"] = WATCH_ALSO
    if any(r["owner"] in gone for r in listed):
        sec["gone"] = gone_definition(report)
    return sec


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
    caption = _fragments("documentation is not scored: this is where it changed most, not where a fix is likely", f"changes = commits since {since}" if since else None)
    return _section(f"Most-changed documents · {_shown(len(rows), len(docs))}, by changes", [("document", PATH), ("changes", RIGHT)], rows, caption=caption)


def not_computed_line(report: dict):
    """'truck factor not computed: 17 source files, needs 20', or None: the measures that have no section of
    their own to say why they are missing. The backtest's reason stays under the watch list it would judge."""
    from . import findings
    parts = [f"{a['label']} not computed: {a['reason']}" for a in findings.not_computed(report) if not a.get("said")]
    return "; ".join(parts) or None


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
    # loose: this section's drawing is stored in tests/golden/strings.txt with the hook's and the gate's words,
    # which the watch list's columns (A5) do not touch; it takes the grid when that copy is next regenerated
    return _section(f"Change risk ({len(rows_all):,} files since {base})", columns, rows,
                    note=None if rows else f"no files changed since {base}", caption="\n".join(notes) or None, loose=True)


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


def _tools_words(report: dict, tools: set) -> str:
    """'3 coding-tool names (7 with aliases, sharing 1 no-reply address, 32 commits)': what the rows kept out of
    the People table are, counted as what git records. They are names, and several names on one vendor address
    are one assistant signing each model version differently, so "4 coding tools" for four rows on one address
    counted spellings as tools. The first number is the rows left out, which is what the export's `tools.names`
    holds and what the table's count is short by; every spelling, the ones merged into a row too, is the number
    with aliases, said only when it differs. prometheus's caption gave the 7 alone, beside a JSON key holding 3
    names and 32 commits, and the two could not be told to be one fact. The commits are the export's
    `tools.commits`. The same words in the default report, --full and Markdown."""
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
    return textfmt.count(rows, "coding-tool name") + (f" ({', '.join(detail)})" if detail else "")


BOTS_NAMED = 3   # the bots --full and Markdown name; the default report names the busiest


def _bots_words(bots: list, named: int) -> str:
    """'4 bots left out: dependabot[bot] 882, 3 more': how many, the busiest with their commits, the rest counted."""
    listed = ", ".join(f"{b['name']} {b['commits']:,}" for b in bots[:named])
    return f"{textfmt.count(len(bots), 'bot')} left out: {listed}" + (f", {len(bots) - named:,} more" if len(bots) > named else "")


def people_section(report: dict, full: bool = True, width=None) -> dict:
    """Who commits, most first. The title gives the denominator (the identities git records, coding tools
    taken out) and how many of them had aliases merged; the caption does the subtraction against the header's
    count, names the bots left out and defines the columns. prometheus's caption was eight lines for six rows:
    a count of the rest, the merge total, the tools, three bots by name, three people whose aliases merged
    and a .mailmap hint. The merge total, the aliases by name and the hint are --full's and Markdown's."""
    tools = set((report.get("tools") or {}).get("names") or [])   # load.py keeps them out of the tables about people
    everyone = report["meta"].get("identities") or []
    ids = [i for i in everyone if i["name"] not in tools]
    apart = len(tools & {i["name"] for i in everyone})
    merges = any(i.get("merges") for i in ids)   # merges in their own column: merging every pull request is not writing the code

    def own(i):   # the commits they authored: a Co-authored-by credit is its own column, not a commit of theirs
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
    # When each was last seen, to the month, and "gone" after it past the --gone window: prometheus's table led
    # with a person whose last commit was in 2019, and the reader had the Knowledge map's "(gone)" three rows of
    # another table away to learn it from. By name, as the run's own record of who is gone is (loss.gone).
    act = report.get("activity") or {}
    seen = act.get("authors_all") or act.get("authors") or {}
    gone, _ = _gone_names(report)
    last = [(seen.get(i["name"]) or {}).get("last") or "" for i in listed]
    dated = any(last)
    when = [f"{d[:7]}{' gone' if i['name'] in gone else ''}" if d else "-" for i, d in zip(listed, last)]
    # No address in any rendering, at any width: the Markdown is what the README says to post to a public job
    # summary, and prometheus's --full printed 1,324 addresses beside commit counts. The JSON keeps them, under
    # meta.identities, for whoever has the clone anyway.
    rows = [(i["name"], own(i), *((i.get("merges", 0),) if merges else ()), *((credit(i),) if credited else ()),
             _pct(own(i), total_commits), _pct(lines_of(i), total_lines), *((seen_at,) if dated else ())) for i, seen_at in zip(listed, when)]
    columns = [("author", {}), ("commits", RIGHT), *((("merges", RIGHT),) if merges else ()),
               *((("co-authored", RIGHT),) if credited else ()), ("share", RIGHT), ("surviving", RIGHT),   # the report's one word for the blame measure, defined in the caption
               *((("last commit", WHOLE),) if dated else ())]
    since = report["meta"].get("since")
    source = surviving_source(report) if total_lines else None   # the source of the column, said where the column is: the two steps give different shares
    bots = report["meta"].get("bots") or []
    merged = [i["name"] for i in ids if i.get("aliases")]
    notes = [_fragments(
        f"{len(ids):,} = {textfmt.count(len(everyone), 'identity', 'identities')} less {_tools_words(report, tools)}" if apart else None,
        _bots_words(bots, 1 if full is False else BOTS_NAMED) if bots else None,
        f"commits = since {since}" if since else None,
        "share = of commits" + (", without merges" if merges else ""),
        (f"surviving = {SURVIVING_SOURCES[source]} share at HEAD" + (", over the whole tree" if since else "")) if source else None)]
    if full is not False:   # how the table was made: --full and Markdown
        total_merges = sum(i.get("merges", 0) for i in ids)
        if merges:
            notes.append(f"{textfmt.count(total_merges, 'merge')} in all, in their own column")
        if merged:
            who = ", ".join(merged[:3]) + (f" and {len(merged) - 3:,} more" if len(merged) > 3 else "")
            notes.append(f"aliases merged for {who}; a .mailmap makes that permanent")
    title = (f"People · {_shown(len(rows), len(ids))} {'identity' if len(ids) == 1 else 'identities'}, by commits"
             + (f"{SEP}{len(merged):,} with aliases merged" if merged else "")) if rows else "People"
    sec = _section(title, columns, rows, caption=_paragraphs(*notes))
    sec["bars"] = False   # a share of 9% and one of 3% drew the same single block: the column says nothing the number does not
    if any(i["name"] in gone and d for i, d in zip(listed, last)):
        sec["gone"] = gone_definition(report)
    return sec


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


def _part_month(report: dict, month: str) -> bool:
    """Whether `month` ("YYYY-MM") is the month of the last commit and that commit is before the month's last day:
    a column that holds part of a month beside eleven whole ones."""
    import calendar
    last = report["meta"].get("last_date") or ""
    try:
        return last[:7] == month and int(last[8:10]) < calendar.monthrange(int(month[:4]), int(month[5:7]))[1]
    except ValueError:
        return False


def timeline_section(report: dict, full: bool = True, width=None, months: int = 12) -> dict:
    """Commits each person authored, one column per month: --full and Markdown only, since no rule reads it and
    it is the table most easily read as output per person. The twelve months ending at the last commit are the
    table at every width (fewer only where the history, or the --since window, is shorter): the default report
    used to drop the oldest months on a narrow terminal, so prometheus showed ten at 80 columns and twelve at
    160, and ranked on the months it showed, which listed different people at different widths. The rows are
    ranked on the twelve-month total. A name too long for the room the months leave is cut with an ellipsis
    (never under NAME_FLOOR characters); ranking, bots filtering and the row's key are still the real name. The
    month of the last commit is marked when that commit is not on its last day, and the caption says the rows
    are identities as the run merged them: prometheus listed George Krajcsovits and György Krajcsovits apart."""
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
    totals = {a: sum(per.get(m, 0) for m in span) for a, per in tl.items()}
    ranked = [a for a in sorted(totals, key=lambda a: -totals[a])
              if totals[a] > 0 and a not in bots and a not in credit_only and not identity.is_bot(a)]
    listed = ranked[:_limit("Timeline", full)]
    part = _part_month(report, span[-1])
    heads = [MONTHS[int(m[5:7]) - 1] + (PART_MARK if part and m == span[-1] else "") for m in span]
    columns = [("author", {"no_wrap": True})] + [(head, RIGHT) for head in heads]
    room = width - INDENT - MONTH_WIDTH * len(span) - (len(PART_MARK) if part else 0) if width else None
    # a month without a commit is 0, as zero is in every table: the dot it used to be is the report's separator
    rows = [(textfmt.cut(a, max(NAME_FLOOR, room)) if width else a, *[tl[a].get(m) or 0 for m in span]) for a in listed]
    months_shown = _month_label(span[0]) if len(span) == 1 else f"{_month_label(span[0])} → {_month_label(span[-1])}"
    caption = _fragments(f"{heads[-1]} = to {report['meta'].get('last_date')}, not a whole month" if part else None,
                         "a row = an identity as merged: one person under two names the run did not join has two rows")
    title = f"Timeline · {_shown(len(listed), len(ranked))}, {months_shown}, by commits in those months" if rows else "Timeline"
    return _section(title, columns, rows, note=None if rows else "no commits in the months shown", caption=caption if rows else None)


PART_MARK = "*"   # after the head of the Timeline's last month, when the last commit is before the month's end


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
    scored, tests = _hide_tests(scored, lambda h: h["entity"], full, classifier=cls)
    scored, deleted = _hide_deleted(scored, report, full, classifier=cls)
    scored, generated = _hide_generated(scored, lambda h: h["entity"], report, full, classifier=cls)
    scored, release = _hide_by(scored, lambda h: h["entity"], full, cls, {"release file"}, "release")
    hidden_note = _hidden("file", "files", tests, deleted, generated, release)
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
    pairs, tests = _hide_tests(pairs, lambda p: (p["entity"], p["coupled"]), full, classifier=cls)
    pairs, gone = _hide_gone(pairs, report, full, classifier=cls)
    pairs, release = _hide_release(pairs, full)
    pairs, example = _hide_example_pairs(pairs, full)
    pairs, header = _hide_header_pairs(pairs, full)
    pairs, locale = _hide_locale_pairs(pairs, full)
    pairs, vendor = _hide_vendor(pairs, lambda p: (p["entity"], p["coupled"]), full, report=report, classifier=cls)
    pairs, generated = _hide_generated(pairs, lambda p: (p["entity"], p["coupled"]), report, full, classifier=cls)
    beyond_tests = any((gone, release, example, header, locale, vendor, generated))
    hidden_note = _hidden("pair", "pairs", tests, gone, release, example, header, locale, vendor, generated)
    groups, cluster_note = [], None
    if full is not True:
        # a directory whose files all change together is one row; --full lists every pair
        groups, pairs = coupling.clusters(pairs)
        if groups:
            n_pairs = sum(g["pairs"] for g in groups)
            cluster_note = f"a directory row = its files change with each other ({textfmt.count(n_pairs, 'pair')})"
    limit = _limit("Change coupling", full)
    # One cell for the two files, the directory they share said once (textfmt.brace_pair): prometheus's two path
    # columns each lost their middle at 80 columns (`web/…/promql/format.tsx` beside `web/…/promql/serialize.ts`),
    # and in one column all five rows print whole. A directory whose files change as one is `dir/ (N files)`.
    rows = [(f"{g['dir']} ({g['files']:,} files)", f"≥{g['degree']}%", g["average-revs"]) for g in groups]
    rows += [(textfmt.brace_pair(p["entity"], p["coupled"]), f"{p['degree']}%", p["average-revs"]) for p in pairs[:max(limit - len(groups), 0) if limit else None]]
    # "together" is the share of their changes the two files made in one commit, the JSON's `degree`; "avg changes" its `average-revs`
    columns = [("files", PATH), ("together", RIGHT), ("avg changes", RIGHT)]
    if full is not True:
        columns, rows = _keep(columns, rows, ["files", "together"])
    note = None if rows else _empty_note("no pairs with 5 or more shared changes", hidden_note, "no source pairs with 5 or more shared changes")
    # what a pair means here (a pull request under squash merging, an edit otherwise) is how the table is made, not
    # what it holds: --full and Markdown say it, the default caption keeps to what is hidden and what a row is
    caveat = coupling.regime(report)[1] if full is not False else None
    title = f"Change coupling · {_shown(len(rows), len(groups) + len(pairs))}, by share of changes made together" if rows else "Change coupling"
    sec = _section(title, columns, rows, note=note, caption=_paragraphs(_fragments(hidden_note, cluster_note), caveat if rows else None))
    # A table of one pair that a finding already gives, with its degree, says nothing twice (_said_by_finding).
    # Only test pairs may have been hidden on the way: a count of historical or vendored pairs is said nowhere else.
    if full is False and not groups and not beyond_tests and len(pairs) == 1:
        sec["lone_pair"] = (pairs[0]["entity"], pairs[0]["coupled"])
    return sec


def _said_by_finding(sec: dict, findings) -> bool:
    """Whether a default section holds nothing the Findings above it do not say: the coupling table of one
    pair (coupling_section's `lone_pair`) when "Files that always change together" names that pair with its
    share. The watch list's rows used to be what made the table redundant, a partner among each row's reasons;
    its columns hold no partner, so a pair under that rule's 80% keeps its table."""
    pair = sec.get("lone_pair")
    if not pair:
        return False
    for f in findings or ():
        if (f.get("rule") or {}).get("id") == "tight_coupling":
            if any({p.get("a"), p.get("b")} == set(pair) for p in (f.get("evidence") or {}).get("pairs") or []):
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
    funcs, tests = _hide_tests(funcs, lambda f: f["file"], full, classifier=cls)
    funcs, vendor = _hide_vendor(funcs, lambda f: f["file"], full, report=report, classifier=cls)
    funcs, sample = _hide_by(funcs, lambda f: f["file"], full, cls, {"example code"}, "example")
    funcs, generated = _hide_generated(funcs, lambda f: f["file"], report, full, classifier=cls)
    hidden_note = _hidden("function", "functions", tests, vendor, sample, generated)   # a function is of the kind of file it is in
    limit = _limit("Complex functions", full)
    shown = funcs[:limit]
    rows = [(textfmt.ANONYMOUS if _nameless(f) else f["function"], _where(f), _ccn_cell(f), f["nloc"], f["params"]) for f in shown]
    suspects = sum(1 for f in shown if f.get("suspect"))
    suspect_note = f"{SUSPECT_MARK} = a span lizard may have mis-parsed ({suspects:,})" if suspects else None
    cut = sum(1 for f in shown if f.get("lizard_span"))
    cut_note = (f"{FLOOR_MARK} = lizard ended the function early ({cut:,}): its lines are the structure step's, "
                f"its complexity what lizard counted before it stopped") if cut else None
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
    # what is hidden, then the definitions: the head was lizard's "ccn", and the word needs its measure said once, where the column is
    caption = _fragments(None if note else hidden_note, partial, COMPLEXITY_DEFINITION, suspect_note, cut_note)
    title = f"Complex functions · {_shown(len(rows), len(funcs))}, by complexity" if rows else "Complex functions"
    return _section(title, columns, rows, note=note, caption=caption if rows else None)


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
    """The main owner and the second of an area, as the knowledge map prints them: [name, share, name, share],
    the shares in columns of their own so they line up and "gone" after a name that has stopped committing
    (one space, no brackets; blank means active). When several people hold exactly the top share there is no
    main owner to name and no second: the cell counts them ("shared by 12") and the share is what each of them
    holds, since the name the sort put first is the alphabet's. A second place that several hold equally is
    counted the same way."""
    held = area["owners"]

    def cell(at):
        if at >= len(held):
            return ["-", "-"]
        level = knowledge.tied(held, at)
        name, n = held[at]
        share = _pct(n, area["lines"])
        return [f"shared by {level}", share] if level > 1 else [f"{name}{' gone' if name in gone else ''}", share]
    return cell(0) + (["-", "-"] if knowledge.tied(held) > 1 else cell(1))


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
    counted = "in the tree now" if full is not True and tree else f"over every file in the history{f' since {since}' if since else ''}"
    if full is not True and tree:
        # a directory the history knows but HEAD does not is a layout that no longer exists; the rows are
        # filtered before the areas are built so a vanished layout cannot hide that one directory now dominates
        areas = [a for a in loss.areas(knowledge.present_rows(rows_all, tree), gone, base, dated) if knowledge.in_tree(a["area"], tree, base)]
        hidden = sum(1 for top in {knowledge.top_area(r["entity"], base) for r in rows_all} if not knowledge.in_tree(top, tree, base))
        hidden_note = _hidden("area", "areas", (hidden, "historical"))
    limit = _limit("Knowledge map", full)
    # the lines Co-authored-by trailers credit to a coding tool are not anyone's to own: the owners' shares are
    # of the people's lines, and the tools' part of each area is shown on its own
    assisted = ((report.get("tools") or {}).get("added") or {})
    if full is not True and tree:
        assisted = {e: n for e, n in assisted.items() if e in tree}
    rows, shares, outrank, any_gone = [], [], False, False
    # how many of an area's authors committed to it in the --gone window, as "recent/all" in the authors cell: a
    # count with no names, from the change analysis of 0.45 on (meta's ownership_recent); an output directory from before has no such count,
    # and its --full map is the one it always was. In the cell, not a column of its own, so the owners keep their width
    recent = dated
    for a in areas[:limit]:
        owners = _owner_cells(a, gone)
        any_gone = any_gone or any(knowledge.tied(a["owners"], at) == 1 and a["owners"][at][0] in gone for at in range(min(2, len(a["owners"]))))
        lost = f"{100 * a['lost_share']:.0f}%" if a["lines"] else "-"
        theirs = sum(n for e, n in assisted.items() if knowledge.in_area(e, a["area"], base))
        shares.append(round(100 * theirs / (a["lines"] + theirs)) if a["lines"] + theirs else 0)
        outrank = outrank or (theirs > 0 and theirs >= (a["owners"][1][1] if len(a["owners"]) > 1 else 0))
        authors = f"{a.get('recent', 0):,}/{a['authors']:,}" if recent else a["authors"]
        rows.append((a["area"], f"{a['lines']:,}", authors, lost if gone else "-", *owners, f"{shares[-1]}%"))
    # "added": the lines added to the area over its history, which under a bare "lines" head read as its size at
    # HEAD (prometheus: tsdb/ 138,105 in a repository of 357,025 lines). The title says the map is ranked by it.
    columns = [("area", PATH), ("added", RIGHT), ("authors", RIGHT), ("lost", RIGHT), ("main owner", {}), ("share", RIGHT), ("second", {}), ("share", RIGHT), ("agents", RIGHT)]
    # a column only when a row shown has a whole percent of it; in the default report only when the tools
    # together hold as much of an area as its second owner, where naming them apart changes who is listed
    shown = any(shares) and (full is True or outrank)
    drop = ({2, 3} if full is not True else set()) | (set() if shown else {8})   # authors and lost are --full's; two columns are headed "share", so by position
    columns = [c for n, c in enumerate(columns) if n not in drop]
    rows = [tuple(c for n, c in enumerate(r) if n not in drop) for r in rows]
    # What is hidden, then the definitions, in one paragraph. "owner" is by lines added, and the Truck factor
    # finding above counts files authored: prometheus's web/ is Julius Volz's by both and tsdb/ is not, and
    # nothing said the two were different measures.
    from .findings import truck_factor_absent
    measured = bool(report.get("doa")) and not truck_factor_absent(report)   # said only beside a truck factor to tell it from
    defined = ["owner = by lines added, which is not the Truck factor's measure (files authored)"] if measured else []
    if shown:
        defined.append("agents = the lines trailers credit to coding tools, told by their no-reply address")
    if recent:
        defined.append(f"authors = recent/all, recent being a commit to the area in {_window(months, report['meta'].get('last_date') or '')}")
    notes = [_fragments(hidden_note, *defined)]
    if rows and (left := named_like_project(report, areas[:limit])):
        notes.append(left)
    if full is not False:   # how the map was made, not what it holds: --full and Markdown
        from .findings import imports_gone_note
        if (left := imports_gone_note(report)):   # an import that is gone is no finding: said here, where ownership is read
            notes.append(left)
    title = f"Knowledge map · {_shown(len(rows), len(areas))} {'area' if len(areas) == 1 else 'areas'} {counted}, by lines added" if rows else "Knowledge map"
    sec = _section(title, columns, rows, note=None if rows else "no ownership data", caption=_paragraphs(*notes))
    sec["bars"] = False   # the shares are the owners', one beside each name: a bar on each would be two bar columns
    if rows and (any_gone or (gone and full is True)):   # --full's "lost" column is the gone people's share
        sec["gone"] = gone_definition(report) + (", measured over the whole history" if report["meta"].get("since") else "")
    return sec


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


# One order in the default report, --full and Markdown: the code (what to read first, then what is hard to change
# and what changes together), then the people. prometheus's default ran code, people, people, people, code, code.
# --full's own sections sit in their groups: the watch list's by component and Hotspots after it, Size by language
# closing the code, the Timeline after People, then the history (activity, age, changed lines, trailers) and what
# the tree declares (signing, agent files, the OSPS controls).
BUILDERS = [watch_section, documents_section, watch_by_component_section, hotspots_section, functions_section, coupling_section, size_section,
            knowledge_section, people_section, timeline_section, activity_section, age_section, lines_section, trailers_section, signing_section,
            agent_surface_section, osps_section]
# `--full` and Markdown only: Size, Activity and Code age are interesting once and rarely change what you
# do next; Hotspots ranks the files the watch list already leads with, by the same product; no rule reads the
# Timeline, and the People table's last-commit column says who is still here.
FULL_ONLY = {"size", "activity", "age", "hotspots", "signing", "trailers", "lines", "watch_by_component", "agent_surface", "osps", "timeline"}


def sections(report: dict, full: bool = True, width=None) -> list:
    """Every section as a dict with an `id` (the builder's name without _section), in the one order every
    rendering prints them (BUILDERS). The default terminal report (`full` False) leaves out the sections in
    FULL_ONLY; `full` True and Markdown keep them."""
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
    _define_gone(out)
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

PANEL_EDGES = 4   # a panel's two borders and its padding of one either side
SCORED_GLOSS = "source: not test, example, generated or vendored"   # what "scored" means, said where the count is


def _glue(text: str) -> str:
    """`text` with a no-break space where a line must not break (brief.wrap prints it as a space): between a
    number and the word after it ("18 sweeping", "23% surviving"), between a flag and the word after it
    ("--file-types all"), and either side of the "=" of a definition, so a term, its "=" and the first word of
    its meaning stay on one line."""
    import re
    text = re.sub(r"(?<=[\d%]) (?=[A-Za-z])", brief.NBSP, text)
    text = re.sub(r"(?<![\w-])(--[a-z][\w-]*) (?=\w)", lambda m: m.group(1) + brief.NBSP, text)   # a flag and its argument
    return text.replace(" = ", f"{brief.NBSP}={brief.NBSP}")


def wrapped(text: str, width) -> list:
    """`text` as lines of at most `width`: broken at spaces, a separator kept at the end of the line before it,
    and never between a number and its noun or a term and its "=" (_glue). `width` None is one line."""
    return [text] if width is None else brief.wrap(_glue(text), max(width, 20))


def _fix_share(report: dict):
    """(share of commits that are fixes, the reverts as words), each None when the log does not say: the header's
    commits row and, in other words, the Markdown export's pulse line."""
    act = report.get("activity") or {}
    total = sum(act.get("by_weekday") or [])
    fixes = _pct(act["fix_commits"], total) if act.get("fix_commits") is not None and total else None
    reverts = None
    if act.get("revert_commits") and total:
        share = _pct(act["revert_commits"], total)
        reverts = textfmt.count(act["revert_commits"], "revert") if share == "0%" else f"{share} are reverts"
    return fixes, reverts


def _left_out_words(report: dict):
    """'18 sweeping commits, not counted in churn, coupling or ownership', with the commits the repository
    declares in .git-blame-ignore-revs beside them; None when the change analysis left nothing out (or predates
    the record). Said once, in the header: prometheus's report said it under the Watch list and again in the
    Sweeping commits finding, and the coupling and ownership tables that leave them out as well said nothing."""
    act = report.get("activity") or {}
    swept, declared = [c for c in act.get("sweeping") or [] if not c.get("declared")], act.get("ignored_revs") or 0
    parts = ([textfmt.count(len(swept), "sweeping commit")] if swept else []) + ([f"{declared:,} declared in .git-blame-ignore-revs"] if declared else [])
    return (" and ".join(parts) + ", not counted in churn, coupling or ownership") if parts else None


def header_rows(report: dict, full: bool = False) -> list:
    """The header as labelled rows, [(label, [(fact, style)])], a label describing everything on its row:
    history (commits, span, the --since window, identities), scope (a --path run), steps (the ones that did not
    finish, first after history: every number below may be missing because of them), files (tracked, with code,
    scored: three counts with three denominators, which prometheus's header gave as "1,056 files" and left the
    653 that every ranking is over to a caption), code (lines, languages, the surviving share with its source),
    commits (fixes, reverts), left out (the sweeping commits no count holds) and signing. A row with nothing
    to say is not there. Signing stays here as its own row only until the Supply chain section (plan item A10)
    gives it a home; nothing in this header reads it."""
    s = summary(report)
    rows = []
    history = [(f"{s['commits']:,} commits", "bold"), (f"{s['first_date']} → {s['last_date']}", "")]
    if s["since"]:
        history.append((f"since {s['since']}", "yellow"))
    history.append((textfmt.count(s["identities"], "identity", "identities"), ""))
    rows.append(("history", history))
    if s["scope"]:
        rows.append(("scope", [(scope.label(s["scope"]), "bold yellow"), (scope.REPOSITORY_WIDE, "dim")]))
    unfinished = _unfinished(report)
    if unfinished:
        rows.append(("steps", [(part, "") for part in unfinished]))
    buckets = (report.get("coverage") or {}).get("files") or s["coverage"] or {}
    files = []
    if buckets:
        ratio = scored_phrase(report)   # "17 of 227 files scored", when what no table carries outnumbers what is scored
        every = bool(full and s["coverage"])   # --full counts every bucket
        if every or not ratio:
            files.append((f"{sum(buckets.values()):,} tracked", ""))
        files.append((f"{s['files']:,} with code", ""))
        if every:
            files += [(part, "") for part in classify.coverage_line(s["coverage"]).split(": ", 1)[1].split(SEP)]
        else:
            files.append((f"{ratio or format(buckets.get('scored', 0), ',') + ' scored'} ({SCORED_GLOSS})", ""))
    else:
        files.append((f"{s['files']:,} with code", ""))
    rows.append(("files", files))
    unranked = coverage_phrases(report)   # [share of lines not ranked, the flag that includes them, commits outside the scored files]
    code = [(f"{s['lines']:,} lines", ""), (", ".join(s["languages"]) or "unknown", "")]
    cohorts = report.get("cohorts") or {}
    if cohorts:
        label, lines = max(cohorts.items(), key=lambda kv: kv[1])
        code.append((f"{_pct(lines, sum(cohorts.values()))} surviving from {label.replace('Code added in ', '')}{_by_source(report)}", ""))
    elif _age_status(report) != "run":
        code.append((_age_reason(report), ""))   # the age table is --full only, so this is where a timeout shows
    code += [(part, "") for part in unranked[:2]]
    rows.append(("code", code))
    fixes, reverts = _fix_share(report)
    commits = ([(f"{fixes} are fixes", "")] if fixes else []) + ([(reverts, "")] if reverts else []) + [(part, "") for part in unranked[2:]]
    if commits:
        rows.append(("commits", commits))
    left_out = _left_out_words(report)
    if left_out:
        rows.append(("left out", [(left_out, "")]))
    signed = signing_phrase(report)
    if signed:   # A10 moves this row to the Supply chain section
        rows.append(("signing", [(signed, "")]))
    return rows


LABEL_GAP = 2   # between a header label and its value


def header(report: dict, findings: list = (), full: bool = False, width=None) -> Panel:
    """The header: a title line (the repository, its branch and commit) and header_rows as a label grid, the
    labels padded to the longest and a value that does not fit wrapped with a hanging indent. The finding
    tally is the Findings title's (tally_title). `findings` is not read; it stays for the callers that pass it."""
    s = summary(report)
    inner = width - PANEL_EDGES if width else None
    rows = header_rows(report, full)
    branch = f"branch {s['branch']}" + (f" @ {s['commit'][:8]}" if s["commit"] else "")
    title = f"[bold]{escape(s['name'])}[/bold]{SEP}{escape(branch)}"
    if inner is not None and len(s["name"]) + len(SEP) + len(branch) > inner - 2:   # a title the border would cut: the branch is a row
        title = f"[bold]{escape(s['name'])}[/bold]"
        rows.insert(0, ("branch", [(branch[len("branch "):], "")]))
    pad = max(len(label) for label, _ in rows) + LABEL_GAP
    body = Text()
    for n, (label, facts) in enumerate(rows):
        lines = wrapped(SEP.join(text for text, _ in facts), inner - pad if inner is not None else None)
        for i, line in enumerate(lines):
            piece = Text(line)
            for text, style in facts:
                if style:
                    piece.highlight_words([text], style)
            body.append(f"{label if i == 0 else '':<{pad}}", style="dim")
            body.append_text(piece)
            body.append("\n" if n < len(rows) - 1 or i < len(lines) - 1 else "")
    return Panel(body, title=title, title_align="left", border_style="blue")


UNMEASURED_GLOSSES = ("by rules not measured for precision yet", "not measured for precision yet", "not measured yet")
PANEL_TITLE_EDGES = 6   # what a panel's border takes beside its title: a corner, a dash and a space either side


def tally_title(findings: list, gloss: bool = False, width: int = None) -> str:
    """'Findings · 4 warnings ▲ · 10 notes ● · 5 by rules not measured for precision yet': the tally where the
    findings are, each word beside the mark the entries below carry, so the marks can be counted against it.
    'Findings' alone when there are none. With `gloss`, the last part counts the findings that carry
    brief.UNMEASURED_TAG after their title and says once what the tag means; in a title the border of an
    80-column box would cut, it says so in fewer words (UNMEASURED_GLOSSES, the first that fits `width`)."""
    counts = {sev: sum(1 for f in findings if f["severity"] == sev) for sev in SEVERITY_MARK}
    words = {"critical": lambda n: f"{n:,} critical", "warning": lambda n: textfmt.count(n, "warning"), "info": lambda n: textfmt.count(n, "note")}
    parts = [f"{words[sev](n)} {SEVERITY_MARK[sev]}" for sev, n in counts.items() if n]
    title = SEP.join(["Findings"] + parts)
    unmeasured = sum(1 for f in findings if f.get("unjudged")) if gloss else 0
    if not unmeasured:
        return title
    fits = [g for g in UNMEASURED_GLOSSES if width is None or len(title) + len(SEP) + len(f"{unmeasured:,} {g}") <= width - PANEL_TITLE_EDGES]
    return f"{title}{SEP}{unmeasured:,} {fits[0] if fits else UNMEASURED_GLOSSES[-1]}"


def _unmeasured(g: dict) -> bool:
    """Whether an entry is a rule's that nobody has measured (findings.UNJUDGED, the finding's `unjudged`)."""
    return bool(g["findings"]) and all(f.get("unjudged") for f in g["findings"])


def _titled(g: dict, style: str) -> Text:
    """An entry's title, in its severity's colour, and the dim tag after it when its rule is not measured yet:
    the colour ends with the title."""
    body = Text(g["title"], style=style)
    if _unmeasured(g):
        body.append(f" {brief.UNMEASURED_TAG}", style="dim")
    return body


def _short_entry(g: dict, report: dict, width: int, printed: dict, style: str, found: list = None) -> Text:
    """One entry of the default report's Findings: the title, then each finding's short form (brief.short):
    the statement, its subject lines indented two, and the step under ↳ with its continuation indented two.
    The lines come wrapped, so a path or a version is never split. An entry holding several findings of one
    title shows brief.SUBJECT_LINES of them and counts the rest.

    A note from a rule not measured yet takes the compact shape instead: title, tag, ': ' and the statement
    in the default foreground, brief.COMPACT_LINES lines at most and no step (brief.compact). prometheus's
    report folded five such findings, one of them a warning, into a closing line, so its title counted a
    warning no ▲ stood for; now every finding owns one mark. A warning from such a rule is an entry like any
    other, with the tag after its title."""
    body = _titled(g, style)
    if _unmeasured(g) and g["severity"] == "info" and len(g["findings"]) == 1:
        lead = len(g["title"]) + 1 + len(brief.UNMEASURED_TAG) + 2
        lines = brief.compact(g["findings"][0], report, width, lead, printed, found)
        body.append(":" + (f" {lines[0]}" if lines[0] else ""))
        for line in lines[1:]:
            body.append(f"\n{line}")
        return body
    shorts = [brief.short(f, report, width, printed, found) for f in g["findings"]]
    steps = []
    for s in shorts[:brief.SUBJECT_LINES]:
        for line in s["statement"]:
            body.append(f"\n{line}", style="dim" if len(shorts) == 1 else "")
        for line in s["subjects"]:
            body.append(f"\n  {line}", style="dim" if len(shorts) == 1 else "")
        if s["step"] and s["step"] not in steps:
            steps.append(s["step"])
    if len(shorts) > brief.SUBJECT_LINES:
        body.append(f"\nand {len(shorts) - brief.SUBJECT_LINES:,} more")
    for step in steps:
        body.append("\n↳ " + "\n  ".join(step), style="dim italic")
    return body


PROSE_WIDTH = 100   # a finding's lines are no longer than this on a terminal wider than it


def findings_panel(findings: list, report: dict = None, full: bool = True, width: int = None, printed: dict = None) -> Panel:
    """The Findings box. `full` False is the default report: each finding in its short form (brief.py), for
    which `width` is the terminal's and `printed` the report's sections by id, so a "(see Section)" pointer
    names only a table that is there. `full` True spells every finding out, as the Markdown export does.
    Either way every finding is an entry with its own mark, and one from a rule not measured yet has the tag
    after its title, which the box's title glosses (tally_title)."""
    passed = checks_passed(report or {}, footer=bool(full) or not footer_said(report or {}))
    absent = not_computed_line(report) if report else None
    if not findings and not passed and not absent:
        return Panel(Text("Nothing flagged.", style="green"), title="Findings", title_align="left", border_style="green")
    grid = Table.grid(padding=(0, 1))
    grid.add_column(no_wrap=True)
    grid.add_column(overflow="fold")
    inner = min((width or PROSE_WIDTH + PANEL_EDGES + 2) - PANEL_EDGES - 2, PROSE_WIDTH)   # less the box, the mark and its gap
    for g in textfmt.group_findings(findings):
        style = SEVERITY_STYLE[g["severity"]]
        if not full:
            grid.add_row(Text(SEVERITY_MARK[g["severity"]], style=style), _short_entry(g, report or {}, inner, printed, style, findings))
            continue
        body = _titled(g, style)
        for item in g["items"]:
            body.append(f"\n{item}", style="dim" if len(g["items"]) == 1 else "")
        for advice in g["advice"]:
            body.append(f"\n↳ {advice}", style="dim italic")
        grid.add_row(Text(SEVERITY_MARK[g["severity"]], style=style), body)
    if (passed or absent) and not findings:
        grid.add_row(Text(""), Text("Nothing flagged.", style="green"))
    for title, detail in passed:   # problems first, then the checks that passed
        grid.add_row(Text("✔", style="green"), Text(title, style="green").append(f"\n{detail}", style="dim"))
    if absent:   # last: what was found, what passed, then what was never measured, so its silence is not a pass
        grid.add_row(Text("·", style="dim"), Text(absent, style="dim"))
    return Panel(grid, title=tally_title(findings, gloss=True, width=width), title_align="left", border_style=SEVERITY_STYLE[findings[0]["severity"]] if findings else "green")


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
    """A section's name without its qualifier: 'Watch list' of 'Watch list · 5 of 15, ranked by …' and of a
    title that still carries its qualifier in brackets."""
    return title.split(" · ")[0].split(" (")[0]


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
# A "tail" column is the last text cell of a row (the watch list's "look at first"): it is cut at its end with an
# ellipsis, and only once every path has given up its directories, so a table's overflow has one order: a path loses
# middle directories, then the last text cell is cut, and a number never is.
NAME_KEEP, PROSE_KEEP, PROSE_FLOOR, CUT_FLOOR, PATH_LEAST, NAME_LEAST = 32, 40, 20, 12, 24, 16
GAP = 2         # between two columns: one of padding after a cell and the SIMPLE_HEAD box's divider
LOOSE_GAP = 3   # the drawing before the grid, padding either side: the Change risk section's, whose stored copy
                # (tests/golden/strings.txt) the watch list's change leaves byte for byte


def _gap(sec: dict) -> int:
    return LOOSE_GAP if sec.get("loose") else GAP


def _bars(sec: dict) -> bool:
    """Whether a section's share column carries inline bars: only where there is no bar column already, and
    not in a table that says no (`bars` False: People and the Knowledge map, which are in the default report)."""
    return sec.get("bars", True) and "share" in sec["columns"] and "" not in sec["columns"]


def _kind(name: str, opts: dict) -> str:
    """How a column may give way: "path" (directories elided), "name" (cut in the middle), "prose" (wraps at
    words) or "fixed" (a number, a bar: never cut)."""
    if opts.get("kind"):
        return opts["kind"]
    if opts.get("justify") == "right" or name == "":
        return "fixed"
    return "prose" if opts.get("ratio") else "name"


def _braced(text: str):
    """(shared directory, one rest, the other rest) of a cell of two paths in braces (textfmt.brace_pair), or None."""
    head, brace, group = text.partition("{")
    if not brace or not group.endswith("}") or "," not in group:
        return None
    a, _, b = group[:-1].partition(",")
    return head, a, b


def _cut_braced(text: str, width: int) -> str:
    """A cell of two paths in braces in at most `width` characters, by the order every path gives way in: the
    directory the two share loses its middle first, then each path inside the braces loses its own directories
    (the longer first), and only then is the cell cut in its middle. The file names stay whole as long as they can."""
    head, a, b = _braced(text)

    def form(h, x, y):
        return f"{h}{{{x},{y}}}"
    if head:
        head = textfmt.shorten_path(head, max(width - len(form("", a, b)), 0))
        if len(form(head, a, b)) <= width:
            return form(head, a, b)
    rest = {"a": a, "b": b}
    for k, other in (("a", "b"), ("b", "a")) if len(a) >= len(b) else (("b", "a"), ("a", "b")):
        rest[k] = textfmt.shorten_path(rest[k], max(width - len(form(head, "", rest[other])), 0))
        if len(form(head, rest["a"], rest["b"])) <= width:
            break
    out = form(head, rest["a"], rest["b"])
    return textfmt.cut_middle(out, width) if width > 0 else out   # at no width: the shortest form that keeps both names


def _shortest(text: str) -> str:
    """The shortest form of a path cell that still keeps its file name, or its two, whole."""
    return _cut_braced(text, 0) if _braced(text) else textfmt.shorten_path(text, 0)


def _fit_cell(kind: str, text: str, width: int, others=()) -> str:
    if len(text) <= width:
        return text
    if kind == "path":
        return _cut_braced(text, width) if _braced(text) else textfmt.cut_path(text, width, others)
    if kind == "tail":
        return textfmt.cut(text, width)
    return textfmt.cut_middle(text, width)


def _base(cell: str) -> str:
    if _braced(cell):
        return cell[cell.index("{"):]   # two files in one cell: no tracked file is called that, and no other row
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
    bars = _bars(sec)
    kinds = [_kind(c, o) for c, o in zip(cols, opts)]
    rows = sec["rows"]
    cells = [max(_cell(c, r[i], bars).cell_len for r in rows) for i, c in enumerate(cols)]
    heads = [cell_len(c) for c in cols]
    head_word = [max((cell_len(w) for w in c.split()), default=0) for c in cols]
    want = [max(a, b) for a, b in zip(cells, heads)]

    def room(keep):
        return width - INDENT - _gap(sec) * (len(keep) - 1)
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
            return min(want[i], max(head_word[i], max(cell_len(_shortest(r[i])) for r in rows)))
        return min(want[i], max(head_word[i], NAME_KEEP))

    # the least each column can take: a number whole, a name or path cut to CUT_FLOOR, prose folded at PROSE_FLOOR
    least = [min(want[i], max(head_word[i], PROSE_FLOOR if k == "prose" else CUT_FLOOR)) if k != "fixed" else max(cells[i], head_word[i])
             for i, k in enumerate(kinds)]
    tails = [i for i, k in enumerate(kinds) if k == "tail"]

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
        elif k == "tail":
            floor.append(want[i])   # whole until the paths have given what they can
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
    for floors, give, among in ((floor, ("path", "name"), keep), (floor, ("prose",), keep), (least, ("tail",), [i for i in keep if i in tails]),
                                (least, ("path", "name", "prose"), [i for i in keep if i not in dirs]), (least, ("path",), dirs)):
        while excess() > 0:
            cand = [i for i in among if kinds[i] in give and widths[i] > floors[i]]
            if not cand:
                break
            widths[max(cand, key=lambda i: widths[i])] -= 1
    fitted = [tuple(_fit_cell(kinds[i], r[i], widths[i], namesakes[i][n] if i in namesakes else ()) if kinds[i] in ("path", "name", "tail") else r[i] for i in keep)
              for n, r in enumerate(rows)]
    col_opts = [dict(opts[i], width=widths[i]) for i in keep]
    caption = sec.get("caption")
    if dropped:
        left = f"{textfmt.join_and(dropped)} left out at {width} columns; a wider terminal or --markdown shows {'it' if len(dropped) == 1 else 'them'}"
        caption = f"{caption}\n{left}" if caption else left
    return dict(sec, columns=[cols[i] for i in keep], col_opts=col_opts, rows=fitted, caption=caption)


def rich_table(sec: dict):
    """A table for a section: no title (the caller prints the heading) and no caption (section_block prints it
    under the table, so a table is as wide as its columns and never as wide as its caption), coloured headers,
    bold key column, dimmed secondary columns, zebra rows, threshold colours. A `loose` section keeps the
    drawing from before the grid: wider gaps and the caption inside the table."""
    key = KEY_METRIC.get(_base_title(sec["title"]))
    kw = {}
    if sec.get("loose"):
        if sec.get("caption"):
            kw = {"caption": escape(sec["caption"]), "caption_justify": "left", "caption_style": CAPTION_STYLE}   # a name like renovate[bot] is not markup
        kw["min_width"] = max((len(line) for line in (sec.get("caption") or "").split("\n")), default=0)
    else:
        kw["padding"] = (0, 1, 0, 0)   # with the box's divider, GAP between two columns
    bars = _bars(sec)
    t = Table(box=box.SIMPLE_HEAD, show_edge=False, pad_edge=False, header_style=HEADER,
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


CAPTION_STYLE = "dim italic"
UNDER_INDENT = 2   # a row's line of detail, in from the row's first cell


class _Under:
    """A table with one line of text under each of its rows (the watch list's remaining reasons in --full),
    indented and wrapped at its separators. The table is drawn first and its lines are passed through with the
    detail put after each row's, which a row that is one line makes exact: the rows come after the rule under
    the column heads, and fit() lets no cell of these tables wrap."""

    def __init__(self, table, under: list):
        self.table, self.under = table, under

    def __rich_measure__(self, console, options):
        from rich.measure import Measurement
        return Measurement.get(console, options, self.table)

    def __rich_console__(self, console, options):
        from rich.segment import Segment
        lines = console.render_lines(self.table, options, pad=False)
        rule = next((i for i, line in enumerate(lines) if (text := "".join(seg.text for seg in line).strip()) and set(text) <= set("─ ")), -1)
        for i, line in enumerate(lines):
            yield from line
            yield Segment.line()
            n = i - rule - 1
            if rule >= 0 and 0 <= n < len(self.under) and self.under[n]:
                for part in brief.wrap(self.under[n], max(options.max_width - UNDER_INDENT, 20)):
                    yield from console.render(Text(" " * UNDER_INDENT + part, style="dim"), options)


def caption_lines(sec: dict, width=None) -> list:
    """A section's caption as the lines to print: each paragraph wrapped at spaces, a " · " kept at the end of
    the line before it, so no line starts with a separator, and a definition's term kept with its "=" (wrapped).
    `width` None leaves each paragraph a line."""
    paragraphs = (sec.get("caption") or "").split("\n") if sec.get("caption") else []
    if width is None:
        return paragraphs
    return [line for par in paragraphs for line in wrapped(par, width - INDENT)]


def heading(sec: dict) -> Text:
    symbol = SYMBOLS.get(_base_title(sec["title"]), "•")
    return Text(f"{symbol} ", style=ACCENT) + Text(sec["title"], style=f"bold {ACCENT}")


def section_block(sec: dict, width=None):
    """Heading plus table plus caption, or heading plus a dim note for an empty section. With a `width`, the
    table is fitted to it first (fit) and the caption wrapped to it."""
    if not sec["rows"] and sec["note"]:
        return heading(sec) + Text(f": {sec['note']}", style="dim")
    fitted = fit(sec, width)
    table = rich_table(fitted)
    if fitted.get("loose"):
        return Group(heading(sec), Padding(table, (0, 0, 0, INDENT)))
    if fitted.get("under") and any(fitted["under"]):
        table = _Under(table, fitted["under"])
    parts = [heading(sec), Padding(table, (0, 0, 0, INDENT))]
    lines = caption_lines(fitted, width)
    if lines:
        parts.append(Padding(Text("\n".join(lines), style=CAPTION_STYLE), (0, 0, 0, INDENT)))
    return Group(*parts)


def print_section(console: Console, sec: dict) -> None:
    """Blank line, then the section's heading and table (or note), fitted to the console's width."""
    console.print(Text(""))
    console.print(section_block(sec, console.width))


def report(report: dict, findings: list, console: Console, full: bool = False, risk: dict = None, base: str = None, compare: dict = None) -> None:
    console.print(header(report, findings, full=full, width=console.width))
    secs = [s for s in sections(report, full=full, width=console.width) if not _said_by_finding(s, findings)]
    by_id = {s["id"]: s for s in secs}
    console.print(findings_panel(findings, report, full=full, width=console.width, printed=by_id))   # a short finding may point at its table below
    if compare is not None:
        print_section(console, compare_section(compare))
    # One section under another at every width: small tables used to sit side by side from 100 columns, which
    # changed the order of the lines with the terminal and put two tables on every copied line. A wider terminal
    # un-wraps cells and un-elides paths, and changes nothing else.
    for sec in secs:
        print_section(console, sec)
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
    if not full:
        # The one pointer the default report keeps, now that no caption ends "--full shows them". It is plan item
        # A10's to replace, with the closing index that names the sections only --full prints.
        console.print(Text(FULL_POINTER, style="dim"))
    console.print(Text(results_line(report), style="dim"), soft_wrap=True)


FULL_POINTER = "--full shows the hidden rows and more sections"


def excerpt(report: dict, findings: list, console: Console, full: bool = False) -> None:
    """The report's opening on its own: the header, the Findings title, whose tally counts the findings, and
    the watch list. What the README's text block shows; the findings themselves are in the full report."""
    console.print(header(report, findings, width=console.width))
    console.print(Text(tally_title(list(findings)), style="bold"))
    print_section(console, next(sec for sec in sections(report, full=full, width=console.width) if sec["id"] == "watch"))


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
    under = sec.get("under")   # what a terminal prints under each row is a last column here
    out.append("| " + " | ".join(sec["columns"] + ([sec.get("under_head") or ""] if under else [])) + " |")
    out.append("| " + " | ".join(["---:" if o.get("justify") == "right" else "---" for o in sec["col_opts"]] + (["---"] if under else [])) + " |")
    out += ["| " + " | ".join(_md_cell(c) for c in list(row) + ([under[n]] if under else [])) + " |" for n, row in enumerate(sec["rows"])]
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
            *([rl + "  "] if rl else []), *([] if full else ["`--markdown --full` shows the hidden rows.  "]), results_line(report), ""]
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

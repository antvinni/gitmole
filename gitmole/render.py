"""Turn a loaded report into sections, then draw them with rich or as Markdown/JSON.

The default report is the tighter one: the columns you actually read, capped rows, elided
paths. `full` restores every column and row (Markdown export is always full)."""
from __future__ import annotations

import json
import os

from rich.console import Console
from rich.text import Text

from . import brief, classify, coupling, deps, filetypes, hotspots, identity, knowledge, leaks, loss, provenance, scope, textfmt, trend, watch

# The report's whole palette: bold, dim, yellow for a warning and red for a critical, and nothing else. The
# default render of prometheus held 23 different escape sequences, among them a truecolour blue, purple and pink
# and a near-black row background, which is unreadable on a light theme and noise in a CI log. Yellow and red
# are a severity's and go on a finding's mark and title (and a scan's verdict) only; a note has no colour; a
# section title and a table's first column are bold; captions, rules, column heads and labels are dim; a
# statement, a step and every number are in the terminal's own foreground. The logo banner (banner.py) keeps
# its own colours: it is not the report.
BOLD, DIM = "bold", "dim"
SEVERITY_STYLE = {"critical": "bold red", "warning": "yellow", "info": ""}

# the Timeline's month columns: each is 3 characters wide plus the 2 of GAP in front of it, a clean 5 per
# month. The section itself is indented by 2. The twelve
# months are the table at every width: when a name leaves them no room the name gives way, cut to what is left,
# and NAME_FLOOR is the fewest characters of it still shown before the ellipsis (eight keeps most short names,
# and the start of longer ones, recognisable). The year needs INDENT + NAME_FLOOR + 12 × MONTH_WIDTH = 70 columns.
MONTH_WIDTH, INDENT, NAME_FLOOR = 5, 2, 8

SYMBOLS = {"Size by language": "▤", "People": "◉", "Activity": "◔", "Timeline": "▦", "Hotspots": "◆", "Change coupling": "⟷",
           "Surviving code by year written": "◷", "Net lines added by year": "◷", "Paths in history by year last changed": "◷",
           "Knowledge map": "⌂", "Repo health": "✚", "Portfolio": "▣", "File types": "▥", "Complex functions": "λ", "Watch list": "◎",
           "Change risk": "◈", "Since last report": "⇄", "Most-changed documents": "✎", "Supply chain": "◧"}
SECTION_MARK = "•"   # in front of the title of a section with no pictogram of its own
SEVERITY_MARK = {"critical": "✖", "warning": "▲", "info": "●"}
STEP_MARK = "↳"
RULE_MARK = "─"
BAR_MARK, BLOCK_MARK = "▰", "█"
# How a column lies and how it gives way when a row does not fit (fit): "justify" right for a number, and a
# "kind" of path (it loses middle directories), tail (the last text cell: cut at its end with an ellipsis once
# every path has given its directories) or fixed (never cut). A column with a "ratio" is prose, which gives way
# as a tail does. No cell is ever wrapped onto a second line.
RIGHT = {"justify": "right"}
PATH = {"kind": "path"}
WHOLE = {"kind": "fixed"}   # a short text cell that is never cut, as a number is not: a share with "gone" after it
TAIL = {"kind": "tail"}

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
    return BLOCK_MARK * int(width * part / whole) if whole else ""


def _number(c) -> str:
    """A cell as text: a count takes its thousands separator here, once for every table, so 1061 commits in
    People and 18647 in the header no longer sit beside 357,025 lines (prometheus). Zero is 0. A year, a
    line number or anything else that is not a count reaches a table as text already."""
    return f"{c:,}" if isinstance(c, int) and not isinstance(c, bool) else str(c)


def _section(title, columns, rows, note=None, caption=None, under=None) -> dict:
    """columns: list of (name, column options: RIGHT, PATH, WHOLE, TAIL). rows: lists of cells, a count as an
    int (see _number). `caption` is one paragraph a line, each wrapped at its separators when it is drawn.
    `under` is one line of text per row, drawn indented beneath it on a terminal and as a last column in
    Markdown ("under_head" names it)."""
    sec = {"title": title, "columns": [c[0] for c in columns], "col_opts": [c[1] for c in columns],
           "rows": [[_number(c) for c in r] for r in rows], "note": note, "caption": caption}
    if under is not None:
        sec["under"] = list(under)
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


def _signing_parts(report: dict):
    """(head, mechanisms, last year, forge) of the signing phrase, each '' when there is nothing to say; None
    without the step."""
    sig = report.get("signing") or {}
    if not sig.get("commits"):
        return None
    if not sig.get("signed"):
        return "no commits signed", "", "", ""
    forge = sig.get("forge") or {}
    by_forge, forge_mix = forge.get("signed") or 0, forge.get("mechanisms") or {}
    last = sig.get("last_year") or {}
    own = sig["signed"] - by_forge
    mechanisms = {k: v - forge_mix.get(k, 0) for k, v in (sig.get("mechanisms") or {}).items()} if by_forge else (sig.get("mechanisms") or {})
    mix = ", ".join(f"{k} {_pct(v, sig['commits'])}" for k, v in sorted(mechanisms.items(), key=lambda kv: (-kv[1], kv[0])) if v > 0)
    tail = f", {_pct(last['signed'] - (last.get('forge_signed') or 0) if by_forge else last['signed'], last['commits'])} of the last year's" if last.get("commits") else ""
    if not by_forge:
        return f"{_pct(sig['signed'], sig['commits'])} of commits signed", f" ({mix})", tail, ""
    if not own:
        head, mix, tail = "no commits signed by their authors", "", ""
    else:
        head, mix = f"{_pct(own, sig['commits'])} of commits signed by their authors", f" ({mix})"
    share = _pct(by_forge, sig['commits'])
    return head, mix, tail, "" if share == "0%" else f"; {share} signed by the forge on merge"


def signing_phrase(report: dict):
    """'33% of commits signed (ssh 28%, gpg 6%), 50% of the last year's', or 'no commits signed'; None
    without the step. Read from the commit objects, nothing verified: evidence, not a level. When the
    forge committed and signed some of them itself (a merge from the web), those are named apart: its
    signature says nothing about who wrote the change."""
    parts = _signing_parts(report)
    return "".join(parts) if parts else None


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


RISK_WHY = "why"   # the Markdown column for what a terminal prints under a Change risk row


def risk_section(risk: dict, base: str, full=True) -> dict:
    """The files a change touches, each with its watch score as a bar scaled to the repo's worst file and, under
    its row, why it scores: the reasons the watch list gives the file, whole. They were a third column that
    wrapped inside its cell, in a drawing of its own (gaps of three, the caption as wide as the table); a cell
    never wraps now, and cut to its column a file's reasons would be a dozen words of some thirty. Under the row
    is where --full's watch list puts the same reasons. Markdown keeps them as its last column."""
    rows_all = risk["files"]
    limit = _limit("Change risk", full, cap=RISK_CAP)
    top = risk["max_score"] or 1.0
    rows, why = [], []
    for r in rows_all[:limit]:
        imported = watch.dependents_phrase(r.get("dependents"))
        rows.append((r["file"], BAR_MARK * round(10 * r["score"] / top) if r["score"] else ""))
        why.append(" · ".join(r["reasons"] + ([imported] if imported else [])))
    columns = [("file", PATH), ("risk", {})]
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
    sec = _section(f"Change risk ({len(rows_all):,} files since {base})", columns, rows,
                   note=None if rows else f"no files changed since {base}", caption="\n".join(notes) or None, under=why if rows else None)
    sec["under_head"] = RISK_WHY
    return sec


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
    columns = [("weekday", {}), ("commits", RIGHT), ("share", RIGHT), ("", {})]
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
    columns = [("author", {})] + [(head, RIGHT) for head in heads]
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
    columns = [("component", PATH), ("share", RIGHT), ("top files", TAIL)]
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
    columns = [("period", {}), ("commits", RIGHT), ("lines added", RIGHT), ("moved", RIGHT), (f"churned in {ln.get('churn_days', 14)} days", RIGHT)]
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
    return _section("Surviving code by year written", [("year", {}), ("lines", RIGHT), ("share", RIGHT), ("", {})], rows,
                    note=None if rows else "no age data", caption=f"counted{_by_source(report)[1:]}" if rows and _by_source(report) else None)


def age_fallback_section(report: dict) -> dict:
    """When the blame pass did not run: net lines added per year from the log, or failing that,
    paths by the year they were last changed."""
    reason = _age_reason(report)
    net = (report.get("activity") or {}).get("net_by_year") or {}
    if net:
        total = sum(v for v in net.values() if v > 0)
        rows = [(y, f"{v:,}", _pct(v, total) if v > 0 else "-", _bar(v, total) if v > 0 else "") for y, v in net.items()]
        return _section("Net lines added by year", [("year", {}), ("net lines", RIGHT), ("share", RIGHT), ("", {})], rows,
                        caption=f"{reason}; approximation from the log, not a blame")
    last = report["meta"].get("last_date") or ""
    columns = [("year", {}), ("paths", RIGHT), ("share", RIGHT), ("", {})]
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
    columns = [("function", {}), ("file", PATH), ("complexity", RIGHT), ("lines", RIGHT), ("params", RIGHT)]
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
    return _section("OSPS Baseline", [("control", WHOLE), ("asks", TAIL), ("result", WHOLE), ("evidence", TAIL)],
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
    return _section("Agent surface", [("kind", WHOLE), ("where", PATH), ("what", TAIL)], rows, caption=caption)


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
    columns = [("change", {}), ("what", TAIL)]
    # an empty section prints heading + note and drops the caption (section_block, _md_section), so when
    # there is nothing to show, the caption's own lines fold into the note instead of vanishing with it
    note = None if rows else "; ".join(["nothing changed"] + lines)
    sec = _section("Since last report", columns, rows, note=note, caption="\n".join(lines))
    # A terminal draws it as a label grid, the change as the label and what changed wrapped under its own start:
    # a persisting finding's title with the counts that moved is longer than a cell at 80 columns, a cell never
    # wraps, and cut at its end the row would lose the counts it is there for. Markdown keeps the two columns.
    sec["grid"] = True
    return sec


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


def checks_passed(report: dict) -> list:
    """The checks that ran and passed, secrets first, for the Markdown export's **ok** lines. The terminal
    report says them where it says every scan's result, verdict first, in the Supply chain section
    (supply_chain_rows): the Findings box had a ✔ line for each and the footer said the same again."""
    return [p for p in (secrets_pass(report), dependencies_pass(report)) if p]


def _unreachable_words(report: dict, short: bool) -> str:
    """'; no unreachable objects…' or '; 3 unreachable blobs scanned too', or '' for a run without the sweep."""
    loose = report.get("unreachable") or {}
    if loose and not loose.get("objects"):
        return "; no unreachable objects" + ("" if short else " (a fresh clone fetches only what a ref reaches)")
    if loose.get("scanned"):
        return f"; {loose['scanned']:,} unreachable blob{'s' if loose['scanned'] != 1 else ''} scanned too"
    return ""


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


# --- the Supply chain section and the closing lines --------------------------------------------------
#
# What the scans and the tree's own declarations say, in one titled place, last: secrets, dependencies, signing
# and the checks that ran and found nothing. prometheus's report had them in an untitled footer, two ✔ lines of
# the Findings box and a header row, gave the secrets scan's totals with no verdict (44 values in 1,188 places,
# none in a source file and 1,156 of them graded high), counted 28 and 3 vulnerable packages above a footer
# that said 29, and never printed a check that passed: 65 pinned actions and a tree with none looked the same.
#
# The default report holds the grid to SUPPLY_LINES lines, a cap per row, and the closing lines under it to
# CLOSING_LINES before the path. A new row or clause replaces one. --full prints every row whole, with the
# counts the default leaves to it (distinct values, placeholders, unreachable objects) and the tool versions.

SUPPLY_TITLE = "Supply chain"
SUPPLY_CAPS = {"secrets": 3, "dependencies": 3, "signing": 1, "checked, ok": 3}   # the default report's lines per row
SUPPLY_LINES = sum(SUPPLY_CAPS.values())   # 10
CLOSING_LINES = 6   # the index of --full's sections, the steps line and the re-render line, before the path
INDEX_LINES = 4
SECRETS_FILE, HYGIENE_FILE = "secrets.json", "hygiene.json"
UNVERIFIED = " (signatures not verified)"
NOT_SCANNED = "not scanned"   # in the verdict's position when a scan's step did not run
# The classifier's reasons that set a file aside from the source, in its order, as an adjective before "files".
ASIDE_WORDS = {"generated": "generated", "vendored": "vendored", "test file": "test", "example code": "example"}


def _or(words: list) -> str:
    return words[0] if len(words) == 1 else ", ".join(words[:-1]) + " or " + words[-1]


def secret_places(report: dict) -> list:
    """One entry per place a value was found (a value at a commit, file and line; placeholder-shaped hits left
    out, as leaks.group leaves them): its file, whether HEAD still holds the value there (None when the run
    did not record it) and whether the scanner graded any sighting of it high. Their number is the sum of the
    places leaks.group counts, which is what the Markdown export's Secrets line says."""
    places = {}
    for i, r in enumerate(report.get("secrets") or []):
        if r.get("placeholder"):
            continue
        key = (r.get("value") or ("row", i), r.get("commit"), r.get("file"), r.get("line"))
        p = places.setdefault(key, {"file": r.get("file") or "", "at_head": None, "high": False})
        if isinstance(r.get("at_head"), bool):
            p["at_head"] = bool(p["at_head"]) or r["at_head"]
        p["high"] = p["high"] or r.get("confidence") == "high"
    return list(places.values())


def _where_words(places: list, classifier) -> str:
    """'all in test or example files', '12 of them in test files' or 'none of them in a test, example,
    generated or vendored file': how many of `places` are in a file the classifier sets aside, and as what.
    The words are the classifier's own reasons (ASIDE_WORDS), so a directory it calls example code is never
    called test data here."""
    kinds = [next((ASIDE_WORDS[x] for x in classifier.reasons(p["file"]) if x in ASIDE_WORDS), None) for p in places]
    aside = [k for k in kinds if k]
    if not aside:
        return "none of them in a test, example, generated or vendored file"
    words = _or([w for w in ASIDE_WORDS.values() if w in aside]) + " files"
    return f"all in {words}" if len(aside) == len(places) else f"{len(aside):,} of them in {words}"


def _places_words(label: str, places: list, classifier, where: bool, detail: bool = True) -> str:
    """'at HEAD 18 places, all in test or example files, none high confidence', or 'history only 1,170 places,
    1,156 high confidence, those all in example files': the count, where the places are when `where` asks
    (HEAD's, which a reader can open), the count the scanner graded high, and where those are. `detail` False
    leaves out both where-clauses."""
    parts = [f"{label} {textfmt.count(len(places), 'place')}"]
    said_all = False
    if where and detail:
        words = _where_words(places, classifier)
        said_all = words.startswith("all ")
        parts.append(words)
    high = [p for p in places if p["high"]]
    if not high:
        parts.append("none high confidence")
    else:
        parts.append(f"{len(high):,} high confidence")
        if detail and not said_all:
            words = _where_words(high, classifier)
            parts.append(f"those {words}" if words.startswith("all ") else words)
    return ", ".join(parts)


def _not_scanned(report: dict, step: str, label: str) -> str:
    """'not scanned', with what became of the step when the run recorded it ('not scanned: the secrets scan
    timed out'): in the verdict's position, so a scan that never ran cannot be read as one that found nothing."""
    status = ((report.get("meta") or {}).get("steps") or {}).get(step)
    return NOT_SCANNED + (f": {_step_phrase(label, status)}" if status not in (None, "run") else "")


def secrets_variants(report: dict, full: bool = False) -> list:
    """The secrets row as lists of facts, the fullest first: the verdict and its rule ('none in source
    files', which is the rule that makes a value a finding), then HEAD, then history with its high-confidence
    count, and the file that holds every row. The later variants say less, for a row that does not fit its
    lines. `full` adds what the default report leaves to --full: the distinct values, the placeholder-shaped
    hits left out and the sweep of unreachable objects."""
    from .findings import secrets_found
    if not report.get("secrets_scanned"):
        return [[_not_scanned(report, "betterleaks", "the secrets scan")]]
    rows = report.get("secrets") or []
    groups = leaks.group(rows)
    skipped = leaks.placeholders(rows)
    extra = ([f"{skipped:,} placeholder-shaped hit{'s' if skipped != 1 else ''} left out"] if skipped else []) + \
            ([_unreachable_words(report, False)[2:]] if _unreachable_words(report, False) else [])
    if not groups:
        return [["none found: betterleaks scanned every commit HEAD reaches"] + (extra if full else [])]
    behind = [f for f in secrets_found(report) if f["rule"]["id"] in SECRET_FINDINGS]
    held = sum((f.get("evidence") or {}).get("values", 0) for f in behind)
    if not held:
        verdict = f"none in source files ({SECRETS_FILE})"
    else:
        more = len(groups) - held
        verdict = (f"{textfmt.count(held, 'value')} in the finding{'' if len(behind) == 1 else 's'} above"
                   + (f", {more:,} more never in source" if more > 0 else "") + f" ({SECRETS_FILE})")
    places = secret_places(report)
    classifier = classify.Classifier(report)
    head, past = [p for p in places if p["at_head"] is True], [p for p in places if p["at_head"] is False]
    unknown = [p for p in places if p["at_head"] is None]

    def split(detail):
        return ([_places_words("at HEAD", head, classifier, True, detail)] if head else []) + \
               ([_places_words("history only", past, classifier, False, detail)] if past else []) + \
               ([_places_words("in", unknown, classifier, True, detail)] if unknown else [])
    if full:
        return [[verdict, f"{textfmt.count(len(groups), 'distinct value')} in {textfmt.count(len(places), 'place')}"] + split(True) + extra]
    return [[verdict] + split(True), [verdict] + split(False), [verdict]]


def _vulnerable_split(report: dict, found: list, names: set) -> str:
    """': 28 in the warning above, 3 in the note, 2 counted in both', ', all in the warning above' or '': how the
    total divides between the two dependency findings, which count a package pinned by a source lock and by
    an example's lock once each. prometheus's findings said 28 and 3 over a footer that said 29. Derived from
    the rule's own rows; '' when a finding is not in this report or the parts do not make the total, so no
    number is printed that the reader cannot add up."""
    from . import findings as rules
    parts = {rid: {r.get("name") for r in group} for rid, _, _, group in rules._vuln_rows(report)}
    said = {(f.get("rule") or {}).get("id"): textfmt.severity_word(f["severity"]) for f in found or [] if (f.get("rule") or {}).get("id") in DEPENDENCY_FINDINGS}
    main, aside = parts.get("vulnerable_dependencies") or set(), parts.get("vulnerable_dependencies_aside") or set()
    if not parts or set(parts) - set(said) or (main | aside) != names:
        return ""
    every = "" if len(names) == 1 else "all "
    if main and aside:
        both = len(main & aside)
        return (f": {len(main):,} in the {said['vulnerable_dependencies']} above, {len(aside):,} in the {said['vulnerable_dependencies_aside']}"
                + (f", {both:,} counted in both" if both else ""))
    rid = "vulnerable_dependencies" if main else "vulnerable_dependencies_aside"
    return f", {every}in the {said[rid]} above"


def dependencies_variants(report: dict, found: list = (), full: bool = False) -> list:
    """The dependencies row as lists of facts, the fullest first: what was scanned and how old the database
    copy is, then the totals, reconciled with the findings above (_vulnerable_split), the packages with an
    informational advisory, and the file that holds every row. 'not scanned' or 'no lock files found' stands
    alone in the verdict's position."""
    scan = report.get("dependencies") or {}
    status = scan.get("status")
    if status == "no-sources":
        return [["no lock files found"]]
    if status == "no-database":
        return [[f"{NOT_SCANNED}: no offline vulnerability database; fetch it once with gitmole --fetch-vuln-db CLONE"]]
    if status != "scanned":
        return [[_not_scanned(report, "osv-scanner", "the dependency scan")]]
    size = f"{_packages(scan.get('packages', 0))} in {_dependency_files(scan)}" + (f", database {scan['database_date']}" if scan.get("database_date") else "")
    rows = scan.get("vulnerable") or []
    names = {r.get("name") for r in rows}
    total = (f"{len(names):,} vulnerable" + (f" in {len(rows):,} places" if len(rows) != len(names) else "")) if names else "none vulnerable"
    notes = scan.get("informational") or []
    counted = f"{len(notes):,} with an informational advisory" if notes else ""   # RustSec's unmaintained, unsound and notice advisories: said, not counted as vulnerable
    first = notes[0] if notes else {}
    named = (f"{counted} ({first.get('name')} {first.get('version')}, {' and '.join(first.get('kinds') or [])}"
             + (f", and {len(notes) - 1:,} more" if len(notes) > 1 else "") + ")") if notes else ""
    split = _vulnerable_split(report, found, names) if names else ""

    def said(total_words, note_words):
        facts = [size, total_words] + ([note_words] if note_words else [])
        return facts[:-1] + [f"{facts[-1]} ({brief.DEPENDENCIES_FILE})"]
    out = [said(total + split, named)]
    return out if full else out + [said(total, named), said(total, counted)]


def signing_variants(report: dict, full: bool = False) -> list:
    """The signing row, the fullest first: the share of commits their authors signed, by what, the last year's,
    the forge's own merges, and that no signature was verified. The default report's row is one line, so it
    says the share and that nothing was verified, and --full and the Signing by year table say the rest."""
    parts = _signing_parts(report)
    if not parts:
        return []
    head, mix, tail, forge = parts
    if not (mix or tail or forge):
        return [[head]]   # "no commits signed": nothing to verify
    whole = [[head + mix + tail + forge + UNVERIFIED]]
    return whole if full else whole + [[head + tail + forge + UNVERIFIED], [head + tail + UNVERIFIED], [head + UNVERIFIED], [head]]


def _ok_actions(h: dict):
    a = h.get("actions") or {}
    n = a.get("pinned") or 0
    return f"{n:,} workflow action{'' if n == 1 else 's'} pinned" if n else None


def _ok_updates(h: dict):
    up = h.get("updates") or {}
    return f"{up['tool']} covers {textfmt.join_and(list(up['covered']))}" if up.get("tool") and up.get("covered") else None


def _ok_lockfiles(h: dict):
    n = (h.get("lockfiles") or {}).get("pairs") or 0
    return (f"{n:,} manifests match their lock files" if n > 1 else "1 manifest matches its lock file") if n else None


def _ok_trojan(h: dict):
    n = (h.get("trojan") or {}).get("files") or 0
    return f"{textfmt.count(n, 'file')} free of bidi and mixed-script characters" if n else None


def _ok_binaries(h: dict):
    b = h.get("binaries") or {}
    n = b.get("binaries") or 0
    return f"{n:,} binar{'y' if n == 1 else 'ies'}, none executable" if n and not b.get("executables_count") else None


def _ok_licence(h: dict):
    lic = h.get("licences") or {}
    names = [d.get("expression") for d in lic.get("declared") or [] if d.get("expression")] or ([lic["file_licence"]] if lic.get("file_licence") else [])
    return f"{textfmt.join_and(list(dict.fromkeys(names)))} licence, OSI- or FSF-approved" if lic.get("approved") is True and names else None


def _ok_presence(h: dict):
    pr = h.get("presence") or {}
    there = [word for key, word in (("codeowners", "CODEOWNERS"), ("security_policy", "security policy"), ("pull_request_template", "pull-request template")) if pr.get(key)]
    return f"{textfmt.join_and(there)} present" if there else None


def _ok_workflows(h: dict):
    a = h.get("actions") or {}
    uses = (a.get("pinned") or 0) + (a.get("local") or 0) + (a.get("unpinned_count") or 0)
    return "workflows free of pull-request checkout and script injection" if uses else None


def _ok_submodules(h: dict):
    n = (h.get("submodules") or {}).get("count") or 0
    return f"{textfmt.count(n, 'submodule URL')} safe" if n else None


def _ok_symlinks(h: dict):
    n = (h.get("symlinks") or {}).get("count") or 0
    return f"{textfmt.count(n, 'symlink')} inside the tree" if n else None


def _ok_imports(h: dict):
    n = (h.get("imports") or {}).get("manifests") or 0
    return f"every dependency declared in {textfmt.count(n, 'manifest')} imported" if n else None


# The hygiene families a passed check is said for, in the order the row names them: the four a reader asks about
# first (actions, the update tool, lock files, Trojan Source), then the rest. Each is (the rule ids that are a hit
# in it, its words when it had something to check, else None). A family with a hit is a finding above and never
# here; one with nothing to check (no workflow, no lock file) is not here either, since nothing was checked.
# The families hygiene.json records with no denominator and no declaration to name (registry confusion, install
# scripts) are in that file only.
CHECKED_OK = [(("unpinned_actions",), _ok_actions), (("dependency_updates",), _ok_updates), (("lockfile_drift", "lockfile_missing"), _ok_lockfiles),
              (("trojan_source",), _ok_trojan), (("committed_binaries",), _ok_binaries), (("project_licence", "copyleft_dependencies"), _ok_licence),
              (("repo_policy",), _ok_presence), (("pwn_request", "expression_injection"), _ok_workflows), (("submodule_urls",), _ok_submodules),
              (("unsafe_symlinks",), _ok_symlinks), (("unused_dependencies",), _ok_imports)]


def checked_ok(report: dict) -> list:
    """The hygiene checks that ran with something to check and found nothing, as phrases in CHECKED_OK's order;
    [] without the hygiene step. Whether a family has a hit is the rules' own answer (findings.hygiene_findings),
    so a drift the sweeping commits explain, or an executable under tests, is judged here as it is there."""
    from . import findings as rules
    if not report.get("hygiene"):
        return []
    h = rules._swept_hygiene(report)
    hits = {f["rule"]["id"] for f in rules.hygiene_findings(report)}
    out = []
    for ids, words in CHECKED_OK:
        said = None if hits & set(ids) else words(h)
        if said:
            out.append(said)
    return out


def checked_variants(report: dict, full: bool = False) -> list:
    """The 'checked, ok' row, the fullest first: every phrase of checked_ok and the file they are read from,
    then one phrase fewer at a time, closed with 'more in hygiene.json' for what did not fit."""
    items = checked_ok(report)
    if not items:
        return []
    whole = [items[:-1] + [f"{items[-1]} ({HYGIENE_FILE})"]]
    return whole if full else whole + [items[:k] + [f"more in {HYGIENE_FILE}"] for k in range(len(items) - 1, 0, -1)]


def supply_chain_rows(report: dict, found: list = (), full: bool = False, width=None) -> list:
    """The Supply chain section as [(label, lines, verdict style)]: secrets and dependencies always, each
    saying 'not scanned' when its step did not run; signing and 'checked, ok' when there is something to say.
    Each row is the fullest of its variants that fits its lines (SUPPLY_CAPS) at `width`, the value's own
    width; the tersest is cut at the cap as a last resort. `full`, or no `width`, is every row whole."""
    rows = [("secrets", secrets_variants(report, full), footer_style(found, SECRET_FINDINGS, "")),
            ("dependencies", dependencies_variants(report, found, full), footer_style(found, DEPENDENCY_FINDINGS, "")),
            ("signing", signing_variants(report, full), ""), ("checked, ok", checked_variants(report, full), "")]
    out = []
    for label, variants, style in rows:
        if not variants:
            continue
        if variants[0][0].startswith(NOT_SCANNED):
            style = SEVERITY_STYLE["warning"]   # nothing was checked: not a pass, and not to be read as one
        lines = None
        for facts in variants:
            lines = wrapped(SEP.join(facts), width)
            if full or width is None or len(lines) <= SUPPLY_CAPS[label]:
                break
        else:
            lines = brief.cap(lines, SUPPLY_CAPS[label], max(width, 20))
        out.append((label, lines, style))
    return out


def supply_chain_block(report: dict, found: list = (), full: bool = False, width=None) -> Text:
    """The titled section: a label grid like the header's, the labels padded to the longest and a value that
    does not fit wrapped under its own start. A row carries no status mark; the first words of a scan's row
    are its verdict, in the colour of the worst finding behind it and in none when no finding is."""
    pad = max(len(label) for label in SUPPLY_CAPS) + LABEL_GAP
    grid = []
    for label, lines, style in supply_chain_rows(report, found, full, width - INDENT - pad if width else None):
        pieces = []
        for i, line in enumerate(lines):
            piece = Text(line)
            if style and label == "dependencies" and not lines[0].startswith(NOT_SCANNED):
                piece.highlight_regex(r"[\d,]+ vulnerable\b", style)   # the scan's size comes first on this row; the verdict is the count
            elif style and i == 0:
                piece.stylize(style, 0, len(line.split(SEP)[0].rstrip(" ·")))
            pieces.append(piece)
        grid.append((label, pieces))
    return _lines([heading({"title": SUPPLY_TITLE})] + _grid_lines(grid, pad))


# What gates a step that a run may leave out, and what the step gives: --plots draws the two plots and runs the
# sampled survival analysis they are drawn from; --deep runs the blame pass when it is projected past its budget.
STEP_GATES = {"git-of-theseus": ("--plots", "code survival"), "theseus stack plot": ("--plots", "plot"), "theseus survival plot": ("--plots", "plot"),
              "code age": ("--deep", "code age")}


def _all_steps() -> list:
    """The names of every step a run can take, from the plan itself, so the count follows the code."""
    from . import run
    return [step["name"] for step in run.plan("", "", plots=True, lizard=True, structure=True, backtest="1970-01-01")]


def steps_line(report: dict):
    """'15 of 18 steps ran; --plots runs the other 3 (code survival, 2 plots).': how many of the steps a run can
    take this one took, and for each that did not run the flag that runs it, or what became of it when no flag
    does ('functions not run', 'osv-scanner timed out'). The plots a run did draw are named here and nowhere
    else. None for an output directory whose run recorded no steps."""
    took = (report.get("meta") or {}).get("steps") or {}
    if not took:
        return None
    every = _all_steps()
    every += [name for name in took if name not in every]   # a step of an older gitmole
    ran = [name for name in every if took.get(name) == "run"]
    rest = [name for name in every if took.get(name) != "run"]
    by_flag, plain = {}, []
    for name in rest:
        flag, what = STEP_GATES.get(name, (None, name))
        if flag and name not in took:
            by_flag.setdefault(flag, []).append(what)
        else:
            plain.append(_step_phrase(name, took[name]) if name in took else f"{name} not run")
    parts = []
    for flag, whats in by_flag.items():
        plots = whats.count("plot")
        named = [w for w in whats if w != "plot"] + ([textfmt.count(plots, "plot")] if plots else [])
        n = f"the other {len(whats):,}" if len(whats) == len(rest) and len(whats) > 1 else "it" if len(whats) == len(rest) else f"{len(whats):,} more"
        parts.append(f"{flag} runs {n} ({', '.join(named)})")
    try:
        drawn = sorted(name for name in os.listdir(report.get("out_dir") or "") if name.endswith(".png"))
    except OSError:
        drawn = []
    if drawn:
        parts.append(f"{textfmt.count(len(drawn), 'plot')} drawn ({', '.join(drawn)})")
    return "; ".join([f"{len(ran):,} of {len(every):,} steps ran"] + parts + plain) + "."


def full_only_sections(report: dict) -> list:
    """The titles of the sections only --full prints, in its order, for this report: the builders in FULL_ONLY
    that give rows here (a repository with no agent files has no Agent surface to name). The OSPS Baseline's
    title carries its result, the one number of the list: 'OSPS Baseline (2 gaps, 1 not seen, of 10)'."""
    out = []
    for b in BUILDERS:
        sid = b.__name__[:-len("_section")]
        if sid not in FULL_ONLY:
            continue
        sec = b(report, True, None)
        if sec is None or not sec["rows"]:
            continue
        title = _base_title(sec["title"])
        if sid == "osps":
            results = [row[2] for row in sec["rows"]]
            short = [f"{results.count(r):,} {word}" for r, word in (("gap", "gap" if results.count("gap") == 1 else "gaps"), ("not seen", "not seen"),
                                                                     ("unrecognised", "unrecognised"), ("not checked", "not checked")) if results.count(r)]
            title += f" ({', '.join(short)}, of {len(results):,})" if short else f" (all {len(results):,} met)"
        out.append(title)
    return out


RERENDER = "gitmole DIR --no-run --full re-renders this run, DIR being the path below."


def closing_lines(report: dict, width=None) -> list:
    """The default report's last lines before the path, CLOSING_LINES at most: one sentence naming what --full
    adds (the hidden rows of the tables above, and its own sections by title, generated from FULL_ONLY, so the
    count follows the code), the steps line, and the command that re-renders this run with its argument named.
    prometheus's report named none of --full's sections and none of the three steps it had not run."""
    titles = full_only_sections(report)
    whole = [t.partition(" (")[0].replace(" ", brief.NBSP) + "".join(t.partition(" (")[1:]) for t in titles]   # a title is not broken across two lines
    index = (f"--full shows the hidden rows and adds {textfmt.count(len(titles), 'section')}: {', '.join(whole)}." if titles
             else "--full shows the hidden rows.")
    lines = brief.cap(wrapped(index, width), INDEX_LINES, max(width or 20, 20))
    steps = steps_line(report)
    if steps:
        lines += brief.cap(wrapped(steps, width), CLOSING_LINES - 1 - len(lines), max(width or 20, 20))
    return lines + [RERENDER]


# --- the terminal's drawing --------------------------------------------------
#
# One grammar for every block, and no box anywhere: a title line at column 1, then what the block holds two
# columns in. A table is column heads, a rule exactly as wide as its columns, a row a line and its caption; a
# block without columns (the header, the Supply chain section, Since last report) is a label grid; the
# Findings are entries, each with its mark at column 1. One blank line between two blocks and none inside one.
# prometheus's report had three grammars (two boxes, open tables, bare footer lines), 55 of its 213 lines
# ended in padding, and a box broke a path in two at its border.
#
# Every block is built as lines of text and printed as they are (_lines, show): the console wraps nothing,
# cuts nothing and pads nothing, so the colour render with its escapes stripped is the plain render byte for
# byte, and no line of either ends in a space. The width of the terminal decides only where prose wraps and
# which cells are elided (fit); it never changes a row, an order or a window of months. Alignment is counted
# as the terminal counts cells for a wide character and as one cell for every other; a terminal that draws an
# East Asian ambiguous-width character two cells wide will show those rows one cell out.


def _lines(lines) -> Text:
    """`lines` (text or styled text) as one block that prints as it is: no line wrapped, cut or padded by the
    console, and none ending in a space."""
    out = Text(no_wrap=True, overflow="ignore")
    for n, line in enumerate(lines):
        piece = line.copy() if isinstance(line, Text) else Text(line)
        piece.rstrip()
        if n:
            out.append("\n")
        out.append_text(piece)
    return out


def _wrap_styled(text: Text, width, hang: int = 0) -> list:
    """A styled line as the lines it wraps to at `width` (wrapped), each piece keeping its style and the
    lines after the first indented by `hang`: a title longer than a narrow terminal."""
    plain = text.plain
    if width is None or len(plain) <= width:
        return [text]
    out, at = [], 0
    for n, line in enumerate(wrapped(plain, width, hang)):
        start = plain.find(line, at)
        piece = text[start:start + len(line)] if start >= 0 else Text(line)
        at = start + len(line) if start >= 0 else at
        out.append(piece if n == 0 else Text(" " * hang).append_text(piece))
    return out


def show(console: Console, block) -> None:
    """Print a block: soft-wrapped, so a line longer than the terminal (a path that cannot be broken) is left
    whole for the terminal to wrap, where a copy still pastes as one path."""
    console.print(block, soft_wrap=True)


# --- marks a stream may not be able to carry -------------------------------------------------------------------
#
# Every mark the report prints, with the ASCII it becomes on a stream whose encoding cannot carry it
# (PYTHONIOENCODING=ascii, a legacy code page). Chosen once per stream (carry), one mark at a time, so a
# Latin-1 stream keeps its "·" and "×". The severity marks, the step, the rule and the pictograms are one
# character each, so the finding grid and every rule keep their columns; "…", "→" and "≥" have no honest
# one-character ASCII form, so a line holding one is a character or two longer than its UTF-8 twin, never a
# line more. A character that is not a mark (a name, a path) prints as "?" where the stream cannot carry it:
# prometheus's report raised nothing under LANG=C only because Python reads that locale as UTF-8.
ASCII_MARKS = {
    SEVERITY_MARK["critical"]: "x", SEVERITY_MARK["warning"]: "!", SEVERITY_MARK["info"]: "*", STEP_MARK: ">",
    textfmt.ELLIPSIS: "...", "→": "->", "·": "-", RULE_MARK: "-", "≥": ">=", "×": "x", "—": "-", brief.NBSP: " ",
    **{symbol: "#" for symbol in list(SYMBOLS.values()) + [SECTION_MARK]},   # every pictogram: "# Watch list"
    BAR_MARK: "#", BLOCK_MARK: "#", **{block: str(level) for level, block in enumerate(trend.BLOCKS[:-1], 1)},   # a sparkline as its levels, 1 to 7 and "#"
    "═": "=", "║": "|", "╔": "+", "╗": "+", "╚": "+", "╝": "+", "▀": "#",   # the banner's, should a terminal that cannot carry them be given it
}


def substitutes(encoding) -> dict:
    """The marks `encoding` cannot carry, each with its ASCII substitute: {} for one that carries them all,
    for a stream that names no encoding (a string buffer) and for an encoding Python does not know."""
    if not encoding:
        return {}
    out = {}
    for mark, plain in ASCII_MARKS.items():
        try:
            mark.encode(encoding)
        except UnicodeEncodeError:
            out[mark] = plain
        except LookupError:
            return {}
    return out


class _Substituting:
    """A stream written to through the substitutes: each mark it cannot carry becomes its ASCII form and any
    other character it cannot carry a "?", so writing to it raises nothing. Everything else is the stream's."""

    def __init__(self, stream, table: dict, encoding: str):
        self._stream, self._table, self._encoding = stream, str.maketrans(table), encoding

    def write(self, text: str):
        return self._stream.write(text.translate(self._table).encode(self._encoding, "replace").decode(self._encoding))

    def __getattr__(self, name):
        return getattr(self._stream, name)


def carry(console: Console) -> Console:
    """Make `console` safe for its stream's encoding, once: when the encoding cannot carry a mark, the console
    writes through the substitutes from then on. A UTF-8 stream is left as it is."""
    stream = console.file
    if not isinstance(stream, _Substituting):
        encoding = getattr(stream, "encoding", None)
        table = substitutes(encoding)
        if table:
            console.file = _Substituting(stream, table, encoding)
    return console


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


def wrapped(text: str, width, hang: int = 0) -> list:
    """`text` as lines of at most `width`: broken at spaces, a separator kept at the end of the line before it,
    and never between a number and its noun or a term and its "=" (_glue). `width` None is one line. With
    `hang`, the lines after the first are that much shorter, for the indent they are printed with."""
    return [text] if width is None else brief.wrap(_glue(text), max(width, 20), max(width - hang, 20) if hang else None)


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
    commits (fixes, reverts) and left out (the sweeping commits no count holds). A row with nothing to say
    is not there. Signing is a row of the Supply chain section (supply_chain_rows), where the rest of what the
    tree and the history say about provenance is; prometheus's report had it in four places."""
    s = summary(report)
    rows = []
    history = [(f"{s['commits']:,} commits", BOLD), (f"{s['first_date']} → {s['last_date']}", "")]
    if s["since"]:
        history.append((f"since {s['since']}", BOLD))   # bold, as the scope is: it changes what every count below is of, and yellow is a warning's
    history.append((textfmt.count(s["identities"], "identity", "identities"), ""))
    rows.append(("history", history))
    if s["scope"]:
        rows.append(("scope", [(scope.label(s["scope"]), BOLD), (scope.REPOSITORY_WIDE, DIM)]))
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
    return rows


LABEL_GAP = 2   # between a header label and its value


def _grid_lines(rows: list, pad: int) -> list:
    """A label grid as lines: `rows` is [(label, the value's lines)], the label dim and padded to `pad`, two
    columns in, and the lines a value wraps to under the value's own start."""
    return [Text.assemble(" " * INDENT, (f"{label:<{pad}}", DIM), line) if i == 0 else Text.assemble(" " * (INDENT + pad), line)
            for label, lines in rows for i, line in enumerate(lines)]


def _title(title: str, symbol: str = None) -> Text:
    """A block's title line: its name bold (behind its pictogram, when it has one) and what qualifies it, the
    count and the ranking key, in the plain foreground."""
    name = _base_title(title)
    return Text.assemble((f"{symbol} {name}" if symbol else name, BOLD), title[len(name):])


def header(report: dict, findings: list = (), full: bool = False, width=None) -> Text:
    """The header: a title line (the repository, its branch and commit) and header_rows as a label grid, the
    labels padded to the longest and a value that does not fit wrapped with a hanging indent. The finding
    tally is the Findings title's (tally_title). `findings` is not read; it stays for the callers that pass it."""
    s = summary(report)
    rows = header_rows(report, full)
    branch = f"branch {s['branch']}" + (f" @ {s['commit'][:8]}" if s["commit"] else "")
    title = Text.assemble((s["name"], BOLD), f"{SEP}{branch}")
    if width is not None and len(title.plain) > width:   # a title longer than the line: the branch is a row
        title = Text(s["name"], style=BOLD)
        rows.insert(0, ("branch", [(branch[len("branch "):], "")]))
    pad = max(len(label) for label, _ in rows) + LABEL_GAP
    grid = []
    for label, facts in rows:
        pieces = []
        for line in wrapped(SEP.join(text for text, _ in facts), width - INDENT - pad if width is not None else None):
            piece = Text(line)
            for text, style in facts:
                if style:
                    piece.highlight_words([text], style)
            pieces.append(piece)
        grid.append((label, pieces))
    return _lines([title] + _grid_lines(grid, pad))


UNMEASURED_GLOSSES = ("by rules not measured for precision yet", "not measured for precision yet", "not measured yet")


def tally_title(findings: list, gloss: bool = False, width: int = None) -> str:
    """'Findings · 4 warnings ▲ · 10 notes ● · 5 by rules not measured for precision yet': the tally where the
    findings are, each word beside the mark the entries below carry, so the marks can be counted against it.
    'Findings' alone when there are none. With `gloss`, the last part counts the findings that carry
    brief.UNMEASURED_TAG after their title and says once what the tag means; in a title longer than `width`
    it says so in fewer words (UNMEASURED_GLOSSES, the first that fits). prometheus's title fits 80 columns
    whole now that no border takes six of them."""
    counts = {sev: sum(1 for f in findings if f["severity"] == sev) for sev in SEVERITY_MARK}
    words = {"critical": lambda n: f"{n:,} critical", "warning": lambda n: textfmt.count(n, "warning"), "info": lambda n: textfmt.count(n, "note")}
    parts = [f"{words[sev](n)} {SEVERITY_MARK[sev]}" for sev, n in counts.items() if n]
    title = SEP.join(["Findings"] + parts)
    unmeasured = sum(1 for f in findings if f.get("unjudged")) if gloss else 0
    if not unmeasured:
        return title
    fits = [g for g in UNMEASURED_GLOSSES if width is None or len(title) + len(SEP) + len(f"{unmeasured:,} {g}") <= width]
    return f"{title}{SEP}{unmeasured:,} {fits[0] if fits else UNMEASURED_GLOSSES[-1]}"


def _unmeasured(g: dict) -> bool:
    """Whether an entry is a rule's that nobody has measured (findings.UNJUDGED, the finding's `unjudged`)."""
    return bool(g["findings"]) and all(f.get("unjudged") for f in g["findings"])


def _titled(g: dict, style: str) -> Text:
    """An entry's mark and title, in its severity's colour (a note's in none), and the dim tag after the title
    when its rule is not measured yet: the colour ends with the title."""
    return Text.assemble((f"{SEVERITY_MARK[g['severity']]} {g['title']}", style), (f" {brief.UNMEASURED_TAG}", DIM) if _unmeasured(g) else "")


def _step(lines: list) -> list:
    """A step's lines as printed: led by its mark, the lines it wraps to two further in."""
    return [f"{STEP_MARK} {lines[0]}"] + [f"  {line}" for line in lines[1:]] if lines else []


def _short_entry(g: dict, report: dict, width: int, printed: dict, style: str, found: list = None) -> list:
    """One entry of the default report's Findings as its lines, the mark and title first: then each finding's short
    form (brief.short), the statement, its subject lines indented two, and the step under its mark with its
    continuation indented two. The lines come wrapped, so a path or a version is never split. An entry
    holding several findings of one title shows brief.SUBJECT_LINES of them and counts the rest.

    A note from a rule not measured yet takes the compact shape instead: title, tag, ': ' and the statement,
    brief.COMPACT_LINES lines at most and no step (brief.compact). prometheus's report folded five such
    findings, one of them a warning, into a closing line, so its title counted a warning no ▲ stood for; now
    every finding owns one mark. A warning from such a rule is an entry like any other, with the tag after
    its title. Only the title carries the severity's colour: the statement, the subjects and the step are in
    the terminal's own foreground, where prometheus's were dim yellow and dim italic yellow."""
    body = _titled(g, style)
    if _unmeasured(g) and g["severity"] == "info" and len(g["findings"]) == 1:
        lead = len(g["title"]) + 1 + len(brief.UNMEASURED_TAG) + 2
        lines = brief.compact(g["findings"][0], report, width, lead, printed, found)
        body.append(":" + (f" {lines[0]}" if lines[0] else ""))
        return [body] + lines[1:]
    shorts = [brief.short(f, report, width, printed, found) for f in g["findings"]]
    out, steps = [body], []
    for s in shorts[:brief.SUBJECT_LINES]:
        out += s["statement"] + [f"  {line}" for line in s["subjects"]]
        if s["step"] and s["step"] not in steps:
            steps.append(s["step"])
    if len(shorts) > brief.SUBJECT_LINES:
        out.append(f"and {len(shorts) - brief.SUBJECT_LINES:,} more")
    for step in steps:
        out += _step(step)
    return out


def _long_entry(g: dict, width: int, style: str) -> list:
    """One entry of --full's Findings as its lines: the title, every statement whole and every step, wrapped at
    spaces only, so a path, a package or a version is never broken (the box put the last letter of prometheus's
    web/ui/mantine-ui/src/pages/service-discovery/ServiceDiscoveryPoolsList.tsx on the next line). One longer
    than the line has a line to itself."""
    out = [_titled(g, style)]
    for item in g["items"]:
        out += brief.wrap(item, width)
    for advice in g["advice"]:
        out += _step(brief.wrap(advice, width - 2))
    return out


PROSE_WIDTH = 100   # a finding's lines are no longer than this on a terminal wider than it
ENTRY_INDENT = 2    # a finding's mark and the space after it: what its title, statement and step start behind


def findings_block(findings: list, report: dict = None, full: bool = True, width: int = None, printed: dict = None) -> Text:
    """The Findings: a title line with the tally, then an entry a finding, its mark at column 1, its title on
    the mark's line and its statement at column 3. `full` False is the default report: each finding in its
    short form (brief.py), for which `width` is the terminal's and `printed` the report's sections by id, so
    a "(see Section)" pointer names only a table that is there. `full` True spells every finding out, as the
    Markdown export does. Either way every finding is an entry with its own mark, and one from a rule not
    measured yet has the tag after its title, which the title line glosses (tally_title). It was a box: its
    two borders took four columns from every line, so prometheus's Bug magnets named six of its seven files
    and counted the seventh."""
    absent = not_computed_line(report) if report else None
    inner = min((width or PROSE_WIDTH + ENTRY_INDENT) - ENTRY_INDENT, PROSE_WIDTH)   # less the mark and its gap
    if not findings and not absent:   # a scan that came back clean is a row of the Supply chain section, not a line here
        return _lines([_title("Findings"), " " * ENTRY_INDENT + NOTHING_FLAGGED])
    lines = _wrap_styled(_title(tally_title(findings, gloss=True, width=width)), width, ENTRY_INDENT)
    for g in textfmt.group_findings(findings):
        style = SEVERITY_STYLE[g["severity"]]
        entry = _long_entry(g, inner, style) if full else _short_entry(g, report or {}, inner, printed, style, findings)
        lines += _wrap_styled(entry[0], inner + ENTRY_INDENT, ENTRY_INDENT)   # the mark at column 1; a title longer than the line wraps to column 3
        lines += [Text.assemble(" " * ENTRY_INDENT, line) for line in entry[1:]]
    if absent and not findings:
        lines.append(" " * ENTRY_INDENT + NOTHING_FLAGGED)
    if absent:   # last: what was found, then what was never measured, so its silence is not a pass
        said = brief.wrap(absent, inner)
        lines += [Text(f"· {said[0]}", style=DIM)] + [Text(" " * ENTRY_INDENT + line, style=DIM) for line in said[1:]]
    return _lines(lines)


NOTHING_FLAGGED = "Nothing flagged."


def _base_title(title: str) -> str:
    """A section's name without its qualifier: 'Watch list' of 'Watch list · 5 of 15, ranked by …' and of a
    title that still carries its qualifier in brackets."""
    return title.split(" · ")[0].split(" (")[0]


def _cell(column: str, value: str, bars: bool) -> str:
    """A cell as printed: itself, or a share with its bar after it in a table that draws them."""
    if bars and column == "share" and value.endswith("%"):
        n = int(value[:-1])
        return (f"{value:>4} " + BAR_MARK * (max(1, n // 10) if n else 0)).rstrip()
    return value


# fit(): how far a column may give way, in the one order every table follows. A path loses its middle directories
# first and keeps its file name whole (textfmt.shorten_path), and a name keeps NAME_KEEP characters; then the
# last text cell of the row (a "tail", or prose) is cut at its end with an ellipsis, down to CUT_FLOOR (prose
# to PROSE_FLOOR); only then are names and file names cut in the middle, never below CUT_FLOOR. A number and a
# column head are never cut, and no cell and no head is ever wrapped onto a second line.
# Columns are left out only when even that does not fit: a file name cut at PATH_LEAST, a name at NAME_LEAST;
# a column marked "spare" goes first, then the rightmost.
NAME_KEEP, PROSE_FLOOR, CUT_FLOOR, PATH_LEAST, NAME_LEAST = 32, 20, 12, 24, 16
GAP = 2         # between two columns


def _bars(sec: dict) -> bool:
    """Whether a section's share column carries inline bars: only where there is no bar column already, and
    not in a table that says no (`bars` False: People and the Knowledge map, which are in the default report)."""
    return sec.get("bars", True) and "share" in sec["columns"] and "" not in sec["columns"]


def _kind(name: str, opts: dict) -> str:
    """How a column may give way: "path" (directories elided), "name" (cut in the middle), "tail" and "prose"
    (cut at the end) or "fixed" (a number, a bar: never cut)."""
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
    """A cell in at most `width` cells of the terminal, cut as its kind is cut. The cuts count characters, so
    a cell of characters two cells wide is cut again until it fits."""
    from rich.cells import cell_len
    if cell_len(text) <= width:
        return text

    def cut(to):
        if kind == "path":
            return _cut_braced(text, to) if _braced(text) else textfmt.cut_path(text, to, others)
        return textfmt.cut(text, to) if kind in ("tail", "prose") else textfmt.cut_middle(text, to)
    to = width
    out = cut(to)
    while cell_len(out) > width and to > 1:
        to -= 1
        out = cut(to)
    return out


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
    """The section with its columns sized to `width` from their content, every row on one line: a cell is
    never wrapped, and neither is a column head. When the columns do not fit, the table gives way in one
    order: paths lose directories and long names their middle (widest column first), then the row's last text
    cell is cut at its end, and last the rightmost columns are left out, which the caption says. A number and
    a head are never cut. Rows and captions are otherwise unchanged; a table that fits is returned as it
    came. `width` None (Markdown) fits nothing."""
    from rich.cells import cell_len
    if width is None or not sec["rows"]:
        return sec
    cols, opts = sec["columns"], sec["col_opts"]
    bars = _bars(sec)
    kinds = [_kind(c, o) for c, o in zip(cols, opts)]
    rows = sec["rows"]
    cells = [max(cell_len(_cell(c, r[i], bars)) for r in rows) for i, c in enumerate(cols)]
    heads = [cell_len(c) for c in cols]
    want = [max(a, b) for a, b in zip(cells, heads)]

    def room(keep):
        return width - INDENT - GAP * (len(keep) - 1)
    keep = list(range(len(cols)))
    if sum(want) <= room(keep):
        return sec

    # the paths a cut path must not read as; they change what a cell shows within its width, never the widths,
    # so keeping two files apart costs no column its room and no row a line
    namesakes = {i: _namesakes(sec, i) for i, k in enumerate(kinds) if k == "path"}

    def name_floor(i):   # what a column keeps before anything is cut: whole file names, NAME_KEEP of a name
        if kinds[i] == "path":
            return min(want[i], max(heads[i], max(cell_len(_shortest(r[i])) for r in rows)))
        return min(want[i], max(heads[i], NAME_KEEP))

    # the least each column can take: a number and a head whole, a name or path cut to CUT_FLOOR, prose to PROSE_FLOOR
    least = [min(want[i], max(heads[i], PROSE_FLOOR if k == "prose" else CUT_FLOOR)) if k != "fixed" else want[i]
             for i, k in enumerate(kinds)]
    ends = [i for i, k in enumerate(kinds) if k in ("tail", "prose")]

    def needs(i):   # what a column must have to stay in the table
        if kinds[i] == "path":
            return min(name_floor(i), max(heads[i], PATH_LEAST))
        return min(want[i], max(heads[i], NAME_LEAST)) if kinds[i] == "name" else least[i]
    dropped = []
    while len(keep) > 1 and sum(needs(i) for i in keep) > room(keep):
        spare = [i for i in keep[1:] if opts[i].get("spare")]
        gone = spare[0] if spare else keep[-1]
        keep.remove(gone)
        dropped.append(gone)
    dropped = [cols[i] for i in sorted(dropped)]
    # what each column keeps before anything is cut: file names and NAME_KEEP of a name; a tail is whole until the paths have given what they can
    floor = [name_floor(i) if k in ("path", "name") else want[i] if k in ("tail", "prose") else least[i] for i, k in enumerate(kinds)]
    widths = {i: want[i] for i in keep}

    def excess():
        return sum(widths.values()) - room(keep)
    # a column of directories (the knowledge map's areas) is cut below its names only after every other column
    # has given what it can: an area is the row's subject, an owner's name is its detail
    dirs = {i for i in keep if kinds[i] == "path" and any(r[i].endswith("/") for r in rows)
            and all(r[i].endswith("/") or "/" not in r[i] for r in rows)}   # "(root files)" sits among them
    for floors, give, among in ((floor, ("path", "name"), keep), (least, ("tail", "prose"), [i for i in keep if i in ends]),
                                (least, ("path", "name"), [i for i in keep if i not in dirs]), (least, ("path",), dirs)):
        while excess() > 0:
            cand = [i for i in among if kinds[i] in give and widths[i] > floors[i]]
            if not cand:
                break
            widths[max(cand, key=lambda i: widths[i])] -= 1
    fitted = [tuple(_fit_cell(kinds[i], r[i], widths[i], namesakes[i][n] if i in namesakes else ()) if kinds[i] != "fixed" else r[i] for i in keep)
              for n, r in enumerate(rows)]
    col_opts = [dict(opts[i], width=widths[i]) for i in keep]
    caption = sec.get("caption")
    if dropped:
        left = f"{textfmt.join_and(dropped)} left out at {width} columns; a wider terminal or --markdown shows {'it' if len(dropped) == 1 else 'them'}"
        caption = f"{caption}\n{left}" if caption else left
    return dict(sec, columns=[cols[i] for i in keep], col_opts=col_opts, rows=fitted, caption=caption)


def table_lines(sec: dict) -> dict:
    """A section's table as lines, {"head": line, "rule": line, "rows": [line]}, each two columns in: the
    column heads, dim and lying as their cells do (text left, numbers right); a dim rule exactly as wide as
    the columns, so its right edge is the last column's; and a row a line, its first cell bold and the rest
    in the terminal's own foreground. Two spaces between columns. No colour marks a value, no row has a
    background and nothing is padded on the right: prometheus's tables had a near-black stripe on every other
    row, pink on a share over a fifth and a caption that stretched the table to the width of its sentence."""
    from rich.cells import cell_len
    bars = _bars(sec)
    cols = sec["columns"]
    left = [not (o.get("justify") == "right") or (bars and c == "share") for c, o in zip(cols, sec["col_opts"])]   # a share with its bar starts where the bars do
    cells = [[_cell(c, v, bars) for c, v in zip(cols, row)] for row in sec["rows"]]
    widths = [max([cell_len(c)] + [cell_len(r[i]) for r in cells]) for i, c in enumerate(cols)]
    shown = [i for i, w in enumerate(widths) if w]   # a column with no head and no cell (a bar column of zeroes) is not there

    def line(values, first=None) -> Text:
        out = Text(" " * INDENT)
        for n, i in enumerate(shown):
            pad = " " * max(widths[i] - cell_len(values[i]), 0)
            out.append((" " * GAP if n else "") + ("" if left[i] else pad))
            out.append(values[i], style=first if n == 0 else None)   # the first cell's style stops with the cell, before its padding
            out.append(pad if left[i] else "")
        out.rstrip()
        return out
    head = line(cols)
    head.stylize(DIM, INDENT)
    rule = Text(" " * INDENT).append(RULE_MARK * (sum(widths[i] for i in shown) + GAP * (len(shown) - 1)), style=DIM)
    return {"head": head, "rule": rule, "rows": [line(r, BOLD) for r in cells]}


UNDER_INDENT = 2   # a row's line of detail, in from the row's first cell


def caption_lines(sec: dict, width=None) -> list:
    """A section's caption as the lines to print: each paragraph wrapped at spaces, a " · " kept at the end of
    the line before it, so no line starts with a separator, and a definition's term kept with its "=" (wrapped).
    `width` None leaves each paragraph a line."""
    paragraphs = (sec.get("caption") or "").split("\n") if sec.get("caption") else []
    if width is None:
        return paragraphs
    return [line for par in paragraphs for line in wrapped(par, width - INDENT)]


def _captions(sec: dict, width=None) -> list:
    """A section's caption as printed: dim, two columns in."""
    return [Text.assemble(" " * INDENT, (line, DIM)) for line in caption_lines(sec, width)]


def heading(sec: dict) -> Text:
    """A section's title line, behind its pictogram."""
    return _title(sec["title"], SYMBOLS.get(_base_title(sec["title"]), SECTION_MARK))


def _note_lines(sec: dict, width=None) -> list:
    """A section with no rows: its title, a colon and its note, dim, wrapped under two columns of indent."""
    return _wrap_styled(heading(sec).append(f": {sec['note']}", style=DIM), width, INDENT)


def section_lines(sec: dict, width=None) -> list:
    """A section as its lines: the title, then the column heads, the rule and a row a line, with a row's
    `under` text wrapped beneath it, then the caption, dim; a section with no rows is its title and note; a
    `grid` section (Since last report) is a label grid, its first column the labels. With a `width`, the
    table is fitted to it first (fit) and the prose wrapped to it."""
    if not sec["rows"] and sec["note"]:
        return _note_lines(sec, width)
    if sec.get("grid") and len(sec["columns"]) == 2:
        pad = max(len(r[0]) for r in sec["rows"]) + LABEL_GAP
        rows = [(r[0], [Text(line) for line in wrapped(r[1], width - INDENT - pad if width is not None else None)]) for r in sec["rows"]]
        return _wrap_styled(heading(sec), width, INDENT) + _grid_lines(rows, pad) + _captions(sec, width)
    fitted = fit(sec, width)
    table = table_lines(fitted)
    out = _wrap_styled(heading(sec), width, INDENT) + [table["head"], table["rule"]]
    under = fitted.get("under") or []
    for n, row in enumerate(table["rows"]):
        out.append(row)
        if n < len(under) and under[n]:
            deep = INDENT + UNDER_INDENT
            out += [" " * deep + part for part in ([under[n]] if width is None else brief.wrap(under[n], max(width - deep, 20)))]
    return out + _captions(fitted, width)


def section_block(sec: dict, width=None) -> Text:
    """A section ready to print (section_lines)."""
    return _lines(section_lines(sec, width))


def print_section(console: Console, sec: dict) -> None:
    """Blank line, then the section's title and table (or note), fitted to the console's width."""
    carry(console)
    console.print(Text(""))
    show(console, section_block(sec, console.width))


def _dim(console: Console, line: str) -> None:
    """One of the report's closing lines: dim, and left whole whatever its length (a path must paste)."""
    show(console, Text(line, style=DIM))


def report(report: dict, findings: list, console: Console, full: bool = False, risk: dict = None, base: str = None, compare: dict = None) -> None:
    carry(console)
    show(console, header(report, findings, full=full, width=console.width))
    secs = [s for s in sections(report, full=full, width=console.width) if not _said_by_finding(s, findings)]
    by_id = {s["id"]: s for s in secs}
    console.print(Text(""))
    show(console, findings_block(findings, report, full=full, width=console.width, printed=by_id))   # a short finding may point at its table below
    if compare is not None:
        print_section(console, compare_section(compare))
    # One section under another at every width: small tables used to sit side by side from 100 columns, which
    # changed the order of the lines with the terminal and put two tables on every copied line. A wider terminal
    # un-elides paths and re-wraps prose, and changes nothing else.
    for sec in secs:
        print_section(console, sec)
        if risk is not None and sec["id"] == "watch":
            print_section(console, risk_section(risk, base, full))   # the change, right under the list it is scored against
    console.print(Text(""))
    show(console, supply_chain_block(report, findings, full=full, width=console.width))
    steps = steps_line(report)
    console.print(Text(""))
    if full:
        if steps:
            _dim(console, steps)
        if (line := run_line(report)):
            _dim(console, line)
        _dim(console, results_line(report))
        return
    for line in closing_lines(report, console.width):
        _dim(console, line)
    _dim(console, report.get("out_dir") or "")   # the results path, alone on the last line


def excerpt(report: dict, findings: list, console: Console, full: bool = False) -> None:
    """The report's opening on its own: the header, the Findings title, whose tally counts the findings, and
    the watch list. What the README's text block shows; the findings themselves are in the full report."""
    carry(console)
    show(console, header(report, findings, width=console.width))
    console.print(Text(""))
    show(console, _title(tally_title(list(findings))))
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
                    [("repo", {}), ("commits", RIGHT), ("people", RIGHT), ("top author", RIGHT),
                     ("secrets", RIGHT), ("lines", RIGHT), ("worst finding", TAIL)], rows,
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

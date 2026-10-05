"""The short form of a finding, for the default terminal report: the count and the rule's numbers, the worst
subject, and one step. It is a second rendering of the same `rule` and `evidence`, not the long sentence cut
off: the Markdown export, the JSON and SARIF keep the enumeration (`detail`) byte for byte, since nothing here
writes to a finding, and `--full` lays that same statement out with its subjects a line each (long). prometheus's Findings box was 88 of the default report's 211 lines at 80
columns: Brain methods repeated the first five rows of the Complex functions table below it, one Go
pseudo-version of 40 characters was printed three times, and five notes took more lines than four warnings.

Where the evidence is capped at ten rows and the short form needs a count or a row past them, it asks the
rule's own helper in findings.py (the vulnerable rows, the sweeping commits) and never counts again by a rule
of its own. A finding with no short form of its own (FORMS) prints its statement whole when that is three
lines or fewer, else its lead and at most three lines of its list (_fallback)."""
from __future__ import annotations

import re

from . import deps, findings, textfmt

ELLIPSIS = textfmt.ELLIPSIS
NBSP = " "         # holds a subject to its number while a line is wrapped ("promql/engine.go 10"); printed as a space
SEPARATORS = ("·",)     # a line never starts with one
SUBJECT_LINES = 3       # the subject lines of one finding, a hard cap, with the one exception below
# Vulnerable dependencies is the exception: its subjects are lock files, each with the packages that make it
# matter, so the block is at most VULN_GROUPS lock-file groups of at most VULN_GROUP_LINES lines each and one
# line counting the rest, ten lines in all. A fourth group would replace one; nothing here grows with the
# number of lock files.
VULN_GROUPS = 3
VULN_GROUP_LINES = 3
HANG = "  "             # a subject entry's continuation, in from its first line
DEPENDENCIES_FILE = "dependencies.json"   # the osv-scanner step's file in the output directory, where the packages not named are
STEP_LINES = 3          # the step's lines
WHOLE_LINES = 3         # a statement this short has no need of a short form
BASELINE_MARK = "In the baseline: "   # gate.BASELINE_MARK, which --baseline puts in front of a finding's detail
# After the title of a finding from a rule in findings.UNJUDGED, in either shape; the Findings title glosses it once.
UNMEASURED_TAG = "(not measured yet)"
COMPACT_LINES = 3       # a note from such a rule: title, tag and statement in this many lines, and no step
IGNORE_DEPS_SHORT = "One that does not apply to this code can be ignored in osv-scanner.toml."

# A Go pseudo-version, by its shape: a base version, a 14-digit commit time, a 12-character commit
# (v0.0.0-20251119130332-1174b0ce4f1f, 0.307.4-0.20251119130332-1174b0ce4f1f). The time says nothing the
# commit does not, so the short form keeps the base and the commit; the base alone would name a release the
# advisory does not state (prometheus's fix is itself a pseudo-version).
PSEUDO_VERSION = re.compile(r"(?<![\w.])(v?\d+\.\d+\.\d+-(?:[0-9A-Za-z]+\.)*)\d{14}-([0-9a-f]{12})(?![0-9A-Za-z])")


def short_version(text: str) -> str:
    """`text` with every Go pseudo-version in it shortened to base, ellipsis and commit, on the installed and
    the fixed-in side alike: 0.307.4-0.…-1174b0ce4f1f."""
    return PSEUDO_VERSION.sub(lambda m: f"{m.group(1)}{ELLIPSIS}-{m.group(2)}", text)


def wrap(text: str, width: int, rest: int = None) -> list:
    """`text` as lines of at most `width` characters, broken at spaces only: a path, a hash, a package or a
    version is never split (one longer than a line is left whole on a line of its own), a separator stays at
    the end of the line before it, and what a no-break space joins stays together. With `rest`, the lines
    after the first are at most that wide: an entry whose continuation is indented."""
    words = []
    for w in text.split(" "):
        if not w:
            continue
        if w in SEPARATORS and words:
            words[-1] += " " + w
        else:
            words.append(w)
    lines, line = [], ""
    for w in words:
        if line and len(line) + 1 + len(w) > (width if rest is None or not lines else rest):
            lines.append(line)
            line = w
        else:
            line = f"{line} {w}" if line else w
    if line:
        lines.append(line)
    return [x.replace(NBSP, " ") for x in lines]


def cap(lines: list, n: int, width: int) -> list:
    """At most `n` of `lines`, the last ending in an ellipsis when some were dropped: the last resort, for a
    single subject or a single clause longer than its cap."""
    if len(lines) <= n:
        return lines
    last = lines[n - 1]
    while " " in last and len(last) + 1 > width:
        last = last.rpartition(" ")[0]
    return lines[:n - 1] + [last.rstrip(" ,;:.") + ELLIPSIS]


def most(n: int, said, width: int, lines: int = SUBJECT_LINES, keys=None, least: int = 1) -> list:
    """The lines of said(k) for the largest k of n subjects that fit in `lines` lines, said(k) being the text
    naming the first k and counting the rest. With `keys` (each subject's count) the cut never falls between
    two subjects with the same count: it moves back to before the tie, since naming one of two files fixed
    six times each and hiding the other says the first is worse (prometheus's discovery/oci/oci.go and
    scrape/scrape_append_v2.go). When not even `least` fit, said(least) is cut at the cap."""
    for k in range(n, least - 1, -1):
        if keys and 0 < k < len(keys) and keys[k - 1] == keys[k]:
            continue
        out = wrap(said(k), width)
        if len(out) <= lines:
            return out
    return cap(wrap(said(least), width), lines, width)


def _is(n: int, one: str, many: str) -> str:
    return one if n == 1 else many


def _count(n: int, word: str, plural: str = None, capped: bool = False) -> str:
    """'3 pairs', or '10 or more pairs' when the evidence stops at its cap and there may be more."""
    return f"{n:,} or more {plural or word + 's'}" if capped else textfmt.count(n, word, plural)


def step_lines(advice: str, width: int) -> list:
    """The step in at most STEP_LINES lines: whole when it fits, else without its last sentences, else
    without the last clauses of its first, else cut."""
    out = wrap(advice, width)
    if len(out) <= STEP_LINES:
        return out
    sentences = textfmt._SENTENCE_END.split(advice.strip())
    while len(sentences) > 1:
        sentences.pop()
        out = wrap(" ".join(sentences), width)
        if len(out) <= STEP_LINES:
            return out
    clauses = sentences[0].split("; ")
    while len(clauses) > 1:
        clauses.pop()
        out = wrap("; ".join(clauses).rstrip(".") + ".", width)
        if len(out) <= STEP_LINES:
            return out
    return cap(wrap(sentences[0], width), STEP_LINES, width)


# --- the rules with a short form of their own ---------------------------------------------------------

def _scan_found_nothing(report: dict, paths: list) -> bool:
    """Whether the secrets step ran to its end and holds no row for any of `paths`, at HEAD or in history,
    placeholder-shaped or not: the one case in which the report may say the scan found no value in them."""
    if not report or not report.get("secrets_scanned") or not paths:
        return False
    if ((report.get("meta") or {}).get("steps") or {}).get("betterleaks", "run") != "run":
        return False
    seen = {r.get("file") for r in report.get("secrets") or []}
    return not any(p in seen for p in paths)


def _credential_files(f: dict, report: dict, ctx: dict):
    """'1 file, matched by name: web/ui/react-app/.env. The secrets scan found no value in it, at HEAD or in
    history', the second sentence only when that is so (_scan_found_nothing), and the step conditional with
    it: prometheus's report told the reader to move the values out of a file the scan had found none in."""
    ev = f["evidence"]
    n, files = ev["count"], list(ev["files"])
    every = ((report or {}).get("meta") or {}).get("credential_files") or []
    every = every if len(every) == n else files if len(files) == n else None   # the evidence names ten at most
    clean = every is not None and _scan_found_nothing(report, every)
    by = ", matched by name" if f["rule"].get("by") == "file name" else ""
    lead = f"{textfmt.count(n, 'file')}{by}"
    found = f"The secrets scan found no value in {_is(n, 'it', 'them')}, at HEAD or in history" if clean else ""
    if n == 1:
        statement, subjects = f"{lead}: {files[0]}" + (f". {found}" if found else ""), None
    else:
        statement = lead + (f". {found}" if found else "")
        subjects = most(len(files), lambda k: ", ".join(files[:k]) + (f" and {n - k:,} more" if n > k else ""), ctx["width"] - 2)
    step = (f"If {_is(n, 'it holds', 'one holds')} a login, move the values to the environment and git rm the {_is(n, 'file', 'files')}; "
            "a template belongs in .env.example.") if clean else f["advice"]
    return {"statement": statement, "subjects": subjects, "step": step}


# Why a score in the critical band sits under a warning's mark. The mark says "warning"; the words say what is
# missing, in few enough letters to stay on the entry's third line at 80 columns (prometheus's websocket-driver).
WHY_WARNING = "; not critical, as nothing beside it declares a deployment"


def _vuln_parts(r: dict) -> tuple:
    """One vulnerable row as (which, facts): name, version and one advisory id, then its score, its fix or
    that none is published, and what the lock and the imports say of its reach."""
    ref = findings._malicious_id(r) or next(iter(list(r.get("aliases") or []) + list(r.get("ids") or [])), "")
    floating = findings._floating(r)
    if floating and r.get("requirement") is not None:
        text = f"{r['name']}{r['requirement'] or ' (any version)'}, whose floor is {r['version']}"
    else:
        text = f"{r['name']} {r['version']}"
    text += f" ({ref})" if ref else ""
    facts = []
    if r.get("malicious"):
        facts.append("malicious")
    elif r.get("score") is not None:
        facts.append(f"CVSS {r['score']:.1f}")
    if r.get("fixed"):
        facts.append(f"fixed in {r['fixed']}")
    elif not r.get("malicious"):
        facts.append("no fix published")
    if r.get("runtime") is False:
        facts.append("a dev dependency" + (" nothing imports" if r.get("imported") is False else ""))
    elif r.get("imported") is False:
        facts.append("imported by no tracked file")
    return text, ", ".join(facts)


def _vuln_words(r: dict, where: bool = False) -> str:
    """'websocket-driver 0.7.4 (CVE-2026-54466), CVSS 9.2, fixed in 0.7.5, a dev dependency nothing imports',
    with its lock file when asked."""
    which, facts = _vuln_parts(r)
    return which + (f", {facts}" if facts else "") + (f", in {r['source']}" if where else "")


def _vuln_list(rows: list) -> str:
    """The rows of one lock file in words. Rows that share every fact are named together and the facts said
    once ('A 1.55.8 (CVE-2020-8911) and B 0.56.0 (GO-2026-5932); for both, no fix published, imported by no
    tracked file'), which is how prometheus's two packages in the lock a Dockerfile builds fit one entry."""
    parts = [_vuln_parts(r) for r in rows]
    if len(rows) > 1 and parts[0][1] and len({facts for _, facts in parts}) == 1:
        return f"{textfmt.join_and([which for which, _ in parts])}; for {'both' if len(rows) == 2 else 'each'}, {parts[0][1]}"
    return "; ".join(_vuln_words(r) for r in rows)


def _unshipped_critical(r: dict) -> bool:
    """A score in the critical band on a row that does not make the finding critical, since nothing declares
    that its lock ships (findings._vuln_critical): what a reader of "CVSS 9.2" under a ▲ has to be told."""
    return not findings._floating(r) and r.get("score") is not None and r["score"] >= findings.CRITICAL_SCORE and not r.get("deploys") and not r.get("malicious")


def _ships_words(reasons: list) -> str:
    """', which Dockerfile ships', or ', which Dockerfile and 88 more ship': the first thing that declares the
    lock's deployment (deps.deploys, sorted) and how many more do."""
    more = len(reasons) - 1
    return f", which {reasons[0]}" + (f" and {more:,} more ship" if more else " ships")


def _vuln_group(head: str, rows: list, why: bool, width: int) -> tuple:
    """(lines, rows named) for one lock file: `head`, then as many of `rows` as VULN_GROUP_LINES lines hold,
    in _vuln_list's words, the rest counted ("and 28 more there"), and WHY_WARNING last when the group holds
    the critical score that is a warning. The first row is always named; the reason gives way whole before
    a package's own facts are cut."""
    def said(k, reason, counted=True):
        listed = _vuln_list(rows[:k]) + (f" and {len(rows) - k:,} more there" if counted and len(rows) > k else "")
        return short_version((f"{head}: " if head else "") + listed + (WHY_WARNING if reason else ""))
    tries = [(k, reason, True) for reason in ([True, False] if why else [False]) for k in range(len(rows), 0, -1)]
    out = []
    for k, reason, counted in tries + [(1, False, False)]:   # last, the first row without the count of the rest, which the remainder line holds
        out = wrap(said(k, reason, counted), width, width - len(HANG))
        if len(out) <= VULN_GROUP_LINES:
            break
    out = cap(out, VULN_GROUP_LINES, width - len(HANG))
    return [out[0]] + [HANG + x for x in out[1:]], rows[:k]


def _vulnerable(f: dict, report: dict, ctx: dict):
    """'28 packages in 43 places across 5 lock files. By lock file:', then the lock files that make the
    finding matter, path first and whole, in a fixed order: the one a deploy declaration ships (the first in
    the rule's order) with its packages, the one holding the highest score, the one holding the package the
    step names (findings._vuln_first); then 'and N more packages: dependencies.json'. A lock file is one
    group, printed once: on prometheus the highest score and the step's pick are the same package, and that
    is two groups, not three. Every package named carries one advisory id, its fix or that none is published,
    and what the lock and the imports say of its reach; the group with a critical score that is a warning
    says why. prometheus's report named neither the package scoring 9.2 nor the two in the one lock file a
    Dockerfile builds, which have nothing to upgrade to. With one lock file there is one group and no path
    in front of it, since the statement names the file.

    The cap is VULN_GROUPS groups of VULN_GROUP_LINES lines and the remainder line: the one finding whose
    subject block is not held to SUBJECT_LINES. The note for lock files under tests, examples and vendored
    code is one sentence and no step, three lines with its title. The rows are the rule's own
    (findings._vuln_rows), since the evidence holds the first ten in reach order and the rows named here
    need not be among them."""
    group = next((g for rid, _, _, g in findings._vuln_rows(report or {}) if rid == f["rule"]["id"]), None)
    if not group:
        return None
    aside = f["rule"]["id"] == "vulnerable_dependencies_aside"
    locked = [r for r in group if not findings._floating(r)]
    ranges = [r for r in group if findings._floating(r)]
    pool = locked or group
    worst = findings._vuln_first(pool)
    sources = sorted({r["source"] for r in group})
    range_words = f"{textfmt.count(len(ranges), 'requirement range')} {_is(len(ranges), 'admits', 'admit')} a vulnerable version"
    if locked:
        names = len({r["name"] for r in locked})
        held = sorted({r["source"] for r in locked})
        places = f" in {len(locked):,} places across " if len(locked) != names else " in "
        lead = f"{textfmt.count(names, 'package')}{places}{held[0] if len(held) == 1 else deps.files_phrase(held)}"
        lead += f"; {range_words}" if ranges else ""
    else:
        lead = range_words + (f" in {sources[0]}" if len(sources) == 1 else "")
    scores = [r["score"] for r in pool if r.get("score") is not None]
    if aside:
        label = ("" if len(pool) == 1 else "Malicious" if worst.get("malicious")
                 else "Highest" if worst.get("score") is not None and worst["score"] == max(scores)
                 else "First to fix" if worst.get("fixed") else "First")
        named = short_version(f"{label}: {_vuln_words(worst, len(sources) > 1)}" if label else _vuln_words(worst, len(sources) > 1))
        return {"statement": f"{lead}{'. ' if label else ': '}{named}", "subjects": None, "step": None}
    shipped = next((r for r in pool if r.get("deploys")), None)
    highest = max(pool, key=lambda r: r["score"] if r.get("score") is not None else -1) if scores else None   # the first of equals, in the rule's order
    keys = [r for r in (highest, worst) if r is not None]
    several = len({r["source"] for r in pool}) > 1
    order = []   # the lock files, in the fixed order: shipped, highest score, the step's
    for r in ([shipped] if shipped else []) + keys:
        if r["source"] not in order:
            order.append(r["source"])
    warning = f["severity"] == "warning"
    inner = ctx["width"] - 2
    subjects, said = [], []
    for src in order[:VULN_GROUPS]:
        rows = [r for i, r in enumerate(keys) if r["source"] == src and r not in keys[:i]]
        ships = shipped["deploys"] if shipped and shipped["source"] == src else None
        if ships:   # every package of the lock that ships, the ones the other groups would name first
            rows += [r for r in pool if r["source"] == src and r not in rows]
        head = (src + (_ships_words(ships) if ships else "")) if several else ""
        why = warning and any(_unshipped_critical(r) for r in rows)
        lines, named = _vuln_group(head, rows, why, inner)
        subjects += lines
        said += named
    left = len({r["name"] for r in pool} - {r["name"] for r in said})
    if left:
        subjects.append(f"and {textfmt.count(left, 'more package')}: {DEPENDENCIES_FILE}")
    statement = lead + (_ships_words(shipped["deploys"]) if shipped and not several else "") + (". By lock file:" if several else "")
    advice = f["advice"]
    target = advice[:-len(findings.IGNORE_DEPS)].rstrip() if advice.endswith(findings.IGNORE_DEPS) else None
    return {"statement": statement, "subjects": subjects, "step": f"{target} {IGNORE_DEPS_SHORT}" if target else advice}


def _bug_magnets(f: dict, report: dict, ctx: dict):
    """'18 files were fixed 3 or more times in 6 months; no file more often than is usual for its size', then
    the files at the warning threshold by name in the evidence's order (recent fixes, then all fixes, then
    path) and the rest as a count, so the parts sum to the total: '7 at 5 or more: promql/engine.go 10, ... ·
    11 at 3 or 4'. The evidence names ten files at most; when all ten are at the threshold and there are more,
    how many are at it is not known here, and the block says 'Most fixed:' and counts the rest whole."""
    ev, rule = f["evidence"], f["rule"]
    n, files, low, warn = ev["count"], ev["files"], rule["min_recent"], rule["warn_at"]
    rate = ev.get("fix_rate") or {}
    above = rate.get("above_rate")
    if rate.get("not_run"):
        need = (rule.get("above_rate") or {}).get("min_history_months")
        tail = f"; raw counts, as the test against files of their size needs {need} months of history" if need else "; raw counts"
    elif above is None:
        tail = ""
    elif not above:
        tail = "; no file more often than is usual for its size"
    else:
        tail = f"; {len(above):,}{' or more' if len(above) >= 10 else ''} more often than is usual for {_is(len(above), 'its', 'their')} size"
    statement = f"{textfmt.count(n, 'file')} {_is(n, 'was', 'were')} fixed {low} or more times in {rule.get('window_months', 6)} months{tail}"
    new = set(ev.get("new_in_window") or [])
    names = [f"{x['file']}{NBSP}{x['recent_fixes']:,}" + (" (new in the window)" if x["file"] in new else "") for x in files]
    keys = [x["recent_fixes"] for x in files]
    hot = sum(1 for k in keys if k >= warn)
    known = hot < len(files) or len(files) == n   # whether every file at the threshold is among the ten named
    under = low if warn - 1 <= low else f"{low} or {warn - 1}" if warn - 1 == low + 1 else f"{low} to {warn - 1}"

    def said(k):
        if hot and known:
            rest = f" · {n - hot:,} at {under}" if n > hot else ""
            listed = (": " + ", ".join(names[:k]) + (f" and {hot - k:,} more" if hot > k else "")) if k else ""
            return f"{hot:,} at {warn} or more{listed}{rest}"
        return ("Most fixed: " + ", ".join(names[:k]) + (f" and {n - k:,} more" if n > k else "")) if k else ""
    subjects = most(hot if hot and known else len(files), said, ctx["width"] - 2, keys=keys, least=0)
    return {"statement": statement, "subjects": subjects, "step": f["advice"]}


def _printed(ctx: dict, sid: str, shows) -> bool:
    """Whether section `sid` is printed in this report with a row `shows` accepts: a "(see Section)" pointer
    may name only the finding's own subject table, with the subject in it."""
    sec = (ctx.get("printed") or {}).get(sid)
    return bool(sec) and any(shows(row) for row in sec.get("rows") or [])


def _brain_methods(f: dict, report: dict, ctx: dict):
    """'62 functions have 100 lines or more and complexity 15 or more. Worst: the anonymous function at
    discovery/aws/rds.go:542 (see Complex functions)': the Complex functions table below is this finding's
    subjects in this finding's order, so its first rows are not said twice. Without that table in the
    report, the worst function's numbers are said here."""
    ev, rule = f["evidence"], f["rule"]
    n, first = ev["count"], ev["functions"][0]
    place = findings._place(first)
    which = f"the anonymous function at {place}" if findings._anonymous(first) else f"{first['function']} in {first['file']}"
    pointed = _printed(ctx, "functions", lambda row: row[1] == place)
    statement = (f"{textfmt.count(n, 'function')} {_is(n, 'has', 'have')} {rule['min_lines']} lines or more and complexity {rule['min_ccn']} or more. "
                 f"Worst: {which}" + (" (see Complex functions)" if pointed else f", complexity {first['ccn']:,}, {first['lines']:,} lines"))
    if ev.get("partial"):
        statement += ". The function step stopped part way, so there may be more"
    said = f"Split {which} first, before the next change lands there."
    return {"statement": statement, "subjects": None, "step": "Split it first, before the next change lands there." if f["advice"] == said else f["advice"]}


def _pair_words(a: str, b: str) -> str:
    """'format.tsx and serialize.ts in web/ui/mantine-ui/src/promql/' for two files of one directory, the
    directory said once and whole; two whole paths otherwise."""
    da, _, na = a.rpartition("/")
    db, _, nb = b.rpartition("/")
    return f"{na} and {nb} in {da}/" if da and da == db else f"{a} and {b}"


def _tight_coupling(f: dict, report: dict, ctx: dict):
    """'1 pair changes together 80% of the time or more: format.tsx and serialize.ts in
    web/ui/mantine-ui/src/promql/, 86% (see Change coupling)': the count, the threshold, the first subject and
    the table that lists the rest, when that table is in the report and holds the subject. The evidence names
    ten pairs and ten directories at most, so a count at the cap is 'N or more'."""
    ev, rule = f["evidence"], f["rule"]
    groups, pairs = ev.get("clusters") or [], ev.get("pairs") or []
    when = f"{rule['min_degree']}% of the time or more"
    if groups:
        g = groups[0]
        pointed = _printed(ctx, "coupling", lambda row: row[0] == f"{g['dir']} ({g['files']:,} files)")
        dirs = _count(len(groups), "directory", "directories", capped=len(groups) >= 10)
        also = f" and {_count(len(pairs), 'more pair', capped=len(pairs) >= 10)}" if pairs else ""
        statement = (f"The files of {dirs}{also} change together {when}. "
                     f"{'Largest: ' if len(groups) > 1 else ''}{g['files']:,} files in {g['dir']}" + (" (see Change coupling)" if pointed else ""))
        return {"statement": statement, "subjects": None, "step": f["advice"]}
    if not pairs:
        return None
    p = pairs[0]
    pointed = _printed(ctx, "coupling", lambda row: row[0] == textfmt.brace_pair(p["a"], p["b"]))
    count = f"{_count(len(pairs), 'pair', capped=len(pairs) >= 10)} {_is(len(pairs), 'changes', 'change')} together {when}"
    statement = (f"{count}{': ' if len(pairs) == 1 else '. Highest: '}{_pair_words(p['a'], p['b'])}, {p['degree']}%"
                 + (" (see Change coupling)" if pointed else ""))
    said = f"Review {p['a']} and {p['b']} first: a shared layout or a hidden dependency links them."
    return {"statement": statement, "subjects": None,
            "step": "Look for a shared layout or a hidden dependency between the two." if f["advice"] == said else f["advice"]}


def _sweeping_commits(f: dict, report: dict, ctx: dict):
    """'18 commits each touch 49 files or more and take out as many lines as they put in. Largest: e14795bbf,
    587 files, 2026-01-05'. That they are left out of the churn, coupling and ownership counts is said by the
    sections that leave them out, and the step names none of them, since the file takes them all."""
    swept = findings.sweeps(report or {})
    if not swept:
        return None
    n, top = len(swept), max(swept, key=lambda c: c["files"])
    if n == 1:
        statement = f"1 commit touches {top['files']:,} files and takes out as many lines as it puts in: {top['hash']}, {top['date']}"
    else:
        statement = (f"{n:,} commits each touch {min(c['files'] for c in swept):,} files or more and take out as many lines as they put in. "
                     f"Largest: {top['hash']}, {top['files']:,} files, {top['date']}")
    declared = f["evidence"].get("declared") or 0
    already = f"; {textfmt.count(declared, 'commit')} {_is(declared, 'is', 'are')} declared there already" if declared else ""
    it = _is(n, "it", "them")
    return {"statement": statement, "subjects": None, "step": f"Add {it} to .git-blame-ignore-revs so git blame and GitHub skip {it} too{already}."}


def _unused_dependencies(f: dict, report: dict, ctx: dict):
    """'3 runtime dependencies: lodash in web/ui/mantine-ui/package.json and 2 more in
    web/ui/react-app/package.json': the count, the one the step names, and where the rest are when the
    evidence holds them all and they share a manifest."""
    ev = f["evidence"]
    n, rows = ev["count"], ev["unused"]
    first, rest = rows[0], rows[1:]
    statement = f"{n:,} runtime {_is(n, 'dependency', 'dependencies')}: {first['package']}"
    homes = {r["manifest"] for r in rest}
    if n > 1 and len(rows) == n and homes == {first["manifest"]}:
        statement += f" and {n - 1:,} more in {first['manifest']}"
    else:
        statement += f" in {first['manifest']}"
        if n > 1:
            statement += f" and {n - 1:,} more" + (f" in {next(iter(homes))}" if len(rows) == n and len(homes) == 1 else "")
    said = f"Remove {first['package']} from {first['manifest']} if nothing loads it at run time"
    return {"statement": statement, "subjects": None,
            "step": f"Remove {first['package']} if nothing loads it at run time." if f["advice"].startswith(said) else f["advice"]}


def _truck_factor(f: dict, report: dict, ctx: dict):
    """'9 people would have to leave before 333 of the 653 source files (51%) had no author left; 1 of the 9
    is already gone', then the areas where one person leaving would be enough, most files at stake first.
    The number is said by what it means; the names of a truck factor over three and the variant with
    knowledge halving every five months are in --full. An area's line gives its files, as web/'s 128 of 231
    do: "a single author" was not true of it. Merged with another ownership rule (findings.one_owner), or
    without the run's record of who is gone, the finding keeps its statement."""
    ev = f["evidence"]
    if "measures" in f["rule"] or not (report or {}).get("meta"):
        return None
    gone = findings._gone(report)
    tf, removed = ev["truck_factor"], ev["removed"]
    left = sum(1 for p in removed if p in gone)
    who = "1 person, " + removed[0] + "," if tf == 1 else f"{tf:,} people" + (f" ({textfmt.join_and(removed)})" if tf <= 3 else "")
    statement = (f"{who} would have to leave before {ev['orphaned']:,} of the {ev['files']:,} source files "
                 f"({findings._pct(ev['orphaned'], ev['files'])}) had no author left")
    if left:
        statement += ("; they are already gone" if tf == 1 else f"; all {tf:,} are already gone" if left == tf
                      else f"; {left:,} of the {tf:,} {_is(left, 'is', 'are')} already gone")
    areas = ev.get("areas") or []
    subjects = None
    if areas:
        capped = len(areas) >= 10   # the evidence names ten areas at most
        names = [f"{a['area']} ({a['author']}{' gone' if a['author'] in gone else ''}{', new since ' + a['new_since'] if a.get('new_since') else ''})" for a in areas]
        head = f"In {_count(len(areas), 'area', capped=capped)} one person leaving would be enough: "

        def said(k):
            if k == len(names) and not capped:
                return head + textfmt.join_and(names)
            return head + ", ".join(names[:k]) + (" and more" if capped else f" and {len(names) - k:,} more")
        subjects = most(len(names), said, ctx["width"] - 2)
    step = f["advice"]
    for a in areas:
        if step.startswith(f"Pair someone with {a['author']} on {a['area']} first;") and not a.get("new_since"):
            step = f"Pair someone with {a['author']} on {a['area']} first: {a['orphaned']:,} of its {a['files']:,} files would have no author left."
            break
    return {"statement": statement, "subjects": subjects, "step": step}


# --- the rules not measured yet (findings.UNJUDGED) ------------------------------------------------------
#
# One statement each: the count and the rule's numbers, then the subject the rule's own advice picks, which is
# not always the first the long statement lists (the debt finding lists hotspots in rank order and advises
# the one with the most markers). A note of these prints as that statement alone (compact); a warning prints
# it with its step, like any other finding.

def _lead(f: dict) -> str:
    """What the rule's statement says before its list: the count and the thresholds, in the rule's words."""
    return textfmt._statement_and_advice(f)[0].partition(": ")[0]


def _deep_nesting(f: dict, report: dict, ctx: dict):
    """'147 functions nest 5 levels or more or carry 3 or more separate nested chunks. Worst: eval at
    promql/engine.go:2132, nested 6 deep': the function the advice names, which is the first in a top hotspot
    when the finding is a warning for one, and the deepest by cognitive complexity otherwise. Past the ten
    functions of the evidence the advice's own cannot be described, and the first is named with the advice
    whole."""
    ev, rule = f["evidence"], f["rule"]
    n, rows = ev["count"], ev["functions"]

    def which(fn):
        return f"the anonymous function at {fn['file']}:{fn['start']}" if findings._anonymous(fn) else f"{fn['name']} in {fn['file']}"
    picked = next((fn for fn in rows if f["advice"].startswith(f"Flatten {which(fn)} first:")), None)
    fn = picked or rows[0]
    called = f"the anonymous function at {fn['file']}:{fn['start']}" if findings._anonymous(fn) else f"{fn['name']} at {fn['file']}:{fn['start']}"
    how = f"nested {fn['nesting']} deep" if fn["nesting"] >= rule["min_nesting"] else f"{fn['bumps']} nested chunks"
    label = "Worst" if fn is rows[0] else "In a top hotspot"
    statement = (f"{textfmt.count(n, 'function')} {_is(n, 'nests', 'nest')} {rule['min_nesting']} levels or more or {_is(n, 'carries', 'carry')} "
                 f"{rule['min_bumps']} or more separate nested chunks. {label}: {called}, {how}")
    said = f"Flatten {which(fn)} first: return early and move each nested chunk into a function of its own."
    return {"statement": statement, "subjects": None,
            "step": "Flatten it first: return early, move each nested chunk into a function." if picked and f["advice"] == said else f["advice"]}


def _debt_in_hotspots(f: dict, report: dict, ctx: dict):
    """'8 of the top 10 hotspots carry TODO, FIXME, XXX or HACK comments; most in
    storage/remote/queue_manager.go (10)': the file with the most markers, which is the one the advice names
    and on prometheus the seventh the statement lists."""
    rows = f["evidence"]["files"]
    top = max(rows, key=lambda r: r["markers"])   # the first of equals, as the rule takes it
    return {"statement": f"{_lead(f)}{'; most in' if len(rows) > 1 else ':'} {top['file']} ({top['markers']:,})", "subjects": None, "step": f["advice"]}


def _same_pair(p: dict, q: dict) -> bool:
    return {p["a"], p["b"]} == {q["a"], q["b"]}


def _said_above(f: dict, pair: dict, ctx: dict) -> bool:
    """Whether Files that always change together, printed above this finding, already names `pair` as its one
    subject (_tight_coupling names its first pair when it has no directory to name)."""
    found = ctx.get("found") or []
    at = next((i for i, x in enumerate(found) if x is f), None)
    for x in found[:at] if at is not None else []:
        ev = x.get("evidence") or {}
        if (x.get("rule") or {}).get("id") == "tight_coupling" and not ev.get("clusters") and ev.get("pairs"):
            return _same_pair(ev["pairs"][0], pair)
    return False


def _hidden_coupling(f: dict, report: dict, ctx: dict):
    """'1 pair, the one above; neither file imports the other' when Files that always change together has
    just named it (prometheus printed format.tsx and serialize.ts twice, eight lines apart); else the pair
    with its share. The evidence names ten pairs at most, and the statement counts the rest."""
    ev, rule = f["evidence"], f["rule"]
    pairs = ev["pairs"]
    counted = _MORE.search(textfmt._statement_and_advice(f)[0])
    n = (3 + int((counted.group(1) or counted.group(2)).replace(",", ""))) if counted else len(pairs)
    p = pairs[0]
    above = _said_above(f, p, ctx)
    named = f"{_pair_words(p['a'], p['b'])}, {p['degree']}%"
    if n == 1:
        statement = ("1 pair, the one above; neither file imports the other" if above
                     else f"1 pair changes together {rule['min_degree']}% of the time or more and neither file imports the other: {named}")
    else:
        statement = (f"{n:,} pairs change together {rule['min_degree']}% of the time or more with no import between the two files. "
                     f"Highest: {'the one above' if above else named}")
    return {"statement": statement, "subjects": None, "step": f["advice"]}


def _loop_words(loop: list) -> str:
    """'AlertContents.tsx and CollapsibleAlertPanel.tsx in web/ui/react-app/src/pages/alerts/' for two files
    that import each other; a longer loop as the rule writes it, file → file → back."""
    return _pair_words(loop[0], loop[1]) if len(loop) == 3 else " → ".join(loop)


def _import_cycles(f: dict, report: dict, ctx: dict):
    """'6 groups, the largest 16 files; its shortest loop: AlertContents.tsx and CollapsibleAlertPanel.tsx in
    web/ui/react-app/src/pages/alerts/': the loop the advice says to break first, the largest group's."""
    ev = f["evidence"]
    n, g = ev["count"], ev["groups"][0]
    size = f"{g['size']:,} files"
    statement = (f"1 group of {size}" if n == 1 else f"{n:,} groups, the largest {size}") + f"; its shortest loop: {_loop_words(g['loop'])}"
    return {"statement": statement, "subjects": None, "step": f["advice"]}


def _unreferenced_files(f: dict, report: dict, ctx: dict):
    """'3 files imported by nothing in the tree; first discovery/install/install.go', the one the advice says
    to check before anything else."""
    ev = f["evidence"]
    n, first = ev["count"], ev["files"][0]
    statement = f"{first}, imported by nothing in the tree" if n == 1 else f"{n:,} files imported by nothing in the tree; first {first}"
    return {"statement": statement, "subjects": None, "step": f["advice"]}


def _commented_out_code(f: dict, report: dict, ctx: dict):
    """'4 source files hold 10 or more lines of commented-out code; most in src/a.py (40 lines from line
    12)', the block the advice says to delete."""
    rows = f["evidence"]["files"]
    top = rows[0]
    lead = _lead(f)
    one = lead.startswith("1 ")
    return {"statement": f"{lead}{':' if one else '; most in'} {top['file']} ({textfmt.count(top['lines'], 'line')} from line {top['start']:,})",
            "subjects": None, "step": f["advice"]}


def _hardcoded_addresses(f: dict, report: dict, ctx: dict):
    """'12 IPv4 addresses in string literals in 5 source files; first 10.1.2.3 at src/net.py:8', the one the
    advice says to move into configuration."""
    ev = f["evidence"]
    top = ev["files"][0]
    return {"statement": f"{_lead(f)}{':' if ev['count'] == 1 else '; first'} {top['value']} at {top['file']}:{top['start']}", "subjects": None, "step": f["advice"]}


def _swallowed_errors(f: dict, report: dict, ctx: dict):
    """'9 empty catch blocks in 4 source files, 2 of them a bare except; first in a top hotspot: src/a.py:12
    (3 there)', or 'most in' the file with the most when no hotspot holds one: the file the advice names."""
    ev = f["evidence"]
    rows, hot = ev["files"], ev.get("hotspots") or []
    top = next((r for r in rows if hot and r["file"] == hot[0]), None)
    if hot and top is None:   # the hotspot's row is past the ten the evidence names
        return {"statement": f"{_lead(f)}; first in a top hotspot: {hot[0]}", "subjects": None, "step": f["advice"]}
    top = top or rows[0]
    label = "first in a top hotspot:" if hot else "most in" if len(rows) > 1 else "in"
    there = f" ({top['count']:,} there)" if top.get("count", 1) > 1 and len(rows) > 1 else ""
    return {"statement": f"{_lead(f)}; {label} {top['file']}:{top['start']}{there}", "subjects": None, "step": f["advice"]}


FORMS = {"credential_files": _credential_files, "vulnerable_dependencies": _vulnerable, "vulnerable_dependencies_aside": _vulnerable,
         "bug_magnets": _bug_magnets, "brain_methods": _brain_methods, "tight_coupling": _tight_coupling,
         "sweeping_commits": _sweeping_commits, "unused_dependencies": _unused_dependencies, "truck_factor": _truck_factor,
         "deep_nesting": _deep_nesting, "debt_in_hotspots": _debt_in_hotspots, "hidden_coupling": _hidden_coupling, "import_cycles": _import_cycles,
         "unreferenced_files": _unreferenced_files, "commented_out_code": _commented_out_code, "hardcoded_addresses": _hardcoded_addresses,
         "swallowed_errors": _swallowed_errors}


# --- every other rule -----------------------------------------------------------------------------------

_MORE = re.compile(r"(?: and ([\d,]+) more| \(([\d,]+) more [a-z]+(?: like them)?\))$")


def _fallback(statement: str, width: int) -> dict:
    """A finding without a short form of its own: its statement whole when that is WHOLE_LINES lines or
    fewer; else the lead (what comes before the first colon of its first sentence: the count and the rule's
    numbers) and at most SUBJECT_LINES lines of the list after it, cut between two entries and closed with
    'and N more', N counting the entries dropped here and the ones the statement had already counted. The
    sentences after the list are in --full."""
    if len(wrap(statement, width)) <= WHOLE_LINES:
        return {"statement": statement, "subjects": None}
    head = textfmt._SENTENCE_END.split(statement.strip())[0].rstrip(".")
    lead, colon, listing = head.partition(": ")
    if not colon:
        lead, listing = "", head
    items = listing.split("; ")
    counted = _MORE.search(items[-1])
    already = int((counted.group(1) or counted.group(2)).replace(",", "")) if counted else 0
    if counted:
        items[-1] = items[-1][:counted.start()]

    def said(k):
        rest = len(items) - k + already
        return "; ".join(items[:k]) + (f" and {rest:,} more" if rest else "")
    subjects = most(len(items), said, width - 2 if lead else width)
    return {"statement": f"{lead}:", "subjects": subjects} if lead else {"statement": "\n".join(subjects), "subjects": None}


def _made(f: dict, report: dict, ctx: dict):
    """The rule's own short form, or None: no form, no evidence, or evidence from before a key the form reads
    existed (an older export, a hand-made dict), where the statement stands."""
    form = FORMS.get((f.get("rule") or {}).get("id"))
    if not (form and f.get("evidence") and f.get("advice")):
        return None
    try:
        return form(f, report, ctx)
    except (KeyError, IndexError, TypeError, ValueError):
        return None


def short(f: dict, report: dict = None, width: int = 74, printed: dict = None, found: list = None) -> dict:
    """The finding as the default report prints it: {"statement": lines, "subjects": lines, "step": lines},
    each line at most `width` characters (the subjects and the step two fewer, for their indent). `printed`
    is the report's sections by id, for the "(see Section)" pointer, and `found` the report's findings in
    their order, for a note that restates a subject printed above it. A finding whose evidence lacks what its
    short form reads (an older export, a hand-made dict) takes the fallback, as a rule without one does."""
    ctx = {"width": width, "printed": printed or {}, "found": found or []}
    made = _made(f, report, ctx)
    statement, advice = textfmt._statement_and_advice(f)
    marked = statement.startswith(BASELINE_MARK)
    if made is None:
        made = {**_fallback(short_version(statement[len(BASELINE_MARK):] if marked else statement), width - (len(BASELINE_MARK) if marked else 0)), "step": advice}
    parts = short_version(made["statement"]).split("\n")   # the fallback's list comes wrapped already
    parts[0] = (BASELINE_MARK if marked else "") + parts[0]
    lines = [x for part in parts for x in wrap(part, width)]
    subjects = made.get("subjects") or []
    step = step_lines(short_version(made["step"]), width - 2) if made.get("step") else []
    return {"statement": lines, "subjects": [short_version(x) for x in subjects], "step": step}


LONG_SUBJECTS = 5       # the subjects --full prints under a finding, one a line: what a rule's statement names


def long(f: dict, width: int = 74) -> dict:
    """The finding as --full and `--section findings` print it: {"statement": lines, "subjects": lines, "more":
    lines}, the fact, then the subjects the rule's statement names, one a line (LONG_SUBJECTS at most, the
    lines one wraps to indented under it, and a last line counting the rest), then what the statement says
    after its list. Nothing is cut and no version is shortened: this is the rule's own statement, laid out.
    prometheus's Vulnerable dependencies was one paragraph of eleven lines with its three packages between
    semicolons. A statement that is no list (no colon in its first sentence, or one subject after it) is
    printed whole."""
    made = parts(f)
    if not made["subjects"]:
        return {"statement": wrap(made["statement"], width), "subjects": [], "more": []}
    rest = made["rest"] + max(len(made["subjects"]) - LONG_SUBJECTS, 0)
    subjects = []
    for item in made["subjects"][:LONG_SUBJECTS]:
        lines = wrap(item, width - 2, width - 2 - len(HANG))
        subjects += [lines[0]] + [HANG + x for x in lines[1:]]
    if rest:
        subjects.append(f"and {rest:,} more")
    return {"statement": wrap(made["statement"], width), "subjects": subjects, "more": wrap(made["more"], width) if made["more"] else []}


def parts(f: dict) -> dict:
    """A finding's statement taken apart and not yet laid out: {"statement": the fact, with its colon when a list
    follows, "subjects": what the statement lists after it, "rest": how many more it counts and does not name,
    "more": what it says after the list}. A statement that is no list (no colon in its first sentence, or one
    subject after it) is its own "statement", whole. `long` wraps these for a terminal; the Markdown export
    prints them as a paragraph, a nested list and a paragraph, every subject the statement names, which
    prometheus's export ran together as one paragraph of 945 characters."""
    statement = textfmt._statement_and_advice(f)[0]
    marked = statement.startswith(BASELINE_MARK)
    body = statement[len(BASELINE_MARK):] if marked else statement
    sentences = textfmt._SENTENCE_END.split(body.strip())
    lead, colon, listing = sentences[0].partition(": ")
    items = listing.rstrip(".").split("; ") if colon else []
    if len(items) < 2:
        return {"statement": statement, "subjects": [], "rest": 0, "more": ""}
    counted = _MORE.search(items[-1])
    rest = int((counted.group(1) or counted.group(2)).replace(",", "")) if counted else 0
    if counted:
        items[-1] = items[-1][:counted.start()]
    return {"statement": (BASELINE_MARK if marked else "") + lead + ":", "subjects": items, "rest": rest,
            "more": " ".join(sentences[1:]) if len(sentences) > 1 else ""}


def compact(f: dict, report: dict = None, width: int = 74, lead: int = 0, printed: dict = None, found: list = None) -> list:
    """A note from a rule not measured yet, as the lines after 'Title (not measured yet): ': its statement and
    nothing else, in COMPACT_LINES lines at most, the first of them `lead` characters shorter since the title
    and the tag are on it. No step: the rule's worth is not known, and the statement names the subject its
    advice would. A finding with no form of its own, or without the evidence its form reads, gives the lead of
    its statement and as much of its list as fits. When not even the statement's first word fits beside the
    title, the first line is empty and the statement starts under it."""
    ctx = {"width": width, "printed": printed or {}, "found": found or []}
    made = _made(f, report, ctx)
    statement = textfmt._statement_and_advice(f)[0]
    marked = statement.startswith(BASELINE_MARK)
    if made is None:
        text = statement[len(BASELINE_MARK):] if marked else statement
    else:
        text = " ".join([made["statement"]] + list(made.get("subjects") or []))
    text = (BASELINE_MARK if marked else "") + short_version(text)
    first = width - lead
    words = text.split(" ")
    if first < len(words[0]):
        return [""] + cap(wrap(text, width), COMPACT_LINES - 1, width)
    return cap(wrap(text, first, width), COMPACT_LINES, width)

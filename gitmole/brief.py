"""The short form of a finding, for the default terminal report: the count and the rule's numbers, the worst
subject, and one step. It is a second rendering of the same `rule` and `evidence`, not the long sentence cut
off: `--full`, the Markdown export, the JSON and SARIF keep the enumeration (`detail`) byte for byte, since
nothing here writes to a finding. prometheus's Findings box was 88 of the default report's 211 lines at 80
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
SUBJECT_LINES = 3       # the subject lines of one finding, a hard cap
STEP_LINES = 3          # the step's lines
WHOLE_LINES = 3         # a statement this short has no need of a short form
BASELINE_MARK = "In the baseline: "   # gate.BASELINE_MARK, which --baseline puts in front of a finding's detail
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


def wrap(text: str, width: int) -> list:
    """`text` as lines of at most `width` characters, broken at spaces only: a path, a hash, a package or a
    version is never split (one longer than a line is left whole on a line of its own), a separator stays at
    the end of the line before it, and what a no-break space joins stays together."""
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
        if line and len(line) + 1 + len(w) > width:
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


WHY_WARNING = "; a warning, not critical, as nothing beside it declares a deployment"


def _vuln_words(r: dict, where: bool, warning: bool) -> str:
    """One vulnerable row: name, version, one advisory id, its score, its fix or that none is published, what
    the lock and the imports say of its reach, its lock file when the finding has several, and why a
    critical score is a warning here (WHY_WARNING, always last)."""
    ref = findings._malicious_id(r) or next(iter(list(r.get("aliases") or []) + list(r.get("ids") or [])), "")
    floating = findings._floating(r)
    if floating and r.get("requirement") is not None:
        text = f"{r['name']}{r['requirement'] or ' (any version)'}, whose floor is {r['version']}"
    else:
        text = f"{r['name']} {r['version']}"
    text += f" ({ref})" if ref else ""
    if r.get("malicious"):
        text += ", malicious"
    elif r.get("score") is not None:
        text += f", CVSS {r['score']:.1f}"
    text += f", fixed in {r['fixed']}" if r.get("fixed") else "" if r.get("malicious") else ", no fix published"
    if r.get("runtime") is False:
        text += ", a dev dependency" + (" nothing imports" if r.get("imported") is False else "")
    elif r.get("imported") is False:
        text += ", imported by no tracked file"
    text += f", in {r['source']}" if where else ""
    if warning and not floating and r.get("score") is not None and r["score"] >= findings.CRITICAL_SCORE and not r.get("deploys"):
        text += WHY_WARNING
    return text


def _vulnerable(f: dict, report: dict, ctx: dict):
    """'28 packages in 43 places across 5 lock files' and the one row the advice names (findings._vuln_first):
    the count, the lock files, the worst package, the step. The note for lock files under tests, examples and
    vendored code is one sentence and no step, three lines with its title. The rows are the rule's own
    (findings._vuln_rows), since the evidence holds the first ten in reach order and the advice's row need
    not be among them."""
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
    label = ("" if len(pool) == 1 else "Malicious" if worst.get("malicious")
             else "Highest" if worst.get("score") is not None and worst["score"] == max(scores)
             else "First to fix" if worst.get("fixed") else "First")
    words = _vuln_words(worst, len(sources) > 1, f["severity"] == "warning")
    named = short_version(f"{label}: {words}" if label else words)
    if aside:
        return {"statement": f"{lead}{'. ' if label else ': '}{named}", "subjects": None, "step": None}
    advice = f["advice"]
    target = advice[:-len(findings.IGNORE_DEPS)].rstrip() if advice.endswith(findings.IGNORE_DEPS) else None
    inner = ctx["width"] - 2
    if len(wrap(named, inner)) > SUBJECT_LINES and named.endswith(WHY_WARNING):
        named = named[:-len(WHY_WARNING)]   # the reason gives way before the package's own facts are cut
    return {"statement": lead, "subjects": cap(wrap(named, inner), SUBJECT_LINES, inner), "step": f"{target} {IGNORE_DEPS_SHORT}" if target else advice}


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


FORMS = {"credential_files": _credential_files, "vulnerable_dependencies": _vulnerable, "vulnerable_dependencies_aside": _vulnerable,
         "bug_magnets": _bug_magnets, "brain_methods": _brain_methods, "tight_coupling": _tight_coupling,
         "sweeping_commits": _sweeping_commits, "unused_dependencies": _unused_dependencies, "truck_factor": _truck_factor}


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


def short(f: dict, report: dict = None, width: int = 74, printed: dict = None) -> dict:
    """The finding as the default report prints it: {"statement": lines, "subjects": lines, "step": lines},
    each line at most `width` characters (the subjects and the step two fewer, for their indent). `printed`
    is the report's sections by id, for the "(see Section)" pointer. A finding whose evidence lacks what its
    short form reads (an older export, a hand-made dict) takes the fallback, as a rule without one does."""
    ctx = {"width": width, "printed": printed or {}}
    form = FORMS.get((f.get("rule") or {}).get("id"))
    made = None
    if form and f.get("evidence") and f.get("advice"):
        try:
            made = form(f, report, ctx)
        except (KeyError, IndexError, TypeError):
            made = None   # evidence from before a key existed: the statement stands
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

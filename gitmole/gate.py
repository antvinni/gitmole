"""What a gate (--fail-on, --risk-threshold) can and cannot vouch for; the hook is context and gates nothing.

A gate that stops on findings has checked only what the steps it reads left behind. A betterleaks that
timed out leaves no secrets table, so no secrets finding and nothing for --fail-on critical to stop on:
without this module the exit code was 0, the same as a clean scan. A gate whose steps did not all finish
says which did not and exits EXIT_INCOMPLETE instead, unless it found what it stops on anyway, which is
an answer whatever else is missing."""
from __future__ import annotations

EXIT_FOUND = 3        # the gate found what it stops on
EXIT_INCOMPLETE = 4   # the gate could not check: a step it reads did not complete

# The steps no rule reads: the two plots draw pictures, and the backtest scores the watch list against the
# repository's own past, which only the report's backtest section and the measurement harness read.
# Every other step writes a file some rule reads, so a gate on findings depends on all of them.
UNREAD_STEPS = frozenset({"theseus stack plot", "theseus survival plot", "backtest"})
# the watch score, --risk-threshold's and the hook's number: revisions from the log, lines of code from scc
RISK_STEPS = frozenset({"scc", "git-log", "change analysis"})

WORDS = {"timeout": "timed out", "failed": "failed", "skipped": "was skipped (a step it needs did not complete)",
         "cancelled": "was cancelled"}


def unfinished(report: dict, steps=None) -> list:
    """[(step, status)] for each recorded step a rule reads that did not complete, or only those in `steps`.
    An output directory from before steps were recorded (meta.json without `steps`) gives [], as nothing
    about it can be said."""
    recorded = (report.get("meta") or {}).get("steps") or {}
    return [(name, status) for name, status in sorted(recorded.items())
            if status != "run" and name not in UNREAD_STEPS and (steps is None or name in steps)]


# --- the dependency gate without a database ----------------------------------
#
# osv-scanner run offline with no database on disk exits cleanly having matched nothing: the step is "run",
# dependencies.json says no-database, and without this the gate passed a repository whose packages nobody
# checked. It is not a failed step: the Action's default downloads no database, so an exit 4 on every
# default CI run would be an exit code everybody learns to ignore. It is said once on stderr and in the
# SARIF invocation always; --require-vuln-db, for a pipeline that did ask for the database, makes it exit 4.

NO_DATABASE_NOTE = "dependency gate: no vulnerability database; nothing was checked"


def no_database(report: dict) -> bool:
    """Whether the dependency scan ran with no vulnerability database, so no package was checked. A
    repository with no lock file (no-sources) had nothing to check and is not this."""
    return ((report.get("dependencies") or {}).get("status")) == "no-database"


def describe(missing: list) -> str:
    """'betterleaks timed out, osv-scanner failed'."""
    return ", ".join(f"{name} {WORDS.get(status, status)}" for name, status in missing)


def tripped(found: list, level: str) -> bool:
    """Whether any finding is at `level` or worse."""
    from .findings import SEVERITIES
    return any(SEVERITIES.index(f["severity"]) <= SEVERITIES.index(level) for f in found)


def tripping(found: list, level: str, where: str = "") -> list:
    """One line per rule with a finding at `level` or worse, for stderr: an exit 3 with nothing said left a CI
    log reader to rerun the scan to learn what it stopped on. `where` names the repository in a portfolio.
    A rule nobody has labelled yet (findings.UNJUDGED) counts like any other, as docs/output.md has said since
    the default report began folding them into one line: the gate fails closed, and a pipeline gating on
    warnings may rely on deep nesting. But the report shows such a finding only as a count in that line, so
    the line that names what tripped the gate says it was one of those (paperclip: deep_nesting tripped
    --fail-on warning from "N more from the structure step, not labelled yet")."""
    from .findings import SEVERITIES
    by = {}
    for f in found:
        if SEVERITIES.index(f["severity"]) <= SEVERITIES.index(level):
            by.setdefault(f["rule"]["id"], []).append(f)
    lines = []
    for rule, fs in by.items():
        worst = min((f["severity"] for f in fs), key=SEVERITIES.index)
        titles = "; ".join(dict.fromkeys(f["title"] for f in fs))
        folded = "; not labelled yet, so the report folds it into its closing line, and it counts all the same" if any(f.get("unjudged") for f in fs) else ""
        lines.append(f"--fail-on {level}: {where + ': ' if where else ''}{rule}, {len(fs)} {worst} finding{'s' if len(fs) != 1 else ''}"
                     f" ({titles}{folded}) (exit {EXIT_FOUND})")
    return lines


# --- the baseline ----------------------------------------------------------
#
# A mature repository's history holds secrets in files deleted years ago; the secrets step always reads the
# whole history, and rotating a key does not take it out of git, so --fail-on critical would block such a
# repository on every run forever. --baseline names an earlier --json export of the same clone: what it
# already held is still reported, marked, and does not count toward --fail-on; anything new does.

BASELINE_MARK = "In the baseline: "


def _secret_place(row: dict) -> str:
    """betterleaks' own fingerprint (commit:file:rule:line), the identity .betterleaksignore takes: a place,
    not the value, whose keyed hash differs on every run by design."""
    return row.get("fingerprint") or ":".join(str(row.get(k) or "") for k in ("commit", "file", "rule", "line"))


def _package(row: dict) -> tuple:
    return (row.get("name"), row.get("version"), row.get("source"), tuple(sorted(row.get("ids") or [])))


def _unpinned(rep: dict):
    a = (rep.get("hygiene") or {}).get("actions")
    return None if a is None else a.get("unpinned") or []


def _with_unpinned(rep: dict, rows: list) -> dict:
    h = rep.get("hygiene") or {}
    return {**rep, "hygiene": {**h, "actions": {**(h.get("actions") or {}), "unpinned": rows, "unpinned_count": len(rows)}}}


def _deep(rep: dict):
    s = rep.get("structure")
    return None if not isinstance(s, dict) or "functions" not in s else s.get("functions") or []


def _row_rules():
    """The rules that fold many rows into one finding, as (rule, identity, rows_of, with_rows, held): how to take
    rows out of a report, what a row is, how to put rows back, and which rows of a baseline export its finding
    held. A finding's rule id says nothing about which values, packages, actions or functions it holds, so for
    these the rows the baseline's finding did not hold are judged again on their own. `held` gives None for an
    export from before it carried those rows; that rule is then judged by its key, as every rule was until 0.42.0.
    For secrets and vulnerable dependencies every row is a finding's, so what a baseline held is all its rows;
    for the rest a row is only a subject when the rule picks it, so what the baseline held is what the rule
    picks from the baseline's own rows (the evidence keeps ten, which would make the eleventh look new)."""
    from . import findings

    def picked(pick, present):
        return lambda rep: pick(rep) if present(rep) is not None else None
    return (
        (findings.secrets_found, _secret_place,
         lambda rep: rep.get("secrets") or [],
         lambda rep, rows: {**rep, "secrets": rows},
         lambda rep: rep.get("secrets") or []),
        (findings.vulnerable_dependencies, _package,
         lambda rep: (rep.get("dependencies") or {}).get("vulnerable") or [],
         lambda rep, rows: {**rep, "dependencies": {**(rep.get("dependencies") or {}), "vulnerable": rows}},
         lambda rep: (rep.get("dependencies") or {}).get("vulnerable") or []),
        # a workflow file and the action it names: the same action added to another workflow is new
        (findings.unpinned_actions, lambda r: (r.get("file"), r.get("uses")), lambda rep: _unpinned(rep) or [], _with_unpinned, _unpinned),
        # a function by its file and name: one that grew past the thresholds is new, one that moved to another file is too
        (findings.brain_methods, lambda r: (r.get("file"), r.get("function")), lambda rep: rep.get("functions") or [],
         lambda rep, rows: {**rep, "functions": rows}, picked(findings.brain_rows, lambda rep: rep.get("functions"))),
        (findings.deep_nesting, lambda r: (r.get("file"), r.get("name")), lambda rep: _deep(rep) or [],
         lambda rep, rows: {**rep, "structure": {**(rep.get("structure") or {}), "functions": rows}}, picked(findings.deep_rows, _deep)),
        (findings.bug_magnets, lambda r: r.get("entity"), lambda rep: rep.get("fixes") or [],
         lambda rep, rows: {**rep, "fixes": rows}, picked(findings.magnet_rows, lambda rep: rep.get("fixes"))),
        # a bidirectional character or a mixed-script token by its file, the character or token, and which occurrence in
        # that file it is (findings.trojan_identities), not its line: an unrelated edit above a known token moves nothing
        (findings.trojan_source, lambda r: r["identity"], lambda rep: _trojan(rep) or [], _with_trojan, _trojan),
        # a manifest behind its lock file, by the manifest: the next release's version bump in a known one is not new
        (findings.lockfile_drift, lambda r: r.get("manifest"), findings.drift_rows, _with_drift,
         lambda rep: findings.drift_rows(rep) if "drift" in ((rep.get("hygiene") or {}).get("lockfiles") or {}) else None),
    )


def _trojan(rep: dict):
    """The trojan rows, each with its identity beside it; None for an export without the hygiene step's record."""
    tj = (rep.get("hygiene") or {}).get("trojan")
    if tj is None:
        return None
    from .findings import trojan_identities
    return [{**r, "identity": ident, "kind": ident[0]} for ident, r in trojan_identities(tj)]


def _with_trojan(rep: dict, rows: list) -> dict:
    h = rep.get("hygiene") or {}
    keep = {kind: [{k: v for k, v in r.items() if k not in ("identity", "kind")} for r in rows if r["kind"] == kind] for kind in ("bidi", "mixed_script")}
    return {**rep, "hygiene": {**h, "trojan": {**(h.get("trojan") or {}), **keep, "bidi_count": len(keep["bidi"]),
                                               "mixed_script_count": len(keep["mixed_script"])}}}


def _with_drift(rep: dict, rows: list) -> dict:
    h = rep.get("hygiene") or {}
    return {**rep, "hygiene": {**h, "lockfiles": {**(h.get("lockfiles") or {}), "drift": rows, "drift_count": len(rows)}}}


def _truck_subjects(f: dict) -> set:
    """The people a truck factor hangs on, and its areas of one when the evidence lists them all (it keeps ten)."""
    ev = f.get("evidence") or {}
    areas = ev.get("areas") or []
    return {("without", p) for p in ev.get("removed") or []} | ({("area", a.get("area")) for a in areas} if len(areas) < 10 else set())


def _grown_subjects(f: dict) -> set:
    """The hotspots a complexity growth finding names as grown: all of them, as it judges only the top ten."""
    return {g.get("file") for g in (f.get("evidence") or {}).get("grown") or [] if isinstance(g, dict)}


# the rules judged by their key whose findings name subjects with no rows behind them in the export: a truck factor's
# people and areas of one, complexity growth's grown hotspots. Both are set rules (a count over the whole tree, three
# or more of the top ten), so they cannot be run again over the new subjects alone as _row_rules' rules are.
SUBJECTS = {"truck_factor": _truck_subjects, "complexity_growth": _grown_subjects}


def _subjects_grew(f: dict, old: dict) -> bool:
    """Whether a finding judged by its key holds a subject the baseline's finding did not: a person a truck factor
    hangs on or an area of one, a hotspot that grew which the baseline's growth finding did not name."""
    subjects = SUBJECTS.get(f["rule"]["id"])
    return subjects is not None and bool(subjects(f) - subjects(old))


def against_baseline(report: dict, found: list, before: dict) -> list:
    """Mark each finding of `found` new or in the baseline `before` (an earlier --json export), and return the
    findings that count toward --fail-on. A finding is in the baseline when the export has one with the same
    key (compare.key: the rule id, and the metric or email for the rules that emit several) at the same
    severity or worse. For the rules that fold many subjects into one finding (_row_rules: secrets, vulnerable
    dependencies, unpinned actions, brain methods, deep nesting, bug magnets, Trojan Source, lock file drift) that
    key says nothing about which subjects the finding holds, so their rows are compared instead - a secret's place
    by betterleaks' fingerprint, a package by name, version, lock file and advisory ids, an action by workflow file
    and ref, a function by file and name, a magnet by file, a Trojan Source character or token by file, itself and
    its occurrence in that file, a drifted lock file by its manifest - and the rows the baseline's finding did not
    hold are run through the same rule on their own: what that finds, at the severity it finds it, is what counts.
    A value committed again in a new place is a new row, and counts. A truck factor counts when it hangs on a
    person, or names an area of one, the baseline's did not; complexity growth when a hotspot grew that the
    baseline's did not name. An export without a rule's rows (from before they were exported) judges that rule
    by its key alone. The hygiene step keeps 50 rows a list: past that, a row the baseline had beyond its 50 that
    surfaces when one of them goes reads as new, and counts - the gate fails closed rather than open."""
    from . import compare
    from .findings import SEVERITIES
    was = {compare.key(f): f for f in before.get("findings") or []}
    counted, fresh_ids, row_ids = [], set(), set()
    for rule, identity, rows_of, with_rows, held in _row_rules():
        old = held(before)
        if old is None:
            continue
        row_ids |= {f["rule"]["id"] for f in rule(report)}
        known = {identity(r) for r in old}
        fresh = rule(with_rows(report, [r for r in rows_of(report) if identity(r) not in known]))
        counted += fresh
        fresh_ids |= {f["rule"]["id"] for f in fresh}
    for f in found:
        rid = f["rule"]["id"]
        if rid in row_ids:
            new = rid in fresh_ids
        else:
            old = was.get(compare.key(f))
            new = old is None or SEVERITIES.index(f["severity"]) < SEVERITIES.index(old["severity"]) or _subjects_grew(f, old)
            if new:
                counted.append(f)
        f["baseline"] = "new" if new else "in the baseline"
        if not new:
            f["detail"] = BASELINE_MARK + f["detail"]
    return counted

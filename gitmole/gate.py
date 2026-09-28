"""What a gate (--fail-on, --risk-threshold, the hook) can and cannot vouch for.

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


def describe(missing: list) -> str:
    """'betterleaks timed out, osv-scanner failed'."""
    return ", ".join(f"{name} {WORDS.get(status, status)}" for name, status in missing)


def tripped(found: list, level: str) -> bool:
    """Whether any finding is at `level` or worse."""
    from .findings import SEVERITIES
    return any(SEVERITIES.index(f["severity"]) <= SEVERITIES.index(level) for f in found)


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


def _row_rules():
    """The rules that fold many rows into one finding, with how to take rows out of a report and what a row
    is: a finding's rule id says nothing about which values or packages it holds, so for these the rows the
    baseline did not have are judged again on their own."""
    from . import findings
    return (
        (findings.secrets_found, _secret_place,
         lambda rep: rep.get("secrets") or [],
         lambda rep, rows: {**rep, "secrets": rows}),
        (findings.vulnerable_dependencies, _package,
         lambda rep: (rep.get("dependencies") or {}).get("vulnerable") or [],
         lambda rep, rows: {**rep, "dependencies": {**(rep.get("dependencies") or {}), "vulnerable": rows}}),
    )


def against_baseline(report: dict, found: list, before: dict) -> list:
    """Mark each finding of `found` new or in the baseline `before` (an earlier --json export), and return the
    findings that count toward --fail-on. A finding is in the baseline when the export has one with the same
    key (compare.key: the rule id, and the metric or email for the rules that emit several) at the same
    severity or worse. For secrets and vulnerable dependencies that key says nothing about which values or
    packages the finding holds, so their rows are compared instead - a secret's place by betterleaks'
    fingerprint, a package by name, version, lock file and advisory ids - and the rows the baseline did not
    have are run through the same rule on their own: what that finds is what counts. A value committed again
    in a new place is a new row, and counts."""
    from . import compare
    from .findings import SEVERITIES
    was = {compare.key(f): f["severity"] for f in before.get("findings") or []}
    counted, fresh_ids, row_ids = [], set(), set()
    for rule, identity, rows_of, with_rows in _row_rules():
        row_ids |= {f["rule"]["id"] for f in rule(report)}
        known = {identity(r) for r in rows_of(before)}
        fresh = rule(with_rows(report, [r for r in rows_of(report) if identity(r) not in known]))
        counted += fresh
        fresh_ids |= {f["rule"]["id"] for f in fresh}
    for f in found:
        rid = f["rule"]["id"]
        if rid in row_ids:
            new = rid in fresh_ids
        else:
            old = was.get(compare.key(f))
            new = old is None or SEVERITIES.index(f["severity"]) < SEVERITIES.index(old)
            if new:
                counted.append(f)
        f["baseline"] = "new" if new else "in the baseline"
        if not new:
            f["detail"] = BASELINE_MARK + f["detail"]
    return counted

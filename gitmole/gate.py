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

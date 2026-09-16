"""Knowledge loss: who has stopped committing, and how much of the code is theirs.

"Gone" is measured against the repository's last commit, not today's date, so a clone that was
last fetched a year ago does not mark everyone as gone."""
from __future__ import annotations

from . import identity, knowledge, maat

DEFAULT_MONTHS = 12


def cutoff(report: dict, months: int = DEFAULT_MONTHS):
    last = report["meta"].get("last_date") or ""
    return maat.months_before(last, months) if last else None


def gone(report: dict, months: int = DEFAULT_MONTHS) -> list:
    """People whose last commit is before the cut-off, by name. Bots are never people."""
    cut = cutoff(report, months)
    authors = (report.get("activity") or {}).get("authors") or {}
    if not cut or not authors:
        return []
    bots = {b["name"] for b in report["meta"].get("bots") or []}
    out = [{"name": name, "last": a.get("last", "")} for name, a in authors.items()
           if name not in bots and not identity.is_bot(name) and a.get("last", "") < cut]
    return sorted(out, key=lambda g: g["name"])


def surviving(report: dict, gone_names) -> tuple:
    """(surviving lines written by gone people, all surviving lines); (0, 0) without a blame pass."""
    shares = report.get("theseus_authors") or {}
    return sum(n for name, n in shares.items() if name in gone_names), sum(shares.values())


def areas(rows: list, gone_names) -> list:
    """knowledge.areas over the given ownership rows, each row with `lost` lines and `lost_share`."""
    out = []
    for a in knowledge.areas(rows):
        lost = sum(n for name, n in a["owners"] if name in gone_names)
        out.append({**a, "lost": lost, "lost_share": lost / a["lines"] if a["lines"] else 0.0})
    return out

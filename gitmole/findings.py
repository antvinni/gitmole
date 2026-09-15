"""Heuristics that turn a loaded report into a short list of flagged findings."""
from __future__ import annotations

import re

SEVERITIES = ["critical", "warning", "info"]

PLACEHOLDER_NAMES = {"your name", "unknown", "root", "user"}
PLACEHOLDER_EMAIL = re.compile(r"(@example\.(com|org|net)$|^you@|^user@|^root@|@localhost$)")


def _f(severity: str, title: str, detail: str) -> dict:
    return {"severity": severity, "title": title, "detail": detail}


def _pct(part, whole) -> str:
    return f"{round(100 * part / whole)}%" if whole else "0%"


def secrets_found(report: dict) -> list:
    secrets = report.get("secrets") or []
    if not secrets:
        return []
    sample = ", ".join(f"{s['rule']} in {s['file']} ({s['commit']})" for s in secrets[:3])
    more = f" and {len(secrets) - 3} more" if len(secrets) > 3 else ""
    return [_f("critical", f"{len(secrets)} secret(s) in history", f"{sample}{more}. Rotate them; deleting the file does not remove them from git.")]


def _all_identities(report: dict):
    """Every identity row plus its aliases, flattened."""
    for i in report["meta"].get("identities") or []:
        yield i
        for a in i.get("aliases") or []:
            yield a


def placeholder_identity(report: dict) -> list:
    total = sum(i["commits"] for i in report["meta"].get("identities") or [])
    out = []
    for i in _all_identities(report):
        if i["name"].strip().lower() in PLACEHOLDER_NAMES or PLACEHOLDER_EMAIL.search(i["email"].lower()):
            out.append(_f("warning", "Unconfigured git identity",
                          f"\"{i['name']} <{i['email']}>\" made {i['commits']} commits ({_pct(i['commits'], total)}). Set user.name and user.email; consider a .mailmap for history."))
    return out


def bus_factor(report: dict, threshold: float = 0.7) -> list:
    shares = report.get("theseus_authors") or {}
    total = sum(shares.values())
    if not total:
        return []
    name, lines = max(shares.items(), key=lambda kv: kv[1])
    if lines / total <= threshold:
        return []
    return [_f("warning", "Bus factor of one",
               f"{name} wrote {_pct(lines, total)} of the code that survives today.")]


def sizer_concerns(report: dict) -> list:
    out = []
    for row in report.get("sizer") or []:
        sev = "warning" if row["concern"] >= 2 else "info"
        where = f" at {row['ref']}" if row.get("ref") else ""
        out.append(_f(sev, f"Repo health: {row['name']}", f"{row['value']}{where}. git-sizer level of concern {row['concern']}."))
    return out


def hotspot_dominance(report: dict, ratio: float = 2.0, minimum: int = 20) -> list:
    revs = sorted(report.get("revisions") or [], key=lambda r: -r["n-revs"])
    if len(revs) < 2 or revs[0]["n-revs"] < minimum or revs[0]["n-revs"] < ratio * revs[1]["n-revs"]:
        return []
    top, nxt = revs[0], revs[1]
    return [_f("info", "One file dominates the churn",
               f"{top['entity']} changed {top['n-revs']} times, versus {nxt['n-revs']} for the next file ({nxt['entity']}).")]


def tight_coupling(report: dict, min_degree: int = 80, min_revs: int = 5) -> list:
    pairs = [p for p in report.get("coupling") or [] if p["degree"] >= min_degree and p["average-revs"] >= min_revs]
    if not pairs:
        return []
    pairs.sort(key=lambda p: (-p["degree"], -p["average-revs"]))
    top = "; ".join(f"{p['entity']} + {p['coupled']} ({p['degree']}%)" for p in pairs[:3])
    return [_f("info", "Files that always change together",
               f"{len(pairs)} pairs change together at least {min_degree}% of the time, e.g. {top}. Usually a shared layout or a hidden dependency.")]


def stale_files(report: dict, months: int = 12, share: float = 0.3) -> list:
    age = report.get("age") or []
    if not age:
        return []
    stale = [a for a in age if a["age-months"] >= months]
    if len(stale) / len(age) <= share:
        return []
    return [_f("info", "A large share of files is untouched",
               f"{_pct(len(stale), len(age))} of files ({len(stale)}) have not changed in {months} months or more.")]


def duplicate_identities(report: dict) -> list:
    out = []
    for i in report["meta"].get("identities") or []:
        aliases = i.get("aliases") or []
        if not aliases:
            continue
        names = ", ".join(f"{a['name']} <{a['email']}>" for a in aliases)
        out.append(_f("info", "One person under several identities",
                      f"{names} merged into {i['name']} <{i['email']}> by name and email similarity. Add a .mailmap to make it permanent."))
    return out


RULES = [secrets_found, placeholder_identity, bus_factor, sizer_concerns, hotspot_dominance, tight_coupling, stale_files, duplicate_identities]


def evaluate(report: dict) -> list:
    found = []
    for rule in RULES:
        found.extend(rule(report))
    found.sort(key=lambda f: SEVERITIES.index(f["severity"]))
    return found

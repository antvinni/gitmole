"""Do the findings agree with each other, and with what the run itself collected?

claims.py holds a finding's text to its own numbers. This holds a finding to the rest of the report:
the knowledge map says who is gone, the activity says which commits were left out as sweeping, git
says what is in the tree, betterleaks graded every value. A finding that contradicts one of those is
wrong whatever its own numbers say, and none of it needs a label to see. Ten reviewers reading the
0.38.0 reports of gitmole itself and of apache/devlake found each check below by hand:

- gone_in_advice: the advice names someone the report counts as gone ("Have abeizn review", "Pair
  someone with Adrian Holovaty"). The rules whose subject is the people who left are exempt.
- gone_unmarked: a finding names a gone person as if they were still here (the truck factor's
  "without 青湛, abeizn …", two years after both left) without the "(gone)" the knowledge map uses.
- wrong_area: the advice pairs someone on an area the finding's own evidence gives to someone else
  (react's "Pair someone with Sebastian Markbåge on compiler/", which is Joe Savona's).
- growth_window: a change "in a year" claimed over less than a year of history (gitmole's own
  "+1163% in a year" on ten days).
- secrets_headline: the first value a secrets finding names is graded lower than another value in
  the same finding (devlake's critical led with `password: 'Password'` and never named its GitHub token).
- sarif_gate: a critical or warning finding has no SARIF result, so --fail-on and code scanning
  disagree about the same run.
- tree_claim: a finding says a path is no longer in the tree and git has it at the analysed commit.
- sweeping_evidence: a finding rests on a commit the report says it left out as sweeping (a module
  rename read as a manifest the lock file fell behind).
- trailer_author: a People or Timeline identity that authored no commit, only appears in trailers.

tree_claim and sweeping_evidence need the clone, read at the commit the run recorded and never checked
out; the rest need nothing but the JSON export. A complaint is a defect, not a score - the number to
want is zero.

    python -m gitmole.measure.consistency REPORT.json [--repo CLONE]
    python -m gitmole.measure consistency [--version 0.38.0] [--rerender]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile

from .. import loss, sarif

# the rules whose subject is the people who left: naming them is the point
ABOUT_THE_GONE = frozenset({"knowledge_loss", "authors_gone"})
# evidence keys that hold a person's name, at any depth
PERSON_KEYS = frozenset({"author", "owner", "removed", "removed_decayed", "people", "person", "who"})
CONFIDENCE = {"high": 3, "medium": 2, "low": 1}
GATED = ("critical", "warning")   # what --fail-on can be set to stop on


def _people(evidence, key=None) -> set:
    """Every string held under a person key of the evidence."""
    out = set()
    if isinstance(evidence, dict):
        for k, v in evidence.items():
            out |= _people(v, k)
    elif isinstance(evidence, list):
        for v in evidence:
            out |= _people(v, key)
    elif isinstance(evidence, str) and key in PERSON_KEYS:
        out.add(evidence)
    return out


def _named(text: str, name: str) -> list:
    """The offsets where `name` stands as a name in `text`, not inside a longer word."""
    return [m.end() for m in re.finditer(r"(?<!\w)" + re.escape(name) + r"(?!\w)", text or "")]


def _gone(report: dict) -> set:
    months = (report.get("meta") or {}).get("gone_months", loss.DEFAULT_MONTHS)
    return {g["name"] for g in loss.gone(report, months)}


def _complaint(check: str, f: dict = None, subject: str = "") -> dict:
    return {"check": check, "rule": ((f or {}).get("rule") or {}).get("id", "") if f else "", "subject": subject}


def gone_people(report: dict, found: list) -> list:
    gone = _gone(report)
    out = []
    for f in found:
        rid = (f.get("rule") or {}).get("id")
        if rid in ABOUT_THE_GONE or not gone:
            continue
        for name in sorted(_people(f.get("evidence")) & gone):
            if _named(f.get("advice"), name):
                out.append(_complaint("gone_in_advice", f, name))
            if any(not (f.get("detail") or "")[end:].lstrip().startswith("(gone") for end in _named(f.get("detail"), name)):
                out.append(_complaint("gone_unmarked", f, name))
    return out


def wrong_area(report: dict, found: list) -> list:
    out = []
    for f in found:
        areas = (f.get("evidence") or {}).get("areas")
        m = re.search(r"Pair someone with (.+?) on (\S+)", f.get("advice") or "")
        if not m or not isinstance(areas, list):
            continue
        who, area = m.group(1), m.group(2)
        for a in areas:
            owner = a.get("author") or a.get("owner") if isinstance(a, dict) else None
            if isinstance(a, dict) and a.get("area") == area and owner and owner != who:
                out.append(_complaint("wrong_area", f, f"{who} on {area}, which is {owner}'s"))
    return out


def _history_months(report: dict):
    meta = report.get("meta") or {}
    first, last = meta.get("first_date_all") or meta.get("first_date"), meta.get("last_date")
    if not first or not last:
        return None
    (y0, m0, d0), (y1, m1, d1) = (map(int, first[:10].split("-")), map(int, last[:10].split("-")))
    return (y1 - y0) * 12 + (m1 - m0) - (1 if d1 < d0 else 0)


def growth_window(report: dict, found: list) -> list:
    months = _history_months(report)
    if months is None or months >= 12:
        return []
    out = [_complaint("growth_window", f, f"{months} months of history") for f in found
           if (f.get("rule") or {}).get("id") == "complexity_growth"]
    for row in report.get("watch") or []:   # the watch list's reasons make the same claim, outside any finding
        if any("in a year" in r for r in row.get("reasons") or []):
            out.append(_complaint("growth_window", None, f"watch list: {row.get('file') or row.get('entity')}"))
    return out


def secrets_headline(report: dict, found: list) -> list:
    """The first `<rule> in <file>` a secrets finding names, against every value the scanner found in the
    finding's own files. A lower bound: the evidence names at most ten files."""
    values = [s for s in report.get("secrets") or [] if not s.get("placeholder")]
    out = []
    for f in found:
        rid = (f.get("rule") or {}).get("id") or ""
        if not rid.startswith("secrets"):
            continue
        m = re.search(r": (\S+) in (\S+?)(?: and \d+ other files?)?(?: \(|;|\.$| and \d+ more)", f.get("detail") or "")
        files = set((f.get("evidence") or {}).get("files") or [])
        if not m or not files:
            continue
        head_rule, head_file = m.group(1), m.group(2)
        head = max((CONFIDENCE.get(s.get("confidence"), 0) for s in values if s.get("rule") == head_rule and s.get("file") == head_file), default=0)
        stronger = sorted({s["rule"] for s in values if s.get("file") in files and CONFIDENCE.get(s.get("confidence"), 0) > head})
        if stronger:
            out.append(_complaint("secrets_headline", f, f"leads with {head_rule}; also holds {', '.join(stronger)}"))
    return out


def sarif_gate(report: dict, found: list) -> list:
    if not any(f.get("severity") in GATED for f in found):
        return []
    try:
        results = sarif.build(report, found)["runs"][0]["results"]
    except Exception as e:   # a report SARIF cannot be built from is itself the disagreement
        return [_complaint("sarif_gate", None, f"sarif.build failed: {type(e).__name__}")]
    have = {r.get("ruleId") for r in results}
    return [_complaint("sarif_gate", f, f"{f['severity']} with no SARIF result") for f in found
            if f.get("severity") in GATED and (f.get("rule") or {}).get("id") not in have]


def _git(clone: str, *args) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-c", "core.quotePath=false", *args], cwd=clone, capture_output=True, text=True)


def tree_claim(report: dict, found: list, clone: str, commit: str) -> list:
    out = []
    for f in found:
        ref = (f.get("evidence") or {}).get("ref")
        if ref and "no longer in the tree" in (f.get("detail") or "") and _git(clone, "cat-file", "-e", f"{commit}:{ref}").returncode == 0:
            out.append(_complaint("tree_claim", f, ref))
    return out


def sweeping_evidence(report: dict, found: list, clone: str, commit: str) -> list:
    swept = [s["hash"] for s in (report.get("activity") or {}).get("sweeping") or [] if s.get("hash")]
    out = []
    if not swept:
        return out
    for f in found:
        if (f.get("rule") or {}).get("id") != "lockfile_drift":
            continue
        for d in (f.get("evidence") or {}).get("drift") or []:
            last = _git(clone, "log", "-1", "--format=%H", commit, "--", d.get("manifest", "")).stdout.strip()
            if last and any(last.startswith(h) for h in swept):
                out.append(_complaint("sweeping_evidence", f, f"{d['manifest']} last changed in sweeping {last[:9]}"))
    return out


def trailer_author(report: dict, found: list) -> list:
    """An identity every one of whose commits came from Co-authored-by trailers, shown as an author. A
    row that keeps its authored commits apart (`authored`) is judged by those, so crediting a co-author
    is fine as long as the table does not call the credit authorship."""
    trailers = ((report.get("provenance") or {}).get("trailers") or {}).get("never_author") or []
    aliases = (report.get("meta") or {}).get("aliases") or {}
    authors = (report.get("activity") or {}).get("authors") or {}
    credited = {}
    for t in trailers:
        name = aliases.get(t.get("name"), t.get("name"))
        credited[name] = credited.get(name, 0) + (t.get("commits") or 0)
    shown = {name: a.get("authored", a.get("commits")) or 0 for name, a in authors.items()}
    return [_complaint("trailer_author", None, name) for name, n in sorted(credited.items())
            if name in shown and n >= shown[name] > 0]


FINDING_CHECKS = (gone_people, wrong_area, growth_window, secrets_headline, sarif_gate, trailer_author)
CLONE_CHECKS = (tree_claim, sweeping_evidence)


def over(report: dict, clone: str = None) -> dict:
    """{checked, clean, complaints, clone}: checked and clean count findings; complaints also hold the
    ones about the report's tables (rule "")."""
    found = report.get("findings") or []
    complaints = []
    for check in FINDING_CHECKS:
        complaints += check(report, found)
    commit = (((report.get("meta") or {}).get("run") or {}).get("commit")) if clone else None
    usable = bool(commit) and _git(clone, "cat-file", "-e", f"{commit}^{{commit}}").returncode == 0
    if usable:
        for check in CLONE_CHECKS:
            complaints += check(report, found, clone, commit)
    bad = {c["rule"] for c in complaints if c["rule"]}
    clean = sum(1 for f in found if (f.get("rule") or {}).get("id") not in bad)
    return {"checked": len(found), "clean": clean, "complaints": complaints, "clone": usable}


def by_check(complaints: list) -> dict:
    out = {}
    for c in complaints:
        out[c["check"]] = out.get(c["check"], 0) + 1
    return dict(sorted(out.items()))


SETS = ("development", "large", "awkward", "gate", "well-kept")   # never the holdout: its clones are not read outside a release-tag job


def _clone_of(entry: dict, root: str):
    """Where the round's clone of the entry lives, or None; never clones or builds anything."""
    path = os.path.join(root, "fixtures", entry["fixture"]) if entry.get("fixture") else os.path.join(root, "clones", entry["name"])
    return path if os.path.isdir(path) else None


def _rerendered(out_dir: str, reference: str, tmp: str):
    """This tree's rules over an analysis the round already collected: `gitmole OUT --no-run --json`."""
    from . import corpus, harness
    dest = os.path.join(tmp, "report.json")
    done = subprocess.run([sys.executable, "-m", "gitmole", out_dir, "--no-run", "--json", dest], cwd=corpus.ROOT,
                          env=harness._env(corpus.ROOT, reference), capture_output=True, text=True)
    if done.returncode not in (0, 3) or not os.path.exists(dest):
        return None
    with open(dest, encoding="utf-8") as fh:
        return json.load(fh)


def round_(manifest: dict, root: str, version: str, rerender: bool = False, only=None) -> int:
    """Every saved run of `version`, as recorded or (rerender) as this tree's rules read it now."""
    from . import corpus
    entries = {e["name"]: e for e in corpus.entries(manifest, SETS) if not only or e["name"] in only}
    total, by, rows = {"checked": 0, "clean": 0}, {}, []
    with tempfile.TemporaryDirectory() as tmp:
        for name in sorted(entries):
            work = os.path.join(root, "runs", version, name)
            if rerender:
                data = _rerendered(os.path.join(work, "out"), manifest["reference_date"], tmp) if os.path.isdir(os.path.join(work, "out")) else None
            else:
                try:
                    with open(os.path.join(work, "report.json"), encoding="utf-8") as fh:
                        data = json.load(fh)
                except (OSError, ValueError):
                    data = None
            if not data:
                continue
            one = over(data, _clone_of(entries[name], root))
            total["checked"] += one["checked"]
            total["clean"] += one["clean"]
            for c in one["complaints"]:
                by[c["check"]] = by.get(c["check"], 0) + 1
                rows.append((name, c))
    source = "this tree's rules over the saved analyses" if rerender else "as recorded"
    print(f"{version} ({source}): {sum(by.values())} contradiction(s); {total['clean']} of {total['checked']} findings consistent")
    for k, v in sorted(by.items()):
        print(f"  {k}: {v}")
    for name, c in rows:
        print(f"  {name}/{c['rule'] or '(tables)'}: {c['check']}: {c['subject']}")
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="python -m gitmole.measure.consistency", description=__doc__.split("\n")[0])
    p.add_argument("report", help="a --json export")
    p.add_argument("--repo", help="the clone it was made from, for the checks that read git")
    args = p.parse_args(argv)
    with open(args.report, encoding="utf-8") as fh:
        one = over(json.load(fh), args.repo)
    print(f"{one['clean']} of {one['checked']} findings consistent; {len(one['complaints'])} complaint(s)"
          + ("" if one["clone"] else " (git checks skipped: no clone at the recorded commit)"))
    for c in one["complaints"]:
        print(f"  {c['check']}: {c['rule'] or '(tables)'}: {c['subject']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

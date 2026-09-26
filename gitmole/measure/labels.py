"""Hand labels for findings (docs/measurement.md, "Hand labels").

`dump` writes every finding of the latest recorded release's development, large and well-kept runs to
two files under measure/: labels-sheet.jsonl, one finding per line with an id, the repository, the
commit and the statement, the rule id and severity left out so the labeller cannot see them; and
labels-key.jsonl, which maps the id back to rule and severity. Labellers add lines to measure/labels.jsonl:

    {"id": "...", "labeller": "a", "true": true, "actionable": false}

`score` joins the labels to the key and gives each rule its factual precision with a Wilson interval,
its verdict (sound, broken, undecided, unlabelled against the 0.8 line), its actionable share, and
Cohen's kappa where two labellers labelled the same findings.

Labels carry forward. A finding's id is its rule, repository, pinned commit and evidence, so a finding
that did not change keeps its id and its label from one release to the next. `dump` keeps every key row
it has seen, copies each label to a new id whose repository, rule and statement match a labelled one
(the evidence moved, the claim did not), and writes to the sheet only what is still unlabelled.
`usefulness` gives a release its actionable share: of the findings its default report spells out, the
share labelled actionable, beside how many of them carry a label at all."""
from __future__ import annotations

import hashlib
import json
import os

from . import corpus, dashboard, metrics

DIR = os.path.join(corpus.ROOT, "measure")


def finding_id(rule: str, repo: str, commit: str, evidence) -> str:
    raw = json.dumps([rule, repo, commit, evidence], sort_keys=True, default=str)
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def _read(path: str) -> list:
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as fh:
        return [json.loads(l) for l in fh if l.strip()]


LABELLED_SETS = ("development", "large", "well-kept")


def id_rows(name: str, commit, report_path: str) -> list:
    """One row per finding of a run's --json export: id, rule, severity, whether the default report
    only summarised it, and the statement. [] when the export is missing."""
    try:
        with open(report_path, encoding="utf-8") as fh:
            found = json.load(fh).get("findings") or []
    except (OSError, ValueError, TypeError):
        return []
    rows = []
    for f in found:
        rule = (f.get("rule") or {}).get("id", "")
        rows.append({"id": finding_id(rule, name, commit, f.get("evidence")), "rule": rule, "severity": f.get("severity"),
                     "summary": bool(f.get("summary")), "statement": f.get("detail", "")})
    return rows


def _write(path: str, rows: list) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, sort_keys=True) + "\n")


def dump(records_dir: str) -> tuple:
    """(new findings on the sheet, labels carried forward, the sheet's path) for the latest release."""
    history = dashboard.load_history(records_dir)
    if not history:
        raise SystemExit("labels: no recorded release; run `python -m gitmole.measure run` first")
    latest = history[-1]
    commits = {e["name"]: e.get("commit") for e in corpus.load()["repos"]}
    root = corpus.workspace()
    old_sheet = {r["id"]: r for r in _read(os.path.join(DIR, "labels-sheet.jsonl"))}
    key = {}
    for r in _read(os.path.join(DIR, "labels-key.jsonl")):   # every row ever dumped stays, with its statement
        key[r["id"]] = {**r, "statement": r.get("statement") or (old_sheet.get(r["id"]) or {}).get("statement", "")}
    labels = _read(os.path.join(DIR, "labels.jsonl"))
    labelled = {}
    for lab in labels:
        labelled.setdefault(lab["id"], []).append(lab)
    by_claim = {(r["repo"], r["rule"], r["statement"]): fid for fid, r in key.items() if fid in labelled and r["statement"]}
    sheet, carried = [], []
    for name, rec in sorted(latest["repos"].items()):
        if rec.get("set") not in LABELLED_SETS or rec.get("status") != "ok":
            continue
        for row in id_rows(name, commits.get(name), os.path.join(root, "runs", latest["version"], name, "report.json")):
            fid = row["id"]
            key.setdefault(fid, {"id": fid, "rule": row["rule"], "severity": row["severity"], "repo": name, "version": latest["version"],
                                 "statement": row["statement"]})
            if fid in labelled:
                continue
            source = by_claim.get((name, row["rule"], row["statement"]))
            if source:
                for lab in labelled[source]:
                    copy = {**lab, "id": fid, "carried_from": source}
                    carried.append(copy)
                    labelled.setdefault(fid, []).append(copy)
                continue
            sheet.append({"id": fid, "repo": name, "commit": commits.get(name), "statement": row["statement"]})
    if carried:
        with open(os.path.join(DIR, "labels.jsonl"), "a", encoding="utf-8") as fh:
            for lab in carried:
                fh.write(json.dumps(lab, sort_keys=True) + "\n")
    sheet.sort(key=lambda r: r["id"])   # by hash, so rules and repositories come interleaved
    _write(os.path.join(DIR, "labels-sheet.jsonl"), sheet)
    _write(os.path.join(DIR, "labels-key.jsonl"), sorted(key.values(), key=lambda r: r["id"]))
    return len(sheet), len(carried), os.path.join(DIR, "labels-sheet.jsonl")


def usefulness(record: dict, labels: list = None) -> dict:
    """{actionable_share, labelled_share, shown}: over the labelled sets, the findings the release's default
    report spells out (not summarised), the share of the labelled ones labelled actionable, and the share
    that carry a label at all. Nones for a record from before finding ids were kept."""
    labels = _read(os.path.join(DIR, "labels.jsonl")) if labels is None else labels
    first = {}
    for lab in labels:
        if not lab.get("unsure"):
            first.setdefault(lab["id"], lab)
    shown = [row for rec in record["repos"].values() if rec.get("set") in LABELLED_SETS for row in rec.get("finding_ids") or [] if not row.get("summary")]
    if not shown:
        return {"actionable_share": None, "labelled_share": None, "shown": 0}
    known = [first[row["id"]] for row in shown if row["id"] in first]
    return {"actionable_share": round(sum(bool(l.get("actionable")) for l in known) / len(known), 3) if known else None,
            "labelled_share": round(len(known) / len(shown), 3), "shown": len(shown)}


def score() -> dict:
    key = {r["id"]: r for r in _read(os.path.join(DIR, "labels-key.jsonl"))}
    labels = _read(os.path.join(DIR, "labels.jsonl"))
    by_rule, pairs = {}, {"true": [], "actionable": []}
    by_id = {}
    for lab in labels:
        if lab.get("unsure"):   # a labeller who could not decide adds nothing to either side
            continue
        by_id.setdefault(lab["id"], []).append(lab)
    for fid, labs in by_id.items():
        rule = (key.get(fid) or {}).get("rule", "(unknown)")
        first = labs[0]
        r = by_rule.setdefault(rule, {"n": 0, "true": 0, "actionable": 0})
        r["n"] += 1
        r["true"] += bool(first.get("true"))
        r["actionable"] += bool(first.get("actionable"))
        if len(labs) >= 2:
            pairs["true"].append((bool(labs[0].get("true")), bool(labs[1].get("true"))))
            pairs["actionable"].append((bool(labs[0].get("actionable")), bool(labs[1].get("actionable"))))
    rules = sorted({r["rule"] for r in key.values()})
    out = {"rules": {}, "kappa_true": metrics.kappa(pairs["true"]), "kappa_actionable": metrics.kappa(pairs["actionable"])}
    for rule in rules:
        r = by_rule.get(rule, {"n": 0, "true": 0, "actionable": 0})
        out["rules"][rule] = {"labelled": r["n"], "precision_ci": metrics.wilson(r["true"], r["n"]), "verdict": metrics.verdict(r["true"], r["n"]),
                              "actionable_share": round(r["actionable"] / r["n"], 3) if r["n"] else None}
    counts = {}
    for v in out["rules"].values():
        counts[v["verdict"]] = counts.get(v["verdict"], 0) + 1
    out["verdicts"] = counts
    return out


def main(action: str, records_dir: str) -> int:
    if action == "dump":
        n, carried, path = dump(records_dir)
        print(f"{n} findings to label in {path}; {carried} labels carried forward to findings whose statement did not change")
        return 0
    print(json.dumps(score(), indent=1, sort_keys=True))
    return 0

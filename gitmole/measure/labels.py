"""Hand labels for findings (docs/measurement.md, "Hand labels").

`dump` writes every finding of the latest recorded release's development and well-kept runs to two
files under measure/: labels-sheet.jsonl, one finding per line with an id, the repository, the commit
and the statement, the rule id and severity left out so the labeller cannot see them; and labels-key.jsonl,
which maps the id back to rule and severity. Labellers add lines to measure/labels.jsonl:

    {"id": "...", "labeller": "a", "true": true, "actionable": false}

`score` joins the labels to the key and gives each rule its factual precision with a Wilson interval,
its verdict (sound, broken, undecided, unlabelled against the 0.8 line), its actionable share, and
Cohen's kappa where two labellers labelled the same findings."""
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


def dump(records_dir: str) -> tuple:
    history = dashboard.load_history(records_dir)
    if not history:
        raise SystemExit("labels: no recorded release; run `python -m gitmole.measure run` first")
    latest = history[-1]
    manifest = corpus.load()
    commits = {e["name"]: e.get("commit") for e in manifest["repos"]}
    sheet, key = [], []
    root = corpus.workspace()
    for name, rec in sorted(latest["repos"].items()):
        if rec.get("set") not in ("development", "well-kept") or rec.get("status") != "ok":
            continue
        path = os.path.join(root, "runs", latest["version"], name, "report.json")
        if not os.path.exists(path):
            continue
        with open(path, encoding="utf-8") as fh:
            found = json.load(fh).get("findings") or []
        for f in found:
            rule = (f.get("rule") or {}).get("id", "")
            fid = finding_id(rule, name, commits.get(name), f.get("evidence"))
            sheet.append({"id": fid, "repo": name, "commit": commits.get(name), "statement": f.get("detail", "")})
            key.append({"id": fid, "rule": rule, "severity": f.get("severity"), "repo": name, "version": latest["version"]})
    sheet.sort(key=lambda r: r["id"])   # by hash, so rules and repositories come interleaved
    for fname, rows in (("labels-sheet.jsonl", sheet), ("labels-key.jsonl", key)):
        with open(os.path.join(DIR, fname), "w", encoding="utf-8") as fh:
            for r in rows:
                fh.write(json.dumps(r, sort_keys=True) + "\n")
    return len(sheet), os.path.join(DIR, "labels-sheet.jsonl")


def score() -> dict:
    key = {r["id"]: r for r in _read(os.path.join(DIR, "labels-key.jsonl"))}
    labels = _read(os.path.join(DIR, "labels.jsonl"))
    by_rule, pairs = {}, {"true": [], "actionable": []}
    by_id = {}
    for lab in labels:
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
        n, path = dump(records_dir)
        print(f"{n} findings in {path}")
        return 0
    print(json.dumps(score(), indent=1, sort_keys=True))
    return 0

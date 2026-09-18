"""The findings as SARIF 2.1.0, for GitHub code scanning and GitLab.

`--json` already carries a rule id, thresholds and evidence per finding, which is most of a SARIF
result. What the uploaders need on top: `version "2.1.0"`, `tool.driver` with `rules[]` (id,
shortDescription, help, defaultConfiguration.level), results with `message.text` and a
`physicalLocation` (GitLab drops a result without one), repo-relative POSIX paths (a differing path
closes and reopens the alert), and `properties["security-severity"]` as a 0.1-10.0 string, which is
what GitHub ranks on rather than `level`.

Two gitmole-specific points. Dedup: without a fingerprint the REST upload duplicates alerts, so every
result carries `partialFingerprints["gitmole/v1"]`, a hash of rule, path, commit and line, derived
from non-secret data, so two runs agree although the keyed value hashes in secrets.json never do.
Scope: a secret in an old commit, a sweeping commit, a git-sizer blob no longer in the tree have no
HEAD location; `--sarif-scope head` (the default) keeps only results whose file is in the tree, and
`history` keeps everything, with the commit under `properties.commit`."""
from __future__ import annotations

import hashlib
import json
import re

from . import __version__, leaks

LEVELS = {"critical": "error", "warning": "warning", "info": "note"}
SEVERITY = {"critical": "9.0", "warning": "5.0", "info": "2.0"}
SCHEMA = "https://json.schemastore.org/sarif-2.1.0.json"
HOMEPAGE = "https://github.com/antvinni/gitmole"


def _fingerprint(rule: str, path: str = "", commit: str = "", line="", extra: str = "") -> str:
    parts = [rule, path or "", commit or "", "" if line in (None, "") else str(line)] + ([extra] if extra else [])
    return hashlib.sha256("\0".join(parts).encode("utf-8", "surrogateescape")).hexdigest()


def _location(path: str, line=None) -> dict:
    physical = {"artifactLocation": {"uri": path.replace("\\", "/"), "uriBaseId": "%SRCROOT%"}}
    if line:
        physical["region"] = {"startLine": int(line)}
    return {"physicalLocation": physical}


def _result(rule: str, level: str, severity: str, text: str, path: str = None, line=None, commit: str = None, extra: str = "") -> dict:
    out = {"ruleId": rule, "level": level, "message": {"text": text},
           "partialFingerprints": {"gitmole/v1": _fingerprint(rule, path or "", commit or "", line, extra)},
           "properties": {"security-severity": severity}}
    if path:
        out["locations"] = [_location(path, line)]
    if commit:
        out["properties"]["commit"] = commit
    return out


def _places(f: dict) -> list:
    """[(path, line, commit, extra)] the finding's evidence points at, in the shape each rule writes;
    an empty list for a repository-wide finding."""
    e = f.get("evidence") or {}
    out = []

    def items(key):
        v = e.get(key)
        return v if isinstance(v, list) else []
    for item in items("files"):
        if isinstance(item, str):
            out.append((item, None, None, ""))
        elif isinstance(item, dict) and item.get("file"):
            out.append((item["file"], item.get("start"), None, ""))
    for fn in items("functions"):
        out.append((fn["file"], fn.get("start"), None, fn.get("function", "")))
    for g in items("grown"):
        out.append((g["file"], None, None, ""))
    for p in items("pairs"):
        out.append((p["a"], None, None, p.get("b", "")))
    for c in items("clusters"):
        out.append((c["dir"].rstrip("/") if c["dir"] != "(root files)" else ".", None, None, ""))
    for b in items("largest"):
        if b.get("places"):
            place = b["places"][0]
            out.append((place[0], place[1] if len(place) > 1 else None, None, ""))
    for a in items("islands") or items("areas"):
        area = a.get("area") if isinstance(a, dict) else None
        if area and area != "(root files)":
            out.append((area.rstrip("/"), None, None, ""))
    for path in (e.get("reverted") if isinstance(e.get("reverted"), dict) else {}):
        out.append((path, None, None, ""))
    if isinstance(e.get("file"), str):
        out.append((e["file"], None, None, ""))
    if isinstance(e.get("ref"), str) and e["ref"]:
        out.append((e["ref"], None, None, ""))
    for c in items("commits") or items("sample"):
        if isinstance(c, dict) and c.get("hash"):
            out.append((None, None, c["hash"], ""))
    return out


def _in_tree(report: dict, path: str) -> bool:
    files = (report.get("size") or {}).get("files") or {}
    if not files:
        return True   # nothing to judge by: keep the result rather than drop it
    return path in files or any(p.startswith(path.rstrip("/") + "/") for p in files)


def _secret_results(report: dict, f: dict, scope: str) -> list:
    """One result per distinct (file, commit, line) the scanner reported under this finding's files, from
    the rows themselves, so the line and the commit are the scanner's; placeholders are not secrets."""
    wanted = set((f.get("evidence") or {}).get("files") or [])
    seen, out = set(), []
    for r in report.get("secrets") or []:
        if r.get("placeholder") or r["file"] not in wanted:
            continue
        key = (r["file"], r["commit"], r.get("line"))
        if key in seen:
            continue
        seen.add(key)
        at_head = _in_tree(report, r["file"])
        if scope == "head" and not at_head:
            continue
        line_text = f", line {r['line']} of that commit's version" if r.get("line") else ""
        out.append(_result(f["rule"]["id"], LEVELS[f["severity"]], SEVERITY[f["severity"]],
                           f"{r['rule']} in {r['file']} at commit {r['commit']}{line_text}", r["file"],
                           None if scope == "head" else r.get("line"), r["commit"]))
        out[-1]["partialFingerprints"]["gitmole/v1"] = _fingerprint(f["rule"]["id"], r["file"], r["commit"], r.get("line"))
    return out


def _dependency_results(f: dict) -> list:
    out = []
    for p in (f.get("evidence") or {}).get("packages") or []:
        ref = next((x for x in list(p.get("ids") or []) + list(p.get("aliases") or []) if str(x).startswith(leaks_prefix())), None) \
            or (p["aliases"][0] if p.get("aliases") else (p["ids"][0] if p.get("ids") else ""))
        if p.get("malicious"):
            text, severity = f"{p['name']} {p['version']} in {p['source']}: {ref}, malicious, no fix; remove it", "10.0"
        else:
            score = f" ({p['score']:.1f})" if p.get("score") is not None else ""
            fixed = f"fixed in {p['fixed']}" if p.get("fixed") else "no fix yet"
            text = f"{p['name']} {p['version']} in {p['source']}: {ref}{score}, {fixed}"
            severity = f"{max(0.1, min(10.0, float(p['score']))):.1f}" if p.get("score") is not None else SEVERITY[f["severity"]]
        out.append(_result(f["rule"]["id"], LEVELS[f["severity"]], severity, text, p["source"], None, None, f"{p['name']}@{p['version']}"))
    return out


def leaks_prefix() -> str:
    from . import findings
    return findings.MALICIOUS_PREFIX


def results(report: dict, found: list, scope: str = "head") -> list:
    out = []
    for f in found:
        rule, level, severity = f["rule"]["id"], LEVELS[f["severity"]], SEVERITY[f["severity"]]
        if rule.startswith("secrets_"):
            out += _secret_results(report, f, scope)
            continue
        if rule.startswith("vulnerable_dependencies"):
            out += _dependency_results(f)
            continue
        places = _places(f)
        if not places:
            if scope == "history" or not _repo_wide_needs_tree(f):
                out.append(_result(rule, level, severity, f["detail"]))
            continue
        for path, line, commit, extra in places:
            if path and scope == "head" and not _in_tree(report, path):
                continue
            if not path and scope == "head":
                continue
            out.append(_result(rule, level, severity, f["detail"], path, line, commit, extra))
    return out


def _repo_wide_needs_tree(f: dict) -> bool:
    """A finding with no place to point at (dormant, placeholder identity, stale files) stays in either
    scope: it describes the repository, not history that HEAD no longer has."""
    return False


def _rule(f: dict) -> dict:
    rule = f["rule"]["id"]
    name = "".join(part.capitalize() for part in re.split(r"[^A-Za-z0-9]+", rule) if part)
    return {"id": rule, "name": name, "shortDescription": {"text": f["title"]}, "fullDescription": {"text": f["detail"]},
            "help": {"text": f["advice"], "markdown": f["advice"]}, "defaultConfiguration": {"level": LEVELS[f["severity"]]},
            "properties": {"security-severity": SEVERITY[f["severity"]], "tags": ["gitmole"]}}


def build(report: dict, found: list, scope: str = "head") -> dict:
    """The SARIF document: one run, gitmole as the driver, a rule per distinct finding id, a result
    per place. `scope` is head or history."""
    rules, seen = [], set()
    for f in found:
        if f["rule"]["id"] not in seen:
            seen.add(f["rule"]["id"])
            rules.append(_rule(f))
    manifest = (report.get("meta") or {}).get("run") or {}
    run = {"tool": {"driver": {"name": "gitmole", "version": manifest.get("gitmole") or __version__, "informationUri": HOMEPAGE, "rules": rules}},
           "results": results(report, found, scope),
           "properties": {"scope": scope, "repository": (report.get("meta") or {}).get("name")}}
    if manifest.get("commit"):
        run["versionControlProvenance"] = [{"revisionId": manifest["commit"]}]
    return {"$schema": SCHEMA, "version": "2.1.0", "runs": [run]}


def dumps(report: dict, found: list, scope: str = "head") -> str:
    """The document as text, keys sorted and floats fixed, so the same input is the same bytes."""
    return json.dumps(build(report, found, scope), indent=2, sort_keys=True, ensure_ascii=False) + "\n"

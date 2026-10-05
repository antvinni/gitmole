"""The findings as SARIF 2.1.0, for GitHub code scanning and GitLab, as their SARIF documentation describes.

`--json` already carries a rule id, thresholds and evidence per finding, which is most of a SARIF
result. What the uploaders need on top: `version "2.1.0"`, `tool.driver` with `rules[]` (id,
shortDescription, help, defaultConfiguration.level), results with `message.text` and a
`physicalLocation` (GitLab drops a result without one), repo-relative POSIX paths (a differing path
closes and reopens the alert), and, for the security rules alone (SECURITY), `properties["security-severity"]`
as a 0.1-10.0 string, which is what GitHub ranks on rather than `level` and what makes it file the result as a
security alert.

Two gitmole-specific points. Dedup: without a fingerprint the REST upload duplicates alerts, so every
result carries `partialFingerprints["gitmole/v1"]`, a hash of rule, path, commit and line, derived
from non-secret data, so two runs agree although the keyed value hashes in secrets.json never do.
Scope: a secret in an old commit, a sweeping commit, a file no longer in the tree have no
HEAD location; `--sarif-scope head` (the default) keeps only results whose file is in the tree (for a
secret, whose file at HEAD still holds the value, at the line that does), and
`history` keeps everything, with the commit under `properties.commit`. A finding the head scope would
leave with no result at all keeps one without a location (`properties.inTree` false), so every finding
--fail-on can stop on is in the document.

A critical secret removed from the tree is the one result code scanning most needs, and a location-less
result is one GitHub accepts and does not display (GitLab drops it). So under the head scope each value of
secrets_in_source that HEAD no longer holds anywhere gets one result where it was first committed: the
path as it was, the line of that commit's version, the commit under `properties.commit` and
`properties.inTree` false. SARIF 2.1.0 has no per-result revision (versionControlProvenance is the run's,
HEAD), so the commit rides in the property bag, as it does under the history scope, and the message names
it. GitHub's upload takes a repository-relative uri without checking that the file exists at the analysed
commit, and shows such an alert with its path and message and no source excerpt; its fingerprint is the
history scope's for the same place, so switching scopes does not reopen the alert."""
from __future__ import annotations

import hashlib
import json
import re

from . import __version__, gate, leaks

LEVELS = {"critical": "error", "warning": "warning", "info": "note"}
SEVERITY = {"critical": "9.0", "warning": "5.0", "info": "2.0"}
# The rules whose findings are security findings: a secret or credential, a vulnerable or malicious package,
# code that reads one way and runs another, a supply-chain opening (a movable action tag, an install script, a
# package a public registry can shadow, a committed executable, a submodule fetched with a credential or in the
# clear, a symlink out of the tree, a workflow that runs a fork's code with secrets or pastes an outsider's text into a
# script), an agent told to act without approval. Only these carry
# `security-severity`: GitHub files a result with that property as a security alert and ranks it by the number,
# so a bug magnet at 5.0 read as a Medium vulnerability. The rest go without it, which GitHub files as code
# quality, and their rule's tags say "maintainability" where these say "security".
SECURITY = frozenset({"secrets_in_source", "secrets_possible", "secrets_declared", "secrets_local", "credential_files", "mcp_literal_env",
                      "vulnerable_dependencies", "vulnerable_dependencies_aside", "trojan_source", "unpinned_actions",
                      "agent_approval_disabled", "submodule_urls", "install_scripts", "dependency_confusion", "committed_binaries",
                      "unsafe_symlinks", "pwn_request", "expression_injection"})


def _severity(rule: str, severity: str):
    """The security-severity a result of this rule carries, or None for a rule that is not about security."""
    return SEVERITY[severity] if rule in SECURITY else None
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
           "properties": {} if severity is None else {"security-severity": severity}}
    if path:
        out["locations"] = [_location(path, line)]
    if commit:
        out["properties"]["commit"] = commit
    return out


def _places(f: dict) -> list:
    """[(path, line, commit, extra)] the finding's evidence points at, in the shape each rule writes;
    an empty list for a repository-wide finding."""
    return [p[:4] for p in _placed(f)]


def _placed(f: dict) -> list:
    """_places with what each place is: [(path, line, commit, extra, item)], item the evidence row behind the place
    (None for a bare path or commit), which the place's own message (PLACE_TEXT) is written from."""
    e = f.get("evidence") or {}
    out = []

    def items(key):
        v = e.get(key)
        return v if isinstance(v, list) else []
    for item in items("files"):
        if isinstance(item, str):
            out.append((item, None, None, "", None))
        elif isinstance(item, dict) and item.get("file"):
            out.append((item["file"], item.get("start"), None, "", item))
    for fn in items("functions"):
        out.append((fn["file"], fn.get("start"), None, fn.get("function", ""), fn))
    for g in items("grown"):
        out.append((g["file"], None, None, "", g))
    for p in items("pairs"):
        out.append((p["a"], None, None, p.get("b", ""), p))
    for c in items("clusters"):
        out.append((c["dir"].rstrip("/") if c["dir"] != "(root files)" else ".", None, None, "", c))
    for a in items("islands") or items("areas"):
        area = a.get("area") if isinstance(a, dict) else None
        if area and area != "(root files)":
            out.append((area.rstrip("/"), None, None, "", a))
    # a Trojan Source character or token, at its line; the extra is its identity (findings.trojan_identities), which
    # the gate compares and the fingerprint keys on in place of the line (UNLINED)
    if items("bidi") or items("mixed_script"):
        from .findings import trojan_identities
        for ident, r in trojan_identities({"bidi": items("bidi"), "mixed_script": items("mixed_script")}):
            if isinstance(r.get("file"), str):
                out.append((r["file"], r.get("line"), None, "\0".join(str(x) for x in ident), r))
    # a file the finding is about as a whole: lockfile_drift's manifests, and unpinned_actions' workflow files when
    # the report has no rows behind the finding (_action_results). Line 1, since code scanning shows a result by
    # its region and the rule records no line; one result per file
    named = [(u.get("file"), u) for u in items("unpinned") if isinstance(u, dict)] + \
        [(d.get("manifest"), d) for d in items("drift") if isinstance(d, dict)]
    seen = set()
    for path, item in named:
        if isinstance(path, str) and path and path not in seen:
            seen.add(path)
            out.append((path, 1, None, "", item))
    if isinstance(e.get("file"), str):
        out.append((e["file"], None, None, "", None))
    if isinstance(e.get("ref"), str) and e["ref"]:
        out.append((e["ref"], None, None, "", None))
    for c in items("commits") or items("sample"):
        if isinstance(c, dict) and c.get("hash"):
            out.append((None, None, c["hash"], "", None))
    return out


# The rules whose results are not known by their line: a Trojan Source token is the same token after an edit above it
# moved it, so its fingerprint is its identity (the place's extra) and the line is only the region. The gate's
# --baseline compares the same identity, so a baselined token that moved stays one alert, unchanged.
UNLINED = frozenset({"trojan_source"})


def _magnet_text(report: dict, f: dict, m: dict) -> str:
    above = {x.get("file") for x in ((f.get("evidence") or {}).get("fix_rate") or {}).get("above_rate") or []}
    rate = ", more often than files of its size explain" if m["file"] in above else ""
    whole = f" ({m['fixes']} in all)" if m.get("fixes") is not None else ""
    return f"{m['file']} was fixed {m['recent_fixes']} times in six months{whole}{rate}. Review it before the next release."


def _truck_text(report: dict, f: dict, a: dict) -> str:
    from .findings import _gone, _who
    gone = _gone(report) if isinstance(report.get("meta"), dict) else set()
    left = a.get("author") in gone
    return (f"{a['area']} has a truck factor of one ({_who(a.get('author'), gone)}): {a.get('orphaned')} of its "
            f"{a.get('files')} source files {'already have' if left else 'would have'} no author left without them. "
            + ("Give it an owner." if left else f"Pair someone with {a.get('author')} on it."))


def _brain_text(report: dict, f: dict, fn: dict) -> str:
    from .findings import _called
    return (f"{_called(fn)} at {fn['file']}:{fn.get('start')} is long and complex: complexity {fn.get('ccn')}, {fn.get('lines')} lines, "
            f"{fn.get('params')} param{'s' if fn.get('params') != 1 else ''}. Split it before the next change lands there.")


def _deep_text(report: dict, f: dict, fn: dict) -> str:
    from .findings import _called
    return (f"{_called(fn)} at {fn['file']}:{fn.get('start')} nests {fn.get('nesting')} deep, cognitive complexity {fn.get('cognitive')}, "
            f"{fn.get('bumps')} bump{'s' if fn.get('bumps') != 1 else ''}. Flatten it: return early and move each nested chunk into a function of its own.")


def _drift_text(report: dict, f: dict, d: dict) -> str:
    return (f"{d['manifest']} changed on {d.get('manifest_date')}, after {d.get('lockfile')} last did on {d.get('lockfile_date')}. "
            f"Regenerate {d.get('lockfile')} and commit it with the manifest; a frozen install does not catch this.")


def _trojan_text(report: dict, f: dict, r: dict) -> str:
    from . import textfmt
    what = (f"{r['file']}:{r.get('line')} holds {r['char']}, a bidirectional control character" if r.get("char") else
            f"{r.get('token')} at {r['file']}:{r.get('line')} mixes {textfmt.join_and(r.get('scripts') or [])}")
    return (f"{what}: code can read one way in review and compile another. Look at it in a hex view, and remove the "
            "character unless it is in a string that must hold it.")


# a result's own message, from the evidence row behind its place: the finding's detail is the whole rule's summary,
# and ten results each carrying it said nothing about their own subject. The fingerprint does not read the message.
PLACE_TEXT = {"bug_magnets": _magnet_text, "truck_factor": _truck_text, "brain_methods": _brain_text, "deep_nesting": _deep_text,
              "lockfile_drift": _drift_text, "trojan_source": _trojan_text}


def _place_text(report: dict, f: dict, item) -> str:
    text = PLACE_TEXT.get(f["rule"]["id"])
    if text is None or not isinstance(item, dict):
        return f["detail"]
    try:
        return text(report, f, item)
    except (KeyError, TypeError):   # an evidence row of an older shape: the finding's own text, as before
        return f["detail"]


# the most places a lock file drift result list takes from the hygiene step's rows (it keeps that many); the finding's
# evidence keeps ten
DRIFT_PLACES = 50


def _evidence_rows(report: dict, f: dict) -> dict:
    """The finding with every row the report holds behind it in place of the ten its evidence keeps, for the rules
    whose results are one per row: lock file drift (from the hygiene rows, sweeps left out as the finding does) and
    Trojan Source. A report without those rows (a hand-built finding) keeps the evidence."""
    from . import findings
    rule = f["rule"]["id"]
    if rule == "lockfile_drift":
        rows = findings.drift_rows(report)
        return {**f, "evidence": {**(f.get("evidence") or {}), "drift": rows[:DRIFT_PLACES]}} if rows else f
    if rule == "trojan_source":
        tj = (report.get("hygiene") or {}).get("trojan") or {}
        if tj.get("bidi") or tj.get("mixed_script"):
            return {**f, "evidence": {**(f.get("evidence") or {}), "bidi": tj.get("bidi") or [], "mixed_script": tj.get("mixed_script") or []}}
    return f


def _in_tree(report: dict, path: str) -> bool:
    # a credential file (.env) is tracked, from git's own index; scc never lists it, so with no tree listing to
    # read (an older output directory) it would drop prometheus's credential_files warning from head scope
    if path in ((report.get("meta") or {}).get("credential_files") or []):
        return True
    from .findings import at_head
    return at_head(report, path) is not False   # nothing to judge by: keep the result rather than drop it


def _secret_results(report: dict, f: dict, scope: str) -> list:
    """One result per distinct (file, commit, line) the scanner reported for a value this finding holds, from
    the rows themselves, so the line and the commit are the scanner's; placeholders are not secrets. Each
    value is one finding's (findings.secret_groups): a file often holds values of several, and taking every
    row of the finding's evidence files put hindsight's documentation-only placeholder phrase under the
    critical. Under the head scope a critical value HEAD no longer holds is placed where it was first
    committed (see the module's docstring)."""
    from .findings import secret_groups
    groups = secret_groups(report).get(f["rule"]["id"]) or []
    values = {g["value"] for g in groups if g.get("value")}
    loose = {(p, c) for g in groups if not g.get("value") for p in g["files"] for c in g["commits"]}   # a row with no value is its own group

    def held(r):
        return r.get("value") in values if r.get("value") else (r["file"], r["commit"]) in loose

    def at_head(r):   # the value itself decides, where the scan recorded it: a file still in the tree need not hold it any more
        return r["at_head"] if isinstance(r.get("at_head"), bool) else _in_tree(report, r["file"])
    rows = [r for r in report.get("secrets") or [] if not r.get("placeholder") and held(r)]
    first = {}
    if scope == "head" and f["severity"] == "critical":
        now = {r.get("value") for r in rows if r.get("value") and at_head(r)}
        for r in sorted(rows, key=lambda r: (r.get("date") or "~", r["file"], r["commit"], r.get("line") or 0)):
            if r.get("value") and r["value"] not in now and r["value"] not in first and not r["file"].startswith(leaks.UNREACHABLE):
                first[r["value"]] = r
    placed = {id(r) for r in first.values()}
    seen, out = set(), []
    for r in rows:
        key = (r["file"], r["commit"], r.get("line"))
        if key in seen:
            continue
        if scope == "head" and id(r) in placed:
            seen.add(key)
            out.append(_removed_result(f, r))
            continue
        if scope == "head" and not at_head(r):
            continue
        seen.add(key)
        line_text = f", line {r['line']} of that commit's version" if r.get("line") else ""
        head_text = f"; at HEAD, line {r['head_line']}" if scope == "head" and r.get("head_line") else ""
        out.append(_result(f["rule"]["id"], LEVELS[f["severity"]], _severity(f["rule"]["id"], f["severity"]),
                           f"{r['rule']} in {r['file']} at commit {r['commit']}{line_text}{head_text}", r["file"],
                           r.get("head_line") if scope == "head" else r.get("line"), r["commit"]))
        out[-1]["partialFingerprints"]["gitmole/v1"] = _fingerprint(f["rule"]["id"], r["file"], r["commit"], r.get("line"))
    return out


def _removed_result(f: dict, r: dict) -> dict:
    """A critical value HEAD no longer holds, where it was first committed: the path and line as they were."""
    line_text = f", line {r['line']} of that commit's version" if r.get("line") else ""
    out = _result(f["rule"]["id"], LEVELS[f["severity"]], _severity(f["rule"]["id"], f["severity"]),
                  f"{r['rule']} in {r['file']} at commit {r['commit']}{line_text}; no longer in the tree at HEAD, still in history: "
                  "rotate it", r["file"], r.get("line"), r["commit"])
    out["partialFingerprints"]["gitmole/v1"] = _fingerprint(f["rule"]["id"], r["file"], r["commit"], r.get("line"))
    out["properties"]["inTree"] = False
    return out


def _dependency_results(report: dict, f: dict) -> list:
    """One result per vulnerable row the finding holds, located at the file that pins it: every row from the
    report, not the ten the finding's evidence keeps (hindsight's SARIF carried 10 of 34). A finding with no
    rows in the report behind it (a hand-built one) falls back to its evidence."""
    from . import findings
    rows = next((group for rid, _, _, group in findings._vuln_rows(report) if rid == f["rule"]["id"]), None)
    if rows is None:
        ev = f.get("evidence") or {}
        rows = list(ev.get("packages") or []) + [{**r, "version": r.get("floor")} for r in ev.get("requirements") or []]
    out = []
    for p in rows:
        ref = next((x for x in list(p.get("ids") or []) + list(p.get("aliases") or []) if str(x).startswith(leaks_prefix())), None) \
            or (p["aliases"][0] if p.get("aliases") else (p["ids"][0] if p.get("ids") else ""))
        if p.get("malicious"):
            text, severity = f"{p['name']} {p['version']} in {p['source']}: {ref}, malicious, no fix; remove it", "10.0"
        else:
            score = f" ({p['score']:.1f})" if p.get("score") is not None else ""
            fixed = f"fixed in {p['fixed']}" if p.get("fixed") else "no fix yet"
            text = f"{p['name']} {p['version']} in {p['source']}: {ref}{score}, {fixed}"
            if findings._floating(p):
                text = (f"{p['name']}{p['requirement'] or ' (any version)'} in {p['source']} admits a vulnerable version, its floor {p['version']}: {ref}{score}, {fixed}"
                        if p.get("requirement") is not None else f"{p['name']} {p['version']} in {p['source']}, perhaps only the floor a requirement admits: {ref}{score}, {fixed}")
            severity = f"{max(0.1, min(10.0, float(p['score']))):.1f}" if p.get("score") is not None else _severity(f["rule"]["id"], f["severity"])
        out.append(_result(f["rule"]["id"], LEVELS[f["severity"]], severity, text, p["source"], None, None, f"{p['name']}@{p['version']}"))
    return out


def _action_results(report: dict, f: dict, scope: str) -> list:
    """One result per unpinned `uses:` the hygiene step recorded, at its line: every row, not the ten the
    finding's evidence keeps (paperclip's SARIF covered 2 of its 7 workflow files, both at line 1). A row from
    an output directory older than the recorded line is placed at line 1 of its workflow. A finding with no
    rows in the report behind it (a hand-built one) falls back to its evidence's files."""
    rows = ((report.get("hygiene") or {}).get("actions") or {}).get("unpinned")
    if not rows:
        return []
    rule, level, severity = f["rule"]["id"], LEVELS[f["severity"]], _severity(f["rule"]["id"], f["severity"])
    out, seen = [], set()
    for r in rows:
        line = r.get("line") or 1
        if (r["file"], line, r["uses"]) in seen or (scope == "head" and not _in_tree(report, r["file"])):
            continue
        seen.add((r["file"], line, r["uses"]))
        text = (f"{r['uses']} in {r['file']}" + (f", line {r['line']}" if r.get("line") else "") +
                ": an action used by tag or branch, which whoever controls the action can move to other code. "
                "Pin it to a full commit SHA, with the tag in a comment.")
        out.append(_result(rule, level, severity, text, r["file"], line, None, r["uses"]))
    return out


def leaks_prefix() -> str:
    from . import findings
    return findings.MALICIOUS_PREFIX


def results(report: dict, found: list, scope: str = "head") -> list:
    out = []
    for f in found:
        mine = _finding_results(report, f, scope) or [_elsewhere(f)]
        if f.get("baseline"):   # --baseline: SARIF's own word for a result an earlier run already had
            for r in mine:
                r["baselineState"] = "unchanged" if f["baseline"] == "in the baseline" else "new"
        out += mine
    return out


def _finding_results(report: dict, f: dict, scope: str) -> list:
    rule, level, severity = f["rule"]["id"], LEVELS[f["severity"]], _severity(f["rule"]["id"], f["severity"])
    if rule.startswith("secrets_"):
        return _secret_results(report, f, scope)
    if rule.startswith("vulnerable_dependencies"):
        return _dependency_results(report, f)
    if rule == "unpinned_actions" and ((report.get("hygiene") or {}).get("actions") or {}).get("unpinned"):
        return _action_results(report, f, scope)
    places = _placed(_evidence_rows(report, f))
    if not places:
        return [_result(rule, level, severity, f["detail"])] if scope == "history" or not _repo_wide_needs_tree(f) else []
    out = []
    for path, line, commit, extra, item in places:
        if path and scope == "head" and not _in_tree(report, path):
            continue
        if not path and scope == "head":
            continue
        out.append(_result(rule, level, severity, _place_text(report, f, item), path, line, commit, extra))
        if rule in UNLINED:
            out[-1]["partialFingerprints"]["gitmole/v1"] = _fingerprint(rule, path or "", commit or "", None, extra)
    return out


def _elsewhere(f: dict) -> dict:
    """The one result of a finding whose every place the head scope dropped: a secret only in files deleted
    years ago, a blob no longer in the tree. --fail-on stops on the finding all the same, so leaving it out
    made the exit code and the document disagree - devlake exited 3 on a critical with no error-level result.
    It has no location, as nothing at HEAD is where it is: SARIF allows that, GitHub code scanning accepts
    the upload and does not display the result, GitLab drops it; --sarif-scope history places it."""
    from .compare import key
    out = _result(f["rule"]["id"], LEVELS[f["severity"]], _severity(f["rule"]["id"], f["severity"]),
                  f"{f['detail']} Nothing it names is in the tree at HEAD; --sarif-scope history lists where it was found.",
                  extra="\0".join(str(k) for k in key(f)[1:]))
    out["properties"]["inTree"] = False
    return out


def _repo_wide_needs_tree(f: dict) -> bool:
    """A finding with no place to point at (dormant, placeholder identity) stays in either
    scope: it describes the repository, not history that HEAD no longer has."""
    return False


def _about(f: dict) -> str:
    """What the rule is, from the rule dict alone. A SARIF reportingDescriptor describes the rule, and a
    consumer shows it as the rule's documentation, so one run's numbers, paths and commits do not belong
    in it: the occurrence text is `result.message`, which already carries the statement and the advice.
    Under `--sarif-scope head` the finding's text also put back what the scope had just left out - curl's
    secrets_aside rule named docs/MANUAL and five commit hashes in a document where every one of its
    results had been dropped for not being in the tree."""
    rule = f["rule"]
    settings = ", ".join(f"{k} {v}" for k, v in sorted(rule.items()) if k not in ("id", "ref", "osps"))
    parts = [f"gitmole's {rule['id']} rule."]
    if settings:
        parts.append(f"Settings: {settings}.")
    if rule.get("ref"):
        parts.append(f"Rests on {rule['ref']}.")
    if rule.get("osps"):
        parts.append("Evidence for " + ", ".join(rule["osps"]) + ".")
    parts.append(HOMEPAGE)
    return " ".join(parts)


def _rule(f: dict) -> dict:
    rule = f["rule"]["id"]
    name = "".join(part.capitalize() for part in re.split(r"[^A-Za-z0-9]+", rule) if part)
    about = _about(f)
    return {"id": rule, "name": name, "shortDescription": {"text": f["title"]}, "fullDescription": {"text": about},
            "help": {"text": about, "markdown": about}, "defaultConfiguration": {"level": LEVELS[f["severity"]]},
            "properties": {**({"security-severity": SEVERITY[f["severity"]]} if rule in SECURITY else {}),
                           "tags": ["gitmole", "security" if rule in SECURITY else "maintainability", *f["rule"].get("osps", [])]}}


def build(report: dict, found: list, scope: str = "head") -> dict:
    """The SARIF document: one run, gitmole as the driver, a rule per distinct finding id, a result
    per place. `scope` is head or history."""
    found_results = results(report, found, scope)
    # only the rules this document has a result for: a rule whose every result the scope dropped is not
    # part of the document, and declaring it was how curl's head-scoped SARIF still carried secrets_aside
    reported = {r["ruleId"] for r in found_results}
    rules, seen = [], set()
    for f in found:
        rule = f["rule"]["id"]
        if rule in reported and rule not in seen:
            seen.add(rule)
            rules.append(_rule(f))
    manifest = (report.get("meta") or {}).get("run") or {}
    run = {"tool": {"driver": {"name": "gitmole", "version": manifest.get("gitmole") or __version__, "informationUri": HOMEPAGE, "rules": rules}},
           "results": found_results,
           "properties": {"scope": scope, "repository": (report.get("meta") or {}).get("name")}}
    run["invocations"] = [_invocation(report)]
    if manifest.get("commit"):
        run["versionControlProvenance"] = [{"revisionId": manifest["commit"]}]
    return {"$schema": SCHEMA, "version": "2.1.0", "runs": [run]}


def _invocation(report: dict) -> dict:
    """Whether the run behind these results completed: a step a rule reads that failed or timed out means
    the document is missing whatever that step would have found, so the invocation is not successful and
    one notification per step names it. A consumer reading `results` alone would take an empty list from a
    killed secrets scan for a clean one. A dependency scan with no vulnerability database completed, and
    checked nothing: that is a warning notification, the run still successful."""
    missing = gate.unfinished(report)
    out = {"executionSuccessful": not missing}
    notes = [{"level": "error", "descriptor": {"id": name},
              "message": {"text": f"step {gate.describe([(name, status)])}: the results are missing whatever it would have found"}}
             for name, status in missing]
    if gate.no_database(report):   # the step ran and checked nothing: an empty vulnerable list is not a clean one
        notes.append({"level": "warning", "descriptor": {"id": "no-vulnerability-database"},
                      "message": {"text": f"{gate.NO_DATABASE_NOTE}: osv-scanner found no offline database, so no package was "
                                          "matched against an advisory"}})
    if notes:
        out["toolExecutionNotifications"] = notes
    return out


def dumps(report: dict, found: list, scope: str = "head") -> str:
    """The document as text, keys sorted and floats fixed, so the same input is the same bytes."""
    return json.dumps(build(report, found, scope), indent=2, sort_keys=True, ensure_ascii=False) + "\n"

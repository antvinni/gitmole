"""The OSPS Baseline controls gitmole's rules give evidence for, and the coverage table.

The OpenSSF Open Source Project Security Baseline is a catalogue of controls with ids
(ossf/security-baseline, `baseline/OSPS-*.yaml`). Most of its access-control (AC) and
vulnerability-management (VM) controls are about the forge's settings or the project's documents, which
a clone does not show; the ones below can be read from the clone. Each rule that bears on one carries
its id in the rule dict's `osps`, and the coverage table gives each control a result in this repository:
met, gap, not seen, unrecognised, not applicable, or not checked (the step that reads it did not run).
A result is evidence for the control, not an audit of it."""
from __future__ import annotations

BASELINE = "OSPS Baseline, ossf/security-baseline at 17e09dd (8 September 2026, draft)"

# control id -> (what it asks, in short; the rules that give evidence for it)
CONTROLS = {
    "OSPS-BR-07.01": ("No unencrypted secrets or credentials in version control", ("secrets_in_source", "credential_files")),
    "OSPS-GV-03.01": ("The documentation explains the contribution process", ()),
    "OSPS-LE-01.01": ("Every commit asserts the contributor's right to make it", ()),
    "OSPS-LE-02.01": ("The source licence meets the OSI or FSF definition", ("project_licence",)),
    "OSPS-LE-03.01": ("The licence is in a LICENSE or COPYING file or a LICENSES directory", ("repo_policy",)),
    "OSPS-QA-02.01": ("A dependency list accounts for the direct dependencies", ("lockfile_missing", "lockfile_drift")),
    "OSPS-QA-05.01": ("No generated executable artifacts in version control", ("committed_binaries",)),
    "OSPS-QA-05.02": ("No unreviewable binary artifacts in version control", ("committed_binaries",)),
    "OSPS-VM-02.01": ("The documentation contains security contacts", ("repo_policy",)),
    "OSPS-VM-05.03": ("Changes are checked against known-vulnerable and malicious dependencies", ("vulnerable_dependencies",)),
}

RULE_CONTROLS = {}
for _control, (_, _rules) in CONTROLS.items():
    for _rule in _rules:
        RULE_CONTROLS.setdefault(_rule, []).append(_control)

SIGNOFF_SHARE = 0.9   # commits with a Signed-off-by trailer for OSPS-LE-01.01 to count as met


def _row(control: str, result: str, evidence: str) -> dict:
    return {"control": control, "requirement": CONTROLS[control][0], "rules": list(CONTROLS[control][1]), "result": result, "evidence": evidence}


def _fired(found: list, control: str) -> list:
    return [f for f in found if control in (f.get("rule") or {}).get("osps", [])]


def coverage(report: dict, found: list) -> list:
    """One row per control in CONTROLS: its result here and the fact it rests on."""
    h = report.get("hygiene") or {}
    presence = h.get("presence") or {}
    rows = []

    fired = _fired(found, "OSPS-BR-07.01")
    rows.append(_row("OSPS-BR-07.01", "gap" if fired else "met" if report.get("secrets_scanned") else "not checked",
                     "; ".join(f["title"] for f in fired) if fired else "the secrets scan over every branch found none" if report.get("secrets_scanned") else "the secrets step did not run"))

    for control, key, what in (("OSPS-GV-03.01", "contributing", "a contribution guide"), ("OSPS-VM-02.01", "security_policy", "a security policy"),
                               ("OSPS-LE-03.01", "license", "a licence file")):
        if not presence:
            rows.append(_row(control, "not checked", "the hygiene step did not run"))
        else:
            rows.append(_row(control, "met" if presence.get(key) else "gap", presence.get(key) or f"no {what} at the root, in .github/ or in docs/"))

    trailers = (report.get("provenance") or {}).get("trailers") or {}
    if trailers.get("commits"):
        signed = sum(n for k, n in (trailers.get("keys") or {}).items() if k.lower() == "signed-off-by")
        share = signed / trailers["commits"]
        rows.append(_row("OSPS-LE-01.01", "met" if share >= SIGNOFF_SHARE else "not seen",
                         f"{share:.0%} of {trailers['commits']:,} commits carry Signed-off-by" + ("" if share >= SIGNOFF_SHARE else "; a contributor agreement outside git would not show here")))
    else:
        rows.append(_row("OSPS-LE-01.01", "not checked", "the provenance step did not run"))

    lic = h.get("licences")
    if not isinstance(lic, dict):
        rows.append(_row("OSPS-LE-02.01", "not checked", "the hygiene step did not run"))
    else:
        named = sorted({*(i for d in lic.get("declared") or [] for i in [d["expression"]]), *([lic["file_licence"]] if lic.get("file_licence") else [])})
        if lic.get("approved") is True:
            rows.append(_row("OSPS-LE-02.01", "met", ", ".join(named)))
        elif lic.get("approved") is False:
            rows.append(_row("OSPS-LE-02.01", "gap", ", ".join(named) + " is not OSI- or FSF-approved"))
        elif named or lic.get("files"):
            rows.append(_row("OSPS-LE-02.01", "unrecognised", ", ".join(named) if named else f"{', '.join(lic['files'])} matches no licence text gitmole knows"))
        else:
            rows.append(_row("OSPS-LE-02.01", "gap", "no licence declared or in a licence file"))

    lf = h.get("lockfiles")
    fired = _fired(found, "OSPS-QA-02.01")
    if not isinstance(lf, dict):
        rows.append(_row("OSPS-QA-02.01", "not checked", "the hygiene step did not run"))
    elif fired:
        rows.append(_row("OSPS-QA-02.01", "gap", "; ".join(f["title"] for f in fired)))
    elif lf.get("pairs"):
        rows.append(_row("OSPS-QA-02.01", "met", f"{lf['pairs']} manifest{'s' if lf['pairs'] != 1 else ''} with a lock file at least as new"))
    else:
        rows.append(_row("OSPS-QA-02.01", "not applicable", "no manifest of an ecosystem that locks"))

    b = h.get("binaries")
    fired = _fired(found, "OSPS-QA-05.01")
    for control in ("OSPS-QA-05.01", "OSPS-QA-05.02"):
        if not isinstance(b, dict):
            rows.append(_row(control, "not checked", "the hygiene step did not run"))
        else:
            rows.append(_row(control, "gap" if fired else "met", fired[0]["detail"].split(". ")[0] if fired else "no executable committed outside tests, examples and vendored code"))

    deps = report.get("dependencies") or {}
    fired = [f for f in _fired(found, "OSPS-VM-05.03")]
    if fired:
        rows.append(_row("OSPS-VM-05.03", "gap", fired[0]["detail"].split(": ")[0] + " pinned in the tree"))
    elif deps.get("status") == "scanned":
        rows.append(_row("OSPS-VM-05.03", "met", f"no known-vulnerable package among {deps.get('packages', 0):,} locked"))
    elif deps.get("status") == "no-sources":
        rows.append(_row("OSPS-VM-05.03", "not applicable", "no lock file"))
    else:
        rows.append(_row("OSPS-VM-05.03", "not checked", "the offline vulnerability scan did not run"))
    rows.sort(key=lambda r: r["control"])
    return rows

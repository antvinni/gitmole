"""Heuristics that turn a loaded report into a short list of flagged findings. A rule that rests on a paper
carries the short citation in its rule dict's `ref` (see REFS); docs/references.md has the full entries."""
from __future__ import annotations

import bisect
import math
import os
import re

from . import classify, coupling, deps, filetypes, hotspots, hygiene, knowledge, leaks, licences, loss, maat, osps, scope, structure, textfmt, trend

SEVERITIES = ["critical", "warning", "info"]

PLACEHOLDER_NAMES = {"your name", "unknown", "root", "user"}
PLACEHOLDER_EMAIL = re.compile(r"(@example\.(com|org|net)$|^you@|^user@|^root@|@localhost$)")


# The paper a rule rests on, as the short citation the rule dict carries in `ref`; the full entries are in
# docs/references.md. A rule that is gitmole's own heuristic has none.
REFS = {"tangled_commits": "Herzig and Zeller, MSR 2013",
        "brain_methods": "Lanza and Marinescu, 2006", "tight_coupling": "Gall, Hajek and Jazayeri, ICSM 1998",
        "trojan_source": "Boucher and Anderson, USENIX Security 2023",
        "debt_in_hotspots": "Maldonado and Shihab, MTD 2015", "hidden_coupling": "Ajienka and Capiluppi, JSS 2017",
        "unreferenced_files": "Romano et al., TSE 2020", "signoff_by_co_author": "Linux kernel, Documentation/process/coding-assistants.rst",
        "deep_nesting": "SonarSource cognitive complexity; CodeScene code health",
        "sweeping_commits": "Kolassa, Riehle and Salim, SOFSEM 2013", "import_cycles": "Oyetoyan et al., SANER 2015",
        "pwn_request": "GitHub Security Lab, Preventing pwn requests, 2021",
        "expression_injection": "GitHub, Script injections (Actions security docs)",
        "secrets_in_source": "Meli, McNiece and Reaves, NDSS 2019; Basak et al., ESEM 2023"}


def _f(severity: str, title: str, statement: str, advice: str, rule: dict, evidence: dict) -> dict:
    """A finding: the facts, then the next step. `detail` is the two joined for anyone reading the
    JSON; `advice` says which part is the step so the report can show it on its own line. `rule` is
    the rule's id and the thresholds it fired on, `evidence` the numbers they were compared with:
    between them a reader of the JSON can check the finding without reading this file."""
    if rule.get("id") in REFS and "ref" not in rule:
        rule = {**rule, "ref": REFS[rule["id"]]}
    if rule.get("id") in osps.RULE_CONTROLS and "osps" not in rule:   # the OSPS Baseline controls it gives evidence for
        rule = {**rule, "osps": list(osps.RULE_CONTROLS[rule["id"]])}
    return {"severity": severity, "title": title, "detail": f"{statement.rstrip()} {advice}", "advice": advice,
            "rule": rule, "evidence": evidence}


def _pct(part, whole) -> str:
    return f"{round(100 * part / whole)}%" if whole else "0%"


_SIBILANT = re.compile(r"(s|x|z|ch|sh)$", re.I)   # address -> addresses, box -> boxes, branch -> branches


def _plural(n: int, word: str) -> str:
    """A count and its noun, agreeing. A noun already ending in a sibilant takes -es: appending -s to
    "IPv4 address" is what gave ghidra's report "2 IPv4 addresss"."""
    if n == 1:
        return f"{n} {word}"
    return f"{n} {word}es" if _SIBILANT.search(word) else f"{n} {word}s"


SECRETS_NAMED = 3       # values a secrets finding names, past which it says "and N more"
SECRETS_NAMED_ALL = 5   # up to this many, a critical finding names every value: hindsight's hosted-database password was the fifth


def _secret_statement(groups: list, declared: bool = False, every: int = SECRETS_NAMED) -> str:
    """'N distinct values in M places: rule in file (commits), ...' with at most three values named, or every
    value when there are no more than `every`: the critical finding names up to five, since "and 2 more" is
    where a reader stops, and on hindsight one of the two was the real one.

    A value found in an unreachable blob belongs to no commit, so its commit is the empty string. Those
    are dropped rather than joined, and a value with no commit left names no parenthesis at all: react's
    one critical finding read "in (unreachable blob 00db21063ea1) ()", and django's "(, d61f33f and 6
    more)" with the empty string still in the list. Two distinct values can also be the same rule in the
    same blob, which rendered as the same words twice with nothing to tell them apart; identical entries
    are counted instead. `declared` names, for each value, where the repository declared it allowed."""
    def one(g):
        others = len(g["files"]) - 1
        where = g["files"][0] + (f" and {_plural(others, 'other file')}" if others else "")
        named = [c for c in g["commits"] if c]     # an unreachable blob is in no commit
        commits = ", ".join(named[:2]) + (f" and {len(named) - 2} more" if len(named) > 2 else "")
        said = g.get("declared") if declared else None
        told = f", declared allowed in {said['file']} at {said['commit']}" if said else ""
        return f"{g['rule']} in {where}" + (f" ({commits}{told})" if commits else f" ({told[2:]})" if told else "")
    places = sum(g["places"] for g in groups)
    named = len(groups) if len(groups) <= every else SECRETS_NAMED
    counts = {}                                    # insertion order, so the first named stay in their order
    for text in (one(g) for g in groups[:named]):
        counts[text] = counts.get(text, 0) + 1
    sample = "; ".join(f"{n} values of {text}" if n > 1 else text for text, n in counts.items())
    more = f" and {len(groups) - named} more" if len(groups) > named else ""
    return f"{_plural(len(groups), 'distinct value')} in {_plural(places, 'place')}: {sample}{more}."


# The nearest published estimate of the scanner's accuracy: betterleaks is gitleaks' successor and has no measurement
# of its own. Gitleaks on SecretBench, a benchmark of real secrets in public repositories (Basak et al., ESEM 2023).
SECRETS_MEASURED = "Gitleaks, betterleaks' predecessor: 46% precision, 88% recall on SecretBench (Basak et al., ESEM 2023)"


def _head_split(groups: list) -> dict:
    """The values HEAD still holds and those only in history, each by its rule and first file (never the
    value), from leaks.group's `at_head`; a value the run did not judge counts as still at HEAD, which is
    what the advice assumed before HEAD was read."""
    def name(g):
        return {"rule": g["rule"], "file": g["files"][0]}
    held = [g for g in groups if g.get("at_head") is not False]
    gone = [g for g in groups if g.get("at_head") is False]
    return {"at_head": len(held), "history_only": len(gone), "history_only_values": [name(g) for g in gone][:10]}


def _rotate_advice(groups: list) -> str:
    """Rotate every value; for one only in history, also rewrite the history if it is published. Deleting a
    file leaves the value in every clone: Meli, McNiece and Reaves (NDSS 2019) found 81% of the secrets
    they saw committed to GitHub never removed, and of the repositories that did remove one, none had
    rewritten its history."""
    split = _head_split(groups)
    held, gone = split["at_head"], split["history_only"]
    if not gone:
        return "Rotate them; deleting the file does not remove them from git."
    rewrite = "rewrite it: deleting the file does not remove a value from git"
    if not held:
        return f"None is at HEAD any more: rotate them and, if the history is published, {rewrite}."
    return f"Rotate them all; {held} {'is' if held == 1 else 'are'} still at HEAD and {gone} only in history: if the history is published, {rewrite}."


def _secret_evidence(groups: list, declared: bool = False) -> dict:
    out = {"values": len(groups), "places": sum(g["places"] for g in groups), "files": sorted({f for g in groups for f in g["files"]})[:10]}
    if declared:
        out["declared"] = [dict(g["declared"], rule=g["rule"]) for g in groups][:10]
    return out


# A file named as a template of another (.env.example, config.yml.sample, settings.template): what it holds is
# the shape a reader copies and fills in, by the ecosystem's own naming. A value only ever there is a specimen.
_TEMPLATE_FILE = re.compile(r"\.(example|sample|template)$", re.I)


def secrets_found(report: dict) -> list:
    """Secrets grouped by value. A value anywhere in source is critical. One that only ever appears in
    test files (fixtures, saved pages), example or rule directories (language samples, a scanner's own
    rules), documentation (templates), vendored or generated files is not a finding: it was one
    (secrets_aside) until 0.39.0, labelled never actionable, and it is still counted in the report's
    Secrets line and kept in secrets.json. Version strings, template markers and key blocks without key
    material were flagged as placeholders and are not a finding.

    A value in source the repository declared allowed at some commit (an allowlist of its gitleaks or
    betterleaks config, its ignore file, `gitleaks:allow` on the value's line: leaks.annotate) is not
    critical: betterleaks reads today's config only, so a public key the repository allowlisted and later
    replaced was graded critical and told to be rotated. It is info, naming where the declaration is.

    A value only ever in files named as templates of others (.env.example, *.sample, *.template) is a
    specimen like one in an examples directory. A value every sighting of which is the password of a
    connection string to loopback or to a service the repository's compose file declares (leaks.mark_local)
    is a development default: info (secrets_local), not critical. hindsight's critical held six such values
    in 58 of its 65 places, and its two real ones were the first and the fifth named."""
    return _secrets_by_rule(report)[0]


def _secrets_by_rule(report: dict) -> tuple:
    """(the secrets findings, {rule id: the value groups it holds}): the groups for SARIF, which places each
    value of a finding and no other."""
    groups = leaks.group(report.get("secrets") or [])

    vendored, generated, doubles = filetypes.vendor_dirs(report), _generated(report), _test_doubles(report)

    def in_source(g):   # a copy in an unreachable blob has no path: the value's located copies say where it lives
        located = [f for f in g["files"] if not f.startswith(leaks.UNREACHABLE)] or g["files"]
        inline = set(g.get("test_code_files") or ())   # every sighting there inside a Rust test module
        return any(not (filetypes.is_test_path(f) or filetypes.is_doc_path(f) or filetypes.is_sample_path(f) or filetypes.is_vendored(f, vendored)
                        or filetypes.is_mock_path(f) or filetypes.is_tooling_path(f) or f in generated or _TEMPLATE_FILE.search(f) or f in inline or f in doubles)
                   for f in located)

    def possible(g):   # only the scanner's generic rules found it, and it graded every sighting low
        return g["rule"].startswith("generic-") and g.get("confidence") == "low"
    declared = [g for g in groups if in_source(g) and g.get("declared")]
    local = [g for g in groups if in_source(g) and g.get("local") and not g.get("declared")]
    source = [g for g in groups if in_source(g) and not possible(g) and not g.get("declared") and not g.get("local")]
    maybe = [g for g in groups if in_source(g) and possible(g) and not g.get("declared") and not g.get("local")]
    ignore = "Add the fingerprint of any false positive from secrets.json to .betterleaksignore in the repository."
    out = []
    if source:
        out.append(_f("critical", f"{len(source)} secret(s) in history", _secret_statement(source, every=SECRETS_NAMED_ALL),
                      f"{_rotate_advice(source)} {ignore}",
                      rule={"id": "secrets_in_source", "scanner": "betterleaks", "placeholders": "left out", "measured": SECRETS_MEASURED},
                      evidence={**_secret_evidence(source), **_head_split(source)}))
    if maybe:
        out.append(_f("info", f"{len(maybe)} possible secret(s) in source", _secret_statement(maybe),
                      f"Look at each: the scanner's generic rules found them and graded every sighting low, which is how an ordinary assignment "
                      f"or a hash reads as well as a key. {ignore}",
                      rule={"id": "secrets_possible", "scanner": "betterleaks", "confidence": "low", "rules": "generic-*"}, evidence=_secret_evidence(maybe)))
    if declared:
        out.append(_f("info", f"{len(declared)} secret(s) the repository declared allowed", _secret_statement(declared, declared=True),
                      "The repository marked each as not a secret (a publishable client key, a fixture); confirm that still holds. "
                      "Withdrawing the declaration makes the value a finding again.",
                      rule={"id": "secrets_declared", "scanner": "betterleaks", "declared_by": "config, ignore file or gitleaks:allow at any commit"},
                      evidence=_secret_evidence(declared, declared=True)))
    if local:
        out.append(_f("info", f"{len(local)} password(s) to a local service", _secret_statement(local),
                      "Each is the password of a connection string to this machine or to a service the repository's own compose file "
                      "runs: a development default. Make sure no deployed service shares it.",
                      rule={"id": "secrets_local", "scanner": "betterleaks", "hosts": "loopback, or a service a compose file declares"},
                      evidence=_secret_evidence(local)))
    return out, {"secrets_in_source": source, "secrets_possible": maybe, "secrets_declared": declared, "secrets_local": local}


def secret_groups(report: dict) -> dict:
    """{secrets rule id: the value groups (leaks.group) its finding holds}, for SARIF, which places each value
    under the finding that holds it and under no other."""
    return _secrets_by_rule(report)[1]


def credential_files(report: dict) -> list:
    """Tracked files whose name says they hold a login (.env.production, .netrc, id_rsa): a finding by the
    name alone, whatever betterleaks made of the contents. The run lists them in meta.json."""
    paths = (report.get("meta") or {}).get("credential_files") or []
    if not paths:
        return []
    shown = ", ".join(paths[:5]) + (f" and {len(paths) - 5} more" if len(paths) > 5 else "")
    return [_f("warning", "Credential-shaped files tracked", f"{_plural(len(paths), 'credential-shaped file')} tracked: {shown}.",
               "Move the values to the environment, git rm the files and add them to .gitignore; a template belongs in .env.example.",
               rule={"id": "credential_files", "by": "file name"}, evidence={"count": len(paths), "files": paths[:10]})]


def _all_identities(report: dict):
    """Every identity row plus its aliases, flattened."""
    for i in report["meta"].get("identities") or []:
        yield i
        for a in i.get("aliases") or []:
            yield a


def placeholder_identity(report: dict, min_share: float = 0.01) -> list:
    """A placeholder name or mailbox with a real share of the commits. One stray commit in thousands
    is not worth the panel space."""
    identities = report["meta"].get("identities") or []
    total = sum(i["commits"] for i in identities)

    def is_placeholder(i):
        return i["name"].strip().lower() in PLACEHOLDER_NAMES or bool(PLACEHOLDER_EMAIL.search(i["email"].lower()))
    real = max((i for i in identities if not is_placeholder(i)), key=lambda i: i["commits"], default=None)
    out = []
    for i in _all_identities(report):
        if total and i["commits"] / total < min_share:
            continue
        if is_placeholder(i):
            # the busiest real identity is the likely owner; the line is offered, never applied
            advice = (f"Set user.name and user.email. If those commits are {real['name']}'s, add to .mailmap: "
                      f"{real['name']} <{real['email']}> {i['name']} <{i['email']}>; the people, bus factor and "
                      f"knowledge findings then describe one person." if real
                      else "Set user.name and user.email; consider a .mailmap for history.")
            out.append(_f("warning", "Unconfigured git identity",
                          f"\"{i['name']} <{i['email']}>\" made {_plural(i['commits'], 'commit')} ({_pct(i['commits'], total)}).", advice,
                          rule={"id": "placeholder_identity", "min_share": min_share},
                          evidence={"name": i["name"], "email": i["email"], "commits": i["commits"], "total_commits": total}))
    return out


def _source_ownership(report: dict) -> list:
    """Ownership rows for source files. Test files, vendored trees and generated files are left out of every
    rule that names a next step: owning the tests is not the knowledge risk, whoever imported vendor/ did
    not write it, and whoever last ran a generator did not write its output (pairing someone on a generated
    client is advice about who runs the generator). The default tables leave test files out too."""
    vendored, generated = filetypes.vendor_dirs(report), _generated(report)
    return [r for r in report.get("ownership") or []
            if not (filetypes.is_test_path(r["entity"]) or filetypes.is_vendored(r["entity"], vendored) or r["entity"] in generated)]


def _present_areas(report: dict, rows: list, build=knowledge.areas) -> list:
    """Areas built from the ownership rows of directories that still exist, then only those areas that
    exist themselves: a directory the history knows but HEAD does not (the layout before a move to
    src/ or crates/) is nowhere to pair anyone on. `build` is knowledge.areas or a wrapper of it, called
    with the base a --path run counts its areas from."""
    tree, base = _tree(report), scope.report_base(report)
    return [a for a in build(knowledge.present_rows(rows, tree), base=base) if knowledge.in_tree(a["area"], tree, base)]


def _gone(report: dict) -> set:
    """The names the knowledge map counts as gone (loss.gone), which a finding marks and never sends a
    reader to: advice to pair with someone who stopped committing a year ago cannot be followed."""
    return {g["name"] for g in loss.gone(report, report["meta"].get("gone_months", loss.DEFAULT_MONTHS))}


def _who(name: str, gone: set) -> str:
    """A name as a finding's statement prints it: "(gone)" after it, as the knowledge map does, when
    the person has stopped committing."""
    return f"{name} (gone)" if name in gone else name


def _still_here(owners, gone: set):
    """The first of (name, lines) owners, most first, who is not gone, or None when nobody active holds any
    or when several of them hold exactly as much (_tied_here): the first of those is the alphabet's choice,
    and advice to hand an area to that one person would rest on the spelling of a name."""
    here = [(n, x) for n, x in owners if n not in gone and x > 0]
    return here[0][0] if here and _tied_here(owners, gone) == 1 else None


def _tied_here(owners, gone: set) -> int:
    """How many of the people still here hold exactly the most that anyone still here holds: 0 when nobody
    active holds any, 1 when one person leads, more when the lead is shared."""
    return knowledge.tied([(n, x) for n, x in owners if n not in gone and x > 0])


def bus_factor(report: dict, threshold: float = 0.7, min_lines: int = 200) -> list:
    """One author owns most of the surviving code (whole history). The areas named in the advice
    come from lines added, which `--since` windows, so the advice says so when it applies."""
    shares = report.get("theseus_authors") or {}
    total = sum(shares.values())
    if not total:
        return []
    name, lines = max(shares.items(), key=lambda kv: kv[1])
    if lines / total <= threshold:
        return []
    theirs, owners_of = [], {}
    for a in _present_areas(report, _source_ownership(report)):
        owned = dict(a["owners"]).get(name, 0)
        if a["lines"] >= min_lines and owned / a["lines"] >= 0.8:
            theirs.append((a["area"], round(100 * owned / a["lines"])))
            owners_of[a["area"]] = a["owners"]
    gone = _gone(report)
    ask = None
    if name not in gone and theirs:
        areas = " and ".join(t[0] for t in theirs[:2])
        shares_ = " and ".join(f"{t[1]}%" for t in theirs[:2])
        since = report["meta"].get("since")
        advice = (f"Pair someone with {name} on {areas} first; {'they are' if len(theirs) > 1 else 'it is'} {shares_} theirs"
                  f"{f' since {since}' if since else ''}.")
    elif name not in gone:
        advice = f"Pair someone with {name} before they are unavailable."
    elif theirs:   # they have left: the one to ask is whoever still here wrote the most of what they owned
        area = theirs[0][0]
        ask = _still_here(owners_of[area], gone)
        level = _tied_here(owners_of[area], gone)
        advice = (f"Have {ask}, its largest author still here, own {area} first." if ask
                  else f"Give {area} an owner; the {level} people still here who wrote the most of it wrote equally much." if level > 1
                  else f"Nobody still here has written any of {area}; give it an owner.")
    else:
        ranked = sorted(shares.items(), key=lambda kv: (-kv[1], kv[0]))
        ask, level = _still_here(ranked, gone), _tied_here(ranked, gone)
        advice = (f"Have {ask}, who holds the most surviving code among the people still here, take over what they wrote." if ask
                  else f"Give what they wrote owners; the {level} people still here who hold the most surviving code hold equally much." if level > 1
                  else "Nobody still here holds any of the code; give it owners.")
    return [_f("warning", "Bus factor of one", f"{_who(name, gone)} wrote {_pct(lines, total)} of the code that survives today.", advice,
               rule={"id": "bus_factor", "threshold": threshold, "min_lines": min_lines},
               evidence={"author": name, "gone": name in gone, "ask": ask, "lines": lines, "total_lines": total,
                         "areas": [{"area": a, "share_pct": s} for a, s in theirs[:10]]})]


def _tree(report: dict) -> dict:
    """The files at HEAD, from scc, or {} when the run has no size listing to judge by."""
    return (report.get("size") or {}).get("files") or {}


def at_head(report: dict, path: str):
    """Whether a path (a file, or a directory by its prefix) is in the tree at HEAD: from the run's
    listing of HEAD when it has one, else from scc's file list, which leaves out every file it has no
    language for (a binary, a .env); None when there is neither to judge by."""
    tree = report.get("tree") or _tree(report)
    if not tree:
        return None
    prefix = path.rstrip("/") + "/"
    return path in tree or any(p.startswith(prefix) for p in tree)


def sweeping_commits(report: dict) -> list:
    """The commits the change analysis left out as sweeps (a formatter run, a rename across the tree:
    over the repository's 99th percentile of files touched, with as many lines out as in) that the
    repository has not declared in .git-blame-ignore-revs. Declaring them makes git blame and GitHub
    skip them too, which is the repository's own mechanism for exactly this."""
    act = report.get("activity") or {}
    swept = [c for c in act.get("sweeping") or [] if not c.get("declared")]
    if not swept:
        return []
    declared = act.get("ignored_revs") or 0

    def one(c):
        subject = f", {textfmt.cut(c['subject'], 60)}" if c.get("subject") else ""
        return f"{c['hash']} ({c['files']:,} files, {c['date']}{subject})"
    listed = "; ".join(one(c) for c in swept[:3]) + (f" and {len(swept) - 3} more" if len(swept) > 3 else "")
    least = min(c["files"] for c in swept)
    statement = (f"{_plural(len(swept), 'commit')} each touch {least:,} files or more and take out as many lines as they put in: {listed}. "
                 "They are left out of the churn, coupling and ownership counts.")
    named = textfmt.join_and([c["hash"] for c in swept[:3]]) + (" and the rest" if len(swept) > 3 else "")
    already = f"; {_plural(declared, 'commit')} {'is' if declared == 1 else 'are'} declared there already" if declared else ""
    return [_f("info", "Sweeping commits", statement, f"Add {named} to .git-blame-ignore-revs so git blame and GitHub skip them too{already}.",
               rule={"id": "sweeping_commits", "min_files": maat.SWEEP_MIN_FILES, "percentile": maat.SWEEP_PERCENTILE, "tolerance": maat.SWEEP_TOLERANCE},
               evidence={"declared": declared, "commits": [{"hash": c["hash"], "date": c["date"], "files": c["files"], "added": c.get("added"),
                                                             "deleted": c.get("deleted"), "subject": c.get("subject", "")} for c in swept[:10]]})]


def imports_gone(report: dict) -> list:
    """The import commits nothing of which is in the tree any more: every path they brought in, its renames
    followed, is untracked at the analysed commit and the log shows it deleted (load.parse_imports; known only
    with a tree listing)."""
    return [c for c in (report.get("activity") or {}).get("imports") or [] if c.get("in_tree") == 0]


def imports_gone_note(report: dict):
    """'1 import left out of ownership (7446c84, 313 code files under x/node_modules/, removed in 7619570): nothing
    of it is in the tree', or None: what the report says of an import that is no finding (import_commits)."""
    gone = imports_gone(report)
    if not gone:
        return None

    def one(c):
        where = f" under {c['under']}" if c.get("under") else ""
        rm = c.get("removed_in")
        return f"{c['hash']}, {c['files']:,} code file{'s' if c['files'] != 1 else ''}{where}" + (f", removed in {rm['hash']}" if rm else "")
    listed = "; ".join(one(c) for c in gone[:3]) + (f" and {len(gone) - 3} more" if len(gone) > 3 else "")
    return f"{_plural(len(gone), 'import')} left out of ownership ({listed}): nothing of {'it' if len(gone) == 1 else 'them'} is in the tree"


def import_commits(report: dict) -> list:
    """Commits that brought a codebase in rather than changed it (maat.importing): a hundred code files
    or more, a twentieth or more of every line of code the history adds, deleting at most a hundredth of
    what they add. The change analysis leaves them out of ownership and authorship, and the code-age pass
    credits the lines they wrote to nobody, so the person who committed an import is not made the owner of
    everything in it. Said, since the knowledge tables then read differently from a plain git blame.

    The rule counts code files; the commit's raw totals stand beside them where log.txt gave them
    (load.parse_imports), with the vendored directory everything it brought sits under and the binaries
    it carried. An import nothing of which is still tracked changes no table about the tree: it is no
    finding, and a note under the knowledge map says where it went (imports_gone_note)."""
    act = report.get("activity") or {}
    dead = {c["hash"] for c in imports_gone(report)}
    rows = [c for c in act.get("imports") or [] if c["hash"] not in dead]
    if not rows:
        return []
    total = act.get("added_total") or 0
    gone = _gone(report)

    def one(c):
        raw = "files_all" in c
        files = f"{c['files']:,} code files of {c['files_all']:,}" if raw else f"{c['files']:,} code files"
        lines = f"{c['added']:,} lines of code of {c['added_all']:,}" if raw else f"{c['added']:,} lines of code"
        share = f", {100 * c['added'] / total:.0f}% of all the code the history adds" if total else ""
        where = f", all under {c['under']}" if c.get("under") else ""
        binaries = f", {c['binaries']:,} binary file{'s' if c['binaries'] != 1 else ''}" if c.get("binaries") else ""
        return (f"{c['hash']} by {c['author']} ({'gone, ' if c['author'] in gone else ''}{files}; {lines}{share}{where}{binaries}; "
                f"{c['date']}, {textfmt.cut(c.get('subject', ''), 50)})")
    listed = "; ".join(one(c) for c in rows[:3])
    return [_f("info", "Imports left out of ownership",
               f"{_plural(len(rows), 'commit')} {'adds' if len(rows) == 1 else 'add'} code and {'changes' if len(rows) == 1 else 'change'} almost none: {listed}. "
               # the measures every report has; the truck factor reads authorship and is not computed for a small pool,
               # so naming it promised a number superpowers' report (17 scored files) never showed
               "Ownership, authorship and the churn counts leave it out; code age credits its surviving lines to nobody.",
               "Read the knowledge tables as who has worked on the code since; git blame still names the importer for every untouched line.",
               rule={"id": "import_commits", "share": maat.IMPORT_SHARE, "min_files": maat.IMPORT_MIN_FILES, "deleted": maat.IMPORT_DELETED},
               evidence={"commits": [{"hash": c["hash"], "date": c["date"], "author": c["author"], "files": c["files"], "added": c["added"],
                                      "deleted": c["deleted"], "subject": c.get("subject", ""),
                                      **{k: c[k] for k in ("files_all", "added_all", "binaries", "under", "in_tree") if k in c}}
                                     for c in rows[:10]], "added_total": total})]


def tangled_commits(report: dict, min_share: float = 0.02, min_count: int = 5) -> list:
    """Commits that do several things at once: ten or more files across four or more directories under
    a subject that lists several changes. Herzig and Zeller (MSR 2013) found tangled fixes mislabel a
    large share of the files they touch; the fix pool already leaves out fixes over the repository's
    99th percentile of lines. A habit is worth a line, one such commit in a hundred is not."""
    act = report.get("activity") or {}
    count, listed = act.get("tangled_commits") or 0, act.get("tangled") or []
    total = report["meta"].get("commits") or 0
    if not count or not total or count < min_count or count / total < min_share:
        return []
    big = act.get("oversized_fixes") or 0

    def one(c):
        return f"{c['hash']} ({c['files']:,} files, {c['dirs']} directories, {textfmt.cut(c['subject'], 70)})"
    sample = "; ".join(one(c) for c in listed[:3]) + (f" and {count - 3} more" if count > 3 and len(listed) >= 3 else "")
    aside = (f", so {big} {'fix' if big == 1 else 'fixes'} over the repository's 99th percentile of lines changed {'is' if big == 1 else 'are'} already left out of the fix counts"
             if big else "")
    return [_f("info", "Tangled commits",
               f"{count:,} of {total:,} commits ({_pct(count, total)}) touch {maat.TANGLED_FILES} or more files across {maat.TANGLED_DIRS} or more directories "
               f"under a subject that lists several changes: {sample}. A fix among them credits every file it touched{aside}.",
               "Split a change that does several things before merge; the fix history stays readable and the coupling stays real.",
               rule={"id": "tangled_commits", "min_files": maat.TANGLED_FILES, "min_dirs": maat.TANGLED_DIRS, "min_clauses": maat.TANGLED_CLAUSES,
                     "min_share": min_share, "min_count": min_count},
               evidence={"count": count, "commits": total, "oversized_fixes": big,
                         "sample": [{"hash": c["hash"], "date": c["date"], "files": c["files"], "dirs": c["dirs"], "subject": c["subject"]} for c in listed[:10]]})]


def _both_specimens(a: str, b: str) -> bool:
    """Whether a coupled pair is two pieces of example or documentation material rather than code the
    repository runs. curl's docs/examples/imap-ssl.c and docs/examples/pop3-ssl.c show one technique for
    two protocols, and docs/examples/smtp-expn.c and smtp-vrfy.c two commands of one: the "shared format,
    duplicated rule or copied code" a coupling finding sends the reader to look for is what an example
    family is for, and merging them would make each one worse at its job. Both sides must be specimens;
    an example paired with the code it demonstrates is still reported, since that pair says the example
    tracks the API."""
    def specimen(p):
        return filetypes.is_sample_path(p) or filetypes.is_doc_path(p)
    return specimen(a) and specimen(b)


def tight_coupling(report: dict, min_degree: int = 80, min_revs: int = 5) -> list:
    """A file and its test are expected to change together, so pairs with a test file on either side are
    left out; so are pairs where either file is no longer in the tree, which are history, not a dependency,
    pairs of release plumbing (two version files, a manifest and its lock file), which are a release, and
    pairs that are both example or documentation material (_both_specimens)."""
    tree, vendored, derived = _tree(report), filetypes.vendor_dirs(report), _generated(report)
    pairs = [p for p in report.get("coupling") or [] if p["degree"] >= min_degree and p["average-revs"] >= min_revs
             and not (filetypes.is_test_path(p["entity"]) or filetypes.is_test_path(p["coupled"]))
             and not (p["entity"] in derived or p["coupled"] in derived)
             and not (filetypes.is_release_path(p["entity"]) and filetypes.is_release_path(p["coupled"]))
             and not _both_specimens(p["entity"], p["coupled"])
             and not filetypes.is_header_pair(p["entity"], p["coupled"])
             and not (filetypes.is_vendored(p["entity"], vendored) or filetypes.is_vendored(p["coupled"], vendored))
             and not (tree and (p["entity"] not in tree or p["coupled"] not in tree))]
    if not pairs:
        return []
    pairs.sort(key=lambda p: (-p["degree"], -p["average-revs"]))
    groups, pairs = coupling.clusters(pairs)
    rule = {"id": "tight_coupling", "min_degree": min_degree, "min_revs": min_revs}
    evidence = {"clusters": [{"dir": g["dir"], "files": g["files"], "pairs": g["pairs"], "degree": g["degree"]} for g in groups[:10]],
                "pairs": [{"a": p["entity"], "b": p["coupled"], "degree": p["degree"], "revs": p["average-revs"]} for p in pairs[:10]]}
    when = f"together at least {min_degree}% of the time"
    top = "; ".join(f"{p['entity']} + {p['coupled']} ({p['degree']}%)" for p in pairs[:3])
    if groups:
        # a directory of files that change as one is a generator or a shared layout, said once
        named = ", ".join(f"{g['files']} files in {g['dir']}" for g in groups[:2]) + (f" and {len(groups) - 2} more directories" if len(groups) > 2 else "")
        rest = (f", and {_plural(len(pairs), 'more pair')} {'does' if len(pairs) == 1 else 'do'}: {top}." if pairs
                else f", {_plural(sum(g['pairs'] for g in groups), 'pair')} in all.")
        first = groups[0]
        return [_f("info", "Files that always change together", f"{named} change {when}{rest}",
                   f"Review {first['dir']} first: {first['files']} files change as one; a generator or a shared layout links them.",
                   rule=rule, evidence=evidence)]
    count = f"{len(pairs)} pair changes" if len(pairs) == 1 else f"{len(pairs)} pairs change"
    first = pairs[0]
    return [_f("info", "Files that always change together",
               f"{count} {when}, e.g. {top}.",
               f"Review {first['entity']} and {first['coupled']} first: a shared layout or a hidden dependency links them.",
               rule=rule, evidence=evidence)]


def _months_apart(earlier: str, later: str) -> int:
    """Whole months from one ISO date to another."""
    y1, m1, d1 = (int(x) for x in earlier[:10].split("-"))
    y2, m2, d2 = (int(x) for x in later[:10].split("-"))
    return (y2 - y1) * 12 + (m2 - m1) - (1 if d2 < d1 else 0)


def _dormant_months(report: dict) -> int:
    """Months since the last commit, against the run's reference date (GITMOLE_NOW or today)."""
    import datetime as _dt
    last = report["meta"].get("last_date")
    if not last:
        return 0
    now = report["meta"].get("now") or _dt.date.today().isoformat()
    return max(0, _months_apart(last, now))


def dormant(report: dict, months: int = 12) -> list:
    """No commits for a year or more: everything else in the report describes a repository that has
    stopped, which is the first thing to know about it."""
    idle = _dormant_months(report)
    if idle < months:
        return []
    return [_f("warning", "Dormant repository", f"No commits since {report['meta']['last_date']}, {idle} months ago.",
               "The rest of the report describes a repository that has stopped; look for a successor or an archive notice before depending on it.",
               rule={"id": "dormant", "months": months}, evidence={"last_date": report["meta"]["last_date"], "idle_months": idle})]


def _magnet_items(hot: list, history: dict, now: str, since: str = None) -> list:
    """The hot files as the finding lists them, as (files, text, label, new files), label being what the
    advice calls the item. A hot file whose recent fixes were all commits that also fixed a file listed
    before it is listed with that file, not on its own: it has no fix of its own in the window, so
    counting it again counts the same commits twice (one fix touching four sibling files was once four
    magnets). No threshold: a file joins only when every one of its recent fix commits is the other's.
    A file is "new in the window" when it first appeared less than the six months ago the window
    reaches back to, so its fix count is the whole of its life. That is said only when the history
    (`since`, its first commit) reaches past the window: in a younger repository every file is new in
    it, and the words would tell the reader nothing (VoiceStudio's five were all "new in the window").
    There every fix is recent, so the total, which only repeats the recent count, is left out too.
    Without the history's first date neither is said."""
    whole = bool(since) and maat._months_between(since, now) < maat.RECENT_MONTHS

    def new(f):
        first = (history.get(f["entity"]) or {}).get("first")
        return bool(since) and not whole and bool(first) and maat._months_between(first, now) < maat.RECENT_MONTHS
    commits = {f["entity"]: set((history.get(f["entity"]) or {}).get("recent") or ()) for f in hot}
    items, done = [], set()
    for f in hot:
        if f["entity"] in done:
            continue
        lead = f["entity"]
        members = [g for g in hot if g["entity"] not in done and g["entity"] != lead and commits[g["entity"]] and commits[lead]
                   and commits[g["entity"]] <= commits[lead]]
        done.add(lead)
        done.update(g["entity"] for g in members)
        fresh = [m["entity"] for m in (f, *members) if new(m)]
        # a file new in the window has had every fix inside it, so its total would only repeat the recent count
        counts = [f"{f['recent-fixes']} recent"] + ([] if (whole or new(f)) and f["n-fixes"] == f["recent-fixes"] else [f"{f['n-fixes']} total"])
        text = f"{lead} ({', '.join(counts + (['new in the window'] if new(f) else []))})"
        if members:
            beside = all(g["entity"].rpartition("/")[0] == lead.rpartition("/")[0] for g in members)
            text += f" and {_plural(len(members), 'file')}{' beside it' if beside else ''} fixed in the same commits"
        items.append(([lead, *(g["entity"] for g in members)], text, lead, fresh))
    return items


FIX_RATE_Q = 0.05   # the false discovery rate the fix-rate test keeps to, Benjamini and Hochberg's own example


def _binomial_tail(k: int, n: int, p: float) -> float:
    """P(X >= k) for X ~ Binomial(n, p), summed upward from k in log space until the terms stop mattering."""
    if k <= 0:
        return 1.0
    if k > n:
        return 0.0
    lp, lq = math.log(p), math.log1p(-p)
    term = math.exp(math.lgamma(n + 1) - math.lgamma(k + 1) - math.lgamma(n - k + 1) + k * lp + (n - k) * lq)
    total, i, mode = term, k, (n + 1) * p
    while i < n:
        term *= (n - i) / (i + 1) * p / (1 - p)
        i += 1
        total += term
        if i > mode and term <= total * 1e-17:
            break
    return min(1.0, total)


def _benjamini_hochberg(pvalues: dict, q: float) -> set:
    """The keys whose null the Benjamini-Hochberg step-up procedure rejects at false discovery rate q."""
    ranked = sorted(pvalues.items(), key=lambda kv: (kv[1], kv[0]))
    m, cut = len(ranked), 0
    for i, (_, pv) in enumerate(ranked, 1):
        if pv <= q * i / m:
            cut = i
    return {k for k, _ in ranked[:cut]}


FIX_RATE_STRATA = 10   # tenths of the tested files by lines of code: a big file is compared with big files
FIX_RATE_MIN_MONTHS = 12   # twice the six-month window: a shorter history tests the window's own counts again


def _size_strata(files, size: dict, n: int = FIX_RATE_STRATA) -> dict:
    """Each file's stratum by lines of code: the n-tiles of the tested files' sizes, ties kept together (a
    file's stratum is how many cut points its size reaches), so files of one size are always compared alike."""
    code = {e: ((size.get(e) or {}).get("code") or 0) for e in files}
    ranked = sorted(code.values())
    cuts = [ranked[len(ranked) * i // n] for i in range(1, n)] if ranked else []
    return {e: bisect.bisect_right(cuts, c) for e, c in code.items()}


def _history_months(report: dict):
    """Whole months from the analysed history's first commit to its last, or None when the run has no dates."""
    meta = report.get("meta") or {}
    first, last = meta.get("first_date"), meta.get("last_date")
    return _months_apart(first, last) if first and last else None


def fix_prone(report: dict, keep, q: float = FIX_RATE_Q):
    """The files fixed more often than files of their size in this repository explain: the tested files are
    split into tenths by lines of code, and each file's fix commits are tested against its changes at its
    tenth's rate (fixes over changes) with a one-sided binomial test, then Benjamini-Hochberg over all of
    them at false discovery rate `q`. Against the whole repository's rate, the test mostly named the largest
    files (hindsight at 0.40.0: all 13 in the top tenth by lines, 2 left within their tenth): a big file is
    changed and fixed more, which the magnets' ranking already says. Counts are the whole analysed
    history's, as maat-fixes and maat-revisions draw them from the same commits; the six-month window is
    what picked the magnets, so a history shorter than FIX_RATE_MIN_MONTHS is mostly that window and is not
    tested. Fixes cluster (one pull request, several fix commits), so the variance is wider than a
    binomial's and the test errs towards discovery (Spiegelhalter, Stat Med 2005): the result orders and
    annotates, it decides nothing. None when there is no rate to test against: no change table, a history
    too short, or every change a fix or none."""
    months = _history_months(report)
    if months is not None and months < FIX_RATE_MIN_MONTHS:
        return None
    fixes = {f["entity"]: f["n-fixes"] for f in report.get("fixes") or [] if keep(f["entity"])}
    changes = {r["entity"]: r["n-revs"] for r in report.get("revisions") or [] if keep(r["entity"])}
    if not changes:
        return None
    pool = {e: (fixes.get(e, 0), max(n, fixes.get(e, 0))) for e, n in changes.items()}   # a file with no change row is not tested
    total_fixes, total_changes = sum(k for k, _ in pool.values()), sum(n for _, n in pool.values())
    if not 0 < total_fixes < total_changes:
        return None
    stratum = _size_strata(pool, (report.get("size") or {}).get("files") or {})
    sums = {}
    for e, (k, n) in pool.items():
        a, b = sums.get(stratum[e], (0, 0))
        sums[stratum[e]] = (a + k, b + n)
    rates = {s: k / n for s, (k, n) in sums.items() if n}

    def tail(e, k, n):
        p = rates.get(stratum[e], 0.0)
        return 1.0 if p >= 1 or k == 0 else _binomial_tail(k, n, p)
    pvalues = {e: tail(e, k, n) for e, (k, n) in pool.items() if n}
    return {"fixes": total_fixes, "changes": total_changes, "files": len(pvalues), "q": q,
            "above": _benjamini_hochberg(pvalues, q), "p": pvalues, "counts": pool,
            "rate": {e: rates.get(stratum[e], 0.0) for e in pvalues}}


def _magnet_keep(report: dict):
    """Whether a path may be a bug magnet: not a test, not release plumbing, not generated, still in the tree."""
    plumb, derived, tree = filetypes.plumbing_paths(report), _generated(report), report.get("tree") or _tree(report)

    def keep(path):
        return not (filetypes.is_test_path(path) or filetypes.is_release(path, plumb) or path in derived) and (not tree or path in tree)
    return keep


def magnet_rows(report: dict, min_recent: int = 3) -> list:
    """The fix rows bug_magnets names, every one of them: what --baseline compares (gate.py). A translation
    file (filetypes.is_locale_path) is not one: a fix that adds a message adds it to every locale, so the
    locales are fixed as often as the busiest of them is (univer: 82 of 287 rows). It stays in fix_prone's
    pool and size strata, which are the repository's rate, not a list of places to look."""
    keep = _magnet_keep(report)
    return [f for f in report.get("fixes") or []
            if f["recent-fixes"] >= min_recent and keep(f["entity"]) and not filetypes.is_locale_path(f["entity"])]


def bug_magnets(report: dict, min_recent: int = 3, warn_at: int = 5) -> list:
    """Source files with a run of recent fix commits. Test files are left out: they change with every fix.
    So is release plumbing: a manifest touched by every fix release is not where the bug was.
    So is a file no longer in the tree: the finding names files to review before the next release, and
    a file a later commit deleted is history (from the run's listing of HEAD, else scc's file list).
    A file whose recent fixes all fixed a file above it too is listed with that file (see _magnet_items).
    Most magnets are busy files in a repository that fixes a lot, so the finding names first the ones
    fixed more often than the repository's own fixes explain (see fix_prone), says how many of all
    there are, and says so when there are none. Which files are magnets, and the severity, stay the
    window's counts: the test annotates and orders. When the history is too short for the test
    (FIX_RATE_MIN_MONTHS), the finding says so and is a note: the counts are then raw, and raw fix counts
    mostly rank files by size (paperclip, 7.5 months: 391 magnets, Spearman 0.56 with lines of code, the
    top ten all among the largest files), which is not a warning's worth of evidence."""
    import datetime as _dt
    keep = _magnet_keep(report)
    hot = magnet_rows(report, min_recent)
    if not hot:
        return []
    hot.sort(key=lambda f: (-f["recent-fixes"], -f["n-fixes"], f["entity"]))
    months = _history_months(report)
    short = months is not None and months < FIX_RATE_MIN_MONTHS
    sev = "warning" if hot[0]["recent-fixes"] >= warn_at and not short else "info"
    prone = fix_prone(report, keep)
    above = [f for f in hot if f["entity"] in prone["above"]] if prone else []
    history = report.get("fix_history") or {}
    order = sorted(hot, key=lambda f: f["entity"] not in prone["above"]) if prone else hot   # stable: the window's order within each
    items = _magnet_items(order, history, report["meta"].get("now") or _dt.date.today().isoformat(), report["meta"].get("first_date"))
    listed = "; ".join(text for _, text, _, _ in items[:5])
    more = len(hot) - sum(len(paths) for paths, _, _, _ in items[:5])
    more = f" and {more} more" if more > 0 else ""
    first = " and ".join(label for _, _, label, _ in items[:2])
    clusters = [{"file": paths[0], "with": paths[1:], "fixes": history[paths[0]]["recent"]} for paths, _, _, _ in items if len(paths) > 1]
    fresh = [p for _, _, _, new in items for p in new]
    rate = "" if prone is None else f", {len(above) or 'none'} beyond files of their size"
    untested = (f" Raw counts: the test against files of their size needs {FIX_RATE_MIN_MONTHS} months of history, "
                f"this has {months or 'less than one'}.") if short else ""
    return [_f(sev, "Bug magnets",
               f"{len(hot)} file(s) were fixed {min_recent}+ times in six months{rate}: {listed}{more}.{untested}",
               f"Review {first} before the next release.",
               rule={"id": "bug_magnets", "min_recent": min_recent, "warn_at": warn_at, "window_months": 6, "fix": "the commit subject says so",
                     "oversized": "a fix over the repository's 99th percentile of lines changed credits nothing",
                     "above_rate": {"test": "one-sided binomial, a file's fixes against its changes at the fixes per change of the files of its size, whole history",
                                    "strata": f"{FIX_RATE_STRATA} by lines of code over the tested files", "min_history_months": FIX_RATE_MIN_MONTHS,
                                    "fdr": "Benjamini-Hochberg over every source file", "q": FIX_RATE_Q, "ref": "Benjamini and Hochberg, JRSS B 1995"}},
               evidence={"count": len(hot), "files": [{"file": f["entity"], "recent_fixes": f["recent-fixes"], "fixes": f["n-fixes"]} for f in hot[:10]],
                         **({"fix_rate": {"fixes": prone["fixes"], "changes": prone["changes"], "files": prone["files"],
                                          "above_rate": [{"file": f["entity"], "fixes": prone["counts"][f["entity"]][0], "changes": prone["counts"][f["entity"]][1],
                                                          "size_rate": round(prone["rate"][f["entity"]], 3)}
                                                         for f in above[:10]]}} if prone else
                            {"fix_rate": {"not_run": "history too short", "history_months": months}} if short else {}),
                         **({"shared_fixes": clusters} if clusters else {}), **({"new_in_window": fresh} if fresh else {})})]


def knowledge_islands(report: dict, min_lines: int = 200, min_share: float = 0.9, min_fraction: float = 0.01) -> list:
    """Areas of the tree written almost entirely by one person. Areas that no longer exist are left
    out, of the islands and of the total they are measured against; an island under `min_fraction`
    of that total (laravel's root files against its src/) is not knowledge worth pairing on."""
    areas = _present_areas(report, _source_ownership(report))
    total = sum(a["lines"] for a in areas)
    islands = [i for i in knowledge.islands(areas, min_lines=min_lines, min_share=min_share) if i["lines"] >= min_fraction * total]
    if not islands:
        return []
    covered = sum(i["lines"] for i in islands)
    sev = "warning" if total and covered / total > 0.5 else "info"
    gone = _gone(report)
    listed = "; ".join(f"{i['area']} ({_who(i['owner'], gone)} {i['share']}%)" for i in islands[:5])
    more = f" and {len(islands) - 5} more" if len(islands) > 5 else ""
    largest = max(islands, key=lambda i: i["lines"])
    at = f"it is the largest at {largest['lines']:,} lines"
    if largest["owner"] not in gone:
        advice = f"Pair someone with {largest['owner']} on {largest['area']} first; {at}."
    else:   # its author has left: the one to ask is whoever still here wrote the most of the rest of it
        held = next(a["owners"] for a in areas if a["area"] == largest["area"])
        ask, level = _still_here(held, gone), _tied_here(held, gone)
        advice = (f"Have {ask}, its largest author still here, own {largest['area']} first; {at}." if ask
                  else f"Give {largest['area']} an owner first; {at} and the {level} people still here who wrote the most of it wrote equally much." if level > 1
                  else f"Give {largest['area']} an owner first; {at} and nobody still here has written any of it.")
    return [_f(sev, "Knowledge islands",
               f"{len(islands)} area(s) with at least {min_lines} lines were written almost entirely by one person: {listed}{more}. "
               f"That is {_pct(covered, total)} of all lines added.",
               advice,
               rule={"id": "knowledge_islands", "min_lines": min_lines, "min_share": min_share, "min_fraction": min_fraction},
               evidence={"count": len(islands), "covered_lines": covered, "total_lines": total, "owners": sorted({i["owner"] for i in islands}),
                         "islands": [{"area": i["area"], "owner": i["owner"], "gone": i["owner"] in gone, "share_pct": i["share"], "lines": i["lines"]}
                                     for i in islands[:10]]})]


def _partial(report: dict, step: str, label: str) -> str:
    """A sentence when a step stopped part way, so what it measured is not the whole code."""
    status = (report["meta"].get(step) or {}).get("status")
    reason = {"timeout": "timed out", "failed": "failed"}.get(status)
    return f" {label} {reason} part way, so there may be more." if reason else ""


def _partial_functions(report: dict) -> str:
    return _partial(report, "functions", "Function metrics")


def brain_rows(report: dict, min_ccn: int = 15, min_lines: int = 100) -> list:
    """The function rows brain_methods names, every one of them: what --baseline compares (gate.py)."""
    generated, vendored, inline, doubles = _generated(report), filetypes.vendor_dirs(report), _test_modules(report), _test_doubles(report)
    return [f for f in report.get("functions") or [] if f["ccn"] >= min_ccn and f["nloc"] >= min_lines and not f.get("suspect")
            and not (filetypes.is_test_path(f["file"]) or f["file"] in doubles or filetypes.is_sample_path(f["file"]) or filetypes.is_vendored(f["file"], vendored)
                     or f["file"] in generated or filetypes.is_migration_path(f["file"]) or filetypes.in_spans(f["start"], inline.get(f["file"])))]


def brain_methods(report: dict, min_ccn: int = 15, min_lines: int = 100) -> list:
    """Functions that are both long and complex, in this repository's own source files: test files,
    example code, vendored code, generated files (amalgamations included) and numbered schema
    migrations (written once and replayed as they stand, so nobody should split one) are left out, and
    so is a span the function step marked suspect, since a mis-parse that swallowed the next function is
    long and complex by construction. A function lizard ended early is measured by the structure step's
    span (load.cross_check), and its complexity is a floor. A warning when one sits in a hotspot."""
    big = brain_rows(report, min_ccn, min_lines)
    if not big:
        return []
    big.sort(key=lambda f: (-f["ccn"], -f["nloc"], f["file"], f["function"], f["start"]))
    hot = hotspots.top(report)
    sev = "warning" if any(f["file"] in hot for f in big) else "info"
    listed = "; ".join(f"{_called(f)} ({_place(f)}) complexity {'at least ' if f.get('lizard_span') else ''}{f['ccn']}, {f['nloc']} lines, "
                       f"{_plural(f['params'], 'param')}" for f in big[:5])
    more = f" and {len(big) - 5} more" if len(big) > 5 else ""
    first = big[0]
    which = f"the anonymous function at {_place(first)}" if _anonymous(first) else f"{first['function']} in {first['file']}"
    return [_f(sev, "Brain methods",
               f"{len(big)} function(s) are both long and complex: {listed}{more}.{_partial_functions(report)}",
               f"Split {which} first, before the next change lands there.",
               rule={"id": "brain_methods", "min_ccn": min_ccn, "min_lines": min_lines},
               evidence={"count": len(big), "partial": bool(_partial_functions(report)),
                         "functions": [{"file": f["file"], "function": f["function"], "start": f["start"], "ccn": f["ccn"], "lines": f["nloc"], "params": f["params"]} for f in big[:10]]})]


ANONYMOUS = "(anonymous)"


def _anonymous(f: dict) -> bool:
    """A function lizard (or the structure step) could not name: it goes by its start line's text (or
    "(anonymous)" in an older functions.csv, "(anonymous at line N)" from the structure step), which is
    not a name to search for. Told by the flag the loader sets or by the name's shape (textfmt.nameless)."""
    return bool(f.get("anonymous")) or textfmt.nameless(f.get("function", f.get("name", "")))


def _called(f: dict) -> str:
    """What the report calls a function: its name, or <anonymous> beside a file:line (_place)."""
    return textfmt.ANONYMOUS if _anonymous(f) else f.get("function", f.get("name", ""))


def _place(f: dict) -> str:
    """Where a function is: its file, or file:line when it has no name to find it by."""
    return f"{f['file']}:{f['start']}" if _anonymous(f) else f["file"]


def _test_modules(report: dict) -> dict:
    """{path: spans} of the Rust test modules the run found (meta.json, filetypes.rust_test_modules): a function
    starting inside one is test code in a file that is not a test file. Empty for a run from before the record."""
    return (report.get("meta") or {}).get("test_modules") or {}


def _test_doubles(report: dict) -> set:
    """The source files of Cargo bins only the tests start (meta.json, filetypes.test_doubles): test code, like a
    file under tests/. Empty for a run from before the record."""
    return set((report.get("meta") or {}).get("test_doubles") or [])


def _generated(report: dict) -> set:
    """Build outputs: generated files and amalgamations (see hotspots.derived)."""
    return hotspots.derived(report)


def complexity_growth(report: dict, min_growers: int = 3, min_pct: int = trend.GROWTH_FLOOR, top_n: int = 10) -> list:
    """The top_n source hotspots whose summed complexity grew over the last year, from the trend samples.
    Test files are left out: a growing test file is not the problem the finding is about.
    The sum is scc's per-file count, so it grows with the lines: each file shows its code's change beside it,
    and "Split" goes to the first grown file whose complexity per line also rose by GROWTH_FLOOR - one that grew
    more tangled, not only longer. When none did, the advice says they grew with their size."""
    series = (report.get("trend") or {}).get("files") or {}
    last = report["meta"].get("last_date") or ""
    if not series or not last:
        return []
    top = [h["entity"] for h in hotspots.ranked(report)
           if h["code"] is not None and not filetypes.is_test_path(h["entity"])][:top_n]
    grown = []
    for path in top:
        change = trend.change_over_year(series.get(path) or [], last)
        if change.startswith("+") and int(change[1:-1]) >= min_pct:
            year = trend.year_change(series.get(path) or [], last) or {}
            grown.append((path, int(change[1:-1]), year.get("code"), year.get("per_line")))
    if len(grown) < min_growers:
        return []
    sev = "warning" if top and grown[0][0] == top[0] else "info"

    def code(c):
        return f", code {c:+d}%" if c is not None else ""
    listed = ", ".join(f"{p} (+{g}%{code(c)})" for p, g, c, _ in grown[:5]) + (f" and {len(grown) - 5} more" if len(grown) > 5 else "")
    split_floor = trend.GROWTH_FLOOR
    denser = next((x for x in grown if x[3] is not None and x[3] >= split_floor), None)
    if denser:
        advice = f"Split {denser[0]} before the next change; its complexity per line rose {denser[3]}% in a year."
    else:
        advice = f"Each grew with its size: no file's complexity per line rose {split_floor}% or more in a year."
    return [_f(sev, "Hotspots getting more complex",
               f"{len(grown)} of the {len(top)} top source hotspots grew by {min_pct}% or more in summed complexity in a year: {listed}.",
               advice,
               rule={"id": "complexity_growth", "min_growers": min_growers, "min_pct": min_pct, "top_n": top_n,
                     "split_min_per_line_pct": split_floor,
                     "split_floor_from": "trend.GROWTH_FLOOR, set for summed complexity, borrowed for complexity per line"},
               evidence={"hotspots": len(top), "split": denser[0] if denser else None,
                         "grown": [{"file": p, "growth_pct": g, "code_pct": c, "per_line_pct": d} for p, g, c, d in grown[:10]]})]


CRITICAL_SCORE = 9.0   # CVSS: the band the advisories themselves call critical
MALICIOUS_PREFIX = "MAL-"   # OpenSSF malicious-packages records: the package is malicious, whatever its score
IGNORE_DEPS = "A vulnerability that does not apply to this code can be ignored in osv-scanner.toml at the repository root."


def _malicious_id(r: dict) -> str:
    return next((x for x in list(r.get("ids") or []) + list(r.get("aliases") or []) if str(x).startswith(MALICIOUS_PREFIX)), "")


def _floating(r: dict) -> bool:
    """A row from a requirement file whose specifier does not name one version (`mcp>=1.0.0`), or whose
    specifier was not recorded: its version is the floor osv-scanner read, not what an install picks."""
    return deps.is_requirement_file(r.get("source") or "") and not r.get("pinned")


def _vuln_ref(r: dict) -> str:
    ref = _malicious_id(r) or (r["aliases"][0] if r.get("aliases") else (r["ids"][0] if r.get("ids") else ""))
    score = f", {r['score']:.1f}" if r.get("score") is not None else (f", {r['severity']}" if r.get("severity") not in (None, "unknown") else "")
    if r.get("malicious"):
        score = ", malicious"
    fixed = f", fixed in {r['fixed']}" if r.get("fixed") else ", no fix yet"
    loaded = ", imported by no tracked source" if r.get("imported") is False else ""
    dev = ", development dependencies only" if r.get("runtime") is False else ""
    via = f", reached through {r['via']}" if r.get("runtime") is True and r.get("via") and r["via"] != r.get("name") else ""
    return f"{ref}{score}{fixed}{loaded}{dev}{via}"


def _vuln_statement(rows: list) -> str:
    """The installed rows, counted by lock file, then the requirement ranges whose floor is vulnerable:
    a range admits a vulnerable version without saying one is installed."""
    locked = [r for r in rows if not _floating(r)]
    ranges = [r for r in rows if _floating(r)]
    parts = []
    if locked:
        versions = {}   # one entry per package version, with every file that pins it, in the rows' order
        for r in locked:
            versions.setdefault((r["name"], r["version"]), []).append(r)
        listed = "; ".join(f"{same[0]['name']} {same[0]['version']} ({_vuln_ref(same[0])}) in {same[0]['source']}"
                           + (f" and {_plural(len(same) - 1, 'more file')}" if len(same) > 1 else "") for same in list(versions.values())[:3])
        more = f" and {len(versions) - 3} more" if len(versions) > 3 else ""
        names = len({r["name"] for r in locked})
        places = f" in {len(locked)} places across " if len(locked) != names else " in "
        parts.append(f"{_plural(names, 'vulnerable package')}{places}{deps.files_phrase(r['source'] for r in locked)}: {listed}{more}.")
    if ranges:
        def one(r):
            if r.get("requirement") is None:
                return f"{r['name']} {r['version']} in {r['source']}, a requirement file that may name only the lowest version it admits ({_vuln_ref(r)})"
            return f"{r['name']}{r['requirement'] or ' (any version)'} in {r['source']}, whose floor {r['version']} is vulnerable ({_vuln_ref(r)})"
        listed = "; ".join(one(r) for r in ranges[:3])
        more = f" and {len(ranges) - 3} more" if len(ranges) > 3 else ""
        verb = "admits" if len(ranges) == 1 else "admit"
        parts.append(f"{_plural(len(ranges), 'requirement range')} {verb} a vulnerable version: {listed}{more}.")
    return " ".join(parts)


def _vuln_evidence(r: dict) -> dict:
    out = {"name": r["name"], "version": r["version"], "source": r["source"], "score": r.get("score"),
           "fixed": r.get("fixed") or None, "ids": list(r.get("ids") or []),
           "aliases": list(r.get("aliases") or []), "malicious": bool(r.get("malicious")),
           "imported": r.get("imported", "unknown"), "deploys": list(r.get("deploys") or [])[:3],
           **({"runtime": r["runtime"]} if isinstance(r.get("runtime"), bool) else {}),
           **({"via": r["via"]} if r.get("runtime") is True and r.get("via") else {})}
    if _floating(r):   # the version is the range's floor, not an installed one
        out = {**{k: v for k, v in out.items() if k != "version"}, "floor": r["version"], "requirement": r.get("requirement")}
    return out


def _vuln_rows(report: dict) -> list:
    """(rule id, severity, title, rows) for each group of vulnerable rows: the source tree's, and the ones
    only under tests, examples, docs or vendored code. Each row carries `deploys`, what declares that its
    lock ships (deps.deploys), and the rows are in the order the finding names them: critical ones first,
    a malicious package leading, then by reach (_vuln_reach: a version the lock installs for running that
    the source imports, then one it installs for running, then one only development dependencies reach),
    then the ones with a fixed version before the ones without, then by score. The grade does not move
    with the reach. The finding and its SARIF results read the same rows."""
    scan = report.get("dependencies") or {}
    rows = scan.get("vulnerable") or []
    if not rows:
        return []
    vendored = filetypes.vendor_dirs(report)
    tree, builds = report.get("tree"), scan.get("compose_builds") or ()
    sources = {s.get("path"): s for s in scan.get("sources") or []}
    shipped = {}

    def ships(r):
        src = r.get("source") or ""
        if src not in shipped:
            shipped[src] = deps.deploys(sources.get(src) or {"path": src}, tree, builds)
        return shipped[src]
    rows = [{**r, "deploys": ships(r)} for r in rows]

    def aside(r):
        p = r.get("source") or ""
        return filetypes.is_test_path(p) or filetypes.is_sample_path(p) or filetypes.is_doc_path(p) or filetypes.is_vendored(p, vendored)
    out = []
    for rid, group, title in (("vulnerable_dependencies", [r for r in rows if not aside(r)], "Vulnerable dependencies"),
                              ("vulnerable_dependencies_aside", [r for r in rows if aside(r)], "Vulnerable dependencies only in test, example or vendored lock files")):
        if group:
            group.sort(key=lambda r: (not _vuln_critical(r), not r.get("malicious"), _vuln_reach(r), not r.get("fixed"),
                                      -(r["score"] if r.get("score") is not None else -1), r["name"], r["source"]))
            out.append((rid, _vuln_severity(rid, group), title, group))
    return out


def _vuln_reach(r: dict) -> int:
    """0 for a row the lock installs for running (`runtime` not false) that the source imports, 1 for one
    it installs for running, or whose lock does not say, 2 for one only development dependencies reach."""
    if r.get("runtime") is False:
        return 2
    return 0 if r.get("imported") is True else 1


def _vuln_critical(r: dict) -> bool:
    """A malicious package anywhere; or an installed version an advisory scores in the critical band, pinned
    by a lock that declares it ships (a Dockerfile, a Helm chart, a compose build, an entry point...)."""
    return bool(r.get("malicious")) or (not _floating(r) and r.get("score") is not None and r["score"] >= CRITICAL_SCORE and bool(r.get("deploys")))


def _vuln_severity(rid: str, group: list) -> str:
    """A note aside; else critical when a row is (_vuln_critical), and a warning otherwise: a library's or a
    development workspace's lock pins what its own developers install, not what anyone runs."""
    if rid == "vulnerable_dependencies_aside":
        return "info"
    return "critical" if any(_vuln_critical(r) for r in group) else "warning"


def vulnerable_dependencies(report: dict) -> list:
    """Packages in the lock files with a known vulnerability, from the offline osv-scanner scan. In the source
    tree, a malicious package is critical, and so is one an advisory scores in the critical band when its lock
    file's directory (or a workspace member it pins) declares that it ships; the rest are a warning. One
    pinned only by a lock file under tests, examples, docs or vendored code is a note. A pip requirement range
    whose floor is vulnerable is said as a range, not as an installed version. The advice names the package
    to upgrade first and the version that fixes it."""
    out = []
    for rid, sev, title, group in _vuln_rows(report):
        locked = [r for r in group if not _floating(r)]
        worst = (locked or group)[0]
        if worst.get("malicious"):
            target = f"Remove {worst['name']} {worst['version']} from {worst['source']} first; {_malicious_id(worst)} lists it as malicious, so no version fixes it."
        elif _floating(worst):
            target = f"Raise the floor of {worst['name']} to {worst['fixed']} in {worst['source']} first" if worst.get("fixed") else f"Look at {worst['name']} in {worst['source']} first, which has no fixed version yet"
            target += f"; its floor scores {worst['score']:.1f}." if worst.get("score") is not None else "."
        else:
            target = f"Upgrade {worst['name']} to {worst['fixed']} in {worst['source']} first" if worst.get("fixed") else f"Look at {worst['name']} in {worst['source']} first, which has no fixed version yet"
            target += f"; it scores {worst['score']:.1f}" if worst.get("score") is not None else ""
            target += f", and {_deploy_phrase(worst['deploys'])} ships that lock." if worst.get("deploys") else "."
        statement = _vuln_statement(group)
        unshipped = sorted({r["source"] for r in locked if not r.get("deploys") and r.get("score") is not None and r["score"] >= CRITICAL_SCORE})
        if sev == "warning" and unshipped:
            where = unshipped[0] + (f" and {_plural(len(unshipped) - 1, 'more lock file')}" if len(unshipped) > 1 else "")
            statement += (f" A critical score in {where} is a warning here, as nothing in "
                          f"{'its directory' if len(unshipped) == 1 else 'their directories'} declares a deployment (a Dockerfile, a Helm chart, a compose build, an entry point).")
        ranges = [r for r in group if _floating(r)]
        evidence = {"lock_files": len({r["source"] for r in locked if not deps.is_requirement_file(r["source"])}),
                    "names": len({r["name"] for r in locked}), "places": len(locked), "packages": [_vuln_evidence(r) for r in locked[:10]]}
        if ranges:
            evidence["requirements"] = [_vuln_evidence(r) for r in ranges[:10]]
        out.append(_f(sev, title, statement, f"{target} {IGNORE_DEPS}",
                      rule={"id": "vulnerable_dependencies" if rid == "vulnerable_dependencies" else "vulnerable_dependencies_aside", "critical_score": CRITICAL_SCORE,
                            "malicious_prefix": MALICIOUS_PREFIX, "critical_needs": "a deploy declaration beside the lock"},
                      evidence=evidence))
    return out


def _deploy_phrase(reasons: list) -> str:
    return reasons[0] + (f" (and {len(reasons) - 1} more)" if len(reasons) > 1 else "")


def _files_list(items: list, n: int = 3) -> str:
    return textfmt.join_and(items[:n]) + (f" and {len(items) - n} more" if len(items) > n else "")


def hygiene_findings(report: dict) -> list:
    """The hygiene checks (hygiene.py), one finding per rule, each naming the OpenSSF Scorecard check it
    stands in for without the GitHub API. Nothing for an output directory from before the step."""
    h = _swept_hygiene(report)
    out = []
    for check in (_hygiene_actions, _hygiene_pwn_request, _hygiene_injection, _hygiene_lockfiles, _hygiene_updates, _hygiene_presence, _hygiene_confusion, _hygiene_install, _hygiene_binaries, _hygiene_submodules, _hygiene_symlinks, _hygiene_trojan,
                  _hygiene_unused, _hygiene_licence, _hygiene_copyleft):
        check(h, out)
    return out


def _swept_hygiene(report: dict) -> dict:
    """The hygiene record with the lock file drift that only sweeping commits explain left out (_drift_past_sweeps)."""
    h = report.get("hygiene") or {}
    swept = [c["hash"] for c in (report.get("activity") or {}).get("sweeping") or [] if c.get("hash")]
    if swept and (h.get("lockfiles") or {}).get("drift"):
        h = {**h, "lockfiles": _drift_past_sweeps(h["lockfiles"], swept)}
    return h


def drift_rows(report: dict) -> list:
    """The drift rows lockfile_drift names, every one the hygiene step kept: what --baseline compares (gate.py)
    and where SARIF places the finding."""
    return (_swept_hygiene(report).get("lockfiles") or {}).get("drift") or []


def lockfile_drift(report: dict) -> list:
    """The lockfile_drift finding alone, which --baseline runs again over the manifests its baseline lacked."""
    out = []
    _hygiene_lockfiles(_swept_hygiene(report), out)
    return [f for f in out if f["rule"]["id"] == "lockfile_drift"]


def trojan_source(report: dict) -> list:
    """The trojan_source finding alone, which --baseline runs again over the characters and tokens its baseline lacked."""
    out = []
    _hygiene_trojan(report.get("hygiene") or {}, out)
    return out


def trojan_identities(rows: dict) -> list:
    """[(identity, row)] for a trojan record's rows ({"bidi": [...], "mixed_script": [...]}, the hygiene step's or a
    finding's evidence): a row is its file, its character or token, and which occurrence of that one in that file it
    is, in file order - never its line, so an edit above it moves nothing. What --baseline compares (gate.py) and
    what a SARIF result's fingerprint keys on, so the gate and code scanning agree on which row is new."""
    out, seen = [], {}
    for kind, what in (("bidi", "char"), ("mixed_script", "token")):
        for r in rows.get(kind) or []:
            key = (kind, r.get("file"), r.get(what))
            seen[key] = seen.get(key, 0) + 1
            out.append((key + (seen[key],), r))
    return out


def unpinned_actions(report: dict) -> list:
    """The unpinned_actions finding alone, which --baseline runs again over the rows its baseline lacked."""
    out = []
    _hygiene_actions(report.get("hygiene") or {}, out)
    return out


def _hygiene_actions(h: dict, out: list) -> None:
    a = h.get("actions") or {}
    if a.get("unpinned"):
        n, total = a.get("unpinned_count", len(a["unpinned"])), a.get("unpinned_count", len(a["unpinned"])) + (a.get("pinned") or 0)
        by_file = {}
        for u in a["unpinned"]:
            if u["uses"] not in by_file.setdefault(u["file"], []):
                by_file[u["file"]].append(u["uses"])
        listed = "; ".join(f"{textfmt.join_and(v[:3])}{' and more' if len(v) > 3 else ''} in {k}" for k, v in list(by_file.items())[:3])
        ranked = [u for _, u in sorted(enumerate(a["unpinned"]), key=lambda iu: _action_rank(iu, a.get("origin")))]
        rule = {"id": "unpinned_actions", "scorecard": "Pinned-Dependencies"}
        if all("ref" in u for u in a["unpinned"]):
            rule["order"] = ACTION_ORDER
            rows = list({(u["file"], u["uses"]): {"file": u["file"], "uses": u["uses"]} for u in ranked}.values())[:hygiene.CAP]
        else:   # an output directory from before the rows said what each step is handed: its evidence as it was
            rows = [{"file": u["file"], "uses": u["uses"]} for u in a["unpinned"][:10]]
        out.append(_f("warning", "Actions pinned by tag or branch",
                      f"{n} of {total} workflow steps use an action by tag or branch: {listed}. Whoever controls the action can move the tag to other code.",
                      f"Pin {ranked[0]['uses']} to a full commit SHA first, with the tag in a comment; Dependabot and Renovate keep such pins current.",
                      rule=rule, evidence={"count": n, "pinned": a.get("pinned", 0), "unpinned": rows}))


def _workflow_rows(rows: list) -> list:
    """The rows of a workflow shape as evidence: each names its file, job, line (`start`, where SARIF places it)
    and field."""
    return [{"file": r["file"], "start": r["line"], "job": r.get("job"), "field": r["field"], **({"key": r["key"]} if r.get("key") else {})}
            for r in rows[:10]]


def _hygiene_pwn_request(h: dict, out: list) -> None:
    a = h.get("actions") or {}
    rows = a.get("pwn_request")
    if not rows:
        return
    n = a.get("pwn_request_count", len(rows))
    listed = "; ".join(f"job {r['job']} in {r['file']}, line {r['line']} ({r['key']}: {r['field']})" for r in rows[:3])
    triggers = sorted({t for r in rows for t in r.get("triggers") or []})
    out.append(_f("warning", "Workflows that run a pull request's code with secrets",
                  f"{_plural(n, 'checkout step')} under {textfmt.join_and(triggers)} fetch{'es' if n == 1 else ''} the pull request's head: {listed}. "
                  "These triggers run with the base repository's secrets and a token that can write, so code from a fork that a later "
                  "step builds or runs gets them too. gitmole reads the checkout's own ref: and repository: only, not a value passed in "
                  "through env: or a step output.",
                  f"Build the pull request in a workflow on pull_request, which gets no secrets, and hand its results to the privileged one as an "
                  f"artifact it reads as data; or drop the ref: in {rows[0]['file']} so the checkout is the base branch.",
                  rule={"id": "pwn_request", "scorecard": "Dangerous-Workflow", "triggers": ["pull_request_target", "workflow_run"]},
                  evidence={"count": n, "files": _workflow_rows(rows)}))


def _hygiene_injection(h: dict, out: list) -> None:
    a = h.get("actions") or {}
    rows = a.get("injection")
    if not rows:
        return
    n = a.get("injection_count", len(rows))
    listed = "; ".join(f"{r['field']} at {r['file']}:{r['line']}" + (f" (job {r['job']})" if r.get("job") else "") for r in rows[:3])
    first = rows[0]
    out.append(_f("warning", "Workflow scripts that paste in text an outsider writes",
                  f"{_plural(n, 'run: script')} put{'s' if n == 1 else ''} an event field someone outside the project can write (a title, a body, a branch name, a "
                  f"commit message) straight into the shell: {listed}. Actions pastes the text in before the shell parses the script, so a title or a branch "
                  "name can carry commands. gitmole sees the direct case only, not a value passed through env: or a step output.",
                  f"Pass the field through an environment variable and quote that in the script (env: VALUE: ${{{{ {first['field']} }}}}, then "
                  f"\"$VALUE\"), starting at {first['file']}:{first['line']}.",
                  rule={"id": "expression_injection", "scorecard": "Dangerous-Workflow", "sees": "direct ${{ }} in run: only"},
                  evidence={"count": n, "files": _workflow_rows(rows)}))


def _drift_past_sweeps(lf: dict, swept: list) -> dict:
    """The lock file drift without the manifest changes the report leaves out of every count as sweeping
    (a module rename across the tree is not a dependency change): each drift dated by its newest change
    that is not a sweep, and dropped when every change was one. A drift from before the changes were
    recorded, or whose recorded changes ran out before a non-sweeping one, is kept as it is."""
    kept = []
    for d in lf["drift"]:
        changes = d.get("changes")
        rest = [c for c in changes or [] if not any(c["commit"].startswith(s) for s in swept)]
        if changes is None or (not rest and d.get("more")):
            kept.append(d)
        elif rest:
            kept.append({**d, "manifest_date": rest[0]["date"], "changes": rest})
    dropped = len(lf["drift"]) - len(kept)
    return {**lf, "drift": kept, "drift_count": lf.get("drift_count", len(lf["drift"])) - dropped}


def _drift_row(d: dict) -> dict:
    """One drift for the evidence, naming the change that dates it rather than listing them all."""
    row = {k: v for k, v in d.items() if k not in ("changes", "more")}
    if d.get("changes"):
        row["commit"] = d["changes"][0]["commit"]
    return row


def _action_trust(uses: str, origin) -> int:
    """How far an action's owner sits from the repository, nearest last: another account's action (0)
    before one from the account the repository itself lives under on GitHub (1), before GitHub's own
    actions/ and github/ (2). Without an origin on github.com, only GitHub's own come last."""
    owner = uses.split("/", 1)[0]
    if owner in ("actions", "github"):
        return 2
    home = origin or {}
    return 1 if home.get("host") == "github.com" and owner.lower() == (home.get("owner") or "").lower() else 0


# The order unpinned steps are pinned in, first to last: owner trust (_action_trust), then a branch-shaped ref before a
# release-shaped one, then a step handed a secret or a token that can write before one that is not, then the file
# order. A row from before hygiene recorded ref, secrets and grants ties on the middle two, so the order is as it was.
ACTION_ORDER = ["owner", "branch ref", "secrets or write grants", "file order"]


def _action_rank(iu: tuple, origin) -> tuple:
    i, u = iu
    return (_action_trust(u["uses"], origin), u.get("ref") != "branch", not (u.get("secrets") or u.get("grants")), i)


def _hygiene_lockfiles(h: dict, out: list) -> None:
    lf = h.get("lockfiles") or {}
    if lf.get("drift"):
        d = lf["drift"]
        listed = "; ".join(f"{x['manifest']} changed on {x['manifest_date']}, after {x['lockfile']} last did on {x['lockfile_date']}" for x in d[:3])
        out.append(_f("warning", "Lock files behind their manifests", f"{_plural(lf.get('drift_count', len(d)), 'manifest')} changed after the lock file that pins it: {listed}.",
                      f"Regenerate {d[0]['lockfile']} and commit it with the manifest; a frozen install does not catch this.",
                      rule={"id": "lockfile_drift", "by": "last commit time"},
                      evidence={"count": lf.get("drift_count", len(d)), "drift": [_drift_row(x) for x in d[:10]]}))
    if lf.get("missing"):
        m = lf["missing"]
        listed = "; ".join(f"{x['manifest']} has no {x['expected'][0]}" for x in m[:3])
        out.append(_f("info", "Manifests without a lock file", f"{listed}{' and ' + str(len(m) - 3) + ' more' if len(m) > 3 else ''}.",
                      "Commit the lock file so every install resolves the same versions, and the vulnerability scan can read them.",
                      rule={"id": "lockfile_missing", "scorecard": "Pinned-Dependencies"}, evidence={"missing": m[:10]}))


def _hygiene_updates(h: dict, out: list) -> None:
    up = h.get("updates") or {}
    if up.get("uncovered"):
        names = textfmt.join_and(up["uncovered"])
        locked = [e for e in up["uncovered"] if e != hygiene.ACTIONS_ECOSYSTEM]
        if up.get("tool") and len(locked) < len(up["uncovered"]):   # github-actions: the workflows' actions, not a lock file
            uses = f"{hygiene.ACTIONS_ECOSYSTEM}, whose actions the workflows here use"
            statement = (f"dependabot.yml covers {textfmt.join_and(up['covered']) or 'nothing'} but not "
                         + (f"{textfmt.join_and(locked)}, which have lock files here, nor {uses}." if locked else f"{uses}."))
        elif up.get("tool"):
            statement = f"dependabot.yml covers {textfmt.join_and(up['covered']) or 'nothing'} but not {names}, which have lock files here."
        else:
            statement = f"No dependency update tool is declared for {names}, which have lock files here."
        out.append(_f("info", "Dependencies without an update tool", statement,
                      f"Add a package-ecosystem entry for {up['uncovered'][0]} to .github/dependabot.yml, or a renovate.json.",
                      rule={"id": "dependency_updates", "scorecard": "Dependency-Update-Tool"}, evidence=dict(up)))


def _hygiene_presence(h: dict, out: list) -> None:
    pr = h.get("presence") or {}
    if pr and (not pr.get("license") or not pr.get("security_policy") or pr.get("codeowners_missing")):
        parts = []
        if not pr.get("license"):
            parts.append("No licence file at the root")
        if not pr.get("security_policy"):
            parts.append("no security policy (SECURITY.md)" if parts else "No security policy (SECURITY.md)")
        missing = pr.get("codeowners_missing") or []
        if missing:
            parts.append(f"{pr['codeowners']} names {_plural(len(missing), 'path')} that {'matches' if len(missing) == 1 else 'match'} no tracked file: {_files_list(missing)}")
        advice = ("Add a LICENSE; without one nobody may reuse the code." if not pr.get("license") else
                  "Add a SECURITY.md that says how to report a vulnerability privately." if not pr.get("security_policy") else
                  f"Remove or fix {missing[0]} in {pr['codeowners']}; a stale owner line assigns reviews to nothing.")
        out.append(_f("info", "Repository policy files", "; ".join(parts) + ".", advice,
                      rule={"id": "repo_policy", "scorecard": "Security-Policy, License"}, evidence=dict(pr)))


def _hygiene_confusion(h: dict, out: list) -> None:
    cf = h.get("confusion") or {}
    if cf.get("scoped_public") or cf.get("registries") or cf.get("pip_extra_index"):
        parts = [f"{x['package']} resolved from {x['registry']} in {x['lockfile']}, though .npmrc sends {x['package'].split('/')[0]} to {x['declared']}"
                 for x in (cf.get("scoped_public") or [])[:3]]
        parts += [f"{k} mixes {textfmt.join_and(v)}" for k, v in list((cf.get("registries") or {}).items())[:2]]
        if cf.get("pip_extra_index"):
            parts.append(f"{_files_list(cf['pip_extra_index'])} {'adds' if len(cf['pip_extra_index']) == 1 else 'add'} a pip extra-index-url, which lets a public package shadow a private one")
        sev = "warning" if cf.get("scoped_public") else "info"
        advice = (f"Reinstall {cf['scoped_public'][0]['package']} from {cf['scoped_public'][0]['declared']} and check the published copy is yours."
                  if cf.get("scoped_public") else "Use one index per package: --index-url for the private one, or a scoped registry, rather than an extra index.")
        out.append(_f(sev, "Dependency confusion shapes", "; ".join(parts) + ".", advice,
                      rule={"id": "dependency_confusion"}, evidence={"scoped_public": (cf.get("scoped_public") or [])[:10],
                                                                    "registries": cf.get("registries") or {}, "pip_extra_index": cf.get("pip_extra_index") or []}))


# how each package manager installs without running install scripts: the one the repository declares
# (packageManager) or locks with, since `npm ci` does nothing for a pnpm or Yarn workspace
_NO_SCRIPTS = {"npm": "Install with scripts disabled where the build allows it (npm ci --ignore-scripts)",
               "pnpm": "Install with scripts disabled where the build allows it (pnpm install --frozen-lockfile --ignore-scripts)",
               "yarn": "Install with scripts disabled where the build allows it (yarn install --frozen-lockfile --ignore-scripts)",
               "yarn-berry": "Install with scripts disabled where the build allows it (enableScripts: false in .yarnrc.yml)",
               "bun": "Install with scripts disabled where the build allows it (bun install --frozen-lockfile --ignore-scripts)"}


def _hygiene_install(h: dict, out: list) -> None:
    ins = h.get("install") or {}
    if ins.get("lockfile") or ins.get("manifests") or ins.get("setup_py"):
        parts = []
        if ins.get("lockfile"):
            n = ins.get("lockfile_count", len(ins["lockfile"]))
            parts.append(f"{n} locked package{'s' if n != 1 else ''} {'runs' if n == 1 else 'run'} an install script ({_files_list([x['package'] for x in ins['lockfile']])})")
        parts += [f"{m['file']} declares {textfmt.join_and(m['scripts'])}" for m in (ins.get("manifests") or [])[:3]]
        parts += [f"{s_['file']} calls {textfmt.join_and(s_['calls'])}" for s_ in (ins.get("setup_py") or [])[:3]]
        # the advice of the ecosystem the finding names: npm's switch does nothing to a setup.py, which pip runs whenever it builds from source
        manager = (ins.get("manager") or {}).get("name")
        npm = f"{_NO_SCRIPTS.get(manager, _NO_SCRIPTS['npm'])} and review what the rest run."
        pip = (f"Review what {ins['setup_py'][0]['file']} runs: pip runs it on every install from source; "
               "a wheel install (pip install --only-binary :all:) does not.") if ins.get("setup_py") else ""
        advice = pip if not (ins.get("lockfile") or ins.get("manifests")) else f"{npm} {pip}".strip()
        out.append(_f("info", "Code that runs at install", "; ".join(parts) + ".", advice,
                      rule={"id": "install_scripts"}, evidence={k: ins.get(k) for k in ("lockfile", "manifests", "setup_py")}))


def _hygiene_binaries(h: dict, out: list) -> None:
    b = h.get("binaries") or {}
    exe = [x for x in b.get("executables") or [] if not _aside_path(x["file"])]
    if exe or b.get("lfs_unpointed"):
        parts = []
        if exe:
            named = [f"{x['file']} ({x['format']})" for x in exe]
            parts.append(f"{_plural(len(exe), 'executable')} committed: {_files_list(named)}")
        lfs = b.get("lfs_unpointed") or []
        if lfs:
            parts.append(f"{_files_list(lfs)} {'is' if len(lfs) == 1 else 'are'} committed as a blob though .gitattributes sends {'it' if len(lfs) == 1 else 'them'} to LFS")
        out.append(_f("warning" if exe else "info", "Committed binaries", "; ".join(parts) + ".",
                      f"Build {exe[0]['file']} in CI and publish it as a release asset instead; nobody can review a binary in a diff." if exe
                      else "Run git lfs migrate import for those paths, or drop the filter=lfs line that does not apply.",
                      rule={"id": "committed_binaries", "scorecard": "Binary-Artifacts"}, evidence={"executables": exe[:10], "lfs_unpointed": lfs[:10]}))


def _hygiene_submodules(h: dict, out: list) -> None:
    sm = h.get("submodules") or {}
    if sm.get("credentials") or sm.get("insecure") or sm.get("relative") or sm.get("floating"):
        parts = [f"{x['name']} carries credentials in its URL" for x in sm.get("credentials") or []]
        parts += [f"{x['name']} is fetched over {x['url'].split(':', 1)[0]}://" for x in sm.get("insecure") or []]
        parts += [f"{x['name']} has a relative URL ({x['url']})" for x in sm.get("relative") or []]
        parts += [f"{x['name']} follows branch {x['branch']}" for x in sm.get("floating") or []]
        sev = "critical" if sm.get("credentials") else "warning" if sm.get("insecure") else "info"
        advice = ("Rotate that credential and remove it from .gitmodules; history keeps it." if sm.get("credentials") else
                  "Switch those URLs to https://; a plain-text fetch can be rewritten on the way." if sm.get("insecure") else
                  "Use absolute https:// URLs and let the pinned commit, not a branch, say what is checked out.")
        out.append(_f(sev, "Submodule URLs", "; ".join(parts[:6]) + ".", advice, rule={"id": "submodule_urls"},
                      evidence={k: sm.get(k) or [] for k in ("credentials", "insecure", "relative", "floating")}))


def _hygiene_symlinks(h: dict, out: list) -> None:
    sl = h.get("symlinks") or {}
    if sl.get("outside") or sl.get("into_git"):
        parts = [f"{x['link']} points outside the tree ({x['target']})" for x in sl.get("outside") or []]
        parts += [f"{x['link']} points into .git ({x['target']})" for x in sl.get("into_git") or []]
        out.append(_f("warning", "Symlinks out of the tree", "; ".join(parts[:5]) + ".",
                      "Replace them with files or relative links inside the tree; a checkout that follows them reads or writes where it should not.",
                      rule={"id": "unsafe_symlinks"}, evidence={"outside": sl.get("outside") or [], "into_git": sl.get("into_git") or []}))


def _hygiene_trojan(h: dict, out: list) -> None:
    tj = h.get("trojan") or {}
    if tj.get("bidi") or tj.get("mixed_script"):
        parts = [f"{x['file']}:{x['line']} holds {x['char']}" for x in (tj.get("bidi") or [])[:3]]
        parts += [f"{x['token']} at {x['file']}:{x['line']} mixes {textfmt.join_and(x['scripts'])}" for x in (tj.get("mixed_script") or [])[:3]]
        sev = "critical" if tj.get("bidi") else "warning"
        first = (tj.get("bidi") or tj.get("mixed_script"))[0]
        out.append(_f(sev, "Trojan Source characters", "; ".join(parts) + ". Code can read one way in review and compile another.",
                      f"Look at {first['file']}:{first['line']} in a hex view first, and remove the character unless it is in a string that must hold it.",
                      rule={"id": "trojan_source", "cve": "CVE-2021-42574"},
                      evidence={"bidi": (tj.get("bidi") or [])[:10], "mixed_script": (tj.get("mixed_script") or [])[:10]}))


def _hygiene_unused(h: dict, out: list) -> None:
    im = h.get("imports") or {}
    rows = im.get("unused") or []
    if not rows:
        return
    by_manifest = {}
    for r in rows:
        by_manifest.setdefault(r["manifest"], []).append(r["package"])
    listed = "; ".join(f"{_files_list(v)} in {k}" for k, v in list(by_manifest.items())[:3])
    n = im.get("count", len(rows))
    first = rows[0]
    out.append(_f("info", "Declared dependencies nothing imports",
                  f"{n} runtime {'dependency is' if n == 1 else 'dependencies are'} declared and never imported by a tracked file, nor named in a script or configuration: {listed}.",
                  f"Remove {first['package']} from {first['manifest']} if nothing loads it at run time; an unused dependency is still installed, scanned and updated.",
                  rule={"id": "unused_dependencies", "reads": "package.json dependencies, go.mod direct requirements, Cargo.toml [dependencies]"},
                  evidence={"count": n, "manifests": im.get("manifests", 0), "unused": rows[:10]}))


def _hygiene_licence(h: dict, out: list) -> None:
    lic = h.get("licences") or {}
    declared = lic.get("declared") or []
    if lic.get("approved") is False or lic.get("mismatch"):
        named = "; ".join(f"{d['source']} declares {d['expression']}" for d in declared)
        parts = []
        if lic.get("mismatch"):
            parts.append(f"{named}, but {lic['files'][0]} is the {lic['file_licence']} text")
        if lic.get("approved") is False:
            parts.append(f"the declared licence ({textfmt.join_and([d['expression'] for d in declared] or [lic.get('file_licence') or ''])}) is not OSI- or FSF-approved")
        out.append(_f("warning" if lic.get("approved") is False else "info", "Project licence as declared", "; ".join(parts) + ".",
                      "Make the manifests and the licence file name the same licence; a packager reads the manifest, a lawyer the file." if lic.get("mismatch")
                      else "Say so plainly in the README if the project is source-available rather than open source.",
                      rule={"id": "project_licence", "reads": "root manifests and the licence file"},
                      evidence={"declared": declared, "file": (lic.get("files") or [None])[0], "file_licence": lic.get("file_licence"),
                                "approved": lic.get("approved"), "mismatch": bool(lic.get("mismatch"))}))


def _hygiene_copyleft(h: dict, out: list) -> None:
    lic = h.get("licences") or {}
    strong = lic.get("strong") or []
    if not strong or lic.get("project") != licences.PERMISSIVE:
        return
    n = lic.get("strong_count", len(strong))
    listed = _files_list([f"{d['name']} {d['version']} ({d['expression']})" for d in strong])
    own = textfmt.join_and(sorted({d["expression"] for d in lic.get("declared") or []} | ({lic["file_licence"]} if lic.get("file_licence") else set())))
    weak = f" {lic['weak_count']} more declare{'s' if lic.get('weak_count') == 1 else ''} weak copyleft (LGPL, MPL, EPL), which a dependency usually may." if lic.get("weak_count") else ""
    out.append(_f("warning", "Copyleft dependencies in a permissive project",
                  f"The project declares {own}, and {n} runtime {'dependency' if n == 1 else 'dependencies'} in {textfmt.join_and(sorted({d['lockfile'] for d in strong}))} "
                  f"{'declares' if n == 1 else 'declare'} a strong copyleft licence: {listed}.{weak} Declared, as the lock file records it, not read from the package's files.",
                  f"Check whether {strong[0]['name']} is distributed with the project; if it is, its licence terms reach the whole work.",
                  rule={"id": "copyleft_dependencies", "reads": "package-lock.json and composer.lock licence fields, runtime packages only"},
                  evidence={"project": own, "count": n, "weak": lic.get("weak_count", 0), "dependencies": lic.get("dependencies", 0), "strong": strong[:10]}))


def _aside_path(path: str) -> bool:
    return filetypes.is_test_path(path) or filetypes.is_sample_path(path) or filetypes.is_vendor_path(path)


STRUCTURE_LANGUAGES = {"python", "javascript", "typescript", "tsx", "c", "cpp", "ruby", "go"}   # where the import graph resolves at all


def _structure(report: dict) -> dict:
    s = report.get("structure") or {}
    return s if s.get("status") == "run" else {}


def _scored_top(report: dict, n: int = 10) -> list:
    cls = classify.Classifier(report)
    return [h["entity"] for h in hotspots.ranked(report) if h["code"] is not None and cls.reason(h["entity"]) is None][:n]


def debt_in_hotspots(report: dict, min_markers: int = 3, min_files: int = 2, top_n: int = 10) -> list:
    """Top hotspots whose own comments say they are unfinished: TODO, FIXME, XXX, HACK. Methods carrying
    such self-admitted debt were revised more than twice as often and carried about twice the bug ratio
    (Maldonado and Shihab's markers; the 2024 study of 774,051 Java methods), and most of it is never
    removed: a hot file its authors flagged is a reason no churn number gives."""
    s = _structure(report)
    if not s:
        return []
    files = s.get("files") or {}
    top = _scored_top(report, top_n)
    flagged = [(f, files[f]["debt"]) for f in top if (files.get(f) or {}).get("debt")]
    if not flagged or (max(n for _, n in flagged) < min_markers and len(flagged) < min_files):
        return []   # one marker in one hotspot is ordinary; three in one, or markers in two, is a pattern
    first = max(flagged, key=lambda t: t[1])[0]
    sample = (files[first].get("debt_sample") or [{}])[0]
    at = f", starting at line {sample['line']}" if sample.get("line") else ""
    listed = "; ".join(f"{f} ({n})" for f, n in flagged[:5]) + (f" and {len(flagged) - 5} more" if len(flagged) > 5 else "")
    return [_f("info", "Debt the authors flagged in hotspots",
               f"{len(flagged)} of the top {len(top)} hotspots carry TODO, FIXME, XXX or HACK comments: {listed}.",
               f"Resolve or ticket the markers in {first} first{at}; it changes often and its authors said it is unfinished.",
               rule={"id": "debt_in_hotspots", "markers": ["TODO", "FIXME", "XXX", "HACK"], "min_markers": min_markers, "top_n": top_n,
                     "ref": "Maldonado and Shihab, MTD 2015"},
               evidence={"files": [{"file": f, "markers": n} for f, n in flagged[:10]]})]


def _shape_files(report: dict, key: str) -> list:
    """[(file, shapes)] for this repository's own source files holding a shape: tests, examples,
    documentation, vendored and generated files left out, since a fixture or a sample may do on purpose
    what the source should not."""
    s = _structure(report)
    if not s:
        return []
    generated, vendored = _generated(report), filetypes.vendor_dirs(report)
    return [(p, v["shapes"]) for p, v in sorted((s.get("files") or {}).items()) if (v.get("shapes") or {}).get(key)
            and not (filetypes.is_test_path(p) or filetypes.is_sample_path(p) or filetypes.is_doc_path(p)
                     or filetypes.is_vendored(p, vendored) or p in generated)]


def swallowed_errors(report: dict, min_count: int = 5, top_n: int = 10) -> list:
    """Catch, except and rescue blocks that do nothing and say nothing: no statement, no comment. In
    Python only a bare `except:` or one catching Exception or BaseException counts, since `except
    KeyError: pass` is the language's idiom. A warning when one sits in a top hotspot, where an error
    that vanishes is the hardest to trace."""
    rows = _shape_files(report, "empty_catch")
    total = sum(sh.get("empty_catch_count", len(sh["empty_catch"])) for _, sh in rows)
    if total < min_count:
        return []
    rows.sort(key=lambda r: (-r[1].get("empty_catch_count", 0), r[0]))
    top = set(_scored_top(report, top_n))
    hot = [p for p, _ in rows if p in top]
    listed = _files_list([f"{p}:{sh['empty_catch'][0]}" + (f" and {sh['empty_catch_count'] - 1} more there" if sh.get("empty_catch_count", 1) > 1 else "") for p, sh in rows])
    bare = sum(sh.get("bare_except_count", 0) for _, sh in rows)
    first = hot[0] if hot else rows[0][0]
    return [_f("warning" if hot else "info", "Errors caught and dropped",
               f"{_plural(total, 'empty catch block')} in {_plural(len(rows), 'source file')}"
               + (f", {bare} of them a bare except" if bare else "") + f": {listed}."
               + (f" {textfmt.join_and(hot[:3])} {'is a top hotspot' if len(hot) == 1 else 'are top hotspots'}." if hot else ""),
               f"Log or rethrow in {first} first, or say in a comment why the error is ignored; an error dropped without a trace is the hardest kind to find.",
               rule={"id": "swallowed_errors", "min_count": min_count, "measure": "tree-sitter", "python": "bare, Exception or BaseException only"},
               evidence={"count": total, "bare_except": bare, "hotspots": hot[:10],
                         "files": [{"file": p, "start": sh["empty_catch"][0], "count": sh.get("empty_catch_count", 1)} for p, sh in rows[:10]]})]


def hardcoded_addresses(report: dict) -> list:
    """IPv4 addresses written into string literals in source files: a host that moves, or an environment
    wired into the code. Loopback, unspecified, broadcast, netmask-shaped, documentation-range (RFC 5737)
    and object-identifier-shaped values are not counted (structure.py)."""
    rows = _shape_files(report, "addresses")
    if not rows:
        return []
    total = sum(sh.get("addresses_count", len(sh["addresses"])) for _, sh in rows)
    places = [(p, a) for p, sh in rows for a in sh["addresses"]]
    listed = _files_list([f"{a['value']} at {p}:{a['line']}" for p, a in places])
    return [_f("info", "Addresses written into the code",
               f"{_plural(total, 'IPv4 address')} in string literals in {_plural(len(rows), 'source file')}: {listed}.",
               f"Move {places[0][1]['value']} in {places[0][0]} into configuration, or a name that DNS resolves; an address in code has to be edited and shipped to change.",
               rule={"id": "hardcoded_addresses", "measure": "tree-sitter", "left_out": "loopback, 0.0.0.0, broadcast, RFC 5737, x.x.x.0, first octet 0-2"},
               evidence={"count": total, "files": [{"file": p, "start": a["line"], "value": a["value"]} for p, a in places[:10]]})]


def commented_out_code(report: dict, min_lines: int = 10) -> list:
    """Source files with ten or more lines of code left in comments: blocks of line or block comments in
    which four lines in five read as statements and one starts right at the comment marker. Worked
    examples in prose and documentation comments are not counted. The history already keeps old code."""
    rows = [(p, sh) for p, sh in _shape_files(report, "commented_code") if sh["commented_code"] >= min_lines]
    if not rows:
        return []
    rows.sort(key=lambda r: (-r[1]["commented_code"], r[0]))
    listed = _files_list([f"{p} ({sh['commented_code']} lines from line {sh['commented_sample'][0]})" for p, sh in rows])
    first = rows[0]
    return [_f("info", "Code left in comments",
               f"{_plural(len(rows), 'source file')} {'holds' if len(rows) == 1 else 'hold'} {min_lines} or more lines of commented-out code: {listed}.",
               f"Delete the block at {first[0]}:{first[1]['commented_sample'][0]}; git keeps the old version, and a reader cannot tell whether it is meant to come back.",
               rule={"id": "commented_out_code", "min_lines": min_lines, "measure": "tree-sitter", "code_share": 0.8},
               evidence={"files": [{"file": p, "start": sh["commented_sample"][0], "lines": sh["commented_code"]} for p, sh in rows[:10]]})]


def deep_rows(report: dict, min_nesting: int = 5, min_bumps: int = 3) -> list:
    """The structure step's function rows deep_nesting names, every one of them: what --baseline compares."""
    s = _structure(report)
    if not s:
        return []
    generated, vendored, inline, doubles = _generated(report), filetypes.vendor_dirs(report), _test_modules(report), _test_doubles(report)
    return [f for f in s.get("functions") or [] if (f["nesting"] >= min_nesting or f["bumps"] >= min_bumps)
            and not (filetypes.is_test_path(f["file"]) or f["file"] in doubles or filetypes.is_sample_path(f["file"]) or filetypes.is_vendored(f["file"], vendored)
                     or f["file"] in generated or filetypes.in_spans(f["start"], inline.get(f["file"])))]


def deep_nesting(report: dict, min_nesting: int = 5, min_bumps: int = 3, top_n: int = 10) -> list:
    """Functions nested five levels or more, or with three or more separate chunks of nested logic (a
    bumpy road), in this repository's own source: CodeScene's nesting and bumpy-road factors, measured
    by tree-sitter in every language it parses, with Sonar's cognitive complexity beside them. A
    warning when one sits in a top hotspot."""
    deep = deep_rows(report, min_nesting, min_bumps)
    if not deep:
        return []
    deep.sort(key=lambda f: (-f["cognitive"], -f["nesting"], f["file"], f["start"]))
    top = set(_scored_top(report, top_n))
    sev = "warning" if any(f["file"] in top for f in deep) else "info"

    def one(f):
        return f"{_called(f)} ({f['file']}:{f['start']}) nested {f['nesting']} deep, cognitive complexity {f['cognitive']}, {f['bumps']} bump{'s' if f['bumps'] != 1 else ''}"
    listed = "; ".join(one(f) for f in deep[:5]) + (f" and {len(deep) - 5} more" if len(deep) > 5 else "")
    first = next((f for f in deep if f["file"] in top), deep[0])
    which = f"the anonymous function at {first['file']}:{first['start']}" if _anonymous(first) else f"{first['name']} in {first['file']}"
    return [_f(sev, "Deeply nested code", f"{_plural(len(deep), 'function')} nest {min_nesting} levels or more or carry {min_bumps}+ separate nested chunks: {listed}.",
               f"Flatten {which} first: return early and move each nested chunk into a function of its own.",
               rule={"id": "deep_nesting", "min_nesting": min_nesting, "min_bumps": min_bumps, "measure": "tree-sitter",
                     "ref": "SonarSource cognitive complexity; CodeScene code health"},
               evidence={"count": len(deep), "functions": [{k: f[k] for k in ("file", "name", "start", "nesting", "cognitive", "bumps")} for f in deep[:10]]})]


def hidden_coupling(report: dict, min_degree: int = 60, min_revs: int = 5, min_resolved: float = structure.MIN_RESOLVED) -> list:
    """Pairs that change together without an import between them, in either direction. Ajienka and
    Capiluppi found across 79 projects that many co-changed pairs have no structural dependency at
    all: such a pair is a shared format, a duplicated rule or copy-paste, and neither a pure-git nor a
    pure-static tool can print it. Only for languages whose imports this graph mostly resolves, and not
    for a pair that is example or documentation material on both sides (_both_specimens). Two Go files in
    one directory are one package and see each other with no import, so they are not a hidden pair."""
    s = _structure(report)
    if not s:
        return []
    files, resolved, tree = s.get("files") or {}, s.get("resolved") or {}, _tree(report)
    derived = _generated(report)

    def graphed(p):
        info = files.get(p)
        return info is not None and info.get("language") in STRUCTURE_LANGUAGES and resolved.get(info["language"], 0) >= min_resolved

    hidden = []
    for p in report.get("coupling") or []:
        a, b = p["entity"], p["coupled"]
        if p["degree"] < min_degree or p["average-revs"] < min_revs or not (graphed(a) and graphed(b)):
            continue
        if filetypes.is_test_path(a) or filetypes.is_test_path(b) or filetypes.is_header_pair(a, b) or a in derived or b in derived:
            continue
        if _both_specimens(a, b):
            continue
        if tree and (a not in tree or b not in tree):
            continue
        if b in (files[a].get("imports") or []) or a in (files[b].get("imports") or []):
            continue
        if files[a].get("language") == files[b].get("language") == "go" and os.path.dirname(a) == os.path.dirname(b):
            continue   # one Go package: its files share every name without an import, as the language defines a package
        hidden.append(p)
    if not hidden:
        return []
    hidden.sort(key=lambda p: (-p["degree"], -p["average-revs"], p["entity"]))
    listed = "; ".join(f"{p['entity']} and {p['coupled']} change together {p['degree']}% of the time, and neither imports the other" for p in hidden[:3])
    more = f" ({_plural(len(hidden) - 3, 'more pair')} like them)" if len(hidden) > 3 else ""
    first = hidden[0]
    return [_f("info", "Coupling with no import behind it", f"{listed}{more}.",
               f"Look at why {first['entity']} and {first['coupled']} move together: a shared format, a duplicated rule or copied code is the usual answer.",
               rule={"id": "hidden_coupling", "min_degree": min_degree, "min_revs": min_revs, "min_resolved": min_resolved,
                     "ref": "Ajienka and Capiluppi, JSS 2017"},
               evidence={"pairs": [{"a": p["entity"], "b": p["coupled"], "degree": p["degree"], "revs": p["average-revs"]} for p in hidden[:10]]})]


# Go's compiler refuses an import loop between packages, so a loop through Go files in this graph (an edge runs to every
# file of a package, whatever its build tags) could only be the graph's mistake
NO_CYCLES = {"go"}
DEFERRED_MARKS_FROM = 4   # the structure analyser that first marked deferred imports; an older structure.json would show loops broken on purpose


def _groups(edges: dict) -> list:
    """The strongly connected components of two files or more, by Tarjan's algorithm, iterative so a
    deep graph does not reach the recursion limit; each sorted, and visited in sorted order so the
    same graph gives the same groups."""
    index, low, on, stack, out, n = {}, {}, set(), [], [], 0
    for root in sorted(edges):
        if root in index:
            continue
        work = [(root, iter(edges[root]))]
        index[root] = low[root] = n
        n += 1
        stack.append(root)
        on.add(root)
        while work:
            node, it = work[-1]
            for nxt in it:
                if nxt not in index:
                    index[nxt] = low[nxt] = n
                    n += 1
                    stack.append(nxt)
                    on.add(nxt)
                    work.append((nxt, iter(edges[nxt])))
                    break
                if nxt in on:
                    low[node] = min(low[node], index[nxt])
            else:
                work.pop()
                if work:
                    low[work[-1][0]] = min(low[work[-1][0]], low[node])
                if low[node] == index[node]:
                    group = []
                    while True:
                        p = stack.pop()
                        on.discard(p)
                        group.append(p)
                        if p == node:
                            break
                    if len(group) > 1:
                        out.append(sorted(group))
    return out


def _loop_from(edges: dict, members: set, start: str) -> list:
    """The shortest loop from `start` back to itself inside the group, by breadth-first search with
    neighbours in sorted order: [start, ..., start]; None when there is none."""
    parent, todo = {}, [start]
    while todo:
        nxt_level = []
        for node in todo:
            for nxt in edges[node]:
                if nxt == start:
                    back = [node]   # node, its parent, ..., start
                    while back[-1] != start:
                        back.append(parent[back[-1]])
                    return [*reversed(back), start]
                if nxt in members and nxt not in parent:
                    parent[nxt] = node
                    nxt_level.append(nxt)
        todo = nxt_level
    return None


def _loop(edges: dict, group: list) -> list:
    """The group's shortest loop: the shortest of the shortest loops through each member, ties to the
    member that sorts first, so what the finding names is what docs/output.md says it names."""
    members, best = set(group), None
    for start in group:
        loop = _loop_from(edges, members, start)
        if loop is not None and (best is None or len(loop) < len(best)):
            best = loop
            if len(best) == 3:
                break   # a mutual pair: nothing shorter exists
    return best or [group[0], group[0]]


def import_cycles(report: dict, min_resolved: float = structure.MIN_RESOLVED, min_files: int = structure.MIN_FILES) -> list:
    """Groups of source files that import each other, directly or round a loop, as they load: an import
    inside a function, a type-only import and a dynamic import() are left out, since they are how a
    loop is broken on purpose. Oyetoyan et al. found classes near a cycle change more often (Java, SANER
    2015) and found no rule that tells a harmful cycle from a harmless one, so this names the loops and
    leaves the verdict to the reader. Only groups holding a language structure.trusted vouches for (resolved
    by path, mostly resolved, enough files) and not Go (NO_CYCLES); tests, examples, vendored and generated
    files are left out."""
    s = _structure(report)
    if not s or int(s.get("analyser") or 0) < DEFERRED_MARKS_FROM:
        return []   # a structure.json from before the deferred marks would name the loops deferred imports break on purpose
    files, resolved, derived = s.get("files") or {}, s.get("resolved") or {}, _generated(report)
    judged = structure.trusted(files, resolved, min_resolved, min_files)
    # the graph holds every language that resolves well enough, since .ts, .tsx and .js are one module graph to
    # the loader; a group is named when a trusted language is in it, so two components in a loop with
    # TypeScript count and three lone TypeScript files do not
    keep = {p for p, info in files.items() if info.get("language") in structure.GRAPH_LANGUAGES - NO_CYCLES
            and resolved.get(info.get("language"), 0) >= min_resolved and not _aside_path(p) and p not in derived}
    edges = {p: sorted(set(t for t in files[p].get("imports") or [] if t in keep) - set(files[p].get("deferred") or [])) for p in sorted(keep)}
    groups = [g for g in _groups(edges) if any(files[p].get("language") in judged for p in g)]
    if not groups:
        return []
    groups.sort(key=lambda g: (-len(g), g[0]))
    loops = [_loop(edges, g) for g in groups]

    def said(group, loop):
        arrow = " → ".join(loop)
        return arrow if len(loop) - 1 == len(group) else f"{arrow}, one loop in a group of {len(group)} files"
    listed = "; ".join(said(g, l) for g, l in zip(groups[:3], loops[:3]))
    more = f" ({_plural(len(groups) - 3, 'more group')})" if len(groups) > 3 else ""
    n = len(groups)
    return [_f("info", "Import cycles",
               f"In {_plural(n, 'group')}, files import each other as they load: {listed}{more}.",
               f"Break {' → '.join(loops[0])} first: move what both ends need into a file neither imports, or import it where it is used.",
               rule={"id": "import_cycles", "min_resolved": min_resolved, "min_files": min_files, "ref": REFS["import_cycles"]},
               evidence={"count": n, "groups": [{"files": g[:20], "size": len(g), "loop": l} for g, l in zip(groups[:10], loops[:10])]})]


def unreferenced_files(report: dict) -> list:
    """Files nothing in the tree imports that are no entry point by convention or declaration, from the
    structure step, which already leaves out languages whose graph is too blind to judge. Never
    "dead": Romano et al. found no comprehension cost to dead code in controlled experiments, and a
    dynamic import cannot be seen from here, so this is a list to check, not to delete."""
    s = _structure(report)
    listed = s.get("unreferenced") or []
    # the structure step left test files out by the conventions of its day; one a later convention calls a test
    # (a __fixtures__/ input, a smoke/ script) is taken out here too, so a saved run reads as a new one would
    paths = [p for p in listed if not filetypes.is_test_path(p)]
    if not paths:
        return []
    n = s.get("unreferenced_count", len(listed)) - (len(listed) - len(paths))
    # a file too big to parse imports what it imports unseen: say so, in a language the list judges
    judged = {info.get("language") for p, info in (s.get("files") or {}).items() if p in set(paths)}
    unseen = [r for r in s.get("skipped") or [] if (structure.GRAMMARS.get(os.path.splitext(r.get("file") or "")[1].lower()) or ("",))[0] in judged]
    blind = (f" {_files_list([r['file'] for r in unseen], 2)} {'was' if len(unseen) == 1 else 'were'} too big to parse ({unseen[0]['reason']}), "
             f"so what {'it imports' if len(unseen) == 1 else 'they import'} is not seen.") if unseen else ""
    return [_f("info", "Possibly unreferenced files", f"{_plural(n, 'file')} {'is' if n == 1 else 'are'} imported by nothing in the tree and {'is' if n == 1 else 'are'} no entry point: {_files_list(paths, 5)}.{blind}",
               f"Check {paths[0]} before anything else; dynamic imports, plugins loaded by name and framework routing do not show in an import graph.",
               rule={"id": "unreferenced_files", "ref": "Romano et al., TSE 2020"},
               evidence={"count": n, "files": paths[:10], **({"skipped": unseen[:10]} if unseen else {})})]


def _agents(report: dict) -> dict:
    return ((report.get("provenance") or {}).get("agents")) or {}


def agent_approval_disabled(report: dict) -> list:
    """A committed agent configuration that turns approval prompts off: every clone that picks the
    settings up runs the agent's tools without asking."""
    rows = _agents(report).get("approval_disabled") or []
    if not rows:
        return []
    listed = "; ".join(f"{r['file']} sets {r['setting']}" for r in rows)
    return [_f("warning", "Agent approval prompts turned off in the repository", f"{listed}. Anyone who opens the clone with that agent runs its tools unasked.",
               "Move the setting to your personal settings file, which is not committed, and keep the shared one to what everyone should get.",
               rule={"id": "agent_approval_disabled", "by": "tracked agent settings"}, evidence={"settings": rows})]


def agent_local_settings(report: dict) -> list:
    rows = _agents(report).get("local_settings") or []
    if not rows:
        return []
    return [_f("warning", "Personal agent settings tracked", f"{_files_list(rows)} {'is' if len(rows) == 1 else 'are'} tracked; the file is meant for one machine and to stay out of git.",
               f"git rm --cached {rows[0]} and add it to .gitignore.",
               rule={"id": "agent_local_settings", "by": "path convention"}, evidence={"files": rows})]


def mcp_literal_env(report: dict) -> list:
    """An MCP server declaration whose environment holds a literal value long enough to be a
    credential rather than a ${VAR} reference. The key is named, the value never."""
    rows = [(m["file"], x) for m in _agents(report).get("mcp") or [] for x in m.get("literal_env") or []]
    if not rows:
        return []
    listed = "; ".join(f"{x['server']} sets {x['key']} in {f} to a literal value" for f, x in rows[:5])
    f0, x0 = rows[0]
    return [_f("warning", "Literal values in MCP server declarations", f"{listed}. A committed declaration shares whatever it holds.",
               f"Replace the value of {x0['key']} with ${{{x0['key']}}} and set it in the environment; rotate it if it was a live credential.",
               rule={"id": "mcp_literal_env", "min_length": 16, "placeholders": "left out"},
               evidence={"entries": [{"file": f, "server": x["server"], "key": x["key"]} for f, x in rows[:10]]})]


def agent_instructions_drift(report: dict, min_months: int = 6, min_commits: int = 100) -> list:
    """Agent instruction files (AGENTS.md and the like) far behind the code they describe. A file that only
    points at another (`points_to`, provenance.pointer_targets) is dated by the newest file it points at, and
    one under a vendored directory describes someone else's code, so it is left out. So is a skill or a
    subagent (`kind`, provenance.instruction_kind): the inventory lists them, but an agent loads one for a task
    it names, and a procedure that has not changed in six months is not thereby behind the tree."""
    last = (report.get("meta") or {}).get("last_date") or ""
    vendored = filetypes.vendor_dirs(report)
    stale = [r for r in _agents(report).get("instructions") or []
             if not r.get("kind") and last and _months_apart(r["last"], last) >= min_months and r["commits_behind"] >= min_commits
             and not filetypes.is_vendored(r["file"], vendored)]
    if not stale:
        return []

    def said(r):
        via = f"{r['file']} points at {textfmt.join_and(r['points_to'])}, which" if r.get("points_to") else r["file"]
        return f"{via} last changed on {r['last']}, {_months_apart(r['last'], last)} months and {r['commits_behind']:,} commits before the last commit"
    first = (stale[0].get("points_to") or [stale[0]["file"]])[0]
    return [_f("info", "Agent instructions behind the code", f"{'; '.join(said(r) for r in stale)}.",
               f"Read {first} against the tree and update what moved; an agent follows it literally.",
               rule={"id": "agent_instructions_drift", "min_months": min_months, "min_commits": min_commits,
                     "pointers": "dated by the files they point at", "vendored": "left out", "skills and subagents": "left out"},
               evidence={"files": stale})]


def signoff_by_co_author(report: dict, min_commits: int = 2) -> list:
    """An identity that signs off commits it co-authors but never authors one: the Linux kernel's policy
    on coding assistants forbids an agent to add Signed-off-by, since the DCO is a human's statement."""
    rows = [r for r in ((report.get("provenance") or {}).get("trailers") or {}).get("signoff_by_co_author") or [] if r["commits"] >= min_commits]
    if not rows:
        return []
    listed = "; ".join(f"{r['name']} <{r['email']}> signs off {_plural(r['commits'], 'commit')} but never authors one" for r in rows[:3])
    return [_f("info", "Sign-offs by identities that only co-author", f"{listed}.",
               "A Signed-off-by line certifies the Developer Certificate of Origin; have a person who authors commits add it.",
               rule={"id": "signoff_by_co_author", "min_commits": min_commits, "ref": "Linux kernel, Documentation/process/coding-assistants.rst"},
               evidence={"identities": rows[:10]})]


def _pool_files(report: dict) -> list:
    """The source files still in the tree that no classifier reason sets aside."""
    cls = classify.Classifier(report)
    return sorted(f for f in _tree(report) if cls.reason(f) is None)


def _authors_of(report: dict, files: list, key: str = "is_author") -> dict:
    wanted = set(files)
    out = {f: set() for f in files}
    for r in report.get("doa") or []:
        if r["entity"] in wanted and r.get(key):
            out[r["entity"]].add(r["author"])
    return out


# How well the algorithm agrees with the people who know: against the truck factors 35 systems' own developers
# gave, Avelino's algorithm was exact on 71.4% of them, and on 30% of those whose truck factor was 2 to 5.
TRUCK_FACTOR_MEASURED = "exact on 71.4% of 35 systems, 30% of those at truck factor 2 to 5 (Ferreira, Valente and Ferreira, ICPC 2017)"


TRUCK_MIN_FILES = 20   # under this many source files a truck factor is a statement about a handful of files


def truck_factor_absent(report: dict, min_files: int = TRUCK_MIN_FILES):
    """Why truck_factor() has nothing to say when that is not "nobody is a risk": too few source files, or a
    pool most of which has no author on record. None when it was computed, or when there is no file listing
    or no degree of authorship to compute it from (a step that did not finish, which the header names)."""
    if not _tree(report):
        return None
    files = _pool_files(report)
    if len(files) < min_files:
        return {"measure": "truck_factor", "label": "truck factor", "files": len(files), "min_files": min_files,
                "reason": f"{len(files)} source file{'s' if len(files) != 1 else ''}, needs {min_files}"}
    if not report.get("doa"):
        return None
    orphans = sum(1 for a in _authors_of(report, files).values() if not a)
    if 2 * orphans > len(files):   # knowledge.truck_factor's own stop: more than half orphaned before anyone leaves
        return {"measure": "truck_factor", "label": "truck factor", "files": len(files), "orphaned": orphans,
                "reason": f"{orphans} of the {len(files)} source files have no author on record"}
    return None


def not_computed(report: dict) -> list:
    """The measures this run could not make, each with why: a rule that stays silent because its precondition
    failed reads as a rule that found nothing. The truck factor below its file floor, and the backtest
    without the history (or after a failed step), which the watch list's caption already says (`said`).
    The bug magnets' size test says so inside its own finding."""
    out = []
    truck = truck_factor_absent(report)
    if truck:
        out.append(truck)
    bt = (report.get("meta") or {}).get("backtest") or {}
    if bt.get("status") == "skipped" and bt.get("reason"):
        out.append({"measure": "backtest", "label": "backtest", "reason": bt["reason"], "said": "watch list"})
    elif bt.get("status") in ("failed", "timeout"):
        out.append({"measure": "backtest", "label": "backtest", "reason": f"the step {'timed out' if bt['status'] == 'timeout' else 'failed'}", "said": "watch list"})
    return out


def truck_factor(report: dict, min_files: int = TRUCK_MIN_FILES, area_files: int = 10) -> list:
    """Avelino et al.'s truck factor over the degree of authorship: how many people have to leave before
    more than half the source files have no author. One is a warning, two a note. Changes rather than
    lines, and a creator's bonus, so it can disagree with the surviving-code share, which the bus-factor
    finding reads; the finding says so when it does. Also per area, and with knowledge halving every
    five months."""
    if not report.get("doa"):
        return []
    files = _pool_files(report)
    authored = {f: a for f, a in _authors_of(report, files).items()}
    if len(files) < min_files:
        return []
    tf, removed, share = knowledge.truck_factor(authored)
    if not removed:
        # More than half the pool has no author before anyone leaves (files an import brought in, or
        # history the clone does not hold, have no creator), so there is no truck factor and no one to name.
        return []
    tf_d, removed_d, _ = knowledge.truck_factor(_authors_of(report, files, "is_author_decayed"))
    base = scope.report_base(report)
    depth = knowledge.depth_for(files, base=base)
    areas = {}
    for f in files:
        areas.setdefault(knowledge._area(f, depth, base), []).append(f)
    lone = []
    for area, fs in sorted(areas.items()):
        if len(fs) >= area_files and area != knowledge.ROOT:
            n, who, orphaned_share = knowledge.truck_factor({f: authored[f] for f in fs})
            if n == 1:   # the area's size and what one departure orphans, so a reader can tell ten files from ten thousand
                lone.append((area, who[0], len(fs), round(orphaned_share * len(fs))))
    # most files at stake first: the list, the evidence's first ten and the advice's start area all begin where
    # one departure orphans the most, not where the alphabet does (hindsight's docker/, 9 files, over 267)
    lone.sort(key=lambda t: (-t[3], t[0]))
    if tf > 2 and not lone:
        return []
    orphans = round(share * len(files))
    gone = _gone(report)

    def names(people):
        return textfmt.join_and([_who(p, gone) for p in people])
    shares = report.get("theseus_authors") or {}
    whole = sum(shares.values())
    top, lines = max(shares.items(), key=lambda kv: kv[1]) if shares else (None, 0)
    level = sum(1 for n in shares.values() if n == lines)   # how many hold exactly the largest share
    if level > 1 and shares.get(removed[0]) == lines:
        top = removed[0]   # one of several with the largest share: theirs is still the largest, so nothing differs
    lead = names(removed)
    if tf == 1 and top == removed[0] and 2 * lines <= whole:
        # one departure orphans most files while the lines are split: the two measures differ, so the share is said where the name is
        lead = f"{top} ({'gone, ' if top in gone else ''}{_pct(lines, whole)} of the surviving code)"
    statement = (f"Truck factor {tf}: without {lead}, {orphans} of the {len(files)} source files ({_pct(orphans, len(files))}) "
                 f"have no author left.")
    left = sum(1 for p in removed if p in gone)
    if left:   # for them it is not a risk but a loss that has happened
        statement += " For those marked gone it already has."
    if tf_d != tf and not removed_d:
        statement += " With knowledge halving every five months, more than half the files already have no author."
    elif tf_d != tf and set(removed) < set(removed_d):   # the same people and some more: only the more are new
        statement += f" With knowledge halving every five months it is {tf_d}, adding {names([p for p in removed_d if p not in removed])}."
    elif tf_d != tf:
        statement += f" With knowledge halving every five months it is {tf_d} ({names(removed_d)})."
    if lone:
        statement += " Areas with a truck factor of one: " + ", ".join(f"{a} ({_who(w, gone)})" for a, w, _, _ in lone[:5]) + (f" and {len(lone) - 5} more" if len(lone) > 5 else "") + "."
    if shares and top != removed[0] and level > 1:   # no one name to give: the first in the table would be an accident of its order
        statement += f" The surviving code's largest share, {_pct(lines, whole)}, is held by {level} people equally, which the bus-factor finding reads."
    elif shares and top != removed[0]:
        statement += (f" The surviving code's largest share is {top}'s ({_pct(lines, whole)}), which the bus-factor finding reads." if top not in gone else
                      f" The surviving code's largest share, {_pct(lines, whole)}, belongs to {top} (gone), which the bus-factor finding reads.")
    # the person to pair with is the first named who is still here, on an area that is theirs
    ask = next((p for p in removed if p not in gone), None)
    shared = 0
    if ask is None:
        counts = {}
        for a in authored.values():
            for p in a:
                if p not in gone:
                    counts[p] = counts.get(p, 0) + 1
        ask = min(counts, key=lambda p: (-counts[p], p)) if counts else None
        shared = sum(1 for n in counts.values() if n == counts[ask]) if counts else 0
        if shared > 1:
            ask = None   # several author equally many files: the first by name is no more the one to pair with than the rest
    first_area = next((a for a, w, _, _ in lone if w == ask), None)   # lone is ordered by files at stake
    if ask is None and shared > 1:
        advice = (f"Those named are gone, and the {shared} people still here who author the most files author equally many; "
                  "give the files owners, starting with the ones changed most.")
    elif ask is None:
        advice = "Everyone who authors these files has stopped committing; give the files owners, starting with the ones changed most."
    else:
        why = ("they author most of what would be left without an author" if ask == removed[0] else
               "those named before them are gone" if ask in removed else
               "they author the most files among the people still here")
        advice = f"Pair someone with {ask}" + (f" on {first_area}" if first_area else "") + f" first; {why}."
    return [_f("warning" if tf == 1 else "info", "Truck factor", statement, advice,
               rule={"id": "truck_factor", "doa_author_share": 0.75, "doa_floor": 3.293, "orphan_share": 0.5, "decay_months": 5,
                     "ref": "Avelino et al., ICPC 2016", "measured": TRUCK_FACTOR_MEASURED},
               evidence={"truck_factor": tf, "removed": removed, "truck_factor_decayed": tf_d, "removed_decayed": removed_d,
                         "files": len(files), "orphaned": orphans, "area_authors": sorted({w for _, w, _, _ in lone}),
                         "areas": [{"area": a, "author": w, "files": n, "orphaned": o} for a, w, n, o in lone[:10]]})]


RULES = [dormant, secrets_found, credential_files, vulnerable_dependencies, placeholder_identity, bus_factor, bug_magnets,
         brain_methods, complexity_growth, tight_coupling, knowledge_islands,
         sweeping_commits, import_commits, tangled_commits, hygiene_findings, debt_in_hotspots, deep_nesting, hidden_coupling, import_cycles, unreferenced_files,
         agent_approval_disabled, agent_local_settings, mcp_literal_env, agent_instructions_drift, signoff_by_co_author,
         truck_factor, swallowed_errors, hardcoded_addresses, commented_out_code]


# Rules whose findings were true when labelled but never something to act on: five or more labelled in
# measure/labels.jsonl and none of them actionable (docs/measurement.md, "Hand labels"). Until 0.39.0 the
# default report named them in one line; the nine it held then (authors_gone, component_coupling,
# duplication, knowledge_loss, minor_contributors, repo_health, reverts, secrets_aside, stale_files) were
# retired instead, with the duplicates and git-sizer steps. A test holds this set to the labels, both ways,
# so a rule the labels find inert shows up here as a decision to make: retire it too, or say why not.
SUMMARISED = frozenset()

# Rules nobody has labelled yet: the structure step's, which ran only where tree-sitter was installed by hand
# until 0.32.0 and so never reached the measurement's findings sheet. They are named in a line of their own, so
# the default report does not grow by rules whose worth is unmeasured; the labels decide where they belong, and
# a rule moves out of here when its findings are labelled, into SUMMARISED or into the report proper.
UNJUDGED = frozenset({"commented_out_code", "debt_in_hotspots", "deep_nesting", "hardcoded_addresses",
                      "hidden_coupling", "import_cycles", "swallowed_errors", "unreferenced_files"})


OWNERSHIP = ("bus_factor", "truck_factor", "knowledge_islands")   # in the order the merged finding takes its lead from


def _sole_person(f: dict):
    """The one person an ownership finding is about, or None when it names several: the bus factor's author, a
    truck factor of one whose areas of one are all theirs, islands that all have the same owner."""
    rid, ev = f["rule"]["id"], f["evidence"]
    if rid == "bus_factor":
        return ev.get("author")
    if rid == "truck_factor":
        who = ev.get("removed") or []
        return who[0] if ev.get("truck_factor") == 1 and len(who) == 1 and set(ev.get("area_authors") or who) <= set(who) else None
    owners = ev.get("owners") or []
    return owners[0] if len(owners) == 1 else None


def one_owner(found: list, gone: set) -> list:
    """The bus factor, the truck factor and the knowledge islands, when two or more of them name the same single
    person, as one finding: they are one fact measured three ways (surviving lines, files that would lose their
    author, areas one person wrote), and hindsight's report said it three times with three start areas. The lead
    is the first of OWNERSHIP present; the others' rules and evidence ride along under `measures`, and a second
    sentence gives their numbers, so which measures fired stays visible. The start area is the truck factor's,
    the person's area with the most files at stake, when it counted one; otherwise the lead's advice stands."""
    by = {f["rule"]["id"]: f for f in found if f["rule"]["id"] in OWNERSHIP}
    people = {rid: _sole_person(f) for rid, f in by.items()}
    for who in {p for p in people.values() if p}:
        same = [rid for rid in OWNERSHIP if people.get(rid) == who]
        if len(same) < 2:
            continue
        lead, rest = by[same[0]], [by[rid] for rid in same[1:]]
        parts = []
        bus, truck, isl = (by[rid] if rid in same else None for rid in OWNERSHIP)
        name = _who(who, gone)
        if truck:
            ev = truck["evidence"]
            parts.append(f"without {'them' if bus else name}, {ev['orphaned']} of the {ev['files']} source files "
                         f"({_pct(ev['orphaned'], ev['files'])}) have no author left (truck factor 1)")
        if isl:
            ev = isl["evidence"]
            parts.append(f"{ev['count']} area(s) of at least {isl['rule']['min_lines']} lines are almost entirely theirs, "
                         f"{_pct(ev['covered_lines'], ev['total_lines'])} of all lines added (knowledge islands)")
        said = ", and ".join(parts)
        said = said[0].upper() + said[1:] + "."
        if bus:
            ev = bus["evidence"]
            statement = f"{name} wrote {_pct(ev['lines'], ev['total_lines'])} of the code that survives today. {said}"
        else:
            statement = said
        advice = lead["advice"]
        mine = [a for a in (truck["evidence"]["areas"] if truck else []) if a["author"] == who]
        if truck and mine and who not in gone:
            a = mine[0]   # ordered by files at stake
            advice = f"Pair someone with {who} on {a['area']} first; {a['orphaned']} of its {a['files']} files would have no author left without them."
        merged = _f(max((lead, *rest), key=lambda f: -SEVERITIES.index(f["severity"]))["severity"], lead["title"], statement, advice,
                    rule={**lead["rule"], "measures": {f["rule"]["id"]: f["rule"] for f in rest}},
                    evidence={**lead["evidence"], "measures": {f["rule"]["id"]: f["evidence"] for f in rest}})
        found = [merged if f is lead else f for f in found if not any(f is r for r in rest)]
    return found


def evaluate(report: dict) -> list:
    found = []
    for rule in RULES:
        found.extend(rule(report))
    found = one_owner(found, _gone(report))
    for f in found:
        if f["rule"]["id"] in UNJUDGED:
            f["summary"] = True
            f["unjudged"] = True   # a line of its own: true or not, nobody has said whether it is worth acting on
    found.sort(key=lambda f: SEVERITIES.index(f["severity"]))
    return found

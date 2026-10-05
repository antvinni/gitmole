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

A second set came from reading the 0.39.0 report of a one-developer repository built with a coding
agent (debpalash/VoiceStudio), where five of seventeen findings were false:

- agent_owner: the knowledge map names a tool (one of several names on one shared bare no-reply
  address, identity.tools) as an area's owner or second.
- magnet_gone: a bug magnet the tree no longer holds (132 of VoiceStudio's 296 were a retired frontend/).
- hygiene_misread: an extra index named only on comment lines, install code in a setup.py with no setup().
- lock_workspace: lock drift on a workspace member whose declared root keeps the lock.
- unreferenced_named: a "possibly unreferenced" file a non-prose file of the tree names (a build spec, a
  bundler input, a deploy config).
- self_credit: a People row's co-authored count that includes the author's own aliases on their own commits.
- declared_critical: a critical secret the repository declared allowed at some commit (a gitleaks or
  betterleaks config or ignore file, or `gitleaks:allow` on its line).

A fourth set came from the 0.41.0 report of paperclipai/paperclip, a product built largely by its own coding
agent. Each decides by its own reading of the export or the clone, never by asking the gitmole function it judges:

- tool_owner: a coding tool (harness_tools: a bare no-reply mailbox two or more names use, or an identity there
  credited mostly by trailer) as an owner or second in the knowledge map, an ownership finding's owner, or a
  People row with surviving code.
- merge_total: the People caption's merge total against git's merges, or a People row with negative commits.
- suspect_lead: Complex functions, or a lizard-measured finding, leads with a span lizard marked suspect or one
  the structure step measures more than twice or half as long.
- test_double_lead: a finding's first file is a Cargo binary only tests/ start (`CARGO_BIN_EXE_<name>`).
- test_path_secret: a secret in a smoke/, e2e/ or __fixtures__ path, a `*-e2e.*` name, or below `#[cfg(test)]`.
- peer_unused: an unused dependency the lock records as a peer, or a stylesheet loads by @plugin/@import.
- declared_reference: an unreferenced file a package.json runs or publishes, or `new URL(…, import.meta.url)` loads.
- lock_without_require: a go.mod with no `require` named as a manifest without a lock file.
- dev_only_vuln_lead: the vulnerable lead only devDependencies reach while a runtime-reached row waits behind it.
- silent_precondition: a rule advertises a test with a history precondition, and neither evidence nor text
  says what became of it.
- trailer_case: trailer keys split by case, or an issue id read as a key.

A fifth set came from ten reviewers reading the 0.43.1 report of obra/superpowers, a plugin of Markdown skills
and extensionless scripts where 17 of 229 tracked files were scored. Again each reads the export, the default
report as a reader sees it, or the clone, and none asks the function it judges:

- lock_declares_nothing: a "manifest without a lock file" on a manifest that declares no dependency of any kind.
- contributing_heading: "no contribution guide" while a root document has a heading about contributing.
- tied_owner: a "main owner" whose share the second owner equals, in the knowledge map or an ownership finding.
- unscored_executable: a tracked file with the executable bit and a `#!` line that no table of the run carries.
- dead_import: an import commit none of whose paths is at the analysed commit, described as surviving.
- overrun_span: any Complex functions row whose lines are over twice the structure step's span of that function.
- silent_measure: no truck factor on a pool under its floor that one identity dominates, or a backtest that
  did not run, with no sentence in the default report saying so.
- coverage_unsaid: the files no table carries outnumber the scored ones and the default report never says so.
- fix_episode: a bug magnet whose recent fixes all fall in fewer than three ISO weeks. Information for a rule
  that counts episodes; the rule does not exist yet.
- plural_one: "1 packages", "1 files" in the default report.

A sixth set came from ten reviewers reading the 0.44.0 report of dream-num/univer, a pnpm monorepo, where the
one critical and the lock drift, Trojan Source and identity findings were false (h1 to h7 of the review's plan).
Each reads the evidence itself and never calls the function it judges; the first three complain both ways, of a
claim the evidence does not bear out and of evidence no claim was made for:

- drift_specifiers_agree / drift_unclaimed (h1): lock drift on a manifest whose specifiers all equal its pnpm
  lock's `importers` entry; a member whose specifiers differ with no drift claimed.
- private_critical / published_demoted (h2): a critical whose only deploy evidence is the entry point of a
  `"private": true` package; a row a published member's runtime dependencies reach, shown below a warning.
- trojan_inert / trojan_missed (h3): a mixed-script token only in a comment, a character-class range or a literal
  of the other script's prose; a mixed identifier outside those that no row names.
- noreply_split (h4): `<id>+<login>@users.noreply.<forge>` on one identity, `login` another's one-word name.
- action_order (h5): the pinning advice's first action against trust tier, branch-shaped ref, secrets or grants.
- split_density (h6): "Split" advised for a file whose complexity per line rose less than the growth floor.
- locale_magnet (h7): bug-magnet rows that are locale files by their name's shape.

h6 and h7 share their condition with the fixes the review planned, so they record agreement, not proof.

tree_claim, sweeping_evidence, the second set but agent_owner, merge_total, the paperclip checks named above
that read files, and lock_declares_nothing, contributing_heading, unscored_executable, dead_import,
fix_episode and h1, h2, h3 and h5 need the clone, read at the commit the
run recorded and never checked out; the rest need nothing but the JSON export. A complaint is a defect, not a score - the number to
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

from .. import identity, loss, sarif

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
    """git's output as text. Paths and file contents need not be UTF-8 (the awkward-non-utf8-path fixture
    holds one that is not), so undecodable bytes are replaced rather than raised: a check that cannot read a
    name says nothing about it, and the harness must not crash on the repository it is measuring."""
    return subprocess.run(["git", "-c", "core.quotePath=false", *args], cwd=clone, capture_output=True, text=True,
                          encoding="utf-8", errors="replace")


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
    """An identity every one of whose commits came from Co-authored-by trailers, shown as an author. An
    export that records `authored` per identity counts authored commits apart from trailer credit by
    construction, so its tables cannot call the credit authorship and nothing is judged: comparing credit
    with authored commits there fired on people who wrote commits of their own and were also credited
    under another address. Older exports, whose `commits` mixed the two, are judged by the heuristic that
    the credit covers every commit the row shows."""
    trailers = ((report.get("provenance") or {}).get("trailers") or {}).get("never_author") or []
    aliases = (report.get("meta") or {}).get("aliases") or {}
    authors = (report.get("activity") or {}).get("authors") or {}
    credited = {}
    for t in trailers:
        name = aliases.get(t.get("name"), t.get("name"))
        credited[name] = credited.get(name, 0) + (t.get("commits") or 0)
    if any("authored" in a for a in authors.values()):
        return []
    shown = {name: a.get("commits") or 0 for name, a in authors.items()}
    return [_complaint("trailer_author", None, name) for name, n in sorted(credited.items())
            if name in shown and n >= shown[name] > 0]


# --- the checks the 0.39.0 review of a one-developer, agent-assisted repository added ---------------------

def agents(report: dict) -> set:
    """The identities that are a coding tool rather than a person: identity.tools, the definition the
    report's own tables read (several names on one bare no-reply address), so this check and the report agree."""
    return identity.tools((report.get("meta") or {}).get("identities") or [])


def agent_owner(report: dict, found: list) -> list:
    """The knowledge map names a tool as an area's main owner or second: an owner is someone to pair with."""
    tools = agents(report)
    if not tools:
        return []
    from .. import render
    try:
        section = render.knowledge_section(report, full=False)
    except Exception as e:   # an export the renderer cannot read is not this check's to judge
        return [_complaint("agent_owner", None, f"knowledge map not rendered: {type(e).__name__}")]
    out = []
    for row in section.get("rows") or []:
        area, owners = row[0], [c for c in row[2:] if isinstance(c, str)]
        for cell in owners:
            for name in sorted(_owner_names(cell) & tools):
                out.append(_complaint("agent_owner", None, f"{area}: {name}"))
    return out


_GONE = " gone"   # the word after a name whose person has stopped committing, in the drawing that prints the share in its own column


def _owner_names(cell: str) -> set:
    """The names a knowledge-map owner cell may hold, in either drawing of the map: the name with its share in
    brackets after it ("Ann (30%)", "Ann (gone) (30%)"), or the name alone with the share in the column beside
    it ("Ann", "Ann gone"). A name that itself ends in " gone" cannot be told from a gone "Ann" by the cell, so
    both readings are returned and the caller keeps the one it knows."""
    bare = re.sub(r"(?: \(gone\))? \(\d+%\)$", "", cell)
    return {bare, bare[:-len(_GONE)]} if bare.endswith(_GONE) else {bare}


def _owner_share(km: dict, row: list, role: str):
    """(name, share) of the `role` cell ("main owner", "second") of a drawn knowledge-map row, the share as the
    digits printed; None when the cell names nobody with a share. Reads both drawings (_owner_names): the share
    in the cell's brackets, or in a column headed "share" directly to the right of the role's."""
    cols = km.get("columns") or []
    at = cols.index(role) if role in cols else None
    if at is None or at >= len(row):
        return None
    cell = str(row[at])
    inline = _SHARE_CELL.match(cell)
    if inline:
        return inline.group(1), inline.group(2)
    beside = str(row[at + 1]).strip() if at + 1 < len(cols) and cols[at + 1] == "share" and at + 1 < len(row) else ""
    if not re.fullmatch(r"\d+%", beside):
        return None
    return (cell[:-len(_GONE)] if cell.endswith(_GONE) else cell), beside[:-1]


def _in_head(clone: str, commit: str) -> set:
    done = _git(clone, "ls-tree", "-r", "-z", "--name-only", commit)
    return set(p for p in done.stdout.split("\0") if p) if done.returncode == 0 else set()


def magnet_gone(report: dict, found: list, clone: str, commit: str) -> list:
    """Bug magnets are files to review before the next release, so each must be in the tree the release
    ships; a file the history fixed and a later commit deleted is not one."""
    head = _in_head(clone, commit)
    out = []
    for f in found:
        if (f.get("rule") or {}).get("id") != "bug_magnets" or not head:
            continue
        ev = f.get("evidence") or {}
        named = set(ev.get("new_in_window") or []) | {r.get("file") for r in ev.get("files") or [] if isinstance(r, dict)}
        gone = sorted(p for p in named if p and p not in head)
        if gone:
            out.append(_complaint("magnet_gone", f, f"{len(gone)} of {len(named)} named files are not at HEAD, e.g. {gone[0]}"))
    return out


def _blob(clone: str, commit: str, path: str) -> str:
    done = _git(clone, "show", f"{commit}:{path}")
    return done.stdout if done.returncode == 0 else ""


def hygiene_misread(report: dict, found: list, clone: str, commit: str) -> list:
    """A hygiene finding whose evidence the file does not bear out: an extra index named only on comment
    lines of a requirements file, or install code in a setup.py that calls no setup()."""
    out = []
    for f in found:
        rid, ev = (f.get("rule") or {}).get("id"), f.get("evidence") or {}
        if rid == "dependency_confusion":
            for path in ev.get("pip_extra_index") or []:
                lines = [l.strip() for l in _blob(clone, commit, path).splitlines() if "extra-index-url" in l]
                if lines and all(l.startswith("#") for l in lines):
                    out.append(_complaint("hygiene_misread", f, f"{path}: extra-index-url only on comment lines"))
        if rid == "install_scripts":
            for row in ev.get("setup_py") or []:
                path = row.get("file") if isinstance(row, dict) else row
                text = _blob(clone, commit, path) if path else ""
                if text and not re.search(r"\bsetup\s*\(", text):
                    out.append(_complaint("hygiene_misread", f, f"{path}: no setup() call"))
    return out


def lock_workspace(report: dict, found: list, clone: str, commit: str) -> list:
    """Lock drift on a manifest whose directory an ancestor package.json declares as a workspace member,
    where that ancestor keeps a lock file: the workspace root's lock is the one a frozen install reads."""
    out = []
    head = None
    for f in found:
        if (f.get("rule") or {}).get("id") != "lockfile_drift":
            continue
        head = head if head is not None else _in_head(clone, commit)
        for d in (f.get("evidence") or {}).get("drift") or []:
            manifest, lock = d.get("manifest") or "", d.get("lockfile") or ""
            if not manifest.endswith("package.json"):
                continue
            member = os.path.dirname(manifest)
            parts = member.split("/") if member else []
            for depth in range(len(parts) - 1, -1, -1):
                root = "/".join(parts[:depth])
                try:
                    declared = json.loads(_blob(clone, commit, (root + "/" if root else "") + "package.json") or "{}").get("workspaces")
                except ValueError:
                    continue
                patterns = declared.get("packages") if isinstance(declared, dict) else declared
                rel = "/".join(parts[depth:])
                if isinstance(patterns, list) and any(_glob_match(rel, p) for p in patterns):
                    root_lock = (root + "/" if root else "") + os.path.basename(lock)
                    if root_lock in head:
                        out.append(_complaint("lock_workspace", f, f"{manifest}: a workspace member; the root keeps {root_lock}"))
                    break
    return out


def _glob_match(path: str, pattern: str) -> bool:
    import fnmatch
    return fnmatch.fnmatch(path, pattern.rstrip("/")) or path == pattern.rstrip("/")


_SOURCE_EXT = re.compile(r"\.(?:[cm]?[jt]sx?|py|mjs|cjs)$")


def unreferenced_named(report: dict, found: list, clone: str, commit: str) -> list:
    """A 'possibly unreferenced' file whose path the repository names elsewhere: its last two path segments
    without the extension (`shared/lib/utils`, `hooks/pyi_rth_numpy`) in another tracked file that is not
    prose (Markdown, reStructuredText, plain text, anything under docs/), since a roadmap naming a file does
    not load it. A lower
    bound on what an alias, a build spec, a bundler input or a deploy config refers to; the check does not
    decide whether that mention loads the file, only that the report calls it unreferenced regardless."""
    out = []
    for f in found:
        if (f.get("rule") or {}).get("id") != "unreferenced_files":
            continue
        for path in (f.get("evidence") or {}).get("files") or []:
            path = path.get("file") if isinstance(path, dict) else path
            stem = _SOURCE_EXT.sub("", path or "")
            key = "/".join(stem.split("/")[-2:]) if "/" in stem else stem
            if not key:
                continue
            done = _git(clone, "grep", "-l", "-F", "-e", key, commit, "--")
            others = [o for o in (l.split(":", 1)[1] for l in done.stdout.splitlines() if ":" in l)
                      if o != path and not o.lower().endswith((".md", ".mdx", ".rst", ".txt")) and not o.startswith("docs/")]
            if others:
                out.append(_complaint("unreferenced_named", f, f"{path}: named in {others[0]}" + (f" and {len(others) - 1} more" if len(others) > 1 else "")))
    return out


def self_credit(report: dict, found: list, clone: str, commit: str) -> list:
    """A People row whose co-authored count includes trailers naming the author's own aliases on the
    author's own commits: that is one person writing their commit once, not two people."""
    meta = report.get("meta") or {}
    pairs, by_email, by_name = {}, {}, {}
    for i in meta.get("identities") or []:
        for a in [i] + list(i.get("aliases") or []):
            email = (a.get("email") or "").lower()
            pairs[(a.get("name"), email)] = i.get("name")
            by_email.setdefault(email, set()).add(i.get("name"))
            by_name.setdefault(a.get("name"), set()).add(i.get("name"))
    for alias, name in (meta.get("aliases") or {}).items():
        by_name.setdefault(alias, set()).add(name)

    def who(name: str, email: str):
        """The identity a (name, address) pair was merged into: the pair itself, else an address or a name
        only one identity holds; a no-reply address several identities share decides nothing."""
        email = (email or "").lower()
        if (name, email) in pairs:
            return pairs[(name, email)]
        for pool in (by_email.get(email), by_name.get(name)):
            if pool and len(pool) == 1:
                return next(iter(pool))
        return name

    log = _git(clone, "log", "--no-merges", "--format=%an%x00%ae%x00%(trailers:key=Co-authored-by,valueonly,separator=%x01)%x02", commit)
    if log.returncode != 0:
        return []
    others = {}
    for rec in log.stdout.split("\x02"):
        parts = rec.strip("\n").split("\x00")
        if len(parts) < 3 or not parts[2].strip():
            continue
        author = who(parts[0], parts[1])
        for t in parts[2].split("\x01"):
            m = re.match(r"\s*(.*?)\s*<([^>]*)>", t)
            if m and who(m.group(1), m.group(2)) != author:
                person = who(m.group(1), m.group(2))
                others[person] = others.get(person, 0) + 1
    out = []
    for i in meta.get("identities") or []:
        credited = (i.get("commits") or 0) - (i.get("authored") or 0)
        if "authored" in i and i.get("authored") and credited > others.get(i.get("name"), 0):
            out.append(_complaint("self_credit", None, f"{i.get('name')}: {credited} co-authored, {others.get(i.get('name'), 0)} of them on someone else's commit"))
    return out


def _token(line: str) -> str:
    """The longest run on the line that can be a key: 20 or more of [A-Za-z0-9_-]."""
    runs = re.findall(r"[A-Za-z0-9_\-]{20,}", line or "")
    return max(runs, key=len) if runs else ""


def declared_critical(report: dict, found: list, clone: str, commit: str) -> list:
    """A critical secret the repository itself has declared allowed: at some commit a gitleaks/betterleaks
    config or ignore file names the value, or the value's line carries `gitleaks:allow`. The value is read
    from the clone at the commit the scan found it in, compared in memory and never recorded."""
    configs = [".gitleaks.toml", ".betterleaks.toml", ".gitleaksignore", ".betterleaksignore"]
    history = []
    for cfg in configs:
        done = _git(clone, "log", "--format=%H", commit, "--", cfg)
        history += [(h, cfg) for h in done.stdout.split() if h]
    config_texts = [_blob(clone, h, cfg) for h, cfg in history]
    out = []
    for f in found:
        if f.get("severity") != "critical" or not ((f.get("rule") or {}).get("id") or "").startswith("secrets"):
            continue
        files = set((f.get("evidence") or {}).get("files") or [])
        for s in report.get("secrets") or []:
            if s.get("placeholder") or s.get("file") not in files or not s.get("commit") or not s.get("line"):
                continue
            text = _blob(clone, s["commit"], s["file"]).splitlines()
            token = _token(text[int(s["line"]) - 1]) if 0 < int(s["line"]) <= len(text) else ""
            if not token:
                continue
            marked = any(token in c for c in config_texts)
            if not marked:
                later = _git(clone, "log", "--format=%H", commit, "--", s["file"]).stdout.split()
                marked = any(token in l and "gitleaks:allow" in l for h in later for l in _blob(clone, h, s["file"]).splitlines())
            if marked:
                out.append(_complaint("declared_critical", f, f"{s['rule']} in {s['file']} ({str(s['commit'])[:8]})"))
    return out


# --- the checks the 0.40.0 review of a many-package monorepo added (vectorize-io/hindsight) ------------------

_GENERATED_HEAD = re.compile(r"(?i)\b(generated by|code generated|do not edit|auto-?generated)\b")
_GENERATOR_MANIFESTS = (".openapi-generator/FILES",)


def _declared_generated(clone: str, commit: str, head: set) -> set:
    """Files the repository says a generator wrote: listed in a generator's own manifest (OpenAPI Generator
    writes `.openapi-generator/FILES`, paths relative to the directory above it), or carrying a generator's
    header in their first 20 lines. The harness's own reading, independent of the tool's classifier."""
    out = set()
    for path in head:
        for manifest in _GENERATOR_MANIFESTS:
            if path.endswith(manifest):
                root = path[: -len(manifest)]
                out |= {root + line.strip() for line in _blob(clone, commit, path).splitlines() if line.strip()}
    return out


def _heads(clone: str, commit: str, paths: list, lines: int = 20, size_limit: int = 8192) -> dict:
    """The first `lines` lines of many files at one commit, through one `git cat-file --batch` rather than a
    process per file: an area can hold thousands."""
    if not paths:
        return {}
    done = subprocess.run(["git", "cat-file", "--batch"], cwd=clone, capture_output=True,
                          input="".join(f"{commit}:{p}\n" for p in paths).encode("utf-8", "surrogateescape"))
    out, data, pos = {}, done.stdout, 0
    for p in paths:
        nl = data.find(b"\n", pos)
        if nl < 0:
            break
        header = data[pos:nl].split()
        pos = nl + 1
        if len(header) < 3 or header[1] == b"missing":
            continue
        size = int(header[2])
        body = data[pos:pos + size]
        pos += size + 1
        out[p] = "\n".join(body[:size_limit].decode("utf-8", "replace").splitlines()[:lines])
    return out


def _generated_share(clone: str, commit: str, area: str, head: set, listed: set) -> float:
    files = sorted(p for p in head if p.startswith(area) and os.path.splitext(p)[1] in _SOURCE_EXTS)
    if not files:
        return 0.0
    heads = _heads(clone, commit, [p for p in files if p not in listed])
    gen = sum(1 for p in files if p in listed or _GENERATED_HEAD.search(heads.get(p, "")))
    return gen / len(files)


_SOURCE_EXTS = {".py", ".ts", ".tsx", ".js", ".jsx", ".go", ".rs", ".java", ".rb", ".php", ".cs", ".c", ".cc", ".cpp", ".h", ".hpp"}


def generated_owner(report: dict, found: list, clone: str, commit: str) -> list:
    """An ownership finding whose start area is mostly generator output the repository declares: pairing
    someone on a generated client is advice about who runs the generator. hindsight's largest knowledge
    island was an OpenAPI client, 471 of 553 files with the generator's header."""
    head = _in_head(clone, commit)
    if not head:
        return []
    listed = _declared_generated(clone, commit, head)
    out = []
    for f in found:
        rid, ev = (f.get("rule") or {}).get("id"), f.get("evidence") or {}
        rows = ev.get("islands") if rid == "knowledge_islands" else ev.get("areas") if rid in ("bus_factor", "truck_factor") else None
        if not rows:
            continue
        area = rows[0].get("area")
        m = re.search(r" on (\S+/) first", f.get("advice") or "")
        area = m.group(1) if m else area
        if area and area.endswith("/"):
            share = _generated_share(clone, commit, area, head, listed)
            if share >= 0.5:
                out.append(_complaint("generated_owner", f, f"{area}: {share:.0%} of its source files are declared generated"))
    return out


_POINTER_LINE = re.compile(r"^\s*(?:@\S+|.*\]\([^)]+\)|[\w./-]+\.(?:md|txt))\s*$")


def agent_pointer(report: dict, found: list, clone: str, commit: str) -> list:
    """An agent file dated as stale when it only points at another file (`@AGENTS.md`, `See [CLAUDE.md](…)`,
    a symlink): the instructions live in the file it names, which may have changed yesterday. brew,
    prometheus and hindsight each fired this rule on a pointer."""
    out = []
    for f in found:
        if (f.get("rule") or {}).get("id") != "agent_instructions_drift":
            continue
        for row in (f.get("evidence") or {}).get("files") or []:
            path = row.get("file") if isinstance(row, dict) else row
            mode = _git(clone, "ls-tree", commit, "--", path).stdout.split(" ", 1)[0]
            lines = [l for l in _blob(clone, commit, path).splitlines() if l.strip() and not l.lstrip().startswith("#")]
            if mode == "120000" or (0 < len(lines) <= 3 and any(_POINTER_LINE.match(l) or "see " in l.lower() for l in lines)):
                out.append(_complaint("agent_pointer", f, f"{path} points at another file"))
    return out


def start_area(report: dict, found: list) -> list:
    """The truck factor's advice names the person's area with the most files that would lose their author,
    as its sentence says ("they author most of what would be left"); hindsight's named docker/ (9) over the
    area with 267, the first in alphabetical order."""
    out = []
    for f in found:
        if (f.get("rule") or {}).get("id") != "truck_factor":
            continue
        m = re.search(r"Pair someone with (.+?) on (\S+/) first", f.get("advice") or "")
        areas = (f.get("evidence") or {}).get("areas") or []
        if not m or not areas:
            continue
        theirs = [a for a in areas if a.get("author") == m.group(1)]
        best = max(theirs, key=lambda a: a.get("orphaned") or 0) if theirs else None
        if best and best.get("area") != m.group(2) and (best.get("orphaned") or 0) > next((a.get("orphaned") or 0 for a in theirs if a.get("area") == m.group(2)), 0):
            out.append(_complaint("start_area", f, f"names {m.group(2)}; {best['area']} has {best['orphaned']} files at stake"))
    return out


def structure_skipped(report: dict, found: list, clone: str, commit: str) -> list:
    """Source files the structure step never parsed, with nothing in the report saying so: hindsight's busiest
    file (1.19 MB) was over the size limit and its imports vanished, so a file it imports read as unreferenced."""
    s = report.get("structure") or {}
    parsed = set((s.get("files") or {}).keys())
    declared = {r.get("file") if isinstance(r, dict) else r for r in s.get("skipped") or []}
    if not parsed:
        return []
    done = _git(clone, "ls-tree", "-r", "-l", commit)
    big = []
    for line in done.stdout.splitlines():
        meta, _, path = line.partition("\t")
        parts = meta.split()
        if len(parts) >= 4 and parts[3].isdigit() and int(parts[3]) > 1_000_000 and os.path.splitext(path)[1] in _SOURCE_EXTS \
                and "node_modules/" not in path and "vendor/" not in path and path not in parsed and path not in declared:
            big.append(path)
    return [_complaint("structure_skipped", None, f"{p} not parsed and not named as skipped") for p in sorted(big)]


_EXACT_PIN = re.compile(r"==\s*[\w.*+!-]+")


def dependency_floor(report: dict, found: list, clone: str, commit: str) -> list:
    """A vulnerable row whose version is the floor of a range in a requirements file (`mcp>=1.0.0` reported as
    "mcp 1.0.0"): nothing installs the floor on purpose, so the row names a version the file does not pin."""
    out = []
    for f in found:
        if not ((f.get("rule") or {}).get("id") or "").startswith("vulnerable_dependencies"):
            continue
        for row in (f.get("evidence") or {}).get("packages") or []:
            src = row.get("source") or ""
            if not re.search(r"(^|/)(requirements|constraints)[^/]*\.txt$", src):
                continue
            name = (row.get("name") or "").lower().replace("_", "-")
            for line in _blob(clone, commit, src).splitlines():
                bare = line.split("#", 1)[0].strip()
                if re.match(rf"(?i){re.escape(name).replace('-', '[-_.]')}\b", bare.replace("_", "-")):
                    if not _EXACT_PIN.search(bare):
                        out.append(_complaint("dependency_floor", f, f"{row.get('name')} {row.get('version')} in {src}: '{bare}' pins no version"))
                    break
    return out


def sarif_rows(report: dict, found: list) -> list:
    """Every vulnerable package row the report counts reaches the SARIF document; hindsight's carried 10 of 34,
    the finding's capped evidence."""
    rows = [r for r in ((report.get("dependencies") or {}).get("vulnerable") or [])]
    if not rows or not any(((f.get("rule") or {}).get("id") or "").startswith("vulnerable_dependencies") for f in found):
        return []
    try:
        results = sarif.build(report, found, scope="history")["runs"][0]["results"]
    except Exception as e:
        return [_complaint("sarif_rows", None, f"sarif.build failed: {type(e).__name__}")]
    n = sum(1 for r in results if (r.get("ruleId") or "").startswith("vulnerable_dependencies"))
    return [_complaint("sarif_rows", None, f"{n} SARIF results for {len(rows)} vulnerable rows")] if n < len(rows) else []


def doc_lock(report: dict, found: list) -> list:
    """A dependency file set aside as test, example or documentation when its path is neither: pip's
    requirements*.txt is a manifest whatever its extension says."""
    from .. import filetypes
    vendored = filetypes.vendor_dirs(report)
    out = []
    for f in found:
        if (f.get("rule") or {}).get("id") != "vulnerable_dependencies_aside":
            continue
        for row in (f.get("evidence") or {}).get("packages") or []:
            src = row.get("source") or ""
            if re.search(r"(^|/)(requirements|constraints)[^/]*\.txt$", src) and not (
                    filetypes.is_test_path(src) or filetypes.is_sample_path(src) or filetypes.is_vendored(src, vendored)):
                out.append(_complaint("doc_lock", f, f"{src} set aside although it is a manifest outside tests and examples"))
    return out


_BARE_NO_REPLY = re.compile(r"^(?:no-?reply|donotreply|do-not-reply)@", re.I)   # the harness's own copy of the shape


def tool_person(report: dict, found: list) -> list:
    """An identity grouped as a coding tool although it authored commits under an address of its own: a person
    whose own trailer happened to use a shared no-reply mailbox."""
    tools = agents(report)
    out = []
    for i in (report.get("meta") or {}).get("identities") or []:
        if i.get("name") not in tools or not i.get("authored"):
            continue
        own = [a.get("email") or "" for a in [i] + list(i.get("aliases") or []) if not _BARE_NO_REPLY.match(a.get("email") or "")]
        if own:
            out.append(_complaint("tool_person", None, f"{i.get('name')}: {i['authored']} authored commits, grouped as a tool"))
    return out


# --- the checks the 0.41.0 review of an agent-driven product repository added (paperclipai/paperclip) -------
#
# Each decides by its own reading of the export or the clone, never by calling the gitmole function it judges:
# agent_owner asked identity.tools who the tools are, so when identity.tools was wrong it agreed with it.

_BARE_MAILBOX = re.compile(r"^no-?reply@", re.I)   # the local part is the whole of `noreply`/`no-reply`, never NNN+name@
_OWNERSHIP_RULES = frozenset({"truck_factor", "knowledge_islands", "bus_factor", "knowledge_loss"})


def _addresses(i: dict) -> list:
    return [(i.get("name"), (i.get("email") or "").lower())] + [(a.get("name"), (a.get("email") or "").lower()) for a in i.get("aliases") or []]


def harness_tools(report: dict) -> set:
    """The identities that are a coding tool, read here and not from identity.tools: an identity whose own
    address is a bare no-reply mailbox (`noreply@vendor`, not a forge's per-account `NNN+name@users.noreply…`)
    that two or more distinct names use anywhere in the history (identities, their aliases, trailer-only
    credits), or whose commits are mostly credit from trailers rather than commits it authored."""
    meta = report.get("meta") or {}
    ids = meta.get("identities") or []
    names_on = {}
    for i in ids:
        for name, email in _addresses(i):
            names_on.setdefault(email, set()).add(name)
    for t in ((report.get("provenance") or {}).get("trailers") or {}).get("never_author") or []:
        names_on.setdefault((t.get("email") or "").lower(), set()).add(t.get("name"))
    out = set()
    for i in ids:
        email = (i.get("email") or "").lower()
        if not _BARE_MAILBOX.match(email):
            continue
        commits, authored = i.get("commits") or 0, i.get("authored")
        credited = authored is not None and commits - authored > commits / 2
        if len(names_on.get(email, ())) >= 2 or credited:
            out.add(i.get("name"))
    return out


def _render(report: dict, section: str, full=None):
    """A section as gitmole builds it. `full` None is every row the section has: the mode of a section printed
    on its own (render.SECTION, from the release that has `--section NAME`), and `--full`'s for a renderer
    without one. The checks that ask for it read every row (a tool that owns code in the sixtieth area, a
    People row with negative commits), and once `--full` caps its tables at fifty rows, True would hand them
    the first fifty."""
    from .. import render
    if full is None:
        full = getattr(render, "SECTION", True)
    try:
        return getattr(render, section)(report, full=full)
    except Exception:   # an export the renderer cannot read is not these checks' to judge
        return None


def _column(sec: dict, name: str):
    cols = sec.get("columns") or []
    return cols.index(name) if name in cols else None


def tool_owner(report: dict, found: list) -> list:
    """A coding tool shown as a person who owns code: an owner or second owner in the knowledge map, an owner
    an ownership finding names, or a People row holding surviving code. paperclip's product agent, credited by
    trailer on 2,052 commits at a mailbox nine names share, was second owner of every area. Unlike agent_owner,
    which asks identity.tools who the tools are, the tools here are harness_tools' own reading."""
    tools = harness_tools(report)
    if not tools:
        return []
    out = []
    km = _render(report, "knowledge_section")
    if km:
        for role in ("main owner", "second"):
            at = _column(km, role)
            held = {}
            for row in km.get("rows") or [] if at is not None else []:
                for name in sorted(_owner_names(str(row[at])) & tools):
                    held.setdefault(name, []).append(row[0])
            for name, areas in sorted(held.items()):
                out.append(_complaint("tool_owner", None, f"knowledge map: {name} is {role} of {len(areas)} area(s), e.g. {areas[0]}"))
    for f in found:
        if (f.get("rule") or {}).get("id") in _OWNERSHIP_RULES:
            for name in sorted((_people(f.get("evidence")) | set((f.get("evidence") or {}).get("area_authors") or [])) & tools):
                out.append(_complaint("tool_owner", f, f"names {name} as an owner"))
    people = _render(report, "people_section")
    at = (_column(people, "surviving code") if _column(people, "surviving code") is not None else _column(people, "surviving")) if people else None   # the column under either head
    if at is not None:
        for name in sorted({row[0] for row in people["rows"] if row[0] in tools and row[at] not in ("0%", "-")}):
            share = next(row[at] for row in people["rows"] if row[0] == name and row[at] not in ("0%", "-"))
            out.append(_complaint("tool_owner", None, f"People: {name} holds {share} of the surviving code"))
    return out


def merge_rows(report: dict, found: list) -> list:
    """merge_total, from the export: a People row with negative commits or share, which only a merge count
    subtracted from the wrong row can give (paperclip's second "Dotta" row, -348)."""
    people = _render(report, "people_section")
    if not people:
        return []
    c, s = _column(people, "commits"), _column(people, "share")
    out = []
    for row in people["rows"]:
        if (c is not None and row[c].lstrip().startswith("-") and row[c].strip() != "-") or (s is not None and row[s].startswith("-") and row[s] != "-"):
            out.append(_complaint("merge_total", None, f"People: {row[0]} has {row[c] if c is not None else '?'} commits, {row[s] if s is not None else '?'} share"))
    return out


def merge_total(report: dict, found: list, clone: str, commit: str) -> list:
    """The People caption's merge total against the merges git has at the analysed commit, bots' merges left
    out as the table leaves bots out (paperclip: "725 in all" against 376)."""
    people = _render(report, "people_section")
    m = _MERGES_IN_ALL.search((people or {}).get("caption") or "")
    meta = report.get("meta") or {}
    if not m or (meta.get("paths") or meta.get("path")):
        return []
    bots = {b.get("name") for b in meta.get("bots") or []}
    args = ["log", "--merges", "--format=%an%x00%aN"] + ([f"--since={meta['since']}"] if meta.get("since") else []) + [commit]
    done = _git(clone, *args)
    if done.returncode != 0:
        return []
    real = sum(1 for l in done.stdout.splitlines() if l and not (set(l.split("\0")) & bots or l.split("\0")[0].endswith("[bot]")))
    shown = int((m.group(1) or m.group(2)).replace(",", ""))
    return [_complaint("merge_total", None, f"People says {shown:,} merges in all; git has {real:,} not by a bot")] if shown != real else []


# the People caption's merge total, in either wording: "merges, which are counted apart (5,019 in all)" or "5,019 merges in all"
_MERGES_IN_ALL = re.compile(r"counted apart \(([\d,]+) in all\)|(?<![\w,.])([\d,]+) merges? in all\b")


def _span(f: dict) -> int:
    return (f.get("end") or 0) - (f.get("start") or 0) + 1


def _lead_problems(report: dict, rec: dict) -> list:
    """Why a function record should not lead: lizard marked its span suspect, or the structure step's span of
    the function starting on the same line of the same file disagrees by more than twice."""
    out = []
    if rec.get("suspect"):
        out.append("lizard marks its span suspect")
    for s in (report.get("structure") or {}).get("functions") or []:
        if s.get("file") == rec.get("file") and s.get("start") == rec.get("start") and s.get("end"):
            a, b = _span(rec), _span(s)
            if min(a, b) > 0 and max(a, b) > 2 * min(a, b):
                out.append(f"its span is {a} lines to lizard and {b} to the structure step")
            break
    return out


def suspect_lead(report: dict, found: list) -> list:
    """The function a list leads with is one lizard may have mis-parsed: the first row of Complex functions, or
    the first function a finding measured by lizard names ("Split run in … first"). paperclip's table led with six
    "?" rows, parseSkillFrontmatter at complexity 1036 over 4,232 lines, 19 real lines."""
    funcs = report.get("functions") or []
    out = []
    table = _render(report, "functions_section", full=False)   # the table a reader sees, tests and vendored code hidden
    if table and table.get("rows"):
        name, where, ccn = table["rows"][0][0], table["rows"][0][1], table["rows"][0][2]
        file, _, line = where.rpartition(":") if re.search(r":\d+$", where) else (where, "", "")
        recs = [f for f in funcs if f.get("file") == file and str(f.get("ccn")) == ccn.rstrip("?")
                and (str(f.get("start")) == line if line else f.get("function") == name)]
        why = _lead_problems(report, recs[0]) if recs else (["lizard marks its span suspect"] if ccn.endswith("?") else [])
        if why:
            out.append(_complaint("suspect_lead", None, f"Complex functions leads with {name} in {where}: {'; '.join(why)}"))
    for f in found:
        rows = (f.get("evidence") or {}).get("functions") or []
        if not rows or not isinstance(rows[0], dict) or "ccn" not in rows[0]:
            continue
        head = rows[0]
        rec = next((r for r in funcs if r.get("file") == head.get("file") and r.get("start") == head.get("start")), None)
        why = _lead_problems(report, rec) if rec else []
        if why:
            out.append(_complaint("suspect_lead", f, f"leads with {head.get('function')} in {head.get('file')}: {'; '.join(why)}"))
    return out


def _first_file(f: dict):
    ev = f.get("evidence") or {}
    for key in ("functions", "files", "islands"):
        rows = ev.get(key)
        if isinstance(rows, list) and rows:
            row = rows[0]
            return row.get("file") if isinstance(row, dict) else row if isinstance(row, str) else None
    return None


def _cargo_bin(clone: str, commit: str, path: str, head: set):
    """The Cargo binary target `path` is, by the nearest Cargo.toml above it: a `[[bin]]` whose `path` is it, or
    Cargo's convention src/bin/NAME.rs and src/bin/NAME/main.rs. None when it is not one."""
    parts = path.split("/")
    for depth in range(len(parts) - 1, -1, -1):
        root = "/".join(parts[:depth])
        manifest = (root + "/" if root else "") + "Cargo.toml"
        if manifest not in head:
            continue
        rel = "/".join(parts[depth:])
        for block in re.split(r"(?m)^\s*\[", _blob(clone, commit, manifest)):
            if block.startswith("[bin]]"):
                p = re.search(r'(?m)^\s*path\s*=\s*"([^"]+)"', block)
                n = re.search(r'(?m)^\s*name\s*=\s*"([^"]+)"', block)
                if p and n and os.path.normpath(p.group(1)) == rel:
                    return n.group(1)
        m = re.fullmatch(r"src/bin/([^/]+)\.rs|src/bin/([^/]+)/main\.rs", rel)
        return (m.group(1) or m.group(2)) if m else None
    return None


def test_double_lead(report: dict, found: list, clone: str, commit: str) -> list:
    """A finding whose first-named file is a Cargo binary only the crate's tests run: its name appears as
    `CARGO_BIN_EXE_<name>`, the variable Cargo sets for integration tests, and only under a tests/ directory.
    paperclip's brain methods led with fake-codex-app-server.rs, a test double."""
    head, out = None, []
    for f in found:
        path = _first_file(f)
        if not path or not path.endswith(".rs"):
            continue
        head = head if head is not None else _in_head(clone, commit)
        name = _cargo_bin(clone, commit, path, head)
        if not name:
            continue
        hits = {l.split(":", 2)[1] for l in _git(clone, "grep", "-l", "-F", "-e", f"CARGO_BIN_EXE_{name}", commit, "--").stdout.splitlines() if l.count(":") >= 1}
        if hits and all("tests" in h.split("/")[:-1] for h in hits):
            out.append(_complaint("test_double_lead", f, f"{path}: binary {name}, run only by {len(hits)} file(s) under tests/"))
    return out


_TEST_SEGMENTS = frozenset({"smoke", "e2e", "__fixtures__"})
_E2E_NAME = re.compile(r"[-_]e2e\.", re.I)


def test_path_secret(report: dict, found: list, clone: str, commit: str) -> list:
    """A secret the secrets findings count that sits in test code by the path's convention (a `smoke`, `e2e` or
    `__fixtures__` directory, a `*-e2e.*` or `*_e2e.*` name) or, in Rust, below the file's `#[cfg(test)]` line.
    paperclip's one critical was a deliberately wrong key in a negative test, scripts/smoke/hermes-gateway-e2e.sh.
    The value is never read into the complaint: rule, path and commit only."""
    rows = [s for s in report.get("secrets") or [] if not s.get("placeholder")]
    out = []
    for f in found:
        if not ((f.get("rule") or {}).get("id") or "").startswith("secrets"):
            continue
        files = set((f.get("evidence") or {}).get("files") or [])
        seen = set()
        for s in rows:
            path = s.get("file") or ""
            if path not in files or path in seen:
                continue
            why = None
            if _TEST_SEGMENTS & set(path.split("/")[:-1]) or _E2E_NAME.search(os.path.basename(path)):
                why = "a test path"
            elif path.endswith(".rs"):
                at, line = (commit, s.get("head_line")) if s.get("at_head") and s.get("head_line") else (s.get("commit"), s.get("line"))
                if at and line:
                    text = _blob(clone, at, path).splitlines()[: int(line) - 1]
                    if any(re.match(r"\s*#\[cfg\(test\)\]", l) for l in text):
                        why = "below #[cfg(test)]"
            if why:
                seen.add(path)
                out.append(_complaint("test_path_secret", f, f"{s.get('rule')} in {path} ({str(s.get('commit'))[:8]}): {why}"))
    return out


def _lock_above(head: set, manifest: str, names=("pnpm-lock.yaml", "package-lock.json")):
    parts = os.path.dirname(manifest).split("/") if os.path.dirname(manifest) else []
    for depth in range(len(parts), -1, -1):
        root = "/".join(parts[:depth])
        for n in names:
            lock = (root + "/" if root else "") + n
            if lock in head:
                return lock, root
    return None, None


def _unquote(s: str) -> str:
    s = s.strip()
    return s[1:-1] if len(s) >= 2 and s[0] == s[-1] and s[0] in "'\"" else s


def _yaml_key(s: str):
    """(key, value) of one `key: value` line of a pnpm lock, the key quoted or not."""
    s = s.strip()
    if s[:1] in "'\"":
        end = s.find(s[0], 1)
        return s[1:end], s[end + 1:].lstrip(":").strip()
    key, _, value = s.partition(": ") if ": " in s else (s.rstrip(":"), "", "")
    return key, value.strip()


def _pnpm(text: str) -> tuple:
    """A pnpm lock's importers {id: {group: [(name, version)]}} and its package graph {key: [(name, version)]},
    read by indentation (lock files v6 and v9): enough to walk, not a YAML parser."""
    importers, graph = {}, {}
    section = cur = group = dep = None
    for line in text.splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        ind = len(line) - len(line.lstrip(" "))
        if ind == 0:
            section = s.rstrip(":")
            continue
        if section == "importers":
            if ind == 2:
                cur = _yaml_key(s)[0]
                importers[cur] = {}
            elif ind == 4 and cur is not None:
                group = s.rstrip(":")
                importers[cur].setdefault(group, [])
            elif ind == 6 and cur is not None:
                dep, value = _yaml_key(s)
                if value:   # the v5 shape, `name: version`
                    importers[cur][group].append((dep, _unquote(value)))
            elif ind == 8 and s.startswith("version:") and cur is not None:
                importers[cur][group].append((dep, _unquote(s.split(":", 1)[1])))
        elif section in ("snapshots", "packages"):
            if ind == 2:
                cur = _yaml_key(s)[0].lstrip("/")
                graph.setdefault(cur, [])
            elif ind == 4:
                group = s.rstrip(":")
            elif ind == 6 and group in ("dependencies", "optionalDependencies") and cur is not None:
                name, value = _yaml_key(s)
                graph[cur].append((name, _unquote(value)))
    return importers, graph


def _reach(importers: dict, graph: dict, groups: tuple, roots=None) -> set:
    """The name@version (peer suffixes dropped) every importer (or each of `roots`) reaches from its `groups`;
    a workspace link is followed into that importer's runtime dependencies."""
    seen, todo, out = set(), [], set()
    for imp, g in importers.items():
        if roots is not None and imp not in roots:
            continue
        for group in groups:
            todo += [(imp, n, v) for n, v in g.get(group) or []]
    while todo:
        imp, name, ver = todo.pop()
        if ver.startswith("link:"):
            target = os.path.normpath(os.path.join(imp, ver[5:])).replace(os.sep, "/")
            target = "." if target in ("", ".") else target
            if ("link", target) not in seen:
                seen.add(("link", target))
                todo += [(target, n, v) for grp in ("dependencies", "optionalDependencies") for n, v in (importers.get(target) or {}).get(grp) or []]
            continue
        key = ver if ver.startswith(name + "@") else f"{name}@{ver}"
        if key in seen:
            continue
        seen.add(key)
        out.add(key.split("(", 1)[0])
        todo += [(imp, n, v) for n, v in graph.get(key) or graph.get(key.split("(", 1)[0]) or []]
    return out


def dev_only_vuln_lead(report: dict, found: list, clone: str, commit: str) -> list:
    """The vulnerable-dependencies finding leads with a package of a pnpm lock that only devDependencies reach,
    while another row it counts is reached from runtime dependencies. paperclip led with form-data, there only
    through a test library, and buried multer, which the server imports."""
    out, cache = [], {}
    rows_all = (report.get("dependencies") or {}).get("vulnerable") or []
    for f in found:
        if (f.get("rule") or {}).get("id") != "vulnerable_dependencies":
            continue
        rows = (f.get("evidence") or {}).get("packages") or []
        if not rows or not (rows[0].get("source") or "").endswith("pnpm-lock.yaml"):
            continue
        lock = rows[0]["source"]
        if lock not in cache:
            imps, graph = _pnpm(_blob(clone, commit, lock))
            cache[lock] = (_reach(imps, graph, ("dependencies", "optionalDependencies")), _reach(imps, graph, ("devDependencies",)))
        runtime, dev = cache[lock]
        lead = f"{rows[0].get('name')}@{rows[0].get('version')}"
        if lead in runtime or lead not in dev:
            continue
        other = next((r for r in list(rows[1:]) + list(rows_all) if r.get("source") == lock and f"{r.get('name')}@{r.get('version')}" in runtime), None)
        if other:
            out.append(_complaint("dev_only_vuln_lead", f, f"leads with {rows[0]['name']} {rows[0].get('version')}, reached only through "
                                                         f"devDependencies; {other['name']} {other.get('version')} is reached from dependencies"))
    return out


def _peer_in_lock(clone: str, commit: str, lock: str, lock_root: str, manifest: str, package: str) -> bool:
    text = _blob(clone, commit, lock)
    if not text:
        return False
    member = os.path.relpath(os.path.dirname(manifest) or ".", lock_root or ".").replace(os.sep, "/")
    if lock.endswith("pnpm-lock.yaml"):
        importers, _ = _pnpm(text)
        mine = importers.get(member) or {}
        suffix = "(" + package + "@"
        if any(suffix in v for grp in mine.values() for _, v in grp):
            return True
        # a `peerDependencies:` block of a package the manifest depends on directly
        direct = {n for grp in mine.values() for n, _ in grp}
        cur, peers = None, False
        for line in text.splitlines():
            ind = len(line) - len(line.lstrip(" "))
            s = line.strip()
            if ind == 2 and s:
                cur = _yaml_key(s)[0].lstrip("/").split("(", 1)[0]
                cur = cur.rsplit("@", 1)[0] if cur.count("@") > (1 if cur.startswith("@") else 0) else cur
            elif ind == 4:
                peers = s == "peerDependencies:"
            elif ind == 6 and peers and cur in direct and _yaml_key(s)[0] == package:
                return True
        return False
    try:
        packages = json.loads(text).get("packages") or {}
    except ValueError:
        return False
    if (packages.get(f"node_modules/{package}") or {}).get("peer"):
        return True
    try:
        declared = json.loads(_blob(clone, commit, manifest) or "{}")
    except ValueError:
        declared = {}
    direct = set(declared.get("dependencies") or {}) | set(declared.get("devDependencies") or {})
    return any(package in ((packages.get(f"node_modules/{d}") or {}).get("peerDependencies") or {}) for d in direct)


def peer_unused(report: dict, found: list, clone: str, commit: str) -> list:
    """An "unused dependency" that is used: the lock file records it as a peer another dependency of the same
    manifest needs (pnpm's `(name@version)` suffix or a `peerDependencies` block, npm's `peer: true`), or a
    stylesheet under the manifest loads it by `@plugin` or `@import`. paperclip: @anthropic-ai/sdk, nice-grpc,
    nice-grpc-common (peers) and @tailwindcss/typography (a Tailwind @plugin)."""
    head, out = None, []
    for f in found:
        if (f.get("rule") or {}).get("id") != "unused_dependencies":
            continue
        for row in (f.get("evidence") or {}).get("unused") or []:
            manifest, package = row.get("manifest") or "", row.get("package") or ""
            if row.get("ecosystem") != "npm" or not manifest.endswith("package.json") or not package:
                continue
            head = head if head is not None else _in_head(clone, commit)
            lock, root = _lock_above(head, manifest)
            if lock and _peer_in_lock(clone, commit, lock, root, manifest, package):
                out.append(_complaint("peer_unused", f, f"{package} in {manifest}: a peer dependency in {lock}"))
                continue
            where = os.path.dirname(manifest)
            done = _git(clone, "grep", "-l", "-E", "-e", r"@(plugin|import)[[:space:]]+['\"]" + re.escape(package) + r"['\"/]", commit, "--",
                        *([f"{where}/*.css", f"{where}/**/*.css"] if where else ["*.css"]))
            hits = [l.split(":", 1)[1] for l in done.stdout.splitlines() if ":" in l]
            if hits:
                out.append(_complaint("peer_unused", f, f"{package} in {manifest}: loaded by {hits[0]}"))
    return out


_BUILD_DIRS = ("dist/", "build/", "lib/", "out/")
_EXTS = re.compile(r"(\.d)?\.(?:[cm]?[jt]sx?|json|node)$")


def _stem(path: str) -> str:
    path = path.strip().strip("'\"")
    while path.startswith("./"):
        path = path[2:]
    return _EXTS.sub("", os.path.normpath(path).replace(os.sep, "/")) if path else ""


def _strings(value) -> list:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [s for v in value.values() for s in _strings(v)]
    if isinstance(value, list):
        return [s for v in value for s in _strings(v)]
    return []


def _declares(declared: dict, rel: str):
    """Which field of one package.json names the file at `rel` (relative to it): a `scripts` command's literal
    word (a glob there is a formatter's or linter's input, not a load), or an `exports`, `bin`, `main` or
    `module` target, a `*` in a target matching any run, and a built
    dist/, build/, lib/ or out/ target mapped back to the src/ it is built from."""
    want = _stem(rel)
    if not want:
        return None
    alts = {want} | ({"src/" + want[len(d):] for d in _BUILD_DIRS if want.startswith(d)})

    def names(target: str, wildcard: bool = True) -> bool:
        t = _stem(target)
        if "*" in t and not wildcard:
            return False
        cands = {t} | {"src/" + t[len(d):] for d in _BUILD_DIRS if t.startswith(d)}
        for c in cands:
            if "*" in c:
                rx = re.compile("^" + re.escape(c).replace(r"\*", ".+") + "$")
                if any(rx.match(a) for a in alts):
                    return True
            elif c in alts:
                return True
        return False
    for name, command in (declared.get("scripts") or {}).items():
        if isinstance(command, str) and any(names(w, wildcard=False) for w in re.split(r"[\s;&|()=]+", command) if "/" in w or "." in w):
            return f"scripts.{name}"
    for field in ("exports", "bin", "main", "module"):
        if any(names(t) for t in _strings(declared.get(field))):
            return field
    return None


_URL_LOAD = re.compile(r"""new URL\(\s*(['"`])([^'"`]+)\1\s*,\s*import\.meta\.url""")


def declared_reference(report: dict, found: list, clone: str, commit: str) -> list:
    """A "possibly unreferenced" file the repository declares it uses, by a mechanism that loads it: a
    package.json above it runs it from `scripts` or publishes it through `exports`, `bin`, `main` or `module`
    (wildcards and a dist/ target mapped back to src/), or a module loads it with
    `new URL('…', import.meta.url)`. paperclip's first ten held nine such files. unreferenced_named is the
    wider and weaker net - any mention of the file's last two path segments in a non-prose file - and says only
    that a name appears; this says the repository's own declarations reach the file."""
    head, urls, out = None, None, []
    for f in found:
        if (f.get("rule") or {}).get("id") != "unreferenced_files":
            continue
        head = head if head is not None else _in_head(clone, commit)
        if urls is None:
            urls = {}
            done = _git(clone, "grep", "-n", "-E", "-e", r"new URL\([[:space:]]*['\"`]", commit, "--")
            for line in done.stdout.splitlines():
                parts = line.split(":", 3)
                if len(parts) < 4:
                    continue
                for m in _URL_LOAD.finditer(parts[3]):
                    target = os.path.normpath(os.path.join(os.path.dirname(parts[1]), m.group(2))).replace(os.sep, "/")
                    urls.setdefault(target, parts[1])
        for path in (f.get("evidence") or {}).get("files") or []:
            path = path.get("file") if isinstance(path, dict) else path
            if not path:
                continue
            why = f"loaded by new URL in {urls[path]}" if path in urls else None
            parts = path.split("/")
            for depth in range(len(parts) - 1, -1, -1) if not why else ():
                root = "/".join(parts[:depth])
                pkg = (root + "/" if root else "") + "package.json"
                if pkg not in head:
                    continue
                try:
                    declared = json.loads(_blob(clone, commit, pkg) or "{}")
                except ValueError:
                    continue
                field = _declares(declared, "/".join(parts[depth:])) if isinstance(declared, dict) else None
                if field:
                    why = f"{field} in {pkg}"
                    break
            if why:
                out.append(_complaint("declared_reference", f, f"{path}: {why}"))
    return out


def lock_without_require(report: dict, found: list, clone: str, commit: str) -> list:
    """"Manifest without a lock file" on a go.mod that requires nothing: Go writes no go.sum for a module with
    no `require`, so there is no lock to commit (paperclip's tools/agent-shim/go.mod)."""
    out = []
    for f in found:
        if (f.get("rule") or {}).get("id") != "lockfile_missing":
            continue
        for row in (f.get("evidence") or {}).get("missing") or []:
            manifest = row.get("manifest") if isinstance(row, dict) else row
            if manifest and os.path.basename(manifest) == "go.mod":
                text = _blob(clone, commit, manifest)
                if text and not re.search(r"(?m)^\s*require\b", text):
                    out.append(_complaint("lock_without_require", f, f"{manifest} has no require line"))
    return out


_NOT_RUN = re.compile(r"(?i)\bnot (?:run|tested)\b|\btoo (?:short|little)\b|\bnot enough history\b|\bneeds? \d+ months\b|\bwithout the (?:size )?test\b")


def _has_key(value, key: str) -> bool:
    if isinstance(value, dict):
        return key in value or any(_has_key(v, key) for v in value.values())
    if isinstance(value, list):
        return any(_has_key(v, key) for v in value)
    return False


def silent_precondition(report: dict, found: list) -> list:
    """A finding whose rule advertises a test with a history precondition (a rule entry holding
    `min_history_months`) while its evidence carries no result of that test and its text does not say the test
    did not run. paperclip's bug magnets advertised `above_rate` over 7 months of a 12-month precondition: the 391
    magnets were raw counts, and nothing said so."""
    months = _history_months(report)
    out = []
    for f in found:
        rule = f.get("rule") or {}
        for key, spec in rule.items():
            if not isinstance(spec, dict) or "min_history_months" not in spec:
                continue
            if _has_key(f.get("evidence"), key) or _NOT_RUN.search(f"{f.get('detail') or ''} {f.get('advice') or ''}"):
                continue
            history = f"{months} months of history, " if months is not None else ""
            out.append(_complaint("silent_precondition", f, f"{key}: no result and no word why ({history}needs {spec['min_history_months']})"))
    return out


_TICKET = re.compile(r"^[A-Za-z]+-\d+$")


def trailer_case(report: dict, found: list) -> list:
    """The trailers table splits one key by case (`Co-authored-by` and `Co-Authored-By`: git reads trailer keys
    case-insensitively) or lists an issue id (`PAP-10182`, letters, a hyphen, digits) as a trailer key."""
    keys = list((((report.get("provenance") or {}).get("trailers") or {}).get("keys") or {}).keys())
    folded, out = {}, []
    for k in keys:
        folded.setdefault(k.casefold(), []).append(k)
    for group in folded.values():
        if len(group) > 1:
            out.append(_complaint("trailer_case", None, f"{' and '.join(sorted(group))} counted apart"))
    out += [_complaint("trailer_case", None, f"{k} is an issue id, not a trailer key") for k in keys if _TICKET.match(k)]
    return out


# --- the checks the 0.43.1 review of a plugin of Markdown skills added (obra/superpowers) --------------------
#
# 17 of its 229 tracked files were scored. What gitmole scored it scored correctly; the defects were in what it
# said about the rest, and in what it left unsaid.

_NPM_DECLARES = ("dependencies", "devDependencies", "optionalDependencies", "peerDependencies", "bundledDependencies",
                 "bundleDependencies", "workspaces")
_CARGO_DECLARES = re.compile(r"(?m)^\s*\[(?:[^\]\n]*\.)?(?:dev-|build-)?dependencies(?:\.[^\]\n]*)?\]|^\s*\[workspace[.\]]")


def _toml_section_empty(text: str, names: tuple) -> bool:
    """No `key = value` line under any of the named top-level tables of a TOML file."""
    inside = False
    for line in text.splitlines():
        bare = line.split("#", 1)[0].strip()
        if bare.startswith("["):
            inside = bare.strip("[]").strip() in names
        elif inside and "=" in bare:
            return False
    return True


def _declares_nothing(name: str, text: str):
    """Whether a manifest's text declares no dependency of any kind, by the manifest's own format; None for a
    format not read here (go.mod is lock_without_require's) or a file that does not parse."""
    if not text.strip():
        return None
    if name in ("package.json", "composer.json"):
        try:
            declared = json.loads(text)
        except ValueError:
            return None
        if not isinstance(declared, dict):
            return None
        keys = _NPM_DECLARES if name == "package.json" else ("require", "require-dev")
        return not any(declared.get(k) for k in keys)
    if name == "Cargo.toml":
        return not _CARGO_DECLARES.search(text)
    if name == "Gemfile":
        return not re.search(r"(?m)^\s*(?:gem|gemspec)\b", text)
    if name == "Pipfile":
        return _toml_section_empty(text, ("packages", "dev-packages"))
    return None


def lock_declares_nothing(report: dict, found: list, clone: str, commit: str) -> list:
    """"Manifest without a lock file" on a manifest that declares no dependency of any kind: there is nothing
    for a lock file to pin. superpowers' root package.json holds a name, a version and a `main`; the finding
    cost it an OSPS-QA-02.01 gap. lock_without_require is the same complaint for a go.mod."""
    out = []
    for f in found:
        if (f.get("rule") or {}).get("id") != "lockfile_missing":
            continue
        for row in (f.get("evidence") or {}).get("missing") or []:
            manifest = row.get("manifest") if isinstance(row, dict) else row
            if manifest and _declares_nothing(os.path.basename(manifest), _blob(clone, commit, manifest)):
                out.append(_complaint("lock_declares_nothing", f, f"{manifest} declares no dependencies"))
    return out


_DOC_EXT = (".md", ".markdown", ".mdx", ".rst", ".txt", ".adoc", "")
_NOT_A_GUIDE = re.compile(r"(?i)change|release|history|news")   # a changelog's heading about contributors is not a guide
_ABOUT_CONTRIBUTING = r"[^\n]*\bcontribut(?:ing|ions?\b|e\b|or guid)[^\n]*"
_CONTRIBUTING_HEADING = re.compile(r"(?im)^ {0,3}(?:#{1,6}|=+)[ \t]+" + _ABOUT_CONTRIBUTING + r"$"          # Markdown, AsciiDoc
                                   r"|^" + _ABOUT_CONTRIBUTING + r"\n[ \t]*(?:={3,}|-{3,}|~{3,})[ \t]*$")   # setext, reStructuredText


def _says_no_guide(report: dict, found: list):
    """The finding that says there is no contribution guide, or True when only the OSPS table does."""
    for f in found:
        if re.search(r"(?i)\bno (?:a )?contribut", f.get("detail") or ""):
            return f
    for c in (report.get("osps") or {}).get("controls") or []:
        if c.get("control") == "OSPS-GV-03.01" and c.get("result") == "gap":
            return True
    return None


def contributing_heading(report: dict, found: list, clone: str, commit: str) -> list:
    """The report says there is no contribution guide (a policy finding, or the OSPS-GV-03.01 gap) while a
    document at the root has a heading about contributing: superpowers' README has "## Contributing" and the
    process below it. Root documents only, a README first, changelogs and release notes left out."""
    said = _says_no_guide(report, found)
    if not said:
        return []
    done = _git(clone, "ls-tree", "-z", "--name-only", commit)
    docs = [p for p in done.stdout.split("\0") if p and os.path.splitext(p)[1].lower() in _DOC_EXT
            and (os.path.splitext(p)[1] or p.upper().startswith("README")) and not _NOT_A_GUIDE.search(p)]
    docs.sort(key=lambda p: (not p.upper().startswith("README"), p))
    for path, text in _heads(clone, commit, docs, lines=100_000, size_limit=1_000_000).items():
        m = _CONTRIBUTING_HEADING.search(text)
        if m:
            heading = m.group(0).splitlines()[0].strip()
            return [_complaint("contributing_heading", said if isinstance(said, dict) else None, f"{path} has the heading '{heading[:60]}'")]
    return []


_SHARE_CELL = re.compile(r"^(.*?)(?: \(gone\))? \((\d+)%\)$")


def tied_owner(report: dict, found: list) -> list:
    """A "main owner" who owns no more than the next person: the knowledge map's main owner and second print the
    same share (superpowers' `.hermes-plugin/  Ada Sen (8%)  Caio Lopes (8%)`, twelve co-authors of one squash
    commit in alphabetical order), or an ownership finding names an area's owner while the export's own
    ownership rows give someone else as many lines there."""
    out = []
    km = _render(report, "knowledge_section", full=False)
    if km and _column(km, "main owner") is not None and _column(km, "second") is not None:
        for row in km.get("rows") or []:
            first, second = _owner_share(km, row, "main owner"), _owner_share(km, row, "second")
            if first and second and first[1] == second[1]:
                out.append(_complaint("tied_owner", None, f"knowledge map: {row[0]} {first[0]} and {second[0]}, both {first[1]}%"))
    rows_all = report.get("ownership") or []
    for f in found:
        if (f.get("rule") or {}).get("id") not in _OWNERSHIP_RULES:
            continue
        ev = f.get("evidence") or {}
        for row in (ev.get("islands") or []) + (ev.get("areas") or []):
            area, who = (row.get("area"), row.get("owner") or row.get("author")) if isinstance(row, dict) else (None, None)
            if not area or not area.endswith("/") or not who:
                continue
            lines = {}
            for r in rows_all:
                if (r.get("entity") or "").startswith(area):
                    lines[r.get("author")] = lines.get(r.get("author"), 0) + (r.get("added") or 0)
            rival = sorted(n for n, v in lines.items() if n != who and v == lines.get(who) and v)
            if rival:
                out.append(_complaint("tied_owner", f, f"{area}: {who} and {rival[0]}, both {lines[who]:,} lines"))
    return out


_ASIDE_SEGMENTS = frozenset({"test", "tests", "__tests__", "testing", "spec", "specs", "e2e", "fixtures", "__fixtures__", "testdata", "testsuite",
                             "vendor", "vendored", "third_party", "third-party", "node_modules", "examples", "example", "samples",
                             "dist", "build", "generated"})
_TEST_NAME = re.compile(r"(?i)(?:^|[._-])tests?(?:[._-]|$)")


def _set_aside(path: str, declared: list) -> bool:
    """A test, vendored, example or generated path by the ecosystem's conventions, or one the run lists as
    generated or vendored."""
    parts = path.split("/")
    return bool(_ASIDE_SEGMENTS & {s.lower() for s in parts[:-1]}) or bool(_TEST_NAME.search(parts[-1])) \
        or any(path == d or path.startswith(d.rstrip("/") + "/") for d in declared)


def unscored_executable(report: dict, found: list, clone: str, commit: str) -> list:
    """A tracked file with the executable bit (mode 100755) and a `#!` first line that the run has no size row
    and no revisions row for, outside test, vendored, example and generated paths: the repository runs it, and
    no table can show it. superpowers' hooks/session-start (31 commits, run at every session start) and five
    extensionless skills/*/scripts/ files were "not a source type"."""
    size = (report.get("size") or {}).get("files")
    if not size:
        return []
    meta = report.get("meta") or {}
    declared = [p for key in ("generated", "vendored") for p in meta.get(key) or [] if isinstance(p, str)]
    known = set(size) | {r.get("entity") for r in report.get("revisions") or []}
    done = _git(clone, "ls-tree", "-r", "-z", commit)
    paths = []
    for rec in done.stdout.split("\0"):
        head, _, path = rec.partition("\t")
        if head.startswith("100755 ") and path not in known and not _set_aside(path, declared):
            paths.append(path)
    firsts = _heads(clone, commit, sorted(paths), lines=1, size_limit=256)
    return [_complaint("unscored_executable", None, f"{p}: executable, starts {firsts[p][:40]!r}, in no table")
            for p in sorted(paths) if firsts.get(p, "").startswith("#!")]


_SAYS_REMOVED = re.compile(r"(?i)\bremoved\b|\bno longer\b|\bnothing (?:of it )?(?:survives|is left|remains)\b|\bdeleted\b")


def dead_import(report: dict, found: list, clone: str, commit: str) -> list:
    """An import the analysed commit holds nothing of: every path the import commit added is absent from the
    tree, and the finding still speaks of its surviving lines or never says it was removed. superpowers'
    7446c84 bundled a node_modules that 7619570 removed two days later; "credits its surviving lines to nobody"
    described zero lines."""
    head, out = None, []
    for f in found:
        if (f.get("rule") or {}).get("id") != "import_commits":
            continue
        detail = f.get("detail") or ""
        if _SAYS_REMOVED.search(detail) and "surviving" not in detail:
            continue
        for c in (f.get("evidence") or {}).get("commits") or []:
            done = _git(clone, "diff-tree", "--root", "--no-commit-id", "--name-only", "-r", "-z", "--diff-filter=A", str(c.get("hash") or ""))
            added = [p for p in done.stdout.split("\0") if p] if done.returncode == 0 and c.get("hash") else []
            if not added:
                continue
            head = head if head is not None else _in_head(clone, commit)
            if head and not any(p in head for p in added):
                why = "the text speaks of surviving lines" if "surviving" in detail else "the text does not say it was removed"
                out.append(_complaint("dead_import", f, f"{c['hash']}: none of the {len(added):,} paths it added is in the tree; {why}"))
    return out


def overrun_span(report: dict, found: list) -> list:
    """Any row the default Complex functions table prints whose line count is over twice the span the structure
    step measured for the function starting on the same line of the same file: lizard ran past the function's
    end (superpowers' extractAndStripFrontmatter, 339 lines printed for a function of 36). suspect_lead reads
    only the first row; a reader reads them all."""
    table = _render(report, "functions_section", full=False)
    spans = {(s.get("file"), s.get("start")): _span(s) for s in (report.get("structure") or {}).get("functions") or [] if s.get("end")}
    funcs = report.get("functions") or []
    out = []
    for row in (table or {}).get("rows") or [] if spans else []:
        name, where, ccn, lines = str(row[0]), str(row[1]), str(row[2]).rstrip("?+"), str(row[3]).replace(",", "")
        file, _, line = where.rpartition(":") if re.search(r":\d+$", where) else (where, "", "")
        if not lines.isdigit():
            continue
        for rec in funcs:
            if rec.get("file") == file and str(rec.get("ccn")) == ccn and (str(rec.get("start")) == line if line else rec.get("function") == name):
                span = spans.get((file, rec.get("start")))
                if span and int(lines) > 2 * span:
                    out.append(_complaint("overrun_span", None, f"{name} in {file}: {lines} lines printed, {span} to the structure step"))
                    break
    return out


_DEFAULT = (None, None)   # the last report rendered and its lines: five checks read the same default report


def _default_report(report: dict, found: list):
    """The default terminal report at 80 columns as a reader sees it, as lines; None when it cannot be drawn."""
    global _DEFAULT
    if _DEFAULT[0] is report:
        return _DEFAULT[1]
    lines = None
    try:
        import io

        from rich.console import Console

        from .. import render
        buf = io.StringIO()
        render.report({"out_dir": "", **report}, found, Console(file=buf, width=80, color_system=None, force_terminal=False), full=False)
        lines = buf.getvalue().splitlines()
    except Exception:   # an export the renderer cannot read is not these checks' to judge
        lines = None
    _DEFAULT = (report, lines)
    return lines


def _running(lines: list) -> str:
    """The whole report as one line of running text, box characters dropped: a sentence a panel wrapped reads
    as a sentence again."""
    return " ".join(re.sub(r"[│╭╮╰╯─]", " ", " ".join(lines)).split())


_SUPPLY_CHAIN = re.compile(r"^(?:\S+ )?Supply chain\s*$")   # the section's title line, behind its pictogram or without one
_GRID_LABEL = re.compile(r"^ {2}\S")                        # a row of its label grid starts two in; what a row wraps to starts further in
_FINDINGS = re.compile(r"^(?:\S+ )?Findings(?: · .*)?$")    # the Findings title line once it has no box around it, with its tally or bare
_RULE = re.compile(r"^\s*─+\s*$")                           # the rule under a table's column heads


def _joined(lines: list) -> str:
    return " ".join(" ".join(lines).split())


def _grid_rows(lines: list) -> list:
    """The rows of a label grid as running text, one each: a row starts two in, and what it wraps to starts
    further in and belongs to the row above it."""
    rows = []
    for l in lines:
        if _GRID_LABEL.match(l) or not rows:
            rows.append([l])
        else:
            rows[-1].append(l)
    return [_joined(row) for row in rows]


def _unboxed(block: list) -> list:
    """One run of lines between two blank ones, outside any box, as its chunks. A table (it has a rule under
    its column heads) is a chunk a line, as it always was. From the output plan's item A11 the header and the
    Findings have no box either, and are told by their shape: the Findings block opens with its title line and
    each entry starts at column 1 with its mark, its statement, subject lines and step wrapped under it, so an
    entry is one running text; the header is a title line over a label grid, each row of which is a chunk (a
    row that ends in a number is not counting the next row's label, "files" or "commits"). Anything else is a
    chunk a line."""
    if any(_RULE.match(l) for l in block):
        return list(block)
    if _FINDINGS.match(block[0]):
        entries = []
        for l in block[1:]:
            if l[:1] != " " or not entries:
                entries.append([l])
            else:
                entries[-1].append(l)
        return [block[0]] + [_joined(e) for e in entries]
    if len(block) > 1 and block[0][:1] != " " and all(l.startswith("  ") for l in block[1:]):
        return [block[0]] + _grid_rows(block[1:])
    return list(block)


def _chunks(lines: list) -> list:
    """The report as the pieces a count phrase can sit in: the panels' text and the footer each as running text
    (both wrap mid-sentence), every table line on its own (joining rows would put one row's last number before
    the next row's first word).

    The header and the Findings are read in either drawing. Until the output plan's item A11 they are two
    boxes, every line of which starts with a border, and their text is one running text. From A11 they are
    unboxed blocks, read by their shape (_unboxed).

    The footer is read in either drawing. Until the output plan's item A10 it is the lines from "Secrets:" to
    the end, one running text. From A10 it is a titled Supply chain section, last in the report: a label grid,
    each row of which wraps under its own label and is a chunk of its own (a row that ends in a number is not
    counting the next row's label, "dependencies"), then a blank line and the closing lines, which are one
    running text."""
    panel = [l.strip("│ ") for l in lines if l.startswith("│")]
    old = next((i for i, l in enumerate(lines) if l.startswith("Secrets:")), None)
    new = next((i for i, l in enumerate(lines) if _SUPPLY_CHAIN.match(l)), None)
    at = old if old is not None else new if new is not None else len(lines)
    rest, block = [], []
    for l in [l for l in lines[:at] if not l.startswith(("│", "╭", "╰"))] + [""]:
        if l.strip():
            block.append(l)
        elif block:
            rest += _unboxed(block)
            block = []
    said = [_joined(panel)]
    if old is None and new is not None:
        tail = lines[at + 1:]
        end = next((i for i, l in enumerate(tail) if not l.strip()), len(tail))
        return said + _grid_rows(tail[:end]) + [_joined(tail[end:])] + rest
    return said + [_joined(lines[at:])] + rest


TRUCK_MIN_FILES = 20   # the floor the truck factor's rule documents (findings.truck_factor's min_files), stated here and not imported
_TRUCK_FACTOR_GIVEN = re.compile(r"(?i)truck factor (?:of |is )?\d")
_TRUCK_FACTOR_UNSAID = re.compile(r"(?i)\b(?:no|without a) truck factor\b|truck factor[^.]{0,120}?\b(?:not (?:computed|measured|calculated|run)|"
                                  r"needs|too few|fewer than|under \d+)")


def _dominant(report: dict):
    """(name, share) of the person with the most authored commits, tools left out; None without identities."""
    tools = harness_tools(report)
    counts = {}
    for i in (report.get("meta") or {}).get("identities") or []:
        if i.get("name") not in tools:
            n = i.get("authored") if i.get("authored") is not None else i.get("commits") or 0
            counts[i.get("name")] = counts.get(i.get("name"), 0) + n
    total = sum(counts.values())
    if not total:
        return None
    name = max(sorted(counts), key=lambda k: counts[k])
    return name, counts[name] / total


def silent_measure(report: dict, found: list) -> list:
    """A measure the report did not compute and does not mention. The truck factor: no finding gives one, the
    scored pool is under the rule's floor of 20 files, one person authored half the commits or more (the case
    the measure exists for), and no sentence of the default report says it was not computed; superpowers had 17
    scored files and one author of 78% of the commits. The backtest: the run records that it did not run and
    the default report never uses the word. The bug magnets' size test is silent_precondition's."""
    lines = _default_report(report, found)
    if lines is None:
        return []
    text = _running(lines)
    out = []
    scored = ((report.get("meta") or {}).get("coverage") or {}).get("scored")
    top = _dominant(report)
    given = any((f.get("rule") or {}).get("id") == "truck_factor" or _TRUCK_FACTOR_GIVEN.search(f.get("detail") or "") for f in found)
    if not given and scored and scored < TRUCK_MIN_FILES and top and top[1] >= 0.5 and not _TRUCK_FACTOR_UNSAID.search(text):
        out.append(_complaint("silent_measure", None, f"truck factor: not computed ({scored} scored files, needs {TRUCK_MIN_FILES}) and not said; "
                                                      f"{top[0]} authored {top[1]:.0%} of the commits"))
    backtest = (report.get("meta") or {}).get("backtest") or {}
    if backtest.get("status") and backtest["status"] != "run" and "backtest" not in text.lower():
        out.append(_complaint("silent_measure", None, f"backtest: {backtest['status']} ({backtest.get('reason') or 'no reason recorded'}) and not said"))
    return out


_NO_TABLE = ("not a source type", "not counted by scc")   # the coverage buckets no table of the report carries, hidden or shown
_COVERAGE_SAID = re.compile(r"(?i)\b(?:un|not[- ])scored\b|\bnot (?:a )?source\b|\bscored?:? [\d,]+ of [\d,]+|\b[\d,]+ (?:of [\d,]+ )?(?:files|lines) scored\b")


def coverage_unsaid(report: dict, found: list) -> list:
    """The tracked files no table carries (the run's own coverage count of "not a source type" and "not counted
    by scc"; test, vendored and generated files are in the tables, hidden) outnumber the files it scored, and
    the default report has no line naming unscored or not-scored files or lines. superpowers: 120 against 17,
    under a header that read "10,442 lines in 71 files"."""
    cov = (report.get("meta") or {}).get("coverage") or {}
    scored, unseen = cov.get("scored") or 0, sum(cov.get(k) or 0 for k in _NO_TABLE)
    if unseen <= scored:
        return []
    lines = _default_report(report, found)
    if lines is None or _COVERAGE_SAID.search(_running(lines)):
        return []
    return [_complaint("coverage_unsaid", None, f"{unseen:,} tracked files are in no table, {scored:,} are scored; the default report does not say so")]


def fix_episode(report: dict, found: list, clone: str, commit: str) -> list:
    """A bug magnet whose recent fixes all fall in fewer than three distinct ISO weeks, by the author dates git
    has for the fix commits the export lists (fix_history): one episode of work, a fix and its follow-ups, read
    as a file that keeps breaking. superpowers' three magnets were fixed over one three-day stretch. Information
    for a rule that counts episodes, recorded before that rule is written; skipped when the export lists no
    fix commits."""
    history = report.get("fix_history") or {}
    named = []
    for f in found:
        if (f.get("rule") or {}).get("id") == "bug_magnets":
            named += [(f, r.get("file")) for r in (f.get("evidence") or {}).get("files") or [] if isinstance(r, dict)]
    hashes = sorted({h for _, path in named for h in (history.get(path) or {}).get("recent") or []})
    if not hashes:
        return []
    done = _git(clone, "log", "--no-walk=unsorted", "--format=%H %ad", "--date=format:%G-W%V", *hashes)
    if done.returncode != 0:
        return []
    weeks = dict(l.split(" ", 1) for l in done.stdout.splitlines() if " " in l)
    out = []
    for f, path in named:
        recent = (history.get(path) or {}).get("recent") or []
        when = [next((w for full, w in weeks.items() if full.startswith(h)), None) for h in recent]
        if len(recent) >= 3 and all(when) and len(set(when)) < 3:
            out.append(_complaint("fix_episode", f, f"{path}: {len(recent)} recent fixes in {len(set(when))} week(s) ({', '.join(sorted(set(when)))})"))
    return out


# the nouns gitmole counts in the default report; a closed list, so a table cell beside a word is not a phrase
_COUNTED = ("packages", "lock files", "files", "commits", "identities", "authors", "people", "functions", "lines", "areas", "pairs",
            "manifests", "workflows", "places", "values", "hits", "notes", "warnings", "criticals", "spans", "tools", "coding tools",
            "months", "times", "steps", "directories", "contributors", "findings", "secrets", "dependencies")
_PLURAL_ONE = re.compile(r"(?<![\w,.\-/:])1 (" + "|".join(sorted(_COUNTED, key=len, reverse=True)) + r")\b")


def plural_one(report: dict, found: list) -> list:
    """A count of one before a plural, in a phrase gitmole writes into the default report: superpowers'
    "osv-scanner checked 1 packages in 1 lock file", twice."""
    lines = _default_report(report, found)
    if lines is None:
        return []
    seen = []
    for chunk in _chunks(lines):
        for m in _PLURAL_ONE.finditer(chunk):
            seen.append(m.group(0))
    return [_complaint("plural_one", None, f"'{phrase}' ({seen.count(phrase)}x)") for phrase in sorted(set(seen))]


# --- the checks the 0.44.0 review of a pnpm monorepo added (dream-num/univer) --------------------------------
#
# h1 to h7 of that review's plan. Each reads the lock, the manifests, the workflows, the identities or the trend
# samples itself, and none calls the function it judges (hygiene._locked_part, deps.deploys, locks.pnpm_runtime,
# hygiene.trojan_source, identity.same_person, findings._action_trust, findings.magnet_rows). Where the plan asks,
# a check is two-sided: it complains of a claim the evidence does not bear out and of evidence no claim was made
# for, so a change that deletes a finding outright does not turn it green.

_PNPM_GROUPS = ("dependencies", "devDependencies", "optionalDependencies")


def _override_name(key: str) -> str:
    """The package an entry of a pnpm `overrides:` map is about: `foo`, `foo@<2`, `bar>foo`, `@s/foo@1`."""
    key = _unquote(key).rsplit(">", 1)[-1]
    at = key.find("@", 1)
    return key[:at] if at > 0 else key


def _pnpm_specifiers(text: str) -> tuple:
    """({importer: {(group, name): specifier}}, the names the lock's `overrides:` lists), read by indentation.
    Lock files v6 and v9 write a `specifier:` under each dependency of an importer; v5 writes one `specifiers:`
    block per importer, read here with the group '*'. A v10 lock's first YAML document (`packageManagerDependencies`)
    has no group this reads."""
    out, overridden = {}, set()
    section = cur = group = dep = None
    for line in text.splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        ind = len(line) - len(line.lstrip(" "))
        if ind == 0:
            section, cur, group, dep = _yaml_key(s)[0], None, None, None
            continue
        if section == "overrides" and ind == 2:
            overridden.add(_override_name(_yaml_key(s)[0]))
        elif section in _PNPM_GROUPS + ("specifiers",):   # a lock without a workspace (v5, v6): one importer, at the top
            here = out.setdefault(".", {})
            if ind == 2:
                dep, value = _yaml_key(s)
                if section == "specifiers":
                    here[("*", dep)] = _unquote(value)
            elif ind == 4 and section != "specifiers" and s.startswith("specifier:"):
                here[(section, dep)] = _unquote(s.split(":", 1)[1])
        elif section == "importers":
            if ind == 2:
                cur, group = _yaml_key(s)[0], None
                out.setdefault(cur, {})
            elif ind == 4 and cur is not None:
                group = _yaml_key(s)[0]
            elif ind == 6 and cur is not None and group:
                dep, value = _yaml_key(s)
                if group == "specifiers":
                    out[cur][("*", dep)] = _unquote(value)
            elif ind == 8 and cur is not None and group in _PNPM_GROUPS and s.startswith("specifier:"):
                out[cur][(group, dep)] = _unquote(s.split(":", 1)[1])
    return out, overridden


def _manifest_specifiers(declared: dict, merged: bool) -> dict:
    out = {}
    for group in _PNPM_GROUPS:
        for name, spec in (declared.get(group) or {}).items() if isinstance(declared.get(group), dict) else ():
            out[("*" if merged else group, name)] = str(spec)
    return out


def _json_at(clone: str, commit: str, path: str):
    try:
        data = json.loads(_blob(clone, commit, path) or "null")
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


def _importer_manifest(lock: str, importer: str) -> str:
    root = os.path.dirname(lock)
    member = os.path.normpath(os.path.join(root, importer)).replace(os.sep, "/") if importer not in ("", ".") else root
    member = "" if member == "." else member
    return (member + "/" if member else "") + "package.json"


def _specifier_diff(clone: str, commit: str, lock: str, importer: str, recorded: dict, overridden: set):
    """None when the manifest is not at the commit; else the (group, name, manifest's, lock's) that differ."""
    declared = _json_at(clone, commit, _importer_manifest(lock, importer))
    if declared is None:
        return None
    merged = any(g == "*" for g, _ in recorded)
    wrote = _manifest_specifiers(declared, merged)
    keys = sorted(k for k in set(wrote) | set(recorded) if k[1] not in overridden)
    return [(g, n, wrote.get((g, n)), recorded.get((g, n))) for g, n in keys if wrote.get((g, n)) != recorded.get((g, n))]


def _drift_claims(report: dict, found: list):
    """(the drift rows the lockfile_drift finding counts, whether that list is complete): the run's stored rows,
    else the finding's, without the ones whose every recorded change the report left out as sweeping."""
    f = next((f for f in found if (f.get("rule") or {}).get("id") == "lockfile_drift"), None)
    if f is None:
        return [], (report.get("hygiene") or {}).get("lockfiles") is not None, None
    stored = ((report.get("hygiene") or {}).get("lockfiles") or {}).get("drift")
    rows = stored if isinstance(stored, list) and stored else (f.get("evidence") or {}).get("drift") or []
    swept = {s["hash"] for s in (report.get("activity") or {}).get("sweeping") or [] if s.get("hash")}

    def counted(d):
        changes = [c.get("commit") for c in d.get("changes") or [] if c.get("commit")]
        return not changes or not all(any(c.startswith(h) or h.startswith(c) for h in swept) for c in changes)
    rows = [d for d in rows if counted(d)]
    count = (f.get("evidence") or {}).get("count") or len(rows)
    return rows, len(rows) >= count, f


def pnpm_specifiers(report: dict, found: list, clone: str, commit: str) -> list:
    """h1, both ways, for pnpm locks: a manifest the drift finding says changed after its lock while every
    specifier it declares equals the one the lock's `importers` entry records (univer's 82, all release version
    bumps: pnpm does not record a package's own version), and a member whose specifiers differ from the lock's
    with no drift claimed. The second side is judged only when the claims are all stored."""
    claims, complete, f = _drift_claims(report, found)
    out, cache = [], {}

    def lock_of(lock):
        if lock not in cache:
            cache[lock] = _pnpm_specifiers(_blob(clone, commit, lock))
        return cache[lock]
    claimed = set()
    for d in claims:
        lock, manifest = d.get("lockfile") or "", d.get("manifest") or ""
        claimed.add((lock, manifest))
        if os.path.basename(lock) != "pnpm-lock.yaml":
            continue
        importers, overridden = lock_of(lock)
        importer = next((i for i in importers if _importer_manifest(lock, i) == manifest), None)
        if importer is None:
            continue
        diff = _specifier_diff(clone, commit, lock, importer, importers[importer], overridden)
        if diff == []:
            out.append(_complaint("drift_specifiers_agree", f, f"{manifest}: drift claimed, every specifier equals {lock}'s"))
    if not complete:
        return out
    for lock in sorted(p for p in _in_head(clone, commit) if os.path.basename(p) == "pnpm-lock.yaml" and "node_modules/" not in p):
        importers, overridden = lock_of(lock)
        for importer in sorted(importers):
            manifest = _importer_manifest(lock, importer)
            if (lock, manifest) in claimed:
                continue
            diff = _specifier_diff(clone, commit, lock, importer, importers[importer], overridden)
            if diff:
                g, n, mine, theirs = diff[0]
                out.append(_complaint("drift_unclaimed", f, f"{manifest}: {len(diff)} specifier(s) differ from {lock} "
                                                            f"(e.g. {n}: {mine!r} declared, {theirs!r} locked); no drift claimed"))
    return out


_ENTRY_POINT = re.compile(r"^(\S*package\.json) \S+$")


def _private(clone: str, commit: str, manifest: str) -> bool:
    return ((_json_at(clone, commit, manifest) or {}).get("private")) is True


def private_vulns(report: dict, found: list, clone: str, commit: str) -> list:
    """h2, both ways. A critical vulnerable-dependencies finding whose every deploy declaration is an entry point
    of a package.json that declares `"private": true` (univer's common/shared bin: a private package is never
    published, so its `bin` ships nothing). And a row of a pnpm lock that this check's own walk reaches from the
    runtime dependencies of a member that is not private, shown as development-only or in a note: whatever a
    fix demotes, a published member's runtime dependency stays at a warning or above."""
    out = []
    for f in found:
        if (f.get("rule") or {}).get("id") != "vulnerable_dependencies" or f.get("severity") != "critical":
            continue
        deploys = sorted({d for r in (f.get("evidence") or {}).get("packages") or [] for d in r.get("deploys") or []})
        manifests = [_ENTRY_POINT.match(d) for d in deploys]
        if deploys and all(m and _private(clone, commit, m.group(1)) for m in manifests):
            out.append(_complaint("private_critical", f, f"critical on deploy evidence that is all private: {', '.join(deploys)}"))
    sev = {}
    for f in found:
        if ((f.get("rule") or {}).get("id") or "").startswith("vulnerable_dependencies"):
            for r in (f.get("evidence") or {}).get("packages") or []:
                sev.setdefault((r.get("source"), r.get("name"), r.get("version")), (f.get("severity"), f))
    rows = [r for r in (report.get("dependencies") or {}).get("vulnerable") or [] if (r.get("source") or "").endswith("pnpm-lock.yaml")]
    reach = {}
    for r in rows:
        lock = r["source"]
        if lock not in reach:
            importers, graph = _pnpm(_blob(clone, commit, lock))
            published = {i for i in importers if (_json_at(clone, commit, _importer_manifest(lock, i)) or {"private": True}).get("private") is not True}
            reach[lock] = _reach(importers, graph, ("dependencies", "optionalDependencies"), roots=published)
        if f"{r.get('name')}@{r.get('version')}" not in reach[lock]:
            continue
        shown, f = sev.get((lock, r.get("name"), r.get("version")), (None, None))
        if r.get("runtime") is False:
            out.append(_complaint("published_demoted", f, f"{r['name']} {r.get('version')} in {lock}: a published member's runtime dependency, said to be development-only"))
        elif shown and shown not in GATED:
            out.append(_complaint("published_demoted", f, f"{r['name']} {r.get('version')} in {lock}: a published member's runtime dependency, shown as {shown}"))
    return out


# the harness's own copy of the letters of Cyrillic, Greek and Armenian that pass for Latin ones (UTS #39)
_LOOKS_LATIN = set("аеорсухіјѕһԁӏүАВЕКМНОРСТХІЈЅҮοανριγυΑΒΕΖΗΙΚΜΝΟΡΤΥΧօսհոցզ")
_C_FAMILY = {".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs", ".mts", ".cts", ".java", ".c", ".h", ".cc", ".cpp", ".hpp", ".cs", ".go",
             ".rs", ".swift", ".kt", ".kts", ".scala", ".php", ".dart", ".m", ".mm", ".groovy"}
_HASH_FAMILY = {".py", ".rb", ".sh", ".bash", ".pl", ".r", ".yml", ".yaml", ".toml"}
_REGEX_BEFORE = set("(,=:[!&|?{};+-*%<>~^") | {""}


def _lex(text: str, ext: str) -> list:
    """(start, end, kind) of every comment, string and regular-expression literal of a file, kind one of
    'comment', 'string', 'regex': a small lexer of its own for the C family (with template literals and
    JavaScript regex literals) and the `#` family, enough to say where a token sits, not to parse."""
    spans, i, n = [], 0, len(text)
    cfam, hfam = ext in _C_FAMILY, ext in _HASH_FAMILY
    js = ext in {".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs", ".mts", ".cts"}
    stack, last = [], ""   # open `${` of template literals (brace depth each); the last significant code character

    def string_end(j, q):
        while j < n:
            c = text[j]
            if c == "\\":
                j += 2
                continue
            if c == q or (c == "\n" and q != "`" and len(q) == 1):
                return j + 1
            if q == "`" and text.startswith("${", j):
                return j
            if len(q) == 3 and text.startswith(q, j):
                return j + 3
            j += 1
        return n
    while i < n:
        c = text[i]
        if cfam and text.startswith("//", i):
            j = text.find("\n", i)
            j = n if j < 0 else j
            spans.append((i, j, "comment"))
            i = j
        elif cfam and text.startswith("/*", i):
            j = text.find("*/", i + 2)
            j = n if j < 0 else j + 2
            spans.append((i, j, "comment"))
            i = j
        elif hfam and c == "#":
            j = text.find("\n", i)
            j = n if j < 0 else j
            spans.append((i, j, "comment"))
            i = j
        elif c in "'\"" or (c == "`" and cfam):
            q = text[i:i + 3] if ext == ".py" and text[i:i + 3] in ('"""', "'''") else c
            j = string_end(i + len(q), q)
            spans.append((i, j, "string"))
            if q == "`" and text.startswith("${", j):
                stack.append(0)
                j += 2
            i, last = j, '"'
        elif js and c == "/" and (last in _REGEX_BEFORE or re.search(r"\b(?:return|typeof|case|in|of|void|delete)\s*$", text[max(0, i - 12):i])):
            j, cls = i + 1, False
            while j < n and text[j] != "\n":
                if text[j] == "\\":
                    j += 2
                    continue
                if text[j] == "[":
                    cls = True
                elif text[j] == "]":
                    cls = False
                elif text[j] == "/" and not cls:
                    break
                j += 1
            spans.append((i, min(j + 1, n), "regex"))
            i, last = j + 1, "/"
        elif stack and c == "{":
            stack[-1] += 1
            i, last = i + 1, c
        elif stack and c == "}":
            if stack[-1] == 0:   # the end of a `${…}`: the template literal goes on
                stack.pop()
                j = string_end(i + 1, "`")
                spans.append((i, j, "string"))
                if text.startswith("${", j):
                    stack.append(0)
                    j += 2
                i, last = j, '"'
            else:
                stack[-1] -= 1
                i, last = i + 1, c
        else:
            if not c.isspace():
                last = c if not (c.isalnum() or c in "_$") else "a"
            i += 1
    return spans


def _scripts_of(token: str) -> set:
    import unicodedata
    out = set()
    for ch in token:
        if ch.isalpha():
            try:
                out.add(unicodedata.name(ch).split()[0])
            except ValueError:
                pass
    return out


def _inert(text: str, spans: list, at: int, token: str):
    """Why a mixed-script token at offset `at` is no identifier, or None: it sits in a comment; it is the end of
    a range in a character class (`[A-Za-zА-Яа-я]`, read as `zА`); or it sits in a literal that also holds a whole
    word written in the token's other script (Russian prose naming ZТЕСТ). A literal holding only the token
    (`"аdmin"`) is not inert: a homoglyph compared against is the attack."""
    span = next((s for s in spans if s[0] <= at < s[1]), None)
    if span is None:
        return None
    kind = span[2]
    if kind == "comment":
        return "in a comment"
    inside = text[span[0]:at]
    if inside.rfind("[") > inside.rfind("]") and "-" in (text[at - 1:at], text[at + len(token):at + len(token) + 1]):
        return "a character-class range"
    if kind == "string":
        other = _scripts_of(token) - {"LATIN"}
        for word in re.findall(r"[^\W\d_]+", text[span[0]:span[1]]):
            if word != token and len(word) >= 2 and _scripts_of(word) and _scripts_of(word) <= other:
                return f"in a literal that holds the word {word!r}"
    return None


def _occurrences(text: str, line: int, token: str) -> list:
    starts = [0] + [m.end() for m in re.finditer("\n", text)]
    if not 0 < line <= len(starts):
        return []
    base = starts[line - 1]
    end = starts[line] if line < len(starts) else len(text)
    return [base + m.start() for m in re.finditer(r"(?<!\w)" + re.escape(token) + r"(?!\w)", text[base:end])]


_MIXED_CANDIDATE = r"[\x{0370}-\x{03FF}\x{0400}-\x{052F}\x{0530}-\x{058F}]"


def trojan_tokens(report: dict, found: list, clone: str, commit: str) -> list:
    """h3, both ways, by this check's own lexer. A mixed-script token the trojan_source finding counts that sits
    only where it cannot be an identifier: a comment, a character-class range, a literal that holds whole words
    of the token's other script (univer's three). And a token in code that mixes Latin with look-alike letters
    of another script, in a source file outside tests, vendored and generated code, that no stored row names: the
    finding must still fire on `pаssword = 1`. The second side is judged only when every row is stored."""
    trojan = (report.get("hygiene") or {}).get("trojan")
    if not isinstance(trojan, dict):
        return []
    f = next((f for f in found if (f.get("rule") or {}).get("id") == "trojan_source"), None)
    rows = trojan.get("mixed_script") or []
    texts, lexed, out = {}, {}, []

    def read(path):
        if path not in texts:
            texts[path] = _blob(clone, commit, path)
            lexed[path] = _lex(texts[path], os.path.splitext(path)[1].lower())
        return texts[path], lexed[path]
    for r in rows if f else ():
        text, spans = read(r.get("file") or "")
        at = _occurrences(text, int(r.get("line") or 0), r.get("token") or "")
        why = [_inert(text, spans, a, r["token"]) for a in at]
        if at and all(why):
            out.append(_complaint("trojan_inert", f, f"{r['token']} at {r['file']}:{r['line']}: {why[0]}"))
    if len(rows) < (trojan.get("mixed_script_count") or 0):
        return out
    meta = report.get("meta") or {}
    declared = [p for key in ("generated", "vendored") for p in meta.get(key) or [] if isinstance(p, str)]
    named = {(r.get("file"), r.get("line")) for r in rows}
    done = _git(clone, "grep", "-n", "-I", "-P", "-e", _MIXED_CANDIDATE, commit, "--")
    for hit in done.stdout.splitlines():
        parts = hit.split(":", 3)
        if len(parts) < 4 or not parts[2].isdigit():
            continue
        path, line = parts[1], int(parts[2])
        ext = os.path.splitext(path)[1].lower()
        if ext not in _C_FAMILY | _HASH_FAMILY - {".yml", ".yaml", ".toml"} or _set_aside(path, declared) \
                or "docs" in path.split("/")[:-1] or (path, line) in named:
            continue
        for token in re.findall(r"\w+", parts[3]):
            other = [ch for ch in token if ch.isalpha() and not ch.isascii()]
            if not other or not any(ch.isascii() and ch.isalpha() for ch in token) or not all(ch in _LOOKS_LATIN for ch in other):
                continue
            text, spans = read(path)
            if any(_inert(text, spans, a, token) is None and not any(s[0] <= a < s[1] for s in spans if s[2] != "string")
                   for a in _occurrences(text, line, token)):
                out.append(_complaint("trojan_missed", f, f"{token} at {path}:{line}: outside comments, regexes and prose literals, and no row names it"))
                break
    return out


_FORGE_LOGIN = re.compile(r"^(?:\d+\+)?([A-Za-z0-9][A-Za-z0-9-]*)@users\.noreply\.", re.I)


def noreply_split(report: dict, found: list) -> list:
    """h4: two identities left apart although one's forge address is the other's account: `<id>+<login>@users.
    noreply.<forge>` belongs to one identity and `login` is another's one-word name (univer's "Univer" at
    68851825+DR-Univer@… and "DR-Univer"). Read by this regex over the identities and their aliases, never
    by identity.same_person."""
    ids = (report.get("meta") or {}).get("identities") or []
    by_name = {}
    for i in ids:
        name = i.get("name") or ""
        if name and not re.search(r"\s", name):
            by_name.setdefault(name.casefold(), set()).add(name)
    out, seen = [], set()
    for i in ids:
        for _, email in _addresses(i):
            m = _FORGE_LOGIN.match(email or "")
            if not m:
                continue
            for other in sorted(by_name.get(m.group(1).casefold(), ())):
                pair = tuple(sorted((i.get("name"), other)))
                if other != i.get("name") and pair not in seen:
                    seen.add(pair)
                    out.append(_complaint("noreply_split", None, f"{i.get('name')} <{email}> and {other}: the address's login is the other identity's name"))
    return out


_VERSION_REF = re.compile(r"^v?\d+(?:\.\d+)*$")
_FULL_SHA = re.compile(r"^[0-9a-f]{40}$")
_GRANT = re.compile(r"\b(?:id-token|contents)\s*:\s*write\b|\bwrite-all\b")


def _block(lines: list, at: int) -> list:
    """The lines under the key on line `at`: its inline value and every deeper line after it."""
    ind = len(lines[at]) - len(lines[at].lstrip(" "))
    out = [lines[at].split(":", 1)[1] if ":" in lines[at] else ""]
    for ln in lines[at + 1:]:
        if ln.strip() and not ln.strip().startswith("#") and len(ln) - len(ln.lstrip(" ")) <= ind:
            break
        out.append(ln)
    return out


def _no_comments(lines: list) -> str:
    return "\n".join(l.split(" #", 1)[0] for l in lines if not l.strip().startswith("#"))


def _workflow_steps(text: str) -> list:
    """(uses, secrets, grants) for each step of a workflow that uses an action: secrets when the step or its
    job's env: reads `secrets.`, grants when the workflow's or the job's permissions give id-token or contents
    write, or write-all."""
    lines = text.splitlines()
    code = lambda l: l.strip() and not l.strip().startswith("#")
    top = next((k for k, l in enumerate(lines) if re.match(r"^permissions\s*:", l)), None)
    wf_grant = bool(top is not None and _GRANT.search(_no_comments(_block(lines, top))))
    start = next((k for k, l in enumerate(lines) if re.match(r"^jobs\s*:", l)), None)
    if start is None:
        return []
    end = next((k for k in range(start + 1, len(lines)) if code(lines[k]) and not lines[k].startswith(" ")), len(lines))
    child = next((len(lines[k]) - len(lines[k].lstrip(" ")) for k in range(start + 1, end) if code(lines[k])), None)
    heads = [k for k in range(start + 1, end) if code(lines[k]) and len(lines[k]) - len(lines[k].lstrip(" ")) == child]
    out = []
    for h, head in enumerate(heads):
        stop = heads[h + 1] if h + 1 < len(heads) else end
        body = range(head + 1, stop)
        key_ind = next((len(lines[k]) - len(lines[k].lstrip(" ")) for k in body if code(lines[k])), None)
        job_env, job_grant = "", False
        for k in body:
            if code(lines[k]) and len(lines[k]) - len(lines[k].lstrip(" ")) == key_ind:
                key = lines[k].strip().split(":", 1)[0]
                if key == "env":
                    job_env = _no_comments(_block(lines, k))
                elif key == "permissions":
                    job_grant = bool(_GRANT.search(_no_comments(_block(lines, k))))
        for k in body:
            m = re.match(r"^(\s*)(-\s+)?uses\s*:\s*['\"]?([^'\"\s#]+)", lines[k])
            if not m:
                continue
            item = k if m.group(2) else next((j for j in range(k - 1, head, -1) if re.match(r"^\s*-\s", lines[j])), k)
            ind = len(lines[item]) - len(lines[item].lstrip(" "))
            last = next((j for j in range(item + 1, stop) if code(lines[j]) and len(lines[j]) - len(lines[j].lstrip(" ")) <= ind), stop)
            step = _no_comments(lines[item:last])
            out.append((m.group(3), "secrets." in step or "secrets." in job_env, wf_grant or job_grant))
    return out


def action_order(report: dict, found: list, clone: str, commit: str) -> list:
    """h5: the action the pinning advice names first, against this check's own order over the workflows read
    from the clone: another account's action before the repository's own account's before GitHub's actions/ and
    github/ (the trust tier), then a branch-shaped ref (anything but `v1`, `1.2.3`) before a version, then a
    step given secrets or a job granted id-token/contents write before one that is not. univer's advice named
    codecov/codecov-action@v7 while jikkai/sync-gitee@main was handed secrets.GITEE_PASSWORD."""
    f = next((f for f in found if (f.get("rule") or {}).get("id") == "unpinned_actions"), None)
    m = re.search(r"Pin (\S+) to a full commit SHA first", (f or {}).get("advice") or "")
    if not m:
        return []
    owner = ((((report.get("hygiene") or {}).get("actions") or {}).get("origin")) or {})
    home = (owner.get("owner") or "").lower() if owner.get("host") == "github.com" else None
    rows = []
    for path in sorted(p for p in _in_head(clone, commit) if re.match(r"^\.github/workflows/[^/]+\.ya?ml$", p)):
        for uses, secrets, grants in _workflow_steps(_blob(clone, commit, path)):
            if uses.startswith(("./", "docker://")) or "@" not in uses or _FULL_SHA.match(uses.rsplit("@", 1)[1]):
                continue
            who = uses.split("/", 1)[0].lower()
            tier = 2 if who in ("actions", "github") else 1 if home and who == home else 0
            rows.append(((tier, bool(_VERSION_REF.match(uses.rsplit("@", 1)[1])), not (secrets or grants)), path, uses))
    named = [r for r in rows if r[2] == m.group(1)]
    if not rows or not named:
        return []
    best, mine = min(rows), min(named)
    if best[0] < mine[0]:
        why = ", ".join(w for w, on in (("another account's", best[0][0] == 0), ("a branch ref", not best[0][1]),
                                         ("given secrets or a write grant", not best[0][2])) if on)
        return [_complaint("action_order", f, f"advice names {m.group(1)}; {best[2]} in {best[1]} ranks first ({why})")]
    return []


GROWTH_FLOOR = 25   # percent: the floor findings.complexity_growth states (trend.GROWTH_FLOOR), stated here and not imported


def _year_before(date: str) -> str:
    y, mo, d = (int(x) for x in date[:10].split("-"))
    return f"{y - 1:04d}-{mo:02d}-{min(d, 28) if mo == 2 else d:02d}"


def split_density(report: dict, found: list) -> list:
    """h6: "Split <file>" advised for a file whose complexity per line of code rose less than the growth floor
    over the year the finding speaks of, read from the trend samples: the summed complexity grew with the code,
    not inside it (univer's doc-skeleton.ts, +418% summed, +11% per line). Agreement, not proof: the fix the
    review planned uses the same condition."""
    out = []
    series = (report.get("trend") or {}).get("files") or {}
    last = (report.get("meta") or {}).get("last_date") or ""
    for f in found:
        m = re.search(r"Split (\S+) before", f.get("advice") or "") if (f.get("rule") or {}).get("id") == "complexity_growth" else None
        rows = series.get(m.group(1)) if m else None
        if not rows or not last:
            continue
        before = [s for s in rows if s[0] <= _year_before(last)]
        if not before or not before[-1][1] or not before[-1][2] or not rows[-1][2]:
            continue
        then, now = before[-1][1] / before[-1][2], rows[-1][1] / rows[-1][2]
        rise = round(100 * (now - then) / then)
        if rise < GROWTH_FLOOR:
            out.append(_complaint("split_density", f, f"Split advised for {m.group(1)}: complexity per line {rise:+d}% since {before[-1][0]}"))
    return out


_LOCALE_FILE = re.compile(r"(?:^|/)[a-z]{2,3}(?:-[A-Z][a-z]{3})?[-_](?:[A-Z]{2}|\d{3})\.[A-Za-z0-9]+$"
                          r"|(?:^|/)(?:locales?|i18n)/(?:[^/]+/)*[a-z]{2,3}\.[A-Za-z0-9]+$")


def locale_magnet(report: dict, found: list) -> list:
    """h7: bug-magnet rows that are locale files by the shape of their name (`ru-RU.ts`, `zh-Hant-TW.json`,
    `es_419.po`; a bare `de.json` only under locale/, locales/ or i18n/): a translation touched by every fix
    that adds a string is not where the bug was (univer: 82 of 287). Rows read from the export's fix table at
    the finding's own min_recent, tests and files gone from the tree left out by the paths' convention and the
    size table, never through findings.magnet_rows. Agreement, not proof: the fix the review planned keys on
    the same shape."""
    out = []
    size = set(((report.get("size") or {}).get("files")) or {})
    for f in found:
        if (f.get("rule") or {}).get("id") != "bug_magnets":
            continue
        least = (f.get("rule") or {}).get("min_recent") or 3
        rows = [r.get("entity") or "" for r in report.get("fixes") or [] if (r.get("recent-fixes") or 0) >= least]
        hit = sorted(p for p in rows if _LOCALE_FILE.search(p) and (not size or p in size) and not _set_aside(p, []))
        if hit:
            total = (f.get("evidence") or {}).get("count")
            out.append(_complaint("locale_magnet", f, f"{len(hit)} of {total if total is not None else '?'} magnet rows are locale files, e.g. {hit[0]}"))
    return out


FINDING_CHECKS = (gone_people, wrong_area, growth_window, secrets_headline, sarif_gate, trailer_author, agent_owner,
                  start_area, sarif_rows, doc_lock, tool_person,
                  tool_owner, merge_rows, suspect_lead, silent_precondition, trailer_case,
                  tied_owner, overrun_span, silent_measure, coverage_unsaid, plural_one,
                  noreply_split, split_density, locale_magnet)
CLONE_CHECKS = (tree_claim, sweeping_evidence, magnet_gone, hygiene_misread, lock_workspace, unreferenced_named, self_credit, declared_critical,
                generated_owner, agent_pointer, structure_skipped, dependency_floor,
                merge_total, test_double_lead, test_path_secret, peer_unused, declared_reference, lock_without_require, dev_only_vuln_lead,
                lock_declares_nothing, contributing_heading, unscored_executable, dead_import, fix_episode,
                pnpm_specifiers, private_vulns, trojan_tokens, action_order)


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

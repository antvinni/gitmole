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

- agent_owner: the knowledge map names a tool (an identity that only appears in trailers, or one of
  several names on one shared no-reply address) as an area's owner or second.
- magnet_gone: a bug magnet the tree no longer holds (132 of VoiceStudio's 296 were a retired frontend/).
- hygiene_misread: an extra index named only on comment lines, install code in a setup.py with no setup().
- lock_workspace: lock drift on a workspace member whose declared root keeps the lock.
- unreferenced_named: a "possibly unreferenced" file a non-prose file of the tree names (a build spec, a
  bundler input, a deploy config).
- self_credit: a People row's co-authored count that includes the author's own aliases on their own commits.
- declared_critical: a critical secret the repository declared allowed at some commit (a gitleaks or
  betterleaks config or ignore file, or `gitleaks:allow` on its line).

tree_claim, sweeping_evidence and the second set but agent_owner need the clone, read at the commit the
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

NO_REPLY = re.compile(r"^(?:no-?reply|donotreply|do-not-reply)@", re.I)   # a bare no-reply mailbox; a per-user `id+login@users.noreply…` is not one


def agents(report: dict) -> set:
    """The identities that are a tool rather than a person, by shape: one that authored no commit and
    only ever appears in Co-authored-by trailers, or one whose address is a bare no-reply mailbox that
    several differently named identities share (one per model version of the same assistant)."""
    ids = (report.get("meta") or {}).get("identities") or []
    shared = {}
    for i in ids:
        for email in {i.get("email") or ""} | {a.get("email") or "" for a in i.get("aliases") or []}:
            if NO_REPLY.match(email):
                shared.setdefault(email.lower(), set()).add(i.get("name"))
    out = set()
    for i in ids:
        emails = {(i.get("email") or "").lower()} | {(a.get("email") or "").lower() for a in i.get("aliases") or []}
        if (i.get("authored") == 0 and (i.get("commits") or 0) > 0) or any(len(shared.get(e, ())) >= 2 for e in emails):
            out.add(i.get("name"))
    return out


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
            name = re.sub(r"(?: \(gone\))? \(\d+%\)$", "", cell)
            if name in tools:
                out.append(_complaint("agent_owner", None, f"{area}: {name}"))
    return out


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


FINDING_CHECKS = (gone_people, wrong_area, growth_window, secrets_headline, sarif_gate, trailer_author, agent_owner)
CLONE_CHECKS = (tree_claim, sweeping_evidence, magnet_gone, hygiene_misread, lock_workspace, unreferenced_named, self_credit, declared_critical)


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

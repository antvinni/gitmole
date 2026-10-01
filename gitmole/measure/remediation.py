"""Was the finding acted on? Remediation rates from the repository's own later history.

The `actionable` axis of a hand label asks a person to guess what a maintainer would do. Git records
what maintainers did. For a finding made at cut-off T, this module looks at the tree at T + horizon
and asks whether the specific thing the advice named was fixed: the action ref became a commit hash,
the lockfile was regenerated, the binary left the tree or became an LFS pointer, the bidi codepoint
is gone, the dependency left the manifest.

Nobody acting is not proof a finding was wrong — they may never have run gitmole — so what this
measures is "the repository acted on this within the window", never precision and never worth. It is
a lower bound, and a biased one: a project pins an action or deletes a binary far more readily than
it splits a class, so the mechanical rules score high and the structural ones low for reasons that
have nothing to do with which advice was better. MECHANICAL marks that split and the table reports
the two bands apart, so the bias is on the page rather than in a caveat.

The window is fixed, as the watch list's backtest fixes its horizon: a finding raised too close to
the last commit has not had time to be acted on, and counting it would quietly depress every share.
A run whose cut-off plus horizon reaches past the history is refused rather than reported.

A rule can only be scored when its evidence names its subjects. Several name only totals
(`stale_files` gives a count, not the files), and those are listed in NO_SUBJECTS rather than
silently scoring zero: extending their evidence is what makes them measurable.

A rule whose evidence does name its subjects but has no predicate yet is in NO_PREDICATE, and every id
findings.py emits is in RULES or one of the three lists (a test holds this), so no rule that fired can
leave the report without a line.

NOT_OBSERVABLE is a statement about the advice's wording, not about the finding's value. Pairing
someone on a knowledge island leaves no trace in a tree, which makes the advice unmeasurable here and
says nothing about whether taking it was worth it. Where this list and the hand labels agree, two
methods agreed; that is worth recording and is not the same as either being right.

    python -m gitmole.measure.remediation REPORT.json [MORE.json ...] --repo DIR [--horizon 6]

REPORT.json is a `--json` export made at the cut-off; the horizon picks the commit at the far end
through harness.rev_at, main's first-parent commit, the way the rest of the harness picks one.

A release round (`python -m gitmole.measure run --release`, or `run --remediation`) asks the same question
at each of the ranking's cut-offs on the development repositories (harness.remediate_repo), a release
round only when a path in ASKED_WHEN_CHANGED changed since the last record that asked it:
the release's own export of the tree at the cut-off, scored here by over_window. The record keeps the
outcome counts by rule; pooled() and bands() are the table's arithmetic over them.

A subject the tree did not hold at the cut-off is counted ABSENT and left out of every share. Without
that gate curl's specimen values read as 90% remediated, because the secrets rules name paths from the
whole history and most of those files had been deleted years before the cut-off. The secrets rules are
in NOT_OBSERVABLE for the same reason: the value stays in history whatever the tree does.

A subject whose path left the tree is followed through git's rename detection between the two trees
(pinned limit and similarity, so a user's config cannot change the answer) and its predicate asked
again at the new path; anything but RESOLVED there is MOVED, which is never counted as fixed. Before
this, `git mv` of an unreferenced file or a trojan-source file read as the advice taken. A function gone
by name whose declaration and body survive under another name is MOVED too, not RESOLVED.

Given several exports of one repository, made at several cut-offs, each subject is counted once, at the
first cut-off that flagged it, so a file left open through six cut-offs is one open subject, not six.
A subject renamed between two cut-offs is still two identities; the window's own MOVED catches only a
move inside one window.

The predicates have fixtures in tests/test_remediation.py; the git reads were first exercised on curl
over 2025-09-16 to 2026-03-16, which is where the ABSENT gate and the table's denominators came from.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from collections import Counter

GIT = ["git", "-c", "core.quotePath=false"]

RESOLVED = "resolved"   # the named thing was fixed
OPEN = "open"           # it is still there
GONE = "gone"           # the file it lived in left the tree
UNKNOWN = "unknown"     # the tree cannot answer; needs a second run's metrics
ABSENT = "absent"       # not in the tree at the cut-off, so the window says nothing about it
MOVED = "moved"         # still there under another path or name: never counted as fixed

# git's documented default for diff.renameLimit, pinned on the command line so that a user's git config
# cannot change which moves are found, and so the bytes of a run (C6). Exact renames are found whatever
# the limit; past it git skips the inexact ones and says so, and the run prints that it did.
RENAME_LIMIT = 1000
# git's own default similarity for -M: a path that kept half its content under a new name was moved.
RENAME_SIMILARITY = 50

# The subject keys that hold a path, followed through a rename together.
PATH_KEYS = ("file", "manifest", "lockfile", "source")


HORIZON = 6   # months from the cut-off, the horizon the watch list's backtest uses


def months_after(date: str, months: int) -> str:
    """The ISO date `months` whole months after `date`, the day clamped to the month's length."""
    import calendar
    import datetime as dt
    d = dt.date.fromisoformat(date)
    years, month = divmod(d.month - 1 + months, 12)
    year = d.year + years
    return dt.date(year, month + 1, min(d.day, calendar.monthrange(year, month + 1)[1])).isoformat()


def window(repo: str, cutoff: str, horizon: int) -> tuple:
    """(end date, the commit at it) for a window that fits inside the history, and (end, None) when
    it runs past the last commit. A finding the history has not had `horizon` months to answer is
    not evidence that nobody acted, so that run is refused rather than counted."""
    from .harness import rev_at
    end = months_after(cutoff, horizon)
    last = subprocess.run([*GIT, "log", "-1", "--format=%cs"], cwd=repo,
                          capture_output=True, text=True).stdout.strip()
    if not last or end > last:
        return end, None
    return end, rev_at(repo, end)


def renames(repo: str, before_rev: str, rev: str) -> tuple:
    """({old path: new path}, skipped) between the cut-off tree and the far end of the window, by git's
    own rename detection over the two trees: one process, whatever the number of subjects. A file moved
    twice in the window is found end to end, provided it kept the similarity. `skipped` is True when the
    pinned limit made git leave inexact renames out, which the table then says."""
    proc = subprocess.run([*GIT, "-c", f"diff.renameLimit={RENAME_LIMIT}", "diff", "--no-ext-diff", "--no-textconv", "--no-relative",
                           "--name-status", "-z", f"--find-renames={RENAME_SIMILARITY}%", before_rev, rev, "--"],
                          cwd=repo, capture_output=True)
    if proc.returncode:
        return {}, False
    fields = [f.decode("utf-8", "surrogateescape") for f in proc.stdout.split(b"\0")]
    moves, i = {}, 0
    while i < len(fields) and fields[i]:
        status = fields[i]
        if status[:1] in ("R", "C"):
            if status[:1] == "R":
                moves[fields[i + 1]] = fields[i + 2]
            i += 3
        else:
            i += 2
    return moves, b"renameLimit" in proc.stderr


class After:
    """The tree at the far end of the window, and when each path was last touched.

    One `ls-tree` and one `cat-file --batch` serve every predicate, so a rule with two hundred
    subjects costs two processes rather than two hundred.

    `at_cutoff` holds the paths the tree had when the finding was made, because several rules name
    subjects the cut-off tree does not contain: the secrets rules read every commit HEAD reaches,
    so they name paths deleted years earlier. Counting those as "the file left the tree" turned
    curl's specimen values into a 90% remediation rate for acts nobody performed in the window."""

    def __init__(self, repo: str, rev: str, cutoff: str = "", before_rev: str = ""):
        self.repo, self.rev, self.cutoff, self.before_rev = repo, rev, cutoff, before_rev
        self.at_cutoff = None
        self.moves, self.renames_skipped = {}, False
        if before_rev:
            out = subprocess.run([*GIT, "ls-tree", "-r", "-z", "--name-only", before_rev], cwd=repo,
                                 capture_output=True, check=True).stdout
            self.at_cutoff = {p.decode("utf-8", "surrogateescape") for p in out.split(b"\0") if p}
            self.moves, self.renames_skipped = renames(repo, before_rev, rev)
        self._entries = {}
        out = subprocess.run([*GIT, "ls-tree", "-r", "-z", rev], cwd=repo, capture_output=True, check=True).stdout
        for row in out.split(b"\0"):
            if not row:
                continue
            meta, _, path = row.partition(b"\t")
            mode, _, rest = meta.decode().partition(" ")
            _, _, sha = rest.partition(" ")
            self._entries[path.decode("utf-8", "surrogateescape")] = (mode, sha.strip())
        self._text = {}
        self._day = {}

    def exists(self, path: str) -> bool:
        return path in self._entries

    def mode(self, path: str):
        entry = self._entries.get(path)
        return entry[0] if entry else None

    def is_symlink(self, path: str) -> bool:
        return self.mode(path) == "120000"

    def text(self, path: str):
        """The file's contents at `rev`, or None when it is not in the tree or is not text."""
        if path in self._text:
            return self._text[path]
        entry = self._entries.get(path)
        if not entry:
            self._text[path] = None
            return None
        blob = subprocess.run([*GIT, "cat-file", "blob", entry[1]], cwd=self.repo, capture_output=True)
        value = None if blob.returncode else blob.stdout.decode("utf-8", "replace")
        if value is not None and "\0" in value[:8000]:
            value = None                      # binary: no predicate reads one
        self._text[path] = value
        return value

    def before_text(self, path: str):
        """The file's text in the cut-off tree, or None: what a renamed function is matched against."""
        if not self.before_rev:
            return None
        blob = subprocess.run([*GIT, "cat-file", "blob", f"{self.before_rev}:{path}"], cwd=self.repo, capture_output=True)
        if blob.returncode or b"\0" in blob.stdout[:8000]:
            return None
        return blob.stdout.decode("utf-8", "replace")

    def last_commit_day(self, path: str):
        """YYYY-MM-DD of the last commit to touch `path` at or before `rev`, or None."""
        if path in self._day:
            return self._day[path]
        out = subprocess.run([*GIT, "log", "-1", "--format=%cs", self.rev, "--", path],
                             cwd=self.repo, capture_output=True, text=True).stdout.strip()
        self._day[path] = out or None
        return self._day[path]


# --- subjects: evidence -> one row per thing the advice named ------------------------------------

def _paths(evidence, key="files"):
    """A `files` list that holds either paths or dicts with a `file` key."""
    out = []
    for item in evidence.get(key) or []:
        out.append({"file": item} if isinstance(item, str) else dict(item))
    return out


def _under(evidence, *keys):
    rows = []
    for key in keys:
        for item in evidence.get(key) or []:
            row = dict(item) if isinstance(item, dict) else {"file": item}
            row["_kind"] = key
            rows.append(row)
    return rows


# --- predicates ----------------------------------------------------------------------------------

_HEX = re.compile(r"^[0-9a-f]{40}([0-9a-f]{24})?$")


def _unpinned_action(s, after):
    text = after.text(s["file"])
    if text is None:
        return GONE
    name = (s.get("uses") or "").partition("@")[0]
    if not name:
        return UNKNOWN
    refs = re.findall(rf"uses:\s*{re.escape(name)}@(\S+)", text)
    if not refs:
        return RESOLVED                       # the step no longer uses that action
    return RESOLVED if all(_HEX.match(r.strip("\"'")) for r in refs) else OPEN


def _lockfile_drift(s, after):
    manifest, lock = after.last_commit_day(s["manifest"]), after.last_commit_day(s["lockfile"])
    if manifest is None or lock is None:
        return GONE
    return RESOLVED if lock >= manifest else OPEN


def _lockfile_missing(s, after):
    if not after.exists(s["manifest"]):
        return GONE
    where = os.path.dirname(s["manifest"])
    return RESOLVED if any(after.exists(os.path.join(where, name)) for name in s.get("expected") or []) else OPEN


_LFS_POINTER = "version https://git-lfs.github.com/spec/v1"


def _committed_binary(s, after):
    entry = after.exists(s["file"])
    if not entry:
        return GONE
    text = after.text(s["file"])
    return RESOLVED if text and text.startswith(_LFS_POINTER) else OPEN


def _untracked(s, after):
    """The fix is that the file stopped being tracked: credentials, agent-local settings, dead files."""
    return RESOLVED if not after.exists(s["file"]) else OPEN


def _bidi_char(s, after):
    text = after.text(s["file"])
    if text is None:
        return GONE
    try:
        char = chr(int(str(s["char"]).removeprefix("U+"), 16))
    except (KeyError, ValueError):
        return UNKNOWN
    return OPEN if char in text else RESOLVED   # line numbers drift; the codepoint does not


def _mixed_script(s, after):
    text = after.text(s["file"])
    if text is None:
        return GONE
    token = s.get("token")
    return OPEN if token and token in text else RESOLVED


def _hardcoded_address(s, after):
    text = after.text(s["file"])
    if text is None:
        return GONE
    value = s.get("value")
    return OPEN if value and value in text else RESOLVED


def _unused_dependency(s, after):
    text = after.text(s["manifest"])
    if text is None:
        return GONE
    name = s.get("package") or ""
    if not name:
        return UNKNOWN
    return OPEN if re.search(rf'(^|["\s]){re.escape(name)}(["\s=:,]|$)', text, re.M) else RESOLVED


def _vulnerable_package(s, after):
    text = after.text(s.get("source") or "")
    if text is None:
        return GONE
    version = s.get("version")
    return OPEN if version and version in text else RESOLVED


def _mcp_literal(s, after):
    text = after.text(s["file"])
    if text is None:
        return GONE
    match = re.search(rf'"{re.escape(s.get("key") or "")}"\s*:\s*"([^"]*)"', text)
    if not match:
        return RESOLVED
    return RESOLVED if match.group(1).startswith("${") else OPEN


def _submodule(s, after):
    text = after.text(".gitmodules")
    if text is None:
        return GONE
    needle = s.get("branch") if s.get("_kind") == "floating" else s.get("url")
    if not needle or "***" in needle:
        return UNKNOWN                        # the credential URL was redacted before it was stored
    return OPEN if needle in text else RESOLVED


def _symlink(s, after):
    path = s["file"]
    if not after.exists(path):
        return GONE
    return OPEN if after.is_symlink(path) else RESOLVED


_MARKER = re.compile(r"\b(TODO|FIXME|XXX|HACK)\b")


def _debt_marker(s, after):
    text = after.text(s["file"])
    if text is None:
        return GONE
    was = s.get("markers")
    if not was:
        return UNKNOWN
    return RESOLVED if len(_MARKER.findall(text)) < was else OPEN


_IDENT = r"[A-Za-z_$][\w$]*"


def _indent(line: str) -> int:
    return len(line) - len(line.lstrip())


def _body(lines: list, at: int) -> list:
    """The non-blank lines after the declaration at `at`, up to the first one indented no deeper than it:
    a closing brace, or the next statement at the declaration's level. An opening brace on a line of its
    own at that level (C's usual layout) opens the body rather than ending it. Stripped, so a re-indent
    is not an edit."""
    out, depth = [], _indent(lines[at])
    for line in lines[at + 1:]:
        if not line.strip():
            continue
        out.append(line.strip())
        if _indent(line) <= depth and line.strip() != "{":
            break
    return out


def _similar(a: list, b: list) -> bool:
    """git's rename rule on lines: at least RENAME_SIMILARITY percent of the larger body is shared. Lines
    of punctuation alone (a brace) say nothing about which function this is and are not counted."""
    a, b = [x for x in a if re.search(r"\w", x)], [x for x in b if re.search(r"\w", x)]
    if not a and not b:
        return True
    shared = sum((Counter(a) & Counter(b)).values())
    return shared * 100 >= RENAME_SIMILARITY * max(len(a), len(b))


def _renamed(s, name: str, text: str, after) -> bool:
    """Whether the function the finding named is still in `text` under another name: its declaration
    line at the cut-off, with the name taken for any other identifier, starts a line there, and the body
    that follows is similar by git's own rename threshold. Without the cut-off's text or a declaration
    line that holds the name, nothing can be matched, and the old reading stands."""
    read = getattr(after, "before_text", None)
    start = s.get("start")
    if not read or not isinstance(start, int) or start < 1:
        return False
    before = read(s.get("_from") or s["file"])
    if before is None:
        return False
    old = before.split("\n")
    word = rf"(?<![\w$]){re.escape(name)}(?![\w$])"
    parts = re.split(word, old[start - 1].strip(), maxsplit=1) if start <= len(old) else []
    if len(parts) != 2:
        return False
    head, tail = parts
    shape = re.compile(rf"{re.escape(head)}(?!{re.escape(name)}(?![\w$])){_IDENT}{re.escape(tail)}")
    was = _body(old, start - 1)
    new = text.split("\n")
    return any(shape.fullmatch(line.strip()) and _similar(was, _body(new, i)) for i, line in enumerate(new))


def _named_function(s, after):
    """A weak proxy: the function is gone by name. Whether a surviving one got simpler needs a second
    run's function metrics, so that case is UNKNOWN rather than OPEN. A function that is gone by name
    but whose declaration and body are still there under another name was renamed, not split, and is
    MOVED, never RESOLVED."""
    text = after.text(s["file"])
    if text is None:
        return GONE
    name = s.get("function") or s.get("name") or ""
    if not name or name == "(anonymous)":
        return UNKNOWN
    if name in text:
        return UNKNOWN
    return MOVED if _renamed(s, name, text, after) else RESOLVED


def _instructions_drift(s, after):
    day = after.last_commit_day(s["file"])
    if day is None:
        return GONE
    return RESOLVED if after.cutoff and day > after.cutoff else OPEN


# --- the table -----------------------------------------------------------------------------------

# rule -> (subjects, predicate, gone_is_fix). gone_is_fix says whether the file leaving the tree
# counts as the advice being taken: deleting the committed binary is the fix, while a brain method
# whose whole file was deleted in a reorganisation is not evidence either way.
RULES = {
    "unpinned_actions":      (lambda e: _paths(e, "unpinned"), _unpinned_action, False),
    "lockfile_drift":        (lambda e: _paths(e, "drift"), _lockfile_drift, False),
    "lockfile_missing":      (lambda e: _paths(e, "missing"), _lockfile_missing, False),
    "committed_binaries":    (lambda e: _under(e, "executables", "lfs_unpointed"), _committed_binary, True),
    "credential_files":      (lambda e: _paths(e), _untracked, True),
    "agent_local_settings":  (lambda e: _paths(e), _untracked, True),
    "unreferenced_files":    (lambda e: _paths(e), _untracked, True),
    "trojan_source":         (lambda e: _under(e, "bidi"), _bidi_char, True),
    "trojan_source_mixed":   (lambda e: _under(e, "mixed_script"), _mixed_script, True),
    "hardcoded_addresses":   (lambda e: _paths(e), _hardcoded_address, True),
    "unused_dependencies":   (lambda e: _paths(e, "unused"), _unused_dependency, True),
    "vulnerable_dependencies": (lambda e: _paths(e, "packages"), _vulnerable_package, True),
    "mcp_literal_env":       (lambda e: _paths(e, "entries"), _mcp_literal, True),
    "submodule_urls":        (lambda e: _under(e, "credentials", "insecure", "relative", "floating"), _submodule, True),
    "unsafe_symlinks":       (lambda e: _under(e, "outside", "into_git"), _symlink, True),
    "debt_in_hotspots":      (lambda e: _paths(e), _debt_marker, True),
    "brain_methods":         (lambda e: _paths(e, "functions"), _named_function, False),
    "deep_nesting":          (lambda e: _paths(e, "functions"), _named_function, False),
    "swallowed_errors":      (lambda e: _paths(e), _named_function, False),
    "agent_instructions_drift": (lambda e: _paths(e), _instructions_drift, False),
}

# Rules the predicates can judge cheaply, because the act they name is mechanical: a ref, a path, a
# codepoint. A project does these far more readily than it splits a class, so their share runs high
# for reasons unrelated to which advice was better, and the table reports the two bands apart.
MECHANICAL = {"unpinned_actions", "lockfile_drift", "lockfile_missing", "committed_binaries",
              "credential_files", "agent_local_settings",
              "trojan_source", "trojan_source_mixed", "hardcoded_addresses", "mcp_literal_env",
              "submodule_urls", "unsafe_symlinks", "vulnerable_dependencies", "unused_dependencies",
              "agent_instructions_drift"}

# Rules whose advice names no act that a later tree can show. This is a property of the advice, not a
# verdict on the finding: it says the claim cannot be tested here, not that it is not worth taking.
# A demotion decision may cite it, but must cite it as that and keep it apart from the label evidence.
NOT_OBSERVABLE = {
    "secrets_in_source": "betterleaks reads every commit HEAD reaches, so the value stays in history "
                         "whatever the tree does, and the advice is to rotate it, which no tree shows",
    "secrets_aside": "as secrets_in_source: the value stays in history, and the paths named may have left "
                     "the tree years before the cut-off",
    "repo_health": "git-sizer's own measurement; a level of concern is not a task",
    "knowledge_loss": "pairing leaves no trace in the tree",
    "knowledge_islands": "pairing leaves no trace in the tree",
    "truck_factor": "pairing leaves no trace in the tree",
    "bus_factor": "pairing leaves no trace in the tree",
    "minor_contributors": "who reviews what leaves no trace in the tree",
    "authors_gone": "who holds the knowledge leaves no trace in the tree",
    "component_coupling": "describes a layout, names no act",
    "hidden_coupling": "describes a layout, names no act",
    "import_cycles": "the act is observable, but only in a later tree's import graph, which no predicate here parses",
    "tight_coupling": "describes a layout, names no act",
    "dormant": "a property of the repository, not a defect",
    "placeholder_identity": "a .mailmap entry is observable, but the finding names no one path to check",
    "signoff_by_co_author": "history cannot be un-signed",
    "sweeping_commits": "history cannot be un-committed",
    "import_commits": "history cannot be un-committed",
    "tangled_commits": "history cannot be un-committed",
    "secrets_possible": "the advice is to look at each value; what would show it was done, a fingerprint in "
                        ".betterleaksignore, is not in the evidence, which names files only",
    "reverts": "the advice is a check before merge, and a later tree does not show one as such",
    "secrets_declared": "the advice is to confirm a declaration the repository already made, which no tree shows",
    "secrets_local": "the advice is to check that no deployed service shares a development default, which no tree shows",
}

# Rules that name their subjects only as totals. Extending the evidence to list them is what makes
# them measurable; until then they are neither scored nor written off.
NO_SUBJECTS = {
    "stale_files": "evidence gives counts, not the stale paths",
    "duplication": "blocks carry places, but matching a block's text across a window needs the second run",
    "complexity_growth": "needs the second run's per-file complexity, not the tree",
    "bug_magnets": "the outcome is more fixes, which the watch-list backtest already measures",
}

# Rules whose evidence names subjects a later tree could show acted on, but for which no predicate has
# been written. They are measurable in principle; until a predicate exists they are listed, not scored,
# so a reader sees they fired rather than finding them silently missing from the table.
NO_PREDICATE = {
    "commented_out_code": "names each file and the block's first line; a predicate would look for the block in the later tree",
    "agent_approval_disabled": "names each settings file and setting; a predicate would read that file in the later tree",
    "dependency_confusion": "names each package, lock file and registry; a predicate would re-read the lock file",
    "install_scripts": "names the packages and manifests; a predicate would re-read the lock file and manifests",
    "copyleft_dependencies": "names the dependencies; a predicate would re-read the lock file's licence fields",
    "repo_policy": "names what is missing at the root; a predicate would look for the file in the later tree",
    "dependency_updates": "names the ecosystems left uncovered; a predicate would re-read dependabot.yml or renovate.json",
    "project_licence": "names the licence file and the manifests; a predicate would compare them in the later tree",
    "pwn_request": "names each workflow, job and line; a predicate would re-read the checkout step in the later tree",
    "expression_injection": "names each workflow, line and field; a predicate would look for the expression in the later tree",
}

# The lists printed under the table, in this order, each under its heading.
UNSCORED = (
    ("Fired, and names no act a later tree can show. Not a verdict on their worth:", NOT_OBSERVABLE),
    ("Fired, but its evidence does not name its subjects:", NO_SUBJECTS),
    ("Fired, and names its subjects, but no predicate reads them yet:", NO_PREDICATE),
)


def unscored(fired: set) -> str:
    """The rules that fired but are not in the table, each under the reason it is not."""
    out = []
    for heading, reasons in UNSCORED:
        names = sorted(fired & set(reasons))
        if names:
            out.append(f"\n{heading}\n\n" + "".join(f"- **{n}** — {reasons[n]}\n" for n in names))
    return "".join(out)



# --- when a release round asks remediation's question ----------------------------------------------

# Every path a release's remediation rows depend on, from the repository's root, in one place. A
# --release round asks the question only when one of these changed since the last record that asked
# it (asked_since); otherwise its entries carry {"asked": False, "reason": ...} and the summary shows
# a gap, never a value copied forward. The list errs toward running: a module is here when the scan
# that makes the cut-off exports reaches it, unless it plainly cannot touch a finding (the banner, the
# installer, the SARIF writer...; tests/test_remediation_trigger.py names each one left out and holds
# every module under gitmole/ to one side or the other).
ASKED_WHEN_CHANGED = {
    "the scored rules' predicates": ("gitmole/measure/remediation.py",),
    "the file classifier": ("gitmole/classify.py", "gitmole/filetypes.py"),
    "the code behind the scored findings": (
        "gitmole/findings.py", "gitmole/load.py", "gitmole/render.py", "gitmole/cli.py", "gitmole/__main__.py",
        "gitmole/run.py", "gitmole/launch.py", "gitmole/stepstat.py", "gitmole/tools.py", "gitmole/userdirs.py",
        "gitmole/scope.py", "gitmole/identity.py", "gitmole/textfmt.py",
        "gitmole/maat.py", "gitmole/blame.py", "gitmole/functions.py", "gitmole/structure.py", "gitmole/imports.py",
        "gitmole/hygiene.py", "gitmole/locks.py", "gitmole/deps.py", "gitmole/licences.py", "gitmole/leaks.py",
        "gitmole/provenance.py", "gitmole/signing.py", "gitmole/trend.py", "gitmole/backtest.py", "gitmole/watch.py",
        "gitmole/hotspots.py", "gitmole/coupling.py", "gitmole/knowledge.py", "gitmole/loss.py", "gitmole/osps.py",
        "gitmole/gate.py",
        "pyproject.toml",   # the grammars' versions: what structure parses
    ),
    "the scans at the cut-offs and their pooling": ("gitmole/measure/harness.py", "gitmole/measure/corpus.py", "gitmole/measure/wrap.py",
                                                    "gitmole/measure/dashboard.py", "measure/corpus.json"),
}


def watched_paths() -> list:
    return sorted({p for paths in ASKED_WHEN_CHANGED.values() for p in paths})


def changed_since(root: str, since: str, commit: str = None) -> list:
    """The watched paths that differ between `since` and `commit` in the gitmole checkout at `root`; with
    no `commit`, between `since` and the working tree, uncommitted edits included (a `run` of the worktree).
    Raises CalledProcessError when git cannot tell (an unknown commit): the caller then runs."""
    argv = [*GIT, "diff", "--name-only", "--no-renames", since, *([commit] if commit else []), "--", *watched_paths()]
    out = subprocess.run(argv, cwd=root, check=True, capture_output=True, text=True).stdout
    return sorted(line for line in out.splitlines() if line)


def asked_since(root: str, previous: dict, commit: str = None) -> tuple:
    """(asked, reason, changed) for a release round: asked when no earlier record asked the question, when
    git cannot compare against that record's commit, or when a watched path changed since it. `previous`
    is the latest earlier record whose summary carries remediation's table. Errs toward asking."""
    if not previous or not previous.get("commit"):
        return True, "no earlier record asked it", []
    since, version = previous["commit"], previous.get("version", "?")
    try:
        changed = changed_since(root, since, commit)
    except (subprocess.CalledProcessError, OSError):
        return True, f"cannot compare with {version}'s commit {since[:12]}", []
    if changed:
        return True, f"{len(changed)} watched path{'s' if len(changed) != 1 else ''} changed since {version}", changed
    return False, f"the paths it depends on are unchanged since {version} ({since[:12]})", []


def _present_at_cutoff(subject, after: After) -> bool:
    """Whether the path a subject names was in the tree when the finding was made. A subject with no
    path (a dependency, an action ref) is always judged; only paths can be already-deleted."""
    path = subject.get("file") if isinstance(subject, dict) else subject
    if not isinstance(path, str) or "/" not in path and "." not in path:
        return True
    return path in after.at_cutoff


def _moved(subject, after):
    """The subject with its paths followed through the window's renames, or None when none of them
    moved. Only a path the later tree lacks is followed: one that is still there was not moved away."""
    moves = getattr(after, "moves", None)
    if not moves or not isinstance(subject, dict):
        return None
    out = dict(subject)
    for key in PATH_KEYS:
        path = subject.get(key)
        if isinstance(path, str) and not after.exists(path) and path in moves:
            out[key] = moves[path]
            if key == "file":
                out["_from"] = path
    return out if out != subject else None


def outcome(subject, predicate, after) -> str:
    """The predicate's answer, with a moved subject judged where it went. A file renamed or moved used
    to read as deleted, so an unreferenced file or a trojan-source file was counted fixed by a `git mv`;
    now the predicate is asked again of the new path, and anything but RESOLVED there is MOVED."""
    moved = _moved(subject, after)
    if moved is None:
        return predicate(subject, after)
    answer = predicate(moved, after)
    return RESOLVED if answer == RESOLVED else MOVED


# Subject keys that say which thing a finding named, rather than how it measured that day: a line
# number, a complexity or a count drifts between cut-offs while the subject stays the same.
IDENTITY_KEYS = ("_kind", *PATH_KEYS, "uses", "char", "token", "value", "package", "version", "key",
                 "url", "branch", "function", "name")


def identity(rule: str, subject) -> tuple:
    if not isinstance(subject, dict):
        return (rule, str(subject))
    return (rule, *((k, str(subject[k])) for k in IDENTITY_KEYS if subject.get(k) is not None))


def score(findings: list, after: After, seen: set = None) -> dict:
    """rule -> Counter of outcomes over every subject its findings named. With `seen`, a subject already
    counted at an earlier cut-off is left out (and counted under REPEAT), and the ones counted here are
    added to it: across several cut-offs a subject is counted once, where it was first flagged, so an
    open file flagged six times is not six open subjects."""
    out = {}
    for finding in findings:
        rule = (finding.get("rule") or {}).get("id")
        evidence = finding.get("evidence") or {}
        for name, (subjects, predicate, _) in RULES.items():
            if name.split("_mixed")[0] != rule and name != rule:
                continue
            counts = out.setdefault(name, Counter())
            for subject in subjects(evidence):
                if seen is not None:
                    key = identity(name, subject)
                    if key in seen:
                        counts[REPEAT] += 1
                        continue
                    seen.add(key)
                at_cutoff = getattr(after, "at_cutoff", None)   # a stub tree need not carry one
                if at_cutoff is not None and not _present_at_cutoff(subject, after):
                    counts[ABSENT] += 1       # the window cannot speak for a file that was already gone
                    continue
                try:
                    counts[outcome(subject, predicate, after)] += 1
                except (KeyError, TypeError, subprocess.SubprocessError):
                    counts[UNKNOWN] += 1
    return out


REPEAT = "repeat"   # flagged again at a later cut-off; counted once, at the first


MIN_JUDGED = 5   # below this a share is printed as the fraction it is: 1 of 1 is not 100%


def moved_is_judged(name: str) -> bool:
    """Whether a MOVED subject is in the denominator as not fixed. It is, except for the function rules,
    whose predicate calls every surviving function can't-say (it may have got simpler): a renamed one is
    a survivor too, so it stays out of the share as they do."""
    return RULES[name][1] is not _named_function


def judged(counts: Counter, gone_is_fix: bool, moved: bool = True) -> int:
    """How many subjects the window could speak for: the denominator behind the share. A MOVED subject
    is judged and never fixed (see moved_is_judged for the exception)."""
    return counts[RESOLVED] + counts[OPEN] + (counts[MOVED] if moved else 0) + (counts[GONE] if gone_is_fix else 0)


OUTCOMES = (RESOLVED, OPEN, MOVED, GONE, UNKNOWN, ABSENT, REPEAT)


def counts(scored: dict) -> dict:
    """score()'s Counters as plain dicts for a record: every outcome present, zero or not, so two records diff."""
    return {name: {k: c[k] for k in OUTCOMES} for name, c in sorted(scored.items())}


def pooled(rows) -> dict:
    """rule -> its outcome counts summed over `rows` (each a counts() dict), the rule's gone_is_fix, how many
    subjects the window could speak for, how many of those were acted on, and the share: the table's own
    arithmetic, kept as numbers. Subjects are summed, never shares averaged, as the table pools a band. The
    share is None when nothing was judged; a reader applies MIN_JUDGED, the record keeps the fraction."""
    totals = {}
    for row in rows:
        for name, c in (row or {}).items():
            if name not in RULES:
                continue
            t = totals.setdefault(name, Counter())
            t.update({k: c.get(k, 0) for k in OUTCOMES})
    out = {}
    for name, c in sorted(totals.items()):
        gone_is_fix = RULES[name][2]
        n = judged(c, gone_is_fix, moved_is_judged(name))
        fixed = c[RESOLVED] + (c[GONE] if gone_is_fix else 0)
        out[name] = {**{k: c[k] for k in OUTCOMES}, "gone_is_fix": gone_is_fix,
                     "kind": "mechanical" if name in MECHANICAL else "structural",
                     "judged": n, "acted_on": fixed, "share": round(fixed / n, 4) if n else None}
    return out


def bands(rules: dict) -> dict:
    """pooled() rows summed into the mechanical and structural bands, subjects pooled as table() pools them."""
    out = {}
    for kind in ("mechanical", "structural"):
        rows = [v for v in rules.values() if v["kind"] == kind]
        if rows:
            n, fixed = sum(v["judged"] for v in rows), sum(v["acted_on"] for v in rows)
            out[kind] = {"judged": n, "acted_on": fixed, "share": round(fixed / n, 4) if n else None}
    return out


def table(scored: dict) -> str:
    """One row per rule, mechanical first. Every subject is accounted for in a column, since the
    denominator is the part a reader has to see: a share over two judged subjects and a share over
    two hundred are not the same claim. Each band pools its subjects rather than averaging its rules,
    so one rule with a single subject cannot move the band, and the two bands stay apart because a
    project pins an action far more readily than it splits a class."""
    rows = ["| rule | kind | subjects | acted on | still open | moved | left the tree | can't say | gone before | share |",
            "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|"]
    bands = {"mechanical": Counter(), "structural": Counter()}
    for name, counts in sorted(scored.items(), key=lambda kv: (kv[0] not in MECHANICAL, kv[0])):
        kind = "mechanical" if name in MECHANICAL else "structural"
        gone_is_fix = RULES[name][2]
        n = judged(counts, gone_is_fix, moved_is_judged(name))
        fixed = counts[RESOLVED] + (counts[GONE] if gone_is_fix else 0)
        bands[kind].update({"fixed": fixed, "judged": n})
        if not n:
            shown = "-"
        elif n < MIN_JUDGED:
            shown = f"{fixed} of {n}"
        else:
            shown = format(fixed / n, ".0%")
        rows.append(f"| {name} | {kind} | {sum(counts.values()) - counts[REPEAT]} | {counts[RESOLVED]} | "
                    f"{counts[OPEN]} | {counts[MOVED]} | {counts[GONE]} | {counts[UNKNOWN]} | {counts[ABSENT]} | {shown} |")
    for kind, totals in bands.items():
        if totals["judged"]:
            line = f"\n{kind}: {totals['fixed']} of {totals['judged']} subjects acted on"
            if totals["judged"] >= MIN_JUDGED:
                line += f", {format(totals['fixed'] / totals['judged'], '.0%')}"
            rows.append(line + ".")
        elif totals:
            rows.append(f"\n{kind}: no subject the window could speak for.")
    return "\n".join(rows)


def over_window(findings: list, repo: str, cutoff: str, horizon: int = HORIZON, seen: set = None) -> dict:
    """What main() prints, as a record: the window's end, the outcome counts by rule, and the rules that
    fired but are not scored. A window past the history is an `error`, as main() refuses it. With `seen`,
    shared across one repository's cut-offs oldest first, a subject an earlier cut-off counted is a
    REPEAT here (score())."""
    end, rev = window(repo, cutoff, horizon)
    if not rev:
        return {"end": end, "error": f"the window would end {end}, past this history"}
    from .harness import rev_at
    after = After(repo, rev, cutoff, before_rev=rev_at(repo, cutoff) or "")
    fired = {(f.get("rule") or {}).get("id") for f in findings} - {None}
    scored = {name for name in RULES if name in fired or name.split("_mixed")[0] in fired}
    return {"end": end, "after": rev, "findings": len(findings), "rules": counts(score(findings, after, seen)),
            "unscored": sorted(fired - scored)}


def _load(path: str) -> dict:
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("report", nargs="+", help="a --json export made at the cut-off; several, made at several cut-offs "
                                             "of one repository, count each subject once, at the first that flagged it")
    p.add_argument("--repo", default=".")
    p.add_argument("--horizon", type=int, default=HORIZON, metavar="MONTHS",
                   help=f"months from the cut-off to the far end of the window (default {HORIZON})")
    p.add_argument("--after", metavar="REV", help="score against this commit instead of the one the horizon picks "
                                                  "(one export only)")
    args = p.parse_args(argv)
    exports = [_load(path) for path in args.report]
    if args.after and len(exports) > 1:
        print("remediation: --after places one window; give one export with it", file=sys.stderr)
        return 2
    for path, export in zip(args.report, exports):
        if not export.get("findings"):
            print(f"remediation: {path} carries no findings", file=sys.stderr)
            return 2
    # oldest cut-off first, so a subject is counted at the first export that flagged it
    order = sorted(range(len(exports)), key=lambda i: ((exports[i].get("meta") or {}).get("now") or "", i))
    from .harness import rev_at
    windows = []
    for i in order:
        cutoff = (exports[i].get("meta") or {}).get("now") or ""
        rev, end = args.after, ""
        if not rev:
            if not cutoff:
                print(f"remediation: {args.report[i]} records no reference date, so the window cannot be placed; "
                      "pass --after", file=sys.stderr)
                return 2
            end, rev = window(args.repo, cutoff, args.horizon)
            if not rev:
                print(f"remediation: the window would end {end}, past this history. Move the cut-off back "
                      f"at least {args.horizon} months, or the rates are depressed by findings nobody has had time to act on.",
                      file=sys.stderr)
                return 2
        windows.append((exports[i], cutoff, rev, end))
    seen = set() if len(windows) > 1 else None
    scored, skipped = {}, []
    for export, cutoff, rev, end in windows:
        before_rev = (rev_at(args.repo, cutoff) or "") if cutoff else ""
        after = After(args.repo, rev, cutoff, before_rev=before_rev)
        if after.renames_skipped:
            skipped.append(cutoff or rev)
        for name, counts in score(export["findings"], after, seen).items():
            scored.setdefault(name, Counter()).update(counts)
    if len(windows) == 1:
        _, cutoff, rev, end = windows[0]
        print(f"### Acted on by {end or rev}, against findings made at {cutoff or 'the export'}\n")
    else:
        print(f"### Acted on within {args.horizon} months, against findings made at "
              f"{', '.join(c for _, c, _, _ in windows)}, each subject counted at the first cut-off that flagged it\n")
    print(table(scored) if scored else "No scored rule fired in this export.")
    repeats = sum(c[REPEAT] for c in scored.values())
    if repeats:
        print(f"\n{repeats} subject(s) flagged again at a later cut-off are counted once, at the first.")
    if skipped:
        print(f"\ngit skipped inexact rename detection past diff.renameLimit={RENAME_LIMIT} in the window from "
              f"{', '.join(skipped)}, so a file moved with edits there reads as gone.")
    fired = {(f.get("rule") or {}).get("id") for export, _, _, _ in windows for f in export["findings"]}
    text = unscored(fired)
    if text:
        print(text, end="")
    return 0


if __name__ == "__main__":
    sys.exit(main())

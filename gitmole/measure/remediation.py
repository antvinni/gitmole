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

NOT_OBSERVABLE is a statement about the advice's wording, not about the finding's value. Pairing
someone on a knowledge island leaves no trace in a tree, which makes the advice unmeasurable here and
says nothing about whether taking it was worth it. Where this list and the hand labels agree, two
methods agreed; that is worth recording and is not the same as either being right.

    python -m gitmole.measure.remediation REPORT.json --repo DIR [--horizon 6]

REPORT.json is a `--json` export made at the cut-off; the horizon picks the commit at the far end
through trend.rev_before, the way the rest of the harness picks one.

A subject the tree did not hold at the cut-off is counted ABSENT and left out of every share. Without
that gate curl's specimen values read as 90% remediated, because the secrets rules name paths from the
whole history and most of those files had been deleted years before the cut-off. The secrets rules are
in NOT_OBSERVABLE for the same reason: the value stays in history whatever the tree does.

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
    from .. import trend
    end = months_after(cutoff, horizon)
    last = subprocess.run([*GIT, "log", "-1", "--format=%cs"], cwd=repo,
                          capture_output=True, text=True).stdout.strip()
    if not last or end > last:
        return end, None
    return end, trend.rev_before(repo, end, end_of_day=False)


class After:
    """The tree at the far end of the window, and when each path was last touched.

    One `ls-tree` and one `cat-file --batch` serve every predicate, so a rule with two hundred
    subjects costs two processes rather than two hundred.

    `at_cutoff` holds the paths the tree had when the finding was made, because several rules name
    subjects the cut-off tree does not contain: the secrets rules read every commit on every branch,
    so they name paths deleted years earlier. Counting those as "the file left the tree" turned
    curl's specimen values into a 90% remediation rate for acts nobody performed in the window."""

    def __init__(self, repo: str, rev: str, cutoff: str = "", before_rev: str = ""):
        self.repo, self.rev, self.cutoff = repo, rev, cutoff
        self.at_cutoff = None
        if before_rev:
            out = subprocess.run([*GIT, "ls-tree", "-r", "-z", "--name-only", before_rev], cwd=repo,
                                 capture_output=True, check=True).stdout
            self.at_cutoff = {p.decode("utf-8", "surrogateescape") for p in out.split(b"\0") if p}
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


def _named_function(s, after):
    """A weak proxy: the function is gone by name. Whether a surviving one got simpler needs a second
    run's function metrics, so that case is UNKNOWN rather than OPEN."""
    text = after.text(s["file"])
    if text is None:
        return GONE
    name = s.get("function") or s.get("name") or ""
    if not name or name == "(anonymous)":
        return UNKNOWN
    return RESOLVED if name not in text else UNKNOWN


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
    "secrets_in_source": "betterleaks reads every commit on every branch, so the value stays in history "
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
    "tight_coupling": "describes a layout, names no act",
    "dormant": "a property of the repository, not a defect",
    "placeholder_identity": "a .mailmap entry is observable, but the finding names no one path to check",
    "signoff_by_co_author": "history cannot be un-signed",
    "sweeping_commits": "history cannot be un-committed",
    "import_commits": "history cannot be un-committed",
    "tangled_commits": "history cannot be un-committed",
}

# Rules that name their subjects only as totals. Extending the evidence to list them is what makes
# them measurable; until then they are neither scored nor written off.
NO_SUBJECTS = {
    "stale_files": "evidence gives counts, not the stale paths",
    "duplication": "blocks carry places, but matching a block's text across a window needs the second run",
    "complexity_growth": "needs the second run's per-file complexity, not the tree",
    "bug_magnets": "the outcome is more fixes, which the watch-list backtest already measures",
}


def _present_at_cutoff(subject, after: After) -> bool:
    """Whether the path a subject names was in the tree when the finding was made. A subject with no
    path (a dependency, an action ref) is always judged; only paths can be already-deleted."""
    path = subject.get("file") if isinstance(subject, dict) else subject
    if not isinstance(path, str) or "/" not in path and "." not in path:
        return True
    return path in after.at_cutoff


def score(findings: list, after: After) -> dict:
    """rule -> Counter of outcomes over every subject its findings named."""
    out = {}
    for finding in findings:
        rule = (finding.get("rule") or {}).get("id")
        evidence = finding.get("evidence") or {}
        for name, (subjects, predicate, _) in RULES.items():
            if name.split("_mixed")[0] != rule and name != rule:
                continue
            counts = out.setdefault(name, Counter())
            for subject in subjects(evidence):
                at_cutoff = getattr(after, "at_cutoff", None)   # a stub tree need not carry one
                if at_cutoff is not None and not _present_at_cutoff(subject, after):
                    counts[ABSENT] += 1       # the window cannot speak for a file that was already gone
                    continue
                try:
                    counts[predicate(subject, after)] += 1
                except (KeyError, TypeError, subprocess.SubprocessError):
                    counts[UNKNOWN] += 1
    return out


def acted_on(counts: Counter, gone_is_fix: bool):
    """Share of the subjects the repository acted on, or None when nothing could be judged. This is
    not precision and not worth: see the module docstring."""
    fixed = counts[RESOLVED] + (counts[GONE] if gone_is_fix else 0)
    judged = fixed + counts[OPEN]
    return (fixed / judged) if judged else None


MIN_JUDGED = 5   # below this a share is printed as the fraction it is: 1 of 1 is not 100%


def judged(counts: Counter, gone_is_fix: bool) -> int:
    """How many subjects the window could speak for: the denominator behind the share."""
    return counts[RESOLVED] + counts[OPEN] + (counts[GONE] if gone_is_fix else 0)


def table(scored: dict) -> str:
    """One row per rule, mechanical first. Every subject is accounted for in a column, since the
    denominator is the part a reader has to see: a share over two judged subjects and a share over
    two hundred are not the same claim. Each band pools its subjects rather than averaging its rules,
    so one rule with a single subject cannot move the band, and the two bands stay apart because a
    project pins an action far more readily than it splits a class."""
    rows = ["| rule | kind | subjects | acted on | still open | left the tree | can't say | gone before | share |",
            "|---|---|---:|---:|---:|---:|---:|---:|---:|"]
    bands = {"mechanical": Counter(), "structural": Counter()}
    for name, counts in sorted(scored.items(), key=lambda kv: (kv[0] not in MECHANICAL, kv[0])):
        kind = "mechanical" if name in MECHANICAL else "structural"
        gone_is_fix = RULES[name][2]
        n = judged(counts, gone_is_fix)
        fixed = counts[RESOLVED] + (counts[GONE] if gone_is_fix else 0)
        bands[kind].update({"fixed": fixed, "judged": n})
        if not n:
            shown = "-"
        elif n < MIN_JUDGED:
            shown = f"{fixed} of {n}"
        else:
            shown = format(fixed / n, ".0%")
        rows.append(f"| {name} | {kind} | {sum(counts.values())} | {counts[RESOLVED]} | "
                    f"{counts[OPEN]} | {counts[GONE]} | {counts[UNKNOWN]} | {counts[ABSENT]} | {shown} |")
    for kind, totals in bands.items():
        if totals["judged"]:
            line = f"\n{kind}: {totals['fixed']} of {totals['judged']} subjects acted on"
            if totals["judged"] >= MIN_JUDGED:
                line += f", {format(totals['fixed'] / totals['judged'], '.0%')}"
            rows.append(line + ".")
        elif totals:
            rows.append(f"\n{kind}: no subject the window could speak for.")
    return "\n".join(rows)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("report", help="a --json export made at the cut-off")
    p.add_argument("--repo", default=".")
    p.add_argument("--horizon", type=int, default=HORIZON, metavar="MONTHS",
                   help=f"months from the cut-off to the far end of the window (default {HORIZON})")
    p.add_argument("--after", metavar="REV", help="score against this commit instead of the one the horizon picks")
    args = p.parse_args(argv)
    with open(args.report, encoding="utf-8") as fh:
        export = json.load(fh)
    findings = export.get("findings") or []
    if not findings:
        print("remediation: the export carries no findings", file=sys.stderr)
        return 2
    cutoff = (export.get("meta") or {}).get("now") or ""
    rev, end = args.after, ""
    if not rev:
        if not cutoff:
            print("remediation: the export records no reference date, so the window cannot be placed; pass --after",
                  file=sys.stderr)
            return 2
        end, rev = window(args.repo, cutoff, args.horizon)
        if not rev:
            print(f"remediation: the window would end {end}, past this history. Move the cut-off back "
                  f"at least {args.horizon} months, or the rates are depressed by findings nobody has had time to act on.",
                  file=sys.stderr)
            return 2
    from .. import trend
    before_rev = trend.rev_before(args.repo, cutoff, end_of_day=False) if cutoff else ""
    after = After(args.repo, rev, cutoff, before_rev=before_rev)
    scored = score(findings, after)
    print(f"### Acted on by {end or rev}, against findings made at {cutoff or 'the export'}\n")
    print(table(scored) if scored else "No scored rule fired in this export.")
    fired = {(f.get("rule") or {}).get("id") for f in findings}
    silent = sorted(fired & set(NOT_OBSERVABLE))
    if silent:
        print("\nFired, and names no act a later tree can show. Not a verdict on their worth:\n")
        for name in silent:
            print(f"- **{name}** — {NOT_OBSERVABLE[name]}")
    pending = sorted(fired & set(NO_SUBJECTS))
    if pending:
        print("\nFired, but its evidence does not name its subjects:\n")
        for name in pending:
            print(f"- **{name}** — {NO_SUBJECTS[name]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Which commits the fix-locality outcome counts as fixes, by one of two definitions the harness fixes.

`current` is maat.is_fix as 0.44.0 shipped it, frozen in this module (is_current_fix): a Conventional
`fix:` prefix or a fix or bug word anywhere in the subject. `declared` takes the repository at its word
where it declares the Conventional Commits convention: a commit is a fix if and only if its type is `fix`,
so "ci: fix event name" and "docs: fix image path" are not fixes and an untyped subject is not one either.
The convention is decided window by window: a window declares it when the tree at its cut-off tracks a
commitlint or commitizen configuration at its root, or when at least TYPED_SHARE of the window's own
subjects are typed; a window that does neither is scored by `current` under both names, so the two
outcomes differ only where the repository had said how its commits are typed.

The definitions live here, in the harness's tree, and are read neither from the release being measured
nor from the live maat.is_fix: a candidate that changes maat.is_fix is scored against the outcome this
module defines, so a change to the classifier and a change to the yardstick cannot travel together
(AGENTS.md, rule 3). Both outcomes cover the files a fix touched (evaluate.fixed_between) and the R-SZZ
outcome built from the fixes (evaluate.induced_between over maat.fix_commits); maat.is_fix itself is not
changed.

The labelled outcome (the holdout's ApacheJIT labels) does not depend on either definition and is not
switched."""
from __future__ import annotations

import json
import re
import subprocess

from .. import filetypes, maat

OUTCOMES = ("current", "declared")
DEFAULT = "current"

# The share of typed subjects at which a repository that tracks no configuration still declares the
# convention: the threshold the univer debate set before any run (plan-final.md, PRD4h; msr-researcher r1),
# not swept and not fitted to a corpus repository. A repository that writes "area: text" subjects (curl,
# git, the kernel) has the shape without a type, so the type vocabulary below is what tells the two apart.
TYPED_SHARE = 0.9

# The Conventional Commits types: fix and feat from the specification (conventionalcommits.org, 1.0.0), the
# rest from @commitlint/config-conventional's type-enum, the Angular convention the specification grew from.
# The convention's own vocabulary, not one learned from a repository.
TYPES = ("build", "chore", "ci", "docs", "feat", "fix", "perf", "refactor", "revert", "style", "test")
_TYPED = re.compile(r"^(" + "|".join(TYPES) + r")(?:\([^)]*\))?!?: \S", re.I)

# Where each tool looks for its configuration at the repository's root (commitlint through cosmiconfig;
# commitizen for JavaScript, cz-cli, and for Python). package.json and pyproject.toml declare it by a key.
COMMITLINT_FILES = (".commitlintrc", ".commitlintrc.json", ".commitlintrc.yaml", ".commitlintrc.yml", ".commitlintrc.js",
                    ".commitlintrc.cjs", ".commitlintrc.mjs", ".commitlintrc.ts", ".commitlintrc.cts", "commitlint.config.js",
                    "commitlint.config.cjs", "commitlint.config.mjs", "commitlint.config.ts", "commitlint.config.cts")
COMMITIZEN_FILES = (".czrc", ".cz.json", "cz.json", ".cz.toml", "cz.toml", ".cz.yaml", "cz.yaml", ".cz.yml", "cz.yml")


# `current`, frozen: maat.is_fix as 0.44.0 shipped it, copied here so that a candidate editing maat.is_fix
# cannot move the outcome it is scored against (`candidate BASE worktree` runs this harness from the
# candidate's own tree). tests/test_outcome.py checks the copy against maat.is_fix and fails on purpose
# when the classifier changes: then the copy stays, and the new classifier is a candidate.
CURRENT_FROM = "0.44.0"
_CURRENT_CONVENTIONAL = re.compile(r"^(fix|hotfix|bugfix)(\([^)]*\))?!?:", re.I)
_CURRENT_WORDS = re.compile(r"\b(fix|fixes|fixed|fixing|bugfix|hotfix|bug|bugs|regression|crash|crashes)\b", re.I)


def is_current_fix(subject: str) -> bool:
    """A fix by the `current` outcome: 0.44.0's maat.is_fix, a `fix:` prefix or a fix or bug word."""
    return bool(_CURRENT_CONVENTIONAL.match(subject or "") or _CURRENT_WORDS.search(subject or ""))


def commit_type(subject: str):
    """The Conventional Commits type of a subject, lower-cased, or None when the subject is not typed."""
    m = _TYPED.match(subject or "")
    return m.group(1).lower() if m else None


def is_declared_fix(subject: str) -> bool:
    """A fix by the declared convention: the subject's type is `fix` (with or without a scope or `!`)."""
    return commit_type(subject) == "fix"


def typed_share(subjects) -> dict:
    """{"typed", "subjects", "share"} over `subjects`, less git's own revert subjects, which commitlint
    ignores too."""
    counted = [s for s in subjects if s and not maat.is_revert(s)]
    typed = sum(1 for s in counted if commit_type(s))
    return {"typed": typed, "subjects": len(counted), "share": round(typed / len(counted), 4) if counted else None}


def _git(repo: str, *args):
    try:
        proc = subprocess.run([*filetypes.GIT, *args], cwd=repo, capture_output=True)
    except OSError:   # no such directory: nothing declared
        return None
    return proc.stdout.decode("utf-8", "replace") if proc.returncode == 0 else None


def config_files(repo: str, rev: str = "HEAD") -> list:
    """The commitlint and commitizen configurations tracked at the root of `rev`, by name; a key in
    package.json or pyproject.toml is named as `file#key`."""
    names = set((_git(repo, "ls-tree", "--name-only", rev) or "").split("\n"))
    found = sorted(n for n in names if n in COMMITLINT_FILES or n in COMMITIZEN_FILES)
    if "package.json" in names:
        try:
            pkg = json.loads(_git(repo, "show", f"{rev}:package.json") or "{}")
        except ValueError:
            pkg = {}
        if isinstance(pkg, dict):
            if "commitlint" in pkg:
                found.append("package.json#commitlint")
            if isinstance(pkg.get("config"), dict) and "commitizen" in pkg["config"]:
                found.append("package.json#config.commitizen")
    if "pyproject.toml" in names and re.search(r"(?m)^\[tool\.commitizen\]", _git(repo, "show", f"{rev}:pyproject.toml") or ""):
        found.append("pyproject.toml#tool.commitizen")
    return found


def window_subjects(commits) -> list:
    """The subjects a window's typed share is taken over: the canonical log's commits that touched a file,
    which leaves the merges out (git log --numstat lists no files for a merge)."""
    return [c.get("subject", "") for c in commits if c.get("files")]


def convention(repo: str, rev: str = "HEAD", subjects=None) -> dict:
    """Whether the repository declares the Conventional Commits convention, and on what evidence: the
    configurations tracked at the root of `rev` (named) and the share of `subjects` that are typed
    (default: every non-merge subject reachable from `rev`). The harness asks it once per cut-off, with
    the tree at the cut-off and the window's own subjects (window_conventions)."""
    if subjects is None:
        subjects = (_git(repo, "log", rev, "--no-merges", "--format=%s") or "").split("\n") if rev else []
    share = typed_share(subjects)
    config = config_files(repo, rev) if rev else []
    by = (["config"] if config else []) + (["typed share"] if share["share"] is not None and share["share"] >= TYPED_SHARE else [])
    return {"declared": bool(by), "by": by, "config": config, **share, "threshold": TYPED_SHARE}


def window_conventions(repo: str, windows: dict) -> dict:
    """{cut-off: (rev, subjects)} -> the repository's convention window by window: each decided from the
    configuration tracked in the tree at its cut-off (`rev`, None before the history starts) or the typed
    share of its own subjects. Decided at the pin and applied to every window, a late adopter's untyped
    fixes from before it adopted the convention would be dropped from the early windows: an outcome
    labelled with what the repository did later, the leak fixed_between guards against. `declared` is
    whether any window declares it; `config` every configuration named at any cut-off."""
    return combine({t: convention(repo, rev, subjects) for t, (rev, subjects) in sorted(windows.items())})


def combine(per: dict) -> dict:
    """{cut-off: convention} -> the repository's record of them (window_conventions)."""
    shares = [w["share"] for w in per.values() if w["share"] is not None]
    return {"declared": any(w["declared"] for w in per.values()), "windows": per,
            "config": sorted({c for w in per.values() for c in w["config"]}),
            "share": max(shares) if shares else None, "threshold": TYPED_SHARE}


def predicate(name: str, conv: dict = None):
    """The fix classifier an outcome uses: is_current_fix (0.44.0's maat.is_fix, frozen here) for
    `current`, and for `declared` the type alone where `conv` (one window's convention) declares the
    convention, is_current_fix where it does not."""
    if name not in OUTCOMES:
        raise ValueError(f"unknown outcome {name!r}: one of {', '.join(OUTCOMES)}")
    return is_declared_fix if name == "declared" and conv and conv.get("declared") else is_current_fix


def describe(conv: dict) -> str:
    """One cell for a table: what the repository declares, or why the declared outcome is the current one."""
    if conv is None:
        return "labels"
    pct = "-" if conv.get("share") is None else f"{100 * conv['share']:.0f}% typed"
    windows = conv.get("windows")
    if windows is not None:
        k = sum(1 for w in windows.values() if w["declared"])
        if not k:
            return f"no (at most {pct} in a window)"
        return f"declared in {k} of {len(windows)} windows ({', '.join(conv['config']) or 'typed share'})"
    if not conv.get("declared"):
        return f"no ({pct})"
    return ", ".join(conv.get("config") or []) + (f"; {pct}" if conv.get("config") else pct)

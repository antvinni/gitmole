"""The versions of the tools gitmole runs, pinned so that one gitmole version means one toolchain.

gitmole's own output is deterministic, but the tools it runs are not gitmole: a newer betterleaks can
change what counts as a secret, a newer scc can count a language differently, and the report would move
with no change here. The Homebrew formula installs exactly these versions into `libexec/tools`, which the
`gitmole` wrapper puts first on PATH, and `docs/development.md` says how to move one. A run that finds
another version still runs: it says so once on stderr and records both versions in `meta.json`, so two
reports that differ can be told apart by cause.

`tests/test_tools.py` holds this table to the formula, so the two cannot drift apart.
"""
from __future__ import annotations

# tool -> the version the formula installs. Moving one is a release of its own: bump it here and in
# Formula/gitmole.rb, then measure, since a tool's own rules decide part of the report.
PINNED = {
    "scc": "4.1.0",
    "git-sizer": "1.5.0",
    "betterleaks": "1.8.1",
    "jscpd": "5.3.0",
    "osv-scanner": "2.6.0",
    "lizard": "1.24.0",
}


def differences(found: dict) -> list:
    """[(tool, pinned, found)] for the tools whose version is not the pinned one, sorted. A tool that is
    missing (None) is left out: the run refuses on missing tools before this is asked."""
    out = []
    for name, pinned in sorted(PINNED.items()):
        version = found.get(name)
        if version and version != pinned:
            out.append((name, pinned, version))
    return out


def note(found: dict) -> str | None:
    """The one line a run prints when its toolchain is not the pinned one, or None."""
    diffs = differences(found)
    if not diffs:
        return None
    named = "; ".join(f"{name} {version}, pinned {pinned}" for name, pinned, version in diffs)
    return f"tool versions differ from the pinned set: {named}"

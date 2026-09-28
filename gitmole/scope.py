"""--path: the part of the tree a report describes. A run without it has no scope, and every helper
here is then the identity, so the whole-repository report is the one it always was.

A scope is a sorted list of directories relative to the repository root, without a trailing slash,
none inside another. meta.json records it as "scope" only when there is one."""
from __future__ import annotations

import posixpath
import subprocess

# The steps whose meaning is the repository, not a directory of it: they run over the whole clone
# whatever --path says, and the report says so in one line (docs/cli.md says why, step by step).
REPOSITORY_WIDE = "repository-wide: secrets, dependencies, signing, repository size, workflows, policy and agent files"


def clean(dirs) -> list:
    """The directories as given, in the one spelling a scope keeps: forward slashes, no "./", no trailing
    slash; "." (the root) drops out, and a directory inside another given one is the other's. Raises
    ValueError for a path that leaves the repository or is absolute. No git: the output directory's name
    is decided before the clone exists."""
    out = set()
    for d in dirs or ():
        raw = (d or "").replace("\\", "/").strip()
        if raw.startswith("/"):
            raise ValueError(f"--path wants a directory relative to the repository root, got {d!r}")
        norm = posixpath.normpath(raw) if raw else "."
        if norm == ".." or norm.startswith("../"):
            raise ValueError(f"--path {d!r} leaves the repository")
        if norm != ".":
            out.add(norm)
    kept = sorted(out)
    return [d for d in kept if not any(d.startswith(o + "/") for o in kept if o != d)]


def validate(repo: str, dirs: list) -> None:
    """Raise ValueError unless every directory is a directory of the tree at HEAD."""
    for d in dirs:
        proc = subprocess.run(["git", "cat-file", "-t", f"HEAD:{d}"], cwd=repo, capture_output=True, text=True)
        kind = proc.stdout.strip()
        if kind != "tree":
            what = f"is a {'file' if kind == 'blob' else kind}" if proc.returncode == 0 else "is not in the tree at HEAD"
            raise ValueError(f"--path {d}: {what}; it wants a directory of the tree at HEAD, relative to the repository root")


def of(meta: dict) -> list:
    """The scope a run recorded, or [] for the whole repository."""
    return list((meta or {}).get("scope") or [])


def within(path: str, dirs) -> bool:
    """Whether `path` is under one of `dirs`; everything is, with no scope."""
    return not dirs or any(path.startswith(d + "/") or path == d for d in dirs)


def keep(paths, dirs) -> list:
    return list(paths) if not dirs else [p for p in paths if within(p, dirs)]


def pathspec(dirs) -> list:
    """What a git command that walks history or lists files appends: nothing, or -- and the directories."""
    return ["--", *(":(literal)" + d for d in dirs)] if dirs else []   # literal: a directory named with * or ? is that directory


def base(dirs) -> int:
    """How many directory levels every scoped path shares: the depth the knowledge map and the components
    count their areas from. 0 without a scope, or when the directories share no parent."""
    if not dirs:
        return 0
    parts = [d.split("/") for d in dirs]
    n = 0
    while all(len(p) > n for p in parts) and len({p[n] for p in parts}) == 1:
        n += 1
    return n


def report_base(report: dict) -> int:
    """base() of the scope a report's run recorded: 0 for the whole repository."""
    return base(of((report or {}).get("meta")))


def label(dirs) -> str:
    """The header's words for the scope: 'path backend/plugins/github'."""
    return ("path " if len(dirs) == 1 else "paths ") + ", ".join(dirs)


def slug(dirs) -> str:
    """The output directory's suffix, so a scoped run never lands on the whole repository's directory."""
    return "+".join(d.replace("/", "-") for d in dirs)

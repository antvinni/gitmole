"""What gitmole leaves behind, found by looking: temp clones in the temp folder, analysis-* output
directories under a base, and tools --install-tools placed for pins this gitmole no longer has. Pure
functions; the CLI prints, asks and reports."""
from __future__ import annotations

import glob
import os
import shutil
import tempfile

from . import run, tools, userdirs

TEMP_PREFIX = "gitmole-"      # tempfile.mkdtemp(prefix=...) in cli._resolve_target and cli._portfolio
OUT_PREFIX = "analysis-"      # run.output_dir and cli._portfolio


def temp_dir() -> str:
    """Where the temp clones went: mkdtemp(dir=os.environ.get("TMPDIR")) resolves the same way."""
    return os.environ.get("TMPDIR") or tempfile.gettempdir()


def _is_output(path: str) -> bool:
    return os.path.isdir(path) and os.path.isfile(os.path.join(path, "meta.json"))


def _whole_portfolio(path: str) -> bool:
    """A portfolio parent is gitmole's as a whole when every directory in it is a repo output and every
    other entry is a portfolio.* export or a dotfile."""
    names = os.listdir(path)
    dirs = [n for n in names if os.path.isdir(os.path.join(path, n))]
    rest = [n for n in names if n not in dirs and not n.startswith(".")]
    return bool(dirs) and all(_is_output(os.path.join(path, n)) for n in dirs) and all(n.startswith("portfolio.") for n in rest)


def _outputs(base: str) -> list:
    candidates = sorted(glob.glob(os.path.join(base, OUT_PREFIX + "*")))
    if os.path.isdir(os.path.join(base, ".git")):
        candidates.append(run.output_dir("path", base, None))
    found = []
    for path in candidates:
        if not os.path.isdir(path):
            continue
        if _is_output(path) or _whole_portfolio(path):
            found.append(path)
        else:
            found += [c for c in sorted(glob.glob(os.path.join(path, "*"))) if _is_output(c)]
    return sorted(set(found))


def _clones(tmp: str) -> list:
    paths = [p for p in glob.glob(os.path.join(tmp, TEMP_PREFIX + "*")) if os.path.isdir(p)]
    return sorted(paths, key=lambda p: (os.path.getmtime(p), p))


def _stale_tools(root: str | None) -> list:
    """<tool>-<version> directories under the tool root other than the current pins' (run.env_path never puts
    them on PATH, so they only take space). Only a directory that holds nothing but that tool is listed:
    GITMOLE_TOOLS may name a directory the user keeps other things in, and nothing of theirs is gitmole's to
    delete. The current pins' copies are in use and are not listed."""
    if not root or not os.path.isdir(root):
        return []
    current = {f"{name}-{tools.PINNED[name]}" for name in run.REQUIRED_TOOLS}
    found = []
    for entry in sorted(os.listdir(root)):
        path = os.path.join(root, entry)
        tool = next((t for t in run.REQUIRED_TOOLS if entry.startswith(t + "-") and entry[len(t) + 1:][:1].isdigit()), None)
        if tool and entry not in current and os.path.isdir(path) and not os.path.islink(path) and os.listdir(path) == [tool]:
            found.append(path)
    return found


def tree_size(path: str) -> int:
    if os.path.isfile(path):
        return os.lstat(path).st_size
    total = 0
    for root, _dirs, files in os.walk(path):
        for name in files:
            try:
                total += os.lstat(os.path.join(root, name)).st_size
            except OSError:
                pass
    return total


def find(base: str, tmp: str) -> list:
    """(path, bytes, mtime) for everything gitmole left behind: temp clones oldest first, then output
    directories under base sorted by path, then tools installed for pins no longer in use."""
    paths = _clones(tmp) + _outputs(os.path.abspath(base)) + _stale_tools(userdirs.tools_root())
    return [(p, tree_size(p), os.path.getmtime(p)) for p in paths]


def human(n) -> str:
    units = ["B", "kB", "MB", "GB", "TB"]
    x, i = float(n), 0
    while x >= 1000 and i < len(units) - 1:
        x /= 1000
        i += 1
    if i == 0:
        return f"{int(x)} B"
    return f"{x:.1f} {units[i]}" if x < 10 else f"{x:.0f} {units[i]}"


def remove(paths: list) -> list:
    """rmtree each path, best effort; returns the ones still present afterwards."""
    failed = []
    for p in paths:
        if os.path.isdir(p) and not os.path.islink(p):
            shutil.rmtree(p, ignore_errors=True)
        else:
            try:
                os.remove(p)
            except OSError:
                pass
        if os.path.exists(p):
            failed.append(p)
    return failed

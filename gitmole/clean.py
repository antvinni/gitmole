"""What gitmole leaves behind, found by looking: temp clones in the temp folder and analysis-* output
directories under a base. Pure functions; the CLI prints, asks and reports."""
from __future__ import annotations

import glob
import os
import shutil
import tempfile

from . import run

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


def tree_size(path: str) -> int:
    total = 0
    for root, _dirs, files in os.walk(path):
        for name in files:
            try:
                total += os.lstat(os.path.join(root, name)).st_size
            except OSError:
                pass
    return total


def find(base: str, tmp: str) -> list:
    """(path, bytes, mtime) for every directory gitmole left behind: temp clones oldest first, then
    output directories under base sorted by path."""
    paths = _clones(tmp) + _outputs(os.path.abspath(base))
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
        shutil.rmtree(p, ignore_errors=True)
        if os.path.exists(p):
            failed.append(p)
    return failed

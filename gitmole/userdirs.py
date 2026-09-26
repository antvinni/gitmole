"""The per-user directories gitmole keeps things in: the structure cache and the downloaded tools. One place,
so XDG, a relative value and a home that cannot be found follow the same rules for both.

A tool directory goes first on PATH and every step runs with cwd set to the scanned repository, so a
relative path there would name a directory inside the repository, and gitmole would run the executables the
repository ships. Every tool path here is absolute or None, never relative."""
from __future__ import annotations

import os
import sys

try:
    from . import tools
except ImportError:  # structure.py run as a script: the package directory is sys.path[0]
    import tools

_MACOS = {"cache": "~/Library/Caches", "data": "~/Library/Application Support"}
_XDG = {"cache": ("XDG_CACHE_HOME", "~/.cache"), "data": ("XDG_DATA_HOME", "~/.local/share")}


def absolute(path: str) -> str | None:
    """path with ~ expanded, or None when it is still not absolute (a relative value, or ~ with no home)."""
    if not path:
        return None
    path = os.path.expanduser(path)
    return os.path.normpath(path) if os.path.isabs(path) else None


def base(kind: str, env=None) -> str | None:
    """The platform's per-user directory of this kind, 'cache' or 'data': ~/Library/Caches or ~/Library/
    Application Support on macOS; elsewhere XDG_CACHE_HOME or XDG_DATA_HOME when absolute (a relative one is
    ignored, as the XDG spec says), else ~/.cache or ~/.local/share. None when there is no home to find."""
    env = os.environ if env is None else env
    if sys.platform == "darwin":
        return absolute(_MACOS[kind])
    name, default = _XDG[kind]
    xdg = env.get(name)
    return xdg if xdg and os.path.isabs(xdg) else absolute(default)


def tools_root(env=None) -> str | None:
    """Where --install-tools puts the tools: GITMOLE_TOOLS with ~ expanded, else <data>/gitmole/tools. None
    when that is not an absolute path: a relative GITMOLE_TOOLS is refused, not resolved against whatever
    directory gitmole happens to start in. A directory of gitmole's own, not ~/.local/bin, so nothing in it
    shadows a tool the user installed anywhere but inside a gitmole run."""
    env = os.environ if env is None else env
    explicit = env.get("GITMOLE_TOOLS")
    if explicit:
        return absolute(explicit)
    root = base("data", env)
    return os.path.join(root, "gitmole", "tools") if root else None


def tool_dir(name: str, env=None) -> str | None:
    """<root>/<tool>-<pin>, the directory one pinned tool lives in. Keyed by the pin, so a copy left by an
    older gitmole is never on the PATH of one that pins another version: it is only left behind (--clean)."""
    root = tools_root(env)
    return os.path.join(root, f"{name}-{tools.PINNED[name]}") if root else None


def tool_dirs(names: list) -> list:
    """The directories --install-tools made for these tools at the current pins, those that exist, in order:
    what goes first on PATH wherever gitmole runs one of them."""
    return [d for d in (tool_dir(name) for name in names) if d and os.path.isdir(d)]

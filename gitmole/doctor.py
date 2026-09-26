"""gitmole --doctor: every tool gitmole runs, the version found against the version pinned, and where to
get the pinned one. The same lookups a run makes (run.tool_version, run.lizard_version), so what this
says is what the next report's run.tools_moved will say. Exit 0 when every tool is at its pin, 1 otherwise."""
from __future__ import annotations

import shlex
import shutil
import sys

from . import run, tools

NAMES = [*run.REQUIRED_TOOLS, "lizard"]


def _present(name: str) -> bool:
    return run.has_lizard() if name == "lizard" else run.has_tool(name)


def _version(name: str):
    return run.lizard_version() if name == "lizard" else run.tool_version(name)


def rows(present=_present, version_of=_version) -> list:
    """One row per tool: found, pinned, and a state (ok, moved, missing, or no version when the tool
    is there but printed none)."""
    out = []
    for name in NAMES:
        pinned, here = tools.PINNED.get(name), present(name)
        found = version_of(name) if here else None
        state = ("missing" if not here else "no version" if found is None
                 else "ok" if found == pinned else "moved")
        out.append({"tool": name, "pinned": pinned, "found": found, "state": state})
    return out


def download_command(which=shutil.which) -> str:
    """deps.DOWNLOAD with the osv-scanner a run uses, by full path when the user's own PATH would find
    another or none: installed by --install-tools, it is on gitmole's PATH only (run.env_path), and a
    bare `osv-scanner` pasted into a shell is then not found. The path is quoted: macOS's has a space."""
    from . import deps
    ours, theirs = which("osv-scanner", path=run.env_path()), which("osv-scanner")
    if not ours or ours == theirs:
        return deps.DOWNLOAD
    return deps.DOWNLOAD.replace("osv-scanner", shlex.quote(ours), 1)


def main(console, rows_of=rows, structure_of=run.has_structure, db_of=None, command_of=download_command) -> int:
    from . import cli, deps   # cli imports this module inside main(), so neither import runs at load
    db_of = deps.database_date if db_of is None else db_of
    say = lambda line: console.print(line, markup=False, highlight=False, soft_wrap=True)   # a command wrapped mid-line cannot be pasted
    listed = rows_of()
    width = max(len(r["tool"]) for r in listed)
    shown = [r["found"] or r["state"] for r in listed]
    column = max(len(v) for v in shown)
    for r, found in zip(listed, shown):
        if r["state"] == "ok":
            say(f"{r['tool']:<{width}}  {found:<{column}}  ok")
        else:
            say(f"{r['tool']:<{width}}  {found:<{column}}  pinned {r['pinned']}: {tools.RELEASES[r['tool']]}")
    say("structure step: " + ("available" if structure_of() else "skipped, the tree-sitter grammars do not import (they need Python 3.10 or newer)"))
    db_date = db_of()
    say("vulnerability database: " + (db_date or f"none; inside a clone, run: {command_of()}"))
    off = [r["tool"] for r in listed if r["state"] != "ok"]
    if "lizard" in off:   # a Python package of this interpreter: neither --install-tools nor a separate formula moves it
        say(f"lizard: {shlex.quote(sys.executable)} -m pip install lizard=={tools.PINNED['lizard']}")
    if set(off) & set(run.REQUIRED_TOOLS):
        say(cli.INSTALL_HINT)
        say(cli.INSTALL_URL)
    return 1 if off else 0

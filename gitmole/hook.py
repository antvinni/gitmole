"""The agent-hook gate: `gitmole OUT_DIR --no-run --hook [--risk-threshold N] [-- FILE...]`, after Codacy's
argument for deterministic findings before inference and Zimmermann et al.'s co-change recommendations.

Deterministic findings should run before inference, so the model reasons over a short list rather
than rediscovering known issues. A linter says what is wrong in the diff; gitmole says what history
says about the files the diff touches, and no other tool supplies those fields. The gate has the same
shape everywhere: the hook's JSON on stdin (Claude Code's PostToolUse, Cursor's afterFileEdit, Gemini
CLI's AfterTool), the files it names scored like `--risk`, a one-line summary per file with the
companions the edit left untouched, and exit 2 when the total is over the threshold, which is what
every one of those hooks reads as "block". Files on the command line (pre-commit's way) print the
summary as plain text instead of the hook JSON."""
from __future__ import annotations

import json
import os

_PATH_KEYS = ("file_path", "filePath", "path", "notebook_path")
_LIST_KEYS = ("file_paths", "filePaths", "files", "paths")
_CONTAINERS = ("tool_input", "tool_response", "input", "output")


def paths_in(event, repo: str) -> list:
    """The files a hook event names, relative to `repo`, each once, in order: the path keys the
    agents use at the top level and under tool_input/tool_response. A path outside the repository is
    not this repository's risk and is left out; a relative path is taken as repository-relative."""
    if not isinstance(event, dict):
        return []
    found = []

    def take(value):
        if isinstance(value, str) and value:
            found.append(value)
        elif isinstance(value, list):
            for v in value:
                if isinstance(v, str) and v:
                    found.append(v)
                elif isinstance(v, dict):
                    for k in _PATH_KEYS:
                        if isinstance(v.get(k), str):
                            found.append(v[k])

    for holder in (event, *[event.get(c) for c in _CONTAINERS if isinstance(event.get(c), dict)]):
        for k in _PATH_KEYS:
            take(holder.get(k))
        for k in _LIST_KEYS:
            take(holder.get(k))
    root = os.path.realpath(repo)
    out = []
    for p in found:
        full = os.path.realpath(p if os.path.isabs(p) else os.path.join(root, p))
        if full == root or not full.startswith(root + os.sep):
            continue
        rel = os.path.relpath(full, root)
        if rel not in out:
            out.append(rel)
    return out


def read_event(stdin) -> dict:
    """The hook's JSON from stdin, or {} for nothing or for anything that is not JSON: garbage on
    stdin is not a reason to block an edit."""
    try:
        text = stdin.read() if stdin is not None else ""
    except (OSError, ValueError):
        return {}
    if not text or not text.strip():
        return {}
    try:
        event = json.loads(text)
    except ValueError:
        return {}
    return event if isinstance(event, dict) else {}


def summary(risk: dict, threshold=None) -> list:
    """One line per file, worst first, then the companions the change left untouched, then the total
    against the threshold when there is one."""
    lines = []
    for r in risk["files"]:
        if r.get("rank"):
            where = f"rank {r['rank']} of {risk.get('pool', '?')}" + (", on the watch list" if r.get("watched") else "")
            lines.append(f"{r['file']}: {r['score']:.1f}% of the repository's revisions × lines of code ({where}); " + "; ".join(r["reasons"]))
        else:
            lines.append(f"{r['file']}: not scored ({r['reason']})")
    gaps = risk.get("coupling_gaps") or []
    if gaps:
        from . import render
        lines.append(render.gaps_line(gaps))
    total = f"total {risk['total']:.1f}%"
    if threshold is not None:
        total += f", over the {threshold:g}% threshold" if risk["total"] > threshold else f", under the {threshold:g}% threshold"
    lines.append(total)
    return lines


def hook_output(event: dict, lines: list) -> str:
    """The JSON Claude Code reads back (hookSpecificOutput.additionalContext, a soft warning); Cursor
    and Gemini CLI ignore stdout and read the exit code, so the same document serves all three."""
    name = event.get("hook_event_name") or "PostToolUse"
    return json.dumps({"hookSpecificOutput": {"hookEventName": name, "additionalContext": "\n".join(lines)}})

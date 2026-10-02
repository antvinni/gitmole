"""The agent hook: `gitmole OUT_DIR --no-run --hook [--risk-threshold N] [-- FILE...]`, after Codacy's
argument for deterministic findings before inference and Zimmermann et al.'s co-change recommendations.

Deterministic findings should run before inference, so the model reasons over a short list rather
than rediscovering known issues. A linter says what is wrong in the diff; gitmole says what history
says about the files the diff touches, and no other tool supplies those fields. The hook has the same
shape everywhere: the hook's JSON on stdin (Claude Code's PostToolUse, Cursor's afterFileEdit, Gemini
CLI's AfterTool), the files it names scored like `--risk`, a one-line summary per file with the
companions the edit left untouched, and exit 0. Files on the command line (pre-commit's way) print the
summary as plain text instead of the hook JSON.

It never exits 2, which every one of those hooks reads as "block". Up to 0.42.0 it did, when the total was
over --risk-threshold; but the total is the touched files' share of the repository's revisions × lines of
code, a number no edit can lower: the revisions are already in the log. Lewis et al. (ICSE 2013) shipped a
flag of that kind at Google and saw no change in what developers did, because "there is nothing that can be
done by a team to immediately unflag a file". The only edits that did lower it were the ones that hide the
file from the count (split it, mark it linguist-generated), which make nothing safer. The coupling warning is
something an edit can clear, by touching the companion, but it is right a little more often than not (54% on
the held-out replay, docs/validation.md), so blocking on it would stop the agent wrongly about half the time.
So both are context; --risk-threshold with --hook only says whether the total is over N. `gitmole --risk BASE
--risk-threshold N` in CI still exits 3 over N: there it gates a whole change before review, not one edit."""
from __future__ import annotations

import json
import os
import subprocess

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
    """One line per file, worst first, ending with what imports it where the import graph can say, then the
    companions the change left untouched, then the total against the threshold when there is one."""
    from . import watch
    lines = []
    for r in risk["files"]:
        if r.get("rank"):
            where = f"rank {r['rank']} of {risk.get('pool', '?')}" + (", on the watch list" if r.get("watched") else "")
            line = f"{r['file']}: {r['score']:.1f}% of the repository's revisions × lines of code ({where}); " + "; ".join(r["reasons"])
        else:
            line = f"{r['file']}: {unscored_words(r)}"
        imported = watch.dependents_phrase(r.get("dependents"))
        lines.append(f"{line}; {imported}" if imported else line)
    gaps = risk.get("coupling_gaps") or []
    if gaps:
        from . import render
        lines.append(render.gaps_line(gaps))
    total = f"total {risk['total']:.1f}%"
    if threshold is not None:
        total += f", over the {threshold:g}% threshold" if risk["total"] > threshold else f", under the {threshold:g}% threshold"
    if risk["files"] and not any(r.get("rank") for r in risk["files"]):   # a 0 that was never counted is not a safe change
        total += "; none of these files is scored, so the total says nothing about this change"
    lines.append(total)
    return lines


def unscored_words(r: dict) -> str:
    """Why a file has no score. Documentation is out by its type, which says nothing about how often it
    changes or breaks, so the line says the type is not ranked rather than naming a reason that reads as
    "safe"; one of the most-changed documents also gets its revision count."""
    from . import filetypes, textfmt
    if r.get("reason") == "not a source type" and filetypes.is_doc_path(r["file"]):
        said = "not scored: documentation is not ranked"
        return said + (f"; changed {textfmt.times(r['revisions'])}, one of the most-changed documents" if r.get("revisions") else "")
    return f"not scored ({r['reason']})"


def incomplete_line(missing: str, out_dir: str) -> str:
    """Said when the run the hook reads lacks the log, the sizes or the change analysis: every file then
    scores 0, and a 0 that means "not counted" must not read as "safe"."""
    return f"scores incomplete: {missing} in the run {out_dir} holds, so every file here scores 0 whatever its history"


def hook_output(event: dict, lines: list) -> str:
    """The JSON Claude Code reads back (hookSpecificOutput.additionalContext, a soft warning); Cursor
    and Gemini CLI ignore stdout and read the exit code, so the same document serves all three."""
    name = event.get("hook_event_name") or "PostToolUse"
    return json.dumps({"hookSpecificOutput": {"hookEventName": name, "additionalContext": "\n".join(lines)}})


def setup_hint(out_dir: str) -> str:
    """What to say when the hook's output directory is not there: the one-time run it scores against. Said
    and passed (exit 0), not refused: every agent reads a hook's exit 2 as "block", so a missing directory
    would otherwise stop every edit with a message about arguments."""
    return (f"gitmole hook: no analysis in {out_dir}, so nothing was scored; run once in the repository: "
            f"gitmole . --out {out_dir}")


def behind(repo: str, commit) -> int | None:
    """How many commits HEAD of `repo` has that the analysed `commit` did not, or None when that cannot be
    said (no commit recorded, not a git repository, a commit this clone does not have)."""
    if not commit or not repo:
        return None
    try:
        proc = subprocess.run(["git", "rev-list", "--count", f"{commit}..HEAD"], cwd=repo, capture_output=True, text=True)
    except OSError:
        return None
    try:
        return int(proc.stdout.strip()) if proc.returncode == 0 else None
    except ValueError:
        return None


def stale_line(out_dir: str, repo: str, commit: str, gap: int) -> str:
    """The notice for an analysis older than the tree the agent edits. No threshold: the scores are the
    analysed commit's, and a file changed since has revisions the watch list has not counted, so any gap is
    said, with how large it is, and the reader decides when to refresh."""
    return (f"gitmole hook: the analysis in {out_dir} is of {commit[:12]}, {gap} commit{'s' if gap != 1 else ''} behind HEAD; "
            f"its scores leave those out; refresh it with: gitmole {repo} --out {out_dir}")

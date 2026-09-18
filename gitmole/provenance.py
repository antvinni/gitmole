"""Provenance: what the history declares about how its commits were made, and the agent configuration
the tree declares, read and never inferred.

Runs as a pipeline step, `python -m gitmole.provenance OUT_DIR`, from inside the repository, and
writes provenance.json:

- trailers: every trailer key and how many commits carry it; the co-authors who never author a commit
  here (a structural fact about the repository, no list of products); sign-offs by such identities,
  which the Linux kernel's policy on coding assistants forbids an agent to add.
- cohort: commits with an `Assisted-by` trailer or a never-authoring co-author, against the rest: how
  many were reverted (by git's own `Revert "subject"`), how many are fixes, and how many had a file
  changed again by another commit within two weeks. This repository against itself, with the share
  of commits the cohort covers beside it; no prior from elsewhere, since the best-controlled study
  found the spread between agents larger than the pooled difference.
- shape: neutral descriptors (commits landing in bursts, conventional-commit subjects, how many hours
  of the day commits come in). Every one has a benign cause, and none is labelled.
- agents: the agent instruction files by path convention (AGENTS.md, CLAUDE.md, GEMINI.md,
  .github/copilot-instructions.md) and how far behind HEAD each is, the hook files that declare
  guardrails, tracked personal settings, settings that turn approval prompts off, and MCP server
  declarations whose environment carries literal values rather than references. Values are never
  written."""
from __future__ import annotations

import bisect
import datetime as dt
import json
import os
import re
import subprocess
import sys
from collections import Counter

try:
    from . import filetypes, leaks
except ImportError:  # run as a script: the package directory is sys.path[0]
    import filetypes
    import leaks

SEP, END = "\x1f", "\x1e"
# a trailer key is hyphenated by convention (Co-authored-by, Signed-off-by, Change-Id); git's parser also
# accepts a URL or a line of prose that happens to end the message, and those are not trailers
_TRAILER_LINE = re.compile(r"^([A-Za-z][A-Za-z0-9]*(?:-[A-Za-z0-9]+)+):\s*(?!//)(.+)$")
_IDENT = re.compile(r"^\s*(?P<name>[^<]*?)\s*<(?P<email>[^>]*)>\s*$")
_CONVENTIONAL = re.compile(r"^(feat|fix|docs|style|refactor|perf|test|build|ci|chore|revert)(\([^)]*\))?!?: \S")
BURST_SIZE, BURST_SECONDS = 5, 600
RETOUCH_DAYS = 14


def read_commits(repo: str) -> list:
    """[{hash, time, author, email, subject, trailers: [(key, value)], files}] of HEAD's history, oldest
    first, through one git log: trailers by git's own parser, files from --name-only."""
    fmt = f"{END}%H{SEP}%at{SEP}%aN{SEP}%aE{SEP}%s{SEP}%(trailers:unfold,only){SEP}"
    out = subprocess.run([*filetypes.GIT, "log", "HEAD", "--use-mailmap", "--name-only", f"--format={fmt}"], cwd=repo,
                         capture_output=True, check=True).stdout.decode("utf-8", "replace")
    commits = []
    for chunk in out.split(END)[1:]:
        parts = chunk.split(SEP)
        if len(parts) < 7:
            continue
        h, at, name, email, subject, trailer_text, files = parts[:7]
        trailers = [(m.group(1), m.group(2).strip()) for m in (_TRAILER_LINE.match(l) for l in trailer_text.split("\n")) if m]
        commits.append({"hash": h, "time": int(at), "author": name, "email": email.lower(), "subject": subject,
                        "trailers": trailers, "files": [f for f in files.split("\n") if f.strip()]})
    commits.reverse()
    return commits


def _ident(value: str):
    m = _IDENT.match(value)
    return (m.group("name"), m.group("email").lower()) if m else None


def trailers(commits: list) -> dict:
    keys = Counter()
    authors = {c["email"] for c in commits} | {c["author"] for c in commits}
    co, signed = Counter(), Counter()
    names = {}
    for c in commits:
        for k in {k for k, _ in c["trailers"]}:
            keys[k] += 1
        for k, v in c["trailers"]:
            ident = _ident(v)
            if not ident:
                continue
            names.setdefault(ident[1], ident[0])
            if k.lower() == "co-authored-by":
                co[ident[1]] += 1
            elif k.lower() == "signed-off-by":
                signed[ident[1]] += 1
    never = {e for e in co if e not in authors and names[e] not in authors}
    listing = sorted(({"name": names[e], "email": e, "commits": co[e]} for e in never), key=lambda x: (-x["commits"], x["name"]))
    signoff = sorted(({"name": names[e], "email": e, "commits": signed[e]} for e in never if signed.get(e)), key=lambda x: (-x["commits"], x["name"]))
    return {"commits": len(commits), "keys": dict(sorted(keys.items(), key=lambda kv: (-kv[1], kv[0]))[:25]),
            "with_any": sum(1 for c in commits if c["trailers"]), "never_author": listing[:50], "signoff_by_co_author": signoff[:50]}


def cohort(commits: list, inventory: dict) -> dict:
    """The commits an `Assisted-by` trailer or a never-authoring co-author marks, against the rest."""
    marked_emails = {x["email"] for x in inventory["never_author"]}

    def marked(c):
        for k, v in c["trailers"]:
            if k.lower() == "assisted-by":
                return True
            ident = _ident(v)
            if k.lower() == "co-authored-by" and ident and ident[1] in marked_emails:
                return True
        return False

    reverted = {c["subject"][len('Revert "'):-1] for c in commits if c["subject"].startswith('Revert "') and c["subject"].endswith('"')}
    by_file = {}
    for i, c in enumerate(commits):
        for f in c["files"]:
            by_file.setdefault(f, []).append(i)
    stats = {True: Counter(), False: Counter()}
    for i, c in enumerate(commits):
        s = stats[marked(c)]
        s["commits"] += 1
        s["reverted"] += c["subject"] in reverted
        s["fixes"] += bool(re.match(r"^(fix|hotfix|bugfix)(\([^)]*\))?!?:", c["subject"], re.I) or re.search(r"\b(fix|fixes|fixed|bug)\b", c["subject"], re.I))
        again = False
        for f in c["files"]:   # the next commit to touch each file, by position: the list is in commit order
            k = bisect.bisect_right(by_file[f], i)
            if k < len(by_file[f]) and commits[by_file[f][k]]["time"] - c["time"] <= RETOUCH_DAYS * 86400:
                again = True
                break
        s["retouched"] += again
    total = len(commits)
    return {"definition": "an Assisted-by trailer, or a co-author who never authors a commit here",
            "share": round(stats[True]["commits"] / total, 3) if total else 0.0,
            "cohort": dict(stats[True]) or {"commits": 0}, "rest": dict(stats[False]) or {"commits": 0}}


def shape(commits: list) -> dict:
    """How commits arrive, as neutral numbers: the share landing in runs of five or more by one author
    within ten minutes of each other, the share with conventional-commit subjects, and how many hours
    of the day (in UTC) see commits."""
    burst = set()
    by_author = {}
    for i, c in enumerate(commits):
        by_author.setdefault(c["email"], []).append(i)
    for idx in by_author.values():
        run = [idx[0]]
        for a, b in zip(idx, idx[1:]):
            if commits[b]["time"] - commits[a]["time"] <= BURST_SECONDS:
                run.append(b)
            else:
                if len(run) >= BURST_SIZE:
                    burst.update(run)
                run = [b]
        if len(run) >= BURST_SIZE:
            burst.update(run)
    n = len(commits)
    hours = {dt.datetime.fromtimestamp(c["time"], dt.timezone.utc).hour for c in commits}
    return {"burst_share": round(len(burst) / n, 3) if n else 0.0,
            "conventional_share": round(sum(bool(_CONVENTIONAL.match(c["subject"])) for c in commits) / n, 3) if n else 0.0,
            "hours_used": len(hours)}


INSTRUCTIONS = ("AGENTS.md", "CLAUDE.md", "GEMINI.md", ".github/copilot-instructions.md")
GUARDRAILS = (".claude/settings.json", ".cursor/hooks.json")
MCP = (".mcp.json", ".cursor/mcp.json", ".vscode/mcp.json")
LOCAL = (".claude/settings.local.json",)
_REFERENCE = re.compile(r"^\$\{?[A-Za-z_][A-Za-z0-9_]*\}?$|^\$\{[^}]+\}$|^\{\{.*\}\}$")


def _json(repo: str, path: str):
    try:
        with open(os.path.join(repo, path), encoding="utf-8", errors="replace") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


def _literal_secret(value) -> bool:
    """A literal environment value that could be a credential: a string, not a ${VAR} reference, not a
    placeholder shape, and long enough to be a key (a short word is configuration)."""
    if not isinstance(value, str):
        return False
    v = value.strip()
    return len(v) >= 16 and not _REFERENCE.match(v) and not leaks.is_placeholder(v)


def agents(repo: str) -> dict:
    tracked = set(filetypes.git_paths(repo, "ls-files"))
    head_count = int(subprocess.run(["git", "rev-list", "--count", "HEAD"], cwd=repo, capture_output=True, text=True).stdout.strip() or 0)
    instructions = []
    for path in sorted(p for p in tracked if p.rsplit("/", 1)[-1] in ("AGENTS.md", "CLAUDE.md", "GEMINI.md") or p in INSTRUCTIONS):
        last = subprocess.run(["git", "log", "-1", "--format=%H%x1f%cs", "--", path], cwd=repo, capture_output=True, text=True).stdout.strip()
        if not last:
            continue
        sha, day = last.split("\x1f")
        behind = int(subprocess.run(["git", "rev-list", "--count", f"{sha}..HEAD"], cwd=repo, capture_output=True, text=True).stdout.strip() or 0)
        instructions.append({"file": path, "last": day, "commits_behind": behind})
    guard, disabled = [], []
    for path in GUARDRAILS:
        data = _json(repo, path) if path in tracked else None
        if not isinstance(data, dict):
            continue
        if data.get("hooks"):
            guard.append(path)
        perms = data.get("permissions") if isinstance(data.get("permissions"), dict) else {}
        if perms.get("defaultMode") == "bypassPermissions":
            disabled.append({"file": path, "setting": "permissions.defaultMode=bypassPermissions"})
        if data.get("skipDangerousModePermissionPrompt") is True:
            disabled.append({"file": path, "setting": "skipDangerousModePermissionPrompt=true"})
    mcp = []
    for path in MCP:
        data = _json(repo, path) if path in tracked else None
        if not isinstance(data, dict):
            continue
        servers = data.get("mcpServers") or data.get("servers") or {}
        if not isinstance(servers, dict):
            continue
        literal = [{"server": name, "key": key} for name, spec in sorted(servers.items()) if isinstance(spec, dict)
                   for key, value in sorted((spec.get("env") or {}).items()) if _literal_secret(value)]
        mcp.append({"file": path, "servers": len(servers), "literal_env": literal})
    return {"instructions": instructions, "head_commits": head_count, "guardrails": guard, "approval_disabled": disabled,
            "local_settings": sorted(p for p in tracked if p in LOCAL or p.endswith("/.claude/settings.local.json")), "mcp": mcp}


def main(argv=None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 1:
        print("usage: provenance.py OUT_DIR", file=sys.stderr)
        return 2
    repo = os.getcwd()
    try:
        commits = read_commits(repo)
    except subprocess.CalledProcessError as e:
        print(f"provenance.py: {(e.stderr or b'').decode('utf-8', 'replace').strip() or e}", file=sys.stderr)
        return 1
    inventory = trailers(commits)
    result = {"trailers": inventory, "cohort": cohort(commits, inventory), "shape": shape(commits), "agents": agents(repo)}
    with open(os.path.join(args[0], "provenance.json"), "w", encoding="utf-8") as fh:
        json.dump(result, fh)
    return 0


if __name__ == "__main__":
    sys.exit(main())

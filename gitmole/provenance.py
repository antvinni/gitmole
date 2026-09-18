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
- lines: the lines added to code files in the last year and the year before, with the share git's
  own moved-code detection marks as moved (`--color-moved`, blocks of twenty or more characters) and
  the share deleted again within two weeks, in the same file with the same text: GitClear's moved and
  churned lines, as a direction over this repository rather than a comparison with anyone else's.
  The same two numbers per cohort, and each cohort's watch-list hit rate: the share of its commits
  touching a file on the watch list's top fifteen.
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
from collections import Counter, deque

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
YEAR = 365 * 86400
WATCH_TOP = 15
# data that inflates line counts without being code (the same set the code-age pass leaves out)
DATA_EXCLUDES = [":(exclude,glob)**/*.json", ":(exclude,glob)**/*.lock", ":(exclude,glob)**/*.min.js", ":(exclude,glob)**/*.min.css",
                 ":(exclude,glob)**/*.svg", ":(exclude,glob)**/*.map", ":(exclude,glob)**/*.csv", ":(exclude,glob)**/*.snap"]
_COLORS = ["-c", "color.diff.new=green", "-c", "color.diff.newMoved=cyan", "-c", "color.diff.old=red", "-c", "color.diff.oldMoved=magenta",
           "-c", "color.diff.meta=normal", "-c", "color.diff.frag=normal", "-c", "color.diff.func=normal", "-c", "color.diff.context=normal",
           "-c", "color.diff.whitespace=normal", "-c", "color.diff.commit=normal"]
_ADDED, _MOVED, _DELETED, _DELETED_MOVED = "\x1b[32m+", "\x1b[36m+", "\x1b[31m-", "\x1b[35m-"
_ANSI = re.compile(r"\x1b\[[0-9;]*m")


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


def marker(inventory: dict):
    """The predicate that marks a commit: an `Assisted-by` trailer, or a co-author who never authors."""
    marked_emails = {x["email"] for x in inventory["never_author"]}

    def marked(c):
        for k, v in c["trailers"]:
            if k.lower() == "assisted-by":
                return True
            ident = _ident(v)
            if k.lower() == "co-authored-by" and ident and ident[1] in marked_emails:
                return True
        return False
    return marked


def cohort(commits: list, inventory: dict, watch_files=None) -> dict:
    """The commits an `Assisted-by` trailer or a never-authoring co-author marks, against the rest; with
    `watch_files`, how many of each touched a file on the watch list."""
    marked = marker(inventory)

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
        if watch_files:
            s["watch"] += any(f in watch_files for f in c["files"])
    total = len(commits)
    return {"definition": "an Assisted-by trailer, or a co-author who never authors a commit here",
            "share": round(stats[True]["commits"] / total, 3) if total else 0.0,
            "cohort": dict(stats[True]) or {"commits": 0}, "rest": dict(stats[False]) or {"commits": 0}}


def _code_path(path: str, generated: set, vendored) -> bool:
    return filetypes.matches(path, filetypes.DEFAULT) and path not in generated and not filetypes.is_vendored(path, vendored)


def lines(repo: str, end: int, marked_hashes: set, generated=frozenset(), vendored=()) -> dict:
    """Added, moved and churned lines in code files over the two years before `end` (a timestamp), from
    one `git log -p` with git's moved-code colouring. A line is churned when a later commit, within two
    weeks, deletes a line with the same text from the same file; blank lines and lines without three
    letters or digits (a lone brace) are not matched, since any brace would pair with any other."""
    start = end - 2 * YEAR
    argv = ["git", *_COLORS, "-c", "core.quotePath=false", "log", "HEAD", "--reverse", "--no-merges", "-p", "-U0", "-M", "--color=always",
            "--color-moved=blocks", "--color-moved-ws=allow-indentation-change", f"--since=@{start}", f"--until=@{end}",
            f"--format={END}%H{SEP}%at", "--", ".", *DATA_EXCLUDES]
    proc = subprocess.Popen(argv, cwd=repo, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    windows = {w: Counter() for w in ("last", "before")}
    groups = {True: Counter(), False: Counter()}
    pending = {}   # (path, text) -> [(time, window, marked)] of additions not yet churned
    order = deque()   # (time, key) in the order added, so what is past two weeks can be dropped and memory stays bounded
    t, window, is_marked, path, keep = 0, "last", False, None, False
    for raw in proc.stdout:
        line = raw.decode("utf-8", "replace").rstrip("\n")
        if line.startswith(END):
            h, _, at = line[1:].partition(SEP)
            t = int(at or 0)
            window = "last" if t > end - YEAR else "before"
            is_marked = h in marked_hashes
            windows[window]["commits"] += 1
            groups[is_marked]["commits"] += 1
            path = None
            while order and t - order[0][0] > RETOUCH_DAYS * 86400:
                old_t, key = order.popleft()
                adds = pending.get(key)
                if adds and adds[0][0] == old_t:
                    adds.pop(0)
                if not adds:
                    pending.pop(key, None)
            continue
        if line.startswith("diff --git "):
            plain = _ANSI.sub("", line)   # git ends even an uncoloured header with a reset
            path = filetypes.unquote(plain.rsplit(" b/", 1)[-1]) if " b/" in plain else None
            keep = bool(path) and _code_path(path, generated, vendored)
            continue
        if not keep:
            continue
        if line.startswith((_ADDED, _MOVED)):
            text = _ANSI.sub("", line)[1:].strip()
            moved = line.startswith(_MOVED)
            for c in (windows[window], groups[is_marked]):
                c["added"] += 1
                c["moved"] += moved
            if sum(ch.isalnum() for ch in text) >= 3:
                pending.setdefault((path, text), []).append((t, window, is_marked))
                order.append((t, (path, text)))
        elif line.startswith((_DELETED, _DELETED_MOVED)):
            text = _ANSI.sub("", line)[1:].strip()
            adds = pending.get((path, text))
            while adds and t - adds[0][0] > RETOUCH_DAYS * 86400:
                adds.pop(0)   # too old to count, and older than any later deletion will reach
            if adds and adds[0][0] < t:
                at_, w, m = adds.pop(0)
                windows[w]["churned"] += 1
                groups[m]["churned"] += 1
    proc.stdout.close()
    proc.wait()

    def shares(c):
        added = c.get("added", 0)
        return {"commits": c.get("commits", 0), "added": added, "moved": c.get("moved", 0), "churned": c.get("churned", 0),
                "moved_share": round(c.get("moved", 0) / added, 4) if added else None,
                "churn_share": round(c.get("churned", 0) / added, 4) if added else None}
    day = lambda ts: dt.datetime.fromtimestamp(ts, dt.timezone.utc).date().isoformat()   # noqa: E731
    return {"windows": [{"label": "last year", "from": day(end - YEAR), "to": day(end), **shares(windows["last"])},
                        {"label": "the year before", "from": day(start), "to": day(end - YEAR), **shares(windows["before"])}],
            "cohort": {"marked": shares(groups[True]), "rest": shares(groups[False])},
            "churn_days": RETOUCH_DAYS, "moved": "git --color-moved=blocks"}


def _watch_files(out_dir: str):
    """The watch list's top files, when the change analysis and scc have written their outputs; None
    otherwise, or when this runs as a script outside the package."""
    if not (os.path.exists(os.path.join(out_dir, "size.json")) and os.path.exists(os.path.join(out_dir, "maat-revisions.csv"))):
        return None
    try:
        from . import load, watch
    except ImportError:
        return None
    try:
        report = load.load_report(out_dir, nested=False)
    except load.Unreadable:
        return None
    return {r["file"] for r in watch.risks(report)[:WATCH_TOP]}


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
    watch_files = _watch_files(args[0])
    meta = {}
    try:
        with open(os.path.join(args[0], "meta.json"), encoding="utf-8") as fh:
            meta = json.load(fh)
    except (OSError, ValueError):
        pass
    marked = marker(inventory)
    result = {"trailers": inventory, "cohort": cohort(commits, inventory, watch_files), "shape": shape(commits), "agents": agents(repo)}
    if watch_files is not None:
        result["cohort"]["watch_top"] = WATCH_TOP
    if commits:
        result["lines"] = lines(repo, commits[-1]["time"], {c["hash"] for c in commits if marked(c)}, set(meta.get("generated") or []),
                                filetypes.vendor_dirs({"meta": meta}))
    with open(os.path.join(args[0], "provenance.json"), "w", encoding="utf-8") as fh:
        json.dump(result, fh)
    return 0


if __name__ == "__main__":
    sys.exit(main())

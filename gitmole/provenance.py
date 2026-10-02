"""Provenance: what the history declares about how its commits were made, and the agent configuration
the tree declares, read and never inferred.

Runs as a pipeline step, `python -m gitmole.provenance OUT_DIR`, from inside the repository, and
writes provenance.json:

- trailers: every trailer key and how many commits carry it; the co-authors who never author a commit
  here (a structural fact about the repository, no list of products); sign-offs by such identities,
  which the Linux kernel's policy on coding assistants forbids an agent to add.
- cohort: the declared commits, those with an `Assisted-by` trailer, a never-authoring co-author or a coding
  tool (identity.tools over meta.json) as co-author, against the rest, which is every commit that declares
  nothing and so includes any agent use nobody disclosed (never "humans"): how many were reverted (by git's
  own `Revert "subject"`, or its body line `This reverts commit <sha>`), how many are fixes, and how many had a file
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
  .github/copilot-instructions.md, subagents and skills under .claude/, .codex/ and .agents/; none under a
  template, fixture, example or test directory: is_instruction_file) and how far behind HEAD each is (a file that only points at another, by
  symlink, `@path` or a link, as far as the newest file it points at), the hook files that declare
  guardrails, tracked personal settings, settings that turn approval prompts off, and MCP server
  declarations whose environment carries literal values rather than references. Values are never
  written. Three more parts of the surface are told by shape and only listed, never judged: the hook
  commands any tracked JSON declares (a `hooks` key over an object with a `command`), each with its event
  and the tracked script it runs; the manifests in a root dot-directory whose name ends `-plugin`; and
  every `skills/<name>/SKILL.md` whose frontmatter names and describes it."""
from __future__ import annotations

import bisect
import datetime as dt
import json
import os
import re
import shlex
import subprocess
import sys
from collections import Counter, deque

try:
    from . import filetypes, identity, leaks, maat
except ImportError:  # run as a script: the package directory is sys.path[0]
    import filetypes
    import identity
    import leaks
    import maat

SEP, END = "\x1f", "\x1e"
# a trailer key is hyphenated by convention (Co-authored-by, Signed-off-by, Change-Id); git's parser also
# accepts a URL or a line of prose that happens to end the message, and those are not trailers
_TRAILER_LINE = re.compile(r"^([A-Za-z][A-Za-z0-9]*(?:-[A-Za-z0-9]+)+):\s*(?!//)(.+)$")
# an issue reference that happens to end a message ("PAP-10182: fixed the retry"): a project key in capitals, a
# hyphen and a number, Jira's shape and GitHub's autolink references'. git reads it as a trailer; a trailer key
# names a field (Signed-off-by, Change-Id), and no field's name ends in a bare number
_TICKET_KEY = re.compile(r"^[A-Z][A-Z0-9]*-\d+$")
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
    out = subprocess.run([*filetypes.GIT, *filetypes.RENAMES, "log", "HEAD", "--use-mailmap", "--name-only", f"--format={fmt}"], cwd=repo,
                         capture_output=True, check=True).stdout.decode("utf-8", "replace")
    commits = []
    for chunk in out.split(END)[1:]:
        parts = chunk.split(SEP)
        if len(parts) < 7:
            continue
        h, at, name, email, subject, trailer_text, files = parts[:7]
        trailers = [(m.group(1), m.group(2).strip()) for m in (_TRAILER_LINE.match(l) for l in trailer_text.split("\n"))
                    if m and not _TICKET_KEY.match(m.group(1))]
        commits.append({"hash": h, "time": int(at), "author": name, "email": email.lower(), "subject": subject,
                        "trailers": trailers, "files": [f for f in files.split("\n") if f.strip()]})
    commits.reverse()
    return commits


def _ident(value: str):
    m = _IDENT.match(value)
    return (m.group("name"), m.group("email").lower()) if m else None


def fold_keys(keys: dict) -> dict:
    """Trailer keys counted without regard to case, as git's own trailer matching is (Co-authored-by and
    Co-Authored-By are one trailer), each under its most common spelling, most used first; an issue reference
    (_TICKET_KEY) is not a trailer. Counts per spelling of one key are summed, which for an older run that
    counted spellings apart can count a commit carrying both twice."""
    groups = {}
    for k, n in keys.items():
        if not _TICKET_KEY.match(k):
            groups.setdefault(k.lower(), []).append((k, n))
    folded = [(min(g, key=lambda kv: (-kv[1], kv[0]))[0], sum(n for _, n in g)) for g in groups.values()]
    return dict(sorted(folded, key=lambda kv: (-kv[1], kv[0])))


def trailers(commits: list) -> dict:
    keys, spellings = Counter(), Counter()
    authors = {c["email"] for c in commits} | {c["author"] for c in commits}
    co, signed = Counter(), Counter()
    names = {}
    for c in commits:
        for k in {k.lower() for k, _ in c["trailers"]}:
            keys[k] += 1
        spellings.update(k for k, _ in c["trailers"])
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
    spelled = {}
    for k, n in sorted(spellings.items(), key=lambda kv: (-kv[1], kv[0])):
        spelled.setdefault(k.lower(), k)   # the most common spelling of each key names it
    return {"commits": len(commits), "keys": dict(sorted(((spelled[k], n) for k, n in keys.items()), key=lambda kv: (-kv[1], kv[0]))[:25]),
            "with_any": sum(1 for c in commits if c["trailers"]), "never_author": listing[:50], "signoff_by_co_author": signoff[:50]}


def tool_names(meta: dict) -> frozenset:
    """The coding tools of the run (identity.tools over meta.json's rows), and every name that merged into one."""
    names = identity.tools(meta.get("identities") or [])
    aliases = meta.get("aliases") or {}
    return frozenset(names | {a for a, to in aliases.items() if to in names})


def marker(inventory: dict, tools=frozenset()):
    """The predicate that marks a commit: an `Assisted-by` trailer, or a co-author who never authors or who is a
    coding tool (`tools`, tool_names). A tool that authored a commit or two is still one: paperclip's agent,
    credited on 2,052 commits, authored 2, and the never-authoring test alone left all of them unmarked."""
    marked_emails = {x["email"] for x in inventory["never_author"]}

    def marked(c):
        for k, v in c["trailers"]:
            if k.lower() == "assisted-by":
                return True
            ident = _ident(v)
            if k.lower() == "co-authored-by" and ident and (ident[1] in marked_emails or ident[0] in tools):
                return True
        return False
    return marked


def cohort(commits: list, inventory: dict, watch_files=None, tools=frozenset(), reverts: dict = None) -> dict:
    """The commits that declare a coding tool (an `Assisted-by` trailer, a never-authoring co-author or a coding
    tool as co-author: marker), against the rest. The rest is every commit that declares nothing, which includes
    any agent use nobody disclosed: it is not a group of people. With `watch_files`, how many of each touched a
    file on the watch list. A commit is reverted when a later one is git's `Revert "<its subject>"`, or names its
    hash in git's body line (`reverts`, maat.read_reverts), which survives a rewritten subject."""
    marked = marker(inventory, tools)

    reverted = {c["subject"][len('Revert "'):-1] for c in commits if c["subject"].startswith('Revert "') and c["subject"].endswith('"')}
    named = {r.lower() for shas in (reverts or {}).values() for r in shas}
    lengths = sorted({len(r) for r in named})
    by_file = {}
    for i, c in enumerate(commits):
        for f in c["files"]:
            by_file.setdefault(f, []).append(i)
    stats = {True: Counter(), False: Counter()}
    for i, c in enumerate(commits):
        s = stats[marked(c)]
        s["commits"] += 1
        s["reverted"] += c["subject"] in reverted or any(c["hash"][:n] in named for n in lengths)
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
    return {"definition": "an Assisted-by trailer, or a co-author who never authors a commit here or is a coding tool",
            "share": round(stats[True]["commits"] / total, 3) if total else 0.0,
            "cohort": dict(stats[True]) or {"commits": 0}, "rest": dict(stats[False]) or {"commits": 0}}


def _code_path(path: str, generated: set, vendored, types=filetypes.DEFAULT) -> bool:
    return filetypes.matches(path, types) and path not in generated and not filetypes.is_vendored(path, vendored)


def lines(repo: str, end: int, marked_hashes: set, generated=frozenset(), vendored=(), types=filetypes.DEFAULT) -> dict:
    """Added, moved and churned lines in code files over the two years before `end` (a timestamp), from
    one `git log -p` with git's moved-code colouring. A line is churned when a later commit, within two
    weeks, deletes a line with the same text from the same file; blank lines and lines without three
    letters or digits (a lone brace) are not matched, since any brace would pair with any other."""
    start = end - 2 * YEAR
    argv = ["git", *_COLORS, "-c", "core.quotePath=false", *filetypes.RENAMES, "log", "HEAD", "--reverse", "--no-merges", "-p", "-U0", "-M", "--color=always",
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
            keep = bool(path) and _code_path(path, generated, vendored, types)
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
INSTRUCTION_NAMES = ("AGENTS.md", "CLAUDE.md", "GEMINI.md")   # read by the agents wherever they sit in the tree
# the files the agents load as instructions by their place in the tree: Claude Code's subagents and skills, Codex's
# agents, and the shared .agents/skills convention, in any directory a tool can be started from
AGENT_FILES = re.compile(r"(^|/)(?:(?P<subagent>\.claude/agents/[^/]+\.md|\.codex/agents/[^/]+)|(?P<skill>\.claude/skills/[^/]+/SKILL\.md|\.agents/skills/[^/]+/SKILL\.md))$")


def instruction_kind(path: str):
    """"skill" or "subagent" for a file an agent loads when a task calls for it (AGENT_FILES), None for one it
    reads at the start of every session (AGENTS.md and the like), which is what describes the tree."""
    m = AGENT_FILES.search(path)
    return None if not m else ("subagent" if m.group("subagent") else "skill")
# where an instruction file is the product's data, not the repository's instructions: a template a generator
# copies out, a fixture or example a test or a reader loads (filetypes' test and sample conventions)
_SHIPPED = re.compile(r"(^|/)(templates?|__fixtures__)/")


def is_instruction_file(path: str) -> bool:
    """An agent instruction file the repository gives its own agents: AGENTS.md, CLAUDE.md or GEMINI.md anywhere,
    .github/copilot-instructions.md, or a subagent or skill by the tools' layouts (AGENT_FILES); never one under
    a template, fixture, example or test directory, which a product ships or a test loads (paperclip's nineteen
    persona AGENTS.md)."""
    if not (path.rsplit("/", 1)[-1] in INSTRUCTION_NAMES or path in INSTRUCTIONS or AGENT_FILES.search(path)):
        return False
    return not (_SHIPPED.search(path) or filetypes.is_test_path(path) or filetypes.is_sample_path(path))
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


_POINTER_REF = re.compile(r"@(\S+)|\]\(([^)\s]+)\)|([\w.-]+(?:/[\w.-]+)*\.\w+)")
POINTER_LINES = 3   # a pointer says where the instructions are, in a line or three; more is instructions


def _resolve(ref: str, base: str, tracked: set):
    """A reference in an agent file (`@AGENTS.md`, `./CLAUDE.md#setup`, `docs/agents.md`) as the tracked file it
    names, relative to the file's directory first and then to the root; None when it names no tracked file."""
    ref = ref.split("#", 1)[0].strip("`'\"<>(),;:").rstrip(".")   # a sentence's full stop is not the name's
    if not ref or "://" in ref or ref.startswith("~"):
        return None
    for cand in (os.path.normpath(os.path.join(base, ref)), os.path.normpath(ref.lstrip("/"))):
        if cand in tracked:
            return cand
    return None


def pointer_targets(repo: str, path: str, tracked: set) -> list:
    """The tracked files an agent instruction file only points at, or [] when it holds instructions of its own.
    A pointer, by shape: a symlink, or a file that after its headings and blank lines has at most POINTER_LINES
    lines, each naming a tracked file by `@path` (Claude Code's import), a Markdown link or a bare path
    (brew's and prometheus's CLAUDE.md is `@AGENTS.md`; hindsight's AGENTS.md is "See [CLAUDE.md](./CLAUDE.md)")."""
    full, base = os.path.join(repo, path), os.path.dirname(path)
    if os.path.islink(full):
        target = _resolve(os.readlink(full), base, tracked)
        return [target] if target and target != path else []
    try:
        with open(full, encoding="utf-8", errors="replace") as fh:
            text = fh.read(4096)
    except OSError:
        return []
    lines = [l.strip() for l in text.splitlines() if l.strip() and not l.lstrip().startswith("#")]
    if not lines or len(lines) > POINTER_LINES or len(text) >= 4096:
        return []
    targets = []
    for line in lines:
        named = [t for m in _POINTER_REF.finditer(line) for t in [_resolve(next(g for g in m.groups() if g), base, tracked)] if t and t != path]
        if not named:
            return []
        targets += [t for t in dict.fromkeys(named) if t not in targets]
    return targets


CAP = 50   # rows kept per inventory list: the count says how many there were
COMMAND_SHOWN = 200   # characters of a hook command kept
HOOK_FILE_BYTES = 1_000_000   # a hook declaration is a small file; a larger JSON is data
# a skill by the layout the tools share, wherever the repository keeps it: skills/<name>/SKILL.md whose YAML
# frontmatter gives a `name:` and a `description:` (what a tool reads to decide when to load it)
SKILL_FILE = re.compile(r"(^|/)skills/[^/]+/SKILL\.md$")
_FRONTMATTER = re.compile(r"\A---[ \t]*\r?\n(.*?)\r?\n---[ \t]*(?:\r?\n|\Z)", re.S)
# a manifest in a root dot-directory named <tool>-plugin: where a tool that installs the repository as a plugin
# looks for what it provides
PLUGIN_MANIFEST = re.compile(r"^\.[^/]+-plugin/[^/]+\.(?:json|ya?ml|toml)$")
_VAR_PREFIX = re.compile(r"^(?:\$\{[A-Za-z_][A-Za-z0-9_]*\}|\$[A-Za-z_][A-Za-z0-9_]*|%[A-Za-z_][A-Za-z0-9_]*%)[/\\]")
_EXEC_LINE = re.compile(r"^\s*exec\s+(.+)$", re.M)
_ASSIGNMENT = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]*=)(\S+)")


def _aside(path: str) -> bool:
    """Where an agent file is a product's data or a test's input, not the repository's own surface."""
    return bool(_SHIPPED.search(path)) or "node_modules/" in path or filetypes.is_test_path(path) or filetypes.is_sample_path(path) \
        or filetypes.is_vendor_path(path)


def is_declared_skill(repo: str, path: str) -> bool:
    """Whether a skills/<name>/SKILL.md opens with frontmatter that has both `name:` and `description:`, and its
    skills/ directory is not under a template, fixture, example, test or vendored one. The directory under skills/
    is the skill's name, not a path convention: skills/test-driven-development/ is a skill about tests, not a test."""
    if _aside(path[:SKILL_FILE.search(path).start(0)] + "/SKILL.md"):
        return False
    try:
        with open(os.path.join(repo, path), encoding="utf-8", errors="replace") as fh:
            front = _FRONTMATTER.match(fh.read(8192))
    except OSError:
        return False
    return bool(front) and all(re.search(rf"^{key}:[ \t]*\S", front.group(1), re.M) for key in ("name", "description"))


def hook_commands(doc) -> list:
    """(event, command) for every object with a `command` (a string, or a list of strings) below a `hooks` key
    of a parsed JSON document. The event is the object's own `event` when it has one, else the nearest key
    above it under `hooks` that is not itself `hooks`:

        {"hooks": {"SessionStart": [{"matcher": "startup", "hooks": [{"type": "command", "command": "x"}]}]}}
        {"hooks": {"sessionStart": [{"command": "x"}]}}
        {"contributes": {"hooks": [{"event": "SessionStart", "command": ["sh", "x"]}]}}

    all give ("SessionStart" or "sessionStart", x). An MCP server's `command` is under no `hooks` and is not one."""
    out = []

    def walk(node, event, inside):
        if isinstance(node, list):
            for item in node:
                walk(item, event, inside)
        elif isinstance(node, dict):
            command = node.get("command")
            if inside and (isinstance(command, str) or (isinstance(command, list) and command and all(isinstance(c, str) for c in command))):
                out.append((node["event"] if isinstance(node.get("event"), str) else event, command))
            for key, value in node.items():
                if key == "hooks":
                    walk(value, event, True)
                else:
                    walk(value, key if inside else event, inside)
    walk(doc, None, False)
    return out


def _tracked_path(token: str, bases: list, tracked: set):
    """A command's word as the tracked file it names, or None: a `${VAR}/`, `$VAR/` or `./` prefix is stripped (the
    variable is where the tool put the repository), and what is left is tried against each base directory. A bare
    word (`node`, `test`) is a program, not a path, unless it had such a prefix, holds a slash or ends in an extension."""
    word = token.strip("\"'")
    path = _VAR_PREFIX.sub("", word)
    while path.startswith("./"):
        path = path[2:]
    if not path or not (path != word or "/" in path or re.search(r"\.\w+$", path)):
        return None
    for base in bases:
        cand = os.path.normpath(os.path.join(base, path))
        if cand in tracked:
            return cand
    return None


def _words(command) -> list:
    if isinstance(command, list):
        return command
    try:
        return shlex.split(command)
    except ValueError:
        return command.split()


def _is_script(repo: str, path: str) -> bool:
    """A tracked file that runs: git records it executable (mode 100755, which a checkout on a filesystem without
    the bit still has in the index), or it opens with `#!`."""
    mode = subprocess.run([*filetypes.GIT, "ls-files", "-s", "--", path], cwd=repo, capture_output=True, text=True).stdout[:6]
    if mode == "100755":
        return True
    try:
        with open(os.path.join(repo, path), "rb") as fh:
            return fh.read(2) == b"#!"
    except OSError:
        return False


def hook_script(repo: str, command, file: str, tracked: set) -> dict:
    """What a hook command points at in the tree, from the root and then from the declaring file's directory:

    - {"script"}: the first word naming a tracked file that runs: the command's own first word, or a file git
      records executable or that opens with `#!` (_is_script);
    - {"runs"}: the tracked file that script hands over to. It has an `exec` line, and either that line names the
      file or one of the command's later words does, read from the script's own directory (a wrapper called as
      `run-hook.cmd session-start` that ends `exec bash "${DIR}/${NAME}"`). One hop only, and only through
      `exec`: what a script sources or calls is not followed;
    - {"names"}: with no script, the first tracked file the command names (`cat .claude/instructions.md`,
      `node scripts/check.js`): a file it reads or passes to a program, which is not said to run."""
    words = _words(command)
    bases = ["", os.path.dirname(file)]
    named = [(i, t) for i, w in enumerate(words) for t in [_tracked_path(w, bases, tracked)] if t]
    at, script = next(((i, t) for i, t in named if i == 0 or _is_script(repo, t)), (None, None))
    if not script:
        return {"names": named[0][1]} if named else {}
    out = {"script": script}
    try:
        with open(os.path.join(repo, script), encoding="utf-8", errors="replace") as fh:
            execs = _EXEC_LINE.findall(fh.read(65536))
    except OSError:
        execs = []
    if execs:
        here = [os.path.dirname(script), ""]
        handed = [t for line in execs for w in _words(line) for t in [_tracked_path(w, here, tracked)] if t]
        # a later word of the command is the script's argument: a file beside the script when it names one
        handed += [t for w in words[at + 1:] for t in [_tracked_path("./" + w.strip("\"'"), here[:1], tracked)] if t]
        runs = next((t for t in handed if t != script), None)
        if runs:
            out["runs"] = runs
    return out


def _shown(command) -> str:
    """A hook command as one line, cut to COMMAND_SHOWN characters, with the value of any NAME=value word that
    could be a credential (_literal_secret) replaced: the inventory names commands, never values."""
    text = command if isinstance(command, str) else " ".join(command)
    text = _ASSIGNMENT.sub(lambda m: m.group(1) + "***" if _literal_secret(m.group(2).strip("\"'")) else m.group(0), " ".join(text.split()))
    return text if len(text) <= COMMAND_SHOWN else text[:COMMAND_SHOWN - 1] + "…"


def hooks(repo: str, tracked: set) -> list:
    """Every hook command a tracked JSON file declares (hook_commands), as {file, event, command} with what it
    points at in the tree (hook_script: script and runs, or names):
    one `git grep` names the files holding both words, and only those are parsed. YAML is not read (no parser is
    a dependency), nor a file under a template, fixture, example, test or vendored directory."""
    proc = subprocess.run([*filetypes.GIT, "grep", "-l", "-z", "-I", "--all-match", "-F", "-e", '"hooks"', "-e", '"command"', "--", "*.json"],
                          cwd=repo, capture_output=True)
    rows = []
    for path in sorted(p for p in proc.stdout.decode("utf-8", "surrogateescape").split("\0") if p in tracked and not _aside(p)):
        try:
            if os.path.getsize(os.path.join(repo, path)) > HOOK_FILE_BYTES:
                continue
        except OSError:
            continue
        for event, command in hook_commands(_json(repo, path)):
            rows.append({"file": path, "event": event, "command": _shown(command), **hook_script(repo, command, path, tracked)})
    return rows


def _last_change(repo: str, path: str):
    """(commit, day, commit time) of the last commit that touched `path`, or None."""
    last = subprocess.run(["git", *filetypes.RENAMES, "log", "-1", "--format=%H%x1f%cs%x1f%ct", "--", path], cwd=repo, capture_output=True, text=True).stdout.strip()
    if not last:
        return None
    sha, day, when = last.split("\x1f")
    return sha, day, int(when)


def agents(repo: str) -> dict:
    tracked = set(filetypes.git_paths(repo, "ls-files"))
    head_count = int(subprocess.run(["git", "rev-list", "--count", "HEAD"], cwd=repo, capture_output=True, text=True).stdout.strip() or 0)
    instructions = []
    for path in sorted(p for p in tracked if is_instruction_file(p)):
        targets = pointer_targets(repo, path, tracked)
        # a pointer's instructions are its targets': it is as current as the newest of them
        dated = [c for c in (_last_change(repo, t) for t in (targets or [path])) if c]
        if not dated:
            continue
        sha, day, _ = max(dated, key=lambda c: c[2])
        behind = int(subprocess.run(["git", "rev-list", "--count", f"{sha}..HEAD"], cwd=repo, capture_output=True, text=True).stdout.strip() or 0)
        kind = instruction_kind(path)
        instructions.append(dict({"file": path, "last": day, "commits_behind": behind}, **({"points_to": targets} if targets else {}),
                                 **({"kind": kind} if kind else {})))
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
    declared = hooks(repo, tracked)
    skills = sorted(p for p in tracked if SKILL_FILE.search(p) and is_declared_skill(repo, p))
    manifests = sorted(p for p in tracked if PLUGIN_MANIFEST.match(p))
    return {"instructions": instructions, "head_commits": head_count, "guardrails": guard, "approval_disabled": disabled,
            "local_settings": sorted(p for p in tracked if p in LOCAL or p.endswith("/.claude/settings.local.json")), "mcp": mcp,
            "hooks": declared[:CAP], "hooks_count": len(declared), "plugin_manifests": manifests[:CAP], "plugin_manifests_count": len(manifests),
            "skills": {"count": len(skills), "files": skills[:CAP]}}


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
    tools = tool_names(meta)
    marked = marker(inventory, tools)
    reverts = maat.read_reverts(os.path.join(args[0], "reverts.txt"))
    result = {"trailers": inventory, "cohort": cohort(commits, inventory, watch_files, tools, reverts), "shape": shape(commits), "agents": agents(repo)}
    if watch_files is not None:
        result["cohort"]["watch_top"] = WATCH_TOP
    if commits:
        result["lines"] = lines(repo, commits[-1]["time"], {c["hash"] for c in commits if marked(c)}, set(meta.get("generated") or []),
                                filetypes.vendor_dirs({"meta": meta}), filetypes.with_scripts(filetypes.DEFAULT, meta.get("scripts") or {}))
    with open(os.path.join(args[0], "provenance.json"), "w", encoding="utf-8") as fh:
        json.dump(result, fh)
    return 0


if __name__ == "__main__":
    sys.exit(main())

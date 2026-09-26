"""Ask the person who ran gitmole whether its findings were worth acting on, and write their answers.

Every label in measure/labels.jsonl carries `"labeller": "claude"`: the rules an agent wrote are graded
by the same agent, and no number in the history rests on a judgement from outside the project. This asks
the one population that can answer, on the one occasion they have the report in front of them.

gitmole does not send anything. The answers go to a file the person can read, and the run prints the two
ways to send it: one `gh` command, or a browser. "Nothing is uploaded, nothing phones home" stays true of
gitmole itself, which is why the flag exists rather than an endpoint.

What the file may hold is a closed list (PAYLOAD_KEYS): the rule's id and severity, the answer, gitmole's
version, and three coarse facts about the repository (its main language, and buckets for file count and
commit count). A finding's own words name paths, authors and values, so no statement, path or name is
written, and a test holds the file to that list.

One keystroke answers both axes a label carries. "Worth acting on" is true and actionable; "no" is true
and not actionable, the shape of the nine rules the labels already found inert; "wrong" is not true.

When it asks, which is rarely: only with a terminal on both ends, only from a plain run (any export, gate
or hook flag is a script's run, and portfolio mode is not one repository), never where the environment
declares itself CI, and never with GITMOLE_NO_FEEDBACK set. It asks once on a machine. A decline is
remembered for good; someone who answered is asked again after ANSWERED_AGAIN_DAYS, since their answers
are the ones worth having.
"""
from __future__ import annotations

import datetime as dt
import json
import os

PAYLOAD_KEYS = frozenset({"gitmole", "asked", "answers", "language", "files", "commits"})
ANSWER_KEYS = frozenset({"rule", "severity", "true", "actionable"})
LIMIT = 5                     # findings asked about, so the whole prompt is five keystrokes
ANSWERED_AGAIN_DAYS = 90      # someone who answered is asked again after this, a decline never is
CI_VARS = ("CI", "GITHUB_ACTIONS", "GITLAB_CI", "BUILDKITE", "TEAMCITY_VERSION")
OFF_VAR = "GITMOLE_NO_FEEDBACK"
# the flags that mean a script, not a person, is reading: an export, a gate, the agent hook
SCRIPT_FLAGS = ("json", "markdown", "sarif", "sbom", "fail_on", "risk", "hook", "compare")
ISSUE_URL = "https://github.com/antvinni/gitmole/issues/new?labels=feedback"
FILE_NAME = "gitmole-feedback.json"

INVITATION = "Were these findings worth acting on? 5 questions, nothing leaves your machine [y/N] "
PROMPT = "  {n}/{total} {title} — worth acting on? [y]es / [n]o / [w]rong / [s]kip / [q]uit "
ANSWERS = {"y": (True, True), "n": (True, False), "w": (False, False)}


def bucket(n: int, edges=(100, 1_000, 10_000, 100_000)) -> str:
    """A count as the band it falls in, so a repository cannot be recognised by its size."""
    low = 0
    for edge in edges:
        if n < edge:
            return f"{low}-{edge}"
        low = edge
    return f"{low}+"


def state_path() -> str | None:
    """Where the one fact about this machine lives: whether it has been asked, and what came of it.
    Beside the structure cache, so GITMOLE_CACHE=off turns this off as well."""
    from .structure import cache_root
    root = cache_root()
    return os.path.join(os.path.dirname(root), "feedback.json") if root else None


def read_state(path: str) -> dict:
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {}


def write_state(path: str, state: dict) -> None:
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(state, fh, sort_keys=True)
    except OSError:
        pass      # a cache that cannot be written means it asks again another day, which is harmless


def due(state: dict, today: str) -> bool:
    """Whether this machine is due to be asked: once, then only if the last time was answered."""
    if state.get("declined"):
        return False
    answered = state.get("answered")
    if not answered:
        return not state.get("asked")
    return today >= (dt.date.fromisoformat(answered) + dt.timedelta(days=ANSWERED_AGAIN_DAYS)).isoformat()


def unattended(args, env=None) -> bool:
    """A pipeline or a script is running gitmole, whatever the terminals say: a CI variable is set (Buildkite
    runs its jobs on a pseudo-terminal), or a flag means a machine reads the output. Every question gitmole
    asks checks this first, since a prompt in a pipeline hangs a build."""
    env = os.environ if env is None else env
    return any(env.get(name) for name in CI_VARS) or any(getattr(args, flag, None) for flag in SCRIPT_FLAGS)


def on_terminal(out=None) -> bool:
    """Someone is there to answer: stdin and the stream the question is written to are both terminals. The
    streams' own isatty, not rich's is_terminal, which FORCE_COLOR turns on for a file; and a process started
    with fd 0 closed has sys.stdin None."""
    import sys
    out = sys.stdout if out is None else out
    try:
        return bool(sys.stdin is not None and sys.stdin.isatty() and out.isatty())
    except (AttributeError, ValueError, OSError):   # a stream without isatty, or a closed one
        return False


def should_ask(args, state: dict, today: str, env=None, isatty=None) -> bool:
    """Whether to ask at the end of this run. Any doubt is a no: a prompt in a pipeline hangs a build."""
    env = os.environ if env is None else env
    if env.get(OFF_VAR):
        return False
    if getattr(args, "feedback", False):
        return True      # asked for explicitly, so none of the rest applies but the kill switch
    if unattended(args, env):
        return False
    if getattr(args, "kind", "") == "owner" or getattr(args, "no_run", False):
        return False
    if isatty is None:
        isatty = on_terminal()
    return bool(isatty) and due(state, today)


def spelled_out(found: list) -> list:
    """The findings the default report gave an entry of their own, worst first: what the reader just saw.
    A summarised or unjudged finding was one line among several, so nobody can answer for it."""
    from . import findings as rules
    shown = [f for f in found if not f.get("summary") and not f.get("unjudged")]
    return sorted(shown, key=lambda f: rules.SEVERITIES.index(f["severity"]))[:LIMIT]


def ask(found: list, out, prompt, invitation=INVITATION) -> list:
    """Ask about each finding and return the answers, or [] when the person declines or quits.
    `prompt` reads a line; `out` writes one. Neither is stdin or stdout here, so a test can drive it."""
    questions = spelled_out(found)
    if not questions:
        return []
    if (prompt(invitation) or "").strip().lower() not in ("y", "yes"):
        return []
    answers = []
    for i, finding in enumerate(questions, 1):
        reply = (prompt(PROMPT.format(n=i, total=len(questions), title=finding["title"])) or "").strip().lower()[:1]
        if reply == "q":
            break
        if reply not in ANSWERS:
            continue          # skip, and anything unrecognised is a skip rather than a guess
        true, actionable = ANSWERS[reply]
        answers.append({"rule": (finding.get("rule") or {}).get("id"), "severity": finding["severity"],
                        "true": true, "actionable": actionable})
    out("")
    return answers


def payload(answers: list, report: dict, today: str, version: str) -> dict:
    """The file's whole content: the answers, the version, and three coarse facts. Nothing else, ever.
    The facts come from scc's language totals and the history's commit count, as bands."""
    meta = report.get("meta") or {}
    size = report.get("size") or {}
    languages = sorted((size.get("languages") or []), key=lambda r: -(r.get("code") or 0))
    return {"gitmole": version, "asked": today, "answers": answers,
            "language": (languages[0].get("name") if languages else "") or "",
            "files": bucket(size.get("total_files") or 0),
            "commits": bucket(meta.get("commits") or 0)}


def write(path: str, data: dict) -> str:
    body = {k: v for k, v in data.items() if k in PAYLOAD_KEYS}
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(body, fh, indent=2, sort_keys=True)
        fh.write("\n")
    return path


def how_to_send(path: str, version: str) -> list:
    """The two ways to send it. gitmole never does: the person reads the file and chooses."""
    return [f"Answers written to {path} — no paths, names or values.",
            f'Send them: gh issue create --repo antvinni/gitmole --label feedback --title "feedback from {version}" --body-file {path}',
            f"or paste the file into {ISSUE_URL}"]

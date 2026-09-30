"""Small text helpers that make the report easier to read: path elision, finding grouping, tallies."""
from __future__ import annotations

import re

ELLIPSIS = "…"


def shorten_path(path: str, max_len: int) -> str:
    """Elide middle directories so the path fits, keeping the file name whole:
    a/b/c/d/e.py -> a/…/d/e.py -> …/d/e.py -> …/e.py."""
    if len(path) <= max_len or "/" not in path:
        return path
    parts = path.split("/")
    candidates = [f"{parts[0]}/{ELLIPSIS}/" + "/".join(parts[-2:])] if len(parts) > 3 else []
    if len(parts) > 2:
        candidates.append(f"{ELLIPSIS}/" + "/".join(parts[-2:]))
    candidates.append(f"{ELLIPSIS}/{parts[-1]}")
    for c in candidates:
        if len(c) <= max_len:
            return c
    return candidates[-1]


def cut_middle(text: str, width: int) -> str:
    """`text` in at most `width` characters, the middle given up for an ellipsis so both ends stay
    readable. Words are kept whole where there are words ("Claude Opus 4.8 (1M context) (15%)" ->
    "Claude Opus 4.8 … (15%)"), and a word never ends the head with a bracket it does not close; a single
    token keeps its last segment after a dot, slash or colon whole when that leaves room for a head
    ("dub_transcribe_stream._gen_body" -> "dub_transcri…._gen_body")."""
    if len(text) <= width:
        return text
    if width < 3:
        return text[:max(width - 1, 0)] + ELLIPSIS if width else ""
    words = text.split(" ")
    if len(words) > 1:
        head, tail = [], [words[-1]]
        for w in words[:-1]:
            if len(" ".join(head + [w, ELLIPSIS] + tail)) > width:
                break
            head.append(w)
        while head and head[-1].count("(") > head[-1].count(")"):
            head.pop()
        if head and len(" ".join(head + [ELLIPSIS] + tail)) <= width:
            return " ".join(head + [ELLIPSIS] + tail)
    keep = width - 1
    tail_len = keep // 2
    seg = max(text.rfind("."), text.rfind("/"), text.rfind(":"))
    if seg > 0 and 4 <= keep - (len(text) - seg):
        tail_len = len(text) - seg
    return text[:keep - tail_len] + ELLIPSIS + text[len(text) - tail_len:]


ANONYMOUS = "<anonymous>"   # what the report calls a function that has no name of its own


def nameless(name: str) -> bool:
    """A function name that is not a name: empty, lizard's "(anonymous)", the start line gitmole labels a
    nameless function with (`const rows = (['tts'] as const).map((family) => {`), or the structure step's
    "(anonymous at line 12)". Told by shape: whitespace, an opening bracket that is not an empty `()`
    (`operator()` is a name), `=>` or `{`."""
    return not name or bool(re.search(r"\s|=>|\{", name)) or "(" in name.replace("()", "")


def cut(name: str, cap: int) -> str:
    """`name`, unchanged if it fits in `cap` characters, else cut to exactly `cap` ending in the ellipsis."""
    return name if len(name) <= cap else name[:cap - 1] + ELLIPSIS


def times(n: int) -> str:
    """How often something happened, in words for the small numbers: once, twice, 3 times."""
    return {1: "once", 2: "twice"}.get(n, f"{n} times")


def join_and(items: list) -> str:
    """"a"; "a and b"; "a, b and c": an English list, the last item joined with "and" instead of a comma.
    An empty list is "", not an IndexError."""
    return "" if not items else items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1]


_ADVICE_VERBS = ("Add ", "Set ", "Rotate ", "Pair ", "Rerun ", "Expect ", "Consider ", "Use ", "Review ", "Merge ", "Split ", "Move ", "Extract ")
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+(?=[A-Z])")


def split_advice(detail: str):
    """(statement, advice): the last sentence is advice when it is an instruction and there is
    more than one sentence. The statement loses its trailing period only when advice was split off."""
    sentences = _SENTENCE_END.split(detail.strip())
    if len(sentences) < 2 or not sentences[-1].startswith(_ADVICE_VERBS):
        return detail.strip(), None
    statement = " ".join(sentences[:-1]).rstrip(".")
    return statement, sentences[-1]


def _statement_and_advice(f: dict):
    """A finding's facts and its next step. Rules say which part is the advice; for a finding
    without that field (older JSON, a hand-made dict) the last sentence is taken when it is an
    instruction."""
    detail = f["detail"].strip()
    advice = f.get("advice")
    if advice:
        statement = detail[:-len(advice)].rstrip() if detail.endswith(advice) else detail
        return statement.rstrip("."), advice
    return split_advice(detail)


def group_findings(findings: list) -> list:
    """Merge findings that share a title into one entry with an item list and the distinct next
    steps its items carry, in first-seen order. Order: by severity, then first appearance."""
    order = {"critical": 0, "warning": 1, "info": 2}
    groups, index = [], {}
    for f in findings:
        statement, advice = _statement_and_advice(f)
        key = f["title"]
        if key not in index:
            index[key] = len(groups)
            groups.append({"severity": f["severity"], "title": key, "items": [], "advice": []})
        g = groups[index[key]]
        g["items"].append(statement)
        if advice and advice not in g["advice"]:
            g["advice"].append(advice)
        if order[f["severity"]] < order[g["severity"]]:
            g["severity"] = f["severity"]
    for g in groups:
        if len(g["items"]) > 1:
            g["title"] = f"{g['title']} ({len(g['items'])})"
    groups.sort(key=lambda g: order[g["severity"]])
    return groups


def tally(findings: list) -> str:
    counts = {"critical": 0, "warning": 0, "info": 0}
    for f in findings:
        counts[f["severity"]] += 1
    parts = []
    if counts["critical"]:
        parts.append(f"{counts['critical']} critical")
    if counts["warning"]:
        parts.append(f"{counts['warning']} warning" + ("s" if counts["warning"] != 1 else ""))
    if counts["info"]:
        parts.append(f"{counts['info']} note" + ("s" if counts["info"] != 1 else ""))
    return ", ".join(parts) if parts else "nothing flagged"


def count(n: int, word: str, plural: str = None) -> str:
    """'1 file', '3 files', '2 directories': a number with its noun."""
    return f"{n:,} {word if n == 1 else (plural or word + 's')}"

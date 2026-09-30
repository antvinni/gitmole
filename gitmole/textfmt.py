"""Small text helpers that make the report easier to read: path elision, finding grouping, tallies."""
from __future__ import annotations

import re

ELLIPSIS = "…"


def shorten_path(path: str, max_len: int, others=()) -> str:
    """Elide middle directories so the path fits, keeping the file name whole:
    a/b/c/d/e.py -> a/…/d/e.py -> …/d/e.py -> a/…/e.py -> …/e.py: the parent directory says
    more about a file than the top one does (`…/BlogListPage/index.tsx`). A directory (`a/b/c/`) keeps its own
    name the same way (`…/c/`), never the empty name after its last slash; a name that alone is too
    long is returned whole, for the caller to cut (cut_path).

    `others` are the other paths a reader could take the short form for (the table's other rows, the tracked
    files with the same name): a form that fits one of them too is passed over, and more directories are kept
    from the end until one fits only this path (`ui/…/IssueProperties.tsx` is two files in a tree that also has
    a one-line re-export of that name; `…/issue-properties/IssueProperties.tsx` is one). With none that does,
    the path is returned whole. A `:line` after the path (a nameless function's place) is not part of it."""
    if len(path) <= max_len:
        return path
    slash = "/" if path.endswith("/") else ""
    parts = path.rstrip("/").split("/")
    if len(parts) < 2:
        return path
    parts[-1] += slash
    candidates = [f"{parts[0]}/{ELLIPSIS}/" + "/".join(parts[-2:])] if len(parts) > 3 else []
    if len(parts) > 2:
        candidates += [f"{ELLIPSIS}/" + "/".join(parts[-2:]), f"{parts[0]}/{ELLIPSIS}/{parts[-1]}"]
    candidates.append(f"{ELLIPSIS}/{parts[-1]}")
    if others:
        candidates += [f"{ELLIPSIS}/" + "/".join(parts[-k:]) for k in range(3, len(parts))]
        candidates = [c for c in candidates if not _names_another(c, path, others)]
        if not candidates:
            return path
    for c in candidates:
        if len(c) <= max_len:
            return c
    return min(candidates, key=len)


LINE_SUFFIX = re.compile(r":\d+$")


def _names_another(short: str, path: str, others) -> bool:
    """Whether the elided `short` form of `path` also reads as one of `others`: the same end after the
    ellipsis, and the same top directory before it when the form keeps one."""
    path, short = LINE_SUFFIX.sub("", path), LINE_SUFFIX.sub("", short)
    head, _, tail = short.partition(f"{ELLIPSIS}/")
    head = head.rstrip("/")
    for other in others:
        other = LINE_SUFFIX.sub("", other)
        if other != path and other.endswith("/" + tail) and len(other) > len(tail) + 1 and (not head or other.startswith(head + "/")):
            if not head or len(other) > len(head) + len(tail) + 2:   # the ellipsis stands for one directory at least
                return True
    return False


def cut_path(path: str, width: int, others=()) -> str:
    """`path` in at most `width` characters: directories elided first (shorten_path, which keeps it apart from
    `others`), then the name cut in its middle. A directory keeps its trailing slash (`hindsi…-slim/`), so it
    still reads as one. A form that keeps the path apart but does not fit has its parent directory cut
    instead (`…/iss…/IssueProperties.tsx`), when what is left of it is still no other path's; failing that it
    gives way to the usual form: a file name cut to tell two files apart tells neither."""
    short = shorten_path(path, width, others)
    if len(short) > width and others:
        short = _squeeze_parent(path, width, others) or shorten_path(path, width)
    path = short
    if len(path) <= width:
        return path
    if path.endswith("/") and width > 1:
        return cut_middle(path[:-1], width - 1) + "/"
    return cut_middle(path, width)


def _squeeze_parent(path: str, width: int, others) -> str | None:
    """`…/<start of the parent directory>…/name` in exactly `width` characters, or None when no start of the
    parent that fits sets the path apart from every other of `others` with the same name."""
    line = LINE_SUFFIX.search(path)
    tail = line.group(0) if line else ""
    parts = path[:len(path) - len(tail)].split("/")
    if len(parts) < 3 or not parts[-1] or path.endswith("/"):
        return None
    parent, name = parts[-2], parts[-1] + tail
    keep = width - len(name) - 4   # the two ellipses and the two slashes
    if not 1 <= keep < len(parent):
        return None
    head = parent[:keep]
    for other in others:
        other = LINE_SUFFIX.sub("", other)
        bits = other.split("/")
        if other != path[:len(path) - len(tail)] and len(bits) > 1 and bits[-1] == parts[-1] and bits[-2].startswith(head):
            return None
    return f"{ELLIPSIS}/{head}{ELLIPSIS}/{name}"


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

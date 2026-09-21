"""Does a finding's text agree with its own numbers? The part of the report no other measure looks at.

Everything else here scores what the rules decide: the ranking, how many findings, how long the report
is, whether a finding was acted on. None of it reads the sentence a person actually gets, so a finding
can be true, useful and unreadable and score exactly the same. That is not hypothetical: react's one
critical finding said `facebook-access-token in (unreachable blob 00db21063ea1) (); facebook-access-token
in (unreachable blob 00db21063ea1) ()`, and every number in the 0.33.0 record was content with it.

This checks only what the text can be held to on its own, so there is nothing to tune and no threshold
to sweep: a count of one does not take a plural, a list that joined nothing does not leave its
punctuation behind, and one entry is not printed twice. A complaint is a defect, not a score - the
number to want is zero.

Two shapes are advisory and counted apart, because they are judgements rather than errors: a count over
one followed by what looks like a singular is mostly `23 of 78` and units, and the `(s)` spelling is one
decision about six rules, not six defects.

    python -m gitmole.measure claims [--version 0.34.0]

The checks were written against the 0.33.0 and 0.34.0 rounds, 242 findings over 20 repositories each,
and two false positives were fixed before this landed: a Go function named `errg.Go(func() error {` and a
commit subject quoting `super()` both hold empty parentheses honestly, so those only count where prose
joined an empty list, after a space.
"""
from __future__ import annotations

import collections
import re

# What joining an empty list into a sentence leaves behind.
EMPTY = [
    ("empty parentheses", re.compile(r"(?:^|(?<=\s))\(\)")),
    ("list opens with a separator", re.compile(r"\(\s*[,;]")),
    ("list ends with a separator", re.compile(r"[,;]\s*\)")),
    ("space before a separator", re.compile(r"\s[,;]")),
    ("nothing left to name", re.compile(r"\band 0 (?:more|other)\b")),
    ("space before a full stop", re.compile(r"\s\.(?:\s|$)")),
    ("double space", re.compile(r"\S {2,}\S")),
]

COUNT_NOUN = re.compile(r"\b(\d[\d,]*)\s+([A-Za-z][\w.+-]*)")
MALFORMED = re.compile(r"[A-Za-z]*sss[A-Za-z]*")     # "IPv4 addresss", from appending -s to a sibilant
# singulars that end in s, which the plural check must not mistake for plurals
SINGULAR_S = {"analysis", "always", "bss", "class", "cross", "does", "has", "https", "is", "its", "less",
              "loss", "miss", "pass", "plus", "process", "status", "this", "versus", "was"}
# words that sit between a count and the noun it governs
BETWEEN = {"and", "at", "different", "distinct", "empty", "from", "in", "more", "of", "on", "or", "other",
           "possible", "prior", "recent", "separate", "source", "to", "unreachable", "vulnerable"}


def _counted(text: str):
    """(count, the word it governs, the span as written) for each count in the text."""
    for m in COUNT_NOUN.finditer(text):
        n = int(m.group(1).replace(",", ""))
        for word in text[m.end(1):].split()[:3]:
            w = word.strip(".,;:()").lower()
            if w and w not in BETWEEN:
                yield n, w, m.group(0)
                break


def complaints(finding: dict) -> list:
    """[(kind, the words around it)] for this finding, empty when its text holds together."""
    text = finding.get("detail") or ""
    out = [(kind, text[max(0, m.start() - 40):m.end() + 40])
           for kind, pattern in EMPTY for m in [pattern.search(text)] if m]
    # "1 area(s)" is the singular here; the spelling itself is advisory, not a defect
    for n, word, span in _counted(text.replace("(s)", "")):
        if n == 1 and word.endswith("s") and not word.endswith("ss") and word not in SINGULAR_S:
            out.append(("one takes a plural", span))
    # any word, not only the one a count governs: "2 IPv4 addresss" is governed by "IPv4"
    out += [("malformed plural", m.group(0)) for m in [MALFORMED.search(text)] if m]
    out += [("the same entry twice", item) for item in _repeats(_entries(finding))]
    return out


def _entries(finding: dict) -> list:
    """The "; "-joined entries of a statement's list, without the lead-in that introduces it or the
    punctuation that ends it, so the first entry can be compared with the rest."""
    text = finding.get("detail") or ""
    statement = text.rsplit(finding.get("advice") or "\0", 1)[0]
    listed = statement.split(": ", 1)[-1]
    return [i.strip().rstrip(".") for i in listed.split("; ")]


def _repeats(items: list) -> list:
    return [i for i, n in collections.Counter(i for i in items if len(i) > 20).items() if n > 1]


def advisory(finding: dict) -> list:
    """Shapes worth knowing about that are judgements, not defects, and so are never counted as one."""
    text = finding.get("detail") or ""
    out = [("many takes a singular", span) for n, word, span in _counted(text)
           if n > 1 and word.isalpha() and len(word) > 3 and not word.endswith("s")]
    if "(s)" in text:
        out.append(("the (s) spelling", re.search(r".{0,30}\(s\).{0,20}", text).group(0)))
    return out


def over(found: list) -> dict:
    """{checked, clean, complaints, advisory} for one report's findings. `complaints` names the rule and
    the kind, not the whole sentence: the record is read as a diff, and a statement changes every run."""
    dirty, kinds, advice = 0, [], 0
    for f in found:
        rule = (f.get("rule") or {}).get("id") or ""
        against = complaints(f)
        dirty += bool(against)
        kinds += [{"rule": rule, "kind": kind} for kind, _ in against]
        advice += len(advisory(f))
    return {"checked": len(found), "clean": len(found) - dirty,
            "complaints": sorted(kinds, key=lambda k: (k["rule"], k["kind"])), "advisory": advice}

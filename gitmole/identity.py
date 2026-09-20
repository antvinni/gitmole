"""Merge git identities that belong to the same person."""
from __future__ import annotations

import re


_BOT_NAME = re.compile(r"\bbot\b|\bci\b|deploy|automation|releaser|release-bot", re.I)   # "Deploy from CI", "Release Bot", "hugoreleaser"


def is_bot(name: str, email: str = "") -> bool:
    """A commit author that is a service, not a person: GitHub's *[bot] suffix on the name or the
    mailbox, or a name that says bot, CI, deploy or automation. No product names: a service that
    declares nothing is a person until an alias of it declares otherwise (see bot_names)."""
    n, local = name.strip().lower(), email.strip().lower().split("@")[0]
    if n.endswith("[bot]") or local.endswith("[bot]"):
        return True
    return bool(_BOT_NAME.search(name))


def bot_names(identities: list) -> set:
    """The names that belong to bots, declaration included: an identity that merges with one that
    is a bot (github-actions <github-actions@github.com> beside github-actions[bot]) is the same
    account, and the [bot] suffix on one variant speaks for all of them."""
    out = set()
    for m in merge(identities):
        variants = [m, *m.get("aliases", [])]
        if any(is_bot(v["name"], v["email"]) for v in variants):
            out |= {v["name"] for v in variants}
    return out


def _tokens(name: str) -> set:
    return {t for t in re.split(r"[^a-z0-9]+", name.lower()) if len(t) >= 3}


def _words(name: str) -> list:
    return [w for w in re.split(r"[^a-z0-9]+", name.lower()) if w]


def shared_words(identities: list) -> frozenset:
    """The words that the full names of two people in this history hold (David in David Smith and David
    Sanders): on its own such a word could be either of them, so a bare David under another email joins
    neither, and two bare Davids stay two. Two spellings of one name (Tom Tromey, Author: Tom Tromey)
    share two tokens and are one person, so they do not make Tromey ambiguous. The repository's own names
    decide, not a list of common first names."""
    holders = {}
    for name in {_plain(i["name"]) for i in identities}:
        words = _words(name)
        if len(words) >= 2:
            for w in set(words):
                holders.setdefault(w, []).append(_tokens(name))
    return frozenset(w for w, names in holders.items()
                     if any(len(a & b) < 2 for i, a in enumerate(names) for b in names[i + 1:]))


def _plain(name: str) -> str:
    return " ".join(name.lower().split())


def _distinctive(token: str, shared: frozenset) -> bool:
    """A word that names one person on its own: five letters or more and in no two full names here."""
    return len(token) >= 5 and token not in shared


def _given(name: str) -> bool:
    """One word written the way a given name is written, a capital and then lower case (Jack, George):
    a person who signed with a first name, where KaKa, junegunn and tromey are handles someone chose."""
    name = name.strip()
    return len(name) >= 2 and name.isalpha() and name[0].isupper() and name[1:].islower()


def same_person(a: dict, b: dict, shared: frozenset = frozenset()) -> bool:
    """Same email; two shared name tokens; the same name spelled identically (a handle such as KaKa
    under three emails), unless that name is one word that two full names here share or that is written
    as a given name; or a one-word handle that is one distinctive word of the other's fuller name
    (junegunn and Junegunn Choi), a given name excepted. `shared` is shared_words over the whole history,
    which merge passes. A bare first name under another email is left apart: flink's three Jacks are
    three people, and nothing in the name says which of them a fuller name is."""
    if a["email"].lower() == b["email"].lower():
        return True
    ta, tb = _tokens(a["name"]), _tokens(b["name"])
    if len(ta & tb) >= 2:
        return True
    na, nb = _plain(a["name"]), _plain(b["name"])
    if na and na == nb and (len(_words(na)) >= 2 or (na not in shared and not _given(a["name"]) and not _given(b["name"]))):
        return True
    for x, handle, full in ((a, na, tb), (b, nb, ta)):
        if " " not in handle and handle in full and len(full) >= 2 and _distinctive(handle, shared) and not _given(x["name"]):
            return True
    # RobinMalfait and Robin Malfait: the full name run together, six letters or more so it is not anyone
    sa, sb = _squash(a["name"]), _squash(b["name"])
    if sa and sa == sb and len(sa) >= 6 and (len(ta) >= 2 or len(tb) >= 2):
        return True
    # nlohmann and Niels Lohmann: an initial plus a distinctive surname
    for handle, full in ((na, nb), (nb, na)):
        words = full.split()
        if " " not in handle and len(words) >= 2 and handle == words[0][0] + words[-1] and _distinctive(words[-1], shared):
            return True
    return False


def _squash(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.lower())


def merge(identities: list) -> list:
    """Group identities by shared name tokens or email. Each row keeps the most-committed
    variant's name and email, sums the commits, and lists the other variants as aliases.

    Grouping is transitive: an identity that matches two groups joins them into one, so
    "Hayden <h@noreply>" and "hay-kot <h@pm.me>" end up together once "hay-kot <h@noreply>"
    shows up to link them. Without that the same person appears twice."""
    shared = shared_words(identities)
    groups = []
    for i in identities:
        matched = [g for g in groups if any(same_person(i, j, shared) for j in g)]
        if not matched:
            groups.append([i])
            continue
        first = matched[0]
        first.append(i)
        for other in matched[1:]:
            first.extend(other)
            groups.remove(other)
    merged = []
    for g in groups:
        g = sorted(g, key=lambda x: -x["commits"])
        head = g[0]
        merged.append({
            "name": head["name"],
            "email": head["email"],
            "commits": sum(x["commits"] for x in g),
            "aliases": [{"name": x["name"], "email": x["email"], "commits": x["commits"]} for x in g[1:]],
        })
    merged.sort(key=lambda m: (-m["commits"], m["name"]))
    return merged


def canonical_names(merged: list) -> dict:
    """alias name -> merged name, including the merged names themselves."""
    out = {}
    for m in merged:
        out[m["name"]] = m["name"]
        for a in m.get("aliases", []):
            out[a["name"]] = m["name"]
    return out

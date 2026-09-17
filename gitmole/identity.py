"""Merge git identities that belong to the same person."""
from __future__ import annotations

import re


_BOT_WORDS = ("dependabot", "renovate", "github-actions", "github actions")


def is_bot(name: str, email: str = "") -> bool:
    """A commit author that is a service, not a person: GitHub's *[bot] suffix, or one of the
    common automation names in the name or the mailbox."""
    n, local = name.strip().lower(), email.strip().lower().split("@")[0]
    if n.endswith("[bot]") or local.endswith("[bot]"):
        return True
    return any(w in n for w in _BOT_WORDS) or any(w in local for w in _BOT_WORDS) or email.strip().lower() == "actions@github.com"


def _tokens(name: str) -> set:
    return {t for t in re.split(r"[^a-z0-9]+", name.lower()) if len(t) >= 3}


# A bare first name under two emails may be two people; anything else spelled identically is one.
_COMMON_FIRST_NAMES = {
    "adam", "alex", "alexander", "andrew", "andy", "ann", "anna", "ben", "bob", "chris", "dan", "daniel", "dave", "david", "ed",
    "eric", "frank", "george", "jack", "james", "jan", "jean", "jim", "joe", "john", "jon", "josh", "kevin", "lee", "li", "luke",
    "mark", "martin", "matt", "max", "michael", "mike", "nick", "paul", "pete", "peter", "phil", "rob", "robert", "ryan", "sam",
    "scott", "steve", "tim", "tom", "tony", "will",
}


def _plain(name: str) -> str:
    return " ".join(name.lower().split())


def same_person(a: dict, b: dict) -> bool:
    """Same email, two shared name tokens, or the same name spelled identically (a handle such as
    KaKa under three emails), unless that name is a bare common first name."""
    if a["email"].lower() == b["email"].lower() or len(_tokens(a["name"]) & _tokens(b["name"])) >= 2:
        return True
    name = _plain(a["name"])
    return bool(name) and name == _plain(b["name"]) and name not in _COMMON_FIRST_NAMES


def merge(identities: list) -> list:
    """Group identities by shared name tokens or email. Each row keeps the most-committed
    variant's name and email, sums the commits, and lists the other variants as aliases.

    Grouping is transitive: an identity that matches two groups joins them into one, so
    "Hayden <h@noreply>" and "hay-kot <h@pm.me>" end up together once "hay-kot <h@noreply>"
    shows up to link them. Without that the same person appears twice."""
    groups = []
    for i in identities:
        matched = [g for g in groups if any(same_person(i, j) for j in g)]
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

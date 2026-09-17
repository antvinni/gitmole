"""Merge git identities that belong to the same person."""
from __future__ import annotations

import re


_BOT_WORDS = ("dependabot", "renovate", "github-actions", "github actions", "copilot", "cursor agent", "cursor-agent", "cursoragent")
_BOT_NAME = re.compile(r"\bbot\b|\bci\b|deploy|automation", re.I)   # "Deploy from CI", "Release Bot", "Homebrew Automation"


def is_bot(name: str, email: str = "") -> bool:
    """A commit author that is a service, not a person: GitHub's *[bot] suffix, one of the common
    automation names in the name or the mailbox, or a name that says bot, CI, deploy or automation."""
    n, local = name.strip().lower(), email.strip().lower().split("@")[0]
    if n.endswith("[bot]") or local.endswith("[bot]"):
        return True
    return (any(w in n for w in _BOT_WORDS) or any(w in local for w in _BOT_WORDS) or email.strip().lower() == "actions@github.com"
            or bool(_BOT_NAME.search(name)))


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


def _distinctive(token: str) -> bool:
    """A word that names one person on its own: five letters or more and not a common first name."""
    return len(token) >= 5 and token not in _COMMON_FIRST_NAMES


def same_person(a: dict, b: dict) -> bool:
    """Same email; two shared name tokens; the same name spelled identically (a handle such as KaKa
    under three emails), unless that name is a bare common first name; or a one-word handle that is
    one distinctive word of the other's fuller name (junegunn and Junegunn Choi)."""
    if a["email"].lower() == b["email"].lower():
        return True
    ta, tb = _tokens(a["name"]), _tokens(b["name"])
    if len(ta & tb) >= 2:
        return True
    na, nb = _plain(a["name"]), _plain(b["name"])
    if na and na == nb and na not in _COMMON_FIRST_NAMES:
        return True
    for handle, full in ((na, tb), (nb, ta)):
        if " " not in handle and handle in full and len(full) >= 2 and _distinctive(handle):
            return True
    # RobinMalfait and Robin Malfait: the full name run together, six letters or more so it is not anyone
    sa, sb = _squash(a["name"]), _squash(b["name"])
    if sa and sa == sb and len(sa) >= 6 and (len(ta) >= 2 or len(tb) >= 2):
        return True
    # nlohmann and Niels Lohmann: an initial plus a distinctive surname
    for handle, full in ((na, nb), (nb, na)):
        words = full.split()
        if " " not in handle and len(words) >= 2 and handle == words[0][0] + words[-1] and _distinctive(words[-1]):
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

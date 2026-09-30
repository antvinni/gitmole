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


_NO_REPLY = re.compile(r"(?:do[-_.]?not[-_.]?reply|no[-_.]?reply)", re.I)


def shared_mailbox(email: str) -> bool:
    """An address that names no one: empty (a Co-authored-by trailer with no <...>), or a bare no-reply
    mailbox (noreply@, no-reply@, donotreply@), which a service gives every account it commits for. Two
    names under it are two identities unless the names themselves match. GitHub's per-account
    <id>+<login>@users.noreply.github.com has the account in its local part and still merges."""
    local = email.strip().lower().rpartition("@")[0] if "@" in email else email.strip().lower()
    return not local or bool(_NO_REPLY.fullmatch(local))


def same_person(a: dict, b: dict, shared: frozenset = frozenset()) -> bool:
    """Same email, unless it is a shared_mailbox; two shared name tokens; the same name spelled identically (a handle such as KaKa
    under three emails), unless that name is one word that two full names here share or that is written
    as a given name; or a one-word handle that is one distinctive word of the other's fuller name
    (junegunn and Junegunn Choi), a given name excepted, and a handle that is the fuller name's first word only
    when an address ties them too (_linked). `shared` is shared_words over the whole history,
    which merge passes. A bare first name under another email is left apart: flink's three Jacks are
    three people, and nothing in the name says which of them a fuller name is."""
    if a["email"].lower() == b["email"].lower() and not shared_mailbox(a["email"]):
        return True
    ta, tb = _tokens(a["name"]), _tokens(b["name"])
    if len(ta & tb) >= 2:
        return True
    na, nb = _plain(a["name"]), _plain(b["name"])
    if na and na == nb and (len(_words(na)) >= 2 or (na not in shared and not _given(a["name"]) and not _given(b["name"]))):
        return True
    for x, y, handle, full in ((a, b, na, tb), (b, a, nb, ta)):
        if (" " not in handle and handle in full and len(full) >= 2 and _distinctive(handle, shared) and not _given(x["name"])
                and (_words(y["name"])[0] != handle or _linked(x, y, handle))):
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


def _local_words(email: str) -> set:
    return {w for w in _words(email.rpartition("@")[0]) if len(w) >= 3} if not shared_mailbox(email) else set()


def _linked(handle_id: dict, full_id: dict, handle: str) -> bool:
    """An address ties a one-word handle to the fuller name whose first word it is: the fuller name's own
    mailbox is the handle (junegunn and Junegunn Choi <junegunn.c@…>), or the handle's mailbox holds another
    word of the fuller name. A first name however it is written, lower case included, is anyone's: hindsight's
    co-author "andrew <andrew.neeser@…>" had been merged into Andrew Barnes <bortstheboat@…> on it alone."""
    if handle in _local_words(full_id["email"]):
        return True
    return bool((_tokens(full_id["name"]) - {handle}) & _local_words(handle_id["email"]))


def _squash(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.lower())


def _keys(i: dict) -> set:
    """Every value same_person can match two identities on: two identities that share none of these
    cannot be the same person, so merge compares only identities that share one. The email; each name
    token (two shared tokens, and a one-word handle that is a token of the other's name); the name as
    written; the name run together; and initial-plus-surname, from a full name and from a handle."""
    plain = _plain(i["name"])
    keys = {("email", i["email"].lower()), ("plain", plain), ("squash", _squash(i["name"]))}
    keys |= {("token", t) for t in _tokens(i["name"])}
    words = plain.split()
    if len(words) >= 2:
        keys.add(("initial", words[0][0] + words[-1]))
    elif plain:
        keys.add(("initial", plain))
    return keys


def merge(identities: list) -> list:
    """Group identities by shared name tokens or email. Each row keeps the most-committed
    variant's name and email, sums the commits, and lists the other variants as aliases.

    Grouping is transitive: an identity that matches two groups joins them into one, so
    "Hayden <h@noreply>" and "hay-kot <h@pm.me>" end up together once "hay-kot <h@noreply>"
    shows up to link them. Without that the same person appears twice.

    Each identity is compared only with the earlier ones that share a key with it (_keys), not with
    every member of every group: django's 5,000 identities were 20 million comparisons. The groups,
    their order and their members' order are what comparing every pair gives."""
    shared = shared_words(identities)
    groups, group_of, members, by_key = [], {}, {}, {}   # members: id(group) -> the indices it holds
    for n, i in enumerate(identities):
        keys = _keys(i)
        seen = sorted({m for k in keys for m in by_key.get(k, ())})
        hits = {id(group_of[m]) for m in seen if same_person(i, identities[m], shared)}
        matched = [g for g in groups if id(g) in hits]
        for k in keys:
            by_key.setdefault(k, []).append(n)
        if not matched:
            groups.append([i])
            group_of[n], members[id(groups[-1])] = groups[-1], [n]
            continue
        first = matched[0]
        first.append(i)
        group_of[n] = first
        members[id(first)].append(n)
        for other in matched[1:]:
            first.extend(other)
            groups.remove(other)
            for m in members.pop(id(other)):
                group_of[m] = first
                members[id(first)].append(m)
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


def row_label(row: dict) -> str:
    """An identity row as `Name <email>`, the way the code-age pass labels the lines it blames (blame.label):
    the key of whatever is counted per identity rather than per display name."""
    return f"{row['name']} <{row.get('email') or ''}>"


def canonical_names(merged: list) -> dict:
    """alias name -> merged name, including the merged names themselves."""
    out = {}
    for m in merged:
        out[m["name"]] = m["name"]
        for a in m.get("aliases", []):
            out[a["name"]] = m["name"]
    return out


NO_REPLY_MAILBOX = re.compile(r"^(?:no-?reply|donotreply|do-not-reply)@", re.I)   # a bare no-reply mailbox; a per-user `id+login@users.noreply…` is not one


TRAILER_SHARE = 0.9   # a row at a bare no-reply mailbox credited by trailers for at least nine commits in ten is a tool


def tools(identities: list) -> set:
    """The names of the identities that are a coding tool rather than a person, by shape alone. Two shapes:

    - one of two or more differently named identities on one bare no-reply mailbox (noreply@, no-reply@,
      donotreply@), as an assistant that signs each model version with its own name and the vendor's one
      address does, or a product whose agents all commit under the product's one address;
    - an identity whose only addresses are bare no-reply mailboxes (or empty) and that is credited by
      Co-authored-by trailers for at least TRAILER_SHARE of its commits: a person commits their own work, and
      an assistant is named in the trailer of the person who commits. The cut is one order of magnitude,
      authored at most one commit in ten, fixed before looking at any repository's rows, not swept: it
      separates "never or almost never authors" from "authors", and nothing between the two is a shape.

    A per-account `id+login@users.noreply…` is a person's address, and so is any address naming someone:
    someone credited only by Co-authored-by trailers on such an address is a person, as most of them are
    (django's 71, redis's 63). One name alone on a bare no-reply address that authors its commits is a
    person too. `identities` are the run's merged rows (meta.json). The measurement harness's consistency
    check reads this same definition, so its agent_owner and the report agree.

    Tool-ness belongs to an address, not to a merged row: a row that authored commits and holds an address
    of its own (neither empty nor a bare no-reply mailbox) is a person, whatever else was merged into it.
    hindsight's TuftyBruno authored a commit under his own per-account address and credited himself in a
    trailer under the vendor's shared mailbox; the same spelled name merged the two, and the one shared
    alias made the whole row a tool. The report's tables key people by name, so such a person also keeps
    every row carrying their name out of the tools. Only such a person does: a row that authored nothing
    under an address of its own says nothing about who the name is. paperclip's product agent,
    "Paperclip <noreply@…>", credited on 2,052 commits, was vetoed in 0.41.0 by two stray trailer-only
    rows of the same name on other addresses."""
    shared = {}
    for i in identities:
        for email in {i.get("email") or ""} | {a.get("email") or "" for a in i.get("aliases") or []}:
            if NO_REPLY_MAILBOX.match(email):
                shared.setdefault(email.lower(), set()).add(i.get("name"))
    tool, person = set(), set()
    for i in identities:
        emails = {(i.get("email") or "").lower()} | {(a.get("email") or "").lower() for a in i.get("aliases") or []}
        if bool(i.get("authored")) and any(not shared_mailbox(e) for e in emails):
            person.add(i.get("name"))
            continue
        commits = i.get("commits") or 0
        credited = commits - i.get("authored", commits)
        by_trailer = (commits and credited >= TRAILER_SHARE * commits and any(NO_REPLY_MAILBOX.match(e) for e in emails)
                      and all(shared_mailbox(e) for e in emails))
        if by_trailer or any(len(shared.get(e, ())) >= 2 for e in emails):
            tool.add(i.get("name"))
    return tool - person

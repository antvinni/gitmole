"""Who knows which part of the tree: ownership aggregated by directory.

Every helper takes `base`, the directory levels a --path run's files all share (scope.base): the areas
are then counted from below them, so a run over backend/plugins/ maps backend/plugins/github/ and its
siblings rather than one backend/ holding everything. 0, the default, is the whole repository."""
from __future__ import annotations

from collections import Counter, defaultdict


ROOT = "(root files)"


def in_area(entity: str, area: str, base: int = 0) -> bool:
    """Whether the file `entity` is in `area` (a directory prefix ending in "/", or ROOT: the files with
    no directory below the base)."""
    return entity.count("/") <= base if area == ROOT else entity.startswith(area)


_INDEX = {}   # (id(tree), len(tree), base) -> (tree, the directory prefixes under which a tracked file sits, whether ROOT holds one)


def _tree_index(tree, base: int):
    """Every directory prefix ("a/", "a/b/") some tracked file sits under, and whether any file is a root
    file below the base: built once per tree listing, so in_tree is a set lookup instead of a scan of the
    whole listing for every row it is asked about (react's knowledge map asked 74,194 times). The key
    carries the listing's length, so a listing that gained or lost a path is indexed again."""
    key = (id(tree), len(tree), base)
    hit = _INDEX.get(key)
    if hit is not None and hit[0] is tree:
        return hit[1], hit[2]
    prefixes, root = set(), False
    for path in tree:
        parts = path.split("/")
        if len(parts) - 1 <= base:
            root = True
        for i in range(1, len(parts)):
            prefixes.add("/".join(parts[:i]) + "/")
    if len(_INDEX) > 8:   # a process renders a handful of reports; keep the cache from growing with them
        _INDEX.clear()
    _INDEX[key] = (tree, prefixes, root)
    return prefixes, root


def in_tree(area: str, tree: dict, base: int = 0) -> bool:
    """Whether any tracked file sits under `area` (a directory prefix ending in "/", or ROOT). With
    no tree listing every area counts: there is nothing to judge by."""
    if not tree:
        return True
    prefixes, root = _tree_index(tree, base)
    return root if area == ROOT else area in prefixes


def _area(entity: str, depth: int, base: int = 0) -> str:
    dirs = entity.split("/")[:-1]
    if len(dirs) <= base:
        return ROOT
    return "/".join(dirs[:base + depth]) + "/"


def top_area(entity: str, base: int = 0) -> str:
    """The top-level directory of a path (below the base), or ROOT."""
    return _area(entity, 1, base)


def present_rows(rows: list, tree: dict) -> list:
    """Ownership rows for files still in the tree. Filtering the rows before areas are built keeps a
    vanished layout (the src/ before a move to crates/, a root file deleted years ago) from inflating
    the total, hiding that one directory now holds almost everything, or making a vanished file's
    author the owner of what remains."""
    if not tree:
        return rows
    return [r for r in rows if r["entity"] in tree]


def _aggregate(rows: list, depth: int, base: int = 0, dated: bool = False) -> list:
    """Per area: lines added, authors, owners most first, and, when `dated` (the run's meta says the change
    analysis counted each author's `recent` commits, 0.45 on; a row without one has none), `recent`: how many of
    those authors committed to it inside the run's --gone window. A count, never a name: who is active in an
    area is not a ranking of them."""
    lines, per_author, active = Counter(), defaultdict(Counter), defaultdict(set)
    for r in rows:
        a = _area(r["entity"], depth, base)
        lines[a] += r["added"]
        per_author[a][r["author"]] += r["added"]
        if r.get("recent"):
            active[a].add(r["author"])
    out = []
    for a, n in lines.items():
        owners = sorted(per_author[a].items(), key=lambda kv: (-kv[1], kv[0]))
        out.append({"area": a, "lines": n, "authors": len(owners), "owners": owners, **({"recent": len(active[a])} if dated else {})})
    out.sort(key=lambda x: (-x["lines"], x["area"]))
    return out


def tied(owners: list, at: int = 0) -> int:
    """How many of an area's (name, lines) owners, most first, hold exactly the lines of the one at `at`:
    1 when that one stands alone. _aggregate orders equal counts by name, so the first of several is the
    alphabet's choice and not an owner: a squash commit that credits twelve co-authors gives each a twelfth
    of its lines, and whoever sorts first is then no more the area's owner than the other eleven."""
    if at >= len(owners):
        return 0
    return sum(1 for _, n in owners if n == owners[at][1])


def areas(ownership_rows: list, dominant: float = 0.8, base: int = 0, dated: bool = False) -> list:
    """Areas of the tree by lines added, with per-author ownership.

    Top-level directories, unless one of them holds `dominant` of all lines
    (a lone src/ or the like), in which case its subdirectories are used."""
    rows = [r for r in ownership_rows if r.get("added", 0) > 0]
    if not rows:
        return []
    top = _aggregate(rows, 1, base, dated)
    total = sum(a["lines"] for a in top)
    if top[0]["area"] != ROOT and top[0]["lines"] >= dominant * total:
        return _aggregate(rows, 2, base, dated)
    return top


def islands(areas_list: list, min_lines: int = 200, min_share: float = 0.9) -> list:
    """Areas of at least `min_lines` where one author wrote at least `min_share` of them."""
    out = []
    for a in areas_list:
        if a["lines"] < min_lines or not a["owners"]:
            continue
        owner, n = a["owners"][0]
        if n / a["lines"] >= min_share:
            out.append({"area": a["area"], "owner": owner, "share": round(100 * n / a["lines"]), "lines": a["lines"]})
    return out


def truck_factor(authors_of: dict, orphan_share: float = 0.5) -> tuple:
    """Avelino et al.'s truck factor: remove the person who authors the most files, again and again, until
    more than half the files have no author left. (the number removed, their names in order, the share
    orphaned at the end). authors_of: {file: set of names}."""
    files = list(authors_of)
    if not files:
        return 0, [], 0.0
    remaining = {f: set(a) for f, a in authors_of.items()}
    removed = []

    def orphaned():
        return sum(1 for a in remaining.values() if not a) / len(files)
    while orphaned() <= orphan_share:
        counts = {}
        for a in remaining.values():
            for who in a:
                counts[who] = counts.get(who, 0) + 1
        if not counts:
            break
        top = min(counts, key=lambda w: (-counts[w], w))
        removed.append(top)
        for a in remaining.values():
            a.discard(top)
    return len(removed), removed, orphaned()


def depth_for(paths: list, dominant: float = 0.8, base: int = 0) -> int:
    """1 for top-level directories, 2 when one top-level directory holds `dominant` of the files (a lone
    src/), as the knowledge map chooses."""
    from collections import Counter
    tops = Counter(_area(p, 1, base) for p in paths)
    return 2 if tops and tops.most_common(1)[0][1] >= dominant * len(paths) and tops.most_common(1)[0][0] != ROOT else 1

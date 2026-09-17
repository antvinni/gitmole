"""Change-coupling pairs grouped into clusters: a directory whose files all change together (generated
tables, one-per-version data files) is one fact, not a page of pairs."""
from __future__ import annotations

import os
from collections import defaultdict

ROOT = "(root files)"


def _dir(path: str) -> str:
    head = os.path.dirname(path)
    return head + "/" if head else ROOT


def _components(pairs: list) -> list:
    """Connected groups of files among `pairs` (union-find), each as the list of its pairs."""
    parent = {}

    def find(x):
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for p in pairs:
        parent[find(p["entity"])] = find(p["coupled"])
    groups = defaultdict(list)
    for p in pairs:
        groups[find(p["entity"])].append(p)
    return list(groups.values())


def clusters(pairs: list, min_files: int = 4) -> tuple:
    """Split `pairs` into (groups, rest). Pairs whose two files share a directory are gathered per
    directory and then into connected groups; a group touching at least `min_files` distinct files
    becomes one cluster with the file and pair counts, the weakest degree and the mean of the pairs'
    average revisions. Every other pair comes back unchanged, in its original order. Two unrelated
    pairs in one directory are not a cluster. Clusters are largest first."""
    by_dir = defaultdict(list)
    for p in pairs:
        if _dir(p["entity"]) == _dir(p["coupled"]):
            by_dir[_dir(p["entity"])].append(p)
    groups, taken = [], set()
    for directory, ps in by_dir.items():
        for component in _components(ps):
            files = {p["entity"] for p in component} | {p["coupled"] for p in component}
            if len(files) < min_files:
                continue
            groups.append({"dir": directory, "files": len(files), "pairs": len(component), "degree": min(p["degree"] for p in component),
                           "average-revs": round(sum(p["average-revs"] for p in component) / len(component))})
            taken.update(id(p) for p in component)
    groups.sort(key=lambda g: (-g["files"], -g["degree"], g["dir"]))
    return groups, [p for p in pairs if id(p) not in taken]

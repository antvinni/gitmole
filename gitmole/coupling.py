"""Change-coupling pairs grouped into clusters: a directory whose files all change together (generated
tables, one-per-version data files) is one fact, not a page of pairs."""
from __future__ import annotations

import os
from collections import defaultdict

ROOT = "(root files)"

SQUASH_SHARE = 0.5     # this share of subjects ending in (#NNNN), with almost no merge commits, is a squash-merged repository
FEW_MERGES = 0.02      # under this share of commits with two parents counts as almost none
MANY_MERGES = 0.1      # this share of merge commits and the branches' own commits are what the pairs describe


def regime(report: dict) -> tuple:
    """(kind, caveat): how changes reach the branch, from what the history declares. 'squash' when
    almost no commit has two parents and most subjects carry GitHub's squash suffix, so a coupling
    pair describes a pull request, not an edit; 'merge' when a tenth or more of the commits are merges,
    which export no file list; 'linear' otherwise, with nothing to caveat. An output directory from
    before the merge count says 'linear' too."""
    meta, act = report.get("meta") or {}, report.get("activity") or {}
    commits, merges, squash = meta.get("commits") or 0, meta.get("merges"), act.get("squash_subjects") or 0
    if not commits or merges is None:
        return "linear", None
    if merges / commits < FEW_MERGES and squash / commits >= SQUASH_SHARE:
        return "squash", (f"{round(100 * squash / commits)}% of subjects end in (#NNNN) and {merges:,} of {commits:,} commits are merges: "
                          "squash-merged, so the pairs describe pull requests, not edits")
    if merges / commits >= MANY_MERGES:
        return "merge", f"{merges:,} of {commits:,} commits are merges: merge commits carry no file list, so the pairs describe the commits on the branches"
    return "linear", None


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


def clusters(pairs: list, min_files: int = 4, min_density: float = 0.8) -> tuple:
    """Split `pairs` into (groups, rest). Pairs whose two files share a directory are gathered per
    directory and then into connected groups; a group of at least `min_files` distinct files with at
    least `min_density` of the possible pairs present becomes one cluster with the file and pair
    counts, the weakest degree and the mean of the pairs' average revisions. Every other pair comes
    back unchanged, in its original order. Two unrelated pairs in one directory, or a chain of pairs,
    are not a cluster: "each other" has to be true. Clusters are largest first."""
    by_dir = defaultdict(list)
    for p in pairs:
        if _dir(p["entity"]) == _dir(p["coupled"]):
            by_dir[_dir(p["entity"])].append(p)
    groups, taken = [], set()
    for directory, ps in by_dir.items():
        for component in _components(ps):
            files = {p["entity"] for p in component} | {p["coupled"] for p in component}
            possible = len(files) * (len(files) - 1) / 2
            if len(files) < min_files or len(component) < min_density * possible:
                continue
            groups.append({"dir": directory, "files": len(files), "pairs": len(component), "degree": min(p["degree"] for p in component),
                           "average-revs": round(sum(p["average-revs"] for p in component) / len(component))})
            taken.update(id(p) for p in component)
    groups.sort(key=lambda g: (-g["files"], -g["degree"], g["dir"]))
    return groups, [p for p in pairs if id(p) not in taken]

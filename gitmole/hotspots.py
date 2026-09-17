"""One ranking of hotspots, shared by the table and the findings that talk about them."""
from __future__ import annotations


def ranked(report: dict) -> list:
    """Files by revisions × lines of code, Tornhill-style. Files no longer in the tree score -1 and sort last."""
    files = (report.get("size") or {}).get("files") or {}
    out = []
    for r in report.get("revisions") or []:
        info = files.get(r["entity"])
        out.append({"entity": r["entity"], "revs": r["n-revs"], "code": info["code"] if info else None,
                    "complexity": info["complexity"] if info else None, "score": r["n-revs"] * info["code"] if info else -1})
    out.sort(key=lambda h: (-h["score"], -h["revs"], h["entity"]))
    return out


def top(report: dict, n: int = 10) -> set:
    return {h["entity"] for h in ranked(report)[:n]}


def derived(report: dict) -> set:
    """Files that are build outputs: generated (a header marker or a linguist-generated attribute,
    recorded by the run) or amalgamations (other files pasted together, found from the metrics).
    Their churn and complexity belong to the generator, so every churn view leaves them out."""
    return set((report.get("meta") or {}).get("generated") or []) | amalgamations(report)


def amalgamations(report: dict, min_shared: int = 20, min_sources: int = 2, min_share: float = 0.9) -> set:
    """Files that are other files pasted together by a build step (nlohmann's single_include/json.hpp):
    at least `min_share` of their functions, by name, complexity, length and arity, also appear in
    other files, they hold at least `min_shared` such functions, and those come from at least
    `min_sources` other files. Two files mirroring each other are not an amalgamation; neither is
    the union of the other."""
    from collections import defaultdict
    by_file = defaultdict(set)
    for f in report.get("functions") or []:
        by_file[f["file"]].add((f["function"], f["ccn"], f["nloc"], f["params"]))
    owners = defaultdict(set)
    for file, sigs in by_file.items():
        for s in sigs:
            owners[s].add(file)
    out = set()
    for file, sigs in by_file.items():
        if len(sigs) < min_shared:
            continue
        sources, matched = set(), 0
        for s in sigs:
            others = owners[s] - {file}
            if others:
                matched += 1
                sources |= others
        if matched >= min_shared and matched / len(sigs) >= min_share and len(sources) >= min_sources:
            out.add(file)
    return out

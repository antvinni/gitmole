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

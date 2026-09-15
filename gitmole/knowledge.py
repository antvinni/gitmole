"""Who knows which part of the tree: ownership aggregated by directory."""
from __future__ import annotations

from collections import Counter, defaultdict


def _area(entity: str, depth: int) -> str:
    parts = entity.split("/")
    if len(parts) == 1:
        return "."
    return "/".join(parts[:min(depth, len(parts) - 1)]) + "/"


def _aggregate(rows: list, depth: int) -> list:
    lines, per_author = Counter(), defaultdict(Counter)
    for r in rows:
        a = _area(r["entity"], depth)
        lines[a] += r["added"]
        per_author[a][r["author"]] += r["added"]
    out = []
    for a, n in lines.items():
        owners = sorted(per_author[a].items(), key=lambda kv: (-kv[1], kv[0]))
        out.append({"area": a, "lines": n, "authors": len(owners), "owners": owners})
    out.sort(key=lambda x: (-x["lines"], x["area"]))
    return out


def areas(ownership_rows: list, dominant: float = 0.8) -> list:
    """Areas of the tree by lines added, with per-author ownership.

    Top-level directories, unless one of them holds `dominant` of all lines
    (a lone src/ or the like), in which case its subdirectories are used."""
    rows = [r for r in ownership_rows if r.get("added", 0) > 0]
    if not rows:
        return []
    top = _aggregate(rows, 1)
    total = sum(a["lines"] for a in top)
    if top[0]["area"] != "." and top[0]["lines"] >= dominant * total:
        return _aggregate(rows, 2)
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

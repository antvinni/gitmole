"""Merge git identities that belong to the same person."""
from __future__ import annotations

import re


def _tokens(name: str) -> set:
    return {t for t in re.split(r"[^a-z0-9]+", name.lower()) if len(t) >= 3}


def same_person(a: dict, b: dict) -> bool:
    return a["email"].lower() == b["email"].lower() or len(_tokens(a["name"]) & _tokens(b["name"])) >= 2


def merge(identities: list) -> list:
    """Group identities by shared name tokens or email. Each row keeps the most-committed
    variant's name and email, sums the commits, and lists the other variants as aliases."""
    groups = []
    for i in identities:
        for g in groups:
            if any(same_person(i, j) for j in g):
                g.append(i)
                break
        else:
            groups.append([i])
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

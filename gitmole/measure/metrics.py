"""The arithmetic of docs/measurement.md, with no I/O: headroom, ROC-AUC, recall at an effort budget,
Popt, initial false alarms, rank stability, bootstrap intervals over repositories, Wilson intervals
and Cohen's kappa."""
from __future__ import annotations

import math
import random


def hits(ranked: list, outcome: set, top: int = 15) -> int:
    return len(outcome.intersection(ranked[:top]))


def expected(pool_size: int, positives: int, top: int = 15) -> float:
    """What a random `top` of the pool would name."""
    return min(top, pool_size) * positives / pool_size if pool_size else 0.0


def best(pool_size: int, positives: int, top: int = 15) -> int:
    return min(top, positives, pool_size)


def headroom(h: float, exp: float, most: float):
    """How much of the gap between random and perfect a list closes: (hits - expected) / (best - expected).
    None when there is no gap to close (no positive in the pool, or every file is one)."""
    return None if most - exp <= 0 else (h - exp) / (most - exp)


def auc(ranked: list, outcome: set):
    """ROC-AUC of an ordering: the chance a positive ranks above a negative, ties impossible. None with
    no positive or no negative."""
    pos = sum(1 for f in ranked if f in outcome)
    neg = len(ranked) - pos
    if not pos or not neg:
        return None
    seen_neg, above = 0, 0
    for f in reversed(ranked):   # from the bottom: each positive beats every negative already passed
        if f in outcome:
            above += seen_neg
        else:
            seen_neg += 1
    return above / (pos * neg)


def recall_at_effort(ranked: list, lines: dict, outcome: set, share: float = 0.2, total: int = None):
    """The share of the outcome inside the first files of the ranking whose lines add up to at most
    `share` of the codebase's lines (`total`, else the ranked files' own). None with no positive."""
    positives = [f for f in ranked if f in outcome]
    if not positives:
        return None
    budget = share * (total if total is not None else sum(lines.get(f, 0) for f in ranked))
    used, found = 0, 0
    for f in ranked:
        cost = lines.get(f, 0)
        if used + cost > budget:
            break
        used += cost
        found += f in outcome
    return found / len(positives)


def _lift_area(ranked: list, cost: dict, outcome: set):
    """The area under an ordering's effort-versus-found curve, both axes normalised to 1: x is the
    share of the effort spent, y the share of the outcome found. A trapezoid per file, so a file that
    costs nothing adds nothing. None when there is no effort to spend or nothing to find."""
    total = sum(cost.get(f, 0) for f in ranked)
    positives = sum(1 for f in ranked if f in outcome)
    if not total or not positives:
        return None
    area, y = 0.0, 0.0
    for f in ranked:
        dx = cost.get(f, 0) / total
        dy = (1 if f in outcome else 0) / positives
        area += dx * (y + dy / 2)
        y += dy
    return area


def popt(ranked: list, cost: dict, outcome: set):
    """Popt, the effort-aware measure Fu and Menzies, Yang et al. and Huang et al. state their
    comparisons in: 1 - (area(optimal) - area(ranked)) / (area(optimal) - area(worst)) over the
    effort-versus-found curve. The optimal ordering spends the least effort per file found (the
    outcome's files cheapest first, then the rest); the worst spends the most before finding
    anything. A list beats random above 0.5. None when either class is missing, or when no file
    costs anything to read."""
    if not any(f in outcome for f in ranked) or all(f in outcome for f in ranked):
        return None
    cheapest = sorted(ranked, key=lambda f: (cost.get(f, 0), f))
    dearest = list(reversed(cheapest))
    optimal = [f for f in cheapest if f in outcome] + [f for f in cheapest if f not in outcome]
    worst = [f for f in dearest if f not in outcome] + [f for f in dearest if f in outcome]
    here, best_, worst_ = (_lift_area(r, cost, outcome) for r in (ranked, optimal, worst))
    if here is None or best_ is None or worst_ is None or best_ - worst_ <= 0:
        return None
    return 1 - (best_ - here) / (best_ - worst_)


def ifa(ranked: list, outcome: set, top: int = None):
    """Initial false alarms: how many files a reader passes before the first one in the outcome, over
    the first `top` of the list (all of it when `top` is None). `top` when none of the head is in the
    outcome, which is the convention evaluate.effort already prints. None for an empty list."""
    head = ranked[:top] if top is not None else list(ranked)
    if not head:
        return None
    return next((i for i, f in enumerate(head) if f in outcome), len(head))


def spearman(a: list, b: list):
    """Rank correlation of two orderings over the files both hold. None with fewer than three shared."""
    common = [f for f in a if f in set(b)]
    if len(common) < 3:
        return None
    ra = {f: i for i, f in enumerate(common)}
    rb = {f: i for i, f in enumerate([f for f in b if f in ra])}
    n = len(common)
    d2 = sum((ra[f] - rb[f]) ** 2 for f in common)
    return 1 - 6 * d2 / (n * (n * n - 1))


def jaccard(a, b):
    a, b = set(a), set(b)
    return len(a & b) / len(a | b) if a | b else None


def median(values: list):
    v = sorted(x for x in values if x is not None)
    if not v:
        return None
    n = len(v)
    return v[n // 2] if n % 2 else (v[n // 2 - 1] + v[n // 2]) / 2


def percentile(values: list, q: float):
    v = sorted(x for x in values if x is not None)
    if not v:
        return None
    k = (len(v) - 1) * q
    lo, hi = math.floor(k), math.ceil(k)
    return v[lo] + (v[hi] - v[lo]) * (k - lo)


def bootstrap(groups: dict, stat, rounds: int = 2000, seed: int = 20260918, level: float = 0.95):
    """A percentile interval for stat(values), resampling whole groups (a repository with all its
    cut-offs) with replacement, since the cut-offs of one repository move together. `groups` maps a
    name to its list of values; seeded, so the same input gives the same interval. None with no values."""
    names = [g for g in sorted(groups) if [x for x in groups[g] if x is not None]]
    if not names:
        return None
    rng = random.Random(seed)
    out = []
    for _ in range(rounds):
        pick = [rng.choice(names) for _ in names]
        value = stat([x for g in pick for x in groups[g] if x is not None])
        if value is not None:
            out.append(value)
    if not out:
        return None
    out.sort()
    lo = out[int((1 - level) / 2 * (len(out) - 1))]
    hi = out[int((1 + level) / 2 * (len(out) - 1))]
    return [lo, hi]


def wilson(successes: int, n: int, z: float = 1.96):
    """The Wilson score interval of a proportion; None for n = 0."""
    if n == 0:
        return None
    p = successes / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return [max(0.0, centre - half), min(1.0, centre + half)]


def verdict(successes: int, n: int, line: float = 0.8) -> str:
    """sound when the interval's lower bound clears the line, broken when its upper bound is under it,
    undecided otherwise, unlabelled with no labels."""
    ci = wilson(successes, n)
    if ci is None:
        return "unlabelled"
    if ci[0] > line:
        return "sound"
    if ci[1] < line:
        return "broken"
    return "undecided"


def kappa(pairs: list):
    """Cohen's kappa over [(label_a, label_b)]; None with no pairs or no chance disagreement."""
    if not pairs:
        return None
    n = len(pairs)
    agree = sum(a == b for a, b in pairs) / n
    cats = {x for p in pairs for x in p}
    chance = sum((sum(a == c for a, _ in pairs) / n) * (sum(b == c for _, b in pairs) / n) for c in cats)
    return None if chance >= 1 else (agree - chance) / (1 - chance)

# Validation

What the watch list is worth, measured; back to [the README](https://github.com/antvinni/gitmole#readme).

The watch list is a heuristic. This page says how it did against what
happened next, on three repositories at the commits pinned in
`bin/render-examples`, and how other ways of ranking the same files did on
the same question. Regenerate any table with
`python -m gitmole.evaluate CLONE OUT_DIR`.

## Method

For each of six cut-off dates T, six months apart, counting back from the
pinned commit: the change analysis is rebuilt from the commits before T, scc
measures the tree as it was at T, and each variant names fifteen files. The
outcome is the set of source files that a fix commit touched in the six
months after T. A fix commit is one whose subject says fix, bug, regression
or crash, or uses the conventional `fix:` prefix: a proxy for a bug, as good
as the repository's commit subjects and no better. Every variant ranks the
same pool, the source files still in the tree at T that had changed more
than once; `random (expected)` is what fifteen files drawn from that pool
at random would name. Each column heading says how many files of the pool
were fixed in that window.

The variants: `watch list (hotspot)` is what gitmole ranks by, revisions ×
lines of code. The two factor products are what it ranked by before 0.8,
churn × (1 + recent fixes) × (1 + complexity) × 1.5 for a single owner,
with each factor divided by the repository's largest value (`max-scaled`,
the score 0.7 shipped) or taken as the file's rank among the scored files
(`rank-scaled`). `churn` is revisions alone, `size` lines of code alone, and
`recent fixes` the fix commits of the six months before T.

## Results

### curl, top 15, 6-month horizon

| variant | 2023-09-17 (153 of 614 fixed) | 2024-03-17 (166 of 634 fixed) | 2024-09-17 (190 of 646 fixed) | 2025-03-17 (153 of 656 fixed) | 2025-09-17 (420 of 667 fixed) | 2026-03-17 (217 of 660 fixed) | total |
|---|---:|---:|---:|---:|---:|---:|---:|
| watch list (hotspot) | 15 | 14 | 14 | 13 | 15 | 15 | 86 |
| factor product (max-scaled) | 15 | 14 | 14 | 13 | 15 | 15 | 86 |
| factor product (rank-scaled) | 14 | 13 | 14 | 12 | 15 | 15 | 83 |
| churn | 15 | 14 | 13 | 13 | 15 | 15 | 85 |
| size | 15 | 15 | 15 | 15 | 15 | 15 | 90 |
| recent fixes | 13 | 14 | 14 | 14 | 15 | 15 | 85 |
| random (expected) | 3.7 | 3.9 | 4.4 | 3.5 | 9.4 | 4.9 | 29.8 |

`--all` exports 39,895 commits (7,468 fixes); HEAD reaches 39,758 (7,461 fixes).

### django, top 15, 6-month horizon

| variant | 2023-09-08 (152 of 931 fixed) | 2024-03-08 (150 of 936 fixed) | 2024-09-08 (173 of 938 fixed) | 2025-03-08 (188 of 941 fixed) | 2025-09-08 (178 of 943 fixed) | 2026-03-08 (201 of 956 fixed) | total |
|---|---:|---:|---:|---:|---:|---:|---:|
| watch list (hotspot) | 14 | 14 | 13 | 14 | 14 | 15 | 84 |
| factor product (max-scaled) | 12 | 12 | 12 | 12 | 14 | 14 | 76 |
| factor product (rank-scaled) | 13 | 13 | 12 | 13 | 13 | 14 | 78 |
| churn | 12 | 10 | 12 | 10 | 13 | 13 | 70 |
| size | 13 | 12 | 10 | 11 | 12 | 12 | 70 |
| recent fixes | 13 | 14 | 14 | 14 | 14 | 13 | 82 |
| random (expected) | 2.4 | 2.4 | 2.8 | 3.0 | 2.8 | 3.2 | 16.6 |

`--all` exports 52,833 commits (30,128 fixes); HEAD reaches 34,933 (20,452 fixes).

### react, top 15, 6-month horizon

| variant | 2023-09-16 (82 of 1257 fixed) | 2024-03-16 (57 of 1286 fixed) | 2024-09-16 (76 of 1625 fixed) | 2025-03-16 (103 of 1670 fixed) | 2025-09-16 (110 of 1763 fixed) | 2026-03-16 (36 of 1792 fixed) | total |
|---|---:|---:|---:|---:|---:|---:|---:|
| watch list (hotspot) | 7 | 6 | 12 | 10 | 10 | 11 | 56 |
| factor product (max-scaled) | 5 | 5 | 7 | 10 | 7 | 8 | 42 |
| factor product (rank-scaled) | 7 | 6 | 11 | 12 | 8 | 7 | 51 |
| churn | 3 | 5 | 6 | 9 | 5 | 7 | 35 |
| size | 8 | 5 | 7 | 10 | 8 | 9 | 47 |
| recent fixes | 8 | 6 | 10 | 9 | 9 | 7 | 49 |
| random (expected) | 1.0 | 0.7 | 0.7 | 0.9 | 0.9 | 0.3 | 4.5 |

`--all` exports 35,265 commits (4,501 fixes); HEAD reaches 21,703 (2,985 fixes).

## Totals

| variant | curl | django | react | total |
|---|---:|---:|---:|---:|
| watch list (hotspot) | 86 | 84 | 56 | 226 |
| factor product (max-scaled) | 86 | 76 | 42 | 204 |
| factor product (rank-scaled) | 83 | 78 | 51 | 212 |
| churn | 85 | 70 | 35 | 190 |
| size | 90 | 70 | 47 | 207 |
| recent fixes | 85 | 82 | 49 | 216 |
| random (expected) | 29.8 | 16.6 | 4.5 | 50.9 |

Of 270 possible: three repositories, six cut-offs, fifteen files.

## What the numbers say

Every list beats a random pick: by about three times on curl, between four
and five on django and between eight and twelve on react. Beyond that:

- **Revisions × lines of code does best**, 226 of 270: first on django (84,
  two ahead of recent fixes) and on react (56, five ahead of the rank-scaled
  factor product), and level with most lists on curl. That is why the watch
  list ranks by it, and why fixes, complexity and ownership are the reasons
  printed beside a file and not part of its rank.
- **Recent fixes alone come second**, 216. A file fixed lately is likely to
  be fixed again; the list shows that count first among its reasons.
- **The factor products trail the ranking they replaced**: 212 rank-scaled,
  204 max-scaled. Rank scaling is the better of the two, mostly on react (51
  against 42).
- **Churn alone does worst**, 190, and size alone (207) does better than
  churn: on these repositories how much code a file holds says more about
  its next fix than how often it changed, and the product says more than
  either.
- **curl is saturated.** Between 23% and 63% of its scored files get a
  fix-labelled commit in any six months, so almost any sensible fifteen
  hit; size alone scores 90 of 90 there. The backtest line under a
  report's watch list has the same limit: on a repository where most files
  are fixed often, "named 15 of 15" says little.

## Every ref, or the checked-out branch

Since 0.8 the change log is the checked-out branch's history, `git log
HEAD`; before, it was `git log --all`. The last line under each table counts
what every ref would add: next to nothing on curl (7,468 fix commits against
7,461), about half as much again on django (30,128 against 20,452) and react
(4,501 against 2,985), where release branches carry backports of fixes
already on the main branch and other refs carry work that was never merged.
Counted from every ref, a backport is a second fix to the same file. The
same measurement over the `--all` logs put revisions × lines of code first
as well, 229 of 270.

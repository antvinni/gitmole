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
were fixed in that window. Generated and vendored files are left out of the
pool at every cut-off as they were at that cut-off: the tree is classified as
it stood then, from its own headers, licences and `.gitattributes`. Since
0.10 vendored and example code are out of the pool everywhere, so the numbers
below are re-measured.

The variants: `watch list (hotspot)` is what gitmole ranks by, revisions ×
lines of code. The two factor products are what it ranked by before 0.8,
churn × (1 + recent fixes) × (1 + complexity) × 1.5 for a single owner,
with each factor divided by the repository's largest value (`max-scaled`,
the score 0.7 shipped) or taken as the file's rank among the scored files
(`rank-scaled`). `churn` is revisions alone, `size` lines of code alone, and
`recent fixes` the fix commits of the six months before T.

## Results

### curl, top 15, 6-month horizon

| variant | 2023-09-17 (139 of 497 fixed) | 2024-03-17 (143 of 508 fixed) | 2024-09-17 (163 of 518 fixed) | 2025-03-17 (139 of 527 fixed) | 2025-09-17 (342 of 538 fixed) | 2026-03-17 (195 of 527 fixed) | total |
|---|---:|---:|---:|---:|---:|---:|---:|
| watch list (hotspot) | 15 | 14 | 14 | 13 | 15 | 15 | 86 |
| factor product (max-scaled) | 15 | 14 | 14 | 13 | 15 | 15 | 86 |
| factor product (rank-scaled) | 14 | 13 | 15 | 12 | 15 | 15 | 84 |
| churn | 15 | 14 | 13 | 13 | 15 | 15 | 85 |
| size | 15 | 15 | 15 | 15 | 15 | 15 | 90 |
| recent fixes | 13 | 14 | 14 | 14 | 15 | 15 | 85 |
| random (expected) | 4.2 | 4.2 | 4.7 | 4.0 | 9.5 | 5.6 | 32.2 |

`--all` exports 39,902 commits (7,470 fixes); HEAD reaches 39,758 (7,461 fixes).

### django, top 15, 6-month horizon

| variant | 2023-09-08 (147 of 819 fixed) | 2024-03-08 (150 of 824 fixed) | 2024-09-08 (171 of 826 fixed) | 2025-03-08 (180 of 829 fixed) | 2025-09-08 (173 of 831 fixed) | 2026-03-08 (193 of 844 fixed) | total |
|---|---:|---:|---:|---:|---:|---:|---:|
| watch list (hotspot) | 14 | 14 | 13 | 14 | 14 | 15 | 84 |
| factor product (max-scaled) | 12 | 13 | 13 | 13 | 14 | 15 | 80 |
| factor product (rank-scaled) | 13 | 13 | 12 | 12 | 13 | 14 | 77 |
| churn | 12 | 10 | 12 | 10 | 13 | 13 | 70 |
| size | 15 | 15 | 13 | 13 | 14 | 14 | 84 |
| recent fixes | 13 | 14 | 14 | 14 | 14 | 13 | 82 |
| random (expected) | 2.7 | 2.7 | 3.1 | 3.3 | 3.1 | 3.4 | 18.3 |

`--all` exports 52,840 commits (30,130 fixes); HEAD reaches 34,933 (20,452 fixes).

### react, top 15, 6-month horizon

| variant | 2023-09-16 (81 of 1069 fixed) | 2024-03-16 (57 of 1094 fixed) | 2024-09-16 (63 of 1270 fixed) | 2025-03-16 (62 of 1292 fixed) | 2025-09-16 (74 of 1353 fixed) | 2026-03-16 (33 of 1375 fixed) | total |
|---|---:|---:|---:|---:|---:|---:|---:|
| watch list (hotspot) | 7 | 6 | 12 | 10 | 9 | 10 | 54 |
| factor product (max-scaled) | 5 | 5 | 7 | 10 | 7 | 8 | 42 |
| factor product (rank-scaled) | 7 | 6 | 11 | 12 | 10 | 8 | 54 |
| churn | 3 | 5 | 6 | 9 | 5 | 7 | 35 |
| size | 8 | 5 | 8 | 9 | 7 | 8 | 45 |
| recent fixes | 8 | 6 | 7 | 10 | 8 | 6 | 45 |
| random (expected) | 1.1 | 0.8 | 0.7 | 0.7 | 0.8 | 0.4 | 4.5 |

`--all` exports 35,268 commits (4,501 fixes); HEAD reaches 21,703 (2,985 fixes).

## Totals

| variant | curl | django | react | total |
|---|---:|---:|---:|---:|
| watch list (hotspot) | 86 | 84 | 54 | 224 |
| factor product (max-scaled) | 86 | 80 | 42 | 208 |
| factor product (rank-scaled) | 84 | 77 | 54 | 215 |
| churn | 85 | 70 | 35 | 190 |
| size | 90 | 84 | 45 | 219 |
| recent fixes | 85 | 82 | 45 | 212 |
| random (expected) | 32.2 | 18.3 | 4.5 | 55.0 |

Of 270 possible: three repositories, six cut-offs, fifteen files.

## What the numbers say

Every list beats a random pick: by about three times on curl, four times on
django and eight to twelve times on react. Beyond that:

- **Revisions × lines of code does best**, 224 of 270: level with size alone
  on django (84, two ahead of recent fixes) and with the rank-scaled factor
  product on react (54, nine ahead of size and of recent fixes), and on curl
  level with the max-scaled factor product, one ahead of churn and of recent
  fixes, and four behind size alone. That is why the watch list ranks by it,
  and why fixes, complexity and ownership are the reasons printed beside a
  file and not part of its rank.
- **Size alone comes second**, 219, and is the closest rival: it takes curl
  outright (90 of 90) and ties django, and only react separates the two,
  where it is nine behind.
- **The factor products still trail the ranking that replaced them**: 215
  rank-scaled, 208 max-scaled. Rank scaling is the better of the two, on
  react above all (54 against 42), where it matches the watch list.
- **Recent fixes**, 212. A file fixed lately is likely to be fixed again;
  the list prints that count beside the file, right after how often it
  changed.
- **Churn alone does worst**, 190. Its product with size, which is what the
  watch list ranks by, does better than either factor alone in total, though
  not on curl, where size alone is ahead.
- **curl is saturated.** Between 26% and 64% of its scored files get a
  fix-labelled commit in any six months, so almost any sensible fifteen
  hit; size alone scores 90 of 90 there. The backtest line under a
  report's watch list has the same limit: on a repository where most files
  are fixed often, "named 15 of 15" says little.

## Every ref, or the checked-out branch

Since 0.8 the change log is the checked-out branch's history, `git log
HEAD`; before, it was `git log --all`. The last line under each table counts
what every ref would add: next to nothing on curl (7,470 fix commits against
7,461), about half as much again on django (30,130 against 20,452) and react
(4,501 against 2,985), where release branches carry backports of fixes
already on the main branch and other refs carry work that was never merged.
Counted from every ref, a backport is a second fix to the same file. The
same measurement over the `--all` logs, made before 0.10 changed the pool,
put revisions × lines of code first as well, 229 of 270.

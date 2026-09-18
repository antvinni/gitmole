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
0.10 vendored and example code are out of the pool everywhere, and since
0.11 the log is read with whitespace ignored and the sweeping commits (a
formatter run, a rename across the tree; 115 on curl, 76 on django, 20 on
react) and the commits `.git-blame-ignore-revs` declares are left out of
every count, so a file a formatter only re-indented is not a file that
changed. Since 0.12 a fix that changes more lines than 99% of the
repository's commits (never under 500) is not an outcome either: tangled by
size, it credits none of its files. The numbers below are measured that
way; the pools are a little smaller than before (471 files at curl's first
cut-off, against 497), and the watch list's total moved from 224 to 225.

The variants: `watch list (hotspot)` is what gitmole ranks by, revisions ×
lines of code. The two factor products are what it ranked by before 0.8,
churn × (1 + recent fixes) × (1 + complexity) × 1.5 for a single owner,
with each factor divided by the repository's largest value (`max-scaled`,
the score 0.7 shipped) or taken as the file's rank among the scored files
(`rank-scaled`). `churn` is revisions alone, `size` lines of code alone, and
`recent fixes` the fix commits of the six months before T.

## Results

### curl, top 15, 6-month horizon

| variant | 2023-09-17 (137 of 471 fixed) | 2024-03-17 (142 of 485 fixed) | 2024-09-17 (160 of 504 fixed) | 2025-03-17 (134 of 517 fixed) | 2025-09-17 (264 of 524 fixed) | 2026-03-17 (169 of 511 fixed) | total |
|---|---:|---:|---:|---:|---:|---:|---:|
| watch list (hotspot) | 15 | 14 | 14 | 13 | 15 | 15 | 86 |
| factor product (max-scaled) | 15 | 14 | 14 | 13 | 15 | 15 | 86 |
| factor product (rank-scaled) | 14 | 15 | 15 | 13 | 15 | 15 | 87 |
| churn | 15 | 14 | 13 | 13 | 15 | 15 | 85 |
| size | 15 | 15 | 15 | 15 | 15 | 15 | 90 |
| recent fixes | 14 | 14 | 14 | 13 | 15 | 15 | 85 |
| random (expected) | 4.4 | 4.4 | 4.8 | 3.9 | 7.6 | 5.0 | 30.1 |

`--all` exports 39,902 commits (7,470 fixes); HEAD reaches 39,758 (7,461 fixes).

### django, top 15, 6-month horizon

| variant | 2023-09-08 (147 of 789 fixed) | 2024-03-08 (143 of 793 fixed) | 2024-09-08 (170 of 795 fixed) | 2025-03-08 (173 of 798 fixed) | 2025-09-08 (173 of 803 fixed) | 2026-03-08 (182 of 817 fixed) | total |
|---|---:|---:|---:|---:|---:|---:|---:|
| watch list (hotspot) | 14 | 14 | 13 | 13 | 15 | 15 | 84 |
| factor product (max-scaled) | 12 | 13 | 13 | 12 | 14 | 14 | 78 |
| factor product (rank-scaled) | 13 | 13 | 12 | 13 | 13 | 14 | 78 |
| churn | 12 | 11 | 12 | 10 | 12 | 12 | 69 |
| size | 15 | 15 | 13 | 13 | 14 | 13 | 83 |
| recent fixes | 13 | 14 | 15 | 14 | 14 | 13 | 83 |
| random (expected) | 2.8 | 2.7 | 3.2 | 3.3 | 3.2 | 3.3 | 18.5 |

`--all` exports 52,840 commits (30,130 fixes); HEAD reaches 34,933 (20,452 fixes).

### react, top 15, 6-month horizon

| variant | 2023-09-16 (79 of 946 fixed) | 2024-03-16 (55 of 979 fixed) | 2024-09-16 (63 of 1098 fixed) | 2025-03-16 (60 of 1172 fixed) | 2025-09-16 (74 of 1239 fixed) | 2026-03-16 (33 of 1261 fixed) | total |
|---|---:|---:|---:|---:|---:|---:|---:|
| watch list (hotspot) | 7 | 7 | 12 | 10 | 9 | 10 | 55 |
| factor product (max-scaled) | 5 | 5 | 7 | 10 | 7 | 8 | 42 |
| factor product (rank-scaled) | 9 | 7 | 11 | 12 | 10 | 8 | 57 |
| churn | 3 | 5 | 6 | 9 | 5 | 7 | 35 |
| size | 8 | 5 | 9 | 9 | 7 | 8 | 46 |
| recent fixes | 8 | 6 | 7 | 9 | 8 | 6 | 44 |
| random (expected) | 1.3 | 0.8 | 0.9 | 0.8 | 0.9 | 0.4 | 5.1 |

`--all` exports 35,268 commits (4,501 fixes); HEAD reaches 21,703 (2,985 fixes).

## Totals

| variant | curl | django | react | total |
|---|---:|---:|---:|---:|
| watch list (hotspot) | 86 | 84 | 55 | 225 |
| factor product (max-scaled) | 86 | 78 | 42 | 206 |
| factor product (rank-scaled) | 87 | 78 | 57 | 222 |
| churn | 85 | 69 | 35 | 189 |
| size | 90 | 83 | 46 | 219 |
| recent fixes | 85 | 83 | 44 | 212 |
| random (expected) | 30.1 | 18.5 | 5.1 | 53.7 |

Of 270 possible: three repositories, six cut-offs, fifteen files.

## What the numbers say

Every list beats a random pick: by about three times on curl, four times on
django and eight to twelve times on react. Beyond that:

- **Revisions × lines of code does best**, 225 of 270: first on django (84,
  one ahead of size alone and of recent fixes), two behind the rank-scaled
  factor product on react (55 against 57, nine ahead of size), and on curl
  level with the max-scaled factor product, one ahead of churn and of recent
  fixes, one behind the rank-scaled product and four behind size alone.
  That is why the watch list ranks by it, and why fixes, complexity and
  ownership are the reasons printed beside a file and not part of its rank.
- **The rank-scaled factor product comes second**, 222, and takes curl by
  one (87) and react (57); **size alone**, 219, takes curl outright (90 of
  90) and is one behind on django, and only react separates it from the
  watch list, where it is nine behind.
- **The max-scaled factor product trails**, 206: what 0.7 shipped, and the
  worst of the three on react (42).
- **Recent fixes**, 212. A file fixed lately is likely to be fixed again;
  the list prints that count beside the file, right after how often it
  changed.
- **Churn alone does worst**, 189. Its product with size, which is what the
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

# Validation

What the watch list is worth, measured; back to [the README](https://github.com/antvinni/gitmole#readme).

The watch list is a heuristic. This page says how it did against what
happened next, on three repositories at the commits pinned in
`bin/render-examples`, and how lists that are much simpler to explain did on
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

The variants: `watch (max-scaled)` is the score gitmole 0.7 ships, churn ×
(1 + recent fixes) × (1 + complexity) × 1.5 for a single owner, each factor
divided by the repository's largest value; `watch (rank-scaled)` is the same
product with each factor taken as the file's rank among the scored files;
`churn` is revisions alone, `size` lines of code alone, `hotspot` their
product (the ranking of the report's Hotspots table), and `recent fixes`
the fix commits of the six months before T.

## Results

### curl, top 15, 6-month horizon

| variant | 2023-09-17 (153 of 614 fixed) | 2024-03-17 (166 of 634 fixed) | 2024-09-17 (190 of 646 fixed) | 2025-03-17 (153 of 656 fixed) | 2025-09-17 (420 of 667 fixed) | 2026-03-17 (218 of 660 fixed) | total |
|---|---:|---:|---:|---:|---:|---:|---:|
| watch (max-scaled) | 15 | 14 | 14 | 13 | 15 | 15 | 86 |
| watch (rank-scaled) | 14 | 13 | 14 | 12 | 15 | 15 | 83 |
| churn | 15 | 14 | 13 | 13 | 15 | 15 | 85 |
| size | 15 | 15 | 15 | 15 | 15 | 15 | 90 |
| hotspot | 15 | 14 | 14 | 13 | 15 | 15 | 86 |
| recent fixes | 13 | 14 | 14 | 14 | 15 | 15 | 85 |
| random (expected) | 3.7 | 3.9 | 4.4 | 3.5 | 9.4 | 5.0 | 29.9 |

`--all` exports 39,892 commits (7,468 fixes); HEAD reaches 39,758 (7,461 fixes).

### django, top 15, 6-month horizon

| variant | 2023-09-08 (152 of 1020 fixed) | 2024-03-08 (150 of 1025 fixed) | 2024-09-08 (173 of 1027 fixed) | 2025-03-08 (188 of 1030 fixed) | 2025-09-08 (178 of 1034 fixed) | 2026-03-08 (200 of 1052 fixed) | total |
|---|---:|---:|---:|---:|---:|---:|---:|
| watch (max-scaled) | 13 | 11 | 12 | 11 | 13 | 13 | 73 |
| watch (rank-scaled) | 13 | 13 | 12 | 12 | 12 | 14 | 76 |
| churn | 13 | 10 | 13 | 10 | 13 | 12 | 71 |
| size | 13 | 12 | 10 | 11 | 12 | 12 | 70 |
| hotspot | 14 | 14 | 13 | 14 | 14 | 15 | 84 |
| recent fixes | 13 | 13 | 14 | 12 | 14 | 12 | 78 |
| random (expected) | 2.2 | 2.2 | 2.5 | 2.7 | 2.6 | 2.9 | 15.1 |

`--all` exports 52,832 commits (30,128 fixes); HEAD reaches 34,933 (20,452 fixes).

### react, top 15, 6-month horizon

| variant | 2023-09-16 (85 of 1432 fixed) | 2024-03-16 (65 of 1456 fixed) | 2024-09-16 (82 of 1758 fixed) | 2025-03-16 (113 of 1809 fixed) | 2025-09-16 (117 of 1903 fixed) | 2026-03-16 (45 of 1969 fixed) | total |
|---|---:|---:|---:|---:|---:|---:|---:|
| watch (max-scaled) | 5 | 11 | 7 | 9 | 8 | 6 | 46 |
| watch (rank-scaled) | 8 | 6 | 10 | 13 | 6 | 6 | 49 |
| churn | 3 | 11 | 6 | 9 | 7 | 6 | 42 |
| size | 8 | 5 | 7 | 10 | 8 | 9 | 47 |
| hotspot | 7 | 6 | 12 | 12 | 11 | 11 | 59 |
| recent fixes | 9 | 6 | 11 | 7 | 5 | 2 | 40 |
| random (expected) | 0.9 | 0.7 | 0.7 | 0.9 | 0.9 | 0.3 | 4.4 |

`--all` exports 35,263 commits (4,501 fixes); HEAD reaches 21,703 (2,985 fixes).

## Totals

| variant | curl | django | react | total |
|---|---:|---:|---:|---:|
| watch (max-scaled) | 86 | 73 | 46 | 205 |
| watch (rank-scaled) | 83 | 76 | 49 | 208 |
| churn | 85 | 71 | 42 | 198 |
| size | 90 | 70 | 47 | 207 |
| hotspot | 86 | 84 | 59 | 229 |
| recent fixes | 85 | 78 | 40 | 203 |
| random (expected) | 29.9 | 15.1 | 4.4 | 49.4 |

Of 270 possible: three repositories, six cut-offs, fifteen files.

## What the numbers say

Every list beats a random pick: by about three times on curl, five on
django and ten on react. Beyond that:

- **The hotspot ranking does best**, 229 of 270: clearly ahead on django and
  react, level on curl. Revisions times lines of code, which gitmole
  already prints as its Hotspots table, names more of the files that get
  fixed next than the watch list's longer formula does.
- **Rank scaling costs nothing**: 208 against 205 for the max-scaled score.
  It is three hits behind on curl and three ahead on each of django and
  react, and unlike max scaling it does not move every file's score when one
  outlier moves.
- **The watch list beats churn alone**, 208 and 205 against 198, but not by
  much, and size alone (207) does as well. The fix, complexity and ownership
  factors are better read as the reasons a file is on the list than as
  evidence that the list is sharper for them.
- **curl is saturated.** Between a quarter and two thirds of its scored
  files get a fix-labelled commit in any six months, so almost any sensible
  fifteen hit; size alone scores 90 of 90 there. The backtest line under a
  report's watch list has the same limit: on a repository where most files
  are fixed often, "named 15 of 15" says little.

## Every ref, or the checked-out branch

The change log these tables were computed from is `git log --all`, as
gitmole 0.7 exports it. The last line under each table counts what that
adds to the checked-out branch's own history: next to nothing on curl
(7,468 fix commits against 7,461), about half as much again on django
(30,128 against 20,452) and react (4,501 against 2,985), where release
branches carry backports of fixes already on the main branch and other refs
carry work that was never merged. Those commits are in the churn and fix
counts above, on both sides of every cut-off and for every variant alike.

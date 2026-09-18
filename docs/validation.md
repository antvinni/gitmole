# Validation

What the watch list is worth, measured; back to [the README](https://github.com/antvinni/gitmole#readme).

The watch list is a heuristic. This page says how it did against what
happened next, on three repositories at the commits pinned in
`bin/render-examples`, and how other ways of ranking the same files did on
the same question. Regenerate any table with
`python -m gitmole.evaluate CLONE OUT_DIR`; `--szz` adds the tables against
bug-inducing commits further down.

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
`recent fixes` the fix commits of the six months before T. `change entropy
(HCM)` is Hassan's history complexity metric (ICSE 2009), the one metric with
published evidence of beating churn: per calendar month, the Shannon entropy
of the files' shares of that month's changes, normalised by log2 of the files
changed; a file's score is the sum over months of its share times that
entropy, each month's weight halved for every month back from T.

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
| change entropy (HCM) | 12 | 13 | 15 | 15 | 14 | 15 | 84 |
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
| change entropy (HCM) | 12 | 13 | 6 | 11 | 13 | 10 | 65 |
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
| change entropy (HCM) | 4 | 2 | 10 | 7 | 10 | 3 | 36 |
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
| change entropy (HCM) | 84 | 65 | 36 | 185 |
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
- **Change entropy does not earn the rank**, 185: two behind the watch
  list on curl (84), nineteen behind on django (65) and nineteen on
  react (36), and behind size alone and recent fixes everywhere but curl.
  The roadmap's own rule applies: it stays a reason, `changed in 14
  different months`, printed beside a file that changed in twelve or more,
  and never a rank.
- **curl is saturated.** Between 26% and 64% of its scored files get a
  fix-labelled commit in any six months, so almost any sensible fifteen
  hit; size alone scores 90 of 90 there. The backtest line under a
  report's watch list has the same limit: on a repository where most files
  are fixed often, "named 15 of 15" says little.

## Bug-inducing commits, by R-SZZ

The tables above score fix locality: a fix-labelled commit touched the file
in the six months after the cut-off. A file every fix touches, a changelog or
a config, scores that way without ever being wrong. The SZZ family gives the
other label, defect insertion: the commit that wrote the lines a fix removed.
Rosa et al. measured the git-only variants against a developer-informed
oracle and found R-SZZ, which keeps only the most recent commit a fix's
removed lines blame to, the best of them at precision 0.66 against 0.39 for
keeping every candidate. `python -m gitmole.evaluate CLONE OUT_DIR --szz`
adds that outcome: for each fix landing in the six months after T, `git
blame -w -C -C` of the parent at the lines the fix removed or changed (test,
vendored, example and generated files are not candidates), the most recent
commit blamed is the bug-inducing one, and a file it wrote is a hit when
that commit is before T, so a list drawn at T could have known. An
insert-only fix blames nothing, which is R-SZZ's known blind spot, and a fix
whose bug was planted after T is not counted against any list. The outcome
sets are a third to a quarter the size of the fix-locality ones, so the
numbers below are smaller and the random baseline lower.

### curl, top 15, 6-month horizon, R-SZZ

| variant | 2023-09-17 (38 of 471 bug-inducing) | 2024-03-17 (43 of 485 bug-inducing) | 2024-09-17 (47 of 504 bug-inducing) | 2025-03-17 (48 of 517 bug-inducing) | 2025-09-17 (64 of 524 bug-inducing) | 2026-03-17 (46 of 511 bug-inducing) | total |
|---|---:|---:|---:|---:|---:|---:|---:|
| watch list (hotspot) | 12 | 5 | 7 | 10 | 12 | 10 | 56 |
| factor product (max-scaled) | 11 | 5 | 8 | 10 | 11 | 8 | 53 |
| factor product (rank-scaled) | 13 | 8 | 9 | 10 | 10 | 7 | 57 |
| churn | 11 | 6 | 7 | 11 | 11 | 9 | 55 |
| size | 11 | 6 | 8 | 13 | 13 | 10 | 61 |
| recent fixes | 10 | 4 | 8 | 10 | 12 | 11 | 55 |
| random (expected) | 1.2 | 1.3 | 1.4 | 1.4 | 1.8 | 1.4 | 8.5 |

### django, top 15, 6-month horizon, R-SZZ

| variant | 2023-09-08 (79 of 789 bug-inducing) | 2024-03-08 (65 of 793 bug-inducing) | 2024-09-08 (91 of 795 bug-inducing) | 2025-03-08 (78 of 798 bug-inducing) | 2025-09-08 (95 of 803 bug-inducing) | 2026-03-08 (82 of 817 bug-inducing) | total |
|---|---:|---:|---:|---:|---:|---:|---:|
| watch list (hotspot) | 12 | 10 | 9 | 8 | 12 | 11 | 62 |
| factor product (max-scaled) | 11 | 9 | 9 | 8 | 10 | 9 | 56 |
| factor product (rank-scaled) | 12 | 10 | 8 | 8 | 7 | 10 | 55 |
| churn | 10 | 9 | 7 | 8 | 8 | 8 | 50 |
| size | 14 | 12 | 10 | 10 | 11 | 9 | 66 |
| recent fixes | 13 | 9 | 9 | 11 | 8 | 9 | 59 |
| random (expected) | 1.5 | 1.2 | 1.7 | 1.5 | 1.8 | 1.5 | 9.2 |

### react, top 15, 6-month horizon, R-SZZ

| variant | 2023-09-16 (22 of 946 bug-inducing) | 2024-03-16 (16 of 979 bug-inducing) | 2024-09-16 (24 of 1098 bug-inducing) | 2025-03-16 (17 of 1172 bug-inducing) | 2025-09-16 (28 of 1239 bug-inducing) | 2026-03-16 (16 of 1261 bug-inducing) | total |
|---|---:|---:|---:|---:|---:|---:|---:|
| watch list (hotspot) | 6 | 5 | 6 | 5 | 4 | 6 | 32 |
| factor product (max-scaled) | 4 | 3 | 3 | 3 | 4 | 5 | 22 |
| factor product (rank-scaled) | 6 | 4 | 6 | 6 | 5 | 5 | 32 |
| churn | 2 | 3 | 2 | 3 | 1 | 3 | 14 |
| size | 7 | 4 | 5 | 4 | 4 | 6 | 30 |
| recent fixes | 6 | 4 | 5 | 5 | 4 | 4 | 28 |
| random (expected) | 0.3 | 0.2 | 0.3 | 0.2 | 0.3 | 0.2 | 1.5 |

### Totals, R-SZZ

| variant | curl | django | react | total |
|---|---:|---:|---:|---:|
| watch list (hotspot) | 56 | 62 | 32 | 150 |
| factor product (max-scaled) | 53 | 56 | 22 | 131 |
| factor product (rank-scaled) | 57 | 55 | 32 | 144 |
| churn | 55 | 50 | 14 | 119 |
| size | 61 | 66 | 30 | 157 |
| recent fixes | 55 | 59 | 28 | 142 |
| random (expected) | 8.5 | 9.2 | 1.5 | 19.2 |

Against defect insertion the order changes at the top: **size alone leads**,
61, 66 and 30 for 157 of 270, and the **watch list is second** at
150, ahead on react (32 against 30) and behind on curl and django by five and
four. The rank-scaled factor product follows at 144, recent fixes at 142, the
max-scaled product at 131 and churn alone, last again, at 119; a random
fifteen would name 19. The reading: where a bug was planted is even more a
matter of file size than where the next fix lands, and revisions × lines of
code keeps most of that while staying ahead of every list that leans on
churn or fixes. The watch list keeps its ranking; this page carries both
outcomes so the trade is visible.

## Independent labels

`--labels CSV` scores the same lists against bug-inducing commits labelled by
someone else: ApacheJIT (Keshavarz and Nagappan, MSR 2022; 106,674 commits
across fourteen Apache repositories, SZZ plus six filters) in its own CSV
shape (a `commit_id` column and a `buggy` flag), Defectors (Mahbub, Shuvo and
Rahman, MSR 2023; 24 Python projects at file level) as rows of commit and
path, or a bare list of hashes. The outcome at T is then the source files a
labelled commit touched in the six months after T, the paths the label names
when it names them. For one ApacheJIT repository:

```bash
git clone https://github.com/apache/zookeeper && gitmole zookeeper --out analysis-zookeeper
python -m gitmole.evaluate zookeeper analysis-zookeeper --labels apachejit_total.csv
```

The datasets live on Zenodo (10.5281/zenodo.5907001 and 10.5281/zenodo.7708984),
which the environment this page was last regenerated in could not reach, so
the fourteen-repository table is not here yet; the command above is what
produces it, one repository at a time, and the labelled table prints under
the fix-locality one.

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

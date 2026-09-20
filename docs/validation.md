# Validation

What the watch list is worth, measured; back to [the README](https://github.com/antvinni/gitmole#readme).

The watch list is a heuristic. This page says how it did against what
happened next, on three repositories at the commits pinned in
`bin/render-examples`, and how other ways of ranking the same files did on
the same question. Regenerate any table with
`python -m gitmole.evaluate CLONE OUT_DIR`; `--szz` adds the tables against
bug-inducing commits further down.

## What the ranking is for

The watch list is churn weighted by size: a file's revisions times its
lines of code. Its purpose is to name the files most likely to be fixed in
the next six months, counted per file named. It does not try to find the
most bugs per line read. Measured on 20 September 2026 against the
same pool at the same six cut-offs (`python -m gitmole.measure.signals`),
on the development set (curl, django, react, Ghidra and binutils-gdb
against fix locality; gitmole's own history is too short for a cut-off)
and, once, on the thirteen held-out Apache repositories against ApacheJIT's
labels. The ApacheJIT table further down comes from an earlier release,
which classified the pool differently, so its totals differ from these:

| | development, top-15 hits | holdout, top-15 hits | ROC-AUC beats churn | recall at 20% of lines beats churn |
|---|---:|---:|---:|---:|
| watch list | 310 | 724 | 5 of 5, 13 of 13 | 0 of 5, 1 of 13 |
| churn | 289 | 704 | | |

- **At the head of the list it is churn.** It names a few more fixed files
  than churn alone: 21 more over five development repositories (three
  ahead, one behind, one level) and 20 more over thirteen held-out ones
  (eight ahead, four behind, one level). That is about 3%, and inside the
  noise of any one repository.
- **Over the whole pool it is better than churn.** Its ROC-AUC is higher
  on every repository in both sets (median 0.83 against 0.75 on
  development, 0.77 against 0.74 on the holdout). Size breaks the ties
  between files that changed equally often, and big files that change
  are fixed more often than small ones that change as much.
- **Per line read it is worse.** Read the list from the top until you
  have read 20% of the pool's lines. Churn alone reaches more of the
  fixed files that way on every development repository and on twelve of
  the thirteen held-out ones (median 0.13 against 0.09 on development,
  0.18 against 0.13 on the holdout). The size weight spends that budget
  on large files. Change entropy (HCM), which favours small, scattered
  files, does better still per line on development (median 0.18). If
  your budget is lines rather than files, sort the list by revisions.

Recency does not earn a place either. On development, counting only the
last twelve months of revisions beat the watch list on all five
repositories (336 against 310), and six-month windows, 24-month windows
and exponential decay did about as well (323 to 335). That variant was
chosen before the holdout was read, and there it came to 729 against 724:
ahead on six repositories and behind on seven. A 9% gain that shrinks to
under 1% on labels nobody tuned against is selection on five
repositories, so the ranking is unchanged. The intervals say the same: the
development headroom is 0.62 with a 95% interval of 0.36 to 0.93 over
repositories, too wide to show a gain of that size.

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

| variant | 2023-09-16 (17 of 26 fixed) | 2024-03-16 (55 of 979 fixed) | 2024-09-16 (73 of 1203 fixed) | 2025-03-16 (97 of 1299 fixed) | 2025-09-16 (107 of 1401 fixed) | 2026-03-16 (36 of 1421 fixed) | total |
|---|---:|---:|---:|---:|---:|---:|---:|
| watch list (hotspot) | 11 | 7 | 12 | 10 | 10 | 11 | 61 |
| factor product (max-scaled) | 11 | 5 | 7 | 10 | 7 | 8 | 48 |
| factor product (rank-scaled) | 12 | 7 | 11 | 11 | 9 | 8 | 58 |
| churn | 11 | 5 | 6 | 9 | 5 | 7 | 43 |
| size | 11 | 5 | 9 | 10 | 8 | 9 | 52 |
| recent fixes | 11 | 6 | 10 | 9 | 9 | 7 | 52 |
| change entropy (HCM) | 11 | 2 | 10 | 8 | 11 | 3 | 45 |
| random (expected) | 9.8 | 0.8 | 0.9 | 1.1 | 1.1 | 0.4 | 14.1 |

The first cut-off says nothing about ranking. react's compiler was developed in
its own repository and merged in later, so at 2023-09-16 the tree the backtest
checks out holds 26 scored files, all of the compiler, and a random fifteen of
them would name 9.8 of the 17 that were fixed. Every variant scores 11 or 12
there. The five later cut-offs are the ones that separate the lists.

`--all` exports 35,268 commits (4,501 fixes); HEAD reaches 21,703 (2,985 fixes).

## Totals

| variant | curl | django | react | total |
|---|---:|---:|---:|---:|
| watch list (hotspot) | 86 | 84 | 61 | 231 |
| factor product (max-scaled) | 86 | 78 | 48 | 212 |
| factor product (rank-scaled) | 87 | 78 | 58 | 223 |
| churn | 85 | 69 | 43 | 197 |
| size | 90 | 83 | 52 | 225 |
| recent fixes | 85 | 83 | 52 | 220 |
| change entropy (HCM) | 84 | 65 | 45 | 194 |
| random (expected) | 30.1 | 18.5 | 14.1 | 62.7 |

Of 270 possible: three repositories, six cut-offs, fifteen files.

## What the numbers say

Every list beats a random pick: by about three times on curl, four times on
django and four times on react, where react's first cut-off, with 26 files in
the pool, lifts every variant and the random baseline alike. Beyond that:

- **Revisions × lines of code does best**, 231 of 270: first on django (84,
  one ahead of size alone and of recent fixes), first on react (61, three
  ahead of the rank-scaled factor product and nine ahead of size), and on
  curl level with the max-scaled factor product, one ahead of churn and of
  recent fixes, one behind the rank-scaled product and four behind size
  alone. That is why the watch list ranks by it, and why fixes, complexity
  and ownership are the reasons printed beside a file and not part of its
  rank.
- **Size alone comes second**, 225: it takes curl outright (90 of 90) and is
  one behind on django, and react is where the watch list pulls away from it,
  by nine.
- **The rank-scaled factor product follows**, 223, and takes curl by one (87).
- **Recent fixes**, 220. A file fixed lately is likely to be fixed again;
  the list prints that count beside the file, right after how often it
  changed.
- **The max-scaled factor product trails**, 212: what 0.7 shipped, and the
  worst of the three on django (78) and react (48).
- **Churn alone**, 197. Its product with size, which is what the watch list
  ranks by, does better than either factor alone in total, though not on
  curl, where size alone is ahead.
- **Change entropy does not earn the rank**, 194: two behind the watch
  list on curl (84), nineteen behind on django (65) and sixteen on
  react (45), and behind size alone and recent fixes everywhere but curl.
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

| variant | 2023-09-16 (8 of 26 bug-inducing) | 2024-03-16 (16 of 979 bug-inducing) | 2024-09-16 (30 of 1203 bug-inducing) | 2025-03-16 (29 of 1299 bug-inducing) | 2025-09-16 (33 of 1401 bug-inducing) | 2026-03-16 (18 of 1421 bug-inducing) | total |
|---|---:|---:|---:|---:|---:|---:|---:|
| watch list (hotspot) | 5 | 5 | 6 | 5 | 4 | 7 | 32 |
| factor product (max-scaled) | 6 | 3 | 3 | 3 | 4 | 5 | 24 |
| factor product (rank-scaled) | 6 | 4 | 6 | 5 | 6 | 6 | 33 |
| churn | 6 | 3 | 2 | 3 | 1 | 3 | 18 |
| size | 5 | 4 | 5 | 4 | 4 | 7 | 29 |
| recent fixes | 6 | 4 | 7 | 5 | 4 | 5 | 31 |
| random (expected) | 4.6 | 0.2 | 0.4 | 0.3 | 0.4 | 0.2 | 6.1 |

### Totals, R-SZZ

| variant | curl | django | react | total |
|---|---:|---:|---:|---:|
| watch list (hotspot) | 56 | 62 | 32 | 150 |
| factor product (max-scaled) | 53 | 56 | 24 | 133 |
| factor product (rank-scaled) | 57 | 55 | 33 | 145 |
| churn | 55 | 50 | 18 | 123 |
| size | 61 | 66 | 29 | 156 |
| recent fixes | 55 | 59 | 31 | 145 |
| random (expected) | 8.5 | 9.2 | 6.1 | 23.8 |

Against defect insertion the order changes at the top: **size alone leads**,
61, 66 and 29 for 156 of 270, and the **watch list is second** at
150, ahead on react (32 against 29) and behind on curl and django by five and
four. The rank-scaled factor product and recent fixes follow at 145, the
max-scaled product at 133 and churn alone, last again, at 123; a random
fifteen would name 24. The reading: where a bug was planted is even more a
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

`--end DATE` counts the cut-offs back from a date other than the last
commit, since ApacheJIT's labels stop in December 2019. Under the labelled
table the evaluation prints what each list costs a reviewer: the initial
false alarms (IFA) before its first labelled file, and the lines of code its
top fifteen hold, the inspection budget. A ranking that favours small files
can score well on hits per line and still send a reviewer through many
files before one matters (arXiv 2504.19181), so both sit beside the hits.

### Thirteen Apache repositories, ApacheJIT labels

ApacheJIT's fourteen projects live in thirteen repositories (HDFS and
MapReduce are in apache/hadoop). Each was cloned on 18 September 2026, run
through gitmole, and evaluated with `--labels apachejit_total.csv --end
2019-12-31`: six cut-offs from 2016-12-31 to 2019-06-30, a six-month
horizon, the top fifteen. The labels come from the dataset's GitHub copy
(github.com/hosseinkshvrz/apachejit), since the environment this page was
regenerated in cannot reach Zenodo. Each cell is the labelled files a list
named, summed over the six cut-offs; the first row is how many labelled
files were in the pool the lists draw from.

| variant | activemq | camel | cassandra | flink | groovy | hadoop | hbase | hive | ignite | kafka | spark | zeppelin | zookeeper | total |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| labelled files in the pool | 40 | 844 | 757 | 2403 | 182 | 645 | 1805 | 2285 | 2831 | 1678 | 828 | 440 | 118 | 14856 |
| watch list (hotspot) | 8 | 20 | 59 | 68 | 19 | 42 | 75 | 84 | 89 | 80 | 39 | 57 | 34 | 674 |
| factor product (max-scaled) | 10 | 21 | 62 | 74 | 17 | 45 | 73 | 81 | 88 | 85 | 38 | 60 | 34 | 688 |
| factor product (rank-scaled) | 8 | 15 | 42 | 33 | 22 | 25 | 52 | 69 | 47 | 77 | 30 | 58 | 25 | 503 |
| churn | 8 | 22 | 62 | 69 | 13 | 46 | 75 | 81 | 86 | 81 | 37 | 58 | 36 | 674 |
| size | 10 | 21 | 53 | 42 | 26 | 35 | 69 | 75 | 78 | 78 | 31 | 53 | 26 | 597 |
| recent fixes | 8 | 18 | 42 | 55 | 17 | 18 | 59 | 62 | 85 | 70 | 32 | 54 | 27 | 547 |
| change entropy (HCM) | 3 | 19 | 45 | 65 | 15 | 26 | 68 | 74 | 78 | 81 | 42 | 59 | 25 | 600 |
| random (expected) | 0.7 | 2.7 | 8.2 | 12.9 | 2.6 | 2.5 | 13.9 | 10.1 | 11.2 | 22.8 | 6.4 | 17.2 | 8.8 | 120 |

| variant | IFA, median over repositories | lines of code in the list, median over repositories |
|---|---:|---:|
| watch list (hotspot) | 0 | 22,462 |
| factor product (max-scaled) | 0 | 19,180 |
| factor product (rank-scaled) | 0.5 | 13,946 |
| churn | 0 | 18,573 |
| size | 1 | 27,370 |
| recent fixes | 0 | 13,265 |
| change entropy (HCM) | 0 | 11,927 |

Against labels nobody at gitmole chose, the **watch list names 674
labelled files, 5.6 times what a random fifteen would (120)**. It ties churn
alone (674) and trails the max-scaled factor product it replaced in 0.8 by
fourteen (688, 2%). Change entropy (600), size (597), recent fixes (547) and
the rank-scaled product (503) follow. The order differs from the three
example repositories, where size led against R-SZZ: in these Java-heavy
projects the labels follow change more than size, and the watch list, which
multiplies the two, sits with the change-led lists. The median list sends a
reviewer to a labelled file first (IFA 0) whichever variant ranks it, so the
cost difference is in lines: the watch list's fifteen hold a median of
22,462 lines against 18,573 for churn alone. The watch list keeps its
ranking: it ties the best simple list here, it is ahead of churn on the
example repositories against both fix locality and R-SZZ, and it does not
need the fix labels the factor product leans on. Defectors (24 Python
projects) is still not here; its data is only on Zenodo.

## The hook's coupling warning

`--hook` and `--risk` warn when a change leaves out a file that usually
changes with one it touched. The warning is judged by ROSE's two
experiments (Zimmermann et al., TSE 2005, sections 7.5 and 7.6), with
coupling taken from the history before each of three anchors, six months
apart, and the queries from the two months after each:

- **Precision.** Leave one file out of each commit that touches between
  two and twenty scored files, and count how often the warning names the
  file that was left out.
- **Feedback.** Count how often the warning speaks at all.
- **False alarms.** Count how many complete commits get a warning, where
  every warning is a false alarm.

Until 0.29 a companion was any file that changed together with the
touched one at least 50% of the time (the symmetric degree, over the
average of the two files' changes) over at least five shared changes. On
the development set that warning was right a quarter of the time, and on
react it fired on a third of complete commits. Eighteen thresholds were
tried on the development set: the symmetric degree at 50, 70 and 90, and
ROSE's directed confidence at 0.5, 0.7 and 0.9 (the share of the touched
file's changes that also moved the companion), each over at least 5, 10
or 20 shared changes. The rule was set before the numbers were read. The
warning stays only if some threshold reaches a median precision of 0.5,
with at most 10% of complete commits alarmed and a warning on at least 5%
of queries. Otherwise the warning goes. Directed confidence of 0.7 over
twenty or more shared changes came first (median over five repositories):

| | precision | complete commits alarmed | queries warned |
|---|---:|---:|---:|
| degree 50%, 5 shared (until 0.29), development | 0.26 | 10% | 14% |
| confidence 70%, 20 shared, development | 0.60 | 3% | 9% |
| degree 50%, 5 shared, holdout | 0.29 | 14% | 21% |
| confidence 70%, 20 shared, holdout | 0.49 | 4% | 8% |
| as shipped, development | 0.62 | 4% | 10% |
| as shipped, holdout | 0.54 | 3% | 7% |

It was then read once on the thirteen held-out Apache repositories, which
need no labels for this. There it was right about half the time (0.49 at
the median, 0.50 pooled over all 1,258 warnings): short of the
development number and just short of the 0.5 bar, but 0.2 better than
the old threshold, with a third of the false alarms. The shipped code
differs from the sweep in two ways. It counts logical changesets, as the
coupling table does, where the sweep counted raw commits. And a companion
must be a scored source file. Without that rule, every binutils-gdb change
"left out" a ChangeLog, which every commit touched until 2021, and 75% of
complete commits there raised an alarm. Replayed with the shipped code,
the warning is right 62% of the time on the development set and 54% on the
holdout (0.52 pooled over 1,056 warnings), and 3% of complete commits
raise an alarm; ROSE reported 66% at function granularity. `python -m
gitmole.measure extras` replays it on the development set with every
release.

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

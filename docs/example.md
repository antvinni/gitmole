# Full example report

The complete `gitmole .` report for this repository; the README shows its first two panels; back to [the README](https://github.com/antvinni/gitmole#readme).

Running `gitmole .` inside this repository:

```text
╭─ gitmole ────────────────────────────────────────────────────────────────────────────────────────╮
│ 115 commits  ·  2026-09-15 → 2026-09-16  ·  1 identity  ·  branch main                           │
│ 6,944 lines in 44 files  ·  Python, Ruby                                                         │
│ most commits on Wed at 20:00  ·  3% of commits are fixes  ·  100% of surviving code from 2026    │
│ 3 warnings, 1 note                                                                               │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
╭─ Findings (4) ───────────────────────────────────────────────────────────────────────────────────╮
│ ▲ Bus factor of one                                                                              │
│   vinni wrote 100% of the code that survives today                                               │
│   ↳ Pair someone with vinni on gitmole/ and build/ first; they are 100% and 100% theirs.         │
│ ▲ Hotspots getting more complex                                                                  │
│   4 of the 10 top source hotspots grew by 25% or more in a year: gitmole/render.py (+150%),      │
│   gitmole/cli.py (+32%), gitmole/findings.py (+266%), gitmole/run.py (+26%)                      │
│   ↳ Split gitmole/render.py before the next change; its complexity grew 150% in a year.          │
│ ▲ Knowledge islands                                                                              │
│   2 area(s) with at least 200 lines were written almost entirely by one person: gitmole/ (vinni  │
│   100%); build/ (vinni 100%). That is 97% of all lines added                                     │
│   ↳ Pair someone with vinni on gitmole/ first; it is the largest at 5,458 lines.                 │
│ ● Bug magnets                                                                                    │
│   1 file(s) were fixed 3+ times in the last six months: gitmole/run.py (3 recent, 3 total)       │
│   ↳ Review gitmole/run.py before the next release; expect the next bug there.                    │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯

◎ Watch list
  file                  why
  ──────────────────────────────────────────────────────────────────────────────────────────────────
  gitmole/render.py     changed 38 times · fixed twice in six months · only vinni has touched it ·
                        hotspots_section() complexity 23 · changes with gitmole/cli.py (63%) and 3
                        others
  gitmole/cli.py        changed 38 times · fixed twice in six months · only vinni has touched it ·
                        main() complexity 17 · changes with gitmole/render.py (63%) and 1 other
  gitmole/run.py        changed 25 times · fixed 3 times in six months · only vinni has touched it ·
                        collect_meta() complexity 23 · changes with gitmole/load.py (67%) and 2
                        others
  gitmole/findings.py   changed 25 times · fixed twice in six months · only vinni has touched it ·
                        complexity_growth() complexity 18 · changes with gitmole/load.py (62%) and 1
                        other
  gitmole/load.py       changed 17 times · fixed twice in six months · only vinni has touched it ·
                        parse_git_sizer() complexity 15 · changes with gitmole/run.py (67%) and 2
                        others
  ranked by churn × recent fixes × complexity × single ownership
  too little history to backtest

◉ People
  author      commits   share                surviving code
  ─────────────────────────────────────────────────────────
  vinni           114   100% ▰▰▰▰▰▰▰▰▰▰                100%
  bots left out: github-actions[bot] (1 commits)
  aliases merged for vinni; a .mailmap makes that permanent

⌂ Knowledge map
  area       lines added   main owner     second
  ────────────────────────────────────────────────────────────────
  tests/           6,009   vinni (100%)   -
  gitmole/         5,458   vinni (100%)   -
  build/           1,681   vinni (100%)   -
  Formula/           121   vinni (98%)    github-actions[bot] (2%)
  bin/                94   vinni (100%)   -

▦ Timeline (Oct 2025 → Sep 2026)
  author   Oct   Nov   Dec   Jan   Feb   Mar   Apr   May   Jun   Jul   Aug   Sep
  ──────────────────────────────────────────────────────────────────────────────
  vinni      ·     ·     ·     ·     ·     ·     ·     ·     ·     ·     ·   114

◆ Hotspots
  file                  revs   lines   fixes   authors   trend
  ────────────────────────────────────────────────────────────
  gitmole/render.py       38     569       2         1   +150%
  gitmole/cli.py          38     349       2         1    +32%
  gitmole/findings.py     25     305       2         1   +266%
  gitmole/run.py          25     302       3         1    +26%
  gitmole/maat.py         15     228       2         1       -
  gitmole/load.py         17     194       2         1       -
  gitmole/watch.py         7     132       1         1       -
  gitmole/banner.py        8      84       1         1       -
  and 28 more; 22 test files hidden; --full shows them

⟷ Change coupling
  file                    changes with          degree
  ────────────────────────────────────────────────────
  gitmole/load.py         gitmole/run.py           67%
  gitmole/cli.py          gitmole/render.py        63%
  gitmole/cli.py          gitmole/run.py           63%
  gitmole/render.py       gitmole/run.py           63%
  gitmole/findings.py     gitmole/load.py          62%
  and 12 more; 55 test pairs hidden; --full shows them

λ Complex functions
  function              file                  ccn   lines   params
  ────────────────────────────────────────────────────────────────
  hotspots_section      gitmole/render.py      23      27        3
  collect_meta          gitmole/run.py         23      27        2
  risks                 gitmole/watch.py       22      32        2
  timeline_section      gitmole/render.py      22      16        4
  functions_section     gitmole/render.py      20      25        3
  markdown              gitmole/render.py      19      24        5
  execute               gitmole/run.py         18      37        8
  people_section        gitmole/render.py      18      24        3
  and 35 more; 2 functions in test files hidden; --full shows them

✚ Repo health (git-sizer concerns): nothing flagged

Secrets: none found
Full results and plots in analysis-gitmole
```

In a terminal the banner heads the run: the letters pulse in neon,
the pixel mole beside them glances side to side while the tools work, and
the findings and tables are coloured: section headings in the banner's cyan,
column headers in its violet, one key column per table in full white with
the rest dimmed, inline bars on share columns, and values past a threshold
(a share over 50%, coupling at 90%, five fixes) in pink. On a terminal 100
columns or wider the small tables sit side by side. Piped output, as above,
is plain text.
This is the default report: the header, the findings, the watch list, and
the tables that point at a file or a person. `--full` adds the descriptive
tables the header summarises in one line (size by language, activity by
weekday with the busiest hour, surviving code by year), complexity, score
and idle months to hotspots, emails to people, average revisions to
coupling, the author count to the knowledge map, and lifts the row caps.
The Markdown export keeps every table and column but caps each table at 50
rows unless `--full`.

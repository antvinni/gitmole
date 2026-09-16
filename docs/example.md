# Full example report

The complete `gitmole .` report for this repository, shown in the README as an excerpt; back to [../README.md](../README.md).

Running `gitmole .` inside this repository:

```text
╭─ gitmole ────────────────────────────────────────────────────────────────────────────────────────╮
│ 105 commits  ·  2026-09-15 → 2026-09-16  ·  1 identity  ·  branch main                           │
│ 6,592 lines in 44 files  ·  Python, Shell                                                        │
│ most commits on Wed at 13:00  ·  7% of commits are fixes  ·  100% of surviving code from 2026    │
│ 4 warnings                                                                                       │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
╭─ Findings (4) ───────────────────────────────────────────────────────────────────────────────────╮
│ ▲ Bus factor of one                                                                              │
│   vinni wrote 100% of the code that survives today                                               │
│   ↳ Pair someone with vinni on gitmole/ and build/ first; they are 100% and 100% theirs.         │
│ ▲ Bug magnets                                                                                    │
│   4 file(s) were fixed 3+ times in the last six months: gitmole/load.py (5 recent, 5 total);     │
│   gitmole/render.py (4 recent, 4 total); gitmole/findings.py (3 recent, 3 total); gitmole/run.py │
│   (3 recent, 3 total)                                                                            │
│   ↳ Review gitmole/load.py and gitmole/render.py before the next release; expect the next bug    │
│   there.                                                                                         │
│ ▲ Hotspots getting more complex                                                                  │
│   3 of the 10 top source hotspots grew by 25% or more in a year: gitmole/render.py (+134%),      │
│   gitmole/run.py (+26%), gitmole/findings.py (+262%)                                             │
│   ↳ Split gitmole/render.py before the next change; its complexity grew 134% in a year.          │
│ ▲ Knowledge islands                                                                              │
│   2 area(s) with at least 200 lines were written almost entirely by one person: gitmole/ (vinni  │
│   100%); build/ (vinni 100%). That is 99% of all lines added                                     │
│   ↳ Pair someone with vinni on gitmole/ first; it is the largest at 6,800 lines.                 │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯

◎ Watch list
  file                  why
  ──────────────────────────────────────────────────────────────────────────────────────────────────
  gitmole/render.py     changed 50 times · fixed 4 times in six months · only vinni has touched it ·
                        timeline_section() complexity 22 · changes with gitmole/cli.py (69%) and 3
                        others
  gitmole/run.py        changed 39 times · fixed 3 times in six months · only vinni has touched it ·
                        collect_meta() complexity 23 · changes with gitmole/cli.py (71%) and 3
                        others
  gitmole/findings.py   changed 29 times · fixed 3 times in six months · only vinni has touched it ·
                        knowledge_loss() complexity 34 · changes with gitmole/render.py (58%) and 1
                        other
  gitmole/cli.py        changed 37 times · fixed once in six months · only vinni has touched it ·
                        _analyse() complexity 35 · changes with gitmole/run.py (71%) and 1 other
  gitmole/load.py       changed 25 times · fixed 5 times in six months · only vinni has touched it ·
                        parse_git_sizer() complexity 15 · changes with gitmole/run.py (66%) and 2
                        others
  ranked by churn × recent fixes × complexity × single ownership
  too little history to backtest

◉ People
  author      commits   share                surviving code
  ─────────────────────────────────────────────────────────
  vinni           105   100% ▰▰▰▰▰▰▰▰▰▰                100%
  aliases merged for vinni; a .mailmap makes that permanent

⌂ Knowledge map
  area       lines added   main owner     second
  ──────────────────────────────────────────────
  tests/           7,489   vinni (100%)   -
  gitmole/         6,800   vinni (100%)   -
  build/           3,362   vinni (100%)   -
  bin/                91   vinni (100%)   -

▦ Timeline (Oct 2025 → Sep 2026)
  author   Oct   Nov   Dec   Jan   Feb   Mar   Apr   May   Jun   Jul   Aug   Sep
  ──────────────────────────────────────────────────────────────────────────────
  vinni      ·     ·     ·     ·     ·     ·     ·     ·     ·     ·     ·   105

◆ Hotspots
  file                     revs   lines   fixes   authors   trend
  ───────────────────────────────────────────────────────────────
  tests/test_render.py       49     684       4         1   +738%
  gitmole/render.py          50     545       4         1   +134%
  tests/test_run.py          38     476       3         1    +46%
  tests/test_cli.py          34     522       0         1    +58%
  tests/test_findings.py     28     460       3         1   +400%
  gitmole/run.py             39     302       3         1    +26%
  gitmole/cli.py             37     313       1         1    +24%
  gitmole/findings.py        29     293       3         1   +262%
  and 49 more

⟷ Change coupling
  file                   changes with              degree
  ───────────────────────────────────────────────────────
  gitmole/maat.py        tests/test_maat.py          100%
  gitmole/filetypes.py   tests/test_filetypes.py     100%
  gitmole/functions.py   tests/test_functions.py     100%
  gitmole/knowledge.py   tests/test_knowledge.py     100%
  gitmole/render.py      tests/test_render.py         99%
  and 85 more

λ Complex functions
  function           file                  ccn   lines   params
  ─────────────────────────────────────────────────────────────
  _analyse           gitmole/cli.py         35      66        6
  knowledge_loss     gitmole/findings.py    34      44        3
  main               gitmole/cli.py         28      82        8
  collect_meta       gitmole/run.py         23      27        2
  risks              gitmole/watch.py       22      32        2
  timeline_section   gitmole/render.py      22      16        4
  hotspots_section   gitmole/render.py      21      25        3
  markdown           gitmole/render.py      19      24        5
  and 34 more

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

# Full example report

The complete `gitmole .` report for this repository; the README shows its first two panels; back to [the README](https://github.com/antvinni/gitmole#readme).

Running `gitmole .` inside this repository:

```text
╭─ gitmole ────────────────────────────────────────────────────────────────────────────────────────╮
│ 185 commits  ·  2026-09-15 → 2026-09-17  ·  1 identity  ·  branch main                           │
│ 9,475 lines in 52 files  ·  Python, Ruby                                                         │
│ most commits on Wed at 20:00  ·  4% of commits are fixes  ·  100% of surviving code from 2026    │
│ 3 warnings, 1 note                                                                               │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
╭─ Findings (4) ───────────────────────────────────────────────────────────────────────────────────╮
│ ▲ Bus factor of one                                                                              │
│   vinni wrote 100% of the code that survives today                                               │
│   ↳ Pair someone with vinni on gitmole/ first; it is 100% theirs.                                │
│ ▲ Hotspots getting more complex                                                                  │
│   4 of the 10 top source hotspots grew by 25% or more in a year: gitmole/render.py (+194%),      │
│   gitmole/findings.py (+360%), gitmole/cli.py (+64%), gitmole/run.py (+34%)                      │
│   ↳ Split gitmole/render.py before the next change; its complexity grew 194% in a year.          │
│ ▲ Knowledge islands                                                                              │
│   1 area(s) with at least 200 lines were written almost entirely by one person: gitmole/ (vinni  │
│   100%). That is 98% of all lines added                                                          │
│   ↳ Pair someone with vinni on gitmole/ first; it is the largest at 7,607 lines.                 │
│ ● Bug magnets                                                                                    │
│   5 file(s) were fixed 3+ times in the last six months: gitmole/load.py (4 recent, 4 total);     │
│   gitmole/cli.py (3 recent, 3 total); gitmole/findings.py (3 recent, 3 total); gitmole/render.py │
│   (3 recent, 3 total); gitmole/run.py (3 recent, 3 total)                                        │
│   ↳ Review gitmole/load.py and gitmole/cli.py before the next release; expect the next bug       │
│   there.                                                                                         │
│ ✔ No secrets in history                                                                          │
│   betterleaks scanned every commit on every branch; 28 placeholder-shaped hits left out          │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯

◎ Watch list
  file                  why
  ──────────────────────────────────────────────────────────────────────────────────────────────────
  gitmole/render.py     changed 57 times · fixed 3 times in six months · only vinni has touched it ·
                        knowledge_section() complexity 25 · changes with gitmole/findings.py (69%)
                        and 1 other
  gitmole/findings.py   changed 48 times · fixed 3 times in six months · only vinni has touched it ·
                        tight_coupling() complexity 26 · changes with gitmole/render.py (69%) and 1
                        other
  gitmole/cli.py        changed 47 times · fixed 3 times in six months · only vinni has touched it ·
                        _clean() complexity 24 · changes with gitmole/render.py (52%) and 1 other
  gitmole/run.py        changed 35 times · fixed 3 times in six months · only vinni has touched it ·
                        collect_meta() complexity 24 · changes with gitmole/load.py (56%) and 1
                        other
  gitmole/load.py       changed 29 times · fixed 4 times in six months · only vinni has touched it ·
                        load_report() complexity 17 · changes with gitmole/run.py (56%)
  ranked by churn × recent fixes × complexity × single ownership
  too little history to backtest

◉ People
  author      commits   share                surviving code
  ─────────────────────────────────────────────────────────
  vinni           166   100% ▰▰▰▰▰▰▰▰▰▰                100%
  bots left out: github-actions[bot] (19 commits)
  aliases merged for vinni; a .mailmap makes that permanent

⌂ Knowledge map
  area       lines added   main owner     second
  ──────────────────────────────────────────────
  tests/           8,746   vinni (100%)   -
  gitmole/         7,607   vinni (100%)   -
  Formula/           123   vinni (100%)   -
  2 historical areas hidden; --full shows them

▦ Timeline (Oct 2025 → Sep 2026)
  author   Oct   Nov   Dec   Jan   Feb   Mar   Apr   May   Jun   Jul   Aug   Sep
  ──────────────────────────────────────────────────────────────────────────────
  vinni      ·     ·     ·     ·     ·     ·     ·     ·     ·     ·     ·   166

◆ Hotspots
  file                                     revs        lines        fixes         authors      trend
  ──────────────────────────────────────────────────────────────────────────────────────────────────
  gitmole/render.py                          57          686            3               1      +194%
  gitmole/findings.py                        48          420            3               1      +360%
  gitmole/cli.py                             47          415            3               1       +64%
  gitmole/run.py                             35          326            3               1       +34%
  gitmole/load.py                            29          225            4               1          -
  gitmole/maat.py                            21          244            2               1          -
  gitmole/filetypes.py                       21          145            0               1          -
  gitmole/leaks.py                           17          128            0               1          -
  and 15 more; 24 test files hidden; 14 deleted files hidden; 1 release file hidden; --full shows
  them

⟷ Change coupling
  file                    changes with           degree
  ─────────────────────────────────────────────────────
  gitmole/findings.py     gitmole/render.py         69%
  gitmole/load.py         gitmole/run.py            56%
  gitmole/filetypes.py    gitmole/findings.py       55%
  gitmole/__init__.py     gitmole/filetypes.py      55%
  gitmole/filetypes.py    gitmole/identity.py       53%
  and 33 more; 108 test pairs hidden; --full shows them

λ Complex functions
  function             file                   ccn   lines   params
  ────────────────────────────────────────────────────────────────
  tight_coupling       gitmole/findings.py     26      27        3
  knowledge_section    gitmole/render.py       25      25        3
  _clean               gitmole/cli.py          24      37        3
  risks                gitmole/watch.py        24      34        2
  collect_meta         gitmole/run.py          24      28        2
  hotspots_section     gitmole/render.py       23      32        3
  timeline_section     gitmole/render.py       22      16        4
  main                 gitmole/cli.py          21      54        9
  and 51 more; 2 functions in test files hidden; --full shows them

✚ Repo health (git-sizer concerns): nothing flagged

Secrets: none found; 28 placeholder-shaped hits left out
Dependencies: no lock files found
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

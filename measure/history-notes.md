## What the history shows

- **The ranking improved once, at 0.8.0, and has held since.** Releases 0.2.0 to 0.7.0 ranked by a factor
  product and barely changed its code; their headroom is 0.73 to 0.77, a little above churn alone (0.71 to
  0.75), with 9 wins, 1 loss and 8 ties against it over eighteen cut-offs. 0.8.0 switched to revisions ×
  lines of code and read the checked-out branch's history instead of every ref's: headroom 0.92, 13 wins, no loss and 5 ties, ROC-AUC 0.76 to 0.81. With three development
  repositories the intervals are wide (0.60 to 0.94 at 0.8.0), and 0.92 sits inside 0.7.0's interval, so by
  this page's own rule it is not yet a counted move; it is the largest change in the history and the one the
  holdout was run to check.
- **The price of that ranking is reading effort.** Recall at 20% of the lines fell from 44% to 30% at 0.8.0,
  since a size-weighted list names large files first, and rose to 38% at 0.10.0, when one classifier began
  deciding for every table which files enter the pool.
- **Everything since 0.11.0 added output rather than effectiveness.** From 0.11.0 to 0.25.0 the ranking
  numbers do not move; findings per repository grew from 10.5 to 16 (median) and from 13.4 to 21.8 (p90), and
  the report from about 212 to 258 lines. That is the cost side of the new rules, which the page's noise
  budget asks to be conscious of.
- **The gate caught all three of its cases from 0.15.0,** when the Trojan Source and submodule checks
  arrived; before that it caught the committed key only.
- **Peak memory tripled at 0.15.0,** from about 850 MB to about 3 GB on react. The per-step records 0.26.0
  added put it in the secrets step (betterleaks peaks at 2,994 MB there), which 0.15.0 extended to the
  objects no ref reaches. jscpd's duplicate search is next at about 1 GB. Run time grew from about 200 to 285
  seconds for the three development repositories.
- **Robustness has one standing failure and one since 0.8.0.** Every release crashes on an empty
  repository (`git log` fails before the first commit), and from 0.8.0 git-sizer fails on a shallow clone.
  0.26.0 added a third: its per-step wrapper ran as `python -m`, which searches the analysed repository first,
  so on gitmole's own history every step imported that repository's older gitmole and failed. The measurement
  found it; the release after 0.26.0 fixes it. 0.28.0 fixes the other two: an empty repository is refused
  with exit code 2 and a one-line reason, and a shallow clone skips git-sizer and says why, so robustness
  is 21 of 21.
- **Stability reads 1.00 in every release.** Fifty commits span three days on curl and at most seven weeks on
  react, too short for the top fifteen to change; the measure needs a longer horizon to say anything.
- **No release crashed on a development repository,** so no point sits at the bottom of the graphs.
- **0.26.0's small ranking change is the UTC fix.** Its backtest cuts off at a UTC midnight rather than the
  machine's, which moves a handful of commits across each cut-off: 12 wins and 6 ties instead of 13 and 5,
  recall at 20% 45% instead of 38%.
- **The current release's own checks** (the dashboard at the end of this page): determinism holds across a
  time zone and a locale; every description check agrees (signing is not checked, since gpg was not
  installed); of 50 numeric thresholds 21 are flat, 21 never fire on these repositories and 6 are fragile,
  `tight_coupling`'s 80 among them, which keeps its count at ±10% but names different files. The hook's
  coupling warning is the weakest result here: at file granularity its precision is 0% on django, 17% on
  curl and 43% on react, and on react it warns on a third of complete commits, where every warning is a
  false alarm. ROSE reported 66% precision at function granularity, so the hook's warning does not yet
  earn the ROSE figure its docstring cites.
- **The holdout says the development set flatters the ranking.** 0.26.0 was run once over the thirteen
  ApacheJIT repositories, scored against their independent labels: median headroom 0.61 (interval 0.34 to
  0.80) against 0.93 on the development set, and against churn alone 23 wins, 19 losses and 36 ties, close
  to a draw. Recall at 20% of the lines is 40%. The development set, where the thresholds were chosen, is
  the optimistic end.
- **The gate fires on well-kept projects.** Three of the four CNCF graduated projects got a critical: etcd
  for private keys in files named `*.key.insecure` under `hack/scripts-dev/`, containerd for a `password`
  field in generated protobuf code, prometheus for key-shaped strings in `cmd/tsdb/testdata.20k`. None is
  labelled yet, but on a first reading each is a fixture or generated code, which would put the false
  alarm rate at three in four where the page asks for near zero. This is the most urgent thing the
  measurement found. The labels confirmed all three, and 0.28.0 is at none of four (below).
- **0.28.0's headroom fell because the development set widened, not because the ranking changed.**
  Ghidra and binutils-gdb joined curl, django and react (measure/corpus.json, moves), so that intervals
  over repositories could narrow. On the three original repositories every number is the same as in
  0.27.0 (curl 0.93, django 0.93, react 0.62). Ghidra (0.36, 2 wins and 3 losses against churn) and
  binutils-gdb (0.55) bring the median to 0.62, with an interval of 0.36 to 0.93, and churn's to 0.52.
  The run time of the set rose from 284 to 674 seconds for the same reason; binutils-gdb alone takes six
  minutes. Compare 0.28.0 onwards with each other, not with the rows above it.
- **0.28.0 acted on the measurement rather than adding rules.** The 0.28.0 findings sheet was labelled
  (182 findings, one labeller). Three rules came out broken: `secrets_in_source`, `secrets_possible` and
  `trojan_source`. The false alarms behind them were a documentation URI, a CI database password, right-to-left
  marks in Arabic locale strings, and the bytes of a generated protobuf descriptor. Each was retuned by
  shape, and `hotspot_dominance`, which never fired, was deleted. The criticals went from 3 of 4 well-kept
  repositories to none. On the development set only react keeps one: a token-shaped string in an
  unreachable blob, which has no path that would say what it is. The gate still catches 3 of 3.
  Findings per repository fell from 19.5 to 18.5 (median), and the report from 296 to 278 lines.
- **What the ranking is for** is now said plainly in validation.md: churn weighted by size. At the top
  it is a few files ahead of churn, over the whole pool it is better (ROC-AUC), and per line read it is
  worse. A twelve-month recency variant won on the development set and drew on the holdout, so it was
  not shipped.
- **Peak memory is highest on prometheus,** about 4 GB, in the well-kept set, which the memory graph does not
  plot. The graph plots the development set, where react's 3 GB is still the peak.
- **0.29.0 retuned the hook's coupling warning rather than cutting it.** A companion is now a scored source
  file that moved in at least 70% of the touched file's changesets, over at least twenty of them (ROSE's
  directed confidence), where it was any file changing with it half the time by the symmetric degree. It
  was chosen among eighteen thresholds on the development set, then read once on the thirteen held-out
  repositories: precision 0.26 -> 0.60 on development and 0.29 -> 0.49 on the holdout, and complete commits
  alarmed 10% -> 3% and 14% -> 4%. As shipped, counting changesets and naming only scored source files, it
  is right 62% of the time on development and 54% on the holdout, with 3% of complete commits alarmed; see
  validation.md. Companions have to be scored files because of binutils-gdb: over the full history, every
  change there once touched a ChangeLog, and 75% of its complete commits alarmed until that rule was added.
- **0.29.0's other changes follow the labels.** A README heading about security is the policy a project
  points to (containerd). A stylesheet's `@import` loads an npm package (prometheus). A generated marker
  below a licence header counts (Ghidra's Bison and flex parsers). The rest of the parked classification
  work has no labelled finding behind it and stays parked.
- **The osv-scanner step holds prometheus's peak,** 4 GB, not gitmole: osv-scanner 2.6 keeps about 1.3 GB
  live per Go module with a large dependency graph (`documentation/examples/remote_storage/go.mod`), offline
  and with or without `--no-resolve`. A Go memory limit and a single thread do not lower it. gitmole's own
  steps stay under 1.1 GB.
- **Stability over 50 commits is joined by carry-over across six months** from 0.29.0, the half of the
  question fifty commits cannot answer. Its first reading is 0.94: from one cut-off to the next, six months
  later, the top fifteen keeps nearly all its files (0.90 on curl and Ghidra, 1.00 on binutils-gdb). A list
  ranked by whole-history revisions × lines hardly moves in half a year. The recency variant that would
  move it did not beat it on the holdout (validation.md), so this is what the ranking is, not a fault to fix.
- **Ghidra's brain methods no longer lead with the Bison parser** (`slghparse.cc`'s `yyparse`), the one
  labelled finding the deeper generated markers answer: 241 functions where there were 250. containerd
  loses its false `repo_policy` finding. Nothing else in the record moved.
- **0.30.0 asked whether the findings are worth acting on, not only whether they are true.** Nine rules
  whose labelled findings were all true and none actionable (repository health, knowledge loss, authors
  gone, minor contributors, reverts, duplication, stale files, component coupling, secrets only in tests)
  are now named in one line of the default report. The report spells out 7.5 findings per repository where
  it spelled out 18.5, and runs 220 lines where it ran 278. Of what it spells out, 69% is labelled
  actionable, where it was 31%. That jump is by construction: the nine rules were chosen from these same
  labels on these same repositories, so it shows the mechanism works, not that the report became more
  useful in general. The test is labels the set was not chosen from, a second labeller's sample
  (`measure/labels-second.jsonl`) and new findings on new repositories. Every label so far is one
  labeller's, and that labeller wrote the rules.
- **The long graphs now draw every release over the same four repositories** (curl, django, react and
  gitmole), so the fall in headroom at 0.28.0 and the jump in run time, both from Ghidra and binutils-gdb
  joining the development set, no longer show as moves. On the four, headroom is 0.93 and run time about
  275 seconds from 0.26.0 to 0.30.0. The table above and the dashboard below still use the whole set.
- **0.30.1 fixed three classifications without adding a rule** (the first patch release under the written
  semver rule in development.md). A `packages/` inside a top-level directory is vendored only when no
  workspace manifest declares it, so react's `compiler/packages/` is react's own code again: the scored
  share of the development set rose from 21% to 23%, react's watch list names the compiler, and its
  backtest at the 2023-09 cut-off, where the merged-in compiler history is all the tree has, scores 26
  files where it scored none. Headroom 0.62 and carry-over 0.94 -> 0.90 move only through react. An ELF
  relocatable object is not an executable (Ghidra's two `.elf` disassembler inputs; six DLLs remain).
  Identities merge by what the history's own names say instead of a list of common first names: a word
  two people's full names share (David Smith, David Sanders), or a bare given name (Jack, George), no
  longer joins anyone by name alone. Over the 23 measurement clones that splits about 280 groups the list
  let through (binutils-gdb's five Jasons, django's Thomases and Jannis Leidel's 895 commits beside
  Jannis Vajen's) and makes two wrong merges, a lowercase `steve` joining the one Steve of django and of
  kafka. 22 findings whose wording changed were labelled; each kept its verdict.
- **Report length was measured in a forced terminal all along.** Every record from 0.2.0 to 0.30.0 ran
  with `FORCE_COLOR` inherited from the shell that started it, so the report printed its banner and 80
  columns whatever `COLUMNS` said. A run started without it printed 11 lines fewer for the same code.
  From 0.30.1 the harness sets the terminal itself, and the length column says "80 columns, banner
  included", which is what it always measured.
- **0.31.0 pins the toolchain and moves nothing else.** Every number in the record is the same as 0.30.1's
  on every repository, which is what a release that only fixes where the tools come from should look like.
  What it changes is what a record means: the tools are installed with gitmole at the versions
  `gitmole/tools.py` names, so a row of this table now describes one toolchain rather than whichever
  versions the machine happened to have. Records before it say which versions ran (`run.tools`) but were
  measured against whatever Homebrew had that week, so a report-shaping change in scc, betterleaks or
  jscpd is a possible cause for any move in the rows above this one.

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
  on every repository, findings, ranking, robustness and the gate alike; only the wall time (689 s against
  718) and peak memory (3,034 MB against 2,889) differ, and those vary between runs on one machine. That is
  what a release that only fixes where the tools come from should look like.
  What it changes is what a record means: the tools are installed with gitmole at the versions
  `gitmole/tools.py` names, so a row of this table now describes one toolchain rather than whichever
  versions the machine happened to have. Records before it say which versions ran (`run.tools`) but were
  measured against whatever Homebrew had that week, so a report-shaping change in scc, betterleaks or
  jscpd is a possible cause for any move in the rows above this one.
- **0.32.0 turns the structure step on, and the measurement found what that cost.** The tree-sitter grammars
  ship with gitmole, so the step that reads nesting, debt markers and the import graph runs on every install
  with Python 3.10 or newer, and the seven rules behind it reach the measurement for the first time. They add
  one to six findings per repository, 35 over the set, and every one of them is on the findings sheet rather
  than in the default report: no label has reached these rules, so the report names them in a line of its own
  ("2 more from the structure step, not labelled yet") and the actionable share still measures only what it
  spells out. The watch list does change, for the better: a file's reasons now include what the parser saw
  (`http_rw_hd() nested 7 deep`) in place of a weaker one. The cost is two to eight report lines per
  repository, 13 seconds over the whole set (689 to 702) and no measurable memory: the step runs beside the
  others, not after them. Ghidra pays the most, 39 seconds to 46.
- **Running it everywhere cost three fixes, none of which a test had caught.** The step had been opt-in, so
  nothing had ever run it on an awkward input or under the determinism check. `structure._blobs` passed every
  tracked path to `git ls-files`, about 1.4 MB of arguments for Ghidra's 12,000 deep Java paths where macOS
  allows 1 MB, so the step died with "Argument list too long" on the repository it matters most for, and an
  empty path list made git list the whole index, which is how the binary-only fixture met a `.bin` and
  crashed. A path git hands over as surrogate escapes reached the JSON export, which writes UTF-8, and killed
  the whole run on the non-UTF-8-path fixture; the step now writes the replaced form the other steps write,
  which is also the form the tables it joins with hold. And the suffix index behind import resolution was
  built by walking a set, so where two files answer one module name (django has two `json.py`) the winner
  followed the hash seed: two runs of the same commit gave different import graphs and determinism read "no"
  on django. Each has a test that fails against the old code. The shipped record is the run after all three:
  robustness 21 of 21, determinism yes on both repositories, the gate 3 of 3.
- **The new rules' thresholds are the fittest part of the release.** Sensitivity now covers them: eleven
  thresholds are fragile where eight were, three of the new ones among them (`commented_out_code`'s ten
  lines, `hidden_coupling`'s degree of 60, `swallowed_errors`'s count of five), and `deep_nesting`'s five
  levels is moderate. None was chosen against a label, which is the other reason these findings stay out of
  the default report until the sheet's 35 are labelled.
- **0.33.0 asks the reader, and drops gitmole's own false policy finding.** Every label behind the
  actionable share is an agent's, so the tool now asks the one population that can answer: five yes/no
  questions after a plain interactive run, written to a file the reader chooses to send. It asks once on a
  machine, never in CI or behind an export flag, and gitmole uploads nothing, so the record is untouched by
  it -- the harness has no terminal, so no run here was ever asked. The only number that moves is gitmole's
  own, 8 findings to 7: `repo_policy` said it had no security policy while CONTRIBUTING.md#Security names
  the reporting route, which is the same false alarm the README fallback fixed for containerd at 0.29.0.
  Nothing else in the set changes.
- **The graphs had run two release labels together.** The x axis drew every nth label and then forced the
  last one whatever sat beside it, so the README's ranking graph read "0.31.00.32.0", and the caption was
  drawn along the legend's baseline and through its words. Labels are now spaced by the room a label needs,
  with both ends always drawn, and the note has a line of its own. Every graph on this page is redrawn.

- **0.34.0 fixed eleven things the report said wrongly and moved no number that measures the tool.** The
  ranking, the recall, the findings per repository (23.5 and 27.5), the report length (224 lines), the
  scored share, robustness (21 of 21) and the gate (3 of 3) are all identical to 0.33.0, and the findings
  count is unchanged on every one of the twenty-one repositories, the well-kept four included: nothing
  appeared and nothing disappeared. Report length moved by a line on four repositories and by three on
  react, +3 over the set, which the median does not feel.
- **The one number that appears to improve did not.** The dashboard's actionable share reads 69% where
  0.33.0 read 68%, and 96% of the spelled-out findings carry a label where 99% did. Both come from the
  same two findings: curl's and react's `tight_coupling`, which named a pair of documentation examples and
  were labelled true but not actionable. 0.34.0 leaves a pair of examples out of the coupling rules, so
  those two findings now say something else, carry no label, and leave the denominator -- 75 of 78 are
  labelled where 77 were. The share rose because two findings judged inert stopped being judged, not
  because anything got better. Whether the new claim is worth acting on is a person's to label.
- **Peak memory reads 3,035 MB against 0.33.0's 2,725 MB, and this release did not do it.** The peak is
  betterleaks on react, at the version every one of these releases pins (1.8.1) over the same commit:
  3,036.9 MB at 0.32.0, 2,724.6 at 0.33.0, 3,035.1 here. Nothing in 0.34.0 touches the secrets step.
  Wall time fell from 700 to 691 seconds over the development set.
- **The extras agree.** Determinism across time zone and locale is identical on curl and django, and the
  hook replay is identical to 0.33.0 on every repository. The only sensitivity rows that move are the two
  coupling rules' threshold sweeps, which is what changing those rules is supposed to move.
- **0.34.1 and 0.34.2 have no record of their own, and this is why.** Between 0.34.0 and 0.34.2 nothing
  gitmole runs was touched: the changes are `.github/workflows/ci.yml`, the formula's url and checksum,
  and `docs/development.md`. Both releases exist because the release job failed on its last step after
  doing all of its work -- 0.34.0 asked the tap to pull a `main` the checkout no longer had once the bump
  got a branch of its own, and 0.34.1 was refused permission to open the bump's pull request, which took
  the job down and skipped the publish behind it. No report can move, so the numbers above are all three
  releases'. The page holds a record for thirty-four of fifty-six released tags for the same reason --
  v0.9.1, v0.10.1 and the v0.6.x series have none either, while 0.30.1 does, because that fix moved
  eleven report lines.
- **0.35.0 lands the yardstick the cited papers are stated in, and moves no number that measures the
  tool.** Headroom (0.62 [0.36, 0.93]), ROC-AUC (0.82), W/L/T (17/4/9), recall at a fifth of the lines
  (36%), stability, bug magnets, the scored share, robustness (21 of 21), the gate (3 of 3), report length
  (224) and the findings median (23.5) are all identical to 0.34.0. Every ranking key that existed before
  is byte-identical at every cut-off. What is new is recorded beside them for the first time: Popt, initial
  false alarms, ManualUp as a control and recall under a complexity budget. Read together they say the
  watch list finds the fixed files (AUC 0.82) but spends more lines reaching them than a random order
  would: its Popt is under 0.5 on every development repository (0.24 curl to 0.42 ghidra), churn's is
  0.29 to 0.50, and ManualUp's 0.61 to 0.78 with its first hit at rank 11 to 15. Under a complexity budget
  the three lists keep their order at every repository, so the 2025 critique reproduces as magnitude
  (django's recall 0.60 to 0.17), not as a flip. Hassan's HCM3s and HCM1d, run through `evaluate` on the
  same five repositories, sum to 281 and 256 hits at the top fifteen against churn's 283 and the watch
  list's 318; HCM3s beats churn on django alone. Neither is a candidate for the shipped ranking on this
  evidence.
- **The p90 (27.5 to 28.5) and react (30 to 32 findings, 292 to 305 lines) moved with the clone, not the
  code.** This record was measured on clones made on 22 September in a new workspace; react's carries
  1,153 refs, the sapling pull-request archives among them, and git-sizer reads the whole clone, so two
  more `repo_health` rows fire (Blobs: total size; Biggest checkouts: path length at a remote ref). A run
  of 0.34.2's code over the same clone on 22 September already showed 32, and the diff between that run
  and this one is one surviving line in `knowledge_loss`. The secrets findings' ids moved with the clone
  too, since betterleaks reads its object store, so their labels no longer attach: the dashboard's
  actionable share reads 71% of 78 where 0.34.0 read 69%, and 94% labelled where 96% did, for bookkeeping
  reasons; no label was added or carried. `minor_contributors` changed its statement on every repository
  by design (its count is now Bird's count, with the expected traffic named), so those labels detach too.
- **Wall time (691 to 811 s) and peak memory (3,035 to 1,500 MB) are not comparable this release.** The
  machine carried a load average of 3 to 11 through the timed runs, from something other than the
  harness. betterleaks on react took 136 s against 31 and peaked at 1.5 GB against 3.0, at the same
  pinned version over the same commit; nothing in 0.35.0 touches the secrets step.
- **The extras agree.** Determinism across time zone and locale is identical on curl and django, the hook
  replay is identical to 0.34.0 on all five repositories, none of the 48 sensitivity rows changes its
  verdict, and 244 of 244 findings agree with their own numbers. The signed-commits second check stays
  unavailable, as in 0.33.0 and 0.34.0: gpg is not installed on this machine.
- **0.35.1 is the release where repo health and the secrets scan describe the commit, not the clone,
  and it moves the numbers that should move.** git-sizer used to measure every object any reference
  in the clone reached and betterleaks walked every branch, so the 0.35.0 record's react row carried
  two `repo_health` findings and a critical `secrets_in_source` that belonged to a pull-request
  archive branch the commit never reached, and binutils-gdb carried an oversized commit from a cygwin
  release tag. Both tools now read HEAD's history through a throwaway repository with one reference,
  and those findings are gone: react 32 to 29, binutils-gdb 24 to 23, findings median 23.5 to 23, p90
  28.5 to 27, report length 224 to 220.5. Every other repository keeps its count. The ranking keys are
  byte-identical to 0.35.0 at every cut-off, as a fix that touches no ranking should leave them.
- **The extras agree with 0.35.0 on every check**: determinism identical on curl and django, the hook
  replay identical on all five repositories, no sensitivity verdict moved, 240 of 240 findings agree
  with their own numbers (four fewer findings than 0.35.0, the four removed above). The signed-commits
  second check stays unavailable for want of gpg.
- **The cost lanes are readable this time for most of the set, with two caveats.** binutils-gdb's 421 s
  against 368 was measured under a load average of 10 from something other than the harness; the
  machine also slept for three and a half hours during that run, which the monotonic clock does not
  count. django was measured twice: the first pass, under a load of 6.6, projected its blame pass at
  62 s and skipped code age, so the entry was re-measured alone on a quiet machine (load 2.5) and merged
  in, which is why its wall time reads 166 s and its report has its ownership column. Peak memory reads
  1,125 MB against 1,500, betterleaks on react again at the same pinned version.
- **`evaluate` now prints Popt without labels, and it reverses a verdict.** On hits at fifteen the watch
  list beats every entropy list; on Popt against the same fixes the shipped entropy and Hassan's HCM1d
  beat churn and the watch list on all five development repositories, with a first hit at rank 0 to
  1.5 and a third to a half of the lines. Both are true: the watch list names more of the files that get
  fixed and pays for it in lines. Whether the list should rank by entropy is the holdout's question and
  is not decided by this release.
- **0.36.0 raises the findings ceiling for one rule, and says who decided.** The import cycles rule
  (#152) names groups of files that import each other as they load; it is `info`, in the unjudged set,
  and it fires once on django, ghidra and react in the development set (and on prometheus in the
  well-kept set), so findings per repository go from 23 and 27 at the median and 90th percentile to 23.5
  and 28, with report length unchanged at 220.5 lines because the rule's name joins the unjudged line
  and rewraps it without adding one. Raised from 23 and 27 to 23.5 and 28 for import_cycles, decided by
  the maintainer on 25 September, because a load-time cycle is the kind of finding the structure step
  exists to name and the rule cannot be judged until it fires; time-boxed by its labels — it leaves the
  unjudged set and the report if its actionable share at the next labelling is zero. Everything else
  that measures the tool is identical to 0.35.1: headroom 0.62, ROC-AUC 0.82, W/L/T 17/4/9, recall at
  a fifth of the lines 36%, stability, magnets, the scored share, robustness 21 of 21, the gate 3 of
  3, and every pre-existing ranking key at every cut-off. The record carries nine new ranking keys
  (#141: Popt under complexity and uniform cost and the uncapped false alarms, for the list, churn and
  ManualUp) and two new hook rates (#142: recall and top-3), all first recorded here.
- **The first 0.36.0 round was discarded, and the reason is a release-worthy fix (#153).** A refactor in
  0.36.0's own branch (#147) had left the structure step crashing on any repository with an
  unreferenced file in a trusted language; no test called that function directly and gitmole's own
  repository has no such file, so the suite and the golden report stayed green. The round showed it as
  `steps_failed: structure` on django, ghidra, prometheus and react, which dropped every structure rule
  there and read as a findings median of 18.5. The fix landed with two direct tests and the round was
  rerun; this record is the rerun.
- **The cost lanes are readable but were measured under load.** Wall time 766 s against 812, peak
  1,130 MB against 1,125; the machine carried a load average of 3 to 12 through the timed runs from
  something other than the harness, as in the two previous records. No step was skipped this time:
  django's blame pass ran (86 s).
- **Corrected after the release (independent review, 25 September): one dashboard number did move, for
  bookkeeping reasons, and two sentences above overstate.** The actionable share reads 78% of 77 where
  0.35.1 read 72%, and 82% labelled where 94% did. #145 added each area's size to the truck factor's
  evidence, a finding's id follows its evidence, and so nine of the ten truck factor findings shown took
  new ids that no label carries (gitmole's own is unchanged). Six of the nine detached labels said not
  actionable and three said actionable, so the share went from 52 of 72 to 49 of 63: a rise that no
  finding earned, the same kind of move as 0.35.0's secrets ids. It stays in the record until the next
  labelling; no label was added or carried. The load in the record's entries runs 3.4 to 8.5 on the
  development set, which sets the wall time, and up to 16.4 on the well-kept set (containerd), not 3 to
  12. And "no step was skipped" is true of the load-dependent skip only: ghidra and binutils-gdb skip
  code age and duplicates on their size budgets, as in 0.35.1 and as their headers say.
- **The extras agree**: determinism identical on curl and django; the hook replay identical to 0.35.1 on
  all five repositories, now with recall and top-3 beside precision (curl 0.06, react 0.14, binutils-gdb
  0.11, django and ghidra under 0.01); the sensitivity table gains one row for the new rule and none of
  the 48 verdicts moves; 244 of 244 findings agree with their own numbers. The signed-commits second
  check stays unavailable for want of gpg.
- **Since 0.35.1, besides the rule:** findings describe the commit rather than the clone in words as
  well as numbers (#144), the truck factor's lone-owner areas carry their sizes (#145), the header says
  when the structure step did not run (#146), `--risk` and `--hook` say what imports each touched file
  (#147), a Python import resolves from a root (#148), structure.json marks deferred imports (#151),
  the candidate-ranking and companions-sweep tools score on the record's measures (#141, #142), and
  the example pages are current (#143).

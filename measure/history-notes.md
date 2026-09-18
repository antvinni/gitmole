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
  found it; the release after 0.26.0 fixes it.
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
  measurement found.

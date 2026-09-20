# Measurement

How to tell whether gitmole is getting better; back to [the README](https://github.com/antvinni/gitmole#readme).

[validation.md](https://github.com/antvinni/gitmole/blob/main/docs/validation.md)
answers one question: is the watch list worth reading. This page is the wider
frame — what else the tool claims, how each claim can be checked, and which
numbers have to hold or improve for a release to count as progress. Most of it
is a plan rather than a description: [the order of work](#the-order-of-work) at
the end says what to build first.

## What gitmole claims

Four kinds of output, four kinds of claim, four ways to be wrong.

A **ranking** — the watch list and the hotspots table — claims that files near
the top are likelier to need work than files below them. It is wrong when the
order carries no information. This is the only claim currently measured.

**Findings** claim that a statement about this repository is true and that the
next step beside it is worth taking. A finding is wrong when the statement is
false, and wasted when the statement is true but nobody would act on it. Neither
is measured today.

**Descriptions** — counts, coverage, code age, activity, signing coverage — claim
to be arithmetic. They are wrong when the arithmetic is wrong, which unit tests
over synthetic input catch, or when the thing counted is not the thing named,
which they do not.

A **gate** — `--fail-on`, `--risk-threshold`, the hook — claims a change or a
repository deserves to be stopped. It is wrong when it stops healthy work, and
useless when it never stops anything.

Everything below hangs on that split, because the four need different evidence.

## The corpus, and the holdout

Every number on this page is measured over a fixed corpus of pinned clones, and
the corpus is split in two.

The **development set** is where thresholds get chosen and output gets eyeballed:
curl, django and react, which are also the example repositories. The
**holdout** is a second set, pinned the same way, never looked at while tuning.
When development and holdout disagree, the holdout is the answer.

The thirteen Apache repositories in validation.md, scored against ApacheJIT's
labels, are the nearest thing to a holdout today. They were looked at once, for
one decision (the watch list kept its ranking while tying churn alone, 674 to
674), and nothing was tuned against them. Treat them as the first holdout and
keep it that way.

A holdout is spent by use. Releases here are cut several times a day, so "run it
at every release" would read it dozens of times a week and turn it into a second
development set. Two rules keep it honest:

- Run the holdout when a release note is about to claim the tool got more
  effective, not on every tag. A release that only adds output does not need it.
- When a holdout result changes a decision — a threshold moved, a rule reverted,
  a variant dropped — the repositories that informed it move to development, and
  fresh ones from a reserve list take their place. Record the move beside the
  corpus manifest so the history of what was seen stays visible.

This matters more than any single metric here. gitmole carries a good rule
against a rule keyed on a word list learned from one repository
([development.md](https://github.com/antvinni/gitmole/blob/main/docs/development.md)),
but there is no equivalent discipline for the numbers. `SOLO_SHARE = 0.9`,
`COMPANION_DEGREE = 50`, the coupling rules' `min_degree` (80, 60 and 30 in
findings.py, 30 and 20 in maat.py), bus factor at 0.7, stale files at 0.3, bug
magnets at 3, brain methods at 15 and 100, duplication at 30, knowledge islands
at 200 and 0.9: each is a free parameter chosen against an unrecorded sample.
Some already say where they came from — `CCN_FLOOR = 10` is lizard's own
threshold for a complex function, and `component_coupling` carries a `ref` — and
the rest are choices. Recording which is which, in a line beside each constant,
costs nothing and tells the next reader how much to trust the number.

Corpus composition matters as much as size. Aim for thirty to fifty
repositories spanning: tiny and enormous; single-package and monorepo; active
and dormant; squash-merged, rebase-merged and merge-committed; at least six
language ecosystems; some deliberately badly kept. gitmole's own repository
belongs in it but must not dominate — a 160-commit Python project is not
representative of anything.

### The harness

None of this works if the numbers are gathered by hand. The corpus needs:

- **A manifest in the repository**: one entry per clone with its URL, pinned
  commit, role (development, holdout, reserve, awkward, well-kept, size tier) and
  label source where there is one. JSON, since the tool supports Python 3.9 and
  `tomllib` arrived in 3.11.
- **One command** that runs the manifest and writes a single dashboard JSON, one
  file per release, committed so that two releases diff.
- **A recorded cost.** The backtest multiplies a run by its cut-offs, R-SZZ adds
  a blame per fix, and jscpd needs about a gigabyte per 25 MB of text. Measure
  what the sixteen repositories validation.md already evaluates cost end to
  end before the corpus grows, and run the corpus sequentially under a memory
  budget rather than in parallel.

### Threshold sensitivity

For each threshold, re-run the corpus at ten, twenty-five and fifty percent
either side and record two things: how many findings the rule emits, and the
overlap (Jaccard) of the files or items it flags against the shipped value. A
rule whose finding count triples when its threshold shifts ten percent is fitted
to noise on whatever repository it was written against. A flat count is not
enough on its own: a rule that emits nine findings at every setting but names
different files at each is just as fragile. A rule that is flat on both across a
wide band holds up, and its exact value does not matter. This needs no labels
and no judgement, runs unattended, and is the cheapest way to find out which
constants carry weight.

## Ranking quality

`evaluate.py` already computes hits at k against three outcome definitions (fix
locality, R-SZZ bug insertion, external labels), the random expectation, initial
false alarms and the lines of code in the list. What follows is what to change
and what to add.

**Report headroom, not raw hits and not lift.** The totals table is hard to
read across repositories: curl scores 86 against a random expectation of 30.1,
react 55 against 5.1. Dividing by the expectation (lift) looks like the fix, but
lift cannot exceed k over the expectation, so its ceiling is set by the
repository's base rate: curl's lift of 2.86 is 96% of its ceiling of 2.99, while
react's 10.8 is 61% of 17.6. A median lift over a corpus mostly reports how many
sparse-outcome repositories the corpus holds. The comparable number is how much
of the gap between random and perfect the list closes:

    headroom = (hits − expected) / (best possible − expected)

curl scores 0.93, django 0.92, react 0.59. That puts curl's saturation in the
arithmetic, where the page now only says it in prose, and it does not reward a
corpus for its choice of repositories. Print hits, expected and best possible
beside it so the reader can check. Median headroom at 15 over the holdout is the
number to put in a release note.

**Score the whole ranking, as a diagnostic.** The report shows fifteen files, so
the dashboard scores fifteen. But a change that sharpens ranks 16 to 100
is invisible at the head and still matters to the JSON, the hotspots table and
`--risk`. ROC-AUC over the full ordered pool catches it, and unlike average
precision it does not move with the base rate, so it compares across
repositories.

**Report recall at an effort budget.** The list ranks by revisions × lines of
code, which deliberately favours large files, and large files cost more to
review. Recall at twenty percent of the codebase's lines is the standard
counterweight and is the honest self-check on a size-weighted ranking. If it
sits below the churn baseline, that is worth knowing and worth printing;
size-inverse rankings win this metric easily, which is why it belongs beside the
hit counts rather than replacing them
([arXiv 2504.19181](https://arxiv.org/abs/2504.19181)).

**Report per repository, not only in total.** A total of 231 hides a change that
helped curl by four and hurt react by three. Win, loss and tie counts per
repository per cut-off show whether an improvement generalises or trades. The
ApacheJIT table is the case in point: the watch list ties churn in total and the
per-repository split is the only place the trade shows.

**Measure stability.** Reconstruct the list at a commit and again fifty commits
later and record the rank correlation and the overlap of the top fifteen. A list
that replaces half its entries in a week is not usable by a human even when it
scores well; one that never changes is not responding to the repository. There
is no published target, so establish the current value as the baseline and treat
a large move as a regression to explain. `backtest.py` already reconstructs at
arbitrary cut-offs, so this is aggregation, not new machinery.

Fifty commits turned out to answer only the first half: every release reads
1.00, since fifty commits are days on curl and weeks on react. Since 0.29.0 the
record also keeps each cut-off's top fifteen, and the dashboard reports how
much of it carries over from one cut-off to the next, six months later (the
mean Jaccard overlap, median over repositories). That is the second half,
whether the list answers to the repository at all.

### Noise

gitmole is deterministic, so two runs never differ; the noise is in the sample.
Six cut-offs per repository are not six independent trials — consecutive lists
share most of their files — and three repositories are three data points. The
difference between 86 and 87 on curl, or between 231 and 225 in total, is
inside that noise.

Every ranking number on the dashboard gets an interval: bootstrap over
repositories, resampling whole repositories with their cut-offs rather than
individual cut-offs, since the cut-offs within one repository move together.
Compare two variants with a paired test across repositories (the sign of the
per-repository difference), not by their totals. A release-over-release move
counts as progress or regression only when it leaves the previous release's
interval.

### Labels from outside the project

Every label in `measure/labels.jsonl` carries `"labeller": "claude"`, so the precision and actionable
shares in the history are an agent's reading of rules an agent wrote, and `kappa` between two agent passes
would measure self-consistency. `--feedback` (0.33.0) asks the one population that can answer: on a plain
interactive run, gitmole asks five yes/no questions about the findings it spelled out and writes the
answers to a file the reader chooses to send. Nothing is uploaded, and the file holds no path, name or
value -- a rule id, a severity, the verdict, the version, and three bands.

What comes back is per rule rather than per finding, so it cannot be joined to a labelled finding and
cannot give a kappa. What it can give is the thing no label has: whether a rule's findings were worth
acting on to someone whose repository nobody here has seen. Answers land under `"labeller": "user"`, are
counted per rule beside the agent labels, and never replace them: a handful of answers from keen users is
a biased sample, and the bias runs toward people who liked the tool enough to answer.

## Finding quality

This is the unmeasured half of the tool, and it grew the most between 0.15 and
0.21: `hygiene`, `signing`, `licences`, `osps`, `provenance` and the structure
rules all emit findings that nobody has checked against reality.

### Hand labels

There is no substitute for reading findings and deciding whether they are true.

The protocol: run the corpus, dump every finding as JSONL with its rule id,
repository, pinned commit and evidence. Sample findings per rule, stratified
across repositories. Label each on two axes — **true**, meaning the statement is
factually correct about that repository, and **actionable**, meaning a
maintainer would plausibly do something about it. Store the labels in the
repository, keyed by rule id, repository, commit and a hash of the evidence, so
the work is reproducible and only changed findings need relabelling.

That yields, per rule: factual precision, actionable share, and volume. A rule
under roughly eighty percent factual precision is broken. A rule that is true but
rarely actionable belongs at `info`, or in the JSON only, not in the terminal
report. Severity calibration is the third question — anything emitted as
`critical` should be defensible one finding at a time, because `--fail-on
critical` is a promise.

Ten labels cannot decide the eighty percent line. Eight true of ten has a 95%
interval of 0.49 to 0.94; even ten of ten leaves the lower bound at 0.72. So
label in batches of ten and stop when the interval clears the line: a rule is
**broken** when the upper bound falls under 0.8, **sound** when the lower bound
rises over it (twenty of twenty does, at 0.84), and **undecided** otherwise.
findings.py alone has about fifty rule ids, so the first pass is around five
hundred labels, and the rules that stay undecided say where the next batch goes.
Rules that fire rarely across the corpus may never get there; say so beside
them rather than guessing.

Two cautions on the labels themselves. The person labelling wrote the rules and
is not a maintainer of the labelled repositories, which biases both axes toward
yes. Hide the rule id and severity while labelling, and have a second person
label a sample of fifty so the agreement between the two (Cohen's kappa) can be
reported beside the precision. "Actionable" in particular will agree less than
"true"; if the kappa is low, report actionable share as indicative only.

### The noise budget

Report **findings per repository**, median and 90th percentile across the corpus,
as a first-class metric with a ceiling. The report's brevity is the product. A
release that adds two rules and pushes the median from nine findings to fifteen
has made the tool worse even if both rules are correct, and no per-rule precision
number will show that. Track terminal report length in lines alongside it.

### The findings backtest

Several findings make an implicit prediction, and `backtest.py` already knows how
to rebuild the repository at a cut-off. Point the existing machinery at the
findings and the precision question gets an answer with no human in the loop:

- **bug magnets** at T: were those files fixed again in the following six months?
- **brain methods** at T: was the named function split, shortened, or its file's
  complexity reduced?
- **complexity growth** at T: did complexity keep rising?
- **tight coupling** at T: did the pair keep changing together?
- **knowledge loss** and **bus factor** at T: did the named area take more fixes
  in the following six months than comparable files? Whether it went stale or
  someone picked it up is not a test: either outcome fits the finding.
- **stale files** at T: are they imported by nothing in the import graph at T?
  Whether they were later deleted says whether the advice was taken, not whether
  the files were dead.

The output is not truth — advice not taken is not advice that was wrong — so read
these as calibration rather than accuracy. The number that matters is a ratio:
of the files called bug magnets, the share fixed again, against the same share
among files not called bug magnets. A ratio near one means the rule is naming
files at random, whatever its threshold says.

The comparison group has to be matched. A file flagged as a bug magnet is
already larger and busier than the typical unflagged file, and validation.md
shows that size and change alone predict the next fix well. Compared with every
unflagged file, almost any rule that leans toward big, busy files will show a
ratio above one. Compare instead with unflagged files in the same decile of
revisions × lines of code, the watch list's own score. Then a ratio above one
means the rule knows something the watch list does not.

This runs over as many repositories as can be cloned, which makes it the only
scalable precision signal available.

## Description accuracy

Unit tests prove the arithmetic on synthetic input. They cannot prove that the
thing counted in a real repository is the thing the report names. The check for
that is differential: count the same thing a second way on the corpus and
explain every disagreement.

- **Lines of code** from scc against a second counter (tokei or cloc) on the
  same tree.
- **Signing coverage** against `git log --format=%G?` over the same range.
- **Authors and activity** against `git shortlog -sne`, with and without the
  repository's `.mailmap`, so identity merging shows up as a difference that can
  be explained.
- **Ownership and code age** against `git blame --line-porcelain` counted
  directly, with the same ignore-revs and the same import-commit exclusion.
- **Scored and excluded files** against `git ls-files`, reconciled to the
  exclusion reasons `classify.coverage()` reports.

Each disagreement is either a bug or a definition (scc and tokei count
differently on purpose). Bugs get fixed; definitions get a sentence in
output.md. The metric is the count of unexplained disagreements across the
corpus, and it should be zero.

## The gate

For `--fail-on critical`, measure the **false alarm rate on well-kept
repositories**. Define "well-kept" before running anything, from outside
gitmole — an OpenSSF Scorecard above a fixed score, or a foundation's graduated
status — so the set cannot be picked for passing. Then record every critical it
fires and label each one. A fire is not a false alarm by default: a popular,
well-run repository can hold a real committed secret. The false alarm rate is
the share of repositories with at least one critical labelled false. Near zero
is the requirement; a gate that fails most healthy repositories will be turned
off and never turned back on. Any critical it does fire should be explainable in
one sentence.

For the catch rate, build synthetic fixtures — a repository with a committed
secret, one with a `MAL-` package pinned, one with an unpinned action, one with a
symlink escaping the tree — and assert that the gate fires. That is integration
testing rather than measurement, but it is what stops a refactor from silently
disarming the gate.

For the hook's coupling warning, precision can be measured offline by replaying
history with the two experiments ROSE was evaluated with
([Zimmermann et al., TSE 2005](https://thomas-zimmermann.com/publications/files/zimmermann-tse-2005.pdf),
sections 7.5 and 7.6), computing coupling from the history strictly before each
commit:

- **Error prevention.** Take each commit touching two or more files, leave one
  file out, and ask whether the hook would warn about it. Precision is the share
  of warnings naming the file that was left out; feedback is the share of
  queries that produce any warning. ROSE, at function granularity and 0.9
  confidence, warned on 3% of such queries with precision above 66%.
- **Closure.** Take each complete commit and ask whether the hook would warn
  about anything. Every warning here is a false alarm. ROSE warned on about 2%
  of complete transactions.

The two numbers come from different experiments and are not one result. ROSE's
file-granularity figures (its Table 6) are the fairer bar, since the hook warns
about files. Report the hook's precision, feedback and closure false alarm rate
together; the interruption rate is the cost side.

## The properties, not the outputs

Four cross-cutting guards. None measures whether gitmole is insightful; all of
them measure whether it is trustworthy, and they fail silently if unwatched.

**Determinism.** The CI job proves two runs on one machine agree on one
repository. Widen it: Linux against macOS, oldest supported Python against
newest, `LC_ALL=C` against a UTF-8 locale, two timezones, and five pinned corpus
repositories rather than gitmole itself. Locale and platform are where sort order
and float formatting drift, and the current matrix, macOS only, cannot see
either. The metric is binary and should stay at one.

**Runtime.** Nothing measures it. The pipeline has grown a structure pass, an
import graph, a signing pass and several file sweeps since the step list was
last small enough to hold in your head, and each was added without a number
beside it. Record wall time per step against pinned clones at three sizes, plus
peak memory, and fail the build on a regression beyond a set percentage of the
recorded baseline. Step-level numbers matter more than the total because they
say which step to look at; jscpd's memory behaviour is already documented as a
hazard and tree-sitter will become the next one.

**Robustness.** The share of the corpus that completes with no step in a failed
or timed-out state. The run already records per-step status in `meta.json`, so
this is aggregation. Keep a set of awkward inputs in the corpus: an empty
repository, one commit, a detached HEAD, a shallow clone, submodules, non-UTF-8
paths, a single enormous file, binary-only history.

**Coverage.** `classify.coverage()` already computes how many tracked files are
scored against each exclusion reason. Track the scored share across the corpus
between releases. This is the guard against the worst kind of regression, where
a classifier change excludes a fifth of the tree, nothing errors, and the
report simply gets emptier.

## The gate for a new signal

Before a metric, rule or reason ships, it should be able to answer six questions.

1. **Does it change anything?** Run the corpus with and without it. If the
   ranking and the findings are identical, it is decoration — which is a fine
   thing to put in the JSON, and not a thing to put in the report.
2. **Does it beat what it claims to beat, on the holdout, per repository, outside
   the noise?** The existing baselines are the right comparison and the totals
   are not enough.
3. **What does it cost?** Findings per repository, report length, wall time.
4. **Is its threshold principled or fitted?** If fitted, what does the
   sensitivity sweep say.
5. **Does determinism still hold?**
6. **If none of the above can be answered, does the documentation say so?** An
   unvalidated signal shipped as unvalidated is honest. The same signal shipped
   without saying so is the thing this whole page exists to prevent.

## The release dashboard

Nine numbers, each against the previous release, each from the set named beside
it. Every number carries its interval where it has one, and a move counts only
when it leaves the previous release's interval.

| | set | what it guards |
|---|---|---|
| median headroom at 15 | holdout | the ranking carries information |
| recall at 20% of lines | holdout | the ranking is worth the reading effort |
| top-15 stability over 50 commits | holdout | the list is usable by a human |
| top-15 carried over across six months | development | the list responds to the repository |
| findings per repository, median and p90 | holdout | the report stays short |
| rules sound, broken and undecided | labelled sample | the findings are true |
| repositories with a critical labelled false | well-kept | the gate is usable |
| wall time and peak memory per step, median of three runs | size tiers | the tool stays fast |
| scored share of tracked files | holdout and awkward | the classifier has not over-excluded |
| unexplained description disagreements | size tiers | the counts mean what they say |

A release that moves none of these added features rather than effectiveness. That
is not always wrong — SARIF output moves none of them and is clearly worth
having — but it should be a conscious answer rather than an unasked question.

## The order of work

Cheapest and most reusable first; each step makes the next one cheaper.

1. **The harness**: the corpus manifest, the one command, the dashboard JSON, and
   the recorded cost of the sixteen repositories validation.md already evaluates.
2. **What is only aggregation**: per-repository win, loss and tie; headroom;
   robustness from `meta.json`; scored share from `classify.coverage()`; findings
   per repository.
3. **Threshold sensitivity**, and the one-line note beside each constant.
4. **Noise**: the bootstrap intervals, before any dashboard number is used to
   call a release better.
5. **The findings backtest** with matched comparison groups.
6. **Description checks**, one counter at a time.
7. **Hand labels**, starting with the rules that emit `critical` and `warning`.
8. **The hook replay** and the well-kept set for the gate.
9. **Widening determinism** to Linux, locales and timezones.

## What this does not measure

Everything here measures internal consistency and predictive validity. None of it
measures whether a maintainer read a report and did something differently, which
is the only thing that finally matters and cannot be observed from a clone. The
available proxies are weak and worth being honest about: issues filed, findings
argued with, and the ignore files gitmole's own advice tells people to write.

Some traps worth naming. Counting rules or features as progress rewards the wrong
thing. Treating total findings as a target is Goodhart's law with a severity
column. Measuring on the repositories used for tuning is the failure this page
opens with, and reading the holdout at every release is the same failure more
slowly. Chasing semgrep or CodeQL on vulnerability detection is a different
job that gitmole will lose and does not need to win. And optimising hits at k
alone rewards ranking large files in saturated repositories, which is why
headroom and effort-aware recall sit beside it.

## What is built

`python -m gitmole.measure` implements this page as far as a machine can; see
[development.md](https://github.com/antvinni/gitmole/blob/main/docs/development.md)
for the commands and [measurement-history.md](https://github.com/antvinni/gitmole/blob/main/docs/measurement-history.md)
for every minor release measured with it, 0.2.0 to 0.26.0, and what the history shows.

- **The harness** (step 1): `measure/corpus.json` pins the development set
  (curl, django, react, gitmole), the ApacheJIT holdout, a well-kept set
  (four CNCF graduated projects, the criterion written down before the first
  run), and the awkward and gate fixtures the harness builds. A release runs
  from its own source, extracted from its tag, one repository at a time, and
  its record goes to `docs/measurements/<version>.json` with the time, peak
  memory and load average of every run.
- **Aggregation** (step 2): headroom with hits, expected and best possible
  beside it; win, loss and tie against churn per repository and cut-off;
  ROC-AUC over the whole pool; recall at 20% of the lines; top-15 stability
  over fifty commits; findings per repository, median and p90; report length;
  scored share; robustness over the awkward inputs; the gate's catch rate over
  its fixtures. A release is scored by the current definitions, not its own,
  so the yardstick does not move with the tool.
- **Threshold sensitivity** (step 3): every numeric keyword threshold of every
  rule, moved 10, 25 and 50% either side, with the finding count and the
  Jaccard overlap of what it flags. The one-line provenance beside each
  constant is not written yet; the sweep lists each as fitted until it is.
- **Noise** (step 4): bootstrap intervals over repositories, seeded, and a
  move counted only when it leaves the previous release's interval.
- **The findings backtest** (step 5): bug magnets against unnamed files in the
  same deciles of the list's score. The other rules named above are not
  backtested yet.
- **Description checks** (step 6): commits against `git rev-list`, lines per
  file against a second count, classified files against `git grep -I`,
  signing against `git log --format=%G?` over the last 200 commits. tokei and
  cloc are not installed where this was built, so lines of code are not
  checked against a second counter.
- **Hand labels** (step 7): `labels dump` writes a blinded sheet and a key,
  `labels score` gives each rule its Wilson interval, verdict, actionable share
  and Cohen's kappa. The 0.28.0 sheet is labelled (182 findings, by one
  labeller, `claude`), so kappa waits for a second labeller who did not
  write the rules.
- **The hook replay and the gate** (step 8): the two ROSE experiments at file
  granularity over the development set; the well-kept set's criticals are
  counted, and since 0.28.0 there are none.
- **The headline** (0.30.0): three questions decide whether gitmole is getting
  better, and the README draws one graph for each. *Is it right?* Headroom
  against churn, with the holdout's readings as dots. *Is it useful?* Of the
  findings the default report spells out, the share labelled actionable
  (`labels.usefulness`, from the finding ids each record keeps). *Does it run?*
  Robustness and the gate. Findings, report length, run time and memory are
  costs, and they stay on the history page. The long graphs draw every release
  over the same four repositories (`series` in `measure/corpus.json`), so a
  repository joining the development set cannot read as a move.
- **Labels carry forward**: a finding whose evidence did not change keeps its
  id, and so its label. One whose repository, rule and statement match a
  labelled finding gets a copy of that label (`carried_from`). Each `labels
  dump` puts only the rest on the sheet.
- **The summary line**: a rule with five or more labelled findings, none of
  them actionable, is named in one line of the default report instead of
  spelled out (`findings.SUMMARISED`; a test holds the set to the labels both
  ways). That is how the usefulness graph is meant to move: the report says
  less, and what it still says is more often worth doing.
- **Candidate rankings**: `python -m gitmole.measure.signals` ranks the
  watch list's pool by other signals (churn, size, change entropy, windows
  and decays of recent revisions × lines) at the same cut-offs. It is for
  exploring on the development set. The holdout is read once, with
  `--variant`, for the one candidate chosen there
  ([validation.md](validation.md#what-the-ranking-is-for) has the result).
- **Determinism** (step 9): the CI job compares a second time zone and the C
  locale on macOS, and a Linux run against the macOS one; `extras` repeats the
  time-zone and locale check on the development repositories.


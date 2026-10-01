# Measurement

How to tell whether gitmole is getting better; back to [the README](https://github.com/antvinni/gitmole#readme).

[validation.md](https://github.com/antvinni/gitmole/blob/main/docs/validation.md)
answers one question: is the watch list worth reading. This page is the wider
frame — what else the tool claims, how each claim is checked, and which numbers
have to hold or improve for a release to count as progress. `python -m
gitmole.measure` is the harness that computes them; see
[development.md](https://github.com/antvinni/gitmole/blob/main/docs/development.md)
for the commands and [measurement-history.md](https://github.com/antvinni/gitmole/blob/main/docs/measurement-history.md)
for every measured release and what the history shows.

## What gitmole claims

Four kinds of output, four kinds of claim, four ways to be wrong.

A **ranking** — the watch list and the hotspots table — claims that files near
the top are likelier to need work than files below them. It is wrong when the
order carries no information.

**Findings** claim that a statement about this repository is true and that the
next step beside it is worth taking. A finding is wrong when the statement is
false, and wasted when the statement is true but nobody would act on it.

**Descriptions** — counts, coverage, code age, activity, signing coverage — claim
to be arithmetic. They are wrong when the arithmetic is wrong, which unit tests
over synthetic input catch, or when the thing counted is not the thing named,
which they do not.

A **gate** — `--fail-on`, `--risk-threshold` — claims a change or a
repository deserves to be stopped. It is wrong when it stops healthy work, and
useless when it never stops anything.

Everything below hangs on that split, because the four need different evidence.

## The corpus, and the holdout

Every number on this page is measured over a fixed corpus of pinned clones,
listed in `measure/corpus.json` with each entry's URL, commit, set, size and
ecosystem.

- **development** — where thresholds get chosen and output gets eyeballed:
  medium repositories, diverse by ecosystem — curl and redis (C), react
  (JavaScript), yt-dlp and gitmole itself (Python), jadx (Java), Homebrew's brew
  (Ruby) and tokio (Rust) — each under two minutes and 1.5 GB a run, by
  `development_criterion` beside the corpus.
- **large** — django, ghidra and binutils-gdb, too slow or too big for the
  development loop; run in release rounds only (`run --release`).
- **well-kept** — four CNCF graduated Go projects (coredns, etcd, containerd,
  prometheus), chosen by that outside criterion before any gitmole run on them,
  and never tuned on.
- **holdout** — the thirteen Apache repositories of validation.md, scored
  against ApacheJIT's labels. They were read once, for one decision (the watch
  list kept its ranking while tying churn alone, 674 to 674), and nothing was
  tuned against them. When development and holdout disagree, the holdout is the
  answer.
- **awkward** and **gate** — fixtures the harness builds, with fixed dates.

The cost ceilings — findings per repository, report lines, wall time, peak
memory, scored share — are the development set's, which the loop measures whole;
the large set's wall time and peak memory are ceilings too, checked at release
rounds. The effectiveness numbers span development, large and well-kept in a
release round — fourteen repositories — because the large ones are where the
ranking loses, and a set without them would read better than the tool is. The
well-kept set stays out of the cost ceilings, and a crash there does not mark
the release as crashed. A loop's effectiveness numbers are compared only with
the last release cut to the repositories the loop ran, never with the release
headline. The long graphs draw every release over a fixed series (`series`:
curl, django, react and gitmole, the development set since 0.2.0), so a
repository joining the development set cannot read as a move.

A holdout is spent by use. Two rules keep it honest:

- Read the holdout when a release note is about to claim the tool got more
  effective, not on every tag. A release that only adds output does not need it.
- When a holdout result changes a decision — a threshold moved, a rule reverted,
  a variant dropped — the repositories that informed it move to development, and
  fresh ones from the `reserve` list take their place. Every move is recorded
  under `moves` beside the corpus, so the history of what was seen stays visible.

### The harness

A release runs from its own source, extracted from its tag with `git archive`,
one repository at a time and nothing else on the machine, so times and memory
compare. Its record goes to `docs/measurements/<version>.json` with the time,
peak memory and load average of every run, committed so that two releases diff.
What a release produces is scored by the current tree's definitions, not its
own, so the yardstick does not move with the tool. The rankings at cut-offs are
not timed and run side by side once the timed runs are over.

### Threshold sensitivity

`extras` moves every numeric keyword threshold of every rule by 10, 25 and 50%
either side and records, per repository, how many findings the rule emits and
the overlap (Jaccard) of what it flags against the shipped value, since a rule
that emits nine findings at every setting but names different files at each is
as fragile as one whose count triples. Each threshold gets a verdict — flat,
moderate, fragile, or silent where the rule fires nowhere. It needs no labels
and no judgement, and says which constants carry weight.

## Ranking quality

The harness rebuilds each release's ranking at six cut-offs and scores it
against the files a fix commit touched in the six months after each (the
ApacheJIT labels on the holdout). A fix larger than the repository's 99th
percentile of lines changed is tangled by size and credits nothing; the
percentile is taken over the commits before the window's end, the history as
it stood when the outcome was observed, so no window's outcome depends on what
the repository did after it. `evaluate.py` computes the same against three
outcome definitions (fix locality, R-SZZ bug insertion, external labels).

**Headroom, not raw hits and not lift.** Raw hits do not compare across
repositories: curl scores 86 against a random expectation of 30.1, react 55
against 5.1. Dividing by the expectation (lift) looks like the fix, but lift
cannot exceed k over the expectation, so its ceiling is set by the repository's
base rate: curl's lift of 2.86 is 96% of its ceiling of 2.99, while react's 10.8
is 61% of 17.6. The comparable number is how much of the gap between random and
perfect the list closes:

    headroom = (hits − expected) / (best possible − expected)

curl scores 0.93, django 0.92, react 0.59. That puts curl's saturation in the
arithmetic, and it does not reward a corpus for its choice of repositories.
Hits, expected and best possible are printed beside it so the reader can check.
Median headroom at 15 is the headline number.

**The whole ranking.** A change that sharpens ranks 16 to 100 is invisible at
the head and still matters to the JSON, the hotspots table and `--risk`. ROC-AUC
over the full ordered pool catches it, and it does not move with the base rate.

**Recall at an effort budget.** The list ranks by revisions × lines of code,
which favours large files, and large files cost more to review. Recall at twenty
percent of the codebase's lines is the standard counterweight; size-inverse
rankings win it easily, which is why it sits beside the hit counts rather than
replacing them ([arXiv 2504.19181](https://arxiv.org/abs/2504.19181)).

**Popt, false alarms, and a control.** `Popt` is the whole effort-versus-found
curve, the measure Fu and Menzies, Yang et al. and Huang et al. state every
effort-aware comparison in, so a number here can be put beside a published one:

    Popt = 1 − (area(optimal) − area(list)) / (area(optimal) − area(worst))

Above 0.5 beats random. A list can take a lines budget by naming many tiny files
and still send a reviewer past several before one matters; `ifa`, the files
before the first one fixed, shows it, and is why the effort-aware numbers are
never read alone. `manualup` ranks the smallest file first — the model Fu and
Menzies confirm Yang et al.'s unsupervised predictors all generalise. It is a
control: the expectation, registered before it was run, is that it beats the
watch list on recall at a lines budget and loses badly on `ifa`. If it wins
both, that is the finding.

**Lines are not the only effort driver.** Effort-aware measures assume review
effort is proportional to lines, and a complexity driver gives "quite different
indications" (2504.19181). So recall is also recorded with scc's per-file
complexity as the driver (`recall20_complexity`), and Popt under lines
(`popt`), complexity (`popt_complexity`) and uniform cost (`popt_uniform`, a
pure rank measure and so the size control). A candidate that gains only on
lines gained nothing. `ifa_all` is the false alarms uncapped, since capped at
the top a first hit at rank 40 reads the same as one at 15.

**Hassan's entropy models.** The change entropy gitmole ships is close to
Hassan's HCM2 with a decay of its own. `maat.entropy` also computes the two
models he found best, HCM3s and HCM1d (burst periods, normalised by every file
the history has touched, HCM1d decayed by φ), behind parameters whose defaults
are the shipped analysis, and `evaluate` ranks by them beside the default.

**Per repository, not only in total.** A total hides a change that helped curl
by four and hurt react by three, so win, loss and tie counts against churn are
kept per repository per cut-off.

**Stability and carry-over.** The list is reconstructed at a commit and again
fifty commits later, and the record keeps the rank correlation and the overlap
of the top fifteen. A list that replaces half its entries in a week is not
usable by a human even when it scores well. Fifty commits answer only that
half: every release reads 1.00. The other half — whether the list answers to the
repository at all — is carry-over: the mean Jaccard overlap of the top fifteen
from one cut-off to the next, six months later, median over repositories.

`python -m gitmole.measure.signals` ranks the watch list's pool by other signals
(churn, size, change entropy and HCM3s and HCM1d, each alone and with the size
term restored, windows and decays of recent revisions × lines) at the same
cut-offs and scores every one on all of the measures above. It is for exploring
on the development set.

**Fix-count baselines.** The one ranking signal with long, consistent support
is a file's prior fixes, weighted toward recent ones. `signals` carries it as
rows, never as the list: Rahman et al.'s naive model (FSE 2011), the files by
their count of fixes, as `evaluate` already ranks it (`recent fixes`, the last
six months), the same over the whole history before the cut-off (`fixes`), and
a fix count decayed exponentially (`fix decay Nm`, Graves et al., TSE 2000;
Kim et al., ICSE 2007) at each half-life of a grid declared in the code before
it was run (`FIX_HALF_LIVES`: 3, 6, 12 and 24 months) — swept, not tuned. The
naive model's own cut, the files that fit in a fifth of the codebase's lines, is
`recall20`. The predictor and the development outcome are the same thing —
`maat.is_fix` — so on fix locality these rows share the outcome's label noise
(about half of keyword-found fixes are not fixes, Herbold et al., EMSE 2022) and
are flattered by it. `signals --szz` therefore scores them, and the watch list,
churn and size they must beat, a second time against R-SZZ bug insertion
(`evaluate.induced_between`), under `NAME / R-SZZ`. Development can only rank
these candidates against each other; none of them is promoted without a
release-tag holdout read, one candidate per read, as [Is a candidate
better?](#is-a-candidate-better) sets out.

### Noise

gitmole is deterministic, so two runs never differ; the noise is in the sample.
Six cut-offs per repository are not six independent trials — consecutive lists
share most of their files. Headroom carries a bootstrap interval over repositories, resampling whole
repositories with their cut-offs, since the cut-offs within one repository move
together; it is seeded, so the same input gives the same interval. A
release-over-release move counts only when it leaves the previous release's
interval. Two ranking variants are compared by the paired test in [Is a
candidate better?](#is-a-candidate-better), not by their totals.

## Finding quality

### Hand labels

There is no substitute for reading findings and deciding whether they are true.

`labels dump` writes every finding of the latest recorded release's development,
large and well-kept runs as a blinded sheet — one finding per line with its id,
repository, commit and statement, the rule id and severity left out — and a key
that maps each id back. Each label has two axes: **true**, meaning the statement
is factually correct about that repository, and **actionable**, meaning a
maintainer would plausibly do something about it. A finding's id is its rule,
repository, pinned commit and evidence, so the work is reproducible and only
changed findings need labelling: one whose evidence did not change keeps its
id and so its label, and one whose repository, rule and statement match a
labelled finding gets a copy of that label (`carried_from`).

`labels score` gives each rule its factual precision with a Wilson interval,
its actionable share, and Cohen's kappa where two labellers labelled the same
findings. A rule under roughly eighty percent factual precision is broken. A
rule that is true but rarely actionable belongs at `info`, or in the JSON only.
Anything emitted as `critical` should be defensible one finding at a time,
because `--fail-on critical` is a promise.

Ten labels cannot decide the eighty percent line. Eight true of ten has a 95%
interval of 0.49 to 0.94; even ten of ten leaves the lower bound at 0.72. So a
rule is **broken** when the upper bound falls under 0.8, **sound** when the
lower bound rises over it (twenty of twenty does, at 0.84), and **undecided**
otherwise. Rules that fire rarely across the corpus may never get there.

Every label in `measure/labels.jsonl` carries `"labeller": "claude"`: the
labeller wrote the rules and maintains none of the labelled repositories, which
biases both axes toward yes, and the blinded sheet removes only part of that.
AGENTS.md forbids adding agent labels, since more of them add volume, not
standing. `--feedback` asks the one population that can answer: on a plain
interactive run it asks about the findings it spelled out and writes the answers
— rule id, severity, verdict, version and three coarse buckets, no path, name or
value — to a file the reader chooses to send. They are per rule, so they cannot
be joined to a labelled finding, and they lean toward people who liked the tool
enough to answer.

No outside labels exist, so every number below that rests on `actionable` is
one agent's reading of the findings, not evidence that they are worth acting
on, and the docs quote it as that. Two things act on the labels.
`labels.usefulness` gives each release its actionable share — of the findings its default report spells out, the share
labelled actionable, beside how many carry a label at all. And a rule with five
or more labelled findings, none of them actionable, is a decision to make
(`findings.SUMMARISED`; a test holds the set to the labels both ways). Until
0.39.0 such a rule was named in one line of the default report instead of
spelled out; at 0.39.0 the nine it held were retired instead, with the
duplicates and git-sizer steps they alone needed ([tools.md](tools.md#retired)),
so the set is empty: the report says less, and what it still says is more often
worth doing.

### The noise budget

**Findings per repository**, median and 90th percentile, is a first-class
metric with a ceiling. The report's brevity is the product. A release that adds
two rules and pushes the median from nine findings to fifteen has made the tool
worse even if both rules are correct, and no per-rule precision number will
show that. Terminal report length in lines is tracked alongside it. The current
ceilings are the last release's record.

### The findings backtest

Several findings make an implicit prediction, and the backtest that rebuilds
the repository at a cut-off can check it with no human in the loop. Bug magnets
are backtested: of the files the rule named at a cut-off, the share fixed again
in the following six months, against the same share among unnamed files. The
other predictions — brain methods split, complexity still rising, coupled pairs
still changing together — are not backtested.

The comparison group is matched: a bug magnet is already larger and busier than
the typical file, and size and change alone predict the next fix well, so the
unnamed files compared are those in the same decile of revisions × lines of
code, the watch list's own score. A ratio above one means the rule knows
something the watch list does not; near one, it is naming files at random.

The ratio is printed two ways, side by side, and neither is preferred. The
pooled one adds every decile's unnamed files into one control and every
repository's six cut-offs into one sum, so the deciles weigh by their unnamed
files, a repository with many magnets dominates, and a file named at six
cut-offs counts six times. The standardised one expects each named file to be
fixed at the rate of the unnamed files in its own decile, Σ_d (named_d / named)
· rate_d, takes observed over expected per repository, and reports the median
over repositories, so each counts once. A decile the named files fill alone has
no rate and is left out of the standardised one, and counted.

`python -m gitmole.measure.remediation` asks the other question git can answer:
was the thing a finding named fixed within a fixed window after it — the action
pinned, the binary gone, the dependency dropped. That is "the repository acted
on this", never precision, and a biased lower bound, since mechanical advice is
taken far more readily than structural advice; its docstring says which rules
it can and cannot score. A release round asks it at the ranking's own six cut-offs
on the development repositories (not the large ones, by the maintainer's
decision: binutils-gdb alone would add about 35 minutes): the release's
`--json` export of the tree at each cut-off, scored against the tree six
months later. That is one release run per cut-off, about six times the
development set's run time, in the untimed half beside the rankings: roughly
15 to 20 minutes more wall time per release round. The record
keeps the outcome counts by rule (`remediation` on each entry), the summary
pools them over the development set, and the history page prints the table.
A subject that was renamed or moved is followed through git's rename
detection (limit pinned) and judged at its new path, and counts as *moved*,
never as fixed; a subject still named at several cut-offs of one repository is
counted once, at the first, and the later ones as repeats.

A release round asks the question only when its answer can change: when, since
the commit of the last record that asked it, a path its rows depend on changed —
the predicates (`gitmole/measure/remediation.py`), the file classifier
(`classify.py`, `filetypes.py`), the code behind the scored findings and the
scans at the cut-offs. `remediation.ASKED_WHEN_CHANGED` lists those paths in one
place and errs toward asking; a test holds every module under `gitmole/` to that
list or to a short one left out with a reason (the banner, the installer, the
SARIF writer). The diff is mechanical, `git diff --name-only` over the named
paths. Otherwise each development entry records
`remediation: {"asked": false, "reason": ...}`, the summary keeps the gap and its
reason, and the history page prints "not asked (reason)": a number is never
carried forward from an earlier record. `run --remediation` asks it whatever
changed, and `run --release --no-remediation` records it as not asked. The
record's `remediation_asked` says which way the round went and which watched
paths changed. In the releases from 0.36.0 to 0.43.0 `findings.py` changed in
every one, so the question would have been asked each time: the saving is the
rounds of a release whose changes lie elsewhere.

## Description accuracy

Unit tests prove the arithmetic on synthetic input. They cannot prove that the
thing counted in a real repository is the thing the report names. The check
for that is differential: `extras` counts the same thing a second way on the
development repositories and lists every disagreement.

- **Commits** against `git rev-list --count HEAD`.
- **Lines per file** against the newlines counted in each file scc measured.
  A second counter such as tokei or cloc is not used.
- **Classified files** against the tracked text files `git grep -I` sees.
- **Signing coverage** against `git log --format=%G?` over the last 200 commits,
  where gpg is installed.

Each disagreement is either a bug or a definition. Bugs get fixed; definitions
get a sentence in output.md and an entry in `extras.EXPLANATIONS`. The metric is
the count of unexplained disagreements, and it should be zero.

## Claims: does a finding's text agree with its own numbers

Everything above scores what the rules decide. None of it reads the sentence a
person is given, so a finding can be true, useful and unreadable and score
exactly the same. react's one critical finding at 0.33.0 read
`facebook-access-token in (unreachable blob 00db21063ea1) (); facebook-access-token
in (unreachable blob 00db21063ea1) ()`, and every number in that record was
content with it.

`claims.py` holds each finding to what its own text can be checked against, so
there is nothing to tune and no threshold to sweep:

- **A list that joined nothing** leaves its punctuation behind: `()`, `(, abc`,
  `and 0 more`.
- **A count of one does not take a plural** (`1 params`), and no word carries a
  plural that cannot be one (`2 IPv4 addresss`).
- **One entry is not printed twice** in the same list.

A complaint is a defect rather than a score, so the number to want is zero, and
the dashboard reads it as *findings whose text agrees with their own numbers*,
over every set — the fixtures included, since a rule that rarely fires says its
piece there. Two further shapes are counted apart as advisory, because they are
judgements and not errors: a count over one followed by what reads as a
singular (mostly `23 of 78` and units), and the `(s)` spelling. `python -m
gitmole.measure claims` re-checks a round already run, in seconds.

## Consistency: does a finding agree with the rest of the report

A finding can agree with its own numbers and still contradict the report it
sits in. In the 0.38.0 reports of apache/devlake and of gitmole itself the
collected data was right and the finding drawn from it was not: the knowledge
map marked someone gone and the advice still asked them to review; the
sweeping-commit list held a module rename and the lock-file rule fired on it;
git had a binary at HEAD and repo health said it had left the tree.

`consistency.py` holds each finding to the facts the same run collected, so it
needs no label and has no threshold:

- **gone_in_advice / gone_unmarked** — advice names someone the report counts as
  gone, or a finding names them without the knowledge map's `(gone)`. The two
  rules whose subject is the people who left are exempt.
- **wrong_area** — advice pairs someone on an area its own evidence gives to
  someone else.
- **growth_window** — a change "in a year" over less than a year of history.
- **secrets_headline** — the first value a secrets finding names is graded lower
  than another value in the same finding.
- **sarif_gate** — a critical or warning finding with no SARIF result, so
  `--fail-on` and code scanning disagree about the same run.
- **trailer_author** — a People row whose every commit came from
  `Co-authored-by` trailers, shown as an author.
- **tree_claim / sweeping_evidence** (with the clone, read at the recorded
  commit) — a path called gone that git has, and a finding resting on a commit
  the report says it left out as sweeping.

The 0.39.0 report of debpalash/VoiceStudio, one developer and a coding agent,
added seven more, each from a finding its maintainer checked and found false or
misleading: **agent_owner** (the knowledge map names a tool as an owner),
**magnet_gone** (a bug magnet the tree no longer holds), **hygiene_misread** (an
extra index only in comments, a setup.py with no setup()), **lock_workspace** (lock
drift on a workspace member whose root keeps the lock), **unreferenced_named** (an
"unreferenced" file a build or deploy config names), **self_credit** (co-authored
counts that include the author's own aliases) and **declared_critical** (a critical
the repository declared allowed in a gitleaks or betterleaks config or inline).

The 0.40.0 report of vectorize-io/hindsight, a many-package monorepo whose
maintainer found seven of twenty-four findings false, added eight: **generated_owner**
(an ownership finding's start area is mostly generator output the repository
declares), **agent_pointer** (an agent file dated as stale that only points at
another file), **start_area** (the truck factor's advice names an area other than
the one with the most files at stake), **structure_skipped** (a source file the
structure step never parsed, unnamed), **dependency_floor** (a range's floor reported
as a version), **sarif_rows** (vulnerable rows that never reach SARIF), **doc_lock** (a
requirements file set aside as documentation) and **tool_person** (a person grouped
as a coding tool).

The 0.41.0 report of paperclipai/paperclip, a product built largely by its own
coding agent, added eleven, each deciding by its own reading of the export or the
clone rather than by calling the function it judges (agent_owner asked
`identity.tools`, so it agreed with it when it was wrong): **tool_owner** (a tool —
a bare no-reply mailbox two or more names use, or one credited mostly by trailer —
as an owner, second owner or holder of surviving code), **merge_total** (the People
merge total against git's, or a row with negative commits), **suspect_lead** (a
function list led by a span lizard marked suspect or the structure step measures
over twice as long or short), **test_double_lead** (a finding led by a Cargo binary
only tests/ start), **test_path_secret** (a secret in a smoke, e2e or fixtures path
or below `#[cfg(test)]`), **peer_unused** (an unused dependency the lock records as
a peer, or a stylesheet loads), **declared_reference** (an unreferenced file a
package.json runs or publishes, or `new URL(…, import.meta.url)` loads),
**lock_without_require** (a go.mod with nothing to lock), **dev_only_vuln_lead** (a
vulnerable lead only devDependencies reach while a runtime row waits),
**silent_precondition** (a rule advertising a test that did not run, silently) and
**trailer_case** (trailer keys split by case, or an issue id read as one).

As with claims, a complaint is a defect and the number to want is zero; the
dashboard reads it as *contradictions between a finding and the report's own
facts*, by check. `python -m gitmole.measure consistency` re-checks a round
already run; with `--rerender` it judges the current tree's rules instead, by
re-rendering each saved analysis with `--no-run`, so a change to how findings
are drawn gets its before and after in about two minutes, with nothing
collected again. The 0.38.0 round, before any fix: 394 contradictions, 304 of
343 findings consistent — trailer_author 322, gone_unmarked 38, gone_in_advice
9, sarif_gate 8, growth_window 6, secrets_headline 6, wrong_area 3,
tree_claim 2.

## The gate

For `--fail-on critical`, the measure is the **false alarm rate on well-kept
repositories**, a set defined from outside gitmole before running anything so
it cannot be picked for passing. Every critical it fires is counted. A fire is
not a false alarm by default: a popular, well-run repository can hold a real
committed secret. Near zero is the requirement; a gate that fails most healthy
repositories will be turned off and never turned back on.

The catch rate is measured over the gate fixtures — a repository with a
committed secret, one with a Trojan Source bidi character, one with credentials
in a submodule URL — and the gate must fire on each. That is integration testing
rather than measurement, but it is what stops a refactor from silently
disarming the gate.

For the hook's coupling warning, `extras` replays history with the two
experiments ROSE was evaluated with
([Zimmermann et al., TSE 2005](https://thomas-zimmermann.com/publications/files/zimmermann-tse-2005.pdf),
sections 7.5 and 7.6), at three anchors six months apart, with coupling computed
from the history before each anchor and the two months after it as queries:

- **Error prevention.** Leave one file out of each commit touching two or more,
  and ask whether the hook would name it. Precision is the share of warnings
  naming the file left out, recall the share of queries where it was named,
  feedback the share of queries with any warning, top-3 likelihood how often it
  was among the first three companions named.
- **Closure.** Ask whether the hook would warn about a complete commit. Every
  warning here is a false alarm.

The two come from different experiments and are not one result; ROSE's
file-granularity figures (its Table 6) are the fair bar, since the hook warns
about files. `python -m gitmole.measure.companions` sweeps the shipped
thresholds over support and confidence on the same anchors and commits, so a
proposal to move them is measured before it is made.

## The properties, not the outputs

Four cross-cutting guards. None measures whether gitmole is insightful; all of
them measure whether it is trustworthy, and they fail silently if unwatched.

**Determinism.** In CI, two runs of the same commit on macOS must export the
same JSON outside the envelope, and so must a third in another time zone and the
C locale; a Linux run must match the macOS one wherever both used the same
version of each external tool. `extras` repeats the time-zone and locale check
(UTC and C against Asia/Tokyo and a UTF-8 locale) on curl and django in a
release round, curl and react otherwise. The metric is binary and should stay at
one.

**Runtime.** Every run records its wall time, peak memory, the load average and
the seconds of each step, since step-level numbers say which step to look at.
The ceilings are the last release's record; jscpd's memory behaviour was the
documented hazard until it was retired at 0.39.0.

**Robustness.** The share of runs that complete with no step in a failed or
timed-out state, read from the per-step status in `meta.json`, over every set a
round ran. The awkward set is the inputs most likely to break it: an empty
repository, one commit, a detached HEAD, a shallow clone, a submodule, a
non-UTF-8 path, a single enormous file, binary-only history.

**Coverage.** `classify.coverage()` computes how many tracked files are scored
against each exclusion reason, and the record tracks the scored share between
releases. This is the guard against the worst kind of regression, where a
classifier change excludes a fifth of the tree, nothing errors, and the report
simply gets emptier.

## Is a candidate better?

Headroom compares a list with random, and every sensible list beats random: at a
handful of repositories its interval is too wide for a real improvement to leave it.
The question a ranking change has to answer is narrower — does it name more of the
files that get fixed than the current watch list, on the same ground — and it is
answered by `python -m gitmole.measure.candidate BASE CANDIDATE`, decided before any
run as follows.

- **Same ground.** Both releases are run from their own source on each repository
  of the effectiveness set (development, large and well-kept), ranked at the same
  six cut-offs, and scored on the baseline's pool against the same outcome. The
  baseline is run again beside the candidate rather than read from its record, so
  both share one toolchain and one clone state. A file the candidate did not rank
  goes after the ones it did, in the baseline's order; where the candidate's own
  pool differs (its classifier moved), the files it added and dropped are counted
  in a "pool moved" column, since an added file cannot score on the baseline's
  pool and a dropped one costs the candidate only if it was fixed.
- **The effect** at a cut-off is the candidate's top-fifteen hits minus the
  baseline's; a repository's effect is the mean over its cut-offs, since the
  cut-offs of one history move together.
- **The test** is an exact one-sided sign-flip over the repositories: every one of
  the 2^n patterns of their effects' signs (16,384 for fourteen), the share whose
  total is at least the observed one. No sampling and no seed; a bootstrap
  interval is unreliable at ten to fourteen repositories. A repository where the
  candidate changes nothing flips to itself, so z of them put a floor of 2^z/2^n
  under p: with fewer than five repositories where anything changes, p cannot
  reach 0.05.
- **Nothing is dropped.** A repository or cut-off that failed on either side
  makes the result "incomplete" (and the command exits 1), never a smaller test:
  a candidate that crashes where it would lose must not be judged on the rest.
- **The rule.** A candidate is better when its mean effect is positive and p is
  under 0.05 on the effectiveness set, and then again on the holdout, read once
  for that candidate when the maintainer agrees (`--holdout --approved "who,
  when"`). A read is of a commit, never a working tree, over the whole holdout
  (no `--only`), and only once every clone is present at its pinned commit and
  the labels are in place; it is then appended to `measure/holdout-reads.jsonl`,
  which is committed with the result, and a second read of the same candidate is
  refused unless `--again` says it is one. This command is the one sanctioned way
  to read the holdout; `signals --set holdout` reads it without a log and is for
  the analyses already recorded in validation.md. A candidate that passes on
  development and fails on the holdout is selection, as the twelve-month recency
  variant was (336 against 310 on development, 729 against 724 on the holdout).
- **Reported, never deciding.** The mean without the saturated cut-offs, where
  half the pool or more was fixed and both lists tend to hit alike; and on the
  dashboard, how far the watch list sits above the better of churn alone and
  size alone. Records carry what that needs (`size_*` beside `churn_*`, and each
  cut-off's `pool_digest`, a fingerprint of the files it scored, so two records
  can be checked for having scored the same pool) from the first release round
  after the fields landed; earlier records are not backfilled.
- **Snoring, reported beside the holdout's decision.** A bug is labelled only
  once it is found, and defects are often found long after they are introduced,
  so recent code reads clean (Ahluwalia, Falessi and Di Penta, MSR 2019; Falessi
  et al., TOSEM 2022). Only labels that stop can snore: the holdout's ApacheJIT
  labels end on 2019-12-31, the `end` of every holdout entry, while the
  development outcome is fixes inside a complete six-month window. Wherever the
  repositories' labels end, `candidate` prints the decision a second time without
  the cut-offs whose horizon and one more (T + 2 × horizon) run past that end —
  on the holdout exactly 2019-06-30 — side by side with the one that decides,
  and the JSON keeps it under `unsnored`. It never decides, and nothing is
  dropped from the decision. It runs only where the holdout is read, in a
  release-tag job; its code is tested on fixtures. The control is on the
  development set, where the outcome cannot snore: `python -m gitmole.measure
  positives` prints each cut-off's share of the pool in the outcome from a
  recorded round. On the 0.42.0 record the medians over the seven development
  repositories with cut-offs, oldest first, are 0.23, 0.12, 0.17, 0.13, 0.18 and
  0.13 — no fall toward the latest cut-off, which is what a complete window should
  show.

With fourteen repositories the test can show a candidate that wins consistently,
not a small, uneven gain; that is a property of the corpus, and a result that
does not reach the line is "not shown", not "worse".

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

`python -m gitmole.measure report` writes each release's dashboard into
measurement-history.md, each number from the set named beside it. Headroom
carries its interval, and a move counts only when it leaves the previous
release's interval. "Ranked" is the development set, plus large and well-kept
in a release round.

| | set | what it guards |
|---|---|---|
| median headroom at 15 | holdout, where read; ranked | the ranking carries information |
| recall at 20% of lines | holdout, where read; ranked | the ranking is worth the reading effort |
| top-15 stability over 50 commits | ranked | the list is usable by a human |
| top-15 carried over across six months | ranked | the list responds to the repository |
| hits above the better of churn and size; saturated cut-offs | ranked | information only, never deciding |
| findings per repository, median and p90 | development | the report stays short |
| findings spelled out that are labelled actionable | development and well-kept, plus large in a release round | one agent's reading of whether the findings are worth acting on; no outside labels |
| rules sound, broken and undecided | labelled sample | the findings are true |
| repositories that fired a critical | well-kept | the gate is usable |
| wall time and peak memory | development; large | the tool stays fast |
| scored share of tracked files | development | the classifier has not over-excluded |
| findings whose text agrees with their own numbers | every set | the sentences say what the numbers say |
| unexplained description disagreements | development | the counts mean what they say |

The README draws three of these as graphs, one per question. *Is it right?*
Headroom against churn, with the holdout's readings as dots. *Is it useful?*
The actionable share, captioned as one agent's labels. *Does it run?* Robustness and the gate. Findings, report
length, run time and memory are costs, and they stay on the history page.

A release that moves none of these added features rather than effectiveness.
That is not always wrong — SARIF output moves none of them and is clearly worth
having — but it should be a conscious answer rather than an unasked question.

## What this does not measure

Everything here measures internal consistency and predictive validity. None of
it measures whether a maintainer read a report and did something differently,
which is the only thing that finally matters and cannot be observed from a
clone. The available proxies are weak and worth being honest about: issues
filed, findings argued with, `--feedback` answers, and the ignore files
gitmole's own advice tells people to write.

Some traps worth naming. Counting rules or features as progress rewards the
wrong thing. Treating total findings as a target is Goodhart's law with a
severity column. Measuring on the repositories used for tuning is the failure
the holdout exists to prevent, and reading the holdout at every release is the same
failure more slowly. Chasing semgrep or CodeQL on vulnerability detection is a
different job that gitmole will lose and does not need to win. And optimising
hits at k alone rewards ranking large files in saturated repositories, which is
why headroom and effort-aware recall sit beside it.

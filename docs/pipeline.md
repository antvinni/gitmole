# Pipeline

How gitmole is built, and what keeps an agent-driven loop honest; back to [the README](https://github.com/antvinni/gitmole#readme).

[AGENTS.md](https://github.com/antvinni/gitmole/blob/main/AGENTS.md) is this page's
conclusions as rules, which an agent follows without reading the reasoning here.
[development.md](https://github.com/antvinni/gitmole/blob/main/docs/development.md)
is the mechanics — checkout, tests, releases.
[measurement.md](https://github.com/antvinni/gitmole/blob/main/docs/measurement.md)
is what the tool's effectiveness means and how it is measured. This page is the
loop that connects them: what a change has to show before it lands, and which
decisions an agent is not allowed to make.

## Say what changed and how you know

Every change says what it does to the output and how that was shown: a refactor
says the JSON is identical outside the envelope, a false positive removed names
the rule and the count before and after, a cost change gives the timing, a new
export shows that it works and that determinism holds. The command sits beside
the number.

One claim keeps a higher bar. A change that says gitmole now ranks or catches
better needs the candidate test behind it, ending in one read of the holdout.
Most of 0.11.0 to 0.25.0 was new surface described in effectiveness language,
which is why the history reads as a plateau; the fix is not making the claim
without the number.

## Budgets

A measurement you only read afterwards is a diary. A budget is a control.

The cost lanes have ceilings — findings per repository at the median and p90,
report lines, wall time and peak memory — and they are whatever the last release
record in `docs/measurements/` says: the development set's, plus the large set's
wall time and memory at release rounds. A change that pushes one over does not
fail review on taste; it fails on arithmetic, and has three honest options: make
the case that the ceiling should rise and record who decided, remove or demote
something else to pay for it, or narrow the rule until it fits.

Every new rule looks justified on its own. The budget is the only place the sum
is represented. Nothing in CI checks it: the change states its cost, and the
next release round records whether the sum crossed a line.

Demotion is the cheap currency: a finding that is true but rarely actionable
belongs at `info`, or in the JSON export only, where it costs no report lines
and stays available to anyone who wants it. Demotion is not exemption, though —
0.32.0 kept all thirty-five new findings out of the default report and still
moved the median from 18.5 to 23.5, because the JSON is a cost lane too.

The ceilings are a ratchet set at measured values, not hoped-for ones. Lowering
one is free and is what a prune release does. Raising one requires a line saying
who decided and why, which is the whole mechanism: not a prohibition, a receipt.

## Who marks the homework

The failure mode of an agent-built project is not bad code. It is that the same
process writes the change, writes the test, runs the measurement and narrates
the result, and an agent handed a hypothesis tends to return it confirmed.

Three roles, and the separation matters more than the count.

The **implementer** writes the change.

The **validator** runs the corpus and produces numbers. It should see the diff
and the output and not the rationale or the expected result. Its second job is
to write the strongest available case that the change is noise: the interval it
sits inside, the repository where it lost, the threshold it is sensitive to. A
validator that has read the hypothesis is a rubber stamp with extra steps.

The **labeller** decides whether a finding is true and whether anyone would act on it. Every one of
the 231 labels in `labels.jsonl` carries `"labeller": "claude"`, so the precision figure for rules an
agent wrote is computed by an agent, and no human anchor exists. `kappa` is implemented, but
agreement between two agent passes measures self-consistency, not correctness.

The usual fix is to anchor them: hand-sign a stratified sample each release and publish agreement
against it. That is the right answer for a project with labelling capacity, and this one has not got
it — a maintainer with a day job is not going to sign fifty findings a release, and a mechanism
nobody performs is worse than none, because the history goes on quoting a number whose basis has
quietly lapsed.

So change what is measured rather than fake the anchor. Remediation asks the repository's own later
history whether the named thing was fixed, which is evidence about maintainer behaviour rather than
an opinion about it, and no agent enters. It answers a narrower question than `actionable` and it is
biased toward the mechanical, both of which the harness states. That is a smaller claim honestly
held, which beats a larger one resting on an anchor that was never signed.

The 231 labels are a snapshot and do not grow; more agent labels add volume, not standing. The slot
stays open — the schema carries a `labeller` field, so labels from users drop in without rework, and
the ignore files they write are themselves labels, collected from people who looked and had a stake.

## What agents must not decide

**The holdout.** A holdout an agent can read during development is not a
holdout, and filesystem isolation is not an honest answer when the same agent
runs the corpus: it can reach whatever the harness can reach. So the *number* is
the controlled thing rather than the clone. A holdout figure counts only when the
maintainer asked for it, for a named claim: `python -m gitmole.measure.candidate
--holdout` refuses to run without `--approved` naming who agreed, and appends
each read to `measure/holdout-reads.jsonl`, committed with the result. A figure
computed any other way has no standing and does not enter the history, whoever
computed it. That is checkable after the fact, which a rule about what not to
look at is not.

Contamination is planned for rather than forbidden. `corpus.json` holds eight
repositories in reserve. A holdout repository that has been read during
development moves to the development set and a reserve repository is promoted in
its place — recorded under `moves`, with the date. A holdout that is never
allowed to be spent slowly becomes a development set nobody admits to.

**Thresholds by eye.** A constant chosen by looking at output on the development
repositories is overfitting with extra steps, and it is invisible afterwards.
Every threshold should be principled with a citation, or swept — the sensitivity
run from measurement.md tells you which ones are load-bearing. Record which kind
each one is in a line beside it.

**The corpus.** A repository an agent happened to clone is not a measurement repository. Random
public repositories are a badly biased frame — most are personal, most are short-lived, the median
has a handful of commits, and a third are not software development at all — so a rate averaged over
them is dominated by projects gitmole has nothing to say about. They belong in the robustness lane:
completion rate, crashes, timeouts, scored share, the performance envelope, and shaking out false
positives. Adding one to the effectiveness corpus, or tuning against one, is a decision with a
pre-registered criterion behind it, which is exactly what `corpus.json` records.

**Golden files.** `UPDATE_GOLDEN=1` exists so an intended change to the report
can be reviewed as a diff. An agent that regenerates it to make a test pass has
deleted the review. Keep the regenerated file in its own commit with the diff in
the pull request body.

**Its own validation.** The change and the harness that judges it should not
arrive in the same pull request. When they must, the harness lands first,
against the old behaviour, and its numbers are recorded before the change is
written.

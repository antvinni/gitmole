# Pipeline

How gitmole is built, and what keeps an agent-driven loop honest; back to [the README](https://github.com/antvinni/gitmole#readme).

[development.md](https://github.com/antvinni/gitmole/blob/main/docs/development.md)
is the mechanics — checkout, tests, releases.
[measurement.md](https://github.com/antvinni/gitmole/blob/main/docs/measurement.md)
is what the tool's effectiveness means and how it is measured. This page is the
loop that connects them: who proposes a change, what it has to prove before it
lands, and which decisions an agent is not allowed to make.

## The diagnosis this page exists for

The instruments already work.
[measurement-history.md](https://github.com/antvinni/gitmole/blob/main/docs/measurement-history.md)
records, per release, the ranking's headroom and ROC-AUC, recall at a fifth of
the lines, findings per repository, report length, gate catches and peak memory.
It is more rigorous than most commercial tooling: the well-kept set was chosen
by an outside criterion before anything was run against it, the development and
holdout sets are separate, and a move inside the previous release's confidence
interval is not counted as a move.

And what it says about the last fourteen releases is that they added output
rather than effectiveness. The ranking numbers have not moved since 0.11.0.
Findings per repository went from 10.5 to 16 at the median and 13.4 to 21.8 at
the 90th percentile. The report grew from about 212 lines to about 258.

That is not a failure of the measurement. It is what an unfenced generative loop
does. Each change was individually defensible, every test stayed green, and the
cost only appears when you sum it — which is exactly the quantity no single
pull request is asked about. No workflow runs the corpus, so nothing in the
build could have objected.

The pipeline design question is therefore not how to produce more. It is how to
wire the instruments to the controls.

## Three lanes

Not every change should move the same number, and pretending otherwise turns a
useful metric into a tax on good work.

**Effectiveness** changes claim the tool gets better at ranking or at catching:
a ranking change, a new signal, a threshold. These must move an effectiveness
number — headroom, ROC-AUC, recall at a fifth of the lines, gate catches — on
the holdout, or they do not ship. "It seems right" is what the corpus exists to
replace.

**Correctness** changes claim an existing output was wrong: a false positive
removed, a rule taught an exclusion it should always have had, a statement
corrected. These do not touch the ranking and must not be argued as if they
might. They have their own numbers and should be held to them — precision on
the labelled sample for that rule, false positives removed, and the cost lanes
falling rather than rising. A correctness change that moves none of those has
not been measured yet.

**Reach** changes make the tool usable somewhere it was not: SARIF, SBOM,
pre-commit, the hooks, packaging, documentation. Their acceptance test is that
the new surface works, determinism holds, and the cost lanes do not move.

The lane is declared in the brief and repeated in the release note, and the
build asks only for a number in the declared lane. A change that genuinely
moves nothing in any lane is still allowed, but it says so and says why, and
that sentence is the record. Most of 0.11.0 to 0.25.0 was reach work described
in effectiveness language, which is why the history reads as a plateau rather
than as a deliberate phase.

## Budgets

A measurement you only read afterwards is a diary. A budget is a control.

Give the cost lanes explicit ceilings — findings per repository at the median
and p90, report lines, wall time at a fixed corpus size, peak memory — and set
them at roughly today's values. A change that pushes one over does not fail
review on taste; it fails on arithmetic, and has three honest options: make the
case that the ceiling should rise and record the reason, remove or demote
something else to pay for it, or narrow the rule until it fits.

This is the single mechanism that would have changed the last fourteen releases.
Every new rule looks justified on its own. The budget is the only place the sum
is represented.

Demotion is the cheap currency: a finding that is true but rarely actionable
belongs at `info`, or in the JSON export only, where it costs no report lines
and stays available to anyone who wants it. Demotion is not exemption, though —
0.32.0 kept all thirty-five new findings out of the default report and still
moved the median from 18.5 to 23.5, because the JSON is a cost lane too.

Record the ceilings beside the corpus definition and treat them as a ratchet
set at today's values, not at hoped-for ones. Lowering a ceiling is free and is
what a prune release does. Raising one requires a line saying who decided and
why, which is the whole mechanism: not a prohibition, a receipt.

## The merge gate

Move the cost lanes from a retrospective into the build. The full corpus does
not belong there: several gigabytes of clones and a double-digit runtime per
pull request buys very little, because the two questions have different
sensitivities.

A **cost regression shows on any repository**. Findings per repository, report
length, wall time and peak memory move the same direction on two repositories
as on nine, so the per-pull-request gate runs a small fixed pair — gitmole
itself and one large repository — and fails when a ceiling is crossed without a
recorded note, or when determinism breaks. That is cheap enough to run on every
change that touches the rules, and it is the gate that 0.32.0's move from 18.5
to 23.5 would have tripped.

An **effectiveness claim needs the corpus**, because the intervals are wide at
three development repositories and wider at two. That runs at the release
round, against the full set, once.

Cache by commit, gitmole version and the tool manifest digest, which is already
recorded, so a repeated run is minutes. `--compare` between two JSON exports is
most of the delta already.

## Who marks the homework

The failure mode of an agent-built project is not bad code. It is that the same
process writes the change, writes the test, runs the measurement and narrates
the result, and an agent handed a hypothesis tends to return it confirmed.

Three roles, and the separation matters more than the count.

The **implementer** writes the change against a brief.

The **validator** runs the corpus and produces numbers. It should see the diff
and the output and not the brief, the rationale or the expected result. Its
second job is to write the strongest available case that the change is noise:
the interval it sits inside, the repository where it lost, the threshold it is
sensitive to. A validator that has read the hypothesis is a rubber stamp with
extra steps.

The **labeller** decides whether a finding is true and whether anyone would act
on it. Today every one of the 230 labels in `labels.jsonl` carries
`"labeller": "claude"`, which means the precision figure for rules an agent
wrote is computed by an agent. `kappa` is implemented, but agreement between two
agent passes measures self-consistency, not correctness.

The fix is not to stop using agents for labelling — it is the only way the
volume is affordable. It is to anchor them. Sign a sample by hand each release,
fifty findings stratified across rules, and publish kappa between the hand-signed
anchor and the agent labels alongside the precision number. If that agreement is
high, the agent labels carry weight and the cost stays near zero. If it is not,
the precision numbers in the history need a footnote. Either way the reader can
tell, which is the standard the rest of this project holds itself to.

## What agents must not decide

**The holdout.** A holdout an agent can read during development is not a
holdout, and filesystem isolation is not an honest answer when the same agent
runs the corpus: it can reach whatever the harness can reach. Two mechanisms
work without pretending otherwise.

Make the *number* the controlled thing rather than the clone. A holdout figure
counts only when a release-tag job produced it; one computed locally has no
standing and does not enter the history, whoever computed it. That is checkable
after the fact, which a rule about what not to look at is not.

Then plan for contamination instead of forbidding it. `corpus.json` already
holds eight repositories in reserve. A holdout repository that has been read
during development moves to the development set and a reserve repository is
promoted in its place — recorded, with the date. A holdout that is never
allowed to be spent slowly becomes a development set nobody admits to.

**Thresholds by eye.** A constant chosen by looking at output on the development
repositories is overfitting with extra steps, and it is invisible afterwards.
Every threshold should be principled with a citation, or swept — the sensitivity
run from measurement.md tells you which ones are load-bearing. Record which kind
each one is in a line beside it.

**Golden files.** `UPDATE_GOLDEN=1` exists so an intended change to the report
can be reviewed as a diff. An agent that regenerates it to make a test pass has
deleted the review. Keep the regenerated file in its own commit with the diff in
the pull request body.

**Its own validation.** The change and the harness that judges it should not
arrive in the same pull request. When they must, the harness lands first,
against the old behaviour, and its numbers are recorded before the change is
written.

## Briefs state the number

The spec-driven layout already produces a brief and a report per task. One
addition makes them load-bearing: the brief names the metric that will move, the
direction, roughly how much, and what result would mean the idea was wrong. The
report then measures rather than describes.

A brief that cannot name a number is a reach change, and should say so in the
lane field instead of reaching for a justification it does not have.

Worth noting that `.superpowers/` and `docs/superpowers/` are both gitignored, so
none of this reasoning survives in the repository. For a tool whose entire pitch
is that you can check its working, the record of why each rule exists is the one
artefact most worth keeping. Committing the briefs, or a distilled decision log,
would cost almost nothing.

## Self-hosting

gitmole has a hook, a pre-commit manifest and a provenance pass. Point all three
at its own development.

Run `--hook` as a `PostToolUse` gate on the agents working on gitmole. The
coupling-companion warning then fires during development, its false-alarm rate
stops being a number from a 2005 paper and becomes lived experience, and the
interruption rate can be recorded.

Run the cohort analysis on gitmole's own history. The commits carry
`Co-authored-by` trailers, the provenance pass reads them, and the repository's
own truck-factor finding already reports that an agent wrote half the surviving
code. Revert rate, fix rate and watch-list hit rate for trailer-bearing against
non-trailer commits, measured here, is both dogfooding and a dataset almost
nobody else can produce — with the caveat the roadmap already records, that the
local number is the finding and the global prior is not to be imported.

## Cadence

Given what the history says, the next effectiveness release should probably
remove rather than add: every rule below its precision floor or above its share
of the noise budget gets demoted to `info` or to the JSON, and findings per
repository comes back down while the ranking holds. That is a measurable win and
it is available now, without a new idea.

After that, alternate. A build phase takes items from the roadmap in whichever
lane; a validation phase runs the holdout, refreshes the labels with a
hand-signed anchor, re-runs the sensitivity sweep and prunes whatever did not
earn its place. The build phase is where agents are fastest and the validation
phase is where the project stays honest, and the second one is the one that will
get skipped unless it is scheduled.

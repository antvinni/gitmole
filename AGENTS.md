# AGENTS.md

gitmole is a deterministic offline git and code analyser. Its value is that a
reader can check its working: every finding is a plain rule over counts, and the
same commit gives the same bytes. Changes that add output are easy and changes
that add effectiveness are rare, so this file is mostly about telling the two
apart and about not damaging the record that can tell them apart.

`docs/pipeline.md` has the reasoning. This file is the part you must follow
without reading it.

## Setup and tests

```bash
brew install scc git-sizer betterleaks jscpd osv-scanner   # the versions gitmole/tools.py pins
python -m pip install -e .                                  # the grammars are ordinary dependencies since 0.32.0
python3 -m unittest discover -s tests -t .
```

`GITMOLE_NOW=YYYY-MM-DD` fixes the reference date; the golden test needs it. A tool at a version
other than the pinned one changes the output you are measuring, and every report says so under
`run.tools_moved`; check that before believing a number moved.

Touching `Formula/gitmole.rb` means `brew style Formula/gitmole.rb` before the commit. `brew audit`
cannot be run here: Homebrew refuses to load a formula from an untrusted tap and exits 0 having done
nothing, so the formula job in CI is the first real check of it.

## The four hard rules

**1. Declare a lane, and move a number in it.** Unattended, that means correctness or reach:
effectiveness needs the holdout, and the holdout is not yours to run (below). An effectiveness idea
is prepared, measured on development only, and left with its numbers for a human to confirm.

- *effectiveness* — ranking or catching gets better. Must move an effectiveness
  number on the holdout: headroom, ROC-AUC, recall at a fifth of the lines, gate
  catches.
- *correctness* — an existing output was wrong. A false positive removed, a rule
  taught an exclusion it should always have had. Must move that rule's precision
  or its share acted on, and must not raise the cost lanes.
- *reach* — the tool works somewhere it did not: an export format, packaging,
  docs, an integration. Not expected to move the ranking, and must not be
  argued as if it might.

A change that moves nothing in any lane is allowed, but says so and says why.
That sentence is the record. Most of 0.11.0 to 0.25.0 was reach work described
in effectiveness language, which is why the history reads as a plateau.

**2. Do not spend the cost budget without a receipt.**

The ceilings are whatever the last release records in `docs/measurement-history.md`
and `docs/measurements/`: findings per repository at the median and p90, report
lines, wall time, peak memory. Read them, do not hardcode them here.

Lowering is free. Raising requires a line saying who decided and why. Demotion
to `info` or to the JSON is the currency for paying — but demotion is not
exemption: 0.32.0 kept thirty-five findings out of the default report and the
median still rose, because the JSON is a cost lane too.

If a change would cross a ceiling and you cannot pay for it, stop and leave a
note. Do not raise the ceiling yourself.

**3. A harness lands before the thing it judges.**

Never put a measurement change and the rules it measures in the same commit or
the same pull request. 0.30.1 did, and that release's eleven-line drop can no
longer be attributed to either. The harness lands first, against current
behaviour, and its numbers are recorded before the change is written.

Producing a release's record is not a harness change: a run of the existing harness belongs with the
release it measures. What must land separately is a change to the yardstick itself — the corpus, the
scoring, the way a number is computed or printed.

**4. Do not touch the record.**

These files are the evidence that the tool is improving. An agent editing them
is the worst available failure, because it destroys the thing that would show
the night went wrong.

- `docs/measurement-history.md`, `docs/measurements/*.json`
- `measure/labels*.jsonl`, `measure/corpus.json`
- `tests/golden/report.txt` — regenerate with `UPDATE_GOLDEN=1` only when a
  report change is intended, in its own commit, never to make a test pass

Do not add labels. Every label in `labels.jsonl` already carries
`"labeller": "claude"`, and more agent labels add volume, not standing.

## Never, unattended

- Commit to `main`. Work on a branch.
- Merge a pull request, including one you opened yourself.
- Tag, release, or touch `Formula/`, or push anything that triggers the release job.
- Force-push, rebase published history, or `git clean` / `git add -A` (untracked
  work in this tree has been lost that way twice).
- Run the holdout, or read the holdout clones. Holdout numbers count only when a
  release-tag job produced them.
- Clone or analyse a repository that is not already on this machine. Robustness
  work uses the corpus clones and the fixtures `gitmole/measure/corpus.py` builds.
  Fetching a stranger's repository unattended spends disk and network on your own
  initiative, and hands arbitrary bytes to betterleaks, scc, jscpd and the
  grammars while nobody is watching. Hunting false positives on a fresh
  repository is good work; it is daylight work.
- Add a repository to the measurement corpus. A repo you happened to clone is
  not a measurement repo, and which repositories count is a decision with a
  criterion behind it, recorded in `measure/corpus.json`.
- Turn on anything that reaches the network in a scan: `betterleaks` validation
  stays `--validation=false`, `osv-scanner` stays `--offline`.

## Writing a new rule

A rule may key on three things only, and this constraint is older than anything
else here (`docs/development.md`):

- a path convention of the ecosystem (`vendor/`, `node_modules/`, `dist/`, a
  lock file's name)
- the shape of a value (a version string, a template field, a dotted key path)
- what the repository declares about itself (`linguist-generated`, `.mailmap`,
  a `[bot]` suffix, an ignore file)

Never a product name, a person's name, or a word list learned from one
repository. Such a rule fixes the repository it was written for and guesses
about the next one.

A new rule also needs: a `rule` dict with its id and the thresholds it fired on,
an `evidence` dict that **names its subjects** rather than counting them (a rule
whose evidence gives only a total cannot be measured — see `NO_SUBJECTS` in
`gitmole/measure/remediation.py`), and a threshold that is either principled
with a citation or swept. Never a threshold chosen by looking at output on the
development repositories.

## Working

One commit per loop, with the lane first in the subject, and the numbers in the body:

```
correctness: trojan_source consults the classifier, so a generated protobuf is not a finding

Lane: correctness
Before: containerd 22 findings, trojan_source fired on 1
After:  containerd 21 findings, trojan_source fired on 0
Checked: python3 -m unittest discover -s tests -t . (1052 ok)
```

Those three lines are the receipt. A number with no command beside it is a claim, not a result, and a
command that printed nothing proved nothing — say what you ran and what it said, including when it
said the change did nothing.

Run the tests before each commit. If you are blocked, or a change would break
one of the four rules, stop and write what you found in the commit message or a
note in the branch — do not improvise around it. A loop that ends with an honest
"stopped because X" is worth more than one that ends with a green diff nobody
asked for.

## Unattended loops

**The tree is shared.** Another session may be writing in it. Stage the paths this loop changed, by
name — never `git add -A`, and never a directory, which is how two files that belonged to someone
else were committed on 20 September. Read `git status` before every commit, and if a file you did
not touch has appeared, leave it alone and say so. A stale `.git/index.lock` with no git process
running is safe to remove; anything else about another session's work is not yours to resolve.

**Produce a branch, not a release.** Push the branch and open a pull request so the morning has
something to read. Never merge it, never tag, never touch `Formula/`. CI on a pull request is free
to you and costs the project runner minutes: one push per loop, not one per fix.

**Stop the night when:**

- CI fails twice on the same cause, or any job fails that you cannot explain
- a measurement contradicts the last record and you cannot say why
- the working tree holds changes you did not make and they overlap your work
- a rule here would have to be bent to continue
- the loop has nothing left that fits correctness or reach

Leave the branch, the pull request and a note saying which of these it was.

**What a loop can afford.** A full measurement round is about 45 minutes and the extras another 25,
so a loop that changes any number ends at "record produced", not at "released". A loop that changes
no number — docs, tests, a refactor — should not run the harness at all.

**The three things that look like progress and are not:** regenerating
`tests/golden/report.txt` to make a test pass, adding labels to `measure/labels.jsonl`, and widening
a threshold until a finding disappears. Each leaves a green tree and a worse tool.

## Where the reasoning lives

- `docs/pipeline.md` — lanes, budgets, the gate, who marks the homework, the loops
- `docs/measurement.md` — what effectiveness means and how it is measured
- `docs/measurement-history.md` — what every release actually moved
- `docs/development.md` — layout, tests, releases
- `docs/references.md` — the research each rule rests on

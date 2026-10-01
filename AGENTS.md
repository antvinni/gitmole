# AGENTS.md

gitmole is a deterministic offline git and code analyser. Its value is that a reader can check its
working: every finding is a plain rule over counts, and the same commit gives the same bytes. Keep
it that way, and keep the evidence that it is so.

The core below applies to every change. The appendix applies only when nobody is watching.
`docs/pipeline.md` has the reasoning behind both.

## Setup and tests

```bash
brew install scc betterleaks osv-scanner   # the versions gitmole/tools.py pins
python -m pip install -e .
python3 -m unittest discover -s tests -t .
```

`GITMOLE_NOW=YYYY-MM-DD` fixes the reference date; the golden test needs it. A tool at a version
other than the pinned one changes the output, and every report says so under `run.tools_moved`; check it
before believing a number moved.

Touching `Formula/gitmole.rb` means `brew style Formula/gitmole.rb` before the commit. `brew audit`
cannot be run here (Homebrew refuses a formula from an untrusted tap and exits 0 having done nothing),
so the formula job in CI is its first real check.

## The core

**Say what changed and how you know.** Every commit body ends with one or two lines: what the change
does to the output, and the command that showed it, with what it printed. "No output change: the JSON
is identical outside the envelope (command)" is a complete answer for a refactor; a timing, a count or
a test is the answer for anything else. A number without its command is a claim, not a result, and a
command that printed nothing proved nothing.

**Claim better ranking only with the candidate test.** A change that says gitmole now ranks or catches
better needs the candidate test behind it (`python -m gitmole.measure.candidate`, `docs/measurement.md`, "Is a
candidate better?"): positive on the effectiveness set and then on the holdout, read once, when the
maintainer agrees. Without it, describe what
changed and do not argue that it helps.

**Mind the output budget.** A change that adds findings or report lines says how many, on which
repositories. The ceilings are the last record's (`docs/measurements/`): the development set's, and the
large set's wall time and memory at release rounds. Crossing one needs the maintainer's decision, not
yours. Demoting a finding to `info` or to the JSON is the usual way to pay, but the JSON counts too:
0.32.0 kept thirty-five findings out of the default report and the findings median still rose.

**A harness change lands alone.** A change to how something is measured — the corpus, the scoring, how
a number is computed or printed — goes in its own pull request, run against current behaviour with its
numbers recorded, before any change it would judge. Running the existing harness to produce a release's
record is not a harness change.

**Leave the record alone.** Never edit `docs/measurement-history.md` or `docs/measurements/*` by hand
(`python -m gitmole.measure` `run`, `extras` and `report` write them; do not overwrite a release's
existing record), `measure/labels*.jsonl`, `measure/corpus.json` or `measure/holdout-reads.jsonl` (only
`candidate --holdout` appends to it).
Do not add labels. Regenerate `tests/golden/report.txt` (`UPDATE_GOLDEN=1`) only when a report change
is intended, in its own commit — never to make a test pass.

**Keep scans offline.** `betterleaks` stays `--validation=false`, `osv-scanner` stays `--offline`.
Never read the holdout clones while developing; the one holdout run a claim needs happens when the
maintainer asks for it.

**Git hygiene.** Fetch and branch from `origin/main` (Dependabot moves it unattended); `main` takes pull
requests only. Stage files by name — never `git add -A` or a directory, and never `git clean`
(untracked work has been lost to both, and a directory add committed another session's files on
20 September). Read `git status` before committing, leave files you did not touch alone, and say that
they appeared. No force-push, no rewriting published history. Tag, release or touch `Formula/` only
when the maintainer asks.

**Run the tests before every commit.** If a change would need one of these rules bent, stop and say so
in the pull request instead of working around it.

## Writing a rule

A rule may key on three things only (`docs/development.md#rules`):

- a path convention of the ecosystem (`vendor/`, `node_modules/`, `dist/`, a lock file's name)
- the shape of a value (a version string, a template field, a dotted key path)
- what the repository declares about itself (`linguist-generated`, `.mailmap`, a `[bot]` suffix, an
  ignore file)

Never a product name, a person's name, or a word list learned from one repository.

A rule also needs a `rule` dict with its id and the thresholds it fired on, `evidence` that names its
subjects rather than counting them (the remediation measurement cannot score a total), and a threshold
that is principled with a citation or swept — never one chosen by looking at output on the development
repositories.

## People and agents are never scored

People and agents appear only as the subject of a file- or area-level knowledge risk (an owner, the
person a truck factor hangs on, an area's agent-assisted share). No per-person or per-agent score, rank
or threshold, and no finding about a person's own work; the `--risk` author-experience reasons (EXP,
SEXP) stay reasons and never enter a score or threshold. The People table and the timeline are allowed
as what they are, descriptive counts of what git records per identity (commits, merges, share,
surviving lines), and nothing may be computed from them per person beyond that. A finding about how an
identity is recorded (`placeholder_identity`, `signoff_by_co_author`) is about the record, not the
person's work, and is allowed on the same terms: it names the identity and judges nothing else. The retired
`authors_gone` and `knowledge_loss` shapes stay retired. Engineers rate measuring individuals the
least wise use of this data (Begel and Zimmermann, `docs/references.md`).

## Appendix: unattended loops

When nobody is watching, these apply on top of the core.

**Produce a branch, not a release.** Work on a branch, push it once, open a pull
request, and stop. Never merge, including your own pull request; never tag; never touch `Formula/`.

**The tree is shared.** Another session may be writing in the main checkout. Work in a worktree off
`origin/main`. A stale `.git/index.lock` with no git process running is safe to remove; anything else
about another session's work is not yours to resolve.

**Measure only what can move.** A loop round (`run`: development, awkward, gate) is about 8 minutes of
timed runs, a release round (`run --release`) about 25 plus 15–20 for remediation at the development set's cut-offs, and the extras
have not been timed. Run one only
when the change touches what gitmole finds or ranks (findings, scoring, a pinned
tool), and end the loop at "record produced", not "released". A docs, test or refactor change runs the
tests and nothing else.

**Never, unattended:** run the holdout; add a repository to the corpus; clone or analyse a repository
that is not already on this machine (hunting false positives on a fresh repository is good work, done
while someone is watching); turn on anything that reaches the network in a scan.

**The three things that look like progress and are not:** regenerating the golden file to make a test
pass, adding labels, and widening a threshold until a finding disappears.

**Stop the night when:**

- CI fails twice on the same cause, or a job fails that you cannot explain
- a measurement contradicts the last record and you cannot say why
- the working tree holds changes you did not make and they overlap your work
- a rule here would have to be bent to continue
- nothing is left that you can finish and show without a holdout number or the maintainer's decision

Leave the branch, the pull request and a note saying which of these it was.

## Where the reasoning lives

- `docs/pipeline.md` — why these rules, budgets, who marks the homework
- `docs/measurement.md` — what effectiveness means and how it is measured
- `docs/measurement-history.md` — what every release actually moved
- `docs/development.md` — layout, tests, releases
- `docs/references.md` — the research each rule rests on

# Development

Setting up a checkout, running the tests, cutting a release, and where the code lives; back to [the README](https://github.com/antvinni/gitmole#readme). How to report a bug or send a change: [CONTRIBUTING.md](https://github.com/antvinni/gitmole/blob/main/CONTRIBUTING.md).

## Setup

Homebrew for the five tools, `brew install scc git-sizer betterleaks jscpd osv-scanner`.
Then either a virtual environment with `pip install -e .`, or the checkout
style: `python3 -m pip install --user rich lizard` and
`ln -sfn "$PWD/bin/gitmole" "$(brew --prefix)/bin/gitmole"`, which makes
the checkout what runs.

The checkout symlink and `brew install gitmole` claim the same path, so pick
one: `brew link --overwrite gitmole` makes the Homebrew install what runs,
and the `ln` line above switches back. The launcher runs on whichever
`python3` is first on your PATH, so that interpreter needs rich and lizard;
installing python@3.14 through Homebrew changes which one that is.

## Tests

```bash
python3 -m unittest discover -s tests -t .
```

`tests/test_golden.py` builds a small synthetic repository, runs the whole
pipeline with the real tools, and compares the plain-text report against
`tests/golden/report.txt`. It skips itself when the tools are not installed.
When a change to the report is intended, regenerate the stored file and
review the diff:

```bash
UPDATE_GOLDEN=1 python3 -m unittest tests.test_golden
```

`GITMOLE_NOW=YYYY-MM-DD` fixes the reference date for file ages, which is
what keeps that report stable. gitmole validates it, announces it at the
start of a run, and records it in `meta.json`, so a forgotten export cannot
silently skew a real report.

[AGENTS.md](https://github.com/antvinni/gitmole/blob/main/AGENTS.md) is the short
version an agent follows, and
[pipeline.md](https://github.com/antvinni/gitmole/blob/main/docs/pipeline.md) is
the loop around all of this: which lane a change is in, what it has to prove, and
which decisions an agent is not allowed to make.

## Rules

gitmole has no model; its judgement is the rules in `filetypes.py`,
`leaks.py`, `identity.py` and `findings.py`. A rule may key on three things
only:

- a path convention of the ecosystem (`vendor/`, `node_modules/`, `dist/`,
  `tests/`, `examples/`, `.min.js`, a lock file's name);
- the shape of a value (a version string, a template field, an environment
  reference, a dotted key path, five words of prose);
- what the repository declares about itself (`linguist-generated` in
  `.gitattributes`, "do not edit" in a file's first lines, a nested LICENSE
  naming other copyright holders, `.mailmap`, a `[bot]` suffix).

A rule must not key on a product name, a person's name, or a word list
learned from one repository. Such a rule fixes the repository it was written
for and guesses about the next one. When the remaining noise needs that
kind of knowledge, the answer is the repository's own ignore mechanism, which
the finding's advice already names (`.betterleaksignore`, `.mailmap`), not a
gitmole change.

## Releases

Versions are git tags and follow semantic versioning. A minor release (0.31.0)
adds something: a finding, a section, a column, an option, an export, a tool.
A patch release (0.30.1) only fixes what is there: a rule that misclassified
a file, merged two people or named the wrong executable, a crash, the docs.
A fix can still move the report and the measured numbers; its release gets
its own record in `docs/measurements/` all the same. While the version is
0.x, a change that removes or renames an option or a JSON key is a minor
release and says so in its notes.

To release: bump `__version__` in `gitmole/__init__.py`,
merge, then tag that commit `vX.Y.Z` and push the tag. CI runs the tests and
checks that the tag matches `__version__`, and then waits: both release jobs run
in the `pypi` environment, which requires a reviewer, so a tag pushed by mistake
or by an agent stops at a prompt instead of publishing a version nobody can
unpublish. Approve it and the job builds the sdist and wheel, creates the GitHub
release with notes generated from the merged pull requests, audits and installs
the formula from source, and pushes the bump to `Formula/gitmole.rb` on a branch
named `formula/<tag>`; merging that is what makes `brew upgrade gitmole` follow.
The tag publishes to PyPI after its own approval. Releases are listed at
https://github.com/antvinni/gitmole/releases.

The job tries to open the pull request for that branch and does not fail if it
cannot: opening one needs the repository's "Allow GitHub Actions to create and
approve pull requests", which is off, because the same setting lets a workflow
approve a pull request and so satisfy this ruleset's extra approval for
unattributed changes — and the formula commit is the bot's. When it cannot, the
run's summary says which branch to open. Publishing must not hang on a pull
request being openable: v0.34.0 and v0.34.1 both failed on that line after the
formula had been audited, built from source and tested, which skipped the publish
job behind it.

So a release is three or four clicks: approve the release job, approve the publish
job, open the formula pull request if the run says to, merge it. `main` takes pull
requests only, and the tests, both determinism jobs and the formula job must be
green before one can merge.

The formula installs the last released tarball, not the checkout, so its
dependencies have to satisfy the released code. A change that swaps or drops
an external tool keeps the old dependency in the formula through the version
bump and the tag, and removes it in a separate commit after the release job
has bumped the formula.

### Moving a pinned tool

`gitmole/tools.py` names the version of every tool a release installs, and
`Formula/gitmole.rb` holds the archive and checksum for each platform;
`tests/test_tools.py` fails when the two disagree. To move one: bump the table,
bump the formula's resource (url and sha256 for both CPUs on both systems),
copy the same urls and hashes into `tools.ARCHIVES` for `--install-tools` (plus
the musl jscpd builds, which only the installer uses), then measure the release, since a tool's own rules decide part of the report and
the measurement is where that shows. The python dependencies are pinned in
`pyproject.toml` for the same reason; `brew update-python-resources` refreshes
their resources and is run by hand when a pin moves, never by the release job,
which would otherwise rewrite the pinned tool resources too.

The tree-sitter grammars are among those pins, one per language, and the
formula carries a prebuilt wheel for each, one per system and CPU: six of the
eleven (cpp, java, php, ruby, rust, typescript) publish source archives that omit
the generated `tree_sitter/parser.h` and build nowhere, so a wheel is the only
form that installs. `tests/test_tools.py` checks that every pin has its four
wheels. They need Python 3.10, so a 3.9
install skips the structure step and says why; `tree-sitter-php` stops at
0.23.9, the last version published with a source archive Homebrew can build.
Moving a grammar is the same work as moving a tool, and the same reason to
measure: what it parses decides the nesting, debt and import-graph findings.

The example reports name the gitmole version that made them. When a release
changes the report, run `bin/render-examples` and commit the new
`docs/examples/*.md`; the README's table of examples carries each run's time,
measured by hand on one machine with nothing else running.
Bumping a pin is a separate decision: it changes the repository's history,
not gitmole's output.

## Determinism

`--json` is the same bytes for the same commit and options, outside its
`envelope` key. `tests/test_golden.py` checks that on the synthetic
repository, and the `determinism` job in CI checks it on gitmole itself on
every push, then attests the report on `main`. A new output that varies from
run to run (a timing, a path, a cache count) belongs in the envelope; a list
a parallel step writes belongs sorted where it is loaded.

## Code layout

The code lives in `gitmole/`: `run.py` plans and executes the tools,
`maat.py` is the standalone change analysis (revisions, coupling and sum of
coupling over logical changesets, test co-change, authors with their minor
contributors, age, ownership over the numstat log, co-authors credited,
sweeping commits and declared ignore-revs left out, oversized fixes out of
the fix pool, tangled commits counted; the file names still say maat because
the layout matches what code-maat produced; degree of authorship, commits
between midnight and 4 am and coupling between components are gitmole's own), `blame.py` is the standalone
code-age pass (its output mimics git-of-theseus so one loader serves both),
`leaks.py` runs betterleaks and hashes the values before anything is
written, `duplicates.py` runs jscpd and keeps the blocks without their text,
`deps.py` runs osv-scanner offline and keeps one row per vulnerable package,
`identity.py` merges author aliases, `load.py` parses the outputs,
`classify.py` gives every table, the watch list and `--risk` one answer for
why a file is out of the scored pool, `findings.py` holds the heuristics,
`coupling.py` folds a directory that changes as one into a cluster,
`watch.py` builds the watch list (the pool, each file's share, the reasons),
`hotspots.py` is the one ranking both it and the hotspots table use,
`trend.py` is complexity over time for the top hotspots, `clean.py` finds
and removes what gitmole left behind, `compare.py` is the difference between
two reports (the findings new, resolved and persisting, the watch list's
moves), `hook.py` is the agent-hook gate behind `--hook`, `sarif.py` the SARIF export,
`signing.py` reads commit signing coverage from the objects, `hygiene.py` the
repository hygiene checks, `imports.py` which packages the tracked source
imports, `licences.py` the declared licences and their SPDX expressions,
`osps.py` the OSPS Baseline controls and the coverage table, `sbom.py` the
CycloneDX document behind `--sbom`, `structure.py` the optional tree-sitter pass
(nesting, cognitive complexity, debt markers, the import graph, and the shapes:
empty catch blocks, addresses in literals, commented-out code), `provenance.py`
trailers, cohorts, commit shape and the agent files, `szz.py` finds
bug-inducing commits by R-SZZ for the backtest, and `render.py` draws the report.
`bin/gitmole` is a thin launcher. `bin/render-banner` regenerates
`docs/banner.svg` from the banner code.
`bin/render-examples` clones the repositories listed in the script under
`$TMPDIR/gitmole-examples/`, pins each to its recorded commit, runs gitmole
with the recorded reference date and writes `docs/examples/<repo>.md`; for
the featured one it prints the report's opening as plain text on stdout. Clones and
outputs are reused on a rerun; delete the directory to start clean.
`python -m gitmole.evaluate CLONE OUT_DIR` replays the watch list at six
cut-off dates against the fixes that followed each, next to the two factor
products the list used to rank by, and lists ranked by churn alone, size
alone, recent fixes, the change entropy variants and ManualUp, with a second
table of what each list costs a reviewer against those fixes (initial false
alarms, lines in the list, Popt); `--szz` adds a table against the files a
commit before each cut-off made buggy, by R-SZZ over the fixes that followed
(`szz.py`: the most recent commit a fix's removed lines blame to, one
`git blame -w -C -C` per fix and file, so minutes on a large history), and
`--labels CSV` a third against independent bug-inducing labels in
ApacheJIT's, Defectors' or a bare-hash shape; the variants include Hassan's
change entropy (`maat.entropy`, decayed over calendar months); the results are in
[validation.md](https://github.com/antvinni/gitmole/blob/main/docs/validation.md).
`python -m gitmole.measure` is the harness of
[measurement.md](https://github.com/antvinni/gitmole/blob/main/docs/measurement.md):
`run --ref TAG` runs a release from its own source over the corpus in
`measure/corpus.json` and writes `docs/measurements/<version>.json`,
`history` does that for every release tag not yet recorded (`--releases minor`
for the first shipped release of each x.y series only), `extras` runs the
current tree's sensitivity sweep, description checks, hook replay and
determinism check, `report` redraws `docs/measurement-history.md` and the
graphs in `docs/evolution/`, and `labels dump|score` handle the hand labels.
Clones, fixtures and run outputs go under `$GITMOLE_MEASURE_DIR` (default
`$TMPDIR/gitmole-measure`); `GITMOLE_LABELS_DIR` points at ApacheJIT's
`dataset/` for the holdout. The timed runs are sequential and share the
machine with nothing, so the recorded times and memory are comparable, and
each records the load average it ran under. The rankings at cut-offs are not
timed, so once every timed run is over they are computed side by side
(`--jobs`, default 3; 1 is the old sequential round).

The change analysis (hotspots, coupling, ownership, age) is gitmole's own
code, written after the ideas in Adam Tornhill's code-maat but sharing no
code with it. The bug-inducing commits in `szz.py` follow Rosa et al.'s
R-SZZ as pyszz_v2 describes it, written fresh over `git diff` and `git
blame`, sharing no code with it. The structure pass in `structure.py` borrows three ideas
and no code: cognitive complexity from SonarSource's published
specification (simplified: one increment per run of boolean operators, and
`else if` flat), nesting and the bumpy road from CodeScene's code-health
documentation, and the debt markers from Maldonado and Shihab; the walk,
the metrics and the import resolution are written fresh over py-tree-sitter.

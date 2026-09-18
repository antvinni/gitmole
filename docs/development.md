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

Versions are git tags. To release: bump `__version__` in `gitmole/__init__.py`,
merge, then tag that commit `vX.Y.Z` and push the tag. CI runs the tests, checks
that the tag matches `__version__`, builds the sdist and wheel, and creates the
GitHub release with notes generated from the merged pull requests and the
artefacts attached. The release job then bumps `Formula/gitmole.rb` on main
to the new release, so `brew upgrade gitmole` follows within minutes; the tag
also publishes to PyPI. Releases are listed at
https://github.com/antvinni/gitmole/releases.

The formula installs the last released tarball, not the checkout, so its
dependencies have to satisfy the released code. A change that swaps or drops
an external tool keeps the old dependency in the formula through the version
bump and the tag, and removes it in a separate commit after the release job
has bumped the formula.

The example reports name the gitmole version that made them. When a release
changes the report, run `bin/render-examples` and commit the new
`docs/examples/*.md` and README text block together.
Bumping a pin is a separate decision: it changes the repository's history,
not gitmole's output.

## Code layout

The code lives in `gitmole/`: `run.py` plans and executes the tools,
`maat.py` is the standalone change analysis (revisions, coupling, authors,
age, ownership over the numstat log; the file names still say maat because
the layout matches what code-maat produced), `blame.py` is the standalone
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
moves), and `render.py` draws the report.
`bin/gitmole` is a thin launcher. `bin/render-banner` regenerates
`docs/banner.svg` from the banner code.
`bin/render-examples` clones the repositories listed in the script under
`$TMPDIR/gitmole-examples/`, pins each to its recorded commit, runs gitmole
with the recorded reference date and writes `docs/examples/<repo>.md`; for
the featured one it prints the README's text block on stdout. Clones and
outputs are reused on a rerun; delete the directory to start clean.
`python -m gitmole.evaluate CLONE OUT_DIR` replays the watch list at six
cut-off dates against the fixes that followed each, next to the two factor
products the list used to rank by, and lists ranked by churn alone, size
alone and recent fixes; the results are in
[validation.md](https://github.com/antvinni/gitmole/blob/main/docs/validation.md).

The change analysis (hotspots, coupling, ownership, age) is gitmole's own
code, written after the ideas in Adam Tornhill's code-maat but sharing no
code with it.

# Development

Setting up a checkout, running the tests, cutting a release, and where the code lives; back to [the README](https://github.com/antvinni/gitmole#readme).

## Setup

Homebrew for the three tools, `brew install scc git-sizer betterleaks`.
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

## Code layout

The code lives in `gitmole/`: `run.py` plans and executes the tools,
`maat.py` is the standalone change analysis (revisions, coupling, authors,
age, ownership over the numstat log; the file names still say maat because
the layout matches what code-maat produced), `blame.py` is the standalone
code-age pass (its output mimics git-of-theseus so one loader serves both),
`leaks.py` runs betterleaks and hashes the values before anything is
written, `identity.py` merges author aliases, `load.py` parses the outputs,
`findings.py` holds the heuristics, and `render.py` draws the report.
`bin/gitmole` is a thin launcher. `bin/render-banner` regenerates
`docs/banner.svg` from the banner code.

The change analysis (hotspots, coupling, ownership, age) is gitmole's own
code, written after the ideas in Adam Tornhill's code-maat but sharing no
code with it.

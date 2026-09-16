# Polish round: own complexity, source-first tables, a risk gate, PyPI, one install path, a shorter README

Date: 2026-09-16. Status: approved in discussion, not yet built.

## Goal

Six independent improvements, each its own pull request in the order below.
None changes what the report measures; two change what the default report
shows, one adds a CI gate, three are packaging and documentation.

## 1. The project passes its own complexity finding

`gitmole .` lists `cli._analyse` (complexity 35) and `findings.knowledge_loss`
(34) at the top of Complex functions; both grew during the history-insights
work. Each is split into named helpers so that the two named ones sit under 15 and
nothing in `cli.py` or `findings.py` reaches 20. Four other functions sit
between 21 and 23 (`run.collect_meta`, `render.timeline_section`,
`watch.risks`, `render.hotspots_section`); none is long enough to trip the
brain-methods finding, and they are left for a later round so this PR stays
a bounded refactor.
Behaviour is pinned by the existing suite and the golden report: neither
changes. The 18 minor findings deferred from the history-insights reviews are
taken in the same PR, except those already fixed or ruled unreachable; the
plan lists which.

## 2. Source files first in the tables

Findings already leave test files out; the tables do not. In the default
report:

- **Hotspots** and **Complex functions** rank source files only; test files
  are hidden, and a caption says how many (`N test files hidden; --full shows
  them`). `--full` shows every row, tests included, as today.
- **Change coupling** hides pairs with a test file on either side, since a
  file changing with its own test carries no information; same caption
  rule, same `--full` behaviour.
- Markdown export follows the default rule unless `--full`.
- The watch list and the findings are unchanged (already source-only).
- `filetypes.is_test_path` is the one definition of "test file".

## 3. A CI gate on change risk

`--risk BASE` prints a total but cannot fail a build. A new
`--risk-threshold N` exits 3 when the change-risk total exceeds N. It requires
`--risk` (error, exit 2, otherwise). The JSON export is unchanged; the README's
CI example gains a line with it. The threshold is a plain number on the same
scale as the `total` the section prints.

## 4. PyPI, by trusted publishing

A `publish` job after `release` on every `v*` tag uploads the sdist and wheel
built in the release job to PyPI with OpenID Connect (no API token stored),
using `pypa/gh-action-pypi-publish` under a GitHub environment named `pypi`.
After the first successful publish, `pipx install gitmole` works and the
README's install lines become `pipx install gitmole` (pinned:
`pipx install gitmole==X.Y.Z`); the git-URL form stays as the way to install
main. What only the owner can do: register the pending trusted publisher on
PyPI (owner `antvinni`, repository `gitmole`, workflow `ci.yml`, environment
`pypi`) before the first tag that should publish. Until it exists, the job
fails on upload; the release itself and the formula bump are unaffected
because they run first.

## 5. One developer install path

`bin/install.sh` is deleted. The Development section describes the developer
setup in three commands: Homebrew for the tools, `pip install -e .` in a
virtual environment (or `python3 -m pip install --user rich lizard` for the
checkout-and-symlink style this machine uses), and the symlink line. The
License section's sentence about the script goes.

## 6. A shorter README

The README is 584 lines. Two pages move out to `docs/`:

- `docs/tools.md`: the tool-set rationale ("The tool set" prose and
  "Considered and left out"); the README keeps the table and a link.
- `docs/output.md`: "The output directory" table and "How to read the
  output"; the README's "The terminal report" section stays, with a link.

A third page, `docs/example.md`, holds the full example report; the README
keeps its header, findings and watch list. Result: the README at about 450
lines, from 591, reading as principles, install, run, example, report guide,
development, licence. The under-400 figure first written here was a target;
going lower would have moved the report guide out of the front page, which
is the part a new reader needs most.

## Constraints shared by all six

No new runtime dependency. Every PR keeps `python3 -m unittest discover -s
tests -t .` green and the golden report unchanged unless the spec above says
the default report changes (item 2 only; the golden repository has no test
files, so even there it should not change). Commit trailer as before.

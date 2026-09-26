# Contributing to gitmole

Thanks for helping. This page is short on purpose; the details of setting
up a checkout, running the tests and cutting a release are in
[docs/development.md](https://github.com/antvinni/gitmole/blob/main/docs/development.md).

## Bugs

Open an [issue](https://github.com/antvinni/gitmole/issues) with:

- the gitmole version (`gitmole --version`) and your OS;
- the exact command you ran and what you expected instead;
- `run.log` from the output directory, which holds every command gitmole
  ran and its stderr.

Never paste a real secret, and do not attach `secrets.json` from a private
repository. If the bug is in the secrets step, describe the shape of the
value instead.

## Ideas

Open an issue before writing code for anything beyond a fix, so the design
is agreed before the work. The bar is the README's principles: a change
gets in when it tells the reader something that changes what they do next,
works on any stack from the git log, blame and the files alone, runs
offline, and adds no dependency unless one is unavoidable. A finding that
is merely interesting does not get in.

## Pull requests

1. Fork, branch from `main`, one change per pull request.
2. Write the test first and watch it fail; then make it pass. Every change
   ships with a test that fails without it.
3. Run the whole suite: `python3 -m unittest discover -s tests -t .`
4. If the report is meant to change, regenerate the golden file with
   `UPDATE_GOLDEN=1 python3 -m unittest tests.test_golden` and review the
   diff of `tests/golden/report.txt` in the same pull request.
5. Update the docs in the same pull request: a new option goes in
   `docs/cli.md`, a new section or output file in `docs/output.md`.
6. Describe the why in the pull request, not only the what.

Pull requests are squash-merged, so the pull request title becomes the
commit subject. Keep it a sentence about the outcome, in the style of
`git log`.

## Writing tests

The suite has conventions worth copying:

- Secret-shaped values are built at runtime (`"0123456789abcdef" * 2`,
  `"AKIA" + "X" * 16`), never written as literals. betterleaks and GitHub
  push protection scan this repository too.
- The external tools are not called in unit tests. A stub script on a
  temporary `PATH` stands in for scc, git-sizer, betterleaks, jscpd or osv-scanner, records the
  arguments it was called with and prints a canned report; see the
  `Script` classes in `tests/test_leaks.py`, `tests/test_duplicates.py` and `tests/test_deps.py`.
- Only `tests/test_golden.py` runs the real tools, and it skips itself when
  they are not installed.
- `GITMOLE_NOW=YYYY-MM-DD` fixes the reference date, so tests that depend on
  file ages stay stable.

## Adding or swapping an external tool

One tool per question. A new tool needs a paragraph in
[docs/tools.md](https://github.com/antvinni/gitmole/blob/main/docs/tools.md)
saying which question it answers that nothing already in the set does, and
must be free, offline and installable as a single binary or a pip package.
The change also touches `REQUIRED_TOOLS` in `gitmole/run.py`, the
`depends_on` list in `Formula/gitmole.rb`, the install line in
`.github/workflows/ci.yml`, and the install docs. The formula installs the
last released tarball, so a swap keeps the old dependency in the formula
until the release after the change; the development doc explains the order.

## Security

To report a vulnerability, use
[private vulnerability reporting](https://github.com/antvinni/gitmole/security/advisories/new)
rather than a public issue. Anything that would let a secret value reach
the output directory, the terminal or an export counts; the
[security policy](https://github.com/antvinni/gitmole/blob/main/.github/SECURITY.md)
says what else does.

## Conduct

Everyone taking part is expected to follow the
[code of conduct](https://github.com/antvinni/gitmole/blob/main/.github/CODE_OF_CONDUCT.md).

## Licence

gitmole is MIT. By contributing you agree that your contribution is
licensed the same way.

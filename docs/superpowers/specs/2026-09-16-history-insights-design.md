# History insights: reverts, knowledge loss, change risk, complexity trend, watch-list backtest

Date: 2026-09-16. Status: approved in discussion, not yet built.

## Goal

Five analyses that gitmole can compute from the three inputs it already reads
(`git log --numstat`, `git blame`, the file text at a commit) and that each
change what the reader does next. Each is its own pull request in the order
below, so one can be dropped without touching the others.

## Non-goals

- No new Python dependency. Everything is stdlib plus the tools gitmole already
  requires (scc, git-sizer, gitleaks) and lizard.
- No new input file. Leavers are derived from the log; a leaver list can be
  added later if the derivation is wrong often.
- No prediction model. The backtest validates the existing watch-list score;
  it does not replace it.
- No forge data (pull requests, reviews, CI). Everything runs against a clone.

## Shared rules

- The default terminal report gains exactly four small marks: a pulse phrase
  for reverts, a "trend" column on the hotspots table, one caption line under
  the watch list for the backtest, and the change-risk section only when
  `--risk` is given. Everything else is `--full`, `--json`, or a finding that
  fires only past a threshold.
- Every finding carries a next step (`advice`) that names a file, area or
  person, as the existing rules do in `findings.py`.
- Every new output file is listed in `run.OUTPUTS` so a reused output
  directory never shows a previous run's data, and is read by `load.load_report`
  with a missing file giving an empty value.
- Test files (`filetypes.is_test_path`) are left out of every finding that
  names a file, as today. Bots (`meta["bots"]`) are left out of every count of
  people.
- `--since` bounds the change log as it does today. Knowledge loss and the
  backtest always use the whole history, and say so in their captions when a
  window is set, as the People section does.
- Reference date: `GITMOLE_NOW` when set, otherwise today, as `maat.py` does.
  Knowledge loss measures "gone" against the repository's last commit date, not
  the reference date (see below).

## 1. Reverts

**Data.** `maat.py` already parses every commit's subject. A commit is a revert
when its subject starts with `Revert ` (git's own convention; case-sensitive,
the quote that follows is not required).

**Computation.** In `maat.activity()`: `revert_commits` (count in the window)
and `reverted` (a Counter of file path to number of reverting commits that
touched it, test files included so the table is honest, excluded from the
advice). Both are written into `activity.json`.

**Report.**
- Pulse: `N% of commits are reverts`, only when `revert_commits > 0`.
- Finding `Reverts`: fires when reverts are at least 5% of the commits in the
  window, or at least 5 in number; `warning` at 10%. Statement: `N of M commits
  are reverts; a/b.py was reverted 3 times, c.py twice.` Advice: `Add a check
  before merge for a/b.py; it is the file most often backed out.` When every
  reverted file is a test file, the advice names none and says so.
- `--full`: no table; the reverted files are in the JSON under `activity`.

**Tests.** `test_maat.py`: subjects with and without the prefix; counts per
file. `test_findings.py`: thresholds at 5% / 5 commits / 10%; test-only case.
`test_render.py`: the pulse phrase appears only when there are reverts.

## 2. Knowledge loss

**Who is gone.** From `activity.json` `authors[name].last` (aliases already
applied by `maat.py`): a person is gone when their last commit is more than
`--gone MONTHS` (default 12) before `meta["last_date"]`. Measuring against the
last commit rather than the reference date keeps a clone that was last fetched
a year ago from marking everyone as gone. Bots are never people. The list of
gone names is computed once in a new module `gitmole/loss.py` and not stored;
it is cheap and the JSON export includes the result of the finding.

**What was lost.**
- `surviving`: share of surviving lines (`theseus_authors`) written by gone
  people, over all surviving lines. Empty when the blame pass did not run.
- Per area (`knowledge.areas` over source ownership rows): `lost` share of
  lines added by gone people. Areas are the same ones the knowledge map shows.

**Report.**
- Finding `Knowledge loss`: fires at 10% of surviving code by gone people;
  `warning` at 30%. Statement: `3 people with no commits since 2024-11 wrote
  34% of the code that survives today: Hayden (28%), sephrat (4%), Chip (2%).
  Areas mostly theirs: frontend.old/ (100%), docs/ (91%).` Advice: `Pair
  someone on frontend.old/ first; nobody who wrote it is around to ask.` When
  the blame pass did not run, the finding uses the per-area lost share instead
  (fires at 10% of all lines added) and says `from lines added, not a blame`.
- Knowledge map under `--full`: a `lost` column (share of the area's lines
  added by gone people), and `(gone)` after an owner's name in every mode.
- Caption on the knowledge map when anyone is gone: `gone = no commits in the
  12 months before 2025-11-09`.
- Flag: `--gone MONTHS`, default 12, recorded in `meta.json` as `gone_months`
  so `--no-run` uses the same window.

**Tests.** `test_loss.py`: gone set from synthetic activity with the window
relative to last commit; bots excluded; surviving and per-area shares.
`test_findings.py`: thresholds, the no-blame fallback, advice names the
largest area. `test_render.py`: `(gone)` marker and the `lost` column.

## 3. Change risk

**Input.** `gitmole PATH --risk BASE`. The touched files are `git diff
--name-only BASE...HEAD` (three dots: changes since the merge base) run in the
repository, paths as the change analysis records them. Works with `--no-run`
against an earlier output directory, using `meta["path"]` as the repository.
Not available for remote targets or portfolio mode (error, exit 2).

**Computation.** `watch.risks(report)` already scores every source file still
in the tree that changed more than once. `watch.change_risk(report, files)`
returns one row per touched file: the score and reasons when the file has a
watch row; otherwise score 0 and a reason of `new file` (not in the size data),
`changed once`, or `test file`. Total is the sum of scores; the row count
of files that appear in the top 15 of the watch list is reported separately.

**Report.** A section `Change risk (12 files since main)` after the watch
list: file, score as a 0-10 bar scaled to the highest watch score in the repo,
why. Caption: `total 3.4; 2 of these files are on the watch list`. Rows sorted
by score, cap 15 by default, all under `--full`. In JSON: `change_risk`
with `base`, `files` and `total`. No exit-code gate in this version.

**Tests.** `test_watch.py`: scoring of touched files against a synthetic
report, the three zero-score reasons, ordering. `test_cli.py`: the flag runs
git diff in the repository, refuses remote targets, works with `--no-run`.

## 4. Complexity trend

**Step.** `gitmole/trend.py`, run as a pipeline step named `trend` with
`deps: ["scc", "change analysis"]`, as `python -m gitmole.trend OUT_DIR
--samples 12`, with `PYTHONPATH` set by `run.execute` to the package's parent
directory so the script can use the package's loader and hotspot ranking. It
picks the ten top hotspots that are still in the tree (`hotspots.ranked`,
`code` not None, test files included since the table shows them).

**Sampling.** Up to `--samples` points spread evenly between the first and
last commit date (fewer when the history is shorter than that many months;
at least two). For each point: `git rev-list -1 --before=DATE HEAD`; for each
file, `git show REV:PATH` into a temporary directory under the same relative
path (so scc detects the language); one `scc --by-file --format json` over
that directory. A file absent at that commit gets no sample there. Output
`trend.json`: `{"samples": [DATE, ...], "files": {PATH: [[DATE, complexity,
code] ...]}}`, written atomically. Temporary files are removed.

**Report.**
- Hotspots table, default and full: a `trend` column: the change in
  complexity between the sample nearest to twelve months before the last
  commit and the latest sample, as `+40%`, `-12%`, `=` (within 10%), or `-`
  when there are fewer than two samples for the file. Under `--full` a
  sparkline (`▁▂▃▅▇`) of all samples replaces the percentage.
- Finding `Hotspots getting more complex`: fires when at least three of the
  ten grew by 25% or more over the last year, `warning` when the top hotspot
  is one of them. Statement lists the growers with percentages. Advice:
  `Split a/b.py before the next change; its complexity grew 60% in a year.`
- When the step did not run or timed out, the column shows `-` and the
  `meta["trend"]["status"]` is recorded as the functions step's is.

**Tests.** `test_trend.py`: sampling dates from a span; a synthetic repository
where one file grows in complexity across commits; absent-at-commit handling;
`--samples`. `test_render.py`: the column, the sparkline, the `-` cases.
`test_findings.py`: thresholds.

## 5. Watch-list backtest

**Cut-off.** `maat.py` gains `--until YYYY-MM-DD`: commits with author date
strictly before it, applied together with `--since`. `T` is six months before
`meta["last_date"]`. The backtest is skipped, with the caption `too little
history to backtest`, when the first commit is less than six months before `T`
(so at least twelve months of history overall).

**Step.** `gitmole/backtest.py`, run as `python -m gitmole.backtest OUT_DIR
--until T --now T`, `deps: ["git-log", "change analysis"]`. It runs
`maat.write_all` on the same log export with `until=T, now=T` into
`OUT_DIR/backtest/`, finds `REV = git rev-list -1 --before=T HEAD`, exports
the tree at REV with `git archive REV | tar -x` into a temporary directory,
runs `scc --by-file --format json` there into `OUT_DIR/backtest/size.json`,
and writes `OUT_DIR/backtest/meta.json` with `{"now": T, "last_date": T}`.
The functions step is not rerun: lizard only names functions in reasons and
does not enter the score.

**Evaluation.** In `watch.backtest(report, past)`: `listed` is the top 15 of
`watch.risks(past)`; `fixed` is the set of source files with a fix commit in
`(T, last_date]` from the current `fixes` table (a file's `last-fix` after T,
excluding test files); `hits = listed ∩ fixed`. Also the base rate: the share
of source files in the tree at T that were fixed since, so the reader can see
the lift. Result: `{"t": T, "listed": 15, "fixed": 23, "hits": 9,
"base_rate": 0.02}`.

**Report.** One caption line under the watch list, default and full: `6 months
ago this list would have named 9 of the 23 files fixed since (a random 15
would name 0.5)`. In JSON under `watch_backtest`. When skipped: the reason.

**Tests.** `test_maat.py`: `--until`. `test_backtest.py`: a synthetic repository
with commits across 18 months where a file that churned early is fixed late;
the skip rule. `test_watch.py`: the evaluation on synthetic tables, including
the random baseline. `test_render.py`: the caption and the skip caption.

## Implementation order

1. Reverts.
2. Knowledge loss.
3. Change risk.
4. Complexity trend.
5. Watch-list backtest.

The golden repository's eight commits fire none of the new findings, so PRs
1 to 3 leave `tests/golden/report.txt` unchanged. PR 4 adds the `trend`
column and PR 5 the backtest caption (the golden history spans 17 months, so
the backtest runs there and the caption carries real numbers, to be checked by
hand against the golden commits); each regenerates the golden file with
`UPDATE_GOLDEN=1` and reviews the diff, which must contain only that change. Mealie is the manual check for every PR:
run it, read the new lines, confirm the numbers by hand.

## Out of scope

Leaver list input, an exit-code gate for `--risk`, a defect-prediction model,
identifier or comment analyses, lead-time and PR-size metrics, a Conway
overlay with a team map.

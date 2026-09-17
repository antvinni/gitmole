# Command line

Every target form and option, the exports, the CI gates, and what gitmole does to stay fast on a big repository; back to [the README](https://github.com/antvinni/gitmole#readme).

## Targets

```bash
gitmole .                          # the clone you are in
gitmole /path/to/clone             # any local clone
gitmole owner/repo                 # clones into a temp dir first, with gh or plain git
gitmole https://github.com/o/r     # same, from a URL
gitmole 'owner/*'                  # every non-archived repo of a user or org
```

The last form is portfolio mode: each repository is cloned and analysed in
turn into `analysis-<owner>/<repo>/`, then one table summarises them all with
commits, people, the top author's share of surviving code, secrets found,
size, and the worst finding per repo. `--markdown` and `--json` write a
portfolio document with every repo's findings; `--fail-on` looks across all
of them.

All tools run concurrently, so a run takes about as long as the slowest tool.
Tool stderr goes to `run.log` in the output directory, not the terminal.
Ctrl-C kills every running step, including their child processes, and exits
with code 130.

A remote or portfolio target is cloned into a temp directory that is removed
when the run ends. `gitmole --clean [DIR]` lists what gitmole left behind,
temp clones from earlier versions and `analysis-*` output directories under
DIR (default the current directory; a clone as DIR includes its own output
next to it), with sizes, and deletes them after one y/N question.

## Options

| Option | What it does |
|---|---|
| `--full` | Every section, column and row. Adds the hotspots, size, activity and code age tables; the default report keeps the columns you read, caps each table, elides long paths in the middle, hides test files, deleted files and vendored code, and shows a directory that changes as one as a single coupling row. |
| `--out DIR` | The output directory. Default: `analysis-<repo>` next to a local clone, or in the current directory for a remote target. |
| `--no-run` | Skip the tools and re-render the report from the output directory of an earlier run. Works with the exports and `--risk`. |
| `--since WHEN` | Bound the history by author date: `2y`, `18m`, `90d` or a `YYYY-MM-DD` date. People, activity, timeline, hotspots and coupling then describe the current team rather than the founders. File ages and code age always cover the whole history, identity aliases are still merged over all of it, and an empty window is an error. |
| `--plots` | Also draw the git-of-theseus code-age and survival charts. Needs `gitmole[plots]`. |
| `--file-types LIST` | Which extensions count as code, comma-separated, or `all`. The default is a built-in source list plus names like Makefile and Dockerfile. |
| `--list-file-types` | List the file types in the tree with counts and whether each counts as code, then exit. |
| `--clean [DIR]` | List the directories gitmole created, temp clones and `analysis-*` outputs under DIR, with their sizes, and delete them after a y/N question. The temp clones show as one row with their count; `--full` lists each one. Exit 0 whether you answer yes or no, 2 without a terminal. |
| `--yes` | With `--clean`: delete without asking. For scripts and pipes. |
| `--ignore-data` | Exclude data-like files (csv, json, lock files, minified and vendored assets) from code age, function metrics, duplicates and plots. |
| `--ignore GLOB` | An extra ignore pattern for the same steps. Repeatable. |
| `--workers N` | How many tools run at once. |
| `--timeout S` | Seconds any single tool may run before it is killed. Default 900. A killed tool is marked in the report and the rest still renders. |
| `--time-budget S` | Skip the code-age pass when its projected time exceeds this. Default 60. |
| `--budget N` | Skip the plots above this many git blames. Default 50,000. |
| `--deep` | Run code age, plots and the duplicates step regardless of their budgets. |
| `--gone MONTHS` | How long without a commit counts as gone, measured before the last commit. Default 12. |
| `--markdown PATH` | Write the report as Markdown to PATH, or `-` for stdout. |
| `--json PATH` | Write every table, the watch list and the findings as JSON to PATH, or `-` for stdout. |
| `--fail-on LEVEL` | Exit 3 if any finding is at `critical`, `warning` or `info` or worse. |
| `--risk BASE` | Score the files changed since BASE (the merge base with HEAD) with the watch list's score (each file's share, in percent, of the repository's revisions × lines of code), in one extra section with a total. Needs a local path; works with `--no-run`, and the JSON carries the total. |
| `--risk-threshold N` | With `--risk`: exit 3 when the changed files together hold more than N percent. |

## Exports and CI

```bash
gitmole . --markdown report.md         # the same report as a Markdown document
gitmole . --json report.json           # every table, the watch list and the findings, machine-readable
gitmole . --markdown - | pbcopy        # - means stdout; banner and progress go to stderr
gitmole . --fail-on warning            # exit 3 if any finding is a warning or worse
gitmole . --risk main --risk-threshold 10  # exit 3 if the changed files hold over 10% of the repo's revisions × lines
```

Each finding in the JSON carries, next to its severity, title, detail and
advice, a `rule` (the rule's `id` and the thresholds it fired on) and its
`evidence` (the numbers those thresholds were compared with, lists capped
at ten), so a finding can be checked, filtered or tracked over time without
parsing its sentence:

```json
{"severity": "warning", "title": "Bug magnets",
 "rule": {"id": "bug_magnets", "min_recent": 3, "warn_at": 5, "window_months": 6, "fix": "the commit subject says so"},
 "evidence": {"count": 2, "files": [{"file": "lib/url.c", "recent_fixes": 5, "fixes": 41}]}}
```

The JSON's `watch` rows carry a `trend` field: the change in the file's
complexity over a year (`+54%`, `=` for under ten per cent either way, `-`
when there is nothing to compare), and null when the file was not among the
ten sampled hotspots.

A CI job that runs
`gitmole . --fail-on critical --markdown - >> "$GITHUB_STEP_SUMMARY"` blocks
on secrets in source files and still posts the report. Secrets found only in
test files are a warning, so gate on `warning` to block on those too. Both
exports also work with `--no-run` against an earlier output directory.
`--risk-threshold` needs `--risk`; it exits 3 when the files changed since
main hold more than 10% of the repository's revisions × lines of code, and
the total prints in the Change risk caption.

The scale changed in 0.8.0: before, the total was a sum of factor-product
scores with no fixed unit. A threshold chosen for 0.7 has to be chosen
again; run `gitmole . --risk main` on a few merged changes and read the
totals.

## Big repositories

Blame and the duplicate finder are the two costs that scale with repo size.
gitmole keeps them in check:

- the code-age table comes from one `git blame` per tracked code file at
  HEAD, run on all but two CPU cores at low priority so the machine stays
  usable. That is all the table needs;
- blame cost depends on file size and history depth, not file count, so
  gitmole times a sample of 25 blames first and projects the whole pass. If
  the projection exceeds `--time-budget` (default 60 seconds) the pass is
  skipped with a message, and the report shows net lines added per year from
  the change log instead, labelled as an approximation;
- the plots need history, so `--plots` runs git-of-theseus with monthly
  sampling (tracked files × samples blames) on top, skipped above
  `--budget` (default 50,000 blames);
- `--deep` forces both regardless of the budgets;
- the duplicates step runs jscpd over the tracked code files, in seconds,
  but jscpd holds every token in memory: about a gigabyte per 25 MB of
  tracked text. Above 80 MB of tracked text the step is skipped with a
  message that says how much memory it would need; `--deep` forces it. Older
  scripts that pass `--duplicates` still parse; the flag does nothing now;
- `--ignore-data` excludes data-like files (csv, json, lock files, minified
  and vendored assets) from blame, from the function metrics and from the
  duplicates step, and `--ignore GLOB` adds your own patterns, repeatable.
  Both shrink the blame count a lot on repos full of exports and fixtures.

Two steps read history rather than the working tree, and both are bounded.
The trend behind the hotspots' `trend` column, which also feeds the watch
list's complexity reason, runs scc over the ten top hotspots at up to
twelve sampled commits, one run per sample, not one per file. The backtest
behind the watch list's caption is a second change analysis over the same
log with the window closed six months before the last commit, plus one
checkout of the tree as it was then, exported under the output directory
and removed again when the step ends.

A tool that exceeds `--timeout` is killed along with its child processes,
and the rest of the report still renders: whatever the tool had written is
read as no data, the header's second line names the step (`size timed out`),
and `meta.json` records every step's outcome under `steps`.

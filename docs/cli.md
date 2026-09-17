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
| `--full` | Every column and every row. The default report keeps the columns you read, caps each table, elides long paths in the middle, hides test files, deleted files and vendored code, and shows a directory that changes as one as a single coupling row. |
| `--out DIR` | The output directory. Default: `analysis-<repo>` next to a local clone, or in the current directory for a remote target. |
| `--no-run` | Skip the tools and re-render the report from the output directory of an earlier run. Works with the exports and `--risk`. |
| `--since WHEN` | Bound the history by author date: `2y`, `18m`, `90d` or a `YYYY-MM-DD` date. People, activity, timeline, hotspots and coupling then describe the current team rather than the founders. File ages and code age always cover the whole history, identity aliases are still merged over all of it, and an empty window is an error. |
| `--plots` | Also draw the git-of-theseus code-age and survival charts. Needs `gitmole[plots]`. |
| `--file-types LIST` | Which extensions count as code, comma-separated, or `all`. The default is a built-in source list plus names like Makefile and Dockerfile. |
| `--list-file-types` | List the file types in the tree with counts and whether each counts as code, then exit. |
| `--clean [DIR]` | List the directories gitmole created, temp clones and `analysis-*` outputs under DIR, with their sizes, and delete them after a y/N question. The temp clones show as one row with their count; `--full` lists each one. Exit 0 whether you answer yes or no, 2 without a terminal. |
| `--yes` | With `--clean`: delete without asking. For scripts and pipes. |
| `--duplicates` | Also look for duplicated blocks. Minutes and gigabytes on a large repo; see below. |
| `--ignore-data` | Exclude data-like files (csv, json, lock files, minified and vendored assets) from code age, function metrics and plots. |
| `--ignore GLOB` | An extra ignore pattern for the same steps. Repeatable. |
| `--workers N` | How many tools run at once. |
| `--timeout S` | Seconds any single tool may run before it is killed. Default 900. A killed tool is marked in the report and the rest still renders. |
| `--time-budget S` | Skip the code-age pass when its projected time exceeds this. Default 60. |
| `--budget N` | Skip the plots above this many git blames. Default 50,000. |
| `--deep` | Run code age and plots regardless of the two budgets. |
| `--gone MONTHS` | How long without a commit counts as gone, measured before the last commit. Default 12. |
| `--markdown PATH` | Write the report as Markdown to PATH, or `-` for stdout. |
| `--json PATH` | Write every table, the watch list and the findings as JSON to PATH, or `-` for stdout. |
| `--fail-on LEVEL` | Exit 3 if any finding is at `critical`, `warning` or `info` or worse. |
| `--risk BASE` | Score the files changed since BASE (the merge base with HEAD) with the watch list's score, in one extra section with a total. Needs a local path; works with `--no-run`, and the JSON carries the total. |
| `--risk-threshold N` | With `--risk`: exit 3 when the change-risk total exceeds N. |

## Exports and CI

```bash
gitmole . --markdown report.md         # the same report as a Markdown document
gitmole . --json report.json           # every table, the watch list and the findings, machine-readable
gitmole . --markdown - | pbcopy        # - means stdout; banner and progress go to stderr
gitmole . --fail-on warning            # exit 3 if any finding is a warning or worse
gitmole . --risk main --risk-threshold 5   # exit 3 if the changed files are too risky
```

A CI job that runs
`gitmole . --fail-on critical --markdown - >> "$GITHUB_STEP_SUMMARY"` blocks
on secrets in source files and still posts the report. Secrets found only in
test files are a warning, so gate on `warning` to block on those too. Both
exports also work with `--no-run` against an earlier output directory.
`--risk-threshold` needs `--risk`: it exits 3 when the files changed since
main add up to more than 5 on the watch-list scale; the total prints in the
Change risk caption.

## Big repositories

Blame and lizard's duplicate finder are the two costs that scale with repo
size. gitmole keeps them in check:

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
- the duplicate finder is off by default. It keeps a hash node per token,
  so on a repo of a few thousand files it runs for minutes at one or two
  gigabytes per worker, which is why `--duplicates` also caps that step at
  two workers. Function metrics without it take a second or two;
- `--ignore-data` excludes data-like files (csv, json, lock files, minified
  and vendored assets) from blame and from the function metrics, and
  `--ignore GLOB` adds your own patterns, repeatable. Both shrink the blame
  count a lot on repos full of exports and fixtures.

Two steps read history rather than the working tree, and both are bounded.
The trend behind the hotspots' `trend` column runs scc over the ten top
hotspots at up to twelve sampled commits, one run per sample, not one per
file. The backtest behind the watch list's caption is a second change
analysis over the same log with the window closed six months before the
last commit, plus one checkout of the tree as it was then, exported under
the output directory and removed again when the step ends.

A tool that exceeds `--timeout` is killed along with its child processes,
marked in the report, and the rest of the report still renders.

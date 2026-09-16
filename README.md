<img src="docs/banner.svg" width="912" alt="gitmole">

# gitmole

A local, offline toolkit for digging into any cloned git repository: who
works on it, where the risk is, how old the code is, whether the repo itself
is healthy, and whether anything sensitive was ever committed.

Everything runs against a clone on your machine. No tool here needs a GitHub
token, uploads data, or phones home.

## The tool set

One tool per question. Together they cover most of what a single-command
analysis can tell you about a repo.

| Question | Tool | Install |
|---|---|---|
| What is this repo, at a glance; who commits, when, how much churn | gitmole itself, from the git log | built in |
| How big is the codebase, per language | [scc](https://github.com/boyter/scc) | brew |
| Is the repo itself healthy (huge blobs, deep trees) | [git-sizer](https://github.com/github/git-sizer) | brew |
| Where is the risk: hotspots, coupling, ownership | gitmole's own change analysis over `git log --numstat` | built in |
| How old is the surviving code, per year and author | gitmole's own blame pass (one `git blame` per file at HEAD) | built in |
| Code-age and survival plots over time | [git-of-theseus](https://github.com/erikbern/git-of-theseus) | pip, opt-in with `--plots` |
| Per-function complexity, length, parameters; duplicated blocks with `--duplicates` | [lizard](https://github.com/terryyin/lizard) | pip, installed with gitmole; tracked code files only |
| Have secrets ever been committed | [gitleaks](https://github.com/gitleaks/gitleaks) | brew |

Three external tools: scc for size, git-sizer for repo health, gitleaks for
secrets. Everything about history is computed by gitmole from `git log`.
lizard adds function-level metrics for two dozen languages when it is
installed, in well under a second per thousand files; its duplicate finder
is minutes and gigabytes on a large repo, so it is off unless you pass
`--duplicates`. git-of-theseus only adds the plots, so it is off by default
and only needed with `--plots`. gitleaks should never be skipped on a repo you did
not author.

What gitmole does not do: dead-code detection (that needs a symbol graph per
language) and test coverage (that needs the project's own test run). It will
not guess at either.

### Considered and left out

- **hercules**: overlaps the change analysis and git-of-theseus, and the project is
  archived. Add it only if you want its burndown charts specifically.
- **tokei**: duplicates scc without the effort estimate.
- **git-extras**, **onefetch**, **git-quick-stats**: convenient summaries, but
  everything they report is now computed from the log by gitmole itself, so
  they were dropped to shrink the install.
- **GrimoireLab**: a community-analytics platform (Elasticsearch, Kibana,
  scheduled collectors across GitHub, mailing lists, chat). Not a
  point-at-a-clone tool, and it does not cover code age, hotspots, size,
  repo health, or secrets.
- **trufflehog**: duplicates gitleaks for this purpose. gitleaks is lighter
  and faster on history.
- **GitLens**: useful in the editor, but it has telemetry and paid tiers.

## Install

gitmole needs git, Python 3.9 or newer, and three tools on your PATH:
[scc](https://github.com/boyter/scc) for size,
[git-sizer](https://github.com/github/git-sizer) for repository health and
[gitleaks](https://github.com/gitleaks/gitleaks) for secrets. gitmole itself
is a Python package; install it with [pipx](https://pipx.pypa.io) so it gets
its own environment and a `gitmole` command.

### macOS

```bash
brew install scc git-sizer gitleaks pipx
pipx ensurepath                                  # once; then open a new shell
pipx install 'git+https://github.com/antvinni/gitmole@v0.2.1'
```

### Linux

Homebrew on Linux has all three tools, bottled, so the macOS commands work
unchanged. Without Homebrew, take the tools from your package manager where
it has them and from the projects' release pages otherwise; each ships a
static binary, so dropping it into `~/.local/bin` is enough.

```bash
# Debian and Ubuntu: git-sizer and pipx are packaged
sudo apt install git git-sizer pipx
pipx ensurepath                                  # once; then open a new shell

# scc and gitleaks: one static binary each, from their release pages
#   https://github.com/boyter/scc/releases        (the Linux x86_64 or arm64 archive)
#   https://github.com/gitleaks/gitleaks/releases (the linux x64 or arm64 archive)
# unpack and move the binary into ~/.local/bin, then:
chmod +x ~/.local/bin/scc ~/.local/bin/gitleaks

pipx install 'git+https://github.com/antvinni/gitmole@v0.2.1'
```

On a distribution without a `pipx` package, `python3 -m pip install --user
pipx` installs it. Some distributions package scc or gitleaks as well; if
yours does, prefer that to a downloaded binary.

### Check

```bash
scc --version && git-sizer --version && gitleaks version && gitmole --version
gitmole .                                        # a report of the clone you are in
```

`gitmole` reports any tool it cannot find on the first run.

### Other ways to install

```bash
pipx install 'gitmole[plots] @ git+https://github.com/antvinni/gitmole@v0.2.1'   # adds git-of-theseus for --plots
pipx install git+https://github.com/antvinni/gitmole                        # main, unreleased
```

`python -m gitmole` works too. From a checkout, `pip install -e .` in a
virtual environment gives an editable install. Use pip 22 or newer: the pip
that ships with macOS's system Python is older and silently builds an empty
package called UNKNOWN from modern project files. pipx brings its own current
pip, and `python3 -m pip install -U pip` fixes a plain venv.

On macOS, `./bin/install.sh` does all of the above the developer way: brew
tools, the Python packages into your user site, and a symlink of
`bin/gitmole` into Homebrew's bin directory so the checkout is what runs.

## Run

```bash
gitmole .                          # the clone you are in
gitmole /path/to/clone             # any local clone
gitmole owner/repo                 # clones with gh into a temp dir first
gitmole https://github.com/o/r     # same, from a URL
gitmole 'owner/*'                  # every non-archived repo of a user or org
```

The last form is portfolio mode: each repository is cloned and analysed in
turn into `analysis-<owner>/<repo>/`, then one table summarises them all with
commits, people, the top author's share of surviving code, secrets found,
size, and the worst finding per repo. `--markdown` and `--json` write a
portfolio document with every repo's findings; `--fail-on` looks across all
of them.

Options: `--full` for every column and every row (the default report keeps the
columns you read, caps each table, and elides long paths in the middle),
`--out DIR` to choose the output directory, `--no-run DIR` to re-render the
report from an earlier run, `--since 2y` (or `18m`, `90d`, a date) to bound
the history by author date so people, activity, timeline, hotspots and
coupling describe the current team rather than the founders (file ages and
code age always cover the whole history; identity aliases are still merged
over all of it; an empty window is an error), `--plots` to also draw the
git-of-theseus code-age and survival charts, `--file-types py,sql` to choose
which files count as code (or `all`; `--list-file-types` shows what is in the
tree and what the default includes), `--duplicates` to also look for
duplicated blocks, `--workers N` to change how many tools run at once,
`--timeout S` to cap any single tool (default 15 minutes), `--gone MONTHS` to
change how long without a commit counts as gone (default 12, measured before
the last commit), `--risk BASE` to score the files changed since BASE (the
merge base with HEAD) with the watch list's score, in one extra section with
a total; it works with `--no-run` and the JSON carries the number for CI.
Ctrl-C kills every running step, including their child processes, and exits
with code 130.

All tools run concurrently, so a run takes about as long as the slowest tool.
Tool stderr goes to `run.log` in the output directory, not the terminal.

### Exports and CI

```bash
gitmole . --markdown report.md         # the same report as a Markdown document
gitmole . --json report.json           # every table, the watch list and the findings, machine-readable
gitmole . --markdown - | pbcopy        # - means stdout; banner and progress go to stderr
gitmole . --fail-on warning            # exit 3 if any finding is a warning or worse
```

`--fail-on` accepts `critical`, `warning`, or `info`. A CI job that runs
`gitmole . --fail-on critical --markdown - >> "$GITHUB_STEP_SUMMARY"` blocks
on secrets in source files and still posts the report. Secrets found only in
test files are a warning, so gate on `warning` to block on those too. Both exports also work with
`--no-run` against an earlier output directory.

### Big repositories

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

## Example

Running `gitmole .` inside this repository:

```text
╭─ gitmole ────────────────────────────────────────────────────────────────────────────────────────╮
│ 105 commits  ·  2026-09-15 → 2026-09-16  ·  1 identity  ·  branch main                           │
│ 6,592 lines in 44 files  ·  Python, Shell                                                        │
│ most commits on Wed at 13:00  ·  7% of commits are fixes  ·  100% of surviving code from 2026    │
│ 4 warnings                                                                                       │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
╭─ Findings (4) ───────────────────────────────────────────────────────────────────────────────────╮
│ ▲ Bus factor of one                                                                              │
│   vinni wrote 100% of the code that survives today                                               │
│   ↳ Pair someone with vinni on gitmole/ and build/ first; they are 100% and 100% theirs.         │
│ ▲ Bug magnets                                                                                    │
│   4 file(s) were fixed 3+ times in the last six months: gitmole/load.py (5 recent, 5 total);     │
│   gitmole/render.py (4 recent, 4 total); gitmole/findings.py (3 recent, 3 total); gitmole/run.py │
│   (3 recent, 3 total)                                                                            │
│   ↳ Review gitmole/load.py and gitmole/render.py before the next release; expect the next bug    │
│   there.                                                                                         │
│ ▲ Hotspots getting more complex                                                                  │
│   3 of the 10 top source hotspots grew by 25% or more in a year: gitmole/render.py (+134%),      │
│   gitmole/run.py (+26%), gitmole/findings.py (+262%)                                             │
│   ↳ Split gitmole/render.py before the next change; its complexity grew 134% in a year.          │
│ ▲ Knowledge islands                                                                              │
│   2 area(s) with at least 200 lines were written almost entirely by one person: gitmole/ (vinni  │
│   100%); build/ (vinni 100%). That is 99% of all lines added                                     │
│   ↳ Pair someone with vinni on gitmole/ first; it is the largest at 6,800 lines.                 │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯

◎ Watch list
  file                  why
  ──────────────────────────────────────────────────────────────────────────────────────────────────
  gitmole/render.py     changed 50 times · fixed 4 times in six months · only vinni has touched it ·
                        timeline_section() complexity 22 · changes with gitmole/cli.py (69%) and 3
                        others
  gitmole/run.py        changed 39 times · fixed 3 times in six months · only vinni has touched it ·
                        collect_meta() complexity 23 · changes with gitmole/cli.py (71%) and 3
                        others
  gitmole/findings.py   changed 29 times · fixed 3 times in six months · only vinni has touched it ·
                        knowledge_loss() complexity 34 · changes with gitmole/render.py (58%) and 1
                        other
  gitmole/cli.py        changed 37 times · fixed once in six months · only vinni has touched it ·
                        _analyse() complexity 35 · changes with gitmole/run.py (71%) and 1 other
  gitmole/load.py       changed 25 times · fixed 5 times in six months · only vinni has touched it ·
                        parse_git_sizer() complexity 15 · changes with gitmole/run.py (66%) and 2
                        others
  ranked by churn × recent fixes × complexity × single ownership
  too little history to backtest

◉ People
  author      commits   share                surviving code
  ─────────────────────────────────────────────────────────
  vinni           105   100% ▰▰▰▰▰▰▰▰▰▰                100%
  aliases merged for vinni; a .mailmap makes that permanent

⌂ Knowledge map
  area       lines added   main owner     second
  ──────────────────────────────────────────────
  tests/           7,489   vinni (100%)   -
  gitmole/         6,800   vinni (100%)   -
  build/           3,362   vinni (100%)   -
  bin/                91   vinni (100%)   -

▦ Timeline (Oct 2025 → Sep 2026)
  author   Oct   Nov   Dec   Jan   Feb   Mar   Apr   May   Jun   Jul   Aug   Sep
  ──────────────────────────────────────────────────────────────────────────────
  vinni      ·     ·     ·     ·     ·     ·     ·     ·     ·     ·     ·   105

◆ Hotspots
  file                     revs   lines   fixes   authors   trend
  ───────────────────────────────────────────────────────────────
  tests/test_render.py       49     684       4         1   +738%
  gitmole/render.py          50     545       4         1   +134%
  tests/test_run.py          38     476       3         1    +46%
  tests/test_cli.py          34     522       0         1    +58%
  tests/test_findings.py     28     460       3         1   +400%
  gitmole/run.py             39     302       3         1    +26%
  gitmole/cli.py             37     313       1         1    +24%
  gitmole/findings.py        29     293       3         1   +262%
  and 49 more

⟷ Change coupling
  file                   changes with              degree
  ───────────────────────────────────────────────────────
  gitmole/maat.py        tests/test_maat.py          100%
  gitmole/filetypes.py   tests/test_filetypes.py     100%
  gitmole/functions.py   tests/test_functions.py     100%
  gitmole/knowledge.py   tests/test_knowledge.py     100%
  gitmole/render.py      tests/test_render.py         99%
  and 85 more

λ Complex functions
  function           file                  ccn   lines   params
  ─────────────────────────────────────────────────────────────
  _analyse           gitmole/cli.py         35      66        6
  knowledge_loss     gitmole/findings.py    34      44        3
  main               gitmole/cli.py         28      82        8
  collect_meta       gitmole/run.py         23      27        2
  risks              gitmole/watch.py       22      32        2
  timeline_section   gitmole/render.py      22      16        4
  hotspots_section   gitmole/render.py      21      25        3
  markdown           gitmole/render.py      19      24        5
  and 34 more

✚ Repo health (git-sizer concerns): nothing flagged

Secrets: none found
Full results and plots in analysis-gitmole
```

In a terminal the banner above heads the run: the letters pulse in neon,
the pixel mole beside them glances side to side while the tools work, and
the findings and tables are coloured: section headings in the banner's cyan,
column headers in its violet, one key column per table in full white with
the rest dimmed, inline bars on share columns, and values past a threshold
(a share over 50%, coupling at 90%, five fixes) in pink. On a terminal 100
columns or wider the small tables sit side by side. Piped output, as above,
is plain text.
This is the default report: the header, the findings, the watch list, and
the tables that point at a file or a person. `--full` adds the descriptive
tables the header summarises in one line (size by language, activity by
weekday with the busiest hour, surviving code by year), complexity, score
and idle months to hotspots, emails to people, average revisions to
coupling, the author count to the knowledge map, and lifts the row caps.
The Markdown export keeps every table and column but caps each table at 50
rows unless `--full`.

### The terminal report

1. **Header**: commits, date span, identities, branch, size, top languages,
   one line for the busiest day and hour, the share of fix commits, the
   share that are reverts when there are any, and the year most surviving
   code was written (or why the blame pass did not run), and a one-line
   tally of the findings.
2. **Findings**: anything the heuristics flagged, worst first. Findings of
   the same kind are grouped into one entry with a list, and every finding
   ends with a next step that names the file, area or person to start with,
   on its own line under the facts. Currently:
   secrets in history (see below), an unconfigured git identity
   (example.com and the like), one author owning most surviving code,
   git-sizer concerns, one file dominating the churn, bug magnets (source
   files fixed three or more times in the last six months; a warning at
   five), reverts (5% of commits or five of them; a warning at 10%; names
   the file most often backed out), brain methods (functions with
   complexity 15+ and 100+ lines; a warning when one sits in a hotspot),
   hotspots getting more complex (three or more of the top ten hotspots
   grew by a quarter in a year; a warning when the top one did),
   tightly coupled file pairs (a file and its test are expected to change
   together, so those pairs are left out), duplicated blocks of 30+ lines
   (with `--duplicates`), a large share of stale files (files still in the
   tree; deleted paths do not count), knowledge islands: areas of at least
   200 lines written almost entirely by one person (a warning when such
   areas hold most of the code), and knowledge loss (people with no commits
   in the twelve months before the last commit who wrote 10% or more of the
   surviving code; a warning at 30%). An unconfigured identity is only
   flagged when it made at least 1% of the commits.

   Secrets are grouped by value, so one key copied into ten files is one
   entry with its places counted. A value found in any source file is
   critical. A value found only in test files, such as fixtures and saved
   web pages, is a warning. Version strings and tokens shortened with "..."
   cannot be live secrets, so they are left out and counted on the footer
   line. Nothing is skipped by prefix. To silence a false positive for
   good, copy its fingerprint from `secrets.json` into a `.gitleaksignore`
   at the repository root; gitleaks reads it on the next run.

   A commit counts as a fix when its subject starts with `fix:`, `hotfix:` or
   `bugfix:` in the conventional style, or mentions fix, bug, hotfix,
   regression or crash. Test files are left out of every finding that names a
   file, area or function: they change with every fix, and owning the tests is
   not the knowledge risk. The tables still show them.
3. **Watch list**: the five files where the next bug is most likely, with
   the reasons in words. Every source file still in the tree that changed
   more than once is scored churn × (1 + recent fixes) × (1 + complexity),
   times 1.5 when one person wrote 90% or more of it, each factor scaled to
   the worst file in the repo. Churn is the base because a file nobody
   changes is not where the next bug lands; complexity is scc's per-file
   total, one scale for every file, while the most complex function lizard
   found is named in the reasons. The reasons name the fix count, the sole
   owner, the function and the files it always changes with. Test files are
   left out. Under `--since`, churn and ownership are windowed and the list
   says so. `--full` and the exports show fifteen. With `--risk BASE`, a
   Change risk section follows: every file changed since BASE with its watch
   score as a bar and the reasons, or why it has none (new file, changed
   once, test file).

   Under the watch list, one line says how the list would have done:
   gitmole reruns the change analysis as of six months before the last
   commit, with scc on the tree at that time, ranks the watch list from
   that, and counts how many of the files fixed since were on it, next to
   what a random list of the same size, drawn from the files that had
   changed more than once, would score. Repositories with under a year
   of history say `too little history to backtest`.
4. **Tables**: people (identities merged by name and email similarity on
   top of `.mailmap`, and the caption says whose; bots such as renovate,
   dependabot and GitHub Actions are counted apart in the caption and kept
   out of the timeline), a knowledge map (lines added per area of the tree
   and who wrote them), a timeline of commits per author over the last
   twelve months, hotspots ranked by revisions times lines of code with the
   number of fix commits alongside, change coupling, the most complex
   functions, repo health. Hotspots carry a `trend` column, sampled for the
   top ten hotspots: the change in complexity over the last year from scc on
   the file at sampled commits (`--full` shows the whole series as a
   sparkline). The knowledge map marks owners who have stopped committing
   with `(gone)`, and under `--full` shows the share of each area's lines
   that they wrote. With `--full`: size by language, activity by weekday
   with the busiest hour and the share of commits that are fixes, and
   surviving code by year.

   Size, hotspots, coupling, ownership, code age and the watch list only
   look at source files: a built-in list of code extensions plus names like
   Makefile and Dockerfile (`--file-types all` counts everything). Activity
   and the timeline cover the whole history.
5. **Footer**: where the files and plots are.

### The output directory

Lands in `analysis-<repo>/` next to a local clone, or in the current
directory for a remote target:

| File | From | What it is |
|---|---|---|
| `meta.json` | git | name, branch, commit count, date span, identities |
| `activity.json` | change analysis | commits by weekday, hour and month; net lines per year; fix-commit count; per-author totals and monthly timeline |
| `size.json` | scc | lines per language, COCOMO estimate |
| `repo-health.txt` | git-sizer | oversized objects, deep trees, other repo problems |
| `secrets.json` | gitleaks | secret-looking strings across all history: rule, file, commit, line and fingerprint, with each value replaced by a short keyed hash |
| `log.txt` | git | the numstat log export the change analysis reads |
| `maat-revisions.csv` | change analysis | change frequency per file |
| `maat-coupling.csv` | change analysis | files that change together |
| `maat-authors.csv` | change analysis | authors per file |
| `maat-age.csv` | change analysis | months since last change per file |
| `maat-entity-ownership.csv` | change analysis | lines added and deleted per author per file |
| `maat-fixes.csv` | change analysis | fix commits per file: total, last, and in the last six months |
| `functions.csv` | lizard | per-function complexity, length, parameters |
| `duplicates.txt` | lizard, `--duplicates` only | duplicated blocks and the overall duplicate rate |
| `theseus/` | blame pass (git-of-theseus with `--plots`) | surviving lines by year and by author |
| `code-age.png` | git-of-theseus, `--plots` only | stacked plot of surviving code by year |
| `survival.png` | git-of-theseus, `--plots` only | how long a line of code tends to live |
| `trend.json` | trend step | complexity and lines of the top hotspots at sampled commits |
| `backtest/` | backtest step | the change analysis and size as of six months before the last commit |
| `run.log` | gitmole | every command run and its stderr |

## How to read the output

1. Start with the header and the findings.
2. The hotspots table is `maat-revisions.csv` joined with scc's per-file
   size and complexity, author count, and age, ranked by revisions times
   lines. Large files that change constantly are your risk.
3. Change coupling shows files that always change together. That usually
   means a hidden dependency or copy-pasted layout.
4. People and the surviving-code table tell you whether knowledge is
   concentrated in one or two people; the knowledge map says where. Areas
   are top-level directories, or the subdirectories of a lone top-level one
   such as `src/`.
5. Repo health and secrets are pass or fail checks. Read them only if they
   flag something.

## Development

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

### Releases

Versions are git tags. To release: bump `__version__` in `gitmole/__init__.py`,
merge, then tag that commit `vX.Y.Z` and push the tag. CI runs the tests, checks
that the tag matches `__version__`, builds the sdist and wheel, and creates the
GitHub release with notes generated from the merged pull requests and the
artefacts attached. `pipx install 'git+https://github.com/antvinni/gitmole@vX.Y.Z'`
installs a release. Releases are listed at
https://github.com/antvinni/gitmole/releases.

`bin/render-banner` regenerates `docs/banner.svg` from the banner code.
The code lives in `gitmole/`: `run.py` plans and executes the tools,
`maat.py` is the standalone change analysis (revisions, coupling, authors,
age, ownership over the numstat log; the file names still say maat because
the layout matches what code-maat produced), `blame.py` is the standalone
code-age pass (its output mimics git-of-theseus so one loader serves both),
`identity.py` merges author aliases, `load.py` parses the outputs, `findings.py` holds the heuristics,
and `render.py` draws the report. `bin/gitmole` is a thin launcher.

## Safety notes

- Everything here is offline except the optional clone step, which uses
  your existing gh auth. None of the tools send data anywhere.
- Remote targets are cloned into a fresh temp directory. Local clones are
  only read, but the log export and the gitleaks scan touch all branches.
- Secret values never reach the output directory. gitleaks writes its report
  to gitmole in memory, and gitmole stores a short keyed hash of each value
  in place of the value, the matched text and the commit message. The key is
  random, made for that one report and never saved, so a stored hash cannot
  be checked against a list of common passwords. It only tells you which
  hits in one report share a value.
- Install from the official repos or Homebrew with pinned versions, not from
  forks.

## License

gitmole is released under the [MIT License](LICENSE).

It does not bundle any of the tools it wraps. `bin/install.sh` fetches them
from their own sources, and gitmole runs them as separate processes. Their
licences:

| Tool | Licence |
|---|---|
| scc | MIT |
| git-sizer | MIT |
| gitleaks | MIT |
| rich | MIT |
| lizard | MIT |
| git-of-theseus | Apache-2.0 |

The change analysis (hotspots, coupling, ownership, age) is gitmole's own
code, written after the ideas in Adam Tornhill's code-maat but sharing no
code with it.

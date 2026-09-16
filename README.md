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
| Per-function complexity, length, parameters; duplicated blocks | [lizard](https://github.com/terryyin/lizard) | pip, used when installed |
| Have secrets ever been committed | [gitleaks](https://github.com/gitleaks/gitleaks) | brew |
| Anything custom the above don't answer | [PyDriller](https://github.com/ishepard/pydriller) | pip |

Three external tools: scc for size, git-sizer for repo health, gitleaks for
secrets. Everything about history is computed by gitmole from `git log`.
lizard adds function-level metrics for two dozen languages when it is
installed; git-of-theseus only adds the plots, so it is off by default and
only needed with `--plots`. gitleaks should never be skipped on a repo you did
not author. PyDriller is optional and only matters if you want to script your
own metrics.

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

gitmole needs three tools on your PATH: [scc](https://github.com/boyter/scc),
[git-sizer](https://github.com/github/git-sizer) and
[gitleaks](https://github.com/gitleaks/gitleaks). All three are in Homebrew
and in most Linux package managers, and each ships static binaries.

Then install gitmole itself with pipx (or pip) on any platform:

```bash
brew install scc git-sizer gitleaks          # or your package manager
pipx install git+https://github.com/antvinni/gitmole
pipx install 'gitmole[plots] @ git+https://github.com/antvinni/gitmole'   # adds git-of-theseus for --plots
```

`python -m gitmole` works too. From a checkout, `pip install -e .` gives an
editable install. Use pip 22 or newer: the pip that ships with macOS's system
Python is older and silently builds an empty package called UNKNOWN from
modern project files. pipx brings its own current pip, and
`python3 -m pip install -U pip` fixes a plain venv.

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

Options: `--full` for every column and every row (the default report keeps
the columns you read, caps each table, and elides long paths in the
middle), `--out DIR` to choose the output directory, `--no-run DIR` to
re-render the report from an earlier run, `--since 2y` (or `18m`, `90d`, a
date) to bound the history by author date so people, activity, timeline,
hotspots and coupling describe the current team rather than the founders
(file ages and code age always cover the whole history; identity aliases
are still merged over all of it; an empty window is an error), `--plots` to
also draw
the git-of-theseus code-age and survival charts, `--file-types py,sql` to choose
which files count as code (or `all`; `--list-file-types` shows what is in the
tree and what the default includes), `--workers N` to change how many
tools run at once, `--timeout S` to cap any single tool (default 15 minutes).
Ctrl-C kills every running step, including their child processes, and exits
with code 130.

All tools run concurrently, so a run takes about as long as the slowest tool.
Tool stderr goes to `run.log` in the output directory, not the terminal.

### Exports and CI

```bash
gitmole . --markdown report.md         # the same report as a Markdown document
gitmole . --json report.json           # every table plus the findings, machine-readable
gitmole . --markdown - | pbcopy        # - means stdout; banner and progress go to stderr
gitmole . --fail-on warning            # exit 3 if any finding is a warning or worse
```

`--fail-on` accepts `critical`, `warning`, or `info`. A CI job that runs
`gitmole . --fail-on critical --markdown - >> "$GITHUB_STEP_SUMMARY"` blocks
on leaked secrets and still posts the report. Both exports also work with
`--no-run` against an earlier output directory.

### Big repositories

Blame is the one cost that scales with repo size. gitmole keeps it in check:

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
- `--ignore-data` excludes data-like files (csv, json, lock files, minified
  and vendored assets) from blame, and `--ignore GLOB` adds your own
  patterns, repeatable. Both shrink the blame count a lot on repos full of
  exports and fixtures.

A tool that exceeds `--timeout` is killed along with its child processes,
marked in the report, and the rest of the report still renders.

## Example

Running `gitmole .` inside this repository:

```text
╭─ gitmole ────────────────────────────────────────────────────────────────────────────────────────╮
│ 51 commits  ·  2026-09-15 → 2026-09-16  ·  1 identity  ·  branch main                             │
│ 4,651 lines in 37 files  ·  Python, SVG, Markdown, Plain Text                                    │
│ 2 warnings, 3 notes                                                                              │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
╭─ Findings (5) ───────────────────────────────────────────────────────────────────────────────────╮
│ ▲ Bus factor of one                                                                              │
│   vinni wrote 100% of the code that survives today.                                              │
│ ▲ Knowledge islands                                                                              │
│   3 area(s) with at least 200 lines were written almost entirely by one person: tests/ (vinni    │
│   100%); gitmole/ (vinni 100%); build/ (vinni 100%). That is 99% of all lines added              │
│   ↳ Pair or review across them before that person is unavailable.                                │
│ ● Bug magnets                                                                                    │
│   1 file(s) were fixed 3+ times in the last six months: gitmole/run.py (3 recent, 3 total)       │
│   ↳ Expect the next bug there too.                                                               │
│ ● Files that always change together                                                              │
│   11 pairs change together at least 80% of the time, e.g. gitmole/maat.py + tests/test_maat.py   │
│   (100%); gitmole/findings.py + tests/test_findings.py (100%); gitmole/knowledge.py +            │
│   tests/test_knowledge.py (100%). Usually a shared layout or a hidden dependency.                │
│ ● One person under several identities                                                            │
│   antvinni <5262575+antvinni@users.noreply.github.com> merged into vinni                         │
│   <5262575+antvinni@users.noreply.github.com> by name and email similarity                       │
│   ↳ Add a .mailmap to make it permanent.                                                         │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯

▤ Size by language                             ◉ People
  language     files    code   share             author   commits   share             surviving code
  ──────────────────────────────────────────     ───────────────────────────────────────────────────
  Python          31   3,803    82% ▰▰▰▰▰▰▰▰     vinni         51   100% ▰▰▰▰▰▰▰▰▰▰             100%
  SVG              1     399     9% ▰
  Markdown         1     336     7% ▰
  Plain Text       1      58     1% ▰
  TOML             1      29     1% ▰
  License          1      17     0%
  Shell            1       9     0%

◔ Activity
  weekday   commits   share
  ────────────────────────────────────────────
  Mon             0      0%
  Tue            43     84%   ████████████████
  Wed             8     16%   ███
  Thu             0      0%
  Fri             0      0%
  Sat             0      0%
  Sun             0      0%
  busiest hour 23:00 (13 commits)
  6% of commits are fixes

▦ Timeline (Oct 2025 → Sep 2026)
  author   Oct   Nov   Dec   Jan   Feb   Mar   Apr   May   Jun   Jul   Aug   Sep
  ──────────────────────────────────────────────────────────────────────────────
  vinni      ·     ·     ·     ·     ·     ·     ·     ·     ·     ·     ·    51

◆ Hotspots
  file                   revs   lines   fixes   authors
  ─────────────────────────────────────────────────────
  gitmole/render.py        24     380       2         1
  tests/test_render.py     23     354       2         1
  tests/test_cli.py        21     358       0         1
  tests/test_run.py        22     335       3         1
  gitmole/cli.py           24     273       1         1
  gitmole/run.py           23     248       3         1
  tests/test_maat.py       16     229       2         1
  gitmole/maat.py          16     195       2         1
  and 35 more

⟷ Change coupling
  file                   changes with              degree
  ───────────────────────────────────────────────────────
  gitmole/maat.py        tests/test_maat.py          100%
  gitmole/findings.py    tests/test_findings.py      100%
  gitmole/knowledge.py   tests/test_knowledge.py     100%
  gitmole/render.py      tests/test_render.py         98%
  gitmole/run.py         tests/test_run.py            98%
  and 74 more

◷ Surviving code by year written
  year   lines   share
  ─────────────────────────────────────────────────────
  2026   6,334    100%   ██████████████████████████████

⌂ Knowledge map
  area       lines added   main owner     second
  ──────────────────────────────────────────────
  tests/           3,783   vinni (100%)   -
  gitmole/         3,731   vinni (100%)   -
  build/           3,362   vinni (100%)   -
  bin/                89   vinni (100%)   -

✚ Repo health (git-sizer concerns): nothing flagged

Secrets: none found
Full results and plots in ../analysis-gitmole
```

In a terminal the banner above heads the run: the letters pulse in neon,
the pixel mole beside them glances side to side while the tools work, and
the findings and tables are coloured: section headings in the banner's cyan,
column headers in its violet, one key column per table in full white with
the rest dimmed, inline bars on share columns, and values past a threshold
(a share over 50%, coupling at 90%, five fixes) in pink. On a terminal 100
columns or wider the small tables sit side by side. Piped output, as above,
is plain text.
This is the default report; `--full` adds complexity, score and idle months
to hotspots, emails to people, average revisions to coupling, the author
count to the knowledge map, and lifts the row caps. The Markdown export
keeps every column but caps each table at 50 rows unless `--full`.

### The terminal report

1. **Header**: commits, date span, identities, branch, size, top languages,
   and a one-line tally of the findings.
2. **Findings**: anything the heuristics flagged, worst first. Findings of
   the same kind are grouped into one entry with a list, and advice sits on
   its own line under the facts. Currently:
   secrets in history, an unconfigured git identity (example.com and the
   like), one author owning most surviving code, git-sizer concerns, one file
   dominating the churn, bug magnets (source files fixed three or more times
   in the last six months; a warning at five), brain methods (functions with
   complexity 15+ and 100+ lines; a warning when one sits in a hotspot),
   tightly coupled file pairs, duplicated blocks of 30+ lines, a large share
   of stale files, one person under several identities, and knowledge
   islands: areas of at least 200 lines written almost entirely by
   one person (a warning when such areas hold most of the code).

   A commit counts as a fix when its subject starts with `fix:`, `hotfix:` or
   `bugfix:` in the conventional style, or mentions fix, bug, hotfix,
   regression or crash. Test files are left out of bug magnets because they
   change with every fix.
3. **Tables**: size by language, people (identities merged by name and
   email similarity, on top of `.mailmap`), activity by weekday with the
   busiest hour and the share of commits that are fixes, a timeline of
   commits per author over the last twelve months, hotspots ranked by
   revisions times lines of code with complexity and the number of fix
   commits alongside, change coupling, surviving code by year, the most
   complex functions, a knowledge map (lines added per area of the tree and
   who wrote them), repo health.

   Hotspots, coupling, ownership and code age only look at source files: a
   built-in list of code extensions plus names like Makefile and Dockerfile.
   Size by language, activity and the timeline cover the whole repository.
4. **Footer**: where the files and plots are.

### The output directory

Lands in `analysis-<repo>/` next to a local clone, or in the current
directory for a remote target:

| File | From | What it is |
|---|---|---|
| `meta.json` | git | name, branch, commit count, date span, identities |
| `activity.json` | change analysis | commits by weekday, hour and month; net lines per year; fix-commit count; per-author totals and monthly timeline |
| `size.json` | scc | lines per language, COCOMO estimate |
| `repo-health.txt` | git-sizer | oversized objects, deep trees, other repo problems |
| `secrets.json` | gitleaks | any secret-looking strings across all history |
| `log.txt` | git | the numstat log export the change analysis reads |
| `maat-revisions.csv` | change analysis | change frequency per file |
| `maat-coupling.csv` | change analysis | files that change together |
| `maat-authors.csv` | change analysis | authors per file |
| `maat-age.csv` | change analysis | months since last change per file |
| `maat-entity-ownership.csv` | change analysis | lines added and deleted per author per file |
| `maat-fixes.csv` | change analysis | fix commits per file: total, last, and in the last six months |
| `functions.csv` | lizard | per-function complexity, length, parameters |
| `duplicates.txt` | lizard | duplicated blocks and the overall duplicate rate |
| `theseus/` | blame pass (git-of-theseus with `--plots`) | surviving lines by year and by author |
| `code-age.png` | git-of-theseus, `--plots` only | stacked plot of surviving code by year |
| `survival.png` | git-of-theseus, `--plots` only | how long a line of code tends to live |
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
| git-of-theseus | Apache-2.0 |
| PyDriller | Apache-2.0 |

The change analysis (hotspots, coupling, ownership, age) is gitmole's own
code, written after the ideas in Adam Tornhill's code-maat but sharing no
code with it.

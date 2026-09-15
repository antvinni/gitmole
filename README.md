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
| What is this repo, at a glance | [onefetch](https://github.com/o2sh/onefetch) | brew |
| Who commits, when, how much churn | [git-quick-stats](https://github.com/git-quick-stats/git-quick-stats) | brew |
| How big is the codebase, per language | [scc](https://github.com/boyter/scc) | brew |
| Is the repo itself healthy (huge blobs, deep trees) | [git-sizer](https://github.com/github/git-sizer) | brew |
| Where is the risk: hotspots, coupling, ownership | gitmole's own change analysis over `git log --numstat` | built in |
| How old is the surviving code, per year and author | gitmole's own blame pass (one `git blame` per file at HEAD) | built in |
| Code-age and survival plots over time | [git-of-theseus](https://github.com/erikbern/git-of-theseus) | pip, opt-in with `--plots` |
| Have secrets ever been committed | [gitleaks](https://github.com/gitleaks/gitleaks) | brew |
| Anything custom the above don't answer | [PyDriller](https://github.com/ishepard/pydriller) | pip |

The first four give a full picture in under a minute. The change analysis
and the blame pass produce the genuinely non-obvious insight. git-of-theseus
only adds the plots, so it is off by default. gitleaks should never be skipped on a repo you did not
author. PyDriller is optional and only matters if you want to script your own
metrics.

### Considered and left out

- **hercules**: overlaps the change analysis and git-of-theseus, and the project is
  archived. Add it only if you want its burndown charts specifically.
- **tokei**: duplicates scc without the effort estimate.
- **git-extras**: convenient, but everything it reports is covered above.
- **GrimoireLab**: a community-analytics platform (Elasticsearch, Kibana,
  scheduled collectors across GitHub, mailing lists, chat). Not a
  point-at-a-clone tool, and it does not cover code age, hotspots, size,
  repo health, or secrets.
- **trufflehog**: duplicates gitleaks for this purpose. gitleaks is lighter
  and faster on history.
- **GitLens**: useful in the editor, but it has telemetry and paid tiers.

## Install

Requires Homebrew and Python 3.

```bash
./bin/install.sh
```

That installs the brew tools, the Python packages (git-of-theseus, PyDriller,
rich), and symlinks the `gitmole` command into Homebrew's bin directory.

## Run

```bash
gitmole .                          # the clone you are in
gitmole /path/to/clone             # any local clone
gitmole owner/repo                 # clones with gh into a temp dir first
gitmole https://github.com/o/r     # same, from a URL
```

Options: `--out DIR` to choose the output directory, `--no-run DIR` to
re-render the report from an earlier run, `--plots` to also draw the
git-of-theseus code-age and survival charts, `--workers N` to change how many
tools run at once, `--timeout S` to cap any single tool (default 15 minutes).

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

- the code-age table comes from one `git blame` per tracked text file at
  HEAD, run across every CPU core. That is all the table needs;
- the plots need history, so `--plots` runs git-of-theseus with monthly
  sampling (tracked files × samples blames) on top;
- before running, gitmole checks both against `--budget` (default 50,000
  blames) and skips whichever exceeds it, saying so. Without code age, the
  report shows paths by the year they were last changed, from the change
  analysis, deleted paths included;
- `--deep` forces both regardless of the budget;
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
│ 19 commits  ·  2026-09-15 → 2026-09-15  ·  1 identity  ·  branch main                            │
│ 2,366 lines in 24 files  ·  Python, SVG, Markdown, License                                       │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
╭─ Findings (2) ───────────────────────────────────────────────────────────────────────────────────╮
│ ▲ Bus factor of one                                                                              │
│   vinni wrote 100% of the code that survives today.                                              │
│ ● Files that always change together                                                              │
│   1 pairs change together at least 80% of the time, e.g. gitmole/banner.py +                     │
│   tests/test_banner.py (86%). Usually a shared layout or a hidden dependency.                    │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
Size by language
language   files    code   share   complexity
─────────────────────────────────────────────
Python        20   1,739     73%          440
SVG            1     399     17%            0
Markdown       1     202      9%            0
License        1      17      1%            0
Shell          1       9      0%            1
People
author   email                                       commits   share   surviving code
─────────────────────────────────────────────────────────────────────────────────────
vinni    5262575+antvinni@users.noreply.github.com        19    100%             100%
Hotspots (score = revisions × lines of code)
file                   revs   lines   cplx   score   authors   idle
───────────────────────────────────────────────────────────────────
README.md                14     202      0   2,828         1      0
gitmole/cli.py            6     115     35     690         1      0
gitmole/banner.py         8      84     16     672         1      0
tests/test_banner.py      6      94     38     564         1      0
tests/test_run.py         3     181     29     543         1      0
gitmole/run.py            3     151     57     453         1      0
docs/banner.svg           1     399      0     399         1      0
gitmole/render.py         3     121     59     363         1      0
tests/test_cli.py         3     114      8     342         1      0
tests/test_render.py      3      96      5     288         1      0
Change coupling
file                changes with           degree   avg revs
────────────────────────────────────────────────────────────
gitmole/banner.py   tests/test_banner.py      86%          7
Surviving code by year written
year   lines   share
─────────────────────────────────────────────────────
2026   2,082    100%   ██████████████████████████████
Repo health (git-sizer concerns)
nothing flagged

Secrets: none found

Full results and plots in ../analysis-gitmole
```

In a terminal the banner above heads the run: the letters pulse in neon,
the pixel mole beside them glances side to side while the tools work, and
the findings and tables are coloured. Piped output, as above, is plain text.

### The terminal report

1. **Header**: commits, date span, identities, branch, size, top languages.
2. **Findings**: anything the heuristics flagged, worst first. Currently:
   secrets in history, an unconfigured git identity (example.com and the
   like), one author owning most surviving code, git-sizer concerns, one file
   dominating the churn, tightly coupled file pairs, a large share of stale
   files, and one person under several identities.
3. **Tables**: size by language, people (identities merged by name and
   email similarity, on top of `.mailmap`), hotspots ranked by revisions
   times lines of code with complexity alongside, change coupling,
   surviving code by year, repo health.
4. **Footer**: where the files and plots are.

### The output directory

Lands in `analysis-<repo>/` next to a local clone, or in the current
directory for a remote target:

| File | From | What it is |
|---|---|---|
| `meta.json` | git | name, branch, commit count, date span, identities |
| `overview.txt` | onefetch | languages, authors, age, size |
| `contributors.txt` | git-quick-stats | commits per author, activity by hour and weekday |
| `size.json` | scc | lines per language, COCOMO estimate |
| `repo-health.txt` | git-sizer | oversized objects, deep trees, other repo problems |
| `secrets.json` | gitleaks | any secret-looking strings across all history |
| `log.txt` | git | the numstat log export the change analysis reads |
| `maat-revisions.csv` | change analysis | change frequency per file |
| `maat-coupling.csv` | change analysis | files that change together |
| `maat-authors.csv` | change analysis | authors per file |
| `maat-age.csv` | change analysis | months since last change per file |
| `maat-entity-ownership.csv` | change analysis | lines added and deleted per author per file |
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
   concentrated in one or two people.
5. Repo health and secrets are pass or fail checks. Read them only if they
   flag something.

## Development

```bash
python3 -m unittest discover -s tests -t .
```

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
| onefetch | MIT |
| git-quick-stats | MIT |
| scc | MIT |
| git-sizer | MIT |
| gitleaks | MIT |
| rich | MIT |
| git-of-theseus | Apache-2.0 |
| PyDriller | Apache-2.0 |

The change analysis (hotspots, coupling, ownership, age) is gitmole's own
code, written after the ideas in Adam Tornhill's code-maat but sharing no
code with it.

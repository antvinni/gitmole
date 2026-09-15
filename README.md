```
███╗   ███╗ ██████╗ ██╗     ███████╗    ▄▄████████▄▄
████╗ ████║██╔═══██╗██║     ██╔════╝   ██████████████
██╔████╔██║██║   ██║██║     █████╗    ███  █████  ████
██║╚██╔╝██║██║   ██║██║     ██╔══╝    ███████▄▄███████
██║ ╚═╝ ██║╚██████╔╝███████╗███████╗  ████████████████
╚═╝     ╚═╝ ╚═════╝ ╚══════╝╚══════╝  ▀██████████████▀
```

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
| Where is the risk: hotspots, coupling, ownership | [code-maat](https://github.com/adamtornhill/code-maat) | jar, needs Java |
| How old is the surviving code, per year and author | [git-of-theseus](https://github.com/erikbern/git-of-theseus) | pip |
| Have secrets ever been committed | [gitleaks](https://github.com/gitleaks/gitleaks) | brew |
| Anything custom the above don't answer | [PyDriller](https://github.com/ishepard/pydriller) | pip |

The first four give a full picture in under a minute. code-maat and
git-of-theseus produce the genuinely non-obvious insight, so they are worth
the extra setup. gitleaks should never be skipped on a repo you did not
author. PyDriller is optional and only matters if you want to script your own
metrics.

### Considered and left out

- **hercules**: overlaps code-maat and git-of-theseus, and the project is
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

Requires Homebrew and Python 3. OpenJDK is installed via brew for code-maat.

```bash
./bin/install.sh
```

That installs the brew tools, the Python packages (git-of-theseus, PyDriller,
rich), downloads the pinned code-maat jar to `~/bin`, and symlinks the
`gitmole` command into Homebrew's bin directory. Check the
[code-maat releases](https://github.com/adamtornhill/code-maat/releases)
page before bumping the jar version in `bin/install.sh`.

## Run

```bash
gitmole .                          # the clone you are in
gitmole /path/to/clone             # any local clone
gitmole owner/repo                 # clones with gh into a temp dir first
gitmole https://github.com/o/r     # same, from a URL
```

Options: `--out DIR` to choose the output directory, `--no-run DIR` to
re-render the report from an earlier run, `--jar PATH` if the code-maat jar is
elsewhere, `--workers N` to change how many tools run at once, `--timeout S`
to cap any single tool (default 15 minutes).

All tools run concurrently, so a run takes about as long as the slowest tool.
Tool stderr goes to `run.log` in the output directory, not the terminal.

### Big repositories

git-of-theseus is the one tool whose cost explodes: it runs one `git blame`
per file per sampled commit. gitmole keeps it in check:

- it samples monthly rather than weekly and uses every CPU core;
- before running it estimates the blame count (tracked files × samples) and
  skips git-of-theseus when that exceeds `--budget` (default 50,000). The
  report then shows paths by the year they were last changed, from
  code-maat, instead of surviving lines by year written. code-maat counts
  every path that ever appeared in the log, deleted ones included;
- `--deep` forces git-of-theseus regardless of the budget;
- `--ignore-data` excludes data-like files (csv, json, lock files, minified
  and vendored assets) from git-of-theseus, and `--ignore GLOB` adds your
  own patterns, repeatable. Both shrink the blame count a lot on repos full
  of exports and fixtures.

A tool that exceeds `--timeout` is killed along with its child processes,
marked in the report, and the rest of the report still renders.

## Example

Running `gitmole .` inside this repository:

```text
╭─ gitmole ────────────────────────────────────────────────────────────────────────────────────────╮
│ 9 commits  ·  2026-09-15 → 2026-09-15  ·  1 identity  ·  branch main                             │
│ 1,445 lines in 18 files  ·  Python, Markdown, License, Shell                                     │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
╭─ Findings (1) ───────────────────────────────────────────────────────────────────────────────────╮
│ ▲ Bus factor of one                                                                              │
│   vinni wrote 100% of the code that survives today.                                              │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
Size by language
language   files    code   share   complexity
─────────────────────────────────────────────
Python        15   1,207     84%          289
Markdown       1     206     14%            0
License        1      17      1%            0
Shell          1      15      1%            1
People
author   email                                       commits   share   surviving code
─────────────────────────────────────────────────────────────────────────────────────
vinni    5262575+antvinni@users.noreply.github.com         9    100%             100%
Hotspots (most revised files)
file                   revisions   authors   months idle
────────────────────────────────────────────────────────
README.md                      7         1             0
gitmole/cli.py                 4         1             0
tests/test_cli.py              3         1             0
gitmole/render.py              3         1             0
tests/test_render.py           3         1             0
bin/analyse.sh                 3         1             0
bin/install.sh                 3         1             0
tests/test_run.py              2         1             0
gitmole/run.py                 2         1             0
gitmole/banner.py              2         1             0
Change coupling
no pairs with 5+ shared revisions

Surviving code by year written
year   lines   share
─────────────────────────────────────────────────────
2026   1,541    100%   ██████████████████████████████
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
3. **Tables**: size by language, people, hotspots, change coupling, surviving
   code by year, repo health.
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
| `log.txt` | git | the log export code-maat reads |
| `maat-revisions.csv` | code-maat | change frequency per file |
| `maat-coupling.csv` | code-maat | files that change together |
| `maat-authors.csv` | code-maat | authors per file |
| `maat-age.csv` | code-maat | months since last change per file |
| `maat-entity-ownership.csv` | code-maat | lines added and deleted per author per file |
| `theseus/` | git-of-theseus | raw cohort and survival data |
| `code-age.png` | git-of-theseus | stacked plot of surviving code by year |
| `survival.png` | git-of-theseus | how long a line of code tends to live |
| `run.log` | gitmole | every command run and its stderr |

## How to read the output

1. Start with the header and the findings.
2. The hotspots table is `maat-revisions.csv` joined with author and age.
   Large files that change constantly are your risk.
3. Change coupling shows files that always change together. That usually
   means a hidden dependency or copy-pasted layout.
4. People and the code-age plot tell you whether knowledge is concentrated
   in one or two people.
5. Repo health and secrets are pass or fail checks. Read them only if they
   flag something.

## Development

```bash
python3 -m unittest discover -s tests -t .
```

The code lives in `gitmole/`: `run.py` plans and executes the tools,
`load.py` parses their output, `findings.py` holds the heuristics, and
`render.py` draws the report. `bin/gitmole` is a thin launcher.

## Safety notes

- Everything here is offline except the optional clone step, which uses
  your existing gh auth. gitleaks and git-of-theseus never send data
  anywhere.
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
| code-maat | GPL-3.0 |

code-maat's GPL applies to code-maat itself. gitmole only invokes the
standalone jar as a subprocess and never links to or redistributes it, so it
does not extend to gitmole. If you ever want to ship the jar inside a gitmole
distribution, that changes; drop it or keep it as a separate download.

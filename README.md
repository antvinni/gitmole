<img src="https://raw.githubusercontent.com/antvinni/gitmole/main/docs/banner.svg" width="912" alt="gitmole">

# gitmole

A toolkit for digging into any cloned git repository: who works on it,
where the risk is, how old the code is, whether the repo itself is healthy,
and whether anything sensitive was ever committed.

Free. Any Stack. Local. Offline. Deterministic. Fast. 

- **Free.** MIT licence, no paid tier, no account, no token. A local clone needs no credentials, and a public `owner/repo` is cloned with plain git. Your `gh` login is only used for private repositories and for `owner/*`, and only when you ask for them. The tools it runs are open source too.
- **Any stack.** It reads what every repository has: the git log, git blame and the files themselves.
- **Local & Offline.** Everything runs against a clone on your machine. Nothing is uploaded, nothing phones home; the vulnerability database is a copy you download once.
- **Deterministic.** No AI at runtime. Every finding is a plain rule over counts you can recompute by hand. The same clone gives the same report every time. 
- **Fast.** A 4,400-commit repository takes under thirty seconds.

## Install

```bash
# macOS, or Linux with Homebrew: gitmole and the five tools it runs
brew tap antvinni/gitmole https://github.com/antvinni/gitmole
brew trust antvinni/gitmole
brew install gitmole

# anywhere else: scc, git-sizer, betterleaks, jscpd and osv-scanner on your PATH, then
pipx install gitmole
```

Linux package names, the release binaries, `--plots` and the pip caveats:
[docs/install.md](https://github.com/antvinni/gitmole/blob/main/docs/install.md).

## Usage

```bash
gitmole .                              # the clone you are in
gitmole /path/to/clone                 # any local clone
gitmole owner/repo                     # clones into a temp dir first, with gh or plain git
gitmole 'owner/*'                      # every non-archived repo of a user or org, one summary table

gitmole . --markdown report.md         # the same report as a Markdown document
gitmole . --json report.json           # every table, the watch list and the findings
gitmole . --fail-on warning            # exit 3 if any finding is a warning or worse
gitmole . --risk main --risk-threshold 5   # exit 3 if the files changed since main are too risky
gitmole . --since 2y --full            # the current team, every row and column
gitmole --clean                        # list what gitmole left behind, delete on a yes
```

A CI job that runs `gitmole . --fail-on critical --markdown - >> "$GITHUB_STEP_SUMMARY"`
blocks on secrets in source files and still posts the report. Every option:
[docs/cli.md](https://github.com/antvinni/gitmole/blob/main/docs/cli.md).

## What you get

Running `gitmole .` inside this repository:

```text
╭─ gitmole ────────────────────────────────────────────────────────────────────────────────────────╮
│ 185 commits  ·  2026-09-15 → 2026-09-17  ·  1 identity  ·  branch main                           │
│ 9,475 lines in 52 files  ·  Python, Ruby                                                         │
│ most commits on Wed at 20:00  ·  4% of commits are fixes  ·  100% of surviving code from 2026    │
│ 3 warnings, 1 note                                                                               │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
╭─ Findings (4) ───────────────────────────────────────────────────────────────────────────────────╮
│ ▲ Bus factor of one                                                                              │
│   vinni wrote 100% of the code that survives today                                               │
│   ↳ Pair someone with vinni on gitmole/ first; it is 100% theirs.                                │
│ ▲ Hotspots getting more complex                                                                  │
│   4 of the 10 top source hotspots grew by 25% or more in a year: gitmole/render.py (+194%),      │
│   gitmole/findings.py (+360%), gitmole/cli.py (+64%), gitmole/run.py (+34%)                      │
│   ↳ Split gitmole/render.py before the next change; its complexity grew 194% in a year.          │
│ ▲ Knowledge islands                                                                              │
│   1 area(s) with at least 200 lines were written almost entirely by one person: gitmole/ (vinni  │
│   100%). That is 98% of all lines added                                                          │
│   ↳ Pair someone with vinni on gitmole/ first; it is the largest at 7,607 lines.                 │
│ ● Bug magnets                                                                                    │
│   5 file(s) were fixed 3+ times in the last six months: gitmole/load.py (4 recent, 4 total);     │
│   gitmole/cli.py (3 recent, 3 total); gitmole/findings.py (3 recent, 3 total); gitmole/render.py │
│   (3 recent, 3 total); gitmole/run.py (3 recent, 3 total)                                        │
│   ↳ Review gitmole/load.py and gitmole/cli.py before the next release; expect the next bug       │
│   there.                                                                                         │
│ ✔ No secrets in history                                                                          │
│   betterleaks scanned every commit on every branch; 28 placeholder-shaped hits left out          │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
```

Below that: a watch list of the five files where the next bug is most
likely, with the reasons in words and a backtest of how the list would have
done; then tables for people, the knowledge map, the timeline, hotspots with
their complexity trend, change coupling, complex functions and repo health.
The full report is in
[docs/example.md](https://github.com/antvinni/gitmole/blob/main/docs/example.md),
and every section is explained in
[docs/output.md](https://github.com/antvinni/gitmole/blob/main/docs/output.md).

## The tool set

One tool per question; together they cover what a single command can tell
you about a clone.

| Question | Tool | Install |
|---|---|---|
| What is this repo, at a glance; who commits, when, how much churn | gitmole itself, from the git log | built in |
| How big is the codebase, per language | [scc](https://github.com/boyter/scc) | brew |
| Is the repo itself healthy (huge blobs, deep trees) | [git-sizer](https://github.com/github/git-sizer) | brew |
| Where is the risk: hotspots, coupling, ownership | gitmole's own change analysis over `git log --numstat` | built in |
| How old is the surviving code, per year and author | gitmole's own blame pass (one `git blame` per file at HEAD) | built in |
| Code-age and survival plots over time | [git-of-theseus](https://github.com/erikbern/git-of-theseus) | pip, opt-in with `--plots` |
| Per-function complexity, length, parameters | [lizard](https://github.com/terryyin/lizard) | pip, installed with gitmole; tracked code files only |
| Which blocks of code appear more than once | [jscpd](https://github.com/kucherenko/jscpd) | brew |
| Have secrets ever been committed | [betterleaks](https://github.com/betterleaks/betterleaks) | brew |
| Do the dependencies have known vulnerabilities | [osv-scanner](https://github.com/google/osv-scanner), offline against a local copy of the OSV database | brew, plus a one-time database download |

Why these and not others: [docs/tools.md](https://github.com/antvinni/gitmole/blob/main/docs/tools.md).

## Docs

- [Install](https://github.com/antvinni/gitmole/blob/main/docs/install.md): macOS, Linux, pipx, the check, pinned releases.
- [Command line](https://github.com/antvinni/gitmole/blob/main/docs/cli.md): every option, portfolio mode, exports and CI gates, big repositories.
- [The report and the output files](https://github.com/antvinni/gitmole/blob/main/docs/output.md): what each section and each file means.
- [Full example report](https://github.com/antvinni/gitmole/blob/main/docs/example.md): the whole `gitmole .` output for this repository.
- [Why these tools](https://github.com/antvinni/gitmole/blob/main/docs/tools.md): the rationale, what was left out, licences.
- [Development](https://github.com/antvinni/gitmole/blob/main/docs/development.md): setup, tests, releases, code layout.
- [Contributing](https://github.com/antvinni/gitmole/blob/main/CONTRIBUTING.md): bugs, ideas, pull requests, security reports.

## Safety

- Everything is offline except the optional clone step, which uses your
  existing gh auth. None of the tools send data anywhere; osv-scanner runs
  against a local copy of its database that you download once, and gitmole
  never downloads it for you.
- Remote targets are cloned into a fresh temp directory that is removed when
  the run ends. Local clones are only read, but the log export and the
  secrets scan touch all branches. `gitmole --clean` lists every directory
  gitmole created and deletes them after a y/N question.
- Secret values never reach the output directory. betterleaks reports to
  gitmole in memory, and gitmole stores a short keyed hash in place of the
  value, the matched text and the commit message. The key is random, made
  for that one report and never saved.

## License

[MIT](https://github.com/antvinni/gitmole/blob/main/LICENSE). gitmole runs
the tools it wraps as separate processes and bundles none of them; their
licences are listed in
[docs/tools.md](https://github.com/antvinni/gitmole/blob/main/docs/tools.md#licences).

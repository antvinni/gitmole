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

The opening of the report for [react](https://github.com/facebook/react), 35,263 commits
since 2013, at a pinned commit:

```text
╭─ react ──────────────────────────────────────────────────────────────────────────────────────────╮
│ 35263 commits  ·  2013-05-28 → 2026-09-16  ·  1880 identities  ·  branch main                    │
│ 681,078 lines in 4781 files  ·  JavaScript, TypeScript, Rust, CSS                                │
│ most commits on Wed at 16:00  ·  13% of commits are fixes  ·  1% of commits are reverts  ·  19%  │
│ of surviving code from 2026                                                                      │
│ 1 critical, 6 warnings, 8 notes                                                                  │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯

◎ Watch list
  file                                              why                                             
  ──────────────────────────────────────────────────────────────────────────────────────────────────
  compiler/packages/babel-plugin-react-compiler/s   changed 331 times · fixed twice in six months · 
  rc/Inference/InferMutationAliasingEffects.ts      Joe Savona wrote 98% of it ·                    
                                                    findNonMutatedDestructureSpreads() complexity 39
  packages/react-server/src/ReactFlightServer.js    changed 377 times · fixed once in six months ·  
                                                    renderModelDestructive() complexity 544         
  packages/shared/forks/ReactFeatureFlags.www.js    changed 583 times · fixed once in six months ·  
                                                    changes with                                    
                                                    packages/shared/forks/ReactFeatureFlags.test-ren
                                                    derer.www.js (77%) and 5 others                 
  packages/shared/ReactFeatureFlags.js              changed 575 times · fixed 6 times · changes with
                                                    packages/shared/forks/ReactFeatureFlags.test-ren
                                                    derer.js (80%) and 4 others                     
  packages/react-reconciler/src/ReactFiberWorkLoo   changed 342 times · fixed 4 times in six months 
  p.js                                              · flushSpawnedWork() complexity 48              
  ranked by churn × recent fixes × complexity × single ownership                                    
  6 months ago this list would have named 6 of the 211 files fixed since (a random 15 of the 1979   
  files that had changed more than once would name 0.3)                                             
```

The watch list is the point: the five source files most likely to need a
fix next, the reasons in words, and a backtest that says how the same list,
drawn six months earlier, would have done against the fixes that followed.
Between the header and that list the full report puts its findings, 15 for
react (1 critical, 6 warnings, 8 notes); below it, tables for people, the
knowledge map, the timeline, hotspots with their complexity trend, change
coupling, complex functions and repo health. Every section is explained in
[docs/output.md](https://github.com/antvinni/gitmole/blob/main/docs/output.md).

Reports on repositories you know, each at a pinned commit with a fixed
reference date, published as gitmole wrote them; the repo-health numbers
come from git-sizer over the whole clone, so a fresh clone can differ there:

| Repository | Commits | Lines | Watch list backtest |
|---|---:|---:|---|
| [curl](https://github.com/antvinni/gitmole/blob/main/docs/examples/curl.md) | 39,894 | 247,179 | named 15 of the 239 files fixed in the next six months; a random pick would name 5.0 |
| [django](https://github.com/antvinni/gitmole/blob/main/docs/examples/django.md) | 52,832 | 431,749 | named 13 of the 213 files fixed in the next six months; a random pick would name 2.8 |
| [react](https://github.com/antvinni/gitmole/blob/main/docs/examples/react.md) | 35,263 | 681,078 | named 6 of the 211 files fixed in the next six months; a random pick would name 0.3 |

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
- [Example reports](https://github.com/antvinni/gitmole/tree/main/docs/examples): curl, django and react at pinned commits, regenerated by `bin/render-examples`.
- [Validation](https://github.com/antvinni/gitmole/blob/main/docs/validation.md): the watch list against simpler lists at six cut-offs on three repositories.
- [Why these tools](https://github.com/antvinni/gitmole/blob/main/docs/tools.md): the rationale, what was left out, licences.
- [Development](https://github.com/antvinni/gitmole/blob/main/docs/development.md): setup, tests, releases, code layout.
- [Contributing](https://github.com/antvinni/gitmole/blob/main/CONTRIBUTING.md): bugs, ideas, pull requests, security reports.

## Safety

- Everything is offline except the optional clone step, which uses your
  existing gh auth. None of the tools send data anywhere; osv-scanner runs
  against a local copy of its database that you download once, and gitmole
  never downloads it for you.
- Remote targets are cloned into a fresh temp directory that is removed when
  the run ends. Local clones are only read. The secrets scan reads every
  branch; everything else describes the branch that is checked out.
  `gitmole --clean` lists every directory
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

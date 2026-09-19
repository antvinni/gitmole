<img src="https://raw.githubusercontent.com/antvinni/gitmole/main/docs/banner.svg" width="912" alt="gitmole">

# gitmole

A toolkit for digging into any cloned git repository: who works on it,
where the risk is, how old the code is, whether the repo itself is healthy,
and whether anything sensitive was ever committed.

Free. Any Stack. Local. Offline. Deterministic. Fast. 

- **Free.** MIT licence, no paid tier, no account, no token. A local clone needs no credentials, and a public `owner/repo` is cloned with plain git. Your `gh` login is only used for private repositories and for `owner/*`, and only when you ask for them. The tools it runs are open source too.
- **Any stack.** It reads what every repository has: the git log, git blame and the files themselves.
- **Local & Offline.** Everything runs against a clone on your machine. Nothing is uploaded, nothing phones home; the vulnerability database is a copy you download once.
- **Deterministic.** No AI at runtime. Every finding is a plain rule over counts you can recompute by hand. The JSON export carries each finding's rule, the numbers it fired on and, where a rule rests on a paper, the citation. The same commit gives the same bytes: gitmole's own CI runs it twice on every commit, compares the exports and attests the report.

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
gitmole . --risk main --risk-threshold 10  # exit 3 if the files changed since main hold over 10% of the risk
gitmole . --sarif gitmole.sarif        # the findings for GitHub code scanning or GitLab
gitmole . --sbom sbom.cdx.json         # a CycloneDX SBOM of every package the lock files pin
gitmole . --compare last.json          # what changed since an earlier --json export
gitmole analysis-repo --no-run --hook  # a coding agent's edit hook: history's view of the files it just touched
gitmole . --since 2y --full            # the current team, every row and column
gitmole --clean                        # list what gitmole left behind, delete on a yes
```

A CI job that runs `gitmole . --fail-on critical --markdown - >> "$GITHUB_STEP_SUMMARY"`
blocks on secrets in source files and still posts the report. The same
scoring wires into Claude Code, Cursor, Gemini CLI and pre-commit as a hook
that exits 2 over a threshold. Every option:
[docs/cli.md](https://github.com/antvinni/gitmole/blob/main/docs/cli.md).

## What you get

Reports on repositories you know, each at a pinned commit, published as gitmole wrote them:

| Repository | Commit | Commits | Lines | gitmole run |
|---|---|---:|---:|---:|
| [curl](https://github.com/antvinni/gitmole/blob/main/docs/examples/curl.md) | [`540ee5b5`](https://github.com/curl/curl/commit/540ee5b560cc6e775e11317048a13cc7e355bf91) | 39,758 | 247,179 | 59 s |
| [django](https://github.com/antvinni/gitmole/blob/main/docs/examples/django.md) | [`8cbdd4a8`](https://github.com/django/django/commit/8cbdd4a814397f81adf0129288f32b615bd1f94f) | 34,933 | 431,749 | 135 s |
| [react](https://github.com/antvinni/gitmole/blob/main/docs/examples/react.md) | [`2b19aecd`](https://github.com/facebook/react/commit/2b19aecd0e9111b774fad0fad9862e50bcb5bc8a) | 21,703 | 681,078 | 157 s |

Run times are one `gitmole CLONE` with every default step, on a MacBook Pro (M4, 16 GB).

## Evolution

Every release is run from its own source over the same pinned repositories and
judged by the same yardsticks, so the graphs show what each release changed
([measurement.md](https://github.com/antvinni/gitmole/blob/main/docs/measurement.md)
says how). Three questions decide whether gitmole is getting better:

- **Is it right?** How much of the gap between a random and a perfect top
  fifteen the watch list closes, against churn alone. It is drawn on the same
  four repositories every release (curl, django, react and gitmole), and the
  dots are thirteen Apache repositories nobody tuned against, scored by
  independent labels. Revisions × lines of code (from 0.8.0) closed most of the
  gap on the four. On the thirteen it closes 61% and draws with churn alone.
  The watch list is churn weighted by size: at the top it names about as many
  soon-to-be-fixed files as churn, it orders the whole pool better, and per
  line read it finds fewer
  ([validation.md](https://github.com/antvinni/gitmole/blob/main/docs/validation.md#what-the-ranking-is-for)).
- **Is it useful?** Of the findings the default report spells out, the share
  labelled worth acting on. The labels start at 0.28.0 and are, so far, one
  labeller's.
- **Does it run?** The share of awkward inputs (an empty repository, a shallow
  clone, a detached head, a non-UTF-8 path) it completes, and of the gate's
  planted problems it catches.

<img src="https://raw.githubusercontent.com/antvinni/gitmole/main/docs/evolution/ranking.svg" width="900" alt="Headroom of the watch list by release, against churn alone, with the held-out repositories">
<img src="https://raw.githubusercontent.com/antvinni/gitmole/main/docs/evolution/useful.svg" width="900" alt="Share of the default report's findings labelled actionable, by release">
<img src="https://raw.githubusercontent.com/antvinni/gitmole/main/docs/evolution/robustness.svg" width="900" alt="Runs completed and gate cases caught, by release">

What it costs (findings per repository, report length, run time, memory) and
every release's numbers:
[measurement-history.md](https://github.com/antvinni/gitmole/blob/main/docs/measurement-history.md).

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
| How deeply nested is the code, what did the authors flag, what imports what | [tree-sitter](https://github.com/tree-sitter/py-tree-sitter) grammars for eleven languages | pip, opt-in with `gitmole[structure]` |

Why these and not others: [docs/tools.md](https://github.com/antvinni/gitmole/blob/main/docs/tools.md).

## Docs

- [Install](https://github.com/antvinni/gitmole/blob/main/docs/install.md): macOS, Linux, pipx, the check, pinned releases.
- [Command line](https://github.com/antvinni/gitmole/blob/main/docs/cli.md): every option, portfolio mode, exports and CI gates, big repositories.
- [The report and the output files](https://github.com/antvinni/gitmole/blob/main/docs/output.md): what each section and each file means.
- [Example reports](https://github.com/antvinni/gitmole/tree/main/docs/examples): curl, django and react at pinned commits, regenerated by `bin/render-examples`.
- [Validation](https://github.com/antvinni/gitmole/blob/main/docs/validation.md): the watch list against other ways of ranking the same files at six cut-offs on three repositories.
- [Measurement](https://github.com/antvinni/gitmole/blob/main/docs/measurement.md) and [its history](https://github.com/antvinni/gitmole/blob/main/docs/measurement-history.md): how a release is judged better, and every release judged.
- [Why these tools](https://github.com/antvinni/gitmole/blob/main/docs/tools.md): the rationale, what was left out, licences.
- [References](https://github.com/antvinni/gitmole/blob/main/docs/references.md): the research and tools gitmole's rules are built on.
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
  `gitmole --clean` lists every directory gitmole created and deletes them
  after a y/N question.
- Secret values never reach the output directory. betterleaks reports to
  gitmole in memory, and gitmole stores a short keyed hash in place of the
  value, the matched text and the commit message. The key is random, made
  for that one report and never saved.

## License

[MIT](https://github.com/antvinni/gitmole/blob/main/LICENSE). gitmole runs
the tools it wraps as separate processes and bundles none of them; their
licences are listed in
[docs/tools.md](https://github.com/antvinni/gitmole/blob/main/docs/tools.md#licences).

<img src="https://raw.githubusercontent.com/antvinni/gitmole/main/docs/banner.svg" width="912" alt="gitmole">

# gitmole

A toolkit for digging into any cloned git repository: who works on it,
where the risk is, how old the code is, whether the repo itself is healthy,
and whether anything sensitive was ever committed.

Free. Any stack. Local. Offline. Deterministic. Fast.

- **Free.** MIT licence, no paid tier, no account, no token. A local clone needs no credentials. An `owner/repo` is cloned with `gh` when it is there, so a private repository uses your login, and with plain git when it is not, since a public repository needs no token; `owner/*` lists repositories through `gh`. The tools it runs are open source too.
- **Any stack.** It reads what every repository has: the git log, git blame and the files themselves.
- **Local & Offline.** Everything runs against a clone on your machine. Nothing is uploaded, nothing phones home; the vulnerability database is a copy you download once. Once, on a run with a terminal, gitmole asks five yes/no questions about its own findings and writes your answers to a file it tells you how to send — it still uploads nothing, and `GITMOLE_NO_FEEDBACK=1` turns the question off for good.
- **Deterministic.** No AI at runtime. Every finding is a plain rule over counts you can recompute by hand. The JSON export carries each finding's rule, the numbers it fired on and, where a rule rests on a paper, the citation. The same commit gives the same bytes: gitmole's own CI runs it twice on every commit, compares the exports and attests the report. One gitmole version is one toolchain, since the three tools are pinned and installed with it, and every report records the versions it ran.
- **Fast.** A default run over a large repository takes a minute or two (the example reports below give their times). The expensive passes have budgets: code age is skipped when its blame pass is projected past a minute (projected from the history it walks, so the same commit decides the same way on any machine), and the report says so and how to force it (`--deep`).

## What it is for

Trusting and triaging a repository you did not write, or one you are about to change.

- **A gate you can check.** Secrets in history, invisible and mixed-script characters, vulnerable dependencies and dependency-confusion shapes, agent settings that turn approval off, workflows that check out a pull request's head under `pull_request_target` or write an outsider's title or branch name straight into a script: each a plain rule with its evidence, the same on every run, fit for CI (`--fail-on`, SARIF). It fails closed: a gate whose scan did not finish exits 4 instead of passing, and `--baseline` gates only on what is new since an earlier run, subject by subject (a new unpinned action or a new long, complex function trips it; the ones already there do not), so a secret committed years ago does not block every build. A secret still in the tree is told apart from one only in history, which needs the history rewritten as well as the key rotated. Test code is what the ecosystem's conventions say it is, `smoke/`, `e2e` and `__fixtures__/` paths, Rust `#[cfg(test)]` modules and a Cargo binary only the tests run included, so a wrong key in a negative test is not a critical. A value the repository itself declared allowed (a gitleaks or betterleaks allowlist, `gitleaks:allow`) is a note, not a critical, and so is a database address on the loopback host or on a service the repository's own compose file declares. A tripped gate names on stderr the rules that tripped it. `gitmole --fetch-vuln-db CLONE` downloads the vulnerability database for a clone's ecosystems, and `--require-vuln-db` makes a run without one fail rather than pass unchecked.
- **A place to start looking.** The watch list is Tornhill's hotspots, changes × lines of code. An executable script counts as source whatever its name, and when most of a tree is something the list does not rank (documentation, prompts) the header says how much, with the most-changed documents listed beside it. It tells you where to read first, and `--hook` gives an agent the same ranking for the files it just edited, as context: it never blocks an edit on a history score no edit can lower. It is not a defect model: on repositories nobody tuned against, at the top it names about as many soon-to-be-fixed files as churn alone, and per line read it finds fewer ([validation.md](https://github.com/antvinni/gitmole/blob/main/docs/validation.md#what-the-ranking-is-for)).
- **Who and when.** Ownership, knowledge islands, code age and the files that change together, read from the history itself. A measure that could not be computed is named with the reason, and an area several people share equally has no main owner. Advice names only people still committing; someone who left is marked `(gone)`. A coding assistant credited in commit trailers is counted apart, as an area's agent-assisted share, never as an owner or an author (a name on a no-reply address several names share, or one credited almost only by trailer), and code a generator declares as its output (`.openapi-generator/FILES`, a "generated … do not edit" header) has no owner. When one person holds the bus factor, the truck factor and the knowledge islands, that is one finding, starting where the most files are at stake. `--path DIR` narrows all of it to one package or plugin of a monorepo.

## Install

```bash
# macOS, or Linux with Homebrew: gitmole and the three tools it runs, each pinned
brew tap antvinni/gitmole https://github.com/antvinni/gitmole
brew trust antvinni/gitmole
brew install gitmole

# anywhere else: gitmole from PyPI, then the same three pinned tools into gitmole's own directory
pipx install gitmole
gitmole --install-tools

# either way: every tool gitmole runs, the version found against the one pinned
gitmole --doctor
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
gitmole . --fail-on critical --baseline last.json  # gate only on what is new since last.json
gitmole . --path backend/plugins/github  # one directory: its history, owners and watch list
gitmole analysis-repo --no-run --hook  # an agent's edit hook, over the output of one earlier `gitmole . --out analysis-repo`
gitmole . --since 2y --full            # the current team, every section and every finding
gitmole analysis-repo --no-run --section people --csv  # every row of one table of an earlier run, as CSV
gitmole --clean                        # list what gitmole left behind, delete on a yes
gitmole --doctor                       # every tool gitmole runs, the version found against the one pinned
gitmole --install-tools                # the three pinned tools, downloaded into gitmole's own directory
```

A CI job that runs `gitmole . --fail-on critical --markdown - >> "$GITHUB_STEP_SUMMARY"`
blocks on secrets in source files and still posts the report; in GitHub Actions,
`uses: antvinni/gitmole@v0.44.0` does that with the pinned tools installed and cached
([GitHub Actions](https://github.com/antvinni/gitmole/blob/main/docs/cli.md#github-actions)),
and a [Dockerfile](https://github.com/antvinni/gitmole/blob/main/docs/cli.md#docker) runs it anywhere else. The same
scoring wires into Claude Code, Cursor, Gemini CLI and pre-commit as a hook
that tells the agent what history says about the files it edited, without blocking it, after one `gitmole . --out analysis-repo` for it
to score against ([Agent hooks](https://github.com/antvinni/gitmole/blob/main/docs/cli.md#agent-hooks)). Every option:
[docs/cli.md](https://github.com/antvinni/gitmole/blob/main/docs/cli.md).
What each part of the report means and what to do first:
[Reading your first report](https://github.com/antvinni/gitmole/blob/main/docs/first-report.md).

## What you get

Reports on repositories you know, each at a pinned commit, published as gitmole wrote them:

| Repository | Commit | Commits | Lines | gitmole run |
|---|---|---:|---:|---:|
| [curl](https://github.com/antvinni/gitmole/blob/main/docs/examples/curl.md) | [`540ee5b5`](https://github.com/curl/curl/commit/540ee5b560cc6e775e11317048a13cc7e355bf91) | 39,758 | 247,179 | 47 s |
| [django](https://github.com/antvinni/gitmole/blob/main/docs/examples/django.md) | [`8cbdd4a8`](https://github.com/django/django/commit/8cbdd4a814397f81adf0129288f32b615bd1f94f) | 34,933 | 431,749 | 80 s |
| [react](https://github.com/antvinni/gitmole/blob/main/docs/examples/react.md) | [`2b19aecd`](https://github.com/facebook/react/commit/2b19aecd0e9111b774fad0fad9862e50bcb5bc8a) | 21,703 | 681,078 | 65 s |

Run times are one `gitmole CLONE` with every default step, on a MacBook Pro (M4, 16 GB).

## Evolution

Every release that changes what gitmole finds or ranks is run from its own
source over the same pinned repositories and judged by the same yardsticks
([measurement.md](https://github.com/antvinni/gitmole/blob/main/docs/measurement.md)).

The ranking has held since 0.8.0. On the four repositories every release is
drawn over, headroom rose from 0.73 to 0.92 at 0.8.0 and has been 0.93 since
0.11.0. The lower figures in the history's table (0.62 at 0.28.0, 0.65 at
0.37.0, 0.60 at 0.38.0) are changes to the yardstick, not to the ranking:
repositories joined the set at 0.28.0 and 0.38.0, and 0.37.0 rebuilt the set
and took its cut-offs from first-parent commits. Recent releases cut cost
rather than raising effectiveness: from 0.38.0 to 0.42.0, on the same
development set, the median findings per repository fell from 19.5 to 10, the
report from 216 to 198 lines, and 0.40.0 to 0.42.0 answered findings that
reviewers had checked and found false.

<img src="https://raw.githubusercontent.com/antvinni/gitmole/main/docs/evolution/ranking.svg" width="900" alt="Headroom of the watch list by release, against churn alone and size alone, with the held-out repositories">
<img src="https://raw.githubusercontent.com/antvinni/gitmole/main/docs/evolution/findings.svg" width="900" alt="Findings per repository by release: the median, the 90th percentile, and how many the default report spells out">

Every run completes, and the gate catches 3 of 3, since 0.28.0.

Every release's numbers, including what it costs in report length, run time and
memory:
[measurement-history.md](https://github.com/antvinni/gitmole/blob/main/docs/measurement-history.md).

## The tool set

One tool per question; together they cover what a single command can tell
you about a clone.

| Question | Tool | Install |
|---|---|---|
| What is this repo, at a glance; who commits, when, how much churn | gitmole itself, from the git log | built in |
| How big is the codebase, per language | [scc](https://github.com/boyter/scc) | brew |
| Where is the risk: hotspots, coupling, ownership | gitmole's own change analysis over `git log --numstat` | built in |
| How old is the surviving code, per year and author | gitmole's own blame pass (one `git blame` per file at HEAD) | built in |
| Code-age and survival plots over time | [git-of-theseus](https://github.com/erikbern/git-of-theseus) | pip, opt-in with `--plots` |
| Per-function complexity, length, parameters | [lizard](https://github.com/terryyin/lizard) | pip, installed with gitmole; tracked code files only |
| Have secrets ever been committed | [betterleaks](https://github.com/betterleaks/betterleaks) | brew |
| Do the dependencies have known vulnerabilities | [osv-scanner](https://github.com/google/osv-scanner), offline against a local copy of the OSV database | brew, plus a one-time database download |
| How deeply nested is the code, what did the authors flag, what imports what | [tree-sitter](https://github.com/tree-sitter/py-tree-sitter) grammars for eleven languages | built in, pinned (Python 3.10+) |

Why these and not others: [docs/tools.md](https://github.com/antvinni/gitmole/blob/main/docs/tools.md).

## Docs

Using gitmole:

- [Install](https://github.com/antvinni/gitmole/blob/main/docs/install.md): macOS, Linux, pipx, the check, pinned releases.
- [Command line](https://github.com/antvinni/gitmole/blob/main/docs/cli.md): every option, portfolio mode, exports and CI gates, big repositories.
- [Reading your first report](https://github.com/antvinni/gitmole/blob/main/docs/first-report.md): one screen, each section in plain words, and what to do first.
- [The report and the output files](https://github.com/antvinni/gitmole/blob/main/docs/output.md): what each section and each file means.
- [Example reports](https://github.com/antvinni/gitmole/tree/main/docs/examples): curl, django and react at pinned commits, regenerated by `bin/render-examples`.
- [Why these tools](https://github.com/antvinni/gitmole/blob/main/docs/tools.md): the rationale, what was left out, licences.
- [References](https://github.com/antvinni/gitmole/blob/main/docs/references.md): the research and tools gitmole's rules are built on.
- [Validation](https://github.com/antvinni/gitmole/blob/main/docs/validation.md): the watch list against other ways of ranking the same files at six cut-offs on the development set and the thirteen held-out repositories.

Working on gitmole:

- [Measurement](https://github.com/antvinni/gitmole/blob/main/docs/measurement.md) and [its history](https://github.com/antvinni/gitmole/blob/main/docs/measurement-history.md): how a release is judged better, and every measured release.
- [Development](https://github.com/antvinni/gitmole/blob/main/docs/development.md): setup, tests, releases, code layout.
- [Pipeline](https://github.com/antvinni/gitmole/blob/main/docs/pipeline.md): how a change earns its place, and which decisions an agent does not make.
- [Contributing](https://github.com/antvinni/gitmole/blob/main/CONTRIBUTING.md): bugs, ideas, pull requests, security reports.
- [AGENTS.md](https://github.com/antvinni/gitmole/blob/main/AGENTS.md): the rules a coding agent working on gitmole follows, unattended or not.

## Safety

- Everything is offline except the optional clone step (gh with your
  existing login, else plain git), the tool download you ask for with `--install-tools`
  or a yes to the missing-tools question, and the vulnerability database you ask for with
  `--fetch-vuln-db`. None of the tools send data anywhere; osv-scanner runs against that
  local copy of its database, and gitmole never refreshes it on its own, so the same commit
  gives the same report until you fetch again.
- Remote targets are cloned into a fresh temp directory that is removed when
  the run ends. Local clones are only read. The secrets scan reads the whole
  history of the checked-out commit and the objects no branch reaches;
  everything else describes the branch that is checked out.
  `gitmole --clean` lists every directory gitmole created and deletes them
  after a y/N question, except the tools `--install-tools` placed for the
  version you run, which are in use.
- Secret values never reach the output directory. betterleaks reports to
  gitmole in memory, and gitmole stores a short keyed hash in place of the
  value, the matched text and the commit message. The key is random, made
  for that one report and never saved.

## License

[MIT](https://github.com/antvinni/gitmole/blob/main/LICENSE). gitmole runs
the tools it wraps as separate processes and bundles none of them; their
licences are listed in
[docs/tools.md](https://github.com/antvinni/gitmole/blob/main/docs/tools.md#licences).

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

`gitmole --help` prints the same groups, one line per option; this is the long form.

### Run

Where the output goes and how much a run may spend.

| Option | What it does |
|---|---|
| `--out DIR` | The output directory. Default: `analysis-<repo>` next to a local clone, or in the current directory for a remote target. |
| `--no-run` | Skip the tools and re-render the report from the output directory of an earlier run. **The target is that directory, not the clone**: `gitmole analysis-curl --no-run`. `--out` is not read here. Works with the exports, `--risk` and `--compare`. |
| `--workers N` | How many tools run at once. Default 6. |
| `--timeout SECONDS` | Seconds any single tool may run before it is killed. Default 900. A killed tool is marked in the report and the rest still renders. |
| `--time-budget SECONDS` | Skip the code-age pass when its projected time exceeds this. Default 60. |
| `--budget N` | Skip the plots above this many git blames. Default 50,000. |
| `--deep` | Run code age and plots regardless of their budgets. |
| `--plots` | Also draw the git-of-theseus code-age and survival charts. Needs `gitmole[plots]`. |

### Scope

Which history and which files the analysis reads.

| Option | What it does |
|---|---|
| `--since WHEN` | Bound the history by author date: `2y`, `18m`, `90d` or a `YYYY-MM-DD` date. People, activity, timeline, hotspots and coupling then describe the current team rather than the founders. File ages and code age always cover the whole history, identity aliases are still merged over all of it, and an empty window is an error. |
| `--path DIR` | Describe only the files under DIR, a directory of the tree at HEAD relative to the repository root. Repeatable. The header says the scope and what stays repository-wide; the output directory is `analysis-<repo>-<dir>`, so a scoped run never replaces the whole repository's. See [One part of a repository](#one-part-of-a-repository). |
| `--gone MONTHS` | How long without a commit counts as gone, measured before the last commit. Default 12. |
| `--file-types LIST` | Which extensions count as code, comma-separated, or `all`. The default is a built-in source list plus names like Makefile and Dockerfile. |
| `--ignore-data` | Exclude data-like files (csv, json, lock files, minified and vendored assets) from code age, function metrics and plots. Never changes what a file is: the classifier reads every tracked file. |
| `--ignore GLOB` | An extra ignore pattern for the same steps. Repeatable. |

### Report and exports

What is printed, and what is written beside it.

| Option | What it does |
|---|---|
| `--full` | A report option, not a help option: print the report with every section, column and row. Adds the hotspots, size, activity and code age tables; the default report keeps the columns you read, caps each table, elides long paths in the middle, hides test files, deleted files and vendored code, shows a directory that changes as one as a single coupling row, and names in one line the findings labelled true but never acted on. With `--clean`, it lists each temp clone rather than one row for them all. |
| `--json PATH` | Write every table, the watch list and the findings as JSON to PATH, or `-` for stdout. |
| `--markdown PATH` | Write the report as Markdown to PATH, or `-` for stdout. |
| `--sarif PATH` | Write the findings as SARIF 2.1.0 to PATH, or `-` for stdout, for GitHub code scanning and GitLab. See [SARIF](#sarif). |
| `--sarif-scope SCOPE` | With `--sarif`, `head` or `history`: `head` (the default) keeps only the results whose file is in the tree; `history` keeps every result, the commit in its properties. |
| `--sbom PATH` | Write a CycloneDX 1.6 SBOM of every locked package to PATH, or `-` for stdout. See [SBOM](#sbom). |
| `--compare BEFORE.json` | Add a "Since last report" section against an earlier `--json` export of the same clone: findings new, resolved and persisting (with the counts that moved), files that entered or left the watch list. Works with `--no-run`; never changes the exit code; not with `owner/*`. |
| `--feedback` | Ask five yes/no questions about the findings this run spelled out, and write the answers to `gitmole-feedback.json` beside the output. gitmole sends nothing: it prints a `gh issue create` command and a URL, and you choose. The file holds the rule id, the severity, your answer, gitmole's version and three bands (main language, file count, commit count) — no paths, names or values. Asked once on a plain interactive run without the flag; a decline is never repeated, and an answer is followed up after 90 days. Never asked with an export or gate flag (`--json`, `--markdown`, `--sarif`, `--sbom`, `--fail-on`, `--risk`, `--hook`, `--compare`), in portfolio mode, without a terminal, or where the environment declares CI. `GITMOLE_NO_FEEDBACK=1` turns it off for good, and `GITMOLE_CACHE=off` keeps no record of having asked. |

### Gates

Exit codes for CI and for coding agents.

| Option | What it does |
|---|---|
| `--fail-on LEVEL` | Exit 3 if any finding is at LEVEL or worse, LEVEL being `critical`, `warning` or `info`; exit 4 when none is and a step the findings read did not complete. The rules nobody has labelled yet, which the default report folds into its closing "not labelled yet" line, count like any other; the line on stderr naming what tripped the gate says when it was one of them. See [Exit codes](#exit-codes). |
| `--require-vuln-db` | Exit 4 when the dependency scan ran with no vulnerability database, so no package was checked. Without it that run is said on stderr under a gate and in the SARIF, and passes. See [No vulnerability database](#no-vulnerability-database). |
| `--baseline BEFORE.json` | With an earlier `--json` export of the same clone: the findings it already had are still reported, their statement opening "In the baseline:", and do not count toward `--fail-on`. See [Baseline](#baseline). Not with `owner/*`. |
| `--risk BASE` | Score the files changed since BASE (the merge base with HEAD) with the watch list's score (each file's share, in percent, of the repository's revisions × lines of code), in one extra section with a total. Needs a local path; works with `--no-run`, and the JSON carries the total. |
| `--risk-threshold N` | With `--risk`: exit 3 when the changed files together hold more than N percent; exit 4 when they do not and scc, the log or the change analysis did not complete. With `--hook`: exit 2 at the same point. |
| `--hook` | With `--no-run` and an output directory: read an agent hook's JSON on stdin (or take files after `--`), score the files it names like `--risk`, print a summary the agent reads back, and exit 2 when `--risk-threshold` is exceeded. See [Agent hooks](#agent-hooks). |

### Tools and housekeeping

Checking and installing the tools, looking before a run, and tidying up after one.

| Option | What it does |
|---|---|
| `--doctor` | List every tool gitmole runs with the version found and the version pinned, and where to get a missing or moved one; whether the structure step can run; and the date of the local vulnerability database; then exit. Takes no target; other options are ignored. Exit 0 when every tool is at its pin, 1 otherwise. |
| `--install-tools` | Download the three tools at the versions gitmole pins, from the release archives the Homebrew formula installs and checked against the same sha256, into gitmole's own directory, one `<tool>-<version>` directory each: `GITMOLE_TOOLS` if set (an absolute path), else `~/Library/Application Support/gitmole/tools` on macOS or `$XDG_DATA_HOME/gitmole/tools` (default `~/.local/share/gitmole/tools`) elsewhere. Each tool is run once after it lands to check it prints its pin. A run looks in the current pins' directories before PATH. Takes no target and refuses `--doctor`; other options are ignored. Nothing downloads when the directory cannot be written. Exit 0 when all three landed, 1 when one did not (no build for this platform, a hash mismatch, no network, a copy that does not run here) with the reason named. This, `--fetch-vuln-db` and a yes to the missing-tools question, which is asked only of a person at a terminal and never in CI or with an export or gate flag, are the only downloads gitmole makes of its own; see [install.md](install.md) for everything that reaches the network. |
| `--fetch-vuln-db [CLONE]` | Download osv-scanner's offline vulnerability database for the ecosystems whose lock files CLONE holds (default `.`), with the pinned osv-scanner, into its cache (`OSV_SCANNER_LOCAL_DB_CACHE_DIRECTORY`, else the platform cache), then print the database's date and exit. The scan itself stays offline: a run reads the local copy and every report names its date, so the same commit gives the same report until you fetch again. Never automatic. Takes a local clone only; refuses `--doctor` and `--install-tools`. Exit 0 when fetched or when the clone has no lock file (nothing to fetch), osv-scanner's own code otherwise. |
| `--list-file-types` | List the file types in the tree with counts and whether each counts as code, then exit. |
| `--clean [DIR]` | List what gitmole left behind, temp clones, `analysis-*` outputs under DIR and tools `--install-tools` placed for pins this version no longer uses, with their sizes, and delete them after a y/N question. The temp clones show as one row with their count; `--full` lists each one. Exit 0 whether you answer yes or no, 2 without a terminal. |
| `--yes` | With `--clean`: delete without asking. For scripts and pipes. |
| `--version` | Print gitmole's version and exit. |
| `-h`, `--help` | Print the options in these groups, one line each, with examples, and exit. `--help --full` prints the same: `--full` is a report option. |

## One part of a repository

`--path DIR` narrows a run to the files under DIR: a package of a monorepo, one plugin, the subsystem a new
hire was given. DIR is relative to the repository root and must be a directory of the tree at HEAD; a
mistyped one is an error before anything is written. Give it more than once for several directories.

What is narrowed, and how:

| Step | Scope |
|---|---|
| change log (`git log`) and everything read from it: revisions, fixes, coupling, ownership, authorship, the truck factor, activity, timeline, the backtest | the commits that touch DIR, with only DIR's files in them (`git log -- DIR`). A commit's other files do not count towards its size |
| commits, people, identities, dates in the header | the same commits. Merges are those whose diff against their first parent touches DIR |
| size (scc), the watch list, hotspots, complexity trend | the files under DIR. scc still reads the tree, and the report keeps DIR's files |
| code age (blame), function metrics (lizard) | the files under DIR only |
| structure (tree-sitter) | the whole tree is parsed and the imports resolved, then the result is narrowed to DIR: a file only the rest of the repository imports is not called unreferenced |
| knowledge map, components, the truck factor's areas | counted from below DIR: `--path backend/plugins` maps `backend/plugins/github/`, `backend/plugins/gitlab/` and so on, with the files directly in DIR as the root files |
| committed binaries, symlinks, Trojan Source characters | the files under DIR |

What stays repository-wide, and why:

- **secrets** (betterleaks over history, unreachable objects, credential file names): history is one object
  store, and whoever has the clone has every secret in it, wherever it was committed;
- **dependencies** (osv-scanner, lock files, dependency confusion, install scripts, unused declared
  dependencies): a manifest above DIR, a `go.mod` or a workspace root, governs DIR's code as much as one inside it;
- **signing**, **workflows** (actions pinning), **policy files** (licence,
  security policy, CODEOWNERS, the OSPS baseline), **submodules** and **agent files**: each is a property of
  the repository, declared at its root.

Not with `--no-run` (a re-render cannot narrow an analysis), `--plots` (git-of-theseus reads the whole tree)
or `owner/*`. `--compare` refuses an export of a different scope, a whole-repository one included.

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

The same commit with the same options gives the same bytes. The export is
written with its keys sorted, rows come back in one order whatever order a
parallel step wrote them in, and each secret's keyed hash (the key is made
for one run) is replaced by a stable label, `v1`, `v2`, the same value
getting the same label. What does differ from one run to the next sits in
one top-level key, `envelope`: the blame pass's measured projection (and
`projected_partial` when its sample stopped early, over the budget), the
output directory, the clone's path on this machine, the structure cache's
hits, each step's wall time and peak memory, and the count of objects no ref
reaches — a reflog, a dropped stash, whatever gc has not collected — which
belongs to the clone and not to the commit, so two clones of one commit
differ there. A secret found in one of those objects is a finding this clone
has and another does not. gitmole's own CI runs it
twice on every commit, once more in another time zone and the C locale, and
once on Linux, compares the exports without the envelope (a section an
external tool produces only when both platforms ran the same version of
it), and
on `main` attests the report with `actions/attest`, so a report can be
checked as coming from that commit and that workflow:

```bash
gh attestation verify report.json --repo antvinni/gitmole
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
### Exit codes

| Code | Meaning |
| --- | --- |
| 0 | Done, and no gate asked for found anything. Without `--fail-on`, `--risk-threshold` or `--hook` a run exits 0 even when a step did not complete; the run names the step and the report's header says what is missing. |
| 1 | `--doctor` found a tool off its pin; `--install-tools` or `--clean` could not do all it was asked. |
| 2 | Bad arguments or an unreadable output directory; with `--hook`, over `--risk-threshold` (a `--hook` with no output directory says how to make one and exits 0). |
| 3 | A gate found what it stops on: a finding at the `--fail-on` level or worse that is not in the `--baseline`, or a change over `--risk-threshold`. |
| 4 | A gate could not check: a step it reads failed, timed out or was skipped, and it found nothing it stops on in what the other steps left. The message names the step; `run.log` in the output directory says why. `--fail-on` reads every step but the two plots and the backtest; `--risk-threshold` and `--hook` read scc, the log and the change analysis. Also, with `--require-vuln-db`, a dependency scan that had no vulnerability database. |
| 130 | Interrupted. |

A secrets scan that timed out leaves no secrets table, so before 4 existed
`--fail-on critical` passed a repository whose scan never finished. The
same holds for a re-render: `--no-run` on an output directory with a failed
step exits 4 under a gate. An output directory from before steps were
recorded (before 0.8.0) cannot say, and is judged on what it holds. Under
`owner/*` the code is 3 if any repository tripped the gate, else 4 if any
had an unfinished step. `--sarif` records the same thing on its run:
`invocations[0].executionSuccessful` is false and
`toolExecutionNotifications` names each unfinished step.

### No vulnerability database

osv-scanner runs `--offline`, and with no offline database on disk it
checks nothing and exits cleanly. The step completed, so it is not a
failed step, and until 0.40.0 `--fail-on critical` passed such a run as a
clean one. Now a gate says so on stderr, once:

```
dependency gate: no vulnerability database; nothing was checked
```

and the SARIF carries a `warning` notification with the descriptor
`no-vulnerability-database` in `invocations[0].toolExecutionNotifications`
(the invocation stays successful). The exit code does not change unless
you asked for the database: `--require-vuln-db` makes it 4, the code for a
gate that could not check. It is not the default because the database is
a download (the report's header names the command), and the Action's
`vulnerability-db` input is off by default, so every default CI run would
exit 4 and the code would stop meaning anything; the Action passes
`--require-vuln-db` when `vulnerability-db: true`. A repository with no
lock file had nothing to check and needs no database.

### Baseline

The secrets step reads the whole history, because a key rotated or a file
deleted is still in every clone. So a repository with a secret committed in
2021 and deleted in 2022 has a critical finding on every run, and
`--fail-on critical` would block it forever. `--baseline` takes an earlier
`--json` export of the same clone and gates on what is new since:

```yaml
# first run, once, after the findings in it have been looked at: keep the export
- run: gitmole . --json gitmole-baseline.json
# every later run: report everything, fail only on what the baseline did not have
- run: gitmole . --fail-on critical --baseline gitmole-baseline.json --sarif gitmole.sarif
```

Commit the baseline, or keep it as a CI artifact, and write it again when
the findings in it have been dealt with. A finding counts as in the
baseline when the export has one with the same rule id (and, for the rules
that report several, the same metric or email) at the same severity or
worse; a finding that was a warning and is now critical is new. The rules
whose one finding holds many subjects are compared by their subjects
instead: a secret's place by betterleaks' fingerprint
(`commit:file:rule:line`, the same one `.betterleaksignore` takes), a
vulnerable package by name, version, lock file and advisory ids, an unpinned
action by workflow file and `uses:` ref, a brain method or deeply nested
function by file and name, a bug magnet by file. The subjects the
baseline's finding did not hold go through the same rule on their own, and
what that finds, at the severity it finds it, is what counts: a new secret
or a new unpinned action fails the gate while the old ones stay reported,
and a new magnet with three fixes is a note even when the finding is a
warning because of an old one. A known value committed again is a new
place, and counts. A truck factor counts when it hangs on a person, or
names an area of one, the baseline's did not. The subjects are read from
the rows every `--json` export carries, so an older baseline works as it
is; one that lacks a rule's rows (written before the structure step ran,
say) is judged for that rule by its rule id alone, as every rule but
secrets and vulnerable dependencies was until 0.42.0.
The hygiene step keeps 50 unpinned actions per run, so one past the
fiftieth is not seen.
Findings in the baseline carry `"baseline": "in the baseline"` in the JSON
(`"new"` otherwise) and `baselineState` `unchanged` or `new` in the SARIF;
stderr names the ones that did not count. `--baseline` does not change the
exit code for a step that did not complete: 4 stays 4.

`--risk-threshold` needs `--risk`; it exits 3 when the files changed since
main hold more than 10% of the repository's revisions × lines of code, and
the total prints in the Change risk caption.

The scale changed in 0.8.0: before, the total was a sum of factor-product
scores with no fixed unit. A threshold chosen for 0.7 has to be chosen
again; run `gitmole . --risk main` on a few merged changes and read the
totals.

The Change risk section, and `change_risk` in the JSON, carry what history
says about the change beyond its total. Each scored file has its hotspot
rank, fix counts, owner and share, minor-contributor count and whether it
is on the watch list. `coupling_gaps` lists the companions a touched file
usually changes with that the change did not touch: a file that moved in
70% or more of the touched file's changes, over twenty or more of them
(ROSE's directed confidence, after Zimmermann et al.). Replayed on real
commits with one file left out, 54% of the warnings name the file that was
left out, and 3% of complete commits get one, on thirteen repositories
nobody tuned it on ([validation.md](validation.md#the-hooks-coupling-warning));
so one is uncommon and right a little more often than not. Every touched file,
scored or not, also says what imports it (`imported by 4 files, 31 counting
what imports them`), from the structure step's import graph. Only importers
in a language the graph is trusted for count: Python, JavaScript,
TypeScript (`.ts` and `.tsx` gated apart) or Go, with ten or more files of that
language and 60% or more of its imports resolved (`structure.trusted`, the same gate as possibly unreferenced
files), and never a test file, which exercises a module rather than breaks
with it; a file whose own language fails that gate and that no trusted
importer names gets no count. `dependents` in the
JSON holds both counts and names up to ten direct importers. A dynamic import
or a plugin loaded by name is not in that graph, so the count is a floor.
And `change` holds Kamei et al.'s
just-in-time factors as named reasons beside the mass share, never folded
into it: the files, directories, subsystems and commits, whether it is a
fix by its subjects, lines added against the lines those files had, how
evenly the change spreads over its files, how many of the files changed
this month, their prior changes and people, and the author's prior commits
here and in these subsystems (`touches 9 files across 4 directories in 2
subsystems, 3 commits; a fix, by its subject; adds 340 lines to 1,200
(28%), removes 12; most of the change is in one file; 3 of the 9 files
changed this month; the files have 130 prior changes by 3 people; Bob has
3 prior commits here, 2 in these subsystems`).

## SARIF

`gitmole . --sarif gitmole.sarif` writes the findings in the format GitHub
code scanning and GitLab read: one run with gitmole as the driver, a rule
per finding id with its title, detail and advice, a result per place the
evidence names (a finding about a whole file, such as `lockfile_drift`'s
manifests, points at line 1 of each; `unpinned_actions` has a result per
`uses:` the hygiene step recorded, up to 50, at its line), `level` from the severity (critical is `error`, warning is
`warning`, info is `note`). The security rules alone (secrets, credential
files, vulnerable dependencies, Trojan Source characters, unpinned actions,
install scripts, dependency confusion, committed binaries, submodule URLs,
symlinks out of the tree, agent settings that turn approval off, literal
MCP secrets; `SECURITY` in `gitmole/sarif.py`) carry
`properties["security-severity"]`, which is what GitHub ranks security
alerts by (9.0 critical, 5.0 warning, 2.0 info; a vulnerable dependency
carries its advisory's own score, a malicious one 10.0), and the tag
`security`. The rest carry no security-severity, so code scanning files a
bug magnet or a brain method as code quality rather than as a Medium
vulnerability, and their tag is `maintainability`. Every result has a `partialFingerprints` entry hashed from rule,
path, commit and line, so a second upload updates alerts instead of
duplicating them; for a secret that hash comes from where it was found,
never from the value, so two runs agree although the keyed value hashes
never do. A secret is one result per place, pointing at the file and
naming the commit; its line belongs to that commit's version of the file,
so under the default `--sarif-scope head` it carries no region, and a
secret in a file no longer in the tree, a sweeping commit and anything else
without a HEAD location are left out. `--sarif-scope history` keeps them,
with the commit under `properties.commit`. A finding whose every place the
head scope leaves out still gets one result, with no location and
`properties.inTree` false, so the document holds every finding `--fail-on`
stops on: a critical made only of secrets in files deleted years ago exits
3 and is an `error` result. SARIF allows a result without a location;
GitHub code scanning accepts it and does not display it, GitLab drops it,
and `--sarif-scope history` gives it its places.

```yaml
- run: gitmole . --out analysis --sarif gitmole.sarif
- uses: github/codeql-action/upload-sarif@v3
  with:
    sarif_file: gitmole.sarif
```

## GitHub Actions

The repository is also a composite action. It installs gitmole from PyPI,
the pinned tools with `--install-tools` at the versions that release pins
(the formula's archives and hashes), caches them under the runner's tool
cache keyed on those pins, runs one analysis and appends the Markdown report
to the job summary:

```yaml
on: pull_request
jobs:
  gitmole:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
        with:
          fetch-depth: 0          # gitmole reads the whole history; a shallow clone has one commit
      - uses: antvinni/gitmole@v0.41.0
        with:
          fail-on: critical
```

The tag decides the version: `@v0.41.0` installs `gitmole==0.41.0`.
Pinned to a commit SHA instead (with the tag in a comment, as gitmole's own
`unpinned_actions` finding asks of a workflow), or used from a branch or as
`uses: ./`, the action installs gitmole from its own source at that commit;
the `version` input overrides both. The inputs:

| Input | Default | |
|---|---|---|
| `args` | `.` | The target and any other options, split on whitespace (no shell quoting). |
| `fail-on` | none | `critical`, `warning` or `info`: fail the step when a finding is at that severity or worse. |
| `risk` | none | `--risk` base, for a pull request `origin/${{ github.base_ref }}`. |
| `risk-threshold` | none | With `risk`: fail when the changed files hold more than N percent. |
| `baseline` | `false` | Gate only on what is new since the default branch's last run. See [Baseline in the Action](#baseline-in-the-action). |
| `sarif` | none | Write SARIF to this path. |
| `upload-sarif` | `true` | With `sarif`: upload it to code scanning (`category: gitmole`); the job needs `permissions: security-events: write`, which a pull request from a fork does not get. |
| `vulnerability-db` | `false` | Download osv-scanner's offline database first, cached per day, and pass `--require-vuln-db`, so a scan that still found no database exits 4. |
| `summary` | `true` | Append the Markdown report to the job summary. |
| `version` | the tag | The gitmole version to install from PyPI. |
| `python-version` | `3.12` | The Python gitmole runs on. |

Outputs: `exit-code` (0; 3 when a gate tripped; 4 when a gate could not check
because a step it reads did not finish, or `vulnerability-db` found no database), `markdown` (the report's path) and
`sarif`, and with `baseline` the path of the export it gated against
(`baseline`, empty on a first run). A tripped gate, or one that could not check, fails the job only after
the summary is written and the SARIF uploaded, so a blocked pull request still
shows why.

### Baseline in the Action

With `baseline: true` the action keeps the [baseline](#baseline) for you in
the Actions cache. A push to the default branch saves that run's `--json`
export; a pull request, or a push to any other branch, restores the default
branch's latest one and passes it as `--baseline`, so a pull request fails
only on what it adds. Nothing is saved from a pull request, and nothing from
a run that exited 4, whose export lacks what the unfinished step would have
found: the cached baseline stays. The cache key is per repository, default
branch and `args`, so two gitmole steps over different targets keep two
baselines. When `args` already writes `--json` to a file, that export is the
one saved; otherwise the action adds its own.

```yaml
on:
  push:
    branches: [main]      # saves the baseline
  pull_request:           # gates on what is new since it
jobs:
  gitmole:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      security-events: write
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
        with:
          fetch-depth: 0
      - uses: antvinni/gitmole@v0.41.0
        with:
          fail-on: critical
          baseline: true
          sarif: gitmole.sarif
```

The first run has no baseline, says so in a notice, and gates on every
finding like a run without `baseline`; so does every run until a push to the
default branch has saved one, and again after the cache entry expires (GitHub
evicts one not read for seven days). A secret committed years ago therefore
fails the first run: look at it, rotate it, and the push that follows saves a
baseline that holds it. The baseline records what the default branch had, not
what anyone reviewed; a finding that landed on the default branch is in it.

The network is reached in the setup steps only: pip, the tool archives, and
with `vulnerability-db: true` the OSV database for the ecosystems the
workspace's lock files use. The scan itself runs `osv-scanner --offline` and
`betterleaks --validation=false` as it does anywhere else. Linux and macOS
runners are covered, x86_64 and arm64; before 0.39.0 a Linux arm64 runner was
not, since those versions install git-sizer, which publishes no build for it.

## Docker

The `Dockerfile` at the root installs gitmole from PyPI at a build argument's
version, the pinned tools with `--install-tools`, and git, with
`safe.directory` set so git reads a repository mounted from the host. No
image is published; build it in a clone of this repository:

```bash
docker build --build-arg GITMOLE_VERSION=0.38.0 -t gitmole .
docker run --rm -v "$PWD:/repo" gitmole .
docker run --rm -v "$PWD:/repo" gitmole . --fail-on critical --markdown /repo/gitmole.md
```

The image builds for linux/amd64 and linux/arm64, natively on Apple silicon;
an image of a release before 0.39.0 installs git-sizer, which has no Linux arm64
build, and needs `--platform linux/amd64`. The analysis goes to `/analysis-repo` inside the
container unless `--out` names a mounted path. Run with
`--user "$(id -u):$(id -g)"` to write exports as yourself; add
`--out /tmp/analysis`, since that user cannot write to `/`. The vulnerability
database lives in `/osv`; keep it in a volume and fetch it once:

```bash
docker run --rm -v gitmole-osv:/osv -v "$PWD:/repo" --entrypoint osv-scanner gitmole \
  scan source -r --offline-vulnerabilities --download-offline-databases .
docker run --rm -v gitmole-osv:/osv -v "$PWD:/repo" gitmole .
```

## SBOM

`gitmole . --sbom sbom.cdx.json` writes a CycloneDX 1.6 document of the
packages every lock file in the tree pins, as the osv-scanner step read
them: one component per ecosystem, name and version, with its package URL,
the lock files that pin it as properties, and its licence where
package-lock.json or composer.lock declares one. The metadata names the
repository, its commit and its declared licence. There is no dependency
graph, because not every lock file records one. The same commit gives the
same bytes: the timestamp is the last commit's day and the serial number
is derived from the commit and the components. The package list comes
from the osv-scanner step, which writes it with or without the local
vulnerability database: without one, it reads the lock files a second time
with the matcher switched off. When the step did not run, `--sbom` exits 2
and says so.

## Agent hooks

The same gate wired into a coding agent: after every file edit, the files
the edit touched are scored against the last gitmole run, and the agent
reads the summary back before it goes on. Deterministic findings before
inference, so the model reasons over a short list rather than rediscovering
what history already says. `gitmole OUT_DIR --no-run --hook` reads the
hook's JSON on stdin, takes the file paths the agents put there
(`tool_input.file_path`, `file_path`, `file_paths`, `tool_response.filePath`),
scores them like `--risk`, prints one line per file with what imports it and
the companions the edit left untouched, and exits 2 when the total is over `--risk-threshold`,
which every one of these hooks reads as "block"; without a threshold it is
a soft warning. When the output directory's scc, log or change analysis did
not complete, every file scores 0, so with a threshold the hook exits 4 and
says so instead of passing the edit: Claude Code shows that to you without
blocking the model, Cursor with `failClosed` and pre-commit block on it.

The hook scores against an earlier run, so set it up with one run first, in
the repository:

```bash
gitmole . --out analysis-repo
```

The hook itself then costs a few hundred milliseconds and needs no tool on
PATH. Before that run, or with a mistyped directory, the hook says
`gitmole hook: no analysis in analysis-repo, so nothing was scored; run once
in the repository: gitmole . --out analysis-repo` on stderr and exits 0: an
exit 2 there would block every edit over a missing file. The scores are the
analysed commit's, so when HEAD has moved on the hook also says how far,
on stderr and without changing the exit code (`the analysis in
analysis-repo is of 1a2b3c4d5e6f, 14 commits behind HEAD; its scores leave
those out; refresh it with: gitmole … --out analysis-repo`). There is no
threshold on that gap: any commit since is revisions the watch list has
not counted, so run the same command again when the number is more than
you want to ignore, after a merge from main at the latest.

Claude Code, `.claude/settings.json`, a `PostToolUse` hook on `Write|Edit`;
the JSON on stdout becomes `additionalContext`, exit 2 shows stderr to the
model:

```json
{"hooks": {"PostToolUse": [{"matcher": "Write|Edit",
  "hooks": [{"type": "command", "command": "gitmole analysis-repo --no-run --hook --risk-threshold 10"}]}]}}
```

Cursor, `.cursor/hooks.json`, `afterFileEdit` (add `"failClosed": true` to
block on a non-zero exit); Gemini CLI, `AfterTool` in its settings; both
pass the same shape of JSON on stdin and read the exit code:

```json
{"version": 1, "hooks": {"afterFileEdit": [{"command": "gitmole analysis-repo --no-run --hook --risk-threshold 10", "failClosed": true}]}}
```

pre-commit, from the `.pre-commit-hooks.yaml` in gitmole's repository:
`gitmole-risk` runs the whole analysis against `origin/main` at `pre-push`
(the external tools have to be on PATH, or installed once with `gitmole --install-tools`); `gitmole-hook` scores the staged
files against an earlier run at `pre-commit`, with the output directory as
its first argument:

```yaml
repos:
  - repo: https://github.com/antvinni/gitmole
    rev: vX.Y.Z   # the latest release tag; pre-commit autoupdate fills it in
    hooks:
      - id: gitmole-risk
        args: [--risk, origin/main, --risk-threshold, "10"]
      - id: gitmole-hook
        args: [analysis-repo, --no-run, --hook, --risk-threshold, "10", --]
```

Put the latest tag from [the releases page](https://github.com/antvinni/gitmole/releases)
in place of `vX.Y.Z`, or run `pre-commit autoupdate`, which sets it and moves it
forward later. Secrets are betterleaks' own pre-commit hook; gitmole does not repeat it.

## Big repositories

Blame is the cost that scales with repo size. gitmole keeps it in check:

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
- there is no duplicates step since 0.39.0 (jscpd was retired with the rule it
  fed; [tools.md](tools.md#retired)). Older scripts that pass `--duplicates`
  still parse; the flag does nothing;
- `--ignore-data` excludes data-like files (csv, json, lock files, minified
  and vendored assets) from blame and from the function metrics, and
  `--ignore GLOB` adds your own patterns, repeatable.
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
read as no data, the terminal header's third line (the fourth with `--full`
when there is coverage data; the Markdown header shows the coverage line
whenever there is coverage data, so there it is the fourth without `--full`
too) opens by naming the step (`size timed out`; `structure checks timed out`, `failed`
or `did not complete` for the step whose eight rules have no section of their
own), and `meta.json` records every step's outcome under `steps`. A structure
step skipped because gitmole runs on Python before 3.10 is said nowhere in
the report, default or `--full`, so one commit renders one report on every
interpreter; nor does the install say it, since the grammars' Python-version
markers simply leave them out. Only `meta.json` says so, under `structure`,
with the reason in `install`.

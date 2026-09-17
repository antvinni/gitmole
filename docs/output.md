# The report and the output files

How to read each part of the terminal report, and what each run writes to disk; back to [the README](https://github.com/antvinni/gitmole#readme).

## The terminal report

1. **Header**: commits, date span, identities, branch, size, top languages,
   one line for the busiest day and hour, the share of fix commits, the
   share that are reverts when there are any, and the year most surviving
   code was written (or why the blame pass did not run), and a one-line
   tally of the findings.
2. **Findings**: anything the heuristics flagged, worst first. Findings of
   the same kind are grouped into one entry with a list, and every finding
   ends with a next step that names the file, area or person to start with,
   on its own line under the facts. Currently: a dormant repository (no
   commits for twelve months or more, measured against the run's reference
   date, which also silences the untouched-files note),
   secrets in history (see below), an unconfigured git identity
   (example.com and the like; the advice offers the `.mailmap` line that
   would merge it into the busiest real identity), one author owning most
   surviving code, git-sizer concerns (a large blob that is no longer in
   the tree says so, since deleting it did not shrink the clone), one file dominating the churn, bug magnets (source
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

   One check is also reported when it passes: a green `No secrets in
   history` line closes the panel whenever the betterleaks scan ran and
   found no secret value, so a clean result is said out loud rather than
   left to silence. It is not counted as a finding. When the scan did not
   run, because the step was killed or `--no-run` points at an output
   directory without `secrets.json`, the line is absent. The Markdown
   export carries it as `**ok**`.

   Secrets are grouped by value, so one key copied into ten files is one
   entry with its places counted. A value found in any source file is
   critical. A value found only in test files, such as fixtures and saved
   web pages, only in example, sample, fixture, demo or rules directories
   (a language sample, a scanner's own rule definitions), only in vendored
   code (upstream's own specimens), or only in documentation (`.md`,
   `.rst`, `.txt`, `.adoc`, or anything under `docs/`), where it is
   usually a template, is a warning.
   Six shapes cannot be a live secret and are left out, counted on the
   footer line: version strings, tokens shortened with "...", whole-value
   template markers such as `your-project-id`, `<your-token>`, `XXXX-XXXX`
   or `changeme`, a whole value that is one of the words every example
   uses (`hello`, `secret`, `password`, `123456`), a whole value that
   refers to an environment variable or a template field (`@env:X`,
   `${X}`, `{{.Env.X}}`, `process.env.X`), and a `BEGIN ... KEY`
   block whose body holds no key material, like the dotted sample in
   Google's service-account docs. Every
   rule is about the whole value; nothing is skipped by prefix. To silence a
   false positive for good, copy its fingerprint from `secrets.json` into a
   `.betterleaksignore` at the repository root; betterleaks reads it on the
   next run, and an existing `.gitleaksignore` works too.

   The values themselves are never written. `secrets.json` holds a short
   keyed hash in place of each value, the matched text and the commit
   message; the key is random, made for that one report and never saved, so
   a stored hash cannot be checked against a list of common passwords. It
   only tells you which hits in one report share a value.

   A commit counts as a fix when its subject starts with `fix:`, `hotfix:` or
   `bugfix:` in the conventional style, or mentions fix, bug, hotfix,
   regression or crash. Test files are left out of every finding that names a
   file, area or function: they change with every fix, and owning the tests is
   not the knowledge risk. The default tables leave them out too; `--full`
   shows them.
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
   once, test file, not scored).

   Under the watch list, one line says how the list would have done:
   gitmole reruns the change analysis as of six months before the last
   commit, with scc on the tree at that time, ranks the watch list from
   that, and counts how many of the files fixed since were on it, next to
   what a random list of the same size, drawn from the files that had
   changed more than once, would score. Repositories with under a year
   of history say `too little history to backtest`.
4. **Tables**: people (identities merged on top of `.mailmap` when they
   share an email, two name words, the same name spelled identically
   unless it is a bare common first name, or a one-word handle that is a
   distinctive word of the fuller name; the caption says whose; bots and
   coding agents such as renovate, Copilot, Cursor Agent,
   dependabot and GitHub Actions are counted apart in the caption and kept
   out of the timeline), a knowledge map (lines added per area of the tree
   and who wrote them), a timeline of commits per author over the last
   twelve months, hotspots ranked by revisions times lines of code with the
   number of fix commits alongside, change coupling, the most complex
   functions, repo health. Change coupling hides pairs where either file is
   no longer in the tree, since they describe a layout that no longer
   exists, and shows a directory whose files all change together (generated
   tables, one file per version) as one row with the file count and the
   weakest degree; the caption counts both and `--full` shows every pair.
   Hotspots hide files no longer in the tree the same way. Hotspots carry a `trend` column, sampled for the
   top ten hotspots: the change in complexity over the last year from scc on
   the file at sampled commits (`--full` shows the whole series as a
   sparkline). The knowledge map marks owners who have stopped committing
   with `(gone)`, and under `--full` shows the share of each area's lines
   that they wrote. With `--full`: size by language, activity by weekday
   with the busiest hour and the share of commits that are fixes, and
   surviving code by year.

   Size, hotspots, coupling, ownership, code age and the watch list analyse
   source files: a built-in list of code extensions plus names like Makefile
   and Dockerfile (`--file-types all` counts everything). In the default
   report, the hotspots and complex functions tables hide test files and
   generated files (a file whose first lines say it was generated or must
   not be edited, or that `.gitattributes` marks `linguist-generated`;
   the run records them in `meta.json`), the complex functions table also
   hides vendored code (`vendor/`, `vendored/`, `node_modules/`,
   `third_party/`, `external/`, and a `packages/` inside a package such as
   `requests/packages/`), and the change coupling table hides pairs with a test
   file and pairs of release plumbing (two version files, a manifest and
   its lock file, changelogs); the captions show how many are hidden, and
   `--full` shows them. Release plumbing is also hidden from the hotspots
   table and left out of the watch list, the churn-dominance and the
   bug-magnet findings: a version file or a manifest changes on every
   release by design, not because the next bug lands there. Vendored and generated code is left out of the
   brain methods finding, vendored code out of the knowledge islands and
   bus factor findings too: somebody else's code, or a generator's, is not
   this repository's risk. A function lizard cannot name (a Go function
   literal) is called `(anonymous)` and the advice names its file and
   line. Activity and the timeline cover the whole history.
5. **Footer**: where the files and plots are.

The complete report for the gitmole repository itself is in
[example.md](https://github.com/antvinni/gitmole/blob/main/docs/example.md).

## The output directory

Lands in `analysis-<repo>/` next to a local clone, or in the current
directory for a remote target:

| File | From | What it is |
|---|---|---|
| `meta.json` | git | name, branch, commit count, date span, identities |
| `activity.json` | change analysis | commits by weekday, hour and month; net lines per year; fix-commit count; per-author totals and monthly timeline |
| `size.json` | scc | lines per language, COCOMO estimate |
| `repo-health.txt` | git-sizer | oversized objects, deep trees, other repo problems |
| `secrets.json` | betterleaks | secret-looking strings across all history: rule, file, commit, line and fingerprint, with each value replaced by a short keyed hash |
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
   lines. The change log follows renames, so a moved file is one entity
   under its new path and a pure move adds no lines: whoever moved a tree
   to `src/` did not write it, and the knowledge map says so. Large files that change constantly are your risk. By default the
   tables leave test files and deleted files out and say how many; `--full`
   shows them.
3. Change coupling shows files that always change together. That usually
   means a hidden dependency or copy-pasted layout. A whole directory that
   changes as one is a generator or a shared layout, and shows as one row.
4. People and the surviving-code table tell you whether knowledge is
   concentrated in one or two people; the knowledge map says where. Areas
   are top-level directories, or the subdirectories of a lone top-level one
   such as `src/`. A directory the history knows but the tree no longer has
   (the layout before a move to `src/` or `crates/`) is hidden from the map
   with a count, and left out of the islands, bus-factor and knowledge-loss
   findings; `--full` shows it.
5. Repo health and secrets are pass or fail checks. Read them only if they
   flag something.

# The report and the output files

How to read each part of the terminal report, and what each run writes to disk; back to [the README](https://github.com/antvinni/gitmole#readme).

New to the report? [Reading your first report](first-report.md) is the one-screen version: each section
in plain words, and what to do first. This page is the reference.

## How to read the output

1. Start with the header and the findings.
2. The watch list is the source files ranked by changes × lines of code (a change is one commit that touched the file; the JSON calls them `revs`), from
   `maat-revisions.csv` joined with scc's per-file size. The change log follows
   renames, so a moved file is one entity under its new path and a pure move
   adds no lines: whoever moved a tree to `src/` did not write it, and the
   knowledge map says so. Large files that change constantly are your risk; the
   columns beside each file (`fixes`, `top author`, `look at first`) do not move
   it, they say what to look at there, and the caption's `Check:` says how the
   same ranking would have done six months ago, or that nothing
   has been fixed since the cut-off. The hotspots table behind
   it, which `--full` and the Markdown export add, ranks every file by the same
   product and carries the trend column; the Markdown export caps it and leaves
   test files, deleted files, generated files and release plumbing out, saying
   how many, as `--full` does; `--section hotspots` lists them all. The default report's own tables,
   change coupling and complex functions, leave test files out the same way.
3. Change coupling shows files that always change together. That usually
   means a hidden dependency or copy-pasted layout. A whole directory that
   changes as one is a generator or a shared layout, and shows as one row.
4. The People table's surviving-code column and the bus-factor and knowledge
   findings tell you whether knowledge is concentrated in one or two people;
   the knowledge map says where. Areas are top-level directories, or the
   subdirectories of a lone top-level one such as `src/`. A directory the
   history knows but the tree no longer has (the layout before a move to `src/`
   or `crates/`) is hidden from the map with a count, and left out of the
   islands and bus-factor findings; `--section knowledge-map` shows it.
5. Secrets is a pass or fail check. Read it only if it flags something.
6. One table, whole: `--section NAME` prints a section on its own with every
   row, the ones the report hides too, each with its kind, and `--csv` writes
   the same rows as a CSV. `--full` is every section and every finding, not
   every row: its tables stop at 50
   ([One section, whole](https://github.com/antvinni/gitmole/blob/main/docs/cli.md#one-section-whole)).

## The terminal report

One layout for every part, and no box anywhere: a title line at column 1,
then what the part holds two columns in. A table is its column heads, a rule
exactly as wide as its columns, a row a line and its caption; the header,
the Supply chain section and Since last report are grids of labelled rows,
a value that does not fit wrapped under its own start; the Findings are
entries, each with its mark at column 1, its statement at column 3, its
subject lines at column 5 and its step under `↳`. One blank line between
two parts, none inside one, and no line ends in a space.

The colours are four styles and no more: bold (a part's name, a table's
first column, and in the header the commit count and a `--since` window or
`--path` scope), dim (labels, column heads, rules, captions, the closing
lines, the `(not measured yet)` tag), yellow for a warning and red for a
critical, on the finding's mark and title and on a scan's verdict in the
Supply chain section. A note has no colour, and neither has a statement, a step or a
number, so the report reads the same on a light theme as on a dark one.
(The logo banner keeps its own colours and is only drawn on a terminal.)
Without colour (`NO_COLOR`, a pipe, a file) the report is the same bytes
with the escapes left out.

Every mark has an ASCII form for a stream whose encoding cannot carry it
(`PYTHONIOENCODING=ascii`, a legacy code page), chosen per mark, so a
Latin-1 stream keeps its `·`: `✖` `x`, `▲` `!`, `●` `*`, `↳` `>`, the rule
`-`, a section's pictogram `#`, `·` `-`, `×` `x`, `…` `...`, `→` `->` and
`≥` `>=`. The report then has the same lines; a line that holds one of the
last three is a character or two longer, so a table row with an elided path
is that much out of its columns. Any other character the stream cannot
carry, in a name or a path, prints as `?`. Columns are counted as a
terminal counts cells; one that draws an East Asian ambiguous-width
character two cells wide will show its rows one cell out.

One format for numbers and one word per column, in the terminal and in
Markdown: a count of 1,000 or more has its thousands separator, in the
header, every table and every caption; zero prints as 0 (a month without a
commit in the Timeline too); a span is digits and its unit (`6 months`); a
threshold is `N or more` in a sentence and `≥N` only in a table cell; a
bare vulnerability score has `CVSS` before it. The column heads are
`changes` (commits that touched the file: `revs` in the JSON),
`complexity` (cyclomatic, the function's branch points plus 1, defined in
one line under Complex functions: `ccn` in the JSON; in Hotspots and Size by
language it is the line counter's sum for the file) and `together` (the
share of two files' changes made in one commit: `degree` in the JSON).
The JSON's keys are unchanged.

A table's title carries its count and what it is ranked by (`Complex
functions · 8 of 475, by complexity`; `all 8` when every row is shown), so no
caption ends `and 467 more`. A caption says what the table hides, as a sum
with its breakdown (`501 pairs hidden: 289 test, 192 historical, 10 vendored,
8 generated, 2 example`), and then defines the table's words as `term =
meaning`, the fragments joined by ` · `: two lines at most at 80 columns,
three under People and four under the Watch list with its `Check:`. A word is
defined once, under the first table that prints it (`gone = no commit in the
12 months to 2026-09-18`). How a table was made (the merge regime behind the
coupled pairs, an import left out of ownership, the merge total, whose aliases
were merged) is `--full`'s and Markdown's. No caption says where the hidden
rows are: the default report says it once, in its closing lines.

The sections come in one order in the default report, `--full` and Markdown,
code first and people after: Watch list, Complex functions, Change coupling,
Knowledge map, People, Supply chain. `--full`'s own sections sit in their
groups (the watch list by component and Hotspots after the Watch list, Size by
language after Change coupling, the Timeline after People, then Activity,
Surviving code by year, Changed lines and Trailers), and under `--full` the
Supply chain section opens a group of its own instead of closing the report:
Secrets by rule, Dependencies by lock file, Signing by year, Checks run, Agent
surface and the OSPS Baseline follow it.

`--full` is every section and every finding, not every row. Its header closes
with a `contents` row naming the sections in order. A table stops at 50 rows
(the Markdown export's cap, with or without `--full`), hides what the default
hides, so its first rows are the default's rows, and when the cap cut it the
title says so and names where the rest are: `People · 50 of 1,324 identities,
by commits · --section people`. A count that would sit under the last row is in
the caption instead: the spans lizard may have mis-parsed sort last, so
Complex functions says `? = a span lizard may have mis-parsed (6 of the
table's, listed last)`, and People says how its whole table is spread (`1,324
by commits: 2 with 1,000 or more · 18 with 100 to 999 · 98 with 10 to 99 · 448
with 2 to 9 · 718 with 1 · 37 credited only as co-author · 3 with merges
only`), the bands summing to the title's count. A bar is drawn in eighths of
a cell, scaled so the column's largest value fills eight cells; zero draws
nothing, and a table whose rows would draw fewer than three different bars
has no bar column. Where a table's text does not fit beside its numbers at 80
columns (the OSPS Baseline, Agent surface, Watch list by component, Checks
run, Dependencies by lock file) it is on lines under each row, whole, and in
columns of its own in Markdown and in a CSV. On prometheus `--full` is 964
lines at 80 columns; it was 4,359 while it printed every row. The width of the terminal changes how a cell is elided and how
prose wraps, and nothing else: no rows, no order, no month window (the
Timeline's twelve months need 70 columns), and no two tables side by side.
A cell is never wrapped onto a second line, and neither is a column head.
When a row does not fit, a path loses its middle directories first
(`prompb/…/client/decoder.go`), then the last text cell is cut with `…`; a
number and a head are never cut, and columns that still do not fit are left
out and named under the table. In a finding a path, a package and a version
are always whole: one longer than the line has a line to itself. The word `gone` has one form in every
table: after what it qualifies, one space, no brackets (`23% gone`, `Fabian
Reinartz gone`, `2019-01 gone`); blank means active.

1. **Header**: a title line, the repository with its branch and commit
   (`prometheus · branch measure @ 296080c0`), and labelled rows, each label
   describing everything on its row. `history`: commits, date span, the
   `--since` window, identities. `files`: the three counts with their three
   denominators, `1,676 tracked · 1,056 with code · 653 scored (source: not
   test, example, generated or vendored)`: git's tracked files, the ones the
   line counter found code in, and the source files every ranking is over.
   `code`: lines, top languages and the year most surviving code was written
   with the step that counted it (`23% surviving from 2026, by blame`; `by
   git-of-theseus` after a `--plots` run, whose sampling pass rewrites the same
   two files and gives slightly different shares; or why the blame pass did
   not run). `commits`: the share of fix commits and the reverts (git's
   `Revert "…"` subject or its `This reverts commit <sha>` body line) when
   there are any; the busiest weekday and hour are `--full`'s Activity table.
   `left out`: the sweeping commits and the ones `.git-blame-ignore-revs`
   declares, `18 sweeping commits, not counted in churn, coupling or
   ownership`, said here once for every table below. `scope` (a `--path` run) and `steps` (the ones that
   did not finish) are rows when there is something to say, and a row with
   nothing to say is not printed. The tally of the findings is the Findings
   title's: `Findings · 4 warnings ▲ · 10 notes ● · 5 by rules not measured
   for precision yet`, each word beside the mark
   its entries carry. Signing is a row of the Supply chain section, last
   in the report: the share of commits signed and by what (`51% of commits
   signed (gpg 49%, ssh 2%), 60% of the last year's (signatures not
   verified)`; the default report keeps the row to one line, the share and
   the last four words, and `--full` and a wide terminal say the rest). It
   is read from the `gpgsig` header in each commit object, so it needs no
   keyring and a fresh clone reads the same as the author's; nothing is
   verified, and the figure is evidence toward SLSA Source L2, never a
   level. A commit the forge committed itself, under a bare `noreply@`
   address such as GitHub's `noreply@github.com` (a merge from the web),
   carries the forge's signature and not its author's, so it is named
   apart: `12% of commits signed by their authors (gpg 12%), 0% of the
   last year's; 50% signed by the forge on merge`. `--full` and Markdown add a Signing by year table with humans
   against bots as two totals, and no rate per person (the JSON keeps `signing.by_identity`). `--full` and Markdown add a Trailers table: every hyphenated
   trailer key and how many commits carry it, counted without regard to
   case as git matches them (`Co-authored-by` and `Co-Authored-By` are one
   row, under the more common spelling), and never an issue reference
   such as `PAP-10182:` (capitals, a hyphen and a number) that happens to
   end a message; then the declared commits, those an `Assisted-by` trailer, a co-author
   who never authors a commit or a coding tool marks,
   against the rest (reverted, by git's `Revert "…"` subject or its
   `This reverts commit <sha>` body line; fixes; a file changed again within two
   weeks), with the share of the history they cover, and three neutral
   descriptors of how commits arrive (bursts of commits minutes apart,
   conventional-commit subjects, hours of the day). This
   repository against itself, with no prior from elsewhere, and nothing is
   labelled: every descriptor has an ordinary cause. The rest is every commit that declares
   nothing, which includes any agent use nobody disclosed; it is never a group of people. With `--full` the `files` row
   counts the tracked text files by why they are out of the scored
   pool, `4,512 tracked · 1,470 with code · 582 scored · 13 generated ·
   2,680 test files · 139 example code · 3 release files · 1,095 not a source
   type`, and Markdown always carries that count as a line of its own
   (`4,512 files: 582 scored · …`); a file of
   a type scc does not classify counts as `not counted by scc`.

   The default header says what it ranks when that is the smaller part. When
   the files no table carries (`not a source type`, `not counted by scc`)
   outnumber the scored ones, the `files` row gives the scored count as a
   ratio: `581 of 4,512 files scored`. When the files the type filter left out
   also hold more lines than the scored ones, the `code` row adds `69% of
   tracked lines are documentation, not ranked · --file-types all includes
   them` and the `commits` row `83% of commits and 72% of fixes change only
   unscored files`. The lines are
   scc's code lines, the unit of the header's own count; documentation is
   prose formats and anything under `docs/`; a tree where other types hold
   more reads `37% of tracked lines are in file types that are not ranked`.
   The last phrase labels the populations: `25% are fixes` is
   over every commit, the bug magnets and the watch list over scored files,
   and it says how many commits, and how many fix commits, changed files
   and none that is scored. A tree with more test files than source files
   gets none of this: tests are in the tables, hidden, and `--section NAME`
   shows them. The counts are under `coverage` in the JSON.
2. **Findings**: anything the heuristics flagged, worst first: critical,
   warning, note. "Note" is the word in the terminal, the Markdown export
   and these pages for the severity the JSON, the SARIF and `--fail-on`
   call `info`. Within a
   severity, a finding that rests on the name of a path alone (its `rule`
   says `"by": "file name"` or `"by": "path convention"`: a tracked `.env`,
   a personal settings file) comes after the ones a scan or a count stands
   behind; otherwise the rules keep one fixed order. Findings of
   the same kind are grouped into one entry with a list, and every finding
   ends with a next step that names the file, area or person to start with,
   on its own line under the facts. This page says what each rule names and
   what it leaves out, not when it fires: in the JSON, each finding's `rule`
   carries its id and the thresholds it fired on, and its `evidence` the
   numbers they were compared with.

   The default report prints each finding in a short form: the count and
   the rule's own numbers (`62 functions have 100 lines or more and
   complexity 15 or more`), the worst subject, and the step in three lines
   at most. `--full`, the Markdown export, the JSON and SARIF keep the
   whole statement with every subject it names; the short form is a second
   rendering of the same `rule` and `evidence`, and changes neither. `--full`
   (and `--section findings`) lays the statement out: the fact, then the
   subjects it names a line each, five at most with the rest counted, then
   what the statement says after its list, then the step.
   - A finding whose subjects are a table of the same report in the same
     order names the worst one and points there: Brain methods at Complex
     functions, Files that always change together at Change coupling
     (`(see Complex functions)`). The pointer is printed only when that
     table is in the report with the subject in it; otherwise the subject's
     numbers are said in the finding.
   - Any other finding has three subject lines at most, indented under its
     statement. A list that is cut says `and N more`, and is never cut
     between two subjects with the same count. Bug magnets counts its
     files on either side of its warning threshold, so the parts sum to the
     total: `7 at 5 or more: promql/engine.go 10, ... · 11 at 3 or 4`.
   - Vulnerable dependencies is the one exception to the three lines: its
     subjects are lock files, at most three of them in at most three lines
     each, and one line counting the rest (`and 25 more packages:
     dependencies.json`), ten lines in all whatever the repository holds.
     The lock files come path first and whole, in a fixed order: the one
     something declares as shipped (`go.mod, which Dockerfile and 88 more
     ship:`, the first such lock in the rule's order, with as many of its
     packages as the three lines hold and the rest counted as `and N more
     there`), then the one holding the highest score, then the one holding
     the package the step names. A lock file is one entry however many of
     the three it is. Every package named has one advisory id, its score
     when there is one, `fixed in` and the version or `no fix published`,
     and `imported by no tracked file` or `a dev dependency` when the scan
     says so; packages of one lock file that share all of those are named
     together and the facts said once (`for both, no fix published, ...`).
     A lock file whose score is in the critical band while the finding is
     a warning ends `not critical, as nothing beside it declares a
     deployment`. With one lock file the statement names it and the
     entry has no path in front.
   - The truck factor says what the number means (`9 people would have to
     leave before 333 of the 653 source files (51%) had no author left`),
     how many of them are already gone, and the areas where one person
     leaving would be enough; the names of a truck factor over three and
     the variant with knowledge halving are in `--full`.
   - A credential-shaped file is `matched by name`. When the secrets step
     ran to its end and holds no row for the path, at any commit, the
     finding adds `The secrets scan found no value in it, at HEAD or in
     history` and its step becomes conditional (`If it holds a login,
     ...`); when the step did not run, or has a row for the file, neither
     is said.
   - A Go pseudo-version is shortened by its shape to its base and its
     12-character commit (`0.307.4-0.…-1174b0ce4f1f`), installed and fixed
     alike; the 14-digit commit time between them is in `--full`.
   - The note for vulnerable packages only in test, example or vendored
     lock files is one sentence with no step.
   - A rule with no short form of its own prints its statement whole when
     that is three lines or fewer, else what comes before its list and
     three lines of the list.

   Every finding is an entry with a mark of its own, so the marks can be
   counted against the title's tally. A finding from a rule whose
   precision nobody has measured yet (the set is `UNJUDGED` in
   [gitmole/findings.py](https://github.com/antvinni/gitmole/blob/main/gitmole/findings.py))
   has the dim tag `(not measured yet)` after its title, in the default
   report and in `--full`, and the Findings title says once what the tag
   means and how many carry it: `· 5 by rules not measured for precision
   yet`, or in fewer words (`5 not measured for precision yet`, `5 not
   measured yet`) where the title would be longer than the line. A warning
   or a critical from such a rule is an entry like any other. A note from
   one is compact in the default report: the title, the tag, a colon and
   one statement, three lines at most and no step (`● Possibly
   unreferenced files (not measured yet): 3 files imported by nothing in
   the tree; first discovery/install/install.go`). The statement names
   the subject the rule's own advice picks, which need not be the first
   the long statement lists: the hotspot with the most TODO markers, the
   largest import group's shortest loop, the function in a top hotspot.
   A note that would name a pair the entry *Files that always change
   together* has just named says `the one above`. `--full` and Markdown
   spell these findings out with their steps; JSON (where they carry
   `"summary": true` and `"unjudged": true`), SARIF and `--fail-on` treat
   them like any other finding, and the `--fail-on` line on stderr says
   `not measured yet` when one of them tripped the gate. Until 0.44.0 the
   default report folded them into one closing line ("5 more from the
   structure step, not labelled yet"), which left the title counting a
   warning that no ▲ stood for. Until 0.39.0 a second line named the rules whose findings were
   labelled true but never as something to act on ([measurement.md](measurement.md),
   "Hand labels"); those nine rules were retired instead: duplicated blocks,
   git-sizer's repository health, reverts, stale files, components that
   change together, secrets only in test and other set-aside files, many
   minor contributors, files whose authors have left, and knowledge loss.

   The history and size rules:

   - a dormant repository, measured against the run's reference date;
   - secrets in history (see below);
   - credential-shaped files tracked (a warning): a tracked `.env` or
     `.env.*` that is not a template, `.netrc`, `_netrc`, `.pypirc`,
     `.dockercfg`, a private key named `id_rsa`, `id_dsa`, `id_ecdsa` or
     `id_ed25519`, and anything under a `.ssh/` directory; the name alone is
     the finding, whatever the contents, and test and example paths are not
     counted; the advice is to move the values to the environment, `git rm`
     the files and add them to `.gitignore`;
   - an unconfigured git identity (example.com and the like) that made a
     share of the commits; the advice offers the `.mailmap` line that would
     merge it into the busiest real identity;
   - one author owning most surviving code;
   - bug magnets: source files still in the tree that were fixed again and
     again in recent months; a file whose recent fixes were all commits that
     also fixed a file listed above it is counted with that file ("fixed in
     the same commits"), and a file that first appeared inside the six months
     says it is new in the window, when the history reaches back past them.
     A busy file in a repository that fixes a lot is fixed a lot, so the
     finding names first the files fixed more often than the repository's
     own fixes per change explain, and says how many there are, or "none":
     a one-sided binomial test per file over the whole history, with a
     Benjamini-Hochberg false discovery rate of 5% over every source file.
     Fixes cluster within a pull request, which makes the test err towards
     finding, so it orders and annotates, and which files are magnets is
     the six months' counts. It decides one thing: when it ran and put no
     file above the rate ("no file more often than is usual for its size", an empty
     `evidence.fix_rate.above_rate`), the finding is a note, not a warning,
     since its own sentence says nothing here is unusual, and
     `--fail-on warning` does not stop on it. With a file above the rate
     the severity is the six months' counts. With less
     than twelve months of history the test does not run (it would test
     the window's own counts again); the finding says so, and is a note
     whatever the counts, since raw fix counts mostly follow file size.
     A translation file named for its locale is not a magnet: a fix that
     adds a message adds it to every locale. The name needs a letter region
     (`ru-RU.ts`, `zh-Hant-TW.json`, `pt_BR.po`) anywhere, or, directly in
     a `locale/`, `locales/`, `i18n/` or `po/` directory (or in gettext's
     `<lang>/LC_MESSAGES/` below one), a numeric region or none
     (`es-419.json`, `de.json`, `po/fr.po`). A lower-case region
     (`en-us.ts`) and a file named for its domain in a directory named for
     its locale (`fr/LC_MESSAGES/django.po`) are not known. A translation
     file still counts in the test's rate for files of its size;
   - brain methods: functions both complex and long, a warning when one
     sits in a hotspot;
   - hotspots getting more complex, a warning when the top one did; each
     file's summed complexity (scc's count, which grows with the lines)
     stands beside the change in its code, and the advice to split goes to
     the first one whose complexity per line also rose 25% or more in the
     year, or says they grew with their size;
   - tightly coupled file pairs; a file and its test are expected to change
     together, so those pairs are left out;
   - vulnerable dependencies (see below);
   - knowledge islands: areas written almost entirely by one person, a
     warning when such areas hold most of the code.

   Repository hygiene is read from the clone alone, the checks OpenSSF
   Scorecard and the OSPS Baseline otherwise make through the GitHub API,
   each rule naming the Scorecard check it stands in for: workflow steps,
   and the steps of a composite action (an `action.yml` whose `runs:` uses
   `composite`), that use an action by tag or branch rather than a full commit SHA (a
   warning, whose advice names another account's action before one from
   the account the `origin` remote says the repository lives under, and
   either before GitHub's own `actions/`; within each, a branch-shaped ref
   such as `@main` before a release-shaped one (`@v7`, `@1.2.3`), then a
   step handed a secret (`secrets.` in its `with:` or `env:`, or the
   `env:` it inherits; `secrets.GITHUB_TOKEN` is the job's own token, like
   `github.token`, and counts only by what it may do) or a token that can write (`id-token: write`,
   `contents: write` or `write-all` in its job's `permissions:`, else the
   workflow's) before one that is not, each row in `hygiene.json` saying
   which as `ref`, `secrets` and `grants`; the evidence names each action
   once per file, up to 50); a manifest whose last commit is newer than its lock file's, by
   commit time (a warning), and a manifest of an ecosystem that locks by
   convention with no lock file in its directory or above it (a note),
   unless it declares nothing a lock would pin: a `go.mod` with no
   `require`, a `package.json` with no dependency of any kind and no
   `workspaces`, a `Cargo.toml` with no entry in a dependency table and no
   `[workspace]`, a `composer.json` requiring only the platform (`php`,
   `ext-*`), a `Pipfile` with empty package tables (`lockfiles.nothing_to_lock`
   in `hygiene.json` names them; a `Gemfile` is Ruby and is not read); the
   ecosystems with a tracked lock file that `dependabot.yml` does not cover,
   and `github-actions` when it leaves that out while a workflow or composite
   action uses another repository's action, pinned or not,
   or no update tool at all (Renovate covers every manager by itself); no
   licence file, no `SECURITY.md` (at the root, in `.github/` or `docs/`,
   or a heading about security in the README or CONTRIBUTING, such as
   "Reporting security issues", that points to one elsewhere), and `CODEOWNERS` lines that match no
   tracked file; a scoped npm package resolved from another host than the
   one `.npmrc` declares for its scope (a warning), lock files that mix
   registries, and a pip `extra-index-url`; packages that run install
   scripts, lifecycle scripts in the repository's own `package.json`, and
   process or network calls in `setup.py`; executables by their magic bytes
   (ELF, PE, Mach-O; an ELF relocatable object, which nothing runs, is not
   one) outside test and example paths (a warning), and blobs
   `.gitattributes` sends to LFS that were committed as they are;
   submodule URLs with credentials (critical; the credential is redacted),
   over plain `http://` or `git://` (a warning), relative, or following a
   branch; symlinks that resolve outside the tree or into `.git/`; and
   Trojan Source, bidirectional control characters in source files
   (CVE-2021-42574, critical) and identifiers that mix Latin with
   Cyrillic, Greek, Armenian or Cherokee letters that pass for Latin ones
   (a Cyrillic `о` in `process`; a warning; `μs` is not one, since `μ`
   reads as itself). Generated files are left out. `hygiene.json` holds
   every check's raw result.

   What the project declares about its dependencies and licence is read
   as declared, never detected. Declared dependencies nothing imports: a
   `package.json` runtime dependency no tracked file imports (a stylesheet's
   `@import`, `@use`, `@forward` or Tailwind's `@plugin` counts, `~` prefix
   and all), names in a quoted string of a configuration file, runs from the
   manifest's scripts, or that the lock file resolved as the peer of another
   package the manifest declares (a `pnpm-lock.yaml` version's peer suffix,
   the `peerDependencies` a `package-lock.json` or Yarn 2+ lock records); a `go.mod` direct requirement no import path or `go:generate`
   line falls under; a Cargo.toml dependency no `name::` path, `use` or
   `extern crate` names (a note). Python and Ruby are left out because a
   distribution's import name need not be its own, and gitmole keeps no
   table of names. The project's licence as declared: a root manifest
   (package.json, pyproject.toml, Cargo.toml, composer.json, a gemspec,
   setup.cfg) that names a different licence from the licence file's text
   (a note), or a declared licence known not to be OSI- or FSF-approved (a
   warning). Copyleft dependencies in a permissive project: runtime
   packages whose licence, as package-lock.json or composer.lock records
   it, is strong copyleft (GPL, AGPL, SSPL, EUPL, OSL) while the project's
   own is permissive (a warning); weak copyleft (LGPL, MPL, EPL) is counted
   in the finding, not flagged. SPDX expressions are evaluated with `OR`
   as the user's choice and `AND` as every term; a GPL with a linking
   exception counts as weak. Other lock files record no licence and are
   not read for one.

   Rules that give evidence for an OSPS Baseline control carry its id in
   `rule.osps`, and SARIF tags the rule with it. The OSPS Baseline section
   (`--full`, Markdown and `osps` in the JSON) lists the controls a
   clone can show: secrets in version control, the licence file and its
   licence, sign-off on every commit, a contribution guide (a
   `CONTRIBUTING` file, or a heading about contributing in the README or
   the docs' index; a pull request template is recorded in
   `presence.pull_request_template` and named beside a gap, and is not a
   guide), security
   contacts, a dependency list, executables and binaries in version
   control, and known-vulnerable dependencies. Each gets a result here:
   met, gap, not seen (sign-off on too few commits, where a contributor
   agreement outside git would not show), unrecognised (a licence gitmole
   does not know), not applicable, or not checked when the step that reads
   it did not run. It is evidence for a control, not an audit of it;
   access control and most of vulnerability management live in the
   forge's settings and are not in the table.

   The structure step runs by default (Python 3.10 or newer; see
   [install.md](https://github.com/antvinni/gitmole/blob/main/docs/install.md#structure-nesting-debt-markers-the-import-graph)):
   tree-sitter parses every tracked file in eleven languages, once per
   file content, and its findings are these:

   - debt the authors flagged in hotspots: TODO, FIXME, XXX and HACK
     comments, the markers Maldonado and Shihab defined, in the top
     hotspots;
   - deeply nested code: functions nested deep, or with several separate
     chunks of nested logic (CodeScene's bumpy road), with Sonar's
     cognitive complexity beside them; a warning when one sits in a top
     hotspot;
   - coupling with no import behind it: a pair that changes together often
     although neither file imports the other, which Ajienka and Capiluppi
     found is common and usually a shared format, a duplicated rule or
     copied code; only for languages whose imports the graph mostly
     resolves, and not for two Go files in one directory, which are one
     package and share every name with no import;
   - import cycles: groups of Python, JavaScript and TypeScript source files
     that import each other, directly or round a loop, as they load, each
     named by its shortest loop (`a.py → b.py → a.py`; of equal loops, the
     one through the file that sorts first); the three largest groups are
     named and the rest counted (`(2 more groups)`). A loop's files must be
     in a language whose imports mostly resolve to a file, and a group is
     named only when one of its languages also has enough files in the
     repository (the same gate as possibly unreferenced files and the
     dependents count on `--risk`), so two `.tsx` components in a loop with
     TypeScript count where three lone TypeScript files do not; tests,
     examples and fixtures, vendored code and generated files are left out,
     and so is Go, whose compiler refuses a loop between packages, so a
     loop through Go files could only be the graph's mistake. An import inside a function (not one called where it is written) or an
     instance field's initialiser, TypeScript's and Flow's `import type`
     and an import whose every name is marked `type` (erased by
     TypeScript's default; a project built with `verbatimModuleSyntax` keeps
     it as `import {}`, which loads the module, so a loop through one can be
     missed there), a dynamic `import()`, and an import under
     `if TYPE_CHECKING:`, `elif TYPE_CHECKING:`, `if False:` or after
     `if not TYPE_CHECKING:` do not run at load and are left out, since
     they are how a loop is broken on purpose. Oyetoyan et al. found classes
     near a cycle change more often and found no rule that tells a harmful
     cycle from a harmless one, so the finding names the loops and says
     nothing about which to keep;
   - possibly unreferenced files: Python, JavaScript, TypeScript and Go
     files nothing imports that are no entry point by convention (such as
     `__main__.py`, `index.*`, `main.*`, `*.config.*`, a dotfile, a file
     beside `package.json` or `go.mod`, `bin/`, `scripts/`, `migrations/`,
     file-routed `pages/` and `app/`), by declaration (`pyproject.toml`
     scripts, `package.json` main, bin and exports, a wildcard export
     expanded, a path into a build output such as `dist/x.js` read as its
     source `src/x.ts`), by being named by path in another tracked file (a
     package script, a shell script, a CI step, `new URL('./x.mjs',
     import.meta.url)`; relative to that file, its package or the root, or
     as the one tracked path the name ends with; documentation does not
     count) or by content (a
     `__main__` guard, a shebang, Go's `package main`); a basename that
     recurs across directories, and a directory the code itself barely
     imports, are loaded by name and left
     out, and a language where too many files still look unreferenced loads
     code by name and gets no list at all. Never "dead": a dynamic import
     does not show in an import graph;
   - errors caught and dropped: catch, except and rescue blocks with no
     statement and no comment, a warning when one sits in a top hotspot; a
     comment keeps a block out, since it says the error is ignored on
     purpose, and in Python only a bare `except:` or one catching Exception
     or BaseException counts, since `except KeyError: pass` is the
     language's idiom;
   - addresses written into the code: IPv4 addresses in string literals,
     loopback, `0.0.0.0`, broadcast and netmask shapes, the RFC 5737
     documentation ranges, a trailing `.0` (a network, or a four-part
     version) and a first octet of 0 to 2 (how an ASN.1 object identifier
     starts) left out, and literals inside attributes and annotations too;
   - code left in comments, counted per block (a block comment, or line
     comments on consecutive lines) when most of its lines read as a
     statement and one starts right at the comment marker; prose with a
     worked example under it, documentation comments and tool directives
     are not counted.

   The last three are shape rules, in the source files only (tests,
   examples, documentation, vendored and generated files left out), run on
   the same tree-sitter pass rather than a second parser.
   Flow-typed JavaScript parses with errors, and its metrics come from the
   partial tree. The watch list gains three reasons from the same step:
   `5 TODO/FIXME comments`, `parse() nested 6 deep`, and `defines 72
   functions and classes` for a file that defines a great many.

   Changed lines (`--full` and Markdown, `provenance.lines` in the JSON):
   the lines added to code files in the last year and the year before, the
   share git's own moved-code detection marks as moved (`--color-moved`,
   blocks of twenty characters or more), and the share deleted again within
   two weeks from the same file with the same text, GitClear's moved and
   churned lines as a direction for this repository. Blank lines and lines
   without three letters or digits are not matched, since any brace would
   pair with any other. When commits carry an `Assisted-by` trailer or a
   co-author who never authors, the same two numbers for them against the
   rest, and the trailers section adds each side's watch-list hit rate: the
   share of its commits that touched a file on the watch list's top fifteen.

   What the history declares about how commits were made is read, never
   inferred. Agent configuration is a surface like `package.json`: a
   committed setting that turns approval prompts off
   (`permissions.defaultMode` set to `bypassPermissions`) and a tracked
   `.claude/settings.local.json`, which is meant for one machine, are
   warnings; an MCP server declaration (`.mcp.json`, `.cursor/mcp.json`,
   `.vscode/mcp.json`) whose environment holds a literal value rather than
   a `${VAR}` reference is a warning that names the key and never the
   value; an instruction file (`AGENTS.md`, `CLAUDE.md`, `GEMINI.md`,
   `.github/copilot-instructions.md`) far behind the last commit, in time
   and in commits, is a note. The inventory in `provenance.json` also lists
   the subagents and skills the tools load for a task (`.claude/agents/`,
   `.claude/skills/*/SKILL.md`, `.codex/agents/`, `.agents/skills/*/SKILL.md`),
   which the note leaves out, and none of these files under a template,
   fixture, example or test directory, where they are a product's data or a
   test's input. Three more parts of that surface are told by shape and only
   listed, never a finding: the hook commands any tracked JSON declares (an
   object with a `command` below a `hooks` key), each with its event, the
   tracked script the command names once a `${VAR}/` or `./` prefix is
   stripped (the command's own first word, or a file git records
   executable or that opens with `#!`; any other tracked file it names is
   recorded as `names`, not as something that runs), and the tracked file
   that script hands over to with `exec` (one hop; YAML is not read); the manifests in a root dot-directory whose
   name ends `-plugin`; and every `skills/<name>/SKILL.md` whose frontmatter
   has a `name:` and a `description:`. `--full` and Markdown print them as
   the Agent surface section, when there is anything to list
   (`provenance.agents` in the JSON: `hooks`, `plugin_manifests`,
   `skills`). A `Signed-off-by` from an identity that
   co-authors commits but never authors one is a note: the Linux kernel's
   policy forbids an agent to add the Developer Certificate of Origin.

   Knowledge is also measured by degree of authorship (Avelino et al.): per
   file and person, a bonus for creating it (the first commit that added
   lines to it; a pure move creates nothing), their own changes, and a
   logarithmic dilution by everyone else's, so changes count, not lines,
   and a reformat transfers nothing. A person is an author of a file when
   their degree is close to the file's highest. The truck factor is how
   many authors have to leave before most of the source files have none; a
   low one is a finding, and an area whose own truck factor is one is
   named, with `new since <month>` beside its author when its first commit is
   inside the `--gone` window before the last commit, none of its files
   arrived by a rename (a directory that moved is not new; git's `-M` is read
   one hop, and a move below its similarity reads as files added), and the
   history reaches back before the window (in a younger repository every
   area is as new as the rest). One
   author is what a new area has, so the advice never starts in one. It is
   computed a second time with knowledge decaying over time
   (JetBrains' Bus Factor Explorer). It does not name who holds the largest
   share of the surviving code: that is the bus factor's measure, and the
   name changed with the step that counted the lines.

   Two scans are also reported when they pass, so a clean result is said
   out loud rather than left to silence: the Supply chain section's
   `secrets` row opens `none found: betterleaks scanned every commit HEAD
   reaches` whenever the betterleaks scan ran and found no secret value,
   and its `dependencies` row says `none vulnerable` whenever osv-scanner
   checked the lock files and found nothing. Neither is counted as a
   finding. When a scan did not run, because the step was killed or
   `--no-run` points at an output directory without its file, the row says
   `not scanned` where the verdict would be. The Markdown export has the
   same section under the same title, a row an item; the portfolio export,
   which has no such section, says each pass as an `Ok:` line under a
   repository's findings. Until 0.44.0 the terminal report had them as two
   green ✔ lines closing the Findings.

   Vulnerable dependencies come from osv-scanner over the lock files,
   offline against the local copy of the OSV database (see
   [install.md](https://github.com/antvinni/gitmole/blob/main/docs/install.md#the-vulnerability-database)
   for the one-time download). One row per package with an advisory: the
   CVE or advisory id, the worst CVSS score, and the version that fixes it.
   A package pinned by a lock file in the source tree is a warning. It is
   critical when it is a `MAL-` record (OpenSSF's malicious-packages list
   ships in the same database; those records carry no score, and a
   malicious package is critical whatever its score), or when an advisory
   scores in CVSS's critical band and the lock file's directory declares
   that it ships: a lock pins what is installed where it is used, and a
   library's lock pins only its own developers' environment, since whoever
   installs the published package resolves its dependencies again. What
   counts as declaring it, in the lock's directory or in a workspace member
   the lock pins (uv's `[tool.uv.workspace]`, Cargo's `[workspace]`,
   `workspaces` in package.json, `pnpm-workspace.yaml`): a `Dockerfile`
   (`Dockerfile.*`, `*.Dockerfile`, `Containerfile`), a Helm `Chart.yaml`,
   a `Procfile`, `fly.toml`, `vercel.json`, `netlify.toml`, `wrangler.toml`
   or `serverless.yml`; a compose service whose `build` context is that
   directory; an entry point (`[project.scripts]`, `[project.gui-scripts]`
   or `[tool.poetry.scripts]` in pyproject.toml, `bin` in a package.json
   that does not declare `"private": true`, `[[bin]]` in Cargo.toml); and for Cargo and Go the ecosystem's program
   layout (`src/main.rs` or `src/bin/`, `main.go` or `cmd/`). A lock
   nothing declares, a published library's or a development or integration
   workspace's, stays a warning at any score, and the finding says which
   lock's critical score it held back. Each package row in the evidence
   names what declared its lock (`deploys`). The rows are named critical
   ones first (a malicious package leading), then by reach: a version the
   lock installs for running that the source imports, then one it installs
   for running (or whose lock does not say), then one only development
   dependencies reach (`runtime`: false, from a `pnpm-lock.yaml` importer's
   dependencies walked through its snapshots, or a `package-lock.json`
   `dev` mark; said as "development dependencies only"). The pnpm walk
   starts from the root importer and every member except one that declares
   `"private": true` that nothing deploys (no tracked deploy file in its
   directory, no compose service built from it), and follows a `link:` into
   any member; a row it reaches names the direct dependency its shortest
   path starts from (`via`, said as "reached through @grpc/grpc-js" when
   that is another package). Then those with a fixed version before those
   without, then by score, so the advice starts where a fix exists. The
   reach orders the rows and never changes the grade.
   A package pinned only by a lock file under tests,
   examples, docs or vendored code is a note. osv-scanner also reads pip's requirement
   files (`requirements*.txt`, `constraints*.txt`, `*.in` by those names),
   and for a range such as `mcp>=1.0.0` it reports the floor, 1.0.0, which
   no install picks on purpose; the scan keeps each such row's specifier,
   and a row whose specifier does not name one version (`==`) is said as a
   range whose floor is vulnerable, never counted as an installed package,
   and never critical by its score. Requirement files are counted apart
   from lock files, here and in the Supply chain section. The advice names the package to upgrade
   first, or, for a malicious one, to remove: a malicious package, then one
   that makes the finding critical, then the highest score that has a fixed
   version published ("it scores CVSS 9.2, the highest with a fix published";
   a bare score in a finding always carries the word CVSS),
   which need not be the first package the sentence lists, since those are
   in order of reach. An advisory that does not
   apply to your code is silenced in `osv-scanner.toml` at the repository
   root. Each row says whether any tracked source imports the package
   (`imported`: true, false, or unknown where the import name need not be
   the package's, as in Python and Ruby; where the lock records the
   versions the workspaces depend on directly, an import of the name is
   not an import of another version a tool brings along); the finding names a package
   nothing imports, and never lowers its severity for it, since an
   unimported package is still installed. This is not reachability, which
   needs a buildable tree. A package whose every advisory is informational
   (RustSec's `unmaintained`, `unsound` and `notice`, which report no
   vulnerability) is not counted as vulnerable; the Supply chain section's
   `dependencies` row names it. That row says how many packages in how
   many lock files were checked and how old the database copy is; without
   lock files, or without the database, it says that instead.

   Secrets are grouped by value, so one key copied into ten files is one
   entry with its places counted. A value found in any source file is
   critical. A value found only in test files, such as fixtures and saved
   web pages, only in example, sample, fixture, demo, tutorial, exercise, rules or stubs
   directories and `.stub` files (a language sample, a scanner's own rule
   definitions, a template a generator fills in), only in vendored
   code (upstream's own specimens), or only in documentation (`.md`,
   `.rst`, `.txt`, `.adoc`, anything under `docs/` or a CamelCase
   `ProjectDocs/`, and type stubs, `.pyi`
   and `.d.ts`, which declare shapes and hold no runtime values), where it
   is usually a template, is no finding (it was a warning until 0.39.0, and
   labelled never actionable); nor is a value found only in generated
   files, mocks (`mock/`, `mocks/`, `mock_*`, `*_mock.*`), tooling under
   `hack/`, `fixtures-*` directories or `testdata.*` files. Such values
   still count in the Supply chain section's `secrets` row and stay in
   `secrets.json`, so the row opens `none in source files`, not `none
   found`, while any is there, and the OSPS-BR-07.01 row counts them
   beside its result.
   A copy in an unreachable blob has no path, so the value's other copies
   decide; a value found only in unreachable blobs counts as source.
   betterleaks grades each sighting low, medium or high. A value that only
   the scanner's `generic-*` rules found, and that was graded low
   everywhere, is a possible secret: a note, since an ordinary
   assignment or a hash reads the same way. A `generic-*` value that is
   one word in one case (`PGPASSWORD: postgres`) is graded low whatever
   its context, since that is a service default or a sample. A provider's
   rule (an AWS key id, a Slack token) stays critical at any grade.

   Shapes that cannot be a live secret are left out, counted on the
   `secrets` row in `--full` and in Markdown: version strings, tokens shortened with "...", a dotted
   path of lowercase words such as `passwords.password` (a translation or
   config key), whole-value
   template markers such as `your-project-id`, `<your-token>`, `XXXX-XXXX`
   or `changeme`, a template field anywhere inside the value (`{token}`,
   `${X}`, `%(name)s`, `<user>`), a run of words that reads as prose, a whole
   value that is one of the words every example
   uses (`hello`, `secret`, `password`, `123456`), a run up the alphabet
   and the digits (`qr6stu789vwxyz`, `abcd1234`), a whole value that
   refers to an environment variable or a template field (`@env:X`,
   `${X}`, `{{.Env.X}}`, `process.env.X`), a bare `BEGIN ... KEY` header
   with nothing after it (a pattern a script greps for), a `BEGIN ... KEY`
   block whose body holds no key material, like the dotted sample in
   Google's service-account docs, and a value whose line, or the two lines
   above it, calls it an example, sample, dummy, fake or placeholder or
   fills in a template field (the lines are read from the clone at scan
   time, one `git show` per finding, and never written). So are
   a value the line shows outside any string literal, right after `=`,
   `(` or `,`, in a language whose literals must be quoted (a register
   assignment `PSW = EIPSW;` in a SLEIGH processor file, `id ==
   idaapi.PLFM_386`), where the quotes before it are counted so a
   credential inside a URL literal stays a finding, and shell and
   configuration files, where `PASSWORD=x` is a literal, are not judged
   this way; a masked value such as `elastic:XXXXXX`; a value that names a
   file, such as an icon; a name that holds the keyword itself joined by
   letters or underscores and written in one case (`resetpassword`,
   `password_missing`, `CURLOPT_PASSWD`; a mixed-case `MyCompanySecret`
   reads as a chosen password and stays a finding); a GUID
   in a table of GUIDs, like a list of interface ids; and a key header
   that closes its own string literal, which is code writing a PEM file.
   Every
   rule is about the whole value; nothing is skipped by prefix. To silence a
   false positive for good, copy its fingerprint from `secrets.json` into a
   `.betterleaksignore` at the repository root; betterleaks reads it on the
   next run, and an existing `.gitleaksignore` works too.

   betterleaks walks the history the refs reach; it does not see a commit
   only the reflog remembers, a dropped stash or a blob added and never
   committed. The secrets step also takes every object in the repository
   less those a ref reaches, writes the blobs among them (up to a cap on
   count and size) under the output directory for one `betterleaks dir`
   pass, removes them again, and reports what it finds as `(unreachable
   blob <hash>)`; the `secrets` row in `--full` and in Markdown says how many it scanned, or that there were
   none, which is what a fresh clone looks like, since a clone fetches only
   what a ref reaches. What each clone happens to hold is its own, not the
   commit's, so the counts sit in the `--json` export's `envelope` and a
   secret found in one of those objects is a finding another clone of the
   same commit will not have. betterleaks' live validation of a found credential
   is network, so gitmole passes `--validation=false` rather than rely on
   the default.

   The values themselves are never written. `secrets.json` holds a short
   keyed hash in place of each value, the matched text and the commit
   message; the key is random, made for that one report and never saved, so
   a stored hash cannot be checked against a list of common passwords. It
   only tells you which hits in one report share a value.

   A commit counts as a fix when its subject starts with `fix:`, `hotfix:` or
   `bugfix:` in the conventional style, or mentions fix, bug, hotfix,
   regression or crash; a fix that changes more lines than almost every
   other commit in the repository is tangled by size and credits
   none of its files, in the fix counts, the bug-magnet finding and the
   backtest alike, and `activity.json` counts them. A commit is tangled
   when it touches many files across several directories under
   a subject that lists several changes: parts between semicolons, commas,
   ampersands and pluses, and a part after "and" only when it is two words
   or more, so "a new agent on macOS and Linux" is one change. Test files are left out of every finding that names a
   file, area or function: they change with every fix, and owning the tests is
   not the knowledge risk. The tables leave them out too, under `--full` as
   well; `--section NAME` shows them, marked `test`.

   The change log is read with whitespace ignored (`git log -w
   --ignore-blank-lines`), so a hunk that only re-indents counts no lines
   and a file a formatter only re-indented is not a revision. A commit that
   touches more files than almost every other commit and takes out about
   as many lines as it puts in is a sweeping commit: a formatter run, a
   rename across the tree, a copyright-year bump. It would count as a
   revision of every file it touches and couple them all to each other, so
   it is left out of the revisions, coupling, authors, ownership, fix and
   age counts, along with every commit the repository declares
   uninteresting in `.git-blame-ignore-revs` (and the file
   `blame.ignoreRevsFile` names); the activity totals keep them,
   `activity.json` lists them, the header's `left out` row counts them, and
   the finding names the undeclared ones with the advice to declare them,
   so that git blame and GitHub skip them too. An import is left out the
   same way: a commit that adds to a great many files, deletes almost
   nothing, and holds a large share of every line the history ever adds,
   such as a project published with its past squashed into one first
   commit. Whoever committed it did not write what it holds, so it gives
   nobody ownership, authorship or the degree-of-authorship bonus for
   creating a file, and the code-age pass credits its surviving lines to
   nobody (they still count for their year). A note names it with its
   share, since the knowledge tables then read differently from a plain
   git blame. The rule counts code files, so the note labels them and
   gives the commit's own totals beside them (`313 code files of 722;
   40,853 lines of code of 83,997`), the vendored directory everything it
   added sits under when there is one (`node_modules/`, `vendor/`,
   `third_party/`), and the binary files it carried. An import nothing of
   which is tracked any more, because the log shows every file it brought
   in deleted since, changes no table about the tree: it is no finding,
   and one line under the knowledge map says which commit removed most
   of it; `activity.imports` in the JSON keeps the row (`in_tree`,
   `removed_in`). What an import brought in is read from the log, as the
   paths it added to that no earlier commit touched. A commit's `Co-authored-by` trailers (git's own trailer,
   which GitHub adds to a squash merge and pair programmers add by hand)
   name people who count as its authors too: in the People table,
   credited with the commits they are named on, through `.mailmap` and the
   same identity merge and bot rules; in the authors and ownership tables,
   where a commit's lines are shared equally between everyone it credits;
   and in the code-age pass, where a blamed line is shared the same way,
   so a squash-merged repository does not attribute every line to whoever
   pressed the button. A coding tool is not one of those people. Two or
   more differently named identities on one bare no-reply address
   (`noreply@`, `no-reply@`, `donotreply@`), as an assistant that signs each
   model version with its own name and the vendor's one address, are taken
   for a coding tool by that shape alone, and so is an identity whose only
   addresses are bare no-reply mailboxes and that is credited by trailers
   for at least nine of every ten of its commits (it authors at most one in
   ten: an assistant is named by the person who commits). A per-account
   `id+login@users.noreply…` address, one name alone on a no-reply address
   that authors its own commits, and a name that a person carries who
   authored commits under an address of their own are people. Its lines are kept out of ownership, the knowledge map's
   owners, the per-file author and minor-contributor counts, the degree of
   authorship the truck factor reads, the bus factor, the knowledge islands
   and the People rows, and a person's degree of authorship no longer
   counts its changes as someone else's. The knowledge map shows the tools'
   part of each area in an `agents` column when a shown area has a whole
   percent of it (the default report: where they hold as much as the
   second owner), and the People caption says how many names were left out,
   how many spellings that is with their aliases, the no-reply addresses
   they share and their commits, as the subtraction from the header's count of
   identities to the title's (`1,324 = 1,327 identities less 3 coding-tool
   names (7 with aliases, sharing 1 no-reply address, 32 commits)`), the same
   words in the default report, `--full` and Markdown. No rendering of the People
   table has an email column, at any width; the addresses stay in the
   JSON export's `meta.identities`.
   Someone credited only by trailers, who never commits, is a person and
   counts as one.
3. **Since last report**: with `--compare BEFORE.json`, what changed
   against an earlier `--json` export of the same clone, as a grid of
   labelled rows on a terminal (the change, then what changed, wrapped
   under its own start) and a two-column table in Markdown. Findings are
   matched by their rule id, and for a rule that emits one finding per row
   by the rule id with the mailbox (unconfigured identity), or the metric
   for an export from before 0.39.0 that still has git-sizer's repo health; each one is listed as new, resolved or
   persisting, and a persisting finding whose severity moved says
   `warning → note`. A persisting finding whose counts moved says which,
   from the numbers in its evidence (`values 16 → 1`, `files 3,217 →
   3,400`), so a finding that shrank or grew is not read as unchanged; the
   JSON keeps them as `changed`. Then the files that entered and the files that left
   the top fifteen of the watch list. The caption says what the comparison
   is against, `against 540ee5b5, 2026-09-10` from the before export's
   commit and last commit date or `against an export without a run
   manifest`, and the tally before and after; when nothing changed, the
   section says so and keeps those lines in the note. When `--since`,
   `--file-types`, `--ignore` or `--ignore-data` differ between the two
   runs, the caption's first line lists them, since the changes then partly
   reflect the options; when the two runs scanned against different
   snapshots of the OSV database, it says so, since a new advisory moves the
   vulnerable-dependency finding with no change to the code. Markdown
   carries the section and the JSON carries it under `compare`. The comparison never changes the exit code: `--fail-on`
   reads this run alone.
4. **Watch list**: the five source files most likely to need a fix next, one
   line each with its numbers in columns: `changes` (the commits that touched
   it), `fixes` (in the six months to the last commit, the window the caption
   states: a file fixed 31 times long ago shows 0), `top author` (the largest
   share of the lines added to the file that one person holds, with `gone`
   after it when that person has no commit in the `--gone` window; the share
   and no name, since `gone` beside a 10% share is not a file left without
   an author) and `look at first` (the function nested deepest when that is
   five levels or more, else the most complex one at complexity 10 or more;
   the column is left out when no row shown has either). The title counts the
   rows against the list's fifteen (`5 of 15`) and names the ranking.
   Every source file still in the tree that changed
   more than once is ranked by changes × lines of code, over source
   files only: measured against the fixes that followed at six cut-offs
   on three repositories
   ([validation.md](https://github.com/antvinni/gitmole/blob/main/docs/validation.md)),
   it named more of them than any weighting of fixes, complexity and
   ownership did. A file's score, which `--risk` adds up, is its share, in
   percent, of all scored files' changes × lines of code. The reasons, which
   the JSON carries as `watch[].reasons`, `--hook` joins into its context and
   `--risk` prints beside each file,
   name the fix count (the last six months' when there are any), the sole
   owner, the minor contributors (people with a small share of the file's
   commits each), the most complex function lizard found (a nameless one
   by its line; a span marked `?` in the complex functions table is passed
   over) and, when its summed complexity grew in a year, by how much and
   how much its code grew beside it (the trend is
   sampled for the top hotspots only, so a file further down the list may
   have none), the files it always changes with, and how many files it
   changes with when it is weakly coupled to many (Tornhill's sum of
   coupling), how many of its changes were made between midnight and 4 am
   in the author's own time zone (Eyolfson et al.; a tie-breaker, never a
   rank), how many different months it changed in (Hassan's change
   entropy: scattered changes, which lost to the ranking on the backtest
   and so stay a reason), and how rarely a test file moved with it (`no
   test changed in its 38 changes`, `a test changed in 4 of its 28
   changes`; a repository with no test file anywhere says nothing), none of
   them entering the rank. When each reason appears is set in
   [gitmole/watch.py](https://github.com/antvinni/gitmole/blob/main/gitmole/watch.py).
   Test files are left out, and so
   are vendored code and example code (the `examples/`, `samples/`,
   `fixtures/`, `testdata/`, `demos/`, `tutorials/`, `exercises/` (and
   `ExerciseFiles/`), `rules/` and `stubs/` directories and `.stub` files;
   a course's exercise binaries are teaching material), which the complex functions table hides for the same
   reason: somebody else's code, or a specimen, is not this repository's
   risk. Generated files, amalgamations and release plumbing leave the pool
   too, for their own reasons rather than that one. Under `--since`, churn
   and ownership are windowed and the list says so.
   `--full` and the exports show fifteen. `--full` and Markdown add a Watch
   list by component: each component's share of the list's revisions ×
   lines of code and its own top three files, since one busy subtree
   otherwise takes the whole list; the JSON carries it as
   `watch_by_component`. The default report prints no reasons in
   words. `--full` prints the ones the columns do not hold on one indented line
   under each row, Markdown in a last column (`also`), and the JSON carries
   them all.
   With `--risk BASE`, a
   Change risk section follows: every file changed since BASE with its watch
   score as a bar and, on the lines under its row, the reasons whole (a last
   column, `why`, in Markdown), or why it has none: the first reason that
   applies of `generated`, `vendored`, `test file`, `example code`,
   `release file`, `amalgamation`, `not a source type` and `not in the
   tree`, the last covering a file the change deleted and, under `--no-run`,
   one added after the run; otherwise `changed once`, or `no revisions on
   record`. The caption adds Kamei's factors for the change (files,
   directories, subsystems and commits; whether it is a fix by its
   subjects; lines added against the lines the files had; how evenly it
   spreads; files changed this month; prior changes and people; the
   author's prior commits, here and in these subsystems) and the companions the change left
   untouched (`not touched: core/ast.py, which moved in 72% of
   core/parser.py's changes`); the JSON carries them under `change_risk.change` and
   `change_risk.coupling_gaps`, and each scored file's rank, fix counts,
   owner, share and minor contributors. Each file's why also says what
   imports it (`imported by 4 files, 31 counting what imports them`) where the
   import graph resolves well enough to count; `dependents` in the JSON. `--hook` is the same scoring for a
   coding agent's hook, see
   [cli.md](https://github.com/antvinni/gitmole/blob/main/docs/cli.md#agent-hooks).

   Under the watch list, the caption's `Check:` says how the ranking would
   have done: gitmole reruns the change analysis as of six months before the
   last commit, with scc on the tree at that time, ranks the watch list from
   that, and counts how many of the files fixed since its top fifteen held,
   out of the fixed files that had changed more than once by then (the pool
   the list draws from): `6 months ago the top 15 of this ranking held 13 of
   the 91 files fixed since. The 15 most-changed files also held 13; 15
   random files would hold 2.9.` The second sentence is the comparison: what
   the same number of most-changed files held, and what a random pick of that
   size would. When the result is one a random pick could have given, by the
   one-sided hypergeometric test (Fisher's exact test) at p < 0.05, the
   sentence ends `and 3 is not distinguishable from that (p = 0.19)`.
   `--full` and Markdown add what the count is over (`Counted over the 464
   files that had changed more than once by then; 24 more files fixed since
   had not; p < 0.001.`); the pool, its fixed files, the list's length and
   its hits are all in the JSON's `watch_backtest`. Repositories with under a
   year of history say `Check: none, too little history to backtest`.

   When documentation is more than half the tree's lines and none of it is
   ranked, a short list follows the watch list: **Most-changed documents**,
   the five most-revised documents with their revision counts (fifteen
   with `--full` and in the JSON's `coverage.documents`). It is a count
   from the log the run already has, taken the way a source file's
   revisions are (in the window, without the sweeping and import commits),
   over the documents that are out of the pool for their type alone. It is
   by revisions alone: not a score, not a finding, and no claim that a fix
   is likelier there.

   A measure the run could not make says so in one dim line that closes the
   findings: `truck factor not computed: 17 source files, needs 20`, or
   that more than half the source files have no author on record. Without
   it a missing truck factor reads as nobody being a risk. The backtest's
   reason stays under the watch list, and the bug magnets' size test inside
   that finding; all of them are listed under `not_computed` in the JSON.

   That line is one cut-off on one repository. How the list does over six
   cut-offs on curl, django and react, next to lists ranked by churn alone,
   by size alone and by the factor product the list used to rank by, is in
   [validation.md](https://github.com/antvinni/gitmole/blob/main/docs/validation.md).
   "Fixed" means a commit whose subject says so, which is a proxy for a bug.
5. **Tables**: people (identities merged on top of `.mailmap` when they
   share an email, two name words, the same name spelled identically
   unless it is one word that two people's full names in the history hold
   or that is written as a given name (Jack, George), a one-word handle
   that is a distinctive word of the fuller name, the fuller name run together
   (RobinMalfait), or an initial plus the surname (nlohmann); the title counts them (`242 with aliases merged`) and `--full` says whose; merges
   counted in a column of their own and left out of the commit count and
   share, since merging every pull request is not writing the code; a row's
   merges and its surviving code are its own, by the name and address git
   shows, so two rows that share a display name do not each take the
   name's whole count; bots,
   which are any author named `*[bot]`, any identity that merges with
   one (`github-actions` beside `github-actions[bot]` is one account),
   and any author whose name says bot, CI, deploy or automation, no
   product names, are counted in the caption (`4 bots left out:
   dependabot[bot] 882, 3 more`) and kept out of the
   timeline; their lines are left out of ownership and surviving code
   too, so a deploy job that commits a built site owns nothing; the caption
   defines `share` (of commits, without merges) and `surviving` with the step
   that counted it, `surviving = blame share at HEAD` or git-of-theseus's; `last commit` is
   the month each person was last seen, with `gone` after it past the `--gone` window, so the table that
   opens on someone who left in 2019 says so), a knowledge map (lines added per area of the tree over its history, headed
   `added` since it is not the area's size at HEAD, and who wrote them, each owner's share in the column beside the name),
   change coupling, the most complex functions, repo
   health. The Timeline, commits per author per month, is `--full`'s and Markdown's: no rule reads it. It is
   the twelve months to the last commit at every width (fewer only when the history or the `--since` window is shorter),
   ranked on the total of those months; a name too long for the room they leave is cut, never the months. The month of
   the last commit is marked `*` when that commit is before the month's end, and the caption says the rows are
   identities as merged, so one person under two names the run did not join has two rows. Hotspots, ranked by revisions times lines of
   code with the number of fix commits alongside, rank the same files the
   watch list leads with, and so appear under `--full` and in the Markdown
   export, next to size by language, activity and surviving code by year.
   Change coupling counts logical changes rather than commits: commits
   whose subjects share a ticket-shaped key (GitHub's `(#1234)` squash
   suffix, a Jira-shaped `PROJ-42` opening the subject, `Fixes #77`) are one
   change wherever they landed, and the rest group by author and calendar
   day, code-maat's temporal period, so a rebase-merged pull request is one
   change again and a change spread over a ticket's commits counts once;
   the cap on files per change applies after grouping, and the sum of
   coupling and the test co-change counts use the same changes. Under `--full`
   and in Markdown the caption
   says how changes reach the branch when that changes what a pair means:
   almost no merge commits and most subjects ending `(#NNNN)` is a
   squash-merged repository, whose pairs describe pull requests rather than
   edits; many of the commits being merges means the pairs
   describe the commits on the branches, since a merge exports no file list.
   Change coupling hides pairs where either file is
   no longer in the tree, since they describe a layout that no longer
   exists, and shows a directory whose files all change together (generated
   tables, one file per version) as one row with the file count and the
   weakest share; the caption gives the hidden pairs as a sum with its
   breakdown and says what a directory row is (`a directory row = its files
   change with each other (15 pairs)`), and `--section change-coupling` shows every pair. The two
   files of a pair are one cell, the directories they share said once and the
   rest of each in braces, the form a shell expands:
   `web/ui/mantine-ui/src/promql/{format.tsx,serialize.ts}`, or
   `web/{api/v1/api.go,web.go}` for two that part further up. In two columns
   both paths lost their middle at 80 columns; in one, the rows print whole.
   The column `together` is the share of the two files' changes made in one
   commit (`degree` in the JSON); `--full` adds `avg changes`, the mean of
   their change counts (`average-revs`).
   Hotspots hide files no longer in the tree the same way, under `--full` too, and count them in the caption
   (`7,666 files hidden: 6,836 deleted, 821 test, 9 generated`): a file that is gone has no lines,
   complexity or score to show. `--section hotspots` lists every one, after the rows the table shows, marked `removed`. Hotspots carry a `trend` column, sampled for the
   top hotspots: the change in complexity over the last year from scc on
   the file at sampled commits, `-` when no sample is a year old (`--full`
   shows the whole series as a sparkline), and under `--full` a `minors` column (contributors with a
   small share of the file's commits) and a `co-changes` column (the files
   it often changes with). The knowledge map marks owners who have stopped committing
   with `gone` after the name, and under `--full` shows the share of each area's lines
   that they wrote and how many of its authors committed to it in the
   `--gone` window (`recent`, a count with no names). With `--full`: size by language, activity by weekday
   with the busiest hour (the share of commits that are fixes is the header's, and is not said again there), and
   surviving code by year. After the Supply chain section `--full` adds three tables no report had. **Secrets by
   rule**: the scanner's rule, the confidence it gave, the places at HEAD, the places only history holds and the
   first file, never a value or the line it matched. **Dependencies by lock file**: every vulnerable package with
   the lock file that pins it, in the order the findings rank them (a lock that ships, reach, a fix, then the
   score), its version, one advisory id, its fix and its reach under the row, and a package scoring CVSS 9.0 or
   more listed whatever the cap. **Checks run**: a row for each hygiene family (the update tool, the licence and
   the declared files among them), the two scans, the sweep of unreachable objects, the share of imports the
   structure step resolved to a tracked file per language, and every step a run can take, each with what it had
   to look at under it and its result: `clean`, `nothing to check`, `did not run`, `finding` for a check the
   Findings spell out, `no hit` for a family the step records no count for, and `ran` for a step that only
   measures. No seconds, so the same commit gives the same table. An OSPS Baseline gap that rests on a file's
   name and on nothing a scan found says so after its evidence (`matched by file name alone`). The Trailers
   section's comparison of the declared commits with the rest is a second table under the first, a row a
   measure, and the caption keeps the definition of `declared`.

   Size, hotspots, coupling, ownership, code age and the watch list analyse
   source files: a built-in list of code extensions plus names like Makefile
   and Dockerfile (`--file-types all` counts everything), and every file
   that is source by its shape rather than its name: a tracked file with
   the executable bit (mode 100755 in the commit's tree) whose first line
   is `#!interpreter`, such as `hooks/session-start`, `bin/tool` or a
   `scripts/` file with no extension. The interpreter's name gives the
   language (`sh`, `bash`, `python3`, `node`, `ruby`, `perl` and the like;
   `env` hands over to the command it runs), so `--file-types py` keeps an
   executable `#!/usr/bin/env python3` and not a shell hook; an
   interpreter gitmole does not know is still a script, sized when scc has
   a language for it. Mode and first line are read from the analysed
   commit, never from the checkout, and the run lists what it found under
   `scripts` in `meta.json`. A path is judged as it is at that commit: one
   that is such a script at HEAD is source for its whole history under
   that path, and a path no longer in the tree, whose mode at each old
   commit would cost a tree read per commit, keeps the extension rule (the
   backtest reads its cut-off's own tree, so a script deleted since counts
   there). A rename is followed as for any file: the commit that renames
   `session-start.sh` to `session-start` and everything after it are the
   new path's revisions, and what came before stays with the old name. In the default
   report, the complex functions table hides test files and generated
   files (a file whose first five lines say it was generated or must not be
   edited, or, below a licence header and within forty lines, carries a
   comment that says so of this file: `@generated`, an upper-case `DO NOT
   EDIT`, "this file is generated", or a tool's banner such as Bison's "A
   Bison parser, made by GNU Bison 3.7.4" (a script's heredoc is text it
   writes, and ends the search); that `.gitattributes` marks `linguist-generated`, which git
   resolves as it does for itself, nested `.gitattributes` included, or
   that is a bundle, a minified file, a source map or anything under
   `dist/` by name, the run records them in `meta.json`; and an amalgamation, a
   file every one of whose functions also appears identically in other
   files, found from the function metrics); the hotspots table, drawn
   under `--full` and in the Markdown export, hides the same test files
   and generated files in both; `--section hotspots` shows
   everything. The complex functions table also hides vendored code
   (`vendor/`, `vendored/`, `node_modules/`,
   `third_party/`, `external/`, `deps/`, `.yarn/`, a `packages/` inside a
   top-level directory such as `requests/packages/` unless a `package.json`,
   `pnpm-workspace.yaml` or `lerna.json` declares it a workspace (react's
   `compiler/packages/`), any directory whose own `LICENSE` or
   `COPYING` names none of the copyright holders the root licence names,
   any directory where two or more source files, and at least half of
   them, open with a copyright notice naming somebody else: nobody the root
   licence names, no holder a tenth of the tree's source files name, and
   no author of the history by full name (a compression library copied in
   with its per-file headers). A notice line has a year or opens
   "Copyright (c)", so licence prose that mentions "the copyright owner"
   and a template's "Copyright [yyyy]" name nobody, and a root licence
   that names nobody leaves nothing to compare a nested one with,
   or that `.gitattributes` marks `linguist-vendored`, which the run records
   in `meta.json`) and example code (the directories the watch list leaves
   out), and the change coupling table hides pairs
   with a test file, pairs of release plumbing (two version files, a
   manifest and its lock file, changelogs), header pairs (a C-family
   source file and its own header), locale pairs (two translation files
   named for their locales, as the bug magnets know them) and pairs with a
   vendored file on either side; the captions show how many are hidden, and
   `--section change-coupling` shows them, each with the class it is hidden under. Release plumbing is also hidden from the hotspots
   table and left out of the watch list, the churn-dominance and the
   bug-magnet findings: a version file or a manifest changes on every
   release by design, not because anything is wrong with it. Plumbing is
   known by name (`version.py`, `package.json`, lock files, changelogs)
   and by behaviour: `maat-plumbing.csv` lists files with twenty commits
   or more where at least four in five swapped no more than three lines
   for as many, a version constant in `__init__.py` or the three fields
   of a version struct being the usual case. Vendored and generated code is left out of the
   brain methods finding, vendored code out of the knowledge islands and
   bus factor findings too: somebody else's code, or a generator's, is not
   this repository's risk. A function lizard cannot name (a callback, a
   Go function literal) goes by the text of the line it starts on, such
   as `app.post("/api/actions/:id/assign", async (req, res) => {`, and
   its row and the advice name its file and line, since the label is
   not a name to search for. lizard's JavaScript and TypeScript reader
   sometimes loses its place in a template literal or JSX and folds
   the functions that follow into one span; a `?` after the complexity
   marks a span that looks like that (a line inside it opens a block
   no deeper than the function's own start, fewer than a quarter of
   forty or more lines are code, or it has no name and nothing near its
   start line opens a function, as with a JSX ternary read as one), the
   caption says how many, and such spans are left out of the brain
   methods finding. Where the structure step parsed the file cleanly and
   ends the same function less than half as far on, the row's lines are
   the structure step's (a 36-line function no longer reads as 339); the
   complexity is still lizard's, counted over what it swallowed, and the
   `?` stays; `lizard_overrun` in the JSON keeps lizard's own end and
   lines. Activity and the
   timeline cover the whole history.
   The default report collapses what says little, by counts and never by
   a repository's size. A People row needs five commits, the floor the coupling table
   already uses for "enough commits to say anything"; the rest are counted
   in the title (`People · 3 of 8 identities`), and the top three rows stay whatever they hold. The
   change coupling table is left out when it would be one pair that the
   finding *Files that always change together* already names with its share
   and nothing but test pairs was hidden. The complex functions table is one line (`no long,
   complex functions; highest complexity 16 (handleRequest); --full lists
   5 at 10 or more`) when no function meets the brain-methods rule itself,
   complexity 15 or more over 100 lines or more, and the whole list fits
   the table's eight rows; a longer list stays a table. `--full` and the
   Markdown export keep every one of these tables, up to their 50 rows.
6. **Supply chain**, last: a titled grid of labelled rows, what the scans
   and the tree's own declarations say in one place. No row carries a
   status mark; the first words of a scan's row are its verdict, in the
   colour of the worst finding behind it and in none when no finding is.
   - `secrets`: the verdict and its rule first. `none found: betterleaks
     scanned every commit HEAD reaches` when the scan held no value;
     `none in source files (secrets.json)` when every value it held is in
     a file that is no source, which is the rule that makes a value a
     finding; `2 values in the findings above, 3 more never in source`
     otherwise. Then the places, HEAD apart from history: `at HEAD 18
     places, all in test or example files, none high confidence ·
     history only 1,170 places, 1,156 high confidence, those all in
     example files`. A place is one value at one commit, file and line,
     placeholder-shaped hits left out. Where the places are is counted
     from the file classifier every table uses (generated, vendored,
     test, example), so the clause reads `12 of them in test files` when
     that is the count, and never names a kind of file the classifier
     does not.
   - `dependencies`: what was scanned and the date of the database copy,
     then the totals, reconciled with the findings above: `29 vulnerable
     in 46 places: 28 in the warning above, 3 in the note, 2 counted in
     both (dependencies.json)`. The two dependency findings each count a
     package once, so one pinned by a source lock and by an example's
     lock is in both; with one finding the row says `all in the warning
     above`. A package with only an informational advisory is named
     after the totals. `no lock files found`, or `not scanned` with the
     reason, stands alone.
   - `signing`: see the header's entry above.
   - `checked, ok`: the hygiene checks that ran with something to check
     and found nothing, from a fixed list in a fixed order: workflow
     actions pinned, what the update tool covers, manifests level with
     their lock files, files free of bidi and mixed-script characters,
     then binaries with none executable, the licence, the declared files
     (CODEOWNERS, security policy, pull-request template), workflows
     free of pull-request checkout and script injection, submodule URLs,
     symlinks, and declared dependencies all imported. A check with a hit
     is a finding above and never here; one with nothing to check (no
     workflow, no lock file) is absent, as is the whole row when the
     hygiene step did not run. The registry-confusion and install-script
     checks record no count of what they looked at and are in
     `hygiene.json` only.

   The default report holds the grid to ten lines: three each for
   `secrets`, `dependencies` and `checked, ok` and one for `signing`. A row
   that would pass its lines says less, in a fixed order (the secrets row
   drops where the places are, then the places; the dependencies row
   drops the split between the findings; `checked, ok` stops at the last
   check that fits and ends `more in hygiene.json`). `--full` prints every
   row whole and adds what the default leaves to it: the number of
   distinct values, the placeholder-shaped hits left out, and the sweep of
   unreachable objects.

7. **Closing lines.** The default report ends with at most six lines and
   the path:
   - one sentence naming what `--full` adds, and where every row of a
     table is: `--full adds 14 sections: Watch list by component, Hotspots,
     ..., OSPS Baseline (2 gaps, 1 not seen, of 10). --section NAME prints
     one whole.` The list is generated from the sections only `--full`
     prints that have rows for this report (no Agent surface without agent
     files), and the OSPS result is its only number. It keeps to four
     lines: a title is held on one line while that fits, then titles break
     like any words, and past that the last titles are counted (`3 more`);
     the closing words are never cut;
   - the steps line: `15 of 18 steps ran; --plots runs the other 3 (code
     survival, 2 plots).` The total is every step a run can take; each one
     that did not run is named with the flag that runs it (`--plots`,
     `--deep` for a blame pass projected past its budget) or with what
     became of it (`functions not run`, `trend timed out`). Plots are
     named here only when they were drawn (`2 plots drawn (code-age.png,
     survival.png)`);
   - `gitmole DIR --no-run --full re-renders this run, DIR being the path
     below.`;
   - the output directory's path, alone on the last line.

   `--full` closes with the steps line, a Run line (what produced the
   report: gitmole's version, every tool's and the `--ignore`,
   `--ignore-data` and `--deep` options, read from the run manifest
   `meta.run`), an index of the output directory (`Output directory:
   activity.json, backtest/, ..., log.txt*, ... (* = no section renders
   it).`: every name it holds, with a mark on the ones no section of the
   report reads, such as the log, the tree listing and `packages.json`,
   which `--sbom` reads), a line naming `--sarif PATH`, `--sbom PATH` and
   `--json PATH`, `A table stops at 50 rows; --section NAME prints one
   whole.`, and `Full results in …` (`Full results and plots in …`
   only when the directory holds a plot). The header shows the manifest's
   commit as `branch main @ 540ee5b5`.

   **The Markdown export** (`--markdown PATH`) is the same report for a
   reader who is not on the machine that made it: a pull-request comment,
   a job summary. It opens with the tally (`**4 warnings, 10 notes** · 5 by
   rules not measured for precision yet`), then one line saying which of
   the two exports this is and how to get the other or one table whole
   (`The default report: every finding, a table up to 50 rows ·
   --markdown --full adds Secrets by rule, Dependencies by lock file and
   Checks run · --section NAME --markdown prints one table whole`), then
   the header's facts. Its headings are the terminal's section titles and
   nothing else, the same words at either tier and each once, so a link to
   `#hotspots` holds whichever export it points into; what qualifies a
   title (`50 of 475, by complexity`) is the line under it, with the command
   that prints the rest of a table the cap cut (`--section
   complex-functions --markdown`). A finding is a list item: the severity
   word and the title in bold, `(not measured yet)` for a rule nobody has
   measured, and the rule's id as code; then the statement, the subjects
   it names as a nested list, every one the statement lists and a last
   item counting the rest, what it says after them, and each `Next step:`
   on a line of its own. A caption is a paragraph a line. The Supply chain
   section is a list, a row an item, placed where `--full` has it: before
   the first section of its group. Without `--full` the export carries the
   sections it always carried, not the three `--full` gained; with
   `--full`, all of them under the same 50-row cap.

   No text is lost to the renderer. What a reader would paste is a code
   span and everything else has `\`, `` ` ``, `*`, `_`, `<` and `>` escaped
   (and `|` in a table), so a nameless function prints as `<anonymous>`
   where GitHub used to read an HTML tag and print nothing. A table says
   which of its columns hold code (paths, functions, packages, versions,
   advisory and control ids, secret rules) and those cells are spans
   whole. In a finding, the subjects are the ones its own `evidence`
   names: its paths, its packages, a version after its package's name,
   after `fixed in` or after `to`, a function before its file, a commit
   hash. Everywhere else (captions, the header, a prose cell such as the
   watch list's `eval() nesting 6`, and a subject a statement names past
   the ten its evidence holds) a word is a span when it has the shape of
   one: a path that ends in a slash or whose last part has a dot, a file
   name with an extension, a dot file, a call, a flag, an abbreviated
   commit hash. A package or a version has no shape of its own (`2.9` is
   a version and a mean), so outside a finding's evidence and a table's
   column it is left as prose, escaped.

   The export names no path outside the repository. It closes with the
   steps line, the Run line and `gitmole DIR --no-run --markdown -` (`…
   --full` in the full export) `writes this report again, DIR being the
   run's output directory`; a file it points at (`secrets.json`,
   `dependencies.json`, `hygiene.json`, a plot) is named as it is in that
   directory. Until 0.44.0 its last line was `Full results in` and the
   absolute path on the machine that ran it. On prometheus the two exports
   are 41 KB and 53 KB (40,774 and 52,490 characters), both under GitHub's
   65,536-character limit for a comment; `--markdown --full` was 285 KB
   while it printed every row.

A full example, at a pinned commit, is
[docs/examples/react.md](https://github.com/antvinni/gitmole/blob/main/docs/examples/react.md).

## The output directory

Lands in `analysis-<repo>/` next to a local clone, or in the current
directory for a remote target:

| File | From | What it is |
|---|---|---|
| `meta.json` | git | name, branch, commit count, merge-commit count, date span and identities of the checked-out branch's history; every step's outcome under `steps`, its wall time under `step_seconds` and the peak memory of its largest process under `step_peak_mb` (the `--json` export moves these two into its `envelope`, since they vary between runs); what produced the run under `run` (the commit, gitmole's version, every tool's version under `tools`, the versions gitmole pins under `tools_pinned` and any tool that is not at its pinned one under `tools_moved`, and the options); the classifier's `coverage`, `credential_files`, `generated` and `vendored` lists, and `scripts`, the executables with an interpreter line that are source by shape, each with the file type its interpreter gives it (absent when there are none) |
| `gitmole-feedback.json` | you | written only when you answer the five questions (`--feedback`): each answer's rule id, severity, whether it was true and whether you would act on it, plus gitmole's version and three bands (main language, file count, commit count). Nothing else, and nothing is sent |
| `activity.json` | change analysis | commits by weekday, hour and month; net lines per year; fix-commit count; per-author totals and monthly timeline; the sweeping commits left out of the tables, each marked whether `.git-blame-ignore-revs` declares it, the import commits left out with the history's total lines added, and how many declared commits the log holds; the oversized fixes left out of the fix counts, the tangled commits with a sample, and how many subjects end in a squash-merge suffix |
| `size.json` | scc | lines per language, COCOMO estimate |
| `secrets.json` | betterleaks | secret-looking strings across HEAD's history: rule, file, commit, line and fingerprint, with each value replaced by a short keyed hash |
| `dependencies.json` | osv-scanner | the lock files with their package counts, one row per package with a known vulnerability (ids, CVE aliases, score, fixed version, whether an advisory is a `MAL-` record, for a row from a pip requirement file its specifier and whether that pins one version, and for an npm row whether the lock installs it for running (`runtime`) and, from a pnpm lock, the direct dependency it is reached through (`via`)); on each lock file, the workspace members it pins and the entry points declared there, and the directories compose files build from, the database date and a digest of that snapshot; or a status: no lock files, no local database |
| `packages.json` | osv-scanner, with or without its database | every package the lock files pin, once per ecosystem, name and version, with the lock files that pin it and the licence a lock file declares; read by `--sbom`, not part of the report |
| `reverts.txt` | git | the commits whose message carries git revert's body line `This reverts commit <sha>`, each hash with its message body: the change analysis and the cohort count them as reverts whatever their subject says |
| `log.txt` | git | the numstat log export the change analysis reads, whitespace ignored, with each commit's `Co-authored-by` trailers behind its subject |
| `maat-revisions.csv` | change analysis | change frequency per file |
| `maat-coupling.csv` | change analysis | files that change together, over logical changes (a ticket's commits, or one author's day) |
| `maat-soc.csv` | change analysis | sum of coupling per file: its co-changes with any other file, and how many files it often changes with, over logical changes |
| `maat-tests.csv` | change analysis | per production file, how many logical changes touched it and how many of those also touched a test file |
| `maat-doa.csv` | change analysis | degree of authorship per file and person: created it, own changes, others' changes, the degree undecayed and decayed, whether each counts as an author, and the decayed own and others' changes, from which the report recounts the degree without the coding tools |
| `maat-latenight.csv` | change analysis | per file, its revisions and how many were committed between midnight and 4 am in the author's own time zone |
| `maat-components.csv` | change analysis | coupling between components at one and two directory levels, over logical changes: shared changes, degree, average revisions; read by nothing since the component-coupling rule was retired at 0.39.0 |
| `maat-entropy.csv` | change analysis | Hassan's change entropy per file: the months it changed in, and its decayed history complexity (its share of each month's changes times that month's entropy over files, halved per month back) |
| `maat-authors.csv` | change analysis | authors per file (co-authors included), and how many of them are minor contributors |
| `maat-age.csv` | change analysis | months since last change per file |
| `maat-entity-ownership.csv` | change analysis | lines added and deleted per author per file, a commit's lines shared between its author and co-authors, the commits crediting each of them that touched the file, and how many of those fall in the `--gone` window before the last commit (`recent`, blank when none; meta's `ownership_recent` says the count was made) |
| `maat-arrivals.csv` | change analysis | per file, the date of the first commit holding it under its current path and whether a commit brought it there by a rename, over every commit, sweeps and imports included; dates the truck factor's areas; not in the `--json` export, where the truck factor's evidence carries the result as `new_since` |
| `maat-fixes.csv` | change analysis | fix commits per file: total, last, and in the last six months |
| `functions.csv` | lizard | per-function complexity, length, parameters, in lizard's own `--csv` columns, then two of gitmole's: a label for a function lizard could not name (the text of its start line) and, when the span looks mis-parsed, why |
| `theseus/` | blame pass (git-of-theseus with `--plots`) | surviving lines by year and by author |
| `code-age.png` | git-of-theseus, `--plots` only | stacked plot of surviving code by year |
| `survival.png` | git-of-theseus, `--plots` only | how long a line of code tends to live |
| `trend.json` | trend step | complexity and lines of the top hotspots at sampled commits |
| `backtest/` | backtest step | the change analysis and size as of six months before the last commit |
| `signing.json` | signing step | commits signed, by mechanism (gpg, ssh, x509), by year, humans against bots, per identity and over the last year, from the commit objects; `forge` counts the commits the forge committed and signed itself (included in the other counts) |
| `hygiene.json` | hygiene step | each hygiene check's raw result: unpinned actions, lock-file drift, update coverage, policy files, dependency confusion shapes, install scripts, binaries, submodules, symlinks, Trojan Source, the declared licences, the declared dependencies nothing imports |
| `unreachable.json` | secrets step | objects no ref reaches, the blobs among them, how many were scanned and how many findings they gave; a property of this clone, so the `--json` export carries the counts in its `envelope` |
| `structure.json` | structure step, Python 3.10 or newer | per file: language, lines, comments, TODO/FIXME/XXX/HACK markers with a sample, top-level definitions, the files it imports and which of those only after it loads (`deferred`) — resolved for Python (from a root), JavaScript and TypeScript (relative paths), C and C++ (quoted includes), Ruby (`require_relative`, and `require` of a tracked file) and Go (an import path against the `module` and relative `replace` lines of the go.mod files in the tree; a Go import names a package, so it is an edge to every file of that directory the build compiles into it, `_test.go` and `package main` aside), while Rust, Java, C# and PHP imports stay unresolved — its deepest nesting and highest cognitive complexity; the notable functions (nesting, cognitive complexity, complex conditions, bumps); how many imports resolved per language; the empty catch blocks, string-literal addresses and commented-out code lines per file; the possibly unreferenced files; or a status saying how to install it |
| `provenance.json` | provenance step | trailer keys, co-authors who never author, sign-offs by them, the declared commits against the rest (with each side's watch-list hit rate; the JSON keeps the keys `cohort` and `marked`), the lines added, moved and churned within two weeks in the last year and the year before, the commit-shape descriptors, and the agent files (instructions and how far behind, guardrails, approval settings, personal settings tracked, MCP declarations with the keys of literal values, hook commands with their scripts, plugin manifests, skills) |
| `run.log` | gitmole | every command run and its stderr |

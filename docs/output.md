# The report and the output files

How to read each part of the terminal report, and what each run writes to disk; back to [the README](https://github.com/antvinni/gitmole#readme).

## The terminal report

1. **Header**: commits, date span, identities, branch, size, top languages,
   one line for the busiest day and hour, the share of fix commits, the
   share that are reverts when there are any, the year most surviving
   code was written (or why the blame pass did not run), and the share of
   commits signed and by what (`51% of commits signed (gpg 49%, ssh 2%),
   60% of the last year's`), and a one-line tally of the findings. Signing
   is read from the `gpgsig` header in each commit object, so it needs no
   keyring and a fresh clone reads the same as the author's; nothing is
   verified, and the figure is evidence toward SLSA Source L2, never a
   level. `--full` and Markdown add a Signing by year table with humans
   against bots and the busiest identities. With a year of history, the
   header also gives the duplication rate's direction, `26.5% of lines
   duplicated, down from 28.1% a year before`: the duplicates step runs
   jscpd a second time over the tree as it stood a year before the last
   commit. `--full` and Markdown add a Trailers table: every hyphenated
   trailer key and how many commits carry it, then the commits an
   `Assisted-by` trailer or a co-author who never authors a commit marks,
   against the rest (reverted, fixes, a file changed again within two
   weeks), with the share of the history they cover, and three neutral
   descriptors of how commits arrive (bursts of five or more within ten
   minutes, conventional-commit subjects, hours of the day). This
   repository against itself, with no prior from elsewhere, and nothing is
   labelled: every descriptor has an ordinary cause. With `--full`, and always in Markdown, a coverage
   line counts the tracked text files by why they are out of the scored
   pool: `4,512 files: 582 scored · 13 generated · 2,680 test files · 139
   example code · 3 release files · 1,095 not a source type`, and a file of
   a type scc does not classify counts as `not counted by scc`. An output
   directory from before 0.10 has no coverage and shows no line.
2. **Findings**: anything the heuristics flagged, worst first. Findings of
   the same kind are grouped into one entry with a list, and every finding
   ends with a next step that names the file, area or person to start with,
   on its own line under the facts. Currently: a dormant repository (no
   commits for twelve months or more, measured against the run's reference
   date, which also silences the untouched-files note),
   secrets in history (see below), credential-shaped files tracked (a
   warning: a tracked `.env` or `.env.*` that is not a template, `.netrc`,
   `_netrc`, `.pypirc`, `.dockercfg`, a private key named `id_rsa`,
   `id_dsa`, `id_ecdsa` or `id_ed25519`, and anything under a `.ssh/`
   directory; the name alone is the finding, whatever the contents, and
   test and example paths are not counted; the advice is to move the values
   to the environment, `git rm` the files and add them to `.gitignore`),
   an unconfigured git identity
   (example.com and the like; the advice offers the `.mailmap` line that
   would merge it into the busiest real identity), one author owning most
   surviving code, git-sizer concerns (a large blob that is no longer in
   the tree says so, since deleting it did not shrink the clone), one file dominating the churn, bug magnets (source
   files fixed three or more times in the last six months; a warning at
   five), reverts (5% of commits or five of them; a warning at 10%; names
   the file most often backed out when any file was backed out twice,
   otherwise says the reverts are spread), brain methods (functions with
   complexity 15+ and 100+ lines; a warning when one sits in a hotspot),
   hotspots getting more complex (three or more of the top ten hotspots
   grew by a quarter in a year; a warning when the top one did),
   tightly coupled file pairs (a file and its test are expected to change
   together, so those pairs are left out), duplicated blocks of 30+ lines
   (jscpd, over the tracked code files; a block whose every copy is vendored
   or generated is left out), vulnerable dependencies (see below), a large share of stale files (files still in the
   tree; deleted paths do not count), knowledge islands: areas of at least
   200 lines and 1% of the code written almost entirely by one person (a
   warning when such areas hold most of the code), and knowledge loss (people with no commits
   in the twelve months before the last commit who wrote 10% or more of the
   surviving code; a warning at 30%). An unconfigured identity is only
   flagged when it made at least 1% of the commits.

   Repository hygiene is read from the clone alone, the checks OpenSSF
   Scorecard and the OSPS Baseline otherwise make through the GitHub API,
   each rule naming the Scorecard check it stands in for: workflow steps
   that use an action by tag or branch rather than a full commit SHA (a
   warning); a manifest whose last commit is newer than its lock file's, by
   commit time (a warning), and a manifest of an ecosystem that locks by
   convention with no lock file in its directory or above it (a note); the
   ecosystems with a tracked lock file that `dependabot.yml` does not cover,
   or no update tool at all (Renovate covers every manager by itself); no
   licence file, no `SECURITY.md`, and `CODEOWNERS` lines that match no
   tracked file; a scoped npm package resolved from another host than the
   one `.npmrc` declares for its scope (a warning), lock files that mix
   registries, and a pip `extra-index-url`; packages that run install
   scripts, lifecycle scripts in the repository's own `package.json`, and
   process or network calls in `setup.py`; executables by their magic bytes
   (ELF, PE, Mach-O) outside test and example paths (a warning), and blobs
   `.gitattributes` sends to LFS that were committed as they are;
   submodule URLs with credentials (critical; the credential is redacted),
   over plain `http://` or `git://` (a warning), relative, or following a
   branch; symlinks that resolve outside the tree or into `.git/`; and
   Trojan Source, bidirectional control characters in source files
   (CVE-2021-42574, critical) and identifiers that mix Latin with Cyrillic,
   Greek or another confusable script (a warning). `hygiene.json` holds
   every check's raw result.

   What the project declares about its dependencies and licence is read
   as declared, never detected. Declared dependencies nothing imports: a
   `package.json` runtime dependency no tracked file imports, names in a
   quoted string of a configuration file, or runs from the manifest's
   scripts; a `go.mod` direct requirement no import path or `go:generate`
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
   (`--full`, Markdown and `osps` in the JSON) lists the ten controls a
   clone can show: secrets in version control, the licence file and its
   licence, sign-off on every commit, a contribution guide, security
   contacts, a dependency list, executables and binaries in version
   control, and known-vulnerable dependencies. Each gets a result here:
   met, gap, not seen (sign-off below 90% of commits, where a contributor
   agreement outside git would not show), unrecognised (a licence gitmole
   does not know), not applicable, or not checked when the step that reads
   it did not run. It is evidence for a control, not an audit of it;
   access control and most of vulnerability management live in the
   forge's settings and are not in the table.

   With `gitmole[structure]` installed (see
   [install.md](https://github.com/antvinni/gitmole/blob/main/docs/install.md#structure-nesting-debt-markers-the-import-graph)),
   tree-sitter parses every tracked file in eleven languages, once per
   file content, and seven more findings can appear. Debt the authors
   flagged in hotspots: TODO, FIXME, XXX and HACK comments, the markers
   Maldonado and Shihab defined, in the top ten hotspots (three or more in
   one, or any in two). Deeply nested code: functions nested five levels or
   more, or with three or more separate chunks of nested logic (CodeScene's
   bumpy road), with Sonar's cognitive complexity beside them; a warning
   when one sits in a top hotspot. Coupling with no import behind it: a
   pair that changes together 60% of the time or more although neither
   file imports the other, which Ajienka and Capiluppi found is common and
   usually a shared format, a duplicated rule or copied code; only for
   languages whose imports the graph mostly resolves (Python, JavaScript,
   TypeScript, C, C++, Ruby). Possibly unreferenced files: Python,
   JavaScript and TypeScript files nothing imports that are no entry point
   by convention (`__main__.py`, `index.*`, `main.*`, `*.config.*`, a
   dotfile, a file beside `package.json`, `bin/`, `scripts/`,
   `migrations/`, file-routed `pages/` and `app/`), by declaration
   (`pyproject.toml` scripts, `package.json` main, bin and exports) or by
   content (a `__main__` guard, a shebang); a basename that recurs in three
   directories, and a directory the code itself barely imports, are loaded
   by name and left out, and a language where more than one file in twenty
   still looks unreferenced loads code by name and gets no list at all.
   Never "dead": a dynamic import does not show in an import graph.
   Three shape rules, in the source files only (tests, examples,
   documentation, vendored and generated files left out). Errors caught
   and dropped: catch, except and rescue blocks with no statement and no
   comment, five or more, a warning when one sits in a top hotspot; a
   comment keeps a block out, since it says the error is ignored on
   purpose, and in Python only a bare `except:` or one catching Exception
   or BaseException counts, since `except KeyError: pass` is the
   language's idiom. Addresses written into the code: IPv4 addresses in
   string literals, loopback, `0.0.0.0`, broadcast and netmask shapes, the
   RFC 5737 documentation ranges, a trailing `.0` (a network, or a
   four-part version) and a first octet of 0 to 2 (how an ASN.1 object
   identifier starts) left out, and literals inside attributes and
   annotations too. Code left in comments: files with ten or more lines of
   it, counted per block (a block comment, or line comments on consecutive
   lines) when four lines in five read as a statement and one starts right
   at the comment marker; prose with a worked example under it,
   documentation comments and tool directives are not counted. These rules
   run on the same tree-sitter pass rather than a second parser, the
   roadmap's ast-grep: its rules would have been a second wheel for three
   checks one cursor walk already makes.
   Flow-typed JavaScript parses with errors, and its metrics come from the
   partial tree. The watch list gains three reasons from the same step:
   `5 TODO/FIXME comments`, `parse() nested 6 deep`, and `defines 72
   functions and classes` for a file with sixty or more.

   What the history declares about how commits were made is read, never
   inferred. Agent configuration is a surface like `package.json`: a
   committed setting that turns approval prompts off
   (`permissions.defaultMode` set to `bypassPermissions`) and a tracked
   `.claude/settings.local.json`, which is meant for one machine, are
   warnings; an MCP server declaration (`.mcp.json`, `.cursor/mcp.json`,
   `.vscode/mcp.json`) whose environment holds a literal value of sixteen
   characters or more rather than a `${VAR}` reference is a warning that
   names the key and never the value; an instruction file (`AGENTS.md`,
   `CLAUDE.md`, `GEMINI.md`, `.github/copilot-instructions.md`) six months
   and a hundred commits behind the last commit is a note. A `Signed-off-by`
   from an identity that co-authors commits but never authors one, on two
   commits or more, is a note: the Linux kernel's policy forbids an agent
   to add the Developer Certificate of Origin.

   Knowledge is also measured by degree of authorship (Avelino et al.): per
   file and person, a bonus for creating it (the first commit that added
   lines to it; a pure move creates nothing), their own changes, and a
   logarithmic dilution by everyone else's, so changes count, not lines,
   and a reformat transfers nothing. A person is an author of a file when
   their degree is at least three quarters of the file's highest. The
   truck factor is how many authors have to leave before more than half
   the source files have none; one is a warning, two a note, and an area
   whose own truck factor is one is named. It is computed a second time
   with knowledge halving every five months (JetBrains' Bus Factor
   Explorer), and when the surviving code's largest share belongs to
   someone else, the finding says so. Files whose authors have left: five
   or more source files changed in the last year whose every author has
   stopped committing, "creator left, editors remain". Components that
   change together: top-level directories (or the level below a lone
   `src/`) sharing 30% or more of their logical changes, test,
   documentation, example and vendored directories left out: coupling at
   the level of the architecture.

   Two checks are also reported when they pass: a green `No secrets in
   history` line closes the panel whenever the betterleaks scan ran and
   found no secret value, and a green `No known vulnerabilities in
   dependencies` line whenever osv-scanner checked the lock files and found
   nothing, so a clean result is said out loud rather than left to silence.
   Neither is counted as a finding. When a scan did not run, because the
   step was killed or `--no-run` points at an output directory without its
   file, the line is absent. The Markdown export carries them as `**ok**`.

   Vulnerable dependencies come from osv-scanner over the lock files,
   offline against the local copy of the OSV database (see
   [install.md](https://github.com/antvinni/gitmole/blob/main/docs/install.md#the-vulnerability-database)
   for the one-time download). One row per package with an advisory: the
   CVE or advisory id, the worst CVSS score, and the version that fixes it.
   A package pinned by a lock file in the source tree is a warning, critical
   when an advisory scores 9.0 or more or is a `MAL-` record (OpenSSF's
   malicious-packages list ships in the same database; those records carry
   no score, and a malicious package is critical whatever its score); a
   package pinned only by a lock file under tests, examples, docs or
   vendored code is a note. The advice names the package to upgrade first,
   or, for a malicious one, to remove. An advisory that does not apply to your
   code is silenced in `osv-scanner.toml` at the repository root. Each row
   says whether any tracked source imports the package (`imported`: true,
   false, or unknown where the import name need not be the package's, as
   in Python and Ruby); the finding names a package nothing imports, and
   never lowers its severity for it, since an unimported package is still
   installed. This is not reachability, which needs a buildable tree. The footer
   line says how many packages in how many lock files were checked and how
   old the database copy is; without lock files, or without the database, it
   says that instead.

   Secrets are grouped by value, so one key copied into ten files is one
   entry with its places counted. A value found in any source file is
   critical. A value found only in test files, such as fixtures and saved
   web pages, only in example, sample, fixture, demo, rules or stubs
   directories and `.stub` files (a language sample, a scanner's own rule
   definitions, a template a generator fills in), only in vendored
   code (upstream's own specimens), or only in documentation (`.md`,
   `.rst`, `.txt`, `.adoc`, anything under `docs/`, and type stubs, `.pyi`
   and `.d.ts`, which declare shapes and hold no runtime values), where it
   is usually a template, is a warning.
   Twelve shapes cannot be a live secret and are left out, counted on the
   footer line: version strings, tokens shortened with "...", a dotted
   path of lowercase words such as `passwords.password` (a translation or
   config key), whole-value
   template markers such as `your-project-id`, `<your-token>`, `XXXX-XXXX`
   or `changeme`, a template field anywhere inside the value (`{token}`,
   `${X}`, `%(name)s`, `<user>`), five or more words of prose, a whole
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
   time, one `git show` per finding, and never written). Every
   rule is about the whole value; nothing is skipped by prefix. To silence a
   false positive for good, copy its fingerprint from `secrets.json` into a
   `.betterleaksignore` at the repository root; betterleaks reads it on the
   next run, and an existing `.gitleaksignore` works too.

   betterleaks walks the history the refs reach; it does not see a commit
   only the reflog remembers, a dropped stash or a blob added and never
   committed. The secrets step also takes every object in the repository
   less those a ref reaches, writes the blobs among them (up to 5,000, each
   under a megabyte) under the output directory for one `betterleaks dir`
   pass, removes them again, and reports what it finds as `(unreachable
   blob <hash>)`; the footer says how many it scanned, or that there were
   none, which is what a fresh clone looks like, since a clone fetches only
   what a ref reaches. betterleaks' live validation of a found credential
   is network, so gitmole passes `--validation=false` rather than rely on
   the default.

   The values themselves are never written. `secrets.json` holds a short
   keyed hash in place of each value, the matched text and the commit
   message; the key is random, made for that one report and never saved, so
   a stored hash cannot be checked against a list of common passwords. It
   only tells you which hits in one report share a value.

   A commit counts as a fix when its subject starts with `fix:`, `hotfix:` or
   `bugfix:` in the conventional style, or mentions fix, bug, hotfix,
   regression or crash; a fix that changes more lines than 99% of the
   repository's commits (never under 500) is tangled by size and credits
   none of its files, in the fix counts, the bug-magnet finding and the
   backtest alike, and `activity.json` counts them. Test files are left out of every finding that names a
   file, area or function: they change with every fix, and owning the tests is
   not the knowledge risk. The default tables leave them out too; `--full`
   shows them.

   The change log is read with whitespace ignored (`git log -w
   --ignore-blank-lines`), so a hunk that only re-indents counts no lines
   and a file a formatter only re-indented is not a revision. A commit that
   touches at least as many files as 99% of the repository's commits (never
   fewer than twenty) and takes out as many lines as it puts in, within a
   tenth, is a sweeping commit: a formatter run, a rename across the tree, a
   copyright-year bump. It would count as a revision of every file it
   touches and couple them all to each other, so it is left out of the
   revisions, coupling, authors, ownership, fix and age counts, along with
   every commit the repository declares uninteresting in
   `.git-blame-ignore-revs` (and the file `blame.ignoreRevsFile` names);
   the activity totals keep them, `activity.json` lists them, the watch
   list's caption counts them, and the finding names the undeclared ones
   with the advice to declare them, so that git blame and GitHub skip them
   too. A commit's `Co-authored-by` trailers (git's own trailer, which GitHub
   adds to a squash merge and pair programmers add by hand) name people who
   count as its authors too: in the People table, credited with the commits
   they are named on, through `.mailmap` and the same identity merge and bot
   rules; in the authors and ownership tables, where a commit's lines are
   shared equally between everyone it credits; and in the code-age pass,
   where a blamed line is shared the same way, so a squash-merged repository
   does not attribute every line to whoever pressed the button.
3. **Since last report**: with `--compare BEFORE.json`, what changed
   against an earlier `--json` export of the same clone. Findings are
   matched by their rule id, and for the two rules that emit one finding per
   row by the rule id with the metric (repo health) or the mailbox
   (unconfigured identity); each one is listed as new, resolved or
   persisting, and a persisting finding whose severity moved says
   `warning → info`. Then the files that entered and the files that left
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
4. **Watch list**: the five source files most likely to need a fix next, with
   the reasons in words. Every source file still in the tree that changed
   more than once is ranked by revisions × lines of code, over source
   files only: measured against the fixes that followed at six cut-offs
   on three repositories
   ([validation.md](https://github.com/antvinni/gitmole/blob/main/docs/validation.md)),
   it named more of them than any weighting of fixes, complexity and
   ownership did. A file's score, which `--risk` adds up, is its share, in
   percent, of all scored files' revisions × lines of code; the reasons
   name the fix count (the last six months' when there are any), the sole
   owner, the minor contributors when there are three or more (people with
   under 5% of the file's commits each), the most complex function lizard found (a nameless one by its
   line; a span marked `?` in the complex functions table is passed over)
   and, when its complexity grew by a quarter or more in a year, by how
   much (the trend is sampled for the ten top hotspots only, so a file
   further down the list may have none), the files it always changes
   with, when it shares five or more commits with twenty or more other
   files, how many (Tornhill's sum of coupling: the file weakly coupled to
   everything), when three or more and a quarter of its changes were made
   between midnight and 4 am in the author's own time zone, how many
   (Eyolfson et al.; a tie-breaker, never a rank), when it changed in twelve or more different months, how
   many (Hassan's change entropy: scattered changes, which lost to the
   ranking on the backtest and so stay a reason), and, over five or more changes, when a test file moved
   with at most a fifth of them (`no test changed in its 38 changes`, `a
   test changed in 4 of its 28 changes`; a repository with no test file
   anywhere says nothing), none of them entering the rank. Test files are left out, and so
   are vendored code and example code (the `examples/`, `samples/`,
   `fixtures/`, `testdata/`, `demos/`, `rules/` and `stubs/` directories
   and `.stub` files), which the complex functions table hides for the same
   reason: somebody else's code, or a specimen, is not this repository's
   risk. Generated files, amalgamations and release plumbing leave the pool
   too, for their own reasons rather than that one. Under `--since`, churn
   and ownership are windowed and the list says so.
   `--full` and the exports show fifteen. `--full` and Markdown add a Watch
   list by component: each component's share of the list's revisions ×
   lines of code and its own top three files, since one busy subtree
   otherwise takes the whole list; the JSON carries it as
   `watch_by_component`. The default report shows a row's
   first six reasons, most actionable first, and counts the rest (`· 3
   more`); `--full`, Markdown and the JSON carry them all.
   With `--risk BASE`, a
   Change risk section follows: every file changed since BASE with its watch
   score as a bar and the reasons, or why it has none: the first reason that
   applies of `generated`, `vendored`, `test file`, `example code`,
   `release file`, `amalgamation`, `not a source type` and `not in the
   tree`, the last covering a file the change deleted and, under `--no-run`,
   one added after the run; otherwise `changed once`, or `no revisions on
   record`. The caption adds Kamei's factors for the change (files,
   directories and commits; lines added against the lines the files had;
   how evenly it spreads; files changed this month; prior changes and
   people; the author's prior commits) and the companions the change left
   untouched (`not touched: core/ast.py, which changes with core/parser.py
   72% of the time`); the JSON carries them under `change_risk.change` and
   `change_risk.coupling_gaps`, and each scored file's rank, fix counts,
   owner, share and minor contributors. `--hook` is the same scoring for a
   coding agent's hook, see
   [cli.md](https://github.com/antvinni/gitmole/blob/main/docs/cli.md#agent-hooks).

   Under the watch list, one line says how the list would have done:
   gitmole reruns the change analysis as of six months before the last
   commit, with scc on the tree at that time, ranks the watch list from
   that, and counts how many of the files fixed since were on it, next to
   what a random list of the same size, drawn from the files that had
   changed more than once, would score. Repositories with under a year
   of history say `too little history to backtest`.

   That line is one cut-off on one repository. How the list does over six
   cut-offs on curl, django and react, next to lists ranked by churn alone,
   by size alone and by the factor product the list used to rank by, is in
   [validation.md](https://github.com/antvinni/gitmole/blob/main/docs/validation.md).
   "Fixed" means a commit whose subject says so, which is a proxy for a bug.
5. **Tables**: people (identities merged on top of `.mailmap` when they
   share an email, two name words, the same name spelled identically
   unless it is a bare common first name, a one-word handle that is a
   distinctive word of the fuller name, the fuller name run together
   (RobinMalfait), or an initial plus the surname (nlohmann); the caption says whose; bots,
   which are any author named `*[bot]`, any identity that merges with
   one (`github-actions` beside `github-actions[bot]` is one account),
   and any author whose name says bot, CI, deploy or automation, no
   product names, are counted apart in the caption and kept out of the
   timeline; their lines are left out of ownership and surviving code
   too, so a deploy job that commits a built site owns nothing), a knowledge map (lines added per area of the tree
   and who wrote them), a timeline of commits per author over the last
   twelve months, change coupling, the most complex functions, repo
   health. On a narrow terminal the timeline shows fewer of those months,
   dropping the oldest, rather than folding an author's name; the title
   names the months shown. Hotspots, ranked by revisions times lines of
   code with the number of fix commits alongside, rank the same files the
   watch list leads with, and so appear under `--full` and in the Markdown
   export, next to size by language, activity and surviving code by year.
   Change coupling counts logical changes rather than commits: commits
   whose subjects share a ticket-shaped key (GitHub's `(#1234)` squash
   suffix, a Jira-shaped `PROJ-42` opening the subject, `Fixes #77`) are one
   change wherever they landed, and the rest group by author and calendar
   day, code-maat's temporal period, so a rebase-merged pull request is one
   change again and a change spread over a ticket's commits counts once;
   the cap of thirty files per change applies after grouping, and the sum of
   coupling and the test co-change counts use the same changes. The caption
   says how changes reach the branch when that changes what a pair means:
   almost no merge commits and most subjects ending `(#NNNN)` is a
   squash-merged repository, whose pairs describe pull requests rather than
   edits; a tenth or more of the commits being merges means the pairs
   describe the commits on the branches, since a merge exports no file list.
   Change coupling hides pairs where either file is
   no longer in the tree, since they describe a layout that no longer
   exists, and shows a directory whose files all change together (generated
   tables, one file per version) as one row with the file count and the
   weakest degree; the caption counts both and `--full` shows every pair.
   Hotspots hide files no longer in the tree the same way. Hotspots carry a `trend` column, sampled for the
   top ten hotspots: the change in complexity over the last year from scc on
   the file at sampled commits (`--full` shows the whole series as a
   sparkline), and under `--full` a `minors` column (contributors with under
   5% of the file's commits) and a `co-changes` column (the files it shares
   five or more commits with). The knowledge map marks owners who have stopped committing
   with `(gone)`, and under `--full` shows the share of each area's lines
   that they wrote. With `--full`: size by language, activity by weekday
   with the busiest hour and the share of commits that are fixes, and
   surviving code by year.

   Size, hotspots, coupling, ownership, code age and the watch list analyse
   source files: a built-in list of code extensions plus names like Makefile
   and Dockerfile (`--file-types all` counts everything). In the default
   report, the complex functions table hides test files and generated
   files (a file whose first lines say it was generated or must not be
   edited, that `.gitattributes` marks `linguist-generated`, which git
   resolves as it does for itself, nested `.gitattributes` included, or
   that is a bundle, a minified file, a source map or anything under
   `dist/` by name, the run records them in `meta.json`; and an amalgamation, a
   file every one of whose functions also appears identically in other
   files, found from the function metrics); the hotspots table, drawn
   under `--full` and in the Markdown export, hides the same test files
   and generated files in the Markdown export, since `--full` shows
   everything. The complex functions table also hides vendored code
   (`vendor/`, `vendored/`, `node_modules/`,
   `third_party/`, `external/`, `deps/`, `.yarn/`, a `packages/` inside a package
   such as `requests/packages/`, and any directory whose own `LICENSE` or
   `COPYING` names none of the copyright holders the root licence names,
   or that `.gitattributes` marks `linguist-vendored`, which the run records
   in `meta.json`) and example code (the directories the watch list leaves
   out), and the change coupling table hides pairs
   with a test file, pairs of release plumbing (two version files, a
   manifest and its lock file, changelogs), header pairs (a C-family
   source file and its own header) and pairs with a vendored file on
   either side; the captions show how many are hidden, and
   `--full` shows them. Release plumbing is also hidden from the hotspots
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
   methods finding. Activity and the
   timeline cover the whole history.
6. **Footer**: where the files and plots are. `--full` and Markdown close
   with a Run line above it: what produced the report, gitmole's version,
   every tool's and the `--ignore`, `--ignore-data` and `--deep` options,
   read from the run manifest `meta.run` (the commit, the versions, the
   options). The header shows that commit as `branch main @ 540ee5b5`. An
   output directory from before 0.10 has no manifest and shows neither.

A full example, at a pinned commit, is
[docs/examples/react.md](https://github.com/antvinni/gitmole/blob/main/docs/examples/react.md).

## The output directory

Lands in `analysis-<repo>/` next to a local clone, or in the current
directory for a remote target:

| File | From | What it is |
|---|---|---|
| `meta.json` | git | name, branch, commit count, merge-commit count, date span and identities of the checked-out branch's history; every step's outcome under `steps`; what produced the run under `run`; the classifier's `coverage`, `credential_files`, `generated` and `vendored` lists |
| `activity.json` | change analysis | commits by weekday, hour and month; net lines per year; fix-commit count; per-author totals and monthly timeline; the sweeping commits left out of the tables, each marked whether `.git-blame-ignore-revs` declares it, and how many declared commits the log holds; the oversized fixes left out of the fix counts, the tangled commits with a sample, and how many subjects end in a squash-merge suffix |
| `size.json` | scc | lines per language, COCOMO estimate |
| `repo-health.txt` | git-sizer | oversized objects, deep trees, other repo problems |
| `secrets.json` | betterleaks | secret-looking strings across all history: rule, file, commit, line and fingerprint, with each value replaced by a short keyed hash |
| `dependencies.json` | osv-scanner | the lock files with their package counts, one row per package with a known vulnerability (ids, CVE aliases, score, fixed version, whether an advisory is a `MAL-` record), the database date and a digest of that snapshot; or a status: no lock files, no local database |
| `packages.json` | osv-scanner, with or without its database | every package the lock files pin, once per ecosystem, name and version, with the lock files that pin it and the licence a lock file declares; read by `--sbom`, not part of the report |
| `log.txt` | git | the numstat log export the change analysis reads, whitespace ignored, with each commit's `Co-authored-by` trailers behind its subject |
| `maat-revisions.csv` | change analysis | change frequency per file |
| `maat-coupling.csv` | change analysis | files that change together, over logical changes (a ticket's commits, or one author's day) |
| `maat-soc.csv` | change analysis | sum of coupling per file: its co-changes with any other file, and how many files it shares five or more commits with, over logical changes |
| `maat-tests.csv` | change analysis | per production file, how many logical changes touched it and how many of those also touched a test file |
| `maat-doa.csv` | change analysis | degree of authorship per file and person: created it, own changes, others' changes, the degree undecayed and with knowledge halving every five months, and whether each counts as an author |
| `maat-latenight.csv` | change analysis | per file, its revisions and how many were committed between midnight and 4 am in the author's own time zone |
| `maat-components.csv` | change analysis | coupling between components at one and two directory levels, over logical changes: shared changes, degree, average revisions |
| `maat-entropy.csv` | change analysis | Hassan's change entropy per file: the months it changed in, and its decayed history complexity (its share of each month's changes times that month's entropy over files, halved per month back) |
| `maat-authors.csv` | change analysis | authors per file (co-authors included), and how many of them are minor contributors |
| `maat-age.csv` | change analysis | months since last change per file |
| `maat-entity-ownership.csv` | change analysis | lines added and deleted per author per file, a commit's lines shared between its author and co-authors |
| `maat-fixes.csv` | change analysis | fix commits per file: total, last, and in the last six months |
| `functions.csv` | lizard | per-function complexity, length, parameters, in lizard's own `--csv` columns, then two of gitmole's: a label for a function lizard could not name (the text of its start line) and, when the span looks mis-parsed, why |
| `duplicates.json` | jscpd | duplicated blocks over the tracked code files, largest first (the thousand largest), each with every place it appears, and the share of lines inside a block, now and at the last commit a year before; no source text |
| `theseus/` | blame pass (git-of-theseus with `--plots`) | surviving lines by year and by author |
| `code-age.png` | git-of-theseus, `--plots` only | stacked plot of surviving code by year |
| `survival.png` | git-of-theseus, `--plots` only | how long a line of code tends to live |
| `trend.json` | trend step | complexity and lines of the top hotspots at sampled commits |
| `backtest/` | backtest step | the change analysis and size as of six months before the last commit |
| `signing.json` | signing step | commits signed, by mechanism (gpg, ssh, x509), by year, humans against bots, per identity and over the last year, from the commit objects |
| `hygiene.json` | hygiene step | each hygiene check's raw result: unpinned actions, lock-file drift, update coverage, policy files, dependency confusion shapes, install scripts, binaries, submodules, symlinks, Trojan Source, the declared licences, the declared dependencies nothing imports |
| `unreachable.json` | secrets step | objects no ref reaches, the blobs among them, how many were scanned and how many findings they gave |
| `structure.json` | structure step, `gitmole[structure]` only | per file: language, lines, comments, TODO/FIXME/XXX/HACK markers with a sample, top-level definitions, the files it imports, its deepest nesting and highest cognitive complexity; the notable functions (nesting, cognitive complexity, complex conditions, bumps); how many imports resolved per language; the empty catch blocks, string-literal addresses and commented-out code lines per file; the possibly unreferenced files; or a status saying how to install it |
| `provenance.json` | provenance step | trailer keys, co-authors who never author, sign-offs by them, the marked cohort against the rest, the commit-shape descriptors, and the agent files (instructions and how far behind, guardrails, approval settings, personal settings tracked, MCP declarations with the keys of literal values) |
| `run.log` | gitmole | every command run and its stderr |

## How to read the output

1. Start with the header and the findings.
2. The watch list is the source files ranked by revisions × lines of code, from
   `maat-revisions.csv` joined with scc's per-file size. The change log follows
   renames, so a moved file is one entity under its new path and a pure move
   adds no lines: whoever moved a tree to `src/` did not write it, and the
   knowledge map says so. Large files that change constantly are your risk; the
   reasons do not move a file, they say what to look at there, and the backtest
   line says how the same list would have done six months ago, or that nothing
   has been fixed since the cut-off. The hotspots table behind
   it, which `--full` and the Markdown export add, ranks every file by the same
   product and carries the trend column; the Markdown export caps it and leaves
   test files, deleted files, generated files and release plumbing out, saying
   how many, and `--full` shows them all. The default report's own tables,
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
   islands, bus-factor and knowledge-loss findings; `--full` shows it.
5. Repo health and secrets are pass or fail checks. Read them only if they
   flag something.

# The report and the output files

How to read each part of the terminal report, what each rule counts and leaves out, and what each run writes to
disk; back to [the README](https://github.com/antvinni/gitmole#readme).

New to the report? [Reading your first report](first-report.md) is the one-screen version: each section in plain
words, and what to do first. This page is the reference. How each part is drawn, line by line, is in the docstrings
of [gitmole/render.py](https://github.com/antvinni/gitmole/blob/main/gitmole/render.py) and checked by its tests;
why it is drawn that way is in the commit history.

## How to read the output

1. Start with the header and the findings.
2. The watch list is the source files ranked by changes × lines of code (a change is one commit that touched the
   file; the JSON calls them `revs`). Large files that change constantly are your risk. The columns beside each
   file (`fixes`, `top author`, `look at first`) do not move it; they say what to look at there, and the caption's
   `Check:` says how the same ranking would have done six months ago.
3. Change coupling shows files that change together. That usually means a hidden dependency or a copied layout; a
   whole directory that changes as one shows as one row.
4. The People table's surviving-code column, the bus-factor and knowledge findings and the knowledge map tell you
   whether knowledge is concentrated in one or two people, and where.
5. The Supply chain section is a pass or fail check. Read it when it flags something.
6. One table, whole: `--section NAME` prints a section on its own with every row, the ones the report hides too,
   each with its kind, and `--csv` writes the same rows as a CSV. `--full` is every section and every finding, not
   every row: its tables stop at 50
   ([One section, whole](https://github.com/antvinni/gitmole/blob/main/docs/cli.md#one-section-whole)).

## The terminal report

Each part is a rounded box as wide as the page, its title in the top border: the header, the Findings, each section
with rows, and the Supply chain section, one box under another. The page is the terminal's width, or 110 columns on
a wider one. A wider or narrower terminal changes how a path is shortened and how prose wraps, never which rows are
shown or their order. Under 60 columns nothing is boxed. A section with nothing to show is one dim line, and
`--section NAME` prints its section without a box, so every line pastes as a row.

**Colours.** Five styles, all the terminal's own named colours, so a light theme and a dark one each draw them in
their own shade: bold for a part's name and the column a table is ranked by; dim for qualifiers, labels, column
heads, captions and borders; cyan for the header's border and a step's `↳`; yellow for a warning and red for a
critical, on the finding's mark and title and on a scan's verdict. Without colour (`NO_COLOR`, a pipe, a file) the
report is the same bytes with the escapes left out. A stream that cannot carry a mark gets its ASCII form (`✖` `x`,
`▲` `!`, `●` `*`, `↳` `>`, `·` `-`, `…` `...`, box borders `+ | -`), and the report keeps the same lines.

**Marks.** `✖` critical, `▲` warning, `●` note, `↳` the next step, `·` a subject or a fact. "Note" is the word the
report uses for the severity the JSON, SARIF and `--fail-on` call `info`.

**Tables.** A table's title carries its count and what it is ranked by (`Complex functions · 8 of 475, by
complexity`; `all 8` when every row is shown). Its caption says what it hides, as a sum with its breakdown (`501
pairs hidden: 289 test, 192 historical, 10 vendored, 8 generated, 2 example`), and then defines its words as `term =
meaning`, each word once, under the first table that prints it. A cell is never wrapped: a path loses its middle
directories first (`prompb/…/client/decoder.go`), then the last text cell is cut with `…`; a number is never cut. In
a finding, a path, a package and a version are always whole. `gone` after a name, a share or a month means no commit
in the `--gone` window (12 months by default); blank means active.

**Numbers and words.** A count of 1,000 or more has its separator; a threshold is `N or more` in a sentence and
`≥N` in a cell; a bare vulnerability score has `CVSS` before it. The column heads `changes`, `complexity` and
`together` are `revs`, `ccn` and `degree` in the JSON.

**Order.** The sections come in one order in the default report, `--full` and Markdown, code first and people
after: Watch list, Complex functions, Change coupling, Knowledge map, People, Supply chain. `--full` adds its own
sections in their groups (Watch list by component and Hotspots after the Watch list, Size by language after Change
coupling, the Timeline after People, then Activity, Surviving code by year, Changed lines and Trailers), and opens a
group after the Supply chain: Secrets by rule, Dependencies by lock file, Signing by year, Checks run, Agent surface
and the OSPS Baseline. Its header closes with a `contents` row, and a table the 50-row cap cut says so in its title
and names where the rest are (`People · 50 of 1,324 identities, by commits · --section people`).

The parts, in order:

1. **Header**: the repository with its branch and commit (`prometheus · branch measure @ 296080c0`), then labelled
   rows. `history`: commits, date span, the `--since` window, identities. `files`: git's tracked files, the ones
   holding code, and the source files every ranking is over (`1,676 tracked · 1,056 with code · 653 scored (source:
   not test, example, generated or vendored)`). `code`: lines, top languages, and the year most surviving code was
   written with the step that counted it (`by blame`, or `by git-of-theseus` after `--plots`). `commits`: the share
   of fix commits and the reverts. `left out`: the sweeping and declared-uninteresting commits no table counts.
   `scope` (a `--path` run) and `steps` (the ones that did not finish) appear when there is something to say.

   When the files no table ranks outnumber the scored ones, the header says so: `581 of 4,512 files scored`, and
   when documentation also holds more lines, `69% of tracked lines are documentation, not ranked · --file-types all
   includes them` and `83% of commits and 72% of fixes change only unscored files`. The counts are under `coverage`
   in the JSON.

2. **Findings**: anything a rule flagged, worst first: critical, warning, note. Within a severity, a finding that
   rests on a path's name alone (a tracked `.env`; its `rule` says `"by": "file name"`) comes after the ones a scan
   or a count stands behind. Findings of one kind are one entry with a list, and every finding ends with a next step
   that names the file, area or person to start with. The title carries the tally (`Findings · 4 warnings ▲ · 10
   notes ●`). In the JSON each finding's `rule` carries its id and the thresholds it fired on, and its `evidence`
   the numbers they were compared with.

   The default report prints each finding short: the count and the rule's numbers, the worst subject or three
   subject lines (`and N more` past them), and the step. A finding whose subjects are a table of the same report
   names the worst one and points there (`(see Complex functions)`). `--full`, Markdown, the JSON and SARIF keep
   the whole statement with every subject it names.

   A finding from a rule whose precision nobody has measured yet (`UNJUDGED` in
   [gitmole/findings.py](https://github.com/antvinni/gitmole/blob/main/gitmole/findings.py)) carries the dim tag
   `(not measured yet)`, and the Findings title counts them. A note from such a rule has no step. JSON (`"unjudged":
   true`), SARIF and `--fail-on` treat them like any other finding. A measure the run could not make says so in one
   dim line closing the Findings (`truck factor not computed: 17 source files, needs 20`), and every such measure
   is under `not_computed` in the JSON.

   The rules, by what they read, are listed below under [The rules](#the-rules).

3. **Since last report** (`--compare BEFORE.json`): what changed against an earlier `--json` export of the same
   clone. Findings are matched by rule id and listed as new, resolved or persisting; a persisting one says when its
   severity moved (`warning → note`) or its counts did (`values 16 → 1`). Then the files that entered and left the
   watch list's top fifteen. The caption says what the comparison is against and lists any options that differ
   between the two runs, and a different OSV database snapshot. The comparison never changes the exit code.

4. **Watch list**: the five source files most likely to need a fix next, ranked by changes × lines of code over
   every source file still in the tree that changed more than once. On the backtest that ranking named more of the
   files fixed later than any weighting of fixes, complexity and ownership
   ([validation.md](https://github.com/antvinni/gitmole/blob/main/docs/validation.md)). The columns: `changes`,
   `fixes` (in the six months to the last commit), `top author` (the largest share of the file's added lines one
   person holds, `gone` when they left) and `look at first` (the function nested deepest at five levels or more,
   else the most complex at 10 or more). A file's score, which `--risk` adds up, is its share of all scored files'
   changes × lines of code.

   The reasons behind a file (its fixes, a sole owner, minor contributors, the most complex function, growing
   complexity, the files it changes with, late-night changes, scattered months, changes without a test) never move
   the rank. `--full` prints them under each row, Markdown in an `also` column, and the JSON as `watch[].reasons`;
   [gitmole/watch.py](https://github.com/antvinni/gitmole/blob/main/gitmole/watch.py) says when each appears. Test,
   vendored, example and generated files and release plumbing are left out of the list. `--full` and the exports
   show fifteen files and a Watch list by component.

   The caption's `Check:` reruns the analysis as of six months before the last commit and counts how many of the
   files fixed since its top fifteen held, against the same number of most-changed files and a random pick: `6
   months ago the top 15 of this ranking held 13 of the 91 files fixed since. The 15 most-changed files also held
   13; 15 random files would hold 2.9.` A result a random pick could have given (Fisher's exact test, p ≥ 0.05) says
   so. Under a year of history: `Check: none, too little history to backtest`. "Fixed" means a commit whose subject
   says so, a proxy for a bug.

   With `--risk BASE`, a **Change risk** section follows: every file changed since BASE with its watch score as a
   bar and its reasons, or why it has none (`generated`, `test file`, `not in the tree`, `changed once`, …). Its
   caption adds Kamei's factors for the change and the companions it left untouched (`not touched: core/ast.py,
   which moved in 72% of core/parser.py's changes`). `--hook` is the same scoring for a coding agent's hook
   ([cli.md](https://github.com/antvinni/gitmole/blob/main/docs/cli.md#agent-hooks)).

   When documentation is more than half the tree's lines and none of it is ranked, **Most-changed documents**
   follows: the five most-revised documents, by revisions alone. It is not a score and no finding.

5. **Tables.**
   - **Complex functions**: lizard's functions by cyclomatic complexity, test, generated, vendored and example code
     hidden. A function lizard cannot name goes by its file and line. A `?` marks a span lizard's JavaScript or
     TypeScript reader may have mis-parsed (it lost its place in a template literal or JSX); such spans sort last
     and stay out of the brain-methods finding. When no function meets the brain-methods rule and the list fits, the
     table is one line (`no long, complex functions; highest complexity 16 (handleRequest)`).
   - **Change coupling**: pairs of files that change together, over logical changes rather than commits: commits
     sharing a ticket-shaped key (`(#1234)`, `PROJ-42`, `Fixes #77`) are one change, and the rest group by author
     and day. Pairs with a test file, release plumbing, a C file and its header, two locale files, a vendored file
     or a file no longer in the tree are hidden and counted. The two files are one cell in brace form
     (`web/{api/v1/api.go,web.go}`), and a directory whose files all change together is one row. `together` is the
     share of the two files' changes made in one commit. `--full` and Markdown say when squash merging or many merge
     commits change what a pair means.
   - **Knowledge map**: lines added per area of the tree over its history (`added`, not the size at HEAD), and who
     wrote them, `gone` after an owner who stopped committing. Areas are top-level directories, or the
     subdirectories of a lone one such as `src/`; an area the tree no longer has is hidden and counted. An `agents`
     column shows the share coding tools wrote, where it is large enough to matter.
   - **People**: identities merged on top of `.mailmap` when they share an email, two name words, the same name, a
     handle that is a distinctive word of the fuller name, the fuller name run together, or an initial plus the
     surname; the title counts the merges. Merges have their own column and stay out of the commit count. Bots (a
     `[bot]` suffix, an identity that merges with one, a name saying bot, CI, deploy or automation) are counted in
     the caption and own nothing. `last commit` is the month each person was last seen. No rendering shows an email
     address; they stay in the JSON's `meta.identities`. A People row needs five commits in the default report.
   - `--full` adds **Hotspots** (every file by changes × lines of code, with fixes, a `trend` column of complexity
     over the last year, minor contributors and co-changes), **Size by language**, **Activity** (weekdays and the
     busiest hour), **Surviving code by year**, the **Timeline** (commits per author per month over the twelve
     months to the last commit), **Changed lines**, **Trailers**, **Secrets by rule**, **Dependencies by lock
     file**, **Signing by year**, **Checks run** (every hygiene family, scan and step with its result: `clean`,
     `nothing to check`, `did not run`, `finding`, `ran`), **Agent surface** and the **OSPS Baseline**.

6. **Supply chain**, last: what the scans and the tree's own declarations say, in labelled rows whose first words
   are the verdict, in the colour of the worst finding behind it.
   - `secrets`: `none found: betterleaks scanned every commit HEAD reaches`, `none in source files (secrets.json)`
     when every value is in a file that is no source, or `2 values in the findings above, 3 more never in source`;
     then the places at HEAD apart from those only history holds.
   - `dependencies`: what was scanned, the database date, and the vulnerable packages reconciled with the findings
     above (`29 vulnerable in 46 places: 28 in the warning above, 3 in the note, 2 counted in both`); or `no lock
     files found`, or `not scanned` with the reason.
   - `signing`: the share of commits signed by their authors, read from each commit's `gpgsig` header, so a fresh
     clone reads the same as the author's. Nothing is verified, and the figure is evidence toward SLSA Source L2,
     never a level. Commits the forge signed on merge are counted apart.
   - `checked, ok`: the hygiene checks that ran with something to check and found nothing, in a fixed order.

   The default report holds this section to ten lines; a row that would run past its share says less, and `--full`
   prints every row whole.

7. **Closing lines**: what `--full` adds and where every row of a table is; how many steps ran and the flag that
   runs the rest (`--plots`, `--deep`); how to re-render the run (`gitmole DIR --no-run --full`); and the output
   directory's path, alone on the last line. `--full` closes with a Run line (gitmole's version, every tool's and
   the options), an index of the output directory, and the export flags.

**The Markdown export** (`--markdown PATH`) is the same report for a reader who is not on the machine that made it:
a pull-request comment, a job summary. It opens with the tally, then which tier it is and how to get the other, then
the header's facts. Its headings are the terminal's section titles; a finding is a list item with its severity, its
title and its rule id; the Supply chain section is a list. What a reader would paste (paths, functions, packages,
versions, ids) is a code span and the rest is escaped, so nothing is lost to the renderer. It names no path outside
the repository; on prometheus both tiers fit GitHub's 65,536-character limit for a comment. A full example
at a pinned commit is [docs/examples/react.md](https://github.com/antvinni/gitmole/blob/main/docs/examples/react.md).

## The rules

What each rule counts and what it leaves out. When a rule fires, and on what thresholds, is in each finding's `rule`
in the JSON.

**What every rule shares.**
- A **fix** is a commit whose subject starts `fix:`, `hotfix:` or `bugfix:`, or mentions fix, bug, hotfix,
  regression or crash. A fix larger than almost every other commit, or a tangled one (many files across several
  directories under a subject listing several changes), credits none of its files.
- The change log is read with whitespace ignored, so a re-indent is not a change. A **sweeping commit** (more files
  than almost any other, about as many lines out as in: a formatter run, a tree-wide rename) and every commit
  `.git-blame-ignore-revs` declares are left out of revisions, coupling, ownership, fixes and age; the header counts
  them. An **import** (a commit that adds to a great many files and holds a large share of every line ever added,
  such as a project published with its past squashed) gives nobody ownership.
- `Co-authored-by` trailers make their people authors of the commit too, its lines shared equally. A **coding tool**
  is not a person: two or more names on one bare no-reply address, or a no-reply identity credited by trailers for
  nine in ten of its commits. Its lines stay out of ownership, the truck and bus factors and the People rows.
- **Test, vendored, example and generated files** are left out of every finding that names a file, area or function,
  and out of the tables; `--section NAME` shows them, marked. Vendored means `vendor/`, `node_modules/`,
  `third_party/` and the like, `linguist-vendored`, or a directory whose licence or copyright headers name somebody
  the root licence does not. Generated means a marker in the first lines (`@generated`, `DO NOT EDIT`, a generator's
  banner), `linguist-generated`, a bundle, minified file or source map, or an amalgamation. **Release plumbing**
  (version files, manifests, lock files, changelogs, and files that change only by a few swapped lines) is left out
  of the watch list, Hotspots and the churn and bug-magnet findings.
- **Source files** are a built-in list of code extensions and names like Makefile, plus any tracked executable with
  a `#!` line; `--file-types all` counts everything.

**History and size.**
- a dormant repository, measured against the run's reference date;
- credential-shaped files tracked (a warning): a `.env` that is not a template, `.netrc`, `.pypirc`, `.dockercfg`, a
  private key named `id_rsa` and the like, anything under `.ssh/`; the name alone is the finding, test and example
  paths aside. When the secrets scan ran and found no value in the file, the finding says so;
- an unconfigured git identity (example.com and the like) with a share of the commits, with the `.mailmap` line that
  would merge it;
- one author owning most surviving code (the bus factor);
- the truck factor, by degree of authorship (Avelino et al.): how many authors would have to leave before most source
  files had none, how many already have, and the areas where one leaving is enough (`new since <month>` beside an
  area that is new). It is computed a second time with knowledge decaying over time;
- knowledge islands: areas written almost entirely by one person, a warning when they hold most of the code;
- bug magnets: source files fixed again and again in the last six months. A file whose fixes all came with a file
  above it is counted with that file. With twelve months of history or more, a binomial test against the
  repository's own fixes per change (Benjamini-Hochberg at 5%) names the files fixed more often than their size
  explains, and when none is, the finding is a note. A translation file named for its locale is never a magnet;
- brain methods: functions both complex and long, a warning when one sits in a hotspot;
- hotspots getting more complex, a warning when the top one did; the advice goes to the first whose complexity per
  line also rose;
- tightly coupled file pairs, a file and its test aside;
- sweeping commits not yet declared in `.git-blame-ignore-revs`, and an import, named with its share.

**Secrets** (betterleaks over every commit HEAD reaches, plus the objects no ref reaches, written out under the
output directory for one pass and removed again). Values are grouped, so one key in ten files is one entry. A value
in any source file is critical. A value only in tests, examples, fixtures, vendored code, documentation, type stubs,
generated files or mocks is no finding, though the Supply chain row still counts it. A value only `generic-*` rules
found and graded low everywhere is a possible secret, a note; a provider's rule (an AWS key id, a Slack token) stays
critical at any grade. Shapes that cannot be a live secret are left out and counted: version strings, shortened
tokens, dotted config keys, template markers and fields, prose, the words every example uses, alphabet runs,
environment references, empty key headers, masked values, file names, identifiers that contain the keyword, values
the line or the two above call an example. To silence a false positive, copy its fingerprint from `secrets.json` into
`.betterleaksignore` at the repository root. Values are never written: `secrets.json` holds a keyed hash made for that
one report, so it only tells which hits share a value. Live validation stays off (`--validation=false`).

**Vulnerable dependencies** (osv-scanner over the lock files, offline against the local OSV database; see
[install.md](https://github.com/antvinni/gitmole/blob/main/docs/install.md#the-vulnerability-database)). A package
pinned by a lock file in the source tree is a warning. It is critical when it is a `MAL-` (malicious) record, or when
an advisory scores in CVSS's critical band and the lock's directory declares that it ships: a Dockerfile, a Helm
chart, a Procfile or a platform file, a compose service built there, a declared entry point, or Cargo's and Go's
program layout. A library's lock pins only its developers' environment, so it stays a warning at any score and the
finding says which score it held back. Packages are named critical first, then by reach (imported by the source,
installed for running, development only), then those with a fix, then by score; the advice names the highest score
with a fix. A package pinned only under tests, examples, docs or vendored code is a note. A pip requirement with a
range is said as a range whose floor is vulnerable, never as an installed package. An informational advisory
(RustSec's `unmaintained`, `unsound`, `notice`) is not counted as vulnerable. Whether any tracked source imports the
package is said, and never lowers the severity; it is not reachability. Silence an advisory in `osv-scanner.toml` at
the repository root.

**Repository hygiene**, read from the clone alone, each rule naming the OpenSSF Scorecard check it stands in for:
- workflow and composite-action steps that use an action by tag or branch rather than a full commit SHA (a warning;
  another account's action first, a step handed a secret or a writable token before one that is not);
- a manifest newer than its lock file (a warning), and a manifest with no lock file in an ecosystem that locks by
  convention (a note), unless it declares nothing a lock would pin;
- ecosystems with a lock file that `dependabot.yml` does not cover, or no update tool at all;
- no licence file, no security policy, `CODEOWNERS` lines that match no tracked file;
- a scoped npm package resolved from another host than `.npmrc` declares (a warning), lock files mixing registries,
  a pip `extra-index-url`;
- packages that run install scripts, lifecycle scripts in the repository's own `package.json`, process or network
  calls in `setup.py`;
- executables by their magic bytes outside test and example paths (a warning), and LFS-tracked blobs committed as
  they are;
- submodule URLs with credentials (critical, redacted), over plain `http://` or `git://` (a warning), relative, or
  following a branch;
- symlinks that resolve outside the tree or into `.git/`;
- Trojan Source: bidirectional control characters in source (critical) and identifiers that mix Latin with letters
  that pass for it (a warning).

**What the project declares**, read as declared, never detected:
- declared dependencies nothing imports, for npm, Go and Cargo (a note; Python and Ruby are left out, since an import
  name need not be the package's);
- a root manifest naming a different licence from the licence file (a note), or a declared licence that is not OSI-
  or FSF-approved (a warning);
- strong copyleft runtime dependencies in a permissive project, from `package-lock.json` or `composer.lock` (a
  warning); weak copyleft is counted, not flagged.

Rules that give evidence for an OSPS Baseline control carry its id in `rule.osps`, and SARIF tags them with it. The
OSPS Baseline section gives each control a clone can show a result: met, gap, not seen, unrecognised, not applicable
or not checked. It is evidence for a control, not an audit of it.

**Structure** (tree-sitter over every tracked file in eleven languages; Python 3.10 or newer, see
[install.md](https://github.com/antvinni/gitmole/blob/main/docs/install.md#structure-nesting-debt-markers-the-import-graph)):
- debt the authors flagged in hotspots: TODO, FIXME, XXX and HACK comments in the top hotspots;
- deeply nested code: functions nested deep or with several separate nested chunks, a warning in a top hotspot;
- coupling with no import behind it: a pair that changes together though neither file imports the other, for
  languages whose imports mostly resolve, and not for two Go files of one package;
- import cycles: groups of Python, JavaScript and TypeScript files that import each other as they load, each named
  by its shortest loop. Imports that do not run at load (inside a function, type-only, dynamic `import()`, under
  `if TYPE_CHECKING:`) are left out, since they are how a loop is broken on purpose. The finding names the loops and
  does not say which to keep;
- possibly unreferenced files: Python, JavaScript, TypeScript and Go files nothing imports that are no entry point
  by convention, declaration, a path in another tracked file, or content. Never "dead": a dynamic import does not
  show in an import graph;
- errors caught and dropped: empty catch, except and rescue blocks with no comment (in Python only a bare `except:`
  or one catching Exception), a warning in a top hotspot;
- IPv4 addresses written into string literals, loopback, documentation and network shapes aside;
- code left in comments, counted per block.

The last three keep to source files.

**How commits were made**, read from what the history declares, never inferred:
- a committed setting that turns approval prompts off, a tracked `.claude/settings.local.json`, and an MCP server
  declaration holding a literal value instead of a `${VAR}` reference (warnings; the key is named, never the
  value);
- an agent instruction file (`AGENTS.md`, `CLAUDE.md`, …) far behind the last commit (a note);
- a `Signed-off-by` from an identity that co-authors but never authors (a note).

`--full`'s Agent surface lists the hooks, plugin manifests and skills the tree declares, and Trailers and Changed
lines compare the commits a trailer declares against the rest. Nothing there is labelled: every descriptor has an
ordinary cause, and the rest is every commit that declares nothing, never a group of people.

## The output directory

Lands in `analysis-<repo>/` next to a local clone, or in the current
directory for a remote target:

| File | From | What it is |
|---|---|---|
| `meta.json` | git | name, branch, commit count, merge-commit count, date span and identities of the checked-out branch's history; every step's outcome under `steps`, its wall time under `step_seconds` and the peak memory of its largest process under `step_peak_mb` (the `--json` export moves these two into its `envelope`, since they vary between runs); what produced the run under `run` (the commit, gitmole's version, every tool's version under `tools`, the versions gitmole pins under `tools_pinned` and any tool that is not at its pinned one under `tools_moved`, and the options); the classifier's `coverage`, `credential_files`, `generated` and `vendored` lists, and `scripts`, the executables with an interpreter line that are source by shape, each with the file type its interpreter gives it (absent when there are none) |
| `findings.json` | gitmole, last, on every run | the digest of the report, for a script or a CI artefact: `findings`, `watch`, `watch_backtest`, `osps` and `not_computed` as the `--json` export has them, row for row; `summary`, the header's numbers (the portfolio export's row for a repository: commits, dates, the count of identities, lines, files, languages, coverage); of `meta` only `steps` and `run` (what ran, gitmole's version, each tool's and the options); `hygiene` and `dependencies` with every list replaced by its length (`unpinned_count`, `vulnerable_count`), which keeps what each check looked at, what it found and the vulnerability database's date; and `secret_counts`, the secrets scan as counts (values, places at HEAD and only in history, those graded high, placeholders). It is the same bytes for the same commit and options: keys sorted, one line, no path of the machine, no seconds, no memory figure, no email address, and never a secret's value, hash, line or fingerprint. `--no-run` reads a directory and writes nothing |
| `gitmole-feedback.json` | you | written only when you answer the five questions (`--feedback`): each answer's rule id, severity, whether it was true and whether you would act on it, plus gitmole's version and three bands (main language, file count, commit count). Nothing else, and nothing is sent |
| `activity.json` | change analysis | commits by weekday, hour and month; net lines per year; fix-commit count; per-author totals and monthly timeline; the sweeping commits left out of the tables, each marked whether `.git-blame-ignore-revs` declares it, the import commits left out with the history's total lines added, and how many declared commits the log holds; the oversized fixes left out of the fix counts, the tangled commits with a sample, and how many subjects end in a squash-merge suffix |
| `size.json` | scc | lines per language, COCOMO estimate |
| `secrets.json` | betterleaks | secret-looking strings across HEAD's history: rule, file, commit, line and fingerprint, with each value replaced by a short keyed hash |
| `dependencies.json` | osv-scanner | the lock files with their package counts, one row per package with a known vulnerability (ids, CVE aliases, score, fixed version, whether an advisory is a `MAL-` record, for a row from a pip requirement file its specifier and whether that pins one version, and for an npm row whether the lock installs it for running (`runtime`) and, from a pnpm lock, the direct dependency it is reached through (`via`)); on each lock file, the workspace members it pins and the entry points declared there, and the directories compose files build from, the database date and a digest of that snapshot; or a status: no lock files, no local database |
| `packages.json` | osv-scanner, with or without its database | every package the lock files pin, once per ecosystem, name and version, with the lock files that pin it and the licence a lock file declares; read by `--sbom`, not part of the report |
| `reverts.txt` | git | the commits whose message carries git revert's body line `This reverts commit <sha>`, each hash with its message body: the change analysis and the cohort count them as reverts whatever their subject says |
| `log.txt` | git | the numstat log export the change analysis reads, whitespace ignored, with each commit's `Co-authored-by` trailers behind its subject |
| `maat-revisions.csv` | change analysis | change frequency per file |
| `maat-plumbing.csv` | change analysis | the files the change log shows to be release plumbing by behaviour: twenty commits or more, four in five of them swapping no more than three lines for as many. Written only when there is such a file, and the `--json` export has its `plumbing` key only then |
| `maat-coupling.csv` | change analysis | files that change together, over logical changes (a ticket's commits, or one author's day) |
| `maat-soc.csv` | change analysis | sum of coupling per file: its co-changes with any other file, and how many files it often changes with, over logical changes |
| `maat-tests.csv` | change analysis | per production file, how many logical changes touched it and how many of those also touched a test file |
| `maat-doa.csv` | change analysis | degree of authorship per file and person: created it, own changes, others' changes, the degree undecayed and decayed, whether each counts as an author, and the decayed own and others' changes, from which the report recounts the degree without the coding tools |
| `maat-latenight.csv` | change analysis | per file, its revisions and how many were committed between midnight and 4 am in the author's own time zone |
| `maat-components.csv` | change analysis | coupling between components at one and two directory levels, over logical changes: shared changes, degree, average revisions; read by nothing since its rule was retired |
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

## Where each key and file is shown

Every top-level key of the `--json` export and every file of the output
directory has a home: a section of the report, with the tier that prints it
(`default`, `--full`, or `--section NAME` only), or `export only` when no
rendering prints it, or `retired` when gitmole no longer writes it. A test
builds the list of keys from an export and the list of files from an output
directory and fails when one has no row here, so a new key or file is given a
home in the change that adds it. Nothing is retired today; the one removal
is the `plumbing` key and its file when empty.

A key some rule reads is `export only` when its rows are printed nowhere:
the finding it leads to is in the Findings, the rows are not. A file whose
content is a key has that key's home.

| Key or file | Home |
|---|---|
| `activity` | People (default) · the header's `commits` and `left out` rows (default) · Activity (`--full`) · Timeline (`--full`) · export only: `by_hour` past the busiest hour, `tangled`, `oversized_fixes`, `squash_subjects`, `reverted` (the rules that read them are in the Findings) |
| `age` | Hotspots (`--full`), its `idle` column · Surviving code by year (`--full`), when no blame pass ran |
| `authors` | Hotspots (`--full`), its `authors` and `minors` columns · Watch list (`--full`), under each row |
| `change_risk` | Change risk (default), with `--risk` |
| `cohorts` | the header's `code` row (default) · Surviving code by year (`--full`) |
| `companions` | `--section companions` only · Watch list (`--full`), under a row that has one |
| `compare` | Since last report (default), with `--compare` |
| `components` | export only: read by nothing since its rule was retired |
| `coupling` | Change coupling (default) |
| `coverage` | the header's `files` and `code` rows (default) |
| `dependencies` | Supply chain (default), its `dependencies` row · Dependencies by lock file (`--full`) |
| `doa` | export only: read by the Truck factor rule |
| `entropy` | `--section hotspots` only, in its `--csv` (`periods`, `hcm`) · Watch list (`--full`), under a row that changed in many months |
| `envelope` | export only: what differs between two runs of one commit (paths, seconds, memory, the clone's unreachable objects) |
| `findings` | Findings (default) |
| `fix_history` | export only: read by the Bug magnets rule |
| `fixes` | Watch list (default), its `fixes` column · Hotspots (`--full`) |
| `functions` | Complex functions (default) |
| `hygiene` | Supply chain (default), its `checked, ok` row: the checks that ran with something to check and found nothing, by name actions, updates, lock files, bidi and mixed-script, binaries, licence and declared files, as many as fit three lines · Checks run (`--full`), one row for each check, passed or not |
| `latenight` | `--section hotspots` only, in its `--csv` (`late`) · Watch list (`--full`), under a row changed late at night |
| `meta` | the header (default) · the closing lines (default), from `steps` · Checks run (`--full`), one row for each step · People (default), from `identities` |
| `not_computed` | Findings (default), its last line |
| `osps` | OSPS Baseline (`--full`) · the closing lines (default), as the one number of the list of sections |
| `ownership` | Knowledge map (default) · Watch list (default), its `top author` column |
| `plumbing` | export only, and only when it has a row: read by the file classifier, which hides release files from Hotspots and the Watch list |
| `provenance` | Changed lines (`--full`) · Trailers (`--full`) · Agent surface (`--full`) |
| `revisions` | Watch list (default) · Hotspots (`--full`) |
| `secrets` | Supply chain (default), its `secrets` row, as counts · Secrets by rule (`--full`); never a value |
| `secrets_scanned` | Supply chain (default): `not scanned` in the verdict's place |
| `signing` | Supply chain (default), its `signing` row · Signing by year (`--full`) · export only: `by_identity` |
| `size` | the header (default) · Size by language (`--full`) · Hotspots (`--full`), its `lines` column |
| `soc` | Hotspots (`--full`), its `co-changes` column · Watch list (`--full`), under a row with many partners |
| `structure` | Checks run (`--full`): `resolved`, the share of imports that resolve to a tracked file, one row naming each language · Watch list (default), its `look at first` column · export only: the per-file rows, which the structure rules read |
| `surviving_by_identity` | People (default), its `surviving` column |
| `tests` | `--section hotspots` only, in its `--csv` (`n-sets`, `with-tests`) · Watch list (`--full`), under a row whose changes rarely came with a test |
| `theseus_authors` | People (default), its `surviving` column: the total the shares are of · export only: the per-author rows, which the ownership rules read |
| `tools` | People (default), in its caption |
| `trend` | Hotspots (`--full`), its `trend` column · Watch list (`--full`), under a row that grew |
| `watch` | Watch list (default) |
| `watch_backtest` | Watch list (default), the caption's `Check:` |
| `watch_by_component` | Watch list by component (`--full`) |
| `activity.json` | the `activity` key |
| `backtest/` | the `watch_backtest` key |
| `code-age.png` | export only: a plot, with `--plots`; the closing lines name it |
| `dependencies.json` | the `dependencies` key |
| `findings.json` | the `findings` key: the digest of Findings, Watch list and Supply chain, written out |
| `functions.csv` | the `functions` key |
| `gitmole-feedback.json` | export only: your answers to `--feedback` |
| `hygiene.json` | the `hygiene` key |
| `log.txt` | export only: the log the change analysis reads |
| `maat-age.csv` | the `age` key |
| `maat-arrivals.csv` | export only: read by the Truck factor rule, whose evidence carries the result as `new_since` |
| `maat-authors.csv` | the `authors` key |
| `maat-companions.csv` | the `companions` key |
| `maat-components.csv` | the `components` key |
| `maat-coupling.csv` | the `coupling` key |
| `maat-doa.csv` | the `doa` key |
| `maat-entity-ownership.csv` | the `ownership` key |
| `maat-entropy.csv` | the `entropy` key |
| `maat-fixes.csv` | the `fixes` key |
| `maat-latenight.csv` | the `latenight` key |
| `maat-plumbing.csv` | the `plumbing` key |
| `maat-revisions.csv` | the `revisions` key |
| `maat-soc.csv` | the `soc` key |
| `maat-tests.csv` | the `tests` key |
| `meta.json` | the `meta` key |
| `packages.json` | export only: read by `--sbom` |
| `provenance.json` | the `provenance` key |
| `reverts.txt` | export only: read by the change analysis, which counts them in `activity` |
| `run.log` | export only: every command run and its stderr |
| `secrets.json` | the `secrets` key |
| `signing.json` | the `signing` key |
| `size.json` | the `size` key |
| `structure.json` | the `structure` key |
| `survival.png` | export only: a plot, with `--plots`; the closing lines name it |
| `theseus/` | the `cohorts` key |
| `tree.txt` | export only: the tracked paths at HEAD, which the file classifier reads |
| `trend.json` | the `trend` key |
| `unreachable.json` | Supply chain (`--full`), its `secrets` row, as a count; in the export under `envelope` |

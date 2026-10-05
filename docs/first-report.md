# Reading your first report

What each part of `gitmole .` means, in plain words, and what to do first. [output.md](output.md) is the
full reference; back to [the README](https://github.com/antvinni/gitmole#readme).

**Header box.** The repository at a glance, with the branch and commit analysed in its title and one labelled
row per subject: `history` (commits, date span, people), `files` (how many are tracked, how many hold code and how
many are *scored*, the source files every ranking below is over), `code` (lines, languages, how old the surviving
code is), `commits` (how many are fixes or reverts), `left out` (commits that sweep the whole tree, which no count
below includes) and `signing`. A step that failed or timed out gets a `steps` row. The findings are counted by
severity in the title of the Findings box under it. When people commit (the busiest weekday and hour) is in
`--full`'s Activity table.

**Findings.** What the rules flagged, worst first. `✖` is critical, `▲` a warning, `●` a note. Each
finding states the facts, and the line starting `↳` names the file, area or person to start with.
The facts are the short form: how many, against which thresholds, and the worst one, with `(see Complex
functions)` where a table below lists the rest. `--full` names every subject.

- *"N more from the structure step, not labelled yet (2 warnings, 3 notes)"*: newer rules nobody has checked
  against real repositories yet. Treat them as leads, not verdicts; the Findings title's count includes them.

**Tables.** A table's title says how many of its rows are shown and what they are ranked by (*8 of 475, by
complexity*). The lines under it say what it hides (*188 functions hidden: 82 test, 60 generated, …*) and what its
words mean (*gone = no commit in the 12 months to …*); `--full` shows the hidden rows.

**Watch list.** The five source files where a change is most likely to need a fix: ranked by how often
each changed times how big it is (*changes × lines of code*). The other columns say what to look at there and do not change the rank:
`fixes` in the last six months, `top author` (the largest share of the file's lines one person added, with `gone`
after it when that person has stopped committing) and `look at first`, the function nested deepest or, failing
that, the most complex. `--full` adds each file's other reasons on a line under it.
The `Check:` under it replays the ranking six months back and counts how many of the files fixed since
its top held, next to the most changed files and a random pick, so you can see how far to trust it here.
With under a year of history it says *Check: none, too little history to backtest* instead: there is no list from six
months back to replay yet, so nothing here says how far to trust the ranking.

In a repository that is mostly documentation the header says so (*17 of 227 files scored*, *69% of tracked
lines are documentation, not ranked*) and a short **Most-changed documents** list follows: the watch list
ranks source files only, and that list is a plain count of changes, not a ranking of risk. A dim last line
in the findings (*truck factor not computed: 17 source files, needs 20*) names a measure the repository is
too small for, so its absence is not read as a pass.

**People.** Who commits, their share of the commits, and how much of the code in the tree today each
wrote (`surviving`; the caption says which step counted it, gitmole's own blame pass or, after `--plots`, git-of-theseus). Bots are left out and merges have their own column, aliases of one person
are merged (the title says for how many), and a coding tool credited by `Co-authored-by` trailers is left out; the caption counts the names
left out, the spellings with their aliases, the no-reply addresses they share and their commits (*1,324 = 1,327 identities
less 3 coding-tool names (7 with aliases, sharing 1 no-reply address, 32 commits)*; several names on one address are one assistant's
model versions). No report prints an email address, at any width or in Markdown; the JSON export keeps them.

**Knowledge map.** Each top-level area, how many lines were added there, and who wrote most of them.
The title says which files are counted: the default map counts the areas `in the tree now`, so a
directory that was moved or deleted does not make its author an owner of what remains, and `--full`
counts them `over every file in the history`; an area's lines and shares differ between the two for that reason.
`(gone)` marks an owner with no commits in the twelve months before the last commit (`--gone` changes
the twelve). When several people hold exactly the top share, as the co-authors of one squash commit do,
no owner is named: the cell reads `shared by 12 (8%)`, twelve people with 8% each. Lines a `Co-authored-by` trailer credits to a coding tool are not anyone's to own: an
`agents` column shows their share of the area instead.

**Timeline.** Commits per person per month over the last year: who is active now. A row needs five
commits in the months shown; the rest are counted under the table (`and 32 more`), and the top three
are listed whatever they committed. The People table keeps its rows the same way.

**Change coupling.** Pairs of files that change together, and the share of changes they share
(`together`). A pair with no obvious link is often a hidden dependency or copied code. When there is
one pair and the finding *Files that always change together* already names it with its share, the table is left out.

**Complex functions.** The functions with the most branches (`complexity`: cyclomatic, the function's branch points plus 1), with their
length and parameters. A `?` marks a span the parser may have misread, and `<anonymous>` a function
with no name of its own (a callback, a lambda): its file column gives the line to find it by. When no
function is both long and complex (complexity 15 or more over 100 lines or more, the brain-methods
rule) and the list is short enough to fit the table, the section is one line naming the highest
complexity, and `--full` has the table.

In a narrow terminal a long path keeps its file name and loses directories (`backend/…/routers/app.py`),
and a table too wide for the terminal leaves its rightmost columns out and says which under it;
`--markdown` always has every column.

## What to do first

1. Any `✖`: act on it now. A secret in history means rotating the credential, not just deleting the file.
2. Read each `▲` warning's `↳` line and decide yes or no; the advice names where to start.
3. Before changing a file at the top of the watch list, read it, starting at the function under `look at first`.
4. Where the knowledge map shows `(gone)` or one name, find out who can review changes there.

Everything else can wait. `gitmole . --full` shows every section and row, and
`gitmole . --markdown report.md` gives the same report as a document to share.

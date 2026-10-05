# Reading your first report

What each part of `gitmole .` means, in plain words, and what to do first. [output.md](output.md) is the
full reference; back to [the README](https://github.com/antvinni/gitmole#readme).

**Header box.** The repository at a glance: commits, date span, people, the branch and commit analysed,
size and languages, how many commits are fixes or reverts, how old the surviving code is and how many
commits are signed. Its last line counts the findings by severity; a step that failed or timed out is
named here too. When people commit (the busiest weekday and hour) is in `--full`'s Activity table.

**Findings.** What the rules flagged, worst first. `✖` is critical, `▲` a warning, `●` a note. Each
finding states the facts, and the line starting `↳` names the file, area or person to start with.

- *"N more from the structure step, not labelled yet (2 warnings, 3 notes)"*: newer rules nobody has checked
  against real repositories yet. Treat them as leads, not verdicts; the header's count includes them.

**Watch list.** The five source files where a change is most likely to need a fix: ranked by how often
each changed times how big it is. The reasons say what to look at there; they do not change the rank.
The caption under it replays the list six months back and counts how many of the files fixed since
were on it, next to a random list and the most changed files, so you can see how far to trust it here.
With under a year of history it says *too little history to backtest* instead: there is no list from six
months back to replay yet, so nothing here says how far to trust the ranking.

In a repository that is mostly documentation the header says so (*17 of 227 files scored*, *69% of tracked
lines are documentation, not ranked*) and a short **Most-changed documents** list follows: the watch list
ranks source files only, and that list is a plain count of revisions, not a ranking of risk. A dim last line
in the findings (*truck factor not computed: 17 source files, needs 20*) names a measure the repository is
too small for, so its absence is not read as a pass.

**People.** Who commits, their share of the commits, and how much of the code in the tree today each
wrote (`surviving code`; the caption says which step counted it, gitmole's own blame pass or, after `--plots`, git-of-theseus). Bots and merges are counted apart, aliases of one person
are merged, and a coding tool credited by `Co-authored-by` trailers is left out; the caption counts the names
left out and the no-reply addresses they sit on (several names on one address are one assistant's model versions).

**Knowledge map.** Each top-level area, how many lines were added there, and who wrote most of them.
The heading says which files are counted: the default map counts the `files in the tree now`, so a
directory that was moved or deleted does not make its author an owner of what remains, and `--full`
counts `every file in the history`; an area's lines and shares differ between the two for that reason.
`(gone)` marks an owner with no commits in the twelve months before the last commit (`--gone` changes
the twelve). When several people hold exactly the top share, as the co-authors of one squash commit do,
no owner is named: the cell reads `shared by 12 (8%)`, twelve people with 8% each. Lines a `Co-authored-by` trailer credits to a coding tool are not anyone's to own: an
`agents` column shows their share of the area instead.

**Timeline.** Commits per person per month over the last year: who is active now. A row needs five
commits in the months shown; the rest are counted under the table (`and 32 more`), and the top three
are listed whatever they committed. The People table keeps its rows the same way.

**Change coupling.** Pairs of files that change together, and the share of changes they share
(`degree`). A pair with no obvious link is often a hidden dependency or copied code. When there is
one pair and the watch list already shows it (`changes with … (59%)`), the table is left out.

**Complex functions.** The functions with the most branches (`ccn`, cyclomatic complexity), with their
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
3. Before changing a file at the top of the watch list, read it and its reasons.
4. Where the knowledge map shows `(gone)` or one name, find out who can review changes there.

Everything else can wait. `gitmole . --full` shows every section and row, and
`gitmole . --markdown report.md` gives the same report as a document to share.

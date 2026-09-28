# Reading your first report

What each part of `gitmole .` means, in plain words, and what to do first. [output.md](output.md) is the
full reference; back to [the README](https://github.com/antvinni/gitmole#readme).

**Header box.** The repository at a glance: commits, date span, people, the branch and commit analysed,
size and languages, when people commit, how many commits are fixes or reverts, how old the surviving code
is and how many commits are signed. Its last line counts the findings by
severity; a step that failed or timed out is named here too.

**Findings.** What the rules flagged, worst first. `✖` is critical, `▲` a warning, `●` a note. Each
finding states the facts, and the line starting `↳` names the file, area or person to start with.

- *"N more from the structure step, not labelled yet"*: newer rules nobody has checked against real
  repositories yet. Treat them as leads, not verdicts.

**Watch list.** The five source files where a change is most likely to need a fix: ranked by how often
each changed times how big it is. The reasons say what to look at there; they do not change the rank.
The caption under it replays the list six months back and counts how many of the files fixed since
were on it, next to a random list and the most changed files, so you can see how far to trust it here.

**People.** Who commits, their share of the commits, and how much of the code in the tree today each
wrote (`surviving code`, from git blame). Bots and merges are counted apart, and aliases of one person
are merged.

**Knowledge map.** Each top-level area, how many lines were added there, and who wrote most of them.
`(gone)` marks an owner with no commits in the twelve months before the last commit (`--gone` changes
the twelve).

**Timeline.** Commits per person per month over the last year: who is active now.

**Change coupling.** Pairs of files that change together, and the share of changes they share
(`degree`). A pair with no obvious link is often a hidden dependency or copied code.

**Complex functions.** The functions with the most branches (`ccn`, cyclomatic complexity), with their
length and parameters. A `?` marks a span the parser may have misread.

## What to do first

1. Any `✖`: act on it now. A secret in history means rotating the credential, not just deleting the file.
2. Read each `▲` warning's `↳` line and decide yes or no; the advice names where to start.
3. Before changing a file at the top of the watch list, read it and its reasons.
4. Where the knowledge map shows `(gone)` or one name, find out who can review changes there.

Everything else can wait. `gitmole . --full` shows every section and row, and
`gitmole . --markdown report.md` gives the same report as a document to share.

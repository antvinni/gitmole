# `--clean`: list what gitmole left behind and remove it on a yes

Date: 2026-09-17. Status: built the same day on branch polish-7-final-fixes.

## Goal

One command that shows every directory gitmole created and deletes them
after a single y/N question, and a run that no longer leaks its temporary
clone.

## What gitmole leaves behind

Two kinds of directory, both found today by looking, never by a ledger:

- **Output directories.** `analysis-<repo>/` next to a local clone or in the
  current directory for a remote target, `analysis-<owner>/<repo>/` for a
  portfolio, or wherever `--out` pointed. Every one holds a `meta.json`
  written by `run.save_meta`.
- **Temporary clones.** Every remote and portfolio run calls
  `tempfile.mkdtemp(prefix="gitmole-")` in the temp folder and never removes
  it. Each holds one full clone per repository analysed.

## Decisions

- **A flag, not a subcommand.** `gitmole --clean [DIR]`, next to `--no-run`
  and `--list-file-types`, which are the CLI's other modes. A word would
  collide with a folder named `clean`; the flag cannot. `target` becomes
  optional so `gitmole --clean` alone works; without `--clean`, a missing
  target is reported as `target required` with exit 2, as the other argument
  errors are.
- **Stateless.** `--clean` recomputes what it finds. No ledger, no state
  file. It looks in exactly two places:
  1. `<tmp>/gitmole-*` where `<tmp>` is `$TMPDIR`, or Python's default temp
     folder when it is unset: exactly where `mkdtemp(dir=os.environ.get("TMPDIR"))`
     put them.
  2. `DIR/analysis-*/` and, for portfolios, `DIR/analysis-*/*/`, where DIR is
     the optional target and defaults to the current directory. When DIR is
     itself a clone (it has a `.git` entry), its own default output directory
     next to it, `../analysis-<name>/`, is included too, so `gitmole --clean`
     from inside a clone finds the report `gitmole .` wrote. A candidate
     counts only if it holds `meta.json`, so a folder that merely shares the
     name is never listed. A portfolio directory `analysis-<owner>/` is listed
     once, as a whole, when every child that is a directory holds `meta.json`
     and every other entry is a `portfolio.*` export or a dotfile; otherwise
     its matching children are listed one by one.
- **Listing before asking.** A table, `Left behind`, with one row per
  directory: path, size, last modified date. Size is the sum of file sizes in
  the tree, shown as `1.2 MB`, `340 MB`, `2.1 GB`. Sizes are rounded, so the
  caption says what the total is. When nothing is found it prints
  `nothing to clean` and exits 0.
- **One question.** `Delete N directories (total)? [y/N] `. Only `y` or `yes`,
  case-insensitive, deletes; anything else, including an empty line or EOF,
  prints `kept` and exits 0. When the console is not a terminal the question
  is not asked: the list still prints, then
  `--clean needs a terminal to confirm; pass --yes to skip the question` and
  exit 2. `--yes` skips the question on a terminal too. `--yes` without
  `--clean` is an argument error, exit 2.
- **Deletion.** `shutil.rmtree` per listed path, best effort. A final line
  says `removed N directories (total)`; a path that could not be removed is
  named on its own line and the exit code is 1.
- **The leak stops at the source.** A remote run removes its temp parent when
  the run ends, on success, on a failed step, on `NoCommits` and on Ctrl-C,
  with `shutil.rmtree(..., ignore_errors=True)` in a `finally`. A portfolio
  run does the same for its parent after the last repository. Nothing reads
  the clone after the report: `--no-run` reads the output directory and
  `--risk` needs a local path. `--clean` still finds clones left by earlier
  versions and by runs killed with SIGKILL.
- **Other flags with `--clean`.** Any analysis flag alongside `--clean` is
  ignored, the way `--no-run` ignores the tool flags; there is no check for
  every combination. `--since` with `--clean` is not an error.
- **Docs.** README: the `--clean` option in the Run paragraph and one
  sentence in Safety that the temp clone is removed when the run ends.
  `docs/cli.md`: a `--clean [DIR]` and a `--yes` row in the options table, and
  the same sentence under Targets.

## Code layout

- `gitmole/clean.py`, new, pure functions with no console: `find(base, tmp)`
  returns the list of `(path, bytes, mtime)` in listing order (temp clones
  first, oldest first, then output directories sorted by path);
  `tree_size(path)`; `human(bytes)`; `remove(paths)` returns the paths that
  failed.
- `gitmole/cli.py`: `_clean(args, console, ui, err, ask)` builds the section
  with `render._section`, prints it with `render.print_section`, asks, and
  calls `clean.remove`. `main` gains an `ask` parameter, default
  `console.input`, so tests inject the answer. `_resolve_target` and
  `_portfolio` get the `finally`.

## Testing

Unit tests on `clean.find` with a temp tree: an `analysis-x` with
`meta.json` is found, one without is not, a portfolio is listed as a whole,
a partial portfolio lists children, `gitmole-*` in the temp folder is found,
`gitmole-*` under DIR is not. `clean.human` on the boundaries. CLI tests:
`--clean` on an empty directory prints `nothing to clean` and exits 0;
`--clean` with the answer `n` keeps everything; `y` removes and reports;
a non-terminal console without `--yes` lists, refuses and exits 2; `--yes`
on a non-terminal console deletes; `--yes` without `--clean` exits 2; no
target and no `--clean` exits 2 with `target required`. Leak tests: after a
remote run through the fake cloner the temp parent is gone, on success and
when the step fails; the same after a portfolio run.

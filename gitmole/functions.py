#!/usr/bin/env python3
"""Function-level metrics from lizard, over the tracked code files only.

Runs as its own process (a pipeline step) and drives lizard through its Python API rather
than its command line: the file list never touches a shell or a list file, the analysed
repository is never on sys.path, only files lizard has a reader for are measured, and the
CSV is streamed so a killed step still leaves what was measured. Duplicated blocks are
jscpd's job (duplicates.py); lizard's own finder kept a hash node per token and ran to gigabytes."""
from __future__ import annotations

import argparse
import csv
import os
import sys

import lizard

try:
    from . import blame, filetypes
except ImportError:  # run as a script: the package directory is sys.path[0]
    import blame
    import filetypes


def select_files(repo: str, ignore=(), types_spec: str = None) -> list:
    """Tracked text files lizard can parse. Without --file-types that is every language lizard
    knows (a superset of gitmole's default code list, e.g. Fortran); with it, the intersection."""
    types = filetypes.parse(types_spec)
    files = blame.text_files(repo, ignore) if types_spec is None else blame.code_files(repo, ignore, types)
    return [f for f in files if lizard.get_reader_for(f) is not None]


NAME_CAP = 200        # a deeply nested fixture gives lizard a dotted name of megabytes; nobody reads past this
LONG_NAME_CAP = 500


def _cut(text: str, cap: int) -> str:
    return text if len(text) <= cap else text[:cap - 1] + "…"


ANONYMOUS = "(anonymous)"   # lizard's name for a JavaScript function expression; a Go literal gets ""
SPARSE_LINES = 40           # a span this long...
SPARSE_SHARE = 0.25         # ...with under this share of code lines is more likely a mis-parse than a function

OPENS_FUNCTION = ("=>", "->", "func", "lambda")   # what a line that opens a nameless function holds: "func" covers "function"
NEARBY = (0, -1, 1, 2, 3, 4, 5)


def nameless(fn) -> bool:
    return fn.name in ("", ANONYMOUS)


def _opener(lines: list, fn) -> int | None:
    """The line near a nameless function's start that opens a function, or None. lizard puts an arrow
    whose body starts on the next line at the body's line, and a callback in a JSX attribute at the
    tag's line, so the start line is tried first, then the line before, then a few lines on."""
    for offset in NEARBY:
        n = fn.start_line + offset
        if 1 <= n <= len(lines) and any(m in lines[n - 1] for m in OPENS_FUNCTION):
            return n
    return None


def label(lines: list, fn) -> str:
    """What to call a function lizard could not name: the line it starts on, whitespace collapsed, in
    any language. `app.post("/api/x", async (req, res) => {` finds the callback; `(anonymous)` does not.
    When a nearby line opens a function and the start line does not, that line is the label."""
    if not nameless(fn) or not 1 <= fn.start_line <= len(lines):
        return ""
    n = _opener(lines, fn) or fn.start_line
    return _cut(" ".join(lines[n - 1].split()), NAME_CAP)


def suspect(lines: list, fn) -> str:
    """Why a span looks like a mis-parse, or "". lizard fails by losing its place (a template literal,
    JSX) and swallowing what follows into one function, so a swallowed span is long with little code
    in it, or holds a line that opens a block at the indentation of the function's own start: a
    sibling that should have ended it. A line that starts by closing a bracket (`}: Props) {`)
    continues the function's own signature and does not count. It also reads a JSX ternary as a
    nameless function: all code, all deeper than its start, and nothing near the start line opens a
    function."""
    if fn.length >= SPARSE_LINES and fn.nloc < SPARSE_SHARE * fn.length:
        return f"{fn.nloc} of {fn.length} lines are code"
    if nameless(fn) and 1 <= fn.start_line <= len(lines) and _opener(lines, fn) is None:
        return f"nothing opens a function within {max(NEARBY)} lines of line {fn.start_line}"
    span = lines[max(fn.start_line, 1) - 1:fn.end_line]
    if len(span) < 3:
        return ""
    depth = _indent(span[0])
    for number, line in enumerate(span[1:-1], start=fn.start_line + 1):
        text = line.rstrip()
        if text.endswith(("{", ":")) and _indent(text) <= depth and text.lstrip()[0] not in ")]}":
            return f"opens a block at line {number} no deeper than its own start"
    return ""


def _indent(line: str) -> int:
    return len(line) - len(line.lstrip())


def csv_row(info, fn, lines: list = ()) -> list:
    """The columns `lizard --csv` prints, then gitmole's own two: a label for nameless functions and
    why the span looks mis-parsed. Names are cut to what a table can show, so one pathological
    fixture cannot make the file unreadable."""
    name = _cut(fn.name, NAME_CAP)
    return [fn.nloc, fn.cyclomatic_complexity, fn.token_count, fn.parameter_count, fn.length,
            f"{name}@{fn.start_line}-{fn.end_line}@{info.filename}", info.filename, name, _cut(fn.long_name, LONG_NAME_CAP), fn.start_line, fn.end_line,
            label(lines, fn), suspect(lines, fn)]


def _lines(path: str) -> list:
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            return fh.read().splitlines()
    except OSError:
        return []


def keep_newlines(tokens, reader):
    """lizard's own preprocessing, after splitting whitespace tokens that hold newlines into bare ones.
    lizard 1.24 drops any whitespace token but "\\n" there, and its JSX tokenizer hands it the newline
    before a child element joined with the indentation after it: one line lost per child, so every
    function after a JSX block in a .tsx file reports lines before its own."""
    def split(tokens):
        for t in tokens:
            if t != "\n" and t.isspace() and "\n" in t:
                for _ in range(t.count("\n")):
                    yield "\n"
            else:
                yield t
    return lizard.preprocessing(split(tokens), reader)


def extensions() -> list:
    """lizard's metric extensions, with keep_newlines in place of its preprocessing."""
    return [keep_newlines if e is lizard.preprocessing else e for e in lizard.get_extensions([])]


def analyze(files: list, procs: int, exts: list):
    """lizard.analyze_files without its extension bookkeeping: per-file analysis over `procs` workers."""
    return lizard.map_files_to_analyzer(files, lizard.FileAnalyzer(exts), procs)


def measure(repo: str, files: list, out: str, procs: int) -> int:
    """Stream functions.csv while lizard runs. Returns 0, or 1 when lizard gave up on a file (whatever
    was measured by then stays on disk)."""
    exts = extensions()
    rc = 0
    cwd = os.getcwd()
    os.chdir(repo)   # lizard opens the paths as given; relative ones keep the CSV repo-relative
    try:
        with open(os.path.join(out, "functions.csv"), "w", encoding="utf-8", newline="") as fh:
            writer = csv.writer(fh, quoting=csv.QUOTE_NONNUMERIC)
            try:
                for info in analyze(files, procs, exts):
                    lines = _lines(info.filename) if info.function_list else []
                    for fn in info.function_list:
                        writer.writerow(csv_row(info, fn, lines))
                    fh.flush()
            except Exception as e:  # lizard re-raises its parse failures; keep what we have
                print(f"lizard stopped: {e!r}", file=sys.stderr)
                rc = 1
    finally:
        os.chdir(cwd)
    return rc


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("repo")
    p.add_argument("out")
    p.add_argument("--procs", type=int, default=1)
    p.add_argument("--ignore", action="append", default=[])
    p.add_argument("--types", default=None, help="file types spec as for gitmole --file-types")
    args = p.parse_args(argv)
    files = select_files(args.repo, args.ignore, args.types)
    return measure(os.path.abspath(args.repo), files, os.path.abspath(args.out), max(1, args.procs))


if __name__ == "__main__":
    sys.exit(main())

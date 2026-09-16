#!/usr/bin/env python3
"""Function-level metrics and duplicated blocks from lizard, over the tracked code files only.

Runs as its own process (a pipeline step) and drives lizard through its Python API rather
than its command line: the file list never touches a shell or a list file, the analysed
repository is never on sys.path, only files lizard has a reader for are measured, and the
CSV is streamed so a killed step still leaves what was measured."""
from __future__ import annotations

import argparse
import csv
import os
import sys

import lizard
from lizard_ext.lizardduplicate import LizardExtension as Duplicates

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


def csv_row(info, fn) -> list:
    """The columns `lizard --csv` prints, so the loader does not care which produced the file."""
    return [fn.nloc, fn.cyclomatic_complexity, fn.token_count, fn.parameter_count, fn.length,
            f"{fn.name}@{fn.start_line}-{fn.end_line}@{info.filename}", info.filename, fn.name, fn.long_name, fn.start_line, fn.end_line]


def write_duplicates(dup: Duplicates, fh) -> None:
    """The layout `lizard -Eduplicate` prints, snippets in a stable order."""
    fh.write("Duplicates\n===================================\n")
    for block in dup.get_duplicates():
        fh.write("Duplicate block:\n--------------------------\n")
        for s in sorted(block, key=lambda s: (s.file_name, s.start_line)):
            fh.write(f"{s.file_name}:{s.start_line} ~ {s.end_line}\n")
        fh.write("^^^^^^^^^^^^^^^^^^^^^^^^^^\n\n")
    fh.write(f"Total duplicate rate: {(dup.duplicate_rate() or 0.0) * 100:.2f}%\n")
    fh.write(f"Total unique rate: {(dup.unique_rate() or 0.0) * 100:.2f}%\n")


def measure(repo: str, files: list, out: str, procs: int) -> int:
    """Stream functions.csv while lizard runs, then write duplicates.txt. Returns 0, or 1 when
    lizard gave up on a file (whatever was measured by then stays on disk)."""
    exts = lizard.get_extensions(["duplicate"])   # lizard's metric extensions plus the duplicate finder
    dup = next(e for e in exts if isinstance(e, Duplicates))
    rc = 0
    cwd = os.getcwd()
    os.chdir(repo)   # lizard opens the paths as given; relative ones keep the CSV repo-relative
    try:
        with open(os.path.join(out, "functions.csv"), "w", encoding="utf-8", newline="") as fh:
            writer = csv.writer(fh, quoting=csv.QUOTE_NONNUMERIC)
            try:
                for info in lizard.analyze_files(files, threads=procs, exts=exts):
                    for fn in info.function_list:
                        writer.writerow(csv_row(info, fn))
                    fh.flush()
            except Exception as e:  # lizard re-raises its parse failures; keep what we have
                print(f"lizard stopped: {e!r}", file=sys.stderr)
                rc = 1
        with open(os.path.join(out, "duplicates.txt"), "w", encoding="utf-8") as fh:
            write_duplicates(dup, fh)
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

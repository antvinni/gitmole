#!/usr/bin/env python3
"""Function-level metrics and duplicated blocks from lizard, over the tracked code files only.

Runs as its own process (a pipeline step): lists the tracked source files the way the
blame pass does, hands them to lizard through a list file, and splits lizard's single
pass into functions.csv and duplicates.txt."""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile

try:
    from . import blame, filetypes
except ImportError:  # run as a script: the package directory is sys.path[0]
    import blame
    import filetypes

HEADING = "Duplicates"


def split_output(text: str) -> tuple:
    """(csv rows, duplicate report): lizard prints the CSV first, then the extension's block."""
    lines = text.splitlines(keepends=True)
    for i, line in enumerate(lines):
        if line.rstrip("\r\n") == HEADING:
            return "".join(lines[:i]), "".join(lines[i:])
    return text, ""


def measure(repo: str, files: list, procs: int) -> str:
    if not files:
        return ""
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8", errors="surrogateescape") as fh:
        fh.write("".join(f + "\n" for f in files))
        listing = fh.name
    try:
        proc = subprocess.run([sys.executable, "-m", "lizard", "--csv", "-Eduplicate", "--no-gitignore", "-t", str(procs), "-f", listing],
                              cwd=repo, stdout=subprocess.PIPE, stderr=sys.stderr, text=True, errors="replace")
    finally:
        os.unlink(listing)
    if proc.returncode != 0:
        raise RuntimeError(f"lizard exited {proc.returncode}")
    return proc.stdout


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("repo")
    p.add_argument("out")
    p.add_argument("--procs", type=int, default=1)
    p.add_argument("--ignore", action="append", default=[])
    p.add_argument("--types", default=None, help="file types spec as for gitmole --file-types")
    args = p.parse_args(argv)
    types = filetypes.parse(args.types)
    files = blame.code_files(args.repo, ignore=args.ignore, types=types)
    try:
        csv, dup = split_output(measure(args.repo, files, args.procs))
    except RuntimeError as e:
        print(str(e), file=sys.stderr)
        return 1
    with open(os.path.join(args.out, "functions.csv"), "w", encoding="utf-8") as fh:
        fh.write(csv)
    with open(os.path.join(args.out, "duplicates.txt"), "w", encoding="utf-8") as fh:
        fh.write(dup)
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""The repository as it was at a cut-off date, for checking the watch list against what came after.

Runs as a pipeline step: `python -m gitmole.backtest OUT_DIR --until T [--repo DIR]`, from inside
the repository. Reruns the change analysis over OUT_DIR/log.txt with the window ending at T and T as
the reference date, exports the tree at the last commit before T and runs scc on it, and writes it
all under OUT_DIR/backtest/ with a meta.json the loader accepts."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile

from . import filetypes, load, maat


def rev_before(repo: str, date: str):
    proc = subprocess.run(["git", "rev-list", "-1", f"--before={date}T00:00:00", "HEAD"], cwd=repo, capture_output=True, text=True)
    return proc.stdout.strip() or None


def size_at(repo: str, rev: str) -> str:
    """scc's --by-file JSON over the tree at rev."""
    with tempfile.TemporaryDirectory(prefix="gitmole-backtest-") as tmp:
        archive = subprocess.run(["git", "archive", rev], cwd=repo, capture_output=True, check=True)
        subprocess.run(["tar", "-x", "-C", tmp], input=archive.stdout, check=True)
        return subprocess.run(["scc", "--by-file", "--format", "json"], cwd=tmp, capture_output=True, text=True, check=True).stdout


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("out")
    p.add_argument("--until", required=True)
    p.add_argument("--repo", default=".")
    args = p.parse_args(argv)
    try:
        until = maat.validate_now(args.until)
    except ValueError as e:
        print(f"backtest: {e}", file=sys.stderr)
        return 2
    log_path = os.path.join(args.out, "log.txt")
    meta = json.loads(load._read(args.out, "meta.json") or "{}")
    if not meta or not os.path.exists(log_path):
        print("backtest: meta.json and log.txt are needed", file=sys.stderr)
        return 2
    rev = rev_before(args.repo, until)
    if not rev:
        print(f"backtest: no commit before {until}", file=sys.stderr)
        return 2
    sub = os.path.join(args.out, "backtest")
    os.makedirs(sub, exist_ok=True)
    types = filetypes.parse(meta.get("file_types"))
    maat.write_all(log_path, sub, os.path.join(args.out, "meta.json") if "aliases" in meta else None, types, now=until, until=until)
    with open(os.path.join(sub, "size.json"), "w", encoding="utf-8") as fh:
        fh.write(size_at(args.repo, rev))
    with open(os.path.join(sub, "meta.json"), "w", encoding="utf-8") as fh:
        json.dump({"now": until, "last_date": until, "file_types": meta.get("file_types"), "aliases": meta.get("aliases", {})}, fh)
    return 0


if __name__ == "__main__":
    sys.exit(main())

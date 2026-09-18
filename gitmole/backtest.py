#!/usr/bin/env python3
"""The repository as it was at a cut-off date, for checking the watch list against what came after.

Runs as a pipeline step: `python -m gitmole.backtest OUT_DIR --until T [--repo DIR]`, from inside
the repository. Reruns the change analysis over OUT_DIR/log.txt with the window ending at T and T as
the reference date, exports the tree at the last commit before T and runs scc on it, and writes it
all under OUT_DIR/backtest/ with a meta.json the loader accepts.

The last commit before T is chosen by committer date (trend.rev_before with end_of_day=False),
since "the tree as of T" is a committer-date notion. The change analysis windows commits by author
date instead, so the two only disagree for commits that were rebased or cherry-picked after their
original authoring."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile

from . import filetypes, load, maat, trend


def snapshot_at(repo: str, rev: str, out_dir: str) -> tuple:
    """The tree at rev, measured and classified as it was then: scc's --by-file JSON, the generated files
    and the vendored paths. Exported through a temporary index so no archive is held in memory and
    export-ignore attributes do not thin the tree; the same index lets git check-attr read that tree's
    .gitattributes, so the classification is the cut-off's, not HEAD's.

    The tree is written under `out_dir`, not the system temp directory: a SIGKILL cannot run the
    cleanup, and a checkout left next to the report is one the next run clears away."""
    with tempfile.TemporaryDirectory(dir=out_dir, prefix=".backtest-tree-") as tmp:
        tree = os.path.join(tmp, "tree")
        os.makedirs(tree)
        env = dict(os.environ, GIT_INDEX_FILE=os.path.join(tmp, "index"))
        subprocess.run(["git", "read-tree", rev], cwd=repo, env=env, check=True, capture_output=True, text=True)
        subprocess.run(["git", "checkout-index", "-a", f"--prefix={tree}/"], cwd=repo, env=env, check=True, capture_output=True, text=True)
        size = subprocess.run(["scc", "--by-file", "--format", "json"], cwd=tree, capture_output=True, text=True, check=True).stdout
        # the text files of that tree, as blame.text_files lists HEAD's: git grep prints "rev:path"
        proc = subprocess.run([*filetypes.GIT, "grep", "-I", "--name-only", "-z", "-e", "", rev], cwd=repo, capture_output=True)
        if proc.returncode not in (0, 1):   # 1 is grep's "no match" (an empty tree), not a failure
            raise subprocess.CalledProcessError(proc.returncode, proc.args, proc.stdout, proc.stderr)
        paths = sorted(p.decode("utf-8", "surrogateescape").split(":", 1)[1] for p in proc.stdout.split(b"\0") if p)
        attrs = filetypes.attributes(repo, paths, cached=True, env=env)
        return size, filetypes.generated_files(tree, paths, attrs), filetypes.vendored_paths(tree, paths, attrs)


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
    try:
        rev = trend.rev_before(args.repo, until, end_of_day=False)
    except RuntimeError as e:
        print(f"backtest: {e}", file=sys.stderr)
        return 2
    if not rev:
        print(f"backtest: no commit before {until}", file=sys.stderr)
        return 2
    sub = os.path.join(args.out, "backtest")
    os.makedirs(sub, exist_ok=True)
    types = filetypes.parse(meta.get("file_types"))
    maat.write_all(log_path, sub, os.path.join(args.out, "meta.json") if "aliases" in meta else None, types, now=until, until=until)
    try:
        size, generated, vendored = snapshot_at(args.repo, rev, args.out)
    except subprocess.CalledProcessError as e:
        first = ((e.stderr or "").strip().splitlines() or [f"{' '.join(e.cmd)} exited {e.returncode}"])[0]
        print(f"backtest: {first}", file=sys.stderr)
        return 2
    with open(os.path.join(sub, "size.json"), "w", encoding="utf-8") as fh:
        fh.write(size)
    with open(os.path.join(sub, "meta.json"), "w", encoding="utf-8") as fh:
        json.dump({"now": until, "last_date": until, "file_types": meta.get("file_types"), "aliases": meta.get("aliases", {}),
                   "generated": generated, "vendored": vendored}, fh)
    return 0


if __name__ == "__main__":
    sys.exit(main())

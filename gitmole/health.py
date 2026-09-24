"""git-sizer over the commit, not the clone.

gitmole runs this as the git-sizer step: `python3 health.py`, from inside the repository, its stdout
being repo-health.txt. git-sizer measures everything any reference reaches, so a clone that carries a
thousand remote-tracking branches reports blob totals and largest objects that another clone of the
same commit does not have, and the report's findings then describe the clone. The 0.35.0 record
caught this on react: two `repo_health` findings that a clone made three days earlier lacked. A
finding must describe the commit, so git-sizer is pointed at a throwaway repository that borrows the
clone's objects (objects/info/alternates: nothing is copied) and holds exactly one reference, at
HEAD's commit. Whatever is reachable from that reference is the commit's history; whatever is not is
the clone's business and stays out. The reference count and the annotated-tag count are the clone's
too, and so are no longer reported.

The one reference is named after HEAD, so a footnote reads `HEAD^{tree}` in every clone rather than
`refs/heads/main^{tree}` in one and `refs/remotes/origin/x^{tree}` in another."""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile

REF = "refs/heads/HEAD"   # git accepts it from update-ref; `git branch` would not, and nobody branches here


def _git(*args, cwd=None) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)


def scratch(repo: str, into: str) -> str:
    """A repository under `into` that reads `repo`'s objects and has one reference, at `repo`'s HEAD.
    ValueError when `repo` has no commit to point at."""
    head = _git("rev-parse", "--verify", "--quiet", "HEAD^{commit}", cwd=repo)
    if head.returncode != 0 or not head.stdout.strip():
        raise ValueError("no commit at HEAD")
    objects = _git("rev-parse", "--path-format=absolute", "--git-path", "objects", cwd=repo).stdout.strip()
    if not objects:   # git before 2.31 has no --path-format; the path is relative to the working tree then
        objects = os.path.join(repo, _git("rev-parse", "--git-path", "objects", cwd=repo).stdout.strip())
    dest = os.path.join(into, "health")
    _git("init", "-q", dest)
    os.makedirs(os.path.join(dest, ".git", "objects", "info"), exist_ok=True)
    with open(os.path.join(dest, ".git", "objects", "info", "alternates"), "w", encoding="utf-8") as fh:
        fh.write(objects + "\n")
    _git("update-ref", REF, head.stdout.strip(), cwd=dest)
    return dest


def main(argv=None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if args:
        print("usage: health.py  (run from inside the repository; git-sizer's report is written to stdout)", file=sys.stderr)
        return 2
    repo = os.getcwd()
    tmp = tempfile.mkdtemp(prefix="gitmole-health-")
    try:
        try:
            dest = scratch(repo, tmp)
        except ValueError as e:
            print(f"health.py: {e}", file=sys.stderr)
            return 2
        # stderr is inherited, so git-sizer's own messages land in run.log as before
        proc = subprocess.run(["git-sizer", "--verbose", "--no-progress"], cwd=dest, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE)
        text = proc.stdout.decode("utf-8", "replace").replace(REF, "HEAD")
        sys.stdout.write(text)
        sys.stdout.flush()
        return proc.returncode
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())

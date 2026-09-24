"""health.py: git-sizer over the commit, not the clone."""
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

from gitmole import health

SCRIPT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "gitmole", "health.py")


def _git(*args, cwd):
    env = dict(os.environ, GIT_CONFIG_GLOBAL="/dev/null", GIT_CONFIG_SYSTEM="/dev/null", GIT_AUTHOR_NAME="Ann", GIT_AUTHOR_EMAIL="a@x",
               GIT_COMMITTER_NAME="Ann", GIT_COMMITTER_EMAIL="a@x", GIT_AUTHOR_DATE="2026-01-05T10:00:00+00:00", GIT_COMMITTER_DATE="2026-01-05T10:00:00+00:00")
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, env=env, text=True).stdout.strip()


def _repo_with_a_heavy_side_branch(d: str) -> str:
    """main has one small file; a branch `heavy`, not reachable from main, carries a 3 MB blob and a
    remote-tracking ref points at it too, the way a clone with many fetched branches looks."""
    _git("init", "-q", "-b", "main", cwd=d)
    with open(os.path.join(d, "a.py"), "w") as fh:
        fh.write("x = 1\n")
    _git("add", "-A", cwd=d)
    _git("commit", "-q", "-m", "one", cwd=d)
    _git("switch", "-q", "-c", "heavy", cwd=d)
    with open(os.path.join(d, "big.bin"), "wb") as fh:
        fh.write(os.urandom(3_000_000))
    _git("add", "-A", cwd=d)
    _git("commit", "-q", "-m", "heavy", cwd=d)
    heavy = _git("rev-parse", "HEAD", cwd=d)
    _git("update-ref", "refs/remotes/origin/heavy", heavy, cwd=d)
    _git("switch", "-q", "main", cwd=d)
    return heavy


class Scratch(unittest.TestCase):
    def test_one_reference_at_head_borrowing_the_clones_objects(self):
        with tempfile.TemporaryDirectory() as d:
            repo, tmp = os.path.join(d, "repo"), os.path.join(d, "tmp")
            os.makedirs(repo)
            os.makedirs(tmp)
            _repo_with_a_heavy_side_branch(repo)
            head = _git("rev-parse", "HEAD", cwd=repo)
            dest = health.scratch(repo, tmp)
            self.assertEqual(_git("for-each-ref", "--format=%(objectname) %(refname)", cwd=dest), f"{head} {health.REF}",
                             "exactly one reference, at the clone's HEAD")
            self.assertEqual(_git("cat-file", "-t", head, cwd=dest), "commit", "the objects are read through alternates, not copied")
            self.assertEqual(os.listdir(os.path.join(dest, ".git", "objects", "pack")), [], "nothing was copied")

    def test_a_detached_head_is_fine_and_an_empty_repository_is_refused(self):
        with tempfile.TemporaryDirectory() as d:
            repo, tmp = os.path.join(d, "repo"), os.path.join(d, "tmp")
            os.makedirs(repo)
            os.makedirs(tmp)
            _repo_with_a_heavy_side_branch(repo)
            _git("switch", "-q", "--detach", "HEAD", cwd=repo)
            head = _git("rev-parse", "HEAD", cwd=repo)
            self.assertIn(head, _git("for-each-ref", cwd=health.scratch(repo, tmp)))
        with tempfile.TemporaryDirectory() as d:
            _git("init", "-q", cwd=d)
            with self.assertRaises(ValueError):
                health.scratch(d, d)


@unittest.skipUnless(shutil.which("git-sizer"), "git-sizer is not installed")
class Script(unittest.TestCase):
    def test_the_side_branch_is_the_clones_business_and_the_footnotes_say_head(self):
        with tempfile.TemporaryDirectory() as d:
            _repo_with_a_heavy_side_branch(d)
            p = subprocess.run([sys.executable, SCRIPT], cwd=d, capture_output=True, text=True)
            self.assertEqual(p.returncode, 0, p.stderr)
            self.assertNotIn("big.bin", p.stdout, "a blob no reference at HEAD reaches is not the commit's")
            self.assertNotIn("refs/", p.stdout, "the one reference is named HEAD, whatever branch the clone is on")
            self.assertIn("HEAD", p.stdout)
            whole = subprocess.run(["git-sizer", "--verbose", "--no-progress"], cwd=d, capture_output=True, text=True).stdout
            self.assertIn("big.bin", whole, "git-sizer alone would have counted it")
            self.assertEqual(p.stdout.count("Count"), whole.count("Count"), "the same table, over fewer objects")

    def test_arguments_are_refused_and_an_empty_repository_exits_2(self):
        p = subprocess.run([sys.executable, SCRIPT, "extra"], capture_output=True, text=True)
        self.assertEqual(p.returncode, 2)
        with tempfile.TemporaryDirectory() as d:
            _git("init", "-q", cwd=d)
            p = subprocess.run([sys.executable, SCRIPT], cwd=d, capture_output=True, text=True)
            self.assertEqual((p.returncode, p.stdout), (2, ""))
            self.assertIn("no commit at HEAD", p.stderr)


if __name__ == "__main__":
    unittest.main()

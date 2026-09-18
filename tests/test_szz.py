import os
import subprocess
import tempfile
import unittest

from gitmole import szz


def make_repo(d):
    """A file with a bug planted in February, an unrelated edit in March, the fix in April; a test
    file the fix also touches; and an insert-only fix in May."""
    def git(*args, date):
        env = dict(os.environ, GIT_CONFIG_GLOBAL="/dev/null", GIT_CONFIG_SYSTEM="/dev/null", GIT_AUTHOR_NAME="Ann", GIT_AUTHOR_EMAIL="a@x",
                   GIT_COMMITTER_NAME="Ann", GIT_COMMITTER_EMAIL="a@x", GIT_AUTHOR_DATE=f"{date}T00:00:00", GIT_COMMITTER_DATE=f"{date}T00:00:00")
        subprocess.run(["git", *args], cwd=d, check=True, capture_output=True, env=env)

    def write(path, text):
        os.makedirs(os.path.dirname(os.path.join(d, path)) or d, exist_ok=True)
        with open(os.path.join(d, path), "w") as fh:
            fh.write(text)
    git("init", "-q", "-b", "main", date="2025-01-01")
    write("core/f.py", "a\nb\nc\nd\ne\n")
    write("core/g.py", "x\ny\n")
    write("tests/test_f.py", "t\n")
    git("add", "-A", date="2025-01-01")
    git("commit", "-q", "-m", "one", date="2025-01-01")
    write("core/f.py", "a\nB\nc\nd\ne\n")
    git("commit", "-q", "-am", "plant the bug", date="2025-02-01")
    write("core/f.py", "a\nB\nc\nD\ne\nf\n")
    write("core/g.py", "x\nY\n")
    git("commit", "-q", "-am", "change d, add f, touch g", date="2025-03-01")
    write("core/f.py", "a\nb\nc\nD\ne\nf\n")
    write("tests/test_f.py", "t\nu\n")
    git("commit", "-q", "-am", "fix: b", date="2025-04-01")
    write("core/g.py", "x\nY\nz\n")
    git("commit", "-q", "-am", "fix: add z", date="2025-05-01")
    return {line.split()[1]: line.split()[0] for line in
            subprocess.run(["git", "log", "--format=%H %s", "HEAD"], cwd=d, capture_output=True, text=True, check=True).stdout.splitlines()
            if len(line.split()) > 1}


class DeletedRanges(unittest.TestCase):
    def test_the_parent_side_lines_a_fix_removed_or_changed_per_modified_file(self):
        with tempfile.TemporaryDirectory() as d:
            by = make_repo(d)
            self.assertEqual(szz.deleted_ranges(d, by["fix:"]), {"core/f.py": [(2, 1)], "tests/test_f.py": []},
                             "line 2 of the parent's f.py was changed; the test file only gained a line")
            self.assertEqual(szz.deleted_ranges(d, by["plant"]), {"core/f.py": [(2, 1)]})
            self.assertEqual(szz.deleted_ranges(d, by["change"]), {"core/f.py": [(4, 1)], "core/g.py": [(2, 1)]}, "an added line has no parent side")


class BugInducing(unittest.TestCase):
    def test_the_most_recent_commit_blamed_for_a_fixs_deleted_lines_with_its_files(self):
        with tempfile.TemporaryDirectory() as d:
            by = make_repo(d)
            found = szz.bug_inducing(d, by["fix:"])
            self.assertEqual(found, {"commit": by["plant"], "date": "2025-02-01", "files": ["core/f.py"]},
                             "the fix removed line 2, which the February commit wrote; the March commit is not blamed")
            self.assertIsNone(szz.bug_inducing(d, by["add"]), "an insert-only fix blames nothing: R-SZZ finds nothing for it")

    def test_files_the_caller_excludes_are_not_candidates(self):
        with tempfile.TemporaryDirectory() as d:
            by = make_repo(d)
            self.assertIsNone(szz.bug_inducing(d, by["fix:"], exclude=lambda p: p.startswith("core/")))

    def test_the_most_recent_of_several_candidates_wins(self):
        # R-SZZ: of the commits a fix's deleted lines blame to, only the latest is kept; Rosa et al. measured
        # that rule at precision 0.66 against 0.39 for keeping them all
        with tempfile.TemporaryDirectory() as d:
            by = make_repo(d)
            def git(*args, date):
                env = dict(os.environ, GIT_CONFIG_GLOBAL="/dev/null", GIT_CONFIG_SYSTEM="/dev/null", GIT_AUTHOR_NAME="Ann", GIT_AUTHOR_EMAIL="a@x",
                           GIT_COMMITTER_NAME="Ann", GIT_COMMITTER_EMAIL="a@x", GIT_AUTHOR_DATE=f"{date}T00:00:00", GIT_COMMITTER_DATE=f"{date}T00:00:00")
                subprocess.run(["git", *args], cwd=d, check=True, capture_output=True, env=env)
            with open(os.path.join(d, "core/f.py"), "w") as fh:
                fh.write("a\nb\nc\nd\ne\nF\n")   # rewrites line 4 (March's D) and line 6 (March's f) and line 1 (January's a)... only b and F
            git("commit", "-q", "-am", "fix: d and f", date="2025-06-01")
            fix = subprocess.run(["git", "rev-parse", "HEAD"], cwd=d, capture_output=True, text=True).stdout.strip()
            found = szz.bug_inducing(d, fix)
            self.assertEqual((found["commit"], found["date"], found["files"]), (by["change"], "2025-03-01", ["core/f.py"]))


class Labels(unittest.TestCase):
    def test_a_csv_of_buggy_commits_with_or_without_paths(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "labels.csv")
            with open(path, "w") as fh:
                fh.write("commit_id,project,buggy\nabc1234,x,True\ndef5678,x,False\n0123abc,x,1\n")
            self.assertEqual(szz.read_labels(path), {"abc1234": None, "0123abc": None}, "ApacheJIT's shape: a buggy flag per commit")
            with open(path, "w") as fh:
                fh.write("commit,path\nabc1234,src/a.py\nabc1234,src/b.py\n")
            self.assertEqual(szz.read_labels(path), {"abc1234": ["src/a.py", "src/b.py"]}, "Defectors' shape: the files a buggy commit made buggy")
            with open(path, "w") as fh:
                fh.write("abc1234\n0123abc\n")
            self.assertEqual(szz.read_labels(path), {"abc1234": None, "0123abc": None}, "a bare list of hashes")


if __name__ == "__main__":
    unittest.main()

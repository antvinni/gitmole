import os
import subprocess
import tempfile
import unittest

from gitmole import functions


def make_repo(d):
    def git(*args):
        e = dict(os.environ, GIT_CONFIG_GLOBAL="/dev/null", GIT_CONFIG_SYSTEM="/dev/null",
                 GIT_AUTHOR_NAME="Ann", GIT_AUTHOR_EMAIL="a@x", GIT_COMMITTER_NAME="Ann", GIT_COMMITTER_EMAIL="a@x")
        subprocess.run(["git", *args], cwd=d, check=True, capture_output=True, env=e)
    git("init", "-q")
    os.makedirs(os.path.join(d, "vendor"))
    with open(os.path.join(d, "app.py"), "w") as fh:
        fh.write("def tracked(a, b):\n    if a:\n        return b\n    return a\n")
    with open(os.path.join(d, "vendor", "lib.py"), "w") as fh:
        fh.write("def vendored():\n    return 1\n")
    with open(os.path.join(d, "notes.md"), "w") as fh:
        fh.write("def not_code():\n    pass\n")
    with open(os.path.join(d, "page.js"), "w") as fh:
        fh.write("function scripted(a) {\n  if (a) { return 1; }\n  return 0;\n}\n")
    git("add", "-A")
    git("commit", "-q", "-m", "one")
    with open(os.path.join(d, "untracked.py"), "w") as fh:
        fh.write("def untracked():\n    return 2\n")


class FunctionsScript(unittest.TestCase):
    def test_measures_tracked_code_files_only_and_writes_both_outputs(self):
        with tempfile.TemporaryDirectory() as d:
            make_repo(d)
            out = os.path.join(d, "out")
            os.makedirs(out)
            rc = functions.main([d, out, "--procs", "1", "--ignore", "vendor/**"])
            self.assertEqual(rc, 0)
            with open(os.path.join(out, "functions.csv")) as fh:
                csv = fh.read()
            with open(os.path.join(out, "duplicates.txt")) as fh:
                dup = fh.read()
        self.assertIn('"tracked"', csv)
        self.assertNotIn("untracked", csv, "not tracked by git")
        self.assertNotIn("vendored", csv, "--ignore applies")
        self.assertNotIn("not_code", csv, "markdown is not code")
        self.assertNotIn("Duplicates", csv, "the two outputs are split apart")
        self.assertIn("Total duplicate rate", dup)

    def test_file_types_restrict_what_is_measured(self):
        with tempfile.TemporaryDirectory() as d:
            make_repo(d)
            out = os.path.join(d, "out")
            os.makedirs(out)
            rc = functions.main([d, out, "--procs", "1", "--types", "js"])
            with open(os.path.join(out, "functions.csv")) as fh:
                csv = fh.read()
        self.assertEqual(rc, 0)
        self.assertIn("scripted", csv)
        self.assertNotIn("tracked", csv)

    def test_no_code_files_still_writes_empty_outputs(self):
        with tempfile.TemporaryDirectory() as d:
            make_repo(d)
            out = os.path.join(d, "out")
            os.makedirs(out)
            rc = functions.main([d, out, "--procs", "1", "--ignore", "*.py", "--ignore", "*.js"])
            self.assertEqual(rc, 0)
            self.assertTrue(os.path.exists(os.path.join(out, "functions.csv")))
            self.assertTrue(os.path.exists(os.path.join(out, "duplicates.txt")))
            with open(os.path.join(out, "functions.csv")) as fh:
                self.assertEqual(fh.read().strip(), "")


class SplitOutput(unittest.TestCase):
    def test_csv_rows_before_the_duplicates_heading(self):
        text = '3,2,20,1,3,"f@1-3@a.py","a.py","f","f( x )",1,3\nDuplicates\n===\nTotal duplicate rate: 0.00%\n'
        csv, dup = functions.split_output(text)
        self.assertEqual(csv, '3,2,20,1,3,"f@1-3@a.py","a.py","f","f( x )",1,3\n')
        self.assertEqual(dup, "Duplicates\n===\nTotal duplicate rate: 0.00%\n")

    def test_no_heading_means_no_duplicate_data(self):
        self.assertEqual(functions.split_output("1,2,3\n"), ("1,2,3\n", ""))
        self.assertEqual(functions.split_output(""), ("", ""))


if __name__ == "__main__":
    unittest.main()

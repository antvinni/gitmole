import os
import subprocess
import tempfile
import unittest

from gitmole import functions


def make_repo(d, extra=()):
    def git(*args):
        e = dict(os.environ, GIT_CONFIG_GLOBAL="/dev/null", GIT_CONFIG_SYSTEM="/dev/null",
                 GIT_AUTHOR_NAME="Ann", GIT_AUTHOR_EMAIL="a@x", GIT_COMMITTER_NAME="Ann", GIT_COMMITTER_EMAIL="a@x")
        subprocess.run(["git", *args], cwd=d, check=True, capture_output=True, env=e)
    git("init", "-q")
    os.makedirs(os.path.join(d, "vendor"))
    files = {
        "app.py": "def tracked(a, b):\n    if a:\n        return b\n    return a\n",
        "vendor/lib.py": "def vendored():\n    return 1\n",
        "notes.md": "def not_code():\n    pass\n",
        "page.js": "function scripted(a) {\n  if (a) { return 1; }\n  return 0;\n}\n",
        "run.sh": "shelled() {\n  if [ -n \"$1\" ]; then echo hi; fi\n}\n",
        "sim.f90": "subroutine fortran_sub(x)\n  integer :: x\n  if (x > 0) then\n    x = 1\n  end if\nend subroutine\n",
    }
    files.update(extra)
    for name, text in files.items():
        with open(os.path.join(d, name), "w") as fh:
            fh.write(text)
    git("add", "-A")
    git("commit", "-q", "-m", "one")
    with open(os.path.join(d, "untracked.py"), "w") as fh:
        fh.write("def untracked():\n    return 2\n")


def run(d, *args):
    out = os.path.join(d, "out")
    os.makedirs(out, exist_ok=True)
    rc = functions.main([d, out, "--procs", "1", *args])
    with open(os.path.join(out, "functions.csv")) as fh:
        csv = fh.read()
    return rc, csv, sorted(os.listdir(out))


class FunctionsScript(unittest.TestCase):
    def test_measures_tracked_files_lizard_can_read(self):
        with tempfile.TemporaryDirectory() as d:
            make_repo(d)
            rc, csv, written = run(d, "--ignore", "vendor/**")
        self.assertEqual(rc, 0)
        self.assertIn('"tracked"', csv)
        self.assertIn('"fortran_sub"', csv, "every language lizard knows, not only gitmole's default code list")
        self.assertNotIn("untracked", csv, "not tracked by git")
        self.assertNotIn("vendored", csv, "--ignore applies")
        self.assertNotIn("not_code", csv, "markdown is not code")
        self.assertNotIn("shelled", csv, "no lizard reader for shell: no guessing with the C-like fallback")
        self.assertEqual(written, ["functions.csv"], "duplicates are jscpd's step, not lizard's")

    def test_a_huge_nested_name_is_cut_before_it_is_written(self):
        from types import SimpleNamespace
        name = ".".join("a" for _ in range(100_000))
        fn = SimpleNamespace(nloc=5, cyclomatic_complexity=3, token_count=40, parameter_count=1, length=5, name=name,
                             long_name=name + "( )", start_line=1, end_line=5)
        row = functions.csv_row(SimpleNamespace(filename="a.py"), fn)
        self.assertEqual(len(row[7]), functions.NAME_CAP)
        self.assertTrue(row[7].endswith("…"))
        self.assertLessEqual(len(row[8]), functions.LONG_NAME_CAP)
        self.assertLessEqual(len(row[5]), functions.NAME_CAP + len("@1-5@a.py"))

    def test_csv_matches_lizards_own_layout(self):
        with tempfile.TemporaryDirectory() as d:
            make_repo(d)
            rc, csv, _ = run(d, "--types", "py", "--ignore", "vendor/**")
        self.assertEqual(csv, '4,2,14,2,4,"tracked@1-4@app.py","app.py","tracked","tracked( a , b )",1,4\n')

    def test_file_types_restrict_what_is_measured(self):
        with tempfile.TemporaryDirectory() as d:
            make_repo(d)
            rc, csv, _ = run(d, "--types", "js")
        self.assertEqual(rc, 0)
        self.assertIn("scripted", csv)
        self.assertNotIn("tracked", csv)
        self.assertNotIn("fortran", csv)

    def test_no_code_files_still_writes_an_empty_csv(self):
        with tempfile.TemporaryDirectory() as d:
            make_repo(d)
            rc, csv, _ = run(d, "--ignore", "*.py", "--ignore", "*.js", "--ignore", "*.f90")
        self.assertEqual(rc, 0)
        self.assertEqual(csv, "")

    def test_a_lizard_module_in_the_analysed_repo_is_data_not_code_to_run(self):
        bomb = "import sys\nsys.stderr.write('REPO LIZARD RAN')\nsys.exit(7)\n"
        with tempfile.TemporaryDirectory() as d:
            make_repo(d, extra={"lizard.py": bomb, "lizard_ext/__init__.py": bomb} if False else {"lizard.py": bomb})
            rc, csv, _ = run(d, "--types", "py", "--ignore", "vendor/**")
        self.assertEqual(rc, 0)
        self.assertIn('"tracked"', csv)
        self.assertNotIn("REPO LIZARD RAN", csv)

    def test_a_file_lizard_cannot_read_does_not_stop_the_files_after_it(self):
        with tempfile.TemporaryDirectory() as d:
            make_repo(d, extra={"b_gone.py": "def gone():\n    return 3\n", "c_after.py": "def after(a):\n    return a\n"})
            os.remove(os.path.join(d, "b_gone.py"))   # still in the index, no longer on disk
            rc, csv, _ = run(d, "--types", "py", "--ignore", "vendor/**")
        self.assertEqual(rc, 0)
        self.assertIn('"after"', csv, "files after the unreadable one are still measured")


if __name__ == "__main__":
    unittest.main()

import json
import os
import stat
import subprocess
import sys
import tempfile
import unittest

from gitmole import duplicates, run

SCRIPT = duplicates.__file__

BODY = "def f(x):\n" + "".join(f"    y{i} = x + {i}\n    if y{i} > {i}:\n        x = y{i}\n" for i in range(12)) + "    return x\n"


def make_repo(d, files: dict):
    os.makedirs(d, exist_ok=True)

    def git(*args):
        e = dict(os.environ, GIT_CONFIG_GLOBAL="/dev/null", GIT_CONFIG_SYSTEM="/dev/null",
                 GIT_AUTHOR_NAME="Ann", GIT_AUTHOR_EMAIL="a@x", GIT_COMMITTER_NAME="Ann", GIT_COMMITTER_EMAIL="a@x")
        subprocess.run(["git", *args], cwd=d, check=True, capture_output=True, env=e)
    git("init", "-q")
    for name, text in files.items():
        os.makedirs(os.path.dirname(os.path.join(d, name)) or d, exist_ok=True)
        with open(os.path.join(d, name), "w") as fh:
            fh.write(text)
    git("add", "-A")
    git("commit", "-q", "-m", "one")


def pair(a, b, lines=38, fragment="F", start=1):
    return {"format": "python", "fragment": fragment, "kind": "exact", "lines": lines, "tokens": 100,
            "firstFile": {"name": a, "start": start, "end": start + lines - 1},
            "secondFile": {"name": b, "start": start, "end": start + lines - 1}}


class Fold(unittest.TestCase):
    def test_pairs_of_one_fragment_become_one_block_with_every_place(self):
        clones = [pair("src/a.py", "src/b.py"), pair("src/a.py", "src/c.py"), pair("x.py", "y.py", lines=50, fragment="G")]
        blocks = duplicates.fold(clones, {"src/a.py", "src/b.py", "src/c.py", "x.py", "y.py"})
        self.assertEqual(blocks, [{"lines": 50, "places": [("x.py", 1, 50), ("y.py", 1, 50)]},
                                  {"lines": 38, "places": [("src/a.py", 1, 38), ("src/b.py", 1, 38), ("src/c.py", 1, 38)]}], "largest first")

    def test_a_pair_with_an_untracked_side_is_dropped(self):
        clones = [pair("src/a.py", "untracked.py"), pair("./src/a.py", "docs/x.md:python"), pair("src/a.py", "src/b.py")]
        blocks = duplicates.fold(clones, {"src/a.py", "src/b.py", "docs/x.md"})
        self.assertEqual(blocks, [{"lines": 38, "places": [("src/a.py", 1, 38), ("src/b.py", 1, 38)]}],
                         "an untracked file and a code fence in markdown are not this repository's duplication")

    def test_two_places_in_one_file_are_kept_apart(self):
        clones = [pair("a.py", "a.py", fragment="H")]
        clones[0]["secondFile"] = {"name": "a.py", "start": 100, "end": 137}
        self.assertEqual(duplicates.fold(clones, {"a.py"}), [{"lines": 38, "places": [("a.py", 1, 38), ("a.py", 100, 137)]}])


class Rate(unittest.TestCase):
    def test_share_of_kept_lines_inside_a_block_counting_overlaps_once(self):
        with tempfile.TemporaryDirectory() as d:
            for name, n in (("a.py", 100), ("b.py", 50), ("c.py", 50)):
                with open(os.path.join(d, name), "w") as fh:
                    fh.write("x\n" * n)
            blocks = [{"lines": 20, "places": [("a.py", 1, 20), ("b.py", 1, 20)]},
                      {"lines": 15, "places": [("a.py", 10, 24), ("c.py", 30, 44)]}]   # a.py 10-20 already counted
            self.assertEqual(duplicates.rate(blocks, d, ["a.py", "b.py", "c.py"]), round(100 * (24 + 20 + 15) / 200, 2))
            self.assertEqual(duplicates.rate([], d, ["a.py"]), 0.0)
            self.assertEqual(duplicates.rate(blocks, d, []), 0.0, "no files, no rate")


class Script(unittest.TestCase):
    """The wiring, against a stand-in jscpd on PATH that writes a canned report."""

    def _run(self, report, rc=0, extra=()):
        with tempfile.TemporaryDirectory() as d:
            bindir, repo, out = os.path.join(d, "bin"), os.path.join(d, "repo"), os.path.join(d, "out")
            for p in (bindir, out):
                os.makedirs(p)
            make_repo(repo, {"src/a.py": BODY, "src/b.py": BODY, "vendor/lib.py": BODY, "notes.md": "text\n"})
            with open(os.path.join(d, "report.json"), "w") as fh:
                json.dump(report, fh)
            fake = os.path.join(bindir, "jscpd")
            with open(fake, "w") as fh:
                fh.write("#!/bin/sh\n"
                         f"echo \"$@\" > {d}/argv\npwd > {d}/cwd\n"
                         "while [ $# -gt 0 ]; do if [ \"$1\" = --output ]; then mkdir -p \"$2\"; cp "
                         f"{d}/report.json \"$2/jscpd-report.json\"; fi; shift; done\n"
                         f"echo 'jscpd said hi' >&2\nexit {rc}\n")
            os.chmod(fake, os.stat(fake).st_mode | stat.S_IEXEC)
            env = dict(os.environ, PATH=bindir + os.pathsep + os.environ["PATH"])
            p = subprocess.run([sys.executable, SCRIPT, repo, out, "--procs", "3", *extra], env=env, capture_output=True, text=True)
            with open(os.path.join(d, "argv")) as fh:
                argv = fh.read().split()
            with open(os.path.join(d, "cwd")) as fh:
                cwd = fh.read().strip()
            written = None
            if os.path.exists(os.path.join(out, "duplicates.json")):
                with open(os.path.join(out, "duplicates.json")) as fh:
                    written = json.load(fh)
            leftovers = sorted(os.listdir(out))
        return p, argv, cwd, written, leftovers, repo

    REPORT = {"duplicates": [pair("src/a.py", "src/b.py", fragment="def f(x): secret sauce"), pair("src/a.py", "vendor/lib.py", fragment="def f(x): secret sauce"),
                             pair("src/a.py", "untracked.py", fragment="def f(x): secret sauce")],
              "statistics": {"total": {"percentage": 50.0}}}

    def test_runs_jscpd_in_the_repo_and_writes_the_folded_blocks_without_the_fragments(self):
        p, argv, cwd, written, leftovers, repo = self._run(self.REPORT, extra=["--ignore", "vendor/**"])
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(os.path.realpath(cwd), os.path.realpath(repo), "jscpd walks the repository it is started in")
        self.assertEqual(argv[argv.index("--reporters") + 1], "json")
        self.assertEqual(argv[argv.index("--workers") + 1], "3")
        self.assertEqual(argv[argv.index("--ignore") + 1], ".git/**,vendor/**", "the .git directory is never scanned; --ignore globs save work")
        self.assertTrue(argv[argv.index("--output") + 1].startswith(os.path.join(os.path.realpath(os.path.dirname(cwd)), "out", ".jscpd-")) or ".jscpd-" in argv[argv.index("--output") + 1])
        self.assertEqual(argv[-1], ".")
        self.assertEqual(written["blocks"], [{"lines": 38, "places": [["src/a.py", 1, 38], ["src/b.py", 1, 38]]}],
                         "the vendored side is ignored, the untracked side is not tracked")
        self.assertEqual(written["rate"], round(100 * 76 / (2 * BODY.count("\n")), 2), "over the kept code files: a.py and b.py; notes.md is not code")
        self.assertEqual((written["files"], written["clones"], written["tool"]), (2, 1, "jscpd"))
        self.assertNotIn("secret sauce", json.dumps(written), "no fragment text reaches the output directory")
        self.assertEqual(leftovers, ["duplicates.json"], "jscpd's own report and the temporary directory are gone")
        self.assertIn("jscpd said hi", p.stderr, "jscpd's stderr still reaches run.log")

    def test_a_failed_jscpd_writes_nothing_and_fails_the_step(self):
        p, _, _, written, leftovers, _ = self._run(self.REPORT, rc=2)
        self.assertEqual(p.returncode, 2)
        self.assertIsNone(written)
        self.assertEqual(leftovers, [])

    def test_file_types_restrict_the_kept_files(self):
        report = {"duplicates": [pair("src/a.py", "src/b.py"), pair("notes.md", "src/a.py", fragment="M")], "statistics": {}}
        p, _, _, written, _, _ = self._run(report, extra=["--types", "md"])
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(written["blocks"], [], "only markdown counts, and a block needs two markdown sides")
        self.assertEqual(written["files"], 1)
        p, _, _, written, _, _ = self._run(report, extra=["--types", "all"])
        self.assertEqual(sorted(b["places"][0][0] for b in written["blocks"]), ["notes.md", "src/a.py"], "all: every tracked text file")
        self.assertEqual(written["files"], 4)

    def test_data_files_are_not_code_by_default(self):
        # mealie: sixteen thousand lines of locale JSON copied per language topped the list until data files were left out
        report = {"duplicates": [pair("locales/af.json", "locales/ar.json", lines=16307, fragment="J"), pair("src/a.py", "src/b.py")], "statistics": {}}
        p, _, _, written, _, _ = self._run(report)
        self.assertEqual([b["places"][0][0] for b in written["blocks"]], ["src/a.py"])


@unittest.skipUnless(run.has_tool("jscpd"), "jscpd not installed")
class RealJscpd(unittest.TestCase):
    def test_finds_the_copies_among_tracked_files(self):
        with tempfile.TemporaryDirectory() as d:
            repo, out = os.path.join(d, "repo"), os.path.join(d, "out")
            os.makedirs(out)
            make_repo(repo, {"src/a_copy.py": BODY, "src/sub dir/z_copy.py": BODY, "src/café.py": BODY, "vendor/lib.py": BODY, "tests/t_copy.py": BODY,
                             "README.md": "# hi\n"})
            with open(os.path.join(repo, "untracked.py"), "w") as fh:
                fh.write(BODY)
            rc = duplicates.main([repo, out, "--procs", "1", "--ignore", "vendor/**"])
            with open(os.path.join(out, "duplicates.json")) as fh:
                written = json.load(fh)
            self.assertEqual(sorted(os.listdir(out)), ["duplicates.json"])
        self.assertEqual(rc, 0)
        [block] = written["blocks"]
        self.assertEqual([p[0] for p in block["places"]], ["src/a_copy.py", "src/café.py", "src/sub dir/z_copy.py", "tests/t_copy.py"])
        self.assertGreater(block["lines"], 30)
        self.assertGreater(written["rate"], 50)


if __name__ == "__main__":
    unittest.main()

import json
import os
import subprocess
import tempfile
import unittest

from gitmole import blame


def make_repo(d):
    def git(*args, **env):
        e = dict(os.environ, GIT_CONFIG_GLOBAL="/dev/null", GIT_CONFIG_SYSTEM="/dev/null", **env)
        subprocess.run(["git", *args], cwd=d, check=True, capture_output=True, env=e)
    git("init", "-q")
    ann = dict(GIT_AUTHOR_NAME="Ann", GIT_AUTHOR_EMAIL="a@x", GIT_COMMITTER_NAME="Ann", GIT_COMMITTER_EMAIL="a@x",
               GIT_AUTHOR_DATE="2024-05-01T00:00:00", GIT_COMMITTER_DATE="2024-05-01T00:00:00")
    with open(os.path.join(d, "a.py"), "w") as fh:
        fh.write("one\ntwo\nthree\n")
    with open(os.path.join(d, "data.csv"), "w") as fh:
        fh.write("x,y\n1,2\n")
    with open(os.path.join(d, "blob.bin"), "wb") as fh:
        fh.write(b"\x00\x01\x02binary\x00")
    with open(os.path.join(d, "README.md"), "w") as fh:
        fh.write("# docs\n")
    with open(os.path.join(d, "config.yaml"), "w") as fh:
        fh.write("a: 1\n")
    git("add", "-A")
    git("commit", "-q", "-m", "one", **ann)
    bob = dict(ann, GIT_AUTHOR_NAME="Bobby", GIT_AUTHOR_EMAIL="b@x", GIT_AUTHOR_DATE="2026-02-01T00:00:00", GIT_COMMITTER_DATE="2026-02-01T00:00:00")
    with open(os.path.join(d, "a.py"), "a") as fh:
        fh.write("four\n")
    with open(os.path.join(d, "b.py"), "w") as fh:
        fh.write("x\ny\n")
    git("add", "-A")
    git("commit", "-q", "-m", "two", **bob)


class TextFiles(unittest.TestCase):
    def test_lists_tracked_code_files_skipping_binaries_docs_data_and_ignores(self):
        with tempfile.TemporaryDirectory() as d:
            make_repo(d)
            # binaries, Markdown, YAML and CSV are not code; git-of-theseus skips them too
            self.assertEqual(blame.code_files(d), ["a.py", "b.py"])
            self.assertEqual(blame.code_files(d, ignore=["b.*"]), ["a.py"])
            self.assertEqual(blame.code_files(d, types={"csv"}), ["data.csv"])
            self.assertEqual(blame.code_files(d, types=None), ["README.md", "a.py", "b.py", "config.yaml", "data.csv"])
            self.assertIn("data.csv", blame.text_files(d))


class NonAsciiPaths(unittest.TestCase):
    def test_listed_unquoted(self):
        with tempfile.TemporaryDirectory() as d:
            make_repo(d)
            with open(os.path.join(d, "s\u00e4.py"), "w") as fh:
                fh.write("x\n")
            subprocess.run(["git", "-C", d, "add", "-A"], check=True, capture_output=True)
            self.assertIn("s\u00e4.py", blame.code_files(d))
            self.assertFalse([f for f in blame.code_files(d) if f.startswith('"')])
            with open(os.path.join(d, 'q"uote.py'), "w") as fh: fh.write("x\n")
            subprocess.run(["git", "-C", d, "add", "-A"], check=True, capture_output=True)
            self.assertIn('q"uote.py', blame.code_files(d))
            self.assertEqual(blame.blame_file(d, "s\u00e4.py"), {}, "not committed yet, so no blame, but no crash either")


class BlameFile(unittest.TestCase):
    def test_counts_lines_per_year_and_author(self):
        with tempfile.TemporaryDirectory() as d:
            make_repo(d)
            counts = blame.blame_file(d, "a.py")
        self.assertEqual(counts, {("2024", "Ann"): 3, ("2026", "Bobby"): 1})


class Estimate(unittest.TestCase):
    def test_projects_wall_time_from_a_sample(self):
        with tempfile.TemporaryDirectory() as d:
            make_repo(d)
            est = blame.estimate(d, sample=1, procs=2, timer=iter([0.0, 0.5]).__next__)
        # 2 code files, one sampled at 0.5s -> 1.0s single-core -> 0.5s on 2 workers
        self.assertEqual(est["files"], 2)
        self.assertAlmostEqual(est["seconds"], 0.5)

    def test_default_workers_leave_two_cores_free(self):
        self.assertEqual(blame.default_procs(cpu=10), 8)
        self.assertEqual(blame.default_procs(cpu=2), 1)


class WriteAll(unittest.TestCase):
    def test_writes_cohort_and_author_json_in_theseus_layout(self):
        with tempfile.TemporaryDirectory() as d:
            make_repo(d)
            out = os.path.join(d, "out")
            os.makedirs(os.path.join(out, "theseus"))
            meta = os.path.join(out, "meta.json")
            with open(meta, "w") as fh:
                json.dump({"identities": [{"name": "Bob", "email": "b@x", "commits": 1, "aliases": [{"name": "Bobby", "email": "b@x", "commits": 1}]}]}, fh)
            blame.write_all(d, out, ignore=["*.csv"], aliases_path=meta, procs=2)
            with open(os.path.join(out, "theseus", "cohorts.json")) as fh:
                cohorts = json.load(fh)
            with open(os.path.join(out, "theseus", "authors.json")) as fh:
                authors = json.load(fh)
        self.assertEqual(cohorts["labels"], ["Code added in 2024", "Code added in 2026"])
        self.assertEqual(cohorts["y"], [[3], [3]])
        self.assertEqual(len(cohorts["ts"]), 1)
        self.assertEqual(dict(zip(authors["labels"], [y[0] for y in authors["y"]])), {"Ann": 3, "Bob": 3})


class CoAuthors(unittest.TestCase):
    def test_a_blame_line_is_shared_with_the_commits_co_authors(self):
        with tempfile.TemporaryDirectory() as d:
            make_repo(d)
            def git(*args, **env):
                e = dict(os.environ, GIT_CONFIG_GLOBAL="/dev/null", GIT_CONFIG_SYSTEM="/dev/null", **env)
                subprocess.run(["git", *args], cwd=d, check=True, capture_output=True, env=e)
            ann = dict(GIT_AUTHOR_NAME="Ann", GIT_AUTHOR_EMAIL="a@x", GIT_COMMITTER_NAME="Ann", GIT_COMMITTER_EMAIL="a@x",
                       GIT_AUTHOR_DATE="2026-03-01T00:00:00", GIT_COMMITTER_DATE="2026-03-01T00:00:00")
            with open(os.path.join(d, "c.py"), "w") as fh:
                fh.write("p\nq\nr\ns\n")
            git("add", "-A")
            git("commit", "-q", "-m", "pair\n\nCo-authored-by: Cat <c@x>", **ann)
            log = subprocess.run(["git", "log", "HEAD", "--numstat", "--date=iso-strict", "-M",
                                  "--pretty=format:--%h--%ad--%aN--%s%x1f%(trailers:key=Co-authored-by,valueonly,unfold,separator=%x1f)"],
                                 cwd=d, capture_output=True, text=True, check=True).stdout
            shared = blame.co_authors_by_commit(log)
            self.assertEqual(list(shared.values()), [["Cat"]])
            blame.set_co_authors(shared)
            try:
                self.assertEqual(blame.blame_file(d, "c.py"), {("2026", "Ann"): 2, ("2026", "Cat"): 2}, "four lines, two people")
                self.assertEqual(blame.blame_file(d, "a.py"), {("2024", "Ann"): 3, ("2026", "Bobby"): 1}, "a commit without trailers is its author's")
            finally:
                blame.set_co_authors({})
            out = os.path.join(d, "out")
            os.makedirs(os.path.join(out, "theseus"))
            with open(os.path.join(out, "log.txt"), "w") as fh:
                fh.write(log)
            blame.write_all(d, out, procs=2, log_path=os.path.join(out, "log.txt"))
            with open(os.path.join(out, "theseus", "authors.json")) as fh:
                authors = json.load(fh)
        self.assertEqual(dict(zip(authors["labels"], [y[0] for y in authors["y"]])), {"Ann": 5, "Bobby": 3, "Cat": 2},
                         "whole lines: the shares are rounded once, at the end")


if __name__ == "__main__":
    unittest.main()



class Imported(unittest.TestCase):
    def test_lines_an_import_wrote_count_for_their_year_and_for_nobody(self):
        with tempfile.TemporaryDirectory() as d:
            make_repo(d)
            head = subprocess.run(["git", "rev-list", "--max-parents=0", "HEAD"], cwd=d, capture_output=True, text=True, check=True).stdout.strip()
            blame.set_imported([head[:9]])
            try:
                self.assertEqual(blame.blame_file(d, "a.py"), {("2024", None): 3, ("2026", "Bobby"): 1})
            finally:
                blame.set_imported(())

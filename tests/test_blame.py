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
        self.assertEqual(counts, {("2024", "Ann <a@x>"): 3, ("2026", "Bobby <b@x>"): 1}, "keyed by name and address, as the identity rows are")


class Estimate(unittest.TestCase):
    RATE = blame.SECONDS_PER_COMMIT_WALKED / blame.REFERENCE_WORKERS

    def test_counts_the_commits_each_blame_walks(self):
        with tempfile.TemporaryDirectory() as d:
            make_repo(d)
            history = blame.history_times(d)
            # a.py still has lines from the first commit, so its blame walks both; b.py's lines are all from the second
            self.assertEqual(len(history), 2)
            self.assertEqual(blame.commits_walked(d, "a.py", history), 2)
            self.assertEqual(blame.commits_walked(d, "b.py", history), 1)
            self.assertEqual(blame.commits_walked(d, "gone.py", history), 0, "nothing to blame walks nothing")

    def test_projects_the_pass_from_the_work_at_the_reference_rate(self):
        with tempfile.TemporaryDirectory() as d:
            make_repo(d)
            est = blame.estimate(d, sample=1)
            both = blame.estimate(d, sample=2)
        # one file sampled (a.py, 2 commits walked) stands for both code files: 4 commits
        self.assertEqual((est["files"], est["sampled"], est["commits_walked"]), (2, 1, 4))
        self.assertAlmostEqual(est["seconds"], 4 * self.RATE)
        self.assertEqual(both["commits_walked"], 3)
        self.assertAlmostEqual(both["seconds"], 3 * self.RATE)

    def test_the_projection_reads_no_clock_and_no_core_count(self):
        """The decision to run code age must not depend on the machine or its load: django ran it at
        load 2.4-2.7 and skipped it at 3.05 and 8.05 while it was timed."""
        import itertools
        from unittest import mock
        with tempfile.TemporaryDirectory() as d:
            make_repo(d)
            quiet = blame.estimate(d, sample=2)
            slow = itertools.count(0.0, 1000.0)   # every reading a thousand seconds after the last
            with mock.patch("time.monotonic", lambda: next(slow)), mock.patch("time.perf_counter", lambda: next(slow)), \
                    mock.patch("time.time", lambda: next(slow)), mock.patch("os.cpu_count", lambda: 1), \
                    mock.patch("os.getloadavg", lambda: (50.0, 50.0, 50.0), create=True):
                busy = blame.estimate(d, sample=2)
                capped = blame.estimate(d, sample=2, budget=60.0)
        self.assertEqual(quiet, busy)
        self.assertEqual(quiet, capped)
        import inspect
        self.assertFalse({"timer", "procs"} & set(inspect.signature(blame.estimate).parameters),
                         "a clock or a core count passed in would bring the machine back into the decision")

    def test_default_workers_leave_two_cores_free(self):
        self.assertEqual(blame.default_procs(cpu=10), 8)
        self.assertEqual(blame.default_procs(cpu=2), 1)

    def test_stops_sampling_once_the_work_counted_proves_the_budget_exceeded(self):
        with tempfile.TemporaryDirectory() as d:
            make_repo(d)
            # after a.py, 2 commits walked per 2 picked x 2 files = 2 commits: over a budget of one commit's price
            est = blame.estimate(d, sample=2, budget=1.5 * self.RATE)
        self.assertEqual(est["sampled"], 1)
        self.assertTrue(est["partial"])
        self.assertAlmostEqual(est["seconds"], 2 * self.RATE)

    def test_a_budget_it_stays_under_gives_the_same_projection_as_no_budget(self):
        with tempfile.TemporaryDirectory() as d:
            make_repo(d)
            plain = blame.estimate(d, sample=2)
            capped = blame.estimate(d, sample=2, budget=100.0)
        self.assertEqual(plain, capped)
        self.assertNotIn("partial", capped)

    def test_a_history_given_is_used_rather_than_read_again(self):
        with tempfile.TemporaryDirectory() as d:
            make_repo(d)
            est = blame.estimate(d, sample=2, history=[0] * 10 + blame.history_times(d))
        self.assertEqual(est["commits_walked"], 3, "only commits no older than the oldest line count")


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
        self.assertEqual(dict(zip(authors["labels"], [y[0] for y in authors["y"]])), {"Ann <a@x>": 3, "Bobby <b@x>": 3},
                         "git's own spelling; the loader canonicalises the name")


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
            self.assertEqual(list(shared.values()), [["Cat <c@x>"]])
            blame.set_co_authors(shared)
            try:
                self.assertEqual(blame.blame_file(d, "c.py"), {("2026", "Ann <a@x>"): 2, ("2026", "Cat <c@x>"): 2}, "four lines, two people")
                self.assertEqual(blame.blame_file(d, "a.py"), {("2024", "Ann <a@x>"): 3, ("2026", "Bobby <b@x>"): 1}, "a commit without trailers is its author's")
            finally:
                blame.set_co_authors({})
            out = os.path.join(d, "out")
            os.makedirs(os.path.join(out, "theseus"))
            with open(os.path.join(out, "log.txt"), "w") as fh:
                fh.write(log)
            blame.write_all(d, out, procs=2, log_path=os.path.join(out, "log.txt"))
            with open(os.path.join(out, "theseus", "authors.json")) as fh:
                authors = json.load(fh)
        self.assertEqual(dict(zip(authors["labels"], [y[0] for y in authors["y"]])), {"Ann <a@x>": 5, "Bobby <b@x>": 3, "Cat <c@x>": 2},
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
                self.assertEqual(blame.blame_file(d, "a.py"), {("2024", None): 3, ("2026", "Bobby <b@x>"): 1})
            finally:
                blame.set_imported(())

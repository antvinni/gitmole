import json
import os
import subprocess
import tempfile
import unittest

from gitmole import run


class ClassifyTarget(unittest.TestCase):
    def test_existing_directory_is_a_path(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(run.classify_target(d), ("path", os.path.abspath(d)))

    def test_owner_slash_repo_is_remote(self):
        self.assertEqual(run.classify_target("acme/widgets"), ("remote", "acme/widgets"))

    def test_github_url_is_remote(self):
        self.assertEqual(run.classify_target("https://github.com/o/r.git"), ("remote", "https://github.com/o/r.git"))

    def test_garbage_raises(self):
        with self.assertRaises(ValueError):
            run.classify_target("not a repo at all")


class RepoName(unittest.TestCase):
    def test_strips_git_suffix_and_takes_last_segment(self):
        self.assertEqual(run.repo_name("https://github.com/o/r.git"), "r")
        self.assertEqual(run.repo_name("o/r"), "r")
        self.assertEqual(run.repo_name("/tmp/x/widgets"), "widgets")


class OutputDir(unittest.TestCase):
    def test_explicit_wins(self):
        self.assertEqual(run.output_dir("path", "/a/b/repo", "/x/out"), "/x/out")

    def test_local_path_goes_next_to_clone(self):
        self.assertEqual(run.output_dir("path", "/a/b/repo", None), "/a/b/analysis-repo")

    def test_remote_goes_into_cwd(self):
        self.assertEqual(run.output_dir("remote", "/tmp/clone/repo", None, cwd="/home/me"), "/home/me/analysis-repo")


class Plan(unittest.TestCase):
    def test_lists_every_tool_and_theseus_plots_depend_on_analyze(self):
        steps = run.plan("/r", "/o", "/j.jar")
        names = [s["name"] for s in steps]
        for expected in ["onefetch", "git-quick-stats", "scc", "git-sizer", "gitleaks", "git-log",
                         "code-maat revisions", "code-maat coupling", "code-maat authors", "code-maat age",
                         "code-maat entity-ownership", "git-of-theseus", "theseus stack plot", "theseus survival plot"]:
            self.assertIn(expected, names)
        by = {s["name"]: s for s in steps}
        self.assertEqual(by["theseus stack plot"]["deps"], ["git-of-theseus"])
        self.assertEqual(by["code-maat coupling"]["deps"], ["git-log"])
        self.assertEqual(by["onefetch"]["deps"], [])
        self.assertEqual(by["scc"]["stdout"], "/o/size.json")

    def test_theseus_tracks_the_given_branch(self):
        by = {s["name"]: s for s in run.plan("/r", "/o", "/j.jar", branch="trunk")}
        argv = by["git-of-theseus"]["argv"]
        self.assertEqual(argv[argv.index("--branch") + 1], "trunk")


class Execute(unittest.TestCase):
    def test_respects_dependencies_and_reports_failures(self):
        with tempfile.TemporaryDirectory() as d:
            order = os.path.join(d, "order")
            steps = [
                {"name": "slow-first", "argv": ["sh", "-c", f"sleep 0.2; echo first >> {order}"], "stdout": None, "deps": []},
                {"name": "second", "argv": ["sh", "-c", f"echo second >> {order}"], "stdout": None, "deps": ["slow-first"]},
                {"name": "captured", "argv": ["sh", "-c", "echo hello"], "stdout": os.path.join(d, "cap.txt"), "deps": []},
                {"name": "broken", "argv": ["sh", "-c", "echo oops >&2; exit 3"], "stdout": None, "deps": []},
            ]
            seen = []
            results = run.execute(steps, log_path=os.path.join(d, "run.log"), on_done=lambda name, rc: seen.append(name))
            with open(order) as fh:
                self.assertEqual(fh.read().split(), ["first", "second"])
            with open(os.path.join(d, "cap.txt")) as fh:
                self.assertEqual(fh.read().strip(), "hello")
            with open(os.path.join(d, "run.log")) as fh:
                self.assertIn("oops", fh.read())
        self.assertEqual(results["broken"], 3)
        self.assertEqual(results["second"], 0)
        self.assertEqual(sorted(seen), sorted(s["name"] for s in steps))

    def test_skips_steps_whose_dependency_failed(self):
        steps = [
            {"name": "a", "argv": ["sh", "-c", "exit 1"], "stdout": None, "deps": []},
            {"name": "b", "argv": ["sh", "-c", "echo should-not-run"], "stdout": None, "deps": ["a"]},
        ]
        with tempfile.TemporaryDirectory() as d:
            results = run.execute(steps, log_path=os.path.join(d, "run.log"))
        self.assertEqual(results["a"], 1)
        self.assertEqual(results["b"], "skipped")


class CollectMeta(unittest.TestCase):
    def test_reads_commits_span_branch_and_identities_from_git(self):
        with tempfile.TemporaryDirectory() as d:
            def git(*args, **env):
                e = dict(os.environ, GIT_CONFIG_GLOBAL="/dev/null", GIT_CONFIG_SYSTEM="/dev/null", **env)
                subprocess.run(["git", *args], cwd=d, check=True, capture_output=True, env=e)
            git("init", "-q", "-b", "trunk")
            ident = dict(GIT_AUTHOR_DATE="2025-01-02T10:00:00", GIT_COMMITTER_DATE="2025-01-02T10:00:00",
                         GIT_AUTHOR_NAME="Ann", GIT_AUTHOR_EMAIL="ann@x.com", GIT_COMMITTER_NAME="Ann", GIT_COMMITTER_EMAIL="ann@x.com")
            git("commit", "-q", "--allow-empty", "-m", "one", **ident)
            git("commit", "-q", "--allow-empty", "-m", "two", **ident)
            ident.update(GIT_AUTHOR_NAME="Bob", GIT_AUTHOR_EMAIL="bob@x.com", GIT_AUTHOR_DATE="2026-03-04T10:00:00", GIT_COMMITTER_DATE="2026-03-04T10:00:00")
            git("commit", "-q", "--allow-empty", "-m", "three", **ident)
            meta = run.collect_meta(d)
        self.assertEqual(meta["name"], os.path.basename(d))
        self.assertEqual(meta["branch"], "trunk")
        self.assertEqual(meta["commits"], 3)
        self.assertEqual(meta["first_date"], "2025-01-02")
        self.assertEqual(meta["last_date"], "2026-03-04")
        self.assertEqual(meta["identities"], [{"name": "Ann", "email": "ann@x.com", "commits": 2},
                                              {"name": "Bob", "email": "bob@x.com", "commits": 1}])


if __name__ == "__main__":
    unittest.main()

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

    def test_owner_star_is_an_org(self):
        self.assertEqual(run.classify_target("acme/*"), ("org", "acme"))

    def test_garbage_raises(self):
        with self.assertRaises(ValueError):
            run.classify_target("not a repo at all")


class ListRepos(unittest.TestCase):
    def test_uses_gh_to_list_non_archived_repos_sorted(self):
        calls = []
        def lister(argv):
            calls.append(argv)
            return "zeta\nalpha\n"
        self.assertEqual(run.list_repos("acme", lister=lister), ["alpha", "zeta"])
        self.assertEqual(calls[0][:3], ["gh", "repo", "list"])
        self.assertIn("acme", calls[0])
        self.assertIn("isArchived", " ".join(calls[0]))


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
        steps = run.plan("/r", "/o")
        names = [s["name"] for s in steps]
        for expected in ["onefetch", "git-quick-stats", "scc", "git-sizer", "gitleaks", "git-log", "change analysis", "code age"]:
            self.assertIn(expected, names)
        for absent in ["git-of-theseus", "theseus stack plot", "theseus survival plot"]:
            self.assertNotIn(absent, names, "plots are opt-in")
        by = {s["name"]: s for s in steps}
        self.assertEqual(by["change analysis"]["deps"], ["git-log"])
        self.assertEqual(by["code age"]["deps"], [])
        self.assertEqual(by["onefetch"]["deps"], [])
        self.assertEqual(by["scc"]["stdout"], "/o/size.json")
        self.assertIn("--by-file", by["scc"]["argv"])
        self.assertIn("--use-mailmap", by["git-log"]["argv"])

    def test_code_age_runs_the_bundled_blame_script(self):
        by = {s["name"]: s for s in run.plan("/r", "/o", ignore=["*.csv"])}
        argv = by["code age"]["argv"]
        self.assertTrue(argv[1].endswith("gitmole/blame.py"), argv)
        self.assertEqual(argv[2:4], ["/r", "/o"])
        self.assertEqual(argv[argv.index("--procs") + 1], str(os.cpu_count()))
        self.assertEqual(argv[argv.index("--ignore") + 1], "*.csv")
        self.assertEqual(argv[argv.index("--aliases") + 1], "/o/meta.json")

    def test_plots_add_theseus_after_code_age(self):
        by = {s["name"]: s for s in run.plan("/r", "/o", plots=True)}
        self.assertEqual(by["git-of-theseus"]["deps"], ["code age"])
        self.assertEqual(by["theseus stack plot"]["deps"], ["git-of-theseus"])

    def test_age_can_be_left_out(self):
        names = [s["name"] for s in run.plan("/r", "/o", age=False, plots=True)]
        self.assertNotIn("code age", names)
        self.assertIn("git-of-theseus", names)

    def test_change_analysis_runs_the_bundled_script_with_the_meta_aliases(self):
        by = {s["name"]: s for s in run.plan("/r", "/o")}
        argv = by["change analysis"]["argv"]
        self.assertTrue(argv[1].endswith("gitmole/maat.py"), argv)
        self.assertEqual(argv[2:], ["/o/log.txt", "/o", "--aliases", "/o/meta.json"])

    def test_no_java_required(self):
        self.assertNotIn("java", run.REQUIRED_TOOLS)
        self.assertEqual(run.missing_tools(), [])

    def test_theseus_tracks_the_given_branch(self):
        by = {s["name"]: s for s in run.plan("/r", "/o", branch="trunk", plots=True)}
        argv = by["git-of-theseus"]["argv"]
        self.assertEqual(argv[argv.index("--branch") + 1], "trunk")


class PlanTheseusOptions(unittest.TestCase):
    def argv(self, **kw):
        by = {s["name"]: s for s in run.plan("/r", "/o", plots=True, **kw)}
        return by["git-of-theseus"]["argv"]

    def test_uses_every_core_and_monthly_sampling_by_default(self):
        argv = self.argv()
        self.assertEqual(argv[argv.index("--procs") + 1], str(os.cpu_count()))
        self.assertEqual(argv[argv.index("--interval") + 1], str(run.MONTH))

    def test_ignore_patterns_are_forwarded_one_flag_each(self):
        argv = self.argv(ignore=["*.csv", "vendor/**"])
        self.assertEqual(argv[argv.index("--ignore") + 1], "*.csv")
        self.assertEqual(argv.count("--ignore"), 2)
        self.assertIn("vendor/**", argv)


class EstimateBlames(unittest.TestCase):
    def test_files_times_samples_over_the_history_span(self):
        with tempfile.TemporaryDirectory() as d:
            def git(*args, **env):
                e = dict(os.environ, GIT_CONFIG_GLOBAL="/dev/null", GIT_CONFIG_SYSTEM="/dev/null", **env)
                subprocess.run(["git", *args], cwd=d, check=True, capture_output=True, env=e)
            git("init", "-q")
            ident = dict(GIT_AUTHOR_NAME="A", GIT_AUTHOR_EMAIL="a@x", GIT_COMMITTER_NAME="A", GIT_COMMITTER_EMAIL="a@x")
            for i, date in enumerate(["2026-01-01T00:00:00", "2026-02-15T00:00:00", "2026-04-01T00:00:00"]):
                open(os.path.join(d, f"f{i}.py"), "w").write("x")
                open(os.path.join(d, f"g{i}.py"), "w").write("x")
                git("add", "-A")
                git("commit", "-q", "-m", str(i), GIT_AUTHOR_DATE=date, GIT_COMMITTER_DATE=date, **ident)
            est = run.estimate_blames(d, interval=run.MONTH)
        # 6 files; 90 days at a 30-day interval would be 4 samples, capped at the 3 commits that exist
        self.assertEqual(est, {"files": 6, "samples": 3, "blames": 18})


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

    def test_times_out_a_step_and_kills_its_process_group(self):
        with tempfile.TemporaryDirectory() as d:
            marker = os.path.join(d, "child-finished")
            steps = [{"name": "slow", "argv": ["sh", "-c", f"(sleep 5; touch {marker}) & sleep 5"], "stdout": None, "deps": []},
                     {"name": "after", "argv": ["sh", "-c", "true"], "stdout": None, "deps": ["slow"]}]
            results = run.execute(steps, log_path=os.path.join(d, "run.log"), timeout=0.5)
            import time
            time.sleep(0.7)
            self.assertFalse(os.path.exists(marker), "background child kept running after timeout")
        self.assertEqual(results["slow"], "timeout")
        self.assertEqual(results["after"], "skipped")

    def test_tools_get_a_null_stdin_not_the_parents_terminal(self):
        # Regression: children inheriting an interactive stdin as new session leaders
        # corrupted the parent tty (EIO). They must read EOF immediately instead.
        with tempfile.TemporaryDirectory() as d:
            cap = os.path.join(d, "stdin.txt")
            steps = [{"name": "reader", "argv": ["sh", "-c", f"cat > {cap}"], "stdout": None, "deps": []}]
            results = run.execute(steps, log_path=os.path.join(d, "run.log"), timeout=5)
            self.assertEqual(results["reader"], 0)
            with open(cap) as fh:
                self.assertEqual(fh.read(), "")

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
        self.assertEqual(meta["identities"], [{"name": "Ann", "email": "ann@x.com", "commits": 2, "aliases": []},
                                              {"name": "Bob", "email": "bob@x.com", "commits": 1, "aliases": []}])

    def test_identities_are_merged_and_mailmap_is_honoured(self):
        with tempfile.TemporaryDirectory() as d:
            def git(*args, **env):
                e = dict(os.environ, GIT_CONFIG_GLOBAL="/dev/null", GIT_CONFIG_SYSTEM="/dev/null", **env)
                subprocess.run(["git", *args], cwd=d, check=True, capture_output=True, env=e)
            git("init", "-q")
            base = dict(GIT_COMMITTER_NAME="x", GIT_COMMITTER_EMAIL="x@x")
            for name, email in [("Ann Lee", "ann@x.com"), ("ann-lee", "1@users.noreply.github.com"), ("Bob", "bob@x.com"), ("Robert", "bob@old.com")]:
                git("commit", "-q", "--allow-empty", "-m", name, GIT_AUTHOR_NAME=name, GIT_AUTHOR_EMAIL=email, **base)
            with open(os.path.join(d, ".mailmap"), "w") as fh:
                fh.write("Bob <bob@x.com> Robert <bob@old.com>\n")
            git("add", ".mailmap")
            git("commit", "-q", "-m", "mailmap", GIT_AUTHOR_NAME="Bob", GIT_AUTHOR_EMAIL="bob@x.com", **base)
            meta = run.collect_meta(d)
        by = {i["name"]: i for i in meta["identities"]}
        self.assertEqual(set(by), {"Ann Lee", "Bob"})
        self.assertEqual(by["Bob"]["commits"], 3)
        self.assertEqual(by["Bob"]["aliases"], [], "mailmap should merge Robert before the heuristic sees it")
        self.assertEqual([a["name"] for a in by["Ann Lee"]["aliases"]], ["ann-lee"])


if __name__ == "__main__":
    unittest.main()

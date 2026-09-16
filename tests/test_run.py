import json
import os
import subprocess
import tempfile
import sys
import unittest

from gitmole import blame, run


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
    def _lister(self, me="someone", is_org=False):
        calls = []
        def lister(argv):
            calls.append(argv)
            path = argv[2] if len(argv) > 2 else ""
            if path == "user":
                return me + "\n"
            if path.startswith("orgs/") and "/repos" not in path:
                if is_org:
                    return "acme\n"
                raise subprocess.CalledProcessError(1, argv, stderr="HTTP 404: Not Found")
            return "zeta\nalpha\n"
        return lister, calls

    def test_user_repos_via_rest_sorted(self):
        lister, calls = self._lister()
        self.assertEqual(run.list_repos("acme", lister=lister), ["alpha", "zeta"])
        final = calls[-1]
        self.assertEqual(final[:3], ["gh", "api", "--paginate"])
        self.assertTrue(final[3].startswith("users/acme/repos"), final)
        self.assertIn("archived", " ".join(final))

    def test_own_account_includes_private_repos(self):
        lister, calls = self._lister(me="acme")
        run.list_repos("acme", lister=lister)
        self.assertTrue(calls[-1][3].startswith("user/repos"), calls[-1])
        self.assertIn("affiliation=owner", calls[-1][3])

    def test_organisation_uses_the_org_endpoint(self):
        lister, calls = self._lister(is_org=True)
        run.list_repos("acme", lister=lister)
        self.assertTrue(calls[-1][3].startswith("orgs/acme/repos"), calls[-1])


class GhErrors(unittest.TestCase):
    def test_list_repos_wraps_gh_failure_with_its_stderr(self):
        def lister(argv):
            raise subprocess.CalledProcessError(1, argv, stderr="tls: failed to verify certificate")
        with self.assertRaises(run.GhError) as ctx:
            run.list_repos("acme", lister=lister)
        self.assertIn("failed to verify certificate", str(ctx.exception))

    def test_clone_wraps_gh_failure_with_its_stderr(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(run.GhError) as ctx:
                run.clone("acme/definitely-missing-repo-xyz", d, runner=lambda argv: (_ for _ in ()).throw(subprocess.CalledProcessError(1, argv, stderr="repository not found")))
        self.assertIn("repository not found", str(ctx.exception))


class ParseSince(unittest.TestCase):
    def test_relative_and_absolute_forms(self):
        today = "2026-09-15"
        self.assertEqual(run.parse_since("2y", today), "2024-09-15")
        self.assertEqual(run.parse_since("18m", today), "2025-03-15")
        self.assertEqual(run.parse_since("90d", today), "2026-06-17")
        self.assertEqual(run.parse_since("2024-01-01", today), "2024-01-01")

    def test_month_end_clamps(self):
        self.assertEqual(run.parse_since("1m", "2026-03-31"), "2026-02-28")

    def test_garbage_raises_a_value_error_with_the_hint(self):
        for bad in ("yesterday", "2y3m", "2026-13-01", "", "20240101", "1900-01-01", "1000000000d", "99999y"):
            with self.assertRaises(ValueError) as ctx:
                run.parse_since(bad, "2026-09-15")
            self.assertIn("--since", str(ctx.exception), bad)


class SinceInPlanAndMeta(unittest.TestCase):
    def test_plan_exports_the_full_log_and_hands_the_window_to_the_analysis(self):
        by = {s["name"]: s for s in run.plan("/r", "/o", since="2024-01-01")}
        self.assertFalse([a for a in by["git-log"]["argv"] if a.startswith("--since")], "git --since is a traversal cutoff on committer date; the window is applied in Python")
        argv = by["change analysis"]["argv"]
        self.assertEqual(argv[argv.index("--since") + 1], "2024-01-01")
        self.assertNotIn("--since", by["code age"]["argv"])

    def test_collect_meta_counts_only_the_window(self):
        with tempfile.TemporaryDirectory() as d:
            def git(*args, **env):
                e = dict(os.environ, GIT_CONFIG_GLOBAL="/dev/null", GIT_CONFIG_SYSTEM="/dev/null", **env)
                subprocess.run(["git", *args], cwd=d, check=True, capture_output=True, env=e)
            git("init", "-q")
            ident = dict(GIT_AUTHOR_NAME="Ann", GIT_AUTHOR_EMAIL="ann@x.com", GIT_COMMITTER_NAME="Ann", GIT_COMMITTER_EMAIL="ann@x.com")
            for date in ["2023-01-01T10:00:00", "2025-01-01T10:00:00", "2026-01-01T10:00:00"]:
                git("commit", "-q", "--allow-empty", "-m", date, GIT_AUTHOR_DATE=date, GIT_COMMITTER_DATE=date, **ident)
            meta = run.collect_meta(d, since="2024-06-01")
        self.assertEqual(meta["commits"], 2)
        self.assertEqual(meta["first_date"], "2025-01-01")
        self.assertEqual(meta["since"], "2024-06-01")

    def test_window_uses_author_date_and_survives_an_old_committer_date_on_the_tip(self):
        with tempfile.TemporaryDirectory() as d:
            def git(*args, **env):
                e = dict(os.environ, GIT_CONFIG_GLOBAL="/dev/null", GIT_CONFIG_SYSTEM="/dev/null", **env)
                subprocess.run(["git", *args], cwd=d, check=True, capture_output=True, env=e)
            git("init", "-q")
            ident = dict(GIT_AUTHOR_NAME="Ann", GIT_AUTHOR_EMAIL="ann@x.com", GIT_COMMITTER_NAME="Ann", GIT_COMMITTER_EMAIL="ann@x.com")
            git("commit", "-q", "--allow-empty", "-m", "new", GIT_AUTHOR_DATE="2025-01-01T10:00:00", GIT_COMMITTER_DATE="2025-01-01T10:00:00", **ident)
            # rebased old work: authored 2020, committed 2026 -> outside the window by author date
            git("commit", "-q", "--allow-empty", "-m", "rebased", GIT_AUTHOR_DATE="2020-03-01T10:00:00", GIT_COMMITTER_DATE="2026-01-01T10:00:00", **ident)
            # clock-skewed tip: committed "2019" but authored 2026 -> inside; git --since would have stopped here
            git("commit", "-q", "--allow-empty", "-m", "tip", GIT_AUTHOR_DATE="2026-02-01T10:00:00", GIT_COMMITTER_DATE="2019-01-01T10:00:00", **ident)
            meta = run.collect_meta(d, since="2024-06-01")
        self.assertEqual(meta["commits"], 2)
        self.assertEqual((meta["first_date"], meta["last_date"]), ("2025-01-01", "2026-02-01"))

    def test_aliases_come_from_the_whole_history_even_when_windowed(self):
        with tempfile.TemporaryDirectory() as d:
            def git(*args, **env):
                e = dict(os.environ, GIT_CONFIG_GLOBAL="/dev/null", GIT_CONFIG_SYSTEM="/dev/null", **env)
                subprocess.run(["git", *args], cwd=d, check=True, capture_output=True, env=e)
            git("init", "-q")
            base = dict(GIT_COMMITTER_NAME="x", GIT_COMMITTER_EMAIL="x@x")
            for name, email, when in [("John Smith", "john@corp", "2019-01-01T10:00:00"), ("john-smith", "j@old", "2019-06-01T10:00:00"),
                                      ("Zed", "z@x", "2026-01-01T10:00:00")]:
                git("commit", "-q", "--allow-empty", "-m", name, GIT_AUTHOR_NAME=name, GIT_AUTHOR_EMAIL=email, GIT_AUTHOR_DATE=when, GIT_COMMITTER_DATE=when, **base)
            meta = run.collect_meta(d, since="2025-01-01")
        self.assertEqual([i["name"] for i in meta["identities"]], ["Zed"])
        self.assertEqual(meta["aliases"], {"john-smith": "John Smith"}, "merged from the full history so blame and ownership still merge them")


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
        for expected in ["scc", "git-sizer", "gitleaks", "git-log", "change analysis", "code age"]:
            self.assertIn(expected, names)
        for gone in ["onefetch", "git-quick-stats"]:
            self.assertNotIn(gone, names)
        for absent in ["git-of-theseus", "theseus stack plot", "theseus survival plot"]:
            self.assertNotIn(absent, names, "plots are opt-in")
        by = {s["name"]: s for s in steps}
        self.assertEqual(by["change analysis"]["deps"], ["git-log"])
        self.assertEqual(by["code age"]["deps"], [])
        self.assertEqual(by["scc"]["deps"], [])
        self.assertIn("--date=iso-strict", by["git-log"]["argv"])
        self.assertIn("--pretty=format:--%h--%ad--%aN--%s", by["git-log"]["argv"])
        self.assertEqual(by["scc"]["stdout"], "/o/size.json")
        self.assertIn("--by-file", by["scc"]["argv"])
        self.assertIn("--use-mailmap", by["git-log"]["argv"])
        self.assertEqual(by["git-log"]["argv"][:4], ["git", "-c", "core.quotePath=false", "log"], "non-ASCII paths must not be octal-escaped and quoted")

    def test_function_metrics_step_is_optional_and_runs_the_bundled_script(self):
        by = {s["name"]: s for s in run.plan("/r", "/o", lizard=True, ignore=["vendor/**"], types="py,sql", procs=3)}
        argv = by["functions"]["argv"]
        self.assertEqual(argv[:4], [sys.executable, run.FUNCTIONS_SCRIPT, "/r", "/o"])
        self.assertEqual(argv[argv.index("--ignore") + 1], "vendor/**")
        self.assertEqual(argv[argv.index("--types") + 1], "py,sql")
        self.assertIsNone(by["functions"]["stdout"], "the script writes functions.csv and duplicates.txt itself")
        self.assertNotIn("duplicates", by, "one lizard pass produces both")
        self.assertNotIn("functions", [s["name"] for s in run.plan("/r", "/o", lizard=False)])

    def test_function_metrics_use_the_blame_workers_without_the_duplicate_finder(self):
        def step(**kw):
            return {s["name"]: s for s in run.plan("/r", "/o", lizard=True, **kw)}["functions"]["argv"]
        argv = step(procs=8)
        self.assertEqual(argv[argv.index("--procs") + 1], "8")
        self.assertNotIn("--duplicates", argv, "duplicate detection is opt-in")
        argv = step()
        self.assertEqual(argv[argv.index("--procs") + 1], str(blame.default_procs()))

    def test_duplicate_finder_is_forwarded_and_caps_the_workers_at_two(self):
        # lizard's duplicate finder keeps a hash node per token; each worker grows to 1.5-2 GB on a
        # large repo, and the default worker count exhausted a 16 GB machine.
        def procs_for(**kw):
            argv = {s["name"]: s for s in run.plan("/r", "/o", lizard=True, duplicates=True, **kw)}["functions"]["argv"]
            self.assertIn("--duplicates", argv)
            return argv[argv.index("--procs") + 1]
        self.assertEqual(run.FUNCTIONS_MAX_PROCS, 2)
        self.assertEqual(procs_for(procs=8), "2", "an explicit larger count is clamped")
        self.assertEqual(procs_for(procs=1), "1", "a smaller count is kept")
        self.assertEqual(procs_for(), str(min(2, blame.default_procs())), "the default is clamped too")

    def test_gitleaks_runs_through_the_bundled_wrapper_so_raw_secrets_never_reach_disk(self):
        by = {s["name"]: s for s in run.plan("/r", "/o")}
        argv = by["gitleaks"]["argv"]
        self.assertEqual(argv[0], sys.executable)
        self.assertTrue(argv[1].endswith("gitmole/leaks.py"), argv)
        self.assertEqual(argv[2:], ["/o/secrets.json"])
        self.assertIsNone(by["gitleaks"]["stdout"])

    def test_lizard_is_detected_as_a_python_module_not_a_command(self):
        self.assertNotIn("lizard", run.REQUIRED_TOOLS)
        self.assertTrue(run.has_lizard())
        self.assertFalse(run.has_lizard(finder=lambda name: None))

    def test_code_age_runs_the_bundled_blame_script(self):
        by = {s["name"]: s for s in run.plan("/r", "/o", ignore=["*.csv"])}
        argv = by["code age"]["argv"]
        self.assertTrue(argv[1].endswith("gitmole/blame.py"), argv)
        self.assertEqual(argv[2:4], ["/r", "/o"])
        self.assertEqual(argv[argv.index("--procs") + 1], str(max(1, os.cpu_count() - 2)))
        self.assertEqual(argv[argv.index("--ignore") + 1], "*.csv")
        self.assertEqual(argv[argv.index("--aliases") + 1], "/o/meta.json")

    def test_file_types_are_forwarded_to_blame_and_change_analysis(self):
        by = {s["name"]: s for s in run.plan("/r", "/o", types="py,sql")}
        for name in ("code age", "change analysis"):
            argv = by[name]["argv"]
            self.assertEqual(argv[argv.index("--types") + 1], "py,sql", name)
        by = {s["name"]: s for s in run.plan("/r", "/o")}
        self.assertNotIn("--types", by["code age"]["argv"], "default types need no flag")

    def test_reference_date_is_forwarded_to_the_change_analysis_only(self):
        by = {s["name"]: s for s in run.plan("/r", "/o", now="2025-06-15")}
        argv = by["change analysis"]["argv"]
        self.assertEqual(argv[argv.index("--now") + 1], "2025-06-15")
        self.assertNotIn("--now", by["code age"]["argv"])
        self.assertNotIn("--now", {s["name"]: s for s in run.plan("/r", "/o")}["change analysis"]["argv"])

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

    def test_only_three_tools_required_by_default_and_theseus_with_plots(self):
        self.assertEqual(run.REQUIRED_TOOLS, ["scc", "git-sizer", "gitleaks"])
        self.assertEqual(run.missing_tools(), [])
        self.assertEqual(run.missing_tools(plots=True), [])
        self.assertEqual(run.missing_tools(plots=True, path="/nonexistent"), ["scc", "git-sizer", "gitleaks", "git-of-theseus-analyze"])

    def test_theseus_tracks_the_given_branch(self):
        by = {s["name"]: s for s in run.plan("/r", "/o", branch="trunk", plots=True)}
        argv = by["git-of-theseus"]["argv"]
        self.assertEqual(argv[argv.index("--branch") + 1], "trunk")

    def test_trend_runs_as_a_module_after_scc_and_the_change_analysis(self):
        by = {s["name"]: s for s in run.plan("/r", "/o")}
        self.assertEqual(by["trend"]["argv"][:3], [sys.executable, "-m", "gitmole.trend"])
        self.assertEqual(by["trend"]["argv"][3], "/o")
        self.assertEqual(by["trend"]["deps"], ["scc", "change analysis"])
        self.assertNotIn("trend", [s["name"] for s in run.plan("/r", "/o", trend=False)])
        self.assertIn("trend.json", run.OUTPUTS)

    def test_backtest_step_runs_after_the_change_analysis_when_a_cut_off_is_given(self):
        by = {s["name"]: s for s in run.plan("/r", "/o", backtest="2025-12-01")}
        self.assertEqual(by["backtest"]["argv"][:3], [sys.executable, "-m", "gitmole.backtest"])
        self.assertEqual(by["backtest"]["argv"][3:], ["/o", "--until", "2025-12-01"])
        self.assertEqual(by["backtest"]["deps"], ["git-log", "change analysis"])
        self.assertNotIn("backtest", [s["name"] for s in run.plan("/r", "/o")])

    def test_execute_puts_the_package_on_pythonpath(self):
        with tempfile.TemporaryDirectory() as d:
            log = os.path.join(d, "run.log")
            steps = [{"name": "p", "argv": [sys.executable, "-c", "import os; print(os.environ['PYTHONPATH'])"], "stdout": os.path.join(d, "out.txt"), "deps": []}]
            run.execute(steps, log_path=log, cwd=d)
            with open(os.path.join(d, "out.txt")) as fh:
                first = fh.read().strip().split(os.pathsep)[0]
        self.assertEqual(os.path.realpath(first), os.path.realpath(os.path.dirname(os.path.dirname(run.__file__))))


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
            est = run.estimate_blames(d, interval=run.MONTH, sample=0)
        # 6 files; 90 days at a 30-day interval would be 4 samples, capped at the 3 commits that exist
        self.assertEqual({k: est[k] for k in ("files", "samples", "blames")}, {"files": 6, "samples": 3, "blames": 18})
        self.assertIn("seconds", est)


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

    def test_cancel_kills_running_steps_and_marks_pending_ones(self):
        import threading, time
        with tempfile.TemporaryDirectory() as d:
            marker = os.path.join(d, "finished")
            steps = [{"name": "slow", "argv": ["sh", "-c", f"sleep 5; touch {marker}"], "stdout": None, "deps": []},
                     {"name": "after", "argv": ["sh", "-c", "true"], "stdout": None, "deps": ["slow"]}]
            ctl = run.Control()
            box = {}
            t = threading.Thread(target=lambda: box.update(run.execute(steps, log_path=os.path.join(d, "run.log"), control=ctl)))
            t.start()
            time.sleep(0.3)
            started = time.monotonic()
            ctl.cancel()
            t.join(5)
            self.assertLess(time.monotonic() - started, 3, "cancel must not wait for the sleep to finish")
            time.sleep(0.2)
            self.assertFalse(os.path.exists(marker))
        self.assertEqual(box["slow"], "cancelled")
        self.assertEqual(box["after"], "cancelled")

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

    def test_first_date_all_spans_the_whole_history_even_when_windowed(self):
        with tempfile.TemporaryDirectory() as d:
            def git(*args, **env):
                e = dict(os.environ, GIT_CONFIG_GLOBAL="/dev/null", GIT_CONFIG_SYSTEM="/dev/null", **env)
                subprocess.run(["git", *args], cwd=d, check=True, capture_output=True, env=e)
            git("init", "-q")
            ident = dict(GIT_AUTHOR_NAME="Ann", GIT_AUTHOR_EMAIL="ann@x.com", GIT_COMMITTER_NAME="Ann", GIT_COMMITTER_EMAIL="ann@x.com")
            for date in ["2023-01-01T10:00:00", "2025-01-01T10:00:00", "2026-01-01T10:00:00"]:
                git("commit", "-q", "--allow-empty", "-m", date, GIT_AUTHOR_DATE=date, GIT_COMMITTER_DATE=date, **ident)
            windowed = run.collect_meta(d, since="2024-06-01")
            whole = run.collect_meta(d)
        self.assertEqual(windowed["first_date"], "2025-01-01")
        self.assertEqual(windowed["first_date_all"], "2023-01-01", "the backtest measures the whole history")
        self.assertEqual(whole["first_date_all"], whole["first_date"], "without a window the two are the same date")

    def test_bots_are_left_out_of_identities_and_listed_apart(self):
        with tempfile.TemporaryDirectory() as d:
            def git(*args, **env):
                e = dict(os.environ, GIT_CONFIG_GLOBAL="/dev/null", GIT_CONFIG_SYSTEM="/dev/null", **env)
                subprocess.run(["git", *args], cwd=d, check=True, capture_output=True, env=e)
            git("init", "-q")
            base = dict(GIT_COMMITTER_NAME="x", GIT_COMMITTER_EMAIL="x@x")
            for name, email in [("Ann", "ann@x.com"), ("renovate[bot]", "29139614+renovate[bot]@users.noreply.github.com"),
                                ("renovate[bot]", "29139614+renovate[bot]@users.noreply.github.com"), ("dependabot[bot]", "support@github.com")]:
                git("commit", "-q", "--allow-empty", "-m", name, GIT_AUTHOR_NAME=name, GIT_AUTHOR_EMAIL=email, **base)
            meta = run.collect_meta(d)
        self.assertEqual([i["name"] for i in meta["identities"]], ["Ann"])
        self.assertEqual(meta["commits"], 4, "the commit count is the whole history")
        self.assertEqual(meta["bots"], [{"name": "renovate[bot]", "commits": 2}, {"name": "dependabot[bot]", "commits": 1}])


class ChangedFiles(unittest.TestCase):
    def test_lists_paths_changed_since_the_merge_base(self):
        with tempfile.TemporaryDirectory() as d:
            def git(*args):
                e = dict(os.environ, GIT_CONFIG_GLOBAL="/dev/null", GIT_CONFIG_SYSTEM="/dev/null",
                         GIT_AUTHOR_NAME="A", GIT_AUTHOR_EMAIL="a@x", GIT_COMMITTER_NAME="A", GIT_COMMITTER_EMAIL="a@x")
                subprocess.run(["git", *args], cwd=d, check=True, capture_output=True, env=e)
            git("init", "-q", "-b", "main")
            for name in ("a.py", "b.py"):
                open(os.path.join(d, name), "w").write("x\n")
            git("add", "-A"); git("commit", "-q", "-m", "base")
            git("switch", "-q", "-c", "feature")
            open(os.path.join(d, "b.py"), "a").write("y\n")
            os.makedirs(os.path.join(d, "dir"))
            open(os.path.join(d, "dir", "c.py"), "w").write("z\n")
            git("add", "-A"); git("commit", "-q", "-m", "work")
            git("switch", "-q", "main")
            open(os.path.join(d, "a.py"), "a").write("main moved on\n")
            git("commit", "-q", "-am", "main")
            git("switch", "-q", "feature")
            self.assertEqual(run.changed_files(d, "main"), ["b.py", "dir/c.py"], "three-dot diff: main's own change to a.py is not ours")
            with self.assertRaises(ValueError) as ctx:
                run.changed_files(d, "nope")
            self.assertIn("nope", str(ctx.exception))


class ClearOutputs(unittest.TestCase):
    def test_removes_every_tool_output_but_keeps_meta_and_the_log(self):
        with tempfile.TemporaryDirectory() as out:
            os.makedirs(os.path.join(out, "theseus"))
            names = ["size.json", "repo-health.txt", "secrets.json", "log.txt", "maat-revisions.csv", "maat-fixes.csv", "activity.json",
                     "functions.csv", "duplicates.txt", "theseus/cohorts.json", "theseus/authors.json", "theseus/survival.json",
                     "code-age.png", "survival.png", "meta.json", "run.log", "notes.txt"]
            for n in names:
                open(os.path.join(out, n), "w").close()
            run.clear_outputs(out)
            left = sorted(os.path.relpath(os.path.join(r, f), out) for r, _, fs in os.walk(out) for f in fs)
        self.assertEqual(left, ["meta.json", "notes.txt", "run.log"])

    def test_missing_files_are_fine(self):
        with tempfile.TemporaryDirectory() as out:
            run.clear_outputs(out)

    def test_clear_outputs_removes_temporary_checkouts_a_kill_left_behind(self):
        with tempfile.TemporaryDirectory() as d:
            for name in (".backtest-tree-ab12", ".trend-cd34"):
                os.makedirs(os.path.join(d, name, "app"))
                open(os.path.join(d, name, "app", "a.py"), "w").close()
            open(os.path.join(d, ".trend-ef56.json"), "w").close()   # an interrupted atomic write
            open(os.path.join(d, "meta.json"), "w").close()
            run.clear_outputs(d)
            self.assertEqual(sorted(os.listdir(d)), ["meta.json"])

    def test_clear_outputs_removes_the_backtest_directory(self):
        with tempfile.TemporaryDirectory() as d:
            os.makedirs(os.path.join(d, "backtest"))
            open(os.path.join(d, "backtest", "size.json"), "w").close()
            run.clear_outputs(d)
            self.assertFalse(os.path.exists(os.path.join(d, "backtest")))


if __name__ == "__main__":
    unittest.main()

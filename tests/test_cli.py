import io
import json
import os
import pathlib
import tempfile
import unittest

from rich.console import Console

from gitmole import cli, run


def console():
    return Console(file=io.StringIO(), width=100, record=True, force_terminal=False, color_system=None)


class NoRun(unittest.TestCase):
    def test_renders_from_existing_output_dir(self):
        with tempfile.TemporaryDirectory() as out:
            with open(os.path.join(out, "meta.json"), "w") as fh:
                json.dump({"name": "demo", "commits": 5, "identities": []}, fh)
            c = console()
            rc = cli.main([out, "--no-run"], console=c)
        self.assertEqual(rc, 0)
        self.assertIn("demo", c.export_text())

    def test_missing_output_dir_is_an_error(self):
        c = console()
        rc = cli.main(["/nonexistent/analysis-x", "--no-run"], console=c)
        self.assertEqual(rc, 2)
        self.assertIn("/nonexistent/analysis-x", c.export_text())


class LiveRun(unittest.TestCase):
    def test_full_run_on_a_terminal_console_prints_banner_and_report(self):
        with tempfile.TemporaryDirectory() as d:
            import subprocess
            subprocess.run(["git", "init", "-q", d], check=True)
            subprocess.run(["git", "-C", d, "-c", "user.name=T", "-c", "user.email=t@x.com", "commit", "-q", "--allow-empty", "-m", "x"], check=True)
            c = Console(file=io.StringIO(), width=100, record=True, force_terminal=True, color_system="truecolor")
            fake_plan = lambda repo, out, branch="HEAD", **kw: [
                {"name": "quick", "argv": ["sh", "-c", "sleep 0.3"], "stdout": None, "deps": []}]
            rc = cli.main([d, "--out", os.path.join(d, "out")], console=c, tool_check=lambda **kw: [], planner=fake_plan)
            text = c.export_text()
        self.assertEqual(rc, 0)
        self.assertIn("███╗   ███╗", text)
        self.assertIn("1 steps in", text)
        self.assertIn(os.path.basename(d), text)


def _tiny_repo(d):
    import subprocess
    subprocess.run(["git", "init", "-q", d], check=True)
    subprocess.run(["git", "-C", d, "-c", "user.name=T", "-c", "user.email=t@x.com", "commit", "-q", "--allow-empty", "-m", "x"], check=True)


class FunctionMetrics(unittest.TestCase):
    def _main(self, lizard, calls, stale=(), step=("sh", "-c", "true"), name="quick"):
        with tempfile.TemporaryDirectory() as d:
            _tiny_repo(d)
            out = os.path.join(d, "out")
            os.makedirs(os.path.join(out, "theseus"))
            for n in stale:
                open(os.path.join(out, n), "w").close()
            def planner(repo, o, branch="HEAD", **kw):
                calls.append(kw)
                return [{"name": name, "argv": list(step), "stdout": None, "deps": []}]
            rc = cli.main([d, "--out", out], console=console(), tool_check=lambda **kw: [], planner=planner,
                          estimator=lambda repo, interval, **kw: {"files": 1, "samples": 1, "blames": 1}, lizard_check=lambda: lizard)
            with open(os.path.join(out, "meta.json")) as fh:
                meta = json.load(fh)
            left = sorted(os.path.relpath(os.path.join(r, f), out) for r, _, fs in os.walk(out) for f in fs)
        return rc, meta, left

    def test_decided_once_and_recorded(self):
        calls = []
        rc, meta, _ = self._main(True, calls)
        self.assertEqual(rc, 0)
        self.assertTrue(calls[0]["lizard"])
        self.assertEqual(meta["functions"]["status"], "run")

    def test_skipped_without_lizard(self):
        calls = []
        rc, meta, _ = self._main(False, calls)
        self.assertEqual(rc, 0)
        self.assertFalse(calls[0]["lizard"])
        self.assertEqual(meta["functions"]["status"], "skipped")

    def test_a_failed_step_is_recorded_as_such(self):
        _, meta, _ = self._main(True, [], step=("sh", "-c", "exit 3"), name="functions")
        self.assertEqual(meta["functions"]["status"], "failed")
        _, meta, _ = self._main(True, [], step=("sh", "-c", "exit 3"), name="code age")
        self.assertEqual(meta["age"]["status"], "failed")

    def test_every_previous_output_is_cleared_before_a_run(self):
        stale = ("functions.csv", "duplicates.txt", "theseus/cohorts.json", "maat-revisions.csv", "size.json")
        _, _, left = self._main(False, [], stale=stale)
        self.assertEqual(left, ["meta.json", "run.log"], "last run's outputs must not pass for this run's")

    def test_trend_status_is_recorded(self):
        _, meta, _ = self._main(True, [], name="trend")
        self.assertEqual(meta["trend"]["status"], "run")
        _, meta, _ = self._main(True, [], step=("sh", "-c", "exit 3"), name="trend")
        self.assertEqual(meta["trend"]["status"], "failed")

    def test_a_plan_without_a_trend_step_leaves_the_status_alone(self):
        _, meta, _ = self._main(True, [], name="quick")
        self.assertEqual(meta["trend"]["status"], "planned", "a step that never ran did not run")


class Budget(unittest.TestCase):
    def _main(self, extra, estimate, plan_calls):
        with tempfile.TemporaryDirectory() as d:
            _tiny_repo(d)
            c = console()
            def planner(repo, out, branch="HEAD", **kw):
                plan_calls.append(kw)
                return [{"name": "quick", "argv": ["sh", "-c", "true"], "stdout": None, "deps": []}]
            rc = cli.main([d, "--out", os.path.join(d, "out"), *extra], console=c,
                          tool_check=lambda **kw: [], planner=planner, estimator=lambda repo, interval, **kw: estimate)
            with open(os.path.join(d, "out", "meta.json")) as fh:
                meta = json.load(fh)
            return rc, c.export_text(), meta

    BIG = {"files": 80000, "samples": 11, "blames": 880000, "seconds": 400.0}
    SMALL = {"files": 100, "samples": 5, "blames": 500, "seconds": 0.4}
    SLOW = {"files": 28000, "samples": 3, "blames": 84000, "seconds": 390.0}

    def test_code_age_runs_by_default_and_plots_do_not(self):
        calls = []
        _, text, meta = self._main([], self.SMALL, calls)
        self.assertTrue(calls[0]["age"])
        self.assertFalse(calls[0]["plots"])
        self.assertEqual(meta["age"]["status"], "run")
        self.assertNotIn("skipped", text)

    def test_code_age_skipped_when_projected_time_exceeds_budget(self):
        calls = []
        rc, text, meta = self._main([], self.SLOW, calls)
        self.assertEqual(rc, 0)
        self.assertFalse(calls[0]["age"])
        self.assertIn("390", text)
        self.assertIn("60", text)
        self.assertIn("--deep", text)
        self.assertEqual(meta["age"]["status"], "skipped")
        self.assertEqual(meta["age"]["projected_seconds"], 390.0)

    def test_time_budget_flag_raises_the_threshold(self):
        calls = []
        self._main(["--time-budget", "600"], self.SLOW, calls)
        self.assertTrue(calls[0]["age"])

    def test_plots_flag_runs_theseus_under_budget(self):
        calls = []
        _, _, meta = self._main(["--plots"], self.SMALL, calls)
        self.assertTrue(calls[0]["plots"])
        self.assertEqual(meta["plots"]["status"], "run")

    def test_plots_skipped_when_files_times_samples_exceed_budget_but_age_still_runs(self):
        calls = []
        _, text, meta = self._main(["--plots"], {"files": 30000, "samples": 11, "blames": 330000}, calls)
        self.assertTrue(calls[0]["age"], "30,000 files is under the 50,000 budget")
        self.assertFalse(calls[0]["plots"])
        self.assertIn("330,000", text)
        self.assertEqual(meta["plots"]["status"], "skipped")

    def test_deep_forces_both_regardless_of_budget(self):
        calls = []
        self._main(["--deep", "--plots"], self.BIG, calls)
        self.assertTrue(calls[0]["age"])
        self.assertTrue(calls[0]["plots"])

    def test_budget_flag_applies_to_plots(self):
        calls = []
        self._main(["--plots", "--budget", "1000000", "--time-budget", "1000"], self.BIG, calls)
        self.assertTrue(calls[0]["plots"])

    def test_ignore_data_and_custom_ignores_reach_the_planner(self):
        calls = []
        self._main(["--ignore-data", "--ignore", "docs/**"], self.SMALL, calls)
        self.assertIn("*.csv", calls[0]["ignore"])
        self.assertIn("docs/**", calls[0]["ignore"])

    def test_no_ignores_by_default(self):
        calls = []
        self._main([], self.SMALL, calls)
        self.assertEqual(list(calls[0]["ignore"]), [])


class Interrupt(unittest.TestCase):
    def test_keyboard_interrupt_kills_steps_and_exits_130(self):
        import threading, time, signal
        with tempfile.TemporaryDirectory() as d:
            _tiny_repo(d)
            marker = os.path.join(d, "finished")
            planner = lambda repo, out, branch="HEAD", **kw: [
                {"name": "slow", "argv": ["sh", "-c", f"sleep 5; touch {marker}"], "stdout": None, "deps": []}]
            c = console()
            box = {}
            def go():
                box["rc"] = cli.main([d, "--out", os.path.join(d, "out")], console=c, tool_check=lambda **kw: [], planner=planner,
                                     estimator=lambda repo, interval, **kw: {"files": 1, "samples": 1, "blames": 1, "seconds": 0.0})
            t = threading.Thread(target=go)
            t.start()
            time.sleep(0.5)
            cli.interrupt()          # what the SIGINT handler does
            t.join(5)
            self.assertFalse(t.is_alive(), "gitmole must exit promptly after Ctrl-C")
            time.sleep(0.2)
            self.assertFalse(os.path.exists(marker))
        self.assertEqual(box["rc"], 130)
        self.assertIn("interrupted", c.export_text())


class Timeout(unittest.TestCase):
    def test_timed_out_step_is_reported(self):
        with tempfile.TemporaryDirectory() as d:
            _tiny_repo(d)
            c = console()
            planner = lambda repo, out, branch="HEAD", **kw: [
                {"name": "sleepy", "argv": ["sh", "-c", "sleep 3"], "stdout": None, "deps": []}]
            cli.main([d, "--out", os.path.join(d, "out"), "--timeout", "0.3"], console=c,
                     tool_check=lambda **kw: [], planner=planner, estimator=lambda repo, interval, **kw: {"files": 1, "samples": 1, "blames": 1})
            text = c.export_text()
        self.assertIn("sleepy (timeout)", text)


def _report_dir(out, identities=None):
    with open(os.path.join(out, "meta.json"), "w") as fh:
        json.dump({"name": "demo", "commits": 5, "identities": identities or []}, fh)


class Export(unittest.TestCase):
    def test_json_export_to_file(self):
        with tempfile.TemporaryDirectory() as out:
            _report_dir(out)
            c = console()
            rc = cli.main([out, "--no-run", "--json", os.path.join(out, "r.json")], console=c)
            with open(os.path.join(out, "r.json")) as fh:
                d = json.load(fh)
        self.assertEqual(rc, 0)
        self.assertEqual(d["meta"]["name"], "demo")
        self.assertIn("findings", d)
        self.assertIn("demo", c.export_text(), "the terminal report still prints when exporting to a file")

    def test_markdown_to_stdout_replaces_the_terminal_report(self):
        with tempfile.TemporaryDirectory() as out:
            _report_dir(out)
            c = Console(file=io.StringIO(), width=100, record=True, force_terminal=True, color_system="truecolor")
            rc = cli.main([out, "--no-run", "--markdown", "-"], console=c)
            text = c.export_text()
        self.assertEqual(rc, 0)
        self.assertTrue(text.startswith("# demo"), text[:40])
        self.assertNotIn("╭", text)
        self.assertNotIn("███╗", text, "no banner when piping an export to stdout")

    def test_fail_on_returns_3_when_a_finding_reaches_the_level(self):
        ids = [{"name": "Your Name", "email": "you@example.com", "commits": 5, "aliases": []}]
        with tempfile.TemporaryDirectory() as out:
            _report_dir(out, ids)
            self.assertEqual(cli.main([out, "--no-run", "--fail-on", "warning"], console=console()), 3)
            self.assertEqual(cli.main([out, "--no-run", "--fail-on", "critical"], console=console()), 0)
            self.assertEqual(cli.main([out, "--no-run"], console=console()), 0)


class Portfolio(unittest.TestCase):
    def _run(self, extra=(), fail=False):
        with tempfile.TemporaryDirectory() as work:
            def cloner(target, parent):
                d = os.path.join(parent, target.split("/")[-1])
                os.makedirs(d)
                _tiny_repo(d)
                if target.endswith("two"):
                    import subprocess
                    subprocess.run(["git", "-C", d, "-c", "user.name=Your Name", "-c", "user.email=you@example.com",
                                    "commit", "-q", "--allow-empty", "-m", "x"], check=True)
                return d
            planner = lambda repo, out, branch="HEAD", **kw: [{"name": "q", "argv": ["true"], "stdout": None, "deps": []}]
            c = console()
            rc = cli.main(["acme/*", "--out", os.path.join(work, "pf"), *extra], console=c, tool_check=lambda **kw: [], planner=planner,
                          estimator=lambda repo, interval, **kw: {"files": 1, "samples": 1, "blames": 1},
                          lister=lambda owner: ["one", "two"], cloner=cloner)
            text = c.export_text()
            dirs = sorted(os.listdir(os.path.join(work, "pf")))
            has_meta = all(os.path.isfile(os.path.join(work, "pf", d, "meta.json")) for d in dirs)
            md = os.path.join(work, "pf", "portfolio.md")
            md_text = pathlib.Path(md).read_text() if os.path.exists(md) else ""
        return rc, text, dirs, has_meta, md_text

    def test_runs_every_repo_and_prints_one_summary_table(self):
        rc, text, dirs, has_meta, _ = self._run()
        self.assertEqual(rc, 0)
        self.assertEqual(dirs, ["one", "two"])
        self.assertTrue(has_meta)
        self.assertIn("Portfolio", text)
        self.assertIn("one", text)
        self.assertIn("two", text)
        self.assertIn("Unconfigured git identity", text, "worst finding per repo is shown")

    def test_fail_on_looks_across_all_repos(self):
        rc, *_ = self._run(["--fail-on", "warning"])
        self.assertEqual(rc, 3)

    def test_markdown_export_writes_a_portfolio_file(self):
        rc, _, _, _, md = self._run(["--markdown", "portfolio.md"])
        self.assertEqual(rc, 0)
        self.assertTrue(md.startswith("# acme"), md[:40])
        self.assertIn("| repo |", md)


class GhFailures(unittest.TestCase):
    def test_listing_failure_is_reported_cleanly(self):
        def lister(owner):
            raise run.GhError("Post https://api.github.com/graphql: tls: failed to verify certificate")
        c = console()
        rc = cli.main(["acme/*"], console=c, tool_check=lambda **kw: [], lister=lister)
        text = c.export_text()
        self.assertEqual(rc, 2)
        self.assertIn("could not list repositories for acme", text)
        self.assertIn("failed to verify certificate", text)

    def test_clone_failure_is_reported_cleanly(self):
        def cloner(target, parent):
            raise run.GhError("repository not found")
        c = console()
        rc = cli.main(["acme/missing"], console=c, tool_check=lambda **kw: [], cloner=cloner)
        text = c.export_text()
        self.assertEqual(rc, 2)
        self.assertIn("could not clone acme/missing", text)
        self.assertIn("repository not found", text)


class FileTypes(unittest.TestCase):
    def test_list_file_types_prints_the_tree_and_exits(self):
        with tempfile.TemporaryDirectory() as d:
            _tiny_repo(d)
            for name in ["a.py", "notes.md"]:
                with open(os.path.join(d, name), "w") as fh: fh.write("x\n")
            import subprocess
            subprocess.run(["git", "-C", d, "add", "-A"], check=True)
            c = console()
            rc = cli.main([d, "--list-file-types"], console=c, tool_check=lambda **kw: [])
            text = c.export_text()
        self.assertEqual(rc, 0)
        self.assertRegex(text, r"\n▥ File types\n")
        self.assertRegex(text, r"py\s+1\s+yes")
        self.assertRegex(text, r"md\s+1\s+no")
        self.assertNotIn("Findings", text)

    def test_file_types_reach_the_planner(self):
        calls = []
        with tempfile.TemporaryDirectory() as d:
            _tiny_repo(d)
            def planner(repo, out, branch="HEAD", **kw):
                calls.append(kw)
                return [{"name": "q", "argv": ["true"], "stdout": None, "deps": []}]
            cli.main([d, "--out", os.path.join(d, "out"), "--file-types", "py, sql"], console=console(), tool_check=lambda **kw: [],
                     planner=planner, estimator=lambda repo, interval, **kw: {"files": 1, "samples": 1, "blames": 1, "seconds": 0.0})
        self.assertEqual(calls[0]["types"], "py,sql")

    def test_meta_records_the_file_types_so_a_re_render_filters_the_same_way(self):
        def meta_for(*extra):
            with tempfile.TemporaryDirectory() as d:
                _tiny_repo(d)
                out = os.path.join(d, "out")
                planner = lambda repo, o, branch="HEAD", **kw: [{"name": "q", "argv": ["true"], "stdout": None, "deps": []}]
                cli.main([d, "--out", out, *extra], console=console(), tool_check=lambda **kw: [], planner=planner,
                         estimator=lambda repo, interval, **kw: {"files": 1, "samples": 1, "blames": 1, "seconds": 0.0})
                with open(os.path.join(out, "meta.json")) as fh:
                    return json.load(fh)
        self.assertIsNone(meta_for()["file_types"])
        self.assertEqual(meta_for("--file-types", "py, sql")["file_types"], "py,sql")
        self.assertEqual(meta_for("--file-types", "all")["file_types"], "all")


class GoneWindow(unittest.TestCase):
    def _meta(self, *extra):
        with tempfile.TemporaryDirectory() as d:
            _tiny_repo(d)
            out = os.path.join(d, "out")
            planner = lambda repo, o, branch="HEAD", **kw: [{"name": "q", "argv": ["true"], "stdout": None, "deps": []}]
            cli.main([d, "--out", out, *extra], console=console(), tool_check=lambda **kw: [], planner=planner,
                     estimator=lambda repo, interval, **kw: {"files": 1, "samples": 1, "blames": 1, "seconds": 0.0})
            with open(os.path.join(out, "meta.json")) as fh:
                return json.load(fh)

    def test_default_twelve_months_recorded_and_flag_changes_it(self):
        self.assertEqual(self._meta()["gone_months"], 12)
        self.assertEqual(self._meta("--gone", "6")["gone_months"], 6)

    def test_the_default_is_the_window_the_loss_module_defines(self):
        from gitmole import loss
        self.assertEqual(cli.parse_args(["x"]).gone, loss.DEFAULT_MONTHS)


class Duplicates(unittest.TestCase):
    def test_off_by_default_and_on_with_the_flag(self):
        def planned(*extra):
            calls = []
            with tempfile.TemporaryDirectory() as d:
                _tiny_repo(d)
                def planner(repo, out, branch="HEAD", **kw):
                    calls.append(kw)
                    return [{"name": "q", "argv": ["true"], "stdout": None, "deps": []}]
                cli.main([d, "--out", os.path.join(d, "out"), *extra], console=console(), tool_check=lambda **kw: [], planner=planner,
                         estimator=lambda repo, interval, **kw: {"files": 1, "samples": 1, "blames": 1, "seconds": 0.0})
            return calls[0]["duplicates"]
        self.assertFalse(planned())
        self.assertTrue(planned("--duplicates"))


class ReferenceDate(unittest.TestCase):
    def _main(self, env, extra=()):
        from unittest.mock import patch
        calls = []
        with tempfile.TemporaryDirectory() as d, patch.dict(os.environ, env):
            _tiny_repo(d)
            def planner(repo, out, branch="HEAD", **kw):
                calls.append(kw)
                return [{"name": "q", "argv": ["true"], "stdout": None, "deps": []}]
            c = console()
            rc = cli.main([d, "--out", os.path.join(d, "out"), *extra], console=c, tool_check=lambda **kw: [], planner=planner,
                          estimator=lambda repo, interval, **kw: {"files": 1, "samples": 1, "blames": 1, "seconds": 0.0})
            meta_path = os.path.join(d, "out", "meta.json")
            meta = json.loads(pathlib.Path(meta_path).read_text()) if os.path.exists(meta_path) else {}
        return rc, c.export_text(), calls, meta

    def test_env_override_is_forwarded_recorded_and_announced(self):
        rc, text, calls, meta = self._main({"GITMOLE_NOW": "2025-06-15"})
        self.assertEqual(rc, 0)
        self.assertEqual(calls[0]["now"], "2025-06-15")
        self.assertEqual(meta["now"], "2025-06-15")
        self.assertIn("2025-06-15", text)

    def test_absent_override_means_today_and_nothing_recorded(self):
        rc, text, calls, meta = self._main({})
        self.assertIsNone(calls[0]["now"])
        self.assertNotIn("now", meta)

    def test_malformed_override_is_an_error(self):
        rc, text, calls, meta = self._main({"GITMOLE_NOW": "2025-6-15"})
        self.assertEqual(rc, 2)
        self.assertIn("GITMOLE_NOW", text)
        self.assertEqual(calls, [])


class Since(unittest.TestCase):
    def _main(self, extra, env=None):
        from unittest.mock import patch
        calls = []
        with tempfile.TemporaryDirectory() as d, patch.dict(os.environ, env or {}):
            _tiny_repo(d)
            def planner(repo, out, branch="HEAD", **kw):
                calls.append(kw)
                return [{"name": "q", "argv": ["true"], "stdout": None, "deps": []}]
            c = console()
            rc = cli.main([d, "--out", os.path.join(d, "out"), *extra], console=c, tool_check=lambda **kw: [], planner=planner,
                          estimator=lambda repo, interval, **kw: {"files": 1, "samples": 1, "blames": 1, "seconds": 0.0})
            meta_path = os.path.join(d, "out", "meta.json")
            meta = json.loads(pathlib.Path(meta_path).read_text()) if os.path.exists(meta_path) else {}
        return rc, c.export_text(), calls, meta

    def test_since_is_resolved_against_the_reference_date_and_recorded(self):
        rc, text, calls, meta = self._main(["--since", "2y"], {"GITMOLE_NOW": "2026-09-15"})
        self.assertEqual(rc, 0)
        self.assertEqual(calls[0]["since"], "2024-09-15")
        self.assertEqual(meta["since"], "2024-09-15")
        self.assertIn("since 2024-09-15", text)

    def test_bad_since_is_an_error(self):
        rc, text, calls, meta = self._main(["--since", "lately"])
        self.assertEqual(rc, 2)
        self.assertIn("--since", text)
        self.assertEqual(calls, [])

    def test_empty_window_is_an_error_not_an_empty_report(self):
        rc, text, calls, meta = self._main(["--since", "2030-01-01"])
        self.assertEqual(rc, 2)
        self.assertIn("no commits", text)
        self.assertEqual(calls, [])

    def test_since_is_refused_with_no_run(self):
        with tempfile.TemporaryDirectory() as out:
            _report_dir(out)
            c = console()
            rc = cli.main([out, "--no-run", "--since", "2y"], console=c)
        self.assertEqual(rc, 2)
        self.assertIn("--since", c.export_text())


class FullFlag(unittest.TestCase):
    def test_full_shows_the_score_column(self):
        with tempfile.TemporaryDirectory() as out:
            _report_dir(out)
            with open(os.path.join(out, "maat-revisions.csv"), "w") as fh:
                fh.write("entity,n-revs\na.py,3\n")
            with open(os.path.join(out, "size.json"), "w") as fh:
                json.dump([{"Name": "Python", "Count": 1, "Code": 10, "Comment": 0, "Blank": 0, "Complexity": 1,
                            "Files": [{"Location": "a.py", "Code": 10, "Complexity": 1}]}], fh)
            compact = console(); cli.main([out, "--no-run"], console=compact)
            full = console(); cli.main([out, "--no-run", "--full"], console=full)
        self.assertNotIn("score", compact.export_text())
        self.assertIn("score", full.export_text())


class Arguments(unittest.TestCase):
    def test_bad_target_is_reported_not_raised(self):
        c = console()
        rc = cli.main(["definitely not a repo"], console=c)
        self.assertEqual(rc, 2)
        self.assertIn("not a repo", c.export_text())

    def test_missing_tools_are_listed(self):
        with tempfile.TemporaryDirectory() as d:
            c = console()
            rc = cli.main([d], console=c, tool_check=lambda **kw: ["scc"])
        text = c.export_text()
        self.assertEqual(rc, 2)
        self.assertIn("scc", text)
        self.assertIn("install.sh", text)
        self.assertNotIn("jar", text)


class Risk(unittest.TestCase):
    def _repo(self, d):
        import subprocess
        def git(*args):
            e = dict(os.environ, GIT_CONFIG_GLOBAL="/dev/null", GIT_CONFIG_SYSTEM="/dev/null",
                     GIT_AUTHOR_NAME="A", GIT_AUTHOR_EMAIL="a@x", GIT_COMMITTER_NAME="A", GIT_COMMITTER_EMAIL="a@x")
            subprocess.run(["git", *args], cwd=d, check=True, capture_output=True, env=e)
        git("init", "-q", "-b", "main")
        with open(os.path.join(d, "a.py"), "w") as fh: fh.write("x\n")
        git("add", "-A"); git("commit", "-q", "-m", "base")
        git("switch", "-q", "-c", "feature")
        with open(os.path.join(d, "a.py"), "a") as fh: fh.write("y\n")
        git("commit", "-q", "-am", "work")

    def test_risk_section_after_a_run_and_on_a_re_render(self):
        with tempfile.TemporaryDirectory() as d:
            self._repo(d)
            out = os.path.join(d, "out")
            planner = lambda repo, o, branch="HEAD", **kw: [{"name": "q", "argv": ["true"], "stdout": None, "deps": []}]
            c = console()
            rc = cli.main([d, "--out", out, "--risk", "main"], console=c, tool_check=lambda **kw: [], planner=planner,
                          estimator=lambda repo, interval, **kw: {"files": 1, "samples": 1, "blames": 1, "seconds": 0.0})
            self.assertEqual(rc, 0)
            text = c.export_text()
            self.assertIn("Change risk (1 files since main)", text)
            self.assertRegex(text, r"a\.py\s+new file", "the stub planner writes no size.json, so a.py is not in the tree data")
            c = console()
            rc = cli.main([out, "--no-run", "--risk", "main"], console=c)
            self.assertEqual(rc, 0)
            text = c.export_text()
            self.assertIn("Change risk (1 files since main)", text)
            self.assertRegex(text, r"a\.py\s+new file", "the stub planner writes no size.json, so a.py is not in the tree data")

    def test_unknown_base_is_an_error(self):
        with tempfile.TemporaryDirectory() as d:
            self._repo(d)
            out = os.path.join(d, "out")
            planner = lambda repo, o, branch="HEAD", **kw: [{"name": "q", "argv": ["true"], "stdout": None, "deps": []}]
            c = console()
            rc = cli.main([d, "--out", out, "--risk", "nope"], console=c, tool_check=lambda **kw: [], planner=planner,
                          estimator=lambda repo, interval, **kw: {"files": 1, "samples": 1, "blames": 1, "seconds": 0.0})
            self.assertEqual(rc, 2)
            self.assertIn("nope", c.export_text())

    def test_remote_targets_refuse_risk(self):
        c = console()
        rc = cli.main(["owner/repo", "--risk", "main"], console=c, tool_check=lambda **kw: [])
        self.assertEqual(rc, 2)
        self.assertIn("--risk needs a local path", c.export_text())


class BacktestWindow(unittest.TestCase):
    def _run(self, dates, *extra):
        import subprocess
        calls = []
        with tempfile.TemporaryDirectory() as d:
            subprocess.run(["git", "init", "-q", d], check=True)
            for date in dates:
                subprocess.run(["git", "-C", d, "-c", "user.name=T", "-c", "user.email=t@x.com", "commit", "-q", "--allow-empty", "-m", date],
                               check=True, env=dict(os.environ, GIT_AUTHOR_DATE=f"{date}T10:00:00", GIT_COMMITTER_DATE=f"{date}T10:00:00"))
            out = os.path.join(d, "out")
            def planner(repo, o, branch="HEAD", **kw):
                calls.append(kw)
                return [{"name": "q", "argv": ["true"], "stdout": None, "deps": []}]
            cli.main([d, "--out", out, *extra], console=console(), tool_check=lambda **kw: [], planner=planner,
                     estimator=lambda repo, interval, **kw: {"files": 1, "samples": 1, "blames": 1, "seconds": 0.0})
            with open(os.path.join(out, "meta.json")) as fh:
                return calls[0], json.load(fh)

    def test_cut_off_six_months_before_the_last_commit_with_a_year_of_history(self):
        kw, meta = self._run(["2025-01-01", "2025-08-01", "2026-03-01"])
        self.assertEqual(kw["backtest"], "2025-09-01")
        self.assertEqual(meta["backtest"], {"status": "planned", "until": "2025-09-01"})

    def test_since_does_not_narrow_the_history_the_backtest_measures(self):
        kw, meta = self._run(["2025-01-01", "2025-08-01", "2026-03-01"], "--since", "2026-01-01")
        self.assertEqual(kw["backtest"], "2025-09-01", "the window narrows the analysis, not the backtest")
        self.assertEqual(meta["backtest"], {"status": "planned", "until": "2025-09-01"})

    def test_too_little_history_skips(self):
        kw, meta = self._run(["2025-06-01", "2026-03-01"])
        self.assertIsNone(kw["backtest"])
        self.assertEqual(meta["backtest"], {"status": "skipped", "reason": "too little history to backtest"})


if __name__ == "__main__":
    unittest.main()

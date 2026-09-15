import io
import json
import os
import tempfile
import unittest

from rich.console import Console

from gitmole import cli


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
            rc = cli.main([d, "--out", os.path.join(d, "out")], console=c, tool_check=lambda: [], planner=fake_plan)
            text = c.export_text()
        self.assertEqual(rc, 0)
        self.assertIn("███╗   ███╗", text)
        self.assertIn("1 steps in", text)
        self.assertIn(os.path.basename(d), text)


def _tiny_repo(d):
    import subprocess
    subprocess.run(["git", "init", "-q", d], check=True)
    subprocess.run(["git", "-C", d, "-c", "user.name=T", "-c", "user.email=t@x.com", "commit", "-q", "--allow-empty", "-m", "x"], check=True)


class Budget(unittest.TestCase):
    def _main(self, extra, estimate, plan_calls):
        with tempfile.TemporaryDirectory() as d:
            _tiny_repo(d)
            c = console()
            def planner(repo, out, branch="HEAD", **kw):
                plan_calls.append(kw)
                return [{"name": "quick", "argv": ["sh", "-c", "true"], "stdout": None, "deps": []}]
            rc = cli.main([d, "--out", os.path.join(d, "out"), *extra], console=c,
                          tool_check=lambda: [], planner=planner, estimator=lambda repo, interval: estimate)
            with open(os.path.join(d, "out", "meta.json")) as fh:
                meta = json.load(fh)
            return rc, c.export_text(), meta

    BIG = {"files": 80000, "samples": 11, "blames": 880000}
    SMALL = {"files": 100, "samples": 5, "blames": 500}

    def test_code_age_runs_by_default_and_plots_do_not(self):
        calls = []
        _, text, meta = self._main([], self.SMALL, calls)
        self.assertTrue(calls[0]["age"])
        self.assertFalse(calls[0]["plots"])
        self.assertEqual(meta["age"]["status"], "run")
        self.assertNotIn("skipped", text)

    def test_code_age_skipped_when_files_exceed_budget(self):
        calls = []
        rc, text, meta = self._main([], self.BIG, calls)
        self.assertEqual(rc, 0)
        self.assertFalse(calls[0]["age"])
        self.assertIn("80,000", text)
        self.assertIn("--deep", text)
        self.assertEqual(meta["age"]["status"], "skipped")

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

    def test_budget_flag_changes_the_threshold(self):
        calls = []
        self._main(["--budget", "1000000"], self.BIG, calls)
        self.assertTrue(calls[0]["age"])

    def test_ignore_data_and_custom_ignores_reach_the_planner(self):
        calls = []
        self._main(["--ignore-data", "--ignore", "docs/**"], self.SMALL, calls)
        self.assertIn("*.csv", calls[0]["ignore"])
        self.assertIn("docs/**", calls[0]["ignore"])

    def test_no_ignores_by_default(self):
        calls = []
        self._main([], self.SMALL, calls)
        self.assertEqual(list(calls[0]["ignore"]), [])


class Timeout(unittest.TestCase):
    def test_timed_out_step_is_reported(self):
        with tempfile.TemporaryDirectory() as d:
            _tiny_repo(d)
            c = console()
            planner = lambda repo, out, branch="HEAD", **kw: [
                {"name": "sleepy", "argv": ["sh", "-c", "sleep 3"], "stdout": None, "deps": []}]
            cli.main([d, "--out", os.path.join(d, "out"), "--timeout", "0.3"], console=c,
                     tool_check=lambda: [], planner=planner, estimator=lambda repo, interval: {"files": 1, "samples": 1, "blames": 1})
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


class Arguments(unittest.TestCase):
    def test_bad_target_is_reported_not_raised(self):
        c = console()
        rc = cli.main(["definitely not a repo"], console=c)
        self.assertEqual(rc, 2)
        self.assertIn("not a repo", c.export_text())

    def test_missing_tools_are_listed(self):
        with tempfile.TemporaryDirectory() as d:
            c = console()
            rc = cli.main([d], console=c, tool_check=lambda: ["scc"])
        text = c.export_text()
        self.assertEqual(rc, 2)
        self.assertIn("scc", text)
        self.assertIn("install.sh", text)
        self.assertNotIn("jar", text)


if __name__ == "__main__":
    unittest.main()

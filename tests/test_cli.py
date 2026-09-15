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

    def test_skips_theseus_over_budget_and_says_how_to_force(self):
        calls = []
        rc, text, meta = self._main([], {"files": 30000, "samples": 11, "blames": 330000}, calls)
        self.assertEqual(rc, 0)
        self.assertFalse(calls[0]["theseus"])
        self.assertIn("330,000", text)
        self.assertIn("--deep", text)
        self.assertEqual(meta["theseus"]["status"], "skipped")

    def test_runs_theseus_under_budget(self):
        calls = []
        _, text, meta = self._main([], {"files": 100, "samples": 5, "blames": 500}, calls)
        self.assertTrue(calls[0]["theseus"])
        self.assertEqual(meta["theseus"]["status"], "run")
        self.assertNotIn("skipped", text)

    def test_deep_forces_theseus_regardless_of_budget(self):
        calls = []
        self._main(["--deep"], {"files": 30000, "samples": 11, "blames": 330000}, calls)
        self.assertTrue(calls[0]["theseus"])

    def test_budget_flag_changes_the_threshold(self):
        calls = []
        self._main(["--budget", "1000000"], {"files": 30000, "samples": 11, "blames": 330000}, calls)
        self.assertTrue(calls[0]["theseus"])

    def test_ignore_data_and_custom_ignores_reach_the_planner(self):
        calls = []
        self._main(["--ignore-data", "--ignore", "docs/**"], {"files": 1, "samples": 1, "blames": 1}, calls)
        self.assertIn("*.csv", calls[0]["ignore"])
        self.assertIn("docs/**", calls[0]["ignore"])

    def test_no_ignores_by_default(self):
        calls = []
        self._main([], {"files": 1, "samples": 1, "blames": 1}, calls)
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

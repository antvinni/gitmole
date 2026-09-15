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
            fake_plan = lambda repo, out, jar, branch="HEAD": [
                {"name": "quick", "argv": ["sh", "-c", "sleep 0.3"], "stdout": None, "deps": []}]
            rc = cli.main([d, "--out", os.path.join(d, "out"), "--jar", "/x.jar"], console=c, tool_check=lambda jar: [], planner=fake_plan)
            text = c.export_text()
        self.assertEqual(rc, 0)
        self.assertIn("███╗   ███╗", text)
        self.assertIn("1 steps in", text)
        self.assertIn(os.path.basename(d), text)


class Arguments(unittest.TestCase):
    def test_bad_target_is_reported_not_raised(self):
        c = console()
        rc = cli.main(["definitely not a repo"], console=c)
        self.assertEqual(rc, 2)
        self.assertIn("not a repo", c.export_text())

    def test_missing_tools_are_listed(self):
        with tempfile.TemporaryDirectory() as d:
            c = console()
            rc = cli.main([d, "--jar", "/nope/code-maat.jar"], console=c, tool_check=lambda jar: ["scc", jar])
        text = c.export_text()
        self.assertEqual(rc, 2)
        self.assertIn("scc", text)
        self.assertIn("install.sh", text)


if __name__ == "__main__":
    unittest.main()

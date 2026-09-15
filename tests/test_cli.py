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

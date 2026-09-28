"""The docs keep up with the command line: every option --help prints is in docs/cli.md, and --help fits 80 columns."""
import os
import re
import unittest
from unittest import mock

from gitmole import cli

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LONG_OPTION = re.compile(r"(?<![\w-])--[a-z][a-z-]*[a-z]")


def _help(columns: int = 80) -> str:
    with mock.patch.dict(os.environ, {"COLUMNS": str(columns)}):
        return cli.build_parser().format_help()


def _read(*path) -> str:
    with open(os.path.join(ROOT, *path), encoding="utf-8") as f:
        return f.read()


class CliDocsTest(unittest.TestCase):
    def test_every_option_help_prints_has_a_row_in_cli_md(self):
        printed = set(LONG_OPTION.findall(_help()))
        self.assertIn("--install-tools", printed, "the pattern must see the options --help prints")
        # the first cell of a row in the Options tables: | `--sarif-scope SCOPE` | ... or | `-h`, `--help` | ...
        first_cells = re.findall(r"^\| ([^|]*`[^|]*) \|", _read("docs", "cli.md"), re.M)
        documented = {o for cell in first_cells for o in LONG_OPTION.findall(cell)}
        self.assertEqual(sorted(printed - documented), [], "options --help prints with no row in docs/cli.md's Options")

    def test_every_parser_option_is_printed_or_deliberately_hidden(self):
        printed = set(LONG_OPTION.findall(_help()))
        hidden = {"--duplicates"}   # a no-op kept so older scripts still parse
        options = {o for a in cli.build_parser()._actions for o in a.option_strings if o.startswith("--")}
        self.assertEqual(options - printed, hidden)

    def test_help_fits_eighty_columns(self):
        wide = [line for line in _help(80).splitlines() if len(line) > 80]
        self.assertEqual(wide, [])

    def test_help_gives_each_option_one_line(self):
        # a description that wraps is prose that belongs in docs/cli.md; the target and the options
        # whose name and metavar push the description onto its own line are the only two-line entries
        lines = _help(80).splitlines()
        wrapped = [lines[i - 1].strip() for i, line in enumerate(lines)
                   if i and line.startswith(" " * 24) and lines[i - 1].startswith("  --")
                   and len(lines[i - 1].strip().split("  ")) > 1]
        self.assertEqual(wrapped, [])

    def test_full_is_described_as_a_report_option(self):
        line = next(line for line in _help().splitlines() if line.strip().startswith("--full"))
        self.assertIn("report", line)

    def test_install_and_doctor_are_in_readme_and_install_md(self):
        for doc in (_read("README.md"), _read("docs", "install.md")):
            self.assertIn("gitmole --install-tools", doc)
            self.assertIn("gitmole --doctor", doc)

    def test_first_report_page_is_linked(self):
        self.assertTrue(os.path.exists(os.path.join(ROOT, "docs", "first-report.md")))
        self.assertIn("first-report.md", _read("README.md"))
        self.assertIn("first-report.md", _read("docs", "output.md"))

    def test_no_user_facing_snippet_pins_an_old_release(self):
        for path in (".pre-commit-hooks.yaml", "docs/cli.md", "README.md", "docs/install.md"):
            self.assertEqual(re.findall(r"rev: v\d+\.\d+\.\d+", _read(path)), [], path)


if __name__ == "__main__":
    unittest.main()

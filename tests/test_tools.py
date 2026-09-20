import os
import re
import unittest

from gitmole import run, tools

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FORMULA = os.path.join(ROOT, "Formula", "gitmole.rb")


def formula() -> str:
    with open(FORMULA, encoding="utf-8") as fh:
        return fh.read()


class Pinned(unittest.TestCase):
    def test_every_tool_the_run_needs_is_pinned(self):
        self.assertEqual(sorted(tools.PINNED), sorted(run.REQUIRED_TOOLS + ["lizard"]))

    def test_the_formula_installs_the_pinned_versions(self):
        # the formula names each version in its resource urls; a bump in one place and not the other is the bug this catches
        text = formula()
        for name, version in tools.PINNED.items():
            with self.subTest(tool=name):
                self.assertRegex(text, rf'resource "{re.escape(name)}" do\n(?:.*\n)*?\s*url "[^"]*{re.escape(version)}[^"]*"', f"{name} {version}")

    def test_the_wrapper_puts_the_pinned_tools_first_on_the_path(self):
        self.assertIn('libexec/"tools"', formula())

    def test_differences_names_only_the_tools_that_moved(self):
        found = {"scc": "4.1.0", "git-sizer": "1.6.0", "betterleaks": None, "jscpd": "5.3.0",
                 "osv-scanner": "2.6.0", "lizard": "1.24.0"}
        self.assertEqual(tools.differences(found), [("git-sizer", "1.5.0", "1.6.0")], "a missing tool is not a difference")
        self.assertEqual(tools.differences({}), [])
        self.assertEqual(tools.differences({k: v for k, v in tools.PINNED.items()}), [])

    def test_the_note_names_both_versions(self):
        self.assertIsNone(tools.note(dict(tools.PINNED)))
        note = tools.note({**tools.PINNED, "scc": "4.2.0"})
        self.assertEqual(note, "tool versions differ from the pinned set: scc 4.2.0, pinned 4.1.0")


class Manifest(unittest.TestCase):
    def test_the_manifest_records_the_pinned_versions_beside_what_it_found(self):
        class Args:
            ignore, ignore_data, deep, plots = [], False, False, False
        found = {**tools.PINNED, "git": "2.51.0", "scc": "4.2.0"}
        m = run.manifest(ROOT, Args(), version_of=lambda name, path=None: found.get(name), lizard_of=lambda: found["lizard"])
        self.assertEqual(m["tools_pinned"], tools.PINNED)
        self.assertEqual(m["tools_moved"], [{"tool": "scc", "pinned": "4.1.0", "found": "4.2.0"}])
        self.assertEqual(m["tools"]["scc"], "4.2.0")


if __name__ == "__main__":
    unittest.main()

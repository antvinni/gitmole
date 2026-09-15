import os
import subprocess
import tempfile
import unittest

from gitmole import filetypes


class Parse(unittest.TestCase):
    def test_default_when_unset(self):
        self.assertIs(filetypes.parse(None), filetypes.DEFAULT)
        self.assertIn("py", filetypes.DEFAULT)
        self.assertIn("sql", filetypes.DEFAULT)
        self.assertNotIn("md", filetypes.DEFAULT)
        self.assertNotIn("json", filetypes.DEFAULT)

    def test_comma_list_normalised(self):
        self.assertEqual(filetypes.parse(" Py, .SQL ,ts"), {"py", "sql", "ts"})

    def test_all_means_no_filter(self):
        self.assertIsNone(filetypes.parse("all"))


class Matches(unittest.TestCase):
    def test_extension_and_special_names(self):
        self.assertTrue(filetypes.matches("src/a.py", filetypes.DEFAULT))
        self.assertTrue(filetypes.matches("Makefile", filetypes.DEFAULT))
        self.assertTrue(filetypes.matches("deploy/Dockerfile", filetypes.DEFAULT))
        self.assertFalse(filetypes.matches("README.md", filetypes.DEFAULT))
        self.assertFalse(filetypes.matches("data/x.csv", filetypes.DEFAULT))
        self.assertTrue(filetypes.matches("anything.xyz", None))

    def test_custom_set(self):
        self.assertTrue(filetypes.matches("a.sql", {"sql"}))
        self.assertFalse(filetypes.matches("a.py", {"sql"}))


class Discover(unittest.TestCase):
    def test_counts_extensions_in_the_tree_and_marks_included(self):
        with tempfile.TemporaryDirectory() as d:
            subprocess.run(["git", "init", "-q", d], check=True)
            for name in ["a.py", "b.py", "c.md", "Makefile", "d.CSV"]:
                open(os.path.join(d, name), "w").write("x\n")
            subprocess.run(["git", "-C", d, "add", "-A"], check=True)
            rows = filetypes.discover(d, filetypes.DEFAULT)
        self.assertEqual(rows, [("py", 2, True), ("csv", 1, False), ("makefile", 1, True), ("md", 1, False)])


if __name__ == "__main__":
    unittest.main()

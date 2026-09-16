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


class GitPaths(unittest.TestCase):
    def _repo(self, d):
        subprocess.run(["git", "init", "-q", d], check=True)
        for name in ["a.py", "s\u00e4.py", 'q"uote.py', "tab\tx.py"]:
            with open(os.path.join(d, name), "w") as fh: fh.write("x\n")
        subprocess.run(["git", "-C", d, "add", "-A"], check=True)
        # a Latin-1 name that is not valid UTF-8, straight into the index
        blob = subprocess.run(["git", "-C", d, "hash-object", "-w", "--stdin"], input=b"x\n", capture_output=True, check=True).stdout.decode().strip()
        subprocess.run(["git", "-C", d, "update-index", "--add", "--cacheinfo", "100644", blob, "caf\xe9.py".encode("latin-1").decode("utf-8", "surrogateescape")], check=True)

    def test_lists_paths_unquoted_and_never_raises(self):
        with tempfile.TemporaryDirectory() as d:
            self._repo(d)
            paths = filetypes.git_paths(d, "ls-files")
        self.assertIn("s\u00e4.py", paths)
        self.assertIn('q"uote.py', paths)
        self.assertIn("tab\tx.py", paths)
        self.assertFalse([p for p in paths if p.startswith('"')])
        self.assertTrue([p for p in paths if p.startswith("caf")], "the non-UTF-8 name survives decoding")

    def test_discover_uses_the_same_lister(self):
        with tempfile.TemporaryDirectory() as d:
            self._repo(d)
            rows = dict((k, n) for k, n, _ in filetypes.discover(d, filetypes.DEFAULT))
        self.assertEqual(rows.get("py"), 5)
        self.assertFalse([k for k in rows if k.endswith('"')])


class Unquote(unittest.TestCase):
    def test_octal_escapes_quotes_and_mixed_raw_utf8(self):
        self.assertEqual(filetypes.unquote('"src/\\303\\244.py"'), "src/\u00e4.py")
        self.assertEqual(filetypes.unquote('"say \\"hi\\".md"'), 'say "hi".md')
        self.assertEqual(filetypes.unquote('"d\\t\u00e4/x.py"'), "d\t\u00e4/x.py")
        self.assertEqual(filetypes.unquote("plain/path.py"), "plain/path.py")
        self.assertEqual(filetypes.unquote('"bad/\\344dir/x.py"'), "bad/\ufffddir/x.py", "undecodable bytes become U+FFFD, never a raw escape")


class Discover(unittest.TestCase):
    def test_counts_extensions_in_the_tree_and_marks_included(self):
        with tempfile.TemporaryDirectory() as d:
            subprocess.run(["git", "init", "-q", d], check=True)
            for name in ["a.py", "b.py", "c.md", "Makefile", "d.CSV"]:
                with open(os.path.join(d, name), "w") as fh: fh.write("x\n")
            subprocess.run(["git", "-C", d, "add", "-A"], check=True)
            rows = filetypes.discover(d, filetypes.DEFAULT)
        self.assertEqual(rows, [("py", 2, True), ("csv", 1, False), ("makefile", 1, True), ("md", 1, False)])



class TestPaths(unittest.TestCase):
    def test_test_files_and_directories(self):
        for path in ("tests/test_a.py", "a/spec/b.rb", "src/__tests__/x.js", "x/y_test.go", "app.spec.ts", "app.test.tsx", "test_x.py"):
            self.assertTrue(filetypes.is_test_path(path), path)
        for path in ("src/contest.py", "gitmole/render.py", "attest/x.py", "latest.md"):
            self.assertFalse(filetypes.is_test_path(path), path)

    def test_documentation_files_and_directories(self):
        for path in ("README.md", "docs/GA4-API-INTEGRATION.md", "doc/guide.rst", "NOTES.txt", "a/b/CHANGELOG.markdown", "docs/conf.py", "x.adoc"):
            self.assertTrue(filetypes.is_doc_path(path), path)
        for path in ("app/settings.py", "static/index.html", "docsite/app.js", "mdx/a.py", "config.yaml"):
            self.assertFalse(filetypes.is_doc_path(path), path)


if __name__ == "__main__":
    unittest.main()

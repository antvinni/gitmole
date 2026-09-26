import os
import subprocess
import tempfile
import unittest
from unittest import mock

from gitmole import clean, tools


def _output(path):
    os.makedirs(path, exist_ok=True)
    with open(os.path.join(path, "meta.json"), "w") as fh:
        fh.write("{}")
    with open(os.path.join(path, "size.json"), "w") as fh:
        fh.write("x" * 100)


def _no_tools(case):
    """Point the tool root at an empty directory, so this machine's own installed tools are never listed."""
    d = tempfile.TemporaryDirectory()
    case.addCleanup(d.cleanup)
    patcher = mock.patch.dict(os.environ, {"GITMOLE_TOOLS": d.name})
    patcher.start()
    case.addCleanup(patcher.stop)
    return d.name


class Find(unittest.TestCase):
    def setUp(self):
        self.tools = _no_tools(self)

    def test_tools_for_pins_no_longer_used_are_listed_and_the_current_ones_are_not(self):
        current = os.path.join(self.tools, f"scc-{tools.PINNED['scc']}")
        old = os.path.join(self.tools, "scc-4.0.9")
        mixed = os.path.join(self.tools, "jscpd-1.0")   # holds more than the tool: not a directory the installer made
        for d in (current, old, mixed, os.path.join(self.tools, "notes")):
            os.makedirs(d)
        for path, data in ((os.path.join(old, "scc"), b"x" * 7), (os.path.join(mixed, "jscpd"), b"j"), (os.path.join(mixed, "mine"), b"m"),
                           (os.path.join(self.tools, "jscpd"), b"the user's own, in a shared GITMOLE_TOOLS")):
            with open(path, "wb") as fh:
                fh.write(data)
        with tempfile.TemporaryDirectory() as d, tempfile.TemporaryDirectory() as tmp:
            found = clean.find(d, tmp)
        self.assertEqual([(p, size) for p, size, _ in found], [(old, 7)], "a loose file and a mixed directory are the user's")
        self.assertEqual(clean.remove([old]), [])
        self.assertEqual(sorted(os.listdir(self.tools)), sorted([os.path.basename(current), "jscpd", "jscpd-1.0", "notes"]))

    def test_output_directory_with_meta_is_found_and_one_without_is_not(self):
        with tempfile.TemporaryDirectory() as d, tempfile.TemporaryDirectory() as tmp:
            _output(os.path.join(d, "analysis-a"))
            os.makedirs(os.path.join(d, "analysis-b"))
            found = clean.find(d, tmp)
        self.assertEqual([p for p, _, _ in found], [os.path.join(d, "analysis-a")])

    def test_size_and_mtime_come_with_the_path(self):
        with tempfile.TemporaryDirectory() as d, tempfile.TemporaryDirectory() as tmp:
            _output(os.path.join(d, "analysis-a"))
            [(path, size, mtime)] = clean.find(d, tmp)
        self.assertEqual(size, 102)   # meta.json "{}" plus 100 bytes
        self.assertGreater(mtime, 0)

    def test_whole_portfolio_is_listed_once(self):
        with tempfile.TemporaryDirectory() as d, tempfile.TemporaryDirectory() as tmp:
            pf = os.path.join(d, "analysis-acme")
            _output(os.path.join(pf, "one"))
            _output(os.path.join(pf, "two"))
            with open(os.path.join(pf, "portfolio.md"), "w") as fh:
                fh.write("# acme\n")
            with open(os.path.join(pf, ".DS_Store"), "w") as fh:
                fh.write("")
            found = clean.find(d, tmp)
        self.assertEqual([p for p, _, _ in found], [pf])

    def test_partial_portfolio_lists_its_children(self):
        with tempfile.TemporaryDirectory() as d, tempfile.TemporaryDirectory() as tmp:
            pf = os.path.join(d, "analysis-acme")
            _output(os.path.join(pf, "one"))
            os.makedirs(os.path.join(pf, "notes"))
            found = clean.find(d, tmp)
        self.assertEqual([p for p, _, _ in found], [os.path.join(pf, "one")])

    def test_temp_clones_come_first_oldest_first_and_only_from_tmp(self):
        with tempfile.TemporaryDirectory() as d, tempfile.TemporaryDirectory() as tmp:
            newer = os.path.join(tmp, "gitmole-bbb")
            older = os.path.join(tmp, "gitmole-aaa")
            os.makedirs(newer)
            os.makedirs(older)
            os.utime(older, (1, 1))
            os.utime(newer, (2, 2))
            os.makedirs(os.path.join(d, "gitmole-under-base"))
            _output(os.path.join(d, "analysis-a"))
            found = clean.find(d, tmp)
        self.assertEqual([p for p, _, _ in found], [older, newer, os.path.join(d, "analysis-a")])

    def test_a_clone_as_base_includes_its_own_output_next_to_it(self):
        with tempfile.TemporaryDirectory() as d, tempfile.TemporaryDirectory() as tmp:
            repo = os.path.join(d, "widgets")
            subprocess.run(["git", "init", "-q", repo], check=True)
            _output(os.path.join(d, "analysis-widgets"))
            found = clean.find(repo, tmp)
        self.assertEqual([p for p, _, _ in found], [os.path.join(d, "analysis-widgets")])

    def test_nothing_found_is_an_empty_list(self):
        with tempfile.TemporaryDirectory() as d, tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(clean.find(d, tmp), [])


class Human(unittest.TestCase):
    def test_boundaries(self):
        self.assertEqual(clean.human(0), "0 B")
        self.assertEqual(clean.human(999), "999 B")
        self.assertEqual(clean.human(1200), "1.2 kB")
        self.assertEqual(clean.human(1_200_000), "1.2 MB")
        self.assertEqual(clean.human(340_000_000), "340 MB")
        self.assertEqual(clean.human(2_100_000_000), "2.1 GB")


class Remove(unittest.TestCase):
    def test_removes_trees_and_reports_what_is_left(self):
        with tempfile.TemporaryDirectory() as d:
            gone = os.path.join(d, "analysis-a")
            _output(gone)
            failed = clean.remove([gone, os.path.join(d, "never-existed")])
            self.assertFalse(os.path.exists(gone))
        self.assertEqual(failed, [])


class TempDir(unittest.TestCase):
    def test_honours_tmpdir(self):
        with tempfile.TemporaryDirectory() as d:
            old = os.environ.get("TMPDIR")
            os.environ["TMPDIR"] = d
            try:
                self.assertEqual(clean.temp_dir(), d)
            finally:
                if old is None:
                    del os.environ["TMPDIR"]
                else:
                    os.environ["TMPDIR"] = old

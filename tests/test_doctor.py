import io
import unittest

from rich.console import Console

from gitmole import doctor, tools


def console():
    return Console(file=io.StringIO(), width=100, record=True, force_terminal=False, color_system=None)


def pinned_everywhere(name):
    return tools.PINNED[name]


class Rows(unittest.TestCase):
    def test_every_tool_at_its_pin_is_ok(self):
        rows = doctor.rows(present=lambda n: True, version_of=pinned_everywhere)
        self.assertEqual([r["tool"] for r in rows], ["scc", "git-sizer", "betterleaks", "jscpd", "osv-scanner", "lizard"])
        self.assertEqual({r["state"] for r in rows}, {"ok"})

    def test_a_missing_tool_a_moved_one_and_a_silent_one(self):
        versions = {**tools.PINNED, "git-sizer": "1.4.0", "betterleaks": None}
        rows = doctor.rows(present=lambda n: n != "jscpd", version_of=versions.get)
        state = {r["tool"]: r["state"] for r in rows}
        self.assertEqual(state["jscpd"], "missing")
        self.assertEqual(state["git-sizer"], "moved")
        self.assertEqual(state["betterleaks"], "no version")
        self.assertEqual(state["scc"], "ok")


class Main(unittest.TestCase):
    def test_all_ok_exits_0_and_names_the_database(self):
        c = console()
        rc = doctor.main(c, rows_of=lambda: doctor.rows(present=lambda n: True, version_of=pinned_everywhere),
                         structure_of=lambda: True, db_of=lambda: "2026-09-20")
        text = c.export_text()
        self.assertEqual(rc, 0)
        self.assertIn("2026-09-20", text)
        self.assertIn("available", text)
        oks = [l for l in text.splitlines() if l.endswith("  ok")]
        self.assertEqual(len(oks), 6)
        self.assertEqual(len({len(l) for l in oks}), 1)   # the versions line up, 1.24.0 beside 4.1.0

    def test_a_moved_tool_exits_1_and_says_where_to_get_the_pin(self):
        versions = {**tools.PINNED, "git-sizer": "1.4.0"}
        c = console()
        rc = doctor.main(c, rows_of=lambda: doctor.rows(present=lambda n: True, version_of=versions.get),
                         structure_of=lambda: False, db_of=lambda: None)
        text = c.export_text()
        self.assertEqual(rc, 1)
        self.assertIn("1.4.0", text)
        self.assertIn("pinned 1.5.0", text)
        self.assertIn("brew install gitmole", text)
        self.assertIn("Python 3.10", text)                 # why the structure step is skipped
        self.assertIn("--download-offline-databases", text)  # how to get the database
        command = next(l for l in text.splitlines() if "osv-scanner scan source" in l)
        self.assertIn("--download-offline-databases .", command)   # soft_wrap: the command is one pasteable line


if __name__ == "__main__":
    unittest.main()

import json
import os
import tempfile
import unittest

from gitmole import maat

LOG = """--a1--2026-01-10T09:15:00+00:00--Ann--feat: initial layout
3\t1\tsrc/a.py
2\t0\tsrc/b.py

--b2--2026-02-10T14:00:00+00:00--Bob--Add logo -- and docs
1\t1\tsrc/a.py
5\t5\tsrc/b.py
-\t-\timg/logo.png

--c3--2026-03-10T09:30:00+00:00--Ann--fix(core): crash on empty input
4\t0\tsrc/a.py
1\t0\tsrc/c.py

--d4--2026-03-12T22:00:00+00:00--Ann--Refactor helpers
1\t0\tsrc/a.py
1\t0\tsrc/b.py

--e5--2026-04-01T09:00:00+00:00--Ann--Fixed the off-by-one in b
1\t0\tsrc/a.py
1\t0\tsrc/b.py

--f6--2026-04-02T09:45:00+00:00--Ann--prefix cleanup
1\t0\tsrc/a.py
1\t0\tsrc/b.py

--g7--2026-04-03T11:00:00+00:00--Cat--Hotfix: regression in a
0\t2\tsrc/a.py
0\t1\tsrc/b.py
"""


class ParseLog(unittest.TestCase):
    def test_commits_with_files_and_binary_entries(self):
        commits = maat.parse_log(LOG)
        self.assertEqual(len(commits), 7)
        self.assertEqual(commits[0]["author"], "Ann")
        self.assertEqual(commits[0]["date"], "2026-01-10")
        self.assertEqual(commits[0]["time"], "2026-01-10T09:15:00+00:00")
        self.assertEqual(commits[0]["subject"], "feat: initial layout")
        self.assertEqual(commits[1]["subject"], "Add logo -- and docs", "double dashes inside a subject survive")
        self.assertEqual(commits[0]["files"], [("src/a.py", 3, 1), ("src/b.py", 2, 0)])
        self.assertEqual(commits[1]["files"][2], ("img/logo.png", 0, 0))

    def test_subjects_with_exotic_line_break_characters_do_not_split_the_log(self):
        # U+2028 and form feed are line breaks to str.splitlines but not to git
        text = "--x--2026-05-04T10:00:00+00:00--Ann--Fix\u2028broken\x0cthing\n1\t0\tf.py\n"
        commits = maat.parse_log(text)
        self.assertEqual(len(commits), 1)
        self.assertEqual(commits[0]["files"], [("f.py", 1, 0)])
        self.assertTrue(maat.is_fix(commits[0]["subject"]))

    def test_old_logs_without_subjects_still_parse(self):
        commits = maat.parse_log("--x--2026-05-04--Ann\n1\t0\tf.py\n")
        self.assertEqual(commits[0]["subject"], "")
        self.assertEqual(commits[0]["files"], [("f.py", 1, 0)])


class Revisions(unittest.TestCase):
    def test_counts_commits_per_entity(self):
        rows = maat.revisions(maat.parse_log(LOG))
        self.assertEqual(rows[0], {"entity": "src/a.py", "n-revs": 7})
        self.assertEqual(dict((r["entity"], r["n-revs"]) for r in rows)["src/c.py"], 1)


class Coupling(unittest.TestCase):
    def test_degree_is_shared_over_average_revisions(self):
        rows = maat.coupling(maat.parse_log(LOG))
        # a.py: 7 revs, b.py: 6 revs, shared: 6 -> degree 6 / 6.5 = 92%, average-revs 7 (rounded 6.5)
        self.assertEqual(rows, [{"entity": "src/a.py", "coupled": "src/b.py", "degree": 92, "average-revs": 7}])

    def test_pairs_below_thresholds_are_dropped(self):
        rows = maat.coupling(maat.parse_log(LOG), min_shared=7)
        self.assertEqual(rows, [])


class Authors(unittest.TestCase):
    def test_distinct_authors_and_revisions_per_entity(self):
        rows = {r["entity"]: r for r in maat.authors(maat.parse_log(LOG))}
        self.assertEqual(rows["src/a.py"], {"entity": "src/a.py", "n-authors": 3, "n-revs": 7})
        self.assertEqual(rows["src/c.py"]["n-authors"], 1)


class Age(unittest.TestCase):
    def test_months_since_last_change(self):
        rows = {r["entity"]: r["age-months"] for r in maat.age(maat.parse_log(LOG), now="2026-09-15")}
        self.assertEqual(rows["src/a.py"], 5)   # last 2026-04-03
        self.assertEqual(rows["src/c.py"], 6)   # last 2026-03-10
        self.assertEqual(rows["img/logo.png"], 7)


class Ownership(unittest.TestCase):
    def test_added_and_deleted_per_author_per_entity(self):
        rows = {(r["entity"], r["author"]): r for r in maat.entity_ownership(maat.parse_log(LOG))}
        self.assertEqual(rows[("src/a.py", "Ann")], {"entity": "src/a.py", "author": "Ann", "added": 10, "deleted": 1})
        self.assertEqual(rows[("src/a.py", "Cat")]["deleted"], 2)


class Types(unittest.TestCase):
    def test_file_entries_outside_the_types_are_dropped(self):
        commits = maat.parse_log(LOG, types={"py"})
        self.assertEqual(commits[1]["files"], [("src/a.py", 1, 1), ("src/b.py", 5, 5)])
        self.assertNotIn("img/logo.png", {p for c in commits for p, _, _ in c["files"]})

    def test_none_means_everything(self):
        commits = maat.parse_log(LOG, types=None)
        self.assertIn("img/logo.png", {p for c in commits for p, _, _ in c["files"]})


class Timeline(unittest.TestCase):
    def test_commits_per_author_per_month(self):
        a = maat.activity(maat.parse_log(LOG))
        self.assertEqual(a["timeline"]["Ann"], {"2026-01": 1, "2026-03": 2, "2026-04": 2})
        self.assertEqual(a["timeline"]["Bob"], {"2026-02": 1})
        self.assertEqual(a["timeline"]["Cat"], {"2026-04": 1})


class Aliases(unittest.TestCase):
    def test_author_names_are_canonicalised(self):
        commits = maat.parse_log(LOG, aliases={"Bob": "Robert"})
        rows = {r["entity"]: r for r in maat.authors(commits)}
        self.assertEqual(rows["src/a.py"]["n-authors"], 3)
        own = {(r["entity"], r["author"]) for r in maat.entity_ownership(commits)}
        self.assertIn(("src/b.py", "Robert"), own)
        self.assertNotIn(("src/b.py", "Bob"), own)


class IsFix(unittest.TestCase):
    def test_conventional_and_wordy_subjects(self):
        for yes in ["fix: x", "fix(core)!: x", "Fixed the thing", "bugfix", "Hotfix: y", "Resolve crash on start", "regression in parser", "Bug 123"]:
            self.assertTrue(maat.is_fix(yes), yes)
        for no in ["prefix cleanup", "feat: bugsnag integration", "Add fixtures", "docs: typo", "Suffix handling"]:
            self.assertFalse(maat.is_fix(no), no)


class Fixes(unittest.TestCase):
    def test_counts_fixes_per_entity_with_last_and_recent(self):
        rows = {r["entity"]: r for r in maat.fixes(maat.parse_log(LOG), now="2026-09-15")}
        self.assertEqual(rows["src/a.py"], {"entity": "src/a.py", "n-fixes": 3, "last-fix": "2026-04-03", "recent-fixes": 2})
        self.assertEqual(rows["src/b.py"]["n-fixes"], 2)
        self.assertEqual(rows["src/c.py"]["n-fixes"], 1)
        self.assertNotIn("img/logo.png", rows)

    def test_recent_window_is_six_months(self):
        rows = {r["entity"]: r for r in maat.fixes(maat.parse_log(LOG), now="2026-10-02")}
        self.assertEqual(rows["src/a.py"]["recent-fixes"], 1)   # 2026-04-03 is inside six months of 2026-10-02; 2026-04-01 is not


class Activity(unittest.TestCase):
    def test_commits_by_weekday_hour_month_and_author(self):
        a = maat.activity(maat.parse_log(LOG))
        # 2026-01-10 Sat, 02-10 Tue, 03-10 Tue, 03-12 Thu, 04-01 Wed, 04-02 Thu, 04-03 Fri
        self.assertEqual(a["by_weekday"], [0, 2, 1, 2, 1, 1, 0])
        self.assertEqual(a["by_hour"][9], 4)
        self.assertEqual(a["by_hour"][22], 1)
        self.assertEqual(a["by_month"], {"2026-01": 1, "2026-02": 1, "2026-03": 2, "2026-04": 3})
        self.assertEqual(a["authors"]["Ann"], {"commits": 5, "added": 16, "deleted": 1, "first": "2026-01-10", "last": "2026-04-02"})
        self.assertEqual(a["authors"]["Cat"]["deleted"], 3)
        self.assertEqual(a["fix_commits"], 3)

    def test_legacy_short_dates_still_parse(self):
        a = maat.activity(maat.parse_log("--x--2026-05-04--Ann\n1\t0\tf.py\n"))
        self.assertEqual(sum(a["by_weekday"]), 1)
        self.assertEqual(a["by_hour"], [0] * 24)


class UtcZSuffix(unittest.TestCase):
    def test_git_2_45_z_suffix_timestamps_keep_their_hour(self):
        a = maat.activity(maat.parse_log("--x--2026-05-04T09:15:00Z--Ann\n1\t0\tf.py\n"))
        self.assertEqual(a["by_hour"][9], 1)
        self.assertEqual(a["by_weekday"][0], 1)  # 2026-05-04 is a Monday


class NetByYear(unittest.TestCase):
    def test_added_minus_deleted_per_year(self):
        a = maat.activity(maat.parse_log(LOG + "--h8--2025-12-31T10:00:00+00:00--Ann\n7\t2\told.py\n"))
        self.assertEqual(a["net_by_year"], {"2025": 5, "2026": 12})


class NowParameter(unittest.TestCase):
    def test_write_all_takes_the_reference_date_as_a_parameter(self):
        with tempfile.TemporaryDirectory() as d:
            log = os.path.join(d, "log.txt")
            with open(log, "w") as fh:
                fh.write(LOG)
            maat.write_all(log, d, now="2030-01-01")
            with open(os.path.join(d, "maat-age.csv")) as fh:
                rows = dict(line.strip().split(",") for line in fh.readlines()[1:])
        self.assertEqual(rows["src/a.py"], "44")   # 2026-04-03 -> 2030-01-01

    def test_library_ignores_the_environment(self):
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as d, patch.dict(os.environ, {"GITMOLE_NOW": "2030-01-01"}):
            log = os.path.join(d, "log.txt")
            with open(log, "w") as fh:
                fh.write(LOG)
            maat.write_all(log, d)
            with open(os.path.join(d, "maat-age.csv")) as fh:
                rows = dict(line.strip().split(",") for line in fh.readlines()[1:])
        self.assertNotEqual(rows["src/a.py"], "44")

    def test_validate_now_rejects_malformed_dates(self):
        self.assertEqual(maat.validate_now("2025-06-15"), "2025-06-15")
        for bad in ("2025-6-15", "today", "2025-06-15T00:00:00"):
            with self.assertRaises(ValueError):
                maat.validate_now(bad)


class CarriageReturnInSubject(unittest.TestCase):
    def test_write_all_reads_the_log_without_newline_translation(self):
        with tempfile.TemporaryDirectory() as d:
            log = os.path.join(d, "log.txt")
            with open(log, "wb") as fh:
                fh.write(b"--x--2026-05-04T10:00:00+00:00--Ann--Fix the\rwatcher (#1)\n1\t0\tf.py\n")
            maat.write_all(log, d)
            with open(os.path.join(d, "maat-revisions.csv")) as fh:
                self.assertEqual(fh.read().splitlines()[1], "f.py,1")


class SinceWindow(unittest.TestCase):
    def test_window_bounds_everything_except_age(self):
        with tempfile.TemporaryDirectory() as d:
            log = os.path.join(d, "log.txt")
            with open(log, "w") as fh:
                fh.write(LOG)
            maat.write_all(log, d, now="2026-09-15", since="2026-04-01")
            def rows(name):
                with open(os.path.join(d, name)) as fh:
                    return fh.read().splitlines()[1:]
            self.assertEqual(rows("maat-revisions.csv"), ["src/a.py,3", "src/b.py,3"], "only commits from 2026-04-01 on")
            self.assertIn("src/c.py,6", rows("maat-age.csv"), "age keeps the whole history")
            with open(os.path.join(d, "activity.json")) as fh:
                a = json.load(fh)
            self.assertEqual(sum(a["by_weekday"]), 3)
            self.assertEqual(a["window"], "2026-04-01")

    def test_empty_window_is_reported(self):
        commits = maat.parse_log(LOG)
        self.assertEqual(maat.in_window(commits, "2030-01-01"), [])


class WriteAll(unittest.TestCase):
    def test_writes_the_five_csv_files_in_code_maat_layout(self):
        with tempfile.TemporaryDirectory() as d:
            log = os.path.join(d, "log.txt")
            with open(log, "w") as fh:
                fh.write(LOG)
            maat.write_all(log, d)
            names = sorted(n for n in os.listdir(d) if n.startswith("maat-"))
            self.assertEqual(names, ["maat-age.csv", "maat-authors.csv", "maat-coupling.csv", "maat-entity-ownership.csv", "maat-fixes.csv", "maat-revisions.csv"])
            self.assertTrue(os.path.isfile(os.path.join(d, "activity.json")))
            with open(os.path.join(d, "maat-revisions.csv")) as fh:
                self.assertEqual(fh.readline().strip(), "entity,n-revs")
                self.assertEqual(fh.readline().strip(), "src/a.py,7")
            with open(os.path.join(d, "maat-coupling.csv")) as fh:
                self.assertEqual(fh.readline().strip(), "entity,coupled,degree,average-revs")


if __name__ == "__main__":
    unittest.main()

import os
import tempfile
import unittest

from gitmole import maat

LOG = """--a1--2026-01-10T09:15:00+00:00--Ann
3\t1\tsrc/a.py
2\t0\tsrc/b.py

--b2--2026-02-10T14:00:00+00:00--Bob
1\t1\tsrc/a.py
5\t5\tsrc/b.py
-\t-\timg/logo.png

--c3--2026-03-10T09:30:00+00:00--Ann
4\t0\tsrc/a.py
1\t0\tsrc/c.py

--d4--2026-03-12T22:00:00+00:00--Ann
1\t0\tsrc/a.py
1\t0\tsrc/b.py

--e5--2026-04-01T09:00:00+00:00--Ann
1\t0\tsrc/a.py
1\t0\tsrc/b.py

--f6--2026-04-02T09:45:00+00:00--Ann
1\t0\tsrc/a.py
1\t0\tsrc/b.py

--g7--2026-04-03T11:00:00+00:00--Cat
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
        self.assertEqual(commits[0]["files"], [("src/a.py", 3, 1), ("src/b.py", 2, 0)])
        self.assertEqual(commits[1]["files"][2], ("img/logo.png", 0, 0))


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


class Aliases(unittest.TestCase):
    def test_author_names_are_canonicalised(self):
        commits = maat.parse_log(LOG, aliases={"Bob": "Robert"})
        rows = {r["entity"]: r for r in maat.authors(commits)}
        self.assertEqual(rows["src/a.py"]["n-authors"], 3)
        own = {(r["entity"], r["author"]) for r in maat.entity_ownership(commits)}
        self.assertIn(("src/b.py", "Robert"), own)
        self.assertNotIn(("src/b.py", "Bob"), own)


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

    def test_legacy_short_dates_still_parse(self):
        a = maat.activity(maat.parse_log("--x--2026-05-04--Ann\n1\t0\tf.py\n"))
        self.assertEqual(sum(a["by_weekday"]), 1)
        self.assertEqual(a["by_hour"], [0] * 24)


class NetByYear(unittest.TestCase):
    def test_added_minus_deleted_per_year(self):
        a = maat.activity(maat.parse_log(LOG + "--h8--2025-12-31T10:00:00+00:00--Ann\n7\t2\told.py\n"))
        self.assertEqual(a["net_by_year"], {"2025": 5, "2026": 12})


class WriteAll(unittest.TestCase):
    def test_writes_the_five_csv_files_in_code_maat_layout(self):
        with tempfile.TemporaryDirectory() as d:
            log = os.path.join(d, "log.txt")
            with open(log, "w") as fh:
                fh.write(LOG)
            maat.write_all(log, d)
            names = sorted(n for n in os.listdir(d) if n.startswith("maat-"))
            self.assertEqual(names, ["maat-age.csv", "maat-authors.csv", "maat-coupling.csv", "maat-entity-ownership.csv", "maat-revisions.csv"])
            self.assertTrue(os.path.isfile(os.path.join(d, "activity.json")))
            with open(os.path.join(d, "maat-revisions.csv")) as fh:
                self.assertEqual(fh.readline().strip(), "entity,n-revs")
                self.assertEqual(fh.readline().strip(), "src/a.py,7")
            with open(os.path.join(d, "maat-coupling.csv")) as fh:
                self.assertEqual(fh.readline().strip(), "entity,coupled,degree,average-revs")


if __name__ == "__main__":
    unittest.main()

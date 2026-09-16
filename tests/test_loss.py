import unittest

from gitmole import loss


def report(**overrides):
    base = {
        "meta": {"name": "r", "last_date": "2025-11-09", "bots": [{"name": "renovate[bot]", "commits": 9}]},
        "activity": {"authors": {
            "Ann": {"commits": 50, "added": 0, "deleted": 0, "first": "2020-01-01", "last": "2025-11-01"},
            "Bob": {"commits": 20, "added": 0, "deleted": 0, "first": "2020-01-01", "last": "2024-11-08"},   # one day past the window
            "Cat": {"commits": 5, "added": 0, "deleted": 0, "first": "2021-01-01", "last": "2024-11-09"},   # on the cut-off: stays
            "renovate[bot]": {"commits": 9, "added": 0, "deleted": 0, "first": "2024-01-01", "last": "2024-01-01"},
            "dependabot[bot]": {"commits": 1, "added": 0, "deleted": 0, "first": "2023-01-01", "last": "2023-01-01"},
        }},
        "theseus_authors": {"Ann": 600, "Bob": 300, "Cat": 100},
        "ownership": [{"entity": "app/a.py", "author": "Ann", "added": 100, "deleted": 0},
                      {"entity": "app/b.py", "author": "Bob", "added": 900, "deleted": 0},
                      {"entity": "docs/x.md", "author": "Bob", "added": 50, "deleted": 0},
                      {"entity": "tests/t.py", "author": "Bob", "added": 500, "deleted": 0}],
    }
    base.update(overrides)
    return base


class Gone(unittest.TestCase):
    def test_no_commits_in_the_window_before_the_last_commit_not_before_today(self):
        self.assertEqual(loss.cutoff(report(), 12), "2024-11-09")
        self.assertEqual(loss.gone(report()), [{"name": "Bob", "last": "2024-11-08"}])

    def test_bots_are_never_people(self):
        names = [g["name"] for g in loss.gone(report(), months=1)]
        self.assertEqual(names, ["Bob", "Cat"])

    def test_window_is_configurable(self):
        self.assertEqual([g["name"] for g in loss.gone(report(), months=1)], ["Bob", "Cat"])
        self.assertEqual(loss.gone(report(), months=24), [])

    def test_nothing_without_activity_or_last_date(self):
        self.assertEqual(loss.gone(report(activity={})), [])
        r = report()
        r["meta"]["last_date"] = ""
        self.assertEqual(loss.gone(r), [])


class WhatWasLost(unittest.TestCase):
    def test_surviving_lines_by_gone_people(self):
        self.assertEqual(loss.surviving(report(), {"Bob"}), (300, 1000))
        self.assertEqual(loss.surviving(report(theseus_authors={}), {"Bob"}), (0, 0))

    def test_areas_carry_the_lost_share_over_the_rows_given(self):
        from gitmole import filetypes
        rows = [r for r in report()["ownership"] if not filetypes.is_test_path(r["entity"])]
        areas = {a["area"]: a for a in loss.areas(rows, {"Bob"})}
        self.assertEqual(set(areas), {"app/", "docs/"}, "the caller left tests/ out")
        self.assertEqual(areas["app/"]["lost"], 900)
        self.assertAlmostEqual(areas["app/"]["lost_share"], 0.9)
        self.assertAlmostEqual(areas["docs/"]["lost_share"], 1.0)

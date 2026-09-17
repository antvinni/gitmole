import unittest

from gitmole import evaluate


def commit(date, subject, *files):
    return {"hash": date, "date": date, "time": date, "author": "Ann", "subject": subject, "files": list(files)}


COMMITS = [
    commit("2025-01-10", "add", ("core/a.py", 100, 0), ("core/b.py", 50, 0)),
    commit("2025-02-10", "more", ("core/a.py", 10, 2)),
    commit("2025-03-10", "fix: a", ("core/a.py", 3, 3), ("tests/test_a.py", 5, 0)),
    commit("2025-04-10", "tweak", ("core/b.py", 1, 1)),
    commit("2025-07-10", "fix crash", ("core/b.py", 2, 2), ("tests/test_b.py", 1, 0)),
    commit("2025-11-10", "fix: late", ("core/a.py", 1, 1)),
]
SIZE = {"files": {"core/a.py": {"code": 110, "complexity": 9}, "core/b.py": {"code": 50, "complexity": 1}}}


class Dates(unittest.TestCase):
    def test_cutoffs_step_back_from_the_last_commit_oldest_first(self):
        self.assertEqual(evaluate.cutoffs("2026-08-31", windows=3, horizon=6), ["2025-02-28", "2025-08-31", "2026-02-28"])

    def test_months_after_clamps_the_day_and_crosses_the_year(self):
        self.assertEqual(evaluate.months_after("2025-08-31", 6), "2026-02-28")
        self.assertEqual(evaluate.months_after("2025-01-15", 12), "2026-01-15")


class Outcome(unittest.TestCase):
    def test_source_files_a_fix_commit_touched_inside_the_horizon(self):
        self.assertEqual(evaluate.fixed_between(COMMITS, "2025-06-01", "2025-09-01"), {"core/b.py"})
        self.assertEqual(evaluate.fixed_between(COMMITS, "2025-06-01", "2025-12-01"), {"core/a.py", "core/b.py"})
        self.assertEqual(evaluate.fixed_between(COMMITS, "2025-03-10", "2025-03-11"), {"core/a.py"}, "the start is inclusive; the test file is left out")


class Score(unittest.TestCase):
    def test_the_report_at_t_knows_nothing_after_t(self):
        r = evaluate.report_at(COMMITS, "2025-06-01", SIZE, {"bots": [], "generated": []})
        self.assertEqual({x["entity"]: x["n-revs"] for x in r["revisions"]}, {"core/a.py": 3, "core/b.py": 2, "tests/test_a.py": 1})
        self.assertEqual(r["meta"]["now"], "2025-06-01")

    def test_every_variant_is_scored_over_one_pool_next_to_a_random_pick(self):
        r = evaluate.report_at(COMMITS, "2025-06-01", SIZE, {})
        out = evaluate.score(r, {"core/b.py"}, top=1)
        self.assertEqual(set(out), {"watch list (hotspot)", "factor product (max-scaled)", "factor product (rank-scaled)", "churn", "size", "recent fixes", "random (expected)"})
        self.assertEqual(out["churn"], 0, "a.py changed more and was not the file fixed")
        self.assertEqual(out["random (expected)"], 0.5)
        self.assertEqual(evaluate.score(r, {"core/b.py"}, top=2)["churn"], 1)

    def test_a_bot_owns_nothing_at_t_either(self):
        commits = [commit("2025-01-10", "add", ("core/a.py", 100, 0))]
        commits[0]["author"] = "release[bot]"
        self.assertEqual(evaluate.report_at(commits, "2025-06-01", SIZE, {})["ownership"], [])


class Table(unittest.TestCase):
    def test_one_row_per_variant_one_column_per_cut_off_and_a_total(self):
        text = evaluate.table([("2025-02-28", 3, 40, {"churn": 1, "random (expected)": 0.4}),
                               ("2025-08-31", 5, 50, {"churn": 2, "random (expected)": 0.6})])
        self.assertEqual(text.splitlines(), [
            "| variant | 2025-02-28 (3 of 40 fixed) | 2025-08-31 (5 of 50 fixed) | total |",
            "|---|---:|---:|---:|",
            "| churn | 1 | 2 | 3 |",
            "| random (expected) | 0.4 | 0.6 | 1.0 |",
        ])


if __name__ == "__main__":
    unittest.main()

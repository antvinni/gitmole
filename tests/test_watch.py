import unittest

from gitmole import watch


def report(**overrides):
    base = {
        "meta": {"name": "r"},
        "size": {"files": {"core/parser.py": {"code": 800, "complexity": 40}, "core/util.py": {"code": 200, "complexity": 5},
                           "web/index.html": {"code": 4000, "complexity": 0}, "tests/test_parser.py": {"code": 300, "complexity": 2}}},
        "revisions": [{"entity": "web/index.html", "n-revs": 60}, {"entity": "core/parser.py", "n-revs": 40},
                      {"entity": "core/util.py", "n-revs": 30}, {"entity": "tests/test_parser.py", "n-revs": 45},
                      {"entity": "core/gone.py", "n-revs": 50}, {"entity": "core/once.py", "n-revs": 1}],
        "fixes": [{"entity": "core/parser.py", "n-fixes": 9, "last-fix": "2026-09-01", "recent-fixes": 5},
                  {"entity": "core/util.py", "n-fixes": 2, "last-fix": "2025-01-01", "recent-fixes": 0}],
        "authors": [{"entity": "core/parser.py", "n-authors": 1}, {"entity": "core/util.py", "n-authors": 3}, {"entity": "web/index.html", "n-authors": 4}],
        "ownership": [{"entity": "core/parser.py", "author": "Ann", "added": 900, "deleted": 0},
                      {"entity": "core/util.py", "author": "Ann", "added": 190, "deleted": 0},
                      {"entity": "core/util.py", "author": "Bob", "added": 10, "deleted": 0},
                      {"entity": "web/index.html", "author": "Bob", "added": 2000, "deleted": 0},
                      {"entity": "web/index.html", "author": "Cat", "added": 2000, "deleted": 0}],
        "coupling": [{"entity": "core/parser.py", "coupled": "core/ast.py", "degree": 72, "average-revs": 30},
                     {"entity": "core/lexer.py", "coupled": "core/parser.py", "degree": 55, "average-revs": 20},
                     {"entity": "core/parser.py", "coupled": "core/rare.py", "degree": 90, "average-revs": 2},
                     {"entity": "core/parser.py", "coupled": "tests/test_parser.py", "degree": 100, "average-revs": 40}],
        "functions": [{"file": "core/parser.py", "function": "parse", "ccn": 41, "nloc": 220, "params": 9, "start": 10, "end": 300},
                      {"file": "core/parser.py", "function": "peek", "ccn": 2, "nloc": 5, "params": 0, "start": 1, "end": 6},
                      {"file": "core/util.py", "function": "tidy", "ccn": 4, "nloc": 20, "params": 1, "start": 1, "end": 21}],
    }
    base.update(overrides)
    return base


class Risks(unittest.TestCase):
    def test_combines_churn_fixes_complexity_and_ownership(self):
        ranked = watch.risks(report())
        self.assertEqual(ranked[0]["file"], "core/parser.py", "fewer revisions than index.html, but fixed, complex and single-owned")
        self.assertEqual([r["file"] for r in ranked], ["core/parser.py", "web/index.html", "core/util.py"],
                         "twice the churn still beats single ownership plus old fixes")

    def test_reasons_in_plain_words(self):
        top = watch.risks(report())[0]
        self.assertEqual(top["reasons"], ["changed 40 times", "fixed 5 times in six months",
                                          "only Ann has touched it", "parse() complexity 41",
                                          "changes with core/ast.py (72%) and 1 other"])
        by = {r["file"]: r for r in watch.risks(report())}
        self.assertEqual(by["core/util.py"]["reasons"], ["changed 30 times", "fixed twice", "Ann wrote 95% of it"])
        self.assertEqual(by["web/index.html"]["reasons"], ["changed 60 times"])

    def test_leaves_out_tests_deleted_files_and_one_offs(self):
        files = [r["file"] for r in watch.risks(report())]
        self.assertNotIn("tests/test_parser.py", files)
        self.assertNotIn("core/gone.py", files, "no longer in the tree")
        self.assertNotIn("core/once.py", files, "changed once")

    def test_test_companions_and_weak_pairs_are_not_reasons(self):
        top = watch.risks(report())[0]
        coupling = [r for r in top["reasons"] if r.startswith("changes with")][0]
        self.assertNotIn("test_parser", coupling)
        self.assertNotIn("rare", coupling, "2 shared revisions is not a pattern")

    def test_scc_complexity_stands_in_when_lizard_is_absent(self):
        r = report(functions=[])
        ranked = watch.risks(r)
        self.assertEqual(ranked[0]["file"], "core/parser.py")
        self.assertFalse(any("complexity" in x for x in ranked[0]["reasons"]), "scc's file total is not worded")

    def test_empty_without_change_data(self):
        self.assertEqual(watch.risks(report(revisions=[])), [])
        self.assertEqual(watch.risks({"meta": {}, "size": {}}), [])

    def test_complexity_is_scc_file_total_for_every_file_lizard_names_the_function(self):
        # lizard has no reader for shell, Terraform, Makefiles...; with lizard rows present those
        # files used to score complexity 0. One scale (scc's per-file total) for the score,
        # lizard's worst function for the wording.
        r = report()
        r["size"]["files"]["ops/deploy.sh"] = {"code": 300, "complexity": 80}
        r["revisions"].append({"entity": "ops/deploy.sh", "n-revs": 40})
        by = {x["file"]: x for x in watch.risks(r)}
        self.assertEqual(by["ops/deploy.sh"]["complexity"], 80)
        self.assertEqual(by["core/parser.py"]["complexity"], 40, "scc's total, not lizard's worst function")
        self.assertIn("parse() complexity 41", by["core/parser.py"]["reasons"])
        self.assertGreater(by["ops/deploy.sh"]["score"], by["core/util.py"]["score"])


class WhyEmpty(unittest.TestCase):
    def test_says_what_kept_the_list_empty(self):
        self.assertEqual(watch.why_empty(report(revisions=[])), "nothing changed more than once")
        self.assertEqual(watch.why_empty(report(revisions=[{"entity": "core/once.py", "n-revs": 1}])), "nothing changed more than once")
        self.assertEqual(watch.why_empty(report(revisions=[{"entity": "tests/test_a.py", "n-revs": 40}])), "only test files changed more than once")
        r = report(); r["size"] = {"files": {}}
        self.assertEqual(watch.why_empty(r), "no size data for the files that changed")
        self.assertEqual(watch.why_empty(report(revisions=[{"entity": "core/gone.py", "n-revs": 50}])), "the files that changed more than once are no longer in the tree")


class ChangeRisk(unittest.TestCase):
    def test_scores_touched_files_with_the_watch_score_and_reasons(self):
        # Add core/once.py to size.files so it's in the tree and will report "changed once"
        r = report(size={"files": {"core/parser.py": {"code": 800, "complexity": 40}, "core/util.py": {"code": 200, "complexity": 5},
                                   "web/index.html": {"code": 4000, "complexity": 0}, "tests/test_parser.py": {"code": 300, "complexity": 2},
                                   "core/once.py": {"code": 10, "complexity": 0}}})
        out = watch.change_risk(r, ["core/util.py", "core/parser.py", "core/new.py", "core/once.py", "tests/test_parser.py"])
        files = [f["file"] for f in out["files"]]
        self.assertEqual(files[:2], ["core/parser.py", "core/util.py"], "highest score first")
        by = {f["file"]: f for f in out["files"]}
        self.assertGreater(by["core/parser.py"]["score"], by["core/util.py"]["score"])
        self.assertIn("changed 40 times", by["core/parser.py"]["reasons"][0])
        self.assertEqual((by["core/new.py"]["score"], by["core/new.py"]["reasons"]), (0, ["new file"]))
        self.assertEqual((by["core/once.py"]["score"], by["core/once.py"]["reasons"]), (0, ["changed once"]))
        self.assertEqual((by["tests/test_parser.py"]["score"], by["tests/test_parser.py"]["reasons"]), (0, ["test file"]))
        # Test file path that's also new reports "test file" (test file wins over new file)
        test_new_file_out = watch.change_risk(r, ["tests/data/new_fixture.py"])
        self.assertEqual(test_new_file_out["files"][0]["reasons"], ["test file"])
        self.assertAlmostEqual(out["total"], by["core/parser.py"]["score"] + by["core/util.py"]["score"])
        self.assertEqual(out["watched"], 2, "both are in the top 15 of the watch list")
        self.assertEqual(out["max_score"], watch.risks(r)[0]["score"])

    def test_max_score_is_repo_wide_not_touched(self):
        # max_score should be the highest score in the repository, not the max of touched files
        r = report()
        # Touch only util.py (not the top file), but max_score should still be top file's score
        out = watch.change_risk(r, ["core/util.py"])
        self.assertEqual(out["max_score"], watch.risks(r)[0]["score"], "max_score is repo-wide max, not touched max")

    def test_empty(self):
        self.assertEqual(watch.change_risk(report(), []), {"files": [], "total": 0.0, "watched": 0, "max_score": 0.0})


class Backtest(unittest.TestCase):
    def test_counts_how_many_files_fixed_since_the_cut_off_were_on_the_list(self):
        past = report()   # the same synthetic repo, taken as the state at T
        past["meta"] = {"now": "2026-03-01"}
        r = report(fixes=[{"entity": "core/parser.py", "n-fixes": 9, "last-fix": "2026-09-01", "recent-fixes": 5},
                          {"entity": "core/other.py", "n-fixes": 1, "last-fix": "2026-05-01", "recent-fixes": 1},
                          {"entity": "core/util.py", "n-fixes": 2, "last-fix": "2025-01-01", "recent-fixes": 0},
                          {"entity": "tests/test_parser.py", "n-fixes": 3, "last-fix": "2026-08-01", "recent-fixes": 3}],
                   backtest=past)
        out = watch.backtest(r)
        self.assertEqual(out["t"], "2026-03-01")
        self.assertEqual(out["pool"], 3, "the pool has three scorable files")
        self.assertEqual(out["listed"], 3, "the past list has three scorable files")
        self.assertEqual(out["fixed"], 2, "parser and other; util's fix is older, the test file does not count")
        self.assertEqual(out["hits"], 1, "parser was listed; other was not")
        self.assertAlmostEqual(out["expected"], 1.0, msg="3 listed × 1 fixed in the pool / 3 in the pool")

    def test_none_without_a_backtest(self):
        self.assertIsNone(watch.backtest(report()))
        self.assertIsNone(watch.backtest(report(backtest={"meta": {"now": "2026-03-01"}, "size": {"files": {}}})))


if __name__ == "__main__":
    unittest.main()

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
    def test_ranks_by_revisions_times_lines_of_code(self):
        ranked = watch.risks(report())
        self.assertEqual([r["file"] for r in ranked], ["web/index.html", "core/parser.py", "core/util.py"],
                         "60 × 4000, then 40 × 800, then 30 × 200; fixes, complexity and ownership are reasons, not rank")
        self.assertEqual([round(r["score"], 3) for r in ranked], [1.0, 0.667, 0.333], "the share of scored files at or below each product")

    def test_the_factor_products_stay_selectable_for_the_evaluation(self):
        for scoring in ("rank", "max"):
            self.assertEqual(watch.risks(report(), scoring=scoring)[0]["file"], "core/parser.py", scoring)

    def test_reasons_in_plain_words(self):
        top = {r["file"]: r for r in watch.risks(report())}["core/parser.py"]
        self.assertEqual(top["reasons"], ["changed 40 times", "fixed 5 times in six months",
                                          "only Ann has touched it", "parse() complexity 41",
                                          "changes with core/ast.py (72%) and 1 other"])
        by = {r["file"]: r for r in watch.risks(report())}
        self.assertEqual(by["core/util.py"]["reasons"], ["changed 30 times", "fixed twice", "Ann wrote 95% of it"])
        self.assertEqual(by["web/index.html"]["reasons"], ["changed 60 times"])

    def test_a_nameless_function_is_named_by_its_line_and_a_suspect_span_is_passed_over(self):
        r = report()
        r["functions"] = [{"file": "core/parser.py", "function": 'app.post("/api/x", async (req, res) => {', "anonymous": True,
                           "ccn": 125, "nloc": 500, "params": 0, "start": 1162, "end": 1891, "suspect": "opens a block at line 1214 no deeper than its own start"},
                          {"file": "core/parser.py", "function": 'router.get("/x", (req, res) => {', "anonymous": True,
                           "ccn": 41, "nloc": 220, "params": 0, "start": 10, "end": 300, "suspect": ""}]
        top = {r["file"]: r for r in watch.risks(r)}["core/parser.py"]
        self.assertIn("the function at line 10 complexity 41", top["reasons"], "a label is not a name to put () after; a suspect span is not this file's complexity")
        self.assertNotIn("complexity 125", " ".join(top["reasons"]))

    def test_leaves_out_tests_deleted_files_and_one_offs(self):
        files = [r["file"] for r in watch.risks(report())]
        self.assertNotIn("tests/test_parser.py", files)
        self.assertNotIn("core/gone.py", files, "no longer in the tree")
        self.assertNotIn("core/once.py", files, "changed once")

    def test_release_plumbing_is_not_on_the_list(self):
        r = report()
        r["size"]["files"].update({"setup.py": {"code": 6, "complexity": 0}, "version.go": {"code": 2, "complexity": 0}, "Makefile": {"code": 21, "complexity": 0}})
        r["revisions"] = [{"entity": "setup.py", "n-revs": 184}, {"entity": "version.go", "n-revs": 29}, {"entity": "Makefile", "n-revs": 131},
                          {"entity": "core/parser.py", "n-revs": 40}]
        files = sorted(x["file"] for x in watch.risks(r))
        self.assertEqual(files, ["Makefile", "core/parser.py"], "a version file or a manifest changes on every release, not where the next bug lands")

    def test_a_file_the_change_log_shows_as_plumbing_is_not_on_the_list(self):
        r = report()
        r["size"]["files"]["pkg/__init__.py"] = {"code": 40, "complexity": 0}
        r["revisions"] = [{"entity": "pkg/__init__.py", "n-revs": 331}, {"entity": "core/parser.py", "n-revs": 40}]
        r["plumbing"] = [{"entity": "pkg/__init__.py", "n-revs": 331, "tiny-revs": 300}]
        self.assertEqual([x["file"] for x in watch.risks(r)], ["core/parser.py"])

    def test_a_generated_file_is_not_on_the_list(self):
        r = report()
        r["size"]["files"]["dist/all.js"] = {"code": 9000, "complexity": 200}
        r["revisions"] = [{"entity": "dist/all.js", "n-revs": 400}, {"entity": "core/parser.py", "n-revs": 40}]
        r["meta"]["generated"] = ["dist/all.js"]
        self.assertEqual([x["file"] for x in watch.risks(r)], ["core/parser.py"])

    def test_test_companions_and_weak_pairs_are_not_reasons(self):
        top = {r["file"]: r for r in watch.risks(report())}["core/parser.py"]
        coupling = [r for r in top["reasons"] if r.startswith("changes with")][0]
        self.assertNotIn("test_parser", coupling)
        self.assertNotIn("rare", coupling, "2 shared revisions is not a pattern")

    def test_scc_complexity_stands_in_when_lizard_is_absent(self):
        r = report(functions=[])
        ranked = watch.risks(r)
        by = {x["file"]: x for x in ranked}
        self.assertIn("core/parser.py", by)
        self.assertFalse(any("complexity" in x for x in by["core/parser.py"]["reasons"]), "scc's file total is not worded")

    def test_empty_without_change_data(self):
        self.assertEqual(watch.risks(report(revisions=[])), [])
        self.assertEqual(watch.risks({"meta": {}, "size": {}}), [])

    def test_complexity_is_scc_file_total_for_every_file_lizard_names_the_function(self):
        # lizard has no reader for shell, Terraform, Makefiles...; with lizard rows present those
        # files used to score complexity 0. The row's `complexity` field is scc's per-file total
        # for every file; lizard's worst function is only what the reasons name.
        r = report()
        r["size"]["files"]["ops/deploy.sh"] = {"code": 300, "complexity": 80}
        r["revisions"].append({"entity": "ops/deploy.sh", "n-revs": 40})
        by = {x["file"]: x for x in watch.risks(r)}
        self.assertEqual(by["ops/deploy.sh"]["complexity"], 80)
        self.assertEqual(by["core/parser.py"]["complexity"], 40, "scc's total, not lizard's worst function")
        self.assertIn("parse() complexity 41", by["core/parser.py"]["reasons"])
        by_rank = {x["file"]: x for x in watch.risks(r, scoring="rank")}
        self.assertGreater(by_rank["ops/deploy.sh"]["score"], by_rank["core/util.py"]["score"],
                            "under the factor product, deploy.sh's higher complexity lifts its score")


    def test_rank_scaling_keeps_the_order_of_the_synthetic_repo(self):
        self.assertEqual([r["file"] for r in watch.risks(report(), scoring="rank")], ["core/parser.py", "web/index.html", "core/util.py"])

    def test_under_rank_scaling_an_outlier_does_not_rescale_the_other_files(self):
        def scores(outlier_revs, scoring):
            r = report()
            r["size"]["files"]["core/big.py"] = {"code": 10, "complexity": 0}
            r["revisions"].append({"entity": "core/big.py", "n-revs": outlier_revs})
            return {x["file"]: x["score"] for x in watch.risks(r, scoring=scoring)}
        self.assertEqual(scores(100, "rank")["core/util.py"], scores(10000, "rank")["core/util.py"])
        self.assertNotEqual(scores(100, "max")["core/util.py"], scores(10000, "max")["core/util.py"], "what the rank scaling is for")

    def test_a_file_never_fixed_gets_no_lift_from_fixes_under_either_scaling(self):
        for scoring in ("max", "rank"):
            by = {r["file"]: r for r in watch.risks(report(), scoring=scoring)}
            self.assertEqual(by["web/index.html"]["score"], 1.0, f"{scoring}: most changed, no fixes, no complexity, shared")

    def test_an_unknown_scaling_is_refused(self):
        with self.assertRaises(ValueError):
            watch.risks(report(), scoring="median")

    def test_hotspot_is_the_default_scoring(self):
        r = report()
        self.assertEqual([x["score"] for x in watch.risks(r)], [x["score"] for x in watch.risks(r, scoring="hotspot")])


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

    def test_a_file_in_the_tree_with_no_revisions_in_the_window_is_not_scored(self):
        # in size.files (so not "new file"), not a test path, but no maat-revisions row at all:
        # 0 revisions in the window, so it is not the "changed once" case either.
        r = report(size={"files": {**report()["size"]["files"], "core/idle.py": {"code": 50, "complexity": 0}}})
        out = watch.change_risk(r, ["core/idle.py"])
        self.assertEqual((out["files"][0]["score"], out["files"][0]["reasons"]), (0, ["not scored"]))


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

    def test_none_without_a_cut_off_date(self):
        past = report()
        past["meta"] = {}                      # size data, but the sub-report never recorded its cut-off
        self.assertIsNone(watch.backtest(report(backtest=past)), "no date to compare the fixes against")
        past["meta"] = {"now": ""}
        self.assertIsNone(watch.backtest(report(backtest=past)))

    def test_baselines_are_scored_over_the_same_pool_and_the_same_fixes(self):
        def with_big(**over):
            r = report(**over)
            r["size"]["files"]["core/big.py"] = {"code": 9000, "complexity": 3}
            r["revisions"].append({"entity": "core/big.py", "n-revs": 35})
            return r
        past = with_big()
        past["meta"] = {"now": "2026-03-01"}
        r = with_big(fixes=[{"entity": "core/big.py", "n-fixes": 1, "last-fix": "2026-09-01", "recent-fixes": 1}], backtest=past)
        out = watch.backtest(r, top=1)
        self.assertEqual((out["listed"], out["hits"]), (1, 1), "35 × 9000 leads the list, and big.py was fixed")
        self.assertEqual(out["baselines"], {"churn": 0, "size": 1}, "the most changed file is index.html; the largest is big.py")


class RankedBy(unittest.TestCase):
    def test_best_first_ties_by_file_name_and_rows_carry_their_size(self):
        rows = watch.risks(report())
        self.assertEqual({r["file"]: r["code"] for r in rows}, {"core/parser.py": 800, "core/util.py": 200, "web/index.html": 4000})
        self.assertEqual(watch.ranked_by(rows, watch.BASELINES["churn"]), ["web/index.html", "core/parser.py", "core/util.py"])
        self.assertEqual(watch.ranked_by(rows, lambda r: 0), ["core/parser.py", "core/util.py", "web/index.html"])


if __name__ == "__main__":
    unittest.main()

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


def scored_companions(r):
    """The fixture's companions as scored files: a companion the watch list does not score is not named."""
    r["size"]["files"].update({"core/ast.py": {"code": 50, "complexity": 1}, "core/lexer.py": {"code": 50, "complexity": 1},
                               "core/rare.py": {"code": 50, "complexity": 1}})
    r["revisions"] = r["revisions"] + [{"entity": "core/ast.py", "n-revs": 20}, {"entity": "core/lexer.py", "n-revs": 15}, {"entity": "core/rare.py", "n-revs": 2}]
    return r


class Risks(unittest.TestCase):
    def test_ranks_by_revisions_times_lines_of_code(self):
        ranked = watch.risks(report())
        self.assertEqual([r["file"] for r in ranked], ["web/index.html", "core/parser.py", "core/util.py"],
                         "60 × 4000, then 40 × 800, then 30 × 200; fixes, complexity and ownership are reasons, not rank")
        # products 240,000 / 32,000 / 6,000, sum 278,000: 100 × each ÷ 278,000.
        self.assertEqual([round(r["score"], 2) for r in ranked], [86.33, 11.51, 2.16],
                         "each file's percentage share of the pool's revisions × lines of code")
        self.assertAlmostEqual(sum(r["score"] for r in ranked), 100.0, msg="the whole list's scores add up to 100")

    def test_a_single_scored_file_holds_the_whole_pool_and_scores_100(self):
        r = report(revisions=[{"entity": "core/parser.py", "n-revs": 40}])
        ranked = watch.risks(r)
        self.assertEqual([x["file"] for x in ranked], ["core/parser.py"])
        self.assertEqual(ranked[0]["score"], 100.0, "one file is the whole pool, so it holds all of it")

    def test_a_pool_whose_products_are_all_zero_does_not_divide_by_zero(self):
        # a scored file's code is not itself filtered for 0 (only None is); scc can total 0 code
        # for a file of blank lines and comments alone that it still recognises.
        r = report()
        for f in ("core/parser.py", "core/util.py", "web/index.html"):
            r["size"]["files"][f]["code"] = 0
        ranked = watch.risks(r)
        self.assertEqual([x["score"] for x in ranked], [0.0, 0.0, 0.0], "revs × 0 is 0 for every row, so the sum is 0 and every score falls back to 0.0")

    def test_reasons_in_plain_words(self):
        top = {r["file"]: r for r in watch.risks(scored_companions(report()))}["core/parser.py"]
        self.assertEqual(top["reasons"], ["changed 40 times", "fixed 5 times in six months",
                                          "only Ann has touched it", "parse() complexity 41",
                                          "changes with core/ast.py (72%) and 1 other"])
        by = {r["file"]: r for r in watch.risks(report())}
        self.assertEqual(by["core/util.py"]["reasons"], ["changed 30 times", "fixed twice", "Ann wrote 95% of it"])
        self.assertEqual(by["web/index.html"]["reasons"], ["changed 60 times"])

    def test_many_minor_contributors_and_a_wide_coupling_are_reasons(self):
        r = scored_companions(report())
        r["authors"] = [{"entity": "core/parser.py", "n-authors": 14, "n-revs": 40, "minor": 11}, {"entity": "core/util.py", "n-authors": 3, "n-revs": 30, "minor": 2}]
        r["soc"] = [{"entity": "core/parser.py", "soc": 210, "partners": 41}, {"entity": "core/util.py", "soc": 12, "partners": 4}]
        by = {x["file"]: x for x in watch.risks(r)}
        self.assertEqual(by["core/parser.py"]["reasons"], ["changed 40 times", "fixed 5 times in six months", "Ann wrote 100% of it",
                                                           "11 of 14 authors are minor contributors", "parse() complexity 41",
                                                           "changes with core/ast.py (72%) and 1 other", "changes alongside 41 other files"])
        self.assertEqual(by["core/parser.py"]["minor"], 11)
        self.assertEqual(by["core/parser.py"]["partners"], 41)
        self.assertNotIn("minor", " ".join(by["core/util.py"]["reasons"]), "two minor contributors of three is not a crowd")
        self.assertNotIn("alongside", " ".join(by["core/util.py"]["reasons"]))
        self.assertEqual(by["web/index.html"]["minor"], 0, "an output directory without the column reads as none")

    def test_changes_scattered_over_many_months_are_a_reason(self):
        r = report()
        r["entropy"] = [{"entity": "core/parser.py", "periods": 14, "hcm": 2.1}, {"entity": "core/util.py", "periods": 6, "hcm": 0.4}]
        by = {x["file"]: x for x in watch.risks(r)}
        self.assertIn("changed in 14 different months", by["core/parser.py"]["reasons"])
        self.assertNotIn("months", " ".join(by["core/util.py"]["reasons"]), "six months of changes is not scattered")
        self.assertEqual(by["core/parser.py"]["periods"], 14)
        self.assertIsNone({x["file"]: x for x in watch.risks(report())}["core/parser.py"]["periods"], "an output directory without the table")

    def test_debt_markers_deep_nesting_and_a_god_file_are_reasons(self):
        r = report()
        r["structure"] = {"status": "run", "files": {"core/parser.py": {"debt": 5, "definitions": 72, "max_nesting": 6},
                                                     "core/util.py": {"debt": 1, "definitions": 8, "max_nesting": 2}},
                          "functions": [{"file": "core/parser.py", "name": "parse", "start": 10, "nesting": 6, "cognitive": 80}]}
        by = {x["file"]: x for x in watch.risks(r)}
        reasons = by["core/parser.py"]["reasons"]
        self.assertIn("5 TODO/FIXME comments", reasons)
        self.assertIn("parse() nested 6 deep", reasons)
        self.assertIn("defines 72 functions and classes", reasons)
        self.assertFalse([x for x in by["core/util.py"]["reasons"] if "TODO" in x or "nested" in x or "defines" in x])

    def test_late_night_changes_are_a_reason_and_never_a_rank(self):
        r = report()
        r["latenight"] = [{"entity": "core/parser.py", "n-revs": 40, "late": 12}, {"entity": "core/util.py", "n-revs": 30, "late": 2}]
        by = {x["file"]: x for x in watch.risks(r)}
        self.assertIn("30% of its changes made between midnight and 4 am", by["core/parser.py"]["reasons"])
        self.assertNotIn("midnight", " ".join(by["core/util.py"]["reasons"]))
        self.assertEqual([x["file"] for x in watch.risks(r)], [x["file"] for x in watch.risks(report())], "the rank does not move")

    def test_the_watch_list_by_component(self):
        r = report()
        groups = watch.by_component(watch.risks(r), top=2)
        self.assertEqual([(g["component"], [x["file"] for x in g["files"]]) for g in groups],
                         [("web/", ["web/index.html"]), ("core/", ["core/parser.py", "core/util.py"])])
        self.assertAlmostEqual(sum(g["share"] for g in groups), 100.0)

    def test_tests_that_never_move_with_a_file_are_a_reason(self):
        r = report()
        r["tests"] = [{"entity": "core/parser.py", "n-sets": 38, "with-tests": 0}, {"entity": "core/util.py", "n-sets": 28, "with-tests": 4},
                      {"entity": "web/index.html", "n-sets": 55, "with-tests": 30}]
        by = {x["file"]: x for x in watch.risks(r)}
        self.assertIn("no test changed in its 38 changes", by["core/parser.py"]["reasons"])
        self.assertIn("a test changed in 4 of its 28 changes", by["core/util.py"]["reasons"])
        self.assertNotIn("test", " ".join(by["web/index.html"]["reasons"]), "tests move with most of its changes: nothing to say")
        self.assertEqual(by["core/parser.py"]["tested_share"], 0.0)
        r["tests"] = [{"entity": "core/parser.py", "n-sets": 4, "with-tests": 0}]
        self.assertNotIn("test", " ".join({x["file"]: x for x in watch.risks(r)}["core/parser.py"]["reasons"]), "four changes are too few to judge by")
        self.assertIsNone({x["file"]: x for x in watch.risks(report())}["core/parser.py"]["tested_share"], "an output directory without the table")
        r = report(tests=[{"entity": "core/parser.py", "n-sets": 38, "with-tests": 0}])
        del r["size"]["files"]["tests/test_parser.py"]
        self.assertNotIn("test", " ".join({x["file"]: x for x in watch.risks(r)}["core/parser.py"]["reasons"]),
                         "a repository with no test file anywhere has nothing to say about tests moving")

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

    def test_vendored_and_example_code_are_out_of_the_pool(self):
        r = report()
        r["size"]["files"].update({"vendor/lib/x.py": {"code": 300, "complexity": 3}, "examples/demo.py": {"code": 300, "complexity": 3},
                                   "third/lib.js": {"code": 300, "complexity": 3}})
        r["revisions"] += [{"entity": "vendor/lib/x.py", "n-revs": 9}, {"entity": "examples/demo.py", "n-revs": 9}, {"entity": "third/lib.js", "n-revs": 9}]
        r["meta"]["vendored"] = ["third/lib.js"]
        self.assertEqual([x["file"] for x in watch.risks(r)], ["web/index.html", "core/parser.py", "core/util.py"])

    def test_release_plumbing_is_not_on_the_list(self):
        r = report()
        r["size"]["files"].update({"setup.py": {"code": 6, "complexity": 0}, "version.go": {"code": 2, "complexity": 0}, "Makefile": {"code": 21, "complexity": 0}})
        r["revisions"] = [{"entity": "setup.py", "n-revs": 184}, {"entity": "version.go", "n-revs": 29}, {"entity": "Makefile", "n-revs": 131},
                          {"entity": "core/parser.py", "n-revs": 40}]
        files = sorted(x["file"] for x in watch.risks(r))
        self.assertEqual(files, ["Makefile", "core/parser.py"], "a version file or a manifest changes on every release, not because anything is wrong with it")

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
        top = {r["file"]: r for r in watch.risks(scored_companions(report()))}["core/parser.py"]
        coupling = [r for r in top["reasons"] if r.startswith("changes with")][0]
        self.assertNotIn("test_parser", coupling)
        self.assertNotIn("rare", coupling, "2 shared revisions is not a pattern")

    def test_the_directed_companions_table_wins_and_names_only_scored_files(self):
        r = scored_companions(report(companions=[{"entity": "core/parser.py", "companion": "core/lexer.py", "confidence": 85, "shared": 30},
                                                 {"entity": "core/parser.py", "companion": "ChangeLog", "confidence": 95, "shared": 38},
                                                 {"entity": "core/lexer.py", "companion": "core/parser.py", "confidence": 90, "shared": 30}]))
        by = {x["file"]: x for x in watch.risks(r)}
        self.assertEqual(by["core/parser.py"]["companions"], [("core/lexer.py", 85)], "the coupling degree is not read when the table is there; ChangeLog is not scored")
        self.assertEqual(watch.change_risk(r, ["core/parser.py"])["coupling_gaps"], [{"file": "core/parser.py", "companion": "core/lexer.py", "degree": 85}])

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
        # ops/plain.sh differs from deploy.sh only in complexity: same revisions, same lines of
        # code, no fixes or ownership rows for either. The test below compares only the list's
        # own ranking, which is revisions × lines of code and does not read complexity at all.
        r["size"]["files"]["ops/plain.sh"] = {"code": 300, "complexity": 0}
        r["revisions"].append({"entity": "ops/plain.sh", "n-revs": 40})
        by = {x["file"]: x for x in watch.risks(r)}
        self.assertEqual(by["ops/deploy.sh"]["complexity"], 80)
        self.assertEqual(by["core/parser.py"]["complexity"], 40, "scc's total, not lizard's worst function")
        self.assertIn("parse() complexity 41", by["core/parser.py"]["reasons"])
        # revs × code is 40 × 300 for both, so the hotspot rank does not see complexity at all.
        self.assertEqual(by["ops/deploy.sh"]["score"], by["ops/plain.sh"]["score"],
                          "complexity does not enter the hotspot rank")

    def test_there_is_one_ranking_and_no_scoring_to_choose(self):
        import inspect
        self.assertEqual(list(inspect.signature(watch.risks).parameters), ["report", "min_revs"])

    def test_a_year_of_growing_complexity_is_a_reason_and_anything_less_is_not(self):
        def reasons(series):
            r = report(trend={"samples": [], "files": {"core/parser.py": series}})
            r["meta"]["last_date"] = "2026-09-10"
            return {x["file"]: x for x in watch.risks(r)}["core/parser.py"]
        grown = reasons([["2025-09-01", 10, 300], ["2026-09-01", 32, 800]])
        self.assertEqual(grown["trend"], "+220%")
        self.assertIn("complexity +220% in a year", grown["reasons"])
        self.assertEqual(grown["reasons"].index("complexity +220% in a year"), grown["reasons"].index("parse() complexity 41") + 1, "right after the function it is about")
        for series in ([["2025-09-01", 10, 300], ["2026-09-01", 12, 800]],      # +20%: under the floor
                       [["2025-09-01", 40, 300], ["2026-09-01", 10, 800]],      # shrinking is not a reason
                       []):                                                     # sampled, but with nothing to compare
            self.assertFalse([x for x in reasons(series)["reasons"] if "in a year" in x], series)

    def test_a_file_the_trend_step_did_not_sample_has_no_trend(self):
        by = {x["file"]: x for x in watch.risks(report())}
        self.assertIsNone(by["core/parser.py"]["trend"])

    def test_the_floor_is_inclusive_at_exactly_25_percent(self):
        def reasons(now):
            r = report(trend={"samples": [], "files": {"core/parser.py": [["2025-09-01", 100, 300], ["2026-09-01", now, 800]]}})
            r["meta"]["last_date"] = "2026-09-10"
            return {x["file"]: x for x in watch.risks(r)}["core/parser.py"]["reasons"]
        self.assertIn("complexity +25% in a year", reasons(125), "125 is a 25% rise over 100: right at the floor")
        self.assertFalse([x for x in reasons(124) if "in a year" in x], "124 is a 24% rise over 100: just under the floor")


class WhyEmpty(unittest.TestCase):
    def test_says_what_kept_the_list_empty(self):
        self.assertEqual(watch.why_empty(report(revisions=[])), "nothing changed more than once")
        self.assertEqual(watch.why_empty(report(revisions=[{"entity": "core/once.py", "n-revs": 1}])), "nothing changed more than once")
        self.assertEqual(watch.why_empty(report(revisions=[{"entity": "tests/test_a.py", "n-revs": 40}])), "only test files changed more than once")
        r = report(); r["size"] = {"files": {}}
        self.assertEqual(watch.why_empty(r), "no size data for the files that changed")
        self.assertEqual(watch.why_empty(report(revisions=[{"entity": "core/gone.py", "n-revs": 50}])), "the files that changed more than once are no longer in the tree")
        r = report(revisions=[{"entity": "vendor/a.py", "n-revs": 9}, {"entity": "examples/b.py", "n-revs": 9}])
        r["size"]["files"].update({"vendor/a.py": {"code": 1, "complexity": 0}, "examples/b.py": {"code": 1, "complexity": 0}})
        self.assertEqual(watch.why_empty(r), "only vendored code and example code changed more than once")


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
        self.assertEqual((by["core/new.py"]["score"], by["core/new.py"]["reasons"], by["core/new.py"]["reason"]), (0, ["not in the tree"], "not in the tree"),
                         "a file the change deleted, or one added after the run: no scc row either way")
        self.assertEqual((by["core/once.py"]["score"], by["core/once.py"]["reasons"]), (0, ["changed once"]))
        self.assertEqual((by["tests/test_parser.py"]["score"], by["tests/test_parser.py"]["reasons"]), (0, ["test file"]))
        self.assertIsNone(by["core/parser.py"]["reason"], "a scored row carries reason None")
        test_new_file_out = watch.change_risk(r, ["tests/data/new_fixture.py"])
        self.assertEqual(test_new_file_out["files"][0]["reasons"], ["test file"], "the classifier's reason before the tree check")
        self.assertAlmostEqual(out["total"], by["core/parser.py"]["score"] + by["core/util.py"]["score"])
        self.assertEqual(out["watched"], 2, "both are in the top 15 of the watch list")
        self.assertEqual(out["max_score"], watch.risks(r)[0]["score"])

    def test_each_scored_file_carries_the_context_pack_and_the_companions_the_change_left_out(self):
        r = report()
        r["authors"] = [{"entity": "core/parser.py", "n-authors": 14, "n-revs": 40, "minor": 11}, {"entity": "core/util.py", "n-authors": 3, "n-revs": 30, "minor": 0}]
        r["size"]["files"].update({"core/ast.py": {"code": 100, "complexity": 1}, "core/lexer.py": {"code": 100, "complexity": 1}})
        r["revisions"] += [{"entity": "core/ast.py", "n-revs": 30}, {"entity": "core/lexer.py", "n-revs": 20}]
        out = watch.change_risk(r, ["core/parser.py", "core/lexer.py", "tests/test_parser.py"])
        by = {f["file"]: f for f in out["files"]}
        p = by["core/parser.py"]
        self.assertEqual((p["rank"], p["recent_fixes"], p["fixes"], p["owner"], round(p["owner_share"], 2), p["minor"]), (2, 5, 9, "Ann", 1.0, 11),
                         "hotspot rank, fix counts, owner and share, minor contributors: what a reviewer, human or model, reads before the diff")
        self.assertEqual(out["coupling_gaps"], [{"file": "core/parser.py", "companion": "core/ast.py", "degree": 72}],
                         "parser usually changes with ast.py, which this change does not touch; lexer.py is touched, so it is no gap")
        self.assertEqual(by["core/lexer.py"]["rank"], 5)
        self.assertIsNone(by["tests/test_parser.py"]["rank"], "a file the list does not score has no rank")

    def test_kamei_factors_describe_the_change_as_reasons(self):
        r = report()
        r["age"] = [{"entity": "core/parser.py", "age-months": 0}, {"entity": "core/util.py", "age-months": 8}]
        r["activity"] = {"authors_all": {"Ann": {"commits": 120}, "Bob": {"commits": 3}}}
        for row in r["ownership"]:
            row["commits"] = {"Ann": 20, "Bob": 1, "Cat": 4}[row["author"]]
        stats = {"files": ["core/parser.py", "core/util.py", "web/index.html"], "added": {"core/parser.py": 300, "core/util.py": 20, "web/index.html": 4},
                 "deleted": {"core/parser.py": 40, "core/util.py": 0, "web/index.html": 0}, "author": "Bob", "commits": 3,
                 "subjects": ["Tidy the parser", "fix: crash on empty input", "Add a test"]}
        out = watch.change_risk(r, stats["files"], stats)
        c = out["change"]
        self.assertEqual((c["files"], c["dirs"], c["added"], c["deleted"], c["lines_before"]), (3, 2, 324, 40, 5000))
        self.assertAlmostEqual(c["entropy"], 0.248, places=3, msg="Shannon entropy of the change's lines over its files, normalised by log2 of the file count")
        self.assertEqual((c["prior_revisions"], c["recent_files"], c["developers"], c["author"], c["author_commits"]), (130, 1, 3, "Bob", 3))
        self.assertEqual((c["subsystems"], c["fix"], c["author_subsystem_commits"]), (2, True, 2),
                         "NS: core and web; FIX: one subject is a fix; SEXP: Bob's commits to core/util.py and web/index.html")
        self.assertEqual(c["reasons"], ["touches 3 files across 2 directories in 2 subsystems, 3 commits", "a fix, by its subject",
                                        "adds 324 lines to 5,000 (6%), removes 40",
                                        "most of the change is in one file", "1 of the 3 files changed this month",
                                        "the files have 130 prior changes by 3 people", "Bob has 3 prior commits here, 2 in these subsystems"])
        self.assertNotIn("change", watch.change_risk(r, stats["files"]), "without the diff's numbers there are no factors")

    def test_one_subsystem_no_fix_and_an_export_without_commit_counts(self):
        r = report()
        r["activity"] = {"authors_all": {"Ann": {"commits": 120}}}
        stats = {"files": ["core/parser.py", "core/util.py"], "added": {"core/parser.py": 50, "core/util.py": 50}, "deleted": {}, "author": "Ann", "commits": 1,
                 "subjects": ["Refactor helpers"]}
        c = watch.change_risk(r, stats["files"], stats)["change"]
        self.assertEqual((c["subsystems"], c["fix"], c["author_subsystem_commits"]), (1, False, None),
                         "one subsystem is not worth a word; no subject is a fix; the fixture's ownership rows predate the commits column")
        self.assertEqual(c["reasons"][0], "touches 2 files across 1 directory, 1 commit")
        self.assertNotIn("a fix", " ".join(c["reasons"]))
        self.assertEqual(c["reasons"][-1], "Ann has 120 prior commits here", "no subsystem count when the export cannot say")
        stats["subjects"] = []
        self.assertFalse(watch.change_risk(r, stats["files"], stats)["change"]["fix"], "no subjects, no fix")

    def test_a_first_time_author_and_an_even_spread(self):
        r = report()
        r["activity"] = {"authors_all": {"Ann": {"commits": 120}}}
        stats = {"files": ["core/parser.py", "core/util.py"], "added": {"core/parser.py": 50, "core/util.py": 50}, "deleted": {}, "author": "New Person", "commits": 1}
        c = watch.change_risk(r, stats["files"], stats)["change"]
        self.assertEqual(c["entropy"], 1.0)
        self.assertIn("spread evenly over its files", c["reasons"])
        self.assertIn("New Person's first commit here", c["reasons"])

    def test_the_commits_spelling_of_a_name_is_resolved_before_counting_its_history(self):
        """gitmole's own report called its maintainer a first-time contributor: the branch's commits say
        "vinni", the run merged that identity into "antvinni" with 140 commits, and meta.aliases held the
        mapping. `git log --use-mailmap` only merges what a .mailmap declares, and this repository has none."""
        r = report()
        r["activity"] = {"authors_all": {"antvinni": {"commits": 140}}}
        r["meta"]["aliases"] = {"vinni": "antvinni"}
        stats = {"files": ["core/parser.py"], "added": {"core/parser.py": 50}, "deleted": {}, "author": "vinni", "commits": 1}
        c = watch.change_risk(r, stats["files"], stats)["change"]
        self.assertEqual((c["author"], c["author_commits"]), ("antvinni", 140))
        self.assertIn("antvinni has 140 prior commits here", c["reasons"])
        self.assertNotIn("vinni's first commit here", c["reasons"])

    def test_without_an_alias_map_the_identities_are_read_instead(self):
        """An export written before meta.aliases: identity.canonical_names over the identity table."""
        r = report()
        r["activity"] = {"authors_all": {"antvinni": {"commits": 140}}}
        r["meta"].pop("aliases", None)
        r["meta"]["identities"] = [{"name": "antvinni", "email": "a@b.com", "commits": 140, "aliases": [{"name": "vinni", "email": "a@b.com", "commits": 3}]}]
        stats = {"files": ["core/parser.py"], "added": {"core/parser.py": 50}, "deleted": {}, "author": "vinni", "commits": 1}
        c = watch.change_risk(r, stats["files"], stats)["change"]
        self.assertEqual((c["author"], c["author_commits"]), ("antvinni", 140))

    def test_a_name_no_alias_map_knows_is_left_as_it_is(self):
        r = report()
        r["activity"] = {"authors_all": {"antvinni": {"commits": 140}}}
        r["meta"]["aliases"] = {"vinni": "antvinni"}
        stats = {"files": ["core/parser.py"], "added": {"core/parser.py": 50}, "deleted": {}, "author": "Stranger", "commits": 1}
        c = watch.change_risk(r, stats["files"], stats)["change"]
        self.assertEqual((c["author"], c["author_commits"]), ("Stranger", 0))
        self.assertIn("Stranger's first commit here", c["reasons"])

    def test_max_score_is_repo_wide_not_touched(self):
        # max_score should be the highest score in the repository, not the max of touched files
        r = report()
        # Touch only util.py (not the top file), but max_score should still be top file's score
        out = watch.change_risk(r, ["core/util.py"])
        self.assertEqual(out["max_score"], watch.risks(r)[0]["score"], "max_score is repo-wide max, not touched max")

    def test_every_touched_file_gets_the_classifier_reason(self):
        r = report()
        r["size"]["files"].update({"package.json": {"code": 30, "complexity": 0}, "gen/api.pb.go": {"code": 3000, "complexity": 10},
                                   "vendor/lib/x.py": {"code": 300, "complexity": 3}})
        r["revisions"] += [{"entity": "package.json", "n-revs": 80}, {"entity": "gen/api.pb.go", "n-revs": 20},
                           {"entity": "README.md", "n-revs": 15}, {"entity": "vendor/lib/x.py", "n-revs": 9}]
        r["meta"]["generated"] = ["gen/api.pb.go"]
        r["meta"]["file_types"] = None
        by = {f["file"]: f["reasons"] for f in watch.change_risk(r, ["README.md", "package.json", "gen/api.pb.go", "vendor/lib/x.py"])["files"]}
        self.assertEqual(by, {"README.md": ["not a source type"], "package.json": ["release file"], "gen/api.pb.go": ["generated"],
                              "vendor/lib/x.py": ["vendored"]})

    def test_empty(self):
        self.assertEqual(watch.change_risk(report(), []), {"files": [], "total": 0.0, "watched": 0, "max_score": 0.0, "coupling_gaps": [], "pool": 3})

    def test_a_file_in_the_tree_with_no_revisions_in_the_window_is_not_scored(self):
        # in size.files, not a test path, but no maat-revisions row at all: 0 revisions in the window,
        # so it lands on "no revisions on record" rather than "changed once".
        r = report(size={"files": {**report()["size"]["files"], "core/idle.py": {"code": 50, "complexity": 0}}})
        out = watch.change_risk(r, ["core/idle.py"])
        self.assertEqual((out["files"][0]["score"], out["files"][0]["reasons"]), (0, ["no revisions on record"]))


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

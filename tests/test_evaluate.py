import os
import subprocess
import tempfile
import unittest

from gitmole import evaluate, maat, watch
from tests.test_szz import make_repo


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

    def test_an_oversized_fix_is_not_an_outcome(self):
        commits = COMMITS + [commit(f"2025-05-{1 + i:02d}", "small", ("core/a.py", 1, 1)) for i in range(20)]
        commits.append(commit("2025-08-01", "fix: the big one", *[(f"core/g{i}.py", 100, 100) for i in range(10)]))
        self.assertEqual(evaluate.fixed_between(commits, "2025-07-01", "2025-09-01"), {"core/b.py"}, "2,000 lines over the 99th percentile: tangled by size, credits nothing")


class Induced(unittest.TestCase):
    def _log(self, d):
        text = subprocess.run(["git", "log", "HEAD", "--numstat", "--date=iso-strict", "-M", "--pretty=format:--%h--%ad--%aN--%s"],
                              cwd=d, capture_output=True, text=True, check=True).stdout
        return maat.parse_log(text)

    def test_files_a_commit_before_the_cut_off_made_buggy_as_a_fix_inside_the_horizon_shows(self):
        with tempfile.TemporaryDirectory() as d:
            make_repo(d)
            commits = self._log(d)
            self.assertEqual(evaluate.induced_between(d, commits, "2025-03-15", "2025-09-15"), {"core/f.py"},
                             "the April fix blames the February commit, which is before the cut-off")
            self.assertEqual(evaluate.induced_between(d, commits, "2025-01-15", "2025-09-15"), set(),
                             "the same fix, but the bug was planted after this cut-off: not something the list could have known")
            self.assertEqual(evaluate.induced_between(d, commits, "2025-04-15", "2025-09-15"), set(), "the May fix only adds lines: R-SZZ finds nothing")

    def test_labelled_commits_inside_the_horizon_name_their_source_files_or_the_paths_given(self):
        with tempfile.TemporaryDirectory() as d:
            by = make_repo(d)
            commits = self._log(d)
            labels = {by["plant it"][:9]: None, by["change d, add f, touch g"]: ["core/g.py", "docs/x.md"], by["fix: add z"]: None}
            self.assertEqual(evaluate.labelled_between(commits, labels, "2025-01-15", "2025-02-15"), {"core/f.py"}, "an abbreviated label still matches")
            self.assertEqual(evaluate.labelled_between(commits, labels, "2025-02-15", "2025-03-15"), {"core/g.py", "docs/x.md"}, "the paths the label names")
            self.assertEqual(evaluate.labelled_between(commits, labels, "2025-04-15", "2025-06-15"), {"core/g.py"})


class Score(unittest.TestCase):
    def test_effort_is_the_false_alarms_before_the_first_hit_and_the_lines_read(self):
        r = evaluate.report_at(COMMITS, "2025-06-01", SIZE, {"bots": []}, [], [])
        ranked = evaluate.variants(r)["watch list (hotspot)"]
        out = evaluate.effort(r, {ranked[1]}, 15)["watch list (hotspot)"]
        self.assertEqual(set(out), {"ifa", "lines", "popt"}, "effort reports a dict per variant, not a tuple")
        self.assertEqual(out["ifa"], 1, "one file before the first labelled one")
        self.assertEqual(out["lines"], sum(SIZE["files"][f]["code"] for f in ranked[:15]))
        self.assertEqual(evaluate.effort(r, set(), 15)["watch list (hotspot)"]["ifa"], len(ranked[:15]), "no hit: every file was a false alarm")
        table = evaluate.effort_table([{"a": {"ifa": 1, "lines": 100, "popt": 0.4}},
                                       {"a": {"ifa": 3, "lines": 300, "popt": 0.6}}])
        self.assertIn("| a | 2 | 200 | 0.5 |", table)

    def test_the_report_at_t_knows_nothing_after_t(self):
        r = evaluate.report_at(COMMITS, "2025-06-01", SIZE, {"bots": []}, [], [])
        self.assertEqual({x["entity"]: x["n-revs"] for x in r["revisions"]}, {"core/a.py": 3, "core/b.py": 2, "tests/test_a.py": 1})
        self.assertEqual(r["meta"]["now"], "2025-06-01")

    def test_every_variant_is_scored_over_one_pool_next_to_a_random_pick(self):
        r = evaluate.report_at(COMMITS, "2025-06-01", SIZE, {}, [], [])
        out = evaluate.score(r, {"core/b.py"}, top=1)
        self.assertEqual(set(out), {"watch list (hotspot)", "factor product (max-scaled)", "factor product (rank-scaled)", "churn", "size", "recent fixes",
                                    "change entropy (HCM)", "manual up (smallest first)", "change entropy (HCM3s)",
                                    "change entropy (HCM1d)", "random (expected)"})
        self.assertIn("entropy", r, "report_at carries Hassan's entropy per file for the variant to rank by")
        self.assertEqual(out["churn"], 0, "a.py changed more and was not the file fixed")
        self.assertEqual(out["random (expected)"], 0.5)
        self.assertEqual(evaluate.score(r, {"core/b.py"}, top=2)["churn"], 1)

    def test_manual_up_is_the_smallest_first_control(self):
        r = evaluate.report_at(COMMITS, "2025-06-01", SIZE, {}, [], [])
        ranked = evaluate.variants(r)["manual up (smallest first)"]
        sizes = [(SIZE["files"].get(f) or {}).get("code", 0) for f in ranked]
        self.assertEqual(sizes, sorted(sizes), "Fu and Menzies' ManualUp: the cheapest file to read comes first")

    def test_hassans_two_best_models_are_the_ones_in_the_paper(self):
        # every HCM in the paper runs on burst periods and normalises by the system's files; the s
        # superscript is the simple, undecayed sum, and the d model decays by phi
        r = evaluate.report_at(COMMITS, "2025-06-01", SIZE, {}, [], [])
        past = maat.in_window(COMMITS, until="2025-06-01")
        self.assertEqual(r["entropy_hcm3s"], maat.entropy(past, now="2025-06-01", hcpf=3, periods="burst", sizing="system", decay=1.0))
        self.assertEqual(r["entropy_hcm1d"], maat.entropy(past, now="2025-06-01", hcpf=1, periods="burst", sizing="system", phi=maat.HCM1D_PHI))

    def test_a_bot_owns_nothing_at_t_either(self):
        commits = [commit("2025-01-10", "add", ("core/a.py", 100, 0))]
        commits[0]["author"] = "release[bot]"
        self.assertEqual(evaluate.report_at(commits, "2025-06-01", SIZE, {}, [], [])["ownership"], [])


ROWS = [
    {"file": "core/parser.py", "revs": 40, "recent_fixes": 5, "complexity": 40, "solo": True, "code": 800},
    {"file": "web/index.html", "revs": 60, "recent_fixes": 0, "complexity": 0, "solo": False, "code": 4000},
    {"file": "core/util.py", "revs": 30, "recent_fixes": 0, "complexity": 5, "solo": True, "code": 200},
]


class FactorProduct(unittest.TestCase):
    def test_both_scalings_lead_with_the_fixed_complex_single_owned_file(self):
        for scaling in ("max", "rank"):
            self.assertEqual(evaluate.factor_product(ROWS, scaling), ["core/parser.py", "web/index.html", "core/util.py"], scaling)

    def test_a_file_never_fixed_gets_no_lift_from_fixes_under_either_scaling(self):
        for scaling in ("max", "rank"):
            self.assertEqual(evaluate.factor_scores(ROWS, scaling)["web/index.html"], 1.0, f"{scaling}: most changed, no fixes, no complexity, shared")

    def test_under_rank_scaling_an_outlier_does_not_rescale_the_other_files(self):
        def util(outlier_revs, scaling):
            big = {"file": "core/big.py", "revs": outlier_revs, "recent_fixes": 0, "complexity": 0, "solo": False, "code": 10}
            return evaluate.factor_scores(ROWS + [big], scaling)["core/util.py"]
        self.assertEqual(util(100, "rank"), util(10000, "rank"))
        self.assertNotEqual(util(100, "max"), util(10000, "max"), "what the rank scaling is for")

    def test_two_files_that_differ_only_in_complexity(self):
        pair = [{"file": "ops/deploy.sh", "revs": 40, "recent_fixes": 0, "complexity": 80, "solo": False, "code": 300},
                {"file": "ops/plain.sh", "revs": 40, "recent_fixes": 0, "complexity": 0, "solo": False, "code": 300}]
        for scaling in ("max", "rank"):
            scores = evaluate.factor_scores(ROWS + pair, scaling)
            self.assertGreater(scores["ops/deploy.sh"], scores["ops/plain.sh"], f"{scaling}: complexity lifts the factor product")

    def test_no_rows_is_no_list(self):
        self.assertEqual(evaluate.factor_product([], "rank"), [])


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
        self.assertIn("(3 of 40 bug-inducing)", evaluate.table([("2025-02-28", 3, 40, {"churn": 1})], noun="bug-inducing"))


class Page(unittest.TestCase):
    def test_the_effort_table_is_printed_against_fix_locality_without_labels(self):
        """Popt, IFA and the lines in the list used to appear only under --labels, so a variant could be
        compared on hits at k and never on the measure the papers state their results in."""
        results = [("2025-02-28", 3, 40, {"churn": 1, "random (expected)": 0.4})]
        efforts = [{"churn": {"ifa": 2, "lines": 300, "popt": 0.45}}]
        text = evaluate.page("r", 15, 6, results, efforts, spread={"all": 10, "head": 9, "fix_all": 3, "fix_head": 2})
        self.assertIn("### r, top 15, 6-month horizon", text)
        self.assertIn("against the fixes that followed", text)
        self.assertIn("| churn | 2 | 300 | 0.45 |", text)
        self.assertNotIn("labelled", text)
        self.assertNotIn("bug-inducing", text)
        self.assertIn("`--all` exports 10 commits (3 fixes); HEAD reaches 9 (2 fixes).", text)
        with_labels = evaluate.page("r", 15, 6, results, efforts, labelled=results, labelled_effort=efforts, labels_name="x.csv")
        self.assertIn("labelled in x.csv", with_labels)
        self.assertEqual(with_labels.count("Popt over the whole ordering"), 2, "once against the fixes, once against the labels")
        self.assertNotIn("--all", with_labels, "no spread, no line about it")


if __name__ == "__main__":
    unittest.main()

"""The harness's two definitions of a fix (gitmole/measure/outcome.py): `current`, maat.is_fix, and
`declared`, the Conventional Commits type alone where the repository declares the convention. Fixtures
only: the holdout is scored on its labels and is never read here."""
import json
import os
import subprocess
import tempfile
import unittest
from fractions import Fraction
from unittest import mock

from gitmole import evaluate, maat
from gitmole.measure import candidate, dashboard, harness, outcome, report


def _repo(d: str, subjects, files=None):
    """A git repository in `d` with one commit per subject, plus `files` ({path: text}) in the first."""
    env = dict(os.environ, GIT_CONFIG_GLOBAL="/dev/null", GIT_CONFIG_SYSTEM="/dev/null", GIT_AUTHOR_NAME="A",
               GIT_AUTHOR_EMAIL="a@x", GIT_COMMITTER_NAME="A", GIT_COMMITTER_EMAIL="a@x",
               GIT_AUTHOR_DATE="2025-01-01T10:00:00", GIT_COMMITTER_DATE="2025-01-01T10:00:00")

    def git(*args):
        subprocess.run(["git", *args], cwd=d, env=env, check=True, capture_output=True)
    git("init", "-q")
    for path, text in (files or {}).items():
        with open(os.path.join(d, path), "w") as fh:
            fh.write(text)
    for i, s in enumerate(subjects):
        with open(os.path.join(d, "a.txt"), "w") as fh:
            fh.write(str(i))
        git("add", "-A")
        git("commit", "-q", "-m", s)
    return d


def _commits(rows):
    """Canonical-log commits: (date, subject, files)."""
    return [{"hash": f"h{i}", "date": date, "subject": subject, "files": [(f, 1, 1) for f in files]}
            for i, (date, subject, files) in enumerate(rows)]


class Types(unittest.TestCase):
    def test_a_fix_by_the_declared_convention_is_a_commit_typed_fix(self):
        self.assertTrue(outcome.is_declared_fix("fix: a crash"))
        self.assertTrue(outcome.is_declared_fix("fix(core)!: a crash"))
        self.assertTrue(outcome.is_declared_fix("Fix: case does not matter to the type"))
        for subject in ("ci: fix event name", "docs: fix image path", "chore: fix lint", "Fix crash in the parser",
                        "lib: fix a leak", 'Revert "fix: a crash"', "fixup! fix: a crash", "fix:no space"):
            self.assertFalse(outcome.is_declared_fix(subject), subject)

    def test_maat_is_fix_is_untouched_and_is_the_difference(self):
        self.assertTrue(maat.is_fix("ci: fix event name"), "the current outcome keeps counting a fix word under another type")
        self.assertFalse(outcome.is_declared_fix("ci: fix event name"))

    def test_an_area_prefix_is_not_a_type(self):
        self.assertIsNone(outcome.commit_type("tool_operate: fix the progress meter"))
        self.assertEqual(outcome.commit_type("feat(api): add x"), "feat")

    def test_the_typed_share_leaves_gits_reverts_out(self):
        share = outcome.typed_share(["fix: a", "feat: b", "plain words", 'Revert "feat: b"', ""])
        self.assertEqual((share["typed"], share["subjects"], share["share"]), (2, 3, 0.6667))
        self.assertIsNone(outcome.typed_share([])["share"])


# Subjects the frozen `current` copy is checked against maat.is_fix on: prefixes, words, word boundaries, case.
SUBJECTS = ["fix: a", "Fix(core)!: b", "hotfix: c", "bugfix(x): d", "ci: fix event name", "docs: fix image path", "Fixes #12",
            "fixed the build", "fixing", "a bug", "BUGS", "regression in x", "crash on start", "crashes", "prefix the name",
            "debug output", "suffixes", "feat: add x", "Merge pull request #3", "", "bugfixes", "fix", "hotfix", "crashed"]


class FrozenCurrent(unittest.TestCase):
    def test_the_frozen_current_classifier_is_maat_is_fix(self):
        """Fails on purpose when maat.is_fix changes: keep the frozen copy (it is the yardstick) and judge the new
        classifier as a candidate against it; update this test only when the yardstick itself is meant to move."""
        self.assertEqual(outcome.CURRENT_FROM, "0.44.0")
        for subject in SUBJECTS:
            self.assertEqual(outcome.is_current_fix(subject), maat.is_fix(subject), subject)

    def test_a_candidate_editing_is_fix_does_not_move_the_outcome(self):
        commits = _commits([(f"{2020 + i // 12}-{i % 12 + 1:02d}-15", "ci: fix x" if i % 2 else "fix: y", [f"f{i % 4}.py"]) for i in range(72)])
        before = harness.cutoff_windows({"name": "r"}, commits)
        with mock.patch.object(maat, "is_fix", return_value=False):
            self.assertEqual(harness.cutoff_windows({"name": "r"}, commits), before)
            self.assertEqual(harness.cutoff_windows({"name": "r"}, commits, fix=outcome.predicate("current")), before)


class Convention(unittest.TestCase):
    def test_a_tracked_commitlint_config_declares_it_whatever_the_share(self):
        with tempfile.TemporaryDirectory() as d:
            conv = outcome.convention(_repo(d, ["start", "more"], {"commitlint.config.cjs": "module.exports = {}\n"}))
        self.assertTrue(conv["declared"])
        self.assertEqual((conv["by"], conv["config"]), (["config"], ["commitlint.config.cjs"]))
        self.assertEqual(conv["share"], 0.0)

    def test_nine_in_ten_typed_subjects_declare_it_and_eight_do_not(self):
        with tempfile.TemporaryDirectory() as d:
            conv = outcome.convention(_repo(d, ["fix: x"] * 9 + ["untyped"]))
        self.assertEqual((conv["declared"], conv["by"], conv["share"]), (True, ["typed share"], 0.9))
        with tempfile.TemporaryDirectory() as d:
            conv = outcome.convention(_repo(d, ["fix: x"] * 8 + ["untyped"] * 2))
        self.assertFalse(conv["declared"])
        self.assertEqual(outcome.describe(conv), "no (80% typed)")

    def test_a_key_in_package_json_or_pyproject_declares_it(self):
        with tempfile.TemporaryDirectory() as d:
            conv = outcome.convention(_repo(d, ["x"], {"package.json": json.dumps({"config": {"commitizen": {"path": "cz"}}}),
                                                       "pyproject.toml": "[tool.commitizen]\nname = 'cz'\n"}))
        self.assertEqual(conv["config"], ["package.json#config.commitizen", "pyproject.toml#tool.commitizen"])
        with tempfile.TemporaryDirectory() as d:
            conv = outcome.convention(_repo(d, ["x"], {"package.json": json.dumps({"name": "p", "scripts": {"commitlint": "x"}})}))
        self.assertEqual(conv["config"], [], "a script named commitlint is not a configuration")

    def test_a_path_that_is_not_a_repository_declares_nothing(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertFalse(outcome.convention(d)["declared"])

    def test_the_predicate_is_the_harness_choice(self):
        self.assertIs(outcome.predicate("current", {"declared": True}), outcome.is_current_fix)
        self.assertIs(outcome.predicate("declared", {"declared": False}), outcome.is_current_fix, "nothing declared: the two outcomes are one")
        self.assertIs(outcome.predicate("declared", {"declared": True}), outcome.is_declared_fix)
        with self.assertRaises(ValueError):
            outcome.predicate("words", {})


WINDOW = _commits([("2025-02-01", "ci: fix event name", ["ci.py"]), ("2025-02-02", "fix: a crash", ["core.py"]),
                   ("2025-02-03", "Fix the parser", ["parse.py"]), ("2025-02-04", "feat: a thing", ["new.py"])])


class Outcomes(unittest.TestCase):
    def test_fixed_between_takes_the_outcomes_classifier_and_defaults_to_is_fix(self):
        self.assertEqual(evaluate.fixed_between(WINDOW, "2025-01-01", "2025-03-01"), {"ci.py", "core.py", "parse.py"})
        self.assertEqual(evaluate.fixed_between(WINDOW, "2025-01-01", "2025-03-01", outcome.is_declared_fix), {"core.py"})

    def test_the_szz_outcome_takes_it_too(self):
        self.assertEqual([c["hash"] for c in maat.fix_commits(WINDOW)], ["h0", "h1", "h2"])
        self.assertEqual([c["hash"] for c in maat.fix_commits(WINDOW, outcome.is_declared_fix)], ["h1"])
        asked = []
        with mock.patch.object(evaluate.szz, "bug_inducing", side_effect=lambda repo, h, exclude: asked.append(h) or None):
            evaluate.induced_between("/r", WINDOW, "2025-01-01", "2025-03-01", fix=outcome.is_declared_fix)
            self.assertEqual(asked, ["h1"])
            evaluate.induced_between("/r", WINDOW, "2025-01-01", "2025-03-01")
        self.assertEqual(asked, ["h1", "h0", "h1", "h2"])

    def test_cutoff_windows_take_it_and_labels_ignore_it(self):
        commits = _commits([(f"{2020 + i // 12}-{i % 12 + 1:02d}-15", "ci: fix x" if i % 2 else "fix: y", [f"f{i % 4}.py"]) for i in range(72)])
        current = dict(harness.cutoff_windows({"name": "r"}, commits))
        declared = dict(harness.cutoff_windows({"name": "r"}, commits, fix=outcome.is_declared_fix))
        self.assertEqual(list(current), list(declared))
        self.assertTrue(all(declared[t] < current[t] for t in current), "the typed fixes are a subset here")
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(harness.declared_windows({"name": "r"}, commits, d, labels={"h1": None}), (None, {}))


def _rank(pool):
    return {"pool": pool, "revs": {f: 1 for f in pool}, "lines": {f: 10 for f in pool}, "total_code": 10 * len(pool)}


def _history(typed):
    """72 monthly commits from 2020; typed(i) says whether commit i is written in the convention."""
    return _commits([(f"{2020 + i // 12}-{i % 12 + 1:02d}-15", ("ci: fix x" if i % 2 else "fix: y") if typed(i) else ("Fix x" if i % 2 else "bug y"),
                      [f"f{i % 4}.py"]) for i in range(72)])


class RankRepo(unittest.TestCase):
    def _rank_repo(self, commits):
        with mock.patch.object(harness, "canonical_log", return_value=commits), \
             mock.patch.object(harness, "ranking_at", return_value=_rank(["f1.py", "f0.py", "f2.py", "f3.py", "g.py"])), \
             mock.patch.object(harness, "run_backtest_until", return_value=None):
            return harness.rank_repo("src", {"name": "r"}, "/no-clone", "/out", "2026-09-17", "/cache")

    def test_a_declaring_repository_is_scored_against_both(self):
        out = self._rank_repo(_history(lambda i: True))
        self.assertTrue(all(w["by"] == ["typed share"] for w in out["convention"]["windows"].values()))
        row = out["cutoffs"][0]
        self.assertEqual(row["positives"], 4, "every file was touched by a commit with a fix word")
        self.assertEqual(row["declared"]["positives"], 2, "only f0 and f2 by a commit typed fix")
        self.assertNotIn("top", row["declared"])

    def test_a_repository_that_declares_nothing_keeps_one_score(self):
        out = self._rank_repo(_history(lambda i: False))
        self.assertFalse(out["convention"]["declared"])
        self.assertTrue(all("declared" not in r for r in out["cutoffs"]))

    def test_a_late_adopter_is_switched_only_in_the_windows_after_it_adopted(self):
        out = self._rank_repo(_history(lambda i: i >= 54))   # typed from mid-2024
        declared = {r["cutoff"]: "declared" in r for r in out["cutoffs"]}
        self.assertEqual(list(declared.values()), [False] * 4 + [True] * 2, declared)
        self.assertEqual(out["cutoffs"][0]["positives"], 4, "the early windows keep their untyped fixes")

    def test_monkeypatching_is_fix_leaves_the_positives_unmoved(self):
        commits = _history(lambda i: i >= 54)
        before = self._rank_repo(commits)
        with mock.patch.object(maat, "is_fix", return_value=False):
            after = self._rank_repo(commits)
        self.assertEqual(before, after)


class WindowConvention(unittest.TestCase):
    def test_a_config_counts_from_the_cut_off_whose_tree_tracks_it(self):
        with tempfile.TemporaryDirectory() as d:
            _repo(d, ["start"])
            before = subprocess.run(["git", "rev-parse", "HEAD"], cwd=d, capture_output=True, text=True).stdout.strip()
            with open(os.path.join(d, ".commitlintrc.json"), "w") as fh:
                fh.write("{}\n")
            env = dict(os.environ, GIT_CONFIG_GLOBAL="/dev/null", GIT_AUTHOR_NAME="A", GIT_AUTHOR_EMAIL="a@x", GIT_COMMITTER_NAME="A", GIT_COMMITTER_EMAIL="a@x")
            subprocess.run(["git", "add", "-A"], cwd=d, env=env, check=True)
            subprocess.run(["git", "commit", "-q", "-m", "adopt"], cwd=d, env=env, check=True)
            conv = outcome.window_conventions(d, {"2024-01-01": (before, ["untyped"]), "2025-01-01": ("HEAD", ["untyped"]),
                                                  "2019-01-01": (None, [])})
        self.assertEqual({t: w["declared"] for t, w in conv["windows"].items()},
                         {"2019-01-01": False, "2024-01-01": False, "2025-01-01": True})
        self.assertTrue(conv["declared"])
        self.assertEqual(conv["config"], [".commitlintrc.json"])
        self.assertEqual(outcome.describe(conv), "declared in 1 of 3 windows (.commitlintrc.json)")

    def test_the_window_share_leaves_merges_out(self):
        self.assertEqual(outcome.window_subjects([{"subject": "Merge x", "files": []}, {"subject": "fix: y", "files": [("a", 1, 0)]}]), ["fix: y"])


def _record(declared_hits):
    def cut(hits, positives):
        return {"hits": hits, "expected": 1.0, "best": 5, "churn_hits": 2, "size_hits": 1, "auc": 0.6, "churn_auc": 0.5,
                "recall20": 0.3, "churn_recall20": 0.2, "positives": positives, "pool": 50}
    rows = [{**cut(4, 10), "declared": cut(declared_hits, 6)}]
    return {"repos": {"a": {"set": "development", "status": "ok", "ranking": {"cutoffs": rows, "convention": {"declared": True}}},
                      "b": {"set": "development", "status": "ok", "ranking": {"cutoffs": [cut(3, 9)], "convention": {"declared": False}}}}}


class Dashboard(unittest.TestCase):
    def test_the_summary_carries_the_declared_outcome_beside_the_current(self):
        s = dashboard.summarise(_record(declared_hits=2))
        self.assertEqual(s["declared_outcome"]["declaring"], ["a"])
        self.assertEqual(s["headroom"], 0.625, "median of a's 0.75 and b's 0.5")
        self.assertEqual(s["declared_outcome"]["headroom"], 0.375, "a at 0.25 under the declared outcome, b the same as above")
        self.assertEqual(s["declared_outcome"]["wins_losses_ties"], [1, 0, 1])
        self.assertEqual(report.declared_row(s, "development")[0][2],
                         "0.38; churn 0.25, size 0.00; repositories declaring Conventional Commits: a (the rest score as above)")

    def test_the_committed_history_page_renders_byte_for_byte(self):
        """Every record before the switch renders as the committed measurement-history.md does: the new row
        appears only for a record that carries the convention."""
        from gitmole.measure import corpus, labels
        records = os.path.join(corpus.ROOT, "docs", "measurements")
        history = dashboard.load_history(records)
        series = set((corpus.load().get("series") or {}).get("repos") or []) or None
        marks = labels._read(os.path.join(labels.DIR, "labels.jsonl"))
        for r in history:
            r["summary"], r["series"], r["useful"] = dashboard.summarise(r), dashboard.summarise(r, only=series), labels.usefulness(r, marks)
        extras_path = os.path.join(records, "extras", history[-1]["version"] + ".json")
        extras = json.load(open(extras_path, encoding="utf-8")) if os.path.exists(extras_path) else None
        with open(os.path.join(corpus.ROOT, "docs", "measurement-history.md"), encoding="utf-8") as fh:
            self.assertEqual(report.page(history, extras), fh.read())

    def test_a_record_from_before_the_switch_has_no_declared_outcome(self):
        rec = _record(2)
        for r in rec["repos"].values():
            r["ranking"].pop("convention")
            for c in r["ranking"]["cutoffs"]:
                c.pop("declared", None)
        s = dashboard.summarise(rec)
        self.assertNotIn("declared_outcome", s)
        self.assertEqual(report.declared_row(s, "development"), [])


class Candidate(unittest.TestCase):
    def _rows(self):
        row = lambda b, c: {"base_hits": b, "cand_hits": c, "d": c - b, "saturated": False, "pool_added": 0, "pool_dropped": 0}   # noqa: E731
        return {"r1": [{**row(5, 6), "declared": row(3, 1)}], "r2": [row(4, 6)]}

    def test_the_decision_reads_the_outcome_it_is_given(self):
        rows = self._rows()
        self.assertEqual(candidate.decide(rows)["effects"], {"r1": Fraction(1), "r2": Fraction(2)})
        self.assertEqual(candidate.decide(rows, "declared")["effects"], {"r1": Fraction(-2), "r2": Fraction(2)},
                         "r2 declares nothing and scores the same")

    def test_both_outcomes_are_printed_and_the_deciding_one_is_named(self):
        rows = self._rows()
        both = {o: candidate.decide(rows, o) for o in outcome.OUTCOMES}
        result = {**both["current"], "outcome": "current", "outcomes": both,
                  "conventions": {"r1": {"declared": True, "config": ["commitlint.config.cjs"], "share": 0.98}, "r2": {"declared": False, "share": 0.1}}}
        text = candidate.markdown("b", "c", "development", rows, result)
        self.assertIn("| r1 | 1 | 5 | 6 | 1.00 |", text, "the deciding table reads the current outcome")
        self.assertIn("| r1 | commitlint.config.cjs; 98% typed | 5 | 6 | 1.00 | 3 | 1 | -2.00 |", text)
        self.assertIn("| r2 | no (10% typed) | 4 | 6 | 2.00 | 4 | 6 | 2.00 |", text)
        self.assertIn("**current** decides", text)
        self.assertIn("- declared: mean effect 0.00", text)
        self.assertIn("(information)", text)
        declared = candidate.markdown("b", "c", "development", rows, {**both["declared"], "outcome": "declared", "outcomes": both, "conventions": {}})
        self.assertIn("| r1 | 1 | 3 | 1 | -2.00 |", declared, "the deciding table follows --outcome")
        self.assertIn("**declared** decides", declared)

    def test_the_holdout_refuses_the_switch_before_anything_is_read(self):
        with mock.patch.object(candidate.corpus, "load") as load, mock.patch.object(candidate, "log_holdout_read") as logged:
            self.assertEqual(candidate.main(["b", "c", "--holdout", "--approved", "x", "--outcome", "declared"]), 2)
        load.assert_not_called()
        logged.assert_not_called()

    def test_json_keeps_both_outcomes(self):
        rows = self._rows()
        both = {o: candidate.decide(rows, o) for o in outcome.OUTCOMES}
        out = candidate._jsonable({**both["current"], "outcome": "current", "outcomes": both, "conventions": {}})
        self.assertNotIn("outcomes", out)
        json.dumps(out)


class EvaluatePage(unittest.TestCase):
    def _page(self, conv, results=()):
        res = [("2025-01-01", 1, 10, {"watch list (hotspot)": 1})]
        eff = [{"watch list (hotspot)": {"ifa": 0, "lines": 10, "popt": 0.5}}]
        return evaluate.page("r", 15, 6, res, eff, declared={"convention": conv, "results": results or res, "efforts": eff, "induced": []})

    def test_a_repository_that_declares_nothing_gets_one_line(self):
        text = self._page(outcome.combine({"2025-01-01": {"declared": False, "share": 0.03, "config": []}}))
        self.assertIn("No window declares Conventional Commits (no (at most 3% typed in a window)", text)
        self.assertNotIn("declared-type outcome: the repository declares", text)

    def test_a_declaring_repository_gets_the_tables_again(self):
        text = self._page(outcome.combine({"2025-01-01": {"declared": True, "share": 0.95, "config": [".commitlintrc.json"]}}))
        self.assertIn("declares Conventional Commits (declared in 1 of 1 windows (.commitlintrc.json))", text)
        self.assertEqual(text.count("| watch list (hotspot) |"), 4, "hits and effort, under each outcome")


if __name__ == "__main__":
    unittest.main()

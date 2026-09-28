"""A ranking candidate against the current watch list: the paired arithmetic the decision rests on
(docs/measurement.md, "Is a candidate better?")."""
import json
import os
import tempfile
import unittest
from fractions import Fraction

from gitmole.measure import candidate


def _rank(pool):
    return {"pool": pool, "revs": {}, "lines": {}, "total_code": 0}


class Paired(unittest.TestCase):
    def test_both_lists_are_scored_on_the_baselines_pool(self):
        base = _rank(["a", "b", "c", "d"])
        cand = _rank(["c", "x", "a", "b"])   # x is not in the baseline's pool; d is missing from the candidate's
        row = candidate.paired(base, cand, {"c", "d"}, top=2)
        self.assertEqual(row["base_hits"], 0, "a and b")
        self.assertEqual(row["cand_hits"], 1, "c and a: x is dropped, the pool is the baseline's")
        self.assertEqual(row["d"], 1)
        self.assertEqual((row["pool"], row["positives"]), (4, 2))

    def test_a_baseline_file_the_candidate_did_not_rank_goes_last(self):
        row = candidate.paired(_rank(["a", "b", "c"]), _rank(["c"]), {"a"}, top=2)
        self.assertEqual(row["cand_hits"], 1, "c, then a from the baseline's order")

    def test_a_cut_off_is_saturated_when_half_its_pool_was_fixed(self):
        self.assertTrue(candidate.paired(_rank(["a", "b"]), _rank(["a", "b"]), {"a"}, top=1)["saturated"])
        self.assertFalse(candidate.paired(_rank(["a", "b", "c"]), _rank(["a", "b", "c"]), {"a"}, top=1)["saturated"])


class Decide(unittest.TestCase):
    def test_repository_means_then_their_mean_then_the_exact_test(self):
        rows = {"r1": [{"d": 2, "saturated": False}, {"d": 0, "saturated": False}],
                "r2": [{"d": 1, "saturated": False}],
                "r3": [{"d": -1, "saturated": True}, {"d": 0, "saturated": False}]}
        out = candidate.decide(rows)
        self.assertEqual(out["effects"], {"r1": Fraction(1), "r2": Fraction(1), "r3": Fraction(-1, 2)})
        self.assertEqual(out["mean"], Fraction(1, 2))
        self.assertEqual(out["p"], 2 / 8, "totals 2.5 and 1.5 reach the observed 1.5")
        self.assertEqual((out["wins"], out["losses"], out["ties"]), (2, 1, 0))
        self.assertEqual(out["without_saturated"]["effects"]["r3"], Fraction(0), "information only: r3 without its saturated cut-off")

    def test_a_repository_without_a_scored_cut_off_is_left_out(self):
        out = candidate.decide({"r1": [{"d": 1, "saturated": False}], "r2": []})
        self.assertEqual(list(out["effects"]), ["r1"])

    def test_the_verdict_needs_a_positive_mean_and_p_under_the_line(self):
        self.assertEqual(candidate.verdict({"mean": Fraction(1), "p": 0.01}), "better")
        self.assertEqual(candidate.verdict({"mean": Fraction(1), "p": 0.2}), "not shown")
        self.assertEqual(candidate.verdict({"mean": Fraction(0), "p": 1.0}), "not shown")
        self.assertEqual(candidate.verdict({"mean": None, "p": None}), "no data")


class HoldoutReads(unittest.TestCase):
    def test_a_candidate_is_read_once_unless_asked_again(self):
        with tempfile.TemporaryDirectory() as d:
            log = os.path.join(d, "holdout-reads.jsonl")
            candidate.log_holdout_read(log, "0.37.0", "abc", "base1", "cand1", approved="ok, the maintainer, 28 Sep")
            with self.assertRaises(candidate.SpentRead):
                candidate.log_holdout_read(log, "0.37.0", "abc", "base1", "cand1", approved="again")
            candidate.log_holdout_read(log, "0.37.0", "abc", "base1", "cand1", approved="again", again=True)
            rows = [json.loads(line) for line in open(log)]
        self.assertEqual([r["read"] for r in rows], [1, 2], "the second read is counted, not hidden")
        self.assertEqual(rows[0]["approved"], "ok, the maintainer, 28 Sep")

    def test_a_read_needs_the_maintainers_go_ahead(self):
        with tempfile.TemporaryDirectory() as d, self.assertRaises(ValueError):
            candidate.log_holdout_read(os.path.join(d, "log.jsonl"), "b", "c", "b1", "c1", approved="")


class PoolMoved(unittest.TestCase):
    def test_the_candidates_own_pool_is_compared_with_the_baselines(self):
        row = candidate.paired(_rank(["a", "b", "c", "d"]), _rank(["c", "x", "a", "b"]), {"c", "d"}, top=2)
        self.assertEqual((row["pool_added"], row["pool_dropped"]), (1, 1), "x added, d dropped")
        self.assertNotEqual(row["pool_digest"], row["cand_pool_digest"])
        same = candidate.paired(_rank(["a", "b"]), _rank(["b", "a"]), set(), top=1)
        self.assertEqual((same["pool_added"], same["pool_dropped"]), (0, 0))
        self.assertEqual(same["pool_digest"], same["cand_pool_digest"])


class Failures(unittest.TestCase):
    def test_a_failed_repository_makes_the_result_incomplete_not_smaller(self):
        row = lambda b, c: {"base_hits": b, "cand_hits": c, "d": c - b, "saturated": False, "pool_added": 0, "pool_dropped": 0}   # noqa: E731
        rows = {"r1": [row(5, 8)], "r2": [row(4, 6)], "r3": [{"error": "candidate: crashed"}]}
        out = candidate.decide(rows)
        self.assertEqual(out["failed"], {"r3": 1})
        self.assertEqual(candidate.verdict(out), "incomplete", "a candidate that crashes where it would lose is not judged on the rest")
        self.assertIn("Incomplete: r3 (1 failed)", candidate.markdown("b", "c", "development", rows, out))

    def test_a_failed_cut_off_counts_too(self):
        out = candidate.decide({"r1": [{"d": 1, "saturated": False}, {"cutoff": "2025-01-01", "error": "base: boom"}]})
        self.assertEqual(candidate.verdict(out), "incomplete")

    def test_missing_labels_are_an_error_row_not_fix_locality(self):
        from unittest import mock
        with mock.patch.object(candidate.harness, "labels_for", return_value=None), \
             mock.patch.object(candidate.corpus, "clone") as cloned:
            rows = candidate.compare_entry("b", "c", {"name": "kafka", "labels": "apachejit"}, "/nowhere", "2026-09-17", "/nowhere")
        self.assertEqual(rows, [{"error": "labels not found"}])
        cloned.assert_not_called()

    def test_the_p_value_is_printed_to_four_digits(self):
        out = {"effects": {}, "mean": Fraction(1), "p": 0.0496, "wins": 1, "losses": 0, "ties": 0, "failed": {},
               "without_saturated": {"effects": {}, "mean": None, "p": None}}
        self.assertIn("p = 0.0496", candidate.markdown("b", "c", "development", {}, out))


class HoldoutPreflight(unittest.TestCase):
    def _args(self, **kw):
        import argparse
        return argparse.Namespace(**{"base": "v0.37.0", "candidate": "cand", "only": [], **kw})

    def test_a_working_tree_a_subset_and_a_missing_clone_are_refused_before_the_read(self):
        from unittest import mock
        with tempfile.TemporaryDirectory() as root, mock.patch.object(candidate.harness, "labels_for", return_value={"x": 1}):
            problems = candidate.holdout_preflight(self._args(candidate="worktree", only=["kafka"]),
                                                   [{"name": "kafka", "commit": "0" * 40, "labels": "apachejit"}], root, root)
        self.assertEqual(len(problems), 3)
        self.assertTrue(any("working tree" in p for p in problems))
        self.assertTrue(any("--only" in p for p in problems))
        self.assertTrue(any(p.startswith("kafka: no clone") for p in problems))

    def test_missing_labels_are_refused_before_the_read(self):
        from unittest import mock
        with tempfile.TemporaryDirectory() as root, mock.patch.object(candidate.harness, "labels_for", return_value=None):
            problems = candidate.holdout_preflight(self._args(), [{"name": "kafka", "commit": "0" * 40, "labels": "apachejit"}], root, root)
        self.assertTrue(any("labels are not in" in p for p in problems))

    def test_the_read_records_its_sets(self):
        with tempfile.TemporaryDirectory() as d:
            row = candidate.log_holdout_read(os.path.join(d, "log.jsonl"), "b", "c", "b1", "c1", approved="yes", sets="holdout")
        self.assertEqual(row["sets"], "holdout")

    def test_a_ref_that_is_not_a_commit_is_refused(self):
        with self.assertRaises(ValueError):
            candidate.resolve("no-such-ref-anywhere")
        with tempfile.TemporaryDirectory() as d, self.assertRaises(ValueError):
            candidate.log_holdout_read(os.path.join(d, "log.jsonl"), "b", "c", "b1", "", approved="yes")


class CutoffWindows(unittest.TestCase):
    def test_the_cut_offs_and_their_outcomes(self):
        from gitmole.measure import harness
        commits = [{"hash": f"h{i}", "date": f"{2020 + i // 12}-{i % 12 + 1:02d}-15T00:00:00+00:00", "subject": "fix: x" if i % 2 else "feat: y",
                    "files": [(f"f{i % 3}.py", 1, 1)]} for i in range(72)]
        windows = harness.cutoff_windows({"name": "r"}, commits)
        self.assertEqual(len(windows), harness.WINDOWS)
        self.assertEqual([t for t, _ in windows], sorted(t for t, _ in windows), "oldest first")
        self.assertTrue(all(isinstance(o, set) for _, o in windows))
        self.assertTrue(all(o for _, o in windows), "every window holds a fix")
        self.assertEqual(harness.cutoff_windows({"name": "r"}, []), [])

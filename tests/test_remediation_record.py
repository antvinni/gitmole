"""Remediation in the release record: the harness asks remediation's question at the ranking's cut-offs,
the record keeps the outcome counts by rule, and the summary and the history page pool them. The
predicates themselves are tests/test_remediation.py's; nothing here changes what they decide."""
import contextlib
import io
import json
import os
import subprocess
import tempfile
import unittest
from unittest import mock

from gitmole.measure import dashboard, harness
from gitmole.measure import remediation as r

WF = ".github/workflows/ci.yml"
_ENV = dict(os.environ, GIT_CONFIG_GLOBAL="/dev/null", GIT_CONFIG_SYSTEM="/dev/null",
            GIT_AUTHOR_NAME="a", GIT_AUTHOR_EMAIL="a@example.org", GIT_COMMITTER_NAME="a", GIT_COMMITTER_EMAIL="a@example.org")


def _git(cwd, *a, date=None):
    env = dict(_ENV, **({"GIT_AUTHOR_DATE": date, "GIT_COMMITTER_DATE": date} if date else {}))
    return subprocess.run(["git", *a], cwd=cwd, env=env, check=True, capture_output=True, text=True).stdout.strip()


def _commit(repo, files, date, message="c"):
    for path, text in files.items():
        full = os.path.join(repo, path)
        if text is None:
            _git(repo, "rm", "-q", path)
            continue
        os.makedirs(os.path.dirname(full) or repo, exist_ok=True)
        with open(full, "w") as fh:
            fh.write(text)
        _git(repo, "add", path)
    _git(repo, "commit", "-q", "-m", message, date=date + "T12:00:00+00:00")


def _repo(tmp):
    """A workflow with a tag-pinned action and a committed binary, at 2025-01-10; by 2025-06-10 the
    action is pinned to a commit and the binary deleted; the history ends 2025-09-10."""
    _git(tmp, "init", "-q", "-b", "main")
    _commit(tmp, {WF: "    - uses: actions/checkout@v4\n", "tool.exe": "MZ"}, "2025-01-10")
    _commit(tmp, {WF: "    - uses: actions/checkout@11d5960a326750d5838078e36cf38b85af677262 # v4\n", "tool.exe": None}, "2025-06-10")
    _commit(tmp, {"README": "x\n"}, "2025-09-10")


FINDINGS = [{"rule": {"id": "unpinned_actions"}, "evidence": {"unpinned": [{"file": WF, "uses": "actions/checkout@v4"}]}},
            {"rule": {"id": "committed_binaries"}, "evidence": {"executables": [{"file": "tool.exe"}]}},
            {"rule": {"id": "knowledge_islands"}, "evidence": {}}]


class Pooled(unittest.TestCase):
    def test_counts_are_summed_and_the_share_follows_gone_is_fix(self):
        rows = [{"committed_binaries": {"resolved": 1, "open": 2, "gone": 1, "unknown": 0, "absent": 3},
                 "brain_methods": {"resolved": 1, "open": 1, "gone": 2, "unknown": 4, "absent": 0}},
                {"committed_binaries": {"resolved": 0, "open": 0, "gone": 1, "unknown": 0, "absent": 0}}]
        p = r.pooled(rows)
        self.assertEqual(p["committed_binaries"]["gone"], 2)
        self.assertEqual((p["committed_binaries"]["judged"], p["committed_binaries"]["acted_on"]), (5, 3), "left the tree is the fix")
        self.assertEqual((p["brain_methods"]["judged"], p["brain_methods"]["acted_on"]), (2, 1), "left the tree says nothing")
        self.assertTrue(p["committed_binaries"]["gone_is_fix"])
        self.assertFalse(p["brain_methods"]["gone_is_fix"])
        self.assertEqual(p["committed_binaries"]["share"], 0.6)

    def test_nothing_judged_is_no_share_not_zero(self):
        self.assertIsNone(r.pooled([{"brain_methods": {"unknown": 3}}])["brain_methods"]["share"])

    def test_bands_pool_subjects_not_shares(self):
        p = r.pooled([{"unpinned_actions": {"resolved": 1, "open": 0}, "lockfile_drift": {"resolved": 0, "open": 9},
                       "brain_methods": {"resolved": 1, "open": 1}}])
        b = r.bands(p)
        self.assertEqual(b["mechanical"], {"judged": 10, "acted_on": 1, "share": 0.1})
        self.assertEqual(b["structural"]["judged"], 2)

    def test_a_rule_the_table_does_not_know_is_ignored(self):
        self.assertEqual(r.pooled([{"no_such_rule": {"resolved": 1}}]), {})


class OverWindow(unittest.TestCase):
    def test_a_window_over_a_real_history(self):
        with tempfile.TemporaryDirectory() as tmp:
            _repo(tmp)
            row = r.over_window(FINDINGS, tmp, "2025-02-01", 6)
            self.assertEqual(row["end"], "2025-08-01")
            self.assertEqual(row["rules"]["unpinned_actions"]["resolved"], 1)
            self.assertEqual(row["rules"]["committed_binaries"]["open"] + row["rules"]["committed_binaries"]["resolved"], 0)
            self.assertEqual(row["rules"]["committed_binaries"]["gone"], 1)
            self.assertEqual(row["unscored"], ["knowledge_islands"])
            self.assertEqual(row["findings"], 3)

    def test_a_window_past_the_history_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            _repo(tmp)
            self.assertIn("error", r.over_window(FINDINGS, tmp, "2025-06-01", 6))


class AtTheCutOffs(unittest.TestCase):
    """The harness's half: a checkout of the cut-off, the release's own export of it, the predicates."""

    def _fake_run(self, seen):
        def run_release(src, clone, work, reference, **kw):
            seen.append({"head": _git(clone, "rev-parse", "HEAD"), "reference": reference, "src": src,
                         "log": _git(clone, "log", "--format=%cs")})
            os.makedirs(os.path.join(work, "out"))
            report = os.path.join(work, "report.json")
            with open(report, "w") as fh:
                json.dump({"findings": FINDINGS}, fh)
            return {"status": "ok", "seconds": 1.0, "peak_mb": 10, "report": report, "out": os.path.join(work, "out")}
        return run_release

    def test_one_cut_off_runs_the_release_on_the_tree_at_the_cut_off(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo, work = os.path.join(tmp, "repo"), os.path.join(tmp, "work")
            os.makedirs(repo)
            _repo(repo)
            first = _git(repo, "rev-list", "--max-parents=0", "HEAD")
            seen = []
            with mock.patch.object(harness, "run_release", self._fake_run(seen)):
                row = harness.remediation_at("/src", repo, work, "2025-02-01")
            self.assertEqual(seen[0]["head"], first, "the tree as of the cut-off")
            self.assertEqual(seen[0]["log"], "2025-01-10", "and only the history up to it")
            self.assertEqual(seen[0]["reference"], "2025-02-01", "GITMOLE_NOW is the cut-off")
            self.assertEqual(row["rules"]["unpinned_actions"]["resolved"], 1)
            self.assertFalse(os.path.exists(os.path.join(work, "tree")), "the checkout is removed")
            self.assertFalse(os.path.exists(os.path.join(work, "run", "out")), "the run's output directory too")
            self.assertTrue(os.path.exists(os.path.join(work, "run", "report.json")), "the export is kept")
            self.assertEqual(_git(repo, "rev-parse", "--abbrev-ref", "HEAD"), "main", "the corpus clone is untouched")
            self.assertEqual(_git(repo, "worktree", "list").count("\n"), 0)

    def test_a_release_that_fails_at_a_cut_off_is_recorded_not_scored(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = os.path.join(tmp, "repo")
            os.makedirs(repo)
            _repo(repo)
            crash = lambda *a, **k: {"status": "crashed", "note": "boom", "report": None}   # noqa: E731
            with mock.patch.object(harness, "run_release", crash):
                row = harness.remediation_at("/src", repo, os.path.join(tmp, "work"), "2025-02-01")
            self.assertEqual(row["error"], "crashed: boom")
            self.assertNotIn("rules", row)

    def test_a_window_past_the_history_runs_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            _repo(tmp)
            with mock.patch.object(harness, "run_release", lambda *a, **k: self.fail("ran")):
                row = harness.remediation_at("/src", tmp, os.path.join(tmp, "work"), "2025-06-01")
            self.assertIn("past this history", row["error"])

    def test_the_cut_offs_are_the_rankings(self):
        rows = []
        cutoffs = [("2025-01-01", set()), ("2025-07-01", set())]
        with mock.patch.object(harness, "canonical_log", lambda clone, cache: [{}]), \
                mock.patch.object(harness, "cutoff_windows", lambda entry, commits: cutoffs), \
                mock.patch.object(harness, "remediation_at", lambda src, clone, work, t, seen=None: rows.append(t) or
                                  ({"cutoff": t, "rules": {"unpinned_actions": {"resolved": 1}}} if t < "2025-06" else {"cutoff": t, "error": "x"})):
            out = harness.remediate_repo("/src", {"name": "x"}, "/clone", "/work", "/cache")
        self.assertEqual(rows, ["2025-01-01", "2025-07-01"])
        self.assertEqual(out["horizon"], harness.HORIZON)
        self.assertEqual(out["rules"]["unpinned_actions"]["acted_on"], 1, "a failed cut-off is left out of the pool")
        self.assertEqual(len(out["cutoffs"]), 2, "and kept in the rows")

    def test_one_set_of_counted_subjects_spans_the_cut_offs_oldest_first(self):
        """A subject named at six cut-offs is one subject: the set remediation_at scores against is shared."""
        sets, order = [], []
        cutoffs = [("2025-07-01", set()), ("2025-01-01", set())]
        with mock.patch.object(harness, "canonical_log", lambda clone, cache: [{}]), \
                mock.patch.object(harness, "cutoff_windows", lambda entry, commits: cutoffs), \
                mock.patch.object(harness, "remediation_at", lambda src, clone, work, t, seen=None: sets.append(seen) or order.append(t)
                                  or {"cutoff": t, "rules": {}}):
            harness.remediate_repo("/src", {"name": "x"}, "/clone", "/work", "/cache")
        self.assertEqual(order, ["2025-01-01", "2025-07-01"])
        self.assertIsNotNone(sets[0])
        self.assertIs(sets[0], sets[1])

    def test_moved_and_repeats_are_kept_and_moved_is_judged(self):
        pooled = r.pooled([{"unreferenced_files": {"resolved": 1, "open": 1, "moved": 2, "repeat": 5}},
                           {"brain_methods": {"resolved": 1, "moved": 3}}])
        self.assertEqual((pooled["unreferenced_files"]["moved"], pooled["unreferenced_files"]["repeat"]), (2, 5))
        self.assertEqual(pooled["unreferenced_files"]["judged"], 4, "a moved file is judged, and not acted on")
        self.assertEqual(pooled["unreferenced_files"]["acted_on"], 1)
        self.assertEqual(pooled["brain_methods"]["judged"], 1, "a renamed function is a survivor: can't say")
        old = r.pooled([{"unreferenced_files": {"resolved": 1, "open": 1}}])
        self.assertEqual((old["unreferenced_files"]["moved"], old["unreferenced_files"]["judged"]), (0, 2), "a record from before reads as zero")


class InTheRound(unittest.TestCase):
    def _rank(self, entry, remediation=True):
        rec = {"status": "ok", "out": "/out", "clone": "/clone"}   # no report: the label ids are not this test's
        with mock.patch.object(harness, "rank_repo", lambda *a, **k: {"cutoffs": []}), \
                mock.patch.object(harness, "remediate_repo", lambda *a, **k: {"rules": {}}), \
                mock.patch.object(harness, "version_of", lambda src: "9.9.9"):
            return harness.rank_entry("/src", dict(entry, name="x"), "/root", "2026-09-17", rec, None, remediation)

    def test_only_when_the_round_asks(self):
        self.assertNotIn("remediation", self._rank({"set": "development"}, remediation=False), "the fast loop leaves it out")

    def test_a_release_round_asks(self):
        from gitmole.measure import __main__ as main
        seen = []
        measure = lambda ref, sets, manifest, root, only, jobs, remediation: seen.append(remediation) or {"version": "9.9.9"}   # noqa: E731
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(main, "measure", measure), \
                mock.patch.object(main, "write", lambda record: os.path.join(tmp, "9.9.9.json")), \
                mock.patch.object(main.corpus, "load", lambda: {}), mock.patch.object(main.corpus, "workspace", lambda: tmp), \
                mock.patch.object(main.harness, "keep_awake") as awake, contextlib.redirect_stdout(io.StringIO()):
            main.main(["run", "--release"])
            main.main(["run"])
            main.main(["run", "--only", "curl", "--remediation"])
            main.main(["run", "--release", "--remediation"])
            main.main(["run", "--release", "--no-remediation"])
        self.assertEqual(seen, ["auto", False, True, True, "off"], "a release round asks when what it depends on changed; --remediation forces it")
        self.assertEqual(awake.call_count, 5, "every run keeps the machine awake")

    def test_the_development_set_is_asked(self):
        self.assertIn("remediation", self._rank({"set": "development"}))

    def test_the_large_set_is_not(self):
        self.assertNotIn("remediation", self._rank({"set": "large"}), "the maintainer's decision: development only")

    def test_holdout_well_kept_and_fixtures_are_not(self):
        with mock.patch.object(harness, "labels_for", lambda *a: {}):
            self.assertNotIn("remediation", self._rank({"set": "holdout", "labels": "apachejit"}))
        self.assertNotIn("remediation", self._rank({"set": "well-kept"}))
        self.assertNotIn("remediation", self._rank({"set": "gate", "fixture": "secret"}))


def _rec(rules, set_="development"):
    return {"status": "ok", "set": set_, "findings": 4, "report_lines": 100, "seconds": 10, "peak_mb": 100,
            "remediation": {"horizon": 6, "cutoffs": [{"cutoff": "2025-01-01", "rules": rules}, {"cutoff": "2025-07-01", "error": "x"}],
                            "rules": r.pooled([rules])}}


class Summary(unittest.TestCase):
    def test_pooled_over_the_development_set_only(self):
        record = {"version": "9.9.9", "repos": {
            "a": _rec({"unpinned_actions": {"resolved": 2, "open": 2}}),
            "b": _rec({"unpinned_actions": {"resolved": 1, "open": 5}, "brain_methods": {"gone": 3, "unknown": 1}}),
            "L": _rec({"unpinned_actions": {"resolved": 9}}, "large"),
            "k": _rec({"unpinned_actions": {"resolved": 9}}, "well-kept")}}
        s = dashboard.summarise(record)
        acted = s["remediation"]
        self.assertEqual(acted["repos"], 2)
        self.assertEqual(acted["cutoffs"], [2, 4])
        self.assertEqual((acted["rules"]["unpinned_actions"]["acted_on"], acted["rules"]["unpinned_actions"]["judged"]), (3, 10))
        self.assertEqual(acted["rules"]["brain_methods"]["judged"], 0)
        self.assertEqual(acted["bands"]["mechanical"]["share"], 0.3)
        self.assertFalse([k for k in s if "remediation" in k and k != "remediation"], "the large set is not asked")

    def test_a_record_without_it_has_no_key(self):
        rec = _rec({})
        rec.pop("remediation")
        s = dashboard.summarise({"version": "9.9.9", "repos": {"a": rec}})
        self.assertNotIn("remediation", s)
        self.assertNotIn("remediation", dashboard.summarise({"version": "9.9.9", "repos": {"a": _rec({})}}, only={"a"}),
                         "the series graphs do not draw it")


class Page(unittest.TestCase):
    def _record(self, with_it=True):
        rec = _rec({"unpinned_actions": {"resolved": 2, "open": 2}, "brain_methods": {"gone": 3, "open": 6}})
        if not with_it:
            rec.pop("remediation")
        record = {"version": "9.9.9", "reference_date": "2026-09-17", "repos": {"a": rec}}
        record["summary"] = dashboard.summarise(record)
        return record

    def test_the_section_and_the_row(self):
        from gitmole.measure import report
        text = "\n".join(report.current(self._record(), None))
        self.assertIn("### Was it acted on? Remediation by rule, as the yardstick stands", text)
        self.assertIn("| unpinned_actions | mechanical | 2 | 2 | 0 | 0 | no | 0 | 0 | 0 | 2 of 4 |", text, "under five judged, a fraction")
        self.assertIn("| brain_methods | structural | 0 | 6 | 0 | 3 | no | 0 | 0 | 0 | 0 of 6 (0%) |", text)
        self.assertIn("mechanical 2 of 4; structural 0 of 6 (0%)", text)
        self.assertLess(text.index("unpinned_actions"), text.index("brain_methods"), "mechanical first")

    def test_a_record_without_it_says_so(self):
        from gitmole.measure import report
        text = "\n".join(report.current(self._record(False), None))
        self.assertIn("| subjects the repository acted on within six months, mechanical and structural rules (a lower bound) | development | not in this record |", text)
        self.assertNotIn("### Was it acted on?", text)


if __name__ == "__main__":
    unittest.main()

"""When a release round asks remediation's question: only when a path its rows depend on
(remediation.ASKED_WHEN_CHANGED) changed since the last record that asked it. Otherwise the record says
"not asked" and why, and never carries a number forward."""
import glob
import json
import os
import subprocess
import tempfile
import unittest
from unittest import mock

from gitmole.measure import __main__ as main
from gitmole.measure import dashboard, harness, report
from gitmole.measure import remediation as r

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_ENV = dict(os.environ, GIT_CONFIG_GLOBAL="/dev/null", GIT_CONFIG_SYSTEM="/dev/null",
            GIT_AUTHOR_NAME="a", GIT_AUTHOR_EMAIL="a@example.org", GIT_COMMITTER_NAME="a", GIT_COMMITTER_EMAIL="a@example.org")

# Every module under gitmole/ the trigger leaves out, and why it cannot change a scored finding. A new
# module must be added to remediation.ASKED_WHEN_CHANGED or here: when in doubt, there.
LEFT_OUT = {
    "gitmole/__init__.py": "the version string, which every release changes and no finding reads",
    "gitmole/banner.py": "the terminal banner",
    "gitmole/brief.py": "the default terminal report's short form of a finding: it reads the rule and the evidence and writes neither, and remediation reads the export",
    "gitmole/clean.py": "--clean",
    "gitmole/section.py": "--section and --csv: one section of a finished report on its own; it reads the report and writes nothing remediation reads",
    "gitmole/doctor.py": "--doctor",
    "gitmole/install.py": "--install-tools",
    "gitmole/feedback.py": "--feedback, after the report",
    "gitmole/sarif.py": "--sarif, which remediation's scans do not ask for",
    "gitmole/sbom.py": "--sbom, likewise",
    "gitmole/compare.py": "--compare, likewise",
    "gitmole/hook.py": "--hook, likewise",
    "gitmole/evaluate.py": "a development tool, not a pipeline step",
    "gitmole/szz.py": "R-SZZ for evaluate --szz, not a pipeline step",
}
LEFT_OUT_MEASURE = "the harness's other questions; remediation's own code is remediation.py and harness.py"


def _git(cwd, *a):
    return subprocess.run(["git", *a], cwd=cwd, env=_ENV, check=True, capture_output=True, text=True).stdout.strip()


def _write(root, path, text):
    full = os.path.join(root, path)
    os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, "w") as fh:
        fh.write(text)


def _checkout(tmp):
    """A gitmole-shaped checkout with one commit; returns its sha."""
    _git(tmp, "init", "-q", "-b", "main")
    for path in ("gitmole/findings.py", "gitmole/banner.py", "gitmole/measure/remediation.py", "docs/measurement.md"):
        _write(tmp, path, "x = 1\n")
    _git(tmp, "add", "gitmole", "docs")
    _git(tmp, "commit", "-q", "-m", "a")
    return _git(tmp, "rev-parse", "HEAD")


def _commit(tmp, path, text="x = 2\n"):
    _write(tmp, path, text)
    _git(tmp, "add", path)
    _git(tmp, "commit", "-q", "-m", path)
    return _git(tmp, "rev-parse", "HEAD")


def _record(version, commit, asked=True):
    summary = {"remediation": {"rules": {}, "bands": {}, "repos": 1, "cutoffs": [6, 6]}} if asked else \
              {"remediation": {"asked": False, "reason": "x"}}
    return {"version": version, "commit": commit, "repos": {}, "summary": summary}


class Trigger(unittest.TestCase):
    def test_a_changed_rule_module_asks(self):
        with tempfile.TemporaryDirectory() as tmp:
            prev = _checkout(tmp)
            head = _commit(tmp, "gitmole/findings.py")
            asked, reason, changed = r.asked_since(tmp, _record("0.1.0", prev), head)
            self.assertTrue(asked)
            self.assertEqual(changed, ["gitmole/findings.py"])
            self.assertIn("changed since 0.1.0", reason)

    def test_each_named_group_asks(self):
        with tempfile.TemporaryDirectory() as tmp:
            prev = _checkout(tmp)
            for path in ("gitmole/measure/remediation.py", "gitmole/classify.py", "gitmole/filetypes.py", "measure/corpus.json"):
                head = _commit(tmp, path, path + "\n")
                self.assertTrue(r.asked_since(tmp, _record("0.1.0", prev), head)[0], path)
                prev = head

    def test_unchanged_paths_are_not_asked_and_say_since_when(self):
        with tempfile.TemporaryDirectory() as tmp:
            prev = _checkout(tmp)
            _commit(tmp, "gitmole/banner.py")
            head = _commit(tmp, "docs/measurement.md")
            asked, reason, changed = r.asked_since(tmp, _record("0.1.0", prev), head)
            self.assertFalse(asked)
            self.assertEqual(changed, [])
            self.assertEqual(reason, f"the paths it depends on are unchanged since 0.1.0 ({prev[:12]})")

    def test_an_uncommitted_edit_in_the_worktree_asks(self):
        with tempfile.TemporaryDirectory() as tmp:
            prev = _checkout(tmp)
            self.assertFalse(r.asked_since(tmp, _record("0.1.0", prev))[0])
            _write(tmp, "gitmole/findings.py", "x = 3\n")
            self.assertTrue(r.asked_since(tmp, _record("0.1.0", prev))[0], "a run of the worktree reads it as it is")

    def test_no_earlier_record_or_an_unknown_commit_asks(self):
        with tempfile.TemporaryDirectory() as tmp:
            _checkout(tmp)
            self.assertEqual(r.asked_since(tmp, None)[:2], (True, "no earlier record asked it"))
            asked, reason, _ = r.asked_since(tmp, _record("0.1.0", "0" * 40))
            self.assertTrue(asked)
            self.assertIn("cannot compare", reason)


class Decision(unittest.TestCase):
    def _records(self, tmp, *records):
        d = os.path.join(tmp, "records")
        os.makedirs(d)
        for rec in records:
            with open(os.path.join(d, rec["version"] + ".json"), "w") as fh:
                json.dump(rec, fh)
        return d

    def test_forced_runs_whatever_changed(self):
        with tempfile.TemporaryDirectory() as tmp:
            prev = _checkout(tmp)
            d = self._records(tmp, _record("0.1.0", prev))
            with mock.patch.object(main.corpus, "ROOT", tmp):
                self.assertFalse(main.remediation_decision("auto", "worktree", prev, "0.2.0", d)["asked"])
                self.assertTrue(main.remediation_decision(True, "worktree", prev, "0.2.0", d)["asked"])
                off = main.remediation_decision("off", "worktree", prev, "0.2.0", d)
                self.assertEqual((off["asked"], off["reason"]), (False, "--no-remediation"))
                self.assertIsNone(main.remediation_decision(False, "worktree", prev, "0.2.0", d)["reason"], "the fast loop records nothing")

    def test_it_diffs_from_the_last_record_that_asked(self):
        """0.2.0 did not ask; 0.3.0 compares with 0.1.0, whose numbers are the ones that stand."""
        with tempfile.TemporaryDirectory() as tmp:
            first = _checkout(tmp)
            second = _commit(tmp, "gitmole/findings.py")
            d = self._records(tmp, _record("0.1.0", first), _record("0.2.0", second, asked=False))
            self.assertEqual(main.last_asked("0.3.0", d)["version"], "0.1.0")
            self.assertIsNone(main.last_asked("0.1.0", d), "never the record being made, nor a later one")
            with mock.patch.object(main.corpus, "ROOT", tmp):
                got = main.remediation_decision("auto", "v0.3.0", second, "0.3.0", d)
            self.assertTrue(got["asked"])
            self.assertEqual(got["changed"], ["gitmole/findings.py"])


class NotAskedInTheRecord(unittest.TestCase):
    def _rank(self, **kw):
        rec = {"status": "ok", "out": "/out", "clone": "/clone"}
        with mock.patch.object(harness, "rank_repo", lambda *a, **k: {"cutoffs": []}), \
                mock.patch.object(harness, "remediate_repo", lambda *a, **k: {"rules": {"unpinned_actions": {"resolved": 1}}}), \
                mock.patch.object(harness, "version_of", lambda src: "9.9.9"):
            return harness.rank_entry("/src", {"set": "development", "name": "x"}, "/root", "2026-09-17", rec, None, **kw)

    def test_an_entry_not_asked_carries_the_reason_and_no_number(self):
        rec = self._rank(remediation=False, not_asked="the paths it depends on are unchanged since 0.1.0 (abc)")
        self.assertEqual(rec["remediation"], {"asked": False, "reason": "the paths it depends on are unchanged since 0.1.0 (abc)"})
        self.assertIn("rules", self._rank(remediation=True)["remediation"], "asked: the numbers")

    def test_the_summary_shows_a_gap_and_the_page_says_not_asked(self):
        rec = {"status": "ok", "set": "development", "findings": 4, "report_lines": 100, "seconds": 10, "peak_mb": 100,
               "remediation": {"asked": False, "reason": "the paths it depends on are unchanged since 0.1.0 (abc)"}}
        s = dashboard.summarise({"version": "0.2.0", "repos": {"a": rec, "b": dict(rec)}})
        self.assertEqual(s["remediation"], {"asked": False, "reason": "the paths it depends on are unchanged since 0.1.0 (abc)"})
        with mock.patch.object(report.labels, "score", lambda: {"verdicts": {}}):
            page = "\n".join(report.current({"version": "0.2.0", "summary": s, "repos": {}}, {}))
        self.assertIn("not asked (the paths it depends on are unchanged since 0.1.0 (abc))", page)
        self.assertNotIn("Was it acted on?", page, "no table, and nothing copied from an earlier record")


class EveryModuleIsSorted(unittest.TestCase):
    def test_each_module_is_watched_or_left_out_with_a_reason(self):
        watched = set(r.watched_paths())
        for path in sorted(glob.glob(os.path.join(ROOT, "gitmole", "**", "*.py"), recursive=True)):
            rel = os.path.relpath(path, ROOT)
            if rel in watched or rel in LEFT_OUT or (rel.startswith("gitmole/measure/") and "__pycache__" not in rel):
                continue
            self.fail(f"{rel}: add it to remediation.ASKED_WHEN_CHANGED (the default) or to LEFT_OUT with a reason")
        for path in watched:
            self.assertTrue(os.path.exists(os.path.join(ROOT, path)), f"{path} is watched but does not exist")
        self.assertFalse(watched & set(LEFT_OUT))

    def test_the_named_paths(self):
        watched = set(r.watched_paths())
        self.assertLessEqual({"gitmole/measure/remediation.py", "gitmole/classify.py", "gitmole/filetypes.py",
                              "gitmole/findings.py", "gitmole/measure/harness.py"}, watched)


if __name__ == "__main__":
    unittest.main()

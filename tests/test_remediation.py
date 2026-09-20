"""The remediation predicates, against a stub tree. No repository is cloned and no git runs."""
import unittest

from gitmole.measure import remediation as r

WF = ".github/workflows/ci.yml"


class Tree:
    """Stands in for remediation.After: a dict of the tree at the far end of the window."""

    def __init__(self, files, days=None, links=(), cutoff="2025-01-01"):
        self.files, self.days, self.links, self.cutoff = files, days or {}, set(links), cutoff

    def exists(self, path):
        return path in self.files

    def text(self, path):
        return self.files.get(path)

    def is_symlink(self, path):
        return path in self.links

    def last_commit_day(self, path):
        return self.days.get(path)


class UnpinnedActions(unittest.TestCase):
    def sub(self):
        return {"file": WF, "uses": "actions/checkout@v4"}

    def test_a_tag_is_still_open(self):
        self.assertEqual(r._unpinned_action(self.sub(), Tree({WF: "    - uses: actions/checkout@v4\n"})), r.OPEN)

    def test_a_commit_hash_is_the_fix(self):
        after = Tree({WF: "    - uses: actions/checkout@11d5960a326750d5838078e36cf38b85af677262 # v4\n"})
        self.assertEqual(r._unpinned_action(self.sub(), after), r.RESOLVED)

    def test_dropping_the_action_counts_too(self):
        self.assertEqual(r._unpinned_action(self.sub(), Tree({WF: "    - uses: actions/setup-python@v5\n"})), r.RESOLVED)

    def test_a_deleted_workflow_is_gone_not_fixed(self):
        self.assertEqual(r._unpinned_action(self.sub(), Tree({})), r.GONE)


class TrojanSource(unittest.TestCase):
    def test_the_codepoint_not_the_line(self):
        sub = {"file": "a.s", "line": 2, "char": "U+202E"}
        self.assertEqual(r._bidi_char(sub, Tree({"a.s": "x‮y"})), r.OPEN)
        self.assertEqual(r._bidi_char(sub, Tree({"a.s": "\n\n\nx‮y"})), r.OPEN)   # the line moved; the char did not
        self.assertEqual(r._bidi_char(sub, Tree({"a.s": "xy"})), r.RESOLVED)

    def test_a_mixed_script_token(self):
        sub = {"file": "b.go", "token": "x18І"}
        self.assertEqual(r._mixed_script(sub, Tree({"b.go": "const s = x18І"})), r.OPEN)
        self.assertEqual(r._mixed_script(sub, Tree({"b.go": "const s = x18I"})), r.RESOLVED)


class Lockfiles(unittest.TestCase):
    def test_drift_closes_when_the_lockfile_catches_up(self):
        sub = {"manifest": "a/package.json", "lockfile": "a/package-lock.json"}
        stale = Tree({}, days={"a/package.json": "2025-06-01", "a/package-lock.json": "2025-03-01"})
        fresh = Tree({}, days={"a/package.json": "2025-06-01", "a/package-lock.json": "2025-06-02"})
        self.assertEqual(r._lockfile_drift(sub, stale), r.OPEN)
        self.assertEqual(r._lockfile_drift(sub, fresh), r.RESOLVED)

    def test_the_expected_lockfile_sits_beside_its_manifest(self):
        sub = {"manifest": "a/package.json", "expected": ["package-lock.json"]}
        self.assertEqual(r._lockfile_missing(sub, Tree({"a/package.json": "{}", "a/package-lock.json": "{}"})), r.RESOLVED)
        self.assertEqual(r._lockfile_missing(sub, Tree({"a/package.json": "{}", "package-lock.json": "{}"})), r.OPEN)


class Binaries(unittest.TestCase):
    def test_an_lfs_pointer_is_the_fix(self):
        sub = {"file": "bin/tool"}
        self.assertEqual(r._committed_binary(sub, Tree({"bin/tool": "\x7fELF"})), r.OPEN)
        self.assertEqual(r._committed_binary(sub, Tree({"bin/tool": r._LFS_POINTER + "\noid sha256:aa\n"})), r.RESOLVED)
        self.assertEqual(r._committed_binary(sub, Tree({})), r.GONE)


class Dependencies(unittest.TestCase):
    def test_a_package_that_left_the_manifest(self):
        sub = {"manifest": "package.json", "package": "lodash"}
        self.assertEqual(r._unused_dependency(sub, Tree({"package.json": '{"dependencies":{"lodash":"^4"}}'})), r.OPEN)
        self.assertEqual(r._unused_dependency(sub, Tree({"package.json": '{"dependencies":{"react":"^19"}}'})), r.RESOLVED)

    def test_a_version_that_left_the_lock_file(self):
        sub = {"source": "go.sum", "version": "1.2.3"}
        self.assertEqual(r._vulnerable_package(sub, Tree({"go.sum": "pkg v1.2.3 h1:aa"})), r.OPEN)
        self.assertEqual(r._vulnerable_package(sub, Tree({"go.sum": "pkg v1.2.4 h1:aa"})), r.RESOLVED)


class Files(unittest.TestCase):
    def test_untracking_is_the_fix(self):
        self.assertEqual(r._untracked({"file": ".env"}, Tree({".env": "A=1"})), r.OPEN)
        self.assertEqual(r._untracked({"file": ".env"}, Tree({})), r.RESOLVED)

    def test_a_reference_replaces_a_literal(self):
        sub = {"file": ".mcp.json", "key": "TOKEN"}
        self.assertEqual(r._mcp_literal(sub, Tree({".mcp.json": '{"env":{"TOKEN":"abc123"}}'})), r.OPEN)
        self.assertEqual(r._mcp_literal(sub, Tree({".mcp.json": '{"env":{"TOKEN":"${TOKEN}"}}'})), r.RESOLVED)
        self.assertEqual(r._mcp_literal(sub, Tree({".mcp.json": "{}"})), r.RESOLVED)

    def test_a_path_that_stopped_being_a_symlink(self):
        self.assertEqual(r._symlink({"file": "l"}, Tree({"l": ""}, links=["l"])), r.OPEN)
        self.assertEqual(r._symlink({"file": "l"}, Tree({"l": "real file"})), r.RESOLVED)


class Weaker(unittest.TestCase):
    def test_fewer_markers_than_before(self):
        self.assertEqual(r._debt_marker({"file": "a.py", "markers": 3}, Tree({"a.py": "# TODO one\n"})), r.RESOLVED)
        self.assertEqual(r._debt_marker({"file": "a.py", "markers": 1}, Tree({"a.py": "# TODO one\n"})), r.OPEN)

    def test_a_surviving_function_is_unknown_not_open(self):
        """Whether a function that is still there got simpler needs the metrics, not the tree."""
        self.assertEqual(r._named_function({"file": "a.py", "function": "big"}, Tree({"a.py": "def small(): 0"})), r.RESOLVED)
        self.assertEqual(r._named_function({"file": "a.py", "function": "big"}, Tree({"a.py": "def big(): 0"})), r.UNKNOWN)
        self.assertEqual(r._named_function({"file": "a.py", "function": "(anonymous)"}, Tree({"a.py": "x"})), r.UNKNOWN)

    def test_instructions_touched_after_the_cut_off(self):
        sub = {"file": "AGENTS.md"}
        self.assertEqual(r._instructions_drift(sub, Tree({}, days={"AGENTS.md": "2025-06-01"})), r.RESOLVED)
        self.assertEqual(r._instructions_drift(sub, Tree({}, days={"AGENTS.md": "2024-06-01"})), r.OPEN)


class Scoring(unittest.TestCase):
    def findings(self):
        return [{"rule": {"id": "trojan_source"},
                 "evidence": {"bidi": [{"file": "a.s", "line": 2, "char": "U+202E"}],
                              "mixed_script": [{"file": "b.go", "line": 9, "token": "x18І"}]}},
                {"rule": {"id": "unpinned_actions"}, "evidence": {"unpinned": [{"file": WF, "uses": "actions/checkout@v4"}]}},
                {"rule": {"id": "repo_health"}, "evidence": {"metric": "Blobs: Maximum size"}}]

    def test_one_rule_can_feed_two_predicates(self):
        after = Tree({"a.s": "clean", "b.go": "clean", WF: "    - uses: actions/checkout@v4\n"})
        scored = r.score(self.findings(), after)
        self.assertEqual(dict(scored["trojan_source"]), {r.RESOLVED: 1})
        self.assertEqual(dict(scored["trojan_source_mixed"]), {r.RESOLVED: 1})
        self.assertEqual(dict(scored["unpinned_actions"]), {r.OPEN: 1})

    def test_a_rule_with_no_predicate_is_not_scored(self):
        scored = r.score(self.findings(), Tree({}))
        self.assertNotIn("repo_health", scored)
        self.assertIn("repo_health", r.NOT_OBSERVABLE)

    def test_the_rate_counts_a_vanished_file_only_where_that_is_the_fix(self):
        from collections import Counter
        counts = Counter({r.RESOLVED: 3, r.OPEN: 1, r.GONE: 2})
        self.assertAlmostEqual(r.acted_on(counts, True), 5 / 6)
        self.assertAlmostEqual(r.acted_on(counts, False), 3 / 4)
        self.assertIsNone(r.acted_on(Counter({r.UNKNOWN: 4}), True))

    def test_every_table_entry_has_a_verdict_on_vanishing(self):
        for name, (_, _, gone_is_fix) in r.RULES.items():
            self.assertIsInstance(gone_is_fix, bool, name)

    def test_no_rule_is_in_two_lists(self):
        names = set(r.RULES) | set(r.NOT_OBSERVABLE) | set(r.NO_SUBJECTS)
        self.assertEqual(len(names), len(r.RULES) + len(r.NOT_OBSERVABLE) + len(r.NO_SUBJECTS))

    def test_every_mechanical_rule_is_one_that_can_be_scored(self):
        self.assertFalse(r.MECHANICAL - set(r.RULES))

    def test_the_table_separates_the_two_bands(self):
        from collections import Counter
        scored = {"unpinned_actions": Counter({r.RESOLVED: 1}), "brain_methods": Counter({r.OPEN: 1})}
        out = r.table(scored)
        self.assertIn("| unpinned_actions | mechanical |", out)
        self.assertIn("| brain_methods | structural |", out)
        self.assertIn("mechanical: 1 of 1 subjects acted on.", out)
        self.assertIn("structural: 0 of 1 subjects acted on.", out)

    def test_a_share_over_few_subjects_is_printed_as_the_fraction_it_is(self):
        """1 of 1 is not 100%: curl's brain_methods row read 100% off a single judged subject."""
        from collections import Counter
        out = r.table({"brain_methods": Counter({r.RESOLVED: 1, r.UNKNOWN: 8, r.GONE: 1})})
        self.assertIn("| 1 of 1 |", out)
        self.assertNotIn("100%", out.split("\n\n")[0], "not as a percentage in the row")

    def test_every_subject_is_accounted_for_in_a_column(self):
        """The denominator is the point: a share over two judged subjects is not a share over two hundred."""
        from collections import Counter
        counts = Counter({r.RESOLVED: 2, r.OPEN: 1, r.GONE: 1, r.UNKNOWN: 3, r.ABSENT: 4})
        row = [line for line in r.table({"committed_binaries": counts}).split("\n") if "committed_binaries" in line][0]
        self.assertEqual(row.count("|"), 10)
        self.assertIn("| 11 | 2 | 1 | 1 | 3 | 4 |", row, "subjects, then each outcome")

    def test_the_band_pools_subjects_rather_than_averaging_rules(self):
        """Averaging 90% over ten subjects with 0% over one gave curl's misleading 45%."""
        from collections import Counter
        scored = {"unpinned_actions": Counter({r.RESOLVED: 9, r.OPEN: 1}), "lockfile_drift": Counter({r.OPEN: 1})}
        self.assertIn("mechanical: 9 of 11 subjects acted on, 82%.", r.table(scored))

    def test_a_subject_the_cutoff_tree_did_not_hold_is_not_an_act(self):
        """curl's specimen values named paths deleted years before the cut-off; absent then is not fixed now."""
        from collections import Counter
        class Cut(Tree):
            at_cutoff = {"live.yml"}
        findings = [{"rule": {"id": "unpinned_actions"},
                     "evidence": {"unpinned": [{"file": "live.yml", "uses": "actions/checkout@v4"},
                                               {"file": "deleted-in-2019.yml", "uses": "actions/checkout@v4"}]}}]
        tree = Cut({"live.yml": "uses: actions/checkout@v4\n"})   # still there, still by tag
        counts = r.score(findings, tree)["unpinned_actions"]
        self.assertEqual(counts[r.ABSENT], 1)
        self.assertEqual(sum(counts.values()), 2)
        self.assertEqual(r.judged(counts, False), 1, "the absent subject is out of the denominator")


class Window(unittest.TestCase):
    """A finding the history has not had the horizon to answer is not evidence that nobody acted."""

    def test_months_after_clamps_the_day(self):
        self.assertEqual(r.months_after("2025-01-31", 1), "2025-02-28")
        self.assertEqual(r.months_after("2025-01-15", 6), "2025-07-15")
        self.assertEqual(r.months_after("2025-08-15", 6), "2026-02-15")
        self.assertEqual(r.months_after("2024-01-31", 1), "2024-02-29")

    def test_months_after_crosses_december(self):
        self.assertEqual(r.months_after("2025-12-01", 1), "2026-01-01")
        self.assertEqual(r.months_after("2025-11-30", 13), "2026-12-30")


if __name__ == "__main__":
    unittest.main()

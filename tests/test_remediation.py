"""The remediation predicates, against a stub tree. No repository is cloned and no git runs."""
import unittest

from gitmole.measure import remediation as r

WF = ".github/workflows/ci.yml"


class Tree:
    """Stands in for remediation.After: a dict of the tree at the far end of the window, the window's
    renames, and the cut-off tree's text where a test needs it."""

    def __init__(self, files, days=None, links=(), cutoff="2025-01-01", moves=None, before=None):
        self.files, self.days, self.links, self.cutoff = files, days or {}, set(links), cutoff
        self.moves, self.before = moves or {}, before or {}

    def before_text(self, path):
        return self.before.get(path)

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

    def test_the_denominator_counts_a_vanished_file_only_where_that_is_the_fix(self):
        from collections import Counter
        counts = Counter({r.RESOLVED: 3, r.OPEN: 1, r.GONE: 2, r.UNKNOWN: 4})
        self.assertEqual(r.judged(counts, True), 6)
        self.assertEqual(r.judged(counts, False), 4)
        self.assertEqual(r.judged(Counter({r.UNKNOWN: 4}), True), 0)

    def test_every_table_entry_has_a_verdict_on_vanishing(self):
        for name, (_, _, gone_is_fix) in r.RULES.items():
            self.assertIsInstance(gone_is_fix, bool, name)

    def test_no_rule_is_in_two_lists(self):
        lists = (r.RULES, r.NOT_OBSERVABLE, r.NO_SUBJECTS, r.NO_PREDICATE)
        names = set().union(*lists)
        self.assertEqual(len(names), sum(len(x) for x in lists))

    def test_every_rule_the_findings_emit_is_scored_or_listed(self):
        """A rule in none of the tables fires and vanishes from the report without a line."""
        import inspect
        import re
        from gitmole import findings
        emitted = set(re.findall(r'"id": "([a-z_]+)"', inspect.getsource(findings)))
        self.assertIn("unpinned_actions", emitted, "the pattern still finds the ids")
        known = set(r.RULES) | set(r.NOT_OBSERVABLE) | set(r.NO_SUBJECTS) | set(r.NO_PREDICATE)
        self.assertEqual(emitted - known, set())

    def test_a_fired_rule_outside_the_table_is_printed_with_its_reason(self):
        text = r.unscored({"reverts", "commented_out_code", "stale_files", "unpinned_actions"})
        self.assertIn(f"- **reverts** — {r.NOT_OBSERVABLE['reverts']}\n", text)
        self.assertIn("- **commented_out_code** — ", text)
        self.assertIn("- **stale_files** — ", text)
        self.assertNotIn("unpinned_actions", text, "a scored rule is in the table, not in these lists")
        self.assertEqual(r.unscored({"unpinned_actions"}), "")

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
        counts = Counter({r.RESOLVED: 2, r.OPEN: 1, r.MOVED: 5, r.GONE: 1, r.UNKNOWN: 3, r.ABSENT: 4})
        row = [line for line in r.table({"committed_binaries": counts}).split("\n") if "committed_binaries" in line][0]
        self.assertEqual(row.count("|"), 11)
        self.assertIn("| 16 | 2 | 1 | 5 | 1 | 3 | 4 | 33% |", row, "subjects, then each outcome; moved is judged, never fixed")

    def test_the_band_pools_subjects_rather_than_averaging_rules(self):
        """Averaging 90% over ten subjects with 0% over one gave curl's misleading 45%."""
        from collections import Counter
        scored = {"unpinned_actions": Counter({r.RESOLVED: 9, r.OPEN: 1}), "lockfile_drift": Counter({r.OPEN: 1})}
        self.assertIn("mechanical: 9 of 11 subjects acted on, 82%.", r.table(scored))

    def test_a_subject_the_cutoff_tree_did_not_hold_is_not_an_act(self):
        """curl's specimen values named paths deleted years before the cut-off; absent then is not fixed now."""
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


class Moves(unittest.TestCase):
    """A `git mv` is not the advice taken: the subject is followed to its new path and judged there."""

    def test_an_unreferenced_file_moved_is_not_fixed(self):
        findings = [{"rule": {"id": "unreferenced_files"}, "evidence": {"files": ["old/dead.c", "gone.c"]}}]
        tree = Tree({"new/dead.c": "int x;"}, moves={"old/dead.c": "new/dead.c"})
        counts = r.score(findings, tree)["unreferenced_files"]
        self.assertEqual(counts[r.MOVED], 1)
        self.assertEqual(counts[r.RESOLVED], 1, "the file that really left the tree is still the fix")
        self.assertEqual(r.judged(counts, True), 2)

    def test_a_moved_file_whose_codepoint_went_is_resolved_there(self):
        sub = {"file": "a.s", "char": "U+202E"}
        still = Tree({"b.s": "x\u202ey"}, moves={"a.s": "b.s"})
        clean = Tree({"b.s": "xy"}, moves={"a.s": "b.s"})
        self.assertEqual(r.outcome(sub, r._bidi_char, still), r.MOVED)
        self.assertEqual(r.outcome(sub, r._bidi_char, clean), r.RESOLVED)

    def test_a_path_still_in_the_tree_is_not_followed(self):
        """A copy at a new path leaves the old one where it was; only a missing path is followed."""
        tree = Tree({"a.s": "x\u202ey", "b.s": "xy"}, moves={"a.s": "b.s"})
        self.assertEqual(r.outcome({"file": "a.s", "char": "U+202E"}, r._bidi_char, tree), r.OPEN)

    def test_a_moved_manifest_is_followed_with_its_lockfile(self):
        sub = {"manifest": "a/package.json", "package": "lodash"}
        tree = Tree({"b/package.json": '{"dependencies":{"lodash":"^4"}}'}, moves={"a/package.json": "b/package.json"})
        self.assertEqual(r.outcome(sub, r._unused_dependency, tree), r.MOVED)

    def test_a_renamed_function_is_moved_not_resolved(self):
        before = "int x;\nstatic int big(int a, int b)\n{\n    if (a) return b;\n    return a + b;\n}\n"
        after = "int x;\nstatic int huge(int a, int b)\n{\n    if (a) return b;\n    return a + b;\n}\n"
        sub = {"file": "a.c", "function": "big", "start": 2}
        self.assertEqual(r._named_function(sub, Tree({"a.c": after}, before={"a.c": before})), r.MOVED)

    def test_a_brace_on_its_own_line_opens_the_body(self):
        """C's layout: a body cut at the `{` is only the parameters, and any function sharing them would match."""
        before = "static int big(int a,\n               int b)\n{\n  if(a)\n    return b;\n  return a + b;\n}\n"
        same = "static int huge(int a,\n               int b)\n{\n  if(a)\n    return b;\n  return a + b;\n}\n"
        other = "static int other(int a,\n               int b)\n{\n  return a * b * 2;\n}\n"
        sub = {"file": "a.c", "function": "big", "start": 1}
        self.assertEqual(r._named_function(sub, Tree({"a.c": same}, before={"a.c": before})), r.MOVED)
        self.assertEqual(r._named_function(sub, Tree({"a.c": other}, before={"a.c": before})), r.RESOLVED)

    def test_a_function_split_away_is_still_resolved(self):
        before = "def big(a, b):\n    x = a\n    y = b\n    z = a * b\n    return x + y + z\n"
        after = "def part(a, b):\n    return a + b\n\ndef other(a, b):\n    return a * b\n"
        sub = {"file": "a.py", "function": "big", "start": 1}
        self.assertEqual(r._named_function(sub, Tree({"a.py": after}, before={"a.py": before})), r.RESOLVED)

    def test_without_the_cutoff_text_the_old_reading_stands(self):
        sub = {"file": "a.py", "function": "big", "start": 1}
        self.assertEqual(r._named_function(sub, Tree({"a.py": "def huge(): 0"})), r.RESOLVED)

    def test_a_function_in_a_moved_file_is_read_there(self):
        """Its file moved and the name survived: a survivor, so can't-say, and out of the share as survivors are."""
        findings = [{"rule": {"id": "brain_methods"}, "evidence": {"functions": [{"file": "a.py", "function": "big", "start": 1}]}}]
        counts = r.score(findings, Tree({"b.py": "def big(): 0"}, moves={"a.py": "b.py"}))["brain_methods"]
        self.assertEqual(counts[r.MOVED], 1)
        self.assertFalse(r.moved_is_judged("brain_methods"))
        self.assertTrue(r.moved_is_judged("unreferenced_files"))
        self.assertEqual(r.judged(counts, False, r.moved_is_judged("brain_methods")), 0)


class Renames(unittest.TestCase):
    """The rename map from git itself, with the limit pinned on the command line."""

    def test_git_names_the_move(self):
        import os
        import subprocess
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            env = dict(os.environ, GIT_CONFIG_GLOBAL="/dev/null", GIT_CONFIG_SYSTEM="/dev/null",
                       GIT_AUTHOR_NAME="A", GIT_AUTHOR_EMAIL="a@x", GIT_COMMITTER_NAME="A", GIT_COMMITTER_EMAIL="a@x")

            def git(*args):
                return subprocess.run(["git", *args], cwd=d, check=True, capture_output=True, env=env, text=True).stdout.strip()
            git("init", "-q")
            git("config", "diff.renameLimit", "1")      # a user's config: must not change the answer
            git("config", "diff.renames", "false")
            body = "".join(f"line {i}\n" for i in range(40))
            for name in ("keep.c", "move me.c", "drop.c", "other.c"):
                with open(os.path.join(d, name), "w") as fh:
                    fh.write(name + "\n" + body)
            git("add", "keep.c", "move me.c", "drop.c", "other.c")
            git("commit", "-q", "-m", "a")
            first = git("rev-parse", "HEAD")
            os.makedirs(os.path.join(d, "sub"))
            git("mv", "move me.c", "sub/moved.c")
            git("mv", "other.c", "sub/other2.c")
            with open(os.path.join(d, "sub", "moved.c"), "a") as fh:
                fh.write("an edit\n")
            git("rm", "-q", "drop.c")
            git("add", "sub/moved.c")
            git("commit", "-q", "-m", "b")
            moves, skipped = r.renames(d, first, git("rev-parse", "HEAD"))
            self.assertEqual(moves, {"move me.c": "sub/moved.c", "other.c": "sub/other2.c"})
            self.assertFalse(skipped)


class Repeats(unittest.TestCase):
    """Across several cut-offs a subject is counted once, where it was first flagged."""

    def test_a_subject_flagged_twice_is_counted_at_the_first(self):
        seen = set()
        first = [{"rule": {"id": "unpinned_actions"}, "evidence": {"unpinned": [{"file": WF, "uses": "actions/checkout@v4", "line": 3}]}}]
        later = [{"rule": {"id": "unpinned_actions"}, "evidence": {"unpinned": [{"file": WF, "uses": "actions/checkout@v4", "line": 9},
                                                                              {"file": WF, "uses": "actions/cache@v4", "line": 12}]}}]
        tree = Tree({WF: "    - uses: actions/checkout@v4\n    - uses: actions/cache@v4\n"})
        a = r.score(first, tree, seen)["unpinned_actions"]
        b = r.score(later, tree, seen)["unpinned_actions"]
        self.assertEqual(a[r.OPEN], 1)
        self.assertEqual((b[r.OPEN], b[r.REPEAT]), (1, 1), "the line moved; the subject did not")
        both = a + b
        row = [line for line in r.table({"unpinned_actions": both}).split("\n") if "| unpinned_actions" in line][0]
        self.assertIn("| 2 | 0 | 2 |", row, "a repeat is not a subject")

    def test_one_export_counts_every_subject(self):
        findings = [{"rule": {"id": "unpinned_actions"}, "evidence": {"unpinned": [{"file": WF, "uses": "a/b@v1"}, {"file": WF, "uses": "a/b@v1"}]}}]
        self.assertEqual(r.score(findings, Tree({WF: "uses: a/b@v1"}))["unpinned_actions"][r.OPEN], 2)


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

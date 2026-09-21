import unittest

from gitmole import compare


def finding(rid, severity, title, **evidence):
    return {"severity": severity, "title": title, "detail": title, "advice": "", "rule": {"id": rid}, "evidence": evidence}


class Key(unittest.TestCase):
    def test_rule_id_plus_the_row_field_for_rules_that_emit_several(self):
        self.assertEqual(compare.key(finding("bug_magnets", "warning", "Bug magnets")), ("bug_magnets",))
        self.assertEqual(compare.key(finding("repo_health", "warning", "Repo health", metric="Blobs: Maximum size")), ("repo_health", "Blobs: Maximum size"))
        self.assertEqual(compare.key(finding("placeholder_identity", "warning", "Unconfigured", email="root@localhost")), ("placeholder_identity", "root@localhost"))


class Compare(unittest.TestCase):
    def setUp(self):
        self.before = {"meta": {"name": "r", "last_date": "2026-09-10", "since": None, "file_types": None,
                                "run": {"commit": "540ee5b560cc6e775e11317048a13cc7e355bf91", "options": {"ignore": [], "ignore_data": False, "deep": False}}},
                       "findings": [finding("bug_magnets", "warning", "Bug magnets"), finding("reverts", "info", "Reverts"),
                                    finding("repo_health", "warning", "Repo health", metric="Blobs: Maximum size"),
                                    finding("repo_health", "info", "Repo health", metric="Trees: Maximum entries")],
                       "watch": [{"file": "a.py"}, {"file": "b.py"}]}
        self.after_findings = [finding("bug_magnets", "info", "Bug magnets"), finding("credential_files", "warning", "Credential-shaped files tracked"),
                               finding("repo_health", "warning", "Repo health", metric="Blobs: Maximum size")]
        self.after = {"meta": {"name": "r", "last_date": "2026-09-18", "file_types": None, "run": {"commit": "abc", "options": {"ignore": [], "ignore_data": True, "deep": False}}},
                      "size": {"files": {"a.py": {"code": 10, "complexity": 1}, "c.py": {"code": 900, "complexity": 1}}},
                      "revisions": [{"entity": "a.py", "n-revs": 5}, {"entity": "c.py", "n-revs": 50}], "functions": [], "plumbing": []}

    def test_buckets_findings_and_watch_list_moves(self):
        out = compare.compare(self.before, self.after, self.after_findings)
        self.assertEqual([f["title"] for f in out["new"]], ["Credential-shaped files tracked"])
        self.assertEqual([(f["title"], f["evidence"].get("metric")) for f in out["resolved"]], [("Repo health", "Trees: Maximum entries"), ("Reverts", None)])
        self.assertEqual([(f["title"], f["severity"], f["was"]) for f in out["persisting"]],
                         [("Repo health", "warning", "warning"), ("Bug magnets", "info", "warning")], "the after copy, with the severity it had")
        self.assertEqual((out["watch_entered"], out["watch_left"]), (["c.py"], ["b.py"]))
        self.assertEqual(out["tally"], {"before": {"critical": 0, "warning": 2, "info": 2}, "after": {"critical": 0, "warning": 2, "info": 1}})
        self.assertEqual(out["before"], {"commit": "540ee5b560cc6e775e11317048a13cc7e355bf91", "date": "2026-09-10", "options_differ": ["ignore_data"],
                                         "database": None, "gitmole": None, "tools": {}})

    def test_a_persisting_finding_says_which_counts_moved(self):
        self.before["findings"].append(finding("secrets_in_source", "critical", "16 secret(s) in history", values=16, places=40, files=["a.py"]))
        self.before["findings"].append(finding("stale_files", "info", "A large share of files is untouched", files=3217, stale=2482))
        after = self.after_findings + [finding("secrets_in_source", "critical", "1 secret(s) in history", values=1, places=40, files=["b.py"]),
                                       finding("stale_files", "info", "A large share of files is untouched", files=3400, stale=2482, partial=True)]
        by = {f["rule"]["id"]: f["changed"] for f in compare.compare(self.before, self.after, after)["persisting"]}
        self.assertEqual(by["secrets_in_source"], [["values", 16, 1]], "places did not move; the file list is a sample, not a count")
        self.assertEqual(by["stale_files"], [["files", 3217, 3400]], "the note's base changed under it; a flag is not a count")
        self.assertEqual(by["bug_magnets"], [], "no evidence either side")

    def test_compare_skips_watch_rows_without_a_file(self):
        self.before["watch"] = [{"file": "a.py"}, {"note": "no file field"}, {"file": "b.py"}]
        out = compare.compare(self.before, self.after, self.after_findings)
        self.assertEqual((out["watch_entered"], out["watch_left"]), (["c.py"], ["b.py"]))

    def test_an_export_without_a_manifest_compares_findings_only(self):
        self.before["meta"].pop("run")
        out = compare.compare(self.before, self.after, self.after_findings)
        self.assertEqual(out["before"], {"commit": None, "date": "2026-09-10", "options_differ": [], "database": None, "gitmole": None, "tools": {}})

    def test_two_exports_from_different_gitmole_versions_say_so(self):
        """Rules change in most releases, so a finding can be new or resolved here with nothing about the
        repository having changed. The same caveat the OSV database already gets."""
        self.assertIsNone(compare.compare(self.before, self.after, self.after_findings)["before"]["gitmole"],
                          "neither export names a version, so there is nothing to compare")
        self.before["meta"]["run"]["gitmole"] = "0.30.0"
        self.after["meta"]["run"]["gitmole"] = "0.33.0"
        self.assertEqual(compare.compare(self.before, self.after, self.after_findings)["before"]["gitmole"],
                         {"before": "0.30.0", "after": "0.33.0"})
        self.after["meta"]["run"]["gitmole"] = "0.30.0"
        self.assertIsNone(compare.compare(self.before, self.after, self.after_findings)["before"]["gitmole"],
                          "one version, one rule set: nothing to warn about")
        self.before["meta"]["run"].pop("gitmole")
        self.assertIsNone(compare.compare(self.before, self.after, self.after_findings)["before"]["gitmole"],
                          "an export from before the run manifest cannot be compared this way")

    def test_a_tool_that_moved_between_the_exports_is_named(self):
        """scc counts differently, a lizard release parses a language better: the instrument moved, not
        the repository. Both manifests already record every tool's version."""
        self.before["meta"]["run"]["tools"] = {"scc": "4.1.0", "lizard": "1.23.0", "git": "2.55.0"}
        self.after["meta"]["run"]["tools"] = {"scc": "4.1.0", "lizard": "1.24.0", "jscpd": "5.3.0"}
        self.assertEqual(compare.compare(self.before, self.after, self.after_findings)["before"]["tools"],
                         {"lizard": {"before": "1.23.0", "after": "1.24.0"}})
        self.after["meta"]["run"]["tools"]["lizard"] = "1.23.0"
        self.assertEqual(compare.compare(self.before, self.after, self.after_findings)["before"]["tools"], {},
                         "a tool only one export names is not a change anyone can check")

    def test_is_export(self):
        self.assertTrue(compare.is_export(self.before))
        self.assertFalse(compare.is_export({"meta": {}}))
        self.assertFalse(compare.is_export([]))

    def test_is_export_rejects_a_watch_list_that_is_not_a_list_of_rows(self):
        self.assertFalse(compare.is_export({**self.before, "watch": {}}), "watch must be a list")
        self.assertFalse(compare.is_export({**self.before, "watch": ["a.py"]}), "every row must be a dict")

    def test_is_export_rejects_findings_from_before_0_8_0_without_rule_ids(self):
        before = {**self.before, "findings": [{"severity": "warning", "title": "Bug magnets", "detail": "", "advice": ""}]}
        self.assertFalse(compare.is_export(before), "a finding without a rule id crashes key()/_tally() instead of comparing; refuse it up front")

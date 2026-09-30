import hashlib
import json
import unittest

from gitmole import sarif


def finding(rule, severity="warning", title="T", detail="D", advice="A", evidence=None, **rule_extra):
    return {"severity": severity, "title": title, "detail": detail, "advice": advice, "rule": {"id": rule, **rule_extra}, "evidence": evidence or {}}


def report(**over):
    base = {"meta": {"name": "demo", "run": {"commit": "abc1234def", "gitmole": "0.14.0"}},
            "size": {"files": {"src/a.py": {"code": 10, "complexity": 1}, "package-lock.json": {"code": 1, "complexity": 0}}},
            "secrets": []}
    base.update(over)
    return base


class Document(unittest.TestCase):
    def test_the_envelope_github_and_gitlab_read(self):
        doc = sarif.build(report(), [finding("bug_magnets", evidence={"files": [{"file": "src/a.py", "recent_fixes": 5}]})])
        self.assertEqual(doc["version"], "2.1.0")
        self.assertEqual(doc["$schema"], "https://json.schemastore.org/sarif-2.1.0.json")
        driver = doc["runs"][0]["tool"]["driver"]
        self.assertEqual((driver["name"], driver["version"], driver["informationUri"]), ("gitmole", "0.14.0", "https://github.com/antvinni/gitmole"))
        about = "gitmole's bug_magnets rule. https://github.com/antvinni/gitmole"
        self.assertEqual(driver["rules"], [{"id": "bug_magnets", "name": "BugMagnets", "shortDescription": {"text": "T"},
                                            "fullDescription": {"text": about}, "help": {"text": about, "markdown": about},
                                            "defaultConfiguration": {"level": "warning"},
                                            "properties": {"security-severity": "5.0", "tags": ["gitmole"]}}])
        [result] = doc["runs"][0]["results"]
        self.assertEqual(result["ruleId"], "bug_magnets")
        self.assertEqual(result["level"], "warning")
        self.assertEqual(result["message"]["text"], "D")
        self.assertEqual(result["locations"], [{"physicalLocation": {"artifactLocation": {"uri": "src/a.py", "uriBaseId": "%SRCROOT%"}}}])
        self.assertEqual(result["properties"]["security-severity"], "5.0")
        self.assertEqual(result["partialFingerprints"], {"gitmole/v1": hashlib.sha256(b"bug_magnets\0src/a.py\0\0").hexdigest()},
                         "rule, path, commit and line: stable across runs, nothing random in it")
        self.assertEqual(doc["runs"][0]["versionControlProvenance"], [{"repositoryUri": "https://github.com/antvinni/gitmole", "revisionId": "abc1234def"}]
                         if False else [{"revisionId": "abc1234def"}])

    def test_a_rule_describes_itself_and_never_this_runs_paths_or_commits(self):
        """A reportingDescriptor is the rule's documentation. curl's head-scoped SARIF had secrets_aside's
        fullDescription naming docs/MANUAL and five commit hashes - paths and commits the scope had
        dropped from every one of that rule's results."""
        detail = "37 distinct values in 82 places: generic-password in docs/MANUAL (2f69240). Confirm them."
        f = finding("bug_magnets", detail=detail, advice="Delete docs/MANUAL first.",
                    evidence={"files": ["src/a.py"]}, months=12, share=0.3, ref="Bird et al., FSE 2011",
                    osps=["OSPS-BR-07.01"])
        [rule] = sarif.build(report(), [f])["runs"][0]["tool"]["driver"]["rules"]
        self.assertEqual(rule["fullDescription"]["text"],
                         "gitmole's bug_magnets rule. Settings: months 12, share 0.3. Rests on Bird et al., FSE 2011. "
                         "Evidence for OSPS-BR-07.01. https://github.com/antvinni/gitmole")
        self.assertEqual(rule["help"]["text"], rule["fullDescription"]["text"])
        for leak in ("docs/MANUAL", "2f69240", "37 distinct"):
            self.assertNotIn(leak, json.dumps(rule), "the rule says what it checks, not what it found here")
        [result] = sarif.build(report(), [f])["runs"][0]["results"]
        self.assertEqual(result["message"]["text"], detail, "the occurrence text is the result's, and is still there")

    def test_a_finding_whose_every_place_the_scope_dropped_keeps_one_result_without_a_location(self):
        """--fail-on stops on the finding whatever the scope, so the document has it too: devlake exited 3 on a
        critical whose secrets were all in files deleted years ago, and its SARIF had no error-level result."""
        kept = finding("bug_magnets", evidence={"files": [{"file": "src/a.py"}]})
        dropped = finding("brain_methods", evidence={"functions": [{"file": "gone/old.py", "start": 1, "function": "f"}]})
        head = sarif.build(report(), [kept, dropped])
        self.assertEqual([r["id"] for r in head["runs"][0]["tool"]["driver"]["rules"]], ["bug_magnets", "brain_methods"])
        gone = next(r for r in head["runs"][0]["results"] if r["ruleId"] == "brain_methods")
        self.assertNotIn("locations", gone, "nothing at HEAD is where it is")
        self.assertFalse(gone["properties"]["inTree"])
        self.assertIn("--sarif-scope history", gone["message"]["text"])
        self.assertEqual([r["ruleId"] for r in head["runs"][0]["results"]], ["bug_magnets", "brain_methods"])
        history = sarif.build(report(), [kept, dropped], scope="history")
        self.assertEqual(sorted(r["id"] for r in history["runs"][0]["tool"]["driver"]["rules"]), ["brain_methods", "bug_magnets"])

    def test_levels_and_severities_follow_the_finding(self):
        doc = sarif.build(report(), [finding("dormant", "warning", evidence={}), finding("credential_files", "critical", evidence={"files": ["src/a.py"]}),
                                     finding("brain_methods", "info", evidence={"functions": [{"file": "src/a.py", "start": 1, "function": "f"}]})], scope="history")
        by = {r["ruleId"]: r for r in doc["runs"][0]["results"]}
        self.assertEqual((by["credential_files"]["level"], by["credential_files"]["properties"]["security-severity"]), ("error", "9.0"))
        self.assertEqual((by["brain_methods"]["level"], by["brain_methods"]["properties"]["security-severity"]), ("note", "2.0"))
        self.assertEqual(by["brain_methods"]["locations"][0]["physicalLocation"]["region"], {"startLine": 1})
        self.assertNotIn("locations", by["dormant"], "a repository-wide finding has no file to point at")

    def test_every_finding_the_gate_stops_on_has_an_error_result_under_head_scope(self):
        rows = [{"rule": "github-pat", "file": "old/gone.js", "commit": "d2d2d2d", "line": 3, "fingerprint": "y", "value": "h2", "placeholder": False}]
        found = [finding("secrets_in_source", "critical", evidence={"files": ["old/gone.js"]})]
        results = sarif.build(report(secrets=rows), found)["runs"][0]["results"]
        self.assertEqual([(r["ruleId"], r["level"]) for r in results], [("secrets_in_source", "error")])
        self.assertNotIn("locations", results[0])

    def test_workflow_and_manifest_findings_point_at_their_files(self):
        """unpinned_actions and lockfile_drift name files, under keys of their own; without a location code scanning
        never showed them. One result per file, at line 1, as neither rule records a line."""
        found = [finding("unpinned_actions", evidence={"count": 3, "unpinned": [
                     {"file": ".github/workflows/ci.yml", "uses": "actions/checkout@v4"},
                     {"file": ".github/workflows/ci.yml", "uses": "actions/setup-node@v4"},
                     {"file": ".github/workflows/gone.yml", "uses": "x/y@main"}]}),
                 finding("lockfile_drift", evidence={"count": 1, "drift": [
                     {"manifest": "web/package.json", "lockfile": "web/package-lock.json", "manifest_date": "2026-01-02", "lockfile_date": "2025-01-01"}]})]
        tree = frozenset({"src/a.py", ".github/workflows/ci.yml", "web/package.json", "web/package-lock.json"})
        results = sarif.build(report(tree=tree), found)["runs"][0]["results"]
        places = [(r["ruleId"], r["locations"][0]["physicalLocation"]["artifactLocation"]["uri"], r["locations"][0]["physicalLocation"]["region"])
                  for r in results]
        self.assertEqual(places, [("unpinned_actions", ".github/workflows/ci.yml", {"startLine": 1}),
                                  ("lockfile_drift", "web/package.json", {"startLine": 1})],
                         "the workflow no longer in the tree is left out under the head scope")
        history = sarif.build(report(tree=tree), found, scope="history")["runs"][0]["results"]
        self.assertEqual(len([r for r in history if r["ruleId"] == "unpinned_actions"]), 2)

    def test_a_tracked_credential_file_is_in_the_tree_though_scc_does_not_count_it(self):
        """prometheus: web/ui/react-app/.env is in git's index (meta.credential_files) and in no scc language."""
        r = report(meta={"name": "demo", "credential_files": ["web/.env"]})
        results = sarif.build(r, [finding("credential_files", evidence={"files": ["web/.env"]})])["runs"][0]["results"]
        self.assertEqual(results[0]["locations"][0]["physicalLocation"]["artifactLocation"]["uri"], "web/.env")

    def test_head_scope_drops_what_is_not_in_the_tree_and_history_keeps_it_with_the_commit(self):
        found = [finding("sweeping_commits", "info", evidence={"commits": [{"hash": "fmt1", "files": 900}]}),
                 finding("bug_magnets", evidence={"files": [{"file": "gone.py"}, {"file": "src/a.py"}]})]
        head = sarif.build(report(), found, scope="head")
        self.assertEqual([(r["ruleId"], r["locations"][0]["physicalLocation"]["artifactLocation"]["uri"]) for r in head["runs"][0]["results"] if "locations" in r],
                         [("bug_magnets", "src/a.py")], "the deleted file and the commit-level finding have no place at HEAD")
        self.assertEqual([r["ruleId"] for r in head["runs"][0]["results"] if "locations" not in r], ["sweeping_commits"],
                         "the commit-level finding keeps one result, with no location")
        history = sarif.build(report(), found, scope="history")
        by = {r["ruleId"]: r for r in history["runs"][0]["results"]}
        self.assertEqual(by["sweeping_commits"]["properties"]["commit"], "fmt1")
        self.assertEqual({r["locations"][0]["physicalLocation"]["artifactLocation"]["uri"] for r in history["runs"][0]["results"] if "locations" in r},
                         {"gone.py", "src/a.py"})

    def test_head_scope_judges_presence_by_the_listing_of_head(self):
        found = [finding("bug_magnets", evidence={"files": [{"file": ".env"}, {"file": "gone.py"}]})]
        head = sarif.build(report(tree=frozenset({"src/a.py", ".env"})), found, scope="head")
        self.assertEqual([r["locations"][0]["physicalLocation"]["artifactLocation"]["uri"] for r in head["runs"][0]["results"]], [".env"],
                         "a file scc has no language for is at HEAD all the same")

    def test_secrets_are_one_result_per_place_from_the_rows_with_a_stable_fingerprint(self):
        rows = [{"rule": "aws-access-token", "file": "src/a.py", "commit": "c1c1c1c", "line": 9, "fingerprint": "x", "value": "h1", "placeholder": False},
                {"rule": "aws-access-token", "file": "src/a.py", "commit": "c1c1c1c", "line": 9, "fingerprint": "x", "value": "h1", "placeholder": False},
                {"rule": "generic-api-key", "file": "old/gone.py", "commit": "d2d2d2d", "line": 3, "fingerprint": "y", "value": "h2", "placeholder": False},
                {"rule": "generic-api-key", "file": "src/a.py", "commit": "e3e3e3e", "line": 1, "fingerprint": "z", "value": "h3", "placeholder": True}]
        found = [finding("secrets_in_source", "critical", title="2 secret(s) in history", evidence={"files": ["src/a.py", "old/gone.py"]})]
        head = sarif.build(report(secrets=rows), found, scope="head")
        results = head["runs"][0]["results"]
        self.assertEqual(len(results), 1, "one place at HEAD; the duplicate row is one place, the placeholder is not a secret, the gone file is history")
        r = results[0]
        self.assertEqual(r["message"]["text"], "aws-access-token in src/a.py at commit c1c1c1c, line 9 of that commit's version")
        self.assertNotIn("region", r["locations"][0]["physicalLocation"], "the line is the commit's, not HEAD's")
        self.assertEqual(r["properties"]["commit"], "c1c1c1c")
        self.assertEqual(r["partialFingerprints"]["gitmole/v1"], hashlib.sha256(b"secrets_in_source\0src/a.py\0c1c1c1c\x009").hexdigest(),
                         "derived from non-secret data, so two runs agree although the value hashes never do")
        history = sarif.build(report(secrets=rows), found, scope="history")
        self.assertEqual(len(history["runs"][0]["results"]), 2)
        gone = next(x for x in history["runs"][0]["results"] if x["properties"]["commit"] == "d2d2d2d")
        self.assertEqual(gone["locations"][0]["physicalLocation"]["region"], {"startLine": 3})

    def test_head_scope_keeps_a_secret_only_where_heads_file_still_holds_the_value(self):
        """VoiceStudio: a key replaced in a file still in the tree was pinned to that file at HEAD, where it no longer is."""
        rows = [{"rule": "posthog", "file": "src/a.py", "commit": "c1c1c1c", "line": 57, "fingerprint": "x", "value": "h1", "placeholder": False,
                 "at_head": False},
                {"rule": "github-pat", "file": "src/a.py", "commit": "d2d2d2d", "line": 3, "fingerprint": "y", "value": "h2", "placeholder": False,
                 "at_head": True, "head_line": 12}]
        found = [finding("secrets_in_source", "critical", evidence={"files": ["src/a.py"]})]
        [r] = sarif.build(report(secrets=rows), found, scope="head")["runs"][0]["results"]
        self.assertEqual(r["properties"]["commit"], "d2d2d2d", "the replaced value is history only, though its file is in the tree")
        self.assertEqual(r["locations"][0]["physicalLocation"]["region"], {"startLine": 12}, "HEAD's line, where the value is now")
        self.assertEqual(r["message"]["text"], "github-pat in src/a.py at commit d2d2d2d, line 3 of that commit's version; at HEAD, line 12")
        [only] = sarif.build(report(secrets=rows[:1]), found, scope="head")["runs"][0]["results"]
        self.assertNotIn("locations", only, "a gated finding with nothing at HEAD keeps one result, without a location")
        self.assertEqual(only["level"], "error")
        self.assertEqual(len(sarif.build(report(secrets=rows), found, scope="history")["runs"][0]["results"]), 2)

    def test_a_declared_value_is_the_declared_findings_and_not_the_criticals(self):
        said = {"file": ".gitleaks.toml", "commit": "e3ed952", "how": "allowlist regex"}
        rows = [{"rule": "posthog-project-api-key", "file": "src/a.py", "commit": "c1c1c1c", "line": 9, "fingerprint": "x", "value": "h1", "placeholder": False,
                 "declared": said},
                {"rule": "generic-password", "file": "src/a.py", "commit": "d2d2d2d", "line": 3, "fingerprint": "y", "value": "h2", "placeholder": False}]
        found = [finding("secrets_in_source", "critical", evidence={"files": ["src/a.py"]}),
                 finding("secrets_declared", "info", evidence={"files": ["src/a.py"]})]
        results = sarif.build(report(secrets=rows), found, scope="history")["runs"][0]["results"]
        self.assertEqual([(r["ruleId"], r["properties"]["commit"]) for r in results], [("secrets_in_source", "d2d2d2d"), ("secrets_declared", "c1c1c1c")],
                         "one file, two values: each result under the finding that holds its value")

    def test_vulnerable_dependencies_are_one_result_per_package_with_the_advisory_score(self):
        found = [finding("vulnerable_dependencies", "critical", evidence={"packages": [
            {"name": "minimist", "version": "0.0.8", "source": "package-lock.json", "score": 9.8, "fixed": "1.2.6", "ids": ["GHSA-1"], "aliases": ["CVE-2021-1"], "malicious": False},
            {"name": "evil", "version": "1.0.0", "source": "package-lock.json", "score": None, "fixed": None, "ids": ["MAL-2026-1"], "aliases": [], "malicious": True}]})]
        results = sarif.build(report(), found)["runs"][0]["results"]
        self.assertEqual([r["properties"]["security-severity"] for r in results], ["9.8", "10.0"])
        self.assertEqual(results[0]["message"]["text"], "minimist 0.0.8 in package-lock.json: CVE-2021-1 (9.8), fixed in 1.2.6")
        self.assertEqual(results[1]["message"]["text"], "evil 1.0.0 in package-lock.json: MAL-2026-1, malicious, no fix; remove it")
        self.assertEqual(results[1]["partialFingerprints"]["gitmole/v1"], hashlib.sha256(b"vulnerable_dependencies\0package-lock.json\0\0\0evil@1.0.0").hexdigest())

    def test_every_vulnerable_row_is_a_result_not_only_the_ten_the_evidence_keeps(self):
        """hindsight: 34 rows, and the SARIF carried the finding's capped evidence, 10."""
        from gitmole import findings as fs
        rows = [{"name": f"p{i}", "version": "1", "ecosystem": "npm", "source": f"d{i}/package-lock.json", "ids": ["GHSA-1"], "aliases": [],
                 "score": 7.5, "severity": "high", "fixed": "2", "malicious": False} for i in range(14)]
        rows.append({"name": "mcp", "version": "1.0.0", "ecosystem": "PyPI", "source": "svc/requirements.txt", "ids": ["GHSA-2"], "aliases": [],
                     "score": 8.7, "severity": "high", "fixed": "1.9.4", "malicious": False, "requirement": ">=1.0.0", "pinned": False})
        rep = report(dependencies={"status": "scanned", "sources": [], "vulnerable": rows})
        found = fs.vulnerable_dependencies(rep)
        self.assertLess(sum(len(f["evidence"]["packages"]) for f in found), 15)
        results = [r for r in sarif.build(rep, found)["runs"][0]["results"] if r["ruleId"].startswith("vulnerable_dependencies")]
        self.assertEqual(len(results), 15)
        self.assertEqual(sorted(r["locations"][0]["physicalLocation"]["artifactLocation"]["uri"] for r in results)[-1], "svc/requirements.txt")
        self.assertIn("mcp>=1.0.0 in svc/requirements.txt admits a vulnerable version, its floor 1.0.0: GHSA-2 (8.7), fixed in 1.9.4",
                      [r["message"]["text"] for r in results])

    def test_the_document_is_json_and_deterministic(self):
        found = [finding("bug_magnets", evidence={"files": [{"file": "src/a.py"}]})]
        a, b = sarif.dumps(report(), found), sarif.dumps(report(), found)
        self.assertEqual(a, b)
        json.loads(a)


if __name__ == "__main__":
    unittest.main()

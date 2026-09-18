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
        self.assertEqual(driver["rules"], [{"id": "bug_magnets", "name": "BugMagnets", "shortDescription": {"text": "T"}, "fullDescription": {"text": "D"},
                                            "help": {"text": "A", "markdown": "A"}, "defaultConfiguration": {"level": "warning"},
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

    def test_levels_and_severities_follow_the_finding(self):
        doc = sarif.build(report(), [finding("dormant", "warning", evidence={}), finding("credential_files", "critical", evidence={"files": ["src/a.py"]}),
                                     finding("duplication", "info", evidence={"largest": [{"lines": 40, "places": [["src/a.py", 1, 40]]}]})], scope="history")
        by = {r["ruleId"]: r for r in doc["runs"][0]["results"]}
        self.assertEqual((by["credential_files"]["level"], by["credential_files"]["properties"]["security-severity"]), ("error", "9.0"))
        self.assertEqual((by["duplication"]["level"], by["duplication"]["properties"]["security-severity"]), ("note", "2.0"))
        self.assertEqual(by["duplication"]["locations"][0]["physicalLocation"]["region"], {"startLine": 1})
        self.assertNotIn("locations", by["dormant"], "a repository-wide finding has no file to point at")

    def test_head_scope_drops_what_is_not_in_the_tree_and_history_keeps_it_with_the_commit(self):
        found = [finding("sweeping_commits", "info", evidence={"commits": [{"hash": "fmt1", "files": 900}]}),
                 finding("bug_magnets", evidence={"files": [{"file": "gone.py"}, {"file": "src/a.py"}]})]
        head = sarif.build(report(), found, scope="head")
        self.assertEqual([(r["ruleId"], r["locations"][0]["physicalLocation"]["artifactLocation"]["uri"]) for r in head["runs"][0]["results"]],
                         [("bug_magnets", "src/a.py")], "the deleted file and the commit-level finding are gone")
        history = sarif.build(report(), found, scope="history")
        by = {r["ruleId"]: r for r in history["runs"][0]["results"]}
        self.assertEqual(by["sweeping_commits"]["properties"]["commit"], "fmt1")
        self.assertEqual({r["locations"][0]["physicalLocation"]["artifactLocation"]["uri"] for r in history["runs"][0]["results"] if "locations" in r},
                         {"gone.py", "src/a.py"})

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

    def test_vulnerable_dependencies_are_one_result_per_package_with_the_advisory_score(self):
        found = [finding("vulnerable_dependencies", "critical", evidence={"packages": [
            {"name": "minimist", "version": "0.0.8", "source": "package-lock.json", "score": 9.8, "fixed": "1.2.6", "ids": ["GHSA-1"], "aliases": ["CVE-2021-1"], "malicious": False},
            {"name": "evil", "version": "1.0.0", "source": "package-lock.json", "score": None, "fixed": None, "ids": ["MAL-2026-1"], "aliases": [], "malicious": True}]})]
        results = sarif.build(report(), found)["runs"][0]["results"]
        self.assertEqual([r["properties"]["security-severity"] for r in results], ["9.8", "10.0"])
        self.assertEqual(results[0]["message"]["text"], "minimist 0.0.8 in package-lock.json: CVE-2021-1 (9.8), fixed in 1.2.6")
        self.assertEqual(results[1]["message"]["text"], "evil 1.0.0 in package-lock.json: MAL-2026-1, malicious, no fix; remove it")
        self.assertEqual(results[1]["partialFingerprints"]["gitmole/v1"], hashlib.sha256(b"vulnerable_dependencies\0package-lock.json\0\0\0evil@1.0.0").hexdigest())

    def test_the_document_is_json_and_deterministic(self):
        found = [finding("bug_magnets", evidence={"files": [{"file": "src/a.py"}]})]
        a, b = sarif.dumps(report(), found), sarif.dumps(report(), found)
        self.assertEqual(a, b)
        json.loads(a)


if __name__ == "__main__":
    unittest.main()

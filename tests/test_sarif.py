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


class WorkflowShapes(unittest.TestCase):
    def test_a_workflow_shape_is_a_security_result_at_its_line(self):
        f = finding("expression_injection", evidence={"count": 1, "files": [{"file": ".github/workflows/bump.yml", "start": 44, "job": "update",
                                                                              "field": "github.event.pull_request.head.ref"}]})
        [result] = sarif.build(report(tree=[".github/workflows/bump.yml"]), [f])["runs"][0]["results"]
        self.assertEqual(result["locations"][0]["physicalLocation"]["region"], {"startLine": 44})
        self.assertEqual(result["properties"]["security-severity"], "5.0")
        self.assertIn("pwn_request", sarif.SECURITY)


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
                                            "properties": {"tags": ["gitmole", "maintainability"]}}])
        [result] = doc["runs"][0]["results"]
        self.assertEqual(result["ruleId"], "bug_magnets")
        self.assertEqual(result["level"], "warning")
        self.assertEqual(result["message"]["text"], "src/a.py was fixed 5 times in six months. Review it before the next release.",
                         "a result's message names its own subject, not the whole rule's summary")
        self.assertEqual(result["locations"], [{"physicalLocation": {"artifactLocation": {"uri": "src/a.py", "uriBaseId": "%SRCROOT%"}}}])
        self.assertNotIn("security-severity", result["properties"], "a bug magnet is not a vulnerability: GitHub files it as code quality")
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
        self.assertEqual((by["brain_methods"]["level"], by["brain_methods"]["properties"].get("security-severity")), ("note", None))
        rules = {r["id"]: r["properties"] for r in doc["runs"][0]["tool"]["driver"]["rules"]}
        self.assertEqual(rules["credential_files"], {"security-severity": "9.0", "tags": ["gitmole", "security"]})
        self.assertEqual(rules["brain_methods"], {"tags": ["gitmole", "maintainability"]})
        self.assertEqual(by["brain_methods"]["locations"][0]["physicalLocation"]["region"], {"startLine": 1})
        self.assertNotIn("locations", by["dormant"], "a repository-wide finding has no file to point at")

    def test_only_rules_that_exist_are_declared_security_rules(self):
        """paperclip review: bug magnets, brain methods, the truck factor and deep nesting were Medium security alerts."""
        import pathlib
        source = pathlib.Path(sarif.__file__).with_name("findings.py").read_text()
        for rule in sarif.SECURITY:
            self.assertIn(f'"{rule}"', source, rule)
        for rule in ("bug_magnets", "brain_methods", "truck_factor", "deep_nesting"):
            self.assertNotIn(rule, sarif.SECURITY)

    def test_every_finding_the_gate_stops_on_has_an_error_result_under_head_scope(self):
        """A critical secret only in a file deleted since is placed where it was committed, not left without a
        location: GitHub does not display a location-less result, and hindsight's two real keys were exactly these."""
        rows = [{"rule": "github-pat", "file": "old/gone.js", "commit": "d2d2d2d", "line": 3, "fingerprint": "y", "value": "h2", "placeholder": False}]
        found = [finding("secrets_in_source", "critical", evidence={"files": ["old/gone.js"]})]
        results = sarif.build(report(secrets=rows), found)["runs"][0]["results"]
        self.assertEqual([(r["ruleId"], r["level"]) for r in results], [("secrets_in_source", "error")])
        self.assertEqual(results[0]["locations"][0]["physicalLocation"], {"artifactLocation": {"uri": "old/gone.js", "uriBaseId": "%SRCROOT%"},
                                                                          "region": {"startLine": 3}})
        self.assertEqual((results[0]["properties"]["commit"], results[0]["properties"]["inTree"]), ("d2d2d2d", False))
        self.assertIn("no longer in the tree at HEAD", results[0]["message"]["text"])
        history = sarif.build(report(secrets=rows), found, scope="history")["runs"][0]["results"]
        self.assertEqual(history[0]["partialFingerprints"], results[0]["partialFingerprints"], "the same alert under either scope")

    def test_a_removed_critical_value_is_placed_once_where_it_was_first_committed(self):
        def row(value, file, commit, line, date, **extra):
            return {"rule": "groq-api-key", "file": file, "commit": commit, "line": line, "fingerprint": f"{commit}:{file}:{line}", "value": value,
                    "placeholder": False, "confidence": "high", "at_head": False, "date": date, **extra}
        rows = [row("h1", ".env.dev", "b2b2b2b", 7, "2025-03-02T00:00:00Z"), row("h1", ".env.dev", "a1a1a1a", 4, "2025-03-01T00:00:00Z"),
                row("h2", "app/k.py", "c3c3c3c", 1, "2025-01-01T00:00:00Z", at_head=True, head_line=2),
                row("h3", "README.md", "d4d4d4d", 88, "2025-01-01T00:00:00Z", at_head=True, rule="generic-password", confidence="low")]
        from gitmole import findings
        found = findings.secrets_found(report(secrets=rows))
        results = [r for r in sarif.build(report(secrets=rows), found)["runs"][0]["results"] if r["ruleId"] == "secrets_in_source"]
        self.assertEqual(sorted((r["locations"][0]["physicalLocation"]["artifactLocation"]["uri"], r["properties"]["commit"], r["properties"].get("inTree", True))
                                for r in results), [(".env.dev", "a1a1a1a", False), ("app/k.py", "c3c3c3c", True)],
                         "one result for the removed value, at its first commit; the value at HEAD where it is; the documentation-only "
                         "value in another file is no part of the critical")
        low = [dict(x, rule="generic-api-key", confidence="low") for x in rows[:2]]
        info = findings.secrets_found(report(secrets=low))
        self.assertEqual([f["rule"]["id"] for f in info], ["secrets_possible"])
        self.assertFalse([r for r in sarif.build(report(secrets=low), info)["runs"][0]["results"] if r.get("locations")],
                         "only a critical value is placed out of the tree")

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

    def test_every_unpinned_action_is_a_result_at_its_uses_line(self):
        """paperclip: the evidence keeps ten rows, so SARIF covered 2 of 7 workflow files, both at line 1. The report's
        rows are all of them, each with the line of its uses:; a row from an older output directory goes to line 1."""
        rows = [{"file": ".github/workflows/w%d.yml" % i, "uses": "actions/checkout@v4", "line": 10 + i} for i in range(12)]
        rows.append({"file": ".github/workflows/w0.yml", "uses": "x/y@main"})
        found = [finding("unpinned_actions", evidence={"count": 13, "unpinned": [{"file": r["file"], "uses": r["uses"]} for r in rows[:10]]})]
        tree = frozenset(r["file"] for r in rows)
        results = sarif.build(report(tree=tree, hygiene={"actions": {"unpinned": rows, "unpinned_count": 13}}), found)["runs"][0]["results"]
        places = [(r["locations"][0]["physicalLocation"]["artifactLocation"]["uri"], r["locations"][0]["physicalLocation"]["region"]["startLine"])
                  for r in results]
        self.assertEqual(len(results), 13)
        self.assertEqual(places[0], (".github/workflows/w0.yml", 10))
        self.assertEqual(places[-1], (".github/workflows/w0.yml", 1))
        self.assertTrue(results[0]["message"]["text"].startswith("actions/checkout@v4 in .github/workflows/w0.yml, line 10: "))
        self.assertEqual(len({r["partialFingerprints"]["gitmole/v1"] for r in results}), 13)

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
        self.assertEqual(len(results), 2, "one place at HEAD; the duplicate row is one place, the placeholder is not a secret; the value "
                                          "only in the gone file is placed where it was committed")
        self.assertEqual(results[1]["properties"]["inTree"], False)
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
        replaced, r = sarif.build(report(secrets=rows), found, scope="head")["runs"][0]["results"]
        self.assertEqual(r["properties"]["commit"], "d2d2d2d")
        self.assertEqual(r["locations"][0]["physicalLocation"]["region"], {"startLine": 12}, "HEAD's line, where the value is now")
        self.assertEqual(r["message"]["text"], "github-pat in src/a.py at commit d2d2d2d, line 3 of that commit's version; at HEAD, line 12")
        self.assertEqual((replaced["properties"]["commit"], replaced["properties"]["inTree"]), ("c1c1c1c", False),
                         "the replaced value is history only, though its file is in the tree: placed at its commit's line, not HEAD's")
        self.assertEqual(replaced["locations"][0]["physicalLocation"]["region"], {"startLine": 57})
        [only] = sarif.build(report(secrets=rows[:1]), found, scope="head")["runs"][0]["results"]
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


def _trojan_report(rows, bidi=()):
    from gitmole import findings
    rep = report(tree=frozenset({r["file"] for r in list(rows) + list(bidi)}),
                 hygiene={"trojan": {"bidi": list(bidi), "bidi_count": len(bidi), "mixed_script": list(rows), "mixed_script_count": len(rows)}})
    return rep, findings.trojan_source(rep)


def _token(file, line, token="zА"):
    return {"file": file, "line": line, "token": token, "scripts": ["CYRILLIC", "LATIN"]}


class RowResults(unittest.TestCase):
    """univer review (ci-release): Trojan Source had no location though the report had its line, and lock file drift,
    brain methods, deep nesting, bug magnets and the truck factor repeated the whole rule's summary in every result."""

    def test_a_trojan_token_is_placed_at_its_line_and_known_by_the_token_not_the_line(self):
        rep, found = _trojan_report([_token("src/a.ts", 10), _token("src/a.ts", 40), _token("src/b.ts", 3, "pАss")], bidi=[{"file": "src/c.ts", "line": 7, "char": "U+202E"}])
        results = sarif.build(rep, found)["runs"][0]["results"]
        self.assertEqual([(r["locations"][0]["physicalLocation"]["artifactLocation"]["uri"], r["locations"][0]["physicalLocation"]["region"]["startLine"])
                          for r in results], [("src/c.ts", 7), ("src/a.ts", 10), ("src/a.ts", 40), ("src/b.ts", 3)])
        self.assertEqual({r["level"] for r in results}, {"error"}, "a bidirectional character makes the finding critical")
        self.assertEqual(len({r["partialFingerprints"]["gitmole/v1"] for r in results}), 4, "the same token twice in one file is two results")
        self.assertTrue(results[1]["message"]["text"].startswith("zА at src/a.ts:10 mixes CYRILLIC and LATIN: "), results[1]["message"]["text"])
        self.assertTrue(results[0]["message"]["text"].startswith("src/c.ts:7 holds U+202E, a bidirectional control character: "))
        moved, found = _trojan_report([_token("src/a.ts", 15), _token("src/a.ts", 45), _token("src/b.ts", 3, "pАss")], bidi=[{"file": "src/c.ts", "line": 7, "char": "U+202E"}])
        again = sarif.build(moved, found)["runs"][0]["results"]
        self.assertEqual([r["partialFingerprints"] for r in again], [r["partialFingerprints"] for r in results],
                         "five lines added above the tokens: the same alerts, so code scanning neither closes nor reopens them")
        self.assertEqual(again[1]["locations"][0]["physicalLocation"]["region"], {"startLine": 15}, "the line is the region's")

    def test_every_trojan_row_the_report_holds_is_a_result_not_only_the_ten_the_evidence_keeps(self):
        rep, found = _trojan_report([_token(f"src/f{i:02d}.ts", i + 1) for i in range(14)])
        self.assertEqual(len(found[0]["evidence"]["mixed_script"]), 10)
        self.assertEqual(len(sarif.build(rep, found)["runs"][0]["results"]), 14)

    def test_lock_file_drift_is_one_result_per_drifted_manifest_naming_it(self):
        drift = [{"manifest": f"packages/p{i:02d}/package.json", "lockfile": "pnpm-lock.yaml", "manifest_date": "2026-09-29",
                  "lockfile_date": "2026-09-24", "changes": [{"commit": "c%02d" % i, "date": "2026-09-29"}]} for i in range(60)]
        drift[59]["changes"] = [{"commit": "sweep1", "date": "2026-09-29"}]
        hyg = {"lockfiles": {"drift": drift[:50] + drift[59:], "drift_count": 60}}
        rep = report(tree=frozenset(d["manifest"] for d in drift) | {"pnpm-lock.yaml"}, hygiene=hyg,
                     activity={"sweeping": [{"hash": "sweep1"}]})
        from gitmole import findings
        found = findings.lockfile_drift(rep)
        results = sarif.build(rep, found)["runs"][0]["results"]
        self.assertEqual(len(results), 50, "the hygiene step's rows, capped at its own 50, not the evidence's ten; a sweep's drift is left out")
        self.assertNotIn("packages/p59/package.json", {r["locations"][0]["physicalLocation"]["artifactLocation"]["uri"] for r in results})
        self.assertEqual(results[3]["message"]["text"], "packages/p03/package.json changed on 2026-09-29, after pnpm-lock.yaml last did on 2026-09-24. "
                         "Regenerate pnpm-lock.yaml and commit it with the manifest; a frozen install does not catch this.")
        self.assertEqual(results[3]["partialFingerprints"]["gitmole/v1"], sarif._fingerprint("lockfile_drift", "packages/p03/package.json", "", 1),
                         "the fingerprint 0.44.0 gave the same manifest: the message changed, the alert did not")

    def test_brain_methods_deep_nesting_and_the_truck_factor_name_their_own_subject(self):
        brain = finding("brain_methods", evidence={"functions": [{"file": "src/a.py", "function": "parse", "start": 12, "ccn": 31, "lines": 140, "params": 2}]})
        deep = finding("deep_nesting", evidence={"functions": [{"file": "src/a.py", "name": "walk", "start": 80, "nesting": 6, "cognitive": 40, "bumps": 1}]})
        truck = finding("truck_factor", evidence={"areas": [{"area": "src/", "author": "Ann", "files": 30, "orphaned": 20}]})
        rep = report(tree=frozenset({"src/a.py"}))
        rep["meta"]["gone_months"] = 6
        results = {r["ruleId"]: r for r in sarif.build(rep, [brain, deep])["runs"][0]["results"]}
        self.assertEqual(results["brain_methods"]["message"]["text"],
                         "parse at src/a.py:12 is long and complex: complexity 31, 140 lines, 2 params. Split it before the next change lands there.")
        self.assertEqual(results["brain_methods"]["partialFingerprints"]["gitmole/v1"], sarif._fingerprint("brain_methods", "src/a.py", "", 12, "parse"))
        self.assertEqual(results["deep_nesting"]["message"]["text"],
                         "walk at src/a.py:80 nests 6 deep, cognitive complexity 40, 1 bump. Flatten it: return early and move each nested chunk into a function of its own.")
        [area] = sarif.build({"meta": {}}, [truck], scope="history")["runs"][0]["results"]
        self.assertTrue(area["message"]["text"].startswith("src/ has a truck factor of one (Ann): 20 of its 30 source files would have no author left"),
                        area["message"]["text"])

    def test_every_result_whose_report_row_has_a_line_carries_a_region(self):
        from gitmole import findings
        fn = {"file": "src/a.py", "function": "f", "start": 5, "end": 160, "ccn": 20, "nloc": 150, "params": 1}
        deep = {"file": "src/a.py", "name": "g", "start": 200, "nesting": 6, "cognitive": 30, "bumps": 0}
        rep = report(tree=frozenset({"src/a.py", "src/t.ts", ".github/workflows/ci.yml", "web/package.json"}),
                     functions=[fn], structure={"status": "run", "files": {}, "functions": [deep]},
                     hygiene={"trojan": {"bidi": [], "mixed_script": [_token("src/t.ts", 9)], "mixed_script_count": 1},
                              "actions": {"unpinned": [{"file": ".github/workflows/ci.yml", "uses": "x/y@v1", "line": 14}], "unpinned_count": 1},
                              "lockfiles": {"drift": [{"manifest": "web/package.json", "lockfile": "web/package-lock.json",
                                                       "manifest_date": "2026-01-02", "lockfile_date": "2025-01-01"}], "drift_count": 1}})
        found = findings.brain_methods(rep) + findings.deep_nesting(rep) + findings.hygiene_findings(rep)
        self.assertEqual({f["rule"]["id"] for f in found} >= {"brain_methods", "deep_nesting", "trojan_source", "unpinned_actions", "lockfile_drift"}, True)
        results = sarif.build(rep, found)["runs"][0]["results"]
        lines = {(r["ruleId"], r["locations"][0]["physicalLocation"].get("region", {}).get("startLine")) for r in results}
        self.assertEqual(lines, {("brain_methods", 5), ("deep_nesting", 200), ("trojan_source", 9), ("unpinned_actions", 14), ("lockfile_drift", 1)})



if __name__ == "__main__":
    unittest.main()

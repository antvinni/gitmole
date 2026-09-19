"""What the project declares about its dependencies and licences, and what gitmole makes of it: which
packages the source imports (imports.py), the declared licences (licences.py), the OSPS Baseline
coverage (osps.py) and the CycloneDX SBOM (sbom.py)."""
import json
import tempfile
import unittest

from gitmole import deps, findings, imports, licences, osps, render, sarif, sbom
from tests.test_findings import report
from tests.test_hygiene import Repo


class ImportScan(unittest.TestCase):
    def test_js_specifiers_keep_the_package_and_drop_relative_paths_and_builtins(self):
        text = ("import a from 'left-pad'\nimport {x} from \"@scope/pkg/sub\"\nconst b = require('lodash/fp')\nimport './local'\n"
                "import fs from 'node:fs'\nexport * from 'rxjs'\nconst c = await import('chalk')\nimport 'polyfill'\n")
        self.assertEqual(imports.scan_text("npm", text), {"left-pad", "@scope/pkg", "lodash", "rxjs", "chalk", "polyfill"})

    def test_python_top_level_modules_in_normal_form(self):
        text = "import os, yaml as y\nfrom Foo_Bar.baz import q\nfrom . import sibling\n    import requests\n"
        self.assertEqual(imports.scan_text("PyPI", text), {"os", "yaml", "foo_bar", "requests"})

    def test_go_import_blocks_single_imports_and_go_generate(self):
        text = ('package x\nimport (\n\t"fmt"\n\tnet "golang.org/x/net/http2"\n)\nimport "github.com/a/b"\n'
                "//go:generate go run github.com/tool/gen -o x\n")
        self.assertEqual(imports.scan_text("Go", text), {"fmt", "golang.org/x/net/http2", "github.com/a/b", "github.com/tool/gen"})

    def test_rust_paths_and_extern_crate(self):
        found = imports.scan_text("crates.io", "use serde::Serialize;\nextern crate libc;\nfn f() { tokio::spawn(x) }\n")
        self.assertTrue({"serde", "libc", "tokio"} <= found)

    def test_imported_is_false_only_where_the_import_name_is_the_package_name(self):
        seen = {"npm": {"a"}, "Go": {"golang.org/x/net/http2"}, "crates.io": {"serde_json"}, "PyPI": {"requests"}, "RubyGems": {"net/http"}}
        self.assertIs(imports.is_imported("npm", "a", seen), True)
        self.assertIs(imports.is_imported("npm", "b", seen), False)
        self.assertIs(imports.is_imported("Go", "golang.org/x/net", seen), True)
        self.assertIs(imports.is_imported("Go", "golang.org/x/ne", seen), False, "a module is a path prefix, not a string prefix")
        self.assertIsNone(imports.is_imported("Go", "stdlib", seen))
        self.assertIs(imports.is_imported("crates.io", "serde-json", seen), True)
        self.assertIs(imports.is_imported("PyPI", "Requests", seen), True)
        self.assertIsNone(imports.is_imported("PyPI", "PyYAML", seen), "a distribution may be imported under another name")
        self.assertIs(imports.is_imported("RubyGems", "net-http", seen), True)
        self.assertIsNone(imports.is_imported("Maven", "g:a", seen))

    def test_annotate_marks_each_vulnerable_row(self):
        with tempfile.TemporaryDirectory() as d:
            r = Repo(d)
            r.write("src/app.js", "const m = require('minimist')\n")
            r.write("node_modules/qs/index.js", "require('qs-inner')\n")
            r.commit()
            rows = [{"ecosystem": "npm", "name": "minimist"}, {"ecosystem": "npm", "name": "qs"}, {"ecosystem": "PyPI", "name": "jinja2"}]
            imports.annotate(rows, d)
        self.assertEqual([x["imported"] for x in rows], [True, False, "unknown"])


class DeclaredUnused(unittest.TestCase):
    def test_manifest_parsers(self):
        names, scripts = imports.npm_declared(json.dumps({"dependencies": {"a": "1", "@types/node": "1"}, "devDependencies": {"b": "1"}, "scripts": {"x": "rimraf dist"}}))
        self.assertEqual((names, scripts), (["a"], "rimraf dist"))
        gomod = "module m\n\nrequire (\n\tgithub.com/a/b v1.0.0\n\tgithub.com/c/d v1.0.0 // indirect\n)\nrequire github.com/e/f v2.0.0\n"
        self.assertEqual(imports.go_declared(gomod), ["github.com/a/b", "github.com/e/f"])
        cargo = ('[package]\nname = "x"\n[dependencies]\nserde = "1"\nfoo = { package = "bar", version = "1" }\nopenssl-sys = "0.9"\n'
                 'tokio.workspace = true\n[dependencies.rand]\nversion = "0.8"\n[target.\'cfg(unix)\'.dependencies]\nnix = "0.27"\n[dev-dependencies]\nproptest = "1"\n')
        self.assertEqual(imports.cargo_declared(cargo), ["foo", "nix", "rand", "serde", "tokio"])

    def test_unused_leaves_out_what_is_imported_configured_or_scripted(self):
        with tempfile.TemporaryDirectory() as d:
            r = Repo(d)
            r.write("package.json", json.dumps({"dependencies": {"used": "1", "configured": "1", "scripted": "1", "idle": "1"}, "scripts": {"build": "scripted --x"}}))
            r.write("src/a.ts", "import u from 'used'\n")
            r.write(".babelrc.json", json.dumps({"presets": ["configured"]}))
            r.write("other/package.json", json.dumps({"dependencies": {"idle": "1"}}))
            r.write("examples/demo/package.json", json.dumps({"dependencies": {"never": "1"}}))
            r.commit()
            out = imports.unused(d)
        self.assertEqual([(x["manifest"], x["package"]) for x in out["unused"]], [("other/package.json", "idle"), ("package.json", "idle")],
                         "another manifest naming a package is not a use of it, and an example's manifest is left out")


class LicenceExpressions(unittest.TestCase):
    def test_or_takes_the_choice_and_and_takes_every_term(self):
        self.assertEqual(licences.classify("MIT OR GPL-3.0-only"), licences.PERMISSIVE)
        self.assertEqual(licences.classify("MIT AND GPL-3.0-or-later"), licences.STRONG)
        self.assertEqual(licences.classify("(LGPL-2.1+ OR GPL-3.0)"), licences.WEAK)
        self.assertEqual(licences.classify("GPL-2.0-only WITH Classpath-exception-2.0"), licences.WEAK)
        self.assertEqual(licences.classify("MIT/X11"), licences.PERMISSIVE)
        self.assertIsNone(licences.classify("GPL-3.0 OR LicenseRef-Custom"), "an unknown branch may be the one taken")
        self.assertIsNone(licences.classify("Custom"))

    def test_approval_is_three_valued(self):
        self.assertIs(licences.approved("Apache-2.0"), True)
        self.assertIs(licences.approved("GPL-3.0-or-later"), True)
        self.assertIs(licences.approved("SSPL-1.0"), False)
        self.assertIsNone(licences.approved("curl"))

    def test_licence_texts_by_their_opening_words(self):
        mit = "MIT License\n\nPermission is hereby granted, free of charge, to any person obtaining a copy of this software ...\n\nThe above copyright notice and this permission notice shall be included in all copies"
        self.assertEqual(licences.identify(mit), "MIT")
        self.assertEqual(licences.identify("Apache License\n  Version 2.0, January 2004"), "Apache-2.0")
        self.assertEqual(licences.identify("GNU GENERAL PUBLIC LICENSE\nVersion 3, 29 June 2007\n... GNU Lesser General Public License ..."), "GPL-3.0")
        self.assertEqual(licences.identify("GNU LESSER GENERAL PUBLIC LICENSE\nVersion 2.1, February 1999"), "LGPL-2.1")
        self.assertEqual(licences.identify("Redistribution and use in source and binary forms ... Neither the name of"), "BSD-3-Clause")
        self.assertIsNone(licences.identify("All rights reserved."))


class LicenceCheck(unittest.TestCase):
    def _repo(self, d, lock, pyproject='[project]\nname = "x"\nlicense = "MIT"\n'):
        r = Repo(d)
        r.write("LICENSE", "Permission is hereby granted, free of charge, to any person obtaining a copy\nThe above copyright notice and this permission notice shall be included")
        r.write("pyproject.toml", pyproject)
        r.write("package-lock.json", json.dumps(lock))
        r.commit()

    def test_strong_copyleft_runtime_dependencies_and_the_weak_count(self):
        lock = {"lockfileVersion": 3, "packages": {"": {"name": "x"}, "node_modules/gpl-lib": {"version": "1.0.0", "license": "GPL-3.0"},
                                                   "node_modules/lgpl-lib": {"version": "2.0.0", "license": "LGPL-3.0"},
                                                   "node_modules/dev-gpl": {"version": "1.0.0", "license": "AGPL-3.0", "dev": True},
                                                   "node_modules/ok": {"version": "1.0.0", "license": "(MIT OR GPL-2.0)"}}}
        with tempfile.TemporaryDirectory() as d:
            self._repo(d, lock)
            out = licences.check(d)
        self.assertEqual(out["project"], licences.PERMISSIVE)
        self.assertIs(out["approved"], True)
        self.assertFalse(out["mismatch"])
        self.assertEqual([x["name"] for x in out["strong"]], ["gpl-lib"])
        self.assertEqual((out["weak_count"], out["dependencies"]), (1, 3), "development packages are left out")
        f = findings.hygiene_findings({"hygiene": {"licences": out}})
        self.assertEqual([(x["rule"]["id"], x["severity"]) for x in f], [("copyleft_dependencies", "warning")])
        self.assertIn("gpl-lib 1.0.0 (GPL-3.0)", f[0]["detail"])
        self.assertIn("Declared", f[0]["detail"])

    def test_a_manifest_that_disagrees_with_the_licence_file(self):
        with tempfile.TemporaryDirectory() as d:
            self._repo(d, {"packages": {}}, pyproject='[project]\nname = "x"\nlicense = {text = "Apache-2.0"}\n')
            out = licences.check(d)
        self.assertTrue(out["mismatch"])
        f = findings.hygiene_findings({"hygiene": {"licences": out}})
        self.assertEqual([(x["rule"]["id"], x["severity"]) for x in f], [("project_licence", "info")])
        self.assertEqual(f[0]["rule"]["osps"], ["OSPS-LE-02.01"])


class UnusedFinding(unittest.TestCase):
    def test_one_info_finding_naming_the_manifests(self):
        h = {"imports": {"manifests": 2, "count": 2, "unused": [{"manifest": "package.json", "ecosystem": "npm", "package": "a"},
                                                                  {"manifest": "go.mod", "ecosystem": "Go", "package": "github.com/b/c"}]}}
        f = findings.hygiene_findings({"hygiene": h})
        self.assertEqual([(x["rule"]["id"], x["severity"]) for x in f], [("unused_dependencies", "info")])
        self.assertIn("a in package.json", f[0]["detail"])


class VulnerableImported(unittest.TestCase):
    def test_the_row_says_when_nothing_imports_it_and_the_severity_stands(self):
        rows = [{"name": "qs", "version": "1", "ecosystem": "npm", "source": "package-lock.json", "ids": ["GHSA-1"], "aliases": [], "score": 9.8,
                 "severity": "critical", "fixed": "2", "malicious": False, "imported": False}]
        f = findings.vulnerable_dependencies(report(dependencies={"status": "scanned", "vulnerable": rows}))
        self.assertEqual(f[0]["severity"], "critical", "an unimported package is still installed; nothing is suppressed on it")
        self.assertIn("imported by no tracked source", f[0]["detail"])
        self.assertIs(f[0]["evidence"]["packages"][0]["imported"], False)
        self.assertEqual(f[0]["rule"]["osps"], ["OSPS-VM-05.03"])


class OspsCoverage(unittest.TestCase):
    def _report(self, **over):
        h = {"presence": {"license": "LICENSE", "security_policy": None, "contributing": "CONTRIBUTING.md"},
             "licences": {"declared": [{"source": "pyproject.toml", "expression": "MIT"}], "files": ["LICENSE"], "file_licence": "MIT", "approved": True},
             "lockfiles": {"pairs": 0, "missing": [], "drift": []}, "binaries": {"executables": [{"file": "bin/tool", "format": "ELF"}], "lfs_unpointed": []}}
        return report(hygiene=h, secrets_scanned=True, dependencies={"status": "scanned", "packages": 12, "vulnerable": []},
                      provenance={"trailers": {"commits": 10, "keys": {"Signed-off-by": 10}}}, **over)

    def test_every_control_gets_a_result_from_the_data_it_rests_on(self):
        r = self._report()
        rows = {x["control"]: (x["result"], x["evidence"]) for x in osps.coverage(r, findings.evaluate(r))}
        self.assertEqual(set(rows), set(osps.CONTROLS))
        self.assertEqual(rows["OSPS-BR-07.01"][0], "met")
        self.assertEqual(rows["OSPS-VM-02.01"][0], "gap")
        self.assertEqual(rows["OSPS-GV-03.01"], ("met", "CONTRIBUTING.md"))
        self.assertEqual(rows["OSPS-LE-01.01"][0], "met")
        self.assertEqual(rows["OSPS-LE-02.01"], ("met", "MIT"))
        self.assertEqual(rows["OSPS-QA-02.01"][0], "not applicable")
        self.assertEqual(rows["OSPS-QA-05.01"][0], "gap")
        self.assertEqual(rows["OSPS-VM-05.03"][0], "met")

    def test_every_rule_the_table_names_is_one_a_finding_carries(self):
        import inspect
        source = inspect.getsource(findings)
        for control, (_, rules) in osps.CONTROLS.items():
            for rule in rules:
                self.assertIn(f'"id": "{rule}"', source, f"{control} names {rule}, which no rule emits")

    def test_a_secret_in_source_is_a_gap(self):
        r = self._report(secrets=[{"rule": "aws-access-token", "file": "c.py", "commit": "abc1234", "line": 3, "value": "h1"}])
        rows = {x["control"]: x["result"] for x in osps.coverage(r, findings.evaluate(r))}
        self.assertEqual(rows["OSPS-BR-07.01"], "gap")

    def test_a_met_row_names_the_possible_and_aside_secrets_it_set_aside(self):
        r = self._report(secrets=[{"rule": "generic-password", "file": "app/db.py", "commit": "abc1234", "line": 3, "value": "h1", "confidence": "low"},
                                  {"rule": "private-key", "file": "tests/server.key", "commit": "abc1234", "line": 1, "value": "h2", "confidence": "high"}])
        rows = {x["control"]: (x["result"], x["evidence"]) for x in osps.coverage(r, findings.evaluate(r))}
        self.assertEqual(rows["OSPS-BR-07.01"][0], "met")
        self.assertTrue(rows["OSPS-BR-07.01"][1].startswith("no secret in source over every branch; "), rows["OSPS-BR-07.01"][1])
        self.assertIn("1 possible secret(s) in source", rows["OSPS-BR-07.01"][1])
        self.assertIn("1 secret(s) only in test", rows["OSPS-BR-07.01"][1], "not 'found none' while the findings list them")

    def test_nothing_run_is_not_checked_rather_than_met(self):
        r = report()
        rows = {x["control"]: x["result"] for x in osps.coverage(r, findings.evaluate(r))}
        self.assertEqual(set(rows.values()), {"not checked"})

    def test_rules_carry_their_controls_and_sarif_tags_them(self):
        r = self._report()
        found = findings.evaluate(r)
        binaries = next(f for f in found if f["rule"]["id"] == "committed_binaries")
        self.assertEqual(binaries["rule"]["osps"], ["OSPS-QA-05.01", "OSPS-QA-05.02"])
        rules = {x["id"]: x for x in sarif.build(r, found)["runs"][0]["tool"]["driver"]["rules"]}
        self.assertEqual(rules["committed_binaries"]["properties"]["tags"], ["gitmole", "OSPS-QA-05.01", "OSPS-QA-05.02"])

    def test_the_section_is_full_only_and_the_export_carries_the_table(self):
        r = self._report()
        self.assertIn("osps", render.FULL_ONLY)
        out = render.to_json(r, findings.evaluate(r))
        self.assertEqual(out["osps"]["baseline"], osps.BASELINE)
        self.assertEqual(len(out["osps"]["controls"]), len(osps.CONTROLS))


class PackageList(unittest.TestCase):
    def test_one_row_per_package_with_its_lock_files_and_declared_licence(self):
        with tempfile.TemporaryDirectory() as d:
            r = Repo(d)
            r.write("package-lock.json", json.dumps({"packages": {"node_modules/a": {"version": "1.0.0", "license": "ISC"}}}))
            r.write("web/package-lock.json", json.dumps({"packages": {}}))
            r.commit()
            data = {"results": [{"source": {"path": f"{d}/package-lock.json"}, "packages": [{"package": {"name": "a", "version": "1.0.0", "ecosystem": "npm"}},
                                                                                           {"package": {"name": "b", "version": "2.0.0", "ecosystem": "npm"}}]},
                                {"source": {"path": f"{d}/web/package-lock.json"}, "packages": [{"package": {"name": "a", "version": "1.0.0", "ecosystem": "npm"}}]}]}
            rows = deps.packages(data, d)
        self.assertEqual(rows, [{"ecosystem": "npm", "name": "a", "version": "1.0.0", "sources": ["package-lock.json", "web/package-lock.json"], "license": "ISC"},
                                {"ecosystem": "npm", "name": "b", "version": "2.0.0", "sources": ["package-lock.json"]}])


class Sbom(unittest.TestCase):
    PACKAGES = [{"ecosystem": "npm", "name": "@scope/pkg", "version": "1.2.3", "sources": ["package-lock.json"], "license": "MIT"},
                {"ecosystem": "Go", "name": "golang.org/x/net", "version": "0.17.0", "sources": ["go.sum"]},
                {"ecosystem": "Maven", "name": "org.a:b", "version": "2", "sources": ["pom.xml"]},
                {"ecosystem": "PyPI", "name": "Foo_Bar", "version": "3", "sources": ["uv.lock"]},
                {"ecosystem": "Nowhere", "name": "x", "version": "1", "sources": ["x.lock"]}]

    def test_package_urls(self):
        self.assertEqual(sbom.purl("npm", "@scope/pkg", "1.2.3"), "pkg:npm/%40scope/pkg@1.2.3")
        self.assertEqual(sbom.purl("Go", "golang.org/x/net", "0.17.0"), "pkg:golang/golang.org/x/net@v0.17.0")
        self.assertEqual(sbom.purl("Maven", "org.a:b", "2"), "pkg:maven/org.a/b@2")
        self.assertEqual(sbom.purl("PyPI", "Foo_Bar", "3"), "pkg:pypi/foo-bar@3")
        self.assertIsNone(sbom.purl("Nowhere", "x", "1"))

    def test_a_cyclonedx_document_that_is_the_same_bytes_twice(self):
        r = report(meta={"name": "r", "last_date": "2026-09-17", "run": {"commit": "abc", "gitmole": "9.9.9"}},
                   hygiene={"licences": {"declared": [{"source": "pyproject.toml", "expression": "MIT"}], "file_licence": "MIT"}})
        text = sbom.dumps(r, self.PACKAGES)
        self.assertEqual(text, sbom.dumps(r, self.PACKAGES))
        doc = json.loads(text)
        self.assertEqual((doc["bomFormat"], doc["specVersion"], doc["version"]), ("CycloneDX", "1.6", 1))
        self.assertTrue(doc["serialNumber"].startswith("urn:uuid:"))
        self.assertEqual(doc["metadata"]["timestamp"], "2026-09-17T00:00:00Z")
        self.assertEqual(doc["metadata"]["component"], {"type": "application", "bom-ref": "root", "name": "r", "version": "abc", "licenses": [{"expression": "MIT"}]})
        first = doc["components"][0]
        self.assertEqual(first["purl"], "pkg:npm/%40scope/pkg@1.2.3")
        self.assertEqual(first["licenses"], [{"expression": "MIT"}])
        self.assertIn({"name": "gitmole:lockfile", "value": "package-lock.json"}, first["properties"])
        self.assertEqual(doc["components"][-1]["bom-ref"], "Nowhere:x@1")
        self.assertNotIn("purl", doc["components"][-1])
        self.assertNotEqual(json.loads(sbom.dumps(r, self.PACKAGES[:1]))["serialNumber"], doc["serialNumber"])


if __name__ == "__main__":
    unittest.main()

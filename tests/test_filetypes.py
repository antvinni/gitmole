import os
import subprocess
import tempfile
import unittest

from gitmole import filetypes


class Parse(unittest.TestCase):
    def test_default_when_unset(self):
        self.assertIs(filetypes.parse(None), filetypes.DEFAULT)
        self.assertIn("py", filetypes.DEFAULT)
        self.assertIn("sql", filetypes.DEFAULT)
        self.assertNotIn("md", filetypes.DEFAULT)
        self.assertNotIn("json", filetypes.DEFAULT)

    def test_comma_list_normalised(self):
        self.assertEqual(filetypes.parse(" Py, .SQL ,ts"), {"py", "sql", "ts"})

    def test_all_means_no_filter(self):
        self.assertIsNone(filetypes.parse("all"))


class Matches(unittest.TestCase):
    def test_extension_and_special_names(self):
        self.assertTrue(filetypes.matches("src/a.py", filetypes.DEFAULT))
        self.assertTrue(filetypes.matches("Makefile", filetypes.DEFAULT))
        self.assertTrue(filetypes.matches("deploy/Dockerfile", filetypes.DEFAULT))
        self.assertFalse(filetypes.matches("README.md", filetypes.DEFAULT))
        self.assertFalse(filetypes.matches("data/x.csv", filetypes.DEFAULT))
        self.assertTrue(filetypes.matches("anything.xyz", None))

    def test_custom_set(self):
        self.assertTrue(filetypes.matches("a.sql", {"sql"}))
        self.assertFalse(filetypes.matches("a.py", {"sql"}))


class GitPaths(unittest.TestCase):
    def _repo(self, d):
        subprocess.run(["git", "init", "-q", d], check=True)
        for name in ["a.py", "s\u00e4.py", 'q"uote.py', "tab\tx.py"]:
            with open(os.path.join(d, name), "w") as fh: fh.write("x\n")
        subprocess.run(["git", "-C", d, "add", "-A"], check=True)
        # a Latin-1 name that is not valid UTF-8, straight into the index
        blob = subprocess.run(["git", "-C", d, "hash-object", "-w", "--stdin"], input=b"x\n", capture_output=True, check=True).stdout.decode().strip()
        subprocess.run(["git", "-C", d, "update-index", "--add", "--cacheinfo", "100644", blob, "caf\xe9.py".encode("latin-1").decode("utf-8", "surrogateescape")], check=True)

    def test_lists_paths_unquoted_and_never_raises(self):
        with tempfile.TemporaryDirectory() as d:
            self._repo(d)
            paths = filetypes.git_paths(d, "ls-files")
        self.assertIn("s\u00e4.py", paths)
        self.assertIn('q"uote.py', paths)
        self.assertIn("tab\tx.py", paths)
        self.assertFalse([p for p in paths if p.startswith('"')])
        self.assertTrue([p for p in paths if p.startswith("caf")], "the non-UTF-8 name survives decoding")

    def test_discover_uses_the_same_lister(self):
        with tempfile.TemporaryDirectory() as d:
            self._repo(d)
            rows = dict((k, n) for k, n, _ in filetypes.discover(d, filetypes.DEFAULT))
        self.assertEqual(rows.get("py"), 5)
        self.assertFalse([k for k in rows if k.endswith('"')])


class Unquote(unittest.TestCase):
    def test_octal_escapes_quotes_and_mixed_raw_utf8(self):
        self.assertEqual(filetypes.unquote('"src/\\303\\244.py"'), "src/\u00e4.py")
        self.assertEqual(filetypes.unquote('"say \\"hi\\".md"'), 'say "hi".md')
        self.assertEqual(filetypes.unquote('"d\\t\u00e4/x.py"'), "d\t\u00e4/x.py")
        self.assertEqual(filetypes.unquote("plain/path.py"), "plain/path.py")
        self.assertEqual(filetypes.unquote('"bad/\\344dir/x.py"'), "bad/\ufffddir/x.py", "undecodable bytes become U+FFFD, never a raw escape")


class Discover(unittest.TestCase):
    def test_counts_extensions_in_the_tree_and_marks_included(self):
        with tempfile.TemporaryDirectory() as d:
            subprocess.run(["git", "init", "-q", d], check=True)
            for name in ["a.py", "b.py", "c.md", "Makefile", "d.CSV"]:
                with open(os.path.join(d, name), "w") as fh: fh.write("x\n")
            subprocess.run(["git", "-C", d, "add", "-A"], check=True)
            rows = filetypes.discover(d, filetypes.DEFAULT)
        self.assertEqual(rows, [("py", 2, True), ("csv", 1, False), ("makefile", 1, True), ("md", 1, False)])



class TestPaths(unittest.TestCase):
    def test_test_files_and_directories(self):
        for path in ("tests/test_a.py", "a/spec/b.rb", "src/__tests__/x.js", "x/y_test.go", "app.spec.ts", "app.test.tsx", "test_x.py",
                     "pending_tests/main.py", "e2e-tests/login.ts", "src/test_utils/helpers.py", "crates/x/snapshots/rule__S105.py.snap",
                     "src/__snapshots__/a.js.snap", "lib/render.snap"):
            self.assertTrue(filetypes.is_test_path(path), path)
        for path in ("src/contest.py", "gitmole/render.py", "attest/x.py", "latest.md", "src/testimony.py", "snapshot.py"):
            self.assertFalse(filetypes.is_test_path(path), path)

    def test_documentation_files_and_directories(self):
        for path in ("README.md", "docs/GA4-API-INTEGRATION.md", "doc/guide.rst", "NOTES.txt", "a/b/CHANGELOG.markdown", "docs/conf.py", "x.adoc",
                     "docs_src/security/tutorial004.py", "docs-site/app.js", "doc_examples/x.py",
                     "mypy/typeshed/stdlib/_hashlib.pyi", "types/request.d.ts"):   # type stubs declare shapes, they hold no runtime values
            self.assertTrue(filetypes.is_doc_path(path), path)
        for path in ("app/settings.py", "static/index.html", "docsite/app.js", "mdx/a.py", "config.yaml", "doctor/a.py"):
            self.assertFalse(filetypes.is_doc_path(path), path)

    def test_example_fixture_and_rule_directories(self):
        for path in ("examples/language/bru.bru", "example/app.py", "samples/x.json", "sample/x.json", "fixtures/keys.pem",
                     "src/fixture/a.txt", "pkg/testdata/creds.yaml", "demo/x.py", "demos/x.py", "config/generate/rules/slack.go"):
            self.assertTrue(filetypes.is_sample_path(path), path)
        for path in ("app/settings.py", "examplesite/app.py", "src/rulesets/a.go", "sampler/x.py", "config/betterleaks.toml",
                     "src/main/java/com/example/service/impl/AccountServiceImpl.java", "org/example/App.kt"):   # a reverse-domain package
            self.assertFalse(filetypes.is_sample_path(path), path)

    def test_a_source_file_and_its_own_header_are_a_header_pair(self):
        for a, b in (("src/vector.c", "src/vector.h"), ("src/vector.h", "src/vector.c"), ("lib/x.cpp", "lib/x.hpp"), ("lib/x.cc", "lib/x.hh"),
                     ("ui/view.m", "ui/view.h"), ("ui/view.mm", "ui/view.h")):
            self.assertTrue(filetypes.is_header_pair(a, b), (a, b))
        for a, b in (("src/vector.c", "src/list.h"), ("src/vector.c", "include/vector.h"), ("src/a.py", "src/a.pyi"), ("src/vector.c", "src/vector.c")):
            self.assertFalse(filetypes.is_header_pair(a, b), (a, b))

    def test_release_plumbing_files(self):
        for path in ("lib/sinatra/version.rb", "VERSION", "src/pkg/__version__.py", "package.json", "package-lock.json", "Gemfile.lock",
                     "Cargo.toml", "pyproject.toml", "go.sum", "CHANGELOG.md", "CHANGES.rst", "sinatra.gemspec", "uv.lock"):
            self.assertTrue(filetypes.is_release_path(path), path)
        for path in ("lib/version_check.py", "src/app.py", "docs/versions.md", "Makefile", "lib/sinatra/base.rb"):
            self.assertFalse(filetypes.is_release_path(path), path)

    def test_generated_files_by_header_marker_or_attribute(self):
        with tempfile.TemporaryDirectory() as d:
            files = {
                "lib/config-validator.js": "// This file is autogenerated by build/build-validation.js, do not edit\n'use strict'\n",
                "pb/api.pb.go": "// Code generated by protoc-gen-go. DO NOT EDIT.\npackage pb\n",
                "gen/schema.py": "# @generated\nx = 1\n",
                "src/app.py": "# the app; it generated reports once\ndef main():\n    pass\n",
                "docs/notes.md": "generated notes are the best notes\n",
                "dist/bundle.js": "var a = 1;\n",
                "src/late.py": "\n" * 10 + "# generated by hand, do not edit\n",   # a marker past the first lines does not count
            }
            for path, text in files.items():
                os.makedirs(os.path.join(d, os.path.dirname(path)), exist_ok=True)
                with open(os.path.join(d, path), "w") as fh:
                    fh.write(text)
            with open(os.path.join(d, ".gitattributes"), "w") as fh:
                fh.write("* text=auto\ndist/* linguist-generated=true\n*.min.js linguist-generated\n")
            found = filetypes.generated_files(d, sorted(files))
        self.assertEqual(found, ["dist/bundle.js", "gen/schema.py", "lib/config-validator.js", "pb/api.pb.go"])

    def test_a_nested_licence_with_other_copyright_holders_marks_a_vendored_tree(self):
        with tempfile.TemporaryDirectory() as d:
            files = {
                "LICENSE": "MIT License\n\nCopyright (c) 2012-2023 Jukka Lehtosalo and contributors\nCopyright (c) 2015-2023 Dropbox, Inc.\n",
                "mypy/typeshed/LICENSE": "Apache License\nVersion 2.0\n\"Licensor\" shall mean the copyright owner or entity\n",   # no holder named: not ours
                "mypyc/external/googletest/LICENSE": "Copyright 2008, Google Inc.\nAll rights reserved.\n",
                "packages/core/LICENSE": "MIT License\n\nCopyright (c) 2012-present Jukka Lehtosalo\n",   # our own package: same holder
                "mypy/checker.py": "x = 1\n",
            }
            for path, text in files.items():
                os.makedirs(os.path.join(d, os.path.dirname(path)) or d, exist_ok=True)
                with open(os.path.join(d, path), "w") as fh:
                    fh.write(text)
            found = filetypes.vendored_dirs(d, sorted(files))
        self.assertEqual(found, ["mypy/typeshed/", "mypyc/external/googletest/"])
        self.assertTrue(filetypes.is_vendored("mypy/typeshed/stdlib/_hashlib.pyi", found))
        self.assertFalse(filetypes.is_vendored("mypy/checker.py", found))
        self.assertTrue(filetypes.is_vendored("deps/lua/a.c", found), "the name rule still applies")

    def test_no_root_licence_means_no_vendored_dirs_by_licence(self):
        with tempfile.TemporaryDirectory() as d:
            os.makedirs(os.path.join(d, "lib", "x"))
            with open(os.path.join(d, "lib", "x", "LICENSE"), "w") as fh:
                fh.write("Copyright 2008, Google Inc.\n")
            self.assertEqual(filetypes.vendored_dirs(d, ["lib/x/LICENSE"]), [], "nothing to compare against")

    def test_vendored_trees(self):
        for path in ("vendor/github.com/x/y.go", "web/node_modules/a/index.js", "third_party/z/a.c", "thirdparty/a.c", "_vendor/a.py",
                     "external/lib/a.cpp", "requests/packages/urllib3/a.py", "pip/_vendor/six.py", "botocore/vendored/requests/a.py",
                     "deps/lua/src/strbuf.c", "deps/jemalloc/Makefile"):
            self.assertTrue(filetypes.is_vendor_path(path), path)
        for path in ("vendors.py", "src/vendoring/a.py", "node/a.js", "externals.txt", "app/main.go",
                     "packages/runtime-core/src/renderer.ts", "packages-private/x.ts"):   # a monorepo's own packages/ at the root
            self.assertFalse(filetypes.is_vendor_path(path), path)


if __name__ == "__main__":
    unittest.main()

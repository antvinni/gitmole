import os
import subprocess
import tempfile
import unittest

from gitmole import filetypes


def git_repo(d: str, files: dict) -> None:
    """A repository at `d` holding `files` (path -> text), staged, so git check-attr can read its .gitattributes."""
    for path, text in files.items():
        os.makedirs(os.path.join(d, os.path.dirname(path)) or d, exist_ok=True)
        with open(os.path.join(d, path), "w") as fh:
            fh.write(text)
    subprocess.run(["git", "init", "-q"], cwd=d, check=True)
    subprocess.run(["git", "add", "-A"], cwd=d, check=True)


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

    def test_suffix_conventions_of_test_frameworks(self):
        for path in ("com/example/FooTest.java", "com/example/FooTests.java", "src/FooTest.kt", "src/FooSpec.scala", "src/AppTests.cs",
                     "app/models/user_spec.rb", "MyAppTests/UserTests.swift", "MyAppUITests/LaunchTests.swift", "MyAppTests/Mocks/Service.swift",
                     "src/ParserSpec.hs", "src/ParserSpec.lhs", "src/Vault.t.sol", "rtl/tb_counter.v", "rtl/counter_tb.sv", "rtl/fifo_tb.vhdl", "tb_top.v"):
            self.assertTrue(filetypes.is_test_path(path), path)
        for path in ("com/example/Contest.java", "src/requests/client.py", "src/TestHelper.sol", "src/Latest.kt", "rtl/tbench.v",
                     "rtl/outbound.v", "src/spec_writer.rb", "lib/Spec.hs"):   # case-sensitive: contest is not a Test, requests/ is not a Tests/ dir
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
                     "src/fixture/a.txt", "pkg/testdata/creds.yaml", "demo/x.py", "demos/x.py", "config/generate/rules/slack.go",
                     "src/Illuminate/Auth/Console/stubs/login.request.stub", "stubs/model.stub", "resources/views/mail.stub"):   # a stub is a template
            self.assertTrue(filetypes.is_sample_path(path), path)
        for path in ("app/settings.py", "examplesite/app.py", "src/rulesets/a.go", "sampler/x.py", "config/betterleaks.toml", "src/stubby.py",
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

    def test_credential_shaped_file_names(self):
        for path in (".env", ".env.production", "app/.env.local", ".env.production.local", ".netrc", "home/_netrc", ".pypirc", ".dockercfg",
                     "deploy/id_rsa", "id_ed25519", ".ssh/config", "ops/.ssh/known_hosts", ".ENV"):
            self.assertTrue(filetypes.is_credential_path(path), path)
        for path in (".env.example", ".env.sample", "app/.env.template", ".env.dist", "deploy/id_rsa.pub", "prod.env", "src/env.py",
                     "fixtures/.env", "tests/.netrc", "examples/id_rsa", ".npmrc", "server.pem", "keys/app.key"):
            self.assertFalse(filetypes.is_credential_path(path), path)
        self.assertEqual(filetypes.credential_files(["b/.env", "a.py", ".netrc"]), [".netrc", "b/.env"])

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
                "internal/js/renderkatex.bundle.js": "var a=1;\n",   # a bundle, a minified file or a source map is a build output by name
                "static/app.min.css": "a{b:c}\n",
                "static/app.js.map": "{}\n",
                "src/Foundation/resources/renderer/dist/scripts.js": "var e=1;\n",   # a dist/ directory is build output by name
                "src/distance.py": "x = 1\n",
                "out/report.txt": "plain\n",                # attributed at the root
                "pkg/gen/a.txt": "plain\n",                 # attributed by a nested .gitattributes, which git honours
                "pkg/other.txt": "plain\n",
                ".gitattributes": "* text=auto\nout/* linguist-generated=true\n",
                "pkg/.gitattributes": "gen/*.txt linguist-generated\n",
            }
            git_repo(d, files)
            found = filetypes.generated_files(d, sorted(files))
        self.assertEqual(found, ["dist/bundle.js", "gen/schema.py", "internal/js/renderkatex.bundle.js", "lib/config-validator.js",
                                 "out/report.txt", "pb/api.pb.go", "pkg/gen/a.txt",
                                 "src/Foundation/resources/renderer/dist/scripts.js", "static/app.js.map", "static/app.min.css"])

    def test_attributes_come_from_git_and_a_plain_directory_has_none(self):
        with tempfile.TemporaryDirectory() as d:
            git_repo(d, {"third/lib.js": "x\n", "main.go": "y\n", ".gitattributes": "third/** linguist-vendored\n"})
            self.assertEqual(filetypes.attributes(d, ["third/lib.js", "main.go"]), {"third/lib.js": {"linguist-vendored"}})
            self.assertEqual(filetypes.attributes(d, []), {})
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(filetypes.attributes(d, ["a.py"]), {}, "no repository: nothing is attributed, nothing fails")

    def test_linguist_vendored_paths_join_the_licence_found_directories(self):
        with tempfile.TemporaryDirectory() as d:
            files = {
                "LICENSE": "MIT License\n\nCopyright (c) 2012-2023 Jukka Lehtosalo and contributors\n",
                "mypy/typeshed/LICENSE": "Apache License\nVersion 2.0\n\"Licensor\" shall mean the copyright owner or entity\n",
                "mypy/checker.py": "x = 1\n",
                "third/lib.js": "x\n",
                ".gitattributes": "third/** linguist-vendored\n",
            }
            git_repo(d, files)
            found = filetypes.vendored_paths(d, sorted(files))
        self.assertEqual(found, ["mypy/typeshed/", "third/lib.js"], "a directory by licence ends in /, a file by attribute does not")
        self.assertTrue(filetypes.is_vendored("mypy/typeshed/stdlib/_hashlib.pyi", found))
        self.assertTrue(filetypes.is_vendored("third/lib.js", found))
        self.assertFalse(filetypes.is_vendored("third/lib.js2", found), "a file entry matches exactly, not as a prefix")
        self.assertFalse(filetypes.is_vendored("mypy/checker.py", found))

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
            found = filetypes.vendored_paths(d, sorted(files))
        self.assertEqual(found, ["mypy/typeshed/", "mypyc/external/googletest/"])
        self.assertTrue(filetypes.is_vendored("mypy/typeshed/stdlib/_hashlib.pyi", found))
        self.assertFalse(filetypes.is_vendored("mypy/checker.py", found))
        self.assertTrue(filetypes.is_vendored("deps/lua/a.c", found), "the name rule still applies")

    def test_no_root_licence_means_no_vendored_dirs_by_licence(self):
        with tempfile.TemporaryDirectory() as d:
            os.makedirs(os.path.join(d, "lib", "x"))
            with open(os.path.join(d, "lib", "x", "LICENSE"), "w") as fh:
                fh.write("Copyright 2008, Google Inc.\n")
            self.assertEqual(filetypes.vendored_paths(d, ["lib/x/LICENSE"]), [], "nothing to compare against")

    def test_is_vendored_matches_a_large_file_list_exactly_and_a_directory_by_prefix(self):
        # linguist-vendored puts one entry per file, so a real run's list can run into the thousands;
        # this pins correctness (exact file match, prefix directory match), not timing.
        files = tuple(f"libs/pkg{i}/mod.js" for i in range(5000))
        dirs = files + ("mypy/typeshed/",)
        self.assertTrue(filetypes.is_vendored("libs/pkg2500/mod.js", dirs), "a file entry among 5,000, matched exactly")
        self.assertFalse(filetypes.is_vendored("libs/pkg2500/mod.js2", dirs), "a file entry matches exactly, not as a prefix")
        self.assertTrue(filetypes.is_vendored("mypy/typeshed/stdlib/_hashlib.pyi", dirs), "a directory entry, matched by prefix")
        self.assertFalse(filetypes.is_vendored("mypy/checker.py", dirs))

    def test_vendored_trees(self):
        for path in ("vendor/github.com/x/y.go", "web/node_modules/a/index.js", "third_party/z/a.c", "thirdparty/a.c", "_vendor/a.py",
                     "external/lib/a.cpp", "requests/packages/urllib3/a.py", "pip/_vendor/six.py", "botocore/vendored/requests/a.py",
                     "deps/lua/src/strbuf.c", "deps/jemalloc/Makefile", ".yarn/releases/yarn-4.18.0.cjs", ".yarn/plugins/x.cjs"):
            self.assertTrue(filetypes.is_vendor_path(path), path)
        for path in ("vendors.py", "src/vendoring/a.py", "node/a.js", "externals.txt", "app/main.go",
                     "packages/runtime-core/src/renderer.ts", "packages-private/x.ts"):   # a monorepo's own packages/ at the root
            self.assertFalse(filetypes.is_vendor_path(path), path)


if __name__ == "__main__":
    unittest.main()


class HeaderVendoring(unittest.TestCase):
    def test_a_directory_whose_file_headers_name_somebody_else(self):
        with tempfile.TemporaryDirectory() as d:
            apache_root = 'Apache License\nVersion 2.0\n(c) You must retain, in the Source form of any Derivative Works\nCopyright [yyyy] [name of copyright owner]\n'
            files = {"LICENSE": apache_root,
                     "src/py/LICENSE": 'Licensed under the Apache License, Version 2.0 (the "License");\n',   # our own package's notice, naming nobody
                     "src/py/agent.py": "x = 1\n",
                     "lib/lz/a.c": "/*\nCopyright (c) 2015-2016, Apple Inc. All rights reserved.\n*/\nint a;\n",
                     "lib/lz/b.c": "/*\nCopyright (c) 2015-2016, Apple Inc. All rights reserved.\n*/\nint b;\n",
                     "lib/lz/c.h": "/*\nCopyright (c) 2015-2016, Apple Inc.\n*/\n",
                     "tools/x.py": "# Copyright (C) 2019 Ann Author\nx = 1\n",
                     "tools/y.py": "# Copyright (C) 2020 Ann Author\ny = 1\n",
                     **{f"core/m{i}.c": "int m;\n" for i in range(30)}}
            git_repo(d, files)
            env = dict(os.environ, GIT_CONFIG_GLOBAL="/dev/null", GIT_CONFIG_SYSTEM="/dev/null", GIT_AUTHOR_NAME="Ann Author", GIT_AUTHOR_EMAIL="ann@x",
                       GIT_COMMITTER_NAME="Ann Author", GIT_COMMITTER_EMAIL="ann@x")
            subprocess.run(["git", "commit", "-q", "-m", "start"], cwd=d, check=True, env=env)
            found = filetypes.vendored_paths(d, sorted(files))
        self.assertEqual(found, ["lib/lz/"], "a root template names nobody, so the unnamed package licence is not a stranger's; "
                                             "Ann Author commits here, so her headers are ours")


class DocsAndExercises(unittest.TestCase):
    def test_a_projectdocs_directory_and_exercise_files(self):
        self.assertTrue(filetypes.is_doc_path("GhidraDocs/GhidraClass/Intro.html"))
        self.assertFalse(filetypes.is_sample_path("GhidraDocs/GhidraClass/ExerciseFiles/Advanced/animals"), "ExerciseFiles was one repository's name; exercises/ is the convention")
        self.assertTrue(filetypes.is_sample_path("course/exercises/1/a.py"))
        self.assertFalse(filetypes.is_doc_path("src/Docsify/a.js"))
        self.assertFalse(filetypes.is_sample_path("GPL/DMG/data/os/win_x86_32/llio_amd64.dll"))


class DeepGeneratedMarkers(unittest.TestCase):
    LICENCE = "".join(f"// licence line {i}\n" for i in range(14))

    def test_a_tools_banner_below_a_licence_header(self):
        self.assertTrue(filetypes.says_generated(self.LICENCE + "/* A Bison parser, made by GNU Bison 3.7.4.  */\n"))
        self.assertTrue(filetypes.says_generated(self.LICENCE + "/* A lexical scanner generated by flex */\n"))
        self.assertTrue(filetypes.says_generated(self.LICENCE + "/* This file is generated by a shell script.  DO NOT EDIT! */\n"))
        self.assertTrue(filetypes.says_generated(self.LICENCE + "<!-- This file was generated using the following file: -->\n"))

    def test_comments_that_mention_generated_code_say_nothing_about_the_file(self):
        for line in ("// TODO Auto-generated method stub", "* Do not edit the code below.", "/** A bridge method, generated by the compiler. */",
                     "/* To distinguish the assembly code generated by compiler */", "// Modifications made by John Smith",
                     '//----START "DO NOT MODIFY" SECTION----', "# a parent's auto-generated pk"):
            self.assertFalse(filetypes.says_generated(self.LICENCE + line + "\n"), line)
        self.assertTrue(filetypes.says_generated("# auto-generated\n"), "the first five lines keep the looser markers")

    def test_the_generator_is_not_its_own_output(self):
        text = self.LICENCE + "/* This source code is generated by optiontable.pl - DO NOT EDIT BY HAND */\n"
        self.assertFalse(filetypes.says_generated(text, "optiontable.pl"))
        self.assertTrue(filetypes.says_generated(text, "easyoptions.c"))


class NoticeShapes(unittest.TestCase):
    def test_a_gnu_notice_takes_its_holder_from_the_next_line(self):
        text = "   Copyright (C) 1999, 2000, 2001, 2002, 2003\n   Free Software Foundation, Inc.\n"
        self.assertEqual(filetypes._holders(text), {"free", "software", "foundation"})

    def test_spdx_copyright_text_is_a_notice(self):
        self.assertEqual(filetypes._holders("// SPDX-FileCopyrightText: Jane Roe <jane@example.org>\n"), {"jane", "roe", "example", "org"})

    def test_reuse_declarations_mark_somebody_elses_directory(self):
        with tempfile.TemporaryDirectory() as d:
            files = {"LICENSE": "Copyright (c) 2020 Acme Corp\n", "REUSE.toml": 'version = 1\n\n[[annotations]]\npath = ["third/zlib/**"]\nSPDX-FileCopyrightText = "1995 Jean-loup Gailly and Mark Adler"\n\n[[annotations]]\npath = "src/**"\nSPDX-FileCopyrightText = "2020 Acme Corp"\n',
                     ".reuse/dep5": "Format: https://www.debian.org/doc/packaging-manuals/copyright-format/1.0/\n\nFiles: lib/json/*\nCopyright: 2013 Niels Lohmann\nLicense: MIT\n",
                     "third/zlib/a.c": "int a;\n", "lib/json/j.h": "int j;\n", "src/m.c": "int m;\n", **{f"src/f{i}.c": "int f;\n" for i in range(20)}}
            git_repo(d, files)
            self.assertEqual(sorted(filetypes.reuse_annotations(d, sorted(files))), [("lib/json/", {"niels", "lohmann"}), ("src/", {"acme", "corp"}), ("third/zlib/", {"jean", "loup", "gailly", "mark", "adler"})])
            found = filetypes.vendored_paths(d, sorted(files))
        self.assertIn("third/zlib/", found)
        self.assertIn("lib/json/", found)
        self.assertNotIn("src/", found, "the root licence's holder")

    def test_exercise_files_are_no_longer_a_sample_directory_by_their_own_name(self):
        self.assertFalse(filetypes.is_sample_path("GhidraClass/ExerciseFiles/Advanced/animals"))
        self.assertTrue(filetypes.is_sample_path("course/exercises/1/a.py"))

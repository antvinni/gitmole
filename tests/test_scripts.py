"""Source by shape: a tracked file with mode 100755 and an interpreter line is code, whatever its name."""
import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest

from gitmole import blame, classify, cli, filetypes, hygiene, load, maat, structure

try:
    from gitmole import functions
except ImportError:   # lizard is an ordinary dependency, but a checkout without it still runs the rest
    functions = None

HAVE = structure.available()
ENV = dict(os.environ, GIT_CONFIG_GLOBAL="/dev/null", GIT_CONFIG_SYSTEM="/dev/null",
           GIT_AUTHOR_NAME="Ann", GIT_AUTHOR_EMAIL="a@x", GIT_COMMITTER_NAME="Ann", GIT_COMMITTER_EMAIL="a@x")

HOOK = "#!/usr/bin/env bash\nset -e\necho start\n"
TOOL = "#!/usr/bin/env python3\nimport sys\n\n\ndef main(argv):\n    if argv:\n        return 1\n    return 0\n\n\nsys.exit(main(sys.argv[1:]))\n"


def git(d, *args, **kw):
    return subprocess.run(["git", *args], cwd=d, check=True, capture_output=True, env=ENV, **kw)


def make_repo(d, files: dict, executable=()):
    """A repository with one commit holding `files` (path -> text or bytes); `executable` are committed 100755.
    The mode is set in the index, so the test does not depend on the filesystem keeping it."""
    git(d, "init", "-q")
    for path, content in files.items():
        full = os.path.join(d, path)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "wb") as fh:
            fh.write(content if isinstance(content, bytes) else content.encode())
    git(d, "add", "-A")
    for path in executable:
        git(d, "update-index", "--chmod=+x", path)
    git(d, "commit", "-q", "-m", "one")


class Interpreter(unittest.TestCase):
    def test_the_basename_of_the_interpreter_without_its_version(self):
        for line, want in ((b"#!/bin/sh\n", "sh"), (b"#! /bin/bash -e\n", "bash"), (b"#!/usr/bin/python3.11\n", "python"),
                           (b"#!/usr/local/bin/perl5 -w\n", "perl"), (b"#!/usr/bin/ruby2.7", "ruby"), (b"#!/opt/Tools/Node\n", "node")):
            self.assertEqual(filetypes.interpreter(line), want, line)

    def test_env_hands_over_to_its_first_argument_that_is_a_command(self):
        self.assertEqual(filetypes.interpreter(b"#!/usr/bin/env python3\n"), "python")
        self.assertEqual(filetypes.interpreter(b"#!/usr/bin/env -S node --no-warnings\n"), "node")
        self.assertEqual(filetypes.interpreter(b"#!/usr/bin/env LC_ALL=C /usr/bin/perl\n"), "perl")
        self.assertIsNone(filetypes.interpreter(b"#!/usr/bin/env\n"), "env with nothing to run names nothing")

    def test_only_an_interpreter_line_at_the_first_byte_counts(self):
        for head in (b"", b"# comment\n", b"\n#!/bin/sh\n", b"#!\n", b"\x7fELF\x02\x01", b"#!   \nrest"):
            self.assertIsNone(filetypes.interpreter(head), head)

    def test_only_the_first_line_is_read(self):
        self.assertEqual(filetypes.interpreter(b"#!/bin/sh\nexec python3 \"$0\"\n"), "sh")

    def test_the_file_type_is_the_default_list_s_key_or_a_plain_script(self):
        self.assertEqual(filetypes.script_key(b"#!/usr/bin/env python3\n"), "py")
        self.assertEqual(filetypes.script_key(b"#!/bin/dash\n"), "sh")
        self.assertEqual(filetypes.script_key(b"#!/usr/bin/env node\n"), "js")
        self.assertEqual(filetypes.script_key(b"#!/usr/bin/tclsh\n"), filetypes.SCRIPT, "an interpreter the table does not list is still a script")
        self.assertIsNone(filetypes.script_key(b"plain text\n"))

    def test_every_listed_interpreter_maps_to_a_default_type(self):
        self.assertFalse({k for k in filetypes.INTERPRETERS.values() if k not in filetypes.DEFAULT})


class Scripts(unittest.TestCase):
    FILES = {"hooks/session-start": HOOK, "bin/tool": TOOL, "bin/notes": "just words\n", "docs/howto": HOOK,
             "run.sh": "#!/bin/sh\necho hi\n", "bin/blob": b"#!\x00\x01\x02binary\x00", "bin/elf": b"\x7fELF\x00\x00\x00",
             "gen/table.tcl": "#!/usr/bin/tclsh\nputs hi\n", "README.md": "hi\n"}
    EXECUTABLE = ("hooks/session-start", "bin/tool", "bin/notes", "run.sh", "bin/blob", "bin/elf", "gen/table.tcl")

    def test_mode_and_interpreter_line_together_and_nothing_an_extension_already_names(self):
        with tempfile.TemporaryDirectory() as d:
            make_repo(d, self.FILES, self.EXECUTABLE)
            found = filetypes.scripts(d)
        self.assertEqual(found, {"bin/tool": "py", "gen/table.tcl": "script", "hooks/session-start": "bash"},
                         "not docs/howto (an interpreter line, mode 100644), not bin/notes (executable, no interpreter line), "
                         "not run.sh (source by its extension already), not the binaries")

    def test_among_limits_the_blobs_read_to_the_caller_s_text_files(self):
        with tempfile.TemporaryDirectory() as d:
            make_repo(d, self.FILES, self.EXECUTABLE)
            self.assertEqual(filetypes.scripts(d, among=["bin/tool", "README.md"]), {"bin/tool": "py"})
            self.assertEqual(filetypes.scripts(d, among=[]), {})

    def test_the_mode_and_the_bytes_are_the_commit_s_not_the_checkout_s(self):
        with tempfile.TemporaryDirectory() as d:
            make_repo(d, {"hooks/start": HOOK, "bin/later": HOOK}, ["hooks/start"])
            os.chmod(os.path.join(d, "hooks/start"), 0o644)            # the checkout lost the bit
            os.chmod(os.path.join(d, "bin/later"), 0o755)              # an uncommitted chmod
            with open(os.path.join(d, "hooks/start"), "w") as fh:
                fh.write("no longer a script\n")                       # an uncommitted edit
            self.assertEqual(filetypes.scripts(d), {"hooks/start": "bash"})

    def test_another_commit_s_tree_is_read_as_it_was(self):
        with tempfile.TemporaryDirectory() as d:
            make_repo(d, {"bin/old": HOOK, "a.py": "x = 1\n"}, ["bin/old"])
            first = git(d, "rev-parse", "HEAD").stdout.decode().strip()
            git(d, "rm", "-q", "-f", "bin/old")
            git(d, "commit", "-q", "-m", "two")
            self.assertEqual(filetypes.scripts(d), {})
            self.assertEqual(filetypes.scripts(d, first), {"bin/old": "bash"}, "the backtest's cut-off: a script deleted since was one then")

    def test_a_large_blob_is_read_past_without_losing_the_next_one(self):
        with tempfile.TemporaryDirectory() as d:
            make_repo(d, {"a-big": "#!/bin/sh\n" + "echo x\n" * 400_000, "b-small": TOOL}, ["a-big", "b-small"])
            self.assertEqual(filetypes.scripts(d), {"a-big": "sh", "b-small": "py"})

    def test_no_commit_or_no_repository_finds_none(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(filetypes.scripts(d), {})
            git(d, "init", "-q")
            self.assertEqual(filetypes.scripts(d), {})


class Types(unittest.TestCase):
    FOUND = {"hooks/session-start": "bash", "bin/tool": "py", "gen/table": "script"}

    def test_under_the_default_list_every_script_is_source(self):
        types = filetypes.with_scripts(filetypes.DEFAULT, self.FOUND)
        for path in self.FOUND:
            self.assertTrue(filetypes.matches(path, types), path)
        self.assertTrue(filetypes.matches("a.py", types))
        self.assertTrue(filetypes.matches("Makefile", types), "the default list's names still count once it carries scripts")
        self.assertFalse(filetypes.matches("hooks/other", types), "a path, not a name: the same basename elsewhere is not a script")
        self.assertFalse(filetypes.matches("README.md", types))

    def test_under_file_types_only_the_scripts_of_a_listed_type(self):
        types = filetypes.with_scripts(filetypes.parse("py"), self.FOUND)
        self.assertTrue(filetypes.matches("bin/tool", types))
        self.assertFalse(filetypes.matches("hooks/session-start", types))
        self.assertFalse(filetypes.matches("Makefile", types))
        self.assertEqual(filetypes.with_scripts(filetypes.parse("go"), self.FOUND), {"go"}, "none of that type: the set as it was")

    def test_no_filter_and_no_scripts_are_left_as_they_are(self):
        self.assertIsNone(filetypes.with_scripts(None, self.FOUND))
        self.assertIs(filetypes.with_scripts(filetypes.DEFAULT, {}), filetypes.DEFAULT)
        self.assertIs(filetypes.with_scripts(filetypes.DEFAULT, None), filetypes.DEFAULT)

    def test_a_run_s_meta_gives_its_types(self):
        self.assertTrue(filetypes.matches("bin/tool", filetypes.for_meta({"file_types": None, "scripts": self.FOUND})))
        self.assertFalse(filetypes.matches("bin/tool", filetypes.for_meta({"file_types": None})), "a run from before the record: by extension, as it was")
        self.assertIs(filetypes.for_meta({"file_types": None}), filetypes.DEFAULT)
        self.assertIsNone(filetypes.for_meta({}, unrecorded=None))
        self.assertIsNone(filetypes.for_meta({"file_types": "all", "scripts": self.FOUND}))

    def test_the_file_type_listing_counts_a_script_as_code_under_its_own_name(self):
        with tempfile.TemporaryDirectory() as d:
            make_repo(d, {"hooks/session-start": HOOK, "hooks/session-end": "words\n", "a.py": "x = 1\n"}, ["hooks/session-start"])
            rows = filetypes.discover(d, filetypes.with_scripts(filetypes.DEFAULT, filetypes.scripts(d)))
        self.assertEqual(rows, [("py", 1, True), ("session-end", 1, False), ("session-start", 1, True)])


class Carried(unittest.TestCase):
    """Every place the source-type filter applies reads the same list."""

    LOG = ("--aaa1111--2026-03-01T10:00:00+00:00--Ann--rename the hook\n0\t0\thooks/{session-start.sh => session-start}\n\n"
           "--bbb2222--2026-02-01T10:00:00+00:00--Ann--fix the hook\n3\t1\thooks/session-start.sh\n1\t0\tREADME.md\n\n"
           "--ccc3333--2026-03-05T10:00:00+00:00--Bob--tune\n2\t2\thooks/session-start\n4\t0\tbin/notes\n")

    def test_the_change_log_keeps_a_script_s_revisions(self):
        types = filetypes.with_scripts(filetypes.DEFAULT, {"hooks/session-start": "bash"})
        files = [p for c in maat.parse_log(self.LOG, types=types) for p, _, _ in c["files"]]
        self.assertEqual(files, ["hooks/session-start", "hooks/session-start.sh", "hooks/session-start"],
                         "the rename commit and what follows are the script's; the commits before it stay with the old name, as for any renamed file")
        self.assertEqual([p for c in maat.parse_log(self.LOG, types=filetypes.DEFAULT) for p, _, _ in c["files"]], ["hooks/session-start.sh"])

    def test_the_change_analysis_step_reads_the_scripts_from_meta(self):
        with tempfile.TemporaryDirectory() as d:
            with open(os.path.join(d, "log.txt"), "w") as fh:
                fh.write(self.LOG)
            with open(os.path.join(d, "meta.json"), "w") as fh:
                json.dump({"aliases": {}, "scripts": {"hooks/session-start": "bash"}}, fh)
            subprocess.run([sys.executable, maat.__file__, os.path.join(d, "log.txt"), d, "--aliases", os.path.join(d, "meta.json"), "--now", "2026-04-01"],
                           check=True, capture_output=True)
            revisions = {r["entity"]: r["n-revs"] for r in load.parse_maat_csv(load._read(d, "maat-revisions.csv"))}
        self.assertEqual(revisions, {"hooks/session-start": 2, "hooks/session-start.sh": 1})

    def test_blame_lists_a_script_among_the_code_files(self):
        with tempfile.TemporaryDirectory() as d:
            make_repo(d, {"hooks/session-start": HOOK, "a.py": "x = 1\n", "README.md": "hi\n"}, ["hooks/session-start"])
            types = filetypes.with_scripts(filetypes.DEFAULT, filetypes.scripts(d))
            self.assertEqual(blame.code_files(d), ["a.py"])
            self.assertEqual(blame.code_files(d, types=types), ["a.py", "hooks/session-start"])

    def test_the_size_table_and_the_classifier_score_it(self):
        scc = json.dumps([{"Name": "BASH", "Count": 1, "Code": 25, "Comment": 0, "Blank": 0, "Complexity": 1,
                           "Files": [{"Location": "hooks/session-start", "Code": 25, "Complexity": 1}]},
                          {"Name": "License", "Count": 1, "Code": 17, "Comment": 0, "Blank": 0, "Complexity": 0,
                           "Files": [{"Location": "LICENSE", "Code": 17, "Complexity": 0}]}])
        meta = {"file_types": None, "scripts": {"hooks/session-start": "bash"}}
        size = load.parse_scc(scc, filetypes.for_meta(meta, unrecorded=None))
        self.assertEqual(sorted(size["files"]), ["hooks/session-start"])
        c = classify.Classifier({"meta": meta, "size": size})
        self.assertIsNone(c.reason("hooks/session-start"), "in the scored pool")
        self.assertEqual(c.reason("LICENSE"), "not a source type")
        before = classify.Classifier({"meta": {"file_types": None}, "size": load.parse_scc(scc, filetypes.DEFAULT)})
        self.assertEqual(before.reason("hooks/session-start"), "not a source type", "a run that recorded no scripts reads as it did")

    def test_a_script_with_no_scc_row_is_not_counted_rather_than_scored(self):
        meta = {"file_types": None, "scripts": {"gen/table": "script"}}
        c = classify.Classifier({"meta": meta, "size": {"files": {"a.py": {"code": 1}}}})
        self.assertEqual(classify.coverage(c, ["a.py", "gen/table"]), {"scored": 1, "not counted by scc": 1})

    def test_trojan_source_reads_a_script(self):
        bidi = "#!/bin/sh\n# ‮ hidden\necho hi\n"
        with tempfile.TemporaryDirectory() as d:
            make_repo(d, {"hooks/start": bidi, "a.py": "x = 1\n"}, ["hooks/start"])
            self.assertEqual(hygiene.trojan_source(d)["bidi_count"], 0)
            found = hygiene.trojan_source(d, types=filetypes.with_scripts(filetypes.DEFAULT, filetypes.scripts(d)))
        self.assertEqual([b["file"] for b in found["bidi"]], ["hooks/start"])

    @unittest.skipUnless(functions is not None, "lizard is not installed")
    def test_the_function_step_reads_a_script_in_its_interpreter_s_language(self):
        with tempfile.TemporaryDirectory() as d:
            make_repo(d, {"bin/tool": TOOL, "hooks/session-start": HOOK, "a.py": "def f():\n    return 1\n"}, ["bin/tool", "hooks/session-start"])
            out = os.path.join(d, "out")
            os.makedirs(out)
            with open(os.path.join(out, "meta.json"), "w") as fh:
                json.dump({"scripts": filetypes.scripts(d)}, fh)
            self.assertEqual(functions.main([d, out, "--procs", "1"]), 0)
            rows = load.parse_functions(load._read(out, "functions.csv"))
        self.assertEqual([(r["file"], r["function"], r["ccn"]) for r in rows], [("a.py", "f", 1), ("bin/tool", "main", 2)],
                         "under its own path; the shell hook has no lizard reader and is left out")

    @unittest.skipUnless(functions is not None, "lizard is not installed")
    def test_the_function_step_without_a_record_reads_by_extension(self):
        with tempfile.TemporaryDirectory() as d:
            make_repo(d, {"bin/tool": TOOL, "a.py": "def f():\n    return 1\n"}, ["bin/tool"])
            out = os.path.join(d, "out")
            os.makedirs(out)
            self.assertEqual(functions.main([d, out, "--procs", "1"]), 0)
            rows = load.parse_functions(load._read(out, "functions.csv"))
        self.assertEqual([r["file"] for r in rows], ["a.py"])

    @unittest.skipUnless(HAVE, "the tree-sitter grammars need Python 3.10 or newer")
    def test_the_structure_step_parses_a_script_and_takes_it_for_an_entry_point(self):
        files = {"bin/tool": "#!/usr/bin/env python3\nfrom pkg import core\n\ncore.run()\n", "pkg/__init__.py": "", "pkg/core.py": "def run():\n    return 1\n",
                 **{f"pkg/m{i}.py": f"from pkg import core\nX = {i}\n" for i in range(12)}, "hooks/session-start": HOOK}
        with tempfile.TemporaryDirectory() as d:
            make_repo(d, files, ["bin/tool", "hooks/session-start"])
            plain = structure.collect(d, procs=1)
            found = structure.collect(d, procs=1, scripts=filetypes.scripts(d))
        self.assertNotIn("bin/tool", plain["files"])
        self.assertEqual(found["files"]["bin/tool"]["language"], "python")
        self.assertEqual(found["files"]["bin/tool"]["imports"], ["pkg/core.py"])
        self.assertNotIn("hooks/session-start", found["files"], "no grammar for shell: left out, not counted missing")
        self.assertNotIn("bin/tool", found["unreferenced"], "nothing imports an executable: it is started by name")
        self.assertEqual(found["missing_grammars"], {})


class Run(unittest.TestCase):
    _stub_planner = staticmethod(lambda repo, o, branch="HEAD", **kw: [{"name": "q", "argv": ["true"], "stdout": None, "deps": []}])

    def _run(self, files, executable):
        from rich.console import Console
        with tempfile.TemporaryDirectory() as d:
            repo, out = os.path.join(d, "r"), os.path.join(d, "out")
            os.makedirs(repo)
            make_repo(repo, files, executable)
            seen = {}

            def estimator(repo, interval, **kw):
                seen["types"] = kw.get("types")
                return {"files": 1, "samples": 1, "blames": 1, "seconds": 0.0}
            with contextlib.redirect_stderr(io.StringIO()):
                rc = cli.main([repo, "--out", out], console=Console(file=io.StringIO()), tool_check=lambda **kw: [], planner=self._stub_planner,
                              estimator=estimator)
            with open(os.path.join(out, "meta.json")) as fh:
                return rc, json.load(fh), seen["types"]

    def test_a_run_records_its_scripts_and_scores_them(self):
        rc, meta, types = self._run({"hooks/session-start": HOOK, "src/a.py": "x = 1\n", "README.md": "hi\n", "bin/notes": "words\n"},
                                    ["hooks/session-start", "bin/notes"])
        self.assertEqual(rc, 0)
        self.assertEqual(meta["scripts"], {"hooks/session-start": "bash"})
        self.assertEqual(meta["coverage"], {"scored": 2, "not a source type": 2})
        self.assertTrue(filetypes.matches("hooks/session-start", types), "the blame estimate counts the script among the code files")

    def test_a_run_without_scripts_writes_the_meta_it_always_did(self):
        rc, meta, types = self._run({"src/a.py": "x = 1\n", "run.sh": "#!/bin/sh\n"}, ["run.sh"])
        self.assertEqual(rc, 0)
        self.assertNotIn("scripts", meta)
        self.assertIs(types, filetypes.DEFAULT)


if __name__ == "__main__":
    unittest.main()

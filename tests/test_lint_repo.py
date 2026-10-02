"""bin/lint-repo: the data and shell checks of CI's lint job."""
import importlib.machinery
import importlib.util
import io
import os
import subprocess
import tempfile
import unittest

PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "bin", "lint-repo")

try:
    import yaml  # noqa: F401  (only its presence is asked: the test jobs do not install it, the lint job does)
    HAVE_YAML = True
except ImportError:
    HAVE_YAML = False


def load():
    loader = importlib.machinery.SourceFileLoader("lint_repo", PATH)
    spec = importlib.util.spec_from_loader("lint_repo", loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


ACTION = """name: demo
runs:
  using: composite
  steps:
    - uses: actions/checkout@0000000000000000000000000000000000000000
    - name: First
      shell: bash
      run: |
        echo "${{ inputs.x }}"
        exit 0
    - name: Second
      shell: python
      run: print(1)
    - shell: bash
      run: echo one line
"""


class Json(unittest.TestCase):
    def setUp(self):
        self.mod = load()

    def test_a_document_parses(self):
        self.assertEqual(self.mod.json_errors('{"a": [1, 2]}\n'), [])

    def test_a_broken_document_names_its_line(self):
        errors = self.mod.json_errors('{\n"a": 1\n"b": 2}\n')
        self.assertEqual([line for line, _ in errors], [3])

    def test_lines_parse_one_by_one(self):
        self.assertEqual(self.mod.jsonl_errors('{"a": 1}\n{"b": 2}\n'), [])
        self.assertEqual(self.mod.jsonl_errors('{"a": 1}\n{"b": 2}'), [])   # no final newline is still two lines

    def test_a_broken_line_and_a_blank_one_are_each_named(self):
        errors = self.mod.jsonl_errors('{"a": 1}\n\n{"b": \n{"c": 3}\n')
        self.assertEqual([line for line, _ in errors], [2, 3])
        self.assertEqual(errors[0][1], "blank line")

    def test_a_pretty_printed_document_is_not_json_lines(self):
        self.assertTrue(self.mod.jsonl_errors('{\n  "a": 1\n}\n'))


class Shebang(unittest.TestCase):
    def test_only_sh_and_bash_count(self):
        mod = load()
        with tempfile.TemporaryDirectory() as tmp:
            for name, first, want in (("a", "#!/bin/sh\n", "sh"), ("b", "#!/usr/bin/env bash\n", "bash"),
                                      ("c", "#!/usr/bin/env python3\n", None), ("d", "no first line\n", None),
                                      ("e", "#! /bin/bash -e\n", "bash")):
                path = os.path.join(tmp, name)
                with open(path, "w") as f:
                    f.write(first)
                self.assertEqual(mod.shebang_shell(path), want, first)


class Data(unittest.TestCase):
    def test_counts_what_it_parsed_and_fails_on_a_broken_tracked_file(self):
        mod = load()
        with tempfile.TemporaryDirectory() as tmp:
            subprocess.run(["git", "init", "-q", tmp], check=True)
            for name, text in (("good.json", "{}\n"), ("bad.json", "{,}\n"), ("rows.jsonl", "1\n2\n"), ("untracked.json", "{")):
                with open(os.path.join(tmp, name), "w") as f:
                    f.write(text)
            subprocess.run(["git", "-C", tmp, "add", "good.json", "bad.json", "rows.jsonl"], check=True)
            out = io.StringIO()
            self.assertEqual(mod.data(tmp, out), 1)
        text = out.getvalue()
        self.assertIn("bad.json:1:", text)
        self.assertNotIn("untracked.json", text)
        self.assertIn("JSON: 2 tracked files parsed", text)
        self.assertIn("JSON Lines: 1 tracked files parsed", text)
        self.assertIn("YAML: 0 tracked files parsed", text)
        self.assertIn("1 files failed", text)

    def test_this_repository_holds_data_files_of_each_kind(self):
        # the lint job's counts are only worth printing if there is something to count
        names = load().tracked()
        for ext in (".json", ".jsonl", ".yml"):
            self.assertTrue(any(n.endswith(ext) for n in names), ext)


@unittest.skipUnless(HAVE_YAML, "PyYAML is not installed")
class Composite(unittest.TestCase):
    def setUp(self):
        self.mod = load()
        self.runs = self.mod.composite_runs(ACTION)

    def test_every_run_block_is_found_with_its_shell(self):
        self.assertEqual([(n, name, shell) for n, name, shell, _ in self.runs],
                         [(2, "First", "bash"), (3, "Second", "python"), (4, "step 4", "bash")])

    def test_a_script_keeps_the_action_files_line_numbers(self):
        lines = self.runs[0][3].split("\n")
        self.assertEqual(lines[9], "exit 0")                      # line 10 of ACTION
        self.assertEqual(self.runs[2][3].split("\n")[14], "echo one line")   # a plain scalar: line 15, its key's line

    def test_an_expression_becomes_underscores_of_its_length(self):
        self.assertEqual(self.runs[0][3].split("\n")[8], 'echo "' + "_" * len("${{ inputs.x }}") + '"')

    def test_an_action_that_is_not_composite_has_no_run_blocks(self):
        self.assertEqual(self.mod.composite_runs("name: x\nruns:\n  using: node20\n  main: index.js\n"), [])

    def test_broken_yaml_names_its_line(self):
        self.assertEqual([line for line, _ in self.mod.yaml_errors("a: [1, 2\nb: 3\n")][0] > 0, True)
        self.assertEqual(self.mod.yaml_errors("a: 1\n---\nb: 2\n"), [])

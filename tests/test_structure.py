import json
import os
import subprocess
import sys
import tempfile
import unittest

from gitmole import structure

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HAVE = structure.available()


def parse(ext: str, code: str) -> dict:
    name, language, _ = structure.grammar(ext)
    return structure.analyse(code.encode(), name, language)


def fn(result: dict, name: str) -> dict:
    return next(f for f in result["functions"] if f["name"] == name)


@unittest.skipUnless(HAVE, "the tree-sitter grammars need Python 3.10 or newer")
class Metrics(unittest.TestCase):
    def test_nesting_cognitive_complexity_and_a_flat_else_if(self):
        r = parse(".py", "def f(x):\n"
                         "    if x:\n"                 # +1
                         "        for i in x:\n"       # +2 (nesting 1)
                         "            while i:\n"      # +3 (nesting 2)
                         "                pass\n"
                         "    elif y:\n"               # +1, flat
                         "        pass\n"
                         "    else:\n"                 # +1, flat
                         "        pass\n"
                         "    return a and b or c\n")  # +1 and, +1 or? one chain: +1
        f = fn(r, "f")
        self.assertEqual(f["nesting"], 3)
        self.assertEqual(f["cognitive"], 1 + 2 + 3 + 1 + 1 + 1)
        self.assertEqual((f["start"], f["end"]), (1, 10))

    def test_bumps_are_separate_chunks_nested_two_deep(self):
        r = parse(".js", "function g(a) {\n"
                         "  if (a) { if (b) { x() } }\n"
                         "  y();\n"
                         "  for (;;) { while (c) { z() } }\n"
                         "  if (d) { w() }\n"
                         "}\n")
        self.assertEqual(fn(r, "g")["bumps"], 2, "two chunks of nested logic; the flat if is not a bump")

    def test_a_condition_with_four_operands_is_complex(self):
        r = parse(".c", "int h(int a) { if (a && b || c && d) { return 1; } if (a && b) { return 2; } return 0; }\n")
        self.assertEqual(fn(r, "h")["complex_conditions"], 1)

    def test_debt_comments_definitions_imports_and_the_main_guard(self):
        r = parse(".py", "import os\nfrom .util import helper\nfrom . import sibling\n\n"
                         "# TODO: split this\nclass A:\n    def m(self):\n        pass  # FIXME later\n\n"
                         "def top():\n    pass\n\n# todo in lower case is prose\n"
                         "if __name__ == \"__main__\":\n    top()\n")
        self.assertEqual([d["tag"] for d in r["debt"]], ["TODO", "FIXME"])
        self.assertEqual(r["debt"][0]["line"], 5)
        self.assertEqual(r["comments"], 3)
        self.assertEqual(r["definitions"], 3, "the class, its method and the top-level function: the god-file count")
        self.assertTrue(r["main"])
        self.assertEqual([list(i) for i in r["imports"]], [["abs", "os"], ["from", ".util", ["helper"]], ["from", ".", ["sibling"]]])

    def test_a_function_without_a_name_takes_the_one_it_is_bound_to(self):
        r = parse(".js", "const handle = async (e) => { if (e) {} };\nclass S { onChange = () => { if (a) {} } }\nconst o = { go: function () {} };\n")
        self.assertEqual(sorted(f["name"] for f in r["functions"]), ["go", "handle", "onChange"])

    def test_the_other_grammars_parse_and_name_their_functions(self):
        cases = {".go": ("package m\nfunc F(x int) int { if x > 1 { for { } }; return 1 }\n", "F"),
                 ".rs": ("fn f(x: i32) -> i32 { if x > 1 { loop {} } 1 }\n", "f"),
                 ".java": ("class K { int m(int x) { if (x > 1) { for (;;) {} } return 1; } }\n", "m"),
                 ".rb": ("def r(x)\n  if x\n    while y\n    end\n  end\nend\n", "r"),
                 ".cs": ("class K { int M(int x) { if (x > 1) { foreach (var a in b) {} } return 1; } }\n", "M"),
                 ".php": ("<?php\nfunction p($x) { if ($x) { foreach ($a as $b) {} } return 1; }\n", "p"),
                 ".ts": ("export function t(x: number): number { if (x) { while (x) {} } return 1 }\n", "t"),
                 ".tsx": ("export function C() { if (a) { for (;;) {} } return <div/> }\n", "C"),
                 ".cpp": ("int cc(int x) { if (x) { for(;;){} } return 0; }\n", "cc")}
        for ext, (code, name) in cases.items():
            self.assertEqual(fn(parse(ext, code), name)["nesting"], 2, ext)


class Resolve(unittest.TestCase):
    def test_python_js_c_and_ruby_imports_resolve_against_the_tree(self):
        files = {"pkg/__init__.py": {"language": "python", "imports": []},
                 "pkg/a.py": {"language": "python", "imports": [["from", ".b", ["x"]], ["abs", "os"], ["from", ".", ["c"]]]},
                 "pkg/b.py": {"language": "python", "imports": [["abs", "pkg.a"]]},
                 "pkg/c.py": {"language": "python", "imports": []},
                 "src/app/main.py": {"language": "python", "imports": [["from", "app.util", ["f"]]]},
                 "src/app/util.py": {"language": "python", "imports": []},
                 "web/index.ts": {"language": "typescript", "imports": [["path", "./lib/x.js"], ["path", "react"], ["path", "./comp"]]},
                 "web/lib/x.ts": {"language": "typescript", "imports": []},
                 "web/comp/index.tsx": {"language": "tsx", "imports": []},
                 "c/main.c": {"language": "c", "imports": [["include", "util.h"], ["include", "missing.h"]]},
                 "c/util.h": {"language": "c", "imports": []},
                 "lib/r.rb": {"language": "ruby", "imports": [["rel", "s"], ["req", "json"]]},
                 "lib/s.rb": {"language": "ruby", "imports": []}}
        edges, resolved = structure.resolve(files)
        self.assertEqual(edges["pkg/a.py"], ["pkg/b.py", "pkg/c.py"], "relative imports, the stdlib left out")
        self.assertEqual(edges["pkg/b.py"], ["pkg/a.py"])
        self.assertEqual(edges["src/app/main.py"], ["src/app/util.py"], "a src/ layout resolves by suffix")
        self.assertEqual(edges["web/index.ts"], ["web/comp/index.tsx", "web/lib/x.ts"], "a .js import of a .ts file, an index file, no node_modules")
        self.assertEqual(edges["c/main.c"], ["c/util.h"])
        self.assertEqual(edges["lib/r.rb"], ["lib/s.rb"], "a gem is not this tree")
        self.assertEqual(resolved["typescript"], 1.0)
        self.assertEqual(resolved["c"], 0.5)

    def test_the_lowest_path_wins_when_several_files_answer_one_module_name(self):
        """django has two json.py under django/, so an import of it has two candidates and the first wins. The
        suffix index was built by walking a set, so which one came first followed the hash seed: two runs of the
        same commit gave different import graphs, and the determinism check caught it at 0.32.0. Under a hundred
        candidates, set order cannot coincide with sorted order by luck."""
        files = {"app/main.py": {"language": "python", "imports": [["abs", "pkg.json"]]}}
        for i in range(100):
            files[f"d{i:03d}/pkg/json.py"] = {"language": "python", "imports": []}
        edges, _ = structure.resolve(files)
        self.assertEqual(edges["app/main.py"], ["d000/pkg/json.py"], "the lowest path, not whichever the set yielded first")


@unittest.skipUnless(HAVE, "the tree-sitter grammars need Python 3.10 or newer")
class Step(unittest.TestCase):
    def test_the_step_writes_structure_json_and_caches_by_blob(self):
        with tempfile.TemporaryDirectory() as d:
            repo, out, cache = os.path.join(d, "repo"), os.path.join(d, "out"), os.path.join(d, "cache")
            for p in (repo, out):
                os.makedirs(p)
            env = dict(os.environ, GIT_CONFIG_GLOBAL="/dev/null", GIT_CONFIG_SYSTEM="/dev/null", GIT_AUTHOR_NAME="A", GIT_AUTHOR_EMAIL="a@x",
                       GIT_COMMITTER_NAME="A", GIT_COMMITTER_EMAIL="a@x", GITMOLE_CACHE=cache, PYTHONPATH=ROOT)
            subprocess.run(["git", "init", "-q"], cwd=repo, check=True, env=env)
            os.makedirs(os.path.join(repo, "pkg"))
            with open(os.path.join(repo, "pkg", "a.py"), "w") as fh:
                fh.write("from . import b\n# TODO: x\ndef f(x):\n    if x:\n        if y:\n            if z:\n                pass\n")
            with open(os.path.join(repo, "pkg", "b.py"), "w") as fh:
                fh.write("def g():\n    pass\n")
            with open(os.path.join(repo, "notes.txt"), "w") as fh:
                fh.write("not code\n")
            subprocess.run(["git", "add", "-A"], cwd=repo, check=True, env=env)
            subprocess.run(["git", "commit", "-q", "-m", "c"], cwd=repo, check=True, env=env)
            for _ in range(2):
                p = subprocess.run([sys.executable, "-m", "gitmole.structure", out, "--procs", "1"], cwd=repo, env=env, capture_output=True, text=True)
                self.assertEqual(p.returncode, 0, p.stderr)
            with open(os.path.join(out, "structure.json")) as fh:
                data = json.load(fh)
        self.assertEqual(data["status"], "run")
        self.assertEqual(data["languages"], {"python": 2})
        self.assertEqual(data["cached"], 2, "the second run parsed nothing")
        self.assertEqual(data["files"]["pkg/a.py"]["imports"], ["pkg/b.py"])
        self.assertEqual(data["files"]["pkg/a.py"]["debt"], 1)
        self.assertEqual(data["files"]["pkg/a.py"]["max_nesting"], 3)
        self.assertEqual([f["name"] for f in data["functions"]], ["f"])


class Blobs(unittest.TestCase):
    def test_a_path_list_far_past_the_argument_limit_still_lists_the_wanted_files(self):
        """Ghidra's 12,000 deep Java paths overflowed `git ls-files -- <paths>` with "Argument list too
        long", and the structure step failed on the repositories it matters most for. git lists the index
        and the paths are matched here, so the list's size no longer reaches a command line."""
        with tempfile.TemporaryDirectory() as d:
            repo = os.path.join(d, "repo")
            os.makedirs(repo)
            env = dict(os.environ, GIT_CONFIG_GLOBAL="/dev/null", GIT_CONFIG_SYSTEM="/dev/null", GIT_AUTHOR_NAME="A",
                       GIT_AUTHOR_EMAIL="a@x", GIT_COMMITTER_NAME="A", GIT_COMMITTER_EMAIL="a@x")
            with open(os.path.join(repo, "a.py"), "w") as fh:
                fh.write("x = 1\n")
            with open(os.path.join(repo, "b.py"), "w") as fh:
                fh.write("y = 2\n")
            subprocess.run(["git", "init", "-q"], cwd=repo, check=True, env=env)
            subprocess.run(["git", "add", "-A"], cwd=repo, check=True, env=env)
            subprocess.run(["git", "commit", "-q", "-m", "c"], cwd=repo, check=True, env=env)
            long_names = [f"src/{'deep/' * 12}module_{i:06d}.py" for i in range(20000)]   # ~2 MB of paths, twice the macOS limit
            blobs = structure._blobs(repo, ["a.py", *long_names])
        self.assertEqual(sorted(blobs), ["a.py"], "the tracked path is found and the absent ones are ignored")
        self.assertEqual(blobs["a.py"][1], b"x = 1\n")


class NotInstalled(unittest.TestCase):
    def test_without_tree_sitter_the_step_says_how_to_install_it(self):
        with tempfile.TemporaryDirectory() as out:
            from unittest.mock import patch
            with patch.object(structure, "available", return_value=False):
                self.assertEqual(structure.main([out]), 0)
            with open(os.path.join(out, "structure.json")) as fh:
                self.assertEqual(json.load(fh), {"status": "not-installed", "install": "the grammars need Python 3.10 or newer; reinstall gitmole on 3.10+"})


if __name__ == "__main__":
    unittest.main()

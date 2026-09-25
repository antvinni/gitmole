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

    def test_imports_that_do_not_run_when_the_file_loads_are_marked_deferred(self):
        # the ways a cycle is broken on purpose: an import inside a function, a type-only import, a dynamic import()
        r = parse(".py", "import a\nfrom typing import TYPE_CHECKING\nif TYPE_CHECKING:\n    from .b import B\n"
                         "def f():\n    from . import c\ntry:\n    import d\nexcept ImportError:\n    pass\n")
        self.assertEqual([i[1] for i in r["imports"]], ["a", "typing", ".b", ".", "d"])
        self.assertEqual(r["deferred"], [2, 3], "TYPE_CHECKING and the function body; a try/except import still runs at load")
        r = parse(".ts", "import type { T } from './t';\nimport { x } from './x';\nexport type { U } from './u';\nimport('./dyn');\n"
                         "function g() { return require('./g'); }\nconst r = require('./r');\n")
        self.assertEqual([i[1] for i in r["imports"]], ["./t", "./x", "./u", "./dyn", "./g", "./r"])
        self.assertEqual(r["deferred"], [0, 2, 3, 4], "import type and export type are erased; import() and a require in a function wait")
        self.assertEqual(parse(".js", "const r = require('./r');\n")["deferred"], [])
        r = parse(".js", "import type {Fiber} from './f';\nimport typeof X from './x';\nimport {y} from './y';\nexport type {Q} from './q';\n")
        self.assertEqual(r["deferred"], [0, 1, 3], "Flow's import type and import typeof, which the JavaScript grammar reads as an error node")

    def test_the_else_of_type_checking_and_a_function_called_where_it_is_written_run_at_load(self):
        """The common shim `if TYPE_CHECKING: from .a import A / else: from .b import B` loads .b; an elif's body
        runs; `if not TYPE_CHECKING:` is the branch that runs; an aliased constant is still the constant; and a
        require inside `(function () {...})()` runs when the file loads, so none of these is deferred."""
        r = parse(".py", "from typing import TYPE_CHECKING\nif TYPE_CHECKING:\n    from .a import A\nelse:\n    from .b import B\n"
                         "if TYPE_CHECKING:\n    pass\nelif True:\n    from .e import E\nif not TYPE_CHECKING:\n    from .r import R\n")
        self.assertEqual([i[1] for i in r["imports"]], ["typing", ".a", ".b", ".e", ".r"])
        self.assertEqual(r["deferred"], [1], "only the import in the if's own body")
        r = parse(".py", "import typing as t\nif t.TYPE_CHECKING:\n    from .a import A\nfrom typing import TYPE_CHECKING as TC\nif TC:\n    from .c import C\n")
        self.assertEqual(r["deferred"], [1], "an attribute of an aliased module is the constant; an aliased name is not recognised, and says so here")
        r = parse(".py", "import sys, typing\nif not typing.TYPE_CHECKING:\n    from .n import N\n"
                         "if sys.version_info >= (3, 11) or typing.TYPE_CHECKING:\n    from .o import O\nif (TYPE_CHECKING):\n    from .p import P\n")
        self.assertEqual([i[1] for i in r["imports"]], ["sys", "typing", ".n", ".o", ".p"])
        self.assertEqual(r["deferred"], [4], "a negated or combined condition can be true at run time; only the constant alone, "
                                             "brackets or not, is the branch that never runs")
        r = parse(".js", "(function () { require('./iife'); })();\n(() => { require('./arrow'); })();\nfunction g() { require('./g'); }\n"
                         "const h = function () { require('./h'); };\n")
        self.assertEqual([i[1] for i in r["imports"]], ["./iife", "./arrow", "./g", "./h"])
        self.assertEqual(r["deferred"], [2, 3], "the two invoked-in-place functions run at load; g and h wait to be called")

    def test_a_branch_only_a_type_checker_takes_an_all_type_import_and_an_instance_field_wait(self):
        """An import whose every name is marked `type` is erased like `import type`; `elif TYPE_CHECKING:`, the
        legacy `if False:` and whatever follows `if not TYPE_CHECKING:` are taken only by a type checker; an
        instance field's initialiser runs when an instance is built. A function called in place through .call
        or .apply, a static field and a static block run at load."""
        r = parse(".ts", "import { type X, type Y } from './a';\nimport { type X2, y } from './b';\nexport { type Z } from './c';\n"
                         "export { type Z2, w } from './d';\nimport type from './e';\nimport d, { type T } from './f';\nimport {} from './g';\n")
        self.assertEqual([i[1] for i in r["imports"]], ["./a", "./b", "./c", "./d", "./e", "./f", "./g"])
        self.assertEqual(r["deferred"], [0, 2], "only when every name is a type; a default import named type still runs")
        r = parse(".py", "import sys\nif sys.platform == 'win32':\n    pass\nelif TYPE_CHECKING:\n    from .a import A\nelse:\n    from .b import B\n"
                         "if False:\n    import c\nif not TYPE_CHECKING:\n    from .d import D\nelse:\n    from .e import E\n"
                         "if not typing.TYPE_CHECKING:\n    pass\nelif x:\n    from .f import F\nif not (TYPE_CHECKING or x):\n    pass\nelse:\n    from .g import G\n")
        self.assertEqual([i[1] for i in r["imports"]], ["sys", ".a", ".b", "c", ".d", ".e", ".f", ".g"])
        self.assertEqual(r["deferred"], [1, 3, 5, 6], "the elif's own body, if False, and the branches after `not` the constant alone")
        r = parse(".js", "(function () { require('./call'); }).call(this);\n(function () { require('./apply'); }).apply(this, []);\n"
                         "(function () { require('./bind'); }).bind(this);\n"
                         "class A { x = require('./field'); static y = require('./static'); static { require('./block'); } }\n")
        self.assertEqual([i[1] for i in r["imports"]], ["./call", "./apply", "./bind", "./field", "./static", "./block"])
        self.assertEqual(r["deferred"], [2, 3], "bind only makes a function; an instance field waits for new")
        r = parse(".ts", "class B { private x = require('./field'); private static y = require('./static'); }\n")
        self.assertEqual(r["deferred"], [0])
        r = parse(".js", "(function () { require('./call'); })['call'](this);\n(function () { require('./apply'); })[\"apply\"](this);\n"
                         "(function () { require('./other'); })['bind'](this);\n")
        self.assertEqual(r["deferred"], [2], "the bracketed .call and .apply of a minified wrapper run in place too")
        r = parse(".py", "if (not TYPE_CHECKING):\n    from .a import A\nelse:\n    from .b import B\n")
        self.assertEqual(r["deferred"], [1], "brackets round `not` the constant are the same condition")

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
        self.assertEqual(edges["src/app/main.py"], ["src/app/util.py"], "a src/ layout resolves from its root, src/")
        self.assertEqual(edges["web/index.ts"], ["web/comp/index.tsx", "web/lib/x.ts"], "a .js import of a .ts file, an index file, no node_modules")
        self.assertEqual(edges["c/main.c"], ["c/util.h"])
        self.assertEqual(edges["lib/r.rb"], ["lib/s.rb"], "a gem is not this tree")
        self.assertEqual(resolved["typescript"], 1.0)
        self.assertEqual(resolved["c"], 0.5)

    def test_an_absolute_import_resolves_from_a_root_never_from_inside_a_package(self):
        """django has django/utils/warnings.py and django/template/backends/django.py. Matched by suffix alone,
        the standard library's `import warnings` resolved to the first and `import django` to the second, and
        the import graph carried edges no import makes. A module under a package is reached through the
        package's name, so a candidate counts only where what lies above it is not a package itself."""
        py = lambda *imports: {"language": "python", "imports": [list(i) for i in imports]}
        files = {"django/__init__.py": py(), "django/utils/__init__.py": py(), "django/utils/warnings.py": py(["abs", "django"]),
                 "django/template/__init__.py": py(), "django/template/backends/__init__.py": py(),
                 "django/template/backends/django.py": py(), "django/apps/__init__.py": py(["from", ".registry", ["apps"]]),
                 "django/apps/registry.py": py(["abs", "warnings"], ["from", "django.utils", ["warnings"]]),
                 "src/app/__init__.py": py(), "src/app/util.py": py(), "src/app/main.py": py(["from", "app.util", ["f"]]),
                 "tests/helpers.py": py(), "tests/test_x.py": py(["abs", "helpers"])}
        edges, resolved = structure.resolve(files)
        self.assertEqual(edges["django/utils/warnings.py"], ["django/__init__.py"], "the package, not a module that shares its name")
        self.assertEqual(edges["django/apps/registry.py"], ["django/utils/warnings.py"],
                         "`from django.utils import warnings` is the module; the standard library's `import warnings` is not this tree")
        self.assertEqual(edges["django/apps/__init__.py"], ["django/apps/registry.py"])
        self.assertEqual(edges["src/app/main.py"], ["src/app/util.py"], "src/ is no package, so a src/ layout still resolves")
        self.assertEqual(edges["tests/test_x.py"], ["tests/helpers.py"], "a test directory without __init__.py is a root, as pytest makes it")
        self.assertEqual(resolved["python"], 1.0, "`import warnings` is the standard library: not an import that failed to resolve")

    def test_a_directory_without_an_init_inside_a_package_is_no_root(self):
        """pkg/scripts/ has no __init__.py but sits under pkg/, which has one: a namespace subpackage, reached as
        pkg.scripts.io and never as a bare `import io`. Checking only the immediate parent left this class of
        edge alive one level down (django's tests/apps/namespace_package_base/, ghidra's ghidradbg/exdi/)."""
        py = lambda *imports: {"language": "python", "imports": [list(i) for i in imports]}
        files = {"pkg/__init__.py": py(), "pkg/core.py": py(["abs", "io"], ["abs", "pkg.scripts.io"]), "pkg/scripts/io.py": py(),
                 "tests/apps/__init__.py": py(), "tests/apps/ns/nsapp/apps.py": py(), "tests/other/test_y.py": py(["abs", "apps"])}
        edges, resolved = structure.resolve(files)
        self.assertEqual(edges["pkg/core.py"], ["pkg/scripts/io.py"], "the standard library's io is not this tree; the package's own scripts/io is, through its full name")
        self.assertEqual(edges["tests/other/test_y.py"], ["tests/apps/__init__.py"], "tests/ is the root above the outermost package, so `import apps` is tests/apps")
        self.assertEqual(resolved["python"], 1.0)

    def test_an_import_answered_under_two_roots_takes_the_one_nearest_the_importer(self):
        """ghidra keeps one IDA loader per IDA version, 7xx/python/idaxml.py and 9xx/python/idaxml.py, with a script
        beside each doing `from idaxml import ...`. Python puts the script's own directory first on its path, so
        each loads its neighbour; a `from` import made an edge to both, and a plain import took the first path."""
        py = lambda *imports: {"language": "python", "imports": [list(i) for i in imports]}
        files = {"ida/7xx/python/idaxml.py": py(), "ida/7xx/python/load.py": py(["from", "idaxml", ["Loader"]]),
                 "ida/9xx/python/idaxml.py": py(), "ida/9xx/python/load.py": py(["from", "idaxml", ["Loader"]]),
                 "ida/9xx/python/plugin.py": py(["abs", "idaxml"]), "ida/9xx/loaders/xml.py": py(["abs", "idaxml"]),
                 "tools/run.py": py(["abs", "idaxml"])}
        edges, resolved = structure.resolve(files)
        self.assertEqual(edges["ida/7xx/python/load.py"], ["ida/7xx/python/idaxml.py"])
        self.assertEqual(edges["ida/9xx/python/load.py"], ["ida/9xx/python/idaxml.py"], "its neighbour, not both copies")
        self.assertEqual(edges["ida/9xx/python/plugin.py"], ["ida/9xx/python/idaxml.py"], "its neighbour, not the first path")
        self.assertEqual(edges["ida/9xx/loaders/xml.py"], ["ida/9xx/python/idaxml.py"], "no root above it: the copy sharing most of its path")
        self.assertEqual(edges["tools/run.py"], ["ida/7xx/python/idaxml.py"], "neither is nearer: the first path, the same every run")
        self.assertEqual(resolved["python"], 1.0)

    def test_a_relative_import_names_one_tree_path_and_no_longer_falls_back_to_a_suffix(self):
        py = lambda *imports: {"language": "python", "imports": [list(i) for i in imports]}
        files = {"pkg/__init__.py": py(), "pkg/a.py": py(["from", "..x", ["y"]]), "lib/x.py": py()}
        edges, resolved = structure.resolve(files)
        self.assertEqual(edges["pkg/a.py"], [], "..x climbs above the tree's top: nothing there to name, and lib/x.py is not it")
        self.assertEqual(resolved["python"], 0.0, "counted as an import that did not resolve, not silently matched elsewhere")

    def test_eager_leaves_out_the_deferred_imports(self):
        files = {"pkg/a.py": {"language": "python", "imports": [["from", ".", ["b"]]]},
                 "pkg/b.py": {"language": "python", "imports": [["from", ".", ["a"]], ["from", ".", ["c"]]], "deferred": [0]},
                 "pkg/c.py": {"language": "python", "imports": [["from", ".", ["b"]]], "deferred": [0]}}
        edges, resolved = structure.resolve(files)
        self.assertEqual(edges["pkg/b.py"], ["pkg/a.py", "pkg/c.py"])
        eager, same = structure.resolve(files, eager=True)
        self.assertEqual((eager["pkg/a.py"], eager["pkg/b.py"], eager["pkg/c.py"]), (["pkg/b.py"], ["pkg/c.py"], []))
        self.assertEqual(same, resolved, "the resolved share is over every import either way")

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
                fh.write("def g():\n    from . import a\n")
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
        self.assertNotIn("deferred", data["files"]["pkg/a.py"], "a file whose imports all run at load carries no list")
        self.assertEqual((data["files"]["pkg/b.py"]["imports"], data["files"]["pkg/b.py"]["deferred"]), (["pkg/a.py"], ["pkg/a.py"]))
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


class Unreferenced(unittest.TestCase):
    """structure.unreferenced had no test of its own: 0.36.0's first round crashed the structure step on four
    repositories with a NameError on its last line, which no fixture reached because none had an unreferenced
    file in a trusted language."""

    def files(self, n=12, orphans=1):
        py = lambda imports: {"language": "python", "imports": imports, "main": False}
        out = {f"pkg/m{i}.py": py([]) for i in range(n)}
        for i in range(orphans, n):
            out[f"pkg/m{i}.py"]["imports"] = [f"pkg/m{i + 1 if i + 1 < n else orphans}.py"]   # a ring over everything but the first `orphans`, which nothing imports
        return out

    def test_a_file_nothing_imports_in_a_trusted_language_is_named(self):
        files = self.files(n=40)   # one of forty is under MAX_SHARE, so the language is not "loud"
        edges = {p: info["imports"] for p, info in files.items()}
        self.assertEqual(structure.unreferenced(files, edges, {"python": 0.9}, set()), ["pkg/m0.py"])
        self.assertEqual(structure.unreferenced(files, edges, {"python": 0.3}, set()), [], "a graph that resolves a third of the time is not judged")
        self.assertEqual(structure.unreferenced(files, edges, {"python": 0.9}, {"pkg/m0.py"}), [], "a declared entry point is no orphan")

    def test_a_language_where_more_than_one_file_in_twenty_looks_unreferenced_is_not_listed(self):
        files = self.files(n=20, orphans=3)   # 3 of 20 is over MAX_SHARE: the language loads code by name here
        edges = {p: info["imports"] for p, info in files.items()}
        self.assertEqual(structure.unreferenced(files, edges, {"python": 0.9}, set()), [])

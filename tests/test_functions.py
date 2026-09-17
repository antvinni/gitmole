import os
import subprocess
import tempfile
import unittest

from gitmole import functions


def make_repo(d, extra=()):
    def git(*args):
        e = dict(os.environ, GIT_CONFIG_GLOBAL="/dev/null", GIT_CONFIG_SYSTEM="/dev/null",
                 GIT_AUTHOR_NAME="Ann", GIT_AUTHOR_EMAIL="a@x", GIT_COMMITTER_NAME="Ann", GIT_COMMITTER_EMAIL="a@x")
        subprocess.run(["git", *args], cwd=d, check=True, capture_output=True, env=e)
    git("init", "-q")
    os.makedirs(os.path.join(d, "vendor"))
    files = {
        "app.py": "def tracked(a, b):\n    if a:\n        return b\n    return a\n",
        "vendor/lib.py": "def vendored():\n    return 1\n",
        "notes.md": "def not_code():\n    pass\n",
        "page.js": "function scripted(a) {\n  if (a) { return 1; }\n  return 0;\n}\n",
        "run.sh": "shelled() {\n  if [ -n \"$1\" ]; then echo hi; fi\n}\n",
        "sim.f90": "subroutine fortran_sub(x)\n  integer :: x\n  if (x > 0) then\n    x = 1\n  end if\nend subroutine\n",
    }
    files.update(extra)
    for name, text in files.items():
        with open(os.path.join(d, name), "w") as fh:
            fh.write(text)
    git("add", "-A")
    git("commit", "-q", "-m", "one")
    with open(os.path.join(d, "untracked.py"), "w") as fh:
        fh.write("def untracked():\n    return 2\n")


def run(d, *args):
    out = os.path.join(d, "out")
    os.makedirs(out, exist_ok=True)
    rc = functions.main([d, out, "--procs", "1", *args])
    with open(os.path.join(out, "functions.csv")) as fh:
        csv = fh.read()
    return rc, csv, sorted(os.listdir(out))


class FunctionsScript(unittest.TestCase):
    def test_measures_tracked_files_lizard_can_read(self):
        with tempfile.TemporaryDirectory() as d:
            make_repo(d)
            rc, csv, written = run(d, "--ignore", "vendor/**")
        self.assertEqual(rc, 0)
        self.assertIn('"tracked"', csv)
        self.assertIn('"fortran_sub"', csv, "every language lizard knows, not only gitmole's default code list")
        self.assertNotIn("untracked", csv, "not tracked by git")
        self.assertNotIn("vendored", csv, "--ignore applies")
        self.assertNotIn("not_code", csv, "markdown is not code")
        self.assertNotIn("shelled", csv, "no lizard reader for shell: no guessing with the C-like fallback")
        self.assertEqual(written, ["functions.csv"], "duplicates are jscpd's step, not lizard's")

    def test_a_huge_nested_name_is_cut_before_it_is_written(self):
        from types import SimpleNamespace
        name = ".".join("a" for _ in range(100_000))
        fn = SimpleNamespace(nloc=5, cyclomatic_complexity=3, token_count=40, parameter_count=1, length=5, name=name,
                             long_name=name + "( )", start_line=1, end_line=5)
        row = functions.csv_row(SimpleNamespace(filename="a.py"), fn)
        self.assertEqual(len(row[7]), functions.NAME_CAP)
        self.assertTrue(row[7].endswith("…"))
        self.assertLessEqual(len(row[8]), functions.LONG_NAME_CAP)
        self.assertLessEqual(len(row[5]), functions.NAME_CAP + len("@1-5@a.py"))

    def test_csv_is_lizards_own_layout_then_the_label_and_suspect_columns(self):
        with tempfile.TemporaryDirectory() as d:
            make_repo(d)
            rc, csv, _ = run(d, "--types", "py", "--ignore", "vendor/**")
        self.assertEqual(csv, '4,2,14,2,4,"tracked@1-4@app.py","app.py","tracked","tracked( a , b )",1,4,"",""\n')

    def test_a_nameless_function_is_labelled_by_its_start_line(self):
        route = 'app.post("/api/actions/:id/assign", async (req, res) => {\n  if (!req.params.id) { return res.status(400).send(); }\n  res.send(req.params.id);\n});\n'
        literal = "package main\n\nfunc main() {\n\tf := func(x int) int {\n\t\tif x > 0 {\n\t\t\treturn 1\n\t\t}\n\t\treturn 0\n\t}\n\t_ = f\n}\n"
        with tempfile.TemporaryDirectory() as d:
            make_repo(d, extra={"routes.js": route, "lit.go": literal})
            rc, csv, _ = run(d, "--types", "js,go")
        self.assertIn('"(anonymous)","(anonymous)",1,4,"app.post(""/api/actions/:id/assign"", async (req, res) => {",""', csv)
        self.assertIn('""," x int",4,9,"f := func(x int) int {",""', csv, "a Go literal has an empty name and the same kind of label")
        self.assertIn('"main","main",3,11,"",""', csv, "a named function needs no label")

    def test_the_label_is_the_nearest_line_that_opens_a_function_when_lizard_is_a_line_off(self):
        # lizard puts an arrow whose body starts on the next line at the body's line, and a callback in a
        # JSX attribute at the tag's line: the label looks a line back and a few lines on for the `=>`
        src = ("const xs = items.filter((m) =>\n  prev.includes(m)\n);\n"
               "function A() {\n  return (\n    <Input\n      onChange={(e) => {\n        set(e.target.value);\n      }}\n    />\n  );\n}\n")
        with tempfile.TemporaryDirectory() as d:
            make_repo(d, extra={"near.tsx": src})
            rc, csv, _ = run(d, "--types", "tsx")
        self.assertIn('"(anonymous)","(anonymous)",2,2,"const xs = items.filter((m) =>",""', csv)
        self.assertIn('"(anonymous)","(anonymous)",6,8,"onChange={(e) => {",""', csv)

    def test_a_span_that_swallows_a_sibling_is_marked_suspect(self):
        # lizard loses its place in a template literal and folds the next function into `tpl`
        src = ("const tpl = (name) => `\n<html>\n  <body>\n    ${name ? `<h1>${name}</h1>` : \"\"}\n  </body>\n</html>`;\n\n"
               "function after(a) {\n  if (a) { return 1; }\n  return 0;\n}\n")
        with tempfile.TemporaryDirectory() as d:
            make_repo(d, extra={"tpl.js": src})
            rc, csv, _ = run(d, "--types", "js")
        self.assertNotIn('"after"', csv, "the fixture only holds if lizard still swallows the sibling")
        self.assertIn('"tpl","tpl ( name )",1,9,"","opens a block at line 8 no deeper than its own start"', csv)
        self.assertIn('"scripted","scripted ( a )",1,4,"",""', csv, "a closing line is not a sibling")

    def test_a_signature_that_closes_its_parameter_list_on_a_later_line_is_not_a_sibling(self):
        src = ("function Panel({\n  title,\n  onClose,\n}: PanelProps) {\n  if (!title) { return null; }\n  return onClose;\n}\n"
               "class Store {\n  async summary(filters?: {\n    siteId?: string;\n  }): Promise<any> {\n    if (filters) { return 1; }\n    return 0;\n  }\n}\n")
        with tempfile.TemporaryDirectory() as d:
            make_repo(d, extra={"sig.ts": src})
            rc, csv, _ = run(d, "--types", "ts")
        self.assertIn('"Panel","Panel ( title , onClose , PanelProps )",1,7,"",""', csv)
        self.assertIn('"summary","summary ( filters siteId )",9,14,"",""', csv)

    def test_jsx_children_on_their_own_lines_do_not_shift_the_line_numbers(self):
        # lizard 1.24 merges the newline before a JSX child with its indentation into one whitespace token,
        # and its preprocessing drops whitespace tokens other than a bare newline: one line lost per child
        src = ('function A() {\n  return (\n    <div className="grid">\n      <div className="lg">\n      </div>\n'
               '        <Skeleton className="h-48" />\n    </div>\n  );\n}\nfunction B() {\n  return 1;\n}\n')
        with tempfile.TemporaryDirectory() as d:
            make_repo(d, extra={"page.tsx": src})
            rc, csv, _ = run(d, "--types", "tsx")
        self.assertIn('"B","B ( )",10,12,"",""', csv)
        self.assertIn('"A","A ( )",1,9,"",""', csv)

    def test_a_nameless_span_where_nothing_opens_a_function_is_marked_suspect(self):
        # lizard reports a JSX ternary as a function: all code, all deeper than its start, so only the
        # missing `=>` or `function` near its start line gives it away
        src = "function A() {\n  return (\n    <div>\n      {isLoading ? (\n        <p>x</p>\n      ) : (\n        <p>y</p>\n      )}\n    </div>\n  );\n}\n"
        with tempfile.TemporaryDirectory() as d:
            make_repo(d, extra={"ternary.tsx": src})
            rc, csv, _ = run(d, "--types", "tsx")
        self.assertIn('"(anonymous)","(anonymous) ( x )",4,8,"{isLoading ? (","nothing opens a function within 5 lines of line 4"', csv)
        self.assertIn('"A","A ( )",1,11,"",""', csv)

    def test_a_long_span_that_is_mostly_not_code_is_marked_suspect(self):
        body = "".join(f"  // note {i}\n" for i in range(40))
        src = "function sparse(a) {\n" + body + "  if (a) { return 1; }\n  return 0;\n}\n"
        with tempfile.TemporaryDirectory() as d:
            make_repo(d, extra={"sparse.js": src})
            rc, csv, _ = run(d, "--types", "js")
        self.assertIn('"sparse","sparse ( a )",1,44,"","4 of 44 lines are code"', csv)

    def test_file_types_restrict_what_is_measured(self):
        with tempfile.TemporaryDirectory() as d:
            make_repo(d)
            rc, csv, _ = run(d, "--types", "js")
        self.assertEqual(rc, 0)
        self.assertIn("scripted", csv)
        self.assertNotIn("tracked", csv)
        self.assertNotIn("fortran", csv)

    def test_no_code_files_still_writes_an_empty_csv(self):
        with tempfile.TemporaryDirectory() as d:
            make_repo(d)
            rc, csv, _ = run(d, "--ignore", "*.py", "--ignore", "*.js", "--ignore", "*.f90")
        self.assertEqual(rc, 0)
        self.assertEqual(csv, "")

    def test_a_lizard_module_in_the_analysed_repo_is_data_not_code_to_run(self):
        bomb = "import sys\nsys.stderr.write('REPO LIZARD RAN')\nsys.exit(7)\n"
        with tempfile.TemporaryDirectory() as d:
            make_repo(d, extra={"lizard.py": bomb, "lizard_ext/__init__.py": bomb} if False else {"lizard.py": bomb})
            rc, csv, _ = run(d, "--types", "py", "--ignore", "vendor/**")
        self.assertEqual(rc, 0)
        self.assertIn('"tracked"', csv)
        self.assertNotIn("REPO LIZARD RAN", csv)

    def test_a_file_lizard_cannot_read_does_not_stop_the_files_after_it(self):
        with tempfile.TemporaryDirectory() as d:
            make_repo(d, extra={"b_gone.py": "def gone():\n    return 3\n", "c_after.py": "def after(a):\n    return a\n"})
            os.remove(os.path.join(d, "b_gone.py"))   # still in the index, no longer on disk
            rc, csv, _ = run(d, "--types", "py", "--ignore", "vendor/**")
        self.assertEqual(rc, 0)
        self.assertIn('"after"', csv, "files after the unreadable one are still measured")


if __name__ == "__main__":
    unittest.main()

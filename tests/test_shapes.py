"""The shape rules on the tree-sitter pass: an error caught and dropped, an address written into a string
literal, code left in a comment. The parsing tests need the tree-sitter grammars; the findings do not."""
import unittest

from gitmole import findings, structure
from tests.test_findings import report
from tests.test_structure import HAVE, parse


class CommentedCode(unittest.TestCase):
    """The comment classifier is plain text, no grammar needed."""

    def test_code_left_by_an_editor_counts(self):
        self.assertEqual(structure.commented_code_lines("// const old = legacy(x);\n// console.log(state);\n// if (a) {\n//   b();\n// }"), 5)
        self.assertEqual(structure.commented_code_lines("/* legacy(x);\n   other(y); */"), 2)
        self.assertEqual(structure.commented_code_lines("# x = compute(a, b)"), 1)

    def test_prose_examples_directives_and_doc_comments_do_not(self):
        self.assertEqual(structure.commented_code_lines("# Some examples:\n#     SomeModel.objects.annotate(x)\n#     foo(bar)"), 0)
        self.assertEqual(structure.commented_code_lines("//   function f(fn) {\n//     return g();\n//   }"), 0, "indented under the marker: an example")
        self.assertEqual(structure.commented_code_lines("// Build the dispatcher:\n// function Foo(a) {\n// return x;\n// }\n// }"), 0)
        self.assertEqual(structure.commented_code_lines("/** @example foo(1); */"), 0)
        self.assertEqual(structure.commented_code_lines("// eslint-disable-next-line no-console"), 0)
        self.assertEqual(structure.commented_code_lines("/* 35 = OBSOLETE */"), 0)
        self.assertEqual(structure.commented_code_lines("# This explains why we do it."), 0)

    def test_addresses_leave_out_what_is_not_a_host(self):
        self.assertEqual(structure._address("'10.1.2.3'"), "10.1.2.3")
        self.assertEqual(structure._address("`203.0.114.9:8080`"), "203.0.114.9:8080")
        for literal in ("'127.0.0.1'", "'0.0.0.0'", "'255.255.255.0'", "'1.0.0.0'", "'2.5.4.3'", "'192.0.2.10'", "'300.1.1.1'", "'v1.2.3.4'"):
            self.assertIsNone(structure._address(literal), literal)


@unittest.skipUnless(HAVE, "the tree-sitter grammars need Python 3.10 or newer")
class Shapes(unittest.TestCase):
    def test_python_counts_only_the_broad_except_that_does_nothing(self):
        s = parse(".py", "try:\n    x()\nexcept:\n    pass\ntry:\n    y()\nexcept ValueError:\n    pass\n"
                         "try:\n    z()\nexcept Exception as e:\n    pass\ntry:\n    w()\nexcept Exception:\n    # ignored on purpose\n    pass\n")["shapes"]
        self.assertEqual(s["empty_catch"], [3, 11])
        self.assertEqual(s["bare_except"], [3])

    def test_empty_catch_in_other_languages_and_a_comment_saves_it(self):
        self.assertEqual(parse(".js", "try { a() } catch (e) {}\ntry { b() } catch { /* ok */ }\n")["shapes"]["empty_catch"], [1])
        self.assertEqual(parse(".java", "class A { void f() { try { g(); } catch (Exception e) { } } }\n")["shapes"]["empty_catch"], [1])
        self.assertEqual(parse(".rb", "begin\n  x\nrescue\nend\nbegin\n  y\nrescue => e\n  # ok\nend\n")["shapes"]["empty_catch"], [3])

    def test_addresses_in_literals_but_not_in_attributes(self):
        s = parse(".cs", '[assembly: AssemblyVersion("1.2.3.4")]\nclass A { void F() { var s = "8.8.4.4"; } }\n')["shapes"]
        self.assertEqual(s["addresses"], [{"line": 2, "value": "8.8.4.4"}])

    def test_line_comments_on_consecutive_lines_are_one_block_and_trailing_comments_are_not_code(self):
        s = parse(".py", "x = 1  # y = 2\n# a = f(b)\n# c = g(d)\n\n# prose about it\n")["shapes"]
        self.assertEqual((s["commented_code"], s["commented_sample"]), (2, [2]))


def _report(files, **over):
    return report(structure={"status": "run", "files": files}, **over)


class ShapeFindings(unittest.TestCase):
    def test_swallowed_errors_from_five_and_never_in_tests(self):
        files = {"src/a.py": {"shapes": {"empty_catch": [3, 9], "empty_catch_count": 4, "bare_except": [3], "bare_except_count": 1}},
                 "src/b.js": {"shapes": {"empty_catch": [7], "empty_catch_count": 1}},
                 "tests/test_a.py": {"shapes": {"empty_catch": [1], "empty_catch_count": 9}}}
        f = findings.swallowed_errors(_report(files))
        self.assertEqual([(x["rule"]["id"], x["severity"]) for x in f], [("swallowed_errors", "info")])
        self.assertIn("5 empty catch blocks in 2 source files, 1 of them a bare except", f[0]["detail"])
        self.assertEqual(f[0]["evidence"]["files"][0], {"file": "src/a.py", "start": 3, "count": 4})
        del files["src/b.js"]
        self.assertEqual(findings.swallowed_errors(_report(files)), [], "four in source is below the floor")

    def test_addresses_and_commented_code(self):
        files = {"src/net.go": {"shapes": {"addresses": [{"line": 4, "value": "10.0.0.7"}], "addresses_count": 1}},
                 "src/old.js": {"shapes": {"commented_code": 12, "commented_sample": [40, 90]}},
                 "src/some.js": {"shapes": {"commented_code": 3, "commented_sample": [5]}}}
        f = findings.hardcoded_addresses(_report(files))
        self.assertIn("1 IPv4 address in string literals in 1 source file", f[0]["detail"])
        self.assertIn("10.0.0.7 at src/net.go:4", f[0]["detail"])
        files["src/net.go"]["shapes"] = {"addresses": [{"line": 4, "value": "10.0.0.7"}, {"line": 9, "value": "10.0.0.8"}],
                                         "addresses_count": 2}
        f = findings.hardcoded_addresses(_report(files))
        self.assertIn("2 IPv4 addresses in string literals in 1 source file", f[0]["detail"], "ghidra read '2 IPv4 addresss'")
        f = findings.commented_out_code(_report(files))
        self.assertEqual([x["file"] for x in f[0]["evidence"]["files"]], ["src/old.js"])
        self.assertIn("src/old.js (12 lines from line 40)", f[0]["detail"])

    def test_nothing_without_the_structure_step(self):
        for rule in (findings.swallowed_errors, findings.hardcoded_addresses, findings.commented_out_code):
            self.assertEqual(rule(report()), [])


if __name__ == "__main__":
    unittest.main()

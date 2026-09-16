import unittest

from gitmole import watch


def report(**overrides):
    base = {
        "meta": {"name": "r"},
        "size": {"files": {"core/parser.py": {"code": 800, "complexity": 40}, "core/util.py": {"code": 200, "complexity": 5},
                           "web/index.html": {"code": 4000, "complexity": 0}, "tests/test_parser.py": {"code": 300, "complexity": 2}}},
        "revisions": [{"entity": "web/index.html", "n-revs": 60}, {"entity": "core/parser.py", "n-revs": 40},
                      {"entity": "core/util.py", "n-revs": 30}, {"entity": "tests/test_parser.py", "n-revs": 45},
                      {"entity": "core/gone.py", "n-revs": 50}, {"entity": "core/once.py", "n-revs": 1}],
        "fixes": [{"entity": "core/parser.py", "n-fixes": 9, "last-fix": "2026-09-01", "recent-fixes": 5},
                  {"entity": "core/util.py", "n-fixes": 2, "last-fix": "2025-01-01", "recent-fixes": 0}],
        "authors": [{"entity": "core/parser.py", "n-authors": 1}, {"entity": "core/util.py", "n-authors": 3}, {"entity": "web/index.html", "n-authors": 4}],
        "ownership": [{"entity": "core/parser.py", "author": "Ann", "added": 900, "deleted": 0},
                      {"entity": "core/util.py", "author": "Ann", "added": 190, "deleted": 0},
                      {"entity": "core/util.py", "author": "Bob", "added": 10, "deleted": 0},
                      {"entity": "web/index.html", "author": "Bob", "added": 2000, "deleted": 0},
                      {"entity": "web/index.html", "author": "Cat", "added": 2000, "deleted": 0}],
        "coupling": [{"entity": "core/parser.py", "coupled": "core/ast.py", "degree": 72, "average-revs": 30},
                     {"entity": "core/lexer.py", "coupled": "core/parser.py", "degree": 55, "average-revs": 20},
                     {"entity": "core/parser.py", "coupled": "core/rare.py", "degree": 90, "average-revs": 2},
                     {"entity": "core/parser.py", "coupled": "tests/test_parser.py", "degree": 100, "average-revs": 40}],
        "functions": [{"file": "core/parser.py", "function": "parse", "ccn": 41, "nloc": 220, "params": 9, "start": 10, "end": 300},
                      {"file": "core/parser.py", "function": "peek", "ccn": 2, "nloc": 5, "params": 0, "start": 1, "end": 6},
                      {"file": "core/util.py", "function": "tidy", "ccn": 4, "nloc": 20, "params": 1, "start": 1, "end": 21}],
    }
    base.update(overrides)
    return base


class Risks(unittest.TestCase):
    def test_combines_churn_fixes_complexity_and_ownership(self):
        ranked = watch.risks(report())
        self.assertEqual(ranked[0]["file"], "core/parser.py", "fewer revisions than index.html, but fixed, complex and single-owned")
        self.assertEqual([r["file"] for r in ranked], ["core/parser.py", "web/index.html", "core/util.py"],
                         "twice the churn still beats single ownership plus old fixes")

    def test_reasons_in_plain_words(self):
        top = watch.risks(report())[0]
        self.assertEqual(top["reasons"], ["changed 40 times", "fixed 5 times in six months",
                                          "only Ann has touched it", "parse() complexity 41",
                                          "changes with core/ast.py (72%) and 1 other"])
        by = {r["file"]: r for r in watch.risks(report())}
        self.assertEqual(by["core/util.py"]["reasons"], ["changed 30 times", "fixed twice", "Ann wrote 95% of it"])
        self.assertEqual(by["web/index.html"]["reasons"], ["changed 60 times"])

    def test_leaves_out_tests_deleted_files_and_one_offs(self):
        files = [r["file"] for r in watch.risks(report())]
        self.assertNotIn("tests/test_parser.py", files)
        self.assertNotIn("core/gone.py", files, "no longer in the tree")
        self.assertNotIn("core/once.py", files, "changed once")

    def test_test_companions_and_weak_pairs_are_not_reasons(self):
        top = watch.risks(report())[0]
        coupling = [r for r in top["reasons"] if r.startswith("changes with")][0]
        self.assertNotIn("test_parser", coupling)
        self.assertNotIn("rare", coupling, "2 shared revisions is not a pattern")

    def test_scc_complexity_stands_in_when_lizard_is_absent(self):
        r = report(functions=[])
        ranked = watch.risks(r)
        self.assertEqual(ranked[0]["file"], "core/parser.py")
        self.assertFalse(any("complexity" in x for x in ranked[0]["reasons"]), "scc's file total is not worded")

    def test_empty_without_change_data(self):
        self.assertEqual(watch.risks(report(revisions=[])), [])
        self.assertEqual(watch.risks({"meta": {}, "size": {}}), [])


if __name__ == "__main__":
    unittest.main()

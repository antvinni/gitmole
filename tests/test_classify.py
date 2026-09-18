import unittest

from gitmole import classify


def report(**overrides):
    base = {
        "meta": {"file_types": None, "generated": ["gen/api.pb.go"], "vendored": ["mypy/typeshed/", "third/lib.js"]},
        "size": {"files": {"core/parser.py": {"code": 800, "complexity": 40}, "gen/api.pb.go": {"code": 3000, "complexity": 1},
                           "vendor/x_test.go": {"code": 10, "complexity": 1}, "package.json": {"code": 30, "complexity": 0},
                           "big/all.hpp": {"code": 9000, "complexity": 9}, "src/version.py": {"code": 1, "complexity": 0}}},
        "plumbing": [{"entity": "src/version.py"}],
        "functions": [],
    }
    base.update(overrides)
    return base


class Reasons(unittest.TestCase):
    def test_every_reason_in_order_then_the_first(self):
        c = classify.Classifier(report())
        self.assertIsNone(c.reason("core/parser.py"))
        self.assertEqual(c.reasons("gen/api.pb.go"), ("generated",))
        self.assertEqual(c.reasons("vendor/x_test.go"), ("vendored", "test file"), "descriptive order: vendored before test file")
        self.assertEqual(c.reason("vendor/x_test.go"), "vendored")
        self.assertEqual(c.reasons("mypy/typeshed/a.pyi"), ("vendored", "not in the tree"))
        self.assertEqual(c.reason("third/lib.js"), "vendored", "a file entry from linguist-vendored")
        self.assertEqual(c.reason("tests/test_a.py"), "test file")
        self.assertEqual(c.reason("examples/demo.py"), "example code")
        self.assertEqual(c.reason("package.json"), "release file", "a release file before it is not a source type")
        self.assertEqual(c.reasons("package.json"), ("release file", "not a source type"))
        self.assertEqual(c.reason("src/version.py"), "release file", "plumbing by behaviour counts")
        self.assertEqual(c.reason("README.md"), "not a source type")
        self.assertEqual(c.reason("core/gone.py"), "not in the tree")
        self.assertEqual(classify.REASONS, ("generated", "vendored", "test file", "example code", "release file", "amalgamation",
                                            "not a source type", "not in the tree"))

    def test_amalgamations_come_from_the_function_metrics(self):
        funcs = [{"file": "big/all.hpp", "function": f"f{i}", "ccn": 2, "nloc": 5, "params": 1} for i in range(20)]
        funcs += [{"file": f"src/p{i % 3}.hpp", "function": f"f{i}", "ccn": 2, "nloc": 5, "params": 1} for i in range(20)]
        c = classify.Classifier(report(functions=funcs))
        self.assertEqual(c.reason("big/all.hpp"), "amalgamation")

    def test_no_size_data_classifies_nothing_as_gone(self):
        c = classify.Classifier(report(size={"files": {}}))
        self.assertIsNone(c.reason("core/gone.py"), "a killed scc must not empty every table")

    def test_file_types_follow_the_run_and_an_old_directory_is_unfiltered(self):
        c = classify.Classifier(report(meta={"file_types": "py"}))
        self.assertEqual(c.reason("core/parser.py"), None)
        self.assertEqual(c.reason("lib/a.go"), "not a source type")
        c = classify.Classifier({"meta": {}, "size": {"files": {}}})
        self.assertIsNone(c.reason("README.md"), "no file_types record: the run measured everything, so nothing is out by type")

    def test_excluded_asks_whether_any_reason_is_in_the_set(self):
        c = classify.Classifier(report())
        self.assertTrue(c.excluded("vendor/x_test.go", {"test file"}), "a hotspots table hiding tests still hides a vendored test")
        self.assertFalse(c.excluded("vendor/x_test.go", {"generated"}))
        self.assertFalse(c.excluded("core/parser.py", set(classify.REASONS)))


class Coverage(unittest.TestCase):
    def test_counts_tracked_files_by_reason_and_names_the_scc_gap(self):
        c = classify.Classifier(report())
        cov = classify.coverage(c, ["core/parser.py", "gen/api.pb.go", "vendor/x_test.go", "package.json", "README.md", "shaders/a.wgsl", "tests/t.py"])
        self.assertEqual(cov, {"scored": 1, "generated": 1, "vendored": 1, "release file": 1, "not a source type": 1,
                               "not counted by scc": 1, "test file": 1})
        self.assertEqual(classify.coverage_line(cov),
                         "7 files: 1 scored · 1 generated · 1 vendored · 1 test file · 1 release file · 1 not a source type · 1 not counted by scc")
        self.assertEqual(classify.coverage_line({"scored": 3900, "test file": 610, "generated": 120}),
                         "4,630 files: 3,900 scored · 120 generated · 610 test files")

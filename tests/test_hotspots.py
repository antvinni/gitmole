import unittest

from gitmole import hotspots


class Ranked(unittest.TestCase):
    REPORT = {"size": {"files": {"big.py": {"code": 5000, "complexity": 40}, "small.py": {"code": 10, "complexity": 1}}},
              "revisions": [{"entity": "small.py", "n-revs": 31}, {"entity": "big.py", "n-revs": 30}, {"entity": "gone.py", "n-revs": 99}]}

    def test_scores_revisions_times_lines_and_sinks_deleted_files(self):
        ranked = hotspots.ranked(self.REPORT)
        self.assertEqual([r["entity"] for r in ranked], ["big.py", "small.py", "gone.py"])
        self.assertEqual(ranked[0], {"entity": "big.py", "revs": 30, "code": 5000, "complexity": 40, "score": 150000})
        self.assertEqual(ranked[2], {"entity": "gone.py", "revs": 99, "code": None, "complexity": None, "score": -1})

    def test_top_names_the_first_n_files(self):
        self.assertEqual(hotspots.top(self.REPORT, 2), {"big.py", "small.py"})
        self.assertEqual(hotspots.top({"size": {}, "revisions": []}), set())


if __name__ == "__main__":
    unittest.main()


class Amalgamations(unittest.TestCase):
    def _fn(self, file, name, ccn, nloc):
        return {"file": file, "function": name, "ccn": ccn, "nloc": nloc, "params": 1, "start": 1, "end": nloc}

    def test_a_file_whose_functions_all_appear_in_other_files_is_an_amalgamation(self):
        # nlohmann/json: single_include/nlohmann/json.hpp is include/ pasted together by a build step
        fns = []
        for i in range(12):
            fns.append(self._fn("include/detail/input/binary_reader.hpp", f"parse_{i}", 10 + i, 40 + i))
            fns.append(self._fn("single_include/json.hpp", f"parse_{i}", 10 + i, 40 + i))
        for i in range(10):
            fns.append(self._fn("include/detail/output/serializer.hpp", f"dump_{i}", 5 + i, 30 + i))
            fns.append(self._fn("single_include/json.hpp", f"dump_{i}", 5 + i, 30 + i))
        fns.append(self._fn("include/detail/lexer.hpp", "scan", 50, 200))
        self.assertEqual(hotspots.amalgamations({"functions": fns}), {"single_include/json.hpp"})

    def test_a_file_needs_twenty_shared_signatures_from_two_or_more_files(self):
        fns = [self._fn("a.py", f"f{i}", 5, 20) for i in range(25)] + [self._fn("b.py", f"f{i}", 5, 20) for i in range(25)]
        self.assertEqual(hotspots.amalgamations({"functions": fns}), set(), "two files mirroring each other: neither is the union of others")
        fns = [self._fn("a.py", f"f{i}", 5, 20) for i in range(5)] + [self._fn("c.py", f"f{i}", 5, 20) for i in range(5)] \
            + [self._fn("b.py", f"f{i}", 5, 20) for i in range(5)]
        self.assertEqual(hotspots.amalgamations({"functions": fns}), set(), "too few to judge")
        self.assertEqual(hotspots.amalgamations({}), set())

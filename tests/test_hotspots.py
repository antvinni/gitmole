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

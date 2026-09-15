import unittest

from gitmole import knowledge

OWNERSHIP = [
    {"entity": "app/main.py", "author": "Ann", "added": 300, "deleted": 10},
    {"entity": "app/util.py", "author": "Ann", "added": 100, "deleted": 0},
    {"entity": "app/util.py", "author": "Bob", "added": 20, "deleted": 5},
    {"entity": "web/index.html", "author": "Bob", "added": 400, "deleted": 0},
    {"entity": "web/site.css", "author": "Cat", "added": 50, "deleted": 0},
    {"entity": "README.md", "author": "Ann", "added": 30, "deleted": 0},
]


class Areas(unittest.TestCase):
    def test_groups_added_lines_by_top_level_directory(self):
        areas = knowledge.areas(OWNERSHIP)
        by = {a["area"]: a for a in areas}
        self.assertEqual([a["area"] for a in areas], ["web/", "app/", "."])
        self.assertEqual(by["app/"]["lines"], 420)
        self.assertEqual(by["app/"]["owners"], [("Ann", 400), ("Bob", 20)])
        self.assertEqual(by["app/"]["authors"], 2)
        self.assertEqual(by["."]["owners"], [("Ann", 30)])

    def test_descends_when_one_directory_holds_almost_everything(self):
        rows = [dict(r, entity="src/" + r["entity"]) for r in OWNERSHIP if r["entity"] != "README.md"]
        areas = knowledge.areas(rows)
        self.assertEqual([a["area"] for a in areas], ["src/web/", "src/app/"])

    def test_empty(self):
        self.assertEqual(knowledge.areas([]), [])


class Islands(unittest.TestCase):
    def test_areas_dominated_by_one_author(self):
        areas = knowledge.areas(OWNERSHIP)
        islands = knowledge.islands(areas, min_lines=100, min_share=0.9)
        self.assertEqual([(i["area"], i["owner"], i["share"]) for i in islands], [("app/", "Ann", 95)])

    def test_thresholds(self):
        areas = knowledge.areas(OWNERSHIP)
        self.assertEqual([i["area"] for i in knowledge.islands(areas, min_lines=100, min_share=0.8)], ["web/", "app/"])
        self.assertEqual(knowledge.islands(areas, min_lines=1000, min_share=0.5), [])


if __name__ == "__main__":
    unittest.main()

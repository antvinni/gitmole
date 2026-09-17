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
        self.assertEqual([a["area"] for a in areas], ["web/", "app/", "(root files)"])
        self.assertEqual(by["app/"]["lines"], 420)
        self.assertEqual(by["app/"]["owners"], [("Ann", 400), ("Bob", 20)])
        self.assertEqual(by["app/"]["authors"], 2)
        self.assertEqual(by["(root files)"]["owners"], [("Ann", 30)])

    def test_descends_when_one_directory_holds_almost_everything(self):
        rows = [dict(r, entity="src/" + r["entity"]) for r in OWNERSHIP if r["entity"] != "README.md"]
        areas = knowledge.areas(rows)
        self.assertEqual([a["area"] for a in areas], ["src/web/", "src/app/"])

    def test_empty(self):
        self.assertEqual(knowledge.areas([]), [])


class OddNames(unittest.TestCase):
    def test_all_digit_paths_and_authors_do_not_crash(self):
        rows = [{"entity": "2024", "author": "1234", "added": 10, "deleted": 0},
                {"entity": "app/2025", "author": "Ann", "added": 10, "deleted": 0},
                {"entity": "app/x.py", "author": "1234", "added": 10, "deleted": 0}]
        areas = knowledge.areas(rows)
        self.assertEqual([a["area"] for a in areas], ["app/", "(root files)"])
        self.assertEqual(areas[0]["owners"], [("1234", 10), ("Ann", 10)])

    def test_non_ascii_paths_group_with_their_directory(self):
        rows = [{"entity": "src/\u00e4.py", "author": "Ann", "added": 900, "deleted": 0},
                {"entity": "src/b.py", "author": "Bob", "added": 100, "deleted": 0}]
        areas = knowledge.areas(rows)
        self.assertEqual([a["area"] for a in areas], ["src/"])
        self.assertEqual(areas[0]["lines"], 1000)


class InTree(unittest.TestCase):
    TREE = {"crates/core/a.rs": {}, "crates/ignore/src/b.rs": {}, "build.rs": {}}

    def test_an_area_is_in_the_tree_when_any_tracked_file_sits_under_it(self):
        self.assertTrue(knowledge.in_tree("crates/", self.TREE))
        self.assertTrue(knowledge.in_tree("crates/ignore/", self.TREE))
        self.assertFalse(knowledge.in_tree("src/", self.TREE))
        self.assertFalse(knowledge.in_tree("crate/", self.TREE), "a prefix of a directory name is not that directory")

    def test_root_files_are_in_the_tree_when_any_file_has_no_directory(self):
        self.assertTrue(knowledge.in_tree(knowledge.ROOT, self.TREE))
        self.assertFalse(knowledge.in_tree(knowledge.ROOT, {"crates/core/a.rs": {}}))

    def test_no_tree_listing_means_every_area_counts(self):
        self.assertTrue(knowledge.in_tree("src/", {}))

    def test_present_rows_drop_vanished_top_level_directories_so_the_survivor_can_dominate(self):
        rows = [{"entity": "src/a.rs", "author": "Ann", "added": 30000, "deleted": 0},          # the layout before crates/
                {"entity": "crates/core/a.rs", "author": "Ann", "added": 9000, "deleted": 0},
                {"entity": "crates/ignore/b.rs", "author": "Bob", "added": 900, "deleted": 0},
                {"entity": "ci/x.sh", "author": "Ann", "added": 500, "deleted": 0}]
        tree = {"crates/core/a.rs": {}, "crates/ignore/b.rs": {}, "ci/x.sh": {}}
        kept = knowledge.present_rows(rows, tree)
        self.assertEqual([r["entity"] for r in kept], ["crates/core/a.rs", "crates/ignore/b.rs", "ci/x.sh"])
        self.assertEqual([a["area"] for a in knowledge.areas(kept)], ["crates/core/", "crates/ignore/", "ci/"],
                         "with src/ gone, crates/ holds over 80% and the map descends into it")
        self.assertEqual([a["area"] for a in knowledge.areas(rows)], ["src/", "crates/", "ci/"], "the vanished src/ used to hide that")
        self.assertEqual(knowledge.present_rows(rows, {}), rows)


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

import unittest

from gitmole import textfmt


class ShortenPath(unittest.TestCase):
    def test_short_paths_are_untouched(self):
        self.assertEqual(textfmt.shorten_path("gitmole/cli.py", 30), "gitmole/cli.py")

    def test_middle_directories_are_elided_keeping_first_and_last_two(self):
        p = "packages/core/src/repowise/core/pipeline/persist.py"
        self.assertEqual(textfmt.shorten_path(p, 36), "packages/…/pipeline/persist.py")

    def test_elides_more_when_needed(self):
        p = "packages/core/src/repowise/core/pipeline/persist.py"
        self.assertEqual(textfmt.shorten_path(p, 24), "…/pipeline/persist.py")
        self.assertEqual(textfmt.shorten_path(p, 14), "…/persist.py")

    def test_never_cuts_the_file_name(self):
        self.assertEqual(textfmt.shorten_path("a/b/a_very_long_file_name.py", 10), "…/a_very_long_file_name.py")

    def test_root_files(self):
        self.assertEqual(textfmt.shorten_path("Makefile", 5), "Makefile")


class GroupFindings(unittest.TestCase):
    def test_same_title_findings_merge_into_one_with_a_list(self):
        found = [
            {"severity": "info", "title": "One person under several identities", "detail": "a <a@x> merged into A <A@x> by name and email similarity. Add a .mailmap to make it permanent."},
            {"severity": "info", "title": "One person under several identities", "detail": "b <b@x> merged into B <B@x> by name and email similarity. Add a .mailmap to make it permanent."},
            {"severity": "warning", "title": "Bus factor of one", "detail": "Ann wrote 80% of the code that survives today."},
        ]
        grouped = textfmt.group_findings(found)
        self.assertEqual([g["title"] for g in grouped], ["Bus factor of one", "One person under several identities (2)"])
        self.assertEqual(grouped[1]["items"], ["a <a@x> merged into A <A@x> by name and email similarity",
                                               "b <b@x> merged into B <B@x> by name and email similarity"])
        self.assertEqual(grouped[1]["advice"], "Add a .mailmap to make it permanent.")
        self.assertEqual(grouped[0]["items"], ["Ann wrote 80% of the code that survives today."])
        self.assertIsNone(grouped[0]["advice"])

    def test_tally_line(self):
        found = [{"severity": s, "title": s, "detail": ""} for s in ["critical", "warning", "warning", "info", "info", "info"]]
        self.assertEqual(textfmt.tally(found), "1 critical, 2 warnings, 3 notes")
        self.assertEqual(textfmt.tally([]), "nothing flagged")
        self.assertEqual(textfmt.tally(found[3:4]), "1 note")


class SplitAdvice(unittest.TestCase):
    def test_last_sentence_is_advice_when_it_is_an_instruction(self):
        self.assertEqual(textfmt.split_advice("X changed 128 times, versus 51 for the next file (y)."), ("X changed 128 times, versus 51 for the next file (y).", None))
        self.assertEqual(textfmt.split_advice("a <a@x> merged into A <A@x> by name and email similarity. Add a .mailmap to make it permanent."),
                         ("a <a@x> merged into A <A@x> by name and email similarity", "Add a .mailmap to make it permanent."))
        self.assertEqual(textfmt.split_advice("Rotate them; deleting the file does not remove them from git."), ("Rotate them; deleting the file does not remove them from git.", None))
        self.assertEqual(textfmt.split_advice("2 blocks of 30+ duplicated lines. Extract the shared part."), ("2 blocks of 30+ duplicated lines", "Extract the shared part."))


if __name__ == "__main__":
    unittest.main()

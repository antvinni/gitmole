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


class Cut(unittest.TestCase):
    def test_short_string_is_unchanged(self):
        self.assertEqual(textfmt.cut("gitmole/cli.py", 30), "gitmole/cli.py")

    def test_long_string_is_cut_to_exactly_cap_characters_ending_in_the_ellipsis(self):
        name = "a" * 500
        cut = textfmt.cut(name, 10)
        self.assertEqual(len(cut), 10)
        self.assertTrue(cut.endswith(textfmt.ELLIPSIS))


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
        self.assertEqual(grouped[1]["advice"], ["Add a .mailmap to make it permanent."])
        self.assertEqual(grouped[0]["items"], ["Ann wrote 80% of the code that survives today."])
        self.assertEqual(grouped[0]["advice"], [])

    def test_an_explicit_advice_field_is_used_as_is_and_every_distinct_advice_is_kept(self):
        # Re-detecting advice from prose breaks on a name with an initial and keeps only the first
        # item's advice per group; the field carries what the rule meant.
        found = [
            {"severity": "warning", "title": "Repo health", "detail": "Blobs: Maximum size is 240 MiB at v.mp4. Move large files to Git LFS.",
             "advice": "Move large files to Git LFS."},
            {"severity": "info", "title": "Repo health", "detail": "Commits: Count is 900 k. Consider a shallow clone for CI.",
             "advice": "Consider a shallow clone for CI."},
            {"severity": "info", "title": "Repo health", "detail": "Blobs: Total size is 3 GiB. Move large files to Git LFS.",
             "advice": "Move large files to Git LFS."},
            {"severity": "warning", "title": "Bus factor of one", "detail": "Robert C. Martin wrote 90% of the code that survives today. Pair someone with Robert C. Martin before they are unavailable.",
             "advice": "Pair someone with Robert C. Martin before they are unavailable."},
        ]
        grouped = {g["title"]: g for g in textfmt.group_findings(found)}
        health = grouped["Repo health (3)"]
        self.assertEqual(health["items"], ["Blobs: Maximum size is 240 MiB at v.mp4", "Commits: Count is 900 k", "Blobs: Total size is 3 GiB"])
        self.assertEqual(health["advice"], ["Move large files to Git LFS.", "Consider a shallow clone for CI."], "distinct advice, first-seen order")
        bus = grouped["Bus factor of one"]
        self.assertEqual(bus["items"], ["Robert C. Martin wrote 90% of the code that survives today"])
        self.assertEqual(bus["advice"], ["Pair someone with Robert C. Martin before they are unavailable."])

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

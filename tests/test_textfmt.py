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
        self.assertEqual(textfmt.shorten_path(p, 18), "…/persist.py")
        self.assertEqual(textfmt.shorten_path(p, 14), "…/persist.py")

    def test_never_cuts_the_file_name(self):
        self.assertEqual(textfmt.shorten_path("a/b/a_very_long_file_name.py", 10), "…/a_very_long_file_name.py")

    def test_the_nearest_directory_before_the_first_and_the_first_before_none(self):
        # the parent says more about a file than the top directory does: …/BlogListPage/index.tsx
        p = "docs/src/theme/BlogListPage/index.tsx"
        self.assertEqual(textfmt.shorten_path(p, 26), "…/BlogListPage/index.tsx")
        self.assertEqual(textfmt.shorten_path(p, 20), "docs/…/index.tsx")
        self.assertEqual(textfmt.shorten_path(p, 15), "…/index.tsx")

    def test_a_directory_keeps_its_own_name_never_the_empty_one_after_its_slash(self):
        self.assertEqual(textfmt.shorten_path("hindsight-api-slim/", 0), "hindsight-api-slim/")
        self.assertEqual(textfmt.shorten_path("packages/core/src/", 0), "…/src/")
        self.assertEqual(textfmt.shorten_path("packages/core/src/", 12), "…/core/src/")
        self.assertEqual(textfmt.shorten_path("packages/core/src/", 16), "…/core/src/")

    def test_cut_path_cuts_a_directory_name_in_its_middle_keeping_the_slash(self):
        cut = textfmt.cut_path("hindsight-api-slim/", 14)
        self.assertEqual(len(cut), 14)
        self.assertTrue(cut.startswith("hindsi") and cut.endswith("-slim/") and "…" in cut, cut)
        self.assertEqual(textfmt.cut_path("a/b/memory_engine.py", 12), textfmt.cut_middle("…/memory_engine.py", 12))

    def test_a_form_that_also_reads_as_another_path_is_passed_over(self):
        # paperclip: ui/…/IssueProperties.tsx is the component and a one-line re-export beside it
        real, reexport = "ui/src/components/issue-properties/IssueProperties.tsx", "ui/src/components/IssueProperties.tsx"
        self.assertEqual(textfmt.shorten_path(real, 26), "ui/…/IssueProperties.tsx")
        self.assertEqual(textfmt.shorten_path(real, 26, [real, reexport]), "…/issue-properties/IssueProperties.tsx")
        self.assertEqual(textfmt.shorten_path(reexport, 33, [real, reexport]), "…/components/IssueProperties.tsx")
        self.assertEqual(textfmt.shorten_path(real, 40, [real, reexport]), "…/issue-properties/IssueProperties.tsx")

    def test_more_directories_are_kept_until_the_form_names_one_path(self):
        a, b = "x/a/core/src/index.ts", "x/b/core/src/index.ts"
        self.assertEqual(textfmt.shorten_path(a, 0, [a, b]), "…/a/core/src/index.ts")
        self.assertEqual(textfmt.shorten_path("x/y/index.ts", 0, ["x/y/index.ts", "x/index.ts"]), "…/y/index.ts")
        self.assertEqual(textfmt.shorten_path("a/b.ts", 0, ["a/b.ts", "c/a/b.ts"]), "a/b.ts", "no shorter form names it alone")

    def test_a_line_after_the_path_is_not_part_of_it(self):
        real = "ui/src/components/issue-properties/IssueProperties.tsx:12"
        self.assertEqual(textfmt.shorten_path(real, 0, ["ui/src/components/IssueProperties.tsx"]), "…/issue-properties/IssueProperties.tsx:12")

    def test_cut_path_keeps_the_usual_form_when_the_one_that_tells_them_apart_does_not_fit(self):
        real, reexport = "ui/src/components/issue-properties/IssueProperties.tsx", "ui/src/components/IssueProperties.tsx"
        self.assertEqual(textfmt.cut_path(real, 40, [reexport]), "…/issue-properties/IssueProperties.tsx")
        self.assertEqual(textfmt.cut_path(real, 26, [reexport]), "…/iss…/IssueProperties.tsx", "the parent directory is cut, not the name")
        # the same parent on both sides: no start of it tells them apart, and the name is never cut for it
        a, b = "server/wake-queue/application/use-cases.ts", "server/other/application/use-cases.ts"
        self.assertEqual(textfmt.cut_path(a, 34, [b]), "server/…/application/use-cases.ts")
        self.assertEqual(textfmt.cut_path(real + ":12", 29, [reexport]), "…/iss…/IssueProperties.tsx:12")

    def test_root_files(self):
        self.assertEqual(textfmt.shorten_path("Makefile", 5), "Makefile")


class JoinAnd(unittest.TestCase):
    def test_one_two_and_three_items(self):
        self.assertEqual(textfmt.join_and([]), "")
        self.assertEqual(textfmt.join_and(["a"]), "a")
        self.assertEqual(textfmt.join_and(["a", "b"]), "a and b")
        self.assertEqual(textfmt.join_and(["a", "b", "c"]), "a, b and c")


class Cut(unittest.TestCase):
    def test_short_string_is_unchanged(self):
        self.assertEqual(textfmt.cut("gitmole/cli.py", 30), "gitmole/cli.py")

    def test_long_string_is_cut_to_exactly_cap_characters_ending_in_the_ellipsis(self):
        name = "a" * 500
        cut = textfmt.cut(name, 10)
        self.assertEqual(len(cut), 10)
        self.assertTrue(cut.endswith(textfmt.ELLIPSIS))


class CutMiddle(unittest.TestCase):
    def test_fits_unchanged(self):
        self.assertEqual(textfmt.cut_middle("Palash Debnath", 14), "Palash Debnath")

    def test_words_stay_whole_and_the_tail_is_kept(self):
        self.assertEqual(textfmt.cut_middle("Claude Opus 4.8 (1M context) (15%)", 29), "Claude Opus 4.8 … (15%)")

    def test_an_identifier_keeps_its_last_segment(self):
        cut = textfmt.cut_middle("dub_transcribe_stream._gen_body", 24)
        self.assertEqual(len(cut), 24)
        self.assertTrue(cut.endswith("._gen_body"))
        self.assertIn("…", cut)


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

import unittest

from gitmole.measure import claims


def finding(detail, advice="", rule="a_rule"):
    return {"detail": detail, "advice": advice, "rule": {"id": rule}}


def kinds(detail, advice=""):
    return sorted(k for k, _ in claims.complaints(finding(detail, advice)))


class EmptySlot(unittest.TestCase):
    """What joining an empty list into a sentence leaves behind. Every example is a real one."""

    def test_empty_parentheses(self):
        self.assertEqual(kinds("facebook-access-token in (unreachable blob 00db21063ea1) ()."),
                         ["empty parentheses"], "react's one critical finding at 0.33.0")

    def test_a_list_that_opens_with_its_separator(self):
        self.assertEqual(kinds("generic-password in (unreachable blob 742c1cc5ebfb) and 3 other files (, d61f33f and 6 more)."),
                         ["list opens with a separator"], "django's, from an empty commit joined into the list")

    def test_nothing_left_to_name(self):
        self.assertIn("nothing left to name", kinds("4 files changed and 0 more."))

    def test_a_clean_sentence_is_clean(self):
        self.assertEqual(kinds("2 secrets in history: generic-api-key in app/settings.py (c1, c2)."), [])

    def test_parentheses_a_name_owns_are_not_a_defect(self):
        """Both of these were false positives before this landed: the check only fires where prose
        joined an empty list, which is after a space."""
        self.assertEqual(kinds("62 functions are both long and complex: errg.Go(func() error { "
                               "(discovery/aws/rds.go:542) complexity 166, 482 lines, 0 params."), [],
                         "a Go function whose name holds ()")
        self.assertEqual(kinds("75 commits each touch 30 files or more: d6eaf7c018 (339 files, 2017-01-21, "
                               "Refs #23919 -- Replaced super(ClassName, self) with super().) and 72 more."), [],
                         "a commit subject quoting super()")


class Agreement(unittest.TestCase):
    def test_one_does_not_take_a_plural(self):
        self.assertEqual(kinds("curl_easy_strerror (lib/strerror.c) complexity 90, 187 lines, 1 params."),
                         ["one takes a plural"], "curl, binutils-gdb, coredns and prometheus at 0.33.0")
        self.assertEqual(kinds('"Ann <ann@example.org>" made 1 commits (100%).'),
                         ["one takes a plural"], "placeholder_identity, on every fixture it fires on")

    def test_a_count_reaches_past_the_words_between_it_and_its_noun(self):
        self.assertEqual(kinds("change together 65% of the time (1 more pairs like them)."),
                         ["one takes a plural"], "gitmole's own hidden_coupling at 0.33.0")

    def test_a_malformed_plural(self):
        self.assertIn("malformed plural", kinds("2 IPv4 addresss in string literals in 1 source file."))

    def test_a_singular_that_ends_in_s_is_not_a_plural(self):
        for noun in ("1 class", "1 process", "1 status", "1 analysis"):
            self.assertEqual(kinds(f"{noun} was found."), [], noun)

    def test_the_parenthesised_plural_is_read_as_the_singular(self):
        self.assertEqual(kinds("1 area(s) with at least 200 lines were written almost entirely by one person."), [],
                         "the (s) spelling is a judgement, not a defect; advisory() has it")
        self.assertIn("the (s) spelling", [k for k, _ in claims.advisory(finding("1 area(s) with 200 lines."))])


class Repeats(unittest.TestCase):
    def test_the_same_entry_twice(self):
        detail = ("2 distinct values in 2 places: facebook-access-token in (unreachable blob 00db21063ea1); "
                  "facebook-access-token in (unreachable blob 00db21063ea1). Rotate them.")
        self.assertIn("the same entry twice", kinds(detail, advice="Rotate them."))

    def test_two_entries_that_differ_are_not_a_repeat(self):
        detail = ("2 distinct values: generic-api-key in a.py (c1); generic-api-key in b.py (c2). Rotate them.")
        self.assertEqual(kinds(detail, advice="Rotate them."), [])


class Advisory(unittest.TestCase):
    """Judgements, never counted as defects: they are the shapes with a known false-positive rate."""

    def test_many_with_a_singular_is_advisory_only(self):
        self.assertEqual(kinds("23 of 78 findings were labelled."), [])
        self.assertTrue([k for k, _ in claims.advisory(finding("5 commit touched it."))])


class OverAReport(unittest.TestCase):
    def test_it_counts_findings_not_complaints(self):
        found = [finding("1 params here.", rule="brain_methods"),          # one finding, one complaint
                 finding("1 params and () there.", rule="brain_methods"),  # one finding, two complaints
                 finding("all well here.", rule="reverts")]
        out = claims.over(found)
        self.assertEqual((out["checked"], out["clean"]), (3, 1))
        self.assertEqual([c["kind"] for c in out["complaints"]],
                         ["empty parentheses", "one takes a plural", "one takes a plural"])
        self.assertEqual({c["rule"] for c in out["complaints"]}, {"brain_methods"})

    def test_a_report_with_no_findings(self):
        self.assertEqual(claims.over([]), {"checked": 0, "clean": 0, "complaints": [], "advisory": 0})


if __name__ == "__main__":
    unittest.main()

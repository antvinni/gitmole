import unittest

from gitmole import identity


IDS = [
    {"name": "Grzegorz Bankosz", "email": "g@thg.com", "commits": 25},
    {"name": "thg-grzegorz-bankosz", "email": "1@users.noreply.github.com", "commits": 16},
    {"name": "Bob", "email": "bob@x.com", "commits": 40},
    {"name": "Robert", "email": "bob@x.com", "commits": 2},
    {"name": "Ann", "email": "ann@x.com", "commits": 7},
]


class Merge(unittest.TestCase):
    def test_groups_by_shared_name_tokens_or_same_email(self):
        merged = identity.merge(IDS)
        names = [m["name"] for m in merged]
        self.assertEqual(names, ["Bob", "Grzegorz Bankosz", "Ann"])

    def test_an_identical_handle_under_several_emails_is_one_person(self):
        ids = [{"name": "KaKa", "email": "kaka@a.com", "commits": 57}, {"name": "KaKa", "email": "23028015+climba@users.noreply.github.com", "commits": 56},
               {"name": "kaka", "email": "climba@b.com", "commits": 10}, {"name": "namusyaka", "email": "n@a.com", "commits": 180},
               {"name": "namusyaka", "email": "n@b.com", "commits": 8}, {"name": "Li Yu", "email": "li@a.com", "commits": 5},
               {"name": "Li Yu", "email": "li@b.com", "commits": 3}]
        merged = {m["name"]: m["commits"] for m in identity.merge(ids)}
        self.assertEqual(merged, {"KaKa": 123, "namusyaka": 188, "Li Yu": 8})

    def test_a_handle_that_is_one_distinctive_word_of_a_fuller_name_is_the_same_person(self):
        ids = [{"name": "Junegunn Choi", "email": "junegunn.c@a.com", "commits": 2924}, {"name": "junegunn", "email": "junegunn@b.com", "commits": 123},
               {"name": "Sam Altman", "email": "sam@a.com", "commits": 5}, {"name": "sam", "email": "sam@b.com", "commits": 2},
               {"name": "Kevin Brown", "email": "kb@a.com", "commits": 76}, {"name": "Kevin", "email": "k@b.com", "commits": 21}]
        merged = {m["name"]: m["commits"] for m in identity.merge(ids)}
        self.assertEqual(merged, {"Junegunn Choi": 3047, "Sam Altman": 5, "sam": 2, "Kevin Brown": 76, "Kevin": 21},
                         "a short or common first name is not distinctive enough")

    def test_a_handle_that_is_the_full_name_run_together_is_the_same_person(self):
        ids = [{"name": "Robin Malfait", "email": "malfait.robin@a.com", "commits": 1271}, {"name": "RobinMalfait", "email": "1834413+RobinMalfait@users.noreply.github.com", "commits": 4},
               {"name": "Jo Li", "email": "jo@a.com", "commits": 3}, {"name": "joli", "email": "x@b.com", "commits": 1}]
        merged = {m["name"]: m["commits"] for m in identity.merge(ids)}
        self.assertEqual(merged, {"Robin Malfait": 1275, "Jo Li": 3, "joli": 1}, "a run-together name shorter than six letters could be anyone")

    def test_a_handle_of_initial_plus_surname_is_the_same_person(self):
        ids = [{"name": "Niels Lohmann", "email": "mail@nlohmann.me", "commits": 3000}, {"name": "nlohmann", "email": "niels.lohmann@x.com", "commits": 60},
               {"name": "Jo Li", "email": "jo@a.com", "commits": 3}, {"name": "jli", "email": "x@b.com", "commits": 1}]
        merged = {m["name"]: m["commits"] for m in identity.merge(ids)}
        self.assertEqual(merged, {"Niels Lohmann": 3060, "Jo Li": 3, "jli": 1}, "an initial plus a short surname could be anyone")

    def test_a_bare_common_first_name_is_not_enough(self):
        ids = [{"name": "Jean", "email": "jean@a.com", "commits": 24}, {"name": "Jean", "email": "jean@b.com", "commits": 18},
               {"name": "Alex", "email": "alex@a.com", "commits": 3}, {"name": "alex", "email": "alex@b.com", "commits": 2}]
        self.assertEqual(len(identity.merge(ids)), 4, "two Jeans and two Alexes may be four people")

    def test_merged_row_sums_commits_and_lists_aliases(self):
        merged = {m["name"]: m for m in identity.merge(IDS)}
        self.assertEqual(merged["Grzegorz Bankosz"]["commits"], 41)
        self.assertEqual(merged["Grzegorz Bankosz"]["email"], "g@thg.com")
        self.assertEqual(merged["Grzegorz Bankosz"]["aliases"], [{"name": "thg-grzegorz-bankosz", "email": "1@users.noreply.github.com", "commits": 16}])
        self.assertEqual(merged["Bob"]["commits"], 42)
        self.assertEqual(merged["Ann"]["aliases"], [])

    def test_canonical_map_covers_every_alias_name(self):
        merged = identity.merge(IDS)
        m = identity.canonical_names(merged)
        self.assertEqual(m["thg-grzegorz-bankosz"], "Grzegorz Bankosz")
        self.assertEqual(m["Robert"], "Bob")
        self.assertEqual(m["Ann"], "Ann")

    def test_merging_is_transitive_through_a_third_identity(self):
        # A and B share nothing; C matches A by email and B by name tokens, so all three are one person.
        ids = [{"name": "Hayden", "email": "a@x.com", "commits": 10},
               {"name": "hay-kot", "email": "b@x.com", "commits": 5},
               {"name": "hay kot", "email": "a@x.com", "commits": 1}]
        merged = identity.merge(ids)
        self.assertEqual(len(merged), 1, "the third identity joins the first two groups")
        self.assertEqual(merged[0]["name"], "Hayden")
        self.assertEqual(merged[0]["commits"], 16)
        self.assertEqual(sorted(a["name"] for a in merged[0]["aliases"]), ["hay kot", "hay-kot"])

    def test_the_mealie_shape_is_one_person(self):
        ids = [{"name": "Hayden", "email": "1+hay-kot@users.noreply.github.com", "commits": 1495},
               {"name": "hay-kot", "email": "hay-kot@pm.me", "commits": 312},
               {"name": "hay-kot", "email": "1+hay-kot@users.noreply.github.com", "commits": 40},
               {"name": "Hayden", "email": "hay-kot@pm.me", "commits": 30}]
        merged = identity.merge(ids)
        self.assertEqual([m["name"] for m in merged], ["Hayden"])
        self.assertEqual(merged[0]["commits"], 1877)
        self.assertEqual(len(merged[0]["aliases"]), 3)

    def test_empty(self):
        self.assertEqual(identity.merge([]), [])


class IsBot(unittest.TestCase):
    def test_bracketed_bot_suffix_and_the_well_known_names(self):
        for name, email in [("renovate[bot]", "29139614+renovate[bot]@users.noreply.github.com"),
                            ("github-actions[bot]", "41898282+github-actions[bot]@users.noreply.github.com"),
                            ("dependabot[bot]", "support@github.com"), ("Dependabot", "dependabot@example.com"),
                            ("Renovate Bot", "bot@renovateapp.com"), ("GitHub Actions", "actions@github.com"),
                            ("Copilot", "198982749+Copilot@users.noreply.github.com"), ("Cursor Agent", "cursoragent@cursor.com"),
                            ("Deploy from CI", ""), ("Release Bot", "release@x.com"), ("CI", "ci@x.com"), ("Homebrew Automation", "a@x.com"),
                            ("hugoreleaser", "hugoreleaser@x.com"), ("semantic-release-bot", "s@x.com")]:
            self.assertTrue(identity.is_bot(name, email), (name, email))

    def test_people_are_not_bots(self):
        for name, email in [("Ann", "ann@x.com"), ("Bob Otte", "bot@x.com"), ("Robot Lee", "r@x.com"), ("hay-kot", "hay-kot@pm.me")]:
            self.assertFalse(identity.is_bot(name, email), (name, email))


if __name__ == "__main__":
    unittest.main()

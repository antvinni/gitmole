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

    def test_empty(self):
        self.assertEqual(identity.merge([]), [])


class IsBot(unittest.TestCase):
    def test_bracketed_bot_suffix_and_the_well_known_names(self):
        for name, email in [("renovate[bot]", "29139614+renovate[bot]@users.noreply.github.com"),
                            ("github-actions[bot]", "41898282+github-actions[bot]@users.noreply.github.com"),
                            ("dependabot[bot]", "support@github.com"), ("Dependabot", "dependabot@example.com"),
                            ("Renovate Bot", "bot@renovateapp.com"), ("GitHub Actions", "actions@github.com")]:
            self.assertTrue(identity.is_bot(name, email), (name, email))

    def test_people_are_not_bots(self):
        for name, email in [("Ann", "ann@x.com"), ("Bob Otte", "bot@x.com"), ("Robot Lee", "r@x.com"), ("hay-kot", "hay-kot@pm.me")]:
            self.assertFalse(identity.is_bot(name, email), (name, email))


if __name__ == "__main__":
    unittest.main()

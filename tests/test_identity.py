import unittest

from gitmole import identity


IDS = [
    {"name": "Grzegorz Bankosz", "email": "g@a.com", "commits": 25},
    {"name": "thg-grzegorz-bankosz", "email": "1@users.noreply.github.com", "commits": 16},
    {"name": "Bob", "email": "bob@x.com", "commits": 40},
    {"name": "Robert", "email": "bob@x.com", "commits": 2},
    {"name": "Ann", "email": "ann@x.com", "commits": 7},
]


class Merge(unittest.TestCase):
    def test_a_shared_no_reply_mailbox_does_not_make_two_names_one_person(self):
        ids = [{"name": "Tool Alpha", "email": "noreply@service.example", "commits": 9},
               {"name": "Tool Beta", "email": "noreply@service.example", "commits": 4},
               {"name": "Tool Alpha (large)", "email": "noreply@service.example", "commits": 2},
               {"name": "Helper", "email": "no-reply@other.example", "commits": 3},
               {"name": "Assistant", "email": "No-Reply@other.example", "commits": 1}]
        merged = {m["name"]: m["commits"] for m in identity.merge(ids)}
        self.assertEqual(merged, {"Tool Alpha": 11, "Tool Beta": 4, "Helper": 3, "Assistant": 1},
                         "the mailbox names no one; two names that match on their own still merge")

    def test_an_empty_email_does_not_make_two_names_one_person(self):
        ids = [{"name": "Dao Cong Tien", "email": "", "commits": 2}, {"name": "Nguyen Van Trung", "email": "", "commits": 1}]
        self.assertEqual(len(identity.merge(ids)), 2)

    def test_a_per_account_github_no_reply_address_still_merges(self):
        ids = [{"name": "antvinni", "email": "5262575+antvinni@users.noreply.github.com", "commits": 9},
               {"name": "vinni", "email": "5262575+antvinni@users.noreply.github.com", "commits": 4},
               {"name": "someone", "email": "someone@users.noreply.github.com", "commits": 1},
               {"name": "some one", "email": "someone@users.noreply.github.com", "commits": 1}]
        self.assertEqual({m["name"]: m["commits"] for m in identity.merge(ids)}, {"antvinni": 13, "someone": 2})

    def test_shared_mailbox_is_a_shape(self):
        for email in ("noreply@x.example", "no-reply@x.example", "no_reply@x.example", "donotreply@x.example", "do-not-reply@x.example", "", "  "):
            self.assertTrue(identity.shared_mailbox(email), email)
        for email in ("1+a@users.noreply.github.com", "a@users.noreply.github.com", "noreplyer@x.example", "ann@x.example", "reply@x.example"):
            self.assertFalse(identity.shared_mailbox(email), email)

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

    def test_a_first_name_handle_joins_a_full_name_only_when_an_address_ties_them(self):
        # hindsight: co-author "andrew <andrew.neeser@…>" was merged into Andrew Barnes <bortstheboat@…> on the first name alone
        ids = [{"name": "Andrew Barnes", "email": "bortstheboat@a.com", "commits": 2}, {"name": "andrew", "email": "andrew.neeser@b.com", "commits": 1},
               {"name": "Marcus Holloway", "email": "mh@a.com", "commits": 9}, {"name": "marcus", "email": "marcus.holloway@b.com", "commits": 3},
               {"name": "Bartholomew Chen", "email": "bartholomew@a.com", "commits": 7}, {"name": "bartholomew", "email": "b@c.com", "commits": 2}]
        merged = {m["name"]: m["commits"] for m in identity.merge(ids)}
        self.assertEqual(merged, {"Andrew Barnes": 2, "andrew": 1, "Marcus Holloway": 12, "Bartholomew Chen": 9},
                         "the handle's mailbox names the surname, or the full name's mailbox is the handle")

    def test_a_handle_that_is_the_full_name_run_together_is_the_same_person(self):
        ids = [{"name": "Robin Malfait", "email": "malfait.robin@a.com", "commits": 1271}, {"name": "RobinMalfait", "email": "1834413+RobinMalfait@users.noreply.github.com", "commits": 4},
               {"name": "Jo Li", "email": "jo@a.com", "commits": 3}, {"name": "joli", "email": "x@b.com", "commits": 1}]
        merged = {m["name"]: m["commits"] for m in identity.merge(ids)}
        self.assertEqual(merged, {"Robin Malfait": 1275, "Jo Li": 3, "joli": 1}, "a run-together name shorter than six letters could be anyone")

    def test_a_handle_of_initial_plus_surname_is_the_same_person(self):
        ids = [{"name": "Niels Lohmann", "email": "mail@a.com", "commits": 3000}, {"name": "nlohmann", "email": "niels.lohmann@x.com", "commits": 60},
               {"name": "Jo Li", "email": "jo@a.com", "commits": 3}, {"name": "jli", "email": "x@b.com", "commits": 1}]
        merged = {m["name"]: m["commits"] for m in identity.merge(ids)}
        self.assertEqual(merged, {"Niels Lohmann": 3060, "Jo Li": 3, "jli": 1}, "an initial plus a short surname could be anyone")

    def test_a_bare_common_first_name_is_not_enough(self):
        ids = [{"name": "Jean", "email": "jean@a.com", "commits": 24}, {"name": "Jean", "email": "jean@b.com", "commits": 18},
               {"name": "Alex", "email": "alex@a.com", "commits": 3}, {"name": "alex", "email": "alex@b.com", "commits": 2}]
        self.assertEqual(len(identity.merge(ids)), 4, "two Jeans and two Alexes may be four people")

    def test_a_word_two_peoples_full_names_share_names_neither_of_them(self):
        # django: a bare "Jannis" under Jannis Vajen's email pulled Jannis Leidel's 895 commits into one row, and "david"
        # is David Smith's or David Sanders's; Tom Tromey spelt twice is still one person, so tromey stays his
        ids = [{"name": "Jannis Leidel", "email": "jannis@a.com", "commits": 895}, {"name": "Jannis Vajen", "email": "jvajen@b.com", "commits": 2},
               {"name": "Jannis", "email": "jvajen@b.com", "commits": 1}, {"name": "jannis", "email": "j@c.com", "commits": 1},
               {"name": "David Smith", "email": "smithdc@a.com", "commits": 134}, {"name": "David Sanders", "email": "ds@a.com", "commits": 41},
               {"name": "david", "email": "dakrauth@b.com", "commits": 1},
               {"name": "Tom Tromey", "email": "tom@a.com", "commits": 3686}, {"name": "Author: Tom Tromey", "email": "tom@a.com", "commits": 1},
               {"name": "Tom Tromey", "email": "tromey@b.com", "commits": 1703}, {"name": "tromey", "email": "tromey@svn", "commits": 2}]
        self.assertEqual(identity.shared_words(ids), frozenset({"jannis", "david"}))
        merged = {m["name"]: m["commits"] for m in identity.merge(ids)}
        self.assertEqual(merged, {"Jannis Leidel": 895, "Jannis Vajen": 3, "jannis": 1, "David Smith": 134, "David Sanders": 41, "david": 1,
                                  "Tom Tromey": 5392})

    def test_a_bare_given_name_joins_nobody_by_name_alone(self):
        # flink's three Jacks under three unrelated emails, and a Steve beside django's one Steve Hiemstra
        ids = [{"name": "Jack", "email": "jack1@a.com", "commits": 2}, {"name": "Jack", "email": "jack2@b.com", "commits": 1},
               {"name": "Jack", "email": "1+bytesandwich@users.noreply.github.com", "commits": 1},
               {"name": "Steve Hiemstra", "email": "speggy@a.com", "commits": 1}, {"name": "Steve", "email": "steve.k@b.com", "commits": 1}]
        self.assertEqual(len(identity.merge(ids)), 5)

    def test_merged_row_sums_commits_and_lists_aliases(self):
        merged = {m["name"]: m for m in identity.merge(IDS)}
        self.assertEqual(merged["Grzegorz Bankosz"]["commits"], 41)
        self.assertEqual(merged["Grzegorz Bankosz"]["email"], "g@a.com")
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
               {"name": "hay-kot", "email": "hay-kot@b.com", "commits": 312},
               {"name": "hay-kot", "email": "1+hay-kot@users.noreply.github.com", "commits": 40},
               {"name": "Hayden", "email": "hay-kot@b.com", "commits": 30}]
        merged = identity.merge(ids)
        self.assertEqual([m["name"] for m in merged], ["Hayden"])
        self.assertEqual(merged[0]["commits"], 1877)
        self.assertEqual(len(merged[0]["aliases"]), 3)

    def test_a_forge_login_names_the_account_it_belongs_to(self):
        # univer: "Univer" commits under DR-Univer's per-account address, and DR-Univer commits under wbfsa@qq.com
        ids = [{"name": "Univer", "email": "68851825+DR-Univer@users.noreply.github.com", "commits": 561},
               {"name": "DR-Univer", "email": "wbfsa@qq.com", "commits": 48},
               {"name": "Mona Lind", "email": "7+monalind@users.noreply.github.com", "commits": 9},
               {"name": "M. L.", "email": "monalind@x.example", "commits": 2},
               # univer again: the forge kept the login's capital, and the other identity writes it in lower case
               {"name": "Gpound.liu", "email": "141617023+Gggpound@users.noreply.github.com", "commits": 181},
               {"name": "gggpound", "email": "gpoundLiu@x.example", "commits": 10}]
        merged = {m["name"]: m["commits"] for m in identity.merge(ids)}
        self.assertEqual(merged, {"Univer": 609, "Mona Lind": 11, "Gpound.liu": 191}, "a login equal to a one-word name or to a mailbox")
        self.assertEqual(identity._forge_login("68851825+DR-Univer@users.noreply.github.com"), "DR-Univer")
        self.assertEqual(identity._forge_login("dr-univer@users.noreply.github.com"), "dr-univer")
        self.assertEqual(identity._forge_login("wbfsa@qq.com"), "")

    def test_a_login_written_as_a_given_name_or_a_bare_no_reply_mailbox_joins_nobody(self):
        ids = [{"name": "Jack Doe", "email": "1+jack@users.noreply.github.com", "commits": 5},
               {"name": "Jack", "email": "j@x.example", "commits": 1},
               {"name": "Ann Roe", "email": "2+robin@users.noreply.github.com", "commits": 4},
               {"name": "Robin", "email": "r@y.example", "commits": 1},
               {"name": "Tool", "email": "noreply@users.noreply.github.com", "commits": 3},
               {"name": "noreply", "email": "n@z.example", "commits": 1}]
        self.assertEqual(len(identity.merge(ids)), 6, "Jack and Robin are written as given names, noreply@ names no one")
        self.assertEqual(identity._forge_login("noreply@users.noreply.github.com"), "")

    def test_a_login_that_two_full_names_share_joins_nobody(self):
        ids = [{"name": "Morgan Hale", "email": "m@a.example", "commits": 3}, {"name": "Morgan Pike", "email": "p@b.example", "commits": 2},
               {"name": "Kim Roe", "email": "3+morgan@users.noreply.github.com", "commits": 1}, {"name": "morgan", "email": "x@c.example", "commits": 1}]
        self.assertEqual(len(identity.merge(ids)), 4)

    def test_empty(self):
        self.assertEqual(identity.merge([]), [])


class IsBot(unittest.TestCase):
    def test_bracketed_bot_suffix_and_names_that_say_bot_ci_deploy_or_automation(self):
        for name, email in [("renovate[bot]", "29139614+renovate[bot]@users.noreply.github.com"),
                            ("github-actions[bot]", "41898282+github-actions[bot]@users.noreply.github.com"),
                            ("dependabot[bot]", "support@github.com"), ("Renovate Bot", "bot@renovateapp.com"),
                            ("Deploy from CI", ""), ("Release Bot", "release@x.com"), ("CI", "ci@x.com"), ("Homebrew Automation", "a@x.com"),
                            ("hugoreleaser", "hugoreleaser@x.com"), ("semantic-release-bot", "s@x.com")]:
            self.assertTrue(identity.is_bot(name, email), (name, email))

    def test_people_and_bare_product_names_are_not_bots(self):
        # a product name is not a rule: GitHub declares its bots with the [bot] suffix, and a name that
        # declares nothing is a person until an alias of it declares otherwise
        for name, email in [("Ann", "ann@x.com"), ("Bob Otte", "bot@x.com"), ("Robot Lee", "r@x.com"), ("hay-kot", "hay-kot@b.com"),
                            ("Dependabot", "dependabot@example.com"), ("Copilot", "198982749+Copilot@users.noreply.github.com"),
                            ("Cursor Agent", "cursoragent@cursor.com"), ("GitHub Actions", "actions@github.com")]:
            self.assertFalse(identity.is_bot(name, email), (name, email))

    def test_an_identity_that_merges_with_a_declared_bot_is_a_bot(self):
        # fastapi: 2237 commits as "github-actions <github-actions@github.com>" beside 828 as github-actions[bot]
        rows = [{"name": "github-actions", "email": "github-actions@github.com", "commits": 2237},
                {"name": "github-actions[bot]", "email": "41898282+github-actions[bot]@users.noreply.github.com", "commits": 828},
                {"name": "Ann", "email": "a@x.com", "commits": 5}, {"name": "Copilot", "email": "c@x.com", "commits": 1}]
        self.assertEqual(identity.bot_names(rows), {"github-actions", "github-actions[bot]"})
        self.assertEqual(identity.bot_names([]), set())


if __name__ == "__main__":
    unittest.main()


def _merge_all_pairs(identities):
    """identity.merge as it was before the key index: every identity against every member of every
    group. The index must give the same groups, in the same order, with the same alias order."""
    shared = identity.shared_words(identities)
    groups = []
    for i in identities:
        matched = [g for g in groups if any(identity.same_person(i, j, shared) for j in g)]
        if not matched:
            groups.append([i])
            continue
        first = matched[0]
        first.append(i)
        for other in matched[1:]:
            first.extend(other)
            groups.remove(other)
    merged = []
    for g in groups:
        g = sorted(g, key=lambda x: -x["commits"])
        merged.append({"name": g[0]["name"], "email": g[0]["email"], "commits": sum(x["commits"] for x in g),
                       "aliases": [{"name": x["name"], "email": x["email"], "commits": x["commits"]} for x in g[1:]]})
    merged.sort(key=lambda m: (-m["commits"], m["name"]))
    return merged


def _history(seed, n):
    """Identities built from a small vocabulary, so that every way same_person can match turns up:
    shared emails, two shared tokens, identical handles, a handle inside a full name, a name run
    together, an initial plus a surname, and given names that must stay apart."""
    import random
    rnd = random.Random(seed)
    first = ["Jack", "David", "Niels", "Robin", "Junegunn", "Tom", "Ann", "Hayden"]
    last = ["Lohmann", "Malfait", "Choi", "Tromey", "Smith", "Sanders", "Kot", "Bankosz"]
    out = []
    for k in range(n):
        f, l = rnd.choice(first), rnd.choice(last)
        shape = rnd.randrange(7)
        name = [f"{f} {l}", f"{f}{l}", f"{f[0].lower()}{l.lower()}", f.lower() + l.lower(), f, l.lower(), f"Author: {f} {l}"][shape]
        email = rnd.choice([f"{f.lower()}@x.org", f"{l.lower()}@y.org", f"{k}@users.noreply.github.com",
                            f"{k}+{l.lower()}@users.noreply.github.com", f"{k}+{f}{l}@users.noreply.github.com"])
        out.append({"name": name, "email": email, "commits": rnd.randrange(1, 6)})
    return out


class KeyIndex(unittest.TestCase):
    def test_merge_gives_exactly_what_comparing_every_pair_gives(self):
        for seed in range(40):
            ids = _history(seed, 60)
            self.assertEqual(identity.merge([dict(i) for i in ids]), _merge_all_pairs([dict(i) for i in ids]), f"seed {seed}")

    def test_people_who_share_nothing_are_not_compared_with_each_other(self):
        from unittest import mock
        ids = [{"name": f"Person{k:04d} Surname{k:04d}", "email": f"p{k}@x.org", "commits": 1} for k in range(400)]
        with mock.patch.object(identity, "same_person", wraps=identity.same_person) as compared:
            merged = identity.merge(ids)
        self.assertEqual(len(merged), 400)
        self.assertLess(compared.call_count, 400, "all pairs would be 79,800 comparisons")


class Tools(unittest.TestCase):
    """A coding tool is told by shape: one of several names on one bare no-reply address."""

    def test_someone_credited_only_by_trailers_is_a_person(self):
        self.assertEqual(identity.tools([{"name": "Helper", "email": "h@x.org", "commits": 9, "authored": 0}]), set())

    def test_names_sharing_a_bare_no_reply_address_are_a_tool_and_per_user_addresses_are_people(self):
        ids = [{"name": "Model A", "email": "noreply@vendor.example", "commits": 9, "authored": 1},
               {"name": "Model B", "email": "no-reply@vendor.example", "commits": 3, "authored": 1,
                "aliases": [{"name": "Model B2", "email": "noreply@vendor.example", "commits": 1}]},
               {"name": "Ann", "email": "12+ann@users.noreply.example", "commits": 40, "authored": 40},
               {"name": "Bo", "email": "12+bo@users.noreply.example", "commits": 5, "authored": 5}]
        self.assertEqual(identity.tools(ids), {"Model A", "Model B"})

    def test_one_person_on_a_no_reply_address_is_a_person(self):
        self.assertEqual(identity.tools([{"name": "Ann", "email": "noreply@ann.example", "commits": 40, "authored": 40},
                                         {"name": "Old", "email": "o@x.org", "commits": 4}]), set())

    def test_a_name_a_person_also_carries_is_not_a_tool(self):
        ids = [{"name": "pukkandan", "email": "p@x.org", "commits": 1629, "authored": 1616},
               {"name": "pukkandan", "email": "noreply@v.example", "commits": 1, "authored": 0},
               {"name": "Model A", "email": "noreply@v.example", "commits": 9, "authored": 0}]
        self.assertEqual(identity.tools(ids), {"Model A"})

    def test_same_name_rows_that_authored_nothing_of_their_own_do_not_veto_a_tool(self):
        # paperclip: the product's agent on its shared mailbox, and two stray trailer-only rows of the same name
        ids = [{"name": "Dev", "email": "dev@x.org", "commits": 2900, "authored": 2900},
               {"name": "Agent", "email": "noreply@product.example", "commits": 2052, "authored": 2},
               {"name": "Agent CTO", "email": "noreply@product.example", "commits": 2, "authored": 0},
               {"name": "Agent", "email": "agent@product.example", "commits": 2, "authored": 0},
               {"name": "Agent", "email": "agent@users.noreply.example", "commits": 1, "authored": 0}]
        self.assertEqual(identity.tools(ids), {"Agent", "Agent CTO"})

    def test_one_name_on_a_bare_no_reply_mailbox_credited_by_trailers_is_a_tool(self):
        self.assertEqual(identity.tools([{"name": "Model", "email": "noreply@vendor.example", "commits": 20, "authored": 2},
                                         {"name": "Ann", "email": "a@x.org", "commits": 40, "authored": 40}]), {"Model"})
        self.assertEqual(identity.tools([{"name": "Model", "email": "noreply@vendor.example", "commits": 20, "authored": 3}]), set(),
                         "authoring more than one commit in ten is committing one's own work")

    def test_trailer_credits_on_an_address_naming_someone_are_a_person(self):
        # django's 71: credited only by trailers, on personal or per-account addresses
        ids = [{"name": "Helper", "email": "h@x.org", "commits": 9, "authored": 0},
               {"name": "Other", "email": "7+other@users.noreply.github.com", "commits": 3, "authored": 0},
               {"name": "Third", "email": "t@x.org", "commits": 2, "authored": 0, "aliases": [{"name": "Third", "email": "noreply@t.example", "commits": 1}]}]
        self.assertEqual(identity.tools(ids), set())

    def test_a_person_whose_own_trailer_used_the_tools_mailbox_is_a_person(self):
        # hindsight: TuftyBruno authored under his per-account address; his trailer credited him under the vendor's
        ids = [{"name": "TuftyBruno", "email": "7+TuftyBruno@users.noreply.github.com", "commits": 1, "authored": 1,
                "aliases": [{"name": "TuftyBruno", "email": "noreply@v.example", "commits": 0}]},
               {"name": "Model A", "email": "noreply@v.example", "commits": 9, "authored": 0},
               {"name": "Model B", "email": "noreply@v.example", "commits": 4, "authored": 0,
                "aliases": [{"name": "Model B2", "email": "", "commits": 1}]}]
        self.assertEqual(identity.tools(ids), {"Model A", "Model B"})

    def test_a_tool_that_authored_under_the_shared_mailbox_is_still_a_tool(self):
        ids = [{"name": "Model A", "email": "noreply@v.example", "commits": 9, "authored": 3},
               {"name": "Model B", "email": "noreply@v.example", "commits": 4, "authored": 1, "aliases": [{"name": "Model B", "email": "", "commits": 1}]}]
        self.assertEqual(identity.tools(ids), {"Model A", "Model B"}, "an empty address names no one either")

    def test_the_harness_reads_the_same_definition(self):
        from gitmole.measure import consistency
        ids = [{"name": "Helper", "email": "h@x.org", "commits": 9, "authored": 0},
               {"name": "Model A", "email": "noreply@v.example", "commits": 2, "authored": 2},
               {"name": "Model B", "email": "noreply@v.example", "commits": 2, "authored": 2},
               {"name": "Ann", "email": "a@x.org", "commits": 5, "authored": 5}]
        self.assertEqual(consistency.agents({"meta": {"identities": ids}}), identity.tools(ids))
        self.assertEqual(identity.tools(ids), {"Model A", "Model B"})

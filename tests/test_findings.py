import unittest

from gitmole import findings


def report(**overrides):
    base = {
        "meta": {"name": "r", "commits": 100, "identities": [
            {"name": "Ann", "email": "ann@x.com", "commits": 60},
            {"name": "Bob", "email": "bob@x.com", "commits": 40},
        ]},
        "revisions": [{"entity": "a", "n-revs": 10}, {"entity": "b", "n-revs": 9}],
        "coupling": [],
        "age": [{"entity": "a", "age-months": 0}],
        "sizer": [],
        "theseus_authors": {"Ann": 60, "Bob": 40},
        "secrets": [],
    }
    base.update(overrides)
    return base


class SecretsFound(unittest.TestCase):
    def test_critical_when_any_secret(self):
        r = report(secrets=[{"rule": "aws-access-token", "file": "c.py", "commit": "abc1234", "line": 3}])
        f = findings.secrets_found(r)
        self.assertEqual(f[0]["severity"], "critical")
        self.assertIn("aws-access-token", f[0]["detail"])

    def test_nothing_when_clean(self):
        self.assertEqual(findings.secrets_found(report()), [])


class PlaceholderIdentity(unittest.TestCase):
    def test_warns_on_example_com_email_with_commit_share(self):
        r = report()
        r["meta"]["identities"] = [{"name": "Your Name", "email": "you@example.com", "commits": 64},
                                   {"name": "Bob", "email": "bob@x.com", "commits": 36}]
        f = findings.placeholder_identity(r)
        self.assertEqual(f[0]["severity"], "warning")
        self.assertIn("64%", f[0]["detail"])

    def test_nothing_for_real_identities(self):
        self.assertEqual(findings.placeholder_identity(report()), [])


class BusFactor(unittest.TestCase):
    def test_warns_when_one_author_owns_most_surviving_code(self):
        f = findings.bus_factor(report(theseus_authors={"Ann": 79, "Bob": 21}))
        self.assertEqual(f[0]["severity"], "warning")
        self.assertIn("Ann", f[0]["detail"])
        self.assertIn("79%", f[0]["detail"])

    def test_nothing_when_spread(self):
        self.assertEqual(findings.bus_factor(report()), [])


class SizerConcerns(unittest.TestCase):
    def test_one_finding_per_flagged_row_severity_by_stars(self):
        r = report(sizer=[{"name": "Blobs: Maximum size", "value": "21.3 MiB", "concern": 2, "ref": "static/v.mp4"},
                          {"name": "Trees: Maximum entries", "value": "2.1 k", "concern": 1, "ref": ""}])
        f = findings.sizer_concerns(r)
        self.assertEqual([x["severity"] for x in f], ["warning", "info"])
        self.assertIn("static/v.mp4", f[0]["detail"])


class HotspotDominance(unittest.TestCase):
    def test_info_when_top_file_changes_twice_as_often_as_next(self):
        f = findings.hotspot_dominance(report(revisions=[{"entity": "meta.json", "n-revs": 128}, {"entity": "i.html", "n-revs": 51}]))
        self.assertEqual(f[0]["severity"], "info")
        self.assertIn("meta.json", f[0]["detail"])

    def test_nothing_when_even(self):
        self.assertEqual(findings.hotspot_dominance(report()), [])


class TightCoupling(unittest.TestCase):
    def test_info_with_count_of_tight_pairs(self):
        pairs = [{"entity": "a", "coupled": "b", "degree": 100, "average-revs": 10},
                 {"entity": "c", "coupled": "d", "degree": 85, "average-revs": 6},
                 {"entity": "e", "coupled": "f", "degree": 90, "average-revs": 2}]
        f = findings.tight_coupling(report(coupling=pairs))
        self.assertIn("2 pairs", f[0]["detail"])
        self.assertIn("a", f[0]["detail"])

    def test_nothing_when_no_tight_pairs(self):
        self.assertEqual(findings.tight_coupling(report()), [])


class StaleFiles(unittest.TestCase):
    def test_info_when_a_third_untouched_for_a_year(self):
        age = [{"entity": f"f{i}", "age-months": 12} for i in range(4)] + [{"entity": "g", "age-months": 0} for _ in range(6)]
        f = findings.stale_files(report(age=age))
        self.assertIn("40%", f[0]["detail"])

    def test_nothing_when_fresh(self):
        self.assertEqual(findings.stale_files(report()), [])


class DuplicateIdentities(unittest.TestCase):
    def test_groups_same_person_by_shared_name_tokens(self):
        r = report()
        r["meta"]["identities"] = [{"name": "Grzegorz Bankosz", "email": "g@thg.com", "commits": 25},
                                   {"name": "thg-grzegorz-bankosz", "email": "1@users.noreply.github.com", "commits": 16},
                                   {"name": "Bob", "email": "bob@x.com", "commits": 1}]
        f = findings.duplicate_identities(r)
        self.assertEqual(len(f), 1)
        self.assertIn("Grzegorz Bankosz", f[0]["detail"])
        self.assertIn("mailmap", f[0]["detail"])

    def test_nothing_when_distinct(self):
        self.assertEqual(findings.duplicate_identities(report()), [])


class Evaluate(unittest.TestCase):
    def test_orders_by_severity(self):
        r = report(secrets=[{"rule": "x", "file": "f", "commit": "c", "line": 1}],
                   revisions=[{"entity": "m", "n-revs": 100}, {"entity": "n", "n-revs": 10}],
                   theseus_authors={"Ann": 90, "Bob": 10})
        sev = [f["severity"] for f in findings.evaluate(r)]
        self.assertEqual(sev, sorted(sev, key=["critical", "warning", "info"].index))
        self.assertEqual(sev[0], "critical")


if __name__ == "__main__":
    unittest.main()

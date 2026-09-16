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
        self.assertEqual({x["title"] for x in f}, {"Repo health"}, "one title so the report can group them")
        self.assertIn("Blobs: Maximum size", f[0]["detail"])


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

    def test_single_pair_reads_grammatically(self):
        pairs = [{"entity": "a", "coupled": "b", "degree": 100, "average-revs": 10}]
        f = findings.tight_coupling(report(coupling=pairs))
        self.assertIn("1 pair changes together", f[0]["detail"])

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
    def test_reports_merged_aliases_and_suggests_a_mailmap(self):
        r = report()
        r["meta"]["identities"] = [{"name": "Grzegorz Bankosz", "email": "g@thg.com", "commits": 41,
                                    "aliases": [{"name": "thg-grzegorz-bankosz", "email": "1@users.noreply.github.com", "commits": 16}]},
                                   {"name": "Bob", "email": "bob@x.com", "commits": 1, "aliases": []}]
        f = findings.duplicate_identities(r)
        self.assertEqual(len(f), 1)
        self.assertIn("Grzegorz Bankosz", f[0]["detail"])
        self.assertIn("thg-grzegorz-bankosz", f[0]["detail"])
        self.assertIn("mailmap", f[0]["detail"])
        self.assertIn("merged", f[0]["detail"])

    def test_placeholder_identity_is_found_inside_aliases_too(self):
        r = report()
        r["meta"]["identities"] = [{"name": "vinni", "email": "v@x.com", "commits": 100,
                                    "aliases": [{"name": "Your Name", "email": "you@example.com", "commits": 60}]}]
        f = findings.placeholder_identity(r)
        self.assertEqual(len(f), 1)
        self.assertIn("60%", f[0]["detail"])

    def test_nothing_when_distinct(self):
        self.assertEqual(findings.duplicate_identities(report()), [])


class BugMagnets(unittest.TestCase):
    FIXES = [{"entity": "core/parser.py", "n-fixes": 9, "last-fix": "2026-09-01", "recent-fixes": 5},
             {"entity": "core/util.py", "n-fixes": 4, "last-fix": "2026-08-01", "recent-fixes": 3},
             {"entity": "tests/test_parser.py", "n-fixes": 7, "last-fix": "2026-09-01", "recent-fixes": 6},
             {"entity": "core/old.py", "n-fixes": 8, "last-fix": "2024-01-01", "recent-fixes": 0}]

    def test_names_files_with_a_run_of_recent_fixes_excluding_tests(self):
        f = findings.bug_magnets(report(fixes=self.FIXES))
        self.assertEqual(f[0]["severity"], "warning")
        self.assertIn("core/parser.py (5", f[0]["detail"])
        self.assertIn("core/util.py (3", f[0]["detail"])
        self.assertNotIn("tests/", f[0]["detail"])
        self.assertNotIn("core/old.py", f[0]["detail"])

    def test_info_below_five_recent_fixes(self):
        f = findings.bug_magnets(report(fixes=self.FIXES[1:2]))
        self.assertEqual(f[0]["severity"], "info")

    def test_nothing_without_recent_fixes(self):
        self.assertEqual(findings.bug_magnets(report(fixes=self.FIXES[3:])), [])
        self.assertEqual(findings.bug_magnets(report()), [])


class BrainMethods(unittest.TestCase):
    FUNCS = [{"file": "core/parser.py", "function": "parse", "ccn": 41, "nloc": 220, "params": 9, "start": 10, "end": 300},
             {"file": "core/util.py", "function": "tidy", "ccn": 16, "nloc": 120, "params": 2, "start": 1, "end": 130},
             {"file": "core/small.py", "function": "ok", "ccn": 30, "nloc": 40, "params": 1, "start": 1, "end": 41},
             {"file": "core/long.py", "function": "flat", "ccn": 3, "nloc": 400, "params": 1, "start": 1, "end": 401}]

    def test_long_and_complex_functions_worst_first(self):
        f = findings.brain_methods(report(functions=self.FUNCS))
        self.assertEqual(len(f), 1)
        self.assertIn("parse (core/parser.py) complexity 41, 220 lines, 9 params", f[0]["detail"])
        self.assertIn("tidy (core/util.py)", f[0]["detail"])
        self.assertNotIn("small.py", f[0]["detail"], "complex but short is not a brain method")
        self.assertNotIn("long.py", f[0]["detail"], "long but simple is not a brain method")

    def test_warning_when_a_brain_method_sits_in_a_hotspot(self):
        r = report(functions=self.FUNCS, revisions=[{"entity": "core/parser.py", "n-revs": 90}, {"entity": "x.py", "n-revs": 1}])
        self.assertEqual(findings.brain_methods(r)[0]["severity"], "warning")
        self.assertEqual(findings.brain_methods(report(functions=self.FUNCS))[0]["severity"], "info")

    def test_nothing_without_data(self):
        self.assertEqual(findings.brain_methods(report()), [])


class Duplication(unittest.TestCase):
    def test_large_blocks_are_reported(self):
        dup = {"rate": 4.2, "blocks": [{"lines": 71, "places": [("a/x.py", 10, 80), ("b/y.py", 5, 75)]},
                                       {"lines": 12, "places": [("c.py", 1, 12), ("d.py", 1, 12)]}]}
        f = findings.duplication(report(duplicates=dup))
        self.assertEqual(len(f), 1)
        self.assertIn("71 lines", f[0]["detail"])
        self.assertIn("a/x.py:10", f[0]["detail"])
        self.assertNotIn("c.py", f[0]["detail"], "short blocks are noise")
        self.assertIn("4.2%", f[0]["detail"])

    def test_nothing_without_large_blocks(self):
        self.assertEqual(findings.duplication(report(duplicates={"rate": 0.5, "blocks": [{"lines": 12, "places": [("c.py", 1, 12), ("d.py", 1, 12)]}]})), [])
        self.assertEqual(findings.duplication(report()), [])


class KnowledgeIslands(unittest.TestCase):
    OWN = [{"entity": "core/a.py", "author": "Ann", "added": 950, "deleted": 0},
           {"entity": "core/b.py", "author": "Bob", "added": 50, "deleted": 0},
           {"entity": "web/i.html", "author": "Bob", "added": 300, "deleted": 0},
           {"entity": "web/j.html", "author": "Cat", "added": 300, "deleted": 0}]

    def test_warns_when_islands_hold_most_of_the_code(self):
        f = findings.knowledge_islands(report(ownership=self.OWN))
        self.assertEqual(f[0]["severity"], "warning")
        self.assertIn("core/", f[0]["detail"])
        self.assertIn("Ann", f[0]["detail"])
        self.assertIn("95%", f[0]["detail"])
        self.assertNotIn("web/", f[0]["detail"])

    def test_info_when_islands_are_a_minority(self):
        own = self.OWN + [{"entity": "web/k.html", "author": "Dan", "added": 3000, "deleted": 0}]
        f = findings.knowledge_islands(report(ownership=own))
        self.assertEqual(f[0]["severity"], "info")

    def test_nothing_when_shared(self):
        self.assertEqual(findings.knowledge_islands(report(ownership=self.OWN[2:])), [])
        self.assertEqual(findings.knowledge_islands(report()), [])


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

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

    @staticmethod
    def row(value, file, commit="c1", line=1, rule="generic-api-key", placeholder=False):
        return {"rule": rule, "file": file, "commit": commit, "line": line, "fingerprint": f"{commit}:{file}:{rule}:{line}",
                "value": value, "placeholder": placeholder}

    def test_source_values_are_critical_test_only_values_a_warning_each_counted_once(self):
        r = report(secrets=[self.row("h1", "app/settings.py", "c1", 9), self.row("h1", "app/settings.py", "c2", 9),
                            self.row("h2", "tests/data/a.html", "c3", 5), self.row("h2", "tests/data/a.html", "c3", 5),
                            self.row("h2", "app/tests/data/a.html", "c4", 5, rule="aws-access-token"),
                            self.row("h3", "tests/t.py", "c5", 2)])
        found = {f["severity"]: f for f in findings.secrets_found(r)}
        self.assertEqual(set(found), {"critical", "warning"})
        crit, warn = found["critical"], found["warning"]
        self.assertEqual(crit["title"], "1 secret(s) in history")
        self.assertIn("1 distinct value in 2 places: generic-api-key in app/settings.py (c1, c2)", crit["detail"])
        self.assertIn("Rotate", crit["advice"])
        self.assertIn(".gitleaksignore", crit["advice"])
        self.assertEqual(warn["title"], "2 secret(s) only in test files")
        self.assertIn("2 distinct values in 3 places", warn["detail"])
        self.assertIn("tests/data/a.html and 1 other file", warn["detail"])
        self.assertIn(".gitleaksignore", warn["advice"])

    def test_test_only_secrets_do_not_fail_a_critical_gate(self):
        r = report(secrets=[self.row("h3", "tests/t.py")])
        self.assertEqual([f["severity"] for f in findings.secrets_found(r)], ["warning"])

    def test_placeholder_shapes_are_not_a_finding(self):
        r = report(secrets=[self.row("h4", "web/package.json", placeholder=True)])
        self.assertEqual(findings.secrets_found(r), [])

    def test_examples_name_at_most_three_values(self):
        r = report(secrets=[self.row(f"h{i}", f"app/f{i}.py", f"c{i}") for i in range(5)])
        crit = findings.secrets_found(r)[0]
        self.assertIn("and 2 more", crit["detail"])
        self.assertEqual(crit["title"], "5 secret(s) in history")


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

    def test_a_stray_commit_below_one_percent_is_not_worth_a_warning(self):
        r = report()
        r["meta"]["identities"] = [{"name": "Ann", "email": "ann@x.com", "commits": 4405},
                                   {"name": "Elegant", "email": "user@elegant996.net", "commits": 1}]
        self.assertEqual(findings.placeholder_identity(r), [])
        r["meta"]["identities"][1]["commits"] = 45
        self.assertEqual(findings.placeholder_identity(r)[0]["severity"], "warning")


class BusFactor(unittest.TestCase):
    def test_warns_when_one_author_owns_most_surviving_code(self):
        f = findings.bus_factor(report(theseus_authors={"Ann": 79, "Bob": 21}))
        self.assertEqual(f[0]["severity"], "warning")
        self.assertIn("Ann", f[0]["detail"])
        self.assertIn("79%", f[0]["detail"])
        self.assertTrue(f[0]["detail"].endswith("Pair someone with Ann before they are unavailable."), f[0]["detail"])

    def test_advice_names_the_areas_that_are_mostly_theirs(self):
        own = [{"entity": "core/a.py", "author": "Ann", "added": 950, "deleted": 0},
               {"entity": "core/b.py", "author": "Bob", "added": 50, "deleted": 0},
               {"entity": "web/i.html", "author": "Ann", "added": 400, "deleted": 0},
               {"entity": "web/j.html", "author": "Bob", "added": 100, "deleted": 0},
               {"entity": "docs/x.md", "author": "Bob", "added": 300, "deleted": 0}]
        f = findings.bus_factor(report(theseus_authors={"Ann": 79, "Bob": 21}, ownership=own))
        self.assertTrue(f[0]["detail"].endswith("Pair someone with Ann on core/ and web/ first; they are 95% and 80% theirs."), f[0]["detail"])

    def test_areas_come_from_source_files_of_some_size_and_say_when_windowed(self):
        own = [{"entity": "tests/t.py", "author": "Ann", "added": 5000, "deleted": 0},
               {"entity": "docs/readme.md", "author": "Ann", "added": 3, "deleted": 0},
               {"entity": "core/a.py", "author": "Ann", "added": 900, "deleted": 0},
               {"entity": "core/b.py", "author": "Bob", "added": 50, "deleted": 0}]
        r = report(theseus_authors={"Ann": 79, "Bob": 21}, ownership=own)
        self.assertEqual(findings.bus_factor(r)[0]["advice"], "Pair someone with Ann on core/ first; it is 95% theirs.",
                         "tests/ is not a knowledge risk and a 3-line docs/ is too small to name")
        r["meta"]["since"] = "2025-01-01"
        self.assertEqual(findings.bus_factor(r)[0]["advice"], "Pair someone with Ann on core/ first; it is 95% theirs since 2025-01-01.",
                         "ownership is windowed while the headline share is not")

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
        self.assertEqual(f[0]["advice"], "Move large files to Git LFS or rewrite them out of history.")
        self.assertEqual(f[1]["advice"], "Split the widest directory into subdirectories; a directory that wide slows every checkout and diff.")

    def test_advice_per_kind_of_concern(self):
        # keyed on the loader's "section: metric" names, which are the only ones that occur
        def advice(name, ref=""):
            return findings.sizer_concerns(report(sizer=[{"name": name, "value": "1", "concern": 1, "ref": ref}]))[0]["advice"]
        lfs = "Move large files to Git LFS or rewrite them out of history."
        prune = "Consider pruning old branches and tags."
        shallow = "Consider a shallow clone for CI; the history is the cost."
        self.assertEqual(advice("Blobs: Maximum size", "static/v.mp4"), lfs)
        self.assertEqual(advice("Blobs: Total size"), lfs)
        self.assertEqual(advice("Blobs: Count"), shallow, "many small blobs: history, not file size")
        self.assertEqual(advice("References: Count"), prune)
        self.assertEqual(advice("Annotated tags: Count"), prune)
        self.assertEqual(advice("Commits: Count"), shallow)
        self.assertEqual(advice("Commits: Total size"), shallow)
        self.assertEqual(advice("Trees: Count"), shallow)
        self.assertEqual(advice("Trees: Total tree entries"), shallow)
        self.assertEqual(advice("History structure: Maximum history depth"), shallow)
        self.assertEqual(advice("Trees: Maximum entries", "static"), "Split static into subdirectories; a directory that wide slows every checkout and diff.")
        self.assertEqual(advice("Commits: Maximum size"), "Look at that commit; oversized commits are usually imports or octopus merges.")
        self.assertEqual(advice("Commits: Maximum parents"), "Look at that commit; oversized commits are usually imports or octopus merges.")
        self.assertEqual(advice("Biggest checkouts: Number of files"), "Consider a sparse checkout for CI; the tree is the cost.")
        self.assertEqual(advice("Biggest checkouts: Total size of files"), "Consider a sparse checkout for CI; the tree is the cost.")


class HotspotDominance(unittest.TestCase):
    def test_info_when_top_file_changes_twice_as_often_as_next(self):
        f = findings.hotspot_dominance(report(revisions=[{"entity": "meta.json", "n-revs": 128}, {"entity": "i.html", "n-revs": 51}]))
        self.assertEqual(f[0]["severity"], "info")
        self.assertIn("meta.json", f[0]["detail"])
        self.assertTrue(f[0]["detail"].endswith("Consider splitting meta.json; every change lands there."), f[0]["detail"])

    def test_a_test_file_is_not_a_hotspot_to_split(self):
        r = report(revisions=[{"entity": "tests/test_render.py", "n-revs": 60}, {"entity": "gitmole/render.py", "n-revs": 20}, {"entity": "gitmole/cli.py", "n-revs": 5}])
        f = findings.hotspot_dominance(r)
        self.assertEqual(f[0]["advice"], "Consider splitting gitmole/render.py; every change lands there.")

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
        self.assertTrue(f[0]["detail"].endswith("Review a and b first: a shared layout or a hidden dependency links them."), f[0]["detail"])

    def test_a_file_and_its_test_are_expected_to_change_together(self):
        pairs = [{"entity": "gitmole/maat.py", "coupled": "tests/test_maat.py", "degree": 100, "average-revs": 16},
                 {"entity": "src/a.js", "coupled": "src/a.test.js", "degree": 100, "average-revs": 9}]
        self.assertEqual(findings.tight_coupling(report(coupling=pairs)), [])

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
        self.assertIn("Consider deleting what nobody has needed; dead code hides in untouched files.", f[0]["detail"])

    def test_nothing_when_fresh(self):
        self.assertEqual(findings.stale_files(report()), [])

    def test_files_no_longer_in_the_tree_do_not_count(self):
        age = [{"entity": f"f{i}", "age-months": 12} for i in range(4)] + [{"entity": f"g{i}", "age-months": 0} for i in range(6)]
        in_tree = {f"f{i}": {"code": 1, "complexity": 0} for i in range(2)} | {f"g{i}": {"code": 1, "complexity": 0} for i in range(6)}
        self.assertEqual(findings.stale_files(report(age=age, size={"files": in_tree})), [], "2 of 8 files in the tree are stale")
        in_tree = {f"f{i}": {"code": 1, "complexity": 0} for i in range(4)} | {f"g{i}": {"code": 1, "complexity": 0} for i in range(6)}
        f = findings.stale_files(report(age=age, size={"files": in_tree}))
        self.assertIn("40% of files (4)", f[0]["detail"])


class IdentityMerges(unittest.TestCase):
    def test_are_not_a_finding(self):
        r = report()
        r["meta"]["identities"] = [{"name": "Grzegorz Bankosz", "email": "g@thg.com", "commits": 41,
                                    "aliases": [{"name": "thg-grzegorz-bankosz", "email": "1@users.noreply.github.com", "commits": 16}]}]
        self.assertEqual([f["title"] for f in findings.evaluate(r)], [], "merged aliases are a People caption, not a finding")
        self.assertFalse(hasattr(findings, "duplicate_identities"))

    def test_placeholder_identity_is_found_inside_aliases_too(self):
        r = report()
        r["meta"]["identities"] = [{"name": "vinni", "email": "v@x.com", "commits": 100,
                                    "aliases": [{"name": "Your Name", "email": "you@example.com", "commits": 60}]}]
        f = findings.placeholder_identity(r)
        self.assertEqual(len(f), 1)
        self.assertIn("60%", f[0]["detail"])


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
        self.assertTrue(f[0]["detail"].endswith("Review core/parser.py and core/util.py before the next release; expect the next bug there."), f[0]["detail"])

    def test_info_below_five_recent_fixes(self):
        f = findings.bug_magnets(report(fixes=self.FIXES[1:2]))
        self.assertEqual(f[0]["severity"], "info")
        self.assertTrue(f[0]["detail"].endswith("Review core/util.py before the next release; expect the next bug there."), f[0]["detail"])

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
        self.assertTrue(f[0]["detail"].endswith("Split parse in core/parser.py first, before the next change lands there."), f[0]["detail"])

    def test_warning_when_a_brain_method_sits_in_a_hotspot(self):
        r = report(functions=self.FUNCS, revisions=[{"entity": "core/parser.py", "n-revs": 90}, {"entity": "x.py", "n-revs": 1}])
        self.assertEqual(findings.brain_methods(r)[0]["severity"], "warning")
        self.assertEqual(findings.brain_methods(report(functions=self.FUNCS))[0]["severity"], "info")

    def test_hotspot_means_the_ranking_the_table_shows(self):
        funcs = [{"file": "big.py", "function": "run", "ccn": 40, "nloc": 300, "params": 1, "start": 1, "end": 300}]
        revs = [{"entity": f"t{i}.py", "n-revs": 31} for i in range(11)] + [{"entity": "big.py", "n-revs": 30}]
        files = {f"t{i}.py": {"code": 10, "complexity": 0} for i in range(11)}
        files["big.py"] = {"code": 5000, "complexity": 40}
        r = report(functions=funcs, revisions=revs, size={"files": files})
        self.assertEqual(findings.brain_methods(r)[0]["severity"], "warning", "big.py is the top hotspot by revisions × lines")

    def test_nothing_without_data(self):
        self.assertEqual(findings.brain_methods(report()), [])

    def test_functions_in_test_files_are_not_brain_methods(self):
        fns = [{"file": "tests/test_all.py", "function": "test_all", "ccn": 20, "nloc": 400, "params": 1, "start": 1, "end": 400},
               {"file": "core/parser.py", "function": "parse", "ccn": 16, "nloc": 120, "params": 3, "start": 1, "end": 120}]
        f = findings.brain_methods(report(functions=fns))
        self.assertEqual(f[0]["advice"], "Split parse in core/parser.py first, before the next change lands there.")
        self.assertNotIn("test_all", f[0]["detail"])
        self.assertEqual(findings.brain_methods(report(functions=fns[:1])), [])

    def test_a_partial_run_says_there_may_be_more(self):
        r = report(functions=self.FUNCS)
        self.assertNotIn("part way", findings.brain_methods(r)[0]["detail"])
        r["meta"]["functions"] = {"status": "timeout"}
        self.assertIn("Function metrics timed out part way, so there may be more. Split parse in core/parser.py first", findings.brain_methods(r)[0]["detail"])


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
        self.assertTrue(f[0]["detail"].endswith("Extract the 71-line block shared by a/x.py and b/y.py first."), f[0]["detail"])

    def test_advice_names_each_file_once_and_says_within_for_one_file(self):
        block = lambda places: {"rate": 3.1, "blocks": [{"lines": 45, "places": places}]}
        f = findings.duplication(report(duplicates=block([("core/parser.py", 10, 54), ("core/parser.py", 200, 244)])))
        self.assertEqual(f[0]["advice"], "Extract the 45-line block repeated within core/parser.py first.")
        f = findings.duplication(report(duplicates=block([("a.py", 1, 45), ("a.py", 50, 94), ("b.py", 1, 45)])))
        self.assertEqual(f[0]["advice"], "Extract the 45-line block shared by a.py and b.py first.")

    def test_nothing_without_large_blocks(self):
        self.assertEqual(findings.duplication(report(duplicates={"rate": 0.5, "blocks": [{"lines": 12, "places": [("c.py", 1, 12), ("d.py", 1, 12)]}]})), [])
        self.assertEqual(findings.duplication(report()), [])

    def test_a_partial_run_says_there_may_be_more(self):
        dup = {"rate": 4.2, "blocks": [{"lines": 71, "places": [("a/x.py", 10, 80), ("b/y.py", 5, 75)]}]}
        r = report(duplicates=dup)
        r["meta"]["functions"] = {"status": "failed"}
        self.assertIn("4.2% of lines are duplicated. Function metrics failed part way, so there may be more. Extract", findings.duplication(r)[0]["detail"])


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
        self.assertTrue(f[0]["detail"].endswith("Pair someone with Ann on core/ first; it is the largest at 1,000 lines."), f[0]["detail"])

    def test_info_when_islands_are_a_minority(self):
        own = self.OWN + [{"entity": "web/k.html", "author": "Dan", "added": 3000, "deleted": 0}]
        f = findings.knowledge_islands(report(ownership=own))
        self.assertEqual(f[0]["severity"], "info")

    def test_test_directories_are_not_islands(self):
        own = [{"entity": "tests/test_a.py", "author": "Ann", "added": 4000, "deleted": 0},
               {"entity": "core/a.py", "author": "Bob", "added": 300, "deleted": 0}]
        f = findings.knowledge_islands(report(ownership=own))
        self.assertEqual(f[0]["advice"], "Pair someone with Bob on core/ first; it is the largest at 300 lines.")
        self.assertNotIn("tests/", f[0]["detail"])

    def test_nothing_when_shared(self):
        self.assertEqual(findings.knowledge_islands(report(ownership=self.OWN[2:])), [])
        self.assertEqual(findings.knowledge_islands(report()), [])


class Reverts(unittest.TestCase):
    def _report(self, reverts, commits=100, reverted=None):
        r = report()
        r["meta"]["commits"] = commits
        r["activity"] = {"revert_commits": reverts, "reverted": reverted or {}}
        return r

    def test_info_at_five_percent_names_the_most_reverted_file(self):
        # maat.activity sorts by count desc then path, so the test file leads the table
        f = findings.reverts(self._report(5, reverted={"tests/t.py": 4, "core/a.py": 3, "core/b.py": 2}))
        self.assertEqual(f[0]["severity"], "info")
        self.assertEqual(f[0]["title"], "Reverts")
        self.assertIn("5 of 100 commits are reverts; core/a.py was reverted 3 times, core/b.py twice, tests/t.py 4 times",
                      f[0]["detail"], "source files lead, test files still listed")
        self.assertEqual(f[0]["advice"], "Add a check before merge for core/a.py; it is the file most often backed out.")

    def test_five_reverts_fire_even_below_five_percent(self):
        self.assertEqual(len(findings.reverts(self._report(5, commits=1000, reverted={"a.py": 5}))), 1)
        self.assertEqual(findings.reverts(self._report(4, commits=1000, reverted={"a.py": 4})), [])

    def test_warning_at_ten_percent(self):
        self.assertEqual(findings.reverts(self._report(10, reverted={"a.py": 10}))[0]["severity"], "warning")

    def test_only_test_files_reverted_says_so(self):
        f = findings.reverts(self._report(6, reverted={"tests/t.py": 6}))
        self.assertEqual(f[0]["advice"], "Look at why they were backed out; only test files were touched.")

    def test_nothing_without_reverts_or_activity(self):
        self.assertEqual(findings.reverts(self._report(0)), [])
        self.assertEqual(findings.reverts(report()), [])


class KnowledgeLoss(unittest.TestCase):
    def _report(self, **over):
        r = report(**over)
        r["meta"].update({"last_date": "2025-11-09", "bots": []})
        r["activity"] = {"authors": {
            "Ann": {"commits": 60, "added": 0, "deleted": 0, "first": "2020-01-01", "last": "2025-10-01"},
            "Bob": {"commits": 40, "added": 0, "deleted": 0, "first": "2020-01-01", "last": "2024-06-01"}}}
        return r

    def test_warning_names_the_largest_area_nobody_around_wrote(self):
        r = self._report(theseus_authors={"Ann": 60, "Bob": 40},
                         age=[{"entity": "old/a.py", "age-months": 2}, {"entity": "docs/x.md", "age-months": 30}],
                         ownership=[{"entity": "old/a.py", "author": "Bob", "added": 800, "deleted": 0},
                                    {"entity": "docs/x.md", "author": "Bob", "added": 300, "deleted": 0},
                                    {"entity": "app/b.py", "author": "Ann", "added": 900, "deleted": 0}])
        f = findings.knowledge_loss(r)
        self.assertEqual(f[0]["severity"], "warning")
        self.assertEqual(f[0]["title"], "Knowledge loss")
        self.assertIn("People with no commits since 2024-11-09 wrote 40% of the code that survives today: Bob (40%)", f[0]["detail"])
        self.assertIn("Areas mostly theirs: old/ (100%), docs/ (100%)", f[0]["detail"])
        self.assertEqual(f[0]["advice"], "Pair someone on old/ first; nobody who wrote it is around to ask.")

    def test_a_live_area_is_preferred_over_a_bigger_idle_one(self):
        r = self._report(theseus_authors={"Ann": 60, "Bob": 40},
                         age=[{"entity": "old/a.py", "age-months": 30}, {"entity": "live/b.py", "age-months": 3}],
                         ownership=[{"entity": "old/a.py", "author": "Bob", "added": 800, "deleted": 0},
                                    {"entity": "live/b.py", "author": "Bob", "added": 300, "deleted": 0},
                                    {"entity": "app/c.py", "author": "Ann", "added": 900, "deleted": 0}])
        f = findings.knowledge_loss(r)
        self.assertEqual(f[0]["advice"], "Pair someone on live/ first; nobody who wrote it is around to ask.")
        self.assertIn("Areas mostly theirs: live/ (100%), old/ (100%)", f[0]["detail"], "the live area leads the list too")

    def test_advice_falls_back_when_no_area_is_still_live(self):
        r = self._report(theseus_authors={"Ann": 60, "Bob": 40},
                         age=[{"entity": "old/a.py", "age-months": 30}],
                         ownership=[{"entity": "old/a.py", "author": "Bob", "added": 800, "deleted": 0},
                                    {"entity": "app/c.py", "author": "Ann", "added": 900, "deleted": 0}])
        f = findings.knowledge_loss(r)
        self.assertEqual(f[0]["advice"], "Pair someone with the people who worked with Bob before the rest of that knowledge goes.")
        self.assertIn("Areas mostly theirs: old/ (100%)", f[0]["detail"], "the areas are still worth naming")

    def test_root_files_count_as_live_when_a_file_in_the_root_is_fresh(self):
        r = self._report(theseus_authors={"Ann": 60, "Bob": 40},
                         age=[{"entity": "main.py", "age-months": 1}, {"entity": "old/a.py", "age-months": 30}],
                         ownership=[{"entity": "main.py", "author": "Bob", "added": 300, "deleted": 0},
                                    {"entity": "old/a.py", "author": "Bob", "added": 800, "deleted": 0},
                                    {"entity": "app/c.py", "author": "Ann", "added": 900, "deleted": 0}])
        f = findings.knowledge_loss(r)
        self.assertEqual(f[0]["advice"], "Pair someone on (root files) first; nobody who wrote it is around to ask.")

    def test_info_between_ten_and_thirty_percent(self):
        f = findings.knowledge_loss(self._report(theseus_authors={"Ann": 85, "Bob": 15}))
        self.assertEqual(f[0]["severity"], "info")
        self.assertEqual(f[0]["advice"], "Pair someone with the people who worked with Bob before the rest of that knowledge goes.")

    def test_nothing_below_ten_percent_or_when_nobody_is_gone(self):
        self.assertEqual(findings.knowledge_loss(self._report(theseus_authors={"Ann": 95, "Bob": 5})), [])
        r = self._report()
        r["activity"]["authors"]["Bob"]["last"] = "2025-11-01"
        self.assertEqual(findings.knowledge_loss(r), [])

    def test_without_a_blame_pass_uses_lines_added_and_says_so(self):
        r = self._report(theseus_authors={},
                         ownership=[{"entity": "old/a.py", "author": "Bob", "added": 400, "deleted": 0},
                                    {"entity": "app/b.py", "author": "Ann", "added": 600, "deleted": 0}])
        f = findings.knowledge_loss(r)
        self.assertEqual(f[0]["severity"], "warning")
        self.assertIn("wrote 40% of all lines added (from lines added, not a blame)", f[0]["detail"])

    def test_window_from_meta(self):
        r = self._report(theseus_authors={"Ann": 60, "Bob": 40})
        r["meta"]["gone_months"] = 24
        self.assertEqual(findings.knowledge_loss(r), [], "Bob committed 17 months before the last commit")

    def test_small_contributors_are_folded_into_others(self):
        # total 1000; Dan, Eve and Fay each round to 0% individually and are folded into "others".
        r = self._report(theseus_authors={"Ann": 718, "Bob": 250, "Cat": 20, "Dan": 4, "Eve": 4, "Fay": 4})
        for name in ("Cat", "Dan", "Eve", "Fay"):
            r["activity"]["authors"][name] = {"commits": 1, "added": 0, "deleted": 0, "first": "2020-01-01", "last": "2024-06-01"}
        f = findings.knowledge_loss(r)
        self.assertIn("wrote 28% of the code that survives today: Bob (25%), Cat (2%) and 3 others (1%)", f[0]["detail"])
        self.assertNotIn("Dan", f[0]["detail"])


class ComplexityGrowth(unittest.TestCase):
    def _report(self, growth):
        files = {f"core/f{i}.py": {"code": 100, "complexity": 10} for i in range(5)}
        r = report(size={"files": files}, revisions=[{"entity": f"core/f{i}.py", "n-revs": 50 - i} for i in range(5)])
        r["meta"]["last_date"] = "2026-09-10"
        r["trend"] = {"samples": ["2025-09-10", "2026-09-10"],
                      "files": {f"core/f{i}.py": [["2025-09-10", 10, 100], ["2026-09-10", 10 + g, 100]] for i, g in enumerate(growth)}}
        return r

    def test_three_growers_of_a_quarter_are_a_note_warning_when_the_top_hotspot_grows(self):
        f = findings.complexity_growth(self._report([3, 3, 3, 0, 0]))
        self.assertEqual(f[0]["severity"], "warning", "core/f0.py is the top hotspot and grew")
        self.assertEqual(f[0]["title"], "Hotspots getting more complex")
        self.assertIn("3 of the 5 top source hotspots grew by 25% or more in a year: core/f0.py (+30%), core/f1.py (+30%), core/f2.py (+30%)", f[0]["detail"])
        self.assertEqual(f[0]["advice"], "Split core/f0.py before the next change; its complexity grew 30% in a year.")
        f = findings.complexity_growth(self._report([0, 3, 3, 3, 0]))
        self.assertEqual(f[0]["severity"], "info")
        self.assertEqual(f[0]["advice"], "Split core/f1.py before the next change; its complexity grew 30% in a year.")

    def test_a_growing_test_file_is_neither_counted_nor_named(self):
        r = self._report([3, 3, 3, 0, 0])
        r["size"]["files"]["tests/test_x.py"] = {"code": 1000, "complexity": 10}   # the top hotspot by score
        r["revisions"].insert(0, {"entity": "tests/test_x.py", "n-revs": 90})
        r["trend"]["files"]["tests/test_x.py"] = [["2025-09-10", 10, 1000], ["2026-09-10", 20, 1000]]
        f = findings.complexity_growth(r)
        self.assertIn("3 of the 5 top source hotspots", f[0]["detail"], "the test file is not one of the five")
        self.assertNotIn("tests/test_x.py", f[0]["detail"])
        self.assertEqual(f[0]["severity"], "warning", "core/f0.py still leads the source hotspots")

    def test_two_growers_or_small_growth_is_nothing(self):
        self.assertEqual(findings.complexity_growth(self._report([3, 3, 0, 0, 0])), [])
        self.assertEqual(findings.complexity_growth(self._report([2, 2, 2, 2, 2])), [])
        self.assertEqual(findings.complexity_growth(report()), [])


class Advice(unittest.TestCase):
    def test_every_finding_carries_its_next_step_as_a_field_that_ends_the_detail(self):
        r = report(secrets=[{"rule": "aws", "file": "a.env", "commit": "abc1234"}],
                   theseus_authors={"Ann": 79, "Bob": 21},
                   sizer=[{"name": "Blobs: Maximum size", "value": "21.3 MiB", "concern": 2, "ref": "static/v.mp4"}],
                   revisions=[{"entity": "a.py", "n-revs": 128}, {"entity": "b.py", "n-revs": 51}],
                   fixes=[{"entity": "a.py", "n-fixes": 9, "last-fix": "2026-09-01", "recent-fixes": 5}],
                   functions=[{"file": "a.py", "function": "go", "ccn": 20, "nloc": 150, "params": 2, "start": 1, "end": 150}],
                   coupling=[{"entity": "a.py", "coupled": "b.py", "degree": 90, "average-revs": 11}],
                   duplicates={"rate": 4.2, "blocks": [{"lines": 71, "places": [("a.py", 10, 80), ("b.py", 5, 75)]}]},
                   age=[{"entity": "a.py", "age-months": 30}, {"entity": "b.py", "age-months": 0}],
                   ownership=[{"entity": "core/a.py", "author": "Ann", "added": 950, "deleted": 0}])
        r["meta"]["identities"] = [{"name": "Ann", "email": "ann@x.com", "commits": 5, "aliases": [{"name": "root", "email": "root@localhost", "commits": 1}]}]
        found = findings.evaluate(r)
        self.assertEqual({f["title"] for f in found} >= {"Bus factor of one", "Repo health", "Bug magnets", "Brain methods", "Duplicated code",
                                                      "A large share of files is untouched", "Unconfigured git identity", "Knowledge islands"}, True)
        for f in found:
            self.assertTrue(f.get("advice"), f["title"])
            self.assertTrue(f["detail"].endswith(" " + f["advice"]), f["detail"])

    def test_a_name_with_an_initial_keeps_its_advice(self):
        f = findings.bus_factor(report(theseus_authors={"Robert C. Martin": 90, "Bob": 10}))[0]
        self.assertEqual(f["advice"], "Pair someone with Robert C. Martin before they are unavailable.")


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

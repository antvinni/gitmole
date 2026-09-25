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
        self.assertIn(".betterleaksignore", crit["advice"])
        self.assertEqual(warn["title"], "2 secret(s) only in test, example, vendored, generated or documentation files")
        self.assertIn("2 distinct values in 3 places", warn["detail"])
        self.assertIn("tests/data/a.html and 1 other file", warn["detail"])
        self.assertIn(".betterleaksignore", warn["advice"])

    def test_a_value_from_an_unreachable_blob_names_no_commit_rather_than_an_empty_one(self):
        """react's one critical finding read "in (unreachable blob 00db21063ea1) ()", and django's
        "(, d61f33f and 6 more)": an unreachable blob is in no commit, so its commit is the empty string
        and joining it left the comma behind."""
        blob = "(unreachable blob 00db21063ea1)"
        r = report(secrets=[self.row("h1", blob, commit=""), self.row("h2", "app/a.py", "c9")])
        detail = findings.secrets_found(r)[0]["detail"]
        self.assertIn(f"generic-api-key in {blob};", detail, "no parenthesis where there is no commit")
        self.assertNotIn("()", detail)
        self.assertNotIn("(,", detail)
        self.assertIn("generic-api-key in app/a.py (c9)", detail, "a value with a commit still names it")

    def test_two_values_that_read_the_same_are_counted_not_repeated(self):
        """Two distinct values can be the same rule in the same blob at the same line, which rendered as
        the same words twice with nothing to tell them apart."""
        blob = "(unreachable blob 00db21063ea1)"
        r = report(secrets=[self.row("h1", blob, commit="", rule="facebook-access-token"),
                            self.row("h2", blob, commit="", rule="facebook-access-token")])
        detail = findings.secrets_found(r)[0]["detail"]
        self.assertIn(f"2 distinct values in 2 places: 2 values of facebook-access-token in {blob}.", detail)

    def test_test_only_secrets_do_not_fail_a_critical_gate(self):
        r = report(secrets=[self.row("h3", "tests/t.py")])
        self.assertEqual([f["severity"] for f in findings.secrets_found(r)], ["warning"])

    def test_a_value_only_in_an_example_fixture_or_rules_directory_is_a_warning(self):
        r = report(secrets=[self.row("h1", "examples/language/bru.bru", "57d82e9", rule="generic-password"),
                            self.row("h2", "config/generate/rules/slack.go", "04bdee4", rule="slack-bot-token"),
                            self.row("h3", "pkg/testdata/creds.yaml", "c3")])
        f = findings.secrets_found(r)
        self.assertEqual([x["severity"] for x in f], ["warning"])
        self.assertEqual(f[0]["title"], "3 secret(s) only in test, example, vendored, generated or documentation files")
        r = report(secrets=[self.row("h1", "examples/app.py", "c1"), self.row("h1", "app/config.py", "c2")])
        self.assertEqual([x["severity"] for x in findings.secrets_found(r)], ["critical"], "the same value in source is a leak")

    def test_a_value_only_in_vendored_code_is_a_warning(self):
        # oauthlib's RFC test vectors inside requests/packages/: upstream's specimen, not this repository's credential
        r = report(secrets=[self.row("h1", "requests/packages/oauthlib/oauth1/rfc5849/parameters.py", "9576518")])
        r["meta"]["vendored"] = ["requests/packages/"]
        f = findings.secrets_found(r)
        self.assertEqual([x["severity"] for x in f], ["warning"])
        self.assertIn("vendored", f[0]["title"])

    def test_a_value_only_in_documentation_is_a_warning_that_says_template(self):
        r = report(secrets=[self.row("h1", "docs/GA4-API-INTEGRATION.md", "e8c0508")])
        f = findings.secrets_found(r)
        self.assertEqual([x["severity"] for x in f], ["warning"])
        self.assertEqual(f[0]["title"], "1 secret(s) only in test, example, vendored, generated or documentation files")
        self.assertIn("fixtures or templates", f[0]["advice"])
        r = report(secrets=[self.row("h1", "docs/GA4-API-INTEGRATION.md", "e8c0508"), self.row("h1", "app/config.py", "c2")])
        self.assertEqual([x["severity"] for x in findings.secrets_found(r)], ["critical"], "the same value in source is a leak")

    def test_placeholder_shapes_are_not_a_finding(self):
        r = report(secrets=[self.row("h4", "web/package.json", placeholder=True)])
        self.assertEqual(findings.secrets_found(r), [])

    def test_examples_name_at_most_three_values(self):
        r = report(secrets=[self.row(f"h{i}", f"app/f{i}.py", f"c{i}") for i in range(5)])
        crit = findings.secrets_found(r)[0]
        self.assertIn("and 2 more", crit["detail"])
        self.assertEqual(crit["title"], "5 secret(s) in history")


class CredentialFiles(unittest.TestCase):
    def test_warns_and_names_the_files(self):
        r = {"meta": {"credential_files": [".env.production", "deploy/id_rsa"]}}
        found = findings.credential_files(r)
        self.assertEqual(len(found), 1)
        f = found[0]
        self.assertEqual((f["severity"], f["title"], f["rule"]["id"]), ("warning", "Credential-shaped files tracked", "credential_files"))
        self.assertIn("2 credential-shaped files tracked: .env.production, deploy/id_rsa.", f["detail"])
        self.assertEqual(f["evidence"], {"count": 2, "files": [".env.production", "deploy/id_rsa"]})
        self.assertEqual(findings.credential_files({"meta": {}}), [], "an older output directory has no record and no finding")
        self.assertIn(findings.credential_files, findings.RULES)


class PlaceholderIdentity(unittest.TestCase):
    def test_warns_on_example_com_email_with_commit_share(self):
        r = report()
        r["meta"]["identities"] = [{"name": "Your Name", "email": "you@example.com", "commits": 64},
                                   {"name": "Bob", "email": "bob@x.com", "commits": 36}]
        f = findings.placeholder_identity(r)
        self.assertEqual(f[0]["severity"], "warning")
        self.assertIn("64%", f[0]["detail"])
        self.assertIn("Bob <bob@x.com> Your Name <you@example.com>", f[0]["advice"], "the .mailmap line, with the top real identity as the likely owner")
        self.assertIn(".mailmap", f[0]["advice"])

    def test_advice_without_a_real_identity_to_map_to(self):
        r = report()
        r["meta"]["identities"] = [{"name": "Your Name", "email": "you@example.com", "commits": 64}]
        f = findings.placeholder_identity(r)
        self.assertIn("Set user.name and user.email", f[0]["advice"])
        self.assertNotIn("<you@example.com>", f[0]["advice"], "no real identity to suggest, so no invented line")

    def test_one_commit_is_one_commit(self):
        """The claims check found this on every fixture the rule fires on: it read "made 1 commits".
        A rule that only fires on the fixtures is one nobody reads in a development report."""
        r = report()
        r["meta"]["identities"] = [{"name": "Ann", "email": "ann@example.org", "commits": 1}]
        self.assertIn('"Ann <ann@example.org>" made 1 commit (100%).', findings.placeholder_identity(r)[0]["detail"])
        r["meta"]["identities"][0]["commits"] = 2
        self.assertIn("made 2 commits (100%).", findings.placeholder_identity(r)[0]["detail"])

    def test_nothing_for_real_identities(self):
        self.assertEqual(findings.placeholder_identity(report()), [])

    def test_a_stray_commit_below_one_percent_is_not_worth_a_warning(self):
        r = report()
        r["meta"]["identities"] = [{"name": "Ann", "email": "ann@x.com", "commits": 4405},
                                   {"name": "Elegant", "email": "user@a.com", "commits": 1}]
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

    def test_areas_no_longer_in_the_tree_are_not_named_in_the_advice(self):
        own = [{"entity": "flask/a.py", "author": "Ann", "added": 5000, "deleted": 0},   # the pre-src/ layout
               {"entity": "src/a.py", "author": "Ann", "added": 900, "deleted": 0},
               {"entity": "src/b.py", "author": "Bob", "added": 50, "deleted": 0}]
        tree = {"files": {"src/a.py": {"code": 1, "complexity": 0}, "src/b.py": {"code": 1, "complexity": 0}}}
        f = findings.bus_factor(report(theseus_authors={"Ann": 79, "Bob": 21}, ownership=own, size=tree))
        self.assertEqual(f[0]["advice"], "Pair someone with Ann on src/ first; it is 95% theirs.")

    def test_vendored_trees_are_not_named_in_the_advice(self):
        own = [{"entity": "vendor/github.com/x/a.go", "author": "Ann", "added": 500000, "deleted": 0},
               {"entity": "core/a.py", "author": "Ann", "added": 900, "deleted": 0},
               {"entity": "core/b.py", "author": "Bob", "added": 50, "deleted": 0}]
        f = findings.bus_factor(report(theseus_authors={"Ann": 79, "Bob": 21}, ownership=own))
        self.assertEqual(f[0]["advice"], "Pair someone with Ann on core/ first; it is 95% theirs.")

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

    def test_a_big_blob_that_left_the_tree_says_so(self):
        r = report(sizer=[{"name": "Blobs: Maximum size", "value": "21.3 MiB", "concern": 2, "ref": "static/old.mp4"}],
                   size={"files": {"static/coming-soon.mp4": {"code": 0, "complexity": 0}}})
        f = findings.sizer_concerns(r)[0]
        self.assertIn("static/old.mp4, no longer in the tree", f["detail"])
        self.assertIn("a history rewrite is only worth it for clone size", f["advice"])
        r["size"]["files"]["static/old.mp4"] = {"code": 0, "complexity": 0}
        f = findings.sizer_concerns(r)[0]
        self.assertNotIn("no longer", f["detail"])
        self.assertEqual(f["advice"], "Move large files to Git LFS or rewrite them out of history.")
        r["size"] = {}
        self.assertNotIn("no longer", findings.sizer_concerns(r)[0]["detail"], "without a tree listing nothing is claimed")

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


class SweepingCommits(unittest.TestCase):
    def sweep(self, h, files, declared=False, subject="Reformat with black"):
        return {"hash": h, "date": "2026-03-01", "author": "Ann", "subject": subject, "files": files, "added": 4 * files, "deleted": 4 * files, "declared": declared}

    def test_undeclared_sweeps_are_listed_with_the_advice_to_declare_them(self):
        r = report(activity={"sweeping": [self.sweep("fmt1", 1204), self.sweep("ren1", 60, subject="Rename Foo to Bar"), self.sweep("old1", 40, declared=True)],
                             "ignored_revs": 1})
        [f] = findings.sweeping_commits(r)
        self.assertEqual((f["severity"], f["title"]), ("info", "Sweeping commits"))
        self.assertIn("2 commits each touch 60 files or more and take out as many lines as they put in: fmt1 (1,204 files, 2026-03-01, Reformat with black); "
                      "ren1 (60 files, 2026-03-01, Rename Foo to Bar). They are left out of the churn, coupling and ownership counts.", f["detail"])
        self.assertEqual(f["advice"], "Add fmt1 and ren1 to .git-blame-ignore-revs so git blame and GitHub skip them too; 1 commit is declared there already.")
        self.assertEqual(f["rule"], {"id": "sweeping_commits", "min_files": 20, "percentile": 0.99, "tolerance": 0.1, "ref": "Kolassa, Riehle and Salim, SOFSEM 2013"})
        self.assertEqual([c["hash"] for c in f["evidence"]["commits"]], ["fmt1", "ren1"])
        self.assertEqual(f["evidence"]["declared"], 1)

    def test_nothing_when_every_sweep_is_declared_or_there_is_none(self):
        self.assertEqual(findings.sweeping_commits(report(activity={"sweeping": [self.sweep("a", 30, declared=True)], "ignored_revs": 1})), [])
        self.assertEqual(findings.sweeping_commits(report(activity={"sweeping": []})), [])
        self.assertEqual(findings.sweeping_commits(report()), [], "an output directory from before the record")


class MinorContributors(unittest.TestCase):
    def report(self, minors, coupled=None, expected_on=()):
        """Twelve hotspots; `minors[i]` minor contributors on src/f{i}.py. With `coupled`, src/f0.py is coupled
        with it and the people named in `expected_on` are major contributors to it."""
        size = {f"src/f{i}.py": {"code": 1000 - i, "complexity": 1} for i in range(12)}
        revisions = [{"entity": f"src/f{i}.py", "n-revs": 100 - i} for i in range(12)]
        authors = [{"entity": f"src/f{i}.py", "n-authors": 3 + m, "n-revs": 100 - i, "minor": m} for i, m in enumerate(minors)]
        ownership = [{"entity": f"src/f{i}.py", "author": "Ann", "added": 500, "deleted": 0, "commits": 60} for i in range(12)]
        ownership += [{"entity": "src/f0.py", "author": f"Minor {k}", "added": 1, "deleted": 0, "commits": 1} for k in range(minors[0])]
        r = report(size={"files": size}, revisions=revisions, authors=authors, ownership=ownership)
        if coupled:
            r["coupling"] = [{"entity": "src/f0.py", "coupled": coupled, "degree": 50, "average-revs": 50}]
            r["ownership"] += [{"entity": coupled, "author": who, "added": 100, "deleted": 0, "commits": 50} for who in expected_on]
        return r

    def test_minor_contributors_who_are_major_on_a_coupled_file_are_expected_traffic(self):
        r = self.report([6] + [0] * 11, coupled="src/f1.py", expected_on=["Minor 0", "Minor 1"])
        self.assertEqual(findings.minor_contributors(r), [], "6 minors, 2 of them major on the coupled f1: 4 strangers is under the threshold")
        r = self.report([12] + [0] * 11, coupled="src/f1.py", expected_on=["Minor 0", "Minor 1", "Minor 2"])
        [f] = findings.minor_contributors(r)
        self.assertEqual(f["severity"], "info", "12 minors less 3 expected is 9, under warn_at")
        self.assertIn("src/f0.py (9 of 15 authors)", f["detail"])
        self.assertIn("3 of the minor contributors are major contributors to a file these change with and are not counted", f["detail"])
        self.assertEqual(f["evidence"]["files"][0], {"file": "src/f0.py", "minor": 9, "minor_all": 12, "authors": 15, "owner": "Ann",
                                                     "expected": [{"author": "Minor 0", "via": ["src/f1.py"]}, {"author": "Minor 1", "via": ["src/f1.py"]},
                                                                  {"author": "Minor 2", "via": ["src/f1.py"]}]})
        self.assertEqual(f["rule"]["expected_share"], 0.05, "the major/minor line the exclusion uses is the rule's own")

    def test_without_coupling_the_count_is_birds_count(self):
        [f] = findings.minor_contributors(self.report([12] + [0] * 11))
        self.assertEqual((f["severity"], f["evidence"]["files"][0]["minor"], f["evidence"]["files"][0]["minor_all"], f["evidence"]["files"][0]["expected"]),
                         ("warning", 12, 12, []))
        self.assertNotIn("not counted", f["detail"])

    def test_top_hotspots_with_five_or_more_minor_contributors_are_named(self):
        [f] = findings.minor_contributors(self.report([12, 0, 6, 0, 0, 0, 0, 0, 0, 0, 9, 0]))
        self.assertEqual((f["severity"], f["title"]), ("warning", "Many minor contributors"))
        self.assertIn("2 of the top 10 hotspots have 5 or more contributors with under 5% of the file's commits each: src/f0.py (12 of 15 authors); "
                      "src/f2.py (6 of 9 authors).", f["detail"])
        self.assertNotIn("src/f10.py", f["detail"], "outside the top ten")
        self.assertEqual(f["advice"], "Have Ann, who wrote most of src/f0.py, review changes to it from anyone else; "
                                      "Bird et al. found the count of minor contributors the strongest ownership predictor of defects.")
        self.assertEqual(f["rule"], {"id": "minor_contributors", "min_minor": 5, "warn_at": 10, "minor_share": 0.05, "top_n": 10, "expected_share": 0.05,
                                     "ref": "Bird et al., FSE 2011"})
        self.assertEqual(f["evidence"]["files"][0], {"file": "src/f0.py", "minor": 12, "minor_all": 12, "authors": 15, "owner": "Ann", "expected": []})

    def test_info_below_ten_and_nothing_below_five(self):
        [f] = findings.minor_contributors(self.report([5] + [0] * 11))
        self.assertEqual(f["severity"], "info")
        self.assertEqual(findings.minor_contributors(self.report([4] + [0] * 11)), [])
        self.assertEqual(findings.minor_contributors(report()), [], "no size, no hotspots")

    def test_test_files_and_files_out_of_the_pool_are_not_counted(self):
        r = self.report([9] + [0] * 11)
        r["size"]["files"]["tests/test_x.py"] = {"code": 5000, "complexity": 1}
        r["revisions"].insert(0, {"entity": "tests/test_x.py", "n-revs": 500})
        r["authors"].append({"entity": "tests/test_x.py", "n-authors": 40, "n-revs": 500, "minor": 30})
        [f] = findings.minor_contributors(r)
        self.assertNotIn("tests/test_x.py", f["detail"])


class TangledCommits(unittest.TestCase):
    def tangled(self, h, files, dirs, subject, date="2026-03-01"):
        return {"hash": h, "date": date, "files": files, "dirs": dirs, "subject": subject}

    def test_named_with_their_share_when_there_are_enough(self):
        act = {"tangled_commits": 12, "tangled": [self.tangled("t1", 34, 9, "Fix the parser, add a cache and rename the helpers"),
                                                  self.tangled("t2", 12, 4, "Add x; fix y")], "oversized_fixes": 3}
        [f] = findings.tangled_commits(report(activity=act))
        self.assertEqual((f["severity"], f["title"]), ("info", "Tangled commits"))
        self.assertIn("12 of 100 commits (12%) touch 10 or more files across 4 or more directories under a subject that lists several changes: "
                      "t1 (34 files, 9 directories, Fix the parser, add a cache and rename the helpers); t2 (12 files, 4 directories, Add x; fix y). "
                      "A fix among them credits every file it touched, so 3 fixes over the repository's 99th percentile of lines changed are already left out of the fix counts.", f["detail"])
        self.assertEqual(f["advice"], "Split a change that does several things before merge; the fix history stays readable and the coupling stays real.")
        self.assertEqual(f["rule"], {"id": "tangled_commits", "min_files": 10, "min_dirs": 4, "min_clauses": 2, "min_share": 0.02, "min_count": 5,
                                     "ref": "Herzig and Zeller, MSR 2013"})
        self.assertEqual(f["evidence"]["count"], 12)
        self.assertEqual(f["evidence"]["oversized_fixes"], 3)

    def test_nothing_below_the_share_or_the_count(self):
        act = {"tangled_commits": 1, "tangled": [self.tangled("t1", 34, 9, "a, b")]}
        self.assertEqual(findings.tangled_commits(report(activity=act)), [], "one in a hundred is noise")
        act = {"tangled_commits": 6, "tangled": [self.tangled("t1", 34, 9, "a, b")]}
        self.assertEqual(len(findings.tangled_commits(report(activity=act))), 1, "six of a hundred is a habit")
        self.assertEqual(findings.tangled_commits(report()), [])


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

    def test_pairs_of_files_no_longer_in_the_tree_are_history(self):
        pairs = [{"entity": "static/financial-reporting.html", "coupled": "static/internal-audit.html", "degree": 100, "average-revs": 10},
                 {"entity": "sections/a.html", "coupled": "sections/b.html", "degree": 90, "average-revs": 8}]
        tree = {"files": {"sections/a.html": {"code": 1, "complexity": 0}, "sections/b.html": {"code": 1, "complexity": 0}}}
        f = findings.tight_coupling(report(coupling=pairs, size=tree))
        self.assertIn("1 pair changes", f[0]["detail"])
        self.assertNotIn("financial-reporting", f[0]["detail"])
        f = findings.tight_coupling(report(coupling=pairs))
        self.assertIn("2 pairs", f[0]["detail"], "without a tree listing every pair counts")

    def test_generated_pairs_are_the_generators_coupling(self):
        pairs = [{"entity": "js/greet.bundle.js", "coupled": "js/renderkatex.bundle.js", "degree": 83, "average-revs": 10},
                 {"entity": "js/renderkatex.bundle.js", "coupled": "js/renderkatex.js", "degree": 83, "average-revs": 10},
                 {"entity": "src/a.js", "coupled": "src/b.js", "degree": 85, "average-revs": 10}]
        r = report(coupling=pairs)
        r["meta"]["generated"] = ["js/greet.bundle.js", "js/renderkatex.bundle.js"]
        f = findings.tight_coupling(r)
        self.assertIn("1 pair changes together", f[0]["detail"])
        self.assertIn("src/a.js", f[0]["detail"])

    def test_vendored_pairs_are_somebody_elses_coupling(self):
        pairs = [{"entity": "deps/hiredis/adapters/ae.h", "coupled": "deps/hiredis/adapters/libev.h", "degree": 84, "average-revs": 10},
                 {"entity": "src/ae.c", "coupled": "deps/hiredis/net.h", "degree": 85, "average-revs": 10},
                 {"entity": "src/ae.c", "coupled": "src/networking.c", "degree": 85, "average-revs": 10}]
        f = findings.tight_coupling(report(coupling=pairs))
        self.assertIn("1 pair changes together", f[0]["detail"], "a pair with a vendored file on either side is not this repository's dependency")

    def test_a_source_file_and_its_header_are_expected_to_change_together(self):
        pairs = [{"entity": "src/vector.c", "coupled": "src/vector.h", "degree": 100, "average-revs": 20},
                 {"entity": "deps/lua/src/strbuf.c", "coupled": "deps/lua/src/strbuf.h", "degree": 94, "average-revs": 8},
                 {"entity": "src/ae.c", "coupled": "src/networking.c", "degree": 85, "average-revs": 10}]
        f = findings.tight_coupling(report(coupling=pairs))
        self.assertIn("1 pair changes together", f[0]["detail"])
        self.assertIn("src/ae.c", f[0]["detail"])

    def test_release_plumbing_pairs_are_not_a_dependency(self):
        pairs = [{"entity": "lib/sinatra/version.rb", "coupled": "rack-protection/lib/rack/protection/version.rb", "degree": 100, "average-revs": 60},
                 {"entity": "package.json", "coupled": "package-lock.json", "degree": 95, "average-revs": 40},
                 {"entity": "lib/sinatra/version.rb", "coupled": "lib/sinatra/base.rb", "degree": 85, "average-revs": 10}]
        f = findings.tight_coupling(report(coupling=pairs))
        self.assertIn("1 pair changes together", f[0]["detail"], "a version file paired with real code still counts")
        self.assertNotIn("package.json", f[0]["detail"])
        self.assertEqual(findings.tight_coupling(report(coupling=pairs[:2])), [])

    def test_two_examples_are_siblings_by_design(self):
        """curl's docs/examples/imap-ssl.c and pop3-ssl.c show one technique for two protocols. The
        shared format the advice sends the reader to find is what the family is for. One example paired
        with the code it demonstrates is still a pair worth printing."""
        pairs = [{"entity": "docs/examples/smtp-expn.c", "coupled": "docs/examples/smtp-vrfy.c", "degree": 100, "average-revs": 10},
                 {"entity": "docs/examples/imap-ssl.c", "coupled": "docs/examples/pop3-ssl.c", "degree": 90, "average-revs": 10},
                 {"entity": "docs/examples/http-post.c", "coupled": "lib/http.c", "degree": 85, "average-revs": 10}]
        f = findings.tight_coupling(report(coupling=pairs))
        self.assertIn("1 pair changes together", f[0]["detail"])
        self.assertIn("lib/http.c", f[0]["detail"], "an example and the code it demonstrates still count")
        self.assertNotIn("smtp-expn", f[0]["detail"])
        self.assertEqual(findings.tight_coupling(report(coupling=pairs[:2])), [])

    def test_single_pair_reads_grammatically(self):
        pairs = [{"entity": "a", "coupled": "b", "degree": 100, "average-revs": 10}]
        f = findings.tight_coupling(report(coupling=pairs))
        self.assertIn("1 pair changes together", f[0]["detail"])

    def test_a_directory_of_files_that_change_as_one_is_one_cluster(self):
        files = [f"rich/_unicode_data/unicode{n}.py" for n in ("10", "11", "12", "13")]
        pairs = [{"entity": a, "coupled": b, "degree": 100, "average-revs": 5} for i, a in enumerate(files) for b in files[i + 1:]]
        pairs.append({"entity": "rich/a.py", "coupled": "rich/b.py", "degree": 90, "average-revs": 8})
        f = findings.tight_coupling(report(coupling=pairs))
        self.assertIn("4 files in rich/_unicode_data/ change together at least 80% of the time, and 1 more pair does: rich/a.py + rich/b.py (90%).", f[0]["detail"])
        self.assertNotIn("unicode10", f[0]["detail"])
        self.assertTrue(f[0]["detail"].endswith("Review rich/_unicode_data/ first: 4 files change as one; a generator or a shared layout links them."), f[0]["detail"])
        f = findings.tight_coupling(report(coupling=pairs[:-1]))
        self.assertIn("4 files in rich/_unicode_data/ change together at least 80% of the time, 6 pairs in all.", f[0]["detail"])

    def test_nothing_when_no_tight_pairs(self):
        self.assertEqual(findings.tight_coupling(report()), [])


class ReleasePlumbing(unittest.TestCase):
    def test_a_generated_file_is_not_a_bug_magnet(self):
        fixes = [{"entity": "single_include/json.hpp", "n-fixes": 338, "last-fix": "2026-09-01", "recent-fixes": 43},
                 {"entity": "include/json.hpp", "n-fixes": 116, "last-fix": "2026-09-01", "recent-fixes": 15}]
        r = report(fixes=fixes)
        r["meta"]["generated"] = ["single_include/json.hpp"]
        f = findings.bug_magnets(r)
        self.assertIn("include/json.hpp (15 recent", f[0]["detail"])
        self.assertNotIn("single_include", f[0]["detail"])

    def test_a_manifest_is_not_a_bug_magnet(self):
        fixes = [{"entity": "package.json", "n-fixes": 20, "last-fix": "2026-09-01", "recent-fixes": 6},
                 {"entity": "lib/reply.js", "n-fixes": 10, "last-fix": "2026-09-01", "recent-fixes": 4}]
        f = findings.bug_magnets(report(fixes=fixes))
        self.assertIn("lib/reply.js", f[0]["detail"])
        self.assertNotIn("package.json", f[0]["detail"])


class Dormant(unittest.TestCase):
    def test_a_year_without_commits_is_a_warning_that_dates_the_last_one(self):
        r = report()
        r["meta"].update({"last_date": "2025-06-14", "now": "2026-09-17"})
        f = findings.dormant(r)
        self.assertEqual(f[0]["severity"], "warning")
        self.assertEqual(f[0]["title"], "Dormant repository")
        self.assertIn("No commits since 2025-06-14, 15 months ago.", f[0]["detail"])
        self.assertIn("stopped", f[0]["advice"])

    def test_a_recent_commit_is_not_dormant(self):
        r = report()
        r["meta"].update({"last_date": "2026-06-14", "now": "2026-09-17"})
        self.assertEqual(findings.dormant(r), [])
        self.assertEqual(findings.dormant(report()), [], "no dates, no finding")

    def test_stale_files_are_not_reported_for_a_dormant_repository(self):
        age = [{"entity": f"f{i}", "age-months": 15} for i in range(10)]
        r = report(age=age)
        r["meta"].update({"last_date": "2025-06-14", "now": "2026-09-17"})
        self.assertEqual(findings.stale_files(r), [], "every file is untouched because nothing is; the dormancy finding says so")


class StaleFiles(unittest.TestCase):
    def test_info_when_a_third_untouched_for_a_year(self):
        age = [{"entity": f"f{i}", "age-months": 12} for i in range(4)] + [{"entity": "g", "age-months": 0} for _ in range(6)]
        f = findings.stale_files(report(age=age))
        self.assertIn("40%", f[0]["detail"])
        self.assertIn("Consider deleting what nobody has needed; dead code hides in untouched files.", f[0]["detail"])

    def test_nothing_when_fresh(self):
        self.assertEqual(findings.stale_files(report()), [])

    def test_the_evidence_names_files_not_only_how_many(self):
        """A count cannot be checked against a later tree, so the rule could not be scored at all
        (remediation.NO_SUBJECTS), and a reader could not act on it either."""
        age = [{"entity": f"old{i}.py", "age-months": 20 + i} for i in range(12)] + \
              [{"entity": "fresh.py", "age-months": 0}]
        evidence = findings.stale_files(report(age=age))[0]["evidence"]
        self.assertEqual((evidence["stale"], evidence["files"]), (12, 13))
        self.assertEqual(len(evidence["untouched"]), 10, "capped, like every other rule's evidence")
        self.assertNotIn("fresh.py", evidence["untouched"])

    def test_it_names_the_largest_untouched_files_not_the_oldest(self):
        """The advice is to delete dead code, and a file's lines are how much of it is at stake: the
        oldest files in a long-lived repository are its empty `__init__.py`s."""
        age = [{"entity": "pkg/__init__.py", "age-months": 200},
               {"entity": "legacy/parser.py", "age-months": 30},
               {"entity": "legacy/tiny.py", "age-months": 40}]
        tree = {"pkg/__init__.py": {"code": 0, "complexity": 0},
                "legacy/parser.py": {"code": 900, "complexity": 40},
                "legacy/tiny.py": {"code": 3, "complexity": 0}}
        evidence = findings.stale_files(report(age=age, size={"files": tree}))[0]["evidence"]
        self.assertEqual(evidence["untouched"], ["legacy/parser.py", "legacy/tiny.py", "pkg/__init__.py"],
                         "largest first, then oldest")

    def test_vendored_and_generated_files_count_neither_way(self):
        """A checked-in jquery.js has not changed in years because nobody maintains it here, and the
        advice is not to delete it. Out of the numerator and the denominator both, so the share is a
        share of the repository's own files."""
        age = [{"entity": "vendor/jquery.js", "age-months": 90}, {"entity": "api_pb2.py", "age-months": 90},
               {"entity": "legacy/parser.py", "age-months": 90}, {"entity": "live.py", "age-months": 0}]
        tree = {a["entity"]: {"code": 10, "complexity": 0} for a in age}
        r = report(age=age, size={"files": tree})
        r["meta"]["generated"] = ["api_pb2.py"]
        f = findings.stale_files(r)
        self.assertIn("50% of files (1)", f[0]["detail"], "one of two, not three of four")
        self.assertEqual(f[0]["evidence"]["untouched"], ["legacy/parser.py"])

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
        r["meta"]["identities"] = [{"name": "Grzegorz Bankosz", "email": "g@a.com", "commits": 41,
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
        self.assertTrue(f[0]["detail"].endswith("Review core/parser.py and core/util.py before the next release; fixes keep landing there."), f[0]["detail"])

    def test_info_below_five_recent_fixes(self):
        f = findings.bug_magnets(report(fixes=self.FIXES[1:2]))
        self.assertEqual(f[0]["severity"], "info")
        self.assertTrue(f[0]["detail"].endswith("Review core/util.py before the next release; fixes keep landing there."), f[0]["detail"])

    def test_nothing_without_recent_fixes(self):
        self.assertEqual(findings.bug_magnets(report(fixes=self.FIXES[3:])), [])
        self.assertEqual(findings.bug_magnets(report()), [])


class Plural(unittest.TestCase):
    """The report is the product, so its prose agrees with its numbers. These three were found by reading
    the six development reports, not the code."""

    def test_a_noun_ending_in_a_sibilant_takes_es(self):
        self.assertEqual(findings._plural(2, "IPv4 address"), "2 IPv4 addresses", "ghidra read '2 IPv4 addresss'")
        self.assertEqual(findings._plural(1, "IPv4 address"), "1 IPv4 address")
        for word, many in (("box", "boxes"), ("branch", "branches"), ("dish", "dishes")):
            self.assertEqual(findings._plural(3, word), f"3 {many}")

    def test_every_other_noun_the_rules_pass_still_takes_s(self):
        for word in ("place", "commit", "other file", "source file", "pair", "more pair", "param", "path",
                     "executable", "manifest", "lock file", "distinct value", "empty catch block", "function"):
            self.assertEqual(findings._plural(2, word), f"2 {word}s")
            self.assertEqual(findings._plural(1, word), f"1 {word}")


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

    def test_an_anonymous_function_is_named_by_its_place(self):
        fns = [{"file": "completions.go", "function": "(anonymous)", "ccn": 47, "nloc": 136, "params": 1, "start": 316, "end": 585}]
        f = findings.brain_methods(report(functions=fns))
        self.assertIn("(anonymous) (completions.go:316) complexity 47, 136 lines, 1 param", f[0]["detail"])
        self.assertEqual(f[0]["advice"], "Split the anonymous function at completions.go:316 first, before the next change lands there.")

    def test_a_labelled_nameless_function_is_listed_by_its_label_and_placed_by_its_line(self):
        fns = [{"file": "server/routes.ts", "function": 'app.post("/api/x", async (req, res) => {', "anonymous": True,
                "ccn": 47, "nloc": 136, "params": 1, "start": 316, "end": 585, "suspect": ""}]
        f = findings.brain_methods(report(functions=fns))
        self.assertIn('app.post("/api/x", async (req, res) => { (server/routes.ts:316) complexity 47, 136 lines, 1 param', f[0]["detail"])
        self.assertEqual(f[0]["advice"], "Split the anonymous function at server/routes.ts:316 first, before the next change lands there.")

    def test_a_suspect_span_is_not_a_brain_method(self):
        fns = [{"file": "core/parser.py", "function": "parse", "ccn": 41, "nloc": 220, "params": 9, "start": 10, "end": 300,
                "suspect": "opens a block at line 120 no deeper than its own start"},
               {"file": "core/util.py", "function": "tidy", "ccn": 16, "nloc": 120, "params": 2, "start": 1, "end": 130, "suspect": ""}]
        f = findings.brain_methods(report(functions=fns))
        self.assertNotIn("parse", f[0]["detail"], "a span lizard may have mis-parsed is not advice")
        self.assertEqual(f[0]["advice"], "Split tidy in core/util.py first, before the next change lands there.")
        self.assertEqual(findings.brain_methods(report(functions=fns[:1])), [])

    def test_generated_files_are_not_brain_methods(self):
        fns = [{"file": "lib/config-validator.js", "function": "validate10", "ccn": 373, "nloc": 1150, "params": 5, "start": 1, "end": 1150},
               {"file": "lib/reply.js", "function": "onSendEnd", "ccn": 34, "nloc": 180, "params": 2, "start": 1, "end": 180}]
        r = report(functions=fns)
        r["meta"]["generated"] = ["lib/config-validator.js"]
        f = findings.brain_methods(r)
        self.assertEqual(f[0]["advice"], "Split onSendEnd in lib/reply.js first, before the next change lands there.")
        self.assertNotIn("validate10", f[0]["detail"])

    def test_example_code_is_not_a_brain_method(self):
        fns = [{"file": "examples/named-pipe-ready.rs", "function": "windows_main", "ccn": 25, "nloc": 109, "params": 0, "start": 1, "end": 109},
               {"file": "tokio/src/sync/notify.rs", "function": "poll_notified", "ccn": 17, "nloc": 140, "params": 2, "start": 1, "end": 140}]
        f = findings.brain_methods(report(functions=fns))
        self.assertEqual(f[0]["advice"], "Split poll_notified in tokio/src/sync/notify.rs first, before the next change lands there.")
        self.assertNotIn("windows_main", f[0]["detail"])

    def test_an_amalgamated_file_is_not_a_brain_method(self):
        fns = []
        for i in range(25):
            fns.append({"file": f"include/part{i % 3}.hpp", "function": f"f{i}", "ccn": 30, "nloc": 120, "params": 1, "start": 1, "end": 120})
            fns.append({"file": "single_include/all.hpp", "function": f"f{i}", "ccn": 30, "nloc": 120, "params": 1, "start": 1, "end": 120})
        f = findings.brain_methods(report(functions=fns))
        self.assertNotIn("single_include", f[0]["detail"])
        self.assertIn("include/part0.hpp", f[0]["detail"])

    def test_vendored_functions_are_not_brain_methods(self):
        fns = [{"file": "vendor/github.com/google/jsonschema-go/jsonschema/validate.go", "function": "validate", "ccn": 179, "nloc": 424, "params": 3, "start": 1, "end": 424},
               {"file": "processor/workers.go", "function": "countLoopGeneric", "ccn": 56, "nloc": 164, "params": 8, "start": 1, "end": 164}]
        f = findings.brain_methods(report(functions=fns))
        self.assertEqual(f[0]["advice"], "Split countLoopGeneric in processor/workers.go first, before the next change lands there.")
        self.assertNotIn("vendor/", f[0]["detail"])
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
        r["meta"]["duplicates"] = {"status": "failed"}
        self.assertIn("4.2% of lines are duplicated. Duplicate detection failed part way, so there may be more. Extract", findings.duplication(r)[0]["detail"])
        r["meta"]["duplicates"] = {"status": "run"}
        r["meta"]["functions"] = {"status": "failed"}
        self.assertNotIn("part way", findings.duplication(r)[0]["detail"], "lizard's status says nothing about jscpd's step")

    def test_a_block_whose_every_copy_is_vendored_or_generated_is_not_this_repositorys(self):
        dup = {"rate": 4.2, "blocks": [{"lines": 71, "places": [("vendor/a.py", 10, 80), ("vendor/b.py", 5, 75)]},
                                       {"lines": 50, "places": [("dist/app.js", 1, 50), ("dist/app.min.js", 1, 50)]},
                                       {"lines": 40, "places": [("src/mine.py", 1, 40), ("vendor/a.py", 100, 139)]}]}   # sorted, as the loader gives them
        r = report(duplicates=dup)
        r["meta"]["generated"] = ["dist/app.js", "dist/app.min.js"]   # as the run records them
        f = findings.duplication(r)
        self.assertEqual(f[0]["advice"], "Extract the 40-line block shared by src/mine.py and vendor/a.py first.")
        self.assertIn("1 block(s)", f[0]["detail"])


class VulnerableDependencies(unittest.TestCase):
    def row(self, name, version, source, score=7.5, fixed="9.9.9", aliases=("CVE-2024-1",), ids=("GHSA-x",), malicious=False):
        sev = "critical" if malicious or (score is not None and score >= 9) else "high" if score is not None and score >= 7 else "unknown"
        return {"name": name, "version": version, "ecosystem": "npm", "source": source, "ids": list(ids), "aliases": list(aliases),
                "advisories": 1, "score": score, "severity": sev, "summary": "", "fixed": fixed, "malicious": malicious}

    def deps(self, rows):
        return {"status": "scanned", "sources": [{"path": r["source"], "packages": 10} for r in rows], "packages": 10 * len(rows),
                "vulnerable": rows, "database_date": "2026-09-17"}

    def test_a_vulnerable_package_in_a_source_lock_file_is_a_warning_naming_the_fix(self):
        r = report(dependencies=self.deps([self.row("lodash", "4.17.15", "frontend/yarn.lock", score=7.2, fixed="4.17.21")]))
        [f] = findings.vulnerable_dependencies(r)
        self.assertEqual((f["severity"], f["title"]), ("warning", "Vulnerable dependencies"))
        self.assertIn("1 vulnerable package in 1 lock file: lodash 4.17.15 (CVE-2024-1, 7.2, fixed in 4.17.21) in frontend/yarn.lock.", f["detail"])
        self.assertEqual(f["advice"], "Upgrade lodash to 4.17.21 in frontend/yarn.lock first; it scores 7.2. " + findings.IGNORE_DEPS)
        self.assertIn("CVE-2024-1", f["evidence"]["packages"][0]["aliases"], "the identifier the sentence quotes is in the evidence too")

    def test_a_critical_score_makes_it_critical_and_the_worst_leads(self):
        rows = [self.row("minimist", "0.0.8", "package-lock.json", score=9.8, fixed="1.2.6"), self.row("lodash", "4.17.15", "package-lock.json", score=7.2)]
        [f] = findings.vulnerable_dependencies(report(dependencies=self.deps(rows)))
        self.assertEqual(f["severity"], "critical")
        self.assertTrue(f["advice"].startswith("Upgrade minimist to 1.2.6 in package-lock.json first; it scores 9.8."), f["advice"])
        self.assertIn("2 vulnerable packages in 1 lock file", f["detail"])

    def test_a_malicious_package_is_critical_without_a_score_and_the_advice_is_to_remove_it(self):
        rows = [self.row("evil-pad", "1.0.2", "package-lock.json", score=None, fixed=None, aliases=(), ids=("MAL-2026-1234",), malicious=True),
                self.row("lodash", "4.17.15", "package-lock.json", score=7.2)]
        [f] = findings.vulnerable_dependencies(report(dependencies=self.deps(rows)))
        self.assertEqual(f["severity"], "critical")
        self.assertIn("evil-pad 1.0.2 (MAL-2026-1234, malicious, no fix yet) in package-lock.json", f["detail"])
        self.assertEqual(f["advice"], "Remove evil-pad 1.0.2 from package-lock.json first; MAL-2026-1234 lists it as malicious, so no version fixes it. " + findings.IGNORE_DEPS)
        self.assertEqual(f["rule"]["malicious_prefix"], "MAL-")
        self.assertIs(f["evidence"]["packages"][0]["malicious"], True)
        self.assertIs(f["evidence"]["packages"][1]["malicious"], False)

    def test_a_malicious_package_in_a_test_lock_file_stays_a_note(self):
        rows = [self.row("evil-pad", "1.0.2", "tests/e2e/package-lock.json", score=None, fixed=None, aliases=(), ids=("MAL-2026-1234",), malicious=True)]
        [f] = findings.vulnerable_dependencies(report(dependencies=self.deps(rows)))
        self.assertEqual(f["severity"], "info")
        self.assertTrue(f["advice"].startswith("Remove evil-pad 1.0.2 from tests/e2e/package-lock.json first"), f["advice"])

    def test_test_example_and_vendored_lock_files_are_a_note_apart(self):
        rows = [self.row("a", "1", "tests/e2e/yarn.lock", score=9.8), self.row("b", "1", "examples/demo/Cargo.lock", score=None, fixed=None, aliases=()),
                self.row("c", "1", "uv.lock", score=5.0)]
        found = findings.vulnerable_dependencies(report(dependencies=self.deps(rows)))
        self.assertEqual([f["severity"] for f in found], ["warning", "info"])
        self.assertIn("only in test, example or vendored lock files", found[1]["title"])
        self.assertIn("b 1 (GHSA-x, no fix yet) in examples/demo/Cargo.lock", found[1]["detail"])
        self.assertIn("a 1 (CVE-2024-1, 9.8, fixed in 9.9.9) in tests/e2e/yarn.lock", found[1]["detail"])

    def test_no_fix_yet_changes_the_advice(self):
        [f] = findings.vulnerable_dependencies(report(dependencies=self.deps([self.row("x", "1", "go.sum", score=None, fixed=None)])))
        self.assertEqual(f["severity"], "warning")
        self.assertTrue(f["advice"].startswith("Look at x in go.sum first, which has no fixed version yet."), f["advice"])

    def test_more_than_three_are_counted(self):
        rows = [self.row(f"p{i}", "1", "package-lock.json", score=5.0) for i in range(5)]
        [f] = findings.vulnerable_dependencies(report(dependencies=self.deps(rows)))
        self.assertIn("p2 1 (CVE-2024-1, 5.0, fixed in 9.9.9) in package-lock.json and 2 more.", f["detail"])

    def test_nothing_without_a_scan_or_without_vulnerable_packages(self):
        self.assertEqual(findings.vulnerable_dependencies(report()), [])
        self.assertEqual(findings.vulnerable_dependencies(report(dependencies={"status": "no-database"})), [])
        self.assertEqual(findings.vulnerable_dependencies(report(dependencies=self.deps([]))), [])


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

    def test_areas_no_longer_in_the_tree_are_not_islands(self):
        own = [{"entity": "src/a.rs", "author": "Ann", "added": 30000, "deleted": 0},   # moved to crates/ years ago
               {"entity": "grep-printer/a.rs", "author": "Ann", "added": 20000, "deleted": 0},
               {"entity": "crates/core/a.rs", "author": "Bob", "added": 300, "deleted": 0}]
        tree = {"files": {"crates/core/a.rs": {"code": 300, "complexity": 1}}}
        f = findings.knowledge_islands(report(ownership=own, size=tree))
        self.assertEqual(f[0]["advice"], "Pair someone with Bob on crates/core/ first; it is the largest at 300 lines.",
                         "with the vanished directories gone, crates/ holds everything and the map descends into it")
        self.assertNotIn("src/", f[0]["detail"])
        self.assertIn("100% of all lines added", f[0]["detail"], "lines in vanished directories are not in the denominator")
        f = findings.knowledge_islands(report(ownership=own))
        self.assertIn("src/", f[0]["detail"], "without a tree listing every area counts")

    def test_vendored_trees_are_not_islands(self):
        own = [{"entity": "vendor/github.com/x/a.go", "author": "Ann", "added": 500000, "deleted": 0},
               {"entity": "web/node_modules/y/b.js", "author": "Ann", "added": 90000, "deleted": 0},
               {"entity": "core/a.py", "author": "Bob", "added": 300, "deleted": 0}]
        f = findings.knowledge_islands(report(ownership=own))
        self.assertEqual(f[0]["advice"], "Pair someone with Bob on core/ first; it is the largest at 300 lines.")
        self.assertNotIn("vendor/", f[0]["detail"])
        self.assertNotIn("web/", f[0]["detail"])
        self.assertIn("100% of all lines added", f[0]["detail"], "vendored lines are not in the denominator either")

    def test_an_island_that_is_a_sliver_of_the_code_is_not_named(self):
        # laravel: 216 root-file lines by one person against 900,000 lines of src/; prettier's benchmarks/
        own = [{"entity": "composer.json", "author": "Ann", "added": 216, "deleted": 0},
               {"entity": "src/a.php", "author": "Bob", "added": 30000, "deleted": 0},
               {"entity": "src/b.php", "author": "Cat", "added": 20000, "deleted": 0}]
        self.assertEqual(findings.knowledge_islands(report(ownership=own)), [], "under 1% of the lines is not knowledge worth pairing on")
        own[0]["added"] = 600
        f = findings.knowledge_islands(report(ownership=own))
        self.assertEqual(f[0]["advice"], "Pair someone with Ann on (root files) first; it is the largest at 600 lines.")

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

    def test_files_reverted_once_each_are_spread_not_named(self):
        # tokio: 16 reverts across 16 files; naming one of them as "most often backed out" says nothing
        f = findings.reverts(self._report(16, commits=5008, reverted={f"src/f{i}.rs": 1 for i in range(16)}))
        self.assertEqual(f[0]["detail"].split(" Look")[0], "16 of 5008 commits are reverts, spread over 16 files, none backed out twice.")
        self.assertEqual(f[0]["advice"], "Look at why they were backed out; no single file keeps coming back.")
        self.assertEqual(f[0]["evidence"]["files"], 16, "the file count the sentence quotes is in the evidence too")

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

    def test_zero_commits_in_meta_gives_nothing_below_and_at_or_above_min_count(self):
        self.assertEqual(findings.reverts(self._report(3, commits=0, reverted={"a.py": 3})), [])
        self.assertEqual(findings.reverts(self._report(6, commits=0, reverted={"a.py": 6})), [])


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

    def test_areas_no_longer_in_the_tree_are_not_named(self):
        r = self._report(theseus_authors={"Ann": 60, "Bob": 40},
                         age=[{"entity": "flask/a.py", "age-months": 2}, {"entity": "src/x.py", "age-months": 2}],
                         ownership=[{"entity": "flask/a.py", "author": "Bob", "added": 8000, "deleted": 0},   # the old layout, all Bob's
                                    {"entity": "src/x.py", "author": "Bob", "added": 300, "deleted": 0},
                                    {"entity": "app/b.py", "author": "Ann", "added": 900, "deleted": 0}],
                         size={"files": {"src/x.py": {"code": 1, "complexity": 0}, "app/b.py": {"code": 1, "complexity": 0}}})
        f = findings.knowledge_loss(r)
        self.assertIn("Areas mostly theirs: src/ (100%).", f[0]["detail"])
        self.assertNotIn("flask/", f[0]["detail"])
        self.assertEqual(f[0]["advice"], "Pair someone on src/ first; nobody who wrote it is around to ask.")

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

    def test_areas_beyond_three_are_counted_not_named(self):
        r = self._report(theseus_authors={"Ann": 60, "Bob": 40},
                         age=[{"entity": "a1/x.py", "age-months": 2}],
                         ownership=[{"entity": "a1/x.py", "author": "Bob", "added": 300, "deleted": 0},
                                    {"entity": "a2/x.py", "author": "Bob", "added": 300, "deleted": 0},
                                    {"entity": "a3/x.py", "author": "Bob", "added": 300, "deleted": 0},
                                    {"entity": "a4/x.py", "author": "Bob", "added": 300, "deleted": 0},
                                    {"entity": "app/b.py", "author": "Ann", "added": 900, "deleted": 0}])
        f = findings.knowledge_loss(r)
        self.assertIn("Areas mostly theirs: a1/ (100%), a2/ (100%), a3/ (100%) and 1 more.", f[0]["detail"])

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

    def test_everyone_under_one_percent_is_counted_not_named(self):
        # total 1000; 20 gone people at 5 lines each is exactly the 10% floor, and each rounds to 0% individually.
        people = {f"P{i}": 5 for i in range(20)}
        r = self._report(theseus_authors={"Ann": 900, **people})
        for name in people:
            r["activity"]["authors"][name] = {"commits": 1, "added": 0, "deleted": 0, "first": "2020-01-01", "last": "2024-06-01"}
        f = findings.knowledge_loss(r)
        self.assertIn("20 people at under 1% each", f[0]["detail"])


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
                   dependencies={"status": "scanned", "sources": [{"path": "uv.lock", "packages": 3}], "packages": 3, "database_date": None,
                                 "vulnerable": [{"name": "x", "version": "1", "ecosystem": "PyPI", "source": "uv.lock", "ids": ["GHSA-1"], "aliases": [],
                                                 "advisories": 1, "score": 8.0, "severity": "high", "summary": "", "fixed": "2"}]},
                   age=[{"entity": "a.py", "age-months": 30}, {"entity": "b.py", "age-months": 0}],
                   ownership=[{"entity": "core/a.py", "author": "Ann", "added": 950, "deleted": 0}])
        r["meta"]["identities"] = [{"name": "Ann", "email": "ann@x.com", "commits": 5, "aliases": [{"name": "root", "email": "root@localhost", "commits": 1}]}]
        found = findings.evaluate(r)
        self.assertEqual({f["title"] for f in found} >= {"Bus factor of one", "Repo health", "Bug magnets", "Brain methods", "Duplicated code",
                                                      "A large share of files is untouched", "Unconfigured git identity", "Knowledge islands",
                                                      "Vulnerable dependencies"}, True)
        for f in found:
            self.assertTrue(f.get("advice"), f["title"])
            self.assertTrue(f["detail"].endswith(" " + f["advice"]), f["detail"])
        import json
        for f in found:
            self.assertTrue(f["rule"].get("id"), f["title"])
            self.assertIsInstance(f["evidence"], dict, f["title"])
            json.dumps(f)   # tuples and sets would not survive the export
        self.assertEqual(len({f["rule"]["id"] for f in found}), len({f["title"] for f in found}), "one id per kind of finding")

    def test_a_name_with_an_initial_keeps_its_advice(self):
        f = findings.bus_factor(report(theseus_authors={"Robert C. Martin": 90, "Bob": 10}))[0]
        self.assertEqual(f["advice"], "Pair someone with Robert C. Martin before they are unavailable.")

    def test_a_bug_magnet_can_be_rechecked_from_its_own_rule_and_evidence(self):
        f = findings.bug_magnets(report(fixes=[{"entity": "a.py", "n-fixes": 9, "last-fix": "2026-09-01", "recent-fixes": 5},
                                               {"entity": "b.py", "n-fixes": 3, "last-fix": "2026-08-01", "recent-fixes": 3}]))[0]
        self.assertEqual(f["rule"], {"id": "bug_magnets", "min_recent": 3, "warn_at": 5, "window_months": 6, "fix": "the commit subject says so",
                                     "oversized": "a fix over the repository's 99th percentile of lines changed credits nothing"})
        self.assertEqual(f["evidence"], {"count": 2, "files": [{"file": "a.py", "recent_fixes": 5, "fixes": 9}, {"file": "b.py", "recent_fixes": 3, "fixes": 3}]})
        self.assertTrue(all(x["recent_fixes"] >= f["rule"]["min_recent"] for x in f["evidence"]["files"]))

    def test_a_bus_factor_can_be_rechecked_from_its_own_rule_and_evidence(self):
        f = findings.bus_factor(report(theseus_authors={"Ann": 79, "Bob": 21}))[0]
        self.assertEqual(f["rule"], {"id": "bus_factor", "threshold": 0.7, "min_lines": 200})
        self.assertEqual(f["evidence"], {"author": "Ann", "lines": 79, "total_lines": 100, "areas": []})
        self.assertGreater(f["evidence"]["lines"] / f["evidence"]["total_lines"], f["rule"]["threshold"])


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


class Hygiene(unittest.TestCase):
    def h(self, **over):
        base = {"actions": {"unpinned": [], "unpinned_count": 0, "pinned": 0, "local": 0},
                "lockfiles": {"drift": [], "drift_count": 0, "missing": [], "missing_count": 0, "pairs": 0},
                "updates": {"tool": "dependabot", "covered": [], "uncovered": []},
                "presence": {"license": "LICENSE", "security_policy": "SECURITY.md", "codeowners": None, "codeowners_missing": []},
                "confusion": {"scoped_public": [], "scoped_public_count": 0, "registries": {}, "pip_extra_index": []},
                "install": {"lockfile": [], "lockfile_count": 0, "manifests": [], "setup_py": []},
                "binaries": {"binaries": 0, "executables": [], "executables_count": 0, "by_name": [], "lfs_unpointed": []},
                "submodules": {"count": 0, "insecure": [], "credentials": [], "relative": [], "floating": []},
                "symlinks": {"count": 0, "outside": [], "into_git": []},
                "trojan": {"files": 10, "bidi": [], "bidi_count": 0, "mixed_script": [], "mixed_script_count": 0}}
        for k, v in over.items():
            base[k] = {**base[k], **v}
        return report(hygiene=base)

    def by_id(self, r):
        return {f["rule"]["id"]: f for f in findings.hygiene_findings(r)}

    def test_a_clean_repository_has_none_and_an_old_output_directory_too(self):
        self.assertEqual(findings.hygiene_findings(self.h()), [])
        self.assertEqual(findings.hygiene_findings(report()), [])

    def test_unpinned_actions_are_a_warning_naming_the_step_and_the_fix(self):
        f = self.by_id(self.h(actions={"unpinned": [{"file": ".github/workflows/ci.yml", "uses": "actions/checkout@v4"},
                                                    {"file": ".github/workflows/ci.yml", "uses": "org/deploy@main"}], "unpinned_count": 2, "pinned": 1}))["unpinned_actions"]
        self.assertEqual((f["severity"], f["title"]), ("warning", "Actions pinned by tag or branch"))
        self.assertIn("2 of 3 workflow steps use an action by tag or branch: actions/checkout@v4 and org/deploy@main in .github/workflows/ci.yml.", f["detail"])
        self.assertTrue(f["advice"].startswith("Pin org/deploy@main to a full commit SHA first"), f["advice"])
        self.assertEqual(f["rule"]["scorecard"], "Pinned-Dependencies")

    def test_lockfile_drift_and_missing_lockfiles(self):
        found = self.by_id(self.h(lockfiles={"drift": [{"manifest": "package.json", "lockfile": "package-lock.json", "manifest_date": "2026-03-01", "lockfile_date": "2026-01-01"}],
                                             "drift_count": 1, "missing": [{"manifest": "lib/Cargo.toml", "expected": ["Cargo.lock"]}], "missing_count": 1, "pairs": 3}))
        self.assertEqual(found["lockfile_drift"]["severity"], "warning")
        self.assertIn("package.json changed on 2026-03-01, after package-lock.json last did on 2026-01-01", found["lockfile_drift"]["detail"])
        self.assertEqual(found["lockfile_missing"]["severity"], "info")
        self.assertIn("lib/Cargo.toml has no Cargo.lock", found["lockfile_missing"]["detail"])

    def test_update_tooling(self):
        f = self.by_id(self.h(updates={"tool": "dependabot", "covered": ["npm"], "uncovered": ["gomod", "pip"]}))["dependency_updates"]
        self.assertIn("dependabot.yml covers npm but not gomod and pip", f["detail"])
        f = self.by_id(self.h(updates={"tool": None, "covered": [], "uncovered": ["npm"]}))["dependency_updates"]
        self.assertIn("No dependency update tool is declared for npm", f["detail"])

    def test_policy_files(self):
        f = self.by_id(self.h(presence={"license": None, "security_policy": None, "codeowners": ".github/CODEOWNERS", "codeowners_missing": ["/gone/"]}))["repo_policy"]
        self.assertEqual(f["severity"], "info")
        self.assertIn("No licence file at the root; no security policy (SECURITY.md); .github/CODEOWNERS names 1 path that matches no tracked file: /gone/.", f["detail"])

    def test_dependency_confusion_is_a_warning_when_a_scoped_package_left_its_registry(self):
        f = self.by_id(self.h(confusion={"scoped_public": [{"lockfile": "package-lock.json", "package": "@acme/auth", "registry": "registry.npmjs.org",
                                                           "declared": "npm.acme.internal"}], "scoped_public_count": 1}))["dependency_confusion"]
        self.assertEqual(f["severity"], "warning")
        self.assertIn("@acme/auth resolved from registry.npmjs.org in package-lock.json, though .npmrc sends @acme to npm.acme.internal", f["detail"])
        f = self.by_id(self.h(confusion={"pip_extra_index": ["pip.conf"]}))["dependency_confusion"]
        self.assertEqual(f["severity"], "info")

    def test_install_scripts_are_a_note(self):
        f = self.by_id(self.h(install={"lockfile": [{"lockfile": "package-lock.json", "package": "esbuild"}], "lockfile_count": 1,
                                       "manifests": [{"file": "package.json", "scripts": ["postinstall"]}], "setup_py": [{"file": "setup.py", "calls": ["subprocess.run"]}]}))["install_scripts"]
        self.assertEqual(f["severity"], "info")
        self.assertIn("1 locked package runs an install script (esbuild); package.json declares postinstall; setup.py calls subprocess.run", f["detail"])

    def test_committed_executables_outside_tests_are_a_warning(self):
        f = self.by_id(self.h(binaries={"binaries": 3, "executables": [{"file": "build/app.exe", "format": "PE"}, {"file": "tests/data/x.so", "format": "ELF"}],
                                        "executables_count": 2, "lfs_unpointed": ["data/big.bin"]}))["committed_binaries"]
        self.assertEqual(f["severity"], "warning")
        self.assertIn("build/app.exe (PE)", f["detail"])
        self.assertNotIn("tests/data/x.so", f["detail"], "a test fixture is expected to be a binary")
        self.assertIn("data/big.bin is committed as a blob though .gitattributes sends it to LFS", f["detail"])
        self.assertEqual(f["rule"]["scorecard"], "Binary-Artifacts")

    def test_submodules_symlinks_and_trojan_source(self):
        found = self.by_id(self.h(submodules={"count": 2, "credentials": [{"name": "c", "url": "https://***@example.com/c.git"}], "insecure": [{"name": "a", "url": "http://x/a.git"}]},
                                  symlinks={"count": 2, "outside": [{"link": "src/out", "target": "../../etc/passwd"}]},
                                  trojan={"bidi": [{"file": "src/a.py", "line": 2, "char": "U+202E"}], "bidi_count": 1,
                                          "mixed_script": [{"file": "src/b.py", "line": 2, "token": "prоcess", "scripts": ["CYRILLIC", "LATIN"]}], "mixed_script_count": 1}))
        self.assertEqual(found["submodule_urls"]["severity"], "critical", "a credential in a tracked file")
        self.assertIn("c carries credentials in its URL", found["submodule_urls"]["detail"])
        self.assertNotIn("tok", found["submodule_urls"]["detail"])
        self.assertEqual(found["unsafe_symlinks"]["severity"], "warning")
        self.assertIn("src/out points outside the tree (../../etc/passwd)", found["unsafe_symlinks"]["detail"])
        self.assertEqual(found["trojan_source"]["severity"], "critical")
        self.assertIn("src/a.py:2 holds U+202E", found["trojan_source"]["detail"])
        self.assertIn("prоcess at src/b.py:2 mixes CYRILLIC and LATIN", found["trojan_source"]["detail"])


class Structure(unittest.TestCase):
    def base(self, **structure):
        size = {f"src/f{i}.py": {"code": 1000 - i, "complexity": 1} for i in range(12)}
        size.update({"tests/test_f.py": {"code": 50, "complexity": 1}})
        s = {"status": "run", "resolved": {"python": 0.95}, "files": {p: {"language": "python", "debt": 0, "imports": [], "definitions": 5,
                                                                         "max_nesting": 1, "max_cognitive": 3} for p in size},
             "functions": [], "unreferenced": [], "unreferenced_count": 0}
        s.update(structure)
        return report(size={"files": size}, revisions=[{"entity": p, "n-revs": 100 - i} for i, p in enumerate(size)], structure=s)

    def by_id(self, r):
        return {f["rule"]["id"]: f for f in findings.evaluate(r)}

    def test_debt_markers_in_top_hotspots(self):
        r = self.base()
        r["structure"]["files"]["src/f0.py"]["debt"] = 4
        r["structure"]["files"]["src/f0.py"]["debt_sample"] = [{"line": 12, "tag": "TODO", "text": "# TODO: split"}]
        r["structure"]["files"]["src/f3.py"]["debt"] = 1
        f = self.by_id(r)["debt_in_hotspots"]
        self.assertEqual((f["severity"], f["title"]), ("info", "Debt the authors flagged in hotspots"))
        self.assertIn("2 of the top 10 hotspots carry TODO, FIXME, XXX or HACK comments: src/f0.py (4); src/f3.py (1).", f["detail"])
        self.assertEqual(f["advice"], "Resolve or ticket the markers in src/f0.py first, starting at line 12; it changes often and its authors said it is unfinished.")
        self.assertEqual(f["rule"]["ref"], "Maldonado and Shihab, MTD 2015")
        r["structure"]["files"]["src/f0.py"]["debt"] = 1
        r["structure"]["files"]["src/f3.py"]["debt"] = 0
        self.assertNotIn("debt_in_hotspots", self.by_id(r), "one marker in one hotspot is ordinary")

    def test_deeply_nested_and_bumpy_functions(self):
        r = self.base(functions=[{"file": "src/f0.py", "name": "parse", "start": 10, "end": 300, "nesting": 6, "cognitive": 80, "complex_conditions": 2, "bumps": 3},
                                 {"file": "src/f9.py", "name": "tidy", "start": 1, "end": 40, "nesting": 3, "cognitive": 12, "complex_conditions": 0, "bumps": 3},
                                 {"file": "tests/test_f.py", "name": "test_x", "start": 1, "end": 40, "nesting": 7, "cognitive": 90, "complex_conditions": 0, "bumps": 4}])
        f = self.by_id(r)["deep_nesting"]
        self.assertEqual(f["severity"], "warning", "the worst sits in a top hotspot")
        self.assertIn("parse (src/f0.py:10) nested 6 deep, cognitive complexity 80, 3 bumps", f["detail"])
        self.assertIn("tidy (src/f9.py:1)", f["detail"], "three separate bumps are a bumpy road whatever the depth")
        self.assertNotIn("test_x", f["detail"])
        self.assertTrue(f["advice"].startswith("Flatten parse in src/f0.py first"), f["advice"])
        self.assertEqual(f["rule"]["min_nesting"], 5)

    def test_hidden_coupling_is_a_pair_that_changes_together_with_no_import_between(self):
        r = self.base()
        r["coupling"] = [{"entity": "src/f0.py", "coupled": "src/f1.py", "degree": 80, "average-revs": 20},
                         {"entity": "src/f2.py", "coupled": "src/f3.py", "degree": 75, "average-revs": 20},
                         {"entity": "src/f4.py", "coupled": "tests/test_f.py", "degree": 90, "average-revs": 20}]
        r["structure"]["files"]["src/f2.py"]["imports"] = ["src/f3.py"]
        f = self.by_id(r)["hidden_coupling"]
        self.assertIn("src/f0.py and src/f1.py change together 80% of the time, and neither imports the other", f["detail"])
        self.assertNotIn("src/f2.py", f["detail"], "an import explains that pair")
        self.assertEqual(f["rule"]["ref"], "Ajienka and Capiluppi, JSS 2017")
        r["structure"]["resolved"] = {"python": 0.3}
        self.assertNotIn("hidden_coupling", self.by_id(r), "a graph that resolves a third of the imports cannot say what is hidden")

    def test_hidden_coupling_leaves_out_a_pair_of_examples(self):
        """Two examples with no import between them are a family, not a dependency nobody named: all
        seven of curl's hidden pairs were docs/examples programs."""
        r = self.base()
        for p in ("examples/a.py", "examples/b.py"):
            r["size"]["files"][p] = {"code": 100, "complexity": 1}
            r["structure"]["files"][p] = {"language": "python", "debt": 0, "imports": [], "definitions": 5,
                                         "max_nesting": 1, "max_cognitive": 3}
        r["coupling"] = [{"entity": "examples/a.py", "coupled": "examples/b.py", "degree": 90, "average-revs": 20},
                         {"entity": "src/f0.py", "coupled": "src/f1.py", "degree": 80, "average-revs": 20}]
        f = self.by_id(r)["hidden_coupling"]
        self.assertIn("src/f0.py and src/f1.py", f["detail"])
        self.assertNotIn("examples/", f["detail"])
        r["coupling"] = r["coupling"][:1]
        self.assertNotIn("hidden_coupling", self.by_id(r), "nothing left to say once the family is out")

    def test_one_more_hidden_pair_is_one_pair(self):
        """gitmole's own report read "(1 more pairs like them)"."""
        r = self.base()
        r["coupling"] = [{"entity": f"src/f{i}.py", "coupled": f"src/f{i + 6}.py", "degree": 90 - i, "average-revs": 20}
                         for i in range(4)]
        self.assertIn("(1 more pair like them)", self.by_id(r)["hidden_coupling"]["detail"])
        r["coupling"].append({"entity": "src/f4.py", "coupled": "src/f10.py", "degree": 85, "average-revs": 20})
        self.assertIn("(2 more pairs like them)", self.by_id(r)["hidden_coupling"]["detail"])

    def test_possibly_unreferenced_files(self):
        r = self.base(unreferenced=["src/f11.py"], unreferenced_count=1)
        f = self.by_id(r)["unreferenced_files"]
        self.assertEqual((f["severity"], f["title"]), ("info", "Possibly unreferenced files"))
        self.assertIn("src/f11.py", f["detail"])
        self.assertIn("dynamic imports, plugins loaded by name and framework routing do not show", f["advice"])

    def test_nothing_without_the_step(self):
        r = self.base()
        r["structure"] = {"status": "not-installed"}
        self.assertFalse({"debt_in_hotspots", "deep_nesting", "hidden_coupling", "unreferenced_files"} & set(self.by_id(r)))


class AgentSurface(unittest.TestCase):
    def rep(self, agents=None, trailers=None):
        return report(provenance={"agents": agents or {}, "trailers": trailers or {"never_author": [], "signoff_by_co_author": []}},
                      meta={"name": "r", "commits": 1000, "identities": [], "last_date": "2026-09-01"})

    def by_id(self, r):
        return {f["rule"]["id"]: f for f in findings.evaluate(r)}

    def test_approval_prompts_turned_off_and_personal_settings_tracked_are_warnings(self):
        found = self.by_id(self.rep(agents={"approval_disabled": [{"file": ".claude/settings.json", "setting": "permissions.defaultMode=bypassPermissions"}],
                                            "local_settings": [".claude/settings.local.json"]}))
        f = found["agent_approval_disabled"]
        self.assertEqual(f["severity"], "warning")
        self.assertIn(".claude/settings.json sets permissions.defaultMode=bypassPermissions", f["detail"])
        self.assertEqual(found["agent_local_settings"]["severity"], "warning")
        self.assertIn(".claude/settings.local.json is tracked", found["agent_local_settings"]["detail"])

    def test_literal_values_in_an_mcp_declaration_name_the_key_never_the_value(self):
        f = self.by_id(self.rep(agents={"mcp": [{"file": ".mcp.json", "servers": 2, "literal_env": [{"server": "db", "key": "DB_URL"}]}]}))["mcp_literal_env"]
        self.assertEqual(f["severity"], "warning")
        self.assertIn("db sets DB_URL in .mcp.json to a literal value", f["detail"])
        self.assertIn("${DB_URL}", f["advice"])

    def test_stale_instructions(self):
        found = self.by_id(self.rep(agents={"instructions": [{"file": "AGENTS.md", "last": "2025-01-01", "commits_behind": 640},
                                                             {"file": "CLAUDE.md", "last": "2026-08-20", "commits_behind": 12}]}))
        f = found["agent_instructions_drift"]
        self.assertEqual(f["severity"], "info")
        self.assertIn("AGENTS.md last changed on 2025-01-01, 20 months and 640 commits before the last commit", f["detail"])
        self.assertNotIn("CLAUDE.md", f["detail"])

    def test_a_sign_off_by_an_identity_that_only_co_authors(self):
        f = self.by_id(self.rep(trailers={"never_author": [], "signoff_by_co_author": [{"name": "Ghost", "email": "ghost@x.com", "commits": 3}]}))["signoff_by_co_author"]
        self.assertEqual(f["severity"], "info")
        self.assertIn("Ghost <ghost@x.com> signs off 3 commits but never authors one", f["detail"])
        self.assertEqual(self.by_id(self.rep()).get("signoff_by_co_author"), None)
        one = self.rep(trailers={"never_author": [], "signoff_by_co_author": [{"name": "Ghost", "email": "ghost@x.com", "commits": 1}]})
        self.assertIsNone(self.by_id(one).get("signoff_by_co_author"), "one commit is not a habit")


class References(unittest.TestCase):
    def test_every_rule_resting_on_a_paper_names_it_where_the_numbers_are(self):
        expected = {"minor_contributors": "Bird et al., FSE 2011", "tangled_commits": "Herzig and Zeller, MSR 2013",
                    "brain_methods": "Lanza and Marinescu, 2006", "tight_coupling": "Gall, Hajek and Jazayeri, ICSM 1998",
                    "trojan_source": "Boucher and Anderson, USENIX Security 2023",
                    "debt_in_hotspots": "Maldonado and Shihab, MTD 2015", "hidden_coupling": "Ajienka and Capiluppi, JSS 2017",
                    "unreferenced_files": "Romano et al., TSE 2020", "sweeping_commits": "Kolassa, Riehle and Salim, SOFSEM 2013"}
        for rule, ref in expected.items():
            self.assertEqual(findings.REFS[rule], ref, rule)
        import os
        with open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "docs", "references.md")) as fh:
            page = fh.read()
        for ref in expected.values():
            surname = ref.split(",")[0].split(" and ")[0].split(" et al.")[0]
            self.assertIn(surname, page, f"{ref} is on the references page")

    def test_the_ref_reaches_the_rule_dict(self):
        found = findings.tight_coupling(report(coupling=[{"entity": "a.py", "coupled": "b.py", "degree": 90, "average-revs": 10}]))
        self.assertEqual(found[0]["rule"]["ref"], "Gall, Hajek and Jazayeri, ICSM 1998")


class TruckFactor(unittest.TestCase):
    def rep(self, doa, **over):
        files = sorted({r["entity"] for r in doa})
        base = dict(size={"files": {f: {"code": 10, "complexity": 1} for f in files}}, doa=doa,
                    revisions=[{"entity": f, "n-revs": 3} for f in files],
                    meta={"name": "r", "commits": 100, "identities": [], "last_date": "2026-09-01", "gone_months": 12},
                    activity={"authors_all": {"Ann": {"last": "2026-08-01"}, "Bob": {"last": "2026-08-01"}, "Cat": {"last": "2024-01-01"}}},
                    age=[{"entity": f, "age-months": 1} for f in files])
        base.update(over)
        return report(**base)

    def row(self, f, who, author=1, decayed=None):
        return {"entity": f, "author": who, "fa": 0, "dl": 1, "ac": 0, "doa": 4.0, "doa_decayed": 4.0, "is_author": author,
                "is_author_decayed": author if decayed is None else decayed}

    def test_one_person_whose_departure_orphans_most_files(self):
        doa = [self.row(f"core/a{i}.py", "Ann") for i in range(20)] + [self.row(f"web/b{i}.py", "Bob") for i in range(8)]
        doa += [self.row("core/a0.py", "Bob", author=0)]
        found = {f["rule"]["id"]: f for f in findings.evaluate(self.rep(doa))}
        f = found["truck_factor"]
        self.assertEqual(f["severity"], "warning")
        self.assertIn("Truck factor 1: without Ann, 20 of the 28 source files (71%) have no author left", f["detail"])
        self.assertIn("core/ (Ann)", f["detail"], "an area whose own truck factor is one")
        self.assertEqual(f["rule"]["ref"], "Avelino et al., ICPC 2016")
        self.assertEqual(f["evidence"]["truck_factor"], 1)
        self.assertEqual(f["evidence"]["areas"], [{"area": "core/", "author": "Ann", "files": 20, "orphaned": 20}],
                         "an area row says how big the area is and what one departure orphans; web/ has under ten files and is not judged")

    def test_a_shared_codebase_has_none(self):
        doa = [self.row(f"core/a{i}.py", who) for i in range(30) for who in ("Ann", "Bob", "Cat")]
        self.assertNotIn("truck_factor", {f["rule"]["id"] for f in findings.evaluate(self.rep(doa))})

    def test_a_pool_most_of_which_has_no_author_has_no_truck_factor(self):
        # Issue #129: files an import brought in have no creator, and a lightly changed one has no author by
        # DOA. When more than half the pool is like that nobody has to leave, so there is no one to name.
        doa = [self.row(f"core/a{i}.py", "Ann", author=0) for i in range(20)] + [self.row(f"web/b{i}.py", "Bob") for i in range(8)]
        found = {f["rule"]["id"]: f for f in findings.evaluate(self.rep(doa))}
        self.assertNotIn("truck_factor", found)

    def test_decay_leaving_most_files_authorless_is_said_without_an_empty_name(self):
        doa = [self.row(f"core/a{i}.py", "Ann", decayed=0) for i in range(20)] + [self.row(f"web/b{i}.py", "Bob") for i in range(8)]
        f = {x["rule"]["id"]: x for x in findings.evaluate(self.rep(doa))}["truck_factor"]
        self.assertIn("Truck factor 1: without Ann", f["detail"])
        self.assertNotIn("()", f["detail"])
        self.assertIn("With knowledge halving every five months, more than half the files already have no author", f["detail"])
        self.assertEqual(f["evidence"]["truck_factor_decayed"], 0)

    def test_files_whose_authors_all_left_while_others_still_edit_them(self):
        doa = [self.row(f"core/a{i}.py", "Cat") for i in range(6)] + [self.row(f"core/a{i}.py", "Bob", author=0) for i in range(6)]
        doa += [self.row(f"web/b{i}.py", who) for i in range(20) for who in ("Ann", "Bob")]
        f = {x["rule"]["id"]: x for x in findings.evaluate(self.rep(doa))}["authors_gone"]
        self.assertEqual(f["severity"], "info")
        self.assertIn("6 source files changed in the last year have no author still committing", f["detail"])
        self.assertIn("core/a0.py (Cat)", f["detail"])


class ComponentCoupling(unittest.TestCase):
    def test_pairs_of_components_that_change_together(self):
        files = {f"{d}/f{i}.py": {"code": 10, "complexity": 1} for d in ("auth", "billing", "tests", "web") for i in range(5)}
        r = report(size={"files": files},
                   components=[{"depth": 1, "entity": "auth/", "coupled": "billing/", "degree": 45, "shared": 30, "average-revs": 66},
                               {"depth": 1, "entity": "auth/", "coupled": "tests/", "degree": 80, "shared": 50, "average-revs": 60},
                               {"depth": 1, "entity": "billing/", "coupled": "web/", "degree": 22, "shared": 12, "average-revs": 50},
                               {"depth": 2, "entity": "auth/x/", "coupled": "billing/y/", "degree": 90, "shared": 20, "average-revs": 22}])
        f = {x["rule"]["id"]: x for x in findings.evaluate(r)}["component_coupling"]
        self.assertIn("auth/ and billing/ change together in 45% of their changes (30 shared)", f["detail"])
        self.assertNotIn("tests/", f["detail"], "a component of tests changes with what it tests")
        self.assertNotIn("web/", f["detail"], "under the 30% floor")
        self.assertNotIn("auth/x/", f["detail"], "the depth is the one the tree's layout asks for")


class ImportCommits(unittest.TestCase):
    def test_the_import_is_named_with_its_share(self):
        act = {"imports": [{"hash": "79d8f164f8", "date": "2019-03-26", "author": "Dan", "files": 12449, "added": 2800751, "deleted": 16,
                            "subject": "Candidate release of source code."}], "added_total": 6648513}
        f = findings.import_commits(report(activity=act))
        self.assertEqual(f[0]["rule"]["id"], "import_commits")
        self.assertIn("79d8f164f8 by Dan (12,449 files, 2,800,751 lines, 42% of every line the history adds", f[0]["detail"])
        self.assertEqual(findings.import_commits(report(activity={})), [])


class SecretsByConfidence(unittest.TestCase):
    def _row(self, value, rule, file, confidence):
        return {"rule": rule, "file": file, "commit": "abc1234", "line": 3, "fingerprint": value, "value": value, "placeholder": False, "confidence": confidence}

    def test_a_generic_hit_graded_low_everywhere_is_a_possible_secret(self):
        rows = [self._row("v1", "generic-api-key", "scripts/genproto.sh", "low"), self._row("v2", "generic-password", "app/db.py", "low"),
                self._row("v2", "generic-password", "app/db2.py", "medium"), self._row("v3", "aws-access-token", "app/aws.py", "low")]
        f = {x["rule"]["id"]: x for x in findings.secrets_found(report(secrets=rows))}
        self.assertEqual(f["secrets_possible"]["severity"], "info", "five of six labelled false: a note, not a warning")
        self.assertIn("1 possible secret(s)", f["secrets_possible"]["title"])
        self.assertIn("2 secret(s)", f["secrets_in_source"]["title"], "one medium sighting keeps a value critical; a provider's rule stays critical")

    def test_generated_mock_tooling_and_testdata_files_are_aside(self):
        rows = [self._row("g", "generic-password", "api/registry.pb.go", "medium"), self._row("m", "generic-api-key", "discovery/openstack/mock.go", "medium"),
                self._row("h", "private-key", "hack/scripts-dev/certs/server.key.insecure", "high"), self._row("t", "ibm-cloud-user-api-key", "cmd/tsdb/testdata.20k", "high"),
                self._row("f", "private-key", "integration/fixtures-expired/server.key", "high"), self._row("w", "private-key", "Godeps/_workspace/src/x/server.key", "high")]
        r = report(secrets=rows, meta={"name": "r", "commits": 100, "identities": [], "generated": ["api/registry.pb.go"]})
        f = {x["rule"]["id"]: x for x in findings.secrets_found(r)}
        self.assertNotIn("secrets_in_source", f)
        self.assertIn("6 secret(s) only in", f["secrets_aside"]["title"])

    def test_an_unreachable_copy_is_placed_by_the_located_ones(self):
        rows = [self._row("t", "generic-password", "(unreachable blob 742c1cc5ebfb)", "medium"), self._row("t", "generic-password", "tests/mail/tests.py", "medium"),
                self._row("u", "facebook-access-token", "(unreachable blob 00db21063ea1)", "high")]
        f = {x["rule"]["id"]: x for x in findings.secrets_found(report(secrets=rows))}
        self.assertIn("1 secret(s) only in", f["secrets_aside"]["title"], "its other copy is a test file")
        self.assertIn("1 secret(s) in history", f["secrets_in_source"]["title"], "only ever unreachable: nowhere to say it is test data")

import unittest

from gitmole import findings, hygiene, structure


def report(**overrides):
    base = {
        "meta": {"name": "r", "commits": 100, "identities": [
            {"name": "Ann", "email": "ann@x.com", "commits": 60},
            {"name": "Bob", "email": "bob@x.com", "commits": 40},
        ]},
        "revisions": [{"entity": "a", "n-revs": 10}, {"entity": "b", "n-revs": 9}],
        "coupling": [],
        "age": [{"entity": "a", "age-months": 0}],
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

    def test_source_values_are_critical_and_test_only_values_are_no_finding(self):
        r = report(secrets=[self.row("h1", "app/settings.py", "c1", 9), self.row("h1", "app/settings.py", "c2", 9),
                            self.row("h2", "tests/data/a.html", "c3", 5), self.row("h2", "tests/data/a.html", "c3", 5),
                            self.row("h2", "app/tests/data/a.html", "c4", 5, rule="aws-access-token"),
                            self.row("h3", "tests/t.py", "c5", 2)])
        found = {f["severity"]: f for f in findings.secrets_found(r)}
        self.assertEqual(set(found), {"critical"}, "a value only in test files was secrets_aside until 0.39.0: labelled never actionable, retired")
        crit = found["critical"]
        self.assertEqual(crit["title"], "1 secret(s) in history")
        self.assertIn("1 distinct value in 2 places: generic-api-key in app/settings.py (c1, c2)", crit["detail"])
        self.assertIn("Rotate", crit["advice"])
        self.assertIn(".betterleaksignore", crit["advice"])

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

    def test_a_value_only_inside_a_rust_test_module_is_no_finding(self):
        """paperclip's two possible secrets were generic-password hits inside #[cfg(test)] modules of runner-core."""
        inline = dict(self.row("h1", "src/durable/state.rs", "c1", 3471, rule="generic-password"), confidence="low", test_code=True)
        self.assertEqual(findings.secrets_found(report(secrets=[inline])), [])
        outside = self.row("h1", "src/durable/state.rs", "c2", 12, rule="generic-password")
        self.assertEqual([f["rule"]["id"] for f in findings.secrets_found(report(secrets=[inline, outside]))], ["secrets_possible"])

    def test_test_only_secrets_do_not_fail_a_critical_gate(self):
        r = report(secrets=[self.row("h3", "tests/t.py")])
        self.assertEqual(findings.secrets_found(r), [])

    def test_a_value_only_in_an_example_fixture_or_rules_directory_is_no_finding(self):
        r = report(secrets=[self.row("h1", "examples/language/bru.bru", "57d82e9", rule="generic-password"),
                            self.row("h2", "config/generate/rules/slack.go", "04bdee4", rule="slack-bot-token"),
                            self.row("h3", "pkg/testdata/creds.yaml", "c3")])
        self.assertEqual(findings.secrets_found(r), [])
        r = report(secrets=[self.row("h1", "examples/app.py", "c1"), self.row("h1", "app/config.py", "c2")])
        self.assertEqual([x["severity"] for x in findings.secrets_found(r)], ["critical"], "the same value in source is a leak")

    def test_a_value_only_in_vendored_code_is_no_finding(self):
        # oauthlib's RFC test vectors inside requests/packages/: upstream's specimen, not this repository's credential
        r = report(secrets=[self.row("h1", "requests/packages/oauthlib/oauth1/rfc5849/parameters.py", "9576518")])
        self.assertEqual(len(findings.secrets_found(r)), 1, "not vendored: a leak")
        r["meta"]["vendored"] = ["requests/packages/"]
        self.assertEqual(findings.secrets_found(r), [])

    def test_a_value_only_in_documentation_is_no_finding(self):
        r = report(secrets=[self.row("h1", "docs/GA4-API-INTEGRATION.md", "e8c0508")])
        self.assertEqual(findings.secrets_found(r), [])
        r = report(secrets=[self.row("h1", "docs/GA4-API-INTEGRATION.md", "e8c0508"), self.row("h1", "app/config.py", "c2")])
        self.assertEqual([x["severity"] for x in findings.secrets_found(r)], ["critical"], "the same value in source is a leak")

    def test_the_token_the_scanner_graded_high_is_named_first(self):
        """apache/devlake's critical named three generic-password form labels and never the GitHub token
        in a clone URL, which betterleaks graded high: the headline names the strongest values."""
        from gitmole import leaks
        pat = "ghp_" + "Zq8vLm2Rt7Kp" * 3   # built at runtime
        line = f"      url: 'https://{pat}@github.com/o/r.git',"
        self.assertFalse(leaks.is_placeholder(pat, line, "ui/src/data/TestBlueprintDetail.js", "github-pat"))
        rows = [dict(self.row(f"h{n}", f"ui/src/registry/plugins/p{n}.json", rule="generic-password"), confidence="medium") for n in range(5)]
        rows.append(dict(self.row("hp", "ui/src/data/TestBlueprintDetail.js", rule="github-pat"), confidence="high"))
        [crit] = findings.secrets_found(report(secrets=rows))
        self.assertEqual(crit["severity"], "critical")
        self.assertIn("6 distinct values in 6 places: github-pat in ui/src/data/TestBlueprintDetail.js (c1);", crit["detail"])

    def test_placeholder_shapes_are_not_a_finding(self):
        r = report(secrets=[self.row("h4", "web/package.json", placeholder=True)])
        self.assertEqual(findings.secrets_found(r), [])

    def test_examples_name_at_most_three_values_past_five(self):
        r = report(secrets=[self.row(f"h{i}", f"app/f{i}.py", f"c{i}") for i in range(6)])
        crit = findings.secrets_found(r)[0]
        self.assertIn("and 3 more", crit["detail"])
        self.assertEqual(crit["title"], "6 secret(s) in history")

    def test_up_to_five_values_every_one_is_named(self):
        """hindsight's hosted-database password was the fifth value and read as "and 5 more"."""
        r = report(secrets=[self.row(f"h{i}", f"app/f{i}.py", f"c{i}") for i in range(5)])
        crit = findings.secrets_found(r)[0]
        self.assertNotIn("more", crit["detail"])
        self.assertIn("generic-api-key in app/f4.py (c4).", crit["detail"])

    def test_a_value_only_in_template_files_is_no_finding(self):
        r = report(secrets=[self.row("h1", "docker/timescale/.env.example", rule="generic-password"),
                            self.row("h2", "config/settings.yml.sample"), self.row("h3", "deploy/values.template")])
        self.assertEqual(findings.secrets_found(r), [])
        r = report(secrets=[self.row("h1", ".env.example"), self.row("h1", ".env.dev", "c2")])
        self.assertEqual([x["severity"] for x in findings.secrets_found(r)], ["critical"], "the same value in a real file is a leak")

    def test_a_password_to_a_local_service_is_info_and_the_hosted_one_stays_critical(self):
        rows = [dict(self.row("hl", f"docker/f{i}.yml", f"c{i}", rule="generic-credential-uri"), local=True, confidence="medium") for i in range(4)]
        rows += [dict(self.row("hr", ".env.dev", "c9", rule="generic-credential-uri"), confidence="medium"),
                 dict(self.row("hm", "app/db.py", "c8", rule="generic-credential-uri"), confidence="medium", local=True),
                 dict(self.row("hm", "app/prod.py", "c8", rule="generic-credential-uri"), confidence="medium", local=False),
                 dict(self.row("hl", "docker/docker-compose.yml", "c1", rule="generic-password"), confidence="medium")]
        f = {x["rule"]["id"]: x for x in findings.secrets_found(report(secrets=rows))}
        self.assertEqual(set(f), {"secrets_in_source", "secrets_local"})
        self.assertEqual(f["secrets_local"]["severity"], "info")
        self.assertIn("1 password(s) to a local service", f["secrets_local"]["title"])
        self.assertEqual(f["secrets_local"]["evidence"]["files"], ["docker/docker-compose.yml"] + [f"docker/f{i}.yml" for i in range(4)],
                         "the evidence names the files; the compose file's own setting of the password is the same default")
        self.assertIn("2 secret(s) in history", f["secrets_in_source"]["title"], "a value also sent to another host is not a local default")
        self.assertIn(".env.dev", f["secrets_in_source"]["detail"])


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

    GONE = {"meta": {"name": "r", "commits": 100, "identities": [], "last_date": "2026-09-01", "gone_months": 12},
            "activity": {"authors_all": {"Ann": {"last": "2024-01-01"}, "Bob": {"last": "2026-08-01"}}}}

    def test_someone_who_has_left_is_marked_and_the_advice_names_who_is_still_here(self):
        own = [{"entity": "core/a.py", "author": "Ann", "added": 950, "deleted": 0},
               {"entity": "core/b.py", "author": "Bob", "added": 50, "deleted": 0}]
        [f] = findings.bus_factor(report(theseus_authors={"Ann": 79, "Bob": 21}, ownership=own, **self.GONE))
        self.assertTrue(f["detail"].startswith("Ann (gone) wrote 79% of the code that survives today."), f["detail"])
        self.assertEqual(f["advice"], "Have Bob, its largest author still here, own core/ first.")
        self.assertEqual((f["evidence"]["gone"], f["evidence"]["ask"]), (True, "Bob"))
        [f] = findings.bus_factor(report(theseus_authors={"Ann": 79, "Bob": 21}, ownership=own[:1], **self.GONE))
        self.assertEqual(f["advice"], "Nobody still here has written any of core/; give it an owner.")
        [f] = findings.bus_factor(report(theseus_authors={"Ann": 79, "Bob": 21}, **self.GONE))
        self.assertNotIn("Ann", f["advice"])
        self.assertIn("Have Bob, who holds the most surviving code among the people still here", f["advice"])

    def test_people_still_here_who_hold_equally_much_are_counted_and_none_is_named(self):
        own = [{"entity": "core/a.py", "author": "Ann", "added": 900, "deleted": 0},
               {"entity": "core/b.py", "author": "Bob", "added": 50, "deleted": 0},
               {"entity": "core/c.py", "author": "Cat", "added": 50, "deleted": 0}]
        [f] = findings.bus_factor(report(theseus_authors={"Ann": 79, "Bob": 21}, ownership=own, **self.GONE))
        self.assertEqual(f["advice"], "Give core/ an owner; the 2 people still here who wrote the most of it wrote equally much.",
                         "Bob before Cat is the alphabet's order")
        self.assertIsNone(f["evidence"]["ask"])
        [f] = findings.bus_factor(report(theseus_authors={"Ann": 80, "Bob": 10, "Cat": 10}, **self.GONE))
        self.assertEqual(f["advice"], "Give what they wrote owners; the 2 people still here who hold the most surviving code hold equally much.")


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
        self.assertTrue(f[0]["detail"].endswith("Review core/parser.py and core/util.py before the next release."), f[0]["detail"])

    def test_info_below_five_recent_fixes(self):
        f = findings.bug_magnets(report(fixes=self.FIXES[1:2]))
        self.assertEqual(f[0]["severity"], "info")
        self.assertTrue(f[0]["detail"].endswith("Review core/util.py before the next release."), f[0]["detail"])

    def test_a_file_whose_recent_fixes_all_fixed_a_file_above_it_is_listed_with_that_file(self):
        fixes = [{"entity": f"plug/tasks/{n}.go", "n-fixes": k, "last-fix": "2026-09-01", "recent-fixes": k}
                 for n, k in (("user", 5), ("org", 4), ("ent", 4), ("helper", 4))] + [self.FIXES[0]]
        history = {"plug/tasks/user.go": {"first": "2026-02-26", "recent": ["h5", "h4", "h3", "h2", "h1"]},
                   "plug/tasks/org.go": {"first": "2026-02-26", "recent": ["h4", "h3", "h2", "h1"]},
                   "plug/tasks/ent.go": {"first": "2026-02-26", "recent": ["h4", "h3", "h2", "h1"]},
                   "plug/tasks/helper.go": {"first": "2026-02-26", "recent": ["h9", "h3", "h2", "h1"]},   # h9 is its own: it stands alone
                   "core/parser.py": {"first": "2020-01-01", "recent": ["p1", "h1", "h2", "p4", "p5"]}}
        r = report(fixes=fixes, fix_history=history)
        r["meta"]["now"] = "2026-09-17"
        f = findings.bug_magnets(r)[0]
        self.assertIn("5 file(s) were fixed 3+ times in six months: core/parser.py (5 recent, 9 total); "
                      "plug/tasks/user.go (5 recent, 5 total) and 2 files beside it fixed in the same commits; "
                      "plug/tasks/helper.go (4 recent, 4 total).", f["detail"], "created seven months before now: not new in the window")
        self.assertIn("Review core/parser.py and plug/tasks/user.go before the next release", f["advice"])
        self.assertEqual(f["evidence"]["shared_fixes"], [{"file": "plug/tasks/user.go", "with": ["plug/tasks/ent.go", "plug/tasks/org.go"],
                                                         "fixes": ["h5", "h4", "h3", "h2", "h1"]}])
        self.assertEqual([x["file"] for x in f["evidence"]["files"]], ["core/parser.py", "plug/tasks/user.go", "plug/tasks/ent.go",
                                                                      "plug/tasks/helper.go", "plug/tasks/org.go"], "the files it names are unchanged")

    def test_a_file_elsewhere_is_not_beside_it(self):
        fixes = [{"entity": "a/x.py", "n-fixes": 4, "last-fix": "2026-09-01", "recent-fixes": 4},
                 {"entity": "b/y.py", "n-fixes": 3, "last-fix": "2026-09-01", "recent-fixes": 3}]
        r = report(fixes=fixes, fix_history={"a/x.py": {"first": "2020-01-01", "recent": ["1", "2", "3", "4"]},
                                             "b/y.py": {"first": "2020-01-01", "recent": ["1", "2", "3"]}})
        self.assertIn("a/x.py (4 recent, 4 total) and 1 file fixed in the same commits.", findings.bug_magnets(r)[0]["detail"])

    def test_a_file_younger_than_the_window_says_so(self):
        r = report(fixes=[{**self.FIXES[0], "n-fixes": 5}, self.FIXES[1]], fix_history={"core/parser.py": {"first": "2026-05-01", "recent": ["a", "b", "c", "d", "e"]},
                                                       "core/util.py": {"first": "2026-01-01", "recent": ["f", "g", "h"]}})
        r["meta"].update({"now": "2026-09-17", "first_date": "2020-01-01"})
        f = findings.bug_magnets(r)[0]
        self.assertIn("core/parser.py (5 recent, new in the window); core/util.py (3 recent, 4 total).", f["detail"])
        self.assertEqual(f["evidence"]["new_in_window"], ["core/parser.py"])
        r["fixes"][0]["n-fixes"] = 6   # a count the window does not hold all of: both numbers stay
        self.assertIn("core/parser.py (5 recent, 6 total, new in the window)", findings.bug_magnets(r)[0]["detail"])
        del r["meta"]["first_date"]
        self.assertNotIn("new in the window", findings.bug_magnets(r)[0]["detail"], "without the history's start, no claim")

    def test_a_history_younger_than_the_window_says_nothing_of_it(self):
        """VoiceStudio's history is five months long: every file is new in the six-month window, so the
        words, printed on each of the five, said nothing, and every total repeated its recent count."""
        r = report(fixes=[{**self.FIXES[0], "n-fixes": 5}, {**self.FIXES[1], "n-fixes": 3}],
                   fix_history={"core/parser.py": {"first": "2026-05-01", "recent": ["a", "b", "c", "d", "e"]},
                                "core/util.py": {"first": "2026-04-10", "recent": ["f", "g", "h"]}})
        r["meta"].update({"now": "2026-09-17", "first_date": "2026-04-10"})
        f = findings.bug_magnets(r)[0]
        self.assertIn("fixed 3+ times in six months: core/parser.py (5 recent); core/util.py (3 recent).", f["detail"])
        self.assertNotIn("new_in_window", f["evidence"])

    def test_without_the_commits_every_file_stands_alone(self):
        f = findings.bug_magnets(report(fixes=self.FIXES))[0]
        self.assertNotIn("shared_fixes", f["evidence"])
        self.assertNotIn("new in the window", f["detail"])

    def test_a_file_no_longer_in_the_tree_is_not_a_magnet(self):
        """VoiceStudio's finding named 296 files, 132 of them in a frontend/ retired the week before."""
        gone = {"entity": "frontend/app.js", "n-fixes": 9, "last-fix": "2026-09-01", "recent-fixes": 9}
        f = findings.bug_magnets(report(fixes=[gone, *self.FIXES], tree=frozenset({"core/parser.py", "core/util.py"})))[0]
        self.assertNotIn("frontend/app.js", f["detail"])
        self.assertEqual([x["file"] for x in f["evidence"]["files"]], ["core/parser.py", "core/util.py"])
        self.assertEqual(f["evidence"]["count"], 2)
        by_scc = report(fixes=[gone, *self.FIXES], size={"files": {"core/parser.py": {"code": 9}, "core/util.py": {"code": 3}}})
        self.assertNotIn("frontend/app.js", findings.bug_magnets(by_scc)[0]["detail"], "an output directory from before tree.txt: scc's list")
        self.assertIn("frontend/app.js", findings.bug_magnets(report(fixes=[gone, *self.FIXES]))[0]["detail"], "nothing to judge by: kept")

    @staticmethod
    def rated(fixes, revs):
        """A report whose change table holds `revs` ({file: changes}) beside 97 quiet files, 2 changes each and
        no fix: the repository fixes about one change in ten."""
        quiet = {f"src/q{i}.py": 2 for i in range(97)}
        return report(fixes=[{"entity": e, "n-fixes": k, "last-fix": "2026-09-01", "recent-fixes": r} for e, k, r in fixes],
                      revisions=[{"entity": e, "n-revs": n} for e, n in {**revs, **quiet}.items()])

    def test_names_first_the_files_fixed_beyond_the_repository_rate(self):
        """VoiceStudio fixes 45% of its changes: most of its magnets were busy files at that rate, and one
        of the five named was fixed less often than the repository's average."""
        r = self.rated([("src/busy.py", 30, 9), ("src/prone.py", 12, 4)], {"src/busy.py": 200, "src/prone.py": 14})
        prone = findings.fix_prone(r, lambda p: True)
        self.assertEqual((prone["fixes"], prone["changes"], prone["files"]), (42, 408, 99))
        self.assertEqual(prone["above"], {"src/prone.py"}, "12 of 14 against 42 of 408; 30 of 200 is about the rate")
        f = findings.bug_magnets(r)[0]
        self.assertIn("2 file(s) were fixed 3+ times in six months, 1 beyond files of their size: "
                      "src/prone.py (4 recent, 12 total); src/busy.py (9 recent, 30 total).", f["detail"])
        self.assertIn("Review src/prone.py and src/busy.py before the next release.", f["advice"])
        self.assertEqual(f["severity"], "warning", "severity stays the window's: busy.py has 9 recent fixes")
        self.assertEqual([x["file"] for x in f["evidence"]["files"]], ["src/busy.py", "src/prone.py"], "the named files keep the window's order")
        self.assertEqual(f["evidence"]["fix_rate"], {"fixes": 42, "changes": 408, "files": 99,
                                                     "above_rate": [{"file": "src/prone.py", "fixes": 12, "changes": 14, "size_rate": 0.103}]},
                         "no sizes: one stratum, the repository's own rate")

    def test_says_so_when_none_is_fixed_beyond_the_rate(self):
        r = self.rated([("src/busy.py", 30, 9), ("src/lib.py", 20, 0)], {"src/busy.py": 300, "src/lib.py": 100})
        f = findings.bug_magnets(r)[0]   # 30 of 300 against 50 of 494
        self.assertIn("1 file(s) were fixed 3+ times in six months, none beyond files of their size: src/busy.py", f["detail"])
        self.assertEqual(f["evidence"]["fix_rate"]["above_rate"], [])

    def test_a_large_file_is_tested_against_files_of_its_size(self):
        """hindsight at 0.40.0: all 13 files the whole-repository rate named were in the top tenth by lines of code.
        Ten big files fixed at 30% beside 90 small ones at 5%: against the pooled rate every big one stands out,
        against the big ones' own rate none does, and a big file fixed far more often than its peers still does."""
        big = {f"src/big{i}.py": 40 for i in range(9)}
        small = {f"src/s{i}.py": 20 for i in range(90)}
        fixes = [(e, 12, 4) for e in big] + [(e, 1, 0) for e in small] + [("src/worst.py", 30, 6)]
        r = report(fixes=[{"entity": e, "n-fixes": k, "last-fix": "2026-09-01", "recent-fixes": x} for e, k, x in fixes],
                   revisions=[{"entity": e, "n-revs": n} for e, n in {**big, **small, "src/worst.py": 40}.items()],
                   size={"files": {**{e: {"code": 2000} for e in big}, **{e: {"code": 50} for e in small}, "src/worst.py": {"code": 2000}}})
        prone = findings.fix_prone(r, lambda p: True)
        self.assertEqual(prone["above"], {"src/worst.py"})
        self.assertAlmostEqual(prone["rate"]["src/big0.py"], (9 * 12 + 30) / 400)
        f = findings.bug_magnets(r)[0]
        self.assertIn("10 file(s) were fixed 3+ times in six months, 1 beyond files of their size: src/worst.py", f["detail"])

    def test_no_rate_test_on_a_history_barely_longer_than_the_window(self):
        """hindsight: eleven months of history, the six-month window most of it."""
        r = self.rated([("src/busy.py", 30, 9), ("src/prone.py", 12, 4)], {"src/busy.py": 200, "src/prone.py": 14})
        r["meta"] = dict(r["meta"], first_date="2025-10-30", last_date="2026-09-30")
        self.assertIsNone(findings.fix_prone(r, lambda p: True))
        f = findings.bug_magnets(r)[0]
        self.assertIn("2 file(s) were fixed 3+ times in six months: src/busy.py", f["detail"])
        # paperclip review (D6): the test that did not run was advertised and never mentioned, and 391 raw counts were a warning
        self.assertIn("Raw counts: the test against files of their size needs 12 months of history, this has 11.", f["detail"])
        self.assertEqual(f["evidence"]["fix_rate"], {"not_run": "history too short", "history_months": 11})
        self.assertEqual(f["severity"], "info", "nine recent fixes, but raw counts on a short history are a note")
        r["meta"]["first_date"] = "2025-09-30"
        self.assertIsNotNone(findings.fix_prone(r, lambda p: True), "twelve months: tested")
        f = findings.bug_magnets(r)[0]
        self.assertEqual(f["severity"], "warning")
        self.assertNotIn("Raw counts", f["detail"])
        del r["meta"]["first_date"]
        self.assertEqual(findings.bug_magnets(r)[0]["severity"], "warning", "no dates to judge by: the window's counts decide, as before")

    def test_the_rate_is_over_the_files_the_rule_reads(self):
        """Tests change with every fix and are left out of the magnets, so they are left out of the rate too."""
        r = self.rated([("src/prone.py", 12, 4), ("tests/test_prone.py", 12, 4)], {"src/prone.py": 14, "tests/test_prone.py": 14})
        f = findings.bug_magnets(r)[0]
        self.assertEqual((f["evidence"]["fix_rate"]["fixes"], f["evidence"]["fix_rate"]["changes"]), (12, 208))

    def test_the_binomial_tail_and_the_step_up(self):
        from math import comb
        for k, n, p in ((0, 5, 0.3), (3, 10, 0.2), (12, 14, 0.1), (30, 200, 0.103), (7, 7, 0.5), (8, 7, 0.5)):
            exact = sum(comb(n, i) * p ** i * (1 - p) ** (n - i) for i in range(k, n + 1))
            self.assertAlmostEqual(findings._binomial_tail(k, n, p), exact, places=12, msg=(k, n, p))
        self.assertLess(findings._binomial_tail(105, 132, 0.451), 1e-9)
        # Benjamini and Hochberg's step-up: the largest i with p(i) <= q i / m, and every smaller p with it
        self.assertEqual(findings._benjamini_hochberg({"a": 0.01, "b": 0.02, "c": 0.04, "d": 0.5}, 0.05), {"a", "b"})
        self.assertEqual(findings._benjamini_hochberg({"a": 0.02, "b": 0.025, "c": 0.9}, 0.05), {"a", "b"}, "0.02 > 0.05/3 alone, but b carries it")
        self.assertEqual(findings._benjamini_hochberg({"a": 0.2}, 0.05), set())

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

    def test_a_function_in_a_cargo_test_double_is_not_a_brain_method(self):
        fns = [{"file": "crates/core/src/bin/fake-server.rs", "function": "run", "ccn": 360, "nloc": 1266, "params": 0, "start": 5, "end": 1300},
               {"file": "crates/core/src/lib.rs", "function": "serve", "ccn": 20, "nloc": 150, "params": 1, "start": 10, "end": 160}]
        r = report(functions=fns)
        r["meta"]["test_doubles"] = ["crates/core/src/bin/fake-server.rs"]
        f = findings.brain_methods(r)[0]
        self.assertEqual([x["function"] for x in f["evidence"]["functions"]], ["serve"])

    def test_a_function_inside_a_rust_test_module_is_not_a_brain_method(self):
        fns = [{"file": "src/lib.rs", "function": "big_case", "ccn": 40, "nloc": 300, "params": 0, "start": 520, "end": 820},
               {"file": "src/lib.rs", "function": "run", "ccn": 20, "nloc": 150, "params": 1, "start": 10, "end": 160}]
        r = report(functions=fns)
        r["meta"]["test_modules"] = {"src/lib.rs": [[500, 900]]}
        f = findings.brain_methods(r)[0]
        self.assertEqual(f["evidence"]["count"], 1)
        self.assertEqual(f["evidence"]["functions"][0]["function"], "run")

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
        self.assertIn("<anonymous> (completions.go:316) complexity 47, 136 lines, 1 param", f[0]["detail"])
        self.assertEqual(f[0]["advice"], "Split the anonymous function at completions.go:316 first, before the next change lands there.")

    def test_a_labelled_nameless_function_is_listed_as_anonymous_and_placed_by_its_line(self):
        # VoiceStudio's 0.39.0 report listed `const rows = (['tts', 'asr', 'llm'] as const).map((family) => {` as a name
        for flag in (True, False):   # the loader's flag, or the name's shape alone (an analysis the flag is missing from)
            fns = [{"file": "server/routes.ts", "function": 'app.post("/api/x", async (req, res) => {', "anonymous": flag,
                    "ccn": 47, "nloc": 136, "params": 1, "start": 316, "end": 585, "suspect": ""}]
            f = findings.brain_methods(report(functions=fns))
            self.assertIn("<anonymous> (server/routes.ts:316) complexity 47, 136 lines, 1 param", f[0]["detail"])
            self.assertNotIn("app.post", f[0]["detail"])
        fns = [{"file": "a.cpp", "function": "Matrix::operator()", "ccn": 47, "nloc": 136, "params": 1, "start": 3, "end": 200, "suspect": ""}]
        self.assertIn("Matrix::operator() (a.cpp) complexity 47", findings.brain_methods(report(functions=fns))[0]["detail"], "an empty () is part of a name")
        fns = [{"file": "server/routes.ts", "function": 'app.post("/api/x", async (req, res) => {', "anonymous": True,
                "ccn": 47, "nloc": 136, "params": 1, "start": 316, "end": 585, "suspect": ""}]
        f = findings.brain_methods(report(functions=fns))
        self.assertEqual(f[0]["advice"], "Split the anonymous function at server/routes.ts:316 first, before the next change lands there.")

    def test_a_suspect_span_is_not_a_brain_method(self):
        fns = [{"file": "core/parser.py", "function": "parse", "ccn": 41, "nloc": 220, "params": 9, "start": 10, "end": 300,
                "suspect": "opens a block at line 120 no deeper than its own start"},
               {"file": "core/util.py", "function": "tidy", "ccn": 16, "nloc": 120, "params": 2, "start": 1, "end": 130, "suspect": ""}]
        f = findings.brain_methods(report(functions=fns))
        self.assertNotIn("parse", f[0]["detail"], "a span lizard may have mis-parsed is not advice")
        self.assertEqual(f[0]["advice"], "Split tidy in core/util.py first, before the next change lands there.")
        self.assertEqual(findings.brain_methods(report(functions=fns[:1])), [])

    def test_a_function_lizard_ended_early_is_a_brain_method_at_its_real_length(self):
        fns = [{"file": "server/heartbeat.ts", "function": "executeRun", "ccn": 55, "nloc": 6394, "params": 2, "start": 20179, "end": 26572,
                "suspect": "", "lizard_span": {"end": 20446, "nloc": 222}}]
        f = findings.brain_methods(report(functions=fns))
        self.assertIn("executeRun (server/heartbeat.ts) complexity at least 55, 6394 lines, 2 params", f[0]["detail"])
        self.assertEqual(f[0]["evidence"]["functions"][0]["lines"], 6394)

    def test_generated_files_are_not_brain_methods(self):
        fns = [{"file": "lib/config-validator.js", "function": "validate10", "ccn": 373, "nloc": 1150, "params": 5, "start": 1, "end": 1150},
               {"file": "lib/reply.js", "function": "onSendEnd", "ccn": 34, "nloc": 180, "params": 2, "start": 1, "end": 180}]
        r = report(functions=fns)
        r["meta"]["generated"] = ["lib/config-validator.js"]
        f = findings.brain_methods(r)
        self.assertEqual(f[0]["advice"], "Split onSendEnd in lib/reply.js first, before the next change lands there.")
        self.assertNotIn("validate10", f[0]["detail"])

    def test_a_numbered_schema_migration_is_not_a_brain_method(self):
        fns = [{"file": "backend/core/models/migrationscripts/20240116_modify_fileds_sort.go", "function": "Up", "ccn": 37, "nloc": 146, "params": 1, "start": 1, "end": 146},
               {"file": "backend/core/runner/run_task.go", "function": "RunPluginSubTasks", "ccn": 33, "nloc": 145, "params": 6, "start": 1, "end": 145}]
        f = findings.brain_methods(report(functions=fns))
        self.assertEqual(f[0]["advice"], "Split RunPluginSubTasks in backend/core/runner/run_task.go first, before the next change lands there.")
        self.assertNotIn("20240116", f[0]["detail"], "a migration is replayed as written; nobody should split it")
        self.assertEqual(findings.brain_methods(report(functions=fns[:1])), [])

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
        [f] = findings.vulnerable_dependencies(report(dependencies=self.deps(rows), tree=frozenset({"Dockerfile", "package-lock.json"})))
        self.assertEqual(f["severity"], "critical")
        self.assertTrue(f["advice"].startswith("Upgrade minimist to 1.2.6 in package-lock.json first; it scores 9.8, and Dockerfile ships that lock."), f["advice"])
        self.assertIn("2 vulnerable packages in 1 lock file", f["detail"])
        self.assertEqual(f["evidence"]["packages"][0]["deploys"], ["Dockerfile"])

    def test_a_critical_score_in_a_lock_nothing_declares_it_ships_is_a_warning(self):
        """hindsight: the headline was chromadb in an integration library's development lock, not the shipped
        service's pyjwt in the root uv.lock."""
        rows = [self.row("chromadb", "1.1.1", "integrations/crewai/uv.lock", score=9.4, fixed=None)]
        [f] = findings.vulnerable_dependencies(report(dependencies=self.deps(rows), tree=frozenset({"integrations/crewai/pyproject.toml"})))
        self.assertEqual(f["severity"], "warning")
        self.assertIn("A critical score in integrations/crewai/uv.lock is a warning here, as nothing in its directory declares a deployment", f["detail"])
        self.assertEqual(f["evidence"]["packages"][0]["deploys"], [])

    def test_what_ships_is_read_from_the_tree_the_workspace_and_the_compose_builds(self):
        base = self.row("pyjwt", "2.13.0", "uv.lock", score=9.1, fixed="2.14.0")
        cases = [({"path": "uv.lock", "packages": 1, "members": ["api"]}, frozenset({"api/Dockerfile.prod"}), (), ["api/Dockerfile.prod"]),
                 ({"path": "uv.lock", "packages": 1, "entry_points": ["api/pyproject.toml [project.scripts]"]}, frozenset(), (), ["api/pyproject.toml [project.scripts]"]),
                 ({"path": "svc/uv.lock", "packages": 1}, frozenset(), ["svc"], ["a compose service built from svc"]),
                 ({"path": "svc/uv.lock", "packages": 1}, frozenset({"helm/Chart.yaml", "svc/sub/Dockerfile"}), (), [])]
        for source, tree, builds, want in cases:
            row = {**base, "source": source["path"]}
            deps = {**self.deps([row]), "sources": [source], "compose_builds": list(builds)}
            [f] = findings.vulnerable_dependencies(report(dependencies=deps, tree=tree))
            self.assertEqual(f["evidence"]["packages"][0]["deploys"], want, source)
            self.assertEqual(f["severity"], "critical" if want else "warning", source)

    def test_within_a_grade_a_fixable_package_leads_a_fixless_one(self):
        rows = [self.row("chromadb", "1.1.1", "uv.lock", score=9.4, fixed=None), self.row("pyjwt", "2.13.0", "uv.lock", score=9.1, fixed="2.14.0"),
                self.row("click", "8.1.8", "uv.lock", score=7.2, fixed="8.3.3")]
        [f] = findings.vulnerable_dependencies(report(dependencies=self.deps(rows), tree=frozenset({"Dockerfile"})))
        self.assertEqual([p["name"] for p in f["evidence"]["packages"]], ["pyjwt", "chromadb", "click"])
        self.assertTrue(f["advice"].startswith("Upgrade pyjwt to 2.14.0 in uv.lock first"), f["advice"])

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

    def test_a_requirement_range_is_said_as_a_range_and_kept_out_of_the_installed_rows(self):
        """hindsight: `mcp>=1.0.0` was reported as "mcp 1.0.0" in a "lock file"; the floor is what osv-scanner
        read, and no install picks it on purpose."""
        floor = {**self.row("mcp", "1.0.0", "tools/requirements.txt", score=9.1, fixed="1.9.4"), "requirement": ">=1.0.0", "pinned": False}
        pin = {**self.row("requests", "2.31.0", "tools/requirements.txt", score=5.6, fixed="2.32.0"), "requirement": "==2.31.0", "pinned": True}
        [f] = findings.vulnerable_dependencies(report(dependencies=self.deps([floor, pin])))   # one group, wherever requirement files are filed
        self.assertNotEqual(f["severity"], "critical", "a vulnerable floor is not an installed critical")
        self.assertIn("1 vulnerable package in 1 requirement file: requests 2.31.0 (CVE-2024-1, 5.6, fixed in 2.32.0) in tools/requirements.txt.", f["detail"])
        self.assertIn("1 requirement range admits a vulnerable version: mcp>=1.0.0 in tools/requirements.txt, whose floor 1.0.0 is vulnerable (CVE-2024-1, 9.1, fixed in 1.9.4).", f["detail"])
        self.assertEqual([p["name"] for p in f["evidence"]["packages"]], ["requests"])
        self.assertEqual(f["evidence"]["lock_files"], 0, "a requirement file is not a lock file")
        self.assertEqual(f["evidence"]["requirements"][0]["floor"], "1.0.0")
        self.assertEqual(f["evidence"]["requirements"][0]["requirement"], ">=1.0.0")
        self.assertNotIn("version", f["evidence"]["requirements"][0])
        self.assertTrue(f["advice"].startswith("Upgrade requests to 2.32.0 in tools/requirements.txt first"), f["advice"])

    def test_only_ranges_advise_raising_the_floor(self):
        old = self.row("mcp", "1.0.0", "requirements.txt", score=8.7, fixed="1.9.4")   # a scan from before the specifier was kept
        [f] = findings.vulnerable_dependencies(report(dependencies=self.deps([old])))
        self.assertIn("mcp 1.0.0 in requirements.txt, a requirement file that may name only the lowest version it admits", f["detail"])
        self.assertTrue(f["advice"].startswith("Raise the floor of mcp to 1.9.4 in requirements.txt first; its floor scores 8.7."), f["advice"])
        self.assertEqual(f["evidence"]["packages"], [])

    def test_a_package_in_many_lock_files_is_counted_once_and_its_places_apart(self):
        """hindsight said "34 vulnerable packages": 34 rows of package and lock file, about 20 packages."""
        rows = [self.row("pyjwt", "2.13.0", f"{d}/uv.lock", score=7.1) for d in ("a", "b", "c")] + [self.row("click", "8.1.8", "a/uv.lock", score=7.0)]
        [f] = findings.vulnerable_dependencies(report(dependencies=self.deps(rows)))
        self.assertIn("2 vulnerable packages in 4 places across 3 lock files: pyjwt 2.13.0 (CVE-2024-1, 7.1, fixed in 9.9.9) in a/uv.lock and 2 more files; click 8.1.8", f["detail"])
        self.assertEqual((f["evidence"]["names"], f["evidence"]["places"], f["evidence"]["lock_files"]), (2, 4, 3))
        self.assertEqual(len(f["evidence"]["packages"]), 4, "the evidence keeps a row per place")

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

    def test_an_island_whose_author_has_left_is_marked_and_handed_to_someone_still_here(self):
        r = report(ownership=self.OWN, meta={"name": "r", "commits": 100, "identities": [], "last_date": "2026-09-01", "gone_months": 12},
                   activity={"authors_all": {"Ann": {"last": "2024-01-01"}, "Bob": {"last": "2026-08-01"}}})
        [f] = findings.knowledge_islands(r)
        self.assertIn("core/ (Ann (gone) 95%)", f["detail"])
        self.assertEqual(f["advice"], "Have Bob, its largest author still here, own core/ first; it is the largest at 1,000 lines.")
        r["ownership"] = self.OWN + [{"entity": "core/c.py", "author": "Cat", "added": 50, "deleted": 0}]
        [f] = findings.knowledge_islands(r)
        self.assertEqual(f["advice"], "Give core/ an owner first; it is the largest at 1,050 lines and the 2 people still here who wrote the most of it "
                                      "wrote equally much.", "Bob and Cat wrote 50 lines each: neither is its largest author still here")

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

    def test_generated_files_are_not_islands(self):
        # hindsight's OpenAPI client: the person who last ran the generator "owns" thousands of lines they did not write
        own = [{"entity": "clients/python/api/a_api.py", "author": "Ann", "added": 500000, "deleted": 0},
               {"entity": "core/a.py", "author": "Bob", "added": 300, "deleted": 0}]
        r = report(ownership=own)
        r["meta"]["generated"] = ["clients/python/api/a_api.py"]
        f = findings.knowledge_islands(r)
        self.assertEqual(f[0]["advice"], "Pair someone with Bob on core/ first; it is the largest at 300 lines.")
        self.assertNotIn("clients/", f[0]["detail"])
        self.assertEqual(findings.bus_factor(r), findings.bus_factor(report(ownership=own[1:])), "the bus factor reads the same rows")

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

    def test_less_than_a_year_of_samples_claims_no_growth_in_a_year(self):
        r = self._report([3, 3, 3, 0, 0])
        r["trend"]["files"] = {p: [["2026-06-10", s[0][1], 100], s[1]] for p, s in r["trend"]["files"].items()}
        self.assertEqual(findings.complexity_growth(r), [], "three months is not a year")


class Advice(unittest.TestCase):
    def test_every_finding_carries_its_next_step_as_a_field_that_ends_the_detail(self):
        r = report(secrets=[{"rule": "aws", "file": "a.env", "commit": "abc1234"}],
                   theseus_authors={"Ann": 79, "Bob": 21},
                   revisions=[{"entity": "a.py", "n-revs": 128}, {"entity": "b.py", "n-revs": 51}],
                   fixes=[{"entity": "a.py", "n-fixes": 9, "last-fix": "2026-09-01", "recent-fixes": 5}],
                   functions=[{"file": "a.py", "function": "go", "ccn": 20, "nloc": 150, "params": 2, "start": 1, "end": 150}],
                   coupling=[{"entity": "a.py", "coupled": "b.py", "degree": 90, "average-revs": 11}],
                   dependencies={"status": "scanned", "sources": [{"path": "uv.lock", "packages": 3}], "packages": 3, "database_date": None,
                                 "vulnerable": [{"name": "x", "version": "1", "ecosystem": "PyPI", "source": "uv.lock", "ids": ["GHSA-1"], "aliases": [],
                                                 "advisories": 1, "score": 8.0, "severity": "high", "summary": "", "fixed": "2"}]},
                   age=[{"entity": "a.py", "age-months": 30}, {"entity": "b.py", "age-months": 0}],
                   ownership=[{"entity": "core/a.py", "author": "Ann", "added": 950, "deleted": 0},
                              {"entity": "web/b.py", "author": "Bob", "added": 900, "deleted": 0}])   # islands of two people: not merged into the bus factor
        r["meta"]["identities"] = [{"name": "Ann", "email": "ann@x.com", "commits": 5, "aliases": [{"name": "root", "email": "root@localhost", "commits": 1}]}]
        found = findings.evaluate(r)
        self.assertEqual({f["title"] for f in found} >= {"Bus factor of one", "Bug magnets", "Brain methods",
                                                      "Unconfigured git identity", "Knowledge islands",
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
                                     "oversized": "a fix over the repository's 99th percentile of lines changed credits nothing",
                                     "above_rate": {"test": "one-sided binomial, a file's fixes against its changes at the fixes per change of the files of its size, whole history",
                                                    "strata": "10 by lines of code over the tested files", "min_history_months": 12,
                                                    "fdr": "Benjamini-Hochberg over every source file", "q": 0.05, "ref": "Benjamini and Hochberg, JRSS B 1995"}})
        self.assertEqual(f["evidence"], {"count": 2, "files": [{"file": "a.py", "recent_fixes": 5, "fixes": 9}, {"file": "b.py", "recent_fixes": 3, "fixes": 3}]},
                         "no change table for a.py or b.py: no rate to test against, so no fix_rate")
        self.assertTrue(all(x["recent_fixes"] >= f["rule"]["min_recent"] for x in f["evidence"]["files"]))

    def test_a_bus_factor_can_be_rechecked_from_its_own_rule_and_evidence(self):
        f = findings.bus_factor(report(theseus_authors={"Ann": 79, "Bob": 21}))[0]
        self.assertEqual(f["rule"], {"id": "bus_factor", "threshold": 0.7, "min_lines": 200})
        self.assertEqual(f["evidence"], {"author": "Ann", "gone": False, "ask": None, "lines": 79, "total_lines": 100, "areas": []})
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

    def test_the_pin_advice_names_another_owners_action_before_the_repositorys_own(self):
        unpinned = [{"file": ".github/workflows/a.yml", "uses": "actions/checkout@v7"}, {"file": ".github/workflows/a.yml", "uses": "apache/skywalking-eyes@main"},
                    {"file": ".github/workflows/b.yml", "uses": "golangci/golangci-lint-action@v9"}]
        def advice(origin):
            return self.by_id(self.h(actions={"unpinned": unpinned, "unpinned_count": 3, "pinned": 0, "origin": origin}))["unpinned_actions"]["advice"]
        self.assertTrue(advice({"host": "github.com", "owner": "Apache"}).startswith("Pin golangci/golangci-lint-action@v9 "), "apache's own action is nearer than golangci's")
        self.assertTrue(advice(None).startswith("Pin apache/skywalking-eyes@main "), "no origin: the order as before")
        self.assertTrue(advice({"host": "gitlab.com", "owner": "apache"}).startswith("Pin apache/skywalking-eyes@main "), "an account on another host is not the GitHub one")
        f = self.by_id(self.h(actions={"unpinned": unpinned[:2], "unpinned_count": 2, "pinned": 0, "origin": {"host": "github.com", "owner": "apache"}}))["unpinned_actions"]
        self.assertTrue(f["advice"].startswith("Pin apache/skywalking-eyes@main "), "the repository's own owner still comes before GitHub's")

    def test_within_an_owner_tier_a_branch_ref_then_a_step_handed_secrets_or_a_write_token_comes_first(self):
        # univer: codecov@v7 led the advice while jikkai/sync-gitee@main, a branch handed two secrets, sat at row 19
        def row(uses, ref="version", secrets=False, grants=False, file=".github/workflows/ci.yml"):
            return {"file": file, "uses": uses, "line": 1, "ref": ref, "secrets": secrets, "grants": grants}
        unpinned = [row("actions/checkout@v7", secrets=True), row("codecov/codecov-action@v7", secrets=True),
                    row("pnpm/setup@v2", grants=True), row("o/plain@v1"), row("dream-num/own@main", ref="branch", secrets=True),
                    row("jikkai/sync-gitee@main", ref="branch", secrets=True, file=".github/workflows/sync.yml")]
        f = self.by_id(self.h(actions={"unpinned": unpinned, "unpinned_count": 6, "pinned": 0, "origin": {"host": "github.com", "owner": "dream-num"}}))["unpinned_actions"]
        self.assertTrue(f["advice"].startswith("Pin jikkai/sync-gitee@main "), f["advice"])
        self.assertEqual([u["uses"] for u in f["evidence"]["unpinned"]],
                         ["jikkai/sync-gitee@main", "codecov/codecov-action@v7", "pnpm/setup@v2", "o/plain@v1", "dream-num/own@main", "actions/checkout@v7"],
                         "owner first, then the branch, then a secret or a write grant, then the file order")
        self.assertEqual(f["rule"]["order"], findings.ACTION_ORDER)
        quiet = [row("o/first@v1"), row("o/second@v1", grants=True), row("o/third@v1", secrets=True)]
        f = self.by_id(self.h(actions={"unpinned": quiet, "unpinned_count": 3, "pinned": 0}))["unpinned_actions"]
        self.assertTrue(f["advice"].startswith("Pin o/second@v1 "), "a write token outranks an earlier step handed nothing")

    def test_the_evidence_names_each_action_once_per_file_up_to_the_hygiene_cap(self):
        rows = [{"file": f".github/workflows/w{i % 30}.yml", "uses": "actions/checkout@v7", "line": i, "ref": "version", "secrets": False, "grants": False}
                for i in range(120)]
        f = self.by_id(self.h(actions={"unpinned": rows, "unpinned_count": 120, "pinned": 0}))["unpinned_actions"]
        named = [(u["file"], u["uses"]) for u in f["evidence"]["unpinned"]]
        self.assertEqual((len(named), len(set(named))), (30, 30), "four checkouts in a file are one subject")
        many = [{**r, "file": f".github/workflows/w{i}.yml"} for i, r in enumerate(rows)]
        f = self.by_id(self.h(actions={"unpinned": many, "unpinned_count": 120, "pinned": 0}))["unpinned_actions"]
        self.assertEqual(len(f["evidence"]["unpinned"]), hygiene.CAP)

    def test_rows_from_before_the_step_context_keep_their_order_and_evidence(self):
        # a saved 0.44.0 output directory: no ref, secrets or grants, so the finding renders as it did
        unpinned = [{"file": ".github/workflows/a.yml", "uses": "actions/checkout@v7"}] * 4 + \
                   [{"file": f".github/workflows/w{i}.yml", "uses": f"o{i}/x@v1"} for i in range(9)] + \
                   [{"file": ".github/workflows/z.yml", "uses": "jikkai/sync-gitee@main"}]
        f = self.by_id(self.h(actions={"unpinned": unpinned, "unpinned_count": 14, "pinned": 0}))["unpinned_actions"]
        self.assertTrue(f["advice"].startswith("Pin o0/x@v1 "), "the first of the tie, as before")
        self.assertEqual(f["evidence"]["unpinned"], unpinned[:10])
        self.assertNotIn("order", f["rule"])

    def test_a_pwn_request_is_a_warning_naming_the_job_line_and_field(self):
        row = {"file": ".github/workflows/preview.yml", "job": "build", "line": 14, "key": "ref", "field": "github.event.pull_request.head.sha",
               "triggers": ["pull_request_target"]}
        f = self.by_id(self.h(actions={"unpinned": [], "unpinned_count": 0, "pinned": 1, "pwn_request": [row], "pwn_request_count": 1}))["pwn_request"]
        self.assertEqual((f["severity"], f["title"]), ("warning", "Workflows that run a pull request's code with secrets"))
        self.assertIn("1 checkout step under pull_request_target fetches the pull request's head: job build in .github/workflows/preview.yml, "
                      "line 14 (ref: github.event.pull_request.head.sha).", f["detail"])
        self.assertIn("not a value passed in through env: or a step output", f["detail"])
        self.assertEqual(f["evidence"], {"count": 1, "files": [{"file": ".github/workflows/preview.yml", "start": 14, "job": "build",
                                                                "field": "github.event.pull_request.head.sha", "key": "ref"}]})
        self.assertEqual(f["rule"]["scorecard"], "Dangerous-Workflow")
        self.assertIn("ref", f["rule"])

    def test_an_expression_injection_is_a_warning_that_says_it_sees_the_direct_case_only(self):
        rows = [{"file": ".github/workflows/bump.yml", "job": "update", "line": 44, "field": "github.event.pull_request.head.ref"}]
        f = self.by_id(self.h(actions={"unpinned": [], "unpinned_count": 0, "pinned": 1, "injection": rows, "injection_count": 1}))["expression_injection"]
        self.assertEqual(f["severity"], "warning")
        self.assertIn("1 run: script puts an event field someone outside the project can write (a title, a body, a branch name, a commit message) straight into the shell: "
                      "github.event.pull_request.head.ref at .github/workflows/bump.yml:44 (job update).", f["detail"])
        self.assertIn("gitmole sees the direct case only", f["detail"])
        self.assertIn("env: VALUE: ${{ github.event.pull_request.head.ref }}", f["advice"])
        self.assertEqual(f["evidence"]["files"][0]["start"], 44)

    def test_lockfile_drift_and_missing_lockfiles(self):
        found = self.by_id(self.h(lockfiles={"drift": [{"manifest": "package.json", "lockfile": "package-lock.json", "manifest_date": "2026-03-01", "lockfile_date": "2026-01-01"}],
                                             "drift_count": 1, "missing": [{"manifest": "lib/Cargo.toml", "expected": ["Cargo.lock"]}], "missing_count": 1, "pairs": 3}))
        self.assertEqual(found["lockfile_drift"]["severity"], "warning")
        self.assertIn("package.json changed on 2026-03-01, after package-lock.json last did on 2026-01-01", found["lockfile_drift"]["detail"])
        self.assertEqual(found["lockfile_missing"]["severity"], "info")
        self.assertIn("lib/Cargo.toml has no Cargo.lock", found["lockfile_missing"]["detail"])

    def test_a_drift_whose_changes_were_sweeping_is_left_out(self):
        # devlake: backend/go.mod's last change was e355317df, the module rename the report lists as sweeping
        drift = [{"manifest": "backend/go.mod", "lockfile": "backend/go.sum", "manifest_date": "2026-09-02", "lockfile_date": "2026-08-26",
                  "changes": [{"commit": "e355317df1f1d40af094d5e9c63d7dc9b5530f83", "date": "2026-09-02"}]},
                 {"manifest": "web/package.json", "lockfile": "web/package-lock.json", "manifest_date": "2026-09-02", "lockfile_date": "2026-01-01",
                  "changes": [{"commit": "e355317df1f1d40af094d5e9c63d7dc9b5530f83", "date": "2026-09-02"}, {"commit": "abc1234ffff", "date": "2026-03-01"}]}]
        r = self.h(lockfiles={"drift": drift, "drift_count": 2, "missing": [], "missing_count": 0, "pairs": 2})
        r["activity"] = {"sweeping": [{"hash": "e355317df", "files": 900}]}
        f = self.by_id(r)["lockfile_drift"]
        self.assertIn("1 manifest changed after the lock file that pins it: web/package.json changed on 2026-03-01", f["detail"])
        self.assertEqual(f["evidence"]["drift"], [{"manifest": "web/package.json", "lockfile": "web/package-lock.json", "manifest_date": "2026-03-01",
                                                   "lockfile_date": "2026-01-01", "commit": "abc1234ffff"}])
        r["hygiene"]["lockfiles"]["drift"] = drift[:1]
        r["hygiene"]["lockfiles"]["drift_count"] = 1
        self.assertNotIn("lockfile_drift", self.by_id(r))
        r["hygiene"]["lockfiles"]["drift"] = [{**drift[0], "more": True}]
        self.assertIn("lockfile_drift", self.by_id(r), "the recorded changes ran out: nothing says the older ones were sweeps")
        r["hygiene"]["lockfiles"]["drift"] = [{k: v for k, v in drift[0].items() if k != "changes"}]
        self.assertIn("lockfile_drift", self.by_id(r), "an output directory from before the changes were recorded")

    def test_update_tooling(self):
        f = self.by_id(self.h(updates={"tool": "dependabot", "covered": ["npm"], "uncovered": ["gomod", "pip"]}))["dependency_updates"]
        self.assertIn("dependabot.yml covers npm but not gomod and pip", f["detail"])
        f = self.by_id(self.h(updates={"tool": None, "covered": [], "uncovered": ["npm"]}))["dependency_updates"]
        self.assertIn("No dependency update tool is declared for npm", f["detail"])
        f = self.by_id(self.h(updates={"tool": "dependabot", "covered": ["npm"], "uncovered": ["github-actions"]}))["dependency_updates"]
        self.assertIn("dependabot.yml covers npm but not github-actions, whose actions the workflows here use.", f["detail"])
        self.assertIn("package-ecosystem entry for github-actions", f["advice"])
        f = self.by_id(self.h(updates={"tool": "dependabot", "covered": ["npm"], "uncovered": ["gomod", "github-actions"]}))["dependency_updates"]
        self.assertIn("dependabot.yml covers npm but not gomod, which have lock files here, nor github-actions, whose actions the workflows here use.", f["detail"])

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
        self.assertIn("npm ci --ignore-scripts", f["advice"])
        self.assertIn("pip install --only-binary", f["advice"], "both ecosystems named, both switches given")

    def test_install_advice_is_the_declared_package_managers(self):
        manifests = [{"file": "package.json", "scripts": ["postinstall"]}]
        for manager, switch in (("pnpm", "pnpm install --frozen-lockfile --ignore-scripts"), ("yarn-berry", "enableScripts: false"),
                                ("yarn", "yarn install --frozen-lockfile --ignore-scripts"), ("npm", "npm ci --ignore-scripts")):
            f = self.by_id(self.h(install={"lockfile": [], "manifests": manifests, "setup_py": [], "manager": {"name": manager, "from": "packageManager"}}))["install_scripts"]
            self.assertIn(switch, f["advice"], manager)
            if manager != "npm":
                self.assertNotIn("npm ci", f["advice"], manager)

    def test_a_setup_py_alone_gets_the_advice_of_its_own_ecosystem(self):
        # VoiceStudio's scripts/setup.py was told to run npm ci --ignore-scripts, which does nothing to a Python file
        f = self.by_id(self.h(install={"lockfile": [], "manifests": [], "setup_py": [{"file": "pkg/setup.py", "calls": ["subprocess.run"]}]}))["install_scripts"]
        self.assertNotIn("npm", f["advice"])
        self.assertIn("pkg/setup.py", f["advice"])
        self.assertIn("pip install --only-binary", f["advice"])

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
        s = {"status": "run", "analyser": "4", "resolved": {"python": 0.95}, "files": {p: {"language": "python", "debt": 0, "imports": [], "definitions": 5,
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

    def test_a_nameless_nested_function_is_anonymous_at_its_line(self):
        r = self.base(functions=[{"file": "src/f0.py", "name": "(anonymous at line 12)", "start": 12, "end": 300, "nesting": 6, "cognitive": 80,
                                  "complex_conditions": 2, "bumps": 3}])
        f = self.by_id(r)["deep_nesting"]
        self.assertIn("<anonymous> (src/f0.py:12) nested 6 deep", f["detail"])
        self.assertTrue(f["advice"].startswith("Flatten the anonymous function at src/f0.py:12 first"), f["advice"])
        self.assertEqual(f["evidence"]["functions"][0]["name"], "(anonymous at line 12)", "the evidence keeps what the step recorded")

    def test_import_cycles_name_each_group_and_a_shortest_loop_through_it(self):
        r = self.base()
        files = r["structure"]["files"]
        files["src/f0.py"]["imports"] = ["src/f1.py"]                  # f0 -> f1 -> f2 -> f0: one loop of three
        files["src/f1.py"]["imports"] = ["src/f2.py"]
        files["src/f2.py"]["imports"] = ["src/f0.py", "src/f3.py"]
        files["src/f4.py"]["imports"] = ["src/f5.py"]                  # f4 <-> f5, a pair
        files["src/f5.py"]["imports"] = ["src/f4.py"]
        files["src/f6.py"]["imports"] = ["src/f7.py"]                  # f6 <-> f7 only through a deferred import: no cycle at load
        files["src/f7.py"].update(imports=["src/f6.py"], deferred=["src/f6.py"])
        files["tests/test_f.py"]["imports"] = ["src/f8.py"]            # a test in a loop is not the source's layout
        files["src/f8.py"]["imports"] = ["tests/test_f.py"]
        f = self.by_id(r)["import_cycles"]
        self.assertEqual(f["severity"], "info")
        self.assertIn("In 2 groups, files import each other as they load: src/f0.py → src/f1.py → src/f2.py → src/f0.py; "
                      "src/f4.py → src/f5.py → src/f4.py.", f["detail"])
        self.assertNotIn("src/f6.py", f["detail"], "a deferred import is how a cycle is broken on purpose")
        self.assertNotIn("src/f8.py", f["detail"])
        self.assertEqual(f["evidence"]["groups"][0], {"files": ["src/f0.py", "src/f1.py", "src/f2.py"], "size": 3,
                                                      "loop": ["src/f0.py", "src/f1.py", "src/f2.py", "src/f0.py"]})
        self.assertEqual(f["evidence"]["count"], 2)
        self.assertTrue(f["advice"].startswith("Break src/f0.py → src/f1.py → src/f2.py → src/f0.py first"), f["advice"])
        self.assertEqual(f["rule"]["id"], "import_cycles")
        self.assertIn("Oyetoyan", f["rule"]["ref"])
        r["structure"]["resolved"] = {"python": 0.3}
        self.assertNotIn("import_cycles", self.by_id(r), "a graph that resolves a third of the imports cannot vouch for a loop")

    def test_import_cycles_judge_only_the_languages_the_graph_is_trusted_for(self):
        """The one gate structure.trusted sets for every rule leaning on the graph: a language resolved by path,
        mostly resolved, over at least MIN_FILES files. Three TypeScript files in a loop are too few to vouch
        for; at ten the language is judged."""
        r = self.base()
        files = r["structure"]["files"]
        files["src/f4.py"]["imports"], files["src/f5.py"]["imports"] = ["src/f5.py"], ["src/f4.py"]
        r["structure"]["resolved"]["typescript"] = 0.9
        ts = {"language": "typescript", "debt": 0, "definitions": 5, "max_nesting": 1, "max_cognitive": 3}
        for i in range(3):
            files[f"web/t{i}.ts"] = dict(ts, imports=[f"web/t{(i + 1) % 3}.ts"])
        f = self.by_id(r)["import_cycles"]
        self.assertNotIn("web/", f["detail"], "three TypeScript files are under the gate's ten")
        self.assertEqual(f["evidence"]["count"], 1)
        self.assertEqual((f["rule"]["min_resolved"], f["rule"]["min_files"]), (structure.MIN_RESOLVED, structure.MIN_FILES))
        for i in range(3, structure.MIN_FILES):
            files[f"web/t{i}.ts"] = dict(ts, imports=[])
        f = self.by_id(r)["import_cycles"]
        self.assertIn("web/t0.ts → web/t1.ts → web/t2.ts → web/t0.ts", f["detail"], "ten TypeScript files: the language is judged")
        self.assertEqual(f["evidence"]["count"], 2)

    def test_a_loop_through_a_small_language_is_kept_when_a_trusted_one_is_in_it(self):
        """.ts and .tsx are two languages to the gate and one module graph to the loader: two components in a
        loop with ten TypeScript files are judged by the TypeScript side, where two alone would not be."""
        r = self.base()
        files = r["structure"]["files"]
        r["structure"]["resolved"].update(typescript=0.9, tsx=0.9)
        ts = {"debt": 0, "definitions": 5, "max_nesting": 1, "max_cognitive": 3}
        files["web/C0.tsx"] = dict(ts, language="tsx", imports=["web/a0.ts"])
        files["web/a0.ts"] = dict(ts, language="typescript", imports=["web/C0.tsx"])
        self.assertNotIn("web/", (self.by_id(r).get("import_cycles") or {}).get("detail", ""), "one TypeScript file: nothing vouches")
        for i in range(1, structure.MIN_FILES):
            files[f"web/a{i}.ts"] = dict(ts, language="typescript", imports=[])
        f = self.by_id(r)["import_cycles"]
        self.assertIn("web/C0.tsx → web/a0.ts → web/C0.tsx", f["detail"])

    def test_a_structure_json_from_before_the_deferred_marks_names_no_loop(self):
        """Without the marks the rule would name the loops deferred imports break on purpose — the false
        groups the commit body recorded on django and binutils-gdb — so an older analyser's file is not judged."""
        r = self.base()
        files = r["structure"]["files"]
        files["src/f4.py"]["imports"], files["src/f5.py"]["imports"] = ["src/f5.py"], ["src/f4.py"]
        self.assertIn("import_cycles", self.by_id(r))
        for older in ("3", None):
            r["structure"]["analyser"] = older
            self.assertNotIn("import_cycles", self.by_id(r), f"analyser {older}")

    def test_the_group_is_named_by_its_own_shortest_loop_not_the_first_files(self):
        """a -> b -> c -> d -> a with d -> c: the shortest loop through a has four steps, the group's shortest is
        c -> d -> c, and that is what the finding names and the advice says to break first."""
        r = self.base()
        files = r["structure"]["files"]
        files["src/f0.py"]["imports"], files["src/f1.py"]["imports"] = ["src/f1.py"], ["src/f2.py"]
        files["src/f2.py"]["imports"], files["src/f3.py"]["imports"] = ["src/f3.py"], ["src/f0.py", "src/f2.py"]
        f = self.by_id(r)["import_cycles"]
        self.assertEqual(f["evidence"]["groups"][0]["loop"], ["src/f2.py", "src/f3.py", "src/f2.py"])
        self.assertIn("src/f2.py → src/f3.py → src/f2.py, one loop in a group of 4 files", f["detail"])
        self.assertTrue(f["advice"].startswith("Break src/f2.py → src/f3.py → src/f2.py first"), f["advice"])

    def test_a_large_group_is_named_by_its_shortest_loop_and_its_size(self):
        r = self.base()
        files = r["structure"]["files"]
        for i in range(6):                                              # f0 -> f1 -> ... -> f5 -> f0, and f3 -> f1 short-cuts it
            files[f"src/f{i}.py"]["imports"] = [f"src/f{(i + 1) % 6}.py"]
        files["src/f3.py"]["imports"].append("src/f1.py")
        f = self.by_id(r)["import_cycles"]
        self.assertIn("In 1 group, files import each other as they load: src/f1.py → src/f2.py → src/f3.py → src/f1.py, one loop in a group of 6 files.",
                      f["detail"], "the short cut makes a three-step loop, and that is the group's shortest, not the six-step ring through f0")
        files["src/f5.py"]["imports"] = []
        files["src/f0.py"]["imports"] = ["src/f1.py", "src/f2.py"]
        files["src/f2.py"]["imports"] = ["src/f3.py", "src/f0.py"]
        f = self.by_id(r)["import_cycles"]
        self.assertIn("src/f0.py → src/f2.py → src/f0.py, one loop in a group of 4 files", f["detail"], "the shortest loop through the first file")
        self.assertEqual(f["evidence"]["groups"][0]["files"], ["src/f0.py", "src/f1.py", "src/f2.py", "src/f3.py"])

    def test_the_groups_match_mutual_reachability_on_random_graphs(self):
        import random
        rng = random.Random(7)
        for _ in range(200):
            nodes = [f"n{i:02d}" for i in range(rng.randint(1, 25))]
            edges = {a: sorted({rng.choice(nodes) for _ in range(rng.randint(0, 3))} - {a}) for a in nodes}

            def reach(a):
                seen, todo = set(), [a]
                while todo:
                    for b in edges[todo.pop()]:
                        if b not in seen:
                            seen.add(b)
                            todo.append(b)
                return seen
            r = {a: reach(a) for a in nodes}
            want = sorted({tuple(sorted([a] + [b for b in nodes if b in r[a] and a in r[b] and b != a])) for a in nodes} - {(a,) for a in nodes})
            self.assertEqual(sorted(map(tuple, findings._groups(edges))), want)
            for g in findings._groups(edges):
                loop = findings._loop(edges, g)
                self.assertEqual(loop[0], loop[-1])
                self.assertIn(loop[0], g)
                self.assertTrue(all(b in edges[a] for a, b in zip(loop, loop[1:])), "every step of the loop is an import")
                self.assertTrue(all(len(findings._loop_from(edges, set(g), m) or loop) >= len(loop) for m in g), "no member has a shorter loop: the group's shortest")

    def test_import_cycles_leave_out_go_whose_compiler_refuses_them(self):
        """A Go import is an edge to every file of the package, whatever its build tags, so two files built for
        different platforms can close a loop the compiler would never see; a real one does not build."""
        r = self.base()
        files = r["structure"]["files"]
        r["structure"]["resolved"]["go"] = 1.0
        go = {"language": "go", "debt": 0, "definitions": 5, "max_nesting": 1, "max_cognitive": 3}
        for i in range(structure.MIN_FILES):
            files[f"p{i}/x_linux.go"] = dict(go, imports=[f"p{(i + 1) % structure.MIN_FILES}/x_linux.go"])
        self.assertNotIn("import_cycles", self.by_id(r))

    def test_import_cycles_is_unjudged_until_labelled(self):
        self.assertIn("import_cycles", findings.UNJUDGED)

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

    def test_hidden_coupling_leaves_out_two_go_files_of_one_package(self):
        """A Go package is a directory whose files share every name with no import between them, so two of
        them changing together is the package at work; two Go files in different packages are a pair."""
        r = self.base()
        for p in ("store/a.go", "store/b.go", "api/c.go"):
            r["size"]["files"][p] = {"code": 100, "complexity": 1}
            r["structure"]["files"][p] = {"language": "go", "debt": 0, "imports": [], "definitions": 5, "max_nesting": 1, "max_cognitive": 3}
        r["structure"]["resolved"]["go"] = 0.9
        r["coupling"] = [{"entity": "store/a.go", "coupled": "store/b.go", "degree": 90, "average-revs": 20},
                         {"entity": "store/a.go", "coupled": "api/c.go", "degree": 80, "average-revs": 20}]
        f = self.by_id(r)["hidden_coupling"]
        self.assertIn("store/a.go and api/c.go", f["detail"])
        self.assertNotIn("store/b.go", f["detail"], "one package: no import is needed between its files")
        r["structure"]["files"]["api/c.go"]["imports"] = ["store/a.go", "store/b.go"]
        self.assertNotIn("hidden_coupling", self.by_id(r), "an import of the package explains the other pair")

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

    def test_a_file_a_later_test_convention_names_is_left_out_of_a_saved_list(self):
        """paperclip's list led with packages/db/src/__fixtures__/x.mjs, a Jest fixture the structure step of its day
        did not call a test file; the render takes it out and counts one fewer."""
        f = self.by_id(self.base(unreferenced=["src/__fixtures__/f.mjs", "src/f11.py"], unreferenced_count=3))["unreferenced_files"]
        self.assertNotIn("__fixtures__", f["detail"])
        self.assertEqual((f["evidence"]["count"], f["evidence"]["files"]), (2, ["src/f11.py"]))
        self.assertNotIn("unreferenced_files", self.by_id(self.base(unreferenced=["scripts/smoke/run.mjs"], unreferenced_count=1)))

    def test_a_skipped_file_in_a_judged_language_is_named(self):
        """hindsight's busiest file was over the size limit, its imports vanished, and a file it imports read as
        unreferenced with nothing saying so."""
        skipped = [{"file": "src/huge.py", "bytes": 5_000_000, "reason": "over 4 MB"}, {"file": "web/app.min.js", "bytes": 2_000_000, "reason": "minified"}]
        f = self.by_id(self.base(unreferenced=["src/f11.py"], unreferenced_count=1, skipped=skipped))["unreferenced_files"]
        self.assertIn("src/huge.py was too big to parse (over 4 MB), so what it imports is not seen.", f["detail"])
        self.assertNotIn("app.min.js", f["detail"], "a language the list does not judge says nothing about it")
        self.assertEqual(f["evidence"]["skipped"], skipped[:1])
        f = self.by_id(self.base(unreferenced=["src/f11.py"], unreferenced_count=1, skipped=skipped[1:]))["unreferenced_files"]
        self.assertNotIn("skipped", f["evidence"])

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

    def test_a_pointer_names_its_target_and_a_vendored_file_is_left_out(self):
        found = self.by_id(self.rep(agents={"instructions": [
            {"file": "CLAUDE.md", "last": "2025-01-01", "commits_behind": 640, "points_to": ["AGENTS.md"]},
            {"file": "vendor/go.opentelemetry.io/otel/AGENTS.md", "last": "2025-01-01", "commits_behind": 640}]}))
        f = found["agent_instructions_drift"]
        self.assertIn("CLAUDE.md points at AGENTS.md, which last changed on 2025-01-01", f["detail"])
        self.assertNotIn("vendor/", f["detail"])
        self.assertEqual([r["file"] for r in f["evidence"]["files"]], ["CLAUDE.md"])
        self.assertTrue(f["advice"].startswith("Read AGENTS.md against the tree"))

    def test_a_skill_or_subagent_is_listed_but_is_never_behind_the_tree(self):
        found = self.by_id(self.rep(agents={"instructions": [
            {"file": ".claude/skills/fix/SKILL.md", "last": "2025-01-01", "commits_behind": 640, "kind": "skill"},
            {"file": ".codex/agents/runner.toml", "last": "2025-01-01", "commits_behind": 640, "kind": "subagent"}]}))
        self.assertNotIn("agent_instructions_drift", found)

    def test_a_sign_off_by_an_identity_that_only_co_authors(self):
        f = self.by_id(self.rep(trailers={"never_author": [], "signoff_by_co_author": [{"name": "Ghost", "email": "ghost@x.com", "commits": 3}]}))["signoff_by_co_author"]
        self.assertEqual(f["severity"], "info")
        self.assertIn("Ghost <ghost@x.com> signs off 3 commits but never authors one", f["detail"])
        self.assertEqual(self.by_id(self.rep()).get("signoff_by_co_author"), None)
        one = self.rep(trailers={"never_author": [], "signoff_by_co_author": [{"name": "Ghost", "email": "ghost@x.com", "commits": 1}]})
        self.assertIsNone(self.by_id(one).get("signoff_by_co_author"), "one commit is not a habit")


class References(unittest.TestCase):
    def test_every_rule_resting_on_a_paper_names_it_where_the_numbers_are(self):
        expected = {"tangled_commits": "Herzig and Zeller, MSR 2013",
                    "brain_methods": "Lanza and Marinescu, 2006", "tight_coupling": "Gall, Hajek and Jazayeri, ICSM 1998",
                    "trojan_source": "Boucher and Anderson, USENIX Security 2023",
                    "debt_in_hotspots": "Maldonado and Shihab, MTD 2015", "hidden_coupling": "Ajienka and Capiluppi, JSS 2017",
                    "unreferenced_files": "Romano et al., TSE 2020", "sweeping_commits": "Kolassa, Riehle and Salim, SOFSEM 2013",
                    "import_cycles": "Oyetoyan et al., SANER 2015"}
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

    def test_people_who_have_left_are_marked_and_not_the_ones_to_pair_with(self):
        doa = [self.row(f"core/a{i}.py", "Cat") for i in range(20)] + [self.row(f"web/b{i}.py", "Bob") for i in range(8)]
        f = {x["rule"]["id"]: x for x in findings.evaluate(self.rep(doa))}["truck_factor"]
        self.assertIn("Truck factor 1: without Cat (gone), 20 of the 28 source files", f["detail"])
        self.assertIn("have no author left. For those marked gone it already has.", f["detail"])
        self.assertIn("core/ (Cat (gone))", f["detail"])
        self.assertEqual(f["advice"], "Pair someone with Bob first; they author the most files among the people still here.")

    def test_people_still_here_who_author_equally_many_files_are_counted_and_none_is_named(self):
        doa = ([self.row(f"core/a{i}.py", "Cat") for i in range(20)] + [self.row(f"web/b{i}.py", "Bob") for i in range(8)]
               + [self.row(f"lib/c{i}.py", "Ann") for i in range(8)])
        f = {x["rule"]["id"]: x for x in findings.evaluate(self.rep(doa, theseus_authors={"Ann": 50, "Bob": 50}))}["truck_factor"]
        self.assertEqual(f["advice"], "Those named are gone, and the 2 people still here who author the most files author equally many; "
                                      "give the files owners, starting with the ones changed most.")
        self.assertIn("The surviving code's largest share, 50%, is held by 2 people equally, which the bus-factor finding reads.", f["detail"])

    def test_the_area_named_in_the_advice_is_the_named_persons_own(self):
        doa = [self.row(f"a{i}.py", "Ann") for i in range(20)] + [self.row(f"core/b{i}.py", "Bob") for i in range(10)]
        f = {x["rule"]["id"]: x for x in findings.evaluate(self.rep(doa))}["truck_factor"]
        self.assertEqual(f["evidence"]["areas"], [{"area": "core/", "author": "Bob", "files": 10, "orphaned": 10}])
        self.assertEqual(f["advice"], "Pair someone with Ann first; they author most of what would be left without an author.",
                         "core/ is Bob's: it is not where to pair someone with Ann")

    def test_the_start_area_is_where_most_files_are_at_stake(self):
        # hindsight named docker/ (9 files at stake) over hindsight-api-slim/ (267): the first area in the alphabet
        doa = [self.row(f"server/a{i}.py", "Ann") for i in range(30)] + [self.row(f"docker/d{i}.py", "Ann") for i in range(10)]
        doa += [self.row(f"web/b{i}.py", "Bob") for i in range(8)]
        f = {x["rule"]["id"]: x for x in findings.evaluate(self.rep(doa, theseus_authors={"Ann": 50, "Bob": 50}))}["truck_factor"]
        self.assertEqual(f["advice"], "Pair someone with Ann on server/ first; they author most of what would be left without an author.")
        self.assertEqual([a["area"] for a in f["evidence"]["areas"]], ["server/", "docker/"], "most at stake first")

    def test_an_even_split_of_the_surviving_code_is_explained(self):
        doa = [self.row(f"core/a{i}.py", "Ann") for i in range(20)] + [self.row(f"web/b{i}.py", "Bob") for i in range(8)]
        f = {x["rule"]["id"]: x for x in findings.evaluate(self.rep(doa, theseus_authors={"Ann": 50, "Bob": 50}))}["truck_factor"]
        self.assertIn("Truck factor 1: without Ann (50% of the surviving code), 20 of the 28 source files", f["detail"])
        f = {x["rule"]["id"]: x for x in findings.evaluate(self.rep(doa))}["truck_factor"]
        self.assertNotIn("surviving code", f["detail"], "Ann's 60% agrees with the truck factor")

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


class OneOwner(unittest.TestCase):
    """The bus factor, the truck factor and the knowledge islands naming one person are one finding: hindsight's
    report said the same fact three times, each with its own start area."""
    rep, row = TruckFactor.rep, TruckFactor.row

    def doa(self):
        return ([self.row(f"core/a{i}.py", "Ann") for i in range(20)] + [self.row(f"docs/d{i}.py", "Ann") for i in range(10)]
                + [self.row(f"web/b{i}.py", "Bob") for i in range(8)])

    def own(self):
        return [{"entity": "core/a0.py", "author": "Ann", "added": 900, "deleted": 0}, {"entity": "web/b0.py", "author": "Bob", "added": 50, "deleted": 0},
                {"entity": "docs/d0.py", "author": "Ann", "added": 300, "deleted": 0}]

    def test_one_person_three_measures_is_one_finding(self):
        found = findings.evaluate(self.rep(self.doa(), theseus_authors={"Ann": 90, "Bob": 10}, ownership=self.own()))
        ids = [f["rule"]["id"] for f in found]
        self.assertEqual([i for i in ids if i in findings.OWNERSHIP], ["bus_factor"])
        [f] = [f for f in found if f["rule"]["id"] == "bus_factor"]
        self.assertEqual(f["severity"], "warning")
        self.assertEqual(set(f["rule"]["measures"]), {"truck_factor", "knowledge_islands"}, "which measures fired stays in the rule")
        self.assertEqual(f["evidence"]["measures"]["truck_factor"]["truck_factor"], 1)
        self.assertEqual(f["evidence"]["measures"]["knowledge_islands"]["owners"], ["Ann"])
        self.assertIn("Ann wrote 90% of the code that survives today. Without them, 30 of the 38 source files (79%) have no author left (truck factor 1)", f["detail"])
        self.assertIn("2 area(s) of at least 200 lines are almost entirely theirs", f["detail"])
        self.assertIn("(knowledge islands)", f["detail"])
        self.assertEqual(f["advice"], "Pair someone with Ann on core/ first; 20 of its 20 files would have no author left without them.",
                         "the start area is the one with the most files at stake")

    def test_different_people_stay_apart(self):
        found = findings.evaluate(self.rep(self.doa(), theseus_authors={"Bob": 90, "Ann": 10}))
        ids = {f["rule"]["id"] for f in found}
        self.assertLessEqual({"bus_factor", "truck_factor"}, ids)
        self.assertNotIn("measures", next(f for f in found if f["rule"]["id"] == "bus_factor")["rule"])

    def test_a_truck_factor_with_someone_elses_area_of_one_stays_apart(self):
        doa = self.doa() + [self.row(f"web/c{i}.py", "Bob") for i in range(4)]   # web/ now has 12 files, all Bob's
        found = findings.evaluate(self.rep(doa, theseus_authors={"Ann": 90, "Bob": 10}))
        self.assertLessEqual({"bus_factor", "truck_factor"}, {f["rule"]["id"] for f in found})

    def test_two_of_three_merge_and_keep_the_leads_title(self):
        found = findings.evaluate(self.rep(self.doa(), theseus_authors={"Ann": 60, "Bob": 40}, ownership=self.own()))
        [f] = [f for f in found if f["rule"]["id"] in findings.OWNERSHIP]
        self.assertEqual((f["rule"]["id"], f["title"]), ("truck_factor", "Truck factor"))
        self.assertEqual(list(f["rule"]["measures"]), ["knowledge_islands"])
        self.assertTrue(f["detail"].startswith("Without Ann, 30 of the 38 source files"), f["detail"])


class ImportCommits(unittest.TestCase):
    def test_the_import_is_named_with_its_share(self):
        act = {"imports": [{"hash": "79d8f164f8", "date": "2019-03-26", "author": "Dan", "files": 12449, "added": 2800751, "deleted": 16,
                            "subject": "Candidate release of source code."}], "added_total": 6648513}
        f = findings.import_commits(report(activity=act))
        self.assertEqual(f[0]["rule"]["id"], "import_commits")
        self.assertIn("79d8f164f8 by Dan (12,449 code files; 2,800,751 lines of code, 42% of all the code the history adds", f[0]["detail"])
        self.assertIn("1 commit adds code and changes almost none: ", f[0]["detail"], "the rule allows deletions up to 1%")
        self.assertIn("Ownership, authorship and the churn counts leave it out", f[0]["detail"])
        self.assertNotIn("truck factor", f[0]["detail"], "a report with too few files to compute one must not be told it left the import out")
        self.assertEqual(findings.import_commits(report(activity={})), [])
        act["authors_all"] = {"Dan": {"last": "2019-03-26"}}
        f = findings.import_commits(report(activity=act, meta={"name": "r", "commits": 100, "identities": [], "last_date": "2026-09-01"}))
        self.assertIn("79d8f164f8 by Dan (gone, 12,449 code files", f[0]["detail"])

    ROW = {"hash": "7446c84", "date": "2026-03-09", "author": "Ann", "files": 313, "added": 40853, "deleted": 5, "subject": "Bundle the dependencies",
           "files_all": 722, "added_all": 83997, "binaries": 1, "under": "skills/x/node_modules/"}

    def test_the_counts_are_labelled_code_files_beside_the_commits_raw_totals(self):
        f = findings.import_commits(report(activity={"imports": [{**self.ROW, "in_tree": 12}], "added_total": 69000}))
        self.assertIn("7446c84 by Ann (313 code files of 722; 40,853 lines of code of 83,997, 59% of all the code the history adds, "
                      "all under skills/x/node_modules/, 1 binary file; 2026-03-09, Bundle the dependencies)", f[0]["detail"])
        self.assertEqual({k: f[0]["evidence"]["commits"][0][k] for k in ("files_all", "added_all", "binaries", "under", "in_tree")},
                         {"files_all": 722, "added_all": 83997, "binaries": 1, "under": "skills/x/node_modules/", "in_tree": 12})

    def test_an_import_nothing_of_which_is_in_the_tree_is_a_note_not_a_finding(self):
        gone = {**self.ROW, "in_tree": 0, "removed_in": {"hash": "7619570", "date": "2026-03-11", "commits": 2}}
        rep = report(activity={"imports": [gone], "added_total": 69000})
        self.assertEqual(findings.import_commits(rep), [])
        self.assertEqual(findings.imports_gone_note(rep),
                         "1 import left out of ownership (7446c84, 313 code files under skills/x/node_modules/, removed in 7619570): nothing of it is in the tree")
        both = report(activity={"imports": [gone, {**self.ROW, "hash": "aaa1111", "in_tree": 3}], "added_total": 69000})
        [f] = findings.import_commits(both)
        self.assertTrue(f["detail"].startswith("1 commit adds code"), f["detail"])
        self.assertEqual([c["hash"] for c in f["evidence"]["commits"]], ["aaa1111"])
        self.assertIsNone(findings.imports_gone_note(report(activity={"imports": [self.ROW]})), "no tree listing, nothing claimed")


class SecretsDeclared(unittest.TestCase):
    """VoiceStudio: a public analytics key the repository allowlisted, then replaced; betterleaks reads today's config only."""

    def test_a_value_the_repository_declared_is_info_naming_the_declaration_and_the_rest_stays_critical(self):
        said = {"file": ".gitleaks.toml", "commit": "e3ed952", "how": "allowlist regex"}
        rows = [{"rule": "posthog-project-api-key", "file": "backend/core/analytics.py", "commit": "23f1767", "line": 57, "fingerprint": "a",
                 "value": "v1", "placeholder": False, "confidence": "high", "declared": said},
                {"rule": "posthog-project-api-key", "file": "frontend/src/utils/analytics.ts", "commit": "23f1767", "line": 44, "fingerprint": "b",
                 "value": "v1", "placeholder": False, "confidence": "high"},
                {"rule": "generic-password", "file": "scripts/smoke.ps1", "commit": "51bbf50", "line": 8, "fingerprint": "c",
                 "value": "v2", "placeholder": False, "confidence": "medium"}]
        f = {x["rule"]["id"]: x for x in findings.secrets_found(report(secrets=rows))}
        self.assertEqual(set(f), {"secrets_in_source", "secrets_declared"})
        self.assertIn("1 distinct value in 1 place: generic-password in scripts/smoke.ps1", f["secrets_in_source"]["detail"])
        d = f["secrets_declared"]
        self.assertEqual(d["severity"], "info")
        self.assertIn("posthog-project-api-key in backend/core/analytics.py and 1 other file (23f1767, declared allowed in .gitleaks.toml at e3ed952)",
                      d["detail"], "one declaration covers the value wherever it is")
        self.assertNotIn("otate", d["advice"])
        self.assertEqual(d["evidence"]["declared"], [dict(said, rule="posthog-project-api-key")])
        self.assertEqual(d["evidence"]["files"], ["backend/core/analytics.py", "frontend/src/utils/analytics.ts"])
        only = findings.secrets_found(report(secrets=rows[:2]))
        self.assertEqual([x["severity"] for x in only], ["info"], "nothing critical is left for --fail-on critical to stop on")

    def test_a_declared_value_only_in_tests_is_still_no_finding(self):
        rows = [{"rule": "x", "file": "tests/t.py", "commit": "c", "line": 1, "fingerprint": "a", "value": "v1", "placeholder": False,
                 "declared": {"file": ".gitleaksignore", "commit": "d", "how": "fingerprint"}}]
        self.assertEqual(findings.secrets_found(report(secrets=rows)), [])


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

    def test_generated_mock_tooling_and_testdata_files_are_no_finding(self):
        rows = [self._row("g", "generic-password", "api/registry.pb.go", "medium"), self._row("m", "generic-api-key", "discovery/openstack/mock.go", "medium"),
                self._row("h", "private-key", "hack/scripts-dev/certs/server.key.insecure", "high"), self._row("t", "ibm-cloud-user-api-key", "cmd/tsdb/testdata.20k", "high"),
                self._row("f", "private-key", "integration/fixtures-expired/server.key", "high"), self._row("w", "private-key", "Godeps/_workspace/src/x/server.key", "high")]
        r = report(secrets=rows, meta={"name": "r", "commits": 100, "identities": [], "generated": ["api/registry.pb.go"]})
        self.assertEqual(findings.secrets_found(r), [])

    def test_an_unreachable_copy_is_placed_by_the_located_ones(self):
        rows = [self._row("t", "generic-password", "(unreachable blob 742c1cc5ebfb)", "medium"), self._row("t", "generic-password", "tests/mail/tests.py", "medium"),
                self._row("u", "facebook-access-token", "(unreachable blob 00db21063ea1)", "high")]
        f = {x["rule"]["id"]: x for x in findings.secrets_found(report(secrets=rows))}
        self.assertEqual(set(f), {"secrets_in_source"})
        self.assertIn("1 secret(s) in history", f["secrets_in_source"]["title"], "only ever unreachable: nowhere to say it is test data")
        self.assertIn("facebook-access-token", f["secrets_in_source"]["detail"])
        self.assertNotIn("generic-password", f["secrets_in_source"]["detail"], "its other copy is a test file")



class SecretsAtHead(unittest.TestCase):
    def _row(self, value, file, at_head=None):
        r = {"rule": "aws-access-token", "file": file, "commit": "abc1234", "line": 3, "fingerprint": value + file, "value": value,
             "placeholder": False, "confidence": "high"}
        if at_head is not None:
            r["at_head"] = at_head
        return r

    def _critical(self, rows):
        return next(x for x in findings.secrets_found(report(secrets=rows)) if x["rule"]["id"] == "secrets_in_source")

    def test_a_value_only_in_history_is_told_to_rewrite_it(self):
        f = self._critical([self._row("a", "app/a.py", False), self._row("b", "app/b.py", False)])
        self.assertIn("None is at HEAD any more", f["advice"])
        self.assertIn("if the history is published, rewrite it", f["advice"])
        self.assertEqual((f["evidence"]["at_head"], f["evidence"]["history_only"]), (0, 2))
        self.assertEqual(f["evidence"]["history_only_values"], [{"rule": "aws-access-token", "file": "app/a.py"}, {"rule": "aws-access-token", "file": "app/b.py"}])
        self.assertNotIn("a", [v.get("value") for v in f["evidence"]["history_only_values"]], "the evidence never carries the value")

    def test_a_value_still_at_head_anywhere_is_at_head(self):
        f = self._critical([self._row("a", "app/old.py", False), self._row("a", "app/new.py", True)])
        self.assertTrue(f["advice"].startswith("Rotate them; deleting the file does not remove them from git."))
        self.assertEqual((f["evidence"]["at_head"], f["evidence"]["history_only"]), (1, 0))

    def test_a_mix_counts_each_and_one_unjudged_counts_as_at_head(self):
        f = self._critical([self._row("a", "app/a.py", True), self._row("b", "app/b.py", False), self._row("c", "app/c.py")])
        self.assertIn("2 are still at HEAD and 1 only in history", f["advice"])
        self.assertEqual(len(findings.secrets_found(report(secrets=[self._row("a", "app/a.py", True), self._row("b", "app/b.py", False)]))), 1,
                         "the split is in the text: still one finding")

    def test_the_rule_carries_its_measured_limit(self):
        f = self._critical([self._row("a", "app/a.py", True)])
        self.assertIn("46% precision, 88% recall", f["rule"]["measured"])
        self.assertIn("Meli", f["rule"]["ref"])


class OneThreshold(unittest.TestCase):
    def test_the_structure_rules_read_min_resolved_from_one_place(self):
        """The sweep reads a threshold from the signature; a copy of the number drifts from the constant."""
        import inspect
        from gitmole import findings, structure
        for rule in (findings.hidden_coupling, findings.import_cycles):
            self.assertIs(inspect.signature(rule).parameters["min_resolved"].default, structure.MIN_RESOLVED, rule.__name__)

import os
import subprocess
import tempfile
import unittest
from unittest import mock

from gitmole.measure import consistency


def report(**over):
    """The least of an export each check reads: a history from 2020 to 2026 in which Ann left in 2022."""
    base = {
        "meta": {"first_date": "2020-01-01", "last_date": "2026-09-01", "gone_months": 12, "bots": [], "aliases": {}},
        "activity": {"authors": {"Ann": {"commits": 40, "last": "2022-03-01"}, "Bo": {"commits": 90, "last": "2026-08-30"}},
                     "sweeping": []},
        "findings": [],
    }
    for k, v in over.items():
        base[k] = v if not isinstance(v, dict) or k not in base else {**base[k], **v}
    return base


def finding(rule, detail="", advice="", evidence=None, severity="info"):
    return {"rule": {"id": rule}, "detail": detail, "advice": advice, "evidence": evidence or {}, "severity": severity, "title": rule}


def checks(r, clone=None):
    return sorted(c["check"] for c in consistency.over(r, clone)["complaints"])


class GonePeople(unittest.TestCase):
    def test_advice_naming_someone_gone(self):
        """django's "Have Adrian Holovaty ... review", react's "Pair someone with Jan Kassens": the
        knowledge map in the same report marks both gone."""
        f = finding("minor_contributors", "x.py (6 of 9 authors).", "Have Ann, who wrote most of x.py, review changes to it.",
                    {"files": [{"file": "x.py", "owner": "Ann"}]})
        self.assertEqual(checks(report(findings=[f])), ["gone_in_advice"])

    def test_advice_naming_someone_active_is_fine(self):
        f = finding("minor_contributors", "x.py (6 of 9 authors).", "Have Bo review changes to it.", {"files": [{"file": "x.py", "owner": "Bo"}]})
        self.assertEqual(checks(report(findings=[f])), [])

    def test_a_gone_name_in_the_detail_needs_the_mark(self):
        unmarked = finding("truck_factor", "Truck factor 2: without Ann and Bo, 9 files have no author left.", "",
                           {"removed": ["Ann", "Bo"]})
        marked = finding("truck_factor", "Truck factor 2: without Ann (gone) and Bo, 9 files have no author left.", "",
                         {"removed": ["Ann", "Bo"]})
        self.assertEqual(checks(report(findings=[unmarked])), ["gone_unmarked"])
        self.assertEqual(checks(report(findings=[marked])), [])

    def test_the_rules_about_the_gone_may_name_them(self):
        f = finding("knowledge_loss", "Ann left; 40% of the code is theirs.", "Find who knows Ann's code.", {"people": ["Ann"]})
        self.assertEqual(checks(report(findings=[f])), [])

    def test_a_name_inside_a_path_is_not_the_person(self):
        """Only the evidence's person fields are names; a directory called ann/ in the advice is not Ann."""
        f = finding("bug_magnets", "ann/x.py was fixed 5 times.", "Review ann/x.py before the next release.", {"files": [{"file": "ann/x.py"}]})
        self.assertEqual(checks(report(findings=[f])), [])


class WrongArea(unittest.TestCase):
    def test_pairing_on_someone_elses_area(self):
        """react's truck factor fell back to another person's area: compiler/ is Joe Savona's."""
        f = finding("truck_factor", "Truck factor 4.", "Pair someone with Bo on compiler/ first; they author most of it.",
                    {"removed": ["Bo"], "areas": [{"area": "compiler/", "author": "Cy"}]})
        self.assertEqual(checks(report(findings=[f])), ["wrong_area"])

    def test_pairing_on_their_own_area(self):
        f = finding("truck_factor", "Truck factor 4.", "Pair someone with Bo on compiler/ first.",
                    {"removed": ["Bo"], "areas": [{"area": "compiler/", "author": "Bo"}]})
        self.assertEqual(checks(report(findings=[f])), [])


class GrowthWindow(unittest.TestCase):
    def test_a_year_claimed_over_ten_days(self):
        """gitmole's own report: "+1163% in a year" on a history of ten days."""
        r = report(meta={"first_date": "2026-09-15", "last_date": "2026-09-25"},
                   findings=[finding("complexity_growth", "3 hotspots grew by 25% or more in a year.")],
                   watch=[{"file": "a.py", "reasons": ["complexity +1163% in a year"]}])
        self.assertEqual(checks(r), ["growth_window", "growth_window"])

    def test_a_year_of_history_is_enough(self):
        r = report(findings=[finding("complexity_growth", "3 hotspots grew by 25% or more in a year.")])
        self.assertEqual(checks(r), [])


class SecretsHeadline(unittest.TestCase):
    def test_leading_with_the_weakest_value(self):
        """devlake's critical named `password: 'Password'` first and never the GitHub token beside it."""
        f = finding("secrets_in_source", "2 distinct values in 3 places: generic-password in ui/Providers.js (1aee294); "
                    "github-pat in ui/Detail.js (2debaa3).", evidence={"files": ["ui/Detail.js", "ui/Providers.js"]}, severity="critical")
        secrets = [{"rule": "generic-password", "file": "ui/Providers.js", "confidence": "low"},
                   {"rule": "github-pat", "file": "ui/Detail.js", "confidence": "high"}]
        self.assertIn("secrets_headline", checks(report(findings=[f], secrets=secrets)))

    def test_leading_with_the_strongest_value(self):
        f = finding("secrets_in_source", "2 distinct values in 3 places: github-pat in ui/Detail.js (2debaa3); "
                    "generic-password in ui/Providers.js (1aee294).", evidence={"files": ["ui/Detail.js", "ui/Providers.js"]})
        secrets = [{"rule": "generic-password", "file": "ui/Providers.js", "confidence": "low"},
                   {"rule": "github-pat", "file": "ui/Detail.js", "confidence": "high"}]
        self.assertEqual(checks(report(findings=[f], secrets=secrets)), [])


class SarifGate(unittest.TestCase):
    def test_a_critical_with_no_result(self):
        """devlake: --fail-on critical exits 3 on a critical that code scanning never shows."""
        f = finding("secrets_in_source", "1 distinct value in 1 place: github-pat in gone.js (abc1234).", severity="critical",
                    evidence={"files": ["gone.js"]})
        r = report(findings=[f], size={"files": {"kept.js": {}}})   # the file is no longer in the tree, so no location survives
        # sarif.py now keeps a location-less result for such a finding; the check must still see a document without one
        with mock.patch.object(consistency.sarif, "results", return_value=[]):
            self.assertIn("sarif_gate", checks(r))
        self.assertNotIn("sarif_gate", checks(r), "the finding has its result now")

    def test_info_findings_are_not_gated(self):
        r = report(findings=[finding("reverts", "5 reverts.")])
        self.assertNotIn("sarif_gate", checks(r))


class TrailerAuthor(unittest.TestCase):
    def test_a_co_author_counted_as_an_author(self):
        """gitmole's People table: every commit of the agent came from Co-authored-by trailers."""
        r = report(activity={"authors": {"Bot Author": {"commits": 19, "last": "2026-08-01"}, "Bo": {"commits": 90, "last": "2026-08-30"}}},
                   provenance={"trailers": {"never_author": [{"name": "Bot Author", "commits": 19}]}})
        self.assertEqual(checks(r), ["trailer_author"])

    def test_aliases_are_followed(self):
        r = report(meta={"aliases": {"Agent 4.5": "Agent 4.8"}},
                   activity={"authors": {"Agent 4.8": {"commits": 7, "last": "2026-08-01"}}},
                   provenance={"trailers": {"never_author": [{"name": "Agent 4.5", "commits": 7}]}})
        self.assertEqual(checks(r), ["trailer_author"])

    def test_authored_commits_kept_apart_are_fine(self):
        r = report(activity={"authors": {"Bot Author": {"commits": 19, "authored": 0, "last": "2026-08-01"}}},
                   provenance={"trailers": {"never_author": [{"name": "Bot Author", "commits": 19}]}})
        self.assertEqual(checks(r), [])

    def test_an_export_with_authored_counts_is_honest_by_construction(self):
        """Someone who wrote commits and is also credited under another address: after the People table
        started counting authored commits apart, comparing credit with them fired on such people."""
        r = report(activity={"authors": {"Bo": {"commits": 9, "authored": 3, "last": "2026-08-30"}}},
                   provenance={"trailers": {"never_author": [{"name": "Bo", "commits": 6}]}})
        self.assertEqual(checks(r), [])

    def test_someone_who_also_authored(self):
        r = report(activity={"authors": {"Bo": {"commits": 90, "last": "2026-08-30"}}},
                   provenance={"trailers": {"never_author": [{"name": "Bo", "commits": 4}]}})
        self.assertEqual(checks(r), [])


def git(repo, *args, env=None):
    return subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True, env=env).stdout.strip()


class WithTheClone(unittest.TestCase):
    """tree_claim and sweeping_evidence read git at the commit the run recorded."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = self.tmp.name
        env = {**os.environ, "GIT_AUTHOR_NAME": "Bo", "GIT_AUTHOR_EMAIL": "bo@example.org", "GIT_COMMITTER_NAME": "Bo",
               "GIT_COMMITTER_EMAIL": "bo@example.org", "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_SYSTEM": os.devnull}
        git(self.repo, "init", "-q", "-b", "main", env=env)
        with open(os.path.join(self.repo, "tool"), "wb") as fh:
            fh.write(b"\xcf\xfa\xed\xfe" + b"\0" * 64)
        with open(os.path.join(self.repo, "go.mod"), "w") as fh:
            fh.write("module example.org/old\n")
        git(self.repo, "add", "tool", "go.mod", env=env)
        git(self.repo, "commit", "-q", "-m", "first", env=env)
        with open(os.path.join(self.repo, "go.mod"), "w") as fh:
            fh.write("module example.org/new\n")
        git(self.repo, "add", "go.mod", env=env)
        git(self.repo, "commit", "-q", "-m", "rename the module", env=env)
        self.head = git(self.repo, "rev-parse", "HEAD")

    def tearDown(self):
        self.tmp.cleanup()

    def base(self, **over):
        return report(meta={"run": {"commit": self.head}}, **over)

    def test_a_binary_at_head_called_gone(self):
        """devlake's 37 MiB Mach-O: git-sizer's row said it had left the tree, scc's listing leaves binaries out."""
        f = finding("repo_health", "Blobs: Maximum size is 37.4 MiB at tool, no longer in the tree.", evidence={"ref": "tool"})
        self.assertEqual(checks(self.base(findings=[f]), self.repo), ["tree_claim"])

    def test_a_path_really_gone_is_fine(self):
        f = finding("repo_health", "Blobs: Maximum size is 37.4 MiB at old.bin, no longer in the tree.", evidence={"ref": "old.bin"})
        self.assertEqual(checks(self.base(findings=[f]), self.repo), [])

    def test_drift_that_rests_on_a_sweeping_commit(self):
        """devlake's go.mod "changed after go.sum": the change was the module rename the report left out as sweeping."""
        f = finding("lockfile_drift", "1 manifest changed after the lock file that pins it.",
                    evidence={"drift": [{"manifest": "go.mod", "lockfile": "go.sum"}]})
        r = self.base(findings=[f], activity={"sweeping": [{"hash": self.head[:9]}]})
        self.assertEqual(checks(r, self.repo), ["sweeping_evidence"])
        r = self.base(findings=[f], activity={"sweeping": []})
        self.assertEqual(checks(r, self.repo), [])

    def test_without_the_recorded_commit_the_git_checks_are_skipped(self):
        f = finding("repo_health", "Blobs: Maximum size is 37.4 MiB at tool, no longer in the tree.", evidence={"ref": "tool"})
        one = consistency.over(report(meta={"run": {"commit": "0" * 40}}, findings=[f]), self.repo)
        self.assertFalse(one["clone"])
        self.assertEqual(one["complaints"], [])


class Totals(unittest.TestCase):
    def test_clean_counts_findings_and_tables_are_apart(self):
        f = finding("minor_contributors", "x.py.", "Have Ann review it.", {"files": [{"owner": "Ann"}]})
        g = finding("reverts", "5 reverts.")
        r = report(findings=[f, g], provenance={"trailers": {"never_author": [{"name": "Bo", "commits": 90}]}})
        one = consistency.over(r)
        self.assertEqual((one["checked"], one["clean"]), (2, 1))
        self.assertEqual(consistency.by_check(one["complaints"]), {"gone_in_advice": 1, "trailer_author": 1})


if __name__ == "__main__":
    unittest.main()

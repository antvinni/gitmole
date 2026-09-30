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


class Agents(unittest.TestCase):
    """VoiceStudio: every model version of one assistant was its own identity on one shared no-reply address."""

    def ids(self, *rows):
        return report(meta={"identities": [dict(r) for r in rows]})

    def test_a_trailer_only_identity_is_a_person(self):
        r = self.ids({"name": "Helper", "email": "h@x.org", "commits": 9, "authored": 0})
        self.assertEqual(consistency.agents(r), set())

    def test_names_sharing_a_bare_no_reply_address_are_a_tool(self):
        r = self.ids({"name": "Model A", "email": "noreply@vendor.example", "commits": 9, "authored": 1},
                     {"name": "Model B", "email": "noreply@vendor.example", "commits": 3, "authored": 0},
                     {"name": "Ann", "email": "12+ann@users.noreply.example", "commits": 40, "authored": 40},
                     {"name": "Bo", "email": "12+bo@users.noreply.example", "commits": 5, "authored": 5})
        self.assertEqual(consistency.agents(r), {"Model A", "Model B"}, "a per-user noreply address is a person")

    def test_one_person_on_a_no_reply_address_is_a_person(self):
        r = self.ids({"name": "Ann", "email": "noreply@ann.example", "commits": 40, "authored": 40})
        self.assertEqual(consistency.agents(r), set())


class WithARepository(unittest.TestCase):
    """The checks the VoiceStudio review added, each on the smallest tree that shows it."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = self.tmp.name
        self.env = {**os.environ, "GIT_AUTHOR_NAME": "Ann", "GIT_AUTHOR_EMAIL": "ann@example.org", "GIT_COMMITTER_NAME": "Ann",
                    "GIT_COMMITTER_EMAIL": "ann@example.org", "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_SYSTEM": os.devnull}
        git(self.repo, "init", "-q", "-b", "main", env=self.env)

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, path, text):
        full = os.path.join(self.repo, path)
        os.makedirs(os.path.dirname(full) or self.repo, exist_ok=True)
        with open(full, "w") as fh:
            fh.write(text)

    def commit(self, message="c", **env):
        git(self.repo, "add", "-A", env=self.env)
        git(self.repo, "commit", "-q", "-m", message, env={**self.env, **env})
        return git(self.repo, "rev-parse", "HEAD")

    def over(self, **r):
        head = git(self.repo, "rev-parse", "HEAD")
        meta = {"run": {"commit": head}, **(r.pop("meta", {}))}
        return sorted(c["check"] for c in consistency.over(report(meta=meta, **r), self.repo)["complaints"])

    def test_a_bug_magnet_deleted_since(self):
        self.write("app/live.py", "x = 1\n")
        self.write("old/gone.py", "y = 1\n")
        self.commit()
        git(self.repo, "rm", "-q", "old/gone.py", env=self.env)
        self.commit("retire old/")
        f = finding("bug_magnets", evidence={"files": [{"file": "app/live.py"}], "new_in_window": ["app/live.py", "old/gone.py"]})
        self.assertEqual(self.over(findings=[f]), ["magnet_gone"])
        f = finding("bug_magnets", evidence={"files": [{"file": "app/live.py"}], "new_in_window": ["app/live.py"]})
        self.assertEqual(self.over(findings=[f]), [])

    def test_an_extra_index_named_only_in_a_comment(self):
        """VoiceStudio's requirements.txt: `# No --extra-index-url lines` matched as one."""
        self.write("req/requirements.txt", "# No --extra-index-url lines: one index\ntorch==2.0\n")
        self.write("real/requirements.txt", "--extra-index-url https://example.org/simple\ntorch==2.0\n")
        self.commit()
        comment = finding("dependency_confusion", evidence={"pip_extra_index": ["req/requirements.txt"]})
        real = finding("dependency_confusion", evidence={"pip_extra_index": ["real/requirements.txt"]})
        self.assertEqual(self.over(findings=[comment]), ["hygiene_misread"])
        self.assertEqual(self.over(findings=[real]), [])

    def test_a_setup_py_that_calls_no_setup(self):
        self.write("scripts/setup.py", "import subprocess\nsubprocess.run(['make'])\n")
        self.write("pkg/setup.py", "from setuptools import setup\nsetup(name='p')\n")
        self.commit()
        helper = finding("install_scripts", evidence={"setup_py": [{"file": "scripts/setup.py", "calls": ["subprocess.run"]}]})
        real = finding("install_scripts", evidence={"setup_py": [{"file": "pkg/setup.py", "calls": []}]})
        self.assertEqual(self.over(findings=[helper]), ["hygiene_misread"])
        self.assertEqual(self.over(findings=[real]), [])

    def test_drift_in_a_workspace_member_whose_root_keeps_the_lock(self):
        self.write("package.json", '{"workspaces": ["app"]}')
        self.write("bun.lock", "{}")
        self.write("app/package.json", '{"dependencies": {"a": "1"}}')
        self.write("app/bun.lock", "{}")
        self.commit()
        f = finding("lockfile_drift", evidence={"drift": [{"manifest": "app/package.json", "lockfile": "app/bun.lock"}]})
        self.assertEqual(self.over(findings=[f]), ["lock_workspace"])
        g = finding("lockfile_drift", evidence={"drift": [{"manifest": "tool/package.json", "lockfile": "tool/bun.lock"}]})
        self.assertEqual(self.over(findings=[g]), [], "not a declared member")

    def test_an_unreferenced_file_a_build_config_names(self):
        self.write("hooks/rth_compat.py", "x = 1\n")
        self.write("app.spec", "runtime_hooks=['hooks/rth_compat.py']\n")
        self.write("lone/dead.py", "y = 1\n")
        self.write("docs/ROADMAP.md", "retire lone/dead.py\n")
        self.commit()
        named = finding("unreferenced_files", evidence={"files": ["hooks/rth_compat.py"]})
        prose = finding("unreferenced_files", evidence={"files": ["lone/dead.py"]})
        self.assertEqual(self.over(findings=[named]), ["unreferenced_named"])
        self.assertEqual(self.over(findings=[prose]), [], "a roadmap naming a file does not load it")

    def test_co_authored_counts_the_author_crediting_an_alias(self):
        """VoiceStudio: 430 of the owner's 454 co-authored commits were his own, through a second name."""
        self.write("a.py", "1\n")
        self.commit("mine\n\nCo-authored-by: Ann Old <ann@old.example>")
        self.write("b.py", "1\n")
        self.commit("theirs\n\nCo-authored-by: Ann <ann@example.org>", GIT_AUTHOR_NAME="Bo", GIT_AUTHOR_EMAIL="bo@example.org")
        ids = [{"name": "Ann", "email": "ann@example.org", "commits": 3, "authored": 1,
                "aliases": [{"name": "Ann Old", "email": "ann@old.example"}]},
               {"name": "Bo", "email": "bo@example.org", "commits": 1, "authored": 1}]
        self.assertEqual(self.over(meta={"identities": ids}), ["self_credit"], "two credited, one is someone else's")
        ids[0]["commits"] = 2
        self.assertEqual(self.over(meta={"identities": ids}), [])

    def test_a_critical_the_repository_declared_allowed(self):
        """VoiceStudio's publishable analytics key: allowlisted in .gitleaks.toml, then replaced."""
        value = "phc_" + "A1b2C3d4E5f6G7h8I9j0K1l2M3n4"
        self.write("app/analytics.py", "KEY = '" + value + "'\n")
        first = self.commit("add analytics")
        self.write(".gitleaks.toml", '[allowlist]\nregexes = ["' + value + '"]\n')
        self.commit("the key is publishable")
        self.write(".gitleaks.toml", "[allowlist]\nregexes = []\n")
        self.write("app/analytics.py", "KEY = 'rotated'\n")
        self.commit("replace the key")
        f = finding("secrets_in_source", severity="critical", evidence={"files": ["app/analytics.py"]})
        rows = [{"rule": "posthog-project-api-key", "file": "app/analytics.py", "line": 1, "commit": first, "confidence": "high"}]
        self.assertIn("declared_critical", self.over(findings=[f], secrets=rows))
        f["severity"] = "warning"
        self.assertNotIn("declared_critical", self.over(findings=[f], secrets=rows), "only a critical is held to it")

class UndecodablePaths(unittest.TestCase):
    """The 0.40.0 round crashed on the awkward-non-utf8-path fixture: git printed a Latin-1 file name."""

    def test_a_path_that_is_not_utf8_does_not_crash_the_checks(self):
        from gitmole.measure import corpus
        with tempfile.TemporaryDirectory() as root:
            repo = corpus.fixture("non-utf8-path", root)   # the very fixture: its path is built through git's index
            head = git(repo, "rev-parse", "HEAD")
            names = subprocess.run(["git", "ls-tree", "-r", "-z", "--name-only", head], cwd=repo, capture_output=True).stdout
            self.assertTrue(any(not _utf8(n) for n in names.split(b"\0") if n), "the fixture holds a name that is not UTF-8")
            f = finding("bug_magnets", evidence={"files": [{"file": "x.py"}], "new_in_window": ["x.py"]})
            one = consistency.over(report(meta={"run": {"commit": head}}, findings=[f]), repo)
            self.assertTrue(one["clone"], "the git checks ran rather than raising")


def _utf8(b: bytes) -> bool:
    try:
        b.decode("utf-8")
        return True
    except UnicodeDecodeError:
        return False

class FromTheExport(unittest.TestCase):
    """The hindsight review's checks that need nothing but the export."""

    def test_the_truck_factor_starts_where_most_is_at_stake(self):
        """hindsight's advice named docker/ (9 files at stake) over the area with 267, first alphabetically."""
        areas = [{"area": "docker/", "author": "Bo", "orphaned": 9}, {"area": "server/", "author": "Bo", "orphaned": 267}]
        bad = finding("truck_factor", advice="Pair someone with Bo on docker/ first; they author most of it.", evidence={"areas": areas})
        good = finding("truck_factor", advice="Pair someone with Bo on server/ first; they author most of it.", evidence={"areas": areas})
        self.assertEqual(checks(report(findings=[bad])), ["start_area"])
        self.assertEqual(checks(report(findings=[good])), [])

    def test_a_requirements_file_set_aside_as_documentation(self):
        rows = [{"name": "mcp", "version": "1.0.0", "source": "integrations/code/requirements.txt"}]
        f = finding("vulnerable_dependencies_aside", evidence={"packages": rows})
        self.assertEqual(checks(report(findings=[f])), ["doc_lock"])
        rows[0]["source"] = "tests/requirements.txt"
        self.assertEqual(checks(report(findings=[f])), [], "a test path is set aside rightly")

    def test_a_person_grouped_as_a_tool(self):
        """TuftyBruno authored a commit under his own address; his own trailer used a shared no-reply mailbox."""
        ids = [{"name": "Model A", "email": "noreply@vendor.example", "commits": 9, "authored": 0},
               {"name": "Model B", "email": "noreply@vendor.example", "commits": 3, "authored": 0},
               {"name": "Tufty", "email": "7+tufty@users.noreply.example", "commits": 2, "authored": 1,
                "aliases": [{"name": "Tufty", "email": "noreply@vendor.example"}]}]
        r = report(meta={"identities": ids})
        found = checks(r)
        self.assertEqual(found.count("tool_person"), 1 if "Tufty" in consistency.agents(r) else 0,
                         "complains exactly when the tool rule claims the person")


class WithARepositoryAgain(unittest.TestCase):
    """The hindsight review's checks that read the clone."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = self.tmp.name
        self.env = {**os.environ, "GIT_AUTHOR_NAME": "Ann", "GIT_AUTHOR_EMAIL": "ann@example.org", "GIT_COMMITTER_NAME": "Ann",
                    "GIT_COMMITTER_EMAIL": "ann@example.org", "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_SYSTEM": os.devnull}
        git(self.repo, "init", "-q", "-b", "main", env=self.env)

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, path, text):
        full = os.path.join(self.repo, path)
        os.makedirs(os.path.dirname(full) or self.repo, exist_ok=True)
        with open(full, "w") as fh:
            fh.write(text)

    def over(self, **r):
        git(self.repo, "add", "-A", env=self.env)
        git(self.repo, "commit", "-q", "--allow-empty", "-m", "c", env=self.env)
        head = git(self.repo, "rev-parse", "HEAD")
        meta = {"run": {"commit": head}, **(r.pop("meta", {}))}
        return sorted(c["check"] for c in consistency.over(report(meta=meta, **r), self.repo)["complaints"])

    def test_an_island_of_declared_generator_output(self):
        for i in range(4):
            self.write(f"client/models/m{i}.py", '"""\n    API\n\n    Generated by OpenAPI Generator.\n\n    Do not edit the class manually.\n"""\nx = 1\n')
        self.write("client/api.py", "y = 1\n")
        f = finding("knowledge_islands", advice="Pair someone with Bo on client/ first.",
                    evidence={"islands": [{"area": "client/", "owner": "Bo"}]})
        self.assertEqual(self.over(findings=[f]), ["generated_owner"])

    def test_a_generator_manifest_declares_its_files(self):
        self.write("sdk/.openapi-generator/FILES", "a.py\nb.py\n")
        self.write("sdk/a.py", "x = 1\n")
        self.write("sdk/b.py", "x = 2\n")
        self.write("sdk/c.py", "x = 3\n")
        f = finding("bus_factor", advice="Pair someone with Bo on sdk/ first.", evidence={"areas": [{"area": "sdk/"}]})
        self.assertEqual(self.over(findings=[f]), ["generated_owner"], "two of three listed by the generator's manifest")

    def test_an_agent_file_that_points_elsewhere(self):
        self.write("AGENTS.md", "# Agents\n\nSee [CLAUDE.md](CLAUDE.md).\n")
        self.write("CLAUDE.md", "# Rules\n" + "".join(f"- rule {i}\n" for i in range(20)))
        f = finding("agent_instructions_drift", evidence={"files": [{"file": "AGENTS.md"}]})
        self.assertEqual(self.over(findings=[f]), ["agent_pointer"])
        g = finding("agent_instructions_drift", evidence={"files": [{"file": "CLAUDE.md"}]})
        self.assertEqual(self.over(findings=[g]), [], "a file of instructions is dated on its own")

    def test_a_source_file_the_structure_step_skipped_silently(self):
        self.write("engine/big.py", "x = 1\n" * 200_000)   # 1.2 MB
        self.write("engine/small.py", "y = 1\n")
        s = {"files": {"engine/small.py": {"language": "python"}}}
        self.assertEqual(self.over(structure=s), ["structure_skipped"])
        s["skipped"] = [{"file": "engine/big.py", "reason": "size"}]
        self.assertEqual(self.over(structure=s), [], "a skip the report names is not silent")

    def test_a_range_reported_as_a_version(self):
        self.write("tool/requirements.txt", "mcp>=1.0.0\nrequests==2.31.0  # pinned\n")
        rows = [{"name": "mcp", "version": "1.0.0", "source": "tool/requirements.txt"},
                {"name": "requests", "version": "2.31.0", "source": "tool/requirements.txt"}]
        f = finding("vulnerable_dependencies", evidence={"packages": rows})
        self.assertEqual(self.over(findings=[f]), ["dependency_floor"], "only the unpinned one")

class FromThePaperclipExport(unittest.TestCase):
    """The paperclip review's checks that need nothing but the export."""

    IDS = [{"name": "Ann", "email": "ann@x.org", "commits": 50, "authored": 50},
           {"name": "Tool", "email": "noreply@vendor.example", "commits": 40, "authored": 1},
           {"name": "Helper", "email": "noreply@vendor.example", "commits": 2, "authored": 0}]
    OWN = [{"entity": "src/a.py", "author": "Ann", "added": 100, "deleted": 0, "commits": 3},
           {"entity": "src/a.py", "author": "Tool", "added": 60, "deleted": 0, "commits": 3}]

    def test_a_tool_shown_as_an_owner(self):
        """paperclip's product agent, a trailer on 2,052 commits at a mailbox nine names share, was second owner everywhere."""
        r = report(meta={"identities": self.IDS}, ownership=self.OWN, theseus_authors={"Ann": 100, "Tool": 80})
        subjects = [c["subject"] for c in consistency.over(r)["complaints"] if c["check"] == "tool_owner"]
        self.assertEqual(len(subjects), 2, subjects)
        self.assertTrue(any("second" in s for s in subjects) and any("surviving" in s for s in subjects))

    def test_a_tool_kept_out_of_the_tables(self):
        r = report(meta={"identities": self.IDS}, ownership=self.OWN[:1], theseus_authors={"Ann": 100},
                   tools={"names": ["Tool", "Helper"]})
        self.assertNotIn("tool_owner", checks(r))

    def test_a_per_account_no_reply_address_is_a_person(self):
        ids = [{"name": "Ann", "email": "12+ann@users.noreply.example", "commits": 50, "authored": 50},
               {"name": "Ann B", "email": "12+ann@users.noreply.example", "commits": 5, "authored": 5}]
        self.assertEqual(consistency.harness_tools(report(meta={"identities": ids})), set())

    def test_one_name_credited_mostly_by_trailer_is_a_tool(self):
        ids = [{"name": "Agent", "email": "noreply@agent.example", "commits": 30, "authored": 2}]
        self.assertEqual(consistency.harness_tools(report(meta={"identities": ids})), {"Agent"})
        ids[0]["authored"] = 30
        self.assertEqual(consistency.harness_tools(report(meta={"identities": ids})), set(), "one person on their own no-reply mailbox")

    def test_a_people_row_with_negative_commits(self):
        """paperclip: an alias of Dotta with one co-authored commit carried 348 merges, shown as -348 commits."""
        ids = [{"name": "Bo", "email": "bo@x.org", "commits": 90, "authored": 90, "merges": 10},
               {"name": "Bo", "email": "bo@users.noreply.example", "commits": 1, "authored": 0, "merges": 10}]
        self.assertEqual(checks(report(meta={"identities": ids})), ["merge_total"])
        ids[1]["merges"] = 0
        self.assertEqual(checks(report(meta={"identities": ids})), [])

    def test_a_table_that_leads_with_a_suspect_span(self):
        """paperclip's Complex functions led with parseSkillFrontmatter, complexity 1036 over 4,232 lines: 19 real ones."""
        funcs = [{"file": "a.ts", "function": "parse", "ccn": 900, "nloc": 4000, "params": 1, "start": 10, "end": 4500, "suspect": "opens a block"},
                 {"file": "b.ts", "function": "run", "ccn": 80, "nloc": 300, "params": 0, "start": 5, "end": 320}]
        self.assertEqual(checks(report(functions=funcs)), ["suspect_lead"])
        del funcs[0]["suspect"]
        self.assertEqual(checks(report(functions=funcs)), [])

    def test_a_lead_whose_span_the_structure_step_disputes(self):
        funcs = [{"file": "b.ts", "function": "run", "ccn": 80, "nloc": 300, "params": 0, "start": 5, "end": 320}]
        f = finding("brain_methods", evidence={"functions": [{"file": "b.ts", "function": "run", "ccn": 80, "lines": 300, "start": 5}]})
        far = {"functions": [{"file": "b.ts", "name": "run", "start": 5, "end": 6000}]}
        near = {"functions": [{"file": "b.ts", "name": "run", "start": 5, "end": 330}]}
        self.assertEqual(checks(report(functions=funcs, findings=[f], structure=far)), ["suspect_lead", "suspect_lead"])
        self.assertEqual(checks(report(functions=funcs, findings=[f], structure=near)), [])

    def test_a_test_that_did_not_run_and_says_nothing(self):
        """paperclip: 7.5 months of history, the size-matched test needs 12, the rule still advertised it."""
        rule = {"id": "bug_magnets", "above_rate": {"test": "binomial", "min_history_months": 12}}
        f = {**finding("bug_magnets", "391 file(s) were fixed 3+ times in six months: a.py.", evidence={"count": 1}), "rule": rule}
        r = report(meta={"first_date": "2026-02-16", "last_date": "2026-09-30"}, findings=[f])
        self.assertEqual(checks(r), ["silent_precondition"])
        f["evidence"]["fix_rate"] = {"above_rate": []}
        self.assertEqual(checks(r), [], "the result is there, even an empty one")
        del f["evidence"]["fix_rate"]
        f["detail"] += " The size test did not run: too little history."
        self.assertEqual(checks(r), [], "the text says so")

    def test_trailer_keys_split_by_case_or_an_issue_id(self):
        r = report(provenance={"trailers": {"keys": {"Co-authored-by": 9, "Co-Authored-By": 4, "PAP-10182": 1}}})
        self.assertEqual(checks(r), ["trailer_case", "trailer_case"])
        r = report(provenance={"trailers": {"keys": {"Co-authored-by": 9, "Signed-off-by": 4}}})
        self.assertEqual(checks(r), [])


class WithThePaperclipRepository(unittest.TestCase):
    """The paperclip review's checks that read the clone."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = self.tmp.name
        self.env = {**os.environ, "GIT_AUTHOR_NAME": "Ann", "GIT_AUTHOR_EMAIL": "ann@example.org", "GIT_COMMITTER_NAME": "Ann",
                    "GIT_COMMITTER_EMAIL": "ann@example.org", "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_SYSTEM": os.devnull}
        git(self.repo, "init", "-q", "-b", "main", env=self.env)

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, path, text):
        full = os.path.join(self.repo, path)
        os.makedirs(os.path.dirname(full) or self.repo, exist_ok=True)
        with open(full, "w") as fh:
            fh.write(text)

    def commit(self, message="c"):
        git(self.repo, "add", "-A", env=self.env)
        git(self.repo, "commit", "-q", "--allow-empty", "-m", message, env=self.env)
        return git(self.repo, "rev-parse", "HEAD")

    def over(self, **r):
        head = self.commit()
        meta = {"run": {"commit": head}, **(r.pop("meta", {}))}
        return sorted(c["check"] for c in consistency.over(report(meta=meta, **r), self.repo)["complaints"])

    def test_the_merge_total_against_git(self):
        """paperclip: "725 in all" against 376 merges git has."""
        self.commit("one")
        git(self.repo, "checkout", "-q", "-b", "side", env=self.env)
        self.write("x", "1\n")
        self.commit("side")
        git(self.repo, "checkout", "-q", "main", env=self.env)
        git(self.repo, "merge", "-q", "--no-ff", "-m", "merge", "side", env=self.env)
        ids = [{"name": "Ann", "email": "ann@example.org", "commits": 5, "authored": 5, "merges": 2}]
        self.assertEqual(self.over(meta={"identities": ids}), ["merge_total"])
        ids[0]["merges"] = 1
        self.assertEqual(self.over(meta={"identities": ids}), [])

    def test_a_cargo_binary_only_the_tests_run(self):
        """paperclip's brain methods led with fake-codex-app-server.rs, which tests/ start through CARGO_BIN_EXE_."""
        self.write("crate/Cargo.toml", '[package]\nname = "core"\n\n[[bin]]\nname = "fake-server"\npath = "src/bin/fake-server.rs"\n')
        self.write("crate/src/bin/fake-server.rs", "fn main() {}\n")
        self.write("crate/src/bin/daemon.rs", "fn main() {}\n")
        self.write("crate/tests/it.rs", 'const B: &str = env!("CARGO_BIN_EXE_fake-server");\nconst D: &str = env!("CARGO_BIN_EXE_daemon");\n')
        self.write("crate/src/launch.rs", 'const D: &str = env!("CARGO_BIN_EXE_daemon");\n')
        fake = finding("brain_methods", evidence={"functions": [{"file": "crate/src/bin/fake-server.rs", "function": "main", "start": 1}]})
        daemon = finding("brain_methods", evidence={"functions": [{"file": "crate/src/bin/daemon.rs", "function": "main", "start": 1}]})
        self.assertEqual(self.over(findings=[fake]), ["test_double_lead"])
        self.assertEqual(self.over(findings=[daemon]), [], "named outside tests/ too")

    def test_a_secret_in_test_code(self):
        """paperclip's critical sat in scripts/smoke/…-e2e.sh; its two possible secrets below #[cfg(test)]."""
        self.write("scripts/smoke/gateway-e2e.sh", "curl -H 'Authorization: Bearer x'\n")
        self.write("src/state.rs", "fn a() {}\n\n#[cfg(test)]\nmod tests {\n    const P: &str = \"x\";\n}\n")
        self.write("src/live.rs", "const P: &str = \"x\";\n\n#[cfg(test)]\nmod tests {}\n")
        head = self.commit()
        rows = [{"rule": "curl-auth-header", "file": "scripts/smoke/gateway-e2e.sh", "line": 1, "commit": head, "confidence": "high"},
                {"rule": "generic-password", "file": "src/state.rs", "line": 5, "commit": head, "at_head": True, "head_line": 5},
                {"rule": "generic-password", "file": "src/live.rs", "line": 1, "commit": head, "at_head": True, "head_line": 1}]
        crit = finding("secrets_in_source", severity="critical", evidence={"files": ["scripts/smoke/gateway-e2e.sh"]})
        possible = finding("secrets_possible", evidence={"files": ["src/state.rs", "src/live.rs"]})
        self.assertEqual(self.over(findings=[crit, possible], secrets=rows), ["test_path_secret", "test_path_secret"])
        crit["evidence"]["files"] = []
        possible["evidence"]["files"] = ["src/live.rs"]
        self.assertEqual(self.over(findings=[crit, possible], secrets=rows), [], "above #[cfg(test)] is the code itself")

    def test_an_unused_dependency_the_lock_records_as_a_peer(self):
        """paperclip: @anthropic-ai/sdk and nice-grpc were peers of packages the manifests depend on;
        @tailwindcss/typography a Tailwind @plugin."""
        self.write("pnpm-lock.yaml", "lockfileVersion: '9.0'\n\nimporters:\n\n  .: {}\n\n  server:\n    dependencies:\n"
                   "      acp:\n        specifier: ^1\n        version: 1.0.0(sdk@2.0.0)\n      sdk:\n        specifier: ^2\n        version: 2.0.0\n"
                   "      lonely:\n        specifier: ^1\n        version: 1.0.0\n\npackages:\n\n  acp@1.0.0:\n    peerDependencies:\n      sdk: '>=2'\n")
        self.write("server/package.json", '{"dependencies": {"acp": "^1", "sdk": "^2", "lonely": "^1"}}')
        self.write("ui/package.json", '{"dependencies": {"typo": "^1"}}')
        self.write("ui/src/index.css", '@import "tailwindcss";\n@plugin "typo";\n')
        rows = [{"ecosystem": "npm", "manifest": "server/package.json", "package": "sdk"},
                {"ecosystem": "npm", "manifest": "ui/package.json", "package": "typo"},
                {"ecosystem": "npm", "manifest": "server/package.json", "package": "lonely"}]
        f = finding("unused_dependencies", evidence={"unused": rows})
        self.assertEqual(self.over(findings=[f]), ["peer_unused", "peer_unused"], "lonely is unused indeed")

    def test_an_unreferenced_file_a_package_declares(self):
        """paperclip's first ten "unreferenced" files: run by scripts, published through exports, loaded by new URL."""
        self.write("pkg/package.json", '{"scripts": {"replay": "tsx src/cli/replay.ts", "fmt": "prettier --write \'src/**/*.ts\'"}, '
                   '"exports": {".": "./dist/index.js", "./testing": "./dist/testing.js", "./tools/*": "./dist/tools/*.js"}}')
        for p in ("src/cli/replay.ts", "src/testing.ts", "src/tools/hash.ts", "src/orphan.ts", "src/fixtures/data.mjs"):
            self.write("pkg/" + p, "export {}\n")
        self.write("pkg/src/loader.test.ts", "const u = new URL('./fixtures/data.mjs', import.meta.url);\n")
        files = ["pkg/src/cli/replay.ts", "pkg/src/testing.ts", "pkg/src/tools/hash.ts", "pkg/src/fixtures/data.mjs"]
        f = finding("unreferenced_files", evidence={"files": files})
        self.assertEqual(self.over(findings=[f]).count("declared_reference"), 4)
        g = finding("unreferenced_files", evidence={"files": ["pkg/src/orphan.ts"]})
        self.assertNotIn("declared_reference", self.over(findings=[g]), "a formatter's glob does not load it")

    def test_a_go_module_that_requires_nothing(self):
        self.write("tools/shim/go.mod", "module example.org/shim\n\ngo 1.22\n")
        self.write("svc/go.mod", "module example.org/svc\n\ngo 1.22\n\nrequire example.org/x v1.0.0\n")
        empty = finding("lockfile_missing", evidence={"missing": [{"manifest": "tools/shim/go.mod", "expected": ["go.sum"]}]})
        real = finding("lockfile_missing", evidence={"missing": [{"manifest": "svc/go.mod", "expected": ["go.sum"]}]})
        self.assertEqual(self.over(findings=[empty]), ["lock_without_require"])
        self.assertEqual(self.over(findings=[real]), [])

    def test_a_vulnerable_lead_only_dev_dependencies_reach(self):
        """paperclip led with form-data, reached only through supertest, and buried multer, which the server imports."""
        self.write("pnpm-lock.yaml", "lockfileVersion: '9.0'\n\nimporters:\n\n  server:\n    dependencies:\n"
                   "      multer:\n        specifier: ^2\n        version: 2.2.0\n    devDependencies:\n"
                   "      supertest:\n        specifier: ^7\n        version: 7.2.2\n\npackages:\n\n  form-data@4.0.5:\n    resolution: {}\n\n"
                   "snapshots:\n\n  form-data@4.0.5: {}\n\n  multer@2.2.0: {}\n\n  supertest@7.2.2:\n    dependencies:\n      form-data: 4.0.5\n")
        dev = {"name": "form-data", "version": "4.0.5", "source": "pnpm-lock.yaml", "score": 8.7}
        run = {"name": "multer", "version": "2.2.0", "source": "pnpm-lock.yaml", "score": 7.5}
        f = finding("vulnerable_dependencies", evidence={"packages": [dev, run]})
        self.assertEqual(self.over(findings=[f]), ["dev_only_vuln_lead"])
        f = finding("vulnerable_dependencies", evidence={"packages": [run, dev]})
        self.assertEqual(self.over(findings=[f]), [])


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

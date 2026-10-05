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

    def test_a_tool_shown_as_an_owner_in_the_map_with_shares_in_their_own_columns(self):
        from unittest.mock import patch
        km = {"columns": ["area", "added", "main owner", "share", "second", "share"], "rows": [["src/", "160", "Ann", "62%", "Tool gone", "38%"]]}
        people = {"columns": ["author", "commits", "share", "surviving"], "rows": [["Ann", "50", "98%", "56%"], ["Tool", "1", "2%", "44%"]], "caption": None}
        r = report(meta={"identities": self.IDS})
        with patch.object(consistency, "_render", side_effect=lambda rep, section, full=True: km if section == "knowledge_section" else people):
            subjects = [c["subject"] for c in consistency.over(r)["complaints"] if c["check"] in ("tool_owner", "agent_owner")]
        self.assertEqual(subjects, ["knowledge map: Tool is second of 1 area(s), e.g. src/", "People: Tool holds 44% of the surviving code"],
                         "the name is found before the word gone, and the column under its shorter head")

    def test_the_checks_read_every_row_of_a_table_whatever_the_report_caps(self):
        """A tool past the fiftieth row of People and of the knowledge map is still a tool shown as an owner: the
        checks ask for the section whole (render.SECTION), which is every row whether or not --full caps its tables."""
        ids = [{"name": f"P{n:02d}", "email": f"p{n}@x.org", "commits": 200 - n, "authored": 200 - n} for n in range(70)] + self.IDS[1:]
        own = [{"entity": f"d{n:02d}/a.py", "author": f"P{n:02d}", "added": 1000 - n, "deleted": 0, "commits": 3} for n in range(70)]
        own += [{"entity": "zz/a.py", "author": "Ann", "added": 9, "deleted": 0, "commits": 3}, {"entity": "zz/a.py", "author": "Tool", "added": 5, "deleted": 0, "commits": 3}]
        r = report(meta={"identities": ids}, ownership=own, theseus_authors={"P00": 100, "Tool": 80})
        self.assertEqual(len(consistency._render(r, "people_section")["rows"]), 72)
        self.assertEqual(len(consistency._render(r, "knowledge_section")["rows"]), 71)
        subjects = [c["subject"] for c in consistency.over(r)["complaints"] if c["check"] == "tool_owner"]
        self.assertEqual(subjects, ["knowledge map: Tool is second of 1 area(s), e.g. zz/", "People: Tool holds 44% of the surviving code"])
        self.assertEqual(len(consistency._render(r, "people_section", full=False)["rows"]), 6, "a check that asks for the default's table gets it")

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
        """paperclip: an alias of Dotta with one co-authored commit carried 348 merges, shown as -348 commits.
        The check reads the People table as gitmole draws it, so it is fed a drawn table with such a row."""
        from unittest.mock import patch
        table = {"columns": ["author", "commits", "merges", "share"], "rows": [["Bo", "90", "10", "90%"], ["Bo", "-10", "10", "-9%"]]}
        with patch.object(consistency, "_render", return_value=table):
            self.assertEqual(checks(report()), ["merge_total"])
        table["rows"][1] = ["Bo", "0", "0", "0%"]
        with patch.object(consistency, "_render", return_value=table):
            self.assertEqual(checks(report()), [])

    def test_merges_counted_by_name_no_longer_draw_a_negative_row(self):
        """The same shape through gitmole's own table: since merges belong to an identity, not its display name,
        the co-author-only alias no longer shows the other row's merges as negative commits."""
        ids = [{"name": "Bo", "email": "bo@x.org", "commits": 90, "authored": 90, "merges": 10},
               {"name": "Bo", "email": "bo@users.noreply.example", "commits": 1, "authored": 0, "merges": 10}]
        self.assertNotIn("merge_total", checks(report(meta={"identities": ids})))

    def test_a_list_that_leads_with_a_suspect_span(self):
        """paperclip's Complex functions led with parseSkillFrontmatter, complexity 1036 over 4,232 lines: 19 real ones.
        A finding whose first function is that span is the same complaint, whatever order the table draws."""
        funcs = [{"file": "a.ts", "function": "parse", "ccn": 900, "nloc": 4000, "params": 1, "start": 10, "end": 4500, "suspect": "opens a block"},
                 {"file": "b.ts", "function": "run", "ccn": 80, "nloc": 300, "params": 0, "start": 5, "end": 320}]
        f = finding("brain_methods", evidence={"functions": [dict(funcs[0]), dict(funcs[1])]})
        self.assertEqual(checks(report(functions=funcs, findings=[f])), ["suspect_lead"])
        del funcs[0]["suspect"]
        self.assertEqual(checks(report(functions=funcs, findings=[f])), [])

    def test_the_table_no_longer_leads_with_a_suspect_span(self):
        """The same rows through gitmole's own table: suspect spans sort after every trusted row, so the table a
        reader sees leads with a function lizard measured cleanly."""
        funcs = [{"file": "a.ts", "function": "parse", "ccn": 900, "nloc": 4000, "params": 1, "start": 10, "end": 4500, "suspect": "opens a block"},
                 {"file": "b.ts", "function": "run", "ccn": 80, "nloc": 300, "params": 0, "start": 5, "end": 320}]
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


class FromTheSuperpowersExport(unittest.TestCase):
    """The superpowers review's checks that need the export and the default report drawn from it. The report
    and its tables are handed in as drawn, as the paperclip tests hand in a People table."""

    def drawn(self, lines, r=None, table=None):
        with mock.patch.object(consistency, "_default_report", return_value=lines), \
                mock.patch.object(consistency, "_render", return_value=table):
            return checks(r or report())

    def test_a_main_owner_tied_with_the_second(self):
        """superpowers: `.hermes-plugin/  Ada Sen (8%)  Caio Lopes (8%)`, alphabetical among twelve co-authors."""
        table = {"columns": ["area", "lines added", "main owner", "second"],
                 "rows": [["plugin/", "96", "Ann (8%)", "Bo (8%)"], ["src/", "900", "Bo (60%)", "Ann (gone) (30%)"], ["hooks/", "75", "Bo (100%)", "-"]]}
        self.assertEqual(self.drawn(None, table=table), ["tied_owner"])
        table["rows"][0][2] = "Ann (9%)"
        self.assertEqual(self.drawn(None, table=table), [])

    def test_a_tied_owner_is_read_with_the_share_in_its_own_column_too(self):
        """The map drawn with the shares beside the names and "gone" after a name: the same check, the same complaint."""
        table = {"columns": ["area", "added", "main owner", "share", "second", "share"],
                 "rows": [["plugin/", "96", "Ann", "8%", "Bo gone", "8%"], ["src/", "900", "Bo", "60%", "Ann gone", "30%"], ["hooks/", "75", "Bo", "100%", "-", "-"],
                          ["docs/", "40", "shared by 3", "33%", "-", "-"]]}
        with mock.patch.object(consistency, "_default_report", return_value=None), mock.patch.object(consistency, "_render", return_value=table):
            said = [c["subject"] for c in consistency.over(report())["complaints"] if c["check"] == "tied_owner"]
        self.assertEqual(said, ["knowledge map: plugin/ Ann and Bo, both 8%"])
        table["rows"][0][3] = "9%"
        self.assertEqual(self.drawn(None, table=table), [])

    def test_an_owner_cell_is_read_in_either_drawing(self):
        self.assertEqual(consistency._owner_names("Ann (gone) (30%)"), {"Ann"})
        self.assertEqual(consistency._owner_names("Ann (30%)"), {"Ann"})
        self.assertEqual(consistency._owner_names("Ann"), {"Ann"})
        self.assertEqual(consistency._owner_names("Ann gone"), {"Ann", "Ann gone"}, "a gone Ann, or somebody named so: the caller knows its names")
        km = {"columns": ["area", "added", "main owner", "share", "second", "share"]}
        self.assertEqual(consistency._owner_share(km, ["src/", "9", "Ann gone", "70%", "Bo", "30%"], "main owner"), ("Ann", "70"))
        self.assertEqual(consistency._owner_share(km, ["src/", "9", "Ann gone", "70%", "Bo", "30%"], "second"), ("Bo", "30"))
        self.assertIsNone(consistency._owner_share(km, ["src/", "9", "Ann", "100%", "-", "-"], "second"))
        old = {"columns": ["area", "lines added", "main owner", "second"]}
        self.assertEqual(consistency._owner_share(old, ["src/", "9", "Ann (gone) (70%)", "Bo (30%)"], "main owner"), ("Ann", "70"))
        self.assertIsNone(consistency._owner_share(old, ["src/", "9", "Ann (100%)", "-"], "second"))

    def test_the_merge_total_is_read_in_either_wording(self):
        self.assertEqual(consistency._MERGES_IN_ALL.search("commits and share leave out merges, which are counted apart (5,019 in all)").group(1), "5,019")
        self.assertEqual(consistency._MERGES_IN_ALL.search("share = of commits, without merges · 5,019 merges in all").group(2), "5,019")
        self.assertEqual(consistency._MERGES_IN_ALL.search("1 merge in all").group(2), "1")
        self.assertIsNone(consistency._MERGES_IN_ALL.search("share = of commits, without merges"))

    def test_a_finding_whose_area_owner_is_tied(self):
        own = [{"entity": "plugin/a.py", "author": "Ann", "added": 50}, {"entity": "plugin/b.py", "author": "Bo", "added": 50},
               {"entity": "src/a.py", "author": "Bo", "added": 500}]
        f = finding("knowledge_islands", evidence={"islands": [{"area": "plugin/", "owner": "Bo"}]})
        self.assertEqual(checks(report(ownership=own, findings=[f])), ["tied_owner"],
                         "the finding; the map gitmole draws of the same rows now reads \"shared by 2\" and names no owner")
        tied = {"columns": ["area", "lines added", "main owner", "second"], "rows": [["plugin/", "100", "Ann (50%)", "Bo (50%)"]]}
        self.assertEqual(self.drawn(None, report(ownership=own), tied).count("tied_owner"), 1, "a drawn map that still names a tied owner")
        own[1]["added"] = 60
        self.assertEqual(checks(report(ownership=own, findings=[f])), [])

    def test_a_row_lizard_ran_past_the_end_of(self):
        """superpowers: extractAndStripFrontmatter, 339 lines printed for the 36 the function spans, on the fifth row."""
        funcs = [{"file": "a.js", "function": "handle", "ccn": 16, "nloc": 43, "params": 2, "start": 5, "end": 50},
                 {"file": "b.js", "function": "strip", "ccn": 11, "nloc": 339, "params": 1, "start": 33, "end": 382}]
        table = {"columns": ["function", "file", "ccn", "lines", "params"], "rows": [["handle", "a.js", "16", "43", "2"], ["strip", "b.js", "11?", "339", "1"]]}
        spans = {"functions": [{"file": "a.js", "name": "handle", "start": 5, "end": 50}, {"file": "b.js", "name": "strip", "start": 33, "end": 68}]}
        self.assertEqual(self.drawn(None, report(functions=funcs, structure=spans), table).count("overrun_span"), 1)
        spans["functions"][1]["end"] = 300
        self.assertNotIn("overrun_span", self.drawn(None, report(functions=funcs, structure=spans), table))

    SMALL = {"coverage": {"scored": 17, "not a source type": 12}, "identities": [{"name": "Ann", "email": "ann@x.org", "commits": 80, "authored": 80},
                                                                               {"name": "Bo", "email": "bo@x.org", "commits": 20, "authored": 20}]}

    def test_a_truck_factor_not_computed_and_not_mentioned(self):
        """superpowers: 17 scored files under the floor of 20, one author of 78% of the commits, not a word."""
        r = report(meta=self.SMALL)
        self.assertEqual(self.drawn(["│ The truck factor and the churn counts leave the import out. │"], r), ["silent_measure"])
        self.assertEqual(self.drawn(["Truck factor not computed: 17 scored files, it needs 20"], r), [])

    def test_a_truck_factor_nobody_would_expect(self):
        spread = {**self.SMALL, "identities": [{"name": n, "email": n + "@x.org", "commits": 30, "authored": 30} for n in ("Ann", "Bo", "Cy")]}
        self.assertEqual(self.drawn(["nothing"], report(meta=spread)), [], "nobody authored half")
        self.assertEqual(self.drawn(["nothing"], report(meta={**self.SMALL, "coverage": {"scored": 40}})), [], "the pool is over the floor")
        f = finding("truck_factor", "Truck factor 1: without Bo, 9 files have no author left.", evidence={"removed": ["Bo"]})
        self.assertEqual(self.drawn(["nothing"], report(meta=self.SMALL, findings=[f])), [], "it was computed")

    def test_a_backtest_that_did_not_run_and_is_not_mentioned(self):
        r = report(meta={"backtest": {"status": "skipped", "reason": "too little history to backtest"}})
        self.assertEqual(self.drawn(["◎ Watch list", "  nothing to watch"], r), ["silent_measure"])
        self.assertEqual(self.drawn(["◎ Watch list", "  too little history to backtest"], r), [])
        self.assertEqual(self.drawn(["◎ Watch list"], report(meta={"backtest": {"status": "run", "until": "2026-03-01"}})), [])

    def test_most_of_the_tree_unscored_and_unsaid(self):
        """superpowers: 120 files of no source type against 17 scored, under "10,442 lines in 71 files"."""
        r = report(meta={"coverage": {"scored": 17, "not a source type": 120, "test file": 87}})
        self.assertEqual(self.drawn(["│ 10,442 lines in 71 files │"], r), ["coverage_unsaid"])
        self.assertEqual(self.drawn(["│ 10,442 lines in 71 files  ·  120 files not │", "│ scored (Markdown) │"], r), [], "wrapped, and still said")
        tests = report(meta={"coverage": {"scored": 17, "not a source type": 12, "test file": 87}})
        self.assertEqual(self.drawn(["│ 10,442 lines in 71 files │"], tests), [], "test files are in the tables")

    def test_one_followed_by_a_plural(self):
        """superpowers: "osv-scanner checked 1 packages in 1 lock file", in the findings panel and the footer."""
        lines = ["│   osv-scanner checked 1 packages in 1 lock file against the local database   │", "",
                 "  author   commits", "  Ann           11", "  files and commits leave out merges", "",
                 "Secrets: none found", "Dependencies: 1 ", "packages in 1 lock file, none vulnerable"]
        subjects = [c["subject"] for c in self.complaints(lines)]
        self.assertEqual(subjects, ["'1 packages' (2x)"])
        fine = ["│ 1 package in 1 lock file; 21 files, 1,001 commits, 0.1 lines, v1 files │", "  Ann   1", "  files hidden"]
        self.assertEqual(self.complaints(fine), [], "a row's last number is not the next line's count")

    def test_one_followed_by_a_plural_in_the_supply_chain_section(self):
        """The footer as the output plan's item A10 draws it: a titled label grid, then the closing lines. A row
        wraps under its own label, so a phrase split by the wrap is still read, and a row that ends in a number
        does not count the label of the row after it."""
        grid = ["│   osv-scanner checked 1 package in 1 lock file   │", "",
                "⛨ Supply chain",
                "  secrets       none in source files (secrets.json) · at HEAD 18 places, 1",
                "                places high confidence",
                "  dependencies  1 packages in 1 lock file, database 2026-09-30 · 1",
                "                lock files held 1",
                "  secrets       a second row whose label follows a row that ends in 1",
                "",
                "--full adds 1 section: Timeline. 15 of 18 steps ran; --plots runs the other 1",
                "steps.", "/tmp/out"]
        self.assertEqual(sorted(c["subject"] for c in self.complaints(grid)), ["'1 lock files' (1x)", "'1 packages' (1x)", "'1 places' (1x)", "'1 steps' (1x)"])
        self.assertEqual(self.complaints(["Supply chain", "  signing       1", "  dependencies  none vulnerable"]), [], "the title without a pictogram, and no closing lines")
        old = ["Secrets: none found", "Dependencies: 1 ", "packages in 1 lock file, none vulnerable"]
        self.assertEqual([c["subject"] for c in self.complaints(old)], ["'1 packages' (1x)"], "the drawing before A10 is read as it was")

    def test_one_followed_by_a_plural_in_a_header_and_findings_without_their_boxes(self):
        """The header and the Findings as the output plan's item A11 draws them: a title line over a label grid,
        and a title line over entries that each start at column 1 with their mark. A phrase the wrap split is
        still read, within a header row and within an entry; a header row that ends in a number does not count
        the label of the row after it; and a table is still read a line at a time."""
        bare = ["demo · branch main @ 296080c0",
                "  history   21 commits · 2026-01-01 → 2026-09-01 · 1",
                "            identities",
                "  code      5,421 lines · Python · 23% surviving from 1",
                "  commits   16% are fixes · 84 reverts",
                "  left out  1 sweeping",
                "            commits, not counted in churn",
                "",
                "Findings · 1 warning ▲ · 1 note ●",
                "▲ Vulnerable dependencies",
                "  osv-scanner checked 1",
                "  packages in 1 lock file. By lock file:",
                "    go.mod: 1",
                "      places, no fix published",
                "  ↳ Upgrade it first; it is in 1",
                "    lock files.",
                "● Bug magnets (not measured yet): 1",
                "  files were fixed 3 or more times",
                "",
                "◎ Watch list · 1 of 1, ranked by changes × lines of code",
                "  file  changes",
                "  ─────────────",
                "  a.py        1",
                "  files hidden: none",
                "",
                "Supply chain",
                "  secrets       none found"]
        self.assertEqual(sorted(c["subject"] for c in self.complaints(bare)),
                         ["'1 files' (1x)", "'1 identities' (1x)", "'1 lock files' (1x)", "'1 packages' (1x)", "'1 places' (1x)"])
        fine = ["demo", "  history   1 commit · 1 identity · 1", "  files     1 tracked", "", "Findings · 1 note ●", "● One (not measured yet): 1",
                "● files is the next entry's first word", "", "Nothing here is a table:", "  the count is 1", "  files in all"]
        self.assertEqual(self.complaints(fine), [], "a row's last number, and an entry's, is not the next one's count; nor is a table line's")
        boxed = ["╭─ demo ──╮", "│ history   1 │", "│ commits │", "╰─────────╯", "╭─ Findings ─╮", "│ ▲ checked 1 │", "│   packages  │", "╰────────────╯"]
        self.assertEqual(sorted(c["subject"] for c in self.complaints(boxed)), ["'1 commits' (1x)", "'1 packages' (1x)"], "the boxes are read as they were")

    def complaints(self, lines):
        with mock.patch.object(consistency, "_default_report", return_value=lines):
            return consistency.plural_one(report(), [])

    def test_the_default_report_is_drawn_from_an_export(self):
        """The text checks read gitmole's own default report: an export render.report can draw gives lines, one
        it cannot gives None and the checks say nothing."""
        self.assertIsNone(consistency._default_report(report(), []))
        self.assertEqual(checks(report(meta={"backtest": {"status": "skipped"}})), [])


class WithTheSuperpowersRepository(WithThePaperclipRepository):
    """The superpowers review's checks that read the clone."""

    test_the_merge_total_against_git = test_a_cargo_binary_only_the_tests_run = test_a_secret_in_test_code = None
    test_an_unused_dependency_the_lock_records_as_a_peer = test_an_unreferenced_file_a_package_declares = None
    test_a_go_module_that_requires_nothing = test_a_vulnerable_lead_only_dev_dependencies_reach = None

    def missing(self, *manifests):
        return finding("lockfile_missing", evidence={"missing": [{"manifest": m, "expected": ["x.lock"]} for m in manifests]})

    def test_a_manifest_that_declares_nothing(self):
        """superpowers' root package.json: a name, a version and a `main`."""
        self.write("package.json", '{"name": "x", "version": "1.0.0", "main": "index.js", "dependencies": {}}')
        self.write("app/package.json", '{"name": "app", "devDependencies": {"left-pad": "^1"}}')
        self.write("ws/package.json", '{"name": "ws", "workspaces": ["packages/*"]}')
        self.write("tool/Cargo.toml", '[package]\nname = "tool"\n')
        self.write("svc/Cargo.toml", '[package]\nname = "svc"\n\n[target.x.dev-dependencies]\nserde = "1"\n')
        self.write("empty/Gemfile", 'source "https://rubygems.org"\n')
        self.write("web/Gemfile", 'source "https://rubygems.org"\ngem "rack"\n')
        self.write("py/Pipfile", "[packages]\n\n[requires]\npython_version = \"3\"\n")
        self.write("php/composer.json", '{"require": {"monolog/monolog": "^3"}}')
        self.write("broken/package.json", "{not json")
        self.assertEqual(self.over(findings=[self.missing("package.json", "tool/Cargo.toml", "empty/Gemfile", "py/Pipfile")]), ["lock_declares_nothing"] * 4)
        declared = self.missing("app/package.json", "ws/package.json", "svc/Cargo.toml", "web/Gemfile", "php/composer.json", "broken/package.json", "gone/package.json")
        self.assertEqual(self.over(findings=[declared]), [])

    GAP = {"controls": [{"control": "OSPS-GV-03.01", "result": "gap", "evidence": "no contribution guide"}]}

    def test_a_readme_heading_about_contributing(self):
        """superpowers: OSPS-GV-03.01 a gap, and "## Contributing" at line 375 of the README."""
        self.write("README.md", "# X\n" + "filler\n" * 2000 + "\n## Contributing\n\nOpen a pull request.\n")
        self.assertEqual(self.over(osps=self.GAP), ["contributing_heading"])
        self.assertEqual(self.over(osps={"controls": [{"control": "OSPS-GV-03.01", "result": "met"}]}), [], "the report did not say so")

    def test_a_finding_that_says_so_and_an_rst_heading(self):
        self.write("HACKING.rst", "Hacking\n=======\n\nHow to contribute\n-----------------\n\nSend patches.\n")
        f = finding("repo_policy", "No contribution guide (CONTRIBUTING.md).")
        head = self.commit()
        one = consistency.over(report(meta={"run": {"commit": head}}, findings=[f]), self.repo)
        self.assertEqual([(c["check"], c["rule"]) for c in one["complaints"]], [("contributing_heading", "repo_policy")])

    def test_mentions_of_contributors_are_not_a_guide(self):
        self.write("README.md", "# X\n\n## Contributors\n\nThanks to everyone who contributed. See contributing notes elsewhere.\n")
        self.write("CHANGELOG.md", "# Changes\n\n## Contributing guide rewritten\n")
        self.write("docs/guide.md", "# Contributing\n")
        self.assertEqual(self.over(osps=self.GAP), [], "a thanks list, a changelog entry and a file below the root")

    def script(self, path, text, executable=True):
        self.write(path, text)
        if executable:
            os.chmod(os.path.join(self.repo, path), 0o755)

    def test_an_executable_script_no_table_carries(self):
        """superpowers: hooks/session-start, mode 755, `#!/usr/bin/env bash`, no extension, 31 commits, in no table."""
        self.script("hooks/session-start", "#!/usr/bin/env bash\necho hi\n")
        self.script("scripts/build.sh", "#!/bin/sh\nmake\n")                      # scored: the size step has it
        self.script("tests/run-all", "#!/bin/sh\n")                                # a test path
        self.script("vendor/tool/run", "#!/bin/sh\n")                              # vendored
        self.script("gen/out", "#!/bin/sh\n")                                      # the run lists it as generated
        self.script("bin/blob", "\x7fELF not a script\n")                          # executable, no #!
        self.script("notes/plan", "#!/bin/sh\n", executable=False)                 # a #! without the bit
        r = {"size": {"files": {"scripts/build.sh": {"code": 2}}}, "meta": {"generated": ["gen/out"]}}
        self.assertEqual(self.over(**r), ["unscored_executable"])
        r["revisions"] = [{"entity": "hooks/session-start", "n-revs": 31}]
        self.assertEqual(self.over(**r), [], "the history tables have it")

    IMPORT = ("1 commit brought code in without changing any: {h} by Ann (2 files). Ownership leaves it out, "
              "and the code-age pass credits its surviving lines to nobody.")

    def test_an_import_nothing_survives_of(self):
        """superpowers: 7446c84 bundled node_modules, 7619570 removed it two days later."""
        self.write("index.js", "z\n")
        self.commit("first")
        self.write("node_modules/a/index.js", "x\n")
        self.write("node_modules/b/index.js", "y\n")
        imported = self.commit("bundle")
        f = finding("import_commits", self.IMPORT.format(h=imported[:7]), evidence={"commits": [{"hash": imported[:7], "files": 2}]})
        self.assertEqual(self.over(findings=[f]), [], "still in the tree")
        git(self.repo, "rm", "-q", "-r", "node_modules/a", env=self.env)
        self.assertEqual(self.over(findings=[f]), [], "half of it is still in the tree")
        git(self.repo, "rm", "-q", "-r", "node_modules", env=self.env)
        self.assertEqual(self.over(findings=[f]), ["dead_import"])
        f["detail"] = f"1 commit brought code in: {imported[:7]} by Ann (2 files), removed since; nothing of it is in the tree."
        self.assertEqual(self.over(findings=[f]), [], "the text says so")

    def fix(self, path, n, date):
        self.write(path, f"{n}\n")
        git(self.repo, "add", "-A", env=self.env)
        git(self.repo, "commit", "-q", "-m", f"fix {n}", env={**self.env, "GIT_AUTHOR_DATE": date + "T12:00:00", "GIT_COMMITTER_DATE": date + "T12:00:00"})
        return git(self.repo, "rev-parse", "--short", "HEAD")

    def test_fixes_that_are_one_episode(self):
        """superpowers: stop-server.sh's four recent fixes all in ISO week 24."""
        self.write("c.sh", "c\n")
        burst = [self.fix("a.sh", n, d) for n, d in enumerate(["2026-06-08", "2026-06-09", "2026-06-10", "2026-06-16"])]
        spread = [self.fix("b.sh", n, d) for n, d in enumerate(["2026-06-08", "2026-06-17", "2026-07-01"])]
        f = finding("bug_magnets", evidence={"files": [{"file": "a.sh", "recent_fixes": 4}, {"file": "b.sh", "recent_fixes": 3}, {"file": "c.sh", "recent_fixes": 3}]})
        history = {"a.sh": {"recent": burst}, "b.sh": {"recent": spread}}
        self.assertEqual(self.over(findings=[f], fix_history=history), ["fix_episode"], "a.sh: two weeks; b.sh: three; c.sh: no commits listed")
        self.assertEqual(self.over(findings=[f]), [], "an export that lists no fix commits is not judged")


UNIVER_CHECKS = {"drift_specifiers_agree", "drift_unclaimed", "private_critical", "published_demoted", "trojan_inert", "trojan_missed",
                 "action_order", "noreply_split", "split_density", "locale_magnet"}


class FromTheUniverExport(unittest.TestCase):
    """The univer review's checks that need nothing but the export (h4, h6, h7)."""

    def test_a_forge_address_whose_login_is_another_identity(self):
        """univer: "Univer" commits as 68851825+DR-Univer@users.noreply.github.com, and "DR-Univer" is another identity."""
        ids = [{"name": "Univer", "email": "68851825+DR-Univer@users.noreply.github.com", "aliases": []},
               {"name": "DR-Univer", "email": "wbfsa@example.org", "aliases": []}]
        self.assertEqual(checks(report(meta={"identities": ids})), ["noreply_split"])
        ids[1]["name"] = "Dr Univer"   # not one word: a person's name, not an account
        self.assertEqual(checks(report(meta={"identities": ids})), [])

    def test_merged_or_bare_no_reply_addresses_are_not_split(self):
        ids = [{"name": "bob-example", "email": "bob@example.org", "aliases": [{"name": "Bob", "email": "9999+bob-example@users.noreply.github.com"}]},
               {"name": "noreply", "email": "noreply@github.com", "aliases": []},
               {"name": "Cy", "email": "noreply@github.com", "aliases": []}]
        self.assertEqual(checks(report(meta={"identities": ids})), [])

    def growth(self, then, now, advice="Split a.ts before the next change; its complexity grew 418% in a year."):
        f = finding("complexity_growth", "3 of the 10 top source hotspots grew.", advice, {"grown": [{"file": "a.ts", "growth_pct": 418}]}, "warning")
        return report(meta={"last_date": "2026-10-04"}, findings=[f], trend={"files": {"a.ts": [["2025-08-30", *then], ["2026-10-04", *now]]}})

    def test_split_advised_for_a_file_that_grew_with_its_size(self):
        """univer's doc-skeleton.ts: summed complexity 279 -> 1,446 (+418%), per line 0.268 -> 0.298 (+11%)."""
        self.assertEqual(checks(self.growth((279, 1042), (1446, 4858))), ["split_density"])

    def test_split_advised_for_a_file_that_grew_denser(self):
        """layout-ruler.ts: per line 0.260 -> 0.381 (+47%), past the floor: the advice stands."""
        self.assertEqual(checks(self.growth((294, 1129), (1078, 2828))), [])
        self.assertEqual(checks(self.growth((279, 1042), (1446, 4858), advice="Look at a.ts.")), [], "no Split advised")

    def magnets(self, *paths, count=None):
        f = finding("bug_magnets", evidence={"count": count or len(paths), "files": []}, severity="warning")
        f["rule"]["min_recent"] = 3
        return report(findings=[f], fixes=[{"entity": p, "recent-fixes": 3, "n-fixes": 9} for p in paths])

    def test_locale_files_among_the_bug_magnets(self):
        """univer: 82 of 287 magnet rows were translations (ru-RU.ts, zh-TW.ts), touched by every fix that adds a string."""
        r = self.magnets("packages/ui/src/locale/ru-RU.ts", "packages/ui/src/locale/zh-Hant-TW.ts", "po/es_419.po", "app/i18n/de.json", "src/set.ts")
        self.assertEqual(checks(r), ["locale_magnet"])
        self.assertIn("4 of 5", consistency.over(r)["complaints"][0]["subject"])

    def test_names_that_are_not_locales(self):
        """set.ts and api.ts outside a locale directory, and index.ts inside one, are code."""
        self.assertEqual(checks(self.magnets("src/set.ts", "src/api.ts", "src/locale/index.ts", "src/locale/de.test.ts")), [])


class WithTheUniverRepository(WithThePaperclipRepository):
    """The univer review's checks that read the clone (h1, h2, h3, h5)."""

    test_the_merge_total_against_git = test_a_cargo_binary_only_the_tests_run = test_a_secret_in_test_code = None
    test_an_unused_dependency_the_lock_records_as_a_peer = test_an_unreferenced_file_a_package_declares = None
    test_a_go_module_that_requires_nothing = test_a_vulnerable_lead_only_dev_dependencies_reach = None

    def mine(self, **r):
        return [c for c in self.over(**r) if c in UNIVER_CHECKS]

    LOCK = ("lockfileVersion: '9.0'\n\noverrides:\n  left-pad: 2.0.0\n\nimporters:\n\n  .:\n    devDependencies:\n"
            "      tool:\n        specifier: ^3.0.0\n        version: 3.1.0\n\n  packages/core:\n    dependencies:\n"
            "      lib:\n        specifier: ^1.0.0\n        version: 1.2.0\n      left-pad:\n        specifier: 2.0.0\n        version: 2.0.0\n\n"
            "  packages/ui:\n    dependencies:\n      lib:\n        specifier: ^1.0.0\n        version: 1.2.0\n")

    def drift(self, *manifests, count=None):
        rows = [{"lockfile": "pnpm-lock.yaml", "manifest": m, "manifest_date": "2026-09-29", "lockfile_date": "2026-09-24",
                 "changes": [{"commit": "f" * 40, "date": "2026-09-29"}]} for m in manifests]
        f = finding("lockfile_drift", evidence={"count": count or len(rows), "drift": rows}, severity="warning")
        return {"findings": [f] if rows else [], "hygiene": {"lockfiles": {"drift": rows, "drift_count": count or len(rows)}}}

    def test_drift_claimed_on_a_version_bump_pnpm_does_not_lock(self):
        """univer's 82: every change was the release's `version`, which pnpm's importers do not record. A
        left-pad the lock's overrides pin is not a difference either."""
        self.write("pnpm-lock.yaml", self.LOCK)
        self.write("package.json", '{"private": true, "devDependencies": {"tool": "^3.0.0"}}')
        self.write("packages/core/package.json", '{"name": "core", "version": "0.2.0", "dependencies": {"lib": "^1.0.0", "left-pad": "^1"}}')
        self.write("packages/ui/package.json", '{"name": "ui", "version": "0.2.0", "dependencies": {"lib": "^1.0.0"}}')
        self.assertEqual(self.mine(**self.drift("packages/core/package.json", "packages/ui/package.json")),
                         ["drift_specifiers_agree", "drift_specifiers_agree"])
        self.assertEqual(self.mine(**self.drift()), [], "nothing claimed, nothing differs")

    def test_drift_on_a_real_change_both_ways(self):
        """A dependency the manifest changed is drift: claimed, no complaint; unclaimed, a complaint, unless the
        claims were cut short by the run's cap."""
        self.write("pnpm-lock.yaml", self.LOCK)
        self.write("package.json", '{"private": true, "devDependencies": {"tool": "^3.0.0"}}')
        self.write("packages/core/package.json", '{"dependencies": {"lib": "^1.0.0", "left-pad": "2.0.0"}}')
        self.write("packages/ui/package.json", '{"dependencies": {"lib": "^2.0.0"}}')
        self.assertEqual(self.mine(**self.drift("packages/ui/package.json")), [])
        self.assertEqual(self.mine(**self.drift()), ["drift_unclaimed"])
        self.assertEqual(self.mine(**self.drift("packages/core/package.json")), ["drift_specifiers_agree", "drift_unclaimed"])
        self.assertEqual(self.mine(**self.drift("packages/core/package.json", count=60)), ["drift_specifiers_agree"], "claims capped")

    def test_a_v5_lock_records_specifiers_in_a_block(self):
        self.write("pnpm-lock.yaml", "lockfileVersion: 5.4\n\nimporters:\n\n  app:\n    specifiers:\n      lib: ^1.0.0\n"
                   "    dependencies:\n      lib: 1.2.0\n")
        self.write("app/package.json", '{"version": "2.0.0", "dependencies": {"lib": "^1.0.0"}}')
        self.assertEqual(self.mine(**self.drift("app/package.json")), ["drift_specifiers_agree"])
        self.write("app/package.json", '{"dependencies": {"lib": "^1.0.0", "more": "^1"}}')
        self.assertEqual(self.mine(**self.drift("app/package.json")), [])

    VULN_LOCK = ("lockfileVersion: '9.0'\n\nimporters:\n\n  .: {}\n\n  common/shared:\n    dependencies:\n"
                 "      immutable:\n        specifier: ^5\n        version: 5.1.2\n\n  packages/protocol:\n    dependencies:\n"
                 "      grpc:\n        specifier: ^1\n        version: 1.14.0\n\npackages:\n\n  grpc@1.14.0:\n    resolution: {}\n\n"
                 "snapshots:\n\n  grpc@1.14.0:\n    dependencies:\n      protobufjs: 7.5.5\n\n  protobufjs@7.5.5: {}\n\n  immutable@5.1.2: {}\n")

    def vulns(self, rows, severity="critical"):
        return {"findings": [finding("vulnerable_dependencies", evidence={"packages": rows}, severity=severity)],
                "dependencies": {"vulnerable": rows}}

    def test_a_critical_shipped_only_by_a_private_package(self):
        """univer's ✖: "common/shared/package.json bin ships that lock", and common/shared declares private."""
        self.write("pnpm-lock.yaml", self.VULN_LOCK)
        self.write("package.json", '{"private": true}')
        self.write("common/shared/package.json", '{"private": true, "bin": {"x": "cli.js"}}')
        self.write("packages/protocol/package.json", '{"name": "@u/protocol"}')
        row = {"name": "immutable", "version": "5.1.2", "source": "pnpm-lock.yaml", "score": 9.8, "runtime": True,
               "deploys": ["common/shared/package.json bin"]}
        self.assertEqual(self.mine(**self.vulns([row])), ["private_critical"])
        row["deploys"] = ["common/shared/package.json bin", "common/shared/Dockerfile"]
        self.assertEqual(self.mine(**self.vulns([row])), [], "a Dockerfile ships it")
        self.write("common/shared/package.json", '{"bin": {"x": "cli.js"}}')
        row["deploys"] = ["common/shared/package.json bin"]
        self.assertEqual(self.mine(**self.vulns([row])), [], "a published package's bin ships")

    def test_a_published_members_runtime_dependency_stays_at_a_warning(self):
        """protobufjs, through @grpc/grpc-js from packages/protocol (published): after a fix it may leave the
        critical, never fall to a note or to development-only."""
        self.write("pnpm-lock.yaml", self.VULN_LOCK)
        self.write("package.json", '{"private": true}')
        self.write("common/shared/package.json", '{"private": true}')
        self.write("packages/protocol/package.json", '{"name": "@u/protocol"}')
        reached = {"name": "protobufjs", "version": "7.5.5", "source": "pnpm-lock.yaml", "score": 8.1, "runtime": True}
        private = {"name": "immutable", "version": "5.1.2", "source": "pnpm-lock.yaml", "score": 9.8, "runtime": False}
        self.assertEqual(self.mine(**self.vulns([reached, private], "warning")), [], "the private member's row may be development-only")
        self.assertEqual(self.mine(**self.vulns([reached], "info")), ["published_demoted"])
        self.assertEqual(self.mine(**self.vulns([{**reached, "runtime": False}], "warning")), ["published_demoted"])

    def trojan(self, rows, count=None):
        return {"findings": [finding("trojan_source", evidence={"mixed_script": rows, "bidi": []}, severity="warning")] if rows else [],
                "hygiene": {"trojan": {"mixed_script": rows, "mixed_script_count": len(rows) if count is None else count, "bidi": [], "bidi_count": 0}}}

    def test_mixed_tokens_that_are_no_identifier(self):
        """univer's three: a regex class range and Russian prose naming a function ZТЕСТ."""
        self.write("src/tools.ts", "const ok = /^[A-Za-zА-Яа-яЁё_]/.test(name);\n// zА in a comment\n")
        self.write("src/ru-RU.ts", "export default {\n  ZTEST: { description: 'Возвращает значение. функция ZТЕСТ возвращает' },\n};\n")
        rows = [{"file": "src/tools.ts", "line": 1, "token": "zА", "scripts": ["CYRILLIC", "LATIN"]},
                {"file": "src/tools.ts", "line": 2, "token": "zА", "scripts": ["CYRILLIC", "LATIN"]},
                {"file": "src/ru-RU.ts", "line": 2, "token": "ZТЕСТ", "scripts": ["CYRILLIC", "LATIN"]}]
        self.assertEqual(self.mine(**self.trojan(rows)), ["trojan_inert"] * 3)

    def test_homoglyphs_in_code_and_in_a_bare_literal_are_real(self):
        """`pаssword = 1` and `role === "аdmin"`: the attack itself, named or not."""
        self.write("src/auth.ts", 'let pаssword = 1;\nif (role === "аdmin") {}\nconst t = `${pаssword} and Слово`;\n')
        rows = [{"file": "src/auth.ts", "line": 1, "token": "pаssword", "scripts": ["CYRILLIC", "LATIN"]},
                {"file": "src/auth.ts", "line": 2, "token": "аdmin", "scripts": ["CYRILLIC", "LATIN"]},
                {"file": "src/auth.ts", "line": 3, "token": "pаssword", "scripts": ["CYRILLIC", "LATIN"]}]
        self.assertEqual(self.mine(**self.trojan(rows)), [])
        self.assertEqual(self.mine(**self.trojan(rows[1:])), ["trojan_missed"], "a fix that drops the code row is caught")
        self.assertEqual(self.mine(**self.trojan(rows[1:], count=5)), [], "rows capped: not judged")

    def test_a_homoglyph_outside_the_checked_code_is_not_missed(self):
        self.write("src/a.ts", "// pаssword in a comment\nconst r = /[a-zа-я]/;\n")
        self.write("tests/a.test.ts", "let pаssword = 1;\n")
        self.write("docs/a.md", "pаssword\n")
        self.assertEqual(self.mine(**self.trojan([])), [])

    def actions(self, advice):
        f = finding("unpinned_actions", advice=f"Pin {advice} to a full commit SHA first, with the tag in a comment.", severity="warning")
        return {"findings": [f], "hygiene": {"actions": {"origin": {"host": "github.com", "owner": "dream-num"}}}}

    def test_the_pinning_advice_leads_with_what_ranks_first(self):
        """univer named codecov/codecov-action@v7 while jikkai/sync-gitee@main was given secrets.GITEE_PASSWORD."""
        self.write(".github/workflows/ci.yml", "on: push\njobs:\n  test:\n    runs-on: ubuntu-latest\n    steps:\n"
                   "      - uses: actions/checkout@v4\n      - uses: codecov/codecov-action@v7\n        with:\n          files: x\n")
        self.write(".github/workflows/sync.yml", "on: push\njobs:\n  sync:\n    runs-on: ubuntu-latest\n    steps:\n"
                   "      - name: mirror\n        uses: jikkai/sync-gitee@main\n        with:\n          password: ${{ secrets.GITEE_PASSWORD }}\n"
                   "      - uses: dream-num/own@main\n")
        self.assertEqual(self.mine(**self.actions("codecov/codecov-action@v7")), ["action_order"])
        self.assertEqual(self.mine(**self.actions("jikkai/sync-gitee@main")), [])

    def test_a_job_granted_id_token_ranks_before_one_that_is_not(self):
        self.write(".github/workflows/release.yml", "on: push\npermissions:\n  contents: read\njobs:\n  plain:\n    runs-on: x\n    steps:\n"
                   "      - uses: other/lint@v2\n  publish:\n    runs-on: x\n    permissions:\n      id-token: write\n    steps:\n"
                   "      - uses: pnpm/setup@v2\n      - uses: other/pinned@" + "a" * 40 + "\n")
        self.assertEqual(self.mine(**self.actions("other/lint@v2")), ["action_order"])
        self.assertEqual(self.mine(**self.actions("pnpm/setup@v2")), [])


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

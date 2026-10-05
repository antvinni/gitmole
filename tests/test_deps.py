import json
import os
import stat
import subprocess
import sys
import tempfile
import unittest

from gitmole import deps

SCRIPT = deps.__file__


def vuln(id_, aliases=(), summary="", fixed=None, name="lodash", severity_word=None, max_severity=None):
    v = {"id": id_, "aliases": list(aliases), "summary": summary,
         "affected": [{"package": {"name": name, "ecosystem": "npm"},
                       "ranges": [{"type": "SEMVER", "events": [{"introduced": "0"}] + ([{"fixed": fixed}] if fixed else [])}]}]}
    if severity_word:
        v["database_specific"] = {"severity": severity_word}
    return v


def package(name, version, vulns, ecosystem="npm", max_severity="7.5"):
    return {"package": {"name": name, "version": version, "ecosystem": ecosystem}, "vulnerabilities": vulns,
            "groups": [{"ids": [v["id"] for v in vulns], "aliases": [], "max_severity": max_severity}] if vulns else []}


def report(cwd="/repo"):
    return {"results": [
        {"source": {"path": f"{cwd}/frontend/yarn.lock", "type": "lockfile"},
         "packages": [package("lodash", "4.17.15", [vuln("GHSA-1", ["CVE-2021-23337"], "Command injection", fixed="4.17.21"),
                                                     vuln("GHSA-2", ["CVE-2020-8203"], "Prototype pollution", fixed="4.17.19")], max_severity="7.2"),
                      package("left-pad", "1.3.0", []),
                      package("minimist", "0.0.8", [vuln("GHSA-3", ["CVE-2021-44906"], fixed="1.2.6", name="minimist")], max_severity="9.8")]},
        {"source": {"path": f"{cwd}/uv.lock", "type": "lockfile"},
         "packages": [package("requests", "2.31.0", [], ecosystem="PyPI")]},
    ]}


class Summarise(unittest.TestCase):
    def test_one_row_per_vulnerable_package_worst_first_with_relative_lock_paths(self):
        out = deps.summarise(report(), "/repo")
        self.assertEqual(out["status"], "scanned")
        self.assertEqual(out["sources"], [{"path": "frontend/yarn.lock", "packages": 3}, {"path": "uv.lock", "packages": 1}])
        self.assertEqual(out["packages"], 4)
        self.assertEqual([r["name"] for r in out["vulnerable"]], ["minimist", "lodash"], "highest score first")
        lodash = out["vulnerable"][1]
        self.assertEqual(lodash, {"name": "lodash", "version": "4.17.15", "ecosystem": "npm", "source": "frontend/yarn.lock",
                                  "ids": ["GHSA-1", "GHSA-2"], "aliases": ["CVE-2020-8203", "CVE-2021-23337"], "advisories": 1,
                                  "score": 7.2, "severity": "high", "summary": "Command injection", "fixed": "4.17.19", "malicious": False})
        self.assertEqual(out["vulnerable"][0]["severity"], "critical")
        self.assertNotIn("affected", json.dumps(out), "the advisories' full text stays out of the output directory")

    def test_a_path_outside_the_clone_is_kept_as_given(self):
        out = deps.summarise(report(), "/elsewhere")
        self.assertEqual(out["sources"][0]["path"], "/repo/frontend/yarn.lock")

    def test_fixed_version_is_the_smallest_above_the_installed_one(self):
        vulns = [vuln("A", fixed="4.17.21"), vuln("B", fixed="4.17.19"), vuln("C", fixed="4.10.0")]
        self.assertEqual(deps.fixed_version(vulns, "lodash", "4.17.15"), "4.17.19")
        self.assertEqual(deps.fixed_version(vulns, "lodash", "5.0.0"), "4.17.21", "nothing above: the highest named")
        self.assertIsNone(deps.fixed_version([vuln("D")], "lodash", "1.0.0"), "no advisory names a fix")
        self.assertIsNone(deps.fixed_version(vulns, "other", "1.0.0"), "another package's ranges do not apply")

    def test_severity_falls_back_to_the_advisorys_own_word(self):
        pkg = package("x", "1", [vuln("E", severity_word="MODERATE")], max_severity="")
        row = deps.summarise({"results": [{"source": {"path": "a.lock"}, "packages": [pkg]}]}, "/r")["vulnerable"][0]
        self.assertEqual((row["score"], row["severity"]), (None, "medium"))
        pkg = package("x", "1", [vuln("E")], max_severity="")
        row = deps.summarise({"results": [{"source": {"path": "a.lock"}, "packages": [pkg]}]}, "/r")["vulnerable"][0]
        self.assertEqual(row["severity"], "unknown")

    def test_a_malicious_package_advisory_is_critical_whatever_its_score_and_leads(self):
        """OpenSSF's malicious-packages records are MAL- ids in the same OSV database; they carry no CVSS,
        so without this rule a known-malicious package lands in the unknown bucket."""
        rows = [package("minimist", "0.0.8", [vuln("GHSA-3", ["CVE-2021-44906"], fixed="1.2.6", name="minimist")], max_severity="9.8"),
                package("evil-pad", "1.0.2", [vuln("MAL-2026-1234", (), "Malicious code in evil-pad (npm)", name="evil-pad")], max_severity=""),
                package("aliased", "2.0.0", [vuln("GHSA-9", ["MAL-2026-99"], name="aliased")], max_severity="")]
        out = deps.summarise({"results": [{"source": {"path": "package-lock.json"}, "packages": rows}]}, "/r")
        self.assertEqual([(r["name"], r["severity"], r["malicious"]) for r in out["vulnerable"]],
                         [("aliased", "critical", True), ("evil-pad", "critical", True), ("minimist", "critical", False)],
                         "malicious first, by name; then by score")
        self.assertIsNone(out["vulnerable"][1]["score"], "the score stays what the advisory says: nothing")
        self.assertEqual(out["vulnerable"][1]["ids"], ["MAL-2026-1234"])

    def test_an_informational_advisory_is_a_note_not_a_vulnerability(self):
        # paperclip: rustls-pemfile 2.2.0, RUSTSEC-2025-0134 "rustls-pemfile is unmaintained", no score, was counted vulnerable
        note = vuln("RUSTSEC-2025-0134", summary="rustls-pemfile is unmaintained", name="rustls-pemfile")
        note["affected"][0]["database_specific"] = {"informational": "unmaintained", "cvss": None}
        real = vuln("RUSTSEC-2026-0285", summary="TLS 1.3 handshake", fixed="0.23.45", name="rustls")
        mixed = vuln("RUSTSEC-2024-0001", name="both")
        mixed_note = vuln("RUSTSEC-2024-0002", name="both")
        mixed_note["affected"][0]["database_specific"] = {"informational": "unsound"}
        rows = [package("rustls-pemfile", "2.2.0", [note], ecosystem="crates.io", max_severity=""),
                package("rustls", "0.23.43", [real], ecosystem="crates.io", max_severity="5.3"),
                package("both", "1.0.0", [mixed, mixed_note], ecosystem="crates.io", max_severity="")]
        out = deps.summarise({"results": [{"source": {"path": "/r/Cargo.lock"}, "packages": rows}]}, "/r")
        self.assertEqual(sorted(r["name"] for r in out["vulnerable"]), ["both", "rustls"], "one real advisory keeps a package vulnerable")
        self.assertEqual(out["informational"], [{"name": "rustls-pemfile", "version": "2.2.0", "ecosystem": "crates.io", "source": "Cargo.lock",
                                                 "ids": ["RUSTSEC-2025-0134"], "kinds": ["unmaintained"], "summary": "rustls-pemfile is unmaintained"}])

    def test_an_empty_scan(self):
        self.assertEqual(deps.summarise({"results": []}, "/r"), {"status": "scanned", "sources": [], "packages": 0, "vulnerable": []})

    def test_a_row_says_it_is_not_malicious(self):
        row = deps.summarise(report(), "/repo")["vulnerable"][0]
        self.assertIs(row["malicious"], False)


class Requirements(unittest.TestCase):
    """osv-scanner reads `mcp>=1.0.0` as mcp 1.0.0: the row keeps the specifier, so a floor is not an install."""

    def test_the_specifier_is_read_by_the_normalised_name(self):
        text = "# pinned\n-r base.txt\nMCP >= 1.0.0 ; python_version >= '3.9'  # the SDK\nrequests[socks]==2.31.0\nPyYAML\n"
        self.assertEqual(deps.requirement(text, "mcp"), ">=1.0.0")
        self.assertEqual(deps.requirement(text, "requests"), "==2.31.0")
        self.assertEqual(deps.requirement(text, "pyyaml"), "", "the bare name admits any version")
        self.assertIsNone(deps.requirement(text, "base"), "an option line names no package")
        self.assertIsNone(deps.requirement(text, "absent"))

    def test_a_row_from_a_requirement_file_says_whether_it_is_pinned(self):
        with tempfile.TemporaryDirectory() as repo:
            os.makedirs(os.path.join(repo, "tools"))
            with open(os.path.join(repo, "tools", "requirements.txt"), "w") as fh:
                fh.write("mcp>=1.0.0\nrequests==2.31.0\npytest==7.*\n")
            pkgs = [package(n, v, [vuln("GHSA-" + n, name=n)], ecosystem="PyPI") for n, v in (("mcp", "1.0.0"), ("requests", "2.31.0"), ("pytest", "7.0"))]
            out = deps.summarise({"results": [{"source": {"path": os.path.join(repo, "tools", "requirements.txt"), "type": "lockfile"}, "packages": pkgs}]}, repo)
        got = {r["name"]: (r.get("requirement"), r.get("pinned")) for r in out["vulnerable"]}
        self.assertEqual(got, {"mcp": (">=1.0.0", False), "requests": ("==2.31.0", True), "pytest": ("==7.*", False)})

    def test_a_lock_file_row_carries_no_specifier(self):
        self.assertNotIn("requirement", deps.summarise(report(), "/repo")["vulnerable"][0])

    def test_files_are_counted_by_kind(self):
        self.assertEqual(deps.files_phrase(["uv.lock", "a/package-lock.json"]), "2 lock files")
        self.assertEqual(deps.files_phrase(["uv.lock", "x/requirements-dev.txt", "y/requirements.txt"]), "1 lock file and 2 requirement files")
        self.assertEqual(deps.files_phrase(["constraints.txt"]), "1 requirement file")


class Declarations(unittest.TestCase):
    """What a lock's directory declares about how it ships, read from its files at collection."""

    def write(self, repo, path, text):
        full = os.path.join(repo, path)
        os.makedirs(os.path.dirname(full) or repo, exist_ok=True)
        with open(full, "w") as fh:
            fh.write(text)

    def test_workspace_members_and_their_entry_points(self):
        with tempfile.TemporaryDirectory() as repo:
            self.write(repo, "package.json", json.dumps({"private": True, "workspaces": ["web"]}))   # npm's members are not uv.lock's
            self.write(repo, "pyproject.toml", '[tool.uv.workspace]\nmembers = [\n  "api",\n  "libs/*",\n]\nexclude = ["libs/old"]\n')
            self.write(repo, "api/pyproject.toml", '[project]\nname = "api"\n\n[project.scripts]\napi = "api.main:main"\n')
            self.write(repo, "libs/core/pyproject.toml", '[project]\nname = "core"\n')
            self.write(repo, "libs/old/pyproject.toml", '[project]\nname = "old"\n[project.scripts]\nold = "x:y"\n')
            self.write(repo, "web/package.json", json.dumps({"name": "w", "workspaces": ["packages/*", "!packages/skip"]}))
            self.write(repo, "web/packages/cli/package.json", json.dumps({"name": "c", "bin": {"c": "cli.js"}}))
            self.write(repo, "web/packages/skip/package.json", json.dumps({"name": "s", "bin": "s.js"}))
            self.write(repo, "web/packages/lint/package.json", json.dumps({"name": "l", "private": True, "bin": {"l": "l.js"}}))
            self.write(repo, "lib/package.json", json.dumps({"name": "lib", "main": "index.js"}))
            self.write(repo, "rs/Cargo.toml", '[package]\nname = "x"\n\n[[bin]]\nname = "x"\n')
            self.write(repo, "deploy/docker-compose.yml", "services:\n  api:\n    build:\n      context: ../api\n      dockerfile: Dockerfile\n  web:\n    build: ../web\n  db:\n    image: postgres\n")
            subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
            subprocess.run(["git", "add", "."], cwd=repo, check=True)
            result = {"sources": [{"path": p, "packages": 1} for p in ("uv.lock", "web/package-lock.json", "lib/package-lock.json", "rs/Cargo.lock")]}
            deps.declare(result, repo)
        src = {s["path"]: s for s in result["sources"]}
        self.assertEqual(src["uv.lock"]["members"], ["api", "libs/core"], "an excluded member is not one")
        self.assertEqual(src["uv.lock"]["entry_points"], ["api/pyproject.toml [project.scripts]"])
        self.assertEqual(src["web/package-lock.json"]["entry_points"], ["web/packages/cli/package.json bin"], "a private toolbox's bin is a command for its developers, not a program")
        self.assertNotIn("entry_points", src["lib/package-lock.json"], "a library declares no program")
        self.assertEqual(src["rs/Cargo.lock"]["entry_points"], ["rs/Cargo.toml [[bin]]"])
        self.assertEqual(result["compose_builds"], ["api", "web"])

    def test_compose_build_contexts(self):
        text = "services:\n  a:\n    build: .\n  b:\n    build:\n      dockerfile: x\n  c:\n    build: https://github.com/x/y.git\n  d:\n    build: ${CTX}\n"
        self.assertEqual(deps.compose_builds(text, "docker/a"), ["docker/a", "docker/a"])
        self.assertEqual(deps.compose_builds("services:\n  a:\n    build: ../../..\n", "a"), [], "outside the repository")

    def test_what_declares_a_lock_ships(self):
        tree = {"svc/Dockerfile", "svc/uv.lock", "lib/src/lib.rs", "cli/src/main.rs", "tool/cmd/x/main.go", "Chart.yaml"}
        self.assertEqual(deps.deploys({"path": "svc/uv.lock"}, tree), ["svc/Dockerfile"])
        self.assertEqual(deps.deploys({"path": "lib/Cargo.lock"}, tree), [])
        self.assertEqual(deps.deploys({"path": "cli/Cargo.lock"}, tree), ["cli/src/main.rs"])
        self.assertEqual(deps.deploys({"path": "tool/go.mod"}, tree), ["tool/cmd/x/main.go"])
        self.assertEqual(deps.deploys({"path": "uv.lock"}, tree), ["Chart.yaml"])
        self.assertEqual(deps.deploys({"path": "svc/uv.lock"}, None), [], "an older run without a tree")


class DatabaseDate(unittest.TestCase):
    def test_newest_file_under_the_cache_names_the_day_and_nothing_means_none(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertIsNone(deps.database_date(d))
            os.makedirs(os.path.join(d, "osv-scalibr", "npm"))
            path = os.path.join(d, "osv-scalibr", "npm", "all.zip")
            open(path, "w").close()
            os.utime(path, (1_600_000_000, 1_600_000_000))
            self.assertEqual(deps.database_date(d), "2020-09-13")

    def test_the_digest_names_the_snapshot_and_changes_when_it_does(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertIsNone(deps.database_digest(d))
            os.makedirs(os.path.join(d, "osv-scalibr", "npm"))
            path = os.path.join(d, "osv-scalibr", "npm", "all.zip")
            with open(path, "w") as fh:
                fh.write("a")
            os.utime(path, (1_600_000_000, 1_600_000_000))
            first = deps.database_digest(d)
            self.assertRegex(first, r"^[0-9a-f]{16}$")
            self.assertEqual(deps.database_digest(d), first)
            os.utime(path, (1_600_000_100, 1_600_000_100))
            self.assertNotEqual(deps.database_digest(d), first, "a refreshed copy is another snapshot")

    def test_the_explicit_variable_wins_over_the_platform_cache(self):
        from unittest.mock import patch
        with patch.dict(os.environ, {"OSV_SCANNER_LOCAL_DB_CACHE_DIRECTORY": "/x/y"}):
            self.assertEqual(deps.cache_dir(), "/x/y")
        with patch.dict(os.environ, {"OSV_SCANNER_LOCAL_DB_CACHE_DIRECTORY": ""}):
            self.assertTrue(os.path.isabs(deps.cache_dir()))


class Script(unittest.TestCase):
    """The wiring, against a stand-in osv-scanner on PATH."""

    def _run(self, stdout: str, rc: int = 0, stderr: str = "Scanning dir .\n", listing: str = None):
        with tempfile.TemporaryDirectory() as d:
            bindir, repo, out = os.path.join(d, "bin"), os.path.join(d, "repo"), os.path.join(d, "out")
            for p in (bindir, repo, out):
                os.makedirs(p)
            with open(os.path.join(d, "stdout.json"), "w") as fh:
                fh.write(stdout)
            with open(os.path.join(d, "stderr.txt"), "w") as fh:
                fh.write(stderr)
            fake = os.path.join(bindir, "osv-scanner")
            with open(fake, "w") as fh:
                listed = ""
                if listing is not None:   # the second pass, matcher off, answers with the package list
                    with open(os.path.join(d, "listing.json"), "w") as lh:
                        lh.write(listing)
                    listed = f'case "$*" in *vulnmatch*) cat {d}/listing.json; exit 0;; esac\n'
                fh.write(f"#!/bin/sh\n{listed}echo \"$@\" > {d}/argv\npwd > {d}/cwd\ncat {d}/stdout.json\ncat {d}/stderr.txt >&2\nexit {rc}\n")
            os.chmod(fake, os.stat(fake).st_mode | stat.S_IEXEC)
            env = dict(os.environ, PATH=bindir + os.pathsep + os.environ["PATH"], OSV_SCANNER_LOCAL_DB_CACHE_DIRECTORY=os.path.join(d, "nodb"))
            target = os.path.join(out, "dependencies.json")
            p = subprocess.run([sys.executable, SCRIPT, target], cwd=repo, env=env, capture_output=True, text=True)
            with open(os.path.join(d, "argv")) as fh:
                argv = fh.read().split()
            with open(os.path.join(d, "cwd")) as fh:
                cwd = fh.read().strip()
            written = None
            if os.path.exists(target):
                with open(target) as fh:
                    written = json.load(fh)
            leftovers = sorted(os.listdir(out))
            self.packages = None
            if "packages.json" in leftovers:
                with open(os.path.join(out, "packages.json")) as fh:
                    self.packages = json.load(fh)["packages"]
        return p, argv, cwd, written, leftovers, repo

    def test_scans_the_repository_offline_and_writes_the_summary(self):
        p, argv, cwd, written, leftovers, repo = self._run(json.dumps(report(cwd="/repo")), rc=1)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(argv[:2], ["scan", "source"])
        self.assertIn("--offline", argv, "nothing leaves the machine")
        self.assertIn("--all-packages", argv, "the clean packages are counted too")
        self.assertEqual(argv[argv.index("--format") + 1], "json")
        self.assertEqual(argv[-1], ".")
        self.assertEqual(os.path.realpath(cwd), os.path.realpath(repo))
        self.assertEqual(written["status"], "scanned")
        self.assertEqual([r["name"] for r in written["vulnerable"]], ["minimist", "lodash"])
        self.assertIsNone(written["database_date"], "no local database directory: no date")
        self.assertEqual(leftovers, ["dependencies.json", "packages.json"])
        self.assertIn("Scanning dir", p.stderr, "osv-scanner's own log still reaches run.log")

    def test_no_lock_files_is_recorded_not_failed(self):
        p, _, _, written, _, _ = self._run("", rc=128, stderr="No package sources found, --help for usage information.\n")
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(written, {"status": "no-sources"})

    def test_a_missing_local_database_is_recorded_with_the_download_command(self):
        p, _, _, written, _, _ = self._run('{"results": []}', rc=127,
                                           stderr="could not load db for npm ecosystem: unable to fetch OSV database: no offline version of the OSV database is available\n")
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(written["status"], "no-database")
        self.assertEqual(written["download"], "osv-scanner scan source -r --offline-vulnerabilities --download-offline-databases .")

    def test_without_the_database_the_lock_files_are_still_listed_for_the_sbom(self):
        listing = json.dumps({"results": [{"source": {"path": "./package-lock.json"}, "packages": [{"package": {"name": "a", "version": "1", "ecosystem": "npm"}}]}]})
        p, _, _, written, leftovers, _ = self._run('{"results": []}', rc=127, listing=listing,
                                                   stderr="unable to fetch OSV database: no offline version of the OSV database is available\n")
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(written["status"], "no-database", "the vulnerabilities were not checked, whatever the listing found")
        self.assertEqual(leftovers, ["dependencies.json", "packages.json"])
        self.assertEqual(self.packages, [{"ecosystem": "npm", "name": "a", "version": "1", "sources": ["package-lock.json"]}])

    def test_any_other_failure_writes_nothing_and_fails_the_step(self):
        p, _, _, written, leftovers, _ = self._run("", rc=127, stderr="something else broke\n")
        self.assertEqual(p.returncode, 127)
        self.assertIsNone(written)
        self.assertEqual(leftovers, [])


if __name__ == "__main__":
    unittest.main()

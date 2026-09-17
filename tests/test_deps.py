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
                                  "score": 7.2, "severity": "high", "summary": "Command injection", "fixed": "4.17.19"})
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

    def test_an_empty_scan(self):
        self.assertEqual(deps.summarise({"results": []}, "/r"), {"status": "scanned", "sources": [], "packages": 0, "vulnerable": []})


class DatabaseDate(unittest.TestCase):
    def test_newest_file_under_the_cache_names_the_day_and_nothing_means_none(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertIsNone(deps.database_date(d))
            os.makedirs(os.path.join(d, "osv-scalibr", "npm"))
            path = os.path.join(d, "osv-scalibr", "npm", "all.zip")
            open(path, "w").close()
            os.utime(path, (1_600_000_000, 1_600_000_000))
            self.assertEqual(deps.database_date(d), "2020-09-13")

    def test_the_explicit_variable_wins_over_the_platform_cache(self):
        from unittest.mock import patch
        with patch.dict(os.environ, {"OSV_SCANNER_LOCAL_DB_CACHE_DIRECTORY": "/x/y"}):
            self.assertEqual(deps.cache_dir(), "/x/y")
        with patch.dict(os.environ, {"OSV_SCANNER_LOCAL_DB_CACHE_DIRECTORY": ""}):
            self.assertTrue(os.path.isabs(deps.cache_dir()))


class Script(unittest.TestCase):
    """The wiring, against a stand-in osv-scanner on PATH."""

    def _run(self, stdout: str, rc: int = 0, stderr: str = "Scanning dir .\n"):
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
                fh.write(f"#!/bin/sh\necho \"$@\" > {d}/argv\npwd > {d}/cwd\ncat {d}/stdout.json\ncat {d}/stderr.txt >&2\nexit {rc}\n")
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
        self.assertEqual(leftovers, ["dependencies.json"])
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

    def test_any_other_failure_writes_nothing_and_fails_the_step(self):
        p, _, _, written, leftovers, _ = self._run("", rc=127, stderr="something else broke\n")
        self.assertEqual(p.returncode, 127)
        self.assertIsNone(written)
        self.assertEqual(leftovers, [])


if __name__ == "__main__":
    unittest.main()

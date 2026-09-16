import hashlib
import json
import os
import stat
import subprocess
import sys
import tempfile
import unittest

from gitmole import leaks

SCRIPT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "gitmole", "leaks.py")

# Synthetic values only, built at runtime: a secret-shaped literal would make gitleaks, GitHub push
# protection and gitmole itself flag this file.
FAKE = "0123456789abcdef" * 2
VERSION = "5.0.0-" + "1667386184.dfbbb54"
RAW = [
    {"RuleID": "generic-api-key", "File": "app/settings.py", "Commit": "c1c1c1c1c1", "StartLine": 9, "Fingerprint": "c1c1c1c1c1:app/settings.py:generic-api-key:9",
     "Secret": FAKE, "Match": f'SECRET = "{FAKE}"', "Line": f'SECRET = "{FAKE}"',
     "Author": "Ann", "Message": f"rotate {FAKE} out of settings"},   # a message can quote the value
    {"RuleID": "generic-api-key", "File": "web/package.json", "Commit": "d2d2d2d2d2", "StartLine": 21, "Fingerprint": "d2d2d2d2d2:web/package.json:generic-api-key:21",
     "Secret": VERSION, "Match": f'auth-next": "{VERSION}"'},
]


class Digest(unittest.TestCase):
    def test_short_stable_and_distinct(self):
        self.assertEqual(leaks.digest("abc"), hashlib.sha256(b"abc").hexdigest()[:12])
        self.assertNotEqual(leaks.digest("abc"), leaks.digest("abd"))


class Placeholder(unittest.TestCase):
    def test_shapes_that_cannot_be_a_live_secret(self):
        for value in [VERSION, "1.2.3", "10.4.0+build.7", "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...", "abcdef…"]:
            self.assertTrue(leaks.is_placeholder(value), value)

    def test_anything_else_is_taken_seriously(self):
        # built at runtime: a literal in these shapes would trip secret scanners on this very file
        key_id, long_key = "AKIA" + "X" * 16, "6L" + "x" * 38
        for value in [FAKE, key_id, long_key, "1.2", "v1.2.3.4.5x", ""]:
            self.assertFalse(leaks.is_placeholder(value), value)


class Sanitise(unittest.TestCase):
    def test_raw_values_are_replaced_by_a_hash_and_a_placeholder_flag(self):
        rows = leaks.sanitise(RAW)
        text = json.dumps(rows)
        self.assertNotIn("0123456789abcdef", text)
        self.assertNotIn("dfbbb54", text)
        for row in rows:
            self.assertFalse({"Secret", "Match", "Line", "Message"} & set(row), row)
        self.assertEqual(rows[0]["SecretHash"], leaks.digest(FAKE))
        self.assertEqual([r["Placeholder"] for r in rows], [False, True])
        self.assertEqual(rows[0]["Fingerprint"], RAW[0]["Fingerprint"])
        self.assertEqual(rows[0]["Author"], "Ann")


class Script(unittest.TestCase):
    """Runs the script against a stand-in gitleaks on PATH, so the wiring is tested without real keys."""

    def _run(self, stdout: str, rc: int = 0):
        with tempfile.TemporaryDirectory() as d:
            bindir, repo, out = os.path.join(d, "bin"), os.path.join(d, "repo"), os.path.join(d, "out")
            for p in (bindir, repo, out):
                os.makedirs(p)
            with open(os.path.join(d, "stdout.json"), "w") as fh:
                fh.write(stdout)
            fake = os.path.join(bindir, "gitleaks")
            with open(fake, "w") as fh:
                fh.write(f"#!/bin/sh\necho \"$@\" > {d}/argv\npwd > {d}/cwd\ncat {d}/stdout.json\necho 'INF scanned' >&2\nexit {rc}\n")
            os.chmod(fake, os.stat(fake).st_mode | stat.S_IEXEC)
            env = dict(os.environ, PATH=bindir + os.pathsep + os.environ["PATH"])
            report = os.path.join(out, "secrets.json")
            p = subprocess.run([sys.executable, SCRIPT, report], cwd=repo, env=env, capture_output=True, text=True)
            with open(os.path.join(d, "argv")) as fh:
                argv = fh.read().split()
            with open(os.path.join(d, "cwd")) as fh:
                cwd = fh.read().strip()
            written = None
            if os.path.exists(report):
                with open(report) as fh:
                    written = fh.read()
            leftovers = sorted(os.listdir(out))
        return p, argv, cwd, written, leftovers, repo

    def test_report_goes_through_memory_and_only_hashes_reach_disk(self):
        p, argv, cwd, written, leftovers, repo = self._run(json.dumps(RAW))
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(argv[:1], ["git"])
        self.assertEqual(argv[argv.index("--report-path") + 1], "-", "the raw report must never be a file")
        self.assertEqual(argv[argv.index("--report-format") + 1], "json")
        self.assertEqual(os.path.realpath(cwd), os.path.realpath(repo), "gitleaks scans the repository it is started in")
        self.assertNotIn("0123456789abcdef", written)
        self.assertEqual(len(json.loads(written)), 2)
        self.assertEqual(leftovers, ["secrets.json"], "no temporary file is left behind")
        self.assertIn("INF scanned", p.stderr, "gitleaks' own log still reaches run.log")

    def test_no_findings_writes_an_empty_list(self):
        p, _, _, written, _, _ = self._run("[]")
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(json.loads(written), [])

    def test_a_failed_scan_writes_nothing_and_fails_the_step(self):
        p, _, _, written, leftovers, _ = self._run(json.dumps(RAW), rc=2)
        self.assertEqual(p.returncode, 2)
        self.assertIsNone(written, "a partial scan must not pass for a clean one")
        self.assertEqual(leftovers, [])


class Group(unittest.TestCase):
    def row(self, value, file, commit="c1", line=1, rule="generic-api-key", placeholder=False):
        return {"rule": rule, "file": file, "commit": commit, "line": line, "fingerprint": f"{commit}:{file}:{rule}:{line}",
                "value": value, "placeholder": placeholder}

    def test_one_entry_per_value_with_its_distinct_places_source_first(self):
        rows = [self.row("h2", "tests/data/a.html", "c3", 5), self.row("h2", "tests/data/a.html", "c3", 5),   # same place twice
                self.row("h2", "app/tests/data/a.html", "c4", 5),
                self.row("h1", "app/settings.py", "c1", 9), self.row("h1", "app/settings.py", "c2", 9),
                self.row("h3", "tests/t.py", "c5", 2),
                self.row("h4", "web/package.json", "c6", 21, placeholder=True)]
        groups = leaks.group(rows)
        self.assertEqual([g["value"] for g in groups], ["h1", "h2", "h3"], "source first, then by places; placeholders left out")
        self.assertEqual(groups[0], {"value": "h1", "rule": "generic-api-key", "files": ["app/settings.py"], "commits": ["c1", "c2"],
                                     "places": 2, "test": False})
        self.assertEqual(groups[1]["files"], ["tests/data/a.html", "app/tests/data/a.html"])
        self.assertEqual(groups[1]["places"], 2)
        self.assertTrue(groups[1]["test"])
        self.assertEqual(leaks.placeholders(rows), 1)

    def test_a_value_seen_in_source_and_tests_counts_as_source(self):
        groups = leaks.group([self.row("h1", "tests/t.py", "c1"), self.row("h1", "app/a.py", "c2")])
        self.assertFalse(groups[0]["test"])

    def test_rows_without_a_value_are_their_own_group(self):
        groups = leaks.group([{"rule": "aws", "file": "a.env", "commit": "abc1234"}, {"rule": "aws", "file": "b.env", "commit": "abc1234"}])
        self.assertEqual(len(groups), 2)


if __name__ == "__main__":
    unittest.main()

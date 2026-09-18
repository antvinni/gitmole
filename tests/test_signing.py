import json
import os
import subprocess
import tempfile
import unittest

from gitmole import signing


def make_repo(d):
    """Two SSH-signed commits by Ann in 2025, one unsigned by Ann in 2026, one unsigned by a bot."""
    def git(*args, **env):
        e = dict(os.environ, GIT_CONFIG_GLOBAL="/dev/null", GIT_CONFIG_SYSTEM="/dev/null", GIT_AUTHOR_NAME="Ann", GIT_AUTHOR_EMAIL="a@x",
                 GIT_COMMITTER_NAME="Ann", GIT_COMMITTER_EMAIL="a@x", GIT_AUTHOR_DATE="2025-03-01T00:00:00", GIT_COMMITTER_DATE="2025-03-01T00:00:00")
        e.update(env)
        subprocess.run(["git", *args], cwd=d, check=True, capture_output=True, env=e)
    git("init", "-q", "-b", "main")
    key = os.path.join(d, "key")
    subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", key], check=True, capture_output=True)
    git("config", "gpg.format", "ssh")
    git("config", "user.signingkey", key)
    with open(os.path.join(d, "f"), "w") as fh:
        fh.write("a\n")
    git("add", "f")
    git("commit", "-q", "-S", "-m", "one")
    git("commit", "-q", "-S", "--allow-empty", "-m", "two")
    git("commit", "-q", "--allow-empty", "-m", "three", GIT_AUTHOR_DATE="2026-01-01T00:00:00", GIT_COMMITTER_DATE="2026-01-01T00:00:00")
    git("commit", "-q", "--allow-empty", "-m", "bump", GIT_AUTHOR_NAME="renovate[bot]", GIT_AUTHOR_EMAIL="1+renovate[bot]@users.noreply.github.com",
        GIT_AUTHOR_DATE="2026-02-01T00:00:00", GIT_COMMITTER_DATE="2026-02-01T00:00:00")


class Classify(unittest.TestCase):
    def test_the_signature_kind_from_the_header_payload(self):
        self.assertEqual(signing.kind("-----BEGIN SSH SIGNATURE-----\nU1NI..."), "ssh")
        self.assertEqual(signing.kind("-----BEGIN PGP SIGNATURE-----\n\niQ..."), "gpg")
        self.assertEqual(signing.kind("-----BEGIN SIGNED MESSAGE-----\nMII..."), "x509")
        self.assertEqual(signing.kind("garbage"), "other")


class Coverage(unittest.TestCase):
    def test_counts_signed_commits_by_mechanism_year_and_people_against_bots_without_a_keyring(self):
        with tempfile.TemporaryDirectory() as d:
            make_repo(d)
            out = signing.coverage(d, bots={"renovate[bot]"})
        self.assertEqual((out["commits"], out["signed"]), (4, 2))
        self.assertEqual(out["mechanisms"], {"ssh": 2})
        self.assertEqual(out["by_year"], {"2025": {"commits": 2, "signed": 2}, "2026": {"commits": 2, "signed": 0}})
        self.assertEqual(out["humans"], {"commits": 3, "signed": 2})
        self.assertEqual(out["bots"], {"commits": 1, "signed": 0})
        self.assertEqual(out["by_identity"], [{"name": "Ann", "commits": 3, "signed": 2}, {"name": "renovate[bot]", "commits": 1, "signed": 0}])
        self.assertEqual(out["last_year"], {"commits": 4, "signed": 2}, "the twelve months before the last commit: everything here is inside them")

    def test_the_step_writes_signing_json_from_inside_the_repository(self):
        with tempfile.TemporaryDirectory() as d:
            make_repo(d)
            out = os.path.join(d, "out")
            os.makedirs(out)
            with open(os.path.join(out, "meta.json"), "w") as fh:
                json.dump({"bots": [{"name": "renovate[bot]", "commits": 1}]}, fh)
            rc = subprocess.run([signing.PYTHON, "-m", "gitmole.signing", out], cwd=d, capture_output=True, text=True,
                                env=dict(os.environ, PYTHONPATH=os.path.dirname(os.path.dirname(os.path.abspath(__file__))))).returncode
            self.assertEqual(rc, 0)
            with open(os.path.join(out, "signing.json")) as fh:
                data = json.load(fh)
        self.assertEqual((data["commits"], data["signed"], data["bots"]["commits"]), (4, 2, 1))


if __name__ == "__main__":
    unittest.main()

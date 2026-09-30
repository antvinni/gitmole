import hashlib
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
import unittest.mock

from gitmole import leaks

SCRIPT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "gitmole", "leaks.py")

# Synthetic values only, built at runtime: a secret-shaped literal would make betterleaks, GitHub push
# protection and gitmole itself flag this file.
FAKE = "0123456789abcdef" * 2
VERSION = "5.0.0-" + "1667386184.dfbbb54"
RAW = [
    {"RuleID": "generic-api-key", "File": "app/settings.py", "Commit": "c1c1c1c1c1", "StartLine": 9, "Fingerprint": "c1c1c1c1c1:app/settings.py:generic-api-key:9",
     "Secret": FAKE, "Match": f'SECRET = "{FAKE}"', "Line": f'SECRET = "{FAKE}"',
     "Author": "Ann", "Message": f"rotate {FAKE} out of settings",   # a message can quote the value
     "Attributes": {"confidence": "high", "git.message": f"rotate {FAKE} out of settings", "path": "app/settings.py"}},   # betterleaks repeats it here
    {"RuleID": "generic-api-key", "File": "web/package.json", "Commit": "d2d2d2d2d2", "StartLine": 21, "Fingerprint": "d2d2d2d2d2:web/package.json:generic-api-key:21",
     "Secret": VERSION, "Match": f'auth-next": "{VERSION}"'},
]


class Digest(unittest.TestCase):
    def test_keyed_short_stable_under_one_key_and_distinct(self):
        key = b"k" * 32
        self.assertEqual(len(leaks.digest("abc", key)), 12)
        self.assertEqual(leaks.digest("abc", key), leaks.digest("abc", key))
        self.assertNotEqual(leaks.digest("abc", key), leaks.digest("abd", key))

    def test_a_stored_hash_cannot_be_checked_against_a_word_list(self):
        key = leaks.new_key()
        plain = hashlib.sha256(b"hunter2").hexdigest()[:12]
        self.assertNotEqual(leaks.digest("hunter2", key), plain, "an unkeyed hash of a weak value is a dictionary lookup away")
        self.assertNotEqual(leaks.digest("hunter2", key), leaks.digest("hunter2", leaks.new_key()), "a fresh key per report")
        self.assertGreaterEqual(len(key), 32)


class Placeholder(unittest.TestCase):
    def test_shapes_that_cannot_be_a_live_secret(self):
        for value in [VERSION, "1.2.3", "10.4.0+build.7", "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...", "abcdef…"]:
            self.assertTrue(leaks.is_placeholder(value), value)

    def test_a_key_block_without_key_material_is_a_template(self):
        # Google's service-account sample: header, a dotted body, footer; a real body is hundreds of base64 characters
        for body in ["...", "\\n...\\n", "", "…", "xxxx"]:
            self.assertTrue(leaks.is_placeholder(f"-----BEGIN PRIVATE KEY-----{body}-----END PRIVATE KEY-----"), body)
        self.assertTrue(leaks.is_placeholder("-----BEGIN RSA PRIVATE KEY-----\\n...\\n-----END RSA PRIVATE KEY-----\\n"))
        real = "-----BEGIN PRIVATE KEY-----\\n" + "MIIEvQIBADANBgkqhkiG9w0BAQEFAASCBKcwggSjAgEAAoIBAQC" * 4 + "\\n-----END PRIVATE KEY-----"
        self.assertFalse(leaks.is_placeholder(real))

    def test_template_markers_are_placeholders(self):
        for value in ["your-project-id", "YOUR_API_KEY", "<your-token-here>", "xxxxxxxxxxxxxxxxxxxx", "XXXX-XXXX-XXXX", "changeme", "CHANGE_ME", "replace-me"]:
            self.assertTrue(leaks.is_placeholder(value), value)
        for value in ["AKIA" + "X" * 16, "6L" + "x" * 38, "ghp_" + "a1" * 18, "yourkey" + "9" * 20]:
            self.assertFalse(leaks.is_placeholder(value), "a marker inside real-looking material is not enough: " + value)

    def test_common_example_words_are_placeholders(self):
        # `password: 'hello'` in a doc comment, `secret` in a sample config: the words every example uses
        for value in ["hello", "Hello", "secret", "password", "PASSWORD", "example", "123456", "qwerty", "letmein", "foo", "dummy"]:
            self.assertTrue(leaks.is_placeholder(value), value)
        for value in ["x-oauth-basic", "x-access-token", "x-token-auth"]:   # one service's documented literals are vocabulary, not a shape
            self.assertFalse(leaks.is_placeholder(value), value)
        self.assertTrue(leaks.is_placeholder("hunter2", line='url = f"https://{token}:hunter2@github.com/{SLUG}.git"'),
                        "a line with a template field is a template being filled in")
        for value in ["hello123", "secret-9f8a7b6c5d4e", "s3cr3t!Passw0rd", "foobarbaz2024"]:
            self.assertFalse(leaks.is_placeholder(value), "a word inside other material is not a placeholder: " + value)

    def test_a_dotted_key_path_is_a_placeholder(self):
        # laravel: `const INVALID_PASSWORD = 'passwords.password';` names a translation key, not a password
        for value in ["passwords.password", "reminders.sent", "auth.failed", "validation.required_if"]:
            self.assertTrue(leaks.is_placeholder(value), value)
        for value in ["hunter2.xyz", "secret.Key9", "s3cr3t.pass", "auth.Fail3d"]:
            self.assertFalse(leaks.is_placeholder(value), "digits or capitals make it material: " + value)

    def test_references_to_an_environment_variable_are_placeholders(self):
        # fzf's notarisation config: `password = "@env:AC_PASSWORD"`; goreleaser: `{{.Env.MACOS_SIGN_PASSWORD}}`
        for value in ["@env:AC_PASSWORD", "{{.Env.MACOS_SIGN_PASSWORD}}", "${DB_PASSWORD}", "$DB_PASSWORD", "$(cat ~/.secret)", "%APPDATA_KEY%",
                      "{{ secrets.API_TOKEN }}", "<%= ENV['KEY'] %>", "process.env.API_KEY", "os.environ['API_KEY']", "os.environ.get('K')", "ENV['SECRET']"]:
            self.assertTrue(leaks.is_placeholder(value), value)
        for value in ["p@ssw0rd!", "AKIA" + "X" * 16, "env-9f8a7b6c5d4e3f2a", "${not closed", "hello$world"]:
            self.assertFalse(leaks.is_placeholder(value), value)

    def test_a_key_header_with_no_key_material_after_it_is_a_marker_not_a_key(self):
        # ohmyzsh's ssh-agent plugin greps files for the header; the scanner captures the header and the shell code after it
        for value in ["-----BEGIN OPENSSH PRIVATE KEY-----", "^-----BEGIN\\ OPENSSH\\ PRIVATE\\ KEY-----", "-----BEGIN RSA PRIVATE KEY-----\\n",
                      '-----BEGIN OPENSSH PRIVATE KEY-----".\n      if [[ -f "$file" && $(command head -n 1 "$file") =~ ^-----BEGIN ]]; then']:
            self.assertTrue(leaks.is_placeholder(value), value)
        real = "-----BEGIN OPENSSH PRIVATE KEY-----\n" + "b3BlbnNzaC1rZXktdjEAAAAABG5vbmUAAAAEbm9uZQAAAAAAAAABAAAAMwAAAAtzc2gtZW" * 3
        self.assertFalse(leaks.is_placeholder(real), "a header followed by base64 is a key, END or no END")

    def test_the_line_is_read_from_the_clone_at_the_commit(self):
        with tempfile.TemporaryDirectory() as d:
            subprocess.run(["git", "init", "-q", d], check=True)
            with open(os.path.join(d, "gen.sh"), "w") as fh:
                fh.write("#!/bin/sh\n# Example password: nz5ej2kypkvcw0rn5cvhs6qxtm\necho hi\n")
            subprocess.run(["git", "-C", d, "add", "gen.sh"], check=True)
            subprocess.run(["git", "-C", d, "-c", "user.name=T", "-c", "user.email=t@x.com", "commit", "-q", "-m", "gen"], check=True)
            sha = subprocess.run(["git", "-C", d, "rev-parse", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()
            self.assertEqual(leaks.line_of(d, sha, "gen.sh", 2), "# Example password: nz5ej2kypkvcw0rn5cvhs6qxtm")
            self.assertEqual(leaks.line_of(d, sha, "gen.sh", 3, above=2), "#!/bin/sh\n# Example password: nz5ej2kypkvcw0rn5cvhs6qxtm\necho hi",
                             "with context: the lines above, joined")
            self.assertEqual(leaks.line_of(d, sha, "gen.sh", 9), "", "past the end is nothing, not an error")
            self.assertEqual(leaks.line_of(d, sha, "missing.sh", 1), "")
            self.assertEqual(leaks.line_of(d, "", "gen.sh", 1), "")
            rows = [{"RuleID": "generic-api-key", "Commit": sha, "File": "gen.sh", "StartLine": n} for n in (1, 2)]
            rows.append({"RuleID": "brave-search-api-key", "Commit": sha, "File": "gen.sh", "StartLine": 3})
            with unittest.mock.patch.object(leaks, "LINE_LOOKUPS", 1):
                leaks.read_lines(d, rows)
            self.assertEqual([r.get("Line") for r in rows], ["#!/bin/sh", None, "#!/bin/sh\n# Example password: nz5ej2kypkvcw0rn5cvhs6qxtm\necho hi"],
                             "past the cap a generic row goes without its line and a provider's row still gets it")

    def test_a_line_that_calls_itself_an_example_is_a_placeholder(self):
        # `# Example password: nz5ej2kypkvcw0rn5cvhs6qxtm` in a password generator's header comment
        self.assertTrue(leaks.is_placeholder("nz5ej2kypkvcw0rn5cvhs6qxtm", line="# Example password: nz5ej2kypkvcw0rn5cvhs6qxtm"))
        self.assertTrue(leaks.is_placeholder("nz5ej2kypkvcw0rn5cvhs6qxtm", line="token = 'nz5ej2kypkvcw0rn5cvhs6qxtm'  # e.g. from the dashboard"))
        self.assertTrue(leaks.is_placeholder("nz5ej2kypkvcw0rn5cvhs6qxtm", line="SAMPLE_KEY = 'nz5ej2kypkvcw0rn5cvhs6qxtm'"))
        self.assertFalse(leaks.is_placeholder("nz5ej2kypkvcw0rn5cvhs6qxtm", line="api_key = 'nz5ej2kypkvcw0rn5cvhs6qxtm'"))
        self.assertFalse(leaks.is_placeholder("nz5ej2kypkvcw0rn5cvhs6qxtm"), "without the line there is nothing to go on")

    def test_a_run_up_the_alphabet_or_the_digits_is_made_up(self):
        # ohmyzsh's spotify plugin: CLIENT_SECRET="qr6stu789vwxyz" in a usage message
        for value in ["qr6stu789vwxyz", "abcdefghijklmnop", "abcd1234efgh5678", "ABCDEF123456", "0123456789abcdef"]:
            self.assertTrue(leaks.is_placeholder(value), value)
        for value in ["nz5ej2kypkvcw0rn5cvhs6qxtm", "abcdefg", "zyxwvutsrq", "ghp_" + "a1" * 18]:
            self.assertFalse(leaks.is_placeholder(value), value)

    def test_a_value_with_a_template_field_inside_it_is_a_template(self):
        # pytest's release script: oauth_url = f"https://{token}:x-oauth-basic@github.com/{SLUG}.git"
        for value in ["https://{token}:x-oauth-basic@github.com/pytest-dev/pytest.git", "Bearer ${TOKEN}", "key-%(api_key)s", "sk_live_{{ secret }}",
                      "${{ secrets.CODECOV_TOKEN }}", "https://<user>:<pass>@host/db"]:
            self.assertTrue(leaks.is_placeholder(value), value)
        for value in ["https://x:hunter2@host/db", "ghp_" + "a1" * 18, "{" + "a1" * 10]:
            self.assertFalse(leaks.is_placeholder(value), value)

    def test_a_sentence_of_prose_is_a_description_not_a_secret(self):
        # pytest's devpi task: 'password': 'user password on devpi to stage the generated package '
        for value in ["user password on devpi to stage the generated package", "The API key used to talk to the billing service"]:
            self.assertTrue(leaks.is_placeholder(value), value)
        for value in ["correct horse battery", "nz5ej2kypkvcw0rn5cvhs6qxtm", "one two 3 four five"]:
            self.assertFalse(leaks.is_placeholder(value), "under five words, or a digit among them: not prose")

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
            self.assertFalse({"Secret", "Match", "Line", "Message", "Attributes"} & set(row), row)
        self.assertEqual(len(rows[0]["SecretHash"]), 12)
        again = leaks.sanitise(RAW + RAW)
        self.assertEqual(again[0]["SecretHash"], again[2]["SecretHash"], "one key per report: repeats still group")
        self.assertNotEqual(again[0]["SecretHash"], rows[0]["SecretHash"], "a new report gets a new key")
        self.assertEqual([r["Placeholder"] for r in rows], [False, True])
        self.assertEqual(rows[0]["Fingerprint"], RAW[0]["Fingerprint"])
        self.assertEqual(rows[0]["Author"], "Ann")

    def test_the_line_is_read_for_the_placeholder_flag_before_it_is_dropped(self):
        row = dict(RAW[0], Line="# Example token: " + RAW[0]["Secret"])
        [clean] = leaks.sanitise([row])
        self.assertTrue(clean["Placeholder"])
        self.assertNotIn("Line", clean)

    def test_a_generic_hit_on_a_word_of_one_case_is_graded_low(self):
        word = "pg" + "admin"   # built at runtime, like FAKE
        row = dict(RAW[0], RuleID="generic-password", Secret=word, Line=f"PGPASSWORD: {word}", Attributes={"confidence": "medium"})
        self.assertEqual(leaks.sanitise([row])[0]["Confidence"], "low", "a service default: the context raised it, the shape does not")
        self.assertEqual(leaks.sanitise([dict(row, Secret=word + "9Q")])[0]["Confidence"], "medium", "digits or mixed case keep the scanner's grade")
        self.assertEqual(leaks.sanitise([dict(row, RuleID="aws-access-token")])[0]["Confidence"], "medium", "a provider's rule keeps its grade")


class Script(unittest.TestCase):
    """Runs the script against a stand-in betterleaks on PATH, so the wiring is tested without real keys."""

    def _run(self, stdout: str, rc: int = 0):
        with tempfile.TemporaryDirectory() as d:
            bindir, repo, out = os.path.join(d, "bin"), os.path.join(d, "repo"), os.path.join(d, "out")
            for p in (bindir, repo, out):
                os.makedirs(p)
            with open(os.path.join(d, "stdout.json"), "w") as fh:
                fh.write(stdout)
            fake = os.path.join(bindir, "betterleaks")
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
        self.assertEqual(argv[argv.index("--log-opts") + 1:argv.index("--log-opts") + 3], ["--full-history", "HEAD"],
                         "HEAD's history, not betterleaks' default of every reference in the clone")
        self.assertEqual(os.path.realpath(cwd), os.path.realpath(repo), "betterleaks scans the repository it is started in")
        self.assertNotIn("0123456789abcdef", written)
        self.assertEqual(len(json.loads(written)), 2)
        self.assertEqual(leftovers, ["secrets.json"], "no temporary file is left behind")
        self.assertIn("INF scanned", p.stderr, "betterleaks' own log still reaches run.log")

    def test_no_findings_writes_an_empty_list(self):
        for empty in ["[]", "null"]:   # betterleaks prints null for a clean repository
            p, _, _, written, _, _ = self._run(empty)
            self.assertEqual(p.returncode, 0, p.stderr)
            self.assertEqual(json.loads(written), [], empty)

    def test_a_failed_scan_writes_nothing_and_fails_the_step(self):
        p, _, _, written, leftovers, _ = self._run(json.dumps(RAW), rc=2)
        self.assertEqual(p.returncode, 2)
        self.assertIsNone(written, "a partial scan must not pass for a clean one")
        self.assertEqual(leftovers, [])


def _git_repo_with_unreachable_objects(d):
    """A repository with one commit on main, a commit only the reflog remembers, and a dangling blob."""
    def git(*args):
        env = dict(os.environ, GIT_CONFIG_GLOBAL="/dev/null", GIT_CONFIG_SYSTEM="/dev/null", GIT_AUTHOR_NAME="Ann", GIT_AUTHOR_EMAIL="a@x",
                   GIT_COMMITTER_NAME="Ann", GIT_COMMITTER_EMAIL="a@x")
        return subprocess.run(["git", *args], cwd=d, check=True, capture_output=True, env=env, text=True).stdout.strip()
    git("init", "-q", "-b", "main")
    with open(os.path.join(d, "a.py"), "w") as fh:
        fh.write("x = 1\n")
    git("add", "-A")
    git("commit", "-q", "-m", "one")
    with open(os.path.join(d, "b.py"), "w") as fh:
        fh.write("TOKEN = '" + FAKE + "'\n")
    git("add", "-A")
    git("commit", "-q", "-m", "two")
    git("reset", "-q", "--hard", "HEAD~1")   # the second commit now lives only in the reflog
    with open(os.path.join(d, "loose.txt"), "w") as fh:
        fh.write("loose\n")
    dangling = git("hash-object", "-w", "loose.txt")
    os.remove(os.path.join(d, "loose.txt"))
    return dangling


class Unreachable(unittest.TestCase):
    def test_blobs_no_ref_reaches_reflog_only_and_dangling_alike(self):
        with tempfile.TemporaryDirectory() as d:
            dangling = _git_repo_with_unreachable_objects(d)
            found = leaks.unreachable(d)
        self.assertEqual(found["blobs"], 2, "b.py from the reset commit and the dangling blob")
        self.assertIn(dangling, found["shas"])
        self.assertGreaterEqual(found["objects"], 4, "the reset commit, its tree, its blob, the dangling blob")

    def test_nothing_outside_a_repository(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertIsNone(leaks.unreachable(d))

    def test_the_step_scans_the_unreachable_blobs_too_and_says_how_many(self):
        with tempfile.TemporaryDirectory() as d:
            bindir, repo, out = os.path.join(d, "bin"), os.path.join(d, "repo"), os.path.join(d, "out")
            for p in (bindir, repo, out):
                os.makedirs(p)
            _git_repo_with_unreachable_objects(repo)
            with open(os.path.join(d, "git.json"), "w") as fh:
                fh.write("null")
            fake = os.path.join(bindir, "betterleaks")
            with open(fake, "w") as fh:
                fh.write(f"""#!/bin/sh
echo "$@" >> {d}/argv
if [ "$1" = dir ]; then
  for f in "$2"/*; do
    if grep -q TOKEN "$f"; then
      printf '[{{"RuleID": "generic-api-key", "File": "%s", "StartLine": 1, "Fingerprint": "x", "Secret": "{FAKE}", "Match": "m", "Line": "l"}}]' "$f"
      exit 0
    fi
  done
  echo null
else
  cat {d}/git.json
fi
""")
            os.chmod(fake, os.stat(fake).st_mode | stat.S_IEXEC)
            env = dict(os.environ, PATH=bindir + os.pathsep + os.environ["PATH"], GIT_CONFIG_GLOBAL="/dev/null", GIT_CONFIG_SYSTEM="/dev/null")
            p = subprocess.run([sys.executable, SCRIPT, os.path.join(out, "secrets.json")], cwd=repo, env=env, capture_output=True, text=True)
            self.assertEqual(p.returncode, 0, p.stderr)
            with open(os.path.join(d, "argv")) as fh:
                calls = [line.split() for line in fh.read().splitlines()]
            with open(os.path.join(out, "secrets.json")) as fh:
                rows = json.load(fh)
            with open(os.path.join(out, "unreachable.json")) as fh:
                record = json.load(fh)
            leftovers = sorted(os.listdir(out))
        self.assertEqual([c[0] for c in calls], ["git", "dir"])
        self.assertTrue(all("--validation=false" in c for c in calls), "live-credential validation is network; it stays off, explicitly")
        [row] = rows
        self.assertRegex(row["File"], r"^\(unreachable blob [0-9a-f]{12}\)$")
        self.assertEqual(row["Commit"], "")
        self.assertRegex(row["Fingerprint"], r"^unreachable:[0-9a-f]{40}:generic-api-key:1$", "no scratch path, the same in every run")
        self.assertNotIn(FAKE, json.dumps(rows))
        self.assertEqual((record["blobs"], record["scanned"], record["findings"]), (2, 2, 1))
        self.assertEqual(leftovers, ["secrets.json", "unreachable.json"], "the blobs written for the scan are gone")


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
                                     "places": 2, "test": False, "docs": False, "confidence": None, "declared": None})
        self.assertEqual(groups[1]["files"], ["tests/data/a.html", "app/tests/data/a.html"])
        self.assertEqual(groups[1]["places"], 2)
        self.assertTrue(groups[1]["test"])
        self.assertEqual(leaks.placeholders(rows), 1)

    def test_a_value_only_in_documentation_is_flagged_as_such(self):
        groups = leaks.group([self.row("h1", "docs/GA4-API-INTEGRATION.md", "c1"), self.row("h1", "README.md", "c2")])
        self.assertTrue(groups[0]["docs"])
        self.assertFalse(groups[0]["test"])
        groups = leaks.group([self.row("h1", "docs/setup.md", "c1"), self.row("h1", "app/a.py", "c2")])
        self.assertFalse(groups[0]["docs"], "one place in source is enough")
        groups = leaks.group([self.row("h1", "tests/t.py", "c1")])
        self.assertFalse(groups[0]["docs"])
        self.assertTrue(groups[0]["test"])

    def test_a_value_seen_in_source_and_tests_counts_as_source(self):
        groups = leaks.group([self.row("h1", "tests/t.py", "c1"), self.row("h1", "app/a.py", "c2")])
        self.assertFalse(groups[0]["test"])

    def test_rows_without_a_value_are_their_own_group(self):
        groups = leaks.group([{"rule": "aws", "file": "a.env", "commit": "abc1234"}, {"rule": "aws", "file": "b.env", "commit": "abc1234"}])
        self.assertEqual(len(groups), 2)


if __name__ == "__main__":
    unittest.main()


class PlaceholderShapes(unittest.TestCase):
    def test_an_unquoted_symbol_in_a_language_that_quotes_literals(self):
        self.assertTrue(leaks.is_placeholder("EIPSW", "    PSW = EIPSW;", "Ghidra/Processors/V850/data/languages/V850.sinc"))
        self.assertTrue(leaks.is_placeholder("idaapi.PLFM_386", "if (idaapi.ph.id == idaapi.PLFM_386 and bits == 0):", "plugins/xmlexp.py"))
        self.assertFalse(leaks.is_placeholder("hunter2real", "PASSWORD=hunter2real", "deploy/env.sh"), "a shell literal needs no quotes")
        self.assertFalse(leaks.is_placeholder("s3cr3tPass", 'url = "https://user:s3cr3tPass@host/x"', "src/client.py"), "inside a literal")
        self.assertFalse(leaks.is_placeholder("Zq8vLm2Rt7Kp", 'u = "https://host/?token=Zq8vLm2Rt7Kp"', "src/client.py"), "an = inside a literal")
        self.assertFalse(leaks.is_placeholder("EIPSW", "", "x.sinc"), "no line, no judgement")

    def test_masks_file_references_labels_and_code_writing_a_header(self):
        self.assertTrue(leaks.is_placeholder("elastic:XXXXXX"))
        self.assertTrue(leaks.is_placeholder("preferences-desktop-user-password.png"))
        self.assertTrue(leaks.is_placeholder("EMPTY_ICON{images/lock.png[size(8"))
        self.assertTrue(leaks.is_placeholder("resetpassword"))
        self.assertTrue(leaks.is_placeholder("password_missing"))
        self.assertTrue(leaks.is_placeholder("changeme"))
        self.assertTrue(leaks.is_placeholder('-----BEGIN PRIVATE KEY-----");\n\t\twriter.println();'))
        self.assertFalse(leaks.is_placeholder("P4ssw0rd!x9Q"))
        self.assertTrue(leaks.is_placeholder("CURLOPT_PASSWD"))
        self.assertFalse(leaks.is_placeholder("MyCompanySecret"), "mixed case reads as a chosen password, not a name")

    def test_a_guid_in_a_table_of_guids_is_an_interface_id(self):
        table = "EAAAC2D5-C290-11D1-905D-00C04FD9189D IDXA\nEAAAC2D6-C290-11D1-905D-00C04FD9189D IDXB\nEAAAC2D7-C290-11D1-905D-00C04FD9189D IDXC"
        self.assertTrue(leaks.is_placeholder("EAAAC2D7-C290-11D1-905D-00C04FD9189D", table))
        self.assertFalse(leaks.is_placeholder("EAAAC2D7-C290-11D1-905D-00C04FD9189D", "api_key = EAAAC2D7-C290-11D1-905D-00C04FD9189D"))


class DefaultsAndPunctuatedWords(unittest.TestCase):
    def test_a_value_repeating_its_key_or_its_neighbours_is_a_default(self):
        self.assertTrue(leaks.is_placeholder("postgres", "    POSTGRES_PASSWORD: postgres"))
        self.assertTrue(leaks.is_placeholder("postgres", '    "USER": "postgres",\n    "PASSWORD": "postgres",'))
        self.assertFalse(leaks.is_placeholder("hunterzebra", 'password = "hunterzebra"'))
        self.assertFalse(leaks.is_placeholder("postgres", ""), "no line, no judgement")

    def test_an_example_word_with_punctuation_in_it(self):
        self.assertTrue(leaks.is_placeholder("pass?word"))
        self.assertFalse(leaks.is_placeholder("Xk9vTq2LmZ"))


@unittest.skipUnless(shutil.which("betterleaks"), "betterleaks is not installed")
class HeadOnly(unittest.TestCase):
    """betterleaks' own default walks every reference in the clone (--full-history --all); gitmole walks
    HEAD's history, so a secret on a branch the commit does not reach is the clone's, not the commit's."""

    KEY = "AK" + "IA" + "Z3Q7XK2MLPLWR4TB"   # the gate fixture's hand-made pair, assembled so this file holds none: an id alone is not reported
    SECRET = "u8Jq2pR7vN1x" + "Y6tB4mK9sW3cF0hL5dG2aZ8eQ7rT"

    def _git(self, *args, cwd):
        env = dict(os.environ, GIT_CONFIG_GLOBAL="/dev/null", GIT_CONFIG_SYSTEM="/dev/null", GIT_AUTHOR_NAME="Ann", GIT_AUTHOR_EMAIL="a@x",
                   GIT_COMMITTER_NAME="Ann", GIT_COMMITTER_EMAIL="a@x")
        return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, env=env, text=True).stdout.strip()

    def _scan(self, repo):
        with tempfile.TemporaryDirectory() as out:
            report = os.path.join(out, "secrets.json")
            p = subprocess.run([sys.executable, SCRIPT, report], cwd=repo, capture_output=True, text=True)
            self.assertEqual(p.returncode, 0, p.stderr)
            with open(report) as fh:
                return json.load(fh)

    def test_a_secret_on_an_unreached_branch_is_not_the_commits(self):
        with tempfile.TemporaryDirectory() as d:
            self._git("init", "-q", "-b", "main", cwd=d)
            with open(os.path.join(d, "a.py"), "w") as fh:
                fh.write("x = 1\n")
            self._git("add", "-A", cwd=d)
            self._git("commit", "-q", "-m", "one", cwd=d)
            self._git("switch", "-q", "-c", "leaky", cwd=d)
            with open(os.path.join(d, "deploy.py"), "w") as fh:
                fh.write(f'AWS_ACCESS_KEY_ID = "{self.KEY}"\nAWS_SECRET_ACCESS_KEY = "{self.SECRET}"\n')
            self._git("add", "-A", cwd=d)
            self._git("commit", "-q", "-m", "settings", cwd=d)
            self._git("switch", "-q", "main", cwd=d)
            self.assertEqual(self._scan(d), [], "the key lives on `leaky`, which main does not reach")
            self._git("merge", "-q", "--no-edit", "leaky", cwd=d)
            found = self._scan(d)
            self.assertEqual(sorted({f["File"] for f in found}), ["deploy.py"], "merged into HEAD's history, it is the commit's")


class ContextAndForms(unittest.TestCase):
    """The placeholder rules against the scanner's two kinds of rule. Every value is built at runtime:
    a literal in these shapes would trip secret scanners on this very file."""
    KEY_ID = "AKIA" + "Q7ZR4W2N" + "K5TM3XPB"          # an access key id's shape, no EXAMPLE in it
    PAT = "ghp_" + "Zq8vLm2Rt7Kp" * 3                  # a classic GitHub token's shape

    def test_a_word_inside_an_identifier_or_a_path_does_not_make_an_example_line(self):
        value = "nz5ej2kypkvcw0rn5cvhs6qxtm"
        self.assertFalse(leaks.is_placeholder(value, f"sample_rate = 0.1\napi_key = '{value}'"), "sample_rate names a rate, not this value")
        self.assertFalse(leaks.is_placeholder(value, f"# see examples/README for the setup\napi_key = '{value}'"), "a path, not a word")
        self.assertFalse(leaks.is_placeholder(value, f"fake_clock = Clock()\napi_key = '{value}'"))
        self.assertTrue(leaks.is_placeholder(value, f"# Example:\napi_key = '{value}'"), "a word of its own still calls it an example")
        self.assertTrue(leaks.is_placeholder(value, f"sampleApiKey = '{value}'"), "the value's own key calls it a sample")

    def test_a_provider_key_next_to_an_example_comment_is_still_a_key(self):
        """A gate fixture: a committed key under a comment that says "example" or "sample" must be caught."""
        for line in (f"# example config\nAWS_ACCESS_KEY_ID={self.KEY_ID}", f"sample_rate = 0.1\naws_key = '{self.KEY_ID}'",
                     f"# e.g. from the console\nkey = {self.KEY_ID}"):
            self.assertFalse(leaks.is_placeholder(self.KEY_ID, line, "deploy/env.sh", "aws-access-token"), line)
        self.assertFalse(leaks.is_placeholder(self.PAT, f"# see examples/README\nTOKEN = {self.PAT}", "ci/push.py", "github-pat"),
                         "a provider's key is judged by its own shape, not the words around it")
        self.assertTrue(leaks.is_placeholder("AKIA" + "IOSFODNN7" + "EXAMPLE", "", "", "aws-access-token"), "EXAMPLE in the value itself")
        self.assertTrue(leaks.is_placeholder("username:" + "fakepwd", "", "", "curl-auth-user"), "so is fake")
        self.assertFalse(leaks.is_placeholder("Zq8vLm2" + "fAkE" + "Rt7KpWn3", "", "", "square-access-token"), "not in mixed case")
        self.assertTrue(leaks.is_placeholder(self.KEY_ID, f"# Example:\nkey = {self.KEY_ID}", "", "generic-api-key"),
                        "a generic rule's value keeps its context")

    def test_a_match_inside_a_data_uri_is_image_bytes(self):
        payload = "iVBORw0KGgo" + "AAAANSUhEUgAAAB" + "BSA" + "Zq8vLm2Rt7KpWn3cXe9YbH4" + "AAAAAElFTkSuQmCC"
        line = f'      {{/* <img src="data:image/png;base64,{payload}" /> */}}'
        value = "BSA" + "Zq8vLm2Rt7KpWn3cXe9YbH4"
        self.assertTrue(leaks.is_placeholder(value, line, "ui/src/pages/offline/index.jsx", "brave-search-api-key"))
        self.assertFalse(leaks.is_placeholder(value, f"BRAVE_KEY = '{value}'", "ui/src/api.js", "brave-search-api-key"))

    def test_a_guid_in_a_table_of_guids_is_an_id_whichever_rule_matched_it(self):
        guid = "EAAAC2D7-C290-11D1-905D-00C04FD9189D"
        table = f"EAAAC2D6-C290-11D1-905D-00C04FD9189D IDXB\n{guid} IDXC"
        self.assertTrue(leaks.is_placeholder(guid, table, "data/iids.txt", "square-access-token"))
        self.assertFalse(leaks.is_placeholder(guid, f"# example\ntoken = {guid}", "app.py", "square-access-token"))

    def test_form_labels_and_hints_are_placeholders(self):
        # apache/devlake's connection forms: the labels a user reads, not the values they type
        self.assertTrue(leaks.is_placeholder("eg. " + "*" * 12, "    password: 'eg. " + "*" * 12 + "',"))
        self.assertTrue(leaks.is_placeholder("e.g. hunter2", ""))
        self.assertTrue(leaks.is_placeholder("*" * 12))
        self.assertTrue(leaks.is_placeholder("Enter Password"))
        self.assertTrue(leaks.is_placeholder("jenkins api access token"))
        self.assertTrue(leaks.is_placeholder("Token", "    token: 'Token',"), "a value that repeats its own key")
        self.assertTrue(leaks.is_placeholder("DB_PASS", '  "db.pass": "DB_PASS"'), "the same name in another case")
        self.assertFalse(leaks.is_placeholder("correct horse battery staple"), "a passphrase has spaces and names no credential")
        self.assertFalse(leaks.is_placeholder("my token is 7Hq2"), "a digit among the words: not a label")
        self.assertFalse(leaks.is_placeholder("Zq8vLm2Rt7Kp", "    token: 'Zq8vLm2Rt7Kp',"))
        self.assertFalse(leaks.is_placeholder("egg.Zq8vLm2Rt7Kp"), "eg. only as a word of its own")

    def test_a_private_key_block_is_not_prose(self):
        body = "MIIEpAIBAAKCAQEA" + "Zq8vLm2Rt7KpWn3c" * 8 + "fake"   # a long body can spell anything
        block = f"-----BEGIN RSA PRIVATE KEY-----\n{body}\n-----END RSA PRIVATE KEY-----"
        self.assertFalse(leaks.is_placeholder(block, "", "", "private-key"))

    def test_sanitise_judges_a_provider_rule_without_its_context(self):
        row = {"RuleID": "github-pat", "File": "ui/src/data/Blueprint.js", "Commit": "c1", "StartLine": 3, "Secret": self.PAT,
               "Line": f"// example blueprint\nurl: 'https://{self.PAT}@github.com/o/r.git',", "Attributes": {"confidence": "high"}}
        [clean] = leaks.sanitise([row])
        self.assertFalse(clean["Placeholder"])
        self.assertEqual(clean["Confidence"], "high")
        [clean] = leaks.sanitise([dict(row, RuleID="generic-api-key")])
        self.assertTrue(clean["Placeholder"], "the same line keeps a generic hit out")


class HeadlineOrder(unittest.TestCase):
    @staticmethod
    def row(value, file, rule, confidence, line=1, commit="c1"):
        return {"rule": rule, "file": file, "commit": commit, "line": line, "fingerprint": f"{commit}:{file}:{rule}:{line}",
                "value": value, "placeholder": False, "confidence": confidence}

    def test_the_strongest_value_comes_first(self):
        rows = [self.row("h1", "ui/src/data/Providers.js", "generic-password", "medium", n) for n in range(1, 8)]
        rows += [self.row("h2", "ui/src/data/Blueprint.js", "github-pat", "high"),
                 self.row("h3", "ui/src/data/Other.js", "generic-api-key", "high"),
                 self.row("h4", "ui/src/data/Low.js", "slack-webhook-url", "low")]
        self.assertEqual([g["value"] for g in leaks.group(rows)], ["h2", "h3", "h1", "h4"],
                         "the scanner's grade first, then a provider's rule before a generic one, then places")


class Declared(unittest.TestCase):
    """The repository's own declaration that a value is not a secret, at any commit of HEAD's history."""

    def repo(self, d):
        from tests.test_hygiene import Repo
        return Repo(d)

    def raw(self, repo, path, value, line=1):
        commit = repo.git("log", "-1", "--format=%H", "--", path).stdout.decode().strip()
        return {"RuleID": "posthog-project-api-key", "File": path, "Commit": commit, "StartLine": line, "Secret": value,
                "Fingerprint": f"{commit}:{path}:posthog-project-api-key:{line}"}

    def test_an_allowlist_regex_that_a_later_config_dropped_still_declares_the_value(self):
        old, new = "phc_" + FAKE, "phc_" + FAKE[::-1]
        with tempfile.TemporaryDirectory() as d:
            r = self.repo(d)
            r.write("app/analytics.py", f'TOKEN = "{old}"\n')
            r.commit(date="2026-01-01T00:00:00")
            first = self.raw(r, "app/analytics.py", old)
            r.write(".gitleaks.toml", "[extend]\nuseDefault = true\n\n[allowlist]\nregexes = [\n  # the public key\n  '''^" + old + "$''',\n]\n")
            r.commit(date="2026-01-02T00:00:00")
            declaring = r.git("rev-parse", "HEAD").stdout.decode().strip()
            r.write("app/analytics.py", f'TOKEN = "{new}"\n')
            r.write(".gitleaks.toml", "[allowlist]\nregexes = ['''^" + new + "$''']\n")
            r.commit(date="2026-01-03T00:00:00")
            other = dict(first, Secret="phc_" + "9" * 32)
            leaks.annotate(d, [first, other])
        self.assertEqual(first["Declared"], {"File": ".gitleaks.toml", "Commit": declaring, "How": "allowlist regex"})
        self.assertNotIn("Declared", other, "a value no version declared stays undeclared")
        self.assertNotIn(old, json.dumps(leaks.sanitise([first])), "the declaration names the file and commit, never the value")

    def test_a_marker_on_the_values_line_in_a_later_version_declares_it(self):
        value = "phc_" + FAKE
        with tempfile.TemporaryDirectory() as d:
            r = self.repo(d)
            r.write("web/a.ts", f"const T = '{value}';\n")
            r.commit(date="2026-01-01T00:00:00")
            row = self.raw(r, "web/a.ts", value)
            r.write("web/a.ts", f"const T = '{value}'; // gitleaks:allow publishable\n")
            r.commit(date="2026-01-02T00:00:00")
            marking = r.git("rev-parse", "HEAD").stdout.decode().strip()
            r.write("web/b.ts", "// gitleaks:allow on a line of its own\n")
            r.commit(date="2026-01-03T00:00:00")
            other = dict(row, Secret="phc_" + "9" * 32)
            leaks.annotate(d, [row, other])
        self.assertEqual(row["Declared"], {"File": "web/a.ts", "Commit": marking, "How": "gitleaks:allow"})
        self.assertNotIn("Declared", other, "the marker covers the value on its own line only")

    def test_stopwords_ignore_files_and_what_is_not_a_declaration(self):
        value = "sk_" + FAKE
        with tempfile.TemporaryDirectory() as d:
            r = self.repo(d)
            r.write("app/k.py", f'KEY = "{value}"\n')
            r.commit(date="2026-01-01T00:00:00")
            row = self.raw(r, "app/k.py", value)
            # a rule's own detection regex matches the value too, and says the opposite of allowed
            r.write(".gitleaks.toml", "[[rules]]\nid = \"x\"\nregex = '''sk_[0-9a-f]{32}'''\n")
            r.commit(date="2026-01-02T00:00:00")
            leaks.annotate(d, [row])
            self.assertNotIn("Declared", row, "a detection regex is not an allowlist")
            r.write(".gitleaks.toml", "[[allowlists]]\ncondition = \"AND\"\nstopwords = [\"" + FAKE[:10] + "\"]\npaths = ['''^docs/''']\n")
            r.commit(date="2026-01-03T00:00:00")
            leaks.annotate(d, [row])
            self.assertNotIn("Declared", row, "AND: the stopword matches, the path does not")
            os.remove(os.path.join(d, ".gitleaks.toml"))
            r.write(".betterleaksignore", "# reviewed\n" + row["Fingerprint"] + "\n")
            r.commit(date="2026-01-04T00:00:00")
            leaks.annotate(d, [row])
            self.assertEqual((row["Declared"]["File"], row["Declared"]["How"]), (".betterleaksignore", "fingerprint"))
            elsewhere = dict({k: v for k, v in row.items() if k != "Declared"}, Fingerprint="other")
            leaks.annotate(d, [elsewhere])
            self.assertNotIn("Declared", elsewhere, "an ignore file that names neither the value nor the place")
            r.write(".gitleaks.toml", "[[rules]]\nid = \"x\"\n[rules.allowlist]\nstopwords = [\"" + FAKE[:10] + "\"]\n")
            r.commit(date="2026-01-05T00:00:00")
            leaks.annotate(d, [elsewhere])
            self.assertEqual(elsewhere["Declared"]["How"], "allowlist stopword")

    def test_outside_a_repository_nothing_is_declared(self):
        with tempfile.TemporaryDirectory() as d:
            row = {"RuleID": "x", "File": "a.py", "Commit": "abc", "StartLine": 1, "Secret": FAKE}
            leaks.annotate(d, [row])
        self.assertNotIn("Declared", row)


class DeclaredToml(unittest.TestCase):
    def test_the_allowlist_tables_and_their_keys(self):
        text = ("title = 'x'\n[extend]\nuseDefault = true\n[allowlist]\ndescription = \"d\"\nregexes = ['''^a$''', # c\n  '''b\\.c''']\n"
                "stopwords = [\"s1\"]\n[[rules]]\nid = \"r\"\nregex = '''zzz'''\n[[rules.allowlists]]\nregexTarget = \"line\"\nregexes = [\"q\\\\d\"]\n"
                "[[allowlists]]\ncondition = \"AND\"\npaths = ['''^t/''']\ncommits = [\"abc\"]\n")
        lists = leaks.allowlists(text)
        self.assertEqual([(a["regexes"], a["stopwords"], a["paths"], a["commits"], a["target"], a["condition"]) for a in lists],
                         [(["^a$", "b\\.c"], ["s1"], [], [], "secret", "or"), (["q\\d"], [], [], [], "line", "or"), ([], [], ["^t/"], ["abc"], "secret", "and")],
                         "a basic string's escapes are TOML's; a literal string's are the regex's; a rule's detection regex is not read")


class AtHead(unittest.TestCase):
    def test_whether_heads_version_of_the_file_still_holds_the_value_and_where(self):
        from tests.test_hygiene import Repo
        gone, kept = "sk_" + FAKE, "sk_" + FAKE[::-1]
        with tempfile.TemporaryDirectory() as d:
            r = Repo(d)
            r.write("app/k.py", f'A = "{gone}"\nB = "{kept}"\n')
            r.commit(date="2026-01-01T00:00:00")
            first = r.git("rev-parse", "HEAD").stdout.decode().strip()
            r.write("app/k.py", f'# moved down\nA = "none"\n\nB = "{kept}"\nC = "{kept}"\n')
            r.commit(date="2026-01-02T00:00:00")
            rows = [{"RuleID": "x", "File": "app/k.py", "Commit": first, "StartLine": 1, "Secret": gone},
                    {"RuleID": "x", "File": "app/k.py", "Commit": first, "StartLine": 2, "Secret": kept},
                    {"RuleID": "x", "File": "app/k.py", "Commit": first, "StartLine": 5, "Secret": kept},
                    {"RuleID": "x", "File": "old/deleted.py", "Commit": first, "StartLine": 2, "Secret": kept},
                    {"RuleID": "x", "File": "(unreachable blob 0123456789ab)", "Commit": "", "StartLine": 2, "Secret": kept}]
            leaks.annotate(d, rows)
        self.assertEqual([(x["AtHead"], x.get("HeadLine")) for x in rows], [(False, None), (True, 4), (True, 5), (False, None), (False, None)],
                         "the file is in the tree for the first row, but the value is not; the second moved to line 4; "
                         "a row whose own line holds the value at HEAD keeps it")
        clean = leaks.sanitise(rows)
        self.assertNotIn(FAKE[::-1], json.dumps(clean))
        self.assertEqual(clean[1]["HeadLine"], 4)

    def test_outside_a_repository_it_is_left_out(self):
        with tempfile.TemporaryDirectory() as d:
            row = {"RuleID": "x", "File": "a.py", "Commit": "abc", "StartLine": 1, "Secret": FAKE}
            leaks.annotate(d, [row])
        self.assertNotIn("AtHead", row)

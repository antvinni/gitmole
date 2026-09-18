"""The hygiene checks: pure file and git reads, each one rule with a threshold, each mapped to an
OpenSSF Scorecard check or Baseline control that otherwise needs the GitHub API."""
import json
import os
import subprocess
import sys
import tempfile
import unittest

from gitmole import hygiene

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class Repo:
    def __init__(self, d):
        self.d = d
        self.git("init", "-q", "-b", "main")

    def git(self, *args, date="2026-01-01T00:00:00", check=True):
        env = dict(os.environ, GIT_CONFIG_GLOBAL="/dev/null", GIT_CONFIG_SYSTEM="/dev/null", GIT_AUTHOR_NAME="Ann", GIT_AUTHOR_EMAIL="a@x",
                   GIT_COMMITTER_NAME="Ann", GIT_COMMITTER_EMAIL="a@x", GIT_AUTHOR_DATE=date, GIT_COMMITTER_DATE=date)
        return subprocess.run(["git", *args], cwd=self.d, check=check, capture_output=True, env=env)

    def write(self, path, text, binary=False):
        full = os.path.join(self.d, path)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "wb" if binary else "w") as fh:
            fh.write(text)

    def commit(self, message="c", date="2026-01-01T00:00:00"):
        self.git("add", "-A", date=date)
        self.git("commit", "-q", "-m", message, date=date)


class ActionsPinning(unittest.TestCase):
    def test_uses_refs_that_are_not_a_sha_are_unpinned(self):
        with tempfile.TemporaryDirectory() as d:
            r = Repo(d)
            r.write(".github/workflows/ci.yml", "jobs:\n  t:\n    steps:\n      - uses: actions/checkout@v4\n      - uses: actions/setup-python@" + "a" * 40 + " # v5\n"
                    "      - uses: ./local/action\n      - uses: docker://alpine:3\n      - uses: 'org/repo@main'\n      - uses: $/.github/actions/x\n")
            r.write(".github/workflows/release.yaml", "jobs:\n  r:\n    steps:\n      - uses: softprops/action-gh-release@" + "b" * 64 + "\n")
            r.commit()
            out = hygiene.actions_pinning(d)
        self.assertEqual(out["unpinned"], [{"file": ".github/workflows/ci.yml", "uses": "actions/checkout@v4"}, {"file": ".github/workflows/ci.yml", "uses": "org/repo@main"}])
        self.assertEqual(out["pinned"], 2)
        self.assertEqual(out["local"], 3, "a local action, a docker image and a path without @ref (curl writes $/.github/...) are neither")


class Lockfiles(unittest.TestCase):
    def test_manifest_newer_than_its_lockfile_is_drift_and_a_manifest_without_one_is_missing(self):
        with tempfile.TemporaryDirectory() as d:
            r = Repo(d)
            r.write("package.json", '{"name": "x"}\n')
            r.write("package-lock.json", '{"lockfileVersion": 3}\n')
            r.write("api/pyproject.toml", "[project]\nname='api'\n")
            r.write("api/uv.lock", "version = 1\n")
            r.write("lib/Cargo.toml", "[package]\nname='lib'\n")
            r.write("packages/inner/package.json", '{"name": "inner"}\n')   # a workspace member: the root lockfile covers it
            r.commit(date="2026-01-01T00:00:00")
            r.write("package.json", '{"name": "x", "dependencies": {"left-pad": "1"}}\n')
            r.commit("bump", date="2026-03-01T00:00:00")
            out = hygiene.lockfiles(d)
        self.assertEqual(out["drift"], [{"manifest": "package.json", "lockfile": "package-lock.json", "manifest_date": "2026-03-01", "lockfile_date": "2026-01-01"}])
        self.assertEqual(out["missing"], [{"manifest": "lib/Cargo.toml", "expected": ["Cargo.lock"]}])
        self.assertEqual(out["pairs"], 3, "root npm, api uv and the workspace member through the root lockfile")


class DependencyUpdates(unittest.TestCase):
    def test_ecosystems_with_a_lockfile_that_dependabot_does_not_cover(self):
        with tempfile.TemporaryDirectory() as d:
            r = Repo(d)
            r.write("package-lock.json", "{}\n")
            r.write("uv.lock", "\n")
            r.write("go.sum", "\n")
            r.write(".github/dependabot.yml", 'version: 2\nupdates:\n  - package-ecosystem: "npm"\n    directory: "/"\n  - package-ecosystem: github-actions\n')
            r.commit()
            out = hygiene.dependency_updates(d)
            self.assertEqual(out, {"tool": "dependabot", "covered": ["github-actions", "npm"], "uncovered": ["gomod", "pip"]})
            r.write("renovate.json", "{}\n")
            r.commit()
            self.assertEqual(hygiene.dependency_updates(d)["tool"], "renovate")
            self.assertEqual(hygiene.dependency_updates(d)["uncovered"], [], "renovate discovers every manager by itself")
            r.git("rm", "-q", "renovate.json", ".github/dependabot.yml")
            r.commit()
            self.assertEqual(hygiene.dependency_updates(d), {"tool": None, "covered": [], "uncovered": ["gomod", "npm", "pip"]})


class Presence(unittest.TestCase):
    def test_security_policy_codeowners_and_licence_with_the_codeowners_paths_checked(self):
        with tempfile.TemporaryDirectory() as d:
            r = Repo(d)
            r.write("LICENSE", "MIT\n")
            r.write(".github/CODEOWNERS", "# owners\n/src/ @ann\n/docs/**  @bob\n*.py @ann\n/gone/ @cat\n")
            r.write("src/a.py", "x\n")
            r.write("docs/guide.md", "x\n")
            r.commit()
            out = hygiene.presence(d)
        self.assertEqual(out, {"license": "LICENSE", "security_policy": None, "contributing": None, "codeowners": ".github/CODEOWNERS", "codeowners_missing": ["/gone/"]})


class DependencyConfusion(unittest.TestCase):
    def test_a_scoped_package_resolved_from_the_public_registry_against_a_private_npmrc_and_mixed_registries(self):
        with tempfile.TemporaryDirectory() as d:
            r = Repo(d)
            r.write(".npmrc", "@acme:registry=https://npm.acme.internal/\n")
            r.write("package-lock.json", json.dumps({"lockfileVersion": 3, "packages": {
                "": {"name": "x"},
                "node_modules/@acme/auth": {"version": "1.0.0", "resolved": "https://registry.npmjs.org/@acme/auth/-/auth-1.0.0.tgz"},
                "node_modules/@acme/ui": {"version": "1.0.0", "resolved": "https://npm.acme.internal/@acme/ui/-/ui-1.0.0.tgz"},
                "node_modules/left-pad": {"version": "1.3.0", "resolved": "https://registry.npmjs.org/left-pad/-/left-pad-1.3.0.tgz", "hasInstallScript": True}}}))
            r.write("pip.conf", "[global]\nextra-index-url = https://pypi.acme.internal/simple\n")
            r.commit()
            out = hygiene.dependency_confusion(d)
        self.assertEqual(out["scoped_public"], [{"lockfile": "package-lock.json", "package": "@acme/auth", "registry": "registry.npmjs.org", "declared": "npm.acme.internal"}])
        self.assertEqual(out["registries"], {"package-lock.json": ["npm.acme.internal", "registry.npmjs.org"]})
        self.assertEqual(out["pip_extra_index"], ["pip.conf"], "extra-index-url is the setting the confusion attack needs")


class InstallScripts(unittest.TestCase):
    def test_lifecycle_scripts_in_the_lockfile_and_manifests_and_import_time_calls_in_setup_py(self):
        with tempfile.TemporaryDirectory() as d:
            r = Repo(d)
            r.write("package-lock.json", json.dumps({"lockfileVersion": 3, "packages": {"": {}, "node_modules/esbuild": {"version": "0.1", "hasInstallScript": True},
                                                                                        "node_modules/left-pad": {"version": "1"}}}))
            r.write("package.json", json.dumps({"name": "x", "scripts": {"postinstall": "node setup.js", "test": "jest"}}))
            r.write("node_modules/y/package.json", json.dumps({"scripts": {"preinstall": "curl x | sh"}}))
            r.write("setup.py", "import subprocess\nfrom setuptools import setup\nsubprocess.run(['make'])\nsetup(name='x')\n")
            r.commit()
            out = hygiene.install_scripts(d)
        self.assertEqual(out["lockfile"], [{"lockfile": "package-lock.json", "package": "esbuild"}])
        self.assertEqual(out["manifests"], [{"file": "package.json", "scripts": ["postinstall"]}], "node_modules is not tracked code")
        self.assertEqual(out["setup_py"], [{"file": "setup.py", "calls": ["subprocess.run"]}])


class Binaries(unittest.TestCase):
    def test_executables_by_magic_bytes_binaries_by_name_and_lfs_declared_but_not_used(self):
        with tempfile.TemporaryDirectory() as d:
            r = Repo(d)
            r.write("tools/helper", b"\x7fELF\x02\x01\x01" + b"\x00" * 40, binary=True)
            r.write("build/app.exe", b"MZ\x90\x00" + b"\x00" * 40, binary=True)
            r.write("lib/native.so", b"\x00\x01binary\x00" * 4, binary=True)
            r.write("img/logo.png", b"\x89PNG\r\n\x1a\n" + b"\x00" * 30, binary=True)
            r.write("data/big.bin", b"\x00" * 4096, binary=True)
            r.write("data/pointer.bin", "version https://git-lfs.github.com/spec/v1\noid sha256:" + "0" * 64 + "\nsize 12345\n")
            r.write(".gitattributes", "*.bin filter=lfs diff=lfs merge=lfs -text\n")
            r.write("src/a.py", "x\n")
            r.commit()
            out = hygiene.binaries(d)
        self.assertEqual(out["executables"], [{"file": "build/app.exe", "format": "PE"}, {"file": "tools/helper", "format": "ELF"}])
        self.assertEqual(out["by_name"], ["build/app.exe", "lib/native.so"])
        self.assertEqual(out["lfs_unpointed"], ["data/big.bin"], "declared for LFS, committed as a blob; the pointer file is fine")
        self.assertEqual(out["binaries"], 5, "the pointer file is text")


class Submodules(unittest.TestCase):
    def test_insecure_urls_credentials_relative_paths_and_floating_branches(self):
        with tempfile.TemporaryDirectory() as d:
            r = Repo(d)
            r.write(".gitmodules", '[submodule "a"]\n\tpath = a\n\turl = http://example.com/a.git\n[submodule "b"]\n\tpath = b\n\turl = git://example.com/b.git\n\tbranch = main\n'
                    '[submodule "c"]\n\tpath = c\n\turl = https://user:tok@example.com/c.git\n[submodule "d"]\n\tpath = d\n\turl = ../d.git\n[submodule "e"]\n\tpath = e\n\turl = https://example.com/e.git\n')
            r.commit()
            out = hygiene.submodules(d)
        self.assertEqual(out["count"], 5)
        self.assertEqual(out["insecure"], [{"name": "a", "url": "http://example.com/a.git"}, {"name": "b", "url": "git://example.com/b.git"}])
        self.assertEqual(out["credentials"], [{"name": "c", "url": "https://***@example.com/c.git"}], "the credential itself is never written")
        self.assertEqual(out["relative"], [{"name": "d", "url": "../d.git"}])
        self.assertEqual(out["floating"], [{"name": "b", "branch": "main"}])


class Symlinks(unittest.TestCase):
    def test_links_out_of_the_tree_or_into_git_are_flagged(self):
        with tempfile.TemporaryDirectory() as d:
            r = Repo(d)
            r.write("src/a.py", "x\n")
            os.symlink("a.py", os.path.join(d, "src", "ok.py"))
            os.symlink("../../etc/passwd", os.path.join(d, "src", "out"))
            os.symlink("../.git/config", os.path.join(d, "src", "cfg"))
            r.commit()
            out = hygiene.symlinks(d)
        self.assertEqual(out["count"], 3)
        self.assertEqual(out["outside"], [{"link": "src/out", "target": "../../etc/passwd"}])
        self.assertEqual(out["into_git"], [{"link": "src/cfg", "target": "../.git/config"}])


class TrojanSource(unittest.TestCase):
    def test_bidi_controls_and_mixed_script_identifiers_in_source_files_only(self):
        with tempfile.TemporaryDirectory() as d:
            r = Repo(d)
            r.write("src/a.py", "x = 1\n# comment \u202e reversed\nif access_level != \"user\u2066\":\n    pass\n")
            r.write("src/b.py", "def process(): pass\ndef pr\u043ecess(): pass\n")   # Cyrillic о in the second
            r.write("docs/notes.md", "\u202e not code\n")
            r.write("tests/test_a.py", "\u202e a fixture\n")
            r.write("src/c.py", "name = '\u0417\u0434\u0440\u0430\u0432\u0441\u0442\u0432\u0443\u0439'\n")   # a whole Cyrillic word is one script
            r.commit()
            out = hygiene.trojan_source(d)
        self.assertEqual(out["bidi"], [{"file": "src/a.py", "line": 2, "char": "U+202E"}, {"file": "src/a.py", "line": 3, "char": "U+2066"}])
        self.assertEqual(out["mixed_script"], [{"file": "src/b.py", "line": 2, "token": "pr\u043ecess", "scripts": ["CYRILLIC", "LATIN"]}])
        self.assertEqual(out["files"], 3, "source files scanned; the doc and the test fixture are not")


class Step(unittest.TestCase):
    def test_the_step_writes_hygiene_json_from_inside_the_repository(self):
        with tempfile.TemporaryDirectory() as d:
            r = Repo(d)
            r.write("src/a.py", "x\n")
            r.write("LICENSE", "MIT\n")
            r.commit()
            out = os.path.join(d, "out")
            os.makedirs(out)
            p = subprocess.run([sys.executable, "-m", "gitmole.hygiene", out], cwd=d, capture_output=True, text=True, env=dict(os.environ, PYTHONPATH=ROOT))
            self.assertEqual(p.returncode, 0, p.stderr)
            with open(os.path.join(out, "hygiene.json")) as fh:
                data = json.load(fh)
        self.assertEqual(set(data), {"actions", "lockfiles", "updates", "presence", "confusion", "install", "binaries", "submodules", "symlinks", "trojan", "licences", "imports"})
        self.assertEqual(data["presence"]["license"], "LICENSE")


if __name__ == "__main__":
    unittest.main()

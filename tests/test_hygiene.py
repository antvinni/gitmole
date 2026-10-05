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
        handed = {"secrets": False, "grants": False}
        self.assertEqual(out["unpinned"], [{"file": ".github/workflows/ci.yml", "uses": "actions/checkout@v4", "line": 4, "ref": "version", **handed},
                                           {"file": ".github/workflows/ci.yml", "uses": "org/repo@main", "line": 8, "ref": "branch", **handed}],
                         "each at the line of its uses:")
        self.assertEqual(out["pinned"], 2)
        self.assertEqual(out["local"], 3, "a local action, a docker image and a path without @ref (curl writes $/.github/...) are neither")
        self.assertIsNone(out["origin"], "no origin remote")

    def test_the_origin_owner_is_read_from_the_remote_without_the_rest_of_the_url(self):
        cases = {"https://github.com/apache/devlake": {"host": "github.com", "owner": "apache"},
                 "https://x-access-token:s3cret@GitHub.com/apache/devlake.git": {"host": "github.com", "owner": "apache"},
                 "git@github.com:Homebrew/brew.git": {"host": "github.com", "owner": "Homebrew"},
                 "ssh://git@github.com:22/tokio-rs/tokio.git": {"host": "github.com", "owner": "tokio-rs"},
                 "/tmp/clones/devlake": None, "file:///tmp/clones/devlake": None, "https://example.org/repo.git": None}
        for url, expected in cases.items():
            with tempfile.TemporaryDirectory() as d:
                Repo(d)
                subprocess.run(["git", "remote", "add", "origin", url], cwd=d, check=True, capture_output=True)
                self.assertEqual(hygiene.origin_owner(d), expected, url)

    def rows(self, text):
        with tempfile.TemporaryDirectory() as d:
            r = Repo(d)
            r.write(".github/workflows/w.yml", text)
            r.commit()
            return {u["line"]: (u["uses"], u["ref"], u["secrets"], u["grants"]) for u in hygiene.actions_pinning(d)["unpinned"]}

    def test_a_ref_is_a_version_only_when_shaped_like_one(self):
        refs = ["v7", "1.2.3", "v1.0.0", "main", "release/v1", "stable", "v2-beta", "a1b2c3d"]
        got = self.rows("jobs:\n  t:\n    steps:\n" + "".join(f"      - uses: o/a@{r}\n" for r in refs))
        self.assertEqual([got[n + 4][1] for n in range(len(refs))], ["version"] * 3 + ["branch"] * 5,
                         "@v7, @1.2.3 and @v1.0.0 are release-shaped; a branch, a path-like ref, a suffix and a short sha are not")

    def test_a_step_is_handed_secrets_through_its_own_with_or_env_or_the_env_it_inherits(self):
        got = self.rows("""jobs:
  own:
    steps:
      - name: with
        uses: o/with@v1
        with:
          token: ${{ secrets.TOKEN }}
      - uses: o/env@v1
        env:
          TOKEN: ${{ secrets.TOKEN }}
      - uses: o/plain@v1
        with:
          token: ${{ github.token }}
        if: ${{ secrets.TOKEN != '' }}
      # with: ${{ secrets.TOKEN }}
  inherited:
    env:
      TURBO_TOKEN: ${{ secrets.TURBO_TOKEN }}
    steps:
      - uses: o/job-env@v1
  caller:
    uses: o/repo/.github/workflows/r.yml@main
    secrets: inherit
  quiet-caller:
    uses: o/repo/.github/workflows/q.yml@main
    with:
      level: 1
""")
        self.assertEqual({v[0]: v[2] for v in got.values()},
                         {"o/with@v1": True, "o/env@v1": True, "o/plain@v1": False, "o/job-env@v1": True,
                          "o/repo/.github/workflows/r.yml@main": True, "o/repo/.github/workflows/q.yml@main": False},
                         "an if: or a comment that names a secret hands the action nothing")
        workflow_env = self.rows("env:\n  TOKEN: ${{ secrets.TOKEN }}\njobs:\n  t:\n    steps:\n      - uses: o/a@v1\n")
        self.assertTrue(workflow_env[6][2], "the workflow's env: is inherited too")

    def test_a_token_that_can_write_comes_from_the_job_or_else_the_workflow(self):
        got = self.rows("""permissions:
  contents: write
jobs:
  inherits:
    steps:
      - uses: o/inherits@v1
  narrows:
    permissions:
      contents: read
    steps:
      - uses: o/narrows@v1
  oidc:
    permissions:
      id-token: write
      contents: read
    steps:
      - uses: o/oidc@v1
  all:
    permissions: write-all
    steps:
      - uses: o/all@v1
  comments:
    permissions: { pull-requests: write }
    steps:
      - uses: o/comments@v1
""")
        self.assertEqual({v[0]: v[3] for v in got.values()},
                         {"o/inherits@v1": True, "o/narrows@v1": False, "o/oidc@v1": True, "o/all@v1": True, "o/comments@v1": False},
                         "a job's own permissions replace the workflow's; pull-requests: write can neither push nor mint a cloud token")
        self.assertEqual({v[3] for v in self.rows("jobs:\n  t:\n    steps:\n      - uses: o/a@v1\n").values()}, {False},
                         "no permissions declared: what the token can do is the repository's setting, which the files do not say")

    def test_a_composite_action_is_read_like_a_workflow_and_other_action_files_are_not(self):
        composite = ("name: setup\nruns:\n  using: composite\n  steps:\n    - uses: pnpm/setup@v2\n      with:\n        install: false\n"
                     "    - uses: actions/cache/restore@" + "c" * 40 + "\n    - run: echo ${{ github.event.issue.title }}\n      shell: bash\n")
        with tempfile.TemporaryDirectory() as d:
            r = Repo(d)
            r.write(".github/workflows/ci.yml", "jobs:\n  t:\n    steps:\n      - uses: ./.github/actions/setup\n")
            r.write(".github/actions/setup/action.yml", composite)
            r.write("action.yaml", composite.replace("pnpm/setup@v2", "o/root@main"))
            r.write("js/action.yml", "name: js\nruns:\n  using: node20\n  main: index.js\nuses: o/never@v1\n")
            r.write("tests/fixtures/action.yml", composite.replace("pnpm/setup@v2", "o/fixture@v1"))
            r.write("docs/action.yml.md", composite)
            r.commit()
            out = hygiene.actions_pinning(d)
        self.assertEqual([(u["file"], u["uses"], u["line"], u["ref"]) for u in out["unpinned"]],
                         [(".github/actions/setup/action.yml", "pnpm/setup@v2", 5, "version"), ("action.yaml", "o/root@main", 5, "branch")],
                         "a JavaScript action has no steps; a test fixture is a specimen")
        self.assertEqual((out["pinned"], out["local"]), (2, 1))
        self.assertEqual(out["injection_count"], 0, "workflow_shapes reads workflows only: a composite action has no trigger of its own")


PWN = """name: preview
on:
  pull_request_target:
    types: [opened, synchronize]
permissions:
  contents: read
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - name: Check out the pull request
        uses: actions/checkout@v4
        with:
          ref: ${{ github.event.pull_request.head.sha }}
      - run: npm ci && npm test
"""

# react's sizebot shape: under workflow_run, the head's sha is a value (an artifact lookup, a comment), never the checkout's ref
SIZEBOT = """on:
  workflow_run:
    workflows: [build]
    types: [completed]
jobs:
  comment:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      # ref: ${{ github.event.workflow_run.head_sha }} would check out the fork
      - name: Download
        env:
          SHA: ${{ github.event.workflow_run.head_sha }}
        run: |
          gh run download --name "sizes-${{ github.event.workflow_run.head_sha }}"
      - uses: actions/checkout@v4
        with:
          ref: builds/facebook-www
"""

INJECTION = """on: [issues, pull_request]
jobs:
  triage:
    runs-on: ubuntu-latest
    steps:
      - run: echo "${{ github.event.issue.title }}"
      - name: Branch
        run: |
          echo building
          git push origin "HEAD:refs/heads/${{github.event.pull_request.head.ref}}"
      - run: echo "${{ github.event.inputs.tag }}" "${{ github.event.pull_request.number }}"
      - if: ${{ !contains(github.event.head_commit.message, 'ci skip') }}
        env:
          TITLE: ${{ github.event.pull_request.title }}
        run: echo "$TITLE"
      - run: printf '%s' "${{ github.event.commits[0].message }}" "${{ github.head_ref }}"
"""


class WorkflowShapes(unittest.TestCase):
    def test_a_checkout_of_the_pull_requests_head_under_pull_request_target_is_a_pwn_request(self):
        out = hygiene.workflow_shapes(".github/workflows/preview.yml", PWN)
        self.assertEqual(out["pwn_request"], [{"file": ".github/workflows/preview.yml", "job": "build", "line": 14, "key": "ref",
                                               "field": "github.event.pull_request.head.sha", "triggers": ["pull_request_target"]}])
        self.assertEqual(out["injection"], [])

    def test_workflow_run_and_the_repository_key_and_the_inline_trigger_forms(self):
        text = ("on: [push, workflow_run]\njobs:\n  deploy:\n    steps:\n      - uses: actions/checkout@v4\n        with:\n"
                "          repository: ${{ github.event.workflow_run.head_repository.full_name }}\n          ref: ${{ github.event.workflow_run.head_sha }}\n")
        rows = hygiene.workflow_shapes("w.yml", text)["pwn_request"]
        self.assertEqual([(r["job"], r["line"], r["key"]) for r in rows], [("deploy", 7, "repository"), ("deploy", 8, "ref")])
        self.assertEqual(rows[0]["triggers"], ["workflow_run"])

    def test_the_heads_sha_used_as_a_value_is_not_one(self):
        self.assertEqual(hygiene.workflow_shapes("w.yml", SIZEBOT), {"pwn_request": [], "injection": []})

    def test_the_same_checkout_under_pull_request_is_not_one(self):
        """on: pull_request gives a fork's run no secrets: checking out its head there is the normal case (etcd)."""
        self.assertEqual(hygiene.workflow_shapes("w.yml", PWN.replace("pull_request_target", "pull_request"))["pwn_request"], [])

    def test_a_ref_in_another_step_is_not_the_checkouts(self):
        text = ("on: pull_request_target\njobs:\n  a:\n    steps:\n      - uses: actions/checkout@v4\n"
                "      - uses: some/action@v1\n        with:\n          ref: ${{ github.event.pull_request.head.sha }}\n")
        self.assertEqual(hygiene.workflow_shapes("w.yml", text)["pwn_request"], [])

    def test_an_outsiders_field_straight_in_a_run_script_is_an_injection(self):
        rows = hygiene.workflow_shapes(".github/workflows/triage.yml", INJECTION)["injection"]
        self.assertEqual([(r["line"], r["field"], r["job"]) for r in rows],
                         [(6, "github.event.issue.title", "triage"), (10, "github.event.pull_request.head.ref", "triage"),
                          (16, "github.event.commits[0].message", "triage"), (16, "github.head_ref", "triage")],
                         "not inputs.* (only a writer sets it), not a number, not an if: or an env: value")

    def test_the_walk_carries_both_shapes_beside_the_pins(self):
        with tempfile.TemporaryDirectory() as d:
            r = Repo(d)
            r.write(".github/workflows/preview.yml", PWN)
            r.write(".github/workflows/triage.yml", INJECTION)
            r.write(".github/workflows/sizebot.yml", SIZEBOT)
            r.commit()
            out = hygiene.actions_pinning(d)
        self.assertEqual((out["pwn_request_count"], out["injection_count"]), (1, 4))
        self.assertEqual(out["unpinned_count"], 3, "the pins are counted as before")


class Lockfiles(unittest.TestCase):
    def test_manifest_newer_than_its_lockfile_is_drift_and_a_manifest_without_one_is_missing(self):
        with tempfile.TemporaryDirectory() as d:
            r = Repo(d)
            r.write("package.json", '{"name": "x"}\n')
            r.write("package-lock.json", '{"lockfileVersion": 3}\n')
            r.write("api/pyproject.toml", "[project]\nname='api'\n")
            r.write("api/uv.lock", "version = 1\n")
            r.write("lib/Cargo.toml", "[package]\nname='lib'\n\n[dependencies]\nserde = '1'\n")
            r.write("packages/inner/package.json", '{"name": "inner"}\n')   # a workspace member: the root lockfile covers it
            r.commit(date="2026-01-01T00:00:00")
            r.write("package.json", '{"name": "x", "dependencies": {"left-pad": "1"}}\n')
            r.commit("bump", date="2026-03-01T00:00:00")
            out = hygiene.lockfiles(d)
            bump = r.git("rev-parse", "HEAD").stdout.decode().strip()
        self.assertEqual(out["drift"], [{"manifest": "package.json", "lockfile": "package-lock.json", "manifest_date": "2026-03-01", "lockfile_date": "2026-01-01",
                                         "changes": [{"commit": bump, "date": "2026-03-01"}]}])
        self.assertEqual(out["missing"], [{"manifest": "lib/Cargo.toml", "expected": ["Cargo.lock"]}])
        self.assertEqual(out["pairs"], 3, "root npm, api uv and the workspace member through the root lockfile")

    def test_a_go_mod_that_requires_nothing_needs_no_go_sum(self):
        # paperclip's tools/agent-shim/go.mod: a module line and a go line, stdlib only
        with tempfile.TemporaryDirectory() as d:
            r = Repo(d)
            r.write("shim/go.mod", "module example.com/x/shim\n\ngo 1.22\n// require nothing yet\n")
            r.write("tool/go.mod", "module example.com/x/tool\n\ngo 1.22\n\nrequire (\n\tgolang.org/x/text v0.3.0\n)\n")
            r.write("one/go.mod", "module example.com/x/one\n\nrequire golang.org/x/text v0.3.0\n")
            r.commit()
            out = hygiene.lockfiles(d)
        self.assertEqual([m["manifest"] for m in out["missing"]], ["one/go.mod", "tool/go.mod"])
        self.assertEqual(out["nothing_to_lock"], ["shim/go.mod"])

    def test_a_manifest_that_declares_nothing_to_lock_is_not_missing_a_lock(self):
        """superpowers' root package.json: a name, a version and a `main`, no dependency of any kind. The report said
        "package.json has no package-lock.json" and OSPS-QA-02.01 read as a gap; there is nothing to pin."""
        declares_nothing = {
            "package.json": '{"name": "x", "version": "1.0.0", "main": "x.js", "dependencies": {}, "scripts": {"test": "node t.js"}}\n',
            "crate/Cargo.toml": "[package]\nname = 'x'\nversion = '0.1.0'\nedition = '2021'\n\n[dependencies]\n# none yet\n\n[features]\ndefault = []\n",
            "php/composer.json": '{"name": "a/b", "require": {"php": ">=8.1", "ext-json": "*"}}\n',
            "py/Pipfile": "[[source]]\nurl = 'https://pypi.org/simple'\n\n[packages]\n\n[dev-packages]\n\n[requires]\npython_version = '3.12'\n",
        }
        declares = {
            "a/package.json": '{"name": "a", "devDependencies": {"left-pad": "1"}}\n',
            "b/package.json": '{"name": "b", "peerDependencies": {"react": "*"}}\n',
            "c/package.json": '{"name": "c", "workspaces": ["packages/*"]}\n',
            "d/package.json": '{"name": "d", ',   # does not parse: says nothing about what it declares
            "e/Cargo.toml": "[package]\nname = 'e'\n\n[dev-dependencies]\ntempfile = '3'\n",
            "f/Cargo.toml": "[workspace]\nmembers = ['x']\n",
            "g/Cargo.toml": "[package]\nname = 'g'\n\n[target.'cfg(unix)'.dependencies]\nlibc = '0.2'\n",
            "h/composer.json": '{"require": {"php": ">=8.1", "monolog/monolog": "^3"}}\n',
            "i/Pipfile": "[packages]\nrequests = '*'\n",
            "j/Gemfile": "source 'https://rubygems.org'\n",   # Ruby, not data: not read
        }
        with tempfile.TemporaryDirectory() as d:
            r = Repo(d)
            for path, text in {**declares_nothing, **declares}.items():
                r.write(path, text)
            r.commit()
            out = hygiene.lockfiles(d)
        self.assertEqual(out["nothing_to_lock"], sorted(declares_nothing))
        self.assertEqual([m["manifest"] for m in out["missing"]], sorted(declares))
        self.assertEqual(out["pairs"], 0)

    def test_a_change_the_lock_does_not_record_is_not_drift(self):
        # devlake's backend/go.mod "changed on 2026-09-02, after go.sum": the module rename, one line
        with tempfile.TemporaryDirectory() as d:
            r = Repo(d)
            r.write("go.mod", "module example.com/incubator-x\n\ngo 1.26\n\nrequire golang.org/x/text v0.3.0\n")
            r.write("go.sum", "golang.org/x/text v0.3.0 h1:abc=\n")
            r.write("web/package.json", '{"name": "web", "scripts": {"build": "vite"}, "dependencies": {"vite": "5"}}\n')
            r.write("web/package-lock.json", '{"lockfileVersion": 3}\n')
            r.commit(date="2026-01-01T00:00:00")
            r.write("go.mod", "module example.com/x // renamed\n\ngo 1.26\n\nrequire golang.org/x/text v0.3.0\n")
            r.write("web/package.json", '{\n  "name": "web",\n  "scripts": {"build": "vite build"},\n  "dependencies": {"vite": "5"}\n}\n')
            r.commit("rename the module, reformat", date="2026-03-01T00:00:00")
            self.assertEqual(hygiene.lockfiles(d)["drift"], [])
            r.write("go.mod", "module example.com/x\n\ngo 1.26\n\nrequire golang.org/x/text v0.4.0\n")
            r.commit("bump", date="2026-04-01T12:00:00")
            bump = r.git("rev-parse", "HEAD").stdout.decode().strip()
            r.write("go.mod", "module example.com/y\n\ngo 1.26\n\nrequire golang.org/x/text v0.4.0\n")
            r.commit("rename again", date="2026-05-01T12:00:00")
            drift = hygiene.lockfiles(d)["drift"]
        self.assertEqual(drift, [{"manifest": "go.mod", "lockfile": "go.sum", "manifest_date": "2026-04-01", "lockfile_date": "2026-01-01",
                                  "changes": [{"commit": bump, "date": "2026-04-01"}]}], "dated by the change the lock records, not the rename after it")


    def test_a_cargo_toml_change_the_lock_does_not_resolve_is_not_drift(self):
        # VoiceStudio's native/desktop-bridge/Cargo.toml: one comment above global-hotkey reworded after Cargo.lock
        base = ('[package]\nname = "bridge"\nversion = "0.1.0"\ndescription = "x"\n\n[dependencies]\n'
                '# Same backend already pinned elsewhere.\nglobal-hotkey = "=0.8.0"\nurl = { git = "https://h/r#frag" }\n\n'
                '[target.\'cfg(unix)\'.dependencies]\nlibc = "0.2"\n\n[features]\ndefault = []\n\n[profile.release]\nlto = true\n')
        with tempfile.TemporaryDirectory() as d:
            r = Repo(d)
            r.write("Cargo.toml", base)
            r.write("Cargo.lock", "version = 4\n")
            r.commit(date="2026-09-18T00:00:00")
            r.write("Cargo.toml", base.replace("# Same backend already pinned elsewhere.", "# Native global-shortcut backend.")
                    .replace('description = "x"', 'description = "y"').replace("default = []", 'default = ["fast"]').replace("lto = true", "lto = false")
                    .replace('"=0.8.0"\n', '"=0.8.0"   # pinned\n'))
            r.commit("comments, description, features, profile", date="2026-09-26T00:00:00")
            self.assertEqual(hygiene.lockfiles(d)["drift"], [])
            r.write("Cargo.toml", base.replace('libc = "0.2"', 'libc = "0.3"'))
            r.commit("a target dependency", date="2026-09-27T12:00:00")
            bump = r.git("rev-parse", "HEAD").stdout.decode().strip()
            r.write("Cargo.toml", base.replace('libc = "0.2"', 'libc = "0.3"').replace('version = "0.1.0"', 'version = "0.2.0"'))
            r.commit("the version, which the lock records", date="2026-09-28T12:00:00")
            release = r.git("rev-parse", "HEAD").stdout.decode().strip()
            drift = hygiene.lockfiles(d)["drift"]
        self.assertEqual(drift[0]["changes"], [{"commit": release, "date": "2026-09-28"}, {"commit": bump, "date": "2026-09-27"}])

    def test_a_workspace_member_is_pinned_by_the_roots_lock_even_with_one_of_its_own(self):
        # VoiceStudio: the root package.json declares "workspaces": ["electron"]; CI installs from the root
        # bun.lock frozen, and electron/bun.lock is a stale leftover the finding told the reader to regenerate
        with tempfile.TemporaryDirectory() as d:
            r = Repo(d)
            r.write("package.json", json.dumps({"name": "mono", "workspaces": ["electron", "packages/*", "!packages/legacy"]}))
            r.write("bun.lock", "{}\n")
            r.write("electron/package.json", '{"name": "e"}\n')
            r.write("electron/bun.lock", "{}\n")
            r.write("packages/a/package.json", '{"name": "a"}\n')
            r.write("packages/a/bun.lock", "{}\n")
            r.write("packages/a/tools/package.json", '{"name": "t"}\n')   # `*` does not cross a directory
            r.write("packages/a/tools/bun.lock", "{}\n")
            r.write("packages/legacy/package.json", '{"name": "l"}\n')   # excluded by "!packages/legacy"
            r.write("packages/legacy/bun.lock", "{}\n")
            r.write("site/package.json", json.dumps({"name": "site", "workspaces": {"packages": ["apps/**"]}}))
            r.write("site/yarn.lock", "\n")
            r.write("site/apps/web/ui/package.json", '{"name": "ui"}\n')
            r.write("site/apps/web/ui/yarn.lock", "\n")
            r.commit(date="2026-09-14T00:00:00")
            for m in ("electron", "packages/a", "packages/a/tools", "packages/legacy", "site/apps/web/ui"):
                r.write(f"{m}/package.json", json.dumps({"name": m, "dependencies": {"left-pad": "1"}}))
            r.write("bun.lock", '{"lockfileVersion": 1}\n')
            r.write("site/yarn.lock", "# updated\n")
            r.commit("members add a dependency; the roots relock", date="2026-09-26T00:00:00")
            r.write("packages/a/tools/package.json", json.dumps({"name": "t", "dependencies": {"left-pad": "2"}}))
            r.write("packages/legacy/package.json", json.dumps({"name": "l", "dependencies": {"left-pad": "2"}}))
            r.commit("later", date="2026-09-28T00:00:00")
            out = hygiene.lockfiles(d)
        self.assertEqual([(x["manifest"], x["lockfile"]) for x in out["drift"]],
                         [("packages/a/tools/package.json", "packages/a/tools/bun.lock"), ("packages/legacy/package.json", "packages/legacy/bun.lock")],
                         "electron, packages/a and site/apps/web/ui are members their roots relocked; the rest keep their own lock")

    ROOT_MANIFEST = {"name": "mono", "version": "1.0.0", "private": True, "workspaces": ["packages/*"], "packageManager": "pnpm@9.1.0",
                     "pnpm": {"overrides": {"left-pad": "1.3.0"}}, "devDependencies": {"typescript": "5.4.0"}}
    MEMBER_MANIFEST = {"name": "@mono/a", "version": "1.0.0", "dependencies": {"left-pad": "^1.0.0"},
                       "peerDependencies": {"react": "*"}, "peerDependenciesMeta": {"react": {"optional": True}},
                       "dependenciesMeta": {"left-pad": {"injected": False}}}

    def _drift_after(self, lock, root=None, member=None):
        """The (manifest, lockfile) drift pairs after one commit that rewrites the root and member manifests
        of a workspace locked by `lock` at its root, a month after the lock's last commit."""
        with tempfile.TemporaryDirectory() as d:
            r = Repo(d)
            r.write("package.json", json.dumps(self.ROOT_MANIFEST, indent=2))
            r.write("packages/a/package.json", json.dumps(self.MEMBER_MANIFEST, indent=2))
            if lock == "pnpm-lock.yaml":
                r.write("pnpm-workspace.yaml", "packages:\n  - packages/*\n")
            r.write(lock, "lockfileVersion: '9.0'\n")
            r.commit(date="2026-09-01T00:00:00")
            r.write("package.json", json.dumps(root or self.ROOT_MANIFEST, indent=2))
            r.write("packages/a/package.json", json.dumps(member or self.MEMBER_MANIFEST, indent=2))
            r.git("add", "-A")
            r.git("commit", "-q", "--allow-empty", "-m", "change", date="2026-10-01T00:00:00")
            return sorted((x["manifest"], x["lockfile"]) for x in hygiene.lockfiles(d)["drift"])

    def test_pnpm_lock_does_not_record_a_name_or_a_version(self):
        """univer: 82 package.json files "changed after pnpm-lock.yaml" — every member's release bump. pnpm-lock.yaml
        records each importer's dependency specifiers, never its name or version, so a bump cannot put it behind."""
        bumped_root = dict(self.ROOT_MANIFEST, name="mono-renamed", version="1.1.0", scripts={"build": "tsc"})
        bumped_member = dict(self.MEMBER_MANIFEST, name="@mono/a2", version="1.1.0", description="now described")
        self.assertEqual(self._drift_after("pnpm-lock.yaml", bumped_root, bumped_member), [])
        moved_member = dict(self.MEMBER_MANIFEST, packageManager="pnpm@9.2.0")
        self.assertEqual(self._drift_after("pnpm-lock.yaml", member=moved_member), [],
                         "pnpm reads packageManager from the workspace root only")

    def test_pnpm_lock_still_drifts_on_what_it_records(self):
        both = [("package.json", "pnpm-lock.yaml"), ("packages/a/package.json", "pnpm-lock.yaml")]
        root_only, member_only = both[:1], both[1:]
        cases = {
            "member dependency": ({}, {"dependencies": {"left-pad": "^1.1.0"}}, member_only),
            "member peerDependenciesMeta": ({}, {"peerDependenciesMeta": {"react": {"optional": False}}}, member_only),
            "member dependenciesMeta": ({}, {"dependenciesMeta": {"left-pad": {"injected": True}}}, member_only),
            "root devDependency": ({"devDependencies": {"typescript": "5.5.0"}}, {}, root_only),
            "root packageManager": ({"packageManager": "pnpm@9.2.0"}, {}, root_only),
            "root pnpm.overrides": ({"pnpm": {"overrides": {"left-pad": "1.3.1"}}}, {}, root_only),
            "a version bump beside a dependency change": ({"version": "2.0.0"}, {"version": "2.0.0", "optionalDependencies": {"fsevents": "2"}}, member_only),
        }
        for label, (root, member, expected) in cases.items():
            with self.subTest(label):
                self.assertEqual(self._drift_after("pnpm-lock.yaml", dict(self.ROOT_MANIFEST, **root), dict(self.MEMBER_MANIFEST, **member)), expected)

    def test_npm_yarn_and_bun_locks_keep_the_name_and_version(self):
        """package-lock.json and npm-shrinkwrap.json record the root's and each workspace's name and version, so a
        version-only bump still puts them behind; yarn.lock and bun.lock keep that reading until a fixture shows theirs."""
        for lock in ("package-lock.json", "npm-shrinkwrap.json", "yarn.lock", "bun.lock"):
            with self.subTest(lock):
                self.assertEqual(self._drift_after(lock, dict(self.ROOT_MANIFEST, version="1.1.0"), dict(self.MEMBER_MANIFEST, version="1.1.0")),
                                 [("package.json", lock), ("packages/a/package.json", lock)])


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

    def test_github_actions_is_uncovered_only_when_a_dependabot_yml_leaves_it_out(self):
        # univer: dependabot.yml declares npm alone while eight workflows and a composite action use remote actions
        with tempfile.TemporaryDirectory() as d:
            r = Repo(d)
            r.write("pnpm-lock.yaml", "lockfileVersion: '9.0'\n")
            r.write(".github/workflows/ci.yml", "jobs:\n  t:\n    steps:\n      - uses: ./.github/actions/setup\n      - uses: docker://alpine:3\n")
            r.write(".github/dependabot.yml", "version: 2\nupdates:\n  - package-ecosystem: npm\n    directory: /\n")
            r.commit()
            self.assertEqual(hygiene.dependency_updates(d)["uncovered"], [], "a local action and a docker image are not github-actions'")
            r.write(".github/actions/setup/action.yml", "runs:\n  using: composite\n  steps:\n    - uses: actions/cache@" + "a" * 40 + "\n")
            r.commit()
            self.assertEqual(hygiene.dependency_updates(d), {"tool": "dependabot", "covered": ["npm"], "uncovered": ["github-actions"]},
                             "a SHA pin in a composite action needs updating too")
            r.write("go.sum", "\n")
            r.commit()
            self.assertEqual(hygiene.dependency_updates(d)["uncovered"], ["gomod", "github-actions"], "after the lock files' ecosystems")
            r.write(".github/dependabot.yml", "version: 2\nupdates:\n  - package-ecosystem: npm\n  - package-ecosystem: 'github-actions'\n  - package-ecosystem: gomod\n")
            r.commit()
            self.assertEqual(hygiene.dependency_updates(d)["uncovered"], [])
            r.write("renovate.json", "{}\n")
            r.git("rm", "-q", ".github/dependabot.yml")
            r.commit()
            self.assertEqual(hygiene.dependency_updates(d)["uncovered"], [], "renovate's github-actions manager is on by default")
            r.git("rm", "-q", "renovate.json")
            r.commit()
            self.assertEqual(hygiene.dependency_updates(d), {"tool": None, "covered": [], "uncovered": ["gomod", "npm"]},
                             "with no tool at all the lock files already say so; github-actions is not added")


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
        self.assertEqual(out, {"license": "LICENSE", "security_policy": None, "contributing": None, "codeowners": ".github/CODEOWNERS", "codeowners_missing": ["/gone/"],
                               "pull_request_template": None})


    def test_a_readme_heading_about_security_is_the_policy_the_project_points_to(self):
        with tempfile.TemporaryDirectory() as d:
            r = Repo(d)
            r.write("README.md", "# tool\n\nText about security in passing.\n\n### Security audit\n\nx\n\n### Reporting security issues\n\nSee the org's SECURITY.md.\n")
            r.commit()
            self.assertEqual(hygiene.presence(d)["security_policy"], "README.md#Reporting security issues")
        with tempfile.TemporaryDirectory() as d:
            r = Repo(d)
            r.write("README.md", "# tool\n\nWe care about security.\n")
            r.commit()
            self.assertIsNone(hygiene.presence(d)["security_policy"], "a sentence is not a section")

    def test_a_contributing_heading_about_security_counts_too(self):
        """gitmole's own repository is the case: CONTRIBUTING.md#Security names the reporting route, and the
        finding said there was no policy. A project that says how to report has one wherever it wrote it."""
        with tempfile.TemporaryDirectory() as d:
            r = Repo(d)
            r.write("README.md", "# tool\n\nNothing about that here.\n")
            r.write("CONTRIBUTING.md", "# contributing\n\n## Security\n\nTo report a vulnerability, use private reporting.\n")
            r.commit()
            self.assertEqual(hygiene.presence(d)["security_policy"], "CONTRIBUTING.md#Security")

    def test_a_readme_heading_about_contributing_is_the_guide_and_a_pull_request_template_is_only_evidence(self):
        """superpowers: README.md has "## Contributing" with the steps, .github/PULL_REQUEST_TEMPLATE.md, no CONTRIBUTING."""
        with tempfile.TemporaryDirectory() as d:
            r = Repo(d)
            r.write("README.md", "# tool\n\nWe welcome contributions.\n\n## Contributors\n\nAnn\n\n## Contributing\n\n1. Fork\n2. Open a pull request\n")
            r.write(".github/PULL_REQUEST_TEMPLATE.md", "## What\n")
            r.commit()
            out = hygiene.presence(d)
        self.assertEqual(out["contributing"], "README.md#Contributing", "not the list of contributors, and not the sentence")
        self.assertEqual(out["pull_request_template"], ".github/PULL_REQUEST_TEMPLATE.md")
        with tempfile.TemporaryDirectory() as d:
            r = Repo(d)
            r.write("README.md", "# tool\n\nWe welcome contributions.\n\n## Contributors\n\nAnn\n")
            r.write(".github/PULL_REQUEST_TEMPLATE/feature.md", "## What\n")
            r.write("docs/index.md", "# Docs\n\n### How to contribute ###\n\nSend a patch.\n")
            r.commit()
            out = hygiene.presence(d)
            self.assertEqual(out["contributing"], "docs/index.md#How to contribute", "the docs' index is read after the README")
            self.assertEqual(out["pull_request_template"], ".github/PULL_REQUEST_TEMPLATE/feature.md")
            r.git("rm", "-q", "docs/index.md")
            r.write("CONTRIBUTING.rst", "x\n")
            r.commit("guide")
            self.assertEqual(hygiene.presence(d)["contributing"], "CONTRIBUTING.rst", "the file by its name comes first")
            r.git("rm", "-q", "CONTRIBUTING.rst")
            r.commit("gone")
            self.assertIsNone(hygiene.presence(d)["contributing"], "a template alone is not a guide")

    def test_the_readme_wins_when_both_name_one(self):
        with tempfile.TemporaryDirectory() as d:
            r = Repo(d)
            r.write("README.md", "# tool\n\n## Reporting security issues\n\nHere.\n")
            r.write("CONTRIBUTING.md", "# contributing\n\n## Security\n\nAlso here.\n")
            r.commit()
            self.assertEqual(hygiene.presence(d)["security_policy"], "README.md#Reporting security issues")


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

    def test_an_extra_index_named_only_in_a_comment_is_not_one(self):
        # VoiceStudio's cosyvoice requirements.txt: "# No --extra-index-url lines"
        with tempfile.TemporaryDirectory() as d:
            r = Repo(d)
            r.write("a/requirements.txt", "# No --extra-index-url lines\ntorch==2.5  # not via --extra-index-url either\n")
            r.write("b/pip.conf", "[global]\n; extra-index-url = https://old.example/simple\n# extra-index-url = x\n")
            r.write("c/requirements.txt", "--extra-index-url https://pypi.acme.internal/simple  # the private one\nacme-auth\n")
            r.write("d/pip.ini", "[global]\nextra-index-url = https://pypi.acme.internal/simple\n")
            r.commit()
            out = hygiene.dependency_confusion(d)
        self.assertEqual(out["pip_extra_index"], ["c/requirements.txt", "d/pip.ini"])


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

    def test_the_package_manager_is_the_declared_one_else_the_lock_files(self):
        # paperclip declares "packageManager": "pnpm@9.15.4" and was told `npm ci --ignore-scripts`
        cases = [({"packageManager": "pnpm@9.15.4"}, {}, {"name": "pnpm", "from": "packageManager"}),
                 ({"packageManager": "yarn@1.22.22"}, {"yarn.lock": "# yarn lockfile v1\n"}, {"name": "yarn", "from": "packageManager"}),
                 ({"packageManager": "yarn@4.1.0"}, {}, {"name": "yarn-berry", "from": "packageManager"}),
                 ({}, {"yarn.lock": "__metadata:\n  version: 8\n"}, {"name": "yarn-berry", "from": "yarn.lock"}),
                 ({}, {"pnpm-lock.yaml": "lockfileVersion: '9.0'\n"}, {"name": "pnpm", "from": "pnpm-lock.yaml"}),
                 ({"packageManager": "made-up"}, {"package-lock.json": "{}"}, {"name": "npm", "from": "package-lock.json"}),
                 ({}, {}, None)]
        for manifest, files, expected in cases:
            with tempfile.TemporaryDirectory() as d:
                r = Repo(d)
                r.write("package.json", json.dumps({"name": "x", "scripts": {"postinstall": "node s.js"}, **manifest}))
                for path, text in files.items():
                    r.write(path, text)
                r.commit()
                self.assertEqual(hygiene.install_scripts(d).get("manager"), expected, (manifest, files))

    def test_a_setup_py_without_setup_is_a_script_pip_never_runs(self):
        # VoiceStudio's scripts/setup.py is `uv run python scripts/setup.py`: no setuptools, no setup()
        with tempfile.TemporaryDirectory() as d:
            r = Repo(d)
            r.write("scripts/setup.py", "import subprocess\nsubprocess.run(['uv', 'sync'])\n")
            r.write("pkg/setup.py", "import os, setuptools\nos.system('make')\nsetuptools.setup(name='x')\n")
            r.write("old/setup.py", "from distutils.core import setup\nimport subprocess\nsubprocess.call(['make'])\nsetup(name='y')\n")
            r.commit()
            out = hygiene.install_scripts(d)
        self.assertEqual(out["setup_py"], [{"file": "old/setup.py", "calls": ["subprocess.call"]}, {"file": "pkg/setup.py", "calls": ["os.system"]}])


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

    def test_an_elf_relocatable_object_is_not_an_executable(self):
        # Ghidra's GnuDisassembler/data/big.elf and little.elf: a linker's input, kept as a disassembler's test data
        def elf(big_endian: bool, e_type: int) -> bytes:
            return b"\x7fELF\x01" + (b"\x02" if big_endian else b"\x01") + b"\x01" + b"\x00" * 9 + e_type.to_bytes(2, "big" if big_endian else "little") + b"\x00" * 30
        with tempfile.TemporaryDirectory() as d:
            r = Repo(d)
            r.write("data/big.elf", elf(True, 1), binary=True)
            r.write("data/little.elf", elf(False, 1), binary=True)
            r.write("bin/tool", elf(False, 2), binary=True)
            r.write("lib/libx.so", elf(True, 3), binary=True)
            r.commit()
            out = hygiene.binaries(d)
        self.assertEqual(out["executables"], [{"file": "bin/tool", "format": "ELF"}, {"file": "lib/libx.so", "format": "ELF"}])
        self.assertEqual(out["executables_count"], 2)


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
            r.write("src/d.go", "// small overhead (<500\u03bcs per request)\n")   # a Greek μ before a unit reads as itself
            r.commit()
            out = hygiene.trojan_source(d)
        self.assertEqual(out["bidi"], [{"file": "src/a.py", "line": 2, "char": "U+202E"}, {"file": "src/a.py", "line": 3, "char": "U+2066"}])
        self.assertEqual(out["mixed_script"], [{"file": "src/b.py", "line": 2, "token": "pr\u043ecess", "scripts": ["CYRILLIC", "LATIN"]}])
        self.assertEqual(out["files"], 4, "source files scanned; the doc and the test fixture are not")


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


class TrojanRetuned(unittest.TestCase):
    def test_direction_marks_are_text_and_generated_files_are_skipped(self):
        with tempfile.TemporaryDirectory() as d:
            r = Repo(d)
            r.write("locale/ar/formats.py", 'DATE_FORMAT = "j F‏، Y"\n')
            r.write("api/version.pb.go", 'var x = "x18Іabc"\n')
            r.write("src/check.py", 'access = "user‮ admin"\n')
            r.commit()
            out = hygiene.trojan_source(d, {"api/version.pb.go"})
        self.assertEqual([x["file"] for x in out["bidi"]], ["src/check.py"], "U+200F in a locale string is a direction mark, not an override")
        self.assertEqual(out["mixed_script"], [], "a generated file's bytes are not a reviewer's trap")

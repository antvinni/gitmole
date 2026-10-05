"""What npm-family lock files declare, read without a YAML library (locks.py): the workspaces' direct
dependencies, what an install without dev dependencies reaches, and the peers the lock resolved."""
import json
import unittest

from gitmole import locks

PNPM = """lockfileVersion: '9.0'

settings:
  autoInstallPeers: false

importers:

  .:
    devDependencies:
      supertest:
        specifier: ^7.0.0
        version: 7.1.0

  server:
    dependencies:
      '@photon-ai/imessage':
        specifier: 2.1.0
        version: 2.1.0(nice-grpc-common@2.0.4)(nice-grpc@2.1.17)
      nice-grpc:
        specifier: ^2.1.17
        version: 2.1.17
      nice-grpc-common:
        specifier: ^2.0.4
        version: 2.0.4
      multer:
        specifier: ^2.2.0
        version: 2.2.0
      shared:
        specifier: workspace:*
        version: link:../packages/shared
      esbuild:
        specifier: ^0.28.2
        version: 0.28.2

  packages/shared:
    dependencies:
      qs:
        specifier: ^6.15.0
        version: 6.15.0

packages:

  '@photon-ai/imessage@2.1.0':
    resolution: {integrity: sha512-x}
    peerDependencies:
      nice-grpc: ^2.1.11
      nice-grpc-common: ^2.0.2

  multer@2.2.0:
    resolution: {integrity: sha512-x}

snapshots:

  '@photon-ai/imessage@2.1.0(nice-grpc-common@2.0.4)(nice-grpc@2.1.17)':
    optionalDependencies:
      nice-grpc: 2.1.17
      nice-grpc-common: 2.0.4

  multer@2.2.0:
    dependencies:
      busboy: 1.6.0

  busboy@1.6.0: {}

  nice-grpc@2.1.17: {}

  nice-grpc-common@2.0.4: {}

  qs@6.15.0: {}

  esbuild@0.28.2: {}

  supertest@7.1.0:
    dependencies:
      form-data: 4.0.5
      esbuild: 0.18.20

  form-data@4.0.5: {}

  esbuild@0.18.20: {}
"""

# univer's shape: a published member reaches protobufjs through @grpc/grpc-js; a private toolbox reaches immutable
WORKSPACE = """lockfileVersion: '9.0'

importers:

  .:
    dependencies:
      root-dep:
        specifier: ^1
        version: 1.0.0

  packages/protocol:
    dependencies:
      '@grpc/grpc-js':
        specifier: ^1.14.4
        version: 1.14.4
      linked:
        specifier: workspace:*
        version: link:../../common/linked

  common/shared:
    dependencies:
      sass:
        specifier: ^1
        version: 1.0.0

  common/linked:
    dependencies:
      left-pad:
        specifier: ^1
        version: 1.3.0

snapshots:

  root-dep@1.0.0: {}

  '@grpc/grpc-js@1.14.4':
    dependencies:
      '@grpc/proto-loader': 0.8.0

  '@grpc/proto-loader@0.8.0':
    dependencies:
      protobufjs: 7.5.5

  protobufjs@7.5.5: {}

  sass@1.0.0:
    dependencies:
      immutable: 5.1.2

  immutable@5.1.2: {}

  left-pad@1.3.0: {}
"""


class Pnpm(unittest.TestCase):
    def setUp(self):
        self.lock = locks.pnpm(PNPM)

    def test_keys_split_into_name_and_version(self):
        self.assertEqual(locks.split_key("'@scope/a@1.0.0(b@2.0.0(c@3))'".strip("'")), ("@scope/a", "1.0.0"))
        self.assertEqual(locks.split_key("/left-pad@1.3.0"), ("left-pad", "1.3.0"))
        self.assertEqual(locks.suffix_peers("1.0.0(@x/a@1(b@2))(c@3)"), {"@x/a", "b", "c"})

    def test_importers_and_their_sections(self):
        self.assertEqual(sorted(self.lock["importers"]), [".", "packages/shared", "server"])
        self.assertEqual(self.lock["importers"]["server"]["dependencies"]["multer"], "2.2.0")
        self.assertEqual(self.lock["peers"]["@photon-ai/imessage"], ["nice-grpc", "nice-grpc-common"])

    def test_runtime_is_what_dependencies_reach_through_links_and_snapshots(self):
        runtime = locks.pnpm_runtime(self.lock)
        self.assertIn(("busboy", "1.6.0"), runtime, "a dependency of a runtime dependency")
        self.assertIn(("qs", "6.15.0"), runtime, "through the workspace link")
        self.assertIn(("nice-grpc", "2.1.17"), runtime)
        self.assertNotIn(("form-data", "4.0.5"), runtime, "reached only through a devDependency")
        self.assertNotIn(("esbuild", "0.18.20"), runtime)
        self.assertIn(("esbuild", "0.28.2"), runtime)

    def test_each_runtime_package_names_the_direct_dependency_it_is_reached_through(self):
        runtime = locks.pnpm_runtime(self.lock)
        self.assertEqual(runtime[("busboy", "1.6.0")], "multer")
        self.assertEqual(runtime[("nice-grpc", "2.1.17")], "nice-grpc", "a direct dependency is its own first hop, though @photon-ai/imessage reaches it too")
        self.assertEqual(runtime[("qs", "6.15.0")], "qs", "a linked member's dependency is a first hop")

    def test_a_held_member_is_not_walked_from_but_a_link_into_it_and_the_root_are(self):
        lock = locks.pnpm(WORKSPACE)
        everything = locks.pnpm_runtime(lock)
        self.assertIn(("immutable", "5.1.2"), everything, "with nothing held, every importer is walked")
        held = locks.pnpm_runtime(lock, {"common/shared", "common/linked", "."})
        self.assertNotIn(("immutable", "5.1.2"), held, "only a held member's dependencies reach it")
        self.assertNotIn(("sass", "1.0.0"), held)
        self.assertEqual(held[("protobufjs", "7.5.5")], "@grpc/grpc-js")
        self.assertEqual(held[("left-pad", "1.3.0")], "left-pad", "a held member a published one links to ships with it")
        self.assertEqual(held[("root-dep", "1.0.0")], "root-dep", "the root importer is walked whatever it declares")

    def test_direct_versions_and_importer_peers(self):
        self.assertEqual(locks.pnpm_direct(self.lock)["esbuild"], {"0.28.2"})
        self.assertEqual(locks.pnpm_importer_peers(self.lock, "server"), {"nice-grpc", "nice-grpc-common"})
        self.assertEqual(locks.pnpm_importer_peers(self.lock, "."), set())


class Npm(unittest.TestCase):
    LOCK = json.dumps({"lockfileVersion": 3, "packages": {
        "": {"dependencies": {"a": "1"}, "devDependencies": {"t": "1"}},
        "node_modules/a": {"version": "1.0.0", "peerDependencies": {"p": "^1"}},
        "node_modules/p": {"version": "1.2.0"},
        "node_modules/t": {"version": "2.0.0", "dev": True},
        "node_modules/o": {"version": "3.0.0", "devOptional": True},
        "node_modules/a/node_modules/q": {"version": "0.1.0", "peerDependencies": {"z": "1"}},
        "web/node_modules/q": {"version": "0.2.0"}}})

    def test_dev_marks_direct_paths_and_peers(self):
        packages = locks.npm(self.LOCK)
        self.assertEqual(locks.npm_runtime(packages), {("a", "1.0.0"), ("p", "1.2.0"), ("q", "0.1.0"), ("q", "0.2.0")})
        self.assertEqual(locks.npm_direct(packages)["q"], {"0.2.0"}, "a copy nested under another package is not what the code resolves")
        self.assertEqual(locks.npm_peers(packages, {"a", "q"}), {"p"})
        self.assertIsNone(locks.npm('{"lockfileVersion": 1, "dependencies": {}}'))


class Yarn(unittest.TestCase):
    def test_berry_records_peers_and_classic_does_not(self):
        berry = ('__metadata:\n  version: 8\n\n"@lexical/react@npm:0.48.0":\n  version: 0.48.0\n  peerDependencies:\n    react: ">=17"\n    yjs: ">=13.5.22"\n'
                 '  checksum: abc\n\n"left-pad@npm:1.3.0":\n  version: 1.3.0\n')
        self.assertEqual(locks.yarn_peers(berry, {"@lexical/react"}), {"react", "yjs"})
        self.assertEqual(locks.yarn_peers(berry, {"left-pad"}), set())
        self.assertEqual(locks.yarn_peers('# yarn lockfile v1\n\nleft-pad@^1.3.0:\n  version "1.3.0"\n', {"left-pad"}), set())


if __name__ == "__main__":
    unittest.main()

import os
import re
import unittest

from gitmole import run, tools

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FORMULA = os.path.join(ROOT, "Formula", "gitmole.rb")


def formula() -> str:
    with open(FORMULA, encoding="utf-8") as fh:
        return fh.read()


class Pinned(unittest.TestCase):
    def test_every_tool_the_run_needs_is_pinned(self):
        self.assertEqual(sorted(tools.PINNED), sorted(run.REQUIRED_TOOLS + ["lizard"]))

    def test_the_formula_installs_the_pinned_versions(self):
        # the formula names each version in its resource urls; a bump in one place and not the other is the bug this catches
        text = formula()
        for name, version in tools.PINNED.items():
            with self.subTest(tool=name):
                self.assertRegex(text, rf'resource "{re.escape(name)}" do\n(?:.*\n)*?\s*url "[^"]*{re.escape(version)}[^"]*"', f"{name} {version}")

    def test_the_wrapper_puts_the_pinned_tools_first_on_the_path(self):
        self.assertIn('libexec/"tools"', formula())

    def test_the_formula_carries_every_pinned_grammar_wheel_for_every_platform(self):
        """Six of the eleven grammars publish no buildable source archive, so the formula installs prebuilt
        wheels: one per grammar per platform, at the version pyproject.toml pins."""
        import re
        with open(os.path.join(ROOT, "pyproject.toml"), encoding="utf-8") as fh:
            pins = dict(re.findall(r'"(tree-sitter[\w-]*)==([\d.]+); python_version', fh.read()))
        self.assertEqual(len(pins), 12, "py-tree-sitter and eleven grammars")
        text = formula()
        for name, version in sorted(pins.items()):
            wheel_name = name.replace("-", "_")
            with self.subTest(package=name):
                if name == "tree-sitter":   # py-tree-sitter builds from its source archive
                    self.assertIn(f"tree_sitter-{version}.tar.gz", text)
                    continue
                found = len(re.findall(rf"{wheel_name}-{re.escape(version)}-\S*\.whl", text))
                self.assertEqual(found, 4, f"{name} {version}: one wheel for each system and CPU")
        self.assertEqual(text.count("using: :nounzip"), 44, "a wheel is not unpacked before pip sees it")
        self.assertIn('system libexec/"bin/python", "-m", "pip", "install"', text,
                      "the venv is created without pip's script, so pip runs as a module")

    def test_differences_names_only_the_tools_that_moved(self):
        found = {"scc": "4.2.0", "betterleaks": None, "osv-scanner": "2.6.0", "lizard": "1.24.0"}
        self.assertEqual(tools.differences(found), [("scc", "4.1.0", "4.2.0")], "a missing tool is not a difference")
        self.assertEqual(tools.differences({}), [])
        self.assertEqual(tools.differences({k: v for k, v in tools.PINNED.items()}), [])

    def test_the_note_names_both_versions(self):
        self.assertIsNone(tools.note(dict(tools.PINNED)))
        note = tools.note({**tools.PINNED, "scc": "4.2.0"})
        self.assertEqual(note, "tool versions differ from the pinned set: scc 4.2.0, pinned 4.1.0")

    @staticmethod
    def _formula_by_platform() -> dict:
        """{(system, cpu): {tool: (url, sha256)}} for every tool resource (the grammar wheels left out), read per
        on_macos/on_linux and on_arm/on_intel block, so an archive listed under the wrong platform is a difference too."""
        text = formula()
        out = {}
        for system in ("macos", "linux"):
            block = re.search(rf"\n  on_{system} do\n(.*?)\n  end\n", text, re.S).group(1)
            for cpu_block, cpu in (("arm", "arm64"), ("intel", "x86_64")):
                inner = re.search(rf"\n    on_{cpu_block} do\n(.*?)\n    end\n", "\n" + block + "\n", re.S).group(1)
                found = re.findall(r'resource "([\w-]+)" do\s*url "([^"]+)"\s*sha256 "([0-9a-f]{64})"', inner)
                out[("darwin" if system == "macos" else "linux", cpu)] = {name: (url, sha) for name, url, sha in found
                                                                          if not name.startswith("tree-sitter")}
        return out

    def test_the_installer_downloads_the_archives_the_formula_installs(self):
        """One table of urls and hashes in two places is the bug this catches: on every platform, every archive
        the installer names must be the one the formula names for that tool there, with the same hash. A tool the
        installer has no url for would be one the formula compiles (as it did git-sizer's source on Linux arm64). The formula may
        also name a tool gitmole no longer runs: it installs the last released tarball, so a dropped tool stays
        in it through the version bump and the release (docs/development.md) and leaves it in a commit of its
        own; the check is then that every pinned tool is in the formula, not that the two lists are equal. The
        musl entries are the installer's own: Homebrew on Linux is glibc."""
        in_formula = self._formula_by_platform()
        self.assertEqual(sorted(in_formula), sorted(k for k in tools.ARCHIVES if k[0] != "linux-musl"))
        for key, entries in in_formula.items():
            with self.subTest(platform=key):
                for name, entry in tools.ARCHIVES[key].items():
                    self.assertIn(name, entries, f"{name} is pinned but the formula does not install it")
                    if "url" in entry:
                        self.assertEqual(entries[name], (entry["url"], entry["sha256"]), name)
                self.assertEqual(set(entries) - set(tools.ARCHIVES[key]), set(entries) - set(tools.PINNED),
                                 "the formula's extras are tools no longer pinned")

    def test_musl_takes_the_linux_builds(self):
        """The pinned tools are static builds that run on either C library."""
        for cpu in ("arm64", "x86_64"):
            with self.subTest(cpu=cpu):
                self.assertEqual(tools.ARCHIVES[("linux-musl", cpu)], tools.ARCHIVES[("linux", cpu)])

    def test_every_platform_names_every_tool_and_every_url_carries_its_pin(self):
        self.assertEqual(sorted(tools.ARCHIVES), [("darwin", "arm64"), ("darwin", "x86_64"), ("linux", "arm64"), ("linux", "x86_64"),
                                                  ("linux-musl", "arm64"), ("linux-musl", "x86_64")])
        for key, per_tool in tools.ARCHIVES.items():
            with self.subTest(platform=key):
                self.assertEqual(sorted(per_tool), sorted(run.REQUIRED_TOOLS))
                for name, entry in per_tool.items():
                    self.assertIn("url", entry, f"{name} on {key}: upstream publishes a build for every platform since git-sizer left")
                    self.assertIn(tools.PINNED[name], entry["url"], f"{name} on {key}")
                    self.assertRegex(entry["sha256"], r"^[0-9a-f]{64}$")

    def test_every_pinned_tool_has_a_release_page(self):
        self.assertEqual(sorted(tools.RELEASES), sorted(tools.PINNED))
        for name, url in tools.RELEASES.items():
            self.assertTrue(url.startswith("https://"), name)


class Manifest(unittest.TestCase):
    def test_the_manifest_records_the_pinned_versions_beside_what_it_found(self):
        class Args:
            ignore, ignore_data, deep, plots = [], False, False, False
        found = {**tools.PINNED, "git": "2.51.0", "scc": "4.2.0"}
        m = run.manifest(ROOT, Args(), version_of=lambda name, path=None: found.get(name), lizard_of=lambda: found["lizard"])
        self.assertEqual(m["tools_pinned"], tools.PINNED)
        self.assertEqual(m["tools_moved"], [{"tool": "scc", "pinned": "4.1.0", "found": "4.2.0"}])
        self.assertEqual(m["tools"]["scc"], "4.2.0")


if __name__ == "__main__":
    unittest.main()

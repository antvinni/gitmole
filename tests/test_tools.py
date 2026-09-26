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
        found = {"scc": "4.1.0", "git-sizer": "1.6.0", "betterleaks": None, "jscpd": "5.3.0",
                 "osv-scanner": "2.6.0", "lizard": "1.24.0"}
        self.assertEqual(tools.differences(found), [("git-sizer", "1.5.0", "1.6.0")], "a missing tool is not a difference")
        self.assertEqual(tools.differences({}), [])
        self.assertEqual(tools.differences({k: v for k, v in tools.PINNED.items()}), [])

    def test_the_note_names_both_versions(self):
        self.assertIsNone(tools.note(dict(tools.PINNED)))
        note = tools.note({**tools.PINNED, "scc": "4.2.0"})
        self.assertEqual(note, "tool versions differ from the pinned set: scc 4.2.0, pinned 4.1.0")

    @staticmethod
    def _formula_by_platform() -> dict:
        """{(system, cpu): {(url, sha256)}} for the five tools, read per on_macos/on_linux and on_arm/on_intel
        block, so an archive listed under the wrong platform is a difference too."""
        text = formula()
        out = {}
        for system in ("macos", "linux"):
            block = re.search(rf"\n  on_{system} do\n(.*?)\n  end\n", text, re.S).group(1)
            for cpu_block, cpu in (("arm", "arm64"), ("intel", "x86_64")):
                inner = re.search(rf"\n    on_{cpu_block} do\n(.*?)\n    end\n", "\n" + block + "\n", re.S).group(1)
                out[("darwin" if system == "macos" else "linux", cpu)] = set(re.findall(
                    r'resource "(?:scc|git-sizer|betterleaks|osv-scanner|jscpd)" do\s*url "([^"]+)"\s*sha256 "([0-9a-f]{64})"', inner))
        return out

    def test_the_installer_downloads_the_archives_the_formula_installs(self):
        """One table of urls and hashes in two places is the bug this catches: on every platform, every archive
        the installer names must be one the formula names there, with the same hash, and the formula's only
        extra is the git-sizer source it compiles on Linux arm64, which the installer cannot use. The musl
        entries are the installer's own: Homebrew on Linux is glibc."""
        in_formula = self._formula_by_platform()
        self.assertEqual(sorted(in_formula), sorted(k for k in tools.ARCHIVES if k[0] != "linux-musl"))
        self.assertEqual(sum(len(v) for v in in_formula.values()), 20, "five tools, four platforms")
        for key, entries in in_formula.items():
            with self.subTest(platform=key):
                in_table = {(e["url"], e["sha256"]) for e in tools.ARCHIVES[key].values() if "url" in e}
                self.assertEqual(in_table - entries, set())
                extra = sorted(url for url, _ in entries - in_table)
                self.assertEqual(extra, ["https://github.com/github/git-sizer/archive/refs/tags/v1.5.0.tar.gz"] if key == ("linux", "arm64") else [])

    def test_musl_differs_from_glibc_linux_in_jscpd_alone(self):
        for cpu in ("arm64", "x86_64"):
            with self.subTest(cpu=cpu):
                musl, glibc = tools.ARCHIVES[("linux-musl", cpu)], tools.ARCHIVES[("linux", cpu)]
                self.assertEqual({n for n in musl if musl[n] != glibc[n]}, {"jscpd"})
                self.assertIn("-musl-", musl["jscpd"]["url"])

    def test_every_platform_names_every_tool_and_every_url_carries_its_pin(self):
        self.assertEqual(sorted(tools.ARCHIVES), [("darwin", "arm64"), ("darwin", "x86_64"), ("linux", "arm64"), ("linux", "x86_64"),
                                                  ("linux-musl", "arm64"), ("linux-musl", "x86_64")])
        for key, per_tool in tools.ARCHIVES.items():
            with self.subTest(platform=key):
                self.assertEqual(sorted(per_tool), sorted(run.REQUIRED_TOOLS))
                for name, entry in per_tool.items():
                    if "url" in entry:
                        self.assertIn(tools.PINNED[name], entry["url"], f"{name} on {key}")
                        self.assertRegex(entry["sha256"], r"^[0-9a-f]{64}$")
                    else:
                        self.assertIn("note", entry, f"{name} on {key}: a tool without a url says why")
                        self.assertIn(f"ReleaseVersion={tools.PINNED[name]}", entry["note"], "the build command carries the pin")
        without = [(key, name) for key, per_tool in tools.ARCHIVES.items() for name, e in per_tool.items() if "url" not in e]
        self.assertEqual(without, [(("linux", "arm64"), "git-sizer"), (("linux-musl", "arm64"), "git-sizer")],
                         "the one build upstream does not publish")

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

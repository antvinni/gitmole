"""Every key of the --json export and every file of the output directory has a stated home (docs/output.md,
"Where each key and file is shown"): a section and its tier, "export only" or "retired". prometheus's export held
companions, per-file test co-change, the late-night share, the change entropy and the directory-level coupling,
and its directory packages.json, reverts.txt and tree.txt, and nothing said that no report printed them."""
import io
import json
import os
import re
import tempfile
import unittest
from unittest.mock import patch

from rich.console import Console

from gitmole import cli, render, run, section
from tests.test_golden import HERMETIC_ENV, build_repo
from tests.test_render import sample_report

DOC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "docs", "output.md")
HEADING = "## Where each key and file is shown"
# What an export or a directory holds only on some runs, so the synthetic repository's does not: each has a row too.
SOME_KEYS = {"plumbing": "the change log shows a file to be release plumbing", "change_risk": "--risk", "compare": "--compare"}
SOME_FILES = {"maat-plumbing.csv": "as the key", "code-age.png": "--plots", "survival.png": "--plots", "gitmole-feedback.json": "--feedback",
              "unreachable.json": "the secrets step's sweep, which a step that did not finish leaves out", "trend.json": "the trend step",
              "functions.csv": "lizard", "structure.json": "the grammars, on Python 3.10 or newer", "backtest/": "the backtest step",
              "theseus/": "the blame pass", "dependencies.json": "osv-scanner", "packages.json": "osv-scanner", "secrets.json": "a secrets scan that finished"}
# The blocks of the report that are not a section with a table: named in a home as they are in the docs.
BLOCKS = ("Findings", "Supply chain", "Change risk", "Since last report", "the header", "the closing lines")
TIERS = ("(default)", "(`--full`)")


def homes() -> dict:
    """The table's rows, {key or file: home}, read from the page."""
    with open(DOC, encoding="utf-8") as fh:
        text = fh.read()
    body = text[text.index(HEADING):]
    rows = re.findall(r"^\| `([^`]+)` \| (.+) \|$", body, re.M)
    return dict(rows)


def run_once(work: str) -> tuple:
    """(the export's top-level keys, the output directory's entries) of one run over the synthetic repository."""
    repo, out, target = os.path.join(work, "demo"), os.path.join(work, "out"), os.path.join(work, "report.json")
    os.makedirs(repo)
    build_repo(repo)
    c = Console(file=io.StringIO(), width=100, force_terminal=False, color_system=None)
    with patch.dict(os.environ, HERMETIC_ENV):
        rc = cli.main([repo, "--out", out, "--json", target], console=c, version_note=lambda found: None)
    assert rc == 0, rc
    with open(target, encoding="utf-8") as fh:
        keys = sorted(json.load(fh))
    return keys, sorted(name + ("/" if os.path.isdir(os.path.join(out, name)) else "") for name in os.listdir(out))


class Table(unittest.TestCase):
    def test_the_page_has_one_table_with_a_row_a_name(self):
        with open(DOC, encoding="utf-8") as fh:
            text = fh.read()
        self.assertEqual(text.count(HEADING), 1)
        names = re.findall(r"^\| `([^`]+)` \| ", text[text.index(HEADING):], re.M)
        self.assertEqual(len(names), len(set(names)), "a key or a file has one row")
        self.assertEqual(names, sorted(n for n in names if "." not in n and "/" not in n) + sorted(n for n in names if "." in n or "/" in n), "keys, then files, each in order")

    def test_every_home_is_a_section_with_its_tier_a_key_export_only_or_retired(self):
        table = homes()
        titles = {name.replace("-", " ") for name in section.NAMES} | {b.lower() for b in BLOCKS}
        for name, home in table.items():
            for part in home.split(" · "):
                if part.startswith(("export only", "retired")):
                    continue
                key = re.fullmatch(r"the `([\w]+)` key(?:: .+)?", part)
                if key:
                    self.assertIn(key.group(1), table, f"{name}: its home is a key with no row")
                    self.assertFalse("." in key.group(1) or "/" in key.group(1))
                    continue
                only = re.match(r"`--section ([\w-]+)` only\b", part)
                if only:
                    self.assertIn(only.group(1), section.NAMES, f"{name}: {part}")
                    continue
                title = next((t for t in sorted(titles, key=len, reverse=True) if part.lower().startswith(t)), None)
                self.assertIsNotNone(title, f"{name}: '{part}' names no section of the report, nor 'export only' or 'retired'")
                self.assertTrue(any(tier in part for tier in TIERS), f"{name}: '{part}' does not say which tier prints it")

    def test_every_key_the_export_can_hold_has_a_row(self):
        table = homes()
        r = sample_report()
        r["plumbing"] = [{"entity": "pkg/__init__.py", "n-revs": 25, "tiny-revs": 24}]
        exported = json.loads(render.dumps_json(r, [], risk={"base": "main"}, compare={"findings": {}}))
        for key in sorted(set(exported) | set(SOME_KEYS)):
            self.assertIn(key, table, f"the --json export's `{key}` has no home in docs/output.md ({HEADING[3:]})")
        for key in SOME_KEYS:
            self.assertIn(key, exported, f"{key} is listed as a key of some exports and this one, made to hold it, does not")

    def test_every_file_a_run_can_write_has_a_row(self):
        table = homes()
        written = {n for n in run.OUTPUTS if "/" not in n} | {n.split("/")[0] + "/" for n in run.OUTPUTS if "/" in n} | {"meta.json", "run.log", "backtest/"}
        retired = {"duplicates.json", "duplicates.txt", "repo-health.txt"}   # run.OUTPUTS clears what steps wrote before 0.39.0; no run writes them
        for name in sorted(written - retired | set(SOME_FILES)):
            self.assertIn(name, table, f"the output directory's {name} has no home in docs/output.md ({HEADING[3:]})")

    def test_the_passed_checks_and_the_resolution_rate_are_rendered_where_the_table_says(self):
        from tests.test_full import full, rich_report
        table = homes()
        self.assertIn("Checks run (`--full`)", table["hygiene"])
        self.assertIn("Supply chain (default)", table["hygiene"])
        self.assertIn("Checks run (`--full`): `resolved`", table["structure"])
        checks = [name for name, _, _ in render.CHECKS]
        for name in ("workflow actions pinned to a commit", "lock files against their manifests", "bidi and mixed-script characters", "committed binaries",
                     "dependency update tool", "declared files", "licence"):   # actions, lockfiles, trojan, binaries, updates, presence, licences
            self.assertIn(name, checks, "one row each in Checks run")
        r = rich_report()
        r["structure"] = dict(r.get("structure") or {}, status="run", resolved={"python": 1.0, "tsx": 0.916})
        text = " ".join(full(report=r).split())
        self.assertIn("imports resolved to a tracked file", text)
        self.assertIn("python 100%, tsx 92%", text, "the rate per language, one row")


@unittest.skipUnless(run.missing_tools() == [] and run.has_lizard(), "external tools or lizard not installed")
class RealRun(unittest.TestCase):
    """The lists come from a real export and a real output directory, so a key or a file a change adds fails here
    until the table gives it a home."""

    @classmethod
    def setUpClass(cls):
        with tempfile.TemporaryDirectory() as work:
            cls.keys, cls.files = run_once(work)

    def test_every_key_of_a_real_export_has_a_row(self):
        table = homes()
        self.assertGreater(len(self.keys), 30)
        for key in self.keys:
            self.assertIn(key, table, f"the --json export's `{key}` has no home in docs/output.md ({HEADING[3:]})")

    def test_every_file_of_a_real_output_directory_has_a_row(self):
        table = homes()
        self.assertIn("findings.json", self.files)
        self.assertIn("meta.json", self.files)
        for name in self.files:
            self.assertIn(name, table, f"the output directory's {name} has no home in docs/output.md ({HEADING[3:]})")

    def test_no_row_is_for_a_key_or_a_file_that_does_not_exist(self):
        known = set(self.keys) | set(self.files) | set(SOME_KEYS) | set(SOME_FILES)
        for name in homes():
            self.assertIn(name, known, f"docs/output.md gives a home to {name}, which no export and no output directory holds: list it in SOME_KEYS or SOME_FILES with what writes it, or drop the row")


if __name__ == "__main__":
    unittest.main()

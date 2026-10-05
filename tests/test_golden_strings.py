"""End-to-end: the strings the report shares with a pipeline and with a coding agent, compared to a stored copy.

tests/golden/report.txt holds the terminal report. Three other surfaces are built from the same words and no
stored output held them: what `--hook` hands an agent as additionalContext, the Change risk section `--risk`
adds, and the stderr lines a tripped gate (`--fail-on`, `--risk-threshold`) leaves in a CI log. A change to the
report's wording moves them too, and this file is where that shows.

Regenerate the stored copy with:  UPDATE_GOLDEN=1 python3 -m unittest tests.test_golden_strings
"""
import io
import json
import os
import tempfile
import unittest
from unittest.mock import patch

from rich.console import Console

from gitmole import cli, gate, run
from tests.test_golden import HERMETIC_ENV, build_repo, normalise, update_requested

GOLDEN = os.path.join(os.path.dirname(__file__), "golden", "strings.txt")
BASE = "HEAD~2"   # the last two commits: one adds app/old.py and edits both modules, one removes it and edits main


def _console():
    # wide enough that no line of the three surfaces wraps: a wrap would be the console's, not the string's
    return Console(file=io.StringIO(), width=100, record=True, force_terminal=False, color_system=None)


def _risk_section(text: str) -> list:
    """The Change risk section of a report: from its heading to the blank line that ends it."""
    lines = text.splitlines()
    start = next(i for i, line in enumerate(lines) if "Change risk (" in line)
    end = next((i for i in range(start, len(lines)) if not lines[i].strip()), len(lines))
    return lines[start:end]


@unittest.skipUnless(run.missing_tools() == [] and run.has_lizard(), "external tools or lizard not installed")
class GoldenStrings(unittest.TestCase):
    def test_hook_risk_and_gate_strings_match_stored_output(self):
        with tempfile.TemporaryDirectory() as work:
            repo = os.path.join(work, "demo")
            os.makedirs(repo)
            build_repo(repo)
            out = os.path.join(work, "out")
            c = _console()
            with patch.dict(os.environ, HERMETIC_ENV):
                rc = cli.main([repo, "--out", out, "--risk", BASE, "--risk-threshold", "1", "--fail-on", "info"],
                              console=c, version_note=lambda found: None)
                self.assertEqual(rc, gate.EXIT_FOUND)
                report = normalise(c.export_text(), out).replace(os.path.realpath(repo), "<repo>").replace(repo, "<repo>")
                h = _console()
                event = {"hook_event_name": "PostToolUse", "tool_input": {"file_path": os.path.join(repo, "app", "main.py")}}
                self.assertEqual(cli.main([out, "--no-run", "--hook", "--risk-threshold", "1"], console=h, stdin=io.StringIO(json.dumps(event))), 0)
            # a test console is stdout and stderr at once, so the GITMOLE_NOW notice precedes the hook's JSON
            said = next(line for line in h.export_text().splitlines() if line.startswith("{"))
            context = json.loads(said)["hookSpecificOutput"]["additionalContext"]
        gates = [line for line in report.splitlines() if line.startswith(("--fail-on", "--risk-threshold"))]
        actual = "\n".join(["[--hook additionalContext]", context, "", f"[--risk {BASE} section]", *_risk_section(report), "",
                            "[gate lines on stderr]", *gates]) + "\n"
        if update_requested():
            with open(GOLDEN, "w") as fh:
                fh.write(actual)
        self.assertTrue(os.path.exists(GOLDEN), f"{GOLDEN} is missing; run with UPDATE_GOLDEN=1 to create it, then review it")
        with open(GOLDEN) as fh:
            expected = fh.read()
        if actual != expected:
            import difflib
            diff = "\n".join(difflib.unified_diff(expected.splitlines(), actual.splitlines(), "golden", "actual", lineterm=""))
            self.fail("the shared strings differ from tests/golden/strings.txt (UPDATE_GOLDEN=1 to accept):\n" + diff)


if __name__ == "__main__":
    unittest.main()

"""End-to-end: a deterministic synthetic repo through the real pipeline, compared to a stored report.

Regenerate the stored report with:  UPDATE_GOLDEN=1 python3 -m unittest tests.test_golden
"""
import io
import os
import re
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from rich.console import Console

from gitmole import cli, run

GOLDEN = os.path.join(os.path.dirname(__file__), "golden", "report.txt")
NOW = "2025-06-15"

AUTHORS = {
    "ann": ("Ann Example", "ann@demo.test"),
    "bob": ("Bob Example", "bob@demo.test"),
    "bob2": ("bob-example", "9999+bob-example@users.noreply.demo.test"),
}

# (author, iso timestamp, {path: content or None to delete})
COMMITS = [
    ("ann", "2024-01-10T09:00:00+00:00", {"app/main.py": "def main():\n    return 1\n", "README.md": "# demo\n", "data/rows.csv": "a,b\n1,2\n"}),
    ("ann", "2024-02-14T10:30:00+00:00", {"app/main.py": "def main():\n    return 2\n\ndef helper(x):\n    if x:\n        return x\n    return 0\n", "app/util.py": "VALUE = 1\n"}),
    ("bob", "2024-03-03T14:00:00+00:00", {"app/util.py": "VALUE = 2\nOTHER = 3\n", "app/main.py": "def main():\n    return 3\n\ndef helper(x):\n    if x:\n        return x\n    return 0\n"}),
    ("ann", "2024-06-20T11:00:00+00:00", {"app/main.py": "def main():\n    return 4\n\ndef helper(x):\n    if x:\n        return x\n    return 0\n", "app/util.py": "VALUE = 4\nOTHER = 3\n"}),
    ("bob2", "2024-09-01T08:00:00+00:00", {"Makefile": "test:\n\tpython3 -m unittest\n"}),
    ("ann", "2024-12-12T22:15:00+00:00", {"app/main.py": "def main():\n    return 5\n\ndef helper(x):\n    if x:\n        return x\n    return 0\n", "app/util.py": "VALUE = 5\nOTHER = 3\n"}),
    ("ann", "2025-03-05T09:45:00+00:00", {"app/main.py": "def main():\n    return 6\n\ndef helper(x):\n    if x:\n        return x\n    return 0\n", "app/util.py": "VALUE = 6\nOTHER = 3\n", "app/old.py": "x = 1\n"}),
    ("bob", "2025-05-30T16:20:00+00:00", {"app/old.py": None, "app/main.py": "def main():\n    return 7\n\ndef helper(x):\n    if x:\n        return x\n    return 0\n"}),
]


def build_repo(d):
    def git(*args, **env):
        e = dict(os.environ, GIT_CONFIG_GLOBAL="/dev/null", GIT_CONFIG_SYSTEM="/dev/null", **env)
        subprocess.run(["git", *args], cwd=d, check=True, capture_output=True, env=e)
    git("init", "-q", "-b", "main")
    for who, when, files in COMMITS:
        name, email = AUTHORS[who]
        for path, content in files.items():
            full = os.path.join(d, path)
            if content is None:
                os.remove(full)
                continue
            os.makedirs(os.path.dirname(full), exist_ok=True)
            with open(full, "w") as fh:
                fh.write(content)
        git("add", "-A")
        git("commit", "-q", "-m", f"{who} {when[:10]}", GIT_AUTHOR_NAME=name, GIT_AUTHOR_EMAIL=email, GIT_COMMITTER_NAME=name,
            GIT_COMMITTER_EMAIL=email, GIT_AUTHOR_DATE=when, GIT_COMMITTER_DATE=when)


# The pipeline's own git subprocesses must not see the developer's git config either.
HERMETIC_ENV = {"GITMOLE_NOW": NOW, "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_SYSTEM": "/dev/null"}


def normalise(text: str, out_dir: str) -> str:
    text = re.sub(r"^\d+ steps in [\d.]+s\n", "", text, flags=re.M)
    text = text.replace(out_dir, "<out>")
    return "\n".join(line.rstrip() for line in text.strip().splitlines()) + "\n"


def update_requested() -> bool:
    return os.environ.get("UPDATE_GOLDEN", "").strip().lower() in ("1", "true", "yes")


@unittest.skipUnless(run.missing_tools() == [], "external tools not installed")
class Golden(unittest.TestCase):
    def test_report_matches_stored_output(self):
        with tempfile.TemporaryDirectory() as work:
            repo = os.path.join(work, "demo")
            os.makedirs(repo)
            build_repo(repo)
            out = os.path.join(work, "out")
            c = Console(file=io.StringIO(), width=100, record=True, force_terminal=False, color_system=None)
            with patch.dict(os.environ, HERMETIC_ENV):
                rc = cli.main([repo, "--out", out], console=c)
            self.assertEqual(rc, 0)
            actual = normalise(c.export_text(), out)
        if update_requested():
            with open(GOLDEN, "w") as fh:
                fh.write(actual)
        self.assertTrue(os.path.exists(GOLDEN), f"{GOLDEN} is missing; run with UPDATE_GOLDEN=1 to create it, then review it")
        with open(GOLDEN) as fh:
            expected = fh.read()
        if actual != expected:
            import difflib
            diff = "\n".join(difflib.unified_diff(expected.splitlines(), actual.splitlines(), "golden", "actual", lineterm=""))
            self.fail("report differs from tests/golden/report.txt (UPDATE_GOLDEN=1 to accept):\n" + diff)


if __name__ == "__main__":
    unittest.main()

import os
import subprocess
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class ModuleEntryPoint(unittest.TestCase):
    def test_python_m_gitmole_reports_the_version(self):
        p = subprocess.run([sys.executable, "-m", "gitmole", "--version"], cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertTrue(p.stdout.startswith("gitmole "), p.stdout)


class Pyproject(unittest.TestCase):
    def test_declares_the_console_script_and_runtime_dependency(self):
        with open(os.path.join(ROOT, "pyproject.toml")) as fh:
            text = fh.read()
        self.assertIn('gitmole = "gitmole.cli:main"', text)
        self.assertIn('"rich', text)
        self.assertIn('requires-python = ">=3.9"', text)
        self.assertIn("git-of-theseus", text, "plots extra")


if __name__ == "__main__":
    unittest.main()

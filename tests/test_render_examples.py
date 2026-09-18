"""The pure parts of bin/render-examples: the committed document's shape and the pins' shape."""
import importlib.machinery
import importlib.util
import os
import unittest

PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "bin", "render-examples")


def load():
    loader = importlib.machinery.SourceFileLoader("render_examples", PATH)
    spec = importlib.util.spec_from_loader("render_examples", loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


MARKDOWN = """# curl

35000 commits · 1999-12-29 → 2026-09-17 · 900 identities · branch master  
200,000 lines in 1,200 files · C

## Findings

- something

## Watch list

| file | why |
| --- | --- |
| lib/url.c | changed 800 times |

betterleaks scanned every commit on every branch

gitmole 0.10.0 · git 2.55.0 · scc 4.1.0
Full results and plots in /private/tmp/x/gitmole-examples/analysis-curl
"""


class Document(unittest.TestCase):
    def setUp(self):
        self.mod = load()
        self.doc = self.mod.document("curl/curl", "a" * 40, MARKDOWN)

    def test_keeps_the_title_first(self):
        self.assertTrue(self.doc.startswith("# curl\n"))

    def test_provenance_names_version_target_commit_and_date(self):
        from gitmole import __version__
        line = self.doc.split("\n")[2]
        self.assertIn(f"gitmole {__version__}", line)
        self.assertIn("[curl/curl](https://github.com/curl/curl)", line)
        self.assertIn("https://github.com/curl/curl/commit/" + "a" * 40, line)
        self.assertIn("`" + "a" * 12 + "`", line)
        self.assertIn(self.mod.NOW, line)
        self.assertIn("bin/render-examples", line)
        self.assertIn("(https://github.com/antvinni/gitmole#readme)", line)

    def test_drops_the_machine_specific_last_line(self):
        self.assertNotIn("Full results and plots", self.doc)
        self.assertNotIn("/private/tmp", self.doc)
        self.assertNotIn("gitmole 0.10.0 ·", self.doc)
        self.assertTrue(self.doc.endswith("every commit on every branch\n"))

    def test_body_is_otherwise_unchanged(self):
        self.assertIn("| lib/url.c | changed 800 times |", self.doc)
        self.assertIn("## Watch list", self.doc)

    def test_strips_the_footer_render_markdown_actually_emits(self):
        from tests.test_render import sample_report
        from gitmole import render
        markdown = render.markdown(sample_report(), [])
        self.assertIn("Full results and plots in", markdown)          # the fixture copies this sentence
        doc = self.mod.document("demo/demo", "b" * 40, markdown)
        self.assertNotIn("Full results and plots in", doc)
        self.assertNotIn(sample_report()["out_dir"], doc)


class Pins(unittest.TestCase):
    def test_every_example_is_a_github_target_with_a_full_sha(self):
        mod = load()
        self.assertGreaterEqual(len(mod.EXAMPLES), 3)
        for target, sha in mod.EXAMPLES:
            self.assertRegex(target, r"^[\w.-]+/[\w.-]+$")
            self.assertRegex(sha, r"^[0-9a-f]{40}$", f"{target} is not pinned to a full commit hash")

    def test_names_are_unique_and_featured_is_one_of_them(self):
        mod = load()
        from gitmole import run
        names = [run.repo_name(t) for t, _ in mod.EXAMPLES]
        self.assertEqual(len(names), len(set(names)))
        self.assertIn(mod.FEATURED, names)

    def test_constants(self):
        mod = load()
        self.assertRegex(mod.NOW, r"^\d{4}-\d{2}-\d{2}$")
        self.assertEqual(mod.WIDTH, 100)
        self.assertGreaterEqual(mod.TIMEOUT, 900)

    def test_unknown_name_exits_2_and_names_the_choices(self):
        mod = load()
        import io, contextlib
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            rc = mod.main(["nope"])
        self.assertEqual(rc, 2)
        self.assertIn("nope", err.getvalue())
        self.assertIn("curl", err.getvalue())

import io
import json
import os
import tempfile
import unittest

from rich.console import Console

from gitmole import banner, cli


class Banner(unittest.TestCase):
    def test_has_six_rows_of_block_letters(self):
        text = banner.neon()
        rows = text.plain.rstrip("\n").split("\n")
        self.assertEqual(len(rows), 6)
        self.assertTrue(rows[0].startswith("███╗   ███╗"))

    def test_every_row_is_coloured_and_bold(self):
        text = banner.neon()
        styled = [span for span in text.spans if span.style]
        self.assertEqual(len(styled), 6)
        for span in styled:
            self.assertIn("bold", str(span.style))
            self.assertIn("#", str(span.style))

    def test_rows_do_not_share_one_colour(self):
        colours = {str(span.style) for span in banner.neon().spans}
        self.assertGreater(len(colours), 1)


class Rotation(unittest.TestCase):
    def test_offset_rotates_the_palette_down_one_row(self):
        base = [str(sp.style) for sp in banner.neon().spans]
        shifted = [str(sp.style) for sp in banner.neon(offset=1).spans]
        self.assertEqual(shifted[1:], base[:-1])
        self.assertEqual(shifted[0], base[-1])

    def test_offset_wraps_after_six(self):
        self.assertEqual([str(sp.style) for sp in banner.neon(offset=6).spans],
                         [str(sp.style) for sp in banner.neon().spans])


class Animator(unittest.TestCase):
    def test_frames_cycle_through_every_offset_then_repeat(self):
        frames = banner.frames()
        seen = [next(frames).plain for _ in range(7)]
        self.assertEqual(seen[0], seen[6])
        styles = [[str(sp.style) for sp in banner.neon(offset=i).spans][0] for i in range(6)]
        self.assertEqual(len(set(styles)), 6)


class Mole(unittest.TestCase):
    def test_art_is_25_rows_and_at_most_72_wide(self):
        rows = banner.mole().plain.rstrip("\n").split("\n")
        self.assertEqual(len(rows), 25)
        self.assertLessEqual(max(len(r) for r in rows), 72)
        self.assertEqual(banner.MOLE_WIDTH, 72)

    def test_every_visible_character_is_coloured(self):
        text = banner.mole()
        plain = text.plain
        covered = [False] * len(plain)
        for span in text.spans:
            if span.style:
                for i in range(span.start, span.end):
                    covered[i] = True
        uncoloured = {plain[i] for i, c in enumerate(covered) if not c and plain[i] not in " \n"}
        self.assertEqual(uncoloured, set())

    def test_shades_map_to_distinct_colours(self):
        text = banner.mole()
        plain = text.plain
        def colour_of(ch):
            i = plain.index(ch)
            return next(str(sp.style) for sp in text.spans if sp.start <= i < sp.end)
        self.assertNotEqual(colour_of("@"), colour_of("="))
        self.assertNotEqual(colour_of("*"), colour_of("."))


class SplashInCli(unittest.TestCase):
    def _run(self, width):
        import subprocess
        with tempfile.TemporaryDirectory() as d:
            subprocess.run(["git", "init", "-q", d], check=True)
            subprocess.run(["git", "-C", d, "-c", "user.name=T", "-c", "user.email=t@x.com", "commit", "-q", "--allow-empty", "-m", "x"], check=True)
            c = Console(file=io.StringIO(), width=width, record=True, force_terminal=True, color_system="truecolor")
            planner = lambda repo, out, jar, branch="HEAD", **kw: [{"name": "q", "argv": ["true"], "stdout": None, "deps": []}]
            cli.main([d, "--out", os.path.join(d, "out"), "--jar", "/x.jar"], console=c, tool_check=lambda jar: [], planner=planner,
                     estimator=lambda repo, interval: {"files": 1, "samples": 1, "blames": 1})
            return c.export_text()

    def test_splash_on_a_wide_terminal(self):
        self.assertIn("@#%%%%%%%%%%%%%%%###.", self._run(width=100))

    def test_no_splash_on_a_narrow_terminal(self):
        self.assertNotIn("@#%%%%%%%%%%%%%%%###.", self._run(width=60))


class BannerInCli(unittest.TestCase):
    def _run(self, terminal: bool) -> str:
        with tempfile.TemporaryDirectory() as out:
            with open(os.path.join(out, "meta.json"), "w") as fh:
                json.dump({"name": "demo", "commits": 1, "identities": []}, fh)
            c = Console(file=io.StringIO(), width=100, record=True, force_terminal=terminal, color_system="truecolor" if terminal else None)
            cli.main([out, "--no-run"], console=c)
            return c.export_text()

    def test_printed_on_a_terminal(self):
        self.assertIn("███╗   ███╗", self._run(terminal=True))

    def test_not_printed_when_piped(self):
        self.assertNotIn("███╗", self._run(terminal=False))


if __name__ == "__main__":
    unittest.main()

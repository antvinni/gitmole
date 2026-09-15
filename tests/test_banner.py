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

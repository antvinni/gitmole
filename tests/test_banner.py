import io
import json
import os
import tempfile
import unittest

from rich.console import Console

from gitmole import banner, cli


def letter_styles(text):
    """Style of the block-letter span at the start of each banner row."""
    plain = text.plain
    starts = [0] + [i + 1 for i, ch in enumerate(plain) if ch == "\n"][:-1]
    return [str(next(sp.style for sp in text.spans if sp.start == i)) for i in starts]


class Banner(unittest.TestCase):
    def test_has_six_rows_of_block_letters(self):
        text = banner.neon()
        rows = text.plain.rstrip("\n").split("\n")
        self.assertEqual(len(rows), 6)
        self.assertTrue(rows[0].startswith("███╗   ███╗"))

    def test_every_row_is_coloured_and_bold(self):
        styles = letter_styles(banner.neon())
        self.assertEqual(len(styles), 6)
        for st in styles:
            self.assertIn("bold", st)
            self.assertIn("#", st)

    def test_rows_do_not_share_one_colour(self):
        self.assertGreater(len(set(letter_styles(banner.neon()))), 1)


class MoleSprite(unittest.TestCase):
    def test_sprite_sits_right_of_every_letter_row(self):
        rows = banner.neon().plain.rstrip("\n").split("\n")
        widths = {len(r) for r in rows}
        self.assertEqual(len(widths), 1, "rows must be equal width so the sprite lines up")
        self.assertEqual(widths.pop(), banner.LETTERS_WIDTH + banner.GAP + banner.SPRITE_WIDTH)
        for r in rows:
            sprite = r[banner.LETTERS_WIDTH + banner.GAP:]
            self.assertTrue(set(sprite) <= set("▀▄█ "), sprite)

    def test_sprite_is_twelve_pixel_rows_in_six_lines(self):
        self.assertEqual(len(banner.SPRITE), 12)
        self.assertTrue(all(len(row) == banner.SPRITE_WIDTH for row in banner.SPRITE))

    def test_sprite_uses_background_colours_for_lower_pixels(self):
        text = banner.neon()
        bg = [sp for sp in text.spans if sp.style and getattr(sp.style, "bgcolor", None)]
        self.assertGreater(len(bg), 0)

    def test_sprite_does_not_rotate_with_the_letters(self):
        a = [str(sp.style) for sp in banner.neon().spans if sp.style and getattr(sp.style, "bgcolor", None)]
        b = [str(sp.style) for sp in banner.neon(offset=3).spans if sp.style and getattr(sp.style, "bgcolor", None)]
        self.assertEqual(a, b)


class Rotation(unittest.TestCase):
    def test_offset_rotates_the_palette_down_one_row(self):
        base = letter_styles(banner.neon())
        shifted = letter_styles(banner.neon(offset=1))
        self.assertEqual(shifted[1:], base[:-1])
        self.assertEqual(shifted[0], base[-1])

    def test_offset_wraps_after_six(self):
        self.assertEqual(letter_styles(banner.neon(offset=6)), letter_styles(banner.neon()))


def sprite_styles(text):
    return [str(sp.style) for sp in text.spans if sp.style and getattr(sp.style, "bgcolor", None)]


class EyeMovement(unittest.TestCase):
    def test_look_left_and_right_render_differently(self):
        self.assertNotEqual(sprite_styles(banner.neon(look=0)), sprite_styles(banner.neon(look=1)))
        self.assertEqual(banner.neon(look=0).plain, banner.neon(look=1).plain)

    def test_pupils_stay_inside_the_eyes(self):
        for look in (0, 1):
            grid = banner.sprite_grid(look)
            self.assertEqual(len(grid), 12)
            for row in grid:
                self.assertEqual(len(row), 16)
            # pupils only appear on rows 4-5 and in the eye columns 3-5 / 10-12, plus the nose on row 6
            for r, row in enumerate(grid):
                for c, ch in enumerate(row):
                    if ch == "K":
                        self.assertTrue((r in (4, 5) and (3 <= c <= 5 or 10 <= c <= 12)) or (r == 6 and c in (7, 8)), (r, c))

    def test_frames_move_the_eyes_over_time(self):
        gen = banner.frames()
        seen = {tuple(sprite_styles(next(gen))) for _ in range(40)}
        self.assertGreaterEqual(len(seen), 2)


class Animator(unittest.TestCase):
    def test_frames_cycle_through_every_offset_then_repeat(self):
        frames = banner.frames()
        seen = [next(frames).plain for _ in range(7)]
        self.assertEqual(seen[0], seen[6])
        styles = [letter_styles(banner.neon(offset=i))[0] for i in range(6)]
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

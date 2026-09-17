"""The MOLE banner, in neon, with a pixel mole beside it."""
from __future__ import annotations

from rich.color import Color
from rich.style import Style
from rich.text import Text

ART = """\
███╗   ███╗ ██████╗ ██╗     ███████╗
████╗ ████║██╔═══██╗██║     ██╔════╝
██╔████╔██║██║   ██║██║     █████╗  
██║╚██╔╝██║██║   ██║██║     ██╔══╝  
██║ ╚═╝ ██║╚██████╔╝███████╗███████╗
╚═╝     ╚═╝ ╚═════╝ ╚══════╝╚══════╝"""

LETTERS_WIDTH = 36
GAP = 2

# hot magenta -> pink -> electric cyan, one stop per row
NEON = ["#ff00ff", "#ff2ee6", "#ff5cc8", "#c86cff", "#5ad0ff", "#00ffff"]

# Pixel mole, 16 x 12. Two pixel rows per text line via half blocks.
PALETTE = {
    "C": "#5ff0ff",  # cyan outline / mound rim
    "M": "#ff4fe0",  # magenta cap
    "P": "#ff7fc8",  # pink face
    "V": "#c07cff",  # violet body
    "B": "#7fd8f0",  # mound
    "D": "#4aa8c8",  # mound speckle
    "W": "#ffffff",  # muzzle, paws
    "K": "#1b1b2b",  # pupils, nose
}
# "K" on rows 4-5 are the pupils; `look` slides them one column: 0 = inner (toward the letters), 1 = outer.
SPRITE = [
    "....CCCCCCCC....",
    "..CCMMMMMMMMCC..",
    ".CMMMMMMMMMMMMC.",
    ".CPCCCPWWPCCCPC.",
    "CPPKKCPWWPKKCPPC",
    "CPPKKCPWWPKKCPPC",
    "CPPCCCPKKPCCCPPC",
    "CVVVVVVVVVVVVVVC",
    "CVVWWVVVVVVWWVVC",
    "CVVWWVVVVVVWWVVC",
    "CBBBBBDBBBBBDBBC",
    ".CBBDBBBBBDBBBC.",
]
SPRITE_WIDTH = len(SPRITE[0])
EYE_ROWS = (4, 5)
EYES = ((3, 6), (10, 13))  # column ranges of the two eyes


def sprite_grid(look: int = 0) -> list:
    """The pixel grid with pupils shifted to the inner (0) or outer (1) side of each eye."""
    grid = [list(row) for row in SPRITE]
    for r in EYE_ROWS:
        for start, end in EYES:
            for c in range(start, end):
                grid[r][c] = "C"
            if look == 0:
                grid[r][start] = grid[r][start + 1] = "K"
            else:
                grid[r][start + 1] = grid[r][start + 2] = "K"
    return ["".join(row) for row in grid]


def _sprite_rows(look: int = 0) -> list:
    """Six Text rows, each packing two pixel rows with ▀ / ▄ and fg/bg colours."""
    grid = sprite_grid(look)
    rows = []
    for top, bottom in zip(grid[0::2], grid[1::2]):
        line = Text()
        for t, b in zip(top, bottom):
            if t == "." and b == ".":
                line.append(" ")
            elif b == ".":
                line.append("▀", style=Style(color=Color.parse(PALETTE[t])))
            elif t == ".":
                line.append("▄", style=Style(color=Color.parse(PALETTE[b])))
            else:
                line.append("▀", style=Style(color=Color.parse(PALETTE[t]), bgcolor=Color.parse(PALETTE[b])))
        rows.append(line)
    return rows


def neon(offset: int = 0, look: int = 0, version: str = None) -> Text:
    """The banner with the palette rotated down by `offset` rows, and the mole beside it.
    With `version`, a dim `v1.2.3` row underneath: the report's reproducibility stamp."""
    text = Text()
    sprite = _sprite_rows(look)
    for i, row in enumerate(ART.split("\n")):
        colour = NEON[(i - offset) % len(NEON)]
        text.append(row, style=Style(color=Color.parse(colour), bold=True))
        text.append(" " * GAP)
        text.append_text(sprite[i])
        text.append("\n")
    if version:
        text.append(f"v{version}\n", style="dim")
    return text


LOOK_EVERY = 5  # frames per glance; at 10 fps the eyes move every half second


def frames(version: str = None):
    """Endless generator of banner frames: gradient flowing down, eyes glancing side to side."""
    n = 0
    while True:
        yield neon(offset=n % len(NEON), look=(n // LOOK_EVERY) % 2, version=version)
        n += 1

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
SPRITE = [
    "....CCCCCCCC....",
    "..CCMMMMMMMMCC..",
    ".CMMMMMMMMMMMMC.",
    ".CPCKCPWWPCKCPC.",
    "CPPCKCPWWPCKCPPC",
    "CPPCCCPWWPCCCPPC",
    "CPPPPPPKKPPPPPPC",
    "CVVVVVVVVVVVVVVC",
    "CVVWWVVVVVVWWVVC",
    "CVVWWVVVVVVWWVVC",
    "CBBBBBDBBBBBDBBC",
    ".CBBDBBBBBDBBBC.",
]
SPRITE_WIDTH = len(SPRITE[0])


def _sprite_rows() -> list:
    """Six Text rows, each packing two pixel rows with ▀ / ▄ and fg/bg colours."""
    rows = []
    for top, bottom in zip(SPRITE[0::2], SPRITE[1::2]):
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


def neon(offset: int = 0) -> Text:
    """The banner with the palette rotated down by `offset` rows, and the mole beside it."""
    text = Text()
    sprite = _sprite_rows()
    for i, row in enumerate(ART.split("\n")):
        colour = NEON[(i - offset) % len(NEON)]
        text.append(row, style=Style(color=Color.parse(colour), bold=True))
        text.append(" " * GAP)
        text.append_text(sprite[i])
        text.append("\n")
    return text


def frames():
    """Endless generator of banner frames with the gradient flowing downwards."""
    offset = 0
    while True:
        yield neon(offset)
        offset = (offset + 1) % len(NEON)

"""The MOLE banner, in neon."""
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

# hot magenta -> pink -> electric cyan, one stop per row
NEON = ["#ff00ff", "#ff2ee6", "#ff5cc8", "#c86cff", "#5ad0ff", "#00ffff"]


def neon(offset: int = 0) -> Text:
    """The banner with the palette rotated down by `offset` rows."""
    text = Text()
    rows = ART.split("\n")
    for i, row in enumerate(rows):
        colour = NEON[(i - offset) % len(NEON)]
        text.append(row, style=Style(color=Color.parse(colour), bold=True))
        text.append("\n")
    return text


def frames():
    """Endless generator of banner frames with the gradient flowing downwards."""
    offset = 0
    while True:
        yield neon(offset)
        offset = (offset + 1) % len(NEON)


# --- the mole splash -------------------------------------------------------

import os  # noqa: E402

MOLE_WIDTH = 72

# density-shaded art: darkest characters are the mole, mid tones the mound, light ones grass and sky
SHADES = {
    "@": "#4a2c20", "#": "#5a3a2a", "%": "#6b4632",
    "*": "#8b5a3c",
    "+": "#a8763e", "=": "#b9884a",
    "-": "#6abf4b", ":": "#7fcf5c", ".": "#9ddb7a",
}


def mole() -> Text:
    """The mole splash, coloured by shade."""
    path = os.path.join(os.path.dirname(__file__), "mole.txt")
    with open(path, encoding="ascii") as fh:
        art = fh.read().rstrip("\n")
    text = Text()
    for row in art.split("\n"):
        for ch in row:
            text.append(ch, style=Style(color=Color.parse(SHADES[ch])) if ch in SHADES else None)
        text.append("\n")
    return text

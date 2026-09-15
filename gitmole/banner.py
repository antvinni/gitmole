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

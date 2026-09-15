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


def neon() -> Text:
    text = Text()
    for i, row in enumerate(ART.split("\n")):
        text.append(row, style=Style(color=Color.parse(NEON[i]), bold=True))
        text.append("\n")
    return text

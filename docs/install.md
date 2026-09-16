# Install

Every way to install gitmole and the three tools it runs; back to [the README](https://github.com/antvinni/gitmole#readme).

gitmole needs git, Python 3.9 or newer, and three tools on your PATH:
[scc](https://github.com/boyter/scc) for size,
[git-sizer](https://github.com/github/git-sizer) for repository health and
[betterleaks](https://github.com/betterleaks/betterleaks) for secrets. gitmole itself
is a Python package; install it with [pipx](https://pipx.pypa.io) so it gets
its own environment and a `gitmole` command.

## macOS

Homebrew installs gitmole and the three tools in one go. The tap lives in
the gitmole repository, so the first command names it by URL; the second marks it
trusted, which Homebrew 7 requires before it will install from a third-party
tap; after that the short name works everywhere, `brew upgrade` included.

```bash
brew tap antvinni/gitmole https://github.com/antvinni/gitmole
brew trust antvinni/gitmole
brew install gitmole
```

Without Homebrew, install the three tools yourself and use pipx:

```bash
pipx ensurepath                                  # once; then open a new shell
pipx install gitmole
```

## Linux

With Homebrew on Linux the same three commands work unchanged; all three tools
are bottled there. Without Homebrew, take the tools from your package manager
where it has them and from the projects' release pages otherwise; each ships
a static binary, so dropping it into `~/.local/bin` is enough.

```bash
# Debian and Ubuntu: git-sizer and pipx are packaged
sudo apt install git git-sizer pipx
pipx ensurepath                                  # once; then open a new shell

# scc and betterleaks: one static binary each, from their release pages
#   https://github.com/boyter/scc/releases               (the Linux x86_64 or arm64 archive)
#   https://github.com/betterleaks/betterleaks/releases (the linux x64 or arm64 archive)
# unpack and move the binary into ~/.local/bin, then:
chmod +x ~/.local/bin/scc ~/.local/bin/betterleaks

pipx install gitmole
```

On a distribution without a `pipx` package, `python3 -m pip install --user
pipx` installs it. Some distributions package scc or betterleaks as well; if
yours does, prefer that to a downloaded binary.

## Check

```bash
scc --version && git-sizer --version && betterleaks version && gitmole --version
gitmole .                                        # a report of the clone you are in
```

`gitmole` reports any tool it cannot find on the first run.

## Other ways to install

```bash
pipx install 'gitmole[plots]'                                                # adds git-of-theseus for --plots
pipx install gitmole==0.4.0                                                  # a pinned release
pipx install git+https://github.com/antvinni/gitmole                        # main, unreleased
```

`python -m gitmole` works too. From a checkout, `pip install -e .` in a
virtual environment gives an editable install. Use pip 22 or newer: the pip
that ships with macOS's system Python is older and silently builds an empty
package called UNKNOWN from modern project files. pipx brings its own current
pip, and `python3 -m pip install -U pip` fixes a plain venv.

Releases are listed at https://github.com/antvinni/gitmole/releases. Install
from the official repository, PyPI or the Homebrew tap with pinned versions,
not from forks.

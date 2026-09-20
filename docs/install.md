# Install

Every way to install gitmole and the five tools it runs; back to [the README](https://github.com/antvinni/gitmole#readme).

gitmole needs git, Python 3.9 or newer, and five tools on your PATH:
[scc](https://github.com/boyter/scc) for size,
[git-sizer](https://github.com/github/git-sizer) for repository health,
[betterleaks](https://github.com/betterleaks/betterleaks) for secrets,
[jscpd](https://github.com/kucherenko/jscpd) for duplicated blocks and
[osv-scanner](https://github.com/google/osv-scanner) for known vulnerabilities
in the dependencies. gitmole itself
is a Python package; install it with [pipx](https://pipx.pypa.io) so it gets
its own environment and a `gitmole` command.

## macOS

Homebrew installs gitmole and the five tools in one go. The tap lives in
the gitmole repository, so the first command names it by URL; the second marks it
trusted, which Homebrew 7 requires before it will install from a third-party
tap; after that the short name works everywhere, `brew upgrade` included.

```bash
brew tap antvinni/gitmole https://github.com/antvinni/gitmole
brew trust antvinni/gitmole
brew install gitmole
```

Without Homebrew, install the five tools yourself and use pipx:

```bash
pipx ensurepath                                  # once; then open a new shell
pipx install gitmole
```

## Linux

With Homebrew on Linux the same three commands work unchanged; all five tools
are bottled there. Without Homebrew, take the tools from your package manager
where it has them and from the projects' release pages otherwise; each ships
a static binary, so dropping it into `~/.local/bin` is enough.

```bash
# Debian and Ubuntu: git-sizer and pipx are packaged
sudo apt install git git-sizer pipx
pipx ensurepath                                  # once; then open a new shell

# scc, betterleaks, jscpd and osv-scanner: one static binary each, from their release pages
#   https://github.com/boyter/scc/releases               (the Linux x86_64 or arm64 archive)
#   https://github.com/betterleaks/betterleaks/releases (the linux x64 or arm64 archive)
#   https://github.com/kucherenko/jscpd/releases        (the linux x64 or arm64 gnu archive; or pip install jscpd)
#   https://github.com/google/osv-scanner/releases      (the linux_amd64 or linux_arm64 binary)
# unpack and move the binary into ~/.local/bin, then:
chmod +x ~/.local/bin/scc ~/.local/bin/betterleaks ~/.local/bin/jscpd ~/.local/bin/osv-scanner

pipx install gitmole
```

On a distribution without a `pipx` package, `python3 -m pip install --user
pipx` installs it. Some distributions package scc, betterleaks or osv-scanner
as well; if yours does, prefer that to a downloaded binary.

## Check

```bash
scc --version && git-sizer --version && betterleaks version && jscpd --version && osv-scanner --version && gitmole --version
gitmole .                                        # a report of the clone you are in
```

`gitmole` reports any tool it cannot find on the first run.

## The vulnerability database

osv-scanner matches the lock files against a copy of the
[OSV](https://osv.dev) database kept on this machine, and gitmole runs it
offline: nothing leaves the machine, and gitmole never downloads anything.
Fetch the copy once, inside a clone, and the download covers the ecosystems
that clone uses (npm, PyPI, Go, crates.io and so on); run it again to refresh
it, or in a clone of another ecosystem:

```bash
osv-scanner scan source -r --offline-vulnerabilities --download-offline-databases .
```

Until then the report footer says the dependencies were not scanned and
prints that command. The copy lives in osv-scanner's cache directory
(`~/Library/Caches/osv-scalibr` on macOS, `~/.cache/osv-scalibr` on Linux, or
`OSV_SCANNER_LOCAL_DB_CACHE_DIRECTORY`), and the report says how old it is.

## Structure: nesting, debt markers, the import graph

The structure step is optional. It needs `gitmole[structure]`: py-tree-sitter
and one compiled grammar per language (Python, JavaScript, TypeScript and
TSX, Go, Rust, Java, C, C++, Ruby, C#, PHP), each an MIT wheel with nothing to
compile and nothing to download at run time. Python 3.10 or newer.

```bash
pipx install 'gitmole[structure]'
pipx inject gitmole tree-sitter tree-sitter-python tree-sitter-javascript   # or add grammars to an existing install
```

The Homebrew formula does not include it. Without it the step is skipped and
`meta.json` says how to install it; a grammar that is missing skips its
language only. Results are cached by blob hash under
`~/Library/Caches/gitmole/structure` (`~/.cache/gitmole/structure` on
Linux), so a file that has not changed is not parsed twice;
`GITMOLE_CACHE` names another directory, or `off`.

## Other ways to install

```bash
pipx install 'gitmole[plots]'                                                # adds git-of-theseus for --plots
pipx install 'gitmole[structure]'                                            # adds tree-sitter for the structure step
pipx install gitmole==X.Y.Z                                                  # a pinned release, from the releases page
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

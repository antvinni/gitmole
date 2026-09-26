# Install

Every way to install gitmole and the five tools it runs; back to [the README](https://github.com/antvinni/gitmole#readme).

gitmole needs git, Python 3.9 or newer, and five tools, on your PATH or in a
directory of gitmole's own:
[scc](https://github.com/boyter/scc) for size,
[git-sizer](https://github.com/github/git-sizer) for repository health,
[betterleaks](https://github.com/betterleaks/betterleaks) for secrets,
[jscpd](https://github.com/kucherenko/jscpd) for duplicated blocks and
[osv-scanner](https://github.com/google/osv-scanner) for known vulnerabilities
in the dependencies. gitmole itself
is a Python package; install it with [pipx](https://pipx.pypa.io) so it gets
its own environment and a `gitmole` command.

## macOS

Homebrew installs gitmole and the five tools in one go, each at the version
gitmole pins, into gitmole's own `libexec/tools`. The tap lives in
the gitmole repository, so the first command names it by URL; the second marks it
trusted, which Homebrew 7 requires before it will install from a third-party
tap; after that the short name works everywhere, `brew upgrade` included.

```bash
brew tap antvinni/gitmole https://github.com/antvinni/gitmole
brew trust antvinni/gitmole
brew install gitmole
```

Nothing else is needed: the tools come with gitmole rather than as separate
formulae, so a `brew upgrade` of something else cannot move them. They sit
beside gitmole's own environment and are not added to your PATH.

## The pinned versions

One gitmole version is one toolchain. The tools decide part of the report —
betterleaks' rules decide what counts as a secret, scc's definitions decide
what counts as a language — so they are pinned, and the version each release
installs is listed in
[gitmole/tools.py](https://github.com/antvinni/gitmole/blob/main/gitmole/tools.py).
Every report records both what gitmole pinned and what it actually ran, under
`run.tools` and `run.tools_pinned` in `meta.json`, and a run whose tools are
not the pinned ones says so once on stderr. That is a note, not a refusal:
gitmole runs with whatever versions are there.

Without Homebrew, pipx installs gitmole and gitmole installs the tools:

```bash
pipx ensurepath                                  # once; then open a new shell
pipx install gitmole
gitmole --install-tools                          # the five tools, pinned, into gitmole's own directory
```

`--install-tools` downloads the same release archives the formula does, from
github.com (which sends each download on to
release-assets.githubusercontent.com; an allowlist must admit both) and
registry.npmjs.org, about 80 MB on macOS arm64 at 0.36.0. It checks each
against the same sha256, keeps the one executable from each, runs it once to
see that it prints its pinned version, and puts it in a directory per tool and
pin, such as `scc-4.1.0/`, under `~/Library/Application Support/gitmole/tools`
on macOS or `$XDG_DATA_HOME/gitmole/tools`, default
`~/.local/share/gitmole/tools`, on Linux. `GITMOLE_TOOLS` names another
directory; it must be an absolute path (`~` is expanded), and a relative one
is refused rather than resolved inside whatever repository you run in. A run
looks in the current pins' directories before PATH, so a distribution's copy
of a tool cannot shadow the pinned one, and a copy left by an older gitmole is
never used: `gitmole --clean` lists it. `pipx uninstall gitmole` does not
remove the directory; delete it by hand.

Skip the command and the first `gitmole .` asks whether to download the tools
it is missing, when a person is there to answer: stdin and the output are
terminals, no CI variable is set (`CI`, `GITHUB_ACTIONS`, `GITLAB_CI`,
`BUILDKITE`, `TEAMCITY_VERSION`), and no export or gate flag says a script is
reading. Otherwise it names the command and exits 2. Nothing is downloaded
without a yes.

gitmole downloads nothing of its own apart from that. It reaches the network
to clone a remote target you name and to list `owner/*` with `gh`; and git
itself fetches from the remote when a step reads an object a partial clone
(`git clone --filter=...`) left out. A scan of a full local clone reaches
nothing.

On a python.org Python for macOS that has not run its `Install
Certificates.command`, gitmole verifies the downloads against macOS's own
`/etc/ssl/cert.pem`; `SSL_CERT_FILE`, when set, decides alone.

## Linux

With Homebrew on Linux the same three commands work unchanged, and the pinned
tools come with gitmole exactly as on macOS; on Linux arm64, where git-sizer
publishes no build, the formula builds the pinned version from source, which
needs Go at install time. Without Homebrew, `pipx install gitmole` and
`gitmole --install-tools` work as on macOS, on x86_64 and arm64, with the
same one gap: on Linux arm64 `--install-tools` installs the other four and says
why git-sizer did not land.
`go install -ldflags "-X main.ReleaseVersion=1.5.0" github.com/github/git-sizer@v1.5.0`
builds the pinned one into `~/go/bin`, which must then be on PATH (without the
`-X` flag the build prints no version, and `--doctor` cannot tell it is the
pinned one), or take your distribution's package and accept the version note.
On a musl distribution such as Alpine, `--install-tools` takes jscpd's musl
build; the other four are static and are the same files.

The manual route below is for a machine that cannot reach github.com: take the
tools from your package manager where it has them, or copy the archives
[gitmole/tools.py](https://github.com/antvinni/gitmole/blob/main/gitmole/tools.py)
names from a machine that can, and check them against its sha256. Each ships a
static binary, so dropping it into `~/.local/bin` is enough.

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
gitmole --doctor                                 # every tool, found against pinned
gitmole .                                        # a report of the clone you are in
```

`gitmole --doctor` names any tool that is missing or not at its pinned version,
and where to get the pinned one; a run reports a missing tool too, and on a
terminal offers to download it.

## The vulnerability database

osv-scanner matches the lock files against a copy of the
[OSV](https://osv.dev) database kept on this machine, and gitmole runs it
offline: nothing leaves the machine, and gitmole downloads nothing during a scan.
Fetch the copy once, inside a clone, and the download covers the ecosystems
that clone uses (npm, PyPI, Go, crates.io and so on); run it again to refresh
it, or in a clone of another ecosystem:

```bash
osv-scanner scan source -r --offline-vulnerabilities --download-offline-databases .
```

Until then the report footer says the dependencies were not scanned and
prints that command. If `--install-tools` installed osv-scanner, your shell
does not find it by that bare name: `gitmole --doctor` prints the same command
with the full path of the osv-scanner gitmole runs. The copy lives in osv-scanner's cache directory
(`~/Library/Caches/osv-scalibr` on macOS, `~/.cache/osv-scalibr` on Linux, or
`OSV_SCANNER_LOCAL_DB_CACHE_DIRECTORY`), and the report says how old it is.

## Structure: nesting, debt markers, the import graph

The structure step runs by default. Its grammars come with gitmole: py-tree-sitter
and one compiled grammar per language (Python, JavaScript, TypeScript and
TSX, Go, Rust, Java, C, C++, Ruby, C#, PHP), each pinned like the tools and each
an MIT package. Homebrew installs the grammars from their prebuilt wheels rather
than building them, because six of the eleven publish source archives that omit
the generated parser header and cannot be built at all. It needs Python 3.10 or newer, so a gitmole installed on 3.9
skips the step and `meta.json` says why.

`gitmole[structure]` still resolves, and now installs nothing extra. A grammar
that is missing skips its language only. Results are cached by blob hash under
`~/Library/Caches/gitmole/structure` (`~/.cache/gitmole/structure` on
Linux), so a file that has not changed is not parsed twice;
`GITMOLE_CACHE` names another directory, or `off`.

## Other ways to install

```bash
pipx install 'gitmole[plots]'                                                # adds git-of-theseus for --plots
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

"""The versions of the tools gitmole runs, pinned so that one gitmole version means one toolchain.

gitmole's own output is deterministic, but the tools it runs are not gitmole: a newer betterleaks can
change what counts as a secret, a newer scc can count a language differently, and the report would move
with no change here. The Homebrew formula installs exactly these versions into `libexec/tools`, which the
`gitmole` wrapper puts on PATH (behind only the directories `gitmole --install-tools` made for these same
pins), and `docs/development.md` says how to move one. A run that finds
another version still runs: it says so once on stderr and records both versions in `meta.json`, so two
reports that differ can be told apart by cause.

`tests/test_tools.py` holds this table to the formula, so the two cannot drift apart.
"""
from __future__ import annotations

# tool -> the version the formula installs. Moving one is a release of its own: bump it here and in
# Formula/gitmole.rb, then measure, since a tool's own rules decide part of the report.
PINNED = {
    "scc": "4.1.0",
    "git-sizer": "1.5.0",
    "betterleaks": "1.8.1",
    "osv-scanner": "2.6.0",
    "lizard": "1.24.0",
}

# Where each pinned tool's build comes from, per system and CPU: the archives and hashes Formula/gitmole.rb
# names, so `gitmole --install-tools` installs the bytes `brew install gitmole` does. tests/test_tools.py holds
# this table and the formula to each other. An entry with a `note` and no `url` is a platform upstream
# publishes no build for: the formula compiles it at install time, this table cannot.
ARCHIVES = {
    ("darwin", "arm64"): {
        "scc": {"url": "https://github.com/boyter/scc/releases/download/v4.1.0/scc_Darwin_arm64.tar.gz",
                "sha256": "7201c7aa4aace058d43308462cba72adb18f6094c08c0741727455976d0a0747"},
        "git-sizer": {"url": "https://github.com/github/git-sizer/releases/download/v1.5.0/git-sizer-1.5.0-darwin-arm64.zip",
                      "sha256": "7d1e8a6e1218d4640eebcca54c78b855055eb387eac34647b4928f072ffb8805"},
        "betterleaks": {"url": "https://github.com/betterleaks/betterleaks/releases/download/v1.8.1/betterleaks_1.8.1_darwin_arm64.tar.gz",
                        "sha256": "8e80f33b5f2a7426b390347b9fd466033723cb94b6bdffa7572632e2eaec964e"},
        "osv-scanner": {"url": "https://github.com/google/osv-scanner/releases/download/v2.6.0/osv-scanner_darwin_arm64",
                        "sha256": "98c460dcd37de25819babd757d04542045b6243113e209edcd4d89fedb0256b4"},
    },
    ("darwin", "x86_64"): {
        "scc": {"url": "https://github.com/boyter/scc/releases/download/v4.1.0/scc_Darwin_x86_64.tar.gz",
                "sha256": "7f705031228add7e55edded409179a60de6b538d41f153ba2922dee95adda50d"},
        "git-sizer": {"url": "https://github.com/github/git-sizer/releases/download/v1.5.0/git-sizer-1.5.0-darwin-amd64.zip",
                      "sha256": "f491edfb6e6552ecec401cd6a2b57b6790c9110b34286a01a0d315f65530de50"},
        "betterleaks": {"url": "https://github.com/betterleaks/betterleaks/releases/download/v1.8.1/betterleaks_1.8.1_darwin_x64.tar.gz",
                        "sha256": "6abc37df76f881cffae406aa2cec72bea6e6ae64b4e771b3ed21b4aac472ed10"},
        "osv-scanner": {"url": "https://github.com/google/osv-scanner/releases/download/v2.6.0/osv-scanner_darwin_amd64",
                        "sha256": "60c5296637e977b28eeda5c7f13573e447659a632922737f94d11fa7e30ad6ca"},
    },
    ("linux", "arm64"): {
        "scc": {"url": "https://github.com/boyter/scc/releases/download/v4.1.0/scc_Linux_arm64.tar.gz",
                "sha256": "6e0d2a1f8d3540ba7df185477dec40bb7340f1b214bfd303147de5cad2bd7b8b"},
        "git-sizer": {"note": "upstream publishes no Linux arm64 build; the formula compiles it with Go, and "
                              f"`go install -ldflags \"-X main.ReleaseVersion={PINNED['git-sizer']}\" "
                              f"github.com/github/git-sizer@v{PINNED['git-sizer']}` does the same into ~/go/bin "
                              "(without the -X flag the build prints no version)"},
        "betterleaks": {"url": "https://github.com/betterleaks/betterleaks/releases/download/v1.8.1/betterleaks_1.8.1_linux_arm64.tar.gz",
                        "sha256": "bbb578b12a2f65d7082ab436abf37724232bc71d8a078e3c41336574420f1b48"},
        "osv-scanner": {"url": "https://github.com/google/osv-scanner/releases/download/v2.6.0/osv-scanner_linux_arm64",
                        "sha256": "2c71403eb443d05891c4f268c3ad771cf4f16e5443463fd7851ef8f454d3c7e4"},
    },
    ("linux", "x86_64"): {
        "scc": {"url": "https://github.com/boyter/scc/releases/download/v4.1.0/scc_Linux_x86_64.tar.gz",
                "sha256": "c7328436d3027f4357d3d7853f7dc3ac2bbcb4ca08f1adad91a27c593884079b"},
        "git-sizer": {"url": "https://github.com/github/git-sizer/releases/download/v1.5.0/git-sizer-1.5.0-linux-amd64.zip",
                      "sha256": "a166f7692a02ba68239cb014386f0263ec15525a36928784482644423aae2395"},
        "betterleaks": {"url": "https://github.com/betterleaks/betterleaks/releases/download/v1.8.1/betterleaks_1.8.1_linux_x64.tar.gz",
                        "sha256": "efa407244e1ea8e35f582b8a42becdeac08bdead04f68eb752adda722d583c2a"},
        "osv-scanner": {"url": "https://github.com/google/osv-scanner/releases/download/v2.6.0/osv-scanner_linux_amd64",
                        "sha256": "ca69b3d3cd08f889a49dc0a383122f71cc528b83803671df5fd874d97485b108"},
    },
}

# On a musl Linux (Alpine) install.platform_key says ("linux-musl", cpu). The pinned tools are static Go builds
# and run on either C library, so a musl Linux takes the Linux builds. (jscpd's npm builds were per C library
# until it was retired at 0.39.0.)
for _cpu in ("x86_64", "arm64"):
    ARCHIVES[("linux-musl", _cpu)] = dict(ARCHIVES[("linux", _cpu)])

# Where a human gets a tool the installer cannot: named by --doctor and by a failed --install-tools.
RELEASES = {
    "scc": "https://github.com/boyter/scc/releases",
    "git-sizer": "https://github.com/github/git-sizer/releases",
    "betterleaks": "https://github.com/betterleaks/betterleaks/releases",
    "osv-scanner": "https://github.com/google/osv-scanner/releases",
    "lizard": "https://pypi.org/project/lizard/",
}


def differences(found: dict) -> list:
    """[(tool, pinned, found)] for the tools whose version is not the pinned one, sorted. A tool that is
    missing (None) is left out: the run refuses on missing tools before this is asked."""
    out = []
    for name, pinned in sorted(PINNED.items()):
        version = found.get(name)
        if version and version != pinned:
            out.append((name, pinned, version))
    return out


def note(found: dict) -> str | None:
    """The one line a run prints when its toolchain is not the pinned one, or None."""
    diffs = differences(found)
    if not diffs:
        return None
    named = "; ".join(f"{name} {version}, pinned {pinned}" for name, pinned, version in diffs)
    return f"tool versions differ from the pinned set: {named}"

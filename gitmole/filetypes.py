"""Which files count as source code, and how to get paths out of git safely.
Standalone so blame.py and maat.py can import it as scripts."""
from __future__ import annotations

import re
import subprocess
from collections import Counter

# git quotes paths with non-ASCII, quote, backslash or control characters unless told not to;
# every git call that prints paths goes through this prefix.
GIT = ["git", "-c", "core.quotePath=false"]


def git_paths(repo: str, subcommand: str, *args) -> list:
    """Paths printed by a git subcommand, read NUL-separated as bytes so nothing is ever quoted
    and a name that is not valid UTF-8 survives (as surrogate escapes that round-trip into argv)."""
    out = subprocess.run([*GIT, subcommand, "-z", *args], cwd=repo, capture_output=True).stdout
    return sorted(p.decode("utf-8", "surrogateescape") for p in out.split(b"\0") if p)


def unquote(path: str) -> str:
    """Undo git's C-style quoting ("src/\\303\\244.py", "say \\"hi\\".md") when it still appears,
    e.g. in an older log export. Bytes that are not UTF-8 become U+FFFD."""
    if len(path) < 2 or path[0] != '"' or path[-1] != '"':
        return path
    inner = path[1:-1]
    return inner.encode("utf-8").decode("unicode_escape").encode("latin-1").decode("utf-8", "replace")

# Source extensions analysed by default. Docs, data and config are deliberately absent.
DEFAULT = frozenset("""
py pyi pyx js jsx mjs cjs ts tsx vue svelte java kt kts scala groovy clj cljs cljc edn
c cc cpp cxx h hh hpp hxx m mm cs fs fsx vb go rs swift rb erb rake php pl pm t lua r rmd
dart ex exs erl hrl hs lhs ml mli elm nim zig cr jl sql psql plsql sh bash zsh fish ps1 psm1 bat cmd
html htm css scss sass less styl tf tfvars hcl nix cmake gradle sbt proto thrift graphql gql
asm s v sv vhd vhdl cu cl glsl hlsl wgsl
""".split())

# Extensionless files that are code, by lowercased name.
NAMES = frozenset({"makefile", "dockerfile", "rakefile", "gemfile", "justfile", "vagrantfile", "cmakelists.txt", "build.gradle"})


def parse(spec):
    """None -> DEFAULT; 'all' -> None (no filter); 'py, .SQL' -> {'py', 'sql'}."""
    if spec is None:
        return DEFAULT
    if spec.strip().lower() == "all":
        return None
    return {t.strip().lstrip(".").lower() for t in spec.split(",") if t.strip()}


_TEST_PATH = re.compile(r"(^|/)(tests?|spec|specs|__tests__|testing)(/|$)|(^|/)(test_[^/]*|[^/]*_test\.[^/]+|[^/]*\.spec\.[^/]+|[^/]*\.test\.[^/]+)$", re.I)


def is_test_path(path: str) -> bool:
    """A test file or anything under a tests directory: changes with every fix, so not a signal on its own."""
    return bool(_TEST_PATH.search(path))


_DOC_PATH = re.compile(r"(^|/)docs?(/|$)|\.(md|markdown|rst|txt|adoc)$", re.I)


def is_doc_path(path: str) -> bool:
    """Documentation: prose formats anywhere, or anything under docs/. A key in a planning document
    is far more often a template than a leak."""
    return bool(_DOC_PATH.search(path))


def key(path: str) -> str:
    """The lowercased extension, or the whole lowercased name when there is none."""
    name = path.rsplit("/", 1)[-1].lower()
    if name in NAMES:
        return name
    return name.rsplit(".", 1)[-1] if "." in name.strip(".") else name


def matches(path: str, types) -> bool:
    if types is None:
        return True
    k = key(path)
    return k in types or k in NAMES and types is DEFAULT


def discover(repo: str, types=DEFAULT) -> list:
    """[(key, file count, included)] over the index, most common first."""
    counts = Counter(key(p) for p in git_paths(repo, "ls-files"))
    rows = [(k, n, matches(f"x.{k}" if k not in NAMES else k, types)) for k, n in counts.items()]
    return sorted(rows, key=lambda r: (-r[1], r[0]))

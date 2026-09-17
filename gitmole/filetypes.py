"""Which files count as source code, and how to get paths out of git safely.
Standalone so blame.py and maat.py can import it as scripts."""
from __future__ import annotations

import fnmatch
import os
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


_SAMPLE_PATH = re.compile(r"(^|/)(examples?|samples?|fixtures?|testdata|demos?|rules)(/|$)", re.I)


def is_sample_path(path: str) -> bool:
    """Example, sample, fixture, demo and rule directories: a value there is a specimen (a language
    sample, a scanner's own rule definitions), not a credential in use."""
    return bool(_SAMPLE_PATH.search(path))


_VENDOR_PATH = re.compile(r"(^|/)(_?vendor|node_modules|third_?party|external)(/|$)", re.I)


def is_vendor_path(path: str) -> bool:
    """Vendored and third-party trees: somebody else's code, so its complexity and its single
    importer are not this repository's risk."""
    return bool(_VENDOR_PATH.search(path))


_RELEASE_NAMES = {"version", "version.rb", "version.py", "version.go", "version.rs", "version.txt", "__version__.py", "package.json",
                  "package-lock.json", "yarn.lock", "pnpm-lock.yaml", "gemfile", "gemfile.lock", "cargo.toml", "cargo.lock",
                  "pyproject.toml", "setup.py", "setup.cfg", "poetry.lock", "uv.lock", "go.mod", "go.sum", "composer.json", "composer.lock"}


def is_release_path(path: str) -> bool:
    """Release plumbing: version files, manifests, lock files and changelogs. Two of them changing
    together is a release commit, not a dependency between them."""
    name = path.rsplit("/", 1)[-1].lower()
    return name in _RELEASE_NAMES or name.endswith(".gemspec") or name.startswith(("changelog", "changes.", "history.", "news."))


# What a generated file says about itself in its first lines: protoc, ajv, code generators of every kind.
_GENERATED = re.compile(r"auto[- ]?generated|generated (by|from|file|code|automatically|with)|do not (edit|modify)|@generated|code generated", re.I)
GENERATED_HEAD_LINES = 5


def _generated_patterns(repo: str) -> list:
    """The .gitattributes patterns marked linguist-generated at the repository root."""
    try:
        with open(os.path.join(repo, ".gitattributes"), encoding="utf-8", errors="replace") as fh:
            lines = fh.read().splitlines()
    except OSError:
        return []
    out = []
    for line in lines:
        parts = line.split()
        if len(parts) >= 2 and any(p in ("linguist-generated", "linguist-generated=true") for p in parts[1:]):
            out.append(parts[0].lstrip("/"))
    return out


def _attribute_match(path: str, pattern: str) -> bool:
    if "/" in pattern:
        return fnmatch.fnmatchcase(path, pattern) or fnmatch.fnmatchcase(path, pattern.rstrip("/") + "/*")
    return fnmatch.fnmatchcase(path.rsplit("/", 1)[-1], pattern)


def generated_files(repo: str, paths: list) -> list:
    """The tracked files that are generated: marked linguist-generated in .gitattributes, or saying so
    in their first lines. Their complexity and churn are the generator's, not the repository's."""
    patterns = _generated_patterns(repo)
    out = []
    for path in paths:
        if any(_attribute_match(path, p) for p in patterns):
            out.append(path)
            continue
        try:
            with open(os.path.join(repo, path), "rb") as fh:
                head = fh.read(2048)
        except OSError:
            continue
        if any(_GENERATED.search(line) for line in head.decode("utf-8", "replace").splitlines()[:GENERATED_HEAD_LINES]):
            out.append(path)
    return sorted(out)


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

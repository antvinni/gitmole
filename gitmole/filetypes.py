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


_TEST_PATH = re.compile(r"(^|/)(tests?|spec|specs|__tests__|testing|snapshots?|__snapshots__|[\w-]+[_-]tests?|tests?[_-][\w-]+)(/|$)"
                        r"|(^|/)(test_[^/]*|[^/]*_test\.[^/]+|[^/]*\.spec\.[^/]+|[^/]*\.test\.[^/]+|[^/]*\.snap)$", re.I)


def is_test_path(path: str) -> bool:
    """A test file or anything under a tests directory (tests/, pending_tests/, e2e-tests/, test_utils/,
    snapshots/ and .snap files): changes with every fix, so not a signal on its own."""
    return bool(_TEST_PATH.search(path))


_DOC_PATH = re.compile(r"(^|/)docs?([-_][\w-]+)?(/|$)|\.(md|markdown|rst|txt|adoc|pyi|d\.ts)$", re.I)


def is_doc_path(path: str) -> bool:
    """Documentation: prose formats anywhere, anything under docs/, doc/, docs_src/, docs-site/, and
    type stubs (.pyi, .d.ts), which declare shapes and carry no runtime values. A key in a planning
    document, a tutorial or a stub's default is far more often a specimen than a leak."""
    return bool(_DOC_PATH.search(path))


_SAMPLE_PATH = re.compile(r"(^|/)(examples?|samples?|fixtures?|testdata|demos?|rules|stubs?)(/|$)|\.stub$", re.I)
_PACKAGE_EXAMPLE = re.compile(r"(^|/)(com|org|net|io|dev|me|co)/examples?(/|$)", re.I)   # Java's com.example.* is a package, not a sample


def is_sample_path(path: str) -> bool:
    """Example, sample, fixture, demo, rule and stub directories, and .stub files: a value there is a
    specimen (a language sample, a scanner's own rule definitions, a template a generator fills in),
    not a credential in use; code there is not the product. A reverse-domain package such as
    com/example/ is neither."""
    return bool(_SAMPLE_PATH.search(path)) and not _PACKAGE_EXAMPLE.search(path)


_VENDOR_PATH = re.compile(r"(^|/)(_?vendor|vendored|node_modules|third_?party|external|deps|\.yarn)(/|$)|^[^/]+/packages/", re.I)


def is_vendor_path(path: str) -> bool:
    """Vendored and third-party trees: somebody else's code, so its complexity and its single
    importer are not this repository's risk. A `packages/` inside a package (requests/packages/,
    the Python vendoring convention) counts; a monorepo's own `packages/` at the root does not."""
    return bool(_VENDOR_PATH.search(path))


_RELEASE_NAMES = {"version", "version.rb", "version.py", "version.go", "version.rs", "version.txt", "__version__.py", "package.json",
                  "package-lock.json", "yarn.lock", "pnpm-lock.yaml", "gemfile", "gemfile.lock", "cargo.toml", "cargo.lock",
                  "pyproject.toml", "setup.py", "setup.cfg", "poetry.lock", "uv.lock", "go.mod", "go.sum", "composer.json", "composer.lock"}


def is_release_path(path: str) -> bool:
    """Release plumbing: version files, manifests, lock files and changelogs. Two of them changing
    together is a release commit, not a dependency between them."""
    name = path.rsplit("/", 1)[-1].lower()
    return name in _RELEASE_NAMES or name.endswith(".gemspec") or name.startswith(("changelog", "changes.", "history.", "news."))


_LICENCE_NAME = re.compile(r"^(LICEN[CS]E|COPYING)(\.|-|_|$)", re.I)
_HOLDER_STOP = {"copyright", "the", "and", "all", "rights", "reserved", "inc", "llc", "ltd", "contributors", "present", "authors",
                "owner", "owners", "holder", "holders", "notice", "this", "above", "shall", "mean", "entity", "licensor"}


_NOTICE = re.compile(r"^\W*copyright\b|\(c\)|©", re.I)   # a notice line, not legal prose that mentions copyright


def _holders(text: str) -> set:
    """The words that name whoever a licence's copyright notices belong to."""
    out = set()
    for line in text.splitlines():
        if _NOTICE.search(line):
            out |= {t.lower() for t in re.findall(r"[A-Za-z]{3,}", line) if t.lower() not in _HOLDER_STOP}
    return out


def _read_head(repo: str, path: str, size: int = 20_000) -> str:
    try:
        with open(os.path.join(repo, path), "rb") as fh:
            return fh.read(size).decode("utf-8", "replace")
    except OSError:
        return ""


def vendored_dirs(repo: str, paths: list) -> list:
    """Directories holding somebody else's code, by licence: a nested LICENSE or COPYING whose
    copyright lines name none of the holders the root licence names (mypy/typeshed/, a bundled
    googletest). A monorepo's own packages carry the same holder and stay. Without a root licence
    naming anyone there is nothing to compare against."""
    ours = set()
    for p in paths:
        if "/" not in p and _LICENCE_NAME.match(p):
            ours |= _holders(_read_head(repo, p))
    if not ours:
        return []
    out = set()
    for p in paths:
        head, _, name = p.rpartition("/")
        if head and _LICENCE_NAME.match(name) and not (_holders(_read_head(repo, p)) & ours):
            out.add(head + "/")
    return sorted(out)


def vendor_dirs(report: dict) -> tuple:
    """The vendored directories a run found by licence (see vendored_dirs)."""
    return tuple((report.get("meta") or {}).get("vendored") or [])


def is_vendored(path: str, dirs=()) -> bool:
    """is_vendor_path, or under a directory the run found to be vendored by licence."""
    return is_vendor_path(path) or any(path.startswith(d) for d in dirs)


_SOURCE_EXT = {"c", "cc", "cpp", "cxx", "m", "mm"}
_HEADER_EXT = {"h", "hh", "hpp", "hxx"}


def is_header_pair(a: str, b: str) -> bool:
    """A C-family source file and its own header, same directory and stem: they change together by
    construction, so the pair says nothing about a hidden dependency."""
    if a == b:
        return False
    (da, sa, ea), (db, sb, eb) = _split(a), _split(b)
    return da == db and sa == sb and ({ea, eb} & _SOURCE_EXT) and ({ea, eb} & _HEADER_EXT) and ea != eb


def _split(path: str) -> tuple:
    head, _, name = path.rpartition("/")
    stem, _, ext = name.rpartition(".")
    return head, stem, ext.lower()


def plumbing_paths(report: dict) -> set:
    """Files the change log showed to be release plumbing by behaviour rather than by name: nearly
    every commit touching them changed a line or two (a version constant in __init__.py)."""
    return {r["entity"] for r in report.get("plumbing") or []}


def is_release(path: str, plumbing=frozenset()) -> bool:
    """is_release_path, or a path the change log showed to be plumbing (see plumbing_paths)."""
    return is_release_path(path) or path in plumbing


# What a generated file says about itself in its first lines: protoc, ajv, code generators of every kind.
_GENERATED = re.compile(r"auto[- ]?generated|generated (by|from|file|code|automatically|with)|do not (edit|modify)|@generated|code generated", re.I)
GENERATED_HEAD_LINES = 5
_GENERATED_NAME = re.compile(r"\.(min\.js|min\.css|bundle\.js|map)$|(^|/)dist/", re.I)   # a build output by name: nobody edits a bundle, a source map or dist/


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
        if _GENERATED_NAME.search(path) or any(_attribute_match(path, p) for p in patterns):
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

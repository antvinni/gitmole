"""Which files count as source code, and how to get paths out of git safely.
Standalone so blame.py and maat.py can import it as scripts."""
from __future__ import annotations

import functools
import json
import os
import posixpath
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


_TEST_PATH = re.compile(r"(^|/)(tests?|spec|specs|__tests__|testing|testsuite|snapshots?|__snapshots__|[\w-]+[_-]tests?|tests?[_-][\w-]+)(/|$)"
                        r"|(^|/)(test_[^/]*|[^/]*_test\.[^/]+|[^/]*\.spec\.[^/]+|[^/]*\.test\.[^/]+|[^/]*\.snap)$", re.I)

# Suffix conventions of test frameworks, case-sensitive (Contest.java is not a Test, requests/ is not a
# Tests/ target): JUnit/XCTest/NUnit's FooTest(s), hspec/ScalaTest's FooSpec, RSpec's _spec.rb, Foundry's
# .t.sol, HDL testbenches tb_x / x_tb, and test-target directories such as AppTests/ or AppUITests/.
_TEST_SUFFIX = re.compile(r"[A-Za-z0-9]Tests?\.(java|kt|kts|scala|groovy|swift|cs)$|[A-Za-z0-9]Spec\.(hs|lhs|scala|kt|groovy)$|_spec\.rb$|\.t\.sol$"
                          r"|(^|/)tb_[^/]*\.(v|sv|vhd|vhdl)$|_tb\.(v|sv|vhd|vhdl)$|(^|/)[A-Za-z0-9]+Tests/")


_MOCK_PATH = re.compile(r"(^|/)mocks?/|(^|/)mock_[^/]+$|(^|/)mock\.[a-z]+$|_mocks?\.[a-z]+$", re.I)   # gomock's mock_x.go, x_mock.go, mocks/


def is_mock_path(path: str) -> bool:
    """A test double by the conventions mock generators and test suites use: a mocks/ directory, mock.go,
    mock_x.go, x_mock.go. A value in one is a fake for a test, not a credential in use."""
    return bool(_MOCK_PATH.search(path))


_TOOLING_PATH = re.compile(r"(^|/)hack/")


def is_tooling_path(path: str) -> bool:
    """Developer tooling by the Go ecosystem's convention: hack/ holds the scripts and local test setups
    that build and run the project, not what it ships."""
    return bool(_TOOLING_PATH.search(path))


def is_test_path(path: str) -> bool:
    """A test file or anything under a tests directory (tests/, pending_tests/, e2e-tests/, test_utils/,
    snapshots/ and .snap files): changes with every fix, so not a signal on its own. Also the suffix
    conventions of test frameworks: FooTest.java, user_spec.rb, ParserSpec.hs, Vault.t.sol, tb_counter.v,
    and AppTests/ directories."""
    return bool(_TEST_PATH.search(path) or _TEST_SUFFIX.search(path))


_DOC_PATH = re.compile(r"(^|/)docs?([-_][\w-]+)?(/|$)|\.(md|markdown|rst|txt|adoc|pyi|d\.ts)$|(^|/)[A-Za-z0-9]+Docs/", re.I)


def is_doc_path(path: str) -> bool:
    """Documentation: prose formats anywhere, anything under docs/, doc/, docs_src/, docs-site/ or a
    CamelCase ProjectDocs/ (the AppTests/ convention for documentation), and
    type stubs (.pyi, .d.ts), which declare shapes and carry no runtime values. A key in a planning
    document, a tutorial or a stub's default is far more often a specimen than a leak."""
    return bool(_DOC_PATH.search(path))


_SAMPLE_PATH = re.compile(r"(^|/)(examples?|samples?|fixtures?([-_][\w-]+)?|testdata|demos?|rules|stubs?|tutorials?|exercises?(files)?)(/|$)"
                          r"|\.stub$|(^|/)testdata[._-][^/]*$", re.I)   # fixtures-expired/, a testdata.20k file
_PACKAGE_EXAMPLE = re.compile(r"(^|/)(com|org|net|io|dev|me|co)/examples?(/|$)", re.I)   # Java's com.example.* is a package, not a sample


def is_sample_path(path: str) -> bool:
    """Example, sample, fixture, demo, tutorial, exercise, rule and stub directories, and .stub files
    (a course's exercise binaries are teaching material): a value there is a
    specimen (a language sample, a scanner's own rule definitions, a template a generator fills in),
    not a credential in use; code there is not the product. A reverse-domain package such as
    com/example/ is neither."""
    return bool(_SAMPLE_PATH.search(path)) and not _PACKAGE_EXAMPLE.search(path)


_VENDOR_PATH = re.compile(r"(^|/)(_?vendor|vendored|node_modules|third_?party|external|deps|\.yarn|Godeps/_workspace)(/|$)", re.I)   # Godeps/_workspace: godep's vendoring


def is_vendor_path(path: str) -> bool:
    """Vendored and third-party trees by name: somebody else's code, so its complexity and its single
    importer are not this repository's risk. A `packages/` inside a top-level directory needs the
    repository to decide (packages_vendored)."""
    return bool(_VENDOR_PATH.search(path))


_PACKAGES_DIR = re.compile(r"^([^/]+)/packages/")


def _workspace_globs(repo: str, manifest_dirs: list) -> set:
    """The workspace patterns the package.json (`workspaces`, a list or {packages: [...]}), pnpm-workspace.yaml
    (`packages:`) and lerna.json (`packages`) in `manifest_dirs` declare, each joined to its manifest's
    directory: the trees a JavaScript monorepo says are its own. A manifest that does not parse declares
    nothing; an exclusion (`!packages/old`) is left out."""
    out = set()
    for d in manifest_dirs:
        at = (d + "/") if d else ""
        found = []
        for name, key in (("package.json", "workspaces"), ("lerna.json", "packages")):
            try:
                value = json.loads(_read_head(repo, at + name, 200_000) or "null")
            except ValueError:
                continue
            value = value.get(key) if isinstance(value, dict) else None
            value = value.get("packages") if isinstance(value, dict) else value
            found += [g for g in value if isinstance(g, str)] if isinstance(value, list) else []
        pnpm = re.search(r"^packages:[ \t]*\n((?:[ \t]+.*\n?|\n)*)", _read_head(repo, at + "pnpm-workspace.yaml"), re.M)
        if pnpm:
            found += re.findall(r"^[ \t]+-[ \t]*['\"]?([^'\"#\s]+)", pnpm.group(1), re.M)
        out |= {posixpath.normpath(at + g) for g in found if not g.startswith("!")}
    return out


def packages_vendored(repo: str, paths: list) -> list:
    """`X/packages/` inside a top-level directory, each ending in `/`: the Python vendoring convention
    (requests/packages/), unless a workspace manifest in X or at the root declares that tree the
    repository's own (react's compiler/package.json lists packages/* as its workspaces). A monorepo's
    own `packages/` at the root is never a candidate."""
    dirs = sorted({m.group(1) for p in paths if (m := _PACKAGES_DIR.match(p))})
    if not dirs:
        return []
    globs = _workspace_globs(repo, ["", *dirs])
    return [f"{d}/packages/" for d in dirs if not any(g == f"{d}/packages" or g.startswith(f"{d}/packages/") for g in globs)]


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
_YEAR = re.compile(r"\b(19|20)\d\d\b")
_OPENS = re.compile(r"^\W*copyright\b.*(\(c\)|©)", re.I)
# ...and it is dated, or opens "Copyright (c)": "Copyright [yyyy] [name of copyright owner]" is a template, and
# Apache's "(c) You must retain ..." is a list item


def _is_notice(line: str) -> bool:
    return bool(_NOTICE.search(line)) and bool(_YEAR.search(line) or _OPENS.search(line))


def _holders(text: str) -> set:
    """The words that name whoever a licence's copyright notices belong to. A notice line has a year or
    opens "Copyright (c)"; licence prose that merely mentions the copyright owner names nobody."""
    out = set()
    for line in text.splitlines():
        if _is_notice(line):
            out |= {t.lower() for t in re.findall(r"[A-Za-z]{3,}", line) if t.lower() not in _HOLDER_STOP}
    return out


HEADER_LINES = 40          # a file's own notice sits in its opening comment
HEADER_SHARE = 0.10        # a holder named in this share of the tree's source files is the project's own


def _authors(repo: str) -> list:
    """The history's author names, each as its set of words of three letters or more: people who commit
    here. A notice names one of them when it holds every word of the name, so a shared first name does
    not make a stranger's code ours."""
    out = subprocess.run([*GIT, "log", "HEAD", "--format=%aN"], cwd=repo, capture_output=True).stdout.decode("utf-8", "replace")
    names = {frozenset(t.lower() for t in re.findall(r"[A-Za-z]{3,}", n)) for n in set(out.split("\n"))}
    return [n for n in names if len(n) >= 2]   # a one-word handle is too easily a word of the notice


def header_vendored(repo: str, paths: list, ours: set) -> list:
    """Directories whose source files carry somebody else's copyright notice in their opening comment
    (a compression library copied in with its per-file licence headers), each ending in `/`: two or
    more files, and at least half the directory's source files, name holders that are none of `ours`,
    none of the holders a tenth or more of the tree's source files name, and no author of this history by
    full name."""
    headed, sources = {}, 0
    for p in paths:
        if matches(p, DEFAULT):
            sources += 1
            head = "\n".join(_read_head(repo, p, 4000).splitlines()[:HEADER_LINES])
            holders = _holders(head)
            if holders:
                headed[p] = holders
    if not headed:
        return []
    common = Counter(w for h in headed.values() for w in h)
    own = set(ours) | {w for w, n in common.items() if n >= HEADER_SHARE * sources}
    people = _authors(repo)

    def theirs(holders):
        return not (holders & own) and not any(name <= holders for name in people)
    by_dir = {}
    for p in paths:
        if matches(p, DEFAULT):
            by_dir.setdefault(p.rpartition("/")[0], []).append(p)
    out = []
    for d, files in sorted(by_dir.items()):
        foreign = [p for p in files if p in headed and theirs(headed[p])]
        if d and len(foreign) >= 2 and 2 * len(foreign) >= len(files):
            out.append(d + "/")
    return out


def _read_head(repo: str, path: str, size: int = 20_000) -> str:
    try:
        with open(os.path.join(repo, path), "rb") as fh:
            return fh.read(size).decode("utf-8", "replace")
    except OSError:
        return ""


def vendored_paths(repo: str, paths: list, attrs: dict = None) -> list:
    """Somebody else's code, as the repository itself says: directories holding a nested LICENSE or
    COPYING whose copyright lines name none of the holders the root licence names (mypy/typeshed/, a
    bundled googletest), each ending in `/`; directories whose files' own headers name somebody else
    (header_vendored); a `packages/` inside a top-level directory that no workspace declares
    (packages_vendored); and every file marked linguist-vendored in .gitattributes,
    as git resolves it. A monorepo's own packages carry the same holder and stay. Without a root licence
    naming anyone there is no licence comparison. `attrs` is attributes() when the caller has it."""
    attrs = attributes(repo, paths) if attrs is None else attrs
    out = {p for p in paths if "linguist-vendored" in attrs.get(p, ())}
    ours = set()
    for p in paths:
        if "/" not in p and _LICENCE_NAME.match(p):
            ours |= _holders(_read_head(repo, p))
    if ours:
        for p in paths:
            head, _, name = p.rpartition("/")
            if head and _LICENCE_NAME.match(name) and not (_holders(_read_head(repo, p)) & ours):
                out.add(head + "/")
    out.update(header_vendored(repo, paths, ours))
    out.update(packages_vendored(repo, paths))
    return sorted(out)


def vendor_dirs(report: dict) -> tuple:
    """The vendored directories and files a run found (see vendored_paths)."""
    return tuple((report.get("meta") or {}).get("vendored") or [])


@functools.lru_cache(maxsize=8)
def _vendor_split(dirs: tuple) -> tuple:
    """The run's vendored list as the two things it actually is: file entries, matched exactly, and
    directory entries, matched by prefix. Cached because every caller passes the same tuple."""
    return frozenset(d for d in dirs if not d.endswith("/")), tuple(d for d in dirs if d.endswith("/"))


def is_vendored(path: str, dirs=()) -> bool:
    """is_vendor_path, or listed by the run (see vendored_paths): a directory entry, ending in `/`, by
    prefix; a file entry exactly."""
    files, prefixes = _vendor_split(tuple(dirs))
    return is_vendor_path(path) or path in files or path.startswith(prefixes)


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


# File names that exist to hold a login: dotenv files and their per-environment variants, the network and
# package-index credential files, SSH private keys and the .ssh directory. Cross-ecosystem conventions of
# tooling, like Makefile above; a template (.env.example) is not one.
_CREDENTIAL_NAME = re.compile(r"^(\.env(\..+)?|\.netrc|_netrc|\.pypirc|\.dockercfg|id_(rsa|dsa|ecdsa|ed25519))$")
_CREDENTIAL_TEMPLATE = re.compile(r"^\.env\.(.+\.)?(example|sample|template|dist)$")
_SSH_DIR = re.compile(r"(^|/)\.ssh/")


def is_credential_path(path: str) -> bool:
    """A file that by its name holds a credential, tracked: a finding whatever its contents, unless it
    sits in test or example code, where a specimen is expected."""
    if is_test_path(path) or is_sample_path(path):
        return False
    if _SSH_DIR.search(path):
        return True
    name = path.rsplit("/", 1)[-1].lower()
    return bool(_CREDENTIAL_NAME.match(name)) and not _CREDENTIAL_TEMPLATE.match(name)


def credential_files(paths: list) -> list:
    return sorted(p for p in paths if is_credential_path(p))


# What a generated file says about itself in its first lines: protoc, ajv, code generators of every kind.
_GENERATED = re.compile(r"auto[- ]?generated|generated (by|from|file|code|automatically|with)|do not (edit|modify)|@generated|code generated", re.I)
GENERATED_HEAD_LINES = 5
# Past a leading licence comment, only a comment that says it of this file: @generated, an upper-case DO NOT
# EDIT, "this file is generated", or a tool's banner, a comment opening "A ..." that ends "generated by TOOL" or
# "made by TOOL 1.2" (flex's "A lexical scanner generated by flex", Bison's "A Bison parser, made by GNU Bison
# 3.7.4."). A comment that mentions generated code ("an auto-generated key", "the code generated by the
# compiler", "Do not edit the code below") says nothing about the file it sits in.
GENERATED_DEEP_LINES = 40
_COMMENT_LINE = re.compile(r"^\s*(//|#|/\*|\*|--|;|<!--|%)")
# A shell heredoc (cat <<EOF, fragment <<'EOF'): what follows is text the script writes, banner and all, so the
# script is the generator and not its output. The delimiter is upper case, which a C++ `out << name` is not.
_HEREDOC = re.compile(r"<<-?\s*(['\"]?)[A-Z_]{2,}\1(\s|$)")
_GENERATED_DEEP = re.compile(r"@generated|(?<![\"'])DO NOT (?i:edit|modify)\b"
                             r"|\b(?i:this|the) (?i:file|source|source code|code|header|module) (?i:is|was|has been) (?i:automatically |auto[- ]?)?(?i:generated)")
_NOT_ARTICLE = r"(?!(?i:the|a|an|this|that|our|your|its|their)\b)"   # a tool has a name; "the compiler" is a description
_GENERATED_BANNER = re.compile(r"^\W*(A|An)\b[^.]{0,60}?\b(generated by " + _NOT_ARTICLE + r"[A-Za-z][\w.+-]*( [A-Za-z][\w.+-]*)?( v?\d[\w.]*)?"
                               r"|made by " + _NOT_ARTICLE + r"[A-Za-z][\w.+-]*( [A-Za-z][\w.+-]*)? v?\d[\w.]*)[\s.]*(\*/)?\s*$")


def says_generated(text: str, name: str = "") -> bool:
    """Whether a file's opening says it is generated: any marker in its first five lines, and past them,
    within forty, a comment that says it of this file. A banner that names the file itself belongs to the
    generator (curl's optiontable.pl holds the banner it writes), not to its output, and so does one past a
    heredoc opener."""
    lines = text.splitlines()
    if any(_GENERATED.search(line) for line in lines[:GENERATED_HEAD_LINES]):
        return True
    if any(_HEREDOC.search(line) for line in lines[:GENERATED_HEAD_LINES]):
        return False
    for line in lines[GENERATED_HEAD_LINES:GENERATED_DEEP_LINES]:
        if _HEREDOC.search(line):
            return False
        if not _COMMENT_LINE.match(line):
            continue
        if name and name in line:
            continue
        if _GENERATED_DEEP.search(line) or _GENERATED_BANNER.search(_COMMENT_LINE.sub("", line)):
            return True
    return False


_GENERATED_NAME = re.compile(r"\.(min\.js|min\.css|bundle\.js|map)$|(^|/)dist/", re.I)   # a build output by name: nobody edits a bundle, a source map or dist/


def attributes(repo: str, paths: list, cached: bool = False, env: dict = None) -> dict:
    """path -> the linguist attributes git sets on it (linguist-generated, linguist-vendored), resolved by
    git itself, so a nested .gitattributes and info/attributes count exactly as they do for git. `cached`
    reads the .gitattributes files of the index instead of the working tree: with GIT_INDEX_FILE in `env`
    pointing at a temporary index, that is the tree at another commit (the backtest). A plain directory
    that is no repository, or a git that fails, attributes nothing."""
    if not paths:
        return {}
    argv = [*GIT, "check-attr", "--stdin", "-z", *(["--cached"] if cached else []), "linguist-generated", "linguist-vendored"]
    stdin = b"".join(p.encode("utf-8", "surrogateescape") + b"\0" for p in paths)
    proc = subprocess.run(argv, cwd=repo, env=env, input=stdin, capture_output=True)
    if proc.returncode != 0:
        return {}  # the main run goes on without linguist classifications; only the backtest raises on this
    out = {}
    fields = proc.stdout.split(b"\0")
    for i in range(0, len(fields) - 2, 3):   # -z prints path, attribute, value, each NUL-terminated
        path, attr, value = (f.decode("utf-8", "surrogateescape") for f in fields[i:i + 3])
        if value in ("set", "true"):
            out.setdefault(path, set()).add(attr)
    return out


def generated_files(repo: str, paths: list, attrs: dict = None) -> list:
    """The tracked files that are generated: a build output by name, marked linguist-generated (as git
    resolves it), or saying so in their opening (says_generated). Their complexity and churn are the generator's, not
    the repository's. `attrs` is attributes() when the caller already has it."""
    attrs = attributes(repo, paths) if attrs is None else attrs
    out = []
    for path in paths:
        if _GENERATED_NAME.search(path) or "linguist-generated" in attrs.get(path, ()):
            out.append(path)
            continue
        try:
            with open(os.path.join(repo, path), "rb") as fh:
                head = fh.read(8192)   # forty lines of licence header can run past a couple of kilobytes
        except OSError:
            continue
        if says_generated(head.decode("utf-8", "replace"), path.rsplit("/", 1)[-1]):
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

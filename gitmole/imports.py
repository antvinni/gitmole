"""Which packages the tracked source imports: for a vulnerable package, whether anything loads it at
all, and the declared dependencies nothing loads. Not reachability (osv-scanner's call analysis needs a
buildable tree and a toolchain); a textual read of import statements, so it says `imported` and never
`reachable`, and nothing is suppressed on it.

Each ecosystem keys on its own import syntax: `import`/`require` specifiers in JavaScript and
TypeScript, import paths in Go, `crate::` paths and `extern crate` in Rust, `import`/`from` in Python,
`require` in Ruby. Where the import name is the package name by the ecosystem's rules (npm, Go
modules, Rust crates with `-` read as `_`), an absent import is `false`. Where it need not be (a Python
distribution's modules, a gem's files), a match is `true` and no match is `unknown`: gitmole keeps no
table of distribution names, so it cannot say PyYAML is imported as yaml. Declared-but-never-imported
is read for package.json `dependencies`, go.mod direct requirements and Cargo.toml `[dependencies]`
only, for the same reason."""
from __future__ import annotations

import json
import os
import re

try:
    from . import filetypes
except ImportError:  # run inside a script: the package directory is sys.path[0]
    import filetypes

LIMIT = 1_000_000   # bytes read per file: a larger file is generated or data, not code that imports
JS = (".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx", ".mts", ".cts", ".vue", ".svelte", ".astro")
EXTENSIONS = {"npm": JS, "PyPI": (".py", ".pyi"), "Go": (".go",), "crates.io": (".rs",), "RubyGems": (".rb", ".rake", ".gemspec")}
EXACT = {"npm", "Go", "crates.io"}   # the import name is the package name: an absent import is false

_JS_SPEC = re.compile(r"""(?:\bfrom\s*|\bimport\s*\(\s*|\bimport\s+|\brequire\s*\(\s*|\brequire\.resolve\s*\(\s*|\bexport\s*\*\s*from\s*)['"]([^'"\s]+)['"]""")
_PY_IMPORT = re.compile(r"^[ \t]*import[ \t]+([\w., \t]+)", re.M)
_PY_FROM = re.compile(r"^[ \t]*from[ \t]+(\w[\w.]*)[ \t]+import\b", re.M)
_GO_BLOCK = re.compile(r"^import\s*\((.*?)^\)", re.M | re.S)
_GO_ONE = re.compile(r"""^import\s+(?:[\w.]+\s+)?"([^"]+)\"""", re.M)
_GO_QUOTED = re.compile(r'"([^"]+)"')
_GO_GENERATE = re.compile(r"^//go:generate\s+(.*)$", re.M)
_RS_PATH = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]*)::")
_RS_CRATE = re.compile(r"\b(?:extern\s+crate|use)\s+(?:::)?([A-Za-z_][A-Za-z0-9_]*)")
_RB_REQUIRE = re.compile(r"""\brequire(?:_relative)?\s*\(?\s*['"]([^'"]+)['"]""")


def js_package(spec: str) -> str | None:
    """The npm package a specifier loads: `@scope/name` or `name`, without the subpath; None for a
    relative path, an absolute one, a URL or a node: builtin."""
    if not spec or spec[0] in "./#~" or ":" in spec.split("/", 1)[0]:
        return None
    parts = spec.split("/")
    if spec.startswith("@"):
        return "/".join(parts[:2]) if len(parts) > 1 else None
    return parts[0]


def python_name(name: str) -> str:
    """PEP 503's normal form, with `_` as the separator so a module name compares with it."""
    return re.sub(r"[-_.]+", "_", name).lower()


def rust_name(name: str) -> str:
    return name.replace("-", "_")


def _read(repo: str, path: str) -> str:
    try:
        with open(os.path.join(repo, path), "rb") as fh:
            data = fh.read(LIMIT + 1)
    except OSError:
        return ""
    if len(data) > LIMIT or b"\0" in data[:8000]:
        return ""
    return data.decode("utf-8", "replace")


def scan_text(ecosystem: str, text: str) -> set:
    """The names one file imports, in the form the ecosystem's packages are compared in."""
    found = set()
    if ecosystem == "npm":
        found.update(p for p in (js_package(s) for s in _JS_SPEC.findall(text)) if p)
    elif ecosystem == "PyPI":
        for group in _PY_IMPORT.findall(text):
            for item in group.split(","):
                word = item.strip().split(" ")[0].split(".")[0]
                if word:
                    found.add(python_name(word))
        found.update(python_name(m.split(".")[0]) for m in _PY_FROM.findall(text))
    elif ecosystem == "Go":
        for block in _GO_BLOCK.findall(text):
            found.update(_GO_QUOTED.findall(block))
        found.update(_GO_ONE.findall(text))
        for line in _GO_GENERATE.findall(text):   # a tool run by go:generate is a use of its module
            found.update(w for w in line.split() if "." in w.split("/")[0] and "/" in w)
    elif ecosystem == "crates.io":
        found.update(_RS_PATH.findall(text))
        found.update(_RS_CRATE.findall(text))
    elif ecosystem == "RubyGems":
        found.update(_RB_REQUIRE.findall(text))
    return found


def scan(repo: str, ecosystems, paths: list = None) -> dict:
    """{ecosystem: the names imported anywhere in the tracked files of that ecosystem's extensions}.
    node_modules is left out: somebody else's imports."""
    paths = filetypes.git_paths(repo, "ls-files") if paths is None else paths
    wanted = {e: EXTENSIONS[e] for e in ecosystems if e in EXTENSIONS}
    out = {e: set() for e in wanted}
    for path in paths:
        if "node_modules/" in path:
            continue
        low = path.lower()
        for eco, exts in wanted.items():
            if low.endswith(exts):
                out[eco] |= scan_text(eco, _read(repo, path))
    return out


def _go_match(module: str, imported: set) -> bool:
    return any(p == module or p.startswith(module + "/") for p in imported)


def is_imported(ecosystem: str, name: str, imported: dict):
    """True, False or None (unknown) for one package against scan()'s result."""
    names = imported.get(ecosystem)
    if names is None:
        return None
    if ecosystem == "npm":
        hit = name in names
    elif ecosystem == "Go":
        if name in ("stdlib", "toolchain"):
            return None
        hit = _go_match(name, names)
    elif ecosystem == "crates.io":
        hit = rust_name(name) in names
    elif ecosystem == "PyPI":
        hit = python_name(name) in names
    elif ecosystem == "RubyGems":
        hit = any(r == name or r.split("/")[0] == name or r == name.replace("-", "/") for r in names)
    else:
        return None
    if hit:
        return True
    return False if ecosystem in EXACT else None


def annotate(rows: list, repo: str, paths: list = None) -> None:
    """Set `imported` to true, false or "unknown" on each vulnerable-package row, in place."""
    if not rows:
        return
    imported = scan(repo, {r.get("ecosystem") for r in rows}, paths)
    for r in rows:
        value = is_imported(r.get("ecosystem"), r.get("name", ""), imported)
        r["imported"] = "unknown" if value is None else value


# --- declared, never imported -------------------------------------------------------------------

def _aside(path: str) -> bool:
    return ("node_modules/" in path or filetypes.is_test_path(path) or filetypes.is_sample_path(path)
            or filetypes.is_vendor_path(path) or filetypes.is_doc_path(path))


def npm_declared(text: str) -> tuple:
    """(the runtime `dependencies` of a package.json, its scripts' text). Type-only packages
    (`@types/`) are left out: nothing imports them by name."""
    try:
        data = json.loads(text)
    except ValueError:
        return [], ""
    if not isinstance(data, dict):
        return [], ""
    deps = data.get("dependencies") or {}
    scripts = data.get("scripts") or {}
    names = sorted(n for n in deps if isinstance(n, str) and not n.startswith("@types/")) if isinstance(deps, dict) else []
    return names, " ".join(str(v) for v in scripts.values()) if isinstance(scripts, dict) else ""


def go_declared(text: str) -> list:
    """go.mod's direct requirements: the `require` lines without `// indirect`."""
    out, block = [], False
    for raw in text.split("\n"):
        line = raw.strip()
        if line.startswith("require ("):
            block = True
            continue
        if block and line.startswith(")"):
            block = False
            continue
        body = line[len("require "):] if line.startswith("require ") else line if block else None
        if body is None or not body or body.startswith("//") or "// indirect" in body:
            continue
        parts = body.split()
        if len(parts) >= 2:
            out.append(parts[0])
    return sorted(set(out))


_TOML_HEADER = re.compile(r"^\s*\[+\s*([^\]]+?)\s*\]+\s*(?:#.*)?$")
_TOML_KEY = re.compile(r"""^\s*("?)([A-Za-z0-9_.-]+)\1\s*=""")


def cargo_declared(text: str) -> list:
    """Cargo.toml's `[dependencies]`, target-specific ones included, as the names the code uses: the
    table key, which a `package =` rename makes the import name. Build and dev dependencies are left
    out, and so are `-sys` crates, which are linked for their native library and not named in code."""
    out, table = [], ""
    for line in text.split("\n"):
        h = _TOML_HEADER.match(line)
        if h:
            table = h.group(1).replace('"', "").replace("'", "")
            if re.match(r"^(target\..+\.)?dependencies\.[A-Za-z0-9_-]+$", table):   # [dependencies.name]
                out.append(table.rsplit(".", 1)[1])
            continue
        if re.match(r"^(target\..+\.)?dependencies$", table):
            k = _TOML_KEY.match(line)
            if k:
                out.append(k.group(2).split(".")[0])   # `name.workspace = true` is a dotted key
    return sorted({n for n in out if not n.endswith(("-sys", "_sys"))})


def _quoted_heads(text: str) -> set:
    """Every quoted string's package head, for configuration files that name a package without
    importing it (a Babel preset, an ESLint plugin, a Jest environment)."""
    out = set()
    for s in re.findall(r"""['"`]([@\w][\w@./-]*)['"`]""", text):
        p = js_package(s)
        if p:
            out.add(p)
    return out


def _manifest_or_lock(path: str) -> bool:
    """A manifest or lock file names every dependency in quotes, so it cannot count as a use of one."""
    base = os.path.basename(path).lower()
    return base in ("package.json", "composer.json", "deno.json") or "lock" in base or base == "npm-shrinkwrap.json"


def unused(repo: str, paths: list = None) -> dict:
    """Declared runtime dependencies that no tracked file imports: for npm, not imported, not named in
    a quoted string of any JavaScript, TypeScript, JSON or YAML file other than a manifest or lock file,
    and not a word in the manifest's scripts; for Go, no import path or go:generate line under the module; for Rust, no `name::` path,
    `use name` or `extern crate name`. Manifests under tests, examples, documentation and vendored
    code are left out."""
    paths = filetypes.git_paths(repo, "ls-files") if paths is None else paths
    manifests = [p for p in paths if os.path.basename(p) in ("package.json", "go.mod", "Cargo.toml") and not _aside(p)]
    if not manifests:
        return {"manifests": 0, "unused": [], "count": 0}
    kinds = {os.path.basename(p) for p in manifests}
    wanted = ({"npm"} if "package.json" in kinds else set()) | ({"Go"} if "go.mod" in kinds else set()) | ({"crates.io"} if "Cargo.toml" in kinds else set())
    imported = scan(repo, wanted, paths)
    if "npm" in wanted:
        named = set()
        for p in paths:
            if "node_modules/" not in p and p.lower().endswith(JS + (".json", ".jsonc", ".json5", ".yml", ".yaml")) and not _manifest_or_lock(p):
                named |= _quoted_heads(_read(repo, p))
        imported["npm"] = imported["npm"] | named
    out = []
    for m in sorted(manifests):
        text = _read(repo, m)
        base = os.path.basename(m)
        if base == "package.json":
            names, scripts = npm_declared(text)
            words = set(re.findall(r"[\w@./-]+", scripts))
            out += [{"manifest": m, "ecosystem": "npm", "package": n} for n in names
                    if n not in imported["npm"] and n not in words and n.rsplit("/", 1)[-1] not in words]
        elif base == "go.mod":
            out += [{"manifest": m, "ecosystem": "Go", "package": n} for n in go_declared(text) if not _go_match(n, imported["Go"])]
        else:
            out += [{"manifest": m, "ecosystem": "crates.io", "package": n} for n in cargo_declared(text) if rust_name(n) not in imported["crates.io"]]
    return {"manifests": len(manifests), "unused": out[:50], "count": len(out)}

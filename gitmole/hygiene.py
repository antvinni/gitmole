"""Repository hygiene from the clone alone: the checks OpenSSF Scorecard and the OSPS Baseline make
through the GitHub API, done with file and git reads; Trojan Source after Boucher and Anderson (USENIX
Security 2023).

Runs as a pipeline step, `python -m gitmole.hygiene OUT_DIR`, from inside the repository, and writes
hygiene.json; findings.py turns it into findings. Each check keys on a convention of the ecosystem (a
workflow's `uses:`, a lock file's name, `.gitmodules`, a symlink's mode) or on the shape of a value (a
40-hex ref, magic bytes, a bidirectional control character), never on a name:

- actions: `uses: owner/repo@ref` in .github/workflows where the ref is not a full commit SHA;
- lockfiles: a manifest whose last commit is newer than its lock file's, or a manifest with none;
- updates: the ecosystems whose lock files are tracked that dependabot.yml does not cover;
- presence: a licence, a security policy, a contribution guide, CODEOWNERS and the CODEOWNERS paths
  that match nothing;
- confusion: a scoped npm package resolved from a registry other than the one .npmrc declares for
  its scope, several registries in one lock file, a pip `extra-index-url`;
- install: packages with install scripts in package-lock.json, lifecycle scripts in a tracked
  package.json, process and network calls in setup.py;
- binaries: executables by their magic bytes, native libraries by name, blobs .gitattributes sends
  to LFS that were committed as they are;
- submodules: plain http:// or git:// URLs, credentials in a URL, relative URLs, `branch =`;
- symlinks: links that resolve outside the tree or into .git/;
- trojan: bidirectional control characters (CVE-2021-42574) and identifiers that mix Latin with
  Cyrillic, Greek or another confusable script, in source files;
- licences: the licences the project and its locked dependencies declare (licences.py);
- imports: declared dependencies that nothing tracked imports (imports.py)."""
from __future__ import annotations

import ast
import json
import os
import re
import subprocess
import sys
import unicodedata
from collections import defaultdict
from urllib.parse import urlsplit

try:
    from . import filetypes, imports, licences
except ImportError:  # run as a script: the package directory is sys.path[0]
    import filetypes
    import imports
    import licences

CAP = 50   # rows kept per list: the count says how many there were


def _tracked(repo: str) -> list:
    return filetypes.git_paths(repo, "ls-files")


def _read(repo: str, path: str, limit: int = 2_000_000):
    try:
        with open(os.path.join(repo, path), "rb") as fh:
            return fh.read(limit)
    except OSError:
        return None


def _text(repo: str, path: str) -> str:
    data = _read(repo, path)
    return data.decode("utf-8", "replace") if data is not None else ""


def _aside(path: str) -> bool:
    """Test, example, documentation and vendored paths, and anything under node_modules: specimens and
    somebody else's code, which the checks about this repository's own supply chain leave out."""
    return ("node_modules/" in path or filetypes.is_test_path(path) or filetypes.is_sample_path(path)
            or filetypes.is_vendor_path(path))


# --- GitHub Actions pinning ---------------------------------------------------------------------

_USES = re.compile(r"""^\s*(?:-\s*)?uses:\s*['"]?([^'"\s#]+)""", re.M)
_SHA = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")


def actions_pinning(repo: str) -> dict:
    """Every `uses:` in the tracked workflows: pinned to a full commit SHA, a local action or a docker
    image (neither), or unpinned (a tag or a branch the action's owner can move)."""
    unpinned, pinned, local = [], 0, 0
    for path in _tracked(repo):
        if not re.match(r"^\.github/workflows/[^/]+\.ya?ml$", path):
            continue
        for ref in _USES.findall(_text(repo, path)):
            if ref.startswith("./") or ref.startswith("docker://") or "@" not in ref:   # a remote action always names its ref
                local += 1
            elif "@" in ref and _SHA.match(ref.rsplit("@", 1)[1]):
                pinned += 1
            else:
                unpinned.append({"file": path, "uses": ref})
    return {"unpinned": unpinned[:CAP], "unpinned_count": len(unpinned), "pinned": pinned, "local": local}


# --- lock files ---------------------------------------------------------------------------------

LOCKS = {"package.json": ["package-lock.json", "npm-shrinkwrap.json", "yarn.lock", "pnpm-lock.yaml", "bun.lock", "bun.lockb"],
         "pyproject.toml": ["uv.lock", "poetry.lock", "pdm.lock"],
         "Pipfile": ["Pipfile.lock"],
         "Cargo.toml": ["Cargo.lock"],
         "go.mod": ["go.sum"],
         "Gemfile": ["Gemfile.lock"],
         "composer.json": ["composer.lock"]}
LOCK_EXPECTED = {"package.json", "Pipfile", "Cargo.toml", "go.mod", "Gemfile", "composer.json"}   # pyproject libraries often lock nothing


def _last_commit(repo: str, path: str) -> int:
    out = subprocess.run(["git", "log", "-1", "--format=%ct", "--", path], cwd=repo, capture_output=True, text=True).stdout.strip()
    return int(out) if out.isdigit() else 0


def _day(ts: int) -> str:
    import datetime as dt
    return dt.datetime.fromtimestamp(ts, dt.timezone.utc).date().isoformat()


def lockfiles(repo: str) -> dict:
    """Each tracked manifest with the lock file that pins it: in its own directory, or in an ancestor
    (a workspace member is locked by the root). Drift is a manifest whose last commit is newer than its
    lock file's, by commit time, which a clone keeps and mtime does not; missing is a manifest of an
    ecosystem that locks by convention with no lock file anywhere above it."""
    tracked = set(_tracked(repo))
    drift, missing, pairs = [], [], 0
    for path in sorted(tracked):
        name = path.rsplit("/", 1)[-1]
        if name not in LOCKS or _aside(path):
            continue
        d = os.path.dirname(path)
        lock = None
        while True:
            for candidate in LOCKS[name]:
                full = f"{d}/{candidate}" if d else candidate
                if full in tracked:
                    lock = full
                    break
            if lock or not d:
                break
            d = os.path.dirname(d)
        if not lock:
            if name in LOCK_EXPECTED:
                missing.append({"manifest": path, "expected": LOCKS[name][:1] if name != "package.json" else ["package-lock.json"]})
            continue
        pairs += 1
        m, l = _last_commit(repo, path), _last_commit(repo, lock)
        if m > l:
            drift.append({"manifest": path, "lockfile": lock, "manifest_date": _day(m), "lockfile_date": _day(l)})
    return {"drift": drift[:CAP], "drift_count": len(drift), "missing": missing[:CAP], "missing_count": len(missing), "pairs": pairs}


# --- dependency update tooling ------------------------------------------------------------------

ECOSYSTEMS = {"package-lock.json": "npm", "npm-shrinkwrap.json": "npm", "yarn.lock": "npm", "pnpm-lock.yaml": "npm", "bun.lock": "bun",
              "uv.lock": "pip", "poetry.lock": "pip", "pdm.lock": "pip", "Pipfile.lock": "pip", "Cargo.lock": "cargo", "go.sum": "gomod",
              "Gemfile.lock": "bundler", "composer.lock": "composer"}
_ALIASES = {"uv": "pip", "pipenv": "pip", "poetry": "pip", "yarn": "npm", "pnpm": "npm"}
_RENOVATE = {"renovate.json", "renovate.json5", ".renovaterc", ".renovaterc.json", ".github/renovate.json", ".github/renovate.json5",
             ".gitlab/renovate.json"}
_ECOSYSTEM_LINE = re.compile(r"""package-ecosystem:\s*['"]?([\w-]+)""")


def dependency_updates(repo: str) -> dict:
    """Which update bot the repository declares, and the ecosystems with a tracked lock file it does not
    cover. Renovate discovers every manager by itself, so under Renovate nothing is uncovered."""
    tracked = _tracked(repo)
    present = sorted({ECOSYSTEMS[p.rsplit("/", 1)[-1]] for p in tracked if p.rsplit("/", 1)[-1] in ECOSYSTEMS and not _aside(p)})
    if any(p in _RENOVATE for p in tracked):
        return {"tool": "renovate", "covered": present, "uncovered": []}
    config = next((p for p in (".github/dependabot.yml", ".github/dependabot.yaml") if p in tracked), None)
    if not config:
        return {"tool": None, "covered": [], "uncovered": present}
    declared = sorted({_ALIASES.get(e, e) for e in _ECOSYSTEM_LINE.findall(_text(repo, config))})
    return {"tool": "dependabot", "covered": declared, "uncovered": [e for e in present if e not in declared]}


# --- licence, security policy, CODEOWNERS -------------------------------------------------------

def _codeowners_matches(pattern: str, paths: list) -> bool:
    """gitignore-style matching, as CODEOWNERS uses it: a leading or inner slash anchors to the root, a
    trailing slash means a directory, `*` and `**` glob."""
    from fnmatch import fnmatch
    anchored = pattern.startswith("/") or "/" in pattern.rstrip("/")
    p = pattern.lstrip("/")
    directory = p.endswith("/")
    p = p.rstrip("/")
    for path in paths:
        if anchored:
            if fnmatch(path, p) or path.startswith(p + "/") or (not directory and fnmatch(path, p + "/*")):
                return True
        elif fnmatch(path.rsplit("/", 1)[-1], p) or fnmatch(path, "*/" + p) or fnmatch(path, p) or f"/{p}/" in f"/{path}" or path.startswith(p + "/"):
            return True
    return False


_SECURITY_HEADING = re.compile(r"^#{1,6}\s+(.*\bsecurity\b.*?)\s*#*\s*$", re.I | re.M)


def _readme_security(repo: str, tracked: list):
    """`README.md#heading` when the root README has a Markdown heading about security ("Reporting security
    issues"): the project saying where its policy is, often an organisation's SECURITY.md elsewhere, which
    a clone cannot see."""
    readme = next((p for p in tracked if "/" not in p and re.match(r"^readme(\.md|\.markdown)?$", p, re.I)), None)
    headings = [h.strip() for h in _SECURITY_HEADING.findall(_text(repo, readme))] if readme else []
    best = next((h for h in headings if re.search(r"report|vulnerab|disclos", h, re.I)), headings[0] if headings else None)   # how to report, over an audit
    return f"{readme}#{best}" if best else None


def presence(repo: str) -> dict:
    tracked = _tracked(repo)
    roots = ("", ".github/", "docs/")

    def first(names):
        for prefix in roots:
            for p in tracked:
                if p.startswith(prefix) and "/" not in p[len(prefix):] and re.match(names, p[len(prefix):], re.I):
                    return p
        return None
    licence = next((p for p in tracked if "/" not in p and re.match(r"^(licen[cs]e|copying)(\.|-|$)", p, re.I)), None) \
        or next(("LICENSES/" for p in tracked if p.startswith("LICENSES/")), None)   # the REUSE layout
    policy = first(r"^security(\.md|\.txt|\.rst)?$") or _readme_security(repo, tracked)
    contributing = first(r"^contributing(\.md|\.txt|\.rst|\.adoc)?$")
    owners = first(r"^codeowners$")
    missing = []
    if owners:
        for line in _text(repo, owners).split("\n"):
            line = line.split("#", 1)[0].strip()
            if not line:
                continue
            pattern = line.split()[0]
            if not _codeowners_matches(pattern, tracked):
                missing.append(pattern)
    return {"license": licence, "security_policy": policy, "contributing": contributing, "codeowners": owners, "codeowners_missing": missing[:CAP]}


# --- dependency confusion -----------------------------------------------------------------------

_SCOPE_REGISTRY = re.compile(r"^\s*(@[\w.-]+):registry\s*=\s*(\S+)", re.M)


def _host(url: str) -> str:
    try:
        return urlsplit(url).hostname or ""
    except ValueError:
        return ""


def _npm_packages(lock: dict):
    """(name, entry) for every package in a package-lock, v2/v3 `packages` or v1 `dependencies`."""
    packages = lock.get("packages")
    if isinstance(packages, dict):
        for key, entry in packages.items():
            if key and isinstance(entry, dict):
                yield key.rsplit("node_modules/", 1)[-1], entry
        return

    def walk(deps):
        for name, entry in (deps or {}).items():
            if isinstance(entry, dict):
                yield name, entry
                yield from walk(entry.get("dependencies"))
    yield from walk(lock.get("dependencies"))


def _npm_locks(repo: str) -> list:
    out = []
    for path in _tracked(repo):
        if path.rsplit("/", 1)[-1] in ("package-lock.json", "npm-shrinkwrap.json") and not _aside(path):
            try:
                out.append((path, json.loads(_text(repo, path) or "{}")))
            except ValueError:
                continue
    return out


def dependency_confusion(repo: str) -> dict:
    """The shapes of a dependency-confusion attack a clone can show: a package of a scope .npmrc sends to
    a private registry that the lock file resolved from another host; lock files that mix registries;
    a pip configuration that adds an extra index, which is the setting the attack needs."""
    tracked = _tracked(repo)
    scopes = {}
    for path in tracked:
        if path.rsplit("/", 1)[-1] == ".npmrc":
            for scope, url in _SCOPE_REGISTRY.findall(_text(repo, path)):
                scopes[scope] = _host(url)
    scoped, registries = [], {}
    for path, lock in _npm_locks(repo):
        hosts = set()
        for name, entry in _npm_packages(lock):
            resolved = entry.get("resolved")
            if not isinstance(resolved, str) or "://" not in resolved:
                continue
            host = _host(resolved)
            hosts.add(host)
            scope = name.split("/", 1)[0] if name.startswith("@") else None
            if scope in scopes and scopes[scope] and host != scopes[scope]:
                scoped.append({"lockfile": path, "package": name, "registry": host, "declared": scopes[scope]})
        if len(hosts) > 1:
            registries[path] = sorted(hosts)
    pip = [p for p in tracked if (p.rsplit("/", 1)[-1] in ("pip.conf", "pip.ini") or re.search(r"(^|/)requirements[\w.-]*\.(txt|in)$", p))
           and not _aside(p) and re.search(r"extra[-_]index[-_]url", _text(repo, p), re.I)]
    return {"scoped_public": scoped[:CAP], "scoped_public_count": len(scoped), "registries": registries, "pip_extra_index": pip}


# --- install-time code --------------------------------------------------------------------------

LIFECYCLE = ("preinstall", "install", "postinstall")
_RISKY_CALLS = re.compile(r"^(subprocess\.\w+|os\.(system|popen|exec\w*|spawn\w*)|urllib\.request\.urlopen|urlopen|requests\.\w+|socket\.\w+|exec|eval)$")


def _call_name(node) -> str:
    f = node.func
    parts = []
    while isinstance(f, ast.Attribute):
        parts.append(f.attr)
        f = f.value
    if isinstance(f, ast.Name):
        parts.append(f.id)
    return ".".join(reversed(parts))


def install_scripts(repo: str) -> dict:
    """Code that runs when a dependency is installed: packages package-lock.json marks hasInstallScript,
    lifecycle scripts in the repository's own package.json files, and process, network and exec calls
    in a setup.py, which pip runs."""
    in_lock = []
    for path, lock in _npm_locks(repo):
        for name, entry in _npm_packages(lock):
            if entry.get("hasInstallScript"):
                in_lock.append({"lockfile": path, "package": name})
    manifests, setups = [], []
    for path in _tracked(repo):
        name = path.rsplit("/", 1)[-1]
        if _aside(path):
            continue
        if name == "package.json":
            try:
                scripts = (json.loads(_text(repo, path) or "{}").get("scripts") or {})
            except (ValueError, AttributeError):
                continue
            hooks = [k for k in LIFECYCLE if k in scripts]
            if hooks:
                manifests.append({"file": path, "scripts": hooks})
        elif name == "setup.py":
            try:
                tree = ast.parse(_text(repo, path))
            except SyntaxError:
                continue
            calls = sorted({n for n in (_call_name(c) for c in ast.walk(tree) if isinstance(c, ast.Call)) if _RISKY_CALLS.match(n)})
            if calls:
                setups.append({"file": path, "calls": calls})
    return {"lockfile": in_lock[:CAP], "lockfile_count": len(in_lock), "manifests": manifests[:CAP], "setup_py": setups[:CAP]}


# --- committed binaries -------------------------------------------------------------------------

_MAGIC = [(b"\x7fELF", "ELF"), (b"MZ", "PE"), (b"\xfe\xed\xfa\xce", "Mach-O"), (b"\xfe\xed\xfa\xcf", "Mach-O"),
          (b"\xce\xfa\xed\xfe", "Mach-O"), (b"\xcf\xfa\xed\xfe", "Mach-O"), (b"\xca\xfe\xba\xbe", "Mach-O")]
_NATIVE = re.compile(r"\.(so(\.\d+)*|dll|dylib|jar|pyd|node|exe)$", re.I)


def _binary_paths(repo: str) -> list:
    """Tracked files whose index content git itself calls binary (`ls-files --eol`: i/-text)."""
    out = subprocess.run([*filetypes.GIT, "ls-files", "--eol", "-z"], cwd=repo, capture_output=True).stdout
    paths = []
    for entry in out.split(b"\0"):
        if not entry or b"\t" not in entry:
            continue
        info, path = entry.split(b"\t", 1)
        if info.startswith(b"i/-text"):
            paths.append(path.decode("utf-8", "surrogateescape"))
    return sorted(paths)


def binaries(repo: str) -> dict:
    """Executables by their first bytes (ELF, PE, Mach-O; a Java class shares Mach-O's fat magic and is
    left alone), native libraries and archives by name, and binary blobs .gitattributes sends to LFS
    that were committed as they are rather than as pointers."""
    found = _binary_paths(repo)
    executables = []
    for path in found:
        head = _read(repo, path, 8) or b""
        fmt = next((name for magic, name in _MAGIC if head.startswith(magic)), None)
        if fmt and not path.endswith(".class"):
            executables.append({"file": path, "format": fmt})
    unpointed = []
    if found:
        proc = subprocess.run(["git", "check-attr", "-z", "--stdin", "filter"], cwd=repo, capture_output=True,
                              input=b"\0".join(p.encode("utf-8", "surrogateescape") for p in found) + b"\0")
        parts = proc.stdout.split(b"\0")
        for i in range(0, len(parts) - 2, 3):
            if parts[i + 2] == b"lfs":
                unpointed.append(parts[i].decode("utf-8", "surrogateescape"))
    return {"binaries": len(found), "executables": executables[:CAP], "executables_count": len(executables),
            "by_name": [p for p in found if _NATIVE.search(p)][:CAP], "lfs_unpointed": sorted(unpointed)[:CAP]}


# --- submodules ---------------------------------------------------------------------------------

def submodules(repo: str) -> dict:
    """What .gitmodules declares: plain http:// or git:// URLs anyone on the path can rewrite,
    credentials in a URL (redacted here), relative URLs that resolve against wherever the clone came
    from, and `branch =`, the only floating reference git supports."""
    if not os.path.isfile(os.path.join(repo, ".gitmodules")):
        return {"count": 0, "insecure": [], "credentials": [], "relative": [], "floating": []}
    out = subprocess.run(["git", "config", "-f", ".gitmodules", "-z", "--list"], cwd=repo, capture_output=True).stdout.decode("utf-8", "replace")
    subs = defaultdict(dict)
    for entry in out.split("\0"):
        key, _, value = entry.partition("\n")
        if not key.startswith("submodule."):
            continue
        name, _, field = key[len("submodule."):].rpartition(".")
        subs[name][field] = value
    insecure, creds, relative, floating = [], [], [], []
    for name in sorted(subs):
        url, branch = subs[name].get("url", ""), subs[name].get("branch")
        if url.startswith(("http://", "git://")):
            insecure.append({"name": name, "url": url})
        m = re.match(r"^([a-z][a-z0-9+.-]*://)([^/@]+)@(.*)$", url, re.I)
        if m and (":" in m.group(2) or m.group(1).lower().startswith("http")):
            creds.append({"name": name, "url": f"{m.group(1)}***@{m.group(3)}"})
        if url.startswith(("./", "../")):
            relative.append({"name": name, "url": url})
        if branch:
            floating.append({"name": name, "branch": branch})
    return {"count": len(subs), "insecure": insecure, "credentials": creds, "relative": relative, "floating": floating}


# --- symlinks -----------------------------------------------------------------------------------

def symlinks(repo: str) -> dict:
    """Tracked symlinks (mode 120000) whose target resolves outside the tree or into .git/: a checkout
    that follows them reads or writes where the repository has no business."""
    out = subprocess.run([*filetypes.GIT, "ls-files", "-s", "-z"], cwd=repo, capture_output=True).stdout
    links = []
    for entry in out.split(b"\0"):
        if entry.startswith(b"120000 "):
            meta, path = entry.split(b"\t", 1)
            links.append((path.decode("utf-8", "surrogateescape"), meta.split()[1].decode()))
    outside, into_git = [], []
    if links:
        proc = subprocess.run(["git", "cat-file", "--batch"], cwd=repo, capture_output=True,
                              input="\n".join(sha for _, sha in links).encode() + b"\n")
        data, pos, targets = proc.stdout, 0, []
        for _ in links:
            end = data.find(b"\n", pos)
            size = int(data[pos:end].split()[2])
            targets.append(data[end + 1:end + 1 + size].decode("utf-8", "surrogateescape"))
            pos = end + 1 + size + 1
        for (path, _), target in zip(links, targets):
            resolved = os.path.normpath(os.path.join(os.path.dirname(path), target))
            if os.path.isabs(target) or resolved == ".." or resolved.startswith("../"):
                outside.append({"link": path, "target": target})
            elif resolved == ".git" or resolved.startswith(".git/"):
                into_git.append({"link": path, "target": target})
    return {"count": len(links), "outside": outside[:CAP], "into_git": into_git[:CAP]}


# --- Trojan Source ------------------------------------------------------------------------------

# The embeddings, overrides and isolates Trojan Source reorders code with. The direction marks (U+200E, U+200F,
# U+061C) only set the direction of neutral characters and are ordinary text in right-to-left locales.
BIDI = {0x202A, 0x202B, 0x202C, 0x202D, 0x202E, 0x2066, 0x2067, 0x2068, 0x2069}
CONFUSABLE = {"CYRILLIC", "GREEK", "ARMENIAN", "CHEROKEE"}   # scripts whose letters pass for Latin ones
# The letters of those scripts that Unicode's confusables data (UTS #39) maps to an ASCII letter. A token
# spoofs a Latin identifier only when every letter of it reads as Latin; μs in a comment does not, pr\u043ecess does.
LOOKALIKE = set(
    "\u0430\u0435\u043e\u0440\u0441\u0443\u0445\u0455\u0456\u0458\u0501\u051b\u051d\u04bb\u04cf\u04af"   # Cyrillic а е о р с у х ѕ і ј ԁ ԛ ԝ һ ӏ ү
    "\u0410\u0412\u0415\u041a\u041c\u041d\u041e\u0420\u0421\u0422\u0425\u0405\u0406\u0408\u04ae\u051a\u051c\u04c0"   # А В Е К М Н О Р С Т Х Ѕ І Ј Ү Ԛ Ԝ Ӏ
    "\u03bf\u03b1\u03bd\u03c1\u03b9\u03b3\u03c5"   # Greek ο α ν ρ ι γ υ
    "\u0391\u0392\u0395\u0396\u0397\u0399\u039a\u039c\u039d\u039f\u03a1\u03a4\u03a5\u03a7"   # Α Β Ε Ζ Η Ι Κ Μ Ν Ο Ρ Τ Υ Χ
    "\u0585\u057d\u0570\u0578\u0581\u0566"   # Armenian օ ս հ ո ց զ
    "\u13aa\u13f4\u13df\u13ac\u13bb\u13ab\u13e6\u13de\u13b7\u13e2\u13da\u13a2\u13d4\u13c3"   # Cherokee Ꭺ Ᏼ Ꮯ Ꭼ Ꮋ Ꭻ Ꮶ Ꮮ Ꮇ Ꮲ Ꮪ Ꭲ Ꮤ Ꮓ
)
_WORD = re.compile(r"[^\W\d]\w*")


def _script(c: str) -> str:
    try:
        return unicodedata.name(c).split()[0]
    except ValueError:
        return ""


def trojan_source(repo: str, generated=frozenset()) -> dict:
    """Bidirectional control characters in source files (CVE-2021-42574: code that reads one way and
    compiles another), and identifiers that mix Latin with a confusable script's look-alike letters (a
    Cyrillic о inside `process`; a Greek μ before a unit reads as itself, and is not one). Source files only, tests, examples, documentation and vendored code left out, so the
    false-positive rate stays near zero; a whole word in one script is prose, not a trick."""
    bidi, mixed, files = [], [], 0
    for path in _tracked(repo):
        if not filetypes.matches(path, filetypes.DEFAULT) or _aside(path) or filetypes.is_doc_path(path) or path in generated:
            continue   # a generated file's bytes (a protobuf descriptor) are the generator's, not a reviewer's trap
        data = _read(repo, path)
        if data is None or b"\0" in data[:8000]:
            continue
        files += 1
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            continue
        if text.isascii():
            continue
        for n, line in enumerate(text.split("\n"), 1):
            for c in line:
                if ord(c) in BIDI:
                    bidi.append({"file": path, "line": n, "char": f"U+{ord(c):04X}"})
            for token in _WORD.findall(line):
                if token.isascii():
                    continue
                scripts = {_script(c) for c in token if c.isalpha()}
                foreign = [c for c in token if c.isalpha() and _script(c) in CONFUSABLE]
                if "LATIN" in scripts and foreign and all(c in LOOKALIKE for c in foreign):
                    mixed.append({"file": path, "line": n, "token": token, "scripts": sorted(scripts)})
    return {"files": files, "bidi": bidi[:CAP], "bidi_count": len(bidi), "mixed_script": mixed[:CAP], "mixed_script_count": len(mixed)}


CHECKS = {"actions": actions_pinning, "lockfiles": lockfiles, "updates": dependency_updates, "presence": presence,
          "confusion": dependency_confusion, "install": install_scripts, "binaries": binaries, "submodules": submodules,
          "symlinks": symlinks, "trojan": trojan_source, "licences": licences.check, "imports": imports.unused}


def main(argv=None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 1:
        print("usage: hygiene.py OUT_DIR", file=sys.stderr)
        return 2
    repo, out = os.getcwd(), {}
    generated = set()
    try:
        with open(os.path.join(args[0], "meta.json"), encoding="utf-8") as fh:
            generated = set(json.load(fh).get("generated") or [])   # the run's own classification, written before the steps
    except (OSError, ValueError):
        pass
    for key, check in CHECKS.items():
        try:
            out[key] = check(repo, generated) if key == "trojan" else check(repo)
        except (OSError, subprocess.SubprocessError, ValueError) as e:   # one check failing leaves the others standing
            print(f"hygiene.py: {key}: {e}", file=sys.stderr)
            out[key] = None
    with open(os.path.join(args[0], "hygiene.json"), "w", encoding="utf-8") as fh:
        json.dump(out, fh)
    return 0


if __name__ == "__main__":
    sys.exit(main())

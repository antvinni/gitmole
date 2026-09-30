#!/usr/bin/env python3
"""Known vulnerabilities in the dependencies, from osv-scanner over the lock files, offline.

gitmole runs this as the osv-scanner step: `python3 deps.py OUT_JSON`, from inside the repository.
osv-scanner reads every lock file it knows (package-lock.json, yarn.lock, uv.lock, poetry.lock, go.sum,
Cargo.lock, Gemfile.lock and the rest) and matches the packages against a copy of the OSV database on
this machine; with --offline nothing leaves the machine, and the copy is downloaded once by the user, never
by gitmole. Its report repeats every advisory in full; this wrapper keeps one row per vulnerable package
(ids, the CVE aliases, the worst score, the version that fixes it, whether an advisory is a MAL- record) and the lock files with their package
counts, and writes only that. Standalone, like leaks.py.

The same module reads the status back for the report footer.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import re
import subprocess
import sys
import tempfile

try:
    from . import imports, licences, locks
except ImportError:  # run as a script: the package directory is sys.path[0]
    import imports
    import licences
    import locks

ARGV = ["osv-scanner", "scan", "source", "-r", "--offline", "--format", "json", "--all-packages", "."]
NO_SOURCES = 128           # osv-scanner: no lock file found
NO_DATABASE = "no offline version of the OSV database"   # its message when the local copy is missing
DOWNLOAD = "osv-scanner scan source -r --offline-vulnerabilities --download-offline-databases ."
CACHE_DIRS = ("osv-scalibr", "osv-scanner")   # where the local copy lives under the cache directory, by version

_NUMBER = re.compile(r"\d+")


def cache_dir() -> str:
    """The directory osv-scanner keeps its local database in: its own variable, else the platform cache."""
    explicit = os.environ.get("OSV_SCANNER_LOCAL_DB_CACHE_DIRECTORY")
    if explicit:
        return explicit
    if sys.platform == "darwin":
        return os.path.expanduser("~/Library/Caches")
    if sys.platform.startswith("win"):
        return os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    return os.environ.get("XDG_CACHE_HOME") or os.path.expanduser("~/.cache")


def database_date(base: str = None) -> str | None:
    """The day the local database was last refreshed (the newest file under it), in UTC, or None when none."""
    base = cache_dir() if base is None else base
    newest = None
    for name in CACHE_DIRS:
        root = os.path.join(base, name)
        for dirpath, _, files in os.walk(root):
            for f in files:
                try:
                    mtime = os.path.getmtime(os.path.join(dirpath, f))
                except OSError:
                    continue
                newest = mtime if newest is None else max(newest, mtime)
    return dt.datetime.fromtimestamp(newest, dt.timezone.utc).date().isoformat() if newest else None


def database_digest(base: str = None) -> str | None:
    """A digest of the local database snapshot: every file under the cache directories, by path, size
    and modification time. Two runs against the same snapshot agree; a refresh changes it, which is how
    --compare can say a dependency finding moved because the database did. None when there is none."""
    import hashlib
    base = cache_dir() if base is None else base
    entries = []
    for name in CACHE_DIRS:
        root = os.path.join(base, name)
        for dirpath, _, files in os.walk(root):
            for f in files:
                full = os.path.join(dirpath, f)
                try:
                    st = os.stat(full)
                except OSError:
                    continue
                entries.append(f"{os.path.relpath(full, base)}\0{st.st_size}\0{int(st.st_mtime)}")
    if not entries:
        return None
    return hashlib.sha256("\n".join(sorted(entries)).encode("utf-8", "surrogateescape")).hexdigest()[:16]


def _key(version: str) -> tuple:
    return tuple(int(n) for n in _NUMBER.findall(version or ""))


def fixed_version(vulns: list, name: str, version: str) -> str | None:
    """The smallest fixed version above the installed one across the advisories' ranges, else the
    highest named; None when no advisory names a fix."""
    fixes = set()
    for v in vulns:
        for a in v.get("affected") or []:
            if (a.get("package") or {}).get("name", "").lower() != (name or "").lower():
                continue
            for r in a.get("ranges") or []:
                for e in r.get("events") or []:
                    if e.get("fixed"):
                        fixes.add(e["fixed"])
    if not fixes:
        return None
    current = _key(version)
    above = [f for f in fixes if _key(f) > current]
    return min(above, key=_key) if above else max(fixes, key=_key)


def _score(groups: list, vulns: list) -> float | None:
    scores = []
    for g in groups:
        try:
            scores.append(float(g.get("max_severity") or ""))
        except ValueError:
            pass
    if scores:
        return max(scores)
    return None


_WORDS = {"CRITICAL": 9.5, "HIGH": 8.0, "MODERATE": 5.5, "MEDIUM": 5.5, "LOW": 2.0}
MALICIOUS_PREFIX = "MAL-"   # OpenSSF malicious-packages records (ossf/malicious-packages), in the same OSV database; they carry no CVSS


def is_malicious(vulns: list) -> bool:
    """Whether any advisory, by id or alias, is a MAL- record: the package itself is malicious, not merely
    vulnerable, and no score would say so."""
    return any(str(x).startswith(MALICIOUS_PREFIX) for v in vulns for x in [v.get("id", "")] + list(v.get("aliases") or []))


def _label(score, vulns: list) -> str:
    """critical / high / medium / low from the CVSS score, or from the advisory's own word when it has
    no score, else unknown. A malicious package is critical whatever the score."""
    if is_malicious(vulns):
        return "critical"
    if score is None:
        words = [(v.get("database_specific") or {}).get("severity", "").upper() for v in vulns]
        known = [w for w in words if w in _WORDS]
        score = max(_WORDS[w] for w in known) if known else None
    if score is None:
        return "unknown"
    return "critical" if score >= 9 else "high" if score >= 7 else "medium" if score >= 4 else "low"


def _relative(path: str, cwd: str) -> str:
    if os.path.isabs(path):
        try:   # real paths on both sides: osv-scanner may report /tmp/... for a cwd of /private/tmp/...
            rel = os.path.relpath(os.path.realpath(path), os.path.realpath(cwd))
        except ValueError:
            return path
        return path if rel.startswith("..") else rel
    return path[2:] if path.startswith("./") else path


# pip's requirement files: osv-scanner reads them as it reads a lock file (its JSON calls both "lockfile"),
# but a requirement is a specifier, not an installed version, and for `mcp>=1.0.0` it reports the floor, 1.0.0,
# which no install picks on purpose. The file's name is the convention pip and pip-tools use.
REQUIREMENT_FILE = re.compile(r"(^|/)[^/]*(requirements|constraints)[^/]*\.(txt|in)$")
_REQUIREMENT = re.compile(r"^([A-Za-z0-9][A-Za-z0-9._-]*)\s*(?:\[[^\]]*\])?\s*([^;]*)")
_EXACT = re.compile(r"^===?[^,*]+$")   # one `==` or `===` clause without a wildcard: the only specifier that names one version


def is_requirement_file(path: str) -> bool:
    """Whether osv-scanner read this file as a pip requirement file rather than a lock file."""
    return bool(REQUIREMENT_FILE.search(path or ""))


def _normal(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name or "").lower()   # PEP 503


def requirement(text: str, name: str):
    """The specifier a requirement file gives `name` ('>=1.0.0'; '' for the bare name), or None when no line
    names it (an included file, a URL). Comments, options and environment markers are left out."""
    for raw in text.splitlines():
        line = re.split(r"(?:^|\s)#", raw, maxsplit=1)[0].strip()
        if not line or line.startswith("-"):
            continue
        m = _REQUIREMENT.match(line)
        if m and _normal(m.group(1)) == _normal(name):
            return re.sub(r"\s+", "", m.group(2))
    return None


def _pin(row: dict, cwd: str, texts: dict) -> None:
    """On a row from a requirement file, the specifier it was read from and whether that names one version:
    `requirement` and `pinned`, so the report can tell a floor from a pin. Nothing when the line is not found."""
    path = row["source"]
    if path not in texts:
        try:
            with open(os.path.join(cwd, path), encoding="utf-8", errors="replace") as fh:
                texts[path] = fh.read()
        except OSError:
            texts[path] = ""
    spec = requirement(texts[path], row["name"])
    if spec is not None:
        row["requirement"] = spec
        row["pinned"] = bool(_EXACT.match(spec))


def files_phrase(paths) -> str:
    """'3 lock files', or '3 lock files and 1 requirement file': a requirement file is not a lock file."""
    paths = set(paths)
    reqs = sum(1 for p in paths if is_requirement_file(p))
    locks = len(paths) - reqs
    out = [f"{n} {word}{'' if n == 1 else 's'}" for n, word in ((locks, "lock file"), (reqs, "requirement file")) if n]
    return " and ".join(out) or "0 lock files"


def informational(v: dict) -> str | None:
    """The kind of an advisory that reports no vulnerability: RustSec's informational advisories
    (`unmaintained`, `unsound`, `notice`), which OSV carries in affected[].database_specific.informational
    and cargo-audit reports as warnings, not vulnerabilities. None for any other advisory."""
    for a in v.get("affected") or []:
        kind = (a.get("database_specific") or {}).get("informational")
        if isinstance(kind, str) and kind:
            return kind
    return None


def summarise(data: dict, cwd: str) -> dict:
    """One row per vulnerable package; a package whose every advisory is informational (informational())
    goes to `informational` instead: it is a note about the package, not a vulnerability in it."""
    sources, vulnerable, notes, packages, texts = [], [], [], 0, {}
    for r in data.get("results") or []:
        path = _relative((r.get("source") or {}).get("path") or "", cwd)
        pkgs = r.get("packages") or []
        sources.append({"path": path, "packages": len(pkgs)})
        packages += len(pkgs)
        for p in pkgs:
            vulns = p.get("vulnerabilities") or []
            if not vulns:
                continue
            info = p.get("package") or {}
            kinds = [informational(v) for v in vulns]
            if all(kinds):
                notes.append({"name": info.get("name", ""), "version": info.get("version", ""), "ecosystem": info.get("ecosystem", ""),
                              "source": path, "ids": [v.get("id", "") for v in vulns], "kinds": sorted(set(kinds)),
                              "summary": next((v.get("summary") for v in vulns if v.get("summary")), "")})
                continue
            groups = p.get("groups") or []
            score = _score(groups, vulns)
            aliases = sorted({a for v in vulns for a in v.get("aliases") or [] if a.startswith("CVE-")})
            vulnerable.append({"name": info.get("name", ""), "version": info.get("version", ""), "ecosystem": info.get("ecosystem", ""),
                               "source": path, "ids": [v.get("id", "") for v in vulns], "aliases": aliases,
                               "advisories": len(groups) or len(vulns), "score": score, "severity": _label(score, vulns),
                               "summary": next((v.get("summary") for v in vulns if v.get("summary")), ""),
                               "fixed": fixed_version(vulns, info.get("name", ""), info.get("version", "")),
                               "malicious": is_malicious(vulns)})
            if is_requirement_file(path):
                _pin(vulnerable[-1], cwd, texts)
    vulnerable.sort(key=lambda r: (not r["malicious"], -(r["score"] if r["score"] is not None else -1), r["name"], r["source"]))
    notes.sort(key=lambda r: (r["name"], r["version"], r["source"]))
    return {"status": "scanned", "sources": sources, "packages": packages, "vulnerable": vulnerable, **({"informational": notes} if notes else {})}


# --- what the lock says about each vulnerable row ---------------------------------------------------

def lock_context(rows: list, cwd: str) -> None:
    """Set `runtime` on each row from a pnpm-lock.yaml or package-lock.json: true when an install without
    development dependencies puts that version on disk (locks.pnpm_runtime, locks.npm_runtime), false
    when only development dependencies reach it; left out for a lock that does not say. And where the
    lock records which versions the workspaces depend on directly, an `imported` true for a version no
    workspace depends on becomes false: the import loads the version its workspace resolves, not this
    one (esbuild imported at 0.28.2 says nothing about a 0.18.20 a build tool brings)."""
    parsed = {}
    for r in rows:
        src = r.get("source") or ""
        name = src.rsplit("/", 1)[-1]
        if r.get("ecosystem") != "npm" or name not in ("pnpm-lock.yaml", "package-lock.json", "npm-shrinkwrap.json"):
            continue
        if src not in parsed:
            try:   # the whole lock: a large workspace's is well past _file's cap
                with open(os.path.join(cwd, src), encoding="utf-8", errors="replace") as fh:
                    text = fh.read()
            except OSError:
                text = ""
            if name == "pnpm-lock.yaml":
                lock = locks.pnpm(text) if text else None
                parsed[src] = (locks.pnpm_runtime(lock), locks.pnpm_direct(lock)) if lock and lock["importers"] else None
            else:
                lock = locks.npm(text) if text else None
                parsed[src] = (locks.npm_runtime(lock), locks.npm_direct(lock)) if lock else None
        if not parsed[src]:
            continue
        runtime, direct = parsed[src]
        r["runtime"] = (r.get("name"), r.get("version")) in runtime
        if r.get("imported") is True and r.get("name") in direct and r.get("version") not in direct[r["name"]]:
            r["imported"] = False


# --- what a lock's directory declares about how it ships ---------------------------------------------
#
# A lock file pins what gets installed where that lock is used: a service built from its directory
# installs exactly those versions, while a library's lock pins only its own development environment
# (whoever installs the published package resolves its dependencies again). Which one a directory is, it
# declares itself: a container build, a Helm chart, a platform's deploy file, a compose service built from
# it, or an entry point that makes it a program. The collection records what needs a file's contents (the
# entry points, the workspace members, the compose build contexts); the file names are read from the tree
# when the report is drawn, so an older scan still gets those.

DEPLOY_FILE = re.compile(r"^(?:Dockerfile(?:\..+)?|.+\.Dockerfile|Containerfile(?:\..+)?|Chart\.yaml|Procfile|fly\.toml|"
                         r"vercel\.json|netlify\.toml|wrangler\.toml|serverless\.ya?ml)$")
COMPOSE_FILE = re.compile(r"(^|/)(?:docker-)?compose(?:\.[^/]+)?\.ya?ml$")
_TOML_TABLE = re.compile(r"^\s*\[\[?\s*([^\]]+?)\s*\]\]?\s*(?:#.*)?$")
_ENTRY_TABLES = {"project.scripts": "[project.scripts]", "project.gui-scripts": "[project.gui-scripts]",
                 "tool.poetry.scripts": "[tool.poetry.scripts]", "bin": "[[bin]]"}


def _file(cwd: str, path: str) -> str:
    try:
        with open(os.path.join(cwd, path), encoding="utf-8", errors="replace") as fh:
            return fh.read(2_000_000)
    except OSError:
        return ""


def _toml_tables(text: str) -> dict:
    """{table: its lines} for a TOML file, enough to see which tables exist and read a string array."""
    out, table = {"": []}, ""
    for line in text.splitlines():
        m = _TOML_TABLE.match(line)
        if m:
            table = re.sub(r"\s*\.\s*", ".", m.group(1)).replace('"', "")
            out.setdefault(table, [])
            continue
        out[table].append(line)
    return out


def _toml_array(lines: list, key: str) -> list:
    text = "\n".join(lines)
    m = re.search(rf"(?m)^\s*{re.escape(key)}\s*=\s*\[(.*?)\]", text, re.S)
    return re.findall(r"[\"']([^\"']+)[\"']", m.group(1)) if m else []


def _join(d: str, name: str) -> str:
    return f"{d}/{name}" if d else name


_NPM_LOCKS = ("package-lock.json", "npm-shrinkwrap.json", "yarn.lock", "bun.lock", "bun.lockb")


def _members(cwd: str, lock_dir: str, lock: str) -> list:
    """The workspace members a lock at `lock_dir` pins, from the manifest its own tool reads: uv.lock from
    uv's [tool.uv.workspace], Cargo.lock from Cargo's [workspace], npm, Yarn and Bun locks from
    package.json `workspaces`, pnpm-lock.yaml from pnpm-workspace.yaml."""
    import glob
    patterns, drop = [], []
    if lock == "uv.lock":
        py = _toml_tables(_file(cwd, _join(lock_dir, "pyproject.toml")))
        patterns += _toml_array(py.get("tool.uv.workspace", []), "members")
        drop += _toml_array(py.get("tool.uv.workspace", []), "exclude")
    if lock == "Cargo.lock":
        cargo = _toml_tables(_file(cwd, _join(lock_dir, "Cargo.toml")))
        patterns += _toml_array(cargo.get("workspace", []), "members")
        drop += _toml_array(cargo.get("workspace", []), "exclude")
    if lock in _NPM_LOCKS:
        try:
            declared = json.loads(_file(cwd, _join(lock_dir, "package.json")) or "{}").get("workspaces")
        except (ValueError, AttributeError):
            declared = None
        declared = declared.get("packages") if isinstance(declared, dict) else declared
        for p in declared if isinstance(declared, list) else []:
            if isinstance(p, str):
                (drop if p.startswith("!") else patterns).append(p.lstrip("!"))
    in_packages = False
    for line in (_file(cwd, _join(lock_dir, "pnpm-workspace.yaml")) if lock == "pnpm-lock.yaml" else "").splitlines():
        if re.match(r"^packages\s*:", line):
            in_packages = True
            continue
        if in_packages:
            m = re.match(r"^\s*-\s*[\"']?([^\"'#]+?)[\"']?\s*(?:#.*)?$", line)
            if m:
                (drop if m.group(1).startswith("!") else patterns).append(m.group(1).lstrip("!"))
            elif line.strip() and not line.startswith((" ", "\t")):
                in_packages = False
    base = os.path.join(cwd, lock_dir)

    def expand(ps):
        found = set()
        for p in ps:
            for hit in glob.glob(os.path.join(base, p.strip().rstrip("/"))):
                if os.path.isdir(hit):
                    rel = os.path.relpath(hit, cwd)
                    if not rel.startswith(".."):
                        found.add(rel.replace(os.sep, "/"))
        return found
    return sorted(expand(patterns) - expand(drop) - {lock_dir or "."})


def _entry_points(cwd: str, d: str) -> list:
    """What makes the directory a program by its manifests: [project.scripts] and the like in
    pyproject.toml, `bin` in package.json, [[bin]] in Cargo.toml."""
    out = []
    for name in ("pyproject.toml", "Cargo.toml"):
        tables = _toml_tables(_file(cwd, _join(d, name)))
        for t, label in _ENTRY_TABLES.items():
            if t in tables and (name == "Cargo.toml") == (t == "bin"):
                out.append(f"{_join(d, name)} {label}")
        if name == "pyproject.toml" and any(re.match(r"^\s*(?:gui-)?scripts\s*=", line) for line in tables.get("project", [])):
            out.append(f"{_join(d, name)} [project.scripts]")
    try:
        doc = json.loads(_file(cwd, _join(d, "package.json")) or "{}")
    except ValueError:
        doc = {}
    if isinstance(doc, dict) and doc.get("bin"):
        out.append(f"{_join(d, 'package.json')} bin")
    return sorted(set(out))


def compose_builds(text: str, compose_dir: str) -> list:
    """The directories a compose file's services build from: `build: path`, or `context:` under
    `build:` (the compose file's own directory when it names none), relative to the repository."""
    out, lines = [], text.splitlines()
    for i, line in enumerate(lines):
        m = re.match(r"^(\s*)build\s*:\s*(.*?)\s*(?:#.*)?$", line)
        if not m:
            continue
        indent, value = len(m.group(1)), m.group(2).strip("\"'")
        if not value:
            value = "."
            for nxt in lines[i + 1:]:
                if nxt.strip() and len(nxt) - len(nxt.lstrip()) <= indent:
                    break
                c = re.match(r"^\s*context\s*:\s*[\"']?([^\"'#]+?)[\"']?\s*(?:#.*)?$", nxt)
                if c:
                    value = c.group(1)
                    break
        if value.startswith("{") or "://" in value or value.startswith("git@") or "$" in value:
            continue
        rel = os.path.normpath(os.path.join(compose_dir, value)).replace(os.sep, "/")
        if not rel.startswith(".."):
            out.append("" if rel == "." else rel)
    return out


def declare(result: dict, cwd: str) -> None:
    """Add to each lock file's source row what needs its directory's files read: the workspace `members` it
    pins and the `entry_points` of it and its members; and to the result the `compose_builds`."""
    for src in result.get("sources") or []:
        d = os.path.dirname(src["path"])
        members = _members(cwd, d, os.path.basename(src["path"]))
        entries = [e for m in [d] + members for e in _entry_points(cwd, m)]
        if members:
            src["members"] = members
        if entries:
            src["entry_points"] = entries
    listed = subprocess.run(["git", "ls-files", "-z"], cwd=cwd, stdin=subprocess.DEVNULL, capture_output=True)
    builds = set()
    for path in listed.stdout.decode("utf-8", "replace").split("\0"):
        if path and COMPOSE_FILE.search(path) and "node_modules/" not in path:
            builds.update(compose_builds(_file(cwd, path), os.path.dirname(path)))
    result["compose_builds"] = sorted(builds)


def deploys(source: dict, tree, builds=()) -> list:
    """What declares that this lock ships: a deploy file (DEPLOY_FILE) in its directory or a workspace
    member's, a compose service built from one of them, an entry point; for Cargo and Go also the
    ecosystem's own program layout (src/main.rs or src/bin/, main.go or cmd/). [] when nothing does:
    a library, or a workspace kept for development and integration."""
    path = source.get("path") or ""
    dirs = [os.path.dirname(path)] + list(source.get("members") or [])
    lock = os.path.basename(path)
    out = list(source.get("entry_points") or [])
    wanted = set(dirs)
    for p in tree or ():
        d, _, name = p.rpartition("/")
        if d in wanted and DEPLOY_FILE.match(name):
            out.append(p)
        elif lock == "Cargo.lock" and any(p == _join(x, "src/main.rs") or p.startswith(_join(x, "src/bin/")) for x in dirs):
            out.append(p)
        elif lock in ("go.mod", "go.sum") and any(p == _join(x, "main.go") or p.startswith(_join(x, "cmd/")) for x in dirs):
            out.append(p)
    out += [f"a compose service built from {x or 'the root'}" for x in dirs if x in set(builds)]
    return sorted(set(out))


PACKAGES = "packages.json"   # every locked package, for --sbom; not part of the report, which keeps the vulnerable ones


def packages(data: dict, cwd: str) -> list:
    """Every package the lock files pin, once per ecosystem, name and version, with the lock files that
    pin it and the licence a lock file declares for it (package-lock.json, composer.lock), sorted."""
    declared = {}
    try:
        for d in licences.lock_licences(cwd, [_relative(p, cwd) for p in _lock_paths(data)], every=True):
            declared.setdefault((d["ecosystem"], d["name"], d["version"]), d["expression"])
    except OSError:
        pass
    by_key = {}
    for r in data.get("results") or []:
        path = _relative((r.get("source") or {}).get("path") or "", cwd)
        for p in r.get("packages") or []:
            info = p.get("package") or {}
            key = (info.get("ecosystem", ""), info.get("name", ""), info.get("version", ""))
            row = by_key.setdefault(key, {"ecosystem": key[0], "name": key[1], "version": key[2], "sources": []})
            if path not in row["sources"]:
                row["sources"].append(path)
    out = []
    for key in sorted(by_key):
        row = by_key[key]
        row["sources"].sort()
        if key in declared:
            row["license"] = declared[key]
        out.append(row)
    return out


def _lock_paths(data: dict) -> list:
    return [(r.get("source") or {}).get("path") or "" for r in data.get("results") or []]


# The same scan with the vulnerability matcher switched off: it reads every lock file and matches nothing,
# so it needs no database. The flag is osv-scanner's experimental plugin switch (2.x); when it fails, there
# is no package list and --sbom says so.
LIST_ARGV = ARGV[:-1] + ["--experimental-disable-plugins", "vulnmatch/osvlocal", "."]


def list_packages():
    proc = subprocess.run(LIST_ARGV, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if proc.returncode not in (0, 1):
        print(f"deps.py: listing the packages without the database: osv-scanner exited {proc.returncode}", file=sys.stderr)
        return None
    try:
        data = json.loads(proc.stdout.decode("utf-8", "replace") or "{}")
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def write_packages(rows: list, target: str) -> None:
    with open(target, "w", encoding="utf-8") as fh:
        json.dump({"packages": rows}, fh, indent=0, sort_keys=True)


def write(result: dict, target: str) -> None:
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(os.path.abspath(target)), prefix=".dependencies-", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(result, fh, indent=1)
        os.replace(tmp, target)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


def main(argv=None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 1:
        print("usage: deps.py OUT_JSON", file=sys.stderr)
        return 2
    target = args[0]
    proc = subprocess.run(ARGV, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    err = proc.stderr.decode("utf-8", "replace")
    sys.stderr.write(err)   # osv-scanner's own log lands in run.log
    if proc.returncode == NO_SOURCES:
        result = {"status": "no-sources"}
    elif NO_DATABASE in err:
        result = {"status": "no-database", "download": DOWNLOAD}
        listed = list_packages()   # the package list for --sbom needs no database
        if listed is not None:
            write_packages(packages(listed, os.getcwd()), os.path.join(os.path.dirname(os.path.abspath(target)), PACKAGES))
    elif proc.returncode in (0, 1):   # 1: packages with vulnerabilities were found
        text = proc.stdout.decode("utf-8", "replace").strip()
        try:
            data = json.loads(text) if text else {}
        except json.JSONDecodeError:
            print("deps.py: osv-scanner printed no JSON report; nothing written", file=sys.stderr)
            return 1
        result = summarise(data, os.getcwd())
        try:
            declare(result, os.getcwd())
        except OSError as e:   # the rows stand without it; the report then reads only the tree
            print(f"deps.py: declarations: {e}", file=sys.stderr)
        result["database_date"] = database_date()
        result["database_digest"] = database_digest()
        try:
            imports.annotate(result["vulnerable"], os.getcwd())
        except OSError as e:   # the rows stand without it
            print(f"deps.py: imports: {e}", file=sys.stderr)
        lock_context(result["vulnerable"], os.getcwd())
        write_packages(packages(data, os.getcwd()), os.path.join(os.path.dirname(os.path.abspath(target)), PACKAGES))
    else:
        print(f"deps.py: osv-scanner exited {proc.returncode}; no report written", file=sys.stderr)
        return proc.returncode
    write(result, target)
    return 0


if __name__ == "__main__":
    sys.exit(main())

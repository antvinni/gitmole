#!/usr/bin/env python3
"""Known vulnerabilities in the dependencies, from osv-scanner over the lock files, offline.

gitmole runs this as the osv-scanner step: `python3 deps.py OUT_JSON`, from inside the repository.
osv-scanner reads every lock file it knows (package-lock.json, yarn.lock, uv.lock, poetry.lock, go.sum,
Cargo.lock, Gemfile.lock and the rest) and matches the packages against a copy of the OSV database on
this machine; with --offline nothing leaves the machine, and the copy is downloaded once by the user, never
by gitmole. Its report repeats every advisory in full; this wrapper keeps one row per vulnerable package
(ids, the CVE aliases, the worst score, the version that fixes it, whether an advisory is a MAL- record) and the lock files with their package
counts, and writes only that. Standalone, like leaks.py and duplicates.py.

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
    """The day the local database was last refreshed (the newest file under it), or None when none."""
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
    return dt.datetime.fromtimestamp(newest).date().isoformat() if newest else None


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
MALICIOUS_PREFIX = "MAL-"   # OpenSSF malicious-packages records, in the same OSV database; they carry no CVSS


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
        try:
            rel = os.path.relpath(path, cwd)
        except ValueError:
            return path
        return path if rel.startswith("..") else rel
    return path[2:] if path.startswith("./") else path


def summarise(data: dict, cwd: str) -> dict:
    sources, vulnerable, packages = [], [], 0
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
            groups = p.get("groups") or []
            score = _score(groups, vulns)
            aliases = sorted({a for v in vulns for a in v.get("aliases") or [] if a.startswith("CVE-")})
            vulnerable.append({"name": info.get("name", ""), "version": info.get("version", ""), "ecosystem": info.get("ecosystem", ""),
                               "source": path, "ids": [v.get("id", "") for v in vulns], "aliases": aliases,
                               "advisories": len(groups) or len(vulns), "score": score, "severity": _label(score, vulns),
                               "summary": next((v.get("summary") for v in vulns if v.get("summary")), ""),
                               "fixed": fixed_version(vulns, info.get("name", ""), info.get("version", "")),
                               "malicious": is_malicious(vulns)})
    vulnerable.sort(key=lambda r: (not r["malicious"], -(r["score"] if r["score"] is not None else -1), r["name"], r["source"]))
    return {"status": "scanned", "sources": sources, "packages": packages, "vulnerable": vulnerable}


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
    elif proc.returncode in (0, 1):   # 1: packages with vulnerabilities were found
        text = proc.stdout.decode("utf-8", "replace").strip()
        try:
            data = json.loads(text) if text else {}
        except json.JSONDecodeError:
            print("deps.py: osv-scanner printed no JSON report; nothing written", file=sys.stderr)
            return 1
        result = summarise(data, os.getcwd())
        result["database_date"] = database_date()
    else:
        print(f"deps.py: osv-scanner exited {proc.returncode}; no report written", file=sys.stderr)
        return proc.returncode
    write(result, target)
    return 0


if __name__ == "__main__":
    sys.exit(main())

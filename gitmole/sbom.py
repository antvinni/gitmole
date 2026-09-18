"""A CycloneDX 1.6 SBOM from the lock files, for `--sbom`.

The packages are the ones the osv-scanner step read from every lock file in the tree (packages.json in
the output directory): one component per ecosystem, name and version, with a package URL, the lock files
that pin it as properties, and the licence a lock file declares for it where one does (package-lock.json,
composer.lock). The metadata names the repository, its commit and its declared licence. There is no
dependency graph: the lock files osv-scanner reads do not all record one, and a partial graph would
read as a complete one.

Deterministic like `--json`: the timestamp is the last commit's day, and the serial number is a UUID derived from
the commit and the components, so the same commit gives the same bytes."""
from __future__ import annotations

import json
import os
import uuid
from urllib.parse import quote

from . import __version__

SPEC = "1.6"
PURL_TYPES = {"npm": "npm", "PyPI": "pypi", "Go": "golang", "crates.io": "cargo", "RubyGems": "gem", "Maven": "maven", "NuGet": "nuget",
              "Packagist": "composer", "Pub": "pub", "Hex": "hex", "Hackage": "hackage", "CRAN": "cran", "ConanCenter": "conan",
              "SwiftURL": "swift", "GitHub Actions": "github", "Bioconductor": "bioconductor", "CocoaPods": "cocoapods"}
NAMESPACE = uuid.UUID("5d0f1a3e-9c8b-4f63-9a51-8f0b6c1e2d47")   # gitmole's own, for uuid5


def _seg(s: str) -> str:
    return quote(s, safe="")


def purl(ecosystem: str, name: str, version: str) -> str | None:
    """The package URL of one package, or None for an ecosystem purl has no type for."""
    t = PURL_TYPES.get(ecosystem)
    if not t or not name:
        return None
    if t == "maven" and ":" in name:
        group, artifact = name.split(":", 1)
        path = f"{_seg(group)}/{_seg(artifact)}"
    elif t == "pypi":
        path = _seg(name.lower().replace("_", "-"))
    elif t in ("npm", "golang", "composer", "github", "swift") and "/" in name:
        path = "/".join(_seg(p) for p in name.split("/"))
    else:
        path = _seg(name)
    if t == "golang" and version and version[0].isdigit():
        version = "v" + version
    return f"pkg:{t}/{path}" + (f"@{_seg(version)}" if version else "")


def read_packages(out_dir: str):
    """The package list the dependency step wrote, or None when it wrote none."""
    try:
        with open(os.path.join(out_dir, "packages.json"), encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return None
    return data.get("packages") if isinstance(data, dict) and isinstance(data.get("packages"), list) else None


def _licences(expression: str) -> list:
    return [{"expression": expression}] if expression else []


def build(report: dict, packages: list) -> dict:
    meta = report.get("meta") or {}
    run = meta.get("run") or {}
    commit = run.get("commit") or ""
    components = []
    for p in packages:
        ref = purl(p.get("ecosystem", ""), p.get("name", ""), p.get("version", ""))
        c = {"type": "library", "bom-ref": ref or f"{p.get('ecosystem')}:{p.get('name')}@{p.get('version')}", "name": p.get("name", "")}
        if p.get("version"):
            c["version"] = p["version"]
        if ref:
            c["purl"] = ref
        if p.get("license"):
            c["licenses"] = _licences(p["license"])
        c["properties"] = [{"name": "gitmole:ecosystem", "value": p.get("ecosystem", "")}] + [{"name": "gitmole:lockfile", "value": s} for s in p.get("sources") or []]
        components.append(c)
    lic = (report.get("hygiene") or {}).get("licences") or {}
    own = sorted({d["expression"] for d in lic.get("declared") or []} | ({lic["file_licence"]} if lic.get("file_licence") else set()))
    root = {"type": "application", "bom-ref": "root", "name": meta.get("name") or "repository"}
    if commit:
        root["version"] = commit
    if len(own) == 1:
        root["licenses"] = _licences(own[0])
    body = json.dumps(components, sort_keys=True)
    serial = uuid.uuid5(NAMESPACE, f"{commit}\0{body}")
    metadata = {"tools": {"components": [{"type": "application", "name": "gitmole", "version": run.get("gitmole") or __version__}]}, "component": root}
    if meta.get("last_date"):   # the last commit's day, so the same commit gives the same timestamp
        metadata["timestamp"] = f"{meta['last_date']}T00:00:00Z"
    return {"bomFormat": "CycloneDX", "specVersion": SPEC, "serialNumber": f"urn:uuid:{serial}", "version": 1,
            "metadata": metadata, "components": components}


def dumps(report: dict, packages: list) -> str:
    return json.dumps(build(report, packages), indent=2, sort_keys=True, ensure_ascii=False) + "\n"

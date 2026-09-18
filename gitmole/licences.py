"""Licences as they are declared, not detected: the project's own (its root manifests and its licence
file) and its dependencies' (the `license` fields a lock file records). No full-text detection of
arbitrary files; the licence file is matched against the opening words of a small set of licence texts,
and a text it does not match is reported as unrecognised, never guessed.

Where the declared licences live: `license` in package.json and composer.json, PEP 639
`license = "…"` (or the older table form) in pyproject.toml, `license` in Cargo.toml's `[package]`,
`license`/`licenses` in a gemspec, and `license =` in setup.cfg; for dependencies, package-lock.json
(npm 7 and later record each package's licence) and composer.lock. Cargo.lock, Gemfile.lock,
yarn.lock, uv.lock and poetry.lock record none, so their packages are not read.

Expressions are SPDX: `AND`, `OR`, `WITH` and parentheses, evaluated here rather than with a library.
`OR` is the licensee's choice (the least restrictive branch counts), `AND` is every term (the most
restrictive counts). A GPL with a linking exception counts as weak copyleft."""
from __future__ import annotations

import json
import os
import re

try:
    from . import filetypes
except ImportError:  # run inside a script: the package directory is sys.path[0]
    import filetypes

CAP = 50

PERMISSIVE, WEAK, STRONG = "permissive", "weak copyleft", "strong copyleft"
RANK = {PERMISSIVE: 0, WEAK: 1, STRONG: 2}
_PERMISSIVE = {"MIT", "MIT-0", "ISC", "0BSD", "APACHE-2.0", "APACHE-1.1", "UNLICENSE", "BSL-1.0", "CC0-1.0", "ZLIB", "PYTHON-2.0",
               "PSF-2.0", "BLUEOAK-1.0.0", "CC-BY-3.0", "CC-BY-4.0", "CURL", "X11", "WTFPL", "ARTISTIC-2.0", "NCSA", "UPL-1.0",
               "POSTGRESQL", "OPENSSL", "PHP-3.01", "RUBY", "UNICODE-3.0", "UNICODE-DFS-2016", "BSD-2-CLAUSE", "BSD-3-CLAUSE", "MPL-2.0-NO-COPYLEFT-EXCEPTION"}
_WEAK = ("LGPL-", "MPL-", "EPL-", "CDDL-", "CPL-", "MS-RL", "CC-BY-SA-")
_STRONG = ("GPL-", "AGPL-", "SSPL-", "EUPL-", "OSL-")
# OSI- or FSF-approved, for OSPS-LE-02.01: these ids and the copyleft families by prefix; the ones below
# are known not to be, and anything else is unrecognised rather than a gap
_APPROVED = {"MIT", "MIT-0", "ISC", "0BSD", "APACHE-2.0", "APACHE-1.1", "UNLICENSE", "BSL-1.0", "CC0-1.0", "ZLIB", "PYTHON-2.0",
             "BLUEOAK-1.0.0", "X11", "ARTISTIC-2.0", "NCSA", "UPL-1.0", "POSTGRESQL", "PHP-3.01", "RUBY", "UNICODE-3.0",
             "BSD-2-CLAUSE", "BSD-3-CLAUSE"}
_APPROVED_PREFIX = ("LGPL-", "GPL-", "AGPL-", "MPL-", "EPL-", "CDDL-", "EUPL-", "OSL-", "CPL-")
_NOT_APPROVED = {"SSPL-1.0", "CC-BY-3.0", "CC-BY-4.0", "CC-BY-NC-4.0", "BUSL-1.1", "ELASTIC-2.0", "COMMONS-CLAUSE"}


def _norm(token: str) -> str:
    t = token.strip().upper().rstrip("+")
    for suffix in ("-ONLY", "-OR-LATER"):
        if t.endswith(suffix):
            t = t[: -len(suffix)]
    return t


def family(licence_id: str) -> str | None:
    """permissive, weak copyleft, strong copyleft, or None for an id not in the set."""
    t = _norm(licence_id)
    if t in _PERMISSIVE or t.startswith("BSD-"):
        return PERMISSIVE
    if t.startswith(_WEAK):
        return WEAK
    if t.startswith(_STRONG):
        return STRONG
    return None


def approved(licence_id: str):
    """True for an OSI- or FSF-approved id, False for one known not to be, None when not in either set."""
    t = _norm(licence_id)
    if t in _APPROVED or t.startswith(_APPROVED_PREFIX):
        return True
    return False if t in _NOT_APPROVED else None


_TOKEN = re.compile(r"\(|\)|[^\s()]+")


def _tokens(expr: str) -> list:
    expr = expr.strip()
    if expr.startswith("(") is False and "/" in expr and " " not in expr:   # "MIT/X11", an npm-era choice
        expr = " OR ".join(expr.split("/"))
    return _TOKEN.findall(expr)


def ids(expr: str) -> list:
    """The licence ids an expression names, exceptions left out."""
    out, skip = [], False
    for t in _tokens(expr or ""):
        if skip:
            skip = False
            continue
        if t.upper() == "WITH":
            skip = True
            continue
        if t in ("(", ")") or t.upper() in ("AND", "OR"):
            continue
        out.append(t)
    return out


def classify(expr: str):
    """The family an SPDX expression puts on its user: OR takes the least restrictive branch, AND the
    most restrictive term, `GPL WITH exception` is weak. None when no term is a known id."""
    tokens = _tokens(expr or "")
    pos = 0

    def atom():
        nonlocal pos
        if pos >= len(tokens):
            return None
        t = tokens[pos]
        pos += 1
        if t == "(":
            v = or_expr()
            if pos < len(tokens) and tokens[pos] == ")":
                pos += 1
            return v
        v = family(t)
        if pos < len(tokens) and tokens[pos].upper() == "WITH":
            pos += 2
            if v == STRONG:
                v = WEAK
        return v

    def combine(values, pick):
        known = [v for v in values if v is not None]
        return pick(known, key=RANK.get) if known else None

    def and_expr():
        nonlocal pos
        vals = [atom()]
        while pos < len(tokens) and tokens[pos].upper() == "AND":
            pos += 1
            vals.append(atom())
        return combine(vals, max) if len(vals) > 1 else vals[0]

    def or_expr():
        nonlocal pos
        vals = [and_expr()]
        while pos < len(tokens) and tokens[pos].upper() == "OR":
            pos += 1
            vals.append(and_expr())
        if len(vals) == 1:
            return vals[0]
        if PERMISSIVE in vals:
            return PERMISSIVE
        return None if None in vals else combine(vals, min)   # an unknown branch may be the one the user takes
    return or_expr() if tokens else None


# --- the project's own licence ------------------------------------------------------------------

# The opening words that name each licence text, checked in this order (the GNU titles are upper case in
# the texts themselves, and the GPL mentions the Lesser GPL in its closing paragraph)
TEXTS = [("AGPL-3.0", ["GNU AFFERO GENERAL PUBLIC LICENSE"]), ("LGPL-3.0", ["GNU LESSER GENERAL PUBLIC LICENSE", "Version 3"]),
         ("LGPL-2.1", ["GNU LESSER GENERAL PUBLIC LICENSE", "Version 2.1"]), ("LGPL-2.0", ["GNU LIBRARY GENERAL PUBLIC LICENSE"]),
         ("GPL-3.0", ["GNU GENERAL PUBLIC LICENSE", "Version 3"]), ("GPL-2.0", ["GNU GENERAL PUBLIC LICENSE", "Version 2"]),
         ("MPL-2.0", ["Mozilla Public License", "2.0"]), ("EPL-2.0", ["Eclipse Public License - v 2.0"]),
         ("Apache-2.0", ["Apache License", "Version 2.0"]), ("BSL-1.0", ["Boost Software License - Version 1.0"]),
         ("Unlicense", ["This is free and unencumbered software released into the public domain"]),
         ("CC0-1.0", ["CC0 1.0 Universal"]),
         ("MIT", ["Permission is hereby granted, free of charge, to any person obtaining a copy", "The above copyright notice and this permission notice shall be included"]),
         ("MIT-0", ["Permission is hereby granted, free of charge, to any person obtaining a copy"]),
         ("ISC", ["Permission to use, copy, modify, and/or distribute this software for any purpose with or without fee is hereby granted, provided that"]),
         ("0BSD", ["Permission to use, copy, modify, and/or distribute this software for any purpose with or without fee is hereby granted"]),
         ("BSD-3-Clause", ["Redistribution and use in source and binary forms", "Neither the name"]),
         ("BSD-3-Clause", ["Redistribution and use in source and binary forms", "names of its contributors may"]),
         ("BSD-2-Clause", ["Redistribution and use in source and binary forms"]),
         ("curl", ["COPYRIGHT AND PERMISSION NOTICE", "Permission to use, copy, modify, and distribute this software for any purpose with or without fee is hereby granted"]),
         ("Zlib", ["This software is provided 'as-is', without any express or implied warranty", "must not be misrepresented"])]


def identify(text: str) -> str | None:
    """The licence a licence file's text is, from TEXTS, or None when it matches none."""
    flat = " ".join(re.sub(r"[*#>_`]", " ", text).split())
    for licence_id, phrases in TEXTS:
        if all(p in flat for p in phrases):
            return licence_id
    return None


def _read(repo: str, path: str, limit: int = 2_000_000) -> str:
    try:
        with open(os.path.join(repo, path), "rb") as fh:
            return fh.read(limit).decode("utf-8", "replace")
    except OSError:
        return ""


def _toml_value(text: str, table: str, key: str):
    """A string (or the text of an inline table) under [table] in a TOML file, without a parser: the
    Python gitmole supports may predate tomllib."""
    current = ""
    for line in text.split("\n"):
        h = re.match(r"^\s*\[\s*([^\]]+?)\s*\]\s*(?:#.*)?$", line)
        if h:
            current = h.group(1)
            continue
        if current != table:
            continue
        m = re.match(rf"""^\s*{re.escape(key)}\s*=\s*(?:"([^"]*)"|'([^']*)'|(\{{.*\}}))""", line)
        if m:
            return m.group(1) if m.group(1) is not None else m.group(2) if m.group(2) is not None else m.group(3)
    return None


def declared(repo: str, paths: list) -> list:
    """[{source, expression}] the root manifests declare."""
    out = []
    root = {p for p in paths if "/" not in p}
    for name in ("package.json", "composer.json"):
        if name in root:
            try:
                data = json.loads(_read(repo, name))
            except ValueError:
                data = {}
            lic = data.get("license") if isinstance(data, dict) else None
            if isinstance(lic, list):
                lic = " OR ".join(str(x) for x in lic)
            if isinstance(lic, dict):
                lic = lic.get("type")
            if isinstance(lic, str) and lic.strip() and lic.upper() not in ("UNLICENSED", "SEE LICENSE IN LICENSE"):
                out.append({"source": name, "expression": lic.strip()})
    if "pyproject.toml" in root:
        v = _toml_value(_read(repo, "pyproject.toml"), "project", "license")
        if v and v.startswith("{"):   # the pre-PEP 639 table: its text counts when it is an id
            m = re.search(r"""text\s*=\s*["']([^"']+)["']""", v)
            v = m.group(1).strip() if m and family(m.group(1).strip()) else None
        if v:
            out.append({"source": "pyproject.toml", "expression": v})
    if "Cargo.toml" in root:
        v = _toml_value(_read(repo, "Cargo.toml"), "package", "license")
        if v and not v.startswith("{"):
            out.append({"source": "Cargo.toml", "expression": v})
    if "setup.cfg" in root:
        m = re.search(r"^license\s*=\s*([A-Za-z0-9.+ ()-]+?)\s*$", _read(repo, "setup.cfg"), re.M)
        if m and family(m.group(1).split()[0]):
            out.append({"source": "setup.cfg", "expression": m.group(1)})
    for p in sorted(root):
        if p.endswith(".gemspec"):
            m = re.search(r"""\.licen[cs]es?\s*=\s*\[?\s*['"]([^'"]+)['"]""", _read(repo, p))
            if m:
                out.append({"source": p, "expression": m.group(1)})
    return out


def licence_files(paths: list) -> list:
    return sorted(p for p in paths if "/" not in p and re.match(r"^(licen[cs]e|copying)(\.|-|$)", p, re.I))


# --- the dependencies' licences -----------------------------------------------------------------

def _aside(path: str) -> bool:
    return ("node_modules/" in path or filetypes.is_test_path(path) or filetypes.is_sample_path(path)
            or filetypes.is_vendor_path(path) or filetypes.is_doc_path(path))


def lock_licences(repo: str, paths: list, every: bool = False) -> list:
    """[{lockfile, ecosystem, name, version, expression}] for every runtime package a package-lock.json
    or composer.lock declares a licence for; development-only packages are left out, and so are lock
    files under tests, examples, documentation and vendored code unless `every` (the SBOM lists them)."""
    out = []
    for p in sorted(paths):
        base = os.path.basename(p)
        if base not in ("package-lock.json", "npm-shrinkwrap.json", "composer.lock") or (_aside(p) and not every):
            continue
        try:
            data = json.loads(_read(repo, p, 200_000_000))
        except ValueError:
            continue
        if not isinstance(data, dict):
            continue
        if base == "composer.lock":
            for pkg in data.get("packages") or []:
                lic = pkg.get("license")
                if isinstance(lic, list) and lic:
                    out.append({"lockfile": p, "ecosystem": "Packagist", "name": pkg.get("name", ""), "version": str(pkg.get("version", "")),
                                "expression": " OR ".join(str(x) for x in lic)})
            continue
        for key, pkg in sorted((data.get("packages") or {}).items()):
            if not key or not isinstance(pkg, dict) or pkg.get("dev") or pkg.get("devOptional") or pkg.get("link"):
                continue
            lic = pkg.get("license")
            if isinstance(lic, dict):
                lic = lic.get("type")
            if not isinstance(lic, str) or not lic.strip():
                continue
            name = pkg.get("name") or key.rsplit("node_modules/", 1)[-1]
            out.append({"lockfile": p, "ecosystem": "npm", "name": name, "version": str(pkg.get("version", "")), "expression": lic.strip()})
    return out


def _approved_all(all_ids: list):
    """True when every declared id is approved, False when one is known not to be, None otherwise (or with none)."""
    verdicts = [approved(i) for i in all_ids]
    if not verdicts or None in verdicts and False not in verdicts:
        return None
    return all(verdicts)


def check(repo: str, paths: list = None) -> dict:
    """What hygiene.json keeps: the project's declared licences and licence file, whether they agree,
    and the runtime dependencies whose declared licence is copyleft (strong, and weak by count)."""
    paths = filetypes.git_paths(repo, "ls-files") if paths is None else paths
    decl = declared(repo, paths)
    files = licence_files(paths)
    text_id = None
    for f in files:
        text_id = identify(_read(repo, f))
        if text_id:
            break
    declared_ids = sorted({i for d in decl for i in ids(d["expression"])})
    project_exprs = [d["expression"] for d in decl] + ([text_id] if text_id else [])
    families = [classify(e) for e in project_exprs]
    project = max((f for f in families if f), key=RANK.get, default=None)
    mismatch = bool(text_id and declared_ids and _norm(text_id) not in {_norm(i) for i in declared_ids})
    deps = lock_licences(repo, paths)
    strong, weak, seen = [], 0, set()
    for d in deps:
        key = (d["ecosystem"], d["name"], d["version"])
        if key in seen:
            continue
        seen.add(key)
        fam = classify(d["expression"])
        if fam == STRONG:
            strong.append(d)
        elif fam == WEAK:
            weak += 1
    all_ids = declared_ids + ([text_id] if text_id else [])
    return {"declared": decl, "files": files, "file_licence": text_id, "project": project,
            "approved": _approved_all(all_ids), "unrecognised": sorted({i for i in all_ids if approved(i) is None}),
            "mismatch": mismatch, "dependencies": len(seen), "strong": strong[:CAP], "strong_count": len(strong), "weak_count": weak}

"""What an npm-family lock file declares about the packages it pins, read without a YAML library: which
workspace (importer) declares which package directly, which packages only its development dependencies
reach, and which packages the lock resolved as another package's peer.

pnpm-lock.yaml (lockfile versions 6 and 9) names every workspace under `importers`, each with its
`dependencies`, `optionalDependencies` and `devDependencies` and the version each resolved to; a resolved
version carries the peers it was resolved with as a suffix (`2.1.0(nice-grpc@2.1.17)`). The packages'
own dependencies are under `snapshots` (9) or `packages` (6), keyed by that same `name@version(suffix)`.
package-lock.json (v2, v3) keys its `packages` by install path and marks the ones only development
dependencies reach `dev` or `devOptional`, and records each package's `peerDependencies`. A Yarn 2+
yarn.lock records `peerDependencies` per entry; a Yarn 1 lock records no peers and no dev marks.

Everything here is what the lock itself says; nothing is resolved again."""
from __future__ import annotations

import collections
import json
import re

_KEY = re.compile(r"^(\s*)(?:'([^']*)'|\"([^\"]*)\"|([^:\s][^:]*?)):(?:\s+(.*?))?\s*$")
_SUFFIX_PEER = re.compile(r"\(((?:@[^@()/]+/)?[^@()]+)@")


def _unquote(value: str) -> str:
    value = (value or "").strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
        return value[1:-1]
    return value


def _lines(text: str):
    """(indent, key, value) for every `key: value` line of a block-style YAML document, skipping comments,
    list items and blank lines."""
    for raw in text.split("\n"):
        if not raw.strip() or raw.lstrip().startswith(("#", "- ")):
            continue
        m = _KEY.match(raw)
        if m:
            yield len(m.group(1)), m.group(2) or m.group(3) or m.group(4), _unquote(m.group(5) or "")


def split_key(key: str) -> tuple:
    """(name, version without the peer suffix) of a pnpm package key: `/name@1.0.0` (6), `name@1.0.0(peer@2)`
    (9), `@scope/name@1.0.0`."""
    key = key.lstrip("/")
    head = key.split("(", 1)[0]
    at = head.rfind("@")
    if at <= 0:
        return head, ""
    return head[:at], head[at + 1:]


def plain(version: str) -> str:
    """A resolved version without its peer suffix."""
    return (version or "").split("(", 1)[0]


def suffix_peers(version: str) -> set:
    """The package names in a resolved version's peer suffix, at any depth: `1.0(a@1(b@2))(c@3)` gives a, b, c."""
    return set(_SUFFIX_PEER.findall(version or ""))


def pnpm(text: str) -> dict:
    """{"importers": {dir: {section: {name: resolved version}}}, "graph": {package key: {name: resolved version}},
    "peers": {name: [peer names]}} of a pnpm-lock.yaml: the graph holds each package's dependencies and
    optionalDependencies, the peers each package's declared peerDependencies."""
    importers, graph, peers = {}, {}, {}
    top = entry = section = dep = None
    for indent, key, value in _lines(text):
        if indent == 0:
            top, entry, section, dep = key, None, None, None
            continue
        if top == "importers":
            if indent == 2:
                entry, section, dep = key, None, None
                importers.setdefault(entry, {})
            elif indent == 4 and entry is not None:
                section, dep = key, None
                if section in ("dependencies", "optionalDependencies", "devDependencies"):
                    importers[entry].setdefault(section, {})
            elif indent == 6 and section in ("dependencies", "optionalDependencies", "devDependencies"):
                dep = key
                if value and not value.startswith("{"):   # lockfile 5: `name: version`
                    importers[entry][section][dep] = value
            elif indent == 8 and dep is not None and key == "version" and section in importers[entry]:
                importers[entry][section][dep] = value
        elif top in ("packages", "snapshots"):
            if indent == 2:
                entry, section = key.lstrip("/"), None
                graph.setdefault(entry, {})
            elif indent == 4 and entry is not None:
                section = key
            elif indent == 6 and entry is not None:
                if section in ("dependencies", "optionalDependencies"):
                    graph[entry][key] = value
                elif section == "peerDependencies" and top == "packages":
                    peers.setdefault(split_key(entry)[0], set()).add(key)
    return {"importers": importers, "graph": graph, "peers": {k: sorted(v) for k, v in peers.items()}}


def _pnpm_ref(name: str, version: str):
    """The graph key a resolved version points at, or None for a workspace link or a local path."""
    if not version or version.startswith(("link:", "file:", "workspace:")):
        return None
    if version[0].isdigit():
        return f"{name}@{version}"
    return version[4:] if version.startswith("npm:") else version   # an alias: `other@1.0.0`


def _link(importer: str, version: str):
    """The importer a `link:` version points at, relative to the lock's directory."""
    if not version.startswith("link:"):
        return None
    parts = [] if importer in (".", "") else importer.split("/")
    for step in version[5:].split("/"):
        if step == "..":
            if parts:
                parts.pop()
        elif step not in (".", ""):
            parts.append(step)
    return "/".join(parts) or "."


def pnpm_runtime(parsed: dict, held=()) -> dict:
    """{(name, version): via} for every package reachable from a shipping importer's dependencies or
    optionalDependencies, following workspace links and each package's own dependencies: what an install
    without dev dependencies (`pnpm install --prod`) puts on disk for something that ships. `via` is the
    direct dependency the shortest path starts from (the package itself when it is one).

    `held` names the importers that are not walked from: a workspace member that declares itself
    unpublished ("private": true) and has nothing that deploys it, so its dependencies serve the
    workspace's own development. The lock's root importer is walked from whatever it declares (a lone
    private app ships), and a held member that a walked importer links to is followed like any other.
    So a private workspace root that lists its tooling under `dependencies` rather than
    `devDependencies` over-reports runtime: accepted, as the root cannot be told from a lone app."""
    importers, graph = parsed["importers"], parsed["graph"]
    held = set(held) - {".", ""}
    by_plain = {}
    for key in graph:   # a snapshot may be recorded without the suffix its parent names, or the other way round
        by_plain.setdefault(key.split("(", 1)[0], []).append(key)
    seen, out, todo, done = set(), {}, collections.deque(), set()

    def visit_importer(imp):
        if imp in done or imp not in importers:
            return
        done.add(imp)
        for section in ("dependencies", "optionalDependencies"):
            for name, version in (importers[imp].get(section) or {}).items():
                linked = _link(imp, version)
                if linked is not None:
                    visit_importer(linked)
                else:
                    todo.append((name, version, name))
    for imp in list(importers):
        if imp not in held:
            visit_importer(imp)
    while todo:   # breadth first, so each package keeps the direct dependency of its shortest path
        name, version, via = todo.popleft()
        key = _pnpm_ref(name, version)
        if key is None or key in seen:
            continue
        seen.add(key)
        out.setdefault(split_key(key), via)
        keys = [key] if key in graph else by_plain.get(key.split("(", 1)[0], [])
        for k in keys:
            todo.extend((n, v, via) for n, v in graph[k].items())
    return out


def pnpm_direct(parsed: dict) -> dict:
    """{name: {plain versions some importer declares directly, in any section}}."""
    out = {}
    for sections in parsed["importers"].values():
        for deps in sections.values():
            for name, version in deps.items():
                if _pnpm_ref(name, version):
                    out.setdefault(name, set()).add(split_key(_pnpm_ref(name, version))[1])
    return out


def pnpm_importer_peers(parsed: dict, importer: str) -> set:
    """The names an importer provides as peers to what it depends on: the peer suffixes of its direct
    dependencies' resolved versions, at any depth. pnpm writes a suffix only for a peer it resolved, so an
    optional peer nobody installed is not among them."""
    out = set()
    for deps in (parsed["importers"].get(importer) or {}).values():
        for version in deps.values():
            out |= suffix_peers(version)
    return out


def _npm_name(key: str) -> str:
    return key.rsplit("node_modules/", 1)[-1]


def npm(text: str):
    """The `packages` map of a package-lock.json (v2, v3), or None for a v1 lock or an unparseable one."""
    try:
        data = json.loads(text)
    except ValueError:
        return None
    packages = data.get("packages") if isinstance(data, dict) else None
    return packages if isinstance(packages, dict) else None


def npm_runtime(packages: dict) -> set:
    """(name, version) of every installed package that is not marked `dev` or `devOptional`."""
    return {(_npm_name(k), e.get("version", "")) for k, e in packages.items()
            if k and isinstance(e, dict) and "node_modules/" in k and not e.get("dev") and not e.get("devOptional")}


def npm_direct(packages: dict) -> dict:
    """{name: {versions installed where the repository's own code resolves the name}}: `node_modules/<name>`
    at the root or under a workspace directory, not nested under another package."""
    out = {}
    for k, e in packages.items():
        if not k or not isinstance(e, dict) or "node_modules/" not in k:
            continue
        where = k.rsplit("node_modules/", 1)[0]
        if "node_modules/" not in where:
            out.setdefault(_npm_name(k), set()).add(e.get("version", ""))
    return out


def npm_peers(packages: dict, names) -> set:
    """The peerDependencies of the named packages, as installed where the repository's code resolves them."""
    names, out = set(names), set()
    for k, e in packages.items():
        if k and isinstance(e, dict) and "node_modules/" in k and "node_modules/" not in k.rsplit("node_modules/", 1)[0]:
            if _npm_name(k) in names:
                out |= set((e.get("peerDependencies") or {}).keys()) if isinstance(e.get("peerDependencies"), dict) else set()
    return out


def yarn_peers(text: str, names) -> set:
    """The peerDependencies a Yarn 2+ lock records for the entries of the named packages; a Yarn 1 lock
    records none, so it gives nothing."""
    names, out, current, section = set(names), set(), None, None
    for raw in text.split("\n"):
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        indent = len(raw) - len(raw.lstrip())
        if indent == 0:
            first = _unquote(raw.strip().rstrip(":").split(",")[0].strip())
            current = first.split("@npm:")[0] if "@npm:" in first else split_key(first)[0]
            section = None
            continue
        m = _KEY.match(raw)
        if not m:
            continue
        key = m.group(2) or m.group(3) or m.group(4)
        if indent == 2:
            section = key
        elif indent == 4 and section == "peerDependencies" and current in names:
            out.add(key)
    return out

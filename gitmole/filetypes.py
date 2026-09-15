"""Which files count as source code. Standalone so blame.py and maat.py can import it as scripts."""
from __future__ import annotations

import subprocess
from collections import Counter

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
    out = subprocess.run(["git", "ls-files"], cwd=repo, capture_output=True, text=True, check=True).stdout
    counts = Counter(key(p) for p in out.split("\n") if p)
    rows = [(k, n, matches(f"x.{k}" if k not in NAMES else k, types)) for k, n in counts.items()]
    return sorted(rows, key=lambda r: (-r[1], r[0]))

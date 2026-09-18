"""The corpus: measure/corpus.json, the pinned clones it names, and the fixtures the harness builds (the
awkward inputs and the gate's catch-rate cases), each made with fixed dates so they are the same every time."""
from __future__ import annotations

import json
import os
import subprocess
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
MANIFEST = os.path.join(ROOT, "measure", "corpus.json")
FIXED_DATE = "2026-01-05T10:00:00+00:00"


def workspace() -> str:
    """Where clones, fixtures, version sources and run outputs live: GITMOLE_MEASURE_DIR, else under TMPDIR."""
    return os.environ.get("GITMOLE_MEASURE_DIR") or os.path.join(os.environ.get("TMPDIR") or tempfile.gettempdir(), "gitmole-measure")


def load(path: str = MANIFEST) -> dict:
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def entries(manifest: dict, sets) -> list:
    wanted = set(sets)
    return [e for e in manifest["repos"] if e["set"] in wanted]


def _git(*args, cwd=None, env=None, check=True):
    return subprocess.run(["git", *args], cwd=cwd, env=env, check=check, capture_output=True)


def _env(name="Ann", email="ann@example.org", date=FIXED_DATE) -> dict:
    return dict(os.environ, GIT_CONFIG_GLOBAL="/dev/null", GIT_CONFIG_SYSTEM="/dev/null", GIT_AUTHOR_NAME=name, GIT_AUTHOR_EMAIL=email,
                GIT_COMMITTER_NAME=name, GIT_COMMITTER_EMAIL=email, GIT_AUTHOR_DATE=date, GIT_COMMITTER_DATE=date)


def clone(entry: dict, root: str = None) -> str:
    """The entry's clone at its pinned commit, on a branch named `measure`; cloned or fetched as needed.
    A fixture is built instead."""
    root = root or workspace()
    if entry.get("fixture"):
        return fixture(entry["fixture"], os.path.join(root, "fixtures"))
    dest = os.path.join(root, "clones", entry["name"])
    if not os.path.isdir(os.path.join(dest, ".git")):
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        _git("clone", "--quiet", entry["url"], dest)
    if _git("cat-file", "-e", entry["commit"] + "^{commit}", cwd=dest, check=False).returncode != 0:
        _git("fetch", "--quiet", "origin", cwd=dest)
    _git("checkout", "--quiet", "--force", "-B", "measure", entry["commit"], cwd=dest)
    return dest


def _write(repo: str, path: str, data, mode="w"):
    full = os.path.join(repo, path)
    os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, mode) as fh:
        fh.write(data)


def _commit(repo: str, message: str, **who):
    _git("add", "-A", cwd=repo, env=_env(**who))
    _git("commit", "-q", "--allow-empty", "-m", message, cwd=repo, env=_env(**who))


def fixture(kind: str, root: str) -> str:
    """Build (once) and return the fixture repository `kind`. Awkward inputs test that a run completes;
    gate cases carry exactly one thing `--fail-on critical` must catch."""
    dest = os.path.join(root, kind)
    if os.path.isdir(os.path.join(dest, ".git")) or (kind == "shallow" and os.path.isdir(dest)):
        return dest
    os.makedirs(dest, exist_ok=True)
    if kind == "shallow":   # a depth-one clone of a small history built next to it
        src = fixture("one-commit-history", root)
        os.rmdir(dest)
        _git("clone", "--quiet", "--depth", "1", "file://" + src, dest)
        return dest
    _git("init", "-q", "-b", "main", cwd=dest)
    if kind == "empty":
        return dest
    if kind in ("one-commit", "one-commit-history"):
        _write(dest, "main.py", "def main():\n    return 1\n")
        _commit(dest, "start")
        if kind == "one-commit-history":
            for i in range(5):
                _write(dest, "main.py", f"def main():\n    return {i + 2}\n")
                _commit(dest, f"change {i}", date=f"2026-01-{6 + i:02d}T10:00:00+00:00")
        return dest
    if kind == "detached":
        for i in range(3):
            _write(dest, "a.py", f"x = {i}\n")
            _commit(dest, f"c{i}", date=f"2026-01-{5 + i:02d}T10:00:00+00:00")
        _git("checkout", "-q", "--detach", "HEAD~1", cwd=dest)
        return dest
    if kind == "submodule":
        inner = fixture("one-commit", root)
        _write(dest, "app.py", "print('app')\n")
        _commit(dest, "app")
        _git("-c", "protocol.file.allow=always", "submodule", "add", "-q", "file://" + inner, "vendor/inner", cwd=dest, env=_env())
        _commit(dest, "add submodule")
        return dest
    if kind == "non-utf8-path":   # a Latin-1 name straight into the index: macOS will not create it on disk, git records it
        _write(dest, "ok.py", "y = 2\n")
        sha = subprocess.run(["git", "hash-object", "-w", "--stdin"], cwd=dest, input=b"x = 1\n", capture_output=True, check=True).stdout.decode().strip()
        _git("add", "ok.py", cwd=dest, env=_env())
        subprocess.run([b"git", b"update-index", b"--add", b"--cacheinfo", b"100644," + sha.encode() + b",caf\xe9.py"], cwd=dest, check=True, env=_env())
        _git("commit", "-q", "-m", "latin-1 file name", cwd=dest, env=_env())   # the index as it stands: add -A would stage the name's absence
        return dest
    if kind == "huge-file":
        _write(dest, "data/generated.py", "".join(f"VALUE_{i} = {i}\n" for i in range(600_000)))
        _write(dest, "main.py", "import data.generated\n")
        _commit(dest, "a very large file")
        return dest
    if kind == "binary-only":
        for i in range(3):
            _write(dest, f"blob{i}.bin", bytes(range(256)) * (i + 1), mode="wb")
            _commit(dest, f"binary {i}", date=f"2026-01-{5 + i:02d}T10:00:00+00:00")
        return dest
    if kind == "secret":   # a live-looking AWS key in source: a hand-made value, assembled here so this file holds none
        key, secret = "AK" + "IA" + "Z3Q7XK2MLPLWR4TB", "u8Jq2pR7vN1x" + "Y6tB4mK9sW3cF0hL5dG2aZ8eQ7rT"   # an access key id is base32: A-Z and 2-7
        _write(dest, "deploy.py", f'AWS_ACCESS_KEY_ID = "{key}"\nAWS_SECRET_ACCESS_KEY = "{secret}"\n')
        _commit(dest, "deploy settings")
        return dest
    if kind == "trojan-source":
        _write(dest, "check.py", 'def is_admin(user):\n    access = "user‮ ⁦# admin⁩ ⁦"\n    return access == "admin"\n')
        _commit(dest, "access check")
        return dest
    if kind == "submodule-credentials":
        url = "https://" + "deploy:" + "s3cretT0ken99" + "@git.example.org/team/lib.git"
        _write(dest, ".gitmodules", f'[submodule "lib"]\n\tpath = lib\n\turl = {url}\n')
        _write(dest, "main.py", "print(1)\n")
        _commit(dest, "submodule settings")
        return dest
    raise ValueError(f"unknown fixture {kind}")

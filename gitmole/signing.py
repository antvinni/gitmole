"""Commit signing coverage, read from the commit objects, with no keyring and no network.

`%G?` depends on the local keyring: on a fresh clone nearly every signed commit comes back E, cannot
check. The keyring-independent reading is the `gpgsig` (or `gpgsig-sha256`) header in the commit
object itself, which one `git cat-file --batch` streams for the whole history, and its payload says
which mechanism signed it: `BEGIN PGP SIGNATURE` (GPG), `BEGIN SSH SIGNATURE` (SSH), `BEGIN SIGNED
MESSAGE` (CMS, which is gitsign and Sigstore). That gives coverage and the mechanism mix, per year,
humans against bots, per identity, with nothing verified. Verification against a keyring or Rekor is
out of scope, and so is reading the Fulcio certificate inside a CMS blob, which would need a
dependency. About a tenth of commits across GitHub are signed; the figure is evidence toward SLSA
Source L2, never a level assertion.

Runs as a pipeline step, `python -m gitmole.signing OUT_DIR`, from inside the repository; writes
signing.json."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from collections import Counter

PYTHON = sys.executable
LAST_YEAR_MONTHS = 12


def kind(payload: str) -> str:
    head = payload.lstrip()[:40]
    if head.startswith("-----BEGIN PGP SIGNATURE"):
        return "gpg"
    if head.startswith("-----BEGIN SSH SIGNATURE"):
        return "ssh"
    if head.startswith("-----BEGIN SIGNED MESSAGE"):
        return "x509"
    return "other"


def _commits(repo: str) -> list:
    """[(sha, author name, date)] of HEAD's history, author names through .mailmap, oldest last as git lists them."""
    proc = subprocess.run(["git", "log", "HEAD", "--use-mailmap", "--format=%H%x1f%aN%x1f%ad", "--date=short"], cwd=repo, capture_output=True, check=True)
    out = []
    for line in proc.stdout.decode("utf-8", "replace").split("\n"):
        parts = line.split("\x1f")
        if len(parts) == 3:
            out.append(tuple(parts))
    return out


def _signatures(repo: str, shas: list) -> dict:
    """{sha: mechanism} for the commits whose object carries a gpgsig header, through one cat-file --batch."""
    if not shas:
        return {}
    proc = subprocess.run(["git", "cat-file", "--batch"], cwd=repo, input="\n".join(shas).encode() + b"\n", capture_output=True, check=True)
    data, pos, out = proc.stdout, 0, {}
    while pos < len(data):
        end = data.find(b"\n", pos)
        if end < 0:
            break
        header = data[pos:end].decode("ascii", "replace").split()
        pos = end + 1
        if len(header) != 3 or header[1] != "commit":
            continue   # "missing" or a non-commit: nothing to read
        sha, size = header[0], int(header[2])
        body = data[pos:pos + size].decode("utf-8", "replace")
        pos += size + 1   # the trailing newline after the object
        headers = body.split("\n\n", 1)[0]
        for line in headers.split("\n"):
            if line.startswith("gpgsig ") or line.startswith("gpgsig-sha256 "):
                out[sha] = kind(line.split(" ", 1)[1])
                break
    return out


def coverage(repo: str, bots: set = frozenset()) -> dict:
    """How much of HEAD's history is signed, and how: totals, by mechanism, by year, humans against
    bots (the run's own bot names), per identity, and over the twelve months before the last commit."""
    commits = _commits(repo)
    signed = _signatures(repo, [sha for sha, _, _ in commits])
    mechanisms, by_year, by_identity = Counter(), {}, {}
    humans, robots = {"commits": 0, "signed": 0}, {"commits": 0, "signed": 0}
    last = max((d for _, _, d in commits), default="")
    cut = f"{int(last[:4]) - 1}{last[4:]}" if last else ""
    last_year = {"commits": 0, "signed": 0}
    for sha, author, date in commits:
        is_signed = sha in signed
        if is_signed:
            mechanisms[signed[sha]] += 1
        year = by_year.setdefault(date[:4], {"commits": 0, "signed": 0})
        year["commits"] += 1
        year["signed"] += is_signed
        who = robots if author in bots else humans
        who["commits"] += 1
        who["signed"] += is_signed
        ident = by_identity.setdefault(author, {"name": author, "commits": 0, "signed": 0})
        ident["commits"] += 1
        ident["signed"] += is_signed
        if cut and date > cut:
            last_year["commits"] += 1
            last_year["signed"] += is_signed
    identities = sorted(by_identity.values(), key=lambda i: (-i["commits"], i["name"]))
    return {"commits": len(commits), "signed": len(signed), "mechanisms": dict(sorted(mechanisms.items())),
            "by_year": dict(sorted(by_year.items())), "humans": humans, "bots": robots, "by_identity": identities[:50], "last_year": last_year}


def main(argv=None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 1:
        print("usage: signing.py OUT_DIR", file=sys.stderr)
        return 2
    out_dir = args[0]
    bots = set()
    meta_path = os.path.join(out_dir, "meta.json")
    if os.path.exists(meta_path):
        with open(meta_path, encoding="utf-8") as fh:
            bots = {b["name"] for b in (json.load(fh).get("bots") or [])}
    try:
        data = coverage(os.getcwd(), bots)
    except subprocess.CalledProcessError as e:
        print(f"signing.py: {(e.stderr or b'').decode('utf-8', 'replace').strip() or e}", file=sys.stderr)
        return 1
    with open(os.path.join(out_dir, "signing.json"), "w", encoding="utf-8") as fh:
        json.dump(data, fh)
    return 0


if __name__ == "__main__":
    sys.exit(main())

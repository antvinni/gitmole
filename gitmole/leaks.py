#!/usr/bin/env python3
"""betterleaks, with the secret values kept out of the output directory.

gitmole runs this as the betterleaks step: `python3 leaks.py OUT_JSON`, from inside the repository.
betterleaks writes its JSON report to our stdout, so the raw report is never a file; each value is
replaced by a short keyed hash (enough to tell one value repeated in many places from many values)
and a flag for shapes that cannot be a live secret, and only that is written. The key is random,
made for one report and never stored, so a hash in secrets.json cannot be checked against a list of
likely values; the price is that hashes from two runs cannot be compared, which nothing does. The report never needed the
values: it names the rule, the file and the commit. Standalone, like maat.py and blame.py.

The same module groups the loaded rows for the findings and the report footer.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import subprocess
import sys
import tempfile

try:
    from . import filetypes
except ImportError:  # run as a script: the package directory is sys.path[0]
    import filetypes

ARGV = ["betterleaks", "git", "--no-banner", "--report-format", "json", "--report-path", "-", "--exit-code", "0"]
# the value, the text around it, and the commit message, which can quote it; Attributes repeats the message
RAW_FIELDS = ("Secret", "Match", "Line", "Message", "Attributes")

# Shapes that cannot be a live secret: a version string (5.0.0-1667386184.dfbbb54), a token shortened
# with an ellipsis, a whole-value template marker (your-project-id, <your-token>, XXXX-XXXX, changeme),
# a whole value that is one of the words every example uses (`password: 'hello'` in a doc comment),
# and a key block whose body holds no key material. Every rule is about the whole value; nothing is
# skipped by prefix, since a public and a private key of the same service often share one.
_VERSION = re.compile(r"^\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?$")
_MARKER = re.compile(r"^(<[^<>]+>|x+|(?:x{2,}[-_ ]?)+|your[-_][\w-]+|change[-_]?me|replace[-_]?me)$", re.I)
_EXAMPLE_WORDS = {"password", "passwd", "pass", "secret", "hello", "hey", "test", "example", "sample", "dummy", "foo", "bar",
                  "baz", "admin", "root", "user", "123456", "12345678", "123456789", "abc123", "qwerty", "letmein", "welcome",
                  "x-oauth-basic", "x-access-token", "x-token-auth"}   # documented literals for the password slot of token auth
# A whole value that refers to an environment variable or a template field is where the secret will be
# read from, not the secret: `@env:AC_PASSWORD`, `${DB_PASSWORD}`, `{{.Env.X}}`, `process.env.X`, `<%= ENV['X'] %>`.
_ENV_REF = re.compile(r"^(@env:\w+|\$\{[^{}]+\}|\$[A-Za-z_]\w*|\$\([^()]+\)|%[A-Za-z_]\w*%|\{\{.*\}\}|<%=?.*%>"
                      r"|process\.env\.\w+|os\.environ(\[[^\]]+\]|\.get\([^()]*\))|ENV\[[^\]]+\])$", re.S)
_KEY_BLOCK = re.compile(r"-----BEGIN [A-Z ]*KEY-----(.*?)-----END [A-Z ]*KEY-----", re.S)
_KEY_MATERIAL = 64   # a real body is hundreds of base64 characters; a template has dots or a few x's


def new_key() -> bytes:
    """A random key for one report. Never written anywhere."""
    return os.urandom(32)


def digest(value: str, key: bytes) -> str:
    """HMAC-SHA256 of the value under the report's key, cut to 12 hex characters: equal values in one
    report share it, and without the key it says nothing about the value."""
    return hmac.new(key, value.encode("utf-8", "surrogateescape"), hashlib.sha256).hexdigest()[:12]


# A header followed by no key material is a pattern a script greps for, not a key (ohmyzsh's ssh-agent
# plugin: the scanner captures the header and the shell code after it).
_HEADER = re.compile(r"^\^?-----BEGIN[ \\A-Z]*KEY-----")
_BASE64_RUN = re.compile(r"[A-Za-z0-9+/=]{40,}")
# A line that calls its own value an example is documentation, wherever it sits: "# Example password: ...".
_EXAMPLE_LINE = re.compile(r"\b(example|sample|dummy|fake|placeholder)|\be\.g\.", re.I)


def _made_up(value: str) -> bool:
    """A run up the alphabet and the digits (qr6stu789vwxyz, abcd1234): typed, not generated. Eight
    characters or more, letters non-decreasing, digits non-decreasing, both present or one long."""
    alnum = re.sub(r"[^A-Za-z0-9]", "", value).lower()
    letters = [c for c in alnum if c.isalpha()]
    digits = [c for c in alnum if c.isdigit()]
    if len(alnum) < 8 or len(alnum) != len(letters) + len(digits):
        return False
    return letters == sorted(letters) and digits == sorted(digits) and len(set(letters)) >= 4 or (not letters and digits == sorted(digits))


# A template field anywhere inside the value: {token}, ${X}, ${{ X }}, %(name)s, {{ x }}, <user>.
_TEMPLATE_FIELD = re.compile(r"\{[A-Za-z_][\w.]*\}|\$\{[^{}]*\}|\$\{\{.*?\}\}|%\([A-Za-z_]\w*\)s|\{\{.*?\}\}|<[A-Za-z_][\w-]*>")
# Five or more words of letters: a description of the secret, not the secret.
_PROSE = re.compile(r"^[A-Za-z][A-Za-z'-]*(\s+[A-Za-z][A-Za-z'-]*){4,}\s*$")


def is_placeholder(value: str, line: str = "") -> bool:
    """Whether `value` has a shape that cannot be a live secret. `line` is the source line the value
    sat on, read from the clone at scan time and never written."""
    value = (value or "").strip()
    if (_VERSION.match(value) or value.endswith("...") or value.endswith("…") or _MARKER.match(value) or value.lower() in _EXAMPLE_WORDS
            or _ENV_REF.match(value) or _made_up(value) or _TEMPLATE_FIELD.search(value) or _PROSE.match(value)):
        return True
    if line and (_EXAMPLE_LINE.search(line) or _TEMPLATE_FIELD.search(line)):   # the line is an example, or a template being filled in
        return True
    m = _KEY_BLOCK.search(value)
    if m:
        body = re.sub(r"\s|\.|…|\\n", "", m.group(1))   # literal \n sequences appear in JSON samples
        return len(body) < _KEY_MATERIAL
    h = _HEADER.match(value)
    if h and not _BASE64_RUN.search(value[h.end():]):
        return True
    return False


def line_of(repo: str, commit: str, path: str, number: int) -> str:
    """Line `number` of `path` as it was at `commit`, from the clone; "" when it cannot be read. Read
    for the placeholder rule and dropped, like every other raw field."""
    if not (commit and path and number):
        return ""
    proc = subprocess.run(["git", "-C", repo, "show", f"{commit}:{path}"], capture_output=True)
    if proc.returncode != 0:
        return ""
    lines = proc.stdout.decode("utf-8", "replace").split("\n")
    return lines[number - 1] if 0 < number <= len(lines) else ""


LINE_LOOKUPS = 400   # one git call per finding; past this many the rest go without their line


def sanitise(rows: list) -> list:
    key = new_key()   # one key for the whole report, so repeats of a value still group
    out = []
    for r in rows:
        value = r.get("Secret") or ""
        clean = {k: v for k, v in r.items() if k not in RAW_FIELDS}
        clean["SecretHash"] = digest(value, key)
        clean["Placeholder"] = is_placeholder(value, r.get("Line") or "")   # the line is read here and dropped with the other raw fields
        out.append(clean)
    return out


def group(rows: list) -> list:
    """One entry per distinct secret value (placeholders left out): its rule, the files and commits it
    appears in, the number of distinct places (commit, file, line), whether every place is a test
    file, and whether every place is a documentation file. Values that appear in source come first,
    then the most widespread."""
    groups, order = {}, []
    for i, r in enumerate(rows):
        if r.get("placeholder"):
            continue
        key = r.get("value") or ("row", i)
        if key not in groups:
            groups[key] = {"value": r.get("value"), "rule": r["rule"], "files": [], "commits": [], "_places": set(), "test": True, "docs": True}
            order.append(key)
        g = groups[key]
        if r["file"] not in g["files"]:
            g["files"].append(r["file"])
        if r["commit"] not in g["commits"]:
            g["commits"].append(r["commit"])
        g["_places"].add((r["commit"], r["file"], r.get("line")))
        g["test"] = g["test"] and filetypes.is_test_path(r["file"])
        g["docs"] = g["docs"] and filetypes.is_doc_path(r["file"])
    out = []
    for key in order:
        g = groups[key]
        places = g.pop("_places")
        out.append({**g, "places": len(places)})
    out.sort(key=lambda g: (g["test"], -g["places"]))   # stable: first-seen order breaks ties
    return out


def placeholders(rows: list) -> int:
    """Distinct places whose value had a placeholder shape."""
    return len({(r["commit"], r["file"], r.get("line")) for r in rows if r.get("placeholder")})


def main(argv=None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 1:
        print("usage: leaks.py OUT_JSON", file=sys.stderr)
        return 2
    target = args[0]
    # stderr is inherited, so betterleaks' own log lands in run.log as before
    proc = subprocess.run(ARGV, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE)
    if proc.returncode != 0:
        print(f"leaks.py: betterleaks exited {proc.returncode}; no report written", file=sys.stderr)
        return proc.returncode
    text = proc.stdout.decode("utf-8", "surrogateescape").strip()
    raw = (json.loads(text) if text else None) or []   # a clean repository is reported as null
    for r in raw[:LINE_LOOKUPS]:   # betterleaks does not report the line; the clone in the current directory has it
        r["Line"] = line_of(os.getcwd(), r.get("Commit") or "", r.get("File") or "", int(r.get("StartLine") or 0))
    rows = sanitise(raw)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(os.path.abspath(target)), prefix=".secrets-", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(rows, fh, indent=1)
        os.replace(tmp, target)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)
    return 0


if __name__ == "__main__":
    sys.exit(main())

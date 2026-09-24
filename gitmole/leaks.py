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

# --validation=false: betterleaks can check a found credential against the live service, which is network;
# it is off by default, and gitmole says so rather than rely on the default.
# --log-opts "--full-history HEAD": betterleaks' own default is `--full-history --all`, every reference in
# the clone, so a clone carrying a thousand remote-tracking branches reports secrets another clone of
# the same commit does not have. HEAD's history is the commit's; the unreachable objects are scanned
# separately below and recorded as the clone's in the envelope.
ARGV = ["betterleaks", "git", "--no-banner", "--report-format", "json", "--report-path", "-", "--exit-code", "0", "--validation=false",
        "--log-opts", "--full-history HEAD"]
DIR_ARGV = ["betterleaks", "dir", "{dir}", "--no-banner", "--report-format", "json", "--report-path", "-", "--exit-code", "0", "--validation=false"]
UNREACHABLE_CAP = 5000          # blobs scanned outside reachable history; the count of the rest is recorded
UNREACHABLE_MAX_BYTES = 1_000_000
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
                  "baz", "admin", "root", "user", "123456", "12345678", "123456789", "abc123", "qwerty", "letmein", "welcome"}
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
# A dotted path of lowercase words (passwords.password, auth.failed): a translation or config key, not a password.
_KEY_PATH = re.compile(r"^[a-z_]+(\.[a-z_]+)+$")


# Languages whose string literals must be quoted: there, a value the scanner matched without a quote in
# front of it is a symbol or an expression (`PSW = EIPSW;`, `id == idaapi.PLFM_386`), not a literal. Shell,
# configuration and markup are left out, since `PASSWORD=hunter2` is a literal there. sinc and slaspec are
# SLEIGH processor specifications, which name registers like PSW.
QUOTED_LANGUAGES = frozenset("""
py pyi pyx js jsx mjs cjs ts tsx vue svelte java kt kts scala groovy gradle c cc cpp cxx h hh hpp hxx m mm cs fs go rs swift rb php
dart ex exs lua r jl zig nim cr ml hs sql proto sinc slaspec
""".split())
_MASKED = re.compile(r"^[^:\s]+:(x{3,}|\*{3,}|<[^<>]+>|\.{3,})$", re.I)   # user:XXXXXX, user:****, user:<password>
_FILE_REF = re.compile(r"\.(png|jpe?g|gif|svg|ico|icns|bmp|webp|pdf|html?|css|md|txt|xml|properties)\b", re.I)
_LABEL = re.compile(r"^[A-Za-z_]*(pass(word|wd|phrase)|secret|token)[A-Za-z_]*$", re.I)   # resetpassword, password_missing: a name, not a value


def _is_label(value: str) -> bool:
    """A name built on the keyword, in one case as names are written (resetpassword, CURLOPT_PASSWD,
    password_missing); a mixed-case word such as MyCompanySecret is more likely a chosen password."""
    return bool(_LABEL.match(value)) and (value == value.lower() or value == value.upper())
_HEADER_WRITTEN = re.compile(r"^-----BEGIN[ A-Z]*KEY-----(?:\\n)?[\"'`]")   # print("-----BEGIN ... KEY-----\n"): code writing a PEM file
_UUID = re.compile(r"\b[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}\b")


def _unquoted(value: str, line: str, path: str) -> bool:
    """Whether the source line shows `value` outside any string literal, right after an assignment, a
    comparison, an opening parenthesis or a comma, in a language where a literal would be quoted. The
    quotes before it are counted, so `"https://user:pass@host"` and `"?token=abc"` stay literals."""
    ext = path.rsplit(".", 1)[-1].lower() if "." in path.rsplit("/", 1)[-1] else ""
    if ext not in QUOTED_LANGUAGES or not line:
        return False
    last = line.split("\n")[-1]
    i = last.find(value)
    if i < 0:
        return False
    before = last[:i]
    plain = re.sub(r"\\.", "", before)   # an escaped quote does not open or close anything
    if plain.count('"') % 2 or plain.count("'") % 2 or plain.count("`") % 2:
        return False
    return before.rstrip().endswith(("=", "(", ","))


def _repeats_nearby(value: str, line: str) -> bool:
    """A short alphabetic value that is also a word of its own key or of the lines around it
    (POSTGRES_PASSWORD: postgres; "USER": "postgres" above "PASSWORD": "postgres"): a service's default,
    which a real password does not repeat."""
    if not line or not re.fullmatch(r"[A-Za-z]{3,20}", value):
        return False
    last = line.split("\n")[-1]
    i = last.find(value)
    context = (line[: len(line) - len(last) + i] if i >= 0 else line) + " " + (last[i + len(value):] if i >= 0 else "")
    words = {w.lower() for w in re.findall(r"[A-Za-z]+", context)}
    return value.lower() in words


def is_placeholder(value: str, line: str = "", path: str = "") -> bool:
    """Whether `value` has a shape that cannot be a live secret. `line` is the source line the value
    sat on (with two above), read from the clone at scan time and never written; `path` is the file,
    which with the line says whether the value was a quoted literal."""
    value = (value or "").strip()
    if _HEADER_WRITTEN.match(value) or _MASKED.match(value) or (_FILE_REF.search(value) and not any(ch.isspace() for ch in value)) or _is_label(value):
        return True
    if _unquoted(value, line or "", path or ""):
        return True
    if _repeats_nearby(value, line or ""):
        return True
    stripped = re.sub(r"[^A-Za-z0-9]", "", value).lower()
    if stripped != value.lower() and stripped in _EXAMPLE_WORDS:   # pass?word, p-a-s-s-w-o-r-d: an example word with its punctuation
        return True
    if line and _UUID.fullmatch(value) and len(_UUID.findall(line)) >= 2:   # a table of interface ids, not a token
        return True
    if (_VERSION.match(value) or value.endswith("...") or value.endswith("…") or _MARKER.match(value) or value.lower() in _EXAMPLE_WORDS
            or _ENV_REF.match(value) or _made_up(value) or _TEMPLATE_FIELD.search(value) or _PROSE.match(value) or _KEY_PATH.match(value)):
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


def line_of(repo: str, commit: str, path: str, number: int, above: int = 0) -> str:
    """Line `number` of `path` as it was at `commit`, from the clone, with `above` lines before it
    joined on; "" when it cannot be read. Read for the placeholder rules and dropped, like every
    other raw field. Two lines above catch a comment that calls the value an example."""
    if not (commit and path and number):
        return ""
    proc = subprocess.run(["git", "-C", repo, "show", f"{commit}:{path}"], capture_output=True)
    if proc.returncode != 0:
        return ""
    lines = proc.stdout.decode("utf-8", "replace").split("\n")
    if not 0 < number <= len(lines):
        return ""
    return "\n".join(lines[max(0, number - 1 - above):number])


LINE_LOOKUPS = 400   # one git call per finding; past this many the rest go without their line


def sanitise(rows: list) -> list:
    key = new_key()   # one key for the whole report, so repeats of a value still group
    out = []
    for r in rows:
        value = r.get("Secret") or ""
        clean = {k: v for k, v in r.items() if k not in RAW_FIELDS}
        attrs = r.get("Attributes") if isinstance(r.get("Attributes"), dict) else {}
        if attrs.get("confidence") in ("low", "medium", "high"):   # the scanner's own grade, kept; the rest of Attributes can quote the value
            clean["Confidence"] = attrs["confidence"]
            if str(r.get("RuleID", "")).startswith("generic-") and _ONE_WORD.fullmatch(value):
                clean["Confidence"] = "low"   # PGPASSWORD: postgres. The context raised it; a word of one case is a service default or a sample
        clean["SecretHash"] = digest(value, key)
        clean["Placeholder"] = is_placeholder(value, r.get("Line") or "", r.get("File") or "")   # read here and dropped with the other raw fields
        out.append(clean)
    return out


CONFIDENCE = {"low": 0, "medium": 1, "high": 2}
_ONE_WORD = re.compile(r"[a-z]{3,20}|[A-Z]{3,20}")


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
            groups[key] = {"value": r.get("value"), "rule": r["rule"], "files": [], "commits": [], "_places": set(), "test": True, "docs": True,
                           "confidence": None}
            order.append(key)
        g = groups[key]
        if r["file"] not in g["files"]:
            g["files"].append(r["file"])
        if r["commit"] not in g["commits"]:
            g["commits"].append(r["commit"])
        g["_places"].add((r["commit"], r["file"], r.get("line")))
        if CONFIDENCE.get(r.get("confidence"), -1) > CONFIDENCE.get(g["confidence"], -1):   # the scanner's highest grade for the value
            g["confidence"] = r.get("confidence")
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


def unreachable(repo: str):
    """The objects no ref reaches: a commit only the reflog remembers, a stash dropped, a blob added and
    never committed. betterleaks walks the reachable history and sees none of them. Every object in the
    repository (`cat-file --batch-all-objects`) less those `rev-list --objects --all` reaches; the blobs
    among them, up to the cap and under a megabyte, are what gets scanned. None outside a repository. A
    fresh clone fetches only reachable objects, so there it is zero, and the record says so."""
    def run(*args):
        return subprocess.run(["git", *args], cwd=repo, capture_output=True)
    every = run("cat-file", "--batch-all-objects", "--batch-check=%(objectname) %(objecttype) %(objectsize)")
    reached = run("rev-list", "--objects", "--all")
    if every.returncode != 0 or reached.returncode != 0:
        return None
    seen = {line.split(b" ", 1)[0] for line in reached.stdout.split(b"\n") if line}
    objects, blobs = 0, []
    for line in every.stdout.split(b"\n"):
        parts = line.split()
        if len(parts) != 3 or parts[0] in seen:
            continue
        objects += 1
        if parts[1] == b"blob" and int(parts[2]) <= UNREACHABLE_MAX_BYTES:
            blobs.append(parts[0].decode())
    return {"objects": objects, "blobs": len(blobs), "shas": sorted(blobs)}


UNREACHABLE = "(unreachable blob "   # the File of a row from an unreachable blob, before its hash


def scan_unreachable(repo: str, out_dir: str, found: dict) -> list:
    """betterleaks over the unreachable blobs, each written under the output directory by its hash and
    removed again; its rows name the blob as `(unreachable blob <hash>)`, with no commit."""
    shas = found["shas"][:UNREACHABLE_CAP]
    if not shas:
        return []
    with tempfile.TemporaryDirectory(dir=out_dir, prefix=".unreachable-") as tmp:
        proc = subprocess.run(["git", "cat-file", "--batch"], cwd=repo, capture_output=True, input="\n".join(shas).encode() + b"\n")
        data, pos = proc.stdout, 0
        for sha in shas:
            end = data.find(b"\n", pos)
            if end < 0:
                break
            header = data[pos:end].split()
            size = int(header[2]) if len(header) == 3 else 0
            with open(os.path.join(tmp, sha), "wb") as fh:
                fh.write(data[end + 1:end + 1 + size])
            pos = end + 1 + size + 1
        argv = [tmp if a == "{dir}" else a for a in DIR_ARGV]
        scan = subprocess.run(argv, cwd=repo, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE)
        if scan.returncode != 0:
            print(f"leaks.py: betterleaks dir exited {scan.returncode}; unreachable blobs not scanned", file=sys.stderr)
            return []
        text = scan.stdout.decode("utf-8", "surrogateescape").strip()
        rows = (json.loads(text) if text else None) or []
    for r in rows:
        sha = os.path.basename(r.get("File") or "")
        r["File"] = f"{UNREACHABLE}{sha[:12]})"
        r["Commit"] = ""
        # betterleaks' own fingerprint names the scratch path the blob was written to; this one names the blob,
        # so it is the same in every run and can go into .betterleaksignore
        r["Fingerprint"] = f"unreachable:{sha}:{r.get('RuleID', '')}:{r.get('StartLine', '')}"
    return rows


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
        r["Line"] = line_of(os.getcwd(), r.get("Commit") or "", r.get("File") or "", int(r.get("StartLine") or 0), above=2)
    found = unreachable(os.getcwd())
    extra = scan_unreachable(os.getcwd(), os.path.dirname(os.path.abspath(target)), found) if found else []
    rows = sanitise(raw + extra)
    if found is not None:
        with open(os.path.join(os.path.dirname(os.path.abspath(target)), "unreachable.json"), "w", encoding="utf-8") as fh:
            json.dump({"objects": found["objects"], "blobs": found["blobs"], "scanned": min(found["blobs"], UNREACHABLE_CAP),
                       "findings": len(extra)}, fh)
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

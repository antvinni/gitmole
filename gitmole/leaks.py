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
# The word stands on its own: a prefix of an identifier (`sample_rate = 0.1`, `fake_clock`) or a path
# segment (`see examples/README`) names something else, not the value. An identifier that is the value's
# own key (SAMPLE_KEY = '...') is read separately, by its segments (_segments).
_EXAMPLE_LINE = re.compile(r"(?<![\w/-])(examples?|samples?|dummy|fake|placeholder)(?![\w/-])|\be\.g\.", re.I)
# The value itself says so: AWS's documented AKIAIOSFODNN7EXAMPLE, `username:fakepwd` (the line rule used to
# catch these through the value's own text on the line; a provider's rule now reads only the value). The
# word in one case, as words are written: a random key's chance of spelling `fake` so is one in 64^4 per
# position, against one in 32^4 case-blind. A key block is left to its own rule, since its body is long
# enough to spell anything.
_SAYS_EXAMPLE = re.compile("|".join(w for word in ("example", "sample", "dummy", "fake", "placeholder") for w in (word, word.upper(), word.capitalize())))
_EXAMPLE_SEGMENTS = {"example", "examples", "sample", "samples", "dummy", "fake", "placeholder"}


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
# A hint written into a form field: `'eg. ************'`, `"e.g. admin"`, `"i.e. https://..."`. A secret has
# no "eg." standing as a word of its own inside it.
_HINT = re.compile(r"(?:^|\s)(?:e\.?g|i\.e)\.(?:\s|$)", re.I)
# A value made only of mask characters: `************`, `••••••`. (x's are _MARKER's.)
_MASK_ONLY = re.compile(r"^[*•●]{3,}$")
# A value of several words that names the kind of credential it stands for (`Enter Password`, `jenkins api
# access token`) is a form label or a description. The words are the keywords of betterleaks' own
# generic-password and generic-api-key rules. Whitespace alone decides nothing: betterleaks captures it only
# in generic-password's quoted form (its unquoted form and generic-api-key's value exclude it), and a
# passphrase has spaces, so `correct horse battery staple` is still taken seriously; what marks a label is
# that it names the credential rather than being one.
_CREDENTIAL_WORD = re.compile(r"(?<![A-Za-z])(passw(?:or)?ds?|passphrases?|pwd|psw|tokens?|secrets?|keys?|credentials?|creds|auth)(?![A-Za-z])", re.I)
_WORDS = re.compile(r"^[A-Za-z][A-Za-z'./-]*(?:\s+[A-Za-z][A-Za-z'./-]*)+$")   # two or more words of letters, nothing else
# A data: URI's base64 payload (an inline image, a font): a provider's pattern can match inside its bytes.
_DATA_URI = re.compile(r"data:[\w.+-]+/[\w.+-]+(?:;[\w.+-]+=[\w.+-]+)*;base64,([A-Za-z0-9+/=]+)", re.I)
# What stands between a key and its value on the value's own line: `password: '`, `"token" => "`, `KEY = `.
_KEY_BEFORE = re.compile(r"([A-Za-z_][\w.-]*)[\"'`\]]?\s*(?:=>|:=|=|:)\s*[\"'`]?$")


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


def _key_of(value: str, line: str) -> str:
    """The key the value is assigned to on its own line (`password` in `password: 'x'`), or ""."""
    if not line:
        return ""
    last = line.split("\n")[-1]
    i = last.rfind(value)   # the value follows its key, which can be the same word
    m = _KEY_BEFORE.search(last[:i]) if i > 0 else None
    return m.group(1) if m else ""


def _segments(name: str) -> list:
    """An identifier's words: SAMPLE_KEY, sampleKey and sample-key are all [sample, key]."""
    return [w.lower() for w in re.findall(r"[A-Z]+(?![a-z])|[A-Z]?[a-z]+|\d+", name)]


def _in_data_uri(value: str, line: str) -> bool:
    """Whether the value sits inside a data: URI's base64 payload on its own line: bytes of an image."""
    last = (line or "").split("\n")[-1]
    return bool(value) and any(value in m.group(1) for m in _DATA_URI.finditer(last))


def is_placeholder(value: str, line: str = "", path: str = "", rule: str = "") -> bool:
    """Whether `value` has a shape that cannot be a live secret. `line` is the source line the value
    sat on (with two above), read from the clone at scan time and never written; `path` is the file,
    which with the line says whether the value was a quoted literal. `rule` is betterleaks' rule id: a
    provider's rule (anything but generic-*) matched the provider's own key format, so its value is
    judged by its own shape and where it sits (in a data: URI, in a table of GUIDs), never by the words
    around it (a real key under `# see examples/README` is still a key); the generic rules matched a
    keyword and a string, and there the context is the evidence."""
    value = (value or "").strip()
    if _in_data_uri(value, line or ""):
        return True
    if line and _UUID.fullmatch(value) and len(_UUID.findall(line)) >= 2:   # a table of interface ids, not a token (ghidra's iids.txt, where a
        return True                                                        # provider's pattern for tokens beginning EAAA matched a GUID)
    if rule and not rule.startswith("generic-"):
        line = ""
    if _HEADER_WRITTEN.match(value) or _MASKED.match(value) or (_FILE_REF.search(value) and not any(ch.isspace() for ch in value)) or _is_label(value):
        return True
    if (_HINT.search(value) or _MASK_ONLY.match(value) or (_WORDS.match(value) and _CREDENTIAL_WORD.search(value))
            or (_SAYS_EXAMPLE.search(value) and "-----BEGIN" not in value)):
        return True
    key = _key_of(value, line or "")
    if key and (re.sub(r"[^a-z0-9]", "", value.lower()) in {re.sub(r"[^a-z0-9]", "", k.lower()) for k in (key, key.rsplit(".", 1)[-1])}
                or _EXAMPLE_SEGMENTS & set(_segments(key))):   # password: 'Password'; SAMPLE_KEY = '...'
        return True
    if _unquoted(value, line or "", path or ""):
        return True
    if _repeats_nearby(value, line or ""):
        return True
    stripped = re.sub(r"[^A-Za-z0-9]", "", value).lower()
    if stripped != value.lower() and stripped in _EXAMPLE_WORDS:   # pass?word, p-a-s-s-w-o-r-d: an example word with its punctuation
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


def _file_at(repo: str, commit: str, path: str):
    """The lines of `path` at `commit`, or None when it cannot be read."""
    proc = subprocess.run(["git", "-C", repo, "show", f"{commit}:{path}"], capture_output=True)
    return proc.stdout.decode("utf-8", "replace").split("\n") if proc.returncode == 0 else None


def line_of(repo: str, commit: str, path: str, number: int, above: int = 0, files: dict = None) -> str:
    """Line `number` of `path` as it was at `commit`, from the clone, with `above` lines before it
    joined on; "" when it cannot be read. Read for the placeholder rules and dropped, like every
    other raw field. Two lines above catch a comment that calls the value an example. `files`, when
    given, keeps each file read for the next row in it, so a file is one git call however many rows."""
    if not (commit and path and number):
        return ""
    if files is None:
        lines = _file_at(repo, commit, path)
    else:
        if (commit, path) not in files:
            files[(commit, path)] = _file_at(repo, commit, path)
        lines = files[(commit, path)]
    if lines is None or not 0 < number <= len(lines):
        return ""
    return "\n".join(lines[max(0, number - 1 - above):number])


LINE_LOOKUPS = 400   # rows whose line is read; past this many a generic rule's rows go without it


def read_lines(repo: str, rows: list) -> None:
    """Each row's source line, for the placeholder rules: the first LINE_LOOKUPS rows, and past them the
    rows of a provider's rule, which are few and whose line can still show the value is not a key (bytes
    of an inline image, a table of GUIDs). A generic rule's row past the cap goes without, as before."""
    files = {}
    for i, r in enumerate(rows):
        if i >= LINE_LOOKUPS and str(r.get("RuleID") or "").startswith("generic-"):
            continue
        r["Line"] = line_of(repo, r.get("Commit") or "", r.get("File") or "", int(r.get("StartLine") or 0), above=2, files=files)


# What the repository says about its own findings. betterleaks reads the allowlist of the config in the
# directory it runs in, today's version only, so a value the repository allowlisted and later replaced with
# another (VoiceStudio's public analytics key, rotated for a second public key) is still reported at the
# commit that added it. The config files as every commit of HEAD's history had them, and the inline
# marker on the value's own line in any version of its file, are the repository's declaration.
CONFIGS = (".gitleaks.toml", ".betterleaks.toml", ".gitleaksignore", ".betterleaksignore")
ALLOW_MARKERS = ("gitleaks:allow", "betterleaks:allow")
_TOML_TOKEN = re.compile(r"'''(.*?)'''|\"\"\"(.*?)\"\"\"|'([^'\n]*)'|\"((?:[^\"\\\n]|\\.)*)\"|(#[^\n]*)"
                         r"|^[ \t]*(\[\[?[^\]\n]*\]\]?)|(?:^|[{,])[ \t]*([A-Za-z0-9_.-]+)[ \t]*=", re.S | re.M)
_ALLOW_KEYS = ("regexes", "stopwords", "paths", "commits")


def _toml_string(m) -> str:
    if m.group(4) is not None:   # a basic string: its escapes are TOML's, not the regex's
        return re.sub(r"\\(.)", lambda e: {"n": "\n", "t": "\t", "\\": "\\", '"': '"'}.get(e.group(1), "\\" + e.group(1)), m.group(4))
    return next(g for g in m.groups()[:3] if g is not None)


def allowlists(text: str) -> list:
    """The allowlists a gitleaks/betterleaks TOML config declares: the global [allowlist], every
    [[allowlists]] and each rule's [rules.allowlist] / [[rules.allowlists]], as dicts of regexes,
    stopwords, paths and commits plus regexTarget and condition. A small reader, since the Python gitmole
    supports may predate tomllib: strings are assigned to the key before them and the table they sit in;
    an allowlist written as an inline table ({ regexes = [...] }) is not read."""
    out, current, key = [], None, None
    for m in _TOML_TOKEN.finditer(text or ""):
        if m.group(5) is not None:
            continue
        if m.group(6) is not None:
            name = m.group(6).strip("[] \t").lower()
            current = {k: [] for k in _ALLOW_KEYS} if name.split(".")[-1] in ("allowlist", "allowlists") else None
            if current is not None:
                current.update(target="secret", condition="or")
                out.append(current)
            key = None
            continue
        if m.group(7) is not None:
            key = m.group(7)
            continue
        if current is None or key is None:
            continue
        value = _toml_string(m)
        if key in _ALLOW_KEYS:
            current[key].append(value)
        elif key == "regexTarget":
            current["target"] = value.lower()
        elif key == "condition":
            current["condition"] = value.lower()
    return out


def _search(pattern: str, text: str) -> bool:
    """RE2's pattern against `text`; a pattern Python's re cannot read is compared as a literal."""
    try:
        return re.search(pattern.replace(r"\z", r"\Z"), text or "") is not None
    except re.error:
        return pattern == text


def _allowed_by(lists: list, row: dict) -> str:
    """How an allowlist of `lists` covers the row's value: "regex", "stopword" or ""; a paths or commits
    entry is honoured only beside one of those under condition AND, since on its own it declares a place,
    not the value, and betterleaks applies today's already."""
    value, line = row.get("Secret") or "", (row.get("Line") or "").split("\n")[-1]
    for a in lists:
        subject = {"line": line, "match": row.get("Match") or ""}.get(a["target"], value)
        hits = {"regex": any(_search(p, subject) for p in a["regexes"]),
                "stopword": any(w and w.lower() in value.lower() for w in a["stopwords"])}
        if a["condition"] == "and":
            place = [c for c, entries in (("paths", a["paths"]), ("commits", a["commits"])) if entries]
            by_place = all(any(_search(p, row.get("File") or "") for p in a["paths"]) if c == "paths"
                           else any(str(row.get("Commit") or "").startswith(e) for e in a["commits"] if e) for c in place)
            asked = [k for k, entries in (("regex", a["regexes"]), ("stopword", a["stopwords"])) if entries]
            if asked and by_place and all(hits[k] for k in asked):
                return " and ".join(asked)
        else:
            for how in ("regex", "stopword"):
                if hits[how]:
                    return how
    return ""


def _stands_alone(value: str, text: str) -> bool:
    """`value` in `text` with no letter, digit or underscore either side: the value itself, not part of a longer one."""
    return bool(value) and re.search(r"(?<![A-Za-z0-9_])" + re.escape(value) + r"(?![A-Za-z0-9_])", text or "") is not None


def _history(repo: str, paths: list, *extra) -> list:
    """[(commit, path)] for each commit of HEAD's history that changed one of `paths`, oldest first."""
    if not paths:
        return []
    proc = subprocess.run(["git", "-C", repo, "log", "--reverse", "--format=%x00%H", "--name-only", *extra, "HEAD", "--", *paths],
                          capture_output=True)
    if proc.returncode != 0:
        return []
    wanted, out = set(paths), []
    for chunk in proc.stdout.decode("utf-8", "surrogateescape").split("\x00")[1:]:
        lines = [l for l in chunk.split("\n") if l]
        out += [(lines[0], p) for p in lines[1:] if p in wanted]
    return out


def _blobs(repo: str, specs: list):
    """Yield (spec, text or None) for each `rev:path`, from one `git cat-file --batch` read object by object."""
    if not specs:
        return
    proc = subprocess.Popen(["git", "-C", repo, "cat-file", "--batch"], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    try:
        for spec in specs:
            proc.stdin.write(spec.encode("utf-8", "surrogateescape") + b"\n")
            proc.stdin.flush()
            header = proc.stdout.readline().split()
            if len(header) != 3 or header[1] != b"blob":
                if len(header) == 3:   # a tree or a commit: skip its body
                    proc.stdout.read(int(header[2]) + 1)
                yield spec, None
                continue
            data = proc.stdout.read(int(header[2]) + 1)[:-1]
            yield spec, data.decode("utf-8", "surrogateescape")
    finally:
        proc.stdin.close()
        proc.stdout.close()
        proc.wait()


def annotate(repo: str, rows: list) -> None:
    """What the clone says about each row, read while the value is in memory and written as neither the
    value nor anything derived from it.

    `Declared`, when the repository declared the value allowed at some commit of HEAD's history: an
    allowlist regex or stopword of a .gitleaks.toml or .betterleaks.toml matches it, it stands on its own
    in a .gitleaksignore or .betterleaksignore (or the row's fingerprint is listed there), or a version of
    its file carries it on a line marked gitleaks:allow. {File, Commit, How}: the first declaration."""
    if not rows:
        return
    versions = _history(repo, list(CONFIGS))
    configs = []   # (commit, path, allowlists or None, text), oldest first
    for (commit, path), (_, text) in zip(versions, _blobs(repo, [f"{c}:{p}" for c, p in versions])):
        if text is not None:
            configs.append((commit, path, allowlists(text) if path.endswith(".toml") else None, text))
    located = sorted({r.get("File") or "" for r in rows if r.get("Commit") and r.get("File")})
    # the versions of each file that added or removed a marked line, the only ones that can hold one. Finding
    # them diffs every version of every file named (15 s on yt-dlp's 118), so only in a repository that uses
    # the markers today or has had a config: one that removed its every marker and never had a config is missed.
    uses = bool(configs) or subprocess.run(["git", "-C", repo, "grep", "-q", "-I", "-F", "leaks:allow", "HEAD", "--"],
                                           capture_output=True).returncode == 0
    marked = _history(repo, located, "-Gleaks:allow") if located and uses else []
    marker_lines = {}   # path -> [(commit, marked line)]
    for (commit, path), (_, text) in zip(marked, _blobs(repo, [f"{c}:{p}" for c, p in marked])):
        for l in (text or "").split("\n"):
            if any(m in l for m in ALLOW_MARKERS):
                marker_lines.setdefault(path, []).append((commit, l))
    for r in rows:
        value, path = r.get("Secret") or "", r.get("File") or ""
        if not value:
            continue
        declared = None
        for commit, cfg, lists, text in configs:
            if lists is not None:
                how = _allowed_by(lists, r)
                how = f"allowlist {how}" if how else ""
            else:
                ignored = [l.strip() for l in text.split("\n") if l.strip() and not l.lstrip().startswith("#")]
                how = ("fingerprint" if r.get("Fingerprint") and r["Fingerprint"] in ignored
                       else "literal" if any(_stands_alone(value, l) for l in ignored) else "")
            if how:
                declared = {"File": cfg, "Commit": commit, "How": how}
                break
        if declared is None:
            hit = next(((c, l) for c, l in marker_lines.get(path, []) if value in l), None)
            if hit:
                declared = {"File": path, "Commit": hit[0], "How": next(m for m in ALLOW_MARKERS if m in hit[1])}
        if declared:
            r["Declared"] = declared


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
        clean["Placeholder"] = is_placeholder(value, r.get("Line") or "", r.get("File") or "", str(r.get("RuleID") or ""))   # read here and dropped with the other raw fields
        out.append(clean)
    return out


CONFIDENCE = {"low": 0, "medium": 1, "high": 2}
_ONE_WORD = re.compile(r"[a-z]{3,20}|[A-Z]{3,20}")


def group(rows: list) -> list:
    """One entry per distinct secret value (placeholders left out): its rule, the files and commits it
    appears in, the number of distinct places (commit, file, line), whether every place is a test
    file, whether every place is a documentation file, and the repository's declaration of it, if any. The strongest come first, since a finding
    names the first three: the scanner's highest grade, then a provider's rule before a generic one,
    then values that appear in source, then the most widespread (devlake's critical led with a form
    label's `password: 'Enter Password'` and never named the GitHub token graded high)."""
    groups, order = {}, []
    for i, r in enumerate(rows):
        if r.get("placeholder"):
            continue
        key = r.get("value") or ("row", i)
        if key not in groups:
            groups[key] = {"value": r.get("value"), "rule": r["rule"], "files": [], "commits": [], "_places": set(), "test": True, "docs": True,
                           "confidence": None, "declared": None}
            order.append(key)
        g = groups[key]
        if r["file"] not in g["files"]:
            g["files"].append(r["file"])
        if r["commit"] not in g["commits"]:
            g["commits"].append(r["commit"])
        g["_places"].add((r["commit"], r["file"], r.get("line")))
        if CONFIDENCE.get(r.get("confidence"), -1) > CONFIDENCE.get(g["confidence"], -1):   # the scanner's highest grade for the value
            g["confidence"] = r.get("confidence")
        if r.get("declared") and not g["declared"]:   # the value is one: a declaration of it anywhere covers every place
            g["declared"] = r["declared"]
        g["test"] = g["test"] and filetypes.is_test_path(r["file"])
        g["docs"] = g["docs"] and filetypes.is_doc_path(r["file"])
    out = []
    for key in order:
        g = groups[key]
        places = g.pop("_places")
        out.append({**g, "places": len(places)})
    out.sort(key=lambda g: (-CONFIDENCE.get(g["confidence"], -1), str(g["rule"]).startswith("generic-"), g["test"], -g["places"]))   # stable: first-seen order breaks ties
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
    read_lines(os.getcwd(), raw)   # betterleaks does not report the line; the clone in the current directory has it
    found = unreachable(os.getcwd())
    extra = scan_unreachable(os.getcwd(), os.path.dirname(os.path.abspath(target)), found) if found else []
    annotate(os.getcwd(), raw + extra)   # before sanitise drops the values
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

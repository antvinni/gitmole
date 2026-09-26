"""gitmole --install-tools: the pinned tools, downloaded from the archives Formula/gitmole.rb names, checked
against the same sha256, and placed one executable each in a directory of gitmole's own per tool and pin
(userdirs.tool_dir), which run.env_path puts first on PATH. It runs only on that flag or on a yes to the
question a first run asks a person at a terminal; it is the only download gitmole makes of its own. The
network is otherwise reached to clone a remote target (run.clone), to list owner/* with gh, and by git itself
when a partial clone lacks objects a step reads."""
from __future__ import annotations

import contextlib
import hashlib
import http.client
import io
import os
import platform
import ssl
import sys
import tarfile
import tempfile
import urllib.error
import urllib.parse
import urllib.request
import zipfile

from . import run, tools, userdirs

TIMEOUT = 60   # seconds one download may take to connect, or to send its next bytes

# what platform.machine() says on the systems the formula covers -> the cpu name tools.ARCHIVES keys on
_CPUS = {"arm64": "arm64", "aarch64": "arm64", "x86_64": "x86_64", "amd64": "x86_64"}

# A GitHub release download is a redirect to a second host, which the question names too: behind an allowlist
# the user must admit both. What github.com answered on 26 Sep 2026; fetch() names the host it was sent to
# whenever a download fails, so a change here shows itself in the error.
REDIRECT_HOSTS = {"github.com": "release-assets.githubusercontent.com"}

# macOS keeps its root certificates here; a python.org Python has none of its own until the user runs its
# "Install Certificates.command", and then every download fails to verify.
_MACOS_CA_FILE = "/etc/ssl/cert.pem"


class InstallError(Exception):
    """One tool could not be installed; the message names the cause, and the url when there was one."""


def _musl() -> bool:
    """Whether this Linux's C library is musl (Alpine), where a glibc build cannot start."""
    try:
        return not (os.confstr("CS_GNU_LIBC_VERSION") or "").startswith("glibc")
    except (ValueError, OSError, AttributeError):   # the name is unknown outside glibc
        return True


def platform_key(system: str = None, machine: str = None, musl: bool = None) -> tuple:
    """(system, cpu) as tools.ARCHIVES keys it: the system lower-cased, "linux-musl" for a musl Linux, and the
    cpu as the formula names it (arm64 for aarch64, x86_64 for amd64), or passed through when it is neither."""
    system = (system or platform.system()).lower()
    machine = machine or platform.machine()
    if system == "linux" and (_musl() if musl is None else musl):
        system = "linux-musl"
    return system, _CPUS.get(machine.lower(), machine.lower())


def tools_dir() -> str | None:
    """The directory the tools go under (userdirs.tools_root), or None when there is no absolute one."""
    return userdirs.tools_root()


def downloadable(names: list, key: tuple = None) -> list:
    """The names the table has an archive for on this platform, in the order given."""
    per_tool = tools.ARCHIVES.get(platform_key() if key is None else key, {})
    return [n for n in names if "url" in per_tool.get(n, {})]


def hosts(names: list, key: tuple = None) -> list:
    """Every host the downloads of these tools reach, sorted: the table's, and where each redirects."""
    per_tool = tools.ARCHIVES.get(platform_key() if key is None else key, {})
    named = {urllib.parse.urlparse(per_tool[n]["url"]).netloc for n in names if "url" in per_tool.get(n, {})}
    return sorted(named | {REDIRECT_HOSTS[h] for h in named if h in REDIRECT_HOSTS})


def offer(names: list, dest: str = None, key: tuple = None) -> str:
    """The question a first run asks a person: which versions, from which hosts, into which directory."""
    dest = tools_dir() if dest is None else dest
    versions = ", ".join(f"{n} {tools.PINNED[n]}" for n in names)
    return f"Download the pinned {versions} from {', '.join(hosts(names, key))} into {dest}? [y/N] "


class _Redirects(urllib.request.HTTPRedirectHandler):
    """Remembers the last url a download was sent on to, so a failure can name the host that failed."""

    def __init__(self):
        super().__init__()
        self.last = None

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        self.last = newurl
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _context() -> ssl.SSLContext:
    """The default context, with macOS's own roots added when this Python has none (a python.org build
    before Install Certificates.command); SSL_CERT_FILE, when set, is left to decide alone."""
    context = ssl.create_default_context()
    if sys.platform == "darwin" and not os.environ.get("SSL_CERT_FILE") and not context.get_ca_certs() \
            and os.path.isfile(_MACOS_CA_FILE):
        context.load_verify_locations(_MACOS_CA_FILE)
    return context


def _opener(redirects: _Redirects):
    return urllib.request.build_opener(redirects, urllib.request.HTTPSHandler(context=_context()))


def fetch(url: str) -> bytes:
    """The bytes at url, following redirects (a GitHub release download is one), or InstallError. A body cut
    short or a garbled response is an http.client.HTTPException, not an OSError, and is caught with them."""
    request = urllib.request.Request(url, headers={"User-Agent": "gitmole"})
    redirects = _Redirects()
    try:
        with _opener(redirects).open(request, timeout=TIMEOUT) as response:
            return response.read()
    except (urllib.error.URLError, OSError, http.client.HTTPException) as e:
        via = f" (sent on to {urllib.parse.urlparse(redirects.last).netloc})" if redirects.last else ""
        raise InstallError(f"{url}{via}: {e or type(e).__name__}") from e


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def pick(names: list, tool: str) -> str | None:
    """The archive member that is the tool, found as the formula finds it. Homebrew steps into an archive's
    one top-level directory (jscpd's npm package/), then takes the first file of `tool`, `bin/tool`, and the
    `tool_*` names at that level, sorted (osv-scanner ships a bare osv-scanner_darwin_arm64). Nothing
    deeper is searched and a directory is never a candidate."""
    files = [n for n in names if not n.endswith("/")]
    tops = {n.split("/", 1)[0] for n in files}
    if len(tops) == 1 and all("/" in n for n in files):
        inside = {n.split("/", 1)[1]: n for n in files}
    else:
        inside = {n: n for n in files}
    for wanted in (tool, f"bin/{tool}"):
        if wanted in inside:
            return inside[wanted]
    prefixed = sorted(n for n in inside if "/" not in n and n.startswith(tool + "_"))
    return inside[prefixed[0]] if prefixed else None


def unpack(data: bytes, url: str, tool: str) -> bytes:
    """The tool's executable out of what url served: a .tar.gz or .tgz, a .zip, or the bare binary itself.
    The member is read into memory and nothing is extracted, so no path inside an archive ever names a file
    on this disk (and tarfile's extraction filter, absent before 3.12, is not needed)."""
    name = os.path.basename(urllib.parse.urlparse(url).path)
    if name.endswith((".tar.gz", ".tgz")):
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tar:
            members = {m.name: m for m in tar.getmembers() if m.isfile()}
            chosen = pick(list(members), tool)
            if chosen is None:
                raise InstallError(f"{url}: no {tool} executable in the archive ({', '.join(sorted(members)) or 'empty'})")
            return tar.extractfile(members[chosen]).read()
    if name.endswith(".zip"):
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            files = [n for n in archive.namelist() if not n.endswith("/")]
            chosen = pick(files, tool)
            if chosen is None:
                raise InstallError(f"{url}: no {tool} executable in the archive ({', '.join(sorted(files)) or 'empty'})")
            return archive.read(chosen)
    if pick([name], tool) is None:
        raise InstallError(f"{url}: not an archive, and not named like {tool}")
    return data


def place(data: bytes, dest: str, tool: str) -> str:
    """Write the executable as dest/tool, mode 755, through a temporary file of its own so an interrupted
    write leaves nothing under the tool's name and two installs at once never share one; a tool already
    there is replaced whole, by rename."""
    os.makedirs(dest, exist_ok=True)
    final = os.path.join(dest, tool)
    fd, partial = tempfile.mkstemp(dir=dest, prefix=f".{tool}.")
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
        os.chmod(partial, 0o755)
        os.replace(partial, final)
    finally:
        if os.path.exists(partial):
            os.remove(partial)
    return final


def check(path: str, tool: str) -> None:
    """InstallError, and the copy removed, unless the placed executable runs and prints its pin: a build for
    another C library or CPU is refused here rather than failing every run after it."""
    found = run.printed_version(path)
    if found == tools.PINNED[tool]:
        return
    os.remove(path)
    with contextlib.suppress(OSError):   # the <tool>-<pin> directory, empty again; a directory on PATH should hold its tool
        os.rmdir(os.path.dirname(path))
    said = f"prints version {found}" if found else "does not run here, or prints no version"
    raise InstallError(f"{path} {said}, not the pinned {tools.PINNED[tool]}; removed")


def writable(dest: str | None) -> str | None:
    """Why nothing can be installed under dest, or None when a file can be written there: asked once,
    before any download, so an unwritable directory costs no 80 MB to find out."""
    if dest is None:
        return ("no directory to install into: GITMOLE_TOOLS must be an absolute path, "
                "and without it the home directory must be known")
    try:
        os.makedirs(dest, exist_ok=True)
        fd, probe = tempfile.mkstemp(dir=dest, prefix=".gitmole-write-check.")
        os.close(fd)
        os.remove(probe)
    except OSError as e:
        return f"cannot write to {dest}: {e}"
    return None


def install(names: list, dest: str = None, key: tuple = None, fetcher=fetch, say=print, checker=check) -> list:
    """Download, verify, place and run each named tool, saying one line per step; the names that landed, in
    order. Each goes into dest/<tool>-<pin>. A tool that fails (no build for this platform, a network error,
    a hash mismatch, an archive without it, a copy that does not run) is said and skipped with nothing of it
    left, and the rest still install. A destination that cannot be written stops everything first."""
    dest = tools_dir() if dest is None else dest
    key = platform_key() if key is None else key
    problem = writable(dest)
    if problem:
        say(problem)
        return []
    per_tool = tools.ARCHIVES.get(key, {})
    done = []
    for name in names:
        entry = per_tool.get(name)
        if entry is None or "url" not in entry:
            why = f"no pinned build for {key[0]} {key[1]}" if entry is None else entry["note"]
            say(f"{name}: {why}; see {tools.RELEASES[name]}")
            continue
        say(f"{name}: downloading {entry['url']}")
        try:
            data = fetcher(entry["url"])
            found = digest(data)
            if found != entry["sha256"]:
                raise InstallError(f"{entry['url']}: sha256 {found}, expected {entry['sha256']}; nothing written")
            try:
                executable = unpack(data, entry["url"], name)
            except (tarfile.TarError, zipfile.BadZipFile, EOFError) as e:
                raise InstallError(f"{entry['url']}: cannot unpack: {e}") from e
            path = place(executable, os.path.join(dest, f"{name}-{tools.PINNED[name]}"), name)
            checker(path, name)
        except (InstallError, OSError) as e:
            say(f"{name}: {e}")
            continue
        say(f"{name}: installed {path} ({tools.PINNED[name]})")
        done.append(name)
    return done

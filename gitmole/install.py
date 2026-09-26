"""gitmole --install-tools: the pinned tools, downloaded from the archives Formula/gitmole.rb names, checked
against the same sha256, and placed one executable each in a directory of gitmole's own, which run.env_path
puts first on PATH. This is the one place gitmole fetches anything, and it runs only on that flag or on a yes
to the question a first run asks on a terminal: a scan itself never reaches the network."""
from __future__ import annotations

import hashlib
import io
import os
import platform
import sys
import tarfile
import urllib.error
import urllib.parse
import urllib.request
import zipfile

from . import tools

TIMEOUT = 60   # seconds one download may take to connect, or to send its next bytes

# what platform.machine() says on the systems the formula covers -> the cpu name tools.ARCHIVES keys on
_CPUS = {"arm64": "arm64", "aarch64": "arm64", "x86_64": "x86_64", "amd64": "x86_64"}


class InstallError(Exception):
    """One tool could not be installed; the message names the cause, and the url when there was one."""


def platform_key(system: str = None, machine: str = None) -> tuple:
    """(system, cpu) as tools.ARCHIVES keys it: the system lower-cased, the cpu as the formula names it
    (arm64 for aarch64, x86_64 for amd64), or passed through when it is neither."""
    system = (system or platform.system()).lower()
    machine = machine or platform.machine()
    return system, _CPUS.get(machine.lower(), machine.lower())


def tools_dir(env=None) -> str:
    """Where the installer puts the tools: GITMOLE_TOOLS, else the per-user data directory of the platform,
    as structure.cache_root does for the cache. A directory of gitmole's own, not ~/.local/bin: nothing here
    shadows a tool the user installed themselves anywhere but inside a gitmole run."""
    env = os.environ if env is None else env
    explicit = env.get("GITMOLE_TOOLS")
    if explicit:
        return explicit
    if sys.platform == "darwin":
        base = os.path.expanduser("~/Library/Application Support")
    else:
        base = env.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share")
    return os.path.join(base, "gitmole", "tools")


def downloadable(names: list, key: tuple = None) -> list:
    """The names the table has an archive for on this platform, in the order given."""
    per_tool = tools.ARCHIVES.get(platform_key() if key is None else key, {})
    return [n for n in names if "url" in per_tool.get(n, {})]


def offer(names: list, dest: str = None, key: tuple = None) -> str:
    """The question a first run asks on a terminal: which versions, from which hosts, into which directory."""
    dest = tools_dir() if dest is None else dest
    per_tool = tools.ARCHIVES.get(platform_key() if key is None else key, {})
    hosts = sorted({urllib.parse.urlparse(per_tool[n]["url"]).netloc for n in names if "url" in per_tool.get(n, {})})
    versions = ", ".join(f"{n} {tools.PINNED[n]}" for n in names)
    return f"Download the pinned {versions} from {', '.join(hosts)} into {dest}? [y/N] "


def fetch(url: str) -> bytes:
    """The bytes at url, following redirects (a GitHub release download is one), or InstallError."""
    request = urllib.request.Request(url, headers={"User-Agent": "gitmole"})
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
            return response.read()
    except (urllib.error.URLError, OSError) as e:   # URLError is an OSError; both named so the intent reads
        raise InstallError(f"{url}: {e}") from e


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def pick(names: list, tool: str) -> str | None:
    """The archive member that is the tool, the formula's search in Python: a file named `tool` (at the root
    of scc's, betterleaks' and git-sizer's archives; under package/bin/ in jscpd's npm tarball), else the one
    file whose name starts with `tool_` (osv-scanner ships a bare osv-scanner_darwin_arm64). The shallowest
    exact name wins; a directory is never a candidate; two prefixed files is an ambiguity, so None."""
    files = [n for n in names if not n.endswith("/")]
    exact = [n for n in files if os.path.basename(n) == tool]
    if exact:
        return sorted(exact, key=lambda n: (n.count("/"), n))[0]
    prefixed = [n for n in files if os.path.basename(n).startswith(tool + "_")]
    return prefixed[0] if len(prefixed) == 1 else None


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
    """Write the executable as dest/tool, mode 755, through a temporary name so an interrupted write leaves
    nothing half-written under the tool's name; a tool already there is replaced."""
    os.makedirs(dest, exist_ok=True)
    final = os.path.join(dest, tool)
    partial = os.path.join(dest, f".{tool}.partial")
    try:
        with open(partial, "wb") as fh:
            fh.write(data)
        os.chmod(partial, 0o755)
        os.replace(partial, final)
    finally:
        if os.path.exists(partial):
            os.remove(partial)
    return final


def install(names: list, dest: str = None, key: tuple = None, fetcher=fetch, say=print) -> list:
    """Download, verify and place each named tool, saying one line per step; the names that landed, in
    order. A tool that fails (no build for this platform, a network error, a hash mismatch, an archive
    without it) is said and skipped with nothing of it written, and the rest still install."""
    dest = tools_dir() if dest is None else dest
    key = platform_key() if key is None else key
    per_tool = tools.ARCHIVES.get(key, {})
    done = []
    for name in names:
        entry = per_tool.get(name)
        try:
            if entry is None:
                raise InstallError(f"no pinned build for {key[0]} {key[1]}; see {tools.RELEASES[name]}")
            if "url" not in entry:
                raise InstallError(f"{entry['note']}; see {tools.RELEASES[name]}")
            say(f"{name}: downloading {entry['url']}")
            data = fetcher(entry["url"])
            found = digest(data)
            if found != entry["sha256"]:
                raise InstallError(f"{entry['url']}: sha256 {found}, expected {entry['sha256']}; nothing written")
            try:
                executable = unpack(data, entry["url"], name)
            except (tarfile.TarError, zipfile.BadZipFile, EOFError) as e:
                raise InstallError(f"{entry['url']}: cannot unpack: {e}") from e
            path = place(executable, dest, name)
        except (InstallError, OSError) as e:
            say(f"{name}: {e}")
            continue
        say(f"{name}: installed {path} ({tools.PINNED[name]})")
        done.append(name)
    return done

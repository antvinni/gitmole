import http.client
import io
import os
import tarfile
import tempfile
import unittest
import zipfile
from unittest import mock

from gitmole import install, run, tools, userdirs

KEY = ("test", "cpu")   # a platform of its own, so the tests never touch the real table's urls


def placed(dest: str, name: str) -> str:
    return os.path.join(dest, f"{name}-{tools.PINNED[name]}", name)
FAKE_BIN = {name: f"#!/bin/sh\necho {name} version {tools.PINNED[name]}\n".encode() for name in run.REQUIRED_TOOLS}


def tar_gz(files: dict) -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for path, data in files.items():
            info = tarfile.TarInfo(path)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
    return buf.getvalue()


def zipped(files: dict) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as archive:
        for path, data in files.items():
            archive.writestr(path, data)
    return buf.getvalue()


def archives() -> dict:
    """url -> bytes, in the shapes the real releases have (see the plan's Background)."""
    return {
        "https://example.test/scc_Test_cpu.tar.gz": tar_gz({"LICENSE": b"mit", "README.md": b"#", "scc": FAKE_BIN["scc"]}),
        "https://example.test/git-sizer-1.5.0-test-cpu.zip": zipped({"LICENSE.md": b"mit", "git-sizer": FAKE_BIN["git-sizer"]}),
        "https://example.test/betterleaks_1.8.1_test_cpu.tar.gz": tar_gz({"LICENSE": b"mit", "betterleaks": FAKE_BIN["betterleaks"]}),
        "https://example.test/osv-scanner_test_cpu": FAKE_BIN["osv-scanner"],
        "https://registry.example.test/jscpd-test-cpu/-/jscpd-test-cpu-5.3.0.tgz": tar_gz(
            {"package/bin/jscpd": FAKE_BIN["jscpd"], "package/LICENSE": b"mit", "package/package.json": b"{}"}),
    }


def table(served: dict) -> dict:
    """tools.ARCHIVES[KEY] for the served archives, hashes computed from the bytes."""
    by_tool = {"scc": "scc_Test_cpu.tar.gz", "git-sizer": "git-sizer-1.5.0-test-cpu.zip", "betterleaks": "betterleaks_1.8.1_test_cpu.tar.gz",
               "osv-scanner": "osv-scanner_test_cpu", "jscpd": "jscpd-test-cpu-5.3.0.tgz"}
    out = {}
    for name, tail in by_tool.items():
        url = next(u for u in served if u.endswith(tail))
        out[name] = {"url": url, "sha256": install.digest(served[url])}
    return out


class Fetcher:
    def __init__(self, served: dict, failing: set = ()):
        self.served, self.failing, self.calls = served, set(failing), []

    def __call__(self, url: str) -> bytes:
        self.calls.append(url)
        if url in self.failing:
            raise install.InstallError(f"{url}: <urlopen error [Errno 8] nodename nor servname provided>")
        return self.served[url]


class Platform(unittest.TestCase):
    def test_platform_key_normalises_the_cpu_names_the_two_systems_use(self):
        self.assertEqual(install.platform_key("Darwin", "arm64"), ("darwin", "arm64"))
        self.assertEqual(install.platform_key("Darwin", "x86_64"), ("darwin", "x86_64"))
        self.assertEqual(install.platform_key("Linux", "aarch64", musl=False), ("linux", "arm64"))
        self.assertEqual(install.platform_key("Linux", "x86_64", musl=False), ("linux", "x86_64"))
        self.assertEqual(install.platform_key("Linux", "AMD64", musl=False), ("linux", "x86_64"))
        self.assertEqual(install.platform_key("Linux", "x86_64", musl=True), ("linux-musl", "x86_64"), "Alpine")
        self.assertEqual(install.platform_key("Darwin", "arm64", musl=True), ("darwin", "arm64"), "musl means nothing off Linux")
        self.assertEqual(install.platform_key("Windows", "ARM64"), ("windows", "arm64"))
        self.assertEqual(install.platform_key("Linux", "riscv64", musl=False), ("linux", "riscv64"), "an unknown cpu passes through")
        system, cpu = install.platform_key()
        self.assertEqual(system, system.lower())

    def test_tools_root_honours_the_override_and_ends_in_gitmole_tools(self):
        self.assertEqual(userdirs.tools_root({"GITMOLE_TOOLS": "/somewhere/tools"}), "/somewhere/tools")
        default = userdirs.tools_root({})
        self.assertTrue(default.endswith(os.path.join("gitmole", "tools")), default)
        self.assertTrue(os.path.isabs(default))
        self.assertEqual(userdirs.tools_root({"GITMOLE_TOOLS": ""}), default, "an empty override is no override")
        self.assertTrue(os.path.isabs(userdirs.tools_root({"XDG_DATA_HOME": "relative"})), "a relative XDG_DATA_HOME is ignored, as the spec says")

    def test_a_tool_root_is_absolute_or_none_never_inside_the_scanned_repository(self):
        """A relative root would resolve against the cwd a step runs in, the scanned repository, and put the
        repository's own executables first on PATH."""
        self.assertIsNone(userdirs.tools_root({"GITMOLE_TOOLS": "relative/tools"}), "refused, not resolved against the cwd")
        self.assertIsNone(userdirs.tools_root({"GITMOLE_TOOLS": "bin"}))
        home = os.path.expanduser("~")
        self.assertEqual(userdirs.tools_root({"GITMOLE_TOOLS": "~/.local/share/gitmole/tools"}),
                         os.path.join(home, ".local", "share", "gitmole", "tools"), "a literal ~ from YAML or a Dockerfile is expanded")
        with mock.patch("os.path.expanduser", side_effect=lambda p: p):   # no HOME and no passwd entry
            self.assertIsNone(userdirs.tools_root({}))
            self.assertIsNone(userdirs.tool_dir("scc", {}))
            self.assertEqual(userdirs.tool_dirs(["scc"]), [])

    def test_each_tool_has_a_directory_per_pin(self):
        self.assertEqual(userdirs.tool_dir("scc", {"GITMOLE_TOOLS": "/t"}), f"/t/scc-{tools.PINNED['scc']}")

    def test_downloadable_is_the_subset_the_table_has_a_url_for(self):
        with mock.patch.dict(tools.ARCHIVES, {KEY: {**table(archives()), "git-sizer": {"note": "none"}}}):
            self.assertEqual(install.downloadable(["scc", "git-sizer", "jscpd"], key=KEY), ["scc", "jscpd"])
        self.assertEqual(install.downloadable(["scc"], key=("nowhere", "cpu")), [])
        self.assertEqual(install.downloadable(["git-sizer"], key=("linux", "arm64")), [])
        self.assertEqual(install.downloadable(["git-sizer"], key=("linux", "x86_64")), ["git-sizer"])


class Pick(unittest.TestCase):
    def test_the_root_executable_then_bin_then_the_prefixed_bare_name(self):
        self.assertEqual(install.pick(["LICENSE", "README.md", "scc"], "scc"), "scc")
        self.assertEqual(install.pick(["package/bin/jscpd", "package/LICENSE", "package/package.json"], "jscpd"), "package/bin/jscpd")
        self.assertEqual(install.pick(["osv-scanner_darwin_arm64"], "osv-scanner"), "osv-scanner_darwin_arm64")
        self.assertEqual(install.pick(["deep/scc", "scc"], "scc"), "scc", "the shallowest exact name wins")
        self.assertIsNone(install.pick(["LICENSE", "README.md"], "scc"))
        self.assertIsNone(install.pick(["scc/", "LICENSE"], "scc"), "a directory is not the tool")
        self.assertEqual(install.pick(["scc_b", "scc_a"], "scc"), "scc_a", "the first prefixed name, sorted, as the formula's Dir[] takes it")

    def test_it_looks_where_the_formula_looks_and_nowhere_deeper(self):
        """Homebrew steps into an archive's one top-level directory, then tries tool, bin/tool, tool_*."""
        self.assertEqual(install.pick(["scc-4.1.0/scc", "scc-4.1.0/LICENSE"], "scc"), "scc-4.1.0/scc", "one top directory is stepped into")
        self.assertIsNone(install.pick(["a/b/scc", "LICENSE"], "scc"), "the formula does not search a/b/")
        self.assertEqual(install.pick(["bin/scc", "scc"], "scc"), "scc", "tool before bin/tool")
        self.assertIsNone(install.pick(["docs/scc_notes/x"], "scc"), "a tool_ prefix counts at the top level only")


class Install(unittest.TestCase):
    def test_each_archive_shape_yields_one_executable_at_its_name(self):
        served = archives()
        fetcher = Fetcher(served)
        said = []
        with tempfile.TemporaryDirectory() as d, mock.patch.dict(tools.ARCHIVES, {KEY: table(served)}):
            dest = os.path.join(d, "tools")
            done = install.install(run.REQUIRED_TOOLS, dest=dest, key=KEY, fetcher=fetcher, say=said.append)
            self.assertEqual(done, run.REQUIRED_TOOLS)
            self.assertEqual(sorted(os.listdir(dest)), sorted(f"{n}-{tools.PINNED[n]}" for n in run.REQUIRED_TOOLS), "a directory per tool and pin")
            for name in run.REQUIRED_TOOLS:
                path = placed(dest, name)
                self.assertEqual(os.listdir(os.path.dirname(path)), [name], "one file, no partials, no LICENSE")
                with open(path, "rb") as fh:
                    self.assertEqual(fh.read(), FAKE_BIN[name], name)
                self.assertTrue(os.access(path, os.X_OK), name)
                self.assertTrue(run.has_tool(name, path=os.path.dirname(path)), f"{name} is found on a PATH holding only its directory")
        self.assertEqual(len(fetcher.calls), 5)
        self.assertEqual(sum(1 for l in said if ": downloading https://" in l), 5)
        self.assertEqual(sum(1 for l in said if ": installed " in l and tools.PINNED["scc"] in l), 1, "each installed line names the pin")

    def test_a_hash_mismatch_writes_nothing_and_the_rest_still_install(self):
        served = archives()
        wrong = table(served)
        wrong["scc"] = {**wrong["scc"], "sha256": "0" * 64}
        said = []
        with tempfile.TemporaryDirectory() as d, mock.patch.dict(tools.ARCHIVES, {KEY: wrong}):
            done = install.install(["scc", "jscpd"], dest=d, key=KEY, fetcher=Fetcher(served), say=said.append)
            self.assertEqual(done, ["jscpd"])
            self.assertEqual(os.listdir(d), [f"jscpd-{tools.PINNED['jscpd']}"])
        line = [l for l in said if l.startswith("scc: ")][-1]   # after "scc: downloading ..." comes the verdict
        self.assertIn("sha256", line)
        self.assertIn("expected " + "0" * 64, line)
        self.assertIn("nothing written", line)

    def test_a_network_error_is_said_with_its_url_and_the_rest_still_install(self):
        served = archives()
        url = next(u for u in served if "betterleaks" in u)
        said = []
        with tempfile.TemporaryDirectory() as d, mock.patch.dict(tools.ARCHIVES, {KEY: table(served)}):
            done = install.install(["betterleaks", "scc"], dest=d, key=KEY, fetcher=Fetcher(served, failing={url}), say=said.append)
            self.assertEqual(done, ["scc"])
            self.assertEqual(os.listdir(d), [f"scc-{tools.PINNED['scc']}"])
        self.assertTrue(any(l.startswith("betterleaks: ") and url in l and "nodename" in l for l in said), said)

    def test_a_tool_upstream_does_not_build_is_said_not_fetched(self):
        fetcher = Fetcher({})
        said = []
        with tempfile.TemporaryDirectory() as d:
            done = install.install(["git-sizer"], dest=d, key=("linux", "arm64"), fetcher=fetcher, say=said.append)
            self.assertEqual(done, [])
            self.assertEqual(os.listdir(d), [], "the directory is made but holds nothing")
        self.assertEqual(fetcher.calls, [])
        self.assertIn("no Linux arm64 build", said[0])
        self.assertIn(f'go install -ldflags "-X main.ReleaseVersion={tools.PINNED["git-sizer"]}" '
                      f'github.com/github/git-sizer@v{tools.PINNED["git-sizer"]}', said[0], "the version is set, or the build prints none")
        self.assertIn(tools.RELEASES["git-sizer"], said[0])

    def test_an_unknown_platform_installs_nothing_and_says_which_platform(self):
        fetcher = Fetcher({})
        said = []
        with tempfile.TemporaryDirectory() as d:
            done = install.install(["scc", "jscpd"], dest=d, key=("windows", "x86_64"), fetcher=fetcher, say=said.append)
        self.assertEqual(done, [])
        self.assertEqual(fetcher.calls, [])
        self.assertEqual(len(said), 2)
        self.assertIn("no pinned build for windows x86_64", said[0])
        self.assertIn(tools.RELEASES["scc"], said[0])

    def test_an_archive_without_the_tool_or_not_an_archive_at_all_is_refused(self):
        served = {"https://example.test/scc_Test_cpu.tar.gz": tar_gz({"LICENSE": b"mit"}),
                  "https://example.test/git-sizer-1.5.0-test-cpu.zip": b"not a zip",
                  "https://example.test/jscpd-test-cpu-5.3.0.tgz": b"not gzip either"}
        entries = {name: {"url": url, "sha256": install.digest(data)}
                   for name, (url, data) in zip(["scc", "git-sizer", "jscpd"], served.items())}
        said = []
        with tempfile.TemporaryDirectory() as d, mock.patch.dict(tools.ARCHIVES, {KEY: entries}):
            done = install.install(["scc", "git-sizer", "jscpd"], dest=d, key=KEY, fetcher=Fetcher(served), say=said.append)
            self.assertEqual(done, [])
            self.assertEqual(os.listdir(d), [])
        self.assertIn("no scc executable in the archive", " ".join(said))
        self.assertIn("LICENSE", " ".join(said), "what the archive did hold is named")
        self.assertIn("git-sizer: https://example.test/git-sizer-1.5.0-test-cpu.zip: cannot unpack", " ".join(said))
        self.assertIn("jscpd: https://example.test/jscpd-test-cpu-5.3.0.tgz: cannot unpack", " ".join(said))

    def test_a_tool_already_there_is_replaced_not_appended_to(self):
        served = archives()
        with tempfile.TemporaryDirectory() as d, mock.patch.dict(tools.ARCHIVES, {KEY: table(served)}):
            os.makedirs(os.path.dirname(placed(d, "scc")))
            with open(placed(d, "scc"), "wb") as fh:
                fh.write(b"an older scc, much longer than the new one " * 10)
            install.install(["scc"], dest=d, key=KEY, fetcher=Fetcher(served), say=lambda line: None)
            with open(placed(d, "scc"), "rb") as fh:
                self.assertEqual(fh.read(), FAKE_BIN["scc"])
            self.assertEqual(os.listdir(os.path.dirname(placed(d, "scc"))), ["scc"])

    def test_the_default_destination_is_the_tool_directory(self):
        served = archives()
        with tempfile.TemporaryDirectory() as d, mock.patch.dict(tools.ARCHIVES, {KEY: table(served)}), \
                mock.patch.dict(os.environ, {"GITMOLE_TOOLS": os.path.join(d, "own")}):
            install.install(["scc"], key=KEY, fetcher=Fetcher(served), say=lambda line: None)
            self.assertTrue(os.path.isfile(placed(os.path.join(d, "own"), "scc")))

    def test_an_unwritable_destination_is_said_once_before_any_download(self):
        """Finding out after the whole 76 MB set was fetched is the cost this saves."""
        served = archives()
        fetcher = Fetcher(served)
        said = []
        with tempfile.TemporaryDirectory() as d, mock.patch.dict(tools.ARCHIVES, {KEY: table(served)}):
            blocker = os.path.join(d, "a-file")
            open(blocker, "w").close()
            done = install.install(run.REQUIRED_TOOLS, dest=os.path.join(blocker, "tools"), key=KEY, fetcher=fetcher, say=said.append)
        self.assertEqual(done, [])
        self.assertEqual(fetcher.calls, [], "nothing downloaded")
        self.assertEqual(len(said), 1)
        self.assertIn("cannot write to", said[0])

    def test_no_absolute_destination_is_said_once_and_nothing_downloads(self):
        fetcher = Fetcher(archives())
        said = []
        with mock.patch.dict(os.environ, {"GITMOLE_TOOLS": "relative"}):
            done = install.install(["scc"], key=KEY, fetcher=fetcher, say=said.append)
        self.assertEqual((done, fetcher.calls), ([], []))
        self.assertIn("GITMOLE_TOOLS must be an absolute path", said[0])

    def test_a_copy_that_does_not_print_its_pin_is_removed_and_the_rest_still_install(self):
        """A glibc jscpd on Alpine placed fine and failed every run after; running it once catches that."""
        served = archives()
        served["https://example.test/osv-scanner_test_cpu"] = b"#!/bin/sh\necho osv-scanner version: 0.0.1\n"
        broken = tar_gz({"scc": b"\x7fELF not for this machine"})
        served["https://example.test/scc_Test_cpu.tar.gz"] = broken
        said = []
        with tempfile.TemporaryDirectory() as d, mock.patch.dict(tools.ARCHIVES, {KEY: table(served)}):
            done = install.install(["scc", "osv-scanner", "jscpd"], dest=d, key=KEY, fetcher=Fetcher(served), say=said.append)
            self.assertEqual(done, ["jscpd"])
            self.assertEqual(os.listdir(d), [f"jscpd-{tools.PINNED['jscpd']}"], "nothing of the two refused copies is left")
        self.assertTrue(any(l.startswith("osv-scanner: ") and "prints version 0.0.1" in l for l in said), said)
        self.assertTrue(any(l.startswith("scc: ") and "does not run here" in l for l in said), said)

    def test_a_leftover_temporary_file_of_another_install_is_not_touched(self):
        """Two installs at once each write through a temporary file of their own."""
        with tempfile.TemporaryDirectory() as d:
            other = os.path.join(d, ".scc.partial")
            open(other, "wb").close()
            path = install.place(b"new", d, "scc")
            self.assertTrue(os.path.exists(other), "the other install's file is its own")
            self.assertEqual(sorted(os.listdir(d)), [".scc.partial", "scc"])
            with open(path, "rb") as fh:
                self.assertEqual(fh.read(), b"new")

    def test_a_failing_output_is_not_blamed_on_a_tool(self):
        served = archives()
        def say(line):
            raise BrokenPipeError(32, "Broken pipe")
        with tempfile.TemporaryDirectory() as d, mock.patch.dict(tools.ARCHIVES, {KEY: table(served)}):
            with self.assertRaises(BrokenPipeError):
                install.install(["scc"], dest=d, key=KEY, fetcher=Fetcher(served), say=say)


class Offer(unittest.TestCase):
    def test_the_question_names_the_versions_the_hosts_and_the_directory(self):
        served = archives()
        with mock.patch.dict(tools.ARCHIVES, {KEY: table(served)}):
            question = install.offer(["scc", "jscpd"], dest="/x/tools", key=KEY)
        self.assertIn("scc 4.1.0", question)
        self.assertIn("jscpd 5.3.0", question)
        self.assertIn("example.test, registry.example.test", question, "the hosts, sorted, once each")
        self.assertIn("/x/tools", question)
        self.assertTrue(question.endswith("[y/N] "), "a prompt, with the default a no")

    def test_the_real_table_names_github_its_download_host_and_npm(self):
        """A GitHub release download is sent on to a second host; behind an allowlist both must be admitted."""
        question = install.offer(run.REQUIRED_TOOLS, dest="/x", key=("linux", "x86_64"))
        self.assertIn("github.com, registry.npmjs.org, release-assets.githubusercontent.com", question)
        self.assertEqual(install.hosts(["jscpd"], key=("linux", "x86_64")), ["registry.npmjs.org"])


class Fetch(unittest.TestCase):
    @staticmethod
    def _opener(result=None, error=None, sent_to=None):
        """An opener standing in for the network: it returns result, or records a redirect and raises error."""
        calls = []

        def make(redirects):
            opener = mock.MagicMock()

            def open_(request, timeout=None):
                calls.append((request, timeout))
                if sent_to:
                    redirects.last = sent_to
                if error is not None:
                    raise error
                response = mock.MagicMock()
                response.__enter__.return_value.read.return_value = result
                return response
            opener.open.side_effect = open_
            return opener
        return make, calls

    def test_a_failed_connection_is_an_install_error_naming_the_url(self):
        import urllib.error
        make, _ = self._opener(error=urllib.error.URLError("nodename nor servname provided"))
        with mock.patch.object(install, "_opener", make):
            with self.assertRaises(install.InstallError) as caught:
                install.fetch("https://example.test/scc.tar.gz")
        self.assertIn("https://example.test/scc.tar.gz", str(caught.exception))
        self.assertIn("nodename", str(caught.exception))

    def test_a_body_cut_short_is_an_install_error_not_a_traceback(self):
        """IncompleteRead and BadStatusLine are http.client.HTTPException, not OSError."""
        for error in (http.client.IncompleteRead(b"x" * 10, 990), http.client.BadStatusLine("garbage")):
            with self.subTest(error=type(error).__name__):
                make, _ = self._opener(error=error)
                with mock.patch.object(install, "_opener", make), self.assertRaises(install.InstallError):
                    install.fetch("https://example.test/scc.tar.gz")

    def test_a_failure_after_a_redirect_names_the_host_it_was_sent_to(self):
        import urllib.error
        make, _ = self._opener(error=urllib.error.URLError("Connection refused"),
                               sent_to="https://release-assets.githubusercontent.com/github-production-release-asset/1/2?sig=x")
        with mock.patch.object(install, "_opener", make), self.assertRaises(install.InstallError) as caught:
            install.fetch("https://github.com/boyter/scc/releases/download/v4.1.0/scc_Linux_x86_64.tar.gz")
        self.assertIn("sent on to release-assets.githubusercontent.com", str(caught.exception))
        self.assertNotIn("sig=", str(caught.exception), "the host, not the signed url")

    def test_the_request_names_gitmole_and_reads_the_whole_body(self):
        make, calls = self._opener(result=b"bytes")
        with mock.patch.object(install, "_opener", make):
            self.assertEqual(install.fetch("https://example.test/x"), b"bytes")
        request, timeout = calls[0]
        self.assertEqual(request.full_url, "https://example.test/x")
        self.assertEqual(request.get_header("User-agent"), "gitmole")
        self.assertEqual(timeout, install.TIMEOUT)

    def test_a_python_without_certificates_on_macos_borrows_the_systems(self):
        """A python.org build has no CA bundle until Install Certificates.command runs; every download failed."""
        context = mock.MagicMock()
        context.get_ca_certs.return_value = []
        env = {k: v for k, v in os.environ.items() if k != "SSL_CERT_FILE"}
        with mock.patch("ssl.create_default_context", return_value=context), mock.patch.object(install.sys, "platform", "darwin"), \
                mock.patch("os.path.isfile", return_value=True), mock.patch.dict(os.environ, env, clear=True):
            install._context()
        context.load_verify_locations.assert_called_once_with("/etc/ssl/cert.pem")
        context = mock.MagicMock()
        context.get_ca_certs.return_value = [{"subject": "a root"}]
        with mock.patch("ssl.create_default_context", return_value=context), mock.patch.object(install.sys, "platform", "darwin"):
            install._context()
        context.load_verify_locations.assert_not_called()


class OnThePath(unittest.TestCase):
    def test_the_tool_directory_comes_first_once_it_exists_and_not_before(self):
        with tempfile.TemporaryDirectory() as d:
            root = os.path.join(d, "tools")
            with mock.patch.dict(os.environ, {"GITMOLE_TOOLS": root}):
                scc = userdirs.tool_dir("scc")
                self.assertNotIn(scc, run.env_path().split(os.pathsep), "a directory that is not there is not on the PATH")
                os.makedirs(scc)
                parts = run.env_path().split(os.pathsep)
                self.assertEqual(parts[0], scc)
                self.assertIn(os.environ.get("PATH", ""), run.env_path(), "the caller's PATH still follows")

    def test_a_copy_for_another_pin_is_never_on_the_path(self):
        """After a pin bump the old copy would otherwise win over the formula's and the user's alike."""
        with tempfile.TemporaryDirectory() as d, mock.patch.dict(os.environ, {"GITMOLE_TOOLS": d}):
            os.makedirs(os.path.join(d, "scc-4.0.9"))
            open(os.path.join(d, "scc"), "w").close()   # the flat layout before one directory per pin
            parts = run.env_path().split(os.pathsep)
            self.assertNotIn(os.path.join(d, "scc-4.0.9"), parts)
            self.assertNotIn(d, parts)

    def test_backtest_and_duplicates_look_where_a_run_looks(self):
        """In-process callers (evaluate, measure, the tests) ran scc and jscpd off the plain PATH."""
        from gitmole import backtest, duplicates
        seen = []
        def fake_run(argv, **kw):
            seen.append((argv[0], (kw.get("env") or {}).get("PATH", "")))
            raise RuntimeError("stop here")
        with tempfile.TemporaryDirectory() as d, mock.patch.dict(os.environ, {"GITMOLE_TOOLS": d}):
            for name in ("scc", "jscpd"):
                os.makedirs(userdirs.tool_dir(name))
            with mock.patch("subprocess.run", side_effect=fake_run):
                with self.assertRaises(RuntimeError):
                    duplicates.run_jscpd(d, d, 1)
            with mock.patch("gitmole.backtest.subprocess.run", side_effect=lambda argv, **kw: fake_run(argv, **kw) if argv[0] == "scc"
                            else mock.MagicMock(returncode=0, stdout=b"", stderr=b"")):
                with self.assertRaises(RuntimeError):
                    backtest.snapshot_at(d, "HEAD", d)
            self.assertEqual([argv0 for argv0, _ in seen], ["jscpd", "scc"])
            for name, path in seen:
                self.assertEqual(path.split(os.pathsep)[0], userdirs.tool_dir(name), name)

    def test_an_installed_tool_is_then_found_and_versioned_like_any_other(self):
        served = archives()
        with tempfile.TemporaryDirectory() as d, mock.patch.dict(tools.ARCHIVES, {KEY: table(served)}), \
                mock.patch.dict(os.environ, {"GITMOLE_TOOLS": os.path.join(d, "tools")}):
            self.assertIn("scc", run.missing_tools(path=os.path.join(d, "empty-path")))
            self.assertEqual(install.writable(os.path.join(d, "tools")), None)
            install.install(["scc"], key=KEY, fetcher=Fetcher(served), say=lambda line: None)
            self.assertNotIn("scc", run.missing_tools(path=run.env_path()))
            run.tool_version.cache_clear()
            self.assertEqual(run.tool_version("scc", path=run.env_path()), tools.PINNED["scc"], "the fake prints `scc version 4.1.0`")
            run.tool_version.cache_clear()


if __name__ == "__main__":
    unittest.main()

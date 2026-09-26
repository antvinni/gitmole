import io
import os
import tarfile
import tempfile
import unittest
import zipfile
from unittest import mock

from gitmole import install, run, tools

KEY = ("test", "cpu")   # a platform of its own, so the tests never touch the real table's urls
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
        self.assertEqual(install.platform_key("Linux", "aarch64"), ("linux", "arm64"))
        self.assertEqual(install.platform_key("Linux", "x86_64"), ("linux", "x86_64"))
        self.assertEqual(install.platform_key("Linux", "AMD64"), ("linux", "x86_64"))
        self.assertEqual(install.platform_key("Windows", "ARM64"), ("windows", "arm64"))
        self.assertEqual(install.platform_key("Linux", "riscv64"), ("linux", "riscv64"), "an unknown cpu passes through")
        system, cpu = install.platform_key()
        self.assertEqual(system, system.lower())

    def test_tools_dir_honours_the_override_and_ends_in_gitmole_tools(self):
        self.assertEqual(install.tools_dir({"GITMOLE_TOOLS": "/somewhere/tools"}), "/somewhere/tools")
        default = install.tools_dir({})
        self.assertTrue(default.endswith(os.path.join("gitmole", "tools")), default)
        self.assertTrue(os.path.isabs(default))
        self.assertEqual(install.tools_dir({"GITMOLE_TOOLS": ""}), default, "an empty override is no override")

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
        self.assertIsNone(install.pick(["scc_a", "scc_b"], "scc"), "two prefixed files is an ambiguity, not a pick")


class Install(unittest.TestCase):
    def test_each_archive_shape_yields_one_executable_at_its_name(self):
        served = archives()
        fetcher = Fetcher(served)
        said = []
        with tempfile.TemporaryDirectory() as d, mock.patch.dict(tools.ARCHIVES, {KEY: table(served)}):
            dest = os.path.join(d, "tools")
            done = install.install(run.REQUIRED_TOOLS, dest=dest, key=KEY, fetcher=fetcher, say=said.append)
            self.assertEqual(done, run.REQUIRED_TOOLS)
            self.assertEqual(sorted(os.listdir(dest)), sorted(run.REQUIRED_TOOLS), "one file per tool, no partials, no LICENSE")
            for name in run.REQUIRED_TOOLS:
                path = os.path.join(dest, name)
                with open(path, "rb") as fh:
                    self.assertEqual(fh.read(), FAKE_BIN[name], name)
                self.assertTrue(os.access(path, os.X_OK), name)
                self.assertTrue(run.has_tool(name, path=dest), f"{name} is found on a PATH holding only this directory")
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
            self.assertEqual(os.listdir(d), ["jscpd"])
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
            self.assertEqual(os.listdir(d), ["scc"])
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
        self.assertIn("go install github.com/github/git-sizer@v1.5.0", said[0])
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
            with open(os.path.join(d, "scc"), "wb") as fh:
                fh.write(b"an older scc, much longer than the new one " * 10)
            install.install(["scc"], dest=d, key=KEY, fetcher=Fetcher(served), say=lambda line: None)
            with open(os.path.join(d, "scc"), "rb") as fh:
                self.assertEqual(fh.read(), FAKE_BIN["scc"])
            self.assertEqual(os.listdir(d), ["scc"])

    def test_the_default_destination_is_the_tool_directory(self):
        served = archives()
        with tempfile.TemporaryDirectory() as d, mock.patch.dict(tools.ARCHIVES, {KEY: table(served)}), \
                mock.patch.dict(os.environ, {"GITMOLE_TOOLS": os.path.join(d, "own")}):
            install.install(["scc"], key=KEY, fetcher=Fetcher(served), say=lambda line: None)
            self.assertTrue(os.path.isfile(os.path.join(d, "own", "scc")))


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

    def test_the_real_table_asks_from_github_and_npm(self):
        question = install.offer(run.REQUIRED_TOOLS, dest="/x", key=("linux", "x86_64"))
        self.assertIn("github.com, registry.npmjs.org", question)


class Fetch(unittest.TestCase):
    def test_a_failed_connection_is_an_install_error_naming_the_url(self):
        import urllib.error
        with mock.patch("urllib.request.urlopen", side_effect=urllib.error.URLError("nodename nor servname provided")):
            with self.assertRaises(install.InstallError) as caught:
                install.fetch("https://example.test/scc.tar.gz")
        self.assertIn("https://example.test/scc.tar.gz", str(caught.exception))
        self.assertIn("nodename", str(caught.exception))

    def test_the_request_names_gitmole_and_reads_the_whole_body(self):
        response = mock.MagicMock()
        response.__enter__.return_value.read.return_value = b"bytes"
        with mock.patch("urllib.request.urlopen", return_value=response) as urlopen:
            self.assertEqual(install.fetch("https://example.test/x"), b"bytes")
        request = urlopen.call_args.args[0]
        self.assertEqual(request.full_url, "https://example.test/x")
        self.assertEqual(request.get_header("User-agent"), "gitmole")
        self.assertEqual(urlopen.call_args.kwargs["timeout"], install.TIMEOUT)


if __name__ == "__main__":
    unittest.main()

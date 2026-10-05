"""--path: a report about the files under a directory. Every test here pairs the scoped result with the
unscoped one on the same fixture, so the whole-repository behaviour is pinned alongside."""
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest

from rich.console import Console

from gitmole import blame, cli, hygiene, knowledge, load, maat, render, run, scope, structure

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def console():
    return Console(file=io.StringIO(), width=120, record=True, force_terminal=False, color_system=None)


def _git(d, *args, **env):
    e = dict(os.environ, GIT_CONFIG_GLOBAL="/dev/null", GIT_CONFIG_SYSTEM="/dev/null", **env)
    return subprocess.run(["git", *args], cwd=d, check=True, capture_output=True, env=e).stdout.decode()


def _write(d, path, text):
    os.makedirs(os.path.dirname(os.path.join(d, path)) or d, exist_ok=True)
    with open(os.path.join(d, path), "w") as fh:
        fh.write(text)


def _commit(d, who, when, message, files):
    for path, text in files.items():
        _write(d, path, text)
        _git(d, "add", path)
    _git(d, "commit", "-q", "-m", message, GIT_AUTHOR_NAME=who, GIT_AUTHOR_EMAIL=f"{who.lower()}@x.com", GIT_AUTHOR_DATE=when,
         GIT_COMMITTER_NAME=who, GIT_COMMITTER_EMAIL=f"{who.lower()}@x.com", GIT_COMMITTER_DATE=when)


def fixture(d):
    """svc/a, svc/b and web/, with a feature branch into svc/ merged with a merge commit: six commits, three
    of them and the branch's one touching svc/, and one merge."""
    _git(d, "init", "-q", "-b", "main")
    _commit(d, "Ann", "2025-01-01T10:00:00", "web and readme", {"web/z.py": "def z():\n    return 1\n", "README.md": "hi\n"})
    _commit(d, "Bob", "2025-02-01T10:00:00", "svc a", {"svc/a/x.py": "def x():\n    return 1\n"})
    _commit(d, "Ann", "2025-03-01T10:00:00", "fix: both", {"svc/a/x.py": "def x():\n    return 2\n", "web/z.py": "def z():\n    return 2\n"})
    _commit(d, "Cid", "2025-04-01T10:00:00", "svc b", {"svc/b/y.py": "def y():\n    return 1\n"})
    _git(d, "switch", "-q", "-c", "feature")
    _commit(d, "Bob", "2025-05-01T10:00:00", "feature in b", {"svc/b/y.py": "def y():\n    return 3\n"})
    _git(d, "switch", "-q", "main")
    _commit(d, "Ann", "2025-05-02T10:00:00", "web again", {"web/z.py": "def z():\n    return 3\n"})
    _git(d, "merge", "-q", "--no-ff", "-m", "Merge feature", "feature", GIT_AUTHOR_NAME="Ann", GIT_AUTHOR_EMAIL="ann@x.com",
         GIT_COMMITTER_NAME="Ann", GIT_COMMITTER_EMAIL="ann@x.com", GIT_AUTHOR_DATE="2025-05-03T10:00:00", GIT_COMMITTER_DATE="2025-05-03T10:00:00")


class Clean(unittest.TestCase):
    def test_one_spelling_per_directory_and_the_root_drops_out(self):
        self.assertEqual(scope.clean(["svc/", "./svc", "svc/a", "web//"]), ["svc", "web"])
        self.assertEqual(scope.clean(["."]), [])
        self.assertEqual(scope.clean([]), [])

    def test_a_path_outside_the_repository_is_refused(self):
        for bad in ["../x", "/abs/path", "svc/../../x"]:
            with self.assertRaises(ValueError):
                scope.clean([bad])

    def test_base_is_the_levels_every_directory_shares(self):
        self.assertEqual(scope.base([]), 0)
        self.assertEqual(scope.base(["backend/plugins/github"]), 3)
        self.assertEqual(scope.base(["a/x", "a/y"]), 1)
        self.assertEqual(scope.base(["a", "b"]), 0)

    def test_within_and_the_pathspec_are_the_identity_without_a_scope(self):
        self.assertTrue(scope.within("anything/at/all.py", []))
        self.assertEqual(scope.pathspec([]), [])
        self.assertEqual(scope.pathspec(["svc"]), ["--", ":(literal)svc"])
        self.assertTrue(scope.within("svc/a.py", ["svc"]))
        self.assertFalse(scope.within("svcx/a.py", ["svc"]), "a sibling that shares the prefix is not inside")


class Validate(unittest.TestCase):
    def test_a_directory_of_head_passes_and_anything_else_says_why(self):
        with tempfile.TemporaryDirectory() as d:
            fixture(d)
            scope.validate(d, ["svc", "svc/a"])
            with self.assertRaisesRegex(ValueError, "not in the tree at HEAD"):
                scope.validate(d, ["nope"])
            with self.assertRaisesRegex(ValueError, "is a file"):
                scope.validate(d, ["README.md"])


class History(unittest.TestCase):
    def test_meta_counts_the_commits_that_touch_the_directory_and_records_it(self):
        with tempfile.TemporaryDirectory() as d:
            fixture(d)
            whole, scoped = run.collect_meta(d), run.collect_meta(d, scope=["svc"])
        self.assertEqual(whole["commits"], 7)
        self.assertNotIn("scope", whole, "the whole repository's meta.json is the one it always was")
        self.assertEqual(scoped["commits"], 4, "svc a, fix: both, svc b and the branch's commit")
        self.assertEqual(scoped["scope"], ["svc"])
        self.assertEqual(sorted(i["name"] for i in scoped["identities"]), ["Ann", "Bob", "Cid"])
        self.assertEqual(scoped["first_date"], "2025-02-01")
        self.assertEqual(whole["merges"], 1)
        self.assertEqual(scoped["merges"], 1, "the merge brought svc/b's change in; a plain pathspec would have simplified it away")
        with tempfile.TemporaryDirectory() as d:
            fixture(d)
            web = run.collect_meta(d, scope=["web"])
        self.assertEqual(web["merges"], 0, "the merge changed nothing under web/ against main")

    def _revisions(self, d, out, scope_dirs):
        steps = {s["name"]: s for s in run.plan(d, out, scope=scope_dirs)}
        with open(os.path.join(out, "log.txt"), "w") as fh:
            subprocess.run(steps["git-log"]["argv"], cwd=d, check=True, stdout=fh)
        run.save_meta(run.collect_meta(d, scope=scope_dirs), out)
        maat.write_all(os.path.join(out, "log.txt"), out, os.path.join(out, "meta.json"), now="2025-06-01")
        with open(os.path.join(out, "maat-revisions.csv")) as fh:
            return {r["entity"]: r["n-revs"] for r in load.parse_maat_csv(fh.read())}

    def test_the_change_log_and_everything_counted_from_it_cover_only_the_directory(self):
        with tempfile.TemporaryDirectory() as d, tempfile.TemporaryDirectory() as out:
            fixture(d)
            whole = self._revisions(d, out, [])
            scoped = self._revisions(d, out, ["svc"])
        self.assertEqual(whole, {"web/z.py": 3, "svc/a/x.py": 2, "svc/b/y.py": 2})
        self.assertEqual(scoped, {"svc/a/x.py": 2, "svc/b/y.py": 2}, "same counts for the files inside, none for the rest")


class Plan(unittest.TestCase):
    def test_the_default_plan_carries_no_path_and_a_scoped_one_narrows_the_right_steps(self):
        whole = {s["name"]: s["argv"] for s in run.plan("/r", "/o", lizard=True)}
        scoped = {s["name"]: s["argv"] for s in run.plan("/r", "/o", lizard=True, scope=["svc", "web"])}
        for argv in whole.values():
            self.assertNotIn("--path", argv)
        self.assertNotIn("--", whole["git-log"])
        self.assertEqual(scoped["git-log"][-3:], ["--", ":(literal)svc", ":(literal)web"])
        for name in ["code age", "functions"]:
            argv = scoped[name]
            self.assertEqual([argv[i + 1] for i, a in enumerate(argv) if a == "--path"], ["svc", "web"], name)
        for name in ["scc", "betterleaks", "osv-scanner", "signing", "hygiene", "provenance", "change analysis"]:
            self.assertEqual(scoped[name], whole[name], f"{name}: narrowed from meta.json or repository-wide, never by its argv")

    def test_the_output_directory_names_the_scope(self):
        self.assertEqual(run.output_dir("path", "/w/devlake", None), "/w/analysis-devlake")
        self.assertEqual(run.output_dir("path", "/w/devlake", None, scope=["backend/plugins/github"]),
                         "/w/analysis-devlake-backend-plugins-github")
        self.assertEqual(run.output_dir("path", "/w/devlake", "/x/out", scope=["a"]), "/x/out", "--out as given")


class Files(unittest.TestCase):
    def test_text_files_and_the_estimate_read_only_the_directory(self):
        with tempfile.TemporaryDirectory() as d:
            fixture(d)
            self.assertEqual(blame.text_files(d), ["README.md", "svc/a/x.py", "svc/b/y.py", "web/z.py"])
            self.assertEqual(blame.text_files(d, paths=["svc"]), ["svc/a/x.py", "svc/b/y.py"])
            tracked = blame.text_files(d)
            whole = run.estimate_blames(d, sample=0, tracked=tracked)
            scoped = run.estimate_blames(d, sample=0, tracked=tracked, scope=["svc/a"])
        self.assertEqual((whole["files"], whole["code_files"]), (4, 3))
        self.assertEqual((scoped["files"], scoped["code_files"]), (1, 1))

    def test_the_size_table_keeps_the_directory_and_rebuilds_the_totals(self):
        text = json.dumps([{"Name": "Python", "Count": 2, "Code": 30, "Comment": 0, "Blank": 0, "Complexity": 3,
                            "Files": [{"Location": "./svc/a/x.py", "Code": 10, "Complexity": 1}, {"Location": "web/z.py", "Code": 20, "Complexity": 2}]}])
        self.assertEqual(load.parse_scc(text)["total_code"], 30)
        scoped = load.parse_scc(text, scope=["svc"])
        self.assertEqual((scoped["total_code"], scoped["total_files"], list(scoped["files"])), (10, 1, ["svc/a/x.py"]))

    def test_a_committed_binary_outside_the_directory_is_not_its_finding(self):
        with tempfile.TemporaryDirectory() as d:
            fixture(d)
            for path in ["svc/a/tool", "web/tool"]:
                os.makedirs(os.path.join(d, os.path.dirname(path)), exist_ok=True)
                with open(os.path.join(d, path), "wb") as fh:
                    fh.write(b"\x7fELF\x02\x01\x01" + b"\0" * 9 + b"\x02\x00" + b"\0" * 40)
                _git(d, "add", path)
            self.assertEqual([e["file"] for e in hygiene.binaries(d)["executables"]], ["svc/a/tool", "web/tool"])
            self.assertEqual([e["file"] for e in hygiene.binaries(d, scope=["svc"])["executables"]], ["svc/a/tool"])


@unittest.skipUnless(structure.available(), "the tree-sitter grammars need Python 3.10 or newer")
class Structure(unittest.TestCase):
    def test_the_whole_tree_is_parsed_and_only_the_result_narrowed(self):
        with tempfile.TemporaryDirectory() as d:
            repo, out = os.path.join(d, "repo"), os.path.join(d, "out")
            os.makedirs(out)
            os.makedirs(repo)
            _git(repo, "init", "-q")
            _write(repo, "svc/__init__.py", "")
            _write(repo, "svc/lib.py", "def f():\n    if a:\n        if b:\n            if c:\n                pass\n")
            _write(repo, "web/main.py", "from svc import lib\ndef g():\n    if a:\n        if b:\n            if c:\n                pass\n")
            _git(repo, "add", "svc", "web")
            _git(repo, "commit", "-q", "-m", "c", GIT_AUTHOR_NAME="A", GIT_AUTHOR_EMAIL="a@x", GIT_COMMITTER_NAME="A", GIT_COMMITTER_EMAIL="a@x")
            env = dict(os.environ, PYTHONPATH=ROOT, GITMOLE_CACHE=os.path.join(d, "cache"))
            results = {}
            for name, meta in [("whole", {}), ("scoped", {"scope": ["svc"]})]:
                with open(os.path.join(out, "meta.json"), "w") as fh:
                    json.dump(meta, fh)
                p = subprocess.run([sys.executable, "-m", "gitmole.structure", out, "--procs", "1"], cwd=repo, env=env, capture_output=True, text=True)
                self.assertEqual(p.returncode, 0, p.stderr)
                with open(os.path.join(out, "structure.json")) as fh:
                    results[name] = json.load(fh)
        whole, scoped = results["whole"], results["scoped"]
        self.assertEqual(sorted(whole["files"]), ["svc/__init__.py", "svc/lib.py", "web/main.py"])
        self.assertEqual(whole["files"]["web/main.py"]["imports"], ["svc/lib.py"])
        self.assertEqual(sorted(scoped["files"]), ["svc/__init__.py", "svc/lib.py"])
        self.assertEqual([f["file"] for f in scoped["functions"]], ["svc/lib.py"])
        self.assertEqual(scoped["languages"], {"python": 2})
        self.assertNotIn("svc/lib.py", scoped["unreferenced"], "web/ imports it: parsing only svc/ would have called it unreferenced")


class Areas(unittest.TestCase):
    ROWS = [{"entity": "backend/plugins/github/tasks/a.go", "author": "Ann", "added": 50},
            {"entity": "backend/plugins/github/api/b.go", "author": "Bob", "added": 30},
            {"entity": "backend/plugins/github/impl.go", "author": "Cid", "added": 10}]

    def test_the_knowledge_map_counts_its_areas_from_below_the_directory(self):
        self.assertEqual([a["area"] for a in knowledge.areas(self.ROWS)], ["backend/plugins/"], "the whole-repository map: one area")
        self.assertEqual([a["area"] for a in knowledge.areas(self.ROWS, base=3)],
                         ["backend/plugins/github/tasks/", "backend/plugins/github/api/", knowledge.ROOT])
        self.assertTrue(knowledge.in_area("backend/plugins/github/impl.go", knowledge.ROOT, 3))
        self.assertFalse(knowledge.in_area("backend/plugins/github/api/b.go", knowledge.ROOT, 3))

    def test_components_count_from_below_the_directory(self):
        self.assertEqual(maat.component("backend/plugins/github/api/b.go", 1), "backend/")
        self.assertEqual(maat.component("backend/plugins/github/api/b.go", 1, 3), "backend/plugins/github/api/")
        self.assertEqual(maat.component("backend/plugins/github/impl.go", 1, 3), "(root files)")


class CommandLine(unittest.TestCase):
    def _run(self, d, extra, calls=None):
        def planner(repo, o, branch="HEAD", **kw):
            if calls is not None:
                calls.append(kw)
            return [{"name": "q", "argv": ["true"], "stdout": None, "deps": []}]
        c = console()
        rc = cli.main([d, *extra], console=c, tool_check=lambda **kw: [], planner=planner,
                      estimator=lambda repo, interval, **kw: {"files": 1, "samples": 1, "blames": 1, "seconds": 0.0})
        return rc, c.export_text()

    def test_a_scoped_run_plans_records_and_says_its_scope(self):
        with tempfile.TemporaryDirectory() as d:
            fixture(d)
            calls = []
            rc, text = self._run(d, ["--path", "svc/", "--path", "./svc/a"], calls)
            out = os.path.join(os.path.dirname(d), f"analysis-{os.path.basename(d)}-svc")
            try:
                self.assertEqual(rc, 0)
                self.assertEqual(calls[0]["scope"], ["svc"])
                with open(os.path.join(out, "meta.json")) as fh:
                    meta = json.load(fh)
            finally:
                import shutil
                shutil.rmtree(out, ignore_errors=True)
        self.assertEqual(meta["scope"], ["svc"])
        self.assertEqual(meta["commits"], 4)
        self.assertIn("path svc", text)
        self.assertIn(scope.REPOSITORY_WIDE, " ".join(text.replace("│", " ").split()), "on the header's scope row, wrapped under its label")

    def test_the_default_run_passes_no_scope(self):
        with tempfile.TemporaryDirectory() as d:
            fixture(d)
            calls = []
            rc, text = self._run(d, ["--out", os.path.join(d, "out")], calls)
            with open(os.path.join(d, "out", "meta.json")) as fh:
                meta = json.load(fh)
        self.assertEqual(rc, 0)
        self.assertNotIn("scope", calls[0])
        self.assertNotIn("scope", meta)
        self.assertNotIn("repository-wide", text)

    def test_a_path_that_is_not_a_directory_of_head_stops_before_anything_is_written(self):
        with tempfile.TemporaryDirectory() as d:
            fixture(d)
            out = os.path.join(d, "out")
            rc, text = self._run(d, ["--out", out, "--path", "nope"])
            self.assertEqual(rc, 2)
            self.assertIn("--path nope: is not in the tree at HEAD", text)
            self.assertFalse(os.path.exists(out))

    def test_combinations_that_cannot_be_narrowed_are_refused(self):
        with tempfile.TemporaryDirectory() as d:
            fixture(d)
            for extra, said in [(["--no-run"], "a re-render cannot narrow"), (["--plots"], "git-of-theseus reads the whole tree"),
                                (["--path", "../up"], "leaves the repository")]:
                c = console()
                rc = cli.main([d, "--path", "svc", *extra], console=c, tool_check=lambda **kw: 1 / 0)
                self.assertEqual(rc, 2, extra)
                self.assertIn(said, c.export_text())
            c = console()
            self.assertEqual(cli.main(["someone/*", "--path", "svc"], console=c, tool_check=lambda **kw: []), 2)
            self.assertIn("--path needs one repository", c.export_text())

    def test_compare_refuses_an_export_of_another_scope(self):
        with tempfile.TemporaryDirectory() as d:
            fixture(d)
            whole, scoped = os.path.join(d, "whole"), os.path.join(d, "scoped")
            before = os.path.join(d, "before.json")
            self.assertEqual(self._run(d, ["--out", whole, "--json", before])[0], 0)
            self.assertEqual(self._run(d, ["--out", scoped, "--path", "svc"])[0], 0)
            c = console()
            self.assertEqual(cli.main([scoped, "--no-run", "--compare", before], console=c), 2)
            self.assertIn("it describes the whole repository, this run describes path svc", " ".join(c.export_text().split()))
            self.assertEqual(cli.main([whole, "--no-run", "--compare", before], console=console()), 0)


class Header(unittest.TestCase):
    def test_markdown_says_the_scope_and_what_stays_repository_wide(self):
        with tempfile.TemporaryDirectory() as out:
            with open(os.path.join(out, "meta.json"), "w") as fh:
                json.dump({"name": "demo", "scope": ["svc"], "identities": []}, fh)
            scoped = render.markdown(load.load_report(out), [])
            with open(os.path.join(out, "meta.json"), "w") as fh:
                json.dump({"name": "demo", "identities": []}, fh)
            whole = render.markdown(load.load_report(out), [])
        self.assertIn(f"path svc · {scope.REPOSITORY_WIDE}", scoped)
        self.assertNotIn("repository-wide", whole)


if __name__ == "__main__":
    unittest.main()

import json
import os
import subprocess
import sys
import tempfile
import unittest

from gitmole import backtest


def history_repo(d):
    """18 months: hot.py churns early and is fixed late; calm.py is touched once."""
    def git(*args, date):
        e = dict(os.environ, GIT_CONFIG_GLOBAL="/dev/null", GIT_CONFIG_SYSTEM="/dev/null",
                 GIT_AUTHOR_NAME="A", GIT_AUTHOR_EMAIL="a@x", GIT_COMMITTER_NAME="A", GIT_COMMITTER_EMAIL="a@x",
                 GIT_AUTHOR_DATE=f"{date}T10:00:00", GIT_COMMITTER_DATE=f"{date}T10:00:00")
        subprocess.run(["git", *args], cwd=d, check=True, capture_output=True, env=e)
    git("init", "-q", date="2025-01-01")
    with open(os.path.join(d, "calm.py"), "w") as fh: fh.write("x = 1\n")
    with open(os.path.join(d, "hot.py"), "w") as fh: fh.write("def f():\n    return 1\n")
    os.makedirs(os.path.join(d, "gen"), exist_ok=True)
    with open(os.path.join(d, "gen", "out.py"), "w") as fh: fh.write("# @generated\nx = 1\n")
    os.makedirs(os.path.join(d, "vend"), exist_ok=True)
    with open(os.path.join(d, "vend", "lib.py"), "w") as fh: fh.write("x = 1\n")
    with open(os.path.join(d, ".gitattributes"), "w") as fh: fh.write("vend/** linguist-vendored\n")
    git("add", "-A", date="2025-01-01"); git("commit", "-q", "-m", "start", date="2025-01-01")
    for i, date in enumerate(["2025-02-01", "2025-04-01", "2025-06-01", "2025-08-01", "2025-10-01"], start=2):
        with open(os.path.join(d, "hot.py"), "a") as fh: fh.write(f"def f{i}():\n    return {i}\n")
        git("commit", "-q", "-am", f"grow {i}", date=date)
    with open(os.path.join(d, "hot.py"), "a") as fh: fh.write("# fixed\n")
    os.remove(os.path.join(d, "gen", "out.py"))   # gone by HEAD; still there at the cut-off
    git("commit", "-q", "-am", "fix: crash in hot", date="2026-04-01")
    with open(os.path.join(d, "calm.py"), "a") as fh: fh.write("y = 2\n")
    git("commit", "-q", "-am", "tweak calm", date="2026-06-01")


def export(d, out):
    os.makedirs(out, exist_ok=True)
    log = subprocess.run(["git", "-c", "core.quotePath=false", "log", "HEAD", "--use-mailmap", "--numstat", "--date=iso-strict",
                          "--pretty=format:--%h--%ad--%aN--%s", "--no-renames"], cwd=d, capture_output=True, text=True, check=True).stdout
    with open(os.path.join(out, "log.txt"), "w") as fh:
        fh.write(log)
    with open(os.path.join(out, "meta.json"), "w") as fh:
        json.dump({"name": "x", "first_date": "2025-01-01", "last_date": "2026-06-01", "file_types": None, "aliases": {}}, fh)


class Step(unittest.TestCase):
    def test_writes_the_change_analysis_and_size_as_of_the_cut_off(self):
        with tempfile.TemporaryDirectory() as d:
            history_repo(d)
            out = os.path.join(d, "out")
            export(d, out)
            rc = backtest.main([out, "--until", "2025-12-01", "--repo", d])
            self.assertEqual(rc, 0)
            sub = os.path.join(out, "backtest")
            with open(os.path.join(sub, "maat-revisions.csv")) as fh:
                revs = dict(line.strip().split(",") for line in fh.readlines()[1:])
            with open(os.path.join(sub, "size.json")) as fh:
                size = json.load(fh)
            with open(os.path.join(sub, "meta.json")) as fh:
                meta = json.load(fh)
            listing = sorted(os.listdir(out))
        self.assertEqual(listing, ["backtest", "log.txt", "meta.json"], "the exported tree is cleaned up")
        self.assertEqual(revs, {"hot.py": "6", "calm.py": "1", "gen/out.py": "1", "vend/lib.py": "1"},
                         "the fix and the tweak are after the cut-off; gen/out.py and vend/lib.py were only added, not yet touched again")
        self.assertEqual(sorted(f["Location"] for r in size for f in r["Files"]), ["calm.py", "gen/out.py", "hot.py", "vend/lib.py"])
        hot = next(f for r in size for f in r["Files"] if f["Location"] == "hot.py")
        self.assertEqual(hot["Code"], 12, "hot.py as it was on 2025-10-01: six two-line functions")
        self.assertEqual(meta, {"now": "2025-12-01", "last_date": "2025-12-01", "file_types": None, "aliases": {},
                                "generated": ["gen/out.py"], "vendored": ["vend/lib.py"]},
                         "classified at the cut-off: gen/out.py was still there, and the attribute is read from that tree's .gitattributes")

    def test_export_ignored_files_are_still_measured(self):
        with tempfile.TemporaryDirectory() as d:
            history_repo(d)

            def git(*args, date):
                e = dict(os.environ, GIT_CONFIG_GLOBAL="/dev/null", GIT_CONFIG_SYSTEM="/dev/null",
                         GIT_AUTHOR_NAME="A", GIT_AUTHOR_EMAIL="a@x", GIT_COMMITTER_NAME="A", GIT_COMMITTER_EMAIL="a@x",
                         GIT_AUTHOR_DATE=f"{date}T10:00:00", GIT_COMMITTER_DATE=f"{date}T10:00:00")
                subprocess.run(["git", *args], cwd=d, check=True, capture_output=True, env=e)
            with open(os.path.join(d, ".gitattributes"), "w") as fh: fh.write("calm.py export-ignore\n")
            git("add", "-A", date="2025-11-01")
            git("commit", "-q", "-m", "ignore calm on export", date="2025-11-01")
            out = os.path.join(d, "out")
            export(d, out)
            rc = backtest.main([out, "--until", "2025-12-01", "--repo", d])
            self.assertEqual(rc, 0)
            with open(os.path.join(out, "backtest", "size.json")) as fh:
                size = json.load(fh)
        self.assertIn("calm.py", [f["Location"] for r in size for f in r["Files"]],
                       "export-ignore in .gitattributes must not thin the tree scc measures")

    def test_a_failed_git_or_scc_exits_2_with_one_line(self):
        import contextlib
        import io
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as d:
            history_repo(d)
            out = os.path.join(d, "out")
            export(d, out)
            boom = subprocess.CalledProcessError(128, ["git", "read-tree"], stderr="fatal: not a tree object\nsecond line\n")
            err = io.StringIO()
            with patch.object(backtest, "snapshot_at", side_effect=boom), contextlib.redirect_stderr(err):
                rc = backtest.main([out, "--until", "2025-12-01", "--repo", d])
        self.assertEqual(rc, 2)
        self.assertEqual(err.getvalue(), "backtest: fatal: not a tree object\n")

    def test_a_failing_git_grep_fails_the_snapshot_instead_of_claiming_an_empty_classification(self):
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as d:
            history_repo(d)
            out = os.path.join(d, "out")
            os.makedirs(out)
            real_run = subprocess.run

            def fake_run(cmd, *a, **kw):
                # only the git grep call fails; read-tree, checkout-index and scc run for real, so a
                # failure in the classification listing itself is what this test pins down
                if "grep" in cmd:
                    return subprocess.CompletedProcess(cmd, 2, stdout=b"", stderr=b"fatal: boom\n")
                return real_run(cmd, *a, **kw)

            with patch("gitmole.backtest.subprocess.run", side_effect=fake_run):
                with self.assertRaises(subprocess.CalledProcessError) as ctx:
                    backtest.snapshot_at(d, "HEAD", out)
        self.assertEqual(ctx.exception.returncode, 2, "a real git grep failure (not exit 1, which just means no matches) must surface")
        self.assertEqual(ctx.exception.stderr, "fatal: boom\n", "decoded so main() prints a string, not a bytes repr")

    def test_missing_inputs_exit_2(self):
        import contextlib
        import io
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "out")
            os.makedirs(out)   # neither meta.json nor log.txt written
            err = io.StringIO()
            with contextlib.redirect_stderr(err):
                rc = backtest.main([out, "--until", "2025-12-01", "--repo", d])
        self.assertEqual(rc, 2)
        self.assertEqual(err.getvalue(), "backtest: meta.json and log.txt are needed\n")

    def test_no_commit_before_the_cut_off_exits_2(self):
        with tempfile.TemporaryDirectory() as d:
            history_repo(d)
            out = os.path.join(d, "out")
            export(d, out)
            self.assertEqual(backtest.main([out, "--until", "2024-01-01", "--repo", d]), 2)

    def test_runs_as_a_module(self):
        p = subprocess.run([sys.executable, "-m", "gitmole.backtest", "--help"], capture_output=True, text=True,
                           env=dict(os.environ, PYTHONPATH=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
        self.assertEqual(p.returncode, 0, p.stderr)

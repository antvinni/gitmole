import io
import json
import os
import pathlib
import tempfile
import unittest

from rich.console import Console

from gitmole import cli, run


def console():
    return Console(file=io.StringIO(), width=100, record=True, force_terminal=False, color_system=None)


class NoRun(unittest.TestCase):
    def test_renders_from_existing_output_dir(self):
        with tempfile.TemporaryDirectory() as out:
            with open(os.path.join(out, "meta.json"), "w") as fh:
                json.dump({"name": "demo", "commits": 5, "identities": []}, fh)
            c = console()
            rc = cli.main([out, "--no-run"], console=c)
        self.assertEqual(rc, 0)
        self.assertIn("demo", c.export_text())

    def test_missing_output_dir_is_an_error(self):
        c = console()
        rc = cli.main(["/nonexistent/analysis-x", "--no-run"], console=c)
        self.assertEqual(rc, 2)
        self.assertIn("/nonexistent/analysis-x", c.export_text())

    def test_no_run_pointed_at_a_clone_says_what_it_wanted_and_where_it_is(self):
        """Every other invocation takes the clone, so `gitmole CLONE --no-run --out DIR` is the natural
        mistake: --out is not read here, and the directory a run wrote is the target. The message names it."""
        with tempfile.TemporaryDirectory() as tmp:
            clone, out = os.path.join(tmp, "curl"), os.path.join(tmp, "analysis-curl")
            os.makedirs(clone)
            os.makedirs(out)
            _report_dir(out)
            c = console()
            rc = cli.main([clone, "--no-run", "--out", out], console=c)
            text = c.export_text()
        self.assertEqual(rc, 2)
        self.assertIn("the target is that directory, not the clone", text)
        self.assertIn("--out is not read with --no-run", text)
        self.assertIn(f"Did you mean: gitmole {out} --no-run", text)

    def test_no_run_finds_the_output_directory_a_run_would_have_written(self):
        """With no --out at all, the conventional analysis-<repo> beside the clone is named."""
        with tempfile.TemporaryDirectory() as tmp:
            clone = os.path.join(tmp, "curl")
            os.makedirs(clone)
            os.makedirs(os.path.join(tmp, "analysis-curl"))
            _report_dir(os.path.join(tmp, "analysis-curl"))
            c = console()
            rc = cli.main([clone, "--no-run"], console=c)
            text = c.export_text()
        self.assertEqual(rc, 2)
        self.assertIn(f"Did you mean: gitmole {os.path.join(tmp, 'analysis-curl')} --no-run", text)
        self.assertNotIn("--out is not read", text, "nothing to say about a flag that was not passed")

    def test_no_run_with_nothing_to_point_at_says_only_what_it_wanted(self):
        with tempfile.TemporaryDirectory() as tmp:
            c = console()
            rc = cli.main([tmp, "--no-run"], console=c)
            text = c.export_text()
        self.assertEqual(rc, 2)
        self.assertIn("the target is that directory, not the clone", text)
        self.assertNotIn("Did you mean", text, "no guess without a directory that holds a report")

    def test_terminal_no_run_prints_the_banner_with_the_version(self):
        from gitmole import __version__
        with tempfile.TemporaryDirectory() as out:
            with open(os.path.join(out, "meta.json"), "w") as fh:
                json.dump({"name": "demo", "commits": 5, "identities": []}, fh)
            c = Console(file=io.StringIO(), width=100, record=True, force_terminal=True, color_system="truecolor")
            rc = cli.main([out, "--no-run"], console=c)
            text = c.export_text()
        self.assertEqual(rc, 0)
        self.assertIn("███╗   ███╗", text)
        self.assertIn(f"v{__version__}", text)

    def test_a_truncated_meta_json_is_an_error_not_a_traceback(self):
        with tempfile.TemporaryDirectory() as out:
            with open(os.path.join(out, "meta.json"), "w") as fh:
                fh.write('{"name": "d", "comm')
            c = console()
            rc = cli.main([out, "--no-run"], console=c)
        self.assertEqual(rc, 2)
        self.assertIn("run gitmole again", c.export_text())


class LiveRun(unittest.TestCase):
    def test_full_run_on_a_terminal_console_prints_banner_and_report(self):
        with tempfile.TemporaryDirectory() as d:
            import subprocess
            subprocess.run(["git", "init", "-q", d], check=True)
            subprocess.run(["git", "-C", d, "-c", "user.name=T", "-c", "user.email=t@x.com", "commit", "-q", "--allow-empty", "-m", "x"], check=True)
            c = Console(file=io.StringIO(), width=100, record=True, force_terminal=True, color_system="truecolor")
            fake_plan = lambda repo, out, branch="HEAD", **kw: [
                {"name": "quick", "argv": ["sh", "-c", "sleep 0.3"], "stdout": None, "deps": []}]
            rc = cli.main([d, "--out", os.path.join(d, "out")], console=c, tool_check=lambda **kw: [], planner=fake_plan)
            text = c.export_text()
        self.assertEqual(rc, 0)
        self.assertIn("███╗   ███╗", text)
        from gitmole import __version__
        self.assertIn(f"v{__version__}", text)
        self.assertIn("1 steps in", text)
        self.assertIn(os.path.basename(d), text)


def _tiny_repo(d):
    import subprocess
    subprocess.run(["git", "init", "-q", d], check=True)
    subprocess.run(["git", "-C", d, "-c", "user.name=T", "-c", "user.email=t@x.com", "commit", "-q", "--allow-empty", "-m", "x"], check=True)


class FunctionMetrics(unittest.TestCase):
    def _main(self, lizard, calls, stale=(), step=("sh", "-c", "true"), name="quick"):
        with tempfile.TemporaryDirectory() as d:
            _tiny_repo(d)
            out = os.path.join(d, "out")
            os.makedirs(os.path.join(out, "theseus"))
            for n in stale:
                open(os.path.join(out, n), "w").close()
            def planner(repo, o, branch="HEAD", **kw):
                calls.append(kw)
                return [{"name": name, "argv": list(step), "stdout": None, "deps": []}]
            rc = cli.main([d, "--out", out], console=console(), tool_check=lambda **kw: [], planner=planner,
                          estimator=lambda repo, interval, **kw: {"files": 1, "samples": 1, "blames": 1}, lizard_check=lambda: lizard)
            with open(os.path.join(out, "meta.json")) as fh:
                meta = json.load(fh)
            left = sorted(os.path.relpath(os.path.join(r, f), out) for r, _, fs in os.walk(out) for f in fs)
        return rc, meta, left

    def test_decided_once_and_recorded(self):
        calls = []
        rc, meta, _ = self._main(True, calls)
        self.assertEqual(rc, 0)
        self.assertTrue(calls[0]["lizard"])
        self.assertEqual(meta["functions"]["status"], "run")

    def test_the_structure_step_is_planned_when_tree_sitter_is_installed(self):
        for have in (True, False):
            with tempfile.TemporaryDirectory() as d:
                _tiny_repo(d)
                out = os.path.join(d, "out")
                calls = []
                def planner(repo, o, branch="HEAD", **kw):
                    calls.append(kw)
                    return [{"name": "q", "argv": ["true"], "stdout": None, "deps": []}]
                cli.main([d, "--out", out], console=console(), tool_check=lambda **kw: [], planner=planner,
                         estimator=lambda repo, interval, **kw: {"files": 1, "samples": 1, "blames": 1}, lizard_check=lambda: False,
                         structure_check=lambda: have)
                with open(os.path.join(out, "meta.json")) as fh:
                    meta = json.load(fh)
            self.assertEqual(calls[0]["structure"], have)
            self.assertEqual(meta["structure"]["status"], "run" if have else "skipped")
            if not have:
                self.assertEqual(meta["structure"]["install"], "the grammars need Python 3.10 or newer; reinstall gitmole on 3.10+")

    def test_skipped_without_lizard(self):
        calls = []
        rc, meta, _ = self._main(False, calls)
        self.assertEqual(rc, 0)
        self.assertFalse(calls[0]["lizard"])
        self.assertEqual(meta["functions"]["status"], "skipped")

    def test_a_failed_step_is_recorded_as_such(self):
        _, meta, _ = self._main(True, [], step=("sh", "-c", "exit 3"), name="functions")
        self.assertEqual(meta["functions"]["status"], "failed")
        _, meta, _ = self._main(True, [], step=("sh", "-c", "exit 3"), name="code age")
        self.assertEqual(meta["age"]["status"], "failed")

    def test_every_previous_output_is_cleared_before_a_run(self):
        stale = ("functions.csv", "duplicates.json", "dependencies.json", "theseus/cohorts.json", "maat-revisions.csv", "size.json")
        _, _, left = self._main(False, [], stale=stale)
        self.assertEqual(left, ["meta.json", "run.log"], "last run's outputs must not pass for this run's")

    def test_trend_status_is_recorded(self):
        _, meta, _ = self._main(True, [], name="trend")
        self.assertEqual(meta["trend"]["status"], "run")
        _, meta, _ = self._main(True, [], step=("sh", "-c", "exit 3"), name="trend")
        self.assertEqual(meta["trend"]["status"], "failed")

    def test_a_plan_without_a_trend_step_leaves_the_status_alone(self):
        _, meta, _ = self._main(True, [], name="quick")
        self.assertEqual(meta["trend"]["status"], "planned", "a step that never ran did not run")

    def test_every_steps_outcome_is_recorded_not_only_the_optional_ones(self):
        _, meta, _ = self._main(True, [], step=("sh", "-c", "exit 3"), name="scc")
        self.assertEqual(meta["steps"], {"scc": "failed"})
        _, meta, _ = self._main(True, [], name="git-sizer")
        self.assertEqual(meta["steps"], {"git-sizer": "run"})


class Budget(unittest.TestCase):
    def _main(self, extra, estimate, plan_calls):
        with tempfile.TemporaryDirectory() as d:
            _tiny_repo(d)
            c = console()
            def planner(repo, out, branch="HEAD", **kw):
                plan_calls.append(kw)
                return [{"name": "quick", "argv": ["sh", "-c", "true"], "stdout": None, "deps": []}]
            rc = cli.main([d, "--out", os.path.join(d, "out"), *extra], console=c,
                          tool_check=lambda **kw: [], planner=planner, estimator=lambda repo, interval, **kw: estimate)
            with open(os.path.join(d, "out", "meta.json")) as fh:
                meta = json.load(fh)
            return rc, c.export_text(), meta

    BIG = {"files": 80000, "samples": 11, "blames": 880000, "seconds": 400.0}
    SMALL = {"files": 100, "samples": 5, "blames": 500, "seconds": 0.4}
    SLOW = {"files": 28000, "samples": 3, "blames": 84000, "seconds": 390.0}

    def test_code_age_runs_by_default_and_plots_do_not(self):
        calls = []
        _, text, meta = self._main([], self.SMALL, calls)
        self.assertTrue(calls[0]["age"])
        self.assertFalse(calls[0]["plots"])
        self.assertEqual(meta["age"]["status"], "run")
        self.assertNotIn("skipped", text)

    def test_code_age_skipped_when_projected_time_exceeds_budget(self):
        calls = []
        rc, text, meta = self._main([], self.SLOW, calls)
        self.assertEqual(rc, 0)
        self.assertFalse(calls[0]["age"])
        self.assertIn("390", text)
        self.assertIn("60", text)
        self.assertIn("--deep", text)
        self.assertEqual(meta["age"]["status"], "skipped")
        self.assertEqual(meta["age"]["projected_seconds"], 390.0)

    def test_time_budget_flag_raises_the_threshold(self):
        calls = []
        self._main(["--time-budget", "600"], self.SLOW, calls)
        self.assertTrue(calls[0]["age"])

    def test_plots_flag_runs_theseus_under_budget(self):
        calls = []
        _, _, meta = self._main(["--plots"], self.SMALL, calls)
        self.assertTrue(calls[0]["plots"])
        self.assertEqual(meta["plots"]["status"], "run")

    def test_plots_skipped_when_files_times_samples_exceed_budget_but_age_still_runs(self):
        calls = []
        _, text, meta = self._main(["--plots"], {"files": 30000, "samples": 11, "blames": 330000}, calls)
        self.assertTrue(calls[0]["age"], "30,000 files is under the 50,000 budget")
        self.assertFalse(calls[0]["plots"])
        self.assertIn("330,000", text)
        self.assertEqual(meta["plots"]["status"], "skipped")

    def test_deep_forces_both_regardless_of_budget(self):
        calls = []
        self._main(["--deep", "--plots"], self.BIG, calls)
        self.assertTrue(calls[0]["age"])
        self.assertTrue(calls[0]["plots"])

    def test_budget_flag_applies_to_plots(self):
        calls = []
        self._main(["--plots", "--budget", "1000000", "--time-budget", "1000"], self.BIG, calls)
        self.assertTrue(calls[0]["plots"])

    def test_ignore_data_and_custom_ignores_reach_the_planner(self):
        calls = []
        self._main(["--ignore-data", "--ignore", "docs/**"], self.SMALL, calls)
        self.assertIn("*.csv", calls[0]["ignore"])
        self.assertIn("docs/**", calls[0]["ignore"])

    def test_no_ignores_by_default(self):
        calls = []
        self._main([], self.SMALL, calls)
        self.assertEqual(list(calls[0]["ignore"]), [])


class Interrupt(unittest.TestCase):
    def test_keyboard_interrupt_kills_steps_and_exits_130(self):
        import threading, time, signal
        with tempfile.TemporaryDirectory() as d:
            _tiny_repo(d)
            marker = os.path.join(d, "finished")
            planner = lambda repo, out, branch="HEAD", **kw: [
                {"name": "slow", "argv": ["sh", "-c", f"sleep 5; touch {marker}"], "stdout": None, "deps": []}]
            c = console()
            box = {}
            def go():
                box["rc"] = cli.main([d, "--out", os.path.join(d, "out")], console=c, tool_check=lambda **kw: [], planner=planner,
                                     estimator=lambda repo, interval, **kw: {"files": 1, "samples": 1, "blames": 1, "seconds": 0.0})
            t = threading.Thread(target=go)
            t.start()
            time.sleep(0.5)
            cli.interrupt()          # what the SIGINT handler does
            t.join(5)
            self.assertFalse(t.is_alive(), "gitmole must exit promptly after Ctrl-C")
            time.sleep(0.2)
            self.assertFalse(os.path.exists(marker))
        self.assertEqual(box["rc"], 130)
        self.assertIn("interrupted", c.export_text())


class Timeout(unittest.TestCase):
    def test_timed_out_step_is_reported(self):
        with tempfile.TemporaryDirectory() as d:
            _tiny_repo(d)
            c = console()
            planner = lambda repo, out, branch="HEAD", **kw: [
                {"name": "sleepy", "argv": ["sh", "-c", "sleep 3"], "stdout": None, "deps": []}]
            cli.main([d, "--out", os.path.join(d, "out"), "--timeout", "0.3"], console=c,
                     tool_check=lambda **kw: [], planner=planner, estimator=lambda repo, interval, **kw: {"files": 1, "samples": 1, "blames": 1})
            text = c.export_text()
        self.assertIn("sleepy (timeout)", text)

    def test_a_timed_out_step_is_recorded_in_meta(self):
        with tempfile.TemporaryDirectory() as d:
            _tiny_repo(d)
            out = os.path.join(d, "out")
            planner = lambda repo, o, branch="HEAD", **kw: [{"name": "scc", "argv": ["sh", "-c", "sleep 3"], "stdout": None, "deps": []}]
            cli.main([d, "--out", out, "--timeout", "0.3"], console=console(), tool_check=lambda **kw: [], planner=planner,
                     estimator=lambda repo, interval, **kw: {"files": 1, "samples": 1, "blames": 1})
            with open(os.path.join(out, "meta.json")) as fh:
                self.assertEqual(json.load(fh)["steps"], {"scc": "timeout"})


def _report_dir(out, identities=None):
    with open(os.path.join(out, "meta.json"), "w") as fh:
        json.dump({"name": "demo", "commits": 5, "identities": identities or []}, fh)


class Export(unittest.TestCase):
    def test_json_export_to_file(self):
        with tempfile.TemporaryDirectory() as out:
            _report_dir(out)
            c = console()
            rc = cli.main([out, "--no-run", "--json", os.path.join(out, "r.json")], console=c)
            with open(os.path.join(out, "r.json")) as fh:
                d = json.load(fh)
        self.assertEqual(rc, 0)
        self.assertEqual(d["meta"]["name"], "demo")
        self.assertIn("findings", d)
        self.assertIn("demo", c.export_text(), "the terminal report still prints when exporting to a file")

    def test_markdown_to_stdout_replaces_the_terminal_report(self):
        with tempfile.TemporaryDirectory() as out:
            _report_dir(out)
            c = Console(file=io.StringIO(), width=100, record=True, force_terminal=True, color_system="truecolor")
            rc = cli.main([out, "--no-run", "--markdown", "-"], console=c)
            text = c.export_text()
        self.assertEqual(rc, 0)
        self.assertTrue(text.startswith("# demo"), text[:40])
        self.assertNotIn("╭", text)
        self.assertNotIn("███╗", text, "no banner when piping an export to stdout")

    def test_sarif_export_to_file_and_to_stdout_with_a_scope(self):
        ids = [{"name": "Your Name", "email": "you@example.com", "commits": 5, "aliases": []}]
        with tempfile.TemporaryDirectory() as out:
            _report_dir(out, ids)
            c = console()
            rc = cli.main([out, "--no-run", "--sarif", os.path.join(out, "r.sarif")], console=c)
            with open(os.path.join(out, "r.sarif")) as fh:
                d = json.load(fh)
            self.assertEqual(rc, 0)
            self.assertEqual(d["version"], "2.1.0")
            self.assertEqual(d["runs"][0]["tool"]["driver"]["name"], "gitmole")
            self.assertEqual([r["id"] for r in d["runs"][0]["tool"]["driver"]["rules"]], ["placeholder_identity"])
            self.assertEqual(d["runs"][0]["properties"]["scope"], "head")
            self.assertIn("demo", c.export_text(), "the terminal report still prints when exporting to a file")
            c = Console(file=io.StringIO(), width=100, record=True, force_terminal=True, color_system="truecolor")
            rc = cli.main([out, "--no-run", "--sarif", "-", "--sarif-scope", "history"], console=c)
            text = c.export_text()
        self.assertEqual(rc, 0)
        self.assertEqual(json.loads(text)["runs"][0]["properties"]["scope"], "history")
        self.assertNotIn("███╗", text, "no banner when piping an export to stdout")

    def test_fail_on_returns_3_when_a_finding_reaches_the_level(self):
        ids = [{"name": "Your Name", "email": "you@example.com", "commits": 5, "aliases": []}]
        with tempfile.TemporaryDirectory() as out:
            _report_dir(out, ids)
            self.assertEqual(cli.main([out, "--no-run", "--fail-on", "warning"], console=console()), 3)
            self.assertEqual(cli.main([out, "--no-run", "--fail-on", "critical"], console=console()), 0)
            self.assertEqual(cli.main([out, "--no-run"], console=console()), 0)


class Portfolio(unittest.TestCase):
    def _run(self, extra=(), fail=False):
        with tempfile.TemporaryDirectory() as work:
            def cloner(target, parent):
                d = os.path.join(parent, target.split("/")[-1])
                os.makedirs(d)
                _tiny_repo(d)
                if target.endswith("two"):
                    import subprocess
                    subprocess.run(["git", "-C", d, "-c", "user.name=Your Name", "-c", "user.email=you@example.com",
                                    "commit", "-q", "--allow-empty", "-m", "x"], check=True)
                return d
            planner = lambda repo, out, branch="HEAD", **kw: [{"name": "q", "argv": ["true"], "stdout": None, "deps": []}]
            c = console()
            rc = cli.main(["acme/*", "--out", os.path.join(work, "pf"), *extra], console=c, tool_check=lambda **kw: [], planner=planner,
                          estimator=lambda repo, interval, **kw: {"files": 1, "samples": 1, "blames": 1},
                          lister=lambda owner: ["one", "two"], cloner=cloner)
            text = c.export_text()
            dirs = sorted(os.listdir(os.path.join(work, "pf")))
            has_meta = all(os.path.isfile(os.path.join(work, "pf", d, "meta.json")) for d in dirs)
            md = os.path.join(work, "pf", "portfolio.md")
            md_text = pathlib.Path(md).read_text() if os.path.exists(md) else ""
        return rc, text, dirs, has_meta, md_text

    def test_runs_every_repo_and_prints_one_summary_table(self):
        rc, text, dirs, has_meta, _ = self._run()
        self.assertEqual(rc, 0)
        self.assertEqual(dirs, ["one", "two"])
        self.assertTrue(has_meta)
        self.assertIn("Portfolio", text)
        self.assertIn("one", text)
        self.assertIn("two", text)
        self.assertIn("Unconfigured git identity", text, "worst finding per repo is shown")

    def test_fail_on_looks_across_all_repos(self):
        rc, *_ = self._run(["--fail-on", "warning"])
        self.assertEqual(rc, 3)

    def test_markdown_export_writes_a_portfolio_file(self):
        rc, _, _, _, md = self._run(["--markdown", "portfolio.md"])
        self.assertEqual(rc, 0)
        self.assertTrue(md.startswith("# acme"), md[:40])
        self.assertIn("| repo |", md)

    def test_an_unreadable_repo_is_reported_and_skipped_not_a_traceback(self):
        from unittest.mock import patch

        from gitmole import load
        real_load_report = load.load_report

        def flaky(out_dir, *a, **kw):
            if os.path.basename(out_dir) == "one":
                raise load.Unreadable("x is truncated or not JSON; run gitmole again")
            return real_load_report(out_dir, *a, **kw)

        with patch("gitmole.cli.load.load_report", side_effect=flaky):
            rc, text, dirs, has_meta, _ = self._run()
        self.assertEqual(rc, 0)
        self.assertEqual(dirs, ["one", "two"], "one's meta.json was still written to disk; only re-loading it failed")
        self.assertIn("x is truncated or not JSON; run gitmole again; skipped", text)
        self.assertIn("two", text, "the other repository still appears in the summary table")


class GhFailures(unittest.TestCase):
    def test_listing_failure_is_reported_cleanly(self):
        def lister(owner):
            raise run.GhError("Post https://api.github.com/graphql: tls: failed to verify certificate")
        c = console()
        rc = cli.main(["acme/*"], console=c, tool_check=lambda **kw: [], lister=lister)
        text = c.export_text()
        self.assertEqual(rc, 2)
        self.assertIn("could not list repositories for acme", text)
        self.assertIn("failed to verify certificate", text)

    def test_clone_failure_is_reported_cleanly(self):
        def cloner(target, parent):
            raise run.GhError("repository not found")
        c = console()
        rc = cli.main(["acme/missing"], console=c, tool_check=lambda **kw: [], cloner=cloner)
        text = c.export_text()
        self.assertEqual(rc, 2)
        self.assertIn("could not clone acme/missing", text)
        self.assertIn("repository not found", text)


class TempClones(unittest.TestCase):
    """A remote or portfolio run removes the temp parent it cloned into, whatever happened in between."""

    def _cloner(self, parents):
        def cloner(target, parent):
            parents.append(parent)
            d = os.path.join(parent, target.split("/")[-1])
            os.makedirs(d)
            _tiny_repo(d)
            return d
        return cloner

    def _planner(self, argv):
        return lambda repo, out, branch="HEAD", **kw: [{"name": "q", "argv": argv, "stdout": None, "deps": []}]

    def test_remote_run_removes_its_clone_on_success(self):
        parents = []
        with tempfile.TemporaryDirectory() as work:
            rc = cli.main(["acme/widgets", "--out", os.path.join(work, "out")], console=console(), tool_check=lambda **kw: [],
                          planner=self._planner(["true"]), estimator=lambda repo, interval, **kw: {"files": 1, "samples": 1, "blames": 1},
                          cloner=self._cloner(parents))
        self.assertEqual(rc, 0)
        self.assertEqual(len(parents), 1)
        self.assertFalse(os.path.exists(parents[0]))

    def test_remote_run_removes_its_clone_when_a_step_fails(self):
        parents = []
        with tempfile.TemporaryDirectory() as work:
            cli.main(["acme/widgets", "--out", os.path.join(work, "out")], console=console(), tool_check=lambda **kw: [],
                     planner=self._planner(["false"]), estimator=lambda repo, interval, **kw: {"files": 1, "samples": 1, "blames": 1},
                     cloner=self._cloner(parents))
        self.assertFalse(os.path.exists(parents[0]))

    def test_failed_clone_leaves_no_parent(self):
        parents = []
        def cloner(target, parent):
            parents.append(parent)
            raise run.GhError("repository not found")
        rc = cli.main(["acme/missing"], console=console(), tool_check=lambda **kw: [], cloner=cloner)
        self.assertEqual(rc, 2)
        self.assertFalse(os.path.exists(parents[0]))

    def test_portfolio_run_removes_its_parent(self):
        parents = []
        with tempfile.TemporaryDirectory() as work:
            rc = cli.main(["acme/*", "--out", os.path.join(work, "pf")], console=console(), tool_check=lambda **kw: [],
                          planner=self._planner(["true"]), estimator=lambda repo, interval, **kw: {"files": 1, "samples": 1, "blames": 1},
                          lister=lambda owner: ["one", "two"], cloner=self._cloner(parents))
        self.assertEqual(rc, 0)
        self.assertEqual(len(set(parents)), 1)
        self.assertFalse(os.path.exists(parents[0]))


class FileTypes(unittest.TestCase):
    def test_list_file_types_prints_the_tree_and_exits(self):
        with tempfile.TemporaryDirectory() as d:
            _tiny_repo(d)
            for name in ["a.py", "notes.md"]:
                with open(os.path.join(d, name), "w") as fh: fh.write("x\n")
            import subprocess
            subprocess.run(["git", "-C", d, "add", "-A"], check=True)
            c = console()
            rc = cli.main([d, "--list-file-types"], console=c, tool_check=lambda **kw: [])
            text = c.export_text()
        self.assertEqual(rc, 0)
        self.assertRegex(text, r"\n▥ File types\n")
        self.assertRegex(text, r"py\s+1\s+yes")
        self.assertRegex(text, r"md\s+1\s+no")
        self.assertNotIn("Findings", text)

    def test_list_file_types_refuses_a_remote_target(self):
        c = console()
        rc = cli.main(["owner/repo", "--list-file-types"], console=c, tool_check=lambda **kw: [])
        self.assertEqual(rc, 2)
        self.assertIn("--list-file-types needs a local path", c.export_text())

    def test_file_types_reach_the_planner(self):
        calls = []
        with tempfile.TemporaryDirectory() as d:
            _tiny_repo(d)
            def planner(repo, out, branch="HEAD", **kw):
                calls.append(kw)
                return [{"name": "q", "argv": ["true"], "stdout": None, "deps": []}]
            cli.main([d, "--out", os.path.join(d, "out"), "--file-types", "py, sql"], console=console(), tool_check=lambda **kw: [],
                     planner=planner, estimator=lambda repo, interval, **kw: {"files": 1, "samples": 1, "blames": 1, "seconds": 0.0})
        self.assertEqual(calls[0]["types"], "py,sql")

    def test_meta_records_the_file_types_so_a_re_render_filters_the_same_way(self):
        def meta_for(*extra):
            with tempfile.TemporaryDirectory() as d:
                _tiny_repo(d)
                out = os.path.join(d, "out")
                planner = lambda repo, o, branch="HEAD", **kw: [{"name": "q", "argv": ["true"], "stdout": None, "deps": []}]
                cli.main([d, "--out", out, *extra], console=console(), tool_check=lambda **kw: [], planner=planner,
                         estimator=lambda repo, interval, **kw: {"files": 1, "samples": 1, "blames": 1, "seconds": 0.0})
                with open(os.path.join(out, "meta.json")) as fh:
                    return json.load(fh)
        self.assertIsNone(meta_for()["file_types"])
        self.assertEqual(meta_for("--file-types", "py, sql")["file_types"], "py,sql")
        self.assertEqual(meta_for("--file-types", "all")["file_types"], "all")


class GoneWindow(unittest.TestCase):
    def _meta(self, *extra):
        with tempfile.TemporaryDirectory() as d:
            _tiny_repo(d)
            out = os.path.join(d, "out")
            planner = lambda repo, o, branch="HEAD", **kw: [{"name": "q", "argv": ["true"], "stdout": None, "deps": []}]
            cli.main([d, "--out", out, *extra], console=console(), tool_check=lambda **kw: [], planner=planner,
                     estimator=lambda repo, interval, **kw: {"files": 1, "samples": 1, "blames": 1, "seconds": 0.0})
            with open(os.path.join(out, "meta.json")) as fh:
                return json.load(fh)

    def test_default_twelve_months_recorded_and_flag_changes_it(self):
        self.assertEqual(self._meta()["gone_months"], 12)
        self.assertEqual(self._meta("--gone", "6")["gone_months"], 6)

    def test_the_default_is_the_window_the_loss_module_defines(self):
        from gitmole import loss
        self.assertEqual(cli.parse_args(["x"]).gone, loss.DEFAULT_MONTHS)


class Duplicates(unittest.TestCase):
    def _main(self, extra, estimate, plan_calls):
        with tempfile.TemporaryDirectory() as d:
            _tiny_repo(d)
            c = console()
            def planner(repo, out, branch="HEAD", **kw):
                plan_calls.append(kw)
                return [{"name": "duplicates", "argv": ["sh", "-c", "true"], "stdout": None, "deps": []}]
            rc = cli.main([d, "--out", os.path.join(d, "out"), *extra], console=c, tool_check=lambda **kw: [], planner=planner,
                          estimator=lambda repo, interval, **kw: estimate)
            with open(os.path.join(d, "out", "meta.json")) as fh:
                meta = json.load(fh)
        return rc, c.export_text(), meta

    SMALL = {"files": 100, "samples": 5, "blames": 500, "seconds": 0.4, "text_bytes": 34_000_000}
    HUGE = {"files": 40000, "samples": 5, "blames": 500, "seconds": 0.4, "text_bytes": 171_000_000}

    def test_on_by_default_and_recorded(self):
        calls = []
        _, text, meta = self._main([], self.SMALL, calls)
        self.assertTrue(calls[0]["duplicates"])
        self.assertEqual(meta["duplicates"], {"status": "run", "text_mb": 34.0, "budget_mb": run.DUPLICATES_BUDGET_MB})
        self.assertNotIn("duplicates skipped", text)

    def test_skipped_over_the_text_budget_unless_deep(self):
        calls = []
        _, text, meta = self._main([], self.HUGE, calls)
        self.assertFalse(calls[0]["duplicates"])
        self.assertEqual(meta["duplicates"]["status"], "skipped")
        self.assertIn("duplicates skipped: 171 MB of tracked text is over the 80 MB budget", text)
        self.assertIn("jscpd would need about 7 GB", text)
        self.assertIn("--deep", text)
        calls = []
        _, text, meta = self._main(["--deep"], self.HUGE, calls)
        self.assertTrue(calls[0]["duplicates"])
        self.assertEqual(meta["duplicates"]["status"], "run")

    def test_an_estimate_without_a_text_size_runs_it(self):
        calls = []
        self._main([], {"files": 1, "samples": 1, "blames": 1, "seconds": 0.0}, calls)
        self.assertTrue(calls[0]["duplicates"])

    def test_the_old_flag_still_parses(self):
        self.assertTrue(cli.parse_args(["x", "--duplicates"]).duplicates, "an older CI line must not break")


class ReferenceDate(unittest.TestCase):
    def _main(self, env, extra=()):
        from unittest.mock import patch
        calls = []
        with tempfile.TemporaryDirectory() as d, patch.dict(os.environ, env):
            _tiny_repo(d)
            def planner(repo, out, branch="HEAD", **kw):
                calls.append(kw)
                return [{"name": "q", "argv": ["true"], "stdout": None, "deps": []}]
            c = console()
            rc = cli.main([d, "--out", os.path.join(d, "out"), *extra], console=c, tool_check=lambda **kw: [], planner=planner,
                          estimator=lambda repo, interval, **kw: {"files": 1, "samples": 1, "blames": 1, "seconds": 0.0})
            meta_path = os.path.join(d, "out", "meta.json")
            meta = json.loads(pathlib.Path(meta_path).read_text()) if os.path.exists(meta_path) else {}
        return rc, c.export_text(), calls, meta

    def test_env_override_is_forwarded_recorded_and_announced(self):
        rc, text, calls, meta = self._main({"GITMOLE_NOW": "2025-06-15"})
        self.assertEqual(rc, 0)
        self.assertEqual(calls[0]["now"], "2025-06-15")
        self.assertEqual(meta["now"], "2025-06-15")
        self.assertIn("2025-06-15", text)

    def test_absent_override_means_today_and_nothing_recorded(self):
        rc, text, calls, meta = self._main({})
        self.assertIsNone(calls[0]["now"])
        self.assertNotIn("now", meta)

    def test_malformed_override_is_an_error(self):
        rc, text, calls, meta = self._main({"GITMOLE_NOW": "2025-6-15"})
        self.assertEqual(rc, 2)
        self.assertIn("GITMOLE_NOW", text)
        self.assertEqual(calls, [])


class Since(unittest.TestCase):
    def _main(self, extra, env=None):
        from unittest.mock import patch
        calls = []
        with tempfile.TemporaryDirectory() as d, patch.dict(os.environ, env or {}):
            _tiny_repo(d)
            def planner(repo, out, branch="HEAD", **kw):
                calls.append(kw)
                return [{"name": "q", "argv": ["true"], "stdout": None, "deps": []}]
            c = console()
            rc = cli.main([d, "--out", os.path.join(d, "out"), *extra], console=c, tool_check=lambda **kw: [], planner=planner,
                          estimator=lambda repo, interval, **kw: {"files": 1, "samples": 1, "blames": 1, "seconds": 0.0})
            meta_path = os.path.join(d, "out", "meta.json")
            meta = json.loads(pathlib.Path(meta_path).read_text()) if os.path.exists(meta_path) else {}
        return rc, c.export_text(), calls, meta

    def test_since_is_resolved_against_the_reference_date_and_recorded(self):
        rc, text, calls, meta = self._main(["--since", "2y"], {"GITMOLE_NOW": "2026-09-15"})
        self.assertEqual(rc, 0)
        self.assertEqual(calls[0]["since"], "2024-09-15")
        self.assertEqual(meta["since"], "2024-09-15")
        self.assertIn("since 2024-09-15", text)

    def test_bad_since_is_an_error(self):
        rc, text, calls, meta = self._main(["--since", "lately"])
        self.assertEqual(rc, 2)
        self.assertIn("--since", text)
        self.assertEqual(calls, [])

    def test_empty_window_is_an_error_not_an_empty_report(self):
        rc, text, calls, meta = self._main(["--since", "2030-01-01"])
        self.assertEqual(rc, 2)
        self.assertIn("no commits", text)
        self.assertEqual(calls, [])

    def test_since_is_refused_with_no_run(self):
        with tempfile.TemporaryDirectory() as out:
            _report_dir(out)
            c = console()
            rc = cli.main([out, "--no-run", "--since", "2y"], console=c)
        self.assertEqual(rc, 2)
        self.assertIn("--since", c.export_text())


class FullFlag(unittest.TestCase):
    def test_full_shows_the_score_column(self):
        with tempfile.TemporaryDirectory() as out:
            _report_dir(out)
            with open(os.path.join(out, "maat-revisions.csv"), "w") as fh:
                fh.write("entity,n-revs\na.py,3\n")
            with open(os.path.join(out, "size.json"), "w") as fh:
                json.dump([{"Name": "Python", "Count": 1, "Code": 10, "Comment": 0, "Blank": 0, "Complexity": 1,
                            "Files": [{"Location": "a.py", "Code": 10, "Complexity": 1}]}], fh)
            compact = console(); cli.main([out, "--no-run"], console=compact)
            full = console(); cli.main([out, "--no-run", "--full"], console=full)
        self.assertNotIn("score", compact.export_text())
        self.assertIn("score", full.export_text())


class Arguments(unittest.TestCase):
    def test_bad_target_is_reported_not_raised(self):
        c = console()
        rc = cli.main(["definitely not a repo"], console=c)
        self.assertEqual(rc, 2)
        self.assertIn("not a repo", c.export_text())

    def test_non_repo_directory_is_reported_not_raised(self):
        with tempfile.TemporaryDirectory() as d:
            target = os.path.join(d, "checkouts")
            os.mkdir(target)
            c = console()
            rc = cli.main([target], console=c, tool_check=lambda **kw: [])
            created = os.listdir(d)
        self.assertEqual(rc, 2)
        self.assertIn("not a git repository", c.export_text())
        self.assertEqual(created, ["checkouts"])   # no analysis-checkouts/ next to a bad target

    def test_missing_tools_are_listed(self):
        with tempfile.TemporaryDirectory() as d:
            _tiny_repo(d)
            c = console()
            rc = cli.main([d], console=c, tool_check=lambda **kw: ["scc"])
        text = c.export_text()
        self.assertEqual(rc, 2)
        self.assertIn("scc", text)
        self.assertIn("brew install scc git-sizer betterleaks jscpd osv-scanner", text)
        self.assertNotIn("jar", text)


class GeneratedFiles(unittest.TestCase):
    def test_a_run_records_the_generated_files_in_meta(self):
        with tempfile.TemporaryDirectory() as d:
            _tiny_repo(d)
            os.makedirs(os.path.join(d, "lib"))
            with open(os.path.join(d, "lib", "validator.js"), "w") as fh:
                fh.write("// This file is autogenerated by build/build.js, do not edit\nmodule.exports = 1\n")
            with open(os.path.join(d, "lib", "app.js"), "w") as fh:
                fh.write("module.exports = 2\n")
            import subprocess
            subprocess.run(["git", "-C", d, "add", "-A"], check=True)
            subprocess.run(["git", "-C", d, "-c", "user.name=T", "-c", "user.email=t@x.com", "commit", "-q", "-m", "files"], check=True)
            out = os.path.join(d, "out")
            planner = lambda repo, o, branch="HEAD", **kw: [{"name": "q", "argv": ["true"], "stdout": None, "deps": []}]
            rc = cli.main([d, "--out", out], console=console(), tool_check=lambda **kw: [], planner=planner,
                          estimator=lambda repo, interval, **kw: {"files": 2, "samples": 1, "blames": 2})
            with open(os.path.join(out, "meta.json")) as fh:
                meta = json.load(fh)
        self.assertEqual(rc, 0)
        self.assertEqual(meta["generated"], ["lib/validator.js"])
        self.assertEqual(meta["vendored"], [], "no nested licence, nothing vendored by licence")

    def test_a_run_records_the_vendored_dirs_in_meta(self):
        with tempfile.TemporaryDirectory() as d:
            _tiny_repo(d)
            os.makedirs(os.path.join(d, "ext", "gtest"))
            with open(os.path.join(d, "LICENSE"), "w") as fh:
                fh.write("Copyright (c) 2020 Ann Example\n")
            with open(os.path.join(d, "ext", "gtest", "LICENSE"), "w") as fh:
                fh.write("Copyright 2008, Google Inc.\n")
            with open(os.path.join(d, "ext", "gtest", "gtest.cc"), "w") as fh:
                fh.write("int x;\n")
            import subprocess
            subprocess.run(["git", "-C", d, "add", "-A"], check=True)
            subprocess.run(["git", "-C", d, "-c", "user.name=T", "-c", "user.email=t@x.com", "commit", "-q", "-m", "files"], check=True)
            out = os.path.join(d, "out")
            planner = lambda repo, o, branch="HEAD", **kw: [{"name": "q", "argv": ["true"], "stdout": None, "deps": []}]
            rc = cli.main([d, "--out", out], console=console(), tool_check=lambda **kw: [], planner=planner,
                          estimator=lambda repo, interval, **kw: {"files": 2, "samples": 1, "blames": 2})
            with open(os.path.join(out, "meta.json")) as fh:
                meta = json.load(fh)
        self.assertEqual(rc, 0)
        self.assertEqual(meta["vendored"], ["ext/gtest/"])

    def _repo_with(self, repo, files):
        import subprocess
        subprocess.run(["git", "init", "-q", repo], check=True)
        for path, content in files.items():
            full = os.path.join(repo, path)
            os.makedirs(os.path.dirname(full), exist_ok=True)
            with open(full, "w") as fh:
                fh.write(content)
        subprocess.run(["git", "-C", repo, "add", "-A"], check=True)
        subprocess.run(["git", "-C", repo, "-c", "user.name=t", "-c", "user.email=t@x", "commit", "-q", "-m", "init"], check=True)

    _stub_planner = staticmethod(lambda repo, o, branch="HEAD", **kw: [{"name": "q", "argv": ["true"], "stdout": None, "deps": []}])

    def test_a_run_records_the_coverage_by_reason_over_every_tracked_text_file(self):
        with tempfile.TemporaryDirectory() as d:
            repo = os.path.join(d, "r")
            self._repo_with(repo, {"src/a.py": "x = 1\n", "tests/test_a.py": "x = 1\n", "README.md": "hi\n", "gen/b.py": "# @generated\nx = 1\n"})
            out = os.path.join(d, "out")
            rc = cli.main([repo, "--out", out, "--ignore", "gen/*"], console=console(), tool_check=lambda **kw: [], planner=self._stub_planner,
                          estimator=lambda repo, interval, **kw: {"files": 1, "samples": 1, "blames": 1, "seconds": 0.0})
            self.assertEqual(rc, 0)
            with open(os.path.join(out, "meta.json")) as fh:
                meta = json.load(fh)
        self.assertEqual(meta["generated"], ["gen/b.py"], "--ignore shapes blame and functions, never the classifier")
        self.assertEqual(meta["coverage"], {"scored": 1, "test file": 1, "not a source type": 1, "generated": 1},
                         "no size.json from the stub planner: nothing counts as not counted by scc, and every tracked text file is placed")

    def test_a_run_records_the_credential_shaped_files_in_meta(self):
        with tempfile.TemporaryDirectory() as d:
            repo = os.path.join(d, "r")
            self._repo_with(repo, {".env.production": "SECRET=1\n", ".env.example": "SECRET=\n"})
            out = os.path.join(d, "out")
            rc = cli.main([repo, "--out", out], console=console(), tool_check=lambda **kw: [], planner=self._stub_planner,
                          estimator=lambda repo, interval, **kw: {"files": 2, "samples": 1, "blames": 2})
            self.assertEqual(rc, 0)
            with open(os.path.join(out, "meta.json")) as fh:
                meta = json.load(fh)
        self.assertEqual(meta["credential_files"], [".env.production"])


class Clean(unittest.TestCase):
    """--clean lists what gitmole left behind and deletes on a yes. TMPDIR is pointed at a scratch dir so the
    real temp folder is never listed or touched."""

    def _with_tmp(self, fn):
        with tempfile.TemporaryDirectory() as work, tempfile.TemporaryDirectory() as tmp:
            old = os.environ.get("TMPDIR")
            os.environ["TMPDIR"] = tmp
            try:
                return fn(work, tmp)
            finally:
                if old is None:
                    del os.environ["TMPDIR"]
                else:
                    os.environ["TMPDIR"] = old

    def _output(self, path):
        os.makedirs(path)
        with open(os.path.join(path, "meta.json"), "w") as fh:
            fh.write("{}")

    def test_nothing_to_clean(self):
        def go(work, tmp):
            c = console()
            rc = cli.main(["--clean", work], console=c)
            return rc, c.export_text()
        rc, text = self._with_tmp(go)
        self.assertEqual(rc, 0)
        self.assertIn("nothing to clean", text)

    def test_lists_then_keeps_on_anything_but_yes(self):
        def go(work, tmp):
            self._output(os.path.join(work, "analysis-a"))
            os.makedirs(os.path.join(tmp, "gitmole-x"))
            c = Console(file=io.StringIO(), width=120, record=True, force_terminal=True, color_system=None)
            asked = []
            rc = cli.main(["--clean", work], console=c, ask=lambda q: asked.append(q) or "n")
            return rc, c.export_text(), asked, os.path.isdir(os.path.join(work, "analysis-a")), os.path.isdir(os.path.join(tmp, "gitmole-x"))
        rc, text, asked, out_kept, tmp_kept = self._with_tmp(go)
        self.assertEqual(rc, 0)
        self.assertIn("Left behind", text)
        self.assertIn("analysis-a", text)
        self.assertIn("gitmole-* (1 temp clone)", text, "temp clones collapse to one row per temp folder")
        self.assertNotIn("gitmole-x", text)
        self.assertEqual(len(asked), 1)
        self.assertIn("Delete 2 directories", asked[0])
        self.assertIn("kept", text)
        self.assertTrue(out_kept)
        self.assertTrue(tmp_kept)

    def test_full_lists_every_temp_clone(self):
        def go(work, tmp):
            os.makedirs(os.path.join(tmp, "gitmole-x"))
            os.makedirs(os.path.join(tmp, "gitmole-y"))
            c = Console(file=io.StringIO(), width=120, record=True, force_terminal=True, color_system=None)
            rc = cli.main(["--clean", work, "--full"], console=c, ask=lambda q: "n")
            return rc, c.export_text()
        rc, text = self._with_tmp(go)
        self.assertEqual(rc, 0)
        self.assertIn("gitmole-x", text)
        self.assertIn("gitmole-y", text)
        self.assertNotIn("temp clones", text)

    def test_rows_stay_on_one_line_at_a_narrow_width(self):
        def go(work, tmp):
            deep = os.path.join(work, "some", "rather", "long", "chain", "of", "directories")
            self._output(os.path.join(deep, "analysis-widgets"))
            os.makedirs(os.path.join(tmp, "gitmole-x"))
            c = Console(file=io.StringIO(), width=60, record=True, force_terminal=True, color_system=None)
            rc = cli.main(["--clean", deep], console=c, ask=lambda q: "n")
            return rc, c.export_text()
        rc, text = self._with_tmp(go)
        self.assertEqual(rc, 0)
        rows = [line for line in text.splitlines() if line.strip().startswith("/")]
        self.assertEqual(len(rows), 2, text)
        self.assertTrue(any("analysis-widgets" in r and "…/" in r for r in rows), text)
        self.assertTrue(all(" B " in r and "2026-" in r for r in rows), "each row carries its size and date on the same line:\n" + text)

    def test_yes_answer_removes_and_reports(self):
        def go(work, tmp):
            self._output(os.path.join(work, "analysis-a"))
            os.makedirs(os.path.join(tmp, "gitmole-x"))
            c = Console(file=io.StringIO(), width=120, record=True, force_terminal=True, color_system=None)
            rc = cli.main(["--clean", work], console=c, ask=lambda q: "Y")
            return rc, c.export_text(), os.listdir(work), os.listdir(tmp)
        rc, text, work_left, tmp_left = self._with_tmp(go)
        self.assertEqual(rc, 0)
        self.assertIn("removed 2 directories", text)
        self.assertEqual(work_left, [])
        self.assertEqual(tmp_left, [])

    def test_default_base_is_the_current_directory(self):
        def go(work, tmp):
            self._output(os.path.join(work, "analysis-a"))
            here = os.getcwd()
            os.chdir(work)
            try:
                c = console()
                rc = cli.main(["--clean", "--yes"], console=c)
            finally:
                os.chdir(here)
            return rc, os.listdir(work)
        rc, left = self._with_tmp(go)
        self.assertEqual(rc, 0)
        self.assertEqual(left, [])

    def test_no_terminal_lists_and_refuses_without_yes(self):
        def go(work, tmp):
            self._output(os.path.join(work, "analysis-a"))
            c = console()   # force_terminal=False
            rc = cli.main(["--clean", work], console=c, ask=lambda q: self.fail("must not ask"))
            return rc, c.export_text(), os.path.isdir(os.path.join(work, "analysis-a"))
        rc, text, kept = self._with_tmp(go)
        self.assertEqual(rc, 2)
        self.assertIn("analysis-a", text)
        self.assertIn("needs a terminal", text)
        self.assertIn("--yes", text)
        self.assertTrue(kept)

    def test_yes_flag_skips_the_question(self):
        def go(work, tmp):
            self._output(os.path.join(work, "analysis-a"))
            c = console()
            rc = cli.main(["--clean", work, "--yes"], console=c, ask=lambda q: self.fail("must not ask"))
            return rc, c.export_text(), os.listdir(work)
        rc, text, left = self._with_tmp(go)
        self.assertEqual(rc, 0)
        self.assertIn("removed 1 directory", text)
        self.assertEqual(left, [])

    def test_yes_without_clean_is_an_error(self):
        c = console()
        rc = cli.main([".", "--yes"], console=c)
        self.assertEqual(rc, 2)
        self.assertIn("--yes needs --clean", c.export_text())

    def test_no_target_without_clean_is_an_error(self):
        c = console()
        rc = cli.main([], console=c)
        self.assertEqual(rc, 2)
        self.assertIn("target required", c.export_text())


class Risk(unittest.TestCase):
    def _repo(self, d):
        import subprocess
        def git(*args):
            e = dict(os.environ, GIT_CONFIG_GLOBAL="/dev/null", GIT_CONFIG_SYSTEM="/dev/null",
                     GIT_AUTHOR_NAME="A", GIT_AUTHOR_EMAIL="a@x", GIT_COMMITTER_NAME="A", GIT_COMMITTER_EMAIL="a@x")
            subprocess.run(["git", *args], cwd=d, check=True, capture_output=True, env=e)
        git("init", "-q", "-b", "main")
        with open(os.path.join(d, "a.py"), "w") as fh: fh.write("x\n")
        git("add", "-A"); git("commit", "-q", "-m", "base")
        git("switch", "-q", "-c", "feature")
        with open(os.path.join(d, "a.py"), "a") as fh: fh.write("y\n")
        git("commit", "-q", "-am", "work")

    def test_risk_section_after_a_run_and_on_a_re_render(self):
        with tempfile.TemporaryDirectory() as d:
            self._repo(d)
            out = os.path.join(d, "out")
            planner = lambda repo, o, branch="HEAD", **kw: [{"name": "q", "argv": ["true"], "stdout": None, "deps": []}]
            c = console()
            rc = cli.main([d, "--out", out, "--risk", "main"], console=c, tool_check=lambda **kw: [], planner=planner,
                          estimator=lambda repo, interval, **kw: {"files": 1, "samples": 1, "blames": 1, "seconds": 0.0})
            self.assertEqual(rc, 0)
            text = c.export_text()
            self.assertIn("Change risk (1 files since main)", text)
            self.assertRegex(text, r"a\.py\s+no revisions on record", "the stub planner writes no size.json and no log, so a.py has no scc row and no revisions")
            c = console()
            rc = cli.main([out, "--no-run", "--risk", "main"], console=c)
            self.assertEqual(rc, 0)
            text = c.export_text()
            self.assertIn("Change risk (1 files since main)", text)
            self.assertRegex(text, r"a\.py\s+no revisions on record", "the stub planner writes no size.json and no log, so a.py has no scc row and no revisions")

    def test_unknown_base_is_an_error(self):
        with tempfile.TemporaryDirectory() as d:
            self._repo(d)
            out = os.path.join(d, "out")
            planner = lambda repo, o, branch="HEAD", **kw: [{"name": "q", "argv": ["true"], "stdout": None, "deps": []}]
            c = console()
            rc = cli.main([d, "--out", out, "--risk", "nope"], console=c, tool_check=lambda **kw: [], planner=planner,
                          estimator=lambda repo, interval, **kw: {"files": 1, "samples": 1, "blames": 1, "seconds": 0.0})
            self.assertEqual(rc, 2)
            self.assertIn("nope", c.export_text())

    def test_remote_targets_refuse_risk(self):
        c = console()
        rc = cli.main(["owner/repo", "--risk", "main"], console=c, tool_check=lambda **kw: [])
        self.assertEqual(rc, 2)
        self.assertIn("--risk needs a local path", c.export_text())

    def test_portfolio_targets_refuse_risk(self):
        c = console()
        rc = cli.main(["owner/*", "--risk", "main"], console=c, tool_check=lambda **kw: [])
        self.assertEqual(rc, 2)
        self.assertIn("--risk needs a local path", c.export_text())

    def test_threshold_exits_3_when_the_total_is_over_it(self):
        with tempfile.TemporaryDirectory() as d:
            self._repo(d)
            out = os.path.join(d, "out")
            planner = lambda repo, o, branch="HEAD", **kw: [{"name": "q", "argv": ["true"], "stdout": None, "deps": []}]
            estimator = lambda repo, interval, **kw: {"files": 1, "samples": 1, "blames": 1, "seconds": 0.0}
            c = console()
            rc = cli.main([d, "--out", out, "--risk", "main", "--risk-threshold", "-1"], console=c, tool_check=lambda **kw: [],
                          planner=planner, estimator=estimator)
            self.assertEqual(rc, 3, "0 exceeds -1")
            self.assertIn("Change risk (1 files since main)", c.export_text())
            c = console()
            rc = cli.main([out, "--no-run", "--risk", "main", "--risk-threshold", "0"], console=c)
            self.assertEqual(rc, 0, "0 does not exceed 0")
            self.assertIn("Change risk (1 files since main)", c.export_text())

    def test_threshold_needs_risk(self):
        c = console()
        rc = cli.main(["owner/repo", "--risk-threshold", "1"], console=c, tool_check=lambda **kw: [])
        self.assertEqual(rc, 2)
        self.assertIn("--risk-threshold needs --risk", c.export_text())

    def test_threshold_needs_risk_under_no_run_too(self):
        with tempfile.TemporaryDirectory() as d:
            self._repo(d)
            out = os.path.join(d, "out")
            planner = lambda repo, o, branch="HEAD", **kw: [{"name": "q", "argv": ["true"], "stdout": None, "deps": []}]
            estimator = lambda repo, interval, **kw: {"files": 1, "samples": 1, "blames": 1, "seconds": 0.0}
            c = console()
            rc = cli.main([d, "--out", out], console=c, tool_check=lambda **kw: [], planner=planner, estimator=estimator)
            self.assertEqual(rc, 0)
            c = console()
            rc = cli.main([out, "--no-run", "--risk-threshold", "1"], console=c)
            self.assertEqual(rc, 2)
            self.assertIn("--risk-threshold needs --risk", c.export_text())

    def test_compare_checks_its_file_exists_before_any_run(self):
        c = console()
        rc = cli.main([".", "--compare", "/nonexistent/before.json"], console=c, tool_check=lambda **kw: 1 / 0)
        self.assertEqual(rc, 2, "caught before the run: tool_check would raise if it were reached")
        self.assertIn("--compare: no such file: /nonexistent/before.json", c.export_text())

    def test_compare_against_an_earlier_export(self):
        with tempfile.TemporaryDirectory() as d:
            self._repo(d)
            out = os.path.join(d, "out")
            planner = lambda repo, o, branch="HEAD", **kw: [{"name": "q", "argv": ["true"], "stdout": None, "deps": []}]
            estimator = lambda repo, interval, **kw: {"files": 1, "samples": 1, "blames": 1, "seconds": 0.0}
            before = os.path.join(d, "before.json")
            rc = cli.main([d, "--out", out, "--json", before], console=console(), tool_check=lambda **kw: [], planner=planner, estimator=estimator)
            self.assertEqual(rc, 0)
            c = console()
            rc = cli.main([out, "--no-run", "--compare", before], console=c)
            self.assertEqual(rc, 0)
            text = c.export_text()
            self.assertIn("Since last report", text)
            # not just "nothing changed" -- the watch list's own empty note ("nothing changed more than
            # once") would make that assertion pass vacuously; pin the compare section's own printed text
            self.assertIn("Since last report: nothing changed; against", text)
            with open(os.path.join(d, "junk.json"), "w") as fh:
                fh.write("[1, 2]")
            err = console()
            self.assertEqual(cli.main([out, "--no-run", "--compare", os.path.join(d, "junk.json")], console=err), 2)
            self.assertIn("not a gitmole --json export", err.export_text())
            with open(before) as fh:
                other = json.load(fh)
            other["meta"]["name"] = "elsewhere"
            with open(os.path.join(d, "other.json"), "w") as fh:
                json.dump(other, fh)
            err = console()
            self.assertEqual(cli.main([out, "--no-run", "--compare", os.path.join(d, "other.json")], console=err), 2)
            self.assertIn("describes elsewhere", err.export_text())
            err = console()   # `before` must still exist: an owner/* target is rejected for being org, not for its file
            self.assertEqual(cli.main(["someone/*", "--compare", before], console=err), 2)
            self.assertIn("--compare needs one repository", err.export_text())


class BacktestWindow(unittest.TestCase):
    def _run(self, dates, *extra):
        import subprocess
        calls = []
        with tempfile.TemporaryDirectory() as d:
            subprocess.run(["git", "init", "-q", d], check=True)
            for date in dates:
                subprocess.run(["git", "-C", d, "-c", "user.name=T", "-c", "user.email=t@x.com", "commit", "-q", "--allow-empty", "-m", date],
                               check=True, env=dict(os.environ, GIT_AUTHOR_DATE=f"{date}T10:00:00", GIT_COMMITTER_DATE=f"{date}T10:00:00"))
            out = os.path.join(d, "out")
            def planner(repo, o, branch="HEAD", **kw):
                calls.append(kw)
                return [{"name": "q", "argv": ["true"], "stdout": None, "deps": []}]
            cli.main([d, "--out", out, *extra], console=console(), tool_check=lambda **kw: [], planner=planner,
                     estimator=lambda repo, interval, **kw: {"files": 1, "samples": 1, "blames": 1, "seconds": 0.0})
            with open(os.path.join(out, "meta.json")) as fh:
                return calls[0], json.load(fh)

    def test_cut_off_six_months_before_the_last_commit_with_a_year_of_history(self):
        kw, meta = self._run(["2025-01-01", "2025-08-01", "2026-03-01"])
        self.assertEqual(kw["backtest"], "2025-09-01")
        self.assertEqual(meta["backtest"], {"status": "planned", "until": "2025-09-01"})

    def test_since_does_not_narrow_the_history_the_backtest_measures(self):
        kw, meta = self._run(["2025-01-01", "2025-08-01", "2026-03-01"], "--since", "2026-01-01")
        self.assertEqual(kw["backtest"], "2025-09-01", "the window narrows the analysis, not the backtest")
        self.assertEqual(meta["backtest"], {"status": "planned", "until": "2025-09-01"})

    def test_too_little_history_skips(self):
        kw, meta = self._run(["2025-06-01", "2026-03-01"])
        self.assertIsNone(kw["backtest"])
        self.assertEqual(meta["backtest"], {"status": "skipped", "reason": "too little history to backtest"})


if __name__ == "__main__":
    unittest.main()

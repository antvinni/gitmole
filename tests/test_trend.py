import json
import os
import subprocess
import sys
import tempfile
import unittest

from gitmole import trend

SCRIPT_MODULE = "gitmole.trend"


class SampleDates(unittest.TestCase):
    def test_evenly_spread_across_the_span(self):
        dates = trend.sample_dates("2025-01-01", "2026-01-01", 12)
        self.assertEqual(dates[0], "2025-01-01")
        self.assertEqual(dates[-1], "2026-01-01")
        self.assertEqual(len(dates), 12)
        self.assertEqual(len({d[:7] for d in dates}), 12)

    def test_short_histories_give_fewer_points(self):
        self.assertEqual(trend.sample_dates("2026-03-01", "2026-03-20", 12), ["2026-03-01", "2026-03-20"])
        self.assertEqual(trend.sample_dates("2026-03-01", "2026-03-01", 12), ["2026-03-01"])


class ChangeOverYear(unittest.TestCase):
    S = [["2024-01-01", 10, 100], ["2024-11-01", 20, 100], ["2025-06-01", 25, 100], ["2025-11-01", 30, 100]]

    def test_compares_the_sample_nearest_a_year_back_with_the_latest(self):
        self.assertEqual(trend.change_over_year(self.S, "2025-11-09"), "+50%")       # 2024-11-01 (20) -> 30
        self.assertEqual(trend.change_over_year(self.S[1:], "2025-11-09"), "+50%")
        self.assertEqual(trend.change_over_year(self.S[2:], "2025-11-09"), "+20%", "no sample a year back: the earliest")

    def test_flat_within_ten_percent_and_unmeasurable(self):
        self.assertEqual(trend.change_over_year([["2024-11-01", 20, 1], ["2025-11-01", 21, 1]], "2025-11-09"), "=")
        self.assertEqual(trend.change_over_year([["2025-11-01", 21, 1]], "2025-11-09"), "-")
        self.assertEqual(trend.change_over_year([["2024-11-01", 0, 1], ["2025-11-01", 5, 1]], "2025-11-09"), "-")
        self.assertEqual(trend.change_over_year([["2024-11-01", 20, 1], ["2025-11-01", 14, 1]], "2025-11-09"), "-30%")


class Sparkline(unittest.TestCase):
    def test_maps_values_onto_eight_levels(self):
        self.assertEqual(trend.sparkline([["d", 0, 1], ["d", 5, 1], ["d", 10, 1]]), "▁▄█")
        self.assertEqual(trend.sparkline([["d", 7, 1], ["d", 7, 1]]), "▁▁")
        self.assertEqual(trend.sparkline([]), "")

    def test_a_single_sample_is_not_a_line(self):
        self.assertEqual(trend.sparkline([["d", 7, 1]]), "", "one point draws no trend; the cell reads -")


class RevBefore(unittest.TestCase):
    def _repo(self, d):
        e = dict(os.environ, GIT_CONFIG_GLOBAL="/dev/null", GIT_CONFIG_SYSTEM="/dev/null",
                 GIT_AUTHOR_NAME="A", GIT_AUTHOR_EMAIL="a@x", GIT_COMMITTER_NAME="A", GIT_COMMITTER_EMAIL="a@x",
                 GIT_AUTHOR_DATE="2025-06-01T22:30:00+00:00", GIT_COMMITTER_DATE="2025-06-01T22:30:00+00:00")
        subprocess.run(["git", "init", "-q", d], check=True, capture_output=True, env=e)
        subprocess.run(["git", "commit", "-q", "--allow-empty", "-m", "one"], cwd=d, check=True, capture_output=True, env=e)

    def test_the_two_boundaries_of_a_day(self):
        with tempfile.TemporaryDirectory() as d:
            self._repo(d)
            self.assertTrue(trend.rev_before(d, "2025-06-01", end_of_day=True), "the trend samples include the day itself")
            self.assertIsNone(trend.rev_before(d, "2025-06-01", end_of_day=False), "the backtest cuts off as the day begins")
            self.assertTrue(trend.rev_before(d, "2025-06-02", end_of_day=False))

    def test_the_day_is_a_utc_day_wherever_the_run_is(self):
        with tempfile.TemporaryDirectory() as d:
            self._repo(d)   # 22:30 UTC is already the next morning in Tokyo
            old = os.environ.get("TZ")
            os.environ["TZ"] = "Asia/Tokyo"
            try:
                self.assertTrue(trend.rev_before(d, "2025-06-01", end_of_day=True))
                self.assertIsNone(trend.rev_before(d, "2025-06-01", end_of_day=False))
            finally:
                if old is None:
                    del os.environ["TZ"]
                else:
                    os.environ["TZ"] = old

    def test_the_tree_at_a_date_is_on_heads_first_parent_chain(self):
        with tempfile.TemporaryDirectory() as d:
            main, side = side_branch_repo(d)
            plain = subprocess.run(["git", "rev-list", "-1", "--before=2026-01-15T00:00:00+00:00", "HEAD"], cwd=d, capture_output=True, text=True).stdout.strip()
            self.assertEqual(plain, side, "by date alone the side branch merged later wins")
            self.assertEqual(trend.rev_before(d, "2026-01-15", end_of_day=False), main)
            self.assertEqual(trend.rev_before(d, "2026-01-14", end_of_day=True), main)

    def test_a_git_failure_raises_with_gits_own_message(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(RuntimeError) as ctx:
                trend.rev_before(d, "2025-06-01")
        self.assertIn("not a git repository", str(ctx.exception).lower())


def side_branch_repo(d):
    """main: A (Jan 1), B (Jan 5), then a merge (Jan 20) of a side branch whose one commit S is dated Jan 10.
    Returns (B, S): by date alone S is the latest commit before Jan 15, though main at Jan 15 was B."""
    env = dict(os.environ, GIT_CONFIG_GLOBAL="/dev/null", GIT_CONFIG_SYSTEM="/dev/null",
               GIT_AUTHOR_NAME="A", GIT_AUTHOR_EMAIL="a@x", GIT_COMMITTER_NAME="A", GIT_COMMITTER_EMAIL="a@x")

    def git(*a, date=None):
        e = dict(env, **({"GIT_AUTHOR_DATE": date, "GIT_COMMITTER_DATE": date} if date else {}))
        return subprocess.run(["git", *a], cwd=d, env=e, check=True, capture_output=True, text=True).stdout.strip()

    git("init", "-q", "-b", "main")
    git("commit", "-q", "--allow-empty", "-m", "A", date="2026-01-01T12:00:00+00:00")
    git("checkout", "-q", "-b", "side")
    git("commit", "-q", "--allow-empty", "-m", "S", date="2026-01-10T12:00:00+00:00")
    git("checkout", "-q", "main")
    git("commit", "-q", "--allow-empty", "-m", "B", date="2026-01-05T12:00:00+00:00")
    b = git("rev-parse", "HEAD")
    git("merge", "-q", "--no-ff", "-m", "M", "side", date="2026-01-20T12:00:00+00:00")
    return b, git("rev-parse", "side")


def grow_repo(d):
    """One file whose complexity grows over four commits a month apart; a second file that appears late."""
    def git(*args, date):
        e = dict(os.environ, GIT_CONFIG_GLOBAL="/dev/null", GIT_CONFIG_SYSTEM="/dev/null",
                 GIT_AUTHOR_NAME="A", GIT_AUTHOR_EMAIL="a@x", GIT_COMMITTER_NAME="A", GIT_COMMITTER_EMAIL="a@x",
                 GIT_AUTHOR_DATE=date, GIT_COMMITTER_DATE=date)
        subprocess.run(["git", *args], cwd=d, check=True, capture_output=True, env=e)
    git("init", "-q", date="2025-01-01T10:00:00")
    os.makedirs(os.path.join(d, "app"))
    for i, date in enumerate(["2025-01-01", "2025-02-01", "2025-03-01", "2025-04-01"], start=1):
        body = "def f(x):\n" + "".join(f"    if x > {k}:\n        return {k}\n" for k in range(i * 3)) + "    return 0\n"
        with open(os.path.join(d, "app", "a.py"), "w") as fh:
            fh.write(body)
        if i == 4:
            with open(os.path.join(d, "app", "late.py"), "w") as fh:
                fh.write("def g():\n    return 1\n")
        git("add", "-A", date=f"{date}T10:00:00")
        git("commit", "-q", "-m", f"step {i}", date=f"{date}T10:00:00")


class Step(unittest.TestCase):
    def test_measures_the_top_hotspots_at_sampled_commits(self):
        with tempfile.TemporaryDirectory() as d:
            grow_repo(d)
            out = os.path.join(d, "out")
            os.makedirs(out)
            with open(os.path.join(out, "meta.json"), "w") as fh:
                json.dump({"name": "x", "first_date": "2025-01-01", "last_date": "2025-04-01", "file_types": None}, fh)
            with open(os.path.join(out, "size.json"), "w") as fh:
                fh.write(subprocess.run(["scc", "--by-file", "--format", "json"], cwd=d, capture_output=True, text=True, check=True).stdout)
            with open(os.path.join(out, "maat-revisions.csv"), "w") as fh:
                fh.write("entity,n-revs\napp/a.py,4\napp/late.py,1\n")
            rc = trend.main([out, "--repo", d, "--samples", "4"])
            with open(os.path.join(out, "trend.json")) as fh:
                data = json.load(fh)
            listing = sorted(os.listdir(out))
        self.assertEqual(rc, 0)
        self.assertFalse([n for n in listing if n.startswith(".trend-")], "the checkout directory lives under the output directory and is cleaned up")
        self.assertEqual(len(data["samples"]), 4)
        self.assertEqual((data["samples"][0], data["samples"][-1]), ("2025-01-01", "2025-04-01"))
        a = data["files"]["app/a.py"]
        self.assertEqual([s[0] for s in a], data["samples"])
        self.assertEqual([s[1] for s in a], sorted(s[1] for s in a), "complexity never drops: each sample sees the same or a later commit")
        self.assertLess(a[0][1], a[-1][1])
        self.assertEqual(len(data["files"]["app/late.py"]), 1, "absent at the first three samples")
        self.assertEqual(listing, ["maat-revisions.csv", "meta.json", "size.json", "trend.json"], "no temp files left")

    def test_missing_inputs_exit_2(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(trend.main([d, "--repo", d]), 2)

    def test_runs_as_a_module(self):
        p = subprocess.run([sys.executable, "-m", SCRIPT_MODULE, "--help"], capture_output=True, text=True,
                           env=dict(os.environ, PYTHONPATH=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
        self.assertEqual(p.returncode, 0, p.stderr)

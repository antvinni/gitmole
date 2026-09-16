import json
import os
import subprocess
import sys
import tempfile
import unittest

from gitmole import trend

SCRIPT_MODULE = "gitmole.trend"


class SampleDates(unittest.TestCase):
    def test_evenly_spread_and_at_most_one_per_month(self):
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
        open(os.path.join(d, "app", "a.py"), "w").write(body)
        if i == 4:
            open(os.path.join(d, "app", "late.py"), "w").write("def g():\n    return 1\n")
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

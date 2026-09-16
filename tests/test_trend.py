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

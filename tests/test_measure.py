"""The measurement framework: its arithmetic against docs/measurement.md's own worked numbers, the graphs,
the dashboard's crash rule, the fixtures and the sensitivity verdicts."""
import json
import os
import subprocess
import tempfile
import unittest

from gitmole.measure import corpus, dashboard, extras, harness, metrics, svg


class Arithmetic(unittest.TestCase):
    def test_headroom_puts_saturation_in_the_arithmetic(self):
        self.assertAlmostEqual(metrics.headroom(86, 30.1, 90), 0.933, places=3, msg="curl's 0.93 in measurement.md, with 90 as its best possible")
        self.assertIsNone(metrics.headroom(3, 5, 5), "no gap between random and perfect")

    def test_auc_counts_positives_above_negatives(self):
        self.assertEqual(metrics.auc(["a", "b", "c", "d"], {"a", "b"}), 1.0)
        self.assertEqual(metrics.auc(["c", "d", "a", "b"], {"a", "b"}), 0.0)
        self.assertEqual(metrics.auc(["a", "c", "b", "d"], {"a", "b"}), 0.75)
        self.assertIsNone(metrics.auc(["a"], {"a"}))

    def test_recall_at_an_effort_budget(self):
        lines = {"big": 800, "small": 100, "mid": 100}
        self.assertEqual(metrics.recall_at_effort(["big", "small", "mid"], lines, {"small"}, 0.2), 0.0, "the big file spends the budget first")
        self.assertEqual(metrics.recall_at_effort(["small", "mid", "big"], lines, {"small", "big"}, 0.2), 0.5)

    def test_popt_is_one_for_the_optimal_order_and_zero_for_the_worst(self):
        cost = {"a": 1, "b": 1, "c": 2}   # a is the only file that was fixed
        self.assertEqual(metrics.popt(["a", "b", "c"], cost, {"a"}), 1.0, "the positive first, cheapest negatives after")
        self.assertEqual(metrics.popt(["c", "b", "a"], cost, {"a"}), 0.0, "the dearest negatives first, the positive last")

    def test_popt_of_a_middling_order_is_the_worked_example(self):
        cost = {"a": 1, "b": 1, "c": 2}
        # areas under the effort-versus-found curve: optimal 0.875, worst 0.125, ["b", "a", "c"] 0.625,
        # so 1 - (0.875 - 0.625) / (0.875 - 0.125) = 1 - 0.25 / 0.75
        self.assertAlmostEqual(metrics.popt(["b", "a", "c"], cost, {"a"}), 2 / 3, places=6)

    def test_popt_is_none_without_both_classes_or_without_cost(self):
        self.assertIsNone(metrics.popt(["a", "b"], {"a": 1, "b": 1}, set()), "no positive")
        self.assertIsNone(metrics.popt(["a", "b"], {"a": 1, "b": 1}, {"a", "b"}), "no negative")
        self.assertIsNone(metrics.popt(["a", "b"], {"a": 0, "b": 0}, {"a"}), "no effort to spend")

    def test_ifa_counts_the_false_alarms_before_the_first_hit(self):
        self.assertEqual(metrics.ifa(["a", "b", "c"], {"a"}), 0)
        self.assertEqual(metrics.ifa(["a", "b", "c"], {"c"}), 2)
        self.assertEqual(metrics.ifa(["a", "b", "c"], {"c"}, top=2), 2, "capped at the head the reviewer reads")
        self.assertIsNone(metrics.ifa([], {"a"}))

    def test_stability_measures(self):
        self.assertEqual(metrics.spearman(["a", "b", "c", "d"], ["a", "b", "c", "d"]), 1.0)
        self.assertEqual(metrics.spearman(["a", "b", "c"], ["c", "b", "a"]), -1.0)
        self.assertEqual(metrics.jaccard(["a", "b"], ["b", "c"]), 1 / 3)

    def test_wilson_and_the_verdict_match_the_plan(self):
        lo, hi = metrics.wilson(8, 10)
        self.assertEqual((round(lo, 2), round(hi, 2)), (0.49, 0.94))
        self.assertEqual(round(metrics.wilson(10, 10)[0], 2), 0.72)
        self.assertEqual(metrics.verdict(20, 20), "sound", "twenty of twenty clears the line at 0.84")
        self.assertEqual(metrics.verdict(8, 10), "undecided")
        self.assertEqual(metrics.verdict(2, 20), "broken")
        self.assertEqual(metrics.verdict(0, 0), "unlabelled")

    def test_kappa(self):
        self.assertEqual(metrics.kappa([(True, True), (False, False)]), 1.0)
        self.assertAlmostEqual(metrics.kappa([(True, True), (True, False), (False, False), (False, True)]), 0.0)

    def test_bootstrap_resamples_whole_repositories_and_is_seeded(self):
        groups = {"a": [0.9, 0.8], "b": [0.2, 0.3], "c": [0.5]}
        one = metrics.bootstrap(groups, metrics.median)
        self.assertEqual(one, metrics.bootstrap(groups, metrics.median), "seeded: the same interval every time")
        self.assertLessEqual(one[0], one[1])
        self.assertIsNone(metrics.bootstrap({"a": [None]}, metrics.median))



class HarnessScore(unittest.TestCase):
    """score() is what every release record is built from: its existing keys must not move."""

    RANK = {"pool": ["big", "small", "mid"], "revs": {"big": 9, "small": 5, "mid": 1},
            "lines": {"big": 800, "small": 100, "mid": 100}, "total_code": 1000}

    def test_score_keeps_its_old_keys_and_adds_the_effort_aware_ones(self):
        out = harness.score(dict(self.RANK), {"small"}, top=3)
        for key in ("pool", "positives", "hits", "expected", "best", "churn_hits", "auc", "churn_auc",
                    "recall20", "churn_recall20", "top"):
            self.assertIn(key, out, f"{key} is part of the record and must not vanish")
        self.assertEqual(out["ifa"], 1, "the list names big before small")
        self.assertIsNotNone(out["popt"])
        self.assertIsNotNone(out["churn_popt"])
        self.assertIn("churn_ifa", out)

    def test_manualup_is_recorded_as_a_control_with_its_false_alarms(self):
        out = harness.score(dict(self.RANK), {"big"}, top=3)
        self.assertEqual(out["manualup_ifa"], 2, "smallest first names both small files before big")
        for key in ("manualup_hits", "manualup_auc", "manualup_recall20", "manualup_popt"):
            self.assertIn(key, out)

class Scoring(unittest.TestCase):
    def test_one_cut_off_against_random_perfect_and_churn(self):
        rank = {"pool": ["a", "b", "c", "d"], "revs": {"a": 1, "b": 9, "c": 5, "d": 3}, "lines": {"a": 10, "b": 10, "c": 10, "d": 10}, "total_code": 40}
        s = harness.score(rank, {"a", "c", "z"}, top=2)
        self.assertEqual((s["positives"], s["hits"], s["best"], s["churn_hits"]), (2, 1, 2, 1))
        self.assertEqual(s["expected"], 1.0)
        self.assertEqual(s["top"], ["a", "b"], "the list's own top, kept for the carry-over")

    def test_matched_magnets(self):
        rank = {"pool": [f"f{i}" for i in range(20)], "magnets": ["f0", "f1"]}
        m = harness.magnets_at(rank, {"f0", "f2"})
        self.assertEqual((m["named"], m["named_fixed"], m["matched"], m["matched_fixed"]), (2, 1, 0, 0), "f0 and f1 fill the top decile alone")
        self.assertIsNone(harness.magnets_at({"pool": ["a"], "magnets": None}, set()))


def _record(statuses):
    repos = {}
    for name, status in statuses.items():
        rec = {"status": status, "set": "development", "findings": 4, "report_lines": 100, "seconds": 10, "peak_mb": 100}
        if status == "ok":
            rec["ranking"] = {"cutoffs": [{"cutoff": "2026-01-01", "pool": 40, "positives": 10, "hits": 6, "expected": 3.75, "best": 10, "churn_hits": 5,
                                           "auc": 0.7, "churn_auc": 0.6, "recall20": 0.3, "churn_recall20": 0.2}]}
        else:
            rec["note"] = "Traceback: boom"
        repos[name] = rec
    return {"version": "9.9.9", "repos": repos}


class Dashboard(unittest.TestCase):
    def test_a_release_is_summarised(self):
        s = dashboard.summarise(_record({"a": "ok", "b": "ok"}))
        self.assertIsNone(s["crashed"])
        self.assertAlmostEqual(s["headroom"], round((6 - 3.75) / (10 - 3.75), 3))
        self.assertEqual(s["wins_losses_ties"], [2, 0, 0])
        self.assertEqual(s["robust"], [2, 2])

    def test_a_crash_on_any_development_repository_marks_the_release(self):
        s = dashboard.summarise(_record({"a": "ok", "b": "crashed"}))
        self.assertEqual(s["crashed"], {"b": "Traceback: boom"})
        self.assertEqual(s["robust"], [1, 2])

    def test_the_top_fifteen_carried_over_between_consecutive_cut_offs(self):
        rec = _record({"a": "ok", "b": "ok"})
        cut = rec["repos"]["a"]["ranking"]["cutoffs"][0]
        rec["repos"]["a"]["ranking"]["cutoffs"] = [dict(cut, top=["x", "y"]), dict(cut, top=["x", "z"]), dict(cut, top=["x", "z"])]
        self.assertAlmostEqual(dashboard.summarise(rec)["carryover_top15"], round((1 / 3 + 1) / 2, 3), msg="b kept no tops: the median of one repository")
        self.assertIsNone(dashboard.summarise(_record({"a": "ok"}))["carryover_top15"], "a record from before the tops were kept")

    def test_a_move_counts_only_outside_the_previous_interval(self):
        self.assertEqual(dashboard.moved({"headroom_ci": [0.4, 0.6]}, {"headroom": 0.7}), "up")
        self.assertEqual(dashboard.moved({"headroom_ci": [0.4, 0.6]}, {"headroom": 0.5}), "")


class Graphs(unittest.TestCase):
    def test_a_chart_draws_lines_bands_and_crashes_the_same_bytes_every_time(self):
        args = ("t", ["0.1", "0.2", "0.3"], [{"label": "x", "values": [0.2, None, 0.8], "band": [[0.1, 0.3], None, [0.7, 0.9]]},
                                            {"label": "y", "values": [0.5, 0.5, 0.5], "dashed": True}], [1], (0, 1), "%")
        one = svg.chart(*args)
        self.assertEqual(one, svg.chart(*args))
        self.assertIn("stroke-dasharray", one)
        self.assertIn("crashed", one)
        self.assertTrue(one.startswith("<svg") and one.strip().endswith("</svg>"))

    def test_release_labels_never_touch_and_both_ends_are_drawn(self):
        """The README's ranking graph ran 0.31.0 and 0.32.0 together into "0.31.00.32.0": the tick step drew
        every nth label and then forced the last one whatever sat beside it."""
        import re
        for count in (2, 5, 12, 32, 60):
            labels = [f"0.{i}.0" for i in range(count)]
            out = svg.chart("t", labels, [{"label": "x", "values": [0.5] * count}])
            drawn = re.findall(r'<text x="([\d.]+)" y="\d+" text-anchor="middle"[^>]*>([^<]+)</text>', out)
            with self.subTest(releases=count):
                self.assertEqual((drawn[0][1], drawn[-1][1]), (labels[0], labels[-1]), "both ends are drawn")
                gaps = [float(b[0]) - float(a[0]) for a, b in zip(drawn, drawn[1:])]
                self.assertGreaterEqual(min(gaps), svg.TICK_GAP, "no two labels are closer than one label's width")

    def test_the_note_has_a_line_below_the_legend(self):
        """Both were drawn on the same baseline, so a long note ran through the legend's words."""
        out = svg.chart("t", ["0.1", "0.2"], [{"label": "watch list", "values": [0.5, 0.6]},
                                              {"label": "churn alone", "values": [0.4, 0.4], "dashed": True}],
                        note="dots: independent labels, repositories never tuned on")
        import re
        legend = {float(y) for y in re.findall(r'<text x="[\d.]+" y="([\d.]+)" fill="#1f2328">(?:watch list|churn alone)</text>', out)}
        note = {float(y) for y in re.findall(r'<text x="[\d.]+" y="([\d.]+)" fill="#57606a"[^>]*>dots:', out)}
        self.assertEqual(len(legend), 1, "the legend is one line")
        self.assertTrue(note and min(note) > max(legend), "and the note sits below it")


class Fixtures(unittest.TestCase):
    def test_every_fixture_builds(self):
        with tempfile.TemporaryDirectory() as d:
            for kind in ("empty", "one-commit", "detached", "shallow", "submodule", "non-utf8-path", "binary-only", "secret", "trojan-source", "submodule-credentials"):
                path = corpus.fixture(kind, d)
                self.assertTrue(os.path.isdir(path), kind)
            head = subprocess.run(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=os.path.join(d, "detached"), capture_output=True, text=True).stdout.strip()
            self.assertEqual(head, "HEAD")
            self.assertTrue(os.path.exists(os.path.join(d, "shallow", ".git", "shallow")))
            names = subprocess.run(["git", "ls-files", "-z"], cwd=os.path.join(d, "non-utf8-path"), capture_output=True).stdout.split(b"\0")
            self.assertIn(b"caf\xe9.py", names, "the Latin-1 name is in the commit")

    def test_the_trojan_fixture_holds_the_bidi_characters_and_the_builder_does_not(self):
        # gitmole is in its own development set, so a literal U+202E here is a critical finding on gitmole
        with tempfile.TemporaryDirectory() as d:
            path = corpus.fixture("trojan-source", d)
            with open(os.path.join(path, "check.py"), encoding="utf-8") as fh:
                written = fh.read()
        self.assertIn("\u202e", written, "the fixture is the point: it holds the characters")
        with open(corpus.__file__, encoding="utf-8") as fh:
            builder = fh.read()
        for char in ("\u202e", "\u2066", "\u2069"):
            self.assertNotIn(char, builder, "write them as escapes, as the secret fixture assembles its key")

    def test_the_run_environment_forces_a_terminal_whatever_the_caller_set(self):
        # 0.2.0 to 0.30.0 were measured with a forced terminal; a caller without FORCE_COLOR printed 11 lines fewer
        saved = {k: os.environ.get(k) for k in harness._TTY_VARS}
        try:
            for k in harness._TTY_VARS:
                os.environ.pop(k, None)
            os.environ["TTY_INTERACTIVE"] = "1"
            env = harness._env("/src", "2026-09-17")
        finally:
            for k, v in saved.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v
        self.assertEqual(env["FORCE_COLOR"], "1")
        self.assertNotIn("TTY_INTERACTIVE", env)
        self.assertEqual((env["PYTHONPATH"], env["GITMOLE_NOW"], env["NO_COLOR"]), ("/src", "2026-09-17", "1"))

    def test_the_manifest_names_every_set_and_pins_every_clone(self):
        m = corpus.load()
        self.assertEqual({e["set"] for e in m["repos"]}, {"development", "holdout", "well-kept", "awkward", "gate"})
        for e in m["repos"]:
            self.assertTrue(e.get("fixture") or (e.get("url") and len(e.get("commit", "")) == 40), e["name"])
        self.assertTrue(m["well_kept_criterion"])


class Sensitivity(unittest.TestCase):
    def _row(self, base, near):
        return {"base": {"r": base}, "shifts": {"0.9": {"repos": {"r": near}}, "1.1": {"repos": {"r": near}}}}

    def test_verdicts(self):
        self.assertEqual(extras._verdict(self._row(4, {"findings": 4, "jaccard": 1.0})), "flat")
        self.assertEqual(extras._verdict(self._row(4, {"findings": 9, "jaccard": 0.4})), "fragile")
        self.assertEqual(extras._verdict(self._row(4, {"findings": 4, "jaccard": 0.6})), "moderate", "same count, different files")
        self.assertEqual(extras._verdict(self._row(0, {"findings": 0, "jaccard": None})), "silent")


if __name__ == "__main__":
    unittest.main()


class Signals(unittest.TestCase):
    def test_recent_revisions_times_lines_reorder_the_same_pool(self):
        from gitmole.measure import signals
        from tests.test_watch import report
        commits = [{"hash": f"h{i}", "date": "2026-08-01", "author": "Ann", "subject": "work", "files": [("core/util.py", 1, 1)]} for i in range(30)]
        commits += [{"hash": "old", "date": "2020-01-01", "author": "Ann", "subject": "work", "files": [("web/index.html", 1, 1), ("core/parser.py", 1, 1)]}]
        ranked, lines = signals.variants(report(), commits, "2026-09-01")
        self.assertEqual(ranked["watch list"], ["web/index.html", "core/parser.py", "core/util.py"])
        self.assertEqual(sorted(ranked["revs 12m x lines"]), sorted(ranked["watch list"]), "every variant ranks the one pool")
        self.assertEqual(ranked["revs 12m x lines"][0], "core/util.py", "30 changes this year × 200 lines, against one each in 2020")
        self.assertEqual(ranked["churn"][0], "web/index.html")
        self.assertEqual(lines["core/parser.py"], 800)


class SummarisedRules(unittest.TestCase):
    def test_the_summarised_set_is_what_the_labels_say(self):
        """A rule with five or more labelled findings, none of them actionable, is summarised; every summarised
        rule is one. New labels that break this ask for the set to change with them."""
        from gitmole import findings
        from gitmole.measure import labels
        rules = labels.score()["rules"]
        inert = {r for r, v in rules.items() if v["labelled"] >= 5 and v["actionable_share"] == 0}
        self.assertEqual(set(findings.SUMMARISED), inert)

    def test_the_unjudged_set_is_the_rules_no_label_has_reached(self):
        """findings.UNJUDGED holds the structure step's rules only while nobody has labelled them. A label on
        one of them asks for it to leave the set: into the report proper, or into SUMMARISED."""
        from gitmole import findings
        from gitmole.measure import labels
        rules = labels.score()["rules"]
        labelled = {r for r, v in rules.items() if v["labelled"]}
        self.assertEqual(set(findings.UNJUDGED) & labelled, set(), "these rules have labels now; decide where they belong")
        self.assertEqual(set(findings.UNJUDGED) & set(findings.SUMMARISED), set(), "a rule is summarised or unjudged, not both")


class CarriedLabels(unittest.TestCase):
    def test_a_label_follows_a_finding_whose_statement_did_not_change(self):
        from unittest import mock
        from gitmole.measure import labels
        commit = next(e for e in corpus.load()["repos"] if e["name"] == "curl").get("commit")
        old = labels.finding_id("stale_files", "curl", commit, {"files": 100})
        with tempfile.TemporaryDirectory() as d:
            ldir, records, work = os.path.join(d, "measure"), os.path.join(d, "records"), os.path.join(d, "work")
            for p in (ldir, records, os.path.join(work, "runs", "9.9.9", "curl")):
                os.makedirs(p)
            with open(os.path.join(ldir, "labels-key.jsonl"), "w") as fh:
                fh.write(json.dumps({"id": old, "rule": "stale_files", "severity": "info", "repo": "curl", "version": "9.9.8", "statement": "S"}) + "\n")
            with open(os.path.join(ldir, "labels.jsonl"), "w") as fh:
                fh.write(json.dumps({"id": old, "labeller": "a", "true": True, "actionable": False}) + "\n")
            with open(os.path.join(records, "9.9.9.json"), "w") as fh:
                json.dump({"version": "9.9.9", "repos": {"curl": {"set": "development", "status": "ok"}}}, fh)
            with open(os.path.join(work, "runs", "9.9.9", "curl", "report.json"), "w") as fh:
                json.dump({"findings": [{"rule": {"id": "stale_files"}, "severity": "info", "detail": "S", "evidence": {"files": 101}},
                                        {"rule": {"id": "bug_magnets"}, "severity": "warning", "detail": "B", "evidence": {"count": 3}, "summary": False}]}, fh)
            with mock.patch.object(labels, "DIR", ldir), mock.patch.dict(os.environ, {"GITMOLE_MEASURE_DIR": work}):
                n, carried, path = labels.dump(records)
                self.assertEqual((n, carried), (1, 1), "the stale-files claim is unchanged; the bug magnets finding is new")
                with open(path) as fh:
                    self.assertEqual([json.loads(l)["statement"] for l in fh], ["B"])
                again = labels.dump(records)
                self.assertEqual(again[:2], (1, 0), "a second dump carries nothing twice")
                new = labels.finding_id("stale_files", "curl", commit, {"files": 101})
                rec = {"repos": {"curl": {"set": "development", "finding_ids": [{"id": new, "rule": "stale_files", "summary": False},
                                                                                {"id": "x", "rule": "bug_magnets", "summary": False},
                                                                                {"id": "y", "rule": "reverts", "summary": True}]}}}
                self.assertEqual(labels.usefulness(rec), {"actionable_share": 0.0, "labelled_share": 0.5, "shown": 2},
                                 "the summarised finding is not in the default report; one of the two shown carries a label")


class Series(unittest.TestCase):
    def test_a_repository_joining_the_development_set_does_not_move_the_series(self):
        rec = _record({"a": "ok", "b": "ok"})
        joined = json.loads(json.dumps(rec))
        for name in ("c", "d"):   # two lower repositories move the median of four
            joined["repos"][name] = {**joined["repos"]["a"], "ranking": {"cutoffs": [dict(joined["repos"]["a"]["ranking"]["cutoffs"][0], hits=4)]}}
        self.assertEqual(dashboard.summarise(joined, only={"a", "b"})["headroom"], dashboard.summarise(rec)["headroom"])
        self.assertNotEqual(dashboard.summarise(joined)["headroom"], dashboard.summarise(rec)["headroom"], "the whole set does move")

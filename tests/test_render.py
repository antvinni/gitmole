import io
import unittest

from rich.console import Console

from gitmole import render


def sample_report():
    return {
        "out_dir": "/tmp/analysis-demo",
        "meta": {"name": "demo", "branch": "main", "commits": 363, "first_date": "2025-08-20", "last_date": "2026-09-10",
                 "identities": [{"name": "Ann", "email": "ann@x.com", "commits": 234}, {"name": "Bob", "email": "bob@x.com", "commits": 129}]},
        "size": {"languages": [{"name": "HTML", "files": 28, "code": 4783, "comment": 144, "blank": 732, "complexity": 0},
                               {"name": "Python", "files": 7, "code": 638, "comment": 50, "blank": 52, "complexity": 57}],
                 "total_code": 5421, "total_files": 35,
                 "files": {"static/apps-metadata.json": {"code": 800, "complexity": 0}, "static/index.html": {"code": 4000, "complexity": 12},
                           "static/a.html": {"code": 300, "complexity": 0}, "static/b.html": {"code": 200, "complexity": 0}}},
        "revisions": [{"entity": "static/apps-metadata.json", "n-revs": 128}, {"entity": "static/index.html", "n-revs": 51}],
        "authors": [{"entity": "static/apps-metadata.json", "n-authors": 4, "n-revs": 128}],
        "coupling": [{"entity": "static/tax.html", "coupled": "static/treasury.html", "degree": 85, "average-revs": 11}],
        "age": [{"entity": "static/index.html", "age-months": 0}],
        "sizer": [{"name": "Blobs: Maximum size", "value": "21.3 MiB", "concern": 2, "ref": "static/video/clip.mp4"}],
        "cohorts": {"Code added in 2025": 8733, "Code added in 2026": 2728},
        "theseus_authors": {"Ann": 9076, "Bob": 2342},
        "secrets": [],
        "secrets_scanned": True,
        "fixes": [{"entity": "static/apps-metadata.json", "n-fixes": 9, "last-fix": "2026-09-01", "recent-fixes": 4}],
        "functions": [{"file": "static/js/app.js", "function": "render", "ccn": 27, "nloc": 180, "params": 4, "start": 10, "end": 200},
                      {"file": "static/js/util.js", "function": "tidy", "ccn": 12, "nloc": 30, "params": 1, "start": 1, "end": 31}],
        "duplicates": {"rate": 1.5, "blocks": []},
        "ownership": [{"entity": "static/a.html", "author": "Ann", "added": 900, "deleted": 0},
                      {"entity": "static/b.html", "author": "Bob", "added": 100, "deleted": 0},
                      {"entity": "tests/t.py", "author": "Bob", "added": 300, "deleted": 0}],
        "activity": {"by_weekday": [40, 50, 45, 60, 30, 5, 3], "by_hour": [0] * 9 + [20, 30, 25] + [0] * 12,
                     "by_month": {"2026-07": 10, "2026-08": 20, "2026-09": 12}, "authors": {},
                     "timeline": {"Ann": {"2025-10": 3, "2026-08": 12, "2026-09": 7}, "Bob": {"2026-09": 5},
                                  "Old Timer": {"2019-01": 400}}},
    }


def _section_text(text: str, heading: str) -> str:
    """The rendered report from one section's heading to the end: what that section printed."""
    return text[text.index(heading):]


def rendered(report, findings, width=120, full=False):
    console = Console(file=io.StringIO(), width=width, record=True, force_terminal=False, color_system=None)
    render.report(report, findings, console, full=full)
    return console.export_text()


class Report(unittest.TestCase):
    def test_header_shows_name_commits_span_and_languages(self):
        text = rendered(sample_report(), [])
        self.assertIn("demo", text)
        self.assertIn("363", text)
        self.assertIn("2025-08-20", text)
        self.assertIn("HTML", text)

    def test_findings_section_lists_each_finding(self):
        f = [{"severity": "warning", "title": "Bus factor of one", "detail": "Ann wrote 79% of the code."}]
        text = rendered(sample_report(), f)
        self.assertIn("Bus factor of one", text)
        self.assertIn("79%", text)

    def test_no_findings_says_so(self):
        self.assertIn("Nothing flagged", rendered(sample_report(), []))

    def test_a_clean_secrets_scan_is_said_out_loud_in_the_findings(self):
        text = rendered(sample_report(), [])
        self.assertIn("✔ No secrets in history", text)
        self.assertIn("betterleaks scanned every commit on every branch", text)
        f = [{"severity": "warning", "title": "Bus factor of one", "detail": "Ann wrote 79% of the code."}]
        text = rendered(sample_report(), f)
        self.assertIn("Findings (1)", text, "the pass line is not a finding and is not counted")
        self.assertIn("✔ No secrets in history", text)
        self.assertLess(text.index("Bus factor of one"), text.index("No secrets in history"), "problems first, the pass line last")

    def test_the_pass_line_names_the_placeholder_hits_left_out(self):
        r = sample_report()
        r["secrets"] = [{"rule": "r", "file": "p.json", "commit": "c1", "line": 1, "fingerprint": "c1:p.json", "value": "h3", "placeholder": True}]
        self.assertIn("No secrets in history", rendered(r, []))
        self.assertIn("1 placeholder-shaped hit left out", rendered(r, []))

    def test_no_pass_line_when_the_scan_did_not_run_or_found_something(self):
        r = sample_report()
        r["secrets_scanned"] = False
        self.assertNotIn("No secrets in history", rendered(r, []), "a killed step or an old output directory has no secrets.json: say nothing")
        r = sample_report()
        r["secrets"] = [{"rule": "r", "file": "a.py", "commit": "c1", "line": 1, "fingerprint": "c1:a.py", "value": "h1", "placeholder": False}]
        f = [{"severity": "critical", "title": "1 secret(s) in history", "detail": "x"}]
        self.assertNotIn("No secrets in history", rendered(r, f))

    def test_tables_show_people_hotspots_coupling_age_and_health(self):
        text = rendered(sample_report(), [], full=True)
        self.assertIn("Ann", text)
        self.assertIn("static/apps-metadata.json", text)
        self.assertIn("static/treasury.html", text)
        self.assertIn("2025", text)
        self.assertIn("21.3 MiB", text)

    def test_header_mentions_the_window_when_bounded(self):
        r = sample_report()
        r["meta"]["since"] = "2024-09-15"
        text = rendered(r, [])
        self.assertIn("since 2024-09-15", text)
        self.assertNotIn("since", rendered(sample_report(), []))

    def test_header_singular_identity(self):
        r = sample_report()
        r["meta"]["identities"] = r["meta"]["identities"][:1]
        text = rendered(r, [])
        self.assertIn("1 identity ", text)
        self.assertNotIn("1 identities", text)

    def test_header_mentions_reverts_only_when_there_are_any(self):
        r = sample_report()
        r["activity"]["revert_commits"] = 7
        self.assertIn("3% of commits are reverts", rendered(r, []))     # 7 of 233 commits in by_weekday
        self.assertNotIn("reverts", rendered(sample_report(), []))
        r["activity"]["revert_commits"] = 1
        self.assertIn("1 revert", rendered(r, []))                     # 1 of 233 commits rounds to 0%
        self.assertNotIn("% of commits are reverts", rendered(r, []))
        r["activity"]["by_weekday"] = [1000, 0, 0, 0, 0, 0, 0]
        r["activity"]["revert_commits"] = 2
        self.assertIn("2 reverts", rendered(r, []))                    # 2 of 1000 commits still rounds to 0%, and is plural

    def test_empty_coupling_collapses_to_one_line(self):
        r = sample_report()
        r["coupling"] = []
        text = rendered(r, [], width=60)
        self.assertIn("Change coupling: no pairs with 5+ shared revisions", text)
        self.assertNotIn("together)\n", text.replace("(files that change\ntogether)", "together)\n"))

    def test_age_falls_back_to_last_changed_years_when_theseus_skipped(self):
        r = sample_report()
        r["cohorts"] = {}
        r["meta"]["age"] = {"status": "skipped", "files": 80000, "budget": 50000}
        r["activity"] = {}
        r["age"] = [{"entity": "a", "age-months": 0}, {"entity": "b", "age-months": 2},
                    {"entity": "c", "age-months": 14}, {"entity": "d", "age-months": 30}]
        text = rendered(r, [], full=True)
        self.assertIn("Paths in history by year last changed", text)
        self.assertIn("code age skipped", text)
        self.assertNotIn("code-maat", text)
        for year, count in (("2026", "2"), ("2025", "1"), ("2024", "1")):
            self.assertRegex(text, rf"{year}\s+{count}\s")
        self.assertNotIn("Surviving code by year written", text)

    def test_age_uses_net_lines_from_the_log_when_blame_skipped(self):
        r = sample_report()
        r["cohorts"] = {}
        r["meta"]["age"] = {"status": "skipped"}
        r["activity"]["net_by_year"] = {"2025": 8000, "2026": 2000}
        text = rendered(r, [], full=True)
        self.assertIn("Net lines added by year", text)
        self.assertIn("code age skipped", text)
        self.assertRegex(text, r"2025\s+8,000\s+80%")
        self.assertNotIn("Paths in history", text)

    def test_age_says_when_blame_timed_out(self):
        r = sample_report()
        r["cohorts"] = {}
        r["meta"]["age"] = {"status": "timeout"}
        r["activity"] = {}
        self.assertIn("code age timed out", rendered(r, [], full=True))

    def test_hotspots_rank_by_revisions_times_lines_and_show_complexity(self):
        r = sample_report()
        r["revisions"] = [{"entity": "static/apps-metadata.json", "n-revs": 128}, {"entity": "static/index.html", "n-revs": 51},
                          {"entity": "gone.py", "n-revs": 300}]
        text = rendered(r, [], full=True)
        text = text[text.index("◆ Hotspots"):]
        lines = [l.strip() for l in text.splitlines() if l.strip().startswith(("static/", "gone.py"))]
        # index.html: 51 x 4000 = 204,000 beats metadata.json: 128 x 800 = 102,400; deleted gone.py sorts last
        self.assertTrue(lines[0].startswith("static/index.html"), lines)
        self.assertTrue(lines[1].startswith("static/apps-metadata.json"), lines)
        self.assertTrue(lines[2].startswith("gone.py"), lines)
        self.assertRegex(lines[0], r"51\s+4,000\s+12")
        self.assertIn("score", text)
        self.assertIn("fixes", text)
        self.assertRegex(lines[1], r"static/apps-metadata.json\s+128\s+800\s+0\s+102,400\s+9\s")

    def test_footer_path_is_never_wrapped(self):
        r = sample_report()
        r["out_dir"] = "/very/long/" + "x" * 150 + "/analysis-demo"
        text = rendered(r, [], width=80)
        self.assertIn("Full results and plots in " + r["out_dir"], text)

    def test_footer_points_at_output_dir(self):
        self.assertIn("/tmp/analysis-demo", rendered(sample_report(), []))

    def test_fits_a_narrow_terminal_without_error(self):
        text = rendered(sample_report(), [], width=80)
        self.assertTrue(all(len(line) <= 80 for line in text.splitlines()), "a line exceeds 80 columns")

    def test_knowledge_map_marks_gone_owners_and_full_has_a_lost_column(self):
        r = sample_report()
        r["meta"]["last_date"] = "2026-09-10"
        r["meta"]["bots"] = []
        r["activity"]["authors"] = {"Ann": {"commits": 1, "added": 0, "deleted": 0, "first": "2025-01-01", "last": "2026-09-01"},
                                    "Bob": {"commits": 1, "added": 0, "deleted": 0, "first": "2025-01-01", "last": "2025-01-01"}}
        text = rendered(r, [])
        self.assertIn("Bob (gone)", text)
        self.assertIn("gone = no commits in the 12 months before 2026-09-10", text)
        self.assertNotIn("lost", text.split("⌂ Knowledge map")[1].split("\n")[1], "the lost column is --full only")
        full = rendered(r, [], full=True)
        self.assertRegex(full, r"area\s+lines added\s+authors\s+lost\s+main owner")
        self.assertRegex(full, r"static/\s+1,000\s+2\s+10%")
        self.assertNotIn("gone", rendered(sample_report(), []))

    def test_knowledge_map_caption_says_gone_is_measured_over_the_whole_history(self):
        r = sample_report()
        r["meta"].update({"last_date": "2026-09-10", "bots": []})
        r["size"]["files"]["tests/t.py"] = {"code": 1, "complexity": 0}   # every area in the tree, so nothing is hidden
        r["activity"]["authors"] = {"Ann": {"commits": 1, "added": 0, "deleted": 0, "first": "2025-01-01", "last": "2026-09-01"},
                                    "Bob": {"commits": 1, "added": 0, "deleted": 0, "first": "2025-01-01", "last": "2025-01-01"}}
        def caption(rep):
            return next(x for x in render.sections(rep, full=False) if x["id"] == "knowledge")["caption"]
        self.assertEqual(caption(r), "gone = no commits in the 12 months before 2026-09-10")
        r["meta"]["since"] = "2026-01-01"
        self.assertEqual(caption(r), "gone = no commits in the 12 months before 2026-09-10; "
                                     "gone and lost are measured over the whole history")

    def test_hotspots_carry_a_trend_column_and_a_sparkline_under_full(self):
        r = sample_report()
        r["meta"]["last_date"] = "2026-09-10"
        r["trend"] = {"samples": ["2025-09-10", "2026-03-10", "2026-09-10"],
                      "files": {"static/index.html": [["2025-09-10", 10, 4000], ["2026-03-10", 12, 4000], ["2026-09-10", 16, 4000]]}}
        text = rendered(r, [])
        self.assertRegex(text, r"file\s+revs\s+lines\s+fixes\s+authors\s+trend")
        self.assertRegex(text, r"static/index\.html\s+51\s+4,000\s+0\s+-\s+\+60%")
        self.assertRegex(text, r"static/apps-metadata\.json\s+128\s+800\s+9\s+4\s+-")
        self.assertRegex(rendered(r, [], full=True), r"static/index\.html.*▁▃█")
        self.assertRegex(rendered(sample_report(), []), r"static/index\.html\s+51\s+4,000\s+0\s+-\s+-")

    def test_full_hotspots_say_the_trend_column_covers_the_top_ten(self):
        r = sample_report()
        r["meta"]["last_date"] = "2026-09-10"
        def caption(rep, full):
            return next(x for x in render.sections(rep, full=full) if x["id"] == "hotspots")["caption"]
        self.assertIsNone(caption(r, True), "no trend data, nothing to explain")
        r["trend"] = {"samples": ["2025-09-10", "2026-09-10"],
                      "files": {"static/index.html": [["2025-09-10", 10, 4000], ["2026-09-10", 16, 4000]]}}
        self.assertEqual(caption(r, True), "trend sampled for the top 10 hotspots")
        self.assertIsNone(caption(r, False), "the tight report keeps its captions short")
        r["revisions"] = [{"entity": f"f{i}.py", "n-revs": 100 - i} for i in range(60)]
        r["size"]["files"].update({f"f{i}.py": {"code": 10, "complexity": 0} for i in range(60)})   # in the tree, so not hidden as deleted
        self.assertEqual(caption(r, "markdown"), "and 10 more; trend sampled for the top 10 hotspots")

    def test_watch_list_caption_reports_the_backtest_or_why_not(self):
        r = sample_report()
        r["meta"]["backtest"] = {"status": "skipped", "reason": "too little history to backtest"}
        self.assertIn("too little history to backtest", rendered(r, []))
        r = sample_report()
        past = sample_report()
        past["meta"] = {"now": "2026-03-10"}
        r["backtest"] = past
        r["fixes"] = [{"entity": "static/index.html", "n-fixes": 1, "last-fix": "2026-08-01", "recent-fixes": 1},
                      {"entity": "static/other.html", "n-fixes": 1, "last-fix": "2026-08-01", "recent-fixes": 1}]
        text = rendered(r, [], width=150)
        self.assertIn("6 months ago this list would have named 1 of the 2 files fixed since "
                     "(a random 2 of the 2 files that had changed more than once would name 1.0)", text)
        self.assertEqual(render.to_json(r, [])["watch_backtest"]["hits"], 1)
        self.assertEqual(render.to_json(r, [])["watch_backtest"]["pool"], 2)


    def test_backtest_caption_says_whole_history_under_a_window(self):
        r = sample_report()
        past = sample_report()
        past["meta"] = {"now": "2026-03-10"}
        r["backtest"] = past
        r["fixes"] = [{"entity": "static/index.html", "n-fixes": 1, "last-fix": "2026-08-01", "recent-fixes": 1},
                      {"entity": "static/other.html", "n-fixes": 1, "last-fix": "2026-08-01", "recent-fixes": 1}]
        r["meta"]["since"] = "2026-01-01"
        caption = next(x for x in render.sections(r, full=False) if x["id"] == "watch")["caption"]
        self.assertIn("ranked by churn × recent fixes × complexity × single ownership; commits since 2026-01-01", caption)
        self.assertTrue(caption.endswith("would name 1.0); whole history"), caption)

    def test_default_hotspots_hide_test_files_and_say_so(self):
        r = sample_report()
        r["revisions"].append({"entity": "tests/test_a.py", "n-revs": 200})
        r["size"]["files"]["tests/test_a.py"] = {"code": 50, "complexity": 1}
        text = rendered(r, [])
        hot = text[text.index("◆ Hotspots"):]
        self.assertNotIn("tests/test_a.py", hot)
        self.assertIn("1 test file hidden; --full shows them", hot)
        full_text = rendered(r, [], full=True)
        self.assertIn("tests/test_a.py", full_text[full_text.index("◆ Hotspots"):])

    def test_default_coupling_hides_test_pairs_and_says_so(self):
        r = sample_report()
        r["coupling"].append({"entity": "static/tax.html", "coupled": "tests/test_tax.py", "degree": 100, "average-revs": 11})
        text = rendered(r, [], width=200)
        coupling = text[text.index("Change coupling"):]
        self.assertNotIn("tests/test_tax.py", coupling)
        self.assertIn("1 test pair hidden; 1 historical pair hidden; --full shows them", coupling, "one suffix for every hidden count")
        full_text = rendered(r, [], full=True)
        self.assertIn("tests/test_tax.py", full_text[full_text.index("Change coupling"):])

    def test_default_complex_functions_hide_test_files(self):
        r = sample_report()
        r["functions"].append({"file": "tests/test_a.py", "function": "test_thing", "ccn": 40, "nloc": 50, "params": 0, "start": 1, "end": 50})
        text = rendered(r, [])
        fn = text[text.index("Complex functions"):]
        self.assertNotIn("tests/test_a.py", fn)
        self.assertIn("1 function in a test file hidden; --full shows them", fn)
        full_text = rendered(r, [], full=True)
        self.assertIn("tests/test_a.py", full_text[full_text.index("Complex functions"):])

    def test_default_complex_functions_hide_vendored_code_and_say_so(self):
        r = sample_report()
        r["functions"].append({"file": "vendor/github.com/x/y.go", "function": "validate", "ccn": 179, "nloc": 424, "params": 3, "start": 1, "end": 424})
        r["functions"].append({"file": "tests/test_a.py", "function": "test_thing", "ccn": 40, "nloc": 50, "params": 0, "start": 1, "end": 50})
        fn = _section_text(rendered(r, [], width=200), "Complex functions")
        self.assertNotIn("vendor/", fn)
        self.assertIn("1 function in a test file hidden; 1 function in vendored code hidden; --full shows them", fn)
        full = _section_text(rendered(r, [], width=200, full=True), "Complex functions")
        self.assertIn("vendor/github.com/x/y.go", full)

    def test_default_tables_hide_generated_files_and_say_so(self):
        r = sample_report()
        r["meta"]["generated"] = ["lib/config-validator.js"]
        r["size"]["files"]["lib/config-validator.js"] = {"code": 1153, "complexity": 373}
        r["revisions"].append({"entity": "lib/config-validator.js", "n-revs": 8})
        r["functions"].append({"file": "lib/config-validator.js", "function": "validate10", "ccn": 373, "nloc": 1150, "params": 5, "start": 1, "end": 1150})
        text = rendered(r, [], width=200)
        hot = text[text.index("◆ Hotspots"):text.index("Change coupling")]
        self.assertNotIn("config-validator", hot)
        self.assertIn("1 generated file hidden; --full shows them", hot)
        fn = _section_text(text, "Complex functions")
        self.assertNotIn("validate10", fn)
        self.assertIn("1 function in a generated file hidden; --full shows them", fn)
        full = rendered(r, [], width=200, full=True)
        self.assertIn("validate10", full)

    def test_default_hotspots_hide_release_plumbing_and_say_so(self):
        r = sample_report()
        r["size"]["files"].update({"setup.py": {"code": 6, "complexity": 0}, "version.go": {"code": 2, "complexity": 0}})
        r["revisions"] += [{"entity": "setup.py", "n-revs": 184}, {"entity": "version.go", "n-revs": 29}]
        hot = rendered(r, [], width=200)
        hot = hot[hot.index("◆ Hotspots"):hot.index("Change coupling")]
        self.assertNotIn("setup.py", hot)
        self.assertIn("2 release files hidden; --full shows them", hot)
        full = rendered(r, [], width=200, full=True)
        self.assertIn("setup.py", full[full.index("◆ Hotspots"):])

    def test_default_hotspots_hide_files_the_change_log_shows_as_plumbing(self):
        r = sample_report()
        r["size"]["files"]["pkg/__init__.py"] = {"code": 40, "complexity": 0}
        r["revisions"].append({"entity": "pkg/__init__.py", "n-revs": 331})
        r["plumbing"] = [{"entity": "pkg/__init__.py", "n-revs": 331, "tiny-revs": 300}]
        hot = rendered(r, [], width=200)
        hot = hot[hot.index("◆ Hotspots"):hot.index("Change coupling")]
        self.assertNotIn("pkg/__init__.py", hot)
        self.assertIn("1 release file hidden; --full shows them", hot)

    def test_default_coupling_hides_vendored_pairs_and_says_so(self):
        r = sample_report()
        for f in ("deps/lua/a.c", "deps/lua/b.c", "src/x.c", "src/y.c"):
            r["size"]["files"][f] = {"code": 30, "complexity": 1}
        r["coupling"] = [{"entity": "deps/lua/a.c", "coupled": "deps/lua/b.c", "degree": 90, "average-revs": 20},
                         {"entity": "deps/lua/a.c", "coupled": "src/x.c", "degree": 70, "average-revs": 9},
                         {"entity": "src/x.c", "coupled": "src/y.c", "degree": 60, "average-revs": 9}]
        coupling = _section_text(rendered(r, [], width=200), "Change coupling")
        self.assertIn("src/y.c", coupling)
        self.assertNotIn("deps/", coupling)
        self.assertIn("2 vendored pairs hidden; --full shows them", coupling)

    def test_default_coupling_hides_generated_pairs_and_says_so(self):
        r = sample_report()
        r["meta"]["generated"] = ["js/a.bundle.js", "js/b.bundle.js"]
        for f in ("js/a.bundle.js", "js/b.bundle.js", "js/b.js", "src/x.js", "src/y.js"):
            r["size"]["files"][f] = {"code": 30, "complexity": 1}
        r["coupling"] = [{"entity": "js/a.bundle.js", "coupled": "js/b.bundle.js", "degree": 83, "average-revs": 20},
                         {"entity": "js/b.bundle.js", "coupled": "js/b.js", "degree": 83, "average-revs": 20},
                         {"entity": "src/x.js", "coupled": "src/y.js", "degree": 60, "average-revs": 9}]
        coupling = _section_text(rendered(r, [], width=200), "Change coupling")
        self.assertIn("src/y.js", coupling)
        self.assertNotIn("bundle", coupling)
        self.assertIn("2 generated pairs hidden; --full shows them", coupling)

    def test_default_coupling_hides_header_pairs_and_says_so(self):
        r = sample_report()
        for f in ("src/vector.c", "src/vector.h", "src/list.c"):
            r["size"]["files"][f] = {"code": 30, "complexity": 1}
        r["coupling"] = [{"entity": "src/vector.c", "coupled": "src/vector.h", "degree": 100, "average-revs": 20},
                         {"entity": "src/list.c", "coupled": "src/vector.h", "degree": 60, "average-revs": 9}]
        coupling = _section_text(rendered(r, [], width=200), "Change coupling")
        self.assertIn("src/list.c", coupling)
        self.assertNotIn("100%", coupling)
        self.assertIn("1 header pair hidden; --full shows them", coupling)
        full = _section_text(rendered(r, [], width=200, full=True), "Change coupling")
        self.assertIn("100%", full)

    def test_default_coupling_hides_release_plumbing_pairs_and_says_so(self):
        r = sample_report()
        for f in ("lib/version.rb", "contrib/version.rb", "Gemfile", "Gemfile.lock"):
            r["size"]["files"][f] = {"code": 3, "complexity": 0}
        r["coupling"] = [{"entity": "lib/version.rb", "coupled": "contrib/version.rb", "degree": 64, "average-revs": 60},
                         {"entity": "Gemfile", "coupled": "Gemfile.lock", "degree": 90, "average-revs": 20},
                         {"entity": "static/index.html", "coupled": "static/apps-metadata.json", "degree": 90, "average-revs": 11}]
        coupling = _section_text(rendered(r, [], width=200), "Change coupling")
        self.assertIn("static/index.html", coupling)
        self.assertNotIn("version.rb", coupling)
        self.assertIn("2 release pairs hidden; --full shows them", coupling)
        full = _section_text(rendered(r, [], width=200, full=True), "Change coupling")
        self.assertIn("version.rb", full)

    def test_default_complex_functions_hide_example_code_and_amalgamations(self):
        r = sample_report()
        r["functions"].append({"file": "examples/demo.js", "function": "main", "ccn": 30, "nloc": 90, "params": 0, "start": 1, "end": 90})
        for i in range(25):
            r["functions"].append({"file": f"src/part{i % 3}.js", "function": f"f{i}", "ccn": 12, "nloc": 30, "params": 1, "start": 1, "end": 30})
            r["functions"].append({"file": "dist/all.js", "function": f"f{i}", "ccn": 12, "nloc": 30, "params": 1, "start": 1, "end": 30})
        fn = _section_text(rendered(r, [], width=200), "Complex functions")
        self.assertNotIn("examples/demo.js", fn)
        self.assertNotIn("dist/all.js", fn)
        self.assertIn("1 function in example code hidden; 25 functions in generated files hidden; --full shows them", fn)

    def test_hotspots_with_only_test_files_say_what_was_hidden(self):
        r = sample_report()
        r["revisions"] = [{"entity": "tests/test_a.py", "n-revs": 200}]
        r["size"]["files"] = {"tests/test_a.py": {"code": 50, "complexity": 1}}
        hot = _section_text(rendered(r, [], width=200), "\u25c6 Hotspots")
        self.assertIn("no source hotspots; 1 test file hidden; --full shows them", hot)

    def test_default_coupling_hides_pairs_of_deleted_files_and_says_so(self):
        r = sample_report()   # the tree holds static/index.html and static/apps-metadata.json only
        r["coupling"] = [{"entity": "static/index.html", "coupled": "static/apps-metadata.json", "degree": 90, "average-revs": 11},
                         {"entity": "static/tax.html", "coupled": "static/treasury.html", "degree": 85, "average-revs": 11}]
        coupling = _section_text(rendered(r, [], width=200), "Change coupling")
        self.assertIn("static/index.html", coupling)
        self.assertNotIn("static/tax.html", coupling)
        self.assertIn("1 historical pair hidden; --full shows them", coupling)
        full = _section_text(rendered(r, [], width=200, full=True), "Change coupling")
        self.assertIn("static/tax.html", full)
        self.assertNotIn("hidden", full)

    def test_default_hotspots_hide_deleted_files_and_say_so(self):
        r = sample_report()   # the tree holds static/index.html and static/apps-metadata.json only
        r["revisions"].append({"entity": "src/sizes/old.go", "n-revs": 40})
        hot = _section_text(rendered(r, [], width=200), "◆ Hotspots")
        self.assertNotIn("src/sizes/old.go", hot)
        self.assertIn("1 deleted file hidden; --full shows them", hot)
        full = _section_text(rendered(r, [], width=200, full=True), "◆ Hotspots")
        self.assertIn("src/sizes/old.go", full)
        self.assertNotIn("hidden", full)

    def test_hotspots_without_a_tree_listing_hide_nothing(self):
        r = sample_report()
        r["size"]["files"] = {}
        hot = _section_text(rendered(r, [], width=200), "◆ Hotspots")
        self.assertIn("static/index.html", hot)
        self.assertNotIn("deleted", hot)

    def test_default_coupling_collapses_a_directory_that_changes_as_one(self):
        r = sample_report()
        files = [f"rich/_unicode_data/unicode{n}.py" for n in ("10", "11", "12", "13")]
        for f in files:
            r["size"]["files"][f] = {"code": 600, "complexity": 0}
        r["coupling"] = [{"entity": a, "coupled": b, "degree": 100, "average-revs": 5} for i, a in enumerate(files) for b in files[i + 1:]]
        r["coupling"].append({"entity": "static/index.html", "coupled": "static/apps-metadata.json", "degree": 90, "average-revs": 11})
        coupling = _section_text(rendered(r, [], width=200), "Change coupling")
        self.assertIn("rich/_unicode_data/ (4 files)", coupling)
        self.assertIn("each other", coupling)
        self.assertIn("≥100%", coupling)
        self.assertNotIn("unicode10", coupling)
        self.assertIn("static/index.html", coupling)
        self.assertIn("6 pairs in 1 directory shown as one row; --full shows them", coupling)
        full = _section_text(rendered(r, [], width=200, full=True), "Change coupling")
        self.assertIn("unicode10", full)
        self.assertNotIn("each other", full)

    def test_coupling_with_only_test_pairs_says_what_was_hidden(self):
        r = sample_report()
        r["coupling"] = [{"entity": "static/tax.html", "coupled": "tests/test_tax.py", "degree": 100, "average-revs": 11}]
        coupling = _section_text(rendered(r, [], width=200), "Change coupling")
        self.assertIn("no source pairs with 5+ shared revisions; 1 test pair hidden; --full shows them", coupling)

    def test_coupling_with_nothing_to_show_keeps_its_plain_note(self):
        r = sample_report()
        r["coupling"] = []
        coupling = _section_text(rendered(r, [], width=200), "Change coupling")
        self.assertIn("no pairs with 5+ shared revisions", coupling)
        self.assertNotIn("hidden", coupling)

    def test_complex_functions_with_only_test_files_say_what_was_hidden(self):
        r = sample_report()
        r["functions"] = [{"file": "tests/test_a.py", "function": "test_thing", "ccn": 40, "nloc": 50, "params": 0, "start": 1, "end": 50}]
        fn = _section_text(rendered(r, [], width=200), "Complex functions")
        self.assertIn("nothing over complexity 10 in source files (1 function measured); "
                      "1 function in a test file hidden; --full shows them", fn)

    def test_complex_functions_with_nothing_to_show_keep_their_plain_note(self):
        r = sample_report()
        r["functions"] = [{"file": "static/js/app.js", "function": "render", "ccn": 2, "nloc": 5, "params": 0, "start": 1, "end": 5}]
        fn = _section_text(rendered(r, [], width=200), "Complex functions")
        self.assertIn("nothing over complexity 10 (1 function measured)", fn)
        self.assertNotIn("hidden", fn)


class HideTests(unittest.TestCase):
    """render._hide_tests: the rows dropped from the default tables and the caption that counts them."""

    def hide(self, paths, full=False, **kw):
        rows = [{"path": p} for p in paths]
        kept, note = render._hide_tests(rows, lambda r: r["path"], full, **kw)
        return [r["path"] for r in kept], note

    def test_full_hides_nothing(self):
        kept, note = self.hide(["app.py", "tests/test_app.py"], full=True)
        self.assertEqual(kept, ["app.py", "tests/test_app.py"])
        self.assertIsNone(note)

    def test_markdown_export_still_hides(self):
        kept, note = self.hide(["app.py", "tests/test_app.py"], full="markdown")
        self.assertEqual(kept, ["app.py"])
        self.assertEqual(note, "1 test file hidden; --full shows them")

    def test_nothing_hidden_has_no_note(self):
        kept, note = self.hide(["app.py", "util.py"])
        self.assertEqual(kept, ["app.py", "util.py"])
        self.assertIsNone(note)

    def test_a_pair_goes_when_either_side_is_a_test(self):
        pairs = [("app.py", "util.py"), ("app.py", "tests/test_app.py"), ("tests/test_util.py", "util.py")]
        kept, note = render._hide_tests(pairs, lambda p: p, False, noun="test pair")
        self.assertEqual(kept, [("app.py", "util.py")])
        self.assertEqual(note, "2 test pairs hidden; --full shows them")

    def test_singular_and_plural_of_the_default_noun(self):
        self.assertEqual(self.hide(["tests/test_a.py"])[1], "1 test file hidden; --full shows them")
        self.assertEqual(self.hide(["tests/test_a.py", "tests/test_b.py"])[1], "2 test files hidden; --full shows them")

    def test_singular_and_plural_of_a_multi_word_noun(self):
        kw = {"noun": "function in a test file", "plural": "functions in test files"}
        self.assertEqual(self.hide(["tests/test_a.py"], **kw)[1], "1 function in a test file hidden; --full shows them")
        self.assertEqual(self.hide(["tests/test_a.py", "tests/test_b.py"], **kw)[1],
                         "2 functions in test files hidden; --full shows them")

    def test_the_count_is_every_hidden_row_not_only_the_visible_ones(self):
        kept, note = self.hide(["app.py"] + [f"tests/test_{i}.py" for i in range(12)])
        self.assertEqual(kept, ["app.py"])
        self.assertEqual(note, "12 test files hidden; --full shows them")   # hiding happens before any row cap


class Activity(unittest.TestCase):
    def test_activity_shows_weekdays_and_busiest_hour(self):
        text = rendered(sample_report(), [], full=True)
        self.assertIn("Activity", text)
        self.assertRegex(text, r"Thu\s+60")
        self.assertIn("busiest hour 10:00", text)

    def test_activity_notes_the_share_of_fix_commits(self):
        r = sample_report()
        r["activity"]["fix_commits"] = 58
        self.assertIn("25% of commits are fixes", rendered(r, [], full=True))

    def test_activity_absent_when_no_data(self):
        r = sample_report()
        r["activity"] = {}
        self.assertIn("no activity data", rendered(r, [], full=True))


class ComplexFunctions(unittest.TestCase):
    def test_section_lists_functions_by_complexity(self):
        text = rendered(sample_report(), [], full=True)
        self.assertIn("Complex functions", text)
        self.assertRegex(text, r"render\s+static/js/app.js\s+27\s+180\s+4")
        self.assertRegex(text, r"render.*\n.*tidy", "worst first")

    def test_absent_without_data(self):
        r = sample_report()
        r["functions"] = []
        self.assertIn("Complex functions: no function metrics (install lizard)", rendered(r, []))

    def test_note_says_why_there_is_nothing(self):
        r = sample_report()
        r["functions"] = []
        for status, note in (("skipped", "no function metrics (install lizard)"), ("timeout", "function metrics timed out"),
                             ("failed", "function metrics failed (see run.log)"), ("run", "no functions found in the code files"),
                             ("planned", "function metrics did not complete")):
            r["meta"]["functions"] = {"status": status}
            self.assertIn(f"Complex functions: {note}", rendered(r, []), status)

    def test_a_partial_run_says_so_even_with_rows(self):
        r = sample_report()
        for status, reason in (("timeout", "function metrics timed out"), ("failed", "function metrics failed (see run.log)")):
            r["meta"]["functions"] = {"status": status}
            sec = next(x for x in render.sections(r, full=True) if x["title"] == "Complex functions")
            self.assertTrue(sec["rows"])
            self.assertEqual(sec["caption"], f"partial: {reason}", status)
        r["meta"]["functions"] = {"status": "timeout"}
        r["functions"] = [{"file": "a.py", "function": "simple", "ccn": 2, "nloc": 5, "params": 0, "start": 1, "end": 5}]
        self.assertIn("Complex functions: nothing over complexity 10 (1 function measured; partial: function metrics timed out)", rendered(r, []))

    def test_a_partial_run_keeps_the_more_caption(self):
        r = sample_report()
        r["meta"]["functions"] = {"status": "timeout"}
        r["functions"] = [{"file": f"f{i}.py", "function": f"fn{i}", "ccn": 20, "nloc": 30, "params": 0, "start": 1, "end": 30} for i in range(10)]
        sec = next(x for x in render.sections(r, full=False) if x["title"] == "Complex functions")
        self.assertEqual(sec["caption"], "and 2 more; partial: function metrics timed out")

    def test_long_paths_are_elided_like_every_other_table(self):
        r = sample_report()
        r["functions"] = [{"file": "static/javascript/components/deeply/nested/directory/structure/app.js", "function": "render",
                           "ccn": 27, "nloc": 180, "params": 4, "start": 10, "end": 200}]
        text = rendered(r, [], width=80)
        self.assertRegex(text, r"render\s+static/…/structure/app.js\s+27")
        self.assertNotIn("component\n", text)

    def test_ties_break_by_file_function_and_line_not_by_arrival(self):
        r = sample_report()
        r["functions"] = [{"file": "z.py", "function": "b", "ccn": 12, "nloc": 30, "params": 0, "start": 9, "end": 20},
                          {"file": "a.py", "function": "c", "ccn": 12, "nloc": 30, "params": 0, "start": 5, "end": 20},
                          {"file": "a.py", "function": "c", "ccn": 12, "nloc": 30, "params": 0, "start": 1, "end": 4}]
        sec = next(x for x in render.sections(r, full=True) if x["title"] == "Complex functions")
        self.assertEqual([(row[1], row[0]) for row in sec["rows"]], [("a.py", "c"), ("a.py", "c"), ("z.py", "b")])

    def test_a_long_function_name_does_not_squeeze_the_path_to_the_floor(self):
        r = sample_report()
        r["functions"] = [{"file": "src/main/java/com/example/service/impl/AccountServiceImpl.java",
                           "function": "shouldReturnTheAccountWhenTheIdentifierIsKnownAndActive",
                           "ccn": 27, "nloc": 180, "params": 4, "start": 10, "end": 200}]
        sec = next(x for x in render.sections(r, full=False, width=100) if x["title"] == "Complex functions")
        self.assertEqual(sec["rows"][0][1], "src/…/impl/AccountServiceImpl.java", "the directory survives; only the name would at the 16-char floor")

    def test_only_functions_over_the_floor(self):
        r = sample_report()
        r["functions"] = [{"file": "a.py", "function": "simple", "ccn": 9, "nloc": 300, "params": 0, "start": 1, "end": 300}]
        text = rendered(r, [])
        self.assertNotIn("simple", text)
        self.assertIn("Complex functions: nothing over complexity 10 (1 function measured)", text)
        r["functions"].append({"file": "a.py", "function": "twisty", "ccn": 10, "nloc": 20, "params": 0, "start": 1, "end": 20})
        text = rendered(r, [])
        self.assertRegex(text, r"twisty\s+a.py\s+10\s+20")
        self.assertNotIn("simple", text)
        self.assertNotIn("more", text, "the caption counts only functions over the floor")


class WatchList(unittest.TestCase):
    def test_leads_the_tables_with_reasons_in_words(self):
        r = sample_report()
        r["authors"].append({"entity": "static/index.html", "n-authors": 1, "n-revs": 51})
        r["ownership"].append({"entity": "static/index.html", "author": "Ann", "added": 4000, "deleted": 0})
        text = rendered(r, [], width=120)
        self.assertIn("◎ Watch list", text)
        self.assertRegex(text, r"static/index.html\s+changed 51 times · only Ann has touched it")
        self.assertRegex(text, r"static/apps-metadata.json\s+changed 128 times · fixed 4 times in six months")
        self.assertIn("ranked by churn × recent fixes × complexity × single ownership", text)

    def test_capped_at_five_by_default_and_fifteen_in_full(self):
        r = sample_report()
        r["revisions"] = [{"entity": f"f{i}.py", "n-revs": 100 - i} for i in range(20)]
        r["size"]["files"] = {f"f{i}.py": {"code": 10, "complexity": 0} for i in range(20)}
        compact = next(x for x in render.sections(r, full=False) if x["id"] == "watch")
        self.assertEqual(len(compact["rows"]), 5)
        self.assertNotIn("more", compact["caption"] or "", "a watch list is not a table to page through")
        full = next(x for x in render.sections(r, full=True) if x["id"] == "watch")
        self.assertEqual(len(full["rows"]), 15)
        md = next(x for x in render.sections(r, full="markdown") if x["id"] == "watch")
        self.assertEqual(len(md["rows"]), 15)

    def test_paths_stay_whole(self):
        r = sample_report()
        deep = "static/javascript/components/deeply/nested/directory/structure/app.js"
        r["revisions"] = [{"entity": deep, "n-revs": 9}, {"entity": "static/index.html", "n-revs": 2}]
        r["size"]["files"][deep] = {"code": 100, "complexity": 1}
        text = rendered(r, [], width=100)
        self.assertIn(deep, text.split("◎ Watch list")[1].split("◉ People")[0])

    def test_note_when_nothing_qualifies(self):
        r = sample_report()
        r["revisions"] = []
        self.assertIn("Watch list: nothing changed more than once", rendered(r, []))

    def test_note_names_the_real_reason_when_files_did_change(self):
        r = sample_report()
        r["size"]["files"] = {}
        text = rendered(r, [])
        self.assertIn("Watch list: no size data for the files that changed", text)
        self.assertNotIn("nothing changed more than once", text)
        r = sample_report()
        r["revisions"] = [{"entity": "tests/test_a.py", "n-revs": 40}]
        self.assertIn("Watch list: only test files changed more than once", rendered(r, []))

    def test_caption_says_when_ownership_and_churn_are_windowed(self):
        r = sample_report()
        r["meta"]["since"] = "2025-01-01"
        sec = next(x for x in render.sections(r, full=False) if x["id"] == "watch")
        self.assertEqual(sec["caption"], "ranked by churn × recent fixes × complexity × single ownership; commits since 2025-01-01")


class DescriptiveTables(unittest.TestCase):
    def test_default_report_leaves_them_out_and_full_brings_them_back(self):
        text = rendered(sample_report(), [])
        for title in ("Size by language", "Activity", "Surviving code by year written"):
            self.assertNotIn(title, text, title)
        full = rendered(sample_report(), [], full=True)
        for title in ("Size by language", "Activity", "Surviving code by year written"):
            self.assertIn(title, full, title)

    def test_header_keeps_one_line_of_them(self):
        r = sample_report()
        r["activity"]["fix_commits"] = 58
        text = rendered(r, [])
        self.assertIn("most commits on Thu at 10:00  ·  25% of commits are fixes  ·  76% of surviving code from 2025", text)
        r["activity"] = {}
        r["cohorts"] = {}
        self.assertNotIn("most commits", rendered(r, []))

    def test_header_line_says_when_code_age_did_not_run(self):
        # the age table is --full only now, so the header is where the timeout has to show
        r = sample_report()
        r["cohorts"] = {}
        for status, phrase in (("timeout", "code age timed out"), ("skipped", "code age skipped"), ("failed", "code age failed")):
            r["meta"]["age"] = {"status": status}
            self.assertIn(phrase, rendered(r, []), status)
            self.assertIn(phrase, render.markdown(r, []), status)
        r["meta"]["age"] = {"status": "run"}
        self.assertNotIn("code age", rendered(r, []), "an empty table after a normal run is not a header phrase")

    def test_header_line_is_in_markdown_too(self):
        self.assertIn("most commits on Thu at 10:00 · 76% of surviving code from 2025", render.markdown(sample_report(), []))


class KnowledgeMap(unittest.TestCase):
    def test_section_lists_areas_with_owners(self):
        text = rendered(sample_report(), [], full=True)
        self.assertIn("Knowledge map", text)
        self.assertRegex(text, r"static/\s+1,000\s+2\s+-\s+Ann \(90%\)\s+Bob \(10%\)")
        self.assertRegex(text, r"tests/\s+300\s+1\s+-\s+Bob \(100%\)")

    def test_absent_without_ownership(self):
        r = sample_report()
        r["ownership"] = []
        self.assertIn("no ownership data", rendered(r, []))

    def test_default_map_hides_areas_no_longer_in_the_tree_and_says_so(self):
        r = sample_report()   # the tree holds static/ files only; tests/t.py in the ownership rows is history
        r["ownership"].append({"entity": "flask/app.py", "author": "Ann", "added": 4000, "deleted": 0})
        km = _section_text(rendered(r, [], width=200), "Knowledge map")
        self.assertIn("static/", km)
        self.assertNotIn("flask/", km)
        self.assertNotIn("tests/", km)
        self.assertIn("2 historical areas hidden; --full shows them", km)
        r["size"]["files"]["tests/t.py"] = {"code": 1, "complexity": 0}
        km = _section_text(rendered(r, [], width=200), "Knowledge map")
        self.assertIn("tests/", km, "a file back in the tree brings its area back")
        self.assertIn("1 historical area hidden; --full shows them", km)
        full = _section_text(rendered(r, [], width=200, full=True), "Knowledge map")
        self.assertIn("flask/", full)
        self.assertNotIn("hidden", full)

    def test_map_without_a_tree_listing_hides_nothing(self):
        r = sample_report()
        r["size"]["files"] = {}
        km = _section_text(rendered(r, [], width=200), "Knowledge map")
        self.assertIn("tests/", km)
        self.assertNotIn("historical", km)


class Timeline(unittest.TestCase):
    def test_last_twelve_months_per_author_with_dots_for_zero(self):
        text = rendered(sample_report(), [], width=120)
        self.assertIn("Timeline (Oct 2025 → Sep 2026)", text)
        self.assertRegex(text, r"Ann\s+3(\s+·){9}\s+12\s+7")
        self.assertRegex(text, r"Bob(\s+·){11}\s+5")
        self.assertIn("Oct", text)
        self.assertNotIn("Old Timer", text, "authors with no commits in the window are left out")

    def test_timeline_starts_at_the_window(self):
        r = sample_report()
        r["meta"]["since"] = "2026-07-15"
        text = rendered(r, [], width=120)
        self.assertIn("Timeline (Jul 2026 → Sep 2026)", text)
        self.assertNotIn("Oct", text)

    def test_people_caption_says_what_is_windowed(self):
        r = sample_report()
        r["meta"]["since"] = "2026-07-15"
        text = rendered(r, [])
        self.assertIn("commits since 2026-07-15; surviving code is for the whole tree", text)

    def test_bots_are_left_out_of_the_timeline_and_named_under_people(self):
        r = sample_report()
        r["meta"]["bots"] = [{"name": "renovate[bot]", "commits": 940}, {"name": "github-actions[bot]", "commits": 195}]
        r["activity"]["timeline"]["renovate[bot]"] = {"2026-08": 30, "2026-09": 40}
        text = rendered(r, [], width=120)
        self.assertNotIn("renovate[bot]", text.split("◉ People")[0], "the panel and findings do not mention bots")
        self.assertRegex(text, r"Ann\s+3(\s+·){9}\s+12\s+7")
        self.assertNotIn("renovate[bot]   ", text, "no timeline row for a bot")
        self.assertIn("bots left out: renovate[bot] (940 commits), github-actions[bot] (195)", text)
        self.assertNotIn("bots left out", rendered(sample_report(), []))

    def test_a_bot_recognised_only_by_email_has_no_timeline_row_either(self):
        r = sample_report()
        r["meta"]["bots"] = [{"name": "GitHub", "commits": 12}]   # actions@github.com: a bot by its address, not its name
        r["activity"]["timeline"]["GitHub"] = {"2026-08": 30, "2026-09": 40}
        text = rendered(r, [], width=120)
        timeline = text.split("▦ Timeline")[1].split("◆ Hotspots")[0]
        self.assertNotIn("GitHub", timeline)
        self.assertIn("Ann", timeline)

    def test_people_caption_names_who_had_aliases_merged(self):
        r = sample_report()
        r["meta"]["identities"][0]["aliases"] = [{"name": "ann-x", "email": "1@users.noreply.github.com", "commits": 3}]
        text = rendered(r, [])
        self.assertIn("aliases merged for Ann; a .mailmap makes that permanent", text)
        self.assertNotIn("aliases merged", rendered(sample_report(), []))

    def test_secrets_line_counts_distinct_values_and_the_placeholders_left_out(self):
        def row(value, file, commit, placeholder=False):
            return {"rule": "r", "file": file, "commit": commit, "line": 1, "fingerprint": f"{commit}:{file}", "value": value, "placeholder": placeholder}
        r = sample_report()
        r["secrets"] = [row("h1", "a.py", "c1"), row("h1", "a.py", "c2"), row("h2", "tests/b.py", "c1"), row("h3", "p.json", "c1", True)]
        self.assertIn("Secrets: 2 distinct values in 3 places; 1 placeholder-shaped hit left out", render.secrets_line(r))
        r["secrets"] = [row("h3", "p.json", "c1", True)]
        self.assertEqual(render.secrets_line(r), "Secrets: none found; 1 placeholder-shaped hit left out")
        self.assertEqual(render.secrets_line(sample_report()), "Secrets: none found")

    def test_timeline_absent_without_data(self):
        r = sample_report()
        r["activity"] = {}
        self.assertIn("no timeline data", rendered(r, []))


class Layout(unittest.TestCase):
    def test_header_carries_the_findings_tally(self):
        f = [{"severity": "warning", "title": "Bus factor of one", "detail": "Ann wrote 79% of the code."},
             {"severity": "info", "title": "x", "detail": "y."}]
        self.assertIn("1 warning, 1 note", rendered(sample_report(), f))
        self.assertIn("nothing flagged", rendered(sample_report(), []))

    def test_findings_are_grouped_with_one_advice_line(self):
        f = [{"severity": "info", "title": "One person under several identities", "detail": "a <a@x> merged into A <A@x> by name and email similarity. Add a .mailmap to make it permanent."},
             {"severity": "info", "title": "One person under several identities", "detail": "b <b@x> merged into B <B@x> by name and email similarity. Add a .mailmap to make it permanent."}]
        text = rendered(sample_report(), f)
        self.assertIn("One person under several identities (2)", text)
        self.assertEqual(text.count("Add a .mailmap"), 1)
        self.assertIn("↳ Add a .mailmap to make it permanent.", text)
        self.assertIn("a <a@x> merged into A <A@x>", text)

    def test_sections_open_with_a_symbol_and_a_title(self):
        text = rendered(sample_report(), [], width=80)
        self.assertRegex(text, r"\n\n◉ People\n")
        self.assertRegex(text, r"\n\n◆ Hotspots\n")
        self.assertNotIn("─────", text.split("◉ People")[1].split("\n")[0], "no rule across the width")

    def test_small_tables_sit_side_by_side_on_wide_terminals(self):
        wide = rendered(sample_report(), [], width=120, full=True)
        line = next(l for l in wide.splitlines() if "▤ Size by language" in l)
        self.assertIn("◉ People", line)
        line = next(l for l in wide.splitlines() if "◔ Activity" in l)
        self.assertIn("◷ Surviving code by year written", line)
        narrow = rendered(sample_report(), [], width=80, full=True)
        line = next(l for l in narrow.splitlines() if "▤ Size by language" in l)
        self.assertNotIn("People", line)

    def test_people_and_knowledge_map_pair_up_in_the_default_report(self):
        wide = rendered(sample_report(), [], width=120)
        line = next(l for l in wide.splitlines() if "◉ People" in l)
        self.assertIn("⌂ Knowledge map", line)
        self.assertLess(wide.index("◎ Watch list"), wide.index("◉ People"), "the watch list comes first")

    def test_share_columns_carry_inline_bars(self):
        text = rendered(sample_report(), [], width=80)
        people = text[text.index("◉ People"):text.index("⌂ Knowledge map")]
        self.assertRegex(people, r"Ann\s+234\s+64% ▰{6}")
        text = rendered(sample_report(), [], width=80, full=True)
        size = text[text.index("▤ Size by language"):text.index("◉ People")]
        self.assertRegex(size, r"HTML\s+28\s+4,783\s+88% ▰{8}")

    def test_grades(self):
        self.assertEqual(render.cell_style("share", "64%"), "bold #ff5cc8")
        self.assertEqual(render.cell_style("share", "25%"), "#ff9ee0")
        self.assertIsNone(render.cell_style("share", "3%"))
        self.assertEqual(render.cell_style("degree", "95%"), "bold #ff5cc8")
        self.assertEqual(render.cell_style("fixes", "5"), "bold #ff5cc8")

    def test_default_columns_are_the_ones_you_read(self):
        secs = {x["title"]: x for x in render.sections(sample_report(), full=False)}
        self.assertNotIn("Size by language", secs)
        self.assertEqual(secs["People"]["columns"], ["author", "commits", "share", "surviving code"])
        self.assertEqual([x for x in secs if x.startswith("Hotspots")], ["Hotspots"])
        self.assertEqual(secs["Hotspots"]["columns"], ["file", "revs", "lines", "fixes", "authors", "trend"])
        self.assertEqual(secs["Change coupling"]["columns"], ["file", "changes with", "degree"])
        self.assertEqual(secs["Knowledge map"]["columns"], ["area", "lines added", "main owner", "second"])

    def test_full_restores_every_column_and_row(self):
        secs = {x["title"]: x for x in render.sections(sample_report(), full=True)}
        self.assertEqual(secs["Size by language"]["columns"], ["language", "files", "code", "share", "complexity"])
        self.assertIn("email", secs["People"]["columns"])
        self.assertEqual(secs["Hotspots (score = revisions × lines of code)"]["columns"], ["file", "revs", "lines", "cplx", "score", "fixes", "authors", "idle", "trend"])
        self.assertIn("avg revs", secs["Change coupling"]["columns"])

    def test_row_caps_and_the_more_line(self):
        r = sample_report()
        r["revisions"] = [{"entity": f"f{i}.py", "n-revs": 100 - i} for i in range(12)]
        r["size"]["files"] = {f"f{i}.py": {"code": 10, "complexity": 0} for i in range(12)}
        compact = {x["title"]: x for x in render.sections(r, full=False)}["Hotspots"]
        self.assertEqual(len(compact["rows"]), 8)
        self.assertEqual(compact["caption"], "and 4 more")
        full = {x["title"]: x for x in render.sections(r, full=True)}["Hotspots (score = revisions × lines of code)"]
        self.assertEqual(len(full["rows"]), 12)
        self.assertIsNone(full["caption"])

    def test_long_paths_are_elided_not_folded(self):
        r = sample_report()
        long = "packages/core/src/repowise/core/pipeline/persist_and_more_words.py"
        r["revisions"] = [{"entity": long, "n-revs": 50}]
        r["size"]["files"] = {long: {"code": 100, "complexity": 1}}
        text = rendered(r, [], width=80)
        self.assertIn("…/pipeline/persist_and_more_words.py", text)
        self.assertNotIn(long, text)
        hot = text[text.index("\n◆ Hotspots"):]
        self.assertNotRegex(hot, r"\n\s*[a-z_]+\.py\s*\n", "no folded file-name tails")

    def test_threshold_styles(self):
        self.assertIsNone(render.cell_style("degree", "70%"))
        self.assertIsNone(render.cell_style("fixes", "2"))
        self.assertIsNone(render.cell_style("file", "5"))


class ReviewFixes(unittest.TestCase):
    def test_print_section_draws_heading_table_and_note(self):
        c = Console(file=io.StringIO(), width=80, record=True, force_terminal=False, color_system=None)
        render.print_section(c, render._section("File types", [("type", {})], [["py"]], caption="c = code"))
        render.print_section(c, render._section("Portfolio (0 repositories)", [("repo", {})], [], note="no repositories"))
        text = c.export_text()
        self.assertRegex(text, r"\n▥ File types\n")
        self.assertIn("c = code", text)
        self.assertIn("Portfolio (0 repositories): no repositories", text)

    def test_full_lifts_the_timeline_cap(self):
        r = sample_report()
        r["activity"]["timeline"] = {f"Author {i:02d}": {"2026-09": 12 - i} for i in range(12)}
        compact = next(x for x in render.sections(r, full=False) if x["title"].startswith("Timeline"))
        full = next(x for x in render.sections(r, full=True) if x["title"].startswith("Timeline"))
        self.assertEqual((len(compact["rows"]), compact["caption"]), (8, "and 4 more"))
        self.assertEqual((len(full["rows"]), full["caption"]), (12, None))

    def test_paths_fit_next_to_wide_numbers_at_narrow_widths(self):
        r = sample_report()
        long = "services/payments/adapters/stripe_webhook_handler_v2.py"
        r["revisions"] = [{"entity": long, "n-revs": 12345}]
        r["size"]["files"] = {long: {"code": 1234567, "complexity": 9}}
        # 75 is the narrowest width where the 31-character file name fits beside these numbers
        for width in (75, 76, 84):
            text = rendered(r, [], width=width)
            hot = text[text.index("\n◆ Hotspots"):]
            self.assertNotRegex(hot, r"\n\s*[a-z_0-9]+\.py\s*\n", f"folded tail at width {width}")
            self.assertNotRegex(hot, r"\.p\s*\n", f"file name cut at width {width}")

    def test_markdown_rows_are_capped_unless_full(self):
        r = sample_report()
        r["revisions"] = [{"entity": f"f{i}.py", "n-revs": 200 - i} for i in range(60)]
        r["size"]["files"] = {f"f{i}.py": {"code": 10, "complexity": 0} for i in range(60)}
        import re as _re
        rows = lambda md: len(_re.findall(r"^\| f\d+\.py \|", md[md.index("## Hotspots"):], _re.M))
        md = render.markdown(r, [])
        self.assertEqual(rows(md), 50)
        self.assertIn("_and 10 more_", md)
        self.assertEqual(rows(render.markdown(r, [], full=True)), 60)

    def test_repo_health_findings_group(self):
        f = [{"severity": "warning", "title": "Repo health", "detail": "Blobs: Maximum size is 21.3 MiB at a.mp4. git-sizer level of concern 2."},
             {"severity": "info", "title": "Repo health", "detail": "Trees: Maximum entries is 2.1 k. git-sizer level of concern 1."}]
        text = rendered(sample_report(), f)
        self.assertIn("Repo health (2)", text)

    def test_a_group_shows_every_distinct_next_step(self):
        f = [{"severity": "warning", "title": "Repo health", "detail": "Commits: Count is 900 k. git-sizer level of concern 2. Consider a shallow clone for CI; the history is the cost.",
              "advice": "Consider a shallow clone for CI; the history is the cost."},
             {"severity": "warning", "title": "Repo health", "detail": "Blobs: Maximum size is 240 MiB at static/v.mp4. git-sizer level of concern 3. Move large files to Git LFS or rewrite them out of history.",
              "advice": "Move large files to Git LFS or rewrite them out of history."}]
        text = rendered(sample_report(), f)
        self.assertIn("↳ Consider a shallow clone for CI; the history is the cost.", text)
        self.assertIn("↳ Move large files to Git LFS or rewrite them out of history.", text)
        md = render.markdown(sample_report(), f)
        self.assertIn("_Consider a shallow clone for CI; the history is the cost._ _Move large files to Git LFS or rewrite them out of history._", md)

    def test_fixes_threshold_has_no_dead_recent_branch(self):
        self.assertIsNone(render.cell_style("recent", "9"))

    def test_portfolio_markdown_groups_findings_like_the_report(self):
        rep = sample_report()
        f = [{"severity": "info", "title": "One person under several identities", "detail": "a merged into A by name and email similarity. Add a .mailmap to make it permanent."},
             {"severity": "info", "title": "One person under several identities", "detail": "b merged into B by name and email similarity. Add a .mailmap to make it permanent."}]
        md = render.portfolio_markdown("acme", [("demo", rep, f)])
        self.assertIn("One person under several identities (2)", md)
        self.assertEqual(md.count("Add a .mailmap"), 1)
        self.assertIn("- **ok** No secrets in history", md, "each repository says when its scan came back clean")


class Sections(unittest.TestCase):
    def test_sections_carry_title_columns_and_rows_in_report_order(self):
        secs = render.sections(sample_report(), full=True)
        titles = [x["title"] for x in secs]
        self.assertEqual(titles[:5], ["Watch list", "Size by language", "People", "Knowledge map", "Activity"])
        self.assertTrue(titles[5].startswith("Timeline"))
        self.assertTrue(titles[6].startswith("Hotspots"))
        self.assertEqual(titles[-2], "Complex functions")
        self.assertEqual(titles[-1], "Repo health (git-sizer concerns)")
        self.assertEqual([x["id"] for x in secs][:4], ["watch", "size", "people", "knowledge"])
        size = secs[1]
        self.assertEqual(size["columns"][:3], ["language", "files", "code"])
        self.assertEqual(size["rows"][0][0], "HTML")

    def test_empty_section_has_a_note_instead_of_rows(self):
        r = sample_report()
        r["coupling"] = []
        sec = next(x for x in render.sections(r, full=True) if x["title"] == "Change coupling")
        self.assertEqual(sec["rows"], [])
        self.assertEqual(sec["note"], "no pairs with 5+ shared revisions")


class Markdown(unittest.TestCase):
    def test_markdown_has_header_findings_and_tables(self):
        f = [{"severity": "warning", "title": "Bus factor of one", "detail": "Ann wrote 79% of the code."}]
        md = render.markdown(sample_report(), f)
        self.assertTrue(md.startswith("# demo"))
        self.assertIn("363 commits", md)
        self.assertIn("## Findings", md)
        self.assertIn("**warning** Bus factor of one", md)
        self.assertIn("## Watch list", md)
        self.assertIn("## Size by language", md, "the export keeps every table")
        self.assertIn("| language | files | code |", md)
        self.assertIn("| HTML | 28 | 4,783 |", md)
        self.assertIn("static/apps-metadata.json", md)
        self.assertIn("Secrets: none found", md)
        self.assertNotIn("╭", md)

    def test_markdown_escapes_pipes_and_notes_empty_tables(self):
        r = sample_report()
        r["coupling"] = []
        r["revisions"] = [{"entity": "weird|name.py", "n-revs": 3}]
        r["size"]["files"]["weird|name.py"] = {"code": 5, "complexity": 0}   # in the tree, so not hidden as deleted
        md = render.markdown(r, [])
        self.assertIn("weird\\|name.py", md)
        self.assertIn("_no pairs with 5+ shared revisions_", md)
        self.assertIn("Nothing flagged.", md)
        self.assertIn("- **ok** No secrets in history", md)
        r["secrets_scanned"] = False
        self.assertNotIn("No secrets in history", render.markdown(r, []))


class Json(unittest.TestCase):
    def test_to_json_is_serialisable_and_carries_findings_and_meta(self):
        import json as _json
        f = [{"severity": "info", "title": "x", "detail": "y"}]
        text = _json.dumps(render.to_json(sample_report(), f))
        d = _json.loads(text)
        self.assertEqual(d["meta"]["name"], "demo")
        self.assertEqual(d["findings"], f)
        self.assertEqual(d["size"]["total_code"], 5421)
        self.assertIn("revisions", d)
        self.assertIn("cohorts", d)
        self.assertEqual(d["watch"][0]["file"], "static/apps-metadata.json")
        self.assertIn("reasons", d["watch"][0])

    def test_the_nested_backtest_sub_report_is_left_out(self):
        r = sample_report()
        past = sample_report()
        past["meta"] = {"now": "2026-03-10"}
        r["backtest"] = past
        j = render.to_json(r, [])
        self.assertNotIn("backtest", j, "a second whole report inside the export helps nobody")
        self.assertIn("watch_backtest", j, "the numbers drawn from it stay")


class ChangeRisk(unittest.TestCase):
    RISK = {"files": [{"file": "core/parser.py", "score": 3.0, "reasons": ["changed 40 times", "fixed 5 times in six months"], "watched": True},
                      {"file": "core/util.py", "score": 0.6, "reasons": ["changed 30 times"], "watched": True},
                      {"file": "core/new.py", "score": 0, "reasons": ["new file"], "watched": False}],
            "total": 3.6, "watched": 2, "max_score": 3.0}

    def test_section_has_a_bar_scaled_to_the_worst_file_in_the_repo(self):
        sec = render.risk_section(self.RISK, "main", full=False)
        self.assertEqual(sec["title"], "Change risk (3 files since main)")
        self.assertEqual(sec["columns"], ["file", "risk", "why"])
        self.assertEqual(sec["rows"][0], ["core/parser.py", "▰▰▰▰▰▰▰▰▰▰", "changed 40 times · fixed 5 times in six months"])
        self.assertEqual(sec["rows"][1][1], "▰▰")
        self.assertEqual(sec["rows"][2][1], "")
        self.assertEqual(sec["caption"], "total 3.6; 2 of these files are on the watch list")

    def test_one_watched_file_reads_as_one_file(self):
        risk = {"files": [{"file": "core/parser.py", "score": 3.0, "reasons": ["changed 40 times"], "watched": True}],
                "total": 3.0, "watched": 1, "max_score": 3.0}
        sec = render.risk_section(risk, "main", full=False)
        self.assertEqual(sec["caption"], "total 3.0; 1 of these files is on the watch list")

    def test_capped_rows_come_from_the_shared_limit_helper(self):
        risk = {"files": [{"file": f"f{i}.py", "score": 1.0, "reasons": ["changed 3 times"], "watched": False} for i in range(20)],
                "total": 20.0, "watched": 0, "max_score": 1.0}
        self.assertEqual(len(render.risk_section(risk, "main", full=False)["rows"]), render.RISK_CAP)
        self.assertIn("and 5 more", render.risk_section(risk, "main", full=False)["caption"])
        self.assertEqual(len(render.risk_section(risk, "main", full="markdown")["rows"]), render.RISK_CAP)
        self.assertEqual(len(render.risk_section(risk, "main", full=True)["rows"]), 20)

    def test_the_section_follows_the_watch_list_not_the_last_table(self):
        import io
        from rich.console import Console
        console = Console(file=io.StringIO(), width=120, record=True, force_terminal=False, color_system=None)
        render.report(sample_report(), [], console, full=False, risk={"base": "main", **self.RISK}, base="main")
        text = console.export_text()
        self.assertLess(text.index("◈ Change risk"), text.index("◉ People"), "the risk of this change belongs with the watch list")
        self.assertGreater(text.index("◈ Change risk"), text.index("◎ Watch list"))
        md = render.markdown(sample_report(), [], risk={"base": "main", **self.RISK}, base="main")
        self.assertLess(md.index("## Change risk"), md.index("## People"))
        self.assertGreater(md.index("## Change risk"), md.index("## Watch list"))

    def test_empty_change(self):
        sec = render.risk_section({"files": [], "total": 0.0, "watched": 0, "max_score": 0.0}, "main", full=False)
        self.assertEqual(sec["note"], "no files changed since main")

    def test_json_carries_the_risk_when_given(self):
        j = render.to_json(sample_report(), [], risk={"base": "main", **self.RISK})
        self.assertEqual(j["change_risk"]["base"], "main")
        self.assertEqual(j["change_risk"]["total"], 3.6)
        self.assertNotIn("change_risk", render.to_json(sample_report(), []))


if __name__ == "__main__":
    unittest.main()

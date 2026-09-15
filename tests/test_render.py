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
                 "files": {"static/apps-metadata.json": {"code": 800, "complexity": 0}, "static/index.html": {"code": 4000, "complexity": 12}}},
        "revisions": [{"entity": "static/apps-metadata.json", "n-revs": 128}, {"entity": "static/index.html", "n-revs": 51}],
        "authors": [{"entity": "static/apps-metadata.json", "n-authors": 4, "n-revs": 128}],
        "coupling": [{"entity": "static/tax.html", "coupled": "static/treasury.html", "degree": 85, "average-revs": 11}],
        "age": [{"entity": "static/index.html", "age-months": 0}],
        "sizer": [{"name": "Blobs: Maximum size", "value": "21.3 MiB", "concern": 2, "ref": "static/video/clip.mp4"}],
        "cohorts": {"Code added in 2025": 8733, "Code added in 2026": 2728},
        "theseus_authors": {"Ann": 9076, "Bob": 2342},
        "secrets": [],
        "ownership": [{"entity": "static/a.html", "author": "Ann", "added": 900, "deleted": 0},
                      {"entity": "static/b.html", "author": "Bob", "added": 100, "deleted": 0},
                      {"entity": "tests/t.py", "author": "Bob", "added": 300, "deleted": 0}],
        "activity": {"by_weekday": [40, 50, 45, 60, 30, 5, 3], "by_hour": [0] * 9 + [20, 30, 25] + [0] * 12,
                     "by_month": {"2026-07": 10, "2026-08": 20, "2026-09": 12}, "authors": {},
                     "timeline": {"Ann": {"2025-10": 3, "2026-08": 12, "2026-09": 7}, "Bob": {"2026-09": 5},
                                  "Old Timer": {"2019-01": 400}}},
    }


def rendered(report, findings, width=120):
    console = Console(file=io.StringIO(), width=width, record=True, force_terminal=False, color_system=None)
    render.report(report, findings, console)
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

    def test_tables_show_people_hotspots_coupling_age_and_health(self):
        text = rendered(sample_report(), [])
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

    def test_empty_coupling_table_says_none_and_keeps_short_title(self):
        r = sample_report()
        r["coupling"] = []
        text = rendered(r, [], width=60)
        self.assertIn("Change coupling", text)
        self.assertIn("no pairs with 5+ shared revisions", text)
        self.assertNotIn("together)\n", text.replace("(files that change\ntogether)", "together)\n"))

    def test_age_falls_back_to_last_changed_years_when_theseus_skipped(self):
        r = sample_report()
        r["cohorts"] = {}
        r["meta"]["age"] = {"status": "skipped", "files": 80000, "budget": 50000}
        r["activity"] = {}
        r["age"] = [{"entity": "a", "age-months": 0}, {"entity": "b", "age-months": 2},
                    {"entity": "c", "age-months": 14}, {"entity": "d", "age-months": 30}]
        text = rendered(r, [])
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
        text = rendered(r, [])
        self.assertIn("Net lines added by year", text)
        self.assertIn("code age skipped", text)
        self.assertRegex(text, r"2025\s+8,000\s+80%")
        self.assertNotIn("Paths in history", text)

    def test_age_says_when_blame_timed_out(self):
        r = sample_report()
        r["cohorts"] = {}
        r["meta"]["age"] = {"status": "timeout"}
        r["activity"] = {}
        self.assertIn("code age timed out", rendered(r, []))

    def test_hotspots_rank_by_revisions_times_lines_and_show_complexity(self):
        r = sample_report()
        r["revisions"] = [{"entity": "static/apps-metadata.json", "n-revs": 128}, {"entity": "static/index.html", "n-revs": 51},
                          {"entity": "gone.py", "n-revs": 300}]
        text = rendered(r, [])
        lines = [l for l in text.splitlines() if l.startswith(("static/", "gone.py"))]
        # index.html: 51 x 4000 = 204,000 beats metadata.json: 128 x 800 = 102,400; deleted gone.py sorts last
        self.assertTrue(lines[0].startswith("static/index.html"), lines)
        self.assertTrue(lines[1].startswith("static/apps-metadata.json"), lines)
        self.assertTrue(lines[2].startswith("gone.py"), lines)
        self.assertRegex(lines[0], r"51\s+4,000\s+12")
        self.assertIn("score", text)

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


class Activity(unittest.TestCase):
    def test_activity_shows_weekdays_and_busiest_hour(self):
        text = rendered(sample_report(), [])
        self.assertIn("Activity", text)
        self.assertRegex(text, r"Thu\s+60")
        self.assertIn("busiest hour 10:00", text)

    def test_activity_absent_when_no_data(self):
        r = sample_report()
        r["activity"] = {}
        self.assertIn("no activity data", rendered(r, []))


class KnowledgeMap(unittest.TestCase):
    def test_section_lists_areas_with_owners(self):
        text = rendered(sample_report(), [])
        self.assertIn("Knowledge map", text)
        self.assertRegex(text, r"static/\s+1,000\s+2\s+Ann \(90%\)\s+Bob \(10%\)")
        self.assertRegex(text, r"tests/\s+300\s+1\s+Bob \(100%\)")

    def test_absent_without_ownership(self):
        r = sample_report()
        r["ownership"] = []
        self.assertIn("no ownership data", rendered(r, []))


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

    def test_timeline_absent_without_data(self):
        r = sample_report()
        r["activity"] = {}
        self.assertIn("no timeline data", rendered(r, []))


class Sections(unittest.TestCase):
    def test_sections_carry_title_columns_and_rows_in_report_order(self):
        secs = render.sections(sample_report())
        titles = [x["title"] for x in secs]
        self.assertEqual(titles[:3], ["Size by language", "People", "Activity"])
        self.assertTrue(titles[3].startswith("Timeline"))
        self.assertEqual(titles[-2], "Knowledge map")
        self.assertTrue(titles[4].startswith("Hotspots"))
        self.assertEqual(titles[-1], "Repo health (git-sizer concerns)")
        size = secs[0]
        self.assertEqual(size["columns"][:3], ["language", "files", "code"])
        self.assertEqual(size["rows"][0][0], "HTML")

    def test_empty_section_has_a_note_instead_of_rows(self):
        r = sample_report()
        r["coupling"] = []
        sec = next(x for x in render.sections(r) if x["title"] == "Change coupling")
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
        self.assertIn("## Size by language", md)
        self.assertIn("| language | files | code |", md)
        self.assertIn("| HTML | 28 | 4,783 |", md)
        self.assertIn("static/apps-metadata.json", md)
        self.assertIn("Secrets: none found", md)
        self.assertNotIn("╭", md)

    def test_markdown_escapes_pipes_and_notes_empty_tables(self):
        r = sample_report()
        r["coupling"] = []
        r["revisions"] = [{"entity": "weird|name.py", "n-revs": 3}]
        md = render.markdown(r, [])
        self.assertIn("weird\\|name.py", md)
        self.assertIn("_no pairs with 5+ shared revisions_", md)
        self.assertIn("Nothing flagged.", md)


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


if __name__ == "__main__":
    unittest.main()

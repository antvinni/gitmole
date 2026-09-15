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
                 "total_code": 5421, "total_files": 35},
        "revisions": [{"entity": "static/apps-metadata.json", "n-revs": 128}, {"entity": "static/index.html", "n-revs": 51}],
        "authors": [{"entity": "static/apps-metadata.json", "n-authors": 4, "n-revs": 128}],
        "coupling": [{"entity": "static/tax.html", "coupled": "static/treasury.html", "degree": 85, "average-revs": 11}],
        "age": [{"entity": "static/index.html", "age-months": 0}],
        "sizer": [{"name": "Blobs: Maximum size", "value": "21.3 MiB", "concern": 2, "ref": "static/video/clip.mp4"}],
        "cohorts": {"Code added in 2025": 8733, "Code added in 2026": 2728},
        "theseus_authors": {"Ann": 9076, "Bob": 2342},
        "secrets": [],
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

    def test_footer_points_at_output_dir(self):
        self.assertIn("/tmp/analysis-demo", rendered(sample_report(), []))

    def test_fits_a_narrow_terminal_without_error(self):
        text = rendered(sample_report(), [], width=80)
        self.assertTrue(all(len(line) <= 80 for line in text.splitlines()), "a line exceeds 80 columns")


if __name__ == "__main__":
    unittest.main()

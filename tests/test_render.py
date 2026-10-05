import json
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
        "cohorts": {"Code added in 2025": 8733, "Code added in 2026": 2728},
        "theseus_authors": {"Ann": 9076, "Bob": 2342},
        "secrets": [],
        "secrets_scanned": True,
        "fixes": [{"entity": "static/apps-metadata.json", "n-fixes": 9, "last-fix": "2026-09-01", "recent-fixes": 4}],
        "functions": [{"file": "static/js/app.js", "function": "render", "ccn": 27, "nloc": 180, "params": 4, "start": 10, "end": 200},
                      {"file": "static/js/util.js", "function": "tidy", "ccn": 12, "nloc": 30, "params": 1, "start": 1, "end": 31}],
        "dependencies": {"status": "scanned", "sources": [{"path": "package-lock.json", "packages": 120}, {"path": "uv.lock", "packages": 31}],
                         "packages": 151, "vulnerable": [], "database_date": "2026-09-16"},
        "ownership": [{"entity": "static/a.html", "author": "Ann", "added": 900, "deleted": 0},
                      {"entity": "static/b.html", "author": "Bob", "added": 100, "deleted": 0},
                      {"entity": "tests/t.py", "author": "Bob", "added": 300, "deleted": 0}],
        "activity": {"by_weekday": [40, 50, 45, 60, 30, 5, 3], "by_hour": [0] * 9 + [20, 30, 25] + [0] * 12,
                     "by_month": {"2026-07": 10, "2026-08": 20, "2026-09": 12}, "authors": {},
                     "timeline": {"Ann": {"2025-10": 3, "2026-08": 12, "2026-09": 7}, "Bob": {"2026-09": 5},
                                  "Old Timer": {"2019-01": 400}}},
    }


def _section_text(text: str, heading: str) -> str:
    """One section of the rendered report: from its heading to the blank line that ends it."""
    return text[text.index(heading):].split("\n\n")[0]


def _titled(secs, name: str) -> dict:
    """The section called `name`, whatever its title's qualifier says ("Complex functions · 8 of 475, by complexity")."""
    return next(x for x in secs if render._base_title(x["title"]) == name)


def rendered(report, findings, width=120, full=False, compare=None):
    console = Console(file=io.StringIO(), width=width, record=True, force_terminal=False, color_system=None)
    render.report(report, findings, console, full=full, compare=compare)
    return console.export_text()


def _rendered_section(sec: dict, width=120) -> str:
    """One section drawn on its own, the way `rendered` draws a whole report: for Hotspots, which
    the default terminal report no longer carries, but whose drawing (folding, eliding, hiding) is
    still worth checking directly."""
    console = Console(file=io.StringIO(), width=width, record=True, force_terminal=False, color_system=None)
    render.print_section(console, sec)
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
        self.assertIn("betterleaks scanned every commit HEAD reaches", text)
        f = [{"severity": "warning", "title": "Bus factor of one", "detail": "Ann wrote 79% of the code."}]
        text = rendered(sample_report(), f)
        self.assertIn("─ Findings · 1 warning ▲ ─", text, "the pass line is not a finding and is not counted")
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

    def test_a_clean_dependency_scan_is_said_out_loud_and_in_the_footer(self):
        text = rendered(sample_report(), [])
        self.assertIn("✔ No known vulnerabilities in dependencies", text)
        self.assertIn("osv-scanner checked 151 packages in 2 lock files against the local database from 2026-09-16", text)
        self.assertIn("Dependencies: 151 packages in 2 lock files, none vulnerable (database from 2026-09-16)", rendered(sample_report(), [], full=True))
        self.assertLess(text.index("No secrets in history"), text.index("No known vulnerabilities"), "secrets first")

    def test_the_default_report_does_not_repeat_two_clean_scans_in_the_footer(self):
        r = sample_report()
        r["unreachable"] = {"objects": 4, "scanned": 3}
        text = rendered(r, [])
        self.assertNotIn("Secrets: none found", text)
        self.assertNotIn("Dependencies: ", text)
        self.assertIn("betterleaks scanned every commit HEAD reaches; 3 unreachable blobs scanned too", text, "what only the footer said moves up")
        self.assertIn("Full results in", text)
        full = rendered(r, [], full=True)
        self.assertIn("Secrets: none found; 3 unreachable blobs scanned too", full)
        self.assertNotIn("HEAD reaches; 3 unreachable", full, "--full keeps the footer, so the line above it stays as it was")
        self.assertIn("Secrets: none found", render.markdown(r, []))

    def test_the_footer_stays_when_either_scan_has_more_to_say(self):
        r = sample_report()
        r["dependencies"]["informational"] = [{"name": "paste", "version": "1.0.15", "kinds": ["unmaintained"]}]
        text = " ".join(rendered(r, []).split())
        self.assertIn("Secrets: none found", text)
        self.assertIn("1 with an informational advisory (paste 1.0.15, unmaintained)", text)
        r = sample_report()
        r["dependencies"] = {"status": "no-sources"}
        text = rendered(r, [])
        self.assertIn("Secrets: none found", text)
        self.assertIn("Dependencies: no lock files found", text)

    def test_vulnerable_packages_drop_the_pass_line_and_count_in_the_footer(self):
        r = sample_report()
        r["dependencies"]["vulnerable"] = [{"name": "lodash", "version": "4.17.15", "source": "package-lock.json", "score": 7.2, "fixed": "4.17.21",
                                            "ids": ["GHSA-1"], "aliases": ["CVE-2021-23337"], "severity": "high", "ecosystem": "npm", "advisories": 1, "summary": ""}]
        text = rendered(r, [])
        self.assertNotIn("No known vulnerabilities", text)
        self.assertIn("Dependencies: 151 packages in 2 lock files, 1 vulnerable (database from 2026-09-16)", text)

    def test_the_footer_counts_packages_and_places_apart(self):
        r = sample_report()
        row = {"name": "lodash", "version": "4.17.15", "source": "package-lock.json", "score": 7.2, "fixed": "4.17.21",
               "ids": ["GHSA-1"], "aliases": [], "severity": "high", "ecosystem": "npm", "advisories": 1, "summary": ""}
        r["dependencies"]["vulnerable"] = [row, {**row, "source": "web/package-lock.json"}]
        self.assertIn("Dependencies: 151 packages in 2 lock files, 1 vulnerable in 2 places (database", rendered(r, []))

    def test_a_requirement_file_is_not_counted_as_a_lock_file(self):
        r = sample_report()
        r["dependencies"]["sources"].append({"path": "tools/requirements.txt", "packages": 3})
        text = rendered(r, [], full=True)
        self.assertIn("osv-scanner checked 151 packages in 2 lock files and 1 requirement file against", text)
        self.assertIn("Dependencies: 151 packages in 2 lock files and 1 requirement file, none vulnerable", text)

    def test_one_lock_file_is_named_and_one_package_is_singular(self):
        """superpowers: "1 packages in 1 lock file" beside "package.json has no package-lock.json"; the lock was a test's."""
        r = sample_report()
        r["dependencies"].update(packages=1, sources=[{"path": "tests/server/package-lock.json", "packages": 1}])
        text = " ".join(rendered(r, [], full=True).split())   # --full: the default report leaves the footer's two lines out when both scans are clean
        self.assertIn("osv-scanner checked 1 package in 1 lock file (tests/server/package-lock.json) against the local database", text)
        self.assertIn("Dependencies: 1 package in 1 lock file (tests/server/package-lock.json), none vulnerable", text)
        self.assertNotIn("1 packages", text)
        self.assertIn("osv-scanner checked 1 package in 1 lock file (tests/server/package-lock.json)", " ".join(rendered(r, []).split()))
        r["dependencies"].update(sources=[{"path": "requirements.txt", "packages": 1}])
        self.assertIn("Dependencies: 1 package in 1 requirement file (requirements.txt), none vulnerable", " ".join(rendered(r, [], full=True).split()))

    def test_the_footer_says_why_dependencies_were_not_scanned(self):
        r = sample_report()
        r["dependencies"] = {"status": "no-sources"}
        text = rendered(r, [])
        self.assertIn("Dependencies: no lock files found", text)
        self.assertNotIn("No known vulnerabilities", text, "nothing was checked")
        r["dependencies"] = {"status": "no-database", "download": "osv-scanner scan source -r --offline-vulnerabilities --download-offline-databases ."}
        text = rendered(r, [])
        self.assertIn("Dependencies: not scanned, no offline vulnerability database; fetch it once: gitmole --fetch-vuln-db", text)
        r["dependencies"] = {"status": "not-run"}
        text = rendered(r, [])
        self.assertNotIn("Dependencies:", text, "an output directory from before the step says nothing")
        self.assertIn("Secrets: none found", text)

    def test_tables_show_people_hotspots_coupling_and_age(self):
        text = rendered(sample_report(), [], full=True)
        self.assertIn("Ann", text)
        self.assertIn("static/apps-metadata.json", text)
        self.assertIn("static/{tax.html,treasury.html}", text)
        self.assertIn("2025", text)
        self.assertNotIn("Repo health", text, "git-sizer's table left at 0.39.0")

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
        self.assertRegex(rendered(r, []), r"commits +3% are reverts")     # 7 of 233 commits in by_weekday
        self.assertNotIn("reverts", rendered(sample_report(), []))
        r["activity"]["revert_commits"] = 1
        self.assertIn("1 revert", rendered(r, []))                     # 1 of 233 commits rounds to 0%
        self.assertNotIn("% are reverts", rendered(r, []))
        r["activity"]["by_weekday"] = [1000, 0, 0, 0, 0, 0, 0]
        r["activity"]["revert_commits"] = 2
        self.assertIn("2 reverts", rendered(r, []))                    # 2 of 1000 commits still rounds to 0%, and is plural

    def test_empty_coupling_collapses_to_one_line(self):
        r = sample_report()
        r["coupling"] = []
        text = rendered(r, [], width=60)
        self.assertIn("Change coupling: no pairs with 5 or more shared changes", text)
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
        text = rendered(r, [], width=140, full=True)   # wide enough for the eleven columns with their paths whole
        text = text[text.index("◆ Hotspots"):]
        lines = [l.strip() for l in text.splitlines() if l.strip().startswith(("static/", "gone.py"))]
        # index.html: 51 x 4000 = 204,000 beats metadata.json: 128 x 800 = 102,400; deleted gone.py has no score and no row
        self.assertTrue(lines[0].startswith("static/index.html"), lines)
        self.assertTrue(lines[1].startswith("static/apps-metadata.json"), lines)
        self.assertFalse([l for l in lines if l.startswith("gone.py")], lines)
        self.assertIn("1 removed file not listed (maat-revisions.csv has them)", " ".join(text.split()))
        self.assertRegex(lines[0], r"51\s+4,000\s+12")
        self.assertIn("score", text)
        self.assertIn("fixes", text)
        self.assertRegex(lines[1], r"static/apps-metadata.json\s+128\s+800\s+0\s+102,400\s+9\s")

    def test_full_hotspots_carry_minor_contributors_and_co_change_columns(self):
        r = sample_report()
        r["authors"] = [{"entity": "static/apps-metadata.json", "n-authors": 4, "n-revs": 128, "minor": 2}]
        r["soc"] = [{"entity": "static/apps-metadata.json", "soc": 300, "partners": 17}]
        text = rendered(r, [], full=True, width=200)
        text = text[text.index("◆ Hotspots"):]
        self.assertIn("minors", text)
        self.assertIn("co-changes", text)
        line = next(l for l in text.splitlines() if "apps-metadata.json" in l)
        self.assertRegex(line, r"128\s+800\s+0\s+102,400\s+9\s+4\s+2\s+17\s")
        md = render.markdown(r, [])
        self.assertNotIn("co-changes", md, "the Markdown table keeps its columns")

    def test_the_header_counts_the_sweeping_commits_left_out_once_for_every_table(self):
        """prometheus said it under the Watch list and in the finding; the coupling and ownership tables leave them out too."""
        r = sample_report()
        r["activity"]["sweeping"] = [{"hash": "a", "files": 40, "date": "2026-01-05", "declared": False}, {"hash": "b", "files": 30, "date": "2026-01-06", "declared": True}]
        r["activity"]["ignored_revs"] = 3
        row = dict(render.header_rows(r))["left out"]
        self.assertEqual(row, [("1 sweeping commit and 3 declared in .git-blame-ignore-revs, not counted in churn, coupling or ownership", "")],
                         "a declared sweep is counted among the declared")
        for full in (False, True):
            text = rendered(r, [], full=full)
            self.assertEqual(text.count("sweeping commit"), 1, "in the header and in no caption")
            self.assertRegex(text, r"│ left out +1 sweeping commit and 3 declared")
        r["activity"]["sweeping"] = [{"hash": "a", "files": 40, "date": "2026-01-05", "declared": False}, {"hash": "c", "files": 41, "date": "2026-01-07", "declared": False}]
        r["activity"]["ignored_revs"] = 0
        self.assertEqual(dict(render.header_rows(r))["left out"][0][0], "2 sweeping commits, not counted in churn, coupling or ownership")
        r["activity"]["sweeping"] = []
        self.assertNotIn("left out", dict(render.header_rows(r)))
        self.assertNotIn("sweeping", rendered(r, []))

    def test_the_reasons_the_columns_do_not_hold_are_under_each_row_in_full_and_a_last_column_in_markdown(self):
        """prometheus's five files took 21 lines of reasons in one wrapped cell; the default table has none."""
        from unittest.mock import patch
        r = sample_report()
        many = ["changed 51 times"] + [f"reason {i}" for i in range(8)]
        with patch.object(render.watch, "_reasons", return_value=many):
            short = next(x for x in render.sections(r, full=False) if x["id"] == "watch")
            full = next(x for x in render.sections(r, full=True) if x["id"] == "watch")
            text = _rendered_section(full, width=60)
            md = render.markdown(r, [])
            exported = render.to_json(r, [])["watch"][0]["reasons"]
        self.assertNotIn("under", short, "one line a file")
        self.assertEqual(short["columns"], ["file", "changes", "fixes", "top author"])
        self.assertEqual(full["under"][0], " · ".join(many[1:]), "the change count is a column, the rest is under the row")
        self.assertEqual(full["rows"][0][:3], ["static/index.html", "51", "0"])
        lines = [line.rstrip() for line in text.splitlines()]
        at = next(i for i, line in enumerate(lines) if line.lstrip().startswith("static/index.html"))
        self.assertEqual(lines[at + 1:at + 3], ["    reason 0 · reason 1 · reason 2 · reason 3 · reason 4 ·", "    reason 5 · reason 6 · reason 7"],
                         "indented under its row, wrapped after a separator and never before one")
        self.assertIn("| file | changes | fixes | top author | also |", md)
        self.assertIn("| static/index.html | 51 | 0 | - | " + " · ".join(many[1:]) + " |", md)
        self.assertEqual(exported, many, "the export keeps every reason, the change count too")

    def test_the_watch_list_s_columns(self):
        r = sample_report()
        r["meta"]["gone_months"] = 12
        r["activity"]["authors_all"] = {"Ann": {"last": "2024-01-01"}, "Bob": {"last": "2026-09-01"}}
        r["revisions"].append({"entity": "static/a.html", "n-revs": 9})
        r["ownership"] += [{"entity": "static/index.html", "author": "Ann", "added": 9, "deleted": 0}, {"entity": "static/index.html", "author": "Bob", "added": 91, "deleted": 0},
                           {"entity": "static/apps-metadata.json", "author": "Ann", "added": 100, "deleted": 0}]
        r["functions"] += [{"file": "static/index.html", "function": "draw", "ccn": 31, "nloc": 90, "params": 1, "start": 5, "end": 95},
                           {"file": "static/a.html", "function": "(anonymous)", "ccn": 12, "nloc": 40, "params": 0, "start": 7, "end": 47}]
        r["structure"] = {"status": "run", "files": {}, "functions": [{"file": "static/index.html", "name": "(anonymous at line 40)", "start": 40, "end": 60, "nesting": 6},
                                                                      {"file": "static/apps-metadata.json", "name": "shallow", "start": 1, "end": 9, "nesting": 4}]}
        sec = next(x for x in render.sections(r, full=False) if x["id"] == "watch")
        self.assertEqual(sec["title"], "Watch list · all 3, ranked by changes × lines of code")
        self.assertEqual(sec["columns"], ["file", "changes", "fixes", "top author", "look at first"])
        self.assertEqual(sec["rows"], [["static/index.html", "51", "0", " 91%", "<anonymous>:40 nesting 6"],
                                       ["static/apps-metadata.json", "128", "4", "100% gone", ""],
                                       ["static/a.html", "9", "0", "100% gone", "<anonymous>:7 complexity 12"]],
                         "the share of the largest author and no name; the deepest function at 5 levels or more, else the most complex at 10 or more; "
                         "the shares end in one column, so gone starts in one")
        self.assertEqual(sec["caption"].split("\n")[0], "fixes = in the 6 months to 2026-09-10 · top author = largest share of the lines added to the file · "
                                                        "gone = no commit in the 12 months to 2026-09-10")
        r["activity"]["authors_all"]["Ann"]["last"] = "2026-09-02"
        sec = next(x for x in render.sections(r, full=False) if x["id"] == "watch")
        self.assertNotIn("gone", sec["caption"], "a word no row carries is not defined")
        self.assertEqual([row[3] for row in sec["rows"]], [" 91%", "100%", "100%"], "blank means active")

    def test_the_last_text_cell_is_cut_at_its_end_after_the_path_has_lost_its_directories(self):
        sec = render._section("Watch list", [("file", render.PATH), ("changes", render.RIGHT), ("top author", render.WHOLE), ("look at first", render.TAIL)],
                              [("storage/remote/otlptranslator/prometheusremotewrite/helper.go", 1234, "23% gone", "writePostingsToTmpFiles() complexity 26")])
        self.assertEqual(render.fit(sec, 82)["rows"][0], ("storage/…/helper.go", "1,234", "23% gone", "writePostingsToTmpFiles() complexity 26"),
                         "the path gives its middle directories first")
        self.assertEqual(render.fit(sec, 80)["rows"][0], ("…/helper.go", "1,234", "23% gone", "writePostingsToTmpFiles() complexity 26"), "all of them before anything else is cut")
        fitted = render.fit(sec, 60)
        self.assertEqual(fitted["rows"][0], ("…/helper.go", "1,234", "23% gone", "writePostingsToTmpFiles()…"), "then the last text cell, at its end; no number is cut")
        text = _rendered_section(sec, width=60)
        self.assertEqual([line.split()[0] for line in text.splitlines() if "helper.go" in line or "…" in line], ["…/helper.go"], "one line for the row")
        for line in text.splitlines():
            self.assertLessEqual(len(line.rstrip()), 60)

    def test_the_duplication_rate_is_no_longer_a_header_phrase(self):
        """The duplicates step left at 0.39.0; an old report dict that still carries its rate says nothing of it."""
        r = sample_report()
        r["duplicates"] = {"rate": 6.1, "blocks": [], "then": {"date": "2025-09-10", "rate": 4.2, "files": 30}}
        self.assertFalse([x for x in render.pulse(r) if "duplicated" in x])

    def test_provenance_is_a_full_only_section_of_trailers_with_the_cohort_and_shape_below(self):
        r = sample_report()
        r["provenance"] = {"trailers": {"commits": 363, "keys": {"Co-authored-by": 40, "Signed-off-by": 12, "Assisted-by": 5}, "with_any": 50,
                                        "never_author": [{"name": "Helper", "email": "h@x", "commits": 30}], "signoff_by_co_author": []},
                           "cohort": {"definition": "an Assisted-by trailer, or a co-author who never authors a commit here or is a coding tool", "share": 0.096,
                                      "cohort": {"commits": 35, "reverted": 2, "fixes": 4, "retouched": 20},
                                      "rest": {"commits": 328, "reverted": 3, "fixes": 60, "retouched": 150}},
                           "shape": {"burst_share": 0.12, "conventional_share": 0.8, "hours_used": 20}, "agents": {}}
        self.assertNotIn("Trailers", rendered(r, [], width=200))
        block = _section_text(rendered(r, [], width=200, full=True), "Trailers")
        self.assertRegex(block, r"Co-authored-by\s+40\s+11%")
        caption = render.trailers_section(r)["caption"]
        self.assertIn("declared commits (an Assisted-by trailer, or a co-author who never authors a commit here or is a coding tool): 35, 10% of the history; "
                      "reverted 6% against 1% for the rest (every commit that declares nothing, undisclosed agent use included), fixes 11% against 18%, a file changed again within 2 weeks 57% against 46%", caption)
        self.assertIn("12% of commits land in bursts of 5 or more within 10 minutes; 80% have conventional-commit subjects; commits come in 20 hours of the day", caption)
        self.assertIn("## Trailers", render.markdown(r, []))

    def test_the_comparison_says_when_the_vulnerability_database_changed(self):
        result = {"new": [], "resolved": [], "persisting": [], "watch_entered": [], "watch_left": [],
                  "tally": {"before": {"critical": 0, "warning": 0, "info": 0}, "after": {"critical": 0, "warning": 0, "info": 0}},
                  "before": {"commit": "abc12345", "date": "2026-09-01", "options_differ": [], "database": {"before": "2026-09-01", "after": "2026-09-17"}}}
        sec = render.compare_section(result)
        text = (sec.get("caption") or "") + (sec.get("note") or "")
        self.assertIn("the vulnerability database changed between the runs (2026-09-01 to 2026-09-17), so a dependency finding can move with no change to the code", text)

    def test_the_comparison_says_when_the_two_exports_came_from_different_gitmole_versions(self):
        """A rule changes in most releases, so a finding can read as new or resolved with nothing about
        the repository having changed."""
        result = {"new": [], "resolved": [], "persisting": [], "watch_entered": [], "watch_left": [],
                  "tally": {"before": {"critical": 0, "warning": 0, "info": 0}, "after": {"critical": 0, "warning": 0, "info": 0}},
                  "before": {"commit": "abc12345", "date": "2026-09-01", "options_differ": [], "database": None,
                             "gitmole": {"before": "0.30.0", "after": "0.33.0"}}}
        sec = render.compare_section(result)
        text = (sec.get("caption") or "") + (sec.get("note") or "")
        self.assertIn("the earlier export was written by gitmole 0.30.0, this one by 0.33.0: "
                      "a rule changed between them moves a finding with no change to the code", text)
        result["before"]["gitmole"] = None
        sec = render.compare_section(result)
        self.assertNotIn("written by gitmole", (sec.get("caption") or "") + (sec.get("note") or ""))
        result["before"]["tools"] = {"lizard": {"before": "1.23.0", "after": "1.24.0"}, "scc": {"before": "4.0.0", "after": "4.1.0"}}
        sec = render.compare_section(result)
        self.assertIn("a tool moved between the runs (lizard 1.23.0 → 1.24.0, scc 4.0.0 → 4.1.0), "
                      "so its counts can move with no change to the code", (sec.get("caption") or "") + (sec.get("note") or ""))

    def test_the_watch_list_by_component_is_a_full_only_section(self):
        r = sample_report()
        self.assertNotIn("Watch list by component", rendered(r, [], width=200))
        self.assertIn("Watch list by component", rendered(r, [], width=200, full=True))
        self.assertIn("## Watch list by component", render.markdown(r, []))
        self.assertIn("watch_by_component", render.to_json(r, []))

    def test_the_json_is_the_same_bytes_for_the_same_clone_whatever_the_run(self):
        import copy
        a = sample_report()
        a["secrets"] = [{"rule": "k", "file": "b.py", "commit": "c2", "line": 3, "fingerprint": "f2", "value": "9f00aa11bb22", "placeholder": False},
                        {"rule": "k", "file": "a.py", "commit": "c1", "line": 1, "fingerprint": "f1", "value": "12ab34cd56ef", "placeholder": False},
                        {"rule": "k", "file": "c.py", "commit": "c3", "line": 2, "fingerprint": "f3", "value": "12ab34cd56ef", "placeholder": False}]
        a["meta"]["age"] = {"status": "run", "projected_seconds": 3.14159, "files": 10}
        a["structure"] = {"status": "run", "cached": 0, "files": {}}
        a["unreachable"] = {"objects": 605, "blobs": 180, "scanned": 180, "findings": 6}
        b = copy.deepcopy(a)
        # another clone of the same commit: its own reflog, its own dropped stashes, its own gc timing
        b["unreachable"] = {"objects": 41, "blobs": 12, "scanned": 12, "findings": 0}
        for row, other in zip(b["secrets"], ("0000ffff1111", "aaaabbbbcccc", "aaaabbbbcccc")):
            row["value"] = other                     # another run: another random key, the same grouping
        b["secrets"].reverse()                       # and betterleaks free to report in another order
        b["meta"]["age"]["projected_seconds"] = 2.71828
        b["structure"]["cached"] = 40
        b["out_dir"] = "/somewhere/else"
        first, second = json.loads(render.dumps_json(a, [])), json.loads(render.dumps_json(b, []))
        self.assertNotEqual(first["envelope"], second["envelope"], "timings, the output path and cache hits vary, and live in the envelope")
        self.assertEqual(first["envelope"]["unreachable"], a["unreachable"],
                         "what no ref reaches belongs to the clone, not the commit: CI compared it across two "
                         "runners and failed the day actions/checkout changed how it fetches")
        self.assertNotIn("unreachable", first, "and so it is not in the part promised to be the same bytes")
        del first["envelope"], second["envelope"]
        self.assertEqual(json.dumps(first, sort_keys=True), json.dumps(second, sort_keys=True))
        self.assertEqual([r["value"] for r in first["secrets"]], ["v1", "v2", "v1"], "the same value, the same label, by the rows' sorted order")
        text = render.dumps_json(a, [])
        self.assertTrue(text.endswith("}\n"))
        self.assertEqual(text, render.dumps_json(a, []))

    def test_the_secrets_line_says_what_lay_outside_reachable_history(self):
        r = sample_report()
        r["unreachable"] = {"objects": 0, "blobs": 0, "scanned": 0, "findings": 0}
        self.assertEqual(render.secrets_line(r), "Secrets: none found; no unreachable objects (a fresh clone fetches only what a ref reaches)")
        r["unreachable"] = {"objects": 12, "blobs": 7, "scanned": 7, "findings": 0}
        self.assertEqual(render.secrets_line(r), "Secrets: none found; 7 unreachable blobs scanned too")
        r["unreachable"] = {}
        self.assertEqual(render.secrets_line(r), "Secrets: none found", "an output directory from before the sweep")

    def test_signing_coverage_is_a_header_phrase_and_a_full_only_table(self):
        r = sample_report()
        r["signing"] = {"commits": 363, "signed": 121, "mechanisms": {"ssh": 100, "gpg": 21},
                        "by_year": {"2025": {"commits": 163, "signed": 21}, "2026": {"commits": 200, "signed": 100}},
                        "humans": {"commits": 340, "signed": 121}, "bots": {"commits": 23, "signed": 0},
                        "by_identity": [{"name": "Ann", "commits": 234, "signed": 120}, {"name": "Bob", "commits": 106, "signed": 1}],
                        "last_year": {"commits": 210, "signed": 105}}
        self.assertIn("33% of commits signed (ssh 28%, gpg 6%), 50% of the last year's", render.pulse(r))
        text = rendered(r, [], width=200)
        self.assertNotIn("◈ Signing", text, "the table is --full only")
        full = rendered(r, [], width=200, full=True)
        self.assertIn("Signing by year", full)
        block = _section_text(full, "Signing by year")
        self.assertRegex(block, r"2026\s+200\s+100\s+50%")
        self.assertIn("humans 36% signed, bots 0%; read from the commit objects, nothing verified", block)
        for surface in (full, render.markdown(r, [], full=True), render.markdown(r, [])):
            self.assertNotIn("Ann 51%", surface, "no rate per person: prometheus's caption ranked four named people by how often they sign")
            self.assertNotIn("Bob 1%", surface)
        self.assertIn("## Signing by year", render.markdown(r, []))
        r["signing"]["forge"] = {"commits": 60, "signed": 60, "mechanisms": {"ssh": 39, "gpg": 21}}
        r["signing"]["last_year"]["forge_signed"] = 105
        self.assertIn("17% of commits signed by their authors (ssh 17%), 0% of the last year's; 17% signed by the forge on merge", render.pulse(r))
        full = rendered(r, [], width=200, full=True)
        self.assertIn("60 of the signed commits were committed and signed by the forge on merge", _section_text(full, "Signing by year"))
        r["signing"]["forge"] = {"commits": 121, "signed": 121, "mechanisms": {"ssh": 100, "gpg": 21}}
        self.assertIn("no commits signed by their authors; 33% signed by the forge on merge", render.pulse(r), "a merge button's key is not developer signing")
        r["signing"]["forge"] = {"commits": 1, "signed": 1, "mechanisms": {"ssh": 1}}
        r["signing"]["last_year"]["forge_signed"] = 1
        self.assertIn("33% of commits signed by their authors (ssh 27%, gpg 6%), 50% of the last year's", render.pulse(r), "a share that rounds to nothing is not spelled out")
        r["signing"] = {"commits": 5, "signed": 0, "mechanisms": {}, "by_year": {"2026": {"commits": 5, "signed": 0}}, "humans": {"commits": 5, "signed": 0},
                        "bots": {"commits": 0, "signed": 0}, "by_identity": [], "last_year": {"commits": 5, "signed": 0}}
        self.assertIn("no commits signed", render.pulse(r))
        r["signing"] = {}
        self.assertFalse([p for p in render.pulse(r) if "signed" in p], "an output directory without the step says nothing")

    def test_footer_path_is_never_wrapped(self):
        r = sample_report()
        r["out_dir"] = "/very/long/" + "x" * 150 + "/analysis-demo"
        text = rendered(r, [], width=80)
        self.assertIn("Full results in " + r["out_dir"], text)

    def test_footer_points_at_output_dir(self):
        self.assertIn("/tmp/analysis-demo", rendered(sample_report(), []))

    def test_the_last_line_names_plots_only_when_a_plot_was_written(self):
        # prometheus's default directory holds no .png, and its last line promised "Full results and plots"
        import os
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            r = dict(sample_report(), out_dir=d)
            self.assertEqual(render.results_line(r), f"Full results in {d}")
            self.assertIn(f"Full results in {d}", render.markdown(r, []))
            open(os.path.join(d, "code-age.png"), "wb").close()
            self.assertEqual(render.results_line(r), f"Full results and plots in {d}")
            self.assertIn(f"Full results and plots in {d}", render.markdown(r, []))
        self.assertEqual(render.results_line(dict(sample_report(), out_dir="/no/such/dir")), "Full results in /no/such/dir")

    def test_a_surviving_code_figure_names_the_step_it_came_from(self):
        # prometheus: 23% from 2026 by blame, 24% once --plots had git-of-theseus rewrite the same two files
        r = sample_report()
        self.assertIsNone(render.surviving_source(r), "an output directory that records neither step")
        self.assertIn("76% of surviving code from 2025", render.pulse(r))
        r["meta"]["age"] = {"status": "run", "method": "blame"}
        r["meta"]["steps"] = {"code age": "run"}
        self.assertIn("76% of surviving code from 2025, by blame", render.pulse(r))
        self.assertIn("surviving = blame share at HEAD", _section_text(rendered(r, []), "People"))
        self.assertRegex(rendered(r, []), r"│ code +5,421 lines · HTML, Python · 76% surviving from 2025, by blame")
        self.assertIn("76% of surviving code from 2025, by blame", render.markdown(r, []))
        r["meta"]["steps"]["git-of-theseus"] = "run"
        self.assertIn("76% of surviving code from 2025, by git-of-theseus", render.pulse(r), "--plots ran after the blame pass, into the same files")
        self.assertIn("surviving = git-of-theseus share at HEAD", _section_text(rendered(r, []), "People"))
        self.assertIn("counted by git-of-theseus", _section_text(rendered(r, [], full=True), "Surviving code by year written"))
        r["meta"]["steps"]["git-of-theseus"] = "failed"
        self.assertIn("76% of surviving code from 2025, by blame", render.pulse(r), "a survival step that did not finish replaced nothing")
        r["meta"]["since"] = "2026-07-15"
        self.assertIn("commits = since 2026-07-15 · share = of commits · surviving = blame share at HEAD, over the whole tree", _section_text(rendered(r, []), "People"))

    def test_a_footer_line_takes_its_colour_from_the_finding_behind_it(self):
        # prometheus: 44 values, none in source and none in a finding, printed red
        mk = lambda rid, sev: {"severity": sev, "title": rid, "detail": "x", "rule": {"id": rid}}   # noqa: E731
        self.assertEqual(render.footer_style([], render.SECRET_FINDINGS, ""), "", "a count with no finding behind it has no colour")
        self.assertEqual(render.footer_style([], render.SECRET_FINDINGS, "green"), "green", "a scan that found nothing")
        self.assertEqual(render.footer_style([mk("bug_magnets", "critical")], render.SECRET_FINDINGS, ""), "", "another rule's finding is not behind this line")
        self.assertEqual(render.footer_style([mk("secrets_possible", "info"), mk("secrets_in_source", "critical")], render.SECRET_FINDINGS, ""), "bold red")
        self.assertEqual(render.footer_style([mk("vulnerable_dependencies", "warning")], render.DEPENDENCY_FINDINGS, ""), "yellow")
        dep = {"status": "scanned", "packages": 5, "sources": [{"path": "go.mod"}], "vulnerable": [{"name": "a", "source": "go.mod"}]}
        self.assertEqual(render.dependencies_line({"dependencies": dep})[1], "", "a vulnerable package is red only through its finding")

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
        self.assertRegex(text, r"static/\s+1,000\s+Ann\s+90%\s+Bob gone\s+10%", "the word after the name, one space, no brackets; the shares in their own columns")
        self.assertIn("gone = no commit in the 12 months to 2026-09-10", text)
        self.assertEqual(text.count("gone = "), 1, "defined once")
        self.assertNotIn("lost", text.split("⌂ Knowledge map")[1].split("\n")[1], "the lost column is --full only")
        full = rendered(r, [], full=True)
        self.assertRegex(full, r"area\s+added\s+authors\s+lost\s+main owner\s+share\s+second\s+share")
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
        self.assertEqual(caption(r), "gone = no commit in the 12 months to 2026-09-10")
        r["meta"]["since"] = "2026-01-01"
        self.assertEqual(caption(r), "gone = no commit in the 12 months to 2026-09-10, measured over the whole history")
        self.assertIsNone(render.knowledge_section(r, full=False)["caption"], "the definition is the report's, given to the first table that prints the word")
        r["meta"]["since"] = None
        r["authors"] = [{"entity": "static/a.html", "n-authors": 1, "n-revs": 9}]
        r["revisions"] = [{"entity": "static/a.html", "n-revs": 9}, {"entity": "static/b.html", "n-revs": 4}]
        secs = {x["id"]: x for x in render.sections(r, full=False)}
        self.assertEqual(secs["watch"]["rows"][1][3], "100% gone", "static/b.html is Bob's")
        self.assertEqual(secs["knowledge"]["rows"][0][4], "Bob gone")
        self.assertIn("gone = no commit in the 12 months to 2026-09-10", secs["watch"]["caption"], "the Watch list prints the word first")
        self.assertIsNone(secs["knowledge"]["caption"], "and the Knowledge map does not define it again")

    def test_the_knowledge_map_says_its_owner_is_not_the_truck_factors_only_beside_a_truck_factor(self):
        """prometheus: web/ is Julius Volz's by lines added and by files authored, tsdb/ only by the first; nothing said the two differ."""
        owner = "owner = by lines added, which is not the Truck factor's measure (files authored)"
        r = sample_report()
        self.assertEqual(render.knowledge_section(r, full=False)["caption"], "1 historical area hidden", "no truck factor was computed here: nothing to tell the owner from")
        r["size"]["files"].update({f"static/p{i}.py": {"code": 10, "complexity": 1} for i in range(20)})
        r["doa"] = [{"entity": f"static/p{i}.py", "author": "Ann", "is_author": True} for i in range(20)]
        self.assertEqual(render.knowledge_section(r, full=False)["caption"], f"1 historical area hidden · {owner}", "what is hidden, then the definitions")
        r["ownership"].append({"entity": "flask/app.py", "author": "Ann", "added": 4000, "deleted": 0})
        self.assertEqual(render.knowledge_section(r, full=False)["caption"], f"2 historical areas hidden · {owner}")

    def test_hotspots_carry_a_trend_column_and_a_sparkline_under_full(self):
        r = sample_report()
        r["meta"]["last_date"] = "2026-09-10"
        r["trend"] = {"samples": ["2025-09-10", "2026-03-10", "2026-09-10"],
                      "files": {"static/index.html": [["2025-09-10", 10, 4000], ["2026-03-10", 12, 4000], ["2026-09-10", 16, 4000]]}}
        text = _rendered_section(render.hotspots_section(r, full="markdown", width=120))
        self.assertRegex(text, r"file\s+changes\s+lines\s+fixes\s+authors\s+trend")
        self.assertRegex(text, r"static/index\.html\s+51\s+4,000\s+0\s+-\s+\+60%")
        self.assertRegex(text, r"static/apps-metadata\.json\s+128\s+800\s+9\s+4\s+-")
        self.assertRegex(rendered(r, [], full=True), r"static/index\.html.*▁▃█")
        self.assertRegex(_rendered_section(render.hotspots_section(sample_report(), full="markdown", width=120)),
                         r"static/index\.html\s+51\s+4,000\s+0\s+-\s+-")

    def test_full_hotspots_say_the_trend_column_covers_the_top_ten(self):
        r = sample_report()
        r["meta"]["last_date"] = "2026-09-10"
        def caption(rep, full):
            return render.hotspots_section(rep, full=full, width=None)["caption"]
        self.assertIsNone(caption(r, True), "no trend data, nothing to explain")
        r["trend"] = {"samples": ["2025-09-10", "2026-09-10"],
                      "files": {"static/index.html": [["2025-09-10", 10, 4000], ["2026-09-10", 16, 4000]]}}
        self.assertEqual(caption(r, True), "trend sampled for the top 10 hotspots")
        r["revisions"] = [{"entity": f"f{i}.py", "n-revs": 100 - i} for i in range(60)]
        r["size"]["files"].update({f"f{i}.py": {"code": 10, "complexity": 0} for i in range(60)})   # in the tree, so not hidden as deleted
        self.assertEqual(caption(r, "markdown"), "and 10 more; trend sampled for the top 10 hotspots")

    def test_watch_list_caption_reports_the_backtest_or_why_not(self):
        r = sample_report()
        r["meta"]["backtest"] = {"status": "skipped", "reason": "too little history to backtest"}
        self.assertIn("Check: none, too little history to backtest", rendered(r, []))
        r = sample_report()
        past = sample_report()
        past["meta"] = {"now": "2026-03-10"}
        r["backtest"] = past
        r["fixes"] = [{"entity": "static/index.html", "n-fixes": 1, "last-fix": "2026-08-01", "recent-fixes": 1},
                      {"entity": "static/other.html", "n-fixes": 1, "last-fix": "2026-08-01", "recent-fixes": 1}]
        text = next(x for x in render.sections(r, full=False) if x["id"] == "watch")["caption"]
        self.assertIn("Check: 6 months ago the top 2 of this ranking held 1 of the 1 file fixed since. The 2 most-changed files also held 1; "
                      "2 random files would hold 1.0, and 1 is not distinguishable from that (p = 1).", text)
        r = sample_report()
        r["meta"]["backtest"] = {"status": "timeout"}
        self.assertIn("Check: none, backtest timed out", next(x for x in render.sections(r, full=False) if x["id"] == "watch")["caption"])
        r = sample_report()
        past = sample_report()
        past["meta"] = {"now": "2026-03-10"}
        r["backtest"] = past
        r["fixes"] = [{"entity": "static/index.html", "n-fixes": 1, "last-fix": "2026-08-01", "recent-fixes": 1},
                      {"entity": "static/other.html", "n-fixes": 1, "last-fix": "2026-08-01", "recent-fixes": 1}]
        self.assertEqual(render.to_json(r, [])["watch_backtest"]["positives"], 1, "static/other.html was not in the pool")
        self.assertEqual(render.to_json(r, [])["watch_backtest"]["hits"], 1)
        self.assertEqual(render.to_json(r, [])["watch_backtest"]["pool"], 2)
        self.assertEqual(render.to_json(r, [])["watch_backtest"]["baselines"]["churn"], 1)

    def test_nothing_fixed_since_the_cut_off_is_one_sentence_not_three_zeros(self):
        r = sample_report()
        past = sample_report()
        past["meta"] = {"now": "2026-03-10"}
        r["backtest"] = past
        r["fixes"] = [{"entity": "static/index.html", "n-fixes": 1, "last-fix": "2026-01-01", "recent-fixes": 0}]   # before the cut-off
        caption = next(x for x in render.sections(r, full=False) if x["id"] == "watch")["caption"]
        self.assertIn("Check: nothing has been fixed since the cut-off 6 months ago, so there is nothing to score this ranking against.", caption)
        self.assertNotIn("0 of the 0", caption)
        self.assertEqual(render.to_json(r, [])["watch_backtest"]["fixed"], 0, "the JSON keeps the numbers")

    def test_backtest_caption_says_whole_history_under_a_window(self):
        r = sample_report()
        past = sample_report()
        past["meta"] = {"now": "2026-03-10"}
        r["backtest"] = past
        r["fixes"] = [{"entity": "static/index.html", "n-fixes": 1, "last-fix": "2026-08-01", "recent-fixes": 1},
                      {"entity": "static/other.html", "n-fixes": 1, "last-fix": "2026-08-01", "recent-fixes": 1}]
        r["meta"]["since"] = "2026-01-01"
        caption = next(x for x in render.sections(r, full=False) if x["id"] == "watch")["caption"]
        self.assertTrue(caption.startswith("changes = commits since 2026-01-01 · fixes = in the 6 months to 2026-09-10 · "), caption)
        self.assertIn("\nCheck, over the whole history: 6 months ago the top 2 of this ranking held 1 of the 1 file fixed since.", caption)

    def test_backtest_words_say_what_the_numbers_mean(self):
        bt = {"t": "2026-03-10", "pool": 1245, "listed": 15, "fixed": 205, "positives": 128, "hits": 3, "expected": 1.5,
              "baselines": {"churn": 5, "size": 2}, "p_by_chance": 0.19}
        self.assertEqual(render.backtest_words(bt),
                         "6 months ago the top 15 of this ranking held 3 of the 128 files fixed since. The 15 most-changed files held 5, more than this ranking; "
                         "15 random files would hold 1.5, and 3 is not distinguishable from that (p = 0.19).",
                         "devlake's, which once read 3 of the 205 beside a random 1.5 out of 128 and said nothing about either")
        self.assertTrue(render.backtest_words(bt, detail=True).endswith(" Counted over the 1,245 files that had changed more than once by then; 77 more files fixed since had not."),
                        "--full and Markdown say what the 128 are out of, and where the other 77 of the 205 went")
        bt.update(hits=9, p_by_chance=0.00002)
        self.assertTrue(render.backtest_words(bt).endswith("held 9 of the 128 files fixed since. The 15 most-changed files held 5, fewer than this ranking; 15 random files would hold 1.5."))
        self.assertTrue(render.backtest_words(bt, detail=True).endswith("had not; p < 0.001."), "the p of a result that is not chance is --full's")
        bt.update(hits=5, p_by_chance=0.0496)
        self.assertTrue(render.backtest_words(bt).endswith("The 15 most-changed files also held 5; 15 random files would hold 1.5."))
        self.assertTrue(render.backtest_words(bt, detail=True).endswith("; p = 0.0496."), "0.0496 is not rounded to a 0.05 that reads as the other side of the line")
        bt.update(hits=5, p_by_chance=0.05)
        self.assertIn("and 5 is not distinguishable from that (p = 0.05)", render.backtest_words(bt), "at the line it is chance, and the default report says so")
        bt.update(positives=0)
        self.assertEqual(render.backtest_words(bt), "None of the 205 files fixed since the cut-off 6 months ago had changed more than once by then, "
                                                    "so there is nothing to score this ranking against.")
        old = {k: v for k, v in bt.items() if k not in ("positives", "p_by_chance")}
        self.assertEqual(render.backtest_words(old), "6 months ago the top 15 of this ranking held 5 of the 205 files fixed since. The 15 most-changed files held 5; "
                                                     "15 random files of the 1,245 that had changed more than once would hold 1.5.",
                         "a backtest recorded before the pool's own count keeps to the counts it has")
        one = {"t": "2026-03-10", "pool": 9, "listed": 1, "fixed": 1, "positives": 1, "hits": 1, "expected": 0.1, "baselines": {"churn": 0, "size": 0}, "p_by_chance": 0.11}
        self.assertIn("The most-changed file held 0, fewer than this ranking; 1 random file would hold 0.1", render.backtest_words(one))

    def test_markdown_hotspots_hide_test_files_and_say_so(self):
        r = sample_report()
        r["revisions"].append({"entity": "tests/test_a.py", "n-revs": 200})
        r["size"]["files"]["tests/test_a.py"] = {"code": 50, "complexity": 1}
        hot = _rendered_section(render.hotspots_section(r, full="markdown", width=120))
        self.assertNotIn("tests/test_a.py", hot)
        self.assertIn("1 test file hidden", hot)
        self.assertNotIn("--full shows them", hot, "the report says where the hidden rows are once, at its end")
        full_text = rendered(r, [], full=True)
        self.assertIn("tests/test_a.py", full_text[full_text.index("◆ Hotspots"):])

    def test_default_coupling_hides_test_pairs_and_says_so(self):
        r = sample_report()
        r["coupling"].append({"entity": "static/tax.html", "coupled": "tests/test_tax.py", "degree": 100, "average-revs": 11})
        text = rendered(r, [], width=200)
        coupling = text[text.index("Change coupling"):]
        self.assertNotIn("tests/test_tax.py", coupling)
        self.assertIn("2 pairs hidden: 1 historical, 1 test", coupling, "the sum with its breakdown")
        self.assertIn(render.FULL_POINTER, text, "one pointer, at the report's end")
        full_text = rendered(r, [], full=True)
        self.assertIn("{static/tax.html,tests/test_tax.py}", full_text[full_text.index("Change coupling"):])

    def test_default_complex_functions_hide_test_files(self):
        r = sample_report()
        r["functions"].append({"file": "tests/test_a.py", "function": "test_thing", "ccn": 40, "nloc": 50, "params": 0, "start": 1, "end": 50})
        text = rendered(r, [])
        fn = text[text.index("Complex functions"):]
        self.assertNotIn("tests/test_a.py", fn)
        self.assertIn("1 test function hidden", fn)
        full_text = rendered(r, [], full=True)
        self.assertIn("tests/test_a.py", full_text[full_text.index("Complex functions"):])

    def test_a_nameless_function_is_anonymous_with_its_file_and_line(self):
        r = sample_report()
        r["functions"].append({"file": "server/routes.ts", "function": 'app.post("/api/x", async (req, res) => {', "anonymous": True,
                               "ccn": 25, "nloc": 60, "params": 0, "start": 1162, "end": 1240, "suspect": ""})
        fn = _section_text(rendered(r, [], width=200), "Complex functions")
        self.assertRegex(fn, r"<anonymous>\s+server/routes.ts:1162")
        self.assertNotIn("app.post", fn, "a start line is not a name")
        self.assertIn("server/routes.ts:1162", fn)
        self.assertNotIn("static/js/app.js:", fn, "a named function is found by its name; the row shows the file alone")

    def test_a_suspect_span_is_marked_and_the_caption_says_what_the_mark_means(self):
        r = sample_report()
        r["functions"].append({"file": "lib/tpl.js", "function": "tpl", "anonymous": False, "ccn": 30, "nloc": 9, "params": 1, "start": 1, "end": 9,
                               "suspect": "opens a block at line 8 no deeper than its own start"})
        fn = _section_text(rendered(r, [], width=200), "Complex functions")
        self.assertIn("30?", fn)
        self.assertIn("? = a span lizard may have mis-parsed (1)", fn)
        plain = _section_text(rendered(sample_report(), [], width=200), "Complex functions")
        self.assertNotIn("?", plain)

    def test_suspect_spans_sort_after_every_trusted_function(self):
        # paperclip: six "?" rows led the table, a 25-line regex helper at complexity 1036 first
        r = sample_report()
        r["functions"] += [{"file": "server/access.ts", "function": "parseSkillFrontmatter", "anonymous": False, "ccn": 1036, "nloc": 4232, "params": 1,
                            "start": 211, "end": 4766, "suspect": "opens a block at line 231 no deeper than its own start"},
                           {"file": "server/runs.ts", "function": "trusted", "anonymous": False, "ccn": 11, "nloc": 30, "params": 1,
                            "start": 1, "end": 30, "suspect": ""}]
        for full in (False, True):
            fn = _section_text(rendered(r, [], width=200, full=full), "Complex functions")
            self.assertLess(fn.index("trusted"), fn.index("parseSkillFrontmatter"), full)
            self.assertIn("1036?", fn)

    def test_a_function_lizard_ended_early_is_marked_at_least_and_sorts_by_its_count(self):
        r = sample_report()
        r["functions"].append({"file": "server/heartbeat.ts", "function": "executeRun", "anonymous": False, "ccn": 55, "nloc": 6394, "params": 2,
                               "start": 20179, "end": 26572, "suspect": "", "lizard_span": {"end": 20446, "nloc": 222}})
        fn = _section_text(rendered(r, [], width=200), "Complex functions")
        self.assertRegex(fn, r"executeRun\s+server/heartbeat.ts\s+55\+\s+6,394")
        self.assertIn("+ = lizard ended the function early (1): its lines are the structure step's, its complexity what lizard counted before it stopped", fn)

    def test_default_complex_functions_hide_vendored_code_and_say_so(self):
        r = sample_report()
        r["functions"].append({"file": "vendor/github.com/x/y.go", "function": "validate", "ccn": 179, "nloc": 424, "params": 3, "start": 1, "end": 424})
        r["functions"].append({"file": "tests/test_a.py", "function": "test_thing", "ccn": 40, "nloc": 50, "params": 0, "start": 1, "end": 50})
        fn = _section_text(rendered(r, [], width=200), "Complex functions")
        self.assertNotIn("vendor/", fn)
        self.assertIn("2 functions hidden: 1 test, 1 vendored", fn)
        full = _section_text(rendered(r, [], width=200, full=True), "Complex functions")
        self.assertIn("vendor/github.com/x/y.go", full)

    def test_markdown_tables_hide_generated_files_and_say_so(self):
        r = sample_report()
        r["meta"]["generated"] = ["lib/config-validator.js"]
        r["size"]["files"]["lib/config-validator.js"] = {"code": 1153, "complexity": 373}
        r["revisions"].append({"entity": "lib/config-validator.js", "n-revs": 8})
        r["functions"].append({"file": "lib/config-validator.js", "function": "validate10", "ccn": 373, "nloc": 1150, "params": 5, "start": 1, "end": 1150})
        text = rendered(r, [], width=200)
        hot = _rendered_section(render.hotspots_section(r, full="markdown", width=200), width=200)
        self.assertNotIn("config-validator", hot)
        self.assertIn("1 generated file hidden", hot)
        fn = _section_text(text, "Complex functions")
        self.assertNotIn("validate10", fn)
        self.assertIn("1 generated function hidden", fn)
        full = rendered(r, [], width=200, full=True)
        self.assertIn("validate10", full)

    def test_markdown_hotspots_hide_release_plumbing_and_say_so(self):
        r = sample_report()
        r["size"]["files"].update({"setup.py": {"code": 6, "complexity": 0}, "version.go": {"code": 2, "complexity": 0}})
        r["revisions"] += [{"entity": "setup.py", "n-revs": 184}, {"entity": "version.go", "n-revs": 29}]
        hot = _rendered_section(render.hotspots_section(r, full="markdown", width=200), width=200)
        self.assertNotIn("setup.py", hot)
        self.assertIn("2 release files hidden", hot)
        full = rendered(r, [], width=200, full=True)
        self.assertIn("setup.py", full[full.index("◆ Hotspots"):])

    def test_markdown_hotspots_hide_files_the_change_log_shows_as_plumbing(self):
        r = sample_report()
        r["size"]["files"]["pkg/__init__.py"] = {"code": 40, "complexity": 0}
        r["revisions"].append({"entity": "pkg/__init__.py", "n-revs": 331})
        r["plumbing"] = [{"entity": "pkg/__init__.py", "n-revs": 331, "tiny-revs": 300}]
        hot = _rendered_section(render.hotspots_section(r, full="markdown", width=200), width=200)
        self.assertNotIn("pkg/__init__.py", hot)
        self.assertIn("1 release file hidden", hot)

    def test_default_coupling_hides_vendored_pairs_and_says_so(self):
        r = sample_report()
        for f in ("deps/lua/a.c", "deps/lua/b.c", "src/x.c", "src/y.c"):
            r["size"]["files"][f] = {"code": 30, "complexity": 1}
        r["coupling"] = [{"entity": "deps/lua/a.c", "coupled": "deps/lua/b.c", "degree": 90, "average-revs": 20},
                         {"entity": "deps/lua/a.c", "coupled": "src/x.c", "degree": 70, "average-revs": 9},
                         {"entity": "src/x.c", "coupled": "src/y.c", "degree": 60, "average-revs": 9}]
        coupling = _section_text(rendered(r, [], width=200), "Change coupling")
        self.assertIn("src/{x.c,y.c}", coupling)
        self.assertNotIn("deps/", coupling)
        self.assertIn("2 vendored pairs hidden", coupling)

    def test_the_coupling_caption_names_the_merge_regime(self):
        r = sample_report()
        r["size"]["files"].update({"static/tax.html": {"code": 30, "complexity": 0}, "static/treasury.html": {"code": 30, "complexity": 0}})
        r["meta"]["merges"] = 2
        r["activity"]["squash_subjects"] = 300
        regime = "83% of subjects end in (#NNNN) and 2 of 363 commits are merges: squash-merged, so the pairs describe pull requests, not edits"
        self.assertIn(regime, _section_text(rendered(r, [], width=200, full=True), "Change coupling"))
        self.assertIn(regime, render.markdown(r, []))
        self.assertNotIn("squash", _section_text(rendered(r, [], width=200), "Change coupling"), "how the table was made is --full's; the default caption says what is hidden and what a row is")
        r["activity"]["squash_subjects"] = 3
        coupling = _section_text(rendered(r, [], width=200, full=True), "Change coupling")
        self.assertNotIn("squash", coupling)

    def test_default_coupling_hides_generated_pairs_and_says_so(self):
        r = sample_report()
        r["meta"]["generated"] = ["js/a.bundle.js", "js/b.bundle.js"]
        for f in ("js/a.bundle.js", "js/b.bundle.js", "js/b.js", "src/x.js", "src/y.js"):
            r["size"]["files"][f] = {"code": 30, "complexity": 1}
        r["coupling"] = [{"entity": "js/a.bundle.js", "coupled": "js/b.bundle.js", "degree": 83, "average-revs": 20},
                         {"entity": "js/b.bundle.js", "coupled": "js/b.js", "degree": 83, "average-revs": 20},
                         {"entity": "src/x.js", "coupled": "src/y.js", "degree": 60, "average-revs": 9}]
        coupling = _section_text(rendered(r, [], width=200), "Change coupling")
        self.assertIn("src/{x.js,y.js}", coupling)
        self.assertNotIn("bundle", coupling)
        self.assertIn("2 generated pairs hidden", coupling)

    def test_default_coupling_hides_header_pairs_and_says_so(self):
        r = sample_report()
        for f in ("src/vector.c", "src/vector.h", "src/list.c"):
            r["size"]["files"][f] = {"code": 30, "complexity": 1}
        r["coupling"] = [{"entity": "src/vector.c", "coupled": "src/vector.h", "degree": 100, "average-revs": 20},
                         {"entity": "src/list.c", "coupled": "src/vector.h", "degree": 60, "average-revs": 9}]
        coupling = _section_text(rendered(r, [], width=200), "Change coupling")
        self.assertIn("src/{list.c,vector.h}", coupling)
        self.assertNotIn("100%", coupling)
        self.assertIn("1 header pair hidden", coupling)
        full = _section_text(rendered(r, [], width=200, full=True), "Change coupling")
        self.assertIn("100%", full)

    def test_default_coupling_hides_locale_pairs_and_says_so(self):
        """univer's top two rows were locale/ clusters: a message added in one locale is added in all of them.
        A locale paired with the code that reads it stays."""
        r = sample_report()
        for f in ("src/locale/en-US.ts", "src/locale/zh-CN.ts", "src/locales/de.ts", "src/locale/index.ts", "src/menu.ts"):
            r["size"]["files"][f] = {"code": 30, "complexity": 1}
        r["coupling"] = [{"entity": "src/locale/en-US.ts", "coupled": "src/locale/zh-CN.ts", "degree": 91, "average-revs": 20},
                         {"entity": "src/locales/de.ts", "coupled": "src/locale/zh-CN.ts", "degree": 88, "average-revs": 20},
                         {"entity": "src/locale/en-US.ts", "coupled": "src/menu.ts", "degree": 60, "average-revs": 9},
                         {"entity": "src/locale/index.ts", "coupled": "src/locale/en-US.ts", "degree": 55, "average-revs": 9}]
        coupling = _section_text(rendered(r, [], width=200), "Change coupling")
        self.assertIn("src/{locale/en-US.ts,menu.ts}", coupling)
        self.assertIn("src/locale/{index.ts,en-US.ts}", coupling)
        self.assertNotIn("zh-CN", coupling)
        self.assertIn("2 locale pairs hidden", coupling)
        full = _section_text(rendered(r, [], width=200, full=True), "Change coupling")
        self.assertIn("91%", full)

    def test_default_coupling_hides_pairs_of_examples_and_says_so(self):
        """curl's top two rows were docs/examples/ clusters: sibling programs showing one technique for
        two protocols. An example paired with the code it demonstrates stays."""
        r = sample_report()
        for f in ("docs/examples/imap-ssl.c", "docs/examples/pop3-ssl.c", "docs/examples/http-post.c", "lib/http.c"):
            r["size"]["files"][f] = {"code": 30, "complexity": 1}
        r["coupling"] = [{"entity": "docs/examples/imap-ssl.c", "coupled": "docs/examples/pop3-ssl.c", "degree": 90, "average-revs": 20},
                         {"entity": "docs/examples/http-post.c", "coupled": "lib/http.c", "degree": 70, "average-revs": 9}]
        coupling = _section_text(rendered(r, [], width=200), "Change coupling")
        self.assertIn("{docs/examples/http-post.c,lib/http.c}", coupling, "an example and the code it demonstrates still count")
        self.assertNotIn("pop3-ssl.c", coupling)
        self.assertIn("1 example pair hidden", coupling)
        full = _section_text(rendered(r, [], width=200, full=True), "Change coupling")
        self.assertIn("pop3-ssl.c", full)

    def test_default_coupling_hides_release_plumbing_pairs_and_says_so(self):
        r = sample_report()
        for f in ("lib/version.rb", "contrib/version.rb", "Gemfile", "Gemfile.lock"):
            r["size"]["files"][f] = {"code": 3, "complexity": 0}
        r["coupling"] = [{"entity": "lib/version.rb", "coupled": "contrib/version.rb", "degree": 64, "average-revs": 60},
                         {"entity": "Gemfile", "coupled": "Gemfile.lock", "degree": 90, "average-revs": 20},
                         {"entity": "static/index.html", "coupled": "static/apps-metadata.json", "degree": 90, "average-revs": 11}]
        coupling = _section_text(rendered(r, [], width=200), "Change coupling")
        self.assertIn("static/{index.html,apps-metadata.json}", coupling)
        self.assertNotIn("version.rb", coupling)
        self.assertIn("2 release pairs hidden", coupling)
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
        self.assertIn("Complex functions · 8 of 27, by complexity", fn, "the count of the rest is the title's")
        self.assertIn("26 functions hidden: 25 generated, 1 example", fn, "the largest class first")

    def test_hotspots_with_only_test_files_say_what_was_hidden(self):
        r = sample_report()
        r["revisions"] = [{"entity": "tests/test_a.py", "n-revs": 200}]
        r["size"]["files"] = {"tests/test_a.py": {"code": 50, "complexity": 1}}
        hot = _rendered_section(render.hotspots_section(r, full="markdown", width=200), width=200)
        self.assertIn("no source hotspots · 1 test file hidden", hot)

    def test_default_coupling_hides_pairs_of_deleted_files_and_says_so(self):
        r = sample_report()   # the tree holds static/index.html and static/apps-metadata.json only
        r["coupling"] = [{"entity": "static/index.html", "coupled": "static/apps-metadata.json", "degree": 90, "average-revs": 11},
                         {"entity": "static/tax.html", "coupled": "static/treasury.html", "degree": 85, "average-revs": 11}]
        coupling = _section_text(rendered(r, [], width=200), "Change coupling")
        self.assertIn("static/{index.html,apps-metadata.json}", coupling)
        self.assertNotIn("tax.html", coupling)
        self.assertIn("1 historical pair hidden", coupling)
        full = _section_text(rendered(r, [], width=200, full=True), "Change coupling")
        self.assertIn("static/{tax.html,treasury.html}", full)
        self.assertNotIn("hidden", full)

    def test_markdown_hotspots_hide_deleted_files_and_say_so(self):
        r = sample_report()   # the tree holds static/index.html and static/apps-metadata.json only
        r["revisions"].append({"entity": "src/sizes/old.go", "n-revs": 40})
        hot = _rendered_section(render.hotspots_section(r, full="markdown", width=200), width=200)
        self.assertNotIn("src/sizes/old.go", hot)
        self.assertIn("1 deleted file hidden", hot)
        full = _section_text(rendered(r, [], width=200, full=True), "◆ Hotspots")
        self.assertNotIn("hidden", full)

    def test_full_hotspots_count_the_removed_files_in_one_line_and_say_how_many_an_import_brought(self):
        # superpowers: 412 of 483 rows were files no longer tracked, three dashes each, 312 of them a removed import's
        r = sample_report()
        r["revisions"] += [{"entity": f"lib/node_modules/ws/f{i}.js", "n-revs": 1} for i in range(3)] + [{"entity": "src/sizes/old.go", "n-revs": 40}]
        r["imported"] = frozenset(f"lib/node_modules/ws/f{i}.js" for i in range(3))
        full = " ".join(_rendered_section(render.hotspots_section(r, full=True, width=200), width=200).split())
        self.assertNotIn("old.go", full)
        self.assertNotIn("node_modules/ws/f1.js", full)
        self.assertIn("static/index.html", full)
        self.assertIn("4 removed files not listed, 3 from left-out imports (maat-revisions.csv has them)", full)
        r["tree"] = frozenset({"src/sizes/old.go", "static/index.html"})   # tracked, but scc has no language for it: still a row
        self.assertIn("old.go", _rendered_section(render.hotspots_section(r, full=True, width=200), width=200))

    def test_hotspots_without_a_tree_listing_hide_nothing(self):
        r = sample_report()
        r["size"]["files"] = {}
        hot = _rendered_section(render.hotspots_section(r, full="markdown", width=200), width=200)
        self.assertIn("static/index.html", hot)
        self.assertNotIn("deleted", hot)
        r["revisions"].append({"entity": "src/sizes/old.go", "n-revs": 40})
        self.assertIn("old.go", _rendered_section(render.hotspots_section(r, full=True, width=200), width=200))

    def test_default_coupling_collapses_a_directory_that_changes_as_one(self):
        r = sample_report()
        files = [f"rich/_unicode_data/unicode{n}.py" for n in ("10", "11", "12", "13")]
        for f in files:
            r["size"]["files"][f] = {"code": 600, "complexity": 0}
        r["coupling"] = [{"entity": a, "coupled": b, "degree": 100, "average-revs": 5} for i, a in enumerate(files) for b in files[i + 1:]]
        r["coupling"].append({"entity": "static/index.html", "coupled": "static/apps-metadata.json", "degree": 90, "average-revs": 11})
        coupling = _section_text(rendered(r, [], width=200), "Change coupling")
        self.assertRegex(coupling, r"rich/_unicode_data/ \(4 files\) +≥100%", "a directory group has one form, with its weakest share")
        self.assertNotRegex(coupling, r"\(4 files\) +each other", "the caption says what a directory row is, not a cell on every such row")
        self.assertNotIn("unicode10", coupling)
        self.assertRegex(coupling, r"static/\{index.html,apps-metadata.json\} +90%")
        self.assertIn("Change coupling · all 2, by share of changes made together", coupling)
        self.assertIn("a directory row = its files change with each other (6 pairs)", coupling)
        full = _section_text(rendered(r, [], width=200, full=True), "Change coupling")
        self.assertIn("rich/_unicode_data/{unicode10.py,unicode11.py}", full)
        self.assertNotIn("(4 files)", full)

    def test_coupling_with_only_test_pairs_says_what_was_hidden(self):
        r = sample_report()
        r["coupling"] = [{"entity": "static/tax.html", "coupled": "tests/test_tax.py", "degree": 100, "average-revs": 11}]
        coupling = _section_text(rendered(r, [], width=200), "Change coupling")
        self.assertIn("Change coupling: no source pairs with 5 or more shared changes · 1 test pair hidden", coupling)

    def test_coupling_with_nothing_to_show_keeps_its_plain_note(self):
        r = sample_report()
        r["coupling"] = []
        coupling = _section_text(rendered(r, [], width=200), "Change coupling")
        self.assertIn("no pairs with 5 or more shared changes", coupling)
        self.assertNotIn("hidden", coupling)

    def test_complex_functions_with_only_test_files_say_what_was_hidden(self):
        r = sample_report()
        r["functions"] = [{"file": "tests/test_a.py", "function": "test_thing", "ccn": 40, "nloc": 50, "params": 0, "start": 1, "end": 50}]
        fn = _section_text(rendered(r, [], width=200), "Complex functions")
        self.assertIn("nothing at complexity 10 or more in source files (1 function measured) · 1 test function hidden", fn)

    def test_complex_functions_with_nothing_to_show_keep_their_plain_note(self):
        r = sample_report()
        r["functions"] = [{"file": "static/js/app.js", "function": "render", "ccn": 2, "nloc": 5, "params": 0, "start": 1, "end": 5}]
        fn = _section_text(rendered(r, [], width=200), "Complex functions")
        self.assertIn("nothing at complexity 10 or more (1 function measured)", fn)
        self.assertNotIn("hidden", fn)

    def test_header_shows_the_commit_when_the_run_recorded_one_and_the_run_line_closes_full_and_markdown(self):
        r = sample_report()
        r["meta"]["run"] = {"commit": "540ee5b560cc6e775e11317048a13cc7e355bf91", "gitmole": "0.10.0",
                            "tools": {"git": "2.55.0", "scc": "4.1.0", "jscpd": None, "lizard": "1.24.0"},
                            "options": {"ignore": ["*.min.js"], "ignore_data": True, "deep": False}}
        line = "gitmole 0.10.0 · git 2.55.0 · scc 4.1.0 · lizard 1.24.0 · --ignore *.min.js --ignore-data"
        self.assertEqual(render.run_line(r), line, "a tool with no version is left out")
        self.assertIn("@ 540ee5b5", rendered(r, []))
        self.assertIn(line, rendered(r, [], full=True))
        self.assertNotIn("gitmole 0.10.0", rendered(r, []), "the default report stays tight")
        md = render.markdown(r, [])
        self.assertIn("branch main @ 540ee5b5", md)
        self.assertIn(f"\n{line}  \n`--markdown --full` shows the hidden rows.  \nFull results in", md)
        self.assertIn(f"\n{line}  \nFull results in", render.markdown(r, [], full=True))
        r["meta"].pop("run")
        self.assertIsNone(render.run_line(r))
        self.assertNotIn("@ ", render.markdown(r, []).split("\n")[2], "an older output directory: the branch alone")


class HideTests(unittest.TestCase):
    """render._hide_tests: the rows dropped from the default tables and the count the caption's sum is built from."""

    def hide(self, paths, full=False):
        rows = [{"path": p} for p in paths]
        kept, hidden = render._hide_tests(rows, lambda r: r["path"], full)
        return [r["path"] for r in kept], hidden

    def test_full_hides_nothing(self):
        kept, hidden = self.hide(["app.py", "tests/test_app.py"], full=True)
        self.assertEqual(kept, ["app.py", "tests/test_app.py"])
        self.assertIsNone(hidden)

    def test_markdown_export_still_hides(self):
        kept, hidden = self.hide(["app.py", "tests/test_app.py"], full="markdown")
        self.assertEqual(kept, ["app.py"])
        self.assertEqual(hidden, (1, "test"))

    def test_nothing_hidden_has_no_note(self):
        kept, hidden = self.hide(["app.py", "util.py"])
        self.assertEqual(kept, ["app.py", "util.py"])
        self.assertIsNone(hidden)
        self.assertIsNone(render._hidden("file", "files", hidden, None))

    def test_a_pair_goes_when_either_side_is_a_test(self):
        pairs = [("app.py", "util.py"), ("app.py", "tests/test_app.py"), ("tests/test_util.py", "util.py")]
        kept, hidden = render._hide_tests(pairs, lambda p: p, False)
        self.assertEqual(kept, [("app.py", "util.py")])
        self.assertEqual(render._hidden("pair", "pairs", hidden), "2 test pairs hidden")

    def test_one_class_is_named_with_its_noun_in_the_singular_or_the_plural(self):
        self.assertEqual(render._hidden("file", "files", self.hide(["tests/test_a.py"])[1]), "1 test file hidden")
        self.assertEqual(render._hidden("file", "files", self.hide(["tests/test_a.py", "tests/test_b.py"])[1]), "2 test files hidden")
        self.assertEqual(render._hidden("area", "areas", (34, "historical")), "34 historical areas hidden")

    def test_several_classes_are_a_sum_with_its_breakdown_largest_first(self):
        """prometheus's coupling caption: five counts in five clauses, each ending "hidden", and no sum."""
        self.assertEqual(render._hidden("pair", "pairs", (289, "test"), (192, "historical"), None, (2, "example"), (10, "vendored"), (8, "generated")),
                         "501 pairs hidden: 289 test, 192 historical, 10 vendored, 8 generated, 2 example")
        self.assertEqual(render._hidden("function", "functions", (1, "vendored"), (1, "test")), "2 functions hidden: 1 test, 1 vendored", "a tie by name")
        self.assertEqual(render._hidden("pair", "pairs", (0, "test"), (3, "locale")), "3 locale pairs hidden", "a class of none is not a class")

    def test_the_count_is_every_hidden_row_not_only_the_visible_ones(self):
        kept, hidden = self.hide(["app.py"] + [f"tests/test_{i}.py" for i in range(12)])
        self.assertEqual(kept, ["app.py"])
        self.assertEqual(hidden, (12, "test"))   # hiding happens before any row cap

    def test_a_vendored_test_is_hidden_by_the_tests_rule(self):
        """Not a discriminating case: is_test_path already matches vendor/x_test.go by its _test.go
        suffix alone, so this passed before the classifier existed too. What it does verify: _hide_tests
        with no classifier and no report still builds one and hides a row whose first reason is vendored."""
        rows = [{"path": "vendor/x_test.go"}, {"path": "src/a.go"}]
        kept, hidden = render._hide_tests(rows, lambda r: r["path"], False)
        self.assertEqual([r["path"] for r in kept], ["src/a.go"],
                         "_hide_tests(classifier=None, no report) hides a row whose first reason is vendored")
        self.assertEqual(hidden, (1, "test"), "_hide_tests(classifier=None, no report) still counts it as a test file")


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

    def test_a_partial_projection_is_kept_in_the_envelope(self):
        """Whether the blame sample stopped early depends on how fast this machine blamed, like the seconds."""
        a = sample_report()
        a["meta"]["age"] = {"status": "skipped", "projected_seconds": 60.02, "projected_partial": True, "files": 10}
        out = json.loads(render.dumps_json(a, []))
        self.assertIs(out["envelope"]["projected_partial"], True)
        self.assertNotIn("projected_partial", out["meta"]["age"])

    def test_a_partial_run_says_so_even_with_rows(self):
        r = sample_report()
        for status, reason in (("timeout", "function metrics timed out"), ("failed", "function metrics failed (see run.log)")):
            r["meta"]["functions"] = {"status": status}
            sec = _titled(render.sections(r, full=True), "Complex functions")
            self.assertTrue(sec["rows"])
            self.assertEqual(sec["caption"], f"partial: {reason} · {render.COMPLEXITY_DEFINITION}", status)
        r["meta"]["functions"] = {"status": "timeout"}
        r["functions"] = [{"file": "a.py", "function": "simple", "ccn": 2, "nloc": 5, "params": 0, "start": 1, "end": 5}]
        self.assertIn("Complex functions: nothing at complexity 10 or more (1 function measured; partial: function metrics timed out)", rendered(r, []))

    def test_a_partial_run_keeps_the_count_of_the_rest(self):
        r = sample_report()
        r["meta"]["functions"] = {"status": "timeout"}
        r["functions"] = [{"file": f"f{i}.py", "function": f"fn{i}", "ccn": 20, "nloc": 30, "params": 0, "start": 1, "end": 30} for i in range(10)]
        sec = _titled(render.sections(r, full=False), "Complex functions")
        self.assertEqual(sec["title"], "Complex functions · 8 of 10, by complexity", "the rest are counted in the title")
        self.assertEqual(sec["caption"], "partial: function metrics timed out · " + render.COMPLEXITY_DEFINITION)

    def test_the_default_report_gives_one_line_when_no_function_is_both_long_and_complex(self):
        # superpowers: five rows topping at complexity 16 in 43 lines, none a brain method (15 or more over 100 lines or more)
        r = sample_report()
        r["functions"] = [{"file": "a.py", "function": "handle", "ccn": 16, "nloc": 43, "params": 2, "start": 1, "end": 43, "suspect": ""},
                          {"file": "a.py", "function": "swallowed", "ccn": 40, "nloc": 36, "params": 1, "start": 50, "end": 86, "suspect": "ran on"},
                          {"file": "b.py", "function": "long_only", "ccn": 11, "nloc": 300, "params": 0, "start": 1, "end": 300, "suspect": ""}]
        sec = _titled(render.sections(r, full=False), "Complex functions")
        self.assertEqual((sec["rows"], sec["caption"]), ([], None))
        self.assertEqual(sec["note"], "no long, complex functions; highest complexity 16 (handle); --full lists 3 at 10 or more")
        self.assertEqual(len(_titled(render.sections(r, full=True), "Complex functions")["rows"]), 3)
        self.assertTrue(_titled(render.sections(r, full="markdown"), "Complex functions")["rows"], "Markdown keeps the table")
        r["functions"].append({"file": "c.py", "function": "brain", "ccn": 15, "nloc": 100, "params": 0, "start": 1, "end": 100, "suspect": ""})
        sec = _titled(render.sections(r, full=False), "Complex functions")
        self.assertEqual(len(sec["rows"]), 4, "one function meets the rule: the table is back, every row of it")

    def test_a_list_longer_than_the_table_stays_a_table_without_a_brain_method(self):
        # gitmole's own: 166 functions at 10 or more, led by complexity 55 in 89 lines; the rows behind "and N more" are information
        r = sample_report()
        r["functions"] = [{"file": f"f{i}.py", "function": f"fn{i}", "ccn": 55 - i, "nloc": 89, "params": 0, "start": 1, "end": 89, "suspect": ""} for i in range(9)]
        sec = _titled(render.sections(r, full=False), "Complex functions")
        self.assertEqual((len(sec["rows"]), sec["title"], sec["caption"]), (8, "Complex functions · 8 of 9, by complexity", render.COMPLEXITY_DEFINITION))

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
        sec = _titled(render.sections(r, full=True), "Complex functions")
        self.assertEqual([(row[1], row[0]) for row in sec["rows"]], [("a.py", "c"), ("a.py", "c"), ("z.py", "b")])

    def test_a_long_function_name_does_not_squeeze_the_path_to_the_floor(self):
        r = sample_report()
        r["functions"] = [{"file": "src/main/java/com/example/service/impl/AccountServiceImpl.java",
                           "function": "shouldReturnTheAccountWhenTheIdentifierIsKnownAndActive",
                           "ccn": 27, "nloc": 180, "params": 4, "start": 10, "end": 200}]
        sec = render.fit(_titled(render.sections(r, full=False, width=100), "Complex functions"), 100)
        self.assertEqual(sec["rows"][0][1], "src/…/impl/AccountServiceImpl.java", "the directories survive; only the name would at the 16-char floor")

    def test_only_functions_over_the_floor(self):
        r = sample_report()
        r["functions"] = [{"file": "a.py", "function": "simple", "ccn": 9, "nloc": 300, "params": 0, "start": 1, "end": 300}]
        text = rendered(r, [])
        self.assertNotIn("simple", text)
        self.assertIn("Complex functions: nothing at complexity 10 or more (1 function measured)", text)
        r["functions"].append({"file": "a.py", "function": "twisty", "ccn": 10, "nloc": 20, "params": 0, "start": 1, "end": 20})
        text = rendered(r, [], full=True)
        self.assertRegex(text, r"twisty\s+a.py\s+10\s+20")
        self.assertNotIn("simple", text)
        self.assertNotIn("more", text, "the caption counts only functions over the floor")


class WatchList(unittest.TestCase):
    def test_leads_the_tables_with_its_numbers_in_columns(self):
        r = sample_report()
        r["authors"].append({"entity": "static/index.html", "n-authors": 1, "n-revs": 51})
        r["ownership"].append({"entity": "static/index.html", "author": "Ann", "added": 4000, "deleted": 0})
        text = rendered(r, [], width=120)
        self.assertIn("◎ Watch list · all 2, ranked by changes × lines of code", text)
        self.assertRegex(text, r"static/index.html\s+51\s+0\s+100%\s*\n")
        self.assertRegex(text, r"static/apps-metadata.json\s+128\s+4\s+-\s*\n", "no ownership row, so no share")
        self.assertNotIn("only Ann has touched it", text, "the reasons in words are --full's, under each row")
        self.assertIn("only Ann has touched it", rendered(r, [], width=120, full=True))
        self.assertEqual(render.to_json(r, [])["watch"][0]["reasons"], ["changed 51 times", "only Ann has touched it"])

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
        self.assertEqual(sec["caption"], "changes = commits since 2025-01-01 · fixes = in the 6 months to 2026-09-10 · top author = largest share of the lines added to the file")


class FullOnlySections(unittest.TestCase):
    def test_default_report_leaves_them_out_and_full_brings_them_back(self):
        text = rendered(sample_report(), [])
        for title in ("Size by language", "Activity", "Surviving code by year written"):
            self.assertNotIn(title, text, title)
        full = rendered(sample_report(), [], full=True)
        for title in ("Size by language", "Activity", "Surviving code by year written"):
            self.assertIn(title, full, title)

    def test_hotspots_moved_to_full_and_markdown_alongside_the_other_descriptive_tables(self):
        self.assertIn("hotspots", render.FULL_ONLY)
        text = rendered(sample_report(), [])
        self.assertNotIn("◆ Hotspots", text)
        full = rendered(sample_report(), [], full=True)
        self.assertIn("◆ Hotspots", full)
        self.assertIn("## Hotspots", render.markdown(sample_report(), []))

    def test_header_keeps_one_line_of_them(self):
        r = sample_report()
        r["activity"]["fix_commits"] = 58
        text = rendered(r, [])
        self.assertRegex(text, r"│ commits +25% are fixes +│")
        self.assertRegex(text, r"│ code +5,421 lines · HTML, Python · 76% surviving from 2025 +│")
        self.assertNotIn("most commits on", text, "the busiest weekday and hour are trivia for the header; --full's Activity table has them")
        self.assertIn("busiest hour 10:00", rendered(r, [], full=True))
        r["activity"] = {}
        r["cohorts"] = {}
        self.assertNotIn("are fixes", rendered(r, []))
        self.assertNotIn("│ commits", rendered(r, []), "a row with nothing to say is not there")

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

    def test_header_line_says_when_the_structure_step_did_not_run(self):
        # eight rules read structure.json and return nothing without it, so its absence has to show somewhere
        r = sample_report()
        for status, phrase in (("timeout", "structure checks timed out"), ("failed", "structure checks failed"),
                               ("planned", "structure checks did not complete")):   # planned: the run was interrupted before the step recorded itself
            r["meta"]["structure"] = {"status": status}
            self.assertIn(phrase, rendered(r, []), status)
            self.assertIn(phrase, render.markdown(r, []), status)
            self.assertLess(rendered(r, []).index(phrase), rendered(r, []).index("│ files"), "a missing step is said before the numbers that may miss it")
        r["meta"]["structure"] = {"status": "skipped", "install": "the grammars need Python 3.10 or newer; reinstall gitmole on 3.10+"}
        self.assertNotIn("structure checks", rendered(r, []), "a skip is the interpreter's, said at install time: the report must not differ by Python version")
        r["meta"]["structure"] = {"status": "run"}
        r["structure"] = {"status": "run"}
        self.assertNotIn("structure checks", rendered(r, []))
        r["structure"] = {"status": "not-installed"}
        self.assertNotIn("structure checks", rendered(r, []), "the child found no grammars: the same interpreter case, the same silence")
        r["structure"] = {}
        self.assertIn("structure checks failed", rendered(r, []), "meta says run but structure.json is unreadable: the rules found nothing, and the header says so")
        del r["meta"]["structure"]
        r.pop("structure", None)
        self.assertNotIn("structure checks", rendered(r, []), "an output directory written before the step existed says nothing")

    def test_header_line_is_in_markdown_too(self):
        self.assertIn("76% of surviving code from 2025", render.markdown(sample_report(), []))
        self.assertNotIn("most commits on", render.markdown(sample_report(), []))

    def test_header_line_names_the_core_steps_that_did_not_finish(self):
        r = sample_report()
        r["meta"]["steps"] = {"scc": "timeout", "osv-scanner": "failed", "change analysis": "skipped", "betterleaks": "run", "trend": "failed",
                              "git-sizer": "failed"}   # a retired step an old meta.json still names is not a core one
        text = rendered(r, [], width=160)
        self.assertRegex(text, r"│ steps +size timed out · change analysis skipped · dependency scan failed +│")
        self.assertNotIn("trend failed", text, "the optional steps say so in their own sections")
        self.assertNotIn("repo health", text)
        self.assertIn("size timed out · change analysis skipped", render.markdown(r, []))
        r["meta"]["steps"] = {"scc": "run"}
        self.assertNotIn("size", render.pulse(r)[0])

    def test_core_steps_are_still_step_names_the_planner_emits(self):
        # a step renamed in run.plan without a matching rename here would silently drop out of the
        # header's "did not finish" line instead of failing loudly, so this pins the two together.
        from gitmole import run
        self.assertLessEqual(set(render.CORE_STEPS), {s["name"] for s in run.plan("/r", "/o")},
                             "a renamed step would otherwise stop being named in the header")

    def test_full_header_and_markdown_carry_the_coverage_line(self):
        r = sample_report()
        r["meta"]["coverage"] = {"scored": 3900, "test file": 610, "generated": 120}
        line = "4,630 files: 3,900 scored · 120 generated · 610 test files"
        self.assertRegex(rendered(r, [], full=True), r"│ files +4,630 tracked · 35 with code · 3,900 scored · 120 generated · 610 test files +│")
        self.assertRegex(rendered(r, []), r"│ files +4,630 tracked · 35 with code · 3,900 scored \(source: not test, example, generated or vendored\) +│",
                         "the default header relates the three counts and leaves the buckets to --full")
        self.assertIn(line, render.markdown(r, []))
        r["meta"].pop("coverage")
        self.assertNotIn("files:", render.markdown(r, []).split("## Findings")[0], "an older output directory has no coverage record")


class KnowledgeMap(unittest.TestCase):
    def test_section_lists_areas_with_owners(self):
        text = rendered(sample_report(), [], full=True)
        self.assertIn("Knowledge map", text)
        self.assertRegex(text, r"static/\s+1,000\s+2\s+-\s+Ann\s+90%\s+Bob\s+10%")
        self.assertRegex(text, r"tests/\s+300\s+1\s+-\s+Bob\s+100%\s+-\s+-")

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
        self.assertIn("Knowledge map · all 1 area in the tree now, by lines added", km)
        self.assertIn("2 historical areas hidden", km)
        r["size"]["files"]["tests/t.py"] = {"code": 1, "complexity": 0}
        km = _section_text(rendered(r, [], width=200), "Knowledge map")
        self.assertIn("tests/", km, "a file back in the tree brings its area back")
        self.assertIn("1 historical area hidden", km)
        full = _section_text(rendered(r, [], width=200, full=True), "Knowledge map")
        self.assertIn("flask/", full)
        self.assertNotIn("hidden", full)

    def test_map_without_a_tree_listing_hides_nothing(self):
        r = sample_report()
        r["size"]["files"] = {}
        km = _section_text(rendered(r, [], width=200), "Knowledge map")
        self.assertIn("tests/", km)
        self.assertNotIn("historical", km)


    def test_the_heading_says_which_files_each_view_counts(self):
        # superpowers: tests/ 9,568 lines in the default map and 10,765 under --full, .opencode/ 13% and 59%
        r = sample_report()
        self.assertEqual(render.knowledge_section(r, full=False)["title"], "Knowledge map · all 1 area in the tree now, by lines added")
        self.assertEqual(render.knowledge_section(r, full="markdown")["title"], "Knowledge map · all 1 area in the tree now, by lines added")
        self.assertEqual(render.knowledge_section(r, full=True)["title"], "Knowledge map · all 2 areas over every file in the history, by lines added")
        self.assertEqual(render._base_title(render.knowledge_section(r, full=True)["title"]), "Knowledge map", "the symbol and the key column still find it")
        r["ownership"] += [{"entity": f"static/d{i}/x.html", "author": "Ann", "added": 9 - i, "deleted": 0} for i in range(8)]
        r["size"]["files"].update({f"static/d{i}/x.html": {"code": 3, "complexity": 0} for i in range(8)})
        self.assertRegex(render.knowledge_section(r, full=False)["title"], r"^Knowledge map · 6 of \d+ areas in the tree now, by lines added$", "the rows shown against the rows there are")
        r = sample_report()
        r["size"]["files"] = {}
        self.assertEqual(render.knowledge_section(r, full=False)["title"], "Knowledge map · all 2 areas over every file in the history, by lines added",
                         "with no listing of HEAD nothing is filtered")
        r["meta"]["since"] = "2026-01-01"
        self.assertEqual(render.knowledge_section(r, full=True)["title"], "Knowledge map · all 2 areas over every file in the history since 2026-01-01, by lines added")
        r["ownership"] = []
        self.assertEqual(render.knowledge_section(r, full=True)["title"], "Knowledge map", "an empty map counts nothing")

    def test_the_consistency_checks_still_read_the_map_and_the_people_table_as_drawn(self):
        """Four checks of the measurement harness read these tables as text. A drawing they cannot read finds nothing and says nothing."""
        from gitmole.measure import consistency
        r = sample_report()
        r["meta"].update({"last_date": "2026-09-10", "bots": []})
        r["activity"]["authors"] = {"Ann": {"commits": 1, "first": "2025-01-01", "last": "2026-09-01"}, "Bob": {"commits": 1, "first": "2025-01-01", "last": "2025-01-01"}}
        km = render.knowledge_section(r, full=False)
        self.assertEqual(km["rows"][0][2:6], ["Ann", "90%", "Bob gone", "10%"])
        self.assertEqual(consistency._owner_share(km, km["rows"][0], "main owner"), ("Ann", "90"))
        self.assertEqual(consistency._owner_share(km, km["rows"][0], "second"), ("Bob", "10"), "the name without the word gone, the share from the column beside it")
        self.assertIn("Bob", consistency._owner_names(km["rows"][0][4]))
        people = render.people_section(r, full=True)
        self.assertEqual(people["rows"][0][consistency._column(people, "surviving")], "79%")
        merged = {"meta": {"identities": [{"name": "Rya", "email": "r@x", "commits": 70, "merges": 60}, {"name": "Dee", "email": "d@x", "commits": 30}]}}
        self.assertEqual(consistency._MERGES_IN_ALL.search(render.people_section(merged)["caption"]).group(2), "60")

    def test_a_tied_top_share_is_shared_and_names_no_owner(self):
        # superpowers' .hermes-plugin/: one squash commit credited twelve people equally, and the map named the
        # first two by alphabet as main owner and second
        area = {"area": "plugin/", "lines": 96, "owners": [(n, 8) for n in "ABCDEFGHIJKL"]}
        self.assertEqual(render._owner_cells(area, set()), ["shared by 12", "8%", "-", "-"])
        area = {"area": "tools/", "lines": 431, "owners": [("Ann", 87), ("Bob", 86), ("Cat", 86), ("Dan", 86), ("Eve", 86)]}
        self.assertEqual(render._owner_cells(area, {"Ann"}), ["Ann gone", "20%", "shared by 4", "20%"], "a second place held equally is counted too")
        area = {"area": "core/", "lines": 100, "owners": [("Ann", 60), ("Bob", 30), ("Cat", 10)]}
        self.assertEqual(render._owner_cells(area, {"Bob"}), ["Ann", "60%", "Bob gone", "30%"], "gone follows the name after one space: no comma, no brackets")
        self.assertEqual(render._owner_cells({"area": "x/", "lines": 5, "owners": [("Ann", 5)]}, set()), ["Ann", "100%", "-", "-"])
        r = sample_report()
        r["ownership"] += [{"entity": "plugin/p.json", "author": who, "added": 8, "deleted": 0} for who in ("Zed", "Ann", "Bob")]
        row = next(x for x in render.knowledge_section(r, full=True)["rows"] if x[0] == "plugin/")
        self.assertEqual(row[4:8], ["shared by 3", "33%", "-", "-"])

    def test_the_tools_part_of_an_area_is_its_own_column_and_nobody_s_ownership(self):
        r = sample_report()   # load.py has already taken the tools' rows out of the ownership table
        r["tools"] = {"names": ["Model A"], "commits": 5, "added": {"static/a.html": 250, "tests/t.py": 1}, "surviving": 0}
        km = render.knowledge_section(r, full=False)
        self.assertEqual(km["columns"], ["area", "added", "main owner", "share", "second", "share", "agents"])
        self.assertEqual(km["rows"][0], ["static/", "1,000", "Ann", "90%", "Bob", "10%", "20%"], "250 of the 1,250 lines static/ was given")
        self.assertIn("agents = the lines trailers credit to coding tools", km["caption"])
        r["tools"]["added"] = {"static/a.html": 50}
        self.assertNotIn("agents", render.knowledge_section(r, full=False)["columns"],
                         "the default map shows them only where they hold as much as the second owner")
        self.assertEqual(render.knowledge_section(r, full=True)["columns"][-1], "agents")
        r["tools"]["added"] = {"static/a.html": 4}
        self.assertEqual(render.knowledge_section(r, full=False)["columns"], ["area", "added", "main owner", "share", "second", "share"],
                         "no column for less than a whole percent")
        self.assertEqual(render.knowledge_section(r, full=True)["columns"][-2:], ["second", "share"])

    def test_full_counts_an_areas_recent_authors_and_names_none(self):
        r = sample_report()
        before = render.knowledge_section(r, full=True)
        self.assertNotIn("recent", before["columns"], "rows from before 0.45 carry no count, and the map is the one it was")
        for row in r["ownership"]:
            if row["author"] == "Ann":
                row["recent"] = 2
        self.assertEqual([row[2] for row in render.knowledge_section(r, full=True)["rows"]], ["2", "1"],
                         "the meta, not the rows, says the count was made: authors stay a plain count")
        r["meta"]["ownership_recent"] = True
        r["ownership"].append({"entity": "static/b.css", "author": "Cat", "added": 1, "deleted": 0, "commits": 1, "recent": 1})
        km = render.knowledge_section(r, full=True)
        self.assertEqual(km["columns"], before["columns"], "a count in the authors cell, not a column: the owners keep their width")
        by = {row[0]: row for row in km["rows"]}
        self.assertEqual(by["static/"][2], "2/3", "Ann and Cat committed there in the window; Bob did not")
        self.assertIn(f"authors = recent/all, recent being a commit to the area in the 12 months to {r['meta']['last_date']}", km["caption"])
        self.assertNotIn("recent", render.knowledge_section(r, full=False)["caption"] or "", "the default map does not show it")

    def test_the_json_export_leaves_the_arrivals_out(self):
        # their one reader is the truck factor, whose evidence carries new_since; a re-render without them dates nothing
        r = sample_report()
        r["arrivals"] = [{"entity": "static/a.html", "first": "2026-01-01", "renamed": 0}]
        self.assertNotIn("arrivals", render.to_json(r, []))

    def test_an_owner_named_like_the_project_is_captioned_and_nothing_else_moves(self):
        # univer: "Univer" owns 55% of engine-render/ and the root package.json is named "univer"
        r = sample_report()
        plain = render.knowledge_section(r, full=False)
        self.assertNotIn("named like the project", plain["caption"] or "")
        r["meta"]["declared"] = {"name": "ann", "file": "package.json", "field": "name"}
        km = render.knowledge_section(r, full=False)
        self.assertIn('Ann is named like the project (package.json "name": "ann"); git does not record whether one person '
                      "or several commit under it", km["caption"])
        self.assertEqual(km["rows"], plain["rows"], "a caption, not a number")
        r["meta"]["declared"] = {"name": "demo", "file": "go.mod", "field": "module"}
        r["meta"]["identities"] = [{"name": "Demo", "email": "d@x.example", "commits": 1}]
        self.assertNotIn("named like the project", render.knowledge_section(r, full=False)["caption"] or "",
                         "an identity the map does not show as an owner is not captioned")
        self.assertEqual(render._declared_text({"name": "demo", "file": "go.mod", "field": "module"}), "go.mod module …/demo")
        self.assertEqual(render._declared_text({"name": "demo", "file": "Cargo.toml", "field": "name"}), 'Cargo.toml name = "demo"')


class Timeline(unittest.TestCase):
    def test_the_timeline_left_the_default_report(self):
        """No rule reads it, and its months changed with the terminal's width; People says who is still here."""
        self.assertIn("timeline", render.FULL_ONLY)
        for width in (80, 120, 200):
            self.assertNotIn("Timeline", rendered(sample_report(), [], width=width))
        self.assertIn("▦ Timeline", rendered(sample_report(), [], full=True))
        self.assertIn("## Timeline", render.markdown(sample_report(), []), "Markdown keeps the sections it had")

    def test_last_twelve_months_per_author_with_zero_as_0(self):
        text = rendered(sample_report(), [], width=120, full=True)
        self.assertIn("▦ Timeline · all 2, Oct 2025 → Sep 2026, by commits in those months", text)
        self.assertRegex(text, r"Ann\s+3(\s+0){9}\s+12\s+7")
        self.assertRegex(text, r"Bob(\s+0){11}\s+5")
        self.assertIn("Oct", text)
        self.assertNotIn("Old Timer", text, "authors with no commits in the window are left out")

    def test_the_month_of_the_last_commit_is_marked_when_it_is_not_whole_and_the_rows_are_identities_as_merged(self):
        """prometheus: Sep 2026 ends on the 18th beside eleven whole months, and George and György Krajcsovits are two rows."""
        sec = render.timeline_section(sample_report(), full=True)   # the last commit is 2026-09-10
        self.assertEqual(sec["columns"][-2:], ["Aug", "Sep*"])
        self.assertEqual(sec["caption"], "Sep* = to 2026-09-10, not a whole month · a row = an identity as merged: one person under two names the run did not join has two rows")
        r = sample_report()
        r["meta"]["last_date"] = "2026-09-30"
        sec = render.timeline_section(r, full=True)
        self.assertEqual(sec["columns"][-1], "Sep", "a whole month has no mark")
        self.assertTrue(sec["caption"].startswith("a row = an identity as merged"))
        r["meta"]["last_date"] = "2026-08-31"   # the log's last month is later than the recorded date: nothing to mark
        self.assertEqual(render.timeline_section(r, full=True)["columns"][-1], "Sep")

    def test_timeline_starts_at_the_window(self):
        r = sample_report()
        r["meta"]["since"] = "2026-07-15"
        sec = render.timeline_section(r, full=True)
        self.assertEqual(sec["title"], "Timeline · all 2, Jul 2026 → Sep 2026, by commits in those months")
        self.assertEqual(sec["columns"], ["author", "Jul", "Aug", "Sep*"])

    def test_timeline_starts_no_earlier_than_the_history(self):
        r = sample_report()
        r["activity"]["timeline"] = {"Ann": {"2026-09": 4}, "Bob": {"2026-08": 1}}
        sec = render.timeline_section(r, full=True)
        self.assertEqual(sec["title"], "Timeline · all 2, Aug 2026 → Sep 2026, by commits in those months", "ten days of history once drew Oct 2025 onwards, empty")
        self.assertNotIn("Oct", sec["columns"])
        r["activity"]["timeline"] = {"Ann": {"2026-09": 4}}
        self.assertEqual(render.timeline_section(r, full=True)["title"], "Timeline · all 1, Sep 2026, by commits in those months", "one month is not a range")

    def test_people_caption_says_what_is_windowed(self):
        r = sample_report()
        r["meta"]["since"] = "2026-07-15"
        text = rendered(r, [])
        self.assertIn("commits = since 2026-07-15 · share = of commits", text)
        r["meta"]["age"] = {"status": "run", "method": "blame"}
        self.assertIn("surviving = blame share at HEAD, over the whole tree", rendered(r, []))

    def test_a_person_with_no_commit_of_their_own_has_no_timeline_row(self):
        r = sample_report()
        r["activity"]["timeline"]["Tool"] = {"2026-09": 40}   # an older run counted trailer credits here
        r["activity"]["authors"] = {"Ann": {"commits": 22}, "Tool": {"commits": 40, "authored": 0}}
        text = rendered(r, [], width=120, full=True)
        self.assertNotRegex(_section_text(text, "▦ Timeline"), r"Tool\s+\d")
        self.assertRegex(_section_text(text, "▦ Timeline"), r"Ann\s+\d")

    def test_bots_are_left_out_of_the_timeline_and_named_under_people(self):
        r = sample_report()
        r["meta"]["bots"] = [{"name": "renovate[bot]", "commits": 940}, {"name": "github-actions[bot]", "commits": 195}]
        r["activity"]["timeline"]["renovate[bot]"] = {"2026-08": 30, "2026-09": 40}
        text = rendered(r, [], width=120)
        self.assertNotIn("renovate[bot]", text.split("◉ People")[0], "the panel and findings do not mention bots")
        full = rendered(r, [], width=120, full=True)
        self.assertRegex(full, r"Ann\s+3(\s+0){9}\s+12\s+7")
        self.assertNotIn("renovate[bot]", _section_text(full, "▦ Timeline"), "no timeline row for a bot")
        self.assertIn("2 bots left out: renovate[bot] 940, 1 more", text, "how many, and the busiest")
        self.assertIn("2 bots left out: renovate[bot] 940, github-actions[bot] 195", rendered(r, [], width=120, full=True), "--full names three")
        self.assertNotIn("bots left out", rendered(sample_report(), []))

    def test_a_bot_recognised_only_by_email_has_no_timeline_row_either(self):
        r = sample_report()
        r["meta"]["bots"] = [{"name": "GitHub", "commits": 12}]   # actions@github.com: a bot by its address, not its name
        r["activity"]["timeline"]["GitHub"] = {"2026-08": 30, "2026-09": 40}
        text = rendered(r, [], width=120, full=True)
        timeline = _section_text(text, "▦ Timeline")
        self.assertNotIn("GitHub", timeline)
        self.assertIn("Ann", timeline)

    def test_people_caption_names_who_had_aliases_merged(self):
        r = sample_report()
        r["meta"]["identities"][0]["aliases"] = [{"name": "ann-x", "email": "1@users.noreply.github.com", "commits": 3}]
        text = rendered(r, [])
        self.assertIn("◉ People · all 2 identities, by commits · 1 with aliases merged", text, "the count is the title's")
        self.assertNotIn(".mailmap", text, "whose, and the hint, are --full's")
        self.assertIn("aliases merged for Ann; a .mailmap makes that permanent", rendered(r, [], full=True))
        self.assertIn("aliases merged for Ann; a .mailmap makes that permanent", render.markdown(r, []))
        self.assertNotIn("aliases merged", rendered(sample_report(), []))

    def test_secrets_line_counts_distinct_values_and_the_placeholders_left_out(self):
        def row(value, file, commit, placeholder=False):
            return {"rule": "r", "file": file, "commit": commit, "line": 1, "fingerprint": f"{commit}:{file}", "value": value, "placeholder": placeholder}
        r = sample_report()
        r["secrets"] = [row("h1", "a.py", "c1"), row("h1", "a.py", "c2"), row("h2", "tests/b.py", "c1"), row("h3", "p.json", "c1", True)]
        self.assertIn("Secrets: 2 distinct values in 3 places, 1 never in source (secrets.json); 1 placeholder-shaped hit left out",
                      render.secrets_line(r), "the footer says how many of its values no finding holds (VoiceStudio: 4 in the footer, 2 in the finding)")
        r["unreachable"] = {"objects": 0}
        self.assertTrue(render.secrets_line(r).endswith("; no unreachable objects"), "the parenthetical pays for the count")
        r["secrets"] = [row("h1", "a.py", "c1"), dict(row("h4", "b.py", "c1"), declared={"file": ".gitleaksignore", "commit": "d", "how": "literal"})]
        self.assertEqual(render.secrets_line(r), "Secrets: 2 distinct values in 2 places; no unreachable objects",
                         "a declared value is in a finding too; with every value in one, there is nothing to add")
        del r["unreachable"]
        r["secrets"] = [row("h3", "p.json", "c1", True)]
        self.assertEqual(render.secrets_line(r), "Secrets: none found; 1 placeholder-shaped hit left out")
        self.assertEqual(render.secrets_line(sample_report()), "Secrets: none found")

    def test_timeline_absent_without_data(self):
        r = sample_report()
        r["activity"] = {}
        self.assertIn("Timeline: no timeline data", rendered(r, [], full=True))

    def test_the_twelve_months_are_the_table_at_every_width_and_the_ranking_is_on_their_total(self):
        """prometheus printed ten months at 80 columns and twelve at 160, and ranked on the months it showed: curl
        listed Xiaoke Wang and react Sebastian Markbåge at one width and not at another."""
        r = sample_report()
        r["activity"]["timeline"] = {"Stopped Last Autumn": {"2025-10": 40, "2025-11": 30},
                                     "Here All Year": {f"2026-{m:02d}": 2 for m in range(1, 10)}}
        seen = []
        for width in (60, 80, 120, 200, None):
            sec = render.timeline_section(r, full=True, width=width)
            self.assertEqual(len(sec["columns"]) - 1, 12, width)
            self.assertEqual(sec["title"], "Timeline · all 2, Oct 2025 → Sep 2026, by commits in those months", width)
            seen.append([row[0][:7] for row in sec["rows"]])   # at 60 columns the names are cut to make room for the months
        self.assertEqual(seen, [["Stopped", "Here Al"]] * 5, "70 commits in the twelve months against 18: the same rows in the same order at every width")

    def test_a_name_gives_way_to_the_months_and_is_never_folded(self):
        r = sample_report()
        name = "a" * 70   # longer than any room the twelve months leave at 80 columns
        r["activity"]["timeline"] = {name: {f"2025-{m:02d}": 3 for m in range(10, 13)} | {f"2026-{m:02d}": 3 for m in range(1, 10)}}
        text = rendered(r, [], width=80, full=True)
        section_text = _section_text(text, "▦ Timeline")
        sec = next(s for s in render.sections(r, full=True, width=80) if s["id"] == "timeline")
        self.assertEqual(len(sec["columns"]) - 1, 12)
        for month in ("Oct", "Jan", "Aug", "Sep*"):
            self.assertIn(month, section_text, f"the {month} column header is fully visible, not starved to nothing")
        self.assertNotIn(name, section_text, "the full 70-character name does not fit")
        self.assertIn("a" * 16 + "…", section_text, "the name gives way, cut with an ellipsis, rather than the months")
        rows = [line for line in section_text.splitlines() if line.lstrip().startswith("aaa")]
        self.assertEqual(len(rows), 1, "one row, not a name folded onto a second line")
        for line in section_text.splitlines():
            self.assertLessEqual(len(line.rstrip()), 80, "no line wider than the terminal")
        self.assertEqual(render.timeline_section(r, full=True)["rows"][0][0], name, "with no width (Markdown) nothing is cut")


class Layout(unittest.TestCase):
    def test_the_findings_title_carries_the_tally(self):
        f = [{"severity": "warning", "title": "Bus factor of one", "detail": "Ann wrote 79% of the code."},
             {"severity": "info", "title": "x", "detail": "y."}]
        text = rendered(sample_report(), f)
        self.assertIn("╭─ Findings · 1 warning ▲ · 1 note ● ─", text, "the tally is where the findings are, each word beside its mark")
        self.assertNotIn("1 warning, 1 note", text, "and not in the header")
        self.assertIn("╭─ Findings ─", rendered(sample_report(), []))
        self.assertIn("Nothing flagged.", rendered(sample_report(), []))
        self.assertEqual(render.tally_title([{"severity": "critical"}, {"severity": "critical"}, {"severity": "info"}]), "Findings · 2 critical ✖ · 1 note ●")

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
        self.assertRegex(text, r"\n\n◉ People · all 2 identities, by commits\n")
        full = rendered(sample_report(), [], width=80, full=True)
        self.assertRegex(full, r"\n\n◆ Hotspots \(score = changes × lines of code\)\n")
        self.assertNotIn("─────", text.split("◉ People")[1].split("\n")[0], "no rule across the width")

    def test_no_tables_sit_side_by_side_at_any_width(self):
        """Size by language sat beside People, and Activity beside Surviving code, from 100 columns: the order of the
        lines changed with the terminal, and every copied line held two tables."""
        for full in (False, True):
            orders = set()
            for width in (80, 120, 200, 300):
                text = rendered(sample_report(), [], width=width, full=full)
                heads = [line for line in text.splitlines() if line[:1] in set(render.SYMBOLS.values()) | {"•"}]
                for line in heads:
                    self.assertNotRegex(line[2:], r"[◎◉◆⟷λ⌂▤◔▦◷•] [A-Z]", "one section on a line")
                orders.add(tuple(render._base_title(line[2:]).split(":")[0] for line in heads))   # an empty section is its title, a colon and a note
            self.assertEqual(len(orders), 1, "one order of sections whatever the width")
        self.assertEqual(orders.pop(), ("Watch list", "Watch list by component", "Hotspots", "Complex functions", "Change coupling", "Size by language", "Knowledge map", "People",
                                        "Timeline", "Activity", "Surviving code by year written", "Changed lines", "Trailers", "Signing by year", "OSPS Baseline"))

    def test_one_order_of_sections_in_the_default_report_full_and_markdown(self):
        """prometheus's default ran code, people, people, people, code, code."""
        r = sample_report()
        default = [s["id"] for s in render.sections(r, full=False)]
        self.assertEqual(default, ["watch", "functions", "coupling", "knowledge", "people"], "what to read first, what is hard to change, what changes together; then the people")
        for full in (True, "markdown"):
            ids = [s["id"] for s in render.sections(r, full=full)]
            self.assertEqual([i for i in ids if i in default], default, "the same order with --full's own sections in their groups")
            self.assertLess(ids.index("people"), ids.index("timeline"))
            self.assertEqual(ids[:3], ["watch", "watch_by_component", "hotspots"])

    def test_share_columns_carry_inline_bars_in_full_only_tables(self):
        text = rendered(sample_report(), [], width=80)
        self.assertNotIn("▰", text, "no bars in the default report: People's said nothing its number did not")
        self.assertRegex(_section_text(text, "◉ People"), r"Ann\s+234\s+64%\s+79%")
        text = rendered(sample_report(), [], width=80, full=True)
        self.assertRegex(_section_text(text, "▤ Size by language"), r"HTML\s+28\s+4,783\s+88% ▰{8}")
        self.assertNotIn("▰", _section_text(text, "◉ People"))
        self.assertNotIn("▰", _section_text(text, "⌂ Knowledge map"), "two share columns, and no bar on either")

    def test_grades(self):
        self.assertEqual(render.cell_style("share", "64%"), "bold #ff5cc8")
        self.assertEqual(render.cell_style("share", "25%"), "#ff9ee0")
        self.assertIsNone(render.cell_style("share", "3%"))
        self.assertEqual(render.cell_style("together", "95%"), "bold #ff5cc8", "the coupling table's head, the JSON's degree")
        self.assertEqual(render.cell_style("fixes", "5"), "bold #ff5cc8")
        self.assertEqual(render.cell_style("fixes", "1,204"), "bold #ff5cc8", "a count with its separator is still a count")

    def test_default_columns_are_the_ones_you_read(self):
        secs = {render._base_title(x["title"]): x for x in render.sections(sample_report(), full=False)}
        self.assertNotIn("Size by language", secs)
        self.assertNotIn("Hotspots", secs, "hotspots is --full and Markdown only")
        self.assertEqual(secs["People"]["columns"], ["author", "commits", "share", "surviving"])
        hot = render.hotspots_section(sample_report(), full="markdown", width=None)
        self.assertEqual(hot["title"], "Hotspots")
        self.assertEqual(hot["columns"], ["file", "changes", "lines", "fixes", "authors", "trend"])
        self.assertEqual(secs["Change coupling"]["columns"], ["files", "together"])
        self.assertEqual(secs["Knowledge map"]["columns"], ["area", "added", "main owner", "share", "second", "share"], "the count is headed for what it counts, and a percentage has its own column")

    def test_full_restores_every_column_and_row(self):
        secs = {render._base_title(x["title"]): x for x in render.sections(sample_report(), full=True)}
        self.assertEqual(secs["Size by language"]["columns"], ["language", "files", "code", "share", "complexity"])
        self.assertEqual(secs["People"]["columns"], ["author", "commits", "share", "surviving"], "--full adds rows to People, never an address")
        self.assertEqual(secs["Hotspots"]["columns"], ["file", "changes", "lines", "complexity", "score", "fixes", "authors", "minors", "co-changes", "idle", "trend"])
        self.assertIn("avg changes", secs["Change coupling"]["columns"])

    def test_row_caps_and_the_more_line(self):
        # the 8-row default cap with "and N more" is pinned for Timeline instead
        # (test_full_lifts_the_timeline_cap): Hotspots has no default-report row cap of its own any
        # more, since it only ships under --full and Markdown. Under --full it shows every row.
        r = sample_report()
        r["revisions"] = [{"entity": f"f{i}.py", "n-revs": 100 - i} for i in range(12)]
        r["size"]["files"] = {f"f{i}.py": {"code": 10, "complexity": 0} for i in range(12)}
        full = {x["title"]: x for x in render.sections(r, full=True)}["Hotspots (score = changes × lines of code)"]
        self.assertEqual(len(full["rows"]), 12)
        self.assertIsNone(full["caption"])

    # test_long_paths_are_elided_not_folded removed: it pinned Hotspots eliding long paths at a
    # narrow width, which no longer happens in any shipped mode (Hotspots only ships under --full,
    # which restores every column and never elides, and Markdown, which never passes a width). The
    # same "elided, not folded" behaviour is already pinned for Complex functions, which stays in
    # the default report, by test_long_paths_are_elided_like_every_other_table above.

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

    def test_full_lists_every_timeline_row_and_markdown_caps_them(self):
        r = sample_report()
        r["activity"]["timeline"] = {f"Author {i:02d}": {"2026-09": 60 - i} for i in range(60)}
        full = _titled(render.sections(r, full=True), "Timeline")
        md = _titled(render.sections(r, full="markdown"), "Timeline")
        self.assertEqual((len(full["rows"]), full["title"]), (60, "Timeline · all 60, Sep 2026, by commits in those months"))
        self.assertEqual((len(md["rows"]), md["title"]), (50, "Timeline · 50 of 60, Sep 2026, by commits in those months"), "the count of the rest is the title's")

    def test_paths_fit_next_to_wide_numbers_at_narrow_widths(self):
        # re-pointed at Complex functions: Hotspots no longer elides paths in any shipped mode, so
        # this narrow-width edge case is pinned on a table that still elides in the default report.
        r = sample_report()
        long = "services/payments/adapters/stripe_webhook_handler_v2.py"
        r["functions"] = [{"file": long, "function": "handle", "ccn": 12345, "nloc": 1234567, "params": 9, "start": 1, "end": 2}]
        # 67 is the narrowest width where the 28-character file name fits beside these numbers
        for width in (67, 68, 84):
            fn = _section_text(rendered(r, [], width=width), "Complex functions")
            self.assertNotRegex(fn, r"\n\s*[a-z_0-9]+\.py\s*\n", f"folded tail at width {width}")
            self.assertNotRegex(fn, r"\.p\s*\n", f"file name cut at width {width}")

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


class AgentSurface(unittest.TestCase):
    AGENTS = {"instructions": [{"file": "AGENTS.md", "last": "2026-09-01", "commits_behind": 1},
                               {"file": ".claude/skills/fix/SKILL.md", "last": "2026-09-01", "commits_behind": 0, "kind": "skill"}],
              "hooks": [{"file": "hooks/hooks.json", "event": "SessionStart", "command": "./hooks/run-hook.cmd session-start",
                         "script": "hooks/run-hook.cmd", "runs": "hooks/session-start"}], "hooks_count": 1,
              "plugin_manifests": [".acme-plugin/marketplace.json", ".acme-plugin/plugin.json", ".other-plugin/plugin.yaml"], "plugin_manifests_count": 3,
              "skills": {"count": 3, "files": [".claude/skills/fix/SKILL.md", "skills/a/SKILL.md", "skills/b/SKILL.md"]}}

    def test_the_inventory_is_a_full_only_section_and_no_finding(self):
        r = sample_report()
        r["provenance"] = {**(r.get("provenance") or {}), "agents": self.AGENTS}
        self.assertNotIn("Agent surface", rendered(r, []), "the default report does not move")
        text = " ".join(rendered(r, [], width=200, full=True).split())
        self.assertIn("Agent surface", text)
        self.assertIn("instructions AGENTS.md last changed 2026-09-01, 1 commit before the last", text)
        self.assertIn("skills .claude/skills/ 1 with a name and a description: fix", text)
        self.assertIn("skills skills/ 2 with a name and a description: a, b", text)
        self.assertIn("hook hooks/hooks.json SessionStart: ./hooks/run-hook.cmd session-start → hooks/run-hook.cmd → hooks/session-start", text)
        self.assertIn("plugin manifest .acme-plugin/ marketplace.json, plugin.json", text)
        self.assertIn("1 instruction file, 3 skills, 1 hook command, 3 plugin manifests; read from the tree by path convention and shape, listed and not judged", text)
        self.assertIn("agent_surface", render.FULL_ONLY)
        from gitmole import findings
        self.assertEqual([f["rule"]["id"] for f in findings.evaluate(r)], [f["rule"]["id"] for f in findings.evaluate(sample_report())])

    def test_a_tree_that_declares_nothing_has_no_section(self):
        r = sample_report()
        self.assertNotIn("Agent surface", rendered(r, [], full=True))
        r["provenance"] = {**(r.get("provenance") or {}), "agents": {"instructions": [], "guardrails": [], "mcp": []}}   # a run from before the inventory
        self.assertNotIn("Agent surface", rendered(r, [], full=True))
        self.assertNotIn("Agent surface", render.markdown(r, [], full=True))


class Sections(unittest.TestCase):
    def test_sections_carry_title_columns_and_rows_in_report_order(self):
        secs = render.sections(sample_report(), full=True)
        titles = [x["title"] for x in secs]
        self.assertEqual(titles[:2], ["Watch list · all 2, ranked by changes × lines of code", "Watch list by component"])
        self.assertTrue(titles[2].startswith("Hotspots"))
        self.assertEqual(titles[3:9], ["Complex functions · all 2, by complexity", "Change coupling · all 1, by share of changes made together", "Size by language",
                                       "Knowledge map · all 2 areas over every file in the history, by lines added", "People · all 2 identities, by commits",
                                       "Timeline · all 2, Oct 2025 → Sep 2026, by commits in those months"])
        self.assertEqual(titles[-1], "OSPS Baseline")
        self.assertEqual([x["id"] for x in secs][:7], ["watch", "watch_by_component", "hotspots", "functions", "coupling", "size", "knowledge"])
        size = secs[5]
        self.assertEqual(size["columns"][:3], ["language", "files", "code"])
        self.assertEqual(size["rows"][0][0], "HTML")

    def test_empty_section_has_a_note_instead_of_rows(self):
        r = sample_report()
        r["coupling"] = []
        sec = _titled(render.sections(r, full=True), "Change coupling")
        self.assertEqual(sec["rows"], [])
        self.assertEqual(sec["note"], "no pairs with 5 or more shared changes")


class Markdown(unittest.TestCase):
    def test_markdown_has_header_findings_and_tables(self):
        f = [{"severity": "warning", "title": "Bus factor of one", "detail": "Ann wrote 79% of the code."}]
        md = render.markdown(sample_report(), f)
        self.assertTrue(md.startswith("# demo"))
        self.assertIn("363 commits", md)
        self.assertIn("## Findings", md)
        self.assertIn("**warning** Bus factor of one", md)
        note = render.markdown(sample_report(), [{"severity": "info", "title": "Sweeping commits", "detail": "2 commits."}])
        self.assertIn("**note** Sweeping commits", note, "the terminal's word, where the JSON says info (prometheus: **info** under a tally of 10 notes)")
        self.assertNotIn("**info**", note)
        self.assertIn('"severity": "info"', render.dumps_json(sample_report(), [{"severity": "info", "title": "Sweeping commits", "detail": "2 commits."}]))
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
        self.assertIn("_no pairs with 5 or more shared changes_", md)
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
        self.assertEqual(d["watch"][0]["file"], "static/index.html")   # 51 × 4000 beats 128 × 800
        self.assertIn("reasons", d["watch"][0])
        self.assertIn("trend", d["watch"][0])

    def test_the_nested_backtest_sub_report_is_left_out(self):
        r = sample_report()
        past = sample_report()
        past["meta"] = {"now": "2026-03-10"}
        r["backtest"] = past
        j = render.to_json(r, [])
        self.assertNotIn("backtest", j, "a second whole report inside the export helps nobody")
        self.assertIn("watch_backtest", j, "the numbers drawn from it stay")

    def test_the_listing_of_head_is_left_out(self):
        r = sample_report()
        r["tree"] = frozenset({"a.py", "bin/tool"})
        self.assertNotIn("tree", render.to_json(r, []), "every path in the clone is not a finding; the JSON is a cost lane")


class ChangeRisk(unittest.TestCase):
    RISK = {"files": [{"file": "core/parser.py", "score": 3.0, "reasons": ["changed 40 times", "fixed 5 times in 6 months"], "watched": True},
                      {"file": "core/util.py", "score": 0.6, "reasons": ["changed 30 times"], "watched": True},
                      {"file": "core/new.py", "score": 0, "reasons": ["not in the tree"], "watched": False}],
            "total": 3.6, "watched": 2, "max_score": 3.0}

    def test_section_has_a_bar_scaled_to_the_worst_file_in_the_repo(self):
        sec = render.risk_section(self.RISK, "main", full=False)
        self.assertEqual(sec["title"], "Change risk (3 files since main)")
        risk = dict(self.RISK, change={"reasons": ["touches 3 files across 2 directories, 1 commit", "adds 20 lines to 800 (2%), removes 4"]},
                    coupling_gaps=[{"file": "core/parser.py", "companion": "core/ast.py", "degree": 72}, {"file": "core/parser.py", "companion": "core/lexer.py", "degree": 55}])
        caption = render.risk_section(risk, "main", full=False)["caption"]
        self.assertIn("touches 3 files across 2 directories, 1 commit; adds 20 lines to 800 (2%), removes 4", caption)
        self.assertIn("not touched: core/ast.py, which moved in 72% of core/parser.py's changes, and core/lexer.py (55%)", caption)
        self.assertEqual(sec["columns"], ["file", "risk", "why"])
        self.assertEqual(sec["rows"][0], ["core/parser.py", "▰▰▰▰▰▰▰▰▰▰", "changed 40 times · fixed 5 times in 6 months"])
        self.assertEqual(sec["rows"][1][1], "▰▰")
        self.assertEqual(sec["rows"][2][1], "")
        self.assertEqual(sec["caption"], "total 3.6% of the repository's changes × lines of code; 2 of these files are on the watch list")

    def test_the_why_column_says_what_imports_the_file(self):
        risk = {"files": [{"file": "core/util.py", "score": 0.6, "reasons": ["changed 30 times"], "watched": True,
                           "dependents": {"direct": 2, "all": 5, "files": ["core/lexer.py", "core/parser.py"]}},
                          {"file": "core/new.py", "score": 0, "reasons": ["changed once"], "watched": False,
                           "dependents": {"direct": 1, "all": 1, "files": ["core/util.py"]}},
                          {"file": "main.py", "score": 0, "reasons": ["changed once"], "watched": False, "dependents": None}],
                "total": 0.6, "watched": 1, "max_score": 3.0}
        rows = render.risk_section(risk, "main", full=False)["rows"]
        self.assertEqual(rows[0][2], "changed 30 times · imported by 2 files, 5 counting what imports them")
        self.assertEqual(rows[1][2], "changed once · imported by core/util.py", "a file the list does not score can still be imported")
        self.assertEqual(rows[2][2], "changed once")

    def test_one_watched_file_reads_as_one_file(self):
        risk = {"files": [{"file": "core/parser.py", "score": 3.0, "reasons": ["changed 40 times"], "watched": True}],
                "total": 3.0, "watched": 1, "max_score": 3.0}
        sec = render.risk_section(risk, "main", full=False)
        self.assertEqual(sec["caption"], "total 3.0% of the repository's changes × lines of code; 1 of these files is on the watch list")

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


class Compare(unittest.TestCase):
    def test_compare_section_lists_the_buckets_and_the_watch_moves(self):
        result = {"new": [{"severity": "warning", "title": "Credential-shaped files tracked"}],
                  "resolved": [{"severity": "info", "title": "Reverts"}],
                  "persisting": [{"severity": "info", "title": "Bug magnets", "was": "warning"}, {"severity": "warning", "title": "Repo health", "was": "warning"}],
                  "watch_entered": ["c.py"], "watch_left": ["b.py"],
                  "tally": {"before": {"critical": 0, "warning": 2, "info": 2}, "after": {"critical": 0, "warning": 2, "info": 1}},
                  "before": {"commit": "540ee5b560cc6e775e11317048a13cc7e355bf91", "date": "2026-09-10", "options_differ": ["ignore_data"]}}
        sec = render.compare_section(result)
        self.assertEqual(sec["title"], "Since last report")
        self.assertEqual(sec["rows"], [["new", "warning · Credential-shaped files tracked"], ["resolved", "note · Reverts"],
                                       ["persisting", "warning → note · Bug magnets"], ["persisting", "warning · Repo health"],
                                       ["entered the watch list", "c.py"], ["left the watch list", "b.py"]],
                         "_section stringifies every row into a list, like every other section's rows")
        self.assertEqual(sec["caption"], "options differ: ignore_data; the changes partly reflect them\n"
                                         "against 540ee5b5, 2026-09-10 · 2 warnings, 2 notes → 2 warnings, 1 note")
        result["before"] = {"commit": None, "date": "2026-09-10", "options_differ": []}
        self.assertEqual(render.compare_section(result)["caption"], "against an export without a run manifest, 2026-09-10 · 2 warnings, 2 notes → 2 warnings, 1 note")
        result["persisting"] = [{"severity": "critical", "title": "1 secret(s) in history", "was": "critical", "changed": [["values", 16, 1], ["places", 40, 2]]},
                                {"severity": "warning", "title": "Duplicated code", "was": "warning",
                                 "changed": [["a", 1, 2], ["b", 1, 2], ["c", 1, 2], ["d", 1, 2], ["rate_pct", 6.4, 5.25]]}]
        self.assertEqual([r[1] for r in render.compare_section(result)["rows"] if r[0] == "persisting"],
                         ["critical · 1 secret(s) in history (values 16 → 1; places 40 → 2)",
                          "warning · Duplicated code (a 1 → 2; b 1 → 2; c 1 → 2; d 1 → 2; 1 more)"])
        empty = {**result, "new": [], "resolved": [], "persisting": [], "watch_entered": [], "watch_left": []}
        self.assertEqual(render.compare_section(empty)["note"],
                         "nothing changed; against an export without a run manifest, 2026-09-10 · 2 warnings, 2 notes → 2 warnings, 1 note",
                         "the empty case folds the caption's lines into the note, or the reader loses the against-commit and tally")
        r = sample_report()
        text = rendered(r, [], compare=result)
        self.assertIn("Since last report", text)
        self.assertIn("## Since last report", render.markdown(r, [], compare=result))
        self.assertEqual(render.to_json(r, [], compare=result)["compare"], result)


class Excerpt(unittest.TestCase):
    def _text(self, findings=()):
        console = Console(file=io.StringIO(), width=100, record=True, force_terminal=False, color_system=None)
        render.excerpt(sample_report(), list(findings), console)
        return console.export_text()

    def test_prints_header_and_watch_list(self):
        text = self._text()
        self.assertIn("demo", text)                     # header panel title
        self.assertIn("363 commits", text)
        self.assertIn("Watch list", text)
        self.assertIn("static/apps-metadata.json", text)   # both scored files fit under the excerpt's cap of 5

    def test_prints_nothing_else(self):
        text = self._text()
        for heading in ("Hotspots", "People", "Knowledge map", "Timeline", "Change coupling", "Repo health", "Full results", "No secrets"):
            self.assertNotIn(heading, text)
        self.assertEqual([line for line in text.splitlines() if "Findings" in line], ["Findings"], "the title alone, with the tally when there is one")

    def test_findings_are_tallied_in_their_title_not_listed(self):
        found = [{"severity": "warning", "title": "Bus factor of one", "detail": "Ann wrote 80% of the code",
                  "advice": "Pair someone with Ann."}]
        text = self._text(found)
        self.assertIn("Findings · 1 warning ▲\n", text)
        self.assertNotIn("Bus factor of one", text)


if __name__ == "__main__":
    unittest.main()


class ChangedLines(unittest.TestCase):
    def test_two_windows_and_the_cohorts_when_there_are_marked_commits(self):
        w = {"commits": 10, "added": 200, "moved": 20, "churned": 10, "moved_share": 0.1, "churn_share": 0.05}
        rep = {"provenance": {"lines": {"windows": [{"label": "last year", "from": "2025-01-01", "to": "2026-01-01", **w},
                                                    {"label": "the year before", "from": "2024-01-01", "to": "2025-01-01", **w, "added": 0, "moved_share": None, "churn_share": None}],
                                        "cohort": {"marked": {**w, "commits": 2}, "rest": w}, "churn_days": 14},
                               "cohort": {"cohort": {"commits": 2, "watch": 1}, "rest": {"commits": 8, "watch": 2}, "watch_top": 15, "share": 0.2}}}
        sec = render.lines_section(rep)
        self.assertEqual(sec["rows"][0], ["last year (2025-01-01 to 2026-01-01)", "10", "200", "10.0%", "5.0%"])
        self.assertEqual(sec["rows"][1][3:], ["-", "-"])
        self.assertEqual([r[0] for r in sec["rows"][2:]], ["declared commits, both years", "the rest, both years"])
        self.assertIn("lines", render.FULL_ONLY)
        self.assertIn("touched a file on the watch list's top 15 50% against 25%", render.trailers_section(rep)["caption"] or render.trailers_section(rep)["note"] or "")


class SmallRepository(unittest.TestCase):
    """superpowers: a 124-line report for four notes, a quarter of it rows that said little (count rules, never a repository's size)."""

    def people(self, *commits):
        r = sample_report()
        r["meta"]["identities"] = [{"name": f"P{n}", "email": f"p{n}@x.com", "commits": c} for n, c in enumerate(commits)]
        return r

    def test_people_rows_need_five_commits_and_the_rest_are_counted(self):
        sec = render.people_section(self.people(512, 86, 8, 3, 3, 2, 1, 1), full=False)
        self.assertEqual([row[0] for row in sec["rows"]], ["P0", "P1", "P2"])
        self.assertEqual(sec["title"], "People · 3 of 8 identities, by commits", "the rest are counted in the title")
        self.assertNotIn("more", sec["caption"])
        self.assertEqual(len(render.people_section(self.people(512, 86, 8, 3, 3, 2, 1, 1), full=True)["rows"]), 8)
        self.assertEqual(len(render.people_section(self.people(512, 86, 8, 3, 3, 2, 1, 1), full="markdown")["rows"]), 8)

    def test_the_top_three_people_stay_whatever_they_committed(self):
        sec = render.people_section(self.people(4, 2, 1, 1), full=False)
        self.assertEqual([row[0] for row in sec["rows"]], ["P0", "P1", "P2"])
        self.assertEqual(sec["title"], "People · 3 of 4 identities, by commits")
        sec = render.people_section(self.people(900, 800, 700, 600, 500, 400, 300), full=False)
        self.assertEqual(len(sec["rows"]), 6, "a large repository's rows are all over the floor: the cap decides, as before")
        self.assertEqual(sec["title"], "People · 6 of 7 identities, by commits")

    def test_the_timeline_lists_everyone_with_a_commit_in_its_months(self):
        """The default report's Timeline kept rows of five commits or more; the table is --full's now, which lists them all."""
        r = sample_report()
        r["activity"]["timeline"] = {"Ann": {"2026-08": 12, "2026-09": 7}, "Bob": {"2026-09": 5}, "Cy": {"2026-09": 4}, "Di": {"2026-07": 2, "2026-09": 2},
                                     "Ed": {"2026-09": 1}, "Old": {"2019-01": 400}}
        sec = render.timeline_section(r, full=True)
        self.assertEqual([row[0] for row in sec["rows"]], ["Ann", "Bob", "Cy", "Di", "Ed"], "ranked on the total of the months shown; Old has none in them")
        self.assertNotIn("more", sec["caption"])

    def coupled(self):
        r = sample_report()
        r["size"]["files"].update({"src/a.py": {"code": 500, "complexity": 9}, "src/b.py": {"code": 300, "complexity": 4}})
        r["revisions"] = [{"entity": "src/a.py", "n-revs": 40}, {"entity": "src/b.py", "n-revs": 30}]
        r["coupling"] = [{"entity": "src/a.py", "coupled": "src/b.py", "degree": 80, "average-revs": 12}]
        return r

    def test_one_coupled_pair_its_finding_already_names_is_no_table(self):
        from gitmole import findings
        r = self.coupled()
        found = findings.tight_coupling(r)
        text = rendered(r, found)
        self.assertIn("a.py and b.py in src/, 80%", " ".join(text.split()), "the finding gives the pair and its share")
        self.assertNotIn("Change coupling", text, "and points at no table, since none is printed")
        self.assertIn("Change coupling", rendered(r, found, full=True))
        self.assertIn("## Change coupling", render.markdown(r, found))
        r["coupling"][0]["degree"] = 60   # under the finding's 80%: the watch list's columns name no partner, so the table is the only place
        self.assertEqual(findings.tight_coupling(r), [])
        self.assertIn("⟷ Change coupling", rendered(r, []))

    def test_the_coupling_table_stays_when_it_says_more_than_the_watch_list(self):
        r = self.coupled()
        r["coupling"].append({"entity": "src/a.py", "coupled": "static/index.html", "degree": 60, "average-revs": 9})
        self.assertIn("Change coupling", rendered(r, []), "two pairs")
        r = self.coupled()
        r["coupling"].append({"entity": "src/a.py", "coupled": "src/gone.py", "degree": 60, "average-revs": 9})
        self.assertIn("1 historical pair hidden", rendered(r, []), "a hidden count that is said nowhere else")
        r = self.coupled()
        r["revisions"] = []   # nothing ranked, so the watch list has no row to show the pair on
        self.assertIn("Change coupling", rendered(r, []))
        r = sample_report()
        r["coupling"] = []
        self.assertIn("Change coupling: no pairs with 5 or more shared changes", rendered(r, []), "an empty table's note is kept: it says there is none")


class PeopleMerges(unittest.TestCase):
    def test_merges_are_counted_apart_and_left_out_of_the_share(self):
        rep = {"meta": {"identities": [{"name": "Rya", "email": "r@x", "commits": 70, "merges": 60},
                                       {"name": "Dee", "email": "d@x", "commits": 30}]}}
        sec = render.people_section(rep)
        self.assertEqual([c for c in sec["columns"]], ["author", "commits", "merges", "share", "surviving"])
        self.assertEqual(sec["rows"][0][:4], ["Dee", "30", "0", "75%"], "Dee wrote three quarters of the non-merge commits")
        self.assertEqual(sec["caption"], "share = of commits, without merges\n60 merges in all, in their own column", "the total is --full's and Markdown's")
        self.assertEqual(render.people_section(rep, full=False)["caption"], "share = of commits, without merges")
        plain = render.people_section({"meta": {"identities": [{"name": "Dee", "email": "d@x", "commits": 30}]}})
        self.assertNotIn("merges", plain["columns"])

    def test_co_author_credit_is_shown_apart_from_the_commits_they_authored(self):
        rep = {"meta": {"identities": [{"name": "Tool", "email": "t@x", "commits": 60, "authored": 0},
                                       {"name": "Dee", "email": "d@x", "commits": 45, "authored": 30}]}}
        sec = render.people_section(rep, full=False)
        self.assertEqual(sec["columns"], ["author", "commits", "co-authored", "share", "surviving"])
        self.assertEqual([r[:4] for r in sec["rows"]], [["Dee", "30", "15", "100%"], ["Tool", "0", "60", "0%"]],
                         "commits and share count the commits each authored; the credit is its own column")
        plain = render.people_section({"meta": {"identities": [{"name": "Dee", "email": "d@x", "commits": 30, "authored": 30}]}})
        self.assertNotIn("co-authored", plain["columns"])


    def test_a_count_of_a_thousand_or_more_has_its_separator_in_every_table_and_the_header(self):
        # prometheus: "18647 commits" and "1056 files" on the lines around "357,025 lines", and 1061 commits in People
        r = sample_report()
        r["meta"]["commits"] = 18647
        r["size"]["total_files"] = 1056
        r["meta"]["identities"] = [{"name": "Ann", "email": "ann@x.com", "commits": 1061}, {"name": "Bob", "email": "bob@x.com", "commits": 129}]
        r["meta"]["bots"] = [{"name": "dependabot[bot]", "commits": 2882}]
        self.assertEqual(render.people_section(r, full=False)["rows"][0][:2], ["Ann", "1,061"])
        self.assertIn("1 bot left out: dependabot[bot] 2,882", render.people_section(r, full=False)["caption"])
        for text in (rendered(r, [], width=80), rendered(r, [], full=True), render.markdown(r, [])):
            self.assertIn("18,647 commits", text)
            self.assertRegex(text, r"in 1,056 files|1,056 with code")
            self.assertNotIn("18647", text)
            self.assertNotIn("1061", text)
        self.assertEqual(render._number(0), "0", "zero prints as 0")
        self.assertEqual(render._number("2026"), "2026", "a year reaches a table as text and stays as it is")
        self.assertEqual(render.summary(r)["commits"], 18647, "the summary a JSON export carries keeps the number")

    def test_one_word_for_each_column_whatever_the_json_calls_it(self):
        # prometheus: "ccn" in Complex functions beside "complexity" in the Brain methods finding; "revs", "cplx" and "degree" under --full
        r = sample_report()
        r["functions"] = [{"file": f"f{i}.py", "function": f"fn{i}", "ccn": 55 - i, "nloc": 189, "params": 0, "start": 1, "end": 189, "suspect": ""} for i in range(9)]
        heads = {s["id"]: s["columns"] for s in render.sections(r, full=True)}
        self.assertEqual(heads["functions"], ["function", "file", "complexity", "lines", "params"])
        self.assertEqual(heads["coupling"], ["files", "together", "avg changes"])
        self.assertEqual(heads["hotspots"][:4], ["file", "changes", "lines", "complexity"])
        for name in ("ccn", "cplx", "revs", "avg revs", "degree", "revisions"):
            self.assertFalse([sid for sid, cols in heads.items() if name in cols], name)
        for title, key in render.KEY_METRIC.items():
            sec = next((s for s in render.sections(r, full=True) if s["title"].split(" (")[0] == title), None)
            if sec and sec["rows"]:
                self.assertIn(key, sec["columns"], f"{title}: the column read first is looked up by its printed head")
        fn = next(s for s in render.sections(r, full=False) if s["id"] == "functions")
        self.assertTrue(fn["caption"].endswith("complexity = cyclomatic: the function's branch points plus 1"), "the renamed head is defined once, under its table")
        watch = [w for w in render.dumps_json(r, []).splitlines() if '"revs"' in w or '"ccn"' in w or '"degree"' in w]
        self.assertTrue(watch, "the export keeps its keys: revs, ccn, degree")

    def test_no_rendering_of_the_people_table_has_an_address(self):
        # prometheus --full at 160 columns, and both Markdown exports, printed every address beside its commit count
        r = sample_report()
        for full in (False, True, "markdown"):
            self.assertNotIn("email", render.people_section(r, full=full)["columns"])
        surfaces = [rendered(r, [], width=w, full=f) for w in (80, 160, 300) for f in (False, True)] + [render.markdown(r, []), render.markdown(r, [], full=True)]
        for text in surfaces:
            self.assertNotIn("ann@x.com", text)
            self.assertNotIn("bob@x.com", text)
        self.assertIn("ann@x.com", render.dumps_json(r, []), "the export keeps the addresses")

    def test_coding_tools_are_left_out_of_the_rows_and_counted_in_the_caption(self):
        rep = {"meta": {"identities": [{"name": "Model A", "email": "noreply@v.example", "commits": 60, "authored": 0},
                                       {"name": "Model B", "email": "noreply@v.example", "commits": 6, "authored": 0},
                                       {"name": "Dee", "email": "d@x", "commits": 30, "authored": 30}]},
               "tools": {"names": ["Model A", "Model B"], "commits": 66, "added": {}, "surviving": 0}}
        sec = render.people_section(rep, full=False)
        self.assertEqual([r[0] for r in sec["rows"]], ["Dee"])
        self.assertNotIn("co-authored", sec["columns"])
        self.assertEqual(sec["title"], "People · all 1 identity, by commits")
        self.assertIn("1 = 3 identities less 2 coding-tool names (sharing 1 no-reply address, 66 commits)", sec["caption"],
                      "two spellings on one address are not two tools: the caption counts what git records, names and commits as the export's tools key has them, "
                      "and does the subtraction from the header's count of identities to the title's")
        self.assertIn("1 = 3 identities less 2 coding-tool names (sharing 1 no-reply address, 66 commits)", render.people_section(rep, full=True)["caption"], "the same words under --full")
        rep["meta"]["identities"][0]["aliases"] = [{"name": "Model A (1M)", "email": "noreply@v.example", "commits": 5},
                                                   {"name": "Model A", "email": "no-reply@w.example", "commits": 1}]
        self.assertIn("less 2 coding-tool names (3 with aliases, sharing 2 no-reply addresses, 66 commits)", render.people_section(rep, full=False)["caption"],
                      "a spelling merged into a row is a name too, counted beside the rows and not in their place (prometheus: 7 in the caption, 3 in the export)")
        rep = {"meta": {"identities": [{"name": "Tool", "email": "", "commits": 9, "authored": 0}, {"name": "Dee", "email": "d@x", "commits": 30, "authored": 30}]},
               "tools": {"names": ["Tool"], "commits": 9, "added": {}, "surviving": 0}}
        self.assertIn("1 = 2 identities less 1 coding-tool name (9 commits)", render.people_section(rep, full=False)["caption"])
        self.assertNotIn("no-reply", render.people_section(rep, full=False)["caption"], "no address is not a no-reply address")

    def test_rows_sharing_a_name_keep_their_own_surviving_code_and_no_row_goes_negative(self):
        rep = {"meta": {"identities": [{"name": "Dev", "email": "dev@home.example", "commits": 30, "authored": 30, "merges": 4},
                                       {"name": "Dev", "email": "7+dev@users.noreply.example", "commits": 1, "authored": 0, "merges": 4}]},
               "theseus_authors": {"Dev": 100}, "surviving_by_identity": {"Dev <dev@home.example>": 100}}
        sec = render.people_section(rep, full=True)
        home, noreply = sec["rows"]   # most commits first; the table has no address to tell them by (the two rows read "Dev")
        self.assertEqual([home[0], home[1], home[-1]], ["Dev", "26", "100%"])
        self.assertEqual(noreply[1], "0", "an old run's merges on a row that authored nothing never go below zero")
        self.assertEqual(noreply[-1], "0%", "the name's lines are the other row's")


class SummaryLine(unittest.TestCase):
    def _findings(self):
        mk = lambda rid, sev, title: {"severity": sev, "title": title, "detail": f"{title} detail", "advice": "act", "rule": {"id": rid}}   # noqa: E731
        return [mk("secrets_in_source", "critical", "1 secret(s) in history"), mk("bug_magnets", "warning", "Bug magnets")]

    def _text(self, panel):
        out = io.StringIO()
        Console(file=out, width=200, color_system=None).print(panel)
        return out.getvalue()

    def test_the_default_report_has_no_seldom_acted_on_line(self):
        """The rules it named were retired at 0.39.0 (findings.SUMMARISED is empty)."""
        text = self._text(render.findings_panel(self._findings(), {}, full=False))
        self.assertIn("Bug magnets detail", text)
        self.assertNotIn("seldom acted on", text)
        self.assertFalse(hasattr(render, "summary_line"))

    def test_every_finding_owns_one_mark_and_an_unmeasured_rule_s_carries_the_tag(self):
        """prometheus: the title said 5 warnings over four ▲, the fifth folded into a closing line with four notes."""
        unjudged = [{"severity": "warning", "title": "Deep nesting", "detail": "deep. Flatten it.", "advice": "Flatten it.",
                     "rule": {"id": "deep_nesting"}, "summary": True, "unjudged": True},
                    {"severity": "info", "title": "Debt in hotspots", "detail": "debt in two of them. Ticket it.", "advice": "Ticket it.",
                     "rule": {"id": "debt_in_hotspots"}, "summary": True, "unjudged": True}]
        found = self._findings() + unjudged
        text = self._text(render.findings_panel(found, {}, full=False))
        lines = [line.strip("│ ").rstrip() for line in text.splitlines()]
        self.assertNotIn("more from the structure step", text)
        self.assertNotIn("--full lists them", text)
        self.assertEqual(sum(line.startswith("▲ ") for line in lines), 2, "the title's 2 warnings are two marks")
        self.assertEqual(sum(line.startswith(("✖ ", "▲ ", "● ")) for line in lines), len(found))
        at = lines.index("▲ Deep nesting (not measured yet)")
        self.assertEqual(lines[at + 1:at + 3], ["deep", "↳ Flatten it."], "a warning is an entry like any other, with its step")
        self.assertIn("● Debt in hotspots (not measured yet): debt in two of them", lines, "a note is title, tag and statement, and no step")
        self.assertNotIn("Ticket it.", text)
        self.assertIn("Findings · 1 critical ✖ · 2 warnings ▲ · 1 note ● · 2 by rules not measured for precision yet", text.splitlines()[0])
        full = self._text(render.findings_panel(found, {}, full=True))
        self.assertIn("▲ Deep nesting (not measured yet)", full)
        self.assertIn("● Debt in hotspots (not measured yet)\n", full.replace(" │", "").replace("  \n", "\n").replace(" \n", "\n") + "\n" if False else "\n".join(x.strip("│ ").rstrip() for x in full.splitlines()) + "\n")
        self.assertIn("↳ Ticket it.", full, "--full keeps the step")
        self.assertIn("2 by rules not measured for precision yet", full.splitlines()[0])

    def test_the_title_glosses_the_tag_in_fewer_words_when_the_box_would_cut_it(self):
        mk = lambda sev, unjudged=False: {"severity": sev, "title": "T", "detail": "d", "rule": {"id": "r"}, **({"unjudged": True} if unjudged else {})}   # noqa: E731
        found = [mk("warning")] * 4 + [mk("info")] * 6 + [mk("info", True)] * 4 + [mk("warning", True)]
        self.assertEqual(render.tally_title(found), "Findings · 5 warnings ▲ · 10 notes ●", "the bare tally, as the README's excerpt prints it")
        self.assertEqual(render.tally_title(found, gloss=True), "Findings · 5 warnings ▲ · 10 notes ● · 5 by rules not measured for precision yet")
        self.assertEqual(render.tally_title(found, gloss=True, width=80), "Findings · 5 warnings ▲ · 10 notes ● · 5 not measured for precision yet")
        self.assertEqual(render.tally_title([mk("critical")] + found, gloss=True, width=80), "Findings · 1 critical ✖ · 5 warnings ▲ · 10 notes ● · 5 not measured yet")
        self.assertEqual(render.tally_title(found[:10], gloss=True, width=80), "Findings · 4 warnings ▲ · 6 notes ●", "nothing to gloss")
        for width in (60, 80, 100, 160):
            out = io.StringIO()
            Console(file=out, width=width, color_system=None).print(render.findings_panel([mk("critical")] + found, {}, full=False, width=width))
            self.assertNotIn("…", out.getvalue().splitlines()[0], width)


class Fit(unittest.TestCase):
    """At 80 columns no table splits a name, an identifier or a path across two lines: the columns are sized
    from their content, paths lose directories and long names their middle, and a table that cannot fit
    leaves its rightmost columns out and says so (debpalash/VoiceStudio's 0.39.0 report split "Palash
    Debnath", `tts_stream.p / y` and `branch main @ / eef0e230`)."""

    def people(self):
        r = sample_report()
        r["meta"]["identities"] = [{"name": "Palash Debnath", "email": "p@x.com", "commits": 3060, "authored": 3060 - 454, "merges": 913},
                                   {"name": "Paolo Antinori", "email": "q@x.com", "commits": 38, "merges": 4}]
        r["theseus_authors"] = {"Palash Debnath": 900, "Paolo Antinori": 10}
        return r

    def test_a_name_is_never_split_across_lines(self):
        text = _section_text(rendered(self.people(), [], width=80), "◉ People")
        self.assertIn("Palash Debnath", text)
        self.assertIn("Paolo Antinori", text)

    def test_a_path_is_elided_not_wrapped(self):
        r = sample_report()
        r["coupling"] = [{"entity": "backend/api/routers/openai_compat.py", "coupled": "backend/api/routers/tts_stream.py", "degree": 31, "average-revs": 9},
                         {"entity": "electron/src/renderer/src/features/settings/model-library.tsx", "coupled": "backend/api/schemas.py",
                          "degree": 30, "average-revs": 9}]
        r["size"]["files"].update({p: {"code": 10, "complexity": 0} for c in r["coupling"] for p in (c["entity"], c["coupled"])})
        text = _section_text(rendered(r, [], width=80), "⟷ Change coupling")
        self.assertIn("backend/api/routers/{openai_compat.py,tts_stream.py}", text, "two files of one directory print whole in one cell")
        self.assertIn("{electron/…/settings/model-library.tsx,backend/api/schemas.py}", text, "a path inside the braces loses its middle directories, the longer first")
        self.assertTrue(all(len(line) <= 80 for line in text.splitlines()))
        narrow = _section_text(rendered(r, [], width=54), "⟷ Change coupling")
        self.assertIn("…/routers/{openai_compat.py,tts_stream.py}", narrow, "the directory the two share goes before either name")
        self.assertIn("{…/model-library.tsx,…/api/schemas.py}", narrow)
        self.assertTrue(all(len(line.rstrip()) <= 54 for line in narrow.splitlines()))

    def test_a_long_area_keeps_its_name_and_the_owner_columns_give_way_first(self):
        # hindsight at 0.40.0: "hindsight-integrations/" (23 characters) printed as "…/" at 80 columns while the
        # owner columns kept their full width
        areas = ["hindsight-integrations/", "hindsight-api-slim/", "hindsight-cli/"]
        cols = [("area", render.PATH), ("lines added", render.RIGHT), ("main owner", {}), ("second", {})]
        rows = [(a, "311,910", "Nicolò Boschi (77%)", "Miguel de Benito Delgado (3%)") for a in areas]
        fitted = render.fit(render._section("Knowledge map", cols, rows), 80)
        self.assertEqual([r[0] for r in fitted["rows"]], areas)
        self.assertEqual(len(fitted["columns"]), 4, "nothing left out")
        self.assertLess(fitted["col_opts"][3]["width"], len("Miguel de Benito Delgado (3%)"))

    def test_an_area_too_long_for_any_width_is_cut_in_its_middle_and_keeps_its_slash(self):
        sec = render._section("Knowledge map", [("area", render.PATH)], [("hindsight-api-slim/",), ("docs/",)])
        fitted = render.fit(sec, 16)
        self.assertTrue(fitted["rows"][0][0].endswith("/"))
        self.assertIn("…", fitted["rows"][0][0])
        self.assertTrue(fitted["rows"][0][0].startswith("hind"))

    def test_a_cut_path_is_not_left_reading_as_another_file(self):
        real, reexport = "ui/src/components/issue-properties/IssueProperties.tsx", "ui/src/components/IssueProperties.tsx"
        cols = [("function", {"overflow": "fold"}), ("file", render.PATH), ("ccn", render.RIGHT)]
        rows = [("TruncatedCopyable", real, "861"), ("renderAVeryLongFunctionNameThatTakesRoom", "server/src/a/b/c/routes.ts", "40")]
        plain = render.fit(render._section("Complex functions", cols, rows), 82)
        self.assertEqual(plain["rows"][0][1], "ui/…/IssueProperties.tsx", "nothing else of that name is known")
        sec = dict(render._section("Complex functions", cols, rows), homes={"IssueProperties.tsx": [reexport, real]})
        told = render.fit(sec, 82)
        self.assertEqual([o["width"] for o in told["col_opts"]], [o["width"] for o in plain["col_opts"]], "no column gives up room for it")
        self.assertRegex(told["rows"][0][1], r"^…/issue-p[a-z-]*…/IssueProperties.tsx$", "the directory is cut, not the name")
        self.assertEqual(render.fit(sec, 100)["rows"][0][1], "ui/…/issue-properties/IssueProperties.tsx")
        both = render.fit(render._section("Complex functions", cols, [("a", real, "1"), ("b", "ui/src/pages/IssueProperties.tsx", "1"),
                                                                     ("c", reexport, "1"), rows[1]]), 82)
        shown = [r[1] for r in both["rows"][:3]]
        self.assertEqual(len(set(shown)), 3, f"rows of one table never shorten to the same text: {shown}")

    def test_sections_know_the_tracked_files_that_share_a_shown_name(self):
        r = sample_report()
        r["tree"] = frozenset({"lib/a/index.js", "lib/b/index.js", "README.md"})
        r["functions"].append({"file": "lib/a/index.js", "function": "f", "anonymous": False, "ccn": 30, "nloc": 9, "params": 1, "start": 1, "end": 9, "suspect": ""})
        secs = render.sections(r, full=False, width=80)
        self.assertEqual(sorted(secs[0]["homes"]["index.js"]), ["lib/a/index.js", "lib/b/index.js"])
        self.assertNotIn("README.md", secs[0]["homes"], "only names two tracked paths share")
        self.assertNotIn("homes", render.sections(r, full=False, width=None)[0], "Markdown shows whole paths")

    def test_a_table_that_fits_is_left_alone(self):
        sec = render._section("T", [("file", render.PATH), ("n", render.RIGHT)], [("a/b.py", 1)])
        self.assertIs(render.fit(sec, 80), sec)
        self.assertIs(render.fit(sec, None), sec, "Markdown fits nothing")

    def test_a_header_wraps_at_its_spaces_before_a_name_is_cut(self):
        sec = render._section("T", [("owner", {}), ("surviving code", render.RIGHT)], [("x" * 60, "63%")])
        fitted = render.fit(sec, 76)
        self.assertEqual(fitted["rows"][0][0], "x" * 60)
        self.assertLess(fitted["col_opts"][1]["width"], len("surviving code"))

    def test_full_hotspots_are_one_line_a_row_with_the_left_out_columns_named(self):
        r = sample_report()
        deep = "backend/services/deeply/nested/directory/model_manager.py"
        r["revisions"] = [{"entity": deep, "n-revs": 132}] + r["revisions"]
        r["size"]["files"][deep] = {"code": 2039, "complexity": 634}
        text = _rendered_section(render.hotspots_section(r, full=True, width=80), width=80)
        row = next(line for line in text.splitlines() if "model_manager.py" in line)
        self.assertRegex(row, r"…/(\w+/)?model_manager\.py")
        self.assertIn("132", row)
        self.assertRegex(" ".join(text.split()), r"trend left out at 80 columns; a wider terminal or --markdown shows them")
        self.assertTrue(all(len(line) <= 80 for line in text.splitlines()))

    def test_header_facts_are_not_split(self):
        r = sample_report()
        r["meta"]["run"] = {"commit": "eef0e230" + "0" * 32}
        r["meta"]["commits"] = 3470
        r["meta"]["identities"] = [{"name": f"p{i}", "email": f"{i}@x", "commits": 1} for i in range(87)]
        r["meta"]["branch"] = "main-with-a-longer-name"
        text = rendered(r, [], width=80)
        self.assertIn("╭─ demo · branch main-with-a-longer-name @ eef0e230 ─", text, "the title line: the repository, its branch and commit")
        r["meta"]["branch"] = "feature/" + "x" * 44
        text = rendered(r, [], width=80)
        self.assertIn("╭─ demo ─", text, "a title the border would cut gives the branch a row")
        self.assertRegex(text, r"│ branch +feature/x{44} @ eef0e230 +│")

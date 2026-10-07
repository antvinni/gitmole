"""`--full` is every section and every finding, not every row.

prometheus's --full was 4,359 lines at 80 columns: 84% of them the rows of four uncapped tables, People alone
1,337, with Complex functions led by generated parsers and the scans' results in the last 45 lines. Its tables
stop at fifty rows now and hide what the default hides, each finding is laid out with its subjects a line
each, the Supply chain section opens a group of its own with three sections no report had, and every row
is one `--section NAME` away."""
import io
import os
import re
import tempfile
import unittest

from rich.console import Console

from gitmole import render, section
from tests.test_layout import WIDTHS, drawn, found, rich_report
from tests.test_render import _headings, _section_text, sample_report


def full(width=80, report=None, findings=None) -> str:
    out = io.StringIO()
    render.report(report or rich_report(), found() if findings is None else findings, Console(file=out, width=width, force_terminal=False, color_system=None), full=True)
    return out.getvalue()


class Shape(unittest.TestCase):
    def test_the_header_closes_with_the_sections_in_their_order(self):
        text = full()
        head = " ".join(text.split("\n\n")[0].split())
        titles = ["Findings"] + _headings(text)
        self.assertTrue(head.endswith("contents " + ", ".join(titles)), head[-300:])
        self.assertNotIn("contents", drawn(80).split("\n\n")[0], "the default report has no contents row")

    def test_the_order_is_the_defaults_with_fulls_sections_in_their_groups(self):
        self.assertEqual(_headings(full()), [
            "Watch list", "Watch list by component", "Hotspots", "Complex functions", "Change coupling", "Size by language",   # the code
            "Knowledge map", "People", "Timeline",                                                                          # the people
            "Activity", "Surviving code by year", "Changed lines", "Trailers",                                              # the history
            "Supply chain", "Secrets by rule", "Dependencies by lock file", "Signing by year", "Checks run", "Agent surface", "OSPS Baseline"])
        default = [h for h in _headings(drawn(80, extras=False))]
        self.assertEqual([h for h in _headings(full()) if h in default], default, "the default's sections, in the default's order")
        self.assertEqual(default[-1], "Supply chain", "last in the default report, where it has no sections of its own to open")

    def test_every_finding_is_in_the_long_shape(self):
        mk = lambda title, detail, advice: {"severity": "warning", "title": title, "detail": f"{detail} {advice}", "advice": advice, "rule": {"id": "r"}}   # noqa: E731
        listed = mk("Brain methods", "9 functions are both long and complex: one (a.py) complexity 20; two (b.py) complexity 19; three (c.py) complexity 18; four (d.py) complexity 17; "
                    "five (e.py) complexity 16; six (f.py) complexity 15 and 3 more. They are measured by lizard.", "Split one first.")
        text = full(findings=[listed] + found())
        self.assertIn("▲ Brain methods\n  9 functions are both long and complex:\n    · one (a.py) complexity 20\n    · two (b.py) complexity 19\n    · three (c.py) complexity 18\n"
                      "    · four (d.py) complexity 17\n    · five (e.py) complexity 16\n    and 4 more\n  They are measured by lizard\n  ↳ Split one first.\n", text,
                      "the fact, five subjects a line each, the rest counted with the ones the statement had counted, what the statement adds, the step")
        block = text[text.index("\nFindings"):text.index("\nWatch list")]
        self.assertEqual(len([line for line in block.splitlines() if line and line[0] in "✖▲●"]), 5, "every finding, each with its own mark")
        self.assertIn("● Debt the authors flagged in hotspots (not measured yet)\n  8 of the top 10 hotspots carry TODO or FIXME comments; most in\n  static/index.html (10)\n  ↳ Ticket it.", text,
                      "a statement that is no list is whole, and a note from a rule not measured yet keeps its step")

    def test_a_subject_longer_than_the_line_wraps_under_itself(self):
        f = {"severity": "info", "title": "T", "detail": "2 pairs: " + "; ".join(f"services/gateway/internal/transport/middleware/authentication/a{n}.go and b{n}.go change together 9{n}% of the time" for n in (1, 2)) + ".",
             "advice": "", "rule": {"id": "r"}}
        made = render.brief.long(f, 74)
        self.assertEqual(made["statement"], ["2 pairs:"])
        self.assertEqual(made["subjects"][:2], ["services/gateway/internal/transport/middleware/authentication/a1.go", "  and b1.go change together 91% of the time"],
                         "the line it wraps to marked as its continuation, and no lone word on it")


class Capped(unittest.TestCase):
    def big(self) -> dict:
        r = rich_report()
        r["revisions"] = [{"entity": f"src/f{i:03d}.py", "n-revs": 400 - i} for i in range(70)] + [{"entity": f"tests/test_f{i:03d}.py", "n-revs": 900 - i} for i in range(30)]
        r["size"]["files"] = {**{f"src/f{i:03d}.py": {"code": 100, "complexity": 3} for i in range(70)}, **{f"tests/test_f{i:03d}.py": {"code": 100, "complexity": 3} for i in range(30)}}
        r["functions"] = [{"file": f"src/f{i:03d}.py", "function": f"fn{i}", "ccn": 200 - i, "nloc": 120, "params": 1, "start": 1, "end": 121, **({"suspect": "x"} if i % 20 == 0 else {})} for i in range(70)]
        r["meta"]["identities"] = [{"name": f"Person {i:03d}", "email": f"p{i}@x.org", "commits": c, "authored": a} for i, (c, a) in enumerate(
            [(1500, 1500), (120, 120), (15, 15)] + [(3, 3)] * 30 + [(1, 1)] * 40 + [(2, 0)] * 5)]
        return r

    def test_a_table_stops_at_fifty_rows_which_are_the_defaults_rows_first(self):
        r = self.big()
        secs = {s["id"]: s for s in render.sections(r, full=True)}
        default = {s["id"]: s for s in render.sections(r, full=False)}
        for sid in ("hotspots", "functions", "people"):
            self.assertEqual(len(secs[sid]["rows"]), render.TABLE_CAP, sid)
        self.assertEqual([row[0] for row in secs["functions"]["rows"][:8]], [row[0] for row in default["functions"]["rows"]], "the first rows are exactly the default's rows")
        shown = [row[0] for row in default["people"]["rows"]]   # three: under five commits a row is counted, not listed, in the default
        self.assertEqual([row[0] for row in secs["people"]["rows"][:len(shown)]], shown)
        self.assertFalse([row for row in secs["hotspots"]["rows"] if row[0].startswith("tests/")], "what the default hides stays hidden")
        self.assertIn("30 test files hidden", secs["hotspots"]["caption"], "and stays counted")

    def test_a_capped_title_says_fifty_of_n_and_names_its_section(self):
        secs = {s["id"]: s["title"] for s in render.sections(self.big(), full=True)}
        self.assertEqual(secs["hotspots"], "Hotspots · 50 of 70, by changes × lines of code · --section hotspots")
        self.assertEqual(secs["functions"], "Complex functions · 50 of 70, by complexity · --section complex-functions")
        self.assertEqual(secs["people"], "People · 50 of 78 identities, by commits · --section people")
        for sid, title in secs.items():
            if "--section" in title:
                self.assertEqual(section.canonical(title.rsplit("--section ", 1)[1]), section.name_of(sid), "the argument is one --section takes")
            else:
                self.assertNotRegex(title, r" \d+ of \d+", f"{sid}: a table the cap cut names where its rows are")
        self.assertNotIn("--section", "".join(s["title"] for s in render.sections(self.big(), full=False)), "the default report says it once, in its closing lines")
        self.assertNotIn("--section", "".join(s["title"] for s in render.sections(self.big(), full="markdown")))

    def test_a_data_quality_note_is_a_count_in_the_caption_not_a_row_below_the_cap(self):
        """prometheus: "? marks 13 spans lizard may have mis-parsed" sat under 663 rows; the spans sort last."""
        sec = next(s for s in render.sections(self.big(), full=True) if s["id"] == "functions")
        self.assertFalse([row for row in sec["rows"] if row[2].endswith("?")], "every mis-parsed span is past the cap")
        self.assertIn("? = a span lizard may have mis-parsed (4 of the table's, listed last)", sec["caption"])
        self.assertNotIn("mis-parsed", next(s for s in render.sections(self.big(), full=False) if s["id"] == "functions")["caption"], "the default's eight rows hold none, and say nothing")

    def test_people_ends_with_how_the_whole_table_is_spread_and_the_bands_sum_to_its_count(self):
        r = self.big()
        sec = next(s for s in render.sections(r, full=True) if s["id"] == "people")
        line = next(par for par in sec["caption"].split("\n") if " by commits: " in par)
        self.assertEqual(line, "78 by commits: 1 with 1,000 or more · 1 with 100 to 999 · 1 with 10 to 99 · 30 with 2 to 9 · 40 with 1 · 5 credited only as co-author")
        total = int(re.search(r"of ([\d,]+) identities", sec["title"]).group(1).replace(",", ""))
        bands = [int(n.replace(",", "")) for n in re.findall(r"(?:: | · )([\d,]+) (?:with|credited)", line)]
        self.assertEqual(sum(bands), total, "the bands are the renderer's own rows: they sum to the title's N")
        whole = render.whole_section(r, "people")
        commits = [int(row[1].replace(",", "")) for row in whole["rows"]]
        self.assertEqual(len(commits), total)
        self.assertEqual([sum(1 for c in commits if c >= 1000), sum(1 for c in commits if 100 <= c < 1000), sum(1 for c in commits if 10 <= c < 100),
                          sum(1 for c in commits if 2 <= c < 10), commits.count(1), commits.count(0)], bands, "counted again from the commits column of the whole table")
        self.assertNotIn("by commits:", next(s for s in render.sections(sample_report(), full=True) if s["id"] == "people")["caption"], "a table the cap does not cut needs no line for its tail")
        self.assertEqual(render.people_spread([(0, 0), (0, 3), (5, 0)]), "3 by commits: 1 with 2 to 9 · 1 credited only as co-author · 1 with merges only")

    def test_the_markdown_export_with_full_takes_the_same_cap(self):
        r = self.big()
        md = render.markdown(r, [], full=True)
        self.assertEqual(len(re.findall(r"(?m)^\| Person \d+ \|", md)), render.TABLE_CAP)
        self.assertIn("## People\n\n50 of 78 identities, by commits · `--section people --markdown` prints every row\n", md)
        self.assertIn("a table up to 50 rows · `--section NAME --markdown` prints one table whole", md)

    def test_the_markdown_export_without_full_keeps_the_sections_it_had(self):
        r = rich_report()
        heads = [line[3:] for line in render.markdown(r, found()).splitlines() if line.startswith("## ")]
        for title in ("Secrets by rule", "Dependencies by lock file", "Checks run"):
            self.assertFalse([h for h in heads if h.startswith(title)], title)
        self.assertTrue([h for h in heads if h.startswith("OSPS Baseline")] and [h for h in heads if h.startswith("Hotspots")])
        full_heads = [line[3:] for line in render.markdown(r, found(), full=True).splitlines() if line.startswith("## ")]
        for title in ("Secrets by rule", "Dependencies by lock file", "Checks run"):
            self.assertTrue([h for h in full_heads if h.startswith(title)], title)

    def test_the_timeline_is_twelve_months_ranked_on_their_total_at_every_width(self):
        r = rich_report()
        r["meta"].pop("since")
        r["activity"]["timeline"] = {"Ann": {"2025-10": 30}, "Bob": {"2026-09": 5, "2026-08": 4}, "Cy": {"2026-09": 31}}
        for width in (80, 100, 160):
            sec = next(s for s in render.sections(r, full=True, width=width) if s["id"] == "timeline")
            self.assertEqual(len(sec["columns"]) - 1, 12, width)
            self.assertEqual([row[0] for row in sec["rows"]], ["Cy", "Ann", "Bob"], "on the twelve-month total")
            self.assertEqual(sec["columns"][-1], "Sep*", "the month of the last commit is part of a month")
            self.assertIn("a row = an identity as merged", sec["caption"])


class SupplyChain(unittest.TestCase):
    def test_the_three_new_sections_are_fulls_and_the_closing_index_counts_them(self):
        r = rich_report()
        self.assertLessEqual(render.FULL_NEW, render.FULL_ONLY)
        titles = render.full_only_sections(r)
        for title in ("Secrets by rule", "Dependencies by lock file", "Checks run"):
            self.assertIn(title, titles)
            self.assertIn(title.lower().replace(" ", "-"), section.NAMES)
            self.assertNotIn(title, _headings(drawn(80)), "not a section of the default report")
        closing = " ".join(drawn(80).split())
        self.assertIn(f"--full adds {len(titles)} sections: ", closing)
        self.assertEqual(len(titles), 14)

    def test_secrets_by_rule_never_prints_a_value_or_a_line(self):
        r = rich_report()
        r["secrets"] += [{"rule": "generic-api-key", "file": "tests/fixtures/keys.py", "commit": "abc1234", "line": 9, "value": "SECRETVALUE1", "match": "key = SECRETVALUE1", "confidence": "low", "at_head": True},
                         {"rule": "generic-api-key", "file": "docs/old.md", "commit": "0001111", "line": 2, "value": "SECRETVALUE2", "confidence": "low", "at_head": False},
                         {"rule": "generic-api-key", "file": "a.py", "commit": "0002222", "line": 2, "value": "EXAMPLE", "placeholder": True, "confidence": "low", "at_head": True}]
        sec = render.secrets_by_rule_section(r)
        self.assertEqual(sec["columns"], ["rule", "confidence", "at HEAD", "history only", "first file"])
        self.assertEqual(sec["rows"], [["private-key", "high", "0", "1", "services/gateway/internal/transport/middleware/authentication/testdata/ca.key"],
                                       ["generic-api-key", "low", "2", "1", "tests/fixtures/keys.py"]], "the scanner's strongest grade first; a placeholder-shaped hit is no place")
        self.assertIn("1 placeholder-shaped hit left out", sec["caption"])
        for surface in (full(report=r), render.markdown(r, found(), full=True), section.csv_text(r, found(), "secrets-by-rule")):
            self.assertNotIn("SECRETVALUE", surface)
            self.assertNotIn("key = ", surface)
        r["secrets"] = []
        self.assertIsNone(render.secrets_by_rule_section(r), "a scan that found nothing has no table: the Supply chain row says so")

    def test_dependencies_are_in_the_findings_order_and_a_critical_score_is_listed_whatever_the_cap(self):
        r = rich_report()
        sec = render.dependencies_by_lock_file_section(r)
        self.assertEqual([row[0] for row in sec["rows"]], ["github.com/example/gateway", "websocket-driver"], "reach before score: the finding's own order")
        self.assertEqual(sec["under"][1], "0.7.4 · CVE-2026-54466 · fixed in 0.7.5 · a dev dependency")
        self.assertEqual(sec["wide"]["columns"], ["package", "lock file", "CVSS", "version", "advisory", "fixed in", "reach"], "Markdown and the CSV keep every column")
        r["dependencies"]["vulnerable"] = ([{"name": f"pkg{i:02d}", "version": "1.0.0", "source": "package-lock.json", "ids": [f"GHSA-{i}"], "score": 5.0, "fixed": "1.0.1", "imported": True} for i in range(55)]
                                           + [{"name": "last-and-critical", "version": "2.0.0", "source": "package-lock.json", "ids": ["GHSA-z"], "score": 9.0, "imported": False, "runtime": False}])
        capped = render.dependencies_by_lock_file_section(r)
        self.assertEqual(len(capped["rows"]), render.TABLE_CAP + 1)
        self.assertEqual(capped["rows"][-1][0], "last-and-critical", "a dev dependency with no fix sorts last, and scores 9.0")
        self.assertIn("Dependencies by lock file · 50 of 56 vulnerable", capped["title"])
        self.assertIn("1 more row past the cap for a CVSS of 9 or more", capped["caption"])
        self.assertEqual(len(render.whole_section(r, "dependencies_by_lock_file")["rows"]), 56)
        r["dependencies"]["vulnerable"] = []
        self.assertIsNone(render.dependencies_by_lock_file_section(r))

    def test_checks_run_tells_clean_from_nothing_to_check_from_did_not_run(self):
        r = rich_report()
        rows = {row[0]: (row[1], row[2]) for row in render.checks_run_section(r)["wide"]["rows"]}
        self.assertEqual(rows["workflow actions pinned to a commit"], ("clean", "65 uses of an action"))
        self.assertEqual(rows["submodule URLs"], ("nothing to check", ""))
        self.assertEqual(rows["dependency update tool"], ("clean", "renovate covers gomod and npm"))
        self.assertEqual(rows["licence"], ("clean", "Apache-2.0"))
        self.assertEqual(rows["declared files"], ("clean", "LICENSE, SECURITY.md, CODEOWNERS"))
        self.assertEqual(rows["registry confusion"], ("no hit", "not counted"), "a family with no count of what it looked at does not claim one")
        self.assertEqual(rows["dependency scan"], ("finding", "151 packages in 2 lock files, database 2026-09-16"))
        self.assertEqual(rows["unreachable objects"], ("nothing to check", "0 objects no ref reaches"))
        self.assertEqual(rows["imports resolved to a tracked file"], ("ran", "go 100%, tsx 92%"), "the rate behind four findings, per language")
        self.assertEqual(rows["step: trend"], ("timed out", ""))
        self.assertEqual(rows["step: code age"], ("did not run", "--deep runs it"))
        self.assertEqual(rows["step: scc"], ("ran", "35 files with code"))
        text = _section_text(full(report=r), "Checks run")
        self.assertNotRegex(text, r"\d+(\.\d+)?s\b", "no seconds: the same commit, the same table")
        r["hygiene"] = {}
        r["structure"] = {}
        r.pop("unreachable")
        rows = {row[0]: row[1] for row in render.checks_run_section(r)["wide"]["rows"]}
        self.assertEqual({rows[k] for k in ("licence", "symlinks", "imports resolved to a tracked file", "unreachable objects")}, {"did not run"}, "a check that never ran is not a pass")
        r["hygiene"] = {"actions": {"pinned": 3, "unpinned_count": 1, "unpinned": [{"file": ".github/workflows/ci.yml", "uses": "actions/checkout@v4", "line": 3}]}}
        self.assertEqual({row[0]: row[1] for row in render.checks_run_section(r)["wide"]["rows"]}["workflow actions pinned to a commit"], "finding")

    def test_an_osps_gap_that_rests_on_a_file_name_says_so(self):
        r = rich_report()
        r["meta"]["credential_files"] = ["web/.env"]
        rows = {row[0]: row for row in render.osps_section(r)["wide"]["rows"]}
        self.assertEqual(rows["OSPS-BR-07.01"][1:], ["gap", "No unencrypted secrets or credentials in version control", "Credential-shaped files tracked (matched by file name alone)"])
        self.assertNotIn("file name alone", rows["OSPS-GV-03.01"][3], "a gap a check stands behind says nothing of it")
        text = _section_text(full(report=r), "OSPS Baseline")
        self.assertIn("  OSPS-BR-07.01  gap\n    asks: No unencrypted secrets or credentials in version control\n    evidence: Credential-shaped files tracked (matched by file name alone)\n", text)


class NothingLost(unittest.TestCase):
    """prometheus at 80 columns: "No unencrypted secrets o…", "promql/engine.go · promql/functions.go · promql/promqltes…"."""

    def test_no_text_of_these_three_sections_is_cut_at_any_width(self):
        for width in WIDTHS:
            text = full(width)
            for title in ("Watch list by component", "Agent surface", "OSPS Baseline") + (("Checks run", "Dependencies by lock file") if width >= 80 else ()):   # 80 columns is the complete report
                self.assertNotIn("…", _section_text(text, title).replace("…/", ""), (width, title))   # a path may still lose its directories
        text = full(80)
        self.assertIn("  static/      35%\n    static/index.html · static/apps-metadata.json\n", text, "a component's files under its row, whole")
        self.assertIn("  hook             hooks/hooks.json\n    SessionStart: ./hooks/run-hook.cmd session-start → hooks/run-hook.cmd →\n    hooks/session-start\n", text)

    def test_markdown_keeps_them_as_columns(self):
        md = render.markdown(rich_report(), found(), full=True)
        self.assertIn("| control | result | asks | evidence |", md)
        self.assertIn("| kind | where | what |", md)
        self.assertIn("| component | share | top files |", md)
        self.assertIn("| check | result | checked |", md)


class Tidied(unittest.TestCase):
    def test_bars_are_one_family_scaled_to_the_columns_largest_value(self):
        self.assertEqual(render.bar_cells([80, 40, 10, 1, 0]), ["████████", "████", "█", "▏", ""], "the largest fills eight cells; anything above zero draws an eighth at least")
        self.assertEqual(render.bar_cells([64, 63, 33]), ["████████", "███████▉", "████▏"])
        self.assertIsNone(render.bar_cells([5, 5, 0]), "two lengths: no column")
        self.assertIsNone(render.bar_cells([0, 0]))
        text = full()
        self.assertRegex(_section_text(text, "Activity"), r"Thu +60 +26%  ████████\n")
        self.assertNotIn("▰", text.replace(_section_text(text, "Watch list"), ""), "no second glyph family")
        for mark in render.BAR_PARTS + render.BLOCK_MARK:
            self.assertIn(mark, render.ASCII_MARKS)

    def test_the_second_table_of_trailers_has_its_heads_then_its_rows(self):
        r = rich_report()
        r["provenance"]["cohort"] = {"definition": "an Assisted-by trailer", "share": 0.1, "cohort": {"commits": 35, "reverted": 2, "fixes": 4, "retouched": 20},
                                     "rest": {"commits": 328, "reverted": 3, "fixes": 60, "retouched": 150}}
        for width in WIDTHS:
            lines = _section_text(full(width, report=r), "Trailers").splitlines()
            at = next(i for i, line in enumerate(lines) if line.startswith("  declared commits against the rest"))
            self.assertRegex(lines[at + 1], r"^  commits +35 +328$", width)
            self.assertLessEqual(max(len(line) for line in lines[at:at + 5]), width)

    def test_a_caption_of_full_is_definitions_not_a_chain_of_semicolons(self):
        sec = render.lines_section(rich_report())
        self.assertEqual(sec["caption"], "code files only · moved = lines git's moved-code detection marks (--color-moved=blocks) · "
                                         "churned = deleted again within 2 weeks from the same file with the same text")
        self.assertEqual(len(sec["rows"]), 2, "the two windows are rows, as they were")


class Closing(unittest.TestCase):
    def test_full_closes_with_what_made_it_what_the_directory_holds_and_where_the_rows_are(self):
        r = rich_report()
        with tempfile.TemporaryDirectory() as out:
            for name in ("meta.json", "maat-revisions.csv", "packages.json", "tree.txt", "survival.png"):
                open(os.path.join(out, name), "w").close()
            os.mkdir(os.path.join(out, "backtest"))
            r["out_dir"] = out
            r["meta"]["run"] = {"gitmole": "0.44.0", "tools": {"git": "2.55.0", "scc": "4.1.0"}, "options": {"deep": True}}
            closing = full(report=r).split("\n\n")[-1].splitlines()
        self.assertEqual(closing[0], "7 of 18 steps ran; --deep runs 1 more (code age); --plots runs 3 more (code", "the steps, with the flag that gates each one not run")
        text = " ".join(closing)
        self.assertIn("1 plot drawn (survival.png)", text)
        self.assertIn("gitmole 0.44.0 · git 2.55.0 · scc 4.1.0 · --deep", text)
        self.assertIn("Output directory: backtest/, maat-revisions.csv, meta.json, packages.json*, survival.png, tree.txt* (* = no section renders it).", text)
        self.assertIn("--sarif PATH writes the findings for code scanning, --sbom PATH the locked packages, --json PATH every table.", text)
        self.assertEqual(closing[-2], "A table stops at 50 rows; --section NAME prints one whole.")
        self.assertEqual(closing[-1], f"Full results and plots in {out}")
        self.assertFalse([line for line in closing[:-1] if len(line) > 80], "wrapped to the terminal, all but the path")

    def test_the_defaults_index_keeps_to_four_lines_and_never_loses_its_last_words(self):
        titles = ["Watch list by component", "Hotspots", "Size by language", "Timeline", "Activity", "Surviving code by year", "Changed lines", "Trailers", "Secrets by rule",
                  "Dependencies by lock file", "Signing by year", "Checks run", "Agent surface", "OSPS Baseline (2 gaps, 1 not seen, of 10)"]
        lines = render.index_line(titles, 80, render.INDEX_LINES)
        self.assertEqual(lines, ["--full adds 14 sections: Watch list by component, Hotspots, Size by language,",
                                 "Timeline, Activity, Surviving code by year, Changed lines, Trailers, Secrets by",
                                 "rule, Dependencies by lock file, Signing by year, Checks run, Agent surface,",
                                 "OSPS Baseline (2 gaps, 1 not seen, of 10). --section NAME prints one whole."], "prometheus's fourteen, in the four lines the index has")
        self.assertEqual(render.index_line(titles[:3], 80, 4), ["--full adds 3 sections: Watch list by component, Hotspots, Size by language.", "--section NAME prints one whole."])
        longer = titles[:-1] + ["A section with a long title of its own", "OSPS Baseline (2 gaps, 1 not seen, 1 unrecognised, 1 not checked, of 10)"]
        cut = render.index_line(longer, 80, 4)
        self.assertEqual(len(cut), 4)
        self.assertTrue(cut[-1].endswith("more. --section NAME prints one whole."), cut)
        self.assertTrue(cut[0].startswith("--full adds 15 sections: "), "the count is of every section, named or not")
        self.assertEqual(" ".join(render.index_line([], 80, 4)), "--full prints every finding whole and more of every table. --section NAME prints one whole.")

    def test_help_says_what_full_is(self):
        from gitmole import cli
        text = cli.build_parser().format_help()
        self.assertIn("--full                every section and finding; --section NAME for each row", text)
        self.assertNotIn("row and column", text)


if __name__ == "__main__":
    unittest.main()

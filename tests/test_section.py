"""`--section NAME` prints one section whole, as a table, as Markdown or as CSV.

prometheus's Hotspots and People tables existed only in --full's 4,359 lines and in a 27 MB JSON export, and
its 55 companion pairs in no rendering at all. A section on its own holds every row, the default's first and
then the kinds the default hides, each named; the CSV holds every field the export has for a row and never
an address; and none of it writes a file."""
import csv
import io
import json
import os
import tempfile
import unittest
from unittest import mock

from rich.console import Console

from gitmole import cli, render, section
from tests.test_layout import SGR, WIDTHS, found, rich_report
from tests.test_render import sample_report


def whole_report() -> dict:
    """rich_report with rows of every kind a table hides, a companion pair, and a person whose name is an address."""
    r = rich_report()
    r["size"]["files"]["tests/test_app.py"] = {"code": 900, "complexity": 40}
    r["revisions"] += [{"entity": "tests/test_app.py", "n-revs": 300}, {"entity": "old/gone.py", "n-revs": 77}]
    r["functions"] += [{"file": "tests/test_app.py", "function": "test_everything", "ccn": 90, "nloc": 400, "params": 0, "start": 1, "end": 401}]
    r["coupling"] += [{"entity": "static/index.html", "coupled": "tests/test_app.py", "degree": 99, "average-revs": 30}]
    r["companions"] = [{"entity": "static/a.html", "companion": "static/b.html", "confidence": 90, "shared": 12},
                       {"entity": "tests/test_app.py", "companion": "static/index.html", "confidence": 95, "shared": 20}]
    r["tests"] = [{"entity": "static/index.html", "n-sets": 40, "with-tests": 30}]
    r["latenight"] = [{"entity": "static/index.html", "n-revs": 51, "late": 6}]
    r["entropy"] = [{"entity": "static/index.html", "periods": 9, "hcm": 0.25}]
    r["meta"]["identities"] += [{"name": "dev@example.com", "email": "dev@example.com", "commits": 3, "aliases": [{"name": "Dev", "email": "dev@old.example.com", "commits": 1}]}]
    r["activity"]["authors"] = {"Bob": {"commits": 129, "authored": 129, "added": 4000, "deleted": 100, "first": "2025-08-20", "last": "2026-09-10"}}
    return r


def shown(names, width=80, report=None, colour=False) -> str:
    c = Console(file=io.StringIO(), width=width, force_terminal=colour, color_system="truecolor" if colour else None)
    section.show(report or whole_report(), found(), c, [section.canonical(n) for n in names])
    return c.file.getvalue()


def rows_of(name, report=None) -> tuple:
    heads, *rows = list(csv.reader(io.StringIO(section.csv_text(report or whole_report(), found(), section.canonical(name)))))
    return heads, rows


class Names(unittest.TestCase):
    def test_every_section_the_renderer_builds_has_a_name(self):
        self.assertEqual(sorted(sid for sid in section.NAMES.values() if sid != section.FINDINGS), sorted(render.section_ids()))
        self.assertEqual(len(set(section.NAMES.values())), len(section.NAMES), "one name a section")

    def test_a_name_is_the_title_in_lower_case(self):
        report = whole_report()
        for name, sid in section.NAMES.items():
            if sid in (section.FINDINGS, "documents"):
                continue
            sec = render.whole_section(report, sid)
            self.assertEqual(render._base_title(sec["title"]).lower().replace(" ", "-"), name)

    def test_case_spaces_and_hyphens_do_not_matter(self):
        for given in ("complex-functions", "Complex functions", "COMPLEX_FUNCTIONS", " complex   functions "):
            self.assertEqual(section.canonical(given), "complex-functions")
        self.assertEqual(section.canonical("watch"), "watch-list", "the short name of the list")
        self.assertIsNone(section.canonical("functions"), "an id is not a name")
        self.assertIsNone(section.canonical(""))

    def test_help_lists_the_names(self):
        text = cli.build_parser().format_help()
        self.assertIn("section names, for --section NAME:", text)
        listed = text.split("section names, for --section NAME:")[1].split("\n\n")[0].replace("\n", " ")
        self.assertEqual([n.strip() for n in listed.split(",")], list(section.NAMES))


class OneSection(unittest.TestCase):
    def test_it_is_that_section_and_nothing_else(self):
        text = shown(["people"])
        self.assertTrue(text.startswith("◉ People · all 3 identities, by commits"), text[:60])
        for other in ("demo · branch", "Findings", "Supply chain", "Watch list", "--full", "/tmp/analysis-demo"):
            self.assertNotIn(other, text)

    def test_several_come_in_the_order_asked_one_blank_line_apart(self):
        text = shown(["activity", "people"])
        self.assertLess(text.index("◔ Activity"), text.index("◉ People"))
        self.assertEqual(text.count("\n\n"), 1)

    def test_every_row_the_default_s_first_then_the_kinds_it_hides(self):
        report = whole_report()
        default = render.functions_section(report, full=False)["rows"]
        sec = render.whole_section(report, "functions")
        self.assertEqual(sec["columns"], ["function", "file", "kind", "complexity", "lines", "params"])
        self.assertEqual([(r[0], r[1]) for r in sec["rows"][:len(default)]], [(r[0], r[1]) for r in default], "the first rows are the default's rows")
        self.assertEqual({r[2] for r in sec["rows"][:len(default)]}, {"source"})
        self.assertEqual(tuple(sec["rows"][-1][:4]), ("test_everything", "tests/test_app.py", "test", "90"), "the most complex of all, and last: the default hides it")
        self.assertIn("all 5", sec["title"])
        self.assertNotIn("hidden", sec["caption"] or "", "nothing is")

    def test_hotspots_name_a_removed_file_and_a_test(self):
        heads, rows = rows_of("hotspots")
        kinds = {r[0]: r[heads.index("kind")] for r in rows}
        self.assertEqual(kinds["old/gone.py"], "removed")
        self.assertEqual(kinds["tests/test_app.py"], "test")
        self.assertEqual(kinds["static/index.html"], "source")
        self.assertLess([r[0] for r in rows].index("static/index.html"), [r[0] for r in rows].index("tests/test_app.py"), "a test after the default's rows, whatever its score")
        self.assertEqual(len(rows), len(whole_report()["revisions"]), "every file the history changed")

    def test_the_hotspots_csv_holds_every_per_file_number_of_the_export(self):
        heads, rows = rows_of("hotspots")
        row = dict(zip(heads, next(r for r in rows if r[0] == "static/index.html")))
        self.assertEqual(heads[:6], ["file", "kind", "n-revs", "code", "complexity", "score"])
        self.assertEqual((row["n-sets"], row["with-tests"], row["late"], row["periods"], row["hcm"], row["age-months"]), ("40", "30", "6", "9", "0.25", "0"),
                         "test co-change, late-night changes and entropy: in no table of any report")
        self.assertEqual(row["score"], str(51 * 4000), "a number is a number: no thousands separator")

    def test_coupling_lists_every_pair_with_the_kind_it_is_hidden_under(self):
        heads, rows = rows_of("change coupling")
        self.assertEqual(heads, ["entity", "coupled", "kind", "degree", "average-revs"])
        kinds = [r[2] for r in rows]
        self.assertEqual(kinds, sorted(kinds, key=lambda k: k != "source"), "the pairs the default shows, then the ones it hides")
        hidden = rows[kinds.count("source"):]
        self.assertEqual(hidden[0], ["static/index.html", "tests/test_app.py", "test", "99", "30"], "the highest degree of all, and after every pair the default shows")
        self.assertEqual([int(r[3]) for r in hidden], sorted((int(r[3]) for r in hidden), reverse=True), "and those in the table's ranking too")
        self.assertIn(["static/tax.html", "static/treasury.html", "removed", "85", "11"], hidden, "neither file is in the tree")

    def test_companions_is_a_section_though_no_report_prints_one(self):
        self.assertNotIn("Companions", "".join(sec["title"] for sec in render.sections(whole_report(), full=True)))
        text = shown(["companions"], width=120)
        self.assertIn("Companions · all 2, by share of the file's changes its companion moved in", text)
        heads, rows = rows_of("companions")
        self.assertEqual(heads, ["entity", "companion", "kind", "confidence", "shared"])
        self.assertEqual(rows, [["static/a.html", "static/b.html", "source", "90", "12"], ["tests/test_app.py", "static/index.html", "test", "95", "20"]])

    def test_watch_prints_the_reasons_the_default_dropped(self):
        text = shown(["watch"])
        self.assertTrue(text.startswith("◎ Watch list · all "))
        row = next(i for i, line in enumerate(text.splitlines()) if "token_validator.go" in line)
        self.assertEqual(text.splitlines()[row + 1], "    Björn Rabenstein wrote 100% of it", "under the row, as --full prints them")
        heads, rows = rows_of("watch")
        self.assertEqual(heads[0], "file")
        self.assertIn("changed 51 times", rows[[r[0] for r in rows].index("static/index.html")][heads.index("reasons")], "every reason, the ones the columns hold too")
        self.assertEqual(rows[0][heads.index("function")], "validateTokenAgainstEveryConfiguredIssuer", "the function by name, as the export has it")

    def test_findings_prints_every_finding_in_the_long_form(self):
        text = shown(["findings"])
        self.assertTrue(text.startswith("Findings · 1 critical ✖ · 1 warning ▲ · 2 notes ●"))
        self.assertIn("↳ Ticket it.", text, "a note from a rule not measured yet keeps its step in the long form")
        heads, rows = rows_of("findings")
        self.assertEqual(heads, ["severity", "rule", "title", "statement", "step"])
        self.assertEqual([r[0] for r in rows], ["critical", "warning", "info", "info"])
        self.assertEqual(rows[0][3:], ["1 value in config/settings.py, still at HEAD", "Rotate it, then remove it from the history."])

    def test_a_section_with_nothing_for_this_run_says_so(self):
        self.assertEqual(shown(["most changed documents"]), "most-changed-documents: nothing in this run\n")
        self.assertEqual(section.csv_text(whole_report(), [], "most-changed-documents"), "")

    def test_a_step_that_did_not_finish_is_said_under_the_section(self):
        r = whole_report()
        r["meta"]["steps"] = {"scc": "timeout"}
        self.assertEqual(shown(["activity"], report=r).splitlines()[-1], "not complete: size timed out")
        self.assertNotIn("not complete", shown(["activity"]))


class Csv(unittest.TestCase):
    def test_no_csv_of_any_section_holds_an_address(self):
        report = whole_report()
        for name in section.NAMES:
            text = section.csv_text(report, found(), name)
            self.assertNotIn("@", text, name)
            self.assertNotIn("example.com", text, name)

    def test_people_has_every_field_of_a_person_but_the_address(self):
        heads, rows = rows_of("people")
        self.assertEqual(heads, ["author", "commits", "merges", "co-authored", "share", "surviving", "surviving lines", "lines added", "lines deleted",
                                 "first commit", "last commit", "gone", "aliases"])
        self.assertEqual(rows[1], ["Bob", "129", "0", "0", "35%", "21%", "2342", "4000", "100", "2025-08-20", "2026-09-10", "", "0"])
        self.assertEqual(rows[2][0], "dev", "a name that is an address is cut at its @")
        self.assertEqual(rows[2][-1], "1", "the aliases as a count: each is an address too")
        self.assertEqual(len(rows), 3, "every identity, no floor of commits and no cap")

    def test_a_table_with_no_rows_of_its_own_is_its_cells_without_bars_or_separators(self):
        heads, rows = rows_of("activity")
        self.assertEqual(heads, ["weekday", "commits", "share"], "the bar column is a drawing")
        self.assertEqual(rows[0], ["Mon", "40", "17%"])
        heads, rows = rows_of("size by language")
        self.assertEqual(rows[0], ["HTML", "28", "4783", "88%", "0"])
        heads, _ = rows_of("knowledge map")
        self.assertEqual(len(set(heads)), len(heads), "two columns headed share are told apart")
        self.assertIn("main owner share", heads)

    def test_the_csv_has_the_rows_of_the_table_in_its_order(self):
        report = whole_report()
        for name, sid in section.NAMES.items():
            if sid in (section.FINDINGS, "documents"):
                continue
            sec = render.whole_section(report, sid)
            made = section.table(report, [], name)
            self.assertEqual(len(made[1]), len(sec["rows"]), name)
            self.assertTrue(all(len(row) == len(made[0]) for row in made[1]), name)


class Markdown(unittest.TestCase):
    def test_the_named_sections_and_nothing_else(self):
        md = section.markdown(whole_report(), found(), ["people", "findings"])
        self.assertTrue(md.startswith("## People · all 3 identities, by commits · 1 with aliases merged\n\n| author | commits |"), md[:80])
        self.assertIn("\n## Findings\n\n- **critical** Secrets in source", md)
        self.assertNotIn("# demo", md)
        self.assertNotIn("Watch list", md)
        self.assertNotIn("example.com", md)


class Layout(unittest.TestCase):
    """The invariants of tests/test_layout.py, for every section on its own at every width."""

    def test_every_section_keeps_the_grammar(self):
        report = whole_report()
        for name in section.NAMES:
            for width in WIDTHS:
                plain, colour = shown([name], width, report), shown([name], width, report, colour=True)
                self.assertEqual(SGR.sub("", colour), plain, (name, width))
                self.assertEqual([line for line in plain.split("\n") if line != line.rstrip()], [], (name, width))
                codes = {code for params in SGR.findall(colour) for code in params.split(";")}
                self.assertLessEqual(codes, {"0", "1", "2", "31", "33"}, (name, width))
                lines = plain.splitlines()
                for i, line in enumerate(lines):
                    if set(line.strip()) == {"─"}:   # a table: its rule is as wide as its widest row
                        table = [lines[i - 1]] + [row for row in lines[i + 1:] if row.startswith("  ") and not row.startswith("    ")]
                        sec = render.whole_section(report, section.NAMES[name], width)
                        drawn = render.table_lines(render.fit(sec, width))
                        self.assertEqual(len(line), max(len(x.plain) for x in [drawn["head"]] + drawn["rows"]), (name, width))
                        self.assertLessEqual(len(line), width, (name, width))
                        self.assertTrue(table)

    def test_an_ascii_stream_raises_nothing(self):
        report = whole_report()
        for name in section.NAMES:
            raw = io.BytesIO()
            stream = io.TextIOWrapper(raw, encoding="ascii", newline="\n")
            section.show(report, found(), render.carry(Console(file=stream, width=80, force_terminal=False, color_system=None)), [name])
            stream.flush()
            text = raw.getvalue().decode("ascii")
            self.assertEqual(len(text.splitlines()), len(shown([name], 80, report).splitlines()), name)


def _out_dir(out: str) -> None:
    """An output directory with a People table and two files in history."""
    ids = [{"name": "Ann", "email": "ann@x.com", "commits": 5, "aliases": []}, {"name": "bob@corp.example", "email": "bob@corp.example", "commits": 2, "aliases": []}]
    with open(os.path.join(out, "meta.json"), "w") as fh:
        json.dump({"name": "demo", "commits": 7, "identities": ids}, fh)
    with open(os.path.join(out, "maat-revisions.csv"), "w") as fh:
        fh.write("entity,n-revs\na.py,3\ntests/test_a.py,9\n")
    with open(os.path.join(out, "size.json"), "w") as fh:
        json.dump([{"Name": "Python", "Count": 2, "Code": 30, "Comment": 0, "Blank": 0, "Complexity": 1,
                    "Files": [{"Location": "a.py", "Code": 10, "Complexity": 1}, {"Location": "tests/test_a.py", "Code": 20, "Complexity": 0}]}], fh)


def _contents(out: str) -> dict:
    held = {}
    for name in sorted(os.listdir(out)):
        with open(os.path.join(out, name), "rb") as fh:
            held[name] = fh.read()
    return held


def _main(argv, colour=False):
    c = Console(file=io.StringIO(), width=100, force_terminal=colour, color_system="truecolor" if colour else None)
    with mock.patch.dict(os.environ):
        os.environ.pop("GITMOLE_NOW", None)   # its notice goes to stderr, which is this console too
        rc = cli.main(argv, console=c)
    return rc, c.file.getvalue()


class CommandLine(unittest.TestCase):
    def test_a_section_of_an_earlier_run_writes_no_file(self):
        with tempfile.TemporaryDirectory() as out:
            _out_dir(out)
            before = _contents(out)
            rc, text = _main([out, "--no-run", "--section", "hotspots"])
            rc2, table = _main([out, "--no-run", "--section", "People", "--csv"])
            after = _contents(out)
        self.assertEqual((rc, rc2), (0, 0))
        self.assertEqual(after, before, "no new file, and the existing ones as they were")
        self.assertTrue(text.startswith("◆ Hotspots"), "no banner, no header: the section")
        self.assertRegex(text, r"\n  …/test_a\.py +test +9 ")
        self.assertNotIn("Findings", text)
        self.assertEqual(table.splitlines()[:3], ["author,commits,merges,co-authored,share,surviving,surviving lines,lines added,lines deleted,first commit,last commit,gone,aliases",
                                                  "Ann,5,0,0,71%,-,0,,,,,,0", "bob,2,0,0,29%,-,0,,,,,,0"])
        self.assertNotIn("@", table)

    def test_csv_is_the_rows_alone_even_on_a_terminal(self):
        with tempfile.TemporaryDirectory() as out:
            _out_dir(out)
            rc, text = _main([out, "--no-run", "--section", "hotspots", "--csv"], colour=True)
        self.assertEqual(rc, 0)
        self.assertEqual(text.splitlines()[0], "file,kind,n-revs,code,complexity,score,trend")
        self.assertNotIn("\x1b", text)

    def test_markdown_takes_the_section(self):
        with tempfile.TemporaryDirectory() as out:
            _out_dir(out)
            rc, text = _main([out, "--no-run", "--section", "hotspots", "--markdown", "-"])
        self.assertEqual(rc, 0)
        self.assertTrue(text.startswith("## Hotspots (score = changes × lines of code)\n\n| file | kind |"), text[:80])
        self.assertNotIn("# demo", text)

    def test_an_unknown_name_prints_the_list_and_exits_2_before_anything_runs(self):
        rc, text = _main(["/nonexistent/analysis-x", "--no-run", "--section", "hot spots", "--section", "nope"])
        self.assertEqual(rc, 2)
        self.assertIn("--section: no section called 'hot spots', 'nope'. The names:", text)
        for name in section.NAMES:
            self.assertIn(name, text)
        self.assertNotIn("no gitmole output found", text, "said before the target is looked at")

    def test_the_combinations_that_make_no_sense_are_refused(self):
        with tempfile.TemporaryDirectory() as out:
            _out_dir(out)
            for extra, why in ((["--section", "people", "--full"], "--full has nothing to add"),
                               (["--csv"], "--csv needs --section NAME"),
                               (["--section", "people", "--section", "activity", "--csv"], "give one --section"),
                               (["--section", "people", "--csv", "--markdown", "-"], "choose one"),
                               (["--section", "people", "--json", "-"], "would both write to stdout; give --json a file"),
                               (["--section", "people", "--sarif", "-"], "would both write to stdout; give --sarif a file"),
                               (["--section", "people", "--hook"], "--hook prints an agent's context instead")):
                rc, text = _main([out, "--no-run"] + extra)
                self.assertEqual(rc, 2, extra)
                self.assertIn(why, text, extra)
            self.assertEqual(_main(["owner/*", "--section", "people"])[0], 2)
            self.assertIn("--section needs one repository, not owner/*", _main(["owner/*", "--section", "people"])[1])

    def test_an_export_to_a_file_and_a_gate_work_as_they_always_did(self):
        with tempfile.TemporaryDirectory() as out:
            _out_dir(out)
            with open(os.path.join(out, "secrets.json"), "w") as fh:
                json.dump([{"RuleID": "aws-access-token", "File": "a.py", "Commit": "abc1234", "StartLine": 3, "Secret": "AKIAQWERTYUIOPASDFGH", "Fingerprint": "abc1234:a.py:aws-access-token:3"}], fh)
            path = os.path.join(out, "r.json")
            plain = os.path.join(out, "plain.json")
            rc, text = _main([out, "--no-run", "--section", "people", "--json", path, "--fail-on", "critical"])
            _main([out, "--no-run", "--json", plain])
            with open(path) as a, open(plain) as b:
                self.assertEqual(a.read(), b.read(), "the JSON export is the whole export, section or not")
        self.assertTrue(text.startswith("◉ People"))
        self.assertIn(rc, (0, 3))
        self.assertEqual(rc, _main_rc_without_section(), "the gate reads the findings, not what is printed")


def _main_rc_without_section() -> int:
    with tempfile.TemporaryDirectory() as out:
        _out_dir(out)
        with open(os.path.join(out, "secrets.json"), "w") as fh:
            json.dump([{"RuleID": "aws-access-token", "File": "a.py", "Commit": "abc1234", "StartLine": 3, "Secret": "AKIAQWERTYUIOPASDFGH", "Fingerprint": "abc1234:a.py:aws-access-token:3"}], fh)
        return _main([out, "--no-run", "--fail-on", "critical"])[0]


class Whole(unittest.TestCase):
    def test_the_default_report_and_full_are_as_they_were(self):
        """The mode is new; no other rendering reads it."""
        report = sample_report()
        for full in (False, True, "markdown"):
            for sec in render.sections(report, full=full):
                self.assertNotIn("kind", sec["columns"] if sec["id"] != "agent_surface" else [], (full, sec["id"]))
                self.assertNotIn("csv", sec)


if __name__ == "__main__":
    unittest.main()

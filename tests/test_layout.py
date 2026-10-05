"""One layout grammar that survives a pipe, a light theme, no colour and no Unicode.

The report is drawn as lines of text and printed as they are, so these hold for every render, whatever the
width: the colour render with its escapes stripped is the plain render byte for byte; the only escapes are
bold, dim, yellow and red; a stream that cannot carry a mark gets its ASCII substitute and raises nothing; a
table's rule is exactly as long as its widest row; no line ends in a space; and no line of the default
report passes the width but a path that cannot be broken. prometheus's default report held 23 different
escape sequences, 55 of its 213 lines ended in padding, and a box broke a path at its border."""
import io
import json
import os
import re
import tempfile
import unittest

from rich.console import Console

from gitmole import cli, render
from tests.test_render import AgentSurface, ChangeRisk, sample_report

SGR = re.compile(r"\x1b\[([0-9;]*)m")
WIDTHS = (60, 80, 100, 160)
DEEP = "services/gateway/internal/transport/middleware/authentication/token_validator.go"   # 78 characters: longer than a cell, and with its indent than a line of 80


def rich_report() -> dict:
    """sample_report with what makes a layout work for its living: paths too long for a cell, a name outside
    ASCII, a window, a scope, and every --full section with something in it."""
    r = sample_report()
    r["meta"]["identities"] = [{"name": "Björn Rabenstein", "email": "b@x.com", "commits": 234}, {"name": "Bob", "email": "bob@x.com", "commits": 129}]
    r["meta"]["since"] = "2025-01-01"
    r["theseus_authors"] = {"Björn Rabenstein": 9076, "Bob": 2342}
    r["size"]["files"][DEEP] = {"code": 2400, "complexity": 310}
    r["revisions"] = [{"entity": DEEP, "n-revs": 240}] + r["revisions"]
    r["functions"] += [{"file": DEEP, "function": "validateTokenAgainstEveryConfiguredIssuer", "ccn": 61, "nloc": 240, "params": 5, "start": 40, "end": 300},
                       {"file": "static/js/app.js", "function": "(anonymous)", "anonymous": True, "ccn": 33, "nloc": 120, "params": 0, "start": 210, "end": 330}]
    r["coupling"] += [{"entity": DEEP, "coupled": DEEP.replace("token_validator", "token_cache"), "degree": 92, "average-revs": 14},
                      {"entity": "static/a.html", "coupled": "static/b.html", "degree": 71, "average-revs": 9}]
    r["ownership"] += [{"entity": DEEP, "author": "Björn Rabenstein", "added": 5200, "deleted": 10}]
    r["signing"] = {"commits": 100, "signed": 46, "mechanisms": {"gpg": 40, "ssh": 6}, "last_year": {"commits": 50, "signed": 40},
                    "by_year": {"2025": {"commits": 60, "signed": 20}, "2026": {"commits": 40, "signed": 26}}}
    w = {"commits": 10, "added": 200, "moved": 20, "churned": 10, "moved_share": 0.1, "churn_share": 0.05}
    r["provenance"] = {"trailers": {"commits": 363, "keys": {"Co-authored-by": 40, "Signed-off-by": 212}},
                       "lines": {"windows": [{"label": "last year", "from": "2025-09-10", "to": "2026-09-10", **w},
                                             {"label": "the year before", "from": "2024-09-10", "to": "2025-09-10", **w}], "churn_days": 14},
                       "agents": AgentSurface.AGENTS}
    # what --full's supply-chain sections read: the scan's rows by rule, a vulnerable package past the critical band, the hygiene record and the steps
    r["secrets"] = [{"rule": "generic-api-key", "file": "tests/fixtures/keys.py", "commit": "abc1234", "line": 3, "value": "v1", "confidence": "low", "at_head": True},
                    {"rule": "private-key", "file": DEEP.replace("token_validator.go", "testdata/ca.key"), "commit": "def5678", "line": 1, "value": "v2", "confidence": "high", "at_head": False}]
    r["dependencies"]["vulnerable"] = [
        {"name": "github.com/example/gateway", "version": "0.307.4-0.20251119130332-1174b0ce4f1f", "source": "services/gateway/go.mod", "ids": ["GO-2026-1"], "aliases": ["CVE-2026-40179"],
         "score": 7.5, "fixed": "0.311.2-0.20260410083055-07c6232d159b", "imported": True},
        {"name": "websocket-driver", "version": "0.7.4", "source": "package-lock.json", "ids": ["GHSA-x"], "aliases": ["CVE-2026-54466"], "score": 9.2, "fixed": "0.7.5", "imported": False, "runtime": False}]
    r["hygiene"] = {"actions": {"pinned": 65, "local": 5, "unpinned_count": 0}, "lockfiles": {"pairs": 9}, "updates": {"tool": "renovate", "covered": ["gomod", "npm"], "uncovered": []},
                    "trojan": {"files": 675}, "binaries": {"binaries": 9, "executables_count": 0}, "submodules": {"count": 0}, "symlinks": {"count": 0}, "confusion": {}, "install": {},
                    "presence": {"license": "LICENSE", "security_policy": "SECURITY.md", "codeowners": "CODEOWNERS"}, "licences": {"file_licence": "Apache-2.0", "approved": True, "files": ["LICENSE"]},
                    "imports": {"manifests": 9, "unused": [], "count": 0}}
    r["structure"] = {"status": "run", "resolved": {"go": 1.0, "tsx": 0.916}}
    r["unreachable"] = {"objects": 0, "blobs": 0, "scanned": 0, "findings": 0}
    r["meta"]["steps"] = {"scc": "run", "git-log": "run", "change analysis": "run", "betterleaks": "run", "osv-scanner": "run", "hygiene": "run", "structure": "run", "trend": "timeout"}
    return r


def found() -> list:
    """A critical, a warning with a title longer than a narrow terminal, a note, one from a rule not measured
    yet, and a statement that names a path no line can hold."""
    mk = lambda sev, title, detail, advice, **more: {"severity": sev, "title": title, "detail": f"{detail} {advice}", "advice": advice, "rule": {"id": "r"}, **more}   # noqa: E731
    return [mk("critical", "Secrets in source", "1 value in config/settings.py, still at HEAD.", "Rotate it, then remove it from the history."),
            mk("warning", "Vulnerable dependencies only in test, example or vendored lock files", f"3 packages in 2 lock files: {DEEP} pins one of them and is the first to fix.",
               "Upgrade the first of them; one that does not apply to this code can be ignored in osv-scanner.toml at the repository root."),
            mk("info", "Sweeping commits", "2 commits each touch 40 files or more.", "Add them to .git-blame-ignore-revs."),
            mk("info", "Debt the authors flagged in hotspots", "8 of the top 10 hotspots carry TODO or FIXME comments; most in static/index.html (10).", "Ticket it.", unjudged=True)]


COMPARE = {"new": [{"severity": "warning", "title": "Credential-shaped files tracked"}], "resolved": [{"severity": "info", "title": "Reverts"}],
           "persisting": [{"severity": "info", "title": "Vulnerable dependencies only in test, example or vendored lock files", "was": "warning",
                           "changed": [["packages", 16, 1], ["places", 40, 2], ["lock files", 3, 2]]}],
           "watch_entered": ["c.py"], "watch_left": [DEEP],
           "tally": {"before": {"critical": 0, "warning": 2, "info": 2}, "after": {"critical": 1, "warning": 1, "info": 2}},
           "before": {"commit": "540ee5b560cc6e775e11317048a13cc7e355bf91", "date": "2026-09-10", "options_differ": []}}
RISK = {"base": "main", **ChangeRisk.RISK,
        "files": ChangeRisk.RISK["files"] + [{"file": DEEP, "score": 1.5, "watched": True,
                                             "reasons": ["changed 240 times", "fixed 12 times in 6 months", "7 of 9 authors are minor contributors", "changes alongside 31 other files"]}]}


def drawn(width: int, full: bool = False, colour: bool = False, stream=None, extras: bool = True) -> str:
    """The report at `width`, plain or with colour forced, into a string or into `stream`."""
    out = stream or io.StringIO()
    console = Console(file=out, width=width, force_terminal=colour, color_system="truecolor" if colour else None)
    extra = {"risk": RISK, "base": "main", "compare": COMPARE} if extras else {}
    render.report(rich_report(), found(), console, full=full, **extra)
    return "" if stream else out.getvalue()


def every_render():
    """(what it is, its text) for every drawing a width or a mode can change."""
    for width in WIDTHS:
        for full in (False, True):
            for colour in (False, True):
                yield (width, full, colour), drawn(width, full, colour)


class NoBoxes(unittest.TestCase):
    def test_a_block_is_a_title_at_column_one_and_its_content_two_columns_in(self):
        lines = drawn(80).splitlines()
        self.assertFalse([line for line in lines if set(line) & set("│╭╮╰╯")], "no box anywhere")
        self.assertEqual(lines[0], "demo · branch main", "the header's title line")
        self.assertTrue(lines[1].startswith("  history  "), "its label grid, two columns in")
        at = lines.index("")
        self.assertEqual(lines[at + 1], "Findings · 1 critical ✖ · 1 warning ▲ · 2 notes ● · 1 not measured yet", "one blank line, then the Findings title at column 1")
        self.assertEqual(lines[at + 2], "✖ Secrets in source", "the mark at column 1, the title on its line")
        self.assertEqual(lines[at + 3], "  1 value in config/settings.py, still at HEAD", "the statement at column 3")
        self.assertEqual(lines[at + 4], "  ↳ Rotate it, then remove it from the history.", "the step under its mark")
        self.assertNotIn("", lines[at + 1:lines.index("", at + 1)], "no blank line inside a block")
        self.assertNotIn("\n\n\n", drawn(80), "and one between two")

    def test_every_finding_owns_one_mark_at_column_one(self):
        for full in (False, True):
            lines = drawn(80, full).splitlines()
            block = lines[lines.index("") + 1:]
            block = block[:block.index("")]
            self.assertEqual([line[0] for line in block[1:] if line[0] != " "], ["✖", "▲", "●", "●", "·"], "four findings, and what was not computed last")

    def test_a_title_longer_than_the_terminal_wraps_under_itself(self):
        lines = drawn(60).splitlines()
        at = next(i for i, line in enumerate(lines) if line.startswith("▲ "))
        self.assertEqual(lines[at:at + 2], ["▲ Vulnerable dependencies only in test, example or vendored", "  lock files"])


class OneRender(unittest.TestCase):
    def test_the_colour_render_with_its_escapes_stripped_is_the_plain_render(self):
        """NO_COLOR, a pipe and --no-color give the colour render's bytes with the escapes stripped."""
        for width in WIDTHS:
            for full in (False, True):
                self.assertEqual(SGR.sub("", drawn(width, full, colour=True)), drawn(width, full), (width, full))

    def test_the_colour_render_holds_only_bold_dim_yellow_and_red(self):
        seen = set()
        for what, text in every_render():
            if what[2]:
                self.assertNotIn("\x1b[38", text, "no truecolour or 256-colour foreground")
                self.assertNotIn("\x1b[48", text, "no background")
                codes = {code for params in SGR.findall(text) for code in params.split(";")}
                self.assertLessEqual(codes, {"0", "1", "2", "31", "33"}, what)   # reset, bold, dim, red, yellow: no italic (3), cyan (36), blue (34), green (32)
                seen |= set(SGR.findall(text))
                self.assertEqual(SGR.sub("", text).count("\x1b"), 0, "and no other escape")
        self.assertEqual(seen, {"0", "1", "2", "33", "1;31"}, "reset, bold, dim, a warning's yellow and a critical's bold red, and no other combination")

    def test_severity_colour_is_on_the_mark_and_title_only(self):
        text = drawn(80, colour=True)
        self.assertIn("\x1b[1;31m✖ Secrets in source\x1b[0m\n  1 value in config/settings.py, still at HEAD\n  ↳ Rotate it", text,
                      "the statement and the step in the terminal's own foreground")
        self.assertIn("\n● Sweeping commits\n", text, "a note's mark and title have no colour")
        self.assertIn("● Debt the authors flagged in hotspots\x1b[2m (not measured yet)\x1b[0m: 8 of the top 10", text, "the tag dim, and nothing coloured before it")
        self.assertIn("\x1b[1m◎ Watch list\x1b[0m · ", text, "a section's name bold in the default foreground, its qualifier plain")
        self.assertIn("\x1b[1mdemo\x1b[0m · branch main", text)
        self.assertRegex(text, r"\n  \x1b\[2mfile +changes +fixes[^\n\x1b]*\x1b\[0m\n  \x1b\[2m─+\x1b\[0m\n  \x1b\[1m[^\x1b]+\x1b\[0m +[\d,]+ [^\x1b]*\n", "heads and rule dim, a row's first cell bold, its numbers plain")


class Lines(unittest.TestCase):
    def test_no_line_of_any_render_ends_in_a_space(self):
        for what, text in every_render():
            self.assertEqual([line for line in SGR.sub("", text).split("\n") if line != line.rstrip()], [], what)

    def test_no_other_surface_ends_a_line_in_a_space_either(self):
        report = rich_report()
        for width in WIDTHS:
            c = Console(file=io.StringIO(), width=width, force_terminal=False, color_system=None)
            render.excerpt(report, found(), c)
            render.print_section(c, render.portfolio_section([("demo", report, found()), ("other-repository-with-a-long-name", report, [])]))
            render.print_section(c, render._section("File types", [("type", {}), ("files", render.RIGHT), ("code", {})], [("py", 12, "yes"), ("md", 3, "no")], caption="code = analysed"))
            render.print_section(c, render._section("Watch list", [("file", render.PATH)], [], note="no file changed more than once, " * 6 + "so there is nothing to rank"))
            text = c.file.getvalue()
            self.assertEqual([line for line in text.split("\n") if line != line.rstrip()], [], width)
            self.assertLessEqual(max(len(line) for line in text.split("\n")), max(width, 74), "and each keeps to the width")

    def test_no_line_of_the_default_passes_the_width_but_a_path_that_cannot_be_broken(self):
        """From 80 columns, which is the complete report (the closing line that names the re-render command is
        74 characters, and is one line by the closing block's cap)."""
        for width in (80, 100, 160):
            over = [line for line in drawn(width).splitlines() if len(line) > width]
            for line in over:   # only where a path is longer than the room its block's indent leaves: it is whole, and the line is as short as it can be
                self.assertTrue(line.endswith(DEEP) and len(DEEP) > width - (len(line) - len(DEEP)), (width, line))
            if width == 80:
                self.assertEqual(over, [f"  {DEEP}", f"  left the watch list     {DEEP}"], "in a finding, on a line of its own; in a label grid, at the value's start")

    def test_a_path_is_whole_in_a_finding_and_elided_only_in_a_table(self):
        for width in WIDTHS:
            lines = drawn(width).splitlines()
            block = lines[lines.index("") + 1:]
            block = block[:block.index("")]
            self.assertIn(DEEP, " ".join(block), width)
            self.assertNotIn("…", " ".join(block), "no ellipsis in the Findings")
        watch = drawn(80).split("◎ Watch list")[1].split("\n\n")[0]
        self.assertIn("…/token_validator.go", watch, "the table gives up the directories")
        self.assertNotIn(DEEP, watch)


class Tables(unittest.TestCase):
    def tables(self):
        report = rich_report()
        for width in WIDTHS + (None,):
            for full in (False, True):
                secs = render.sections(report, full=full, width=width) + [render.risk_section(RISK, "main", full), render.portfolio_section([("demo", report, found())])]
                for sec in secs:
                    if sec["rows"] and not sec.get("grid"):
                        yield (width, full, sec["title"]), render.fit(sec, width), render.table_lines(render.fit(sec, width))

    def test_every_table_s_rule_is_exactly_as_long_as_its_widest_row(self):
        seen = 0
        for what, _, table in self.tables():
            widest = max(len(line.plain) for line in [table["head"]] + table["rows"])
            self.assertEqual(len(table["rule"].plain), widest, what)
            self.assertEqual(set(table["rule"].plain.strip()), {"─"}, what)
            seen += 1
        self.assertGreater(seen, 100, "every table of the default report and of --full, at five widths")

    def test_no_cell_is_wrapped_and_no_number_is_cut(self):
        for what, fitted, table in self.tables():
            self.assertEqual(len(table["rows"]), len(fitted["rows"]), f"{what}: a row is a line")
            self.assertNotIn("\n", table["head"].plain, f"{what}: the heads are one line")
            for name, opts, column in zip(fitted["columns"], fitted["col_opts"], zip(*fitted["rows"])):
                if opts.get("justify") == "right" or opts.get("kind") == "fixed":
                    self.assertFalse([cell for cell in column if "…" in cell], f"{what}: {name} is never cut")
            if what[0]:
                self.assertLessEqual(len(table["rule"].plain), what[0], f"{what}: the table keeps to the width")

    def test_columns_are_two_apart_and_heads_lie_as_their_cells_do(self):
        sec = render._section("T", [("file", render.PATH), ("changes", render.RIGHT), ("top author", render.WHOLE), ("look at first", render.TAIL)],
                              [("a.py", 1234, "23% gone", "eval() nesting 6"), ("lib/b.py", 7, " 9%", "")])
        table = render.table_lines(sec)
        self.assertEqual([table["head"].plain, table["rule"].plain] + [row.plain for row in table["rows"]],
                         ["  file      changes  top author  look at first",
                          "  " + "─" * 47,
                          "  a.py        1,234  23% gone    eval() nesting 6",
                          "  lib/b.py        7   9%"])

    def test_width_changes_wrapping_and_elision_never_rows_order_or_months(self):
        report = rich_report()
        for full in (False, True):
            shape = {}
            for width in WIDTHS:
                secs = [render.fit(sec, width) for sec in render.sections(report, full=full, width=width)]
                number = lambda row: next((c for c in row if c.replace(",", "").rstrip("%").strip().isdigit()), "")   # noqa: E731 - a row's first number, which no width cuts
                shape[width] = [(sec["id"], len(sec["rows"]), [number(row) for row in sec["rows"]]) for sec in secs]
                if full and width >= 70:   # a name's first eight characters and twelve months need 70 columns; under that the last columns are left out and named
                    months = next(sec for sec in secs if sec["id"] == "timeline")["columns"][1:]
                    self.assertEqual(len(months), 12, f"twelve months at {width} columns")
            self.assertEqual(len({json.dumps(v) for v in shape.values()}), 1, "the same sections, in the same order, with the same rows in the same order at every width")

    def test_the_reasons_of_a_change_are_under_its_row_whole(self):
        """Change risk had a drawing of its own, its reasons a third column that wrapped inside its cell."""
        text = drawn(80).split("◈ Change risk")[1].split("\n\n")[0].splitlines()
        self.assertRegex(text[1], r"^  file +risk$")
        self.assertEqual(text[2], "  " + "─" * (len(text[1]) - 2 + len("▰" * 10) - len("risk")), "the table drawing of every other section: heads, then a rule as wide as the columns")
        row = next(i for i, line in enumerate(text) if "token_validator.go" in line)
        self.assertRegex(text[row], r"^  services/…/authentication/token_validator\.go +▰{5}$")
        self.assertEqual(text[row + 1:row + 3], ["    changed 240 times · fixed 12 times in 6 months · 7 of 9 authors are minor",
                                                 "    contributors · changes alongside 31 other files"])

    def test_since_last_report_is_a_label_grid_so_nothing_of_a_row_is_cut(self):
        text = drawn(80).split("⇄ Since last report")[1].split("\n\n")[0].splitlines()
        self.assertEqual(text[1], "  new                     warning · Credential-shaped files tracked")
        at = next(i for i, line in enumerate(text) if line.startswith("  persisting"))
        self.assertEqual(text[at:at + 3], ["  persisting              warning → note · Vulnerable dependencies only in test,",
                                           "                          example or vendored lock files (packages 16 → 1;",
                                           "                          places 40 → 2; lock files 3 → 2)"])
        self.assertFalse([line for line in text if set(line.strip()) == {"─"}], "a grid has no rule")


class Ascii(unittest.TestCase):
    def into(self, encoding: str, full: bool = False) -> str:
        raw = io.BytesIO()
        stream = io.TextIOWrapper(raw, encoding=encoding, newline="\n")   # errors are strict: a character it cannot carry raises
        drawn(80, full, stream=stream)
        stream.flush()
        return raw.getvalue().decode(encoding)

    def test_a_stream_that_cannot_carry_a_mark_would_raise(self):
        stream = io.TextIOWrapper(io.BytesIO(), encoding="ascii")
        with self.assertRaises(UnicodeEncodeError):
            stream.write("▲ a warning")
            stream.flush()

    def test_an_ascii_stream_raises_nothing_and_has_the_same_number_of_lines(self):
        for full in (False, True):
            plain, text = drawn(80, full), self.into("ascii", full)
            self.assertEqual(len(text.splitlines()), len(plain.splitlines()), full)
            self.assertTrue(text.isascii())
            self.assertEqual(text, plain.translate(str.maketrans(render.ASCII_MARKS)).replace("ö", "?"), "each mark its substitute, any other character a question mark")
        lines = self.into("ascii").splitlines()
        self.assertEqual(lines[0], "demo - branch main")
        self.assertIn("x Secrets in source", lines)
        self.assertIn("  > Rotate it, then remove it from the history.", lines)
        self.assertIn("# Watch list - all 3, ranked by changes x lines of code", lines)
        self.assertEqual(lines[1:3], ["  history  363 commits - 2025-08-20 -> 2026-09-10 - since 2025-01-01 -", "           2 identities"])
        self.assertTrue(any(set(line.strip()) == {"-"} and len(line) > 20 for line in lines), "a rule of hyphens")
        self.assertTrue(any(".../token_validator.go" in line for line in lines), "an elided path")
        self.assertTrue(any(line.startswith("  Bj?rn Rabenstein") for line in lines), "a name it cannot carry does not stop the report")

    def test_the_marks_the_stream_can_carry_are_kept(self):
        latin = self.into("latin-1")
        self.assertIn("demo · branch main", latin, "Latin-1 has the middle dot")
        self.assertIn("changes × lines of code", latin)
        self.assertIn("Björn Rabenstein", latin)
        self.assertIn("\n! Vulnerable dependencies", latin, "and not the triangle")
        self.assertEqual(self.into("utf-8"), drawn(80), "a UTF-8 stream is written to as it always was")
        self.assertEqual(render.substitutes("utf-8"), {})
        self.assertEqual(render.substitutes(None), {}, "a string buffer names no encoding")
        self.assertEqual(render.substitutes("no-such-codec"), {})

    def test_every_mark_has_one_fixed_substitute(self):
        marks = set(render.SEVERITY_MARK.values()) | set(render.SYMBOLS.values()) | {render.SECTION_MARK, render.STEP_MARK, render.RULE_MARK, render.BAR_MARK, render.BLOCK_MARK, "…", "→", "·", "≥", "×"}
        self.assertLessEqual(marks, set(render.ASCII_MARKS))
        self.assertTrue(all(plain.isascii() and plain for plain in render.ASCII_MARKS.values()))
        one = [render.SEVERITY_MARK[s] for s in render.SEVERITY_MARK] + [render.STEP_MARK, render.RULE_MARK, render.SECTION_MARK] + list(render.SYMBOLS.values())
        self.assertEqual({len(render.ASCII_MARKS[m]) for m in one}, {1}, "the marks a grid is counted from keep their one column")
        for full in (False, True):   # no mark the report prints is missing from the table: what is left is a letter of a name
            left = {ch for ch in drawn(80, full) if not ch.isascii() and ch not in render.ASCII_MARKS}
            self.assertEqual(left, {"ö"}, full)

    def test_the_command_line_writes_through_the_substitutes(self):
        with tempfile.TemporaryDirectory() as out:
            with open(os.path.join(out, "meta.json"), "w") as fh:
                json.dump({"name": "demo", "commits": 5, "identities": []}, fh)
            raw = io.BytesIO()
            stream = io.TextIOWrapper(raw, encoding="ascii", newline="\n")
            rc = cli.main([out, "--no-run"], console=Console(file=stream, width=80, force_terminal=False, color_system=None))
            stream.flush()
        self.assertEqual(rc, 0)
        text = raw.getvalue().decode("ascii")
        self.assertIn("demo - branch ?", text)
        self.assertIn("# Supply chain", text)


if __name__ == "__main__":
    unittest.main()

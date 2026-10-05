"""What the report says about the part of a tree it does not rank: the header's coverage line when the
files the type filter left out hold more lines than the scored ones, the most-changed documents when
documentation is most of the tree, the measures that could not be computed, and the hook's words for a
document. A repository of Markdown skills had 17 of its 227 files scored and nothing said so."""
import io
import json
import os
import tempfile
import unittest

from rich.console import Console

from gitmole import classify, findings, hook, load, render, watch


def _scc(files: dict) -> list:
    """size.json rows: {path: (language, code)}."""
    rows = {}
    for path, (lang, code) in files.items():
        row = rows.setdefault(lang, {"Name": lang, "Count": 0, "Code": 0, "Comment": 0, "Blank": 0, "Complexity": 0, "Files": []})
        row["Count"] += 1
        row["Code"] += code
        row["Files"].append({"Location": path, "Code": code, "Complexity": 0})
    return list(rows.values())


DOCS = {"app/run.sh": ("Shell", 100), "skills/a/SKILL.md": ("Markdown", 600), "README.md": ("Markdown", 200),
        "tests/README.md": ("Markdown", 50), "hooks/hooks.json": ("JSON", 50)}
CODE = {"app/main.py": ("Python", 900), "README.md": ("Markdown", 100)}

LOG = "\n".join([
    "--c5--2026-05-01T10:00:00+00:00--Ann--fix: the skill's wording",
    "3\t1\tskills/a/SKILL.md",
    "",
    "--c4--2026-04-01T10:00:00+00:00--Ann--fix the runner",
    "2\t2\tapp/run.sh",
    "1\t0\tREADME.md",
    "",
    "--c3--2026-03-01T10:00:00+00:00--Ann--Merge branch 'x'",
    "",
    "--c2--2026-02-01T10:00:00+00:00--Ann--reword",
    "5\t5\tskills/a/SKILL.md",
    "1\t1\tREADME.md",
    "1\t1\ttests/README.md",
    "",
    "--c1--2026-01-01T10:00:00+00:00--Ann--start",
    "100\t0\tapp/run.sh",
    "600\t0\tskills/a/SKILL.md",
    "200\t0\tREADME.md",
    "50\t0\ttests/README.md",
    "",
])


def _out(d: str, files: dict, coverage: dict, log: str = LOG, activity: dict = None) -> str:
    for name, text in {"meta.json": json.dumps({"name": "demo", "commits": 5, "identities": [], "file_types": None, "coverage": coverage}),
                       "size.json": json.dumps(_scc(files)), "log.txt": log,
                       "activity.json": json.dumps(activity or {"by_weekday": [5, 0, 0, 0, 0, 0, 0], "fix_commits": 2})}.items():
        with open(os.path.join(d, name), "w") as fh:
            fh.write(text)
    return d


def _docs_report(d: str) -> dict:
    return load.load_report(_out(d, DOCS, {"scored": 1, "not a source type": 3, "test file": 1}))


def _text(report: dict, found=(), width=100, full=False) -> str:
    console = Console(file=io.StringIO(), width=width, record=True, force_terminal=False, color_system=None)
    render.report(report, list(found), console, full=full)
    return console.export_text()


class Lines(unittest.TestCase):
    def test_lines_are_split_by_what_the_type_filter_left_out(self):
        cls = classify.Classifier({"meta": {"file_types": None}, "size": {"files": {"app/run.sh": {"code": 100, "complexity": 0}}}})
        lines = classify.lines(cls, {p: n for p, (_, n) in DOCS.items()})
        self.assertEqual(lines, {"tracked": 1000, "scored": 100, "documentation": 850, "other_types": 50},
                         "a README under tests/ is documentation the filter left out, wherever it sits")
        self.assertTrue(classify.unranked(lines))
        self.assertTrue(classify.documents_lead(lines))

    def test_a_tree_of_tests_is_ranked_as_it_was_meant_to_be(self):
        """Most trees hold more test lines than source lines; that is not what the line is about."""
        self.assertFalse(classify.unranked({"tracked": 1000, "scored": 300, "documentation": 100, "other_types": 100}))
        self.assertFalse(classify.unranked({"tracked": 0, "scored": 0, "documentation": 0, "other_types": 0}))
        self.assertFalse(classify.documents_lead({"tracked": 1000, "scored": 100, "documentation": 500, "other_types": 400}), "half is not most")

    def test_documents_are_out_for_their_type_and_nothing_else(self):
        cls = classify.Classifier({"meta": {"file_types": None, "generated": ["docs/api.md"]}, "size": {"files": {"app/run.sh": {"code": 1, "complexity": 0}}}})
        code = dict.fromkeys(["README.md", "docs/api.md", "tests/README.md", "docs/conf.py", "app/run.sh", "hooks/hooks.json"], 1)
        self.assertEqual(classify.documents(cls, code), {"README.md"})

    def test_all_file_types_leaves_nothing_out_by_type(self):
        cls = classify.Classifier({"meta": {"file_types": "all"}, "size": {"files": {p: {"code": n, "complexity": 0} for p, (_, n) in DOCS.items()}}})
        lines = classify.lines(cls, {p: n for p, (_, n) in DOCS.items()})
        self.assertEqual((lines["documentation"], lines["other_types"]), (0, 0))
        self.assertFalse(classify.unranked(lines))


class History(unittest.TestCase):
    def test_commits_outside_the_scored_pool_and_document_revisions(self):
        out = load.parse_unscored_history(LOG, {}, lambda p: p == "app/run.sh", {"skills/a/SKILL.md", "README.md"})
        self.assertEqual(out["commits"], {"commits": 5, "fixes": 2, "outside": 2, "fixes_outside": 1},
                         "a merge has no file list and is never outside; a fix that touched the runner is inside")
        self.assertEqual(out["revisions"], {"skills/a/SKILL.md": 3, "README.md": 3})

    def test_revisions_leave_out_the_imports_and_sweeps_and_keep_to_the_window(self):
        out = load.parse_unscored_history(LOG, {"imports": [{"hash": "c1"}], "sweeping": [{"hash": "c2"}]}, lambda p: False, {"README.md"})
        self.assertEqual(out["revisions"], {"README.md": 1})
        self.assertEqual(out["commits"]["commits"], 5, "the commit shares are over every commit the header counts")
        windowed = load.parse_unscored_history(LOG, {"window": "2026-03-15"}, lambda p: False, {"README.md"})
        self.assertEqual((windowed["commits"]["commits"], windowed["revisions"]), (2, {"README.md": 1}))


class Loaded(unittest.TestCase):
    def test_a_tree_of_documents_gets_the_line_the_commits_and_the_list(self):
        with tempfile.TemporaryDirectory() as d:
            cov = _docs_report(d)["coverage"]
        self.assertTrue(cov["unranked"])
        self.assertEqual(cov["lines"], {"tracked": 1000, "scored": 100, "documentation": 850, "other_types": 50})
        self.assertEqual(cov["commits"], {"commits": 5, "fixes": 2, "outside": 2, "fixes_outside": 1})
        self.assertEqual(cov["documents"], [{"file": "README.md", "revisions": 3}, {"file": "skills/a/SKILL.md", "revisions": 3}],
                         "ties by path; tests/README.md is a test file before it is a document")

    def test_a_tree_of_code_reads_no_log_and_says_nothing(self):
        with tempfile.TemporaryDirectory() as d:
            report = load.load_report(_out(d, CODE, {"scored": 1, "not a source type": 1}, log="not a log at all\n"))
        self.assertEqual(report["coverage"], {"files": {"scored": 1, "not a source type": 1}, "unranked": False,
                                              "lines": {"tracked": 1000, "scored": 900, "documentation": 100, "other_types": 0}})
        self.assertEqual(render.coverage_phrases(report), [])
        self.assertIsNone(render.scored_phrase(report))
        self.assertIsNone(render.documents_section(report, False))
        self.assertNotIn("documents", [s["id"] for s in render.sections(report, full=False)])

    def test_a_file_scc_counted_that_git_does_not_track_is_not_the_repositorys(self):
        """scc reads the working directory: with --out inside the clone it counted the run's own output while it
        was being written, and the documentation lines differed from one run of a commit to the next."""
        with tempfile.TemporaryDirectory() as d:
            _out(d, {**DOCS, "analysis/report.md": ("Markdown", 7000)}, {"scored": 1, "not a source type": 3, "test file": 1})
            with open(os.path.join(d, "tree.txt"), "wb") as fh:
                fh.write(b"\0".join(p.encode() for p in DOCS) + b"\0")
            cov = load.load_report(d)["coverage"]
        self.assertEqual(cov["lines"], {"tracked": 1000, "scored": 100, "documentation": 850, "other_types": 50})

    def test_a_run_that_recorded_no_coverage_has_none(self):
        with tempfile.TemporaryDirectory() as d:
            _out(d, DOCS, {})
            self.assertEqual(load.load_report(d)["coverage"], {})


class Rendered(unittest.TestCase):
    def test_the_header_says_what_is_ranked_and_which_commits_are_outside_it(self):
        with tempfile.TemporaryDirectory() as d:
            report = _docs_report(d)
            self.assertEqual(render.scored_phrase(report), "1 of 5 files scored")
            self.assertEqual(render.coverage_phrases(report),
                             ["85% of tracked lines are documentation, not ranked", "--file-types all includes them",
                              "40% of commits and 50% of fixes change only unscored files"])
            text = _text(report)
            self.assertIn("│ 1 of 5 files scored  ·  85% of tracked lines are documentation, not ranked", text)
            self.assertIn("40% of commits and 50% of fixes change only unscored files", text)
            full = _text(report, full=True)
            self.assertIn("5 files: 1 scored", full)
            self.assertNotIn("1 of 5 files scored", full, "--full's own coverage line counts the files")
            self.assertIn("85% of tracked lines are documentation", full)
            self.assertIn("85% of tracked lines are documentation", render.markdown(report, []))

    def test_other_types_are_named_when_they_are_the_larger_part(self):
        report = {"coverage": {"unranked": True, "files": {"scored": 2, "not a source type": 8},
                               "lines": {"tracked": 1000, "scored": 200, "documentation": 100, "other_types": 400}}}
        self.assertEqual(render.coverage_phrases(report),
                         ["50% of tracked lines are in file types that are not ranked", "--file-types all includes them"])

    def test_files_no_table_carries_cost_one_fact_and_no_line(self):
        """curl: 1,095 files of other types against 581 scored, yet most of its lines are scored code."""
        files = {"scored": 581, "test file": 2680, "not a source type": 1095, "generated": 13}
        report = {"coverage": {"unranked": False, "files": files, "lines": {"tracked": 100, "scored": 48, "documentation": 19, "other_types": 8}}}
        self.assertTrue(classify.unseen(files))
        self.assertEqual(render.scored_phrase(report), "581 of 4,369 files scored")
        self.assertEqual(render.coverage_phrases(report), [])
        with tempfile.TemporaryDirectory() as d:
            loaded = load.load_report(_out(d, {"app/main.py": ("Python", 900), "a.md": ("Markdown", 100), "b.md": ("Markdown", 100)},
                                           {"scored": 1, "not a source type": 2}))
        self.assertRegex(_text(loaded, width=80), r"│ nothing flagged  ·  1 of 3 files scored +│", "on the tally's line: no line added")
        files["scored"] = 1200
        self.assertFalse(classify.unseen(files), "tests are in the tables, hidden: they are not what is unseen")
        self.assertIsNone(render.scored_phrase(report))
        self.assertIsNone(render.scored_phrase({"coverage": {}}))

    def test_the_documents_follow_the_watch_list_and_claim_no_ranking(self):
        with tempfile.TemporaryDirectory() as d:
            report = _docs_report(d)
            ids = [s["id"] for s in render.sections(report, full=False)]
            self.assertEqual(ids[:2], ["watch", "documents"])
            sec = render.documents_section(report, False)
            self.assertEqual(sec["rows"], [["README.md", "3"], ["skills/a/SKILL.md", "3"]])
            self.assertTrue(sec["caption"].startswith("by changes alone"))
            report["coverage"]["documents"] = [{"file": f"d{i}.md", "revisions": 20 - i} for i in range(12)]
            self.assertEqual(len(render.documents_section(report, False)["rows"]), 5, "a short list")
            self.assertEqual(len(render.documents_section(report, True)["rows"]), 12)
            self.assertNotIn("Most-changed documents", [f["title"] for f in findings.evaluate(report)], "information, not a finding")


def _pool(n: int, **over) -> dict:
    files = {f"src/f{i}.py": {"code": 10, "complexity": 1} for i in range(n)}
    return {"meta": {"file_types": None}, "size": {"files": files}, **over}


class NotComputed(unittest.TestCase):
    def test_a_truck_factor_below_its_floor_says_so(self):
        self.assertEqual(findings.not_computed(_pool(17)),
                         [{"measure": "truck_factor", "label": "truck factor", "files": 17, "min_files": 20, "reason": "17 source files, needs 20"}])
        self.assertEqual(findings.truck_factor_absent(_pool(1))["reason"], "1 source file, needs 20")
        self.assertEqual(render.not_computed_line(_pool(17)), "truck factor not computed: 17 source files, needs 20")
        self.assertEqual(findings.truck_factor(_pool(17, doa=[{"entity": "src/f0.py", "author": "Ann", "is_author": 1}])), [],
                         "the rule and the reason read the same floor")

    def test_nothing_is_said_of_a_truck_factor_that_was_computed_or_could_not_be_counted(self):
        doa = [{"entity": f"src/f{i}.py", "author": "Ann" if i % 2 else "Bob", "is_author": 1, "is_author_decayed": 1} for i in range(20)]
        self.assertIsNone(findings.truck_factor_absent(_pool(20, doa=doa)))
        self.assertIsNone(findings.truck_factor_absent(_pool(20)), "no degree of authorship: an older run, or a step the header names")
        self.assertIsNone(findings.truck_factor_absent({"meta": {}, "size": {"files": {}}}), "no file listing to count by")
        self.assertIsNone(render.not_computed_line(_pool(20, doa=doa)))

    def test_a_pool_mostly_without_authors_says_so(self):
        doa = [{"entity": f"src/f{i}.py", "author": "Ann", "is_author": 1} for i in range(5)]
        absent = findings.truck_factor_absent(_pool(20, doa=doa))
        self.assertEqual(absent["reason"], "15 of the 20 source files have no author on record")
        self.assertEqual(findings.truck_factor(_pool(20, doa=doa)), [])

    def test_the_backtest_is_listed_and_stays_said_under_the_watch_list(self):
        r = _pool(25, meta={"file_types": None, "backtest": {"status": "skipped", "reason": "too little history to backtest"}})
        self.assertEqual([a["measure"] for a in findings.not_computed(r)], ["backtest"])
        self.assertIsNone(render.not_computed_line(r), "one place says it: the caption of the list it would judge")
        r["meta"]["backtest"] = {"status": "timeout"}
        self.assertEqual(findings.not_computed(r)[0]["reason"], "the step timed out")

    def test_the_line_closes_the_findings_panel_and_the_markdown_list(self):
        with tempfile.TemporaryDirectory() as d:
            report = _docs_report(d)
            text = _text(report)
            self.assertIn("· truck factor not computed: 1 source file, needs 20", text)
            self.assertIn("Nothing flagged.", text)
            self.assertIn("- **not computed** truck factor not computed: 1 source file, needs 20", render.markdown(report, []))
            self.assertEqual(render.to_json(report, [])["not_computed"][0]["measure"], "truck_factor")


class Hook(unittest.TestCase):
    def test_a_document_is_not_ranked_which_is_not_safe(self):
        with tempfile.TemporaryDirectory() as d:
            report = _docs_report(d)
            risk = watch.change_risk(report, ["skills/a/SKILL.md", "hooks/hooks.json", "docs/new.md"])
        lines = hook.summary(risk)
        self.assertEqual(lines, ["docs/new.md: not scored: documentation is not ranked",
                                 "hooks/hooks.json: not scored (not a source type)",
                                 "skills/a/SKILL.md: not scored: documentation is not ranked; changed 3 times, one of the most-changed documents",
                                 "total 0.0%; none of these files is scored, so the total says nothing about this change"])
        self.assertTrue(hook.summary(risk, 10)[-1].startswith("total 0.0%, under the 10% threshold; none of these files is scored"))

    def test_a_scored_file_keeps_the_plain_total(self):
        risk = {"files": [{"file": "a.py", "score": 2.0, "reasons": ["changed 3 times"], "rank": 1, "watched": True},
                          {"file": "README.md", "score": 0, "reasons": ["not a source type"], "reason": "not a source type", "rank": None}],
                "total": 2.0, "pool": 4}
        self.assertEqual(hook.summary(risk)[-2:], ["README.md: not scored: documentation is not ranked", "total 2.0%"])
        self.assertEqual(hook.summary({"files": [], "total": 0.0})[-1], "total 0.0%")


if __name__ == "__main__":
    unittest.main()

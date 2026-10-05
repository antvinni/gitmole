"""The default report's short form of a finding (gitmole/brief.py): a count, the rule's numbers, the worst
subject and one step, built from the rule and the evidence. The long statement stays where it was."""
import copy
import io
import os
import re
import unittest

from rich.console import Console

from gitmole import brief, findings, render

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _f(rid, statement, advice, evidence=None, severity="info", title="A title", **rule):
    return findings._f(severity, title, statement, advice, rule={"id": rid, **rule}, evidence=evidence or {})


def _text(f, report=None, width=74, printed=None):
    s = brief.short(f, report, width, printed)
    return "\n".join(s["statement"] + ["  " + x for x in s["subjects"]] + (["↳ " + "\n  ".join(s["step"])] if s["step"] else []))


def _panel(found, report=None, full=False, width=80, printed=None):
    out = io.StringIO()
    Console(file=out, width=width, color_system=None).print(render.findings_panel(found, report or {}, full=full, width=width, printed=printed))
    return out.getvalue()


class Shapes(unittest.TestCase):
    def test_a_go_pseudo_version_keeps_its_base_and_its_commit(self):
        self.assertEqual(brief.short_version("0.307.4-0.20251119130332-1174b0ce4f1f"), "0.307.4-0.…-1174b0ce4f1f")
        self.assertEqual(brief.short_version("fixed in v0.0.0-20260410083055-07c6232d159b)"), "fixed in v0.0.0-…-07c6232d159b)")
        self.assertEqual(brief.short_version("v2.1.0-rc.1.0.20260410083055-07c6232d159b+incompatible"), "v2.1.0-rc.1.0.…-07c6232d159b+incompatible")

    def test_what_is_not_one_is_left_alone(self):
        for text in ("1.82.2", "4.17.21-beta.3", "2026-01-05", "e14795bbf", "0.307.4-0.2025111913033-1174b0ce4f1f", "20251119130332-1174b0ce4f1f"):
            self.assertEqual(brief.short_version(text), text)

    def test_a_line_breaks_at_spaces_only_and_never_starts_with_a_separator(self):
        lines = brief.wrap("7 at 5 or more: a/very/long/path/to/engine.go 10, b.go 9 · 11 at 3 or 4", 30)
        self.assertEqual(lines, ["7 at 5 or more:", "a/very/long/path/to/engine.go 10,", "b.go 9 · 11 at 3 or 4"])
        self.assertTrue(all(not x.startswith("·") for x in brief.wrap("aaaa bbbb · cccc · dddd · eeee", 9)))
        self.assertIn("a/very/long/path/to/engine.go 10,", lines, "the count stays with its file, and the path is whole though longer than a line")

    def test_a_cut_never_falls_between_two_subjects_with_the_same_count(self):
        names, keys = ["a 9", "b 6", "c 6", "d 5", "e 4"], [9, 6, 6, 5, 4]

        def said(k):
            return ", ".join(names[:k]) + (f" and {5 - k} more" if k < 5 else "")
        self.assertEqual(brief.most(5, said, 40, lines=1, keys=keys), ["a 9, b 6, c 6, d 5, e 4"])
        self.assertEqual(brief.most(5, said, 20, lines=1, keys=keys), ["a 9 and 4 more"], "b and c tie: the cut moves back to before both, though b would fit")
        self.assertEqual(brief.most(5, said, 20, lines=1), ["a 9, b 6 and 3 more"], "without counts there is no tie to keep whole")

    def test_the_step_gives_up_its_last_sentences_then_its_last_clauses(self):
        advice = "Do the first thing in the place named here; or do the other thing over there instead. A second sentence that explains why at some length. A third."
        self.assertEqual(brief.step_lines(advice, 200), [advice])
        self.assertEqual(" ".join(brief.step_lines(advice, 50)), "Do the first thing in the place named here; or do the other thing over there instead. A second sentence that explains why at some length.")
        self.assertEqual(" ".join(brief.step_lines(advice, 40)), "Do the first thing in the place named here; or do the other thing over there instead.")
        self.assertEqual(" ".join(brief.step_lines(advice, 30)), "Do the first thing in the place named here.")
        self.assertEqual(len(brief.step_lines(advice, 8)), brief.STEP_LINES)
        self.assertTrue(brief.step_lines(advice, 8)[-1].endswith("…"))


class BugMagnets(unittest.TestCase):
    """prometheus: 18 magnets, 7 of them at the warning threshold of 5, two of those with 6 fixes each."""
    FILES = [("promql/engine.go", 10), ("promql/functions.go", 9), ("tsdb/head.go", 8), ("tsdb/db.go", 8), ("discovery/oci/oci.go", 6),
             ("scrape/scrape_append_v2.go", 6), ("tsdb/head_read.go", 5), ("a.go", 4), ("b.go", 4), ("c.go", 3)]

    def finding(self, files=None, count=18, **evidence):
        files = self.FILES if files is None else files
        return _f("bug_magnets", "18 files were fixed 3 or more times in 6 months: a long list.", "Review promql/engine.go and promql/functions.go before the next release.",
                  {"count": count, "files": [{"file": p, "recent_fixes": n, "fixes": n * 5} for p, n in files], **evidence},
                  min_recent=3, warn_at=5, window_months=6, above_rate={"min_history_months": 12})

    def test_the_parts_sum_to_the_total(self):
        f = self.finding(fix_rate={"fixes": 1726, "changes": 12434, "files": 700, "above_rate": []}, new_in_window=["discovery/oci/oci.go"])
        s = brief.short(f, {}, 100)
        self.assertEqual(s["statement"], ["18 files were fixed 3 or more times in 6 months; no file more often than is usual for its size"])
        self.assertEqual(" ".join(s["subjects"]), "7 at 5 or more: promql/engine.go 10, promql/functions.go 9, tsdb/head.go 8, tsdb/db.go 8, "
                                                  "discovery/oci/oci.go 6 (new in the window), scrape/scrape_append_v2.go 6, tsdb/head_read.go 5 · 11 at 3 or 4")
        self.assertEqual(s["step"], ["Review promql/engine.go and promql/functions.go before the next release."])

    def test_a_list_too_long_for_three_lines_stops_before_a_tie_and_still_sums(self):
        s = brief.short(self.finding(), {}, 60)
        self.assertLessEqual(len(s["subjects"]), 3)
        said = " ".join(s["subjects"])
        self.assertEqual(said, "7 at 5 or more: promql/engine.go 10, promql/functions.go 9, tsdb/head.go 8, tsdb/db.go 8 and 3 more · 11 at 3 or 4",
                         "oci.go fits and scrape_append_v2.go does not, and both were fixed 6 times: neither is named")
        named = said.split(": ")[1].split(" and ")[0].count(",") + 1
        self.assertEqual(named + 3 + 11, 18)

    def test_the_rate_clause_follows_the_evidence(self):
        self.assertEqual(brief.short(self.finding(), {}, 200)["statement"], ["18 files were fixed 3 or more times in 6 months"], "no test, nothing said")
        above = [{"file": "a.go", "fixes": 9, "changes": 10, "size_rate": 0.1}]
        self.assertIn("; 1 more often than is usual for its size", brief.short(self.finding(fix_rate={"above_rate": above}), {}, 200)["statement"][0])
        short = brief.short(self.finding(fix_rate={"not_run": "history too short", "history_months": 7}), {}, 200)["statement"][0]
        self.assertIn("; raw counts, as the test against files of their size needs 12 months of history", short)

    def test_ten_named_all_at_the_threshold_with_more_behind_them_claims_no_split(self):
        ten = [(f"f{i}.go", 20 - i) for i in range(10)]
        s = brief.short(self.finding(files=ten, count=25), {}, 200)
        self.assertEqual(s["subjects"], ["Most fixed: " + ", ".join(f"f{i}.go {20 - i}" for i in range(10)) + " and 15 more"],
                         "the evidence stops at ten: how many of the other 15 are at 5 or more is not known here")

    def test_none_at_the_threshold_and_a_single_file(self):
        s = brief.short(self.finding(files=[("a.go", 4), ("b.go", 3)], count=2), {}, 200)
        self.assertEqual(s["subjects"], ["Most fixed: a.go 4, b.go 3"])
        one = brief.short(self.finding(files=[("a.go", 7)], count=1), {}, 200)
        self.assertEqual((one["statement"], one["subjects"]), (["1 file was fixed 3 or more times in 6 months"], ["1 at 5 or more: a.go 7"]))

    def test_a_finding_without_its_evidence_keeps_its_statement(self):
        f = {"severity": "warning", "title": "Bug magnets", "detail": "Bug magnets detail act", "advice": "act", "rule": {"id": "bug_magnets"}}
        self.assertEqual(brief.short(f, {}, 80), {"statement": ["Bug magnets detail"], "subjects": [], "step": ["act"]})


class SeeSection(unittest.TestCase):
    """The pointer names a section only when it is this finding's own subject table, printed in this report,
    with the subject in it: Brain methods to Complex functions, tight coupling to Change coupling."""
    FUNCS = [{"file": "discovery/aws/rds.go", "function": "errg.Go(func() error {", "start": 542, "ccn": 166, "lines": 482, "params": 0},
             {"file": "tsdb/wlog/checkpoint.go", "function": "Checkpoint", "start": 112, "ccn": 74, "lines": 273, "params": 7}]

    def brain(self, funcs=None, count=62, partial=False):
        funcs = funcs or self.FUNCS
        which = "the anonymous function at discovery/aws/rds.go:542" if funcs is self.FUNCS else f"{funcs[0]['function']} in {funcs[0]['file']}"
        return _f("brain_methods", "62 functions are both long and complex: a; b; c; d; e and 57 more.", f"Split {which} first, before the next change lands there.",
                  {"count": count, "partial": partial, "functions": funcs}, severity="warning", title="Brain methods", min_ccn=15, min_lines=100)

    def test_brain_methods_points_at_the_table_that_lists_them(self):
        printed = {"functions": {"rows": [["<anonymous>", "discovery/aws/rds.go:542", "166", "482", "0"]]}}
        self.assertEqual(_text(self.brain(), {}, 200, printed),
                         "62 functions have 100 lines or more and complexity 15 or more. Worst: the anonymous function at discovery/aws/rds.go:542 (see Complex functions)\n"
                         "↳ Split it first, before the next change lands there.")

    def test_without_the_table_or_without_the_row_the_numbers_are_said_instead(self):
        for printed in (None, {}, {"functions": {"rows": []}}, {"functions": {"rows": [["Checkpoint", "tsdb/wlog/checkpoint.go", "74", "273", "7"]]}},
                        {"coupling": {"rows": [["<anonymous>", "discovery/aws/rds.go:542"]]}}):
            text = _text(self.brain(), {}, 200, printed)
            self.assertNotIn("(see", text)
            self.assertIn("Worst: the anonymous function at discovery/aws/rds.go:542, complexity 166, 482 lines", text)

    def test_a_named_function_one_function_and_a_partial_run(self):
        named = self.brain(funcs=self.FUNCS[1:], count=1, partial=True)
        self.assertEqual(_text(named, {}, 200), "1 function has 100 lines or more and complexity 15 or more. Worst: Checkpoint in tsdb/wlog/checkpoint.go, complexity 74, 273 lines. "
                                                "The function step stopped part way, so there may be more\n↳ Split it first, before the next change lands there.")

    def pair(self, pairs=None, clusters=None):
        pairs = [{"a": "web/ui/src/promql/format.tsx", "b": "web/ui/src/promql/serialize.ts", "degree": 86, "revs": 7}] if pairs is None else pairs
        advice = (f"Review {pairs[0]['a']} and {pairs[0]['b']} first: a shared layout or a hidden dependency links them." if not clusters
                  else "Review gen/ first: 12 files change as one; a generator or a shared layout links them.")
        return _f("tight_coupling", "1 pair changes together at least 80% of the time: a + b (86%).", advice, {"clusters": clusters or [], "pairs": pairs},
                  title="Files that always change together", min_degree=80, min_revs=5)

    def test_a_pair_in_one_directory_names_the_directory_once_and_points_at_change_coupling(self):
        printed = {"coupling": {"rows": [["web/ui/src/promql/{format.tsx,serialize.ts}", "86%"]]}}
        self.assertEqual(_text(self.pair(), {}, 200, printed),
                         "1 pair changes together 80% of the time or more: format.tsx and serialize.ts in web/ui/src/promql/, 86% (see Change coupling)\n"
                         "↳ Look for a shared layout or a hidden dependency between the two.")
        self.assertNotIn("(see", _text(self.pair(), {}, 200, {"coupling": {"rows": [["{x.py,y.py}", "90%"]]}}), "the table is there and the pair is not in it")
        self.assertNotIn("(see", _text(self.pair(), {}, 200, {"functions": {"rows": [["web/ui/src/promql/format.tsx", "web/ui/src/promql/serialize.ts"]]}}))

    def test_several_pairs_two_directories_and_a_count_at_the_evidence_s_cap(self):
        pairs = [{"a": "api/a.py", "b": "db/b.py", "degree": 95, "revs": 9}, {"a": "c.py", "b": "d.py", "degree": 81, "revs": 6}]
        self.assertTrue(_text(self.pair(pairs), {}, 200).startswith("2 pairs change together 80% of the time or more. Highest: api/a.py and db/b.py, 95%\n"))
        self.assertTrue(_text(self.pair(pairs * 5), {}, 200).startswith("10 or more pairs change together"), "the evidence names ten at most")
        self.assertEqual(brief._pair_words("a.py", "b.py"), "a.py and b.py", "two root files have no directory to name")

    def test_a_directory_that_changes_as_one(self):
        groups = [{"dir": "gen/", "files": 12, "pairs": 60, "degree": 83}, {"dir": "api/", "files": 4, "pairs": 6, "degree": 90}]
        f = self.pair(pairs=[{"a": "x.py", "b": "y.py", "degree": 88, "revs": 5}], clusters=groups)
        printed = {"coupling": {"rows": [["gen/ (12 files)", "each other", "≥83%"]]}}
        self.assertEqual(_text(f, {}, 200, printed), "The files of 2 directories and 1 more pair change together 80% of the time or more. Largest: 12 files in gen/ (see Change coupling)\n"
                                                    "↳ Review gen/ first: 12 files change as one; a generator or a shared layout links them.")
        self.assertEqual(brief.short(self.pair(pairs=[], clusters=groups[:1]), {}, 200)["statement"], ["The files of 1 directory change together 80% of the time or more. 12 files in gen/"])


class CredentialFiles(unittest.TestCase):
    """"The secrets scan found no value in it" joins two steps, so it is said only when the secrets step ran to
    its end and holds no row for the path; the step is conditional under the same condition."""
    def finding(self, paths=("web/ui/react-app/.env",)):
        return findings.credential_files({"meta": {"credential_files": list(paths)}})[0]

    def report(self, paths=("web/ui/react-app/.env",), **kw):
        return {"meta": {"credential_files": list(paths), "steps": {"betterleaks": "run"}}, "secrets_scanned": True, "secrets": [], **kw}

    def test_scanned_and_no_row_for_the_path(self):
        self.assertEqual(_text(self.finding(), self.report(secrets=[{"rule": "x", "file": "testdata/key.pem", "commit": "c", "line": 1}]), 200),
                         "1 file, matched by name: web/ui/react-app/.env. The secrets scan found no value in it, at HEAD or in history\n"
                         "↳ If it holds a login, move the values to the environment and git rm the file; a template belongs in .env.example.")

    def test_the_clause_is_absent_when_the_scan_did_not_run_did_not_finish_or_has_a_row(self):
        row = {"rule": "generic-api-key", "file": "web/ui/react-app/.env", "commit": "c1", "line": 2, "placeholder": True}
        for report in (None, {}, self.report(secrets_scanned=False), self.report(secrets=[row]),
                       {**self.report(), "meta": {"credential_files": ["web/ui/react-app/.env"], "steps": {"betterleaks": "timeout"}}}):
            text = _text(self.finding(), report, 200)
            self.assertEqual(text, "1 file, matched by name: web/ui/react-app/.env\n"
                                   "↳ Move the values to the environment, git rm the files and add them to .gitignore; a template belongs in .env.example.", report)

    def test_several_files_are_subject_lines_and_one_row_among_them_withholds_the_clause(self):
        paths = [f"deploy/{i}/.env.production" for i in range(12)]
        s = brief.short(self.finding(paths), self.report(paths), 74)
        self.assertEqual(" ".join(s["statement"]), "12 files, matched by name. The secrets scan found no value in them, at HEAD or in history")
        self.assertLessEqual(len(s["subjects"]), 3)
        self.assertTrue(s["subjects"][-1].endswith(" more"))
        self.assertEqual(" ".join(s["step"]), "If one holds a login, move the values to the environment and git rm the files; a template belongs in .env.example.")
        dirty = self.report(paths, secrets=[{"rule": "x", "file": paths[11], "commit": "c", "line": 1}])
        self.assertEqual(brief.short(self.finding(paths), dirty, 74)["statement"], ["12 files, matched by name"], "the twelfth is past the evidence's ten and still counts")
        self.assertEqual(brief.short(self.finding(paths), {"secrets_scanned": True, "secrets": []}, 74)["statement"], ["12 files, matched by name"],
                         "without the run's own list the two past the evidence cannot be vouched for")


class Vulnerable(unittest.TestCase):
    def row(self, name, version, source, score=7.5, fixed="9.9.9", **kw):
        return {"name": name, "version": version, "ecosystem": "npm", "source": source, "ids": ["GHSA-x"], "aliases": ["CVE-2026-1"], "advisories": 1,
                "score": score, "severity": "high", "summary": "", "fixed": fixed, "malicious": False, **kw}

    def report(self, rows):
        return {"meta": {"name": "r"}, "dependencies": {"status": "scanned", "sources": [{"path": r["source"], "packages": 10} for r in rows], "packages": 99, "vulnerable": rows}}

    def test_the_count_the_lock_files_the_package_the_advice_names_and_the_step(self):
        rows = [self.row("example.org/own/module", "0.307.4-0.20251119130332-1174b0ce4f1f", "compliance/go.mod", fixed="0.311.2-0.20260410083055-07c6232d159b", imported=True),
                self.row("websocket-driver", "0.7.4", "web/pnpm-lock.yaml", score=9.2, fixed="0.7.5", runtime=False, imported=False),
                self.row("moment", "2.30.1", "web/pnpm-lock.yaml", score=5.9, fixed="2.31.0"), self.row("moment", "2.30.1", "console/pnpm-lock.yaml", score=5.9, fixed="2.31.0")]
        r = self.report(rows)
        [f] = findings.vulnerable_dependencies(r)
        self.assertIn("0.307.4-0.20251119130332-1174b0ce4f1f", f["detail"], "the long statement keeps the version whole")
        self.assertEqual(_text(f, r, 200), "3 packages in 4 places across 3 lock files\n"
                                           "  Highest: websocket-driver 0.7.4 (CVE-2026-1), CVSS 9.2, fixed in 0.7.5, a dev dependency nothing imports, in web/pnpm-lock.yaml; "
                                           "a warning, not critical, as nothing beside it declares a deployment\n"
                                           "↳ Upgrade websocket-driver to 0.7.5 in web/pnpm-lock.yaml first; it scores CVSS 9.2, the highest with a fix published. "
                                           "One that does not apply to this code can be ignored in osv-scanner.toml.")
        narrow = brief.short(f, r, 74)
        self.assertLessEqual(len(narrow["subjects"]), 3)
        self.assertNotIn("…", " ".join(narrow["subjects"]), "the reason gives way whole before the package's facts are cut")

    def test_a_pseudo_version_is_short_on_both_sides_in_the_default_form_only(self):
        r = self.report([self.row("example.org/own/module", "0.307.4-0.20251119130332-1174b0ce4f1f", "compliance/go.mod", fixed="0.311.2-0.20260410083055-07c6232d159b")])
        [f] = findings.vulnerable_dependencies(r)
        before = copy.deepcopy(f)
        text = _text(f, r, 200)
        self.assertEqual(text, "1 package in compliance/go.mod\n  example.org/own/module 0.307.4-0.…-1174b0ce4f1f (CVE-2026-1), CVSS 7.5, fixed in 0.311.2-0.…-07c6232d159b\n"
                               "↳ Upgrade example.org/own/module to 0.311.2-0.…-07c6232d159b in compliance/go.mod first; it scores CVSS 7.5. "
                               "One that does not apply to this code can be ignored in osv-scanner.toml.")
        self.assertEqual(f, before, "the finding the JSON, the Markdown and --full read is not written to")
        self.assertIn("0.311.2-0.20260410083055-07c6232d159b", _panel([f], r, full=True, width=200))
        self.assertNotIn("20260410083055", _panel([f], r, full=False, width=200))

    def test_the_note_for_example_lock_files_is_one_sentence_and_no_step(self):
        rows = [self.row("google.golang.org/grpc", "1.82.1", "documentation/examples/remote_storage/go.mod", score=8.7, fixed="1.82.2"),
                self.row("golang.org/x/crypto", "0.54.0", "documentation/examples/remote_storage/go.mod", score=None, fixed="0.55.0")]
        r = self.report(rows)
        [f] = findings.vulnerable_dependencies(r)
        s = brief.short(f, r, 74)
        self.assertEqual(s, {"statement": ["2 packages in documentation/examples/remote_storage/go.mod. Highest:",
                                           "google.golang.org/grpc 1.82.1 (CVE-2026-1), CVSS 8.7, fixed in 1.82.2"], "subjects": [], "step": []})
        self.assertEqual(len(_panel([f], r).splitlines()), 2 + 3, "its own entry in three lines")

    def test_no_fix_a_requirement_range_and_a_finding_without_its_report(self):
        r = self.report([self.row("left-pad", "1.0.0", "package-lock.json", score=None, fixed=None, imported=False)])
        [f] = findings.vulnerable_dependencies(r)
        self.assertEqual(brief.short(f, r, 200)["subjects"], ["left-pad 1.0.0 (CVE-2026-1), no fix published, imported by no tracked file"])
        self.assertTrue(brief.short(f, {}, 200)["statement"][0].startswith("1 vulnerable package in 1 lock file: left-pad 1.0.0 (CVE-2026-1, "),
                        "the rows are the run's: without them the statement stands")
        r = self.report([self.row("mcp", "1.0.0", "requirements.txt", fixed="1.2.0", requirement=">=1.0.0", pinned=False)])
        [f] = findings.vulnerable_dependencies(r)
        self.assertEqual(brief.short(f, r, 200)["statement"] + brief.short(f, r, 200)["subjects"],
                         ["1 requirement range admits a vulnerable version in requirements.txt", "mcp>=1.0.0, whose floor is 1.0.0 (CVE-2026-1), CVSS 7.5, fixed in 1.2.0"])


class OtherForms(unittest.TestCase):
    def test_sweeping_commits_counts_them_all_and_names_the_largest(self):
        swept = [{"hash": f"c{i:08x}", "date": "2024-09-09", "files": 49 + i, "added": 9, "deleted": 9, "subject": "chore: sweep"} for i in range(17)]
        swept.insert(0, {"hash": "e14795bbf", "date": "2026-01-05", "files": 587, "added": 588, "deleted": 588, "subject": "Remove copyright date from headers (#17785)"})
        r = {"activity": {"sweeping": swept + [{"hash": "d0", "date": "2020-01-01", "files": 900, "declared": True}], "ignored_revs": 1}}
        [f] = findings.sweeping_commits(r)
        self.assertEqual(len(f["evidence"]["commits"]), 10, "the evidence stops at ten, the count does not")
        self.assertEqual(_text(f, r, 200), "18 commits each touch 49 files or more and take out as many lines as they put in. Largest: e14795bbf, 587 files, 2026-01-05\n"
                                           "↳ Add them to .git-blame-ignore-revs so git blame and GitHub skip them too; 1 commit is declared there already.")
        one = {"activity": {"sweeping": swept[:1]}}
        self.assertEqual(_text(findings.sweeping_commits(one)[0], one, 200), "1 commit touches 587 files and takes out as many lines as it puts in: e14795bbf, 2026-01-05\n"
                                                                             "↳ Add it to .git-blame-ignore-revs so git blame and GitHub skip it too.")
        self.assertIn("Remove copyright date", _text(f, {}, 200), "without the run the statement stands")

    def unused(self, rows, count=None):
        return _f("unused_dependencies", "3 runtime dependencies are declared and never imported: a long list.",
                  f"Remove {rows[0]['package']} from {rows[0]['manifest']} if nothing loads it at run time; an unused dependency is still installed, scanned and updated.",
                  {"count": count or len(rows), "manifests": 9, "unused": rows})

    def test_unused_dependencies_names_the_one_the_step_names(self):
        rows = [{"manifest": "web/mantine-ui/package.json", "package": "lodash"}, {"manifest": "web/react-app/package.json", "package": "downshift"},
                {"manifest": "web/react-app/package.json", "package": "x"}]
        self.assertEqual(_text(self.unused(rows), {}, 200), "3 runtime dependencies: lodash in web/mantine-ui/package.json and 2 more in web/react-app/package.json\n"
                                                            "↳ Remove lodash if nothing loads it at run time.")
        self.assertEqual(brief.short(self.unused(rows[:1]), {}, 200)["statement"], ["1 runtime dependency: lodash in web/mantine-ui/package.json"])
        self.assertEqual(brief.short(self.unused(rows[1:]), {}, 200)["statement"], ["2 runtime dependencies: downshift and 1 more in web/react-app/package.json"])
        self.assertEqual(brief.short(self.unused(rows, count=14), {}, 200)["statement"], ["14 runtime dependencies: lodash in web/mantine-ui/package.json and 13 more"],
                         "past the evidence's ten nothing says where the rest are")
        mixed = rows + [{"manifest": "go.mod", "package": "example.org/y"}]
        self.assertEqual(brief.short(self.unused(mixed), {}, 200)["statement"], ["4 runtime dependencies: lodash in web/mantine-ui/package.json and 3 more"])


class TruckFactor(unittest.TestCase):
    """prometheus: a truck factor of 9, one of the nine gone, and three areas where one person is enough."""
    PEOPLE = ["Ann", "Bob", "Cy", "Di", "Ed", "Flo", "Gus", "Hal", "Ida"]

    def report(self, gone=("Hal",)):
        authors = {p: {"last": "2019-01-01" if p in gone else "2026-09-01"} for p in self.PEOPLE + ["Zed"]}
        return {"meta": {"name": "r", "last_date": "2026-09-18", "now": "2026-09-18"}, "activity": {"authors": authors}}

    def finding(self, tf=9, areas=None, advice="Pair someone with Ann on web/ first; they author most of what would be left without an author.", **rule):
        areas = [{"area": "web/", "author": "Ann", "files": 231, "orphaned": 128}, {"area": "plugins/", "author": "Zed", "files": 27, "orphaned": 24},
                 {"area": "prompb/", "author": "Hal", "files": 10, "orphaned": 7, "new_since": "2026-03"}] if areas is None else areas
        return _f("truck_factor", "Truck factor 9: without Ann, Bob, Cy, Di, Ed, Flo, Gus, Hal (gone) and Ida, 333 of the 653 source files (51%) have no author left. "
                                  "For those marked gone it already has. With knowledge halving every 5 months it is 12, adding X, Y and Z. Areas with a truck factor of one: web/ (Ann).",
                  advice, {"truck_factor": tf, "removed": self.PEOPLE[:tf], "truck_factor_decayed": 12, "removed_decayed": self.PEOPLE, "files": 653, "orphaned": 333, "areas": areas},
                  title="Truck factor", **rule)

    def test_it_leads_with_what_the_number_means_and_keeps_the_areas_of_one(self):
        text = _text(self.finding(), self.report(), 200)
        self.assertEqual(text, "9 people would have to leave before 333 of the 653 source files (51%) had no author left; 1 of the 9 is already gone\n"
                               "  In 3 areas one person leaving would be enough: web/ (Ann), plugins/ (Zed) and prompb/ (Hal gone, new since 2026-03)\n"
                               "↳ Pair someone with Ann on web/ first: 128 of its 231 files would have no author left.")
        self.assertNotIn("halving", text)
        self.assertNotIn("Bob", text, "nine names are the People table's to give")

    def test_few_people_are_named_and_one_person_is_said_as_one(self):
        self.assertEqual(brief.short(self.finding(tf=2, areas=[]), self.report(), 200)["statement"],
                         ["2 people (Ann and Bob) would have to leave before 333 of the 653 source files (51%) had no author left"])
        self.assertEqual(brief.short(self.finding(tf=1, areas=[]), self.report(gone=("Ann",)), 200)["statement"],
                         ["1 person, Ann, would have to leave before 333 of the 653 source files (51%) had no author left; they are already gone"])
        self.assertTrue(brief.short(self.finding(tf=2, areas=[]), self.report(gone=("Ann", "Bob")), 200)["statement"][0].endswith("; all 2 are already gone"))

    def test_areas_past_three_lines_are_counted_and_a_capped_list_claims_no_total(self):
        many = [{"area": f"services/component-{i}/", "author": "Ann", "files": 20, "orphaned": 11} for i in range(9)]
        s = brief.short(self.finding(areas=many), self.report(), 74)
        self.assertLessEqual(len(s["subjects"]), 3)
        self.assertRegex(" ".join(s["subjects"]), r"^In 9 areas one person leaving would be enough: services/component-0/ \(Ann\), .* and \d more$")
        ten = brief.short(self.finding(areas=many + many[:1]), self.report(), 400)["subjects"][0]
        self.assertTrue(ten.startswith("In 10 or more areas one person leaving would be enough: "))
        self.assertTrue(ten.endswith(" and more"))

    def test_other_advice_stands_and_a_merged_or_reportless_finding_keeps_its_statement(self):
        gone = "Everyone who authors these files has stopped committing; give the files owners, starting with the ones changed most."
        self.assertEqual(brief.short(self.finding(advice=gone), self.report(), 200)["step"], [gone])
        new = self.finding(advice="Pair someone with Hal on prompb/ first; they author most of what would be left without an author.")
        self.assertEqual(brief.short(new, self.report(), 200)["step"], ["Pair someone with Hal on prompb/ first; they author most of what would be left without an author."])
        for f, report in ((self.finding(measures={"knowledge_islands": {}}), self.report()), (self.finding(), {})):
            self.assertTrue(brief.short(f, report, 400)["statement"][0].startswith("Truck factor 9: without Ann"))


class Fallback(unittest.TestCase):
    """A rule with no short form of its own: whole when short, else the lead and three lines of its list."""
    def test_a_statement_of_three_lines_or_fewer_is_printed_whole(self):
        f = _f("repo_policy", "No licence file at the root; no security policy (SECURITY.md).", "Add a LICENSE; without one nobody may reuse the code.")
        self.assertEqual(brief.short(f, {}, 74), {"statement": ["No licence file at the root; no security policy (SECURITY.md)"], "subjects": [],
                                                  "step": ["Add a LICENSE; without one nobody may reuse the code."]})

    def test_a_long_list_keeps_its_lead_and_counts_what_it_drops_with_what_was_counted_already(self):
        items = [f"commit{i:02d} (25 files, 6 directories, a subject that lists several changes at once)" for i in range(3)]
        f = _f("tangled_commits", f"97 of 5,000 commits (2%) touch 10 or more files across 4 or more directories: {'; '.join(items)} and 94 more. "
                                  "A fix among them credits every file it touched.", "Split a change that does several things before merge.")
        s = brief.short(f, {}, 74)
        self.assertEqual(" ".join(s["statement"]), "97 of 5,000 commits (2%) touch 10 or more files across 4 or more directories:")
        self.assertEqual(len(s["subjects"]), 3)
        self.assertEqual(" ".join(s["subjects"]), "commit00 (25 files, 6 directories, a subject that lists several changes at once); "
                                                  "commit01 (25 files, 6 directories, a subject that lists several changes at once) and 95 more", "one dropped here and the 94 the statement counted")
        self.assertNotIn("credits every file", " ".join(s["subjects"]), "the sentences after the list are --full's")

    def test_a_list_without_a_lead_and_one_entry_longer_than_the_cap(self):
        parts = [f"deploy/environments/region-{i}/service.lock resolved a package from a registry the configuration does not name" for i in range(6)]
        s = brief.short(_f("dependency_confusion", "; ".join(parts) + ".", "Use one index per package."), {}, 74)
        self.assertEqual(s["statement"], ["deploy/environments/region-0/service.lock resolved a package from a", "registry the configuration does not name and 5 more"],
                         "the second entry would be a fourth line, so the list stops after the first")
        self.assertEqual(s["subjects"], [], "with no lead the entries are the statement")
        one = brief.short(_f("hidden_coupling", " ".join(["word"] * 120) + ".", "Look."), {}, 74)
        self.assertEqual(len(one["statement"]), 3)
        self.assertTrue(one["statement"][-1].endswith("…"))

    def test_the_baseline_mark_stays_in_front(self):
        f = _f("bus_factor", "Ann wrote 80% of the code that survives today.", "Pair someone with Ann before they are unavailable.")
        f["detail"] = "In the baseline: " + f["detail"]
        self.assertEqual(brief.short(f, {}, 74)["statement"], ["In the baseline: Ann wrote 80% of the code that survives today"])
        magnets = BugMagnets().finding()
        magnets["detail"] = "In the baseline: " + magnets["detail"]
        self.assertTrue(brief.short(magnets, {}, 200)["statement"][0].startswith("In the baseline: 18 files were fixed"))

    def test_every_rule_the_code_can_produce_keeps_to_the_caps(self):
        """Each rule id in findings.py, given a statement and a step far past the caps and
        no evidence to read: no line over the width, three subject lines and three step lines at most."""
        with open(os.path.join(ROOT, "gitmole", "findings.py"), encoding="utf-8") as fh:
            source = fh.read()
        ids = sorted(set(re.findall(r'"id": "([a-z_]+)"', source)) | set(brief.FORMS))
        self.assertGreater(len(ids), 40)
        self.assertTrue(set(brief.FORMS) <= set(ids), "a short form for a rule that does not exist")
        listing = "; ".join(f"src/package{i}/module{i}.py (a reason given at some length, {i} times over)" for i in range(12))
        for rid in ids:
            for evidence in ({}, {"count": 3}):
                f = _f(rid, f"12 things were found by a rule with a threshold of 5 or more: {listing} and 30 more. A closing sentence.",
                       "Do the first thing first, in the place the rule names, and then the next thing; " * 6 + "then stop. And one more sentence.", evidence)
                for width in (40, 74, 100):
                    s = brief.short(f, {}, width)
                    self.assertTrue(s["statement"] and s["step"], rid)
                    self.assertLessEqual(len(s["subjects"]), brief.SUBJECT_LINES, rid)
                    self.assertLessEqual(len(s["step"]), brief.STEP_LINES, rid)
                    self.assertTrue(all(len(x) <= width for x in s["statement"] + s["subjects"] + s["step"]), (rid, width, s))


class Panel(unittest.TestCase):
    def found(self):
        return [BugMagnets().finding(fix_rate={"above_rate": []}), SeeSection().brain()]

    def test_the_default_report_is_short_and_full_keeps_the_enumeration(self):
        found = self.found()
        before = copy.deepcopy(found)
        default, full = _panel(found), _panel(found, full=True)
        self.assertIn("7 at 5 or more: promql/engine.go 10", default)
        self.assertIn("│     7 at 5 or more", default, "subject lines at column 5")
        self.assertIn("│   ↳ Review promql/engine.go", default)
        self.assertNotIn("7 at 5 or more", full)
        self.assertIn("62 functions are both long and complex: a; b; c; d; e and 57 more", full)
        self.assertIn("a long list", full)
        self.assertEqual(found, before)
        self.assertEqual(render.to_json({"meta": {}}, found)["findings"], before, "no key is added to what the JSON exports")

    def test_no_line_is_longer_than_the_terminal_and_a_step_s_second_line_is_indented(self):
        f = _f("pwn_request", "1 checkout step under pull_request_target fetches the pull request's head: job build in .github/workflows/ci.yml, line 12 (ref: head.sha).",
               "Build the pull request in a workflow on pull_request, which gets no secrets, and hand its results to the privileged one as an artifact it reads as data; "
               "or drop the ref: in .github/workflows/ci.yml so the checkout is the base branch.", severity="warning")
        for width in (60, 80, 100, 160):
            lines = _panel(self.found() + [f], width=width).splitlines()
            self.assertTrue(all(len(x) == width for x in lines), width)
        text = _panel([f], width=80)
        self.assertIn("│   ↳ Build the pull request in a workflow on pull_request, which gets no", text)
        self.assertIn("│     secrets, and hand its results", text)
        self.assertLessEqual(sum(1 for x in text.splitlines() if "↳" in x or x.startswith("│     ")), 3)
        wide = _panel(self.found(), width=200).splitlines()
        self.assertLessEqual(max(len(x.rstrip("│ ")) for x in wide if x.startswith("│")), 100 + 4, "prose stays within 100 characters on a wide terminal")

    def test_findings_sharing_a_title_show_three_and_count_the_rest(self):
        same = [_f("placeholder_identity", f"\"user{i} <user{i}@localhost>\" made 30 commits (3%).", "Set user.name and user.email.", severity="warning", title="Unconfigured git identity")
                for i in range(5)]
        text = _panel(same)
        self.assertIn("Unconfigured git identity (5)", text)
        self.assertIn("user2 <user2@localhost>", text)
        self.assertNotIn("user3", text)
        self.assertIn("│   and 2 more", text)
        self.assertEqual(text.count("↳"), 1, "the same step once")


if __name__ == "__main__":
    unittest.main()

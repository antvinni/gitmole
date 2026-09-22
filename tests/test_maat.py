import json
import math
import os
import tempfile
import unittest

from gitmole import maat

LOG = """--a1--2026-01-10T09:15:00+00:00--Ann--feat: initial layout
3\t1\tsrc/a.py
2\t0\tsrc/b.py

--b2--2026-02-10T14:00:00+00:00--Bob--Add logo -- and docs
1\t1\tsrc/a.py
5\t5\tsrc/b.py
-\t-\timg/logo.png

--c3--2026-03-10T09:30:00+00:00--Ann--fix(core): crash on empty input
4\t0\tsrc/a.py
1\t0\tsrc/c.py

--d4--2026-03-12T22:00:00+00:00--Ann--Refactor helpers
1\t0\tsrc/a.py
1\t0\tsrc/b.py

--e5--2026-04-01T09:00:00+00:00--Ann--Fixed the off-by-one in b
1\t0\tsrc/a.py
1\t0\tsrc/b.py

--f6--2026-04-02T09:45:00+00:00--Ann--prefix cleanup
1\t0\tsrc/a.py
1\t0\tsrc/b.py

--g7--2026-04-03T11:00:00+00:00--Cat--Hotfix: regression in a
0\t2\tsrc/a.py
0\t1\tsrc/b.py
"""


class ParseLog(unittest.TestCase):
    def test_commits_with_files_and_binary_entries(self):
        commits = maat.parse_log(LOG)
        self.assertEqual(len(commits), 7)
        self.assertEqual(commits[0]["author"], "Ann")
        self.assertEqual(commits[0]["date"], "2026-01-10")
        self.assertEqual(commits[0]["time"], "2026-01-10T09:15:00+00:00")
        self.assertEqual(commits[0]["subject"], "feat: initial layout")
        self.assertEqual(commits[1]["subject"], "Add logo -- and docs", "double dashes inside a subject survive")
        self.assertEqual(commits[0]["files"], [("src/a.py", 3, 1), ("src/b.py", 2, 0)])
        self.assertEqual(commits[1]["files"][2], ("img/logo.png", 0, 0))

    def test_renames_are_followed_to_the_new_path_and_a_pure_move_adds_no_lines(self):
        # `git log -M --numstat` spells a rename three ways; the mover is not the owner of what moved
        log = ("--d63e94f5--2023-08-13T10:00:00+00:00--Nate--Move to src layout\n"
               "0\t0\t{requests => src/requests}/__init__.py\n"
               "4\t7\tSECURITY.md => .github/SECURITY.md\n"
               "0\t0\tCODE_OF_CONDUCT.md => .github/CODE_OF_CONDUCT.md\n"
               "2\t0\tsrc/requests/{models.py => models_v2.py}\n"
               "1\t1\tMakefile\n")
        commits = maat.parse_log(log, types=None)
        self.assertEqual(commits[0]["files"], [("src/requests/__init__.py", 0, 0), (".github/SECURITY.md", 4, 7),
                                                (".github/CODE_OF_CONDUCT.md", 0, 0), ("src/requests/models_v2.py", 2, 0), ("Makefile", 1, 1)])

    def test_subjects_with_exotic_line_break_characters_do_not_split_the_log(self):
        # U+2028 and form feed are line breaks to str.splitlines but not to git
        text = "--x--2026-05-04T10:00:00+00:00--Ann--Fix\u2028broken\x0cthing\n1\t0\tf.py\n"
        commits = maat.parse_log(text)
        self.assertEqual(len(commits), 1)
        self.assertEqual(commits[0]["files"], [("f.py", 1, 0)])
        self.assertTrue(maat.is_fix(commits[0]["subject"]))

    def test_old_logs_without_subjects_still_parse(self):
        commits = maat.parse_log("--x--2026-05-04--Ann\n1\t0\tf.py\n")
        self.assertEqual(commits[0]["subject"], "")
        self.assertEqual(commits[0]["files"], [("f.py", 1, 0)])


class QuotedPathsInLog(unittest.TestCase):
    def test_paths_are_unquoted_when_parsed(self):
        text = '--x--2026-05-04T10:00:00+00:00--Ann--s\n1\t0\t"src/\\303\\244.py"\n2\t0\t"say \\"hi\\".py"\n'
        commits = maat.parse_log(text, types=None)
        self.assertEqual([p for p, _, _ in commits[0]["files"]], ["src/\u00e4.py", 'say "hi".py'])

    def test_csv_files_are_written_as_utf8_regardless_of_locale(self):
        with tempfile.TemporaryDirectory() as d:
            log = os.path.join(d, "log.txt")
            with open(log, "w", encoding="utf-8") as fh:
                fh.write("--x--2026-05-04T10:00:00+00:00--\u00c5nn--s\n1\t0\tsrc/\u4e2d.py\n")
            maat.write_all(log, d, types=None)
            with open(os.path.join(d, "maat-entity-ownership.csv"), "rb") as fh:
                raw = fh.read()
        self.assertIn("src/\u4e2d.py".encode("utf-8"), raw)
        self.assertIn("\u00c5nn".encode("utf-8"), raw)


class Revisions(unittest.TestCase):
    def test_counts_commits_per_entity(self):
        rows = maat.revisions(maat.parse_log(LOG))
        self.assertEqual(rows[0], {"entity": "src/a.py", "n-revs": 7})
        self.assertEqual(dict((r["entity"], r["n-revs"]) for r in rows)["src/c.py"], 1)


class Plumbing(unittest.TestCase):
    def _commits(self, path, tiny, big):
        out = [{"hash": f"t{i}", "date": "2026-01-01", "time": "", "author": "A", "subject": "bump", "files": [(path, 1, 1)]} for i in range(tiny)]
        out += [{"hash": f"b{i}", "date": "2026-01-01", "time": "", "author": "A", "subject": "work", "files": [(path, 40, 12)]} for i in range(big)]
        return out

    def test_a_file_whose_commits_nearly_always_change_a_line_or_two_is_plumbing(self):
        commits = self._commits("fastapi/__init__.py", tiny=300, big=31) + self._commits("fastapi/routing.py", tiny=10, big=90) + self._commits("VERSION", tiny=5, big=0)
        rows = maat.plumbing(commits)
        self.assertEqual(rows, [{"entity": "fastapi/__init__.py", "n-revs": 331, "tiny-revs": 300}],
                         "routing.py has real edits; VERSION has too few commits to judge")

    def test_a_bump_that_swaps_three_lines_is_tiny_but_growth_is_not(self):
        # hugo's version_current.go: every release edits Major, Minor and PatchLevel, 3 lines out and 3 in
        bumps = [{"hash": f"b{i}", "date": "2026-01-01", "time": "", "author": "A", "subject": "release", "files": [("common/hugo/version_current.go", 3, 3)]}
                 for i in range(30)]
        growth = [{"hash": f"g{i}", "date": "2026-01-01", "time": "", "author": "A", "subject": "add", "files": [("lib/list.py", 3, 0)]} for i in range(30)]
        rows = maat.plumbing(bumps + growth)
        self.assertEqual([r["entity"] for r in rows], ["common/hugo/version_current.go"], "three lines added with nothing removed is growth, not a bump")

    def test_written_alongside_the_other_analyses(self):
        with tempfile.TemporaryDirectory() as d:
            log = os.path.join(d, "log.txt")
            with open(log, "w", encoding="utf-8") as fh:
                fh.write("".join(f"--h{i}--2026-01-{1 + i % 28:02d}T10:00:00+00:00--Ann--bump\n1\t1\tpkg/__init__.py\n" for i in range(25)))
            maat.write_all(log, d, types=None)
            with open(os.path.join(d, "maat-plumbing.csv"), encoding="utf-8") as fh:
                text = fh.read()
        self.assertEqual(text.splitlines(), ["entity,n-revs,tiny-revs", "pkg/__init__.py,25,25"])


class Coupling(unittest.TestCase):
    def test_degree_is_shared_over_average_revisions(self):
        rows = maat.coupling(maat.parse_log(LOG))
        # a.py: 7 revs, b.py: 6 revs, shared: 6 -> degree 6 / 6.5 = 92%, average-revs 7 (rounded 6.5)
        self.assertEqual(rows, [{"entity": "src/a.py", "coupled": "src/b.py", "degree": 92, "average-revs": 7}])

    def test_pairs_below_thresholds_are_dropped(self):
        rows = maat.coupling(maat.parse_log(LOG), min_shared=7)
        self.assertEqual(rows, [])


class Authors(unittest.TestCase):
    def test_distinct_authors_and_revisions_per_entity(self):
        rows = {r["entity"]: r for r in maat.authors(maat.parse_log(LOG))}
        self.assertEqual(rows["src/a.py"], {"entity": "src/a.py", "n-authors": 3, "n-revs": 7, "minor": 0})
        self.assertEqual(rows["src/c.py"]["n-authors"], 1)


class Age(unittest.TestCase):
    def test_months_since_last_change(self):
        rows = {r["entity"]: r["age-months"] for r in maat.age(maat.parse_log(LOG), now="2026-09-15")}
        self.assertEqual(rows["src/a.py"], 5)   # last 2026-04-03
        self.assertEqual(rows["src/c.py"], 6)   # last 2026-03-10
        self.assertEqual(rows["img/logo.png"], 7)


class Ownership(unittest.TestCase):
    def test_added_and_deleted_per_author_per_entity(self):
        rows = {(r["entity"], r["author"]): r for r in maat.entity_ownership(maat.parse_log(LOG))}
        self.assertEqual(rows[("src/a.py", "Ann")], {"entity": "src/a.py", "author": "Ann", "added": 10, "deleted": 1})
        self.assertEqual(rows[("src/a.py", "Cat")]["deleted"], 2)


class Types(unittest.TestCase):
    def test_file_entries_outside_the_types_are_dropped(self):
        commits = maat.parse_log(LOG, types={"py"})
        self.assertEqual(commits[1]["files"], [("src/a.py", 1, 1), ("src/b.py", 5, 5)])
        self.assertNotIn("img/logo.png", {p for c in commits for p, _, _ in c["files"]})

    def test_none_means_everything(self):
        commits = maat.parse_log(LOG, types=None)
        self.assertIn("img/logo.png", {p for c in commits for p, _, _ in c["files"]})


class Timeline(unittest.TestCase):
    def test_commits_per_author_per_month(self):
        a = maat.activity(maat.parse_log(LOG))
        self.assertEqual(a["timeline"]["Ann"], {"2026-01": 1, "2026-03": 2, "2026-04": 2})
        self.assertEqual(a["timeline"]["Bob"], {"2026-02": 1})
        self.assertEqual(a["timeline"]["Cat"], {"2026-04": 1})


class Aliases(unittest.TestCase):
    def test_author_names_are_canonicalised(self):
        commits = maat.parse_log(LOG, aliases={"Bob": "Robert"})
        rows = {r["entity"]: r for r in maat.authors(commits)}
        self.assertEqual(rows["src/a.py"]["n-authors"], 3)
        own = {(r["entity"], r["author"]) for r in maat.entity_ownership(commits)}
        self.assertIn(("src/b.py", "Robert"), own)
        self.assertNotIn(("src/b.py", "Bob"), own)


class IsFix(unittest.TestCase):
    def test_conventional_and_wordy_subjects(self):
        for yes in ["fix: x", "fix(core)!: x", "Fixed the thing", "bugfix", "Hotfix: y", "Resolve crash on start", "regression in parser", "Bug 123"]:
            self.assertTrue(maat.is_fix(yes), yes)
        for no in ["prefix cleanup", "feat: bugsnag integration", "Add fixtures", "docs: typo", "Suffix handling"]:
            self.assertFalse(maat.is_fix(no), no)


class Fixes(unittest.TestCase):
    def test_counts_fixes_per_entity_with_last_and_recent(self):
        rows = {r["entity"]: r for r in maat.fixes(maat.parse_log(LOG), now="2026-09-15")}
        self.assertEqual(rows["src/a.py"], {"entity": "src/a.py", "n-fixes": 3, "last-fix": "2026-04-03", "recent-fixes": 2})
        self.assertEqual(rows["src/b.py"]["n-fixes"], 2)
        self.assertEqual(rows["src/c.py"]["n-fixes"], 1)
        self.assertNotIn("img/logo.png", rows)

    def test_recent_window_is_six_months(self):
        rows = {r["entity"]: r for r in maat.fixes(maat.parse_log(LOG), now="2026-10-02")}
        self.assertEqual(rows["src/a.py"]["recent-fixes"], 1)   # 2026-04-03 is inside six months of 2026-10-02; 2026-04-01 is not


class Activity(unittest.TestCase):
    def test_commits_by_weekday_hour_month_and_author(self):
        a = maat.activity(maat.parse_log(LOG))
        # 2026-01-10 Sat, 02-10 Tue, 03-10 Tue, 03-12 Thu, 04-01 Wed, 04-02 Thu, 04-03 Fri
        self.assertEqual(a["by_weekday"], [0, 2, 1, 2, 1, 1, 0])
        self.assertEqual(a["by_hour"][9], 4)
        self.assertEqual(a["by_hour"][22], 1)
        self.assertEqual(a["by_month"], {"2026-01": 1, "2026-02": 1, "2026-03": 2, "2026-04": 3})
        self.assertEqual(a["authors"]["Ann"], {"commits": 5, "added": 16, "deleted": 1, "first": "2026-01-10", "last": "2026-04-02"})
        self.assertEqual(a["authors"]["Cat"]["deleted"], 3)
        self.assertEqual(a["fix_commits"], 3)

    def test_legacy_short_dates_still_parse(self):
        a = maat.activity(maat.parse_log("--x--2026-05-04--Ann\n1\t0\tf.py\n"))
        self.assertEqual(sum(a["by_weekday"]), 1)
        self.assertEqual(a["by_hour"], [0] * 24)


class UtcZSuffix(unittest.TestCase):
    def test_git_2_45_z_suffix_timestamps_keep_their_hour(self):
        a = maat.activity(maat.parse_log("--x--2026-05-04T09:15:00Z--Ann\n1\t0\tf.py\n"))
        self.assertEqual(a["by_hour"][9], 1)
        self.assertEqual(a["by_weekday"][0], 1)  # 2026-05-04 is a Monday


class NetByYear(unittest.TestCase):
    def test_added_minus_deleted_per_year(self):
        a = maat.activity(maat.parse_log(LOG + "--h8--2025-12-31T10:00:00+00:00--Ann\n7\t2\told.py\n"))
        self.assertEqual(a["net_by_year"], {"2025": 5, "2026": 12})


class NowParameter(unittest.TestCase):
    def test_write_all_takes_the_reference_date_as_a_parameter(self):
        with tempfile.TemporaryDirectory() as d:
            log = os.path.join(d, "log.txt")
            with open(log, "w") as fh:
                fh.write(LOG)
            maat.write_all(log, d, now="2030-01-01")
            with open(os.path.join(d, "maat-age.csv")) as fh:
                rows = dict(line.strip().split(",") for line in fh.readlines()[1:])
        self.assertEqual(rows["src/a.py"], "44")   # 2026-04-03 -> 2030-01-01

    def test_library_ignores_the_environment(self):
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as d, patch.dict(os.environ, {"GITMOLE_NOW": "2030-01-01"}):
            log = os.path.join(d, "log.txt")
            with open(log, "w") as fh:
                fh.write(LOG)
            maat.write_all(log, d)
            with open(os.path.join(d, "maat-age.csv")) as fh:
                rows = dict(line.strip().split(",") for line in fh.readlines()[1:])
        self.assertNotEqual(rows["src/a.py"], "44")

    def test_validate_now_rejects_malformed_dates(self):
        self.assertEqual(maat.validate_now("2025-06-15"), "2025-06-15")
        for bad in ("2025-6-15", "today", "2025-06-15T00:00:00"):
            with self.assertRaises(ValueError):
                maat.validate_now(bad)


class CarriageReturnInSubject(unittest.TestCase):
    def test_write_all_reads_the_log_without_newline_translation(self):
        with tempfile.TemporaryDirectory() as d:
            log = os.path.join(d, "log.txt")
            with open(log, "wb") as fh:
                fh.write(b"--x--2026-05-04T10:00:00+00:00--Ann--Fix the\rwatcher (#1)\n1\t0\tf.py\n")
            maat.write_all(log, d)
            with open(os.path.join(d, "maat-revisions.csv")) as fh:
                self.assertEqual(fh.read().splitlines()[1], "f.py,1")


class Reverts(unittest.TestCase):
    def test_a_revert_is_gits_own_subject_prefix(self):
        self.assertTrue(maat.is_revert('Revert "feat: initial layout"'))
        self.assertTrue(maat.is_revert("Revert layout change"))
        self.assertFalse(maat.is_revert("revert: layout"), "conventional-commit style is not git's revert")
        self.assertFalse(maat.is_revert("Reverting nothing"))
        self.assertFalse(maat.is_revert(""))

    def test_activity_counts_reverts_and_the_files_they_touch(self):
        log = LOG + ('--h8--2026-04-04T10:00:00+00:00--Ann--Revert "Refactor helpers"\n1\t0\tsrc/a.py\n1\t0\tsrc/b.py\n\n'
                     '--i9--2026-04-05T10:00:00+00:00--Bob--Revert "prefix cleanup"\n0\t1\tsrc/a.py\n')
        a = maat.activity(maat.parse_log(log))
        self.assertEqual(a["revert_commits"], 2)
        self.assertEqual(a["reverted"], {"src/a.py": 2, "src/b.py": 1})

    def test_no_reverts(self):
        a = maat.activity(maat.parse_log(LOG))
        self.assertEqual(a["revert_commits"], 0)
        self.assertEqual(a["reverted"], {})


class SinceWindow(unittest.TestCase):
    def test_window_bounds_everything_except_age(self):
        with tempfile.TemporaryDirectory() as d:
            log = os.path.join(d, "log.txt")
            with open(log, "w") as fh:
                fh.write(LOG)
            maat.write_all(log, d, now="2026-09-15", since="2026-04-01")
            def rows(name):
                with open(os.path.join(d, name)) as fh:
                    return fh.read().splitlines()[1:]
            self.assertEqual(rows("maat-revisions.csv"), ["src/a.py,3", "src/b.py,3"], "only commits from 2026-04-01 on")
            self.assertIn("src/c.py,6", rows("maat-age.csv"), "age keeps the whole history")
            with open(os.path.join(d, "activity.json")) as fh:
                a = json.load(fh)
            self.assertEqual(sum(a["by_weekday"]), 3)
            self.assertEqual(a["window"], "2026-04-01")

    def test_authors_all_keeps_everyone_while_authors_stays_windowed(self):
        with tempfile.TemporaryDirectory() as d:
            log = os.path.join(d, "log.txt")
            with open(log, "w") as fh:
                fh.write(LOG)
            maat.write_all(log, d, now="2026-09-15", since="2026-04-01")
            with open(os.path.join(d, "activity.json")) as fh:
                act = json.load(fh)
        self.assertEqual(sorted(act["authors"]), ["Ann", "Cat"], "only the people who committed in the window")
        self.assertEqual(act["authors"]["Ann"]["first"], "2026-04-01")
        self.assertEqual(sorted(act["authors_all"]), ["Ann", "Bob", "Cat"], "knowledge loss needs everyone")
        self.assertEqual(act["authors_all"]["Ann"], {"commits": 5, "added": 16, "deleted": 1, "first": "2026-01-10", "last": "2026-04-02"})
        self.assertEqual(act["authors_all"]["Bob"], {"commits": 1, "added": 6, "deleted": 6, "first": "2026-02-10", "last": "2026-02-10"})

    def test_empty_window_is_reported(self):
        commits = maat.parse_log(LOG)
        self.assertEqual(maat.in_window(commits, "2030-01-01"), [])


class WriteAll(unittest.TestCase):
    def test_writes_the_csv_files_in_code_maat_layout_plus_plumbing(self):
        with tempfile.TemporaryDirectory() as d:
            log = os.path.join(d, "log.txt")
            with open(log, "w") as fh:
                fh.write(LOG)
            maat.write_all(log, d)
            names = sorted(n for n in os.listdir(d) if n.startswith("maat-"))
            self.assertEqual(names, ["maat-age.csv", "maat-authors.csv", "maat-companions.csv", "maat-components.csv", "maat-coupling.csv", "maat-doa.csv",
                                     "maat-entity-ownership.csv", "maat-entropy.csv", "maat-fixes.csv", "maat-latenight.csv", "maat-plumbing.csv",
                                     "maat-revisions.csv", "maat-soc.csv", "maat-tests.csv"])
            self.assertTrue(os.path.isfile(os.path.join(d, "activity.json")))
            with open(os.path.join(d, "maat-revisions.csv")) as fh:
                self.assertEqual(fh.readline().strip(), "entity,n-revs")
                self.assertEqual(fh.readline().strip(), "src/a.py,7")
            with open(os.path.join(d, "maat-coupling.csv")) as fh:
                self.assertEqual(fh.readline().strip(), "entity,coupled,degree,average-revs")


class MonthsBefore(unittest.TestCase):
    def test_subtracts_whole_months_and_clamps_the_day(self):
        self.assertEqual(maat.months_before("2025-11-09", 12), "2024-11-09")
        self.assertEqual(maat.months_before("2026-03-31", 1), "2026-02-28")
        self.assertEqual(maat.months_before("2026-01-15", 6), "2025-07-15")
        self.assertEqual(maat.months_before("2026-01-15", 0), "2026-01-15")

    def test_over_a_year_wraps_the_year_boundary_more_than_once(self):
        self.assertEqual(maat.months_before("2026-01-15", 13), "2024-12-15")
        self.assertEqual(maat.months_before("2026-01-15", 24), "2024-01-15")


class Until(unittest.TestCase):
    def test_until_is_exclusive_and_combines_with_since(self):
        commits = maat.parse_log(LOG)
        self.assertEqual([c["hash"] for c in maat.in_window(commits, until="2026-03-10")], ["a1", "b2"])
        self.assertEqual([c["hash"] for c in maat.in_window(commits, since="2026-02-10", until="2026-04-01")], ["b2", "c3", "d4"])

    def test_write_all_takes_until(self):
        with tempfile.TemporaryDirectory() as d:
            log = os.path.join(d, "log.txt")
            with open(log, "w") as fh:
                fh.write(LOG)
            maat.write_all(log, d, now="2026-03-10", until="2026-03-10")
            with open(os.path.join(d, "maat-revisions.csv")) as fh:
                rows = dict(line.strip().split(",") for line in fh.readlines()[1:])
            with open(os.path.join(d, "activity.json")) as fh:
                act = json.load(fh)
        self.assertEqual(rows, {"src/a.py": "2", "src/b.py": "2"})
        self.assertEqual(act["fix_commits"], 0)
        self.assertEqual(act["until"], "2026-03-10")


def _commit(h, files, author="Ann", date="2026-01-05", subject="work", co_authors=()):
    return {"hash": h, "date": date, "time": f"{date}T10:00:00+00:00", "author": author, "subject": subject,
            "files": list(files), "co_authors": list(co_authors)}


class CoAuthors(unittest.TestCase):
    LOG = ("--a1--2026-01-10T09:15:00+00:00--Ann--feat: pair work\x1fBob <bob@x.com>\x1fdependabot[bot] <1234+dependabot[bot]@users.noreply.github.com>\x1fAnn <ann@x.com>\x1fBob <bob@x.com>\n"
           "10\t0\tsrc/a.py\n"
           "5\t1\tsrc/b.py\n"
           "\n"
           "--b2--2026-02-10T14:00:00+00:00--Cat--solo\x1f\n"
           "2\t2\tsrc/a.py\n")

    def test_co_authored_by_trailers_name_the_other_people_on_the_commit(self):
        commits = maat.parse_log(self.LOG)
        self.assertEqual(commits[0]["subject"], "feat: pair work", "the trailers are split off the subject")
        self.assertEqual(commits[0]["co_authors"], ["Bob"], "the author is not their own co-author, a bot is nobody, a repeat is one person")
        self.assertEqual(commits[1]["co_authors"], [])
        self.assertEqual(maat.parse_log(LOG)[0]["co_authors"], [], "a log written before trailers were exported still parses")

    def test_co_authors_are_canonicalised_like_authors(self):
        commits = maat.parse_log(self.LOG, aliases={"Bob": "Robert"})
        self.assertEqual(commits[0]["co_authors"], ["Robert"])

    def test_co_authors_count_as_authors_of_the_file_and_share_its_lines(self):
        commits = maat.parse_log(self.LOG)
        rows = {r["entity"]: r for r in maat.authors(commits)}
        self.assertEqual(rows["src/a.py"]["n-authors"], 3, "Ann, Bob and Cat")
        own = {(r["entity"], r["author"]): (r["added"], r["deleted"]) for r in maat.entity_ownership(commits)}
        self.assertEqual(own[("src/a.py", "Ann")], (5, 0))
        self.assertEqual(own[("src/a.py", "Bob")], (5, 0))
        self.assertEqual(own[("src/b.py", "Ann")], (3, 1), "the odd line and the odd deletion go to the committer")
        self.assertEqual(own[("src/b.py", "Bob")], (2, 0))
        totals = maat.author_totals(commits)
        self.assertEqual(totals["Bob"], {"commits": 1, "added": 7, "deleted": 0, "first": "2026-01-10", "last": "2026-01-10"})
        self.assertEqual(maat.activity(commits)["timeline"]["Bob"], {"2026-01": 1})


class MinorContributors(unittest.TestCase):
    def test_authors_under_five_percent_of_a_files_commits_are_minor(self):
        commits = [_commit(f"m{i}", [("core/big.py", 1, 0)], author="Ann") for i in range(38)]
        commits += [_commit("x1", [("core/big.py", 1, 0)], author="Bob"), _commit("x2", [("core/big.py", 1, 0)], author="Cat")]
        commits += [_commit("s1", [("core/small.py", 1, 0)], author="Ann"), _commit("s2", [("core/small.py", 1, 0)], author="Bob")]
        rows = {r["entity"]: r for r in maat.authors(commits)}
        self.assertEqual(rows["core/big.py"], {"entity": "core/big.py", "n-authors": 3, "n-revs": 40, "minor": 2}, "1 of 40 commits is 2.5%")
        self.assertEqual(rows["core/small.py"]["minor"], 0, "1 of 2 commits is half")


class SumOfCoupling(unittest.TestCase):
    def test_total_co_changes_and_partners_per_entity(self):
        commits = [_commit(f"c{i}", [("hub.py", 1, 0), (f"leaf{i % 3}.py", 1, 0)], date=f"2026-01-{1 + i:02d}") for i in range(15)]
        commits.append(_commit("big", [(f"f{i}.py", 1, 0) for i in range(40)], date="2026-02-01"))
        rows = {r["entity"]: r for r in maat.soc(commits)}
        self.assertEqual(rows["hub.py"], {"entity": "hub.py", "soc": 15, "partners": 3}, "15 co-changes over 3 files, each shared 5 times")
        self.assertEqual(rows["leaf0.py"], {"entity": "leaf0.py", "soc": 5, "partners": 1})
        self.assertNotIn("f1.py", rows, "a commit over the changeset cap is not coupling, as in coupling()")
        self.assertEqual([r["entity"] for r in maat.soc(commits)][0], "hub.py", "the most coupled first")


class Sweeping(unittest.TestCase):
    def _history(self):
        commits = [_commit(f"c{i}", [("src/a.py", 3, 1), (f"src/f{i % 7}.py", 2, 1)], subject="work") for i in range(200)]
        commits.append(_commit("fmt1", [(f"src/f{i}.py", 4, 4) for i in range(60)], subject="Reformat with black", date="2026-03-01"))
        commits.append(_commit("imp1", [(f"lib/v{i}.py", 100, 0) for i in range(60)], subject="Import the vendored library"))
        commits.append(_commit("ren1", [(f"src/g{i}.py", 1, 1) for i in range(25)], subject="Rename Foo to Bar everywhere", date="2026-04-01"))
        return commits

    def test_a_commit_over_the_99th_percentile_of_files_with_as_many_lines_out_as_in_is_sweeping(self):
        swept = maat.sweeping(self._history())
        self.assertEqual([c["hash"] for c in swept], ["fmt1", "ren1"], "the import adds far more than it removes; the rename sweep is as symmetric as the reformat")

    def test_a_small_history_needs_twenty_files_at_least(self):
        commits = [_commit(f"c{i}", [("a.py", 1, 1)]) for i in range(5)] + [_commit("w", [(f"f{i}.py", 1, 1) for i in range(12)])]
        self.assertEqual(maat.sweeping(commits), [], "12 files is the biggest commit here, but not a sweep")
        commits.append(_commit("big", [(f"g{i}.py", 1, 1) for i in range(20)]))
        self.assertEqual([c["hash"] for c in maat.sweeping(commits)], ["big"])

    def test_write_all_leaves_sweeping_and_declared_commits_out_and_records_them(self):
        commits = self._history()
        commits.append(_commit("decl", [("src/a.py", 9, 2), ("src/f1.py", 3, 3)], subject="declared uninteresting", date="2026-05-01"))
        with tempfile.TemporaryDirectory() as d:
            log = os.path.join(d, "log.txt")
            with open(log, "w") as fh:
                for c in commits:
                    fh.write(f"--{c['hash']}--{c['time']}--{c['author']}--{c['subject']}\n")
                    fh.writelines(f"{a}\t{dd}\t{p}\n" for p, a, dd in c["files"])
                    fh.write("\n")
            maat.write_all(log, d, ignore_revs={"decl0000000000000000000000000000000000000"})
            with open(os.path.join(d, "maat-revisions.csv")) as fh:
                revs = dict(line.strip().split(",") for line in fh.readlines()[1:])
            with open(os.path.join(d, "maat-authors.csv")) as fh:
                authors = {line.split(",")[0]: line.strip().split(",") for line in fh.readlines()[1:]}
            with open(os.path.join(d, "activity.json")) as fh:
                act = json.load(fh)
        self.assertEqual(revs["src/a.py"], "200", "the declared commit's revision is gone")
        self.assertEqual(revs["src/f1.py"], "29", "200 / 7 rounded up, the reformat and the declared commit left out")
        self.assertNotIn("src/g1.py", revs, "the rename sweep was its only commit")
        self.assertEqual(sum(act["by_weekday"]), 204, "activity still counts every commit")
        self.assertEqual([s["hash"] for s in act["sweeping"]], ["fmt1", "ren1"])
        self.assertEqual(act["sweeping"][0], {"hash": "fmt1", "date": "2026-03-01", "author": "Ann", "subject": "Reformat with black",
                                              "files": 60, "added": 240, "deleted": 240, "declared": False})
        self.assertEqual(act["ignored_revs"], 1, "one declared commit was found in the log")

    def test_a_declared_sweep_is_marked_declared(self):
        act = maat.activity(self._history(), ignored={"fmt1"})
        self.assertEqual([(s["hash"], s["declared"]) for s in act["sweeping"]], [("fmt1", True), ("ren1", False)])


class Changesets(unittest.TestCase):
    def test_a_ticket_shaped_key_in_the_subject(self):
        self.assertEqual(maat.ticket_key("Add the parser (#1234)"), "#1234", "GitHub's squash-merge suffix")
        self.assertEqual(maat.ticket_key("PROJ-42: handle nulls"), "PROJ-42", "a Jira-shaped key")
        self.assertEqual(maat.ticket_key("Handle nulls. Fixes #77"), "#77")
        self.assertEqual(maat.ticket_key("Closes #77 and refs #78"), "#77", "the first reference names the change")
        self.assertIsNone(maat.ticket_key("Handle nulls"))
        self.assertIsNone(maat.ticket_key("Use UTF-8 everywhere"), "UTF-8 is a word, not a ticket: a key opens the subject")
        self.assertEqual(maat.ticket_key("[PROJ-42] handle nulls"), "PROJ-42")
        self.assertIsNone(maat.ticket_key("bump to 2024-01"), "a date is not a key")

    def test_commits_sharing_a_key_are_one_changeset_the_rest_group_by_author_and_day(self):
        commits = [_commit("a1", [("x.py", 1, 0)], author="Ann", date="2026-01-05", subject="PROJ-1 start"),
                   _commit("a2", [("y.py", 2, 0)], author="Bob", date="2026-01-09", subject="PROJ-1 finish"),
                   _commit("b1", [("p.py", 1, 0), ("x.py", 1, 1)], author="Ann", date="2026-01-05", subject="tidy"),
                   _commit("b2", [("q.py", 1, 0)], author="Ann", date="2026-01-05", subject="more tidy"),
                   _commit("c1", [("q.py", 3, 0)], author="Ann", date="2026-01-06", subject="next day"),
                   _commit("d1", [("r.py", 1, 0)], author="Cat", date="2026-01-05", subject="Cat's own (#9)"),
                   _commit("d2", [("s.py", 1, 0)], author="Cat", date="2026-01-05", subject="Cat again (#10)")]
        sets = maat.changesets(commits)
        self.assertEqual([(c["hash"], c["commits"], sorted(p for p, _, _ in c["files"])) for c in sets],
                         [("a1", 2, ["x.py", "y.py"]), ("b1", 2, ["p.py", "q.py", "x.py"]), ("c1", 1, ["q.py"]), ("d1", 1, ["r.py"]), ("d2", 1, ["s.py"])],
                         "a key wins over the day; two squash merges by one person on one day stay apart")
        self.assertEqual(sets[1]["files"], [("p.py", 1, 0), ("x.py", 1, 1), ("q.py", 1, 0)], "lines summed per path, first seen first")
        self.assertEqual((sets[0]["author"], sets[0]["date"], sets[0]["subject"]), ("Ann", "2026-01-05", "PROJ-1 start"), "the first commit speaks for the set")

    def test_coupling_and_sum_of_coupling_count_changesets_not_commits(self):
        commits = []
        for i in range(6):   # a rebase-merged feature: the model and its migration land as two commits by one author on one day
            commits.append(_commit(f"m{i}", [("app/model.py", 5, 1)], author="Ann", date=f"2026-02-{10 + i:02d}", subject="model"))
            commits.append(_commit(f"g{i}", [("app/migration.py", 5, 1)], author="Ann", date=f"2026-02-{10 + i:02d}", subject="migration"))
        self.assertEqual(maat.coupling(commits), [{"entity": "app/migration.py", "coupled": "app/model.py", "degree": 100, "average-revs": 6}])
        self.assertEqual(maat.soc(commits)[0], {"entity": "app/migration.py", "soc": 6, "partners": 1})

    def test_the_changeset_cap_applies_after_grouping(self):
        commits = [_commit(f"c{i}", [(f"f{i}.py", 1, 0), ("hub.py", 1, 0)], author="Ann", date="2026-03-01", subject="") for i in range(40)]
        self.assertEqual(maat.coupling(commits), [], "forty small commits in a day are one sweep of forty files, over the cap")


class TestCoChange(unittest.TestCase):
    def test_share_of_a_files_changesets_that_also_touched_a_test(self):
        commits = [_commit(f"a{i}", [("core/a.py", 1, 0), ("tests/test_a.py", 1, 0)]) for i in range(3)]
        commits += [_commit(f"b{i}", [("core/a.py", 1, 0)], date="2026-02-01") for i in range(1)]
        commits += [_commit(f"c{i}", [("core/b.py", 1, 0)], date=f"2026-03-{1 + i:02d}") for i in range(4)]
        rows = {r["entity"]: r for r in maat.test_cochange(commits)}
        self.assertEqual(rows["core/a.py"], {"entity": "core/a.py", "n-sets": 2, "with-tests": 1},
                         "three same-day commits are one changeset with a test, the February one has none")
        self.assertEqual(rows["core/b.py"], {"entity": "core/b.py", "n-sets": 4, "with-tests": 0})
        self.assertNotIn("tests/test_a.py", rows, "a test file's own row would say nothing")


class OversizedFixes(unittest.TestCase):
    def _history(self):
        commits = [_commit(f"c{i}", [("src/a.py", 3, 1)], subject="fix: small", date="2026-06-01") for i in range(200)]
        commits.append(_commit("big", [(f"src/f{i}.py", 40, 40) for i in range(30)], subject="fix: everything at once", date="2026-06-02"))
        commits.append(_commit("med", [("src/z.py", 300, 100)], subject="fix: medium", date="2026-06-03"))
        return commits

    def test_a_fix_over_the_99th_percentile_of_lines_changed_credits_nothing(self):
        rows = {r["entity"]: r for r in maat.fixes(self._history(), now="2026-09-01")}
        self.assertNotIn("src/f1.py", rows, "2,400 lines: over the 99th percentile and over the floor")
        self.assertEqual(rows["src/z.py"]["n-fixes"], 1, "400 lines: under the 500-line floor, whatever the percentile")
        self.assertEqual(rows["src/a.py"]["n-fixes"], 200)
        self.assertEqual([c["hash"] for c in maat.oversized(self._history())], ["big"])
        self.assertEqual(maat.activity(self._history())["oversized_fixes"], 1)

    def test_fix_commits_is_the_pool_the_backtest_reads(self):
        self.assertEqual([c["hash"] for c in maat.fix_commits(self._history())][-2:], ["c199", "med"])


class Tangled(unittest.TestCase):
    def test_many_files_across_many_directories_under_a_subject_with_several_clauses(self):
        files = [(f"pkg{i % 5}/f{i}.py", 1, 1) for i in range(12)]
        yes = _commit("t1", files, subject="Fix the parser, add a cache and rename the helpers")
        one_thing = _commit("t2", files, subject="Rename the helpers (see foo(a, b))")
        few_dirs = _commit("t3", [(f"pkg/f{i}.py", 1, 1) for i in range(12)], subject="Fix the parser, add a cache and rename the helpers")
        self.assertTrue(maat.is_tangled(yes))
        self.assertFalse(maat.is_tangled(one_thing), "a comma inside brackets is not a clause")
        self.assertFalse(maat.is_tangled(few_dirs))
        self.assertEqual(maat.clauses("Fix a; add b"), 2)
        self.assertEqual(maat.clauses("Fix a & b + c"), 3)
        act = maat.activity([yes, one_thing, few_dirs])
        self.assertEqual(act["tangled_commits"], 1)
        self.assertEqual(act["tangled"], [{"hash": "t1", "date": "2026-01-05", "files": 12, "dirs": 5, "subject": "Fix the parser, add a cache and rename the helpers"}])

    def test_squash_subjects_are_counted(self):
        commits = [_commit("s1", [("a.py", 1, 0)], subject="Add x (#12)"), _commit("s2", [("a.py", 1, 0)], subject="Add y (#13)"), _commit("r1", [("a.py", 1, 0)], subject="Add z")]
        self.assertEqual(maat.activity(commits)["squash_subjects"], 2)


class IgnoreRevs(unittest.TestCase):
    def test_reads_full_shas_past_comments_and_matches_abbreviated_hashes(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, ".git-blame-ignore-revs")
            with open(path, "w") as fh:
                fh.write("# Reformat with black\nabcdef0123456789abcdef0123456789abcdef01\n\n  FEDCBA9876543210fedcba9876543210fedcba98  # trailing note\nnot-a-sha\n")
            revs = maat.read_ignore_revs([path, os.path.join(d, "missing")])
        self.assertEqual(revs, {"abcdef0123456789abcdef0123456789abcdef01", "fedcba9876543210fedcba9876543210fedcba98"})
        self.assertTrue(maat.is_ignored("abcdef0", revs))
        self.assertTrue(maat.is_ignored("fedcba9876543210fedcba9876543210fedcba98", revs))
        self.assertFalse(maat.is_ignored("abcdef1", revs))


if __name__ == "__main__":
    unittest.main()


class ChangeEntropy(unittest.TestCase):
    def test_hassans_decayed_entropy_over_monthly_periods(self):
        # Two files share January evenly (entropy 1); February is all one file (entropy 0); a lone file in March
        # changes nothing (one file: no scatter). Decay halves a period's weight each month back from `now`.
        commits = [_commit("j1", [("a.py", 1, 0)], date="2026-01-05"), _commit("j2", [("b.py", 1, 0)], date="2026-01-20"),
                   _commit("f1", [("a.py", 1, 0)], date="2026-02-03"), _commit("f2", [("a.py", 1, 0)], date="2026-02-09"),
                   _commit("m1", [("c.py", 1, 0)], date="2026-03-01")]
        rows = {r["entity"]: r for r in maat.entropy(commits, now="2026-03-31")}
        self.assertEqual(rows["a.py"]["periods"], 2)
        self.assertEqual(rows["b.py"]["periods"], 1)
        self.assertEqual(rows["c.py"]["periods"], 1)
        # a.py: January share 0.5 × entropy 1 × weight 0.25 (two months back) + February share 1 × entropy 0 = 0.125
        self.assertAlmostEqual(rows["a.py"]["hcm"], 0.125)
        self.assertAlmostEqual(rows["b.py"]["hcm"], 0.125)
        self.assertEqual(rows["c.py"]["hcm"], 0.0)
        self.assertEqual([r["entity"] for r in maat.entropy(commits, now="2026-03-31")][:2], ["a.py", "b.py"], "highest first, ties by name")

    COMMITS = [_commit("j1", [("a.py", 1, 0)], date="2026-01-05"), _commit("j2", [("b.py", 1, 0)], date="2026-01-20"),
               _commit("f1", [("a.py", 1, 0)], date="2026-02-03"), _commit("f2", [("a.py", 1, 0)], date="2026-02-09"),
               _commit("m1", [("c.py", 1, 0)], date="2026-03-01")]

    def test_the_shipped_analysis_is_the_default_and_the_variants_do_not_move_it(self):
        plain = maat.entropy(self.COMMITS, now="2026-03-31")
        spelled = maat.entropy(self.COMMITS, now="2026-03-31", hcpf=2, periods="month", sizing="period", phi=None)
        self.assertEqual(plain, spelled, "entropy.csv ships this: naming today's defaults must change nothing")

    def test_hcpf3_splits_a_period_evenly_where_hcpf2_splits_it_by_share(self):
        # one month, a.py changed twice and b.py once: HCM2s gives a.py two thirds, HCM3s gives them the same
        commits = [_commit("x1", [("a.py", 1, 0)], date="2026-03-02"), _commit("x2", [("a.py", 1, 0)], date="2026-03-03"),
                   _commit("x3", [("b.py", 1, 0)], date="2026-03-04")]
        share = {r["entity"]: r["hcm"] for r in maat.entropy(commits, now="2026-03-31", hcpf=2)}
        even = {r["entity"]: r["hcm"] for r in maat.entropy(commits, now="2026-03-31", hcpf=3)}
        self.assertGreater(share["a.py"], share["b.py"], "HCM2s weights by the file's share of the period")
        self.assertEqual(even["a.py"], even["b.py"], "HCM3s splits the period's entropy evenly")

    def test_hcpf1_gives_every_changed_file_the_whole_period_entropy(self):
        commits = [_commit("x1", [("a.py", 1, 0)], date="2026-03-02"), _commit("x2", [("a.py", 1, 0)], date="2026-03-03"),
                   _commit("x3", [("b.py", 1, 0)], date="2026-03-04")]
        whole = {r["entity"]: r["hcm"] for r in maat.entropy(commits, now="2026-03-31", hcpf=1)}
        even = {r["entity"]: r["hcm"] for r in maat.entropy(commits, now="2026-03-31", hcpf=3)}
        self.assertEqual(whole["a.py"], whole["b.py"])
        self.assertAlmostEqual(whole["a.py"], 2 * even["a.py"], msg="two files changed: the whole is twice the even split")

    def test_burst_periods_split_on_a_quiet_gap_where_a_month_does_not(self):
        commits = [dict(_commit("a", [("one.py", 1, 0)], date="2026-03-02"), time="2026-03-02T01:00:00+00:00"),
                   dict(_commit("b", [("two.py", 1, 0)], date="2026-03-02"), time="2026-03-02T09:00:00+00:00")]
        month = {r["entity"]: r["periods"] for r in maat.entropy(commits, now="2026-03-31", periods="month")}
        burst = {r["entity"]: r["periods"] for r in maat.entropy(commits, now="2026-03-31", periods="burst")}
        self.assertEqual(month["one.py"], 1)
        self.assertEqual(burst["one.py"], 1)
        month_hcm = {r["entity"]: r["hcm"] for r in maat.entropy(commits, now="2026-03-31", periods="month")}
        burst_hcm = {r["entity"]: r["hcm"] for r in maat.entropy(commits, now="2026-03-31", periods="burst")}
        self.assertGreater(month_hcm["one.py"], 0.0, "one calendar month holding two files is scattered")
        self.assertEqual(burst_hcm["one.py"], 0.0, "eight hours apart is two bursts of one file each: no scatter")

    def test_a_phi_decay_replaces_the_halving(self):
        halved = {r["entity"]: r["hcm"] for r in maat.entropy(self.COMMITS, now="2026-03-31")}
        phied = {r["entity"]: r["hcm"] for r in maat.entropy(self.COMMITS, now="2026-03-31", phi=maat.HCM1D_PHI)}
        self.assertNotEqual(halved["a.py"], phied["a.py"], "exp(-back/phi) is not 0.5 ** back")
        self.assertGreater(phied["a.py"], halved["a.py"], "phi of 10 forgets more slowly than halving every month")

    def test_adaptive_sizing_normalises_over_the_recent_working_set(self):
        commits = [_commit("j1", [("a.py", 1, 0)], date="2026-01-05"), _commit("j2", [("b.py", 1, 0)], date="2026-01-06"),
                   _commit("f1", [("c.py", 1, 0)], date="2026-02-03"), _commit("f2", [("d.py", 1, 0)], date="2026-02-04")]
        period = {r["entity"]: r["hcm"] for r in maat.entropy(commits, now="2026-02-28", sizing="period")}
        adaptive = {r["entity"]: r["hcm"] for r in maat.entropy(commits, now="2026-02-28", sizing="adaptive")}
        self.assertLess(adaptive["c.py"], period["c.py"],
                        "normalising over four files rather than two lowers a two-file period's entropy")

    def test_written_alongside_the_other_analyses(self):
        with tempfile.TemporaryDirectory() as d:
            log = os.path.join(d, "log.txt")
            with open(log, "w") as fh:
                fh.write(LOG)
            maat.write_all(log, d, now="2026-09-15")
            with open(os.path.join(d, "maat-entropy.csv")) as fh:
                self.assertEqual(fh.readline().strip(), "entity,periods,hcm")


class DegreeOfAuthorship(unittest.TestCase):
    def test_avelinos_doa_with_the_creator_bonus_and_dilution_by_others(self):
        commits = [_commit("c1", [("a.py", 10, 0)], author="Ann", date="2026-01-01"),
                   _commit("c2", [("a.py", 2, 1)], author="Ann", date="2026-01-02"),
                   _commit("c3", [("a.py", 1, 1)], author="Bob", date="2026-01-03"),
                   _commit("m1", [("b.py", 0, 0)], author="Mover", date="2026-01-04"),
                   _commit("c4", [("b.py", 5, 0)], author="Cat", date="2026-01-05")]
        rows = {(r["entity"], r["author"]): r for r in maat.doa(commits, now="2026-01-10")}
        ann = rows[("a.py", "Ann")]
        self.assertEqual((ann["fa"], ann["dl"], ann["ac"]), (1, 2, 1))
        self.assertAlmostEqual(ann["doa"], 3.293 + 1.098 + 0.164 * 2 - 0.321 * math.log(2), places=3)
        self.assertEqual(rows[("a.py", "Bob")]["fa"], 0)
        self.assertEqual((rows[("b.py", "Cat")]["fa"], rows[("b.py", "Mover")]["fa"]), (1, 0), "a pure move adds no lines and creates nothing")
        self.assertEqual(ann["is_author"], 1)
        self.assertEqual(rows[("a.py", "Bob")]["is_author"], 0, "Bob's DOA is under the 3.293 floor")

    def test_decay_halves_knowledge_every_five_months(self):
        old = [_commit(f"o{i}", [("a.py", 1, 0)], author="Ann", date="2024-01-01") for i in range(10)]
        new = [_commit(f"n{i}", [("a.py", 1, 0)], author="Bob", date="2026-01-01") for i in range(3)]
        rows = {r["author"]: r for r in maat.doa(old + new, now="2026-01-01")}
        self.assertEqual(rows["Ann"]["is_author"], 1, "undecayed, ten changes and creation outweigh three")
        self.assertGreater(rows["Bob"]["doa_decayed"], rows["Ann"]["doa_decayed"] - 1.098, "decayed, Ann's two-year-old changes count for little")
        self.assertEqual(rows["Bob"]["is_author_decayed"], 1)


class LateNight(unittest.TestCase):
    def test_commits_between_midnight_and_four_in_the_authors_own_time(self):
        commits = [dict(_commit("a", [("x.py", 1, 0)]), time="2026-01-05T01:30:00+09:00"),
                   dict(_commit("b", [("x.py", 1, 0)]), time="2026-01-05T03:59:00-05:00"),
                   dict(_commit("c", [("x.py", 1, 0)]), time="2026-01-05T04:00:00+00:00"),
                   dict(_commit("d", [("x.py", 1, 0), ("y.py", 1, 0)]), time="2026-01-05T23:00:00+00:00")]
        rows = {r["entity"]: r for r in maat.latenight(commits)}
        self.assertEqual(rows["x.py"], {"entity": "x.py", "n-revs": 4, "late": 2})
        self.assertEqual(rows["y.py"]["late"], 0)


class Components(unittest.TestCase):
    def test_coupling_between_top_level_components_over_logical_changes(self):
        commits = []
        for i in range(12):
            commits.append(_commit(f"a{i}", [("auth/login.py", 1, 0), ("billing/charge.py", 1, 0)], date=f"2026-01-{1 + i:02d}"))
        for i in range(12):
            commits.append(_commit(f"b{i}", [("auth/token.py", 1, 0)], author="Bob", date=f"2026-02-{1 + i:02d}"))
        commits.append(_commit("c", [("docs/x.md", 1, 0), ("auth/login.py", 1, 0)], date="2026-03-01"))
        rows = [r for r in maat.components(commits) if r["depth"] == 1]
        self.assertEqual(rows, [{"depth": 1, "entity": "auth/", "coupled": "billing/", "degree": 65, "shared": 12, "average-revs": 19}],
                         "12 shared changes over an average of (25 + 12) / 2; docs/ shares one change, under the floor")


class Imports(unittest.TestCase):
    def _history(self):
        imp = _commit("imp", [(f"core/f{i}.py", 1000, 0) for i in range(120)], author="Dan", date="2019-03-26")
        work = [_commit(f"w{i}", [("core/f1.py", 20, 5), ("core/f2.py", 10, 2)], author="Kim" if i % 2 else "Lee", date=f"2020-01-{1 + i:02d}")
                for i in range(20)]
        feature = _commit("feat", [(f"new/g{i}.py", 30, 0) for i in range(110)], author="Kim", date="2020-02-01")   # 3,300 of ~124,000 lines
        return [imp, *work, feature]

    def test_an_add_only_commit_holding_a_twentieth_of_the_history_is_an_import(self):
        commits = self._history()
        self.assertEqual([c["hash"] for c in maat.importing(commits)], ["imp"], "a big new feature is a small share of the history and stays in")
        self.assertNotIn("imp", [c["hash"] for c in maat.analysed(commits)])
        owners = {r["entity"]: r["author"] for r in maat.entity_ownership(maat.analysed(commits)) if r["entity"] == "core/f1.py"}
        self.assertNotEqual(owners.get("core/f1.py"), "Dan", "the importer owns nothing")

    def test_nobody_created_what_an_import_brought_in(self):
        commits = self._history()
        rows = maat.doa(maat.analysed(commits), now="2020-03-01", imported=maat.imported_files(commits))
        self.assertEqual({r["fa"] for r in rows if r["entity"] == "core/f1.py"}, {0}, "the first editor after the import did not create the file")
        self.assertEqual({r["fa"] for r in rows if r["entity"] == "new/g1.py"}, {1})
        act = maat.activity(commits)
        self.assertEqual([c["hash"] for c in act["imports"]], ["imp"])
        self.assertEqual(act["added_total"], sum(a for c in commits for _, a, _ in c["files"]))


class ComponentPairs(unittest.TestCase):
    def test_a_directory_is_not_coupled_with_its_own_subdirectory(self):
        commits = [_commit(f"a{i}", [("gradle/build.gradle", 1, 0), ("gradle/root/x.gradle", 1, 0), ("app/y.py", 1, 0)], date=f"2026-01-{1 + i:02d}")
                   for i in range(12)]
        pairs = {(r["entity"], r["coupled"]) for r in maat.components(commits)}
        self.assertNotIn(("gradle/", "gradle/root/"), pairs)
        self.assertIn(("app/", "gradle/root/"), pairs)


class ClausesAfterAnd(unittest.TestCase):
    def test_a_one_word_part_after_and_joins_nouns_not_changes(self):
        self.assertEqual(maat.clauses("GP-1005: Added new agent for lldb on macOS and Linux"), 1)
        self.assertEqual(maat.clauses("Fix parser and update docs"), 2)
        self.assertEqual(maat.clauses("Delete Deprecated plugins, GADP"), 2, "a comma still separates")


class Companions(unittest.TestCase):
    def test_directed_confidence_keeps_a_small_file_that_moves_with_a_busy_one(self):
        def c(i, files):
            return {"hash": f"h{i:03d}", "date": f"2026-01-{1 + i % 28:02d}", "time": "", "author": f"a{i}", "subject": "work", "files": [(p, 1, 1) for p in files]}
        commits = [c(i, ["core/small.py", "core/hub.py"]) for i in range(20)]           # every change to small.py touches hub.py
        commits += [c(100 + i, ["core/hub.py"]) for i in range(80)]                      # hub.py mostly moves alone
        rows = maat.companions(commits)
        self.assertEqual(rows, [{"entity": "core/small.py", "companion": "core/hub.py", "confidence": 100, "shared": 20}],
                         "20 of hub.py's 100 changes is 20%: not a companion that way; the symmetric degree would be 33% and drop both")
        self.assertEqual(maat.companions(commits[:19] + commits[20:]), [], "19 shared changes are too few")

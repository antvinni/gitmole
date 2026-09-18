import hashlib
import json
import unittest

from gitmole import load


class ParseScc(unittest.TestCase):
    def test_returns_languages_sorted_by_code_desc_with_totals(self):
        text = json.dumps([
            {"Name": "Python", "Count": 2, "Code": 100, "Comment": 5, "Blank": 3, "Complexity": 7},
            {"Name": "HTML", "Count": 4, "Code": 400, "Comment": 0, "Blank": 10, "Complexity": 0},
        ])
        result = load.parse_scc(text)
        self.assertEqual([r["name"] for r in result["languages"]], ["HTML", "Python"])
        self.assertEqual(result["languages"][0]["files"], 4)
        self.assertEqual(result["total_code"], 500)
        self.assertEqual(result["total_files"], 6)

    def test_truncated_json_is_no_data(self):
        self.assertEqual(load.parse_scc('[{"Name": "Py')["languages"], [])


class ParseSccByFile(unittest.TestCase):
    def test_collects_per_file_code_and_complexity_with_clean_paths(self):
        text = json.dumps([
            {"Name": "Python", "Count": 2, "Code": 100, "Comment": 5, "Blank": 3, "Complexity": 7,
             "Files": [{"Location": "./src/a.py", "Code": 60, "Complexity": 5}, {"Location": "src/b.py", "Code": 40, "Complexity": 2}]},
        ])
        result = load.parse_scc(text)
        self.assertEqual(result["files"], {"src/a.py": {"code": 60, "complexity": 5}, "src/b.py": {"code": 40, "complexity": 2}})
        self.assertEqual(result["total_code"], 100)

    def test_file_types_filter_the_files_and_the_language_totals_are_rebuilt_from_what_is_left(self):
        text = json.dumps([
            {"Name": "Python", "Count": 2, "Code": 100, "Comment": 5, "Blank": 3, "Complexity": 7,
             "Files": [{"Location": "src/a.py", "Code": 60, "Comment": 5, "Blank": 3, "Complexity": 5}, {"Location": "src/b.py", "Code": 40, "Comment": 0, "Blank": 0, "Complexity": 2}]},
            {"Name": "JSON", "Count": 1, "Code": 9000, "Comment": 0, "Blank": 0, "Complexity": 0,
             "Files": [{"Location": "data/big.json", "Code": 9000, "Comment": 0, "Blank": 0, "Complexity": 0}]},
            {"Name": "Makefile", "Count": 1, "Code": 8, "Comment": 0, "Blank": 0, "Complexity": 0,
             "Files": [{"Location": "Makefile", "Code": 8, "Comment": 0, "Blank": 0, "Complexity": 0}]},
        ])
        result = load.parse_scc(text, types=load.filetypes.DEFAULT)
        self.assertEqual([r["name"] for r in result["languages"]], ["Python", "Makefile"], "JSON is data; Makefile is code by name")
        self.assertEqual(result["languages"][0], {"name": "Python", "files": 2, "code": 100, "comment": 5, "blank": 3, "complexity": 7})
        self.assertEqual(result["total_code"], 108)
        self.assertEqual(result["total_files"], 3)
        self.assertEqual(set(result["files"]), {"src/a.py", "src/b.py", "Makefile"})
        self.assertEqual(load.parse_scc(text, types={"json"})["total_code"], 9000)
        self.assertEqual(load.parse_scc(text, types=None)["total_code"], 9108, "None means no filter")

    def test_files_key_is_empty_without_by_file_data(self):
        self.assertEqual(load.parse_scc(json.dumps([{"Name": "Go", "Count": 1, "Code": 1, "Comment": 0, "Blank": 0, "Complexity": 0}]))["files"], {})


class ParseMaatCsv(unittest.TestCase):
    def test_parses_rows_with_numeric_columns(self):
        text = "entity,n-revs\nstatic/a.json,128\nsrc/b.py,3\n"
        rows = load.parse_maat_csv(text)
        self.assertEqual(rows, [
            {"entity": "static/a.json", "n-revs": 128},
            {"entity": "src/b.py", "n-revs": 3},
        ])

    def test_empty_text_gives_empty_list(self):
        self.assertEqual(load.parse_maat_csv(""), [])

    def test_truncated_or_empty_numeric_cells_become_zero(self):
        rows = load.parse_maat_csv("entity,author,added,deleted\napp/x.py,Ann,10,0\napp/y.py,Bob\napp/z.py,Cat,,x\n")
        self.assertEqual(rows[1]["added"], 0)
        self.assertEqual(rows[1]["deleted"], 0)
        self.assertEqual(rows[2]["added"], 0)
        self.assertEqual(rows[2]["deleted"], 0)

    def test_only_numeric_columns_are_converted(self):
        rows = load.parse_maat_csv("entity,author,added,deleted\n2024,1234,10,0\n")
        self.assertEqual(rows, [{"entity": "2024", "author": "1234", "added": 10, "deleted": 0}])
        rows = load.parse_maat_csv("entity,n-fixes,last-fix,recent-fixes\n007,2,2026-01-05,1\n")
        self.assertEqual(rows[0]["entity"], "007")
        self.assertEqual(rows[0]["last-fix"], "2026-01-05")
        self.assertEqual(rows[0]["n-fixes"], 2)


class ParseGitSizer(unittest.TestCase):
    TEXT = """| Name                         | Value     | Level of concern               |
| ---------------------------- | --------- | ------------------------------ |
| * Blobs                      |           |                                |
|   * Count                    |   951     |                                |
|   * Maximum size         [4] |  21.3 MiB | **                             |
| * Trees                      |           |                                |
|   * Maximum entries      [3] |    24     |                                |
| History structure            |           |                                |
| * Maximum history depth      |   136 k   | *                              |
| * Maximum tag depth          |     1     |                                |
| Biggest checkouts            |           |                                |
| * Number of files        [8] |  62.3 k   | *                              |
| * Total size of files        |   747 MiB |                                |

[3]  d2afdbc (e5d1b8f:static)
[4]  b2ad626 (986027f:static/video/clip.mp4)
"""

    def test_returns_only_rows_with_concern_and_resolves_footnote(self):
        rows = load.parse_git_sizer(self.TEXT)
        self.assertEqual(rows, [
            {"name": "Blobs: Maximum size", "value": "21.3 MiB", "concern": 2, "ref": "static/video/clip.mp4"},
            {"name": "History structure: Maximum history depth", "value": "136 k", "concern": 1, "ref": ""},
            {"name": "Biggest checkouts: Number of files", "value": "62.3 k", "concern": 1, "ref": ""},
        ], "single-level sections (history structure, biggest checkouts) are rows too, not headers")


class ParseTheseus(unittest.TestCase):
    def test_returns_latest_value_per_label(self):
        text = json.dumps({
            "labels": ["Code added in 2025", "Code added in 2026"],
            "ts": ["2025-08-20T10:26:08", "2026-09-10T14:20:58"],
            "y": [[100, 80], [0, 20]],
        })
        self.assertEqual(load.parse_theseus(text), {"Code added in 2025": 80, "Code added in 2026": 20})

    def test_truncated_json_is_no_data(self):
        self.assertEqual(load.parse_theseus('{"labels": ["Code ad'), {})


class ParseAuthorsLog(unittest.TestCase):
    def test_counts_commits_per_identity(self):
        text = "Ann\tann@x.com\nBob\tbob@x.com\nAnn\tann@x.com\n"
        self.assertEqual(load.parse_authors_log(text), [
            {"name": "Ann", "email": "ann@x.com", "commits": 2},
            {"name": "Bob", "email": "bob@x.com", "commits": 1},
        ])


class ParseFunctions(unittest.TestCase):
    CSV = ('2,1,31,3,2,"_f@14-15@gitmole/findings.py","gitmole/findings.py","_f","_f( severity , title , detail )",14,15\n'
           '120,41,900,9,140,"parse@10-150@src/parser.py","./src/parser.py","parse","parse( a , b )",10,150\n')

    def test_rows_with_clean_paths(self):
        rows = load.parse_functions(self.CSV)
        self.assertEqual(rows[0], {"file": "gitmole/findings.py", "function": "_f", "anonymous": False, "ccn": 1, "nloc": 2, "params": 3,
                                   "start": 14, "end": 15, "suspect": ""})
        self.assertEqual(rows[1]["file"], "src/parser.py")
        self.assertEqual((rows[1]["ccn"], rows[1]["nloc"], rows[1]["params"]), (41, 120, 9))

    def test_empty(self):
        self.assertEqual(load.parse_functions(""), [])

    def test_a_row_with_a_huge_long_name_does_not_abort_the_report(self):
        # ruff: lizard wrote a long name of several hundred kilobytes for one function, over csv's default field limit
        huge = "f( " + "a, " * 100_000 + ")"
        rows = load.parse_functions(f'5,3,40,1,5,"f@1-5@a.rs","a.rs","f","{huge}",1,5\n')
        self.assertEqual((rows[0]["function"], rows[0]["file"], rows[0]["ccn"]), ("f", "a.rs", 3))

    def test_a_huge_function_name_is_cut_to_something_a_table_can_show(self):
        # a test fixture of deeply nested functions gives lizard a dotted name of megabytes
        name = ".".join("a" for _ in range(100_000))
        rows = load.parse_functions(f'5,3,40,1,5,"{name}@1-5@a.py","a.py","{name}","{name}( )",1,5\n')
        self.assertEqual(len(rows[0]["function"]), load.NAME_CAP)
        self.assertTrue(rows[0]["function"].endswith("…"))

    def test_a_nameless_function_is_called_anonymous(self):
        # lizard names Go function literals with an empty string where it names JavaScript's "(anonymous)"
        rows = load.parse_functions('136,47,926,1,270,"@316-585@completions.go","completions.go",""," c * Command",316,585\n')
        self.assertEqual((rows[0]["function"], rows[0]["start"], rows[0]["anonymous"], rows[0]["suspect"]), ("(anonymous)", 316, True, ""))

    def test_a_nameless_function_goes_by_its_label_and_stays_marked_anonymous(self):
        rows = load.parse_functions('136,47,926,1,270,"@316-585@completions.go","completions.go",""," c * Command",316,585,"Run: func(c *Command) {",""\n'
                                    '4,2,36,0,4,"(anonymous)@1-4@routes.js","routes.js","(anonymous)","(anonymous)",1,4,"app.post(""/api/x"", async (req, res) => {",""\n'
                                    '4,2,14,2,4,"tracked@1-4@app.py","app.py","tracked","tracked( a , b )",1,4,"",""\n')
        self.assertEqual([(r["function"], r["anonymous"]) for r in rows],
                         [("Run: func(c *Command) {", True), ('app.post("/api/x", async (req, res) => {', True), ("tracked", False)])

    def test_a_suspect_span_carries_its_reason(self):
        rows = load.parse_functions('9,1,21,1,9,"tpl@1-9@tpl.js","tpl.js","tpl","tpl ( name )",1,9,"","opens a block at line 8 no deeper than its own start"\n')
        self.assertEqual(rows[0]["suspect"], "opens a block at line 8 no deeper than its own start")

    def test_a_row_cut_short_by_a_killed_step_does_not_abort_the_report(self):
        rows = load.parse_functions(self.CSV + '5,3,40,1,5,"g@1-5@a.py","a.py","g","g( )",1,\n')
        self.assertEqual(len(rows), 3)
        self.assertEqual((rows[2]["function"], rows[2]["end"]), ("g", 0))


class ParseDuplicates(unittest.TestCase):
    TEXT = """header junk
Duplicates
===================================
Duplicate block:
--------------------------
gitmole/render.py:457 ~ 459
gitmole/render.py:492 ~ 494
^^^^^^^^^^^^^^^^^^^^^^^^^^
Duplicate block:
--------------------------
a/x.py:10 ~ 80
b/y.py:5 ~ 75
c/z.py:1 ~ 71
^^^^^^^^^^^^^^^^^^^^^^^^^^

Total duplicate rate: 0.78%
Total unique rate: 99.65%
"""

    def test_blocks_with_span_and_rate(self):
        d = load.parse_duplicates(self.TEXT)
        self.assertEqual(d["rate"], 0.78)
        self.assertEqual(len(d["blocks"]), 2)
        self.assertEqual(d["blocks"][1], {"lines": 71, "places": [("a/x.py", 10, 80), ("b/y.py", 5, 75), ("c/z.py", 1, 71)]})
        self.assertEqual(d["blocks"][0]["lines"], 3)

    def test_empty(self):
        self.assertEqual(load.parse_duplicates(""), {"rate": None, "blocks": []})

    def test_places_come_out_in_path_order_whatever_lizard_printed(self):
        text = "Duplicate block:\n---\nz.py:1 ~ 40\na.py:9 ~ 48\na.py:1 ~ 40\n^^^\nTotal duplicate rate: 5.00%\n"
        self.assertEqual(load.parse_duplicates(text)["blocks"][0]["places"], [("a.py", 1, 40), ("a.py", 9, 48), ("z.py", 1, 40)])


class ParseSecrets(unittest.TestCase):
    def test_returns_rule_file_commit_fingerprint_and_the_hashed_value(self):
        hashed = "0a1b2c" + "3d4e5f"   # built at runtime so secret scanners do not flag this file
        text = json.dumps([{"RuleID": "aws-access-token", "File": "config.py", "Commit": "abc1234def", "StartLine": 3,
                            "Fingerprint": "abc1234def:config.py:aws-access-token:3", "SecretHash": hashed, "Placeholder": False}])
        self.assertEqual(load.parse_secrets(text), [
            {"rule": "aws-access-token", "file": "config.py", "commit": "abc1234", "line": 3,
             "fingerprint": "abc1234def:config.py:aws-access-token:3", "value": hashed, "placeholder": False},
        ])

    def test_a_report_from_before_the_wrapper_is_hashed_on_load_and_never_keeps_the_value(self):
        from gitmole import leaks
        version = "5.0.0-" + "1667386184.dfbbb54"   # built at runtime so secret scanners do not flag this file
        text = json.dumps([{"RuleID": "generic-api-key", "File": "web/package.json", "Commit": "d2d2d2d", "StartLine": 21,
                            "Secret": version, "Match": "x"}])
        rows = load.parse_secrets(json.dumps(json.loads(text) * 2))
        row = rows[0]
        self.assertEqual(rows[0]["value"], rows[1]["value"], "one key per file read: repeats still group")
        self.assertNotEqual(row["value"], hashlib.sha256(version.encode()).hexdigest()[:12], "keyed, like the wrapper")
        self.assertTrue(row["placeholder"])
        self.assertNotIn("dfbbb54", json.dumps(row))

    def test_a_row_with_neither_hash_nor_value_still_loads(self):
        row = load.parse_secrets(json.dumps([{"RuleID": "x", "File": "f", "Commit": "c", "StartLine": 1}]))[0]
        self.assertIsNone(row["value"])
        self.assertFalse(row["placeholder"])

    def test_empty_file_is_no_findings(self):
        self.assertEqual(load.parse_secrets(""), [])


class LoadReport(unittest.TestCase):
    def test_reads_every_file_and_tolerates_missing_ones(self):
        import os, tempfile
        with tempfile.TemporaryDirectory() as out:
            os.makedirs(os.path.join(out, "theseus"))
            files = {
                "meta.json": json.dumps({"name": "demo", "commits": 3, "identities": []}),
                "size.json": json.dumps([{"Name": "Python", "Count": 1, "Code": 10, "Comment": 0, "Blank": 0, "Complexity": 1}]),
                "maat-revisions.csv": "entity,n-revs\na.py,3\n",
                "maat-plumbing.csv": "entity,n-revs,tiny-revs\npkg/__init__.py,25,24\n",
                "maat-coupling.csv": "entity,coupled,degree,average-revs\n",
                "maat-age.csv": "entity,age-months\na.py,0\n",
                "maat-authors.csv": "entity,n-authors,n-revs,minor\na.py,1,3,0\n",
                "maat-soc.csv": "entity,soc,partners\na.py,41,7\n",
                "maat-tests.csv": "entity,n-sets,with-tests\na.py,3,1\n",
                "maat-fixes.csv": "entity,n-fixes,last-fix,recent-fixes\na.py,2,2026-01-05,1\n",
                "repo-health.txt": "",
                "secrets.json": "[]",
                "activity.json": json.dumps({"by_weekday": [1, 0, 0, 0, 0, 0, 0], "by_hour": [0] * 24, "by_month": {"2026-01": 1}, "authors": {}}),
                "functions.csv": '3,2,20,1,3,"f@1-3@a.py","a.py","f","f( x )",1,3\n',
                "duplicates.json": json.dumps({"tool": "jscpd", "files": 2, "clones": 1, "rate": 5.0, "blocks": [{"lines": 40, "places": [["b.py", 1, 40], ["a.py", 1, 40]]}]}),
                "dependencies.json": json.dumps({"status": "scanned", "sources": [{"path": "uv.lock", "packages": 4}], "packages": 4, "vulnerable": [],
                                                 "database_date": "2026-09-17"}),
                "theseus/cohorts.json": json.dumps({"labels": ["Code added in 2026"], "ts": ["t"], "y": [[10]]}),
                "theseus/authors.json": json.dumps({"labels": ["Ann"], "ts": ["t"], "y": [[10]]}),
                "signing.json": json.dumps({"commits": 3, "signed": 1, "mechanisms": {"ssh": 1}, "by_year": {"2026": {"commits": 3, "signed": 1}},
                                            "humans": {"commits": 3, "signed": 1}, "bots": {"commits": 0, "signed": 0}, "by_identity": [], "last_year": {"commits": 3, "signed": 1}}),
            }
            for name, text in files.items():
                with open(os.path.join(out, name), "w") as fh:
                    fh.write(text)
            r = load.load_report(out)
        self.assertEqual(r["meta"]["name"], "demo")
        self.assertEqual(r["size"]["total_code"], 10)
        self.assertEqual(r["revisions"][0]["entity"], "a.py")
        self.assertEqual(r["plumbing"], [{"entity": "pkg/__init__.py", "n-revs": 25, "tiny-revs": 24}])
        self.assertEqual(r["coupling"], [])
        self.assertEqual(r["fixes"][0]["recent-fixes"], 1)
        self.assertEqual(r["authors"], [{"entity": "a.py", "n-authors": 1, "n-revs": 3, "minor": 0}])
        self.assertEqual(r["soc"], [{"entity": "a.py", "soc": 41, "partners": 7}], "sum of coupling, as numbers")
        self.assertEqual(r["tests"], [{"entity": "a.py", "n-sets": 3, "with-tests": 1}], "test co-change, as numbers")
        self.assertEqual(r["cohorts"], {"Code added in 2026": 10})
        self.assertEqual(r["theseus_authors"], {"Ann": 10})
        self.assertEqual(r["sizer"], [])
        self.assertEqual(r["secrets"], [])
        self.assertTrue(r["secrets_scanned"], "secrets.json was written, empty")
        self.assertEqual(r["activity"]["by_month"], {"2026-01": 1})
        self.assertEqual(r["functions"][0]["function"], "f")
        self.assertEqual(r["duplicates"], {"rate": 5.0, "files": 2, "blocks": [{"lines": 40, "places": [("a.py", 1, 40), ("b.py", 1, 40)]}]})
        self.assertEqual(r["dependencies"], {"status": "scanned", "sources": [{"path": "uv.lock", "packages": 4}], "packages": 4, "vulnerable": [],
                                             "database_date": "2026-09-17"})
        self.assertEqual(r["signing"]["signed"], 1)
        self.assertEqual(r["out_dir"], out)

    def test_an_older_output_directory_still_reads_lizards_duplicates_and_has_no_dependency_scan(self):
        import os, tempfile
        with tempfile.TemporaryDirectory() as out:
            with open(os.path.join(out, "meta.json"), "w") as fh:
                json.dump({"name": "d", "commits": 1, "identities": []}, fh)
            with open(os.path.join(out, "duplicates.txt"), "w") as fh:
                fh.write("Duplicate block:\n---\na.py:1 ~ 40\nb.py:1 ~ 40\n^^^\nTotal duplicate rate: 5.00%\n")
            r = load.load_report(out)
        self.assertEqual(r["duplicates"], {"rate": 5.0, "blocks": [{"lines": 40, "places": [("a.py", 1, 40), ("b.py", 1, 40)]}]})
        self.assertEqual(r["dependencies"], {"status": "not-run"})

    def test_dependency_statuses_short_of_a_scan(self):
        self.assertEqual(load.parse_dependencies({"status": "no-sources"}), {"status": "no-sources"})
        self.assertEqual(load.parse_dependencies({"status": "no-database", "download": "osv-scanner ..."}), {"status": "no-database", "download": "osv-scanner ..."})
        self.assertEqual(load.parse_dependencies(None), {"status": "not-run"})
        self.assertEqual(load.parse_dependencies({}), {"status": "not-run"}, "a truncated file is no scan")

    def test_bot_authors_are_dropped_from_ownership_and_surviving_code(self):
        # mdBook: a gh-pages deploy job committed the built site under the root, so "Deploy from CI" owned the root files
        import os, tempfile
        with tempfile.TemporaryDirectory() as out:
            os.makedirs(os.path.join(out, "theseus"))
            files = {
                "meta.json": json.dumps({"name": "demo", "commits": 3, "identities": [{"name": "Ann", "email": "a@x", "commits": 2}],
                                         "bots": [{"name": "Deploy from CI", "commits": 40}, {"name": "github-actions", "commits": 2237}]}),
                "maat-entity-ownership.csv": "entity,author,added,deleted\nindex.html,Deploy from CI,6000,0\nsrc/a.rs,Ann,300,0\nsrc/b.rs,dependabot[bot],20,0\n"
                                             "docs/x.md,github-actions,900,0\n",   # a bot the run knew by its alias's [bot] suffix, not by name
                "theseus/authors.json": json.dumps({"labels": ["Ann", "Deploy from CI", "github-actions"], "ts": ["t"], "y": [[300], [6000], [900]]}),
            }
            for name, text in files.items():
                with open(os.path.join(out, name), "w") as fh:
                    fh.write(text)
            r = load.load_report(out)
        self.assertEqual([o["author"] for o in r["ownership"]], ["Ann"])
        self.assertEqual(r["theseus_authors"], {"Ann": 300})

    def test_size_is_filtered_by_the_file_types_recorded_in_meta(self):
        import os, tempfile
        size = json.dumps([{"Name": "JSON", "Count": 1, "Code": 9000, "Comment": 0, "Blank": 0, "Complexity": 0,
                            "Files": [{"Location": "d.json", "Code": 9000, "Comment": 0, "Blank": 0, "Complexity": 0}]},
                           {"Name": "Python", "Count": 1, "Code": 10, "Comment": 0, "Blank": 0, "Complexity": 1,
                            "Files": [{"Location": "a.py", "Code": 10, "Comment": 0, "Blank": 0, "Complexity": 1}]}])
        def total(meta):
            with tempfile.TemporaryDirectory() as out:
                with open(os.path.join(out, "meta.json"), "w") as fh:
                    json.dump(meta, fh)
                with open(os.path.join(out, "size.json"), "w") as fh:
                    fh.write(size)
                return load.load_report(out)["size"]["total_code"]
        self.assertEqual(total({"name": "d", "commits": 1, "identities": []}), 9010,
                         "no record means a run from before the filter: re-render it as it was measured, not with a guessed list")
        self.assertEqual(total({"name": "d", "commits": 1, "identities": [], "file_types": None}), 10)
        self.assertEqual(total({"name": "d", "commits": 1, "identities": [], "file_types": "all"}), 9010)
        self.assertEqual(total({"name": "d", "commits": 1, "identities": [], "file_types": "json"}), 9000)

    def test_surviving_lines_are_re_keyed_to_merged_identities(self):
        import os, tempfile
        with tempfile.TemporaryDirectory() as out:
            os.makedirs(os.path.join(out, "theseus"))
            with open(os.path.join(out, "meta.json"), "w") as fh:
                json.dump({"name": "demo", "commits": 3, "identities": [
                    {"name": "Bob", "email": "b@x", "commits": 3, "aliases": [{"name": "Robert", "email": "r@x", "commits": 1}]}]}, fh)
            with open(os.path.join(out, "theseus/authors.json"), "w") as fh:
                json.dump({"labels": ["Bob", "Robert", "Ann"], "ts": ["t"], "y": [[70], [20], [10]]}, fh)
            r = load.load_report(out)
        self.assertEqual(r["theseus_authors"], {"Bob": 90, "Ann": 10})

    def test_the_duplication_rate_a_year_back_is_kept(self):
        d = load.parse_duplicates_json({"rate": 6.1, "files": 10, "blocks": [], "then": {"date": "2025-09-17", "rev": "abc", "files": 9, "rate": 4.2}})
        self.assertEqual(d["then"], {"date": "2025-09-17", "rev": "abc", "files": 9, "rate": 4.2})
        self.assertNotIn("then", load.parse_duplicates_json({"rate": 6.1, "blocks": []}))

    def test_no_signing_file_is_an_empty_record(self):
        import os, tempfile
        with tempfile.TemporaryDirectory() as out:
            with open(os.path.join(out, "meta.json"), "w") as fh:
                fh.write("{}")
            self.assertEqual(load.load_report(out)["signing"], {}, "an output directory from before the step, or a killed step")
            self.assertEqual(load.load_report(out)["hygiene"], {})
            self.assertEqual(load.load_report(out)["unreachable"], {})
            self.assertEqual(load.load_report(out)["structure"], {})
            self.assertEqual(load.load_report(out)["provenance"], {})

    def test_missing_optional_file_gives_empty_value(self):
        import tempfile
        with tempfile.TemporaryDirectory() as out:
            with open(f"{out}/meta.json", "w") as fh:
                fh.write(json.dumps({"name": "demo", "commits": 0, "identities": []}))
            r = load.load_report(out)
        self.assertEqual(r["revisions"], [])
        self.assertEqual(r["activity"], {})
        self.assertEqual(r["fixes"], [])
        self.assertEqual(r["functions"], [])
        self.assertEqual(r["duplicates"], {"rate": None, "blocks": []})
        self.assertEqual(r["dependencies"], {"status": "not-run"})
        self.assertEqual(r["cohorts"], {})
        self.assertEqual(r["size"]["languages"], [])

    def test_secrets_scanned_is_true_only_when_the_step_wrote_its_file(self):
        import os, tempfile
        with tempfile.TemporaryDirectory() as out:
            with open(os.path.join(out, "meta.json"), "w") as fh:
                json.dump({"name": "d", "commits": 1, "identities": []}, fh)
            self.assertFalse(load.load_report(out)["secrets_scanned"])
            with open(os.path.join(out, "secrets.json"), "w") as fh:
                fh.write("[]")
            r = load.load_report(out)
            self.assertTrue(r["secrets_scanned"])
            self.assertEqual(r["secrets"], [])

    def test_trend_is_read_and_empty_when_missing(self):
        import os, tempfile
        with tempfile.TemporaryDirectory() as out:
            with open(os.path.join(out, "meta.json"), "w") as fh:
                json.dump({"name": "d", "commits": 1, "identities": []}, fh)
            self.assertEqual(load.load_report(out)["trend"], {"samples": [], "files": {}})
            with open(os.path.join(out, "trend.json"), "w") as fh:
                json.dump({"samples": ["2025-01-01"], "files": {"a.py": [["2025-01-01", 3, 10]]}}, fh)
            self.assertEqual(load.load_report(out)["trend"]["files"]["a.py"], [["2025-01-01", 3, 10]])

    def test_malformed_trend_or_activity_json_gives_the_empty_value(self):
        import os, tempfile
        with tempfile.TemporaryDirectory() as out:
            with open(os.path.join(out, "meta.json"), "w") as fh:
                json.dump({"name": "d", "commits": 1, "identities": []}, fh)
            with open(os.path.join(out, "trend.json"), "w") as fh:
                fh.write("{")
            with open(os.path.join(out, "activity.json"), "w") as fh:
                fh.write("{")
            r = load.load_report(out)
        self.assertEqual(r["trend"], {"samples": [], "files": {}})
        self.assertEqual(r["activity"], {})

    def test_output_a_killed_tool_left_truncated_gives_the_empty_value(self):
        import os, tempfile
        with tempfile.TemporaryDirectory() as out:
            with open(os.path.join(out, "meta.json"), "w") as fh:
                json.dump({"name": "d", "commits": 1, "identities": []}, fh)
            os.makedirs(os.path.join(out, "theseus"))
            for name in ("size.json", "theseus/cohorts.json", "theseus/authors.json", "secrets.json"):
                with open(os.path.join(out, name), "w") as fh:
                    fh.write('[{"Name": "Python", "Cou')   # scc's stdout when the timeout killed it
            r = load.load_report(out)
        self.assertEqual(r["size"], {"languages": [], "total_code": 0, "total_files": 0, "files": {}})
        self.assertEqual(r["cohorts"], {})
        self.assertEqual(r["theseus_authors"], {})
        self.assertEqual(r["secrets"], [])
        self.assertFalse(r["secrets_scanned"], "half a secrets file is not a clean scan")

    def test_an_unreadable_meta_json_is_one_clear_error(self):
        import os, tempfile
        with tempfile.TemporaryDirectory() as out:
            with open(os.path.join(out, "meta.json"), "w") as fh:
                fh.write('{"name": "d", "comm')
            with self.assertRaises(load.Unreadable) as ctx:
                load.load_report(out)
        self.assertIn("meta.json", str(ctx.exception))
        self.assertIn("run gitmole again", str(ctx.exception))

    def test_an_unreadable_backtest_sub_report_is_no_backtest(self):
        import os, tempfile
        with tempfile.TemporaryDirectory() as out:
            with open(os.path.join(out, "meta.json"), "w") as fh:
                json.dump({"name": "d", "commits": 1, "identities": []}, fh)
            os.makedirs(os.path.join(out, "backtest"))
            with open(os.path.join(out, "backtest", "meta.json"), "w") as fh:
                fh.write("{")
            self.assertIsNone(load.load_report(out)["backtest"])

    def test_backtest_sub_report_is_loaded_when_present(self):
        import os, tempfile
        with tempfile.TemporaryDirectory() as out:
            with open(os.path.join(out, "meta.json"), "w") as fh:
                json.dump({"name": "d", "commits": 1, "identities": []}, fh)
            self.assertIsNone(load.load_report(out)["backtest"])
            os.makedirs(os.path.join(out, "backtest"))
            with open(os.path.join(out, "backtest", "meta.json"), "w") as fh:
                json.dump({"now": "2025-09-01", "last_date": "2025-09-01"}, fh)
            with open(os.path.join(out, "backtest", "maat-revisions.csv"), "w") as fh:
                fh.write("entity,n-revs\na.py,3\n")
            past = load.load_report(out)["backtest"]
        self.assertEqual(past["meta"]["now"], "2025-09-01")
        self.assertEqual(past["revisions"], [{"entity": "a.py", "n-revs": 3}])
        self.assertIsNone(past["backtest"], "no recursion")


if __name__ == "__main__":
    unittest.main()

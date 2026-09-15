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


class ParseSccByFile(unittest.TestCase):
    def test_collects_per_file_code_and_complexity_with_clean_paths(self):
        text = json.dumps([
            {"Name": "Python", "Count": 2, "Code": 100, "Comment": 5, "Blank": 3, "Complexity": 7,
             "Files": [{"Location": "./src/a.py", "Code": 60, "Complexity": 5}, {"Location": "src/b.py", "Code": 40, "Complexity": 2}]},
        ])
        result = load.parse_scc(text)
        self.assertEqual(result["files"], {"src/a.py": {"code": 60, "complexity": 5}, "src/b.py": {"code": 40, "complexity": 2}})
        self.assertEqual(result["total_code"], 100)

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


class ParseGitSizer(unittest.TestCase):
    TEXT = """| Name                         | Value     | Level of concern               |
| ---------------------------- | --------- | ------------------------------ |
| * Blobs                      |           |                                |
|   * Count                    |   951     |                                |
|   * Maximum size         [4] |  21.3 MiB | **                             |
| * Trees                      |           |                                |
|   * Maximum entries      [3] |    24     |                                |

[3]  d2afdbc (e5d1b8f:static)
[4]  b2ad626 (986027f:static/video/clip.mp4)
"""

    def test_returns_only_rows_with_concern_and_resolves_footnote(self):
        rows = load.parse_git_sizer(self.TEXT)
        self.assertEqual(rows, [
            {"name": "Blobs: Maximum size", "value": "21.3 MiB", "concern": 2, "ref": "static/video/clip.mp4"},
        ])


class ParseTheseus(unittest.TestCase):
    def test_returns_latest_value_per_label(self):
        text = json.dumps({
            "labels": ["Code added in 2025", "Code added in 2026"],
            "ts": ["2025-08-20T10:26:08", "2026-09-10T14:20:58"],
            "y": [[100, 80], [0, 20]],
        })
        self.assertEqual(load.parse_theseus(text), {"Code added in 2025": 80, "Code added in 2026": 20})


class ParseAuthorsLog(unittest.TestCase):
    def test_counts_commits_per_identity(self):
        text = "Ann\tann@x.com\nBob\tbob@x.com\nAnn\tann@x.com\n"
        self.assertEqual(load.parse_authors_log(text), [
            {"name": "Ann", "email": "ann@x.com", "commits": 2},
            {"name": "Bob", "email": "bob@x.com", "commits": 1},
        ])


class ParseSecrets(unittest.TestCase):
    def test_returns_rule_file_and_commit_per_finding(self):
        text = json.dumps([{"RuleID": "aws-access-token", "File": "config.py", "Commit": "abc1234def", "StartLine": 3}])
        self.assertEqual(load.parse_secrets(text), [
            {"rule": "aws-access-token", "file": "config.py", "commit": "abc1234", "line": 3},
        ])

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
                "maat-coupling.csv": "entity,coupled,degree,average-revs\n",
                "maat-age.csv": "entity,age-months\na.py,0\n",
                "maat-authors.csv": "entity,n-authors,n-revs\na.py,1,3\n",
                "repo-health.txt": "",
                "secrets.json": "[]",
                "activity.json": json.dumps({"by_weekday": [1, 0, 0, 0, 0, 0, 0], "by_hour": [0] * 24, "by_month": {"2026-01": 1}, "authors": {}}),
                "theseus/cohorts.json": json.dumps({"labels": ["Code added in 2026"], "ts": ["t"], "y": [[10]]}),
                "theseus/authors.json": json.dumps({"labels": ["Ann"], "ts": ["t"], "y": [[10]]}),
            }
            for name, text in files.items():
                with open(os.path.join(out, name), "w") as fh:
                    fh.write(text)
            r = load.load_report(out)
        self.assertEqual(r["meta"]["name"], "demo")
        self.assertEqual(r["size"]["total_code"], 10)
        self.assertEqual(r["revisions"][0]["entity"], "a.py")
        self.assertEqual(r["coupling"], [])
        self.assertEqual(r["cohorts"], {"Code added in 2026": 10})
        self.assertEqual(r["theseus_authors"], {"Ann": 10})
        self.assertEqual(r["sizer"], [])
        self.assertEqual(r["secrets"], [])
        self.assertEqual(r["activity"]["by_month"], {"2026-01": 1})
        self.assertEqual(r["out_dir"], out)

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

    def test_missing_optional_file_gives_empty_value(self):
        import tempfile
        with tempfile.TemporaryDirectory() as out:
            with open(f"{out}/meta.json", "w") as fh:
                fh.write(json.dumps({"name": "demo", "commits": 0, "identities": []}))
            r = load.load_report(out)
        self.assertEqual(r["revisions"], [])
        self.assertEqual(r["activity"], {})
        self.assertEqual(r["cohorts"], {})
        self.assertEqual(r["size"]["languages"], [])


if __name__ == "__main__":
    unittest.main()

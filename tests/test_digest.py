"""findings.json: the digest of a report a run writes into its output directory (gitmole/digest.py)."""
import json
import os
import tempfile
import unittest

from gitmole import cli, digest, findings, load, render, run
from tests.test_render import rendered, sample_report
from tests.test_section import _contents, _main, _out_dir


def secret_report():
    r = sample_report()
    r["out_dir"] = "/abs/machine/path/analysis-demo"
    r["meta"].update({"path": "/abs/machine/clone", "steps": {"scc": "run", "betterleaks": "run"}, "step_seconds": {"scc": 1.25}, "step_peak_mb": {"scc": 80},
                      "run": {"commit": "540ee5b560cc6e775e11317048a13cc7e355bf91", "gitmole": "0.44.0", "tools": {"git": "2.55.0"}, "options": {"ignore": [], "ignore_data": False, "deep": False}}})
    r["secrets"] = [{"rule": "aws-access-token", "file": "static/a.html", "commit": "abc1234", "line": 3, "fingerprint": "abc1234:static/a.html:aws-access-token:3",
                     "value": "hash-of-AKIAQWERTYUIOPASDFGH", "placeholder": False, "confidence": "high", "at_head": True},
                    {"rule": "aws-access-token", "file": "static/a.html", "commit": "def5678", "line": 9, "fingerprint": "def5678:static/a.html:aws-access-token:9",
                     "value": "hash-of-AKIAQWERTYUIOPASDFGH", "placeholder": False, "confidence": "low", "at_head": False},
                    {"rule": "generic-api-key", "file": "static/b.html", "commit": "abc1234", "line": 1, "fingerprint": "abc1234:static/b.html:generic-api-key:1",
                     "value": "hash-of-1.2.3", "placeholder": True, "confidence": "low", "at_head": True}]
    r["hygiene"] = {"actions": {"unpinned": [{"file": ".github/workflows/ci.yml", "uses": "a/b@v1"}], "unpinned_count": 14, "pinned": 65, "origin": {"host": "github.com", "owner": "demo"}},
                    "updates": {"tool": "renovate", "covered": ["gomod", "npm"], "uncovered": []}, "trojan": {"files": 675, "bidi": [], "bidi_count": 0}}
    return r


class Digest(unittest.TestCase):
    def test_it_holds_the_conclusions_under_the_exports_keys_and_shapes(self):
        r = secret_report()
        found = findings.evaluate(r)
        made, full = digest.build(r, found), render.to_json(r, found)
        self.assertEqual(sorted(made), ["dependencies", "findings", "hygiene", "meta", "not_computed", "osps", "secret_counts", "summary", "watch"])
        for key in ("findings", "watch", "osps", "not_computed"):
            self.assertEqual(made[key], full[key], f"{key}: the export's own rows")
        self.assertTrue(found, "the fixture has a secret in source")
        self.assertEqual(made["summary"], render.summary(r), "the header's numbers, as the portfolio export's row for a repository")
        self.assertEqual(made["meta"], {"steps": r["meta"]["steps"], "run": r["meta"]["run"]}, "what ran and with which tools")
        self.assertEqual(made["dependencies"], {"status": "scanned", "packages": 151, "database_date": "2026-09-16", "sources_count": 2, "vulnerable_count": 0})

    def test_a_backtest_is_carried_when_the_report_has_one(self):
        from unittest import mock
        r = secret_report()
        with mock.patch.object(render.watch, "backtest", return_value={"hits": 3, "listed": 15}):
            self.assertEqual(digest.build(r, [])["watch_backtest"], {"hits": 3, "listed": 15})

    def test_a_list_is_its_length_and_the_steps_own_count_wins(self):
        made = digest.build(secret_report(), [])["hygiene"]
        self.assertEqual(made["actions"], {"unpinned_count": 14, "pinned": 65, "origin": {"host": "github.com", "owner": "demo"}}, "hygiene.json caps the list and counts all of it")
        self.assertEqual(made["updates"], {"tool": "renovate", "covered_count": 2, "uncovered_count": 0})
        self.assertEqual(made["trojan"], {"files": 675, "bidi_count": 0}, "a check that passed says what it looked at and that it found nothing")

    def test_the_secrets_scan_is_counts_and_never_a_value_a_line_or_a_fingerprint(self):
        r = secret_report()
        text = digest.dumps(r, findings.evaluate(r))
        self.assertEqual(json.loads(text)["secret_counts"], {"scanned": True, "values": 1, "places": 2, "at_head": {"places": 1, "high_confidence": 1},
                                                           "history_only": {"places": 1, "high_confidence": 0}, "unplaced": {"places": 0, "high_confidence": 0}, "placeholders": 1})
        for row in r["secrets"]:
            for key in ("value", "fingerprint"):
                self.assertNotIn(row[key], text, key)
        self.assertNotIn("fingerprint\"", text)
        r["secrets"], r["secrets_scanned"] = [], False
        self.assertEqual(digest.build(r, [])["secret_counts"]["scanned"], False, "a scan that did not run is not a scan that found nothing")

    def test_it_is_a_function_of_the_commit(self):
        r = secret_report()
        text = digest.dumps(r, findings.evaluate(r))
        for machine in ("/abs/machine", "step_seconds", "step_peak_mb", "1.25", "ann@x.com", "bob@x.com", "out_dir", "envelope"):
            self.assertNotIn(machine, text)
        self.assertEqual(text, digest.dumps(secret_report(), findings.evaluate(secret_report())))
        self.assertEqual(text, json.dumps(json.loads(text), sort_keys=True, ensure_ascii=False, separators=(",", ":")) + "\n", "sorted keys, one line")
        self.assertNotEqual(digest.FILE, "report.json", "the name the docs teach for the full export")

    def test_a_run_writes_it_and_a_reused_directory_starts_without_the_last_one(self):
        self.assertIn(digest.FILE, run.OUTPUTS)
        with tempfile.TemporaryDirectory() as out:
            path = digest.write(out, secret_report(), [])
            self.assertEqual(os.listdir(out), [digest.FILE], "written whole: no temporary file is left")
            with open(path, encoding="utf-8") as fh:
                self.assertEqual(fh.read(), digest.dumps(secret_report(), []))
            run.clear_outputs(out)
            self.assertEqual(os.listdir(out), [])

    def test_a_re_render_writes_nothing_and_reads_a_directory_that_holds_one(self):
        with tempfile.TemporaryDirectory() as out:
            _out_dir(out)
            before = _contents(out)
            rc, text = _main([out, "--no-run"])
            self.assertEqual(rc, 0)
            self.assertEqual(_contents(out), before, "--no-run reads a directory and writes nothing into it")
            self.assertIn(render.RERENDER, text)
            self.assertNotIn(digest.FILE, text, "no file, no pointer")
            report = load.load_report(out)
            digest.write(out, report, findings.evaluate(report))
            self.assertEqual(json.dumps(load.load_report(out), sort_keys=True, default=str), json.dumps(report, sort_keys=True, default=str), "the file is no input of the report")
            rc, text = _main([out, "--no-run"])
            self.assertEqual((rc, text.splitlines()[-2:]), (0, [render.RERENDER_DIGEST, out]), "named once it exists, in the re-render line's place")
            rc, md = _main([out, "--no-run", "--markdown", "-"])
            self.assertTrue(md.endswith("DIR being the run's output directory; `findings.json` there holds the findings for a script.\n"), md[-200:])
            self.assertNotIn(out, md)
            rc, full = _main([out, "--no-run", "--full"])
            self.assertIn(" findings.json,", " ".join(full.split()), "--full's index of the directory lists it, unmarked")
            for extra in (["--sarif", "-"], ["--json", "-"], ["--section", "hotspots"]):
                self.assertEqual(_main([out, "--no-run"] + extra)[0], 0, extra)

    def test_the_pointer_costs_no_line_and_fits_80_columns(self):
        self.assertLessEqual(len(render.RERENDER_DIGEST), 80)
        with tempfile.TemporaryDirectory() as out:
            r = dict(sample_report(), out_dir=out)
            without = rendered(r, [], width=80)
            open(os.path.join(out, digest.FILE), "w").close()
            named = rendered(r, [], width=80)
        self.assertEqual(len(named.splitlines()), len(without.splitlines()))
        self.assertEqual([a for a, b in zip(without.splitlines(), named.splitlines()) if a != b], [render.RERENDER], "the one line that changes")
        self.assertEqual(named.splitlines()[-2], "gitmole DIR --no-run --full re-renders this run; findings.json is in DIR, below.")


class Plumbing(unittest.TestCase):
    """prometheus's maat-plumbing.csv was 25 bytes, a header, and the export repeated it as an empty key."""

    def test_the_export_has_the_key_only_when_it_has_rows(self):
        r = sample_report()
        r["plumbing"] = []
        self.assertNotIn("plumbing", render.to_json(r, []))
        self.assertNotIn("plumbing", json.loads(render.dumps_json(r, [])))
        r["plumbing"] = [{"entity": "pkg/__init__.py", "n-revs": 25, "tiny-revs": 24}]
        self.assertEqual(render.to_json(r, [])["plumbing"], r["plumbing"])

    def test_an_older_directory_with_the_empty_file_still_loads_and_exports_none(self):
        with tempfile.TemporaryDirectory() as out:
            _out_dir(out)
            with open(os.path.join(out, "maat-plumbing.csv"), "w") as fh:
                fh.write("entity,n-revs,tiny-revs\n")
            old = load.load_report(out)
            self.assertEqual(old["plumbing"], [])
            os.remove(os.path.join(out, "maat-plumbing.csv"))
            new = load.load_report(out)
            self.assertEqual(new["plumbing"], [], "no file reads as no rows")
            self.assertEqual(render.dumps_json(old, []), render.dumps_json(new, []), "with the file or without it, the same export")
            with open(os.path.join(out, "maat-plumbing.csv"), "w") as fh:
                fh.write("entity,n-revs,tiny-revs\na.py,25,24\n")
            self.assertEqual(json.loads(render.dumps_json(load.load_report(out), []))["plumbing"], [{"entity": "a.py", "n-revs": 25, "tiny-revs": 24}])

    def test_every_reader_takes_a_missing_key_as_no_rows(self):
        from gitmole import classify, filetypes
        r = sample_report()
        r.pop("plumbing", None)
        self.assertEqual(filetypes.plumbing_paths(r), set())
        self.assertEqual(classify.Classifier(r).plumbing, set())
        exported = json.loads(render.dumps_json(r, []))
        self.assertEqual(filetypes.plumbing_paths(exported), set(), "an export read back by --compare or --baseline")


if __name__ == "__main__":
    unittest.main()

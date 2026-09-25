"""The agent-hook gate: gitmole --hook reads a hook's JSON on stdin, scores the files it names, and
exits 2 over the threshold, the same shape for Claude Code, Cursor and Gemini CLI."""
import io
import json
import os
import subprocess
import tempfile
import unittest

from rich.console import Console

from gitmole import cli, hook


class Paths(unittest.TestCase):
    def test_file_paths_come_from_the_keys_the_agents_use(self):
        self.assertEqual(hook.paths_in({"tool_name": "Edit", "tool_input": {"file_path": "/r/src/a.py", "old_string": "x"}}, "/r"), ["src/a.py"],
                         "Claude Code: tool_input.file_path, made relative to the repository")
        self.assertEqual(hook.paths_in({"file_path": "/r/src/b.py", "edits": [{"old_string": "x"}]}, "/r"), ["src/b.py"], "Cursor afterFileEdit")
        self.assertEqual(hook.paths_in({"tool_input": {"file_paths": ["/r/a.py", "/r/b.py"]}}, "/r"), ["a.py", "b.py"])
        self.assertEqual(hook.paths_in({"tool_response": {"filePath": "/r/c.py"}}, "/r"), ["c.py"])
        self.assertEqual(hook.paths_in({"tool_input": {"command": "ls"}}, "/r"), [], "a Bash call names no file")
        self.assertEqual(hook.paths_in({"tool_input": {"file_path": "/elsewhere/x.py"}}, "/r"), [], "a file outside the repository is not this repository's risk")
        self.assertEqual(hook.paths_in({"tool_input": {"file_path": "src/rel.py"}}, "/r"), ["src/rel.py"], "a relative path is taken as repository-relative")


class Gate(unittest.TestCase):
    def _repo(self, d):
        def git(*args, **env):
            e = dict(os.environ, GIT_CONFIG_GLOBAL="/dev/null", GIT_CONFIG_SYSTEM="/dev/null", GIT_AUTHOR_NAME="Ann", GIT_AUTHOR_EMAIL="a@x",
                     GIT_COMMITTER_NAME="Ann", GIT_COMMITTER_EMAIL="a@x")
            e.update(env)
            subprocess.run(["git", *args], cwd=d, check=True, capture_output=True, env=e)
        git("init", "-q", "-b", "main")
        with open(os.path.join(d, "a.py"), "w") as fh:
            fh.write("x\n")
        git("add", "-A")
        git("commit", "-q", "-m", "base")

    def _out(self, d):
        out = os.path.join(d, "out")
        os.makedirs(out)
        with open(os.path.join(out, "meta.json"), "w") as fh:
            json.dump({"name": "demo", "path": d, "commits": 30, "identities": [], "last_date": "2026-09-01", "file_types": None}, fh)
        with open(os.path.join(out, "size.json"), "w") as fh:
            json.dump([{"Name": "Python", "Count": 2, "Code": 900, "Comment": 0, "Blank": 0, "Complexity": 10,
                        "Files": [{"Location": "./core/hot.py", "Code": 800, "Complexity": 9}, {"Location": "./core/cold.py", "Code": 100, "Complexity": 1}]}], fh)
        with open(os.path.join(out, "maat-revisions.csv"), "w") as fh:
            fh.write("entity,n-revs\ncore/hot.py,40\ncore/cold.py,2\n")
        with open(os.path.join(out, "maat-coupling.csv"), "w") as fh:
            fh.write("entity,coupled,degree,average-revs\ncore/hot.py,core/cold.py,80,20\ncore/hot.py,CHANGES,90,20\n")
        return out

    def test_the_gate_reads_stdin_scores_the_named_files_and_exits_2_over_the_threshold(self):
        with tempfile.TemporaryDirectory() as d:
            self._repo(d)
            out = self._out(d)
            event = {"hook_event_name": "PostToolUse", "tool_name": "Edit", "tool_input": {"file_path": os.path.join(d, "core/hot.py")}}
            stdout = io.StringIO()
            rc = cli.main([out, "--no-run", "--hook", "--risk-threshold", "50"], console=Console(file=stdout, width=200), stdin=io.StringIO(json.dumps(event)))
            self.assertEqual(rc, 2, "hot.py holds 99% of the repository's revisions × lines: over 50, the edit is blocked")
            printed = json.loads(stdout.getvalue().splitlines()[0])   # the JSON on stdout; what follows is the stderr text, on the same console here
            context = printed["hookSpecificOutput"]["additionalContext"]
            self.assertIn("over the 50% threshold", stdout.getvalue().splitlines()[-1], "the reason also goes to stderr, which is what the agent shows on exit 2")
            self.assertEqual(printed["hookSpecificOutput"]["hookEventName"], "PostToolUse")
            self.assertIn("core/hot.py: 99.4% of the repository's revisions × lines of code (rank 1 of 2, on the watch list)", context)
            self.assertIn("not touched: core/cold.py, which moved in 80% of core/hot.py's changes", context)
            self.assertNotIn("CHANGES", context, "a companion is a scored source file, not a change log every commit touched")
            self.assertIn("total 99.4%, over the 50% threshold", context)
            stdout = io.StringIO()
            rc = cli.main([out, "--no-run", "--hook"], console=Console(file=stdout, width=200), stdin=io.StringIO(json.dumps(event)))
            self.assertEqual(rc, 0, "no threshold: a soft warning only")
            self.assertIn("core/hot.py: 99.4%", json.loads(stdout.getvalue().splitlines()[0])["hookSpecificOutput"]["additionalContext"])

    def test_the_summary_says_what_imports_each_file(self):
        risk = {"files": [{"file": "core/util.py", "score": 0.6, "reasons": ["changed 30 times"], "rank": 2, "watched": True,
                           "dependents": {"direct": 2, "all": 5, "files": ["core/lexer.py", "core/parser.py"]}},
                          {"file": "core/new.py", "score": 0, "reasons": ["changed once"], "reason": "changed once", "rank": None,
                           "dependents": {"direct": 1, "all": 1, "files": ["core/util.py"]}},
                          {"file": "main.py", "score": 0, "reasons": ["changed once"], "reason": "changed once", "rank": None}],
                "total": 0.6, "pool": 9}
        lines = hook.summary(risk)
        self.assertEqual(lines[0], "core/util.py: 0.6% of the repository's revisions × lines of code (rank 2 of 9, on the watch list); "
                                   "changed 30 times; imported by 2 files, 5 counting what imports them")
        self.assertEqual(lines[1], "core/new.py: not scored (changed once); imported by core/util.py")
        self.assertEqual(lines[2], "main.py: not scored (changed once)")

    def test_nothing_to_say_for_a_file_the_list_does_not_score_and_for_no_file(self):
        with tempfile.TemporaryDirectory() as d:
            self._repo(d)
            out = self._out(d)
            stdout = io.StringIO()
            rc = cli.main([out, "--no-run", "--hook", "--risk-threshold", "1"], console=Console(file=stdout, width=200),
                          stdin=io.StringIO(json.dumps({"tool_input": {"file_path": os.path.join(d, "core/cold.py")}})))
            self.assertEqual(rc, 0)
            self.assertIn("core/cold.py: 0.6%", json.loads(stdout.getvalue().splitlines()[0])["hookSpecificOutput"]["additionalContext"])
            stdout = io.StringIO()
            rc = cli.main([out, "--no-run", "--hook"], console=Console(file=stdout, width=200), stdin=io.StringIO(json.dumps({"tool_input": {"command": "ls"}})))
            self.assertEqual(rc, 0)
            self.assertEqual(stdout.getvalue(), "", "no file named: no output, so the agent's hook stays quiet")
            rc = cli.main([out, "--no-run", "--hook"], console=Console(file=stdout, width=200), stdin=io.StringIO("not json"))
            self.assertEqual(rc, 0, "garbage on stdin is not a reason to block an edit")

    def test_files_can_come_as_arguments_for_pre_commit(self):
        with tempfile.TemporaryDirectory() as d:
            self._repo(d)
            out = self._out(d)
            stdout = io.StringIO()
            rc = cli.main([out, "--no-run", "--hook", "--risk-threshold", "50", "--", "core/hot.py"], console=Console(file=stdout, width=200), stdin=io.StringIO(""))
            self.assertEqual(rc, 2)
            self.assertIn("core/hot.py: 99.4%", stdout.getvalue())
            self.assertNotIn("hookSpecificOutput", stdout.getvalue(), "with files on the command line the summary is plain text, for pre-commit's log")

    def test_the_hook_needs_an_output_directory(self):
        c = Console(file=io.StringIO(), width=200)
        rc = cli.main(["owner/repo", "--hook"], console=c, tool_check=lambda **kw: [])
        self.assertEqual(rc, 2)
        self.assertIn("--hook needs --no-run", c.file.getvalue())


if __name__ == "__main__":
    unittest.main()

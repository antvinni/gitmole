import json
import os
import tempfile
import unittest

from gitmole import feedback


class Args:
    """The attributes should_ask reads off a parsed command line."""

    def __init__(self, **kw):
        self.feedback = False
        self.no_run = False
        self.kind = "local"
        for flag in feedback.SCRIPT_FLAGS:
            setattr(self, flag, None)
        for k, v in kw.items():
            setattr(self, k, v)


TODAY = "2026-09-20"


class WhenItAsks(unittest.TestCase):
    def test_a_plain_interactive_run_on_a_fresh_machine(self):
        self.assertTrue(feedback.should_ask(Args(), {}, TODAY, env={}, isatty=True))

    def test_never_without_a_terminal(self):
        self.assertFalse(feedback.should_ask(Args(), {}, TODAY, env={}, isatty=False))

    def test_never_where_the_environment_says_ci(self):
        for name in feedback.CI_VARS:
            with self.subTest(var=name):
                self.assertFalse(feedback.should_ask(Args(), {}, TODAY, env={name: "true"}, isatty=True))

    def test_never_with_an_export_a_gate_or_the_hook(self):
        for flag in feedback.SCRIPT_FLAGS:
            with self.subTest(flag=flag):
                self.assertFalse(feedback.should_ask(Args(**{flag: "x"}), {}, TODAY, env={}, isatty=True),
                                 f"--{flag} is a script's run, and a prompt there hangs it")

    def test_never_in_portfolio_mode_or_a_re_render(self):
        self.assertFalse(feedback.should_ask(Args(kind="owner"), {}, TODAY, env={}, isatty=True))
        self.assertFalse(feedback.should_ask(Args(no_run=True), {}, TODAY, env={}, isatty=True))

    def test_the_kill_switch_beats_everything_including_the_flag(self):
        env = {feedback.OFF_VAR: "1"}
        self.assertFalse(feedback.should_ask(Args(), {}, TODAY, env=env, isatty=True))
        self.assertFalse(feedback.should_ask(Args(feedback=True), {}, TODAY, env=env, isatty=True))

    def test_the_flag_asks_even_where_a_run_would_not(self):
        self.assertTrue(feedback.should_ask(Args(feedback=True, json="r.json"), {"declined": True}, TODAY,
                                            env={"CI": "true"}, isatty=False))


class OnTerminal(unittest.TestCase):
    """The streams' own isatty decides, not rich's is_terminal: FORCE_COLOR turns that on for a redirected file."""

    class Stream:
        def __init__(self, tty):
            self.tty = tty

        def isatty(self):
            return self.tty

    def test_both_stdin_and_the_output_must_be_terminals(self):
        from unittest import mock
        with mock.patch("sys.stdin", self.Stream(True)):
            self.assertTrue(feedback.on_terminal(self.Stream(True)))
            self.assertFalse(feedback.on_terminal(self.Stream(False)), "gitmole . > report.txt")
        with mock.patch("sys.stdin", self.Stream(False)):
            self.assertFalse(feedback.on_terminal(self.Stream(True)), "input from a pipe")

    def test_a_closed_stdin_or_a_stream_without_isatty_is_no_terminal(self):
        from unittest import mock
        with mock.patch("sys.stdin", None):
            self.assertFalse(feedback.on_terminal(self.Stream(True)), "started with fd 0 closed: sys.stdin is None")
        with mock.patch("sys.stdin", self.Stream(True)):
            self.assertFalse(feedback.on_terminal(object()))

    def test_unattended_is_a_ci_variable_or_a_script_flag(self):
        self.assertFalse(feedback.unattended(Args(), env={}))
        self.assertTrue(feedback.unattended(Args(), env={"BUILDKITE": "true"}))
        self.assertTrue(feedback.unattended(Args(fail_on="critical"), env={}))


class Cadence(unittest.TestCase):
    def test_once_on_a_machine(self):
        self.assertTrue(feedback.due({}, TODAY))
        self.assertFalse(feedback.due({"asked": TODAY}, TODAY), "asked once and not answered: never again")

    def test_a_decline_is_remembered_for_good(self):
        self.assertFalse(feedback.due({"declined": True, "asked": "2020-01-01"}, TODAY))

    def test_someone_who_answered_is_asked_again_after_ninety_days(self):
        self.assertFalse(feedback.due({"asked": "2026-06-01", "answered": "2026-06-01"}, "2026-08-01"))
        self.assertTrue(feedback.due({"asked": "2026-06-01", "answered": "2026-06-01"}, "2026-09-01"))


class Asking(unittest.TestCase):
    def findings(self):
        return [{"severity": "info", "title": "Debt in hotspots", "rule": {"id": "debt_in_hotspots"}, "summary": True,
                 "unjudged": True},
                {"severity": "warning", "title": "Bus factor of one", "rule": {"id": "bus_factor"}},
                {"severity": "critical", "title": "2 secrets in history", "rule": {"id": "secrets_in_source"}},
                {"severity": "info", "title": "Committed binaries", "rule": {"id": "committed_binaries"}}]

    def drive(self, replies):
        said = iter(replies)
        lines = []
        return feedback.ask(self.findings(), lines.append, lambda text: next(said, "")), lines

    def test_it_asks_about_what_the_report_spelled_out_worst_first(self):
        answers, _ = self.drive(["y", "y", "n", "w"])
        self.assertEqual([a["rule"] for a in answers], ["secrets_in_source", "bus_factor", "committed_binaries"])
        self.assertEqual([(a["true"], a["actionable"]) for a in answers],
                         [(True, True), (True, False), (False, False)])

    def test_a_summarised_or_unjudged_finding_is_never_asked_about(self):
        answers, _ = self.drive(["y", "y", "y", "y", "y"])
        self.assertNotIn("debt_in_hotspots", [a["rule"] for a in answers], "it was one line among several")

    def test_enter_declines_and_nothing_is_asked(self):
        answers, _ = self.drive([""])
        self.assertEqual(answers, [])

    def test_q_stops_and_keeps_what_was_answered(self):
        answers, _ = self.drive(["y", "y", "q", "y"])
        self.assertEqual([a["rule"] for a in answers], ["secrets_in_source"])

    def test_an_unrecognised_reply_is_a_skip_rather_than_a_guess(self):
        answers, _ = self.drive(["y", "?", "n"])
        self.assertEqual([a["rule"] for a in answers], ["bus_factor"])

    def test_no_findings_means_no_invitation(self):
        asked = []
        self.assertEqual(feedback.ask([], asked.append, lambda text: asked.append(text) or "y"), [])
        self.assertEqual(asked, [])


class Payload(unittest.TestCase):
    def report(self):
        """The shapes a real export carries: size.languages from scc, total_files, meta.commits."""
        return {"meta": {"name": "secret-project", "commits": 4321},
                "size": {"total_files": 640, "total_code": 910,
                         "languages": [{"name": "Python", "code": 900}, {"name": "Go", "code": 10}],
                         "files": {"src/pay.py": {"code": 900}}}}

    def test_it_holds_the_answers_the_version_and_three_coarse_facts(self):
        data = feedback.payload([{"rule": "bus_factor", "severity": "warning", "true": True, "actionable": True}],
                                self.report(), TODAY, "0.33.0")
        self.assertEqual(set(data), set(feedback.PAYLOAD_KEYS))
        self.assertEqual((data["language"], data["files"], data["commits"]), ("Python", "100-1000", "1000-10000"))

    def test_the_file_carries_nothing_but_the_closed_list(self):
        data = feedback.payload([], self.report(), TODAY, "0.33.0")
        data["meta"] = self.report()["meta"]          # a caller adding more does not get it written
        with tempfile.TemporaryDirectory() as d:
            path = feedback.write(os.path.join(d, feedback.FILE_NAME), data)
            with open(path, encoding="utf-8") as fh:
                text = fh.read()
        self.assertEqual(set(json.loads(text)), set(feedback.PAYLOAD_KEYS))
        for leak in ("secret-project", "src/pay.py", "4321", "640"):
            self.assertNotIn(leak, text, "no name, path or exact count leaves the machine")

    def test_an_answer_carries_only_the_rule_the_severity_and_the_verdict(self):
        answers, _ = Asking().drive(["y", "y"])
        self.assertEqual(set(answers[0]), set(feedback.ANSWER_KEYS))

    def test_how_to_send_names_both_ways_and_neither_is_gitmole(self):
        lines = feedback.how_to_send("/tmp/gitmole-feedback.json", "0.33.0")
        self.assertTrue(any("gh issue create" in line for line in lines))
        self.assertTrue(any(feedback.ISSUE_URL in line for line in lines))


class Wiring(unittest.TestCase):
    """cli._feedback: where the prompt happens, what it writes, and that a run never breaks over it."""

    def run_it(self, answers, env=None, **kw):
        """A test has no terminal, so the explicit flag stands in for the interactive path."""
        import io
        from unittest.mock import patch
        from rich.console import Console
        from gitmole import cli
        err = Console(file=io.StringIO(), width=100, color_system=None)
        with tempfile.TemporaryDirectory() as d:
            args = Args(out=d, feedback=True, **kw)
            with patch.dict(os.environ, {"GITMOLE_CACHE": os.path.join(d, "cache"), **(env or {})}):
                cli._feedback(Payload().report(), [], args, err, err, ask=lambda *a: answers)
            written = os.path.join(d, feedback.FILE_NAME)
            body = open(written, encoding="utf-8").read() if os.path.exists(written) else None
        return body, err.file.getvalue()

    def answers(self):
        return [{"rule": "bus_factor", "severity": "warning", "true": True, "actionable": True}]

    def test_answers_are_written_beside_the_output_and_both_ways_to_send_are_printed(self):
        body, out = self.run_it(self.answers())
        self.assertIsNotNone(body, "the file lands in the output directory")
        self.assertEqual(set(json.loads(body)), set(feedback.PAYLOAD_KEYS))
        self.assertIn("gh issue create", out)
        self.assertIn(feedback.ISSUE_URL, out)

    def test_a_decline_writes_no_file_and_says_nothing(self):
        body, out = self.run_it([])
        self.assertIsNone(body)
        self.assertEqual(out.strip(), "")

    def test_the_kill_switch_stops_even_the_flag(self):
        body, out = self.run_it(self.answers(), env={feedback.OFF_VAR: "1"})
        self.assertIsNone(body)
        self.assertEqual(out.strip(), "")

    def test_the_state_remembers_the_decline(self):
        import io
        from unittest.mock import patch
        from rich.console import Console
        from gitmole import cli
        with tempfile.TemporaryDirectory() as d:
            cache = os.path.join(d, "cache", "structure")
            with patch.dict(os.environ, {"GITMOLE_CACHE": cache}):
                err = Console(file=io.StringIO(), width=100, color_system=None)
                cli._feedback(Payload().report(), [], Args(out=d, feedback=True), err, err, ask=lambda *a: [])
                state = feedback.read_state(feedback.state_path())
                self.assertTrue(state.get("declined"))
                self.assertFalse(feedback.should_ask(Args(), state, TODAY, env={}, isatty=True),
                                 "and it is not asked again")


class Buckets(unittest.TestCase):
    def test_counts_become_bands(self):
        self.assertEqual([feedback.bucket(n) for n in (0, 99, 100, 2_000, 50_000, 900_000)],
                         ["0-100", "0-100", "100-1000", "1000-10000", "10000-100000", "100000+"])


if __name__ == "__main__":
    unittest.main()

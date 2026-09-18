import json
import os
import subprocess
import sys
import tempfile
import unittest

from gitmole import provenance

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class Repo:
    def __init__(self, d):
        self.d = d
        self.git("init", "-q", "-b", "main")

    def git(self, *args, name="Ann", email="ann@x.com", date="2026-01-05T10:00:00"):
        date = date + "+00:00"   # explicit: the hour count must not depend on the machine's time zone
        env = dict(os.environ, GIT_CONFIG_GLOBAL="/dev/null", GIT_CONFIG_SYSTEM="/dev/null", GIT_AUTHOR_NAME=name, GIT_AUTHOR_EMAIL=email,
                   GIT_COMMITTER_NAME=name, GIT_COMMITTER_EMAIL=email, GIT_AUTHOR_DATE=date, GIT_COMMITTER_DATE=date)
        return subprocess.run(["git", *args], cwd=self.d, check=True, capture_output=True, env=env, text=True).stdout

    def commit(self, path, text, message, **who):
        full = os.path.join(self.d, path)
        os.makedirs(os.path.dirname(full) or self.d, exist_ok=True)
        with open(full, "a") as fh:
            fh.write(text)
        self.git("add", "-A", "-f", path, **who)   # -f: a personal excludes file may ignore .claude/settings.local.json
        self.git("commit", "-q", "-m", message, **who)


def history(d):
    r = Repo(d)
    r.commit("a.py", "1\n", "feat: start", date="2026-01-05T10:00:00")
    r.commit("a.py", "2\n", "feat: helper\n\nCo-authored-by: Helper Agent <agent-bot@tools.example>", date="2026-01-05T10:02:00")
    r.commit("b.py", "3\n", "feat: more\n\nAssisted-by: SomeModel v2\nSigned-off-by: Ann <ann@x.com>", date="2026-01-05T10:04:00")
    r.commit("a.py", "4\n", "fix: a bug", date="2026-01-05T10:06:00")
    r.commit("c.py", "5\n", "pair work\n\nCo-authored-by: Bob <bob@x.com>", date="2026-01-05T10:08:00")
    r.commit("c.py", "6\n", "Bob's own", name="Bob", email="bob@x.com", date="2026-03-01T12:00:00")
    r.commit("d.py", "7\n", "Revert \"feat: helper\"", date="2026-03-02T09:00:00")
    r.commit("e.py", "8\n", "odd\n\nCo-authored-by: Ghost <ghost@x.com>\nSigned-off-by: Ghost <ghost@x.com>", date="2026-04-01T09:00:00")
    r.commit("f.py", "9\n", "see the docs\n\nhttps://example.com/x\nNOTE: prose that ends a message", date="2026-04-02T09:00:00")
    return r


class Trailers(unittest.TestCase):
    def test_inventory_and_the_co_author_who_never_authors(self):
        with tempfile.TemporaryDirectory() as d:
            history(d)
            commits = provenance.read_commits(d)
            out = provenance.trailers(commits)
        self.assertEqual(out["commits"], 9)
        self.assertEqual(out["keys"], {"Co-authored-by": 3, "Signed-off-by": 2, "Assisted-by": 1}, "a URL and a line of prose are not trailers")
        self.assertEqual(out["with_any"], 4)
        self.assertEqual(out["never_author"], [{"name": "Ghost", "email": "ghost@x.com", "commits": 1},
                                               {"name": "Helper Agent", "email": "agent-bot@tools.example", "commits": 1}],
                         "Bob co-authors and also authors, so he is not listed")
        self.assertEqual(out["signoff_by_co_author"], [{"name": "Ghost", "email": "ghost@x.com", "commits": 1}],
                         "a sign-off by an identity that only ever co-authors: what the kernel's policy forbids agents")


class Cohorts(unittest.TestCase):
    def test_trailer_cohort_against_the_rest(self):
        with tempfile.TemporaryDirectory() as d:
            history(d)
            commits = provenance.read_commits(d)
            out = provenance.cohort(commits, provenance.trailers(commits))
        self.assertEqual(out["definition"], "an Assisted-by trailer, or a co-author who never authors a commit here")
        self.assertEqual((out["cohort"]["commits"], out["rest"]["commits"]), (3, 6))
        self.assertEqual(out["cohort"]["reverted"], 1, "the helper commit was reverted by subject")
        self.assertEqual(out["rest"]["reverted"], 0)
        self.assertEqual(out["cohort"]["fixes"], 0)
        self.assertEqual(out["rest"]["fixes"], 1)
        self.assertEqual(out["cohort"]["retouched"], 1, "a.py changed again two minutes after the helper commit")
        self.assertEqual(out["share"], 0.333)


class Shape(unittest.TestCase):
    def test_neutral_descriptors_of_how_commits_arrive(self):
        with tempfile.TemporaryDirectory() as d:
            history(d)
            out = provenance.shape(provenance.read_commits(d))
        self.assertEqual(out["burst_share"], 0.556, "five of nine commits land in a run of five or more within ten minutes of each other")
        self.assertEqual(out["conventional_share"], 0.444, "feat: x3 and fix: x1")
        self.assertEqual(out["hours_used"], 3)
        self.assertNotIn("ai", json.dumps(out).lower().replace("assisted", ""), "a descriptor is never labelled")


class Agents(unittest.TestCase):
    def test_agent_configuration_as_a_declared_surface(self):
        with tempfile.TemporaryDirectory() as d:
            r = Repo(d)
            r.commit("AGENTS.md", "rules\n", "agents", date="2025-01-01T10:00:00")
            r.commit(".claude/settings.json", json.dumps({"hooks": {"PostToolUse": []}, "permissions": {"defaultMode": "bypassPermissions"}}), "settings",
                     date="2025-01-02T10:00:00")
            r.commit(".claude/settings.local.json", "{}", "oops", date="2025-01-03T10:00:00")
            r.commit(".mcp.json", json.dumps({"mcpServers": {"db": {"command": "x", "env": {"DB_URL": "postgres://u:" + "p4ss" * 4 + "@h/db",
                                                                                            "TOKEN": "${TOKEN}", "MODE": "readonly"}},
                                                             "web": {"command": "y"}}}), "mcp", date="2025-01-04T10:00:00")
            for i in range(5):
                r.commit("src.py", f"{i}\n", f"work {i}", date=f"2026-0{i + 1}-01T10:00:00")
            out = provenance.agents(d)
        self.assertEqual(out["instructions"], [{"file": "AGENTS.md", "last": "2025-01-01", "commits_behind": 8}])
        self.assertEqual(out["guardrails"], [".claude/settings.json"])
        self.assertEqual(out["approval_disabled"], [{"file": ".claude/settings.json", "setting": "permissions.defaultMode=bypassPermissions"}])
        self.assertEqual(out["local_settings"], [".claude/settings.local.json"])
        self.assertEqual(out["mcp"], [{"file": ".mcp.json", "servers": 2, "literal_env": [{"server": "db", "key": "DB_URL"}]}],
                         "a ${VAR} reference is where a secret is read from; a short word is configuration; the values themselves are never written")
        self.assertNotIn("p4ss", json.dumps(out))


class Lines(unittest.TestCase):
    def _write(self, r, path, text, message, date):
        with open(os.path.join(r.d, path), "w") as fh:
            fh.write(text)
        r.git("add", "-A", date=date)
        r.git("commit", "-q", "-m", message, date=date)

    def test_moved_and_churned_lines_by_year_and_cohort(self):
        body = "".join(f"def function_number_{i}(argument):\n    return argument * {i} + compute_offset({i})\n" for i in range(6))
        with tempfile.TemporaryDirectory() as d:
            r = Repo(d)
            self._write(r, "c.py", "unrelated_value = compute_something()\n", "start", "2024-06-01T10:00:00")   # the year before
            self._write(r, "a.py", body + "keep_this_line = 1\ntemporary_line = 2\n", "add a", "2025-06-01T10:00:00")
            self._write(r, "a.py", body + "keep_this_line = 1\n", "drop the temporary line\n\nAssisted-by: Tool", "2025-06-05T10:00:00")
            with open(os.path.join(d, "c.py"), "a") as fh:
                fh.write(body)
            self._write(r, "a.py", "keep_this_line = 1\n", "move the functions into c.py", "2025-07-01T10:00:00")
            commits = provenance.read_commits(d)
            marked = provenance.marker(provenance.trailers(commits))
            out = provenance.lines(d, commits[-1]["time"], {c["hash"] for c in commits if marked(c)})
        last, before = out["windows"]
        self.assertEqual((before["commits"], before["added"]), (1, 1))
        self.assertEqual(last["added"], len(body.splitlines()) * 2 + 2)
        self.assertEqual(last["churned"], 1, "the temporary line went within four days; the kept line and the moved functions are not churn")
        self.assertEqual(last["moved"], len(body.splitlines()), "git marks the functions as moved from a.py to b.py")
        self.assertEqual(out["cohort"]["marked"]["commits"], 1)
        self.assertEqual(out["cohort"]["rest"]["churned"], 1, "the churn belongs to the commit that added the line")


class WatchHits(unittest.TestCase):
    def test_each_cohort_counts_its_commits_touching_a_watched_file(self):
        with tempfile.TemporaryDirectory() as d:
            history(d)
            commits = provenance.read_commits(d)
        inv = provenance.trailers(commits)
        out = provenance.cohort(commits, inv, {"a.py"})
        self.assertEqual((out["cohort"]["watch"], out["rest"]["watch"]), (1, 2), "the helper commit is marked; start and the fix are not")
        self.assertNotIn("watch", provenance.cohort(commits, inv)["rest"], "no watch list, no count")


class Step(unittest.TestCase):
    def test_the_step_writes_provenance_json(self):
        with tempfile.TemporaryDirectory() as d:
            history(d)
            out = os.path.join(d, "out")
            os.makedirs(out)
            p = subprocess.run([sys.executable, "-m", "gitmole.provenance", out], cwd=d, capture_output=True, text=True,
                               env=dict(os.environ, PYTHONPATH=ROOT, GIT_CONFIG_GLOBAL="/dev/null", GIT_CONFIG_SYSTEM="/dev/null"))
            self.assertEqual(p.returncode, 0, p.stderr)
            with open(os.path.join(out, "provenance.json")) as fh:
                data = json.load(fh)
        self.assertEqual(set(data), {"trailers", "cohort", "shape", "agents", "lines"})


if __name__ == "__main__":
    unittest.main()

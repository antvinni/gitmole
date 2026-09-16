# History Insights Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add five history-based analyses to gitmole (reverts, knowledge loss, change risk, complexity trend, watch-list backtest), each shipped as its own pull request.

**Architecture:** Each analysis is a small pure module over the report dict that `load.load_report` builds, plus a finding in `findings.py` and a mark in `render.py`. Two of them (trend, backtest) add a pipeline step: a standalone script run by `run.execute` that writes files into the output directory, which the loader then reads. Nothing new lands in the default terminal report beyond the four marks the spec allows.

**Tech Stack:** Python 3.9 stdlib, rich (already a dependency), git, scc. Tests with `unittest`.

**Spec:** `docs/superpowers/specs/2026-09-16-history-insights-design.md`

## Global Constraints

- No new Python dependency. `pyproject.toml` `dependencies` stays `["rich>=13", "lizard>=1.24"]`.
- Every new output file is added to `run.OUTPUTS` (or `OUTPUT_GLOBS`), and `load.load_report` gives an empty value when it is missing.
- Every finding is built with `findings._f(severity, title, statement, advice)`; the advice names a file, area or person.
- Test files (`filetypes.is_test_path`) are left out of any finding that names a file. Bots (`meta["bots"]`, `identity.is_bot`) are left out of every count of people.
- The default report gains only: a reverts pulse phrase, a `trend` column on Hotspots, one backtest caption under the watch list, and the change-risk section when `--risk` is passed.
- Reference date: `GITMOLE_NOW` when set, otherwise today (already handled by `cli.main`; scripts take `--now`).
- Run the whole suite with `python3 -m unittest discover -s tests -t .` before every commit. It must print `OK`.
- One PR per part. Branch from `main` for each. Commit messages end with the attribution line the session's system reminder gives.
- Test values that look like secrets must be built at runtime, never written as literals (GitHub push protection blocks them).

## Conventions the executor must know

- The report dict (`load.load_report`) has keys: `meta`, `size` (`{"languages", "total_code", "total_files", "files": {path: {"code", "complexity"}}}`), `revisions`, `coupling`, `authors`, `age`, `ownership`, `fixes`, `sizer`, `cohorts`, `theseus_authors` (name → surviving lines), `secrets`, `activity`, `functions`, `duplicates`, `out_dir`.
- `meta` has `name`, `path`, `branch`, `commits`, `first_date`, `last_date` (`YYYY-MM-DD`), `identities`, `bots` (`[{"name", "commits"}]`), `aliases`, optional `since`, `file_types`, `age`, `functions`, `plots`.
- `activity` (from `maat.activity`) has `by_weekday`, `by_hour`, `by_month`, `net_by_year`, `authors` (`name → {"commits", "added", "deleted", "first", "last"}`), `timeline`, `fix_commits`, `window`.
- Tests for findings build reports with `report(**overrides)` in `tests/test_findings.py`; render tests use `sample_report()` and `rendered(report, findings, width=120, full=False)` in `tests/test_render.py`; watch tests use `report(**overrides)` in `tests/test_watch.py`.
- Pipeline steps are dicts `{"name", "argv", "stdout", "deps"}` built in `run.plan`; `run.execute` runs them with `cwd=repo_dir`.
- The golden test (`tests/test_golden.py`) compares a real run against `tests/golden/report.txt`; regenerate with `UPDATE_GOLDEN=1 python3 -m unittest tests.test_golden` and review `git diff tests/golden/report.txt`.
- Manual check for every part: `python3 -m gitmole /Users/antonvinni/workspace/github.com/mealie-recipes/mealie --out /tmp/claude/mealie-check` and read the new lines.

---

# Part 1: Reverts (PR 1)

## File structure

- Modify `gitmole/maat.py`: `is_revert`, revert counts in `activity()`.
- Modify `gitmole/findings.py`: `reverts` rule.
- Modify `gitmole/render.py`: pulse phrase.
- Modify `README.md`: one sentence in the findings list.
- Tests: `tests/test_maat.py`, `tests/test_findings.py`, `tests/test_render.py`.

### Task 1.1: Count reverts in the change analysis

**Files:**
- Modify: `gitmole/maat.py` (near `is_fix`, and `activity()`)
- Test: `tests/test_maat.py`

**Interfaces:**
- Produces: `maat.is_revert(subject: str) -> bool`; `activity()` gains `"revert_commits": int` and `"reverted": {path: int}` (paths sorted by count desc then name).

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_maat.py` (before the `if __name__` block):

```python
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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python3 -m unittest tests.test_maat.Reverts -v`
Expected: 3 failures/errors, `AttributeError: module 'gitmole.maat' has no attribute 'is_revert'` and `KeyError: 'revert_commits'`.

- [ ] **Step 3: Implement**

In `gitmole/maat.py`, after `is_fix`:

```python
def is_revert(subject: str) -> bool:
    """git's own revert subject: `Revert "..."`. Case-sensitive, the quote is not required."""
    return (subject or "").startswith("Revert ")
```

In `activity()`, extend the initialisers and the loop, and the returned dict:

```python
    by_weekday, by_hour, by_month, net_by_year = [0] * 7, [0] * 24, Counter(), Counter()
    authors, timeline, fix_commits = {}, defaultdict(Counter), 0
    revert_commits, reverted = 0, Counter()
    for c in commits:
        ...existing body...
        fix_commits += is_fix(c.get("subject", ""))
        if is_revert(c.get("subject", "")):
            revert_commits += 1
            for p, _, _ in c["files"]:
                reverted[p] += 1
        ...
    return {"by_weekday": by_weekday, "by_hour": by_hour, "by_month": dict(sorted(by_month.items())),
            "net_by_year": dict(sorted(net_by_year.items())), "authors": authors,
            "timeline": {a: dict(sorted(m.items())) for a, m in timeline.items()}, "fix_commits": fix_commits,
            "revert_commits": revert_commits,
            "reverted": dict(sorted(reverted.items(), key=lambda kv: (-kv[1], kv[0])))}
```

- [ ] **Step 4: Run the tests**

Run: `python3 -m unittest tests.test_maat -v`
Expected: all pass (the existing `Activity` test compares specific keys, not the whole dict).

- [ ] **Step 5: Commit**

```bash
git add gitmole/maat.py tests/test_maat.py
git commit -m "Count revert commits and the files they back out"
```

### Task 1.2: The Reverts finding

**Files:**
- Modify: `gitmole/findings.py` (new rule, add to `RULES` after `bug_magnets`)
- Test: `tests/test_findings.py`

**Interfaces:**
- Consumes: `report["activity"]["revert_commits"]`, `report["activity"]["reverted"]`, `report["meta"]["commits"]`.
- Produces: `findings.reverts(report, min_share=0.05, min_count=5, warn_share=0.10) -> list`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_findings.py` before `class Advice`:

```python
class Reverts(unittest.TestCase):
    def _report(self, reverts, commits=100, reverted=None):
        r = report()
        r["meta"]["commits"] = commits
        r["activity"] = {"revert_commits": reverts, "reverted": reverted or {}}
        return r

    def test_info_at_five_percent_names_the_most_reverted_file(self):
        f = findings.reverts(self._report(5, reverted={"core/a.py": 3, "core/b.py": 2, "tests/t.py": 4}))
        self.assertEqual(f[0]["severity"], "info")
        self.assertEqual(f[0]["title"], "Reverts")
        self.assertIn("5 of 100 commits are reverts; core/a.py was reverted 3 times, core/b.py twice", f[0]["detail"])
        self.assertEqual(f[0]["advice"], "Add a check before merge for core/a.py; it is the file most often backed out.")

    def test_five_reverts_fire_even_below_five_percent(self):
        self.assertEqual(len(findings.reverts(self._report(5, commits=1000, reverted={"a.py": 5}))), 1)
        self.assertEqual(findings.reverts(self._report(4, commits=1000, reverted={"a.py": 4})), [])

    def test_warning_at_ten_percent(self):
        self.assertEqual(findings.reverts(self._report(10, reverted={"a.py": 10}))[0]["severity"], "warning")

    def test_only_test_files_reverted_says_so(self):
        f = findings.reverts(self._report(6, reverted={"tests/t.py": 6}))
        self.assertEqual(f[0]["advice"], "Look at why they were backed out; only test files were touched.")

    def test_nothing_without_reverts_or_activity(self):
        self.assertEqual(findings.reverts(self._report(0)), [])
        self.assertEqual(findings.reverts(report()), [])
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python3 -m unittest tests.test_findings.Reverts -v`
Expected: `AttributeError: module 'gitmole.findings' has no attribute 'reverts'`.

- [ ] **Step 3: Implement**

In `gitmole/findings.py`, after `bug_magnets`:

```python
def _times(n: int) -> str:
    return {1: "once", 2: "twice"}.get(n, f"{n} times")


def reverts(report: dict, min_share: float = 0.05, min_count: int = 5, warn_share: float = 0.10) -> list:
    """Commits backed out with git revert. The file most often reverted is where a check before merge pays."""
    act = report.get("activity") or {}
    n = act.get("revert_commits") or 0
    total = report["meta"].get("commits") or 0
    if not n or (n < min_count and (not total or n / total < min_share)):
        return []
    sev = "warning" if total and n / total >= warn_share else "info"
    reverted = act.get("reverted") or {}
    listed = ", ".join(f"{p} was reverted {_times(c)}" for p, c in list(reverted.items())[:3])
    statement = f"{n} of {total} commits are reverts" + (f"; {listed}." if listed else ".")
    source = [p for p in reverted if not filetypes.is_test_path(p)]
    if source:
        advice = f"Add a check before merge for {source[0]}; it is the file most often backed out."
    else:
        advice = "Look at why they were backed out; only test files were touched."
    return [_f(sev, "Reverts", statement, advice)]
```

Add `reverts` to `RULES` right after `bug_magnets`.

- [ ] **Step 4: Run the tests**

Run: `python3 -m unittest tests.test_findings -v`
Expected: all pass, including `Advice` (the new rule does not fire on its fixture: no `activity`).

- [ ] **Step 5: Commit**

```bash
git add gitmole/findings.py tests/test_findings.py
git commit -m "Reverts finding: share of commits backed out, most reverted file"
```

### Task 1.3: Pulse phrase and README

**Files:**
- Modify: `gitmole/render.py` (`pulse()`)
- Modify: `README.md` (findings list in "The terminal report", item 2)
- Test: `tests/test_render.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_render.py` inside class `Report` (after `test_header_singular_identity`):

```python
    def test_header_mentions_reverts_only_when_there_are_any(self):
        r = sample_report()
        r["activity"]["revert_commits"] = 7
        self.assertIn("3% of commits are reverts", rendered(r, []))     # 7 of 233 commits in by_weekday
        self.assertNotIn("reverts", rendered(sample_report(), []))
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python3 -m unittest tests.test_render.Report.test_header_mentions_reverts_only_when_there_are_any -v`
Expected: FAIL, `'3% of commits are reverts' not found`.

- [ ] **Step 3: Implement**

In `render.pulse()`, after the fix-commits phrase:

```python
    if act.get("revert_commits") and total:
        out.append(f"{_pct(act['revert_commits'], total)} of commits are reverts")
```

In `README.md`, in the findings list of "The terminal report" item 2, after "bug magnets (...; a warning at five)," add: `reverts (5% of commits or five of them; a warning at 10%; names the file most often backed out),`.

- [ ] **Step 4: Run the whole suite**

Run: `python3 -m unittest discover -s tests -t .`
Expected: `OK`. The golden report has no reverts, so it is unchanged.

- [ ] **Step 5: Manual check and commit**

Run gitmole on mealie and confirm the pulse line shows a reverts percentage, and the finding, if it fires, names a real file.

```bash
git add gitmole/render.py README.md tests/test_render.py
git commit -m "Reverts in the header pulse; README"
```

Open the PR: title `Reverts: pulse phrase and finding`.

---

# Part 2: Knowledge loss (PR 2)

## File structure

- Create `gitmole/loss.py`: who is gone, and what they own. Pure functions over the report.
- Modify `gitmole/maat.py`: `months_before(date, months)` helper (shared by cli and loss).
- Modify `gitmole/cli.py`: `--gone MONTHS`, `meta["gone_months"]`.
- Modify `gitmole/findings.py`: `knowledge_loss` rule.
- Modify `gitmole/render.py`: `(gone)` marker, `lost` column under `--full`, caption.
- Modify `README.md`.
- Tests: `tests/test_loss.py` (new), `tests/test_maat.py`, `tests/test_cli.py`, `tests/test_findings.py`, `tests/test_render.py`.

### Task 2.1: `months_before` helper

**Files:**
- Modify: `gitmole/maat.py` (next to `_months_between`)
- Test: `tests/test_maat.py`

**Interfaces:**
- Produces: `maat.months_before(date: str, months: int) -> str` (ISO dates; day clamped to the month's length).

- [ ] **Step 1: Write the failing test**

Append to `tests/test_maat.py`:

```python
class MonthsBefore(unittest.TestCase):
    def test_subtracts_whole_months_and_clamps_the_day(self):
        self.assertEqual(maat.months_before("2025-11-09", 12), "2024-11-09")
        self.assertEqual(maat.months_before("2026-03-31", 1), "2026-02-28")
        self.assertEqual(maat.months_before("2026-01-15", 6), "2025-07-15")
        self.assertEqual(maat.months_before("2026-01-15", 0), "2026-01-15")
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python3 -m unittest tests.test_maat.MonthsBefore -v`
Expected: `AttributeError`.

- [ ] **Step 3: Implement**

In `gitmole/maat.py`, after `_months_between`:

```python
def months_before(date: str, months: int) -> str:
    """The ISO date `months` whole months before `date`, day clamped to the month's length."""
    import calendar
    d = dt.date.fromisoformat(date)
    y, m = d.year, d.month - months
    while m <= 0:
        y, m = y - 1, m + 12
    return dt.date(y, m, min(d.day, calendar.monthrange(y, m)[1])).isoformat()
```

- [ ] **Step 4: Run the tests**

Run: `python3 -m unittest tests.test_maat -v` → all pass.

- [ ] **Step 5: Commit**

```bash
git add gitmole/maat.py tests/test_maat.py
git commit -m "maat.months_before helper"
```

### Task 2.2: The loss module

**Files:**
- Create: `gitmole/loss.py`
- Test: `tests/test_loss.py`

**Interfaces:**
- Produces:
  - `loss.cutoff(report, months) -> str | None`: `months_before(meta["last_date"], months)`, None when there is no last date.
  - `loss.gone(report, months=12) -> list[dict]`: `[{"name", "last"}]`, people (not bots) whose `activity.authors[name].last < cutoff`, sorted by name.
  - `loss.surviving(report, gone_names) -> tuple[int, int]`: (lines by gone people, total surviving lines).
  - `loss.areas(rows, gone_names) -> list[dict]`: `knowledge.areas` over the given ownership rows (the caller picks source-only or all), each row with `"lost": int` (lines by gone people) and `"lost_share": float`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_loss.py`:

```python
import unittest

from gitmole import loss


def report(**overrides):
    base = {
        "meta": {"name": "r", "last_date": "2025-11-09", "bots": [{"name": "renovate[bot]", "commits": 9}]},
        "activity": {"authors": {
            "Ann": {"commits": 50, "added": 0, "deleted": 0, "first": "2020-01-01", "last": "2025-11-01"},
            "Bob": {"commits": 20, "added": 0, "deleted": 0, "first": "2020-01-01", "last": "2024-11-08"},   # one day past the window
            "Cat": {"commits": 5, "added": 0, "deleted": 0, "first": "2021-01-01", "last": "2024-11-09"},   # on the cut-off: stays
            "renovate[bot]": {"commits": 9, "added": 0, "deleted": 0, "first": "2024-01-01", "last": "2024-01-01"},
            "dependabot[bot]": {"commits": 1, "added": 0, "deleted": 0, "first": "2023-01-01", "last": "2023-01-01"},
        }},
        "theseus_authors": {"Ann": 600, "Bob": 300, "Cat": 100},
        "ownership": [{"entity": "app/a.py", "author": "Ann", "added": 100, "deleted": 0},
                      {"entity": "app/b.py", "author": "Bob", "added": 900, "deleted": 0},
                      {"entity": "docs/x.md", "author": "Bob", "added": 50, "deleted": 0},
                      {"entity": "tests/t.py", "author": "Bob", "added": 500, "deleted": 0}],
    }
    base.update(overrides)
    return base


class Gone(unittest.TestCase):
    def test_no_commits_in_the_window_before_the_last_commit_not_before_today(self):
        self.assertEqual(loss.cutoff(report(), 12), "2024-11-09")
        self.assertEqual(loss.gone(report()), [{"name": "Bob", "last": "2024-11-08"}])

    def test_bots_are_never_people(self):
        names = [g["name"] for g in loss.gone(report(), months=1)]
        self.assertEqual(names, ["Bob", "Cat"])

    def test_window_is_configurable(self):
        self.assertEqual([g["name"] for g in loss.gone(report(), months=1)], ["Bob", "Cat"])
        self.assertEqual(loss.gone(report(), months=24), [])

    def test_nothing_without_activity_or_last_date(self):
        self.assertEqual(loss.gone(report(activity={})), [])
        r = report()
        r["meta"]["last_date"] = ""
        self.assertEqual(loss.gone(r), [])


class WhatWasLost(unittest.TestCase):
    def test_surviving_lines_by_gone_people(self):
        self.assertEqual(loss.surviving(report(), {"Bob"}), (300, 1000))
        self.assertEqual(loss.surviving(report(theseus_authors={}), {"Bob"}), (0, 0))

    def test_areas_carry_the_lost_share_over_the_rows_given(self):
        from gitmole import filetypes
        rows = [r for r in report()["ownership"] if not filetypes.is_test_path(r["entity"])]
        areas = {a["area"]: a for a in loss.areas(rows, {"Bob"})}
        self.assertEqual(set(areas), {"app/", "docs/"}, "the caller left tests/ out")
        self.assertEqual(areas["app/"]["lost"], 900)
        self.assertAlmostEqual(areas["app/"]["lost_share"], 0.9)
        self.assertAlmostEqual(areas["docs/"]["lost_share"], 1.0)
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python3 -m unittest tests.test_loss -v`
Expected: `ModuleNotFoundError: No module named 'gitmole.loss'`.

- [ ] **Step 3: Implement**

Create `gitmole/loss.py`:

```python
"""Knowledge loss: who has stopped committing, and how much of the code is theirs.

"Gone" is measured against the repository's last commit, not today's date, so a clone that was
last fetched a year ago does not mark everyone as gone."""
from __future__ import annotations

from . import identity, knowledge, maat

DEFAULT_MONTHS = 12


def cutoff(report: dict, months: int = DEFAULT_MONTHS):
    last = report["meta"].get("last_date") or ""
    return maat.months_before(last, months) if last else None


def gone(report: dict, months: int = DEFAULT_MONTHS) -> list:
    """People whose last commit is before the cut-off, by name. Bots are never people."""
    cut = cutoff(report, months)
    authors = (report.get("activity") or {}).get("authors") or {}
    if not cut or not authors:
        return []
    bots = {b["name"] for b in report["meta"].get("bots") or []}
    out = [{"name": name, "last": a.get("last", "")} for name, a in authors.items()
           if name not in bots and not identity.is_bot(name) and a.get("last", "") < cut]
    return sorted(out, key=lambda g: g["name"])


def surviving(report: dict, gone_names) -> tuple:
    """(surviving lines written by gone people, all surviving lines); (0, 0) without a blame pass."""
    shares = report.get("theseus_authors") or {}
    return sum(n for name, n in shares.items() if name in gone_names), sum(shares.values())


def areas(rows: list, gone_names) -> list:
    """knowledge.areas over the given ownership rows, each row with `lost` lines and `lost_share`."""
    out = []
    for a in knowledge.areas(rows):
        lost = sum(n for name, n in a["owners"] if name in gone_names)
        out.append({**a, "lost": lost, "lost_share": lost / a["lines"] if a["lines"] else 0.0})
    return out
```

- [ ] **Step 4: Run the tests**

Run: `python3 -m unittest tests.test_loss -v` → all pass.

- [ ] **Step 5: Commit**

```bash
git add gitmole/loss.py tests/test_loss.py
git commit -m "loss module: who is gone and what they own"
```

### Task 2.3: `--gone` flag recorded in meta

**Files:**
- Modify: `gitmole/cli.py` (`parse_args`, `_analyse`)
- Test: `tests/test_cli.py`

**Interfaces:**
- Produces: `meta["gone_months"]` (int), read by findings and render via `report["meta"].get("gone_months", loss.DEFAULT_MONTHS)`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_cli.py` inside class `FileTypes` after `test_meta_records_the_file_types...` (it reuses `meta_for`'s shape; copy the helper):

```python
class GoneWindow(unittest.TestCase):
    def _meta(self, *extra):
        with tempfile.TemporaryDirectory() as d:
            _tiny_repo(d)
            out = os.path.join(d, "out")
            planner = lambda repo, o, branch="HEAD", **kw: [{"name": "q", "argv": ["true"], "stdout": None, "deps": []}]
            cli.main([d, "--out", out, *extra], console=console(), tool_check=lambda **kw: [], planner=planner,
                     estimator=lambda repo, interval, **kw: {"files": 1, "samples": 1, "blames": 1, "seconds": 0.0})
            with open(os.path.join(out, "meta.json")) as fh:
                return json.load(fh)

    def test_default_twelve_months_recorded_and_flag_changes_it(self):
        self.assertEqual(self._meta()["gone_months"], 12)
        self.assertEqual(self._meta("--gone", "6")["gone_months"], 6)
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python3 -m unittest tests.test_cli.GoneWindow -v` → `KeyError: 'gone_months'`.

- [ ] **Step 3: Implement**

In `cli.parse_args`, after `--since`:

```python
    p.add_argument("--gone", type=int, default=12, metavar="MONTHS", help="a person with no commits this many months before the last commit counts as gone (default 12)")
```

In `cli._analyse`, right after `meta["file_types"] = types_spec`:

```python
    meta["gone_months"] = args.gone
```

- [ ] **Step 4: Run the tests**

Run: `python3 -m unittest tests.test_cli -v` → all pass.

- [ ] **Step 5: Commit**

```bash
git add gitmole/cli.py tests/test_cli.py
git commit -m "--gone MONTHS, recorded in meta.json"
```

### Task 2.4: The Knowledge loss finding

**Files:**
- Modify: `gitmole/findings.py` (new rule after `knowledge_islands`, add to `RULES` after `knowledge_islands`)
- Test: `tests/test_findings.py`

**Interfaces:**
- Consumes: `loss.gone`, `loss.surviving`, `loss.areas`.
- Produces: `findings.knowledge_loss(report, min_share=0.10, warn_share=0.30) -> list`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_findings.py` before `class Advice`:

```python
class KnowledgeLoss(unittest.TestCase):
    def _report(self, **over):
        r = report(**over)
        r["meta"].update({"last_date": "2025-11-09", "bots": []})
        r["activity"] = {"authors": {
            "Ann": {"commits": 60, "added": 0, "deleted": 0, "first": "2020-01-01", "last": "2025-10-01"},
            "Bob": {"commits": 40, "added": 0, "deleted": 0, "first": "2020-01-01", "last": "2024-06-01"}}}
        return r

    def test_warning_names_the_largest_area_nobody_around_wrote(self):
        r = self._report(theseus_authors={"Ann": 60, "Bob": 40},
                         ownership=[{"entity": "old/a.py", "author": "Bob", "added": 800, "deleted": 0},
                                    {"entity": "docs/x.md", "author": "Bob", "added": 300, "deleted": 0},
                                    {"entity": "app/b.py", "author": "Ann", "added": 900, "deleted": 0}])
        f = findings.knowledge_loss(r)
        self.assertEqual(f[0]["severity"], "warning")
        self.assertEqual(f[0]["title"], "Knowledge loss")
        self.assertIn("1 person with no commits since 2024-11-09 wrote 40% of the code that survives today: Bob (40%)", f[0]["detail"])
        self.assertIn("Areas mostly theirs: old/ (100%), docs/ (100%)", f[0]["detail"])
        self.assertEqual(f[0]["advice"], "Pair someone on old/ first; nobody who wrote it is around to ask.")

    def test_info_between_ten_and_thirty_percent(self):
        f = findings.knowledge_loss(self._report(theseus_authors={"Ann": 85, "Bob": 15}))
        self.assertEqual(f[0]["severity"], "info")
        self.assertEqual(f[0]["advice"], "Pair someone with the people who worked with Bob before the rest of that knowledge goes.")

    def test_nothing_below_ten_percent_or_when_nobody_is_gone(self):
        self.assertEqual(findings.knowledge_loss(self._report(theseus_authors={"Ann": 95, "Bob": 5})), [])
        r = self._report()
        r["activity"]["authors"]["Bob"]["last"] = "2025-11-01"
        self.assertEqual(findings.knowledge_loss(r), [])

    def test_without_a_blame_pass_uses_lines_added_and_says_so(self):
        r = self._report(theseus_authors={},
                         ownership=[{"entity": "old/a.py", "author": "Bob", "added": 400, "deleted": 0},
                                    {"entity": "app/b.py", "author": "Ann", "added": 600, "deleted": 0}])
        f = findings.knowledge_loss(r)
        self.assertEqual(f[0]["severity"], "warning")
        self.assertIn("wrote 40% of all lines added (from lines added, not a blame)", f[0]["detail"])

    def test_window_from_meta(self):
        r = self._report(theseus_authors={"Ann": 60, "Bob": 40})
        r["meta"]["gone_months"] = 24
        self.assertEqual(findings.knowledge_loss(r), [], "Bob committed 17 months before the last commit")
```

- [ ] **Step 2: Run them to verify they fail**

Run: `python3 -m unittest tests.test_findings.KnowledgeLoss -v` → `AttributeError`.

- [ ] **Step 3: Implement**

In `gitmole/findings.py`, import `loss` (`from . import filetypes, hotspots, knowledge, leaks, loss`) and add after `knowledge_islands`:

```python
def knowledge_loss(report: dict, min_share: float = 0.10, warn_share: float = 0.30) -> list:
    """Code written by people who have stopped committing. Share of surviving code from the blame
    pass; when that did not run, share of lines added, and the statement says so."""
    months = report["meta"].get("gone_months", loss.DEFAULT_MONTHS)
    gone = loss.gone(report, months)
    if not gone:
        return []
    names = {g["name"] for g in gone}
    lost, total = loss.surviving(report, names)
    by_person = {n: v for n, v in (report.get("theseus_authors") or {}).items() if n in names}
    basis = "of the code that survives today"
    source_rows = _source_ownership(report)
    if not total:
        areas_all = loss.areas(source_rows, names)
        total = sum(a["lines"] for a in areas_all)
        lost = sum(a["lost"] for a in areas_all)
        by_person = {}
        for r in (r for r in source_rows if r["author"] in names):
            by_person[r["author"]] = by_person.get(r["author"], 0) + r["added"]
        basis = "of all lines added (from lines added, not a blame)"
    if not total or lost / total < min_share:
        return []
    sev = "warning" if lost / total >= warn_share else "info"
    people = sorted(by_person.items(), key=lambda kv: (-kv[1], kv[0]))
    listed = ", ".join(f"{n} ({_pct(v, total)})" for n, v in people[:3]) + (f" and {len(people) - 3} more" if len(people) > 3 else "")
    theirs = [a for a in loss.areas(source_rows, names) if a["lines"] >= 200 and a["lost_share"] >= 0.8]
    theirs.sort(key=lambda a: (-a["lines"], a["area"]))
    statement = (f"{len(gone)} {'person' if len(gone) == 1 else 'people'} with no commits since {loss.cutoff(report, months)} "
                 f"wrote {_pct(lost, total)} {basis}: {listed}.")
    if theirs:
        statement += " Areas mostly theirs: " + ", ".join(f"{a['area']} ({round(100 * a['lost_share'])}%)" for a in theirs[:3]) + "."
        advice = f"Pair someone on {theirs[0]['area']} first; nobody who wrote it is around to ask."
    else:
        advice = f"Pair someone with the people who worked with {people[0][0]} before the rest of that knowledge goes."
    return [_f(sev, "Knowledge loss", statement, advice)]
```

Add `knowledge_loss` to `RULES` after `knowledge_islands`.

- [ ] **Step 4: Run the tests**

Run: `python3 -m unittest tests.test_findings -v` → all pass. If `Advice` fails because the new rule fired on its fixture, it has no `activity`, so it must not fire; fix the rule, not the test.

- [ ] **Step 5: Commit**

```bash
git add gitmole/findings.py tests/test_findings.py
git commit -m "Knowledge loss finding"
```

### Task 2.5: Knowledge map marks and README

**Files:**
- Modify: `gitmole/render.py` (`knowledge_section`)
- Modify: `README.md` (options paragraph; "Tables" item 4; output section)
- Test: `tests/test_render.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_render.py` inside class `Report`:

```python
    def test_knowledge_map_marks_gone_owners_and_full_has_a_lost_column(self):
        r = sample_report()
        r["meta"]["last_date"] = "2026-09-10"
        r["meta"]["bots"] = []
        r["activity"]["authors"] = {"Ann": {"commits": 1, "added": 0, "deleted": 0, "first": "2025-01-01", "last": "2026-09-01"},
                                    "Bob": {"commits": 1, "added": 0, "deleted": 0, "first": "2025-01-01", "last": "2025-01-01"}}
        text = rendered(r, [])
        self.assertIn("Bob (gone)", text)
        self.assertIn("gone = no commits in the 12 months before 2026-09-10", text)
        self.assertNotIn("lost", text.split("⌂ Knowledge map")[1].split("\n")[1], "the lost column is --full only")
        full = rendered(r, [], full=True)
        self.assertRegex(full, r"area\s+lines added\s+authors\s+lost\s+main owner")
        self.assertRegex(full, r"static/\s+1,000\s+2\s+10%")
        self.assertNotIn("gone", rendered(sample_report(), []))
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python3 -m unittest tests.test_render.Report.test_knowledge_map_marks_gone_owners_and_full_has_a_lost_column -v` → FAIL.

- [ ] **Step 3: Implement**

Replace `knowledge_section` in `gitmole/render.py`:

```python
def knowledge_section(report: dict, full: bool = True, width=None) -> dict:
    """Ownership by area of the tree: who wrote most of each directory, gone owners marked."""
    months = report["meta"].get("gone_months", loss.DEFAULT_MONTHS)
    gone = {g["name"] for g in loss.gone(report, months)}
    areas = loss.areas(report.get("ownership") or [], gone)   # every area the map showed before, tests included
    limit = _limit("Knowledge map", full)
    rows = []
    for a in areas[:limit]:
        owners = [f"{name}{' (gone)' if name in gone else ''} ({_pct(n, a['lines'])})" for name, n in a["owners"][:2]] + ["-"]
        rows.append((a["area"], f"{a['lines']:,}", a["authors"], _pct(a["lost"], a["lines"]) if gone else "-", owners[0], owners[1]))
    columns = [("area", PATH), ("lines added", RIGHT), ("authors", RIGHT), ("lost", RIGHT), ("main owner", {}), ("second", {})]
    if full is not True:
        columns, rows = _keep(columns, rows, ["area", "lines added", "main owner", "second"])
    notes = [c for c in (_more(len(areas), limit),) if c]
    if gone:
        notes.append(f"gone = no commits in the {months} months before {report['meta'].get('last_date')}")
    return _section("Knowledge map", columns, rows, note=None if rows else "no ownership data", caption="\n".join(notes) or None)
```

Add `loss` to the render import line: `from . import hotspots, identity, knowledge, leaks, loss, textfmt, watch`.

README: in the Options paragraph add `` `--gone MONTHS` to change how long without a commit counts as gone (default 12, measured before the last commit) ``. In "Tables" item 4 add: "the knowledge map marks owners who have stopped committing with `(gone)`, and under `--full` shows the share of each area's lines that they wrote". In the findings list add "knowledge loss (people with no commits in the last twelve months who wrote 10% or more of the surviving code; a warning at 30%)".

- [ ] **Step 4: Run the whole suite**

Run: `python3 -m unittest discover -s tests -t .` → `OK`. The golden repository's two authors both committed within its last year, so the golden file is unchanged.

- [ ] **Step 5: Manual check and commit**

On mealie, confirm the finding lists real people and the map marks them. Commit and open the PR `Knowledge loss: gone people and what they own`.

```bash
git add gitmole/render.py README.md tests/test_render.py
git commit -m "Knowledge map: gone owners marked, lost column under --full; README"
```

---

# Part 3: Change risk (PR 3)

## File structure

- Modify `gitmole/run.py`: `changed_files(repo, base)`.
- Modify `gitmole/watch.py`: `change_risk(report, files)`.
- Modify `gitmole/render.py`: `risk_section`, JSON export.
- Modify `gitmole/cli.py`: `--risk BASE`.
- Modify `README.md`.
- Tests: `tests/test_run.py`, `tests/test_watch.py`, `tests/test_render.py`, `tests/test_cli.py`.

### Task 3.1: Files changed since a base ref

**Files:**
- Modify: `gitmole/run.py` (after `collect_meta`)
- Test: `tests/test_run.py`

**Interfaces:**
- Produces: `run.changed_files(repo_dir, base) -> list[str]`, sorted; raises `ValueError` with git's message when the base is unknown.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_run.py` before `class ClearOutputs`:

```python
class ChangedFiles(unittest.TestCase):
    def test_lists_paths_changed_since_the_merge_base(self):
        with tempfile.TemporaryDirectory() as d:
            def git(*args):
                e = dict(os.environ, GIT_CONFIG_GLOBAL="/dev/null", GIT_CONFIG_SYSTEM="/dev/null",
                         GIT_AUTHOR_NAME="A", GIT_AUTHOR_EMAIL="a@x", GIT_COMMITTER_NAME="A", GIT_COMMITTER_EMAIL="a@x")
                subprocess.run(["git", *args], cwd=d, check=True, capture_output=True, env=e)
            git("init", "-q", "-b", "main")
            for name in ("a.py", "b.py"):
                open(os.path.join(d, name), "w").write("x\n")
            git("add", "-A"); git("commit", "-q", "-m", "base")
            git("switch", "-q", "-c", "feature")
            open(os.path.join(d, "b.py"), "a").write("y\n")
            os.makedirs(os.path.join(d, "dir"))
            open(os.path.join(d, "dir", "c.py"), "w").write("z\n")
            git("add", "-A"); git("commit", "-q", "-m", "work")
            git("switch", "-q", "main")
            open(os.path.join(d, "a.py"), "a").write("main moved on\n")
            git("commit", "-q", "-am", "main")
            git("switch", "-q", "feature")
            self.assertEqual(run.changed_files(d, "main"), ["b.py", "dir/c.py"], "three-dot diff: main's own change to a.py is not ours")
            with self.assertRaises(ValueError) as ctx:
                run.changed_files(d, "nope")
            self.assertIn("nope", str(ctx.exception))
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python3 -m unittest tests.test_run.ChangedFiles -v` → `AttributeError`.

- [ ] **Step 3: Implement**

In `gitmole/run.py` after `collect_meta`:

```python
def changed_files(repo_dir: str, base: str) -> list:
    """Paths that differ between the merge base with `base` and HEAD, sorted. ValueError when git refuses."""
    proc = subprocess.run([*filetypes.GIT, "diff", "-z", "--name-only", f"{base}...HEAD"], cwd=repo_dir, capture_output=True)
    if proc.returncode != 0:
        raise ValueError((proc.stderr.decode("utf-8", "replace").strip() or f"git diff {base}...HEAD failed"))
    return sorted(p.decode("utf-8", "surrogateescape") for p in proc.stdout.split(b"\0") if p)
```

- [ ] **Step 4: Run the tests** → `python3 -m unittest tests.test_run -v` all pass.

- [ ] **Step 5: Commit**

```bash
git add gitmole/run.py tests/test_run.py
git commit -m "run.changed_files: paths changed since a base ref"
```

### Task 3.2: Scoring touched files

**Files:**
- Modify: `gitmole/watch.py`
- Test: `tests/test_watch.py`

**Interfaces:**
- Consumes: `watch.risks(report)` rows (`file`, `score`, `reasons`).
- Produces: `watch.change_risk(report, files) -> dict`: `{"files": [{"file", "score", "reasons", "watched": bool}], "total": float, "watched": int, "max_score": float}`; rows sorted by score desc then file. A file without a watch row gets score 0 and one reason: `"test file"`, `"new file"` (not in `size.files`), or `"changed once"`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_watch.py`:

```python
class ChangeRisk(unittest.TestCase):
    def test_scores_touched_files_with_the_watch_score_and_reasons(self):
        r = report()
        out = watch.change_risk(r, ["core/util.py", "core/parser.py", "core/new.py", "core/once.py", "tests/test_parser.py"])
        files = [f["file"] for f in out["files"]]
        self.assertEqual(files[:2], ["core/parser.py", "core/util.py"], "highest score first")
        by = {f["file"]: f for f in out["files"]}
        self.assertGreater(by["core/parser.py"]["score"], by["core/util.py"]["score"])
        self.assertIn("changed 40 times", by["core/parser.py"]["reasons"][0])
        self.assertEqual((by["core/new.py"]["score"], by["core/new.py"]["reasons"]), (0, ["new file"]))
        self.assertEqual((by["core/once.py"]["score"], by["core/once.py"]["reasons"]), (0, ["changed once"]))
        self.assertEqual((by["tests/test_parser.py"]["score"], by["tests/test_parser.py"]["reasons"]), (0, ["test file"]))
        self.assertAlmostEqual(out["total"], by["core/parser.py"]["score"] + by["core/util.py"]["score"])
        self.assertEqual(out["watched"], 2, "both are in the top 15 of the watch list")
        self.assertEqual(out["max_score"], watch.risks(r)[0]["score"])

    def test_empty(self):
        self.assertEqual(watch.change_risk(report(), []), {"files": [], "total": 0.0, "watched": 0, "max_score": 0.0})
```

- [ ] **Step 2: Run it to verify it fails** → `AttributeError`.

- [ ] **Step 3: Implement**

Append to `gitmole/watch.py`:

```python
WATCH_TOP = 15   # the same cap the report's --full watch list uses


def change_risk(report: dict, files: list) -> dict:
    """The watch score of each touched file, and their sum. Files the watch list never scored get 0
    and one reason saying why."""
    ranked = risks(report)
    by_file = {r["file"]: r for r in ranked}
    watched = {r["file"] for r in ranked[:WATCH_TOP]}
    in_tree = (report.get("size") or {}).get("files") or {}
    rows = []
    for f in files:
        r = by_file.get(f)
        if r:
            rows.append({"file": f, "score": r["score"], "reasons": r["reasons"], "watched": f in watched})
        elif filetypes.is_test_path(f):
            rows.append({"file": f, "score": 0, "reasons": ["test file"], "watched": False})
        elif f not in in_tree:
            rows.append({"file": f, "score": 0, "reasons": ["new file"], "watched": False})
        else:
            rows.append({"file": f, "score": 0, "reasons": ["changed once"], "watched": False})
    rows.sort(key=lambda r: (-r["score"], r["file"]))
    return {"files": rows, "total": float(sum(r["score"] for r in rows)), "watched": sum(r["watched"] for r in rows),
            "max_score": float(ranked[0]["score"]) if ranked else 0.0}
```

- [ ] **Step 4: Run the tests** → `python3 -m unittest tests.test_watch -v` all pass.

- [ ] **Step 5: Commit**

```bash
git add gitmole/watch.py tests/test_watch.py
git commit -m "watch.change_risk: score the files a change touches"
```

### Task 3.3: The section, the flag, JSON, README

**Files:**
- Modify: `gitmole/render.py` (`risk_section`, `print_risk`, `to_json`)
- Modify: `gitmole/cli.py` (`--risk`, `_render`)
- Modify: `README.md`
- Test: `tests/test_render.py`, `tests/test_cli.py`

**Interfaces:**
- Produces: `render.risk_section(risk: dict, base: str, full) -> dict` (a section like the others); `cli` passes `args.risk`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_render.py` (new class):

```python
class ChangeRisk(unittest.TestCase):
    RISK = {"files": [{"file": "core/parser.py", "score": 3.0, "reasons": ["changed 40 times", "fixed 5 times in six months"], "watched": True},
                      {"file": "core/util.py", "score": 0.6, "reasons": ["changed 30 times"], "watched": True},
                      {"file": "core/new.py", "score": 0, "reasons": ["new file"], "watched": False}],
            "total": 3.6, "watched": 2, "max_score": 3.0}

    def test_section_has_a_bar_scaled_to_the_worst_file_in_the_repo(self):
        sec = render.risk_section(self.RISK, "main", full=False)
        self.assertEqual(sec["title"], "Change risk (3 files since main)")
        self.assertEqual(sec["columns"], ["file", "risk", "why"])
        self.assertEqual(sec["rows"][0], ["core/parser.py", "▰▰▰▰▰▰▰▰▰▰", "changed 40 times · fixed 5 times in six months"])
        self.assertEqual(sec["rows"][1][1], "▰▰")
        self.assertEqual(sec["rows"][2][1], "")
        self.assertEqual(sec["caption"], "total 3.6; 2 of these files are on the watch list")

    def test_empty_change(self):
        sec = render.risk_section({"files": [], "total": 0.0, "watched": 0, "max_score": 0.0}, "main", full=False)
        self.assertEqual(sec["note"], "no files changed since main")

    def test_json_carries_the_risk_when_given(self):
        j = render.to_json(sample_report(), [], risk={"base": "main", **self.RISK})
        self.assertEqual(j["change_risk"]["base"], "main")
        self.assertEqual(j["change_risk"]["total"], 3.6)
        self.assertNotIn("change_risk", render.to_json(sample_report(), []))
```

Append to `tests/test_cli.py`:

```python
class Risk(unittest.TestCase):
    def _repo(self, d):
        import subprocess
        def git(*args):
            e = dict(os.environ, GIT_CONFIG_GLOBAL="/dev/null", GIT_CONFIG_SYSTEM="/dev/null",
                     GIT_AUTHOR_NAME="A", GIT_AUTHOR_EMAIL="a@x", GIT_COMMITTER_NAME="A", GIT_COMMITTER_EMAIL="a@x")
            subprocess.run(["git", *args], cwd=d, check=True, capture_output=True, env=e)
        git("init", "-q", "-b", "main")
        open(os.path.join(d, "a.py"), "w").write("x\n")
        git("add", "-A"); git("commit", "-q", "-m", "base")
        git("switch", "-q", "-c", "feature")
        open(os.path.join(d, "a.py"), "a").write("y\n")
        git("commit", "-q", "-am", "work")

    def test_risk_section_after_a_run_and_on_a_re_render(self):
        with tempfile.TemporaryDirectory() as d:
            self._repo(d)
            out = os.path.join(d, "out")
            planner = lambda repo, o, branch="HEAD", **kw: [{"name": "q", "argv": ["true"], "stdout": None, "deps": []}]
            c = console()
            rc = cli.main([d, "--out", out, "--risk", "main"], console=c, tool_check=lambda **kw: [], planner=planner,
                          estimator=lambda repo, interval, **kw: {"files": 1, "samples": 1, "blames": 1, "seconds": 0.0})
            self.assertEqual(rc, 0)
            self.assertIn("Change risk (1 files since main)", c.export_text())
            self.assertRegex(c.export_text(), r"a\.py\s+new file", "the stub planner writes no size.json, so a.py is not in the tree data")
            c = console()
            rc = cli.main([out, "--no-run", "--risk", "main"], console=c)
            self.assertEqual(rc, 0)
            self.assertIn("Change risk (1 files since main)", c.export_text())

    def test_unknown_base_is_an_error(self):
        with tempfile.TemporaryDirectory() as d:
            self._repo(d)
            out = os.path.join(d, "out")
            planner = lambda repo, o, branch="HEAD", **kw: [{"name": "q", "argv": ["true"], "stdout": None, "deps": []}]
            c = console()
            rc = cli.main([d, "--out", out, "--risk", "nope"], console=c, tool_check=lambda **kw: [], planner=planner,
                          estimator=lambda repo, interval, **kw: {"files": 1, "samples": 1, "blames": 1, "seconds": 0.0})
            self.assertEqual(rc, 2)
            self.assertIn("nope", c.export_text())

    def test_remote_targets_refuse_risk(self):
        c = console()
        rc = cli.main(["owner/repo", "--risk", "main"], console=c, tool_check=lambda **kw: [])
        self.assertEqual(rc, 2)
        self.assertIn("--risk needs a local path", c.export_text())
```

- [ ] **Step 2: Run them to verify they fail** → `AttributeError: risk_section`, argparse error for `--risk`.

- [ ] **Step 3: Implement**

In `gitmole/render.py`, after `watch_section`:

```python
RISK_CAP = 15


def risk_section(risk: dict, base: str, full=True) -> dict:
    """The files a change touches, each with its watch score as a bar scaled to the repo's worst file."""
    rows_all = risk["files"]
    limit = None if full is True else RISK_CAP
    top = risk["max_score"] or 1.0
    rows = [(r["file"], "▰" * round(10 * r["score"] / top) if r["score"] else "", " · ".join(r["reasons"])) for r in rows_all[:limit]]
    columns = [("file", PATH), ("risk", {}), ("why", {"overflow": "fold", "ratio": 3})]
    notes = [f"total {risk['total']:.1f}; {risk['watched']} of these files are on the watch list"] if rows else []
    more = _more(len(rows_all), limit)
    if more:
        notes.append(more)
    return _section(f"Change risk ({len(rows_all)} files since {base})", columns, rows,
                    note=None if rows else f"no files changed since {base}", caption="\n".join(notes) or None)
```

Add `"Change risk": "◈"` to `SYMBOLS` and `"Change risk": "risk"` to `KEY_METRIC` (both keyed on `_base_title`, which cuts at ` (`).

Change `to_json`:

```python
def to_json(report: dict, findings: list, risk: dict = None) -> dict:
    out = {**{k: v for k, v in report.items()}, "findings": findings,
           "watch": [{k: v for k, v in r.items() if k != "function"} | {"function": r["function"]["function"] if r["function"] else None}
                     for r in watch.risks(report)[:WATCH_FULL]]}
    if risk is not None:
        out["change_risk"] = risk
    return out
```

Change `report()` to accept `risk=None, base=None` and, after the last section loop and before the secrets line, `if risk is not None: print_section(console, risk_section(risk, base, full))`. Change `markdown()` the same way: accept `risk=None, base=None` and append the section's table after the other sections when given (reuse the same table-writing lines, or refactor the loop to take a list of sections that includes it).

In `gitmole/cli.py`:
- `parse_args`: `p.add_argument("--risk", metavar="BASE", help="score the files changed since BASE (merge base with HEAD) with the watch list's score; needs a local path")`.
- In `main`, right after `kind, target = run.classify_target(...)`: `if args.risk and kind != "path": err.print("[red]--risk needs a local path[/red]"); return 2`.
- In `_render(out_dir, console, ui, args)`: after `found = findings.evaluate(report)`:

```python
    risk = None
    if args.risk:
        try:
            files = run.changed_files(report["meta"].get("path") or os.getcwd(), args.risk)
        except ValueError as e:
            (Console(stderr=True) if console.file is sys.stdout else console).print(f"[red]--risk {args.risk}:[/red] {e}", soft_wrap=True)
            return 2
        from . import watch
        risk = {"base": args.risk, **watch.change_risk(report, files)}
```

and pass `risk=risk, base=args.risk` into `render.to_json`, `render.markdown` and `render.report`. For `--no-run`, `report["meta"]["path"]` is the repository recorded at run time.

README: in the Options paragraph add `` `--risk BASE` to score the files changed since BASE (the merge base with HEAD) with the watch list's score, in one extra section with a total; it works with `--no-run` and the JSON carries the number for CI ``. In "The terminal report" add item 5a, or a sentence under the watch list item: "With `--risk BASE`, a Change risk section follows: every file changed since BASE with its watch score as a bar and the reasons, or why it has none (new file, changed once, test file)."

- [ ] **Step 4: Run the whole suite** → `OK`. Golden unchanged (no `--risk`).

- [ ] **Step 5: Manual check and commit**

On a mealie feature branch (or `--risk HEAD~20`), confirm the section lists files with bars and the total matches the JSON. Commit; open PR `Change risk: score the files a branch touches`.

```bash
git add gitmole/render.py gitmole/cli.py README.md tests/test_render.py tests/test_cli.py
git commit -m "--risk BASE: change risk section, JSON export"
```

---

# Part 4: Complexity trend (PR 4)

## File structure

- Create `gitmole/trend.py`: the step (sampling, measuring) plus the pure helpers the renderer and findings use.
- Modify `gitmole/run.py`: `TREND` step, `PYTHONPATH` in `execute`, `OUTPUTS`.
- Modify `gitmole/cli.py`: `meta["trend"]` status.
- Modify `gitmole/load.py`: read `trend.json`.
- Modify `gitmole/render.py`: `trend` column.
- Modify `gitmole/findings.py`: `complexity_growth`.
- Modify `README.md`; regenerate `tests/golden/report.txt`.
- Tests: `tests/test_trend.py` (new), `tests/test_run.py`, `tests/test_cli.py`, `tests/test_load.py`, `tests/test_render.py`, `tests/test_findings.py`.

### Task 4.1: Pure helpers: sample dates, yearly change, sparkline

**Files:**
- Create: `gitmole/trend.py`
- Test: `tests/test_trend.py`

**Interfaces:**
- Produces:
  - `trend.sample_dates(first: str, last: str, n: int) -> list[str]`: n ISO dates evenly spread from first to last inclusive; at most one per calendar month; at least the two ends when they differ; `[last]` when equal.
  - `trend.change_over_year(series: list, last_date: str) -> str`: series of `[date, complexity, code]`; compares the sample nearest to twelve months before `last_date` (at or before that date if any, else the earliest) with the last sample; returns `"+40%"`, `"-12%"`, `"="` (within 10%), or `"-"` (fewer than two samples, or the base complexity is 0).
  - `trend.sparkline(series: list) -> str`: complexity values mapped onto `▁▂▃▄▅▆▇█`, `""` for empty.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_trend.py`:

```python
import json
import os
import subprocess
import sys
import tempfile
import unittest

from gitmole import trend

SCRIPT_MODULE = "gitmole.trend"


class SampleDates(unittest.TestCase):
    def test_evenly_spread_and_at_most_one_per_month(self):
        dates = trend.sample_dates("2025-01-01", "2026-01-01", 12)
        self.assertEqual(dates[0], "2025-01-01")
        self.assertEqual(dates[-1], "2026-01-01")
        self.assertEqual(len(dates), 12)
        self.assertEqual(len({d[:7] for d in dates}), 12)

    def test_short_histories_give_fewer_points(self):
        self.assertEqual(trend.sample_dates("2026-03-01", "2026-03-20", 12), ["2026-03-01", "2026-03-20"])
        self.assertEqual(trend.sample_dates("2026-03-01", "2026-03-01", 12), ["2026-03-01"])


class ChangeOverYear(unittest.TestCase):
    S = [["2024-01-01", 10, 100], ["2024-11-01", 20, 100], ["2025-06-01", 25, 100], ["2025-11-01", 30, 100]]

    def test_compares_the_sample_nearest_a_year_back_with_the_latest(self):
        self.assertEqual(trend.change_over_year(self.S, "2025-11-09"), "+50%")       # 2024-11-01 (20) -> 30
        self.assertEqual(trend.change_over_year(self.S[1:], "2025-11-09"), "+50%")
        self.assertEqual(trend.change_over_year(self.S[2:], "2025-11-09"), "+20%", "no sample a year back: the earliest")

    def test_flat_within_ten_percent_and_unmeasurable(self):
        self.assertEqual(trend.change_over_year([["2024-11-01", 20, 1], ["2025-11-01", 21, 1]], "2025-11-09"), "=")
        self.assertEqual(trend.change_over_year([["2025-11-01", 21, 1]], "2025-11-09"), "-")
        self.assertEqual(trend.change_over_year([["2024-11-01", 0, 1], ["2025-11-01", 5, 1]], "2025-11-09"), "-")
        self.assertEqual(trend.change_over_year([["2024-11-01", 20, 1], ["2025-11-01", 14, 1]], "2025-11-09"), "-30%")


class Sparkline(unittest.TestCase):
    def test_maps_values_onto_eight_levels(self):
        self.assertEqual(trend.sparkline([["d", 0, 1], ["d", 5, 1], ["d", 10, 1]]), "▁▄█")
        self.assertEqual(trend.sparkline([["d", 7, 1], ["d", 7, 1]]), "▁▁")
        self.assertEqual(trend.sparkline([]), "")
```

- [ ] **Step 2: Run it to verify it fails** → `ModuleNotFoundError`.

- [ ] **Step 3: Implement**

Create `gitmole/trend.py`:

```python
#!/usr/bin/env python3
"""Complexity over time for the top hotspots: scc on each file's contents at sampled commits.

Runs as a pipeline step: `python -m gitmole.trend OUT_DIR [--repo DIR] [--samples N] [--top N]`,
from inside the repository (or with --repo). Reads size.json and maat-revisions.csv the earlier
steps wrote, picks the top hotspots still in the tree, and writes trend.json:
{"samples": [DATE, ...], "files": {PATH: [[DATE, complexity, code], ...]}}.

The pure helpers below are also what the renderer and the findings use."""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import subprocess
import sys
import tempfile

from . import hotspots, load, filetypes

BLOCKS = "▁▂▃▄▅▆▇█"


def sample_dates(first: str, last: str, n: int) -> list:
    a, b = dt.date.fromisoformat(first), dt.date.fromisoformat(last)
    if b <= a:
        return [last]
    span = (b - a).days
    n = max(2, min(n, span // 28 + 1))
    out, seen = [], set()
    for i in range(n):
        d = (a + dt.timedelta(days=round(span * i / (n - 1)))).isoformat()
        if i not in (0, n - 1) and d[:7] in seen:
            continue   # at most one interior sample per month; the two ends always stay
        seen.add(d[:7])
        out.append(d)
    out[-1] = last
    return out


def change_over_year(series: list, last_date: str) -> str:
    if len(series) < 2:
        return "-"
    from .maat import months_before
    year_ago = months_before(last_date, 12)
    before = [s for s in series if s[0] <= year_ago]
    base = before[-1] if before else series[0]
    then, now = base[1], series[-1][1]
    if not then:
        return "-"
    pct = round(100 * (now - then) / then)
    if abs(pct) < 10:
        return "="
    return f"{pct:+d}%"


def sparkline(series: list) -> str:
    values = [s[1] for s in series]
    if not values:
        return ""
    lo, hi = min(values), max(values)
    if hi == lo:
        return BLOCKS[0] * len(values)
    return "".join(BLOCKS[round((v - lo) / (hi - lo) * (len(BLOCKS) - 1))] for v in values)
```

(The step's `main`, `rev_before`, `measure` come in Task 4.2.)

- [ ] **Step 4: Run the tests** → `python3 -m unittest tests.test_trend -v` all pass.

- [ ] **Step 5: Commit**

```bash
git add gitmole/trend.py tests/test_trend.py
git commit -m "trend helpers: sample dates, yearly change, sparkline"
```

### Task 4.2: The trend step

**Files:**
- Modify: `gitmole/trend.py` (add `rev_before`, `measure`, `top_files`, `main`)
- Test: `tests/test_trend.py`

**Interfaces:**
- Produces:
  - `trend.rev_before(repo, date) -> str | None`: `git rev-list -1 --before=DATE HEAD`.
  - `trend.measure(repo, rev, files) -> dict[path, (complexity, code)]`: files missing at `rev` are absent from the result.
  - `trend.top_files(out_dir, n) -> list[str]`: top n in-tree hotspots from `size.json` + `maat-revisions.csv`, using `meta.json`'s `file_types`.
  - `trend.main(argv) -> int`: writes `OUT_DIR/trend.json` atomically; exit 0; exit 2 when the inputs are missing.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_trend.py`:

```python
def grow_repo(d):
    """One file whose complexity grows over four commits a month apart; a second file that appears late."""
    def git(*args, date):
        e = dict(os.environ, GIT_CONFIG_GLOBAL="/dev/null", GIT_CONFIG_SYSTEM="/dev/null",
                 GIT_AUTHOR_NAME="A", GIT_AUTHOR_EMAIL="a@x", GIT_COMMITTER_NAME="A", GIT_COMMITTER_EMAIL="a@x",
                 GIT_AUTHOR_DATE=date, GIT_COMMITTER_DATE=date)
        subprocess.run(["git", *args], cwd=d, check=True, capture_output=True, env=e)
    git("init", "-q", date="2025-01-01T10:00:00")
    os.makedirs(os.path.join(d, "app"))
    for i, date in enumerate(["2025-01-01", "2025-02-01", "2025-03-01", "2025-04-01"], start=1):
        body = "def f(x):\n" + "".join(f"    if x > {k}:\n        return {k}\n" for k in range(i * 3)) + "    return 0\n"
        open(os.path.join(d, "app", "a.py"), "w").write(body)
        if i == 4:
            open(os.path.join(d, "app", "late.py"), "w").write("def g():\n    return 1\n")
        git("add", "-A", date=f"{date}T10:00:00")
        git("commit", "-q", "-m", f"step {i}", date=f"{date}T10:00:00")


class Step(unittest.TestCase):
    def test_measures_the_top_hotspots_at_sampled_commits(self):
        with tempfile.TemporaryDirectory() as d:
            grow_repo(d)
            out = os.path.join(d, "out")
            os.makedirs(out)
            with open(os.path.join(out, "meta.json"), "w") as fh:
                json.dump({"name": "x", "first_date": "2025-01-01", "last_date": "2025-04-01", "file_types": None}, fh)
            with open(os.path.join(out, "size.json"), "w") as fh:
                fh.write(subprocess.run(["scc", "--by-file", "--format", "json"], cwd=d, capture_output=True, text=True, check=True).stdout)
            with open(os.path.join(out, "maat-revisions.csv"), "w") as fh:
                fh.write("entity,n-revs\napp/a.py,4\napp/late.py,1\n")
            rc = trend.main([out, "--repo", d, "--samples", "4"])
            with open(os.path.join(out, "trend.json")) as fh:
                data = json.load(fh)
        self.assertEqual(rc, 0)
        self.assertEqual(len(data["samples"]), 4)
        self.assertEqual((data["samples"][0], data["samples"][-1]), ("2025-01-01", "2025-04-01"))
        a = data["files"]["app/a.py"]
        self.assertEqual([s[0] for s in a], data["samples"])
        self.assertEqual([s[1] for s in a], sorted(s[1] for s in a), "complexity never drops: each sample sees the same or a later commit")
        self.assertLess(a[0][1], a[-1][1])
        self.assertEqual(len(data["files"]["app/late.py"]), 1, "absent at the first three samples")
        self.assertEqual(sorted(os.listdir(out)), ["maat-revisions.csv", "meta.json", "size.json", "trend.json"], "no temp files left")

    def test_missing_inputs_exit_2(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(trend.main([d, "--repo", d]), 2)

    def test_runs_as_a_module(self):
        p = subprocess.run([sys.executable, "-m", SCRIPT_MODULE, "--help"], capture_output=True, text=True,
                           env=dict(os.environ, PYTHONPATH=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
        self.assertEqual(p.returncode, 0, p.stderr)
```

- [ ] **Step 2: Run it to verify it fails** → `AttributeError: main`.

- [ ] **Step 3: Implement**

Append to `gitmole/trend.py`:

```python
def rev_before(repo: str, date: str):
    proc = subprocess.run(["git", "rev-list", "-1", f"--before={date}T23:59:59", "HEAD"], cwd=repo, capture_output=True, text=True)
    rev = proc.stdout.strip()
    return rev or None


def measure(repo: str, rev: str, files: list) -> dict:
    """{path: (complexity, code)} for the files that exist at rev, from one scc run over their contents."""
    out = {}
    with tempfile.TemporaryDirectory(prefix="gitmole-trend-") as tmp:
        present = []
        for path in files:
            proc = subprocess.run([*filetypes.GIT, "show", f"{rev}:{path}"], cwd=repo, capture_output=True)
            if proc.returncode != 0:
                continue
            target = os.path.join(tmp, path)
            os.makedirs(os.path.dirname(target), exist_ok=True)
            with open(target, "wb") as fh:
                fh.write(proc.stdout)
            present.append(path)
        if not present:
            return out
        scc = subprocess.run(["scc", "--by-file", "--format", "json"], cwd=tmp, capture_output=True, text=True)
        if scc.returncode != 0:
            return out
        for path, info in load.parse_scc(scc.stdout)["files"].items():
            out[path] = (info["complexity"], info["code"])
    return out


def top_files(out_dir: str, n: int) -> list:
    meta = json.loads(load._read(out_dir, "meta.json") or "{}")
    size = load.parse_scc(load._read(out_dir, "size.json"), filetypes.parse(meta["file_types"]) if "file_types" in meta else None)
    revisions = load.parse_maat_csv(load._read(out_dir, "maat-revisions.csv"))
    ranked = hotspots.ranked({"size": size, "revisions": revisions})
    return [h["entity"] for h in ranked if h["code"] is not None][:n]


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("out")
    p.add_argument("--repo", default=".")
    p.add_argument("--samples", type=int, default=12)
    p.add_argument("--top", type=int, default=10)
    args = p.parse_args(argv)
    meta = json.loads(load._read(args.out, "meta.json") or "{}")
    if not (meta.get("first_date") and meta.get("last_date") and os.path.exists(os.path.join(args.out, "size.json"))
            and os.path.exists(os.path.join(args.out, "maat-revisions.csv"))):
        print("trend: meta.json with dates, size.json and maat-revisions.csv are needed", file=sys.stderr)
        return 2
    files = top_files(args.out, args.top)
    dates = sample_dates(meta["first_date"], meta["last_date"], args.samples)
    series = {f: [] for f in files}
    for date in dates:
        rev = rev_before(args.repo, date)
        if not rev:
            continue
        for path, (cplx, code) in measure(args.repo, rev, files).items():
            series[path].append([date, cplx, code])
    data = {"samples": dates, "files": series}
    fd, tmp = tempfile.mkstemp(dir=args.out, prefix=".trend-", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh)
        os.replace(tmp, os.path.join(args.out, "trend.json"))
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run the tests** → `python3 -m unittest tests.test_trend -v` all pass (scc must be installed; it is a required tool).

- [ ] **Step 5: Commit**

```bash
git add gitmole/trend.py tests/test_trend.py
git commit -m "trend step: scc on the top hotspots at sampled commits"
```

### Task 4.3: Wire the step into the run, and load its output

**Files:**
- Modify: `gitmole/run.py` (`OUTPUTS`, `plan`, `execute` env)
- Modify: `gitmole/cli.py` (`meta["trend"]` status like `functions`)
- Modify: `gitmole/load.py` (`"trend"` key)
- Test: `tests/test_run.py`, `tests/test_cli.py`, `tests/test_load.py`

**Interfaces:**
- Produces: step `{"name": "trend", "argv": [sys.executable, "-m", "gitmole.trend", out_dir, "--samples", "12"], "stdout": None, "deps": ["scc", "change analysis"]}`; `run.execute` env has `PYTHONPATH` starting with the package's parent; `report["trend"]` = parsed `trend.json` or `{"samples": [], "files": {}}`; `meta["trend"]["status"]` in `planned/run/failed/timeout/skipped`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_run.py` in class `Plan`:

```python
    def test_trend_runs_as_a_module_after_scc_and_the_change_analysis(self):
        by = {s["name"]: s for s in run.plan("/r", "/o")}
        self.assertEqual(by["trend"]["argv"][:3], [sys.executable, "-m", "gitmole.trend"])
        self.assertEqual(by["trend"]["argv"][3], "/o")
        self.assertEqual(by["trend"]["deps"], ["scc", "change analysis"])
        self.assertNotIn("trend", [s["name"] for s in run.plan("/r", "/o", trend=False)])
        self.assertIn("trend.json", run.OUTPUTS)

    def test_execute_puts_the_package_on_pythonpath(self):
        with tempfile.TemporaryDirectory() as d:
            log = os.path.join(d, "run.log")
            steps = [{"name": "p", "argv": [sys.executable, "-c", "import os; print(os.environ['PYTHONPATH'])"], "stdout": os.path.join(d, "out.txt"), "deps": []}]
            run.execute(steps, log_path=log, cwd=d)
            with open(os.path.join(d, "out.txt")) as fh:
                first = fh.read().strip().split(os.pathsep)[0]
        self.assertEqual(os.path.realpath(first), os.path.realpath(os.path.dirname(os.path.dirname(run.__file__))))
```

Append to `tests/test_cli.py` in class `FunctionMetrics`:

```python
    def test_trend_status_is_recorded(self):
        _, meta, _ = self._main(True, [], name="trend")
        self.assertEqual(meta["trend"]["status"], "run")
        _, meta, _ = self._main(True, [], step=("sh", "-c", "exit 3"), name="trend")
        self.assertEqual(meta["trend"]["status"], "failed")
```

Append to `tests/test_load.py` in class `LoadReport`:

```python
    def test_trend_is_read_and_empty_when_missing(self):
        import os, tempfile
        with tempfile.TemporaryDirectory() as out:
            with open(os.path.join(out, "meta.json"), "w") as fh:
                json.dump({"name": "d", "commits": 1, "identities": []}, fh)
            self.assertEqual(load.load_report(out)["trend"], {"samples": [], "files": {}})
            with open(os.path.join(out, "trend.json"), "w") as fh:
                json.dump({"samples": ["2025-01-01"], "files": {"a.py": [["2025-01-01", 3, 10]]}}, fh)
            self.assertEqual(load.load_report(out)["trend"]["files"]["a.py"], [["2025-01-01", 3, 10]])
```

- [ ] **Step 2: Run them to verify they fail** → KeyError / AssertionError.

- [ ] **Step 3: Implement**

`gitmole/run.py`:
- Add `"trend.json"` to `OUTPUTS`.
- `plan(..., lizard=False, duplicates=False, trend=True, samples=12)`; after the lizard block:

```python
    if trend:
        steps.append({"name": "trend", "argv": [sys.executable, "-m", "gitmole.trend", out_dir, "--samples", str(samples)],
                      "stdout": None, "deps": ["scc", "change analysis"]})
```

- In `execute`, replace the env line:

```python
    package_parent = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
    env = dict(os.environ, PATH=env_path(),
               PYTHONPATH=os.pathsep.join([package_parent] + [p for p in [os.environ.get("PYTHONPATH", "")] if p]))
```

`gitmole/cli.py` `_analyse`: after `meta["functions"] = ...` add `meta["trend"] = {"status": "planned"}`; after the functions status update add `meta["trend"]["status"] = status("trend")`.

`gitmole/load.py` `load_report`: add

```python
        "trend": json.loads(_read(out_dir, "trend.json") or '{"samples": [], "files": {}}'),
```

- [ ] **Step 4: Run the whole suite** → `OK` (the golden test now runs the trend step; its output is not yet rendered, so the golden file is unchanged).

- [ ] **Step 5: Commit**

```bash
git add gitmole/run.py gitmole/cli.py gitmole/load.py tests/test_run.py tests/test_cli.py tests/test_load.py
git commit -m "trend step in the pipeline; trend.json loaded"
```

### Task 4.4: The `trend` column and the finding

**Files:**
- Modify: `gitmole/render.py` (`hotspots_section`)
- Modify: `gitmole/findings.py` (`complexity_growth`, in `RULES` after `brain_methods`)
- Modify: `README.md`; regenerate `tests/golden/report.txt`
- Test: `tests/test_render.py`, `tests/test_findings.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_render.py` in class `Report`:

```python
    def test_hotspots_carry_a_trend_column_and_a_sparkline_under_full(self):
        r = sample_report()
        r["meta"]["last_date"] = "2026-09-10"
        r["trend"] = {"samples": ["2025-09-10", "2026-03-10", "2026-09-10"],
                      "files": {"static/index.html": [["2025-09-10", 10, 4000], ["2026-03-10", 12, 4000], ["2026-09-10", 16, 4000]]}}
        text = rendered(r, [])
        self.assertRegex(text, r"file\s+revs\s+lines\s+fixes\s+authors\s+trend")
        self.assertRegex(text, r"static/index\.html\s+51\s+4,000\s+0\s+-\s+\+60%")
        self.assertRegex(text, r"static/apps-metadata\.json\s+128\s+800\s+9\s+4\s+-")
        self.assertRegex(rendered(r, [], full=True), r"static/index\.html.*▁▃█")
        self.assertRegex(rendered(sample_report(), []), r"static/index\.html\s+51\s+4,000\s+0\s+-\s+-")
```

Append to `tests/test_findings.py` before `class Advice`:

```python
class ComplexityGrowth(unittest.TestCase):
    def _report(self, growth):
        files = {f"core/f{i}.py": {"code": 100, "complexity": 10} for i in range(5)}
        r = report(size={"files": files}, revisions=[{"entity": f"core/f{i}.py", "n-revs": 50 - i} for i in range(5)])
        r["meta"]["last_date"] = "2026-09-10"
        r["trend"] = {"samples": ["2025-09-10", "2026-09-10"],
                      "files": {f"core/f{i}.py": [["2025-09-10", 10, 100], ["2026-09-10", 10 + g, 100]] for i, g in enumerate(growth)}}
        return r

    def test_three_growers_of_a_quarter_are_a_note_warning_when_the_top_hotspot_grows(self):
        f = findings.complexity_growth(self._report([3, 3, 3, 0, 0]))
        self.assertEqual(f[0]["severity"], "warning", "core/f0.py is the top hotspot and grew")
        self.assertEqual(f[0]["title"], "Hotspots getting more complex")
        self.assertIn("3 of the 10 top hotspots grew by 25% or more in a year: core/f0.py (+30%), core/f1.py (+30%), core/f2.py (+30%)", f[0]["detail"])
        self.assertEqual(f[0]["advice"], "Split core/f0.py before the next change; its complexity grew 30% in a year.")
        f = findings.complexity_growth(self._report([0, 3, 3, 3, 0]))
        self.assertEqual(f[0]["severity"], "info")
        self.assertEqual(f[0]["advice"], "Split core/f1.py before the next change; its complexity grew 30% in a year.")

    def test_two_growers_or_small_growth_is_nothing(self):
        self.assertEqual(findings.complexity_growth(self._report([3, 3, 0, 0, 0])), [])
        self.assertEqual(findings.complexity_growth(self._report([2, 2, 2, 2, 2])), [])
        self.assertEqual(findings.complexity_growth(report()), [])
```

- [ ] **Step 2: Run them to verify they fail** → AssertionError / AttributeError.

- [ ] **Step 3: Implement**

`gitmole/render.py`: import `trend` (`from . import hotspots, identity, knowledge, leaks, loss, textfmt, trend, watch`). In `hotspots_section`, build the cell:

```python
    series = (report.get("trend") or {}).get("files") or {}
    last = report["meta"].get("last_date") or ""
    def trend_cell(path):
        s = series.get(path) or []
        if full is True:
            return trend.sparkline(s) or "-"
        return trend.change_over_year(s, last) if last else "-"
```

Append `trend_cell(h["entity"])` to each row tuple, add `("trend", RIGHT)` at the end of `columns`, and include `"trend"` at the end of the `_keep` list. The `-` cases fall out: no series gives `"-"` from `change_over_year` (fewer than two samples) and `"-"` from the empty sparkline.

`gitmole/findings.py`, after `brain_methods` (import `trend`):

```python
def complexity_growth(report: dict, min_growers: int = 3, min_pct: int = 25) -> list:
    """Top hotspots whose complexity grew over the last year, from the trend samples."""
    series = (report.get("trend") or {}).get("files") or {}
    last = report["meta"].get("last_date") or ""
    if not series or not last:
        return []
    top = [h["entity"] for h in hotspots.ranked(report) if h["code"] is not None][:10]
    grown = []
    for path in top:
        change = trend.change_over_year(series.get(path) or [], last)
        if change.startswith("+") and int(change[1:-1]) >= min_pct:
            grown.append((path, int(change[1:-1])))
    if len(grown) < min_growers:
        return []
    sev = "warning" if top and grown[0][0] == top[0] else "info"
    listed = ", ".join(f"{p} (+{g}%)" for p, g in grown[:5]) + (f" and {len(grown) - 5} more" if len(grown) > 5 else "")
    first = grown[0]
    return [_f(sev, "Hotspots getting more complex",
               f"{len(grown)} of the {len(top)} top hotspots grew by {min_pct}% or more in a year: {listed}.",
               f"Split {first[0]} before the next change; its complexity grew {first[1]}% in a year.")]
```

Add `complexity_growth` to `RULES` after `brain_methods`. (`grown` keeps hotspot order, so `grown[0]` is the highest-ranked grower; the `warning` case checks it is the top hotspot.)

README: in "Tables" item 4 add "hotspots carry a `trend` column: the change in complexity over the last year from scc on the file at sampled commits (`--full` shows the whole series as a sparkline)"; in the findings list add "hotspots getting more complex (three or more of the ten top hotspots grew by a quarter in a year; a warning when the top one did)". In the output table add `| trend.json | trend step | complexity and lines of the top hotspots at sampled commits |`.

- [ ] **Step 4: Run the whole suite, regenerate the golden**

Run: `python3 -m unittest discover -s tests -t .` → the golden test fails on the new column. Run `UPDATE_GOLDEN=1 python3 -m unittest tests.test_golden`, then `git diff tests/golden/report.txt`: the only change must be the `trend` column on the Hotspots table (all `-`, since the golden repo's files have samples but are tiny; if a `+N%` appears, check the numbers by hand before accepting). Run the suite again → `OK`.

- [ ] **Step 5: Manual check and commit**

On mealie, confirm the hotspots table shows percentages, `--full` shows sparklines, and the run is not more than a few seconds slower. Commit; open PR `Complexity trend for the top hotspots`.

```bash
git add gitmole/render.py gitmole/findings.py README.md tests/golden/report.txt tests/test_render.py tests/test_findings.py
git commit -m "Hotspots trend column and the complexity-growth finding"
```

---

# Part 5: Watch-list backtest (PR 5)

## File structure

- Modify `gitmole/maat.py`: `--until`.
- Create `gitmole/backtest.py`: the step.
- Modify `gitmole/watch.py`: `backtest(report)`.
- Modify `gitmole/run.py`, `gitmole/cli.py`: the step, the skip rule, `meta["backtest"]`.
- Modify `gitmole/load.py`: the `backtest` sub-report.
- Modify `gitmole/render.py`: caption under the watch list; JSON.
- Modify `README.md`; regenerate `tests/golden/report.txt`.
- Tests: `tests/test_maat.py`, `tests/test_backtest.py` (new), `tests/test_watch.py`, `tests/test_run.py`, `tests/test_cli.py`, `tests/test_load.py`, `tests/test_render.py`.

### Task 5.1: `--until` in the change analysis

**Files:**
- Modify: `gitmole/maat.py` (`in_window`, `write_all`, `__main__`)
- Test: `tests/test_maat.py`

**Interfaces:**
- Produces: `maat.in_window(commits, since=None, until=None)`: keeps commits with `since <= date < until`; `maat.write_all(..., since=None, until=None)`; script flag `--until YYYY-MM-DD`. Ages (`maat-age.csv`) still use the whole history, as with `--since`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_maat.py`:

```python
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
        self.assertEqual(rows, {"src/a.py": "2", "src/b.py": "2", "img/logo.png": "1"})
        self.assertEqual(act["fix_commits"], 0)
        self.assertEqual(act["until"], "2026-03-10")
```

- [ ] **Step 2: Run it to verify it fails** → TypeError (unexpected keyword).

- [ ] **Step 3: Implement**

In `gitmole/maat.py`:

```python
def in_window(commits: list, since: str = None, until: str = None) -> list:
    """Commits authored on or after `since` and before `until` (YYYY-MM-DD); all of them when both are None."""
    return [c for c in commits if (not since or c["date"] >= since) and (not until or c["date"] < until)]
```

`write_all(log_path, out_dir, aliases_path=None, types=filetypes.DEFAULT, now=None, since=None, until=None)`: `windowed = in_window(commits, since, until)`; and `act["until"] = until` next to `act["window"] = since`. In `__main__`, parse `--until` exactly like `--since` (a `while "--until" in args` block with `validate_now`) and pass it to `write_all`.

- [ ] **Step 4: Run the tests** → `python3 -m unittest tests.test_maat -v` all pass.

- [ ] **Step 5: Commit**

```bash
git add gitmole/maat.py tests/test_maat.py
git commit -m "maat --until: an exclusive upper bound on the window"
```

### Task 5.2: The backtest step

**Files:**
- Create: `gitmole/backtest.py`
- Test: `tests/test_backtest.py`

**Interfaces:**
- Produces: `python -m gitmole.backtest OUT_DIR --until T [--repo DIR]`: writes `OUT_DIR/backtest/{maat-*.csv, activity.json, size.json, meta.json}`; `meta.json` is `{"now": T, "last_date": T, "file_types": <copied from OUT_DIR/meta.json>, "aliases": <copied>}`. Exit 2 when `OUT_DIR/log.txt` or `meta.json` is missing or no commit exists before T.

- [ ] **Step 1: Write the failing test**

Create `tests/test_backtest.py`:

```python
import json
import os
import subprocess
import sys
import tempfile
import unittest

from gitmole import backtest


def history_repo(d):
    """18 months: hot.py churns early and is fixed late; calm.py is touched once."""
    def git(*args, date):
        e = dict(os.environ, GIT_CONFIG_GLOBAL="/dev/null", GIT_CONFIG_SYSTEM="/dev/null",
                 GIT_AUTHOR_NAME="A", GIT_AUTHOR_EMAIL="a@x", GIT_COMMITTER_NAME="A", GIT_COMMITTER_EMAIL="a@x",
                 GIT_AUTHOR_DATE=f"{date}T10:00:00", GIT_COMMITTER_DATE=f"{date}T10:00:00")
        subprocess.run(["git", *args], cwd=d, check=True, capture_output=True, env=e)
    git("init", "-q", date="2025-01-01")
    open(os.path.join(d, "calm.py"), "w").write("x = 1\n")
    open(os.path.join(d, "hot.py"), "w").write("def f():\n    return 1\n")
    git("add", "-A", date="2025-01-01"); git("commit", "-q", "-m", "start", date="2025-01-01")
    for i, date in enumerate(["2025-02-01", "2025-04-01", "2025-06-01", "2025-08-01", "2025-10-01"], start=2):
        open(os.path.join(d, "hot.py"), "a").write(f"def f{i}():\n    return {i}\n")
        git("commit", "-q", "-am", f"grow {i}", date=date)
    open(os.path.join(d, "hot.py"), "a").write("# fixed\n")
    git("commit", "-q", "-am", "fix: crash in hot", date="2026-04-01")
    open(os.path.join(d, "calm.py"), "a").write("y = 2\n")
    git("commit", "-q", "-am", "tweak calm", date="2026-06-01")


def export(d, out):
    os.makedirs(out, exist_ok=True)
    log = subprocess.run(["git", "-c", "core.quotePath=false", "log", "--all", "--use-mailmap", "--numstat", "--date=iso-strict",
                          "--pretty=format:--%h--%ad--%aN--%s", "--no-renames"], cwd=d, capture_output=True, text=True, check=True).stdout
    with open(os.path.join(out, "log.txt"), "w") as fh:
        fh.write(log)
    with open(os.path.join(out, "meta.json"), "w") as fh:
        json.dump({"name": "x", "first_date": "2025-01-01", "last_date": "2026-06-01", "file_types": None, "aliases": {}}, fh)


class Step(unittest.TestCase):
    def test_writes_the_change_analysis_and_size_as_of_the_cut_off(self):
        with tempfile.TemporaryDirectory() as d:
            history_repo(d)
            out = os.path.join(d, "out")
            export(d, out)
            rc = backtest.main([out, "--until", "2025-12-01", "--repo", d])
            self.assertEqual(rc, 0)
            sub = os.path.join(out, "backtest")
            with open(os.path.join(sub, "maat-revisions.csv")) as fh:
                revs = dict(line.strip().split(",") for line in fh.readlines()[1:])
            with open(os.path.join(sub, "size.json")) as fh:
                size = json.load(fh)
            with open(os.path.join(sub, "meta.json")) as fh:
                meta = json.load(fh)
        self.assertEqual(revs, {"hot.py": "6", "calm.py": "1"}, "the fix and the tweak are after the cut-off")
        self.assertEqual(sorted(f["Location"] for r in size for f in r["Files"]), ["calm.py", "hot.py"])
        hot = next(f for r in size for f in r["Files"] if f["Location"] == "hot.py")
        self.assertEqual(hot["Code"], 12, "hot.py as it was on 2025-10-01: six two-line functions")
        self.assertEqual(meta, {"now": "2025-12-01", "last_date": "2025-12-01", "file_types": None, "aliases": {}})

    def test_no_commit_before_the_cut_off_exits_2(self):
        with tempfile.TemporaryDirectory() as d:
            history_repo(d)
            out = os.path.join(d, "out")
            export(d, out)
            self.assertEqual(backtest.main([out, "--until", "2024-01-01", "--repo", d]), 2)

    def test_runs_as_a_module(self):
        p = subprocess.run([sys.executable, "-m", "gitmole.backtest", "--help"], capture_output=True, text=True,
                           env=dict(os.environ, PYTHONPATH=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
        self.assertEqual(p.returncode, 0, p.stderr)
```

- [ ] **Step 2: Run it to verify it fails** → `ModuleNotFoundError`.

- [ ] **Step 3: Implement**

Create `gitmole/backtest.py`:

```python
#!/usr/bin/env python3
"""The repository as it was at a cut-off date, for checking the watch list against what came after.

Runs as a pipeline step: `python -m gitmole.backtest OUT_DIR --until T [--repo DIR]`, from inside
the repository. Reruns the change analysis over OUT_DIR/log.txt with the window ending at T and T as
the reference date, exports the tree at the last commit before T and runs scc on it, and writes it
all under OUT_DIR/backtest/ with a meta.json the loader accepts."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile

from . import filetypes, load, maat


def rev_before(repo: str, date: str):
    proc = subprocess.run(["git", "rev-list", "-1", f"--before={date}T00:00:00", "HEAD"], cwd=repo, capture_output=True, text=True)
    return proc.stdout.strip() or None


def size_at(repo: str, rev: str) -> str:
    """scc's --by-file JSON over the tree at rev."""
    with tempfile.TemporaryDirectory(prefix="gitmole-backtest-") as tmp:
        archive = subprocess.run(["git", "archive", rev], cwd=repo, capture_output=True, check=True)
        subprocess.run(["tar", "-x", "-C", tmp], input=archive.stdout, check=True)
        return subprocess.run(["scc", "--by-file", "--format", "json"], cwd=tmp, capture_output=True, text=True, check=True).stdout


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("out")
    p.add_argument("--until", required=True)
    p.add_argument("--repo", default=".")
    args = p.parse_args(argv)
    try:
        until = maat.validate_now(args.until)
    except ValueError as e:
        print(f"backtest: {e}", file=sys.stderr)
        return 2
    log_path = os.path.join(args.out, "log.txt")
    meta = json.loads(load._read(args.out, "meta.json") or "{}")
    if not meta or not os.path.exists(log_path):
        print("backtest: meta.json and log.txt are needed", file=sys.stderr)
        return 2
    rev = rev_before(args.repo, until)
    if not rev:
        print(f"backtest: no commit before {until}", file=sys.stderr)
        return 2
    sub = os.path.join(args.out, "backtest")
    os.makedirs(sub, exist_ok=True)
    types = filetypes.parse(meta.get("file_types"))
    maat.write_all(log_path, sub, os.path.join(args.out, "meta.json") if "aliases" in meta else None, types, now=until, until=until)
    with open(os.path.join(sub, "size.json"), "w", encoding="utf-8") as fh:
        fh.write(size_at(args.repo, rev))
    with open(os.path.join(sub, "meta.json"), "w", encoding="utf-8") as fh:
        json.dump({"now": until, "last_date": until, "file_types": meta.get("file_types"), "aliases": meta.get("aliases", {})}, fh)
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run the tests** → `python3 -m unittest tests.test_backtest -v` all pass.

- [ ] **Step 5: Commit**

```bash
git add gitmole/backtest.py tests/test_backtest.py
git commit -m "backtest step: the change analysis and size as of a cut-off"
```

### Task 5.3: Evaluate the past watch list

**Files:**
- Modify: `gitmole/watch.py`
- Test: `tests/test_watch.py`

**Interfaces:**
- Consumes: `report["backtest"]` (a report dict loaded from `OUT_DIR/backtest/`, Task 5.4) with `meta["now"]`, `size`, `revisions`, `fixes`, `authors`, `ownership`, `coupling`; `report["fixes"]` (current).
- Produces: `watch.backtest(report) -> dict | None`: `{"t", "listed", "fixed", "hits", "expected"}` where `fixed` counts current source files with `last-fix > t`, `expected = listed * fixed / files_at_t` (files at t = source files in `backtest["size"]["files"]`), rounded to one decimal; `None` when there is no backtest sub-report or it has no size data.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_watch.py`:

```python
class Backtest(unittest.TestCase):
    def test_counts_how_many_files_fixed_since_the_cut_off_were_on_the_list(self):
        past = report()   # the same synthetic repo, taken as the state at T
        past["meta"] = {"now": "2026-03-01"}
        r = report(fixes=[{"entity": "core/parser.py", "n-fixes": 9, "last-fix": "2026-09-01", "recent-fixes": 5},
                          {"entity": "core/other.py", "n-fixes": 1, "last-fix": "2026-05-01", "recent-fixes": 1},
                          {"entity": "core/util.py", "n-fixes": 2, "last-fix": "2025-01-01", "recent-fixes": 0},
                          {"entity": "tests/test_parser.py", "n-fixes": 3, "last-fix": "2026-08-01", "recent-fixes": 3}],
                   backtest=past)
        out = watch.backtest(r)
        self.assertEqual(out["t"], "2026-03-01")
        self.assertEqual(out["listed"], 3, "the past list has three scorable files")
        self.assertEqual(out["fixed"], 2, "parser and other; util's fix is older, the test file does not count")
        self.assertEqual(out["hits"], 1, "parser was listed; other was not")
        self.assertAlmostEqual(out["expected"], round(3 * 2 / 3, 1), "3 listed × 2 fixed / 3 source files in the tree at T")

    def test_none_without_a_backtest(self):
        self.assertIsNone(watch.backtest(report()))
        self.assertIsNone(watch.backtest(report(backtest={"meta": {"now": "2026-03-01"}, "size": {"files": {}}})))
```

- [ ] **Step 2: Run it to verify it fails** → `AttributeError`.

- [ ] **Step 3: Implement**

Append to `gitmole/watch.py`:

```python
def backtest(report: dict):
    """How the watch list as of the cut-off T (report["backtest"]) did against the fixes that came after."""
    past = report.get("backtest")
    if not past or not (past.get("size") or {}).get("files"):
        return None
    t = past["meta"]["now"]
    listed = [r["file"] for r in risks(past)[:WATCH_TOP]]
    fixed = {f["entity"] for f in report.get("fixes") or [] if f.get("last-fix", "") > t and not filetypes.is_test_path(f["entity"])}
    source_at_t = [p for p in past["size"]["files"] if not filetypes.is_test_path(p)]
    expected = round(len(listed) * len(fixed) / len(source_at_t), 1) if source_at_t else 0.0
    return {"t": t, "listed": len(listed), "fixed": len(fixed), "hits": len(fixed.intersection(listed)), "expected": expected}
```

- [ ] **Step 4: Run the tests** → `python3 -m unittest tests.test_watch -v` all pass.

- [ ] **Step 5: Commit**

```bash
git add gitmole/watch.py tests/test_watch.py
git commit -m "watch.backtest: the past list against the fixes since"
```

### Task 5.4: Wire the step, the skip rule, the loader, the caption, JSON, README, golden

**Files:**
- Modify: `gitmole/run.py` (`plan(..., backtest=None)`, `OUTPUTS`/`clear_outputs` for the `backtest/` directory)
- Modify: `gitmole/cli.py` (`_analyse`: compute T and the skip rule; `meta["backtest"]`)
- Modify: `gitmole/load.py` (`report["backtest"]`)
- Modify: `gitmole/render.py` (`watch_section` caption; `to_json`)
- Modify: `README.md`; regenerate `tests/golden/report.txt`
- Test: `tests/test_run.py`, `tests/test_cli.py`, `tests/test_load.py`, `tests/test_render.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_run.py`, class `Plan`:

```python
    def test_backtest_step_runs_after_the_change_analysis_when_a_cut_off_is_given(self):
        by = {s["name"]: s for s in run.plan("/r", "/o", backtest="2025-12-01")}
        self.assertEqual(by["backtest"]["argv"][:3], [sys.executable, "-m", "gitmole.backtest"])
        self.assertEqual(by["backtest"]["argv"][3:], ["/o", "--until", "2025-12-01"])
        self.assertEqual(by["backtest"]["deps"], ["git-log", "change analysis"])
        self.assertNotIn("backtest", [s["name"] for s in run.plan("/r", "/o")])

    def test_clear_outputs_removes_the_backtest_directory(self):
        with tempfile.TemporaryDirectory() as d:
            os.makedirs(os.path.join(d, "backtest"))
            open(os.path.join(d, "backtest", "size.json"), "w").close()
            run.clear_outputs(d)
            self.assertFalse(os.path.exists(os.path.join(d, "backtest")))
```

`tests/test_cli.py`, new class:

```python
class BacktestWindow(unittest.TestCase):
    def _run(self, dates):
        import subprocess
        calls = []
        with tempfile.TemporaryDirectory() as d:
            subprocess.run(["git", "init", "-q", d], check=True)
            for date in dates:
                subprocess.run(["git", "-C", d, "-c", "user.name=T", "-c", "user.email=t@x.com", "commit", "-q", "--allow-empty", "-m", date],
                               check=True, env=dict(os.environ, GIT_AUTHOR_DATE=f"{date}T10:00:00", GIT_COMMITTER_DATE=f"{date}T10:00:00"))
            out = os.path.join(d, "out")
            def planner(repo, o, branch="HEAD", **kw):
                calls.append(kw)
                return [{"name": "q", "argv": ["true"], "stdout": None, "deps": []}]
            cli.main([d, "--out", out], console=console(), tool_check=lambda **kw: [], planner=planner,
                     estimator=lambda repo, interval, **kw: {"files": 1, "samples": 1, "blames": 1, "seconds": 0.0})
            with open(os.path.join(out, "meta.json")) as fh:
                return calls[0], json.load(fh)

    def test_cut_off_six_months_before_the_last_commit_with_a_year_of_history(self):
        kw, meta = self._run(["2025-01-01", "2025-08-01", "2026-03-01"])
        self.assertEqual(kw["backtest"], "2025-09-01")
        self.assertEqual(meta["backtest"], {"status": "planned", "until": "2025-09-01"})

    def test_too_little_history_skips(self):
        kw, meta = self._run(["2025-06-01", "2026-03-01"])
        self.assertIsNone(kw["backtest"])
        self.assertEqual(meta["backtest"], {"status": "skipped", "reason": "too little history to backtest"})
```

`tests/test_load.py`, class `LoadReport`:

```python
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
```

`tests/test_render.py`, class `Report`:

```python
    def test_watch_list_caption_reports_the_backtest_or_why_not(self):
        r = sample_report()
        r["meta"]["backtest"] = {"status": "skipped", "reason": "too little history to backtest"}
        self.assertIn("too little history to backtest", rendered(r, []))
        r = sample_report()
        past = sample_report()
        past["meta"] = {"now": "2026-03-10"}
        r["backtest"] = past
        r["fixes"] = [{"entity": "static/index.html", "n-fixes": 1, "last-fix": "2026-08-01", "recent-fixes": 1},
                      {"entity": "static/other.html", "n-fixes": 1, "last-fix": "2026-08-01", "recent-fixes": 1}]
        text = rendered(r, [])
        self.assertIn("6 months ago this list would have named 1 of the 2 files fixed since (a random 2 would name 2.0)", text)
        self.assertEqual(render.to_json(r, [])["watch_backtest"]["hits"], 1)
```

(`sample_report()`'s size has two files, both source, and `risks` scores both; so `listed` is 2 and `expected` is 2 × 2 / 2 = 2.0.)

- [ ] **Step 2: Run them to verify they fail**.

- [ ] **Step 3: Implement**

`gitmole/run.py`:
- `plan(..., trend=True, samples=12, backtest: str = None)`; after the trend block:

```python
    if backtest:
        steps.append({"name": "backtest", "argv": [sys.executable, "-m", "gitmole.backtest", out_dir, "--until", backtest],
                      "stdout": None, "deps": ["git-log", "change analysis"]})
```

- `clear_outputs`: after removing files, `import shutil; shutil.rmtree(os.path.join(out_dir, "backtest"), ignore_errors=True)`.

`gitmole/cli.py` `_analyse`, after `meta["trend"] = ...`:

```python
    from . import maat as _maat
    cut = _maat.months_before(meta["last_date"], 6) if meta["last_date"] else None
    if cut and meta["first_date"] and meta["first_date"] <= _maat.months_before(cut, 6):
        meta["backtest"] = {"status": "planned", "until": cut}
    else:
        cut = None
        meta["backtest"] = {"status": "skipped", "reason": "too little history to backtest"}
```

pass `backtest=cut` to `planner(...)`, and after the run `if cut: meta["backtest"]["status"] = status("backtest")`.

`gitmole/load.py` `load_report`: add a parameter `nested=True` and, in the dict, `"backtest": load_report(os.path.join(out_dir, "backtest"), nested=False) if nested and os.path.isfile(os.path.join(out_dir, "backtest", "meta.json")) else None`.

`gitmole/render.py` `watch_section`: build the caption lines as a list:

```python
    notes = ["ranked by churn × recent fixes × complexity × single ownership" + (f"; commits since {since}" if since else "")]
    bt = watch.backtest(report)
    status = report["meta"].get("backtest") or {}
    if bt:
        notes.append(f"6 months ago this list would have named {bt['hits']} of the {bt['fixed']} files fixed since "
                     f"(a random {bt['listed']} would name {bt['expected']})")
    elif status.get("reason"):
        notes.append(status["reason"])
    elif status.get("status") in ("failed", "timeout"):
        notes.append(f"backtest {status['status']}")
    caption = "\n".join(notes)
```

`to_json`: add `"watch_backtest": watch.backtest(report)` (None when absent; drop the key when None).

README: in "Big repositories" or after the watch list description add: "Under the watch list, one line says how the list would have done: gitmole reruns the change analysis as of six months before the last commit, with scc on the tree at that time, ranks the watch list from that, and counts how many of the files fixed since were on it, next to what a random list of the same size would score. Repositories with under a year of history say `too little history to backtest`." Add `| backtest/ | backtest step | the change analysis and size as of six months before the last commit |` to the output table.

- [ ] **Step 4: Run the whole suite, regenerate the golden**

Run the suite; the golden test fails on the new caption. `UPDATE_GOLDEN=1 python3 -m unittest tests.test_golden`; `git diff tests/golden/report.txt` must show only the added line `too little history to backtest` under the watch list (the golden repo spans 17 months, so check: last commit 2025-05-30, T = 2024-11-30, first commit 2024-01-10 ≤ 2024-05-30 → the backtest runs. Then the caption is the "6 months ago" line; read the numbers and confirm by hand: which files were fixed after 2024-11-30 in the golden history, and which the past list names). Accept only when the numbers are right. Run the suite again → `OK`.

- [ ] **Step 5: Manual check and commit**

On mealie: the caption shows hits out of fixed with the random baseline; check `backtest/size.json` exists and `backtest/` is removed on a rerun. Commit; open PR `Watch-list backtest`.

```bash
git add gitmole/run.py gitmole/cli.py gitmole/load.py gitmole/render.py README.md tests/golden/report.txt tests/test_run.py tests/test_cli.py tests/test_load.py tests/test_render.py
git commit -m "Backtest step, skip rule, watch-list caption, JSON export"
```

---

## Self-review notes

- Spec coverage: reverts (1.1–1.3), knowledge loss with `--gone`, `(gone)` marker, `lost` column, no-blame fallback (2.1–2.5), change risk with base ref, `--no-run`, remote refusal, JSON, no gate (3.1–3.3), trend step with `PYTHONPATH`, column, sparkline, finding, status (4.1–4.4), backtest with `--until`, cut-off and skip rule, evaluation with baseline, caption, JSON (5.1–5.4). Golden regenerated in Parts 4 and 5 only.
- Names used across tasks: `maat.months_before`, `loss.gone/cutoff/surviving/areas`, `run.changed_files`, `watch.change_risk/backtest/WATCH_TOP`, `render.risk_section`, `trend.sample_dates/change_over_year/sparkline/main`, `backtest.main`, `maat.in_window(commits, since, until)`. Each is defined before it is used.
- `loss.areas` takes ownership rows: the knowledge map passes all of them (so the areas shown do not change when someone is gone), the finding passes source rows only.

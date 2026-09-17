# README Visual and Example Reports Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The README opens with a picture of the coloured report for a repository people know, and `docs/examples/` holds committed, reproducible gitmole reports for curl, django, react and (if it finishes) kubernetes, each with a watch list and its backtest.

**Architecture:** `render.excerpt()` prints the top of the report (header, findings, watch list) to any rich console. A new script `bin/render-examples`, built like `bin/render-banner`, clones each example repository once under `$TMPDIR/gitmole-examples/`, pins it to a recorded commit, runs gitmole with a fixed `GITMOLE_NOW`, writes `docs/examples/<repo>.md` from the Markdown export, and records the featured repository's excerpt through rich's `Console.export_svg` into `docs/report.svg`. The README embeds that SVG at the top and links the example reports from a table; `docs/example.md` (gitmole on itself) goes away.

**Tech Stack:** Python 3.9+, rich 13+ (`Console(record=True).export_svg`), git, the five external tools, `unittest`.

**Spec:** No separate spec. The design was agreed in chat on 2026-09-17 from two pieces of README feedback: (3) put a visual at the top, and (4) show reports on repositories people know, committed under `docs/examples/`. Decisions taken: a rich SVG rather than a vhs GIF (no new tools, reproducible, crisp); repositories curl, django, react, plus kubernetes only if its report is not mostly budget skips; pinned commits and a fixed reference date so reruns give the same files.

## Global Constraints

- Python 3.9 is the floor (`pyproject.toml`): `from __future__ import annotations` in any new module, no `match`.
- No new dependencies. rich is already required; git is already required.
- Tests run from the checkout root with `python3 -m unittest discover -s tests -t .`. If that interpreter lacks rich, use `/opt/homebrew/Cellar/gitmole/0.7.0/libexec/bin/python` in its place, for the tests and for `bin/render-examples`.
- `bin/` scripts are plain Python files with a `#!/usr/bin/env python3` line and no `.py` suffix (see `bin/render-banner`); their pure functions are tested by loading the file with `importlib`.
- Rules in this repository never key on product or person names. Nothing in this plan adds a rule; the example repositories are data, listed in one table in the script.
- The example reports name real contributors of public repositories (bus factor, knowledge islands, people table). That is public git-log information; secret values never appear because gitmole stores keyed hashes. Still, read each generated file before committing it.
- The README's image URL is absolute (`https://raw.githubusercontent.com/antvinni/gitmole/main/docs/report.svg`) like the banner's, so it also renders on PyPI.
- Work on a branch off `main`. Commit after each task. Do not open a pull request unless the user asks.
- Long runs (the clones and analyses in Task 3) go through `run_in_background` and are waited for; never shortened or killed for being slow.

---

### Task 1: `render.excerpt()`, the top of the report on its own

**Files:**
- Modify: `gitmole/render.py` (after `report()`, around line 812)
- Test: `tests/test_render.py`

**Interfaces:**
- Consumes: `header(report, findings) -> Panel`, `findings_panel(findings, report) -> Panel`, `watch_section(report, full, width) -> dict`, `print_section(console, sec)` from `gitmole/render.py`.
- Produces: `render.excerpt(report: dict, findings: list, console: Console, full: bool = False) -> None`. Prints the header panel, the findings panel and the watch list section (blank line, heading, table, caption) and nothing else. Task 2 records it to SVG and to plain text.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_render.py`:

```python
class Excerpt(unittest.TestCase):
    def _text(self, findings=()):
        console = Console(file=io.StringIO(), width=100, record=True, force_terminal=False, color_system=None)
        render.excerpt(sample_report(), list(findings), console)
        return console.export_text()

    def test_prints_header_findings_and_watch_list(self):
        text = self._text()
        self.assertIn("demo", text)                     # header panel title
        self.assertIn("363 commits", text)
        self.assertIn("Findings", text)
        self.assertIn("Watch list", text)
        self.assertIn("static/apps-metadata.json", text)   # the top watch row: 128 revisions

    def test_prints_nothing_else(self):
        text = self._text()
        for heading in ("Hotspots", "People", "Knowledge map", "Timeline", "Change coupling", "Repo health", "Full results"):
            self.assertNotIn(heading, text)

    def test_findings_are_listed(self):
        found = [{"severity": "warning", "title": "Bus factor of one", "detail": "Ann wrote 80% of the code",
                  "advice": "Pair someone with Ann."}]
        text = self._text(found)
        self.assertIn("Bus factor of one", text)
        self.assertIn("Findings (1)", text)
```

A finding is a dict with `severity`, `title`, `detail` (the statement followed by the advice) and `advice`, exactly as `gitmole/findings.py` builds them; `textfmt.group_findings` reads those four keys.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python3 -m unittest tests.test_render.Excerpt -v`
Expected: three errors with `AttributeError: module 'gitmole.render' has no attribute 'excerpt'`.

- [ ] **Step 3: Implement `excerpt`**

In `gitmole/render.py`, directly after `report()` and before the `# --- markdown / json` comment:

```python
def excerpt(report: dict, findings: list, console: Console, full: bool = False) -> None:
    """The top of the report on its own: header, findings and the watch list. What a screenshot shows."""
    console.print(header(report, findings))
    console.print(findings_panel(findings, report))
    print_section(console, watch_section(report, full=full, width=console.width))
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python3 -m unittest tests.test_render -v`
Expected: every test in the module passes, including the three new ones.

- [ ] **Step 5: Run the whole suite**

Run: `python3 -m unittest discover -s tests -t .`
Expected: OK (the golden test may report `skipped` when a tool is missing; that is fine).

- [ ] **Step 6: Commit**

```bash
git add gitmole/render.py tests/test_render.py
git commit -m "render.excerpt prints the header, findings and watch list on their own

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 2: `bin/render-examples`, the script that makes the reports and the SVG

**Files:**
- Create: `bin/render-examples` (executable)
- Test: `tests/test_render_examples.py`

**Interfaces:**
- Consumes: `render.excerpt` (Task 1); `run.repo_name(target) -> str` and `run.clone_url(target) -> str` from `gitmole/run.py`; `load.load_report(out_dir) -> dict`; `findings.evaluate(report) -> list`; `gitmole.__version__`.
- Produces, as module-level names in the script (tests load the file with `importlib`):
  - `NOW: str` (`"2026-09-17"`), `TIMEOUT: int` (`3600`), `WIDTH: int` (`100`), `FEATURED: str`.
  - `EXAMPLES: list[tuple[str, str]]` of `(owner/repo, full commit sha)`.
  - `workspace() -> str`: `$TMPDIR/gitmole-examples` (or `tempfile.gettempdir()` when `TMPDIR` is unset).
  - `checkout(target: str, sha: str) -> str`: clone or fetch, put the default branch at `sha`, return the clone path.
  - `analyse(clone: str, out_dir: str) -> str`: run gitmole, return the Markdown export.
  - `document(target: str, sha: str, markdown: str) -> str`: the committed file: title, provenance line, body without the machine-specific last line.
  - `excerpt(out_dir: str) -> tuple[str, str]`: `(svg, plain_text)` of the report's top.
  - `main(argv: list[str]) -> int`.
- Files written: `docs/examples/<repo>.md` per example, `docs/report.svg` for `FEATURED`; the plain-text excerpt of `FEATURED` goes to stdout for pasting into the README.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_render_examples.py`:

```python
"""The pure parts of bin/render-examples: the committed document's shape and the pins' shape."""
import importlib.machinery
import importlib.util
import os
import re
import unittest

PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "bin", "render-examples")


def load():
    loader = importlib.machinery.SourceFileLoader("render_examples", PATH)
    spec = importlib.util.spec_from_loader("render_examples", loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


MARKDOWN = """# curl

35000 commits · 1999-12-29 → 2026-09-17 · 900 identities · branch master  
200,000 lines in 1,200 files · C

## Findings

- something

## Watch list

| file | why |
| --- | --- |
| lib/url.c | changed 800 times |

betterleaks scanned every commit on every branch

Full results and plots in /private/tmp/x/gitmole-examples/analysis-curl
"""


class Document(unittest.TestCase):
    def setUp(self):
        self.mod = load()
        self.doc = self.mod.document("curl/curl", "a" * 40, MARKDOWN)

    def test_keeps_the_title_first(self):
        self.assertTrue(self.doc.startswith("# curl\n"))

    def test_provenance_names_version_target_commit_and_date(self):
        from gitmole import __version__
        line = self.doc.split("\n")[2]
        self.assertIn(f"gitmole {__version__}", line)
        self.assertIn("[curl/curl](https://github.com/curl/curl)", line)
        self.assertIn("https://github.com/curl/curl/commit/" + "a" * 40, line)
        self.assertIn("`" + "a" * 12 + "`", line)
        self.assertIn(self.mod.NOW, line)
        self.assertIn("bin/render-examples", line)
        self.assertIn("(https://github.com/antvinni/gitmole#readme)", line)

    def test_drops_the_machine_specific_last_line(self):
        self.assertNotIn("Full results and plots", self.doc)
        self.assertNotIn("/private/tmp", self.doc)
        self.assertTrue(self.doc.endswith("every commit on every branch\n"))

    def test_body_is_otherwise_unchanged(self):
        self.assertIn("| lib/url.c | changed 800 times |", self.doc)
        self.assertIn("## Watch list", self.doc)


class Pins(unittest.TestCase):
    def test_every_example_is_a_github_target_with_a_full_sha(self):
        mod = load()
        self.assertGreaterEqual(len(mod.EXAMPLES), 3)
        for target, sha in mod.EXAMPLES:
            self.assertRegex(target, r"^[\w.-]+/[\w.-]+$")
            self.assertRegex(sha, r"^[0-9a-f]{40}$", f"{target} is not pinned to a full commit hash")

    def test_names_are_unique_and_featured_is_one_of_them(self):
        mod = load()
        from gitmole import run
        names = [run.repo_name(t) for t, _ in mod.EXAMPLES]
        self.assertEqual(len(names), len(set(names)))
        self.assertIn(mod.FEATURED, names)

    def test_constants(self):
        mod = load()
        self.assertRegex(mod.NOW, r"^\d{4}-\d{2}-\d{2}$")
        self.assertEqual(mod.WIDTH, 100)
        self.assertGreaterEqual(mod.TIMEOUT, 900)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python3 -m unittest tests.test_render_examples -v`
Expected: every test errors with `FileNotFoundError` for `bin/render-examples`.

- [ ] **Step 3: Write the script**

Create `bin/render-examples`. The pins are placeholders here on purpose: Task 3 replaces them with real hashes before the `Pins` tests can pass.

```python
#!/usr/bin/env python3
"""Regenerate docs/examples/*.md and docs/report.svg from pinned clones of well-known repositories.

Each repository is cloned once under $TMPDIR/gitmole-examples/, put at its pinned commit and analysed
with a fixed reference date, so a rerun on any machine writes the same files. The featured repository's
header, findings and watch list are also recorded as docs/report.svg for the README, and printed as
plain text on stdout for the README's text block.

    bin/render-examples              # every repository
    bin/render-examples curl react   # only these; the SVG is refreshed when the featured one ran
"""
from __future__ import annotations

import io
import os
import re
import subprocess
import sys
import tempfile

from rich.console import Console

ROOT = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
sys.path.insert(0, ROOT)
from gitmole import __version__, findings, load, render, run  # noqa: E402

NOW = "2026-09-17"      # GITMOLE_NOW for every run: file ages and the backtest cut-off stay fixed
TIMEOUT = 3600          # seconds any single tool may run; kubernetes needs more than the default 900
WIDTH = 100             # the README's text block and the SVG share one width
FEATURED = "curl"       # whose excerpt becomes docs/report.svg and the README's text block

# (owner/repo, commit): the default branch tip on the day the examples were last regenerated.
# A new pin comes from:  git ls-remote https://github.com/OWNER/REPO HEAD
EXAMPLES = [
    ("curl/curl", "0000000000000000000000000000000000000000"),
    ("django/django", "0000000000000000000000000000000000000000"),
    ("facebook/react", "0000000000000000000000000000000000000000"),
    ("kubernetes/kubernetes", "0000000000000000000000000000000000000000"),
]


def workspace() -> str:
    return os.path.join(os.environ.get("TMPDIR") or tempfile.gettempdir(), "gitmole-examples")


def git(*args: str, cwd: str | None = None) -> str:
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True).stdout


def checkout(target: str, sha: str) -> str:
    """Clone target once under the workspace, then put its default branch at sha. Returns the clone."""
    dest = os.path.join(workspace(), run.repo_name(target))
    if os.path.isdir(dest):
        git("fetch", "--quiet", "origin", cwd=dest)
    else:
        os.makedirs(workspace(), exist_ok=True)
        git("clone", "--quiet", run.clone_url(target), dest)
    branch = git("rev-parse", "--abbrev-ref", "origin/HEAD", cwd=dest).strip().split("/", 1)[1]
    git("checkout", "--quiet", "--force", "-B", branch, sha, cwd=dest)   # a named branch, so the report's header shows it
    return dest


def analyse(clone: str, out_dir: str) -> str:
    """Run gitmole on the clone; progress stays on stderr, the Markdown export comes back."""
    argv = [sys.executable, "-m", "gitmole", clone, "--out", out_dir, "--timeout", str(TIMEOUT), "--markdown", "-"]
    return subprocess.run(argv, check=True, stdout=subprocess.PIPE, text=True).stdout


def document(target: str, sha: str, markdown: str) -> str:
    """The committed file: the title, a provenance line, then the export without its machine-specific last line."""
    title, rest = markdown.split("\n", 1)
    body = re.sub(r"\n+Full results and plots in [^\n]*\n?$", "\n", rest)
    provenance = (f"_gitmole {__version__} on [{target}](https://github.com/{target}) at "
                  f"[`{sha[:12]}`](https://github.com/{target}/commit/{sha}), reference date {NOW}; "
                  f"regenerated by `bin/render-examples`; back to [the README](https://github.com/antvinni/gitmole#readme)._")
    return f"{title}\n\n{provenance}\n{body}"


def excerpt(out_dir: str) -> tuple[str, str]:
    """(svg, plain text) of the report's top for a finished output directory."""
    report = load.load_report(out_dir)
    found = findings.evaluate(report)
    colour = Console(file=io.StringIO(), width=WIDTH, record=True, force_terminal=True, color_system="truecolor")
    render.excerpt(report, found, colour)
    plain = Console(file=io.StringIO(), width=WIDTH, record=True, force_terminal=False, color_system=None)
    render.excerpt(report, found, plain)
    name = report["meta"]["name"]
    return colour.export_svg(title=f"gitmole {name}", unique_id="gitmole"), plain.export_text()


def main(argv: list[str]) -> int:
    os.environ["GITMOLE_NOW"] = NOW   # the analyses and the in-process excerpt use the same date
    names = [run.repo_name(t) for t, _ in EXAMPLES]
    unknown = sorted(set(argv) - set(names))
    if unknown:
        print(f"unknown example: {', '.join(unknown)}; choose from {', '.join(names)}", file=sys.stderr)
        return 2
    wanted = set(argv) or set(names)
    examples_dir = os.path.join(ROOT, "docs", "examples")
    os.makedirs(examples_dir, exist_ok=True)
    for target, sha in EXAMPLES:
        name = run.repo_name(target)
        if name not in wanted:
            continue
        clone = checkout(target, sha)
        out_dir = os.path.join(workspace(), f"analysis-{name}")
        markdown = analyse(clone, out_dir)
        path = os.path.join(examples_dir, f"{name}.md")
        with open(path, "w") as fh:
            fh.write(document(target, sha, markdown))
        print(f"wrote {os.path.relpath(path, ROOT)}", file=sys.stderr)
    featured_out = os.path.join(workspace(), f"analysis-{FEATURED}")
    if os.path.isfile(os.path.join(featured_out, "meta.json")):
        svg, text = excerpt(featured_out)
        svg_path = os.path.join(ROOT, "docs", "report.svg")
        with open(svg_path, "w") as fh:
            fh.write(svg)
        print(f"wrote {os.path.relpath(svg_path, ROOT)} ({os.path.getsize(svg_path):,} bytes); the text below is the README block",
              file=sys.stderr)
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
```

Then make it executable:

```bash
chmod +x bin/render-examples
```

- [ ] **Step 4: Run the tests**

Run: `python3 -m unittest tests.test_render_examples -v`
Expected: the four `Document` tests and `Pins.test_names_are_unique_and_featured_is_one_of_them` and `Pins.test_constants` pass; `Pins.test_every_example_is_a_github_target_with_a_full_sha` passes too, because forty zeros match the pattern. The real pins land in Task 3. If `test_provenance_names_version_target_commit_and_date` fails on the line index, print `self.doc.split("\n")[:4]` and fix the index: the provenance is the third line (index 2), after the title and one blank line.

- [ ] **Step 5: Smoke-test the excerpt path against this checkout**

The SVG export needs a real output directory; this repository's own analysis is the cheapest one.

Run:

```bash
gitmole . --out "$TMPDIR/gitmole-examples/analysis-gitmole"
```

Then, from the checkout root, in a file `$TMPDIR/smoke.py`:

```python
import importlib.machinery, importlib.util, os, sys
sys.path.insert(0, os.getcwd())
loader = importlib.machinery.SourceFileLoader("render_examples", "bin/render-examples")
spec = importlib.util.spec_from_loader("render_examples", loader)
mod = importlib.util.module_from_spec(spec)
loader.exec_module(mod)
os.environ["GITMOLE_NOW"] = mod.NOW
svg, text = mod.excerpt(os.path.join(os.environ["TMPDIR"], "gitmole-examples", "analysis-gitmole"))
open(os.path.join(os.environ["TMPDIR"], "smoke.svg"), "w").write(svg)
print(text)
print(len(svg), "bytes of svg")
```

Run: `python3 "$TMPDIR/smoke.py"`
Expected: the plain text shows the three panels at width 100, exactly like the README's current block plus the watch list; the SVG is well under 200 kB. Open `$TMPDIR/smoke.svg` with the Read tool to check it renders: box borders, colours, the ▲ ● ✔ ↳ marks. rich's SVG declares Fira Code from a CDN; GitHub's image proxy blocks that, so the fallback is the viewer's monospace font, which is fine for box drawing.

- [ ] **Step 6: Run the whole suite and commit**

Run: `python3 -m unittest discover -s tests -t .`
Expected: OK.

```bash
git add bin/render-examples tests/test_render_examples.py
git commit -m "bin/render-examples writes docs/examples/*.md and docs/report.svg from pinned clones

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 3: Pin the repositories, run the script, choose the featured one

**Files:**
- Modify: `bin/render-examples` (the `EXAMPLES` pins and `FEATURED`)
- Create: `docs/examples/curl.md`, `docs/examples/django.md`, `docs/examples/react.md`, `docs/examples/kubernetes.md` (kept only if the rule in Step 4 says so), `docs/report.svg`

**Interfaces:**
- Consumes: everything in Task 2.
- Produces: the committed reports and SVG; the plain-text excerpt saved to `$TMPDIR/featured.txt` for Task 4; the numbers for the README table (commits, headline finding, backtest sentence per repository), noted in the commit message body.

- [ ] **Step 1: Resolve the pins**

Run, one command per repository so a failure is attributable:

```bash
git ls-remote https://github.com/curl/curl HEAD
git ls-remote https://github.com/django/django HEAD
git ls-remote https://github.com/facebook/react HEAD
git ls-remote https://github.com/kubernetes/kubernetes HEAD
```

Expected: one line each, `<40 hex> HEAD`. If the sandbox refuses `github.com`, report the restriction and stop; the user decides.

- [ ] **Step 2: Write the pins into the script**

Replace each `"0000000000000000000000000000000000000000"` in `EXAMPLES` with the hash from Step 1 for that repository. Run `python3 -m unittest tests.test_render_examples -v`; expected: all pass.

- [ ] **Step 3: Run the script in the background and wait for it**

Check disk first: `df -h "$TMPDIR"` needs about 4 GB free (kubernetes alone is over 1 GB cloned plus its output). Then:

```bash
bin/render-examples
```

Run it with `run_in_background: true` and a `timeout` of 1800000; if it is still running when the notification arrives, that is the tool's ceiling and not a reason to stop: run it again with only the names that have not finished (`bin/render-examples kubernetes`), since finished clones and outputs are reused. Expected on stderr: the usual gitmole progress per repository, then `wrote docs/examples/curl.md` and so on, then `wrote docs/report.svg (… bytes)`. Save stdout (the plain-text excerpt) to `$TMPDIR/featured.txt`.

Order of magnitude: curl and react a few minutes each; django longer (the secrets scan walks every commit); kubernetes tens of minutes. The blame pass projects itself and skips above `--time-budget 60`; jscpd skips above 80 MB of tracked text. Both are expected on kubernetes and show as a message in the report, not a failure.

- [ ] **Step 4: Decide whether kubernetes stays**

Read its statuses:

```bash
python3 -c "import json; m=json.load(open('$TMPDIR/gitmole-examples/analysis-kubernetes/meta.json')); print(json.dumps({k: v for k, v in m.items() if k in ('steps', 'backtest', 'age', 'duplicates', 'plots')}, indent=2))"
```

If the key names differ, print `list(m)` and pick the ones that record step statuses. Keep kubernetes when the secrets scan, the change analysis, the trend and the backtest all finished (no `timeout`, no `failed`); a skipped blame pass or a skipped duplicates step is acceptable, and the report says so itself. Otherwise delete `docs/examples/kubernetes.md`, remove its row from `EXAMPLES`, and say so in the commit message. Apply the same check to the other three; a `timeout` there means rerunning that one with a higher `TIMEOUT` rather than dropping it.

- [ ] **Step 5: Choose the featured repository**

For each kept report, read the watch list caption in `docs/examples/<name>.md`, the italic line under the Watch list table that starts `6 months ago this list would have named`. The featured repository is the one whose named count beats the random expectation by the widest margin and whose findings panel is fuller than "Bus factor of one". Default is curl. If a different one wins, set `FEATURED` in `bin/render-examples` to its name and rerun `bin/render-examples <name>` (clone and output are reused, so it re-analyses in minutes) to refresh `docs/report.svg` and `$TMPDIR/featured.txt`.

- [ ] **Step 6: Read what will be committed**

Read every `docs/examples/*.md` in full with the Read tool. Check: no path from `$TMPDIR` remains; the provenance line is the third line; the secrets line reports counts and hashed values only; the tables render (pipes escaped by `_md_cell`). Open `docs/report.svg` with the Read tool and confirm it shows the three panels. Note per repository: commit count and span from the first line under the title, the first finding's title, and the backtest sentence. Those go into the README table in Task 4.

- [ ] **Step 7: Run the suite and commit**

Run: `python3 -m unittest discover -s tests -t .`
Expected: OK.

```bash
git add bin/render-examples docs/examples docs/report.svg
git commit -m "Example reports for curl, django, react and kubernetes at pinned commits; docs/report.svg

<one line per repository: commits, headline finding, backtest sentence; and why kubernetes was dropped if it was>

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 4: The README, the docs, and the end of `docs/example.md`

**Files:**
- Modify: `README.md` (top block lines 1-9; "What you get" section lines 53-95; the Docs list line 121)
- Modify: `docs/output.md:197` (the link to `example.md`)
- Modify: `docs/development.md` (Code layout paragraph, and a sentence in Releases)
- Delete: `docs/example.md`

**Interfaces:**
- Consumes: `docs/report.svg`, `docs/examples/*.md`, `$TMPDIR/featured.txt` and the per-repository numbers from Task 3.
- Produces: nothing programmatic. A link check in Step 5 is the test.

- [ ] **Step 1: Put the picture at the top of the README**

The README currently opens with the banner `<img>`, `# gitmole`, one paragraph, the tagline line, and the six principle bullets. Insert the report image after the paragraph and before the tagline, so the first thing under the name is the report:

```markdown
<img src="https://raw.githubusercontent.com/antvinni/gitmole/main/docs/banner.svg" width="912" alt="gitmole">

# gitmole

A toolkit for digging into any cloned git repository: who works on it,
where the risk is, how old the code is, whether the repo itself is healthy,
and whether anything sensitive was ever committed.

<img src="https://raw.githubusercontent.com/antvinni/gitmole/main/docs/report.svg" width="912" alt="gitmole on curl: the summary, the findings, and the watch list of files where the next bug is likely, with a backtest">

Any stack. Free. Offline. No token. No AI. Light.
```

Replace `curl` in the alt text with the featured repository if Task 3 chose another.

- [ ] **Step 2: Rewrite "What you get"**

Replace the section from `## What you get` up to (not including) `## The tool set` with the following, filling the four bracketed spots from Task 3's notes and pasting `$TMPDIR/featured.txt` verbatim into the code block:

````markdown
## What you get

The top of the report for [curl](https://github.com/curl/curl), [commits] commits
since [first year], at a pinned commit:

```text
[contents of $TMPDIR/featured.txt]
```

The watch list is the point: the five files where the next bug is most
likely, the reasons in words, and a backtest that says how the same list,
drawn six months earlier, would have done against the fixes that followed.
Below it: tables for people, the knowledge map, the timeline, hotspots with
their complexity trend, change coupling, complex functions and repo health.
Every section is explained in
[docs/output.md](https://github.com/antvinni/gitmole/blob/main/docs/output.md).

Reports on repositories you know, each at a pinned commit with a fixed
reference date so the file is reproducible:

| Repository | Commits | First finding | Backtest |
|---|---:|---|---|
| [curl](https://github.com/antvinni/gitmole/blob/main/docs/examples/curl.md) | [n] | [title] | named [x] of the [y] files fixed since; random would name [z] |
| [django](https://github.com/antvinni/gitmole/blob/main/docs/examples/django.md) | [n] | [title] | … |
| [react](https://github.com/antvinni/gitmole/blob/main/docs/examples/react.md) | [n] | [title] | … |
| [kubernetes](https://github.com/antvinni/gitmole/blob/main/docs/examples/kubernetes.md) | [n] | [title] | … |
````

Drop the kubernetes row if Task 3 dropped it. The `Backtest` cell is the caption's numbers in a short clause; keep the caption's wording for `named` and `random`. If the featured repository is not curl, swap the name and link in the first sentence too.

- [ ] **Step 3: Repoint every link to `docs/example.md`, then delete it**

- `README.md` Docs list: replace the line `- [Full example report](https://github.com/antvinni/gitmole/blob/main/docs/example.md): the whole `gitmole .` output for this repository.` with `- [Example reports](https://github.com/antvinni/gitmole/tree/main/docs/examples): curl, django, react and kubernetes at pinned commits, regenerated by `bin/render-examples`.` (drop kubernetes from the list if it was dropped).
- `docs/output.md:197`: replace the `example.md` link with `[docs/examples/curl.md](https://github.com/antvinni/gitmole/blob/main/docs/examples/curl.md)` and adjust the sentence around it so it reads as a full example rather than "the whole output for this repository". Read the two lines above it first.
- Delete the file: `git rm docs/example.md`.
- Confirm nothing else points at it: `grep -rn "example.md" README.md docs CONTRIBUTING.md gitmole tests Formula`. Expected: no output.

- [ ] **Step 4: Document the script**

In `docs/development.md`, Code layout paragraph, after the sentence about `bin/render-banner`, add:

```markdown
`bin/render-examples` clones the repositories listed in the script under
`$TMPDIR/gitmole-examples/`, pins each to its recorded commit, runs gitmole
with the recorded reference date and writes `docs/examples/<repo>.md` and,
for the featured one, `docs/report.svg` plus the README's text block on
stdout. Clones and outputs are reused on a rerun; delete the directory to
start clean.
```

In the Releases section, after the paragraph about the formula, add:

```markdown
The example reports name the gitmole version that made them. When a release
changes the report, run `bin/render-examples` and commit the new
`docs/examples/*.md`, `docs/report.svg` and README text block together.
Bumping a pin is a separate decision: it changes the repository's history,
not gitmole's output.
```

- [ ] **Step 5: Check every link and the render**

- Links to files in this repository: for each `docs/…` path in `README.md`, `docs/output.md` and `docs/development.md`, confirm the file exists:

```bash
grep -oh "antvinni/gitmole/blob/main/[^)\" ]*" README.md docs/*.md | sed 's|antvinni/gitmole/blob/main/||' | sort -u | while read -r f; do [ -e "$f" ] || echo "missing: $f"; done
```

Expected: no output.
- Read `README.md` top to bottom once with the Read tool: the picture sits under the description, the text block matches the picture (same repository, same panels), the table has one row per committed example, no sentence still says "this repository" about the example.
- `python3 -m unittest discover -s tests -t .` expected OK (the packaging test reads the README through `pyproject.toml`).

- [ ] **Step 6: Commit**

```bash
git add README.md docs/output.md docs/development.md
git commit -m "README opens with the curl report; example reports replace the self-report

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

(`git rm docs/example.md` from Step 3 is already staged.)

---

## Self-review notes

- Feedback (3), a visual at the top: Task 1 and Task 2 produce it, Task 4 Step 1 places it.
- Feedback (4), reports on known repositories with a backtest: Task 2 builds the pipeline, Task 3 runs and commits it, Task 4 Step 2 gives it the README table and the "here is where the next bug is likely, with a backtest" framing.
- Names used across tasks: `render.excerpt` (Task 1) is what `bin/render-examples`'s `excerpt()` calls (Task 2); `EXAMPLES`, `FEATURED`, `NOW`, `TIMEOUT`, `WIDTH`, `document()`, `checkout()`, `analyse()`, `main()` are the same in the script and its tests.
- Out of scope, on purpose: a vhs GIF, a `docs/examples/README.md` index, CI regeneration of the examples (it needs multi-gigabyte clones), a version bump (docs and a three-line render helper; the user decides whether the next release carries it).

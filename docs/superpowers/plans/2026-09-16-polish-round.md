# Polish Round Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Six independent improvements, one PR each: the package passes its own complexity finding and clears its deferred review findings; the default tables show source files first; `--risk-threshold` gates CI; releases publish to PyPI; `bin/install.sh` is retired; the README drops under 400 lines.

**Architecture:** Refactors keep every public function's signature and behaviour (pinned by the 434-test suite and the golden report); table changes are confined to `render.py`'s section builders; the gate is a few lines in `cli.py`; PyPI is one workflow job; the rest is files moving.

**Tech Stack:** Python 3.9 stdlib, rich, lizard; unittest; GitHub Actions; `pypa/gh-action-pypi-publish`.

**Spec:** `docs/superpowers/specs/2026-09-16-polish-round-design.md`

## Global Constraints

- No new runtime dependency. `pyproject.toml` `dependencies` stays `["rich>=13", "lizard>=1.24"]`.
- `python3 -m unittest discover -s tests -t .` prints OK before every commit; `python3 -W error::ResourceWarning -m unittest discover -s tests -t .` too (the suite is warning-clean and must stay so).
- The golden report `tests/golden/report.txt` does not change in any task.
- Every commit message: subject, blank line, `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`.
- One branch and PR per part, from main, merged when the checks (`tests` ×2, `homebrew formula`) pass.
- `filetypes.is_test_path(path)` is the only definition of a test file.

## Facts the executor needs

- `gitmole .` on this checkout prints the Complex functions table; `python3 -m gitmole . --out $TMPDIR/self --json - | python3 -c 'import json,sys; [print(f["ccn"], f["file"], f["function"]) for f in sorted(json.load(sys.stdin)["functions"], key=lambda f: -f["ccn"])[:12]]'` lists the twelve most complex functions with their ccn.
- `cli._analyse(repo_dir, out_dir, args, ui, planner, estimator)` runs one repository: budgets (blame time, plots), `meta` assembly (file types, gone window, age/plots/functions/trend/backtest status records, the backtest cut-off and skip rule), `clear_outputs`, plan, execute, status recording, the failed-steps notice. Tests in `tests/test_cli.py` drive it through `cli.main` with stub planners and estimators.
- `findings.knowledge_loss(report)` computes who is gone, the lost share (blame or lines-added fallback), the named-people clause, the areas clause with liveness, and the advice. Tests: `tests/test_findings.py::KnowledgeLoss`.
- `render.hotspots_section`, `functions_section`, `coupling_section` build rows then call `_keep` for the default columns and `_shorten` for paths; captions are joined with `_more(total, limit)`.
- `cli._render` computes `risk = {"base": ..., **watch.change_risk(report, files)}` and returns 3 for `--fail-on`; `risk["total"]` is the number to gate on.
- The release job in `.github/workflows/ci.yml` builds `dist/` and creates the release, then bumps the formula; jobs declare `permissions` explicitly.
- Deferred findings from the history-insights reviews (ledger copy at `/tmp/claude-501/history-insights-ledger.md`, one line each, prefixed `minor (deferred)`).

---

# Part 1: Own complexity and deferred findings (PR 1)

### Task 1.1: Split `cli._analyse`

**Files:**
- Modify: `gitmole/cli.py`
- Test: `tests/test_cli.py` (existing tests pin behaviour; no new tests unless a helper gets a signature worth a direct test)

**Interfaces:**
- Produces, in `cli.py`: `_budgets(args, estimate, ui) -> tuple[bool, bool]` (age_ok, plots_ok, printing the two skip notices), `_meta_for_run(repo_dir, args, estimate, age_ok, plots_ok) -> tuple[dict, str | None]` (meta with every status record, and the backtest cut-off or None; raises `NoCommits`), `_record_statuses(meta, results, age_ok, plots_ok, lizard_ok, cut) -> None`. `_analyse` becomes the sequence: budgets, meta, clear, plan, execute, cancel check, statuses, save, notice.

- [ ] **Step 1: Measure before**

Run the twelve-most-complex command from the facts; note `_analyse`'s ccn (35 at the time of writing) and the full-suite baseline (`OK`, 434 tests).

- [ ] **Step 2: Extract the three helpers**

Move the code, do not rewrite it. `_budgets` takes lines from `ignore = ...` through the two `ui.print` notices and returns `(age_ok, plots_ok)`; `_meta_for_run` takes from `meta = run.collect_meta(...)` through the backtest skip rule and returns `(meta, cut)`; `_record_statuses` takes the `status()` closure and the five `if` blocks. Keep every string identical (tests match on them).

- [ ] **Step 3: Verify**

```bash
python3 -m unittest discover -s tests -t .
python3 -m gitmole . --out $TMPDIR/self --json - | python3 -c 'import json,sys; print([ (f["ccn"], f["function"]) for f in json.load(sys.stdin)["functions"] if f["file"]=="gitmole/cli.py" and f["ccn"]>=15])'
```

Expected: OK, 434 tests; no function in `cli.py` at or above 20, and `_analyse` under 15 (`main` may stay at its current 28 only if splitting it would be argument-handling churn; if it is above 20, extract `_no_run(args, console, ui, err)` for the `--no-run` block and `_resolve_target(args, ...)` for the remote/org branches, which brings it under 20).

- [ ] **Step 4: Commit**

`git commit` with subject `cli: _analyse split into budgets, meta and status recording`.

### Task 1.2: Split `findings.knowledge_loss`

**Files:**
- Modify: `gitmole/findings.py`
- Test: `tests/test_findings.py::KnowledgeLoss` (existing) plus the two deferred-coverage tests below.

**Interfaces:**
- Produces: `_loss_totals(report, names) -> tuple[int, int, dict, str]` (lost, total, by_person, basis: blame or the lines-added fallback), `_loss_people(by_person, total) -> str` (the "Bob (25%), Cat (2%) and 3 others (1%)" or "N people at under 1% each" clause), `_loss_areas(report, names) -> list` (areas at 200+ lines and 80%+ lost, liveness set, sorted live-first). `knowledge_loss` then reads as: gone → totals → threshold → people clause → areas → statement and advice.

- [ ] **Step 1: Pin the untested branch before refactoring**

Add to `tests/test_findings.py::KnowledgeLoss`: `test_everyone_under_one_percent_is_counted_not_named`: twelve gone people at 8 lines each of a 1,000-line surviving total, plus one active author with the rest; the statement contains `12 people at under 1% each`. It passes on the current code; its job is to guard the split.

- [ ] **Step 2: Extract the helpers**

Move code without changing strings. Keep `_is_live` as is.

- [ ] **Step 3: Verify**

Suite OK; `knowledge_loss` under 15 by the JSON check (file `gitmole/findings.py`).

- [ ] **Step 4: Commit** — `findings: knowledge_loss split into totals, people and areas`.

### Task 1.3: Deferred findings

**Files:** as listed per item.

Take these (each a small change with a test where behaviour changes); skip the ones marked done or unreachable.

- [ ] `maat.activity`: fold the reverts loop into the existing per-file pass (1.1). Test: existing `Reverts` tests.
- [ ] `findings.reverts`: when `meta["commits"]` is 0 the rule returns `[]`; test it (1.2).
- [ ] `tests/test_render.py::Report`: the plural plain count: with `activity["by_weekday"] = [1000, 0, 0, 0, 0, 0, 0]` and `revert_commits = 2`, the header says `2 reverts` (1.3).
- [ ] `findings.knowledge_loss` areas clause: `and N more` after three areas (2.4). Test with four qualifying areas.
- [ ] `render.knowledge_section`: use `a["lost_share"]` instead of recomputing (2.5). No behaviour change; suite pins it.
- [ ] `cli._render`: thread `err` from `main` instead of rebuilding the stderr console inline (3.3). Suite pins it.
- [ ] `watch.change_risk`: the reason `changed once` only when the file's revision count is 1; a file in the tree with a watch row absent for another reason says `not scored` (3.2). Test: a file in `size.files` with `n-revs` 0 in the window.
- [ ] `load.load_report`: a malformed `trend.json` or `activity.json` gives the empty value instead of raising (4.3). Test: write `{` to each and load.
- [ ] `tests/test_trend.py`: rename `test_evenly_spread_and_at_most_one_per_month` to `test_evenly_spread_across_the_span` (4.2).
- [ ] `tests/test_backtest.py`: a test for the missing-inputs exit 2 (5.2).
- [ ] `tests/test_run.py`: a non-ASCII path through `changed_files` (3.1), building the file name from bytes as `tests/test_filetypes.py` does.
- [ ] `tests/test_cli.py`: `--risk` on a portfolio target (`owner/*`) exits 2 with the message (3.3).
- [ ] `tests/test_maat.py`: `months_before` over 13 and 24 months (2.1).
- [ ] Skip, with a line in the PR body saying why: 2.2 (unreachable guard, harmless), 2.3 and 4.1 and 5.3 (already fixed in the final fix wave), 2.5 double parentheses (plan-specified wording, cosmetic), 4.2 symlink case (not a real case), 4.3 dependency-skip wording (shared with git-of-theseus, predates), 1.3 and 4.4 README wraps (the README is rewritten in Part 6).

- [ ] **Commit** per two or three items, then push, open PR 1 (`Own complexity and the deferred review findings`), merge when green.

# Part 2: Source files first (PR 2)

### Task 2.1: Hotspots and Complex functions hide test files by default

**Files:**
- Modify: `gitmole/render.py` (`hotspots_section`, `functions_section`)
- Test: `tests/test_render.py`

- [ ] **Step 1: Failing tests**

In `Report`: `test_default_hotspots_hide_test_files_and_say_so`: add `"tests/test_a.py"` to `sample_report()`'s size files and revisions (revs 200 so it would rank first); `rendered(r, [])` does not contain `tests/test_a.py` in the Hotspots section, its caption contains `1 test file hidden; --full shows them`; `rendered(r, [], full=True)` contains it. Same shape for `functions_section` with a `tests/test_a.py` function at ccn 40: `test_default_complex_functions_hide_test_files`.

- [ ] **Step 2: Implement**

In both builders, when `full is not True`, filter rows whose path is a test file before applying the limit, count the hidden ones, and add `f"{n} test file{'s' if n != 1 else ''} hidden; --full shows them"` to the caption (joined with `; ` to `_more`). The `and N more` count is over the visible rows.

- [ ] **Step 3: Suite, commit** — `Hotspots and Complex functions: source files by default`.

### Task 2.2: Coupling hides test pairs by default

**Files:**
- Modify: `gitmole/render.py` (`coupling_section`)
- Test: `tests/test_render.py`

- [ ] Failing test: `sample_report()`'s coupling gets a pair `("static/tax.html", "tests/test_tax.py", 100%)`; the default table does not list it and the caption says `1 test pair hidden; --full shows them`; `--full` lists it.
- [ ] Implement: in the default view, drop pairs where either side is a test path, count, caption as above.
- [ ] Suite, commit — `Change coupling: pairs with a test file are --full only`.

### Task 2.3: README and PR

- [ ] README "The terminal report" item 4: one sentence that the default tables show source files, that test rows and file-plus-test pairs are under `--full`, and that the caption counts them.
- [ ] Manual check on mealie: the Hotspots table no longer shows the two integration-test files in its top rows; the coupling table's first row is the Dockerfile pair or another source pair.
- [ ] Push, open PR 2 (`Tables show source files by default`), merge when green.

# Part 3: `--risk-threshold` (PR 3)

### Task 3.1: The gate

**Files:**
- Modify: `gitmole/cli.py`
- Test: `tests/test_cli.py::Risk`

- [ ] **Step 1: Failing tests**

`test_threshold_exits_3_when_the_total_is_over_it`: with the `Risk` class's repository and stub planner, the one touched file scores 0 (it is a `new file` to the stub run), so the total is 0. `--risk main --risk-threshold -1` must exit 3 (0 exceeds -1) and `--risk-threshold 0` must exit 0 (0 does not exceed 0); in both cases the Change risk section is in the output. `test_threshold_needs_risk`: `--risk-threshold 1` without `--risk` exits 2 with `--risk-threshold needs --risk`.

- [ ] **Step 2: Implement**

`parse_args`: `p.add_argument("--risk-threshold", type=float, metavar="N", help="with --risk: exit 3 when the change-risk total exceeds N")`. In `main`, after the `--risk needs a local path` check: `if args.risk_threshold is not None and not args.risk: err.print(...); return 2`. In `_render`, after the `--fail-on` check: `if risk is not None and args.risk_threshold is not None and risk["total"] > args.risk_threshold: return 3`.

- [ ] **Step 3: README**

Exports and CI: add `gitmole . --risk main --risk-threshold 5` to the block with one sentence: "exit 3 when the files changed since main add up to more than 5 on the watch-list scale; the total prints in the Change risk caption".

- [ ] Suite, commit (`--risk-threshold: exit 3 over the change-risk total`), PR 3, merge.

# Part 4: PyPI (PR 4)

### Task 4.1: The publish job

**Files:**
- Modify: `.github/workflows/ci.yml`

- [ ] **Step 1: Add the job**

After `release`:

```yaml
  publish:
    name: publish to PyPI
    if: startsWith(github.ref, 'refs/tags/v')
    needs: release
    runs-on: ubuntu-latest
    environment: pypi
    permissions:
      id-token: write
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - name: Build the sdist and wheel
        run: |
          python -m pip install build
          python -m build
      - uses: pypa/gh-action-pypi-publish@release/v1
```

(Rebuilding is simpler than passing artefacts between jobs and produces identical files from the same tag.)

- [ ] **Step 2: The owner's step, before the next tag**

On PyPI, logged in as the owner: Account settings → Publishing → add a pending publisher: project `gitmole`, owner `antvinni`, repository `gitmole`, workflow `ci.yml`, environment `pypi`. On GitHub: Settings → Environments → create `pypi` (no protection rules needed). Record in the PR body that this must exist before the first tag that publishes; the release and formula bump still succeed if it does not, only the `publish` job fails.

- [ ] **Step 3: README**

Install: the macOS "without Homebrew" and the Linux pipx lines become `pipx install gitmole`; the pinned form `pipx install gitmole==X.Y.Z`; the git-URL form stays for main. Releases paragraph: "the tag also publishes to PyPI".

- [ ] Suite (unchanged), commit (`Publish releases to PyPI by trusted publishing`), PR 4, merge. The first tag after the owner's step proves it.

# Part 5: Retire `bin/install.sh` (PR 5)

- [ ] `git rm bin/install.sh`.
- [ ] README Development: replace the paragraph about the script with the developer setup: `brew install scc git-sizer gitleaks`; either `python3 -m venv .venv && . .venv/bin/activate && pip install -e .`, or the checkout style `python3 -m pip install --user rich lizard` plus `ln -sfn "$PWD/bin/gitmole" "$(brew --prefix)/bin/gitmole"`. Remove the "On macOS, `./bin/install.sh`..." paragraph from Install and the License sentence that mentions the script.
- [ ] `grep -rn install.sh .` finds nothing outside git history. Suite OK (nothing referenced it). Commit (`Retire bin/install.sh; the developer setup is three commands`), PR 5, merge.

# Part 6: A shorter README (PR 6)

- [ ] Create `docs/tools.md` with "The tool set" prose (keep the table in the README) and "Considered and left out"; the README's "The tool set" section becomes the table plus "Why these and not others: docs/tools.md".
- [ ] Create `docs/output.md` with "The output directory" and "How to read the output"; the README's "The terminal report" section ends with a link to it.
- [ ] Check every relative link resolves (`grep -o '](docs/[^)]*)' README.md` and `ls` each), that no section is duplicated, and that `wc -l README.md` is under 400.
- [ ] Commit (`README under 400 lines; tool rationale and output reference move to docs/`), PR 6, merge.

---

## Self-review notes

- Spec coverage: §1 → Tasks 1.1–1.3; §2 → 2.1–2.3; §3 → 3.1; §4 → 4.1; §5 → Part 5; §6 → Part 6.
- Nothing here changes the golden report: the golden repository has no test files and no `--risk`.
- Part 4's first real run depends on the owner creating the PyPI pending publisher and the GitHub environment; the plan says so and the release stays safe without it.

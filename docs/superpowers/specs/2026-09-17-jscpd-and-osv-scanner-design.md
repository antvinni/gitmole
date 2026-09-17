# jscpd for duplicates, osv-scanner for dependencies

Date: 2026-09-17. Version 0.7.0.

## Why

Two gaps in the tool set, found by surveying established tools against the
bar in CONTRIBUTING (one question nothing in the set answers; free; offline;
one binary or a pip package; the answer changes what you do next):

- lizard's duplicate finder kept a hash node per token and grew to 1.5 to
  2 GB per worker on a large repository, so duplicates were opt-in behind
  `--duplicates` and capped at two workers. jscpd 5 (Rust, September 2026,
  MIT, brew formula with no dependencies, a PyPI wheel of the same binary)
  does the same job in seconds.
- nothing answered "does this repository depend on anything with a known
  vulnerability". osv-scanner (Go, Apache-2.0, brew formula with no
  dependencies) reads every lock file and, with `--offline`, matches them
  against a local copy of the OSV database without sending anything.

Measured on this machine: jscpd took 0.03 s on gitmole, 0.55 s on mealie
(1,400 files, 34 MB of tracked text, 0.9 GB peak memory) and 6.5 s on a
40,000-file tree of generated SQL (171 MB, 4 GB peak). About a gigabyte per
25 MB of tracked text.

## Design

**Duplicates step** (`gitmole/duplicates.py`, a standalone script like
`leaks.py`): runs `jscpd --reporters json` in the clone with `.git/**` and
the run's `--ignore` globs excluded, reads the report from a temporary
directory under the output directory, keeps the pairs whose two sides are
both tracked code files (the built-in source list, or `--file-types`),
folds the pairs of one fragment (hashed) into a block with every place it
appears, measures the share of the kept files' lines inside a block, drops
the fragment text, and writes `duplicates.json` (the thousand largest
blocks). The raw report is removed before the step returns. Data files are
out on purpose: on mealie the largest "duplicate" was a 16,000-line locale
file copied per language.

Runs by default. Skipped above `DUPLICATES_BUDGET_MB` (80) of tracked text,
measured by `estimate_blames`, with a notice that says how much memory it
would take; `--deep` forces it. `--duplicates` is kept as a hidden no-op so
older CI lines still parse. lizard keeps the function metrics; its
duplicate extension and the two-worker cap are gone.

**Dependencies step** (`gitmole/deps.py`): runs
`osv-scanner scan source -r --offline --format json --all-packages .` in
the clone and writes `dependencies.json`: one row per vulnerable package
(ids, CVE aliases, worst score from the groups' `max_severity`, the
smallest fixed version above the installed one), the lock files with their
package counts, and the date of the newest file under osv-scanner's cache
directory. Exit 128 becomes `{"status": "no-sources"}`; the "no offline
version of the OSV database" message becomes `{"status": "no-database"}`
with the download command; any other failure writes nothing and fails the
step. gitmole never downloads the database.

**Finding** `vulnerable_dependencies`: a package pinned by a lock file in
the source tree is a warning, critical when its score is 9.0 or more; one
pinned only by a lock file under tests, examples, docs or vendored code is
a note. The advice names the package, the fixed version and the lock file,
and `osv-scanner.toml` as the repository's own ignore mechanism.

**Report**: a green `No known vulnerabilities in dependencies` pass line
next to the secrets one (`checks_passed`), and a footer line: packages and
lock files checked with the database date, or `no lock files found`, or the
download command. An output directory from before the step prints nothing.

**Wiring**: `REQUIRED_TOOLS` gains `jscpd` and `osv-scanner`; the formula,
CI and the install docs follow. The golden test's synthetic repository has
no lock files, so its report is deterministic with or without a database.

## Left out

grype and trivy (larger database, less explicit offline contract), PMD CPD
(Java, slower), rust-code-analysis (no release since 2021), askalono
(archived May 2026), licensee (Ruby gem), OpenSSF Scorecard local mode
(file-presence checks only), semgrep (dependencies and registry rulesets),
enry (gitmole's conventions already cover linguist's lists).

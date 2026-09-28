# Why these tools

Why gitmole includes each tool in the tool set, and the ones it left out; back to [the README](https://github.com/antvinni/gitmole#readme).

One tool per question. Together they cover most of what a single-command
analysis can tell you about a repo.

Three external tools: scc for size, betterleaks for secrets, osv-scanner for
known vulnerabilities in the dependencies. betterleaks reads HEAD's history
only, not every reference the clone happens to carry, so two clones of one
commit report the same secrets; what no reference reaches is scanned
separately and recorded as the clone's. Each is pinned to one version, listed in
[gitmole/tools.py](https://github.com/antvinni/gitmole/blob/main/gitmole/tools.py)
and installed with gitmole by the Homebrew formula, because their own rules
decide part of the report: a tool that moved on its own would move the report
under an unchanged gitmole version. A run with other versions still works and
says so; `meta.json` records both. Everything about history is computed by gitmole from `git log`.
lizard, a pinned python dependency installed with gitmole, adds
function-level metrics for two dozen languages in well under a second per
thousand files. git-of-theseus only adds
the plots, so it is off by default and only needed with `--plots`. betterleaks
should never be skipped on a repo you did not author.

**osv-scanner** answers "does this repository depend on anything with a known
vulnerability", from the lock files (package-lock.json, yarn.lock, uv.lock,
poetry.lock, go.sum, Cargo.lock, Gemfile.lock and the rest) against a copy of
the [OSV](https://osv.dev) database on this machine. gitmole runs it with
`--offline`, so nothing leaves the machine; the copy is downloaded once by
you, never by gitmole, with the command the report footer prints, and refreshed
the same way when you want newer advisories. A repository without lock files
gets a footer line saying so, and a missing database is reported, not
downloaded. To silence an advisory that does not apply to your code, add its
id to `osv-scanner.toml` at the repository root, osv-scanner's own ignore file.

**tree-sitter**, installed with gitmole and pinned like the other tools, answers "how is the
code shaped, and what imports what": nesting, compound conditions,
cognitive complexity, the TODO and FIXME markers the authors left, the
import graph that says which co-changing files have no import between them,
and three shape rules (errors caught and dropped, addresses in literals, code
left in comments) that ast-grep would otherwise have needed a second wheel for.
It is py-tree-sitter with one grammar wheel per language (Python,
JavaScript, TypeScript, Go, Rust, Java, C, C++, Ruby, C#, PHP), each a
compiled grammar inside an MIT wheel: nothing to compile, nothing fetched at
run time. tree-sitter-language-pack, which covers 371 languages, was the
first choice and was left out because it downloads its grammars when first
used, which breaks the offline rule.

What gitmole does not do: dead-code detection (the import graph can say
"possibly unreferenced" for Python, JavaScript, TypeScript and Go, never
"dead"; the real thing needs a symbol graph per language) and test coverage
(that needs the project's own test run). It will not guess at either.

## Retired

- **jscpd** and **git-sizer**, at 0.39.0 (September 2026). Each fed one rule,
  `duplication` and `repo_health`, and both rules were among the nine whose
  findings were checked and found true but never something a reader acted on:
  five or more labelled findings each, none labelled actionable
  ([measurement.md](measurement.md), "Hand labels"). Until then the default
  report named them in one line and spelled them out only under `--full`; the
  steps still ran on every repository and cost wall time and memory for it.
  jscpd held about a gigabyte per 25 MB of tracked text (on apache/devlake it
  was the second-largest memory user, 856 MB), and git-sizer was the one tool
  with no Linux arm64 build upstream. The maintainer chose to remove the nine
  rules rather than keep paying for them, and the two tools went with the
  rules they fed. The committed-binaries check (hygiene) still names the
  executables in the tree and the files .gitattributes sends to LFS that were
  committed as blobs.
- **lizard's duplicate finder**, before that: replaced by jscpd at 0.7.0. It
  kept a hash node per token and every worker grew to 1.5 to 2 GB on a large
  repository. lizard still measures the functions.

## Considered and left out

- **PMD CPD**: another established duplicate finder; needs Java and was thirty
  times slower than jscpd on the same corpus.
- **grype**, **trivy**: answer the same question as osv-scanner from lock files.
  Both need a larger database download, and osv-scanner's offline contract is
  the one its documentation states outright: no project or dependency
  information leaves the machine.
- **hercules**: overlaps the change analysis and git-of-theseus, and the project is
  archived. Add it only if you want its burndown charts specifically.
- **tokei**: duplicates scc without the effort estimate.
- **git-extras**, **onefetch**, **git-quick-stats**: convenient summaries, but
  everything they report is now computed from the log by gitmole itself, so
  they were dropped to shrink the install.
- **GrimoireLab**: a community-analytics platform (Elasticsearch, Kibana,
  scheduled collectors across GitHub, mailing lists, chat). Not a
  point-at-a-clone tool, and it does not cover code age, hotspots, size or
  secrets.
- **gitleaks**: replaced by betterleaks in September 2026. betterleaks is the
  successor written by the same author, takes the same flags, reads the same
  config and `.gitleaksignore`, and its detector catches more than the
  entropy check gitleaks relies on. gitmole strips its extra per-finding
  attributes, which repeat the commit message, the same way it strips the
  message itself.
- **trufflehog**: duplicates betterleaks for this purpose. betterleaks is
  lighter and faster on history.
- **GitLens**: useful in the editor, but it has telemetry and paid tiers.
- **askalono**, **licensee**, **trivy's licence scanner**: licence detection.
  askalono was archived in May 2026, licensee is a Ruby gem, and trivy is the
  heaviest tool here. gitmole reads what is declared instead: the manifests,
  the lock files' licence fields, and the licence file against the opening
  words of a small set of texts.
- **syft**, **cdxgen**: SBOM generators. osv-scanner already reads every
  lock file, so `--sbom` writes CycloneDX from its package list.
- **OpenSSF Scorecard** in local mode: only its file-presence checks run without
  the GitHub API. **semgrep**: a dozen dependencies and rulesets fetched from a
  registry. **enry**: linguist's vendored and generated lists, which gitmole's
  own conventions cover.

## Licences

gitmole does not bundle any of the tools it wraps; it runs them as separate
processes. gitmole itself is MIT.

| Tool | Licence |
|---|---|
| scc | MIT |
| betterleaks | MIT |
| osv-scanner | Apache-2.0 |
| rich | MIT |
| lizard | MIT |
| git-of-theseus | Apache-2.0 |
| py-tree-sitter and the tree-sitter grammars | MIT |

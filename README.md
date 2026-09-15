# gitmole

A local, offline toolkit for digging into any cloned git repository: who
works on it, where the risk is, how old the code is, whether the repo itself
is healthy, and whether anything sensitive was ever committed.

Everything runs against a clone on your machine. No tool here needs a GitHub
token, uploads data, or phones home.

## The tool set

One tool per question. Together they cover most of what a single-command
analysis can tell you about a repo.

| Question | Tool | Install |
|---|---|---|
| What is this repo, at a glance | [onefetch](https://github.com/o2sh/onefetch) | brew |
| Who commits, when, how much churn | [git-quick-stats](https://github.com/git-quick-stats/git-quick-stats) | brew |
| How big is the codebase, per language | [scc](https://github.com/boyter/scc) | brew |
| Is the repo itself healthy (huge blobs, deep trees) | [git-sizer](https://github.com/github/git-sizer) | brew |
| Where is the risk: hotspots, coupling, ownership | [code-maat](https://github.com/adamtornhill/code-maat) | jar, needs Java |
| How old is the surviving code, per year and author | [git-of-theseus](https://github.com/erikbern/git-of-theseus) | pip |
| Have secrets ever been committed | [gitleaks](https://github.com/gitleaks/gitleaks) | brew |
| Anything custom the above don't answer | [PyDriller](https://github.com/ishepard/pydriller) | pip |

The first four give a full picture in under a minute. code-maat and
git-of-theseus produce the genuinely non-obvious insight, so they are worth
the extra setup. gitleaks should never be skipped on a repo you did not
author. PyDriller is optional and only matters if you want to script your own
metrics.

### Considered and left out

- **hercules**: overlaps code-maat and git-of-theseus, and the project is
  archived. Add it only if you want its burndown charts specifically.
- **tokei**: duplicates scc without the effort estimate.
- **git-extras**: convenient, but everything it reports is covered above.
- **GrimoireLab**: a community-analytics platform (Elasticsearch, Kibana,
  scheduled collectors across GitHub, mailing lists, chat). Not a
  point-at-a-clone tool, and it does not cover code age, hotspots, size,
  repo health, or secrets.
- **trufflehog**: duplicates gitleaks for this purpose. gitleaks is lighter
  and faster on history.
- **GitLens**: useful in the editor, but it has telemetry and paid tiers.

## Install

Requires Homebrew and Python 3. OpenJDK is installed via brew for code-maat.

```bash
./bin/install.sh
```

That runs, roughly:

```bash
brew install onefetch git-quick-stats scc git-sizer gitleaks openjdk
python3 -m pip install --user git-of-theseus pydriller
curl -L -o ~/bin/code-maat.jar \
  https://github.com/adamtornhill/code-maat/releases/download/v1.0.4/code-maat-1.0.4-standalone.jar
```

The jar version is pinned in `bin/install.sh`. Check the
[code-maat releases](https://github.com/adamtornhill/code-maat/releases)
page before bumping it.

## Run

```bash
./bin/analyse.sh /path/to/clone
```

Output lands in `analysis-<repo-name>/` next to the clone:

| File | From | What it is |
|---|---|---|
| `overview.txt` | onefetch | languages, authors, age, size |
| `contributors.txt` | git-quick-stats | commits per author, activity by hour and weekday |
| `size.json` | scc | lines per language, COCOMO estimate |
| `repo-health.txt` | git-sizer | oversized objects, deep trees, other repo problems |
| `secrets.json` | gitleaks | any secret-looking strings across all history |
| `log.txt` | git | the log export code-maat reads |
| `maat-revisions.csv` | code-maat | change frequency per file |
| `maat-coupling.csv` | code-maat | files that change together |
| `maat-authors.csv` | code-maat | authors per file |
| `maat-age.csv` | code-maat | months since last change per file |
| `maat-entity-ownership.csv` | code-maat | lines added and deleted per author per file |
| `theseus/` | git-of-theseus | raw cohort and survival data |
| `code-age.png` | git-of-theseus | stacked plot of surviving code by year |
| `survival.png` | git-of-theseus | how long a line of code tends to live |

## How to read the output

1. Start with `overview.txt` and `contributors.txt` for orientation.
2. Sort `maat-revisions.csv` by count and join it with line counts from
   `size.json`. Large files that change constantly are your hotspots.
3. `maat-coupling.csv` shows files that always change together. That usually
   means a hidden dependency.
4. `maat-entity-ownership.csv` and the git-of-theseus plots tell you whether
   knowledge is concentrated in one or two people.
5. `repo-health.txt` and `secrets.json` are pass or fail checks. Read them
   only if they flag something.

## Safety notes

- Everything here is offline. gitleaks and git-of-theseus never send data
  anywhere.
- Run against a fresh clone in a scratch directory. code-maat and
  git-of-theseus only read, but the log export and the gitleaks scan touch all
  branches, so a throwaway clone keeps things clean.
- Install from the official repos or Homebrew with pinned versions, not from
  forks.

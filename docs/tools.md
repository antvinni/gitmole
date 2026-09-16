# Why these tools

Why gitmole includes each tool in the tool set, and the ones it left out; back to [../README.md](../README.md).

One tool per question. Together they cover most of what a single-command
analysis can tell you about a repo.

Three external tools: scc for size, git-sizer for repo health, gitleaks for
secrets. Everything about history is computed by gitmole from `git log`.
lizard adds function-level metrics for two dozen languages when it is
installed, in well under a second per thousand files; its duplicate finder
is minutes and gigabytes on a large repo, so it is off unless you pass
`--duplicates`. git-of-theseus only adds the plots, so it is off by default
and only needed with `--plots`. gitleaks should never be skipped on a repo you did
not author.

What gitmole does not do: dead-code detection (that needs a symbol graph per
language) and test coverage (that needs the project's own test run). It will
not guess at either.

## Considered and left out

- **hercules**: overlaps the change analysis and git-of-theseus, and the project is
  archived. Add it only if you want its burndown charts specifically.
- **tokei**: duplicates scc without the effort estimate.
- **git-extras**, **onefetch**, **git-quick-stats**: convenient summaries, but
  everything they report is now computed from the log by gitmole itself, so
  they were dropped to shrink the install.
- **GrimoireLab**: a community-analytics platform (Elasticsearch, Kibana,
  scheduled collectors across GitHub, mailing lists, chat). Not a
  point-at-a-clone tool, and it does not cover code age, hotspots, size,
  repo health, or secrets.
- **trufflehog**: duplicates gitleaks for this purpose. gitleaks is lighter
  and faster on history.
- **GitLens**: useful in the editor, but it has telemetry and paid tiers.

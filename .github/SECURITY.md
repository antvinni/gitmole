# Security policy

## Reporting a vulnerability

Do not open a public issue. Use
[private vulnerability reporting](https://github.com/antvinni/gitmole/security/advisories/new),
which reaches the maintainer, [@antvinni](https://github.com/antvinni), and
nobody else.

Include:

- the gitmole version (`gitmole --version`) and your OS;
- what an attacker controls and what they gain;
- steps to reproduce, ideally a small repository that triggers it.

Never paste a real secret. If the problem involves a secret value, describe
its shape instead.

## What counts

gitmole reads repositories it did not write and hands their bytes to scc,
git-sizer, betterleaks, jscpd, osv-scanner and the tree-sitter grammars.
Anything that goes wrong on that path is in scope, for example:

- a secret value reaching the output directory, the terminal or an export;
- a repository's contents causing a command to run, or a file to be written
  outside the output directory;
- a scan reaching the network when it should not (betterleaks runs with
  `--validation=false`, osv-scanner with `--offline`).

A vulnerability in one of those tools is best reported to its own project.
Tell us as well if gitmole's use of it makes it exploitable.

## Supported versions

Fixes go into the latest release only.

| Version | Supported |
|---|---|
| Latest release | ✅ |
| Older releases | ❌ |

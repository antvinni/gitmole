#!/usr/bin/env bash
# Install the gitmole tool set on macOS and link the gitmole command. Requires Homebrew and Python 3.
set -euo pipefail

brew install scc git-sizer gitleaks

python3 -m pip install --user rich lizard
# git-of-theseus is only needed for --plots: python3 -m pip install --user git-of-theseus

# Put the gitmole command on PATH next to the brew tools.
ln -sfn "$(cd "$(dirname "$0")" && pwd)/gitmole" "$(brew --prefix)/bin/gitmole"

echo
echo "Installed. Try:  gitmole ."
echo "Verify tools with:"
echo "  scc --version; git-sizer --version; gitleaks version"
echo "  git-of-theseus-analyze --help"

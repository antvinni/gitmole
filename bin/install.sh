#!/usr/bin/env bash
# Install the gitmole tool set on macOS. Requires Homebrew and Python 3.
set -euo pipefail

CODE_MAAT_VERSION="1.0.4"
JAR_DIR="${HOME}/bin"

# openjdk is keg-only; analyse.sh adds /opt/homebrew/opt/openjdk/bin to PATH itself.
brew install onefetch git-quick-stats scc git-sizer gitleaks openjdk

python3 -m pip install --user git-of-theseus pydriller

mkdir -p "$JAR_DIR"
curl -L -o "${JAR_DIR}/code-maat.jar" \
  "https://github.com/adamtornhill/code-maat/releases/download/v${CODE_MAAT_VERSION}/code-maat-${CODE_MAAT_VERSION}-standalone.jar"

echo
echo "Installed. Verify with:"
echo "  onefetch --version; git-quick-stats --help | head -1; scc --version; git-sizer --version; gitleaks version"
echo "  java -jar ${JAR_DIR}/code-maat.jar --help"
echo "  git-of-theseus-analyze --help"

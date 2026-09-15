#!/usr/bin/env bash
# Install the gitmole tool set on macOS. Requires Homebrew, Python 3, Java.
set -euo pipefail

CODE_MAAT_VERSION="1.0.4"
JAR_DIR="${HOME}/bin"

brew install onefetch git-quick-stats scc git-sizer gitleaks

python3 -m pip install --user git-of-theseus pydriller

mkdir -p "$JAR_DIR"
curl -L -o "${JAR_DIR}/code-maat.jar" \
  "https://github.com/adamtornhill/code-maat/releases/download/v${CODE_MAAT_VERSION}/code-maat-${CODE_MAAT_VERSION}-standalone.jar"

echo
echo "Installed. Verify with:"
echo "  onefetch --version; git-quick-stats --help | head -1; scc --version; git-sizer --version; gitleaks version"
echo "  java -jar ${JAR_DIR}/code-maat.jar --help"
echo "  git-of-theseus-analyze --help"

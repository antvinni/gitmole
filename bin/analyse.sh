#!/usr/bin/env bash
# Run the full gitmole analysis against a cloned repo.
# usage: bin/analyse.sh /path/to/clone
set -euo pipefail

if [ $# -ne 1 ] || [ ! -d "$1/.git" ]; then
  echo "usage: $0 /path/to/clone" >&2
  exit 1
fi

repo="$(cd "$1" && pwd)"
out="$(dirname "$repo")/analysis-$(basename "$repo")"
jar="${CODE_MAAT_JAR:-$HOME/bin/code-maat.jar}"
mkdir -p "$out"
cd "$repo"

echo "==> overview (onefetch)"
onefetch --no-art > "$out/overview.txt"

echo "==> contributors (git-quick-stats)"
git-quick-stats -T > "$out/contributors.txt"

echo "==> size (scc)"
scc --format json > "$out/size.json"

echo "==> repo health (git-sizer)"
git-sizer --verbose > "$out/repo-health.txt"

echo "==> secrets (gitleaks)"
gitleaks git --report-path "$out/secrets.json" --exit-code 0

echo "==> hotspots, coupling, ownership (code-maat)"
git log --all --numstat --date=short --pretty=format:'--%h--%ad--%aN' --no-renames > "$out/log.txt"
for a in revisions coupling authors age entity-ownership; do
  java -jar "$jar" -l "$out/log.txt" -c git2 -a "$a" > "$out/maat-$a.csv"
done

echo "==> code age (git-of-theseus)"
git-of-theseus-analyze . --outdir "$out/theseus"
git-of-theseus-stack-plot "$out/theseus/cohorts.json" --outfile "$out/code-age.png"
git-of-theseus-survival-plot "$out/theseus/survival.json" --outfile "$out/survival.png"

echo
echo "Done. Results in $out"

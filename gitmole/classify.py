"""Why a file is out of the scored pool: one answer for every table, the watch list and --risk.

Built once per report, so the type filter, scc's rows, the generated and vendored lists, the amalgamations
and the plumbing are read once and every section asks the same object. Not in filetypes, which blame.py
and maat.py import as scripts and which must stay free of package imports."""
from __future__ import annotations

from collections import Counter

from . import filetypes, hotspots

# In descriptive order: what a reader would call the file first. package.json is a release file before
# it is not a source type; vendor/x_test.go is vendored before it is a test file; a generated test is
# generated. The order is part of the contract: reason() is the first that applies.
REASONS = ("generated", "vendored", "test file", "example code", "release file", "amalgamation", "not a source type", "not in the tree")

# The coverage line's nouns, by count.
_NOUNS = {"scored": ("scored", "scored"), "generated": ("generated", "generated"), "vendored": ("vendored", "vendored"),
          "test file": ("test file", "test files"), "example code": ("example code", "example code"),
          "release file": ("release file", "release files"), "amalgamation": ("amalgamation", "amalgamations"),
          "not a source type": ("not a source type", "not a source type"), "not counted by scc": ("not counted by scc", "not counted by scc")}


class Classifier:
    def __init__(self, report: dict):
        meta = report.get("meta") or {}
        # a run records its --file-types spec (None for the default list); a run from before that record
        # was measured unfiltered and is classified unfiltered, as load.load_report filters scc
        self.types = filetypes.parse(meta["file_types"]) if "file_types" in meta else None
        self.tree = (report.get("size") or {}).get("files") or {}
        self.generated = set(meta.get("generated") or [])
        self.vendored = filetypes.vendor_dirs(report)
        self.amalgamations = hotspots.amalgamations(report)
        self.plumbing = filetypes.plumbing_paths(report)

    def reasons(self, path: str) -> list:
        """Every reason that applies, in REASONS order. `not in the tree` needs a tree to judge by: a run
        whose scc step was killed classifies nothing as gone, so it cannot empty every table."""
        out = []
        if path in self.generated:
            out.append("generated")
        if filetypes.is_vendored(path, self.vendored):
            out.append("vendored")
        if filetypes.is_test_path(path):
            out.append("test file")
        if filetypes.is_sample_path(path):
            out.append("example code")
        if filetypes.is_release(path, self.plumbing):
            out.append("release file")
        if path in self.amalgamations:
            out.append("amalgamation")
        if not filetypes.matches(path, self.types):
            out.append("not a source type")
        if self.tree and path not in self.tree:
            out.append("not in the tree")
        return out

    def reason(self, path: str):
        """The first reason, or None for a file in the scored pool."""
        found = self.reasons(path)
        return found[0] if found else None

    def excluded(self, path: str, reasons) -> bool:
        """Whether a table that hides `reasons` hides this file: any of its reasons is enough, so a table
        that hides tests still hides a vendored test."""
        return any(r in reasons for r in self.reasons(path))


def coverage(classifier: Classifier, tracked: list) -> dict:
    """How many tracked files each reason claims, `scored` for none. A tracked file with no scc row is a
    type scc does not classify rather than a deleted one, so it counts as `not counted by scc`."""
    counts = Counter()
    for path in tracked:
        reason = classifier.reason(path)
        counts["scored" if reason is None else "not counted by scc" if reason == "not in the tree" else reason] += 1
    return dict(counts)


def coverage_line(cov: dict) -> str:
    """'4,781 files: 3,900 scored · 610 test files · …', the buckets in REASONS order."""
    order = ["scored", *REASONS[:-1], "not counted by scc"]
    parts = [f"{cov[k]:,} {_NOUNS[k][0 if cov[k] == 1 else 1]}" for k in order if cov.get(k)]
    return f"{sum(cov.values()):,} files: " + " · ".join(parts)

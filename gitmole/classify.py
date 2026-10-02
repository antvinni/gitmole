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
        self.test_doubles = set(meta.get("test_doubles") or [])   # Cargo bins only the tests start (filetypes.test_doubles)
        self.vendored = filetypes.vendor_dirs(report)
        self.amalgamations = hotspots.amalgamations(report)
        self.plumbing = filetypes.plumbing_paths(report)
        self._reasons = {}   # memoised per instance: every hide pass in a report asks the same paths again

    def reasons(self, path: str) -> tuple:
        """Every reason that applies, in REASONS order. `not in the tree` needs a tree to judge by: a run
        whose scc step was killed classifies nothing as gone, so it cannot empty every table. Cached per
        path and returned as a tuple so callers cannot mutate the cached result."""
        if path in self._reasons:
            return self._reasons[path]
        out = []
        if path in self.generated:
            out.append("generated")
        if filetypes.is_vendored(path, self.vendored):
            out.append("vendored")
        if filetypes.is_test_path(path) or path in self.test_doubles:
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
        self._reasons[path] = tuple(out)
        return self._reasons[path]

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


DOC_MAJORITY = 0.5   # documentation holding more than this share of the tree's lines is what the repository is made of


def lines(classifier: Classifier, code: dict) -> dict:
    """{tracked, scored, documentation, other_types}: scc's code lines over every file it counted (`code`,
    load.all_code), those of the scored pool, and those the type filter left out, documentation
    (filetypes.is_doc_path) apart from the rest. A file of a type that is not ranked counts there wherever
    it sits: a README under tests/ is documentation the filter left out before it is a test file. The
    unit is the header's own, so the shares can be checked against its line count."""
    out = {"tracked": 0, "scored": 0, "documentation": 0, "other_types": 0}
    for path, n in code.items():
        out["tracked"] += n
        if classifier.reason(path) is None:
            out["scored"] += n
        elif not filetypes.matches(path, classifier.types):
            out["documentation" if filetypes.is_doc_path(path) else "other_types"] += n
    return out


def unranked(lines: dict) -> bool:
    """Whether the files the type filter left out hold more lines than the scored ones: the report then
    ranks the smaller part of what `--file-types all` would, and its header says so. Lines, not files, and
    the type filter alone: a tree with more test files than source files is ranked as it was meant to be,
    which is most trees."""
    return lines["documentation"] + lines["other_types"] > lines["scored"]


NO_TABLE = ("not a source type", "not counted by scc")   # the coverage buckets no table carries, hidden or shown


def unseen(files: dict) -> bool:
    """Whether the tracked files no table carries outnumber the scored ones, by the run's own coverage count:
    a test, a vendored or a generated file is in the tables, hidden, and --full shows it; a file of a type
    that is not ranked is in none. The header then says how many files are scored."""
    return sum(files.get(k) or 0 for k in NO_TABLE) > (files.get("scored") or 0)


def documents_lead(lines: dict) -> bool:
    """Whether documentation the type filter left out is most of the tree's lines (DOC_MAJORITY)."""
    return lines["tracked"] > 0 and lines["documentation"] > DOC_MAJORITY * lines["tracked"]


def documents(classifier: Classifier, code: dict) -> frozenset:
    """The documents at HEAD that are out of the pool for their type and for nothing else: a generated
    page, a vendored README or a test's fixture has its own reason, and the list of most-changed
    documents is not about those. `code` is the tree at HEAD, so "not in the tree", which the classifier
    says of every file its type-filtered listing lacks, is not a reason here."""
    def only_its_type(path):
        return [r for r in classifier.reasons(path) if r != "not in the tree"] == ["not a source type"]
    return frozenset(p for p in code if filetypes.is_doc_path(p) and only_its_type(p))

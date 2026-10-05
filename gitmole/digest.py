"""findings.json: what the report concluded, as a file a script can read and a CI job can upload.

prometheus's output directory was 17 MB and held no findings: they were 27 KB of a 27 MB `--json` export that
a run writes only when asked, so the directory the report's last line called the results had the inputs of
every conclusion and none of the conclusions. The two files a reader would be sent to for the rest,
secrets.json and dependencies.json, are mode 0600, so a digest that names them from a CI artefact names files
its reader cannot open; what a reader needs from them (the counts, the database's date) is here instead.

The file is a function of the commit and the options, as the export outside its `envelope` is: no path of the
machine, no seconds, no memory figure. It holds no email address (`summary` counts the identities) and no
secret: a value, its hash, a matched line and a fingerprint stay in secrets.json, and here the scan is counts.
It is not called report.json, which the README and docs/cli.md teach as the name of the full export.

Every key but two is the full export's, with the export's rows: `findings`, `watch`, `watch_backtest`, `osps`,
`not_computed`, and of `meta` the two members that say what made the report (`steps`, `run`). `summary` is the
portfolio export's row for a repository, the header's numbers. `hygiene` and `dependencies` are the export's
objects with every list replaced by its length (`unused` by `unused_count`), which is what a check that passed
has to say. `secret_counts` is the one key the export does not have: there the scan is rows.
"""
from __future__ import annotations

import json
import os

from . import leaks, render

FILE = render.FINDINGS_FILE
META_KEYS = ("steps", "run")   # what ran and with which tools: the same for the same commit, unlike the seconds beside them


def _counted(value):
    """A step's object without its lists: a scalar as it is, an object the same way, and a list as its length
    under `<key>_count`, unless the object counts it already (hygiene.json's own `unpinned_count` beside
    `unpinned`, which holds the first rows only)."""
    if not isinstance(value, dict):
        return value
    out = {}
    for key, v in value.items():
        if isinstance(v, list):
            out.setdefault(f"{key}_count", len(v))
        elif isinstance(v, dict):
            out[key] = _counted(v)
        else:
            out[key] = v
    for key, v in value.items():   # the step's own count wins over a list's length: the list may be capped
        if key.endswith("_count") and not isinstance(v, (list, dict)):
            out[key] = v
    return out


def secret_counts(report: dict) -> dict:
    """The secrets scan as counts: whether it ran, the distinct values, the places they are in (a value at a
    commit, file and line), how many of those HEAD still holds or only history does, each with the number the
    scanner graded high, and the placeholder-shaped hits left out. Never a value, a line or a fingerprint."""
    rows = report.get("secrets") or []
    places = render.secret_places(report)

    def split(kept):
        return {"places": len(kept), "high_confidence": sum(1 for p in kept if p["high"])}
    return {"scanned": bool(report.get("secrets_scanned")), "values": len(leaks.group(rows)), "places": len(places),
            "at_head": split([p for p in places if p["at_head"] is True]), "history_only": split([p for p in places if p["at_head"] is False]),
            "unplaced": split([p for p in places if p["at_head"] is None]), "placeholders": leaks.placeholders(rows)}


def build(report: dict, found: list) -> dict:
    """The digest of one report: see the module's text for what each key is and where its shape comes from."""
    full = render.to_json(report, found)
    meta = report.get("meta") or {}
    out = {key: full[key] for key in ("findings", "watch", "watch_backtest", "osps", "not_computed") if key in full}
    out["summary"] = render.summary(report)
    out["meta"] = {key: meta[key] for key in META_KEYS if key in meta}
    out["hygiene"] = _counted(report.get("hygiene") or {})
    out["dependencies"] = _counted(report.get("dependencies") or {})
    out["secret_counts"] = secret_counts(report)
    return out


def dumps(report: dict, found: list) -> str:
    """The digest as text: keys sorted and no indentation, since its size is paid on every run."""
    return json.dumps(build(report, found), sort_keys=True, ensure_ascii=False, separators=(",", ":")) + "\n"


def write(out_dir: str, report: dict, found: list) -> str:
    """Write the digest into the output directory, whole or not at all, and return its path."""
    path = os.path.join(out_dir, FILE)
    with open(path + ".tmp", "w", encoding="utf-8") as fh:
        fh.write(dumps(report, found))
    os.replace(path + ".tmp", path)
    return path

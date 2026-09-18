"""What changed since an earlier --json export: findings that are new, resolved or persisting, files that
entered or left the watch list, the tally before and after. Pure over two report dicts."""
from __future__ import annotations

from . import findings, watch

# A rule emits one finding per report, except these two, which emit one per row; the evidence field
# that tells the rows apart joins the rule id in the key.
KEY_FIELDS = {"repo_health": "metric", "placeholder_identity": "email"}


def key(finding: dict) -> tuple:
    """A finding's identity across two reports: the rule id alone, unless the rule is one of KEY_FIELDS,
    where one report can hold several findings for the same rule and the evidence field is what tells
    them apart (a metric name, an email)."""
    rid = finding["rule"]["id"]
    field = KEY_FIELDS.get(rid)
    return (rid, (finding.get("evidence") or {}).get(field)) if field else (rid,)


def is_export(data) -> bool:
    """A gitmole --json export: a report with its findings and watch list. Every finding must carry a
    rule id and a severity, the shape key() and _tally() read without a default — exports from before
    0.8.0 have findings without a `rule`, and would otherwise pass this check and crash later on a bare
    KeyError instead of being refused here."""
    if not (isinstance(data, dict) and isinstance(data.get("meta"), dict) and "findings" in data and "watch" in data):
        return False
    found, watch_rows = data.get("findings"), data.get("watch")
    return (isinstance(found, list) and isinstance(watch_rows, list) and all(isinstance(r, dict) for r in watch_rows) and
            all(isinstance(f, dict) and isinstance(f.get("rule"), dict) and "id" in f["rule"] and "severity" in f for f in found))


def _tally(found: list) -> dict:
    counts = {s: 0 for s in findings.SEVERITIES}
    for f in found:
        counts[f["severity"]] += 1
    return counts


def _ordered(found: list) -> list:
    return sorted(found, key=lambda f: (findings.SEVERITIES.index(f["severity"]), f["title"], str(key(f))))


def _options_differ(before_meta: dict, after_meta: dict) -> list:
    """The options that change what a run sees: --since and --file-types from meta's top level, --ignore and
    --ignore-data from the manifest when both exports have one. --deep is recorded there too but only
    decides whether code age, plots and duplicates ran, none of which reach the findings or the watch list."""
    out = [name for name in ("since", "file_types") if before_meta.get(name) != after_meta.get(name)]
    b, a = (before_meta.get("run") or {}).get("options"), (after_meta.get("run") or {}).get("options")
    if b is not None and a is not None:
        out += [name for name in ("ignore", "ignore_data") if b.get(name) != a.get(name)]
    return out


def compare(before: dict, report: dict, found: list, top: int = watch.WATCH_TOP) -> dict:
    """before: an earlier export; report and found: this run's loaded report and its findings."""
    b = {key(f): f for f in before.get("findings") or []}
    a = {key(f): f for f in found}
    persisting = [{**a[k], "was": b[k]["severity"]} for k in a if k in b]
    before_watch = [f for f in (r.get("file") for r in (before.get("watch") or [])[:top]) if f]
    after_watch = [r["file"] for r in watch.risks(report)[:top]]
    meta_b, meta_a = before.get("meta") or {}, report.get("meta") or {}
    return {"new": _ordered([a[k] for k in a if k not in b]), "resolved": _ordered([b[k] for k in b if k not in a]),
            "persisting": _ordered(persisting),
            "watch_entered": [f for f in after_watch if f not in before_watch], "watch_left": [f for f in before_watch if f not in after_watch],
            "tally": {"before": _tally(before.get("findings") or []), "after": _tally(found)},
            "before": {"commit": (meta_b.get("run") or {}).get("commit"), "date": meta_b.get("last_date"),
                       "options_differ": _options_differ(meta_b, meta_a)}}

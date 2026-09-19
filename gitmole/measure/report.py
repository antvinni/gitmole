"""docs/measurement-history.md and the graphs under docs/evolution/, from the release records. Each
summary is recomputed from the raw per-repository records, so a change to the aggregation needs no rerun."""
from __future__ import annotations

import json
import os

from . import corpus, dashboard, labels, svg

DOCS = os.path.join(corpus.ROOT, "docs")
GRAPHS = os.path.join(DOCS, "evolution")


def _pct(x):
    return "-" if x is None else f"{100 * x:.0f}%"


def _num(x, fmt="{:.2f}"):
    return "-" if x is None else fmt.format(x)


def _short(note: str, n: int = 70) -> str:
    """A failure note cut to its last clause: the exception's name and the start of its message."""
    note = " ".join(str(note).split())
    return note if len(note) <= n else note[:n - 1] + "…"


def _share(pair):
    return None if not pair or not pair[1] else pair[0] / pair[1]


def graphs(history: list) -> dict:
    """The long graphs draw each release over the fixed series (corpus.json `series`), so a change to the
    development set is not a move; robustness and the gate are fixtures, the holdout its own set."""
    labels_ = [r["version"] for r in history]
    s = [r.get("series") or r["summary"] for r in history]
    whole = [r["summary"] for r in history]
    crashed = [i for i, x in enumerate(whole) if x.get("crashed")]
    col = lambda k: [x.get(k) for x in s]   # noqa: E731
    useful = [r.get("useful") or {} for r in history]
    out = {}
    out["ranking.svg"] = svg.chart("Is it right? The watch list's share of the gap from random to perfect (headroom at 15)", labels_, [
        {"label": "watch list", "values": col("headroom"), "band": [x.get("headroom_ci") for x in s]},
        {"label": "churn alone", "values": col("churn_headroom"), "dashed": True, "color": "#57606a"},
        {"label": "watch list, 13 held-out repositories", "values": [x.get("holdout_headroom") for x in whole], "color": "#bf3989"}], crashed, (0, 1), "%",
        "curl, django, react and gitmole (every release), six cut-offs, fixes in the next six months; dots: independent labels, repositories never tuned on")
    out["useful.svg"] = svg.chart("Is it useful? Findings the default report spells out that are worth acting on", labels_, [
        {"label": "labelled actionable", "values": [u.get("actionable_share") for u in useful]},
        {"label": "carrying a label at all", "values": [u.get("labelled_share") for u in useful], "dashed": True, "color": "#57606a"}], crashed, (0, 1), "%",
        "development and well-kept sets, hand labels (measure/labels.jsonl); none before 0.28.0")
    out["whole-ranking.svg"] = svg.chart("The whole ranking: ROC-AUC and recall at 20% of the lines", labels_, [
        {"label": "AUC", "values": col("auc")}, {"label": "AUC, churn", "values": col("churn_auc"), "dashed": True, "color": "#0969da"},
        {"label": "recall at 20%", "values": col("recall20"), "color": "#8250df"},
        {"label": "recall, churn", "values": col("churn_recall20"), "dashed": True, "color": "#8250df"}], crashed, (0, 1), "",
        "median over curl, django, react and gitmole")
    out["findings.svg"] = svg.chart("Findings per repository", labels_, [
        {"label": "median", "values": col("findings_median")}, {"label": "90th percentile", "values": col("findings_p90"), "dashed": True},
        {"label": "spelled out in the default report", "values": col("shown_median"), "color": "#1a7f37"}],
        crashed, None, "", "curl, django, react and gitmole; the report's brevity is the product")
    out["report-length.svg"] = svg.chart("Terminal report length (lines, median)", labels_, [
        {"label": "lines at 100 columns", "values": col("report_lines")}], crashed, None, "", "the default report, curl, django, react and gitmole")
    out["runtime.svg"] = svg.chart("Run time of curl, django, react and gitmole (seconds, one repository at a time)", labels_, [
        {"label": "seconds", "values": col("seconds")}], crashed, None, "", "one laptop; each run records the load average")
    out["memory.svg"] = svg.chart("Peak memory of the largest process (MB)", labels_, [
        {"label": "MB", "values": col("peak_mb")}], crashed, None, "", "the largest of the runs on curl, django, react and gitmole")
    out["robustness.svg"] = svg.chart("Does it run? Robustness, gate catch rate and scored share", labels_, [
        {"label": "runs completed", "values": [_share(x.get("robust")) for x in whole]},
        {"label": "gate cases caught", "values": [_share(x.get("gate_caught")) for x in whole]},
        {"label": "tracked text files scored", "values": col("scored_share")}], crashed, (0, 1), "%",
        "awkward inputs and gate fixtures included")
    return out


def _moves(history: list) -> dict:
    out, prev = {}, None
    for r in history:
        s = r["summary"]
        if prev is not None and not s.get("crashed"):
            m = dashboard.moved(prev, s)
            if m:
                out[r["version"]] = m
        if not s.get("crashed"):
            prev = s
    return out


def page(history: list, extras: dict) -> str:
    moves = _moves(history)
    lines = ["# Measurement history", "",
             "Every release of gitmole run through the harness of "
             "[measurement.md](https://github.com/antvinni/gitmole/blob/main/docs/measurement.md); back to "
             "[the README](https://github.com/antvinni/gitmole#readme). Regenerated by `python -m gitmole.measure report` "
             "from the records in [docs/measurements/](https://github.com/antvinni/gitmole/tree/main/docs/measurements).", "",
             "Each release runs from its own source over the development set (curl, django and react at the example "
             "commits, and gitmole itself), the awkward inputs and the gate fixtures, one repository at a time, with the "
             f"reference date fixed at {history[-1]['reference_date'] if history else ''}. What it produces is scored by "
             "the current definitions, which stay fixed across the history: the ranking is the release's own, rebuilt at "
             "six cut-offs by its own backtest, and the outcome is the files a fix commit touched in the six months after "
             "each cut-off. The holdout is not read here: it runs only for the release a note claims is more effective. "
             "A release that crashed or timed out on a development repository is drawn at the bottom of every graph "
             "with a red cross, and its row says why. The graphs draw every release over the same four repositories, "
             "curl, django, react and gitmole, so a repository joining the development set is not a move; the table "
             "and the dashboard use the whole set. The first three graphs are the ones the README shows: is the "
             "ranking right, are the findings worth acting on, does it run.", ""]
    notes = os.path.join(corpus.ROOT, "measure", "history-notes.md")
    if os.path.exists(notes):   # the reading of the history, written by hand; the rest of the page is generated
        with open(notes, encoding="utf-8") as fh:
            lines += [fh.read().strip(), ""]
    for name in ("ranking", "useful", "robustness", "whole-ranking", "findings", "report-length", "runtime", "memory"):
        lines += [f"![{name}](evolution/{name}.svg)", ""]
    lines += ["## By release", "",
              "Headroom is (hits − random) / (perfect − random) at 15, the median over the development repositories, "
              "with a bootstrap interval over repositories. ▲ or ▼ marks a release whose value left the previous "
              "release's interval, the only move that counts. W/L/T is the watch list against churn alone at each "
              "cut-off. Bug magnets is how much more often the files the rule named were fixed again than unnamed "
              "files in the same deciles of the list's own score.", "",
              "| release | headroom | churn | W/L/T | AUC | recall 20% | stable | magnets | findings | lines | scored | robust | gate | seconds | MB | note |",
              "|---|---:|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|"]
    for r in history:
        s = r["summary"]
        if s.get("crashed"):
            note = "crashed: " + "; ".join(f"{k}: {_short(v)}" for k, v in sorted(s["crashed"].items()))
            lines.append(f"| {r['version']} | crashed | | | | | | | | | | {_num(_share(s.get('robust')), '{:.0%}')} | | | | {note.replace('|', '/')} |")
            continue
        ci = s.get("headroom_ci")
        head = _num(s.get("headroom")) + (f" [{ci[0]:.2f}, {ci[1]:.2f}]" if ci and ci[0] != ci[1] else "")
        head += {"up": " ▲", "down": " ▼"}.get(moves.get(r["version"]), "")
        wlt = "/".join(str(x) for x in s["wins_losses_ties"]) if s.get("wins_losses_ties") else "-"
        gate = f"{s['gate_caught'][0]}/{s['gate_caught'][1]}" if s.get("gate_caught") else "-"
        robust = f"{s['robust'][0]}/{s['robust'][1]}" if s.get("robust") else "-"
        failed = [f"{n}: {_short(x.get('note') or x['status'])}" for n, x in sorted(r["repos"].items()) if x.get("status") not in ("ok", "refused")]
        failed += [f"{n}: {len(x['steps_failed'])} step(s) failed" for n, x in sorted(r["repos"].items()) if x.get("status") == "ok" and x.get("steps_failed")]
        lines.append(f"| {r['version']} | {head} | {_num(s.get('churn_headroom'))} | {wlt} | {_num(s.get('auc'))} | {_pct(s.get('recall20'))} | "
                     f"{_num(s.get('stability_top15'))} | {_num(s.get('bug_magnets_ratio'))} | {_num(s.get('findings_median'), '{:g}')}/{_num(s.get('findings_p90'), '{:g}')} | "
                     f"{_num(s.get('report_lines'), '{:g}')} | {_pct(s.get('scored_share'))} | {robust} | {gate} | {_num(s.get('seconds'), '{:.0f}')} | "
                     f"{_num(s.get('peak_mb'), '{:.0f}')} | {'; '.join(failed).replace('|', '/')} |")
    if history:
        lines += ["", *current(history[-1], extras)]
    return "\n".join(lines) + "\n"


def current(record: dict, extras: dict) -> list:
    s = record["summary"]
    out = [f"## The dashboard for {record['version']}", ""]
    rows = [("median headroom at 15", "holdout", f"{_num(s.get('holdout_headroom'))} {s.get('holdout_headroom_ci') or ''}".strip() if s.get("holdout_headroom") is not None else "not run for this record"),
            ("median headroom at 15", "development", _num(s.get("headroom"))),
            ("recall at 20% of lines", "holdout" if s.get("holdout_recall20") is not None else "development", _pct(s.get("holdout_recall20") if s.get("holdout_recall20") is not None else s.get("recall20"))),
            ("top-15 stability over 50 commits", "development", _num(s.get("stability_top15"))),
            ("top-15 carried over from one cut-off to the next, six months", "development", _num(s.get("carryover_top15"))),
            ("findings per repository, median and p90", "development", f"{_num(s.get('findings_median'), '{:g}')} and {_num(s.get('findings_p90'), '{:g}')}")]
    u = record.get("useful") or {}
    rows.append(("findings the default report spells out that are labelled actionable", "development and well-kept",
                 f"{_pct(u.get('actionable_share'))} of {u.get('shown', 0)}, {_pct(u.get('labelled_share'))} labelled" if u.get("shown") else "no finding ids in this record"))
    score = labels.score()
    rows.append(("rules sound, broken and undecided", "labelled sample", ", ".join(f"{k} {v}" for k, v in sorted(score["verdicts"].items())) or "no labels"))
    kept = s.get("well_kept_with_critical")
    rows.append(("repositories with a critical labelled false", "well-kept", f"{kept[0]} of {kept[1]} fired a critical" if kept else "not run for this record"))
    rows.append(("wall time and peak memory", "development", f"{_num(s.get('seconds'), '{:.0f}')} s, {_num(s.get('peak_mb'), '{:.0f}')} MB"))
    rows.append(("scored share of tracked files", "development", _pct(s.get("scored_share"))))
    desc = (extras or {}).get("description") or {}
    unexplained = sum(1 for checks in desc.values() for c in checks if c["agree"] is False and not c.get("explained"))
    rows.append(("unexplained description disagreements", "development", str(unexplained) if desc else "not run"))
    out += ["| | set | value |", "|---|---|---|"] + [f"| {a} | {b} | {c} |" for a, b, c in rows] + [""]
    if extras:
        out += _extras(extras)
    return out


def _extras(x: dict) -> list:
    out = []
    sens = x.get("sensitivity") or []
    if sens:
        counts = {}
        for r in sens:
            counts[r["verdict"]] = counts.get(r["verdict"], 0) + 1
        out += ["### Threshold sensitivity", "",
                f"{len(sens)} numeric thresholds across the rules, each moved 10, 25 and 50% either side on the development set: "
                + ", ".join(f"{v} {k}" for k, v in sorted(counts.items())) + ". None of them records where its value came from, "
                "so each counts as fitted until a line beside it says otherwise.", "",
                "| rule | threshold | default | verdict | findings at −10% / shipped / +10% |", "|---|---|---:|---|---|"]
        for r in sorted(sens, key=lambda r: ({"fragile": 0, "moderate": 1, "flat": 2, "silent": 3, "untested": 4}[r["verdict"]], r["rule"], r["param"])):
            if r["verdict"] in ("silent", "untested"):
                continue
            def n(f):
                sh = r["shifts"].get(f)
                return "=" if sh is None else str(sum(v["findings"] for v in sh["repos"].values()))
            out.append(f"| {r['rule']} | {r['param']} | {r['default']} | {r['verdict']} | {n('0.9')} / {sum(r['base'].values())} / {n('1.1')} |")
        out.append("")
    desc = x.get("description") or {}
    if desc:
        out += ["### Description checks", "", "| repository | check | gitmole | second count | by |", "|---|---|---:|---:|---|"]
        for repo, checks in sorted(desc.items()):
            for c in checks:
                mark = "" if c["agree"] else " (not checked)" if c["agree"] is None else (" (explained)" if c.get("explained") else " (unexplained)")
                out.append(f"| {repo} | {c['check']}{mark} | {c['gitmole']} | {c['second']} | {c['second_by']} |")
        out.append("")
    hook = x.get("hook") or {}
    if hook:
        out += ["### The hook's coupling warning, replayed", "",
                "Zimmermann et al.'s experiments at file granularity: leave one file out of a commit and see whether the "
                "warning names it (precision, and feedback: the share of queries that warn), and a complete commit, where "
                "any warning is a false alarm. ROSE's file-level figures are the bar.", "",
                "| repository | queries | feedback | precision | complete commits | closure false alarms |", "|---|---:|---:|---:|---:|---:|"]
        for repo, h in sorted(hook.items()):
            out.append(f"| {repo} | {h['queries']} | {_pct(h['feedback'])} | {_pct(h['precision'])} | {h['complete_commits']} | {_pct(h['closure_false_alarm_rate'])} |")
        out.append("")
    det = x.get("determinism") or []
    if det:
        out += ["### Determinism across time zones and locales", "",
                "| repository | identical outside the envelope |", "|---|---|"] + [f"| {d['repo']} | {'yes' if d['identical'] else 'no'} |" for d in det] + [""]
    return out


def render(records_dir: str) -> list:
    history = dashboard.load_history(records_dir)
    series = set((corpus.load().get("series") or {}).get("repos") or []) or None
    marks = labels._read(os.path.join(labels.DIR, "labels.jsonl"))
    for r in history:
        r["summary"] = dashboard.summarise(r)
        r["series"] = dashboard.summarise(r, only=series)
        r["useful"] = labels.usefulness(r, marks)
    extras = None
    extras_dir = os.path.join(records_dir, "extras")
    if history and os.path.exists(os.path.join(extras_dir, f"{history[-1]['version']}.json")):
        with open(os.path.join(extras_dir, f"{history[-1]['version']}.json"), encoding="utf-8") as fh:
            extras = json.load(fh)
    os.makedirs(GRAPHS, exist_ok=True)
    written = []
    for name, text in graphs(history).items():
        path = os.path.join(GRAPHS, name)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)
        written.append(path)
    path = os.path.join(DOCS, "measurement-history.md")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(page(history, extras))
    written.append(path)
    return written

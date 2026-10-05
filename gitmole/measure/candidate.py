"""Is a ranking candidate better than the current watch list? The decision of docs/measurement.md, "Is a
candidate better?": both releases are run from their own source over the same repositories, ranked at
the same six cut-offs, and scored on the baseline's pool against the same outcome; the effect at a
cut-off is the candidate's top-fifteen hits minus the baseline's, averaged per repository, and an exact
one-sided sign-flip test over the repositories decides.

    python -m gitmole.measure.candidate BASE CANDIDATE [--sets development,large,well-kept] [--only NAME]... [--outcome current|declared] [--json PATH]
    python -m gitmole.measure.candidate BASE CANDIDATE --holdout --approved "who agreed, when" [--again] [--json PATH]

BASE and CANDIDATE are git refs of this repository ("worktree" for the working tree, except on the
holdout). The baseline is run again beside the candidate rather than read from its record, so the two
share one toolchain and one clone state. The holdout is read only with the maintainer's go-ahead, over
all of its repositories, and only once every clone and the labels are in place; each read is then
appended to measure/holdout-reads.jsonl, which is committed with the result. A second read of the same
candidate is refused unless --again says it is one, and is counted as such.

A repository or cut-off that failed on either side makes the result "incomplete": dropping it would let
a candidate that crashes where it would lose be judged on the rest. What the saturated cut-offs (half
the pool or more fixed) do to the result is printed for information and never decides: at such a
cut-off the two lists tend to name the same files and tie on their own. Where the labels end (the
holdout's), the decision is printed again without the cut-offs that may be snoring (snore_exposed), for
information only.

Fix locality has two definitions of a fix, both this tree's and never the releases' (measure.outcome):
`current` (maat.is_fix) and `declared` (the type `fix` alone, where the repository declares Conventional
Commits). Both are scored and printed side by side; --outcome names the one that decides, `current`
unless asked, so a candidate that changes the classifier is judged against an outcome it cannot move.
The holdout is scored on its labels, which neither definition decides."""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import subprocess
import sys
from fractions import Fraction

from .. import evaluate
from . import corpus, dashboard, harness, metrics
from . import outcome as outcomes

SATURATED = dashboard.SATURATED   # half the pool or more fixed at a cut-off: flagged, for information only
ALPHA = 0.05                      # the one-sided p under which a positive mean effect counts
HOLDOUT_READS = os.path.join(corpus.ROOT, "measure", "holdout-reads.jsonl")
EFFECTIVENESS_SETS = "development,large,well-kept"


class SpentRead(Exception):
    """The holdout was already read for this candidate."""


def _digest(files) -> str:
    return hashlib.sha256("\n".join(sorted(files)).encode("utf-8", "surrogateescape")).hexdigest()[:16]


def paired(base: dict, cand: dict, outcome: set, top: int = harness.TOP) -> dict:
    """One cut-off, both lists on the baseline's pool: the candidate's order restricted to the files the
    baseline scored, with any it did not rank after them in the baseline's order. Where the candidate's
    own pool differs (its classifier moved), the files it added and dropped are counted: an added file
    cannot score on the baseline's pool, and a dropped one costs the candidate only if it was fixed, so a
    pool that moved is reported beside the effect rather than hidden in it."""
    pool = base["pool"]
    members, cand_members = set(pool), set(cand["pool"])
    positives = outcome & members
    ranked = [f for f in dict.fromkeys(cand["pool"]) if f in members]
    placed = set(ranked)
    ranked += [f for f in pool if f not in placed]
    base_hits, cand_hits = metrics.hits(pool, positives, top), metrics.hits(ranked, positives, top)
    return {"pool": len(pool), "positives": len(positives), "base_hits": base_hits, "cand_hits": cand_hits,
            "d": cand_hits - base_hits, "saturated": bool(pool) and len(positives) / len(pool) >= SATURATED,
            "pool_digest": _digest(members), "cand_pool_digest": _digest(cand_members),
            "pool_added": len(cand_members - members), "pool_dropped": len(members - cand_members)}


def _effects(rows: dict) -> dict:
    return {r: Fraction(sum(x["d"] for x in xs), len(xs)) for r, xs in rows.items() if xs}


def under(rows: dict, outcome: str) -> dict:
    """The rows as scored against `outcome`: a cut-off's `declared` pairing in place of its own under the
    declared-type outcome, where the repository declares the convention (elsewhere the two are one)."""
    if outcome == "current":
        return rows
    return {r: [{**x, **x["declared"]} if x.get("declared") else x for x in xs] for r, xs in rows.items()}


def decide(rows: dict, outcome: str = "current") -> dict:
    """{repository: [rows]} -> the per-repository mean effects, their mean, the exact one-sided sign-flip p
    over repositories, and wins, losses and ties over repositories; `failed` counts the rows that carry an
    error, per repository; beside it, for information, the same without the saturated cut-offs. `outcome`
    is the definition of a fix the rows are read under (measure.outcome)."""
    rows = under(rows, outcome)
    failed = {r: sum("error" in x for x in xs) for r, xs in rows.items() if any("error" in x for x in xs)}
    rows = {r: [x for x in xs if "d" in x] for r, xs in rows.items()}

    def summary(effects):
        mean = sum(effects.values()) / len(effects) if effects else None
        return {"effects": effects, "mean": mean, "p": metrics.sign_flip(list(effects.values()))}

    out = summary(_effects(rows))
    out.update(wins=sum(e > 0 for e in out["effects"].values()), losses=sum(e < 0 for e in out["effects"].values()),
               ties=sum(e == 0 for e in out["effects"].values()), failed=failed)
    out["without_saturated"] = summary(_effects({r: [x for x in xs if not x["saturated"]] for r, xs in rows.items()}))
    return out


def snore_exposed(cutoff: str, label_end: str, horizon: int = harness.HORIZON) -> bool:
    """Whether a cut-off's bugs may not have been labelled yet. A labelled dataset stops at `label_end`, and
    a bug is labelled only once it is found: defects are often found releases after they are introduced
    ("snoring", Ahluwalia, Falessi and Di Penta, MSR 2019; Falessi et al., TOSEM 2022), so recent code reads
    clean. A cut-off is exposed when its horizon and one more horizon for the bugs inserted in it to surface
    (T + 2 x horizon) run past the label end: on the holdout's ApacheJIT labels, which end on 2019-12-31,
    exactly 2019-06-30. Fix locality on development is a complete window and cannot snore."""
    return evaluate.months_after(cutoff, 2 * horizon) > label_end


def unsnored(rows: dict, ends: dict, horizon: int = harness.HORIZON) -> dict:
    """decide() again without the snore-exposed cut-offs of the repositories whose labels end (`ends`:
    {repository: label end}), with what was left out under `dropped`. Reported beside the decision, never
    deciding: nothing is dropped from the result itself. A failed row is kept, so a failure still shows."""
    dropped = {r: sorted({x["cutoff"] for x in xs if "d" in x and ends.get(r) and snore_exposed(x["cutoff"], ends[r], horizon)})
               for r, xs in rows.items()}
    kept = {r: [x for x in xs if "d" not in x or x["cutoff"] not in dropped[r]] for r, xs in rows.items()}
    out = decide(kept)
    out["dropped"] = {r: v for r, v in dropped.items() if v}
    return out


def verdict(result: dict) -> str:
    if result.get("failed"):
        return "incomplete"
    if result.get("mean") is None:
        return "no data"
    return "better" if result["mean"] > 0 and result["p"] is not None and result["p"] < ALPHA else "not shown"


def log_holdout_read(path: str, base: str, cand: str, base_commit: str, cand_commit: str, approved: str,
                     again: bool = False, sets: str = "holdout") -> dict:
    """Append one holdout read. A read needs the maintainer's go-ahead in words; a candidate already read
    raises SpentRead unless `again` says this is a second read, which is then counted, not hidden."""
    if not (approved or "").strip():
        raise ValueError("a holdout read needs --approved: who agreed to it, and when")
    if not cand_commit:
        raise ValueError("a holdout read needs the candidate's commit")
    rows = []
    if os.path.exists(path):
        with open(path, encoding="utf-8") as fh:
            rows = [json.loads(line) for line in fh if line.strip()]
    earlier = [r for r in rows if r.get("candidate_commit") == cand_commit]
    if earlier and not again:
        raise SpentRead(f"the holdout was read for {cand_commit[:12]} on {earlier[-1]['date']}; pass --again to read it again, counted as read {len(earlier) + 1}")
    row = {"date": dt.date.today().isoformat(), "base": base, "candidate": cand, "base_commit": base_commit,
           "candidate_commit": cand_commit, "approved": approved.strip(), "read": len(earlier) + 1, "sets": sets}
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, sort_keys=True) + "\n")
    return row


def resolve(ref: str) -> str:
    """The commit a ref names, or ValueError; `worktree` is HEAD plus whatever is uncommitted."""
    proc = subprocess.run(["git", "rev-parse", "--verify", ("HEAD" if ref == "worktree" else ref) + "^{commit}"],
                          cwd=corpus.ROOT, capture_output=True, text=True)
    if proc.returncode != 0:
        raise ValueError(f"not a commit: {ref}")
    return proc.stdout.strip()


def holdout_preflight(args, entries: list, root: str, labels_dir: str) -> list:
    """Everything that could make a holdout read measure the wrong thing, checked before the read is
    logged: a committed candidate (a working tree is not a commit anyone can name), all of the holdout (a
    subset would let partial reads choose repositories), every clone present at its pinned commit (none is
    fetched for a read), and the labels the holdout is scored against. Returns the problems, empty if none."""
    problems = []
    if "worktree" in (args.base, args.candidate):
        problems.append("the holdout is read for commits, not a working tree")
    if args.only:
        problems.append("the holdout is read whole: --only is refused with --holdout")
    for entry in entries:
        dest = os.path.join(root, "clones", entry["name"])
        ok = os.path.isdir(os.path.join(dest, ".git")) and subprocess.run(
            ["git", "cat-file", "-e", entry["commit"] + "^{commit}"], cwd=dest, capture_output=True).returncode == 0
        if not ok:
            problems.append(f"{entry['name']}: no clone at its pinned commit under {os.path.join(root, 'clones')}")
        if entry.get("labels") and harness.labels_for(entry, None, labels_dir) is None:
            problems.append(f"{entry['name']}: its {entry['labels']} labels are not in {labels_dir}")
    return sorted(set(problems))


def compare_entry(base_src: str, cand_src: str, entry: dict, root: str, reference: str, labels_dir: str, conventions: dict = None) -> list:
    """Both releases on one repository: each run once from its own source, then ranked at every cut-off,
    each cut-off paired against the current outcome and, where the repository declares Conventional
    Commits, against the declared-type one under `declared`. A failure on either side is a row with an
    error, never a missing row. The repository's convention goes into `conventions` when one is given."""
    labels = harness.labels_for(entry, None, labels_dir) if entry.get("labels") else None
    if entry.get("labels") and labels is None:
        return [{"error": "labels not found"}]   # never quietly scored on fix locality instead
    clone = corpus.clone(entry, root)
    outs = {}
    for side, src in (("base", base_src), ("candidate", cand_src)):
        rec = harness.run_release(src, clone, os.path.join(root, "candidate", side, entry["name"]), reference)
        if rec.get("status") != "ok":
            return [{"error": f"{side}: {rec.get('note') or rec.get('status')}"}]
        outs[side] = rec["out"]
    commits = harness.canonical_log(clone, os.path.join(root, "logs", entry["name"] + ".txt"))
    conv, declared = harness.declared_windows(entry, commits, clone, labels)
    if conventions is not None:
        conventions[entry["name"]] = conv
    rows = []
    for t, outcome in harness.cutoff_windows(entry, commits, labels, outcomes.predicate("current")):
        base = harness.ranking_at(base_src, clone, outs["base"], t, reference)
        cand = harness.ranking_at(cand_src, clone, outs["candidate"], t, reference)
        if "error" in base or "error" in cand:
            rows.append({"cutoff": t, "error": ("base: " + base["error"]) if "error" in base else ("candidate: " + cand["error"])})
            continue
        row = {"cutoff": t, **paired(base, cand, outcome)}
        if t in declared:
            row["declared"] = paired(base, cand, declared[t])
        rows.append(row)
    return rows


def _num(x) -> str:
    return "-" if x is None else f"{float(x):.2f}"


def _p(x) -> str:
    return "-" if x is None else f"{float(x):.4f}"


def markdown(base: str, cand: str, sets: str, rows: dict, result: dict) -> str:
    """The decision as Markdown, its table read under the outcome that decided (result["outcome"]), then
    both outcomes side by side when the result carries them."""
    raw, rows = rows, under(rows, result.get("outcome", outcomes.DEFAULT))
    lines = [f"### {cand} against {base}, {sets}", "",
             "| repository | cut-offs | baseline hits | candidate hits | mean effect | saturated | pool moved | failed |",
             "|---|---:|---:|---:|---:|---:|---:|---|"]
    for name in sorted(rows):
        ok = [x for x in rows[name] if "d" in x]
        errors = [x["error"] for x in rows[name] if "error" in x]
        moved = sum(bool(x.get("pool_added") or x.get("pool_dropped")) for x in ok)
        lines.append(f"| {name} | {len(ok)} | {sum(x['base_hits'] for x in ok)} | {sum(x['cand_hits'] for x in ok)} | "
                     f"{_num(result['effects'].get(name))} | {sum(x['saturated'] for x in ok)} | {moved} | "
                     f"{(str(len(errors)) + ': ' + errors[0][:80].replace('|', '/')) if errors else ''} |")
    n = len(result["effects"])
    lines += ["", f"Mean effect over {n} {'repository' if n == 1 else 'repositories'}: {_num(result['mean'])} top-fifteen hits per "
              f"cut-off; wins, losses and ties over repositories {result['wins']}/{result['losses']}/{result['ties']}; "
              f"exact one-sided sign-flip p = {_p(result['p'])}. Verdict: **{verdict(result)}** "
              f"(positive mean and p < {ALPHA}, with nothing failed)."]
    if result.get("failed"):
        lines += ["", "Incomplete: " + ", ".join(f"{r} ({k} failed)" for r, k in sorted(result["failed"].items()))
                  + ". A failure is not dropped: rerun once it is fixed."]
    lines += ["", f"For information, without the saturated cut-offs: mean {_num(result['without_saturated']['mean'])}, "
              f"p = {_p(result['without_saturated']['p'])}. It does not decide. \"Pool moved\" counts the cut-offs where the "
              "candidate's own pool differs from the baseline's; both were scored on the baseline's."]
    if result.get("unsnored") is not None:
        lines += ["", snoring_table(result, result["unsnored"])]
    if result.get("outcomes"):
        lines += ["", outcomes_table(raw, result["outcomes"], result.get("outcome", outcomes.DEFAULT), result.get("conventions") or {})]
    return "\n".join(lines) + "\n"


def outcomes_table(rows: dict, results: dict, deciding: str, conventions: dict) -> str:
    """Both definitions of a fix side by side (measure.outcome), per repository, with the decision under
    each; the one --outcome named decides and the other is information. A repository that declares no
    convention scores the same under both."""
    def hits(name, outcome):
        ok = [x for x in under({name: rows[name]}, outcome)[name] if "d" in x]
        return sum(x["base_hits"] for x in ok), sum(x["cand_hits"] for x in ok)
    lines = [f"Fix locality by both definitions of a fix (measure.outcome); **{deciding}** decides, the other is information:", "",
             "| repository | convention | baseline hits, current | candidate hits, current | effect, current | "
             "baseline hits, declared | candidate hits, declared | effect, declared |", "|---|---|---:|---:|---:|---:|---:|---:|"]
    for name in sorted(rows):
        (bc, cc), (bd, cd) = hits(name, "current"), hits(name, "declared")
        lines.append(f"| {name} | {outcomes.describe(conventions.get(name)) if name in conventions else '-'} | {bc} | {cc} | "
                     f"{_num(results['current']['effects'].get(name))} | {bd} | {cd} | {_num(results['declared']['effects'].get(name))} |")
    lines.append("")
    for o in outcomes.OUTCOMES:
        r = results[o]
        lines.append(f"- {o}: mean effect {_num(r['mean'])}, wins, losses and ties {r['wins']}/{r['losses']}/{r['ties']}, "
                     f"p = {_p(r['p'])}, **{verdict(r)}**{' (decides)' if o == deciding else ' (information)'}")
    return "\n".join(lines)


def snoring_table(result: dict, quiet: dict) -> str:
    """The decision with every cut-off beside the same without the snore-exposed ones, for information."""
    cut = sorted({t for ts in quiet["dropped"].values() for t in ts})
    n = sum(len(ts) for ts in quiet["dropped"].values())

    def wlt(x):
        return f"{sum(e > 0 for e in x['effects'].values())}/{sum(e < 0 for e in x['effects'].values())}/{sum(e == 0 for e in x['effects'].values())}"
    rows = ["| | every cut-off (decides) | without the snore-exposed cut-offs (reported only) |", "|---|---:|---:|",
            f"| cut-offs left out | 0 | {n}{(' (' + ', '.join(cut) + ')') if cut else ''} |",
            f"| mean effect | {_num(result['mean'])} | {_num(quiet['mean'])} |",
            f"| wins/losses/ties | {wlt(result)} | {wlt(quiet)} |",
            f"| sign-flip p | {_p(result['p'])} | {_p(quiet['p'])} |",
            f"| verdict | {verdict(result)} | {verdict(quiet)} |"]
    return ("Snoring, for information: a cut-off whose horizon and one more run past its labels' end may hold bugs not yet "
            "labelled. The verdict is the left column's; the right one never decides, and nothing is dropped.\n\n" + "\n".join(rows))


def _jsonable(result: dict) -> dict:
    """The result for --json: its Fractions as floats. Both outcomes' results are written beside it, not in it."""
    def part(x):
        return {**x, "effects": {k: float(v) for k, v in x["effects"].items()}, "mean": None if x["mean"] is None else float(x["mean"])}
    result = {k: v for k, v in result.items() if k != "outcomes"}
    out = {**part(result), "without_saturated": part(result["without_saturated"]), "verdict": verdict(result)}
    if result.get("unsnored") is not None:
        quiet = result["unsnored"]
        out["unsnored"] = {**part(quiet), "without_saturated": part(quiet["without_saturated"]), "verdict": verdict(quiet)}
    return out


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="python -m gitmole.measure.candidate", description=__doc__.split("\n\n")[0])
    p.add_argument("base")
    p.add_argument("candidate")
    p.add_argument("--sets", default=EFFECTIVENESS_SETS)
    p.add_argument("--only", action="append", default=[])
    p.add_argument("--holdout", action="store_true", help="read the holdout: needs --approved")
    p.add_argument("--approved", default="", help="who agreed to this holdout read, and when")
    p.add_argument("--again", action="store_true", help="a second holdout read of the same candidate, counted as one")
    p.add_argument("--outcome", choices=outcomes.OUTCOMES, default=outcomes.DEFAULT,
                   help="the definition of a fix that decides (measure.outcome); both are printed")
    p.add_argument("--json", help="write the rows and the result here")
    args = p.parse_args(argv)
    if args.holdout and args.outcome != outcomes.DEFAULT:
        print("candidate: the holdout is scored on its labels, which no definition of a fix decides: --outcome is refused with --holdout", file=sys.stderr)
        return 2
    manifest = corpus.load()
    root = corpus.workspace()
    sets = "holdout" if args.holdout else args.sets
    labels_dir = os.environ.get("GITMOLE_LABELS_DIR") or os.path.join(root, "labels")
    entries = [e for e in corpus.entries(manifest, sets.split(",")) if not e.get("fixture") and (not args.only or e["name"] in args.only)]
    try:
        commits = resolve(args.base), resolve(args.candidate)
    except ValueError as e:
        print(f"candidate: {e}", file=sys.stderr)
        return 2
    if args.holdout:
        problems = holdout_preflight(args, entries, root, labels_dir)
        if problems:
            print("candidate: the holdout is not read:\n  " + "\n  ".join(problems), file=sys.stderr)
            return 2
    base_src, cand_src = harness.source(args.base, root), harness.source(args.candidate, root)
    if args.holdout:
        try:   # logged once everything is in place and before anything is read: a crash midway still spent it
            log_holdout_read(HOLDOUT_READS, args.base, args.candidate, *commits, args.approved, args.again, sets)
        except (ValueError, SpentRead) as e:
            print(f"candidate: {e}", file=sys.stderr)
            return 2
    rows, conventions = {}, {}
    for entry in entries:
        print(f"candidate: {entry['name']}", file=sys.stderr, flush=True)
        rows[entry["name"]] = compare_entry(base_src, cand_src, entry, root, manifest["reference_date"], labels_dir, conventions)
    both = {o: decide(rows, o) for o in outcomes.OUTCOMES}
    result = dict(both[args.outcome])
    ends = {e["name"]: e["end"] for e in entries if e.get("labels") and e.get("end")}
    if ends:   # labels that stop can snore (the holdout's); fix locality cannot, and gets no such column
        result["unsnored"] = unsnored(under(rows, args.outcome), ends)
    result.update(outcome=args.outcome, outcomes=both, conventions=conventions)
    print(markdown(args.base, args.candidate, sets, rows, result))
    dirty = "worktree" in (args.base, args.candidate) and bool(subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=no"], cwd=corpus.ROOT, capture_output=True, text=True).stdout.strip())
    if args.json:
        with open(args.json, "w", encoding="utf-8") as fh:
            json.dump({"base": args.base, "candidate": args.candidate, "commits": list(commits), "sets": sets,
                       "worktree_dirty": dirty,   # a working tree is HEAD plus changes no commit names
                       "outcome": args.outcome, "conventions": conventions,
                       "rows": rows, "result": _jsonable(result),
                       "outcomes": {o: _jsonable(r) for o, r in both.items()}}, fh, indent=2, sort_keys=True)
    return 0 if verdict(result) in ("better", "not shown") else 1   # incomplete or no data: nothing was decided


if __name__ == "__main__":
    sys.exit(main())

"""Heuristics that turn a loaded report into a short list of flagged findings. A rule that rests on a paper
carries the short citation in its rule dict's `ref` (see REFS); docs/references.md has the full entries."""
from __future__ import annotations

import re

from . import classify, coupling, filetypes, hotspots, knowledge, leaks, licences, loss, maat, osps, structure, textfmt, trend

SEVERITIES = ["critical", "warning", "info"]

PLACEHOLDER_NAMES = {"your name", "unknown", "root", "user"}
PLACEHOLDER_EMAIL = re.compile(r"(@example\.(com|org|net)$|^you@|^user@|^root@|@localhost$)")


# The paper a rule rests on, as the short citation the rule dict carries in `ref`; the full entries are in
# docs/references.md. A rule that is gitmole's own heuristic has none.
REFS = {"minor_contributors": "Bird et al., FSE 2011", "tangled_commits": "Herzig and Zeller, MSR 2013",
        "brain_methods": "Lanza and Marinescu, 2006", "tight_coupling": "Gall, Hajek and Jazayeri, ICSM 1998",
        "trojan_source": "Boucher and Anderson, USENIX Security 2023",
        "debt_in_hotspots": "Maldonado and Shihab, MTD 2015", "hidden_coupling": "Ajienka and Capiluppi, JSS 2017",
        "unreferenced_files": "Romano et al., TSE 2020", "signoff_by_co_author": "Linux kernel, Documentation/process/coding-assistants.rst",
        "deep_nesting": "SonarSource cognitive complexity; CodeScene code health",
        "sweeping_commits": "Kolassa, Riehle and Salim, SOFSEM 2013", "import_cycles": "Oyetoyan et al., SANER 2015"}


def _f(severity: str, title: str, statement: str, advice: str, rule: dict, evidence: dict) -> dict:
    """A finding: the facts, then the next step. `detail` is the two joined for anyone reading the
    JSON; `advice` says which part is the step so the report can show it on its own line. `rule` is
    the rule's id and the thresholds it fired on, `evidence` the numbers they were compared with:
    between them a reader of the JSON can check the finding without reading this file."""
    if rule.get("id") in REFS and "ref" not in rule:
        rule = {**rule, "ref": REFS[rule["id"]]}
    if rule.get("id") in osps.RULE_CONTROLS and "osps" not in rule:   # the OSPS Baseline controls it gives evidence for
        rule = {**rule, "osps": list(osps.RULE_CONTROLS[rule["id"]])}
    return {"severity": severity, "title": title, "detail": f"{statement.rstrip()} {advice}", "advice": advice,
            "rule": rule, "evidence": evidence}


def _pct(part, whole) -> str:
    return f"{round(100 * part / whole)}%" if whole else "0%"


_SIBILANT = re.compile(r"(s|x|z|ch|sh)$", re.I)   # address -> addresses, box -> boxes, branch -> branches


def _plural(n: int, word: str) -> str:
    """A count and its noun, agreeing. A noun already ending in a sibilant takes -es: appending -s to
    "IPv4 address" is what gave ghidra's report "2 IPv4 addresss"."""
    if n == 1:
        return f"{n} {word}"
    return f"{n} {word}es" if _SIBILANT.search(word) else f"{n} {word}s"


def _secret_statement(groups: list) -> str:
    """'N distinct values in M places: rule in file (commits), ...' with at most three values named.

    A value found in an unreachable blob belongs to no commit, so its commit is the empty string. Those
    are dropped rather than joined, and a value with no commit left names no parenthesis at all: react's
    one critical finding read "in (unreachable blob 00db21063ea1) ()", and django's "(, d61f33f and 6
    more)" with the empty string still in the list. Two distinct values can also be the same rule in the
    same blob, which rendered as the same words twice with nothing to tell them apart; identical entries
    are counted instead."""
    def one(g):
        others = len(g["files"]) - 1
        where = g["files"][0] + (f" and {_plural(others, 'other file')}" if others else "")
        named = [c for c in g["commits"] if c]     # an unreachable blob is in no commit
        commits = ", ".join(named[:2]) + (f" and {len(named) - 2} more" if len(named) > 2 else "")
        return f"{g['rule']} in {where}" + (f" ({commits})" if commits else "")
    places = sum(g["places"] for g in groups)
    counts = {}                                    # insertion order, so the first three stay in their order
    for text in (one(g) for g in groups[:3]):
        counts[text] = counts.get(text, 0) + 1
    sample = "; ".join(f"{n} values of {text}" if n > 1 else text for text, n in counts.items())
    more = f" and {len(groups) - 3} more" if len(groups) > 3 else ""
    return f"{_plural(len(groups), 'distinct value')} in {_plural(places, 'place')}: {sample}{more}."


def _secret_evidence(groups: list) -> dict:
    return {"values": len(groups), "places": sum(g["places"] for g in groups), "files": sorted({f for g in groups for f in g["files"]})[:10]}


def secrets_found(report: dict) -> list:
    """Secrets grouped by value. A value anywhere in source is critical; one that only ever appears in
    test files (fixtures, saved pages), example or rule directories (language samples, a scanner's own
    rules) or documentation (templates) is a warning, so a critical gate does not trip on test data or a
    planning document. Version strings, template markers and key blocks without key material were
    flagged as placeholders and are not a finding."""
    groups = leaks.group(report.get("secrets") or [])

    vendored, generated = filetypes.vendor_dirs(report), _generated(report)

    def in_source(g):   # a copy in an unreachable blob has no path: the value's located copies say where it lives
        located = [f for f in g["files"] if not f.startswith(leaks.UNREACHABLE)] or g["files"]
        return any(not (filetypes.is_test_path(f) or filetypes.is_doc_path(f) or filetypes.is_sample_path(f) or filetypes.is_vendored(f, vendored)
                        or filetypes.is_mock_path(f) or filetypes.is_tooling_path(f) or f in generated)
                   for f in located)

    def possible(g):   # only the scanner's generic rules found it, and it graded every sighting low
        return g["rule"].startswith("generic-") and g.get("confidence") == "low"
    source = [g for g in groups if in_source(g) and not possible(g)]
    maybe = [g for g in groups if in_source(g) and possible(g)]
    aside = [g for g in groups if not in_source(g)]
    ignore = "Add the fingerprint of any false positive from secrets.json to .betterleaksignore in the repository."
    out = []
    if source:
        out.append(_f("critical", f"{len(source)} secret(s) in history", _secret_statement(source),
                      f"Rotate them; deleting the file does not remove them from git. {ignore}",
                      rule={"id": "secrets_in_source", "scanner": "betterleaks", "placeholders": "left out"}, evidence=_secret_evidence(source)))
    if maybe:
        out.append(_f("info", f"{len(maybe)} possible secret(s) in source", _secret_statement(maybe),
                      f"Look at each: the scanner's generic rules found them and graded every sighting low, which is how an ordinary assignment "
                      f"or a hash reads as well as a key. {ignore}",
                      rule={"id": "secrets_possible", "scanner": "betterleaks", "confidence": "low", "rules": "generic-*"}, evidence=_secret_evidence(maybe)))
    if aside:
        out.append(_f("warning", f"{len(aside)} secret(s) only in test, example, vendored, generated or documentation files", _secret_statement(aside),
                      f"Confirm they are fixtures or templates, not live keys. {ignore}",
                      rule={"id": "secrets_aside", "scanner": "betterleaks", "placeholders": "left out"}, evidence=_secret_evidence(aside)))
    return out


def credential_files(report: dict) -> list:
    """Tracked files whose name says they hold a login (.env.production, .netrc, id_rsa): a finding by the
    name alone, whatever betterleaks made of the contents. The run lists them in meta.json."""
    paths = (report.get("meta") or {}).get("credential_files") or []
    if not paths:
        return []
    shown = ", ".join(paths[:5]) + (f" and {len(paths) - 5} more" if len(paths) > 5 else "")
    return [_f("warning", "Credential-shaped files tracked", f"{_plural(len(paths), 'credential-shaped file')} tracked: {shown}.",
               "Move the values to the environment, git rm the files and add them to .gitignore; a template belongs in .env.example.",
               rule={"id": "credential_files", "by": "file name"}, evidence={"count": len(paths), "files": paths[:10]})]


def _all_identities(report: dict):
    """Every identity row plus its aliases, flattened."""
    for i in report["meta"].get("identities") or []:
        yield i
        for a in i.get("aliases") or []:
            yield a


def placeholder_identity(report: dict, min_share: float = 0.01) -> list:
    """A placeholder name or mailbox with a real share of the commits. One stray commit in thousands
    is not worth the panel space."""
    identities = report["meta"].get("identities") or []
    total = sum(i["commits"] for i in identities)

    def is_placeholder(i):
        return i["name"].strip().lower() in PLACEHOLDER_NAMES or bool(PLACEHOLDER_EMAIL.search(i["email"].lower()))
    real = max((i for i in identities if not is_placeholder(i)), key=lambda i: i["commits"], default=None)
    out = []
    for i in _all_identities(report):
        if total and i["commits"] / total < min_share:
            continue
        if is_placeholder(i):
            # the busiest real identity is the likely owner; the line is offered, never applied
            advice = (f"Set user.name and user.email. If those commits are {real['name']}'s, add to .mailmap: "
                      f"{real['name']} <{real['email']}> {i['name']} <{i['email']}>; the people, bus factor and "
                      f"knowledge findings then describe one person." if real
                      else "Set user.name and user.email; consider a .mailmap for history.")
            out.append(_f("warning", "Unconfigured git identity",
                          f"\"{i['name']} <{i['email']}>\" made {_plural(i['commits'], 'commit')} ({_pct(i['commits'], total)}).", advice,
                          rule={"id": "placeholder_identity", "min_share": min_share},
                          evidence={"name": i["name"], "email": i["email"], "commits": i["commits"], "total_commits": total}))
    return out


def _source_ownership(report: dict) -> list:
    """Ownership rows for source files. Test files and vendored trees are left out of every rule that
    names a next step: owning the tests is not the knowledge risk, and whoever imported vendor/ did
    not write it. The default tables leave test files out too."""
    vendored = filetypes.vendor_dirs(report)
    return [r for r in report.get("ownership") or [] if not (filetypes.is_test_path(r["entity"]) or filetypes.is_vendored(r["entity"], vendored))]


def _present_areas(report: dict, rows: list, build=knowledge.areas) -> list:
    """Areas built from the ownership rows of directories that still exist, then only those areas that
    exist themselves: a directory the history knows but HEAD does not (the layout before a move to
    src/ or crates/) is nowhere to pair anyone on. `build` is knowledge.areas or a wrapper of it."""
    tree = _tree(report)
    return [a for a in build(knowledge.present_rows(rows, tree)) if knowledge.in_tree(a["area"], tree)]


def bus_factor(report: dict, threshold: float = 0.7, min_lines: int = 200) -> list:
    """One author owns most of the surviving code (whole history). The areas named in the advice
    come from lines added, which `--since` windows, so the advice says so when it applies."""
    shares = report.get("theseus_authors") or {}
    total = sum(shares.values())
    if not total:
        return []
    name, lines = max(shares.items(), key=lambda kv: kv[1])
    if lines / total <= threshold:
        return []
    theirs = []
    for a in _present_areas(report, _source_ownership(report)):
        owned = dict(a["owners"]).get(name, 0)
        if a["lines"] >= min_lines and owned / a["lines"] >= 0.8:
            theirs.append((a["area"], round(100 * owned / a["lines"])))
    if theirs:
        areas = " and ".join(t[0] for t in theirs[:2])
        shares_ = " and ".join(f"{t[1]}%" for t in theirs[:2])
        since = report["meta"].get("since")
        advice = (f"Pair someone with {name} on {areas} first; {'they are' if len(theirs) > 1 else 'it is'} {shares_} theirs"
                  f"{f' since {since}' if since else ''}.")
    else:
        advice = f"Pair someone with {name} before they are unavailable."
    return [_f("warning", "Bus factor of one", f"{name} wrote {_pct(lines, total)} of the code that survives today.", advice,
               rule={"id": "bus_factor", "threshold": threshold, "min_lines": min_lines},
               evidence={"author": name, "lines": lines, "total_lines": total, "areas": [{"area": a, "share_pct": s} for a, s in theirs[:10]]})]


def _sizer_advice(row: dict) -> str:
    """The remedy for one git-sizer row, keyed on the loader's "section: metric" name. Big blobs
    want LFS, many refs want pruning, a wide tree wants splitting, a big checkout wants a sparse
    checkout; everything else that grows is history, and a shallow clone is the answer to that."""
    section, _, metric = row["name"].partition(": ")
    if section == "Blobs" and metric in ("Maximum size", "Total size"):
        return "Move large files to Git LFS or rewrite them out of history."
    if section in ("References", "Annotated tags"):
        return "Consider pruning old branches and tags."
    if section == "Biggest checkouts":
        return "Consider a sparse checkout for CI; the tree is the cost."
    if section == "Trees" and metric == "Maximum entries":
        where = row.get("ref") or "the widest directory"
        return f"Split {where} into subdirectories; a directory that wide slows every checkout and diff."
    if section == "Commits" and metric in ("Maximum size", "Maximum parents"):
        return "Look at that commit; oversized commits are usually imports or octopus merges."
    return "Consider a shallow clone for CI; the history is the cost."


def _tree(report: dict) -> dict:
    """The files at HEAD, from scc, or {} when the run has no size listing to judge by."""
    return (report.get("size") or {}).get("files") or {}


def sizer_concerns(report: dict) -> list:
    tree = _tree(report)
    out = []
    for row in report.get("sizer") or []:
        sev = "warning" if row["concern"] >= 2 else "info"
        where = f" at {row['ref']}" if row.get("ref") else ""
        advice = _sizer_advice(row)
        if row.get("ref") and tree and row["name"].startswith("Blobs: ") and row["ref"] not in tree:
            where += ", no longer in the tree"   # deleting it did not shrink the clone
            advice = "It is already gone from the tree; a history rewrite is only worth it for clone size."
        out.append(_f(sev, "Repo health", f"{row['name']} is {row['value']}{where}. git-sizer level of concern {row['concern']}.", advice,
                      rule={"id": "repo_health", "source": "git-sizer", "warning_at_concern": 2},
                      evidence={"metric": row["name"], "value": row["value"], "concern": row["concern"], "ref": row.get("ref") or None}))
    return out


def sweeping_commits(report: dict) -> list:
    """The commits the change analysis left out as sweeps (a formatter run, a rename across the tree:
    over the repository's 99th percentile of files touched, with as many lines out as in) that the
    repository has not declared in .git-blame-ignore-revs. Declaring them makes git blame and GitHub
    skip them too, which is the repository's own mechanism for exactly this."""
    act = report.get("activity") or {}
    swept = [c for c in act.get("sweeping") or [] if not c.get("declared")]
    if not swept:
        return []
    declared = act.get("ignored_revs") or 0

    def one(c):
        subject = f", {textfmt.cut(c['subject'], 60)}" if c.get("subject") else ""
        return f"{c['hash']} ({c['files']:,} files, {c['date']}{subject})"
    listed = "; ".join(one(c) for c in swept[:3]) + (f" and {len(swept) - 3} more" if len(swept) > 3 else "")
    least = min(c["files"] for c in swept)
    statement = (f"{_plural(len(swept), 'commit')} each touch {least:,} files or more and take out as many lines as they put in: {listed}. "
                 "They are left out of the churn, coupling and ownership counts.")
    named = textfmt.join_and([c["hash"] for c in swept[:3]]) + (" and the rest" if len(swept) > 3 else "")
    already = f"; {_plural(declared, 'commit')} {'is' if declared == 1 else 'are'} declared there already" if declared else ""
    return [_f("info", "Sweeping commits", statement, f"Add {named} to .git-blame-ignore-revs so git blame and GitHub skip them too{already}.",
               rule={"id": "sweeping_commits", "min_files": maat.SWEEP_MIN_FILES, "percentile": maat.SWEEP_PERCENTILE, "tolerance": maat.SWEEP_TOLERANCE},
               evidence={"declared": declared, "commits": [{"hash": c["hash"], "date": c["date"], "files": c["files"], "added": c.get("added"),
                                                             "deleted": c.get("deleted"), "subject": c.get("subject", "")} for c in swept[:10]]})]


def import_commits(report: dict) -> list:
    """Commits that brought a codebase in rather than changed it (maat.importing): add-only, a hundred
    files or more, a twentieth or more of every line the history adds. The change analysis leaves them out
    of ownership and authorship, and the code-age pass credits the lines they wrote to nobody, so the
    person who committed an import is not made the owner of everything in it. Said, since the knowledge
    tables then read differently from a plain git blame."""
    act = report.get("activity") or {}
    rows = act.get("imports") or []
    if not rows:
        return []
    total = act.get("added_total") or 0

    def one(c):
        share = f", {100 * c['added'] / total:.0f}% of every line the history adds" if total else ""
        return f"{c['hash']} by {c['author']} ({c['files']:,} files, {c['added']:,} lines{share}, {c['date']}, {textfmt.cut(c.get('subject', ''), 50)})"
    listed = "; ".join(one(c) for c in rows[:3])
    return [_f("info", "Imports left out of ownership",
               f"{_plural(len(rows), 'commit')} brought code in without changing any: {listed}. "
               "Ownership, authorship, the truck factor and the churn counts leave it out, and the code-age pass credits its surviving lines to nobody.",
               "Read the knowledge tables as who has worked on the code since; git blame still names the importer for every untouched line.",
               rule={"id": "import_commits", "share": maat.IMPORT_SHARE, "min_files": maat.IMPORT_MIN_FILES, "deleted": maat.IMPORT_DELETED},
               evidence={"commits": [{"hash": c["hash"], "date": c["date"], "author": c["author"], "files": c["files"], "added": c["added"],
                                      "deleted": c["deleted"], "subject": c.get("subject", "")} for c in rows[:10]], "added_total": total})]


def tangled_commits(report: dict, min_share: float = 0.02, min_count: int = 5) -> list:
    """Commits that do several things at once: ten or more files across four or more directories under
    a subject that lists several changes. Herzig and Zeller (MSR 2013) found tangled fixes mislabel a
    large share of the files they touch; the fix pool already leaves out fixes over the repository's
    99th percentile of lines. A habit is worth a line, one such commit in a hundred is not."""
    act = report.get("activity") or {}
    count, listed = act.get("tangled_commits") or 0, act.get("tangled") or []
    total = report["meta"].get("commits") or 0
    if not count or not total or count < min_count or count / total < min_share:
        return []
    big = act.get("oversized_fixes") or 0

    def one(c):
        return f"{c['hash']} ({c['files']:,} files, {c['dirs']} directories, {textfmt.cut(c['subject'], 70)})"
    sample = "; ".join(one(c) for c in listed[:3]) + (f" and {count - 3} more" if count > 3 and len(listed) >= 3 else "")
    aside = (f", so {big} {'fix' if big == 1 else 'fixes'} over the repository's 99th percentile of lines changed {'is' if big == 1 else 'are'} already left out of the fix counts"
             if big else "")
    return [_f("info", "Tangled commits",
               f"{count:,} of {total:,} commits ({_pct(count, total)}) touch {maat.TANGLED_FILES} or more files across {maat.TANGLED_DIRS} or more directories "
               f"under a subject that lists several changes: {sample}. A fix among them credits every file it touched{aside}.",
               "Split a change that does several things before merge; the fix history stays readable and the coupling stays real.",
               rule={"id": "tangled_commits", "min_files": maat.TANGLED_FILES, "min_dirs": maat.TANGLED_DIRS, "min_clauses": maat.TANGLED_CLAUSES,
                     "min_share": min_share, "min_count": min_count},
               evidence={"count": count, "commits": total, "oversized_fixes": big,
                         "sample": [{"hash": c["hash"], "date": c["date"], "files": c["files"], "dirs": c["dirs"], "subject": c["subject"]} for c in listed[:10]]})]


def minor_contributors(report: dict, min_minor: int = 5, warn_at: int = 10, top_n: int = 10) -> list:
    """Top hotspots with a crowd of minor contributors, people with under 5% of the file's commits
    each. Bird et al. ("Don't Touch My Code!", FSE 2011) found that count the strongest ownership
    predictor of defects, ahead of the sole owner, which is the knowledge risk the watch list names
    separately. Their section 7 finds most minor contributors are major contributors to a component
    the file depends on — expected traffic — so a minor contributor who is major on a file this one
    changes with (coupling.expected_minors) is not counted. Over the watch list's own pool: test,
    vendored, example and generated files are out."""
    minors = {a["entity"]: (a.get("minor", 0), a["n-authors"]) for a in report.get("authors") or []}
    if not any(m for m, _ in minors.values()):
        return []
    cls = classify.Classifier(report)
    top = [h["entity"] for h in hotspots.ranked(report) if h["code"] is not None and cls.reason(h["entity"]) is None][:top_n]
    expected = coupling.expected_minors(report, [f for f in top if f in minors and minors[f][0] >= min_minor])
    crowded = []
    for f in top:
        if f not in minors or minors[f][0] < min_minor:
            continue
        all_minor, n = minors[f]
        counted = all_minor - len(expected.get(f) or [])
        if counted >= min_minor:
            crowded.append((f, counted, n, all_minor))
    if not crowded:
        return []
    crowded.sort(key=lambda t: (-t[1], t[0]))
    owners = {}
    for r in report.get("ownership") or []:
        if r.get("added", 0) > (owners.get(r["entity"]) or ("", 0))[1]:
            owners[r["entity"]] = (r["author"], r["added"])
    sev = "warning" if crowded[0][1] >= warn_at else "info"
    listed = "; ".join(f"{f} ({m} of {n} authors)" for f, m, n, _ in crowded[:5]) + (f" and {len(crowded) - 5} more" if len(crowded) > 5 else "")
    excluded = sum(len(expected.get(f) or []) for f, _, _, _ in crowded)
    aside = (f" {excluded} of the minor contributors are major contributors to a file these change with and are not counted"
             " (Bird et al., section 7)." if excluded else "")
    first, owner = crowded[0][0], (owners.get(crowded[0][0]) or (None, 0))[0]
    who = f"Have {owner}, who wrote most of {first}, review changes to it from anyone else" if owner else f"Give {first} an owner who reviews every change to it"
    return [_f(sev, "Many minor contributors",
               f"{len(crowded)} of the top {len(top)} hotspots have {min_minor} or more contributors with under {round(100 * maat.MINOR_SHARE)}% of the file's commits each: {listed}.{aside}",
               f"{who}; Bird et al. found the count of minor contributors the strongest ownership predictor of defects.",
               rule={"id": "minor_contributors", "min_minor": min_minor, "warn_at": warn_at, "minor_share": maat.MINOR_SHARE, "top_n": top_n,
                     "expected_share": maat.MINOR_SHARE},
               evidence={"files": [{"file": f, "minor": m, "minor_all": a, "authors": n, "owner": (owners.get(f) or (None, 0))[0],
                                    "expected": (expected.get(f) or [])[:5]} for f, m, n, a in crowded[:10]]})]


def _both_specimens(a: str, b: str) -> bool:
    """Whether a coupled pair is two pieces of example or documentation material rather than code the
    repository runs. curl's docs/examples/imap-ssl.c and docs/examples/pop3-ssl.c show one technique for
    two protocols, and docs/examples/smtp-expn.c and smtp-vrfy.c two commands of one: the "shared format,
    duplicated rule or copied code" a coupling finding sends the reader to look for is what an example
    family is for, and merging them would make each one worse at its job. Both sides must be specimens;
    an example paired with the code it demonstrates is still reported, since that pair says the example
    tracks the API."""
    def specimen(p):
        return filetypes.is_sample_path(p) or filetypes.is_doc_path(p)
    return specimen(a) and specimen(b)


def tight_coupling(report: dict, min_degree: int = 80, min_revs: int = 5) -> list:
    """A file and its test are expected to change together, so pairs with a test file on either side are
    left out; so are pairs where either file is no longer in the tree, which are history, not a dependency,
    pairs of release plumbing (two version files, a manifest and its lock file), which are a release, and
    pairs that are both example or documentation material (_both_specimens)."""
    tree, vendored, derived = _tree(report), filetypes.vendor_dirs(report), _generated(report)
    pairs = [p for p in report.get("coupling") or [] if p["degree"] >= min_degree and p["average-revs"] >= min_revs
             and not (filetypes.is_test_path(p["entity"]) or filetypes.is_test_path(p["coupled"]))
             and not (p["entity"] in derived or p["coupled"] in derived)
             and not (filetypes.is_release_path(p["entity"]) and filetypes.is_release_path(p["coupled"]))
             and not _both_specimens(p["entity"], p["coupled"])
             and not filetypes.is_header_pair(p["entity"], p["coupled"])
             and not (filetypes.is_vendored(p["entity"], vendored) or filetypes.is_vendored(p["coupled"], vendored))
             and not (tree and (p["entity"] not in tree or p["coupled"] not in tree))]
    if not pairs:
        return []
    pairs.sort(key=lambda p: (-p["degree"], -p["average-revs"]))
    groups, pairs = coupling.clusters(pairs)
    rule = {"id": "tight_coupling", "min_degree": min_degree, "min_revs": min_revs}
    evidence = {"clusters": [{"dir": g["dir"], "files": g["files"], "pairs": g["pairs"], "degree": g["degree"]} for g in groups[:10]],
                "pairs": [{"a": p["entity"], "b": p["coupled"], "degree": p["degree"], "revs": p["average-revs"]} for p in pairs[:10]]}
    when = f"together at least {min_degree}% of the time"
    top = "; ".join(f"{p['entity']} + {p['coupled']} ({p['degree']}%)" for p in pairs[:3])
    if groups:
        # a directory of files that change as one is a generator or a shared layout, said once
        named = ", ".join(f"{g['files']} files in {g['dir']}" for g in groups[:2]) + (f" and {len(groups) - 2} more directories" if len(groups) > 2 else "")
        rest = (f", and {_plural(len(pairs), 'more pair')} {'does' if len(pairs) == 1 else 'do'}: {top}." if pairs
                else f", {_plural(sum(g['pairs'] for g in groups), 'pair')} in all.")
        first = groups[0]
        return [_f("info", "Files that always change together", f"{named} change {when}{rest}",
                   f"Review {first['dir']} first: {first['files']} files change as one; a generator or a shared layout links them.",
                   rule=rule, evidence=evidence)]
    count = f"{len(pairs)} pair changes" if len(pairs) == 1 else f"{len(pairs)} pairs change"
    first = pairs[0]
    return [_f("info", "Files that always change together",
               f"{count} {when}, e.g. {top}.",
               f"Review {first['entity']} and {first['coupled']} first: a shared layout or a hidden dependency links them.",
               rule=rule, evidence=evidence)]


def _months_apart(earlier: str, later: str) -> int:
    """Whole months from one ISO date to another."""
    y1, m1, d1 = (int(x) for x in earlier[:10].split("-"))
    y2, m2, d2 = (int(x) for x in later[:10].split("-"))
    return (y2 - y1) * 12 + (m2 - m1) - (1 if d2 < d1 else 0)


def _dormant_months(report: dict) -> int:
    """Months since the last commit, against the run's reference date (GITMOLE_NOW or today)."""
    import datetime as _dt
    last = report["meta"].get("last_date")
    if not last:
        return 0
    now = report["meta"].get("now") or _dt.date.today().isoformat()
    return max(0, _months_apart(last, now))


def dormant(report: dict, months: int = 12) -> list:
    """No commits for a year or more: everything else in the report describes a repository that has
    stopped, which is the first thing to know about it."""
    idle = _dormant_months(report)
    if idle < months:
        return []
    return [_f("warning", "Dormant repository", f"No commits since {report['meta']['last_date']}, {idle} months ago.",
               "The rest of the report describes a repository that has stopped; look for a successor or an archive notice before depending on it.",
               rule={"id": "dormant", "months": months}, evidence={"last_date": report["meta"]["last_date"], "idle_months": idle})]


def stale_files(report: dict, months: int = 12, share: float = 0.3) -> list:
    """Files still in the tree that nobody has touched. The age table covers every path in the
    history, so paths that were deleted are left out here; they are not dead code, they are gone.
    In a dormant repository every file is untouched because nothing is; the dormancy finding says so.

    Vendored and generated files are left out of both counts, as every other rule here leaves them out:
    a checked-in jquery.js has not changed in years because nobody maintains it here, and deleting it is
    not the advice. On django they were three of the ten files the finding named.

    The evidence names files, not only how many: a count cannot be checked against a later tree
    (measure/remediation.py NO_SUBJECTS), and a reader cannot act on one either. It names the largest
    untouched ones rather than the oldest, because the advice is about dead code and a file's lines are
    how much of it is at stake: on django the ten oldest are all empty `__init__.py` files, which nobody
    would delete and no later tree would show deleted. Ties break by age and then by path, so the
    same commit gives the same list."""
    if _dormant_months(report) >= months:
        return []
    age = report.get("age") or []
    tree = _tree(report)
    if tree:
        age = [a for a in age if a["entity"] in tree]
    vendored, derived = filetypes.vendor_dirs(report), _generated(report)
    age = [a for a in age if not (filetypes.is_vendored(a["entity"], vendored) or a["entity"] in derived)]
    if not age:
        return []
    stale = [a for a in age if a["age-months"] >= months]
    if len(stale) / len(age) <= share:
        return []
    return [_f("info", "A large share of files is untouched",
               f"{_pct(len(stale), len(age))} of files ({len(stale)}) have not changed in {months} months or more.",
               "Consider deleting what nobody has needed; dead code hides in untouched files.",
               rule={"id": "stale_files", "months": months, "share": share},
               evidence={"stale": len(stale), "files": len(age),
                         "untouched": [a["entity"] for a in sorted(
                             stale, key=lambda a: (-(tree.get(a["entity"], {}).get("code") or 0),
                                                   -a["age-months"], a["entity"]))[:10]]})]


def bug_magnets(report: dict, min_recent: int = 3, warn_at: int = 5) -> list:
    """Source files with a run of recent fix commits. Test files are left out: they change with every fix.
    So is release plumbing: a manifest touched by every fix release is not where the bug was."""
    plumb, derived = filetypes.plumbing_paths(report), _generated(report)
    hot = [f for f in report.get("fixes") or [] if f["recent-fixes"] >= min_recent
           and not (filetypes.is_test_path(f["entity"]) or filetypes.is_release(f["entity"], plumb) or f["entity"] in derived)]
    if not hot:
        return []
    hot.sort(key=lambda f: (-f["recent-fixes"], -f["n-fixes"], f["entity"]))
    sev = "warning" if hot[0]["recent-fixes"] >= warn_at else "info"
    listed = "; ".join(f"{f['entity']} ({f['recent-fixes']} recent, {f['n-fixes']} total)" for f in hot[:5])
    more = f" and {len(hot) - 5} more" if len(hot) > 5 else ""
    first = " and ".join(f["entity"] for f in hot[:2])
    return [_f(sev, "Bug magnets",
               f"{len(hot)} file(s) were fixed {min_recent}+ times in the last six months: {listed}{more}.",
               f"Review {first} before the next release; fixes keep landing there.",
               rule={"id": "bug_magnets", "min_recent": min_recent, "warn_at": warn_at, "window_months": 6, "fix": "the commit subject says so",
                     "oversized": "a fix over the repository's 99th percentile of lines changed credits nothing"},
               evidence={"count": len(hot), "files": [{"file": f["entity"], "recent_fixes": f["recent-fixes"], "fixes": f["n-fixes"]} for f in hot[:10]]})]


def reverts(report: dict, min_share: float = 0.05, min_count: int = 5, warn_share: float = 0.10) -> list:
    """Commits backed out with git revert. The file most often reverted is where a check before merge pays."""
    act = report.get("activity") or {}
    n = act.get("revert_commits") or 0
    total = report["meta"].get("commits") or 0
    if not n or not total or (n < min_count and n / total < min_share):
        return []
    rule = {"id": "reverts", "min_share": min_share, "min_count": min_count, "warn_share": warn_share}
    sev = "warning" if total and n / total >= warn_share else "info"
    reverted = act.get("reverted") or {}
    repeat = {p: c for p, c in reverted.items() if c >= 2}
    if reverted and not repeat:   # every reverted file was reverted once: no file keeps coming back
        return [_f(sev, "Reverts", f"{n} of {total} commits are reverts, spread over {len(reverted)} files, none backed out twice.",
                   "Look at why they were backed out; no single file keeps coming back.",
                   rule=rule, evidence={"reverts": n, "commits": total, "files": len(reverted), "reverted": {}})]
    reverted = repeat
    # source files lead: a test file at the top of the table would otherwise be the one named first
    items = sorted(reverted.items(), key=lambda kv: filetypes.is_test_path(kv[0]))[:3]
    parts = []
    for i, (p, c) in enumerate(items):
        if i == 0:
            parts.append(f"{p} was reverted {textfmt.times(c)}")
        else:
            parts.append(f"{p} {textfmt.times(c)}")
    listed = ", ".join(parts)
    statement = f"{n} of {total} commits are reverts" + (f"; {listed}." if listed else ".")
    source = [p for p in reverted if not filetypes.is_test_path(p)]
    if source:
        advice = f"Add a check before merge for {source[0]}; it is the file most often backed out."
    else:
        advice = "Look at why they were backed out; only test files were touched."
    return [_f(sev, "Reverts", statement, advice,
               rule=rule, evidence={"reverts": n, "commits": total, "reverted": dict(list(reverted.items())[:10])})]


def knowledge_islands(report: dict, min_lines: int = 200, min_share: float = 0.9, min_fraction: float = 0.01) -> list:
    """Areas of the tree written almost entirely by one person. Areas that no longer exist are left
    out, of the islands and of the total they are measured against; an island under `min_fraction`
    of that total (laravel's root files against its src/) is not knowledge worth pairing on."""
    areas = _present_areas(report, _source_ownership(report))
    total = sum(a["lines"] for a in areas)
    islands = [i for i in knowledge.islands(areas, min_lines=min_lines, min_share=min_share) if i["lines"] >= min_fraction * total]
    if not islands:
        return []
    covered = sum(i["lines"] for i in islands)
    sev = "warning" if total and covered / total > 0.5 else "info"
    listed = "; ".join(f"{i['area']} ({i['owner']} {i['share']}%)" for i in islands[:5])
    more = f" and {len(islands) - 5} more" if len(islands) > 5 else ""
    largest = max(islands, key=lambda i: i["lines"])
    return [_f(sev, "Knowledge islands",
               f"{len(islands)} area(s) with at least {min_lines} lines were written almost entirely by one person: {listed}{more}. "
               f"That is {_pct(covered, total)} of all lines added.",
               f"Pair someone with {largest['owner']} on {largest['area']} first; it is the largest at {largest['lines']:,} lines.",
               rule={"id": "knowledge_islands", "min_lines": min_lines, "min_share": min_share, "min_fraction": min_fraction},
               evidence={"covered_lines": covered, "total_lines": total,
                         "islands": [{"area": i["area"], "owner": i["owner"], "share_pct": i["share"], "lines": i["lines"]} for i in islands[:10]]})]


LIVE_MONTHS = 12


def _is_live(area: str, age_rows: list) -> bool:
    """Has anything in this area changed in the last year? `age` covers every path in the history,
    so an area whose files are all idle is knowledge about code nobody is touching."""
    for row in age_rows:
        if row["age-months"] >= LIVE_MONTHS:
            continue
        entity = row["entity"]
        in_area = "/" not in entity if area == knowledge.ROOT else entity.startswith(area)
        if in_area:
            return True
    return False


def _loss_totals(report: dict, names: set, source_rows: list) -> tuple[int, int, dict, str]:
    """(lost, total, by_person, basis): share of surviving code from the blame pass; when that did
    not run, share of lines added instead, with the basis clause that says so."""
    lost, total = loss.surviving(report, names)
    by_person = {n: v for n, v in (report.get("theseus_authors") or {}).items() if n in names}
    basis = "of the code that survives today"
    if not total:
        areas_all = loss.areas(source_rows, names)
        total = sum(a["lines"] for a in areas_all)
        lost = sum(a["lost"] for a in areas_all)
        by_person = {}
        for r in (r for r in source_rows if r["author"] in names):
            by_person[r["author"]] = by_person.get(r["author"], 0) + r["added"]
        basis = "of all lines added (from lines added, not a blame)"
    return lost, total, by_person, basis


def _loss_people(by_person: dict, total: int) -> str:
    """The "Bob (25%), Cat (2%) and 3 others (1%)" clause, or "N people at under 1% each" when
    nobody's individual share rounds to 1% or more."""
    people = sorted(by_person.items(), key=lambda kv: (-kv[1], kv[0]))
    named = [(n, v) for n, v in people if round(100 * v / total) >= 1][:3]
    if named:
        named_names = {n for n, _ in named}
        rest = [(n, v) for n, v in people if n not in named_names]
        listed = ", ".join(f"{n} ({_pct(v, total)})" for n, v in named)
        if rest:
            listed += f" and {_plural(len(rest), 'other')} ({_pct(sum(v for _, v in rest), total)})"
    else:
        listed = f"{len(people)} {'person' if len(people) == 1 else 'people'} at under 1% each"
    return listed


def _loss_areas(report: dict, names: set, source_rows: list) -> list:
    """Areas at 200+ lines where 80%+ of the surviving code is theirs, still in the tree, tagged live
    or not and sorted live-first: that is where the gap bites soonest."""
    theirs = [a for a in _present_areas(report, source_rows, build=lambda rows: loss.areas(rows, names))
              if a["lines"] >= 200 and a["lost_share"] >= 0.8]
    for a in theirs:
        a["live"] = _is_live(a["area"], report.get("age") or [])
    theirs.sort(key=lambda a: (not a["live"], -a["lines"], a["area"]))   # a live area first: that is where the gap bites
    return theirs


def knowledge_loss(report: dict, min_share: float = 0.10, warn_share: float = 0.30) -> list:
    """Code written by people who have stopped committing. Share of surviving code from the blame
    pass; when that did not run, share of lines added, and the statement says so."""
    months = report["meta"].get("gone_months", loss.DEFAULT_MONTHS)
    gone = loss.gone(report, months)
    if not gone:
        return []
    names = {g["name"] for g in gone}
    source_rows = _source_ownership(report)
    lost, total, by_person, basis = _loss_totals(report, names, source_rows)
    if not total or lost / total < min_share:
        return []
    sev = "warning" if lost / total >= warn_share else "info"
    listed = _loss_people(by_person, total)
    theirs = _loss_areas(report, names, source_rows)
    statement = (f"People with no commits since {loss.cutoff(report, months)} "
                 f"wrote {_pct(lost, total)} {basis}: {listed}.")
    if theirs:
        listed_areas = ", ".join(f"{a['area']} ({round(100 * a['lost_share'])}%)" for a in theirs[:3])
        more = f" and {len(theirs) - 3} more" if len(theirs) > 3 else ""
        statement += f" Areas mostly theirs: {listed_areas}{more}."
    if theirs and theirs[0]["live"]:
        advice = f"Pair someone on {theirs[0]['area']} first; nobody who wrote it is around to ask."
    else:   # nothing there has been touched in a year: pairing on it would be work nobody has asked for
        top = min(by_person, key=lambda n: (-by_person[n], n))
        advice = f"Pair someone with the people who worked with {top} before the rest of that knowledge goes."
    return [_f(sev, "Knowledge loss", statement, advice,
               rule={"id": "knowledge_loss", "gone_months": months, "min_share": min_share, "warn_share": warn_share},
               evidence={"lost_lines": lost, "total_lines": total, "basis": "surviving code" if basis.startswith("of the code") else "lines added",
                         "people": dict(sorted(by_person.items(), key=lambda kv: (-kv[1], kv[0]))[:10]),
                         "areas": [{"area": a["area"], "share_pct": round(100 * a["lost_share"]), "live": a["live"]} for a in theirs[:10]]})]


def _partial(report: dict, step: str, label: str) -> str:
    """A sentence when a step stopped part way, so what it measured is not the whole code."""
    status = (report["meta"].get(step) or {}).get("status")
    reason = {"timeout": "timed out", "failed": "failed"}.get(status)
    return f" {label} {reason} part way, so there may be more." if reason else ""


def _partial_functions(report: dict) -> str:
    return _partial(report, "functions", "Function metrics")


def brain_methods(report: dict, min_ccn: int = 15, min_lines: int = 100) -> list:
    """Functions that are both long and complex, in this repository's own source files: test files,
    example code, vendored code and generated files (amalgamations included) are left out, and so is
    a span the function step marked suspect, since a mis-parse that swallowed the next function is
    long and complex by construction. A warning when one sits in a hotspot."""
    generated, vendored = _generated(report), filetypes.vendor_dirs(report)
    big = [f for f in report.get("functions") or [] if f["ccn"] >= min_ccn and f["nloc"] >= min_lines and not f.get("suspect")
           and not (filetypes.is_test_path(f["file"]) or filetypes.is_sample_path(f["file"]) or filetypes.is_vendored(f["file"], vendored)
                    or f["file"] in generated)]
    if not big:
        return []
    big.sort(key=lambda f: (-f["ccn"], -f["nloc"], f["file"], f["function"], f["start"]))
    hot = hotspots.top(report)
    sev = "warning" if any(f["file"] in hot for f in big) else "info"
    listed = "; ".join(f"{f['function']} ({_place(f)}) complexity {f['ccn']}, {f['nloc']} lines, {_plural(f['params'], 'param')}" for f in big[:5])
    more = f" and {len(big) - 5} more" if len(big) > 5 else ""
    first = big[0]
    which = f"the anonymous function at {_place(first)}" if _anonymous(first) else f"{first['function']} in {first['file']}"
    return [_f(sev, "Brain methods",
               f"{len(big)} function(s) are both long and complex: {listed}{more}.{_partial_functions(report)}",
               f"Split {which} first, before the next change lands there.",
               rule={"id": "brain_methods", "min_ccn": min_ccn, "min_lines": min_lines},
               evidence={"count": len(big), "partial": bool(_partial_functions(report)),
                         "functions": [{"file": f["file"], "function": f["function"], "start": f["start"], "ccn": f["ccn"], "lines": f["nloc"], "params": f["params"]} for f in big[:10]]})]


ANONYMOUS = "(anonymous)"


def _anonymous(f: dict) -> bool:
    """A function lizard could not name: it goes by its start line's text (or "(anonymous)" in an
    older functions.csv), which is not a name to search for."""
    return f.get("anonymous", f["function"] == ANONYMOUS)


def _place(f: dict) -> str:
    """Where a function is: its file, or file:line when it has no name to find it by."""
    return f"{f['file']}:{f['start']}" if _anonymous(f) else f["file"]


def _generated(report: dict) -> set:
    """Build outputs: generated files and amalgamations (see hotspots.derived)."""
    return hotspots.derived(report)


def complexity_growth(report: dict, min_growers: int = 3, min_pct: int = trend.GROWTH_FLOOR, top_n: int = 10) -> list:
    """The top_n source hotspots whose complexity grew over the last year, from the trend samples.
    Test files are left out: a growing test file is not the problem the finding is about."""
    series = (report.get("trend") or {}).get("files") or {}
    last = report["meta"].get("last_date") or ""
    if not series or not last:
        return []
    top = [h["entity"] for h in hotspots.ranked(report)
           if h["code"] is not None and not filetypes.is_test_path(h["entity"])][:top_n]
    grown = []
    for path in top:
        change = trend.change_over_year(series.get(path) or [], last)
        if change.startswith("+") and int(change[1:-1]) >= min_pct:
            grown.append((path, int(change[1:-1])))
    if len(grown) < min_growers:
        return []
    sev = "warning" if top and grown[0][0] == top[0] else "info"
    listed = ", ".join(f"{p} (+{g}%)" for p, g in grown[:5]) + (f" and {len(grown) - 5} more" if len(grown) > 5 else "")
    first = grown[0]
    return [_f(sev, "Hotspots getting more complex",
               f"{len(grown)} of the {len(top)} top source hotspots grew by {min_pct}% or more in a year: {listed}.",
               f"Split {first[0]} before the next change; its complexity grew {first[1]}% in a year.",
               rule={"id": "complexity_growth", "min_growers": min_growers, "min_pct": min_pct, "top_n": top_n},
               evidence={"hotspots": len(top), "grown": [{"file": p, "growth_pct": g} for p, g in grown[:10]]})]


def duplication(report: dict, min_lines: int = 30) -> list:
    """Blocks of min_lines+ lines that appear more than once in this repository's own code. A block
    whose every copy sits in vendored or generated code is somebody else's, or a generator's, duplication."""
    dup = report.get("duplicates") or {}
    generated, vendored = _generated(report), filetypes.vendor_dirs(report)

    def own(b):
        return any(not (filetypes.is_vendored(p, vendored) or p in generated) for p, _, _ in b["places"])
    blocks = [b for b in dup.get("blocks") or [] if b["lines"] >= min_lines and own(b)]
    if not blocks:
        return []
    blocks.sort(key=lambda b: (-b["lines"], b["places"]))
    def place(b):
        return " and ".join(f"{p}:{start}" for p, start, _ in b["places"][:3])
    listed = "; ".join(f"{b['lines']} lines in {place(b)}" for b in blocks[:3])
    more = f" and {len(blocks) - 3} more" if len(blocks) > 3 else ""
    rate = f" Overall {dup['rate']}% of lines are duplicated." if dup.get("rate") is not None else ""
    first = blocks[0]
    files = list(dict.fromkeys(p for p, _, _ in first["places"]))   # each file once, in place order
    where = f"repeated within {files[0]}" if len(files) == 1 else f"shared by {files[0]} and {files[1]}"
    return [_f("info", "Duplicated code", f"{len(blocks)} block(s) of {min_lines}+ duplicated lines: {listed}{more}.{rate}{_partial(report, 'duplicates', 'Duplicate detection')}",
               f"Extract the {first['lines']}-line block {where} first.",
               rule={"id": "duplication", "min_lines": min_lines},
               evidence={"blocks": len(blocks), "rate_pct": dup.get("rate"), "partial": bool(_partial(report, "duplicates", "Duplicate detection")),
                         "largest": [{"lines": b["lines"], "places": [list(p) for p in b["places"][:3]]} for b in blocks[:3]]})]


CRITICAL_SCORE = 9.0   # CVSS: the band the advisories themselves call critical
MALICIOUS_PREFIX = "MAL-"   # OpenSSF malicious-packages records: the package is malicious, whatever its score
IGNORE_DEPS = "A vulnerability that does not apply to this code can be ignored in osv-scanner.toml at the repository root."


def _malicious_id(r: dict) -> str:
    return next((x for x in list(r.get("ids") or []) + list(r.get("aliases") or []) if str(x).startswith(MALICIOUS_PREFIX)), "")


def _vuln_statement(rows: list, sources: int) -> str:
    def one(r):
        ref = _malicious_id(r) or (r["aliases"][0] if r.get("aliases") else (r["ids"][0] if r.get("ids") else ""))
        score = f", {r['score']:.1f}" if r.get("score") is not None else (f", {r['severity']}" if r.get("severity") not in (None, "unknown") else "")
        if r.get("malicious"):
            score = ", malicious"
        fixed = f", fixed in {r['fixed']}" if r.get("fixed") else ", no fix yet"
        loaded = ", imported by no tracked source" if r.get("imported") is False else ""
        return f"{r['name']} {r['version']} ({ref}{score}{fixed}{loaded}) in {r['source']}"
    listed = "; ".join(one(r) for r in rows[:3])
    more = f" and {len(rows) - 3} more" if len(rows) > 3 else ""
    return f"{_plural(len(rows), 'vulnerable package')} in {_plural(sources, 'lock file')}: {listed}{more}."


def vulnerable_dependencies(report: dict) -> list:
    """Packages in the lock files with a known vulnerability, from the offline osv-scanner scan. A package
    a lock file in the source tree pins is critical when an advisory scores in the critical band, else a
    warning; one pinned only by a lock file under tests, examples, docs or vendored code is a note. The
    advice names the package to upgrade first and the version that fixes it."""
    deps = report.get("dependencies") or {}
    rows = deps.get("vulnerable") or []
    if not rows:
        return []
    vendored = filetypes.vendor_dirs(report)

    def aside(r):
        p = r.get("source") or ""
        return filetypes.is_test_path(p) or filetypes.is_sample_path(p) or filetypes.is_doc_path(p) or filetypes.is_vendored(p, vendored)
    source = [r for r in rows if not aside(r)]
    other = [r for r in rows if aside(r)]
    out = []
    for group, sev_default, title in ((source, "warning", "Vulnerable dependencies"),
                                      (other, "info", "Vulnerable dependencies only in test, example or vendored lock files")):
        if not group:
            continue
        worst = group[0]   # the rows come sorted malicious first, then by score, highest first
        critical = worst.get("malicious") or (worst.get("score") is not None and worst["score"] >= CRITICAL_SCORE)
        sev = "critical" if group is source and critical else sev_default
        sources = len({r["source"] for r in group})
        if worst.get("malicious"):
            target = f"Remove {worst['name']} {worst['version']} from {worst['source']} first; {_malicious_id(worst)} lists it as malicious, so no version fixes it."
        else:
            target = f"Upgrade {worst['name']} to {worst['fixed']} in {worst['source']} first" if worst.get("fixed") else f"Look at {worst['name']} in {worst['source']} first, which has no fixed version yet"
            target += f"; it scores {worst['score']:.1f}." if worst.get("score") is not None else "."
        out.append(_f(sev, title, _vuln_statement(group, sources), f"{target} {IGNORE_DEPS}",
                      rule={"id": "vulnerable_dependencies" if group is source else "vulnerable_dependencies_aside", "critical_score": CRITICAL_SCORE,
                            "malicious_prefix": MALICIOUS_PREFIX},
                      evidence={"lock_files": sources,
                                "packages": [{"name": r["name"], "version": r["version"], "source": r["source"], "score": r.get("score"),
                                              "fixed": r.get("fixed") or None, "ids": list(r.get("ids") or []),
                                              "aliases": list(r.get("aliases") or []), "malicious": bool(r.get("malicious")),
                                              "imported": r.get("imported", "unknown")} for r in group[:10]]}))
    return out


def _files_list(items: list, n: int = 3) -> str:
    return textfmt.join_and(items[:n]) + (f" and {len(items) - n} more" if len(items) > n else "")


def hygiene_findings(report: dict) -> list:
    """The hygiene checks (hygiene.py), one finding per rule, each naming the OpenSSF Scorecard check it
    stands in for without the GitHub API. Nothing for an output directory from before the step."""
    h = report.get("hygiene") or {}
    out = []
    for check in (_hygiene_actions, _hygiene_lockfiles, _hygiene_updates, _hygiene_presence, _hygiene_confusion, _hygiene_install, _hygiene_binaries, _hygiene_submodules, _hygiene_symlinks, _hygiene_trojan,
                  _hygiene_unused, _hygiene_licence, _hygiene_copyleft):
        check(h, out)
    return out


def _hygiene_actions(h: dict, out: list) -> None:

    a = h.get("actions") or {}
    if a.get("unpinned"):
        n, total = a.get("unpinned_count", len(a["unpinned"])), a.get("unpinned_count", len(a["unpinned"])) + (a.get("pinned") or 0)
        by_file = {}
        for u in a["unpinned"]:
            if u["uses"] not in by_file.setdefault(u["file"], []):
                by_file[u["file"]].append(u["uses"])
        listed = "; ".join(f"{textfmt.join_and(v[:3])}{' and more' if len(v) > 3 else ''} in {k}" for k, v in list(by_file.items())[:3])
        third = [u for u in a["unpinned"] if not u["uses"].split("/", 1)[0] in ("actions", "github")]
        first = (third or a["unpinned"])[0]["uses"]
        out.append(_f("warning", "Actions pinned by tag or branch",
                      f"{n} of {total} workflow steps use an action by tag or branch: {listed}. Whoever controls the action can move the tag to other code.",
                      f"Pin {first} to a full commit SHA first, with the tag in a comment; Dependabot and Renovate keep such pins current.",
                      rule={"id": "unpinned_actions", "scorecard": "Pinned-Dependencies"}, evidence={"count": n, "pinned": a.get("pinned", 0), "unpinned": a["unpinned"][:10]}))


def _hygiene_lockfiles(h: dict, out: list) -> None:
    lf = h.get("lockfiles") or {}
    if lf.get("drift"):
        d = lf["drift"]
        listed = "; ".join(f"{x['manifest']} changed on {x['manifest_date']}, after {x['lockfile']} last did on {x['lockfile_date']}" for x in d[:3])
        out.append(_f("warning", "Lock files behind their manifests", f"{_plural(lf.get('drift_count', len(d)), 'manifest')} changed after the lock file that pins it: {listed}.",
                      f"Regenerate {d[0]['lockfile']} and commit it with the manifest; a frozen install does not catch this.",
                      rule={"id": "lockfile_drift", "by": "last commit time"}, evidence={"count": lf.get("drift_count", len(d)), "drift": d[:10]}))
    if lf.get("missing"):
        m = lf["missing"]
        listed = "; ".join(f"{x['manifest']} has no {x['expected'][0]}" for x in m[:3])
        out.append(_f("info", "Manifests without a lock file", f"{listed}{' and ' + str(len(m) - 3) + ' more' if len(m) > 3 else ''}.",
                      "Commit the lock file so every install resolves the same versions, and the vulnerability scan can read them.",
                      rule={"id": "lockfile_missing", "scorecard": "Pinned-Dependencies"}, evidence={"missing": m[:10]}))


def _hygiene_updates(h: dict, out: list) -> None:
    up = h.get("updates") or {}
    if up.get("uncovered"):
        names = textfmt.join_and(up["uncovered"])
        if up.get("tool"):
            statement = f"dependabot.yml covers {textfmt.join_and(up['covered']) or 'nothing'} but not {names}, which have lock files here."
        else:
            statement = f"No dependency update tool is declared for {names}, which have lock files here."
        out.append(_f("info", "Dependencies without an update tool", statement,
                      f"Add a package-ecosystem entry for {up['uncovered'][0]} to .github/dependabot.yml, or a renovate.json.",
                      rule={"id": "dependency_updates", "scorecard": "Dependency-Update-Tool"}, evidence=dict(up)))


def _hygiene_presence(h: dict, out: list) -> None:
    pr = h.get("presence") or {}
    if pr and (not pr.get("license") or not pr.get("security_policy") or pr.get("codeowners_missing")):
        parts = []
        if not pr.get("license"):
            parts.append("No licence file at the root")
        if not pr.get("security_policy"):
            parts.append("no security policy (SECURITY.md)" if parts else "No security policy (SECURITY.md)")
        missing = pr.get("codeowners_missing") or []
        if missing:
            parts.append(f"{pr['codeowners']} names {_plural(len(missing), 'path')} that {'matches' if len(missing) == 1 else 'match'} no tracked file: {_files_list(missing)}")
        advice = ("Add a LICENSE; without one nobody may reuse the code." if not pr.get("license") else
                  "Add a SECURITY.md that says how to report a vulnerability privately." if not pr.get("security_policy") else
                  f"Remove or fix {missing[0]} in {pr['codeowners']}; a stale owner line assigns reviews to nothing.")
        out.append(_f("info", "Repository policy files", "; ".join(parts) + ".", advice,
                      rule={"id": "repo_policy", "scorecard": "Security-Policy, License"}, evidence=dict(pr)))


def _hygiene_confusion(h: dict, out: list) -> None:
    cf = h.get("confusion") or {}
    if cf.get("scoped_public") or cf.get("registries") or cf.get("pip_extra_index"):
        parts = [f"{x['package']} resolved from {x['registry']} in {x['lockfile']}, though .npmrc sends {x['package'].split('/')[0]} to {x['declared']}"
                 for x in (cf.get("scoped_public") or [])[:3]]
        parts += [f"{k} mixes {textfmt.join_and(v)}" for k, v in list((cf.get("registries") or {}).items())[:2]]
        if cf.get("pip_extra_index"):
            parts.append(f"{_files_list(cf['pip_extra_index'])} {'adds' if len(cf['pip_extra_index']) == 1 else 'add'} a pip extra-index-url, which lets a public package shadow a private one")
        sev = "warning" if cf.get("scoped_public") else "info"
        advice = (f"Reinstall {cf['scoped_public'][0]['package']} from {cf['scoped_public'][0]['declared']} and check the published copy is yours."
                  if cf.get("scoped_public") else "Use one index per package: --index-url for the private one, or a scoped registry, rather than an extra index.")
        out.append(_f(sev, "Dependency confusion shapes", "; ".join(parts) + ".", advice,
                      rule={"id": "dependency_confusion"}, evidence={"scoped_public": (cf.get("scoped_public") or [])[:10],
                                                                    "registries": cf.get("registries") or {}, "pip_extra_index": cf.get("pip_extra_index") or []}))


def _hygiene_install(h: dict, out: list) -> None:
    ins = h.get("install") or {}
    if ins.get("lockfile") or ins.get("manifests") or ins.get("setup_py"):
        parts = []
        if ins.get("lockfile"):
            n = ins.get("lockfile_count", len(ins["lockfile"]))
            parts.append(f"{n} locked package{'s' if n != 1 else ''} {'runs' if n == 1 else 'run'} an install script ({_files_list([x['package'] for x in ins['lockfile']])})")
        parts += [f"{m['file']} declares {textfmt.join_and(m['scripts'])}" for m in (ins.get("manifests") or [])[:3]]
        parts += [f"{s_['file']} calls {textfmt.join_and(s_['calls'])}" for s_ in (ins.get("setup_py") or [])[:3]]
        out.append(_f("info", "Code that runs at install", "; ".join(parts) + ".",
                      "Install with scripts disabled where the build allows it (npm ci --ignore-scripts) and review what the rest run.",
                      rule={"id": "install_scripts"}, evidence={k: ins.get(k) for k in ("lockfile", "manifests", "setup_py")}))


def _hygiene_binaries(h: dict, out: list) -> None:
    b = h.get("binaries") or {}
    exe = [x for x in b.get("executables") or [] if not _aside_path(x["file"])]
    if exe or b.get("lfs_unpointed"):
        parts = []
        if exe:
            named = [f"{x['file']} ({x['format']})" for x in exe]
            parts.append(f"{_plural(len(exe), 'executable')} committed: {_files_list(named)}")
        lfs = b.get("lfs_unpointed") or []
        if lfs:
            parts.append(f"{_files_list(lfs)} {'is' if len(lfs) == 1 else 'are'} committed as a blob though .gitattributes sends {'it' if len(lfs) == 1 else 'them'} to LFS")
        out.append(_f("warning" if exe else "info", "Committed binaries", "; ".join(parts) + ".",
                      f"Build {exe[0]['file']} in CI and publish it as a release asset instead; nobody can review a binary in a diff." if exe
                      else "Run git lfs migrate import for those paths, or drop the filter=lfs line that does not apply.",
                      rule={"id": "committed_binaries", "scorecard": "Binary-Artifacts"}, evidence={"executables": exe[:10], "lfs_unpointed": lfs[:10]}))


def _hygiene_submodules(h: dict, out: list) -> None:
    sm = h.get("submodules") or {}
    if sm.get("credentials") or sm.get("insecure") or sm.get("relative") or sm.get("floating"):
        parts = [f"{x['name']} carries credentials in its URL" for x in sm.get("credentials") or []]
        parts += [f"{x['name']} is fetched over {x['url'].split(':', 1)[0]}://" for x in sm.get("insecure") or []]
        parts += [f"{x['name']} has a relative URL ({x['url']})" for x in sm.get("relative") or []]
        parts += [f"{x['name']} follows branch {x['branch']}" for x in sm.get("floating") or []]
        sev = "critical" if sm.get("credentials") else "warning" if sm.get("insecure") else "info"
        advice = ("Rotate that credential and remove it from .gitmodules; history keeps it." if sm.get("credentials") else
                  "Switch those URLs to https://; a plain-text fetch can be rewritten on the way." if sm.get("insecure") else
                  "Use absolute https:// URLs and let the pinned commit, not a branch, say what is checked out.")
        out.append(_f(sev, "Submodule URLs", "; ".join(parts[:6]) + ".", advice, rule={"id": "submodule_urls"},
                      evidence={k: sm.get(k) or [] for k in ("credentials", "insecure", "relative", "floating")}))


def _hygiene_symlinks(h: dict, out: list) -> None:
    sl = h.get("symlinks") or {}
    if sl.get("outside") or sl.get("into_git"):
        parts = [f"{x['link']} points outside the tree ({x['target']})" for x in sl.get("outside") or []]
        parts += [f"{x['link']} points into .git ({x['target']})" for x in sl.get("into_git") or []]
        out.append(_f("warning", "Symlinks out of the tree", "; ".join(parts[:5]) + ".",
                      "Replace them with files or relative links inside the tree; a checkout that follows them reads or writes where it should not.",
                      rule={"id": "unsafe_symlinks"}, evidence={"outside": sl.get("outside") or [], "into_git": sl.get("into_git") or []}))


def _hygiene_trojan(h: dict, out: list) -> None:
    tj = h.get("trojan") or {}
    if tj.get("bidi") or tj.get("mixed_script"):
        parts = [f"{x['file']}:{x['line']} holds {x['char']}" for x in (tj.get("bidi") or [])[:3]]
        parts += [f"{x['token']} at {x['file']}:{x['line']} mixes {textfmt.join_and(x['scripts'])}" for x in (tj.get("mixed_script") or [])[:3]]
        sev = "critical" if tj.get("bidi") else "warning"
        first = (tj.get("bidi") or tj.get("mixed_script"))[0]
        out.append(_f(sev, "Trojan Source characters", "; ".join(parts) + ". Code can read one way in review and compile another.",
                      f"Look at {first['file']}:{first['line']} in a hex view first, and remove the character unless it is in a string that must hold it.",
                      rule={"id": "trojan_source", "cve": "CVE-2021-42574"},
                      evidence={"bidi": (tj.get("bidi") or [])[:10], "mixed_script": (tj.get("mixed_script") or [])[:10]}))


def _hygiene_unused(h: dict, out: list) -> None:
    im = h.get("imports") or {}
    rows = im.get("unused") or []
    if not rows:
        return
    by_manifest = {}
    for r in rows:
        by_manifest.setdefault(r["manifest"], []).append(r["package"])
    listed = "; ".join(f"{_files_list(v)} in {k}" for k, v in list(by_manifest.items())[:3])
    n = im.get("count", len(rows))
    first = rows[0]
    out.append(_f("info", "Declared dependencies nothing imports",
                  f"{n} runtime {'dependency is' if n == 1 else 'dependencies are'} declared and never imported by a tracked file, nor named in a script or configuration: {listed}.",
                  f"Remove {first['package']} from {first['manifest']} if nothing loads it at run time; an unused dependency is still installed, scanned and updated.",
                  rule={"id": "unused_dependencies", "reads": "package.json dependencies, go.mod direct requirements, Cargo.toml [dependencies]"},
                  evidence={"count": n, "manifests": im.get("manifests", 0), "unused": rows[:10]}))


def _hygiene_licence(h: dict, out: list) -> None:
    lic = h.get("licences") or {}
    declared = lic.get("declared") or []
    if lic.get("approved") is False or lic.get("mismatch"):
        named = "; ".join(f"{d['source']} declares {d['expression']}" for d in declared)
        parts = []
        if lic.get("mismatch"):
            parts.append(f"{named}, but {lic['files'][0]} is the {lic['file_licence']} text")
        if lic.get("approved") is False:
            parts.append(f"the declared licence ({textfmt.join_and([d['expression'] for d in declared] or [lic.get('file_licence') or ''])}) is not OSI- or FSF-approved")
        out.append(_f("warning" if lic.get("approved") is False else "info", "Project licence as declared", "; ".join(parts) + ".",
                      "Make the manifests and the licence file name the same licence; a packager reads the manifest, a lawyer the file." if lic.get("mismatch")
                      else "Say so plainly in the README if the project is source-available rather than open source.",
                      rule={"id": "project_licence", "reads": "root manifests and the licence file"},
                      evidence={"declared": declared, "file": (lic.get("files") or [None])[0], "file_licence": lic.get("file_licence"),
                                "approved": lic.get("approved"), "mismatch": bool(lic.get("mismatch"))}))


def _hygiene_copyleft(h: dict, out: list) -> None:
    lic = h.get("licences") or {}
    strong = lic.get("strong") or []
    if not strong or lic.get("project") != licences.PERMISSIVE:
        return
    n = lic.get("strong_count", len(strong))
    listed = _files_list([f"{d['name']} {d['version']} ({d['expression']})" for d in strong])
    own = textfmt.join_and(sorted({d["expression"] for d in lic.get("declared") or []} | ({lic["file_licence"]} if lic.get("file_licence") else set())))
    weak = f" {lic['weak_count']} more declare{'s' if lic.get('weak_count') == 1 else ''} weak copyleft (LGPL, MPL, EPL), which a dependency usually may." if lic.get("weak_count") else ""
    out.append(_f("warning", "Copyleft dependencies in a permissive project",
                  f"The project declares {own}, and {n} runtime {'dependency' if n == 1 else 'dependencies'} in {textfmt.join_and(sorted({d['lockfile'] for d in strong}))} "
                  f"{'declares' if n == 1 else 'declare'} a strong copyleft licence: {listed}.{weak} Declared, as the lock file records it, not read from the package's files.",
                  f"Check whether {strong[0]['name']} is distributed with the project; if it is, its licence terms reach the whole work.",
                  rule={"id": "copyleft_dependencies", "reads": "package-lock.json and composer.lock licence fields, runtime packages only"},
                  evidence={"project": own, "count": n, "weak": lic.get("weak_count", 0), "dependencies": lic.get("dependencies", 0), "strong": strong[:10]}))


def _aside_path(path: str) -> bool:
    return filetypes.is_test_path(path) or filetypes.is_sample_path(path) or filetypes.is_vendor_path(path)


STRUCTURE_LANGUAGES = {"python", "javascript", "typescript", "tsx", "c", "cpp", "ruby"}   # where the import graph resolves at all


def _structure(report: dict) -> dict:
    s = report.get("structure") or {}
    return s if s.get("status") == "run" else {}


def _scored_top(report: dict, n: int = 10) -> list:
    from . import classify
    cls = classify.Classifier(report)
    return [h["entity"] for h in hotspots.ranked(report) if h["code"] is not None and cls.reason(h["entity"]) is None][:n]


def debt_in_hotspots(report: dict, min_markers: int = 3, min_files: int = 2, top_n: int = 10) -> list:
    """Top hotspots whose own comments say they are unfinished: TODO, FIXME, XXX, HACK. Methods carrying
    such self-admitted debt were revised more than twice as often and carried about twice the bug ratio
    (Maldonado and Shihab's markers; the 2024 study of 774,051 Java methods), and most of it is never
    removed: a hot file its authors flagged is a reason no churn number gives."""
    s = _structure(report)
    if not s:
        return []
    files = s.get("files") or {}
    top = _scored_top(report, top_n)
    flagged = [(f, files[f]["debt"]) for f in top if (files.get(f) or {}).get("debt")]
    if not flagged or (max(n for _, n in flagged) < min_markers and len(flagged) < min_files):
        return []   # one marker in one hotspot is ordinary; three in one, or markers in two, is a pattern
    first = max(flagged, key=lambda t: t[1])[0]
    sample = (files[first].get("debt_sample") or [{}])[0]
    at = f", starting at line {sample['line']}" if sample.get("line") else ""
    listed = "; ".join(f"{f} ({n})" for f, n in flagged[:5]) + (f" and {len(flagged) - 5} more" if len(flagged) > 5 else "")
    return [_f("info", "Debt the authors flagged in hotspots",
               f"{len(flagged)} of the top {len(top)} hotspots carry TODO, FIXME, XXX or HACK comments: {listed}.",
               f"Resolve or ticket the markers in {first} first{at}; it changes often and its authors said it is unfinished.",
               rule={"id": "debt_in_hotspots", "markers": ["TODO", "FIXME", "XXX", "HACK"], "min_markers": min_markers, "top_n": top_n,
                     "ref": "Maldonado and Shihab, MTD 2015"},
               evidence={"files": [{"file": f, "markers": n} for f, n in flagged[:10]]})]


def _shape_files(report: dict, key: str) -> list:
    """[(file, shapes)] for this repository's own source files holding a shape: tests, examples,
    documentation, vendored and generated files left out, since a fixture or a sample may do on purpose
    what the source should not."""
    s = _structure(report)
    if not s:
        return []
    generated, vendored = _generated(report), filetypes.vendor_dirs(report)
    return [(p, v["shapes"]) for p, v in sorted((s.get("files") or {}).items()) if (v.get("shapes") or {}).get(key)
            and not (filetypes.is_test_path(p) or filetypes.is_sample_path(p) or filetypes.is_doc_path(p)
                     or filetypes.is_vendored(p, vendored) or p in generated)]


def swallowed_errors(report: dict, min_count: int = 5, top_n: int = 10) -> list:
    """Catch, except and rescue blocks that do nothing and say nothing: no statement, no comment. In
    Python only a bare `except:` or one catching Exception or BaseException counts, since `except
    KeyError: pass` is the language's idiom. A warning when one sits in a top hotspot, where an error
    that vanishes is the hardest to trace."""
    rows = _shape_files(report, "empty_catch")
    total = sum(sh.get("empty_catch_count", len(sh["empty_catch"])) for _, sh in rows)
    if total < min_count:
        return []
    rows.sort(key=lambda r: (-r[1].get("empty_catch_count", 0), r[0]))
    top = set(_scored_top(report, top_n))
    hot = [p for p, _ in rows if p in top]
    listed = _files_list([f"{p}:{sh['empty_catch'][0]}" + (f" and {sh['empty_catch_count'] - 1} more there" if sh.get("empty_catch_count", 1) > 1 else "") for p, sh in rows])
    bare = sum(sh.get("bare_except_count", 0) for _, sh in rows)
    first = hot[0] if hot else rows[0][0]
    return [_f("warning" if hot else "info", "Errors caught and dropped",
               f"{_plural(total, 'empty catch block')} in {_plural(len(rows), 'source file')}"
               + (f", {bare} of them a bare except" if bare else "") + f": {listed}."
               + (f" {textfmt.join_and(hot[:3])} {'is a top hotspot' if len(hot) == 1 else 'are top hotspots'}." if hot else ""),
               f"Log or rethrow in {first} first, or say in a comment why the error is ignored; an error dropped without a trace is the hardest kind to find.",
               rule={"id": "swallowed_errors", "min_count": min_count, "measure": "tree-sitter", "python": "bare, Exception or BaseException only"},
               evidence={"count": total, "bare_except": bare, "hotspots": hot[:10],
                         "files": [{"file": p, "start": sh["empty_catch"][0], "count": sh.get("empty_catch_count", 1)} for p, sh in rows[:10]]})]


def hardcoded_addresses(report: dict) -> list:
    """IPv4 addresses written into string literals in source files: a host that moves, or an environment
    wired into the code. Loopback, unspecified, broadcast, netmask-shaped, documentation-range (RFC 5737)
    and object-identifier-shaped values are not counted (structure.py)."""
    rows = _shape_files(report, "addresses")
    if not rows:
        return []
    total = sum(sh.get("addresses_count", len(sh["addresses"])) for _, sh in rows)
    places = [(p, a) for p, sh in rows for a in sh["addresses"]]
    listed = _files_list([f"{a['value']} at {p}:{a['line']}" for p, a in places])
    return [_f("info", "Addresses written into the code",
               f"{_plural(total, 'IPv4 address')} in string literals in {_plural(len(rows), 'source file')}: {listed}.",
               f"Move {places[0][1]['value']} in {places[0][0]} into configuration, or a name that DNS resolves; an address in code has to be edited and shipped to change.",
               rule={"id": "hardcoded_addresses", "measure": "tree-sitter", "left_out": "loopback, 0.0.0.0, broadcast, RFC 5737, x.x.x.0, first octet 0-2"},
               evidence={"count": total, "files": [{"file": p, "start": a["line"], "value": a["value"]} for p, a in places[:10]]})]


def commented_out_code(report: dict, min_lines: int = 10) -> list:
    """Source files with ten or more lines of code left in comments: blocks of line or block comments in
    which four lines in five read as statements and one starts right at the comment marker. Worked
    examples in prose and documentation comments are not counted. The history already keeps old code."""
    rows = [(p, sh) for p, sh in _shape_files(report, "commented_code") if sh["commented_code"] >= min_lines]
    if not rows:
        return []
    rows.sort(key=lambda r: (-r[1]["commented_code"], r[0]))
    listed = _files_list([f"{p} ({sh['commented_code']} lines from line {sh['commented_sample'][0]})" for p, sh in rows])
    first = rows[0]
    return [_f("info", "Code left in comments",
               f"{_plural(len(rows), 'source file')} {'holds' if len(rows) == 1 else 'hold'} {min_lines} or more lines of commented-out code: {listed}.",
               f"Delete the block at {first[0]}:{first[1]['commented_sample'][0]}; git keeps the old version, and a reader cannot tell whether it is meant to come back.",
               rule={"id": "commented_out_code", "min_lines": min_lines, "measure": "tree-sitter", "code_share": 0.8},
               evidence={"files": [{"file": p, "start": sh["commented_sample"][0], "lines": sh["commented_code"]} for p, sh in rows[:10]]})]


def deep_nesting(report: dict, min_nesting: int = 5, min_bumps: int = 3, top_n: int = 10) -> list:
    """Functions nested five levels or more, or with three or more separate chunks of nested logic (a
    bumpy road), in this repository's own source: CodeScene's nesting and bumpy-road factors, measured
    by tree-sitter in every language it parses, with Sonar's cognitive complexity beside them. A
    warning when one sits in a top hotspot."""
    s = _structure(report)
    if not s:
        return []
    generated, vendored = _generated(report), filetypes.vendor_dirs(report)
    deep = [f for f in s.get("functions") or [] if (f["nesting"] >= min_nesting or f["bumps"] >= min_bumps)
            and not (filetypes.is_test_path(f["file"]) or filetypes.is_sample_path(f["file"]) or filetypes.is_vendored(f["file"], vendored)
                     or f["file"] in generated)]
    if not deep:
        return []
    deep.sort(key=lambda f: (-f["cognitive"], -f["nesting"], f["file"], f["start"]))
    top = set(_scored_top(report, top_n))
    sev = "warning" if any(f["file"] in top for f in deep) else "info"

    def one(f):
        return f"{f['name']} ({f['file']}:{f['start']}) nested {f['nesting']} deep, cognitive complexity {f['cognitive']}, {f['bumps']} bump{'s' if f['bumps'] != 1 else ''}"
    listed = "; ".join(one(f) for f in deep[:5]) + (f" and {len(deep) - 5} more" if len(deep) > 5 else "")
    first = next((f for f in deep if f["file"] in top), deep[0])
    return [_f(sev, "Deeply nested code", f"{_plural(len(deep), 'function')} nest {min_nesting} levels or more or carry {min_bumps}+ separate nested chunks: {listed}.",
               f"Flatten {first['name']} in {first['file']} first: return early and move each nested chunk into a function of its own.",
               rule={"id": "deep_nesting", "min_nesting": min_nesting, "min_bumps": min_bumps, "measure": "tree-sitter",
                     "ref": "SonarSource cognitive complexity; CodeScene code health"},
               evidence={"count": len(deep), "functions": [{k: f[k] for k in ("file", "name", "start", "nesting", "cognitive", "bumps")} for f in deep[:10]]})]


def hidden_coupling(report: dict, min_degree: int = 60, min_revs: int = 5, min_resolved: float = 0.6) -> list:
    """Pairs that change together without an import between them, in either direction. Ajienka and
    Capiluppi found across 79 projects that many co-changed pairs have no structural dependency at
    all: such a pair is a shared format, a duplicated rule or copy-paste, and neither a pure-git nor a
    pure-static tool can print it. Only for languages whose imports this graph mostly resolves, and not
    for a pair that is example or documentation material on both sides (_both_specimens)."""
    s = _structure(report)
    if not s:
        return []
    files, resolved, tree = s.get("files") or {}, s.get("resolved") or {}, _tree(report)
    derived = _generated(report)

    def graphed(p):
        info = files.get(p)
        return info is not None and info.get("language") in STRUCTURE_LANGUAGES and resolved.get(info["language"], 0) >= min_resolved

    hidden = []
    for p in report.get("coupling") or []:
        a, b = p["entity"], p["coupled"]
        if p["degree"] < min_degree or p["average-revs"] < min_revs or not (graphed(a) and graphed(b)):
            continue
        if filetypes.is_test_path(a) or filetypes.is_test_path(b) or filetypes.is_header_pair(a, b) or a in derived or b in derived:
            continue
        if _both_specimens(a, b):
            continue
        if tree and (a not in tree or b not in tree):
            continue
        if b in (files[a].get("imports") or []) or a in (files[b].get("imports") or []):
            continue
        hidden.append(p)
    if not hidden:
        return []
    hidden.sort(key=lambda p: (-p["degree"], -p["average-revs"], p["entity"]))
    listed = "; ".join(f"{p['entity']} and {p['coupled']} change together {p['degree']}% of the time, and neither imports the other" for p in hidden[:3])
    more = f" ({_plural(len(hidden) - 3, 'more pair')} like them)" if len(hidden) > 3 else ""
    first = hidden[0]
    return [_f("info", "Coupling with no import behind it", f"{listed}{more}.",
               f"Look at why {first['entity']} and {first['coupled']} move together: a shared format, a duplicated rule or copied code is the usual answer.",
               rule={"id": "hidden_coupling", "min_degree": min_degree, "min_revs": min_revs, "min_resolved": min_resolved,
                     "ref": "Ajienka and Capiluppi, JSS 2017"},
               evidence={"pairs": [{"a": p["entity"], "b": p["coupled"], "degree": p["degree"], "revs": p["average-revs"]} for p in hidden[:10]]})]


DEFERRED_MARKS_FROM = 4   # the structure analyser that first marked deferred imports; an older structure.json would show loops broken on purpose


def _groups(edges: dict) -> list:
    """The strongly connected components of two files or more, by Tarjan's algorithm, iterative so a
    deep graph does not reach the recursion limit; each sorted, and visited in sorted order so the
    same graph gives the same groups."""
    index, low, on, stack, out, n = {}, {}, set(), [], [], 0
    for root in sorted(edges):
        if root in index:
            continue
        work = [(root, iter(edges[root]))]
        index[root] = low[root] = n
        n += 1
        stack.append(root)
        on.add(root)
        while work:
            node, it = work[-1]
            for nxt in it:
                if nxt not in index:
                    index[nxt] = low[nxt] = n
                    n += 1
                    stack.append(nxt)
                    on.add(nxt)
                    work.append((nxt, iter(edges[nxt])))
                    break
                if nxt in on:
                    low[node] = min(low[node], index[nxt])
            else:
                work.pop()
                if work:
                    low[work[-1][0]] = min(low[work[-1][0]], low[node])
                if low[node] == index[node]:
                    group = []
                    while True:
                        p = stack.pop()
                        on.discard(p)
                        group.append(p)
                        if p == node:
                            break
                    if len(group) > 1:
                        out.append(sorted(group))
    return out


def _loop_from(edges: dict, members: set, start: str) -> list:
    """The shortest loop from `start` back to itself inside the group, by breadth-first search with
    neighbours in sorted order: [start, ..., start]; None when there is none."""
    parent, todo = {}, [start]
    while todo:
        nxt_level = []
        for node in todo:
            for nxt in edges[node]:
                if nxt == start:
                    back = [node]   # node, its parent, ..., start
                    while back[-1] != start:
                        back.append(parent[back[-1]])
                    return [*reversed(back), start]
                if nxt in members and nxt not in parent:
                    parent[nxt] = node
                    nxt_level.append(nxt)
        todo = nxt_level
    return None


def _loop(edges: dict, group: list) -> list:
    """The group's shortest loop: the shortest of the shortest loops through each member, ties to the
    member that sorts first, so what the finding names is what docs/output.md says it names."""
    members, best = set(group), None
    for start in group:
        loop = _loop_from(edges, members, start)
        if loop is not None and (best is None or len(loop) < len(best)):
            best = loop
            if len(best) == 3:
                break   # a mutual pair: nothing shorter exists
    return best or [group[0], group[0]]


def import_cycles(report: dict, min_resolved: float = structure.MIN_RESOLVED, min_files: int = structure.MIN_FILES) -> list:
    """Groups of source files that import each other, directly or round a loop, as they load: an import
    inside a function, a type-only import and a dynamic import() are left out, since they are how a
    loop is broken on purpose. Oyetoyan et al. found classes near a cycle change more often (Java, SANER
    2015) and found no rule that tells a harmful cycle from a harmless one, so this names the loops and
    leaves the verdict to the reader. Only groups holding a language structure.trusted vouches for (resolved
    by path, mostly resolved, enough files); tests, examples, vendored and generated files are left out."""
    s = _structure(report)
    if not s or int(s.get("analyser") or 0) < DEFERRED_MARKS_FROM:
        return []   # a structure.json from before the deferred marks would name the loops deferred imports break on purpose
    files, resolved, derived = s.get("files") or {}, s.get("resolved") or {}, _generated(report)
    judged = structure.trusted(files, resolved, min_resolved, min_files)
    # the graph holds every language that resolves well enough, since .ts, .tsx and .js are one module graph to
    # the loader; a group is named when a trusted language is in it, so two components in a loop with
    # TypeScript count and three lone TypeScript files do not
    keep = {p for p, info in files.items() if info.get("language") in structure.GRAPH_LANGUAGES
            and resolved.get(info.get("language"), 0) >= min_resolved and not _aside_path(p) and p not in derived}
    edges = {p: sorted(set(t for t in files[p].get("imports") or [] if t in keep) - set(files[p].get("deferred") or [])) for p in sorted(keep)}
    groups = [g for g in _groups(edges) if any(files[p].get("language") in judged for p in g)]
    if not groups:
        return []
    groups.sort(key=lambda g: (-len(g), g[0]))
    loops = [_loop(edges, g) for g in groups]

    def said(group, loop):
        arrow = " → ".join(loop)
        return arrow if len(loop) - 1 == len(group) else f"{arrow}, one loop in a group of {len(group)} files"
    listed = "; ".join(said(g, l) for g, l in zip(groups[:3], loops[:3]))
    more = f" ({_plural(len(groups) - 3, 'more group')})" if len(groups) > 3 else ""
    n = len(groups)
    return [_f("info", "Import cycles",
               f"In {_plural(n, 'group')}, files import each other as they load: {listed}{more}.",
               f"Break {' → '.join(loops[0])} first: move what both ends need into a file neither imports, or import it where it is used.",
               rule={"id": "import_cycles", "min_resolved": min_resolved, "min_files": min_files, "ref": REFS["import_cycles"]},
               evidence={"count": n, "groups": [{"files": g[:20], "size": len(g), "loop": l} for g, l in zip(groups[:10], loops[:10])]})]


def unreferenced_files(report: dict) -> list:
    """Files nothing in the tree imports that are no entry point by convention or declaration, from the
    structure step, which already leaves out languages whose graph is too blind to judge. Never
    "dead": Romano et al. found no comprehension cost to dead code in controlled experiments, and a
    dynamic import cannot be seen from here, so this is a list to check, not to delete."""
    s = _structure(report)
    paths = s.get("unreferenced") or []
    if not paths:
        return []
    n = s.get("unreferenced_count", len(paths))
    return [_f("info", "Possibly unreferenced files", f"{_plural(n, 'file')} {'is' if n == 1 else 'are'} imported by nothing in the tree and {'is' if n == 1 else 'are'} no entry point: {_files_list(paths, 5)}.",
               f"Check {paths[0]} before anything else; dynamic imports, plugins loaded by name and framework routing do not show in an import graph.",
               rule={"id": "unreferenced_files", "ref": "Romano et al., TSE 2020"}, evidence={"count": n, "files": paths[:10]})]


def _agents(report: dict) -> dict:
    return ((report.get("provenance") or {}).get("agents")) or {}


def agent_approval_disabled(report: dict) -> list:
    """A committed agent configuration that turns approval prompts off: every clone that picks the
    settings up runs the agent's tools without asking."""
    rows = _agents(report).get("approval_disabled") or []
    if not rows:
        return []
    listed = "; ".join(f"{r['file']} sets {r['setting']}" for r in rows)
    return [_f("warning", "Agent approval prompts turned off in the repository", f"{listed}. Anyone who opens the clone with that agent runs its tools unasked.",
               "Move the setting to your personal settings file, which is not committed, and keep the shared one to what everyone should get.",
               rule={"id": "agent_approval_disabled", "by": "tracked agent settings"}, evidence={"settings": rows})]


def agent_local_settings(report: dict) -> list:
    rows = _agents(report).get("local_settings") or []
    if not rows:
        return []
    return [_f("warning", "Personal agent settings tracked", f"{_files_list(rows)} {'is' if len(rows) == 1 else 'are'} tracked; the file is meant for one machine and to stay out of git.",
               f"git rm --cached {rows[0]} and add it to .gitignore.",
               rule={"id": "agent_local_settings", "by": "path convention"}, evidence={"files": rows})]


def mcp_literal_env(report: dict) -> list:
    """An MCP server declaration whose environment holds a literal value long enough to be a
    credential rather than a ${VAR} reference. The key is named, the value never."""
    rows = [(m["file"], x) for m in _agents(report).get("mcp") or [] for x in m.get("literal_env") or []]
    if not rows:
        return []
    listed = "; ".join(f"{x['server']} sets {x['key']} in {f} to a literal value" for f, x in rows[:5])
    f0, x0 = rows[0]
    return [_f("warning", "Literal values in MCP server declarations", f"{listed}. A committed declaration shares whatever it holds.",
               f"Replace the value of {x0['key']} with ${{{x0['key']}}} and set it in the environment; rotate it if it was a live credential.",
               rule={"id": "mcp_literal_env", "min_length": 16, "placeholders": "left out"},
               evidence={"entries": [{"file": f, "server": x["server"], "key": x["key"]} for f, x in rows[:10]]})]


def agent_instructions_drift(report: dict, min_months: int = 6, min_commits: int = 100) -> list:
    """Agent instruction files (AGENTS.md and the like) far behind the code they describe."""
    last = (report.get("meta") or {}).get("last_date") or ""
    stale = [r for r in _agents(report).get("instructions") or []
             if last and _months_apart(r["last"], last) >= min_months and r["commits_behind"] >= min_commits]
    if not stale:
        return []
    listed = "; ".join(f"{r['file']} last changed on {r['last']}, {_months_apart(r['last'], last)} months and {r['commits_behind']:,} commits before the last commit" for r in stale)
    return [_f("info", "Agent instructions behind the code", f"{listed}.",
               f"Read {stale[0]['file']} against the tree and update what moved; an agent follows it literally.",
               rule={"id": "agent_instructions_drift", "min_months": min_months, "min_commits": min_commits},
               evidence={"files": stale})]


def signoff_by_co_author(report: dict, min_commits: int = 2) -> list:
    """An identity that signs off commits it co-authors but never authors one: the Linux kernel's policy
    on coding assistants forbids an agent to add Signed-off-by, since the DCO is a human's statement."""
    rows = [r for r in ((report.get("provenance") or {}).get("trailers") or {}).get("signoff_by_co_author") or [] if r["commits"] >= min_commits]
    if not rows:
        return []
    listed = "; ".join(f"{r['name']} <{r['email']}> signs off {_plural(r['commits'], 'commit')} but never authors one" for r in rows[:3])
    return [_f("info", "Sign-offs by identities that only co-author", f"{listed}.",
               "A Signed-off-by line certifies the Developer Certificate of Origin; have a person who authors commits add it.",
               rule={"id": "signoff_by_co_author", "min_commits": min_commits, "ref": "Linux kernel, Documentation/process/coding-assistants.rst"},
               evidence={"identities": rows[:10]})]


def _pool_files(report: dict) -> list:
    """The source files still in the tree that no classifier reason sets aside."""
    from . import classify
    cls = classify.Classifier(report)
    return sorted(f for f in _tree(report) if cls.reason(f) is None)


def _authors_of(report: dict, files: list, key: str = "is_author") -> dict:
    wanted = set(files)
    out = {f: set() for f in files}
    for r in report.get("doa") or []:
        if r["entity"] in wanted and r.get(key):
            out[r["entity"]].add(r["author"])
    return out


def truck_factor(report: dict, min_files: int = 20, area_files: int = 10) -> list:
    """Avelino et al.'s truck factor over the degree of authorship: how many people have to leave before
    more than half the source files have no author. One is a warning, two a note. Changes rather than
    lines, and a creator's bonus, so it can disagree with the surviving-code share, which the bus-factor
    finding reads; the finding says so when it does. Also per area, and with knowledge halving every
    five months."""
    if not report.get("doa"):
        return []
    files = _pool_files(report)
    authored = {f: a for f, a in _authors_of(report, files).items()}
    if len(files) < min_files:
        return []
    tf, removed, share = knowledge.truck_factor(authored)
    if not removed:
        # More than half the pool has no author before anyone leaves (files an import brought in, or
        # history the clone does not hold, have no creator), so there is no truck factor and no one to name.
        return []
    tf_d, removed_d, _ = knowledge.truck_factor(_authors_of(report, files, "is_author_decayed"))
    depth = knowledge.depth_for(files)
    areas = {}
    for f in files:
        areas.setdefault(knowledge._area(f, depth), []).append(f)
    lone = []
    for area, fs in sorted(areas.items()):
        if len(fs) >= area_files and area != knowledge.ROOT:
            n, who, orphaned_share = knowledge.truck_factor({f: authored[f] for f in fs})
            if n == 1:   # the area's size and what one departure orphans, so a reader can tell ten files from ten thousand
                lone.append((area, who[0], len(fs), round(orphaned_share * len(fs))))
    if tf > 2 and not lone:
        return []
    orphans = round(share * len(files))
    statement = (f"Truck factor {tf}: without {textfmt.join_and(removed)}, {orphans} of the {len(files)} source files ({_pct(orphans, len(files))}) "
                 f"have no author left.")
    if tf_d != tf and not removed_d:
        statement += " With knowledge halving every five months, more than half the files already have no author."
    elif tf_d != tf:
        statement += f" With knowledge halving every five months it is {tf_d} ({textfmt.join_and(removed_d)})."
    if lone:
        statement += " Areas with a truck factor of one: " + ", ".join(f"{a} ({w})" for a, w, _, _ in lone[:5]) + (f" and {len(lone) - 5} more" if len(lone) > 5 else "") + "."
    shares = report.get("theseus_authors") or {}
    if shares and removed:
        top, lines = max(shares.items(), key=lambda kv: kv[1])
        if top != removed[0]:
            statement += f" The surviving code's largest share is {top}'s ({_pct(lines, sum(shares.values()))}), which the bus-factor finding reads."
    first_area = next((a for a, w, _, _ in lone if w == removed[0]), lone[0][0] if lone else None)
    advice = f"Pair someone with {removed[0]}" + (f" on {first_area}" if first_area else "") + " first; they author most of what would be left without an author."
    return [_f("warning" if tf == 1 else "info", "Truck factor", statement, advice,
               rule={"id": "truck_factor", "doa_author_share": 0.75, "doa_floor": 3.293, "orphan_share": 0.5, "decay_months": 5,
                     "ref": "Avelino et al., ICPC 2016"},
               evidence={"truck_factor": tf, "removed": removed, "truck_factor_decayed": tf_d, "removed_decayed": removed_d,
                         "files": len(files), "orphaned": orphans,
                         "areas": [{"area": a, "author": w, "files": n, "orphaned": o} for a, w, n, o in lone[:10]]})]


def authors_gone(report: dict, min_files: int = 5) -> list:
    """Files whose every author by degree of authorship has stopped committing, while others still
    change them: "creator left, editors remain", knowledge the blame share cannot show."""
    if not report.get("doa"):
        return []
    months = report["meta"].get("gone_months", loss.DEFAULT_MONTHS)
    gone = {g["name"] for g in loss.gone(report, months)}
    fresh = {a["entity"] for a in report.get("age") or [] if a["age-months"] < 12}
    files = [f for f in _pool_files(report) if f in fresh]
    authored = _authors_of(report, files)
    left = [(f, sorted(a)) for f, a in authored.items() if a and a <= gone]
    if len(left) < min_files:
        return []
    listed = "; ".join(f"{f} ({textfmt.join_and(a)})" for f, a in left[:5]) + (f" and {len(left) - 5} more" if len(left) > 5 else "")
    return [_f("info", "Files whose authors have left", f"{len(left)} source files changed in the last year have no author still committing: {listed}.",
               f"Make the people who edit {left[0][0]} its authors: review its design with them and write down what only {left[0][1][0]} knew.",
               rule={"id": "authors_gone", "gone_months": months, "min_files": min_files, "ref": "Avelino et al., ICPC 2016"},
               evidence={"count": len(left), "files": [{"file": f, "authors": a} for f, a in left[:10]]})]


def component_coupling(report: dict, min_degree: int = 30) -> list:
    """Components (top-level directories, or the level below a lone src/) that change together in a
    large share of their changes: coupling at the level of the architecture, where two files in one
    directory is only a layout."""
    rows = report.get("components") or []
    if not rows:
        return []
    depth = knowledge.depth_for(list(_tree(report)) or [r["entity"] + "x" for r in rows])

    def aside(c):
        probe = c + "x.py"
        return filetypes.is_test_path(probe) or filetypes.is_sample_path(probe) or filetypes.is_doc_path(probe) or filetypes.is_vendor_path(probe)
    pairs = [r for r in rows if r["depth"] == depth and r["degree"] >= min_degree and not aside(r["entity"]) and not aside(r["coupled"])]
    if not pairs:
        return []
    listed = "; ".join(f"{p['entity']} and {p['coupled']} change together in {p['degree']}% of their changes ({p['shared']} shared)" for p in pairs[:3])
    more = f" ({_plural(len(pairs) - 3, 'more pair')})" if len(pairs) > 3 else ""
    first = pairs[0]
    return [_f("info", "Components that change together", f"{listed}{more}.",
               f"Look at what {first['entity']} and {first['coupled']} share: a change that keeps landing in both is an interface nobody named.",
               rule={"id": "component_coupling", "min_degree": min_degree, "depth": depth, "ref": "Tornhill, Your Code as a Crime Scene, 2024"},
               evidence={"pairs": [{"a": p["entity"], "b": p["coupled"], "degree": p["degree"], "shared": p["shared"]} for p in pairs[:10]]})]


RULES = [dormant, secrets_found, credential_files, vulnerable_dependencies, placeholder_identity, bus_factor, sizer_concerns, bug_magnets,
         minor_contributors, reverts, brain_methods, complexity_growth, tight_coupling, duplication, stale_files, knowledge_islands, knowledge_loss,
         sweeping_commits, import_commits, tangled_commits, hygiene_findings, debt_in_hotspots, deep_nesting, hidden_coupling, import_cycles, unreferenced_files,
         agent_approval_disabled, agent_local_settings, mcp_literal_env, agent_instructions_drift, signoff_by_co_author,
         truck_factor, authors_gone, component_coupling, swallowed_errors, hardcoded_addresses, commented_out_code]


# Rules whose findings were true when labelled but never something to act on: five or more labelled in
# measure/labels.jsonl and none of them actionable (docs/measurement.md, "Hand labels"). The default terminal
# report names them in one line instead of spelling each out; --full, Markdown, JSON, SARIF and --fail-on
# see every finding as before. A test holds this set to the labels, both ways.
SUMMARISED = frozenset({"authors_gone", "component_coupling", "duplication", "knowledge_loss", "minor_contributors", "repo_health",
                        "reverts", "secrets_aside", "stale_files"})

# Rules nobody has labelled yet: the structure step's, which ran only where tree-sitter was installed by hand
# until 0.32.0 and so never reached the measurement's findings sheet. They are named in a line of their own, so
# the default report does not grow by rules whose worth is unmeasured; the labels decide where they belong, and
# a rule moves out of here when its findings are labelled, into SUMMARISED or into the report proper.
UNJUDGED = frozenset({"commented_out_code", "debt_in_hotspots", "deep_nesting", "hardcoded_addresses",
                      "hidden_coupling", "import_cycles", "swallowed_errors", "unreferenced_files"})


def evaluate(report: dict) -> list:
    found = []
    for rule in RULES:
        found.extend(rule(report))
    for f in found:
        if f["rule"]["id"] in SUMMARISED:
            f["summary"] = True   # the default report's one line, not a full entry
        elif f["rule"]["id"] in UNJUDGED:
            f["summary"] = True
            f["unjudged"] = True   # a line of its own: true or not, nobody has said whether it is worth acting on
    found.sort(key=lambda f: SEVERITIES.index(f["severity"]))
    return found

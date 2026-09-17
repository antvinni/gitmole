"""Heuristics that turn a loaded report into a short list of flagged findings."""
from __future__ import annotations

import re

from . import coupling, filetypes, hotspots, knowledge, leaks, loss, textfmt, trend

SEVERITIES = ["critical", "warning", "info"]

PLACEHOLDER_NAMES = {"your name", "unknown", "root", "user"}
PLACEHOLDER_EMAIL = re.compile(r"(@example\.(com|org|net)$|^you@|^user@|^root@|@localhost$)")


def _f(severity: str, title: str, statement: str, advice: str) -> dict:
    """A finding: the facts, then the next step. `detail` is the two joined for anyone reading the
    JSON; `advice` says which part is the step so the report can show it on its own line."""
    return {"severity": severity, "title": title, "detail": f"{statement.rstrip()} {advice}", "advice": advice}


def _pct(part, whole) -> str:
    return f"{round(100 * part / whole)}%" if whole else "0%"


def _plural(n: int, word: str) -> str:
    return f"{n} {word}{'' if n == 1 else 's'}"


def _secret_statement(groups: list) -> str:
    """'N distinct values in M places: rule in file (commits), ...' with at most three values named."""
    def one(g):
        others = len(g["files"]) - 1
        where = g["files"][0] + (f" and {_plural(others, 'other file')}" if others else "")
        commits = ", ".join(g["commits"][:2]) + (f" and {len(g['commits']) - 2} more" if len(g["commits"]) > 2 else "")
        return f"{g['rule']} in {where} ({commits})"
    places = sum(g["places"] for g in groups)
    sample = "; ".join(one(g) for g in groups[:3])
    more = f" and {len(groups) - 3} more" if len(groups) > 3 else ""
    return f"{_plural(len(groups), 'distinct value')} in {_plural(places, 'place')}: {sample}{more}."


def secrets_found(report: dict) -> list:
    """Secrets grouped by value. A value anywhere in source is critical; one that only ever appears in
    test files (fixtures, saved pages), example or rule directories (language samples, a scanner's own
    rules) or documentation (templates) is a warning, so a critical gate does not trip on test data or a
    planning document. Version strings, template markers and key blocks without key material were
    flagged as placeholders and are not a finding."""
    groups = leaks.group(report.get("secrets") or [])

    def in_source(g):
        return any(not (filetypes.is_test_path(f) or filetypes.is_doc_path(f) or filetypes.is_sample_path(f) or filetypes.is_vendor_path(f))
                   for f in g["files"])
    source = [g for g in groups if in_source(g)]
    aside = [g for g in groups if not in_source(g)]
    ignore = "Add the fingerprint of any false positive from secrets.json to .betterleaksignore in the repository."
    out = []
    if source:
        out.append(_f("critical", f"{len(source)} secret(s) in history", _secret_statement(source),
                      f"Rotate them; deleting the file does not remove them from git. {ignore}"))
    if aside:
        out.append(_f("warning", f"{len(aside)} secret(s) only in test, example, vendored or documentation files", _secret_statement(aside),
                      f"Confirm they are fixtures or templates, not live keys. {ignore}"))
    return out


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
                          f"\"{i['name']} <{i['email']}>\" made {i['commits']} commits ({_pct(i['commits'], total)}).", advice))
    return out


def _source_ownership(report: dict) -> list:
    """Ownership rows for source files. Test files and vendored trees are left out of every rule that
    names a next step: owning the tests is not the knowledge risk, and whoever imported vendor/ did
    not write it. The default tables leave test files out too."""
    return [r for r in report.get("ownership") or [] if not (filetypes.is_test_path(r["entity"]) or filetypes.is_vendor_path(r["entity"]))]


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
    return [_f("warning", "Bus factor of one", f"{name} wrote {_pct(lines, total)} of the code that survives today.", advice)]


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
        out.append(_f(sev, "Repo health", f"{row['name']} is {row['value']}{where}. git-sizer level of concern {row['concern']}.", advice))
    return out


def hotspot_dominance(report: dict, ratio: float = 2.0, minimum: int = 20) -> list:
    """One source file takes most of the churn. Test files are left out: they change with everything.
    So is release plumbing: a version file or a manifest changes on every release by design."""
    plumb = filetypes.plumbing_paths(report)
    revs = sorted((r for r in report.get("revisions") or [] if not (filetypes.is_test_path(r["entity"]) or filetypes.is_release(r["entity"], plumb))),
                  key=lambda r: -r["n-revs"])
    if len(revs) < 2 or revs[0]["n-revs"] < minimum or revs[0]["n-revs"] < ratio * revs[1]["n-revs"]:
        return []
    top, nxt = revs[0], revs[1]
    return [_f("info", "One file dominates the churn",
               f"{top['entity']} changed {top['n-revs']} times, versus {nxt['n-revs']} for the next file ({nxt['entity']}).",
               f"Consider splitting {top['entity']}; every change lands there.")]


def tight_coupling(report: dict, min_degree: int = 80, min_revs: int = 5) -> list:
    """A file and its test are expected to change together, so pairs with a test file on either side are
    left out; so are pairs where either file is no longer in the tree, which are history, not a dependency,
    and pairs of release plumbing (two version files, a manifest and its lock file), which are a release."""
    tree = _tree(report)
    pairs = [p for p in report.get("coupling") or [] if p["degree"] >= min_degree and p["average-revs"] >= min_revs
             and not (filetypes.is_test_path(p["entity"]) or filetypes.is_test_path(p["coupled"]))
             and not (filetypes.is_release_path(p["entity"]) and filetypes.is_release_path(p["coupled"]))
             and not (tree and (p["entity"] not in tree or p["coupled"] not in tree))]
    if not pairs:
        return []
    pairs.sort(key=lambda p: (-p["degree"], -p["average-revs"]))
    groups, pairs = coupling.clusters(pairs)
    when = f"together at least {min_degree}% of the time"
    top = "; ".join(f"{p['entity']} + {p['coupled']} ({p['degree']}%)" for p in pairs[:3])
    if groups:
        # a directory of files that change as one is a generator or a shared layout, said once
        named = ", ".join(f"{g['files']} files in {g['dir']}" for g in groups[:2]) + (f" and {len(groups) - 2} more directories" if len(groups) > 2 else "")
        rest = (f", and {_plural(len(pairs), 'more pair')} {'does' if len(pairs) == 1 else 'do'}: {top}." if pairs
                else f", {_plural(sum(g['pairs'] for g in groups), 'pair')} in all.")
        first = groups[0]
        return [_f("info", "Files that always change together", f"{named} change {when}{rest}",
                   f"Review {first['dir']} first: {first['files']} files change as one; a generator or a shared layout links them.")]
    count = f"{len(pairs)} pair changes" if len(pairs) == 1 else f"{len(pairs)} pairs change"
    first = pairs[0]
    return [_f("info", "Files that always change together",
               f"{count} {when}, e.g. {top}.",
               f"Review {first['entity']} and {first['coupled']} first: a shared layout or a hidden dependency links them.")]


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
               "The rest of the report describes a repository that has stopped; look for a successor or an archive notice before depending on it.")]


def stale_files(report: dict, months: int = 12, share: float = 0.3) -> list:
    """Files still in the tree that nobody has touched. The age table covers every path in the
    history, so paths that were deleted are left out here; they are not dead code, they are gone.
    In a dormant repository every file is untouched because nothing is; the dormancy finding says so."""
    if _dormant_months(report) >= months:
        return []
    age = report.get("age") or []
    tree = _tree(report)
    if tree:
        age = [a for a in age if a["entity"] in tree]
    if not age:
        return []
    stale = [a for a in age if a["age-months"] >= months]
    if len(stale) / len(age) <= share:
        return []
    return [_f("info", "A large share of files is untouched",
               f"{_pct(len(stale), len(age))} of files ({len(stale)}) have not changed in {months} months or more.",
               "Consider deleting what nobody has needed; dead code hides in untouched files.")]


def bug_magnets(report: dict, min_recent: int = 3, warn_at: int = 5) -> list:
    """Source files with a run of recent fix commits. Test files are left out: they change with every fix.
    So is release plumbing: a manifest touched by every fix release is not where the bug was."""
    plumb = filetypes.plumbing_paths(report)
    hot = [f for f in report.get("fixes") or [] if f["recent-fixes"] >= min_recent
           and not (filetypes.is_test_path(f["entity"]) or filetypes.is_release(f["entity"], plumb))]
    if not hot:
        return []
    hot.sort(key=lambda f: (-f["recent-fixes"], -f["n-fixes"], f["entity"]))
    sev = "warning" if hot[0]["recent-fixes"] >= warn_at else "info"
    listed = "; ".join(f"{f['entity']} ({f['recent-fixes']} recent, {f['n-fixes']} total)" for f in hot[:5])
    more = f" and {len(hot) - 5} more" if len(hot) > 5 else ""
    first = " and ".join(f["entity"] for f in hot[:2])
    return [_f(sev, "Bug magnets",
               f"{len(hot)} file(s) were fixed {min_recent}+ times in the last six months: {listed}{more}.",
               f"Review {first} before the next release; expect the next bug there.")]


def reverts(report: dict, min_share: float = 0.05, min_count: int = 5, warn_share: float = 0.10) -> list:
    """Commits backed out with git revert. The file most often reverted is where a check before merge pays."""
    act = report.get("activity") or {}
    n = act.get("revert_commits") or 0
    total = report["meta"].get("commits") or 0
    if not n or not total or (n < min_count and n / total < min_share):
        return []
    sev = "warning" if total and n / total >= warn_share else "info"
    reverted = act.get("reverted") or {}
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
    return [_f(sev, "Reverts", statement, advice)]


def knowledge_islands(report: dict, min_lines: int = 200, min_share: float = 0.9) -> list:
    """Areas of the tree written almost entirely by one person. Areas that no longer exist are left
    out, of the islands and of the total they are measured against."""
    areas = _present_areas(report, _source_ownership(report))
    islands = knowledge.islands(areas, min_lines=min_lines, min_share=min_share)
    if not islands:
        return []
    total = sum(a["lines"] for a in areas)
    covered = sum(i["lines"] for i in islands)
    sev = "warning" if total and covered / total > 0.5 else "info"
    listed = "; ".join(f"{i['area']} ({i['owner']} {i['share']}%)" for i in islands[:5])
    more = f" and {len(islands) - 5} more" if len(islands) > 5 else ""
    largest = max(islands, key=lambda i: i["lines"])
    return [_f(sev, "Knowledge islands",
               f"{len(islands)} area(s) with at least {min_lines} lines were written almost entirely by one person: {listed}{more}. "
               f"That is {_pct(covered, total)} of all lines added.",
               f"Pair someone with {largest['owner']} on {largest['area']} first; it is the largest at {largest['lines']:,} lines.")]


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
    return [_f(sev, "Knowledge loss", statement, advice)]


def _partial_functions(report: dict) -> str:
    """A sentence when the lizard step stopped part way, so what it measured is not the whole code."""
    status = (report["meta"].get("functions") or {}).get("status")
    reason = {"timeout": "timed out", "failed": "failed"}.get(status)
    return f" Function metrics {reason} part way, so there may be more." if reason else ""


def brain_methods(report: dict, min_ccn: int = 15, min_lines: int = 100) -> list:
    """Functions that are both long and complex, in this repository's own source files: test files,
    vendored code and generated files are left out. A warning when one sits in a hotspot."""
    generated = _generated(report)
    big = [f for f in report.get("functions") or [] if f["ccn"] >= min_ccn and f["nloc"] >= min_lines
           and not (filetypes.is_test_path(f["file"]) or filetypes.is_vendor_path(f["file"]) or f["file"] in generated)]
    if not big:
        return []
    big.sort(key=lambda f: (-f["ccn"], -f["nloc"], f["file"], f["function"], f["start"]))
    hot = hotspots.top(report)
    sev = "warning" if any(f["file"] in hot for f in big) else "info"
    listed = "; ".join(f"{f['function']} ({_place(f)}) complexity {f['ccn']}, {f['nloc']} lines, {f['params']} params" for f in big[:5])
    more = f" and {len(big) - 5} more" if len(big) > 5 else ""
    first = big[0]
    which = f"the anonymous function at {_place(first)}" if first["function"] == ANONYMOUS else f"{first['function']} in {first['file']}"
    return [_f(sev, "Brain methods",
               f"{len(big)} function(s) are both long and complex: {listed}{more}.{_partial_functions(report)}",
               f"Split {which} first, before the next change lands there.")]


ANONYMOUS = "(anonymous)"


def _place(f: dict) -> str:
    """Where a function is: its file, or file:line when it has no name to find it by."""
    return f"{f['file']}:{f['start']}" if f["function"] == ANONYMOUS else f["file"]


def _generated(report: dict) -> set:
    """Files the run found to be generated (a header marker or a linguist-generated attribute)."""
    return set((report.get("meta") or {}).get("generated") or [])


def complexity_growth(report: dict, min_growers: int = 3, min_pct: int = 25, top_n: int = 10) -> list:
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
               f"Split {first[0]} before the next change; its complexity grew {first[1]}% in a year.")]


def duplication(report: dict, min_lines: int = 30) -> list:
    dup = report.get("duplicates") or {}
    blocks = [b for b in dup.get("blocks") or [] if b["lines"] >= min_lines]
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
    return [_f("info", "Duplicated code", f"{len(blocks)} block(s) of {min_lines}+ duplicated lines: {listed}{more}.{rate}{_partial_functions(report)}",
               f"Extract the {first['lines']}-line block {where} first.")]


RULES = [dormant, secrets_found, placeholder_identity, bus_factor, sizer_concerns, hotspot_dominance, bug_magnets, reverts, brain_methods,
         complexity_growth, tight_coupling, duplication, stale_files, knowledge_islands, knowledge_loss]


def evaluate(report: dict) -> list:
    found = []
    for rule in RULES:
        found.extend(rule(report))
    found.sort(key=lambda f: SEVERITIES.index(f["severity"]))
    return found

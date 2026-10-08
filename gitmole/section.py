"""`--section NAME`: one section of the report on its own and whole, as a table, as Markdown or as CSV.

The report caps every table and hides the rows that are not the repository's own source, so a reader who
wants the rest had `--full`'s dump (prometheus: 4,359 lines at 80 columns, 1,337 of them People) or a 27 MB
JSON export. A section printed here has every row, the ones the default shows first and in the same
ranking, then the ones it hides, each with a one-word kind where the rows are files; and `--csv` writes
the same rows to stdout with every field the export holds for them. Nothing is written to the output
directory: a file per table on every run would add to a directory that is a cost of its own, and
functions.csv is already there, headerless, for --no-run to read back.

A name is the section's title in lower case with a hyphen for each space ("complex-functions"), so it
needs no quoting; the title itself, in any case, is taken too. NAMES maps each to the id the renderer
builds the section under (render.BUILDERS), and holds two that are no table of any report: `findings`,
every finding in the long form, and `companions`, the directed pairs --hook and --risk read."""
from __future__ import annotations

import csv
import difflib
import io
import re

FINDINGS = "findings"
# name -> section id, in the order --full prints them; the sections no report prints last
NAMES = {
    "findings": FINDINGS, "watch-list": "watch", "most-changed-documents": "documents", "watch-list-by-component": "watch_by_component",
    "hotspots": "hotspots", "complex-functions": "functions", "change-coupling": "coupling", "size-by-language": "size",
    "knowledge-map": "knowledge", "people": "people", "timeline": "timeline", "activity": "activity",
    "surviving-code-by-year": "age", "changed-lines": "lines", "trailers": "trailers", "secrets-by-rule": "secrets_by_rule",
    "dependencies-by-lock-file": "dependencies_by_lock_file", "signing-by-year": "signing", "checks-run": "checks_run",
    "agent-surface": "agent_surface", "osps-baseline": "osps", "companions": "companions",
}
ALIASES = {"watch": "watch-list"}   # the short name the plan and the docs use for the list
PERSON_COLUMNS = ("author", "owner", "main owner", "second")   # the columns of a table that hold a person's name


def canonical(name: str):
    """The name in NAMES that `name` means, or None: case and the run of spaces, hyphens or underscores between
    two words do not matter, so "Complex functions", "complex-functions" and "COMPLEX_FUNCTIONS" are one."""
    key = re.sub(r"[\s_-]+", "-", (name or "").strip().lower())
    key = ALIASES.get(key, key)
    return key if key in NAMES else None


def close_name(name: str):
    """The name in NAMES that a misspelt `name` was likely meant to be ("peple" -> "people"), by difflib at its
    default cut-off, or None when nothing is near."""
    key = re.sub(r"[\s_-]+", "-", (name or "").strip().lower())
    close = difflib.get_close_matches(key, list(NAMES) + list(ALIASES), n=1)
    return canonical(close[0]) if close else None


def name_of(sid: str):
    """The --section name of a section id ("functions" -> "complex-functions"), or None."""
    return next((name for name, s in NAMES.items() if s == sid), None)


def names_text(width: int = 78, indent: str = "  ") -> str:
    """Every name, comma-separated and wrapped, for --help and for the message an unknown name gets."""
    lines, line = [], indent
    for i, name in enumerate(NAMES):
        word = name + ("," if i < len(NAMES) - 1 else "")
        if len(line) + len(word) + (0 if line == indent else 1) > width and line != indent:
            lines.append(line)
            line = indent
        line += ("" if line == indent else " ") + word
    return "\n".join(lines + [line])


def check(args) -> str | None:
    """What is wrong with --section and --csv as given, or None; the names are replaced by their canonical
    form on the way. The rules, kept few: a section is whole already, so --full has nothing to add; --csv is
    one section's rows on stdout, so it takes exactly one --section and no other export to stdout; and
    another export to stdout (--json -, --sarif -, --sbom -) would share it with the section. An export to
    a file is written as always, and the gates read the findings, not what is printed, so they are unchanged."""
    asked = list(getattr(args, "section", None) or [])
    if getattr(args, "csv", False) and not asked:
        return "--csv needs --section NAME: it writes one section's rows"
    if not asked:
        return None
    unknown = [n for n in asked if canonical(n) is None]
    if unknown:
        guesses = [g for g in (close_name(n) for n in unknown) if g]
        guess = f"; did you mean {' or '.join(dict.fromkeys(guesses))}?" if guesses else "."
        return f"--section: no section called {', '.join(repr(n) for n in unknown)}{guess} The names:\n{names_text()}"
    args.section = list(dict.fromkeys(canonical(n) for n in asked))
    if args.full:
        return "--section prints a section whole, every row of it; --full has nothing to add to it"
    if getattr(args, "hook", False):
        return "--section prints a section of the report; --hook prints an agent's context instead"
    to_stdout = [flag for flag, value in (("--json", args.json), ("--sarif", args.sarif), ("--sbom", args.sbom)) if value == "-"]
    if to_stdout:
        return f"--section and {to_stdout[0]} - would both write to stdout; give {to_stdout[0]} a file"
    if args.csv and len(args.section) > 1:
        return "--csv writes one section's rows: give one --section"
    if args.csv and args.markdown:
        return "--csv and --markdown are two forms of one section: choose one"
    return None


def _built(report: dict, name: str, width=None):
    from . import render
    return render.whole_section(report, NAMES[name], width)


def _nothing(name: str) -> str:
    return f"{name}: nothing in this run"


def _unfinished(report: dict):
    """'not complete: the secrets scan timed out': the one line a section on its own keeps of the header, since
    rows missing because a step did not finish must not read as rows that are not there."""
    from . import render
    parts = render._unfinished(report)
    return f"not complete: {'; '.join(parts)}" if parts else None


def show(report: dict, found: list, console, names: list) -> None:
    """Print the named sections, one blank line between two: no header, no Findings (unless asked for by
    name) and no closing lines."""
    from rich.text import Text

    from . import render
    render.carry(console)
    for n, name in enumerate(names):
        if n:
            console.print(Text(""))
        if NAMES[name] == FINDINGS:
            render.show(console, render.findings_block(found, report, full=True, width=render.page_width(console)))
            continue
        sec = _built(report, name, render.page_width(console))
        render.show(console, Text(_nothing(name), style=render.DIM) if sec is None else render.section_block(sec, render.page_width(console)))
    left = _unfinished(report)
    if left:
        render.show(console, Text(left, style=render.DIM))


def markdown(report: dict, found: list, names: list) -> str:
    """The named sections as Markdown, each under its own heading as the Markdown export writes it."""
    from . import render
    out = []
    for name in names:
        if NAMES[name] == FINDINGS:
            out += ["", "## Findings", ""] + render._md_findings(found, report)
            continue
        sec = _built(report, name)
        out += ["", render.md_paragraph(_nothing(name))] if sec is None else render._md_section(sec)
    left = _unfinished(report)
    return "\n".join(out[1:] + (["", render.md_paragraph(left)] if left else []) + [""])


_COUNT = re.compile(r"^-?\d{1,3}(?:,\d{3})+$")


def _plain(cell):
    """A table's cell as a CSV's: a count without its thousands separators, anything else as it is."""
    return cell.replace(",", "") if isinstance(cell, str) and _COUNT.match(cell) else cell


def table(report: dict, found: list, name: str):
    """(heads, rows) of one section's CSV, or None for a section this run has nothing for. A section that
    holds more for a row than its table shows gives its own (render: "csv"); any other is its table, the bar
    column left out and what a terminal prints under a row as a last column. The findings are a row each:
    severity (the export's word), rule id, title, statement and step."""
    from . import render, textfmt
    if NAMES[name] == FINDINGS:
        rows = []
        for f in found:
            statement, advice = textfmt._statement_and_advice(f)
            rows.append([f["severity"], (f.get("rule") or {}).get("id") or "", f["title"], statement, advice or ""])
        return ["severity", "rule", "title", "statement", "step"], rows
    sec = _built(report, name)
    if sec is None:
        return None
    if sec.get("csv"):
        return sec["csv"]
    if sec.get("wide"):   # the columns a terminal draws under each row are columns here
        sec = dict(sec, columns=sec["wide"]["columns"], rows=sec["wide"]["rows"], under=None)
    keep = [i for i, c in enumerate(sec["columns"]) if c]
    under = sec.get("under")
    heads = [sec["columns"][i] for i in keep] + ([sec.get("under_head") or "also"] if under else [])
    # two columns under one head (the knowledge map's two shares) each take the head before them: "main owner share"
    heads = [f"{heads[n - 1]} {h}" if n and heads.count(h) > 1 else h for n, h in enumerate(heads)]
    people = [n for n, i in enumerate(keep) if sec["columns"][i] in PERSON_COLUMNS]
    rows = []
    for n, row in enumerate(sec["rows"]):
        cells = [_plain(row[i]) for i in keep]
        for at in people:
            cells[at] = render.no_address(cells[at])
        rows.append(cells + ([under[n]] if under else []))
    return heads, rows


def csv_text(report: dict, found: list, name: str) -> str:
    """One section as a headed CSV: the rows `show` prints, in its order. "" for a section with nothing."""
    made = table(report, found, name)
    if made is None:
        return ""
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(made[0])
    writer.writerows(made[1])
    return out.getvalue()

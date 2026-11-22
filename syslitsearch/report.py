"""Excel report of a search run."""

from __future__ import annotations

from pathlib import Path

from openpyxl import Workbook
from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from .search import RunResult

HEAD = Font(bold=True, color='FFFFFF')
HEAD_FILL = PatternFill('solid', fgColor='305496')
HIT_FILL = PatternFill('solid', fgColor='4472C4')
HIT_FONT = Font(bold=True, color='FFFFFF')
GREY_FILL = PatternFill('solid', fgColor='EDEDED')
GREY_FONT = Font(color='808080')
WRAP = Alignment(wrap_text=True, vertical='top')
CENTER = Alignment(horizontal='center', vertical='center')

MATCHING_NOTE = ('Lexical filter: a record passes if every group of the search string has at least one term in its title or abstract. '
                 'Tolerated automatically: case, hyphen/slash/apostrophe = space (or left out), singular = plural, British/American s/z '
                 'spelling, accents. Not tolerated: other word forms ("agentic" does not match "agent"); use "word*" in the keyword file for that.')


def _clean(value):
    """Strings without the control characters Excel refuses, cut to Excel's cell limit."""
    if isinstance(value, str):
        return ILLEGAL_CHARACTERS_RE.sub('', value)[:32000]
    return value


def _header(ws, row: int, values: list) -> None:
    for col, v in enumerate(values, 1):
        c = ws.cell(row, col, v)
        c.fill, c.font, c.alignment = HEAD_FILL, HEAD, Alignment(wrap_text=True, vertical='center')


def _widths(ws, widths: list[int]) -> None:
    for i, w in enumerate(widths, 1):
        ws.column_dimensions[get_column_letter(i)].width = w


def _mark(cell, value: str) -> None:
    cell.value = value
    cell.alignment = CENTER
    if value == 'x':
        cell.fill, cell.font = HIT_FILL, HIT_FONT
    elif value == '–':
        cell.fill, cell.font = GREY_FILL, GREY_FONT


def _overview(wb: Workbook, run: RunResult) -> None:
    ws = wb.active
    ws.title = 'Overview'
    lines = [
        ('Systematic literature search', True),
        (f'Run: {run.started}', False),
        (f'Years: {run.years[0]}–{run.years[1]}' if run.years else 'Years: no filter', False),
        *[(f'{k}: {v}', False) for k, v in run.settings.items()],
        ('', False),
        ('Search string (terms in a group ORed, groups ANDed)', True),
        *[(f'Group {g}: ' + ' | '.join(t.text for t in terms), False) for g, terms in run.query.groups.items()],
        ('', False),
        (MATCHING_NOTE, False),
        ('Hits reported = what the database counts; records = what was downloaded; passed = title or abstract contains the '
         'search string (reading list); no abstract = the title alone does not pass and the database has no abstract, so '
         'the record cannot be checked (sheet "No abstract", check by hand); excluded = the abstract is there and does not '
         'contain the search string.', False),
        ('', False),
    ]
    r = 1
    for text, bold in lines:
        c = ws.cell(r, 1, text)
        c.alignment = WRAP
        if bold:
            c.font = Font(bold=True, size=12)
        r += 1
    _header(ws, r, ['Database', 'Status', 'Connector tested', 'Hits reported', 'Records', 'Passed filter', 'No abstract', 'Excluded',
                    'References indexed', 'References found by query', 'References passing filter'])
    for res in run.sources:
        r += 1
        n_ref = len(run.references)
        idx = sum(v is not None for v in res.indexed.values())
        found = res.found_references
        passing = {rec.reference for rec in res.passed if rec.reference}
        excluded = len(res.records) - len(res.passed) - len(res.no_abstract)
        vals = [res.source.label, res.status, 'yes' if res.source.tested else 'no', res.total, len(res.records), len(res.passed),
                len(res.no_abstract), excluded, f'{idx} of {n_ref}' if n_ref else '', f'{len(found)} of {n_ref}' if n_ref else '',
                f'{len(passing)} of {n_ref}' if n_ref else '']
        for col, v in enumerate(vals, 1):
            ws.cell(r, col, v).alignment = WRAP
    r += 2
    counts = {s: sum(m.status == s for m in run.merged) for s in ('passed', 'no abstract', 'excluded')}
    ws.cell(r, 1, f'All databases together, duplicates merged: {len(run.merged)} papers: {counts["passed"]} on the reading list, '
                  f'{counts["no abstract"]} without abstract, {counts["excluded"]} excluded.').font = Font(bold=True)
    _widths(ws, [110, 28, 10, 12, 10, 10, 10, 10, 14, 14, 14])


def _paper_rows(ws, run: RunResult, items, with_missing: bool) -> None:
    groups = run.query.names
    cols = ['#', 'Title', 'Year', 'Venue', 'Venue type', 'Databases', 'Reference', 'DOI', 'arXiv', 'URL']
    cols += [f'Group {g}: terms found' for g in groups]
    if with_missing:
        cols.append('Missing groups')
    cols.append('Abstract')
    _header(ws, 1, cols)
    items = sorted(items, key=lambda m: (-(m.best('year') or 0), m.best('title').lower()))
    for i, m in enumerate(items, 1):
        row = [i, m.best('title'), m.best('year'), *m.venue(), ', '.join(m.sources), m.reference, m.best('doi'),
               m.best('arxiv_id'), m.best('url')]
        row += ['; '.join(m.matched(g)) for g in groups]
        if with_missing:
            row.append(', '.join(m.missing()))
        row.append(m.best('abstract'))
        ws.append([_clean(v) for v in row])
    widths = [5, 60, 6, 30, 11, 22, 14, 24, 12, 30] + [24] * len(groups) + ([16] if with_missing else []) + [90]
    _widths(ws, widths)
    for row in ws.iter_rows(min_row=2):
        for c in row:
            c.alignment = WRAP
    ws.freeze_panes = 'C2'
    ws.auto_filter.ref = ws.dimensions


def _references(wb: Workbook, run: RunResult) -> None:
    ws = wb.create_sheet('References')
    extra_cols = sorted({k for ref in run.references for k in ref.extra})
    cols = ['Label', 'Title', 'DOI', 'arXiv'] + extra_cols
    active = [res for res in run.sources if res.status == 'ok']
    for res in active:
        cols += [f'{res.source.label}: indexed', f'{res.source.label}: found by query', f'{res.source.label}: passes filter']
    _header(ws, 1, cols)
    ws.row_dimensions[1].height = 45
    for ref in run.references:
        row = [ref.label, ref.title, ref.doi, ref.arxiv_id] + [ref.extra.get(k, '') for k in extra_cols]
        ws.append([_clean(v) for v in row])
        r = ws.max_row
        col = len(row) + 1
        for res in active:
            indexed = res.indexed.get(ref.label) is not None
            recs = [rec for rec in res.records if rec.reference == ref.label]
            _mark(ws.cell(r, col), 'x' if indexed else '–')
            _mark(ws.cell(r, col + 1), 'x' if recs else ('' if indexed else '–'))
            if recs:
                passed = any(rec.check.passed for rec in recs)
                no_abs = not any(rec.abstract for rec in recs)
                _mark(ws.cell(r, col + 2), 'x' if passed else ('no abstract' if no_abs else 'missing: ' + ', '.join(recs[0].check.missing)))
            else:
                ws.cell(r, col + 2, '' if indexed else '–').alignment = CENTER
            col += 3
    _widths(ws, [16, 60, 22, 12] + [14] * len(extra_cols) + [12] * (3 * len(active)))
    ws.freeze_panes = 'C2'
    ws.cell(ws.max_row + 2, 1, 'x = yes; – = the database does not hold the paper; "found by query" uses the year filter of the run.')


def _matrix(wb: Workbook, title: str, run: RunResult, found: dict[str, set[str]], available: dict[str, bool],
            counts: dict | None, note: str) -> None:
    ws = wb.create_sheet(title[:31])
    labels = run.references.labels
    cols = ['ID', 'Group', 'Term', 'References found']
    if counts is not None:
        cols += ['Hits alone', 'Hits with the other groups']
    _header(ws, 1, cols + labels)
    ws.row_dimensions[1].height = 90
    first = len(cols) + 1
    for i in range(first, first + len(labels)):
        ws.cell(1, i).alignment = Alignment(text_rotation=90, horizontal='center', vertical='bottom')
    for term in run.all_terms:
        refs = found.get(term.id, set())
        row = [term.id, term.group, term.text, len(refs)]
        if counts is not None:
            tr = counts.get(term.id)
            row += [tr.alone if tr else None, tr.with_other if tr else None]
        ws.append([_clean(v) for v in row])
        r = ws.max_row
        for j, label in enumerate(labels):
            _mark(ws.cell(r, first + j), 'x' if label in refs else ('' if available.get(label) else '–'))
    last = ws.max_row
    ws.append([])
    ws.append(['', '', f'Terms that find the reference (of {len(run.all_terms)})'])
    r = ws.max_row
    ws.cell(r, 3).font = Font(bold=True)
    for j in range(len(labels)):
        col = get_column_letter(first + j)
        ws.cell(r, first + j, f'=COUNTIF({col}2:{col}{last},"x")').alignment = CENTER
    ws.cell(r + 2, 1, note)
    _widths(ws, [8, 8, 30, 10] + ([12, 14] if counts is not None else []) + [4] * len(labels))
    ws.freeze_panes = ws.cell(2, 5)


def _hit_counts(wb: Workbook, run: RunResult) -> None:
    ws = wb.create_sheet('Hit counts')
    active = [res for res in run.sources if res.terms]
    cols = ['ID', 'Group', 'Term']
    for res in active:
        cols += [f'{res.source.label}: alone', f'{res.source.label}: with other groups']
    _header(ws, 1, cols)
    ws.row_dimensions[1].height = 45
    for term in run.all_terms:
        row = [term.id, term.group, term.text]
        for res in active:
            tr = res.terms.get(term.id)
            row += [tr.alone if tr else None, tr.with_other if tr else None]
        ws.append([_clean(v) for v in row])
    _widths(ws, [8, 8, 30] + [14] * (2 * len(active)))
    ws.freeze_panes = 'D2'
    ws.cell(ws.max_row + 2, 1, 'Hits as counted by the database (year filter of the run). "With other groups": the term AND every group '
                               'of the search string except the term\'s own group.')


def _queries(wb: Workbook, run: RunResult) -> None:
    ws = wb.create_sheet('Queries')
    _header(ws, 1, ['Database', 'What', 'Query'])
    for res in run.sources:
        ws.append([res.source.label, 'search string', res.main_query or res.status])
        for term in run.all_terms:
            tr = res.terms.get(term.id)
            if tr:
                ws.append([res.source.label, f'{term.id} alone', tr.alone_query])
                if tr.with_query:
                    ws.append([res.source.label, f'{term.id} with other groups', tr.with_query])
    _widths(ws, [18, 24, 140])
    for row in ws.iter_rows(min_row=2):
        for c in row:
            c.alignment = WRAP


def write_report(run: RunResult, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    wb = Workbook()
    _overview(wb, run)
    _paper_rows(wb.create_sheet('Reading list'), run, [m for m in run.merged if m.status == 'passed'], with_missing=False)
    _paper_rows(wb.create_sheet('No abstract'), run, [m for m in run.merged if m.status == 'no abstract'], with_missing=True)
    _paper_rows(wb.create_sheet('Excluded'), run, [m for m in run.merged if m.status == 'excluded'], with_missing=True)
    if len(run.references):
        _references(wb, run)
        for res in run.sources:
            if res.terms:
                available = {label: rec is not None for label, rec in res.indexed.items()}
                _matrix(wb, f'Matrix {res.source.label}', run, {k: v.references for k, v in res.terms.items()}, available, res.terms,
                        f'x = {res.source.label} finds the reference with this term alone (no year filter); – = not indexed there.')
        _matrix(wb, 'Matrix lexical', run, run.lexical, {label: label in run.reference_texts for label in run.references.labels}, None,
                'x = the term occurs in the reference\'s title or abstract (lexical filter rules); – = no abstract available. '
                'Compare with the database matrices to see where a database finds a paper without the term in title/abstract.')
    if any(res.terms for res in run.sources):
        _hit_counts(wb, run)
    _queries(wb, run)
    wb.save(path)
    return path

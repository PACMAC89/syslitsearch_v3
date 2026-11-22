"""Combine two syslitsearch search workbooks without changing either original.

Run from the project root: python merge_syslitsearch_reports.py
"""
from __future__ import annotations

from collections import Counter
from pathlib import Path
import re
import unicodedata
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font, PatternFill, Alignment

ROOT = Path('results/prisma/retriever_2026_new_run')
INPUTS = (ROOT / 'search.xlsx', ROOT / 'scopus_only.xlsx')
OUTPUT = ROOT / 'search_merged.xlsx'
SHEETS = ('Reading list', 'No abstract', 'Excluded')
BASE = ('Title', 'Year', 'Venue', 'Venue type', 'Databases', 'Reference', 'DOI', 'arXiv', 'URL', 'Abstract')


def norm(value):
    s = unicodedata.normalize('NFKD', str(value or '')).casefold()
    return re.sub(r'[^a-z0-9]+', ' ', s).strip()


def norm_doi(value):
    return re.sub(r'^(https?://(dx\.)?doi\.org/|doi:)', '', str(value or '').strip().lower()).strip()


def norm_arxiv(value):
    return re.sub(r'^(https?://arxiv\.org/(abs|pdf)/|arxiv:)', '', str(value or '').strip().lower()).removesuffix('.pdf')


def nonempty(x):
    return x is not None and str(x).strip() != ''


def source_names(value):
    return {v.strip() for v in str(value or '').split(',') if v.strip()}


def merge_values(old, new, key):
    if key == 'Databases':
        return ', '.join(sorted(source_names(old) | source_names(new)))
    if key.startswith('Group ') and key.endswith(': terms found'):
        terms = {v.strip() for x in (old, new) for v in str(x or '').split(';') if v.strip()}
        return '; '.join(sorted(terms))
    if key == 'Missing groups':
        a = {v.strip() for v in str(old or '').split(',') if v.strip()}
        b = {v.strip() for v in str(new or '').split(',') if v.strip()}
        return ', '.join(sorted(a & b)) if old and new else (old or new)
    if not nonempty(old):
        return new
    if not nonempty(new):
        return old
    if key in ('Title', 'Abstract') and len(str(new)) > len(str(old)):
        return new
    return old


def main():
    for path in INPUTS:
        if not path.is_file():
            raise SystemExit(f'Input missing: {path}')
    if OUTPUT.exists():
        raise SystemExit(f'Output exists, refusing overwrite: {OUTPUT}')

    entries = []
    all_headers = []
    for path in INPUTS:
        wb = load_workbook(path, read_only=True, data_only=True)
        try:
            for sheet in SHEETS:
                if sheet not in wb:
                    raise ValueError(f'{path}: missing sheet {sheet}')
                rows = wb[sheet].iter_rows(values_only=True)
                headers = next(rows)
                if not all(x in headers for x in BASE):
                    raise ValueError(f'{path}: incompatible {sheet} columns')
                for h in headers:
                    if h not in all_headers and h != '#':
                        all_headers.append(h)
                for row in rows:
                    d = dict(zip(headers, row))
                    if nonempty(d.get('Title')):
                        entries.append((sheet, d, path.name))
        finally:
            wb.close()

    # Union-find handles DOI, arXiv and normalized-title links transitively.
    parent = list(range(len(entries)))
    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i
    def union(i, j):
        parent[find(i)] = find(j)

    seen = {}
    for i, (_, d, _) in enumerate(entries):
        keys = []
        if norm_doi(d.get('DOI')):
            keys.append(('doi', norm_doi(d['DOI'])))
        if norm_arxiv(d.get('arXiv')):
            keys.append(('arxiv', norm_arxiv(d['arXiv'])))
        title = norm(d.get('Title'))
        if len(title) > 20:
            keys.append(('title', title))
        for key in keys:
            if key in seen:
                union(i, seen[key])
            else:
                seen[key] = i

    grouped = {}
    for i, entry in enumerate(entries):
        grouped.setdefault(find(i), []).append(entry)

    merged = []
    for cluster in grouped.values():
        # A pass in any database means the combined record passes.
        target = next((s for s in SHEETS if any(x[0] == s for x in cluster)), 'Excluded')
        d = {}
        for _, item, _ in cluster:
            for key in all_headers:
                d[key] = merge_values(d.get(key), item.get(key), key)
        d['DOI'] = norm_doi(d.get('DOI'))
        d['arXiv'] = norm_arxiv(d.get('arXiv'))
        merged.append((target, d, sorted({x[2] for x in cluster})))

    out = Workbook()
    overview = out.active
    overview.title = 'Overview'
    overview.append(['Combined search: Semantic Scholar, Scopus, IEEE Xplore'])
    overview.append(['Source files', ', '.join(p.name for p in INPUTS)])
    overview.append(['Method', 'Merged by DOI, arXiv identifier or normalized title; transitive matches combined'])
    overview.append(['Caution', 'Original search.xlsx Overview/Queries are not a combined PRISMA audit; consult both originals'])
    overview.append(['Records across input sheets', len(entries)])
    overview.append(['Unique merged papers', len(merged)])
    overview.append(['Duplicate records removed', len(entries) - len(merged)])
    counts = Counter(s for s, _, _ in merged)
    for sheet in SHEETS:
        overview.append([sheet, counts[sheet]])
    overview.column_dimensions['A'].width = 34
    overview.column_dimensions['B'].width = 105

    cols = ['#'] + [h for h in all_headers if h != 'Missing groups']
    # Preserve original schema order; Missing groups only on no-abstract/excluded sheets.
    for sheet in SHEETS:
        ws = out.create_sheet(sheet)
        sheet_cols = cols.copy()
        if sheet != 'Reading list' and 'Missing groups' in all_headers:
            sheet_cols.insert(-1, 'Missing groups')
        ws.append(sheet_cols)
        items = [d for s, d, _ in merged if s == sheet]
        items.sort(key=lambda d: (-(int(d.get('Year')) if str(d.get('Year') or '').isdigit() else 0), str(d.get('Title') or '').lower()))
        for n, d in enumerate(items, 1):
            ws.append([n if h == '#' else d.get(h) for h in sheet_cols])
        ws.freeze_panes = 'C2'
        ws.auto_filter.ref = ws.dimensions
        for cell in ws[1]:
            cell.font = Font(bold=True, color='FFFFFF')
            cell.fill = PatternFill('solid', fgColor='305496')
        for col in ws.columns:
            name = col[0].value
            ws.column_dimensions[col[0].column_letter].width = 70 if name == 'Abstract' else (58 if name == 'Title' else 22)
    audit = out.create_sheet('Merge provenance')
    audit.append(['Title', 'Databases', 'Original files', 'Input records in cluster'])
    for (s, d, paths), cluster in zip(merged, grouped.values()):
        audit.append([d.get('Title'), d.get('Databases'), ', '.join(paths), len(cluster)])
    audit.column_dimensions['A'].width = 70
    audit.column_dimensions['B'].width = 35
    audit.column_dimensions['C'].width = 45
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    out.save(OUTPUT)
    print(f'Created: {OUTPUT}')
    print(f'Input rows: {len(entries)}; unique papers: {len(merged)}; duplicates: {len(entries)-len(merged)}')
    for sheet in SHEETS:
        print(f'{sheet}: {counts[sheet]}')

if __name__ == '__main__':
    main()

"""Conservative, evidence-based peer-review gate after title/abstract screening.

No database metadata or DOI is treated as proof of peer review. A human reviewer
records an auditable source and checks the publication version. Only verified
peer-reviewed papers with a current 'include' verdict enter the final list.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter
from datetime import date
from pathlib import Path

import openpyxl
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter

STATUSES = ('unverified', 'verified_peer_reviewed', 'verified_not_peer_reviewed')
FIELDS = ('ID', 'Paper fingerprint', 'Title', 'DOI', 'Venue', 'Venue type', 'Publication status',
          'Evidence URL', 'Evidence description', 'Verified version DOI', 'Reviewer', 'Verified on')


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _fingerprint(p: dict) -> str:
    data = [str(p.get(k) or '').strip() for k in ('ID', 'Title', 'DOI', 'Year', 'Venue')]
    return hashlib.sha256(json.dumps(data, ensure_ascii=False).encode('utf-8')).hexdigest()


def _papers(screening: Path) -> list[dict]:
    wb = openpyxl.load_workbook(screening, read_only=True, data_only=True)
    try:
        if 'Screening' not in wb:
            raise ValueError('Sheet "Screening" missing')
        it = wb['Screening'].iter_rows(values_only=True)
        header = next(it)
        required = {'ID', 'Verdict', 'Title', 'DOI', 'Year', 'Venue', 'Venue type'}
        if not required.issubset(set(header)):
            raise ValueError(f'Missing screening columns: {sorted(required - set(header))}')
        papers = [dict(zip(header, r)) for r in it if r and r[0]]
        ids = [str(p['ID']) for p in papers]
        if len(ids) != len(set(ids)):
            raise ValueError('Duplicate paper IDs in screening workbook')
        return papers
    finally:
        wb.close()


def prepare(screening: Path, evidence: Path) -> int:
    if evidence.exists():
        raise FileExistsError(f'Will not overwrite existing evidence: {evidence}')
    papers = _papers(screening)
    evidence.parent.mkdir(parents=True, exist_ok=True)
    with evidence.open('w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        for p in papers:
            w.writerow({'ID': p['ID'], 'Paper fingerprint': _fingerprint(p), 'Title': p['Title'],
                        'DOI': p.get('DOI') or '', 'Venue': p.get('Venue') or '',
                        'Venue type': p.get('Venue type') or '', 'Publication status': 'unverified'})
    return len(papers)


def _clean(value):
    if isinstance(value, str) and value.startswith(('=', '+', '-', '@')):
        return "'" + value
    return value


def finalize(screening: Path, evidence: Path, output: Path) -> dict:
    if output.resolve() in (screening.resolve(), evidence.resolve()):
        raise ValueError('Output must not overwrite inputs')
    if output.exists():
        raise FileExistsError(f'Will not overwrite existing final report: {output}')
    papers = _papers(screening)
    with evidence.open('r', encoding='utf-8-sig', newline='') as f:
        reader = csv.DictReader(f)
        if not set(FIELDS).issubset(reader.fieldnames or []):
            raise ValueError('Evidence CSV columns missing; create with publication prepare')
        entries = list(reader)
    by_id = {}
    for e in entries:
        key = (e.get('ID') or '').strip()
        if not key or key in by_id:
            raise ValueError(f'Missing or duplicate evidence ID: {key}')
        by_id[key] = e
    ids = {str(p['ID']) for p in papers}
    if set(by_id) != ids:
        raise ValueError(f'Evidence mismatch: missing={sorted(ids - set(by_id))}; extra={sorted(set(by_id) - ids)}')
    rows = []
    for p in papers:
        e = by_id[str(p['ID'])]
        if e['Paper fingerprint'] != _fingerprint(p):
            raise ValueError(f'Paper changed since evidence preparation: {p["ID"]}')
        status = (e.get('Publication status') or '').strip()
        if status not in STATUSES:
            raise ValueError(f'Invalid publication status for {p["ID"]}: {status!r}')
        if status != 'unverified':
            for field in ('Evidence URL', 'Evidence description', 'Reviewer', 'Verified on'):
                if not (e.get(field) or '').strip():
                    raise ValueError(f'{p["ID"]}: {field} required for verified status')
            url = e['Evidence URL'].strip()
            if not url.startswith(('https://', 'http://')):
                raise ValueError(f'{p["ID"]}: Evidence URL must be http(s)')
            try:
                date.fromisoformat(e['Verified on'].strip())
            except ValueError as exc:
                raise ValueError(f'{p["ID"]}: Verified on must be YYYY-MM-DD') from exc
        verdict = str(p.get('Verdict') or '').strip().lower()
        if verdict not in ('include', 'unsure', 'exclude'):
            raise ValueError(f'{p["ID"]}: invalid screening verdict {verdict!r}')
        destination = ('Final Reading List' if verdict == 'include' and status == 'verified_peer_reviewed'
                       else 'Manual Review' if verdict in ('include', 'unsure') and status == 'unverified'
                       else 'Not Included')
        rows.append((p, e, status, destination))
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    cols = ['ID', 'Screening verdict', 'Publication status', 'Title', 'Year', 'Venue', 'Venue type',
            'DOI', 'arXiv', 'URL', 'Evidence URL', 'Evidence description', 'Verified version DOI',
            'Reviewer', 'Verified on', 'Paper fingerprint']
    for sheet_name in ('Final Reading List', 'Manual Review', 'Not Included', 'Publication Evidence'):
        ws = wb.create_sheet(sheet_name)
        ws.append(cols)
        for c in ws[1]:
            c.font = Font(bold=True)
        for p, e, status, dest in rows:
            if sheet_name not in (dest, 'Publication Evidence'):
                continue
            ws.append([_clean(x) for x in (p['ID'], p['Verdict'], status, p['Title'], p.get('Year'),
                       p.get('Venue'), p.get('Venue type'), p.get('DOI'), p.get('arXiv'), p.get('URL'),
                       e.get('Evidence URL'), e.get('Evidence description'), e.get('Verified version DOI'),
                       e.get('Reviewer'), e.get('Verified on'), e.get('Paper fingerprint'))])
        ws.freeze_panes = 'D2'
        ws.auto_filter.ref = ws.dimensions
        for i, width in enumerate((12, 19, 29, 65, 9, 32, 18, 26, 20, 30, 42, 62, 26, 24, 17, 22), 1):
            ws.column_dimensions[get_column_letter(i)].width = width
    counts = Counter(dest for _, _, _, dest in rows)
    summary = wb.create_sheet('Quality Report', 0)
    for k, v in [('Input screening', str(screening)), ('Screening SHA256', _sha(screening)),
                 ('Evidence CSV', str(evidence)), ('Evidence SHA256', _sha(evidence)),
                 ('Generated on', date.today().isoformat()), ('Total papers', len(rows)),
                 ('Final peer-reviewed includes', counts['Final Reading List']),
                 ('Manual review', counts['Manual Review']), ('Not included', counts['Not Included']),
                 ('Policy', 'Only include + documented human verification; no automatic peer-review inference')]:
        summary.append([k, v])
    summary.column_dimensions['A'].width = 33
    summary.column_dimensions['B'].width = 100
    output.parent.mkdir(parents=True, exist_ok=True)
    wb.save(output)
    return {'total': len(rows), 'final': counts['Final Reading List'],
            'manual_review': counts['Manual Review'], 'not_included': counts['Not Included']}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description='Evidence-based peer-review gate for screening workbooks')
    sub = parser.add_subparsers(dest='command', required=True)
    a = sub.add_parser('prepare', help='create evidence CSV; never overwrites')
    a.add_argument('--screening', type=Path, required=True)
    a.add_argument('--evidence', type=Path, required=True)
    b = sub.add_parser('finalize', help='create audited final workbook; never overwrites')
    b.add_argument('--screening', type=Path, required=True)
    b.add_argument('--evidence', type=Path, required=True)
    b.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == 'prepare':
            print(f'{prepare(args.screening, args.evidence)} papers prepared: {args.evidence}')
        else:
            print(f'{args.output}: {finalize(args.screening, args.evidence, args.output)}')
    except (ValueError, FileExistsError, OSError) as exc:
        parser.exit(2, f'ERROR: {exc}\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

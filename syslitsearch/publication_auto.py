"""Conservative bibliographic enrichment for P0-02.

Crossref/OpenAlex identify publication versions, but NEVER prove peer review.
Output is a separate suggestions CSV; human-verified evidence CSV stays unchanged.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import time
from pathlib import Path
from urllib.parse import quote

import requests

from .publication import FIELDS

SUGGESTION_FIELDS = ('ID', 'Paper fingerprint', 'Lookup status', 'Matched DOI',
                     'Match method', 'Crossref title', 'Crossref venue', 'Crossref type',
                     'Crossref publisher', 'Crossref ISSN', 'Crossref URL',
                     'OpenAlex ID', 'OpenAlex title', 'OpenAlex venue', 'OpenAlex type',
                     'OpenAlex DOI', 'OpenAlex URL', 'Notes')
DOI_PATTERN = re.compile(r'^10\.\d{4,9}/\S+$', re.I)


def normalize_doi(value: str) -> str:
    value = (value or '').strip()
    value = re.sub(r'^https?://(?:dx\.)?doi\.org/', '', value, flags=re.I)
    value = re.sub(r'^doi:\s*', '', value, flags=re.I)
    return value.strip()


def _read_csv(path: Path, required: set[str]):
    with path.open(encoding='utf-8-sig', newline='') as f:
        reader = csv.DictReader(f)
        if not required.issubset(reader.fieldnames or []):
            raise ValueError(f'Missing CSV columns: {sorted(required - set(reader.fieldnames or []))}')
        return list(reader)


def _get(session, url, timeout, retries=2):
    for attempt in range(retries + 1):
        try:
            response = session.get(url, timeout=timeout, headers={'User-Agent': 'syslitsearch/2.0 (academic bibliographic enrichment)'})
            if response.status_code == 404:
                return None
            if response.status_code in (429, 500, 502, 503, 504) and attempt < retries:
                time.sleep(min(2 ** attempt, 4))
                continue
            response.raise_for_status()
            return response.json()
        except (requests.RequestException, ValueError):
            if attempt == retries:
                raise
            time.sleep(min(2 ** attempt, 4))
    return None


def lookup_doi(doi: str, session=None, timeout=20):
    """Fetch *only exact DOI* records; no fuzzy title matches."""
    doi = normalize_doi(doi)
    if not DOI_PATTERN.fullmatch(doi):
        raise ValueError('Invalid DOI')
    session = session or requests.Session()
    escaped = quote(doi, safe='')
    crossref = _get(session, 'https://api.crossref.org/works/' + escaped, timeout)
    openalex = _get(session, 'https://api.openalex.org/works/https://doi.org/' + escaped, timeout)
    c = (crossref or {}).get('message') or {}
    a = openalex or {}
    c_doi = normalize_doi(c.get('DOI') or '')
    a_doi = normalize_doi(a.get('doi') or '')
    if c and c_doi.lower() != doi.lower():
        raise ValueError('Crossref returned a different DOI')
    if a and a_doi.lower() != doi.lower():
        raise ValueError('OpenAlex returned a different DOI')
    return {
        'Lookup status': 'found' if c or a else 'not_found',
        'Matched DOI': doi if c or a else '',
        'Match method': 'exact_doi' if c or a else '',
        'Crossref title': (c.get('title') or [''])[0],
        'Crossref venue': (c.get('container-title') or [''])[0],
        'Crossref type': c.get('type') or '',
        'Crossref publisher': c.get('publisher') or '',
        'Crossref ISSN': '; '.join(c.get('ISSN') or []),
        'Crossref URL': c.get('URL') or '',
        'OpenAlex ID': a.get('id') or '',
        'OpenAlex title': a.get('title') or '',
        'OpenAlex venue': ((a.get('primary_location') or {}).get('source') or {}).get('display_name') or '',
        'OpenAlex type': a.get('type') or '',
        'OpenAlex DOI': a.get('doi') or '',
        'OpenAlex URL': a.get('id') or '',
    }


def enrich(evidence: Path, output: Path, *, session=None, timeout=20, delay=0.1, max_records=None):
    if output.resolve() == evidence.resolve() or output.exists():
        raise FileExistsError('Refusing to overwrite evidence or existing suggestions')
    rows = _read_csv(evidence, set(FIELDS))
    ids = [r['ID'] for r in rows]
    if len(ids) != len(set(ids)):
        raise ValueError('Duplicate evidence IDs')
    session = session or requests.Session()
    cache = {}
    result = []
    for row in rows[:max_records] if max_records is not None else rows:
        item = {'ID': row['ID'], 'Paper fingerprint': row['Paper fingerprint']}
        doi = normalize_doi(row.get('Verified version DOI') or row.get('DOI') or '')
        if not doi or not DOI_PATTERN.fullmatch(doi):
            item.update({'Lookup status': 'missing_or_invalid_doi', 'Notes': 'DOI requires manual discovery; no title-based guess'})
        else:
            if doi not in cache:
                try:
                    cache[doi] = lookup_doi(doi, session=session, timeout=timeout)
                except (requests.RequestException, ValueError) as exc:
                    cache[doi] = {'Lookup status': 'lookup_error', 'Notes': f'{type(exc).__name__}: {str(exc)[:180]}'}
                if delay:
                    time.sleep(delay)
            item.update(cache[doi])
        result.append(item)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=SUGGESTION_FIELDS, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(result)
    return {'processed': len(result), 'found': sum(r.get('Lookup status') == 'found' for r in result),
            'manual_or_error': sum(r.get('Lookup status') != 'found' for r in result)}


def main(argv=None):
    parser = argparse.ArgumentParser(description='DOI-based Crossref/OpenAlex enrichment; no automatic peer-review certification')
    parser.add_argument('--evidence', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--timeout', type=float, default=20)
    parser.add_argument('--delay', type=float, default=0.1)
    parser.add_argument('--max-records', type=int)
    args = parser.parse_args(argv)
    try:
        print(json.dumps(enrich(args.evidence, args.output, timeout=args.timeout, delay=args.delay,
                                max_records=args.max_records), ensure_ascii=False))
    except (OSError, ValueError) as exc:
        parser.exit(2, f'ERROR: {exc}\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

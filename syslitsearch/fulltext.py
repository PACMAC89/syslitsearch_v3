"""Conservative open-access full-text discovery and extraction for review candidates.

Discovery never changes human eligibility decisions. No paywall bypass.
"""
from __future__ import annotations
import csv
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote, urlparse

import requests

FIELDS = ['ID','Title','DOI','screening_verdict','retrieval_status','fulltext_decision','exclusion_reason','reviewer','decision_date','notes']
OA_FIELDS = ['ID','Title','DOI','lookup_status','source','landing_url','pdf_url','local_pdf','local_text','extraction_status','characters','error']

def _doi(raw):
    raw = str(raw or '').strip()
    raw = re.sub(r'^https?://(?:dx\.)?doi\.org/', '', raw, flags=re.I)
    return raw if re.fullmatch(r'10\.\d{4,9}/\S+', raw, re.I) else ''

def _safe_url(url):
    """Limit automatic network fetching to public HTTPS destinations."""
    if not isinstance(url, str): return ''
    u = urlparse(url)
    if u.scheme != 'https' or not u.hostname or u.username or u.password: return ''
    host = u.hostname.lower()
    if host in ('localhost',) or host.endswith(('.local','.internal')): return ''
    # Discovery URLs are returned for user inspection, never automatically fetched here.
    return url

def _openalex(doi, session):
    url = 'https://api.openalex.org/works/https://doi.org/' + quote(doi, safe='')
    response = session.get(url, timeout=20)
    if response.status_code == 404: return {'lookup_status':'not_found'}
    response.raise_for_status()
    data = response.json()
    candidates = [data.get('best_oa_location'), *(data.get('locations') or [])]
    pdf = ''
    landing = ''
    for loc in candidates:
        if not isinstance(loc,dict): continue
        landing = landing or _safe_url(loc.get('landing_page_url'))
        pdf = pdf or _safe_url(loc.get('pdf_url'))
    return {'lookup_status':'found','source':'OpenAlex','landing_url':landing,'pdf_url':pdf}

def _read_csv(path):
    with path.open('r', encoding='utf-8-sig', newline='') as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames or not set(FIELDS).issubset(reader.fieldnames):
            raise ValueError('Unexpected fulltext_decisions.csv schema')
        rows = list(reader)
    ids = [x['ID'] for x in rows]
    if len(ids) != len(set(ids)): raise ValueError('Duplicate candidate IDs')
    return rows

def discover(decisions_path: Path, output_dir: Path, limit: int = 10, session=None):
    """Discover OA links for up to limit pending records; write a separate append-only audit CSV.

    Existing results are preserved, including failures. Re-running only processes new IDs.
    """
    if limit < 1: raise ValueError('limit must be >= 1')
    rows = _read_csv(decisions_path)
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / 'fulltext_discovery.csv'
    existing = []
    if path.exists():
        with path.open(encoding='utf-8-sig', newline='') as f:
            existing = list(csv.DictReader(f))
    done = {x['ID'] for x in existing}
    todo = [x for x in rows if x['ID'] not in done and x['fulltext_decision'].strip().lower() == 'pending'][:limit]
    session = session or requests.Session()
    added = []
    for item in todo:
        record = {k:'' for k in OA_FIELDS}
        record.update({k:item.get(k,'') for k in ('ID','Title','DOI')})
        doi = _doi(item.get('DOI'))
        if not doi:
            record['lookup_status'] = 'missing_or_invalid_doi'
        else:
            try:
                record.update(_openalex(doi, session))
            except (requests.RequestException, ValueError, KeyError) as exc:
                record['lookup_status'] = 'lookup_error'
                record['error'] = f'{type(exc).__name__}: {str(exc)[:240]}'
        added.append(record)
    if added:
        # Rewriting only the machine-generated discovery file; never the human decision CSV.
        tmp = path.with_suffix('.csv.tmp')
        with tmp.open('w', encoding='utf-8-sig', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=OA_FIELDS)
            writer.writeheader(); writer.writerows(existing + added)
        tmp.replace(path)
    return {'candidate_count':len(rows),'previously_discovered':len(existing),'newly_processed':len(added),
            'status_counts':{k:sum(r['lookup_status']==k for r in added) for k in sorted({r['lookup_status'] for r in added})},
            'discovery_csv':str(path),'human_decisions_unchanged':True,
            'note':'Links are leads, not proof of accessible full text. No PDFs were downloaded.'}

def extract_local(pdf_dir: Path, output_dir: Path, limit: int = 10):
    """Extract full text from user-supplied PDFs named <ID>.pdf; never overwrite text."""
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise ValueError('Install PDF extraction dependency: python -m pip install pypdf') from exc
    output_dir.mkdir(parents=True, exist_ok=True)
    results=[]
    for pdf in sorted(pdf_dir.glob('*.pdf'))[:limit]:
        if not re.fullmatch(r'[A-Za-z0-9_-]{1,80}', pdf.stem):
            results.append({'file':pdf.name,'status':'invalid_filename'}); continue
        target=output_dir / (pdf.stem+'.txt')
        if target.exists():
            results.append({'file':pdf.name,'status':'already_exists'}); continue
        try:
            reader=PdfReader(str(pdf))
            pages=[page.extract_text() or '' for page in reader.pages]
            content='\n\n'.join(f'=== PAGE {i+1} ===\n{t}' for i,t in enumerate(pages))
            if not content.strip() or sum(len(t.strip()) for t in pages)<100:
                results.append({'file':pdf.name,'status':'no_extractable_text'}); continue
            target.write_text(content, encoding='utf-8')
            results.append({'file':pdf.name,'status':'extracted','pages':len(pages),'characters':len(content),'sha256':hashlib.sha256(pdf.read_bytes()).hexdigest()})
        except Exception as exc:
            results.append({'file':pdf.name,'status':'extraction_error','error':str(exc)[:200]})
    return {'files':results,'note':'Scanned/image-only PDFs may need OCR. Extracted text is not an eligibility decision.'}

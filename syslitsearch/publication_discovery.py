"""Conservative OpenAlex title-based discovery of possible published versions.

Candidates are suggestions, never DOI replacements or peer-review evidence.
"""
from __future__ import annotations
import argparse
import csv
import json
import re
from difflib import SequenceMatcher
import time
from pathlib import Path
from urllib.parse import quote
import requests
from .publication import FIELDS
from .publication_verify import read_csv
from .publication_auto import normalize_doi

FIELDS_OUT = ('ID','Paper fingerprint','Original DOI','Candidate DOI','Candidate title',
              'Candidate year','Candidate type','Candidate venue','Candidate OpenAlex ID',
              'Title match','Candidate status','Reason')
PREPRINT_DOI = re.compile(r'^10\.48550/arxiv\.', re.I)
EXCLUDED = {'preprint','posted-content','dataset','book','book-chapter','editorial','letter','other'}

def canonical_title(title):
    return re.sub(r'[^\w]+',' ',(title or '').casefold(),flags=re.UNICODE).strip()

def discover(evidence, output, *, session=None, timeout=20, delay=.1, max_records=None,
             max_candidates=5, preprints_only=False, min_title_similarity=.86):
    evidence=Path(evidence);output=Path(output)
    if output.exists() or output.resolve()==evidence.resolve():
        raise FileExistsError('Refusing to overwrite inputs or existing output')
    if max_records is not None and max_records < 1: raise ValueError('max_records must be >= 1')
    if not 1 <= max_candidates <= 25: raise ValueError('max_candidates must be between 1 and 25')
    if not .5 <= min_title_similarity <= 1: raise ValueError('min_title_similarity must be between 0.5 and 1')
    rows=read_csv(evidence,FIELDS)
    session=session or requests.Session()
    output_rows=[]
    for paper in rows[:max_records]:
        title=(paper.get('Title') or '').strip()
        original_doi=normalize_doi(paper.get('DOI') or '')
        if preprints_only and not PREPRINT_DOI.match(original_doi) and 'arxiv' not in (paper.get('Venue') or '').casefold():
            output_rows.append({'ID':paper['ID'],'Paper fingerprint':paper['Paper fingerprint'],
                'Original DOI':original_doi,'Candidate status':'not_applicable',
                'Reason':'Published-version discovery restricted to preprints'})
            continue
        base={'ID':paper['ID'],'Paper fingerprint':paper['Paper fingerprint'],
              'Original DOI':normalize_doi(paper.get('DOI') or '')}
        if not title:
            output_rows.append({**base,'Candidate status':'manual_title','Reason':'Missing source title'})
            continue
        try:
            url='https://api.openalex.org/works?search='+quote(title,safe='')+'&per-page=25'
            response=session.get(url,timeout=timeout,headers={'User-Agent':'syslitsearch/2.0 (publication candidate discovery)'})
            response.raise_for_status()
            results=response.json().get('results') or []
            if not isinstance(results,list): raise ValueError('Invalid OpenAlex results')
            candidates=[]
            for work in results:
                if not isinstance(work,dict): continue
                candidate_title=work.get('title') or ''
                # Similarity only proposes candidates. It NEVER proves publication identity.
                exact=canonical_title(candidate_title)==canonical_title(title)
                similarity=SequenceMatcher(None,canonical_title(candidate_title),canonical_title(title)).ratio()
                if not exact and similarity < min_title_similarity: continue
                doi=normalize_doi(work.get('doi') or '')
                original=base['Original DOI']
                if not doi or doi.casefold()==original.casefold(): continue
                ptype=(work.get('type') or '').casefold()
                location=work.get('primary_location') or {}
                venue=((location.get('source') or {}).get('display_name') or '')
                status='candidate_needs_verification' if exact else 'possible_title_variant'
                reason=('Exact title candidate' if exact else f'Approximate title candidate (similarity {similarity:.3f})') + '; independently verify authors, year, version, track and peer review'
                if ptype in EXCLUDED or doi.casefold().startswith('10.48550/arxiv.'):
                    status='non_qualifying_candidate'
                    reason='Candidate type or DOI suggests a non-qualifying version'
                candidates.append({**base,'Candidate DOI':doi,'Candidate title':candidate_title,
                    'Candidate year':work.get('publication_year') or '',
                    'Candidate type':ptype,'Candidate venue':venue,
                    'Candidate OpenAlex ID':work.get('id') or '',
                    'Title match':'exact_normalized' if exact else f'approximate:{similarity:.3f}','Candidate status':status,'Reason':reason})
            # Deduplicate DOI, deterministic order; don't silently select one version.
            seen=set()
            for c in sorted(candidates,key=lambda r:(r['Candidate status']!='candidate_needs_verification',str(r['Candidate DOI']))):
                key=c['Candidate DOI'].casefold()
                if key in seen:continue
                seen.add(key)
                if len(seen)>max_candidates:break
                output_rows.append(c)
            if not seen:
                output_rows.append({**base,'Candidate status':'no_title_candidate',
                                    'Reason':'No alternate DOI candidate meeting title threshold; manual search needed'})
        except (requests.RequestException,ValueError,TypeError) as exc:
            output_rows.append({**base,'Candidate status':'lookup_error',
                                'Reason':f'{type(exc).__name__}: {str(exc)[:160]}'})
        if delay:time.sleep(delay)
    output.parent.mkdir(parents=True,exist_ok=True)
    with output.open('w',encoding='utf-8-sig',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=FIELDS_OUT,extrasaction='ignore');writer.writeheader();writer.writerows(output_rows)
    from collections import Counter
    return {'papers':min(len(rows),max_records) if max_records is not None else len(rows),
            'rows':len(output_rows),'statuses':dict(Counter(r['Candidate status'] for r in output_rows))}

def main(argv=None):
    p=argparse.ArgumentParser(description='Find possible published versions; NEVER certifies peer review')
    p.add_argument('--evidence',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--max-records',type=int);p.add_argument('--max-candidates',type=int,default=5)
    p.add_argument('--timeout',type=float,default=20);p.add_argument('--delay',type=float,default=.1)
    p.add_argument('--preprints-only',action='store_true')
    p.add_argument('--min-title-similarity',type=float,default=.86)
    a=p.parse_args(argv)
    try:print(json.dumps(discover(a.evidence,a.output,max_records=a.max_records,max_candidates=a.max_candidates,
                                  timeout=a.timeout,delay=a.delay,preprints_only=a.preprints_only,min_title_similarity=a.min_title_similarity),ensure_ascii=False))
    except (OSError,ValueError) as exc:p.exit(2,f'ERROR: {exc}\n')
    return 0
if __name__=='__main__':raise SystemExit(main())

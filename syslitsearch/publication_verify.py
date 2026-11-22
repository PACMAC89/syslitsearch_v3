"""P0-02c: conservative publication triage, NOT peer-review certification.

Consumes P0-02a evidence and P0-02b metadata; writes suggestions only.
A curated, human-reviewed venue policy registry can suggest verification candidates,
but never changes the evidence CSV or certifies an individual paper automatically.
"""
from __future__ import annotations
import argparse
import csv
import json
import re
from pathlib import Path
from .publication import FIELDS
from .publication_auto import SUGGESTION_FIELDS, normalize_doi

OUT_FIELDS = ('ID', 'Paper fingerprint', 'Decision suggestion', 'Reason',
              'Matched DOI', 'Publication type', 'Venue', 'Policy ID',
              'Policy URL', 'Required human action', 'Publication year', 'Crossref title', 'OpenAlex title', 'Crossref ISSN', 'Bibliographic conflict')
POLICY_FIELDS = ('Policy ID', 'Venue exact', 'ISSN exact', 'Year from', 'Year to',
                 'Publication type exact', 'Policy URL', 'Review procedure',
                 'Policy verified by', 'Policy verified on')
PREPRINT_DOI = re.compile(r'^10\.48550/arxiv\.', re.I)
ABSTRACT_HINT = re.compile(r'(?:^|[./_-])(?:abstract|poster|supplement)(?:[./_-]|$)', re.I)

def read_csv(path, required):
    with Path(path).open(encoding='utf-8-sig', newline='') as f:
        reader=csv.DictReader(f)
        missing=set(required)-set(reader.fieldnames or [])
        if missing: raise ValueError(f'{path}: missing columns {sorted(missing)}')
        rows=list(reader)
    ids=[(r.get('ID') or '').strip() for r in rows]
    if not all(ids) or len(ids)!=len(set(ids)):
        raise ValueError(f'{path}: missing or duplicate IDs')
    return rows

def load_policies(path):
    if path is None: return []
    with Path(path).open(encoding='utf-8-sig', newline='') as f:
        reader=csv.DictReader(f)
        missing=set(POLICY_FIELDS)-set(reader.fieldnames or [])
        if missing: raise ValueError(f'Policy columns missing: {sorted(missing)}')
        policies=list(reader)
    ids = [(p.get('Policy ID') or '').strip() for p in policies]
    if len(ids) != len(set(ids)):
        raise ValueError('Duplicate policy IDs')
    for p in policies:
        required = [k for k in POLICY_FIELDS if k != 'ISSN exact']
        if not all((p.get(k) or '').strip() for k in required):
            raise ValueError('Incomplete policy entry; all policy fields required')
        ptype = p['Publication type exact'].strip().casefold()
        if ptype not in ('journal-article', 'proceedings-article'):
            raise ValueError('Policy type must be journal-article or proceedings-article')
        if ptype == 'journal-article' and not (p.get('ISSN exact') or '').strip():
            raise ValueError('Journal policy requires ISSN exact')
        if not p['Policy URL'].startswith('https://'):
            raise ValueError('Policy URL must be HTTPS')
        if not (p['Year from'].isdigit() and p['Year to'].isdigit() and int(p['Year from'])<=int(p['Year to'])):
            raise ValueError('Invalid policy year range')
        from datetime import date
        date.fromisoformat(p['Policy verified on'])
    return policies

def classify(e, m, policies=()):
    doi=normalize_doi(e.get('Verified version DOI') or e.get('DOI') or '')
    matched=normalize_doi(m.get('Matched DOI') or '')
    venue=(m.get('Crossref venue') or m.get('OpenAlex venue') or '').strip()
    ptype=(m.get('Crossref type') or m.get('OpenAlex type') or '').strip().lower()
    base={'ID':e['ID'], 'Paper fingerprint':e['Paper fingerprint'], 'Matched DOI':matched,
          'Publication type':ptype, 'Venue':venue, 'Policy ID':'', 'Policy URL':'',
          'Publication year':(e.get('Year') or '').strip(),
          'Crossref title':m.get('Crossref title') or '', 'OpenAlex title':m.get('OpenAlex title') or '',
          'Crossref ISSN':m.get('Crossref ISSN') or '', 'Bibliographic conflict':''}
    def result(status, reason, action, policy=None):
        return dict(base, **{'Decision suggestion':status, 'Reason':reason,
                            'Required human action':action,
                            'Policy ID':(policy or {}).get('Policy ID',''),
                            'Policy URL':(policy or {}).get('Policy URL','')})
    if m.get('Lookup status')!='found':
        return result('manual_bibliography', 'No exact DOI metadata match', 'Find and validate publication DOI')
    if not doi or doi.casefold()!=matched.casefold():
        return result('manual_bibliography', 'Metadata DOI differs from evidence DOI', 'Resolve version/DOI mismatch')
    ct=(m.get('Crossref title') or '').strip()
    ot=(m.get('OpenAlex title') or '').strip()
    def norm_title(v): return re.sub(r'[^a-z0-9]+', '', v.casefold())
    if ct and ot and norm_title(ct)!=norm_title(ot):
        base['Bibliographic conflict']='Crossref/OpenAlex titles differ'
        return result('manual_bibliography', 'Crossref and OpenAlex titles disagree', 'Verify bibliographic identity and publication version')
    if PREPRINT_DOI.match(doi) or ptype=='preprint' or 'arxiv' in venue.casefold():
        return result('search_published_version', 'Preprint metadata is not peer-review evidence', 'Locate separately published peer-reviewed version')
    if ABSTRACT_HINT.search(doi) or re.search(r'\.\d{3,5}$', doi) and 'sleep/' in doi.casefold():
        return result('manual_contribution_type', 'DOI suggests an abstract or supplement', 'Check full text and contribution type')
    if ptype not in ('journal-article','proceedings-article','article','conference-paper'):
        return result('manual_contribution_type', 'Publication type does not establish a full research paper', 'Inspect contribution type')
    # Metadata alone is insufficient. Even a matched registry policy requires
    # independent per-paper verification; registry never sets verified status.
    matches=[]
    for p in policies:
        if venue.casefold()!=p['Venue exact'].strip().casefold(): continue
        if ptype!=p['Publication type exact'].strip().casefold(): continue
        policy_issn = p['ISSN exact'].strip()
        metadata_issns = [s.strip().casefold() for s in (m.get('Crossref ISSN') or '').split(';') if s.strip()]
        # An empty ISSN is permitted only for proceedings policies, which
        # must still match the exact venue, type and publication year.
        if policy_issn and policy_issn.casefold() not in metadata_issns: continue
        year=(e.get('Year') or '').strip()
        if not year.isdigit() or not (int(p['Year from'])<=int(year)<=int(p['Year to'])): continue
        matches.append(p)
    if len(matches)==1:
        return result('policy_candidate', 'Curated venue policy matches metadata; individual article still unverified',
                      'Check article track/type, version, and policy source; then record human evidence', matches[0])
    if len(matches)>1:
        return result('manual_policy_ambiguous', 'Multiple venue policies match', 'Resolve overlapping policy entries')
    return result('manual_peer_review', 'No matching curated venue policy; DOI/type alone cannot prove peer review',
                  'Locate official review policy for year and article type')

def triage(evidence, metadata, output, policies=None, screening=None):
    evidence=Path(evidence);metadata=Path(metadata);output=Path(output)
    if output.resolve() in (evidence.resolve(),metadata.resolve()) or output.exists():
        raise FileExistsError('Refusing to overwrite inputs or existing output')
    es=read_csv(evidence, FIELDS)
    ms=read_csv(metadata, SUGGESTION_FIELDS)
    em={e['ID']:e for e in es}
    if screening is not None:
        from .publication import _papers, _fingerprint
        paper_map={str(p['ID']):p for p in _papers(Path(screening))}
        if set(paper_map)!=set(em):
            raise ValueError('Screening/evidence ID mismatch')
        for paper_id, e in em.items():
            p=paper_map[paper_id]
            if e['Paper fingerprint']!=_fingerprint(p):
                raise ValueError(f'Screening/evidence fingerprint mismatch: {paper_id}')
            e['Year']=str(p.get('Year') or '').strip()
    registry=load_policies(policies) if policies else []
    result=[]
    for m in ms:
        e=em.get(m['ID'])
        if e is None: raise ValueError(f'Unknown metadata ID {m["ID"]}')
        if e['Paper fingerprint']!=m['Paper fingerprint']:
            raise ValueError(f'Fingerprint mismatch: {m["ID"]}')
        result.append(classify(e,m,registry))
    output.parent.mkdir(parents=True,exist_ok=True)
    with output.open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=OUT_FIELDS);w.writeheader();w.writerows(result)
    from collections import Counter
    return {'processed':len(result),'suggestions':dict(Counter(r['Decision suggestion'] for r in result))}

def main(argv=None):
    p=argparse.ArgumentParser(description='Conservative peer-review triage; never certifies or changes evidence')
    p.add_argument('--evidence',type=Path,required=True)
    p.add_argument('--metadata',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--policies',type=Path)
    p.add_argument('--screening',type=Path,help='Original screening workbook for verified publication years')
    a=p.parse_args(argv)
    try: print(json.dumps(triage(a.evidence,a.metadata,a.output,a.policies,a.screening),ensure_ascii=False))
    except (OSError,ValueError) as exc: p.exit(2,f'ERROR: {exc}\n')
    return 0
if __name__=='__main__': raise SystemExit(main())

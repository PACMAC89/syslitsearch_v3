"""Automated, auditable discovery of venue-policy *leads*, never certification.

Uses exact DOI metadata already collected and official publisher/venue landing-page
candidates. A link is not evidence that a specific paper was peer reviewed.
"""
from __future__ import annotations
import argparse
import csv
import json
from pathlib import Path
from urllib.parse import quote
import requests
from .publication_auto import _get, SUGGESTION_FIELDS

FIELDS = ('ID','Paper fingerprint','DOI','Venue','Publication type','ISSN',
          'Official source URL','Source kind','Policy search URL','Review status',
          'Required follow-up')

# Whitelist contains only known official journal policy landing pages. These
# URLs are *candidates* and are not asserted to cover a specific article/year.
OFFICIAL_POLICY_LEADS = {
    ('information','journal-article','2078-2489'):
        'https://www.mdpi.com/journal/information/instructions',
}

def _venue_homepage(m, session, timeout):
    """Fetch OpenAlex source homepage for the *exact* work source ID, if any."""
    work_id=(m.get('OpenAlex ID') or '').strip()
    if not work_id.startswith('https://openalex.org/W'):
        return ''
    data=_get(session,'https://api.openalex.org/works/'+quote(work_id.rsplit('/',1)[-1]),timeout)
    source=((data or {}).get('primary_location') or {}).get('source') or {}
    homepage=(source.get('homepage_url') or '').strip()
    return homepage if homepage.startswith('https://') else ''

def discover(metadata: Path, output: Path, *, session=None, timeout=20, fetch_homepages=False):
    metadata=Path(metadata);output=Path(output)
    if output.exists() or output.resolve()==metadata.resolve():
        raise FileExistsError('Refusing to overwrite input or output')
    with metadata.open(encoding='utf-8-sig',newline='') as f:
        reader=csv.DictReader(f)
        missing=set(SUGGESTION_FIELDS)-set(reader.fieldnames or [])
        if missing: raise ValueError(f'Missing metadata columns: {sorted(missing)}')
        rows=list(reader)
    session=session or requests.Session()
    results=[]
    for m in rows:
        venue=(m.get('Crossref venue') or m.get('OpenAlex venue') or '').strip()
        ptype=(m.get('Crossref type') or m.get('OpenAlex type') or '').strip()
        issns=[x.strip() for x in (m.get('Crossref ISSN') or '').split(';') if x.strip()]
        lead=next((url for (v,t,i),url in OFFICIAL_POLICY_LEADS.items()
                   if v==venue.casefold() and t==ptype.casefold() and i in issns),'')
        kind='curated_official_policy_lead' if lead else ''
        if not lead and fetch_homepages and m.get('Lookup status')=='found':
            try:
                lead=_venue_homepage(m,session,timeout)
                if lead: kind='openalex_source_homepage_not_policy'
            except (requests.RequestException,ValueError):
                kind='source_homepage_lookup_error'
        status='requires_review' if m.get('Lookup status')=='found' else 'metadata_unresolved'
        results.append({'ID':m.get('ID',''),'Paper fingerprint':m.get('Paper fingerprint',''),
                        'DOI':m.get('Matched DOI',''),'Venue':venue,'Publication type':ptype,
                        'ISSN':'; '.join(issns),'Official source URL':lead,'Source kind':kind,
                        'Policy search URL':'https://www.google.com/search?q='+quote('"'+venue+'" peer review policy '+ptype),
                        'Review status':status,
                        'Required follow-up':'Verify policy scope, publication year, track and individual contribution; do not auto-certify'})
    output.parent.mkdir(parents=True,exist_ok=True)
    with output.open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=FIELDS);w.writeheader();w.writerows(results)
    return {'processed':len(results),'official_policy_leads':sum(r['Source kind']=='curated_official_policy_lead' for r in results),
            'source_homepage_leads':sum(r['Source kind']=='openalex_source_homepage_not_policy' for r in results),
            'certified':0}

def main(argv=None):
    p=argparse.ArgumentParser(description='Discover policy leads without certifying peer review')
    p.add_argument('--metadata',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True)
    p.add_argument('--fetch-homepages',action='store_true')
    a=p.parse_args(argv)
    try: print(json.dumps(discover(a.metadata,a.out,fetch_homepages=a.fetch_homepages)))
    except (OSError,ValueError) as exc:p.exit(2,f'ERROR: {exc}\n')
if __name__=='__main__':main()

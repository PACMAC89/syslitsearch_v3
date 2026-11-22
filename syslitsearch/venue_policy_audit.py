"""Offline venue-level policy review queue from existing metadata and leads.

No network, no certification. Reuses one review task across papers only when
venue, publication type and ISSN agree; proceedings still require year/track.
"""
from __future__ import annotations
import argparse
import csv
import json
from collections import defaultdict, Counter
from pathlib import Path

COLUMNS = ('Venue key','Venue','Publication type','ISSN','Year','Paper count','Paper IDs',
           'Official source URL','Source kind','Policy URL verified','Review procedure',
           'Track / contribution scope','Verified by','Verified on','Review decision',
           'Notes')

def rows(path):
    with Path(path).open(encoding='utf-8-sig', newline='') as f:
        reader=csv.DictReader(f)
        result=list(reader)
        if not {'ID','Paper fingerprint'}.issubset(reader.fieldnames or []):
            raise ValueError(f'{path}: ID and fingerprint required')
        if len({r['ID'] for r in result})!=len(result):
            raise ValueError(f'{path}: duplicate IDs')
        return result

def build(metadata, leads, output):
    metadata=Path(metadata); leads=Path(leads); output=Path(output)
    if output.exists() or output.resolve() in (metadata.resolve(),leads.resolve()):
        raise FileExistsError('Refusing to overwrite inputs or existing output')
    md=rows(metadata); lead_rows=rows(leads)
    ls={r['ID']:r for r in lead_rows}
    if set(ls)!=set(r['ID'] for r in md):
        raise ValueError('Lead and metadata IDs do not match')
    groups=defaultdict(list)
    for m in md:
        l=ls[m['ID']]
        if m['Paper fingerprint']!=l['Paper fingerprint']:
            raise ValueError(f"Fingerprint mismatch for {m['ID']}")
        venue=(l.get('Venue') or '').strip()
        kind=(l.get('Publication type') or '').strip().lower()
        issn=';'.join(sorted(x.strip().lower() for x in (l.get('ISSN') or '').split(';') if x.strip()))
        # No venue means there is no defensible venue-level grouping.
        # Proceedings are separated by year only when metadata actually includes it.
        year=(m.get('Publication year') or '').strip() if 'proceedings' in kind else ''
        key=(venue.casefold(),kind,issn,year) if venue else ('missing:'+m['ID'],kind,issn,year)
        groups[key].append((m,l))
    result=[]
    for key,items in sorted(groups.items(),key=lambda kv:(-len(kv[1]),str(kv[0]))):
        m,l=items[0]
        urls={x.get('Official source URL','').strip() for _,x in items if x.get('Official source URL','').strip()}
        kinds={x.get('Source kind','').strip() for _,x in items if x.get('Source kind','').strip()}
        result.append({'Venue key':' | '.join(key),'Venue':l.get('Venue',''),
                       'Publication type':l.get('Publication type',''),'ISSN':l.get('ISSN',''),
                       'Year':key[3], 'Paper count':len(items),
                       'Paper IDs':'; '.join(x['ID'] for x,_ in items),
                       'Official source URL':'; '.join(sorted(urls)),
                       'Source kind':'; '.join(sorted(kinds)),
                       'Policy URL verified':'','Review procedure':'',
                       'Track / contribution scope':'','Verified by':'','Verified on':'',
                       'Review decision':'unverified',
                       'Notes':'Policy lead is not peer-review proof; check publication version, year, track, article type.'})
    output.parent.mkdir(parents=True,exist_ok=True)
    with output.open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=COLUMNS);w.writeheader();w.writerows(result)
    return {'papers':len(md),'venue_review_groups':len(result),
            'groups_with_official_leads':sum(bool(r['Official source URL']) for r in result),
            'certified':0,'output':str(output)}

def main(argv=None):
    p=argparse.ArgumentParser(description='Group existing publication leads for venue-level evidence review')
    p.add_argument('--metadata',type=Path,required=True)
    p.add_argument('--leads',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True)
    a=p.parse_args(argv)
    try: print(json.dumps(build(a.metadata,a.leads,a.out),ensure_ascii=False,indent=2))
    except (OSError,ValueError) as e:p.error(str(e))
if __name__=='__main__':main()

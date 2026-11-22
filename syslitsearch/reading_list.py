"""Auditable, non-destructive title/abstract reading-list export.

Venue type is NOT peer-review certification. Human evidence is the only path
into verified status. This is a provisional reading list, not PRISMA inclusion.
"""
from __future__ import annotations
import argparse
import csv
import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.utils import get_column_letter
from .publication import _papers, _fingerprint, FIELDS, STATUSES
from .publication_verify import read_csv


def _sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def _index(path, required):
    if not path: return {}
    return {str(r['ID']):r for r in read_csv(path, required)}


def _safe(v):
    if v is None: return ''
    if isinstance(v,str) and v.startswith(('=','+','-','@')): return "'"+v
    return v


def _add_sheet(wb, name, columns, rows):
    ws=wb.create_sheet(name)
    ws.append(columns)
    for row in rows: ws.append([_safe(x) for x in row])
    ws.freeze_panes='C2'
    ws.auto_filter.ref=ws.dimensions
    ws.row_dimensions[1].height=30
    for cell in ws[1]:
        cell.font=Font(bold=True,color='FFFFFF')
        cell.fill=PatternFill('solid',fgColor='193650')
        cell.alignment=Alignment(wrap_text=True)
    for j,col in enumerate(columns,1):
        width=70 if col in ('Title','Reason','Evidence description','Abstract') else 42 if 'URL' in col or 'Link' in col else 23
        ws.column_dimensions[get_column_letter(j)].width=width
    return ws


def export(screening, output, *, evidence=None, metadata=None, triage=None,
           keywords=None, criteria=None, prisma=None):
    screening=Path(screening); output=Path(output)
    inputs={'screening':screening,'evidence':Path(evidence) if evidence else None,
            'metadata':Path(metadata) if metadata else None,
            'triage':Path(triage) if triage else None,
            'keywords':Path(keywords) if keywords else None,
            'criteria':Path(criteria) if criteria else None,
            'prisma':Path(prisma) if prisma else None}
    for name,p in inputs.items():
        if p and not p.is_file(): raise FileNotFoundError(f'{name}: {p}')
        if p and output.resolve()==p.resolve(): raise ValueError('Output cannot overwrite input')
    if output.exists(): raise FileExistsError(f'Output already exists: {output}')
    papers=_papers(screening)
    ev=_index(evidence,FIELDS)
    md=_index(metadata,('ID','Paper fingerprint','Lookup status','Crossref type','OpenAlex type'))
    tr=_index(triage,('ID','Paper fingerprint','Decision suggestion'))
    ids={str(p['ID']) for p in papers}
    for label,index in [('evidence',ev),('metadata',md),('triage',tr)]:
        if index and not set(index).issubset(ids): raise ValueError(f'{label}: unknown paper IDs')
        for p in papers:
            r=index.get(str(p['ID']))
            if r and r.get('Paper fingerprint')!=_fingerprint(p):
                raise ValueError(f'{label}: fingerprint mismatch for {p["ID"]}')
    ranked=[]; unsure=[]; excluded=[]; audit=[]; evidence_rows=[]; counts=Counter()
    for p in papers:
        pid=str(p['ID']); v=str(p.get('Verdict') or '').strip().lower()
        if v not in ('include','unsure','exclude'): raise ValueError(f'Invalid verdict: {pid}')
        e=ev.get(pid,{}) ; m=md.get(pid,{}) ; t=tr.get(pid,{})
        raw_status=(e.get('Publication status') or 'unverified').strip()
        if raw_status not in STATUSES: raise ValueError(f'Invalid evidence status: {pid}')
        if raw_status!='unverified':
            from datetime import date
            for key in ('Evidence URL','Evidence description','Reviewer','Verified on'):
                if not (e.get(key) or '').strip(): raise ValueError(f'{pid}: missing {key} for verified status')
            if not e['Evidence URL'].startswith(('https://','http://')): raise ValueError(f'{pid}: invalid evidence URL')
            date.fromisoformat(e['Verified on'])
        if raw_status=='verified_peer_reviewed': peer='Verified'; pri='A1'
        elif raw_status=='verified_not_peer_reviewed': peer='Verified not peer-reviewed'; pri='C'
        else:
            # Journal/conference bibliographic metadata is a lead, not certification.
            venue_type=str(p.get('Venue type') or '').lower()
            ptype=str(m.get('Crossref type') or m.get('OpenAlex type') or '').lower()
            preprint=('preprint' in ptype or 'arxiv' in str(p.get('Venue') or '').lower()
                      or str(t.get('Decision suggestion') or '')=='search_published_version')
            likely=(ptype in ('journal-article','proceedings-article') and not preprint
                    and m.get('Lookup status')=='found' and not str(t.get('Bibliographic conflict') or ''))
            if preprint: peer='Preprint / unverified'; pri='C'
            elif likely: peer='Likely (not verified)'; pri='A2'
            else: peer='Unknown'; pri='B'
        counts[(v,pri)]+=1
        row=[pid,pri,peer,p.get('Title'),p.get('Year'),p.get('Venue'),p.get('Venue type'),
             p.get('DOI'),p.get('URL'),p.get('Databases'),p.get('Reason'),
             p.get('Abstract'),t.get('Decision suggestion'),m.get('Crossref type'),m.get('OpenAlex type'),
             e.get('Evidence URL'),e.get('Evidence description'),e.get('Reviewer'),e.get('Verified on'),
             'Not started',p.get('Model verdict')]
        if v=='include': ranked.append(row)
        elif v=='unsure': unsure.append(row)
        else: excluded.append(row)
        audit.append([pid,v,p.get('Model verdict'),p.get('Reason'),p.get('Mentions conflicts/updates'),
                      p.get('Title'),p.get('DOI')])
        evidence_rows.append([pid,p.get('Title'),peer,pri,e.get('Evidence URL'),
                              e.get('Evidence description'),e.get('Reviewer'),e.get('Verified on'),
                              t.get('Decision suggestion'),t.get('Reason'),m.get('Lookup status'),
                              m.get('Matched DOI'),m.get('Crossref type'),m.get('OpenAlex type')])
    order={'A1':0,'A2':1,'B':2,'C':3}
    ranked.sort(key=lambda r:(order[r[1]],-int(r[4] or 0),str(r[3]).casefold()))
    for i,row in enumerate(ranked,1):row.insert(0,i)
    cols=['ID','Priority','Peer-review status','Title','Year','Venue','Venue type','DOI','Paper URL',
          'Databases','Reason','Abstract','Triage suggestion','Crossref type','OpenAlex type',
          'Evidence URL','Evidence description','Reviewer','Verified on','Read status','Model verdict']
    wb=Workbook();wb.remove(wb.active)
    _add_sheet(wb,'01_LESELISTE',['Reading rank']+cols,ranked)
    _add_sheet(wb,'02_UNSURE',cols,unsure)
    _add_sheet(wb,'03_EXCLUDED',cols,excluded)
    _add_sheet(wb,'04_PEER_REVIEW',['ID','Title','Peer-review status','Priority','Evidence URL','Evidence description',
                                   'Reviewer','Verified on','Triage suggestion','Triage reason','Lookup status',
                                   'Matched DOI','Crossref type','OpenAlex type'],evidence_rows)
    _add_sheet(wb,'05_SCREENING_AUDIT',['ID','Verdict','Model verdict','Reason','Empirical indicator','Title','DOI'],audit)
    summary=[['Status','Provisional title/abstract reading list, NOT a completed systematic review'],
             ['Created UTC',datetime.now(timezone.utc).isoformat()],
             ['Records screened',len(papers)],['Include',len(ranked)],['Unsure',len(unsure)],['Exclude',len(excluded)],
             ['Peer-review rule','Verified requires independently documented human evidence; venue type alone is insufficient'],
             ['A2 rule','Bibliographic journal/proceedings type + metadata lookup; NOT proof of peer review'],
             ['Search caveat','Pilot limits, raw deduplication and human validation must be reported separately'],
             ['Screening SHA256',_sha(screening)]]
    for key,path in inputs.items():
        if path and key!='screening':summary.append([f'{key} SHA256',_sha(path)])
    if prisma:
        data=json.loads(Path(prisma).read_text(encoding='utf-8'))
        for k,v in data.items(): summary.append([k,json.dumps(v,ensure_ascii=False) if isinstance(v,(dict,list)) else v])
    _add_sheet(wb,'06_PRISMA_REPORT',['Field','Value'],summary)
    if keywords:
        with Path(keywords).open(encoding='utf-8-sig',newline='') as f: rows=list(csv.reader(f))
        if rows:_add_sheet(wb,'07_KEYWORDS',rows[0],rows[1:])
    if criteria:
        lines=Path(criteria).read_text(encoding='utf-8-sig').splitlines()
        _add_sheet(wb,'08_CRITERIA',['Line','Criterion'],[[i,line] for i,line in enumerate(lines,1)])
    output.parent.mkdir(parents=True,exist_ok=True)
    wb.save(output)
    return {'output':str(output),'screened':len(papers),'include':len(ranked),
            'unsure':len(unsure),'exclude':len(excluded),
            'include_priorities':dict(Counter(r[2] for r in ranked)),
            'note':'Provisional reading list; no automatic peer-review certification'}


def main(argv=None):
    parser=argparse.ArgumentParser(description='Export prioritized, auditable provisional reading list')
    parser.add_argument('--screening',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    for k in ('evidence','metadata','triage','keywords','criteria','prisma'):
        parser.add_argument('--'+k,type=Path)
    args=parser.parse_args(argv)
    try: print(json.dumps(export(**vars(args)),ensure_ascii=False,indent=2))
    except (OSError,ValueError) as e: parser.error(str(e))

if __name__=='__main__':main()

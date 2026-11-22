import csv
import json
from pathlib import Path
import openpyxl
import pytest
from syslitsearch.publication import _fingerprint, FIELDS
from syslitsearch.publication_auto import SUGGESTION_FIELDS
from syslitsearch.publication_verify import triage, POLICY_FIELDS
from syslitsearch.publication_workflow import run

def screening(path):
    w=openpyxl.Workbook();s=w.active;s.title='Screening'
    s.append(['ID','Verdict','Title','DOI','Year','Venue','Venue type'])
    s.append(['R1','include','Example','10.1234/test',2026,'Journal A','journal'])
    w.save(path)

def write(path,fields,rows):
    with path.open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore');w.writeheader();w.writerows(rows)

def test_year_from_screening_allows_policy_candidate(tmp_path):
    x=tmp_path/'s.xlsx';screening(x)
    paper={'ID':'R1','Title':'Example','DOI':'10.1234/test','Year':2026,'Venue':'Journal A'}
    fp=_fingerprint(paper)
    e={'ID':'R1','Paper fingerprint':fp,'DOI':'10.1234/test'}
    m={'ID':'R1','Paper fingerprint':fp,'Lookup status':'found','Matched DOI':'10.1234/test',
       'Crossref type':'journal-article','Crossref venue':'Journal A','Crossref ISSN':'1234-5678'}
    policy=dict(zip(POLICY_FIELDS,['p1','Journal A','1234-5678','2026','2026','journal-article',
                                  'https://example.org/policy','external review','Reviewer','2026-11-17']))
    a,b,c,o=[tmp_path/n for n in ('e.csv','m.csv','p.csv','o.csv')]
    write(a,FIELDS,[e]);write(b,SUGGESTION_FIELDS,[m]);write(c,POLICY_FIELDS,[policy])
    assert triage(a,b,o,policies=c,screening=x)['suggestions']=={'policy_candidate':1}
    row=next(csv.DictReader(o.open(encoding='utf-8-sig')))
    assert row['Publication year']=='2026'
    assert row['Policy ID']=='p1'

def test_mismatched_screening_fingerprint_rejected(tmp_path):
    x=tmp_path/'s.xlsx';screening(x)
    e={'ID':'R1','Paper fingerprint':'wrong','DOI':'10.1234/test'}
    m={'ID':'R1','Paper fingerprint':'wrong','Lookup status':'not_found'}
    a,b,o=[tmp_path/n for n in ('e.csv','m.csv','o.csv')]
    write(a,FIELDS,[e]);write(b,SUGGESTION_FIELDS,[m])
    with pytest.raises(ValueError,match='fingerprint mismatch'):
        triage(a,b,o,screening=x)
    assert not o.exists()

def test_crossref_openalex_title_conflict(tmp_path):
    from syslitsearch.publication_verify import classify
    e={'ID':'R1','Paper fingerprint':'a','DOI':'10.1234/test'}
    m={'Lookup status':'found','Matched DOI':'10.1234/test','Crossref type':'journal-article',
       'Crossref title':'Different paper','OpenAlex title':'Unrelated publication'}
    assert classify(e,m)['Decision suggestion']=='manual_bibliography'

def test_workflow_does_not_certify(tmp_path,monkeypatch):
    x=tmp_path/'s.xlsx';screening(x)
    def fake_lookup(doi,session=None,timeout=20):
        return {'Lookup status':'found','Matched DOI':doi,'Match method':'exact_doi',
                'Crossref title':'Example','Crossref type':'journal-article','Crossref venue':'Journal A'}
    monkeypatch.setattr('syslitsearch.publication_auto.lookup_doi',fake_lookup)
    out=tmp_path/'run'
    result=run(x,out,max_records=1,delay=0)
    assert result['metadata']['found']==1
    assert result['triage']['suggestions']=={'manual_peer_review':1}
    rows=list(csv.DictReader((out/'publication_evidence.csv').open(encoding='utf-8-sig')))
    assert rows[0]['Publication status']=='unverified'
    assert (out/'manifest.json').exists()
    with pytest.raises(FileExistsError):run(x,out,max_records=1,delay=0)

def test_invalid_max_records_no_output(tmp_path):
    x=tmp_path/'s.xlsx';screening(x)
    with pytest.raises(ValueError):run(x,tmp_path/'run',max_records=0)
    assert not (tmp_path/'run').exists()

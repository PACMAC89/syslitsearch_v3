from pathlib import Path
import csv
import openpyxl
import pytest
from syslitsearch.reading_list import export
from syslitsearch.publication import _papers, _fingerprint, FIELDS

def workbook(tmp_path):
    p=tmp_path/'screening.xlsx'; w=openpyxl.Workbook();s=w.active;s.title='Screening'
    s.append(['ID','Verdict','Title','DOI','Year','Venue','Venue type','Reason','Model verdict'])
    s.append(['P1','include','Relevant retrieval','10.1234/a',2026,'Example Conference','conference','Retrieval study','include'])
    s.append(['P2','unsure','Unclear','',2025,'','','Unclear','unsure'])
    s.append(['P3','exclude','Off topic','',2025,'','','Not RAG','exclude'])
    w.save(p);return p

def test_export_no_peer_review_inferred(tmp_path):
    inp=workbook(tmp_path);out=tmp_path/'list.xlsx'
    result=export(inp,out)
    assert result['include_priorities']=={'B':1}
    wb=openpyxl.load_workbook(out)
    assert wb['01_LESELISTE']['C2'].value=='B'
    assert wb['01_LESELISTE']['D2'].value=='Unknown'
    assert wb['02_UNSURE'].max_row==2
    assert wb['03_EXCLUDED'].max_row==2
    with pytest.raises(FileExistsError): export(inp,out)

def test_verified_requires_human_evidence(tmp_path):
    inp=workbook(tmp_path);out=tmp_path/'list.xlsx'; evidence=tmp_path/'e.csv'
    from syslitsearch.publication import prepare
    prepare(inp,evidence)
    with evidence.open(encoding='utf-8-sig',newline='') as f:
        rows=list(csv.DictReader(f))
    rows[0]['Publication status']='verified_peer_reviewed'
    with evidence.open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=FIELDS);w.writeheader();w.writerows(rows)
    with pytest.raises(ValueError,match='missing Evidence URL'):export(inp,out,evidence=evidence)
    rows[0].update({'Evidence URL':'https://publisher.example/policy','Evidence description':'Verified article track','Reviewer':'Human','Verified on':'2026-11-19'})
    with evidence.open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=FIELDS);w.writeheader();w.writerows(rows)
    assert export(inp,out,evidence=evidence)['include_priorities']=={'A1':1}

import csv
import json
from pathlib import Path
import pytest
from openpyxl import Workbook
from syslitsearch.review import _search_audit, audit, eligibility_template, flow_counts, paths


def fixtures(tmp_path):
    out = tmp_path / 'out'; out.mkdir()
    p = {'out':out,'report':out/'search.xlsx','screened':out/'screening.xlsx',
         'eligibility':out/'fulltext_decisions.csv','audit':out/'prisma_audit.json','flow':out/'prisma_counts.json'}
    wb=Workbook(); ws=wb.active; ws.title='Overview'
    ws.append(['Database','Status','Hits reported','Records','Passed filter','No abstract','Excluded'])
    ws.append(['Semantic Scholar','ok',1307,100,95,4,1])
    ws.append(['Scopus','ok',905,100,92,0,8])
    ws.append(['IEEE Xplore','ok',311,100,96,0,4])
    for sheet, title in [('Reading list','A'),('No abstract','B')]:
        ws=wb.create_sheet(sheet); ws.append(['#','Title','Year','DOI','Abstract'])
        ws.append([1,title,2026,'10.123/'+title,'abstract'])
    wb.save(p['report'])
    wb=Workbook(); ws=wb.active; ws.title='Screening'
    ws.append(['ID','Verdict','Model verdict','Title','DOI'])
    ws.append(['R1','include','include','A','10.123/A'])
    ws.append(['N1','unsure','unsure','B','10.123/B'])
    wb.save(p['screened'])
    return {'review_id':'test','max_records':100},p


def test_audit_reconciliation_and_source_counts(tmp_path):
    c,p=fixtures(tmp_path)
    a=audit(c,p)
    assert a['complete_id_reconciliation']
    assert a['search']['total_retrieved_before_merging']==300
    assert a['search']['databases'][0]['hits_reported']==1307
    assert a['verdicts']=={'include':1,'unsure':1}


def test_template_preserves_existing_file(tmp_path):
    c,p=fixtures(tmp_path)
    assert eligibility_template(c,p)['candidates']==2
    with pytest.raises(ValueError,match='refusing to overwrite'):
        eligibility_template(c,p)
    result=flow_counts(c,p)
    assert result['studies_included'] is None
    assert result['fulltext_status']=='in_progress'
    assert result['duplicate_records_removed'] is None


def test_completed_eligibility_counts_and_reasons(tmp_path):
    c,p=fixtures(tmp_path); eligibility_template(c,p)
    with p['eligibility'].open(encoding='utf-8-sig',newline='') as f:
        rows=list(csv.DictReader(f)); fields=list(rows[0])
    rows[0].update(retrieval_status='retrieved',fulltext_decision='include',reviewer='Reviewer 1')
    rows[1].update(retrieval_status='retrieved',fulltext_decision='exclude',exclusion_reason='Wrong population',reviewer='Reviewer 1')
    with p['eligibility'].open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)
    result=flow_counts(c,p)
    assert result['studies_included']==1
    assert result['reports_excluded_with_reasons']=={'Wrong population':1}
    assert result['fulltext_status']=='complete'


def test_missing_exclusion_reason_rejected(tmp_path):
    c,p=fixtures(tmp_path); eligibility_template(c,p)
    with p['eligibility'].open(encoding='utf-8-sig',newline='') as f:
        rows=list(csv.DictReader(f)); fields=list(rows[0])
    rows[0].update(retrieval_status='retrieved',fulltext_decision='exclude',reviewer='R')
    with p['eligibility'].open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)
    with pytest.raises(ValueError,match='without reason'):
        flow_counts(c,p)

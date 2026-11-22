import csv
from pathlib import Path
from syslitsearch.fulltext import discover, _doi

class FakeResponse:
    status_code=200
    def raise_for_status(self): pass
    def json(self): return {'best_oa_location': {'landing_page_url':'https://example.org/paper','pdf_url':'https://example.org/paper.pdf'},'locations':[]}
class FakeSession:
    def get(self,url,timeout):
        assert url.startswith('https://api.openalex.org/works/')
        return FakeResponse()

def test_doi():
    assert _doi('https://doi.org/10.1234/xyz')=='10.1234/xyz'
    assert _doi('no doi')==''

def test_discover_preserves_decisions(tmp_path):
    src=tmp_path/'fulltext_decisions.csv'
    src.write_text('ID,Title,DOI,screening_verdict,retrieval_status,fulltext_decision,exclusion_reason,reviewer,decision_date,notes\nA,Example,10.1234/abc,include,pending,pending,,,,\n',encoding='utf-8')
    original=src.read_bytes()
    a=discover(src,tmp_path/'out',session=FakeSession())
    assert a['newly_processed']==1
    assert src.read_bytes()==original
    b=discover(src,tmp_path/'out',session=FakeSession())
    assert b['newly_processed']==0
    with (tmp_path/'out'/'fulltext_discovery.csv').open(encoding='utf-8-sig') as f:
        rows=list(csv.DictReader(f))
    assert len(rows)==1 and rows[0]['pdf_url']=='https://example.org/paper.pdf'

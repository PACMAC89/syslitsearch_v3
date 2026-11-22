import csv
from syslitsearch.publication import FIELDS
from syslitsearch.publication_discovery import discover
import pytest

class Response:
    def __init__(self,rows):self.rows=rows
    def raise_for_status(self):pass
    def json(self):return {'results':self.rows}
class Session:
    def __init__(self,rows):self.rows=rows
    def get(self,url,**kwargs):return Response(self.rows)

def make_evidence(path):
    with path.open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=FIELDS);w.writeheader()
        w.writerow({'ID':'P1','Paper fingerprint':'abc','Title':'A Study of Graph RAG',
                    'DOI':'10.48550/arxiv.2601.12345'})

def test_exact_title_candidate_not_certification(tmp_path):
    e=tmp_path/'e.csv';o=tmp_path/'o.csv';make_evidence(e)
    works=[{'title':'A Study of Graph RAG','doi':'https://doi.org/10.1000/journal.1',
            'type':'article','publication_year':2026,'id':'https://openalex.org/W1',
            'primary_location':{'source':{'display_name':'Journal X'}}},
           {'title':'Different study','doi':'https://doi.org/10.1000/other','type':'article'}]
    r=discover(e,o,session=Session(works),delay=0)
    assert r['statuses']=={'candidate_needs_verification':1}
    rows=list(csv.DictReader(o.open(encoding='utf-8-sig')))
    assert rows[0]['Candidate DOI']=='10.1000/journal.1'
    assert rows[0]['Candidate status']!='verified_peer_reviewed'
    assert 'Publication status' not in rows[0]

def test_preprint_candidate_not_qualifying(tmp_path):
    e=tmp_path/'e.csv';o=tmp_path/'o.csv';make_evidence(e)
    works=[{'title':'A Study of Graph RAG','doi':'https://doi.org/10.48550/arxiv.2602.12345','type':'preprint'}]
    assert discover(e,o,session=Session(works),delay=0)['statuses']=={'non_qualifying_candidate':1}

def test_no_candidate_and_overwrite_protection(tmp_path):
    e=tmp_path/'e.csv';o=tmp_path/'o.csv';make_evidence(e)
    assert discover(e,o,session=Session([]),delay=0)['statuses']=={'no_title_candidate':1}
    with pytest.raises(FileExistsError):discover(e,o,session=Session([]),delay=0)

def test_error_does_not_halt_batch(tmp_path):
    e=tmp_path/'e.csv';o=tmp_path/'o.csv';make_evidence(e)
    class Broken:
        def get(self,*a,**k):raise ValueError('bad payload')
    assert discover(e,o,session=Broken(),delay=0)['statuses']=={'lookup_error':1}

def test_invalid_limit_no_output(tmp_path):
    e=tmp_path/'e.csv';o=tmp_path/'o.csv';make_evidence(e)
    with pytest.raises(ValueError):discover(e,o,max_records=0)
    assert not o.exists()


def test_targeted_search_skips_journal_without_api(tmp_path):
    e=tmp_path/'e.csv';o=tmp_path/'o.csv'
    with e.open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=FIELDS);w.writeheader()
        w.writerow({'ID':'J','Paper fingerprint':'fp','Title':'Journal paper','DOI':'10.1234/journal','Venue':'Journal X'})
    class NoCalls:
        def get(self,*args,**kwargs):raise AssertionError('No API call expected')
    result=discover(e,o,session=NoCalls(),delay=0,preprints_only=True)
    assert result['statuses']=={'not_applicable':1}

def test_title_variant_is_only_candidate(tmp_path):
    e=tmp_path/'e.csv';o=tmp_path/'o.csv';make_evidence(e)
    works=[{'title':'A Study on Graph RAG','doi':'https://doi.org/10.1234/published',
            'type':'article','publication_year':2026}]
    result=discover(e,o,session=Session(works),delay=0,preprints_only=True)
    assert result['statuses']=={'possible_title_variant':1}
    row=next(csv.DictReader(o.open(encoding='utf-8-sig')))
    assert row['Candidate status']!='verified_peer_reviewed'
    assert row['Title match'].startswith('approximate:')

def test_low_similarity_not_accepted(tmp_path):
    e=tmp_path/'e.csv';o=tmp_path/'o.csv';make_evidence(e)
    works=[{'title':'Completely different topic','doi':'https://doi.org/10.1234/other','type':'article'}]
    assert discover(e,o,session=Session(works),delay=0)['statuses']=={'no_title_candidate':1}

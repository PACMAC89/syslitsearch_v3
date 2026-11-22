import csv
import pytest
from syslitsearch.publication_verify import classify, triage
from syslitsearch.publication import FIELDS
from syslitsearch.publication_auto import SUGGESTION_FIELDS

def sample(doi='10.1000/example',ptype='journal-article',venue='Journal A'):
    e={'ID':'R1','Paper fingerprint':'finger','DOI':doi,'Year':'2026'}
    m={'ID':'R1','Paper fingerprint':'finger','Lookup status':'found','Matched DOI':doi,
       'Crossref type':ptype,'Crossref venue':venue,'Crossref ISSN':'1234-5678'}
    return e,m

def test_preprint_not_verified():
    e,m=sample('10.48550/arxiv.2602.07086','preprint','arXiv')
    assert classify(e,m)['Decision suggestion']=='search_published_version'

def test_abstract_not_verified():
    e,m=sample('10.1093/sleep/zsag091.0346')
    assert classify(e,m)['Decision suggestion']=='manual_contribution_type'

def test_no_policy_no_verification():
    assert classify(*sample())['Decision suggestion']=='manual_peer_review'

def test_doi_mismatch():
    e,m=sample();m['Matched DOI']='10.1000/other'
    assert classify(e,m)['Decision suggestion']=='manual_bibliography'

def test_policy_is_candidate_not_verified():
    e,m=sample()
    p={'Policy ID':'p1','Venue exact':'Journal A','ISSN exact':'1234-5678',
       'Year from':'2025','Year to':'2026','Publication type exact':'journal-article',
       'Policy URL':'https://example.org/review','Review procedure':'external review',
       'Policy verified by':'human','Policy verified on':'2026-11-17'}
    assert classify(e,m,[p])['Decision suggestion']=='policy_candidate'
    e['Year']='2027'
    assert classify(e,m,[p])['Decision suggestion']=='manual_peer_review'

def write(path,fields,rows):
    with path.open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore');w.writeheader();w.writerows(rows)

def test_triage_refuses_fingerprint_mismatch(tmp_path):
    e,m=sample();m['Paper fingerprint']='changed'
    a,b,o=[tmp_path/x for x in ('e.csv','m.csv','o.csv')]
    write(a,FIELDS,[e]);write(b,SUGGESTION_FIELDS,[m])
    with pytest.raises(ValueError,match='Fingerprint mismatch'):triage(a,b,o)
    assert not o.exists()

def test_triage_does_not_modify_inputs(tmp_path):
    e,m=sample();a,b,o=[tmp_path/x for x in ('e.csv','m.csv','o.csv')]
    write(a,FIELDS,[e]);write(b,SUGGESTION_FIELDS,[m])
    before=(a.read_bytes(),b.read_bytes())
    assert triage(a,b,o)['processed']==1
    assert (a.read_bytes(),b.read_bytes())==before
    assert triage if o.exists() else False
    with pytest.raises(FileExistsError):triage(a,b,o)


def policy(venue='Proceedings of SemEval 2026', issn='', ptype='proceedings-article'):
    return {'Policy ID':'p-conference','Venue exact':venue,'ISSN exact':issn,
            'Year from':'2026','Year to':'2026','Publication type exact':ptype,
            'Policy URL':'https://example.org/review','Review procedure':'external review',
            'Policy verified by':'reviewer','Policy verified on':'2026-11-17'}

def test_conference_without_issn_matches_only_exact_venue_and_year():
    e,m=sample(ptype='proceedings-article',venue='Proceedings of SemEval 2026')
    m['Crossref ISSN']=''
    assert classify(e,m,[policy()])['Decision suggestion']=='policy_candidate'
    m['Crossref venue']='Other Conference'
    assert classify(e,m,[policy()])['Decision suggestion']=='manual_peer_review'
    m['Crossref venue']='Proceedings of SemEval 2026'
    e['Year']='2025'
    assert classify(e,m,[policy()])['Decision suggestion']=='manual_peer_review'

def test_journal_without_issn_policy_rejected(tmp_path):
    from syslitsearch.publication_verify import load_policies, POLICY_FIELDS
    path=tmp_path/'policies.csv'
    write(path,POLICY_FIELDS,[policy(venue='Journal A',ptype='journal-article')])
    with pytest.raises(ValueError,match='Journal policy requires ISSN'):
        load_policies(path)

def test_conference_policy_without_issn_loads(tmp_path):
    from syslitsearch.publication_verify import load_policies, POLICY_FIELDS
    path=tmp_path/'policies.csv'
    write(path,POLICY_FIELDS,[policy()])
    assert len(load_policies(path))==1

def test_ambiguous_conference_policies_not_automatically_selected():
    e,m=sample(ptype='proceedings-article',venue='Proceedings of SemEval 2026')
    m['Crossref ISSN']=''
    a=policy(); b=dict(a,**{'Policy ID':'p-conference-2'})
    assert classify(e,m,[a,b])['Decision suggestion']=='manual_policy_ambiguous'

def test_mismatched_issn_does_not_match():
    e,m=sample(ptype='proceedings-article',venue='Proceedings of SemEval 2026')
    m['Crossref ISSN']=''
    assert classify(e,m,[policy(issn='2522-2686')])['Decision suggestion']=='manual_peer_review'

import csv
from pathlib import Path
from syslitsearch.publication_auto import SUGGESTION_FIELDS
from syslitsearch.publication_policy_discovery import discover

def test_policy_leads_never_certify(tmp_path):
    inp=tmp_path/'metadata.csv';out=tmp_path/'leads.csv'
    with inp.open('w',encoding='utf-8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=SUGGESTION_FIELDS);w.writeheader()
        w.writerow({'ID':'R10','Paper fingerprint':'abc','Lookup status':'found','Matched DOI':'10.3390/info17101042', 'Crossref venue':'Information','Crossref type':'journal-article','Crossref ISSN':'2078-2489'})
        w.writerow({'ID':'R6','Paper fingerprint':'def','Lookup status':'found','Matched DOI':'10.18653/v1/2026.semeval-1.254','Crossref venue':'SemEval','Crossref type':'proceedings-article'})
    result=discover(inp,out)
    rows=list(csv.DictReader(out.open(encoding='utf-8-sig')))
    assert result['certified']==0 and result['official_policy_leads']==1
    assert rows[0]['Official source URL'].startswith('https://www.mdpi.com/')
    assert rows[1]['Official source URL']==''
    assert all(r['Review status']=='requires_review' for r in rows)

def test_no_overwrite(tmp_path):
    inp=tmp_path/'a.csv';inp.write_text(','.join(SUGGESTION_FIELDS)+'\n')
    try: discover(inp,inp)
    except FileExistsError: pass
    else: assert False

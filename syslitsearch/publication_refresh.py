"""One-shot offline refresh of the existing prioritized reading list.

No new database searches, LLM calls, or automatic peer-review certification.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
from .reading_list import export
from .venue_policy_audit import build

def main(argv=None):
    p=argparse.ArgumentParser(description='Refresh reading list from existing publication evidence (offline)')
    p.add_argument('--screening',required=True,type=Path)
    p.add_argument('--publication-dir',required=True,type=Path)
    p.add_argument('--output',required=True,type=Path)
    p.add_argument('--keywords',type=Path)
    p.add_argument('--criteria',type=Path)
    p.add_argument('--prisma',type=Path)
    a=p.parse_args(argv)
    d=a.publication_dir
    evidence=d/'publication_evidence.csv'
    metadata=d/'metadata_suggestions.csv'
    triage=d/'publication_triage.csv'
    leads=d/'policy_leads.csv'
    queue=d/'venue_policy_review.csv'
    try:
        if not all(x.is_file() for x in (evidence,metadata,triage)):
            raise FileNotFoundError('publication_evidence.csv, metadata_suggestions.csv and publication_triage.csv required')
        report={}
        if leads.exists() and not queue.exists():
            report['venue_queue']=build(metadata,leads,queue)
        elif leads.exists():
            report['venue_queue']='Existing queue preserved'
        report['reading_list']=export(a.screening,a.output,evidence=evidence,metadata=metadata,
                                      triage=triage,keywords=a.keywords,criteria=a.criteria,prisma=a.prisma)
        print(json.dumps(report,ensure_ascii=False,indent=2))
    except (OSError,ValueError) as exc:p.error(str(exc))
if __name__=='__main__':main()

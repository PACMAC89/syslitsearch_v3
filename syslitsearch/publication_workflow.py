"""P0-02d: one-command, non-destructive bibliographic triage.

No automatic peer-review certification. The final reading list remains gated by
independently reviewed evidence in publication.finalize.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
from .publication import prepare, _papers, _fingerprint
from .publication_auto import enrich
from .publication_verify import triage
from .publication_discovery import discover
from .publication_policy_discovery import discover as discover_policies


def run(screening: Path, out: Path, *, policies: Path | None = None,
        max_records: int | None = None, timeout: float = 20, delay: float = .1,
        discover_versions: bool = False, policy_leads: bool = False):
    screening=Path(screening);out=Path(out)
    if max_records is not None and max_records < 1:
        raise ValueError('max_records must be >= 1')
    if out.exists():
        raise FileExistsError(f'Refusing to reuse existing output directory: {out}')
    if not screening.is_file():
        raise FileNotFoundError(screening)
    if policies and not Path(policies).is_file():
        raise FileNotFoundError(policies)
    # Validate screening before creating any output files.
    papers=_papers(screening)
    if not papers: raise ValueError('Screening workbook is empty')
    if out.resolve()==screening.resolve() or out.resolve() in screening.resolve().parents:
        raise ValueError('Output cannot contain or replace screening input')
    if policies and (out.resolve()==Path(policies).resolve() or out.resolve() in Path(policies).resolve().parents):
        raise ValueError('Output cannot contain or replace policy input')
    out.mkdir(parents=True)
    evidence=out/'publication_evidence.csv'
    metadata=out/'metadata_suggestions.csv'
    suggestions=out/'publication_triage.csv'
    prepare(screening,evidence)
    enrichment=enrich(evidence,metadata,max_records=max_records,timeout=timeout,delay=delay)
    decisions=triage(evidence,metadata,suggestions,policies=policies,screening=screening)
    policy_lead_result=discover_policies(metadata,out/'policy_leads.csv') if policy_leads else None
    discovery=discover(evidence,out/'version_candidates.csv',max_records=max_records,timeout=timeout,delay=delay,preprints_only=True) if discover_versions else None
    manifest={'schema':'syslitsearch-publication-workflow-v1',
              'screening_path':str(screening.resolve()),
              'screening_sha256':hashlib.sha256(screening.read_bytes()).hexdigest(),
              'policies_path':str(Path(policies).resolve()) if policies else None,
              'policies_sha256':hashlib.sha256(Path(policies).read_bytes()).hexdigest() if policies else None,
              'max_records':max_records,'metadata':enrichment,'triage':decisions,
              'version_discovery':discovery,'policy_leads':policy_lead_result,
              'warning':'Triage suggestions are not peer-review certifications; human evidence is mandatory.'}
    (out/'manifest.json').write_text(json.dumps(manifest,indent=2,ensure_ascii=False),encoding='utf-8')
    return manifest


def main(argv=None):
    p=argparse.ArgumentParser(description='Non-destructive metadata + publication triage from screening workbook')
    p.add_argument('--screening',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True)
    p.add_argument('--policies',type=Path)
    p.add_argument('--max-records',type=int)
    p.add_argument('--timeout',type=float,default=20)
    p.add_argument('--delay',type=float,default=.1)
    p.add_argument('--discover-versions',action='store_true',help='OpenAlex exact-title version candidates; not certification')
    p.add_argument('--policy-leads',action='store_true',help='Generate auditable source leads; no peer-review certification')
    a=p.parse_args(argv)
    try:
        print(json.dumps(run(a.screening,a.out,policies=a.policies,max_records=a.max_records,timeout=a.timeout,delay=a.delay,discover_versions=a.discover_versions,policy_leads=a.policy_leads),ensure_ascii=False))
    except (OSError,ValueError) as exc:
        p.exit(2,f'ERROR: {exc}\n')
    return 0
if __name__=='__main__':raise SystemExit(main())

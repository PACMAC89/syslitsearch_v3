"""PRISMA-oriented review runner. PRISMA is a reporting guideline, not a certification."""
from __future__ import annotations
import argparse
import csv
import hashlib
import json
import subprocess
from collections import Counter
import sys
from datetime import datetime, timezone
from pathlib import Path

from .screening import load_papers


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_config(path: Path) -> dict:
    config = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(config, dict):
        raise ValueError('Configuration must be a JSON object')
    required = ['review_id', 'keywords', 'criteria', 'sources', 'years', 'output_dir']
    for key in required:
        if not config.get(key):
            raise ValueError(f'Missing configuration field: {key}')
    if not isinstance(config['sources'], list) or not config['sources']:
        raise ValueError('sources must be a nonempty list')
    if not all(isinstance(x, str) for x in config['sources']):
        raise ValueError('sources must contain strings')
    for key in ('keywords', 'criteria'):
        if not Path(config[key]).is_file():
            raise ValueError(f'Missing input: {config[key]}')
    if config.get('max_records') is not None and (not isinstance(config['max_records'], int) or config['max_records'] < 1):
        raise ValueError('max_records must be a positive integer')
    return config


def paths(c: dict) -> dict:
    out = Path(c['output_dir'])
    return {'out': out, 'report': out / 'search.xlsx', 'screen': out / 'screening',
            'screened': out / 'screening.xlsx', 'manifest': out / 'review_manifest.json',
            'flow': out / 'prisma_counts.json', 'eligibility': out / 'fulltext_decisions.csv', 'audit': out / 'prisma_audit.json'}


def ensure_manifest(c: dict, p: dict, config_path: Path) -> dict:
    p['out'].mkdir(parents=True, exist_ok=True)
    inputs = {k: {'path': str(Path(c[k]).resolve()), 'sha256': digest(Path(c[k]))} for k in ('keywords', 'criteria')}
    inputs['config'] = {'path': str(config_path.resolve()), 'sha256': digest(config_path)}
    if p['manifest'].exists():
        m = json.loads(p['manifest'].read_text(encoding='utf-8'))
        if m['inputs'] != inputs:
            raise ValueError('Review inputs changed; use a new output_dir to preserve provenance')
        return m
    if any(p['out'].iterdir()):
        raise ValueError('Output directory is not empty and has no review manifest; choose a new output_dir')
    m = {'schema': 'syslitsearch-prisma-review-v1', 'review_id': c['review_id'],
         'created_utc': datetime.now(timezone.utc).isoformat(), 'inputs': inputs,
         'search': {'sources': c['sources'], 'years': c['years'], 'max_records': c.get('max_records'),
                    'groups': c.get('groups'), 'no_per_keyword': c.get('no_per_keyword', True)},
         'stages': {}}
    save_manifest(p, m)
    return m


def save_manifest(p: dict, m: dict):
    p['manifest'].write_text(json.dumps(m, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')


def command(c: dict, p: dict, stage: str) -> list[str]:
    if stage == 'search':
        cmd = [sys.executable, '-m', 'syslitsearch', '--keywords', c['keywords'], '--sources', ','.join(c['sources']),
               '--years', c['years'], '--output', str(p['report']), '--exact-output']
        if c.get('groups'):
            cmd += ['--groups', c['groups']]
        if c.get('no_per_keyword', True):
            cmd.append('--no-per-keyword')
        if c.get('max_records'):
            cmd += ['--max-records', str(c['max_records'])]
        return cmd
    base = [sys.executable, '-m', 'syslitsearch.screening']
    if stage == 'prepare':
        return base + ['prepare', '--report', str(p['report']), '--out', str(p['screen']),
                       '--criteria', c['criteria'], '--run', c.get('run', 'run1'),
                       '--size', str(c.get('batch_size', 100))]
    if stage == 'judge':
        return base + ['judge', '--out', str(p['screen']), '--run', c.get('run', 'run1'),
                       '--papers-per-request', str(c.get('papers_per_request', 5))]
    if stage == 'build':
        return base + ['build', '--out', str(p['screen']), '--run', c.get('run', 'run1'),
                       '--report', str(p['report']), '--output', str(p['screened'])]
    raise ValueError(stage)


def _search_audit(report: Path) -> dict:
    """Extract observed database-level numbers from the search workbook, not estimates."""
    from openpyxl import load_workbook
    wb = load_workbook(report, read_only=True, data_only=True)
    try:
        if 'Overview' not in wb.sheetnames:
            raise ValueError('Search workbook has no Overview sheet')
        rows = list(wb['Overview'].iter_rows(values_only=True))
        head = next((i for i, row in enumerate(rows) if row and row[0] == 'Database' and 'Hits reported' in row), None)
        if head is None:
            raise ValueError('Overview has no database summary table')
        columns = list(rows[head]); out = []
        for row in rows[head+1:]:
            if not row or not row[0] or row[0] == 'All databases together, duplicates merged':
                break
            d = dict(zip(columns, row))
            out.append({'database': str(d['Database']), 'status': str(d['Status']),
                        'hits_reported': d['Hits reported'], 'records_retrieved': d['Records'],
                        'passed_lexical_filter': d['Passed filter'],
                        'no_abstract': d['No abstract'], 'excluded_lexical_filter': d['Excluded']})
        if not out:
            raise ValueError('No database rows in Overview')
        sheet_counts = {}
        for name in ('Reading list', 'No abstract', 'Excluded'):
            if name in wb.sheetnames:
                sheet_counts[name] = max(0, wb[name].max_row - 1)
        return {'databases': out, 'search_sheet_counts': sheet_counts,
                'total_retrieved_before_merging': sum(x['records_retrieved'] for x in out if isinstance(x['records_retrieved'], int)),
                'limitations': ['Database hit totals are query estimates, not records exported.',
                                'Unique raw-record deduplication cannot be established from merged report alone.']}
    finally:
        wb.close()


def _screening_rows(path: Path) -> list[dict]:
    from openpyxl import load_workbook
    wb = load_workbook(path, read_only=True, data_only=True)
    try:
        if 'Screening' not in wb.sheetnames:
            raise ValueError('Missing Screening worksheet')
        it = wb['Screening'].iter_rows(values_only=True)
        header = next(it)
        return [dict(zip(header, row)) for row in it if row[0] is not None]
    finally:
        wb.close()


def audit(c: dict, p: dict) -> dict:
    if not p['report'].is_file():
        raise ValueError('Search report missing; run search first')
    search = _search_audit(p['report'])
    papers = load_papers(p['report'])
    screened = _screening_rows(p['screened']) if p['screened'].is_file() else []
    source_ids = [x['id'] for x in papers]
    screen_ids = [str(x['ID']) for x in screened]
    if len(source_ids) != len(set(source_ids)) or len(screen_ids) != len(set(screen_ids)):
        raise ValueError('Duplicate paper IDs detected in search or screening')
    missing = sorted(set(source_ids) - set(screen_ids))
    extra = sorted(set(screen_ids) - set(source_ids))
    verdicts = Counter(str(x.get('Verdict') or 'missing').lower() for x in screened)
    model_verdicts = Counter(str(x.get('Model verdict') or 'missing').lower() for x in screened)
    result = {'schema': 'syslitsearch-prisma-audit-v2', 'review_id': c['review_id'],
              'search': search, 'search_papers_eligible_for_screening': len(papers),
              'screening_workbook_rows': len(screened), 'missing_screening_ids': missing,
              'extra_screening_ids': extra, 'verdicts': dict(verdicts),
              'model_verdicts': dict(model_verdicts),
              'screening_decisions_differing_from_model': sum(str(x.get('Verdict') or '').lower() != str(x.get('Model verdict') or '').lower() for x in screened),
              'complete_id_reconciliation': bool(screened) and not missing and not extra}
    p['audit'].write_text(json.dumps(result, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    return result


def eligibility_template(c: dict, p: dict) -> dict:
    """Prepare a human-editable, ID-bound full-text log; never overwrite decisions."""
    if p['eligibility'].exists():
        raise ValueError('Full-text decisions already exist; refusing to overwrite')
    if not p['screened'].is_file():
        raise ValueError('Screening workbook missing; run build first')
    info = audit(c, p)
    if not info['complete_id_reconciliation']:
        raise ValueError('Screening IDs do not reconcile with search report; resolve before full-text template')
    rows = _screening_rows(p['screened'])
    eligible = [x for x in rows if str(x.get('Verdict') or '').lower() in ('include', 'unsure')]
    unknown = [x['ID'] for x in rows if str(x.get('Verdict') or '').lower() not in ('include','unsure','exclude')]
    if unknown:
        raise ValueError(f'Unrecognized screening decisions for {len(unknown)} records')
    with p['eligibility'].open('w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=['ID','Title','DOI','screening_verdict','retrieval_status',
                                              'fulltext_decision','exclusion_reason','reviewer','decision_date','notes'])
        writer.writeheader()
        for x in eligible:
            writer.writerow({'ID':x['ID'], 'Title':x.get('Title') or '', 'DOI':x.get('DOI') or '',
                             'screening_verdict':x['Verdict'], 'retrieval_status':'pending',
                             'fulltext_decision':'pending'})
    return {'file':str(p['eligibility']), 'candidates':len(eligible),
            'instructions':'Complete retrieval_status (retrieved/not_retrieved/pending), fulltext_decision (include/exclude/pending), reviewer and reason for exclusions. Keep unknowns pending.'}


def _eligibility_counts(p: dict, rows: list[dict]) -> dict:
    if not p['eligibility'].is_file():
        return {'reports_sought_for_retrieval': None, 'reports_not_retrieved': None,
                'reports_assessed_for_eligibility': None, 'reports_excluded_with_reasons': None,
                'studies_included': None, 'fulltext_status':'not_started'}
    with p['eligibility'].open(encoding='utf-8-sig', newline='') as f:
        decisions = list(csv.DictReader(f))
    candidates = {str(x['ID']) for x in rows if str(x.get('Verdict') or '').lower() in ('include','unsure')}
    ids = [str(x.get('ID') or '') for x in decisions]
    if len(ids) != len(set(ids)) or set(ids) != candidates:
        raise ValueError('Full-text decision IDs do not match include/unsure screening candidates')
    valid_retrieval = {'retrieved','not_retrieved','pending'}
    valid_decisions = {'include','exclude','pending'}
    for x in decisions:
        status = str(x.get('retrieval_status') or '').strip().lower()
        decision = str(x.get('fulltext_decision') or '').strip().lower()
        if status not in valid_retrieval or decision not in valid_decisions:
            raise ValueError(f'Invalid full-text status/decision for ID {x["ID"]}')
        if status != 'retrieved' and decision != 'pending':
            raise ValueError(f'Full-text decision without retrieved report: {x["ID"]}')
        if decision == 'exclude' and not str(x.get('exclusion_reason') or '').strip():
            raise ValueError(f'Full-text exclusion without reason: {x["ID"]}')
        if decision != 'pending' and not str(x.get('reviewer') or '').strip():
            raise ValueError(f'Full-text decision without reviewer: {x["ID"]}')
    pending = [x for x in decisions if x['retrieval_status'].strip().lower() == 'pending' or
               (x['retrieval_status'].strip().lower() == 'retrieved' and x['fulltext_decision'].strip().lower() == 'pending')]
    complete = not pending
    included = sum(x['fulltext_decision'].strip().lower() == 'include' for x in decisions)
    excluded = Counter(x['exclusion_reason'].strip() for x in decisions if x['fulltext_decision'].strip().lower() == 'exclude')
    return {'reports_sought_for_retrieval':len(decisions),
            'reports_not_retrieved':sum(x['retrieval_status'].strip().lower() == 'not_retrieved' for x in decisions) if complete else None,
            'reports_assessed_for_eligibility':sum(x['retrieval_status'].strip().lower() == 'retrieved' for x in decisions) if complete else None,
            'reports_excluded_with_reasons':dict(excluded) if complete else None,
            'studies_included':included if complete else None,
            'fulltext_status':'complete' if complete else 'in_progress', 'fulltext_pending':len(pending),
            'provisional_included':included}


def flow_counts(c: dict, p: dict) -> dict:
    """Conservative PRISMA accounting. Unknown values are null, never guessed."""
    info = audit(c, p)
    rows = _screening_rows(p['screened']) if p['screened'].is_file() else []
    sources = info['search']['databases']
    result = {'schema':'syslitsearch-prisma-counts-v2','review_id':c['review_id'],
              'pilot_limited':c.get('max_records') is not None,
              'records_identified_per_database':{x['database']:x['hits_reported'] for x in sources},
              'records_retrieved_per_database':{x['database']:x['records_retrieved'] for x in sources},
              'records_in_search_report':info['search_papers_eligible_for_screening'],
              'duplicate_records_removed':None,
              'records_removed_before_screening_other':None,
              'records_screened':len(rows) if rows else None,
              'title_abstract_verdict_counts':info['verdicts'] if rows else None,
              'records_excluded_by_automation':None,
              'records_excluded_by_humans':None,
              'screening_id_reconciled':info['complete_id_reconciliation'],
              'screening_missing_ids':info['missing_screening_ids'],
              'screening_extra_ids':info['extra_screening_ids'],
              'screening_decisions_differing_from_model':info['screening_decisions_differing_from_model'],
              'warning':'Not a complete PRISMA 2020 diagram: raw dedup counts and human-vs-automation classification are not yet evidenced. Database hits are estimates; records retrieved are capped in pilot.'}
    result.update(_eligibility_counts(p, rows))
    p['flow'].write_text(json.dumps(result, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    return result

def run_stage(c: dict, config_path: Path, stage: str, dry_run: bool = False):
    p = paths(c)
    if stage == 'plan':
        print(json.dumps({'config': c, 'commands': {s: command(c, p, s) for s in ('search','prepare','judge','build')}}, indent=2, ensure_ascii=False))
        return
    m = ensure_manifest(c, p, config_path)
    if stage == 'audit':
        print(json.dumps(audit(c, p), indent=2, ensure_ascii=False))
        return
    if stage == 'eligibility-template':
        print(json.dumps(eligibility_template(c, p), indent=2, ensure_ascii=False))
        return
    if stage == 'fulltext-discover':
        from .fulltext import discover
        if not p['eligibility'].is_file():
            raise ValueError('Full-text decisions missing; run eligibility-template first')
        print(json.dumps(discover(p['eligibility'], p['out'] / 'fulltext', limit=10), indent=2, ensure_ascii=False))
        return
    if stage == 'fulltext-extract':
        from .fulltext import extract_local
        print(json.dumps(extract_local(p['out'] / 'fulltext' / 'pdfs', p['out'] / 'fulltext' / 'texts', limit=10), indent=2, ensure_ascii=False))
        return
    if stage == 'reading-list':
        from .reading_list import export
        if not p['screened'].is_file():
            raise ValueError('Screening workbook missing; run build first')
        folder = p['out'] / 'publication_review'
        print(json.dumps(export(p['screened'], p['out'] / 'prioritized_reading_list.xlsx',
             evidence=folder / 'publication_evidence.csv' if (folder / 'publication_evidence.csv').exists() else None,
             metadata=folder / 'metadata_suggestions.csv' if (folder / 'metadata_suggestions.csv').exists() else None,
             triage=folder / 'publication_triage.csv' if (folder / 'publication_triage.csv').exists() else None,
             keywords=Path(c['keywords']), criteria=Path(c['criteria']),
             prisma=p['flow'] if p['flow'].exists() else None), indent=2, ensure_ascii=False))
        return
    if stage == 'flow':
        if not p['report'].exists():
            raise ValueError('Search report missing; run search first')
        print(json.dumps(flow_counts(c, p), indent=2, ensure_ascii=False))
        return
    if stage not in ('search', 'prepare', 'judge', 'build'):
        raise ValueError(stage)
    if stage == 'search' and p['report'].exists():
        raise ValueError('Search report exists; refusing to overwrite it')
    if stage in ('prepare', 'judge', 'build') and not p['report'].exists():
        raise ValueError('Search report missing; run search first')
    if stage == 'prepare' and p['screen'].exists() and any(p['screen'].iterdir()):
        raise ValueError('Screening folder already exists; refusing to overwrite')
    if stage == 'build' and p['screened'].exists():
        raise ValueError('Screening workbook exists; refusing to overwrite')
    cmd = command(c, p, stage)
    if dry_run:
        print(' '.join(cmd))
        return
    completed = subprocess.run(cmd, check=False)
    if completed.returncode:
        raise RuntimeError(f'{stage} failed with exit code {completed.returncode}')
    m['stages'][stage] = {'completed_utc': datetime.now(timezone.utc).isoformat(),
                          'command': cmd, 'artifact': str({'search':p['report'], 'prepare':p['screen'],
                                                          'judge':p['screen'], 'build':p['screened']}[stage])}
    save_manifest(p, m)
    print(f'{stage}: completed')


def main(argv=None):
    parser = argparse.ArgumentParser(description='PRISMA-oriented staged literature review; no automatic PRISMA compliance claim')
    parser.add_argument('stage', choices=['plan','search','prepare','judge','build','audit','eligibility-template','fulltext-discover','fulltext-extract','flow','reading-list'])
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args(argv)
    try:
        run_stage(load_config(args.config), args.config, args.stage, args.dry_run)
    except (ValueError, RuntimeError) as e:
        parser.error(str(e))
    return 0

if __name__ == '__main__':
    raise SystemExit(main())

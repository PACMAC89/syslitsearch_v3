#!/usr/bin/env python3
"""Read-only PRISMA 2020 reporting for a syslitsearch review.
Usage: python generate_prisma_report.py --review results/prisma/MY_REVIEW
Requires: openpyxl (python -m pip install openpyxl). No network access.
"""
import argparse, json, hashlib, csv, os, tempfile, re
from pathlib import Path
from collections import Counter
from datetime import datetime, timezone
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.utils import get_column_letter

ITEMS = [
('1','Title'),('2','Abstract'),('3','Rationale'),('4','Objectives'),('5','Eligibility criteria'),
('6','Information sources'),('7','Search strategy'),('8','Selection process'),('9','Data collection process'),
('10a','Outcome data items'),('10b','Other data items'),('11','Risk-of-bias assessment'),('12','Effect measures'),
('13a','Synthesis eligibility'),('13b','Data preparation'),('13c','Presentation methods'),('13d','Synthesis methods'),
('13e','Heterogeneity methods'),('13f','Sensitivity analyses'),('14','Reporting bias methods'),('15','Certainty methods'),
('16a','Study selection flow'),('16b','Excluded apparently eligible studies'),('17','Study characteristics'),
('18','Risk of bias results'),('19','Individual study results'),('20a','Synthesis study characteristics'),
('20b','Synthesis results'),('20c','Heterogeneity results'),('20d','Sensitivity results'),('21','Reporting bias results'),
('22','Certainty results'),('23a','Interpretation'),('23b','Evidence limitations'),('23c','Review process limitations'),
('23d','Implications'),('24a','Registration'),('24b','Protocol'),('24c','Protocol amendments'),
('25','Support'),('26','Competing interests'),('27','Data/code availability')]

def read_json(path, required=True):
    if not path.is_file():
        if required: raise FileNotFoundError(f'Required file missing: {path}')
        return {}
    return json.loads(path.read_text(encoding='utf-8-sig'))

def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''): h.update(chunk)
    return h.hexdigest()

def table(wb, name, headers, rows, widths=None):
    sh = wb.create_sheet(name)
    sh.append(list(headers))
    for r in rows:
        sh.append([json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else v for v in r])
    for cell in sh[1]:
        cell.fill = PatternFill('solid', fgColor='17365D')
        cell.font = Font(name='Aptos', size=11, bold=True, color='FFFFFF')
        cell.alignment = Alignment(vertical='center', wrap_text=True)
    sh.row_dimensions[1].height = 30
    sh.freeze_panes = 'A2'
    sh.auto_filter.ref = sh.dimensions
    for i, width in enumerate(widths or [24] * len(headers), start=1):
        sh.column_dimensions[get_column_letter(i)].width = min(width, 85)
    for row in sh.iter_rows(min_row=2):
        for cell in row:
            cell.alignment = Alignment(vertical='top', wrap_text=True)
            cell.font = Font(name='Aptos', size=10)
    sh.sheet_view.showGridLines = False
    sh.sheet_properties.pageSetUpPr.fitToPage = True
    return sh

def main():
    ap=argparse.ArgumentParser(description='PRISMA 2020 evidence-based report generator')
    ap.add_argument('--review',required=True,help='Relative path to ONE review output directory')
    ap.add_argument('--overwrite',action='store_true',help='Explicitly replace generated reports')
    args=ap.parse_args()
    base=Path(args.review).expanduser().resolve(strict=True)
    counts=read_json(base/'prisma_counts.json')
    audit=read_json(base/'prisma_audit.json')
    review_manifest=read_json(base/'review_manifest.json',False)
    input_manifest=read_json(base/'screening/input_manifest.json')
    judge=read_json(base/'screening/run1/judge.json')
    publication=read_json(base/'publication_review/manifest.json',False)
    output_xlsx=base/'prisma_report-final.xlsx'
    output_md=base/'prisma_report_final_paper.md'
    if not args.overwrite and (output_xlsx.exists() or output_md.exists()):
        raise FileExistsError('Output exists; refusing overwrite. Use --overwrite explicitly.')

    db=audit['search']['databases']
    total_retrieved=sum(int(d['records_retrieved']) for d in db)
    lexical=sum(int(d['excluded_lexical_filter']) for d in db)
    screened=int(counts['records_screened'])
    verdicts={k:int(v) for k,v in counts['title_abstract_verdict_counts'].items()}
    assert sum(verdicts.values())==screened, 'Screening counts inconsistent'
    assert total_retrieved==int(audit['search']['total_retrieved_before_merging']), 'Retrieved counts inconsistent'
    assert screened==int(audit['screening_workbook_rows']), 'Audit/screening count inconsistent'

    files=sorted((base/'screening/run1').glob('result_*.jsonl'))
    if not files: raise ValueError('No result_*.jsonl files found')
    decisions=[]; batch_rows=[]
    for f in files:
        lines=[json.loads(s) for s in f.read_text(encoding='utf-8-sig').splitlines() if s.strip()]
        batch_rows.append((f.name,len(lines),sha(f),'Present; SHA256 calculated at report time'))
        decisions.extend(lines)
    ids=[str(r['id']) for r in decisions]
    distinct=len(set(ids)); observed=Counter(str(r['verdict']).lower() for r in decisions)
    assert len(decisions)==screened and distinct==screened, 'Duplicate or missing screening decisions'
    assert observed==Counter(verdicts), 'Judge counts differ from PRISMA counts'
    assert audit['complete_id_reconciliation'] is True, 'Existing audit reports unmatched IDs'
    assert int(audit['screening_decisions_differing_from_model'])==0, 'Existing audit reports differing decisions'

    # input_manifest.files has filename => SHA256 entries, as observed in the user's review.
    input_checks=[]
    for filename,expected in input_manifest.get('files',{}).items():
        matches=list((base/'screening').rglob(filename))
        matching=[p for p in matches if p.is_file() and sha(p).lower()==str(expected).lower()]
        input_checks.append((filename,'OK' if matching else 'MISSING OR HASH MISMATCH',str(expected),
                             str(matching[0].relative_to(base)) if matching else ''))
    if not input_checks or any(x[1]!='OK' for x in input_checks):
        raise ValueError('Input manifest verification failed; no report generated')

    # Independently reconcile every stored LLM decision against the actual Excel audit.
    export_path = base/'final_literature_export.xlsx'
    screening_path = base/'screening.xlsx'
    audit_source = export_path if export_path.is_file() else screening_path
    if not audit_source.is_file():
        raise FileNotFoundError('Neither final_literature_export.xlsx nor screening.xlsx found')
    source_wb=load_workbook(audit_source,read_only=True,data_only=True)
    audit_sheet='05_SCREENING_AUDIT'
    if audit_sheet not in source_wb.sheetnames:
        source_wb.close()
        raise ValueError(f'{audit_source.name} has no {audit_sheet}; cannot independently reconcile decisions')
    ws=source_wb[audit_sheet]
    iterator=ws.values
    headings=[str(x).strip() if x is not None else '' for x in next(iterator)]
    required_cols={'ID','Model verdict'}
    if not required_cols.issubset(headings):
        raise ValueError(f'Missing Excel audit columns: {required_cols-set(headings)}')
    index={name:headings.index(name) for name in required_cols}
    excel_decisions={}
    for row in iterator:
        key=row[index['ID']]
        if key is None: continue
        key=str(key).strip()
        if key in excel_decisions: raise ValueError(f'Duplicate Excel audit ID: {key}')
        excel_decisions[key]=str(row[index['Model verdict']]).strip().lower()
    source_wb.close()
    json_decisions={str(d['id']):str(d['verdict']).strip().lower() for d in decisions}
    missing_ids=sorted(set(excel_decisions)-set(json_decisions))
    extra_ids=sorted(set(json_decisions)-set(excel_decisions))
    mismatches=sorted(k for k in set(excel_decisions)&set(json_decisions) if excel_decisions[k]!=json_decisions[k])
    if missing_ids or extra_ids or mismatches:
        raise ValueError(f'Excel/JSONL disagreement: missing={missing_ids[:5]}, extra={extra_ids[:5]}, mismatches={mismatches[:5]}')
    if len(excel_decisions)!=screened: raise ValueError('Excel audit row count mismatch')

    # Preserve the actually executed search strings; flag anomalies, never silently fix.
    query_rows=[]
    search_path=base/'search.xlsx'
    if search_path.is_file():
        swb=load_workbook(search_path,read_only=True,data_only=True)
        if 'Queries' in swb.sheetnames:
            for row in swb['Queries'].values:
                values=[str(x).strip() if x is not None else '' for x in row]
                if any(values): query_rows.append(values)
        swb.close()
    criteria_path=base/'screening/criteria.md'
    criteria_text=criteria_path.read_text(encoding='utf-8-sig')
    # Original criteria are the authoritative source; do not paraphrase them into invented rules.
    criteria_excerpt=criteria_text[:10000]
    query_anomalies=[]
    if any('infmation' in ' '.join(row).lower() for row in query_rows):
        query_anomalies.append('The archived search queries contain the token "infmation"; do not retroactively correct it.')
    if not query_rows: query_anomalies.append('No query rows could be read from search.xlsx / Queries.')

    candidate_count=verdicts.get('include',0)+verdicts.get('unsure',0)
    discovery_path=base/'fulltext/fulltext_discovery.csv'
    access_counts=Counter(); access_rows=0
    if discovery_path.is_file():
        with discovery_path.open(encoding='utf-8-sig',newline='') as f:
            for r in csv.DictReader(f):
                access_rows+=1
                access_counts[str(r.get('lookup_status','unknown')).strip() or 'unknown']+=1
    if access_rows and access_rows!=candidate_count:
        raise ValueError(f'Fulltext discovery rows {access_rows} differ from Include+Unsure {candidate_count}')

    counts_rows=[]
    def add(metric,value,meaning,source,status='VERIFIED'):
        counts_rows.append((metric,value,meaning,source,status))
    for d in db:
        add('Retrieved: '+d['database'],d['records_retrieved'],'Database-level retrieved records; may overlap across sources','prisma_audit.json')
        add('Lexical exclusions: '+d['database'],d['excluded_lexical_filter'],'Database-level entries; not unique publications','prisma_audit.json')
        add('Passed lexical filter: '+d['database'],d['passed_lexical_filter'],'Database-level entries; not unique publications','prisma_audit.json')
        add('No abstract: '+d['database'],d['no_abstract'],'Database-level count; not necessarily unique','prisma_audit.json')
    add('Total retrieved before merging',total_retrieved,'Sum of database-level retrieved records, not deduplicated','prisma_audit.json')
    add('Lexical exclusions before merging',lexical,'Sum across databases, not unique exclusions','prisma_audit.json')
    add('Search report: Reading list',audit['search']['search_sheet_counts'].get('Reading list'), 'Merged report sheet rows','prisma_audit.json')
    add('Search report: No abstract',audit['search']['search_sheet_counts'].get('No abstract'), 'Merged report sheet rows','prisma_audit.json')
    add('Search report: Excluded',audit['search']['search_sheet_counts'].get('Excluded'), 'Merged report sheet rows','prisma_audit.json')
    add('Screened',screened,'Unique records screened by LLM','prisma_counts.json; result_*.jsonl')
    add('Excel vs JSONL individual decisions matched',len(excel_decisions),'Independently compared IDs and model verdicts','05_SCREENING_AUDIT; result_*.jsonl')
    for k in ('include','unsure','exclude'):
        add('LLM '+k,verdicts.get(k,0),'Title/abstract judgement; not final study inclusion','prisma_counts.json; result_*.jsonl')
    add('Candidates for later eligibility',candidate_count,'Include + Unsure; NOT reports retrieved or assessed','prisma_counts.json','DERIVED')
    add('Unique dedup removals',None,'Cannot be established from merged report','prisma_counts.json','UNKNOWN')
    add('Other removals before screening',None,'Cannot be established as unique records','prisma_counts.json','UNKNOWN')
    add('Reports sought for retrieval',None,'Not established by URL discovery','prisma_counts.json','PENDING')
    add('Reports assessed for eligibility',None,'No full-text eligibility assessment documented','prisma_counts.json','PENDING')
    add('Studies included',None,'Not a completed systematic review','prisma_counts.json','PENDING')
    if access_rows:
        add('Link discovery rows',access_rows,'Bibliographic URL lookup only; NOT full-text retrieval','fulltext/fulltext_discovery.csv')
        for k,v in sorted(access_counts.items()): add('Link status: '+k,v,'Access lead only','fulltext/fulltext_discovery.csv')

    evidence_map=[
        ('Search configuration','review_manifest.json','Review-level configuration/metadata; inspect for exact settings'),
        ('Database search and queries','search.xlsx','Overview / Queries; full strings and search filters'),
        ('Search metrics','prisma_audit.json','Database retrieval, lexical filtering, merged sheet counts'),
        ('PRISMA metrics','prisma_counts.json','Known metrics and explicitly null fields'),
        ('Screening criteria','screening/criteria.md','Archived decision criteria, hash verified'),
        ('Screening IDs','screening/ids.json','Archived input IDs, hash verified'),
        ('Screening source','screening/source.json','Archived source information, hash verified'),
        ('Eight screening inputs','screening/batch_01.txt ... batch_08.txt','Hash-verified input batches'),
        ('Judge configuration','screening/run1/judge.json','Model, endpoint, date, request grouping; null parameters remain unspecified'),
        ('Eight screening results','screening/run1/result_01.jsonl ... result_08.jsonl','ID, verdict, reason, conflicts; count and uniqueness checked'),
        ('Screening workbook','screening.xlsx','Original screening result; existing audit reconciles IDs'),
        ('Publication triage','publication_review/manifest.json','Bibliographic metadata and suggestions; not certification'),
        ('Publication evidence','publication_review/publication_evidence.csv','Evidence placeholders/manual verification'),
        ('Publication triage suggestions','publication_review/publication_triage.csv','Nonbinding verification recommendations'),
        ('Version candidates','publication_review/version_candidates.csv','Candidates, not certified published versions'),
        ('Prioritized reading list','prioritized_reading_list.xlsx','Provisional reading list; not final included studies'),
        ('Consolidated literature export','final_literature_export.xlsx','Reading list plus access links'),
        ('Link discovery','fulltext/fulltext_discovery.csv','Landing/PDF URLs; no PDF download implied'),
        ('Fulltext decision template','fulltext_decisions.csv','Pending human eligibility decisions; not completed')]
    evidence_rows=[(title,rel,'YES' if (base/rel).is_file() else ('MULTIPLE' if ' ... ' in rel else 'NO'),note)
                   for title,rel,note in evidence_map]

    coverage={
        '5':('PARTIAL','screening/criteria.md','Criteria archived; final study-level eligibility not completed'),
        '6':('PARTIAL','search.xlsx; review_manifest.json','Databases known; confirm per-database last search date'),
        '7':('DOCUMENTED','search.xlsx / Queries','Full search strings available; spelling must be preserved'),
        '8':('PARTIAL','screening/run1/judge.json; screening/criteria.md','Automated title/abstract screening; human validation not evidenced'),
        '16a':('PARTIAL','prisma_counts.json; prisma_audit.json','Deduplication and full-text selection numbers unknown'),
        '16b':('PENDING','fulltext_decisions.csv','Full-text exclusion reasons pending'),
        '24a':('REQUIRES AUTHOR','—','Registration status not documented'),
        '24b':('REQUIRES AUTHOR','—','Protocol availability not documented'),
        '24c':('REQUIRES AUTHOR','—','Amendments not documented'),
        '25':('REQUIRES AUTHOR','—','Support/funding declaration needed'),
        '26':('REQUIRES AUTHOR','—','Competing interests declaration needed'),
        '27':('PARTIAL','review_manifest.json; screening/; source code repository','Availability/public sharing must be specified by author'),
    }
    checklist=[]
    for item,label in ITEMS:
        status,location,note=coverage.get(item,('PENDING','—','Requires author-supplied manuscript content, later review stage, or applicability assessment'))
        checklist.append((item,label,status,location,note))

    wb=Workbook()
    wb.remove(wb.active)
    table(wb,'01_PRISMA_COUNTS',['Metric','Value','Interpretation','Evidence','Status'],counts_rows,[37,15,69,45,17])
    table(wb,'02_DATABASES',['Database','Hits reported','Records retrieved','Lexical pass','No abstract','Lexical excluded'],
          [(d['database'],d['hits_reported'],d['records_retrieved'],d['passed_lexical_filter'],d['no_abstract'],d['excluded_lexical_filter']) for d in db],
          [27,19,20,19,19,22])
    table(wb,'03_SCREENING',['Measure','Count','Evidence'],[
        ('Unique judge records',distinct,'result_01..08.jsonl'),('Duplicate judge IDs',len(ids)-distinct,'result_01..08.jsonl'),
        ('Missing/extra IDs (existing audit)',len(audit['missing_screening_ids'])+len(audit['extra_screening_ids']),'prisma_audit.json'),
        ('Model vs workbook deviations (existing audit)',audit['screening_decisions_differing_from_model'],'prisma_audit.json'),
        ('Model vs workbook deviations (independent)',len(mismatches),f'{audit_source.name} / 05_SCREENING_AUDIT'),
        ('Include',observed['include'],'result_01..08.jsonl'),('Unsure',observed['unsure'],'result_01..08.jsonl'),
        ('Exclude',observed['exclude'],'result_01..08.jsonl')],[42,16,43])
    table(wb,'04_PRISMA_CHECKLIST',['Item','Topic','Coverage','Evidence / location','Open requirement'],checklist,[11,32,20,53,83])
    table(wb,'05_EVIDENCE_MAP',['Artifact / purpose','Relative path','Exists','Interpretation'],evidence_rows,[34,69,14,80])
    table(wb,'06_INPUT_HASHES',['File','Verification','Expected SHA256','Resolved path'],input_checks,[25,24,68,65])
    table(wb,'07_JUDGE_OUTPUTS',['File','Decisions','Current SHA256','Comment'],batch_rows,[25,16,68,53])
    table(wb,'08_OPEN_ITEMS',['Priority','Question','Current status','Next action'],[
        ('P0','Raw deduplication','UNKNOWN','Preserve raw per-database records and log dedup pairs/counts in future runs; do not infer from difference'),
        ('P0','Pre-screen removal reconciliation','UNKNOWN','Separate lexical filtering from dedup and other reasons on same record universe'),
        ('P0','Final eligibility and included studies','PENDING','Human fulltext eligibility decisions with reasons; no automated certification'),
        ('P1','Peer-review verification','PENDING','Manually verify publication type, venue policy, version and evidence'),
        ('P1','LLM model reproducibility','PARTIAL','Archive full prompt/software versions/effective parameters, if available'),
        ('P1','Screening validation','PARTIAL','Document whether independent human verification occurred'),
        ('P1','Registration, funding, conflicts','AUTHOR INPUT','Supply protocol, funding, conflicts and data availability declarations'),
        ('P2','Synthesis and risk-of-bias','PENDING','Define synthesis and assessment methods if relevant to final review')],[13,44,22,90])
    table(wb,'09_SEARCH_QUERIES',['Original query field 1','Original query field 2','Original query field 3','Original query field 4','Original query field 5'],
          [row[:5]+['']*max(0,5-len(row)) for row in query_rows],[29,26,84,45,32])
    table(wb,'10_CRITERIA_ARCHIVE',['Line','Original archived screening criterion / text'],
          [(i,line) for i,line in enumerate(criteria_text.splitlines(),1)],[12,105])
    table(wb,'11_PROCESS_LOGIC',['Stage','Record universe / count','Rule / evidence','Scientific interpretation'],[
        ('Search','1926 database entries','prisma_audit.json / search.databases','Before merging; entries may overlap across databases'),
        ('Lexical prefilter','688 database entries excluded','prisma_audit.json / excluded_lexical_filter','Database-level sum; not unique records'),
        ('Merged search report','697 Reading list + 24 No abstract + 673 Excluded','prisma_audit.json / search_sheet_counts','Merged-sheet counts; not a complete raw-record reconciliation'),
        ('Title/abstract LLM screening','721 unique IDs','screening/criteria.md + result_*.jsonl','Include 404; Unsure 58; Exclude 259'),
        ('Bibliographic publication triage','721 records','publication_review/manifest.json','Metadata suggestions; not peer-review certification'),
        ('Candidate pool','462 Include + Unsure','Derived from judge verdicts','Not reports sought or assessed for full text'),
        ('URL discovery',f'{access_rows} rows','fulltext/fulltext_discovery.csv','URL lookup, not fulltext download or assessment'),
        ('Human eligibility','Pending','fulltext_decisions.csv','Not part of completed automated selection'),
        ('Final included studies','Unknown','prisma_counts.json','Must not be inferred from 404 or 462'),
    ],[29,37,80,85])
    table(wb,'12_AUTHOR_CONFIRM',['PRISMA item','Question / author declaration','Status'],[
        ('6','Exact last search date per database, time window, language and filters','AUTHOR CONFIRM'),
        ('7','Check archived literal queries for spelling and unexpected term expansions','AUTHOR CONFIRM'),
        ('8','Number of independent screeners, role of LLM, human review, disagreement resolution','AUTHOR CONFIRM'),
        ('16a','Unique deduplication and other pre-screening removals from raw source logs','UNKNOWN'),
        ('16b','Fulltext eligibility decisions and exclusion reasons','PENDING'),
        ('24a-c','Registration, protocol, amendments or explicitly not registered','AUTHOR CONFIRM'),
        ('25-27','Funding, conflicts, data and code sharing','AUTHOR CONFIRM'),
    ],[18,99,20])
    # Save to temporary file first; never replace an existing output on a failed validation.
    tmp_xlsx=base/'.prisma_report-final.tmp.xlsx'
    tmp_md=base/'.prisma_report_final_paper.tmp.md'
    wb.save(tmp_xlsx)

    model=judge.get('judge',{})
    dbtable='\n'.join(f"| {d['database']} | {d['records_retrieved']} | {d['passed_lexical_filter']} | {d['no_abstract']} | {d['excluded_lexical_filter']} |" for d in db)
    artifact_table='\n'.join(f'| {title} | `{rel}` | {"Present" if (base/rel).is_file() else "Check / multi-file"} |' for title,rel,_ in evidence_map)
    checktable='\n'.join(f'| {item} | {label} | {status} | {location} |' for item,label,status,location,_ in checklist)
    pubmeta=publication.get('metadata',{})
    metadata_line=(f"Bibliographic metadata enrichment reported {pubmeta.get('found', 'not specified')} found and "
                   f"{pubmeta.get('manual_or_error','not specified')} manual/error cases." if pubmeta else
                   'Bibliographic metadata enrichment was performed; detailed totals require verification in the publication manifest.')
    generated=datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')
    paper=f'''# PRISMA 2020 reporting draft: {base.name}

**Status:** Provisional title/abstract screening report; NOT a completed systematic review.  
**Generated:** {generated}  
**Reporting framework:** Page et al. (2021), PRISMA 2020, *BMJ* 372:n71, https://doi.org/10.1136/bmj.n71.

## Methods and results (audited preliminary draft; not submission-ready)

### Information sources and search strategy
A structured bibliographic search was carried out in Semantic Scholar, Scopus and IEEE Xplore. The review was concerned with retrieval-augmented generation and chunking-related methods. The original database-specific queries and restrictions are retained in `search.xlsx` (particularly the `Queries` worksheet). Exact search dates, restrictions and any corrections to query spelling should be checked against the original run records before publication. This report does not silently correct the executed queries.

### Record processing and study selection
The database retrieval logs report {total_retrieved:,} records before merging across sources. A database-level lexical prefilter excluded {lexical:,} entries (summed across databases; not a count of unique publications). Following the project's search/report processing, {screened:,} records entered automated title/abstract screening. **The number of removed duplicates and the complete reconciliation of pre-screening exclusions cannot currently be established from the archived aggregate files.** Accordingly, the difference between retrieved and screened records must not be described as duplicate removal.

Automated title/abstract assessment used an OpenAI-compatible endpoint and model `{model.get('model','not recorded')}` (`{model.get('base_url','not recorded')}`), processing up to {judge.get('papers_per_request','unknown')} papers per request. The judge settings were archived on {judge.get('date','unknown date')}. Parameters recorded as null ({', '.join(k for k in ('temperature','max_tokens','effort') if model.get(k,'not-present') is None) or 'none'}) were not explicitly specified; their effective server defaults are unknown. The archived screening criteria, source IDs and eight input batches were hash-verified against `screening/input_manifest.json`. Each decision was recorded as an ID, a three-way verdict, a rationale and a `conflicts` flag. The `conflicts` field must not be interpreted as inter-rater disagreement without further evidence.

The {len(files)} output files contain {len(decisions):,} decision rows with {distinct:,} distinct IDs. There were no duplicate IDs, and the distribution matches the archived PRISMA counts. An independent comparison with `{audit_source.name}` (`05_SCREENING_AUDIT`) found zero missing IDs, zero additional IDs and zero differing model verdicts. The existing PRISMA audit independently reports no missing/extra IDs and no differences between model verdicts and workbook verdicts. This is an audit of stored decisions, **not** a validation of their scientific correctness or a guarantee of deterministic re-execution.

### Bibliographic enrichment and publication eligibility
A subsequent workflow collected bibliographic metadata, publication-type leads and potential published-version candidates. {metadata_line} These are leads for manual checking, not independent certification of peer review. The review's inclusion policy requires manual evidence of eligible publication status. OpenAlex/DOI/landing-page/PDF links, where present, serve as access leads; they are not evidence that full-text documents were downloaded, retrieved or assessed for eligibility.

## Results

### Database retrieval and prefiltering

| Database | Retrieved records | Passed lexical filter | No abstract (database log) | Lexically excluded |
|---|---:|---:|---:|---:|
{dbtable}
| **Total database entries** | **{total_retrieved}** | **{sum(int(d['passed_lexical_filter']) for d in db)}** | **{sum(int(d['no_abstract']) for d in db)}** | **{lexical}** |

*The totals are sums of database-level entries prior to cross-source deduplication. They must not be interpreted as counts of unique papers.*

### Title/abstract screening

| Classification | Records | Share of screened records |
|---|---:|---:|
| Include (provisional) | {verdicts['include']} | {verdicts['include']/screened:.1%} |
| Unsure | {verdicts['unsure']} | {verdicts['unsure']/screened:.1%} |
| Exclude | {verdicts['exclude']} | {verdicts['exclude']/screened:.1%} |
| **Total screened** | **{screened}** | **100%** |

The provisional candidate set comprises **{candidate_count}** records classified Include or Unsure. This number is not equivalent to reports sought for retrieval, full-text eligibility assessments or final included studies. The search report contains {audit['search']['search_sheet_counts'].get('Reading list','?')} rows in `Reading list`, {audit['search']['search_sheet_counts'].get('No abstract','?')} rows in `No abstract` and {audit['search']['search_sheet_counts'].get('Excluded','?')} rows in `Excluded`. The search-report excluded sheet must not be conflated with the LLM's {verdicts['exclude']} title/abstract exclusions.

### Reproducibility and limitations
All {len(input_checks)} referenced screening input files passed SHA-256 verification. All {len(files)} result batches were readable, with {len(decisions)} unique screening decisions and the expected verdict distribution. The archive contains the judge model identifier, endpoint and request grouping. Reproduction remains limited by unspecified effective generation parameters, potentially changing remote model versions, unverified raw deduplication counts and the absence of completed human publication/full-text eligibility decisions. A full PRISMA 2020 flow diagram must leave unknown boxes unfilled rather than infer them.

## Selection logic and audit trail

The exact archived screening criteria are provided in `screening/criteria.md` and reproduced verbatim in worksheet `10_CRITERIA_ARCHIVE` of the companion workbook. **Do not substitute generic criteria for the actual archived decision rules.** The judge returned `id`, `verdict`, `reason`, and `conflicts` for each record; these are traceable in `screening/run1/result_*.jsonl`. `include` is a provisional title/abstract judgement, `unsure` indicates unresolved eligibility at this stage, and `exclude` is a title/abstract-stage exclusion. The archived criteria, not these generic labels, determine the substantive decision boundaries. The bibliographic publication workflow is subsequent and separate: suggested journal/conference status is not peer-review verification. There was no completed human full-text eligibility assessment in this automated workflow.

The search report's 673 `Excluded` rows represent a **different stage** from the judge's 259 `exclude` decisions. Database-level 688 lexical exclusions are not counts of unique publications. These three quantities must not be merged or equated.

### Executed search queries and anomalies

The full original query rows are preserved in `search.xlsx` / `Queries` and copied into worksheet `09_SEARCH_QUERIES`. No correction has been applied. {(' '.join(query_anomalies)) if query_anomalies else 'No predefined spelling anomaly was flagged by this script; this is not a full linguistic validation.'}

### Record-level audit boundaries

The stored decision record contains a rationale, but the current verification tests **integrity and agreement**, not the scientific validity of that rationale. The archived `judge.json` records model identification and request grouping but not effective server defaults for null parameters. Original raw cross-database deduplication pairs, deduplication counts, human validation, and final eligibility remain unverified.

## Evidence and file location table

All paths below are relative to the review output directory (`--review`).

| Evidence / purpose | Relative path | Status |
|---|---|---|
{artifact_table}

## PRISMA 2020 reporting checklist (working index)

The following is an **original abbreviated index of reporting topics**, not a reproduction of the copyrighted checklist wording. Status `PARTIAL` is not a claim of compliance. `PENDING` requires a later review stage or an applicability decision.

| Item | Topic | Current coverage | Location / evidence |
|---|---|---|---|
{checktable}

## PRISMA reporting status and missing evidence

The accompanying workbook maps each of the 27 PRISMA 2020 items and relevant subitems to available evidence and open actions. `DOCUMENTED` means a supporting artifact exists; it is **not** a formal declaration that the PRISMA item is fully satisfied. `PENDING`, `PARTIAL`, and `REQUIRES AUTHOR` explicitly identify missing manuscript or research-stage information. No unobserved result, exclusion reason, reviewer decision, registration, or final study count has been fabricated.

## Required author confirmations before journal submission

1. Confirm exact database search dates, date range, search syntax, language/publication restrictions and any spelling anomalies in the executed queries.
2. Recover auditable raw-record deduplication and other pre-screen exclusions, or explicitly report their unavailability.
3. Specify whether independent human reviewers validated screening decisions and how disagreements were resolved.
4. Verify eligible peer-reviewed journal/conference publication versions with independent evidence.
5. Complete and document report retrieval, full-text eligibility decisions and exclusions with reasons; distinguish reports from studies.
6. Add protocol/registration status, funding, competing interests, availability of data and code, and a justified synthesis/risk-of-bias plan where applicable.
7. Use the PRISMA 2020 abstract checklist and a finalized flow diagram only after final study selection.

## Reference
Page MJ, McKenzie JE, Bossuyt PM, et al. The PRISMA 2020 statement: an updated guideline for reporting systematic reviews. *BMJ*. 2021;372:n71. doi:10.1136/bmj.n71.
'''
    tmp_md.write_text(paper,encoding='utf-8')
    # Commit only after both files were successfully generated.
    os.replace(tmp_xlsx,output_xlsx)
    os.replace(tmp_md,output_md)
    print('OK: '+str(output_xlsx))
    print('OK: '+str(output_md))
    print(f'Verified: {len(input_checks)} input hashes, {len(files)} batches, {distinct} unique decisions; Excel-ID/verdict mismatches=0; include={verdicts["include"]}, unsure={verdicts["unsure"]}, exclude={verdicts["exclude"]}')

if __name__=='__main__': main()

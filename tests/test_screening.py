import json
from pathlib import Path

import openpyxl
import pytest

from syslitsearch import screening

HEADER = ['#', 'Title', 'Year', 'Venue', 'Venue type', 'Databases', 'Reference', 'DOI', 'arXiv', 'URL',
          'Group A: terms found', 'Abstract']
CRITERIA = '# Criteria\n- "Hardware:" memory chips\n- "Off-topic:" anything else\n- "Survey:" surveys\n'


def make_report(path):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = 'Reading list'
    ws.append(HEADER)
    ws.append([1, 'Mem0: long-term memory', 2025, 'arXiv.org', 'preprint', 'Semantic Scholar', 'Mem0', '', '2504.19413',
               'u1', 'LLM', 'We build a memory layer.'])
    ws.append([2, 'HBM for LLM inference', 2026, 'DATE', 'conference', 'IEEE Xplore', '', '', '', 'u2', 'LLM',
               'Memory bandwidth of HBM; conflicting bank accesses.'])
    ws.append([3, 'A survey of agent memory', 2026, 'ACM CSUR', 'journal', 'Scopus', '', '', '', 'u3', 'LLM',
               'We review memory.'])
    na = wb.create_sheet('No abstract')
    na.append(HEADER)
    na.append([1, 'Memory for chatbots', 2026, '', '', 'Semantic Scholar', '', '', '', 'u4', 'chatbot', ''])
    wb.save(path)


def write_results(out, run, rows):
    lines = [json.dumps(r) for r in rows]
    (out / run / 'result_01.jsonl').write_text('\n'.join(lines[:2]), encoding='utf-8')
    (out / run / 'result_02.jsonl').write_text('\n'.join(lines[2:]), encoding='utf-8')


def test_full_workflow(tmp_path):
    report, criteria, out = tmp_path / 'report.xlsx', tmp_path / 'criteria.md', tmp_path / 'screen'
    make_report(report)
    criteria.write_text(CRITERIA, encoding='utf-8')
    batches = screening.prepare(report, out, criteria, 'run1', size=2)
    assert len(batches) == 2
    assert 'Mem0' not in (out / 'batch_01.txt').read_text(encoding='utf-8').split('Title:')[0]  # no reference label
    assert 'result_01.jsonl' in (out / 'prompts' / 'batch_01.md').read_text(encoding='utf-8')
    assert screening.check(out, 'run1') == ['01: no result yet', '02: no result yet']

    rows = [{'id': 'R1', 'verdict': 'include', 'reason': 'Memory layer.', 'conflicts': False},
            {'id': 'R2', 'verdict': 'exclude', 'reason': 'Hardware: HBM.', 'conflicts': False},
            {'id': 'R3', 'verdict': 'unsure', 'reason': 'Survey: review.', 'conflicts': False},
            {'id': 'N1', 'verdict': 'exclude', 'reason': 'no label here', 'conflicts': False}]
    write_results(out, 'run1', rows)
    report_lines = screening.check(out, 'run1')
    assert report_lines[0].startswith('01: ok') and 'reason without label' in report_lines[1]

    stats = screening.build(out, 'run1', report, tmp_path / 'screening.xlsx', 'test')
    assert stats == {'papers': 4, 'include': 1, 'unsure': 1, 'exclude': 2, 'missing': 0, 'problems': 0,
                     'references': {'include': 1}}
    ws = openpyxl.load_workbook(tmp_path / 'screening.xlsx')['Screening']
    header = [c.value for c in ws[1]]
    first = {h: c.value for h, c in zip(header, ws[2])}
    assert first['ID'] == 'R1' and first['Verdict'] == first['Model verdict'] == 'include'
    assert first['Venue type'] == 'preprint'

    rows[2]['verdict'] = 'include'
    (out / 'run2').mkdir()
    write_results(out, 'run2', rows)
    cmp = screening.compare(out, 'run1', 'A', 'run2', 'B', report, tmp_path / 'compare.xlsx')
    assert cmp['papers'] == 4 and cmp['agree'] == 3

    terms = Path(__file__).parent.parent / 'examples' / 'related_terms.csv'
    assert screening.related(tmp_path / 'screening.xlsx', tmp_path / 'related.xlsx', terms, ('Hardware',)) == 0


def test_related_needs_valid_terms(tmp_path):
    bad = tmp_path / 'terms.csv'
    bad.write_text('name,pattern,fields\nx,conflict,body\n', encoding='utf-8')
    with pytest.raises(ValueError, match='fields'):
        screening.load_terms(bad)


def test_pilot_takes_references_and_a_sample(tmp_path):
    report, criteria, out = tmp_path / 'report.xlsx', tmp_path / 'criteria.md', tmp_path / 'pilot'
    make_report(report)
    criteria.write_text(CRITERIA, encoding='utf-8')
    screening.prepare(report, out, criteria, 'run1', size=10, pilot=1)
    ids = json.loads((out / 'ids.json').read_text(encoding='utf-8'))
    assert 'R1' in ids and 'N1' in ids and len(ids) == 3


def test_criteria_labels():
    assert screening.criteria_labels(CRITERIA) == ('Hardware', 'Off-topic', 'Survey')

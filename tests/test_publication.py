import csv
from pathlib import Path
import openpyxl
import pytest
from syslitsearch.publication import prepare, finalize


def workbook(path):
    w = openpyxl.Workbook()
    s = w.active
    s.title = 'Screening'
    s.append(['ID', 'Verdict', 'Title', 'DOI', 'Year', 'Venue', 'Venue type', 'arXiv', 'URL'])
    s.append(['R1', 'include', 'Research A', '10.1/a', 2025, 'Journal A', 'journal', '', ''])
    s.append(['R2', 'exclude', 'Research B', '', 2025, 'arXiv', 'preprint', '', ''])
    w.save(path)


def update(path, id='R1', **changes):
    with path.open(encoding='utf-8-sig', newline='') as f:
        reader = csv.DictReader(f)
        fields, rows = reader.fieldnames, list(reader)
    for row in rows:
        if row['ID'] == id:
            row.update(changes)
    with path.open('w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def test_default_is_unverified(tmp_path):
    src, evidence, out = (tmp_path / name for name in ('source.xlsx', 'evidence.csv', 'final.xlsx'))
    workbook(src)
    assert prepare(src, evidence) == 2
    assert finalize(src, evidence, out) == {'total': 2, 'final': 0, 'manual_review': 1, 'not_included': 1}
    assert openpyxl.load_workbook(out)['Final Reading List'].max_row == 1


def test_verified_paper_requires_evidence(tmp_path):
    src, evidence, out = (tmp_path / name for name in ('source.xlsx', 'evidence.csv', 'final.xlsx'))
    workbook(src)
    prepare(src, evidence)
    update(evidence, **{'Publication status': 'verified_peer_reviewed'})
    with pytest.raises(ValueError, match='Evidence URL required'):
        finalize(src, evidence, out)
    update(evidence, **{'Evidence URL': 'https://publisher.example/a', 'Evidence description': 'Publisher confirms review',
                        'Reviewer': 'Reviewer A', 'Verified on': '2026-11-17'})
    assert finalize(src, evidence, out)['final'] == 1


def test_changed_paper_is_rejected(tmp_path):
    src, evidence, out = (tmp_path / name for name in ('source.xlsx', 'evidence.csv', 'final.xlsx'))
    workbook(src)
    prepare(src, evidence)
    w = openpyxl.load_workbook(src)
    w['Screening']['C2'] = 'Different paper'
    w.save(src)
    with pytest.raises(ValueError, match='Paper changed'):
        finalize(src, evidence, out)


def test_duplicate_evidence_is_rejected(tmp_path):
    src, evidence, out = (tmp_path / name for name in ('source.xlsx', 'evidence.csv', 'final.xlsx'))
    workbook(src)
    prepare(src, evidence)
    with evidence.open(encoding='utf-8-sig', newline='') as f:
        lines = f.readlines()
    with evidence.open('w', encoding='utf-8-sig', newline='') as f:
        f.writelines(lines + [lines[1]])
    with pytest.raises(ValueError, match='duplicate'):
        finalize(src, evidence, out)


def test_cannot_overwrite_evidence(tmp_path):
    src, evidence = tmp_path / 'source.xlsx', tmp_path / 'evidence.csv'
    workbook(src)
    prepare(src, evidence)
    with pytest.raises(FileExistsError):
        prepare(src, evidence)

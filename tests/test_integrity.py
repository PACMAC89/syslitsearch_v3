import json
import pytest
from syslitsearch import screening
from test_screening import make_report, CRITERIA


def setup_run(tmp_path):
    report, criteria, out = tmp_path / 'report.xlsx', tmp_path / 'criteria.md', tmp_path / 'screen'
    make_report(report)
    criteria.write_text(CRITERIA, encoding='utf-8')
    screening.prepare(report, out, criteria, 'run1', size=2)
    return report, criteria, out


def test_prepare_refuses_reuse(tmp_path):
    report, criteria, out = setup_run(tmp_path)
    with pytest.raises(ValueError, match='not empty'):
        screening.prepare(report, out, criteria, 'run1')


def test_build_refuses_other_report_even_same_ids(tmp_path):
    report, criteria, out = setup_run(tmp_path)
    changed = tmp_path / 'changed.xlsx'
    make_report(changed)
    import openpyxl
    wb = openpyxl.load_workbook(changed)
    wb['Reading list']['B2'] = 'Completely different article'
    wb.save(changed)
    with pytest.raises(ValueError, match='Search report differs'):
        screening.build(out, 'run1', changed, tmp_path / 'output.xlsx')


def test_check_refuses_changed_criteria(tmp_path):
    report, criteria, out = setup_run(tmp_path)
    (out / 'criteria.md').write_text('modified', encoding='utf-8')
    with pytest.raises(ValueError, match='criteria.md'):
        screening.check(out, 'run1')


def test_check_refuses_changed_batch(tmp_path):
    report, criteria, out = setup_run(tmp_path)
    (out / 'batch_01.txt').write_text('### R1\nDifferent paper', encoding='utf-8')
    with pytest.raises(ValueError, match='batch_01.txt'):
        screening.check(out, 'run1')


def test_check_refuses_orphan_results(tmp_path):
    report, criteria, out = setup_run(tmp_path)
    (out / 'run2').mkdir()
    (out / 'run2' / 'result_01.jsonl').write_text('{"id":"R1","verdict":"include"}', encoding='utf-8')
    with pytest.raises(ValueError, match='without input signature'):
        screening.check(out, 'run2')


def test_signature_refuses_modified_manifest(tmp_path):
    report, criteria, out = setup_run(tmp_path)
    manifest = out / 'input_manifest.json'
    data = json.loads(manifest.read_text(encoding='utf-8'))
    data['selected_ids'] = ['R9']
    manifest.write_text(json.dumps(data), encoding='utf-8')
    with pytest.raises(ValueError, match='signature differs'):
        screening.check(out, 'run1')

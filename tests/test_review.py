import json
from pathlib import Path
import pytest
from syslitsearch.review import load_config, paths, ensure_manifest, command, run_stage


def setup(tmp_path):
    (tmp_path/'keywords.csv').write_text('term,group\nRAG,A\n')
    (tmp_path/'criteria.md').write_text('Criteria')
    c = {'review_id':'test','keywords':str(tmp_path/'keywords.csv'), 'criteria':str(tmp_path/'criteria.md'),
         'sources':['semantic_scholar'],'years':'2025-2026','output_dir':str(tmp_path/'output')}
    cfg = tmp_path/'config.json'
    cfg.write_text(json.dumps(c))
    return c, cfg


def test_config_and_commands(tmp_path):
    c, cfg = setup(tmp_path)
    assert load_config(cfg) == c
    assert '--no-per-keyword' in command(c, paths(c), 'search')
    assert '--criteria' in command(c, paths(c), 'prepare')


def test_manifest_and_input_change(tmp_path):
    c, cfg = setup(tmp_path)
    p = paths(c)
    ensure_manifest(c, p, cfg)
    assert ensure_manifest(c, p, cfg)['review_id'] == 'test'
    Path(c['criteria']).write_text('changed')
    with pytest.raises(ValueError, match='inputs changed'):
        ensure_manifest(c, p, cfg)


def test_no_overwrite_and_missing_report(tmp_path):
    c, cfg = setup(tmp_path)
    with pytest.raises(ValueError, match='Search report missing'):
        run_stage(c, cfg, 'prepare')
    p = paths(c)
    p['report'].write_bytes(b'placeholder')
    with pytest.raises(ValueError, match='refusing to overwrite'):
        run_stage(c, cfg, 'search')


def test_dry_run(tmp_path, capsys):
    c, cfg = setup(tmp_path)
    run_stage(c, cfg, 'search', dry_run=True)
    assert 'syslitsearch' in capsys.readouterr().out

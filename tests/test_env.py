import os

from syslitsearch.cli import load_env


def test_env_file_is_read_without_overriding(tmp_path, monkeypatch):
    env = tmp_path / '.env'
    env.write_text('# comment\nIEEE_API_KEY=from-file\nSCOPUS_API_KEY=from-file\nDIMENSIONS_API_KEY=\n', encoding='utf-8')
    monkeypatch.delenv('IEEE_API_KEY', raising=False)
    monkeypatch.setenv('SCOPUS_API_KEY', 'from-environment')
    monkeypatch.delenv('DIMENSIONS_API_KEY', raising=False)
    assert load_env(env) == [env.resolve()]
    assert os.environ['IEEE_API_KEY'] == 'from-file'
    assert os.environ['SCOPUS_API_KEY'] == 'from-environment'
    assert not os.environ.get('DIMENSIONS_API_KEY')  # empty value counts as "no key"
    monkeypatch.delenv('IEEE_API_KEY')

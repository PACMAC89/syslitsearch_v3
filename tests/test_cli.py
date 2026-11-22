from datetime import datetime
from pathlib import Path

from syslitsearch.cli import dated

NOW = datetime(2026, 10, 12, 15, 30)


def test_output_name_gets_the_run_date():
    assert dated(Path('results/full_s2.xlsx'), NOW) == Path('results/261012_full_s2.xlsx')


def test_existing_date_prefix_is_kept():
    assert dated(Path('results/261009_full_s2.xlsx'), NOW) == Path('results/261009_full_s2.xlsx')

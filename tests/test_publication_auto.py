import csv
import pytest
from syslitsearch.publication_auto import normalize_doi, lookup_doi, enrich
from syslitsearch.publication import FIELDS


class Response:
    def __init__(self, code, data=None):
        self.status_code = code
        self.data = data
    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError('bad status')
    def json(self):
        return self.data


class Session:
    def __init__(self, crossref=None, openalex=None):
        self.crossref = crossref
        self.openalex = openalex
        self.calls = []
    def get(self, url, **kwargs):
        self.calls.append(url)
        return Response(200, self.crossref if 'crossref' in url else self.openalex)


def test_doi_normalization():
    assert normalize_doi('https://doi.org/10.1234/ABC') == '10.1234/ABC'
    assert normalize_doi('doi:10.1234/a') == '10.1234/a'


def test_exact_doi_lookup():
    s = Session({'message': {'DOI': '10.1234/a', 'title': ['Title'], 'type': 'journal-article'}},
                {'doi': 'https://doi.org/10.1234/a', 'title': 'Title', 'primary_location': {'source': {'display_name': 'Venue'}}})
    data = lookup_doi('10.1234/a', session=s)
    assert data['Lookup status'] == 'found'
    assert data['Crossref type'] == 'journal-article'
    assert len(s.calls) == 2
    assert data['Match method'] == 'exact_doi'


def test_mismatched_doi_rejected():
    s = Session({'message': {'DOI': '10.9999/b'}}, None)
    with pytest.raises(ValueError, match='different DOI'):
        lookup_doi('10.1234/a', session=s)


def test_no_doi_remains_unverified(tmp_path):
    inp, out = tmp_path / 'evidence.csv', tmp_path / 'suggestions.csv'
    with inp.open('w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerow({'ID': 'R1', 'Paper fingerprint': 'abc', 'DOI': '', 'Publication status': 'unverified'})
    s = Session()
    assert enrich(inp, out, session=s, delay=0) == {'processed': 1, 'found': 0, 'manual_or_error': 1}
    assert not s.calls
    with out.open(encoding='utf-8-sig', newline='') as f:
        r = next(csv.DictReader(f))
    assert r['Lookup status'] == 'missing_or_invalid_doi'
    assert 'Publication status' not in r
    with pytest.raises(FileExistsError):
        enrich(inp, out, session=s, delay=0)


def test_repeated_doi_cached(tmp_path):
    inp, out = tmp_path / 'evidence.csv', tmp_path / 'suggestions.csv'
    with inp.open('w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        for n in (1, 2):
            w.writerow({'ID': f'R{n}', 'Paper fingerprint': str(n), 'DOI': '10.1234/a'})
    s = Session({'message': {'DOI': '10.1234/a'}}, None)
    assert enrich(inp, out, session=s, delay=0)['found'] == 2
    assert len(s.calls) == 2

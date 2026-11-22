"""Dimensions Analytics API (DSL v2). Prepared after the API documentation, not yet tested against the live API.

Needs DIMENSIONS_API_KEY; free access for non-commercial research can be requested from
Digital Science. Searches title and abstract; plural spellings are added to the query because
the phrase search does not stem.
"""

from __future__ import annotations

import os
from typing import Iterator

from ..records import Record
from .base import Source, SourceError, Years

AUTH = 'https://app.dimensions.ai/api/auth.json'
DSL = 'https://app.dimensions.ai/api/dsl/v2'
FIELDS = 'id+doi+title+abstract+year+journal+type'


class Dimensions(Source):
    name = 'dimensions'
    label = 'Dimensions'
    key_env = ('DIMENSIONS_API_KEY',)
    plural_variants = True
    wildcard_in_phrase = False
    title_chunk = 9
    tested = False

    def __init__(self, http):
        super().__init__(http)
        self._token = None
        http.min_interval = max(http.min_interval, 2.0)  # API limit: 30 requests per minute

    def _auth(self) -> str:
        if not self._token:
            r = self.http.post(AUTH, json_body={'key': os.environ.get('DIMENSIONS_API_KEY', '')}, cache=False)
            self._token = r.get('token')
            if not self._token:
                raise SourceError('Dimensions authentication failed')
        return self._token

    def _dsl(self, query: str, years: Years, limit: int, skip: int = 0) -> dict:
        escaped = query.replace('\\', '\\\\').replace('"', '\\"')
        where = f' where year in [{years[0]}:{years[1]}]' if years else ''
        dsl = f'search publications in title_abstract_only for "{escaped}"{where} return publications[{FIELDS}] limit {limit} skip {skip}'
        return self.http.post(DSL, data=dsl, headers={'Authorization': f'JWT {self._auth()}'})

    def count(self, query: str, years: Years) -> int:
        return int((self._dsl(query, years, 1).get('_stats') or {}).get('total_count') or 0)

    @staticmethod
    def _record(p: dict) -> Record:
        return Record('Dimensions', p.get('id', ''), p.get('title') or '', abstract=p.get('abstract') or '', year=p.get('year'),
                      venue=(p.get('journal') or {}).get('title', '') if isinstance(p.get('journal'), dict) else '',
                      doi=p.get('doi') or '', url=f'https://app.dimensions.ai/details/publication/{p.get("id", "")}')

    def fetch(self, query: str, years: Years, max_records: int | None = None) -> Iterator[Record]:
        skip, n = 0, 0
        while True:
            r = self._dsl(query, years, 1000, skip)
            pubs = r.get('publications') or []
            for p in pubs:
                yield self._record(p)
                n += 1
                if max_records and n >= max_records:
                    return
            skip += len(pubs)
            total = int((r.get('_stats') or {}).get('total_count') or 0)
            if not pubs or skip >= total or skip >= 50000:
                return

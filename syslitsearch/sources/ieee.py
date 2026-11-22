"""IEEE Xplore Metadata Search API.

Needs IEEE_API_KEY (developer.ieee.org). The free key has a daily call limit; one call returns
up to 200 records. Count, download and the title filter of the reference check tested against the
live API on 2026-10-09; IEEE holds none of the 25 framework papers used in that test.

IEEE does not match plurals of a quoted phrase ("large language model" misses "large language
models"; A AND B 2023-2026: 1,047 hits without plurals, 1,616 with wildcards, same in the API and the
web search), so plural spellings are added to the query. A field prefix ("All Metadata":) changes nothing.
"""

from __future__ import annotations

import os
from typing import Iterator

from ..records import Record
from .base import Source, Years

API = 'https://ieeexploreapi.ieee.org/api/v1/search/articles'
CONTENT_TYPES = {'Journals': 'journal', 'Early Access Articles': 'journal', 'Magazines': 'journal',
                 'Conferences': 'conference', 'Books': 'book'}


class IEEEXplore(Source):
    name = 'ieee'
    label = 'IEEE Xplore'
    key_env = ('IEEE_API_KEY',)
    plural_variants = True  # quoted phrases are not matched in the plural (see module docstring)
    wildcard_in_phrase = True
    title_chunk = 10
    tested = True

    def __init__(self, http):
        super().__init__(http)
        self.key = os.environ.get('IEEE_API_KEY', '')
        http.min_interval = max(http.min_interval, 0.2)

    def title_filter(self, titles: list[str]) -> str:
        return '(' + ' OR '.join(f'"Document Title":"{t.replace(chr(34), "")}"' for t in titles) + ')'

    def _search(self, query: str, years: Years, start: int = 1, max_records: int = 200) -> dict:
        params = {'apikey': self.key, 'format': 'json', 'querytext': query, 'max_records': max_records, 'start_record': start}
        if years:
            params['start_year'], params['end_year'] = years
        return self.http.get(API, params=params)

    def count(self, query: str, years: Years) -> int:
        return int(self._search(query, years, max_records=1).get('total_records') or 0)

    @staticmethod
    def _record(a: dict) -> Record:
        year = str(a.get('publication_year') or '')
        return Record('IEEE Xplore', str(a.get('article_number', '')), a.get('title') or '', abstract=a.get('abstract') or '',
                      year=int(year) if year.isdigit() else None, venue=a.get('publication_title') or '',
                      doi=a.get('doi') or '', url=a.get('html_url') or '',
                      venue_type=CONTENT_TYPES.get(a.get('content_type') or '', 'other'))

    def fetch(self, query: str, years: Years, max_records: int | None = None) -> Iterator[Record]:
        start, n = 1, 0
        while True:
            r = self._search(query, years, start)
            articles = r.get('articles') or []
            for a in articles:
                yield self._record(a)
                n += 1
                if max_records and n >= max_records:
                    return
            total = int(r.get('total_records') or 0)
            start += len(articles)
            if not articles or start > total:
                return

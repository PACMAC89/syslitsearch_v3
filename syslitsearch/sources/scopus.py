"""Scopus Search API (Elsevier).

Needs SCOPUS_API_KEY (dev.elsevier.com) and a request from the network (or VPN) of an institution
with a Scopus subscription, or an institutional token in SCOPUS_INSTTOKEN that Elsevier issued for exactly this key (otherwise every
request fails with "Institution Token is not associated with API Key").

Tested on 2026-10-09 from the university network: count, download and reference lookup work, and
view=COMPLETE delivers abstracts. The API covers only the web interface's default "Documents"
view, not the "Preprints (Beta)" tab: it finds 5 of the 25 framework papers used in that test, the same 5 as
"Documents" in the web search. Use Semantic Scholar or Dimensions for arXiv preprints.
"""

from __future__ import annotations

import os
from typing import Iterator

from ..records import Record
from .base import Source, Years

API = 'https://api.elsevier.com/content/search/scopus'
AGGREGATION_TYPES = {'Journal': 'journal', 'Trade Journal': 'journal', 'Conference Proceeding': 'conference',
                     'Book Series': 'book series', 'Book': 'book'}


class Scopus(Source):
    name = 'scopus'
    label = 'Scopus'
    key_env = ('SCOPUS_API_KEY', 'SCOPUS_INSTTOKEN')
    plural_variants = False  # Scopus handles plurals and spelling variants itself
    wildcard_in_phrase = True
    title_chunk = 25
    tested = True

    def __init__(self, http):
        super().__init__(http)
        self.headers = {'Accept': 'application/json', 'X-ELS-APIKey': os.environ.get('SCOPUS_API_KEY', '')}
        if os.environ.get('SCOPUS_INSTTOKEN'):
            self.headers['X-ELS-Insttoken'] = os.environ['SCOPUS_INSTTOKEN']
        http.min_interval = max(http.min_interval, 0.2)

    def render(self, groups: list[list[str]]) -> str:
        return f'TITLE-ABS-KEY({super().render(groups)})'

    def title_filter(self, titles: list[str]) -> str:
        return '(' + ' OR '.join(f'TITLE("{t.replace(chr(34), "")}")' for t in titles) + ')'

    @staticmethod
    def _with_years(query: str, years: Years) -> str:
        return f'({query}) AND PUBYEAR > {years[0] - 1} AND PUBYEAR < {years[1] + 1}' if years else query

    def _search(self, query: str, years: Years, cursor: str = '*', count: int = 25, view: str = 'COMPLETE') -> dict:
        params = {'query': self._with_years(query, years), 'cursor': cursor, 'count': count, 'view': view}
        return self.http.get(API, params=params, headers=self.headers)['search-results']

    def count(self, query: str, years: Years) -> int:
        r = self._search(query, years, count=1, view='STANDARD')
        return int(r.get('opensearch:totalResults') or 0)

    @staticmethod
    def _record(e: dict) -> Record:
        link = next((l.get('@href') for l in e.get('link', []) if l.get('@ref') == 'scopus'), '')
        year = (e.get('prism:coverDate') or '')[:4]
        return Record('Scopus', e.get('eid', ''), e.get('dc:title') or '', abstract=e.get('dc:description') or '',
                      year=int(year) if year.isdigit() else None, venue=e.get('prism:publicationName') or '',
                      doi=e.get('prism:doi') or '', url=link,
                      venue_type=AGGREGATION_TYPES.get(e.get('prism:aggregationType') or '', 'other'))

    def fetch(self, query: str, years: Years, max_records: int | None = None) -> Iterator[Record]:
        cursor, n = '*', 0
        while True:
            r = self._search(query, years, cursor)
            entries = [e for e in r.get('entry', []) if 'error' not in e]
            if not entries:
                return
            for e in entries:
                yield self._record(e)
                n += 1
                if max_records and n >= max_records:
                    return
            nxt = (r.get('cursor') or {}).get('@next')
            if not nxt or nxt == cursor:
                return
            cursor = nxt

"""Semantic Scholar Academic Graph API (bulk search; title and abstract; tested)."""

from __future__ import annotations

import os
import re
from typing import Iterator

from ..records import Record
from ..references import References
from .base import Source, SourceError, Years

API = 'https://api.semanticscholar.org/graph/v1'
FIELDS = 'title,abstract,year,venue,externalIds,url'
VENUE_FIELDS = 'venue,publicationVenue,publicationTypes,journal'
PUBLICATION_TYPES = {'Conference': 'conference', 'JournalArticle': 'journal', 'Book': 'book', 'BookSection': 'book'}


class SemanticScholar(Source):
    """Bulk search: Boolean syntax with | (OR), + (AND), - (NOT), "phrases" and word* prefixes.

    The words OR/AND are not operators here. Semantic Scholar stems words itself, so no plural
    variants are added; "*" inside a phrase is not supported and is dropped.
    """

    name = 'semantic_scholar'
    label = 'Semantic Scholar'
    key_env = ()  # optional: S2_API_KEY raises the rate limit
    plural_variants = False
    wildcard_in_phrase = False
    tested = True

    def __init__(self, http):
        super().__init__(http)
        self.key = os.environ.get('S2_API_KEY')
        self.headers = {'x-api-key': self.key} if self.key else None
        http.min_interval = max(http.min_interval, 1.0 if self.key else 1.2)

    def or_(self, parts: list[str]) -> str:
        return '(' + ' | '.join(parts) + ')'

    def and_(self, parts: list[str]) -> str:
        return ' + '.join(parts)

    def _bulk(self, query: str, years: Years, token: str | None = None, fields: str = FIELDS) -> dict:
        params = {'query': query, 'fields': fields}
        if years:
            params['year'] = f'{years[0]}-{years[1]}'
        if token:
            params['token'] = token
        return self.http.get(f'{API}/paper/search/bulk', params=params, headers=self.headers)

    def count(self, query: str, years: Years) -> int:
        return int(self._bulk(query, years, fields='externalIds').get('total') or 0)

    @staticmethod
    def _record(p: dict) -> Record:
        ext = p.get('externalIds') or {}
        return Record('Semantic Scholar', p.get('paperId', ''), p.get('title') or '', abstract=p.get('abstract') or '',
                      year=p.get('year'), venue=p.get('venue') or '', doi=ext.get('DOI') or '', arxiv_id=ext.get('ArXiv') or '',
                      url=p.get('url') or '')

    def fetch(self, query: str, years: Years, max_records: int | None = None) -> Iterator[Record]:
        token, n = None, 0
        while True:
            r = self._bulk(query, years, token)
            for p in r.get('data') or []:
                yield self._record(p)
                n += 1
                if max_records and n >= max_records:
                    return
            token = r.get('token')
            if not token:
                return

    @staticmethod
    def venue_type(p: dict) -> str:
        """Venue type from publicationVenue.type, else from publicationTypes ('' if neither says)."""
        t = ((p.get('publicationVenue') or {}).get('type') or '').lower()
        if t in ('journal', 'conference'):
            return t
        types = p.get('publicationTypes') or []
        return next((PUBLICATION_TYPES[k] for k in PUBLICATION_TYPES if k in types), '')

    def enrich(self, records: list[Record]) -> None:
        """Venue type through the batch endpoint (the bulk search cannot return it); one call per 500 papers.

        A paper without venue gets the journal name if Semantic Scholar has one.
        """
        ids = [r.source_id for r in records if r.source_id]
        info: dict[str, dict] = {}
        for i in range(0, len(ids), 500):
            chunk = ids[i:i + 500]
            papers = self.http.post(f'{API}/paper/batch', params={'fields': VENUE_FIELDS}, json_body={'ids': chunk},
                                    headers=self.headers)
            info.update({pid: p for pid, p in zip(chunk, papers) if p})
        for r in records:
            p = info.get(r.source_id)
            if p:
                r.set_venue(r.venue or (p.get('journal') or {}).get('name') or '', self.venue_type(p))

    def lookup_references(self, refs: References) -> dict[str, Record | None]:
        """By DOI/arXiv id through the batch endpoint, otherwise by title match."""
        found: dict[str, Record | None] = {r.label: None for r in refs}
        with_id = [(r, f'DOI:{r.doi}' if r.doi else f'ARXIV:{r.arxiv_id}') for r in refs if r.doi or r.arxiv_id]
        for i in range(0, len(with_id), 400):
            chunk = with_id[i:i + 400]
            papers = self.http.post(f'{API}/paper/batch', params={'fields': FIELDS}, json_body={'ids': [x[1] for x in chunk]},
                                    headers=self.headers)
            for (ref, _), p in zip(chunk, papers):
                if p:
                    found[ref.label] = self._record(p)
        for ref in refs:
            if found[ref.label] is None and ref.title:
                try:
                    r = self.http.get(f'{API}/paper/search/match', params={'query': ref.title, 'fields': FIELDS}, headers=self.headers)
                except Exception:  # 404 = no match
                    continue
                data = r.get('data') or []
                if data:
                    rec = self._record(data[0])
                    if refs.match(rec) is ref:
                        found[ref.label] = rec
        return found

    def references_found(self, query: str, indexed: dict[str, Record | None], refs: References) -> set[str]:
        """Query AND (titles of the indexed references as phrases); matched by paper id."""
        by_id = {rec.source_id: label for label, rec in indexed.items() if rec is not None}
        if not by_id:
            return set()
        titles = self.or_([f'"{re.sub(r"[:,()?]", " ", indexed[label].title).strip()}"' for label in by_id.values()])
        try:
            records = list(self.fetch(f'({query}) + {titles}', None, 5000))
        except SourceError:
            return set()
        return {by_id[r.source_id] for r in records if r.source_id in by_id}

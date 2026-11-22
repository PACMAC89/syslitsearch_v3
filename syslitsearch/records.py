"""Bibliographic records from the databases, identifier normalisation and deduplication."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .matching import MatchResult, normalize

_ARXIV_DOI = re.compile(r'^10\.48550/arxiv\.(.+)$')
_ARXIV_ID = re.compile(r'(\d{4}\.\d{4,5}|[a-z\-]+(?:\.[a-z]{2})?/\d{7})(?:v\d+)?$')
_PREPRINT = re.compile(r'arxiv|biorxiv|medrxiv|chemrxiv|psyarxiv|techrxiv|ssrn|research ?square|preprints\.org', re.I)
VENUE_TYPES = ('journal', 'conference', 'book series', 'book', 'preprint', 'other')


def norm_doi(doi: str | None) -> str:
    doi = (doi or '').strip().lower()
    doi = re.sub(r'^(https?://(dx\.)?doi\.org/|doi:)', '', doi)
    return doi


def norm_arxiv(arxiv_id: str | None) -> str:
    """arXiv identifier without version, prefix or URL ("2501.13956")."""
    a = (arxiv_id or '').strip().lower()
    a = re.sub(r'^(https?://arxiv\.org/(abs|pdf)/|arxiv:)', '', a).removesuffix('.pdf')
    m = _ARXIV_ID.search(a)
    return m.group(1) if m else a


def norm_title(title: str | None) -> str:
    return normalize(title or '')


@dataclass
class Record:
    source: str
    source_id: str
    title: str
    abstract: str = ''
    year: int | None = None
    venue: str = ''
    doi: str = ''
    arxiv_id: str = ''
    url: str = ''
    check: MatchResult | None = None
    reference: str = ''  # label of the reference paper this record is, if any
    venue_type: str = ''  # one of VENUE_TYPES, or '' if the database does not say

    def __post_init__(self) -> None:
        self.set_venue(self.venue, self.venue_type)
        self.doi = norm_doi(self.doi)
        self.arxiv_id = norm_arxiv(self.arxiv_id)
        m = _ARXIV_DOI.match(self.doi)
        if m and not self.arxiv_id:
            self.arxiv_id = norm_arxiv(m.group(1))

    def set_venue(self, venue: str, venue_type: str = '') -> None:
        """Venue and its type; preprint servers are recognised by name, whatever the database says."""
        self.venue = venue or ''
        self.venue_type = 'preprint' if _PREPRINT.search(self.venue) else (venue_type if self.venue else '')

    def keys(self) -> list[tuple[str, str]]:
        """Identifiers used to recognise the same paper across databases."""
        keys = []
        if self.doi:
            keys.append(('doi', self.doi))
        if self.arxiv_id:
            keys.append(('arxiv', self.arxiv_id))
        t = norm_title(self.title)
        if len(t) > 20:
            keys.append(('title', t))
        return keys


@dataclass
class MergedRecord:
    """One paper found in one or more databases."""

    records: list[Record] = field(default_factory=list)

    @property
    def sources(self) -> list[str]:
        return sorted({r.source for r in self.records})

    def best(self, attr: str):
        values = [getattr(r, attr) for r in self.records if getattr(r, attr)]
        if not values:
            return '' if attr != 'year' else None
        return max(values, key=lambda v: len(str(v))) if attr in ('abstract', 'title') else values[0]

    def venue(self) -> tuple[str, str]:
        """(venue, venue type): the first published venue in database order, else the first one named at all.

        A paper that Semantic Scholar knows only as an arXiv preprint but Scopus or IEEE hold as published
        gets the published venue.
        """
        named = [(r.venue, r.venue_type) for r in self.records if r.venue]
        if not named:
            return '', ''
        return next((v for v in named if v[1] != 'preprint'), named[0])

    @property
    def passed(self) -> bool:
        return any(r.check and r.check.passed for r in self.records)

    @property
    def status(self) -> str:
        """'passed' (reading list), 'no abstract' (cannot be checked, title alone does not pass) or 'excluded'."""
        if self.passed:
            return 'passed'
        if not any(r.abstract for r in self.records):
            return 'no abstract'
        return 'excluded'

    @property
    def reference(self) -> str:
        return next((r.reference for r in self.records if r.reference), '')

    def matched(self, group: str) -> list[str]:
        out = []
        for r in self.records:
            for t in (r.check.matched.get(group, []) if r.check else []):
                if t not in out:
                    out.append(t)
        return out

    def missing(self) -> list[str]:
        """Groups missing in every database's version of the record."""
        sets = [set(r.check.missing) for r in self.records if r.check]
        return sorted(set.intersection(*sets)) if sets else []


def merge(records: list[Record]) -> list[MergedRecord]:
    """Group records that share a DOI, an arXiv id or a normalised title."""
    parent = list(range(len(records)))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    first: dict[tuple[str, str], int] = {}
    for i, rec in enumerate(records):
        for key in rec.keys():
            if key in first:
                parent[find(i)] = find(first[key])
            else:
                first[key] = i
    groups: dict[int, MergedRecord] = {}
    for i, rec in enumerate(records):
        groups.setdefault(find(i), MergedRecord()).records.append(rec)
    return list(groups.values())

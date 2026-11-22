"""Common interface of the database connectors and the query rendering they share."""

from __future__ import annotations

import re
from typing import Iterator

from ..matching import plural, singular, sz_variants
from ..records import Record
from ..references import References
from ..web import Http

Years = tuple[int, int] | None


class SourceError(RuntimeError):
    pass


class Source:
    """One literature database.

    Subclasses set the class attributes and implement count(), fetch() and the syntax hooks.
    """

    name = ''  # command-line name
    label = ''  # display name
    key_env: tuple[str, ...] = ()  # environment variables, the first one is required
    plural_variants = False  # add plural/singular spellings to the database query (database does not stem)
    wildcard_in_phrase = True  # database accepts "word*" inside a quoted phrase
    title_chunk = 25  # how many reference titles fit into one title filter
    tested = False  # connector tested against the live API

    def __init__(self, http: Http):
        self.http = http

    # --- availability -------------------------------------------------------------------------

    def missing_key(self) -> str | None:
        """Name of the missing required environment variable, or None."""
        import os
        if self.key_env and not os.environ.get(self.key_env[0]):
            return self.key_env[0]
        return None

    # --- query syntax -------------------------------------------------------------------------

    def term_variants(self, term: str) -> list[str]:
        """Spellings to OR in the database query: s/z always, plural/singular if the database does not stem."""
        words = term.split()
        variants = [term]
        for i, w in enumerate(words):
            spellings = sz_variants(w.lower())
            if w.endswith('*') or len(spellings) < 2:
                continue
            for v in sorted(spellings):
                variants.append(' '.join(words[:i] + [v] + words[i + 1:]))
        if self.plural_variants and words and not words[-1].endswith('*'):
            last = words[-1].lower()
            for v in (singular(last), plural(singular(last))):
                variants.append(' '.join(words[:-1] + [v]))
        if not self.wildcard_in_phrase:
            variants = [v.replace('*', '') if ' ' in v else v for v in variants]
        unique, seen = [], set()
        for v in variants:
            if v.lower() not in seen:
                seen.add(v.lower())
                unique.append(v)
        return unique

    def quote(self, term: str) -> str:
        """One term in database syntax."""
        return f'"{term}"' if re.search(r'[\s\-]', term) or not term.endswith('*') else term

    def or_(self, parts: list[str]) -> str:
        return '(' + ' OR '.join(parts) + ')'

    def and_(self, parts: list[str]) -> str:
        return ' AND '.join(parts)

    def render(self, groups: list[list[str]]) -> str:
        """Groups of terms -> query (terms ORed within a group, groups ANDed)."""
        return self.and_([self.or_([self.quote(v) for t in g for v in self.term_variants(t)]) for g in groups])

    def title_filter(self, titles: list[str]) -> str:
        """Restriction to the given titles (used only to check which reference papers a query finds)."""
        return self.or_([self.quote(re.sub(r'[:,()?"]', ' ', t).strip()) for t in titles])

    # --- data -----------------------------------------------------------------------------------

    def count(self, query: str, years: Years) -> int:
        raise NotImplementedError

    def fetch(self, query: str, years: Years, max_records: int | None = None) -> Iterator[Record]:
        raise NotImplementedError

    def enrich(self, records: list[Record]) -> None:
        """Add metadata that the search response lacks (default: nothing to add)."""

    def lookup_references(self, refs: References) -> dict[str, Record | None]:
        """Which reference papers the database holds (label -> its record or None)."""
        found: dict[str, Record | None] = {r.label: None for r in refs}
        titled = [r for r in refs if r.title]
        for i in range(0, len(titled), self.title_chunk):
            chunk = titled[i:i + self.title_chunk]
            for rec in self.fetch(self.title_filter([r.title for r in chunk]), None, 2000):
                ref = refs.match(rec)
                if ref and found.get(ref.label) is None:
                    found[ref.label] = rec
        return found

    def references_found(self, query: str, indexed: dict[str, Record | None], refs: References) -> set[str]:
        """Labels of the indexed reference papers that the query finds (no year filter)."""
        titles = [rec.title for rec in indexed.values() if rec is not None]
        labels = set()
        for i in range(0, len(titles), self.title_chunk):
            q = self.and_([query if query.startswith('(') else f'({query})', self.title_filter(titles[i:i + self.title_chunk])])
            for rec in self.fetch(q, None, 2000):
                ref = refs.match(rec)
                if ref:
                    labels.add(ref.label)
        return labels

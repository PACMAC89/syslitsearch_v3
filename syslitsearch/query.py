"""Keyword file -> grouped search string (terms in a group are ORed, groups are ANDed)."""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from pathlib import Path

TERM_COLUMNS = {'term', 'keyword', 'keywords', 'search term'}
GROUP_COLUMNS = {'group', 'block', 'grouping'}
ID_COLUMNS = {'id'}
DEFAULT_GROUP = 'default'


@dataclass(frozen=True)
class Term:
    id: str
    text: str
    group: str


@dataclass
class Query:
    """Ordered groups of terms."""

    groups: dict[str, list[Term]]

    @property
    def names(self) -> list[str]:
        return list(self.groups)

    @property
    def terms(self) -> list[Term]:
        return [t for terms in self.groups.values() for t in terms]

    def select(self, names: list[str] | None) -> 'Query':
        """Only the named groups (all if names is empty), in the order given."""
        if not names:
            return Query(dict(self.groups))
        unknown = [n for n in names if n not in self.groups]
        if unknown:
            raise ValueError(f'unknown group(s) {", ".join(unknown)}; groups in the file: {", ".join(self.groups)}')
        return Query({n: self.groups[n] for n in names})

    def texts(self) -> dict[str, list[str]]:
        return {g: [t.text for t in terms] for g, terms in self.groups.items()}

    def as_lists(self) -> list[list[str]]:
        return [[t.text for t in terms] for terms in self.groups.values()]


def read_table(path: Path) -> list[list[str]]:
    """Rows of a CSV file (comma, semicolon or tab; UTF-8 with or without BOM, else Windows-1252)."""
    try:
        text = path.read_text(encoding='utf-8-sig')
    except UnicodeDecodeError:
        text = path.read_text(encoding='cp1252')
    try:
        delimiter = csv.Sniffer().sniff(text[:4096], delimiters=',;\t').delimiter
    except csv.Error:
        delimiter = ','
    return [[c.strip() for c in row] for row in csv.reader(text.splitlines(), delimiter=delimiter) if any(c.strip() for c in row)]


def load_keywords(path: Path) -> Query:
    """Read the keyword file.

    Columns (header names in any case): term (required), group (optional), id (optional).
    Without a header row the first column is the term and the second, if any, the group.
    Terms without a group share the group "default".
    """
    rows = read_table(path)
    if not rows:
        raise ValueError(f'{path}: no keywords')
    header = [c.lower() for c in rows[0]]
    if any(h in TERM_COLUMNS for h in header):
        i_term = next(i for i, h in enumerate(header) if h in TERM_COLUMNS)
        i_group = next((i for i, h in enumerate(header) if h in GROUP_COLUMNS), None)
        i_id = next((i for i, h in enumerate(header) if h in ID_COLUMNS), None)
        body = rows[1:]
    else:
        i_term, i_group, i_id, body = 0, (1 if len(rows[0]) > 1 else None), None, rows
    groups: dict[str, list[Term]] = {}
    seen_ids = set()
    for row in body:
        text = row[i_term] if i_term < len(row) else ''
        if not text or text.startswith('#'):
            continue
        group = (row[i_group] if i_group is not None and i_group < len(row) else '') or DEFAULT_GROUP
        terms = groups.setdefault(group, [])
        prefix = re.sub(r'\W+', '', group)[:12]
        tid = (row[i_id] if i_id is not None and i_id < len(row) else '') or f'{prefix}{len(terms) + 1:02d}'
        if tid in seen_ids:
            raise ValueError(f'{path}: duplicate id {tid!r}')
        seen_ids.add(tid)
        terms.append(Term(tid, text, group))
    if not groups:
        raise ValueError(f'{path}: no keywords')
    return Query(groups)

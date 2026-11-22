"""Reference papers that a good search string must find."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .query import read_table
from .records import Record, norm_arxiv, norm_doi, norm_title

LABEL_COLUMNS = {'label', 'name', 'short'}
TITLE_COLUMNS = {'title'}
DOI_COLUMNS = {'doi'}
ARXIV_COLUMNS = {'arxiv', 'arxiv_id', 'arxiv id'}


@dataclass
class Reference:
    label: str
    title: str = ''
    doi: str = ''
    arxiv_id: str = ''
    extra: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.doi = norm_doi(self.doi)
        self.arxiv_id = norm_arxiv(self.arxiv_id)

    def keys(self) -> list[tuple[str, str]]:
        return Record('reference', self.label, self.title, doi=self.doi, arxiv_id=self.arxiv_id).keys()


class References:
    def __init__(self, refs: list[Reference]):
        self.refs = refs
        self._by_key = {}
        for ref in refs:
            for key in ref.keys():
                self._by_key.setdefault(key, ref)

    def __iter__(self):
        return iter(self.refs)

    def __len__(self) -> int:
        return len(self.refs)

    @property
    def labels(self) -> list[str]:
        return [r.label for r in self.refs]

    def match(self, record: Record) -> Reference | None:
        for key in record.keys():
            if key in self._by_key:
                return self._by_key[key]
        return None


def load_references(path: Path | None) -> References:
    """Read the reference file: label, title, doi, arxiv_id (at least one of title/doi/arxiv_id per row).

    Further columns are kept and shown in the report.
    """
    if path is None:
        return References([])
    rows = read_table(path)
    if not rows:
        return References([])
    header = [c.lower() for c in rows[0]]

    def col(names):
        return next((i for i, h in enumerate(header) if h in names), None)

    i_label, i_title, i_doi, i_arxiv = col(LABEL_COLUMNS), col(TITLE_COLUMNS), col(DOI_COLUMNS), col(ARXIV_COLUMNS)
    if i_title is None and i_doi is None and i_arxiv is None:
        raise ValueError(f'{path}: needs a title, doi or arxiv_id column')
    used = {i for i in (i_label, i_title, i_doi, i_arxiv) if i is not None}
    refs = []
    for n, row in enumerate(rows[1:], 1):
        get = lambda i: row[i] if i is not None and i < len(row) else ''  # noqa: E731
        if not (get(i_title) or get(i_doi) or get(i_arxiv)):
            continue
        label = get(i_label) or f'R{n:02d}'
        extra = {rows[0][i]: row[i] for i in range(len(row)) if i not in used and i < len(rows[0]) and row[i]}
        refs.append(Reference(label, get(i_title), get(i_doi), get(i_arxiv), extra))
    labels = [r.label for r in refs]
    if len(set(labels)) != len(labels):
        raise ValueError(f'{path}: labels must be unique')
    return References(refs)


def title_key(title: str) -> str:
    return norm_title(title)

"""One search run: query every database, filter the hits lexically, check the reference papers."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from .matching import check, contains, normalize
from .query import Query, Term
from .records import MergedRecord, Record, merge
from .references import References
from .sources import Source
from .sources.base import Years


@dataclass
class TermResult:
    alone_query: str = ''
    with_query: str = ''
    alone: int | None = None
    with_other: int | None = None
    references: set[str] = field(default_factory=set)  # reference labels the database finds with the term alone


@dataclass
class SourceResult:
    source: Source
    status: str = 'ok'
    main_query: str = ''
    total: int | None = None
    records: list[Record] = field(default_factory=list)
    indexed: dict[str, Record | None] = field(default_factory=dict)
    terms: dict[str, TermResult] = field(default_factory=dict)

    @property
    def found_references(self) -> set[str]:
        return {r.reference for r in self.records if r.reference}

    @property
    def passed(self) -> list[Record]:
        return [r for r in self.records if r.check and r.check.passed]

    @property
    def no_abstract(self) -> list[Record]:
        """Records that fail on the title alone and have no abstract to check."""
        return [r for r in self.records if not (r.check and r.check.passed) and not r.abstract]


@dataclass
class RunResult:
    query: Query  # groups of the main search string
    all_terms: list[Term]  # every term of the keyword file (for the keyword matrices)
    references: References
    years: Years
    started: str
    sources: list[SourceResult]
    merged: list[MergedRecord]
    lexical: dict[str, set[str]]  # term id -> reference labels whose title/abstract contains the term
    reference_texts: dict[str, Record]  # label -> record whose title/abstract was used for the lexical matrix
    settings: dict[str, str]


def _log(msg: str) -> None:
    print(msg, flush=True)


def _other_groups(query: Query, term: Term) -> list[list[str]]:
    """The main search string's groups without the term's own group."""
    return [[t.text for t in terms] for g, terms in query.groups.items() if g != term.group]


def run(full: Query, query: Query, references: References, sources: list[Source], years: Years,
        per_keyword: bool = True, max_records: int | None = None, settings: dict | None = None) -> RunResult:
    started = datetime.now().isoformat(timespec='seconds')
    groups = query.texts()
    results = []
    for source in sources:
        res = SourceResult(source)
        results.append(res)
        missing = source.missing_key()
        if missing:
            res.status = f'skipped: environment variable {missing} not set'
            _log(f'{source.label}: {res.status}')
            continue
        try:
            res.main_query = source.render(query.as_lists())
            res.total = source.count(res.main_query, years)
            _log(f'{source.label}: {res.total} hits, fetching records ...')
            res.records = list(source.fetch(res.main_query, years, max_records))
            source.enrich(res.records)
            for rec in res.records:
                rec.check = check(rec.title, rec.abstract, groups)
                ref = references.match(rec)
                rec.reference = ref.label if ref else ''
            _log(f'{source.label}: {len(res.records)} records fetched, {len(res.passed)} pass the lexical filter, '
                 f'{len(res.no_abstract)} without abstract')
            if len(references):
                res.indexed = source.lookup_references(references)
                _log(f'{source.label}: {sum(r is not None for r in res.indexed.values())} of {len(references)} reference papers indexed')
            if per_keyword:
                for i, term in enumerate(full.terms, 1):
                    tr = TermResult()
                    tr.alone_query = source.render([[term.text]])
                    others = _other_groups(query, term)
                    tr.with_query = source.render([[term.text]] + others) if others else ''
                    tr.alone = source.count(tr.alone_query, years)
                    tr.with_other = source.count(tr.with_query, years) if others else None
                    if any(r is not None for r in res.indexed.values()):
                        tr.references = source.references_found(tr.alone_query, res.indexed, references)
                    res.terms[term.id] = tr
                    if i % 10 == 0:
                        _log(f'{source.label}: keyword {i}/{len(full.terms)}')
        except Exception as error:  # keep the other databases running
            res.status = f'error: {error}'
            _log(f'{source.label}: {res.status}')

    # lexical keyword matrix on the reference papers' own title and abstract
    texts: dict[str, Record] = {}
    for res in results:
        for label, rec in res.indexed.items():
            if rec is not None and rec.abstract and (label not in texts or len(rec.abstract) > len(texts[label].abstract)):
                texts[label] = rec
    lexical = {}
    for term in full.terms:
        lexical[term.id] = {label for label, rec in texts.items()
                            if contains(normalize(rec.title), term.text, True) or contains(normalize(rec.abstract), term.text, True)}
    merged = merge([r for res in results for r in res.records])
    return RunResult(query, full.terms, references, years, started, results, merged, lexical, texts, settings or {})

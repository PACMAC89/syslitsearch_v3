"""Lexical check whether a record really contains the search string in its title or abstract.

Databases stem words, search keyword fields or full text, or rank by similarity, so their hits
do not always contain the search terms. This module re-checks every hit against title and
abstract and is the filter for the reading list.

A term matches when it occurs as a whole word or phrase, with these tolerances (applied
automatically, no need to write them in the keyword file):

- case: "LLM" = "llm"
- hyphen, slash, underscore or apostrophe = space, and a hyphen may also be left out:
  "long-term memory" matches "long term memory" and "longterm memory"
- singular = plural, for every word: "memory system" matches "memory systems",
  "ontology" matches "ontologies", "agents" in the file also matches "agent"
- British = American "s/z" spelling: "personalized" matches "personalised",
  "optimization" matches "optimisation"
- accents are ignored

No stemming beyond that: "agentic memory" does not match "agent memory". A "*" at the end
of a word in the keyword file matches any continuation ("memor*").
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from functools import lru_cache

_NON_WORD = re.compile(r'[^a-z0-9]+')
_NON_WORD_KEEP_STAR = re.compile(r'[^a-z0-9*]+')
_SEPARATOR = re.compile(r'(\s+|[-‐-―−/_\']+)')
_HYPHEN_LIKE = re.compile(r'[-‐-―−/_\']+')
# s/z spelling position: "-ise/-ize", "-ised/-ized", "-ising/-izing", "-isation/-ization", "-yse/-yze", ...
_SZ = re.compile(r'(?<=[iy])[sz](?=(?:e|ed|es|er|ers|ing|ation|ations)$)')
_VOWELS = set('aeiou')


def _strip_accents(text: str) -> str:
    text = unicodedata.normalize('NFKD', text or '')
    return ''.join(c for c in text if not unicodedata.combining(c)).lower()


def normalize(text: str) -> str:
    """Lower case without accents; every run of non-alphanumeric characters becomes one space."""
    return _NON_WORD.sub(' ', _strip_accents(text)).strip()


def singular(token: str) -> str:
    """Rough English singular, so that a plural in the keyword file also matches the singular."""
    if len(token) > 4 and token.endswith('ies'):
        return token[:-3] + 'y'
    if len(token) > 4 and token.endswith('es') and (token[-3] in 'sxz' or token[-4:-2] in ('ch', 'sh')):
        return token[:-2]
    if len(token) > 3 and token.endswith('s') and not token.endswith(('ss', 'is', 'us')):
        return token[:-1]
    return token


def plural(token: str) -> str:
    """Rough English plural of a singular token."""
    if len(token) > 2 and token.endswith('y') and token[-2] not in _VOWELS:
        return token[:-1] + 'ies'
    if token.endswith(('s', 'x', 'z', 'ch', 'sh')):
        return token + 'es'
    return token + 's'


def sz_variants(token: str) -> set[str]:
    """The token in both s and z spelling where the British/American difference applies."""
    m = _SZ.search(token)
    if not m:
        return {token}
    return {token[:m.start()] + c + token[m.end():] for c in 'sz'}


def _token_regex(token: str) -> str:
    if token.endswith('*'):
        return re.escape(token.rstrip('*')) + '[a-z0-9]*'
    stem = singular(token)
    m = _SZ.search(stem)
    base = re.escape(stem) if not m else re.escape(stem[:m.start()]) + '[sz]' + re.escape(stem[m.end():])
    if len(stem) > 2 and stem.endswith('y') and stem[-2] not in _VOWELS:
        return base[:-1] + '(?:y|ies)'
    if stem.endswith(('s', 'x', 'z', 'ch', 'sh')):
        return base + '(?:es)?'
    return base + '(?:s|es)?'


@lru_cache(maxsize=None)
def term_regex(term: str) -> re.Pattern:
    """Regular expression for a keyword, to be searched in normalize()d text."""
    pieces = []
    for part in _SEPARATOR.split(_strip_accents(term).strip()):
        if not part:
            continue
        if part.isspace():
            pieces.append(r'\s')
        elif _HYPHEN_LIKE.fullmatch(part):
            pieces.append(r'\s?')
        else:
            tokens = _NON_WORD_KEEP_STAR.sub(' ', part).split()
            if tokens:
                pieces.append(r'\s'.join(_token_regex(t) for t in tokens))
    if not pieces:
        raise ValueError(f'empty search term: {term!r}')
    return re.compile(r'(?<![a-z0-9])' + ''.join(pieces) + r'(?![a-z0-9])')


def contains(text: str, term: str, normalized: bool = False) -> bool:
    """Whether the term occurs in the text (normalize()d already if normalized=True)."""
    return bool(term_regex(term).search(text if normalized else normalize(text)))


@dataclass
class MatchResult:
    """Outcome of checking one record against the grouped search string."""

    passed: bool
    matched: dict[str, list[str]] = field(default_factory=dict)  # group -> terms found
    missing: list[str] = field(default_factory=list)  # groups without any term found

    def describe_missing(self) -> str:
        return ', '.join(self.missing)


def check(title: str, abstract: str, groups: dict[str, list[str]]) -> MatchResult:
    """A record passes if every group has at least one term in its title or abstract.

    Title and abstract are searched separately, so a phrase never spans the two.
    """
    texts = [normalize(title), normalize(abstract)]
    matched, missing = {}, []
    for group, terms in groups.items():
        found = [t for t in terms if any(term_regex(t).search(x) for x in texts)]
        matched[group] = found
        if not found:
            missing.append(group)
    return MatchResult(passed=not missing, matched=matched, missing=missing)

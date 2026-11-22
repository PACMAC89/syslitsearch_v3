"""Database connectors, by command-line name."""

from .base import Source, SourceError
from .dimensions import Dimensions
from .ieee import IEEEXplore
from .scopus import Scopus
from .semantic_scholar import SemanticScholar

SOURCES = {cls.name: cls for cls in (SemanticScholar, Scopus, IEEEXplore, Dimensions)}

__all__ = ['SOURCES', 'Source', 'SourceError']

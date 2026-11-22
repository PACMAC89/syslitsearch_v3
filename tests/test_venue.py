from syslitsearch.records import MergedRecord, Record
from syslitsearch.sources.ieee import IEEEXplore
from syslitsearch.sources.scopus import Scopus
from syslitsearch.sources.semantic_scholar import SemanticScholar


def test_preprint_servers_are_recognised_by_name():
    assert Record('S2', '1', 'T', venue='arXiv.org', venue_type='journal').venue_type == 'preprint'
    assert Record('S2', '1', 'T', venue='bioRxiv').venue_type == 'preprint'
    assert Record('S2', '1', 'T', venue='', venue_type='journal').venue_type == ''


def test_published_venue_wins_over_preprint():
    s2 = Record('Semantic Scholar', '1', 'T', venue='arXiv.org')
    scopus = Record('Scopus', '2', 'T', venue='Lecture Notes in Computer Science', venue_type='book series')
    assert MergedRecord([s2, scopus]).venue() == ('Lecture Notes in Computer Science', 'book series')
    assert MergedRecord([s2]).venue() == ('arXiv.org', 'preprint')
    assert MergedRecord([Record('S2', '1', 'T')]).venue() == ('', '')


def test_first_published_venue_in_database_order():
    s2 = Record('Semantic Scholar', '1', 'T', venue='User Modeling, Adaptation, and Personalization', venue_type='conference')
    scopus = Record('Scopus', '2', 'T', venue='UMAP 2025 Adjunct Proceedings', venue_type='conference')
    assert MergedRecord([s2, scopus]).venue()[0] == 'User Modeling, Adaptation, and Personalization'


def test_semantic_scholar_venue_type():
    assert SemanticScholar.venue_type({'publicationVenue': {'type': 'conference'}, 'publicationTypes': ['JournalArticle']}) == 'conference'
    assert SemanticScholar.venue_type({'publicationVenue': {'name': 'X'}, 'publicationTypes': ['Review', 'JournalArticle']}) == 'journal'
    assert SemanticScholar.venue_type({}) == ''


def test_scopus_and_ieee_venue_types():
    assert Scopus._record({'prism:publicationName': 'LNCS', 'prism:aggregationType': 'Book Series'}).venue_type == 'book series'
    assert Scopus._record({'prism:publicationName': 'KBS', 'prism:aggregationType': 'Journal'}).venue_type == 'journal'
    assert IEEEXplore._record({'publication_title': 'ICASSP', 'content_type': 'Conferences'}).venue_type == 'conference'
    assert IEEEXplore._record({'publication_title': 'IEEE Std', 'content_type': 'Standards'}).venue_type == 'other'

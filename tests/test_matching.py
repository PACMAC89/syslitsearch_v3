import pytest

from syslitsearch.matching import check, contains, normalize, plural, singular, sz_variants


def test_normalize_hyphens_apostrophes_case_accents():
    assert normalize("Long-Term Memory: agents' café") == 'long term memory agents cafe'


@pytest.mark.parametrize('text', ['long-term memory', 'long term memory', 'Long–term memory', 'longterm memory', 'LONG-TERM MEMORIES'])
def test_hyphen_space_case_plural(text):
    assert contains(text, 'long-term memory')


@pytest.mark.parametrize('term,text', [
    ('memory system', 'two memory systems'),
    ('memory systems', 'a memory system'),
    ('ontology', 'with ontologies'),
    ('ontologies', 'an ontology'),
    ('LLM', 'LLMs and agents'),
    ('LLM agent', 'LLM-based agents'),  # does not match: "based" in between
])
def test_plural_both_ways(term, text):
    expected = term != 'LLM agent'
    assert contains(text, term) is expected


@pytest.mark.parametrize('term,text', [
    ('personalized memory', 'personalised memory'),
    ('personalised memory', 'Personalized memory'),
    ('optimization', 'optimisation of agents'),
    ('analyse', 'we analyze'),
])
def test_british_american_sz(term, text):
    assert contains(text, term)


def test_no_stemming_beyond_plural():
    assert not contains('agent memory for LLMs', 'agentic memory')
    assert not contains('agentic memory', 'agent memory')


def test_whole_words_only():
    assert contains('rdfs and turtle', 'rdf')  # side effect of the plural rule: "rdfs" counts as plural of "rdf"
    assert contains('rdf triples', 'rdf')
    assert not contains('knowledge graphical', 'knowledge graph')
    assert not contains('xLLM', 'LLM')


def test_wildcard():
    assert contains('memorization helps', 'memor*')
    assert contains('a memory system', 'memory sys*')
    assert not contains('remembering', 'memor*')


def test_check_groups():
    groups = {'A': ['large language model', 'LLM'], 'B': ['long-term memory', 'memory system']}
    ok = check('A memory system for LLM agents', '', groups)
    assert ok.passed and ok.matched == {'A': ['LLM'], 'B': ['memory system']}
    bad = check('Agents with long term memory', 'We study robots.', groups)
    assert not bad.passed and bad.missing == ['A']


def test_phrase_does_not_span_title_and_abstract():
    assert not check('A study of memory', 'System design matters', {'B': ['memory system']}).passed


def test_helpers():
    assert singular('memories') == 'memory' and plural('memory') == 'memories'
    assert singular('approaches') == 'approach' and plural('class') == 'classes'
    assert sz_variants('personalized') == {'personalized', 'personalised'}
    assert sz_variants('system') == {'system'}

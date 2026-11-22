from syslitsearch.sources import SOURCES
from syslitsearch.web import Http


def make(name):
    return SOURCES[name](Http(None))


def test_semantic_scholar_syntax():
    s2 = make('semantic_scholar')
    q = s2.render([['LLM', 'personalized memory'], ['memory system*']])
    assert q == '("LLM" | "personalized memory" | "personalised memory") + ("memory system")'
    assert s2.render([['llm*']]) == '(llm*)'


def test_scopus_syntax():
    scopus = make('scopus')
    assert scopus.render([['LLM'], ['memory system*']]) == 'TITLE-ABS-KEY(("LLM") AND ("memory system*"))'
    assert scopus.title_filter(['A title']) == '(TITLE("A title"))'


def test_dimensions_adds_plurals():
    dim = make('dimensions')
    assert dim.render([['memory system']]) == '("memory system" OR "memory systems")'


def test_ieee_title_filter():
    assert make('ieee').title_filter(['A', 'B']) == '("Document Title":"A" OR "Document Title":"B")'

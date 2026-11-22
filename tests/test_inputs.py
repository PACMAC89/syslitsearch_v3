import pytest

from syslitsearch.query import DEFAULT_GROUP, load_keywords
from syslitsearch.records import Record, merge, norm_arxiv, norm_doi
from syslitsearch.references import load_references


def write(tmp_path, name, text):
    p = tmp_path / name
    p.write_text(text, encoding='utf-8')
    return p


def test_keywords_with_groups_and_semicolons(tmp_path):
    q = load_keywords(write(tmp_path, 'k.csv', 'Group;Term\nA;LLM\nA;large language model\nB;memory system\n'))
    assert q.names == ['A', 'B']
    assert q.texts() == {'A': ['LLM', 'large language model'], 'B': ['memory system']}
    assert [t.id for t in q.terms] == ['A01', 'A02', 'B01']
    assert q.select(['B']).names == ['B']
    with pytest.raises(ValueError):
        q.select(['C'])


def test_keywords_without_group_column(tmp_path):
    q = load_keywords(write(tmp_path, 'k.csv', 'term\nLLM\nagent memory\n'))
    assert q.names == [DEFAULT_GROUP] and len(q.terms) == 2


def test_keywords_without_header(tmp_path):
    q = load_keywords(write(tmp_path, 'k.csv', 'LLM,A\nmemory system,B\n'))
    assert q.texts() == {'A': ['LLM'], 'B': ['memory system']}


def test_identifiers():
    assert norm_doi('https://doi.org/10.48550/arXiv.2501.13956') == '10.48550/arxiv.2501.13956'
    assert norm_arxiv('arXiv:2501.13956v2') == '2501.13956'
    assert Record('x', '1', 't', doi='10.48550/arXiv.2501.13956').arxiv_id == '2501.13956'


def test_references_match_by_id_and_title(tmp_path):
    refs = load_references(write(tmp_path, 'r.csv', 'label,title,arxiv_id,repo\n'
                                 'Zep,Zep: A Temporal Knowledge Graph Architecture for Agent Memory,2501.13956,graphiti\n'
                                 'Mem0,Mem0: Building Production-Ready AI Agents with Scalable Long-Term Memory,,mem0\n'))
    assert refs.labels == ['Zep', 'Mem0'] and refs.refs[0].extra == {'repo': 'graphiti'}
    by_doi = Record('S2', '1', 'something else', doi='10.48550/arXiv.2501.13956')
    by_title = Record('Scopus', '2', 'MEM0: Building production-ready AI agents with scalable long-term memory', doi='10.3233/faia251160')
    assert refs.match(by_doi).label == 'Zep' and refs.match(by_title).label == 'Mem0'


def test_status_no_abstract():
    from syslitsearch.matching import check
    groups = {'A': ['LLM'], 'B': ['memory system']}
    no_abs = Record('S2', '1', 'An LLM study')
    no_abs.check = check(no_abs.title, no_abs.abstract, groups)
    excl = Record('S2', '2', 'An LLM study', abstract='Nothing about storage here.')
    excl.check = check(excl.title, excl.abstract, groups)
    title_only = Record('S2', '3', 'A memory system for LLM agents')
    title_only.check = check(title_only.title, title_only.abstract, groups)
    assert [m.status for m in merge([no_abs])] == ['no abstract']
    assert [m.status for m in merge([excl])] == ['excluded']
    assert [m.status for m in merge([title_only])] == ['passed']


def test_merge_across_databases():
    a = Record('S2', '1', 'Zep: A Temporal Knowledge Graph Architecture for Agent Memory', arxiv_id='2501.13956')
    b = Record('Dimensions', '2', 'Zep - a temporal knowledge graph architecture for agent memory', doi='10.48550/arxiv.2501.13956')
    c = Record('S2', '3', 'Another paper about something else entirely')
    merged = merge([a, b, c])
    assert sorted(len(m.records) for m in merged) == [1, 2]

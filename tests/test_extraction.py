import json

from syslitsearch import extraction
from syslitsearch.llm import LLMError

TEXT = """Title of the paper
1 Introduction
We store facts and overwrite old ones.
References
[1] A. Author. Some paper. 2024.
[2] B. Author. Other paper. 2025.
Appendix
Table 9: LoCoMo 81.2
"""


class FakeLLM:
    def __init__(self, answers):
        self.answers, self.prompts = list(answers), []
        self.calls = self.cache_hits = self.input_tokens = self.output_tokens = 0

    def describe(self):
        return {'style': 'fake', 'model': 'fake-1', 'base_url': ''}

    def complete(self, system, user, json_mode=False):
        self.calls += 1
        self.prompts.append((system, user, json_mode))
        a = self.answers.pop(0)
        if isinstance(a, Exception):
            raise a
        return a


def test_drop_references_keeps_the_appendix():
    out = extraction.drop_references(TEXT)
    assert 'A. Author' not in out and 'Table 9: LoCoMo 81.2' in out and 'overwrite old ones' in out


def test_drop_references_in_two_columns():
    left = ('the conclusion goes on here      REFERENCES\n'
            'and ends on this line.           [1] A. Author. Some paper.\n'
            '                                 [2] B. Author. Other paper.\n\f'
            '[3] C. Author. Third paper.      [4] D. Author. Fourth paper.\n')
    out = extraction.drop_references(left)
    assert 'and ends on this line.' in out and 'conclusion goes on here' in out
    assert not any(a in out for a in ('A. Author', 'B. Author', 'C. Author', 'D. Author'))
    right = 'last words.\nReferences       man Memory: A Proposed System\n[1] A. Author. Some paper.\n'
    assert 'A. Author' not in extraction.drop_references(right)
    body = 'see the references   in Section 2 for more   and so on\n'
    assert extraction.drop_references(body) == body


def test_drop_references_cuts_nothing_if_a_table_would_go():
    text = 'Results in Table 1.\nReferences\n[1] A. Author.\nMore results              (no appendix heading)\nTable 2: LoCoMo 81.2\n'
    assert extraction.drop_references(text) == text


def test_parse_answer_handles_think_blocks_and_fences():
    assert extraction.parse_answer('<think>hmm {not json}</think>```json\n{"q1_core_approach": "dialogue memory"}\n```') == \
        {'q1_core_approach': 'dialogue memory'}
    assert extraction.parse_answer('{"papers": [{"id": "R1"}]}') == {'id': 'R1'}
    assert extraction.parse_answer('no json here') is None


def test_extract_writes_one_file_per_paper_and_resumes(tmp_path):
    (tmp_path / 'R1.txt').write_text(TEXT, encoding='utf-8')
    (tmp_path / 'R2.txt').write_text(TEXT, encoding='utf-8')
    codebook, schema = tmp_path / 'cb.md', tmp_path / 'schema.json'
    codebook.write_text('Q1 core approach', encoding='utf-8')
    schema.write_text('{"id": "...", "results": []}', encoding='utf-8')
    papers = [{'id': 'R1', 'title': 'One', 'text': str(tmp_path / 'R1.txt')},
              {'id': 'R2', 'title': 'Two', 'text': str(tmp_path / 'R2.txt')},
              {'id': 'R3', 'title': 'Three', 'text': ''}]
    out = tmp_path / 'run'
    llm = FakeLLM(['{"q7_update": "overwrite", "results": [{"benchmark": "LoCoMo", "value": "81.2"}]}', LLMError('HTTP 400')])
    stats = extraction.extract(papers, codebook, schema, out, llm, drop_refs=True, topic='dialogue memory', log=lambda m: None)
    assert stats['done'] == 1 and stats['failed'] == 2
    d = json.loads((out / 'R1.json').read_text(encoding='utf-8'))
    assert d['id'] == 'R1' and d['results'][0]['value'] == '81.2'
    system, user, json_mode = llm.prompts[0]
    assert json_mode and 'Q1 core approach' in system and '"results": []' in system and 'review on dialogue memory.' in system
    assert 'A. Author' not in user and 'Table 9: LoCoMo 81.2' in user
    assert json.loads((out / 'run.json').read_text(encoding='utf-8'))['judge']['model'] == 'fake-1'
    # a second run skips R1
    assert extraction.extract(papers[:1], codebook, schema, out, FakeLLM([]), log=lambda m: None)['skipped'] == 1


def test_unparseable_answer_is_kept_raw(tmp_path):
    (tmp_path / 'R1.txt').write_text('text', encoding='utf-8')
    (tmp_path / 'cb.md').write_text('cb', encoding='utf-8')
    (tmp_path / 's.json').write_text('{}', encoding='utf-8')
    stats = extraction.extract([{'id': 'R1', 'title': 'T', 'text': str(tmp_path / 'R1.txt')}], tmp_path / 'cb.md',
                               tmp_path / 's.json', tmp_path / 'run', FakeLLM(['sorry, no']), log=lambda m: None)
    assert stats['failed'] == 1 and (tmp_path / 'run' / 'R1.raw.txt').exists()

import json

import pytest

from syslitsearch import screening
from syslitsearch.llm import LLM, LLMError

BATCH = """### R1
Title: Mem0
Year: 2025 | Venue: arXiv.org
Abstract: A memory layer.

### R2
Title: HBM for LLMs
Year: 2026 | Venue: DATE
Abstract: Memory bandwidth.
"""


class FakeLLM:
    """Answers from a list; records the prompts."""

    def __init__(self, answers):
        self.answers, self.prompts = list(answers), []
        self.calls = self.cache_hits = self.input_tokens = self.output_tokens = 0

    def describe(self):
        return {'style': 'fake', 'model': 'fake-1'}

    def complete(self, system, user):
        self.calls += 1
        self.prompts.append(user)
        answer = self.answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return answer


def test_batch_papers_and_parsing():
    papers = screening.batch_papers(BATCH)
    assert [i for i, _ in papers] == ['R1', 'R2'] and papers[1][1].startswith('### R2')
    fenced = '```json\n{"id": "R1", "verdict": "Include", "reason": "x", "conflicts": "true"}\n```'
    assert screening.parse_judgments(fenced, {'R1'}) == {'R1': {'id': 'R1', 'verdict': 'include', 'reason': 'x', 'conflicts': True}}
    array = json.dumps([{'id': 'R1', 'verdict': 'exclude', 'reason': 'y'}, {'id': 'R9', 'verdict': 'include'}])
    assert set(screening.parse_judgments(array, {'R1', 'R2'})) == {'R1'}


def test_judge_asks_again_for_missing_papers(tmp_path):
    out = tmp_path / 'screen'
    out.mkdir()
    (out / 'criteria.md').write_text('- "Hardware:" chips', encoding='utf-8')
    (out / 'batch_01.txt').write_text(BATCH, encoding='utf-8')
    first = '{"id": "R1", "verdict": "include", "reason": "Memory layer.", "conflicts": false}\nsome chatter'
    retry = '{"id": "R2", "verdict": "exclude", "reason": "Hardware: HBM.", "conflicts": false}'
    llm = FakeLLM([first, retry])
    stats = screening.judge(out, 'llm', llm, per_request=20, log=lambda m: None)
    assert stats['judged'] == 2 and llm.calls == 2 and 'ids: R2' in llm.prompts[1]
    assert screening.check(out, 'llm') == ['01: ok (2/2)']
    assert json.loads((out / 'llm' / 'judge.json').read_text(encoding='utf-8'))['judge']['model'] == 'fake-1'
    # a complete batch is skipped on the next run
    assert screening.judge(out, 'llm', FakeLLM([]), log=lambda m: None)['judged'] == 2


def test_judge_survives_failed_requests(tmp_path):
    out = tmp_path / 'screen'
    out.mkdir()
    (out / 'criteria.md').write_text('criteria', encoding='utf-8')
    (out / 'batch_01.txt').write_text(BATCH, encoding='utf-8')
    llm = FakeLLM([LLMError('rate limit'), LLMError('rate limit'), LLMError('rate limit')])
    assert screening.judge(out, 'llm', llm, log=lambda m: None)['judged'] == 0
    assert screening.check(out, 'llm')[0].startswith('01: PROBLEM')


def test_llm_settings_from_env(monkeypatch, tmp_path):
    for k in ('LLM_API_STYLE', 'LLM_BASE_URL', 'LLM_MODEL', 'LLM_API_KEY', 'LLM_MAX_TOKENS', 'LLM_TEMPERATURE', 'LLM_EFFORT'):
        monkeypatch.delenv(k, raising=False)
    with pytest.raises(ValueError, match='LLM_MODEL'):
        LLM.from_env(tmp_path)
    monkeypatch.setenv('LLM_MODEL', 'claude-sonnet-5-5')
    monkeypatch.setenv('LLM_BASE_URL', 'https://api.anthropic.com')
    llm = LLM.from_env(tmp_path)
    assert llm.style == 'anthropic' and llm.max_tokens == 16000 and llm.temperature is None
    monkeypatch.setenv('LLM_BASE_URL', '')
    monkeypatch.setenv('LLM_API_STYLE', 'openai')
    with pytest.raises(ValueError, match='LLM_BASE_URL'):
        LLM.from_env(tmp_path)


def test_openai_request_and_cache(monkeypatch, tmp_path):
    llm = LLM('openai', 'local-model', 'http://localhost:8000/v1/', 'secret', temperature=0.0, cache_dir=tmp_path)
    sent = []

    def fake_request(method, url, json_body=None, headers=None, cache=True, **kw):
        sent.append((url, json_body, headers))
        return {'choices': [{'message': {'content': 'answer'}}], 'usage': {'prompt_tokens': 10, 'completion_tokens': 2}}

    monkeypatch.setattr(llm._http, 'request', fake_request)
    assert llm.complete('sys', 'user') == 'answer'
    assert llm.complete('sys', 'user') == 'answer'  # second time from the cache
    url, body, headers = sent[0]
    assert len(sent) == 1 and url == 'http://localhost:8000/v1/chat/completions'
    assert body['temperature'] == 0.0 and 'max_tokens' not in body and headers == {'Authorization': 'Bearer secret'}
    assert 'reasoning_effort' not in body and 'response_format' not in body
    assert 'secret' not in ''.join(p.read_text(encoding='utf-8') for p in tmp_path.iterdir())
    assert (llm.calls, llm.cache_hits, llm.input_tokens) == (1, 1, 10)


def test_openai_effort_and_json_mode(monkeypatch, tmp_path):
    llm = LLM('openai', 'gpt-oss', 'http://localhost:8000/v1', effort='high', cache_dir=None)
    sent = []
    monkeypatch.setattr(llm._http, 'request', lambda method, url, json_body=None, headers=None, cache=True, **kw:
                        sent.append(json_body) or {'choices': [{'message': {'content': '{}'}}]})
    llm.complete('sys', 'user', json_mode=True)
    assert sent[0]['reasoning_effort'] == 'high' and sent[0]['response_format'] == {'type': 'json_object'}
    assert 'allowed_openai_params' not in sent[0]


def test_openai_effort_released_for_litellm(monkeypatch):
    from syslitsearch.web import HttpError
    llm = LLM('openai', 'oski/gpt-oss', 'http://localhost:4000/v1', effort='high', cache_dir=None)
    sent = []

    def proxy(method, url, json_body=None, headers=None, cache=True, **kw):
        sent.append(dict(json_body))
        if 'allowed_openai_params' not in json_body:
            raise HttpError(400, 'HTTP 400: litellm.UnsupportedParamsError: openai does not support parameters')
        return {'choices': [{'message': {'content': 'ok'}}]}

    monkeypatch.setattr(llm._http, 'request', proxy)
    assert llm.complete('sys', 'a') == 'ok' and llm.complete('sys', 'b') == 'ok'
    assert len(sent) == 3 and sent[1]['allowed_openai_params'] == ['reasoning_effort'] and 'allowed_openai_params' in sent[2]

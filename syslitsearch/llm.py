"""A chat model behind one call: OpenAI-compatible /chat/completions or the Anthropic Messages API.

Configured by environment variables (or .env, see .env.example):

  LLM_API_STYLE    openai | anthropic (default: anthropic if LLM_BASE_URL points to anthropic.com, else openai)
  LLM_BASE_URL     openai: base URL incl. /v1, e.g. https://api.openai.com/v1, http://localhost:8000/v1 (vLLM),
                   http://localhost:11434/v1 (Ollama); anthropic: optional (default: the Anthropic API)
  LLM_MODEL        model name as the endpoint expects it
  LLM_API_KEY      API key (optional for local servers; anthropic falls back to ANTHROPIC_API_KEY)
  LLM_MAX_TOKENS   answer limit (anthropic default 16000; openai: sent only if set)
  LLM_TEMPERATURE  sent only if set (several current models reject sampling parameters)
  LLM_EFFORT       sent only if set: anthropic output_config.effort (low, medium, high, xhigh, max); openai
                   reasoning_effort (e.g. low, medium, high for gpt-oss or o-series models; released with
                   allowed_openai_params if a LiteLLM proxy rejects it)

Answers are cached on disk (key: settings + prompts, never the API key), so a repeated run costs nothing.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

from .web import Http, HttpError

STYLES = ('openai', 'anthropic')


class LLMError(RuntimeError):
    """A request that failed after the retries (rate limit, server or connection error) or was refused."""


class LLM:
    def __init__(self, style: str, model: str, base_url: str = '', api_key: str = '', max_tokens: int | None = None,
                 temperature: float | None = None, effort: str | None = None, cache_dir: Path | None = Path('.cache') / 'llm'):
        if style not in STYLES:
            raise ValueError(f'LLM_API_STYLE must be one of {", ".join(STYLES)}, not {style!r}')
        if not model:
            raise ValueError('LLM_MODEL is not set')
        if style == 'openai' and not base_url:
            raise ValueError('LLM_BASE_URL is not set (e.g. https://api.openai.com/v1)')
        self.style, self.model, self.base_url, self.api_key = style, model, base_url.rstrip('/'), api_key
        self.max_tokens = max_tokens or (16000 if style == 'anthropic' else None)
        self.temperature, self.effort = temperature, effort
        self.cache_dir = cache_dir
        if cache_dir:
            cache_dir.mkdir(parents=True, exist_ok=True)
        self.calls = self.cache_hits = self.input_tokens = self.output_tokens = 0
        self._http = Http(None, retries=6, timeout=600)
        self._client = None
        self._release_effort = False  # send allowed_openai_params for a LiteLLM proxy (set after its first refusal)

    @classmethod
    def from_env(cls, cache_dir: Path | None = Path('.cache') / 'llm') -> 'LLM':
        base_url = os.environ.get('LLM_BASE_URL', '').strip()
        style = os.environ.get('LLM_API_STYLE', '').strip().lower() or ('anthropic' if 'anthropic.com' in base_url else 'openai')
        num = lambda name, kind: kind(os.environ[name]) if os.environ.get(name, '').strip() else None  # noqa: E731
        return cls(style, os.environ.get('LLM_MODEL', '').strip(), base_url, os.environ.get('LLM_API_KEY', '').strip(),
                   num('LLM_MAX_TOKENS', int), num('LLM_TEMPERATURE', float), os.environ.get('LLM_EFFORT', '').strip() or None,
                   cache_dir)

    def describe(self) -> dict:
        """The settings that determine the answers (no API key)."""
        return {'style': self.style, 'model': self.model, 'base_url': self.base_url, 'max_tokens': self.max_tokens,
                'temperature': self.temperature, 'effort': self.effort}

    def complete(self, system: str, user: str, json_mode: bool = False) -> str:
        """Text of the model's answer to one system + user prompt. json_mode asks an OpenAI-compatible endpoint
        for a JSON object (response_format); the Anthropic style relies on the prompt instead."""
        parts = [self.describe(), system, user] + ([True] if json_mode else [])
        key = hashlib.sha256(json.dumps(parts, sort_keys=True).encode()).hexdigest()
        path = self.cache_dir / f'{key}.json' if self.cache_dir else None
        if path and path.exists():
            self.cache_hits += 1
            return json.loads(path.read_text(encoding='utf-8'))['text']
        self.calls += 1
        text, usage = self._anthropic(system, user) if self.style == 'anthropic' else self._openai(system, user, json_mode)
        self.input_tokens += usage.get('input', 0) or 0
        self.output_tokens += usage.get('output', 0) or 0
        if path:
            path.write_text(json.dumps({'text': text, 'usage': usage}), encoding='utf-8')
        return text

    def _openai(self, system: str, user: str, json_mode: bool = False) -> tuple[str, dict]:
        body = {'model': self.model, 'messages': [{'role': 'system', 'content': system}, {'role': 'user', 'content': user}]}
        if json_mode:
            body['response_format'] = {'type': 'json_object'}
        if self.max_tokens:
            body['max_tokens'] = self.max_tokens
        if self.temperature is not None:
            body['temperature'] = self.temperature
        if self.effort:
            body['reasoning_effort'] = self.effort
            if self._release_effort:
                body['allowed_openai_params'] = ['reasoning_effort']
        headers = {'Authorization': f'Bearer {self.api_key}'} if self.api_key else None
        try:
            r = self._http.request('POST', f'{self.base_url}/chat/completions', json_body=body, headers=headers, cache=False)
        except HttpError as e:
            if e.status == 429 or e.status >= 500:
                raise LLMError(str(e)) from e
            # a LiteLLM proxy rejects reasoning_effort for some models (e.g. gpt-oss) unless it is released
            if self.effort and not self._release_effort and 'UnsupportedParamsError' in str(e):
                self._release_effort = True
                return self._openai(system, user, json_mode)
            raise
        choice = (r.get('choices') or [{}])[0]
        usage = r.get('usage') or {}
        return (choice.get('message') or {}).get('content') or '', {'input': usage.get('prompt_tokens'),
                                                                   'output': usage.get('completion_tokens')}

    def _anthropic(self, system: str, user: str) -> tuple[str, dict]:
        try:
            import anthropic
        except ImportError as e:
            raise RuntimeError('LLM_API_STYLE=anthropic needs the package "anthropic": pip install -r requirements.txt') from e
        if self._client is None:
            self._client = anthropic.Anthropic(api_key=self.api_key or None, base_url=self.base_url or None,
                                               max_retries=5, timeout=600)
        kwargs = {'model': self.model, 'max_tokens': self.max_tokens, 'system': system,
                  'messages': [{'role': 'user', 'content': user}]}
        if self.temperature is not None:
            kwargs['temperature'] = self.temperature
        if self.effort:
            kwargs['output_config'] = {'effort': self.effort}
        transient = tuple(getattr(anthropic, n) for n in ('RateLimitError', 'InternalServerError', 'APIConnectionError')
                          if hasattr(anthropic, n))
        try:
            msg = self._client.messages.create(**kwargs)
        except transient as e:  # the client has already retried these
            raise LLMError(str(e)) from e
        if msg.stop_reason == 'refusal':
            raise LLMError(f'refused: {getattr(msg.stop_details, "category", None)}')
        text = ''.join(b.text for b in msg.content if b.type == 'text')
        return text, {'input': msg.usage.input_tokens, 'output': msg.usage.output_tokens}

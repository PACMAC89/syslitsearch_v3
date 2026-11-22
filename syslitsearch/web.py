"""Small HTTP client: retries on rate limits, keeps a minimum interval, caches responses on disk."""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any

import requests


class HttpError(RuntimeError):
    def __init__(self, status: int, message: str):
        super().__init__(f'HTTP {status}: {message[:300]}')
        self.status = status


class Http:
    def __init__(self, cache_dir: Path | None = None, min_interval: float = 0.0, retries: int = 8, timeout: int = 90):
        self.cache_dir = cache_dir
        self.min_interval = min_interval
        self.retries = retries
        self.timeout = timeout
        self.calls = 0
        self.cache_hits = 0
        self._last = 0.0
        self.session = requests.Session()
        self.session.headers['User-Agent'] = 'syslitsearch (systematic literature search)'
        if cache_dir:
            cache_dir.mkdir(parents=True, exist_ok=True)

    def _cache_path(self, key: dict) -> Path | None:
        if not self.cache_dir:
            return None
        digest = hashlib.sha256(json.dumps(key, sort_keys=True).encode()).hexdigest()
        return self.cache_dir / f'{digest}.json'

    def request(self, method: str, url: str, *, params: dict | None = None, json_body: Any = None, data: str | None = None,
                headers: dict | None = None, cache: bool = True) -> Any:
        """JSON response of the request; auth headers are never part of the cache key."""
        key = {'m': method, 'u': url, 'p': params, 'j': json_body, 'd': data}
        path = self._cache_path(key) if cache else None
        if path and path.exists():
            self.cache_hits += 1
            return json.loads(path.read_text(encoding='utf-8'))
        for attempt in range(self.retries):
            wait = self.min_interval - (time.monotonic() - self._last)
            if wait > 0:
                time.sleep(wait)
            self._last = time.monotonic()
            self.calls += 1
            try:
                body = data.encode('utf-8') if isinstance(data, str) else data
                r = self.session.request(method, url, params=params, json=json_body, data=body, headers=headers, timeout=self.timeout)
            except requests.RequestException:
                if attempt == self.retries - 1:
                    raise
                time.sleep(min(60, 5 * (attempt + 1)))
                continue
            if r.status_code in (429, 500, 502, 503, 504):
                retry_after = r.headers.get('Retry-After')
                delay = float(retry_after) if retry_after and retry_after.isdigit() else min(60, 5 * (attempt + 1))
                time.sleep(delay)
                continue
            if r.status_code >= 400:
                raise HttpError(r.status_code, r.text)
            result = r.json()
            if path:
                path.write_text(json.dumps(result), encoding='utf-8')
            return result
        raise HttpError(429, f'gave up after {self.retries} attempts: {url}')

    def get(self, url: str, **kw) -> Any:
        return self.request('GET', url, **kw)

    def post(self, url: str, **kw) -> Any:
        return self.request('POST', url, **kw)

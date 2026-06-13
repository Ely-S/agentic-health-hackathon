"""Shared HTTP and cache helpers for literature clients."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, cast

import httpx

from agentic_health_hackathon.journal_lookup.config import JournalLookupSettings


class DiskCache:
    """JSON and text cache stored outside the git worktree."""

    def __init__(self, cache_dir: Path) -> None:
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _path_for(self, namespace: str, key: str, suffix: str) -> Path:
        namespace_dir = self.cache_dir / namespace
        namespace_dir.mkdir(parents=True, exist_ok=True)
        digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
        return namespace_dir / f"{digest}.{suffix}"

    def read_json(self, namespace: str, key: str) -> dict[str, Any] | list[Any] | None:
        path = self._path_for(namespace, key, "json")
        if not path.exists():
            return None
        return cast(
            dict[str, Any] | list[Any],
            json.loads(path.read_text(encoding="utf-8")),
        )

    def write_json(self, namespace: str, key: str, payload: Any) -> None:
        path = self._path_for(namespace, key, "json")
        path.write_text(json.dumps(payload, ensure_ascii=True), encoding="utf-8")

    def read_text(self, namespace: str, key: str) -> str | None:
        path = self._path_for(namespace, key, "txt")
        if not path.exists():
            return None
        return path.read_text(encoding="utf-8")

    def write_text(self, namespace: str, key: str, payload: str) -> None:
        path = self._path_for(namespace, key, "txt")
        path.write_text(payload, encoding="utf-8")


class CachedHttpClient:
    """Thin synchronous HTTP client with disk-backed caching."""

    def __init__(self, settings: JournalLookupSettings) -> None:
        self.settings = settings
        self.cache = DiskCache(settings.cache_dir)
        self.client = httpx.Client(
            timeout=settings.http_timeout_seconds,
            headers={"User-Agent": settings.user_agent},
            follow_redirects=True,
        )

    def close(self) -> None:
        """Close the underlying HTTP client."""
        self.client.close()

    def get_json(
        self,
        *,
        namespace: str,
        url: str,
        params: dict[str, Any],
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any] | list[Any]:
        cache_key = self._cache_key(url, params, headers=headers)
        if cached := self.cache.read_json(namespace, cache_key):
            return cached
        response = self.client.get(url, params=params, headers=headers)
        response.raise_for_status()
        payload = cast(dict[str, Any] | list[Any], response.json())
        self.cache.write_json(namespace, cache_key, payload)
        return payload

    def get_text(
        self,
        *,
        namespace: str,
        url: str,
        params: dict[str, Any],
        headers: dict[str, str] | None = None,
    ) -> str:
        cache_key = self._cache_key(url, params, headers=headers)
        if cached := self.cache.read_text(namespace, cache_key):
            return cached
        response = self.client.get(url, params=params, headers=headers)
        response.raise_for_status()
        payload = response.text
        self.cache.write_text(namespace, cache_key, payload)
        return payload

    @staticmethod
    def _cache_key(url: str, params: dict[str, Any], headers: dict[str, str] | None = None) -> str:
        serialized = json.dumps(
            {"url": url, "params": params, "headers": headers or {}},
            ensure_ascii=True,
            sort_keys=True,
        )
        return serialized

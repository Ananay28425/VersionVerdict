"""Durable search cache and conservative application request allocation.

The allocation is not SerpApi account balance. Every reserved HTTP attempt,
including failed attempts and retries, stays counted across process restarts.
"""

import hashlib
import json
import os
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Callable

CACHE_TTL_SECONDS = 24 * 60 * 60
DEFAULT_REQUEST_BUDGET = 50


class BudgetExhausted(Exception):
    pass


def cache_key(params: dict[str, str]) -> str:
    """Parameters contain search options only, never credentials or manifests."""
    safe = {key: value for key, value in params.items() if key != 'api_key'}
    serialized = json.dumps(safe, sort_keys=True, separators=(',', ':'))
    return hashlib.sha256(serialized.encode()).hexdigest()


class SearchStore:
    def __init__(
        self,
        path: str | Path | None = None,
        *,
        budget_limit: int | None = None,
        ttl_seconds: int = CACHE_TTL_SECONDS,
        clock: Callable[[], float] = time.time,
    ):
        default_dir = Path(__file__).resolve().parents[2] / '.cache' / 'versionverdict'
        cache_dir = Path(os.getenv('VERSIONVERDICT_CACHE_DIR', str(default_dir)))
        self.path = Path(path) if path is not None else cache_dir / 'search.sqlite3'
        self.path = self.path.resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        configured_limit = os.getenv(
            'SERPAPI_REQUEST_BUDGET', str(DEFAULT_REQUEST_BUDGET)
        )
        try:
            self.budget_limit = (
                int(configured_limit) if budget_limit is None else int(budget_limit)
            )
        except ValueError as exc:
            raise ValueError(
                'SERPAPI_REQUEST_BUDGET must be a positive integer'
            ) from exc
        if self.budget_limit < 1 or ttl_seconds < 1:
            raise ValueError('Search budget and cache TTL must be positive')
        self.ttl_seconds = ttl_seconds
        self.clock = clock
        with self._connect() as connection:
            connection.execute('PRAGMA journal_mode=WAL')
            connection.execute(
                'CREATE TABLE IF NOT EXISTS search_cache '
                '(cache_key TEXT PRIMARY KEY, payload TEXT NOT NULL, fetched_at REAL NOT NULL)'
            )
            connection.execute(
                'CREATE TABLE IF NOT EXISTS search_allocation '
                '(id INTEGER PRIMARY KEY CHECK(id=1), attempts INTEGER NOT NULL)'
            )
            connection.execute('INSERT OR IGNORE INTO search_allocation VALUES (1, 0)')

    @contextmanager
    def _connect(self):
        connection = sqlite3.connect(self.path, timeout=10)
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def budget(self) -> dict[str, int]:
        with self._connect() as connection:
            used = connection.execute(
                'SELECT attempts FROM search_allocation WHERE id=1'
            ).fetchone()[0]
        return {
            'budget_limit': self.budget_limit,
            'budget_used': used,
            'budget_remaining': max(0, self.budget_limit - used),
        }

    def reserve(self) -> None:
        with self._connect() as connection:
            connection.execute('BEGIN IMMEDIATE')
            used = connection.execute(
                'SELECT attempts FROM search_allocation WHERE id=1'
            ).fetchone()[0]
            if used >= self.budget_limit:
                raise BudgetExhausted(
                    'VersionVerdict application search allocation exhausted'
                )
            connection.execute(
                'UPDATE search_allocation SET attempts=attempts+1 WHERE id=1'
            )

    def get(self, key: str) -> dict | None:
        with self._connect() as connection:
            row = connection.execute(
                'SELECT payload, fetched_at FROM search_cache WHERE cache_key=?', (key,)
            ).fetchone()
        if row is None or self.clock() - row[1] >= self.ttl_seconds:
            return None
        try:
            payload = json.loads(row[0])
        except (ValueError, TypeError):
            return None
        return payload if isinstance(payload, dict) else None

    def put(self, key: str, payload: dict) -> None:
        with self._connect() as connection:
            connection.execute(
                'INSERT OR REPLACE INTO search_cache VALUES (?, ?, ?)',
                (key, json.dumps(payload, separators=(',', ':')), self.clock()),
            )

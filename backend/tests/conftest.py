"""Keep mocked search accounting separate from the application's durable ledger."""

import pytest


@pytest.fixture(autouse=True)
def isolated_search_allocation(tmp_path, monkeypatch):
    monkeypatch.setenv('VERSIONVERDICT_CACHE_DIR', str(tmp_path / 'search-cache'))
    monkeypatch.setenv('SERPAPI_REQUEST_BUDGET', '50')

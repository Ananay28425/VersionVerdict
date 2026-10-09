"""Explicit live integration: run only with SERPAPI_KEY and permitted network access."""

import os

import httpx
import pytest
from app.retrieval import search_live


@pytest.mark.asyncio
@pytest.mark.skipif(
    not os.getenv('SERPAPI_KEY'),
    reason='SERPAPI_KEY absent; live integration unverified',
)
async def test_live_serpapi_google():
    async with httpx.AsyncClient() as client:
        hits, warnings = await search_live(
            ['pydantic model_validate site:docs.pydantic.dev'],
            os.environ['SERPAPI_KEY'],
            client,
        )
    assert hits, warnings
    assert any(h.url.startswith('https://') for h in hits)

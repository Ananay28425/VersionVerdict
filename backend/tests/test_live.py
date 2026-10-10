"""Opt-in paid-provider tests. Normal checks never spend the shared allowance."""

import os

import httpx
import pytest
from app.planner import QuerySpec
from app.retrieval import search_batch


@pytest.mark.asyncio
@pytest.mark.skipif(
    not os.getenv('SERPAPI_KEY') or os.getenv('RUN_LIVE_SERPAPI') != '1',
    reason='Explicit RUN_LIVE_SERPAPI=1 and SERPAPI_KEY are required; live integration unverified.',
)
@pytest.mark.parametrize('engine', ['google', 'bing'])
async def test_live_serpapi_engine(engine):
    async with httpx.AsyncClient() as client:
        batch = await search_batch(
            [QuerySpec(engine, 'pydantic model_validate site:docs.pydantic.dev')],
            os.environ['SERPAPI_KEY'],
            client,
        )
    assert batch.hits, batch.warnings
    assert batch.receipt['api_calls'] >= 1
    assert all(hit.provenance[0].engine == engine for hit in batch.hits)
    assert any(hit.url.startswith('https://') for hit in batch.hits)

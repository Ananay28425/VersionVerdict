"""Canonical official documentation redirects must preserve source trust bounds."""

import httpx
import pytest

from app.evidence import allowed, document, fetch_text

OLD = 'https://docs.pydantic.dev/latest/concepts/models/'
NEW = 'https://pydantic.dev/docs/validation/latest/concepts/models/'


@pytest.mark.asyncio
async def test_pydantic_canonical_documentation_redirect_is_fetched_and_attributed():
    calls = []
    def handler(request):
        calls.append(str(request.url))
        if str(request.url) == OLD:
            return httpx.Response(301, headers={'location': NEW})
        return httpx.Response(200, text='<main><h1>Models</h1><pre>from pydantic import BaseModel</pre></main>', headers={'content-type': 'text/html'})
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        body = await fetch_text(OLD, client)
    parsed = document(body)
    assert calls == [OLD, NEW]
    assert parsed['source_url'] == NEW
    assert parsed['fetched_at']


@pytest.mark.parametrize('target', [
    'https://example.com/private',
    'http://pydantic.dev/docs/validation/latest/',
    'https://pydantic.dev/pricing/',
    'https://pydantic.dev/docs/validation/../../private',
    'https://pydantic.dev/docs/validation/%2e%2e/private',
    'https://user@pydantic.dev/docs/validation/latest/',
    'https://pydantic.dev:8443/docs/validation/latest/',
])
@pytest.mark.asyncio
async def test_redirect_cannot_leave_official_documentation_boundary(target):
    calls = []
    def handler(request):
        calls.append(str(request.url))
        return httpx.Response(302, headers={'location': target})
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        assert await fetch_text(OLD, client) is None
    assert calls == [OLD]
    assert not allowed(target)


@pytest.mark.asyncio
async def test_redirect_loop_is_bounded():
    calls = []
    def handler(request):
        calls.append(str(request.url))
        return httpx.Response(301, headers={'location': OLD})
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        assert await fetch_text(OLD, client) is None
    assert len(calls) == 3

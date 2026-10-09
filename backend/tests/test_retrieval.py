"""External requests are mocked; none of these tests consume SerpApi searches."""

import asyncio
from concurrent.futures import ThreadPoolExecutor
import json

import httpx
import pytest

from app.planner import QuerySpec, plan
from app.retrieval import SearchError, canonical_url, normalize, search_batch, search_params
from app.search_store import BudgetExhausted, SearchStore, cache_key


SECRET = 'test-secret-never-return'


def payload(search_id='search-123', *, position=1, url='https://docs.pydantic.dev/latest/concepts/models/'):
    return {
        'search_metadata': {'id': search_id, 'json_endpoint': f'https://serpapi.com/search?api_key={SECRET}'},
        'search_parameters': {'api_key': SECRET},
        'organic_results': [
            {'title': 'Models', 'link': url, 'snippet': 'model_validate example', 'position': position}
        ],
    }


def store(tmp_path, limit=50, **kwargs):
    return SearchStore(tmp_path / 'search.sqlite3', budget_limit=limit, **kwargs)


def provenance(hit):
    return hit.model_dump()['provenance']


def test_plan_two_searches_shared_between_profiles_and_bing_opt_in():
    primary = plan('  validate  a model ', 'pydantic')
    expanded = plan('validate a model', 'pydantic', include_secondary=True)
    assert [item.engine for item in primary] == ['google', 'google']
    assert expanded[:2] == primary
    assert expanded[2].engine == 'bing'
    assert 'site:' not in primary[0].query and 'site:docs.pydantic.dev' in primary[1].query
    assert search_params(expanded[2]) == {'engine': 'bing', 'q': expanded[2].query, 'mkt': 'en-IN'}
    assert [item.engine for item in plan('execute SQL', 'sqlalchemy')] == ['google', 'google']
    with pytest.raises(ValueError):
        plan('question', 'unknown')


def test_google_bing_merge_keeps_original_ranks_and_search_ids():
    first = payload('google-123', position=7, url='https://docs.pydantic.dev/a/?utm_source=google')
    second = payload('bing-456', position=2, url='https://docs.pydantic.dev/a/?utm_source=bing')
    hits = normalize([first, second], ['one', 'two'], ['google', 'bing'], ['live', 'cached'])
    assert len(hits) == 1
    assert hits[0].url == 'https://docs.pydantic.dev/a/'
    assert hits[0].position == 2
    assert provenance(hits[0]) == [
        {'engine': 'google', 'query': 'one', 'position': 7, 'search_id': 'google-123', 'retrieval': 'live'},
        {'engine': 'bing', 'query': 'two', 'position': 2, 'search_id': 'bing-456', 'retrieval': 'cached'},
    ]


def test_malformed_hits_and_url_credentials_are_ignored():
    hits = normalize([{'organic_results': [None, {'link': 'javascript:alert(1)'}, {'link': 'https://example.org', 'position': 'oops'}]}], ['test'])
    assert len(hits) == 1 and hits[0].position == 3
    assert canonical_url('https://user:password@example.org/private') == ''
    assert canonical_url('https://[invalid') == ''


@pytest.mark.asyncio
async def test_cache_shared_without_manifest_or_key_and_payload_is_redacted(tmp_path):
    calls = []
    def handler(request):
        calls.append(request)
        return httpx.Response(200, json=payload())
    allocation = store(tmp_path)
    specs = [QuerySpec('google', 'validate models')]
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        first = await search_batch(specs, SECRET, client, store=allocation)
        second = await search_batch(specs, '', client, store=allocation)
    assert len(calls) == 1
    assert first.receipt['api_calls'] == 1 and first.receipt['cache_hits'] == 0
    assert second.receipt['api_calls'] == 0 and second.receipt['cache_hits'] == 1
    assert provenance(first.hits[0])[0]['retrieval'] == 'live'
    assert provenance(second.hits[0])[0]['retrieval'] == 'cached'
    cached = allocation.get(cache_key(search_params(specs[0])))
    assert SECRET not in json.dumps(cached)
    assert 'search_parameters' not in cached
    assert cached['search_metadata']['id'] == 'search-123'


@pytest.mark.asyncio
async def test_concurrent_identical_queries_use_one_attempt(tmp_path):
    calls = []
    async def handler(request):
        calls.append(request)
        await asyncio.sleep(0.03)
        return httpx.Response(200, json=payload())
    path = tmp_path / 'search.sqlite3'
    stores = [SearchStore(path, budget_limit=50), SearchStore(path, budget_limit=50)]
    specs = [QuerySpec('google', 'shared query')]
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        left, right = await asyncio.gather(*(search_batch(specs, SECRET, client, store=item) for item in stores))
    assert len(calls) == 1
    assert left.receipt['api_calls'] + right.receipt['api_calls'] == 1
    assert left.receipt['cache_hits'] + right.receipt['cache_hits'] == 1
    assert stores[0].budget()['budget_used'] == 1


@pytest.mark.asyncio
async def test_bing_opt_in_is_separate_cache_and_preserves_provenance(tmp_path):
    engines = []
    def handler(request):
        engine = request.url.params['engine']
        engines.append(engine)
        if engine == 'bing':
            assert request.url.params['mkt'] == 'en-IN'
        else:
            assert request.url.params['gl'] == 'in' and request.url.params['hl'] == 'en'
        return httpx.Response(200, json=payload(engine))
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await search_batch([QuerySpec('google', 'same'), QuerySpec('bing', 'same')], SECRET, client, store=store(tmp_path))
    assert sorted(engines) == ['bing', 'google']
    assert result.receipt['api_calls'] == 2
    assert {item['engine'] for item in provenance(result.hits[0])} == {'google', 'bing'}


@pytest.mark.asyncio
async def test_explicit_refresh_consumes_attempt_and_cache_ttl_expiry(tmp_path):
    now = [1000.0]
    allocation = store(tmp_path, clock=lambda: now[0], ttl_seconds=100)
    calls = []
    def handler(request):
        calls.append(request)
        return httpx.Response(200, json=payload(str(len(calls))))
    specs = [QuerySpec('google', 'test')]
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        await search_batch(specs, SECRET, client, store=allocation)
        refreshed = await search_batch(specs, SECRET, client, refresh=True, store=allocation)
        now[0] += 99
        cached = await search_batch(specs, SECRET, client, store=allocation)
        now[0] += 1
        expired = await search_batch(specs, SECRET, client, store=allocation)
    assert len(calls) == 3
    assert refreshed.receipt['api_calls'] == 1
    assert cached.receipt['cache_hits'] == 1
    assert expired.receipt['api_calls'] == 1
    assert allocation.budget()['budget_used'] == 3


@pytest.mark.asyncio
async def test_exhausted_budget_survives_restart_but_cached_queries_work(tmp_path):
    allocation = store(tmp_path, limit=1)
    calls = []
    def handler(request):
        calls.append(request)
        return httpx.Response(200, json=payload())
    specs = [QuerySpec('google', 'cached')]
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        await search_batch(specs, SECRET, client, store=allocation)
        restarted = store(tmp_path, limit=1)
        cached = await search_batch(specs, SECRET, client, store=restarted)
        with pytest.raises(SearchError, match='allocation exhausted') as error:
            await search_batch([QuerySpec('google', 'different')], SECRET, client, store=restarted)
    assert len(calls) == 1
    assert cached.receipt['cache_hits'] == 1
    assert error.value.status_code == 429
    assert error.value.receipt['budget_remaining'] == 0
    assert error.value.receipt['api_calls'] == 0


def test_budget_reservation_is_atomic_across_store_instances(tmp_path):
    allocations = [store(tmp_path, limit=4) for _ in range(12)]
    def reserve(allocation):
        try:
            allocation.reserve()
            return True
        except BudgetExhausted:
            return False
    with ThreadPoolExecutor(max_workers=8) as executor:
        outcomes = list(executor.map(reserve, allocations))
    assert sum(outcomes) == 4
    assert allocations[0].budget() == {'budget_limit': 4, 'budget_used': 4, 'budget_remaining': 0}


@pytest.mark.asyncio
@pytest.mark.parametrize('status,body,expected_status,match', [
    (429, {'error': f'quota {SECRET}'}, 429, 'quota'),
    (401, {'error': f'auth {SECRET}'}, 503, 'authentication'),
    (403, {'error': f'access {SECRET}'}, 503, 'access'),
    (200, {'error': f'Your api_key={SECRET} has no searches left'}, 429, 'quota'),
    (200, {'error': f'Invalid API key {SECRET}'}, 503, 'authentication'),
    (200, {'error': f'backend exploded {SECRET}'}, 502, 'unsuccessful'),
])
async def test_provider_errors_never_leak_secrets_or_retry(tmp_path, status, body, expected_status, match):
    calls = []
    def handler(request):
        calls.append(request)
        return httpx.Response(status, json=body)
    allocation = store(tmp_path)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(SearchError, match=match) as error:
            await search_batch([QuerySpec('google', 'error')], SECRET, client, store=allocation)
    assert SECRET not in str(error.value) and 'api_key=' not in str(error.value)
    assert len(calls) == 1
    assert error.value.status_code == expected_status
    assert error.value.receipt['api_calls'] == 1
    assert allocation.budget()['budget_used'] == 1
    assert allocation.get(cache_key(search_params(QuerySpec('google', 'error')))) is None


@pytest.mark.asyncio
async def test_transient_retry_counts_each_attempt(tmp_path):
    calls = []
    def handler(request):
        calls.append(request)
        return httpx.Response(503) if len(calls) == 1 else httpx.Response(200, json=payload())
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await search_batch([QuerySpec('google', 'transient')], SECRET, client, store=store(tmp_path))
    assert len(calls) == 2
    assert result.receipt['api_calls'] == result.receipt['budget_used'] == 2


@pytest.mark.asyncio
async def test_retry_cannot_overrun_budget(tmp_path):
    calls = []
    def handler(request):
        calls.append(request)
        raise httpx.ConnectError(f'URL includes {SECRET}', request=request)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(SearchError, match='allocation exhausted') as error:
            await search_batch([QuerySpec('google', 'network')], SECRET, client, store=store(tmp_path, limit=1))
    assert len(calls) == 1
    assert error.value.receipt['api_calls'] == 1
    assert SECRET not in str(error.value)


@pytest.mark.asyncio
async def test_partial_search_failure_retains_success_and_warning(tmp_path):
    def handler(request):
        if request.url.params['engine'] == 'bing':
            return httpx.Response(429)
        return httpx.Response(200, json=payload())
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await search_batch([QuerySpec('google', 'one'), QuerySpec('bing', 'two')], SECRET, client, store=store(tmp_path))
    assert result.hits and result.warnings == ['bing: SerpApi quota or rate limit reached']
    assert result.receipt['api_calls'] == 2
    assert result.receipt['engines'] == ['google', 'bing']


@pytest.mark.asyncio
async def test_empty_live_results_are_not_fabricated(tmp_path):
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(200, json={'organic_results': []}))) as client:
        result = await search_batch([QuerySpec('google', 'no sources')], SECRET, client, store=store(tmp_path))
    assert result.hits == []
    assert 'no usable organic source URLs' in result.warnings[0]


@pytest.mark.asyncio
async def test_network_concurrency_is_bounded_across_batches(tmp_path):
    running = 0
    peak = 0
    async def handler(request):
        nonlocal running, peak
        running += 1
        peak = max(peak, running)
        await asyncio.sleep(0.02)
        running -= 1
        return httpx.Response(200, json=payload())
    allocation = store(tmp_path)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        await asyncio.gather(
            search_batch([QuerySpec('google', f'first-{index}') for index in range(4)], SECRET, client, store=allocation),
            search_batch([QuerySpec('bing', f'second-{index}') for index in range(4)], SECRET, client, store=allocation),
        )
    assert peak == 2 and allocation.budget()['budget_used'] == 8


@pytest.mark.asyncio
@pytest.mark.parametrize('data', [
    {'search_metadata': {'status': 'Error'}, 'organic_results': []},
    {'search_metadata': {'status': 'Processing'}},
    {'organic_results': 'unexpected string'},
])
async def test_unfinished_or_invalid_responses_are_not_cached(tmp_path, data):
    allocation = store(tmp_path)
    spec = QuerySpec('google', 'bad response')
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(200, json=data))) as client:
        with pytest.raises(SearchError):
            await search_batch([spec], SECRET, client, store=allocation)
    assert allocation.get(cache_key(search_params(spec))) is None
    assert allocation.budget()['budget_used'] == 1

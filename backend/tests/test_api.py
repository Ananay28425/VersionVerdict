"""End-to-end API contracts with mocked provider and fetched source responses."""

import json
import sqlite3
from pathlib import Path

import httpx
import pytest

from app import main
from app.profiler import parse_profile, version_for

ROOT = Path(__file__).resolve().parents[2]
CLIENT = httpx.AsyncClient


def manifests(left=b'pydantic==1.10.15', right=b'pydantic==2.9.2'):
    return {
        'left_file': ('requirements.txt', left),
        'right_file': ('requirements.txt', right),
    }


def request_data(**overrides):
    return {
        'query': 'validate a dictionary into a Pydantic model',
        'library': 'pydantic',
        'mode': 'recorded',
        'left_pydantic_api_mode': 'native',
        'right_pydantic_api_mode': 'native',
        **overrides,
    }


@pytest.mark.asyncio
async def test_independent_pydantic_context_and_shared_pool():
    async with CLIENT(transport=httpx.ASGITransport(app=main.app), base_url='http://test') as client:
        response = await client.post(
            '/api/search',
            data=request_data(right_pydantic_api_mode='unknown'),
            files=manifests(),
        )
    assert response.status_code == 200
    result = response.json()
    left, right = result['results']
    assert left['profile']['pydantic_api_mode'] == 'native'
    assert right['profile']['pydantic_api_mode'] == 'unknown'
    assert left['cards'][0]['label'] == 'COMPATIBLE'
    assert all(card['label'] == 'UNCERTAIN' for card in right['cards'])
    assert {card['id'] for card in left['cards']} == {card['id'] for card in right['cards']}
    assert result['receipt']['api_calls'] == 0
    assert result['pool_id']


@pytest.mark.asyncio
async def test_independent_sqlalchemy_engine_modes():
    async with CLIENT(transport=httpx.ASGITransport(app=main.app), base_url='http://test') as client:
        response = await client.post('/api/search', data=request_data(
            query='execute a SQL statement with SQLAlchemy',
            library='sqlalchemy',
            left_sqlalchemy_future='false',
            right_sqlalchemy_future='true',
        ), files=manifests(b'SQLAlchemy==1.4.54', b'SQLAlchemy==1.4.54'))
    assert response.status_code == 200
    left, right = response.json()['results']
    assert next(card for card in left['cards'] if card['recipe'] == 'Engine.execute()')['label'] == 'STALE'
    assert next(card for card in right['cards'] if card['recipe'] == 'Engine.execute()')['label'] == 'WRONG_VERSION'


@pytest.mark.asyncio
async def test_two_serpapi_engines_cache_across_profiles_and_refresh(monkeypatch):
    secret = 'test-only-secret'
    monkeypatch.setenv('SERPAPI_KEY', secret)
    calls = []
    documents = json.loads((ROOT / 'fixtures/evidence/documents.json').read_text())
    pydantic_urls = [url for url in documents if 'pydantic' in url]

    def handle(request):
        if request.url.host == 'serpapi.com':
            assert request.url.scheme == 'https'
            assert request.url.path == '/search.json'
            assert request.url.params.get('api_key') == secret
            engine = request.url.params['engine']
            assert engine in {'google', 'bing'}
            calls.append(engine)
            urls = pydantic_urls if engine == 'google' else ['https://stackoverflow.com/questions/123/example']
            return httpx.Response(200, json={
                'search_metadata': {'id': f'mocked-{engine}-{len(calls)}', 'status': 'Success'},
                'organic_results': [
                    {'title': 'Models', 'link': url, 'position': index + 1, 'snippet': 'Discovery only'}
                    for index, url in enumerate(urls)
                ],
            })
        if str(request.url) in documents:
            return httpx.Response(200, text=documents[str(request.url)], headers={'content-type': 'text/html'})
        raise AssertionError(f'Unexpected external request host: {request.url.host}')

    transport = httpx.MockTransport(handle)
    monkeypatch.setattr(main.httpx, 'AsyncClient', lambda **kwargs: CLIENT(transport=transport, **kwargs))
    async with CLIENT(transport=httpx.ASGITransport(app=main.app), base_url='http://test') as client:
        fresh = await client.post('/api/search', data=request_data(mode='live', include_secondary='true'), files=manifests())
        assert fresh.status_code == 200, fresh.text
        assert secret not in fresh.text and 'api_key=' not in fresh.text
        data = fresh.json()
        assert data['mode'] == 'live'
        assert data['receipt']['api_calls'] == 3
        assert sorted(calls) == ['bing', 'google', 'google']
        assert data['candidate_count'] == 3
        assert {provenance['engine'] for card in data['results'][0]['cards'] for provenance in card['hit']['provenance']} == {'google', 'bing'}
        assert any(card['label'] == 'UNCERTAIN' and 'stackoverflow' in card['hit']['url'] for card in data['results'][0]['cards'])
        assert [group['cards'][0]['recipe'] for group in data['results']] == ['parse_obj()', 'model_validate()']

        cached = await client.post('/api/search', data=request_data(mode='live', include_secondary='true'), files=manifests(b'pydantic==2.9.2', b'pydantic==1.10.15'))
        assert cached.status_code == 200
        replay = cached.json()
        assert replay['mode'] == 'cached'
        assert replay['receipt']['api_calls'] == 0
        assert replay['receipt']['cache_hits'] == 3
        assert secret not in cached.text and 'api_key=' not in cached.text
        assert len(calls) == 3
        assert replay['pool_id'] == data['pool_id']
        assert [group['cards'][0]['recipe'] for group in replay['results']] == ['model_validate()', 'parse_obj()']

        refreshed = await client.post('/api/search', data=request_data(mode='live', include_secondary='true', refresh='true'), files=manifests())
        assert refreshed.status_code == 200
        assert refreshed.json()['receipt']['api_calls'] == 3
        assert refreshed.json()['receipt']['budget_used'] == 6
        assert len(calls) == 6
        assert secret not in refreshed.text and 'api_key=' not in refreshed.text
        capabilities = await client.get('/api/capabilities')
        assert capabilities.json()['live_search_configured'] is True
        assert secret not in capabilities.text and 'api_key=' not in capabilities.text

    assert secret.encode() not in main.SearchStore().path.read_bytes()


@pytest.mark.asyncio
async def test_capabilities_and_verification_artifacts():
    async with CLIENT(transport=httpx.ASGITransport(app=main.app), base_url='http://test') as client:
        response = await client.get('/api/capabilities')
        assert response.status_code == 200
        capabilities = response.json()
        assert {engine['id'] for engine in capabilities['engines']} == {'google', 'bing'}
        assert capabilities['budget']['used'] == 0
        assert 'account' in capabilities['budget']['scope']
        witnesses = await client.get('/api/witnesses')
        evaluation = await client.get('/api/evaluation')
        assert witnesses.status_code == evaluation.status_code == 200
        assert witnesses.json()['summary']['fail'] == 0
        assert evaluation.json()['case_count'] >= 20
        assert (await client.get('/api/not-a-route')).status_code == 404


@pytest.mark.asyncio
async def test_frontend_documents_are_revalidated_and_assets_have_correct_types(tmp_path, monkeypatch):
    dist = tmp_path / 'frontend' / 'dist'
    (dist / 'assets').mkdir(parents=True)
    (dist / 'index.html').write_text('<html>VersionVerdict</html>')
    (dist / 'assets' / 'app-test.js').write_text('console.log("loaded")')
    monkeypatch.setattr(main, 'ROOT', tmp_path)
    async with CLIENT(transport=httpx.ASGITransport(app=main.app), base_url='http://test') as client:
        for path in ['/', '/index.html', '/workspace']:
            response = await client.get(path)
            assert response.status_code == 200
            assert response.headers['cache-control'] == 'no-cache'
            assert response.headers['content-type'].startswith('text/html')
        script = await client.get('/assets/app-test.js')
        assert script.status_code == 200
        assert 'javascript' in script.headers['content-type']
        assert script.text == 'console.log("loaded")'


@pytest.mark.asyncio
async def test_missing_frontend_assets_do_not_receive_html_fallback(tmp_path, monkeypatch):
    dist = tmp_path / 'frontend' / 'dist'
    dist.mkdir(parents=True)
    (dist / 'index.html').write_text('<html>VersionVerdict</html>')
    monkeypatch.setattr(main, 'ROOT', tmp_path)
    async with CLIENT(transport=httpx.ASGITransport(app=main.app), base_url='http://test') as client:
        for path in ['/assets/stale-build.js', '/assets/missing', '/missing.css']:
            response = await client.get(path)
            assert response.status_code == 404
            assert response.headers['content-type'].startswith('application/json')
            assert 'Rebuild' in response.json()['detail']


@pytest.mark.asyncio
@pytest.mark.parametrize('payload', [
    b'project = "not-a-table"',
    b'[project]\ndependencies = "pydantic==2.9.2"',
    b'[project]\ndependencies = [42]',
    b'[project]\ndynamic = "dependencies"',
    b'[project]\ndynamic = ["dependencies"]\ndependencies = ["pydantic==2.9.2"]',
    b'tool = "not-a-table"',
    b'[tool]\npoetry = "not-a-table"',
    b'[tool.poetry]\ndependencies = "not-a-table"',
])
async def test_malformed_manifest_structure_returns_validation_error(payload):
    async with CLIENT(transport=httpx.ASGITransport(app=main.app), base_url='http://test') as client:
        response = await client.post('/api/search', data=request_data(), files={'left_file': ('pyproject.toml', payload)})
    assert response.status_code == 422


@pytest.mark.parametrize('unresolved', [
    b'pydantic==1.10.15; python_version < "3.13"',
    b'pydantic @ https://example.com/pydantic.whl',
])
def test_unresolved_declaration_prevents_exact_version_claim(unresolved):
    for lines in [b'pydantic==2.9.2\n' + unresolved, unresolved + b'\npydantic==2.9.2']:
        profile = parse_profile('conflict', [('requirements.txt', lines)])
        assert version_for(profile, 'pydantic') is None
        assert len(profile.dependencies) == 2


@pytest.mark.parametrize('poetry', ['"^1.10"', '{version="^1.10", optional=true}'])
def test_unresolved_poetry_declaration_cannot_hide_a_conflict(poetry):
    body = ('[project]\ndependencies=["pydantic==2.9.2"]\n'
            '[tool.poetry.dependencies]\npydantic=' + poetry).encode()
    profile = parse_profile('mixed', [('pyproject.toml', body)])
    assert version_for(profile, 'pydantic') is None
    assert len(profile.dependencies) == 2


@pytest.mark.asyncio
async def test_unavailable_quota_storage_returns_service_error(monkeypatch):
    def unavailable_store():
        raise sqlite3.OperationalError('Internal database path')
    monkeypatch.setattr(main, 'SearchStore', unavailable_store)
    async with CLIENT(transport=httpx.ASGITransport(app=main.app), base_url='http://test') as client:
        response = await client.get('/api/capabilities')
    assert response.status_code == 503
    assert 'Internal database path' not in response.text

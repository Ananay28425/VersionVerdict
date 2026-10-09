import asyncio
import json
from pathlib import Path

import httpx
import pytest
from app.applicability import classify, rank
from app.evidence import extract, fetch_text, fixture_text
from app.main import app
from app.planner import plan
from app.profiler import parse_profile, version_for
from app.retrieval import SearchError, normalize, search_live

ROOT = Path(__file__).resolve().parents[2]
FACTS = json.loads((ROOT / 'fixtures/evidence/facts.json').read_text())


def profile(name, **kwargs):
    return parse_profile(
        name,
        [
            (
                'requirements.txt',
                (ROOT / f'fixtures/profiles/{name}-requirements.txt').read_bytes(),
            )
        ],
        **kwargs,
    )


def cards(library, name, **kwargs):
    data = json.loads((ROOT / f'fixtures/evidence/{library}_search.json').read_text())
    hits = normalize(data['responses'], ['query'])
    p = profile(name, **kwargs)
    return rank([classify(h, fixture_text(h), p, library, FACTS) for h in hits])


def test_pydantic_version_reverses_top_recipe():
    old = cards('pydantic', 'pydantic-v1')
    new = cards('pydantic', 'pydantic-v2')
    assert [(c.recipe, c.label.value) for c in old] == [
        ('parse_obj()', 'COMPATIBLE'),
        ('model_validate()', 'WRONG_VERSION'),
    ]
    assert [(c.recipe, c.label.value) for c in new] == [
        ('model_validate()', 'COMPATIBLE'),
        ('parse_obj()', 'STALE'),
    ]
    assert {c.hit.id for c in old} == {c.hit.id for c in new}
    assert all(len(c.evidence) == 2 for c in old + new)


def test_sqlalchemy_drift_and_future_unknown():
    old = cards('sqlalchemy', 'sqlalchemy-14', sqlalchemy_future=False)
    new = cards('sqlalchemy', 'sqlalchemy-20', sqlalchemy_future=False)
    assert {c.recipe: c.label.value for c in old}['Engine.execute()'] == 'STALE'
    assert {c.recipe: c.label.value for c in new}['Engine.execute()'] == 'WRONG_VERSION'
    unknown = cards('sqlalchemy', 'sqlalchemy-14', sqlalchemy_future=None)
    assert {c.recipe: c.label.value for c in unknown}['Engine.execute()'] == 'UNCERTAIN'


def test_no_body_or_fact_abstains():
    c = cards('pydantic', 'pydantic-v2')[0]
    assert (
        classify(c.hit, None, profile('pydantic-v2'), 'pydantic', FACTS).label.value
        == 'UNCERTAIN'
    )
    facts = dict(FACTS)
    facts['pydantic_new'] = 'wrong text'
    assert (
        classify(
            c.hit, fixture_text(c.hit), profile('pydantic-v2'), 'pydantic', facts
        ).label.value
        == 'UNCERTAIN'
    )


def test_outside_verified_release_line_abstains():
    hit = cards('sqlalchemy', 'sqlalchemy-20', sqlalchemy_future=False)[0].hit
    older = parse_profile(
        'older', [('requirements.txt', b'SQLAlchemy==1.3.24')], sqlalchemy_future=False
    )
    assert (
        classify(hit, fixture_text(hit), older, 'sqlalchemy', FACTS).label.value
        == 'UNCERTAIN'
    )


def test_manifest_range_duplicate_and_marker():
    p = parse_profile(
        'x',
        [
            (
                'requirements.txt',
                b'pydantic>=1,<3\npydantic==2.9.2\nSQLAlchemy>=2; python_version<"3.12"\n',
            )
        ],
    )
    assert version_for(p, 'pydantic') is None
    assert any('multiple declarations' in w for w in p.warnings)
    assert any('marker' in w for w in p.warnings)
    assert len(p.dependencies) == 2


def test_pyproject_and_rejected_path():
    p = parse_profile(
        'x', [('pyproject.toml', b'[project]\ndependencies=["pydantic==2.9.2"]\n')]
    )
    assert version_for(p, 'pydantic') == '2.9.2'
    with pytest.raises(ValueError):
        parse_profile('x', [('setup.py', b'print(1)')])
    combined = parse_profile(
        'combined',
        [
            ('requirements.txt', b'SQLAlchemy==2.0.36'),
            ('pyproject.toml', b'[project]\ndependencies=["pydantic==2.9.2"]'),
        ],
    )
    assert version_for(combined, 'sqlalchemy') == '2.0.36'
    assert version_for(combined, 'pydantic') == '2.9.2'


def test_source_extraction_strips_navigation_and_scripts():
    text = extract(
        '<nav>Skip</nav><main><h1>Migration</h1><pre>model_validate()</pre><script>bad()</script></main>'
    )
    assert 'Migration' in text and 'model_validate()' in text
    assert 'Skip' not in text and 'bad()' not in text


@pytest.mark.asyncio
async def test_document_fetch_rejects_unknown_hosts_and_redirects():
    called = []

    def handler(request):
        called.append(str(request.url))
        return httpx.Response(302, headers={'Location': 'https://example.com/private'})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        assert await fetch_text('https://example.com/private', client) is None
        assert (
            await fetch_text('https://docs.pydantic.dev/latest/migration/', client)
            is None
        )
    assert len(called) == 1


@pytest.mark.asyncio
async def test_serpapi_adapter_normalizes_dedup_and_errors():
    def handler(request):
        assert request.url.params['engine'] == 'google'
        assert request.url.params['api_key'] == 'test-key'
        return httpx.Response(
            200,
            json={
                'organic_results': [
                    {
                        'title': 'A',
                        'link': 'https://docs.pydantic.dev/latest/migration/?utm_source=x',
                        'snippet': 'parse_obj()',
                        'position': 1,
                    }
                ]
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        hits, warnings = await search_live(['first', 'second'], 'test-key', client)
    assert len(hits) == 1 and len(hits[0].queries) == 2 and warnings == []
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda req: httpx.Response(200, json={'error': 'quota'})
        )
    ) as client:
        with pytest.raises(SearchError, match='quota'):
            await search_live(['query'], 'test-key', client)


@pytest.mark.asyncio
async def test_api_recorded_comparison():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url='http://test') as client:
        files = {
            'left_file': (
                'requirements.txt',
                (ROOT / 'fixtures/profiles/pydantic-v1-requirements.txt').read_bytes(),
            ),
            'right_file': (
                'requirements.txt',
                (ROOT / 'fixtures/profiles/pydantic-v2-requirements.txt').read_bytes(),
            ),
        }
        r = await client.post(
            '/api/search',
            data={
                'query': 'validate a dictionary into a Pydantic model',
                'library': 'pydantic',
                'mode': 'recorded',
                'pydantic_api_mode': 'native',
            },
            files=files,
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data['mode'] == 'recorded'
        assert [g['cards'][0]['recipe'] for g in data['results']] == [
            'parse_obj()',
            'model_validate()',
        ]
        assert 'Illustrative' in data['warnings'][0]


@pytest.mark.asyncio
async def test_live_missing_key_is_clear(monkeypatch):
    monkeypatch.delenv('SERPAPI_KEY', raising=False)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url='http://test'
    ) as client:
        r = await client.post(
            '/api/search',
            data={
                'query': 'validate a dictionary into a Pydantic model',
                'library': 'pydantic',
                'mode': 'live',
            },
            files={'left_file': ('requirements.txt', b'pydantic==1.10.15')},
        )
    assert r.status_code == 503 and 'SERPAPI_KEY' in r.text

"""Confirmed hard negatives found during the final applicability review.

All requests are mocked. These cases must abstain rather than treating a token
or a name outside its lexical scope as verified API applicability.
"""

import html
import json
from pathlib import Path

import httpx
import pytest
from app.applicability import classify
from app.evidence import allowed, extract, fetch_text
from app.models import SearchHit
from app.profiler import parse_profile

ROOT = Path(__file__).resolve().parents[2]
FACTS = json.loads((ROOT / 'fixtures/evidence/facts.json').read_text())
PYDANTIC_SETUP = 'from pydantic import BaseModel\nclass User(BaseModel):\n    id: int\n'


def classify_recipe(
    code, *, library='pydantic', manifest='pydantic==2.9.2', future=None
):
    host = 'docs.pydantic.dev' if library == 'pydantic' else 'docs.sqlalchemy.org'
    hit = SearchHit(
        id='safety',
        title='Migration examples',
        position=1,
        url=f'https://{host}/latest/',
        snippet='model_validate execute',
    )
    body = extract(f'<main><h2>Example</h2><pre>{html.escape(code)}</pre></main>')
    profile = parse_profile(
        'Safety',
        [('requirements.txt', manifest.encode())],
        pydantic_api_mode='native',
        sqlalchemy_future=future,
    )
    return classify(hit, body, profile, library, FACTS)


@pytest.mark.parametrize(
    'code',
    [
        PYDANTIC_SETUP + 'User: object = object()\nUser.model_validate({"id": 1})',
        PYDANTIC_SETUP
        + 'User.model_validate: object = lambda value: value\nUser.model_validate({"id": 1})',
        PYDANTIC_SETUP
        + 'def validate(User):\n    return User.model_validate({"id": 1})\nvalidate(object())',
    ],
)
def test_model_receiver_and_method_shadowing_cannot_create_compatibility(code):
    assert classify_recipe(code).label == 'UNCERTAIN'


def test_commit_as_you_go_is_not_a_legacy_sqlalchemy_connection_api():
    code = (
        'from sqlalchemy import create_engine, text\n'
        'engine = create_engine("sqlite://", future=False)\n'
        'with engine.connect() as conn:\n'
        '    conn.execute(text("CREATE TABLE foo (id int)"))\n'
        '    conn.commit()'
    )
    assert (
        classify_recipe(
            code, library='sqlalchemy', manifest='SQLAlchemy==1.4.54', future=False
        ).label
        == 'UNCERTAIN'
    )


def test_sqlalchemy_two_rejects_explicit_legacy_engine_creation():
    code = (
        'from sqlalchemy import create_engine, text\n'
        'engine = create_engine("sqlite://", future=False)\n'
        'with engine.begin() as conn:\n'
        '    conn.execute(text("SELECT 1"))'
    )
    assert (
        classify_recipe(code, library='sqlalchemy', manifest='SQLAlchemy==2.0.36').label
        == 'UNCERTAIN'
    )


def test_repeated_heading_titles_do_not_merge_unrelated_import_scopes():
    code = 'class User(BaseModel):\n    id: int\nUser.model_validate({"id": 1})'
    source = (
        '<main><h2>Example</h2><pre>from pydantic import BaseModel</pre>'
        f'<h2>Example</h2><pre>{html.escape(code)}</pre></main>'
    )
    hit = SearchHit(
        id='repeated',
        title='Examples',
        position=1,
        url='https://docs.pydantic.dev/latest/',
        snippet='model_validate',
    )
    profile = parse_profile(
        'Test', [('requirements.txt', b'pydantic==2.9.2')], pydantic_api_mode='native'
    )
    assert (
        classify(hit, extract(source), profile, 'pydantic', FACTS).label == 'UNCERTAIN'
    )


def test_multiple_code_blocks_in_same_section_can_share_explicit_imports():
    code = 'class User(BaseModel):\n    id: int\nUser.model_validate({"id": 1})'
    source = (
        '<main><h2>Example</h2><pre>from pydantic import BaseModel</pre>'
        f'<pre>{html.escape(code)}</pre></main>'
    )
    hit = SearchHit(
        id='same-section',
        title='Examples',
        position=1,
        url='https://docs.pydantic.dev/latest/',
        snippet='model_validate',
    )
    profile = parse_profile(
        'Test', [('requirements.txt', b'pydantic==2.9.2')], pydantic_api_mode='native'
    )
    assert (
        classify(hit, extract(source), profile, 'pydantic', FACTS).label == 'COMPATIBLE'
    )


@pytest.mark.parametrize(
    'url',
    [
        'http://docs.pydantic.dev/latest/',
        'https://docs.pydantic.dev.evil.example/latest/',
        'https://user:password@docs.pydantic.dev/latest/',
        'https://docs.pydantic.dev:443/latest/',
        'https://127.0.0.1/latest/',
    ],
)
def test_evidence_url_requires_exact_https_documentation_host(url):
    assert not allowed(url)


@pytest.mark.asyncio
async def test_official_source_redirect_cannot_trigger_external_fetch():
    calls = []

    def handler(request):
        calls.append(str(request.url))
        return httpx.Response(302, headers={'location': 'http://127.0.0.1/private'})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        assert await fetch_text('https://docs.pydantic.dev/latest/', client) is None
    assert calls == ['https://docs.pydantic.dev/latest/']

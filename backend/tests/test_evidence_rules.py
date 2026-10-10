"""Adversarial evidence cases: plausible tokens must not create factual certainty."""

import hashlib
import html
import json
from pathlib import Path

import httpx
import pytest
from app.applicability import classify, classify_all
from app.evidence import collect, document, extract, fetch_text
from app.models import SearchHit
from app.profiler import parse_profile

ROOT = Path(__file__).resolve().parents[2]
FACTS = json.loads((ROOT / 'fixtures/evidence/facts.json').read_text())
PYD_OLD = 'from pydantic import BaseModel\nclass User(BaseModel):\n    id: int\nUser.parse_obj({"id": 1})'
PYD_NEW = PYD_OLD.replace('parse_obj', 'model_validate')
SQL_SETUP = (
    'from sqlalchemy import create_engine, text\nengine = create_engine("sqlite://")\n'
)
SQL_TEXT = (
    SQL_SETUP + 'with engine.begin() as conn:\n    conn.execute(text("SELECT 1"))'
)


def page(code: str, heading='Models'):
    return extract(
        f'<main><h2 id="example">{heading}</h2><pre>{html.escape(code)}</pre></main>'
    )


def profile(manifest='pydantic==2.9.2', mode='native', future=None):
    return parse_profile(
        'test',
        [('requirements.txt', manifest.encode())],
        pydantic_api_mode=mode,
        sqlalchemy_future=future,
    )


def hit(library='pydantic'):
    host = 'docs.pydantic.dev' if library == 'pydantic' else 'docs.sqlalchemy.org'
    return SearchHit(
        id='source',
        title='Ordinary documentation title',
        url=f'https://{host}/latest/concepts/models/',
        position=1,
        snippet='parse_obj model_validate Engine.execute Connection.execute',
    )


def verdict(
    code, manifest='pydantic==2.9.2', mode='native', future=None, library='pydantic'
):
    return classify(
        hit(library), page(code), profile(manifest, mode, future), library, FACTS
    )


def test_generic_titles_do_not_hide_code_recipes():
    result = verdict(PYD_NEW)
    assert result.label == 'COMPATIBLE'
    assert result.evidence[0].quote == PYD_NEW
    assert result.evidence[0].section == 'Models'
    assert result.evidence[1].provenance == 'reviewed_snapshot'


def test_old_and_new_code_sections_produce_separate_stable_cards():
    body = extract(
        f'<main><h2>Old</h2><pre>{html.escape(PYD_OLD)}</pre>'
        f'<h2>New</h2><pre>{html.escape(PYD_NEW)}</pre></main>'
    )
    old = classify_all(hit(), body, profile('pydantic==1.10.15'), 'pydantic', FACTS)
    new = classify_all(hit(), body, profile(), 'pydantic', FACTS)
    assert [card.label for card in old] == ['COMPATIBLE', 'WRONG_VERSION']
    assert [card.label for card in new] == ['STALE', 'COMPATIBLE']
    assert [card.id for card in old] == [card.id for card in new]
    assert len(set(card.id for card in new)) == 2
    assert classify(hit(), body, profile(), 'pydantic', FACTS).label == 'UNCERTAIN'


def test_api_mentions_and_unstructured_text_are_not_recipes():
    text = extract(
        '<main><h2>Models</h2><p>parse_obj() became model_validate().</p></main>'
    )
    assert classify(hit(), text, profile(), 'pydantic', FACTS).label == 'UNCERTAIN'
    assert classify(hit(), PYD_NEW, profile(), 'pydantic', FACTS).label == 'UNCERTAIN'
    assert verdict('print("User.model_validate({})")').label == 'UNCERTAIN'


@pytest.mark.parametrize(
    'code',
    [
        'User.model_validate({"id": 1})',
        PYD_NEW.replace('pydantic import', 'unrelated import'),
        'def unrelated():\n    from pydantic import BaseModel\nclass User(BaseModel):\n    id: int\nUser.model_validate({"id": 1})',
        'from pydantic import BaseModel\nclass User(BaseModel):\n    def model_validate(self, value): return value\nUser.model_validate({})',
    ],
)
def test_missing_wrong_or_custom_model_context_abstains(code):
    assert verdict(code).label == 'UNCERTAIN'


@pytest.mark.parametrize(
    'version', ['2.0rc1', '2.9.2.dev1', '2.9.2+custom', '2.9.2.post1', '3.0.0', '1.9.2']
)
def test_unreviewed_versions_abstain(version):
    assert verdict(PYD_NEW, f'pydantic=={version}').label == 'UNCERTAIN'


def test_ranges_and_unknown_api_namespace_abstain():
    assert verdict(PYD_NEW, 'pydantic>=1,<3').label == 'UNCERTAIN'
    assert verdict(PYD_NEW, mode='unknown').label == 'UNCERTAIN'
    assert verdict(PYD_NEW, mode='v1_shim').label == 'UNCERTAIN'


def test_explicit_v1_shim_is_version_and_namespace_sensitive():
    old = PYD_OLD.replace('from pydantic import', 'from pydantic.v1 import')
    new = old.replace('parse_obj', 'model_validate')
    assert verdict(old, mode='v1_shim').label == 'COMPATIBLE'
    assert verdict(new, mode='v1_shim').label == 'WRONG_VERSION'
    assert verdict(old, 'pydantic==1.10.15', mode='v1_shim').label == 'WRONG_VERSION'
    assert verdict(old, mode='native').label == 'UNCERTAIN'


def test_fact_fragment_or_modified_snapshot_cannot_substitute_for_reviewed_source():
    for bad in [
        '| `parse_obj()` | `model_validate()` |',
        FACTS['pydantic_new'] + '\nmodified',
    ]:
        facts = {**FACTS, 'pydantic_new': bad}
        assert (
            classify(hit(), page(PYD_NEW), profile(), 'pydantic', facts).label
            == 'UNCERTAIN'
        )
    manifest = json.loads(
        (ROOT / 'fixtures/evidence/reviewed/manifest.json').read_text()
    )
    for item in manifest:
        actual = (ROOT / 'fixtures/evidence/reviewed' / item['file']).read_bytes()
        assert hashlib.sha256(actual).hexdigest() == item['sha256']


def test_sqlalchemy_connection_requires_executable_statement_and_transaction_scope():
    assert (
        verdict(SQL_TEXT, 'SQLAlchemy==2.0.36', library='sqlalchemy').label
        == 'COMPATIBLE'
    )
    raw = SQL_TEXT.replace('text("SELECT 1")', '"SELECT 1"')
    assert verdict(raw, 'SQLAlchemy==2.0.36', library='sqlalchemy').label == 'UNCERTAIN'
    write = SQL_TEXT.replace('engine.begin()', 'engine.connect()').replace(
        'SELECT 1', 'INSERT INTO foo VALUES (1)'
    )
    assert (
        verdict(write, 'SQLAlchemy==2.0.36', library='sqlalchemy').label == 'UNCERTAIN'
    )
    assert (
        verdict(
            write + '\n    conn.commit()', 'SQLAlchemy==2.0.36', library='sqlalchemy'
        ).label
        == 'COMPATIBLE'
    )
    closed = (
        SQL_SETUP
        + 'with engine.connect() as conn:\n    pass\nconn.execute(text("SELECT 1"))'
    )
    assert (
        verdict(closed, 'SQLAlchemy==2.0.36', library='sqlalchemy').label == 'UNCERTAIN'
    )


def test_sqlalchemy_future_context_and_reviewed_versions():
    engine = SQL_SETUP + 'engine.execute("SELECT 1")'
    assert (
        verdict(engine, 'SQLAlchemy==1.4.54', future=False, library='sqlalchemy').label
        == 'STALE'
    )
    assert (
        verdict(engine, 'SQLAlchemy==1.4.54', future=True, library='sqlalchemy').label
        == 'WRONG_VERSION'
    )
    assert (
        verdict(engine, 'SQLAlchemy==1.4.54', future=None, library='sqlalchemy').label
        == 'UNCERTAIN'
    )
    assert (
        verdict(SQL_TEXT, 'SQLAlchemy==1.4.54', future=None, library='sqlalchemy').label
        == 'UNCERTAIN'
    )
    assert (
        verdict(
            SQL_TEXT, 'SQLAlchemy==1.3.24', future=False, library='sqlalchemy'
        ).label
        == 'UNCERTAIN'
    )


def test_imports_do_not_leak_across_unrelated_heading_sections():
    body = extract(
        '<main><h2>Unrelated</h2><pre>from pydantic import BaseModel</pre>'
        '<h2>Other namespace</h2><pre>class User(BaseModel):\n    id: int\nUser.model_validate({})</pre></main>'
    )
    assert classify(hit(), body, profile(), 'pydantic', FACTS).label == 'UNCERTAIN'


@pytest.mark.asyncio
async def test_official_evidence_not_starved_by_unsupported_first_results():
    candidates = [
        SearchHit(
            id=str(index),
            title='Community',
            url=f'https://example.com/{index}',
            position=index + 1,
        )
        for index in range(10)
    ]
    candidates.append(hit())
    calls = []

    def handler(request):
        calls.append(str(request.url))
        return httpx.Response(
            200,
            headers={'content-type': 'text/html'},
            text=f'<main><pre>{html.escape(PYD_NEW)}</pre></main>',
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        sources = await collect(candidates, client, 'live')
    assert list(sources) == ['source']
    assert len(calls) == 1
    assert document(sources['source'])['fetched_at']


@pytest.mark.asyncio
async def test_oversized_and_non_html_source_bodies_are_rejected():
    for response in [
        httpx.Response(200, content=b'x' * 2_000_001),
        httpx.Response(
            200, headers={'content-type': 'application/json'}, json={'text': PYD_NEW}
        ),
    ]:
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(lambda _: response)
        ) as client:
            assert await fetch_text(hit().url, client) is None


def test_source_engine_mode_cannot_contradict_profile():
    source = (
        SQL_SETUP.replace(
            'create_engine("sqlite://")', 'create_engine("sqlite://", future=True)'
        )
        + 'engine.execute("SELECT 1")'
    )
    assert (
        verdict(source, 'SQLAlchemy==1.4.54', future=False, library='sqlalchemy').label
        == 'UNCERTAIN'
    )


@pytest.mark.parametrize(
    'body',
    [
        'with engine.connect() as conn:\n    conn.execute(text("INSERT INTO foo VALUES (1)"))\nconn.commit()',
        'with engine.connect() as conn:\n    conn.commit()\n    conn.execute(text("INSERT INTO foo VALUES (1)"))',
        'with engine.connect() as conn:\n    conn.execute(text("INSERT INTO foo VALUES (1)"))\n    other.commit()',
        'with engine.begin() as conn:\n    conn = object()\n    conn.execute(text("SELECT 1"))',
    ],
)
def test_transaction_scope_order_and_receiver_shadowing_abstain(body):
    assert (
        verdict(SQL_SETUP + body, 'SQLAlchemy==2.0.36', library='sqlalchemy').label
        == 'UNCERTAIN'
    )


def test_shadowed_base_model_and_receiver_abstain():
    base = 'from pydantic import BaseModel\nBaseModel = Fake\nclass User(BaseModel):\n    id: int\nUser.model_validate({})'
    receiver = PYD_NEW.replace(
        'User.model_validate', 'User = object()\nUser.model_validate'
    )
    custom = 'from pydantic import BaseModel\nclass User(BaseModel):\n    id: int\nUser.model_validate = lambda value: value\nUser.model_validate({})'
    for code in [base, receiver, custom]:
        assert verdict(code).label == 'UNCERTAIN'

"""Universal context declarations and conservative, source-only version claims."""

import json
import socket

import httpx
import pytest

from app import evidence, main
from app.evidence import document, extract, fetch_text, public_allowed, public_addresses
from app.generic_applicability import classify_generic, rank_generic
from app.models import Card, Label, SearchHit
from app.planner import plan
from app.profiler import parse_profile, version_for

CLIENT = httpx.AsyncClient


def context(version='2.1.0', **kwargs):
    data = {'technology': 'Zephyr', 'language': 'C', 'platform': 'RTOS', 'hardware': 'ESP32',
            'dependencies': [{'name': 'Zephyr', 'version': version}], **kwargs}
    return parse_profile('Firmware', [('environment.json', json.dumps(data).encode())])


def card(prose, version='2.1.0', query='How to use gpio_init?', heading='GPIO'):
    hit = SearchHit(id='public-doc', title='Version 9.0 current',
                    url='https://docs.example.org/9.0/', position=1,
                    snippet='gpio_init requires Zephyr >=2.0')
    body = extract(f'<main><h2>{heading}</h2>{prose}</main>', provenance='fetched_source')
    return classify_generic(hit, body, context(version), 'Zephyr', query)


def test_generic_explicit_condition_reverses_without_recipe_registry():
    assert card('<p>gpio_init requires Zephyr >=2.0,&lt;3.0.</p>').label == 'COMPATIBLE'
    assert card('<p>gpio_init requires Zephyr >=2.0,&lt;3.0.</p>', '1.9.0').label == 'WRONG_VERSION'
    assert card('<p>gpio_init was removed in Zephyr 2.0.</p>').label == 'WRONG_VERSION'
    assert card('<p>gpio_init was deprecated in Zephyr 2.0.</p>').label == 'STALE'
    assert card('<p>gpio_init was removed in Zephyr 3.0.</p>').label == 'UNCERTAIN'
    assert card('<p>gpio_init requires Zephyr version 2.0 or higher.</p>').label == 'COMPATIBLE'
    assert card('<p>gpio_init requires Zephyr 2.0 or later.</p>', '1.9.0').label == 'WRONG_VERSION'


@pytest.mark.parametrize('prose,heading', [
    ('<p>gpio_init requires Zephyr >=2.0.</p>', 'Windows only'),
    ('<p>gpio_init requires Zephyr >=2.0.</p><p>Only available on Windows.</p>', 'GPIO'),
    ('<p>gpio_init requires Zephyr >=2.0. Only available on Windows.</p>', 'GPIO'),
    ('<p>gpio_init requires Zephyr >=2.0 if CONFIG_GPIO is enabled.</p>', 'GPIO'),
    ('<p>gpio_init requires Zephyr >=2.0 and driver version 4.</p>', 'GPIO'),
    ('<p>gpio_init requires Zephyr >=2.0 OR &lt;1.5.</p>', 'GPIO'),
    ('<p>gpio_init requires Zephyr >=2.0rc1.</p>', 'GPIO'),
    ('<p>gpio_init requires Zephyr >=2.0.</p><p>gpio_init requires Zephyr &lt;2.0.</p>', 'GPIO'),
    ('<p>uart_init requires Zephyr >=2.0.</p>', 'GPIO'),
    ('<p>gpio_init requires Rust >=2.0.</p>', 'GPIO'),
    ('<p>gpio_init was not introduced in Zephyr 2.0.</p>', 'GPIO'),
    ('<p>gpio_init was not removed in Zephyr 2.0.</p>', 'GPIO'),
    ('<p>gpio_init never requires Zephyr >=2.0.</p>', 'GPIO'),
    ('<p>It is false that gpio_init requires Zephyr >=2.0.</p>', 'GPIO'),
    ('<p>Myth: gpio_init requires Zephyr >=2.0.</p>', 'GPIO'),
])
def test_generic_uncertainty_not_overridden_by_title_snippet_or_url(prose, heading):
    assert card(prose, heading=heading).label == 'UNCERTAIN'


def test_parent_scope_qualifier_and_unknown_version_abstain():
    hit = SearchHit(id='condition', title='Latest', url='https://docs.example.org/', position=1)
    body = extract('<main><h1>Windows only</h1><h2>GPIO</h2><p>gpio_init requires Zephyr >=2.0.</p></main>')
    assert classify_generic(hit, body, context(), 'Zephyr', 'gpio_init').label == 'UNCERTAIN'
    missing = context(dependencies=[{'name': 'Zephyr', 'constraint': '>=1,<3'}])
    result = classify_generic(hit, extract('<p>gpio_init requires Zephyr >=2.0.</p>'), missing, 'Zephyr', 'gpio_init')
    assert result.label == 'UNCERTAIN' and result.evidence
    inherited = extract('<main><h1>GPIO</h1><p>Only available on Windows.</p><h2>Usage</h2><p>gpio_init requires Zephyr >=2.0.</p></main>')
    assert classify_generic(hit, inherited, context(), 'Zephyr', 'gpio_init').label == 'UNCERTAIN'
    for prefix in ['<p>' + 'x' * 2001 + ' Only available on Windows.</p>',
                   '<p>intro</p>' * 301 + '<p>Only available on Windows.</p>']:
        truncated = extract('<main><h1>GPIO</h1>' + prefix + '<p>gpio_init requires Zephyr >=2.0.</p></main>')
        assert classify_generic(hit, truncated, context(), 'Zephyr', 'gpio_init').label == 'UNCERTAIN'


def test_generic_uncertain_source_still_exposes_fetched_excerpts():
    result = card('<p>gpio_init configures GPIO pins.</p>')
    assert result.label == 'UNCERTAIN'
    assert result.evidence[0].quote == 'gpio_init configures GPIO pins.'
    assert result.evidence[0].source_kind == 'fetched source excerpt; applicability unresolved'


def test_environment_json_is_typed_and_retains_context():
    profile = context()
    assert profile.technology == 'Zephyr' and profile.hardware == 'ESP32'
    assert profile.dependencies[0].ecosystem == 'declared'
    assert version_for(profile, 'zephyr') == '2.1.0'
    for data in [
        {'technology': 'x', 'dependencies': [{'name': 'x', 'version': '>=2'}]},
        {'technology': 'x', 'dependencies': [{'name': 'x', 'version': '2', 'constraint': '>=2'}]},
        {'technology': 'x', 'execute': 'danger'},
        {'technology': 'x', 'hardware': ['unsupported']},
    ]:
        with pytest.raises(ValueError):
            parse_profile('Invalid', [('environment.json', json.dumps(data).encode())])


def test_safe_manifest_parsers_preserve_ecosystem_semantics():
    npm = parse_profile('NPM', [('package.json', b'{"dependencies":{"react":"18.2.0","vite":"^6.0.0"}}')])
    assert version_for(npm, 'react') == '18.2.0' and version_for(npm, 'vite') is None
    assert npm.dependencies[1].constraint == '^6.0.0'
    cargo = parse_profile('Rust', [('Cargo.toml', b'[dependencies]\nserde="1.0.210"\ntokio="=1.40.0"\n')])
    assert version_for(cargo, 'serde') is None and version_for(cargo, 'tokio') == '1.40.0'
    go = parse_profile('Go', [('go.mod', b'module example.org/app\ngo 1.22\nrequire (\nexample.org/sdk v2.1.0\n)')])
    assert version_for(go, 'example.org/sdk') == '2.1.0' and version_for(go, 'go') is None
    platformio = parse_profile('MCU', [('platformio.ini', b'[env:esp]\nplatform=espressif32@6.8.1\nboard=esp32dev\nframework=arduino\nlib_deps=owner/Driver@1.2.3')])
    assert platformio.hardware == 'esp32dev' and version_for(platformio, 'owner/Driver') == '1.2.3'


def test_cargo_conditional_and_go_replacements_are_unresolved():
    cargo = parse_profile('Rust', [('Cargo.toml', b'[dependencies]\nserde={version="=1.0.210",optional=true}\n')])
    assert version_for(cargo, 'serde') is None
    custom = parse_profile('Fork', [('Cargo.toml', b'[dependencies]\nserde={version="=1.0.210",git="https://example.org/fork"}\n')])
    assert version_for(custom, 'serde') is None
    go = parse_profile('Go', [('go.mod', b'require example.org/sdk v2.1.0\nreplace example.org/sdk => ../sdk')])
    assert version_for(go, 'example.org/sdk') is None and go.warnings


def test_generic_query_pool_includes_both_versions_once_and_bounded():
    specs = plan('gpio_init error', 'Zephyr', True, profiles=[context('2.1.0'), context('1.9.0')])
    assert [spec.engine for spec in specs] == ['google', 'google', 'bing']
    assert '2.1.0' in specs[1].query and '1.9.0' in specs[1].query
    assert '("2.1.0" OR "1.9.0")' in specs[1].query
    assert 'ESP32' not in specs[0].query and '"ESP32"' in specs[1].query


def test_generic_query_keeps_platform_prose_out_of_broad_question():
    profile = context(platform='bare metal', language='C', hardware='STM32F407')
    specs = plan('FreeRTOS task notification API requirements', 'FreeRTOS', profiles=[profile])
    assert specs[0].query == 'FreeRTOS task notification API requirements "FreeRTOS"'
    assert 'bare' not in specs[0].query and 'bare' not in specs[1].query
    escaped = plan('API error', 'Tool "OR" \\ other')
    assert escaped[0].query == 'API error "Tool OR other"'


def test_generic_relevance_orders_api_over_dictionary_without_changing_verdicts():
    unrelated = Card(hit=SearchHit(id='dictionary', title='BARE Definition',
                                  url='https://dictionary.example.org/bare', snippet='bare hands', position=1),
                     label=Label.UNCERTAIN, explanation='No source evidence')
    relevant = Card(hit=SearchHit(id='docs', title='FreeRTOS task notifications',
                                 url='https://www.freertos.org/task-notifications',
                                 snippet='Task notification API requirements', position=8),
                    label=Label.UNCERTAIN, explanation='No source evidence')
    ordered = rank_generic([unrelated, relevant], 'FreeRTOS', 'task notification API requirements')
    assert ordered[0].hit.id == 'docs' and ordered[0].relevance_score == 40
    assert unrelated.relevance_score == 0
    assert all(card.label == Label.UNCERTAIN and not card.evidence for card in ordered)
    assert all('ordering only' in card.ranking_reasons[-1] for card in ordered)


def test_generic_relevance_does_not_cross_verdict_priority_buckets():
    cards = [Card(hit=SearchHit(id=label.value, title='FreeRTOS task notification requirements',
                               url='https://www.freertos.org/notifications', position=1),
                  label=label, explanation='Test source verdict') for label in Label]
    for item in cards:
        if item.label == Label.COMPATIBLE:
            item.hit.title = 'unmatched'
            item.hit.url = 'https://docs.example.org/'
            item.hit.position = 10
    ranked = rank_generic(cards, 'FreeRTOS', 'task notification requirements')
    assert [item.label for item in ranked] == [Label.COMPATIBLE, Label.UNCERTAIN, Label.STALE, Label.WRONG_VERSION]


@pytest.mark.parametrize('url', [
    'http://docs.example.org/', 'https://127.0.0.1/', 'https://169.254.169.254/latest/',
    'https://localhost/', 'https://machine.internal/', 'https://user:pass@docs.example.org/',
    'https://docs.example.org:8443/', 'https://[::1]/', 'https://0.0.0.0/',
])
def test_public_source_rejects_private_and_credential_urls(url):
    assert not public_allowed(url)


@pytest.mark.asyncio
async def test_dns_mixed_answer_and_timeout_are_rejected(monkeypatch):
    monkeypatch.setattr(socket, 'getaddrinfo', lambda *args, **kwargs: [
        (2, 1, 6, '', ('93.184.216.34', 443)), (2, 1, 6, '', ('127.0.0.1', 443))])
    assert await public_addresses('docs.example.org') == []


@pytest.mark.asyncio
async def test_generic_fetch_pins_ip_and_tls_hostname_without_credentials(monkeypatch):
    async def resolve(host):
        return ['93.184.216.34']
    monkeypatch.setattr(evidence, 'public_addresses', resolve)
    calls = []
    def handler(request):
        calls.append(request)
        assert request.url.host == '93.184.216.34'
        assert request.headers['host'] == 'docs.example.org'
        assert request.extensions['sni_hostname'] == 'docs.example.org'
        assert request.headers['connection'] == 'close'
        assert 'authorization' not in request.headers and 'cookie' not in request.headers
        assert 'api_key' not in request.url.params
        return httpx.Response(200, text='<p>gpio_init requires Zephyr >=2.0.</p>', headers={'content-type': 'text/html'})
    async with CLIENT(transport=httpx.MockTransport(handler), headers={'Authorization': 'secret'}, cookies={'key': 'secret'}) as client:
        body = await fetch_text('https://docs.example.org/gpio', client, universal=True)
    assert document(body)['source_url'] == 'https://docs.example.org/gpio' and len(calls) == 1


@pytest.mark.asyncio
async def test_generic_redirect_rechecks_dns_and_stops_private_target(monkeypatch):
    async def resolve(host):
        return ['93.184.216.34'] if host == 'docs.example.org' else []
    monkeypatch.setattr(evidence, 'public_addresses', resolve)
    calls = []
    def handler(request):
        calls.append(request)
        return httpx.Response(302, headers={'location': 'https://other.example.org/private'})
    async with CLIENT(transport=httpx.MockTransport(handler)) as client:
        assert await fetch_text('https://docs.example.org/', client, universal=True) is None
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_universal_api_shared_live_pool_and_truthful_recorded_rejection(monkeypatch):
    monkeypatch.setenv('SERPAPI_KEY', 'synthetic-only')
    async def resolve(host):
        return ['93.184.216.34']
    monkeypatch.setattr(evidence, 'public_addresses', resolve)
    search_calls = []
    def handler(request):
        if request.url.host == 'serpapi.com':
            search_calls.append(request.url.params['engine'])
            return httpx.Response(200, json={'organic_results': [{'title': 'GPIO', 'link': 'https://docs.example.org/gpio', 'position': 1}]})
        return httpx.Response(200, text='<p>gpio_init requires Zephyr >=2.0.</p>', headers={'content-type': 'text/html'})
    monkeypatch.setattr(main.httpx, 'AsyncClient', lambda **kwargs: CLIENT(transport=httpx.MockTransport(handler), **kwargs))
    files = {'left_file': ('environment.json', json.dumps({'technology':'Zephyr','dependencies':[{'name':'Zephyr','version':'2.1.0'}]})),
             'right_file': ('environment.json', json.dumps({'technology':'Zephyr','dependencies':[{'name':'Zephyr','version':'1.9.0'}]}))}
    async with CLIENT(transport=httpx.ASGITransport(app=main.app), base_url='http://test') as client:
        result = await client.post('/api/search', data={'query':'gpio_init error', 'library':'Zephyr'}, files=files)
        assert result.status_code == 200, result.text
        groups = result.json()['results']
        assert groups[0]['cards'][0]['label'] == 'COMPATIBLE'
        assert groups[1]['cards'][0]['label'] == 'WRONG_VERSION'
        assert groups[0]['cards'][0]['hit']['id'] == groups[1]['cards'][0]['hit']['id']
        assert search_calls == ['google', 'google']
        unsupported = await client.post('/api/search', data={'query':'gpio_init error', 'library':'Zephyr', 'mode':'recorded'}, files=files)
        assert unsupported.status_code == 422

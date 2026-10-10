"""SerpApi Google/Bing discovery with explicit provenance and request accounting."""

import asyncio
from dataclasses import dataclass
import hashlib
import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
import weakref

import httpx

from .models import SearchHit, SearchProvenance
from .planner import QuerySpec
from .search_store import BudgetExhausted, SearchStore, cache_key


SERPAPI_URL = 'https://serpapi.com/search.json'
SUPPORTED_ENGINES = {'google', 'bing'}
_loop_locks: weakref.WeakKeyDictionary = weakref.WeakKeyDictionary()
_loop_semaphores: weakref.WeakKeyDictionary = weakref.WeakKeyDictionary()


class SearchError(Exception):
    def __init__(self, message: str, *, receipt: dict | None = None, status_code: int = 502):
        super().__init__(message)
        self.receipt = receipt
        self.status_code = status_code


@dataclass
class SearchBatch:
    hits: list[SearchHit]
    warnings: list[str]
    receipt: dict


def canonical_url(url: str) -> str:
    try:
        parsed = urlsplit(url)
        if parsed.scheme not in {'http', 'https'} or not parsed.hostname:
            return ''
        if parsed.username or parsed.password:
            return ''
        params = [
            (key, value)
            for key, value in parse_qsl(parsed.query)
            if not key.lower().startswith(('utm_', 'fbclid', 'gclid', 'api_key'))
        ]
        return urlunsplit(('https', parsed.hostname.lower(), parsed.path or '/', urlencode(params), ''))
    except ValueError:
        return ''


def _position(value: object, fallback: int) -> int:
    try:
        position = int(value)
    except (TypeError, ValueError):
        return fallback
    return position if position > 0 else fallback


def normalize(
    payloads: list[dict],
    queries: list[str],
    engines: list[str] | None = None,
    retrieval_modes: list[str] | None = None,
) -> list[SearchHit]:
    seen: dict[str, SearchHit] = {}
    for index, (query, payload) in enumerate(zip(queries, payloads)):
        if not isinstance(payload, dict):
            continue
        engine = engines[index] if engines else 'google'
        mode = retrieval_modes[index] if retrieval_modes else 'illustrative'
        metadata = payload.get('search_metadata', {})
        search_id = metadata.get('id') if isinstance(metadata, dict) else None
        results = payload.get('organic_results', [])
        if not isinstance(results, list):
            continue
        for rank, item in enumerate(results[:10], start=1):
            if not isinstance(item, dict):
                continue
            url = canonical_url(str(item.get('link', '')))
            if not url:
                continue
            position = _position(item.get('position'), rank)
            provenance = {
                'engine': engine,
                'query': query,
                'position': position,
                'search_id': str(search_id) if search_id else None,
                'retrieval': mode,
            }
            if url in seen:
                hit = seen[url]
                if query not in hit.queries:
                    hit.queries.append(query)
                hit.provenance.append(SearchProvenance(**provenance))
                hit.position = min(hit.position, position)
                continue
            seen[url] = SearchHit(
                id=hashlib.sha256(url.encode()).hexdigest()[:16],
                title=str(item.get('title', 'Untitled'))[:200],
                url=url,
                snippet=str(item.get('snippet', ''))[:600],
                position=position,
                queries=[query],
                provenance=[provenance],
            )
    return list(seen.values())


def search_params(spec: QuerySpec) -> dict[str, str]:
    if spec.engine not in SUPPORTED_ENGINES:
        raise SearchError('Unsupported search engine; choose Google or Bing')
    params = {'engine': spec.engine, 'q': spec.query}
    if spec.engine == 'google':
        params.update(hl='en', gl='in')
    else:
        params['mkt'] = 'en-IN'
    return params


def _safe_payload(payload: dict, secret: str) -> dict:
    """Persist a minimal response, excluding search_parameters and provider URLs."""
    def clean(value: object, limit: int) -> str:
        text = str(value or '')
        if secret:
            text = text.replace(secret, '[redacted]')
        text = re.sub(r'(?i)api_key\s*[=:]\s*[^\s&]+', 'api_key=[redacted]', text)
        return text[:limit]

    metadata = payload.get('search_metadata', {})
    results = payload.get('organic_results', [])
    return {
        'search_metadata': {'id': clean(metadata.get('id'), 100) if isinstance(metadata, dict) else ''},
        'organic_results': [
            {
                'link': clean(item.get('link'), 4000),
                'title': clean(item.get('title'), 200),
                'snippet': clean(item.get('snippet'), 600),
                'position': _position(item.get('position'), rank),
            }
            for rank, item in enumerate(results[:10], start=1)
            if isinstance(item, dict)
        ],
    }


def _provider_error(payload: dict) -> SearchError:
    # Provider strings can echo request URLs, API keys, or user input. Classify
    # locally and expose fixed text instead of passing their contents through.
    error = str(payload.get('error', '')).casefold()
    if any(word in error for word in ('quota', 'rate limit', 'run out', 'searches left', 'credits')):
        return SearchError('SerpApi quota or rate limit reached', status_code=429)
    if any(word in error for word in ('api key', 'api_key', 'authentication', 'unauthorized', 'access denied')):
        return SearchError('SerpApi authentication or access failed', status_code=503)
    return SearchError('SerpApi returned an unsuccessful search response')


async def search_batch(
    specs: list[QuerySpec],
    key: str,
    client: httpx.AsyncClient,
    *,
    refresh: bool = False,
    store: SearchStore | None = None,
) -> SearchBatch:
    store = store if store is not None else SearchStore()
    loop = asyncio.get_running_loop()
    semaphore = _loop_semaphores.setdefault(loop, asyncio.Semaphore(2))
    locks = _loop_locks.setdefault(loop, weakref.WeakValueDictionary())
    api_calls = 0
    cache_hits = 0

    async def one(spec: QuerySpec):
        nonlocal api_calls, cache_hits
        params = search_params(spec)
        identifier = cache_key(params)
        lock = locks.setdefault((str(store.path), identifier), asyncio.Lock())
        async with lock:
            if not refresh:
                cached = await asyncio.to_thread(store.get, identifier)
                if cached is not None:
                    cache_hits += 1
                    return cached, 'cached'
            if not key:
                raise SearchError('Live SerpApi search needs a backend API key', status_code=503)
            async with semaphore:
                for attempt in range(2):
                    try:
                        await asyncio.to_thread(store.reserve)
                    except BudgetExhausted as exc:
                        raise SearchError(str(exc), status_code=429) from None
                    api_calls += 1
                    try:
                        response = await client.get(
                            SERPAPI_URL,
                            params={**params, 'api_key': key},
                            timeout=15,
                            follow_redirects=False,
                        )
                        if response.status_code == 429:
                            raise SearchError('SerpApi quota or rate limit reached', status_code=429)
                        if response.status_code in {401, 403}:
                            raise SearchError('SerpApi authentication or access failed', status_code=503)
                        if response.status_code >= 500 and attempt == 0:
                            await asyncio.sleep(0.4)
                            continue
                        if response.status_code >= 400:
                            raise SearchError(f'SerpApi HTTP response failed ({response.status_code})')
                        payload = response.json()
                        if not isinstance(payload, dict):
                            raise SearchError('SerpApi returned an invalid JSON response')
                        if payload.get('error'):
                            raise _provider_error(payload)
                        metadata = payload.get('search_metadata', {})
                        if isinstance(metadata, dict) and metadata.get('status') in {'Error', 'Processing'}:
                            raise SearchError('SerpApi search did not complete successfully')
                        if not isinstance(payload.get('organic_results', []), list):
                            raise SearchError('SerpApi returned invalid organic results')
                        safe = _safe_payload(payload, key)
                        await asyncio.to_thread(store.put, identifier, safe)
                        return safe, 'live'
                    except (httpx.TimeoutException, httpx.TransportError):
                        if attempt == 0:
                            await asyncio.sleep(0.4)
                            continue
                        raise SearchError('SerpApi connection failed after one retry') from None
                    except ValueError:
                        raise SearchError('SerpApi returned invalid JSON') from None

    outcomes = await asyncio.gather(*(one(spec) for spec in specs), return_exceptions=True)
    good = [(spec, outcome) for spec, outcome in zip(specs, outcomes) if isinstance(outcome, tuple)]
    warnings = []
    for spec, outcome in zip(specs, outcomes):
        if isinstance(outcome, SearchError):
            warnings.append(f'{spec.engine}: {outcome}')
        elif isinstance(outcome, Exception):
            warnings.append(f'{spec.engine}: Search storage or retrieval failed')
    receipt = {
        'engines': list(dict.fromkeys(spec.engine for spec in specs)),
        'api_calls': api_calls,
        'cache_hits': cache_hits,
        **await asyncio.to_thread(store.budget),
        'cache_ttl_seconds': store.ttl_seconds,
    }
    if not good:
        errors = [item for item in outcomes if isinstance(item, SearchError)]
        status = errors[0].status_code if errors else 502
        raise SearchError('; '.join(warnings) or 'No search queries were planned', receipt=receipt, status_code=status)
    hits = normalize(
        [outcome[0] for _, outcome in good],
        [spec.query for spec, _ in good],
        [spec.engine for spec, _ in good],
        [outcome[1] for _, outcome in good],
    )
    if not hits:
        warnings.append('Search completed but returned no usable organic source URLs')
    return SearchBatch(hits=hits, warnings=warnings, receipt=receipt)


async def search_live(
    queries: list[str], key: str, client: httpx.AsyncClient
) -> tuple[list[SearchHit], list[str]]:
    """Legacy Google-only adapter; new callers should consume search_batch receipts."""
    result = await search_batch([QuerySpec('google', query) for query in queries], key, client)
    return result.hits, result.warnings

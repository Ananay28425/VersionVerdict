import asyncio
import hashlib
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
import httpx
from .models import SearchHit

SERPAPI_URL = 'https://serpapi.com/search.json'

class SearchError(Exception):
    pass

def canonical_url(url: str) -> str:
    u = urlsplit(url)
    if u.scheme not in {'http', 'https'}:
        return ''
    params = [(k, v) for k, v in parse_qsl(u.query) if not k.lower().startswith(('utm_', 'fbclid', 'gclid', 'api_key'))]
    return urlunsplit(('https', (u.hostname or '').lower(), u.path or '/', urlencode(params), ''))

def normalize(payloads: list[dict], queries: list[str]) -> list[SearchHit]:
    seen: dict[str, SearchHit] = {}
    for query, payload in zip(queries, payloads):
        for item in payload.get('organic_results', [])[:10]:
            url = canonical_url(str(item.get('link', '')))
            if not url:
                continue
            if url in seen:
                seen[url].queries.append(query)
                continue
            seen[url] = SearchHit(id=hashlib.sha256(url.encode()).hexdigest()[:16], title=str(item.get('title', 'Untitled'))[:200], url=url, snippet=str(item.get('snippet', ''))[:600], position=int(item.get('position') or 99), queries=[query])
    return list(seen.values())

async def search_live(queries: list[str], key: str, client: httpx.AsyncClient) -> tuple[list[SearchHit], list[str]]:
    semaphore = asyncio.Semaphore(2)
    async def one(q: str):
        async with semaphore:
            for attempt in range(2):
                try:
                    response = await client.get(SERPAPI_URL, params={'engine':'google','q':q,'api_key':key,'hl':'en','gl':'in'}, timeout=15)
                    if response.status_code == 429:
                        raise SearchError('SerpApi quota or rate limit reached')
                    if response.status_code in {401, 403}:
                        raise SearchError('SerpApi authentication or access failed')
                    if response.status_code >= 500 and attempt == 0:
                        await asyncio.sleep(0.4)
                        continue
                    response.raise_for_status()
                    data = response.json()
                    if not isinstance(data, dict) or data.get('error'):
                        raise SearchError(str(data.get('error', 'Invalid SerpApi response'))[:200] if isinstance(data, dict) else 'Invalid SerpApi response')
                    return data
                except (httpx.TimeoutException, httpx.TransportError) as exc:
                    if attempt == 0:
                        await asyncio.sleep(0.4)
                        continue
                    raise SearchError(f'SerpApi connection failed: {type(exc).__name__}') from exc
                except (httpx.HTTPStatusError, ValueError) as exc:
                    raise SearchError(f'SerpApi response failed: {type(exc).__name__}') from exc
    results = await asyncio.gather(*(one(q) for q in queries), return_exceptions=True)
    good = [(q, r) for q, r in zip(queries, results) if isinstance(r, dict)]
    warnings = [str(r) for r in results if isinstance(r, Exception)]
    if not good:
        raise SearchError('; '.join(warnings) or 'No SerpApi results')
    return normalize([r for _, r in good], [q for q, _ in good]), warnings

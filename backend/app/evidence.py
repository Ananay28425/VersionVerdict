"""Bounded official-source retrieval and heading-scoped, inspectable code evidence."""

import asyncio
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote, urljoin, urlsplit

import httpx
from bs4 import BeautifulSoup
from bs4.element import Tag

from .models import Evidence, SearchHit

ALLOWED = {'docs.pydantic.dev', 'pydantic.dev', 'docs.sqlalchemy.org'}
FIXTURE_ROOT = Path(__file__).resolve().parents[2] / 'fixtures' / 'evidence'
FORMAT = 'versionverdict.source.v1'
MAX_BYTES = 2_000_000
MAX_TEXT = 120_000
MAX_CODE = 12_000


def allowed(url: str) -> bool:
    try:
        parsed = urlsplit(url)
        trusted_path = parsed.hostname != 'pydantic.dev' or (
            parsed.path.startswith('/docs/validation/')
            and '..' not in unquote(parsed.path).split('/')
        )
        return (trusted_path and parsed.scheme == 'https' and parsed.hostname in ALLOWED
                and parsed.port is None and parsed.username is None
                and parsed.password is None)
    except ValueError:
        return False


def extract(html: str, *, provenance: str = 'fetched_source', fetched_at: str | None = None,
            source_url: str | None = None) -> str:
    """Return a serialized document; retain code boundaries rather than flattening recipes.

    Each block carries its enclosing heading and the text of that heading's section.
    Sibling imports may be consulted only within that section, never across the page.
    """
    soup = BeautifulSoup(html, 'html.parser')
    for node in soup(['script', 'style', 'nav', 'footer', 'header']):
        node.decompose()
    root = soup.find('main') or soup.find('article') or soup
    blocks: list[dict] = []
    heading = 'Document'
    section_id = None
    scope_id = 0
    section_parts: list[str] = []
    section_indices: list[int] = []

    def flush() -> None:
        context = ' '.join(section_parts)[:8_000]
        for index in section_indices:
            blocks[index]['context'] = context

    # A pre includes its descendant code/spans; process it once, preserving whitespace.
    for node in root.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'p', 'pre']):
        if any(isinstance(parent, Tag) and parent.name == 'pre' for parent in node.parents):
            continue
        if node.name.startswith('h'):
            flush()
            scope_id += 1
            heading = node.get_text(' ', strip=True)[:300]
            section_id = node.get('id')
            section_parts = []
            section_indices = []
        elif node.name == 'p':
            section_parts.append(node.get_text(' ', strip=True))
        elif node.name == 'pre':
            code = node.get_text('', strip=False)
            if not code.strip() or len(code) > MAX_CODE:
                continue
            section_indices.append(len(blocks))
            blocks.append({'heading': heading, 'section_id': section_id,
                           'scope_id': scope_id, 'code': code, 'context': ''})
            if len(blocks) >= 100:
                break
    flush()
    return json.dumps({'format': FORMAT, 'text': root.get_text(' ', strip=True)[:MAX_TEXT],
                       'blocks': blocks, 'content_hash': hashlib.sha256(html.encode()).hexdigest(),
                       'provenance': provenance, 'fetched_at': fetched_at,
                       'source_url': source_url}, ensure_ascii=False)


def document(body: str) -> dict | None:
    try:
        value = json.loads(body)
    except (TypeError, ValueError):
        return None
    if not isinstance(value, dict) or value.get('format') != FORMAT:
        return None
    if not isinstance(value.get('blocks'), list) or not isinstance(value.get('text'), str):
        return None
    return value


async def fetch_text(url: str, client: httpx.AsyncClient) -> str | None:
    if not allowed(url):
        return None
    try:
        # Validate every hop ourselves. Pydantic's old docs host now redirects to
        # its canonical documentation path; no hop may expand the trust boundary.
        current_url = url
        for hop in range(3):
            async with client.stream('GET', current_url, follow_redirects=False, timeout=8) as response:
                if response.status_code in {301, 302, 303, 307, 308}:
                    location = response.headers.get('location')
                    if not location or hop == 2:
                        return None
                    target = urljoin(current_url, location)
                    if not allowed(target):
                        return None
                    current_url = target
                    continue
                if response.status_code != 200:
                    return None
                mime = response.headers.get('content-type', '').split(';', 1)[0].strip().lower()
                if mime and mime not in {'text/html', 'application/xhtml+xml'}:
                    return None
                chunks = bytearray()
                async for chunk in response.aiter_bytes():
                    chunks.extend(chunk)
                    if len(chunks) > MAX_BYTES:
                        return None
                html = chunks.decode(response.encoding or 'utf-8', errors='replace')
            return extract(html, fetched_at=datetime.now(timezone.utc).isoformat(), source_url=current_url)
        return None
    except (httpx.HTTPError, ValueError, LookupError):
        return None


def fixture_text(hit: SearchHit) -> str | None:
    fixtures = json.loads((FIXTURE_ROOT / 'documents.json').read_text())
    html = fixtures.get(hit.url)
    return extract(html, provenance='authored_fixture') if isinstance(html, str) else None


async def collect(hits: list[SearchHit], client: httpx.AsyncClient, mode: str) -> dict[str, str]:
    semaphore = asyncio.Semaphore(4)

    async def one(hit: SearchHit):
        if mode == 'recorded':
            return fixture_text(hit)
        async with semaphore:
            return await fetch_text(hit.url, client)

    candidates = [hit for hit in hits if allowed(hit.url)][:8]
    texts = await asyncio.gather(*(one(hit) for hit in candidates))
    return {hit.id: body for hit, body in zip(candidates, texts) if body}


def cite(url: str, quote: str, text: str, kind: str, *, section: str | None = None,
         provenance: str | None = None, fetched_at: str | None = None) -> Evidence | None:
    doc = document(text)
    if doc:
        if not any(quote in block.get('code', '') for block in doc['blocks']) and quote not in doc['text']:
            return None
        digest = doc['content_hash']
        provenance = provenance or doc['provenance']
        fetched_at = fetched_at or doc.get('fetched_at')
    else:
        if quote not in text:
            return None
        digest = hashlib.sha256(text.encode()).hexdigest()
    return Evidence(url=url, quote=quote, source_kind=kind, content_hash=digest,
                    section=section, provenance=provenance, fetched_at=fetched_at)

"""Bounded official-source retrieval and heading-scoped, inspectable code evidence."""

import asyncio
import hashlib
import json
import ipaddress
import socket
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote, urljoin, urlsplit, urlunsplit

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


def public_allowed(url: str) -> bool:
    """Syntax-level gate. DNS must additionally be checked and pinned at fetch time."""
    try:
        parsed = urlsplit(url)
        host = parsed.hostname or ''
        if (parsed.scheme != 'https' or parsed.port is not None or parsed.username is not None
                or parsed.password is not None or not host or len(url) > 4000
                or '%' in host or '\\' in url or re_control(url)
                or host.casefold() == 'localhost' or '.' not in host
                or host.casefold().endswith(('.localhost', '.local', '.internal', '.test', '.invalid', '.example'))):
            return False
        try:
            return ipaddress.ip_address(host).is_global
        except ValueError:
            return True
    except ValueError:
        return False


def re_control(value: str) -> bool:
    return any(ord(character) < 32 or ord(character) == 127 for character in value)


async def public_addresses(host: str) -> list[str]:
    """Reject a mixed public/private DNS answer, then connect to a validated IP."""
    try:
        answers = await asyncio.wait_for(
            asyncio.to_thread(socket.getaddrinfo, host, 443, type=socket.SOCK_STREAM), timeout=5)
        addresses = list(dict.fromkeys(answer[4][0] for answer in answers))
        if not addresses or not all(ipaddress.ip_address(address).is_global for address in addresses):
            return []
        return addresses
    except (OSError, ValueError, TimeoutError):
        return []


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
    passages: list[dict] = []
    heading_stack: dict[int, str] = {}
    heading_scopes: dict[int, int] = {}
    extraction_complete = True

    def flush() -> None:
        context = ' '.join(section_parts)[:8_000]
        for index in section_indices:
            blocks[index]['context'] = context

    # A pre includes its descendant code/spans; process it once, preserving whitespace.
    for node in root.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'p', 'li', 'pre']):
        if any(isinstance(parent, Tag) and parent.name == 'pre' for parent in node.parents):
            continue
        if node.name.startswith('h'):
            flush()
            scope_id += 1
            heading = node.get_text(' ', strip=True)[:300]
            level = int(node.name[1])
            heading_stack = {depth: value for depth, value in heading_stack.items() if depth < level}
            heading_stack[level] = heading
            heading_scopes = {depth: value for depth, value in heading_scopes.items() if depth < level}
            heading_scopes[level] = scope_id
            section_id = node.get('id')
            section_parts = []
            section_indices = []
        elif node.name in {'p', 'li'}:
            paragraph = node.get_text(' ', strip=True)
            section_parts.append(paragraph)
            if len(passages) < 300 and 0 < len(paragraph) <= 2000:
                passages.append({'heading': heading, 'section_id': section_id,
                                 'scope_id': scope_id, 'text': paragraph,
                                 'heading_context': ' / '.join(heading_stack.values()),
                                 'ancestor_scope_ids': list(heading_scopes.values())})
            elif paragraph:
                extraction_complete = False
        elif node.name == 'pre':
            code = node.get_text('', strip=False)
            if not code.strip() or len(code) > MAX_CODE:
                continue
            section_indices.append(len(blocks))
            blocks.append({'heading': heading, 'section_id': section_id,
                           'scope_id': scope_id, 'code': code, 'context': ''})
            if len(blocks) >= 100:
                extraction_complete = False
                break
    flush()
    return json.dumps({'format': FORMAT, 'text': root.get_text(' ', strip=True)[:MAX_TEXT],
                       'blocks': blocks, 'passages': passages,
                       'extraction_complete': extraction_complete,
                       'content_hash': hashlib.sha256(html.encode()).hexdigest(),
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


async def _fetch_text(url: str, client: httpx.AsyncClient, *, universal: bool = False) -> str | None:
    # Curated fixed documentation hosts retain the existing trust boundary.
    # Other public hosts use IP pinning rather than weakening the SSRF gate.
    universal = universal and not allowed(url)
    gate = public_allowed if universal else allowed
    if not gate(url):
        return None
    try:
        # Validate every hop ourselves. Pydantic's old docs host now redirects to
        # its canonical documentation path; no hop may expand the trust boundary.
        current_url = url
        for hop in range(3):
            if universal:
                parsed = urlsplit(current_url)
                addresses = await public_addresses(parsed.hostname)
                if not addresses:
                    return None
                address = addresses[0]
                authority = f'[{address}]' if ':' in address else address
                pinned_url = urlunsplit(('https', authority, parsed.path or '/', parsed.query, ''))
                # An explicit Request avoids inherited credentials/cookies. The
                # validated IP is the TCP destination; SNI retains TLS hostname
                # validation, closing the DNS-rebinding gap between checks and GET.
                request = httpx.Request('GET', pinned_url, headers={'Host': parsed.hostname,
                                         'Accept': 'text/html,application/xhtml+xml',
                                         'Connection': 'close',
                                         'User-Agent': 'VersionVerdict/0.3 evidence-fetcher'},
                                        extensions={'sni_hostname': parsed.hostname,
                                                    'timeout': {'connect': 8, 'read': 8, 'write': 8, 'pool': 8}})
                response = await client.send(request, stream=True, follow_redirects=False, auth=None)
            else:
                request = client.build_request('GET', current_url, timeout=8)
                response = await client.send(request, stream=True, follow_redirects=False, auth=None)
            try:
                if response.status_code in {301, 302, 303, 307, 308}:
                    location = response.headers.get('location')
                    if not location or hop == 2:
                        return None
                    target = urljoin(current_url, location)
                    if not gate(target):
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
            finally:
                await response.aclose()
            return extract(html, fetched_at=datetime.now(timezone.utc).isoformat(), source_url=current_url)
        return None
    except (httpx.HTTPError, ValueError, LookupError):
        return None


async def fetch_text(url: str, client: httpx.AsyncClient, *, universal: bool = False) -> str | None:
    """Bound the complete operation as well as each DNS/connect/read step."""
    try:
        return await asyncio.wait_for(_fetch_text(url, client, universal=universal), timeout=20)
    except TimeoutError:
        return None


def fixture_text(hit: SearchHit) -> str | None:
    fixtures = json.loads((FIXTURE_ROOT / 'documents.json').read_text())
    html = fixtures.get(hit.url)
    return extract(html, provenance='authored_fixture') if isinstance(html, str) else None


async def collect(hits: list[SearchHit], client: httpx.AsyncClient, mode: str,
                  *, universal: bool = False) -> dict[str, str]:
    semaphore = asyncio.Semaphore(4)

    async def one(hit: SearchHit):
        if mode == 'recorded':
            return fixture_text(hit)
        async with semaphore:
            return await fetch_text(hit.url, client, universal=universal)

    gate = public_allowed if universal else allowed
    candidates = [hit for hit in hits if gate(hit.url)][:8]
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

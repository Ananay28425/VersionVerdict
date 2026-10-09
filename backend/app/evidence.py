import asyncio
import hashlib
import ipaddress
import json
import socket
from pathlib import Path
from urllib.parse import urlsplit

import httpx
from bs4 import BeautifulSoup

from .models import Evidence, SearchHit

ALLOWED = {'docs.pydantic.dev', 'docs.sqlalchemy.org'}
FIXTURE_ROOT = Path(__file__).resolve().parents[2] / 'fixtures' / 'evidence'


def allowed(url: str) -> bool:
    u = urlsplit(url)
    return (
        u.scheme == 'https' and u.hostname in ALLOWED and not u.port and not u.username
    )


def extract(html: str) -> str:
    soup = BeautifulSoup(html, 'html.parser')
    for node in soup(['script', 'style', 'nav', 'footer', 'header']):
        node.decompose()
    root = soup.find('main') or soup.find('article') or soup
    return root.get_text(' ', strip=True)[:100000]


async def fetch_text(url: str, client: httpx.AsyncClient) -> str | None:
    if not allowed(url):
        return None
    try:
        # Disable redirects. Redirect targets must never bypass the host allowlist.
        response = await client.get(url, follow_redirects=False, timeout=8)
        if response.status_code != 200 or len(response.content) > 2_000_000:
            return None
        return extract(response.text)
    except (httpx.HTTPError, ValueError):
        return None


def fixture_text(hit: SearchHit) -> str | None:
    fixtures = json.loads((FIXTURE_ROOT / 'documents.json').read_text())
    return fixtures.get(hit.url)


async def collect(
    hits: list[SearchHit], client: httpx.AsyncClient, mode: str
) -> dict[str, str]:
    semaphore = asyncio.Semaphore(4)

    async def one(hit: SearchHit):
        if mode == 'recorded':
            return fixture_text(hit)
        async with semaphore:
            return await fetch_text(hit.url, client)

    texts = await asyncio.gather(*(one(h) for h in hits[:8]))
    return {h.id: t for h, t in zip(hits[:8], texts) if t}


def cite(url: str, quote: str, text: str, kind: str) -> Evidence | None:
    if quote not in text:
        return None
    return Evidence(
        url=url,
        quote=quote,
        source_kind=kind,
        content_hash=hashlib.sha256(text.encode()).hexdigest(),
    )

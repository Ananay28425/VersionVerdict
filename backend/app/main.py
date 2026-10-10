"""HTTP boundary for safe manifests, shared retrieval, and conservative verdicts."""

import hashlib
import json
import os
import sqlite3
from pathlib import Path

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse

from .applicability import RULESET_VERSION, classify_all, rank
from .evidence import FIXTURE_ROOT, allowed, public_allowed, collect
from .generic_applicability import GENERIC_RULESET_VERSION, classify_generic, rank_generic
from .models import ProfileResult, SearchReceipt, SearchResponse
from .planner import plan
from .profiler import MAX_FILE_BYTES, SUPPORTED_FILES, parse_profile
from .retrieval import SearchError, normalize, search_batch
from .search_store import SearchStore

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / '.env', override=False)
app = FastAPI(title='VersionVerdict', version='0.2.0')
app.add_middleware(
    CORSMiddleware,
    allow_origins=['http://localhost:5173', 'http://127.0.0.1:5173'],
    allow_methods=['GET', 'POST'],
    allow_headers=['*'],
)


def _budget_store() -> SearchStore:
    try:
        return SearchStore()
    except (OSError, ValueError, sqlite3.Error) as exc:
        raise HTTPException(503, 'Search allocation storage is unavailable.') from exc


def _future_mode(value: str) -> bool | None:
    if value not in {'unknown', 'true', 'false'}:
        raise ValueError('SQLAlchemy future mode must be unknown, true, or false.')
    return None if value == 'unknown' else value == 'true'


async def _manifest_files(
    primary: UploadFile, extra: UploadFile | None
) -> list[tuple[str, bytes]]:
    files = [(primary.filename or '', await primary.read(MAX_FILE_BYTES + 1))]
    if extra is not None:
        files.append((extra.filename or '', await extra.read(MAX_FILE_BYTES + 1)))
    return files


@app.get('/api/health')
def health():
    return {'status': 'ok', 'live_search_configured': bool(os.getenv('SERPAPI_KEY'))}


@app.get('/api/capabilities')
def capabilities():
    try:
        budget = _budget_store().budget()
    except sqlite3.Error as exc:
        raise HTTPException(503, 'Search allocation storage is unavailable.') from exc
    return {
        'engines': [
            {'id': 'google', 'name': 'SerpApi Google Search', 'optional': False},
            {'id': 'bing', 'name': 'SerpApi Bing Search', 'optional': True},
        ],
        'budget': {
            'limit': budget['budget_limit'],
            'used': budget['budget_used'],
            'remaining': budget['budget_remaining'],
            'scope': 'Application allocation; not the shared SerpApi account balance.',
        },
        'live_search_configured': bool(os.getenv('SERPAPI_KEY')),
        'supported_libraries': [],
        'reviewed_libraries': ['pydantic', 'sqlalchemy'],
        'universal_search': True,
        'supported_manifests': sorted(SUPPORTED_FILES),
        'max_manifest_bytes': MAX_FILE_BYTES,
        'default_search_calls': 2,
        'secondary_search_calls': 1,
        'cache_ttl_seconds': 86_400,
        'version_source': 'Declared dependencies; installed versions are not inferred.',
        'generic_verdict_scope': 'Explicit query-specific named source version conditions; runtime/hardware/OS/ABI correctness is not inferred.',
    }


def _artifact(directory: str, filename: str) -> dict:
    path = ROOT / 'fixtures' / directory / filename
    if not path.is_file():
        raise HTTPException(404, 'Verification artifact has not been generated.')
    try:
        return json.loads(path.read_text())
    except (ValueError, OSError) as exc:
        raise HTTPException(503, 'Verification artifact cannot be read.') from exc


@app.get('/api/witnesses')
def witnesses():
    return _artifact('witnesses', 'report.json')


@app.get('/api/evaluation')
def evaluation():
    return _artifact('evaluation', 'report.json')


@app.post('/api/search', response_model=SearchResponse)
async def search(
    query: str = Form(...),
    library: str = Form(...),
    mode: str = Form('live'),
    left_name: str = Form('Project A', min_length=1, max_length=80),
    right_name: str = Form('Project B', min_length=1, max_length=80),
    left_file: UploadFile = File(...),
    left_extra_file: UploadFile | None = File(None),
    right_file: UploadFile | None = File(None),
    right_extra_file: UploadFile | None = File(None),
    left_sqlalchemy_future: str | None = Form(None),
    right_sqlalchemy_future: str | None = Form(None),
    left_pydantic_api_mode: str | None = Form(None),
    right_pydantic_api_mode: str | None = Form(None),
    include_secondary: bool = Form(False),
    refresh: bool = Form(False),
    # Retain old fields while callers migrate to independent profile contexts.
    sqlalchemy_future: str = Form('unknown'),
    pydantic_api_mode: str = Form('unknown'),
):
    query = ' '.join(query.split())
    if not 3 <= len(query) <= 240:
        raise HTTPException(422, 'Query must contain 3 to 240 characters.')
    if mode not in {'live', 'recorded'}:
        raise HTTPException(422, 'Mode must be live or recorded.')
    library = ' '.join(library.split()).strip()
    if not 1 <= len(library) <= 80 or any(ord(char) < 32 or ord(char) == 127 for char in library):
        raise HTTPException(422, 'Technology must contain 1 to 80 printable characters.')
    if library.casefold() in {'pydantic', 'sqlalchemy'}:
        library = library.casefold()
    reviewed = library in {'pydantic', 'sqlalchemy'}
    if mode == 'recorded' and not reviewed:
        raise HTTPException(422, 'Illustrative fixtures are only available for Pydantic and SQLAlchemy. Other targets use live search.')
    try:
        left = parse_profile(
            left_name,
            await _manifest_files(left_file, left_extra_file),
            sqlalchemy_future=_future_mode(left_sqlalchemy_future or sqlalchemy_future),
            pydantic_api_mode=left_pydantic_api_mode or pydantic_api_mode,
        )
        profiles = [left]
        if right_file is not None:
            profiles.append(
                parse_profile(
                    right_name,
                    await _manifest_files(right_file, right_extra_file),
                    sqlalchemy_future=_future_mode(
                        right_sqlalchemy_future or sqlalchemy_future
                    ),
                    pydantic_api_mode=right_pydantic_api_mode or pydantic_api_mode,
                )
            )
        elif right_extra_file is not None:
            raise ValueError('Version B needs its primary dependency file.')
        query_plan = plan(query, library, include_secondary=include_secondary, profiles=profiles)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc

    store = _budget_store()
    receipt = SearchReceipt(**store.budget())
    queries = [spec.query for spec in query_plan]
    response_mode = mode
    # Generic evidence connects to validated IPs with original-host TLS SNI.
    # HTTP/1.1 plus Connection: close prevents TLS-pool reuse across CDN hosts.
    async with httpx.AsyncClient(http2=False) as client:
        if mode == 'live':
            key = os.getenv('SERPAPI_KEY')
            if not key:
                raise HTTPException(
                    503, 'Live SerpApi search needs SERPAPI_KEY on the backend.'
                )
            try:
                batch = await search_batch(
                    query_plan, key, client, refresh=refresh, store=store
                )
            except SearchError as exc:
                return JSONResponse(
                    status_code=getattr(exc, 'status_code', 502),
                    content={'detail': str(exc), 'receipt': getattr(exc, 'receipt', {})},
                )
            hits, warnings = batch.hits, batch.warnings
            receipt = SearchReceipt(**batch.receipt)
            response_mode = (
                'cached' if receipt.api_calls == 0 else 'mixed' if receipt.cache_hits else 'live'
            )
        else:
            expected = {
                'pydantic': 'validate a dictionary into a Pydantic model',
                'sqlalchemy': 'execute a SQL statement with SQLAlchemy',
            }[library]
            if query.casefold() != expected.casefold():
                raise HTTPException(422, f'Illustrative demo only supports: {expected}')
            data = json.loads((FIXTURE_ROOT / f'{library}_search.json').read_text())
            hits = normalize(data['responses'], queries[: len(data['responses'])])
            for hit in hits:
                for provenance in hit.provenance:
                    provenance.retrieval = 'illustrative'
            receipt.engines = ['google']
            warnings = [
                'Illustrative sources and search-shaped data; no live SerpApi search was made.'
            ]
            if include_secondary:
                warnings.append(
                    'Bing is available in live mode; this demo contains Google-shaped fixtures only.'
                )
            queries = queries[: len(data['responses'])]
        texts = await collect(hits, client, mode, universal=not reviewed)

    if mode == 'live':
        source_gate = allowed if reviewed else public_allowed
        eligible = sum(source_gate(hit.url) for hit in hits)
        if eligible > len(texts):
            warnings.append(
                'Some documentation could not be fetched or exceeded the bounded fetch limit. '
                'Unverified sources remain UNCERTAIN.'
            )
        if not eligible:
            warnings.append(
                'No safely fetchable source-content evidence is available for these candidates.'
            )
    facts = json.loads((FIXTURE_ROOT / 'facts.json').read_text())
    results = [
        ProfileResult(
            profile=profile,
            cards=(rank if reviewed else lambda values: rank_generic(values, library, query))([
                card
                for hit in hits
                for card in (classify_all(hit, texts.get(hit.id), profile, library, facts)
                             if reviewed else [classify_generic(hit, texts.get(hit.id), profile, library, query)])
            ]),
        )
        for profile in profiles
    ]
    pool_id = hashlib.sha256(
        json.dumps(sorted(hit.id for hit in hits), separators=(',', ':')).encode()
    ).hexdigest()[:16]
    return SearchResponse(
        mode=response_mode,
        queries=queries,
        candidate_count=len(hits),
        results=results,
        warnings=warnings,
        receipt=receipt,
        pool_id=pool_id,
        rule_version=RULESET_VERSION if reviewed else GENERIC_RULESET_VERSION,
    )


@app.get('/{path:path}', include_in_schema=False)
def frontend(path: str):
    if path.startswith('api/'):
        raise HTTPException(404, 'Unknown API endpoint.')
    dist = ROOT / 'frontend' / 'dist'
    requested = (dist / path).resolve()
    if dist.exists() and requested.is_relative_to(dist.resolve()) and requested.is_file():
        headers = {'Cache-Control': 'no-cache'} if requested.name == 'index.html' else {}
        return FileResponse(requested, headers=headers)
    if path.startswith('assets/') or path.rsplit('/', 1)[-1].count('.'):
        raise HTTPException(404, 'Frontend asset not found. Rebuild the frontend and reload.')
    if (dist / 'index.html').exists():
        return FileResponse(dist / 'index.html', headers={'Cache-Control': 'no-cache'})
    raise HTTPException(404, 'Frontend is not built. Run npm --prefix frontend run build from the repository root.')

import json
import os
from pathlib import Path

import httpx
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from .applicability import classify, rank
from .evidence import FIXTURE_ROOT, collect
from .models import ProfileResult, SearchResponse
from .planner import plan
from .profiler import parse_profile
from .retrieval import SearchError, normalize, search_live

ROOT = Path(__file__).resolve().parents[2]
app = FastAPI(title='VersionVerdict', version='0.1.0')
app.add_middleware(
    CORSMiddleware,
    allow_origins=['http://localhost:5173', 'http://127.0.0.1:5173'],
    allow_methods=['GET', 'POST'],
    allow_headers=['*'],
)


@app.get('/api/health')
def health():
    return {'status': 'ok', 'live_search_configured': bool(os.getenv('SERPAPI_KEY'))}


@app.post('/api/search', response_model=SearchResponse)
async def search(
    query: str = Form(...),
    library: str = Form(...),
    mode: str = Form('live'),
    left_name: str = Form('Project A'),
    right_name: str = Form('Project B'),
    left_file: UploadFile = File(...),
    left_extra_file: UploadFile | None = File(None),
    right_file: UploadFile | None = File(None),
    right_extra_file: UploadFile | None = File(None),
    sqlalchemy_future: str = Form('unknown'),
    pydantic_api_mode: str = Form('unknown'),
):
    if not 3 <= len(query.strip()) <= 240:
        raise HTTPException(422, 'Query must contain 3 to 240 characters')
    if mode not in {'live', 'recorded'}:
        raise HTTPException(422, 'Mode must be live or recorded')
    if sqlalchemy_future not in {'unknown', 'true', 'false'}:
        raise HTTPException(422, 'Invalid SQLAlchemy mode')
    future = None if sqlalchemy_future == 'unknown' else sqlalchemy_future == 'true'
    try:
        queries = plan(query, library)
        left_files = [(left_file.filename or '', await left_file.read(256 * 1024 + 1))]
        if left_extra_file:
            left_files.append(
                (
                    left_extra_file.filename or '',
                    await left_extra_file.read(256 * 1024 + 1),
                )
            )
        left = parse_profile(
            left_name,
            left_files,
            sqlalchemy_future=future,
            pydantic_api_mode=pydantic_api_mode,
        )
        profiles = [left]
        if right_file:
            right_files = [
                (right_file.filename or '', await right_file.read(256 * 1024 + 1))
            ]
            if right_extra_file:
                right_files.append(
                    (
                        right_extra_file.filename or '',
                        await right_extra_file.read(256 * 1024 + 1),
                    )
                )
            profiles.append(
                parse_profile(
                    right_name,
                    right_files,
                    sqlalchemy_future=future,
                    pydantic_api_mode=pydantic_api_mode,
                )
            )
        elif right_extra_file:
            raise ValueError('Version B needs its primary dependency file')
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    async with httpx.AsyncClient() as client:
        if mode == 'live':
            key = os.getenv('SERPAPI_KEY')
            if not key:
                raise HTTPException(
                    503, 'Live SerpApi search needs SERPAPI_KEY on the backend'
                )
            try:
                hits, warnings = await search_live(queries, key, client)
            except SearchError as exc:
                raise HTTPException(502, str(exc)) from exc
        else:
            expected = {
                'pydantic': 'validate a dictionary into a Pydantic model',
                'sqlalchemy': 'execute a SQL statement with SQLAlchemy',
            }[library]
            if query.strip().casefold() != expected.casefold():
                raise HTTPException(
                    422, f'Illustrative fixture only supports: {expected}'
                )
            data = json.loads((FIXTURE_ROOT / f'{library}_search.json').read_text())
            hits = normalize(data['responses'], queries[: len(data['responses'])])
            warnings = [
                'Illustrative search data assembled from official documentation; no live SerpApi request was made.'
            ]
        texts = await collect(hits, client, mode)
    facts = json.loads((FIXTURE_ROOT / 'facts.json').read_text())
    result = [
        ProfileResult(
            profile=p,
            cards=rank([classify(h, texts.get(h.id), p, library, facts) for h in hits]),
        )
        for p in profiles
    ]
    return SearchResponse(
        mode=mode,
        queries=queries,
        candidate_count=len(hits),
        results=result,
        warnings=warnings,
    )


@app.get('/{path:path}', include_in_schema=False)
def frontend(path: str):
    dist = ROOT / 'frontend' / 'dist'
    requested = (dist / path).resolve()
    if (
        dist.exists()
        and requested.is_relative_to(dist.resolve())
        and requested.is_file()
    ):
        return FileResponse(requested)
    if (dist / 'index.html').exists():
        return FileResponse(dist / 'index.html')
    raise HTTPException(404, 'Frontend is not built. Run npm run dev in frontend.')

# VersionVerdict

**The right answer for your version.** Upload a Python dependency manifest and search for a solution. VersionVerdict ranks retrieved recipes against declared dependency versions. Every definitive label includes a fetched recipe quote and a pinned official migration fact.

## Scope

- `requirements.txt` and PEP 621 `pyproject.toml`; simple Poetry declarations.
- Pydantic 1.10 and 2.0–2.14 dictionary validation recipes: `parse_obj()` and `model_validate()`.
- SQLAlchemy 1.4 and 2.0 execution recipes: `Engine.execute()` and `Connection.execute()`.
- Four labels: COMPATIBLE, WRONG_VERSION, STALE, UNCERTAIN.
- A version range, conflicting dependency, unsupported syntax, unclear API namespace, missing page, or missing fact produces UNCERTAIN. The tool reads declarations; it does not claim to inspect installed packages.

## Start locally

Requires Python 3.12+ and Node 22+. From repository root:

```sh
python3.12 -m venv .venv
.venv/bin/python -m pip install -r backend/requirements-lock.txt
npm --prefix frontend ci
PYTHONPATH=backend .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000
```

For frontend development, run `npm --prefix frontend run dev` in another terminal, then open `http://localhost:5173`. For one-service mode, run `npm --prefix frontend run build` and open `http://localhost:8000`.

For live search, set `SERPAPI_KEY` only in the backend environment before starting it. The backend sends async Google Search requests to `https://serpapi.com/search.json`. The key is never sent to the browser. The deployment also needs HTTPS egress to `serpapi.com`, `docs.pydantic.dev`, and `docs.sqlalchemy.org`. First-party documentation is the only source eligible for definitive recipe evidence. External search hits remain UNCERTAIN. A source fetch or rule failure never silently falls back to a snippet-based verdict.

## Run checks

```sh
PYTHONPATH=backend .venv/bin/python -m pytest backend/tests -q
npm --prefix frontend run build
```

The live test in `backend/tests/test_live.py` skips when `SERPAPI_KEY` is absent. Run it after setting the key and enabling network access:

```sh
PYTHONPATH=backend .venv/bin/python -m pytest backend/tests/test_live.py -q
```

An integration test can fail if account quota or egress blocks SerpApi; report that separately from local tests.

## Three-minute demo

1. Open app. Click **Load comparison demo**. Banner says **Illustrative fixture**. Search Pydantic query already filled in.
2. Show identical candidates. V1 ranks `parse_obj()` COMPATIBLE first. V2 ranks `model_validate()` COMPATIBLE first; old method is STALE.
3. Expand both cards. Show recipe quote and official migration fact. Explain that missing source evidence would produce UNCERTAIN.
4. Switch library to SQLAlchemy and load demo. `Engine.execute()` moves from STALE for 1.4 legacy mode to WRONG_VERSION for 2.0.
5. Switch to **Live · SerpApi** when key and egress work. Run search. Point to LIVE SEARCH banner and search queries. Never present illustrative fixtures as captured SerpApi responses.
6. Show test and build commands, repository, and deployment URL.

The JSON search fixtures are illustrative data shaped like organic results, assembled from official documentation. They were not captured from live SerpApi. `fixtures/evidence/facts.json` contains short quotes from pinned official Pydantic and SQLAlchemy migration sources. The main interface uses the same classifier for live and fixture modes. The live path fetches page text from allowlisted official documentation; if unavailable, verdict is UNCERTAIN.

## API

`POST /api/search` accepts multipart fields: `query`, `library` (`pydantic` or `sqlalchemy`), `mode` (`live` or `recorded`), `left_file`, optional `left_extra_file`, optional `right_file`, optional `right_extra_file`, optional `sqlalchemy_future` (`true`, `false`, `unknown`), and `pydantic_api_mode` (`native`, `v1_shim`, `unknown`). Runtime context defaults to unknown. Files must be named `requirements.txt` or `pyproject.toml`; limit is two files and 256 KiB per profile. Recorded mode accepts only the documented demo query for each library. `GET /api/health` reports key presence without revealing its value. OpenAPI is at `/docs`.

## Evidence and ranking

Google organic hits are normalized by HTTPS URL and deduplicated. Only official documentation hosts are fetched, with redirects disabled and timeouts. Classifier recognizes a narrow set of named recipes. It requires the recipe text in fetched source content and a verified migration quote. It evaluates declared exact version and SQLAlchemy future mode. Results sort by category, evidence presence, original search position, then stable ID. Search relevance never increases factual certainty. The rule set is intentionally narrow; unrelated results remain visible as UNCERTAIN.

## Deploy

Build `Dockerfile` as a single service. Set backend `SERPAPI_KEY` as a secret and expose the platform's `PORT`. Keep one worker. Deploying without a key allows illustrative mode; live mode returns an explicit 503. Confirm `/api/health`, then run a live Pydantic search before publishing a live integration claim. Ensure production egress permits SerpApi and official documentation.

## Hackathon fit and limitations

Version-specific reranking supplies the idea and useful developer workflow. SerpApi supplies live discovery. Manifest parsing, source extraction, migration rules, and conservative abstention supply technical depth. Support covers only two libraries and four API patterns. Search results and official documentation can change. The app does not analyze arbitrary repository source, resolve dependency ranges, or validate every external solution. Review current hackathon submission and eligibility rules at the official site before submission; direct site access was blocked during development.

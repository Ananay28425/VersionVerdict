# Evaluation record — October 9, 2026

## Local results

- `PYTHONPATH=backend .venv/bin/python -m pytest backend/tests -q`: 11 passed, 1 skipped. Skipped test is explicit live SerpApi test; `SERPAPI_KEY` was absent.
- `npm --prefix frontend run build`: TypeScript check and Vite production build passed.
- Production-mode Uvicorn smoke: root HTML, demo fixture, and health endpoint returned 200. Pydantic and SQLAlchemy comparison endpoints returned 200.
- Pydantic fixture: exact same candidate IDs for both profiles. V1 top `parse_obj()` COMPATIBLE; V2 top `model_validate()` COMPATIBLE. The non-top recipe is WRONG_VERSION for V1 and STALE for V2, respectively.
- SQLAlchemy fixture: `Engine.execute()` STALE for 1.4 legacy mode; WRONG_VERSION for 2.0. `Connection.execute()` COMPATIBLE for both in verified fixture scope.
- Removing fetched recipe text or migration fact yields UNCERTAIN.
- Unknown Pydantic API namespace yields UNCERTAIN.
- Isolated Python 3.12 package checks: Pydantic 1.10.15 `parse_obj()` works and `model_validate()` is absent; Pydantic 2.9.2 `model_validate()` works and `parse_obj()` emits a deprecation warning. SQLAlchemy 1.4.54 `Engine.execute()` works in legacy mode with RemovedIn20Warning and fails in future mode; SQLAlchemy 2.0.36 has no `Engine.execute()`, while `Connection.execute(text(...))` works.

## Limits

Search JSON fixtures are illustrative, not captured SerpApi output. Direct HTTPS to SerpApi and documentation hosts was blocked by the current cloud proxy. The live test remains unrun. Docker build was attempted; package installation inside Docker could not resolve the cloud proxy hostname. Local source build and server smoke passed. This fixture set verifies specific rules, not general precision. No deployed URL or hackathon submission is claimed.

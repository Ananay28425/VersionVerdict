# Single-service deployment

FastAPI serves both `/api/*` and the built React frontend. The application does not require Redis, a queue, a separate frontend host, or user accounts.

## Local production smoke

From the repository root, with dependencies installed:

```bash
npm --prefix frontend run build
PYTHONPATH=backend .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1
```

Check the homepage, `/api/health`, `/docs`, and both illustrative comparison presets. For live verification, set `SERPAPI_KEY` on the backend before starting the service and inspect the response's actual retrieval provenance.

## Container

```bash
docker build -t versionverdict .
docker run --rm -p 8000:8000 \
  --env-file .env \
  -v versionverdict-cache:/app/.cache/versionverdict \
  versionverdict
```

Unlike the application itself, Docker's `--env-file` option loads the named file. The repository's `.env.example` is a template; copy it to `.env` and populate its backend key privately before using the command.

The image runs one Uvicorn worker and supports the platform's `PORT` variable. The default cache directory is `.cache/versionverdict` under the repository root; the volume above matches the image's `/app` layout.

## Hosted service

Use a host that supports one Docker service with a persistent disk. Configure:

- `SERPAPI_KEY`: secret environment variable.
- `SERPAPI_REQUEST_BUDGET=50`: an application request-attempt allocation; not the account's remaining search balance.
- `VERSIONVERDICT_CACHE_DIR`: a directory on the mounted disk, if different from the default.
- Outbound HTTPS to `serpapi.com`, `docs.pydantic.dev`, `pydantic.dev`, and `docs.sqlalchemy.org`.
- HTTPS ingress and a health check on `/api/health`.

Keep the SQLite cache and request ledger across redeployments. Deleting that directory resets the local ledger, not the SerpApi account's usage. Multiple independent deployments have independent ledgers; their combined usage still counts against a shared account.

This service has no authentication. An internet-facing deployment lets visitors spend its configured local allocation. Keep that allocation small and retain the ledger. Increasing the allocation should be a deliberate account-owner decision, informed by the account dashboard.

## Publication checklist

1. Backend tests and frontend build pass on the final revision.
2. Trusted version-witness and curated evaluation reports identify their exact tested inputs.
3. The key is present only on the server; no frontend bundle or repository file contains it.
4. A real Google search succeeds. Exercise optional Bing explicitly before claiming live Bing usage.
5. Live, cached, and illustrative states are visible and accurate.
6. Both environment comparisons work on the hosted URL.
7. Confirm the actual event eligibility and submission requirements; the code and this deployment guide do not establish prize eligibility.

The Docker build must be verified on the selected host. Earlier cloud attempts encountered package-download proxy failures; a Dockerfile's presence is not evidence that deployment succeeded.

# Single-service deployment

FastAPI serves both `/api/*` and the built React frontend. The application does not require Redis, a queue, a separate frontend host, or user accounts.

## Local production smoke

From the repository root, with dependencies installed:

```bash
./scripts/start_preview.sh
```

The script rebuilds and serves the terminal interface and API on `0.0.0.0:3000` by default. It supports `PORT`, uses one Uvicorn worker, and makes no search request during startup. Check the homepage, `/api/health`, `/docs`, and both illustrative comparison presets. For live verification, set `SERPAPI_KEY` on the backend before starting the service and inspect the response's actual retrieval provenance.

Binding to all interfaces enables a host to forward the service port; it does not publish a public URL. The cloud environment onboarding interface itself does not support embedded web previews. A separate frontend server is unnecessary for a production preview. For Vite development, the backend must run on port 3000 to match the configured API proxy.

## Container

```bash
docker build -t versionverdict .
docker run --rm -p 8000:8000 \
  --env-file .env \
  -v versionverdict-cache:/app/.cache/versionverdict \
  versionverdict
```

Docker's `--env-file` passes the named file into the container as process variables. The repository's `.env.example` is a template; copy it to `.env` and populate its backend key privately before using the command. The backend also loads a root `.env` file for local runs, with process variables taking precedence.

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

# Verification record — October 10, 2026 (IST)

## Scope and reproduction

The evaluation and version witnesses are separate checks. Neither makes a live SerpApi request.

```bash
PYTHONPATH=backend .venv/bin/python -m pytest backend/tests -q
npm --prefix frontend run build
.venv/bin/python scripts/verify_versions.py --output fixtures/witnesses/report.json
PYTHONPATH=backend .venv/bin/python scripts/evaluate.py --output fixtures/evaluation/report.json
```

The version runner prepares four isolated pinned environments. On subsequent runs, `--no-install` reuses those environments without package downloads. Reports record their actual commands, inputs, hashes, observations, and timestamps. Regenerate them after changing recipes or rules.

## Actual package behavior

[Version-witness report](../fixtures/witnesses/report.json): **12 passed, 0 failed, 0 unverified**, executed with Python **3.12.14**.

| Environment | Demonstrated boundary |
|---|---|
| Pydantic 1.10.15 | Native `parse_obj()` succeeds; `model_validate()` is absent. |
| Pydantic 2.9.2 | Native `model_validate()` succeeds; native `parse_obj()` warns; the explicit V1 shim retains its legacy API. |
| SQLAlchemy 1.4.54 | Legacy `Engine.execute()` warns; future mode rejects it; supported connection execution works. |
| SQLAlchemy 2.0.36 | `Engine.execute()` is absent; `Connection.execute(text("SELECT 1"))` succeeds in a managed transaction. |

The full report includes each case and its expected and observed behavior. Witnesses use repository-authored snippets and an in-memory SQLite database. No uploaded repository code or retrieved recipe was executed. Passing these cases does not validate arbitrary web answers, other releases, operating systems, database drivers, or a user's application.

## Curated applicability evaluation

[Cases](../fixtures/evaluation/cases.json) · [Measured report](../fixtures/evaluation/report.json)

The suite has **30 curated source scenarios and 31 expected labels**; one mixed-document scenario contains two recipes. HTML inputs are deliberately authored evaluation fixtures, not captures of pages at their cited documentation-family URLs.

| Measure | Actual result | Denominator |
|---|---|---|
| Exact scenario match | 30 / 30 | Scenarios with exactly the expected ordered labels |
| Label match | 31 / 31 | Expected recipe labels |
| Definitive-label precision | 14 / 14 | Predicted `COMPATIBLE`, `STALE`, or `WRONG_VERSION` labels |
| Definitive coverage | 14 / 31 | All evaluated recipe labels |
| Uncertainty rate | 17 / 31 | All evaluated recipe labels |

Expected label distribution: **7 compatible, 3 stale, 4 wrong-version, 17 uncertain**.

Cases cover native and shim namespaces, migration boundaries, future mode, nonliteral/raw SQL, missing transactions for writes, mixed recipes, unknown versions, unsupported releases, and missing evidence. A high match rate on these curated examples is a regression result, **not production accuracy or general search precision**.

## Application checks

Final local checks: **134 backend tests passed; 2 explicitly opt-in live tests skipped** because no SerpApi key was configured. **TypeScript checks and the Vite production build passed**. **18 browser checks passed**, covering the terminal layout, actual manifest previews, both illustrative demos, source evidence, recipe pairing, clipboard, witnesses, keyboard shortcuts, mobile layouts, and mocked failures. Startup checks deliberately block the JavaScript bundle and disable JavaScript to confirm readable fallback instructions. API outage recovery is mocked explicitly. No unexpected browser errors occurred in the functional demo checks. See [browser verification](browser-verification.json) and [screenshots](screenshots/desktop.png). The GitHub workflow repeats backend/frontend checks without spending the shared search allowance.

The combined service responds on port 3000 through both loopback and the container's network interface. The entry page uses `Cache-Control: no-cache`; missing asset paths return 404 rather than HTML. This verifies runtime readiness, not an embedded preview or public deployment.

The application comparison must preserve the shared hit pool. One source can expose multiple recipe cards, so recipe-card count may exceed source count. Source quotes must support the exact recipe and version claim; a working URL alone is insufficient evidence.

## Live verification and unmeasured claims

Run the explicitly identified live integration test only with a configured backend key and network access:

```bash
RUN_LIVE_SERPAPI=1 PYTHONPATH=backend .venv/bin/python -m pytest backend/tests/test_live.py -q
```

The unauthenticated SerpApi endpoint was reachable and returned HTTP401. Successful live Google and Bing end-to-end retrieval has not been verified because `SERPAPI_KEY` is absent. Pydantic documentation now redirects to `pydantic.dev/docs/validation/`; trusted redirect handling is tested, but the new host requires applying the saved cloud network allowance. SQLAlchemy documentation fetching succeeded in the source smoke check. The available fixtures do not establish live integration, search quality, latency, or API reliability. No live success rate, real-world compatible-source precision, general ranking lift, or deployed uptime is claimed.

The bundled search JSON and documentation HTML are illustrative fixtures. They are not SerpApi captures or actual fetched-page snapshots. Pinned official migration snapshots are a different artifact and retain their reviewed-source provenance.

Earlier Docker build attempts encountered package-download proxy failures. A successful local source build does not establish a successful container deployment.

## Next live evaluation

After real integration works, save redacted genuine responses and evaluate the broad-query result order against the same candidate subset. Candidates discovered only by targeted or Bing queries need a separate merged-retrieval assessment; they have no original broad-query position.

Measure citation support, definitive-label precision, coverage, wrong-version presence in the top three, latency, and actual attempts. Publish the labeled inputs and denominators alongside results. Keep live, cached, and illustrative records distinguishable.

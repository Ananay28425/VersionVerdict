# Recording and teammate runbook

The demo compares the same retrieved candidates under two declared environments, then shows the general stack workflow and an exportable investigation receipt.

## Prepare once

1. Follow the root README setup and run `./scripts/start_preview.sh` on port 3000. The same process serves the terminal interface and API.
2. Run backend tests, the frontend build, `scripts/verify_versions.py`, and `scripts/evaluate.py`. Inspect the reports before citing their results.
3. For a live recording, configure the backend key and run one Pydantic and one SQLAlchemy search. Keep the cache directory for the recording. Ordinary repeated searches reuse cached responses; refreshing spends additional requests.
4. Confirm each result shows its actual provenance. Bundled illustrative data must remain labelled illustrative. A cached live result must remain labelled cached.
5. Record at a readable browser size. Keep the dependency declarations, verdict change, and supporting source visible; avoid a tour of every control.

## Three-minute script

| Time | Screen and narration |
|---|---|
| 0:00–0:20 | Open VersionVerdict. “A valid answer for one dependency version can be wrong for another. VersionVerdict compares source evidence with declared environments, from firmware to frameworks.” Show the persisted color selector briefly. |
| 0:20–0:55 | Load the Pydantic comparison. Show `pydantic==1.10.15` and `pydantic==2.9.2`, with native APIs selected. Submit the same question. State whether this run is live, cached, or illustrative. |
| 0:55–1:30 | Show the shared candidate set: `parse_obj()` applies to V1 but is deprecated in V2; `model_validate()` applies to V2 and is absent from V1. Open recipe and migration evidence. Explain the boundary rather than just reading a badge. |
| 1:30–1:55 | Load SQLAlchemy 1.4.54 versus 2.0.36. Show why `Engine.execute()` is legacy in 1.4 and removed in 2.0. Inspect `Connection.execute(text(...))` evidence. |
| 1:55–2:20 | Open a committed version witness. Show package versions, the authored snippet, and its actual output or warning. Export the investigation as Markdown for a review or issue. |
| 2:20–2:45 | Enter a Rust or firmware stack using manual context, or upload `fixtures/profiles/firmware/environment.json`. Explain that explicit source requirements can be evaluated; missing hardware, API, or version evidence stays uncertain. Show request-budget and cache indicators. |
| 2:45–3:00 | Show repository and setup commands. “SerpApi supplies live technical discovery. VersionVerdict adds dependency profiling, evidence rules, and inspectable version-specific comparisons.” |

Do not edit a failed live attempt into a successful claim. Use a labelled illustrative run if credentials or the network fail; disclose that limitation in the video and submission.

## Submission inventory

- **Primary engine:** SerpApi Google Search API, `engine=google`.
- **Optional engine:** SerpApi Bing Search API, `engine=bing`, enabled by the user for supplementary discovery.
- **Transport:** asynchronous HTTPX requests to `https://serpapi.com/search.json`; the official Python SDK and agent Search Tools are not dependencies.
- **Source:** <https://github.com/Ananay28425/VersionVerdict>.
- **Deployment and video:** add the actual publicly accessible URLs after publication; none are implied by this document.
- **AI assistance:** disclose Codex planning and coding assistance, and identify the tests, source review, and actual version witnesses used to validate the implementation.
- **License:** currently unspecified. Choose and add a license before describing the repository as licensed for reuse.
- **Key boundary:** [server-only SerpApi key handling](security.md); the public search endpoint has a 50-attempt local allocation and no visitor accounts.

Suggested engine description, after both live integrations have been exercised:

> VersionVerdict uses SerpApi Google Search and optional Bing Search to discover technical sources. It profiles declared stack context and supported manifests, inspects bounded public source evidence, and ranks explicit version requirements or reviewed recipes against each environment.

Google retrieval and cache reuse now have a genuine sanitized cloud capture in `docs/live-verification.json`. General source inspection was unavailable there, so that capture contains only uncertain verdicts. Optional Bing remains unverified. A submission demo should use a working local or deployed source-inspection path and state each result's actual live/cached/illustrative status.

## Handoff to a teammate

The root README has the complete install and run commands. For a teammate with Python 3.12 and Node 22 already installed:

1. Clone or pull `Ananay28425/VersionVerdict`.
2. Install the pinned backend requirements and run `npm --prefix frontend ci`.
3. Run `./scripts/start_preview.sh` to build the frontend and start the single FastAPI process.
4. Use an illustrative preset first; it requires no account credentials and spends no SerpApi searches.
5. Configure a live key only when needed. Keep one shared deployed application's persistent cache and request ledger rather than several independently budgeted deployments against the same account.

Do not send account credentials in a screenshot, commit, frontend variable, or demo recording.

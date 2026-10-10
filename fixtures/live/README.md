# Genuine live retrieval capture

`2026-10-10-freertos-google.json` is a sanitized actual `/api/search` response for a declared FreeRTOS environment, using SerpApi Google Search. It is distinct from the authored illustrative fixtures in `fixtures/evidence`.

Two searches were planned. The receipt records three outbound HTTP attempts because one request retried, 18 deduplicated candidate URLs, and the application allocation remaining. The receipt does not report billed credits or the account balance. An identical repeat reused both cache entries and made no new search calls; see `docs/live-verification.json`.

General source inspection was unavailable in this cloud environment. All captured verdicts are `UNCERTAIN`; this file does not establish that the retrieved firmware advice is correct or compatible. The API key, provider request metadata, and private account details are absent. The application does not present this capture as a new live result or expose it through its illustrative-demo mode.

The capture predates the final query/relevance correction and is preserved unchanged. `docs/live-ranking-replay.json` records a separate offline reranking of its actual candidates: all IDs and verdicts remain unchanged, no requests are made, and target-relevant notification sources replace unrelated Bare results in the top three. It does not verify the revised query planner live.

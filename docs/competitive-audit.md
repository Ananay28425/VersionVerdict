# Competitive and submission audit

Reviewed October 10, 2026 (IST). This audit informs the current product changes; it does not estimate a probability of winning.

## Source coverage

The current official [BuiltWithSerpApi catalogue source](https://github.com/serpapi/BuiltWithSerpApi/blob/6a0e5a3e1ff95e03551b412338794032d251b047/src/_data/projects.json) contains **190 entries and 190 distinct source repository URLs**. All 190 listings were reviewed again. The source revision is `6a0e5a3e1ff95e03551b412338794032d251b047`, dated October 4, 2026; its catalogue fields match the previous October 9 review. The previous review read 181 nonempty READMEs, with nine empty or unavailable on the attempted paths. Those README reads were not repeated for every project today.

Catalogue metadata lists 88 hosted URLs, 115 Google Search API users, 64 projects with multiple API entries, and five projects tagged `developer-tools`. These are inventory counts, not functioning deployments, verified integrations, a complete developer-tool population, or hackathon entrant counts. The catalogue is a community showcase containing projects from several events, **not the India hackathon competitor roster**.

PatchSignal, PyPackageOracle, and AshenAudit were cloned again and their core source inspected. Their revisions remain unchanged from the earlier audit. No competitor application, dependency installation, or test suite was executed. A README promise and a source-confirmed behavior are distinguished below; missing documentation is not proof that a feature does not exist.

## Closest developer tools

| Project and evidence | Distinctive implemented behavior | Bounded gap found in inspected source | VersionVerdict decision |
|---|---|---|---|
| [PatchSignal](https://github.com/HyunsikParker/patchsignal/blob/232d801eff6f8cf5e552cff5da7fc1d0ec43c520/app.py#L445) | Google AI Mode developer incident analysis, separately retrieved Google citation corroboration, explicit ranking reasons, request caps. | Manual ecosystem/version input; version matching is a substring bonus in title/snippet. Its [README explicitly states](https://github.com/HyunsikParker/patchsignal/blob/232d801eff6f8cf5e552cff5da7fc1d0ec43c520/README.md) that candidate pages are never fetched. Search presence cannot establish whether a recipe applies. | Preserve fetched source sections, manifest context, deterministic lifecycle rules, and identical-source comparisons. Do not claim version-aware search or ranking reasons are inventions unique to this project. |
| [PyPackageOracle](https://github.com/everestkc/PyPackageOracle/blob/014b0669ecf5d824cda43e65d1c2be360ebdcdb1/oracle.py) | Four Google query perspectives and a clear task-to-package recommendation workflow. | Sends titles/snippets to GPT-4o; no project manifest or source-page applicability checks in this orchestration. Its prompt requests estimated stars and a source count without computing verification. No incorrect user-facing output was observed in this audit. | Keep source support and factual certainty separate from relevance. Avoid generated confidence, popularity, and unsupported consensus claims. |
| [AshenAudit](https://github.com/Kerkar831152/Ashen-Audit/blob/f707304008d21946b0bb335ec60296efa134a85d/src/extension.ts#L359) | IDE reviewers, disagreement-triggered SerpApi search, code repair, and implemented compiler/syntax feedback. | The inspected orchestration does not profile package versions or execute reviewed recipes against pinned dependency environments. [Google search](https://github.com/Kerkar831152/Ashen-Audit/blob/f707304008d21946b0bb335ec60296efa134a85d/src/ai/serpapi.ts#L34) returns five snippets; local validation checks selected code with available toolchains. | Preserve pinned behavior witnesses. An extension or more AI reviewers would add implementation scope without proving this product's version claims. |

The wider catalogue reinforces these lessons: [LiveLLM](https://github.com/prx0r/livellm) advertises official-source verification and a fact ledger; [ApplyPilot](https://github.com/Alyht/ApplyPilot) advertises profile-aware deterministic ranking and replay; [PriceVerdict](https://github.com/xariskrigkos/priceverdict) advertises contradiction handling and abstention; [Grounds](https://github.com/harshwardhan-kp/grounds) appears in the catalogue as an AI-search citation audit. These listing/README patterns establish prior art, not independently reproduced reliability. Citations, receipts, conservative verdicts, extra engines, and AI agents are individually common. The distinctive combination to demonstrate is **one candidate pool, two explicitly declared environments, recipe-level evidence, and reproducible API behavior at a version boundary**.

## Advantage inventory

Baseline inspected: VersionVerdict commit `d58504feb866c855abc62ffafc5e52c165195c2b`. The current expansion should preserve these working mechanisms.

| Advantage | Existing implementation evidence | Remaining product work |
|---|---|---|
| Controlled comparison | `/api/search` retrieves once and ranks the same hits independently for both profiles; response includes `pool_id`. | Keep shared candidate identity and independent context visible in broad-stack mode. |
| Source-supported applicability | Scoped recipe extraction, official documentation fetching, reviewed migration snapshots, hashes, timestamps, namespace and SQLAlchemy mode preconditions. | Broaden research input without presenting unreviewed technologies as universally verified. |
| Behavioral evidence | Committed authored witnesses and reports, accessible through `/api/witnesses`; recipes run against pinned environments. | Keep the witness's exact scope clear. It does not validate arbitrary web snippets or uploaded repositories. |
| Observable search integration | Server-side SerpApi Google Search and optional **SerpApi** Bing Search, original query/position provenance, live/cache labels and explicit failures. | Owner reports local live search now works; retain a sanitized successful run for submission evidence. That report does not verify deployment or every engine. |
| Shared allowance protection | Persistent response cache, bounded concurrency/retries, local request-attempt allocation, explicit refresh. | Explain that the allocation is local; it cannot report or enforce every teammate's shared account activity. |
| Falsifiable correctness | Curated rule evaluation and hard negatives in `fixtures/evaluation`; published denominators and reproducible commands. | Add coverage for broad input and preserve abstention. Curated performance is not production accuracy. |
| Usable developer workflow | Manifest previews, keyboard shortcuts, rank comparisons, evidence inspection, copyable recognized source recipes. | Theme choice, arbitrary declared stack context, and investigation export address the owner's daily-use gaps. |

## Changes selected for this release

1. **Allow any technology context.** Accept explicit user-declared components, versions/ranges, and platform/toolchain conditions alongside existing manifests, with bounded public documentation retrieval. This gives firmware, operating-system, C/C++, Rust, JVM, JavaScript, and other users the same retrieval workflow without pretending that every ecosystem has a dependency resolver. Preserve exact versus range versus unknown. General source inspection must return `UNCERTAIN` when evidence cannot bind a claim to the component and version. Retrieved domains are provenance, not proof of authority. Retain reviewed Python recipes as demonstrations rather than a restriction on live questions.
2. **Export the investigation.** Provide downloadable Markdown/JSON with query, declared contexts, shared pool ID, actual engine/query/position provenance, source URLs, verdict explanations, evidence excerpts/hashes, and live/cache status. This fits issue reports and code reviews and consumes no additional searches. Keep API credentials and uploaded file bodies out of exports.
3. **Make proof and comfort first-class.** Add the four requested persistent themes with legible neutral reading surfaces; retain the terminal command workflow, comparison, original ranking, explicit uncertainty, inspected source sections, and reviewed witnesses. Changing colors must not obscure verdict meaning or failure states. Avoid adding engines merely to increase the engine count.

These priorities strengthen practical usefulness without diluting factual claims. Accounts, agent frameworks, generated fixes, automatic execution of user or web code, and universal compatibility promises remain outside this change.

## Judging and eligibility

The five criteria and October 10, 2026, 11:59 PM IST deadline are **event material supplied by the owner**. The official [event page](https://serpapi.github.io/serpapi-india-hackathon-2026/) could not be independently read from this cloud environment: the network proxy returned 403, including on a permitted public-read retry. The corresponding attempted public source repository was unavailable. This access failure says nothing about whether the site is available to the owner.

Registration, participant/team conditions, allowed development dates, prize eligibility, required artifact fields, deployment requirements, and submission route therefore remain unverified. No feature count or audit can establish entitlement to the ₹1 lakh prize. Check the actual rules before submission.

| Supplied judging criterion | Demonstration to show | Credibility risk to avoid |
|---|---|---|
| Idea strength | A relevant answer changes applicability with the declared environment. | Broad compatibility claims beyond supported evidence. |
| Originality | Same searched candidates, two contexts, explicit recipe boundary, separate pinned witness. | Calling citations, AI, or additional engines novel by themselves. |
| Technical complexity | Safe profiling, bounded async retrieval, deduplication, scoped evidence, semantic rules, and hard-negative evaluation. | Complexity that adds no verified product behavior. |
| Usefulness | Any-stack research, clear uncertainty, comparison, shareable evidence, and comfortable themes. | A polished page that cannot help with real queries outside two examples. |
| Meaningful SerpApi usage | A genuine Google run discovers actual candidates; inspection and context change their ordering. Optional Bing goes through SerpApi. | Illustrative data presented as live search, or page fetching described as another SerpApi engine. |

## Submission blockers

At this audit baseline the README still marks the **public deployment URL, publicly accessible demo video, and license selection** as pending. The owner has reported successful local live usage, but no sanitized genuine capture or deployed live verification was inspected here. These deliverables matter more than another speculative feature. The available resource list contains SDKs, docs, Playground, integrations, Search Tools, blog and catalogue links; it does not itself establish special credits or eligibility.

Record the three-minute demo around one genuine search, the same-source version comparison, one evidence section and witness, a general-stack query that honestly preserves uncertainty, and an exported investigation. Show commands and measured results only when actually executed. Keep the README's supported scope and submission links current.

## Release verification

The expansion now implements the selected changes: any technology target, seven manifest formats, explicit manual hardware/platform context, four persistent palettes, source/verdict filtering, and complete Markdown/JSON investigation exports. The final backend suite passed **173 tests**, with two live tests explicitly skipped; TypeScript and the Vite production build passed. Browser evidence is recorded separately in `docs/browser-verification.json`.

A genuine Google-only FreeRTOS submission returned **18 deduplicated candidates** and recorded **three HTTP attempts including a retry**. Repeating the same generated queries reused two cached responses, made zero new calls, and preserved the candidate pool. The sanitized capture and receipts are committed in `fixtures/live/2026-10-10-freertos-google.json` and `docs/live-verification.json`. This is live retrieval evidence, not firmware compatibility evidence: source inspection was unavailable under the cloud proxy, and every verdict stayed uncertain. Optional Bing and deployed live execution remain unverified. Public deployment, demo video, license selection, and eligibility confirmation still require completion.

The live pool also exposed irrelevant results for loose platform words. The final planner avoids those words in the broad query and groups version alternatives. Bounded metadata relevance now orders generic candidates within verdict groups, with visible ranking reasons. The separately labelled offline replay in `docs/live-ranking-replay.json` moves relevant FreeRTOS sources into the top three while preserving all 18 IDs and uncertain verdicts. This is one observed improvement, not a general relevance benchmark or another live retrieval.

## Reproduce the catalogue inventory

The review used public repository source through Git because Pages HTTP was blocked. No SerpApi request was made for this audit.

```bash
git clone https://github.com/serpapi/BuiltWithSerpApi.git
cd BuiltWithSerpApi
git checkout 6a0e5a3e1ff95e03551b412338794032d251b047
python - <<'PY'
import json
from pathlib import Path
projects = json.loads(Path('src/_data/projects.json').read_text())
print('entries:', len(projects))
print('unique repositories:', len({p['githubUrl'] for p in projects}))
print('hosted URLs:', sum(bool(p.get('hostedUrl')) for p in projects))
print('Google Search:', sum('Google Search API' in p.get('apis', []) for p in projects))
print('multiple listed APIs:', sum(len(p.get('apis', [])) > 1 for p in projects))
PY
```

Expected inventory for that pinned source: **190, 190, 88, 115, 64**. The source JSON SHA-256 is `0b3090f125171f06f7140c26e4609ef40fa9ccf6413134547a22b12b104f98d3`.

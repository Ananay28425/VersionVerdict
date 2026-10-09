# Curated applicability evaluation

Run from the repository root with the backend dependencies installed:

```bash
.venv/bin/python scripts/evaluate.py --output fixtures/evaluation/report.json
```

The 30 reviewed scenarios produce 31 expected recipe verdicts because one page contains two independent examples. Fixtures include native versus V1-shim Pydantic APIs, version ranges, missing source evidence, unsupported and prerelease versions, SQLAlchemy engine mode, raw-string execution, missing receiver context, and uncommitted writes.

All source HTML is **authored evaluation input**. It is not a captured SerpApi response and is not claimed to have been fetched from the documentation-family URL assigned to a test scenario. Pinned official migration snapshots supply the lifecycle rules separately. Evaluation never executes source snippets and makes no live search requests.

`report.json` publishes per-case expected and observed labels, explanations, fixture hash, timestamp, and metric numerators/denominators:

- Exact case match: cases whose complete ordered verdict lists match / cases.
- Label accuracy: correct labels / expected or observed recipe positions, including missing or extra cards as errors.
- Definitive label precision: correct definitive predictions / all definitive predictions. Definitive means `COMPATIBLE`, `WRONG_VERSION`, or `STALE`.
- Definitive coverage: definitive predictions / evaluated recipe positions.
- Uncertainty rate: `UNCERTAIN` predictions / evaluated recipe positions.

Measured October 10, 2026 (IST): **30/30 cases**, **31/31 verdicts**, **14/14 definitive predictions**, **14/31 definitive coverage**, and **17/31 uncertain verdicts**. The curated case set deliberately includes hard negatives; its distribution does not represent real-world traffic. These figures are not production accuracy, live API success, search relevance, or latency measurements.

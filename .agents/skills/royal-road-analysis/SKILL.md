---
name: royal-road-analysis
description: Maintain the Royal Road Python analysis pipeline and generated catalog. Use for source snapshot refreshes, detector or analysis changes, analysis resume/full/retry/single-song runs, pattern or override compilation, and validation of generated analysis data. Do not use for frontend-only work.
---

# Royal Road Analysis

Read the Maintainer Analysis, Stored Data Contracts, Matching Rules, and Verification sections of `PLAN.md` before acting. Preserve those contracts rather than restating or changing them implicitly.

## Choose the Smallest Workflow

- For `data/patterns.json` or `data/overrides.json` changes, compile the catalog without downloading audio or invoking the detector:
  `uv run --no-cache python scripts/compile_catalog.py`
- For ordinary continuation, use resume mode:
  `uv run --no-cache analyze.py --resume`
- To retry only failed or missing records, use:
  `uv run --no-cache analyze.py --retry-failed`
- To analyze one source record while rebuilding the complete catalog, use:
  `uv run --no-cache analyze.py --song <source-id>`
- Use `uv run --no-cache analyze.py --full` only when the user's request requires re-downloading and reanalyzing every recording. Do not infer permission for this expensive external workflow from an unrelated code or pattern change.
- Use `--refresh-source` or `--source-commit <sha>` only when the task requires refreshing or changing the pinned Sorter snapshot.

The analysis CLI owns source consistency checks, download retry/throttling, detector-checkout validation, resumability, atomic publication, and song status preservation. Fix those mechanisms at their source when they fail; do not bypass them by manually editing generated JSON.

## Data Ownership and Safety

- Human-edited inputs are `data/patterns.json` and `data/overrides.json`.
- Generated committed outputs are `data/raw/<song-id>.json`, `data/analysis-manifest.json`, and `data/catalog.json`.
- Keep downloaded audio and HTTP metadata under ignored caches. Never stage audio, credentials, cookies, cache contents, or detector temporary artifacts.
- Keep raw detector timelines immutable. Apply reviewed exclusions and manual corrections through overrides.
- Every source song must remain represented as analyzed, unavailable, or failed. Failed and unavailable songs must not have empty raw timeline files.

## Verification and Handoff

After changing analysis code, patterns, overrides, or generated outputs, run the relevant checks:

- `npm.cmd run lint:python`
- `uv run --no-cache python -m unittest discover -s scripts/tests -p "test_*.py"`
- `uv run --no-cache python scripts/validate_data.py`

If the catalog consumed by the frontend changed, also run the frontend type-check/tests and production build listed in `AGENTS.md`.

Before handing off:

- Confirm generated outputs are internally consistent and no ignored artifacts were staged.
- Report unavailable or failed records rather than omitting them.
- If counts changed, report the source commit, detector submodule revision, detector configuration version, and matching configuration that produced them.

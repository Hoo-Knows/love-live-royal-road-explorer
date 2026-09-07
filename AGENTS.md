# Repository Instructions

## Source of Truth

- Read `PLAN.md` before making changes. It is the authoritative product contract for architecture, matching, data, and playback behavior.
- Keep implementation and tests consistent with `PLAN.md`; do not duplicate its detailed requirements here.
- Update `PLAN.md` when intentionally changing product scope, matching rules, data contracts, playback behavior, dependencies, audio sources, services, or deployment.

## Repository Boundaries

- Keep the deployed application a static Vite/React/TypeScript site with relative assets. Runtime data comes only from committed JSON.
- Keep analysis in the maintainer-only Python 3.9/`uv` pipeline. Do not add a runtime backend, database, authentication, Docker, client-side detector, or hosted audio mirror.
- Preserve the pinned `chord_recognition_module` submodule, dependency revisions, source snapshot provenance, and required attribution.

## Files and Safety

- Keep frontend code in `src/`, maintainer tooling in `scripts/`, and editable matching inputs in `data/patterns.json` and `data/overrides.json`, and metadata corrections in `data/source-overrides.json`.
- Treat `data/source/`, `data/raw/`, `data/analysis-manifest.json`, and `data/catalog.json` as generated output. Change their generators or inputs and regenerate them; never hand-edit compiled output.
- Preserve UTF-8 text, including Japanese names and interface copy.
- Never commit downloaded audio, credentials, cookies, caches, or detector temporary artifacts.
- Preserve unrelated user changes. Avoid destructive resets and broad deletes.

## Workflow

- Use the repository-local `royal-road-analysis` skill for analysis, source refreshes, detector changes, pattern/override compilation, and generated catalog validation.
- Treat full catalog analysis, detector-wide reanalysis, and multi-song resume or retry runs as long-running analysis workflows. This policy does not apply to single-song analysis, pattern/override compilation, tests, data validation, type-checking, or builds.
- Do not start a long-running analysis workflow by default, either synchronously or as a detached/background process. Complete any safe preparation, then hand off the exact command and working directory, the expected generated outputs and provenance, and the follow-up validation commands.
- Start a long-running analysis workflow only when the user explicitly approves the exact command and states whether the agent may wait for it or must run it detached. A broad request to work on the analysis pipeline is not approval to start such a run.
- For an explicitly approved detached run, write output to a dedicated log, provide a status-check command, and confirm before starting that no other analysis process is writing generated data.
- Do not report work that depends on a long-running analysis as complete until its generated outputs have subsequently been inspected and validated.
- Do not run a full catalog analysis unless the requested work requires it. Pattern- or override-only changes use the compile workflow without downloading audio or invoking the detector.
- When generated counts change, report the source snapshot and detector/config revisions responsible.

## Useful Commands

- `npm.cmd ci` installs the locked frontend dependencies.
- `npm.cmd run dev` starts the Vite development server.
- `npm.cmd run lint` runs the Python and frontend linters.
- `npm.cmd run typecheck` checks TypeScript without emitting files.
- `npm.cmd exec -- vitest run --configLoader runner` runs the frontend tests once.
- `uv run --no-cache python -m unittest discover -s scripts/tests -p "test_*.py"` runs the Python tests.
- `uv run --no-cache python scripts/validate_data.py` validates generated analysis data and catalog aggregates.
- `npm.cmd exec -- vite build --configLoader runner --outDir .build/verify` creates a production bundle in an ignored workspace directory.

Run the checks applicable to the changed area before handing off. For behavior or data-contract changes, run lint, both test suites, data validation, type-checking, and the production build.

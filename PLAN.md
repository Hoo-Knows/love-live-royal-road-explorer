# Love Live Royal Road Explorer

## Summary

Build a static React/TypeScript listening atlas for the public `IV–V–iii–vi` and `IV–V–III–vi` labels in the Love Live song catalog. The maintainer matcher also retains the `iv–v–III–VI` definition for analysis, but its `public` configuration flag keeps it out of the compiled catalog and UI. Matching is structural and does not infer or present a song key or major/minor context. The site shows catalog and analysis totals, searchable song rows, and exact timestamped playback moments without a runtime backend.

Metadata and wiki audio URLs come from one commit of the [Love Live Sorter data](https://github.com/hamproductions/the-sorter/tree/main/data). Maintainer analysis calls the pinned, MIT-licensed [large-vocabulary chord recognizer](https://github.com/Hoo-Knows/large-vocabulary-chord-recognition) directly through the `chord_recognition_module` Git submodule. The deployed site needs only the compiled catalog JSON.

## Maintainer Analysis

- Use Python 3.9 and `uv` to fetch one consistent source commit, cache wiki OGG files, run chord recognition, and compile the static catalog.
- Reuse the ignored source cache only when its atomic snapshot marker matches the requested commit and all three file hashes; refresh or fail closed for missing, mixed, or changed files.
- Keep downloads and their conditional-request metadata under ignored `.cache/audio/`. Throttle requests, retry transient failures, validate TLS, and write cache metadata atomically.
- Pin the submodule revision, detector configuration, CPU dependencies, and CA bundle. Validate the submodule checkout before recognition and reject dirty detector worktrees.
- Support full, resume, retry-failed, and single-song analysis. In resume mode, reuse a current analyzed record without downloading audio when its source URL, audio SHA-256, raw timeline, and per-song analysis-version token match; use full mode to force an audio refresh and reanalysis.
- Preserve a valid analyzed timeline during a transient refresh failure in any analysis mode. Mark changed, missing, or permanently failed analysis explicitly and retry it later.
- Publish catalog and manifest checkpoints atomically after each processed song. Pattern/override-only changes use the compile command and never invoke the detector.
- Never commit downloaded audio, credentials, HTTP cache metadata, or detector temporary artifacts.

## Stored Data Contracts

- `data/raw/<song-id>.json` exists only for analyzed songs and contains `schemaVersion`, `songId`, `durationSeconds`, and the immutable indexed `{startSeconds, endSeconds, label}` timeline.
- `data/analysis-manifest.json` is the sole maintainer state file. It contains the source commit, current `chord_recognition_module` revision/config, and one compact record per source song: status, audio URL/hash, analysis-version token, and error.
- The ignored source cache also contains an atomic `.snapshot.json` marker with the source commit and metadata-file hashes; it is provenance only and is never published.
- `data/catalog.json` (schema `4.1.0`) contains only runtime fields: schema/fixture flag, pattern labels, direct aggregate metrics, searchable song metadata/status, one occurrence count per song, and playback occurrences with per-chord bounds plus derived Roman-numeral analyses. Each occurrence stores one ordered decorated analysis string per matched pattern ID, so the analysis text does not repeat the pattern ID or split display-ready labels into another nested structure; extensions and detector bass degrees are display data, while raw chord labels remain unchanged. It contains no build timestamps, revision hashes, HTTP metadata, raw indices, review notes, key profiles, or mode context.
- `data/patterns.json` (schema `5.0.0`) and `data/overrides.json` (schema `2.0.0`) remain readable maintainer inputs. Each pattern has a `public` flag; false definitions remain available to matching but are excluded from public pattern labels, occurrences, and filters. Manual correction notes and raw segment references stay there rather than being published to the frontend.
- Use versioned JSON schemas, atomic writes, and generated-data validation. Do not hand-edit compiled output.

## Matching Rules

- Parse enharmonic roots and inversions while preserving detector labels for display; ignore bass inversion for harmonic function.
- Configure accepted major, dominant, and minor extensions. Exclude diminished, augmented, suspended, and no-chord labels unless explicitly configured.
- Match `IV–V–iii–vi`, `IV–V–III–vi` (the major-third alternative label), and the retained internal `iv–v–III–VI` definition using relative root intervals and chord-quality checks regardless of surrounding key evidence. Only patterns marked `public` are compiled into the public interface.
- Exact matches use exactly four consecutive raw segments. Passing matches consider five consecutive segments where removing one of the three internal segments leaves four valid anchors.
- Apply one global passing rule: the skipped chord must parse, last no more than 2 seconds, and last no more than half as long as each adjacent anchor.
- Never collapse repeats, discard short segments, bridge missing indices, or skip more than one segment. Deduplicate definitions sharing the same anchor interpretation.
- Preserve stable exact IDs derived from the song and four raw segment identities. Derive passing IDs from the song, all five raw segment identities, and the skipped position.
- Preserve exact bounds and add 0.5 seconds of clamped playback padding.
- Apply exclusions and documented manual additions after automatic matching without changing raw timelines.

## Static UI

- Deploy the committed static catalog and Vite production bundle to GitHub Pages through the repository's GitHub Actions workflow. Build on pushes to `main` (or a manual dispatch), run the frontend test suite before publishing, and upload only `dist`; the maintainer pipeline, source/audio caches, and detector checkout are never part of the Pages artifact.
- Show matching-song, analyzed, catalog, occurrence, unavailable, and failed totals directly from the catalog.
- Keep the two public progression labels available in matching results without mode suffixes or key-confidence controls; do not display a progression graphic or pattern labels in the hero, and keep hidden definitions out of occurrence labels and filters.
- Show a Leaderboard section with side-by-side ranked charts for matching-song and occurrence counts, with a shared unit/artist versus series grouping toggle. Credit every listed name, keep the full ranking in a keyboard-scrollable view, and derive statistics from compiled catalog data at runtime.
- Show all songs initially, sorted by occurrence count and normalized title, with a title-sort option and artist/series facet toggles; pair Japanese and English artist names into one stable facet identity, rank artist options by credited-song count with normalized-name tie-breaks, and keep series options in catalog order. Do not expose a pattern facet filter.
- Provide an app-wide English/Japanese toggle for interface copy and catalog name display, including localized song, artist, and series labels. Catalog names and their translations must come from the Sorter snapshot fields; do not synthesize artist/title translations in the client. Preserve one alias slot per credited source record. Use the established Japanese term `王道進行` for the Royal Road progression.
- Search Unicode-aware, case-insensitive substrings across Japanese, English, phonetic, artist, and series names, including source-provided English/romanized aliases.
- Explain that clicking a song plays its occurrences. Expand one row at a time with one player and timestamped occurrence controls showing one plain decorated Roman-numeral analysis line plus the raw chord labels. During ordinary song playback, highlight each occurrence and its current chord as playback reaches its detector segment; moment playback remains scoped to the clicked occurrence and highlights only its chords. Clear playback highlights when playback finishes or focus moves to another playback mode/moment. Passing matches show all five labels and identify the passing chord; the passing chord is omitted from the four-anchor Roman analysis.
- Fetch wiki audio only on expansion using a no-referrer blob request, revoke it on collapse, and provide direct-URL and failure fallbacks. All hook-generated errors use the active localized copy.
- Timestamp controls seek to the padded start, play, and pause at the padded end. Boundary monitoring uses animation frames plus media/timer fallbacks for background tabs. Stale play promises cannot change a newer selection; focus leaving the moment control clears its selection. If the listener uses native controls during that playback, automatic end monitoring stops. Switching selections stops current playback.
- Hidden playback cue: when the first chord of `3:16.4` in `Genyou Yakou` starts playing, the UI highlight color transitions to orange until playback stops, native playback control is used, or the expanded song detail is closed.
- Keep unavailable/failed songs searchable but non-playable. Preserve keyboard access, focus states, responsive styling, reduced motion, source/detector attribution, and the automated-analysis disclaimer.
- Use relative assets for static hosting. Do not expose source or detector revision hashes in the UI.

## Verification and Completion

- Test chord parsing, both retained progressions, rejected discarded forms, context independence, passing rules in all internal gaps, four- and five-segment overrides, stable IDs, schemas, incremental modes, detector-version changes, cache behavior, and atomic writes.
- Test multilingual search/sorting, direct totals/rankings/rendering, the absence of key-confidence controls and mode suffixes, status rendering, audio loading/cleanup, seeking/stopping, and failure fallbacks.
- Validate that manifest IDs equal catalog IDs, only analyzed songs have raw files, segments are ordered/non-overlapping, compiled occurrences reproduce from raw data plus patterns/overrides, and aggregate counts agree.
- Run Python lint/tests, frontend lint/type-check/tests, data validation, and the production build.
- A complete analysis reports every permanent gap; viewing or deploying the finished site requires neither Python nor the detector.

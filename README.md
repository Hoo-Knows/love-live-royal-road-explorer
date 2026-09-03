# Love Live Royal Road Explorer

The Royal Road is a static React/TypeScript listening atlas for the public `IV–V–iii–vi` and `IV–V–III–vi` labels in Love Live songs. The maintainer pattern configuration can retain additional internal definitions, such as `iv–v–III–VI`, without publishing them. Matches use relative root intervals and chord qualities without inferring song keys; exact four-segment matches and eligible short passing chords are included. The deployed site reads committed `data/catalog.json`; it has no backend, database, authentication, client-side detector, or audio mirror.

## Static site

```sh
npm install
npm run dev
```

Useful checks:

```sh
npm run typecheck
npm test
npm run build
npm run validate:data
```

The production build uses relative assets and can be hosted on GitHub Pages or another basic static host. Audio stays on the Love Live wiki and is fetched only when a song row is expanded. The site language toggle uses the Sorter-provided Japanese/English title and credited-name fields directly; it does not generate client-side translations.

## GitHub Pages deployment

The workflow in `.github/workflows/deploy-pages.yml` installs the locked npm dependencies, runs the frontend tests and production build, and deploys only `dist`. It runs on pushes to `main` and can also be started manually from the Actions tab.

For the initial repository setup, open **Settings â†’ Pages** on GitHub and select **GitHub Actions** as the build and deployment source. No `gh-pages` branch or committed build output is needed. Vite's relative asset base supports both a repository URL such as `https://<user>.github.io/royal-road/` and a root/custom-domain deployment.

## Maintainer analysis

Clone recursively so the pinned detector and its bundled model checkpoints are available:

```sh
git clone --recurse-submodules <repository-url>
cd royal-road
uv run analyze.py
```

The Python 3.9 environment is maintainer-only. `uv run analyze.py` fetches one commit of the Love Live Sorter metadata, caches wiki audio under ignored `.cache/audio/`, calls the pinned `chord_recognition_module` Python API, and atomically updates the raw timelines, compact manifest, and frontend catalog.

Analysis modes:

```sh
uv run analyze.py --full
uv run analyze.py --resume
uv run analyze.py --retry-failed
uv run analyze.py --song <source-id>
```

Resume is the default. A current analyzed record is reused directly, without downloading audio, when its URL, audio SHA-256, raw timeline, and analysis-version token still match. Use `--full` to force an audio refresh and reanalysis. ETags and last-modified values are local cache details in `.cache/audio/index.json`; they are not committed.

The source metadata cache is refreshed automatically when its files or ignored
`.snapshot.json` provenance marker are missing or inconsistent. To force a
refresh explicitly (for example, after changing the pinned source commit), run:

```sh
uv run analyze.py --refresh-source
```

Pass `--source-commit <sha>` when you need a specific Sorter snapshot; otherwise
the script uses the manifest commit for a refresh, or resolves the current
`main` commit when starting without an existing snapshot.

If only patterns or reviewed corrections changed, rebuild without downloading audio or invoking recognition:

```sh
npm run compile:catalog
```

The compile command uses the ignored source cache when available and otherwise reconstructs source metadata from the existing catalog. Progress is written to stderr and the final metrics summary to stdout.

## Data layout

- `data/raw/<song-id>.json`: analyzed chord timeline only—song ID, duration, and indexed segments.
- `data/analysis-manifest.json`: source commit, module/config identity, and compact per-song resume/status state.
- `data/catalog.json`: runtime-only song, direct metric/count, pattern label, decorated Roman-numeral analyses, per-chord playback bounds, and searchable name-alias data used by React.
- `data/patterns.json`: editable harmonic definitions, per-pattern public visibility flags, quality sets, and the global passing-chord rule.
- `data/overrides.json`: reviewed exclusions and manual/corrected matches with their notes.

Roman-numeral analyses are ordered display strings, one per matched pattern,
and retain extension detail (`IVmaj7`, `V7`, `iii7`) plus detector bass degrees
as slash suffixes (`IV/3`, `V/b7`). Passing chords remain in the raw chord-label
row and are marked there rather than being included among the four structural
Roman anchors.

Failed and unavailable songs remain in the manifest and catalog but do not have empty raw timeline files. Downloaded audio and HTTP cache metadata are ignored.

## Attribution

Metadata and wiki audio URLs come from [Love Live Sorter](https://github.com/hamproductions/the-sorter/tree/main/data). Chord analysis uses the pinned MIT-licensed [large-vocabulary chord recognizer](https://github.com/Hoo-Knows/large-vocabulary-chord-recognition) through `chord_recognition_module`. Results are automated and may be wrong; recordings remain hosted by the wiki.

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

The production build uses relative assets and can be hosted on GitHub Pages or another basic static host. Audio stays on the Love Live wiki and is fetched only when a song row is expanded. The site language toggle uses the committed ll-fans/wiki Japanese/English title and credited-name fields directly; it does not generate client-side translations.

## GitHub Pages deployment

The workflow in `.github/workflows/deploy-pages.yml` installs the locked npm dependencies, runs the frontend tests and production build, and deploys only `dist`. It runs on pushes to `main` and can also be started manually from the Actions tab.

For the initial repository setup, open **Settings â†’ Pages** on GitHub and select **GitHub Actions** as the build and deployment source. No `gh-pages` branch or committed build output is needed. Vite's relative asset base supports both a repository URL such as `https://<user>.github.io/royal-road/` and a root/custom-domain deployment.

## Maintainer analysis

Clone recursively so the pinned detector and its bundled model checkpoints are available:

```sh
git clone --recurse-submodules <repository-url>
cd royal-road
uv run --no-cache analyze.py
```

The Python 3.9 environment is maintainer-only. `uv run --no-cache analyze.py` reads the committed, validated source snapshot, caches wiki audio under ignored `.cache/audio/`, calls the pinned `chord_recognition_module` Python API, and atomically updates raw timelines, the manifest, and the frontend catalog.

Analysis modes:

```sh
uv run --no-cache analyze.py --full
uv run --no-cache analyze.py --resume
uv run --no-cache analyze.py --retry-failed
uv run --no-cache analyze.py --song <source-id>
```

Resume is the default. A current analyzed record is reused directly, without downloading audio, when its URL, audio SHA-256, raw timeline, and analysis-version token still match. Use `--full` to force an audio refresh and reanalysis. ETags and last-modified values are local cache details in `.cache/audio/index.json`; they are not committed.

Source refresh is a separate, explicit command:

```sh
uv run --no-cache python scripts/refresh_source.py
uv run --no-cache analyze.py
```

The refresh also generates [data/source-review.md](data/source-review.md), listing unresolved names and recordings with reasons and candidate files. Select an ambiguous recording with matching wikiPage and wikiFile entries in data/source-overrides.json; then rerun the refresh and compile commands. The --report option changes the review file location.

To keep compatible successful wiki results and retry only failed, stale, new, or changed songs, run:

```sh
uv run --no-cache python scripts/refresh_source.py --retry-failed
```

The wiki performer label is retained as verification evidence, but it does not replace or block the ordered ll-fans credits shown in the public catalog. Each source song lists all verified wiki audio URLs except off-vocal and instrumental recordings in wiki row order; the first URL is used by the site and analyzer. A `wikiFile` override moves that recording to the front.

The refresh command POSTs paginated songs and artists plus series queries to
[ll-fans](https://ll-fans.jp/api/graphql), including announced releases. It
independently discovers and verifies names and full vocal recordings through
the [wiki MediaWiki API](https://love-live.fandom.com/api.php). It never downloads
audio or runs recognition. Clone/build/compile operations need no source refresh.

Generated UTF-8 inputs are committed in `data/source/`. The versioned marker
records endpoints, collection interval, file hashes, a content-derived snapshot
ID, page revisions, file identities and verification outcomes. It is published
last; partial or altered snapshots are rejected. During later wiki outages,
compatible independently verified enrichment may be retained as stale.
ll-fans failures abort publication.

Edit `data/source-overrides.json` for corrections, then rerun source refresh.
The `songs`, `artists` and `series` objects are keyed by ll-fans IDs and accept
`name`, `englishName`, `wikiPage` and a review `note`. Song records also
accept `wikiFile` (requires `wikiPage`) or `"audio": null` to mark audio
unavailable. Explicit files must occur on the selected wiki page and resolve
through the API. Missing vocal recordings remain unavailable; names
fall back to Japanese. Wiki results are reported by the refresh command and
remain reviewable in the marker.

If only patterns or reviewed corrections changed, rebuild without downloading audio or invoking recognition:

```sh
npm run compile:catalog
```

The compile command uses the committed source snapshot. Only when all source files and the marker are absent does it reconstruct metadata from the committed catalog and manifest; partial or corrupt snapshots are rejected. Progress is written to stderr and the final metrics summary to stdout.

## Data layout

- `data/source/`: generated, committed ll-fans metadata and independently verified wiki enrichment with snapshot provenance.
- `data/source-overrides.json`: editable metadata corrections and explicit wiki selections.
- `data/raw/<song-id>.json`: analyzed chord timeline only—song ID, duration, and indexed segments.
- `data/analysis-manifest.json`: sourceSnapshot ID, module/config identity, and compact per-song resume/status state.
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

Song, artist and series metadata comes from [ll-fans](https://ll-fans.jp/). Names and recording URLs are independently collected from [Love Live! Wiki](https://love-live.fandom.com/wiki/Love_Live!_Wiki); wiki text is available under its [CC BY-SA license](https://www.fandom.com/licensing). Chord analysis uses the pinned MIT-licensed [large-vocabulary chord recognizer](https://github.com/Hoo-Knows/large-vocabulary-chord-recognition) through `chord_recognition_module`. Results are automated and may be wrong; recordings remain hosted by the wiki.

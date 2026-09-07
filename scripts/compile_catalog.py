"""Compile committed raw timelines and compact analysis state without audio work."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys
from typing import Any, Dict, Mapping, Optional

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from royal_road.io_utils import atomic_write_json, read_json  # noqa: E402
from royal_road.metadata import parse_source_catalog  # noqa: E402
from royal_road.pipeline import compile_catalog  # noqa: E402
from royal_road.sources import load_metadata_snapshot, snapshot_absent  # noqa: E402
from royal_road.state import analysis_state, build_manifest  # noqa: E402


def _log(message: str) -> None:
    print(message, file=sys.stderr, flush=True)


def _safe_filename(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "-", value).strip("-") or "song"


def _raw_path(raw_dir: Path, song_id: str) -> Path:
    return raw_dir / f"{_safe_filename(song_id)}.json"


def _read_raw(raw_dir: Path) -> Dict[str, Mapping[str, Any]]:
    analyses: Dict[str, Mapping[str, Any]] = {}
    for path in raw_dir.glob("*.json") if raw_dir.exists() else []:
        try:
            value = read_json(path)
        except (OSError, ValueError):
            continue
        if isinstance(value, Mapping) and value.get("songId") is not None:
            analyses[str(value["songId"])] = value
    return analyses


def _source_songs_from_catalog(catalog: Mapping[str, Any]) -> list[dict[str, Any]]:
    songs = catalog.get("songs")
    if not isinstance(songs, list):
        raise ValueError("Existing catalog has no songs array to use as compile metadata")
    result = []
    for song in songs:
        if not isinstance(song, Mapping) or song.get("id") is None:
            raise ValueError("Existing catalog contains an invalid song record")
        result.append(
            {
                "id": str(song["id"]),
                "titles": dict(song.get("titles", {})),
                "artistNames": list(song.get("artistNames", [])),
                "artistAliases": list(song.get("artistAliases", [])),
                "seriesNames": list(song.get("seriesNames", [])),
                "seriesAliases": list(song.get("seriesAliases", [])),
                "creators": [
                    {
                        "id": str(creator["id"]),
                        "name": creator["name"],
                        "aliases": list(creator.get("aliases", [])),
                    }
                    for creator in song.get("creators", [])
                ],
                "audioUrl": song.get("audioUrl"),
                "releaseDate": song.get("releaseDate"),
            }
        )
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Compile the static catalog from raw timelines.")
    parser.add_argument("--source-dir", type=Path, default=Path("data/source"))
    parser.add_argument("--raw-dir", type=Path, default=Path("data/raw"))
    parser.add_argument("--manifest", type=Path, default=Path("data/analysis-manifest.json"))
    parser.add_argument("--catalog", type=Path, default=Path("data/catalog.json"))
    parser.add_argument("--patterns", type=Path, default=Path("data/patterns.json"))
    parser.add_argument("--overrides", type=Path, default=Path("data/overrides.json"))
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        previous_catalog = read_json(args.catalog) if args.catalog.exists() else {}
        previous_manifest = read_json(args.manifest) if args.manifest.exists() else {}
        if snapshot_absent(args.source_dir):
            _log("source files entirely absent; using metadata from the committed catalog")
            source_songs = _source_songs_from_catalog(previous_catalog)
            is_fixture = bool(previous_catalog.get("isFixture", False))
            snapshot_id = previous_manifest.get("sourceSnapshot")
            if not isinstance(snapshot_id, str) or not re.fullmatch(r"[a-f0-9]{64}", snapshot_id):
                raise ValueError("Catalog fallback requires a valid sourceSnapshot in the manifest")
        else:
            snapshot, source_payloads = load_metadata_snapshot(args.source_dir)
            snapshot_id = snapshot["snapshotId"]
            source_songs = parse_source_catalog(*source_payloads)
            is_fixture = False
        raw_analyses = _read_raw(args.raw_dir)
        patterns = read_json(args.patterns)
        overrides = read_json(args.overrides)
        previous_manifest = read_json(args.manifest) if args.manifest.exists() else {}
        states = dict(previous_manifest.get("songs", {})) if isinstance(previous_manifest, Mapping) else {}
    except (OSError, ValueError, KeyError) as error:
        print(f"Could not read compile inputs: {error}", file=sys.stderr)
        return 2

    source_ids = {str(song["id"]) for song in source_songs}
    states = {song_id: state for song_id, state in states.items() if song_id in source_ids}
    for song in source_songs:
        song_id = str(song["id"])
        audio_url = song.get("audioUrl")
        state = states.get(song_id)
        if not audio_url:
            states[song_id] = analysis_state(status="unavailable", audio_url=None)
        elif state is None:
            states[song_id] = analysis_state(
                status="failed", audio_url=audio_url, error="This song has not been analyzed yet."
            )
        elif state.get("audioUrl") != audio_url:
            states[song_id] = analysis_state(
                status="failed",
                audio_url=audio_url,
                error="The source audio URL changed; reanalyze this song.",
            )
        elif state.get("status") == "analyzed" and song_id not in raw_analyses:
            states[song_id] = analysis_state(
                status="failed", audio_url=audio_url, error="The analyzed timeline is missing."
            )

    obsolete = [song_id for song_id in raw_analyses
                if song_id not in source_ids or states.get(song_id, {}).get("status") != "analyzed"]
    active_raw = {song_id: raw for song_id, raw in raw_analyses.items() if song_id not in obsolete}

    catalog = compile_catalog(
        source_songs,
        active_raw,
        states,
        patterns,
        overrides,
        is_fixture=is_fixture,
    )
    # Matching/configuration errors must not remove existing timelines.
    for song_id in obsolete:
        _raw_path(args.raw_dir, song_id).unlink(missing_ok=True)
    atomic_write_json(args.catalog, catalog)
    atomic_write_json(args.manifest, build_manifest(snapshot_id, states))
    _log(
        f"complete: songs={catalog['metrics']['catalogSongCount']}, "
        f"analyzed={catalog['metrics']['analyzedSongCount']}, "
        f"matching={catalog['metrics']['matchingSongCount']}, "
        f"occurrences={catalog['metrics']['totalOccurrenceCount']}"
    )
    print(json.dumps(catalog["metrics"], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Run or resume the maintainer-only Royal Road analysis pipeline.

The pinned ``chord_recognition_module`` submodule is imported only while
analyzing audio. The deployed static site consumes committed catalog JSON.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import re
import sys
from typing import Any, Dict, Mapping, Optional

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from royal_road.detector import DetectorError, analysis_version, run_detector, validate_detector_checkout  # noqa: E402
from royal_road.downloader import DownloadError, download_audio, probe_duration  # noqa: E402
from royal_road.io_utils import atomic_write_json, read_json  # noqa: E402
from royal_road.metadata import parse_source_catalog  # noqa: E402
from royal_road.pipeline import compile_catalog, replace_catalog_song  # noqa: E402
from royal_road.sources import (  # noqa: E402
    SOURCE_FILES,
    SOURCE_SNAPSHOT_MARKER,
    fetch_metadata_snapshot,
    local_metadata_snapshot,
    read_metadata_payloads,
)
from royal_road.state import analysis_state, build_manifest  # noqa: E402


RAW_SCHEMA_VERSION = "2.0.0"
CACHE_INDEX_SCHEMA_VERSION = "1.0.0"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _log(message: str) -> None:
    print(f"[{_now()}] {message}", file=sys.stderr, flush=True)


def _safe_filename(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "-", value).strip("-") or "song"


def _load_optional(path: Path, default: Any) -> Any:
    return read_json(path) if path.exists() else default


def _manifest_commit(manifest_path: Path) -> Optional[str]:
    if not manifest_path.exists():
        return None
    value = read_json(manifest_path)
    commit = value.get("sourceCommit") if isinstance(value, Mapping) else None
    return str(commit) if commit else None


def _has_source_files(source_dir: Path) -> bool:
    # The marker is part of the cache contract. Without it, the three JSON
    # files may be a partial/mixed snapshot and must be refreshed atomically.
    return all((source_dir / filename).is_file() for filename in SOURCE_FILES) and (
        source_dir / SOURCE_SNAPSHOT_MARKER
    ).is_file()


def _prepare_source_snapshot(
    source_dir: Path,
    manifest_path: Path,
    requested_commit: Optional[str],
    refresh: bool,
) -> Dict[str, Any]:
    """Return a verified source snapshot, refreshing an unusable cache."""
    commit = requested_commit or _manifest_commit(manifest_path)
    if refresh or not _has_source_files(source_dir):
        return fetch_metadata_snapshot(source_dir, commit, log=_log)

    if not commit:
        raise ValueError("--source-commit is required when the manifest has no source commit")
    try:
        return local_metadata_snapshot(source_dir, commit)
    except (OSError, ValueError) as error:
        # A marker can exist while being stale, malformed, or inconsistent with
        # one of the three files. Refresh the complete snapshot in that case.
        _log(f"cached source snapshot is not reusable ({error}); refreshing")
        return fetch_metadata_snapshot(source_dir, commit, log=_log)


def _raw_path(raw_dir: Path, song_id: str) -> Path:
    return raw_dir / f"{_safe_filename(song_id)}.json"


def _read_raw_analyses(raw_dir: Path) -> Dict[str, Dict[str, Any]]:
    analyses: Dict[str, Dict[str, Any]] = {}
    if not raw_dir.exists():
        return analyses
    for path in raw_dir.glob("*.json"):
        try:
            payload = read_json(path)
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(payload, Mapping) and payload.get("songId") is not None:
            analyses[str(payload["songId"])] = dict(payload)
    return analyses


def _raw_record(
    song_id: str,
    duration: Optional[float],
    segments: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "schemaVersion": RAW_SCHEMA_VERSION,
        "songId": song_id,
        "durationSeconds": duration,
        "segments": segments,
    }


def _remove_raw(raw_dir: Path, raw_analyses: Dict[str, Dict[str, Any]], song_id: str) -> None:
    raw_analyses.pop(song_id, None)
    _raw_path(raw_dir, song_id).unlink(missing_ok=True)


def _bound_segments_to_duration(
    segments: list[dict[str, Any]], duration: Optional[float]
) -> list[dict[str, Any]]:
    """Keep detector timestamps inside the measured recording bounds."""

    if duration is None:
        return segments
    duration_value = float(duration)
    if not math.isfinite(duration_value) or duration_value < 0:
        raise ValueError("Recording duration must be a finite, non-negative number")

    bounded: list[dict[str, Any]] = []
    for position, segment in enumerate(segments):
        start = float(segment["startSeconds"])
        end = float(segment["endSeconds"])
        if start >= duration_value:
            raise ValueError(
                f"Detector segment {position} starts at {start}s, outside the {duration_value}s recording"
            )
        if end > duration_value:
            if position != len(segments) - 1:
                raise ValueError(f"Detector segment {position} extends past the recording duration")
            end = duration_value
        if end <= start:
            raise ValueError(f"Detector segment {position} has no time remaining inside the recording")
        bounded.append(segment if end == float(segment["endSeconds"]) else {**segment, "endSeconds": end})
    return bounded


def _publish_checkpoint(
    catalog_path: Path,
    manifest_path: Path,
    catalog: Mapping[str, Any],
    source_commit: str,
    states: Mapping[str, Mapping[str, Any]],
) -> Mapping[str, Any]:
    atomic_write_json(catalog_path, catalog)
    atomic_write_json(manifest_path, build_manifest(source_commit, states))
    return catalog


def _compile_live_song(
    catalog: Mapping[str, Any],
    source_song: Mapping[str, Any],
    raw: Optional[Mapping[str, Any]],
    state: Mapping[str, Any],
    patterns: Mapping[str, Any],
    overrides: Mapping[str, Any],
    *,
    is_fixture: bool,
) -> dict[str, Any]:
    song_id = str(source_song["id"])
    partial = compile_catalog(
        [source_song],
        {song_id: raw} if raw is not None else {},
        {song_id: state},
        patterns,
        overrides,
        is_fixture=is_fixture,
    )
    return replace_catalog_song(catalog, partial["songs"][0])


def _mode_from_args(args: argparse.Namespace) -> str:
    selected = [
        name
        for name, enabled in (
            ("full", args.full),
            ("resume", args.resume),
            ("retry-failed", args.retry_failed),
        )
        if enabled
    ]
    if len(selected) > 1:
        raise ValueError("Choose only one of --full, --resume, or --retry-failed")
    return selected[0] if selected else args.mode


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build the Royal Road raw timelines and static catalog.")
    parser.add_argument("--mode", choices=("full", "resume", "retry-failed"), default="resume")
    parser.add_argument("--full", action="store_true", help="Re-download and reanalyze every selected recording.")
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Reuse current analyzed records without downloading audio (the default).",
    )
    parser.add_argument("--retry-failed", action="store_true", help="Retry only failed or missing analyses.")
    parser.add_argument("--song", help="Analyze one source song ID and still compile the complete catalog.")
    parser.add_argument("--source-commit", help="Source metadata commit; omit to resolve current main when fetching.")
    parser.add_argument("--source-dir", type=Path, default=Path("data/source"))
    parser.add_argument("--refresh-source", action="store_true")
    parser.add_argument("--raw-dir", type=Path, default=Path("data/raw"))
    parser.add_argument("--audio-cache", type=Path, default=Path(".cache/audio"))
    parser.add_argument("--manifest", type=Path, default=Path("data/analysis-manifest.json"))
    parser.add_argument("--catalog", type=Path, default=Path("data/catalog.json"))
    parser.add_argument("--patterns", type=Path, default=Path("data/patterns.json"))
    parser.add_argument("--overrides", type=Path, default=Path("data/overrides.json"))
    parser.add_argument("--throttle", type=float, default=1.0)
    parser.add_argument("--max-retries", type=int, default=3)
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        mode = _mode_from_args(args)
    except ValueError as error:
        parser.error(str(error))
        return 2

    _log(f"starting analysis: mode={mode}, song={args.song or 'all'}")
    _log(f"raw output: {args.raw_dir}; audio cache: {args.audio_cache}")

    try:
        source_snapshot = _prepare_source_snapshot(
            args.source_dir,
            args.manifest,
            args.source_commit,
            args.refresh_source,
        )
        source_songs = parse_source_catalog(*read_metadata_payloads(args.source_dir))
    except Exception as error:
        _log(f"source preparation failed: {error}")
        print(f"Could not prepare source snapshot: {error}", file=sys.stderr)
        return 2

    source_commit = str(source_snapshot["commit"])
    is_fixture = bool(source_snapshot.get("fixture", False))
    _log(f"source ready: commit={source_commit}, songs={len(source_songs)}")

    patterns = read_json(args.patterns)
    overrides = read_json(args.overrides)
    previous_manifest = _load_optional(args.manifest, {"songs": {}})
    previous_states = dict(previous_manifest.get("songs", {})) if isinstance(previous_manifest, Mapping) else {}
    raw_analyses = _read_raw_analyses(args.raw_dir)
    source_by_id = {str(song["id"]): song for song in source_songs}
    # Seed a provisional state for every source song before the first
    # checkpoint. A crash during a fresh or single-song run must not make the
    # unprocessed songs disappear from the manifest.
    states: Dict[str, Mapping[str, Any]] = {}
    for source_song in source_songs:
        song_id = str(source_song["id"])
        audio_url = source_song.get("audioUrl")
        previous_state = previous_states.get(song_id)
        if not audio_url:
            states[song_id] = analysis_state(status="unavailable", audio_url=None)
            _remove_raw(args.raw_dir, raw_analyses, song_id)
        elif not isinstance(previous_state, Mapping) or previous_state.get("audioUrl") != audio_url:
            states[song_id] = analysis_state(
                status="failed",
                audio_url=audio_url,
                error=(
                    "The source audio URL changed; reanalyze this song."
                    if isinstance(previous_state, Mapping)
                    else "This song has not been analyzed yet."
                ),
            )
            if isinstance(previous_state, Mapping):
                _remove_raw(args.raw_dir, raw_analyses, song_id)
        elif previous_state.get("status") == "analyzed" and song_id not in raw_analyses:
            states[song_id] = analysis_state(
                status="failed",
                audio_url=audio_url,
                error="The analyzed timeline is missing.",
            )
        else:
            states[song_id] = dict(previous_state)

    cache_index_path = args.audio_cache / "index.json"
    cache_index = _load_optional(
        cache_index_path,
        {"schemaVersion": CACHE_INDEX_SCHEMA_VERSION, "songs": {}},
    )
    cache_states = dict(cache_index.get("songs", {})) if isinstance(cache_index, Mapping) else {}

    live_catalog = compile_catalog(
        source_songs,
        raw_analyses,
        states,
        patterns,
        overrides,
        is_fixture=is_fixture,
    )
    selected_ids = [str(args.song)] if args.song else list(source_by_id)
    missing = [song_id for song_id in selected_ids if song_id not in source_by_id]
    if missing:
        print(f"Unknown source song ID(s): {', '.join(missing)}", file=sys.stderr)
        return 2
    if any(source_by_id[song_id].get("audioUrl") for song_id in selected_ids):
        try:
            validate_detector_checkout()
        except DetectorError as error:
            _log(f"detector checkout validation failed: {error}")
            print(f"Could not validate detector checkout: {error}", file=sys.stderr)
            return 2

    current_analysis_version = analysis_version()
    processed = {"reused": 0, "analyzed": 0, "unavailable": 0, "failed": 0}
    for position, song_id in enumerate(selected_ids, start=1):
        source_song = source_by_id[song_id]
        audio_url = source_song.get("audioUrl")
        previous_state = states.get(song_id)
        previous_raw = raw_analyses.get(song_id)
        title = source_song.get("titles", {}).get("en") or source_song.get("titles", {}).get("ja") or song_id
        _log(f"[{position}/{len(selected_ids)}] {song_id}: {title}")

        if not audio_url:
            state = analysis_state(status="unavailable", audio_url=None)
            states[song_id] = state
            _remove_raw(args.raw_dir, raw_analyses, song_id)
            processed["unavailable"] += 1
            live_catalog = _compile_live_song(
                live_catalog, source_song, None, state, patterns, overrides, is_fixture=is_fixture
            )
            _publish_checkpoint(args.catalog, args.manifest, live_catalog, source_commit, states)
            continue

        if (
            mode == "retry-failed"
            and previous_state
            and previous_state.get("status") == "analyzed"
            and previous_raw is not None
        ):
            processed["reused"] += 1
            continue

        cache_path = args.audio_cache / f"{_safe_filename(song_id)}.ogg"
        download_info: Optional[Mapping[str, Any]] = None
        reusable_segments: Optional[list[dict[str, Any]]] = None
        if previous_raw and isinstance(previous_raw.get("segments"), list):
            try:
                reusable_segments = _bound_segments_to_duration(
                    list(previous_raw["segments"]), previous_raw.get("durationSeconds")
                )
            except (KeyError, TypeError, ValueError):
                reusable_segments = None

        if (
            mode == "resume"
            and previous_state
            and previous_state.get("status") == "analyzed"
            and previous_state.get("audioUrl") == audio_url
            and previous_state.get("audioSha256")
            and previous_state.get("analysisVersion") == current_analysis_version
            and reusable_segments is not None
        ):
            raw = _raw_record(
                song_id,
                previous_raw.get("durationSeconds") if previous_raw else None,
                reusable_segments,
            )
            atomic_write_json(_raw_path(args.raw_dir, song_id), raw)
            raw_analyses[song_id] = raw
            state = analysis_state(
                status="analyzed",
                audio_url=audio_url,
                audio_sha256=previous_state.get("audioSha256"),
                analysis_version=current_analysis_version,
            )
            states[song_id] = state
            processed["reused"] += 1
            _log("  existing analysis record is current; reusing timeline without downloading audio")
            live_catalog = _compile_live_song(
                live_catalog, source_song, raw, state, patterns, overrides, is_fixture=is_fixture
            )
            _publish_checkpoint(args.catalog, args.manifest, live_catalog, source_commit, states)
            continue

        try:
            cache_previous = cache_states.get(song_id)
            if not isinstance(cache_previous, Mapping) or cache_previous.get("audioUrl") != audio_url:
                cache_previous = None
            _log("  checking/downloading wiki audio")
            download_info = download_audio(
                str(audio_url),
                cache_path,
                cache_previous,
                throttle_seconds=max(0.0, args.throttle),
                max_retries=max(0, args.max_retries),
                log=_log,
            )
            cache_states[song_id] = {
                "audioUrl": audio_url,
                "etag": download_info.get("etag"),
                "lastModified": download_info.get("lastModified"),
            }
            atomic_write_json(
                cache_index_path,
                {"schemaVersion": CACHE_INDEX_SCHEMA_VERSION, "songs": cache_states},
            )
            downloaded_sha = download_info.get("audioSha256")
            if (
                mode == "resume"
                and previous_state
                and previous_state.get("status") == "analyzed"
                and previous_state.get("audioUrl") == audio_url
                and previous_state.get("analysisVersion") == current_analysis_version
                and downloaded_sha
                and downloaded_sha == previous_state.get("audioSha256")
                and reusable_segments is not None
            ):
                raw = _raw_record(
                    song_id,
                    previous_raw.get("durationSeconds") if previous_raw else None,
                    reusable_segments,
                )
                atomic_write_json(_raw_path(args.raw_dir, song_id), raw)
                raw_analyses[song_id] = raw
                state = analysis_state(
                    status="analyzed",
                    audio_url=audio_url,
                    audio_sha256=downloaded_sha,
                    analysis_version=current_analysis_version,
                )
                processed["reused"] += 1
                _log("  audio and analysis version unchanged; reusing timeline")
            else:
                _log("  running pinned chord detector")
                duration = probe_duration(cache_path)
                segments = run_detector(cache_path)
                if duration is None and segments:
                    duration = max(float(segment["endSeconds"]) for segment in segments)
                segments = _bound_segments_to_duration(segments, duration)
                raw = _raw_record(song_id, duration, segments)
                atomic_write_json(_raw_path(args.raw_dir, song_id), raw)
                raw_analyses[song_id] = raw
                state = analysis_state(
                    status="analyzed",
                    audio_url=audio_url,
                    audio_sha256=downloaded_sha,
                    analysis_version=current_analysis_version,
                )
                processed["analyzed"] += 1
                _log(f"  detector complete: segments={len(segments)}")
        except DownloadError as error:
            if (
                error.transient
                and previous_state
                and previous_state.get("status") == "analyzed"
                and previous_state.get("audioUrl") == audio_url
                and previous_state.get("analysisVersion") == current_analysis_version
                and previous_state.get("audioSha256")
                and reusable_segments is not None
            ):
                raw = _raw_record(
                    song_id,
                    previous_raw.get("durationSeconds") if previous_raw else None,
                    reusable_segments,
                )
                atomic_write_json(_raw_path(args.raw_dir, song_id), raw)
                raw_analyses[song_id] = raw
                state = dict(previous_state)
                processed["reused"] += 1
                _log("  transient download failure; retaining the current verified timeline")
            else:
                state = analysis_state(status="failed", audio_url=audio_url, error=error)
                _remove_raw(args.raw_dir, raw_analyses, song_id)
                raw = None
                processed["failed"] += 1
                _log(f"  audio download failed: {error}")
        except (DetectorError, OSError, ValueError) as error:
            state = analysis_state(
                status="failed",
                audio_url=audio_url,
                audio_sha256=download_info.get("audioSha256") if download_info else None,
                error=error,
            )
            _remove_raw(args.raw_dir, raw_analyses, song_id)
            raw = None
            processed["failed"] += 1
            _log(f"  analysis failed: {error}")

        states[song_id] = state
        live_catalog = _compile_live_song(
            live_catalog,
            source_song,
            raw_analyses.get(song_id),
            state,
            patterns,
            overrides,
            is_fixture=is_fixture,
        )
        _publish_checkpoint(args.catalog, args.manifest, live_catalog, source_commit, states)

    # Give every source song one current state, even after a single-song run.
    for source_song in source_songs:
        song_id = str(source_song["id"])
        audio_url = source_song.get("audioUrl")
        state = states.get(song_id)
        if not audio_url:
            states[song_id] = analysis_state(status="unavailable", audio_url=None)
            _remove_raw(args.raw_dir, raw_analyses, song_id)
        elif state is None:
            states[song_id] = analysis_state(
                status="failed",
                audio_url=audio_url,
                error="This song has not been analyzed yet.",
            )
        elif state.get("audioUrl") != audio_url:
            states[song_id] = analysis_state(
                status="failed",
                audio_url=audio_url,
                error="The source audio URL changed; reanalyze this song.",
            )
            _remove_raw(args.raw_dir, raw_analyses, song_id)
        elif state.get("status") == "analyzed" and song_id not in raw_analyses:
            states[song_id] = analysis_state(
                status="failed",
                audio_url=audio_url,
                error="The analyzed timeline is missing.",
            )
        elif state.get("status") != "analyzed":
            _remove_raw(args.raw_dir, raw_analyses, song_id)

    for song_id in list(raw_analyses):
        if song_id not in source_by_id or states.get(song_id, {}).get("status") != "analyzed":
            _remove_raw(args.raw_dir, raw_analyses, song_id)

    catalog = compile_catalog(
        source_songs,
        raw_analyses,
        states,
        patterns,
        overrides,
        is_fixture=is_fixture,
    )
    _publish_checkpoint(args.catalog, args.manifest, catalog, source_commit, states)
    _log(
        f"complete: analyzed={catalog['metrics']['analyzedSongCount']}, "
        f"matching={catalog['metrics']['matchingSongCount']}, "
        f"occurrences={catalog['metrics']['totalOccurrenceCount']}, "
        f"unavailable={catalog['metrics']['unavailableSongCount']}, "
        f"failed={catalog['metrics']['failedSongCount']}"
    )
    print(
        json.dumps(
            {"mode": mode, "processed": processed, "metrics": catalog["metrics"]},
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

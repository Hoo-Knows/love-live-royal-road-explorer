"""Validate compact analysis state, raw timelines, and the static catalog."""

from __future__ import annotations

import argparse
import math
from pathlib import Path
import re
import sys
from typing import Any, Dict, List, Mapping, Optional

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from royal_road.detector import analysis_descriptor, analysis_version  # noqa: E402
from royal_road.io_utils import read_json  # noqa: E402
from royal_road.pipeline import compile_catalog  # noqa: E402


STATUSES = {"analyzed", "unavailable", "failed"}
RAW_FIELDS = {"schemaVersion", "songId", "durationSeconds", "segments"}
STATE_FIELDS = {"status", "audioUrl", "audioSha256", "analysisVersion", "error"}
CATALOG_FIELDS = {
    "schemaVersion",
    "isFixture",
    "patterns",
    "metrics",
    "songs",
}


def _validate_catalog_counts(catalog: Mapping[str, Any]) -> list[str]:
    errors: list[str] = []
    songs = catalog.get("songs", [])
    patterns = catalog.get("patterns", [])
    if not isinstance(songs, list) or not isinstance(patterns, list):
        return errors
    pattern_ids = {str(value.get("id")) for value in patterns if isinstance(value, Mapping)}
    expected_occurrence_count = 0
    expected_matching_count = 0
    for song in songs:
        if not isinstance(song, Mapping):
            continue
        song_id = str(song.get("id"))
        count = song.get("occurrenceCount")
        occurrences = song.get("occurrences")
        if not isinstance(occurrences, list):
            errors.append(f"catalog song {song_id} occurrences must be an array")
            continue
        seen_occurrence_ids = set()
        for occurrence in occurrences:
            if not isinstance(occurrence, Mapping):
                errors.append(f"catalog song {song_id} has an invalid occurrence")
                continue
            occurrence_id = str(occurrence.get("id"))
            if occurrence_id in seen_occurrence_ids:
                errors.append(f"catalog song {song_id} has duplicate occurrence ID {occurrence_id}")
            seen_occurrence_ids.add(occurrence_id)
            occurrence_patterns = occurrence.get("patternIds")
            if not isinstance(occurrence_patterns, list) or not occurrence_patterns or set(occurrence_patterns) - pattern_ids:
                errors.append(f"catalog occurrence {occurrence_id} has unknown patterns")
            labels = occurrence.get("chordLabels")
            bounds = occurrence.get("chordBounds")
            roman_analyses = occurrence.get("romanNumeralAnalyses")
            passing_index = occurrence.get("passingChordIndex")
            if not isinstance(labels, list) or len(labels) not in (4, 5):
                errors.append(f"catalog occurrence {occurrence_id} must have four or five chord labels")
            elif (len(labels) == 4 and passing_index is not None) or (
                len(labels) == 5 and passing_index not in (1, 2, 3)
            ):
                errors.append(f"catalog occurrence {occurrence_id} has an invalid passing chord index")
            if not isinstance(bounds, list) or not isinstance(labels, list) or len(bounds) != len(labels):
                errors.append(f"catalog occurrence {occurrence_id} must have one bound per chord label")
            else:
                try:
                    exact_start = float(occurrence["exactStartSeconds"])
                    exact_end = float(occurrence["exactEndSeconds"])
                except (KeyError, TypeError, ValueError):
                    exact_start = -math.inf
                    exact_end = math.inf
                previous_end = exact_start
                for position, bound in enumerate(bounds):
                    if not isinstance(bound, Mapping) or set(bound) != {"startSeconds", "endSeconds"}:
                        errors.append(f"catalog occurrence {occurrence_id} has invalid chord bounds at {position}")
                        continue
                    try:
                        start = float(bound["startSeconds"])
                        end = float(bound["endSeconds"])
                        if (
                            not math.isfinite(start)
                            or not math.isfinite(end)
                            or start < 0
                            or end <= start
                            or start < previous_end
                            or start < exact_start
                            or end > exact_end
                        ):
                            errors.append(f"catalog occurrence {occurrence_id} has invalid chord bounds at {position}")
                        previous_end = end
                    except (KeyError, TypeError, ValueError):
                        errors.append(f"catalog occurrence {occurrence_id} has invalid chord bounds at {position}")
            if not isinstance(roman_analyses, list) or not roman_analyses:
                errors.append(f"catalog occurrence {occurrence_id} must have Roman-numeral analyses")
            elif not all(isinstance(analysis, str) and analysis.strip() for analysis in roman_analyses):
                errors.append(f"catalog occurrence {occurrence_id} has an invalid Roman-numeral analysis")
            elif isinstance(occurrence_patterns, list) and len(roman_analyses) != len(occurrence_patterns):
                errors.append(f"catalog occurrence {occurrence_id} Roman analyses do not cover its patterns")
        if count != len(occurrences):
            errors.append(f"catalog song {song_id} has an incorrect occurrence count")
        expected_occurrence_count += len(occurrences)
        expected_matching_count += int(bool(occurrences))
    expected_metrics = {
        "matchingSongCount": expected_matching_count,
        "totalOccurrenceCount": expected_occurrence_count,
        "analyzedSongCount": sum(1 for song in songs if song.get("status") == "analyzed"),
        "catalogSongCount": len(songs),
        "unavailableSongCount": sum(1 for song in songs if song.get("status") == "unavailable"),
        "failedSongCount": sum(1 for song in songs if song.get("status") == "failed"),
    }
    if catalog.get("metrics") != expected_metrics:
        errors.append("catalog aggregate status metrics do not match song records")
    return errors


def validate_raw_analysis(raw: Mapping[str, Any], path: str = "raw analysis") -> list[str]:
    errors: list[str] = []
    prefix = f"{path}: "
    if set(raw) != RAW_FIELDS:
        errors.append(prefix + f"fields are {sorted(raw)}, expected {sorted(RAW_FIELDS)}")
    if raw.get("schemaVersion") != "2.0.0":
        errors.append(prefix + "schemaVersion must be 2.0.0")
    if not isinstance(raw.get("songId"), str):
        errors.append(prefix + "songId must be a string")
    segments = raw.get("segments")
    if not isinstance(segments, list):
        return errors + [prefix + "segments must be a list"]
    last_end = -1.0
    seen_indices = set()
    for position, segment in enumerate(segments):
        if not isinstance(segment, Mapping):
            errors.append(prefix + f"segment {position} is not an object")
            continue
        if set(segment) != {"index", "startSeconds", "endSeconds", "label"}:
            errors.append(prefix + f"segment {position} has unexpected fields")
        try:
            index = int(segment["index"])
            start = float(segment["startSeconds"])
            end = float(segment["endSeconds"])
            if not math.isfinite(start) or not math.isfinite(end):
                errors.append(prefix + f"segment {position} has non-finite bounds")
            if index != position or index in seen_indices:
                errors.append(prefix + f"segment {position} has invalid index {index}")
            seen_indices.add(index)
            if start < 0 or end <= start or start < last_end:
                errors.append(prefix + f"segments overlap or have invalid bounds at {position}")
            if not isinstance(segment["label"], str) or not segment["label"].strip():
                errors.append(prefix + f"segment {position} has an invalid label")
            last_end = end
        except (KeyError, TypeError, ValueError):
            errors.append(prefix + f"segment {position} has invalid values")
    duration = raw.get("durationSeconds")
    if duration is not None:
        try:
            duration_value = float(duration)
            if not math.isfinite(duration_value) or duration_value < 0:
                errors.append(prefix + "durationSeconds is invalid")
            elif segments and last_end > duration_value + 1e-6:
                errors.append(prefix + "segments extend past durationSeconds")
        except (TypeError, ValueError):
            errors.append(prefix + "durationSeconds is invalid")
    return errors


def _catalog_source_songs(catalog: Mapping[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "id": str(song["id"]),
            "titles": dict(song.get("titles", {})),
            "artistNames": list(song.get("artistNames", [])),
            "artistAliases": list(song.get("artistAliases", [])),
            "seriesNames": list(song.get("seriesNames", [])),
            "seriesAliases": list(song.get("seriesAliases", [])),
            "audioUrl": song.get("audioUrl"),
            "releaseDate": song.get("releaseDate"),
        }
        for song in catalog.get("songs", [])
        if isinstance(song, Mapping)
    ]


def validate_dataset(
    catalog: Mapping[str, Any],
    manifest: Mapping[str, Any],
    raw_analyses: Mapping[str, Mapping[str, Any]],
    patterns: Mapping[str, Any],
    overrides: Mapping[str, Any],
) -> list[str]:
    errors: list[str] = []
    if set(catalog) != CATALOG_FIELDS:
        errors.append(f"catalog fields are {sorted(catalog)}, expected {sorted(CATALOG_FIELDS)}")
    if catalog.get("schemaVersion") != "4.1.0":
        errors.append("catalog schemaVersion must be 4.1.0")
    errors.extend(_validate_catalog_counts(catalog))
    if set(manifest) != {"schemaVersion", "sourceCommit", "analysis", "songs"}:
        errors.append("manifest has unexpected or missing top-level fields")
    if manifest.get("schemaVersion") != "2.0.0":
        errors.append("manifest schemaVersion must be 2.0.0")
    if manifest.get("analysis") != analysis_descriptor():
        errors.append("manifest analysis descriptor does not match the pinned module")

    songs = catalog.get("songs")
    states = manifest.get("songs")
    if not isinstance(songs, list):
        return errors + ["catalog songs must be an array"]
    if not isinstance(states, Mapping):
        return errors + ["manifest songs must be an object"]
    catalog_by_id = {
        str(song.get("id")): song for song in songs if isinstance(song, Mapping) and song.get("id") is not None
    }
    if len(catalog_by_id) != len(songs):
        errors.append("catalog contains an invalid or duplicate song ID")
    if set(states) != set(catalog_by_id):
        errors.append("manifest song IDs do not match catalog song IDs")

    analyzed_ids = set()
    current_version = analysis_version()
    for song_id, song in catalog_by_id.items():
        state = states.get(song_id)
        if not isinstance(state, Mapping):
            errors.append(f"manifest has no state for {song_id}")
            continue
        if set(state) != STATE_FIELDS:
            errors.append(f"manifest state {song_id} has unexpected or missing fields")
        status = state.get("status")
        if status not in STATUSES:
            errors.append(f"manifest state {song_id} has invalid status {status!r}")
        if song.get("status") != status:
            errors.append(f"catalog and manifest statuses differ for {song_id}")
        if song.get("audioUrl") != state.get("audioUrl"):
            errors.append(f"catalog and manifest audio URLs differ for {song_id}")
        if status == "analyzed":
            analyzed_ids.add(song_id)
            if state.get("analysisVersion") != current_version:
                errors.append(f"analyzed state {song_id} does not use the current analysis version")
            if not state.get("audioSha256"):
                errors.append(f"analyzed state {song_id} has no audio hash")
            if state.get("error") is not None:
                errors.append(f"analyzed state {song_id} has an error")
        elif state.get("analysisVersion") is not None:
            errors.append(f"non-analyzed state {song_id} has an analysis version")
        if status == "unavailable" and state.get("audioUrl") is not None:
            errors.append(f"unavailable state {song_id} has an audio URL")

    if set(raw_analyses) != analyzed_ids:
        missing = sorted(analyzed_ids - set(raw_analyses))
        extra = sorted(set(raw_analyses) - analyzed_ids)
        if missing:
            errors.append(f"analyzed songs missing raw timelines: {missing[:10]}")
        if extra:
            errors.append(f"raw timelines without analyzed state: {extra[:10]}")
    for song_id, raw in raw_analyses.items():
        errors.extend(validate_raw_analysis(raw, f"{song_id} raw"))
        if str(raw.get("songId")) != song_id:
            errors.append(f"raw timeline filename identity differs for {song_id}")

    try:
        expected = compile_catalog(
            _catalog_source_songs(catalog),
            raw_analyses,
            states,
            patterns,
            overrides,
            is_fixture=bool(catalog.get("isFixture", False)),
        )
        if expected != catalog:
            errors.append("catalog does not match a fresh compile of raw timelines and analysis state")
    except (KeyError, TypeError, ValueError) as error:
        errors.append(f"catalog could not be recomputed: {error}")
    return errors


def _safe_filename(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "-", value).strip("-") or "song"


def _load_raw(
    raw_dir: Path,
    diagnostics: Optional[List[str]] = None,
) -> Dict[str, Mapping[str, Any]]:
    result: Dict[str, Mapping[str, Any]] = {}
    if not raw_dir.exists():
        return result
    reported = diagnostics if diagnostics is not None else []
    for path in sorted(raw_dir.glob("*.json")):
        try:
            value = read_json(path)
        except (OSError, ValueError) as error:
            reported.append(f"raw file {path} is unreadable: {error}")
            continue
        if not isinstance(value, Mapping):
            reported.append(f"raw file {path} must contain a JSON object")
            continue
        song_id = value.get("songId")
        if not isinstance(song_id, str) or not song_id.strip():
            reported.append(f"raw file {path} is missing a string songId")
            continue
        song_id = song_id.strip()
        expected_name = f"{_safe_filename(song_id)}.json"
        if path.name != expected_name:
            reported.append(
                f"raw file {path} has a path mismatch for songId {song_id!r}; expected {expected_name}"
            )
        if song_id in result:
            reported.append(f"duplicate raw payload songId {song_id!r} in {path}")
            continue
        result[song_id] = value
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate Royal Road JSON data.")
    parser.add_argument("--catalog", type=Path, default=Path("data/catalog.json"))
    parser.add_argument("--raw-dir", type=Path, default=Path("data/raw"))
    parser.add_argument("--manifest", type=Path, default=Path("data/analysis-manifest.json"))
    parser.add_argument("--patterns", type=Path, default=Path("data/patterns.json"))
    parser.add_argument("--overrides", type=Path, default=Path("data/overrides.json"))
    args = parser.parse_args(argv)
    try:
        catalog = read_json(args.catalog)
        manifest = read_json(args.manifest)
        raw_diagnostics: list[str] = []
        raw = _load_raw(args.raw_dir, raw_diagnostics)
        errors = validate_dataset(
            catalog,
            manifest,
            raw,
            read_json(args.patterns),
            read_json(args.overrides),
        )
        errors = raw_diagnostics + errors
    except (OSError, ValueError) as error:
        print(f"Unable to read data: {error}", file=sys.stderr)
        return 2
    if errors:
        print("Data validation failed:")
        print("\n".join(f"- {error}" for error in errors))
        return 1
    print(f"Validated {len(catalog.get('songs', []))} catalog songs and {len(raw)} raw timelines.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

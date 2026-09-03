"""Catalog compilation shared by the CLI and data validation tests."""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from .matching import (
    apply_overrides,
    build_roman_numeral_analyses,
    load_passing_rule,
    load_pattern_definitions,
    match_patterns,
)


SCHEMA_VERSION = "4.1.0"


def _catalog_metrics(songs: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    counts = [int(song.get("occurrenceCount", 0)) for song in songs]
    return {
        "matchingSongCount": sum(1 for count in counts if count > 0),
        "totalOccurrenceCount": sum(counts),
        "analyzedSongCount": sum(1 for song in songs if song["status"] == "analyzed"),
        "catalogSongCount": len(songs),
        "unavailableSongCount": sum(1 for song in songs if song["status"] == "unavailable"),
        "failedSongCount": sum(1 for song in songs if song["status"] == "failed"),
    }


def _frontend_occurrence(
    occurrence: Mapping[str, Any],
    patterns: Sequence[Any],
) -> dict[str, Any]:
    """Project an internal match into fields consumed by the static site."""

    return {
        "id": occurrence["id"],
        "exactStartSeconds": occurrence["exactStartSeconds"],
        "exactEndSeconds": occurrence["exactEndSeconds"],
        "playbackStartSeconds": occurrence["playbackStartSeconds"],
        "playbackEndSeconds": occurrence["playbackEndSeconds"],
        "chordLabels": list(occurrence["chordLabels"]),
        "chordBounds": [dict(bound) for bound in occurrence["chordBounds"]],
        "patternIds": list(occurrence["patternIds"]),
        "romanNumeralAnalyses": build_roman_numeral_analyses(
            occurrence["chordLabels"],
            occurrence["patternIds"],
            patterns,
            occurrence["passingChordIndex"],
        ),
        "passingChordIndex": occurrence["passingChordIndex"],
        "provenance": occurrence["provenance"],
    }


def replace_catalog_song(
    catalog: Mapping[str, Any],
    replacement: Mapping[str, Any],
) -> dict[str, Any]:
    """Return a catalog snapshot with one compiled song and all metrics replaced."""

    replacement_id = str(replacement["id"])
    found = False
    songs = []
    for song in catalog.get("songs", []):
        if str(song["id"]) == replacement_id:
            songs.append(dict(replacement))
            found = True
        else:
            songs.append(dict(song))
    if not found:
        raise ValueError(f"Cannot replace unknown catalog song {replacement_id}")
    return {**catalog, "metrics": _catalog_metrics(songs), "songs": songs}


def compile_catalog(
    source_songs: Sequence[Mapping[str, Any]],
    raw_analyses: Mapping[str, Mapping[str, Any]],
    analysis_states: Mapping[str, Mapping[str, Any]],
    pattern_payload: Mapping[str, Any],
    override_payload: Mapping[str, Any],
    *,
    is_fixture: bool = False,
) -> dict[str, Any]:
    expected_pattern_fields = {"schemaVersion", "qualitySets", "patterns", "passingRule"}
    if set(pattern_payload) != expected_pattern_fields:
        raise ValueError(f"patterns fields must be {sorted(expected_pattern_fields)}")
    if pattern_payload.get("schemaVersion") != "5.0.0":
        raise ValueError("patterns schemaVersion must be 5.0.0")
    if set(override_payload) != {"schemaVersion", "songs"}:
        raise ValueError("overrides fields must be ['schemaVersion', 'songs']")
    if override_payload.get("schemaVersion") != "2.0.0":
        raise ValueError("overrides schemaVersion must be 2.0.0")
    definitions = load_pattern_definitions(pattern_payload)
    passing_rule = load_passing_rule(pattern_payload)
    quality_sets = pattern_payload.get("qualitySets", {})
    pattern_ids = [definition.id for definition in definitions]
    public_pattern_ids = {definition.id for definition in definitions if definition.public}
    songs = []

    for source in source_songs:
        song_id = str(source["id"])
        raw = raw_analyses.get(song_id)
        state = analysis_states.get(song_id)
        audio_url = source.get("audioUrl")
        if not audio_url:
            status = "unavailable"
            error = "No wiki audio URL was present in the source snapshot."
        elif state is None:
            status = "failed"
            error = "This song has not been analyzed yet."
        else:
            status = str(state.get("status", "failed"))
            error = state.get("error")
            if status == "analyzed" and raw is None:
                status = "failed"
                error = "The analyzed timeline is missing."

        duration = raw.get("durationSeconds") if status == "analyzed" and raw else None
        occurrences = []
        if status == "analyzed" and raw:
            segments = raw.get("segments", [])
            internal = match_patterns(song_id, segments, definitions, quality_sets, duration, passing_rule)
            internal = apply_overrides(
                song_id,
                segments,
                internal,
                override_payload,
                pattern_ids,
                duration,
                passing_rule,
            )
            public_occurrences = []
            for occurrence in internal:
                visible_pattern_ids = [
                    pattern_id for pattern_id in occurrence["patternIds"] if pattern_id in public_pattern_ids
                ]
                if not visible_pattern_ids:
                    continue
                public_occurrence = dict(occurrence)
                public_occurrence["patternIds"] = visible_pattern_ids
                public_occurrences.append(_frontend_occurrence(public_occurrence, definitions))
            occurrences = public_occurrences

        songs.append(
            {
                "id": song_id,
                "titles": dict(source.get("titles", {})),
                "artistNames": list(source.get("artistNames", [])),
                "artistAliases": list(source.get("artistAliases", [])),
                "seriesNames": list(source.get("seriesNames", [])),
                "seriesAliases": list(source.get("seriesAliases", [])),
                "audioUrl": audio_url,
                "releaseDate": source.get("releaseDate"),
                "status": status,
                "durationSeconds": duration,
                "error": error,
                "occurrenceCount": len(occurrences),
                "occurrences": occurrences,
            }
        )

    return {
        "schemaVersion": SCHEMA_VERSION,
        "isFixture": bool(is_fixture),
        "patterns": [
            {"id": definition.id, "label": definition.label}
            for definition in definitions
            if definition.public
        ],
        "metrics": _catalog_metrics(songs),
        "songs": songs,
    }


__all__ = ["SCHEMA_VERSION", "compile_catalog", "replace_catalog_song"]

"""Structural exact and passing-chord pattern matching."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
import re
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple, Union

from .chords import (
    ParsedChord,
    format_roman_numeral,
    parse_chord_label,
    quality_is_allowed,
)


PADDING_SECONDS = 0.5


@dataclass(frozen=True)
class PatternDefinition:
    id: str
    label: str
    root_offsets: Tuple[int, ...]
    qualities: Tuple[str, ...]
    public: bool = True

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "PatternDefinition":
        expected_fields = {"id", "label", "rootOffsets", "qualities", "public"}
        if set(value) != expected_fields:
            raise ValueError(
                f"Pattern {value.get('id', '<unknown>')} fields must be {sorted(expected_fields)}"
            )
        if len(value["rootOffsets"]) != 4 or len(value["qualities"]) != 4:
            raise ValueError(f"Pattern {value.get('id', '<unknown>')} must contain four anchors")
        if not isinstance(value["public"], bool):
            raise ValueError(f"Pattern {value.get('id', '<unknown>')} public flag must be boolean")
        return cls(
            id=str(value["id"]),
            label=str(value["label"]),
            root_offsets=tuple(int(item) % 12 for item in value["rootOffsets"]),
            qualities=tuple(str(item) for item in value["qualities"]),
            public=value["public"],
        )


@dataclass(frozen=True)
class PassingRule:
    max_duration_seconds: float
    max_adjacent_duration_ratio: float

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "PassingRule":
        if set(value) != {"maxDurationSeconds", "maxAdjacentDurationRatio"}:
            raise ValueError("The passing rule has unexpected or missing fields")
        return cls(float(value["maxDurationSeconds"]), float(value["maxAdjacentDurationRatio"]))


def load_pattern_definitions(pattern_payload: Mapping[str, Any]) -> List[PatternDefinition]:
    definitions = [PatternDefinition.from_mapping(value) for value in pattern_payload.get("patterns", [])]
    if not definitions:
        raise ValueError("At least one pattern is required")
    ids = [definition.id for definition in definitions]
    if len(ids) != len(set(ids)):
        raise ValueError("Pattern IDs must be unique")
    return definitions


def load_passing_rule(pattern_payload: Mapping[str, Any]) -> PassingRule:
    value = pattern_payload.get("passingRule")
    if not isinstance(value, Mapping):
        raise ValueError("A global passing rule is required")
    rule = PassingRule.from_mapping(value)
    if not math.isfinite(rule.max_duration_seconds) or rule.max_duration_seconds < 0:
        raise ValueError("The passing duration cap is invalid")
    if not math.isfinite(rule.max_adjacent_duration_ratio) or not 0 <= rule.max_adjacent_duration_ratio <= 1:
        raise ValueError("The passing adjacent-duration ratio is invalid")
    return rule


def _field(segment: Mapping[str, Any], *names: str) -> Any:
    for name in names:
        if name in segment:
            return segment[name]
    raise KeyError(f"Missing segment field; expected one of {names}")


def _segment_identity(segment: Mapping[str, Any], fallback_index: int) -> Dict[str, Any]:
    return {
        "index": int(segment.get("index", fallback_index)),
        "startSeconds": float(_field(segment, "startSeconds", "start")),
        "endSeconds": float(_field(segment, "endSeconds", "end")),
        "label": str(_field(segment, "label", "chord")),
    }


def _safe_song_id(song_id: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "-", str(song_id)).strip("-") or "song"


def stable_occurrence_id(
    song_id: str,
    segments: Sequence[Mapping[str, Any]],
    indices: Optional[Sequence[int]] = None,
) -> str:
    """Make an exact-match ID from the song and four immutable segment identities."""

    if indices is None:
        indices = list(range(len(segments)))
    identity = [
        {**_segment_identity(segment, int(index)), "index": int(index)}
        for index, segment in zip(indices, segments)
    ]
    digest = hashlib.sha256(
        json.dumps(
            {"songId": str(song_id), "segments": identity},
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()[:16]
    return f"rr-{_safe_song_id(song_id)}-{digest}"


def stable_passing_occurrence_id(
    song_id: str,
    segments: Sequence[Mapping[str, Any]],
    passing_chord_index: int,
    indices: Optional[Sequence[int]] = None,
) -> str:
    """Make a passing-match ID from all five identities and the skipped position."""

    if indices is None:
        indices = list(range(len(segments)))
    identity = [
        {**_segment_identity(segment, int(index)), "index": int(index)}
        for index, segment in zip(indices, segments)
    ]
    digest = hashlib.sha256(
        json.dumps(
            {
                "songId": str(song_id),
                "segments": identity,
                "passingChordIndex": int(passing_chord_index),
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()[:16]
    return f"rr-{_safe_song_id(song_id)}-{digest}"


def _clamp_bounds(start: float, end: float, duration_seconds: Optional[float]) -> Tuple[float, float]:
    duration = duration_seconds if duration_seconds is not None and duration_seconds > 0 else end
    return max(0.0, start - PADDING_SECONDS), min(duration, end + PADDING_SECONDS)


def _chord_bounds(identities: Sequence[Mapping[str, Any]]) -> List[Dict[str, float]]:
    return [
        {
            "startSeconds": float(identity["startSeconds"]),
            "endSeconds": float(identity["endSeconds"]),
        }
        for identity in identities
    ]


def _quality_values(
    pattern: PatternDefinition, position: int, quality_sets: Mapping[str, Iterable[str]]
) -> Iterable[str]:
    quality_name = pattern.qualities[position]
    return quality_sets.get(quality_name, (quality_name,))


def _parse_window(
    window: Sequence[Mapping[str, Any]], start_position: int
) -> Optional[Tuple[Tuple[int, ...], List[Dict[str, Any]], List[ParsedChord]]]:
    try:
        indices = tuple(int(segment.get("index", start_position + offset)) for offset, segment in enumerate(window))
    except (TypeError, ValueError):
        return None
    if indices != tuple(range(indices[0], indices[0] + len(window))):
        return None

    identities: List[Dict[str, Any]] = []
    parsed: List[ParsedChord] = []
    previous_end = -1.0
    for offset, segment in enumerate(window):
        try:
            identity = _segment_identity(segment, start_position + offset)
            start = identity["startSeconds"]
            end = identity["endSeconds"]
            chord = parse_chord_label(identity["label"])
        except (KeyError, TypeError, ValueError):
            return None
        if (
            not math.isfinite(start)
            or not math.isfinite(end)
            or start < 0
            or end <= start
            or (offset and start < previous_end)
            or chord is None
        ):
            return None
        previous_end = end
        identities.append(identity)
        parsed.append(chord)
    return indices, identities, parsed


def _matching_patterns(
    parsed: Sequence[ParsedChord],
    patterns: Sequence[PatternDefinition],
    quality_sets: Mapping[str, Iterable[str]],
) -> List[str]:
    first_root = parsed[0].root_pitch_class
    relative_roots = tuple((chord.root_pitch_class - first_root) % 12 for chord in parsed)
    matches = []
    for pattern in patterns:
        if len(pattern.root_offsets) != 4 or tuple(pattern.root_offsets) != relative_roots:
            continue
        if all(
            quality_is_allowed(chord, _quality_values(pattern, position, quality_sets))
            for position, chord in enumerate(parsed)
        ):
            matches.append(pattern.id)
    return sorted(set(matches))


_PATTERN_SEPARATOR = re.compile(r"\s*(?:–|—|-)\s*")


def _pattern_roman_numerals(pattern: PatternDefinition) -> Tuple[str, ...]:
    """Extract the four editable Roman degrees from a pattern label."""

    numerals = tuple(value.strip() for value in _PATTERN_SEPARATOR.split(pattern.label.strip()))
    if len(numerals) == 4 and all(numerals):
        return numerals
    # Matching remains usable for an internal definition with a descriptive
    # label that is not written as four Roman degrees. The public patterns use
    # the four-token form and therefore never take this fallback.
    return ("?", "?", "?", "?")


def build_roman_numeral_analyses(
    chord_labels: Sequence[str],
    pattern_ids: Sequence[str],
    patterns: Sequence[Union[PatternDefinition, Mapping[str, Any]]],
    passing_chord_index: Optional[int] = None,
) -> List[str]:
    """Build decorated Roman labels for every retained pattern definition.

    A passing match has five detector segments but only four structural
    anchors. Its passing chord is intentionally omitted from the Roman labels;
    the occurrence's existing passing index and raw chord labels identify it.
    """

    normalized_patterns = {
        pattern.id if isinstance(pattern, PatternDefinition) else str(pattern["id"]): pattern
        if isinstance(pattern, PatternDefinition)
        else PatternDefinition.from_mapping(pattern)
        for pattern in patterns
    }
    if passing_chord_index is not None and len(chord_labels) == 5:
        anchor_positions = [position for position in range(len(chord_labels)) if position != passing_chord_index]
    else:
        anchor_positions = list(range(min(4, len(chord_labels))))
    parsed_anchors = [parse_chord_label(str(chord_labels[position])) for position in anchor_positions]
    analyses: List[str] = []
    for pattern_id in pattern_ids:
        pattern = normalized_patterns.get(str(pattern_id))
        if pattern is None:
            continue
        numerals = _pattern_roman_numerals(pattern)
        labels = [
            format_roman_numeral(numeral, chord)
            if chord is not None
            else numeral
            for numeral, chord in zip(numerals, parsed_anchors)
        ]
        analyses.append(" → ".join(labels))
    return analyses


def _passing_rule_accepts(
    rule: PassingRule,
    identities: Sequence[Mapping[str, Any]],
    passing_chord_index: int,
) -> bool:
    durations = [float(value["endSeconds"]) - float(value["startSeconds"]) for value in identities]
    passing_duration = durations[passing_chord_index]
    return (
        passing_duration <= rule.max_duration_seconds
        and passing_duration <= durations[passing_chord_index - 1] * rule.max_adjacent_duration_ratio
        and passing_duration <= durations[passing_chord_index + 1] * rule.max_adjacent_duration_ratio
    )


def match_patterns(
    song_id: str,
    segments: Sequence[Mapping[str, Any]],
    patterns: Sequence[Union[PatternDefinition, Mapping[str, Any]]],
    quality_sets: Mapping[str, Iterable[str]],
    duration_seconds: Optional[float],
    passing_rule: Optional[Union[PassingRule, Mapping[str, Any]]] = None,
) -> List[Dict[str, Any]]:
    """Match exact and eligible passing windows and deduplicate definitions."""

    normalized_patterns = [
        pattern if isinstance(pattern, PatternDefinition) else PatternDefinition.from_mapping(pattern)
        for pattern in patterns
    ]
    normalized_passing_rule = (
        passing_rule
        if isinstance(passing_rule, PassingRule) or passing_rule is None
        else PassingRule.from_mapping(passing_rule)
    )
    occurrences: Dict[Tuple[Tuple[int, ...], Optional[int]], Dict[str, Any]] = {}

    for start_position in range(0, max(0, len(segments) - 3)):
        window = segments[start_position : start_position + 4]
        parsed_window = _parse_window(window, start_position)
        if parsed_window is None:
            continue
        indices, identities, parsed = parsed_window
        structural_pattern_ids = _matching_patterns(parsed, normalized_patterns, quality_sets)
        if not structural_pattern_ids:
            continue
        exact_start = identities[0]["startSeconds"]
        exact_end = identities[-1]["endSeconds"]
        playback_start, playback_end = _clamp_bounds(exact_start, exact_end, duration_seconds)
        occurrences[(indices, None)] = {
            "id": stable_occurrence_id(song_id, window, indices),
            "segmentIndices": list(indices),
            "exactStartSeconds": exact_start,
            "exactEndSeconds": exact_end,
            "playbackStartSeconds": playback_start,
            "playbackEndSeconds": playback_end,
            "chordLabels": [identity["label"] for identity in identities],
            "chordBounds": _chord_bounds(identities),
            "patternIds": structural_pattern_ids,
            "romanNumeralAnalyses": build_roman_numeral_analyses(
                [identity["label"] for identity in identities],
                structural_pattern_ids,
                normalized_patterns,
            ),
            "passingChordIndex": None,
            "provenance": "automatic",
            "note": None,
        }

    if normalized_passing_rule is not None:
        for start_position in range(0, max(0, len(segments) - 4)):
            window = segments[start_position : start_position + 5]
            parsed_window = _parse_window(window, start_position)
            if parsed_window is None:
                continue
            indices, identities, parsed = parsed_window
            for passing_chord_index in (1, 2, 3):
                anchors = parsed[:passing_chord_index] + parsed[passing_chord_index + 1 :]
                structural_pattern_ids = _matching_patterns(anchors, normalized_patterns, quality_sets)
                if not structural_pattern_ids:
                    continue
                if not _passing_rule_accepts(normalized_passing_rule, identities, passing_chord_index):
                    continue
                exact_start = identities[0]["startSeconds"]
                exact_end = identities[-1]["endSeconds"]
                playback_start, playback_end = _clamp_bounds(exact_start, exact_end, duration_seconds)
                occurrences[(indices, passing_chord_index)] = {
                    "id": stable_passing_occurrence_id(song_id, window, passing_chord_index, indices),
                    "segmentIndices": list(indices),
                    "exactStartSeconds": exact_start,
                    "exactEndSeconds": exact_end,
                    "playbackStartSeconds": playback_start,
                    "playbackEndSeconds": playback_end,
                    "chordLabels": [identity["label"] for identity in identities],
                    "chordBounds": _chord_bounds(identities),
                    "patternIds": structural_pattern_ids,
                    "romanNumeralAnalyses": build_roman_numeral_analyses(
                        [identity["label"] for identity in identities],
                        structural_pattern_ids,
                        normalized_patterns,
                        passing_chord_index,
                    ),
                    "passingChordIndex": passing_chord_index,
                    "provenance": "automatic",
                    "note": None,
                }

    return sorted(
        occurrences.values(),
        key=lambda value: (value["exactStartSeconds"], value["exactEndSeconds"], value["id"]),
    )


def _manual_occurrence_id(
    song_id: str,
    value: Mapping[str, Any],
    position: int,
    segments: Optional[Sequence[Mapping[str, Any]]] = None,
    indices: Optional[Sequence[int]] = None,
    passing_chord_index: Optional[int] = None,
) -> str:
    if value.get("id"):
        return str(value["id"])
    if segments is not None and indices is not None:
        identity = [
            {**_segment_identity(segment, int(index)), "index": int(index)}
            for index, segment in zip(indices, segments)
        ]
        seed_value: Dict[str, Any] = {"songId": str(song_id), "segments": identity}
        if passing_chord_index is not None:
            seed_value["passingChordIndex"] = passing_chord_index
        seed: Mapping[str, Any] = seed_value
    else:
        seed = {"songId": song_id, "position": position, "override": value}
    digest = hashlib.sha256(
        json.dumps(seed, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()[:16]
    return f"rr-{_safe_song_id(song_id)}-manual-{digest}"


def apply_overrides(
    song_id: str,
    segments: Sequence[Mapping[str, Any]],
    automatic_occurrences: Sequence[Mapping[str, Any]],
    override_payload: Mapping[str, Any],
    pattern_ids: Optional[Iterable[Union[str, PatternDefinition]]] = None,
    duration_seconds: Optional[float] = None,
    passing_rule: Optional[Union[PassingRule, Mapping[str, Any]]] = None,
) -> List[Dict[str, Any]]:
    """Apply documented four- or five-segment corrections after automatic matching."""

    songs_overrides = override_payload.get("songs", {})
    song_overrides = songs_overrides.get(song_id, {}) if isinstance(songs_overrides, Mapping) else {}
    if not song_overrides and song_id in override_payload and isinstance(override_payload[song_id], Mapping):
        song_overrides = override_payload[song_id]
    excluded = {str(value) for value in song_overrides.get("excludeOccurrenceIds", [])}
    occurrences = [dict(value) for value in automatic_occurrences if str(value.get("id")) not in excluded]
    known_pattern_ids = None if pattern_ids is None else {
        value.id if isinstance(value, PatternDefinition) else str(value) for value in pattern_ids
    }
    normalized_passing_rule = (
        passing_rule
        if isinstance(passing_rule, PassingRule) or passing_rule is None
        else PassingRule.from_mapping(passing_rule)
    )
    segment_by_index = {int(segment.get("index", position)): segment for position, segment in enumerate(segments)}

    for position, value in enumerate(song_overrides.get("addOccurrences", [])):
        allowed_fields = {
            "id", "segmentIndices", "exactStartSeconds", "exactEndSeconds",
            "playbackStartSeconds", "playbackEndSeconds", "chordLabels",
            "patternIds", "passingChordIndex", "note",
        }
        if set(value) - allowed_fields:
            raise ValueError(f"Manual override {song_id}[{position}] has unexpected fields")
        note = str(value.get("note", "")).strip()
        if not note:
            raise ValueError(f"Manual override {song_id}[{position}] must include a non-empty note")
        raw_indices = value.get("segmentIndices")
        if not isinstance(raw_indices, list) or len(raw_indices) not in (4, 5):
            raise ValueError(f"Manual override {song_id}[{position}] must reference four or five raw segments")
        try:
            indices = [int(index) for index in raw_indices]
        except (TypeError, ValueError) as error:
            raise ValueError(f"Manual override {song_id}[{position}] has non-integer segment indices") from error
        if indices != list(range(indices[0], indices[0] + len(indices))):
            raise ValueError(f"Manual override {song_id}[{position}] must reference consecutive raw segments")
        if any(index not in segment_by_index for index in indices):
            raise ValueError(f"Manual override {song_id}[{position}] references an unknown raw segment")
        labels = value.get("chordLabels")
        if not isinstance(labels, list) or len(labels) != len(indices) or not all(str(label).strip() for label in labels):
            raise ValueError(f"Manual override {song_id}[{position}] must include one chord label per segment")

        passing_value = value.get("passingChordIndex")
        if len(indices) == 4:
            if passing_value is not None:
                raise ValueError(f"Manual override {song_id}[{position}] cannot mark a passing chord in four segments")
            passing_chord_index = None
        else:
            try:
                passing_chord_index = int(passing_value)
            except (TypeError, ValueError) as error:
                raise ValueError(f"Manual override {song_id}[{position}] must identify an internal passing chord") from error
            if passing_chord_index not in (1, 2, 3):
                raise ValueError(f"Manual override {song_id}[{position}] must identify an internal passing chord")
            if parse_chord_label(str(labels[passing_chord_index])) is None:
                raise ValueError(f"Manual override {song_id}[{position}] has an unparseable passing chord")

        manual_pattern_ids = sorted({str(pattern_id) for pattern_id in value.get("patternIds", [])})
        if not manual_pattern_ids:
            raise ValueError(f"Manual override {song_id}[{position}] must include at least one pattern ID")
        unknown_patterns = set(manual_pattern_ids) - known_pattern_ids if known_pattern_ids is not None else set()
        if unknown_patterns:
            raise ValueError(f"Manual override {song_id}[{position}] has unknown patterns: {sorted(unknown_patterns)}")

        referenced = [segment_by_index[index] for index in indices]
        identities = []
        previous_end = -1.0
        try:
            for index, reference in zip(indices, referenced):
                identity = _segment_identity(reference, index)
                start = identity["startSeconds"]
                end = identity["endSeconds"]
                if (
                    not math.isfinite(start)
                    or not math.isfinite(end)
                    or start < 0
                    or end <= start
                    or start < previous_end
                ):
                    raise ValueError
                identities.append(identity)
                previous_end = end
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError(
                f"Manual override {song_id}[{position}] references invalid or unordered raw segments"
            ) from error
        if passing_chord_index is not None:
            if normalized_passing_rule is None:
                raise ValueError(f"Manual override {song_id}[{position}] requires a global passing rule")
            if not _passing_rule_accepts(normalized_passing_rule, identities, passing_chord_index):
                raise ValueError(f"Manual override {song_id}[{position}] violates the global passing rule")

        expected_exact_start = identities[0]["startSeconds"]
        expected_exact_end = identities[-1]["endSeconds"]
        exact_start = float(value.get("exactStartSeconds", expected_exact_start))
        exact_end = float(value.get("exactEndSeconds", expected_exact_end))
        if not math.isfinite(exact_start) or not math.isfinite(exact_end) or exact_start < 0 or exact_end <= exact_start:
            raise ValueError(f"Manual override {song_id}[{position}] has invalid exact bounds")
        if duration_seconds is not None and duration_seconds > 0 and exact_end > duration_seconds:
            raise ValueError(f"Manual override {song_id}[{position}] extends past the recording")
        if abs(exact_start - expected_exact_start) > 1e-6 or abs(exact_end - expected_exact_end) > 1e-6:
            raise ValueError(f"Manual override {song_id}[{position}] must use exact raw-segment bounds")
        playback_start, playback_end = _clamp_bounds(exact_start, exact_end, duration_seconds)
        if "playbackStartSeconds" in value and abs(float(value["playbackStartSeconds"]) - playback_start) > 1e-6:
            raise ValueError(f"Manual override {song_id}[{position}] must use the 0.5 second playback padding")
        if "playbackEndSeconds" in value and abs(float(value["playbackEndSeconds"]) - playback_end) > 1e-6:
            raise ValueError(f"Manual override {song_id}[{position}] must use the 0.5 second playback padding")
        if playback_end < playback_start:
            raise ValueError(f"Manual override {song_id}[{position}] has invalid playback bounds")

        manual = {
            "id": _manual_occurrence_id(
                song_id, value, position, referenced, indices, passing_chord_index
            ),
            "segmentIndices": indices,
            "exactStartSeconds": exact_start,
            "exactEndSeconds": exact_end,
            "playbackStartSeconds": playback_start,
            "playbackEndSeconds": playback_end,
            "chordLabels": [str(label) for label in labels],
            "chordBounds": _chord_bounds(identities),
            "patternIds": manual_pattern_ids,
            "passingChordIndex": passing_chord_index,
            "provenance": "manual",
            "note": note,
        }
        if any(str(existing.get("id")) == manual["id"] for existing in occurrences):
            raise ValueError(f"Manual override {song_id}[{position}] duplicates occurrence ID {manual['id']}")
        occurrences.append(manual)

    return sorted(
        occurrences,
        key=lambda value: (float(value["exactStartSeconds"]), float(value["exactEndSeconds"]), str(value["id"])),
    )


find_occurrences = match_patterns
find_matches = match_patterns
apply_manual_overrides = apply_overrides


__all__ = [
    "PADDING_SECONDS",
    "PassingRule",
    "PatternDefinition",
    "apply_overrides",
    "apply_manual_overrides",
    "build_roman_numeral_analyses",
    "find_matches",
    "find_occurrences",
    "load_pattern_definitions",
    "load_passing_rule",
    "match_patterns",
    "stable_occurrence_id",
    "stable_passing_occurrence_id",
]

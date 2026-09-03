from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

SCRIPT_DIR = Path(__file__).resolve().parents[1]
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from royal_road.chords import parse_chord_label  # noqa: E402
from royal_road.io_utils import atomic_write_json, read_json  # noqa: E402
from royal_road.matching import (  # noqa: E402
    PassingRule,
    PatternDefinition,
    apply_overrides,
    build_roman_numeral_analyses,
    match_patterns,
    stable_occurrence_id,
    stable_passing_occurrence_id,
)


PATTERN_MAJOR = PatternDefinition(
    "major", "IV–V–iii–vi", (0, 2, 11, 4), ("major", "dominant", "minor", "minor")
)
PATTERN_MINOR = PatternDefinition(
    "minor", "iv–v–III–VI", (0, 2, 10, 3), ("minor", "minor", "major", "major")
)
PATTERN_ALTERNATIVE = PatternDefinition(
    "alternative", "IV–V–III–vi", (0, 2, 11, 4), ("major", "dominant", "dominant", "minor")
)
QUALITY_SETS = {
    "major": ["maj", "maj7"],
    "dominant": ["maj", "maj7", "7", "9"],
    "minor": ["min", "min7", "min9"],
}
PASSING_RULE = PassingRule(2.0, 0.5)


def timeline(labels, start=1.0, durations=None, indices=None):
    durations = durations or [2.0] * len(labels)
    indices = indices or list(range(len(labels)))
    result = []
    cursor = start
    for index, label, duration in zip(indices, labels, durations):
        result.append({"index": index, "startSeconds": cursor, "endSeconds": cursor + duration, "label": label})
        cursor += duration
    return result


class MatchingTests(unittest.TestCase):
    def test_enharmonic_roots_inversions_and_extensions_match_both_forms(self):
        sharp = parse_chord_label("C#:maj7/G#")
        flat = parse_chord_label("Db:maj7/Ab")
        self.assertIsNotNone(sharp)
        self.assertEqual(sharp.root_pitch_class, flat.root_pitch_class)
        self.assertEqual(sharp.original_label, "C#:maj7/G#")
        self.assertEqual(sharp.bass_degree, "5")
        seventh_inversion = parse_chord_label("C:7/3")
        self.assertIsNotNone(seventh_inversion)
        self.assertEqual((seventh_inversion.quality, seventh_inversion.bass_degree), ("7", "3"))

        major = timeline(["Db:maj7/Ab", "Eb:9", "C:min9", "F:min7"])
        minor = timeline(["F#:min7/C#", "G#:min9", "E:maj7", "A:maj"])
        self.assertEqual(match_patterns("major", major, [PATTERN_MAJOR, PATTERN_MINOR], QUALITY_SETS, 30)[0]["patternIds"], ["major"])
        self.assertEqual(match_patterns("minor", minor, [PATTERN_MAJOR, PATTERN_MINOR], QUALITY_SETS, 30)[0]["patternIds"], ["minor"])
        self.assertEqual(match_patterns("major", major, [PATTERN_MAJOR], QUALITY_SETS, 30)[0]["chordLabels"], ["Db:maj7/Ab", "Eb:9", "C:min9", "F:min7"])
        self.assertEqual(
            build_roman_numeral_analyses(
                ["Db:maj7/Ab", "Eb:9", "C:min9", "F:min7"],
                ["major"],
                [PATTERN_MAJOR],
            ),
            ["IVmaj7/5 → V9 → iii9 → vi7"],
        )

    def test_roman_numeral_analyses_omit_only_the_passing_chord(self):
        analyses = build_roman_numeral_analyses(
            ["C:maj", "F#:dim7", "D:7", "B:min7", "E:min"],
            ["major"],
            [PATTERN_MAJOR],
            passing_chord_index=1,
        )
        self.assertEqual(analyses, ["IV → V7 → iii7 → vi"])

    def test_only_retained_progressions_match(self):
        # VI–VII–v–i is structurally identical to IV–V–iii–vi when no key is
        # inferred, so the contract distinction is the retained pattern ID.
        discarded_minor = timeline(["C:maj", "D:maj", "B:min", "E:min"])
        discarded_substitution = timeline(["C:maj", "D:7", "B:maj7", "E:min"])
        occurrence = match_patterns("song", discarded_minor, [PATTERN_MAJOR, PATTERN_MINOR], QUALITY_SETS, 30)[0]
        self.assertEqual(occurrence["patternIds"], ["major"])
        self.assertNotIn("vi-vii-v-i", occurrence["patternIds"])
        alternative = match_patterns(
            "song", discarded_substitution, [PATTERN_MAJOR, PATTERN_ALTERNATIVE, PATTERN_MINOR], QUALITY_SETS, 30
        )
        self.assertEqual(alternative[0]["patternIds"], ["alternative"])

    def test_surrounding_context_neither_accepts_nor_rejects_structural_matches(self):
        with_major_context = timeline(["C:maj", "G:7", "C:maj", "N", "F:min", "G:min", "Eb:maj", "Ab:maj", "N"])
        with_minor_context = timeline(["E:min", "B:7", "E:min", "N", "F:maj", "G:7", "E:min", "A:min", "N"])
        minor_matches = match_patterns("song", with_major_context, [PATTERN_MAJOR, PATTERN_MINOR], QUALITY_SETS, 40)
        major_matches = match_patterns("song", with_minor_context, [PATTERN_MAJOR, PATTERN_MINOR], QUALITY_SETS, 40)
        self.assertEqual([match["patternIds"] for match in minor_matches], [["minor"]])
        self.assertEqual([match["patternIds"] for match in major_matches], [["major"]])

    def test_modulations_are_matched_by_relative_roots(self):
        segments = timeline([
            "C:maj", "D:7", "B:min", "E:min", "N",
            "Gb:maj", "Ab:7", "F:min", "Bb:min",
        ])
        matches = match_patterns("song", segments, [PATTERN_MAJOR], QUALITY_SETS, 30)
        self.assertEqual([match["segmentIndices"] for match in matches], [[0, 1, 2, 3], [5, 6, 7, 8]])

    def test_passing_matches_work_in_all_internal_gaps_for_both_forms(self):
        for anchors, pattern in (
            (["C:maj", "D:7", "B:min", "E:min"], PATTERN_MAJOR),
            (["C:min", "D:min", "Bb:maj", "Eb:maj"], PATTERN_MINOR),
        ):
            for passing_index in (1, 2, 3):
                labels = list(anchors)
                labels.insert(passing_index, "F#:dim7")
                durations = [2.0] * 5
                durations[passing_index] = 1.0
                occurrence = match_patterns(
                    "song", timeline(labels, durations=durations), [pattern], QUALITY_SETS, 20, PASSING_RULE
                )[0]
                self.assertEqual(occurrence["passingChordIndex"], passing_index)
                self.assertEqual(len(occurrence["chordLabels"]), 5)

    def test_global_passing_limits_are_inclusive(self):
        labels = ["C:maj", "F#:sus4", "D:7", "B:min", "E:min"]
        boundary = timeline(labels, durations=[4, 2, 4, 2, 2])
        self.assertEqual(len(match_patterns("song", boundary, [PATTERN_MAJOR], QUALITY_SETS, 20, PASSING_RULE)), 1)
        rejected = (
            timeline(labels, durations=[5, 2.01, 5, 2, 2]),
            timeline(labels, durations=[2, 1.01, 2, 2, 2]),
            timeline(["C:maj", "N", "D:7", "B:min", "E:min"], durations=[2, 1, 2, 2, 2]),
            timeline(labels, durations=[2, 1, 2, 2, 2], indices=[0, 1, 3, 4, 5]),
        )
        for segments in rejected:
            self.assertEqual(match_patterns("song", segments, [PATTERN_MAJOR], QUALITY_SETS, 20, PASSING_RULE), [])

    def test_deduplication_stable_ids_and_bounds(self):
        duplicate = PatternDefinition("duplicate", "duplicate", PATTERN_MAJOR.root_offsets, PATTERN_MAJOR.qualities)
        segments = timeline(["C:maj", "D:7", "B:min", "E:min"], start=0.2)
        occurrence = match_patterns("song", segments, [PATTERN_MAJOR, duplicate], QUALITY_SETS, 8)[0]
        self.assertEqual(occurrence["patternIds"], ["duplicate", "major"])
        self.assertEqual(
            occurrence["chordBounds"],
            [
                {"startSeconds": 0.2, "endSeconds": 2.2},
                {"startSeconds": 2.2, "endSeconds": 4.2},
                {"startSeconds": 4.2, "endSeconds": 6.2},
                {"startSeconds": 6.2, "endSeconds": 8.2},
            ],
        )
        self.assertEqual((occurrence["playbackStartSeconds"], occurrence["playbackEndSeconds"]), (0.0, 8))
        self.assertEqual(occurrence["id"], stable_occurrence_id("song", segments))
        unchanged_id_segments = timeline(["C:maj", "D:7", "B:min", "E:min"])
        self.assertEqual(stable_occurrence_id("song", unchanged_id_segments), "rr-song-0d01439fcb03de4b")

        passing = timeline(["C:maj", "F#:dim", "D:7", "B:min", "E:min"], durations=[2, 1, 2, 2, 2])
        passing_occurrence = match_patterns("song", passing, [PATTERN_MAJOR], QUALITY_SETS, 20, PASSING_RULE)[0]
        self.assertEqual(passing_occurrence["id"], stable_passing_occurrence_id("song", passing, 1))
        self.assertNotEqual(stable_passing_occurrence_id("song", passing, 1), stable_passing_occurrence_id("song", passing, 2))

    def test_overrides_support_four_and_eligible_five_segment_corrections(self):
        exact_segments = timeline(["C:maj", "D:7", "B:min", "E:min"])
        automatic = match_patterns("song", exact_segments, [PATTERN_MAJOR], QUALITY_SETS, 30)
        override = {"songs": {"song": {"excludeOccurrenceIds": [automatic[0]["id"]], "addOccurrences": [{
            "id": "manual-1", "segmentIndices": [0, 1, 2, 3],
            "chordLabels": ["C:maj", "D:7", "B:min", "E:min"],
            "patternIds": ["major"], "note": "Reviewed correction.",
        }]}}}
        result = apply_overrides("song", exact_segments, automatic, override, ["major"], 30, PASSING_RULE)
        self.assertEqual([value["id"] for value in result], ["manual-1"])
        self.assertNotIn("profileIds", result[0])

        passing_segments = timeline(["C:maj", "F#:dim", "D:7", "B:min", "E:min"], durations=[2, 1, 2, 2, 2])
        addition = {
            "segmentIndices": [0, 1, 2, 3, 4],
            "chordLabels": ["C:maj", "F#:dim", "D:7", "B:min", "E:min"],
            "patternIds": ["major"], "passingChordIndex": 1, "note": "Reviewed passing interpretation.",
        }
        result = apply_overrides("song", passing_segments, [], {"songs": {"song": {"addOccurrences": [addition]}}}, ["major"], 20, PASSING_RULE)
        self.assertEqual(result[0]["passingChordIndex"], 1)
        for change in ({"patternIds": ["unknown"]}, {"passingChordIndex": 0}):
            with self.assertRaises(ValueError):
                apply_overrides("song", passing_segments, [], {"songs": {"song": {"addOccurrences": [{**addition, **change}]}}}, ["major"], 20, PASSING_RULE)
        with self.assertRaisesRegex(ValueError, "unexpected fields"):
            apply_overrides(
                "song", passing_segments, [],
                {"songs": {"song": {"addOccurrences": [{**addition, "profileIds": ["inclusive"]}]}}},
                ["major"], 20, PASSING_RULE,
            )

    def test_atomic_json_write_is_readable_and_replaces_existing_files(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "nested" / "record.json"
            atomic_write_json(path, {"version": 1, "unicode": "μ's"})
            atomic_write_json(path, {"version": 2, "unicode": "μ's"})
            self.assertEqual(read_json(path), {"version": 2, "unicode": "μ's"})

    def test_atomic_json_write_retries_a_transient_windows_lock(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "record.json"
            permission_error = PermissionError(5, "access denied")
            with patch("royal_road.io_utils.os.name", "nt"), patch(
                "royal_road.io_utils.os.replace", side_effect=[permission_error, None]
            ) as replace:
                atomic_write_json(path, {"status": "ok"})
            self.assertEqual(replace.call_count, 2)


if __name__ == "__main__":
    unittest.main()

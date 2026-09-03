import json
import io
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest.mock import Mock, patch

SCRIPT_DIR = Path(__file__).resolve().parents[1]
ROOT_DIR = SCRIPT_DIR.parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from royal_road.detector import (  # noqa: E402
    DETECTOR_REVISION,
    DetectorError,
    normalize_detector_segments,
    parse_detector_output,
    run_detector,
    validate_detector_checkout,
)
from royal_road.metadata import parse_source_catalog  # noqa: E402
from royal_road.pipeline import compile_catalog  # noqa: E402
import compile_catalog as compile_cli  # noqa: E402
from validate_data import _validate_catalog_counts  # noqa: E402


class PipelineTests(unittest.TestCase):
    def test_detector_accepts_lab_and_json_output(self):
        self.assertEqual(parse_detector_output("0 2 C:maj\n2 4 D:7\n")[1]["label"], "D:7")
        self.assertEqual(normalize_detector_segments({"segments": [{"start": 0, "end": 1, "chord": "N"}]}), [{"index": 0, "startSeconds": 0.0, "endSeconds": 1.0, "label": "N"}])

    def test_direct_detector_normalizes_rows_and_keeps_stdout_machine_readable(self):
        def recognize(audio_path):
            print(f"Inference on {audio_path}")
            return [[0, 2, "C:maj"], [2, 4, "D:7"]]

        stdout = io.StringIO()
        stderr = io.StringIO()
        with patch("royal_road.detector._load_chord_recognition", return_value=recognize):
            with redirect_stdout(stdout), redirect_stderr(stderr):
                segments = run_detector(Path("song.ogg"))
        self.assertEqual(stdout.getvalue(), "")
        self.assertIn("Inference on song.ogg", stderr.getvalue())
        self.assertEqual(segments[1], {"index": 1, "startSeconds": 2.0, "endSeconds": 4.0, "label": "D:7"})

    def test_detector_checkout_reports_missing_and_wrong_submodule(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            with self.assertRaisesRegex(DetectorError, "submodule is not initialized"):
                validate_detector_checkout(directory)
            (directory / "__init__.py").write_text("", encoding="utf-8")
            result = Mock(returncode=0, stdout="0" * 40 + "\n", stderr="")
            with patch("royal_road.detector.subprocess.run", return_value=result):
                with self.assertRaisesRegex(DetectorError, f"expected {DETECTOR_REVISION}"):
                    validate_detector_checkout(directory)

    def test_source_join_resolves_artist_and_series_names_without_dropping_songs(self):
        songs = [{"id": "1", "name": "曲", "phoneticName": "きょく", "englishName": "Song", "artists": [{"id": "7"}], "seriesIds": ["2"], "wikiAudioUrl": "https://wiki/audio.ogg"}]
        artists = [{"id": "7", "name": "μ's", "englishName": "Muse"}]
        series = [{"id": "2", "name": "ラブライブ！"}]
        result = parse_source_catalog(songs, artists, series)
        self.assertEqual(result[0]["artistNames"], ["μ's"])
        self.assertEqual(result[0]["artistAliases"], ["Muse"])
        self.assertEqual(result[0]["seriesNames"], ["ラブライブ！"])
        self.assertEqual(result[0]["seriesAliases"], [])
        self.assertEqual(result[0]["titles"]["phonetic"], "きょく")

    def test_compiler_keeps_unavailable_and_failed_rows_and_recomputes_metrics(self):
        pattern_payload = json.loads((ROOT_DIR / "data" / "patterns.json").read_text(encoding="utf-8"))
        override_payload = {"schemaVersion": "2.0.0", "songs": {}}
        source_songs = [
            {"id": "good", "titles": {"ja": "Good"}, "artistNames": [], "seriesNames": [], "audioUrl": "https://wiki/g.ogg"},
            {"id": "unavailable", "titles": {"ja": "Unavailable"}, "artistNames": [], "seriesNames": [], "audioUrl": None},
            {"id": "failed", "titles": {"ja": "Failed"}, "artistNames": [], "seriesNames": [], "audioUrl": "https://wiki/f.ogg"},
        ]
        raw = {
            "good": {
                "schemaVersion": "2.0.0", "songId": "good", "durationSeconds": 30,
                "segments": [
                    {"index": 0, "startSeconds": 1, "endSeconds": 2, "label": "C:maj"},
                    {"index": 1, "startSeconds": 2, "endSeconds": 3, "label": "D:7"},
                    {"index": 2, "startSeconds": 3, "endSeconds": 4, "label": "B:min"},
                    {"index": 3, "startSeconds": 4, "endSeconds": 5, "label": "E:min"},
                ]
            },
        }
        states = {
            "good": {"status": "analyzed", "audioUrl": "https://wiki/g.ogg", "audioSha256": "abc", "analysisVersion": "current", "error": None},
            "unavailable": {"status": "unavailable", "audioUrl": None, "audioSha256": None, "analysisVersion": None, "error": None},
            "failed": {"status": "failed", "audioUrl": "https://wiki/f.ogg", "audioSha256": None, "analysisVersion": None, "error": "detector"},
        }
        catalog = compile_catalog(source_songs, raw, states, pattern_payload, override_payload)
        self.assertEqual([song["status"] for song in catalog["songs"]], ["analyzed", "unavailable", "failed"])
        self.assertEqual(catalog["metrics"], {
            "matchingSongCount": 1, "totalOccurrenceCount": 1, "analyzedSongCount": 1,
            "catalogSongCount": 3, "unavailableSongCount": 1, "failedSongCount": 1,
        })
        self.assertEqual(
            set(catalog),
            {"schemaVersion", "isFixture", "patterns", "metrics", "songs"},
        )
        self.assertEqual(catalog["schemaVersion"], "4.1.0")
        self.assertEqual(catalog["songs"][0]["occurrenceCount"], 1)
        self.assertNotIn("profileIds", catalog["songs"][0]["occurrences"][0])
        self.assertNotIn("segmentIndices", catalog["songs"][0]["occurrences"][0])
        self.assertEqual(
            catalog["songs"][0]["occurrences"][0]["chordBounds"],
            [
                {"startSeconds": 1.0, "endSeconds": 2.0},
                {"startSeconds": 2.0, "endSeconds": 3.0},
                {"startSeconds": 3.0, "endSeconds": 4.0},
                {"startSeconds": 4.0, "endSeconds": 5.0},
            ],
        )
        self.assertEqual(catalog["songs"][0]["occurrences"][0]["passingChordIndex"], None)
        self.assertEqual(
            catalog["songs"][0]["occurrences"][0]["romanNumeralAnalyses"],
            ["IV → V7 → iii → vi"],
        )

        invalid_patterns = json.loads(json.dumps(pattern_payload))
        invalid_patterns["schemaVersion"] = "3.0.0"
        with self.assertRaisesRegex(ValueError, "patterns schemaVersion"):
            compile_catalog(source_songs, raw, states, invalid_patterns, override_payload)
        invalid_patterns = json.loads(json.dumps(pattern_payload))
        invalid_patterns["passingRule"]["maxAdjacentDurationRatio"] = 2
        with self.assertRaisesRegex(ValueError, "adjacent-duration ratio"):
            compile_catalog(source_songs, raw, states, invalid_patterns, override_payload)
        invalid_patterns = json.loads(json.dumps(pattern_payload))
        invalid_patterns["patterns"][0]["mode"] = "major"
        with self.assertRaisesRegex(ValueError, "fields must be"):
            compile_catalog(source_songs, raw, states, invalid_patterns, override_payload)

        invalid_catalog = json.loads(json.dumps(catalog))
        invalid_catalog["songs"][0]["occurrenceCount"] = 99
        invalid_catalog["metrics"]["totalOccurrenceCount"] = 99
        validation_errors = _validate_catalog_counts(invalid_catalog)
        self.assertTrue(any("incorrect occurrence count" in error for error in validation_errors))
        self.assertTrue(any("aggregate status metrics" in error for error in validation_errors))

    def test_compile_cli_can_use_committed_catalog_when_source_cache_is_missing(self):
        fixture_catalog = json.loads((ROOT_DIR / "data" / "catalog.json").read_text(encoding="utf-8"))
        fixture_manifest = json.loads((ROOT_DIR / "data" / "analysis-manifest.json").read_text(encoding="utf-8"))
        commit = fixture_manifest["sourceCommit"]
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            raw_dir = directory / "raw"
            raw_dir.mkdir()
            for raw_path in (ROOT_DIR / "data" / "raw").glob("*.json"):
                shutil.copy2(raw_path, raw_dir / raw_path.name)
            catalog_path = directory / "catalog.json"
            catalog_path.write_text(json.dumps(fixture_catalog, ensure_ascii=False), encoding="utf-8")
            manifest_path = directory / "manifest.json"
            manifest_path.write_text(json.dumps(fixture_manifest, ensure_ascii=False), encoding="utf-8")
            self.assertEqual(compile_cli.main([
                "--source-dir", str(directory / "source-cache-that-is-not-committed"),
                "--source-commit", commit,
                "--raw-dir", str(raw_dir),
                "--manifest", str(manifest_path),
                "--catalog", str(catalog_path),
                "--patterns", str(ROOT_DIR / "data" / "patterns.json"),
                "--overrides", str(ROOT_DIR / "data" / "overrides.json"),
            ]), 0)
            rebuilt = json.loads(catalog_path.read_text(encoding="utf-8"))
            self.assertEqual(rebuilt["metrics"], fixture_catalog["metrics"])
            self.assertEqual(set(json.loads(manifest_path.read_text(encoding="utf-8"))), {"schemaVersion", "sourceCommit", "analysis", "songs"})


if __name__ == "__main__":
    unittest.main()

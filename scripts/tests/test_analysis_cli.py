import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

SCRIPT_DIR = Path(__file__).resolve().parents[1]
ROOT_DIR = SCRIPT_DIR.parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import analyze  # noqa: E402
from royal_road.detector import DetectorError  # noqa: E402
from royal_road.downloader import DownloadError  # noqa: E402
from royal_road.sources import SOURCE_SNAPSHOT_MARKER, local_metadata_snapshot  # noqa: E402
from source_fixtures import write_source  # noqa: E402
from scripts.analyze import _bound_segments_to_duration  # noqa: E402


class AnalysisCliTests(unittest.TestCase):
    def _write_source(self, directory: Path) -> None:
        self.snapshot = write_source(directory)

    def _args(self, directory: Path, mode: str):
        return [
            "--mode", mode,
            "--source-dir", str(directory / "source"),
            "--raw-dir", str(directory / "raw"),
            "--audio-cache", str(directory / "audio"),
            "--manifest", str(directory / "manifest.json"),
            "--catalog", str(directory / "catalog.json"),
            "--patterns", str(ROOT_DIR / "data" / "patterns.json"),
            "--overrides", str(ROOT_DIR / "data" / "overrides.json"),
            "--throttle", "0",
        ]

    def test_cli_uses_pinned_submodule_without_detector_command_option(self):
        parser = analyze.build_parser()
        option_strings = {option for action in parser._actions for option in action.option_strings}
        self.assertNotIn("--detector-command", option_strings)

    def test_partial_source_fails_without_network_or_recognition(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            source = directory / "source"
            self._write_source(source)
            (source / SOURCE_SNAPSHOT_MARKER).unlink()
            with patch.object(analyze, "download_audio") as download:
                self.assertEqual(analyze.main(self._args(directory, "resume")), 2)
                download.assert_not_called()
            with self.assertRaisesRegex(ValueError, "Partial"):
                local_metadata_snapshot(source)

    def test_detector_endpoint_is_bounded_to_recording_duration(self):
        segments = [
            {"index": 0, "startSeconds": 1.0, "endSeconds": 2.0, "label": "C:maj"},
            {"index": 1, "startSeconds": 2.0, "endSeconds": 5.02, "label": "D:7"},
        ]

        bounded = _bound_segments_to_duration(segments, 5.0)

        self.assertEqual(bounded[0], segments[0])
        self.assertEqual(bounded[1]["endSeconds"], 5.0)
        with self.assertRaises(ValueError):
            _bound_segments_to_duration(
                [{"index": 0, "startSeconds": 5.0, "endSeconds": 5.02, "label": "C:maj"}],
                5.0,
            )

    def test_pipeline_publishes_catalog_and_matching_manifest_after_each_song(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            source = directory / "source"
            source.mkdir()
            self._write_source(source)
            segments = [
                {"index": 0, "startSeconds": 1, "endSeconds": 2, "label": "C:maj"},
                {"index": 1, "startSeconds": 2, "endSeconds": 3, "label": "D:7"},
                {"index": 2, "startSeconds": 3, "endSeconds": 4, "label": "B:min"},
                {"index": 3, "startSeconds": 4, "endSeconds": 5, "label": "E:min"},
            ]
            real_atomic_write = analyze.atomic_write_json
            publications = []

            def capture_publications(path, payload):
                if Path(path).name in {"catalog.json", "manifest.json"}:
                    publications.append((Path(path).name, json.loads(json.dumps(payload))))
                real_atomic_write(path, payload)

            with (
                patch.object(analyze, "download_audio", return_value={"audioSha256": "same", "etag": "e", "lastModified": None}),
                patch.object(analyze, "run_detector", return_value=segments),
                patch.object(analyze, "probe_duration", return_value=20.0),
                patch.object(analyze, "atomic_write_json", side_effect=capture_publications),
            ):
                self.assertEqual(analyze.main(self._args(directory, "full")), 0)

            self.assertEqual(
                [name for name, _ in publications],
                ["catalog.json", "manifest.json"] * 3,
            )
            for index in range(0, len(publications), 2):
                manifest = publications[index + 1][1]
                self.assertEqual(manifest["sourceSnapshot"], self.snapshot["snapshotId"])
                self.assertEqual(manifest["analysis"]["module"], "chord_recognition_module")
            self.assertEqual(publications[0][1]["metrics"]["analyzedSongCount"], 1)
            self.assertEqual({song["id"] for song in publications[0][1]["songs"]}, {"1", "2"})
            final_manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(
                set(final_manifest["songs"]["1"]),
                {"status", "audioUrl", "audioSha256", "analysisVersion", "error"},
            )
            self.assertNotIn("etag", final_manifest["songs"]["1"])
            cache_index = json.loads((directory / "audio" / "index.json").read_text(encoding="utf-8"))
            self.assertEqual(cache_index["songs"]["1"]["etag"], "e")

    def test_resume_reuses_existing_record_without_downloading_or_reanalyzing(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            source = directory / "source"
            source.mkdir()
            self._write_source(source)
            segments = [
                {"index": 0, "startSeconds": 1, "endSeconds": 2, "label": "C:maj"},
                {"index": 1, "startSeconds": 2, "endSeconds": 3, "label": "D:7"},
                {"index": 2, "startSeconds": 3, "endSeconds": 4, "label": "B:min"},
                {"index": 3, "startSeconds": 4, "endSeconds": 5, "label": "E:min"},
            ]
            download = unittest.mock.Mock(return_value={"audioSha256": "same", "etag": "e", "lastModified": None})
            detector = unittest.mock.Mock(return_value=segments)
            with patch.object(analyze, "download_audio", download), patch.object(analyze, "run_detector", detector), patch.object(analyze, "probe_duration", return_value=20.0):
                self.assertEqual(analyze.main(self._args(directory, "full")), 0)
                self.assertEqual(detector.call_count, 1)
                self.assertEqual(download.call_count, 1)
                with patch.object(analyze, "atomic_write_json", wraps=analyze.atomic_write_json) as write_json:
                    self.assertEqual(analyze.main(self._args(directory, "resume")), 0)
                written_paths = {Path(call.args[0]) for call in write_json.call_args_list}
                self.assertNotIn(directory / "raw" / "1.json", written_paths)
                self.assertEqual(detector.call_count, 1)
                self.assertEqual(download.call_count, 1)
                download.return_value = {"audioSha256": "changed", "etag": "e2", "lastModified": None}
                self.assertEqual(analyze.main(self._args(directory, "resume")), 0)
                self.assertEqual(detector.call_count, 1)
                self.assertEqual(download.call_count, 1)
            catalog = json.loads((directory / "catalog.json").read_text(encoding="utf-8"))
            self.assertEqual({song["status"] for song in catalog["songs"]}, {"analyzed", "unavailable"})
            self.assertEqual(catalog["metrics"]["catalogSongCount"], 2)

    def test_refresh_failure_retains_only_verified_timeline_for_transient_errors(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            source = directory / "source"
            source.mkdir()
            self._write_source(source)
            segments = [
                {"index": 0, "startSeconds": 1, "endSeconds": 2, "label": "C:maj"},
                {"index": 1, "startSeconds": 2, "endSeconds": 3, "label": "D:7"},
                {"index": 2, "startSeconds": 3, "endSeconds": 4, "label": "B:min"},
                {"index": 3, "startSeconds": 4, "endSeconds": 5, "label": "E:min"},
            ]
            with (
                patch.object(analyze, "download_audio", return_value={"audioSha256": "same", "etag": None, "lastModified": None}),
                patch.object(analyze, "run_detector", return_value=segments),
                patch.object(analyze, "probe_duration", return_value=20.0),
            ):
                self.assertEqual(analyze.main(self._args(directory, "full")), 0)

            transient = Mock(side_effect=DownloadError("temporary outage", transient=True))
            with patch.object(analyze, "download_audio", transient):
                self.assertEqual(analyze.main(self._args(directory, "full")), 0)
            retained = json.loads((directory / "catalog.json").read_text(encoding="utf-8"))
            self.assertEqual(retained["songs"][0]["status"], "analyzed")
            self.assertTrue((directory / "raw" / "1.json").exists())

            permanent = Mock(side_effect=DownloadError("permanent 404", transient=False))
            with patch.object(analyze, "download_audio", permanent):
                self.assertEqual(analyze.main(self._args(directory, "full")), 0)
            failed = json.loads((directory / "catalog.json").read_text(encoding="utf-8"))
            self.assertEqual(failed["songs"][0]["status"], "failed")
            self.assertFalse((directory / "raw" / "1.json").exists())

    def test_changed_analysis_version_reanalyzes_unchanged_audio(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            source = directory / "source"
            source.mkdir()
            self._write_source(source)
            segments = [
                {"index": 0, "startSeconds": 1, "endSeconds": 2, "label": "C:maj"},
                {"index": 1, "startSeconds": 2, "endSeconds": 3, "label": "D:7"},
                {"index": 2, "startSeconds": 3, "endSeconds": 4, "label": "B:min"},
                {"index": 3, "startSeconds": 4, "endSeconds": 5, "label": "E:min"},
            ]
            detector = unittest.mock.Mock(return_value=segments)
            with (
                patch.object(analyze, "download_audio", return_value={"audioSha256": "same", "etag": None, "lastModified": None}),
                patch.object(analyze, "run_detector", detector),
                patch.object(analyze, "probe_duration", return_value=20.0),
            ):
                self.assertEqual(analyze.main(self._args(directory, "full")), 0)
                with patch.object(analyze, "analysis_version", return_value="new-analysis-version"):
                    self.assertEqual(analyze.main(self._args(directory, "resume")), 0)
            self.assertEqual(detector.call_count, 2)

    def test_retry_failed_reuses_explicit_failed_status_then_recovers(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            source = directory / "source"
            source.mkdir()
            self._write_source(source)
            download = unittest.mock.Mock(return_value={"audioSha256": "retry", "etag": None, "lastModified": None})
            detector = unittest.mock.Mock(side_effect=[DetectorError("temporary detector failure"), [{"index": 0, "startSeconds": 1, "endSeconds": 2, "label": "C:maj"}, {"index": 1, "startSeconds": 2, "endSeconds": 3, "label": "D:7"}, {"index": 2, "startSeconds": 3, "endSeconds": 4, "label": "B:min"}, {"index": 3, "startSeconds": 4, "endSeconds": 5, "label": "E:min"}]])
            with patch.object(analyze, "download_audio", download), patch.object(analyze, "run_detector", detector), patch.object(analyze, "probe_duration", return_value=20.0):
                self.assertEqual(analyze.main(self._args(directory, "full")), 0)
                first = json.loads((directory / "catalog.json").read_text(encoding="utf-8"))
                self.assertEqual(first["songs"][0]["status"], "failed")
                self.assertEqual(analyze.main(self._args(directory, "retry-failed")), 0)
            second = json.loads((directory / "catalog.json").read_text(encoding="utf-8"))
            self.assertEqual(second["songs"][0]["status"], "analyzed")


if __name__ == "__main__":
    unittest.main()

import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

SCRIPT_DIR = Path(__file__).resolve().parents[1]
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from royal_road.detector import DETECTOR_REVISION, DetectorError, validate_detector_checkout  # noqa: E402
from royal_road.metadata import parse_source_catalog  # noqa: E402
from royal_road.sources import (  # noqa: E402
    SOURCE_FILES,
    SOURCE_SNAPSHOT_MARKER,
    SOURCE_SNAPSHOT_SCHEMA_VERSION,
    fetch_metadata_snapshot,
    local_metadata_snapshot,
)
from validate_data import _load_raw  # noqa: E402


class ReviewFixTests(unittest.TestCase):
    def test_source_cache_marker_records_commit_and_rejects_mixed_files(self):
        bodies = {filename: b"[]" for filename in SOURCE_FILES}

        def request(url, headers=None):
            return bodies[url.rsplit("/", 1)[-1]], {}

        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            with patch("royal_road.sources._request_bytes", side_effect=request):
                snapshot = fetch_metadata_snapshot(directory, "a" * 40)

            self.assertEqual(snapshot["commit"], "a" * 40)
            marker = json.loads((directory / SOURCE_SNAPSHOT_MARKER).read_text(encoding="utf-8"))
            self.assertEqual(marker["schemaVersion"], SOURCE_SNAPSHOT_SCHEMA_VERSION)
            self.assertEqual(marker["commit"], "a" * 40)
            self.assertEqual(
                marker["files"]["song-info.json"],
                hashlib.sha256(b"[]").hexdigest(),
            )
            self.assertEqual(local_metadata_snapshot(directory, "a" * 40)["commit"], "a" * 40)

            (directory / "song-info.json").write_bytes(b"[{}]")
            with self.assertRaisesRegex(ValueError, "does not match"):
                local_metadata_snapshot(directory, "a" * 40)
            with self.assertRaisesRegex(ValueError, "belongs to commit"):
                local_metadata_snapshot(directory, "b" * 40)

    def test_aliases_keep_empty_intermediate_slots(self):
        result = parse_source_catalog(
            [{"id": "song", "name": "Song", "artists": ["first", "second"]}],
            [
                {"id": "first", "name": "First"},
                {"id": "second", "name": "Second", "englishName": "Second English", "romanizedName": "Second Alt"},
            ],
            [],
        )
        self.assertEqual(result[0]["artistNames"], ["First", "Second"])
        self.assertEqual(result[0]["artistAliases"], ["", "Second English"])

    def test_raw_loader_reports_invalid_duplicate_and_path_mismatch_files(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            (directory / "invalid.json").write_text("{", encoding="utf-8")
            (directory / "scalar.json").write_text("[]", encoding="utf-8")
            (directory / "missing-id.json").write_text("{}", encoding="utf-8")
            payload = {"songId": "one", "segments": []}
            (directory / "one.json").write_text(json.dumps(payload), encoding="utf-8")
            (directory / "wrong-name.json").write_text(json.dumps(payload), encoding="utf-8")
            diagnostics = []

            loaded = _load_raw(directory, diagnostics)

            self.assertEqual(set(loaded), {"one"})
            self.assertTrue(any("unreadable" in error for error in diagnostics))
            self.assertTrue(any("JSON object" in error for error in diagnostics))
            self.assertTrue(any("missing a string songId" in error for error in diagnostics))
            self.assertTrue(any("path mismatch" in error for error in diagnostics))
            self.assertTrue(any("duplicate" in error for error in diagnostics))

    def test_detector_rejects_a_dirty_pinned_checkout(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            (directory / "__init__.py").write_text("", encoding="utf-8")
            revision = Mock(returncode=0, stdout=f"{DETECTOR_REVISION}\n", stderr="")
            dirty = Mock(returncode=0, stdout=" M detector.py\n", stderr="")
            with patch("royal_road.detector.subprocess.run", side_effect=[revision, dirty]):
                with self.assertRaisesRegex(DetectorError, "worktree is dirty"):
                    validate_detector_checkout(directory)


if __name__ == "__main__":
    unittest.main()

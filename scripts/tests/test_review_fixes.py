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
from validate_data import _load_raw  # noqa: E402


class ReviewFixTests(unittest.TestCase):
    def test_aliases_keep_one_slot_per_credited_record(self):
        result = parse_source_catalog(
            [{"id": "song", "name": "Song", "artists": ["first", "second"], "seriesIds": []}],
            [
                {"id": "first", "name": "First"},
                {"id": "second", "name": "Second", "englishName": "Second English"},
            ],
            [],
        )
        self.assertEqual(result[0]["artistNames"], ["First", "Second"])
        self.assertEqual(result[0]["artistAliases"], ["First", "Second English"])

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

"""Adapter around the pinned five-model ``chord_recognition_module`` submodule.

The recognizer is imported lazily so catalog compilation and the static site do
not load its analysis-only dependencies.
"""

from __future__ import annotations

import json
import math
from contextlib import redirect_stdout
import importlib
from pathlib import Path
import subprocess
import sys
from typing import Any, Callable, List, Mapping


DETECTOR_NAME = "large-vocabulary-chord-recognition"
DETECTOR_REPOSITORY = "https://github.com/Hoo-Knows/large-vocabulary-chord-recognition"
DETECTOR_REVISION = "264676532dbd38cd536be4bbf8ba5a82c6d45013"
DETECTOR_CONFIG_VERSION = "royal-road-1.0.0"
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DETECTOR_PATH = PROJECT_ROOT / "chord_recognition_module"


class DetectorError(RuntimeError):
    pass


def _record_value(record: Mapping[str, Any], *names: str) -> Any:
    for name in names:
        if name in record:
            return record[name]
    raise KeyError(f"Detector record is missing one of {names}")


def normalize_detector_segments(value: Any) -> List[dict[str, Any]]:
    """Normalize JSON or lab output to the raw timeline schema."""

    if isinstance(value, Mapping):
        for key in ("segments", "chords", "data", "annotations"):
            if key in value:
                value = value[key]
                break
    records: List[Any]
    if isinstance(value, list):
        records = value
    else:
        raise DetectorError("Detector output must be a list or an object containing segments")

    segments: List[dict[str, Any]] = []
    previous_end = -1.0
    for index, record in enumerate(records):
        if isinstance(record, Mapping):
            try:
                start = float(_record_value(record, "startSeconds", "start_time", "start"))
                end = float(_record_value(record, "endSeconds", "end_time", "end"))
                label = str(_record_value(record, "label", "chord", "name"))
            except (KeyError, TypeError, ValueError) as error:
                raise DetectorError(f"Invalid detector segment at index {index}: {record!r}") from error
        elif isinstance(record, (list, tuple)) and len(record) >= 3:
            try:
                start, end, label = float(record[0]), float(record[1]), str(record[2])
            except (TypeError, ValueError) as error:
                raise DetectorError(f"Invalid detector segment at index {index}: {record!r}") from error
        else:
            raise DetectorError(f"Invalid detector segment at index {index}: {record!r}")
        if not math.isfinite(start) or not math.isfinite(end) or start < 0 or end <= start or start < previous_end or not label.strip():
            raise DetectorError(f"Detector segments are not ordered/non-overlapping at index {index}")
        segments.append({"index": index, "startSeconds": start, "endSeconds": end, "label": label})
        previous_end = end
    return segments


def parse_detector_output(text: str) -> List[dict[str, Any]]:
    stripped = text.strip()
    if not stripped:
        raise DetectorError("Detector produced no output")
    try:
        return normalize_detector_segments(json.loads(stripped))
    except json.JSONDecodeError:
        records: List[list[Any]] = []
        for line_number, line in enumerate(stripped.splitlines(), start=1):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            columns = line.split(maxsplit=2)
            if len(columns) != 3:
                raise DetectorError(f"Invalid .lab line {line_number}: {line!r}")
            records.append([columns[0], columns[1], columns[2]])
        return normalize_detector_segments(records)


def analysis_descriptor() -> dict[str, str]:
    return {
        "module": "chord_recognition_module",
        "revision": DETECTOR_REVISION,
        "configVersion": DETECTOR_CONFIG_VERSION,
    }


def analysis_version() -> str:
    """Return the per-song token used to decide whether a timeline is reusable."""

    return f"{DETECTOR_REVISION}:{DETECTOR_CONFIG_VERSION}"


def validate_detector_checkout(detector_path: Path = DETECTOR_PATH) -> None:
    """Ensure the recursive-clone submodule is present at the pinned revision."""

    if not (detector_path / "__init__.py").is_file():
        raise DetectorError(
            "The chord-recognition submodule is not initialized. Clone with "
            "--recurse-submodules or run 'git submodule update --init --recursive'."
        )

    try:
        result = subprocess.run(
            [
                "git",
                "-c",
                f"safe.directory={detector_path.resolve()}",
                "-C",
                str(detector_path),
                "rev-parse",
                "HEAD",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError as error:
        raise DetectorError(f"Could not verify the detector submodule revision: {error}") from error

    revision = result.stdout.strip().lower()
    if result.returncode != 0 or not revision:
        message = result.stderr.strip() or "Git did not return a revision"
        raise DetectorError(f"Could not verify the detector submodule revision: {message}")
    if revision != DETECTOR_REVISION:
        raise DetectorError(
            "The chord-recognition submodule is at revision "
            f"{revision}, expected {DETECTOR_REVISION}. Run "
            "'git submodule update --init --recursive'."
        )

    try:
        status_result = subprocess.run(
            [
                "git",
                "-c",
                f"safe.directory={detector_path.resolve()}",
                "-C",
                str(detector_path),
                "status",
                "--porcelain",
                "--untracked-files=all",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError as error:
        raise DetectorError(f"Could not verify the detector submodule worktree: {error}") from error
    if status_result.returncode != 0:
        message = status_result.stderr.strip() or "Git did not return worktree status"
        raise DetectorError(f"Could not verify the detector submodule worktree: {message}")
    if status_result.stdout.strip():
        raise DetectorError(
            "The chord-recognition submodule worktree is dirty. Restore modified or "
            "untracked detector files before running analysis."
        )


def _load_chord_recognition() -> Callable[[str], Any]:
    validate_detector_checkout()
    if str(PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(PROJECT_ROOT))
    try:
        module = importlib.import_module("chord_recognition_module")
    except Exception as error:
        raise DetectorError(f"Could not import the chord-recognition submodule: {error}") from error
    recognition = getattr(module, "chord_recognition", None)
    if not callable(recognition):
        raise DetectorError("The chord-recognition submodule does not export chord_recognition")
    return recognition


def run_detector(audio_path: Path) -> List[dict[str, Any]]:
    """Run the pinned detector directly and normalize its returned chord rows."""

    recognition = _load_chord_recognition()
    try:
        # Upstream prints model progress to stdout. Keep this CLI's stdout
        # machine-readable by sending that chatter alongside our own logs.
        with redirect_stdout(sys.stderr):
            output = recognition(str(audio_path))
        return normalize_detector_segments(output)
    except DetectorError:
        raise
    except Exception as error:
        raise DetectorError(f"Chord recognition failed: {error}") from error


__all__ = [
    "DETECTOR_CONFIG_VERSION",
    "DETECTOR_NAME",
    "DETECTOR_PATH",
    "DETECTOR_REPOSITORY",
    "DETECTOR_REVISION",
    "DetectorError",
    "analysis_descriptor",
    "analysis_version",
    "normalize_detector_segments",
    "parse_detector_output",
    "run_detector",
    "validate_detector_checkout",
]

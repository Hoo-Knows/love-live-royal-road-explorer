"""Fetch a consistent, commit-pinned metadata snapshot."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Callable, Dict, Mapping, Optional, Tuple
from urllib.request import Request, urlopen

from .https import create_verified_context
from .io_utils import atomic_write_bytes, atomic_write_json, read_json


SOURCE_REPOSITORY = "https://github.com/hamproductions/the-sorter"
SOURCE_API = "https://api.github.com/repos/hamproductions/the-sorter/commits/main"
SOURCE_FILES = ("song-info.json", "artists-info.json", "series-info.json")
SOURCE_RAW_TEMPLATE = "https://raw.githubusercontent.com/hamproductions/the-sorter/{commit}/data/{filename}"
SOURCE_SNAPSHOT_MARKER = ".snapshot.json"
SOURCE_SNAPSHOT_SCHEMA_VERSION = "1.0.0"


def _request_bytes(url: str, headers: Optional[Mapping[str, str]] = None) -> Tuple[bytes, Mapping[str, str]]:
    request = Request(url, headers={"User-Agent": "royal-road-analysis/0.1", **dict(headers or {})})
    with urlopen(request, timeout=60, context=create_verified_context()) as response:
        return response.read(), response.headers


def _sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _snapshot_marker_path(source_dir: Path) -> Path:
    return source_dir / SOURCE_SNAPSHOT_MARKER


def resolve_source_commit() -> str:
    body, _ = _request_bytes(SOURCE_API, {"Accept": "application/vnd.github+json"})
    payload = json.loads(body.decode("utf-8"))
    commit = payload.get("sha")
    if not isinstance(commit, str) or len(commit) < 7:
        raise RuntimeError("GitHub did not return a commit SHA for the source snapshot")
    return commit


def fetch_metadata_snapshot(
    output_dir: Path,
    commit: Optional[str] = None,
    log: Optional[Callable[[str], None]] = None,
) -> Dict[str, Any]:
    commit = commit or resolve_source_commit()
    if not commit or any(character not in "0123456789abcdefABCDEF" for character in commit):
        raise ValueError(f"Source commit must be a hexadecimal SHA: {commit!r}")
    output_dir.mkdir(parents=True, exist_ok=True)
    downloaded = []

    for filename in SOURCE_FILES:
        url = SOURCE_RAW_TEMPLATE.format(commit=commit, filename=filename)
        if log:
            log(f"fetching source file {filename} at {commit}")
        body, headers = _request_bytes(url)
        # Validate every file before replacing any cached copy, so a partial or
        # bad fetch never becomes the input for a later resumable run.
        json.loads(body.decode("utf-8"))
        downloaded.append((filename, url, body, headers))

    if log:
        log(f"validated {len(downloaded)} source files; publishing snapshot")

    file_hashes = {}
    for filename, url, body, headers in downloaded:
        destination = output_dir / filename
        atomic_write_bytes(destination, body)
        file_hashes[filename] = _sha256_bytes(body)
    # Publish provenance only after every metadata file has been atomically
    # replaced. An interrupted publication therefore leaves the previous
    # marker in place, which causes the next reuse attempt to fail closed.
    atomic_write_json(
        _snapshot_marker_path(output_dir),
        {
            "schemaVersion": SOURCE_SNAPSHOT_SCHEMA_VERSION,
            "commit": commit,
            "files": file_hashes,
        },
    )
    return {"commit": commit}


def local_metadata_snapshot(source_dir: Path, commit: str) -> Dict[str, Any]:
    for filename in SOURCE_FILES:
        path = source_dir / filename
        if not path.exists():
            raise FileNotFoundError(f"Missing source metadata file: {path}")

    marker_path = _snapshot_marker_path(source_dir)
    if not marker_path.exists():
        raise ValueError(
            f"Source metadata cache has no snapshot marker: {marker_path}. "
            "Refresh the source snapshot before reusing it."
        )
    try:
        marker = read_json(marker_path)
    except (OSError, ValueError) as error:
        raise ValueError(f"Could not read source metadata snapshot marker: {marker_path}") from error
    if not isinstance(marker, Mapping):
        raise ValueError(f"Source metadata snapshot marker is not an object: {marker_path}")
    if marker.get("schemaVersion") != SOURCE_SNAPSHOT_SCHEMA_VERSION:
        raise ValueError(f"Unsupported source metadata snapshot marker schema: {marker_path}")
    recorded_commit = marker.get("commit")
    if recorded_commit != commit:
        raise ValueError(
            "Source metadata cache belongs to commit "
            f"{recorded_commit!r}, but commit {commit!r} was requested. Refresh the source snapshot."
        )
    recorded_hashes = marker.get("files")
    if not isinstance(recorded_hashes, Mapping) or set(recorded_hashes) != set(SOURCE_FILES):
        raise ValueError(f"Source metadata snapshot marker has incomplete file hashes: {marker_path}")
    for filename in SOURCE_FILES:
        path = source_dir / filename
        try:
            content = path.read_bytes()
            json.loads(content.decode("utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ValueError(f"Source metadata file is unreadable or invalid JSON: {path}") from error
        actual_hash = _sha256_bytes(content)
        if recorded_hashes.get(filename) != actual_hash:
            raise ValueError(f"Source metadata file does not match its snapshot marker: {path}")
    return {"commit": commit}


def read_metadata_payloads(source_dir: Path) -> Tuple[Any, Any, Any]:
    payloads = []
    for filename in SOURCE_FILES:
        with (source_dir / filename).open("r", encoding="utf-8") as handle:
            payloads.append(json.load(handle))
    return payloads[0], payloads[1], payloads[2]


__all__ = [
    "SOURCE_FILES",
    "SOURCE_RAW_TEMPLATE",
    "SOURCE_REPOSITORY",
    "SOURCE_SNAPSHOT_MARKER",
    "SOURCE_SNAPSHOT_SCHEMA_VERSION",
    "fetch_metadata_snapshot",
    "local_metadata_snapshot",
    "read_metadata_payloads",
    "resolve_source_commit",
]

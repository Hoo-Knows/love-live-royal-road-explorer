"""Compact committed analysis state shared by maintainer commands."""

from __future__ import annotations

from typing import Any, Mapping

from .detector import analysis_descriptor


MANIFEST_SCHEMA_VERSION = "2.0.0"


def analysis_state(
    *,
    status: str,
    audio_url: Any,
    audio_sha256: Any = None,
    analysis_version: Any = None,
    error: Any = None,
) -> dict[str, Any]:
    """Build the uniform, intentionally small state record for one source song."""

    return {
        "status": status,
        "audioUrl": str(audio_url) if audio_url is not None else None,
        "audioSha256": str(audio_sha256) if audio_sha256 is not None else None,
        "analysisVersion": str(analysis_version) if analysis_version is not None else None,
        "error": str(error) if error is not None else None,
    }


def build_manifest(
    source_commit: str,
    songs: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    return {
        "schemaVersion": MANIFEST_SCHEMA_VERSION,
        "sourceCommit": str(source_commit),
        "analysis": analysis_descriptor(),
        "songs": dict(songs),
    }


__all__ = ["MANIFEST_SCHEMA_VERSION", "analysis_state", "build_manifest"]

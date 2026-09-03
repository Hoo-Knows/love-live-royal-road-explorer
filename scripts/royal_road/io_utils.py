"""Small atomic and hashing helpers used by the analysis pipeline."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import os
import tempfile
import time
from typing import Any, Optional


def read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def atomic_write_bytes(path: Path, content: bytes) -> None:
    destination = path.resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Optional[Path] = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb", prefix=f".{destination.name}.", suffix=".tmp", dir=str(destination.parent), delete=False
        ) as handle:
            temporary_path = Path(handle.name)
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        last_error: Optional[PermissionError] = None
        for attempt in range(5):
            try:
                os.replace(str(temporary_path), str(destination))
                break
            except PermissionError as error:
                last_error = error
                if os.name != "nt" or attempt == 4:
                    raise
                time.sleep(0.1 * (2**attempt))
        else:
            if last_error is not None:
                raise last_error
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()


def atomic_write_json(path: Path, payload: Any) -> None:
    content = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=False).encode("utf-8")
    atomic_write_bytes(path, content + b"\n")


def atomic_write_text(path: Path, content: str) -> None:
    atomic_write_bytes(path, content.encode("utf-8"))


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_hash(payload: Any) -> str:
    content = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(content).hexdigest()


__all__ = ["atomic_write_bytes", "atomic_write_json", "atomic_write_text", "canonical_hash", "read_json", "sha256_file"]

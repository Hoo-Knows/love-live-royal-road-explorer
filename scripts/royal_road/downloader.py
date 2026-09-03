"""Throttled, retrying audio cache for maintainer analysis only."""

from __future__ import annotations

import math
from pathlib import Path
import os
import shutil
import ssl
import subprocess
import tempfile
import time
from typing import Any, Callable, Mapping, Optional
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .https import create_verified_context
from .io_utils import sha256_file


class DownloadError(RuntimeError):
    """A download failed, with retryability preserved for the caller."""

    def __init__(self, message: str, *, transient: bool = False) -> None:
        super().__init__(message)
        self.transient = transient


_last_request_at = 0.0


def _is_certificate_verification_error(error: BaseException) -> bool:
    for candidate in (error, getattr(error, "reason", None)):
        if isinstance(candidate, ssl.SSLCertVerificationError) or (
            isinstance(candidate, ssl.SSLError) and "CERTIFICATE_VERIFY_FAILED" in str(candidate)
        ):
            return True
    return False


def _is_tls_error(error: BaseException) -> bool:
    for candidate in (error, getattr(error, "reason", None)):
        if isinstance(candidate, ssl.SSLError):
            return True
    return False


def _throttle(seconds: float) -> None:
    global _last_request_at
    wait_for = seconds - (time.monotonic() - _last_request_at)
    if wait_for > 0:
        time.sleep(wait_for)
    _last_request_at = time.monotonic()


def download_audio(
    url: str,
    destination: Path,
    previous: Optional[Mapping[str, Any]] = None,
    throttle_seconds: float = 1.0,
    max_retries: int = 3,
    log: Optional[Callable[[str], None]] = None,
) -> dict[str, Any]:
    """Download to a sibling temporary file and atomically publish the cache entry."""

    destination.parent.mkdir(parents=True, exist_ok=True)
    request_headers = {}
    if previous and destination.exists():
        if previous.get("etag"):
            request_headers["If-None-Match"] = str(previous["etag"])
        if previous.get("lastModified"):
            request_headers["If-Modified-Since"] = str(previous["lastModified"])

    last_error: Optional[Exception] = None
    last_failure_was_transient = False
    for attempt in range(max_retries + 1):
        try:
            if log:
                log(f"    audio request {attempt + 1}/{max_retries + 1}: {url}")
            _throttle(throttle_seconds)
            request = Request(url, headers={"User-Agent": "royal-road-analysis/0.1", **request_headers})
            with urlopen(request, timeout=120, context=create_verified_context()) as response:
                if response.status == 304 and destination.exists():
                    if log:
                        log("    server returned 304; using cached audio")
                    return {
                        "path": str(destination),
                        "audioSha256": sha256_file(destination),
                        "etag": previous.get("etag") if previous else None,
                        "lastModified": previous.get("lastModified") if previous else None,
                        "notModified": True,
                    }
                if response.status < 200 or response.status >= 300:
                    raise HTTPError(url, response.status, "unexpected HTTP status", response.headers, None)
                temporary_path: Optional[Path] = None
                try:
                    with tempfile.NamedTemporaryFile(mode="wb", prefix=f".{destination.name}.", suffix=".part", dir=str(destination.parent), delete=False) as handle:
                        temporary_path = Path(handle.name)
                        while chunk := response.read(1024 * 1024):
                            handle.write(chunk)
                        handle.flush()
                        os.fsync(handle.fileno())
                    os.replace(str(temporary_path), str(destination))
                finally:
                    if temporary_path is not None and temporary_path.exists():
                        temporary_path.unlink()
                return {
                    "path": str(destination),
                    "audioSha256": sha256_file(destination),
                    "etag": response.headers.get("ETag"),
                    "lastModified": response.headers.get("Last-Modified"),
                    "notModified": False,
                }
        except HTTPError as error:
            # urllib commonly raises HTTPError for a 304 response instead of
            # returning a response object. Treat it as a cache hit when the
            # conditional request has a complete local recording.
            if error.code == 304 and destination.exists():
                if log:
                    log("    server returned 304; using cached audio")
                return {
                    "path": str(destination),
                    "audioSha256": sha256_file(destination),
                    "etag": error.headers.get("ETag") if error.headers else (previous.get("etag") if previous else None),
                    "lastModified": error.headers.get("Last-Modified") if error.headers else (previous.get("lastModified") if previous else None),
                    "notModified": True,
                }
            last_error = error
            transient = error.code == 408 or error.code == 429 or error.code >= 500
            last_failure_was_transient = transient
            if not transient or attempt >= max_retries:
                break
            if log:
                log(f"    transient HTTP {error.code}; retrying")
        except (URLError, TimeoutError, OSError) as error:
            last_error = error
            transient = not _is_tls_error(error)
            last_failure_was_transient = transient
            if not transient:
                if log:
                    message = "TLS certificate verification failed" if _is_certificate_verification_error(error) else "TLS failure"
                    log(f"    {message}; not retrying: {getattr(error, 'reason', error)}")
                break
            if attempt >= max_retries:
                break
            if log:
                log(f"    transient network error; retrying: {error}")
        time.sleep(min(30.0, 2.0 ** attempt))

    raise DownloadError(
        f"Unable to download {url}: {last_error}",
        transient=last_failure_was_transient,
    )


def probe_duration(audio_path: Path) -> Optional[float]:
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        return None
    result = subprocess.run(
        [ffprobe, "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(audio_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return None
    try:
        value = float(result.stdout.strip())
    except ValueError:
        return None
    return value if math.isfinite(value) and value >= 0 else None


__all__ = ["DownloadError", "download_audio", "probe_duration"]

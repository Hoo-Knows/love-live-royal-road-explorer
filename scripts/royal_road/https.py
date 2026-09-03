"""Verified HTTPS context for maintainer-only network requests."""

from __future__ import annotations

import os
import ssl
from typing import Any

try:
    import certifi
except ImportError:  # pragma: no cover - the project declares certifi explicitly.
    certifi: Any = None


def create_verified_context() -> ssl.SSLContext:
    """Build a verified context with explicit local CA settings taking priority."""

    configured_cafile = os.environ.get("SSL_CERT_FILE")
    configured_capath = os.environ.get("SSL_CERT_DIR")
    if configured_cafile or configured_capath:
        return ssl.create_default_context(cafile=configured_cafile, capath=configured_capath)
    if certifi is not None:
        try:
            return ssl.create_default_context(cafile=certifi.where())
        except (OSError, ssl.SSLError):
            # Keep verification enabled if the pinned bundle cannot be opened
            # in the current environment (for example, a restricted checkout).
            # The system trust store is the safe fallback; never use an
            # unverified context.
            pass
    return ssl.create_default_context()


__all__ = ["create_verified_context"]

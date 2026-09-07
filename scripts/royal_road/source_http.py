"""Small throttled, verified HTTPS JSON client for explicit source refreshes."""

from __future__ import annotations

import json
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .https import create_verified_context


class SourceHTTP:
    def __init__(self, throttle: float = 0.3, retries: int = 3):
        if throttle < 0 or not 0 <= retries <= 5:
            raise ValueError("Throttle must be nonnegative and retries between zero and five")
        self.throttle = throttle
        self.retries = retries
        self.last_request = 0.0

    def json(self, url: str, payload=None):
        for attempt in range(self.retries + 1):
            time.sleep(max(0, self.last_request + self.throttle - time.monotonic()))
            self.last_request = time.monotonic()
            request = Request(
                url,
                data=json.dumps(payload).encode("utf-8") if payload is not None else None,
                headers={"User-Agent": "RoyalRoadExplorer/1.0 (independent metadata collection)",
                         "Accept": "application/json", "Content-Type": "application/json"},
            )
            try:
                with urlopen(request, timeout=30, context=create_verified_context()) as response:
                    return json.loads(response.read().decode("utf-8"))
            except (HTTPError, URLError, TimeoutError) as error:
                if isinstance(error, HTTPError) and error.code not in (408, 429, 500, 502, 503, 504):
                    raise
                if attempt == self.retries:
                    raise
                time.sleep(min(8, 2 ** attempt))

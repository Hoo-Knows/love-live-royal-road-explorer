"""Explicit independent metadata refresh; never downloads recordings or runs recognition."""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

from royal_road.io_utils import atomic_write_bytes, read_json
from royal_road.ll_fans import fetch_ll_fans
from royal_road.source_http import SourceHTTP
from royal_road.source_report import source_review
from royal_road.sources import load_metadata_snapshot, publish_snapshot, snapshot_absent
from royal_road.wiki import Wiki, enrich


def now():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def refresh(output_dir, overrides_path, client, log, retry_failed_songs=False):
    started = now()
    previous = None
    if not snapshot_absent(output_dir):
        try:
            previous = load_metadata_snapshot(output_dir)
        except (OSError, ValueError) as error:
            log(f"Previous snapshot is unusable; collecting independently: {error}")
    if retry_failed_songs and previous is None:
        raise ValueError("--retry-failed requires a valid existing source snapshot")
    payloads, identities = fetch_ll_fans(client)
    log(f"ll-fans: {len(payloads[0])} songs, {len(payloads[1])} artists, {len(payloads[2])} series")
    wiki = enrich(payloads, identities, read_json(overrides_path), Wiki(client), previous=previous, log=log,
                  retry_failed_songs=retry_failed_songs)
    # An initial collection must have actual wiki access; no unverified URLs
    # or metadata from unrelated snapshots may become independent provenance.
    if previous is None and not any(item.get("file") for item in wiki["songs"].values()):
        raise ValueError("Initial refresh did not independently verify any recordings; wiki access is required")
    return publish_snapshot(output_dir, payloads, started=started, finished=now(), wiki=wiki)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path("data/source"))
    parser.add_argument("--overrides", type=Path, default=Path("data/source-overrides.json"))
    parser.add_argument("--report", type=Path, default=Path("data/source-review.md"))
    parser.add_argument("--throttle", type=float, default=0.3)
    parser.add_argument("--max-retries", type=int, default=3)
    parser.add_argument("--retry-failed", action="store_true",
                        help="reuse compatible successful wiki results and retry unresolved songs")
    args = parser.parse_args(argv)
    try:
        marker = refresh(args.output_dir, args.overrides, SourceHTTP(args.throttle, args.max_retries),
                         lambda message: print(message, file=sys.stderr, flush=True),
                         retry_failed_songs=args.retry_failed)
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(f"Source refresh aborted: {error}", file=sys.stderr)
        return 2
    _, payloads = load_metadata_snapshot(args.output_dir)
    atomic_write_bytes(args.report, source_review(marker, payloads).encode("utf-8"))
    unresolved = {
        kind: [{"id": entity_id, **{key: item[key] for key in ("status", "reason", "candidates") if key in item}}
               for entity_id, item in records.items() if item["status"] != "verified"]
        for kind, records in marker["wiki"].items()
    }
    print(json.dumps({"snapshotId": marker["snapshotId"], "unresolved": unresolved,
                      "wiki": {kind: dict(Counter(item["status"] for item in records.values()))
                               for kind, records in marker["wiki"].items()}}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

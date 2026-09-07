"""Validate and atomically publish committed, independently collected snapshots."""

from __future__ import annotations

from datetime import datetime
import hashlib
import json
import re
from pathlib import Path
from urllib.parse import urlparse

from .io_utils import atomic_write_bytes, atomic_write_json, canonical_hash, read_json


LL_FANS_API = "https://ll-fans.jp/api/graphql"
WIKI_API = "https://love-live.fandom.com/api.php"
SOURCE_FILES = ("song-info.json", "artists-info.json", "series-info.json")
SOURCE_SNAPSHOT_MARKER = ".snapshot.json"
SOURCE_SNAPSHOT_SCHEMA_VERSION = "2.1.0"
LEGACY_SOURCE_SNAPSHOT_SCHEMA_VERSION = "2.0.0"
PROVIDERS = {"metadata": LL_FANS_API, "enrichment": WIKI_API}


def validate_payloads(songs, artists, series, *, require_creator_metadata=True):
    lookups = []
    for records, kind in ((songs, "songs"), (artists, "artists"), (series, "series")):
        if not isinstance(records, list) or not records:
            raise ValueError(f"{kind} must be a nonempty array")
        ids = set()
        for record in records:
            required = {"id", "name", "englishName"}
            if kind == "songs":
                required |= {"phoneticName", "artists", "seriesIds", "releasedOn", "wikiAudioUrl"}
                if require_creator_metadata:
                    required.add("creators")
            optional = {"wikiAudioUrls"} if kind == "songs" else set()
            if kind == "songs" and not require_creator_metadata:
                optional.add("creators")
            if (not isinstance(record, dict) or not required <= set(record)
                    or set(record) - required != (optional & set(record))):
                raise ValueError(f"Invalid {kind} fields: {record!r}")
            for field in ("id", "name", "englishName"):
                if not isinstance(record[field], str) or not record[field].strip():
                    raise ValueError(f"Missing {kind} {field}")
            if not record["id"].isascii() or not record["id"].isdigit() or record["id"] in ids:
                raise ValueError(f"Invalid or duplicate {kind} ID: {record['id']}")
            ids.add(record["id"])
            if kind == "songs":
                if record["phoneticName"] is not None and not isinstance(record["phoneticName"], str):
                    raise ValueError("Invalid song reading")
                creators = record.get("creators", [])
                if not isinstance(creators, list):
                    raise ValueError("Invalid song creators")
                creator_ids = set()
                for creator in creators:
                    if not isinstance(creator, dict) or set(creator) != {"id", "name", "aliases"}:
                        raise ValueError("Invalid song creator")
                    creator_id = creator["id"]
                    if (not isinstance(creator_id, str) or not creator_id.isascii()
                            or not creator_id.isdigit() or creator_id in creator_ids):
                        raise ValueError("Invalid or duplicate song creator ID")
                    creator_ids.add(creator_id)
                    if not isinstance(creator["name"], str) or not creator["name"].strip():
                        raise ValueError("Missing song creator name")
                    aliases = creator["aliases"]
                    if not isinstance(aliases, list) or any(
                            not isinstance(alias, str) or not alias.strip() for alias in aliases):
                        raise ValueError("Invalid song creator aliases")
                    if len(aliases) != len(set(aliases)):
                        raise ValueError("Invalid song creator aliases")
                if record["releasedOn"] is not None:
                    datetime.strptime(record["releasedOn"], "%Y-%m-%d")
                url = record["wikiAudioUrl"]
                urls = record.get("wikiAudioUrls", [url] if url else [])
                if (not isinstance(urls, list) or len(urls) != len(set(urls))
                        or (urls[0] if urls else None) != url):
                    raise ValueError("Invalid ordered wiki audio URLs")
                for audio_url in urls:
                    if (not isinstance(audio_url, str) or urlparse(audio_url).scheme != "https"
                            or urlparse(audio_url).hostname != "static.wikia.nocookie.net"
                            or not urlparse(audio_url).path.startswith("/love-live/images/")):
                        raise ValueError("Invalid wiki audio URL")
        lookups.append(ids)
    for song in songs:
        for key, valid in (("artists", lookups[1]), ("seriesIds", lookups[2])):
            refs = song[key]
            if not isinstance(refs, list) or not refs or any(not isinstance(ref, str) or ref not in valid for ref in refs):
                raise ValueError(f"Invalid {key} references for song {song['id']}")


def snapshot_absent(source_dir: Path) -> bool:
    return not any((source_dir / name).exists() for name in (*SOURCE_FILES, SOURCE_SNAPSHOT_MARKER))


def _content_id(marker):
    return canonical_hash({key: marker[key] for key in ("schemaVersion", "providers", "files", "wiki")})


def publish_snapshot(output_dir: Path, payloads, *, started: str, finished: str, wiki: dict):
    validate_payloads(*payloads)
    bodies = {
        filename: (json.dumps(sorted(records, key=lambda r: int(r["id"])), ensure_ascii=False,
                              indent=2) + "\n").encode("utf-8")
        for filename, records in zip(SOURCE_FILES, payloads)
    }
    marker = {
        "schemaVersion": SOURCE_SNAPSHOT_SCHEMA_VERSION,
        "providers": PROVIDERS,
        "collection": {"startedAt": started, "finishedAt": finished},
        "files": {name: hashlib.sha256(body).hexdigest() for name, body in bodies.items()},
        "wiki": wiki,
    }
    marker["snapshotId"] = _content_id(marker)
    validate_marker(marker, payloads)
    for filename, body in bodies.items():
        atomic_write_bytes(output_dir / filename, body)
    # The previous marker rejects mixed files after interruption.
    atomic_write_json(output_dir / SOURCE_SNAPSHOT_MARKER, marker)
    return marker


def validate_marker(marker, payloads, *, allow_legacy=False):
    if not isinstance(marker, dict) or set(marker) != {
        "schemaVersion", "providers", "collection", "files", "wiki", "snapshotId"
    }:
        raise ValueError("Invalid source snapshot marker fields")
    supported_versions = {SOURCE_SNAPSHOT_SCHEMA_VERSION}
    if allow_legacy:
        supported_versions.add(LEGACY_SOURCE_SNAPSHOT_SCHEMA_VERSION)
    if marker["schemaVersion"] not in supported_versions or marker["providers"] != PROVIDERS:
        raise ValueError("Unsupported source snapshot schema or providers; run scripts/refresh_source.py")
    validate_payloads(*payloads, require_creator_metadata=marker["schemaVersion"] != LEGACY_SOURCE_SNAPSHOT_SCHEMA_VERSION)
    interval = marker["collection"]
    start = datetime.fromisoformat(interval["startedAt"].replace("Z", "+00:00"))
    end = datetime.fromisoformat(interval["finishedAt"].replace("Z", "+00:00"))
    if not start.tzinfo or not end.tzinfo or end < start:
        raise ValueError("Invalid collection interval")
    if set(marker["files"]) != set(SOURCE_FILES) or marker["snapshotId"] != _content_id(marker):
        raise ValueError("Source snapshot ID or file hashes do not match")
    if set(marker["wiki"]) != {"songs", "artists", "series"}:
        raise ValueError("Incomplete wiki verification records")
    for kind, records in zip(("songs", "artists", "series"), payloads):
        evidence = marker["wiki"][kind]
        if set(evidence) != {r["id"] for r in records}:
            raise ValueError(f"Wiki verification IDs differ from {kind}")
        for record in records:
            item = evidence[record["id"]]
            if item.get("status") not in {"verified", "stale", "missing", "ambiguous", "unresolved", "unavailable"}:
                raise ValueError("Invalid wiki verification status")
            if not isinstance(item.get("identity"), str):
                raise ValueError("Missing wiki source identity")
            if not re.fullmatch(r"[a-f0-9]{64}", item["identity"]):
                raise ValueError("Invalid wiki source identity")
            if record.get("wikiAudioUrl"):
                file, page = item.get("file"), item.get("page")
                if (item["status"] not in {"verified", "stale"} or not isinstance(file, dict)
                        or not isinstance(page, dict) or not isinstance(page.get("id"), int)
                        or not isinstance(page.get("revision"), int) or not isinstance(page.get("title"), str)
                        or not isinstance(file.get("id"), int) or not file.get("title", "").startswith("File:")
                        or not re.fullmatch(r"[a-f0-9]{40}", file.get("sha1", ""))
                        or not file.get("timestamp") or file.get("url") != record["wikiAudioUrl"]):
                    raise ValueError("Audio has no matching independent wiki verification")
                if "wikiAudioUrls" in record:
                    urls, files = record["wikiAudioUrls"], item.get("files")
                    if (not isinstance(files, list) or len(files) != len(urls)
                            or any(not isinstance(value, dict)
                                   or not isinstance(value.get("id"), int)
                                   or not value.get("title", "").startswith("File:")
                                   or not re.fullmatch(r"[a-f0-9]{40}", value.get("sha1", ""))
                                   or not value.get("timestamp") or value.get("url") != audio_url
                                   for value, audio_url in zip(files, urls))):
                        raise ValueError("Audio alternatives lack independent wiki verification")



def load_metadata_snapshot(source_dir: Path, *, allow_legacy=False):
    if snapshot_absent(source_dir):
        raise FileNotFoundError(f"Source snapshot absent: {source_dir}; run scripts/refresh_source.py")
    if not all((source_dir / name).is_file() for name in (*SOURCE_FILES, SOURCE_SNAPSHOT_MARKER)):
        raise ValueError("Partial source snapshot; run scripts/refresh_source.py")
    try:
        marker = read_json(source_dir / SOURCE_SNAPSHOT_MARKER)
        bodies = {name: (source_dir / name).read_bytes() for name in SOURCE_FILES}
        payloads = tuple(json.loads(bodies[name].decode("utf-8")) for name in SOURCE_FILES)
        validate_marker(marker, payloads, allow_legacy=allow_legacy)
        for filename in SOURCE_FILES:
            if hashlib.sha256(bodies[filename]).hexdigest() != marker["files"][filename]:
                raise ValueError(f"Source file does not match snapshot marker: {filename}")
    except (KeyError, TypeError) as error:
        raise ValueError(f"Malformed source snapshot: {error}") from error
    return marker, payloads


def local_metadata_snapshot(source_dir: Path):
    return load_metadata_snapshot(source_dir)[0]


def read_metadata_payloads(source_dir: Path):
    return load_metadata_snapshot(source_dir)[1]

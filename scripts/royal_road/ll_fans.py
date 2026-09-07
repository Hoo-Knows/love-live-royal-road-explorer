"""Fetch all ll-fans records, including unreleased songs, using POST GraphQL."""

from __future__ import annotations

from .sources import LL_FANS_API, validate_payloads


SONG_FIELDS = """
id name phoneticName releasedOn seriesIds
artistVariants { id name artistConfigurationCastSet { id artistConfiguration { id artist { id name } } } }
songCredits {
  id
  staffType { id name }
  staffName { id name staff { id name staffNames { id name } } }
}
"""
PAGE_FIELDS = "currentPage lastPage total count hasMorePages"
CREATOR_ROLE_IDS = {"2", "3"}


def graphql(client, query, variables=None):
    payload = client.json(LL_FANS_API, {"query": query, "variables": variables or {}})
    if payload.get("errors") or not isinstance(payload.get("data"), dict):
        raise ValueError(f"ll-fans query failed: {payload}")
    return payload["data"]


def paginate(client, field, fields, page_size=100):
    records, seen = [], set()
    page, expected = 1, None
    while True:
        query = (f"query($page: Int!, $first: Int!) {{ {field}(page: $page, first: $first) "
                 f"{{ data {{ {fields} }} paginatorInfo {{ {PAGE_FIELDS} }} }} }}")
        result = graphql(client, query, {"page": page, "first": page_size})[field]
        info, batch = result["paginatorInfo"], result["data"]
        total, last = info["total"], info["lastPage"]
        if expected is None:
            expected = (total, last)
        if ((total, last) != expected or info["currentPage"] != page or info["count"] != len(batch)
                or not batch or len(batch) > page_size or last != (total + page_size - 1) // page_size
                or info["hasMorePages"] != (page < last)):
            raise ValueError(f"Inconsistent {field} pagination at page {page}")
        for record in batch:
            if not isinstance(record.get("id"), str) or record["id"] in seen:
                raise ValueError(f"Duplicate or invalid {field} ID")
            seen.add(record["id"])
            records.append(record)
        if not info["hasMorePages"]:
            if len(records) != total:
                raise ValueError(f"Incomplete {field} pagination")
            return records
        page += 1


def _creator_records(song):
    """Project main composition/arrangement credits into canonical staff records."""

    creators = {}
    for credit in song.get("songCredits") or []:
        staff_type = credit.get("staffType") or {}
        role_id = str(staff_type.get("id"))
        if role_id not in CREATOR_ROLE_IDS:
            continue
        staff_name = credit.get("staffName") or {}
        staff = staff_name.get("staff") or {}
        creator_id = str(staff.get("id", ""))
        canonical_name = staff.get("name")
        credited_name = staff_name.get("name")
        if not creator_id or not canonical_name or not credited_name:
            raise ValueError(f"Incomplete creator credit for song {song['id']}")

        aliases = []
        for name in [credited_name, *(item.get("name") for item in staff.get("staffNames") or [])]:
            if not isinstance(name, str) or not name.strip() or name == canonical_name or name in aliases:
                continue
            aliases.append(name)

        existing = creators.get(creator_id)
        if existing is None:
            creators[creator_id] = {
                "id": creator_id,
                "name": canonical_name,
                "aliases": aliases,
            }
            continue
        if existing["name"] != canonical_name:
            raise ValueError(f"Inconsistent creator identity for staff {creator_id}")
        existing_aliases = existing["aliases"]
        existing_aliases.extend(alias for alias in aliases if alias not in existing_aliases)
    return list(creators.values())


def fetch_ll_fans(client):
    songs = paginate(client, "songs", SONG_FIELDS)
    artists = paginate(client, "artists", "id name")
    series = graphql(client, "{ seriesList { id name } }")["seriesList"]
    artist_lookup = {a["id"]: a for a in artists}
    normalized = []
    identities = {}
    for song in songs:
        credits = []
        for variant in song["artistVariants"]:
            # Variant and artist IDs belong to different namespaces.
            artist = variant["artistConfigurationCastSet"]["artistConfiguration"]["artist"]
            if artist_lookup.get(artist["id"], {}).get("name") != artist["name"]:
                raise ValueError(f"Inconsistent artist reference for song {song['id']}")
            credits.append(artist["id"])
        normalized.append({
            "id": song["id"], "name": song["name"], "phoneticName": song["phoneticName"],
            "englishName": song["name"], "artists": credits,
            "creators": _creator_records(song),
            "seriesIds": [str(i) for i in song["seriesIds"]], "releasedOn": song["releasedOn"],
            "wikiAudioUrl": None, "wikiAudioUrls": [],
        })
        identities[song["id"]] = song
    payloads = (normalized, [{**a, "englishName": a["name"]} for a in artists],
                [{**s, "englishName": s["name"]} for s in series])
    validate_payloads(*payloads)
    return payloads, identities

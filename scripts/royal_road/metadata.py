"""Adapters for the Love Live Sorter source snapshot."""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence


def _records(payload: Any, preferred_keys: Sequence[str]) -> List[Dict[str, Any]]:
    if isinstance(payload, list):
        return [dict(value) for value in payload if isinstance(value, Mapping)]
    if isinstance(payload, Mapping):
        for key in preferred_keys:
            value = payload.get(key)
            if isinstance(value, list):
                return [dict(item) for item in value if isinstance(item, Mapping)]
        values: List[Dict[str, Any]] = []
        for key, value in payload.items():
            if isinstance(value, Mapping):
                item = dict(value)
                item.setdefault("id", key)
                values.append(item)
        return values
    raise ValueError("Expected a JSON array or object of records")


def _as_list(value: Any) -> List[Any]:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def _text(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _record_id(record: Mapping[str, Any], fallback: Any = None) -> str:
    value = record.get("id", record.get("songId", record.get("key", fallback)))
    if value is None:
        raise ValueError(f"Source record has no ID: {record!r}")
    return str(value)


def _name(record: Mapping[str, Any]) -> Optional[str]:
    return _text(record.get("name") or record.get("title") or record.get("englishName") or record.get("en"))


def _alternate_names(record: Optional[Mapping[str, Any]]) -> List[str]:
    if not record:
        return []
    names: List[str] = []
    for key in (
        "englishName",
        "englishTitle",
        "romanizedName",
        "romanisedName",
        "romaji",
        "en",
    ):
        value = _text(record.get(key))
        if value and value not in names:
            names.append(value)
    return names


def _lookup(records: Iterable[Mapping[str, Any]]) -> Dict[str, Mapping[str, Any]]:
    result: Dict[str, Mapping[str, Any]] = {}
    for record in records:
        result[_record_id(record)] = record
    return result


def _reference_names(
    value: Any,
    lookup: Mapping[str, Mapping[str, Any]],
) -> tuple[List[str], List[str]]:
    names: List[str] = []
    aliases: List[str] = []
    for reference in _as_list(value):
        if isinstance(reference, Mapping):
            reference_id = reference.get("id")
            inline_name = _name(reference)
            record = lookup.get(str(reference_id)) if reference_id is not None else None
            resolved = _name(record) if record else inline_name
            alternate_names = _alternate_names(record or reference)
        else:
            record = lookup.get(str(reference))
            resolved = _name(record) if record else _text(reference)
            alternate_names = _alternate_names(record)
        if resolved:
            try:
                name_index = names.index(resolved)
            except ValueError:
                name_index = len(names)
                names.append(resolved)
                aliases.append("")
            # Keep the alias in the same slot as its canonical source record.
            # In particular, an empty slot must not be removed when a later
            # credited record has an English name.
            if not aliases[name_index]:
                aliases[name_index] = next(
                    (
                        alternate
                        for alternate in alternate_names
                        if alternate != resolved and alternate not in names
                    ),
                    "",
                )
    # Trailing empty slots carry no alignment information because there is no
    # later alias to shift. Keep internal empty slots, however, so an alias on
    # a later credited record remains paired with that record.
    while aliases and not aliases[-1]:
        aliases.pop()
    return names, aliases


def _audio_url(record: Mapping[str, Any]) -> Optional[str]:
    for key in ("wikiAudioUrl", "audioUrl", "audio_url", "oggUrl", "ogg"):
        value = record.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
        if isinstance(value, Mapping):
            nested = _audio_url(value)
            if nested:
                return nested
    files = record.get("files")
    if isinstance(files, Mapping):
        return _audio_url(files)
    return None


def parse_source_catalog(
    songs_payload: Any,
    artists_payload: Any,
    series_payload: Any,
) -> List[Dict[str, Any]]:
    """Normalize the upstream arrays while preserving every source song."""

    songs = _records(songs_payload, ("songs", "items", "data"))
    artists = _lookup(_records(artists_payload, ("artists", "items", "data")))
    series = _lookup(_records(series_payload, ("series", "items", "data")))
    normalized: List[Dict[str, Any]] = []
    seen_ids = set()

    for source in songs:
        song_id = _record_id(source)
        if song_id in seen_ids:
            raise ValueError(f"Duplicate source song ID: {song_id}")
        seen_ids.add(song_id)
        title_ja = _text(source.get("name") or source.get("title"))
        title_en = _text(
            source.get("englishName")
            or source.get("englishTitle")
            or source.get("romanizedName")
            or source.get("romanisedName")
            or source.get("romaji")
            or source.get("en")
        )
        title_phonetic = _text(source.get("phoneticName") or source.get("phonetic") or source.get("reading"))
        artist_refs = source.get("artists", source.get("artistIds", source.get("artist")))
        series_refs = source.get("seriesIds", source.get("series"))
        artist_names, artist_aliases = _reference_names(artist_refs, artists)
        series_names, series_aliases = _reference_names(series_refs, series)
        normalized.append(
            {
                "id": song_id,
                "titles": {"ja": title_ja, "en": title_en, "phonetic": title_phonetic},
                "artistNames": artist_names,
                "artistAliases": artist_aliases,
                "seriesNames": series_names,
                "seriesAliases": series_aliases,
                "audioUrl": _audio_url(source),
                "releaseDate": _text(source.get("releasedOn") or source.get("releaseDate")),
            }
        )

    return normalized


__all__ = ["parse_source_catalog"]

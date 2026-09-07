"""Project the committed ll-fans/wiki snapshot into runtime catalog metadata."""

from __future__ import annotations


def parse_source_catalog(songs_payload, artists_payload, series_payload):
    artists = {record["id"]: record for record in artists_payload}
    series = {record["id"]: record for record in series_payload}
    result, seen = [], set()
    for song in songs_payload:
        song_id = song["id"]
        if song_id in seen:
            raise ValueError(f"Duplicate source song ID: {song_id}")
        seen.add(song_id)
        artist_records = [artists[ref] for ref in song["artists"]]
        series_records = [series[ref] for ref in song["seriesIds"]]
        result.append({
            "id": song_id,
            "titles": {"ja": song["name"], "en": song.get("englishName", song["name"]),
                       "phonetic": song.get("phoneticName")},
            "artistNames": [r["name"] for r in artist_records],
            "artistAliases": [r.get("englishName", r["name"]) for r in artist_records],
            "seriesNames": [r["name"] for r in series_records],
            "seriesAliases": [r.get("englishName", r["name"]) for r in series_records],
            "audioUrl": (song.get("wikiAudioUrls") or [song.get("wikiAudioUrl")])[0],
            "releaseDate": song.get("releasedOn"),
        })
    return result

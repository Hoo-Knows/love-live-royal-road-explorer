"""Small independently generated source fixtures; never depend on network or caches."""

from copy import deepcopy

from royal_road.sources import publish_snapshot

TIME = "2026-09-06T00:00:00Z"
AUDIO = "https://static.wikia.nocookie.net/love-live/images/1/11/Song.ogg/revision/latest?cb=1"


def payloads():
    return (
        [{"id": "1", "name": "曲", "englishName": "Song", "phoneticName": "きょく",
          "artists": ["1"], "seriesIds": ["1"], "releasedOn": "2020-01-01", "wikiAudioUrl": AUDIO, "wikiAudioUrls": [AUDIO]},
         {"id": "2", "name": "音源なし", "englishName": "音源なし", "phoneticName": None,
          "artists": ["1"], "seriesIds": ["1"], "releasedOn": None, "wikiAudioUrl": None, "wikiAudioUrls": []}],
        [{"id": "1", "name": "μ's", "englishName": "μ's"}],
        [{"id": "1", "name": "ラブライブ！", "englishName": "Love Live!"}],
    )


def evidence(data):
    result = {}
    for kind, records in zip(("songs", "artists", "series"), data):
        result[kind] = {r["id"]: {"identity": "a" * 64, "status": "missing"} for r in records}
    result["songs"]["1"].update(
        status="verified",
        page={"id": 1, "title": "Song", "revision": 3},
        file={"id": 2, "title": "File:Song.ogg", "timestamp": TIME, "sha1": "b" * 40, "url": AUDIO},
        files=[{"id": 2, "title": "File:Song.ogg", "timestamp": TIME,
                "sha1": "b" * 40, "url": AUDIO}],
    )
    return result


def write_source(directory, data=None):
    data = deepcopy(data if data is not None else payloads())
    return publish_snapshot(directory, data, started=TIME, finished=TIME, wiki=evidence(data))

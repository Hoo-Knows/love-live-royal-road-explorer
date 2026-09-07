import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

SCRIPT_DIR = Path(__file__).resolve().parents[1]
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import compile_catalog as compile_cli  # noqa: E402
from royal_road.ll_fans import fetch_ll_fans, paginate  # noqa: E402
from royal_road.metadata import parse_source_catalog  # noqa: E402
from royal_road.io_utils import canonical_hash  # noqa: E402
from royal_road.sources import load_metadata_snapshot, local_metadata_snapshot, publish_snapshot, validate_payloads  # noqa: E402
from royal_road.wiki import (  # noqa: E402
    PageHTML, Wiki, WikiUnavailable, credit_matches, enrich, recording_candidates, source_identity,
    validate_corrections, vocal_recording_candidates,
)
from source_fixtures import AUDIO, evidence, payloads, write_source  # noqa: E402


def corrections():
    return {"schemaVersion": "1.0.0", "songs": {}, "artists": {}, "series": {}}


def identities():
    return {s["id"]: {"artistVariants": [{"id": "99", "name": None}], "seriesIds": [1]}
            for s in payloads()[0]}


def page(html, title="Song"):
    return {"page": {"id": 1, "title": title, "revision": 3}, "root": PageHTML(html).root,
            "names": [title], "lead": "Song is a single by μ's."}


def row(title="Song", file="Song.ogg", duration="4:00"):
    return (f'<table><tr><td>{title}</td><td>{duration}</td><td><audio>'
            f'<a href="/wiki/File:{file}">audio</a></audio></td></tr></table>')


class SourceTests(unittest.TestCase):
    def test_refresh_generates_independent_snapshot_and_fetch_failure_preserves_it(self):
        import refresh_source
        from royal_road.io_utils import atomic_write_json
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp)
            atomic_write_json(target / "overrides.json", corrections())
            wiki = Mock()
            wiki.discover.return_value = ([page(row())], False)
            wiki.file.return_value = evidence(payloads())["songs"]["1"]["file"]
            with patch.object(refresh_source, "fetch_ll_fans", return_value=(payloads(), identities())), patch.object(
                refresh_source, "Wiki", return_value=wiki
            ):
                result = refresh_source.refresh(target / "source", target / "overrides.json", Mock(), lambda _: None)
            self.assertEqual(local_metadata_snapshot(target / "source")["snapshotId"], result["snapshotId"])
            saved = (target / "source/.snapshot.json").read_bytes()
            with patch.object(refresh_source, "fetch_ll_fans", side_effect=ValueError("Bad pagination")):
                with self.assertRaises(ValueError):
                    refresh_source.refresh(target / "source", target / "overrides.json", Mock(), lambda _: None)
            self.assertEqual(saved, (target / "source/.snapshot.json").read_bytes())

    def test_retry_failed_requires_an_existing_valid_snapshot(self):
        import refresh_source
        with tempfile.TemporaryDirectory() as temp, patch.object(refresh_source, "fetch_ll_fans") as fetch:
            target = Path(temp)
            with self.assertRaisesRegex(ValueError, "requires a valid existing source snapshot"):
                refresh_source.refresh(target / "source", target / "overrides.json", Mock(),
                                       lambda _: None, retry_failed_songs=True)
            fetch.assert_not_called()

    def test_retry_failed_reuses_successes_and_retries_only_failed_songs(self):
        first = payloads()
        failed_name = first[0][1]["name"]
        initial_wiki = Mock()
        initial_wiki.discover.side_effect = lambda name, *args, **kwargs: (
            ([], False) if name == failed_name else ([page(row())], False))
        initial_wiki.file.return_value = evidence(first)["songs"]["1"]["file"]
        initial_evidence = enrich(first, identities(), corrections(), initial_wiki, log=lambda _: None)
        self.assertEqual(initial_evidence["songs"]["1"]["status"], "verified")
        self.assertEqual(initial_evidence["songs"]["2"]["status"], "missing")

        retry_wiki = Mock()
        retry_wiki.discover.return_value = ([page(row())], False)
        retry_wiki.file.return_value = evidence(first)["songs"]["1"]["file"]
        fresh = payloads()
        result = enrich(fresh, identities(), corrections(), retry_wiki,
                        previous=({"wiki": initial_evidence}, copy.deepcopy(first)),
                        log=lambda _: None, retry_failed_songs=True)
        self.assertEqual(retry_wiki.discover.call_count, 1)
        self.assertEqual(result["songs"]["1"], initial_evidence["songs"]["1"])
        self.assertEqual(result["songs"]["2"]["status"], "verified")
        self.assertEqual(fresh[0][1]["wikiAudioUrl"], AUDIO)

    def test_initial_wiki_outage_does_not_publish_unverified_sources(self):
        import refresh_source
        from royal_road.io_utils import atomic_write_json
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp)
            atomic_write_json(target / "overrides.json", corrections())
            wiki = Mock()
            wiki.discover.side_effect = WikiUnavailable("offline")
            data = payloads()
            for song in data[0]:
                song["wikiAudioUrl"] = None
                song["wikiAudioUrls"] = []
            with patch.object(refresh_source, "fetch_ll_fans", return_value=(data, identities())), patch.object(
                refresh_source, "Wiki", return_value=wiki
            ), self.assertRaisesRegex(ValueError, "wiki access is required"):
                refresh_source.refresh(target / "source", target / "overrides.json", Mock(), lambda _: None)
            self.assertFalse((target / "source/.snapshot.json").exists())

    def test_page_reads_unwrapped_japanese_title_and_infobox_values(self):
        wiki = Wiki(Mock())
        html = ('<div class="mw-parser-output"><aside><div data-source="Japanese Name">'
                '<h3>Kanji</h3><div class="pi-data-value"><ruby><rb>Name</rb><rt>名前</rt></ruby></div></div></aside>'
                '<b>Song</b><span class="t_nihongo_kanji">曲</span>'
                "<p>A single by μ's.</p><h2>Tracks</h2>"
                '<b>Different</b><span class="t_nihongo_kanji">別曲</span></div>')
        wiki.api = Mock(return_value={"parse": {"title": "Song", "pageid": 1, "revid": 2, "text": {"*": html}}})
        result = wiki.page("Song")
        self.assertIn("曲", result["names"])
        self.assertIn("名前", result["names"])
        self.assertNotIn("別曲", result["names"])

    def test_plain_parenthetical_titles_translations_ruby_and_subpage_display(self):
        wiki = Wiki(Mock())
        cases = [
            ("Genyou Yakou", '<b>Genyou Yakou</b> (\u7729\u8000\u591c\u884c <i>lit. Dazzling Night</i>) is a single.', "\u7729\u8000\u591c\u884c"),
            ("Oyasuminasan!", '<p><b>Oyasuminasan!</b><span class="nihongo_kanji">\u304a\u3084\u3059\u307f\u306a\u3055\u3093\uff01, lit. Goodnight</span></p>', "\u304a\u3084\u3059\u307f\u306a\u3055\u3093\uff01"),
            ("Fantasy", '<b>Fantasy</b> (<ruby>37.5\u2103<rt>\u30ca\u30ca\u30c9\u30b4\u30d6</rt></ruby>\u306e\u30d5\u30a1\u30f3\u30bf\u30b8\u30fc) is a song.', "37.5\u2103\u306e\u30d5\u30a1\u30f3\u30bf\u30b8\u30fc"),
        ]
        for title, html, expected in cases:
            wiki.api = Mock(return_value={"parse": {"title": title, "pageid": 1, "revid": 2,
                                                    "text": {"*": '<div class="mw-parser-output">' + html + '<h2>Lyrics</h2><b>Unrelated</b></div>'}}})
            result = wiki.page(title)
            from royal_road.wiki import normalized
            self.assertIn(normalized(expected), [normalized(n) for n in result["names"]])
            self.assertNotIn("Unrelated", result["names"])
        wiki.api = Mock(return_value={"parse": {"title": "Character/Spinoff", "pageid": 1, "revid": 2,
            "text": {"*": '<aside><h2 data-source="name">Yohane</h2></aside><p>Yohane is a singer.</p>'}}})
        self.assertEqual(wiki.page("Character/Spinoff")["displayName"], "Yohane")

    def test_recording_table_verifies_spelling_upload_suffix_and_short_complete_song(self):
        for title, filename, duration in [
            ("Koi no Signal Rin rin rin!", "Koi_no_Shigunaru_Rin_Rin_Rin!.ogg", "4:22"),
            ("Song", "Song_(Fixed).ogg", "4:00"),
            ("1.2.3!", "1.2.3!.mp3", "3:46"),
            ("Afureru Kotoba", "21._Afureru_Kotoba.ogg", "1:55"),
            ("LIVE with a smile!", "LIVE_with_a_smile!.ogg", "5:00"),
        ]:
            with self.subTest(title=title):
                self.assertEqual(len(recording_candidates(page(row(title, filename, duration), title), title)), 1)
        self.assertEqual(recording_candidates(page(row("Song (Kanon)", "Song_Kanon.ogg")), "Song"), [])
        self.assertEqual(recording_candidates(page(row("Song", "Song_preview.ogg")), "Song"), [])

    def test_discovery_searches_beyond_three_and_does_not_retain_episode_hint(self):
        wiki = Wiki(Mock())
        episode = {**page(""), "episode": True}
        song = page(row())
        song["page"] = {"id": 2, "title": "Song", "revision": 4}
        other = {**page(""), "names": ["Other"]}
        wiki.api = Mock(return_value={"query": {"search": [{"title": str(i)} for i in range(4)]}})
        wiki.page = Mock(side_effect=[episode, other, other, other, song])
        self.assertEqual(wiki.discover("Song", hint="Episode", kind="songs")[0], [song])

    def test_composite_credit_separators_preserve_name_punctuation(self):
        from royal_road.wiki import credit_parts
        artists = [{"name": "Aqours"}, {"name": "Liella!"}, {"name": "Mira-Cra Park!"}, {"name": "Aqours・Liella!"}]
        self.assertEqual(credit_parts("Aqours\u30fbLiella!", artists), ["Aqours", "Liella!"])
        self.assertEqual(credit_parts("Aqours feat. \u521d\u97f3\u30df\u30af", artists), ["Aqours", "\u521d\u97f3\u30df\u30af"])
        self.assertEqual(credit_parts("\u6f81\u8c37\u304b\u306e\u3093\uff06\u5510\u53ef\u53ef", artists), ["\u6f81\u8c37\u304b\u306e\u3093", "\u5510\u53ef\u53ef"])
        self.assertEqual(credit_parts("\u30a6\u30a3\u30fc\u30f3\u30fb\u30de\u30eb\u30ac\u30ec\u30fc\u30c6", artists), ["\u30a6\u30a3\u30fc\u30f3\u30fb\u30de\u30eb\u30ac\u30ec\u30fc\u30c6"])

    def test_performer_mismatch_is_diagnostic_and_all_vocal_alternatives_are_kept(self):
        wiki = Mock()
        recordings = row() + row("Song (Kanon)", "Song_Kanon.ogg") + row(
            "Song (Off Vocal)", "Song_off_vocal.ogg")
        wrong = {**page(recordings), "lead": "A song by Aqours"}
        wiki.discover.return_value = ([wrong], False)
        primary = evidence(payloads())["songs"]["1"]["file"]
        alternate_url = AUDIO.replace("Song.ogg", "Song_Kanon.ogg")
        wiki.file.side_effect = lambda title: primary if title == "File:Song.ogg" else {
            **primary, "id": 3, "title": title, "url": alternate_url,
        }
        value = corrections()
        value["artists"]["1"] = {"englishName": "μ's"}
        data = payloads()
        result = enrich(data, identities(), value, wiki, log=lambda _: None)
        self.assertEqual(result["songs"]["1"]["status"], "verified")
        self.assertFalse(result["songs"]["1"]["performerMatch"])
        self.assertEqual(data[0][0]["wikiAudioUrls"], [AUDIO, alternate_url])
        public_song = parse_source_catalog(*data)[0]
        self.assertEqual(public_song["audioUrl"], AUDIO)
        self.assertEqual(public_song["artistNames"], ["μ's"])

    def test_notice_wrapper_does_not_import_track_names_or_lyrics_as_identity(self):
        wiki = Wiki(Mock())
        html = ('<div class="mw-parser-output"><div class="notice">'
                '<p><b>Song</b> (\u66f2) is an insert song in the first episode.</p>'
                '<div class="mw-heading"><h2>Lyrics</h2></div><p><b>Unrelated</b> (\u5225\u66f2)</p></div></div>')
        wiki.api = Mock(return_value={"parse": {"title": "Song", "pageid": 1, "revid": 2, "text": {"*": html}}})
        result = wiki.page("Song")
        self.assertIn("\u66f2", result["names"])
        self.assertNotIn("\u5225\u66f2", result["names"])
        self.assertNotIn("Unrelated", result["lead"])
        self.assertFalse(result["episode"])

    def test_title_tolerance_does_not_conflate_numbered_recording_versions(self):
        good = page(row("Diamond Princess no Yuutsu", "Diamond_Princess_no_Yuutsu.ogg"),
                    "Diamond Princess no Yuuutsu")
        self.assertEqual(len(recording_candidates(good, good["page"]["title"])), 1)
        bad = page(row("Long Song Title 2024", "Long_Song_Title_2024.ogg"), "Long Song Title 2023")
        self.assertEqual(recording_candidates(bad, "Long Song Title 2023"), [])

    def test_explicit_recording_can_resolve_broad_group_vs_member_credit(self):
        wiki = Mock()
        selected = {**page(row("Archive recording", "Unexpected_upload.ogg")),
                    "lead": "A song by four individually named members."}
        wiki.discover.return_value = ([selected], False)
        selected_file = {**evidence(payloads())["songs"]["1"]["file"],
                         "title": "File:Unexpected_upload.ogg"}
        wiki.file.return_value = selected_file
        value = corrections()
        value["artists"]["1"] = {"englishName": "μ's"}
        value["songs"]["1"] = {"wikiPage": "Song", "wikiFile": "File:Unexpected_upload.ogg"}
        data = payloads()
        result = enrich(data, identities(), value, wiki, log=lambda _: None)
        self.assertEqual(result["songs"]["1"]["selection"], "override")
        self.assertEqual(data[0][0]["wikiAudioUrl"], AUDIO)
    def test_composite_aliases_preserve_slots_and_independent_page_evidence(self):
        data = payloads()
        data[1].append({"id": "2", "name": "Aqours", "englishName": "Aqours"})
        data[1].append({"id": "3", "name": "μ's＆Aqours", "englishName": "μ's＆Aqours"})
        wiki = Mock()
        def discover(name, *args, **kwargs):
            return [page("", title=name)], False
        wiki.discover.side_effect = discover
        result = enrich(data, identities(), corrections(), wiki, log=lambda _: None)
        self.assertEqual(data[1][2]["englishName"], "μ's, Aqours")
        self.assertEqual(result["artists"]["3"]["components"], [{"artistId": "1"}, {"artistId": "2"}])

    def test_review_report_lists_override_choices_without_hiding_missing_audio(self):
        from royal_road.source_report import source_review
        data = payloads()
        marker = {"snapshotId": "a" * 64, "wiki": evidence(data)}
        marker["wiki"]["songs"]["1"].update(status="missing", reason="no_selectable_recording",
            recordings=[{"title": "File:Song (Singer).ogg", "reasons": ["different_title_or_version"]}])
        result = source_review(marker, data)
        self.assertIn("no_selectable_recording", result)
        self.assertIn("File:Song (Singer).ogg", result)
        self.assertIn("wikiPage / wikiFile", result)

    def test_pagination_uses_post_variables_and_preserves_order(self):
        client = Mock()
        def respond(url, payload):
            number = payload["variables"]["page"]
            self.assertIn("first: $first", payload["query"])
            return {"data": {"songs": {"data": [{"id": str(number)}],
                    "paginatorInfo": {"currentPage": number, "lastPage": 2,
                                      "total": 2, "count": 1, "hasMorePages": number == 1}}}}
        client.json.side_effect = respond
        self.assertEqual([r["id"] for r in paginate(client, "songs", "id", 1)], ["1", "2"])

    def test_pagination_rejects_repeated_ids_changed_totals_and_bad_counts(self):
        good = {"data": {"songs": {"data": [{"id": "1"}],
                "paginatorInfo": {"currentPage": 1, "lastPage": 2,
                                  "total": 2, "count": 1, "hasMorePages": True}}}}
        for change in ("duplicate", "total", "count", "hasMorePages"):
            first, second = copy.deepcopy(good), copy.deepcopy(good)
            info = second["data"]["songs"]["paginatorInfo"]
            info.update(currentPage=2, hasMorePages=False)
            if change != "duplicate":
                second["data"]["songs"]["data"] = [{"id": "2"}]
                info[change] = {"total": 3, "count": 0, "hasMorePages": True}[change]
            client = Mock()
            client.json.side_effect = [first, second]
            with self.subTest(change=change), self.assertRaises(ValueError):
                paginate(client, "songs", "id", 1)

    def test_variant_id_resolves_to_base_artist_and_keeps_credit_order(self):
        song = {"id": "1", "name": "Future", "phoneticName": None, "releasedOn": "2099-01-01",
                "seriesIds": [1], "artistVariants": [
                    {"id": "88", "name": None, "artistConfigurationCastSet": {
                        "id": "77", "artistConfiguration": {"id": "66", "artist": {"id": "2", "name": "B"}}}},
                    {"id": "99", "name": None, "artistConfigurationCastSet": {
                        "id": "55", "artistConfiguration": {"id": "44", "artist": {"id": "1", "name": "A"}}}},
                ]}
        with patch("royal_road.ll_fans.paginate", side_effect=[
            [song], [{"id": "1", "name": "A"}, {"id": "2", "name": "B"}]
        ]), patch("royal_road.ll_fans.graphql", return_value={"seriesList": [{"id": "1", "name": "Series"}]}):
            data, upstream = fetch_ll_fans(Mock())
        self.assertEqual(data[0][0]["artists"], ["2", "1"])
        self.assertEqual(data[0][0]["releasedOn"], "2099-01-01")
        self.assertEqual(upstream["1"], song)

    def test_creator_import_filters_roles_groups_dual_credits_and_preserves_aliases(self):
        song = {
            "id": "1", "name": "Future", "phoneticName": None, "releasedOn": "2099-01-01",
            "seriesIds": [1], "artistVariants": [], "songCredits": [
                {"staffType": {"id": "1", "name": "作詞"}},
                {"staffType": {"id": "4", "name": "補作曲"}},
                {"staffType": {"id": "2", "name": "作曲"}, "staffName": {
                    "id": "501", "name": "別名", "staff": {"id": "10", "name": "正規名",
                    "staffNames": [{"id": "10", "name": "正規名"}, {"id": "502", "name": "別名"},
                                    {"id": "503", "name": "英語名"}]}}},
                {"staffType": {"id": "3", "name": "編曲"}, "staffName": {
                    "id": "10", "name": "正規名", "staff": {"id": "10", "name": "正規名",
                    "staffNames": [{"id": "10", "name": "正規名"}, {"id": "503", "name": "英語名"}]}}},
                {"staffType": {"id": "2", "name": "作曲"}, "staffName": {
                    "id": "601", "name": "別の人", "staff": {"id": "11", "name": "同名",
                    "staffNames": [{"id": "11", "name": "同名"}]}}},
            ]}
        artists = [{"id": "1", "name": "A"}]
        song["artistVariants"] = [{"artistConfigurationCastSet": {
            "artistConfiguration": {"artist": {"id": "1", "name": "A"}}}}]
        with patch("royal_road.ll_fans.paginate", side_effect=[[song], artists]), patch(
                "royal_road.ll_fans.graphql", return_value={"seriesList": [{"id": "1", "name": "Series"}]}):
            data, _ = fetch_ll_fans(Mock())

        self.assertEqual(data[0][0]["creators"], [
            {"id": "10", "name": "正規名", "aliases": ["別名", "英語名"]},
            {"id": "11", "name": "同名", "aliases": ["別の人"]},
        ])

    def test_creator_import_handles_missing_credits(self):
        song = {"id": "1", "name": "Future", "phoneticName": None, "releasedOn": None,
                "seriesIds": [1], "artistVariants": [{"artistConfigurationCastSet": {
                    "artistConfiguration": {"artist": {"id": "1", "name": "A"}}}}], "songCredits": []}
        with patch("royal_road.ll_fans.paginate", side_effect=[[song], [{"id": "1", "name": "A"}]]), patch(
                "royal_road.ll_fans.graphql", return_value={"seriesList": [{"id": "1", "name": "Series"}]}):
            data, _ = fetch_ll_fans(Mock())
        self.assertEqual(data[0][0]["creators"], [])

    def test_creator_metadata_does_not_change_wiki_source_identity(self):
        data = payloads()
        record = data[0][0]
        artists = {artist["id"]: artist for artist in data[1]}
        before = source_identity("songs", record, identities(), artists, {})
        changed = copy.deepcopy(record)
        changed["creators"] = [{"id": "999", "name": "別の作曲者", "aliases": ["Other"]}]
        after = source_identity("songs", changed, identities(), artists, {})
        self.assertEqual(before, after)

    def test_validation_rejects_duplicates_and_dangling_references(self):
        for change in ("duplicate", "reference", "field"):
            data = payloads()
            if change == "duplicate":
                data[1].append(dict(data[1][0]))
            elif change == "reference":
                data[0][0]["artists"] = ["99"]
            else:
                data[0][0].pop("name")
            with self.subTest(change=change), self.assertRaises(ValueError):
                validate_payloads(*data)

    def test_snapshot_is_deterministic_and_rejects_corruption(self):
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp)
            first = write_source(target)
            second = publish_snapshot(target, payloads(), started="2026-09-07T00:00:00Z",
                                      finished="2026-09-07T00:00:01Z", wiki=evidence(payloads()))
            self.assertEqual(first["snapshotId"], second["snapshotId"])
            self.assertEqual(local_metadata_snapshot(target)["snapshotId"], first["snapshotId"])
            path = target / "song-info.json"
            path.write_bytes(path.read_bytes() + b" ")
            with self.assertRaisesRegex(ValueError, "does not match"):
                local_metadata_snapshot(target)

    def test_legacy_snapshot_is_only_accepted_for_refresh_reuse(self):
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp)
            marker = write_source(target)
            song_path = target / "song-info.json"
            songs = json.loads(song_path.read_text(encoding="utf-8"))
            for song in songs:
                song.pop("creators", None)
            body = (json.dumps(songs, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
            song_path.write_bytes(body)
            marker["schemaVersion"] = "2.0.0"
            marker["files"]["song-info.json"] = hashlib.sha256(body).hexdigest()
            marker["snapshotId"] = canonical_hash({
                key: marker[key] for key in ("schemaVersion", "providers", "files", "wiki")
            })
            (target / ".snapshot.json").write_text(
                json.dumps(marker, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )

            with self.assertRaises(ValueError):
                load_metadata_snapshot(target)
            loaded_marker, loaded_payloads = load_metadata_snapshot(target, allow_legacy=True)
            self.assertEqual(loaded_marker["schemaVersion"], "2.0.0")
            self.assertNotIn("creators", loaded_payloads[0][0])

    def test_interrupted_publication_keeps_marker_and_rejects_mixed_files(self):
        from royal_road.io_utils import atomic_write_bytes
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp)
            first = write_source(target)
            changed = payloads()
            changed[0][0]["englishName"] = "Correction"
            count = 0
            def interrupted(path, body):
                nonlocal count
                count += 1
                if count == 2:
                    raise OSError("Interrupted")
                atomic_write_bytes(path, body)
            with patch("royal_road.sources.atomic_write_bytes", side_effect=interrupted):
                with self.assertRaises(OSError):
                    write_source(target, changed)
            self.assertEqual(json.loads((target / ".snapshot.json").read_text())["snapshotId"], first["snapshotId"])
            with self.assertRaises(ValueError):
                local_metadata_snapshot(target)

    def test_partial_source_never_uses_catalog_fallback(self):
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp)
            (target / "song-info.json").write_text("[]")
            with patch.object(compile_cli, "_source_songs_from_catalog") as fallback:
                self.assertEqual(compile_cli.main(["--source-dir", str(target)]), 2)
                fallback.assert_not_called()

    def test_offline_compilation_reuses_analysis_across_metadata_changes(self):
        from royal_road.io_utils import atomic_write_json
        from royal_road.state import analysis_state, build_manifest
        from royal_road.detector import analysis_version
        root = SCRIPT_DIR.parent
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp)
            snapshot = write_source(target / "source")
            raw = {"schemaVersion": "2.0.0", "songId": "1", "durationSeconds": 10, "segments": [
                {"index": i, "startSeconds": i + 1, "endSeconds": i + 2, "label": label}
                for i, label in enumerate(["C:maj", "D:7", "B:min", "E:min"])
            ]}
            atomic_write_json(target / "raw" / "1.json", raw)
            atomic_write_json(target / "manifest.json", build_manifest(snapshot["snapshotId"], {
                "1": analysis_state(status="analyzed", audio_url=AUDIO, audio_sha256="c" * 64,
                                    analysis_version=analysis_version()),
            }))
            args = ["--source-dir", str(target / "source"), "--raw-dir", str(target / "raw"),
                    "--catalog", str(target / "catalog.json"), "--manifest", str(target / "manifest.json"),
                    "--patterns", str(root / "data/patterns.json"), "--overrides", str(root / "data/overrides.json")]
            original_raw = (target / "raw" / "1.json").read_bytes()
            with patch("urllib.request.urlopen", side_effect=AssertionError("Offline compile opened network")), patch(
                "royal_road.detector.run_detector", side_effect=AssertionError("Compile invoked recognition")
            ):
                self.assertEqual(compile_cli.main(args), 0)
                before = json.loads((target / "catalog.json").read_text(encoding="utf-8"))
                before_state = json.loads((target / "manifest.json").read_text())["songs"]["1"]
                data = payloads()
                data[0][0]["englishName"] = "Corrected title"
                write_source(target / "source", data)
                self.assertEqual(compile_cli.main(args), 0)
                after = json.loads((target / "catalog.json").read_text(encoding="utf-8"))
                self.assertEqual(before["songs"][0]["occurrences"], after["songs"][0]["occurrences"])
                self.assertEqual(before_state, json.loads((target / "manifest.json").read_text())["songs"]["1"])
                self.assertEqual(original_raw, (target / "raw" / "1.json").read_bytes())

    def test_aliases_keep_duplicate_credits_and_fallback_slots(self):
        data = payloads()
        data[0][0]["artists"] = ["1", "2", "1"]
        data[1].append({"id": "2", "name": "名前", "englishName": "Name"})
        result = parse_source_catalog(*data)[0]
        self.assertEqual(result["artistAliases"], ["μ's", "Name", "μ's"])

    def test_recordings_reject_instrumental_short_live_and_alternate_versions(self):
        html = row(file="03._Song.ogg") + row("Song (Off Vocal)", "Song_off_vocal.ogg") + row("Song", "Song_short.ogg", "1:20")
        html += row("Song", "Song_(Live).ogg") + row("Song", "Song_Honoka.ogg") + row("Song", "Song_live_ver.ogg") + row("Song (Solo Ver.)", "Song_solo_ver.ogg")
        found = recording_candidates(page(html), "Song")
        self.assertEqual([f["title"] for f in found], ["File:03. Song.ogg"])
        self.assertEqual(len(recording_candidates(page(row() + row(file="Song_full.ogg")), "Song")), 2)
        self.assertEqual(len(recording_candidates(page(row()), "Different")), 1)  # canonical page title

    def test_all_vocal_recordings_keep_row_order_and_explicit_file_moves_first(self):
        recordings = page(row() + row("Song (Kanon)", "Song_Kanon.ogg")
                          + row("Song (Off Vocal)", "Song_off_vocal.ogg"))
        self.assertEqual([item["title"] for item in vocal_recording_candidates(recordings, "Song")],
                         ["File:Song.ogg", "File:Song Kanon.ogg"])
        unrelated = page(row("Other Song", "Other_Song.ogg") + row("Song (Kanon)", "Song_Kanon.ogg"))
        self.assertEqual([item["title"] for item in vocal_recording_candidates(unrelated, "Song")],
                         ["File:Song Kanon.ogg"])
        self.assertEqual([item["title"] for item in vocal_recording_candidates(
            recordings, "Song", "File:Song Kanon.ogg")],
            ["File:Song Kanon.ogg", "File:Song.ogg"])
        self.assertEqual(vocal_recording_candidates(recordings, "Song", "File:Missing.ogg"), [])

    def test_explicit_file_selection_still_requires_file_on_selected_page(self):
        self.assertEqual(recording_candidates(page(row()), "Song", "File:Missing.ogg"), [])
        self.assertEqual(len(recording_candidates(page(row()), "Song", "File:Song.ogg")), 1)

    def test_performer_match_is_diagnostic(self):
        self.assertFalse(credit_matches(page(row()), [{"name": "Aqours", "englishName": "Aqours"}]))
        self.assertTrue(credit_matches(page(row()), payloads()[1]))

    def test_discovery_handles_redirects_and_rejects_ambiguous_identity(self):
        wiki = Wiki(Mock())
        wiki.api = Mock(return_value={"query": {"search": [{"title": "One"}, {"title": "Two"}]}})
        a, b = page(row()), page(row())
        b["page"] = {"id": 2, "title": "Song", "revision": 4}
        wiki.page = Mock(side_effect=[a, b])
        self.assertTrue(wiki.discover("Song")[1])
        wiki.page = Mock(return_value=a)
        self.assertEqual(wiki.discover("Alias", "Redirect")[0], [a])
        wiki.page.assert_called_once_with("Redirect")

    def test_corrections_validate_ids_and_null_audio(self):
        data = payloads()
        value = corrections()
        value["songs"]["999"] = {"englishName": "Unknown"}
        with self.assertRaises(ValueError):
            validate_corrections(value, data)
        value["songs"] = {"1": {"audio": AUDIO}}
        with self.assertRaises(ValueError):
            validate_corrections(value, data)
        value["songs"] = {"1": {"wikiFile": "File:Song.ogg"}}
        with self.assertRaises(ValueError):
            validate_corrections(value, data)

    def test_corrections_override_names_and_explicit_null_audio(self):
        data, value = payloads(), corrections()
        value["songs"]["1"] = {"englishName": "Corrected", "audio": None}
        wiki = Mock()
        wiki.discover.return_value = ([page(row())], False)
        wiki.file.return_value = evidence(data)["songs"]["1"]["file"]
        result = enrich(data, identities(), value, wiki, log=lambda _: None)
        self.assertEqual(data[0][0]["englishName"], "Corrected")
        self.assertIsNone(data[0][0]["wikiAudioUrl"])
        self.assertEqual(result["songs"]["1"]["status"], "unavailable")

    def test_outage_preserves_verified_name_when_recording_was_missing(self):
        data, value = payloads(), corrections()
        wiki = Mock()
        wiki.discover.return_value = ([page(row())], False)
        wiki.file.return_value = None
        for song in data[0]:
            song["wikiAudioUrl"] = None
        verified = enrich(data, identities(), value, wiki, log=lambda _: None)
        self.assertEqual(verified["songs"]["1"]["status"], "missing")
        previous = ({"wiki": verified}, copy.deepcopy(data))
        wiki.discover.side_effect = WikiUnavailable("outage")
        fresh = payloads()
        fresh[0][0]["wikiAudioUrl"] = None
        fresh[0][0]["wikiAudioUrls"] = []
        result = enrich(fresh, identities(), value, wiki, previous=previous, log=lambda _: None)
        self.assertEqual(result["songs"]["1"]["status"], "stale")
        self.assertEqual(fresh[0][0]["englishName"], "Song")
        self.assertIsNone(fresh[0][0]["wikiAudioUrl"])

    def test_outage_only_reuses_independently_verified_compatible_enrichment(self):
        data, value = payloads(), corrections()
        wiki = Mock()
        wiki.discover.return_value = ([page(row())], False)
        wiki.file.return_value = evidence(data)["songs"]["1"]["file"]
        verified = enrich(data, identities(), value, wiki, log=lambda _: None)
        # Artist pages in this fixture need to retain the actual performer name.
        data[1][0]["englishName"] = "μ's"
        verified["songs"]["1"].update(status="verified", file=evidence(data)["songs"]["1"]["file"])
        data[0][0]["wikiAudioUrl"] = AUDIO
        previous = ({"wiki": verified}, copy.deepcopy(data))
        wiki.discover.side_effect = WikiUnavailable("outage")
        fresh = payloads()
        result = enrich(fresh, identities(), value, wiki, previous=previous, log=lambda _: None)
        self.assertEqual(result["songs"]["1"]["status"], "stale")
        self.assertEqual(fresh[0][0]["wikiAudioUrl"], AUDIO)
        changed = identities()
        changed["1"]["artistVariants"][0]["id"] = "100"
        fresh = payloads()
        fresh[0][0]["wikiAudioUrl"] = None
        fresh[0][0]["wikiAudioUrls"] = []
        result = enrich(fresh, changed, value, wiki, previous=previous, log=lambda _: None)
        self.assertEqual(result["songs"]["1"]["status"], "unresolved")
        self.assertIsNone(fresh[0][0]["wikiAudioUrl"])


if __name__ == "__main__":
    unittest.main()

"""Conservative MediaWiki discovery and recording verification using stdlib HTML."""

from __future__ import annotations

from html.parser import HTMLParser
import re
import unicodedata
from urllib.parse import quote, unquote, urlencode, urlparse

from .io_utils import canonical_hash
from .sources import WIKI_API


def normalized(value):
    text = unicodedata.normalize("NFKC", value).casefold().replace("’", "'")
    return "".join(c for c in text if c.isalnum())


class Node:
    def __init__(self, tag="", attrs=None, parent=None):
        self.tag, self.attrs, self.parent = tag, dict(attrs or []), parent
        self.children = []

    def text(self):
        return " ".join(child.text() if isinstance(child, Node) else child for child in self.children).strip()

    def walk(self, tag=None):
        for child in self.children:
            if isinstance(child, Node):
                if tag is None or child.tag == tag:
                    yield child
                yield from child.walk(tag)

    def ancestor(self, tag):
        node = self.parent
        while node:
            if node.tag == tag:
                return node
            node = node.parent
        return None


class PageHTML(HTMLParser):
    def __init__(self, html):
        super().__init__(convert_charrefs=True)
        self.root = Node()
        self.current = self.root
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        node = Node(tag, attrs, self.current)
        self.current.children.append(node)
        if tag not in {"br", "hr", "img", "input", "meta", "link", "source", "wbr", "area", "embed"}:
            self.current = node

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        self.handle_endtag(tag)

    def handle_endtag(self, tag):
        node = self.current
        while node.parent:
            if node.tag == tag:
                self.current = node.parent
                return
            node = node.parent

    def handle_data(self, data):
        self.current.children.append(data)


def base_text(node):
    """Visible base spelling: ruby readings must not be spliced into names."""
    if not isinstance(node, Node):
        return node
    if node.tag in {"rt", "rp"}:
        return ""
    return "".join(base_text(child) for child in node.children)


def clean_name(value):
    value = re.split(r",?\s*\blit\.\s*", value, maxsplit=1, flags=re.I)[0]
    return re.sub(r"\s+", " ", value).strip()


def credit_parts(name, artists):
    """Split only at credit separators, preserving punctuation inside names."""
    pieces = re.split(r"\u3001|,|[\uff06&\u00d7]|\s+feat\.\s+", name, flags=re.I)
    result = []
    known = sorted((a["name"] for a in artists if a["name"] != name), key=len, reverse=True)
    for piece in pieces:
        piece = piece.strip()
        # Middle dots also occur inside real names. Split only known identities.
        def split_known(rest):
            for candidate in known:
                if rest == candidate:
                    return [candidate]
                if rest.startswith(candidate + "\u30fb"):
                    tail = split_known(rest[len(candidate) + 1:])
                    if tail:
                        return [candidate, *tail]
            return None
        result.extend(split_known(piece) or [piece])
    return [part for part in result if part]


class WikiUnavailable(RuntimeError):
    pass


class Wiki:
    def __init__(self, client):
        self.client = client
        self.memo = {}

    def api(self, **params):
        # Literal MediaWiki separators are valid in query strings.
        url = WIKI_API + "?" + urlencode({**params, "format": "json"}, quote_via=quote, safe="|:")
        if url not in self.memo:
            try:
                payload = self.client.json(url)
            except (OSError, ValueError) as error:
                raise WikiUnavailable(str(error)) from error
            if "error" in payload and payload["error"].get("code") not in {"missingtitle", "invalidtitle"}:
                raise WikiUnavailable(str(payload["error"]))
            self.memo[url] = payload
        return self.memo[url]

    def page(self, title):
        payload = self.api(action="parse", page=title.replace(" ", "_"), prop="text|revid", redirects=1)
        value = payload.get("parse")
        if not value:
            return None
        root = PageHTML(value["text"]["*"]).root
        main = next((n for n in root.walk("div") if "mw-parser-output" in n.attrs.get("class", "")), root)
        # Prune the opening tree recursively: malformed notice wrappers can
        # contain the rest of the article, including headings and track lists.
        infoboxes = []
        stopped = False
        def opening_node(node):
            nonlocal stopped
            if stopped:
                return None
            if not isinstance(node, Node):
                return node
            if node.tag == "aside":
                infoboxes.append(node)
                return None
            if node.tag == "table":
                return None
            if node.attrs.get("id") == "toc" or node.tag in {"h1", "h2", "h3"}:
                stopped = True
                return None
            clone = Node(node.tag, node.attrs.items())
            for child in node.children:
                found = opening_node(child)
                if found is not None:
                    clone.children.append(found)
            return clone
        opening = []
        for node in main.children:
            found = opening_node(node)
            if found is not None:
                opening.append(found)
        lead_text = " ".join(base_text(n) for n in opening)
        name_keys = {"name", "japanese", "japanese name", "kanji", "romaji", "romaji name", "romanized name"}
        names = [value["title"]]
        display = None
        for box in infoboxes:
            for child in box.walk():
                key = child.attrs.get("data-source", "").lower()
                if key in name_keys:
                    values = [base_text(n) for n in child.walk() if "pi-data-value" in n.attrs.get("class", "")]
                    names.extend(values or [base_text(child)])
                    if key == "name":
                        display = (values or [base_text(child)])[0]
                if child.tag in {"rb", "rt"}:
                    names.append(child.text())
        # Plain parenthetical Japanese titles are common. Exclude translation
        # notes and ruby readings, which are not part of the base spelling.
        for text in re.findall(r"[(\uff08]([^()\uff08\uff09]+)[)\uff09]", lead_text):
            text = clean_name(text)
            if re.search(r"[\u3040-\u30ff\u3400-\u9fff]", text):
                names.append(text)
        for node in opening:
            if not isinstance(node, Node):
                continue
            for child in [node, *node.walk()]:
                if child.tag == "b" or "nihongo_kanji" in child.attrs.get("class", ""):
                    names.append(clean_name(base_text(child)))
                if child.tag == "ruby":
                    names.append(base_text(child))
                    readings = "".join(n.text() for n in child.walk("rt"))
                    if readings:
                        names.append(base_text(child) + "(" + readings + ")")
        names = list(dict.fromkeys(clean_name(n) for n in names if clean_name(n)))
        display = clean_name(display or value["title"])
        display = re.sub(r"\s+\(song\)$", "", display, flags=re.I)
        keys = {n.attrs.get("data-source", "").lower() for n in root.walk()}
        episode = "airdate" in keys
        return {
            "page": {"id": value["pageid"], "title": value["title"], "revision": value["revid"]},
            "root": root, "names": names, "displayName": display, "episode": episode,
            "release": "released" in keys,
            "lead": lead_text + " " + " ".join(base_text(n) for n in infoboxes),
        }

    def discover(self, name, explicit=None, hint=None, kind=None):
        if explicit:
            page = self.page(explicit)
            return ([page] if page else []), False
        matches = {}
        def accept(page):
            return (page and normalized(name) in {normalized(n) for n in page["names"]}
                    and not (kind == "songs" and page.get("episode"))
                    and not (kind == "artists" and page.get("release")))
        if hint:
            page = self.page(hint)
            if accept(page):
                matches[page["page"]["id"]] = page
                # A page without a selectable recording is only a hint.
                if kind != "songs" or vocal_recording_candidates(page, page.get("displayName", page["page"]["title"])):
                    return [page], False
        result = self.api(action="query", list="search", srsearch=name)
        candidates = result.get("query", {}).get("search", [])
        for candidate in candidates[:10]:
            page = self.page(candidate["title"])
            if accept(page):
                matches[page["page"]["id"]] = page
        return list(matches.values()), len(matches) > 1

    def files(self, titles):
        """Resolve up to 50 file titles per API request, preserving caller order separately."""
        requested = list(dict.fromkeys(titles))
        result = {}
        for offset in range(0, len(requested), 50):
            chunk = requested[offset:offset + 50]
            payload = self.api(action="query", titles="|".join(title.replace(" ", "_") for title in chunk),
                               prop="imageinfo", iiprop="url|sha1|timestamp|mime|size")
            for page in payload.get("query", {}).get("pages", {}).values():
                infos = page.get("imageinfo")
                if not infos:
                    continue
                info, url = infos[0], infos[0].get("url")
                if (info.get("mime") not in {"application/ogg", "audio/ogg", "audio/mpeg"}
                        or info.get("size", 0) <= 0 or not info.get("sha1") or not url
                        or urlparse(url).scheme != "https"
                        or urlparse(url).hostname != "static.wikia.nocookie.net"
                        or not urlparse(url).path.startswith("/love-live/images/")):
                    continue
                result[normalized(page.get("title", ""))] = {
                    "id": page["pageid"], "title": page["title"], "timestamp": info["timestamp"],
                    "sha1": info["sha1"], "url": url,
                }
        return result

    def file(self, title):
        return self.files([title]).get(normalized(title))


def performer_names(artist):
    return [part for part in re.split("[、,]", artist["englishName"]) if part.strip()]


def credit_matches(page, artists):
    lead = normalized(page["lead"])
    return all(
        all(normalized(part) in lead for part in performer_names(artist))
        or normalized(artist["name"]) in lead
        for artist in artists
    )


def recording_rows(page, title):
    """Explain each recording rejection; filename spelling is not identity."""
    rows = []
    titles = {normalized(n) for n in [title, page["page"]["title"], page.get("displayName", title)]}
    for audio in page["root"].walk("audio"):
        row = audio.ancestor("tr")
        cells = [node.text() for node in row.children if isinstance(node, Node) and node.tag in {"td", "th"}] if row else []
        files = [unquote(urlparse(a.attrs.get("href", "")).path.split("/wiki/")[-1]).replace("_", " ")
                 for a in audio.walk("a") if "/wiki/File:" in a.attrs.get("href", "")]
        for file_title in files:
            reasons = []
            # Only tolerate repeated romanized vowels (Yuuutsu / Yuutsu), not
            # arbitrary edit distance that could conflate numbered versions.
            def spelling(value):
                return re.sub(r"([aeiou])\1+", r"\1", normalized(value))
            exact_title = any(normalized(cell) in titles or any(
                len(base) >= 12 and base.isascii() and spelling(cell) == spelling(base)
                for base in titles) for cell in cells)
            if not exact_title:
                reasons.append("different_title_or_version")
            duration = next((c.strip() for c in cells if re.fullmatch(r"\d+:\d{2}", c.strip())), None)
            if not duration or not (0 <= int(duration.split(":")[1]) < 60 and
                                    int(duration.split(":")[0]) * 60 + int(duration.split(":")[1]) > 0):
                reasons.append("missing_duration")
            # The table establishes song identity. Use filenames only to detect
            # conflicting versions, not to require a particular transliteration.
            stem = file_title.removeprefix("File:").rsplit(".", 1)[0]
            context = " ".join(c for c in cells if "/wiki/File:" not in c) + " " + stem
            if re.search(r"\b(?:off[\s_-]?vocal|instrumental)\b", context.replace("_", " "), re.I):
                reasons.append("non_vocal")
            if re.search(r"\b(?:short|preview|tv[\s_-]?size|anime[\s_-]?ver|live[\s_-]?ver|"
                         r"remix|solo[\s_-]?ver|cover)\b", context.replace("_", " "), re.I):
                reasons.append("excluded_version")
            # Catch mislabeled alternate performer files while accepting file
            # spelling differences and innocuous upload suffixes such as Fixed.
            stripped = re.sub(r"^\d{1,2}[ ._-]+", "", stem)
            if not any(normalized(stripped).startswith(base) for base in titles):
                stripped = stem
            for base in sorted(titles):
                raw_stem = normalized(stem)
                if raw_stem == base:
                    break  # e.g. 1.2.3! is a title, not a track-number prefix
                candidate = normalized(stripped)
                if candidate.startswith(base) and candidate[len(base):] not in {
                    "", "full", "fullver", "fullversion", "fixed", "musicalver"
                }:
                    reasons.append("alternate_file_version")
                    break
            rows.append({"title": file_title, "row": " ".join(cells[:-1])[:400], "reasons": reasons})
    return rows


def recording_candidates(page, title, explicit=None):
    candidates = {}
    for row in recording_rows(page, title):
        if (normalized(row["title"]) == normalized(explicit)) if explicit else not row["reasons"]:
            candidates[row["title"]] = {"title": row["title"], "row": row["row"]}
    return list(candidates.values())


def vocal_recording_candidates(page, title, explicit=None):
    """Return every vocal recording in wiki row order, with an override first."""
    candidates = {}
    selected = None
    explicit_key = normalized(explicit) if explicit else None
    for row in recording_rows(page, title):
        if "non_vocal" in row["reasons"]:
            continue
        value = {"title": row["title"], "row": row["row"]}
        # An explicit file is a deliberate selection on this page, so its
        # filename need not resemble the song title. It still must be vocal.
        if explicit_key and normalized(row["title"]) == explicit_key:
            selected = value
            continue
        if ("different_title_or_version" not in row["reasons"]
                or "alternate_file_version" in row["reasons"]):
            candidates.setdefault(row["title"], value)
    values = list(candidates.values())
    if explicit:
        if selected is None:
            return []
        values.insert(0, selected)
    return values


WIKI_AUDIO_SELECTION_VERSION = "2"


def source_identity(kind, record, identities, artists, correction):
    identity = {"id": record["id"], "name": record["name"], "correction": correction}
    if kind == "songs":
        upstream = identities[record["id"]]
        identity["credits"] = upstream["artistVariants"]
        identity["seriesIds"] = upstream["seriesIds"]
        identity["artistNames"] = [artists[i]["name"] for i in record["artists"]]
        identity["audioSelectionVersion"] = WIKI_AUDIO_SELECTION_VERSION
    return canonical_hash(identity)


def validate_corrections(value, payloads):
    if not isinstance(value, dict) or set(value) != {"schemaVersion", "songs", "artists", "series"}:
        raise ValueError("Invalid source overrides fields")
    if value["schemaVersion"] != "1.0.0":
        raise ValueError("Unsupported source overrides schema")
    for kind, records in zip(("songs", "artists", "series"), payloads):
        ids = {r["id"] for r in records}
        if not isinstance(value[kind], dict) or not set(value[kind]) <= ids:
            raise ValueError(f"Unknown {kind} source override IDs")
        for correction in value[kind].values():
            allowed = {"name", "englishName", "wikiPage", "note"}
            if kind == "songs":
                allowed |= {"wikiFile", "audio"}
            if not isinstance(correction, dict) or not set(correction) <= allowed:
                raise ValueError(f"Invalid {kind} correction")
            for key, text in correction.items():
                if key == "audio":
                    if text is not None:
                        raise ValueError("Only explicit null audio is supported; select wikiFile for a recording")
                elif not isinstance(text, str) or not text.strip():
                    raise ValueError(f"Invalid correction {key}")
            if correction.get("wikiFile") and not correction["wikiFile"].startswith("File:"):
                raise ValueError("wikiFile must use a File: title")
            if correction.get("wikiFile") and not correction.get("wikiPage"):
                raise ValueError("wikiFile requires an explicit wikiPage")
            if "wikiFile" in correction and "audio" in correction:
                raise ValueError("wikiFile and null audio conflict")


def enrich(payloads, identities, corrections, wiki, previous=None, log=print, retry_failed_songs=False):
    validate_corrections(corrections, payloads)
    songs, artists_list, series = payloads
    artists = {a["id"]: a for a in artists_list}
    evidence = {"songs": {}, "artists": {}, "series": {}}
    previous_marker, previous_payloads = previous if previous else ({}, ([], [], []))
    previous_records = {kind: {r["id"]: r for r in records}
                        for kind, records in zip(("songs", "artists", "series"), previous_payloads)}
    outage_count = 0
    for kind, records in (("artists", artists_list), ("series", series), ("songs", songs)):
        # Resolve individually named performers before composite credits.
        records = sorted(records, key=lambda r: (
            len(credit_parts(r["name"], artists_list)) if kind == "artists" else 0, int(r["id"])))
        for index, record in enumerate(records):
            correction = corrections[kind].get(record["id"], {})
            identity = source_identity(kind, record, identities, artists, correction)
            item = {"identity": identity, "status": "unresolved"}
            old = previous_marker.get("wiki", {}).get(kind, {}).get(record["id"], {})
            saved = previous_records[kind].get(record["id"])
            compatible = saved is not None and old.get("identity") == identity
            retry_statuses = {"stale", "missing", "ambiguous", "unresolved"}
            if (retry_failed_songs and compatible
                    and (kind != "songs" or (old.get("status") not in retry_statuses
                                             and "wikiAudioUrls" in saved))):
                record["englishName"] = saved["englishName"]
                if kind == "songs":
                    record["wikiAudioUrl"] = saved["wikiAudioUrl"]
                    record["wikiAudioUrls"] = list(saved["wikiAudioUrls"])
                evidence[kind][record["id"]] = old
                if index % 20 == 0:
                    log(f"wiki {kind}: {index + 1}/{len(records)}; last={record['id']} reused")
                continue
            try:
                if outage_count >= 5:
                    raise WikiUnavailable("Wiki unavailable after five consecutive failures")
                components = credit_parts(record["name"], artists_list)
                component_records = [next((a for a in artists_list if normalized(a["name"]) == normalized(part)
                                           and (evidence["artists"].get(a["id"], {}).get("status") == "verified"
                                                or corrections["artists"].get(a["id"], {}).get("englishName"))), None)
                                     for part in components]
                component_pages = []
                component_aliases = []
                if kind == "artists" and len(components) > 1 and not correction.get("wikiPage"):
                    for part, known in zip(components, component_records):
                        if known:
                            component_aliases.append(known["englishName"])
                            component_pages.append({"artistId": known["id"]})
                        else:
                            found, _ = wiki.discover(part, kind="artists")
                            if len(found) == 1:
                                component_aliases.append(found[0].get("displayName", found[0]["page"]["title"]))
                                component_pages.append({"name": part, "page": found[0]["page"]})
                if kind == "artists" and len(components) > 1 and not correction.get("wikiPage"):
                    pages = []
                    if len(component_aliases) == len(components):
                        record["englishName"] = ", ".join(component_aliases)
                        item.update(status="verified", components=component_pages)
                    else:
                        item.update(status="missing", reason="unresolved_performer_components",
                                    components=component_pages,
                                    candidates=components)
                else:
                    hint = old.get("page", {}).get("title")
                    pages, ambiguous = wiki.discover(correction.get("name", record["name"]),
                                                     correction.get("wikiPage"), hint=hint, kind=kind)
                    item["status"] = "ambiguous" if ambiguous else "missing"
                    item["reason"] = "multiple_pages" if ambiguous else "no_matching_title"
                    if kind == "songs":
                        recording_pages = [p for p in pages if vocal_recording_candidates(
                            p, p.get("displayName", p["page"]["title"]), correction.get("wikiFile"))]
                        if len(recording_pages) == 1:
                            pages = recording_pages
                    if len(pages) == 1:
                        page = pages[0]
                        record["englishName"] = page.get("displayName", page["page"]["title"])
                        item.update(status="verified", page=page["page"])
                        item.pop("reason", None)
                        if kind == "songs":
                            item["performerMatch"] = credit_matches(
                                page, [artists[i] for i in record["artists"]])
                            candidates = vocal_recording_candidates(
                                page, record["englishName"], correction.get("wikiFile"))
                            item["candidates"] = [c["title"] for c in candidates]
                            if type(wiki) is Wiki:
                                verified_by_title = wiki.files([candidate["title"] for candidate in candidates])
                                verified_files = []
                                seen_urls = set()
                                for candidate in candidates:
                                    verified = verified_by_title.get(normalized(candidate["title"]))
                                    if verified and verified["url"] not in seen_urls:
                                        seen_urls.add(verified["url"])
                                        verified_files.append(verified)
                            else:
                                verified_files = []
                                seen_urls = set()
                                for candidate in candidates:
                                    verified = wiki.file(candidate["title"])
                                    if verified and verified["url"] not in seen_urls:
                                        seen_urls.add(verified["url"])
                                        verified_files.append(verified)
                            if correction.get("wikiFile") and (not verified_files or normalized(
                                    verified_files[0]["title"]) != normalized(correction["wikiFile"])):
                                verified_files = []
                            if verified_files:
                                record["wikiAudioUrls"] = [verified["url"] for verified in verified_files]
                                record["wikiAudioUrl"] = record["wikiAudioUrls"][0]
                                item["files"] = verified_files
                                item["file"] = verified_files[0]
                                if correction.get("wikiFile"):
                                    item["selection"] = "override"
                            else:
                                rows = recording_rows(page, record["englishName"])
                                item.update(status="missing", reason="file_verification_failed" if candidates else
                                            "no_selectable_recording" if rows else "no_audio")
                                item["recordings"] = rows
                    elif len(pages) > 1:
                        item.update(status="ambiguous", reason="multiple_pages", candidates=[p["page"]["title"] for p in pages])
                outage_count = 0
            except WikiUnavailable as error:
                outage_count += 1
                if (saved and old.get("identity") == identity
                        and (old.get("status") in {"verified", "stale"} or old.get("page"))):
                    record["englishName"] = saved["englishName"]
                    if kind == "songs":
                        record["wikiAudioUrl"] = saved["wikiAudioUrl"]
                        record["wikiAudioUrls"] = list(saved.get("wikiAudioUrls") or
                                                       ([saved["wikiAudioUrl"]] if saved["wikiAudioUrl"] else []))
                    item = {**old, "status": "stale", "reason": str(error),
                            "lastVerifiedCollection": old.get("lastVerifiedCollection", previous_marker.get("collection"))}
                else:
                    item["reason"] = str(error)
            for key in ("name", "englishName"):
                if key in correction:
                    record[key] = correction[key]
            if kind == "songs" and "audio" in correction:
                record["wikiAudioUrl"] = None
                record["wikiAudioUrls"] = []
                item.update(status="unavailable", reason=correction.get("note", "Explicit null audio override"))
                item.pop("file", None)
            evidence[kind][record["id"]] = item
            if index % 20 == 0:
                log(f"wiki {kind}: {index + 1}/{len(records)}; last={record['id']} {item['status']}")
    return evidence

import hashlib
import json
import os
import re
import time
import urllib.parse
import urllib.request

from core.utils import get_cache_root


class DiscordArtworkLookup:
    CACHE_FORMAT_VERSION = 3
    CACHE_DIR_NAME = "discord_artwork"
    SUCCESS_TTL_SECONDS = 30 * 24 * 60 * 60
    MISS_TTL_SECONDS = 24 * 60 * 60
    USER_AGENT = "StavaPlayer/1.0 (Discord artwork lookup; contact: local-app)"

    def __init__(self):
        self.cache_dir = os.path.join(get_cache_root(), self.CACHE_DIR_NAME)
        os.makedirs(self.cache_dir, exist_ok=True)

    def resolve(self, title, artist, album):
        normalized = self._normalize_metadata(title, artist, album)
        if not normalized:
            return None

        cache_path = self._cache_path_for(normalized)
        cached = self._load_cache(cache_path)
        if cached is not None:
            return cached or None

        artwork_url = self._lookup_cover_art_archive(normalized)
        self._store_cache(cache_path, normalized, artwork_url)
        return artwork_url

    def _normalize_metadata(self, title, artist, album):
        title = self._clean_value(title)
        artist = self._clean_value(artist)
        album = self._clean_value(album)
        if not title and not album:
            return None
        if not artist:
            return None
        return {
            "title": title,
            "artist": artist,
            "album": album,
        }

    def _clean_value(self, value):
        text = str(value or "").strip()
        return " ".join(text.split())

    def _cache_path_for(self, normalized):
        raw_key = "|".join([
            normalized.get("title", "").casefold(),
            normalized.get("artist", "").casefold(),
            normalized.get("album", "").casefold(),
        ])
        digest = hashlib.sha1(raw_key.encode("utf-8")).hexdigest()
        return os.path.join(self.cache_dir, f"{digest}.json")

    def _load_cache(self, cache_path):
        if not os.path.exists(cache_path):
            return None

        try:
            with open(cache_path, "r", encoding="utf-8") as handle:
                payload = json.load(handle)
        except Exception:
            return None

        if int(payload.get("version", 0) or 0) != self.CACHE_FORMAT_VERSION:
            return None

        expires_at = float(payload.get("expires_at", 0.0) or 0.0)
        if expires_at < time.time():
            return None

        return str(payload.get("artwork_url", "") or "")

    def _store_cache(self, cache_path, normalized, artwork_url):
        ttl = self.SUCCESS_TTL_SECONDS if artwork_url else self.MISS_TTL_SECONDS
        payload = {
            "version": self.CACHE_FORMAT_VERSION,
            "metadata": normalized,
            "artwork_url": artwork_url or "",
            "expires_at": time.time() + ttl,
        }
        try:
            with open(cache_path, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, ensure_ascii=True, indent=2)
        except Exception:
            pass

    def _lookup_cover_art_archive(self, normalized):
        release_id = self._find_release_id(normalized)
        if not release_id:
            return self._lookup_itunes_artwork(normalized)

        artwork_data = self._request_json(f"https://coverartarchive.org/release/{release_id}")
        if not isinstance(artwork_data, dict):
            return self._lookup_itunes_artwork(normalized)

        images = artwork_data.get("images") or []
        for image in images:
            if not isinstance(image, dict):
                continue
            if image.get("front"):
                thumbnails = image.get("thumbnails") or {}
                for key in ("500", "250", "large", "small"):
                    candidate = thumbnails.get(key)
                    if self._is_http_url(candidate):
                        return candidate
                candidate = image.get("image")
                if self._is_http_url(candidate):
                    return candidate

        return self._lookup_itunes_artwork(normalized)

    def _lookup_itunes_artwork(self, normalized):
        artist = normalized.get("artist", "")
        title = normalized.get("title", "")
        album = normalized.get("album", "")
        queries = []
        for query in (
            " ".join([term for term in (artist, album or title) if term]),
            " ".join([term for term in (artist, title) if term]),
            title,
            album,
        ):
            query = self._clean_value(query)
            if query and query not in queries:
                queries.append(query)

        candidates = []
        seen_ids = set()
        for query in queries:
            payload = self._request_json(
                "https://itunes.apple.com/search"
                f"?term={urllib.parse.quote(query)}&entity=song&limit=15"
            )
            results = payload.get("results") if isinstance(payload, dict) else None
            if not isinstance(results, list):
                continue
            for item in results:
                if not isinstance(item, dict):
                    continue
                item_id = item.get("trackId") or item.get("collectionId") or json.dumps(item, sort_keys=True)
                if item_id in seen_ids:
                    continue
                seen_ids.add(item_id)
                candidates.append(item)

        best_candidate = None
        best_score = -1
        for item in candidates:
            score = self._score_itunes_candidate(normalized, item)
            if score > best_score:
                best_score = score
                best_candidate = item

        if best_candidate is None or best_score < 4:
            return None

        for field in ("artworkUrl100", "artworkUrl60", "artworkUrl30"):
            candidate = self._upgrade_itunes_artwork_url(best_candidate.get(field))
            if self._is_http_url(candidate):
                return candidate

        return None

    def _score_itunes_candidate(self, normalized, item):
        title = self._normalize_for_match(normalized.get("title"))
        artist = self._normalize_for_match(normalized.get("artist"))
        album = self._normalize_for_match(normalized.get("album"))

        item_title = self._normalize_for_match(item.get("trackName"))
        item_artist = self._normalize_for_match(item.get("artistName"))
        item_album = self._normalize_for_match(item.get("collectionName"))
        combined = " ".join(part for part in (item_title, item_artist, item_album) if part)

        score = 0
        if title:
            if item_title == title:
                score += 6
            elif title in item_title or item_title in title:
                score += 5
            elif title in combined:
                score += 4

        if artist:
            if item_artist == artist:
                score += 5
            elif artist in combined:
                score += 3
            else:
                artist_tokens = [token for token in artist.split() if len(token) > 2]
                matched_tokens = sum(1 for token in artist_tokens if token in combined)
                score += min(3, matched_tokens)

        if album:
            if item_album == album:
                score += 4
            elif album in combined or item_album in album:
                score += 2

        if str(item.get("kind") or "") == "song":
            score += 1
        return score

    def _normalize_for_match(self, value):
        text = self._clean_value(value).casefold()
        if not text:
            return ""
        text = text.replace("&", " and ")
        text = re.sub(r"\b(feat|ft|featuring|ver|version|tv size|instrumental|english)\b", " ", text)
        text = re.sub(r"[^\w\s]", " ", text, flags=re.UNICODE)
        return " ".join(text.split())

    def _upgrade_itunes_artwork_url(self, url):
        text = str(url or "").strip()
        if not text:
            return None
        return text.replace("/100x100bb.jpg", "/512x512bb.jpg").replace("/60x60bb.jpg", "/512x512bb.jpg").replace("/30x30bb.jpg", "/512x512bb.jpg")

    def _find_release_id(self, normalized):
        album = normalized.get("album")
        if album:
            release_id = self._search_release_by_album(normalized)
            if release_id:
                return release_id
        return self._search_release_by_recording(normalized)

    def _search_release_by_album(self, normalized):
        query = f'release:"{normalized["album"]}" AND artist:"{normalized["artist"]}"'
        payload = self._request_json(
            "https://musicbrainz.org/ws/2/release/"
            f"?query={urllib.parse.quote(query)}&fmt=json&limit=5"
        )
        releases = payload.get("releases") if isinstance(payload, dict) else None
        if not isinstance(releases, list):
            return None

        for release in releases:
            release_id = self._extract_release_id(release)
            if release_id:
                return release_id
        return None

    def _search_release_by_recording(self, normalized):
        query = f'recording:"{normalized["title"]}" AND artist:"{normalized["artist"]}"'
        payload = self._request_json(
            "https://musicbrainz.org/ws/2/recording/"
            f"?query={urllib.parse.quote(query)}&fmt=json&limit=5"
        )
        recordings = payload.get("recordings") if isinstance(payload, dict) else None
        if not isinstance(recordings, list):
            return None

        for recording in recordings:
            releases = recording.get("releases") or []
            for release in releases:
                release_id = self._extract_release_id(release)
                if release_id:
                    return release_id
        return None

    def _extract_release_id(self, release):
        if not isinstance(release, dict):
            return None
        release_id = str(release.get("id") or "").strip()
        return release_id or None

    def _request_json(self, url):
        request = urllib.request.Request(
            url,
            headers={
                "User-Agent": self.USER_AGENT,
                "Accept": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=8) as response:
                charset = response.headers.get_content_charset("utf-8")
                raw_text = response.read().decode(charset, errors="replace")
        except Exception:
            return None

        try:
            return json.loads(raw_text)
        except Exception:
            return None

    def _is_http_url(self, value):
        text = str(value or "").strip()
        return text.startswith("https://") or text.startswith("http://")
"""Providers operate on track metadata, independent of player and terminal UI."""

import asyncio
import random
import time
from collections.abc import Callable
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any, Protocol

import httpx

from lyra.lyrics.cache import LyricsCache
from lyra.lyrics.lyricsfile import parse_lyricsfile
from lyra.lyrics.matching import confidence, normalize
from lyra.lyrics.models import Lyrics
from lyra.lyrics.parser import LyricsError, parse_lrc
from lyra.mpris.models import Track


class ProviderError(RuntimeError):
    pass


class LyricsProvider(Protocol):
    async def fetch(self, track: Track, *, force: bool = False) -> Lyrics: ...


def retry_delay(value: str) -> float:
    try:
        return max(1.0, float(value))
    except ValueError:
        try:
            return max(1.0, (parsedate_to_datetime(value) - datetime.now(UTC)).total_seconds())
        except (ValueError, TypeError, OverflowError):
            return 60.0


class LRCLibProvider:
    def __init__(
        self,
        cache: LyricsCache,
        client: httpx.AsyncClient,
        *,
        estimate: bool = True,
        now: Callable[[], float] = time.monotonic,
    ) -> None:
        self.cache, self.client, self.estimate, self.now = cache, client, estimate, now
        self.lock = asyncio.Lock()
        self.next_request = 0.0
        self.retry_at = 0.0

    async def _request(self, endpoint: str, params: dict[str, Any]) -> Any:
        async with self.lock:
            if self.now() < self.retry_at:
                raise ProviderError(
                    f"LRCLIB cooling down; retry in {self.retry_at - self.now():.0f}s"
                )
            await asyncio.sleep(max(0, self.next_request - self.now()))
            try:
                response = await self.client.get(endpoint, params=params)
                self.next_request = self.now() + 0.4
                if response.status_code in (429, 503):
                    delay = retry_delay(response.headers.get("Retry-After", "60"))
                    self.retry_at = self.now() + delay * random.uniform(1.0, 1.3)
                    raise ProviderError(f"LRCLIB busy; retry after at least {delay:.0f}s")
                if response.status_code == 404:
                    return None
                response.raise_for_status()
                if "json" not in response.headers.get("content-type", ""):
                    raise ProviderError("LRCLIB returned an unexpected response format")
                return response.json()
            except (httpx.HTTPError, ValueError) as error:
                raise ProviderError(f"Lyrics request failed: {error}") from error

    async def fetch(self, track: Track, *, force: bool = False) -> Lyrics:
        if not track.title or not track.artist:
            raise ProviderError("Player must expose both title and artist for automatic matching")
        record = None if force else await self.cache.get(track.signature)
        cache_hit = record is not None
        if record is None:
            record = await self._find(track)
        try:
            lyrics = await asyncio.to_thread(self._decode, record, track.duration)
            if not cache_hit:
                await self.cache.put(track.signature, record)
            return lyrics
        except (ValueError, TypeError, KeyError) as error:
            raise ProviderError(f"Invalid lyrics data: {error}") from error

    async def _find(self, track: Track) -> dict[str, Any]:
        params: dict[str, Any] = {"track_name": track.title, "artist_name": track.artist}
        if track.album:
            params["album_name"] = track.album
        if 1 <= track.duration <= 3600:
            params["duration"] = round(track.duration)
        record = await self._request("/api/get", params)
        if isinstance(record, dict) and confidence(track, record) >= 0.9:
            return record
        candidates = await self._request(
            "/api/search",
            {
                "track_name": normalize(track.title),
                "artist_name": normalize(track.artist),
            },
        )
        if not isinstance(candidates, list):
            raise ProviderError("No lyrics found for this track")
        ranked = sorted(
            ((confidence(track, item), item) for item in candidates if isinstance(item, dict)),
            key=lambda item: item[0],
            reverse=True,
        )
        if not ranked or ranked[0][0] < 0.9:
            raise ProviderError("No confident lyric match; use a local LRC file or R to retry")
        # Ambiguous distinct titles/artists are never silently selected.
        if len(ranked) > 1 and ranked[0][0] - ranked[1][0] < 0.02:
            first, second = ranked[0][1], ranked[1][1]
            if (normalize(first.get("trackName", "")), normalize(first.get("artistName", ""))) != (
                normalize(second.get("trackName", "")),
                normalize(second.get("artistName", "")),
            ):
                raise ProviderError("Ambiguous lyric matches; supply a local LRC file")
        return ranked[0][1]

    def _decode(self, record: dict[str, Any], duration: float) -> Lyrics:
        source = f"LRCLIB · #{record.get('id', '?')}"
        if record.get("instrumental"):
            return Lyrics(source=source, instrumental=True)
        if record.get("lyricsfile"):
            try:
                return parse_lyricsfile(
                    record["lyricsfile"], duration, estimate=self.estimate, source=source
                )
            except LyricsError:
                # Legacy representations remain usable if richer data is malformed.
                pass
        synced = record.get("syncedLyrics")
        if synced:
            try:
                return parse_lrc(synced, duration, estimate=self.estimate, source=source)
            except LyricsError:
                if not record.get("plainLyrics"):
                    raise
        if record.get("plainLyrics"):
            return Lyrics(plain=record["plainLyrics"], source=source)
        raise ProviderError("This record contains no usable lyrics")

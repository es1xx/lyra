import tempfile
import unittest
from pathlib import Path

import httpx

from lyra.lyrics.cache import LyricsCache
from lyra.lyrics.lyricsfile import parse_lyricsfile
from lyra.lyrics.matching import confidence, normalize
from lyra.lyrics.parser import LyricsError
from lyra.lyrics.provider import LRCLibProvider, ProviderError, retry_delay
from lyra.mpris.models import Track

TRACK = Track("Signal City", "LYRA Studio", "Original", 12)
RECORD = dict(
    id=1,
    trackName="Signal City",
    artistName="LYRA Studio",
    albumName="Original",
    duration=12,
    syncedLyrics="[00:01]Original sample\n[00:04]Another signal",
)
YAML_WORDS = """version: "1.0"
metadata:
  offset_ms: 100
lines:
  - start_ms: 1000
    end_ms: 4000
    text: "Original signal"
    words:
      - {start_ms: 1000, end_ms: 1800, text: "Original "}
      - {start_ms: 2000, end_ms: 3000, text: "signal"}
"""


class MatchingTests(unittest.TestCase):
    def test_normalize_variants(self):
        self.assertEqual(normalize(" Signal City (feat. Guest) - 2024 Remastered "), "signal city")
        self.assertEqual(normalize("Signal—City!"), "signal city")

    def test_exact(self):
        self.assertEqual(confidence(TRACK, RECORD), 1)

    def test_reject_wrong_artist_duration_or_live(self):
        for change in [
            dict(artistName="Other Person"),
            dict(duration=120),
            dict(trackName="Signal City (Live)"),
            dict(trackName="Other Song"),
        ]:
            self.assertEqual(confidence(TRACK, RECORD | change), 0)

    def test_missing_metadata(self):
        self.assertEqual(confidence(Track(title="Signal City"), RECORD), 0)


class LyricsfileTests(unittest.TestCase):
    def test_word_times_and_gaps(self):
        lyrics = parse_lyricsfile(YAML_WORDS, 12, estimate=True, source="test")
        self.assertEqual(lyrics.timing, "word")
        self.assertEqual(lyrics.lines[0].words[0].start, 1.1)
        self.assertAlmostEqual(lyrics.lines[0].words[0].end, 1.9)
        self.assertEqual(lyrics.lines[0].words[1].start, 2.1)

    def test_line_estimation(self):
        lyrics = parse_lyricsfile(
            'lines: [{start_ms: 1000, text: "Signal city"}]', 5, estimate=True, source="test"
        )
        self.assertEqual(lyrics.timing, "approximate")

    def test_instrumental(self):
        lyrics = parse_lyricsfile("metadata: {instrumental: true}", 5, estimate=True, source="test")
        self.assertTrue(lyrics.instrumental)

    def test_invalid_yaml_or_timestamps(self):
        for content in [
            "!!python/object:bad {}",
            "lines: [",
            "lines: [{start_ms: .nan}]",
            YAML_WORDS.replace("start_ms: 2000", "start_ms: 1500"),
        ]:
            with self.subTest(content=content), self.assertRaises(LyricsError):
                parse_lyricsfile(content, 12, estimate=True, source="test")


class ProviderTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.calls = []
        self.responses = []

        def handler(request):
            self.calls.append(request)
            result = self.responses.pop(0)
            if isinstance(result, Exception):
                raise result
            status, data, headers = result
            return httpx.Response(status, json=data, headers=headers)

        self.client = httpx.AsyncClient(
            base_url="https://lrclib.net", transport=httpx.MockTransport(handler)
        )
        self.addAsyncCleanup(self.client.aclose)
        self.provider = LRCLibProvider(LyricsCache(Path(self.temporary.name)), self.client)

    async def test_fetch_and_cache(self):
        self.responses = [(200, RECORD, {})]
        first = await self.provider.fetch(TRACK)
        second = await self.provider.fetch(TRACK)
        self.assertEqual(first, second)
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(self.calls[0].url.params["duration"], "12")

    async def test_refresh_bypasses_cache(self):
        self.responses = [(200, RECORD, {}), (200, RECORD, {})]
        await self.provider.fetch(TRACK)
        await self.provider.fetch(TRACK, force=True)
        self.assertEqual(len(self.calls), 2)

    async def test_search_after_404(self):
        self.responses = [(404, {}, {}), (200, [RECORD], {})]
        self.assertTrue((await self.provider.fetch(TRACK)).lines)
        self.assertEqual(self.calls[1].url.path, "/api/search")

    async def test_reject_wrong_match(self):
        self.responses = [
            (200, RECORD | {"artistName": "Wrong"}, {}),
            (200, [RECORD | {"duration": 500}], {}),
        ]
        with self.assertRaisesRegex(ProviderError, "confident"):
            await self.provider.fetch(TRACK)

    async def test_rate_limit_and_cooldown(self):
        self.responses = [(429, {}, {"Retry-After": "120"})]
        with self.assertRaisesRegex(ProviderError, "120"):
            await self.provider.fetch(TRACK)
        with self.assertRaisesRegex(ProviderError, "cooling down"):
            await self.provider.fetch(TRACK, force=True)
        self.assertEqual(len(self.calls), 1)

    async def test_busy_server(self):
        self.responses = [(503, {}, {"Retry-After": "5"})]
        with self.assertRaisesRegex(ProviderError, "busy"):
            await self.provider.fetch(TRACK)

    async def test_network_error(self):
        self.responses = [httpx.ConnectError("offline")]
        with self.assertRaisesRegex(ProviderError, "offline"):
            await self.provider.fetch(TRACK)

    async def test_missing_metadata_no_requests(self):
        with self.assertRaises(ProviderError):
            await self.provider.fetch(Track())
        self.assertEqual(self.calls, [])

    async def test_plain_fallback(self):
        self.responses = [(200, RECORD | {"syncedLyrics": None, "plainLyrics": "Original"}, {})]
        self.assertEqual((await self.provider.fetch(TRACK)).timing, "unsynced")

    async def test_bad_lrc_falls_back_to_plain(self):
        self.responses = [(200, RECORD | {"syncedLyrics": "[bad]", "plainLyrics": "Original"}, {})]
        self.assertEqual((await self.provider.fetch(TRACK)).plain, "Original")

    async def test_word_yaml_preferred(self):
        self.responses = [(200, RECORD | {"lyricsfile": YAML_WORDS}, {})]
        self.assertEqual((await self.provider.fetch(TRACK)).timing, "word")

    async def test_invalid_yaml_falls_back_to_lrc(self):
        self.responses = [(200, RECORD | {"lyricsfile": "bad: ["}, {})]
        self.assertEqual((await self.provider.fetch(TRACK)).timing, "approximate")

    async def test_retry_header(self):
        self.assertEqual(retry_delay("10"), 10)
        self.assertEqual(retry_delay("bad"), 60)

    async def test_malformed_record(self):
        self.responses = [(200, RECORD | {"syncedLyrics": "[bad]", "plainLyrics": None}, {})]
        with self.assertRaises(ProviderError):
            await self.provider.fetch(TRACK)

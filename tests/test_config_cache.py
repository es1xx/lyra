import json
import tempfile
import time
import unittest
from pathlib import Path

from lyra.config import Config, ConfigError, load_config, save_config
from lyra.lyrics.cache import LyricsCache
from lyra.lyrics.parser import LyricsError, load_local
from lyra.utils.text import safe_text, timestamp


class ConfigTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.path = Path(self.temporary.name) / "nested/config.toml"

    def test_defaults_without_file(self):
        self.assertEqual(load_config(self.path).mode, "duo")
        self.assertEqual(load_config(self.path).theme, "white")
        self.assertEqual(load_config(self.path).accent_color, "#ffffff")
        self.assertEqual(load_config(self.path).sync_mode, "auto")
        self.assertFalse(self.path.exists())

    def test_palette_roundtrip_and_legacy_theme(self):
        for theme in ("white", "violet", "green", "cyan", "amber", "neon"):
            with self.subTest(theme=theme):
                config = Config(theme=theme)
                save_config(config, self.path)
                self.assertEqual(load_config(self.path), config)

    def test_atomic_roundtrip(self):
        config = Config(
            mode="word",
            sync_offset_ms=-250,
            accent="#abcdef",
            ascii_art=True,
            show_context=False,
            sync_mode="estimated",
        )
        save_config(config, self.path)
        self.assertEqual(load_config(self.path), config)
        self.assertEqual(list(self.path.parent.iterdir()), [self.path])

    def test_invalid_values(self):
        for values in [
            dict(theme="bad"),
            dict(sync_mode="bad"),
            dict(refresh_rate=120),
            dict(refresh_rate=True),
            dict(animation_intensity=float("nan")),
            dict(accent="green"),
            dict(provider="unknown"),
            dict(shortcuts={"x": "exec"}),
            dict(cache_max_entries=0),
            dict(sync_offset_ms=999999),
            dict(user_agent="bad\nheader"),
        ]:
            with self.subTest(values=values), self.assertRaises(ConfigError):
                Config(**values).validate()

    def test_unknown_or_bad_toml(self):
        self.path.parent.mkdir()
        for value in ["unknown = true", "mode = [", "mode = 5"]:
            self.path.write_text(value)
            with self.assertRaises(ConfigError):
                load_config(self.path)

    def test_keyboard_map(self):
        config = Config(shortcuts={"x": "quit", "space": "toggle_play"})
        save_config(config, self.path)
        self.assertEqual(load_config(self.path).shortcuts, config.shortcuts)

    def test_local_file(self):
        path = Path(self.temporary.name) / "song.lrc"
        path.write_text("[00:01]<00:01>Signal<00:02>")
        self.assertEqual(load_local(path, 3).timing, "word")
        path.write_text("[99:99]bad")
        with self.assertRaises(LyricsError):
            load_local(path)

    def test_untrusted_text_and_time(self):
        self.assertEqual(safe_text("title\x1b[31m\x00"), "title[31m")
        self.assertEqual(timestamp(125.9), "02:05")


class CacheTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.cache = LyricsCache(Path(self.temporary.name), ttl=10, max_entries=2)
        self.key = ("Title", "Artist", "Album", 180)

    async def test_roundtrip(self):
        record = {"plainLyrics": "Original sample", "id": 1}
        await self.cache.put(self.key, record)
        self.assertEqual(await self.cache.get(self.key), record)

    async def test_expired(self):
        await self.cache.put(self.key, {"id": 1})
        path = self.cache.path(self.key)
        entry = json.loads(path.read_text())
        entry["created"] = time.time() - 20
        path.write_text(json.dumps(entry))
        self.assertIsNone(await self.cache.get(self.key))

    async def test_corrupt_and_missing(self):
        self.assertIsNone(await self.cache.get(self.key))
        self.cache.path(self.key).write_text("not json")
        self.assertIsNone(await self.cache.get(self.key))

    async def test_disable(self):
        self.cache.enabled = False
        await self.cache.put(self.key, {"id": 1})
        self.assertIsNone(await self.cache.get(self.key))
        self.assertFalse(self.cache.path(self.key).exists())

    async def test_eviction(self):
        for index in range(4):
            await self.cache.put((index,), {"id": index})
        self.assertEqual(len(list(self.cache.directory.glob("*.json"))), 2)
        self.assertEqual(await self.cache.get((3,)), {"id": 3})

    async def test_keys_are_safe_and_distinct(self):
        malicious = ("../../../../file", "artist")
        self.assertEqual(self.cache.path(malicious).parent, self.cache.directory)
        self.assertNotEqual(self.cache.path(self.key), self.cache.path((*self.key, "different")))

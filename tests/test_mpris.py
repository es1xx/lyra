import importlib.util
import unittest
from unittest.mock import AsyncMock

from lyra.mpris.client import INTERFACE, MPRISManager, PlayerError
from lyra.mpris.demo import DemoManager, demo_lyrics
from lyra.mpris.models import Player, Track
from lyra.sync.clock import PlaybackClock


class MetadataTests(unittest.TestCase):
    def test_all_metadata(self):
        track = Track.from_metadata(
            {
                "xesam:title": "Signal",
                "xesam:artist": ["A", "B"],
                "xesam:album": "Night",
                "mpris:length": 12_500_000,
                "mpris:trackid": "/track/1",
                "mpris:artUrl": "https://img",
            }
        )
        self.assertEqual(track, Track("Signal", "A, B", "Night", 12.5, "/track/1", "https://img"))

    def test_missing_and_string_artist(self):
        self.assertEqual(Track.from_metadata({}), Track())
        self.assertEqual(Track.from_metadata({"xesam:artist": "Artist"}).artist, "Artist")

    def test_track_change_invalidates_old_position(self):
        player = Player("player")
        player.apply({"Metadata": {"xesam:title": "First"}, "Position": 20_000_000})
        self.assertTrue(player.clock.known)
        player.apply({"Metadata": {"xesam:title": "Second"}})
        self.assertFalse(player.clock.known)
        self.assertLess(player.clock.read(), 0.1)

    def test_pause_rate_and_resume_properties(self):
        now = [100.0]
        player = Player("player", clock=PlaybackClock(lambda: now[0]))
        player.apply({"Position": 1_000_000, "PlaybackStatus": "Playing"})
        now[0] += 2
        player.apply({"PlaybackStatus": "Paused"})
        now[0] += 20
        self.assertEqual(player.clock.read(), 3)
        player.apply({"PlaybackStatus": "Playing", "Rate": 1.5})
        now[0] += 2
        self.assertEqual(player.clock.read(), 6)


class ManagerTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.manager = MPRISManager("spotify")
        self.first = Player("org.mpris.MediaPlayer2.spotify", identity="Spotify")
        self.second = Player("org.mpris.MediaPlayer2.firefox", identity="Firefox")
        self.manager.players = {self.first.name: self.first, self.second.name: self.second}

    async def test_playing_priority_then_preference(self):
        self.assertIs(self.manager.active, self.first)
        self.second.clock.update(status="Playing")
        self.assertIs(self.manager.active, self.second)
        self.first.clock.update(status="Playing")
        self.assertIs(self.manager.active, self.first)

    async def test_manual_selection_and_disconnect_fallback(self):
        self.first.clock.update(status="Playing")
        self.manager.selected = self.second.name
        self.assertIs(self.manager.active, self.second)
        del self.manager.players[self.second.name]
        self.assertIs(self.manager.active, self.first)
        self.manager.players.clear()
        self.assertIsNone(self.manager.active)

    async def test_no_player_control(self):
        self.manager.players.clear()
        with self.assertRaisesRegex(PlayerError, "No media"):
            await self.manager.control("PlayPause")

    async def test_unsupported_controls(self):
        with self.assertRaisesRegex(PlayerError, "does not support"):
            await self.manager.control("Seek", 5)

    async def test_seek_microseconds_and_toggle_capabilities(self):
        self.first.capabilities = dict.fromkeys(
            ["CanSeek", "CanControl", "CanPlay", "CanPause"], True
        )
        self.manager.call = AsyncMock(return_value=[])
        await self.manager.control("Seek", -5)
        self.manager.call.assert_awaited_with(self.first.name, INTERFACE, "Seek", "x", [-5_000_000])
        await self.manager.control("PlayPause")
        self.manager.call.assert_awaited_with(self.first.name, INTERFACE, "Play", "", [])
        self.first.clock.update(status="Playing")
        await self.manager.control("PlayPause")
        self.manager.call.assert_awaited_with(self.first.name, INTERFACE, "Pause", "", [])

    async def test_refresh_reads_position_separately(self):
        self.first.owner = ":1.20"
        self.manager.call = AsyncMock(
            side_effect=[
                [{"PlaybackStatus": "Playing", "Metadata": {"xesam:title": "New"}}],
                [20_000_000],
            ]
        )
        await self.manager._refresh(self.first.name)
        self.assertTrue(self.first.clock.known)
        self.assertAlmostEqual(self.first.clock.read(), 20, places=2)
        self.assertEqual(self.manager.call.await_args.args[-1], [INTERFACE, "Position"])

    async def test_no_position_does_not_guess_sync(self):
        self.manager.call = AsyncMock(
            side_effect=[[{"PlaybackStatus": "Playing"}], PlayerError("Position unavailable")]
        )
        await self.manager._refresh(self.first.name)
        self.assertFalse(self.first.clock.known)
        self.assertIn(self.first.name, self.manager.players)

    async def test_disconnected_player_removed(self):
        self.manager.call = AsyncMock(side_effect=PlayerError("Disconnected"))
        await self.manager._refresh(self.first.name)
        self.assertNotIn(self.first.name, self.manager.players)

    @unittest.skipUnless(importlib.util.find_spec("dbus_next"), "dbus-next is not installed")
    async def test_real_signal_encoding(self):
        from dbus_next import Message, Variant

        self.first.owner = ":1.20"
        self.manager._signal(
            Message.new_signal("/org/mpris/MediaPlayer2", INTERFACE, "Seeked", "x", [5_000_000])
        )
        message = Message.new_signal(
            "/org/mpris/MediaPlayer2", INTERFACE, "Seeked", "x", [5_000_000]
        )
        message.sender = self.first.owner
        self.manager._signal(message)
        self.assertEqual(round(self.first.clock.read()), 5)
        message = Message.new_signal(
            "/org/mpris/MediaPlayer2",
            "org.freedesktop.DBus.Properties",
            "PropertiesChanged",
            "sa{sv}as",
            [INTERFACE, {"PlaybackStatus": Variant("s", "Paused")}, []],
        )
        message.sender = self.first.owner
        self.manager._signal(message)
        self.assertEqual(self.first.clock.status, "Paused")

    async def test_demo_playback(self):
        demo = DemoManager()
        self.assertEqual(demo_lyrics().timing, "word")
        await demo.control("Seek", 5)
        self.assertAlmostEqual(demo.active.clock.read(), 5, places=2)
        await demo.control("PlayPause")
        self.assertEqual(demo.active.clock.status, "Paused")

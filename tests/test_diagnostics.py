import unittest
from unittest.mock import AsyncMock, Mock

from lyra.diagnostics import describe_players, diagnose
from lyra.mpris.client import MPRISManager, PlayerError
from lyra.mpris.models import Player, Track


class DiagnosticTests(unittest.IsolatedAsyncioTestCase):
    async def test_bus_access_error(self):
        manager = MPRISManager()
        manager.connect = AsyncMock(side_effect=PermissionError("Operation not permitted"))
        lines = []
        self.assertEqual(await diagnose(emit=lines.append, manager=manager), 1)
        self.assertIn("Operation not permitted", "\n".join(lines))

    async def test_no_exposed_player(self):
        manager = MPRISManager()
        manager.connect = AsyncMock()
        manager._daemon = AsyncMock(return_value=[["org.freedesktop.DBus"]])
        lines = []
        self.assertEqual(await diagnose(emit=lines.append, manager=manager), 1)
        self.assertIn("No MPRIS media players", "\n".join(lines))

    async def test_missing_position_is_distinct_from_missing_song(self):
        manager = MPRISManager()
        player = Player("org.mpris.MediaPlayer2.browser")
        player.track = Track("Signal", "LYRA Studio")
        manager.players[player.name] = player
        lines, ready = describe_players(manager)
        self.assertFalse(ready)
        self.assertIn("Song identified", "\n".join(lines))
        self.assertIn("Title: Signal", "\n".join(lines))

    async def test_missing_artist(self):
        manager = MPRISManager()
        player = Player("org.mpris.MediaPlayer2.browser")
        player.track = Track("Signal")
        manager.players[player.name] = player
        lines, ready = describe_players(manager)
        self.assertFalse(ready)
        self.assertIn("title and artist are required", "\n".join(lines))

    async def test_player_read_failure_stays_visible(self):
        manager = MPRISManager()
        manager.players["player"] = Player("player")
        manager.call = AsyncMock(side_effect=PlayerError("Metadata read denied"))
        await manager._refresh("player")
        lines, ready = describe_players(manager)
        self.assertFalse(ready)
        self.assertIn("Metadata read denied", "\n".join(lines))

    async def test_success_and_disconnect(self):
        manager = MPRISManager()
        player = Player("org.mpris.MediaPlayer2.spotify")
        player.track = Track("Signal", "LYRA Studio")
        player.clock.update(position=4, status="Playing")
        manager.players[player.name] = player
        manager.connect = AsyncMock()
        manager._daemon = AsyncMock(return_value=[[player.name]])
        manager._refresh = AsyncMock()
        manager.bus = Mock()
        lines = []
        await diagnose(emit=lines.append, manager=manager)
        self.assertIn("Song detection and playback position are available", "\n".join(lines))
        manager.bus.disconnect.assert_called_once()

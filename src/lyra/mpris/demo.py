"""Original demo material; no network or D-Bus required."""

import asyncio

from lyra.lyrics.models import Lyrics
from lyra.lyrics.parser import parse_lrc
from lyra.mpris.client import MPRISManager
from lyra.mpris.models import Player, Track

DEMO_LRC = """[ti:Signals in the Dark]
[ar:LYRA Studio]
[00:00.00]
[00:02.00]<00:02.00>Wake <00:02.75>the <00:03.25>quiet <00:04.20>city<00:05.50>
[00:05.50]
[00:06.00]<00:06.00>Let <00:06.65>the <00:07.20>green <00:08.00>lights <00:08.80>glow<00:10.00>
[00:10.00]
[00:11.00]<00:11.00>Every <00:11.90>little <00:12.75>signal<00:14.00>
[00:14.00]<00:14.00>Finds <00:14.70>a <00:15.15>place <00:16.00>to <00:16.50>go<00:18.00>
[00:18.00]
[00:20.00]<00:20.00>Through <00:20.80>the <00:21.30>violet <00:22.40>silence<00:24.00>
[00:24.00]<00:24.00>We <00:24.60>are <00:25.20>moving <00:26.20>with <00:27.00>the <00:27.50>sound
[00:29.00]
[00:31.00]<00:31.00>Hold <00:31.70>this <00:32.40>bright <00:33.20>moment<00:35.00>
[00:35.00]<00:35.00>Keep <00:35.70>the <00:36.20>music <00:37.30>all <00:38.00>around<00:40.00>
[00:40.00]
"""


def demo_lyrics() -> Lyrics:
    return parse_lrc(DEMO_LRC, 44, source="LYRA Studio · original demo")


class DemoManager(MPRISManager):
    def __init__(self) -> None:
        super().__init__()
        player = Player("demo", identity="LYRA Studio · DEMO")
        player.track = Track("Signals in the Dark", "LYRA Studio", "Night Signals", 44, "/demo")
        player.capabilities = dict.fromkeys(("CanControl", "CanPlay", "CanPause", "CanSeek"), True)
        player.clock.update(position=0, status="Playing", duration=44)
        self.players["demo"] = player
        self.message = "Demo · simulated playback"

    async def run(self) -> None:
        while True:
            if self.active and self.active.clock.read() >= 44:
                self.active.clock.update(position=0)
            await asyncio.sleep(0.1)

    async def control(self, command: str, seconds: float = 0) -> None:
        player = self.active
        if player is None:
            return
        if command == "Seek":
            player.clock.update(position=min(44, max(0, player.clock.read() + seconds)))
        else:
            player.clock.update(status="Paused" if player.clock.status == "Playing" else "Playing")

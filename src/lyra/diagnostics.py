"""One-shot song detection diagnosis; no terminal UI or lyrics HTTP requests."""

import asyncio
import importlib.util
import sys
from collections.abc import Callable

from lyra.mpris.client import PREFIX, MPRISManager
from lyra.utils.text import safe_text


def describe_players(manager: MPRISManager) -> tuple[list[str], bool]:
    lines = []
    ready = False
    for player in manager.players.values():
        selected = " [selected]" if manager.active is player else ""
        lines.append(f"{player.name}{selected}")
        lines.append(f"  Status: {player.clock.status}")
        lines.append(f"  Title: {safe_text(player.track.title) or '(not exposed)'}")
        lines.append(f"  Artist: {safe_text(player.track.artist) or '(not exposed)'}")
        position = f"{player.clock.read():.2f}s" if player.clock.known else "(not exposed)"
        lines.append(f"  Position: {position}")
        if not player.track.title or not player.track.artist:
            lines.append("  Cannot look up lyrics automatically: title and artist are required.")
        elif not player.clock.known:
            lines.append("  Song identified, but this player supplies no usable playback position.")
        else:
            ready = True
            lines.append("  Song detection and playback position are available.")
    for name, error in manager.player_errors.items():
        lines.append(f"Cannot read {name}: {safe_text(error)}")
    return lines, ready


async def diagnose(
    preferred: str = "", *, emit: Callable[[str], None] = print, manager: MPRISManager | None = None
) -> int:
    emit(f"Python: {sys.executable}")
    missing = [
        name
        for name in ("textual", "dbus_next", "httpx", "rapidfuzz", "yaml")
        if importlib.util.find_spec(name) is None
    ]
    if missing:
        emit(f"Missing dependencies: {', '.join(missing)}")
    manager = manager or MPRISManager(preferred)
    try:
        await manager.connect()
        names = (await manager._daemon("ListNames"))[0]
        players = sorted(name for name in names if name.startswith(PREFIX))
        emit("Session D-Bus: connected")
        if not players:
            emit("No MPRIS media players are exposed to this session.")
            emit(
                "Start playback, enable browser media integration, "
                "and run in your desktop terminal."
            )
            return 1
        await asyncio.gather(*(manager._refresh(name) for name in players))
        lines, ready = describe_players(manager)
        for line in lines:
            emit(line)
        return 0 if ready and not missing else 1
    except Exception as error:
        emit(f"Session D-Bus failed: {safe_text(str(error))}")
        emit("Run LYRA in the same desktop login as the player, without sudo or an isolated bus.")
        return 1
    finally:
        if manager.bus:
            manager.bus.disconnect()

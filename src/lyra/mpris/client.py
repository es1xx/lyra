"""Native MPRIS client with signals, reconciliation polling, and bus reconnection."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from dbus_next import Message
    from dbus_next.aio import MessageBus

from lyra.mpris.models import Player, Track, unwrap

LOG = logging.getLogger(__name__)
PREFIX = "org.mpris.MediaPlayer2."
PATH = "/org/mpris/MediaPlayer2"
INTERFACE = "org.mpris.MediaPlayer2.Player"
PROPERTIES = "org.freedesktop.DBus.Properties"
DBUS = "org.freedesktop.DBus"


class PlayerError(RuntimeError):
    pass


class MPRISManager:
    def __init__(self, preferred: str = "") -> None:
        self.players: dict[str, Player] = {}
        self.preferred = preferred
        self.selected: str | None = None
        self.bus: MessageBus | None = None
        self.message = "Connecting to session D-Bus…"
        self.wakeup = asyncio.Event()
        self.player_errors: dict[str, str] = {}

    @property
    def active(self) -> Player | None:
        if self.selected and self.selected in self.players:
            return self.players[self.selected]
        choices = list(self.players.values())
        return max(
            choices,
            key=lambda player: (
                player.clock.status == "Playing",
                bool(self.preferred and self.preferred.casefold() in player.name.casefold()),
                bool(player.track.title),
                player.name,
            ),
            default=None,
        )

    async def call(
        self,
        destination: str,
        interface: str,
        member: str,
        signature: str = "",
        body: list | None = None,
        path: str = PATH,
    ) -> list:
        from dbus_next import Message, MessageType

        if not self.bus or not self.bus.connected:
            raise PlayerError("Session D-Bus is disconnected")
        try:
            reply = await asyncio.wait_for(
                self.bus.call(
                    Message(
                        destination=destination,
                        path=path,
                        interface=interface,
                        member=member,
                        signature=signature,
                        body=body or [],
                    )
                ),
                timeout=2.0,
            )
        except (TimeoutError, OSError, EOFError) as error:
            raise PlayerError(f"Player did not respond: {error}") from error
        if reply is None or reply.message_type == MessageType.ERROR:
            detail = str(reply.body[0]) if reply and reply.body else member
            raise PlayerError(detail)
        return reply.body

    async def _daemon(self, member: str, signature: str = "", body: list | None = None) -> list:
        return await self.call(DBUS, DBUS, member, signature, body, "/org/freedesktop/DBus")

    def _signal(self, message: Message) -> None:
        from dbus_next import MessageType

        if message.message_type != MessageType.SIGNAL:
            return
        if message.interface == DBUS and message.member == "NameOwnerChanged":
            name, _old, new = message.body
            if name.startswith(PREFIX):
                if name in self.players and self.players[name].owner != new:
                    self.players.pop(name, None)
                self.wakeup.set()
            return
        if message.path != PATH:
            return
        for player in tuple(self.players.values()):
            if player.owner != message.sender:
                continue
            try:
                if message.interface == PROPERTIES and message.member == "PropertiesChanged":
                    interface, changed, invalidated = message.body
                    if interface == INTERFACE:
                        player.apply(changed)
                        if "Position" in invalidated:
                            player.clock.known = False
                        if "Metadata" in invalidated:
                            player.track = Track()
                            player.clock.reset()
                        self.wakeup.set()
                elif message.interface == INTERFACE and message.member == "Seeked":
                    player.clock.update(position=message.body[0] / 1_000_000)
                    player.revision += 1
            except (TypeError, ValueError, KeyError):
                LOG.exception("Invalid MPRIS signal from %s", player.name)

    async def connect(self) -> None:
        from dbus_next.aio import MessageBus

        self.bus = await asyncio.wait_for(MessageBus().connect(), 3)
        self.bus.add_message_handler(self._signal)
        for rule in (
            "type='signal',interface='org.freedesktop.DBus',member='NameOwnerChanged'",
            "type='signal',path='/org/mpris/MediaPlayer2'",
        ):
            await self._daemon("AddMatch", "s", [rule])

    async def run(self) -> None:
        while True:
            try:
                await self.connect()
                await self._monitor()
            except asyncio.CancelledError:
                raise
            except Exception as error:
                LOG.debug("D-Bus connection failed", exc_info=True)
                self.message = f"Session D-Bus unavailable: {error}. Retrying…"
            finally:
                self.players.clear()
                if self.bus:
                    self.bus.disconnect()
                    self.bus = None
            await asyncio.sleep(3)

    async def _monitor(self) -> None:
        while self.bus and self.bus.connected:
            self.wakeup.clear()
            names = (await self._daemon("ListNames"))[0]
            present = {name for name in names if name.startswith(PREFIX)}
            for name in set(self.players) - present:
                self.players.pop(name, None)
            for name in set(self.player_errors) - present:
                self.player_errors.pop(name, None)
            await asyncio.gather(*(self._refresh(name) for name in present))
            if self.players:
                self.message = "Connected"
            elif self.player_errors:
                name, error = next(iter(self.player_errors.items()))
                self.message = (
                    f"Cannot read {name.removeprefix(PREFIX)}: {error} · run lyra --doctor"
                )
            else:
                self.message = "No MPRIS player exposed · start music or run lyra --doctor"
            try:
                await asyncio.wait_for(self.wakeup.wait(), 2)
                # Coalesce bursts of PropertiesChanged without starving the event loop.
                await asyncio.sleep(0.05)
            except TimeoutError:
                pass
        raise PlayerError("Session bus disconnected")

    async def _refresh(self, name: str) -> None:
        try:
            if name not in self.players:
                owner = (await self._daemon("GetNameOwner", "s", [name]))[0]
                player = Player(name, owner, name.removeprefix(PREFIX))
                self.players[name] = player
                try:
                    identity = await self.call(
                        name, PROPERTIES, "Get", "ss", ["org.mpris.MediaPlayer2", "Identity"]
                    )
                    player.identity = str(unwrap(identity[0]))
                except PlayerError:
                    pass
            player = self.players[name]
            revision = player.revision
            properties = await self.call(name, PROPERTIES, "GetAll", "s", [INTERFACE])
            if player.revision == revision:
                player.apply(properties[0])
            # Position normally does NOT emit PropertiesChanged; query it explicitly.
            revision = player.revision
            try:
                position = await self.call(name, PROPERTIES, "Get", "ss", [INTERFACE, "Position"])
                if player.revision == revision:
                    player.clock.update(position=float(unwrap(position[0])) / 1_000_000)
            except PlayerError:
                # A track never sampled successfully remains visibly unsynchronized.
                pass
            self.player_errors.pop(name, None)
        except asyncio.CancelledError:
            raise
        except Exception as error:
            self.player_errors[name] = str(error)
            LOG.debug("Player %s unavailable", name, exc_info=True)
            self.players.pop(name, None)

    async def control(self, command: str, seconds: float = 0) -> None:
        player = self.active
        if not player:
            raise PlayerError("No media player connected")
        needed = (
            "CanSeek"
            if command == "Seek"
            else ("CanPause" if player.clock.status == "Playing" else "CanPlay")
        )
        if not player.capabilities.get("CanControl", False) or not player.capabilities.get(needed):
            raise PlayerError(f"{player.identity} does not support {command.lower()}")
        member = command
        signature, body = ("x", [int(seconds * 1_000_000)]) if command == "Seek" else ("", [])
        if command == "PlayPause":
            member = "Pause" if player.clock.status == "Playing" else "Play"
        try:
            await self.call(player.name, INTERFACE, member, signature, body)
        except (TimeoutError, OSError) as error:
            raise PlayerError(f"Player did not respond: {error}") from error
        self.wakeup.set()

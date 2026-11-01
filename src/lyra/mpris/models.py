import math
from dataclasses import dataclass, field
from typing import Any

from lyra.sync.clock import PlaybackClock


def unwrap(value: Any) -> Any:
    if hasattr(value, "value"):
        return unwrap(value.value)
    if isinstance(value, dict):
        return {key: unwrap(item) for key, item in value.items()}
    if isinstance(value, list):
        return [unwrap(item) for item in value]
    return value


@dataclass(frozen=True)
class Track:
    title: str = ""
    artist: str = ""
    album: str = ""
    duration: float = 0.0
    track_id: str = ""
    artwork: str = ""

    @property
    def signature(self) -> tuple[str, str, str, int]:
        return self.title, self.artist, self.album, round(self.duration)

    @classmethod
    def from_metadata(cls, metadata: dict[str, Any]) -> "Track":
        data = unwrap(metadata)
        artists = data.get("xesam:artist", [])
        if isinstance(artists, str):
            artists = [artists]
        try:
            duration = float(data.get("mpris:length") or 0) / 1_000_000
        except (TypeError, ValueError, OverflowError):
            duration = 0.0
        if not math.isfinite(duration):
            duration = 0.0
        return cls(
            title=str(data.get("xesam:title") or ""),
            artist=", ".join(artists or []),
            album=str(data.get("xesam:album") or ""),
            duration=max(0.0, duration),
            track_id=str(data.get("mpris:trackid", "")),
            artwork=str(data.get("mpris:artUrl", "")),
        )


@dataclass
class Player:
    name: str
    owner: str = ""
    identity: str = ""
    track: Track = field(default_factory=Track)
    clock: PlaybackClock = field(default_factory=PlaybackClock)
    capabilities: dict[str, bool] = field(default_factory=dict)
    revision: int = 0

    def apply(self, properties: dict[str, Any]) -> None:
        data = unwrap(properties)
        self.revision += 1
        if "Metadata" in data:
            track = Track.from_metadata(data["Metadata"])
            if (track.track_id, track.signature) != (self.track.track_id, self.track.signature):
                self.clock.reset()
            self.track = track
        self.clock.update(
            position=data.get("Position", None) / 1_000_000 if "Position" in data else None,
            status=data.get("PlaybackStatus"),
            rate=data.get("Rate"),
            duration=self.track.duration,
        )
        for key in ("CanControl", "CanPlay", "CanPause", "CanSeek"):
            if key in data:
                self.capabilities[key] = bool(data[key])

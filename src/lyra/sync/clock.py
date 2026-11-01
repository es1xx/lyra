"""Playback interpolation; all internal times are seconds, never wall time."""

import math
import time
from collections.abc import Callable


class PlaybackClock:
    def __init__(self, now: Callable[[], float] = time.monotonic) -> None:
        self.now = now
        self.anchor = now()
        self.position = 0.0
        self.status = "Stopped"
        self.rate = 1.0
        self.duration = 0.0
        self.known = False

    def read(self) -> float:
        elapsed = self.now() - self.anchor if self.status == "Playing" else 0.0
        value = max(0.0, self.position + elapsed * self.rate)
        return min(value, self.duration) if self.duration > 0 else value

    def update(
        self,
        *,
        position: float | None = None,
        status: str | None = None,
        rate: float | None = None,
        duration: float | None = None,
    ) -> None:
        # Re-anchor before changing rate/status so pauses never lose elapsed playback.
        current = self.read()
        if position is not None and not math.isfinite(position):
            position = None
        self.position = current if position is None else max(0.0, position)
        self.anchor = self.now()
        if position is not None:
            self.known = True
        if status is not None:
            self.status = status
        if rate is not None and math.isfinite(rate) and rate > 0:
            self.rate = rate
        if duration is not None:
            self.duration = max(0.0, duration)

    def reset(self) -> None:
        self.position = 0.0
        self.anchor = self.now()
        self.known = False

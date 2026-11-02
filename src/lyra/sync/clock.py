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
        self.correction = 0.0
        self.last_sample: tuple[float, float] | None = None

    def read(self) -> float:
        elapsed = self.now() - self.anchor if self.status == "Playing" else 0.0
        correction = self.correction * min(1.0, max(0.0, elapsed) / 0.5)
        value = max(0.0, self.position + elapsed * self.rate + correction)
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
        self.correction = 0.0
        if position is not None:
            self.known = True
            self.last_sample = None
        if status is not None:
            self.status = status
        if rate is not None and math.isfinite(rate) and rate > 0:
            self.rate = rate
        if duration is not None:
            self.duration = max(0.0, duration)

    def sample(self, position: float, sampled_at: float) -> None:
        """Reconcile polling jitter without delaying seeks or reversing playback."""
        if not math.isfinite(position) or not math.isfinite(sampled_at) or position < 0:
            return
        now = self.now()
        if self.status == "Playing" and self.last_sample:
            last_position, last_at = self.last_sample
            # Some players quantize Position to seconds. Do not restart the clock
            # halfway through the same reported second; prolonged stalls still resync.
            if position == last_position and now - last_at < 1.5:
                return
        previous_sample = (position, now)
        if self.status == "Playing":
            position += max(0.0, now - sampled_at) * self.rate
        error = position - self.read()
        if not self.known or self.status != "Playing" or abs(error) > 0.4 * self.rate:
            self.update(position=position)
        elif abs(error) > 0.04:
            self.update()
            # Spread small corrections over half a second; even a negative
            # correction leaves the interpolated clock moving forward.
            self.correction = error
        self.last_sample = previous_sample

    def reset(self) -> None:
        self.position = 0.0
        self.anchor = self.now()
        self.known = False
        self.correction = 0.0
        self.last_sample = None

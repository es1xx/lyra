"""Bounded, atomic on-disk cache; failures never make playback fail."""

import asyncio
import hashlib
import json
import logging
import os
import tempfile
import time
from pathlib import Path
from typing import Any

LOG = logging.getLogger(__name__)


class LyricsCache:
    def __init__(
        self, directory: Path, ttl: float = 604800, max_entries: int = 500, enabled: bool = True
    ) -> None:
        self.directory, self.ttl = directory, ttl
        self.max_entries, self.enabled = max_entries, enabled

    def path(self, key: tuple) -> Path:
        digest = hashlib.sha256(json.dumps(key, ensure_ascii=False).encode()).hexdigest()
        return self.directory / f"{digest}.json"

    async def get(self, key: tuple) -> dict[str, Any] | None:
        if not self.enabled:
            return None
        return await asyncio.to_thread(self._get, key)

    def _get(self, key: tuple) -> dict[str, Any] | None:
        try:
            path = self.path(key)
            if path.stat().st_size > 4_000_000:
                return None
            entry = json.loads(path.read_text())
            if time.time() - float(entry["created"]) > self.ttl:
                return None
            value = entry["record"]
            return value if isinstance(value, dict) else None
        except (OSError, ValueError, KeyError, TypeError):
            return None

    async def put(self, key: tuple, record: dict[str, Any]) -> None:
        if self.enabled:
            await asyncio.to_thread(self._put, key, record)

    def _put(self, key: tuple, record: dict[str, Any]) -> None:
        temporary = None
        try:
            self.directory.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(mode="w", dir=self.directory, delete=False) as output:
                temporary = Path(output.name)
                json.dump({"created": time.time(), "record": record}, output)
            os.replace(temporary, self.path(key))
            entries = sorted(self.directory.glob("*.json"), key=lambda path: path.stat().st_mtime)
            for path in entries[: max(0, len(entries) - self.max_entries)]:
                path.unlink(missing_ok=True)
        except OSError:
            LOG.debug("Could not write lyrics cache", exc_info=True)
        finally:
            if temporary:
                temporary.unlink(missing_ok=True)

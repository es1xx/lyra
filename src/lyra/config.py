"""Validated XDG configuration and atomic preference persistence."""

import json
import math
import os
import re
import tempfile
import tomllib
from dataclasses import asdict, dataclass, field
from pathlib import Path

from platformdirs import user_cache_path, user_config_path

THEMES = {"neon": "#a3ff79", "cyan": "#67e8f9", "violet": "#c4a1ff", "amber": "#ffd580"}
KEYS = {
    "space": "toggle_play",
    "left": "seek_back",
    "right": "seek_forward",
    "up": "offset_up",
    "down": "offset_down",
    "w": "word",
    "d": "duo",
    "c": "compact",
    "a": "toggle_ascii",
    "s": "settings",
    "t": "cycle_theme",
    "p": "choose_player",
    "r": "refresh_lyrics",
    "h": "help",
    "question_mark": "help",
    "q": "quit",
}


class ConfigError(ValueError):
    pass


@dataclass
class Config:
    theme: str = "neon"
    accent: str = ""
    provider: str = "lrclib"
    mode: str = "duo"
    compact: bool = False
    ascii_art: bool = False
    show_context: bool = True
    animation_intensity: float = 0.65
    refresh_rate: int = 30
    preferred_player: str = ""
    sync_offset_ms: int = 0
    estimate_words: bool = True
    cache_enabled: bool = True
    cache_ttl_days: int = 7
    cache_max_entries: int = 500
    user_agent: str = "LYRA/0.1.0 (local Linux terminal lyrics client)"
    shortcuts: dict[str, str] = field(default_factory=lambda: dict(KEYS))

    @property
    def accent_color(self) -> str:
        return self.accent or THEMES[self.theme]

    def validate(self) -> None:
        defaults = Config()
        for name, value in asdict(self).items():
            if type(value) is not type(getattr(defaults, name)):
                # TOML integers are reasonable for intensity too.
                if name == "animation_intensity" and type(value) is int:
                    self.animation_intensity = float(value)
                else:
                    raise ConfigError(f"{name} has the wrong TOML type")
        if self.theme not in THEMES or self.mode not in ("word", "duo"):
            raise ConfigError("theme must be neon/cyan/violet/amber; mode must be word/duo")
        if self.provider not in ("lrclib", "local"):
            raise ConfigError("provider must be lrclib or local")
        if self.accent and not re.fullmatch(r"#[0-9a-fA-F]{6}", self.accent):
            raise ConfigError("accent must be empty or a #RRGGBB color")
        if not 5 <= self.refresh_rate <= 60:
            raise ConfigError("refresh_rate must be between 5 and 60")
        if not math.isfinite(self.animation_intensity) or not 0 <= self.animation_intensity <= 1:
            raise ConfigError("animation_intensity must be between 0 and 1")
        if not -60000 <= self.sync_offset_ms <= 60000:
            raise ConfigError("sync_offset_ms must be within ±60000")
        if not 1 <= self.cache_ttl_days <= 365 or not 1 <= self.cache_max_entries <= 10000:
            raise ConfigError("cache_ttl_days must be 1–365; cache_max_entries must be 1–10000")
        if (
            not self.user_agent
            or not self.user_agent.isascii()
            or any(ord(character) < 32 or ord(character) == 127 for character in self.user_agent)
        ):
            raise ConfigError("user_agent must be nonempty printable ASCII")
        for key, action in self.shortcuts.items():
            if not isinstance(key, str) or not key or action not in set(KEYS.values()):
                raise ConfigError(f"Invalid shortcut: {key!r} = {action!r}")


def config_path() -> Path:
    return user_config_path("lyra") / "config.toml"


def cache_path() -> Path:
    return user_cache_path("lyra")


def load_config(path: Path | None = None) -> Config:
    path = path or config_path()
    if not path.exists():
        return Config()
    try:
        raw = tomllib.loads(path.read_text())
        unknown = set(raw) - set(Config.__dataclass_fields__)
        if unknown:
            raise ConfigError(f"Unknown config options: {', '.join(sorted(unknown))}")
        config = Config(**raw)
        old_defaults = {key: action for key, action in KEYS.items() if key not in ("a", "s")}
        if all(config.shortcuts.get(key) == action for key, action in old_defaults.items()):
            for key in ("a", "s"):
                config.shortcuts.setdefault(key, KEYS[key])
        config.validate()
        return config
    except (OSError, ValueError, TypeError) as error:
        raise ConfigError(f"{path}: {error}") from error


def save_config(config: Config, path: Path | None = None) -> None:
    config.validate()
    path = path or config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["# LYRA preferences. Positive sync offset advances lyrics."]
    for name, value in asdict(config).items():
        if name != "shortcuts":
            lines.append(f"{name} = {json.dumps(value, ensure_ascii=False)}")
    lines.append("\n[shortcuts]")
    lines.extend(
        f"{json.dumps(key)} = {json.dumps(action)}" for key, action in config.shortcuts.items()
    )
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", dir=path.parent, delete=False) as output:
            temporary = Path(output.name)
            output.write("\n".join(lines) + "\n")
        os.replace(temporary, path)
    finally:
        if temporary:
            temporary.unlink(missing_ok=True)

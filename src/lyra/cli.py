"""CLI stays usable without importing the terminal or D-Bus dependencies."""

import argparse
import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

from lyra import __version__
from lyra.config import ConfigError, cache_path, config_path, load_config, save_config


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(prog="lyra", description="Real-time MPRIS terminal karaoke")
    result.add_argument("--doctor", action="store_true", help="diagnose live song detection")
    result.add_argument("--version", action="version", version=f"LYRA {__version__}")
    result.add_argument("--ascii", action="store_true", help="large ASCII words (word mode)")
    result.add_argument("--compact", action="store_true", help="show only the current words")
    result.add_argument("--mode", choices=("word", "duo"), help="active lyric group size")
    result.add_argument("--player", help="preferred MPRIS player name, e.g. spotify")
    result.add_argument("--lyrics", type=Path, help="pin a local UTF-8 LRC file")
    result.add_argument(
        "--demo", action="store_true", help="original lyrics and simulated playback"
    )
    result.add_argument(
        "--debug", action="store_true", help="write rotating debug.log in the cache"
    )
    result.add_argument("--config", type=Path, help="use a different TOML configuration")
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        config = load_config(args.config)
        if args.compact:
            config.compact = True
        if args.ascii:
            config.ascii_art = True
            config.mode = "word"
        if args.mode:
            config.mode = args.mode
        if args.player:
            config.preferred_player = args.player
        config.validate()
        lyrics_file = args.lyrics.expanduser() if args.lyrics else None
        if lyrics_file and not lyrics_file.is_file():
            raise ConfigError(f"Lyrics file not found: {lyrics_file}")
        if args.debug:
            cache_path().mkdir(parents=True, exist_ok=True)
            handler = RotatingFileHandler(
                cache_path() / "debug.log", maxBytes=1_000_000, backupCount=2
            )
            logging.basicConfig(
                level=logging.DEBUG,
                handlers=[handler],
                format="%(asctime)s %(name)s %(levelname)s %(message)s",
            )
        else:
            logging.getLogger().addHandler(logging.NullHandler())
        if args.doctor:
            import asyncio

            from lyra.diagnostics import diagnose

            return asyncio.run(diagnose(config.preferred_player))
        from lyra.app import LyraApp

        app = LyraApp(config, lyrics_file=lyrics_file, demo=args.demo)
        app.run()
        try:
            save_config(config, args.config or config_path())
        except OSError as error:
            print(f"lyra: could not save preferences: {error}", file=sys.stderr)
        return 0
    except ImportError as error:
        print(
            f"lyra: missing dependency ({error}). Install with pipx install .; see README.md.",
            file=sys.stderr,
        )
        return 2
    except (ConfigError, OSError) as error:
        print(f"lyra: {error}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        return 130

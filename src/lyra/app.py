"""Textual presentation. Rendering samples the clock; it never advances playback."""

import asyncio
import logging
from pathlib import Path

import httpx
from rich.text import Text
from textual import events
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.color import Color
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import Static

from lyra.config import THEMES, Config, cache_path
from lyra.lyrics.cache import LyricsCache
from lyra.lyrics.models import Lyrics
from lyra.lyrics.parser import load_local
from lyra.lyrics.provider import LRCLibProvider
from lyra.mpris.client import MPRISManager, PlayerError
from lyra.mpris.demo import DemoManager, demo_lyrics
from lyra.mpris.models import Player, Track
from lyra.sync.timeline import Frame, Timeline
from lyra.ui.ascii import is_art, render_ascii
from lyra.ui.screens import HelpScreen, PlayerScreen, SettingsScreen
from lyra.utils.text import safe_text, timestamp

LOG = logging.getLogger(__name__)


class LyraApp(App[None]):
    TITLE = "LYRA · terminal karaoke"
    ENABLE_COMMAND_PALETTE = False
    AUTO_FOCUS = None
    BINDINGS = [Binding("ctrl+c", "quit", "Quit", priority=True)]
    CSS = """
    Screen { background: #080c14; color: #dfe9f5; align: center middle; }
    #shell { width: 100%; max-width: 104; height: 100%; max-height: 40;
        border: round #263449; padding: 1 3; background: #0c121d; }
    #masthead { height: 2; }
    #brand { width: 1fr; text-style: bold; }
    #connection { width: auto; color: #8295ae; text-align: right; }
    #metadata { height: 5; }
    #player { color: #8295ae; height: 1; }
    #title { text-style: bold; height: 2; content-align: left middle; }
    #artist { color: #a7b8cf; height: 1; }
    #stage { height: 1fr; min-height: 5; content-align: center middle; align: center middle; }
    #previous, #following { height: 1; color: #62748e; text-align: center; width: 100%; }
    #active { height: 3; min-height: 1; content-align: center middle; text-style: bold;
        width: 100%; text-align: center; }
    #line { height: 2; color: #a7b8cf; content-align: center middle; text-align: center; }
    #plain-scroll { display: none; height: 1fr; width: 100%; }
    #plain { height: auto; text-align: center; padding: 1; }
    #source { height: 1; color: #8295ae; text-align: center; }
    #progress { height: 1; margin-top: 1; }
    #times { height: 1; color: #8295ae; }
    #status { height: 1; margin-top: 1; }
    #notice { height: 2; color: #a7b8cf; content-align: center middle; text-align: center; }
    #keys { height: 1; color: #62748e; text-align: center; }
    .short #shell { padding: 0 2; }
    .short #metadata { height: 3; }
    .short #title { height: 1; }
    .short #line, .short #previous, .short #following, .short #keys { display: none; }
    .short #active { height: 1; }
    .short #stage { min-height: 1; }
    .short #notice { height: 1; }
    .short #progress, .short #status { margin-top: 0; }
    .compact #shell { border: none; padding: 0; max-height: 100%; background: #080c14; }
    .compact #masthead, .compact #metadata, .compact #source, .compact #progress,
    .compact #times, .compact #status, .compact #notice, .compact #keys,
    .compact #previous, .compact #following, .compact #line { display: none; }
    .compact #stage { min-height: 1; }
    .compact #active { height: 100%; }
    .ascii #active { height: 5; }
    .compact.ascii #active { height: 100%; }
    .no-context #previous, .no-context #following, .no-context #line { display: none; }
    .compact.keep-context #line { display: block; }
    .compact.keep-context #active { height: 1fr; }

    """

    def __init__(
        self, config: Config, *, lyrics_file: Path | None = None, demo: bool = False
    ) -> None:
        super().__init__()
        self.config = config
        self.lyrics_file = lyrics_file
        self.demo = demo
        self.manager = DemoManager() if demo else MPRISManager(config.preferred_player)
        self.lyrics = Lyrics()
        self.timeline = Timeline(self.lyrics, config.mode)
        self.track_key: tuple | None = None
        self.lyrics_task: asyncio.Task | None = None
        self.manager_task: asyncio.Task | None = None
        self.client: httpx.AsyncClient | None = None
        self.provider: LRCLibProvider | None = None
        self.lyrics_message = "Play a song in an MPRIS-compatible player"
        self.notice = ""
        self.notice_until = 0.0
        self.last_updates: dict[str, object] = {}
        self.metadata_key: tuple | None = None
        self.widgets: dict[str, Static] = {}
        self.pending_controls: set[asyncio.Task] = set()
        self.bindings_map = {action: key for key, action in config.shortcuts.items()}
        for key, action in config.shortcuts.items():
            self.bind(key, action, description=action.replace("_", " "))

    def compose(self) -> ComposeResult:
        with Vertical(id="shell"):
            with Horizontal(id="masthead"):
                yield Static("◉  L Y R A", id="brand", markup=False)
                yield Static("○  WAITING", id="connection", markup=False)
            with Vertical(id="metadata"):
                yield Static("♫  YOUR MUSIC, IN WORDS", id="player", markup=False)
                yield Static("Ready when you are", id="title", markup=False)
                yield Static("", id="artist", markup=False)
            with Vertical(id="stage"):
                yield Static("", id="previous", markup=False)
                yield Static("◌", id="active", markup=False)
                yield Static("", id="following", markup=False)
                yield Static("", id="line", markup=False)
                with VerticalScroll(id="plain-scroll"):
                    yield Static("", id="plain", markup=False)
            yield Static("", id="source", markup=False)
            yield Static("", id="progress", markup=False)
            yield Static("", id="times", markup=False)
            yield Static("", id="status", markup=False)
            yield Static("", id="notice", markup=False)
            yield Static("", id="keys", markup=False)

    async def on_mount(self) -> None:
        self.main_screen = self.screen
        self.plain_scroll = self.query_one("#plain-scroll")
        self.plain_scroll.can_focus = False
        self.shell = self.query_one("#shell")
        self.stage = self.query_one("#stage")
        for widget in self.query(Static):
            if widget.id:
                self.widgets[widget.id] = widget
        self.screen.set_class(self.config.compact, "compact")
        self.screen.set_class(self.size.height < 26 or self.size.width < 55, "short")
        self.apply_display_preferences()
        self.apply_accent()
        self.client = httpx.AsyncClient(
            base_url="https://lrclib.net",
            timeout=httpx.Timeout(12, connect=5),
            headers={"User-Agent": self.config.user_agent, "Accept": "application/json"},
            follow_redirects=False,
        )
        self.provider = LRCLibProvider(
            LyricsCache(
                cache_path() / "lyrics",
                self.config.cache_ttl_days * 86400,
                self.config.cache_max_entries,
                self.config.cache_enabled,
            ),
            self.client,
            estimate=self.config.estimate_words,
        )
        self.manager_task = asyncio.create_task(self.manager.run(), name="mpris")
        self.set_interval(1 / self.config.refresh_rate, self.tick)
        self.tick()

    async def on_unmount(self) -> None:
        tasks = [
            task
            for task in [self.manager_task, self.lyrics_task, *self.pending_controls]
            if task is not None
        ]
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        if self.client:
            await self.client.aclose()

    def on_resize(self, event: events.Resize) -> None:
        if hasattr(self, "main_screen"):
            self.main_screen.set_class(event.size.height < 26 or event.size.width < 55, "short")

    def put(self, name: str, value: str | Text) -> None:
        if self.last_updates.get(name) != value:
            self.widgets[name].update(value)
            self.last_updates[name] = value.copy() if isinstance(value, Text) else value

    def tick(self) -> None:
        if not self.widgets:
            return
        player = self.manager.active
        key = (player.name, player.track.track_id, *player.track.signature) if player else None
        if key != self.track_key:
            self.track_key = key
            self.start_lyrics(player.track if player else None)
        self.render_metadata(player)
        position = player.clock.read() if player else 0
        known = bool(player and player.clock.known)
        frame = self.timeline.at(position, self.config.sync_offset_ms / 1000) if known else Frame()
        self.render_frame(frame, known)
        self.render_transport(player, position)
        message = self.notice if self.notice_until > asyncio.get_running_loop().time() else ""
        if not message:
            message = self.lyrics_message if player else self.manager.message
        if player and not known:
            message = "Playback position unavailable · cannot synchronize this player"
        self.put("notice", safe_text(message))

    def render_metadata(self, player: Player | None) -> None:
        key = (player.name, player.track) if player else None
        if key == self.metadata_key:
            return
        self.metadata_key = key
        self.put(
            "connection", "●  DEMO" if self.demo else ("●  CONNECTED" if player else "○  WAITING")
        )
        self.put(
            "player", safe_text(f"♫  {player.identity}" if player else "♫  YOUR MUSIC, IN WORDS")
        )
        self.put(
            "title",
            safe_text(player.track.title or "Title unavailable")
            if player
            else "Ready when you are",
        )
        self.put(
            "artist",
            safe_text(" · ".join(filter(None, [player.track.artist, player.track.album])))
            if player
            else "Open Spotify, YouTube Music, or another media player",
        )

    def render_frame(self, frame: Frame, known: bool) -> None:
        plain = bool(self.lyrics.plain and not self.lyrics.lines)
        self.plain_scroll.display = plain and not self.config.compact
        self.widgets["active"].display = not plain or self.config.compact
        if plain:
            self.put("plain", safe_text(self.lyrics.plain))
        self.put("previous", safe_text(frame.previous))
        self.put("following", safe_text(frame.following))
        active = frame.active or (
            "UNSYNCED LYRICS"
            if plain
            else "INSTRUMENTAL"
            if self.lyrics.instrumental
            else "· · ·"
            if known
            else "WAITING"
        )
        if not self.lyrics.lines and not plain and not self.lyrics.instrumental:
            active = "L Y R A" if known else "WAITING"
        accent = Color.parse(self.config.accent_color)
        # Color-only transitions never delay or debounce a word boundary.
        intensity = self.config.animation_intensity
        blend = round((1 - frame.progress) * intensity * 0.35, 1) if frame.active else 0
        color = accent.blend(Color.parse("#ffffff"), blend).hex
        display = safe_text(active.upper())
        if self.config.ascii_art and frame.active:
            stage_height = self.stage.size.height
            context_height = 2 if self.config.show_context else 0
            available = stage_height - context_height - (0 if self.config.compact else 2)
            display = render_ascii(display, self.widgets["active"].content_size.width, available)
        if not self.config.compact:
            self.widgets["active"].styles.height = (
                5 if is_art(display) else 1 if self.main_screen.has_class("short") else 3
            )
        self.put("active", Text(display, style=f"bold {color}"))
        self.put("line", safe_text(frame.line))
        timing = {
            "word": "WORD TIMESTAMPS",
            "approximate": "≈ ESTIMATED WORD TIMING",
            "line": "LINE TIMESTAMPS",
            "unsynced": "UNSYNCED · NO TIMING",
        }[self.lyrics.timing]
        self.put(
            "source", safe_text(f"{timing}  ·  {self.lyrics.source}" if self.lyrics.source else "")
        )

    def render_transport(self, player: Player | None, position: float) -> None:
        duration = player.track.duration if player else 0
        width = max(4, self.widgets["progress"].size.width)
        fraction = min(1.0, position / duration) if duration else 0
        fill = min(width - 1, int(fraction * (width - 1)))
        bar = Text("━" * fill + "●", style=self.config.accent_color)
        bar.append("━" * (width - fill - 1), style="#263449")
        self.put("progress", bar)
        elapsed = timestamp(position) if player and player.clock.known else "--:--"
        total = timestamp(duration) if duration else "--:--"
        self.put("times", elapsed + " " * max(1, width - len(elapsed) - len(total)) + total)
        status = player.clock.status.upper() if player else "DISCONNECTED"
        rate = f"  {player.clock.rate:g}×" if player and player.clock.rate != 1 else ""
        self.put(
            "status",
            Text(
                f"{self.config.mode.upper()} MODE   SYNC {self.config.sync_offset_ms:+d}ms   "
                f"{status}{rate}",
                style=self.config.accent_color,
            ),
        )
        hints = [
            ("toggle_play", "play/pause"),
            ("choose_player", "players"),
            ("help", "help"),
            ("quit", "quit"),
        ]
        self.put(
            "keys",
            "   ".join(
                f"{self.bindings_map[action]} {label}"
                for action, label in hints
                if action in self.bindings_map
            ),
        )

    def start_lyrics(self, track: Track | None, force: bool = False) -> None:
        if self.lyrics_task:
            self.lyrics_task.cancel()
        self.lyrics = Lyrics()
        self.timeline = Timeline(self.lyrics, self.config.mode)
        self.lyrics_message = "Finding your words…" if track else "Waiting for music…"
        if track:
            self.lyrics_task = asyncio.create_task(self.fetch_lyrics(track, force), name="lyrics")

    async def fetch_lyrics(self, track: Track, force: bool) -> None:
        try:
            if self.lyrics_file:
                lyrics = await asyncio.to_thread(
                    load_local,
                    self.lyrics_file,
                    track.duration,
                    estimate=self.config.estimate_words,
                )
            elif self.demo:
                lyrics = demo_lyrics()
            elif self.config.provider == "local":
                self.lyrics_message = "Local provider selected · start with --lyrics /path/song.lrc"
                return
            elif self.provider:
                lyrics = await self.provider.fetch(track, force=force)
            else:
                return
            self.lyrics = lyrics
            self.timeline = Timeline(lyrics, self.config.mode)
            self.lyrics_message = (
                "Local file pinned · R reloads"
                if self.lyrics_file
                else (
                    "Instrumental track"
                    if lyrics.instrumental
                    else "≈ Word timing estimated from lines"
                    if lyrics.timing == "approximate"
                    else "Plain lyrics · synchronization unavailable"
                    if lyrics.timing == "unsynced"
                    else "Follow the signal"
                )
            )
        except asyncio.CancelledError:
            raise
        except Exception as error:
            LOG.debug("Lyrics loading failed", exc_info=True)
            self.lyrics_message = f"{error} · R retries"

    def flash(self, text: str) -> None:
        self.notice = text
        self.notice_until = asyncio.get_running_loop().time() + 4

    async def control(self, command: str, seconds: float = 0) -> None:
        try:
            await self.manager.control(command, seconds)
        except PlayerError as error:
            self.flash(str(error))

    def dispatch_control(self, command: str, seconds: float = 0) -> None:
        task = asyncio.create_task(self.control(command, seconds))
        self.pending_controls.add(task)
        task.add_done_callback(self.pending_controls.discard)

    def action_toggle_play(self) -> None:
        self.dispatch_control("PlayPause")

    def action_seek_back(self) -> None:
        self.dispatch_control("Seek", -5)

    def action_seek_forward(self) -> None:
        self.dispatch_control("Seek", 5)

    def action_offset_up(self) -> None:
        self.config.sync_offset_ms = min(60000, self.config.sync_offset_ms + 50)
        self.flash(f"Lyrics advanced · {self.config.sync_offset_ms:+d}ms")

    def action_offset_down(self) -> None:
        self.config.sync_offset_ms = max(-60000, self.config.sync_offset_ms - 50)
        self.flash(f"Lyrics delayed · {self.config.sync_offset_ms:+d}ms")

    def set_mode(self, mode: str) -> None:
        self.config.mode = mode
        self.timeline = Timeline(self.lyrics, mode)

    def action_word(self) -> None:
        self.set_mode("word")

    def action_duo(self) -> None:
        self.set_mode("duo")

    def action_compact(self) -> None:
        self.config.compact = not self.config.compact
        self.apply_display_preferences()

    def apply_display_preferences(self) -> None:
        self.main_screen.set_class(self.config.compact, "compact")
        self.main_screen.set_class(self.config.ascii_art, "ascii")
        self.main_screen.set_class(not self.config.show_context, "no-context")
        self.main_screen.set_class(self.config.show_context, "keep-context")
        self.widgets["active"].styles.height = None

    def action_toggle_ascii(self) -> None:
        self.config.ascii_art = not self.config.ascii_art
        if self.config.ascii_art:
            self.set_mode("word")
        self.apply_display_preferences()

    def action_settings(self) -> None:
        def applied(result: dict | None) -> None:
            if result is not None:
                if result["ascii_art"] and not self.config.ascii_art:
                    self.set_mode("word")
                self.config.ascii_art = result["ascii_art"]
                self.config.show_context = result["show_context"]
                self.config.compact = result["compact"]
                if result["theme"] != self.config.theme:
                    self.config.theme = result["theme"]
                    self.config.accent = ""
                    self.apply_accent()
                self.apply_display_preferences()

        self.push_screen(SettingsScreen(self.config), applied)

    def apply_accent(self) -> None:
        self.widgets["brand"].styles.color = self.config.accent_color
        self.shell.styles.border = ("round", self.config.accent_color)

    def action_cycle_theme(self) -> None:
        names = list(THEMES)
        self.config.theme = names[(names.index(self.config.theme) + 1) % len(names)]
        self.config.accent = ""
        self.apply_accent()

    def action_choose_player(self) -> None:
        def selected(name: str | None) -> None:
            self.manager.selected = name
            self.config.preferred_player = name or ""
            if name and name not in self.manager.players:
                self.flash("Player disconnected · returning to automatic selection")

        self.push_screen(PlayerScreen(self.manager), selected)

    def action_refresh_lyrics(self) -> None:
        if self.manager.active:
            self.start_lyrics(self.manager.active.track, force=True)
        else:
            self.flash("No player connected · play a song first")

    def action_help(self) -> None:
        self.push_screen(HelpScreen(self.config))

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Label, OptionList, Static
from textual.widgets.option_list import Option

from lyra.config import Config
from lyra.mpris.client import MPRISManager
from lyra.utils.text import safe_text


class HelpScreen(ModalScreen[None]):
    BINDINGS = [
        ("escape", "dismiss", "Close"),
        ("h", "dismiss", "Close"),
        ("question_mark", "dismiss", "Close"),
    ]
    DEFAULT_CSS = """
    HelpScreen { align: center middle; background: #050810 80%; }
    #help-box { width: 68; max-width: 95%; height: auto; max-height: 95%;
        border: round #a3ff79; background: #0e1522; padding: 1 3; overflow-y: auto; }
    #help-box Static { height: auto; margin-bottom: 1; }
    """

    def __init__(self, config: Config) -> None:
        super().__init__()
        self.config = config

    def compose(self) -> ComposeResult:
        with Vertical(id="help-box"):
            yield Static("◉  LYRA  /  KEYBOARD", markup=False)
            keys = Text()
            for key, action in self.config.shortcuts.items():
                keys.append(f"{key:18}", style="bold #a3ff79")
                keys.append(action.replace("_", " ") + "\n")
            yield Static(keys)
            yield Static(
                "↑ advances lyrics by 50 ms; ↓ delays them.\n"
                "≈ means estimated word timing. Unsynced lyrics have no highlight.\n"
                "The local --lyrics file is pinned across track changes.\n"
                "Preferences are saved on exit. Escape closes this panel.",
                markup=False,
            )


class PlayerScreen(ModalScreen[str | None]):
    BINDINGS = [("escape", "cancel", "Cancel")]
    DEFAULT_CSS = """
    PlayerScreen { align: center middle; background: #050810 80%; }
    #player-box { width: 72; max-width: 95%; height: auto; max-height: 90%;
        background: #0e1522; padding: 1 2; border: round #67e8f9; }
    #player-box Label { margin-bottom: 1; }
    #choices { height: auto; max-height: 16; }
    """

    def __init__(self, manager: MPRISManager) -> None:
        super().__init__()
        self.manager = manager
        self.names = [None, *sorted(manager.players)]

    def compose(self) -> ComposeResult:
        with Vertical(id="player-box"):
            yield Label("CHOOSE PLAYER · Enter selects · Esc cancels", markup=False)
            choices = [Option("Automatic · follow the playing player", id="auto")]
            for name in self.names[1:]:
                player = self.manager.players[name]
                choices.append(
                    Option(
                        Text(safe_text(f"{player.identity} · {player.clock.status}\n{name}")),
                        id=name,
                    )
                )
            yield OptionList(*choices, id="choices")

    def on_mount(self) -> None:
        self.query_one(OptionList).focus()

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        self.dismiss(None if event.option.id == "auto" else event.option.id)

    def action_cancel(self) -> None:
        self.app.pop_screen()


class SettingsScreen(ModalScreen[dict | None]):
    BINDINGS = [("escape", "dismiss", "Cancel")]
    DEFAULT_CSS = """
    SettingsScreen { align: center middle; background: #050810 80%; }
    #settings-box { width: 64; max-width: 95%; height: auto; max-height: 95%;
        border: round #a3ff79; background: #0e1522; padding: 1 2; overflow-y: auto; }
    #settings-box Static { height: auto; margin-bottom: 1; }
    .setting { height: 3; align-vertical: middle; }
    .setting Label { width: 1fr; height: 3; content-align: left middle; }
    #settings-actions { height: 3; margin-top: 1; align-horizontal: right; }
    """

    def __init__(self, config: Config) -> None:
        super().__init__()
        self.config = config

    def compose(self) -> ComposeResult:
        from textual.containers import Horizontal
        from textual.widgets import Button, Switch

        with Vertical(id="settings-box"):
            yield Static("◉  LYRA / DISPLAY SETTINGS", markup=False)
            for name, label in (
                ("ascii_art", "Large ASCII words"),
                ("show_context", "Keep the small lyric text"),
                ("compact", "Compact view"),
            ):
                with Horizontal(classes="setting"):
                    yield Label(label, markup=False)
                    yield Switch(getattr(self.config, name), id=f"setting-{name}")
            yield Static(
                "ASCII starts in word mode. Long words and small windows use normal text.\n"
                "Tab moves · Space toggles · Escape cancels",
                markup=False,
            )
            with Horizontal(id="settings-actions"):
                yield Button("Apply", id="apply-settings", variant="success")

    def on_button_pressed(self, event) -> None:
        from textual.widgets import Switch

        if event.button.id == "apply-settings":
            self.dismiss(
                {
                    name: self.query_one(f"#setting-{name}", Switch).value
                    for name in ("ascii_art", "show_context", "compact")
                }
            )

import importlib.util
import unittest

HAS_TEXTUAL = importlib.util.find_spec("textual") is not None


@unittest.skipUnless(HAS_TEXTUAL, "Textual is not installed; UI runtime verification unavailable")
class UITests(unittest.IsolatedAsyncioTestCase):
    async def test_auto_sync_and_explicit_estimated_words_setting(self):
        from textual.widgets import Select

        from lyra.app import LyraApp
        from lyra.config import Config
        from lyra.lyrics.parser import parse_lrc

        app = LyraApp(Config(mode="word"), demo=True)
        async with app.run_test(size=(100, 36)) as pilot:
            await pilot.pause()
            app.manager.active.clock.update(position=3, status="Paused")
            app.lyrics = parse_lrc("[00:01]A held note\n[00:10]Next line", 15, source="test")
            app.set_mode("word")
            await pilot.pause()
            self.assertEqual(app.last_updates["active"].plain, "A HELD NOTE")
            self.assertIn("LINE SYNC", app.last_updates["source"])
            self.assertIn("AUTO LINE MODE", app.last_updates["status"].plain)
            await pilot.press("s")
            app.screen.query_one("#setting-sync-mode", Select).value = "estimated"
            await pilot.click("#apply-settings")
            await pilot.pause()
            self.assertEqual(app.config.sync_mode, "estimated")
            self.assertNotEqual(app.last_updates["active"].plain, "A HELD NOTE")
            self.assertTrue(app.timeline.at(3).approximate)
            self.assertIn("ESTIMATED", app.last_updates["source"])

    async def test_monochrome_colors_across_main_and_modal_screens(self):
        import os
        from colorsys import rgb_to_hsv
        from unittest.mock import patch

        from lyra.app import LyraApp
        from lyra.config import THEMES, Config

        for theme in ("white", "cyan", "violet", "green"):
            # Exercise actual theme colors even when the test shell has NO_COLOR.
            with patch.dict(os.environ):
                os.environ.pop("NO_COLOR", None)
                app = LyraApp(Config(ascii_art=True), demo=True)
            async with app.run_test(size=(100, 36)) as pilot:
                await pilot.pause()
                app.config.theme = theme
                app.apply_accent()
                await pilot.pause()
                target = tuple(int(THEMES[theme][i : i + 2], 16) / 255 for i in (1, 3, 5))
                hue = rgb_to_hsv(*target)[0]
                for keys in ((), ("h",), ("escape", "p"), ("escape", "s"), ("tab", "enter")):
                    if keys == ("tab", "enter"):
                        await pilot.click("#setting-theme")
                        self.assertTrue(
                            app.screen.query_one("#setting-theme").has_class("-expanded")
                        )
                    else:
                        await pilot.press(*keys)
                    await pilot.pause()
                    colors = set()
                    for strip in app.screen._compositor.render_strips():
                        for segment in strip:
                            if segment.style:
                                for color in (segment.style.color, segment.style.bgcolor):
                                    if color:
                                        colors.add(color.get_truecolor())
                    self.assertTrue(colors)
                    if theme != "white":
                        self.assertTrue(any(max(color) - min(color) > 12 for color in colors))
                    for color in colors:
                        with self.subTest(theme=theme, keys=keys, color=color):
                            if theme == "white":
                                self.assertEqual(color.red, color.green)
                                self.assertEqual(color.green, color.blue)
                            elif max(color) - min(color) > 12:
                                actual = rgb_to_hsv(*(value / 255 for value in color))[0]
                                delta = abs(actual - hue)
                                self.assertLess(min(delta, 1 - delta), 0.08)

    async def test_color_selection_apply_cancel_and_cycle(self):
        from textual.widgets import Select

        from lyra.app import LyraApp
        from lyra.config import THEMES, Config

        app = LyraApp(Config(), demo=True)
        async with app.run_test(size=(100, 36)) as pilot:
            await pilot.pause()
            self.assertEqual(app.config.accent_color, "#ffffff")
            for theme in ("violet", "green", "cyan", "white"):
                await pilot.press("s")
                app.screen.query_one("#setting-theme", Select).value = theme
                await pilot.click("#apply-settings")
                await pilot.pause()
                self.assertEqual(app.config.theme, theme)
                self.assertEqual(app.widgets["brand"].styles.color.hex.lower(), THEMES[theme])
            await pilot.press("s")
            app.screen.query_one("#setting-theme", Select).value = "violet"
            await pilot.press("escape")
            self.assertEqual(app.config.theme, "white")
            app.config.accent = "#123456"
            await pilot.press("t")
            self.assertEqual(app.config.theme, "violet")
            self.assertEqual(app.config.accent, "")

    async def test_demo_controls_and_modals(self):
        from lyra.app import LyraApp
        from lyra.config import Config
        from lyra.ui.screens import HelpScreen, PlayerScreen

        app = LyraApp(Config(), demo=True)
        async with app.run_test(size=(100, 34)) as pilot:
            await pilot.pause()
            self.assertTrue(app.lyrics.lines)
            await pilot.press("space")
            await pilot.pause()
            self.assertEqual(app.manager.active.clock.status, "Paused")
            await pilot.press("right", "w", "up")
            await pilot.pause()
            self.assertEqual(app.config.mode, "word")
            self.assertEqual(app.config.sync_offset_ms, 50)
            await pilot.press("0")
            self.assertEqual(app.config.sync_offset_ms, 0)
            self.assertGreaterEqual(app.manager.active.clock.read(), 5)
            await pilot.press("h")
            self.assertIsInstance(app.screen, HelpScreen)
            await pilot.press("escape", "p")
            self.assertIsInstance(app.screen, PlayerScreen)
            await pilot.press("enter", "t", "d", "c")
            self.assertEqual(app.config.mode, "duo")
            self.assertTrue(app.main_screen.has_class("compact"))
            await pilot.press("c")
            await pilot.resize_terminal(38, 16)
            await pilot.pause()
            self.assertTrue(app.main_screen.has_class("short"))
            self.assertTrue(app.export_screenshot())

    async def test_missing_player_does_not_freeze(self):
        from lyra.app import LyraApp
        from lyra.config import Config

        app = LyraApp(Config(), demo=True)
        app.manager.players.clear()
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            await pilot.press("space", "right", "r")
            await pilot.pause()
            self.assertIn("No player", app.notice)
            self.assertFalse(app.lyrics.lines)

    async def test_ascii_settings_and_small_context(self):
        from textual.widgets import Switch

        from lyra.app import LyraApp
        from lyra.config import Config
        from lyra.ui.screens import SettingsScreen

        app = LyraApp(Config(), demo=True)
        async with app.run_test(size=(100, 36)) as pilot:
            await pilot.pause()
            app.manager.active.clock.update(position=2.2, status="Paused")
            await pilot.press("a")
            await pilot.pause()
            self.assertTrue(app.config.ascii_art)
            self.assertEqual(app.config.mode, "word")
            self.assertIn("\n", app.last_updates["active"].plain)
            self.assertTrue(app.widgets["line"].display)
            await pilot.press("s")
            self.assertIsInstance(app.screen, SettingsScreen)
            app.screen.query_one("#setting-show_context", Switch).value = False
            await pilot.click("#apply-settings")
            await pilot.pause()
            self.assertFalse(app.config.show_context)
            self.assertFalse(app.widgets["line"].display)
            self.assertTrue(app.config.ascii_art)
            await pilot.press("s")
            app.screen.query_one("#setting-show_context", Switch).value = True
            app.screen.query_one("#setting-compact", Switch).value = True
            await pilot.click("#apply-settings")
            await pilot.pause()
            self.assertTrue(app.config.compact)
            self.assertTrue(app.widgets["line"].display)
            self.assertIn("\n", app.last_updates["active"].plain)
            await pilot.resize_terminal(16, 6)
            await pilot.pause()
            self.assertNotIn("\n", app.last_updates["active"].plain)

    async def test_settings_cancel_keeps_preferences(self):
        from textual.widgets import Switch

        from lyra.app import LyraApp
        from lyra.config import Config

        app = LyraApp(Config(), demo=True)
        async with app.run_test(size=(100, 34)) as pilot:
            await pilot.press("s")
            app.screen.query_one("#setting-ascii_art", Switch).value = True
            await pilot.press("escape")
            self.assertFalse(app.config.ascii_art)

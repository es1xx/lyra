import importlib.util
import unittest

HAS_TEXTUAL = importlib.util.find_spec("textual") is not None


@unittest.skipUnless(HAS_TEXTUAL, "Textual is not installed; UI runtime verification unavailable")
class UITests(unittest.IsolatedAsyncioTestCase):
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

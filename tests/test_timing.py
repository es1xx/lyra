import unittest

from lyra.lyrics.parser import LyricsError, parse_lrc
from lyra.sync.clock import PlaybackClock
from lyra.sync.timeline import Timeline


class ParserTests(unittest.TestCase):
    def test_standard_and_estimation(self):
        lyrics = parse_lrc("[00:01.50]Tiny glowing city\n[00:05.000]Next", 8)
        self.assertEqual(lyrics.lines[0].start, 1.5)
        self.assertEqual(lyrics.lines[0].end, 5)
        self.assertEqual(lyrics.timing, "approximate")
        self.assertAlmostEqual(lyrics.lines[0].words[-1].end, 5)

    def test_no_estimation(self):
        lyrics = parse_lrc("[00:01]A whole line", 5, estimate=False)
        self.assertEqual(lyrics.timing, "line")
        self.assertEqual(lyrics.lines[0].words, ())

    def test_enhanced_exact_times(self):
        lyrics = parse_lrc("[00:01]<00:01>Green <00:02.125>lights<00:03>\n[00:04]", 7)
        self.assertEqual(lyrics.timing, "word")
        self.assertEqual(lyrics.lines[0].words[0].end, 2.125)
        self.assertEqual(lyrics.lines[0].words[-1].end, 3)
        self.assertEqual(lyrics.lines[1].text, "")

    def test_enhanced_group_kept_intact(self):
        lyrics = parse_lrc("[00:01]<00:01>one group <00:03>next", 5)
        self.assertEqual(lyrics.lines[0].words[0].text, "one group")
        self.assertFalse(lyrics.lines[0].words[0].approximate)

    def test_repeated_tags_sorted_with_relative_words(self):
        lyrics = parse_lrc("[00:10][00:20]<00:10>Again <00:11>here", 25)
        self.assertEqual(lyrics.lines[1].words[0].start, 20)
        self.assertEqual(lyrics.lines[1].words[1].start, 21)

    def test_fraction_variants_bom_offset(self):
        lyrics = parse_lrc("\ufeff[ar:Original]\n[offset:-100]\n[00:01:5]Signal", 3)
        self.assertAlmostEqual(lyrics.lines[0].start, 1.4)

    def test_enhanced_offset(self):
        lyrics = parse_lrc("[offset:250]\n[00:01]<00:01>Signal <00:02>home", 4)
        self.assertEqual(lyrics.lines[0].words[0].start, 1.25)
        self.assertEqual(lyrics.lines[0].words[1].start, 2.25)

    def test_plain(self):
        lyrics = parse_lrc("Original words\nA second line")
        self.assertEqual(lyrics.timing, "unsynced")
        self.assertIn("second line", lyrics.plain)

    def test_empty_invalid_and_mixed(self):
        for content in [
            "",
            "[ar:Nobody]",
            "[00:99]bad",
            "[00:01]timed\nuntimed",
            "[00:01]<00:03>late <00:02>early",
            "[00:01]prefix <00:02>tag",
        ]:
            with self.subTest(content=content), self.assertRaises(LyricsError):
                parse_lrc(content)

    def test_unicode(self):
        lyrics = parse_lrc("[00:00]Місто світиться 夜の光", 5)
        self.assertIn("夜の光", lyrics.plain)


class TimelineTests(unittest.TestCase):
    def setUp(self):
        self.lyrics = parse_lrc(
            "[00:01]<00:01>One <00:02>two <00:03>three<00:04>\n[00:05]\n[00:07]<00:07>Next<00:08>",
            10,
        )

    def test_boundaries_and_gaps(self):
        timeline = Timeline(self.lyrics, "word")
        self.assertEqual(timeline.at(0).active, "")
        self.assertEqual(timeline.at(1).active, "One")
        self.assertEqual(timeline.at(1.999).active, "One")
        self.assertEqual(timeline.at(2).active, "two")
        self.assertEqual(timeline.at(4.1).active, "")
        self.assertEqual(timeline.at(5.5).active, "")
        self.assertEqual(timeline.at(11).active, "")

    def test_duo_never_crosses_lines(self):
        timeline = Timeline(self.lyrics, "duo")
        self.assertEqual(timeline.at(1).active, "One two")
        self.assertEqual(timeline.at(3).active, "three")
        self.assertEqual(timeline.at(7).active, "Next")

    def test_seek_and_offset_are_stateless(self):
        timeline = Timeline(self.lyrics, "word")
        self.assertEqual(timeline.at(7.2).active, "Next")
        self.assertEqual(timeline.at(1.1).active, "One")
        self.assertEqual(timeline.at(1.8, 0.3).active, "two")
        self.assertEqual(timeline.at(2.1, -0.3).active, "One")

    def test_context_and_progress(self):
        frame = Timeline(self.lyrics, "word").at(2.5)
        self.assertEqual((frame.previous, frame.following), ("One", "three"))
        self.assertAlmostEqual(frame.progress, 0.5)

    def test_estimation_flag(self):
        self.assertTrue(Timeline(parse_lrc("[00:00]a b", 4)).at(1).approximate)

    def test_auto_uses_lines_instead_of_guessed_word_boundaries(self):
        lyrics = parse_lrc("[00:01]A long held note\n[00:10]Next line", 15)
        auto = Timeline(lyrics, "word", estimate=False)
        for position in (1, 2, 5, 9.9):
            self.assertEqual(auto.at(position).active, "A long held note")
        self.assertEqual(auto.at(10).active, "Next line")
        self.assertEqual(auto.at(0).active, "")

    def test_auto_preserves_exact_words_and_explicit_rests(self):
        auto = Timeline(self.lyrics, "word", estimate=False)
        self.assertEqual(auto.at(2.5).active, "two")
        self.assertEqual(auto.at(4.5).active, "")

    def test_plain_has_no_karaoke(self):
        self.assertEqual(Timeline(parse_lrc("plain lyrics")).at(1).active, "")


class ClockTests(unittest.TestCase):
    def setUp(self):
        self.now = 100.0
        self.clock = PlaybackClock(lambda: self.now)
        self.clock.update(position=10, status="Playing", duration=100)

    def test_interpolation(self):
        self.now += 2
        self.assertEqual(self.clock.read(), 12)

    def test_pause_resume(self):
        self.now += 2
        self.clock.update(status="Paused")
        self.now += 8
        self.assertEqual(self.clock.read(), 12)
        self.clock.update(status="Playing")
        self.now += 3
        self.assertEqual(self.clock.read(), 15)

    def test_rate_change_is_continuous(self):
        self.now += 2
        self.clock.update(rate=2)
        self.assertEqual(self.clock.read(), 12)
        self.now += 2
        self.assertEqual(self.clock.read(), 16)

    def test_seek_and_drift_correction(self):
        self.now += 20
        self.clock.update(position=1)
        self.assertEqual(self.clock.read(), 1)
        self.now += 0.5
        self.clock.update(position=1.45)
        self.assertEqual(self.clock.read(), 1.45)

    def test_clamp_and_reset(self):
        self.clock.update(position=-3)
        self.assertEqual(self.clock.read(), 0)
        self.now += 200
        self.assertEqual(self.clock.read(), 100)
        self.clock.reset()
        self.assertFalse(self.clock.known)

    def test_missing_position(self):
        clock = PlaybackClock(lambda: self.now)
        clock.update(status="Playing")
        self.assertFalse(clock.known)

    def test_invalid_rate_is_ignored(self):
        for rate in [0, -1, float("nan"), float("inf")]:
            self.clock.update(rate=rate)
            self.assertEqual(self.clock.rate, 1)

    def test_poll_jitter_correction_never_reverses_clock(self):
        self.now += 1
        self.clock.sample(10.8, self.now)
        positions = []
        for _ in range(10):
            self.now += 0.05
            positions.append(self.clock.read())
        self.assertEqual(positions, sorted(positions))
        self.assertAlmostEqual(positions[-1], 11.3)

    def test_repeated_whole_second_samples_do_not_restart_playback(self):
        self.clock.sample(10, self.now)
        self.now += 0.5
        self.clock.sample(10, self.now)
        self.assertAlmostEqual(self.clock.read(), 10.5)
        self.now += 0.5
        self.clock.sample(11, self.now)
        self.assertAlmostEqual(self.clock.read(), 11)

    def test_samples_compensate_latency_and_snap_to_seek(self):
        self.now += 0.2
        self.clock.sample(10.1, self.now - 0.1)
        self.assertAlmostEqual(self.clock.read(), 10.2)
        self.clock.sample(40, self.now)
        self.assertAlmostEqual(self.clock.read(), 40)
        self.clock.sample(3, self.now)
        self.assertAlmostEqual(self.clock.read(), 3)

    def test_paused_samples_remain_exact_and_invalid_samples_are_ignored(self):
        self.clock.update(status="Paused")
        self.now += 2
        self.clock.sample(20, self.now - 1)
        self.assertEqual(self.clock.read(), 20)
        for value in (float("nan"), float("inf"), -1):
            self.clock.sample(value, self.now)
            self.assertEqual(self.clock.read(), 20)

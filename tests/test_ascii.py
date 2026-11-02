import unittest

from lyra.ui.ascii import PATTERNS, render_ascii


class AsciiTests(unittest.TestCase):
    def test_word_is_five_rows_of_ascii(self):
        art = render_ascii("Hello", 80, 8)
        self.assertEqual(len(art.splitlines()), 5)
        self.assertEqual(len(set(map(len, art.splitlines()))), 1)
        self.assertEqual(set(art) - {"#", " ", "\n"}, set())

    def test_ukrainian(self):
        self.assertEqual(len(render_ascii("Україна", 80, 8).splitlines()), 5)
        self.assertEqual(len(render_ascii("ЄҐІЇ", 80, 8).splitlines()), 5)

    def test_small_terminal_and_long_words_remain_readable(self):
        self.assertEqual(render_ascii("Hello", 8, 8), "HELLO")
        self.assertEqual(render_ascii("Hello", 80, 4), "HELLO")
        self.assertEqual(render_ascii("夜の光", 80, 8), "夜の光")

    def test_all_glyphs_are_rectangular(self):
        for letter, pattern in PATTERNS.items():
            with self.subTest(letter=letter):
                self.assertEqual(len(pattern.split("/")), 5)
                self.assertEqual(len(set(map(len, pattern.split("/")))), 1)

    def test_parenthesized_words_render_with_both_brackets(self):
        for word in ("(Hello)", "(Привіт)", "(Oh", "yeah)"):
            with self.subTest(word=word):
                art = render_ascii(word, 100, 8)
                self.assertEqual(len(art.splitlines()), 5)
                self.assertEqual(len(set(map(len, art.splitlines()))), 1)
                self.assertEqual(render_ascii(word, 3, 8), word.upper())
        left = render_ascii("(", 3, 5).splitlines()
        right = render_ascii(")", 3, 5).splitlines()
        self.assertEqual(left, [row[::-1] for row in right])
        art = render_ascii("(Hi)", 80, 8).splitlines()
        self.assertEqual([row[:3] for row in art], left)
        self.assertEqual([row[-3:] for row in art], right)

"""LRCLIB Lyricsfile v1: millisecond line/word timings, safely decoded YAML."""

import math
from typing import Any

import yaml

from lyra.lyrics.models import Line, Lyrics, Word
from lyra.lyrics.parser import LyricsError, estimated_words


def milliseconds(value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise LyricsError("Lyricsfile timestamps must be finite numbers")
    return value / 1000


def _words(raw: list, start: float, end: float, offset: float) -> tuple[Word, ...]:
    result = []
    previous = start
    for index, item in enumerate(raw):
        word_start = milliseconds(item["start_ms"]) + offset
        next_start = (
            milliseconds(raw[index + 1]["start_ms"]) + offset if index + 1 < len(raw) else end
        )
        word_end = milliseconds(item["end_ms"]) + offset if "end_ms" in item else next_start
        if word_start < previous or word_end < word_start or word_end > end or word_start < start:
            raise LyricsError("Lyricsfile word timestamps overlap or fall outside their line")
        text = str(item["text"]).strip()
        if text:
            result.append(Word(max(0, word_start), max(0, word_end), text))
        previous = word_end
    return tuple(result)


def parse_lyricsfile(text: str, duration: float, *, estimate: bool, source: str) -> Lyrics:
    if len(text) > 2_000_000:
        raise LyricsError("Lyricsfile exceeds the 2 MB limit")
    try:
        data = yaml.safe_load(text)
        if not isinstance(data, dict) or str(data.get("version", "1.0")) != "1.0":
            raise LyricsError("Unsupported Lyricsfile version")
        metadata = data.get("metadata") or {}
        offset = milliseconds(metadata.get("offset_ms", 0))
        if metadata.get("instrumental"):
            return Lyrics(source=source, instrumental=True)
        raw = sorted(data.get("lines") or [], key=lambda line: milliseconds(line["start_ms"]))
        lines = []
        for index, item in enumerate(raw):
            start = milliseconds(item["start_ms"]) + offset
            next_start = (
                milliseconds(raw[index + 1]["start_ms"]) + offset
                if index + 1 < len(raw)
                else (duration or milliseconds(metadata.get("duration_ms", 0)) or start + 5)
            )
            end = milliseconds(item["end_ms"]) + offset if "end_ms" in item else next_start
            if end < start or end > next_start:
                raise LyricsError("Lyricsfile line timestamps are out of order")
            raw_words = item.get("words") or []
            clean = str(item.get("text") or "".join(str(word["text"]) for word in raw_words))
            words = (
                _words(raw_words, start, end, offset)
                if raw_words
                else (estimated_words(clean, max(0, start), max(0, end)) if estimate else ())
            )
            lines.append(Line(max(0, start), max(0, end), clean, words))
        plain = str(data.get("plain") or "\n".join(line.text for line in lines))
        if not lines and not plain:
            raise LyricsError("Empty Lyricsfile")
        return Lyrics(tuple(lines), plain, source)
    except (yaml.YAMLError, KeyError, TypeError, AttributeError, RecursionError) as error:
        raise LyricsError(f"Invalid Lyricsfile: {error}") from error

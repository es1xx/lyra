"""Strict LRC/Enhanced LRC parser. Blank timed lines preserve instrumental gaps."""

import re
from pathlib import Path

from lyra.lyrics.models import Line, Lyrics, Word

STAMP = r"(\d{1,3}):([0-5]\d)(?:[.:](\d{1,3}))?"
LINE_TAG = re.compile(r"\[" + STAMP + r"\]")
WORD_TAG = re.compile(r"<" + STAMP + r">")
META_TAG = re.compile(r"^\[(?:ar|al|ti|by|re|ve|length|au|id):[^\]]*\]$", re.I)


class LyricsError(ValueError):
    pass


def seconds(match: re.Match[str]) -> float:
    fraction = match.group(3) or "0"
    return int(match.group(1)) * 60 + int(match.group(2)) + int(fraction) / 10 ** len(fraction)


def estimated_words(text: str, start: float, end: float) -> tuple[Word, ...]:
    tokens = text.split()
    weight = sum(max(1, len(token.strip(".,!?;:—"))) for token in tokens)
    result = []
    cursor = start
    for token in tokens:
        stop = cursor + (end - start) * max(1, len(token.strip(".,!?;:—"))) / weight
        result.append(Word(cursor, stop, token, True))
        cursor = stop
    return tuple(result)


def enhanced_words(body: str, start: float, end: float, shift: float) -> tuple[Word, ...]:
    tags = list(WORD_TAG.finditer(body))
    result = []
    if body[: tags[0].start()].strip():
        raise LyricsError("Enhanced LRC text must begin with a word timestamp")
    previous = start
    for index, tag in enumerate(tags):
        word_start = seconds(tag) + shift
        next_tag = tags[index + 1] if index + 1 < len(tags) else None
        word_end = seconds(next_tag) + shift if next_tag else end
        text = body[tag.end() : next_tag.start() if next_tag else len(body)].strip()
        if word_start < previous - 0.001 or word_end < word_start:
            raise LyricsError("Enhanced LRC timestamps are out of order")
        previous = word_start
        if text:
            # A timestamp can denote a group; keep it intact rather than inventing timestamps.
            result.append(Word(max(0, word_start), max(0, min(word_end, end)), text))
    return tuple(result)


def parse_lrc(text: str, duration: float = 0, *, estimate: bool = True, source: str = "") -> Lyrics:
    text = text.lstrip("\ufeff")
    offsets = re.findall(r"\[offset:([+-]?\d+)\]", text, re.I)
    offset = int(offsets[-1]) / 1000 if offsets else 0.0
    entries: list[tuple[float, str, float]] = []
    plain = []
    for raw in text.splitlines():
        raw = raw.strip()
        if not raw or META_TAG.fullmatch(raw) or re.fullmatch(r"\[offset:[+-]?\d+\]", raw, re.I):
            continue
        tags = list(LINE_TAG.finditer(raw))
        if not tags:
            if raw.startswith("[") or WORD_TAG.search(raw):
                raise LyricsError(f"Invalid LRC timestamp: {raw[:60]}")
            plain.append(raw)
            continue
        prefix = "".join(tag.group() for tag in tags)
        if not raw.startswith(prefix):
            raise LyricsError("Line timestamps must appear before lyric text")
        body = raw[len(prefix) :].strip()
        origin = seconds(tags[0])
        for tag in tags:
            # Repeated line tags copy relative enhanced word timestamps too.
            entries.append((seconds(tag) + offset, body, seconds(tag) - origin + offset))
    if not entries:
        if not plain:
            raise LyricsError("Lyrics file contains no lyrics")
        return Lyrics(plain="\n".join(plain), source=source)
    if plain:
        raise LyricsError("Mixed timed and untimed lines; check the LRC file")
    return _build_lines(entries, duration, estimate, source)


def _build_lines(
    entries: list[tuple[float, str, float]], duration: float, estimate: bool, source: str
) -> Lyrics:
    entries.sort(key=lambda entry: entry[0])
    lines = []
    for index, (raw_start, body, shift) in enumerate(entries):
        start = max(0.0, raw_start)
        # No duration: cap the final line, rather than retaining the last word forever.
        end = entries[index + 1][0] if index + 1 < len(entries) else (duration or start + 5)
        end = max(start, end)
        clean = WORD_TAG.sub("", body).strip()
        if WORD_TAG.search(body):
            words = enhanced_words(body, raw_start, end, shift)
        else:
            words = estimated_words(clean, start, end) if estimate else ()
        lines.append(Line(start, end, clean, words))
    return Lyrics(tuple(lines), "\n".join(line.text for line in lines), source)


def load_local(path: Path, duration: float = 0, *, estimate: bool = True) -> Lyrics:
    if path.stat().st_size > 2_000_000:
        raise LyricsError("Lyrics file exceeds the 2 MB limit")
    return parse_lrc(
        path.read_text(encoding="utf-8-sig"),
        duration,
        estimate=estimate,
        source=f"Local · {path.name}",
    )

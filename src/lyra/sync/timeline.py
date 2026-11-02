from bisect import bisect_right
from dataclasses import dataclass

from lyra.lyrics.models import Lyrics, Word


@dataclass(frozen=True)
class Frame:
    previous: str = ""
    active: str = ""
    following: str = ""
    line: str = ""
    approximate: bool = False
    progress: float = 0.0


class Timeline:
    def __init__(self, lyrics: Lyrics, mode: str = "duo", *, estimate: bool = True) -> None:
        self.lyrics = lyrics
        self.groups: list[Word] = []
        size = 1 if mode == "word" else 2
        for line in lyrics.lines:
            if not line.words or (not estimate and any(word.approximate for word in line.words)):
                if line.text:
                    self.groups.append(Word(line.start, line.end, line.text))
                continue
            for index in range(0, len(line.words), size):
                chunk = line.words[index : index + size]
                self.groups.append(
                    Word(
                        chunk[0].start,
                        chunk[-1].end,
                        " ".join(word.text for word in chunk),
                        any(word.approximate for word in chunk),
                    )
                )
        self.groups.sort(key=lambda word: word.start)
        self.starts = [word.start for word in self.groups]
        self.line_starts = [line.start for line in lyrics.lines]

    def at(self, position: float, offset: float = 0) -> Frame:
        # Positive offset advances lyrics relative to audio; no timer drives lyric selection.
        position += offset
        index = bisect_right(self.starts, position) - 1
        line_index = bisect_right(self.line_starts, position) - 1
        line = self.lyrics.lines[line_index] if line_index >= 0 else None
        context = line.text if line and position < line.end else ""
        previous = self.groups[index - 1].text if index > 0 else ""
        following = self.groups[index + 1].text if index + 1 < len(self.groups) else ""
        if index < 0:
            return Frame(following=following)
        word = self.groups[index]
        if position >= word.end:
            return Frame(previous=word.text, following=following, line=context)
        progress = (position - word.start) / max(0.001, word.end - word.start)
        return Frame(previous, word.text, following, context, word.approximate, progress)

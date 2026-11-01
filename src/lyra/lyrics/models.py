from dataclasses import dataclass


@dataclass(frozen=True)
class Word:
    start: float
    end: float
    text: str
    approximate: bool = False


@dataclass(frozen=True)
class Line:
    start: float
    end: float
    text: str
    words: tuple[Word, ...] = ()


@dataclass(frozen=True)
class Lyrics:
    lines: tuple[Line, ...] = ()
    plain: str = ""
    source: str = ""
    instrumental: bool = False

    @property
    def timing(self) -> str:
        words = [word for line in self.lines for word in line.words]
        if not self.lines:
            return "unsynced"
        if not words:
            return "line"
        return "approximate" if any(word.approximate for word in words) else "word"

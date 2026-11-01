import re

CONTROL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f-\x9f]")


def safe_text(value: str) -> str:
    """Metadata and lyric text are untrusted, never Rich markup or terminal escapes."""
    return CONTROL.sub("", value).replace("\t", " ")


def timestamp(seconds: float) -> str:
    seconds = max(0, int(seconds))
    return f"{seconds // 60:02d}:{seconds % 60:02d}"

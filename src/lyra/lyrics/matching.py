"""Conservative metadata matching; versions remain meaningful."""

import math
import re
import unicodedata
from typing import Any

try:
    from rapidfuzz.fuzz import ratio
except ImportError:
    from difflib import SequenceMatcher

    def ratio(first: str, second: str) -> float:
        return SequenceMatcher(None, first, second, autojunk=False).ratio() * 100


from lyra.mpris.models import Track


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).casefold()
    text = re.sub(r"[\[(]?\b(?:feat\.?|ft\.?|featuring)\s+[^\])]*[\])]?", " ", text)
    text = re.sub(r"\b(?:\d{4}\s+)?remaster(?:ed)?(?:\s+\d{4})?\b", " ", text)
    return " ".join(re.sub(r"[^\w\s]", " ", text).split())


def versions(text: str) -> set[str]:
    return set(
        re.findall(
            r"\b(live|acoustic|remix|instrumental|karaoke|demo|sped|slowed)\b", text.casefold()
        )
    )


def confidence(track: Track, record: dict[str, Any]) -> float:
    title = str(record.get("trackName") or record.get("name") or "")
    artist = str(record.get("artistName") or "")
    title_score = ratio(normalize(track.title), normalize(title)) / 100
    artist_score = ratio(normalize(track.artist), normalize(artist)) / 100
    if not track.title or not track.artist or title_score < 0.85 or artist_score < 0.80:
        return 0.0
    if versions(track.title) != versions(title):
        return 0.0
    try:
        duration = float(record.get("duration") or 0)
    except (TypeError, ValueError):
        return 0.0
    if not math.isfinite(duration) or duration < 0:
        return 0.0
    if track.duration and duration and abs(track.duration - duration) > 3:
        return 0.0
    score = title_score * 0.6 + artist_score * 0.4
    album = str(record.get("albumName") or "")
    if track.album and album:
        score = score * 0.95 + ratio(normalize(track.album), normalize(album)) / 100 * 0.05
    return score

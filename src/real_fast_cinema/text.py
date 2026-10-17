"""Text normalization shared by sources and matching."""

import re
import unicodedata

AD_MARKERS = frozenset({"audiodeskription", "horfassung"})
SIGN_MARKERS = frozenset({"gebardensprache"})
OV_MARKERS = frozenset(
    {
        "ov",
        "omu",
        "originalversion",
        "originalfassung",
        "original version",
        "englisch",
        "english",
    }
)
SUBTITLE_MARKERS = frozenset({"untertitel", "mit untertitel"})
KNOWN_MARKERS = AD_MARKERS | SIGN_MARKERS | OV_MARKERS | SUBTITLE_MARKERS

_PAREN_RE = re.compile(r"\s*\(([^()]*)\)")
_YEAR_RE = re.compile(r"(?:19|20)\d{2}")
_PUNCT_RE = re.compile(r"[^\w\s]")
_WS_RE = re.compile(r"\s+")
# Colon, pipe, hyphen, en dash, em dash, middle dot.
_SEPARATORS = "[:|\\-\u2013\u2014\u00b7]"


def fold(text: str) -> str:
    """Lowercases, strips diacritics and punctuation, collapses whitespace."""
    decomposed = unicodedata.normalize("NFKD", text.casefold())
    stripped = "".join(c for c in decomposed if not unicodedata.combining(c))
    return _WS_RE.sub(" ", _PUNCT_RE.sub(" ", stripped)).strip()


def words(text: str) -> list[str]:
    """Returns the folded words of ``text``."""
    return fold(text).split()


def split_markers(title: str) -> tuple[str, tuple[str, ...]]:
    """Removes known parenthesized markers and years from a title.

    Returns:
        The cleaned title and the folded marker contents in order.
    """
    markers: list[str] = []

    def _replace(match: re.Match[str]) -> str:
        content = fold(match.group(1))
        if content in KNOWN_MARKERS or _YEAR_RE.fullmatch(content):
            markers.append(content)
            return ""
        return match.group(0)

    cleaned = _PAREN_RE.sub(_replace, title)
    return _WS_RE.sub(" ", cleaned).strip(), tuple(markers)


def strip_topic_prefix(topic: str, title: str) -> str:
    """Removes a leading ``<topic>:`` (or ``-``, ``|`` ...) from the title."""
    topic = topic.strip()
    if not topic:
        return title
    pattern = re.compile(rf"^\s*{re.escape(topic)}\s*{_SEPARATORS}\s*", re.IGNORECASE)
    return pattern.sub("", title, count=1) or title


def display_title(topic: str, title: str) -> str:
    """Title without markers and without repeated topic prefix."""
    return strip_topic_prefix(topic, split_markers(title)[0])

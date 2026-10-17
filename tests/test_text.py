import pytest

from real_fast_cinema.text import display_title, fold, split_markers, words


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Déjà-vu (Audiodeskription)", "deja vu audiodeskription"),
        ("  Miss   Marple  ", "miss marple"),
        ("Straße", "strasse"),
        ("Gebärdensprache", "gebardensprache"),
        ("Tatort \u00b7 Unter Freunden", "tatort unter freunden"),
    ],
)
def test_fold(raw: str, expected: str) -> None:
    assert fold(raw) == expected


def test_words_splits_folded_text() -> None:
    assert words("Marple, Miss - Mord!") == ["marple", "miss", "mord"]


@pytest.mark.parametrize(
    ("title", "cleaned", "markers"),
    [
        ("Fackel (Audiodeskription)", "Fackel", ("audiodeskription",)),
        (
            "Die Erfindung des Rades (2025) (Gebärdensprache)",
            "Die Erfindung des Rades",
            ("2025", "gebardensprache"),
        ),
        ("Cash (2024)", "Cash", ("2024",)),
        ("Der Film (OV)", "Der Film", ("ov",)),
        ("Teil (1/3)", "Teil (1/3)", ()),
        ("Fackel", "Fackel", ()),
    ],
)
def test_split_markers(title: str, cleaned: str, markers: tuple[str, ...]) -> None:
    assert split_markers(title) == (cleaned, markers)


@pytest.mark.parametrize(
    ("topic", "title", "expected"),
    [
        ("Tatort", "Tatort: Unter Freunden", "Unter Freunden"),
        ("Tatort", "tatort - Fackel (Audiodeskription)", "Fackel"),
        ("Miss Marple", "Miss Marple \u2013 16 Uhr 50", "16 Uhr 50"),
        ("Tatort", "Tatort", "Tatort"),
        ("Tatort", "Tatortreiniger", "Tatortreiniger"),
        ("", "Fackel", "Fackel"),
    ],
)
def test_display_title(topic: str, title: str, expected: str) -> None:
    assert display_title(topic, title) == expected

from datetime import timedelta
from pathlib import Path

import pytest
from pydantic import ValidationError

from real_fast_cinema.config import (
    Defaults,
    DownloadOpts,
    Filters,
    GlobalConfig,
    Profile,
    parse_duration,
)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("90s", timedelta(seconds=90)),
        ("60m", timedelta(minutes=60)),
        ("6h", timedelta(hours=6)),
        (" 1d ", timedelta(days=1)),
        (120, timedelta(seconds=120)),
        (timedelta(hours=2), timedelta(hours=2)),
    ],
)
def test_parse_duration_accepts_units(value: object, expected: timedelta) -> None:
    assert parse_duration(value) == expected


@pytest.mark.parametrize("value", ["abc", "6x", "", "h6", True, None, 1.5])
def test_parse_duration_rejects_invalid(value: object) -> None:
    with pytest.raises(ValueError, match="invalid duration"):
        parse_duration(value)


def test_filters_defaults_exclude_accessibility_variants_and_trailers() -> None:
    filters = Filters()

    assert filters.audio_description is False
    assert filters.sign_language is False
    assert filters.trailer is False
    assert filters.subtitles == "any"
    assert filters.language == "any"
    assert filters.min_duration is None
    assert filters.exclude == []


def test_filters_accept_any_and_duration_strings() -> None:
    filters = Filters.model_validate(
        {"audio_description": "any", "min_duration": "60m", "language": "ov"}
    )

    assert filters.audio_description == "any"
    assert filters.min_duration == timedelta(hours=1)
    assert filters.language == "ov"


def test_profile_minimal_defaults() -> None:
    profile = Profile.model_validate(
        {"name": "krimis", "sources": ["mediathekviewweb"], "titles": "k.txt"}
    )

    assert profile.action == "info"
    assert profile.notify == "errors"
    assert profile.every is None
    assert profile.download is None
    assert profile.mail_to is None


@pytest.mark.parametrize("action", ["download", "both"])
def test_download_action_requires_download_section(action: str) -> None:
    with pytest.raises(ValidationError, match="requires a 'download' section"):
        Profile.model_validate(
            {"name": "p", "sources": ["s"], "titles": "t.txt", "action": action}
        )


@pytest.mark.parametrize("name", ["Krimis", "-x", "a b", ""])
def test_profile_name_must_be_slug(name: str) -> None:
    with pytest.raises(ValidationError):
        Profile.model_validate({"name": name, "sources": ["s"], "titles": "t.txt"})


def test_profile_requires_at_least_one_source() -> None:
    with pytest.raises(ValidationError):
        Profile.model_validate({"name": "p", "sources": [], "titles": "t.txt"})


def test_profile_rejects_unknown_keys() -> None:
    # Review focus 2: a typo must not be silently ignored.
    with pytest.raises(ValidationError, match="filter"):
        Profile.model_validate(
            {
                "name": "p",
                "sources": ["s"],
                "titles": "t.txt",
                "filter": {"min_duration": "60m"},
            }
        )


@pytest.mark.parametrize("target", ["/abs/path", "../outside", "a/../../b"])
def test_download_target_must_be_relative_without_parent(target: str) -> None:
    with pytest.raises(ValidationError, match="relative"):
        DownloadOpts.model_validate({"target": target})


def test_download_rename_rejects_unknown_placeholder() -> None:
    with pytest.raises(ValidationError, match="unknown placeholder"):
        DownloadOpts.model_validate({"target": "x", "rename": "{titel}.{ext}"})


def test_download_rename_requires_ext() -> None:
    with pytest.raises(ValidationError, match="ext"):
        DownloadOpts.model_validate({"target": "x", "rename": "{title}"})


def test_download_rename_accepts_date_format() -> None:
    opts = DownloadOpts.model_validate(
        {"target": "x", "rename": "{date:%Y-%m-%d} {title}.{ext}"}
    )

    assert opts.target == Path("x")


def test_global_config_reads_smtp_from_key() -> None:
    config = GlobalConfig.model_validate(
        {
            "data_dir": "/data",
            "downloads_root": "/media",
            "smtp": {"host": "smtp.example.org", "from": "bot@example.org"},
        }
    )

    assert config.smtp is not None
    assert config.smtp.from_ == "bot@example.org"
    assert config.smtp.port == 587
    assert config.smtp.starttls is True
    assert config.defaults.every == timedelta(hours=6)
    assert config.defaults.max_retries == 3


def test_defaults_every_must_be_positive() -> None:
    with pytest.raises(ValidationError, match="greater than zero"):
        Defaults.model_validate({"every": "0s"})


def test_profile_every_must_be_positive() -> None:
    with pytest.raises(ValidationError, match="greater than zero"):
        Profile.model_validate(
            {"name": "a", "sources": ["x"], "titles": "t.txt", "every": "0s"}
        )


@pytest.mark.parametrize("rename", ["{year:%Y}.{ext}", "{title:{ext}", "{0}.{ext}"])
def test_download_rename_rejects_unrenderable_template(rename: str) -> None:
    with pytest.raises(ValidationError, match="rename"):
        DownloadOpts.model_validate({"target": "x", "rename": rename})

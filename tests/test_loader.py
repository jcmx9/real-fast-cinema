from pathlib import Path

import pytest

from real_fast_cinema.exceptions import ConfigError
from real_fast_cinema.loader import (
    load_global,
    load_profiles,
    load_titles,
)


def test_load_global_reads_config(config_dir: Path) -> None:
    config = load_global(config_dir)

    assert config.mail_to == ["me@example.org"]
    assert config.smtp is not None
    assert config.data_dir.is_absolute()


def test_load_global_resolves_relative_paths_against_config_dir(
    config_dir: Path,
) -> None:
    (config_dir / "config.yaml").write_text(
        "data_dir: data\ndownloads_root: ../media\n", encoding="utf-8"
    )

    config = load_global(config_dir)

    assert config.data_dir == config_dir.resolve() / "data"
    assert config.downloads_root == config_dir.resolve() / "../media"


def test_load_global_missing_file(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="not found"):
        load_global(tmp_path)


@pytest.mark.parametrize(
    ("content", "message"),
    [
        ("data_dir: [unclosed", "config.yaml"),
        ("- a\n- b\n", "mapping"),
        ("data_dir: /data\n", "downloads_root"),
        ("data_dir: /d\ndownloads_root: /m\nunknown: 1\n", "unknown"),
    ],
)
def test_load_global_invalid(config_dir: Path, content: str, message: str) -> None:
    (config_dir / "config.yaml").write_text(content, encoding="utf-8")

    with pytest.raises(ConfigError, match=message):
        load_global(config_dir)


def test_load_titles_skips_comments_blanks_and_duplicates(config_dir: Path) -> None:
    assert load_titles(config_dir, "krimis.txt") == (
        "Miss Marple",
        "Tatort Unter Freunden",
    )


def test_load_titles_handles_bom_and_crlf(config_dir: Path) -> None:
    # Review focus 1: editors may write a BOM and Windows line endings.
    (config_dir / "titles" / "win.txt").write_bytes(
        "﻿Miss Marple\r\n# x\r\nDéjà-vu\r\n".encode()
    )

    assert load_titles(config_dir, "win.txt") == ("Miss Marple", "Déjà-vu")


def test_load_titles_rejects_path_traversal(config_dir: Path) -> None:
    with pytest.raises(ConfigError, match="inside"):
        load_titles(config_dir, "../config.yaml")


def test_load_titles_missing(config_dir: Path) -> None:
    with pytest.raises(ConfigError, match=r"nope\.txt"):
        load_titles(config_dir, "nope.txt")


def test_load_profiles_returns_valid_profiles(config_dir: Path) -> None:
    profiles, errors = load_profiles(config_dir)

    assert errors == []
    assert [p.profile.name for p in profiles] == ["krimis"]
    assert profiles[0].terms == ("Miss Marple", "Tatort Unter Freunden")
    assert profiles[0].path == config_dir / "profiles" / "krimis.yaml"


def test_load_profiles_collects_errors_and_keeps_valid_ones(config_dir: Path) -> None:
    profiles_dir = config_dir / "profiles"
    (profiles_dir / "broken.yaml").write_text("name: [", encoding="utf-8")
    (profiles_dir / "notitles.yml").write_text(
        "name: notitles\nsources: [s]\ntitles: missing.txt\n", encoding="utf-8"
    )
    (profiles_dir / "dupe.yaml").write_text(
        "name: krimis\nsources: [s]\ntitles: krimis.txt\n", encoding="utf-8"
    )

    profiles, errors = load_profiles(config_dir)

    assert [p.profile.name for p in profiles] == ["krimis"]
    assert len(errors) == 3
    assert any("broken.yaml" in e for e in errors)
    assert any("missing.txt" in e for e in errors)
    assert any("duplicate profile name 'krimis'" in e for e in errors)


def test_load_profiles_without_profiles_dir(tmp_path: Path) -> None:
    assert load_profiles(tmp_path) == ([], [])

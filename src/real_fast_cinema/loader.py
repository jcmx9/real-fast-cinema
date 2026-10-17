"""Loads configuration, profiles and title lists from a config directory."""

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from real_fast_cinema.config import GlobalConfig, Profile
from real_fast_cinema.exceptions import ConfigError

CONFIG_FILE = "config.yaml"
PROFILES_DIR = "profiles"
TITLES_DIR = "titles"


@dataclass(frozen=True)
class LoadedProfile:
    """A validated profile together with its resolved search terms."""

    profile: Profile
    terms: tuple[str, ...]
    path: Path


def _read_yaml(path: Path) -> dict[str, Any]:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8-sig"))
    except (OSError, yaml.YAMLError) as exc:
        raise ConfigError(f"{path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ConfigError(f"{path}: expected a mapping at top level")
    return data


def _describe(path: Path, exc: ValidationError) -> str:
    details = "; ".join(
        f"{'.'.join(str(p) for p in err['loc']) or '<root>'}: {err['msg']}"
        for err in exc.errors()
    )
    return f"{path}: {details}"


def load_global(config_dir: Path) -> GlobalConfig:
    """Loads ``config.yaml``; relative paths are resolved against ``config_dir``.

    Raises:
        ConfigError: If the file is missing or invalid.
    """
    path = config_dir / CONFIG_FILE
    if not path.is_file():
        raise ConfigError(f"configuration file not found: {path}")
    try:
        config = GlobalConfig.model_validate(_read_yaml(path))
    except ValidationError as exc:
        raise ConfigError(_describe(path, exc)) from exc
    base = config_dir.resolve()
    return config.model_copy(
        update={
            "data_dir": base / config.data_dir,
            "downloads_root": base / config.downloads_root,
        }
    )


def load_titles(config_dir: Path, name: str) -> tuple[str, ...]:
    """Reads a title list: one term per line, ``#`` comments, blanks ignored.

    Raises:
        ConfigError: If the file is outside ``titles/``, missing or unreadable.
    """
    titles_dir = (config_dir / TITLES_DIR).resolve()
    path = (titles_dir / name).resolve()
    if not path.is_relative_to(titles_dir):
        raise ConfigError(f"title list {name!r} must be inside {titles_dir}")
    try:
        text = path.read_text(encoding="utf-8-sig")
    except OSError as exc:
        raise ConfigError(f"title list unreadable: {path} ({exc.strerror})") from exc
    lines = (line.strip() for line in text.splitlines())
    return tuple(dict.fromkeys(t for t in lines if t and not t.startswith("#")))


def load_profile(config_dir: Path, path: Path) -> LoadedProfile:
    """Loads one profile file and its title list.

    Raises:
        ConfigError: If the profile or its title list is invalid.
    """
    try:
        profile = Profile.model_validate(_read_yaml(path))
    except ValidationError as exc:
        raise ConfigError(_describe(path, exc)) from exc
    terms = load_titles(config_dir, profile.titles)
    return LoadedProfile(profile=profile, terms=terms, path=path)


def load_profiles(config_dir: Path) -> tuple[list[LoadedProfile], list[str]]:
    """Loads all profiles; broken ones are reported instead of raising.

    Returns:
        The valid profiles and a list of error messages.
    """
    profiles_dir = config_dir / PROFILES_DIR
    files = sorted([*profiles_dir.glob("*.yaml"), *profiles_dir.glob("*.yml")])
    loaded: list[LoadedProfile] = []
    errors: list[str] = []
    seen: dict[str, Path] = {}
    for path in files:
        try:
            item = load_profile(config_dir, path)
        except ConfigError as exc:
            errors.append(str(exc))
            continue
        name = item.profile.name
        if name in seen:
            errors.append(
                f"{path}: duplicate profile name {name!r} (already in {seen[name]})"
            )
            continue
        seen[name] = path
        loaded.append(item)
    return loaded, errors

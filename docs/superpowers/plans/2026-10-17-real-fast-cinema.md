# real-fast-cinema Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A self-hosted service (`rf-cinema`) that regularly searches media libraries (first: MediathekViewWeb) for films from title lists defined per profile and either notifies by e-mail or downloads them in maximum quality.

**Architecture:** One Python package with small, focused modules: config/loader (Pydantic + YAML), text normalization, matching/dedup, source plugins behind a `Source` protocol, SQLite state store, downloader (httpx / ffmpeg), notifier plugins behind a `Notifier` protocol, a runner that executes one profile, a scheduler for daemon mode, and a typer CLI (`run`, `daemon`, `check`, `list-sources`). Shipped as a Docker image.

**Tech Stack:** Python ≥ 3.12, uv, hatchling, typer, pydantic v2, httpx, PyYAML, sqlite3, smtplib, ffmpeg (system), pytest (+cov, xdist), ruff, mypy strict, bump-my-version, Docker.

**Spec:** `docs/superpowers/specs/2026-10-16-real-fast-cinema-design.md`

## Global Constraints

- Package `real_fast_cinema`, distribution `real-fast-cinema`, CLI command `rf-cinema`, GitHub `jcmx9/real-fast-cinema`.
- Author identity `jcmx9` only. Never use any real name in code, docs, commits or metadata.
- `requires-python = ">=3.12"`; CI matrix 3.12, 3.13, 3.14; Docker image `python:3.13-slim`.
- CalVer `YY.M.MICRO`; start version `26.10.0.dev1`; single source of truth `src/real_fast_cinema/__init__.py`.
- Runtime deps exactly: `typer>=0.12`, `pydantic>=2.0`, `httpx>=0.27`, `pyyaml>=6.0` (`>=` pins, no upper bounds).
- `mypy --strict` on `src/`; ruff rules `E,F,W,I,N,UP,B,A,SIM,RUF`, line length 88; no non-ASCII confusables (en dash, middle dot) in string literals/comments — use `–` escapes where needed.
- Coverage ≥ 80 % total (enforced), `matching`, `store`, `runner` ≥ 95 %.
- No network in tests (except `@pytest.mark.live`, deselected by default).
- `subprocess.run([...], check=True)`, never `shell=True`.
- SMTP password only from env `RF_CINEMA_SMTP_PASSWORD`.
- Quality: always maximum (`url_video_hd` → `url_video` → `url_video_low`).
- Dedup: same film = equal normalized key **and** durations within `max(60 s, 2 %)`; once per profile.
- Code, docs, commit messages in English; Conventional Commits; no `Co-Authored-By` lines.
- `README.md` (German) and `README.en.md` (English) must be content-identical.
- Release workflow: GitHub release + GHCR image, **no PyPI publish**.
- Single focused test runs use `--no-cov` (the global coverage threshold would fail partial runs).

## Review Focus

1. Title list saved by an editor with UTF-8 BOM or CRLF line endings → terms must still match (test in Task 2).
2. Typo in a profile key (e.g. `filter:` instead of `filters:`) → must be a config error, not silently ignored (test in Task 2).
3. Film titles containing `/`, `:` or `..` (e.g. `Teil 1/2`) → valid file name inside the target folder, never outside (test in Task 6).
4. The same film matched by two terms of one list (e.g. `Tatort Fackel` and `Fackel`) → exactly one action (test in Task 8).
5. Malformed API entries (no video URL, `duration: null`, non-dict entry) → skipped or defaulted, never a crash of the run (test in Task 4).

## File Structure

```
src/real_fast_cinema/
  __init__.py          # __version__
  __main__.py          # python -m real_fast_cinema
  py.typed
  exceptions.py        # RfCinemaError, ConfigError, SourceError, DownloadError, NotifyError
  config.py            # Pydantic models + duration parsing
  loader.py            # config.yaml, profiles/*.yaml, titles/*.txt -> models
  models.py            # Hit, Failure, Report
  text.py              # fold(), words(), split_markers(), display_title()
  matching.py          # matches_term, passes_filters, select, dedup_key, group_hits, best_hit
  store.py             # SQLite state
  sources/__init__.py  # registry: available_sources(), get_source()
  sources/base.py      # Source protocol
  sources/mediathekviewweb.py
  download.py          # Downloader, render_filename, resolve_target, unique_path
  notifiers/__init__.py
  notifiers/base.py    # Notifier protocol
  notifiers/email.py   # EmailNotifier, build_message
  runner.py            # RunContext, run_profile, should_notify, open_context
  scheduler.py         # due_profiles, seconds_until_next, tick, run_daemon
  logsetup.py          # verbosity -> logging handlers
  cli.py               # typer app
tests/
  __init__.py
  conftest.py          # fixtures (config_dir, logging reset)
  fakes.py             # make_hit, FakeSource, FakeNotifier, FakeDownloader, FakeEvent, make_ctx, make_profile
  fixtures/mvw_tatort.json
  test_*.py
config.example/        # sample config, profiles, title list
Dockerfile, docker-compose.yml, .dockerignore
scripts/release.sh, docs/github-release.md, .github/...
```

---

### Task 1: Project scaffold with `--version`

**Files:**
- Create: `pyproject.toml`, `.gitignore`, `.pre-commit-config.yaml`, `LICENSE`
- Create: `src/real_fast_cinema/__init__.py`, `__main__.py`, `py.typed`, `exceptions.py`, `cli.py`
- Create: `tests/__init__.py`, `tests/conftest.py`, `tests/test_cli.py`

**Interfaces:**
- Produces: `real_fast_cinema.__version__: str`; `real_fast_cinema.cli.app: typer.Typer`; exceptions `RfCinemaError`, `ConfigError`, `SourceError`, `DownloadError`, `NotifyError` (all subclass `RfCinemaError`).

- [ ] **Step 1: Create `pyproject.toml`**

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "real-fast-cinema"
dynamic = ["version"]
description = "Searches media libraries for films from title lists and notifies or downloads."
readme = "README.md"
license = { text = "MIT" }
requires-python = ">=3.12"
authors = [{ name = "jcmx9" }]
keywords = ["mediathek", "mediathekviewweb", "download", "watchlist"]
classifiers = [
    "Development Status :: 3 - Alpha",
    "Programming Language :: Python :: 3",
    "License :: OSI Approved :: MIT License",
]
dependencies = [
    "typer>=0.12",
    "pydantic>=2.0",
    "httpx>=0.27",
    "pyyaml>=6.0",
]

[project.scripts]
rf-cinema = "real_fast_cinema.cli:app"

[dependency-groups]
dev = [
    "pytest>=8.0",
    "pytest-cov>=5.0",
    "pytest-xdist>=3.5",
    "ruff>=0.4",
    "mypy>=1.10",
    "bump-my-version>=1.1",
    "pre-commit>=3.7",
    "types-PyYAML>=6.0",
]

[project.urls]
Homepage = "https://github.com/jcmx9/real-fast-cinema"
Repository = "https://github.com/jcmx9/real-fast-cinema"
Issues = "https://github.com/jcmx9/real-fast-cinema/issues"

[tool.hatch.version]
path = "src/real_fast_cinema/__init__.py"

[tool.bumpversion]
current_version = "26.10.0.dev1"
commit = true
tag = true
tag_name = "v{new_version}"
tag_message = "Release {new_version}"
commit_message = "release: {new_version}"
parse = "(?P<year>\\d{2})\\.(?P<month>\\d{1,2})\\.(?P<micro>\\d+)(\\.dev(?P<dev>\\d+))?"
serialize = [
    "{year}.{month}.{micro}.dev{dev}",
    "{year}.{month}.{micro}",
]

[[tool.bumpversion.files]]
filename = "src/real_fast_cinema/__init__.py"
search = '__version__ = "{current_version}"'
replace = '__version__ = "{new_version}"'

[tool.ruff]
target-version = "py312"
line-length = 88

[tool.ruff.lint]
select = ["E", "F", "W", "I", "N", "UP", "B", "A", "SIM", "RUF"]

[tool.ruff.lint.flake8-bugbear]
extend-immutable-calls = ["pathlib.Path", "typer.Option", "typer.Argument"]

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "--cov=src/real_fast_cinema --cov-report=term-missing -n auto -m 'not live'"
markers = ["live: talks to real external services (run with -m live)"]

[tool.mypy]
python_version = "3.12"
strict = true
plugins = ["pydantic.mypy"]

[tool.coverage.run]
source = ["src/real_fast_cinema"]
branch = true

[tool.coverage.report]
fail_under = 80
show_missing = true
exclude_lines = [
    "pragma: no cover",
    "if TYPE_CHECKING:",
    "if __name__ == .__main__.:",
    "@(abc\\.)?abstractmethod",
    "^\\s*\\.\\.\\.$",
]
```

- [ ] **Step 2: Create `.gitignore`**

Use the `.gitignore` from `~/GitHub/CLAUDE.md` section 12 verbatim, keep `uv.lock` committed (application), and append:

```gitignore
# Local runtime data
/config/
/data/
/media/
```

- [ ] **Step 3: Create `.pre-commit-config.yaml`, `LICENSE`**

`.pre-commit-config.yaml`: copy section 11 of `~/GitHub/CLAUDE.md`. `LICENSE`: MIT text from section 8 with `Copyright (c) 2026 jcmx9`.

- [ ] **Step 4: Create package files**

`src/real_fast_cinema/__init__.py`:

```python
"""Searches media libraries for films from title lists."""

__version__ = "26.10.0.dev1"
```

`src/real_fast_cinema/__main__.py`:

```python
from real_fast_cinema.cli import app

app()
```

`src/real_fast_cinema/py.typed`: empty file.

`src/real_fast_cinema/exceptions.py`:

```python
"""Project-specific exceptions."""


class RfCinemaError(Exception):
    """Base class for all expected errors of rf-cinema."""


class ConfigError(RfCinemaError):
    """Invalid or missing configuration, profile or title list."""


class SourceError(RfCinemaError):
    """A source could not be queried."""


class DownloadError(RfCinemaError):
    """A download failed."""


class NotifyError(RfCinemaError):
    """A notification could not be delivered."""
```

`tests/__init__.py`: empty. `tests/conftest.py`:

```python
"""Shared pytest fixtures."""
```

- [ ] **Step 5: Write the failing CLI test** — `tests/test_cli.py`

```python
from typer.testing import CliRunner

from real_fast_cinema import __version__
from real_fast_cinema.cli import app

runner = CliRunner()


def test_version_flag_prints_version() -> None:
    result = runner.invoke(app, ["--version"])

    assert result.exit_code == 0
    assert result.output.strip() == f"rf-cinema {__version__}"


def test_no_arguments_shows_help_with_version() -> None:
    result = runner.invoke(app, [])

    assert "Usage" in result.output
    assert __version__ in result.output
```

- [ ] **Step 6: Run to verify it fails**

Run: `uv sync && uv run pytest tests/test_cli.py -v --no-cov`
Expected: FAIL / collection error — `real_fast_cinema.cli` has no `app`.

- [ ] **Step 7: Implement minimal `cli.py`**

```python
"""Command line interface."""

import typer

from real_fast_cinema import __version__

app = typer.Typer(
    name="rf-cinema",
    help=f"Searches media libraries for films from title lists (v{__version__})",
    no_args_is_help=True,
)


def version_callback(value: bool) -> None:
    if value:
        typer.echo(f"rf-cinema {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: bool = typer.Option(
        False,
        "--version",
        "-V",
        callback=version_callback,
        is_eager=True,
        help="Show version and exit.",
    ),
) -> None:
    """rf-cinema command line."""
```

- [ ] **Step 8: Run tests and checks**

Run: `uv run pytest && uv run ruff check src tests && uv run ruff format --check src tests && uv run mypy src`
Expected: 2 passed, no lint/type errors.

- [ ] **Step 9: Commit**

```bash
git add pyproject.toml uv.lock .gitignore .pre-commit-config.yaml LICENSE src tests
git commit -m "chore: scaffold project with rf-cinema --version"
```

---

### Task 2: Config models and loader

**Files:**
- Create: `src/real_fast_cinema/config.py`, `src/real_fast_cinema/loader.py`
- Modify: `tests/conftest.py` (add `config_dir` fixture)
- Test: `tests/test_config.py`, `tests/test_loader.py`

**Interfaces:**
- Consumes: `ConfigError` (Task 1).
- Produces:
  - `parse_duration(value: object) -> timedelta`
  - `Tristate = bool | Literal["any"]`, `Action = Literal["info","download","both"]`, `Notify = Literal["always","errors","never"]`
  - `SmtpConfig(host, port=587, starttls=True, user=None, from_)` (YAML key `from`)
  - `Defaults(every: timedelta = 6h, max_retries: int = 3)`
  - `GlobalConfig(data_dir: Path, downloads_root: Path, smtp: SmtpConfig | None, mail_to: list[str], defaults: Defaults)`
  - `Filters(min_duration: timedelta | None, audio_description: Tristate=False, sign_language: Tristate=False, trailer: Tristate=False, subtitles: Tristate="any", language: Literal["de","ov","any"]="any", exclude: list[str])`
  - `DownloadOpts(target: Path, rename: str = "{topic} - {title}.{ext}")`, `RENAME_PLACEHOLDERS`
  - `Profile(name, sources: list[str], titles: str, every: timedelta | None, filters, action="info", download: DownloadOpts | None, notify="errors", mail_to: list[str] | None)`
  - `loader.LoadedProfile(profile: Profile, terms: tuple[str, ...], path: Path)` (frozen dataclass)
  - `load_global(config_dir: Path) -> GlobalConfig` (relative paths resolved against `config_dir`)
  - `load_titles(config_dir: Path, name: str) -> tuple[str, ...]`
  - `load_profile(config_dir: Path, path: Path) -> LoadedProfile`
  - `load_profiles(config_dir: Path) -> tuple[list[LoadedProfile], list[str]]` (valid profiles, error messages)
  - Fixture `config_dir` (tmp config with `config.yaml`, `profiles/krimis.yaml`, `titles/krimis.txt`).

- [ ] **Step 1: Add the `config_dir` fixture** — `tests/conftest.py`

```python
"""Shared pytest fixtures."""

from pathlib import Path
from textwrap import dedent

import pytest


@pytest.fixture
def config_dir(tmp_path: Path) -> Path:
    directory = tmp_path / "config"
    (directory / "profiles").mkdir(parents=True)
    (directory / "titles").mkdir()
    (directory / "config.yaml").write_text(
        dedent(
            f"""\
            data_dir: {tmp_path / "data"}
            downloads_root: {tmp_path / "media"}
            smtp:
              host: smtp.example.org
              port: 587
              user: bot@example.org
              from: bot@example.org
            mail_to: [me@example.org]
            """
        ),
        encoding="utf-8",
    )
    (directory / "titles" / "krimis.txt").write_text(
        "# Krimis\nMiss Marple\n\nTatort Unter Freunden\nMiss Marple\n",
        encoding="utf-8",
    )
    (directory / "profiles" / "krimis.yaml").write_text(
        dedent(
            """\
            name: krimis
            sources: [mediathekviewweb]
            titles: krimis.txt
            action: info
            """
        ),
        encoding="utf-8",
    )
    return directory
```

- [ ] **Step 2: Write failing config tests** — `tests/test_config.py`

```python
from datetime import timedelta
from pathlib import Path

import pytest
from pydantic import ValidationError

from real_fast_cinema.config import (
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
```

- [ ] **Step 3: Run to verify failure**

Run: `uv run pytest tests/test_config.py -v --no-cov`
Expected: FAIL — `ModuleNotFoundError: real_fast_cinema.config`.

- [ ] **Step 4: Implement `config.py`**

```python
"""Pydantic models for global configuration and profiles."""

import re
import string
from datetime import timedelta
from pathlib import Path
from typing import Annotated, Literal, Self

from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

_DURATION_RE = re.compile(r"^\s*(\d+)\s*([smhd])\s*$")
_UNIT_SECONDS = {"s": 1, "m": 60, "h": 3600, "d": 86400}

RENAME_PLACEHOLDERS = frozenset({"topic", "title", "channel", "year", "date", "ext"})


def parse_duration(value: object) -> timedelta:
    """Parses durations like ``90s``, ``60m``, ``6h``, ``1d`` or seconds as int.

    Raises:
        ValueError: If the value is not a valid duration.
    """
    if isinstance(value, timedelta):
        return value
    if isinstance(value, int) and not isinstance(value, bool):
        return timedelta(seconds=value)
    if isinstance(value, str):
        match = _DURATION_RE.match(value)
        if match:
            amount, unit = match.groups()
            return timedelta(seconds=int(amount) * _UNIT_SECONDS[unit])
    msg = f"invalid duration: {value!r} (expected e.g. '90s', '60m', '6h', '1d')"
    raise ValueError(msg)


Duration = Annotated[timedelta, BeforeValidator(parse_duration)]
Tristate = bool | Literal["any"]
Action = Literal["info", "download", "both"]
Notify = Literal["always", "errors", "never"]
Language = Literal["de", "ov", "any"]


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True)


class SmtpConfig(_Model):
    """SMTP connection settings (password comes from the environment)."""

    host: str
    port: int = 587
    starttls: bool = True
    user: str | None = None
    from_: str = Field(alias="from")


class Defaults(_Model):
    """Defaults applied to all profiles."""

    every: Duration = timedelta(hours=6)
    max_retries: int = Field(default=3, ge=1)


class GlobalConfig(_Model):
    """Content of ``config.yaml``."""

    data_dir: Path
    downloads_root: Path
    smtp: SmtpConfig | None = None
    mail_to: list[str] = Field(default_factory=list)
    defaults: Defaults = Field(default_factory=Defaults)


class Filters(_Model):
    """Per-profile hit filters."""

    min_duration: Duration | None = None
    audio_description: Tristate = False
    sign_language: Tristate = False
    trailer: Tristate = False
    subtitles: Tristate = "any"
    language: Language = "any"
    exclude: list[str] = Field(default_factory=list)


class DownloadOpts(_Model):
    """Download target and file name template."""

    target: Path
    rename: str = "{topic} - {title}.{ext}"

    @field_validator("target")
    @classmethod
    def _target_is_relative(cls, value: Path) -> Path:
        if value.is_absolute() or ".." in value.parts:
            msg = "target must be relative to downloads_root and must not contain '..'"
            raise ValueError(msg)
        return value

    @field_validator("rename")
    @classmethod
    def _rename_placeholders(cls, value: str) -> str:
        fields = {
            field
            for _, field, _, _ in string.Formatter().parse(value)
            if field is not None
        }
        unknown = fields - RENAME_PLACEHOLDERS
        if unknown:
            allowed = ", ".join(sorted(RENAME_PLACEHOLDERS))
            msg = f"unknown placeholder(s) {sorted(unknown)} (allowed: {allowed})"
            raise ValueError(msg)
        if "ext" not in fields:
            msg = "rename template must contain {ext}"
            raise ValueError(msg)
        return value


class Profile(_Model):
    """One search profile (one YAML file in ``profiles/``)."""

    name: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]*$")
    sources: list[str] = Field(min_length=1)
    titles: str
    every: Duration | None = None
    filters: Filters = Field(default_factory=Filters)
    action: Action = "info"
    download: DownloadOpts | None = None
    notify: Notify = "errors"
    mail_to: list[str] | None = None

    @model_validator(mode="after")
    def _download_section_present(self) -> Self:
        if self.action in ("download", "both") and self.download is None:
            msg = f"action {self.action!r} requires a 'download' section"
            raise ValueError(msg)
        return self
```

(If any line exceeds 88 chars after `ruff format`, split the string literal.)

- [ ] **Step 5: Run config tests**

Run: `uv run pytest tests/test_config.py -v --no-cov`
Expected: all PASS.

- [ ] **Step 6: Write failing loader tests** — `tests/test_loader.py`

```python
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
    with pytest.raises(ConfigError, match="nope.txt"):
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
```

Note: files are processed in sorted order, so `dupe.yaml` is accepted as `krimis` and `krimis.yaml` gets the duplicate error. The assertions hold either way.

- [ ] **Step 7: Run to verify failure**

Run: `uv run pytest tests/test_loader.py -v --no-cov`
Expected: FAIL — `ModuleNotFoundError: real_fast_cinema.loader`.

- [ ] **Step 8: Implement `loader.py`**

```python
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
```

- [ ] **Step 9: Run tests and checks**

Run: `uv run pytest && uv run ruff check --fix src tests && uv run ruff format src tests && uv run mypy src`
Expected: all PASS, no errors.

- [ ] **Step 10: Commit**

```bash
git add src/real_fast_cinema/config.py src/real_fast_cinema/loader.py tests
git commit -m "feat(config): add config models and loader for profiles and title lists"
```

---

### Task 3: Hit model, text normalization and matching

**Files:**
- Create: `src/real_fast_cinema/models.py`, `src/real_fast_cinema/text.py`, `src/real_fast_cinema/matching.py`
- Create: `tests/fakes.py` (test helpers, extended in later tasks)
- Test: `tests/test_text.py`, `tests/test_matching.py`

**Interfaces:**
- Consumes: `Filters`, `Tristate` (Task 2).
- Produces:
  - `models.Hit` (frozen dataclass): `source: str, source_id: str, channel: str, topic: str, title: str, description: str, duration: int, published: datetime, video_url: str, is_hls: bool, is_hd: bool, page_url: str, subtitle_url: str | None, audio_description: bool = False, sign_language: bool = False, trailer: bool = False, language: Literal["de","ov"] = "de", year: int | None = None`
  - `models.Failure(hit: Hit, error: str, attempts: int, final: bool)`
  - `models.Report(profile: str, found, planned, downloaded: list[tuple[Hit, Path]], failed: list[Failure], errors: list[str])` with `summary() -> str`
  - `text.fold(text) -> str`, `text.words(text) -> list[str]`, `text.split_markers(title) -> tuple[str, tuple[str, ...]]`, `text.strip_topic_prefix(topic, title) -> str`, `text.display_title(topic, title) -> str`; constants `AD_MARKERS`, `SIGN_MARKERS`, `OV_MARKERS`, `SUBTITLE_MARKERS`, `KNOWN_MARKERS`
  - `matching.matches_term(hit, term) -> bool`, `passes_filters(hit, filters) -> bool`, `select(hit, term, filters) -> bool`, `dedup_key(hit) -> str`, `durations_close(a: int, b: int) -> bool`, `same_film(a, b) -> bool`, `group_hits(hits) -> list[list[Hit]]`, `best_hit(group) -> Hit`
  - `tests.fakes.make_hit(**overrides) -> Hit`

- [ ] **Step 1: Create `models.py`**

```python
"""Domain models shared by all components."""

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Literal

Language = Literal["de", "ov"]


@dataclass(frozen=True, slots=True)
class Hit:
    """A normalized search result of any source."""

    source: str
    source_id: str
    channel: str
    topic: str
    title: str
    description: str
    duration: int
    published: datetime
    video_url: str
    is_hls: bool
    is_hd: bool
    page_url: str
    subtitle_url: str | None
    audio_description: bool = False
    sign_language: bool = False
    trailer: bool = False
    language: Language = "de"
    year: int | None = None


@dataclass(frozen=True, slots=True)
class Failure:
    """A failed download attempt."""

    hit: Hit
    error: str
    attempts: int
    final: bool


@dataclass(slots=True)
class Report:
    """Outcome of one profile run."""

    profile: str
    found: list[Hit] = field(default_factory=list)
    planned: list[Hit] = field(default_factory=list)
    downloaded: list[tuple[Hit, Path]] = field(default_factory=list)
    failed: list[Failure] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def summary(self) -> str:
        """Returns a one-line summary such as ``2 found, 0 downloaded, 0 failed``."""
        text = (
            f"{len(self.found)} found, {len(self.downloaded)} downloaded, "
            f"{len(self.failed)} failed"
        )
        if self.errors:
            text += f", {len(self.errors)} source errors"
        return text
```

- [ ] **Step 2: Create `tests/fakes.py`**

```python
"""Test helpers (fakes and factories)."""

from datetime import UTC, datetime
from typing import Any

from real_fast_cinema.models import Hit


def make_hit(**overrides: Any) -> Hit:
    values: dict[str, Any] = {
        "source": "fake",
        "source_id": "1",
        "channel": "ARD",
        "topic": "Tatort",
        "title": "Fackel",
        "description": "",
        "duration": 5313,
        "published": datetime(2026, 10, 1, 20, 15, tzinfo=UTC),
        "video_url": "https://cdn.example.org/fackel.mp4",
        "is_hls": False,
        "is_hd": True,
        "page_url": "https://www.example.org/fackel",
        "subtitle_url": None,
    }
    values.update(overrides)
    return Hit(**values)
```

- [ ] **Step 3: Write failing text tests** — `tests/test_text.py`

```python
import pytest

from real_fast_cinema.text import display_title, fold, split_markers, words


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Déjà-vu (Audiodeskription)", "deja vu audiodeskription"),
        ("  Miss   Marple  ", "miss marple"),
        ("Straße", "strasse"),
        ("Gebärdensprache", "gebardensprache"),
        ("Tatort · Unter Freunden", "tatort unter freunden"),
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
        ("Miss Marple", "Miss Marple – 16 Uhr 50", "16 Uhr 50"),
        ("Tatort", "Tatort", "Tatort"),
        ("Tatort", "Tatortreiniger", "Tatortreiniger"),
        ("", "Fackel", "Fackel"),
    ],
)
def test_display_title(topic: str, title: str, expected: str) -> None:
    assert display_title(topic, title) == expected
```

- [ ] **Step 4: Run to verify failure**

Run: `uv run pytest tests/test_text.py -v --no-cov`
Expected: FAIL — `ModuleNotFoundError: real_fast_cinema.text`.

- [ ] **Step 5: Implement `text.py`**

```python
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
_SEPARATORS = "[:|\\-–—·]"


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
```

- [ ] **Step 6: Run text tests**

Run: `uv run pytest tests/test_text.py -v --no-cov`
Expected: all PASS.

- [ ] **Step 7: Write failing matching tests** — `tests/test_matching.py`

```python
from datetime import UTC, datetime
from typing import Any

import pytest

from real_fast_cinema.config import Filters
from real_fast_cinema.matching import (
    best_hit,
    dedup_key,
    durations_close,
    group_hits,
    matches_term,
    passes_filters,
    same_film,
    select,
)
from tests.fakes import make_hit


@pytest.mark.parametrize(
    ("term", "topic", "title", "expected"),
    [
        ("Miss Marple", "Miss Marple", "16 Uhr 50 ab Paddington", True),
        ("miss marple", "Krimi", "Marple, Miss - Mord im Pfarrhaus", True),
        ("Miss Marple", "Krimi", "Miss Marples Rache", False),
        ("Deja vu", "Tatort", "Déjà-vu", True),
        ("Tatort Unter Freunden", "Tatort", "Tatort: Unter Freunden", True),
        ("Tatort Fackel", "Polizeiruf 110", "Fackel", False),
        ("", "Tatort", "Fackel", False),
    ],
)
def test_matches_term_requires_all_words(
    term: str, topic: str, title: str, expected: bool
) -> None:
    assert matches_term(make_hit(topic=topic, title=title), term) is expected


@pytest.mark.parametrize(
    ("hit_overrides", "filters", "expected"),
    [
        ({}, {}, True),
        ({"duration": 37}, {"min_duration": "60m"}, False),
        ({"duration": 3600}, {"min_duration": "60m"}, True),
        ({"audio_description": True}, {}, False),
        ({"audio_description": True}, {"audio_description": True}, True),
        ({}, {"audio_description": True}, False),
        ({"audio_description": True}, {"audio_description": "any"}, True),
        ({"sign_language": True}, {}, False),
        ({"trailer": True}, {}, False),
        ({"trailer": True}, {"trailer": "any"}, True),
        ({}, {"subtitles": True}, False),
        ({"subtitle_url": "https://x/s.vtt"}, {"subtitles": True}, True),
        ({"subtitle_url": "https://x/s.vtt"}, {"subtitles": False}, False),
        ({"language": "ov"}, {"language": "de"}, False),
        ({"language": "ov"}, {"language": "ov"}, True),
        ({"language": "ov"}, {}, True),
        ({"title": "Trailer: Fackel"}, {"exclude": ["Trailer"]}, False),
        ({"title": "Fackel - die Doku"}, {"exclude": ["die Doku"]}, False),
        ({"title": "Die Fackel"}, {"exclude": ["die Doku"]}, True),
        ({}, {"exclude": ["", "  "]}, True),
    ],
)
def test_passes_filters(
    hit_overrides: dict[str, Any], filters: dict[str, Any], expected: bool
) -> None:
    hit = make_hit(**hit_overrides)

    assert passes_filters(hit, Filters.model_validate(filters)) is expected


def test_select_combines_match_and_filters() -> None:
    hit = make_hit(title="Fackel (Audiodeskription)", audio_description=True)

    assert select(make_hit(), "Tatort Fackel", Filters()) is True
    assert select(hit, "Tatort Fackel", Filters()) is False
    assert select(make_hit(), "Polizeiruf", Filters()) is False


@pytest.mark.parametrize(
    ("topic", "title", "key"),
    [
        ("Tatort", "Tatort: Unter Freunden", "tatort|unter freunden"),
        ("Tatort", "Unter Freunden", "tatort|unter freunden"),
        ("Tatort", "Fackel (Audiodeskription)", "tatort|fackel"),
        ("Tatort", "Trailer: Fackel", "tatort|trailer fackel"),
        ("Tatort", "Cash (2024)", "tatort|cash"),
    ],
)
def test_dedup_key(topic: str, title: str, key: str) -> None:
    assert dedup_key(make_hit(topic=topic, title=title)) == key


@pytest.mark.parametrize(
    ("a", "b", "expected"),
    [
        (5170, 5170, True),
        (5170, 5229, True),
        (5170, 5300, False),
        (6000, 6110, True),
        (6000, 6130, False),
        (30, 85, True),
    ],
)
def test_durations_close(a: int, b: int, expected: bool) -> None:
    assert durations_close(a, b) is expected


def test_same_film_needs_key_and_duration() -> None:
    ndr = make_hit(title="Unter Freunden", duration=5170)
    orf = make_hit(title="Tatort: Unter Freunden", duration=5170, channel="ORF")
    short = make_hit(title="Unter Freunden", duration=600)

    assert same_film(ndr, orf) is True
    assert same_film(ndr, short) is False
    assert same_film(ndr, make_hit(title="Fackel", duration=5170)) is False


def test_group_hits_and_best_hit_prefer_mp4_hd_plain_newest() -> None:
    ndr = make_hit(source_id="ndr", title="Unter Freunden", duration=5170)
    orf = make_hit(
        source_id="orf",
        title="Tatort: Unter Freunden",
        duration=5170,
        is_hls=True,
        video_url="https://orf.example/chunklist.m3u8",
    )
    ad = make_hit(
        source_id="ad",
        title="Unter Freunden (Audiodeskription)",
        duration=5170,
        audio_description=True,
        published=datetime(2026, 10, 9, tzinfo=UTC),
    )
    low = make_hit(source_id="low", title="Unter Freunden", duration=5170, is_hd=False)
    other = make_hit(source_id="fackel", title="Fackel")

    groups = group_hits([orf, ad, low, ndr, other])

    assert [[h.source_id for h in g] for g in groups] == [
        ["orf", "ad", "low", "ndr"],
        ["fackel"],
    ]
    assert best_hit(groups[0]).source_id == "ndr"
    assert best_hit(groups[1]).source_id == "fackel"


def test_best_hit_newest_wins_on_tie() -> None:
    old = make_hit(source_id="old", published=datetime(2026, 1, 1, tzinfo=UTC))
    new = make_hit(source_id="new", published=datetime(2026, 9, 1, tzinfo=UTC))

    assert best_hit([old, new]).source_id == "new"
```

- [ ] **Step 8: Run to verify failure**

Run: `uv run pytest tests/test_matching.py -v --no-cov`
Expected: FAIL — `ModuleNotFoundError: real_fast_cinema.matching`.

- [ ] **Step 9: Implement `matching.py`**

```python
"""Matching of hits against search terms, filters and deduplication."""

from collections.abc import Iterable, Sequence
from datetime import datetime

from real_fast_cinema.config import Filters, Tristate
from real_fast_cinema.models import Hit
from real_fast_cinema.text import display_title, fold, words

MIN_DURATION_TOLERANCE = 60
RELATIVE_DURATION_TOLERANCE = 0.02


def _haystack(hit: Hit) -> set[str]:
    return set(words(f"{hit.topic} {hit.title}"))


def _contains_all(haystack: set[str], phrase: str) -> bool:
    needed = words(phrase)
    return bool(needed) and set(needed) <= haystack


def matches_term(hit: Hit, term: str) -> bool:
    """True if every word of ``term`` occurs in topic and title of ``hit``."""
    return _contains_all(_haystack(hit), term)


def _tristate_ok(value: bool, wanted: Tristate) -> bool:
    return wanted == "any" or value == wanted


def passes_filters(hit: Hit, filters: Filters) -> bool:
    """True if ``hit`` satisfies all profile filters."""
    if (
        filters.min_duration is not None
        and hit.duration < filters.min_duration.total_seconds()
    ):
        return False
    checks = (
        (hit.audio_description, filters.audio_description),
        (hit.sign_language, filters.sign_language),
        (hit.trailer, filters.trailer),
        (hit.subtitle_url is not None, filters.subtitles),
    )
    if not all(_tristate_ok(value, wanted) for value, wanted in checks):
        return False
    if filters.language != "any" and hit.language != filters.language:
        return False
    haystack = _haystack(hit)
    return not any(_contains_all(haystack, entry) for entry in filters.exclude)


def select(hit: Hit, term: str, filters: Filters) -> bool:
    """True if ``hit`` matches ``term`` and passes ``filters``."""
    return matches_term(hit, term) and passes_filters(hit, filters)


def dedup_key(hit: Hit) -> str:
    """Normalized ``topic|title`` key used to recognize the same film."""
    return f"{fold(hit.topic)}|{fold(display_title(hit.topic, hit.title))}"


def durations_close(a: int, b: int) -> bool:
    """True if durations differ by at most ``max(60 s, 2 %)``."""
    tolerance = max(MIN_DURATION_TOLERANCE, RELATIVE_DURATION_TOLERANCE * max(a, b))
    return abs(a - b) <= tolerance


def same_film(a: Hit, b: Hit) -> bool:
    """True if both hits describe the same film."""
    return dedup_key(a) == dedup_key(b) and durations_close(a.duration, b.duration)


def group_hits(hits: Iterable[Hit]) -> list[list[Hit]]:
    """Groups hits of the same film, keeping first-seen order."""
    groups: list[list[Hit]] = []
    for hit in hits:
        for group in groups:
            if same_film(group[0], hit):
                group.append(hit)
                break
        else:
            groups.append([hit])
    return groups


def _rank(hit: Hit) -> tuple[bool, bool, bool, bool, datetime]:
    return (
        not hit.is_hls,
        hit.is_hd,
        not hit.audio_description,
        not hit.sign_language,
        hit.published,
    )


def best_hit(group: Sequence[Hit]) -> Hit:
    """Best hit of a group: MP4 before HLS, HD, plain version, newest."""
    return max(group, key=_rank)
```

- [ ] **Step 10: Run tests and checks**

Run: `uv run pytest && uv run ruff check --fix src tests && uv run ruff format src tests && uv run mypy src`
Expected: all PASS.

- [ ] **Step 11: Commit**

```bash
git add src/real_fast_cinema/models.py src/real_fast_cinema/text.py src/real_fast_cinema/matching.py tests
git commit -m "feat(matching): add hit model, text normalization, filters and dedup"
```

---

### Task 4: Source protocol, registry and MediathekViewWeb plugin

**Files:**
- Create: `src/real_fast_cinema/sources/__init__.py`, `sources/base.py`, `sources/mediathekviewweb.py`
- Create: `tests/fixtures/mvw_tatort.json`
- Test: `tests/test_source_mvw.py`, `tests/test_sources_registry.py`

**Interfaces:**
- Consumes: `Hit` (Task 3), `fold`, `split_markers`, `AD_MARKERS`, `SIGN_MARKERS`, `OV_MARKERS` (Task 3), `SourceError`, `ConfigError` (Task 1).
- Produces:
  - `sources.base.Source` protocol: `name: str`, `search(term: str) -> list[Hit]`, `close() -> None`
  - `sources.available_sources() -> list[str]`, `sources.get_source(name: str) -> Source` (raises `ConfigError` for unknown names)
  - `sources.mediathekviewweb.MediathekViewWeb(client: httpx.Client | None = None, *, backoff: float = 1.0, sleep: Callable[[float], None] = time.sleep)`; constants `NAME = "mediathekviewweb"`, `API_URL`, `PAGE_SIZE = 50`, `MAX_RESULTS = 500`, `ATTEMPTS = 3`
  - `sources.mediathekviewweb.to_hit(entry: dict[str, Any]) -> Hit | None`

- [ ] **Step 1: Create the recorded fixture** — `tests/fixtures/mvw_tatort.json`

Shape and values taken from a real API response (2026-10-16), reduced to the interesting variants:

```json
{
  "err": null,
  "result": {
    "queryInfo": {"totalResults": 10, "resultCount": 10},
    "results": [
      {"id": "a1", "channel": "ARD", "topic": "Tatort", "title": "Trailer: Fackel", "description": "", "timestamp": 1791900000, "duration": 37, "url_website": "https://www.ardmediathek.de/a1", "url_video": "https://cdn.ard.example/a1.mp4", "url_video_low": "", "url_video_hd": "https://cdn.ard.example/a1_hd.mp4", "url_subtitle": "https://cdn.ard.example/a1.vtt"},
      {"id": "a2", "channel": "ARD", "topic": "Tatort", "title": "Fackel (Audiodeskription)", "description": "", "timestamp": 1791900000, "duration": 5313, "url_website": "https://www.ardmediathek.de/a2", "url_video": "https://cdn.ard.example/a2.mp4", "url_video_low": "", "url_video_hd": "https://cdn.ard.example/a2_hd.mp4", "url_subtitle": "https://cdn.ard.example/a2.vtt"},
      {"id": "a3", "channel": "ARD", "topic": "Tatort", "title": "Fackel (Gebärdensprache)", "description": "", "timestamp": 1791900000, "duration": 5313, "url_website": "https://www.ardmediathek.de/a3", "url_video": "https://cdn.ard.example/a3.mp4", "url_video_low": "", "url_video_hd": "https://cdn.ard.example/a3_hd.mp4", "url_subtitle": ""},
      {"id": "a4", "channel": "ARD", "topic": "Tatort", "title": "Fackel", "description": "Ein Fall.", "timestamp": 1791900000, "duration": 5313, "url_website": "https://www.ardmediathek.de/a4", "url_video": "https://cdn.ard.example/a4.mp4", "url_video_low": "https://cdn.ard.example/a4_low.mp4", "url_video_hd": "https://cdn.ard.example/a4_hd.mp4", "url_subtitle": "https://cdn.ard.example/a4.vtt"},
      {"id": "n1", "channel": "NDR", "topic": "Tatort", "title": "Unter Freunden", "description": "", "timestamp": 1791300000, "duration": 5170, "url_website": "https://www.ndr.example/n1", "url_video": "https://cdn.ndr.example/n1.mp4", "url_video_low": "", "url_video_hd": "https://cdn.ndr.example/n1.1080.mp4", "url_subtitle": ""},
      {"id": "o1", "channel": "ORF", "topic": "Tatort", "title": "Tatort: Unter Freunden", "description": "", "timestamp": 1791400000, "duration": 5170, "url_website": "https://on.orf.example/o1", "url_video": "https://apasf.example/o1/playlist.m3u8", "url_video_low": "", "url_video_hd": "https://apasf.example/o1/chunklist_b6100000.m3u8", "url_subtitle": ""},
      {"id": "w1", "channel": "WDR", "topic": "Tatort", "title": "Cash (2024)", "description": "", "timestamp": 1791000000, "duration": 5338, "url_website": "https://www.wdr.example/w1", "url_video": "https://cdn.wdr.example/w1.mp4", "url_video_low": "", "url_video_hd": "", "url_subtitle": ""},
      {"id": "v1", "channel": "ARTE.DE", "topic": "Kino", "title": "Der Film (OV)", "description": "", "timestamp": 1791000000, "duration": 6000, "url_website": "https://www.arte.example/v1", "url_video": "https://cdn.arte.example/v1.mp4", "url_video_low": "", "url_video_hd": "", "url_subtitle": ""},
      {"id": "x1", "channel": "ARD", "topic": "Tatort", "title": "Kein Video", "description": "", "timestamp": 1791000000, "duration": 5000, "url_website": "", "url_video": "", "url_video_low": "", "url_video_hd": "", "url_subtitle": ""},
      {"id": "x2", "channel": "ARD", "topic": "Tatort", "title": "Ohne Dauer", "description": null, "timestamp": 1791000000, "duration": null, "url_website": null, "url_video": "https://cdn.ard.example/x2.mp4", "url_video_low": null, "url_video_hd": null, "url_subtitle": null}
    ]
  }
}
```

- [ ] **Step 2: Write failing source tests** — `tests/test_source_mvw.py`

```python
import json
from pathlib import Path
from typing import Any

import httpx
import pytest

from real_fast_cinema.exceptions import SourceError
from real_fast_cinema.sources.mediathekviewweb import (
    API_URL,
    MAX_RESULTS,
    PAGE_SIZE,
    MediathekViewWeb,
    to_hit,
)

FIXTURE = Path(__file__).parent / "fixtures" / "mvw_tatort.json"


def _fixture() -> dict[str, Any]:
    data: dict[str, Any] = json.loads(FIXTURE.read_text(encoding="utf-8"))
    return data


def _entries() -> dict[str, dict[str, Any]]:
    return {e["id"]: e for e in _fixture()["result"]["results"]}


def _source(handler: Any, sleeps: list[float] | None = None) -> MediathekViewWeb:
    client = httpx.Client(transport=httpx.MockTransport(handler))
    recorder = sleeps if sleeps is not None else []
    return MediathekViewWeb(client=client, sleep=recorder.append)


def test_to_hit_maps_fields_and_prefers_hd() -> None:
    hit = to_hit(_entries()["a4"])

    assert hit is not None
    assert hit.source == "mediathekviewweb"
    assert hit.source_id == "a4"
    assert (hit.channel, hit.topic, hit.title) == ("ARD", "Tatort", "Fackel")
    assert hit.duration == 5313
    assert hit.published.timestamp() == 1791900000
    assert hit.video_url == "https://cdn.ard.example/a4_hd.mp4"
    assert hit.is_hd is True
    assert hit.is_hls is False
    assert hit.page_url == "https://www.ardmediathek.de/a4"
    assert hit.subtitle_url == "https://cdn.ard.example/a4.vtt"
    assert hit.description == "Ein Fall."
    assert (hit.audio_description, hit.sign_language, hit.trailer) == (
        False,
        False,
        False,
    )
    assert hit.language == "de"
    assert hit.year is None


@pytest.mark.parametrize(
    ("entry_id", "attribute", "expected"),
    [
        ("a1", "trailer", True),
        ("a2", "audio_description", True),
        ("a3", "sign_language", True),
        ("a3", "subtitle_url", None),
        ("o1", "is_hls", True),
        ("w1", "year", 2024),
        ("w1", "is_hd", False),
        ("w1", "video_url", "https://cdn.wdr.example/w1.mp4"),
        ("v1", "language", "ov"),
    ],
)
def test_to_hit_derives_features(entry_id: str, attribute: str, expected: Any) -> None:
    hit = to_hit(_entries()[entry_id])

    assert hit is not None
    assert getattr(hit, attribute) == expected


def test_to_hit_skips_entries_without_video() -> None:
    # Review focus 5: malformed entries must not crash the run.
    assert to_hit(_entries()["x1"]) is None


def test_to_hit_defaults_null_fields() -> None:
    hit = to_hit(_entries()["x2"])

    assert hit is not None
    assert hit.duration == 0
    assert hit.page_url == ""
    assert hit.description == ""
    assert hit.subtitle_url is None


def test_to_hit_skips_unparseable_numbers() -> None:
    entry = dict(_entries()["a4"], duration="1:28:00")

    assert to_hit(entry) is None


def test_search_posts_query_and_returns_hits() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=_fixture())

    hits = _source(handler).search("Tatort Fackel")

    assert len(hits) == 9
    assert len(requests) == 1
    request = requests[0]
    assert str(request.url) == API_URL
    assert request.headers["Content-Type"] == "text/plain"
    body = json.loads(request.content)
    assert body["queries"] == [{"fields": ["title", "topic"], "query": "Tatort Fackel"}]
    assert body["offset"] == 0
    assert body["size"] == PAGE_SIZE
    assert body["future"] is False


def _paged_handler(total: int, calls: list[int]) -> Any:
    def handler(request: httpx.Request) -> httpx.Response:
        offset = json.loads(request.content)["offset"]
        calls.append(offset)
        count = max(0, min(PAGE_SIZE, total - offset))
        entries = [
            {
                "id": str(i),
                "title": f"T{i}",
                "topic": "X",
                "duration": 60,
                "timestamp": 0,
                "url_video": f"https://cdn.example/{i}.mp4",
            }
            for i in range(offset, offset + count)
        ]
        payload = {
            "err": None,
            "result": {"queryInfo": {"totalResults": total}, "results": entries},
        }
        return httpx.Response(200, json=payload)

    return handler


def test_search_paginates_until_total() -> None:
    calls: list[int] = []

    hits = _source(_paged_handler(120, calls)).search("x")

    assert calls == [0, 50, 100]
    assert len(hits) == 120


def test_search_stops_at_max_results() -> None:
    calls: list[int] = []

    hits = _source(_paged_handler(10_000, calls)).search("x")

    assert len(hits) == MAX_RESULTS
    assert len(calls) == MAX_RESULTS // PAGE_SIZE


def test_search_ignores_non_dict_entries() -> None:
    payload = {
        "err": None,
        "result": {
            "queryInfo": {"totalResults": 2},
            "results": ["oops", _entries()["a4"]],
        },
    }

    hits = _source(lambda r: httpx.Response(200, json=payload)).search("x")

    assert [h.source_id for h in hits] == ["a4"]


def test_search_retries_server_errors_with_backoff() -> None:
    responses = [
        httpx.Response(503),
        httpx.Response(502),
        httpx.Response(200, json=_fixture()),
    ]
    sleeps: list[float] = []

    hits = _source(lambda r: responses.pop(0), sleeps).search("x")

    assert len(hits) == 9
    assert sleeps == [1.0, 2.0]


def test_search_gives_up_after_three_attempts() -> None:
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        raise httpx.ConnectError("refused", request=request)

    with pytest.raises(SourceError, match="giving up after 3 attempts"):
        _source(handler).search("x")
    assert len(calls) == 3


def test_search_does_not_retry_client_errors() -> None:
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(400)

    with pytest.raises(SourceError, match="HTTP 400"):
        _source(handler).search("x")
    assert calls == [1]


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(200, text="<html>"),
        httpx.Response(200, json={"err": ["bad query"], "result": None}),
        httpx.Response(200, json={"err": None, "result": {"results": []}}),
        httpx.Response(
            200,
            json={
                "err": None,
                "result": {"queryInfo": {"totalResults": 1}, "results": "nope"},
            },
        ),
    ],
)
def test_search_rejects_unexpected_payloads(response: httpx.Response) -> None:
    with pytest.raises(SourceError, match="mediathekviewweb"):
        _source(lambda r: response).search("x")


def test_close_closes_client() -> None:
    client = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200)))
    MediathekViewWeb(client=client).close()

    assert client.is_closed


@pytest.mark.live
def test_live_search_returns_hits() -> None:
    source = MediathekViewWeb()
    try:
        hits = source.search("Tatort")
    finally:
        source.close()

    assert hits
    assert all(h.video_url.startswith("http") for h in hits)
```

- [ ] **Step 3: Write failing registry tests** — `tests/test_sources_registry.py`

```python
import pytest

from real_fast_cinema.exceptions import ConfigError
from real_fast_cinema.sources import available_sources, get_source
from real_fast_cinema.sources.mediathekviewweb import MediathekViewWeb


def test_available_sources_lists_mediathekviewweb() -> None:
    assert available_sources() == ["mediathekviewweb"]


def test_get_source_returns_instance() -> None:
    source = get_source("mediathekviewweb")
    try:
        assert isinstance(source, MediathekViewWeb)
        assert source.name == "mediathekviewweb"
    finally:
        source.close()


def test_get_source_unknown_name() -> None:
    with pytest.raises(ConfigError, match="unknown source 'nope'"):
        get_source("nope")
```

- [ ] **Step 4: Run to verify failure**

Run: `uv run pytest tests/test_source_mvw.py tests/test_sources_registry.py -v --no-cov`
Expected: FAIL — `ModuleNotFoundError: real_fast_cinema.sources`.

- [ ] **Step 5: Implement `sources/base.py`**

```python
"""Source plugin protocol."""

from typing import Protocol

from real_fast_cinema.models import Hit


class Source(Protocol):
    """A searchable media service."""

    name: str

    def search(self, term: str) -> list[Hit]:
        """Returns all hits the service reports for ``term``.

        Raises:
            SourceError: If the service cannot be queried.
        """
        ...

    def close(self) -> None:
        """Releases network resources."""
        ...
```

- [ ] **Step 6: Implement `sources/mediathekviewweb.py`**

```python
"""Source plugin for https://mediathekviewweb.de."""

import json
import logging
import time
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

import httpx

from real_fast_cinema import __version__
from real_fast_cinema.exceptions import SourceError
from real_fast_cinema.models import Hit
from real_fast_cinema.text import (
    AD_MARKERS,
    OV_MARKERS,
    SIGN_MARKERS,
    fold,
    split_markers,
)

logger = logging.getLogger(__name__)

NAME = "mediathekviewweb"
API_URL = "https://mediathekviewweb.de/api/query"
PAGE_SIZE = 50
MAX_RESULTS = 500
ATTEMPTS = 3
_TRAILER_WORDS = frozenset({"trailer", "teaser"})
_OV_WORDS = frozenset({"originalversion", "originalfassung"})


def _text(entry: dict[str, Any], key: str) -> str:
    value = entry.get(key)
    return str(value) if value else ""


def to_hit(entry: dict[str, Any]) -> Hit | None:
    """Maps one API entry to a ``Hit``; returns None for unusable entries."""
    hd = _text(entry, "url_video_hd")
    video_url = hd or _text(entry, "url_video") or _text(entry, "url_video_low")
    if not video_url:
        logger.debug("skipping entry %r without video url", entry.get("id"))
        return None
    try:
        duration = int(entry.get("duration") or 0)
        published = datetime.fromtimestamp(int(entry.get("timestamp") or 0), tz=UTC)
    except (TypeError, ValueError, OverflowError, OSError):
        logger.debug("skipping malformed entry %r", entry.get("id"))
        return None
    title = _text(entry, "title")
    _, markers = split_markers(title)
    title_words = fold(title).split()
    is_ov = any(m in OV_MARKERS for m in markers) or bool(
        _OV_WORDS.intersection(title_words)
    )
    return Hit(
        source=NAME,
        source_id=_text(entry, "id"),
        channel=_text(entry, "channel"),
        topic=_text(entry, "topic"),
        title=title,
        description=_text(entry, "description"),
        duration=duration,
        published=published,
        video_url=video_url,
        is_hls=".m3u8" in video_url,
        is_hd=bool(hd),
        page_url=_text(entry, "url_website"),
        subtitle_url=_text(entry, "url_subtitle") or None,
        audio_description=any(m in AD_MARKERS for m in markers),
        sign_language=any(m in SIGN_MARKERS for m in markers),
        trailer=bool(title_words) and title_words[0] in _TRAILER_WORDS,
        language="ov" if is_ov else "de",
        year=next((int(m) for m in markers if m.isdigit()), None),
    )


def _parse(response: httpx.Response) -> dict[str, Any]:
    try:
        data = response.json()
        if data.get("err"):
            raise SourceError(f"{NAME}: API error: {data['err']}")
        result: dict[str, Any] = data["result"]
        if not isinstance(result["results"], list):
            raise TypeError("'results' is not a list")
        int(result["queryInfo"]["totalResults"])
    except (ValueError, KeyError, TypeError, AttributeError) as exc:
        raise SourceError(f"{NAME}: unexpected response: {exc!r}") from exc
    return result


class MediathekViewWeb:
    """Queries the MediathekViewWeb JSON API."""

    name = NAME

    def __init__(
        self,
        client: httpx.Client | None = None,
        *,
        backoff: float = 1.0,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._client = client or httpx.Client(
            timeout=30.0,
            headers={"User-Agent": f"real-fast-cinema/{__version__}"},
        )
        self._backoff = backoff
        self._sleep = sleep

    def close(self) -> None:
        """Closes the HTTP client."""
        self._client.close()

    def search(self, term: str) -> list[Hit]:
        """Searches title and topic; paginates up to ``MAX_RESULTS`` entries."""
        hits: list[Hit] = []
        offset = 0
        while offset < MAX_RESULTS:
            result = self._query(term, offset)
            entries: list[Any] = result["results"]
            for entry in entries:
                hit = to_hit(entry) if isinstance(entry, dict) else None
                if hit is not None:
                    hits.append(hit)
            offset += len(entries)
            if not entries or offset >= int(result["queryInfo"]["totalResults"]):
                break
        logger.debug("%s: %r -> %d hits", NAME, term, len(hits))
        return hits

    def _query(self, term: str, offset: int) -> dict[str, Any]:
        body = json.dumps(
            {
                "queries": [{"fields": ["title", "topic"], "query": term}],
                "sortBy": "timestamp",
                "sortOrder": "desc",
                "future": False,
                "offset": offset,
                "size": PAGE_SIZE,
            }
        )
        last_error = ""
        for attempt in range(ATTEMPTS):
            if attempt:
                self._sleep(self._backoff * 2 ** (attempt - 1))
            try:
                response = self._client.post(
                    API_URL, content=body, headers={"Content-Type": "text/plain"}
                )
            except httpx.TransportError as exc:
                last_error = f"{type(exc).__name__}: {exc}"
                continue
            if response.status_code >= 500:
                last_error = f"HTTP {response.status_code}"
                continue
            if response.is_error:
                raise SourceError(f"{NAME}: HTTP {response.status_code}")
            return _parse(response)
        raise SourceError(f"{NAME}: giving up after {ATTEMPTS} attempts ({last_error})")
```

Note: `MAX_RESULTS // PAGE_SIZE` must be an integer number of pages (500 / 50 = 10) so the cap test is exact.

- [ ] **Step 7: Implement `sources/__init__.py`**

```python
"""Source registry."""

from collections.abc import Callable

from real_fast_cinema.exceptions import ConfigError
from real_fast_cinema.sources.base import Source
from real_fast_cinema.sources.mediathekviewweb import MediathekViewWeb

_FACTORIES: dict[str, Callable[[], Source]] = {
    MediathekViewWeb.name: MediathekViewWeb,
}


def available_sources() -> list[str]:
    """Names of all registered sources."""
    return sorted(_FACTORIES)


def get_source(name: str) -> Source:
    """Creates the source registered under ``name``.

    Raises:
        ConfigError: If no source has that name.
    """
    try:
        factory = _FACTORIES[name]
    except KeyError:
        available = ", ".join(available_sources())
        raise ConfigError(f"unknown source {name!r} (available: {available})") from None
    return factory()


__all__ = ["Source", "available_sources", "get_source"]
```

- [ ] **Step 8: Run tests and checks**

Run: `uv run pytest && uv run ruff check --fix src tests && uv run ruff format src tests && uv run mypy src`
Expected: all PASS (live test deselected).

- [ ] **Step 9: Optional live check**

Run: `uv run pytest -m live --no-cov -v`
Expected: `test_live_search_returns_hits` PASS (needs internet).

- [ ] **Step 10: Commit**

```bash
git add src/real_fast_cinema/sources tests
git commit -m "feat(sources): add source registry and MediathekViewWeb plugin"
```

---

### Task 5: SQLite state store

**Files:**
- Create: `src/real_fast_cinema/store.py`
- Test: `tests/test_store.py`

**Interfaces:**
- Consumes: `Hit` (Task 3), `dedup_key`, `durations_close` (Task 3).
- Produces:
  - `store.Record(row_id: int, notified: bool, downloaded: bool, attempts: int)` (frozen dataclass)
  - `store.Store(path: Path | None)` — `None` = in-memory; context manager
  - `Store.find(profile: str, hit: Hit) -> Record | None`
  - `Store.mark_notified(profile: str, hit: Hit) -> None`
  - `Store.mark_downloaded(profile: str, hit: Hit, path: Path) -> None`
  - `Store.mark_failed(profile: str, hit: Hit, error: str) -> int` (returns attempts so far)
  - `Store.last_run(profile: str) -> datetime | None`, `Store.set_last_run(profile: str, when: datetime) -> None`
  - `Store.close() -> None`

- [ ] **Step 1: Write failing tests** — `tests/test_store.py`

```python
from datetime import UTC, datetime
from pathlib import Path

from real_fast_cinema.store import Record, Store
from tests.fakes import make_hit


def test_find_unknown_returns_none() -> None:
    with Store(None) as store:
        assert store.find("p", make_hit()) is None


def test_mark_notified_is_found_again() -> None:
    hit = make_hit()
    with Store(None) as store:
        store.mark_notified("p", hit)

        record = store.find("p", hit)

    assert record is not None
    assert (record.notified, record.downloaded, record.attempts) == (True, False, 0)


def test_find_matches_same_film_from_other_channel() -> None:
    ndr = make_hit(title="Unter Freunden", duration=5170)
    orf = make_hit(title="Tatort: Unter Freunden", duration=5200, channel="ORF")
    with Store(None) as store:
        store.mark_notified("p", ndr)

        assert store.find("p", orf) is not None
        assert store.find("p", make_hit(title="Unter Freunden", duration=600)) is None


def test_profiles_are_independent() -> None:
    hit = make_hit()
    with Store(None) as store:
        store.mark_notified("a", hit)

        assert store.find("b", hit) is None


def test_mark_failed_counts_attempts_and_download_resets_nothing_else() -> None:
    hit = make_hit()
    with Store(None) as store:
        assert store.mark_failed("p", hit, "timeout") == 1
        assert store.mark_failed("p", hit, "timeout") == 2
        store.mark_downloaded("p", hit, Path("/media/x.mp4"))

        record = store.find("p", hit)

    assert record == Record(
        row_id=record.row_id if record else 0,
        notified=False,
        downloaded=True,
        attempts=2,
    )


def test_one_row_per_film() -> None:
    hit = make_hit()
    with Store(None) as store:
        store.mark_failed("p", hit, "x")
        store.mark_notified("p", hit)
        store.mark_downloaded("p", hit, Path("/m/x.mp4"))

        rows = store._db.execute("SELECT COUNT(*) FROM handled").fetchone()

    assert rows == (1,)


def test_state_persists_across_reopen(tmp_path: Path) -> None:
    db = tmp_path / "data" / "state.db"
    hit = make_hit()
    with Store(db) as store:
        store.mark_notified("p", hit)

    with Store(db) as store:
        assert store.find("p", hit) is not None


def test_last_run_roundtrip() -> None:
    when = datetime(2026, 10, 17, 12, 0, tzinfo=UTC)
    with Store(None) as store:
        assert store.last_run("p") is None
        store.set_last_run("p", when)
        store.set_last_run("p", when.replace(hour=13))

        assert store.last_run("p") == when.replace(hour=13)
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_store.py -v --no-cov`
Expected: FAIL — `ModuleNotFoundError: real_fast_cinema.store`.

- [ ] **Step 3: Implement `store.py`**

```python
"""SQLite state: handled films per profile and last run times."""

import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from types import TracebackType
from typing import Self

from real_fast_cinema.matching import dedup_key, durations_close
from real_fast_cinema.models import Hit

_SCHEMA = """
CREATE TABLE IF NOT EXISTS handled (
    id INTEGER PRIMARY KEY,
    profile TEXT NOT NULL,
    key TEXT NOT NULL,
    duration INTEGER NOT NULL,
    notified INTEGER NOT NULL DEFAULT 0,
    downloaded INTEGER NOT NULL DEFAULT 0,
    attempts INTEGER NOT NULL DEFAULT 0,
    last_error TEXT,
    path TEXT,
    url TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS handled_profile_key ON handled (profile, key);
CREATE TABLE IF NOT EXISTS runs (
    profile TEXT PRIMARY KEY,
    last_run TEXT NOT NULL
);
"""


@dataclass(frozen=True)
class Record:
    """State of one film for one profile."""

    row_id: int
    notified: bool
    downloaded: bool
    attempts: int


def _now() -> str:
    return datetime.now(UTC).isoformat()


class Store:
    """Persistent state; ``path=None`` keeps everything in memory."""

    def __init__(self, path: Path | None) -> None:
        if path is None:
            self._db = sqlite3.connect(":memory:")
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            self._db = sqlite3.connect(path)
        self._db.executescript(_SCHEMA)

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()

    def close(self) -> None:
        """Closes the database connection."""
        self._db.close()

    def find(self, profile: str, hit: Hit) -> Record | None:
        """Returns the record of the same film for ``profile``, if any."""
        rows = self._db.execute(
            "SELECT id, duration, notified, downloaded, attempts FROM handled "
            "WHERE profile = ? AND key = ?",
            (profile, dedup_key(hit)),
        ).fetchall()
        for row_id, duration, notified, downloaded, attempts in rows:
            if durations_close(duration, hit.duration):
                return Record(
                    row_id=row_id,
                    notified=bool(notified),
                    downloaded=bool(downloaded),
                    attempts=attempts,
                )
        return None

    def mark_notified(self, profile: str, hit: Hit) -> None:
        """Marks the film as notified."""
        self._update(profile, hit, "notified = 1")

    def mark_downloaded(self, profile: str, hit: Hit, path: Path) -> None:
        """Marks the film as downloaded to ``path``."""
        self._update(
            profile, hit, "downloaded = 1, path = ?, last_error = NULL", str(path)
        )

    def mark_failed(self, profile: str, hit: Hit, error: str) -> int:
        """Records a failed download and returns the number of attempts."""
        row_id = self._update(
            profile, hit, "attempts = attempts + 1, last_error = ?", error
        )
        (attempts,) = self._db.execute(
            "SELECT attempts FROM handled WHERE id = ?", (row_id,)
        ).fetchone()
        return int(attempts)

    def last_run(self, profile: str) -> datetime | None:
        """Start time of the last run of ``profile``."""
        row = self._db.execute(
            "SELECT last_run FROM runs WHERE profile = ?", (profile,)
        ).fetchone()
        return datetime.fromisoformat(row[0]) if row else None

    def set_last_run(self, profile: str, when: datetime) -> None:
        """Stores the start time of the last run of ``profile``."""
        self._db.execute(
            "INSERT INTO runs (profile, last_run) VALUES (?, ?) "
            "ON CONFLICT (profile) DO UPDATE SET last_run = excluded.last_run",
            (profile, when.isoformat()),
        )
        self._db.commit()

    def _ensure(self, profile: str, hit: Hit) -> int:
        record = self.find(profile, hit)
        if record is not None:
            return record.row_id
        (row_id,) = self._db.execute(
            "INSERT INTO handled (profile, key, duration, url, updated_at) "
            "VALUES (?, ?, ?, ?, ?) RETURNING id",
            (profile, dedup_key(hit), hit.duration, hit.video_url, _now()),
        ).fetchone()
        return int(row_id)

    def _update(self, profile: str, hit: Hit, assignments: str, *params: object) -> int:
        # ``assignments`` is always a constant from this module, never user input.
        row_id = self._ensure(profile, hit)
        self._db.execute(
            f"UPDATE handled SET {assignments}, url = ?, updated_at = ? WHERE id = ?",
            (*params, hit.video_url, _now(), row_id),
        )
        self._db.commit()
        return row_id
```

- [ ] **Step 4: Run tests and checks**

Run: `uv run pytest && uv run ruff check --fix src tests && uv run ruff format src tests && uv run mypy src`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add src/real_fast_cinema/store.py tests/test_store.py
git commit -m "feat(store): add SQLite state for handled films and last runs"
```

---

### Task 6: Downloader (MP4 via httpx, HLS via ffmpeg)

**Files:**
- Create: `src/real_fast_cinema/download.py`
- Test: `tests/test_download.py`

**Interfaces:**
- Consumes: `Hit` (Task 3), `display_title` (Task 3), `DownloadOpts` (Task 2), `DownloadError` (Task 1).
- Produces:
  - `render_filename(template: str, hit: Hit, ext: str) -> str`
  - `url_extension(url: str) -> str`
  - `resolve_target(root: Path, target: Path) -> Path` (creates dir; raises `DownloadError` if outside root)
  - `unique_path(directory: Path, name: str) -> Path`
  - `Downloader(downloads_root: Path, *, client: httpx.Client | None = None, run: Callable[..., Any] = subprocess.run, ffmpeg: str | None = "auto")` with `download(hit: Hit, opts: DownloadOpts) -> Path`, `has_ffmpeg: bool` property, `close() -> None`

- [ ] **Step 1: Write failing tests** — `tests/test_download.py`

```python
import subprocess
from pathlib import Path
from typing import Any

import httpx
import pytest

from real_fast_cinema.config import DownloadOpts
from real_fast_cinema.download import (
    Downloader,
    render_filename,
    resolve_target,
    unique_path,
    url_extension,
)
from real_fast_cinema.exceptions import DownloadError
from tests.fakes import make_hit

OPTS = DownloadOpts(target=Path("filme"))


def _client(handler: Any) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


@pytest.mark.parametrize(
    ("template", "overrides", "expected"),
    [
        (
            "{topic} - {title}.{ext}",
            {"title": "Tatort: Unter Freunden"},
            "Tatort - Unter Freunden.mp4",
        ),
        (
            "{topic} - {title}.{ext}",
            {"title": "Teil 1/2: Mord?"},
            "Tatort - Teil 1_2_ Mord_.mp4",
        ),
        (
            "{title} ({year}).{ext}",
            {"title": "Cash (2024)", "year": 2024},
            "Cash (2024).mp4",
        ),
        ("{title} ({year}).{ext}", {}, "Fackel (2026).mp4"),
        ("{date:%Y-%m-%d} {channel} {title}.{ext}", {}, "2026-10-01 ARD Fackel.mp4"),
        ("{title}.{ext}", {"title": ".."}, "...mp4"),
    ],
)
def test_render_filename(
    template: str, overrides: dict[str, Any], expected: str
) -> None:
    # Review focus 3: "/" and ":" never reach the file system.
    name = render_filename(template, make_hit(**overrides), "mp4")

    assert name == expected.strip(".")
    assert "/" not in name


@pytest.mark.parametrize(
    ("url", "ext"),
    [
        ("https://cdn.example/a/film.mp4", "mp4"),
        ("https://cdn.example/a/film.MP4?token=1", "mp4"),
        ("https://cdn.example/a/film.webm", "webm"),
        ("https://cdn.example/a/film", "mp4"),
        ("https://cdn.example/a/film.verylongext", "mp4"),
    ],
)
def test_url_extension(url: str, ext: str) -> None:
    assert url_extension(url) == ext


def test_resolve_target_creates_directory(tmp_path: Path) -> None:
    directory = resolve_target(tmp_path / "media", Path("filme/krimis"))

    assert directory == (tmp_path / "media" / "filme" / "krimis").resolve()
    assert directory.is_dir()


def test_resolve_target_rejects_symlink_escape(tmp_path: Path) -> None:
    root = tmp_path / "media"
    root.mkdir()
    (root / "link").symlink_to(tmp_path / "outside", target_is_directory=True)

    with pytest.raises(DownloadError, match="escapes"):
        resolve_target(root, Path("link"))


def test_unique_path_appends_counter(tmp_path: Path) -> None:
    (tmp_path / "Film.mp4").write_bytes(b"")
    (tmp_path / "Film (2).mp4").write_bytes(b"")

    assert unique_path(tmp_path, "Film.mp4") == tmp_path / "Film (3).mp4"
    assert unique_path(tmp_path, "Neu.mp4") == tmp_path / "Neu.mp4"


def test_http_download_writes_file_atomically(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == "https://cdn.example.org/fackel.mp4"
        return httpx.Response(200, content=b"video-bytes")

    downloader = Downloader(tmp_path, client=_client(handler), ffmpeg=None)

    path = downloader.download(make_hit(), OPTS)

    assert path == (tmp_path / "filme" / "Tatort - Fackel.mp4").resolve()
    assert path.read_bytes() == b"video-bytes"
    assert list(path.parent.glob(".*.part")) == []


def test_http_download_never_overwrites(tmp_path: Path) -> None:
    downloader = Downloader(
        tmp_path,
        client=_client(lambda r: httpx.Response(200, content=b"new")),
        ffmpeg=None,
    )
    first = downloader.download(make_hit(), OPTS)

    second = downloader.download(make_hit(), OPTS)

    assert second.name == "Tatort - Fackel (2).mp4"
    assert first.read_bytes() == b"new"


def test_http_download_detects_truncation(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, headers={"Content-Length": "100"}, content=b"abc")

    downloader = Downloader(tmp_path, client=_client(handler), ffmpeg=None)

    with pytest.raises(DownloadError, match="incomplete"):
        downloader.download(make_hit(), OPTS)
    assert list((tmp_path / "filme").iterdir()) == []


def test_http_error_raises_download_error_and_cleans_up(tmp_path: Path) -> None:
    downloader = Downloader(
        tmp_path, client=_client(lambda r: httpx.Response(404)), ffmpeg=None
    )

    with pytest.raises(DownloadError, match="404"):
        downloader.download(make_hit(), OPTS)
    assert list((tmp_path / "filme").iterdir()) == []


def test_hls_download_uses_ffmpeg_copy(tmp_path: Path) -> None:
    calls: list[tuple[list[str], dict[str, Any]]] = []

    def fake_run(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess[bytes]:
        calls.append((cmd, kwargs))
        Path(cmd[-1]).write_bytes(b"remuxed")
        return subprocess.CompletedProcess(cmd, 0)

    downloader = Downloader(tmp_path, run=fake_run, ffmpeg="/usr/bin/ffmpeg")
    hit = make_hit(is_hls=True, video_url="https://orf.example/o1/chunklist.m3u8")

    path = downloader.download(hit, OPTS)

    assert path.name == "Tatort - Fackel.mp4"
    assert path.read_bytes() == b"remuxed"
    cmd, kwargs = calls[0]
    assert cmd[0] == "/usr/bin/ffmpeg"
    assert cmd[cmd.index("-i") + 1] == "https://orf.example/o1/chunklist.m3u8"
    assert cmd[cmd.index("-c") + 1] == "copy"
    assert kwargs["check"] is True
    assert "shell" not in kwargs


def test_hls_failure_cleans_up(tmp_path: Path) -> None:
    def fake_run(cmd: list[str], **kwargs: Any) -> None:
        Path(cmd[-1]).write_bytes(b"partial")
        raise subprocess.CalledProcessError(1, cmd)

    downloader = Downloader(tmp_path, run=fake_run, ffmpeg="/usr/bin/ffmpeg")
    hit = make_hit(is_hls=True, video_url="https://orf.example/x.m3u8")

    with pytest.raises(DownloadError, match="CalledProcessError"):
        downloader.download(hit, OPTS)
    assert list((tmp_path / "filme").iterdir()) == []


def test_hls_without_ffmpeg(tmp_path: Path) -> None:
    downloader = Downloader(tmp_path, ffmpeg=None)

    assert downloader.has_ffmpeg is False
    with pytest.raises(DownloadError, match="ffmpeg not found"):
        downloader.download(make_hit(is_hls=True, video_url="https://x/y.m3u8"), OPTS)


def test_auto_detects_ffmpeg(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("shutil.which", lambda name: f"/opt/{name}")

    assert Downloader(tmp_path).has_ffmpeg is True
```

Note on the `".."` case: `render_filename` strips leading/trailing dots, so `"...mp4"` becomes `"mp4"`; the test compares against `expected.strip(".")`.

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_download.py -v --no-cov`
Expected: FAIL — `ModuleNotFoundError: real_fast_cinema.download`.

- [ ] **Step 3: Implement `download.py`**

```python
"""Download action: HTTP streaming for MP4, ffmpeg for HLS streams."""

import logging
import re
import shutil
import subprocess
from collections.abc import Callable
from pathlib import Path, PurePosixPath
from typing import Any, Literal
from urllib.parse import urlparse

import httpx

from real_fast_cinema import __version__
from real_fast_cinema.config import DownloadOpts
from real_fast_cinema.exceptions import DownloadError
from real_fast_cinema.models import Hit
from real_fast_cinema.text import display_title

logger = logging.getLogger(__name__)

_INVALID_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
CHUNK_SIZE = 1 << 20
HLS_TIMEOUT = 6 * 3600


def render_filename(template: str, hit: Hit, ext: str) -> str:
    """Renders the rename template into a safe single file name."""
    name = template.format(
        topic=hit.topic,
        title=display_title(hit.topic, hit.title),
        channel=hit.channel,
        year=hit.year if hit.year is not None else hit.published.year,
        date=hit.published,
        ext=ext,
    )
    return _INVALID_CHARS.sub("_", name).strip().strip(".")


def url_extension(url: str) -> str:
    """File extension of the URL path, ``mp4`` if missing or implausible."""
    suffix = PurePosixPath(urlparse(url).path).suffix.lstrip(".").lower()
    return suffix if suffix.isalnum() and len(suffix) <= 4 else "mp4"


def resolve_target(root: Path, target: Path) -> Path:
    """Resolves and creates ``root/target``; it must stay inside ``root``.

    Raises:
        DownloadError: If the directory escapes ``root`` or cannot be created.
    """
    base = root.resolve()
    directory = (base / target).resolve()
    if not directory.is_relative_to(base):
        raise DownloadError(f"target {target} escapes downloads_root {base}")
    try:
        directory.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise DownloadError(f"cannot create {directory}: {exc.strerror}") from exc
    return directory


def unique_path(directory: Path, name: str) -> Path:
    """``directory/name``, with `` (2)``, `` (3)`` ... if the file exists."""
    candidate = directory / name
    stem, suffix = Path(name).stem, Path(name).suffix
    counter = 2
    while candidate.exists():
        candidate = directory / f"{stem} ({counter}){suffix}"
        counter += 1
    if candidate.name != name:
        logger.warning("%s exists, saving as %s", name, candidate.name)
    return candidate


def _content_length(response: httpx.Response) -> int | None:
    if "Content-Encoding" in response.headers:
        return None
    try:
        return int(response.headers["Content-Length"])
    except (KeyError, ValueError):
        return None


class Downloader:
    """Downloads hits into folders below ``downloads_root``."""

    def __init__(
        self,
        downloads_root: Path,
        *,
        client: httpx.Client | None = None,
        run: Callable[..., Any] = subprocess.run,
        ffmpeg: str | Literal["auto"] | None = "auto",
    ) -> None:
        self._root = downloads_root
        self._client = client or httpx.Client(
            timeout=httpx.Timeout(30.0, read=120.0),
            follow_redirects=True,
            headers={"User-Agent": f"real-fast-cinema/{__version__}"},
        )
        self._run = run
        self._ffmpeg = shutil.which("ffmpeg") if ffmpeg == "auto" else ffmpeg

    @property
    def has_ffmpeg(self) -> bool:
        """True if ffmpeg is available for HLS streams."""
        return self._ffmpeg is not None

    def close(self) -> None:
        """Closes the HTTP client."""
        self._client.close()

    def download(self, hit: Hit, opts: DownloadOpts) -> Path:
        """Downloads ``hit`` and returns the final file path.

        Raises:
            DownloadError: On any failure; no partial file is left behind.
        """
        directory = resolve_target(self._root, opts.target)
        ext = "mp4" if hit.is_hls else url_extension(hit.video_url)
        final = unique_path(directory, render_filename(opts.rename, hit, ext))
        part = final.with_name(f".{final.name}.part")
        logger.info("downloading %s -> %s", hit.video_url, final)
        try:
            if hit.is_hls:
                self._download_hls(hit.video_url, part)
            else:
                self._download_http(hit.video_url, part)
            part.replace(final)
        except (httpx.HTTPError, OSError, subprocess.SubprocessError) as exc:
            raise DownloadError(f"{type(exc).__name__}: {exc}") from exc
        finally:
            part.unlink(missing_ok=True)
        return final

    def _download_http(self, url: str, part: Path) -> None:
        with self._client.stream("GET", url) as response:
            response.raise_for_status()
            expected = _content_length(response)
            written = 0
            with part.open("wb") as handle:
                for chunk in response.iter_bytes(CHUNK_SIZE):
                    handle.write(chunk)
                    written += len(chunk)
        if expected is not None and written != expected:
            raise DownloadError(f"incomplete download: {written} of {expected} bytes")

    def _download_hls(self, url: str, part: Path) -> None:
        if self._ffmpeg is None:
            raise DownloadError("ffmpeg not found - required for HLS streams")
        self._run(
            [
                self._ffmpeg,
                "-nostdin",
                "-loglevel",
                "error",
                "-y",
                "-i",
                url,
                "-c",
                "copy",
                "-f",
                "mp4",
                str(part),
            ],
            check=True,
            capture_output=True,
            timeout=HLS_TIMEOUT,
        )
```

- [ ] **Step 4: Run tests and checks**

Run: `uv run pytest && uv run ruff check --fix src tests && uv run ruff format src tests && uv run mypy src`
Expected: all PASS. If `test_http_download_detects_truncation` fails because httpx itself raises on the length mismatch, that is also acceptable behavior: the raised `httpx` error is wrapped as `DownloadError`; then change the test's `match` to `match="incomplete|Error"`.

- [ ] **Step 5: Commit**

```bash
git add src/real_fast_cinema/download.py tests/test_download.py
git commit -m "feat(download): add downloader with atomic writes and ffmpeg HLS support"
```

---

### Task 7: Notifier protocol and e-mail notifier

**Files:**
- Create: `src/real_fast_cinema/notifiers/__init__.py`, `notifiers/base.py`, `notifiers/email.py`
- Test: `tests/test_email.py`

**Interfaces:**
- Consumes: `Report`, `Hit`, `Failure` (Task 3), `display_title` (Task 3), `SmtpConfig` (Task 2), `NotifyError` (Task 1).
- Produces:
  - `notifiers.base.Notifier` protocol: `send(report: Report, recipients: Sequence[str]) -> None`
  - `notifiers.email.format_duration(seconds: int) -> str`
  - `notifiers.email.build_message(report: Report, sender: str, recipients: Sequence[str]) -> EmailMessage`
  - `notifiers.email.EmailNotifier(smtp: SmtpConfig, password: str | None, smtp_factory: Callable[..., smtplib.SMTP] = smtplib.SMTP)`

- [ ] **Step 1: Write failing tests** — `tests/test_email.py`

```python
import smtplib
from pathlib import Path
from typing import Any

import pytest

from real_fast_cinema.config import SmtpConfig
from real_fast_cinema.exceptions import NotifyError
from real_fast_cinema.models import Failure, Report
from real_fast_cinema.notifiers.email import (
    EmailNotifier,
    build_message,
    format_duration,
)
from tests.fakes import make_hit

SMTP = SmtpConfig.model_validate(
    {"host": "smtp.example.org", "user": "bot@example.org", "from": "bot@example.org"}
)


class FakeSMTP:
    def __init__(self, host: str, port: int, timeout: float | None = None) -> None:
        self.address = (host, port)
        self.started_tls = False
        self.login_args: tuple[str, str] | None = None
        self.messages: list[Any] = []
        self.fail = False

    def __enter__(self) -> "FakeSMTP":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def starttls(self, context: Any = None) -> None:
        self.started_tls = True

    def login(self, user: str, password: str) -> None:
        self.login_args = (user, password)

    def send_message(self, message: Any) -> None:
        if self.fail:
            raise smtplib.SMTPRecipientsRefused({})
        self.messages.append(message)


def _report() -> Report:
    report = Report(profile="krimis")
    report.found.append(make_hit(title="<b>Fackel</b> (2025)", year=2025))
    report.downloaded.append((make_hit(title="Cash"), Path("/media/filme/Cash.mp4")))
    report.failed.append(
        Failure(hit=make_hit(title="Licht"), error="timeout", attempts=3, final=True)
    )
    report.errors.append("mediathekviewweb: HTTP 503")
    return report


@pytest.mark.parametrize(
    ("seconds", "text"), [(37, "0m"), (300, "5m"), (5313, "1h 28m"), (7200, "2h 00m")]
)
def test_format_duration(seconds: int, text: str) -> None:
    assert format_duration(seconds) == text


def test_build_message_headers_and_text() -> None:
    message = build_message(_report(), "bot@example.org", ["a@x.org", "b@x.org"])

    assert message["Subject"] == (
        "[rf-cinema] krimis: 1 found, 1 downloaded, 1 failed, 1 source errors"
    )
    assert message["From"] == "bot@example.org"
    assert message["To"] == "a@x.org, b@x.org"
    text = message.get_body(("plain",)).get_content()
    assert "Found" in text
    assert "Tatort - <b>Fackel</b> (2025)" in text
    assert "https://www.example.org/fackel" in text
    assert "https://cdn.example.org/fackel.mp4" in text
    assert "/media/filme/Cash.mp4" in text
    assert "timeout (attempt 3, giving up)" in text
    assert "mediathekviewweb: HTTP 503" in text


def test_build_message_html_is_escaped() -> None:
    html = (
        build_message(_report(), "bot@example.org", ["a@x.org"])
        .get_body(("html",))
        .get_content()
    )

    assert "&lt;b&gt;Fackel&lt;/b&gt;" in html
    assert "<b>Fackel</b>" not in html
    assert 'href="https://www.example.org/fackel"' in html


def test_send_uses_starttls_and_login() -> None:
    created: list[FakeSMTP] = []

    def factory(host: str, port: int, timeout: float) -> FakeSMTP:
        created.append(FakeSMTP(host, port, timeout))
        return created[-1]

    EmailNotifier(SMTP, "secret", smtp_factory=factory).send(_report(), ["a@x.org"])

    smtp = created[0]
    assert smtp.address == ("smtp.example.org", 587)
    assert smtp.started_tls is True
    assert smtp.login_args == ("bot@example.org", "secret")
    assert len(smtp.messages) == 1


def test_send_without_password_skips_login() -> None:
    created: list[FakeSMTP] = []

    def factory(host: str, port: int, timeout: float) -> FakeSMTP:
        created.append(FakeSMTP(host, port, timeout))
        return created[-1]

    EmailNotifier(SMTP, None, smtp_factory=factory).send(_report(), ["a@x.org"])

    assert created[0].login_args is None


def test_send_wraps_smtp_errors() -> None:
    def factory(host: str, port: int, timeout: float) -> FakeSMTP:
        smtp = FakeSMTP(host, port, timeout)
        smtp.fail = True
        return smtp

    with pytest.raises(NotifyError, match="mail delivery failed"):
        EmailNotifier(SMTP, None, smtp_factory=factory).send(_report(), ["a@x.org"])


def test_send_wraps_connection_errors() -> None:
    def factory(host: str, port: int, timeout: float) -> FakeSMTP:
        raise ConnectionRefusedError("refused")

    with pytest.raises(NotifyError, match="refused"):
        EmailNotifier(SMTP, None, smtp_factory=factory).send(_report(), ["a@x.org"])


def test_send_requires_recipients() -> None:
    with pytest.raises(NotifyError, match="no recipients"):
        EmailNotifier(SMTP, None).send(_report(), [])
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_email.py -v --no-cov`
Expected: FAIL — `ModuleNotFoundError: real_fast_cinema.notifiers`.

- [ ] **Step 3: Implement `notifiers/base.py` and `notifiers/__init__.py`**

`notifiers/base.py`:

```python
"""Notifier plugin protocol."""

from collections.abc import Sequence
from typing import Protocol

from real_fast_cinema.models import Report


class Notifier(Protocol):
    """A channel that delivers run reports."""

    def send(self, report: Report, recipients: Sequence[str]) -> None:
        """Delivers ``report``.

        Raises:
            NotifyError: If delivery fails.
        """
        ...
```

`notifiers/__init__.py`:

```python
"""Notification channels."""

from real_fast_cinema.notifiers.base import Notifier

__all__ = ["Notifier"]
```

- [ ] **Step 4: Implement `notifiers/email.py`**

```python
"""E-mail notifier (SMTP with STARTTLS)."""

import html
import logging
import smtplib
import ssl
from collections.abc import Callable, Sequence
from email.message import EmailMessage

from real_fast_cinema.config import SmtpConfig
from real_fast_cinema.exceptions import NotifyError
from real_fast_cinema.models import Hit, Report
from real_fast_cinema.text import display_title

logger = logging.getLogger(__name__)

SMTP_TIMEOUT = 30.0

type Entry = tuple[Hit, str | None]


def format_duration(seconds: int) -> str:
    """Formats seconds as ``1h 28m`` or ``5m``."""
    hours, rest = divmod(seconds, 3600)
    minutes = rest // 60
    return f"{hours}h {minutes:02d}m" if hours else f"{minutes}m"


def _heading(hit: Hit) -> str:
    year = f" ({hit.year})" if hit.year else ""
    return f"{hit.topic} - {display_title(hit.topic, hit.title)}{year}"


def _meta(hit: Hit) -> str:
    return f"{hit.channel}, {format_duration(hit.duration)}, {hit.published:%Y-%m-%d}"


def _sections(report: Report) -> list[tuple[str, list[Entry]]]:
    sections: list[tuple[str, list[Entry]]] = [
        ("Found", [(hit, None) for hit in report.found]),
        ("Downloaded", [(hit, str(path)) for hit, path in report.downloaded]),
        (
            "Failed",
            [
                (
                    f.hit,
                    f"{f.error} (attempt {f.attempts}"
                    f"{', giving up' if f.final else ''})",
                )
                for f in report.failed
            ],
        ),
    ]
    return [(title, entries) for title, entries in sections if entries]


def _text_body(report: Report) -> str:
    lines: list[str] = []
    for title, entries in _sections(report):
        lines += [title, "=" * len(title)]
        for hit, note in entries:
            lines += [_heading(hit), f"  {_meta(hit)}"]
            lines += [f"  Page:  {hit.page_url}", f"  Video: {hit.video_url}"]
            if note:
                lines.append(f"  {note}")
            lines.append("")
    if report.errors:
        lines += ["Source errors", "=" * 13, *report.errors]
    return "\n".join(lines) + "\n"


def _html_body(report: Report) -> str:
    esc = html.escape
    parts: list[str] = []
    for title, entries in _sections(report):
        parts.append(f"<h2>{esc(title)}</h2><ul>")
        for hit, note in entries:
            note_html = f"<br><i>{esc(note)}</i>" if note else ""
            parts.append(
                f"<li><b>{esc(_heading(hit))}</b><br>{esc(_meta(hit))}<br>"
                f'<a href="{esc(hit.page_url)}">Page</a> | '
                f'<a href="{esc(hit.video_url)}">Video</a>{note_html}</li>'
            )
        parts.append("</ul>")
    if report.errors:
        items = "".join(f"<li>{esc(e)}</li>" for e in report.errors)
        parts.append(f"<h2>Source errors</h2><ul>{items}</ul>")
    return "<html><body>" + "".join(parts) + "</body></html>"


def build_message(
    report: Report, sender: str, recipients: Sequence[str]
) -> EmailMessage:
    """Builds a multipart (text + HTML) digest mail for ``report``."""
    message = EmailMessage()
    message["Subject"] = f"[rf-cinema] {report.profile}: {report.summary()}"
    message["From"] = sender
    message["To"] = ", ".join(recipients)
    message.set_content(_text_body(report))
    message.add_alternative(_html_body(report), subtype="html")
    return message


class EmailNotifier:
    """Sends report digests via SMTP."""

    def __init__(
        self,
        smtp: SmtpConfig,
        password: str | None,
        smtp_factory: Callable[..., smtplib.SMTP] = smtplib.SMTP,
    ) -> None:
        self._smtp = smtp
        self._password = password
        self._factory = smtp_factory

    def send(self, report: Report, recipients: Sequence[str]) -> None:
        """Sends one digest mail.

        Raises:
            NotifyError: If there are no recipients or delivery fails.
        """
        if not recipients:
            raise NotifyError("no recipients configured (mail_to)")
        message = build_message(report, self._smtp.from_, recipients)
        try:
            with self._factory(
                self._smtp.host, self._smtp.port, timeout=SMTP_TIMEOUT
            ) as client:
                if self._smtp.starttls:
                    client.starttls(context=ssl.create_default_context())
                if self._smtp.user and self._password:
                    client.login(self._smtp.user, self._password)
                client.send_message(message)
        except (smtplib.SMTPException, OSError) as exc:
            raise NotifyError(f"mail delivery failed: {exc}") from exc
        logger.info("mail sent to %s: %s", ", ".join(recipients), message["Subject"])
```

- [ ] **Step 5: Run tests and checks**

Run: `uv run pytest && uv run ruff check --fix src tests && uv run ruff format src tests && uv run mypy src`
Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add src/real_fast_cinema/notifiers tests/test_email.py
git commit -m "feat(notify): add e-mail digest notifier"
```

---

### Task 8: Runner (one profile run) and run context

**Files:**
- Create: `src/real_fast_cinema/runner.py`, `src/real_fast_cinema/logsetup.py` (only the `VERBOSE` constant now; extended in Task 10)
- Modify: `tests/fakes.py` (add fakes and context helpers)
- Test: `tests/test_runner.py`

**Interfaces:**
- Consumes: everything from Tasks 2–7: `GlobalConfig`, `Profile`, `DownloadOpts`, `LoadedProfile`, `Hit`, `Report`, `Failure`, `select`, `group_hits`, `best_hit`, `Store`, `Source`, `get_source`, `Downloader`, `Notifier`, `EmailNotifier`, exceptions.
- Produces:
  - `logsetup.VERBOSE = 15`
  - `runner.PASSWORD_ENV = "RF_CINEMA_SMTP_PASSWORD"`, `runner.STATE_DB = "state.db"`
  - `runner.Downloading` protocol: `download(hit: Hit, opts: DownloadOpts) -> Path`
  - `runner.RunContext(config, store, sources: Callable[[str], Source], downloader: Downloading, notifier: Notifier | None, dry_run: bool = False, now: Callable[[], datetime])` (frozen dataclass)
  - `runner.run_profile(ctx: RunContext, loaded: LoadedProfile) -> Report` (does **not** set `last_run`)
  - `runner.should_notify(report: Report, profile: Profile) -> bool`
  - `runner.open_context(config: GlobalConfig, *, dry_run: bool = False) -> Iterator[RunContext]` (context manager)
  - `tests.fakes`: `FakeSource`, `FakeNotifier`, `FakeDownloader`, `make_ctx(tmp_path, *, sources, notifier=None, downloader=None, dry_run=False, max_retries=3)`, `make_profile(**overrides) -> LoadedProfile`

- [ ] **Step 1: Create `logsetup.py` stub**

```python
"""Logging setup for the verbosity levels of the CLI."""

import logging

VERBOSE = 15
logging.addLevelName(VERBOSE, "VERBOSE")
```

- [ ] **Step 2: Extend `tests/fakes.py`** (append below `make_hit`; merge the imports at the top)

```python
from collections.abc import Callable, Sequence
from pathlib import Path

from real_fast_cinema.config import DownloadOpts, GlobalConfig, Profile
from real_fast_cinema.exceptions import DownloadError, NotifyError
from real_fast_cinema.loader import LoadedProfile
from real_fast_cinema.models import Report
from real_fast_cinema.runner import RunContext
from real_fast_cinema.sources.base import Source
from real_fast_cinema.store import Store

NOW = datetime(2026, 10, 17, 12, 0, tzinfo=UTC)


class FakeSource:
    def __init__(
        self,
        name: str = "fake",
        results: dict[str, list[Hit]] | None = None,
        error: Exception | None = None,
    ) -> None:
        self.name = name
        self.results = results or {}
        self.error = error
        self.queries: list[str] = []
        self.closed = False

    def search(self, term: str) -> list[Hit]:
        self.queries.append(term)
        if self.error is not None:
            raise self.error
        return list(self.results.get(term, []))

    def close(self) -> None:
        self.closed = True


class FakeNotifier:
    def __init__(self, fail: bool = False) -> None:
        self.fail = fail
        self.sent: list[tuple[Report, list[str]]] = []

    def send(self, report: Report, recipients: Sequence[str]) -> None:
        if self.fail:
            raise NotifyError("smtp down")
        self.sent.append((report, list(recipients)))


class FakeDownloader:
    def __init__(self, root: Path, fail: bool = False) -> None:
        self.root = root
        self.fail = fail
        self.calls: list[Hit] = []

    def download(self, hit: Hit, opts: DownloadOpts) -> Path:
        self.calls.append(hit)
        if self.fail:
            raise DownloadError("connection reset")
        return self.root / opts.target / f"{hit.source_id}.mp4"


def make_ctx(
    tmp_path: Path,
    *,
    sources: dict[str, Source] | Callable[[str], Source],
    notifier: FakeNotifier | None = None,
    downloader: FakeDownloader | None = None,
    dry_run: bool = False,
    max_retries: int = 3,
) -> RunContext:
    config = GlobalConfig.model_validate(
        {
            "data_dir": tmp_path / "data",
            "downloads_root": tmp_path / "media",
            "mail_to": ["me@example.org"],
            "defaults": {"max_retries": max_retries},
        }
    )
    resolver = sources if callable(sources) else sources.__getitem__
    return RunContext(
        config=config,
        store=Store(None),
        sources=resolver,
        downloader=downloader or FakeDownloader(tmp_path),
        notifier=notifier,
        dry_run=dry_run,
        now=lambda: NOW,
    )


def make_profile(**overrides: Any) -> LoadedProfile:
    terms = tuple(overrides.pop("terms", ("Tatort Fackel",)))
    data: dict[str, Any] = {
        "name": "test",
        "sources": ["fake"],
        "titles": "t.txt",
        "action": "info",
    }
    data.update(overrides)
    if data["action"] != "info":
        data.setdefault("download", {"target": "filme"})
    return LoadedProfile(
        profile=Profile.model_validate(data), terms=terms, path=Path("test.yaml")
    )
```

- [ ] **Step 3: Write failing runner tests** — `tests/test_runner.py`

```python
import dataclasses
import logging
from pathlib import Path

import pytest

from real_fast_cinema.config import GlobalConfig
from real_fast_cinema.exceptions import ConfigError, SourceError
from real_fast_cinema.models import Report
from real_fast_cinema.notifiers.email import EmailNotifier
from real_fast_cinema.runner import open_context, run_profile, should_notify
from tests import fakes
from tests.fakes import (
    FakeDownloader,
    FakeNotifier,
    FakeSource,
    make_ctx,
    make_hit,
    make_profile,
)

FACKEL = make_hit(source_id="f1", title="Fackel")
FACKEL_AD = make_hit(
    source_id="f2", title="Fackel (Audiodeskription)", audio_description=True
)
FREUNDE = make_hit(source_id="u1", title="Unter Freunden", duration=5170)


def _fackel_source() -> FakeSource:
    return FakeSource(results={"Tatort Fackel": [FACKEL, FACKEL_AD]})


def test_info_notifies_once_per_film(tmp_path: Path) -> None:
    notifier = FakeNotifier()
    ctx = make_ctx(tmp_path, sources={"fake": _fackel_source()}, notifier=notifier)
    profile = make_profile()

    first = run_profile(ctx, profile)
    second = run_profile(ctx, profile)

    assert first.found == [FACKEL]
    assert second.found == []
    assert len(notifier.sent) == 1
    assert notifier.sent[0][1] == ["me@example.org"]


def test_profile_recipients_override_global(tmp_path: Path) -> None:
    notifier = FakeNotifier()
    ctx = make_ctx(tmp_path, sources={"fake": _fackel_source()}, notifier=notifier)

    run_profile(ctx, make_profile(mail_to=["other@example.org"]))

    assert notifier.sent[0][1] == ["other@example.org"]


def test_failed_mail_is_retried_next_run(tmp_path: Path) -> None:
    ctx = make_ctx(
        tmp_path, sources={"fake": _fackel_source()}, notifier=FakeNotifier(fail=True)
    )
    run_profile(ctx, make_profile())
    working = FakeNotifier()

    second = run_profile(dataclasses.replace(ctx, notifier=working), make_profile())

    assert second.found == [FACKEL]
    assert len(working.sent) == 1


def test_missing_notifier_does_not_mark_notified(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    ctx = make_ctx(tmp_path, sources={"fake": _fackel_source()}, notifier=None)

    run_profile(ctx, make_profile())
    second = run_profile(ctx, make_profile())

    assert second.found == [FACKEL]
    assert "no notifier configured" in caplog.text


def test_download_success_sends_no_mail_by_default(tmp_path: Path) -> None:
    notifier = FakeNotifier()
    downloader = FakeDownloader(tmp_path)
    ctx = make_ctx(
        tmp_path,
        sources={"fake": _fackel_source()},
        notifier=notifier,
        downloader=downloader,
    )
    profile = make_profile(action="download")

    first = run_profile(ctx, profile)
    second = run_profile(ctx, profile)

    assert first.downloaded == [(FACKEL, tmp_path / "filme" / "f1.mp4")]
    assert first.found == []
    assert second.downloaded == []
    assert downloader.calls == [FACKEL]
    assert notifier.sent == []


def test_download_failure_retries_until_limit(tmp_path: Path) -> None:
    notifier = FakeNotifier()
    downloader = FakeDownloader(tmp_path, fail=True)
    ctx = make_ctx(
        tmp_path,
        sources={"fake": _fackel_source()},
        notifier=notifier,
        downloader=downloader,
        max_retries=2,
    )
    profile = make_profile(action="download")

    reports = [run_profile(ctx, profile) for _ in range(3)]

    assert [(f.attempts, f.final) for f in reports[0].failed] == [(1, False)]
    assert [(f.attempts, f.final) for f in reports[1].failed] == [(2, True)]
    assert reports[2].failed == []
    assert len(downloader.calls) == 2
    assert len(notifier.sent) == 2


@pytest.mark.parametrize(
    ("notify", "fail", "mails"),
    [
        ("never", True, 0),
        ("errors", False, 0),
        ("errors", True, 1),
        ("always", False, 1),
        ("always", True, 1),
    ],
)
def test_notify_setting_for_downloads(
    tmp_path: Path, notify: str, fail: bool, mails: int
) -> None:
    notifier = FakeNotifier()
    ctx = make_ctx(
        tmp_path,
        sources={"fake": _fackel_source()},
        notifier=notifier,
        downloader=FakeDownloader(tmp_path, fail=fail),
    )

    run_profile(ctx, make_profile(action="download", notify=notify))

    assert len(notifier.sent) == mails


def test_both_notifies_and_downloads(tmp_path: Path) -> None:
    notifier = FakeNotifier()
    ctx = make_ctx(tmp_path, sources={"fake": _fackel_source()}, notifier=notifier)
    profile = make_profile(action="both", notify="never")

    first = run_profile(ctx, profile)
    second = run_profile(ctx, profile)

    assert first.found == [FACKEL]
    assert [hit for hit, _ in first.downloaded] == [FACKEL]
    assert len(notifier.sent) == 1
    assert (second.found, second.downloaded) == ([], [])


def test_source_error_skips_only_that_source(tmp_path: Path) -> None:
    broken = FakeSource(name="broken", error=SourceError("broken: HTTP 503"))
    ctx = make_ctx(
        tmp_path,
        sources={"broken": broken, "fake": _fackel_source()},
        notifier=FakeNotifier(),
    )
    profile = make_profile(
        sources=["broken", "fake"], terms=("Tatort Fackel", "Unter Freunden")
    )

    report = run_profile(ctx, profile)

    assert report.errors == ["broken: HTTP 503"]
    assert report.found == [FACKEL]
    assert broken.queries == ["Tatort Fackel"]


def test_same_film_from_two_terms_triggers_once(tmp_path: Path) -> None:
    # Review focus 4: overlapping terms must not duplicate actions.
    notifier = FakeNotifier()
    source = FakeSource(results={"Tatort Fackel": [FACKEL], "Fackel": [FACKEL]})
    ctx = make_ctx(tmp_path, sources={"fake": source}, notifier=notifier)

    report = run_profile(ctx, make_profile(terms=("Tatort Fackel", "Fackel")))

    assert report.found == [FACKEL]
    assert len(notifier.sent) == 1


def test_same_film_on_two_channels_picks_best(tmp_path: Path) -> None:
    orf = make_hit(
        source_id="o1",
        channel="ORF",
        title="Tatort: Unter Freunden",
        duration=5170,
        is_hls=True,
        video_url="https://orf.example/x.m3u8",
    )
    source = FakeSource(results={"Tatort Unter Freunden": [orf, FREUNDE]})
    ctx = make_ctx(tmp_path, sources={"fake": source}, notifier=FakeNotifier())

    report = run_profile(ctx, make_profile(terms=("Tatort Unter Freunden",)))

    assert report.found == [FREUNDE]


def test_dry_run_changes_nothing(tmp_path: Path) -> None:
    notifier = FakeNotifier()
    downloader = FakeDownloader(tmp_path)
    ctx = make_ctx(
        tmp_path,
        sources={"fake": _fackel_source()},
        notifier=notifier,
        downloader=downloader,
        dry_run=True,
    )

    report = run_profile(ctx, make_profile(action="both"))

    assert report.found == [FACKEL]
    assert report.planned == [FACKEL]
    assert downloader.calls == []
    assert notifier.sent == []
    assert ctx.store.find("test", FACKEL) is None


def test_unknown_source_raises_config_error(tmp_path: Path) -> None:
    def resolver(name: str) -> FakeSource:
        raise ConfigError(f"unknown source {name!r}")

    ctx = make_ctx(tmp_path, sources=resolver)

    with pytest.raises(ConfigError, match="unknown source"):
        run_profile(ctx, make_profile())


def test_empty_title_list_warns(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    ctx = make_ctx(tmp_path, sources={"fake": _fackel_source()})

    with caplog.at_level(logging.WARNING):
        report = run_profile(ctx, make_profile(terms=()))

    assert report.found == []
    assert "empty" in caplog.text


@pytest.mark.parametrize(
    ("action", "notify", "fields", "expected"),
    [
        ("info", "errors", {}, False),
        ("info", "never", {"found": [FACKEL]}, True),
        ("info", "always", {"errors": ["x"]}, False),
        ("download", "never", {"errors": ["x"]}, False),
        ("download", "errors", {"errors": ["x"]}, True),
        ("download", "always", {}, False),
    ],
)
def test_should_notify(
    action: str, notify: str, fields: dict[str, list[object]], expected: bool
) -> None:
    report = Report(profile="test", **fields)

    profile = make_profile(action=action, notify=notify).profile

    assert should_notify(report, profile) is expected


def test_open_context_wires_components_and_closes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    created: list[FakeSource] = []

    def fake_get_source(name: str) -> FakeSource:
        created.append(FakeSource(name=name))
        return created[-1]

    monkeypatch.setattr("real_fast_cinema.runner.get_source", fake_get_source)
    config = GlobalConfig.model_validate(
        {
            "data_dir": tmp_path / "data",
            "downloads_root": tmp_path / "media",
            "smtp": {"host": "smtp.example.org", "from": "bot@example.org"},
        }
    )

    with open_context(config) as ctx:
        assert ctx.sources("mediathekviewweb") is ctx.sources("mediathekviewweb")
        assert isinstance(ctx.notifier, EmailNotifier)
        assert ctx.dry_run is False

    assert len(created) == 1
    assert created[0].closed is True
    assert (tmp_path / "data" / "state.db").exists()


def test_open_context_dry_run_creates_no_state(tmp_path: Path) -> None:
    config = GlobalConfig.model_validate(
        {"data_dir": tmp_path / "data", "downloads_root": tmp_path / "media"}
    )

    with open_context(config, dry_run=True) as ctx:
        assert ctx.notifier is None
        assert ctx.dry_run is True

    assert not (tmp_path / "data").exists()


def test_fakes_module_exposes_now() -> None:
    assert fakes.NOW.tzinfo is not None
```

- [ ] **Step 4: Run to verify failure**

Run: `uv run pytest tests/test_runner.py -v --no-cov`
Expected: FAIL — `ModuleNotFoundError: real_fast_cinema.runner` (raised from `tests/fakes.py`).

- [ ] **Step 5: Implement `runner.py`**

```python
"""Executes one profile run and wires the components together."""

import logging
import os
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

from real_fast_cinema.config import DownloadOpts, GlobalConfig, Profile
from real_fast_cinema.download import Downloader
from real_fast_cinema.exceptions import (
    ConfigError,
    DownloadError,
    NotifyError,
    SourceError,
)
from real_fast_cinema.loader import LoadedProfile
from real_fast_cinema.logsetup import VERBOSE
from real_fast_cinema.matching import best_hit, group_hits, select
from real_fast_cinema.models import Failure, Hit, Report
from real_fast_cinema.notifiers.base import Notifier
from real_fast_cinema.notifiers.email import EmailNotifier
from real_fast_cinema.sources import get_source
from real_fast_cinema.sources.base import Source
from real_fast_cinema.store import Store

logger = logging.getLogger(__name__)

PASSWORD_ENV = "RF_CINEMA_SMTP_PASSWORD"
STATE_DB = "state.db"


class Downloading(Protocol):
    """Anything that can download a hit."""

    def download(self, hit: Hit, opts: DownloadOpts) -> Path:
        """Downloads ``hit`` and returns the file path."""
        ...


def _utcnow() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True)
class RunContext:
    """Everything a profile run needs."""

    config: GlobalConfig
    store: Store
    sources: Callable[[str], Source]
    downloader: Downloading
    notifier: Notifier | None
    dry_run: bool = False
    now: Callable[[], datetime] = field(default=_utcnow)


def run_profile(ctx: RunContext, loaded: LoadedProfile) -> Report:
    """Searches, filters, deduplicates and acts for one profile.

    Raises:
        ConfigError: If a source of the profile is unknown.
    """
    profile = loaded.profile
    report = Report(profile=profile.name)
    if not loaded.terms:
        logger.warning("%s: title list %s is empty", profile.name, profile.titles)
    hits = _collect(ctx, loaded, report)
    for group in group_hits(hits):
        _handle(ctx, profile, best_hit(group), report)
    if not ctx.dry_run:
        _notify(ctx, profile, report)
    logger.info("%s: %s", profile.name, report.summary())
    return report


def _collect(ctx: RunContext, loaded: LoadedProfile, report: Report) -> list[Hit]:
    profile = loaded.profile
    sources = [ctx.sources(name) for name in profile.sources]
    hits: list[Hit] = []
    for source in sources:
        for term in loaded.terms:
            try:
                found = source.search(term)
            except SourceError as exc:
                logger.warning("%s: %s (skipping source this run)", profile.name, exc)
                report.errors.append(str(exc))
                break
            selected = [h for h in found if select(h, term, profile.filters)]
            logger.log(
                VERBOSE,
                "%s: %r on %s: %d of %d hits selected",
                profile.name,
                term,
                source.name,
                len(selected),
                len(found),
            )
            hits.extend(selected)
    return hits


def _handle(ctx: RunContext, profile: Profile, hit: Hit, report: Report) -> None:
    record = ctx.store.find(profile.name, hit)
    max_retries = ctx.config.defaults.max_retries
    attempts = record.attempts if record is not None else 0
    need_info = profile.action in ("info", "both") and not (
        record is not None and record.notified
    )
    need_download = (
        profile.action in ("download", "both")
        and not (record is not None and record.downloaded)
        and attempts < max_retries
    )
    if not (need_info or need_download):
        logger.log(VERBOSE, "%s: already handled: %s", profile.name, hit.title)
        return
    if need_info:
        report.found.append(hit)
    if not need_download:
        return
    if ctx.dry_run:
        report.planned.append(hit)
        return
    if profile.download is None:  # guaranteed by Profile validation
        raise ConfigError(f"profile {profile.name}: missing download section")
    try:
        path = ctx.downloader.download(hit, profile.download)
    except DownloadError as exc:
        attempts = ctx.store.mark_failed(profile.name, hit, str(exc))
        final = attempts >= max_retries
        logger.error(
            "%s: download of %s failed (attempt %d/%d): %s",
            profile.name,
            hit.title,
            attempts,
            max_retries,
            exc,
        )
        report.failed.append(
            Failure(hit=hit, error=str(exc), attempts=attempts, final=final)
        )
    else:
        ctx.store.mark_downloaded(profile.name, hit, path)
        report.downloaded.append((hit, path))


def should_notify(report: Report, profile: Profile) -> bool:
    """Decides whether ``report`` must be sent for ``profile``."""
    if report.found:
        return True
    if profile.action == "info":
        return False
    if profile.notify == "always":
        return bool(report.downloaded or report.failed or report.errors)
    if profile.notify == "errors":
        return bool(report.failed or report.errors)
    return False


def _notify(ctx: RunContext, profile: Profile, report: Report) -> None:
    if not should_notify(report, profile):
        return
    if ctx.notifier is None:
        logger.warning(
            "%s: notification needed but no notifier configured", profile.name
        )
        return
    recipients = profile.mail_to or ctx.config.mail_to
    try:
        ctx.notifier.send(report, recipients)
    except NotifyError as exc:
        logger.error("%s: %s (will retry next run)", profile.name, exc)
        return
    for hit in report.found:
        ctx.store.mark_notified(profile.name, hit)


@contextmanager
def open_context(
    config: GlobalConfig, *, dry_run: bool = False
) -> Iterator[RunContext]:
    """Creates store, sources, downloader and notifier; closes them afterwards.

    In dry-run mode no state database is created.
    """
    db_path = config.data_dir / STATE_DB
    store = Store(None if dry_run and not db_path.exists() else db_path)
    sources: dict[str, Source] = {}

    def resolve(name: str) -> Source:
        if name not in sources:
            sources[name] = get_source(name)
        return sources[name]

    notifier: Notifier | None = None
    if config.smtp is not None:
        notifier = EmailNotifier(config.smtp, os.environ.get(PASSWORD_ENV))
    downloader = Downloader(config.downloads_root)
    try:
        yield RunContext(
            config=config,
            store=store,
            sources=resolve,
            downloader=downloader,
            notifier=notifier,
            dry_run=dry_run,
        )
    finally:
        for source in sources.values():
            source.close()
        downloader.close()
        store.close()
```

- [ ] **Step 6: Run tests and checks**

Run: `uv run pytest && uv run ruff check --fix src tests && uv run ruff format src tests && uv run mypy src`
Expected: all PASS; coverage of `runner.py` ≥ 95 % (only the `profile.download is None` guard may be uncovered).

- [ ] **Step 7: Commit**

```bash
git add src/real_fast_cinema/runner.py src/real_fast_cinema/logsetup.py tests
git commit -m "feat(runner): run profiles with dedup, actions and notifications"
```

---

### Task 9: Scheduler and daemon loop

**Files:**
- Create: `src/real_fast_cinema/scheduler.py`
- Modify: `tests/fakes.py` (add `FakeEvent`)
- Test: `tests/test_scheduler.py`

**Interfaces:**
- Consumes: `LoadedProfile`, `load_global`, `load_profiles` (Task 2), `Store` (Task 5), `RunContext`, `run_profile` (Task 8), `GlobalConfig`, exceptions.
- Produces:
  - `due_profiles(profiles: Sequence[LoadedProfile], store: Store, default_every: timedelta, now: datetime) -> list[LoadedProfile]`
  - `seconds_until_next(profiles, store, default_every, now) -> float`
  - `tick(ctx: RunContext, profiles: Sequence[LoadedProfile]) -> float` (runs due profiles, sets `last_run` even on failure, returns seconds until the next one is due)
  - `OpenContext = Callable[[GlobalConfig], AbstractContextManager[RunContext]]`
  - `run_daemon(config_dir: Path, open_ctx: OpenContext, stop: threading.Event, max_sleep: float = 300.0) -> None`
  - `tests.fakes.FakeEvent(iterations: int)` with `is_set()`, `wait(timeout)`, `delays: list[float]`

- [ ] **Step 1: Add `FakeEvent` to `tests/fakes.py`**

```python
class FakeEvent:
    """Stands in for threading.Event; stops after ``iterations`` waits."""

    def __init__(self, iterations: int) -> None:
        self.remaining = iterations
        self.delays: list[float] = []

    def is_set(self) -> bool:
        return self.remaining <= 0

    def wait(self, timeout: float | None = None) -> bool:
        self.delays.append(timeout if timeout is not None else -1.0)
        self.remaining -= 1
        return False

    def set(self) -> None:
        self.remaining = 0
```

- [ ] **Step 2: Write failing tests** — `tests/test_scheduler.py`

```python
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest

from real_fast_cinema.config import GlobalConfig
from real_fast_cinema.exceptions import ConfigError
from real_fast_cinema.runner import RunContext
from real_fast_cinema.scheduler import (
    due_profiles,
    run_daemon,
    seconds_until_next,
    tick,
)
from real_fast_cinema.store import Store
from tests.fakes import (
    NOW,
    FakeDownloader,
    FakeEvent,
    FakeNotifier,
    FakeSource,
    make_ctx,
    make_hit,
    make_profile,
)

SIX_HOURS = timedelta(hours=6)


def test_due_profiles_respects_per_profile_interval() -> None:
    store = Store(None)
    a = make_profile(name="a")
    b = make_profile(name="b", every="1h")
    c = make_profile(name="c")
    store.set_last_run("a", NOW - timedelta(hours=7))
    store.set_last_run("b", NOW - timedelta(minutes=30))

    due = due_profiles([a, b, c], store, SIX_HOURS, NOW)

    assert [p.profile.name for p in due] == ["a", "c"]


def test_seconds_until_next() -> None:
    store = Store(None)
    a = make_profile(name="a")
    b = make_profile(name="b", every="1h")
    store.set_last_run("a", NOW)
    store.set_last_run("b", NOW - timedelta(minutes=30))

    assert seconds_until_next([a, b], store, SIX_HOURS, NOW) == 1800.0
    assert (
        seconds_until_next([a, b, make_profile(name="new")], store, SIX_HOURS, NOW)
        == 0.0
    )
    assert seconds_until_next([], store, SIX_HOURS, NOW) == float("inf")


def test_seconds_until_next_never_negative() -> None:
    store = Store(None)
    store.set_last_run("a", NOW - timedelta(days=2))

    assert seconds_until_next([make_profile(name="a")], store, SIX_HOURS, NOW) == 0.0


def test_tick_runs_due_profiles_and_records_last_run_even_on_failure(
    tmp_path: Path,
) -> None:
    source = FakeSource(results={"Tatort Fackel": [make_hit()]})

    def resolver(name: str) -> FakeSource:
        if name == "missing":
            raise ConfigError("unknown source 'missing'")
        return source

    notifier = FakeNotifier()
    ctx = make_ctx(tmp_path, sources=resolver, notifier=notifier)
    good = make_profile(name="good")
    broken = make_profile(name="broken", sources=["missing"])

    delay = tick(ctx, [good, broken])

    assert ctx.store.last_run("good") == NOW
    assert ctx.store.last_run("broken") == NOW
    assert len(notifier.sent) == 1
    assert delay == SIX_HOURS.total_seconds()


def test_tick_survives_unexpected_exceptions(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    def resolver(name: str) -> FakeSource:
        raise RuntimeError("bug")

    ctx = make_ctx(tmp_path, sources=resolver)

    tick(ctx, [make_profile(name="crashy")])

    assert ctx.store.last_run("crashy") == NOW
    assert "crashy crashed" in caplog.text


def _open_ctx_factory(tmp_path: Path, store: Store) -> Any:
    @contextmanager
    def open_ctx(config: GlobalConfig) -> Iterator[RunContext]:
        yield RunContext(
            config=config,
            store=store,
            sources=lambda name: FakeSource(name=name),
            downloader=FakeDownloader(tmp_path),
            notifier=FakeNotifier(),
            now=lambda: NOW,
        )

    return open_ctx


def test_run_daemon_loops_until_stopped(config_dir: Path, tmp_path: Path) -> None:
    store = Store(None)
    stop = FakeEvent(iterations=2)

    run_daemon(config_dir, _open_ctx_factory(tmp_path, store), stop)

    assert stop.delays == [300.0, 300.0]
    assert store.last_run("krimis") == NOW


def test_run_daemon_uses_short_delay_when_profile_due_soon(
    config_dir: Path, tmp_path: Path
) -> None:
    store = Store(None)
    store.set_last_run("krimis", NOW - SIX_HOURS + timedelta(seconds=42))
    stop = FakeEvent(iterations=1)

    run_daemon(config_dir, _open_ctx_factory(tmp_path, store), stop)

    assert stop.delays == [42.0]


def test_run_daemon_survives_config_errors(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    stop = FakeEvent(iterations=1)

    run_daemon(tmp_path, _open_ctx_factory(tmp_path, Store(None)), stop)

    assert stop.delays == [300.0]
    assert "configuration file not found" in caplog.text


def test_run_daemon_logs_broken_profiles(
    config_dir: Path, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    (config_dir / "profiles" / "broken.yaml").write_text("name: [", encoding="utf-8")
    stop = FakeEvent(iterations=1)

    run_daemon(config_dir, _open_ctx_factory(tmp_path, Store(None)), stop)

    assert "broken.yaml" in caplog.text
```

`FakeEvent` is a duck-typed stand-in for `threading.Event`; tests are not type-checked by CI (`mypy src/`), so no ignore comments are needed.

- [ ] **Step 3: Run to verify failure**

Run: `uv run pytest tests/test_scheduler.py -v --no-cov`
Expected: FAIL — `ModuleNotFoundError: real_fast_cinema.scheduler`.

- [ ] **Step 4: Implement `scheduler.py`**

```python
"""Daemon scheduling: decides which profiles are due and runs them."""

import logging
import threading
from collections.abc import Callable, Sequence
from contextlib import AbstractContextManager
from datetime import datetime, timedelta
from pathlib import Path

from real_fast_cinema.config import GlobalConfig
from real_fast_cinema.exceptions import ConfigError, RfCinemaError
from real_fast_cinema.loader import LoadedProfile, load_global, load_profiles
from real_fast_cinema.runner import RunContext, run_profile
from real_fast_cinema.store import Store

logger = logging.getLogger(__name__)

OpenContext = Callable[[GlobalConfig], AbstractContextManager[RunContext]]


def _interval(loaded: LoadedProfile, default_every: timedelta) -> timedelta:
    return loaded.profile.every or default_every


def due_profiles(
    profiles: Sequence[LoadedProfile],
    store: Store,
    default_every: timedelta,
    now: datetime,
) -> list[LoadedProfile]:
    """Profiles that never ran or whose interval has elapsed."""
    due: list[LoadedProfile] = []
    for loaded in profiles:
        last = store.last_run(loaded.profile.name)
        if last is None or now - last >= _interval(loaded, default_every):
            due.append(loaded)
    return due


def seconds_until_next(
    profiles: Sequence[LoadedProfile],
    store: Store,
    default_every: timedelta,
    now: datetime,
) -> float:
    """Seconds until the next profile is due (``inf`` without profiles)."""
    waits: list[float] = []
    for loaded in profiles:
        last = store.last_run(loaded.profile.name)
        if last is None:
            return 0.0
        waits.append((last + _interval(loaded, default_every) - now).total_seconds())
    return max(0.0, min(waits, default=float("inf")))


def tick(ctx: RunContext, profiles: Sequence[LoadedProfile]) -> float:
    """Runs all due profiles once; returns seconds until the next is due."""
    now = ctx.now()
    default_every = ctx.config.defaults.every
    for loaded in due_profiles(profiles, ctx.store, default_every, now):
        name = loaded.profile.name
        try:
            run_profile(ctx, loaded)
        except RfCinemaError as exc:
            logger.error("profile %s failed: %s", name, exc)
        except Exception:
            logger.exception("profile %s crashed", name)
        ctx.store.set_last_run(name, now)
    return seconds_until_next(profiles, ctx.store, default_every, ctx.now())


def run_daemon(
    config_dir: Path,
    open_ctx: OpenContext,
    stop: threading.Event,
    max_sleep: float = 300.0,
) -> None:
    """Re-reads the configuration and runs due profiles until ``stop`` is set."""
    logger.info("daemon started (config: %s)", config_dir)
    while not stop.is_set():
        delay = max_sleep
        try:
            config = load_global(config_dir)
            profiles, errors = load_profiles(config_dir)
            for message in errors:
                logger.error("%s", message)
            with open_ctx(config) as ctx:
                delay = min(max_sleep, tick(ctx, profiles))
        except ConfigError as exc:
            logger.error("%s", exc)
        logger.debug("sleeping %.0f s", delay)
        stop.wait(delay)
    logger.info("daemon stopped")
```

- [ ] **Step 5: Run tests and checks**

Run: `uv run pytest && uv run ruff check --fix src tests && uv run ruff format src tests && uv run mypy src`
Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add src/real_fast_cinema/scheduler.py tests
git commit -m "feat(scheduler): add per-profile scheduling and daemon loop"
```

---

### Task 10: Logging setup and CLI commands

**Files:**
- Modify: `src/real_fast_cinema/logsetup.py`, `src/real_fast_cinema/cli.py`, `tests/conftest.py`
- Test: `tests/test_logsetup.py`, `tests/test_cli.py`

**Interfaces:**
- Consumes: `load_global`, `load_profiles`, `LoadedProfile` (Task 2), `available_sources` (Task 4), `open_context`, `run_profile` (Task 8), `run_daemon` (Task 9).
- Produces:
  - `logsetup.LOG_FILE = "rf-cinema.log"`, `setup_logging(verbosity: int, log_dir: Path | None) -> None`, `teardown_logging() -> None`
  - CLI commands: `rf-cinema run [-c DIR] [-p NAME] [-Q|-v|-vv]` (exit 0 ok, 1 error, 2 partial failure), `rf-cinema daemon [-c DIR] [-Q|-v|-vv]`, `rf-cinema check [-c DIR] [-p NAME] [-Q|-v|-vv]`, `rf-cinema list-sources`. `-c/--config` defaults to `config`, env `RF_CINEMA_CONFIG`.

- [ ] **Step 1: Write failing logging tests** — `tests/test_logsetup.py`

```python
import logging
from pathlib import Path

from real_fast_cinema.logsetup import LOG_FILE, VERBOSE, setup_logging


def _own_handlers() -> list[logging.Handler]:
    return [h for h in logging.getLogger().handlers if getattr(h, "_rf_cinema", False)]


def _console_levels() -> list[int]:
    return [h.level for h in _own_handlers() if not isinstance(h, logging.FileHandler)]


def test_silent_logs_only_to_file(tmp_path: Path) -> None:
    setup_logging(0, tmp_path)
    logging.getLogger("real_fast_cinema.test").info("hello file")
    for handler in _own_handlers():
        handler.flush()

    assert _console_levels() == []
    assert "hello file" in (tmp_path / LOG_FILE).read_text(encoding="utf-8")


def test_levels_per_verbosity(tmp_path: Path) -> None:
    setup_logging(1, None)
    assert _console_levels() == [logging.INFO]

    setup_logging(2, None)
    assert _console_levels() == [VERBOSE]

    setup_logging(3, tmp_path)
    assert _console_levels() == [logging.DEBUG]
    file_levels = [
        h.level for h in _own_handlers() if isinstance(h, logging.FileHandler)
    ]
    assert file_levels == [logging.DEBUG]
    assert logging.getLogger().level == logging.DEBUG


def test_setup_replaces_previous_handlers(tmp_path: Path) -> None:
    setup_logging(1, tmp_path)
    setup_logging(1, tmp_path)

    assert len(_own_handlers()) == 2
```

- [ ] **Step 2: Implement `logsetup.py`**

```python
"""Logging setup for the verbosity levels of the CLI.

Verbosity: 0 silent (file only), 1 standard, 2 verbose, 3 debug.
"""

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

VERBOSE = 15
logging.addLevelName(VERBOSE, "VERBOSE")

LOG_FILE = "rf-cinema.log"
_MARKER = "_rf_cinema"
_CONSOLE_LEVELS = {1: logging.INFO, 2: VERBOSE}


def teardown_logging() -> None:
    """Removes all handlers installed by ``setup_logging``."""
    root = logging.getLogger()
    for handler in list(root.handlers):
        if getattr(handler, _MARKER, False):
            root.removeHandler(handler)
            handler.close()


def setup_logging(verbosity: int, log_dir: Path | None) -> None:
    """Installs console and file handlers for ``verbosity``."""
    teardown_logging()
    root = logging.getLogger()
    levels: list[int] = []
    if verbosity > 0:
        console = logging.StreamHandler()
        console.setLevel(_CONSOLE_LEVELS.get(verbosity, logging.DEBUG))
        console.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
        handlers: list[logging.Handler] = [console]
    else:
        handlers = []
    if log_dir is not None:
        log_dir.mkdir(parents=True, exist_ok=True)
        file_handler = RotatingFileHandler(
            log_dir / LOG_FILE, maxBytes=5_000_000, backupCount=3, encoding="utf-8"
        )
        file_handler.setLevel(logging.DEBUG if verbosity >= 3 else VERBOSE)
        file_handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
        )
        handlers.append(file_handler)
    for handler in handlers:
        setattr(handler, _MARKER, True)
        root.addHandler(handler)
        levels.append(handler.level)
    root.setLevel(min(levels, default=logging.WARNING))
    logging.getLogger("httpx").setLevel(
        logging.DEBUG if verbosity >= 3 else logging.WARNING
    )
```

- [ ] **Step 3: Add autouse logging reset** — append to `tests/conftest.py`

```python
from collections.abc import Iterator

from real_fast_cinema.logsetup import teardown_logging


@pytest.fixture(autouse=True)
def _reset_logging() -> Iterator[None]:
    yield
    teardown_logging()
```

(Move the new imports to the top of the file.)

- [ ] **Step 4: Run logging tests**

Run: `uv run pytest tests/test_logsetup.py -v --no-cov`
Expected: PASS.

- [ ] **Step 5: Write failing CLI tests** — append to `tests/test_cli.py`

```python
from pathlib import Path

import pytest

from real_fast_cinema import cli
from real_fast_cinema.exceptions import SourceError
from tests.fakes import FakeNotifier, FakeSource, make_hit

MARPLE = make_hit(source_id="m1", topic="Miss Marple", title="16 Uhr 50 ab Paddington")


@pytest.fixture
def fake_source(monkeypatch: pytest.MonkeyPatch) -> FakeSource:
    source = FakeSource(name="mediathekviewweb", results={"Miss Marple": [MARPLE]})
    monkeypatch.setattr("real_fast_cinema.runner.get_source", lambda name: source)
    return source


@pytest.fixture
def fake_notifier(monkeypatch: pytest.MonkeyPatch) -> FakeNotifier:
    notifier = FakeNotifier()
    monkeypatch.setattr(
        "real_fast_cinema.runner.EmailNotifier", lambda smtp, password: notifier
    )
    return notifier


def test_list_sources() -> None:
    result = runner.invoke(app, ["list-sources"])

    assert result.exit_code == 0
    assert result.output.strip() == "mediathekviewweb"


def test_check_shows_dry_run_and_writes_no_state(
    config_dir: Path, fake_source: FakeSource, tmp_path: Path
) -> None:
    result = runner.invoke(app, ["check", "-c", str(config_dir), "-Q"])

    assert result.exit_code == 0, result.output
    assert "[krimis]" in result.output
    assert "notify" in result.output
    assert "16 Uhr 50 ab Paddington" in result.output
    assert not (tmp_path / "data").exists()


def test_check_unknown_profile(config_dir: Path) -> None:
    result = runner.invoke(app, ["check", "-c", str(config_dir), "-p", "nope"])

    assert result.exit_code == 1
    assert "Error: unknown profile 'nope'" in result.output


def test_check_reports_broken_profile_without_traceback(config_dir: Path) -> None:
    (config_dir / "profiles" / "broken.yaml").write_text("name: [", encoding="utf-8")

    result = runner.invoke(app, ["check", "-c", str(config_dir)])

    assert result.exit_code == 1
    assert "Error:" in result.output
    assert "broken.yaml" in result.output
    assert "Traceback" not in result.output


def test_check_rejects_unknown_source(config_dir: Path) -> None:
    (config_dir / "profiles" / "krimis.yaml").write_text(
        "name: krimis\nsources: [nope]\ntitles: krimis.txt\n", encoding="utf-8"
    )

    result = runner.invoke(app, ["check", "-c", str(config_dir)])

    assert result.exit_code == 1
    assert "unknown source 'nope'" in result.output


def test_check_requires_smtp_for_notifications(config_dir: Path) -> None:
    (config_dir / "config.yaml").write_text(
        "data_dir: data\ndownloads_root: media\n", encoding="utf-8"
    )

    result = runner.invoke(app, ["check", "-c", str(config_dir)])

    assert result.exit_code == 1
    assert "smtp" in result.output


def test_check_missing_config(tmp_path: Path) -> None:
    result = runner.invoke(app, ["check", "-c", str(tmp_path)])

    assert result.exit_code == 1
    assert "configuration file not found" in result.output


def test_run_notifies_and_records_state(
    config_dir: Path,
    fake_source: FakeSource,
    fake_notifier: FakeNotifier,
    tmp_path: Path,
) -> None:
    first = runner.invoke(app, ["run", "-c", str(config_dir), "-Q"])
    second = runner.invoke(app, ["run", "-c", str(config_dir), "-Q"])

    assert first.exit_code == 0, first.output
    assert second.exit_code == 0, second.output
    assert len(fake_notifier.sent) == 1
    assert (tmp_path / "data" / "state.db").exists()
    assert (tmp_path / "data" / "rf-cinema.log").exists()


def test_run_partial_failure_exit_code(
    config_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
    fake_notifier: FakeNotifier,
) -> None:
    broken = FakeSource(name="mediathekviewweb", error=SourceError("down"))
    monkeypatch.setattr("real_fast_cinema.runner.get_source", lambda name: broken)

    result = runner.invoke(app, ["run", "-c", str(config_dir), "-Q"])

    assert result.exit_code == 2


def test_daemon_starts_loop(config_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[Path] = []
    monkeypatch.setattr(
        cli, "run_daemon", lambda path, open_ctx, stop: calls.append(path)
    )
    monkeypatch.setattr(cli.signal, "signal", lambda signum, handler: None)

    result = runner.invoke(app, ["daemon", "-c", str(config_dir), "-Q"])

    assert result.exit_code == 0, result.output
    assert calls == [config_dir]


def test_daemon_missing_config(tmp_path: Path) -> None:
    result = runner.invoke(app, ["daemon", "-c", str(tmp_path)])

    assert result.exit_code == 1
    assert "Error:" in result.output


@pytest.mark.parametrize(
    ("flags", "level"),
    [
        ((False, False, False), 1),
        ((True, True, True), 0),
        ((False, True, False), 2),
        ((False, True, True), 3),
    ],
)
def test_verbosity(flags: tuple[bool, bool, bool], level: int) -> None:
    assert cli.verbosity(*flags) == level
```

- [ ] **Step 6: Run to verify failure**

Run: `uv run pytest tests/test_cli.py -v --no-cov`
Expected: FAIL — `No such command 'list-sources'` / missing attributes.

- [ ] **Step 7: Implement `cli.py`** (replace the whole file)

```python
"""Command line interface."""

import logging
import shutil
import signal
import threading
from pathlib import Path
from types import FrameType
from typing import Annotated, NoReturn

import typer

from real_fast_cinema import __version__
from real_fast_cinema.config import GlobalConfig
from real_fast_cinema.exceptions import ConfigError, RfCinemaError
from real_fast_cinema.loader import LoadedProfile, load_global, load_profiles
from real_fast_cinema.logsetup import setup_logging
from real_fast_cinema.runner import open_context, run_profile
from real_fast_cinema.scheduler import run_daemon
from real_fast_cinema.sources import available_sources

logger = logging.getLogger(__name__)

app = typer.Typer(
    name="rf-cinema",
    help=f"Searches media libraries for films from title lists (v{__version__})",
    no_args_is_help=True,
)

ConfigDir = Annotated[
    Path,
    typer.Option(
        "--config",
        "-c",
        envvar="RF_CINEMA_CONFIG",
        file_okay=False,
        help="Configuration directory.",
    ),
]
ProfileName = Annotated[
    str | None, typer.Option("--profile", "-p", help="Only this profile.")
]
Silent = Annotated[
    bool, typer.Option("--silent", "-Q", help="No console output (log file only).")
]
Verbose = Annotated[bool, typer.Option("--verbose", "-v", help="Extended output.")]
Debug = Annotated[bool, typer.Option("--debug", "-vv", help="Debug output.")]


def verbosity(silent: bool, verbose: bool, debug: bool) -> int:
    """Maps the verbosity flags to 0 (silent) .. 3 (debug)."""
    return 0 if silent else (3 if debug else (2 if verbose else 1))


def _fail(message: str) -> NoReturn:
    typer.echo(f"Error: {message}", err=True)
    raise typer.Exit(1)


def _load(
    config_dir: Path, profile_name: str | None
) -> tuple[GlobalConfig, list[LoadedProfile]]:
    try:
        config = load_global(config_dir)
        profiles, errors = load_profiles(config_dir)
    except ConfigError as exc:
        _fail(str(exc))
    if errors:
        _fail("\n".join(errors))
    if profile_name is not None:
        profiles = [p for p in profiles if p.profile.name == profile_name]
        if not profiles:
            _fail(f"unknown profile {profile_name!r}")
    known = set(available_sources())
    for loaded in profiles:
        for name in loaded.profile.sources:
            if name not in known:
                _fail(
                    f"{loaded.path}: unknown source {name!r} "
                    f"(available: {', '.join(sorted(known))})"
                )
    return config, profiles


def version_callback(value: bool) -> None:
    if value:
        typer.echo(f"rf-cinema {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: bool = typer.Option(
        False,
        "--version",
        "-V",
        callback=version_callback,
        is_eager=True,
        help="Show version and exit.",
    ),
) -> None:
    """rf-cinema command line."""


@app.command()
def run(
    config_dir: ConfigDir = Path("config"),
    profile: ProfileName = None,
    silent: Silent = False,
    verbose: Verbose = False,
    debug: Debug = False,
) -> None:
    """Run all (or one) profiles once and exit (exit code 2 on partial failure)."""
    config, profiles = _load(config_dir, profile)
    setup_logging(verbosity(silent, verbose, debug), config.data_dir)
    partial = False
    try:
        with open_context(config) as ctx:
            for loaded in profiles:
                report = run_profile(ctx, loaded)
                ctx.store.set_last_run(loaded.profile.name, ctx.now())
                partial = partial or bool(report.failed or report.errors)
    except RfCinemaError as exc:
        _fail(str(exc))
    if partial:
        raise typer.Exit(2)


@app.command()
def daemon(
    config_dir: ConfigDir = Path("config"),
    silent: Silent = False,
    verbose: Verbose = False,
    debug: Debug = False,
) -> None:
    """Run continuously and execute profiles when they are due."""
    try:
        config = load_global(config_dir)
    except ConfigError as exc:
        _fail(str(exc))
    setup_logging(verbosity(silent, verbose, debug), config.data_dir)
    stop = threading.Event()

    def _stop(signum: int, frame: FrameType | None) -> None:
        logger.info("received signal %d, stopping", signum)
        stop.set()

    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    run_daemon(config_dir, open_context, stop)


@app.command()
def check(
    config_dir: ConfigDir = Path("config"),
    profile: ProfileName = None,
    silent: Silent = False,
    verbose: Verbose = False,
    debug: Debug = False,
) -> None:
    """Validate the configuration and show what a run would do (dry run)."""
    config, profiles = _load(config_dir, profile)
    setup_logging(verbosity(silent, verbose, debug), None)
    needs_mail = [
        p.profile.name
        for p in profiles
        if p.profile.action != "download" or p.profile.notify != "never"
    ]
    if needs_mail and config.smtp is None:
        _fail(f"profiles {needs_mail} send mail but config.yaml has no smtp section")
    if shutil.which("ffmpeg") is None:
        typer.echo("Warning: ffmpeg not found - HLS downloads will fail", err=True)
    try:
        with open_context(config, dry_run=True) as ctx:
            for loaded in profiles:
                report = run_profile(ctx, loaded)
                p = loaded.profile
                typer.echo(
                    f"[{p.name}] {len(loaded.terms)} terms, "
                    f"sources: {', '.join(p.sources)}, action: {p.action}"
                )
                for hit in report.found:
                    typer.echo(f"  notify:   {hit.topic} - {hit.title} ({hit.channel})")
                for hit in report.planned:
                    typer.echo(f"  download: {hit.topic} - {hit.title} ({hit.channel})")
                for error in report.errors:
                    typer.echo(f"  error:    {error}")
    except RfCinemaError as exc:
        _fail(str(exc))


@app.command("list-sources")
def list_sources() -> None:
    """List the available sources."""
    for name in available_sources():
        typer.echo(name)
```

Note: `mypy --strict` accepts `_fail(...)` inside `except` as terminating because it returns `NoReturn`.

- [ ] **Step 8: Run tests and checks**

Run: `uv run pytest && uv run ruff check --fix src tests && uv run ruff format src tests && uv run mypy src`
Expected: all PASS, total coverage ≥ 80 %.

- [ ] **Step 9: Manual smoke test**

Run: `uv run rf-cinema --help && uv run rf-cinema --version && uv run rf-cinema list-sources`
Expected: help text with version, `rf-cinema 26.10.0.dev1`, `mediathekviewweb`.

- [ ] **Step 10: Commit**

```bash
git add src/real_fast_cinema/cli.py src/real_fast_cinema/logsetup.py tests
git commit -m "feat(cli): add run, daemon, check and list-sources commands"
```

---

### Task 11: Example configuration and Docker image

**Files:**
- Create: `config.example/config.yaml`, `config.example/profiles/krimis-info.yaml`, `config.example/profiles/miss-marple-download.yaml`, `config.example/titles/krimis.txt`
- Create: `Dockerfile`, `.dockerignore`, `docker-compose.yml`, `.env.example`
- Test: `tests/test_example_config.py`

**Interfaces:**
- Consumes: `load_global`, `load_profiles` (Task 2), `available_sources` (Task 4).
- Produces: a runnable image `ghcr.io/jcmx9/real-fast-cinema` (entrypoint `rf-cinema`, default `daemon --config /config`), volumes `/config`, `/data`, `/media`.

- [ ] **Step 1: Write the failing test** — `tests/test_example_config.py`

```python
from pathlib import Path

from real_fast_cinema.loader import load_global, load_profiles
from real_fast_cinema.sources import available_sources

EXAMPLE = Path(__file__).resolve().parents[1] / "config.example"


def test_example_config_is_valid() -> None:
    config = load_global(EXAMPLE)
    profiles, errors = load_profiles(EXAMPLE)

    assert errors == []
    assert config.smtp is not None
    assert {p.profile.name for p in profiles} == {"krimis-info", "miss-marple-download"}
    for loaded in profiles:
        assert loaded.terms
        assert set(loaded.profile.sources) <= set(available_sources())
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_example_config.py -v --no-cov`
Expected: FAIL — `configuration file not found`.

- [ ] **Step 3: Create the example files**

`config.example/config.yaml`:

```yaml
# Global settings. Relative paths are resolved against this directory.
data_dir: /data            # SQLite state and log file
downloads_root: /media     # all download targets live below this folder

smtp:
  host: smtp.example.org
  port: 587
  starttls: true
  user: rf-cinema@example.org
  from: rf-cinema@example.org
  # password: environment variable RF_CINEMA_SMTP_PASSWORD

mail_to:
  - me@example.org

defaults:
  every: 6h                # run interval if a profile does not set one
  max_retries: 3           # download attempts per film
```

`config.example/profiles/krimis-info.yaml`:

```yaml
name: krimis-info
sources: [mediathekviewweb]
titles: krimis.txt
every: 12h
filters:
  min_duration: 60m
  exclude: [Hörfassung]
action: info
```

`config.example/profiles/miss-marple-download.yaml`:

```yaml
name: miss-marple-download
sources: [mediathekviewweb]
titles: krimis.txt
every: 6h
filters:
  min_duration: 60m
  audio_description: false
  sign_language: false
  trailer: false
  language: any
action: download
download:
  target: filme/krimis
  rename: "{topic} - {title} ({year}).{ext}"
notify: errors             # always | errors | never
```

`config.example/titles/krimis.txt`:

```text
# One search term per line. All words must occur in topic + title.
# Lines starting with # are comments.
Miss Marple
Tatort Unter Freunden
```

- [ ] **Step 4: Run the test**

Run: `uv run pytest tests/test_example_config.py -v --no-cov`
Expected: PASS.

- [ ] **Step 5: Create Docker files**

`Dockerfile`:

```dockerfile
FROM python:3.13-slim AS build
COPY --from=ghcr.io/astral-sh/uv:0.8 /uv /bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
COPY src ./src
RUN uv sync --frozen --no-dev --no-editable

FROM python:3.13-slim
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 1000 rfcinema \
    && mkdir -p /config /data /media \
    && chown rfcinema:rfcinema /data /media
COPY --from=build /app/.venv /app/.venv
ENV PATH="/app/.venv/bin:${PATH}" PYTHONUNBUFFERED=1
USER rfcinema
VOLUME ["/config", "/data", "/media"]
ENTRYPOINT ["rf-cinema"]
CMD ["daemon", "--config", "/config"]
```

`.dockerignore`:

```text
.git
.venv
.mypy_cache
.pytest_cache
.ruff_cache
__pycache__
config
data
media
tests
docs
.env
```

`docker-compose.yml`:

```yaml
# Example deployment (e.g. on s2). Copy config.example/ to ./config first.
services:
  rf-cinema:
    image: ghcr.io/jcmx9/real-fast-cinema:latest
    build: .
    restart: unless-stopped
    env_file: .env
    volumes:
      - ./config:/config:ro
      - ./data:/data
      - ./media:/media
```

`.env.example`:

```text
RF_CINEMA_SMTP_PASSWORD=change-me
```

- [ ] **Step 6: Verify the image**

Run:

```bash
docker build -t rf-cinema:test .
docker run --rm rf-cinema:test --version
docker run --rm rf-cinema:test list-sources
docker run --rm --entrypoint ffmpeg rf-cinema:test -version
```

Expected: `rf-cinema 26.10.0.dev1`, `mediathekviewweb`, ffmpeg version banner. If the `ghcr.io/astral-sh/uv:0.8` tag does not exist anymore, use the newest `0.x` tag listed at https://github.com/astral-sh/uv/pkgs/container/uv.

- [ ] **Step 7: Commit**

```bash
git add config.example Dockerfile .dockerignore docker-compose.yml .env.example tests/test_example_config.py
git commit -m "feat(docker): add example configuration and container image"
```

---

### Task 12: CI, release tooling and project documents

**Files:**
- Create: `.github/workflows/ci.yml`, `.github/workflows/release.yml`, `.github/dependabot.yml`, `.github/CODEOWNERS`, `CODEOWNERS`
- Create: `scripts/release.sh`, `docs/github-release.md`
- Create: `README.md` (German), `README.en.md` (English), `CHANGELOG.md`, `CONTRIBUTING.md`, `SECURITY.md`

**Interfaces:**
- Consumes: CLI (Task 10), Docker image (Task 11), `[tool.bumpversion]` (Task 1).
- Produces: `scripts/release.sh dev | prod [--new-month] | tag`; tag `v*` → GitHub release (pre-release for `.devN`) + GHCR image.

- [ ] **Step 1: CI workflow** — `.github/workflows/ci.yml`

Copy section 7 `ci.yml` of `~/GitHub/CLAUDE.md` verbatim and append this job:

```yaml
  docker-build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Build image
        run: docker build -t rf-cinema:ci .
      - name: Smoke test
        run: docker run --rm rf-cinema:ci --version
```

- [ ] **Step 2: Release workflow** — `.github/workflows/release.yml` (deviation from the template: no PyPI)

```yaml
name: Release

on:
  push:
    tags: ["v*"]

permissions:
  contents: write
  packages: write

jobs:
  github-release:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: softprops/action-gh-release@v2
        with:
          generate_release_notes: true
          prerelease: ${{ contains(github.ref_name, '.dev') }}

  docker:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: docker/setup-buildx-action@v3
      - uses: docker/login-action@v3
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}
      - id: meta
        uses: docker/metadata-action@v5
        with:
          images: ghcr.io/${{ github.repository }}
          tags: |
            type=raw,value=${{ github.ref_name }}
            type=raw,value=latest,enable=${{ !contains(github.ref_name, '.dev') }}
      - uses: docker/build-push-action@v6
        with:
          context: .
          push: true
          tags: ${{ steps.meta.outputs.tags }}
          labels: ${{ steps.meta.outputs.labels }}
```

- [ ] **Step 3: Dependabot, CODEOWNERS**

`.github/dependabot.yml`: copy section 15 of `~/GitHub/CLAUDE.md` and append:

```yaml
  # Docker base images
  - package-ecosystem: "docker"
    directory: "/"
    schedule:
      interval: "weekly"
      day: "monday"
    target-branch: "dev"
    labels:
      - "docker"
      - "automated"
    commit-message:
      prefix: "chore(docker)"
```

`.github/CODEOWNERS` and `CODEOWNERS` (identical, per project structure convention):

```text
# Default reviewer for all files
*       @jcmx9

# Separate review for CI/CD changes
.github/    @jcmx9
```

- [ ] **Step 4: Release script** — `scripts/release.sh` (`chmod +x`)

```bash
#!/usr/bin/env bash
# Release helper for CalVer YY.M.MICRO with .devN pre-releases.
set -euo pipefail

readonly VERSION_RE='^([0-9]{2})\.([0-9]{1,2})\.([0-9]+)(\.dev([0-9]+))?$'

die() {
  printf 'Error: %s\n' "$*" >&2
  exit 1
}

usage() {
  cat <<'EOF'
Usage:
  scripts/release.sh dev                 bump .devN on dev, tag and push
  scripts/release.sh prod [--new-month]  release dev -> main via PR, then tag main
  scripts/release.sh tag                 tag the release version on main and push
EOF
}

require_clean_branch() {
  local branch="$1"
  [[ "$(git rev-parse --abbrev-ref HEAD)" == "${branch}" ]] || die "must be on ${branch}"
  git diff --quiet && git diff --cached --quiet || die "working tree not clean"
  git pull --ff-only origin "${branch}"
}

current_version() {
  uv run bump-my-version show current_version
}

calendar_base() {
  printf '%s.%s' "$(date +%y)" "$((10#$(date +%m)))"
}

next_dev_version() {
  local current="$1"
  [[ "${current}" =~ ${VERSION_RE} ]] || die "cannot parse version ${current}"
  local year="${BASH_REMATCH[1]}" month="${BASH_REMATCH[2]}"
  local micro="${BASH_REMATCH[3]}" dev="${BASH_REMATCH[5]:-}"
  if [[ -n "${dev}" ]]; then
    printf '%s.%s.%s.dev%s' "${year}" "${month}" "${micro}" "$((dev + 1))"
  elif [[ "${year}.${month}" == "$(calendar_base)" ]]; then
    printf '%s.%s.%s.dev1' "${year}" "${month}" "$((micro + 1))"
  else
    printf '%s.0.dev1' "$(calendar_base)"
  fi
}

next_prod_version() {
  local current="$1" new_month="$2"
  [[ "${current}" =~ ${VERSION_RE} ]] || die "cannot parse version ${current}"
  [[ -n "${BASH_REMATCH[5]:-}" ]] || die "${current} is not a dev version"
  if [[ "${new_month}" == "true" ]]; then
    printf '%s.0' "$(calendar_base)"
  else
    printf '%s.%s.%s' "${BASH_REMATCH[1]}" "${BASH_REMATCH[2]}" "${BASH_REMATCH[3]}"
  fi
}

cmd_dev() {
  require_clean_branch dev
  local new
  new="$(next_dev_version "$(current_version)")"
  uv run bump-my-version bump --new-version "${new}"
  git push origin dev --follow-tags
  printf 'Released dev version %s\n' "${new}"
}

cmd_tag() {
  git checkout main
  git pull --ff-only origin main
  local version
  version="$(current_version)"
  [[ "${version}" =~ ${VERSION_RE} ]] || die "cannot parse version ${version}"
  [[ -z "${BASH_REMATCH[5]:-}" ]] || die "main is on dev version ${version}"
  git tag -a "v${version}" -m "Release ${version}"
  git push origin "v${version}"
  git checkout dev
  printf 'Tagged v%s\n' "${version}"
}

cmd_prod() {
  local new_month="false"
  if [[ "${1:-}" == "--new-month" ]]; then
    new_month="true"
  fi
  command -v gh >/dev/null 2>&1 || die "GitHub CLI (gh) is required"
  require_clean_branch dev
  grep -q '^## \[Unreleased\]' CHANGELOG.md || die "CHANGELOG.md lacks [Unreleased]"
  local new pr_url
  new="$(next_prod_version "$(current_version)" "${new_month}")"
  uv run bump-my-version bump --new-version "${new}" --no-tag
  git push origin dev
  pr_url="$(gh pr create --base main --head dev --title "release: ${new}" --body "Release ${new}")"
  sleep 15
  gh pr checks "${pr_url}" --watch --fail-fast || die "CI failed for ${pr_url}"
  gh pr merge "${pr_url}" --rebase \
    || die "merge failed: merge ${pr_url} manually, then run scripts/release.sh tag"
  cmd_tag
}

main() {
  case "${1:-}" in
    dev) cmd_dev ;;
    prod) shift; cmd_prod "$@" ;;
    tag) cmd_tag ;;
    -h | --help | "") usage ;;
    *) usage >&2; exit 2 ;;
  esac
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  main "$@"
fi
```

- [ ] **Step 5: Verify the release script**

Run:

```bash
shellcheck scripts/release.sh
bash -c 'source scripts/release.sh
  next_dev_version 26.10.0.dev1; echo
  next_prod_version 26.10.0.dev3 false; echo
  next_dev_version 26.10.0; echo'
```

Expected: no shellcheck findings; output `26.10.0.dev2`, `26.10.0`, and `26.10.1.dev1` (if run in October 2026; in a later month `YY.M.0.dev1`).

- [ ] **Step 6: `docs/github-release.md`**

```markdown
# Release Workflow

Versions follow CalVer `YY.M.MICRO`; pre-releases on `dev` carry `.devN`.

| Command | Effect |
|---|---|
| `scripts/release.sh dev` | On `dev`: bump `.devN`, commit, tag `vX.devN`, push. The tag triggers a GitHub pre-release and a GHCR image tagged with the version. |
| `scripts/release.sh prod` | On `dev`: strip `.devN`, commit, open PR `dev -> main`, wait for CI, rebase-merge, tag `main`, push. The tag triggers a GitHub release and GHCR images `vX` and `latest`. |
| `scripts/release.sh prod --new-month` | Like `prod`, but the release version starts the current month (`YY.M.0`). |
| `scripts/release.sh tag` | Tag the current release version on `main` (use after a manual merge). |

Before `prod`: move the entries under `## [Unreleased]` in `CHANGELOG.md` to a new
version section and commit on `dev`.

Requirements: `uv`, `gh` (authenticated), a clean working tree.
PyPI is intentionally not used: the service is distributed as a Docker image.
```

- [ ] **Step 7: `CHANGELOG.md`**

```markdown
# Changelog

All notable changes to this project will be documented in this file.
Format based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added
- Profiles with sources, title list, filters, interval and actions
- MediathekViewWeb source with feature detection (audio description,
  sign language, trailer, original version, year)
- Deduplication across channels and runs (SQLite state)
- Actions: e-mail digest, download (MP4 and HLS via ffmpeg)
- CLI: `run`, `daemon`, `check`, `list-sources`
- Docker image and example configuration

[Unreleased]: https://github.com/jcmx9/real-fast-cinema/commits/dev
```

- [ ] **Step 8: `CONTRIBUTING.md`, `SECURITY.md`**

`CONTRIBUTING.md`: copy section 17 of `~/GitHub/CLAUDE.md`, replace `<repo>` with `real-fast-cinema`.

`SECURITY.md`: copy section 16, but replace the e-mail step 1 with:
`1. Use GitHub's private vulnerability reporting: **Security → Report a vulnerability** in this repository.`

- [ ] **Step 9: `README.md` (German)**

````markdown
# real-fast-cinema

> Durchsucht Mediatheken regelmäßig nach Filmen aus deinen Titellisten und meldet oder lädt sie herunter.

**Version:** 26.10.0.dev1 · **Sprache:** Deutsch | [English](README.en.md)

[![CI](https://github.com/jcmx9/real-fast-cinema/actions/workflows/ci.yml/badge.svg)](https://github.com/jcmx9/real-fast-cinema/actions/workflows/ci.yml)
[![codecov](https://codecov.io/gh/jcmx9/real-fast-cinema/branch/main/graph/badge.svg)](https://codecov.io/gh/jcmx9/real-fast-cinema)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

## Beschreibung

`rf-cinema` arbeitet **Profile** ab. Ein Profil verbindet einen oder mehrere **Dienste**
(zunächst [MediathekViewWeb](https://mediathekviewweb.de)) mit einer **Titelliste**
(eigene Textdatei), **Filtern** und einer **Aktion**:

- `info`: Sammelmail mit Links zu allen neuen Treffern
- `download`: Download in höchster Qualität in einen Zielordner mit Namensschema
- `both`: beides

Ein Suchbegriff trifft, wenn **alle Wörter** in Thema und Titel vorkommen
(`Miss Marple` findet alle Miss-Marple-Filme). Jeder Film löst pro Profil nur
**einmal** aus, auch wenn er auf mehreren Sendern läuft.

## Voraussetzungen

- Python >= 3.12
- [uv](https://docs.astral.sh/uv/)
- Git
- ffmpeg (für HLS-Streams, im Docker-Image enthalten)

## Installation

```bash
uv tool install git+https://github.com/jcmx9/real-fast-cinema.git
```

Oder als Container:

```bash
cp -r config.example config && cp .env.example .env   # anpassen
docker compose up -d
```

## Update

```bash
uv tool install --force git+https://github.com/jcmx9/real-fast-cinema.git
```

Container: `docker compose pull && docker compose up -d`

## Verwendung

```bash
rf-cinema check  -c config          # Konfiguration prüfen + Probelauf
rf-cinema run    -c config          # alle Profile einmal ausführen
rf-cinema run    -c config -p krimis-info
rf-cinema daemon -c config          # dauerhaft, Profile nach Intervall
rf-cinema list-sources
rf-cinema --help
rf-cinema --version
```

## Konfiguration

```
config/
  config.yaml          # global: Pfade, SMTP, Empfänger, Defaults
  profiles/*.yaml      # ein Profil pro Datei
  titles/*.txt         # Titellisten: ein Suchbegriff pro Zeile, # = Kommentar
```

Profil-Beispiel:

```yaml
name: miss-marple-download
sources: [mediathekviewweb]
titles: krimis.txt
every: 6h
filters:
  min_duration: 60m        # Trailer/Clips raus
  audio_description: false # true | false | any
  sign_language: false
  trailer: false
  subtitles: any
  language: any            # de | ov | any
  exclude: [Hörfassung]
action: download           # info | download | both
download:
  target: filme/krimis     # relativ zu downloads_root
  rename: "{topic} - {title} ({year}).{ext}"
notify: errors             # always | errors | never
```

Platzhalter für `rename`: `{topic}`, `{title}`, `{channel}`, `{year}` (Jahr aus dem Titel,
sonst Sendejahr), `{date}` (z. B. `{date:%Y-%m-%d}`), `{ext}`. Das SMTP-Passwort kommt
aus der Umgebungsvariablen `RF_CINEMA_SMTP_PASSWORD`. Profile und Titellisten werden
vor jedem Lauf neu eingelesen.

## Optionen

| Option | Beschreibung |
|--------|-------------|
| `--version`, `-V` | Version anzeigen und beenden |
| `--help` | Hilfe anzeigen und beenden |
| `--config`, `-c` | Konfigurationsverzeichnis (Standard `config`, Env `RF_CINEMA_CONFIG`) |
| `--profile`, `-p` | Nur dieses Profil (`run`, `check`) |
| `--silent`, `-Q` | Keine Konsolenausgabe, nur Log-Datei |
| `--verbose`, `-v` | Erweiterte Ausgabe |
| `--debug`, `-vv` | Debug-Ausgabe |

Exit-Codes von `run`: `0` ok, `1` Fehler, `2` Teilfehler (Download oder Dienst fehlgeschlagen).

## Entwicklung

```bash
git clone git@github.com:jcmx9/real-fast-cinema.git
cd real-fast-cinema
uv sync
uv run pytest
uv run pytest -m live          # Tests gegen die echte API
uv run ruff check --fix . && uv run ruff format .
uv run mypy src/
```

## Projektstruktur

```
src/real_fast_cinema/  – Quellcode
tests/                 – Tests (pytest)
config.example/        – Beispielkonfiguration
scripts/               – Release-Skript
docs/                  – Dokumentation
.github/workflows/     – CI/CD-Pipelines
```

## Versionierung

Dieses Projekt nutzt [CalVer](https://calver.org/) im Format `YY.M.MICRO`.
Releases werden mit [bump-my-version](https://github.com/callowayproject/bump-my-version)
verwaltet, siehe [docs/github-release.md](docs/github-release.md).

## Mitwirken

Den vollständigen Ablauf beschreibt [CONTRIBUTING.md](CONTRIBUTING.md). Kurzfassung:

1. Repository forken
2. Feature-Branch von `dev` anlegen (`git checkout -b feature/my-feature dev`)
3. Änderungen committen (Conventional Commits)
4. Pushen und PR gegen `dev` erstellen

## Sicherheit

Sicherheitslücken bitte **nicht** über öffentliche Issues melden.
Den Ablauf beschreibt [SECURITY.md](SECURITY.md).

## Changelog

Siehe [CHANGELOG.md](CHANGELOG.md).

## Lizenz

MIT – siehe [LICENSE](LICENSE).
````

- [ ] **Step 10: `README.en.md` (English, content-identical)**

````markdown
# real-fast-cinema

> Regularly searches media libraries for films from your title lists and notifies you or downloads them.

**Version:** 26.10.0.dev1 · **Language:** [Deutsch](README.md) | English

[![CI](https://github.com/jcmx9/real-fast-cinema/actions/workflows/ci.yml/badge.svg)](https://github.com/jcmx9/real-fast-cinema/actions/workflows/ci.yml)
[![codecov](https://codecov.io/gh/jcmx9/real-fast-cinema/branch/main/graph/badge.svg)](https://codecov.io/gh/jcmx9/real-fast-cinema)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

## Description

`rf-cinema` processes **profiles**. A profile combines one or more **sources**
(initially [MediathekViewWeb](https://mediathekviewweb.de)) with a **title list**
(separate text file), **filters** and an **action**:

- `info`: digest mail with links to all new hits
- `download`: download in maximum quality into a target folder with a naming scheme
- `both`: both

A search term matches if **all words** occur in topic and title
(`Miss Marple` finds all Miss Marple films). Each film triggers only **once**
per profile, even if it is offered by several channels.

## Prerequisites

- Python >= 3.12
- [uv](https://docs.astral.sh/uv/)
- Git
- ffmpeg (for HLS streams, included in the Docker image)

## Installation

```bash
uv tool install git+https://github.com/jcmx9/real-fast-cinema.git
```

Or as a container:

```bash
cp -r config.example config && cp .env.example .env   # adjust
docker compose up -d
```

## Update

```bash
uv tool install --force git+https://github.com/jcmx9/real-fast-cinema.git
```

Container: `docker compose pull && docker compose up -d`

## Usage

```bash
rf-cinema check  -c config          # validate configuration + dry run
rf-cinema run    -c config          # run all profiles once
rf-cinema run    -c config -p krimis-info
rf-cinema daemon -c config          # run continuously, profiles by interval
rf-cinema list-sources
rf-cinema --help
rf-cinema --version
```

## Configuration

```
config/
  config.yaml          # global: paths, SMTP, recipients, defaults
  profiles/*.yaml      # one profile per file
  titles/*.txt         # title lists: one search term per line, # = comment
```

Profile example:

```yaml
name: miss-marple-download
sources: [mediathekviewweb]
titles: krimis.txt
every: 6h
filters:
  min_duration: 60m        # drop trailers/clips
  audio_description: false # true | false | any
  sign_language: false
  trailer: false
  subtitles: any
  language: any            # de | ov | any
  exclude: [Hörfassung]
action: download           # info | download | both
download:
  target: filme/krimis     # relative to downloads_root
  rename: "{topic} - {title} ({year}).{ext}"
notify: errors             # always | errors | never
```

Placeholders for `rename`: `{topic}`, `{title}`, `{channel}`, `{year}` (year from the
title, otherwise broadcast year), `{date}` (e.g. `{date:%Y-%m-%d}`), `{ext}`. The SMTP
password is read from the environment variable `RF_CINEMA_SMTP_PASSWORD`. Profiles and
title lists are re-read before every run.

## Options

| Option | Description |
|--------|------------|
| `--version`, `-V` | Show version and exit |
| `--help` | Show help text and exit |
| `--config`, `-c` | Configuration directory (default `config`, env `RF_CINEMA_CONFIG`) |
| `--profile`, `-p` | Only this profile (`run`, `check`) |
| `--silent`, `-Q` | No console output, log file only |
| `--verbose`, `-v` | Extended output |
| `--debug`, `-vv` | Debug output |

Exit codes of `run`: `0` ok, `1` error, `2` partial failure (download or source failed).

## Development

```bash
git clone git@github.com:jcmx9/real-fast-cinema.git
cd real-fast-cinema
uv sync
uv run pytest
uv run pytest -m live          # tests against the real API
uv run ruff check --fix . && uv run ruff format .
uv run mypy src/
```

## Project Structure

```
src/real_fast_cinema/  – Source code
tests/                 – Tests (pytest)
config.example/        – Example configuration
scripts/               – Release script
docs/                  – Documentation
.github/workflows/     – CI/CD pipelines
```

## Versioning

This project uses [CalVer](https://calver.org/) in the format `YY.M.MICRO`.
Releases are managed with [bump-my-version](https://github.com/callowayproject/bump-my-version),
see [docs/github-release.md](docs/github-release.md).

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for the full workflow. Quick start:

1. Fork the repository
2. Create a feature branch from `dev` (`git checkout -b feature/my-feature dev`)
3. Commit changes (Conventional Commits)
4. Push and create a PR targeting `dev`

## Security

Please do **not** report security vulnerabilities via public issues.
See [SECURITY.md](SECURITY.md) for the reporting process.

## Changelog

See [CHANGELOG.md](CHANGELOG.md).

## License

MIT – see [LICENSE](LICENSE).
````

Add both README files to `[[tool.bumpversion.files]]` so the version line stays in sync:

```toml
[[tool.bumpversion.files]]
filename = "README.md"
search = "**Version:** {current_version}"
replace = "**Version:** {new_version}"

[[tool.bumpversion.files]]
filename = "README.en.md"
search = "**Version:** {current_version}"
replace = "**Version:** {new_version}"
```

- [ ] **Step 11: Final verification**

Run:

```bash
uv run pre-commit autoupdate
uv run pre-commit install
uv run pre-commit run --all-files
uv run pytest
uv run mypy src
uv run bump-my-version show-bump
diff <(grep -c '^## ' README.md) <(grep -c '^## ' README.en.md)
```

Expected: all hooks pass, tests pass with coverage ≥ 80 %, mypy clean, bump preview shows the README and `__init__.py` files, identical section counts in both READMEs.

- [ ] **Step 12: Commit**

```bash
git add .github scripts docs/github-release.md README.md README.en.md CHANGELOG.md CONTRIBUTING.md SECURITY.md CODEOWNERS pyproject.toml .pre-commit-config.yaml
git commit -m "chore: add CI, release tooling and project documents"
```

---

## Spec Coverage

| Spec section | Task |
|---|---|
| 2 Concepts (source, title list, profile, action, notifier) | 2, 4, 7, 8 |
| 3 Matching rules and filters | 3 (feature flags: 4) |
| 4 Deduplication, best hit, quality | 3, 4, 5, 8 |
| 5 Configuration layout, re-read before every run | 2, 9, 11 |
| 6 Components | 1–10 |
| 7 Data flow, MVW API, status semantics | 4, 8 |
| 8 Download | 6 |
| 9 Notification | 7, 8 |
| 10 Error handling | 4, 6, 7, 8, 9, 10 |
| 11 CLI | 10 |
| 12 Deployment | 11 |
| 13 Testing | all |
| 14 Project conventions, no PyPI | 1, 12 |

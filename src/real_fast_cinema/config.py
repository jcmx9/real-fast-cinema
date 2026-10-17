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

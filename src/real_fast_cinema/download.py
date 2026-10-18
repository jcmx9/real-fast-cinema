"""Download action: HTTP streaming for MP4, ffmpeg for HLS streams."""

import contextlib
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
# 255-byte limit minus ".", ".part" and " (999)" added around the name.
MAX_NAME_BYTES = 240


def render_filename(template: str, hit: Hit, ext: str) -> str:
    """Renders the rename template into a safe single file name.

    Args:
        template: Rename template with placeholders such as ``{title}``.
        hit: Hit providing the values for the placeholders.
        ext: File extension without the leading dot.

    Returns:
        A file name without path separators or leading and trailing dots.
    """
    try:
        name = template.format(
            topic=hit.topic,
            title=display_title(hit.topic, hit.title),
            channel=hit.channel,
            year=hit.year if hit.year is not None else hit.published.year,
            date=hit.published,
            ext=ext,
        )
    except (ValueError, KeyError, IndexError) as exc:
        raise DownloadError(f"invalid rename template {template!r}: {exc}") from exc
    return _cap_length(_INVALID_CHARS.sub("_", name).strip().strip("."))


def _cap_length(name: str) -> str:
    """Truncates the stem so the name fits MAX_NAME_BYTES, keeping the extension."""
    if len(name.encode("utf-8")) <= MAX_NAME_BYTES:
        return name
    stem, dot, suffix = name.rpartition(".")
    if not dot or len(suffix) > 8:
        stem, suffix = name, ""
    else:
        suffix = f".{suffix}"
    budget = MAX_NAME_BYTES - len(suffix.encode("utf-8"))
    cut = stem.encode("utf-8")[:budget].decode("utf-8", errors="ignore")
    return cut.rstrip(" .") + suffix


def url_extension(url: str) -> str:
    """Returns the file extension of the URL path, ``mp4`` if missing or implausible.

    Args:
        url: Absolute URL of the media file.

    Returns:
        Lowercase extension without the dot.
    """
    suffix = PurePosixPath(urlparse(url).path).suffix.lstrip(".").lower()
    return suffix if suffix.isalnum() and len(suffix) <= 4 else "mp4"


def resolve_target(root: Path, target: Path) -> Path:
    """Resolves and creates ``root/target``; it must stay inside ``root``.

    Args:
        root: Downloads root directory.
        target: Path relative to ``root``.

    Returns:
        The resolved, existing target directory.

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
    """Returns ``directory/name``, adding `` (2)``, `` (3)`` ... if it exists.

    Args:
        directory: Existing target directory.
        name: Preferred file name.

    Returns:
        A path that does not exist yet.
    """
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

        Args:
            hit: The hit to download.
            opts: Target folder and rename template.

        Returns:
            Path of the finished file.

        Raises:
            DownloadError: On any failure; no partial file is left behind.
        """
        directory = resolve_target(self._root, opts.target)
        ext = "mp4" if hit.is_hls else url_extension(hit.video_url)
        part: Path | None = None
        try:
            final = unique_path(directory, render_filename(opts.rename, hit, ext))
            part = final.with_name(f".{final.name}.part")
            logger.info("downloading %s -> %s", hit.video_url, final)
            if hit.is_hls:
                self._download_hls(hit.video_url, part)
            else:
                self._download_http(hit.video_url, part)
            part.replace(final)
        except (httpx.HTTPError, OSError, subprocess.SubprocessError) as exc:
            raise DownloadError(f"{type(exc).__name__}: {exc}") from exc
        finally:
            if part is not None:
                with contextlib.suppress(OSError):
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

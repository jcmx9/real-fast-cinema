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

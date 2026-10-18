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
    assert hit.published.tzinfo is not None
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


def test_search_wraps_other_http_errors_after_retries() -> None:
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        raise httpx.DecodingError("bad gzip", request=request)

    with pytest.raises(SourceError, match="giving up after 3 attempts"):
        _source(handler).search("x")
    assert len(calls) == 3

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

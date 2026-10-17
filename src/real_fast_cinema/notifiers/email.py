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

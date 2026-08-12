"""MIME construction and STARTTLS SMTP delivery."""

from __future__ import annotations

import mimetypes
import smtplib
import ssl
from email.message import EmailMessage
from pathlib import Path
from typing import Optional, Sequence

from ngts.scripts.regression_mail.models import RenderedMessage, RunRequest


def build_message(
    rendered: RenderedMessage,
    request: RunRequest,
    sender: str,
    attachment_path: Optional[Path],
) -> EmailMessage:
    message = EmailMessage()
    message["Subject"] = rendered.subject
    message["From"] = sender
    message["To"] = ", ".join(request.to)
    if request.cc:
        message["Cc"] = ", ".join(request.cc)
    message.set_content(rendered.plain)
    if rendered.html:
        message.add_alternative(rendered.html, subtype="html")
    if attachment_path:
        content_type, _ = mimetypes.guess_type(attachment_path.name)
        maintype, subtype = (
            content_type.split("/", 1)
            if content_type and "/" in content_type
            else (
                "application",
                "vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        )
        message.add_attachment(
            attachment_path.read_bytes(),
            maintype=maintype,
            subtype=subtype,
            filename=attachment_path.name,
        )
    return message


class SmtpTransport:
    """Deliver a prepared message without silently downgrading TLS."""

    def __init__(self, host: str, port: int, timeout: int = 120):
        self.host = host
        self.port = port
        self.timeout = timeout

    def send(self, message: EmailMessage, request: RunRequest) -> None:
        recipients = list(request.to) + [address for address in request.cc if address not in request.to]
        server = smtplib.SMTP(self.host, self.port, timeout=self.timeout)
        try:
            server.ehlo()
            server.starttls(context=ssl.create_default_context())
            server.ehlo()
            refused = server.send_message(message, to_addrs=recipients)
        finally:
            server.close()
        if refused:
            raise smtplib.SMTPRecipientsRefused(refused)


class CapturingTransport:
    """In-memory SMTP sink used by integration tests and live smoke harnesses."""

    def __init__(self):
        self.messages = []

    def send(self, message: EmailMessage, request: RunRequest) -> None:
        self.messages.append((message, request))

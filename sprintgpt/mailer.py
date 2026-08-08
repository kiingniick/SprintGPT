"""Minimal SMTP email sender used for transactional mail (password resets).

Configuration comes from the environment / .env (see ``Config``):
``SMTP_HOST``, ``SMTP_PORT``, ``SMTP_USER``, ``SMTP_PASSWORD``, ``SMTP_FROM``,
``SMTP_USE_TLS``. If no SMTP host is configured, ``Config.email_configured`` is
False and callers fall back to showing the reset link on screen instead.
"""
from __future__ import annotations

import smtplib
import ssl
from email.message import EmailMessage

from .config import Config


class MailerError(RuntimeError):
    """Raised when an email can't be sent."""


def send_email(
    cfg: Config,
    to: str,
    subject: str,
    text_body: str,
    html_body: str | None = None,
) -> None:
    if not cfg.email_configured:
        raise MailerError("Email is not configured on this server.")

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = cfg.smtp_from
    msg["To"] = to
    msg.set_content(text_body)
    if html_body:
        msg.add_alternative(html_body, subtype="html")

    try:
        if cfg.smtp_port == 465:
            context = ssl.create_default_context()
            with smtplib.SMTP_SSL(cfg.smtp_host, cfg.smtp_port, timeout=20,
                                  context=context) as server:
                if cfg.smtp_user:
                    server.login(cfg.smtp_user, cfg.smtp_password)
                server.send_message(msg)
        else:
            with smtplib.SMTP(cfg.smtp_host, cfg.smtp_port, timeout=20) as server:
                if cfg.smtp_use_tls:
                    server.starttls(context=ssl.create_default_context())
                if cfg.smtp_user:
                    server.login(cfg.smtp_user, cfg.smtp_password)
                server.send_message(msg)
    except (smtplib.SMTPException, OSError) as e:
        raise MailerError(f"Couldn't send email: {e}") from e

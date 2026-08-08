"""Configuration loading from environment / .env file."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

try:
    from dotenv import load_dotenv, set_key
except ImportError:  # pragma: no cover - dotenv is a declared dependency
    load_dotenv = None
    set_key = None

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = PROJECT_ROOT / ".env"


def load_config() -> "Config":
    """Load configuration from the .env file (if present) and the environment."""
    if load_dotenv is not None and ENV_PATH.exists():
        load_dotenv(ENV_PATH)
    return Config(
        strava_client_id=os.getenv("STRAVA_CLIENT_ID", "").strip(),
        strava_client_secret=os.getenv("STRAVA_CLIENT_SECRET", "").strip(),
        strava_access_token=os.getenv("STRAVA_ACCESS_TOKEN", "").strip(),
        strava_refresh_token=os.getenv("STRAVA_REFRESH_TOKEN", "").strip(),
        strava_token_expires_at=_int_or_zero(os.getenv("STRAVA_TOKEN_EXPIRES_AT", "")),
        db_path=os.getenv("SPRINTGPT_DB", str(PROJECT_ROOT / "sprintgpt.db")),
        secret_key=os.getenv("SPRINTGPT_SECRET", "").strip() or _load_or_create_secret(),
        smtp_host=os.getenv("SMTP_HOST", "").strip(),
        smtp_port=_int_or_zero(os.getenv("SMTP_PORT", "")) or 587,
        smtp_user=os.getenv("SMTP_USER", "").strip(),
        smtp_password=os.getenv("SMTP_PASSWORD", ""),
        smtp_from=(os.getenv("SMTP_FROM", "").strip()
                   or os.getenv("SMTP_USER", "").strip()),
        smtp_use_tls=(os.getenv("SMTP_USE_TLS", "true").strip().lower()
                      not in ("0", "false", "no", "off")),
        app_base_url=os.getenv("APP_BASE_URL", "").strip(),
    )


def _load_or_create_secret() -> str:
    """Return a stable secret key for signing sessions, creating one if needed."""
    secret_path = PROJECT_ROOT / ".secret_key"
    if secret_path.exists():
        return secret_path.read_text(encoding="utf-8").strip()
    import secrets

    key = secrets.token_hex(32)
    try:
        secret_path.write_text(key, encoding="utf-8")
    except OSError:
        pass
    return key


def persist_strava_tokens(access_token: str, refresh_token: str, expires_at: int) -> None:
    """Write refreshed Strava tokens back to the .env file so they survive restarts."""
    if set_key is None:
        return
    if not ENV_PATH.exists():
        ENV_PATH.touch()
    set_key(str(ENV_PATH), "STRAVA_ACCESS_TOKEN", access_token)
    set_key(str(ENV_PATH), "STRAVA_REFRESH_TOKEN", refresh_token)
    set_key(str(ENV_PATH), "STRAVA_TOKEN_EXPIRES_AT", str(expires_at))


def _int_or_zero(value: str) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


@dataclass
class Config:
    strava_client_id: str
    strava_client_secret: str
    strava_access_token: str
    strava_refresh_token: str
    strava_token_expires_at: int
    db_path: str
    secret_key: str = "sprintgpt-dev"
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = ""
    smtp_use_tls: bool = True
    app_base_url: str = ""

    @property
    def strava_configured(self) -> bool:
        return bool(self.strava_client_id and self.strava_client_secret)

    @property
    def email_configured(self) -> bool:
        return bool(self.smtp_host and self.smtp_from)

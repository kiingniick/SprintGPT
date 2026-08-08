"""Strava API client: OAuth authorization + activity syncing.

The client is stateless with respect to *whose* account it is talking to: you
pass in the app credentials (client id/secret) and, for API calls, a specific
user's tokens plus an `on_refresh` callback so refreshed tokens can be persisted
back to that user. This lets many different runners connect their own accounts
through the same running app.
"""
from __future__ import annotations

import time
import webbrowser
from dataclasses import dataclass
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Callable, Optional
from urllib.parse import parse_qs, urlparse

import requests

from .models import Activity

AUTH_URL = "https://www.strava.com/oauth/authorize"
TOKEN_URL = "https://www.strava.com/oauth/token"
API_BASE = "https://www.strava.com/api/v3"
SCOPE = "read,activity:read_all"
REDIRECT_HOST = "localhost"
REDIRECT_PORT = 8721
REDIRECT_URI = f"http://{REDIRECT_HOST}:{REDIRECT_PORT}/callback"


class StravaError(RuntimeError):
    pass


@dataclass
class StravaTokens:
    access_token: str
    refresh_token: str
    expires_at: int


@dataclass
class StravaAuthResult:
    tokens: StravaTokens
    athlete_id: Optional[str]
    display_name: Optional[str]


class _OAuthCallbackHandler(BaseHTTPRequestHandler):
    """Tiny one-shot HTTP handler that captures the ?code=... redirect (CLI)."""

    auth_code: Optional[str] = None

    def do_GET(self) -> None:  # noqa: N802 (name mandated by BaseHTTPRequestHandler)
        params = parse_qs(urlparse(self.path).query)
        _OAuthCallbackHandler.auth_code = params.get("code", [None])[0]
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write(
            b"<html><body style='font-family:sans-serif;text-align:center;margin-top:80px'>"
            b"<h2>Paceloop is connected to Strava.</h2>"
            b"<p>You can close this tab and return to the terminal.</p></body></html>"
        )

    def log_message(self, *args) -> None:
        pass


class StravaClient:
    def __init__(
        self,
        client_id: str,
        client_secret: str,
        tokens: Optional[StravaTokens] = None,
        on_refresh: Optional[Callable[[StravaTokens], None]] = None,
    ) -> None:
        self.client_id = client_id
        self.client_secret = client_secret
        self.tokens = tokens
        self.on_refresh = on_refresh
        self.session = requests.Session()

    @property
    def configured(self) -> bool:
        return bool(self.client_id and self.client_secret)

    def _require_configured(self) -> None:
        if not self.configured:
            raise StravaError(
                "This Paceloop instance isn't set up for Strava yet. The app owner "
                "needs to set STRAVA_CLIENT_ID and STRAVA_CLIENT_SECRET in .env."
            )

    # ---- OAuth --------------------------------------------------------------
    def build_authorize_url(self, redirect_uri: str) -> str:
        self._require_configured()
        return (
            f"{AUTH_URL}?client_id={self.client_id}"
            f"&response_type=code&redirect_uri={redirect_uri}"
            f"&approval_prompt=auto&scope={SCOPE}"
        )

    def exchange_code(self, code: str) -> StravaAuthResult:
        """Exchange an authorization code for tokens + athlete identity."""
        self._require_configured()
        resp = self.session.post(
            TOKEN_URL,
            data={
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "code": code,
                "grant_type": "authorization_code",
            },
            timeout=30,
        )
        if resp.status_code != 200:
            raise StravaError(f"Strava token exchange failed: {resp.status_code} {resp.text}")
        data = resp.json()
        athlete = data.get("athlete") or {}
        name = " ".join(
            p for p in [athlete.get("firstname"), athlete.get("lastname")] if p
        ) or athlete.get("username")
        tokens = StravaTokens(
            data["access_token"], data["refresh_token"], data["expires_at"]
        )
        self.tokens = tokens
        return StravaAuthResult(
            tokens=tokens,
            athlete_id=str(athlete["id"]) if athlete.get("id") else None,
            display_name=name,
        )

    def _ensure_token(self) -> str:
        """Return a valid access token, refreshing (and persisting) if expired."""
        if not self.tokens:
            raise StravaError("Not connected to Strava.")
        if time.time() >= self.tokens.expires_at - 60:
            resp = self.session.post(
                TOKEN_URL,
                data={
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "grant_type": "refresh_token",
                    "refresh_token": self.tokens.refresh_token,
                },
                timeout=30,
            )
            if resp.status_code != 200:
                raise StravaError(f"Strava token refresh failed: {resp.status_code} {resp.text}")
            data = resp.json()
            self.tokens = StravaTokens(
                data["access_token"], data["refresh_token"], data["expires_at"]
            )
            if self.on_refresh:
                self.on_refresh(self.tokens)
        return self.tokens.access_token

    # ---- CLI interactive flow ----------------------------------------------
    def authorize_cli(self) -> StravaAuthResult:
        """Run the local-server OAuth flow for the command line."""
        auth_link = self.build_authorize_url(REDIRECT_URI)
        print("Opening your browser to authorize Strava...")
        print(f"If it doesn't open, paste this URL:\n{auth_link}\n")
        webbrowser.open(auth_link)
        server = HTTPServer((REDIRECT_HOST, REDIRECT_PORT), _OAuthCallbackHandler)
        server.handle_request()
        code = _OAuthCallbackHandler.auth_code
        if not code:
            raise StravaError("Did not receive an authorization code from Strava.")
        return self.exchange_code(code)

    # ---- activities ---------------------------------------------------------
    def fetch_activities(self, after: Optional[datetime] = None, max_pages: int = 20) -> list[Activity]:
        """Fetch the connected athlete's runs as Activity models."""
        token = self._ensure_token()
        headers = {"Authorization": f"Bearer {token}"}
        activities: list[Activity] = []
        params: dict = {"per_page": 100}
        if after is not None:
            params["after"] = int(after.replace(tzinfo=timezone.utc).timestamp())

        for page in range(1, max_pages + 1):
            params["page"] = page
            resp = self.session.get(
                f"{API_BASE}/athlete/activities", headers=headers, params=params, timeout=30
            )
            if resp.status_code != 200:
                raise StravaError(f"Failed to fetch activities: {resp.status_code} {resp.text}")
            batch = resp.json()
            if not batch:
                break
            for raw in batch:
                if raw.get("type") not in ("Run", "TrailRun", "VirtualRun"):
                    continue
                activities.append(self._raw_to_activity(raw))
        return activities

    @staticmethod
    def _raw_to_activity(raw: dict) -> Activity:
        start = raw.get("start_date", "").replace("Z", "+00:00")
        try:
            start_dt = datetime.fromisoformat(start)
        except ValueError:
            start_dt = datetime.now(timezone.utc)
        return Activity(
            start_date=start_dt,
            distance_m=float(raw.get("distance", 0.0)),
            moving_time_s=int(raw.get("moving_time", 0)),
            name=raw.get("name", "Run"),
            elevation_gain_m=float(raw.get("total_elevation_gain", 0.0)),
            average_hr=raw.get("average_heartrate"),
            source="strava",
            external_id=str(raw.get("id")),
        )

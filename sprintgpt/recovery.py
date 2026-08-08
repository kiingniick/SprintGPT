"""Crash handler + self-healing for the web app.

What this actually does (and, honestly, what it can't):

- **Detects** every unhandled exception in a request, logs the full traceback to
  ``logs/errors.log`` (rotating) and the console with a short *incident id*.
- **Auto-fixes on the spot** the classes of failure that are genuinely
  self-recoverable at runtime, then transparently re-runs the request:
    * ``database is locked / busy``  -> brief wait + retry (multi-user contention)
    * ``no such table / column``     -> re-run schema init + migrations, then retry
    * ``malformed`` / bad WAL        -> best-effort WAL checkpoint, then retry
- **Fails gracefully** for everything else: instead of the raw "Internal Server
  Error", the user gets a friendly, on-brand page with a "Try again" button and the
  incident id to report.

It can't magically fix arbitrary logic bugs — nothing can — but it turns the common,
recoverable production hiccups into invisible retries and makes the rest debuggable.
"""
from __future__ import annotations

import logging
import os
import re
import sqlite3
import time
import traceback
import uuid
from logging.handlers import RotatingFileHandler
from typing import Callable, Dict, List, Optional, Tuple

from flask import Flask, current_app, g, request
from werkzeug.exceptions import HTTPException

_LOG_DIR = os.getenv("SPRINTGPT_LOG_DIR", "logs")
_MAX_RETRIES = 2


def _logger() -> logging.Logger:
    log = logging.getLogger("sprintgpt.crash")
    if log.handlers:
        return log
    log.setLevel(logging.INFO)
    log.propagate = False
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    try:
        os.makedirs(_LOG_DIR, exist_ok=True)
        fh = RotatingFileHandler(
            os.path.join(_LOG_DIR, "errors.log"),
            maxBytes=1_000_000, backupCount=5, encoding="utf-8",
        )
        fh.setFormatter(fmt)
        log.addHandler(fh)
    except OSError:
        pass  # read-only filesystem: fall back to console only.
    sh = logging.StreamHandler()
    sh.setFormatter(logging.Formatter("[crash %(levelname)s] %(message)s"))
    log.addHandler(sh)
    return log


# ---- self-healing actions --------------------------------------------------

def _heal_wait() -> None:
    """Transient lock contention: give the writer a moment, then retry."""
    time.sleep(0.4)


def _heal_migrate() -> None:
    """Schema drift (missing table/column): re-open storage, which creates any
    missing tables and runs column migrations, then retry the request."""
    from .config import load_config
    from .storage import Storage

    store = Storage(load_config().db_path)
    store.close()


def _heal_checkpoint() -> None:
    """Best-effort recovery from a bad WAL handoff / 'malformed' read."""
    from .config import load_config

    try:
        conn = sqlite3.connect(load_config().db_path, timeout=30)
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        conn.execute("PRAGMA integrity_check")
        conn.close()
    except sqlite3.Error:
        pass


def _diagnose(exc: BaseException) -> Tuple[Optional[str], Optional[Callable[[], None]]]:
    """Map a known-recoverable exception to (label, heal-fn). Otherwise (None, None)."""
    msg = str(exc).lower()
    if isinstance(exc, sqlite3.OperationalError):
        if "locked" in msg or "busy" in msg:
            return "database-locked", _heal_wait
        if "no such table" in msg or "no such column" in msg or "has no column" in msg:
            return "schema-drift", _heal_migrate
        if "malformed" in msg:
            return "db-corruption", _heal_checkpoint
    if isinstance(exc, sqlite3.DatabaseError) and "malformed" in msg:
        return "db-corruption", _heal_checkpoint
    return None, None


def _redispatch():
    """Re-run the view that just failed, within the still-active request context."""
    rule = getattr(request, "url_rule", None)
    endpoint = rule.endpoint if rule else None
    if not endpoint:
        raise RuntimeError("no matched route to retry")
    view = current_app.view_functions.get(endpoint)
    if view is None:
        raise RuntimeError("no view function to retry")
    return view(**(request.view_args or {}))


def _error_page(incident: str, healed_but_failed: bool) -> str:
    note = (
        "We tried to fix it automatically but it didn't take this time."
        if healed_but_failed
        else "We've logged what happened and we're on it."
    )
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Paceloop hit a snag</title>
<style>
  html,body{{height:100%;margin:0}}
  body{{background:#0b0f17;color:#e7ecf5;font-family:-apple-system,"Segoe UI",Roboto,sans-serif;
       display:flex;align-items:center;justify-content:center;flex-direction:column;
       text-align:center;padding:24px;line-height:1.5}}
  .mark{{width:64px;height:64px;border-radius:18px;background:linear-gradient(135deg,#34d399,#22d3ee);
        display:flex;align-items:center;justify-content:center;font-weight:800;font-size:34px;
        color:#04231b;margin-bottom:18px}}
  h1{{font-size:22px;margin:0 0 6px}}
  p{{color:#93a0b8;margin:0 0 8px;max-width:440px}}
  .row{{display:flex;gap:12px;margin-top:18px;flex-wrap:wrap;justify-content:center}}
  a.btn,button.btn{{display:inline-block;padding:13px 20px;border-radius:12px;border:0;cursor:pointer;
     background:linear-gradient(135deg,#34d399,#22d3ee);color:#04231b;font-weight:800;
     text-decoration:none;font-size:15px}}
  a.ghost{{background:#1b2436;color:#e7ecf5;border:1px solid #2b3650}}
  code{{color:#93a0b8;font-size:12px}}
  .id{{margin-top:22px;color:#6b7688;font-size:12px}}
</style></head>
<body>
  <div class="mark">S</div>
  <h1>Something went sideways</h1>
  <p>{note}</p>
  <p>Your data is safe — try that again in a moment.</p>
  <div class="row">
    <button class="btn" onclick="location.reload()">Try again</button>
    <a class="btn ghost" href="/">Back to home</a>
  </div>
  <div class="id">Incident <code>{incident}</code></div>
</body></html>"""


_INCIDENT_RE = re.compile(r"incident=([0-9a-f]{6,})")


def _field(line: str, key: str) -> str:
    i = line.find(key)
    if i < 0:
        return ""
    parts = line[i + len(key):].split()
    return parts[0] if parts else ""


def read_incidents(limit: int = 20) -> Dict[str, object]:
    """Parse the crash log into a compact, admin-friendly summary.

    Returns ``{"rows": [...], "total": N, "recovered": N, "failed": N}`` where
    each row is ``{id, time, path, type, label, status}`` and status is one of
    ``recovered`` (auto-fixed), ``failed`` (shown the recovery page), or
    ``shown`` (unrecoverable, logged). Newest first. Safe if the log is missing.
    (Key is ``rows`` not ``items`` to avoid clashing with dict.items in templates.)
    """
    empty: Dict[str, object] = {"rows": [], "total": 0, "recovered": 0, "failed": 0}
    path = os.path.join(_LOG_DIR, "errors.log")
    if not os.path.exists(path):
        return empty

    incidents: Dict[str, dict] = {}
    order: List[str] = []
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                m = _INCIDENT_RE.search(line)
                if not m:
                    continue
                iid = m.group(1)[:8]
                rec = incidents.get(iid)
                if rec is None:
                    rec = {"id": iid, "time": "", "path": "", "type": "",
                           "label": "", "status": "shown"}
                    incidents[iid] = rec
                    order.append(iid)
                ts = line[:19]
                if len(ts) >= 19 and ts[4:5] == "-" and ts[13:14] == ":":
                    rec["time"] = ts
                if " path=" in line:
                    rec["path"] = _field(line, "path=")
                    rec["type"] = _field(line, "type=")
                    rec["label"] = _field(line, "label=")
                if "recovered incident=" in line:
                    rec["status"] = "recovered"
                elif "retry failed incident=" in line:
                    rec["status"] = "failed"
    except OSError:
        return empty

    rows = [incidents[i] for i in reversed(order)]
    if limit:
        rows = rows[:limit]
    recovered = sum(1 for r in incidents.values() if r["status"] == "recovered")
    failed = sum(1 for r in incidents.values() if r["status"] == "failed")
    return {
        "rows": rows,
        "total": len(incidents),
        "recovered": recovered,
        "failed": failed,
    }


def install_crash_handler(app: Flask) -> None:
    """Register the global crash handler on a Flask app."""
    log = _logger()

    @app.errorhandler(Exception)
    def _handle(exc):  # noqa: ANN001
        # Normal HTTP responses (404/403/redirects/etc.) are not crashes.
        if isinstance(exc, HTTPException):
            return exc

        incident = uuid.uuid4().hex[:8]
        label, heal = _diagnose(exc)
        path = getattr(request, "path", "?")
        log.error(
            "incident=%s path=%s type=%s label=%s\n%s",
            incident, path, type(exc).__name__, label or "unhandled",
            traceback.format_exc(),
        )

        attempts = getattr(g, "_crash_retries", 0)
        can_retry = heal is not None and attempts < _MAX_RETRIES and getattr(request, "url_rule", None)
        if can_retry:
            g._crash_retries = attempts + 1
            try:
                heal()
            except Exception:  # healing is best-effort
                log.error("heal failed incident=%s\n%s", incident, traceback.format_exc())
            try:
                rv = _redispatch()
                log.info(
                    "recovered incident=%s label=%s attempt=%s", incident, label, attempts + 1
                )
                return current_app.make_response(rv)
            except Exception:
                log.error(
                    "retry failed incident=%s\n%s", incident, traceback.format_exc()
                )
                return _error_page(incident, healed_but_failed=True), 500

        return _error_page(incident, healed_but_failed=False), 500

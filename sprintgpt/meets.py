"""Import race / meet results by athlete name from public results databases.

Runners rarely log their races the way a training app expects - their official
times usually live on results sites like Athletic.net (US high-school, college,
and club cross country + track & field). This module lets a runner type their
name, pick their profile from the matches, and pull every distance race they've
run straight into their SprintGPT log as race activities.

The design is provider-based: each site implements a ``search`` (name -> list of
candidate athletes) and a ``results`` (athlete id -> list of ``Activity``). Adding
another source (MileSplit, TFRRS, ...) is just another entry in ``PROVIDERS``.
Athletic.net is implemented today and already spans both cross country and track
meets nationwide.

Results are returned as ``Activity`` objects with ``source="athletic.net"`` and a
stable ``external_id`` (``an-<result id>``) so re-importing is idempotent - the
storage layer's unique (user, external_id) index drops duplicates automatically.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Callable, Optional
from urllib.parse import quote

import requests

from .models import Activity

MILE_M = 1609.344

# The results sites sit behind Cloudflare, which serves a JS bot-challenge to
# blank/unknown user agents. A normal desktop UA + Accept/Referer gets the JSON
# API through cleanly.
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.athletic.net/",
}
_TIMEOUT = 20

# Ignore short sprints for a distance-running coach: they'd skew VDOT and pace
# analytics. 800 m and up (plus all cross country) are imported.
_MIN_TRACK_M = 800
# Anything longer than ~5 h of clock time is a DNS/DNF/field-mark sentinel.
_MAX_SECONDS = 18000


class MeetImportError(RuntimeError):
    """Raised when a results site can't be reached, searched, or parsed."""


@dataclass
class AthleteMatch:
    """One candidate athlete returned from a name search."""

    provider: str          # provider key, e.g. "athleticnet"
    athlete_id: str
    name: str
    detail: str = ""       # "School - City, ST" subtitle to tell people apart
    gender: str = ""       # "M" / "F" / ""
    source: str = ""       # human label, e.g. "Athletic.net"
    city: str = ""         # parsed home city, for location matching
    state: str = ""        # parsed 2-letter state/province code
    local: bool = False    # True when it matches the user's saved location

    @property
    def ref(self) -> str:
        """Opaque token the import route hands back to us (provider:id)."""
        return f"{self.provider}:{self.athlete_id}"


# Full US state / common territory + Canadian province names -> postal codes, so a
# user who types "Oregon" still matches results tagged "OR".
_STATE_CODES = {
    "alabama": "AL", "alaska": "AK", "arizona": "AZ", "arkansas": "AR",
    "california": "CA", "colorado": "CO", "connecticut": "CT", "delaware": "DE",
    "florida": "FL", "georgia": "GA", "hawaii": "HI", "idaho": "ID",
    "illinois": "IL", "indiana": "IN", "iowa": "IA", "kansas": "KS",
    "kentucky": "KY", "louisiana": "LA", "maine": "ME", "maryland": "MD",
    "massachusetts": "MA", "michigan": "MI", "minnesota": "MN", "mississippi": "MS",
    "missouri": "MO", "montana": "MT", "nebraska": "NE", "nevada": "NV",
    "new hampshire": "NH", "new jersey": "NJ", "new mexico": "NM", "new york": "NY",
    "north carolina": "NC", "north dakota": "ND", "ohio": "OH", "oklahoma": "OK",
    "oregon": "OR", "pennsylvania": "PA", "rhode island": "RI",
    "south carolina": "SC", "south dakota": "SD", "tennessee": "TN", "texas": "TX",
    "utah": "UT", "vermont": "VT", "virginia": "VA", "washington": "WA",
    "west virginia": "WV", "wisconsin": "WI", "wyoming": "WY",
    "district of columbia": "DC",
    "ontario": "ON", "quebec": "QC", "british columbia": "BC", "alberta": "AB",
    "manitoba": "MB", "saskatchewan": "SK", "nova scotia": "NS",
    "new brunswick": "NB", "newfoundland and labrador": "NL",
}


def _norm_state(s: str) -> str:
    """Normalize a state string to a 2-letter code for comparison."""
    s = (s or "").strip()
    if not s:
        return ""
    if len(s) == 2:
        return s.upper()
    return _STATE_CODES.get(s.lower(), s.upper())


# ---------------------------------------------------------------------------
# HTTP helper
# ---------------------------------------------------------------------------

def _get_json(url: str) -> dict:
    try:
        resp = requests.get(url, headers=_HEADERS, timeout=_TIMEOUT)
    except requests.RequestException as e:
        raise MeetImportError(f"Couldn't reach the results site: {e}") from e
    try:
        return resp.json()
    except ValueError:
        snippet = (resp.text or "")[:2000].lower()
        if any(m in snippet for m in ("just a moment", "cf_chl", "cf-chl",
                                      "enable javascript", "challenge-platform")):
            raise MeetImportError(
                "The results site is temporarily blocking automated access "
                "(bot protection). Please wait a minute and try again."
            )
        raise MeetImportError("The results site returned an unexpected response.")


# ---------------------------------------------------------------------------
# Athletic.net provider
# ---------------------------------------------------------------------------

_AN_SEARCH = "https://www.athletic.net/api/v1/AutoComplete/search?q={q}"
_AN_BIO = (
    "https://www.athletic.net/api/v1/AthleteBio/GetAthleteBioData"
    "?athleteId={id}&sport={sport}&level="
)

# Track events that aren't a single flat run - skip these when importing.
_NON_RUN = (
    "relay", "hurdle", "steeple", "walk", "dmr", "smr",
    "shot", "discus", "javelin", "hammer", "put", "throw",
    "jump", "vault", "pentath", "heptath", "decath",
)


def _an_parse_subtext(subtext: str) -> tuple[str, str, str]:
    """Split Athletic.net's ``School (HS)||City, ST`` subtext into school/city/state."""
    school, _, loc = (subtext or "").partition("||")
    school = re.sub(r"\s*\([^)]*\)\s*$", "", school).strip()
    loc = loc.strip()
    city = state = ""
    if loc:
        city_part, _, state_part = loc.rpartition(",")
        if city_part:
            city, state = city_part.strip(), state_part.strip()
        else:
            city = loc.strip().strip(",").strip()
    return school, city, state


def _an_search(name: str) -> list[AthleteMatch]:
    data = _get_json(_AN_SEARCH.format(q=quote(name)))
    docs = ((data.get("response") or {}).get("docs")) or []
    out: list[AthleteMatch] = []
    for d in docs:
        if d.get("type") != "Athlete":
            continue
        school, city, state = _an_parse_subtext(d.get("subtext") or "")
        loc = ", ".join(b for b in (city, state) if b)
        detail = " - ".join(b for b in (school, loc) if b)
        out.append(
            AthleteMatch(
                provider="athleticnet",
                athlete_id=str(d.get("id_db")),
                name=d.get("textsuggest") or "Unknown athlete",
                detail=detail,
                gender=(d.get("gender") or "").upper(),
                source="Athletic.net",
                city=city,
                state=state,
            )
        )
    return out


def _an_date(raw: Optional[str]) -> Optional[datetime]:
    if not raw:
        return None
    raw = str(raw).strip()
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw, fmt)
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(raw[:19])
    except ValueError:
        return None


def _dist_label(meters: float) -> str:
    meters = float(meters)
    if abs(meters - MILE_M) < 30:
        return "1 mile"
    if abs(meters - 2 * MILE_M) < 45:
        return "2 mile"
    if meters >= 1000 and abs(meters / 1000 - round(meters / 1000)) < 0.06:
        return f"{int(round(meters / 1000))}k"
    return f"{int(round(meters))} m"


def _event_meters(name: str) -> Optional[float]:
    """Meters for a flat track run, or None for field events / relays / walks."""
    n = (name or "").strip().lower()
    if not n or any(bad in n for bad in _NON_RUN):
        return None
    m = re.search(r"(\d[\d,]*(?:\.\d+)?)\s*mile", n)
    if m:
        return float(m.group(1).replace(",", "")) * MILE_M
    if "mile" in n:
        return MILE_M
    m = re.search(r"(\d[\d,]*)\s*(?:meters?|m\b)", n)
    if m:
        return float(m.group(1).replace(",", ""))
    m = re.search(r"(\d+(?:\.\d+)?)\s*k\b", n)
    if m:
        return float(m.group(1)) * 1000
    return None


def _an_xc(athlete_id: str) -> list[Activity]:
    data = _get_json(_AN_BIO.format(id=athlete_id, sport="xc"))
    meets = data.get("meets") or {}
    out: list[Activity] = []
    for r in data.get("resultsXC") or []:
        secs = r.get("SortValue")
        dist = r.get("Distance")
        if not secs or not dist or dist <= 0 or not (0 < secs < _MAX_SECONDS):
            continue
        meet = meets.get(str(r.get("MeetID"))) or {}
        when = _an_date(meet.get("EndDate"))
        if when is None:
            continue
        label = _dist_label(dist)
        name = f"{label} XC"
        if meet.get("MeetName"):
            name += f" \u00b7 {meet['MeetName']}"
        out.append(
            Activity(
                start_date=when,
                distance_m=float(dist),
                moving_time_s=int(round(secs)),
                name=name,
                source="athletic.net",
                external_id=f"an-{r.get('IDResult')}",
            )
        )
    return out


def _an_tf(athlete_id: str) -> list[Activity]:
    data = _get_json(_AN_BIO.format(id=athlete_id, sport="tf"))
    meets = data.get("meets") or {}
    events = {e.get("IDEvent"): e for e in (data.get("eventsTF") or [])}
    out: list[Activity] = []
    for r in data.get("resultsTF") or []:
        ev = events.get(r.get("EventID"))
        if not ev or (ev.get("Type") or "").upper() != "T":
            continue  # track running events only (Type "F" is field)
        meters = _event_meters(ev.get("Event") or "")
        if not meters or meters < _MIN_TRACK_M:
            continue
        sort_int = r.get("SortInt")
        if not isinstance(sort_int, (int, float)):
            continue
        secs = sort_int / 1000.0  # SortInt is time in milliseconds for track runs
        if not (0 < secs < _MAX_SECONDS):
            continue  # excludes DNS/DNF sentinels
        meet = meets.get(str(r.get("MeetID"))) or {}
        when = _an_date(r.get("ResultDate")) or _an_date(meet.get("EndDate"))
        if when is None:
            continue
        name = ev.get("Event") or "Track race"
        if meet.get("MeetName"):
            name += f" \u00b7 {meet['MeetName']}"
        out.append(
            Activity(
                start_date=when,
                distance_m=float(meters),
                moving_time_s=int(round(secs)),
                name=name,
                source="athletic.net",
                external_id=f"an-{r.get('IDResult')}",
            )
        )
    return out


def _an_results(athlete_id: str) -> list[Activity]:
    activities = _an_xc(athlete_id) + _an_tf(athlete_id)
    # Newest first is nicer if a caller ever displays them directly.
    activities.sort(key=lambda a: a.start_date)
    return activities


# ---------------------------------------------------------------------------
# Provider registry + public API
# ---------------------------------------------------------------------------

@dataclass
class _Provider:
    label: str
    search: Callable[[str], list[AthleteMatch]]
    results: Callable[[str], list[Activity]]


PROVIDERS: dict[str, _Provider] = {
    "athleticnet": _Provider("Athletic.net", _an_search, _an_results),
}


def search_athletes(
    name: str, city: str = "", state: str = ""
) -> list[AthleteMatch]:
    """Search every provider for athletes matching ``name``.

    When a home ``city`` / ``state`` is supplied (from the user's account), the
    matches are re-ranked so athletes from that location surface first and are
    flagged ``local`` - this makes it far easier to pick the right person when a
    name is common, so the imported meet times are actually yours.
    """
    name = (name or "").strip()
    if len(name) < 2:
        raise MeetImportError("Enter a name to search (at least 2 characters).")

    matches: list[AthleteMatch] = []
    errors: list[str] = []
    for prov in PROVIDERS.values():
        try:
            matches.extend(prov.search(name))
        except MeetImportError as e:
            errors.append(str(e))
    # Only surface an error if *every* provider failed; otherwise show results.
    if not matches and errors:
        raise MeetImportError(errors[0])

    want_state = _norm_state(state)
    want_city = (city or "").strip().lower()
    if want_state or want_city:
        def score(m: AthleteMatch) -> int:
            s = 0
            if want_state and _norm_state(m.state) == want_state:
                s += 2
            if want_city and m.city and m.city.strip().lower() == want_city:
                s += 3
            m.local = s > 0
            return s

        # Stable sort keeps each provider's relevance order within equal scores.
        matches.sort(key=score, reverse=True)
    return matches


def import_results(ref: str) -> list[Activity]:
    """Fetch all importable races for a ``provider:athlete_id`` reference."""
    provider_key, _, athlete_id = (ref or "").partition(":")
    prov = PROVIDERS.get(provider_key)
    if not prov or not athlete_id:
        raise MeetImportError("That athlete selection wasn't recognized.")
    return prov.results(athlete_id)

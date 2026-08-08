"""Import self-recorded runs: single manual entries, CSV files, or Strava exports."""
from __future__ import annotations

import csv
import io
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Optional

from .models import Activity, RACE_DISTANCES


def parse_duration(text: str) -> int:
    """Parse a duration into seconds.

    Accepts "mm:ss", "hh:mm:ss", or a plain number of seconds/minutes with a
    trailing unit (e.g. "45m", "90s", "1.5h").
    """
    text = str(text).strip().lower()
    if not text:
        raise ValueError("Empty duration")

    if text.endswith("h"):
        return int(float(text[:-1]) * 3600)
    if text.endswith("m") and ":" not in text:
        return int(float(text[:-1]) * 60)
    if text.endswith("s") and ":" not in text:
        return int(float(text[:-1]))

    if ":" in text:
        parts = [float(p) for p in text.split(":")]
        if len(parts) == 2:
            mins, secs = parts
            return int(mins * 60 + secs)
        if len(parts) == 3:
            hrs, mins, secs = parts
            return int(hrs * 3600 + mins * 60 + secs)
        raise ValueError(f"Cannot parse duration: {text!r}")

    # Bare number => assume seconds.
    return int(float(text))


def parse_distance(text: str) -> float:
    """Parse a distance into meters.

    Accepts race keywords (5k, 10k, half, marathon...), values with units
    ("10km", "5000m", "3.1mi"), or a bare number assumed to be kilometers.
    """
    text = str(text).strip().lower().replace(" ", "")
    if not text:
        raise ValueError("Empty distance")

    if text in RACE_DISTANCES:
        return RACE_DISTANCES[text]

    if text.endswith("km"):
        return float(text[:-2]) * 1000.0
    if text.endswith("mi"):
        return float(text[:-2]) * 1609.34
    if text.endswith("m"):
        return float(text[:-1])
    if text.endswith("k"):
        return float(text[:-1]) * 1000.0

    # Bare number => assume kilometers (most common for runners).
    return float(text) * 1000.0


def make_manual_activity(
    date_str: str,
    distance_str: str,
    duration_str: str,
    name: str = "Manual run",
    elevation_m: float = 0.0,
    average_hr: Optional[float] = None,
) -> Activity:
    start_dt = datetime.fromisoformat(date_str)
    return Activity(
        start_date=start_dt,
        distance_m=parse_distance(distance_str),
        moving_time_s=parse_duration(duration_str),
        name=name,
        elevation_gain_m=elevation_m,
        average_hr=average_hr,
        source="manual",
    )


def import_csv(path: str | Path) -> list[Activity]:
    """Import runs from a CSV.

    Required headers: date, distance, duration.
    Optional headers: name, elevation, hr (or avg_hr / heartrate).

    Example row:  2026-07-01, 10k, 45:30, Morning tempo, 40, 156
    """
    activities: list[Activity] = []
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        required = {"date", "distance", "duration"}
        if reader.fieldnames is None or not required.issubset({c.lower() for c in reader.fieldnames}):
            raise ValueError(
                "CSV must have at least these headers: date, distance, duration"
            )
        # Normalize field lookups to be case-insensitive.
        for row in reader:
            row = {k.lower().strip(): (v or "").strip() for k, v in row.items()}
            if not row.get("date"):
                continue
            hr_raw = row.get("hr") or row.get("avg_hr") or row.get("heartrate")
            activities.append(
                make_manual_activity(
                    date_str=row["date"],
                    distance_str=row["distance"],
                    duration_str=row["duration"],
                    name=row.get("name") or "Imported run",
                    elevation_m=float(row["elevation"]) if row.get("elevation") else 0.0,
                    average_hr=float(hr_raw) if hr_raw else None,
                )
            )
    return activities


# ---------------------------------------------------------------------------
# Strava bulk export
#
# Strava lets every user download a full archive of their data for free (no API
# subscription needed): Settings -> "Download or Delete Your Account" -> request
# archive. The archive is a .zip whose root contains `activities.csv`, a wide,
# somewhat messy file. Notably it has DUPLICATE column names (e.g. "Distance" in
# km early on and again in meters in the raw block, plus "Elapsed Time" twice),
# and headers/date formats vary by locale and export vintage. We parse defensively.
# ---------------------------------------------------------------------------

_STRAVA_DATE_FORMATS = (
    "%b %d, %Y, %I:%M:%S %p",   # Jul 1, 2024, 7:00:00 AM
    "%b %d, %Y, %H:%M:%S",      # Jul 1, 2024, 19:00:00
    "%d %b %Y, %H:%M:%S",       # 1 Jul 2024, 19:00:00
    "%Y-%m-%d %H:%M:%S",
    "%b %d, %Y",
)


def _strava_date(raw: str) -> Optional[datetime]:
    raw = (raw or "").strip()
    if not raw:
        return None
    for fmt in _STRAVA_DATE_FORMATS:
        try:
            return datetime.strptime(raw, fmt)
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(raw)
    except ValueError:
        return None


def _to_float(raw: Optional[str]) -> Optional[float]:
    """Parse a number that may use ',' as a decimal (EU) or thousands separator."""
    s = (raw or "").strip()
    if not s:
        return None
    if s.count(",") == 1 and s.count(".") == 0:
        s = s.replace(",", ".")  # decimal comma, e.g. "10,42"
    else:
        s = s.replace(",", "")   # thousands separators, e.g. "1,234.5"
    try:
        return float(s)
    except ValueError:
        return None


def _open_activities_csv(path: str | Path):
    """Return a text stream for activities.csv, whether given the .zip or the .csv."""
    p = str(path)
    if zipfile.is_zipfile(p):
        zf = zipfile.ZipFile(p)
        name = next(
            (n for n in zf.namelist() if n.lower().rstrip("/").endswith("activities.csv")),
            None,
        )
        if name is None:
            zf.close()
            raise ValueError(
                "Couldn't find activities.csv inside that Strava export .zip. "
                "Make sure you uploaded the archive Strava emailed you."
            )
        return io.TextIOWrapper(zf.open(name), encoding="utf-8-sig", newline="")
    return open(p, encoding="utf-8-sig", newline="")


def import_strava_export(path: str | Path) -> list[Activity]:
    """Import runs from a Strava bulk-export archive (.zip) or its activities.csv.

    Only activities whose type contains "Run" are imported. Each run keeps its
    Strava activity id as `external_id`, so re-importing (or later syncing) is
    idempotent - duplicates are skipped at the storage layer.
    """
    stream = _open_activities_csv(path)
    try:
        reader = csv.reader(stream)
        header = next(reader, None)
        if not header:
            raise ValueError("The activities.csv file is empty.")
        rows = list(reader)
    finally:
        stream.close()

    cols = [h.strip() for h in header]

    def indices(*names: str) -> list[int]:
        wanted = {n.lower() for n in names}
        return [i for i, h in enumerate(cols) if h.lower() in wanted]

    date_ix = indices("Activity Date", "Date")
    name_ix = indices("Activity Name", "Name")
    type_ix = indices("Activity Type", "Type")
    dist_ix = indices("Distance")
    moving_ix = indices("Moving Time")
    elapsed_ix = indices("Elapsed Time")
    hr_ix = indices("Average Heart Rate", "Average Heart Rate (bpm)")
    elev_ix = indices("Elevation Gain")
    id_ix = indices("Activity ID")

    def cell(row: list[str], ixs: list[int]) -> str:
        for i in ixs:
            if i < len(row) and row[i].strip():
                return row[i].strip()
        return ""

    activities: list[Activity] = []
    for row in rows:
        if not row:
            continue
        atype = cell(row, type_ix).lower()
        # Keep runs only (Run, Trail Run, Virtual Run, Treadmill...). If the export
        # has no type column at all, don't filter everything out.
        if type_ix and "run" not in atype:
            continue

        start = _strava_date(cell(row, date_ix))
        if start is None:
            continue

        # Distance: the CSV may carry km and/or meters. Take the largest parseable
        # value; treat >100 as already-meters, otherwise assume km.
        dist_vals = [v for v in (_to_float(row[i]) if i < len(row) else None for i in dist_ix) if v]
        if not dist_vals:
            continue
        dmax = max(dist_vals)
        distance_m = dmax if dmax > 100 else dmax * 1000.0

        moving = _to_float(cell(row, moving_ix)) or _to_float(cell(row, elapsed_ix))
        if not moving or moving <= 0:
            continue

        activities.append(
            Activity(
                start_date=start,
                distance_m=distance_m,
                moving_time_s=int(moving),
                name=cell(row, name_ix) or "Strava run",
                elevation_gain_m=_to_float(cell(row, elev_ix)) or 0.0,
                average_hr=_to_float(cell(row, hr_ix)),
                source="strava",
                external_id=cell(row, id_ix) or None,
            )
        )
    return activities

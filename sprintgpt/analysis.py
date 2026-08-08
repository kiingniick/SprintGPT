"""Running analytics: VDOT fitness, training paces, load trends, progress.

The VDOT model follows Jack Daniels & Jimmy Gilbert's equations, which relate a
race performance to an estimate of running economy / VO2max ("VDOT") and, from
there, to training paces.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Optional

from .models import Activity, Profile

# Five-zone heart-rate model: (label, low fraction, high fraction, purpose).
HR_ZONES = [
    ("Z1", "Recovery", 0.50, 0.60),
    ("Z2", "Aerobic / Easy", 0.60, 0.70),
    ("Z3", "Tempo", 0.70, 0.80),
    ("Z4", "Threshold", 0.80, 0.90),
    ("Z5", "VO2max", 0.90, 1.01),
]

# Fractions of VDOT (%VO2max) that define each training zone.
INTENSITY = {
    "easy": 0.70,
    "marathon": 0.84,
    "threshold": 0.88,
    "interval": 0.98,
    "repetition": 1.06,
}


def vo2_from_velocity(v_m_per_min: float) -> float:
    """Oxygen cost (ml/kg/min) of running at a given velocity."""
    return -4.60 + 0.182258 * v_m_per_min + 0.000104 * v_m_per_min ** 2


def pct_vo2max_at_time(minutes: float) -> float:
    """Fraction of VO2max sustainable for a race lasting `minutes`."""
    return (
        0.8
        + 0.1894393 * math.exp(-0.012778 * minutes)
        + 0.2989558 * math.exp(-0.1932605 * minutes)
    )


def vdot_from_performance(distance_m: float, time_s: float) -> float:
    """Estimate VDOT from a race/time-trial performance."""
    if distance_m <= 0 or time_s <= 0:
        return 0.0
    minutes = time_s / 60.0
    velocity = distance_m / minutes  # m/min
    vo2 = vo2_from_velocity(velocity)
    pct = pct_vo2max_at_time(minutes)
    return vo2 / pct


# Elite human VDOT tops out in the mid-80s, so any "effort" implying more than
# this is a GPS glitch or corrupt import, not a run worth learning from.
MAX_PLAUSIBLE_VDOT = 85.0
# Fastest credible *sustained* running speed (~2:23/km). Over a real running
# distance, anything quicker is bad data (dropped-signal splits, unit errors).
MAX_RUNNING_SPEED_MS = 7.0


def plausible_effort(distance_m: float, time_s: float, min_distance_m: float = 1500.0) -> bool:
    """True if (distance, time) looks like a genuine effort worth using to judge
    fitness — filtering GPS glitches, corrupt imports, and short sprints that
    would otherwise inflate VDOT and make race predictions wildly optimistic.
    """
    if distance_m < min_distance_m or time_s <= 0:
        return False
    if distance_m / time_s > MAX_RUNNING_SPEED_MS:
        return False
    return 0.0 < vdot_from_performance(distance_m, time_s) <= MAX_PLAUSIBLE_VDOT


def velocity_for_vo2(target_vo2: float) -> float:
    """Invert the VO2 cost curve: velocity (m/min) for a given oxygen cost."""
    a, b, c = 0.000104, 0.182258, -4.60 - target_vo2
    disc = b * b - 4 * a * c
    if disc < 0:
        return 0.0
    return (-b + math.sqrt(disc)) / (2 * a)


def training_paces(vdot: float) -> dict[str, float]:
    """Return training paces (seconds per km) for each zone given a VDOT."""
    paces: dict[str, float] = {}
    for zone, intensity in INTENSITY.items():
        target_vo2 = intensity * vdot
        v = velocity_for_vo2(target_vo2)  # m/min
        if v <= 0:
            paces[zone] = 0.0
            continue
        paces[zone] = 1000.0 / v * 60.0  # sec per km
    return paces


def predict_time(vdot: float, distance_m: float) -> float:
    """Predict a race time (seconds) at `distance_m` for a given VDOT.

    Solved by finding the duration whose implied VO2 demand matches the VDOT.
    """
    if vdot <= 0 or distance_m <= 0:
        return 0.0
    # Binary search on time; the mapping is monotonic.
    lo, hi = 60.0, 6 * 3600.0
    for _ in range(60):
        mid = (lo + hi) / 2
        velocity = distance_m / (mid / 60.0)
        implied_vdot = vo2_from_velocity(velocity) / pct_vo2max_at_time(mid / 60.0)
        if implied_vdot > vdot:
            # Too fast for this fitness -> needs more time.
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


MILE_M = 1609.34
KM_M = 1000.0


@dataclass
class Split:
    index: int
    label: str            # "1", "2", ... or "0.34" for a partial final segment
    segment_m: float
    split_s: float        # time for this segment
    cumulative_s: float   # elapsed time at the end of this segment
    pace_s_per_km: float
    partial: bool = False


def compute_splits(distance_m: float, total_time_s: float, unit: str = "mi") -> list[Split]:
    """Break a single total time over a distance into exact even splits.

    `unit` is "mi" or "km". Assumes an even effort, so every full split shares
    the same pace and the final partial segment is scaled to its distance.
    """
    if distance_m <= 0 or total_time_s <= 0:
        return []
    unit_m = MILE_M if unit == "mi" else KM_M
    pace_per_m = total_time_s / distance_m
    pace_per_km = pace_per_m * 1000.0

    splits: list[Split] = []
    full = int(distance_m // unit_m)
    cumulative = 0.0
    for i in range(1, full + 1):
        seg_time = pace_per_m * unit_m
        cumulative += seg_time
        splits.append(Split(i, str(i), unit_m, seg_time, cumulative, pace_per_km))

    remainder = distance_m - full * unit_m
    if remainder > 1.0:  # ignore sub-meter rounding dust
        seg_time = pace_per_m * remainder
        cumulative += seg_time
        splits.append(
            Split(full + 1, f"{remainder / unit_m:.2f}", remainder, seg_time,
                  cumulative, pace_per_km, partial=True)
        )
    return splits


@dataclass
class HRZone:
    key: str          # Z1..Z5
    name: str         # Recovery, Aerobic, ...
    low_bpm: int
    high_bpm: int
    minutes: float = 0.0  # time spent in this zone (filled by zone_distribution)


def hr_zone_bounds(profile: Profile) -> list[HRZone]:
    """Compute bpm boundaries for each zone.

    Uses heart-rate reserve (Karvonen) if a resting HR is known, else %HRmax.
    """
    zones: list[HRZone] = []
    for key, name, lo, hi in HR_ZONES:
        if profile.resting_hr:
            reserve = profile.max_hr - profile.resting_hr
            low_bpm = profile.resting_hr + lo * reserve
            high_bpm = profile.resting_hr + hi * reserve
        else:
            low_bpm = lo * profile.max_hr
            high_bpm = hi * profile.max_hr
        zones.append(HRZone(key, name, int(round(low_bpm)), int(round(high_bpm))))
    return zones


def classify_hr(bpm: float, profile: Profile) -> int:
    """Return the zone index (0-4) for a given average heart rate."""
    if profile.resting_hr:
        reserve = max(1, profile.max_hr - profile.resting_hr)
        frac = (bpm - profile.resting_hr) / reserve
    else:
        frac = bpm / profile.max_hr
    for i, (_, _, lo, hi) in enumerate(HR_ZONES):
        if frac < hi:
            return i
    return len(HR_ZONES) - 1


def _norm_cdf(x: float, mu: float, sigma: float) -> float:
    return 0.5 * (1.0 + math.erf((x - mu) / (sigma * math.sqrt(2.0))))


def zone_fractions(avg_hr: float, profile: Profile, spread_bpm: float = 8.0) -> list[float]:
    """Estimate the fraction of a run spent in each HR zone from its average HR.

    A run rarely sits at a single heart rate, so we model beat-by-beat HR as a
    normal distribution centered on the average with a modest spread, and
    integrate it over each zone's bpm band. This yields a realistic per-run
    breakdown even when only the average is known.
    """
    zones = hr_zone_bounds(profile)
    fracs: list[float] = []
    for i, z in enumerate(zones):
        lo = -math.inf if i == 0 else float(z.low_bpm)
        hi = math.inf if i == len(zones) - 1 else float(z.high_bpm)
        f = _norm_cdf(hi, avg_hr, spread_bpm) - _norm_cdf(lo, avg_hr, spread_bpm)
        fracs.append(max(0.0, f))
    total = sum(fracs) or 1.0
    return [f / total for f in fracs]


def activity_zone_breakdown(activity: Activity, profile: Profile) -> list[HRZone]:
    """Per-run time-in-zone breakdown (minutes) using the distribution model."""
    zones = hr_zone_bounds(profile)
    if activity.average_hr and activity.moving_time_s > 0:
        minutes = activity.moving_time_s / 60.0
        for z, frac in zip(zones, zone_fractions(activity.average_hr, profile)):
            z.minutes = round(frac * minutes, 1)
    return zones


def trimp(duration_min: float, avg_hr: float, profile: Profile) -> float:
    """Banister TRIMP training-load score using heart-rate reserve.

    More physiologically accurate than pace-based load when HR is available.
    """
    if not profile.resting_hr or profile.max_hr <= profile.resting_hr:
        return 0.0
    hrr = (avg_hr - profile.resting_hr) / (profile.max_hr - profile.resting_hr)
    hrr = max(0.0, min(1.0, hrr))
    coef = 1.67 if profile.sex == "f" else 1.92
    factor = 0.86 if profile.sex == "f" else 0.64
    return duration_min * hrr * factor * math.exp(coef * hrr)


def zone_distribution(activities: list[Activity], profile: Profile) -> list[HRZone]:
    """Aggregate time (minutes) spent in each HR zone across all activities.

    Sums the per-run distribution-model breakdowns for a smoother, more
    realistic picture than hard-classifying each run into a single zone.
    """
    zones = hr_zone_bounds(profile)
    for a in activities:
        if a.average_hr and a.moving_time_s > 0:
            minutes = a.moving_time_s / 60.0
            for z, frac in zip(zones, zone_fractions(a.average_hr, profile)):
                z.minutes += frac * minutes
    for z in zones:
        z.minutes = round(z.minutes, 1)
    return zones


def total_elevation_gain(activities: list[Activity]) -> float:
    """Total climbing (meters) across activities."""
    return round(sum(a.elevation_gain_m or 0.0 for a in activities), 0)


@dataclass
class FitnessState:
    ctl: float  # chronic training load (fitness), ~42-day average
    atl: float  # acute training load (fatigue), ~7-day average
    tsb: float  # training stress balance (form) = ctl - atl
    weekly_km: float
    best_vdot: float
    recent_vdot: float


def _training_load(activity: Activity, profile: Optional[Profile] = None) -> float:
    """A load score for one run.

    Prefers heart-rate-based TRIMP when HR and a profile are available (most
    accurate), and otherwise falls back to distance scaled by relative intensity
    (pace vs. an easy baseline) so a hard 5k counts more than a slow 5k.
    """
    km = activity.distance_km
    if km <= 0 or activity.moving_time_s <= 0:
        return 0.0
    if profile is not None and activity.average_hr:
        score = trimp(activity.moving_time_s / 60.0, activity.average_hr, profile)
        if score > 0:
            return score
    speed = activity.speed_ms
    # Baseline easy speed ~2.8 m/s (~6:00/km); ratio drives intensity multiplier.
    intensity = max(0.5, min(2.5, speed / 2.8))
    return km * 10.0 * intensity


def compute_fitness(
    activities: list[Activity],
    as_of: Optional[date] = None,
    profile: Optional[Profile] = None,
) -> FitnessState:
    """Compute CTL/ATL/TSB, weekly volume, and VDOT estimates."""
    as_of = as_of or date.today()
    ctl_tc, atl_tc = 42.0, 7.0
    ctl, atl = 0.0, 0.0

    daily_load: dict[date, float] = {}
    for a in activities:
        d = a.start_date.date()
        daily_load[d] = daily_load.get(d, 0.0) + _training_load(a, profile)

    if daily_load:
        start = min(daily_load)
        day = start
        while day <= as_of:
            load = daily_load.get(day, 0.0)
            ctl += (load - ctl) / ctl_tc
            atl += (load - atl) / atl_tc
            day += timedelta(days=1)

    # Weekly volume over the last 7 days.
    week_ago = as_of - timedelta(days=7)
    weekly_km = sum(
        a.distance_km for a in activities if week_ago <= a.start_date.date() <= as_of
    )

    # VDOT from best and recent efforts (outlier-guarded so one corrupt run or
    # GPS glitch can't blow the fitness score up to an impossible number).
    best_vdot = 0.0
    for a in activities:
        if plausible_effort(a.distance_m, a.moving_time_s):
            best_vdot = max(best_vdot, vdot_from_performance(a.distance_m, a.moving_time_s))

    recent_cut = as_of - timedelta(days=42)
    recent_efforts = [
        vdot_from_performance(a.distance_m, a.moving_time_s)
        for a in activities
        if a.start_date.date() >= recent_cut and plausible_effort(a.distance_m, a.moving_time_s)
    ]
    recent_vdot = max(recent_efforts) if recent_efforts else best_vdot

    return FitnessState(
        ctl=round(ctl, 1),
        atl=round(atl, 1),
        tsb=round(ctl - atl, 1),
        weekly_km=round(weekly_km, 1),
        best_vdot=round(best_vdot, 1),
        recent_vdot=round(recent_vdot, 1),
    )


def weekly_volume_series(activities: list[Activity], weeks: int = 12) -> list[tuple[date, float]]:
    """Return (week_start, km) tuples for the last `weeks` weeks."""
    if not activities:
        return []
    today = date.today()
    this_week_start = today - timedelta(days=today.weekday())
    series: list[tuple[date, float]] = []
    for i in range(weeks - 1, -1, -1):
        wk_start = this_week_start - timedelta(weeks=i)
        wk_end = wk_start + timedelta(days=6)
        km = sum(
            a.distance_km for a in activities if wk_start <= a.start_date.date() <= wk_end
        )
        series.append((wk_start, round(km, 1)))
    return series


def format_pace(sec_per_km: float) -> str:
    if sec_per_km <= 0:
        return "-"
    m = int(sec_per_km // 60)
    s = int(round(sec_per_km % 60))
    if s == 60:
        m, s = m + 1, 0
    return f"{m}:{s:02d}/km"


def format_time(seconds: float) -> str:
    seconds = int(round(seconds))
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"

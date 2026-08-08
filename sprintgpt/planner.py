"""Generate periodized, personalized training plans.

The planner adapts to *your* data: it starts from your current weekly volume and
VDOT-derived paces, applies progressive overload with recovery weeks, and
periodizes the season into Base -> Build -> Peak -> Taper. Quality sessions are
chosen to suit both the training phase and your goal race distance.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Optional

from .analysis import FitnessState, format_pace, training_paces
from .models import RACE_DISTANCES, Goal, WeeklyPlan, Workout

# Days of the week we schedule quality/long sessions on (Mon=0 ... Sun=6).
LONG_RUN_DAY = 5  # Saturday
QUALITY_DAY_1 = 1  # Tuesday
QUALITY_DAY_2 = 3  # Thursday


@dataclass
class PlanContext:
    fitness: FitnessState
    goal: Goal
    days_per_week: int = 5
    start_volume_km: float = 0.0


def _phase_for_week(week_index: int, total_weeks: int) -> str:
    """Split the season into base/build/peak/taper blocks."""
    if total_weeks <= 3:
        return "taper" if week_index == total_weeks - 1 else "build"
    taper_weeks = 1 if total_weeks < 8 else 2
    remaining = total_weeks - taper_weeks
    base_end = round(remaining * 0.4)
    build_end = round(remaining * 0.8)
    if week_index >= total_weeks - taper_weeks:
        return "taper"
    if week_index < base_end:
        return "base"
    if week_index < build_end:
        return "build"
    return "peak"


def _is_race_distance(distance_m: float) -> str:
    """Classify a goal distance into a coarse bucket for session selection."""
    if distance_m <= 5200:
        return "5k"
    if distance_m <= 12000:
        return "10k"
    if distance_m <= 25000:
        return "half"
    return "marathon"


def _quality_session(
    day: date, phase: str, race_bucket: str, paces: dict[str, float], week_index: int
) -> Workout:
    """Pick the primary quality workout for the week."""
    th = paces["threshold"]
    iv = paces["interval"]
    rep = paces["repetition"]

    if phase == "base":
        reps = 4 + (week_index % 3)
        return Workout(
            day=day,
            kind="repetition",
            description=f"Strides + {reps} x 200m fast @ {format_pace(rep)} "
            f"(easy jog recovery). Builds efficiency.",
            distance_m=6000,
            target_pace_s_per_km=rep,
        )

    if phase == "build":
        if race_bucket in ("5k", "10k"):
            reps = 5 + (week_index % 3)
            return Workout(
                day=day,
                kind="interval",
                description=f"{reps} x 800m @ {format_pace(iv)} w/ 2 min jog. VO2max work.",
                distance_m=3000 + reps * 800,
                target_pace_s_per_km=iv,
            )
        minutes = 20 + (week_index % 3) * 5
        return Workout(
            day=day,
            kind="tempo",
            description=f"{minutes} min tempo @ {format_pace(th)} (threshold). "
            f"Raises lactate threshold.",
            distance_m=int(minutes * 60 / th * 1000) + 4000,
            target_pace_s_per_km=th,
        )

    if phase == "peak":
        if race_bucket in ("5k", "10k"):
            reps = 4 + (week_index % 2)
            return Workout(
                day=day,
                kind="interval",
                description=f"{reps} x 1000m @ {format_pace(iv)} w/ 3 min jog. "
                f"Race-specific VO2max.",
                distance_m=4000 + reps * 1000,
                target_pace_s_per_km=iv,
            )
        return Workout(
            day=day,
            kind="tempo",
            description=f"2 x 15 min @ {format_pace(th)} w/ 3 min float. "
            f"Race-pace threshold.",
            distance_m=int(30 * 60 / th * 1000) + 4000,
            target_pace_s_per_km=th,
        )

    # taper
    return Workout(
        day=day,
        kind="interval",
        description=f"Sharpener: 4 x 400m @ {format_pace(iv)} w/ full recovery. Stay crisp.",
        distance_m=4000,
        target_pace_s_per_km=iv,
    )


def _secondary_quality(
    day: date, phase: str, race_bucket: str, paces: dict[str, float]
) -> Optional[Workout]:
    """An optional second quality session for higher-volume phases."""
    if phase in ("base", "taper"):
        return None
    mp = paces["marathon"]
    th = paces["threshold"]
    if race_bucket == "marathon":
        return Workout(
            day=day,
            kind="tempo",
            description=f"Steady 20 min @ {format_pace(mp)} (marathon pace) inside an easy run.",
            distance_m=int(20 * 60 / mp * 1000) + 3000,
            target_pace_s_per_km=mp,
        )
    return Workout(
        day=day,
        kind="tempo",
        description=f"Cruise intervals: 3 x 6 min @ {format_pace(th)} w/ 90s jog.",
        distance_m=int(18 * 60 / th * 1000) + 3000,
        target_pace_s_per_km=th,
    )


def generate_plan(ctx: PlanContext) -> list[WeeklyPlan]:
    """Build the full week-by-week plan from now until race week."""
    fitness = ctx.fitness
    goal = ctx.goal
    paces = training_paces(fitness.recent_vdot or fitness.best_vdot or 45.0)
    race_bucket = _is_race_distance(goal.distance_m)

    today = date.today()
    start = today - timedelta(days=today.weekday())  # this Monday
    race_week_start = goal.race_date - timedelta(days=goal.race_date.weekday())
    total_weeks = max(1, ((race_week_start - start).days // 7) + 1)
    total_weeks = min(total_weeks, 30)  # cap absurdly long horizons

    # Starting volume: current weekly km, floored to something sensible.
    base_km = ctx.start_volume_km or fitness.weekly_km or 20.0
    base_km = max(base_km, 15.0)
    peak_km = base_km * 1.5  # target peak volume

    plans: list[WeeklyPlan] = []
    for wk in range(total_weeks):
        phase = _phase_for_week(wk, total_weeks)
        wk_start = start + timedelta(weeks=wk)

        # Progressive overload with a recovery cutback every 4th week.
        progress = wk / max(1, total_weeks - 1)
        target_km = base_km + (peak_km - base_km) * min(1.0, progress * 1.4)
        if phase == "taper":
            taper_factor = 0.6 if wk == total_weeks - 1 else 0.75
            target_km *= taper_factor
        elif (wk + 1) % 4 == 0 and phase != "peak":
            target_km *= 0.8  # down week for recovery

        plan = _build_week(wk, phase, wk_start, target_km, race_bucket, paces, goal)
        plans.append(plan)

    return plans


def _build_week(
    wk: int,
    phase: str,
    wk_start: date,
    target_km: float,
    race_bucket: str,
    paces: dict[str, float],
    goal: Goal,
) -> WeeklyPlan:
    easy = paces["easy"]
    workouts: list[Workout] = []

    quality = _quality_session(wk_start + timedelta(days=QUALITY_DAY_1), phase, race_bucket, paces, wk)
    workouts.append(quality)

    secondary = _secondary_quality(
        wk_start + timedelta(days=QUALITY_DAY_2), phase, race_bucket, paces
    )
    if secondary is not None:
        workouts.append(secondary)

    # Long run: a share of weekly volume, larger for longer goal races.
    long_share = {"5k": 0.30, "10k": 0.32, "half": 0.35, "marathon": 0.38}[race_bucket]
    long_km = min(target_km * long_share, 36.0)
    if phase == "taper":
        long_km *= 0.7
    workouts.append(
        Workout(
            day=wk_start + timedelta(days=LONG_RUN_DAY),
            kind="long",
            description=f"Long run @ {format_pace(easy)}. Aerobic endurance.",
            distance_m=long_km * 1000,
            target_pace_s_per_km=easy,
        )
    )

    # Fill remaining volume with easy runs on the other days.
    scheduled_km = sum(w.distance_m for w in workouts) / 1000.0
    remaining_km = max(0.0, target_km - scheduled_km)
    easy_days = [0, 2, 4]  # Mon, Wed, Fri
    per_easy = remaining_km / len(easy_days) if easy_days else 0.0
    for d in easy_days:
        if per_easy < 2:
            kind, desc = "rest", "Rest or 20-30 min cross-training / mobility."
            dist = 0.0
        else:
            kind, desc = "easy", f"Easy run @ {format_pace(easy)}. Conversational effort."
            dist = per_easy * 1000
        workouts.append(
            Workout(day=wk_start + timedelta(days=d), kind=kind, description=desc,
                    distance_m=dist, target_pace_s_per_km=easy if dist else None)
        )

    # Sunday: recovery/rest.
    workouts.append(
        Workout(day=wk_start + timedelta(days=6), kind="recovery",
                description=f"Recovery jog @ {format_pace(easy)} or full rest.",
                distance_m=min(6.0, target_km * 0.12) * 1000, target_pace_s_per_km=easy)
    )

    workouts.sort(key=lambda w: w.day)
    return WeeklyPlan(week_index=wk, phase=phase, start_day=wk_start, workouts=workouts)


def race_week_note(goal: Goal) -> str:
    return (
        f"Race week: {goal.race_name} on {goal.race_date:%A %b %d}. "
        f"Keep runs short and sharp, prioritize sleep, carbs, and hydration."
    )

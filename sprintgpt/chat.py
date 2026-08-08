"""Paceloop's built-in coach chatbot.

A privacy-friendly, offline coach: it answers questions by computing real numbers
from the signed-in athlete's own data (runs, fitness, heart-rate zones, paces,
predictions, goal, and plan). No external API or keys required, so every account
gets a useful assistant out of the box.
"""
from __future__ import annotations

import re
from datetime import date
from typing import Optional

from .analysis import (
    compute_fitness,
    format_pace,
    format_time,
    hr_zone_bounds,
    total_elevation_gain,
    training_paces,
    weekly_volume_series,
    zone_distribution,
)
from .importer import parse_distance
from .models import Activity, Goal, Profile
from .planner import PlanContext, generate_plan
from .predictor import PacePredictor

# Prompts we surface in the UI to help people get started.
SUGGESTIONS = [
    "How much have I run this week?",
    "How's my fitness?",
    "Predict my 5K time",
    "What pace should my easy runs be?",
    "How are my heart-rate zones?",
    "What should I do today?",
]

_RACE_LABELS = [("5k", "5K"), ("10k", "10K"), ("half", "Half marathon"), ("marathon", "Marathon")]


def _km(activities: list[Activity]) -> float:
    return sum(a.distance_km for a in activities)


def _predict(activities: list[Activity], key: str) -> tuple[str, str]:
    dist = parse_distance(key)
    p = PacePredictor().predict(activities, dist)
    pace = p.predicted_time_s / (dist / 1000.0) if dist else 0
    return format_time(p.predicted_time_s), format_pace(pace)


def _this_week_km(activities: list[Activity]) -> float:
    series = weekly_volume_series(activities, weeks=1)
    return series[-1][1] if series else 0.0


def _greeting(bot: str, has_data: bool) -> str:
    if not has_data:
        return (
            f"Hi! I'm {bot}, your running coach. I don't see any runs on your account yet — "
            "import your Strava history or add a run, and I'll break down your fitness, "
            "paces, heart-rate zones, and race predictions for you."
        )
    return (
        f"Hey! I'm {bot}. Ask me about your training — your weekly mileage, fitness and form, "
        "race predictions, target paces, heart-rate zones, or what to run today."
    )


def _help(bot: str) -> str:
    return (
        f"I'm {bot}, and I answer using your own running data. Try asking me:\n"
        "• \"How much have I run this week?\" or \"What's my total mileage?\"\n"
        "• \"How's my fitness / form?\"\n"
        "• \"Predict my 10K\" or \"How fast can I run a marathon?\"\n"
        "• \"What pace should my easy / tempo / interval runs be?\"\n"
        "• \"How are my heart-rate zones?\"\n"
        "• \"What should I do today?\" or \"Am I ready for my race?\""
    )


def _fitness_answer(fitness, activities) -> str:
    vdot = fitness.recent_vdot or fitness.best_vdot
    form = "fresh and ready" if fitness.tsb > 5 else "carrying fatigue" if fitness.tsb < -10 else "well balanced"
    lines = [
        f"Here's your current fitness snapshot:",
        f"• VDOT (fitness score): {vdot:.0f}" if vdot else "• VDOT: not enough data yet",
        f"• Fitness (CTL): {fitness.ctl:.0f}  •  Fatigue (ATL): {fitness.atl:.0f}",
        f"• Form (TSB): {fitness.tsb:+.0f} — you're {form}.",
        f"• Last 7 days: {fitness.weekly_km:.1f} km across {len(activities)} logged runs total.",
    ]
    return "\n".join(lines)


def _form_answer(fitness) -> str:
    if fitness.tsb > 5:
        advice = "You're fresh — a good window for a hard workout or a race."
    elif fitness.tsb < -10:
        advice = "You're fatigued — prioritize easy runs and recovery before your next hard session."
    else:
        advice = "You're balanced — fine to train normally; just listen to your body."
    return (
        f"Your form (TSB) is {fitness.tsb:+.0f} "
        f"(fitness {fitness.ctl:.0f} minus fatigue {fitness.atl:.0f}). {advice}"
    )


def _paces_answer(fitness, want: Optional[str]) -> str:
    vdot = fitness.recent_vdot or fitness.best_vdot
    if not vdot:
        return "I need a few timed runs before I can set your training paces. Add or import some runs first."
    paces = training_paces(vdot)
    label_map = {"easy": "easy", "marathon": "marathon", "threshold": "threshold/tempo",
                 "interval": "interval", "repetition": "repetition"}
    if want and want in paces:
        return f"Your {label_map.get(want, want)} pace is about {format_pace(paces[want])}."
    order = ["easy", "marathon", "threshold", "interval", "repetition"]
    lines = ["Based on a VDOT of {:.0f}, here are your target paces (per km):".format(vdot)]
    for k in order:
        if k in paces:
            lines.append(f"• {label_map.get(k, k).title()}: {format_pace(paces[k])}")
    return "\n".join(lines)


def _predictions_answer(activities, key: Optional[str]) -> str:
    keys = [key] if key else [k for k, _ in _RACE_LABELS]
    label_lookup = dict(_RACE_LABELS)
    lines = ["Here are your predicted race times (from your own runs):"]
    for k in keys:
        time_s, pace = _predict(activities, k)
        lines.append(f"• {label_lookup.get(k, k.upper())}: {time_s}  ({pace})")
    if key:
        time_s, pace = _predict(activities, key)
        return f"I predict you'd run a {label_lookup.get(key, key.upper())} in about {time_s} ({pace})."
    return "\n".join(lines)


def _zones_answer(activities, profile) -> str:
    zones = zone_distribution(activities, profile)
    total = sum(z.minutes for z in zones)
    if total <= 0:
        return ("I don't have heart-rate data on your runs yet. Add runs with an average HR "
                "(or set your max/resting HR in Settings) and I'll show your time in each zone.")
    lines = ["Your heart-rate zone distribution (tracked minutes):"]
    for z in zones:
        pct = (z.minutes / total * 100) if total else 0
        lines.append(f"• {z.key} {z.name} ({z.low_bpm}-{z.high_bpm} bpm): {z.minutes:.0f} min ({pct:.0f}%)")
    easy = sum(z.minutes for z in zones[:2])
    lines.append(f"\nAbout {easy / total * 100:.0f}% of your tracked time is easy (Z1-Z2) — "
                 f"{'nice aerobic base' if easy / total > 0.7 else 'consider adding more easy volume'}.")
    return "\n".join(lines)


def _today_answer(activities, profile, goal, bot: str) -> str:
    if goal is None:
        return ("Set a goal race first (on your dashboard) and I'll build a plan and tell you "
                "exactly what to run each day.")
    fitness = compute_fitness(activities, profile=profile) if activities else compute_fitness([])
    plans = generate_plan(PlanContext(fitness=fitness, goal=goal, start_volume_km=fitness.weekly_km))
    today = date.today()
    # Find the week that contains today (each weekly plan spans 7 days from start_day).
    current = None
    for wk in plans:
        if 0 <= (today - wk.start_day).days < 7:
            current = wk
            break
    if current is None:
        current = plans[0]
    # Today's specific workout, if any.
    todays = [w for w in current.workouts if w.day == today]
    lines = []
    if todays:
        w = todays[0]
        pace = f" @ {format_pace(w.target_pace_s_per_km)}" if w.target_pace_s_per_km else ""
        dist = f" — {w.distance_m/1000:.1f} km" if w.distance_m else ""
        lines.append(f"Today's session: {w.kind.title()}{dist}{pace}.\n{w.description}")
    else:
        lines.append("Nothing specific scheduled for today. Here's this week's outline:")
    lines.append(f"\nWeek {current.week_index + 1} ({current.phase} phase), "
                 f"~{current.total_distance_m/1000:.0f} km planned:")
    for w in current.workouts:
        if w.kind == "rest":
            continue
        pace = f" @ {format_pace(w.target_pace_s_per_km)}" if w.target_pace_s_per_km else ""
        dist = f" {w.distance_m/1000:.1f} km" if w.distance_m else ""
        lines.append(f"• {w.day.strftime('%a')}: {w.kind.title()}{dist}{pace}")
    return "\n".join(lines)


def _ready_answer(activities, profile, goal) -> str:
    if goal is None:
        return "You haven't set a goal race yet. Add one on your dashboard and I'll assess your readiness."
    days = (goal.race_date - date.today()).days
    when = f"in {days} days" if days > 0 else "today" if days == 0 else f"{-days} days ago"
    dist_key = _closest_race_key(goal.distance_m)
    pred_time, pred_pace = _predict(activities, dist_key) if activities else ("-", "-")
    lines = [f"Your goal: {goal.race_name} ({goal.distance_m/1000:.1f} km) {when}."]
    if activities:
        lines.append(f"Based on your training, I project about {pred_time} ({pred_pace}).")
        if goal.target_time_s:
            proj_s = PacePredictor().predict(activities, goal.distance_m).predicted_time_s
            gap = proj_s - goal.target_time_s
            if gap <= 0:
                lines.append(f"That's ahead of your {format_time(goal.target_time_s)} target — you're on track!")
            else:
                lines.append(f"Your target is {format_time(goal.target_time_s)}; you're about "
                             f"{format_time(abs(gap))} off. Keep building consistency.")
    else:
        lines.append("Import some runs and I'll project your finish time and readiness.")
    return "\n".join(lines)


def _closest_race_key(distance_m: float) -> str:
    best, bestd = "10k", 1e18
    for k, _ in _RACE_LABELS:
        d = abs(parse_distance(k) - distance_m)
        if d < bestd:
            best, bestd = k, d
    return best


def _last_run_answer(activities) -> str:
    a = activities[-1]
    hr = f", avg HR {a.average_hr:.0f} bpm" if a.average_hr else ""
    elev = f", {a.elevation_gain_m:.0f} m climb" if a.elevation_gain_m else ""
    return (f"Your last run was \"{a.name}\" on {a.start_date.strftime('%b %d')}: "
            f"{a.distance_km:.2f} km in {format_time(a.moving_time_s)} "
            f"({format_pace(a.pace_s_per_km)}){hr}{elev}.")


def _longest_run_answer(activities) -> str:
    a = max(activities, key=lambda x: x.distance_m)
    return (f"Your longest run is {a.distance_km:.2f} km — \"{a.name}\" on "
            f"{a.start_date.strftime('%b %d, %Y')} in {format_time(a.moving_time_s)} "
            f"({format_pace(a.pace_s_per_km)}).")


def build_reply(
    question: str,
    activities: list[Activity],
    profile: Profile,
    goal: Optional[Goal],
    bot_name: str = "Coach",
) -> str:
    """Return the coach's reply to a free-text question, grounded in the user's data."""
    q = (question or "").strip().lower()
    bot = bot_name or "Coach"
    has_data = bool(activities)

    if not q:
        return _help(bot)

    # Social / meta intents first.
    if re.search(r"\b(hi|hello|hey|yo|hiya|good (morning|afternoon|evening))\b", q):
        return _greeting(bot, has_data)
    if re.search(r"\b(thanks|thank you|thx|cheers|appreciate)\b", q):
        return "Anytime! Keep up the great work. Ask me anything else about your training."
    if re.search(r"\b(help|what can you do|commands|options)\b", q):
        return _help(bot)
    if re.search(r"\b(your name|who are you|what are you)\b", q):
        return (f"I'm {bot}, your Paceloop running coach. You can rename me anytime from the "
                "chat header — it's just cosmetic, I'll still know all your training data.")

    if not has_data:
        return (f"I'd love to help with that, but I don't see any runs on your account yet. "
                "Import your Strava history or add a run on the dashboard, then ask me again!")

    fitness = compute_fitness(activities, profile=profile)

    # Specific race distance requested?
    race_key = None
    if re.search(r"\b(marathon|42)\b", q) and "half" not in q:
        race_key = "marathon"
    elif re.search(r"\b(half|21)\b", q):
        race_key = "half"
    elif re.search(r"\b(10k|10 k|ten k)\b", q):
        race_key = "10k"
    elif re.search(r"\b(5k|5 k|five k|parkrun)\b", q):
        race_key = "5k"

    # Intent routing.
    if re.search(r"\b(ready|prepared|on track|can i (make|hit|achieve|break)|readiness)\b", q):
        return _ready_answer(activities, profile, goal)
    if re.search(r"\b(today|tomorrow|what should i (do|run)|workout|session|schedule|training plan)\b", q):
        return _today_answer(activities, profile, goal, bot)
    if re.search(r"\b(predict|prediction|race time|how fast|finish time|goal time)\b", q) or \
            (race_key and re.search(r"\b(time|predict|run|race)\b", q)):
        return _predictions_answer(activities, race_key)
    if re.search(r"\bpace(s)?\b|how fast should", q):
        want = None
        for key in ("easy", "marathon", "threshold", "tempo", "interval", "repetition"):
            if key in q:
                want = "threshold" if key == "tempo" else key
                break
        return _paces_answer(fitness, want)
    if re.search(r"\b(zone|heart[- ]?rate|hr|cardio)\b", q):
        return _zones_answer(activities, profile)
    if re.search(r"\b(form|tsb|fatigue|fresh|tired|recover|overtrain)\b", q):
        return _form_answer(fitness)
    if re.search(r"\b(fit|fitness|vdot|ctl|how am i doing|progress|shape)\b", q):
        return _fitness_answer(fitness, activities)
    if re.search(r"\b(longest|farthest|furthest|biggest run)\b", q):
        return _longest_run_answer(activities)
    if re.search(r"\b(last run|latest run|recent run|most recent)\b", q):
        return _last_run_answer(activities)
    if re.search(r"\b(elevation|climb|climbing|hills|ascent|vert)\b", q):
        return (f"You've climbed {total_elevation_gain(activities):.0f} m of elevation gain "
                f"across all your logged runs.")
    if re.search(r"\bthis week\b|weekly|this week'?s mileage", q):
        return f"You've run {_this_week_km(activities):.1f} km in the last 7 days."
    if re.search(r"\b(how many runs|number of runs|run count)\b", q):
        return f"You have {len(activities)} runs logged, totaling {_km(activities):.1f} km."
    if re.search(r"\b(total|lifetime|all[- ]?time|overall|how far have i)\b", q):
        return (f"All-time you've logged {len(activities)} runs for {_km(activities):.1f} km "
                f"and {total_elevation_gain(activities):.0f} m of climbing.")
    if re.search(r"\bweek\b", q):
        return f"You've run {_this_week_km(activities):.1f} km in the last 7 days."

    # Fallback: give a quick snapshot plus a nudge toward what I can answer.
    return (
        "I'm not totally sure what you're asking, but here's a quick snapshot:\n"
        f"• {len(activities)} runs, {_km(activities):.1f} km all-time\n"
        f"• Last 7 days: {fitness.weekly_km:.1f} km  •  Form (TSB): {fitness.tsb:+.0f}\n\n"
        "Try asking about your fitness, paces, heart-rate zones, race predictions, or today's workout."
    )

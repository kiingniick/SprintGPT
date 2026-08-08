"""Body metrics and strength-training guidance for runners.

Turns an athlete's physiology (`Profile`) plus their training volume and goal
race into a concrete, non-scary strength recommendation: how many sessions a
week, how long, what to focus on, and *why*. All logic here is deterministic so
the same inputs always yield the same advice.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from .models import Profile


# ---- unit conversions -------------------------------------------------------
_LB_PER_KG = 1.0 / 0.45359237
_IN_PER_CM = 1.0 / 2.54


def ft_in_to_cm(feet: float, inches: float) -> float:
    return (feet * 12.0 + inches) * 2.54


def lb_to_kg(pounds: float) -> float:
    return pounds * 0.45359237


@dataclass
class StrengthPlan:
    """A recommended weekly strength dose for a runner."""

    level: str              # e.g. "Foundational", "Performance", "Durability"
    sessions_per_week: int
    minutes_per_session: int
    focus: list[str] = field(default_factory=list)
    rationale: str = ""

    @property
    def summary(self) -> str:
        return f"{self.sessions_per_week}× / week · {self.minutes_per_session} min"


def strength_recommendation(
    profile: Optional[Profile],
    weekly_km: float,
    goal_distance_m: Optional[float] = None,
) -> StrengthPlan:
    """Recommend a weekly strength dose from volume, goal distance, and BMI.

    The base dose scales with running volume (more mileage → more resilience
    work, capped so it never competes with running). The *focus* is shaped by
    the goal distance and, when available, by BMI.
    """
    km = max(0.0, weekly_km or 0.0)

    # Base dose from weekly running volume.
    if km < 20:
        level = "Foundational"
        sessions, minutes = 2, 25
        base_focus = [
            "Bodyweight basics: squats, lunges, glute bridges, push-ups",
            "Core stability: planks, dead bugs, bird dogs",
            "Ankle & hip mobility to prep for more mileage",
        ]
        why = "You're building a base, so strength work is about durable movement patterns before piling on volume."
    elif km < 50:
        level = "Performance"
        sessions, minutes = 2, 35
        base_focus = [
            "Compound lifts: squats, deadlifts, step-ups (moderate load)",
            "Single-leg work: split squats, calf raises for running economy",
            "Core & hip strength: planks, side planks, hip thrusts",
        ]
        why = "At solid mileage, strength should sharpen running economy and protect against overuse."
    else:
        level = "Durability"
        sessions, minutes = 3, 30
        base_focus = [
            "Heavy, low-rep compound lifts (keep sessions short & crisp)",
            "Plyometrics: bounds, hops, box jumps for power",
            "Single-leg stability & posterior-chain work for injury resistance",
        ]
        why = "High volume demands resilient tissue — brief, heavy sessions add durability without draining your legs."

    # Goal-distance shaping.
    if goal_distance_m:
        if goal_distance_m <= 5000:
            base_focus.append("Explosive power: jumps and short sprints to boost top-end speed")
            why += " Your short-distance goal rewards power and turnover."
        elif goal_distance_m >= 30000:
            base_focus.append("Extra single-leg & core endurance to hold form late in long races")
            why += " Your long-distance goal makes fatigue-resistant form a priority."
        else:
            base_focus.append("Balanced strength + mobility to support tempo and threshold work")

    # BMI shaping (only if we have both height and weight).
    bmi = profile.bmi if profile else None
    if bmi is not None:
        if bmi >= 27:
            minutes = max(minutes, 30)
            base_focus.insert(0, "Start low-impact (machines, bands, bodyweight) and progress load gradually")
            why += " Building strength gradually protects your joints while impact load ramps up."
        elif bmi < 18.5:
            base_focus.append("Keep loads moderate and fuel well — strength here supports bone & tissue health")
            why += " Prioritize consistent fueling alongside strength to protect bone density."

    return StrengthPlan(
        level=level,
        sessions_per_week=sessions,
        minutes_per_session=minutes,
        focus=base_focus,
        rationale=why.strip(),
    )

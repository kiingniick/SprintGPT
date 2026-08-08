"""Core data models shared across the app."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Optional


@dataclass
class Activity:
    """A single run.

    Distances are stored in meters, durations in seconds, so all math is unit-safe.
    `source` is "strava" or "manual". `external_id` is the Strava activity id (if any)
    and is used to de-duplicate on re-sync.
    """

    start_date: datetime
    distance_m: float
    moving_time_s: int
    name: str = "Run"
    elevation_gain_m: float = 0.0
    average_hr: Optional[float] = None
    source: str = "manual"
    external_id: Optional[str] = None
    id: Optional[int] = None

    @property
    def distance_km(self) -> float:
        return self.distance_m / 1000.0

    @property
    def pace_s_per_km(self) -> float:
        if self.distance_m <= 0:
            return 0.0
        return self.moving_time_s / (self.distance_m / 1000.0)

    @property
    def speed_ms(self) -> float:
        if self.moving_time_s <= 0:
            return 0.0
        return self.distance_m / self.moving_time_s


@dataclass
class Profile:
    """Athlete profile used for heart-rate zone math and body metrics.

    `max_hr` and `resting_hr` drive zone boundaries. If `resting_hr` is set,
    zones use heart-rate reserve (Karvonen); otherwise plain %HRmax.

    `height_cm` and `weight_kg` are always stored metric; `units` only controls
    how those values are shown to and collected from the athlete ("imperial" or
    "metric").
    """

    max_hr: int = 190
    resting_hr: Optional[int] = None
    sex: str = "m"  # affects the TRIMP intensity coefficient
    height_cm: Optional[float] = None
    weight_kg: Optional[float] = None
    units: str = "imperial"

    @staticmethod
    def estimate_max_hr(age: int) -> int:
        # Tanaka formula: 208 - 0.7 * age (more accurate than 220 - age).
        return int(round(208 - 0.7 * age))

    @property
    def bmi(self) -> Optional[float]:
        """Body Mass Index (kg/m^2), or None if height/weight aren't set."""
        if not self.height_cm or not self.weight_kg or self.height_cm <= 0:
            return None
        m = self.height_cm / 100.0
        return round(self.weight_kg / (m * m), 1)

    @property
    def bmi_category(self) -> Optional[str]:
        b = self.bmi
        if b is None:
            return None
        if b < 18.5:
            return "Underweight"
        if b < 25:
            return "Healthy"
        if b < 30:
            return "Overweight"
        return "Obese"

    @property
    def height_ft_in(self) -> Optional[tuple[int, int]]:
        """Height as (feet, inches) for imperial display."""
        if not self.height_cm:
            return None
        total_in = self.height_cm / 2.54
        feet = int(total_in // 12)
        inches = int(round(total_in - feet * 12))
        if inches == 12:  # rounding rolled over
            feet, inches = feet + 1, 0
        return feet, inches

    @property
    def weight_lb(self) -> Optional[float]:
        if not self.weight_kg:
            return None
        return round(self.weight_kg / 0.45359237, 1)


@dataclass
class Goal:
    """A target race the plan is built around."""

    race_name: str
    race_date: date
    distance_m: float
    target_time_s: Optional[int] = None
    id: Optional[int] = None


# Canonical race distances in meters, used for predictions and goal parsing.
RACE_DISTANCES = {
    "1k": 1000.0,
    "1500": 1500.0,
    "mile": 1609.34,
    "3k": 3000.0,
    "5k": 5000.0,
    "10k": 10000.0,
    "15k": 15000.0,
    "10mile": 16093.4,
    "half": 21097.5,
    "marathon": 42195.0,
}


@dataclass
class Workout:
    """A single prescribed workout inside a plan."""

    day: date
    kind: str  # easy, long, tempo, interval, repetition, recovery, rest, race
    description: str
    distance_m: float = 0.0
    target_pace_s_per_km: Optional[float] = None

    def __post_init__(self) -> None:
        # Keep dataclass hashing/printing predictable.
        pass


@dataclass
class WeeklyPlan:
    week_index: int
    phase: str
    start_day: date
    workouts: list[Workout] = field(default_factory=list)

    @property
    def total_distance_m(self) -> float:
        return sum(w.distance_m for w in self.workouts)

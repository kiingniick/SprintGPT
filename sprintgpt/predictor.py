"""Race-time prediction.

Predictions are grounded in the athlete's *demonstrated* fitness and endurance,
and are deliberately conservative and progressive rather than projecting an
untrained physiological ceiling:

  * A robust "current potential" is taken from a high percentile of your genuine
    timed efforts (not a single fluke split, downhill, or corrupt GPS record),
    so one bad data point can't make every prediction absurdly fast.
  * That potential is projected to the target distance with Riegel's endurance
    law, using an exponent that *grows* the further the race is beyond the
    longest run you've actually done. This models the real-world fade of racing
    a distance you haven't yet built the endurance for, instead of assuming you
    could hold near-threshold pace for a marathon off a fast 5K.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from .analysis import (
    MAX_RUNNING_SPEED_MS,
    plausible_effort,
    vdot_from_performance,
)
from .models import Activity

# Riegel exponent for a well-trained runner racing near a distance they train
# for. It climbs for extrapolation well beyond the athlete's longest run.
RIEGEL_EXPONENT = 1.06
# How aggressively the exponent grows per doubling of distance past the longest
# run, and the ceiling on that growth.
ENDURANCE_FADE_SLOPE = 0.08
ENDURANCE_FADE_CAP = 0.16
# Enough timed runs to call a model "trained" (drives dashboard messaging).
MIN_SAMPLES_FOR_ML = 12


@dataclass
class Prediction:
    distance_m: float
    predicted_time_s: float
    method: str  # "riegel", "vdot", or "none"
    confidence: str  # low / medium / high


def riegel_predict(
    known_distance_m: float,
    known_time_s: float,
    target_distance_m: float,
    exponent: float = RIEGEL_EXPONENT,
) -> float:
    if known_distance_m <= 0 or known_time_s <= 0:
        return 0.0
    return known_time_s * (target_distance_m / known_distance_m) ** exponent


def _percentile(sorted_vals: list[float], pct: float) -> float:
    """Linear-interpolated percentile of an already-sorted list."""
    if not sorted_vals:
        return 0.0
    if len(sorted_vals) == 1:
        return sorted_vals[0]
    k = (len(sorted_vals) - 1) * (pct / 100.0)
    lo = int(math.floor(k))
    hi = int(math.ceil(k))
    if lo == hi:
        return sorted_vals[lo]
    return sorted_vals[lo] + (sorted_vals[hi] - sorted_vals[lo]) * (k - lo)


class PacePredictor:
    """Predicts finish time for an arbitrary distance from your history."""

    def __init__(self) -> None:
        self._trained = False
        self._samples = 0

    def train(self, activities: list[Activity]) -> bool:
        """Record how much timed data we have. Returns True once there's enough
        to make confident predictions (kept for dashboard messaging)."""
        runs = [a for a in activities if a.distance_m >= 1000 and a.moving_time_s > 0]
        self._samples = len(runs)
        self._trained = self._samples >= MIN_SAMPLES_FOR_ML
        return self._trained

    def _endurance_exponent(self, target_distance_m: float, longest_run_m: float) -> float:
        """Riegel exponent that grows as the target outruns your longest run."""
        if target_distance_m <= longest_run_m or longest_run_m <= 0:
            return RIEGEL_EXPONENT
        overshoot = target_distance_m / longest_run_m
        fade = min(ENDURANCE_FADE_CAP, ENDURANCE_FADE_SLOPE * math.log2(overshoot))
        return RIEGEL_EXPONENT + fade

    def predict(self, activities: list[Activity], target_distance_m: float) -> Prediction:
        if target_distance_m <= 0:
            return Prediction(target_distance_m, 0.0, "none", "low")

        runs = [a for a in activities if a.moving_time_s > 0 and a.distance_m > 0]
        # Genuine timed efforts used to gauge current speed (glitches filtered).
        efforts = [a for a in runs if plausible_effort(a.distance_m, a.moving_time_s)]
        if not efforts:
            return Prediction(target_distance_m, 0.0, "none", "low")

        vdots = sorted(vdot_from_performance(a.distance_m, a.moving_time_s) for a in efforts)
        # Robust "current potential": a high percentile, not the single best, so a
        # lone downhill/short/fluke effort can't dominate every prediction.
        ref_vdot = _percentile(vdots, 88) if len(vdots) >= 5 else vdots[-1]

        # Anchor Riegel at the real effort closest to that potential.
        anchor = min(
            efforts,
            key=lambda a: abs(vdot_from_performance(a.distance_m, a.moving_time_s) - ref_vdot),
        )
        d_ref, t_ref = anchor.distance_m, anchor.moving_time_s

        # Endurance ceiling: the longest genuine run (drop distance glitches by
        # rejecting impossible speeds, but allow slow long runs to count).
        sane = [a for a in runs if a.distance_m / a.moving_time_s <= MAX_RUNNING_SPEED_MS]
        longest = max((a.distance_m for a in sane), default=d_ref)

        exponent = self._endurance_exponent(target_distance_m, longest)
        predicted = riegel_predict(d_ref, t_ref, target_distance_m, exponent)

        # Confidence from data volume and how far we're extrapolating past what
        # the athlete has actually run.
        n = len(efforts)
        extrap = target_distance_m / longest if longest > 0 else 99.0
        if extrap > 1.5 or n < 5:
            conf = "low"
        elif extrap > 1.1 or n < 15:
            conf = "medium"
        else:
            conf = "high"

        method = "riegel" if target_distance_m > longest else "vdot"
        return Prediction(target_distance_m, predicted, method, conf)

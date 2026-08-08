"""Race-time prediction.

Two engines:
  * A machine-learning model (gradient-boosted trees) trained on your own runs,
    which learns how *your* pace scales with distance, elevation and recent
    training volume.
  * A physiology fallback (Riegel endurance formula + VDOT) used when you don't
    yet have enough data to train a trustworthy model.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Optional

import numpy as np

from .analysis import predict_time as vdot_predict, vdot_from_performance
from .models import Activity

# Riegel exponent: empirically ~1.06 for trained runners.
RIEGEL_EXPONENT = 1.06
MIN_SAMPLES_FOR_ML = 12


@dataclass
class Prediction:
    distance_m: float
    predicted_time_s: float
    method: str  # "ml", "riegel", or "vdot"
    confidence: str  # low / medium / high


def riegel_predict(known_distance_m: float, known_time_s: float, target_distance_m: float) -> float:
    if known_distance_m <= 0 or known_time_s <= 0:
        return 0.0
    return known_time_s * (target_distance_m / known_distance_m) ** RIEGEL_EXPONENT


class PacePredictor:
    """Predicts finish time for an arbitrary distance from your history."""

    def __init__(self) -> None:
        self.model = None
        self._trained_samples = 0

    def _features(self, activity: Activity, recent_volume_km: float) -> list[float]:
        return [
            activity.distance_m,
            activity.distance_m ** 0.5,
            activity.elevation_gain_m,
            recent_volume_km,
        ]

    def train(self, activities: list[Activity]) -> bool:
        """Fit the ML model. Returns True if a model was trained."""
        runs = [a for a in activities if a.distance_m >= 1000 and a.moving_time_s > 0]
        if len(runs) < MIN_SAMPLES_FOR_ML:
            self.model = None
            return False

        try:
            from sklearn.ensemble import GradientBoostingRegressor
        except ImportError:
            self.model = None
            return False

        runs.sort(key=lambda a: a.start_date)
        X, y = [], []
        for a in runs:
            window_start = a.start_date - timedelta(days=28)
            recent_volume = sum(
                r.distance_km
                for r in runs
                if window_start <= r.start_date < a.start_date
            )
            X.append(self._features(a, recent_volume))
            y.append(a.moving_time_s)

        model = GradientBoostingRegressor(
            n_estimators=200, max_depth=3, learning_rate=0.05, random_state=42
        )
        model.fit(np.array(X), np.array(y))
        self.model = model
        self._trained_samples = len(runs)
        self._max_train_distance = max(a.distance_m for a in runs)
        self._recent_volume = sum(
            a.distance_km
            for a in runs
            if a.start_date >= runs[-1].start_date - timedelta(days=28)
        )
        return True

    def predict(self, activities: list[Activity], target_distance_m: float) -> Prediction:
        runs = [a for a in activities if a.distance_m >= 1000 and a.moving_time_s > 0]

        if self.model is not None:
            recent_volume = getattr(self, "_recent_volume", 0.0)
            max_train = getattr(self, "_max_train_distance", target_distance_m)
            best_vdot = max(
                (vdot_from_performance(a.distance_m, a.moving_time_s) for a in runs),
                default=0.0,
            )
            vdot_time = vdot_predict(best_vdot, target_distance_m) if best_vdot else 0.0

            # Trees cannot extrapolate: beyond the longest run we've seen, lean on
            # the physiology model, anchored via Riegel to our best real effort.
            if target_distance_m > max_train * 1.05 and best_vdot > 0:
                # How far past the trained range are we (1.0 = right at the edge)?
                overshoot = target_distance_m / max_train
                w_ml = max(0.0, min(0.5, 0.5 / overshoot))
                ml_at_edge = float(self.model.predict(np.array([[
                    max_train, max_train ** 0.5, 0.0, recent_volume]]))[0])
                riegel = riegel_predict(max_train, ml_at_edge, target_distance_m)
                pred = w_ml * riegel + (1.0 - w_ml) * vdot_time
                conf = "low"
            else:
                pred = float(self.model.predict(np.array([[
                    target_distance_m, target_distance_m ** 0.5, 0.0, recent_volume]]))[0])
                if vdot_time > 0:
                    pred = 0.6 * pred + 0.4 * vdot_time
                conf = "high" if self._trained_samples >= 25 else "medium"
            return Prediction(target_distance_m, pred, "ml", conf)

        # Fallback 1: VDOT from best effort.
        best = max(
            runs,
            key=lambda a: vdot_from_performance(a.distance_m, a.moving_time_s),
            default=None,
        )
        if best is not None:
            vdot = vdot_from_performance(best.distance_m, best.moving_time_s)
            return Prediction(
                target_distance_m, vdot_predict(vdot, target_distance_m), "vdot", "low"
            )

        return Prediction(target_distance_m, 0.0, "riegel", "low")

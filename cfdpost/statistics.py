"""Time-weighted statistics independent from visualization."""

from __future__ import annotations

import math

import numpy as np

from .models import RequestError


def time_weighted(values: list[np.ndarray], times: list[float]) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return mean, raw RMS, and fluctuation RMS using trapezoidal time weights."""
    if len(values) != len(times) or len(times) < 2:
        raise RequestError("Time-weighted statistics need at least two values with physical timestamps.")
    if any(not math.isfinite(t) for t in times) or any(b <= a for a, b in zip(times, times[1:])):
        raise RequestError("Physical timestamps must be finite and strictly increasing.")
    shape = values[0].shape
    if any(item.shape != shape for item in values):
        raise RequestError("Field shape changed between snapshots; this version requires a fixed mesh.")
    duration = times[-1] - times[0]
    first = np.zeros(shape, dtype=np.float64)
    second = np.zeros(shape, dtype=np.float64)
    for left, right, ta, tb in zip(values, values[1:], times, times[1:]):
        dt = tb - ta
        first += 0.5 * (left + right) * dt
        second += 0.5 * (left * left + right * right) * dt
    mean = first / duration
    mean_square = second / duration
    raw_rms = np.sqrt(np.maximum(mean_square, 0.0))
    fluctuation = np.sqrt(np.maximum(mean_square - mean * mean, 0.0))
    return mean, raw_rms, fluctuation


def summary(values: np.ndarray, weighting: str = "uniform", weights: np.ndarray | None = None) -> dict[str, float | int | str]:
    if weighting not in {"uniform", "cell_measure"}:
        raise RequestError("Spatial weighting must be 'uniform' or 'cell_measure'.")
    flat = np.asarray(values, dtype=float).reshape(-1)
    if not flat.size:
        raise RequestError("Cannot summarize an empty field.")
    if weighting == "cell_measure":
        if weights is None:
            raise RequestError("cell_measure summaries require one geometric weight per value.")
        result = weighted_summary(flat, np.asarray(weights, dtype=float).reshape(-1))
        return {"spatial_weighting": weighting, **result}
    return {
        "spatial_weighting": weighting,
        "count": int(flat.size),
        "mean": float(np.mean(flat)),
        "rms": float(np.sqrt(np.mean(flat * flat))),
        "minimum": float(np.min(flat)),
        "maximum": float(np.max(flat)),
    }


def weighted_summary(values: np.ndarray, weights: np.ndarray) -> dict[str, float | int]:
    values = np.asarray(values, dtype=float).reshape(-1)
    weights = np.asarray(weights, dtype=float).reshape(-1)
    if values.shape != weights.shape or not values.size:
        raise RequestError("Weighted statistics need equally sized non-empty values and weights.")
    total = float(np.sum(weights))
    if total <= 0 or np.any(weights < 0):
        raise RequestError("Spatial weights must be non-negative and have positive total measure.")
    mean = float(np.sum(values * weights) / total)
    return {
        "count": int(values.size),
        "mean": mean,
        "rms": float(np.sqrt(np.sum(values * values * weights) / total)),
        "minimum": float(np.min(values[weights > 0])),
        "maximum": float(np.max(values[weights > 0])),
    }

"""Small statistics helpers that avoid a numpy dependency."""

from __future__ import annotations

from collections.abc import Sequence


def quantile(values: Sequence[float], q: float) -> float:
    """Linear-interpolated quantile, matching numpy's default method."""
    if not values:
        raise ValueError("quantile of an empty sequence")
    if not 0.0 <= q <= 1.0:
        raise ValueError("q must be between 0 and 1")
    ordered = sorted(values)
    if len(ordered) == 1:
        return float(ordered[0])
    position = q * (len(ordered) - 1)
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = position - lower
    return float(ordered[lower] + (ordered[upper] - ordered[lower]) * fraction)


def maximum(values: Sequence[float]) -> float:
    if not values:
        raise ValueError("max of an empty sequence")
    return float(max(values))


def mean(values: Sequence[float]) -> float:
    if not values:
        raise ValueError("mean of an empty sequence")
    return float(sum(values) / len(values))
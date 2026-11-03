from __future__ import annotations

import pytest

from sysopt_rightsize.stats import maximum, mean, quantile


def test_quantile_interpolates():
    assert quantile([1, 2, 3, 4], 0.5) == 2.5
    assert quantile([1, 2, 3, 4], 0.0) == 1.0
    assert quantile([1, 2, 3, 4], 1.0) == 4.0


def test_quantile_of_a_single_value():
    assert quantile([7], 0.95) == 7.0


def test_quantile_rejects_bad_input():
    with pytest.raises(ValueError, match="empty"):
        quantile([], 0.5)
    with pytest.raises(ValueError, match="between"):
        quantile([1], 1.5)


def test_maximum_and_mean():
    assert maximum([3, 9, 2]) == 9.0
    assert mean([2, 4, 6]) == 4.0
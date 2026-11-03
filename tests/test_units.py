from __future__ import annotations

import pytest

from sysopt_rightsize.units import (
    GIB,
    MIB,
    format_cpu,
    format_memory,
    parse_cpu,
    parse_memory,
    round_up_cpu,
    round_up_memory,
)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("500m", 0.5), ("1", 1.0), ("1.5", 1.5), ("250u", 0.00025), (2, 2.0)],
)
def test_parse_cpu(raw, expected):
    assert parse_cpu(raw) == pytest.approx(expected)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("512Mi", 512 * MIB),
        ("1Gi", GIB),
        ("1G", 1_000_000_000),
        ("1024", 1024),
        (2048, 2048),
    ],
)
def test_parse_memory(raw, expected):
    assert parse_memory(raw) == expected


def test_round_up_cpu_to_ten_millicores():
    assert round_up_cpu(0.301) == 310
    assert round_up_cpu(0.300) == 300
    assert round_up_cpu(0.0001) == 10


def test_round_up_memory_to_sixteen_mib():
    assert round_up_memory(300 * MIB) == 304 * MIB
    assert round_up_memory(16 * MIB) == 16 * MIB


def test_format_cpu():
    assert format_cpu(1000) == "1"
    assert format_cpu(250) == "250m"


def test_format_memory():
    assert format_memory(GIB) == "1Gi"
    assert format_memory(512 * MIB) == "512Mi"
    assert format_memory(1024) == "1Ki"
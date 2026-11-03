from __future__ import annotations

import pytest

from sysopt_rightsize.recommend import (
    Options,
    WorkloadError,
    recommend_workload,
    render_yaml,
)
from sysopt_rightsize.units import MIB


def payload(**overrides):
    base = {
        "workload": "checkout",
        "namespace": "prod",
        "pricing": {
            "cpu_core_hour": 0.04,
            "memory_gib_hour": 0.005,
            "hours_per_month": 730,
        },
        "containers": [
            {
                "name": "api",
                "current": {
                    "cpu_request": "500m",
                    "cpu_limit": "1",
                    "memory_request": "512Mi",
                    "memory_limit": "1Gi",
                },
                "metrics": {
                    "cpu": [[1, 0.1], [2, 0.2], [3, 0.3]],
                    "memory": [[1, 100 * MIB], [2, 200 * MIB], [3, 300 * MIB]],
                },
            }
        ],
    }
    base.update(overrides)
    return base


def test_recommends_p95_with_headroom():
    result = recommend_workload(payload())
    api = result.containers[0]

    assert api.recommended is not None
    assert api.recommended.cpu_request_millicores == 350
    assert api.recommended.cpu_limit_millicores == 450
    assert api.recommended.memory_request_bytes == 336 * MIB
    assert api.recommended.memory_limit_bytes == 384 * MIB


def test_observations_include_p50_p95_p99_and_max():
    api = recommend_workload(payload()).containers[0]

    assert api.cpu_p50 == pytest.approx(0.2)
    assert api.cpu_p95 == pytest.approx(0.29)
    assert api.cpu_p99 == pytest.approx(0.298)
    assert api.cpu_max == pytest.approx(0.3)
    assert api.memory_p95 == pytest.approx(290 * MIB)


def test_monthly_costs_use_requests():
    result = recommend_workload(payload())
    api = result.containers[0]

    assert api.monthly_cost_current == pytest.approx(16.425)
    assert api.monthly_cost_recommended == pytest.approx(11.41765625)
    assert result.monthly_savings == pytest.approx(5.00734375)
    assert result.monthly_savings == pytest.approx(api.monthly_savings)


def test_flags_risk_when_usage_is_close_to_the_limit():
    risky = payload()
    risky["containers"][0]["current"]["cpu_limit"] = "300m"
    risky["containers"][0]["current"]["memory_limit"] = "256Mi"

    api = recommend_workload(risky).containers[0]

    assert "cpu_throttle_risk" in api.flags
    assert "memory_oom_risk" in api.flags
    assert set(api.risk_flags) == {"cpu_throttle_risk", "memory_oom_risk"}


def test_flags_over_provisioning():
    generous = payload()
    generous["containers"][0]["current"]["cpu_request"] = "4"
    generous["containers"][0]["current"]["memory_request"] = "8Gi"

    api = recommend_workload(generous).containers[0]

    assert "cpu_over_requested" in api.flags
    assert "memory_over_requested" in api.flags


def test_missing_samples_produce_no_recommendation():
    sparse = payload()
    sparse["containers"][0]["metrics"] = {}

    api = recommend_workload(sparse).containers[0]

    assert api.recommended is None
    assert "no_cpu_samples" in api.flags
    assert "no_memory_samples" in api.flags


def test_options_override_payload_pricing():
    options = Options(cpu_price_per_core_hour=1.0, memory_price_per_gib_hour=2.0)
    result = recommend_workload(payload(), options)

    assert result.options.cpu_price_per_core_hour == 1.0
    assert result.containers[0].monthly_cost_current == pytest.approx(0.5 * 730 + 0.5 * 2 * 730)


def test_duplicate_container_names_are_rejected():
    duplicate = payload()
    duplicate["containers"].append(dict(duplicate["containers"][0]))

    with pytest.raises(WorkloadError, match="duplicate container name"):
        recommend_workload(duplicate)


def test_invalid_container_shape_is_rejected():
    with pytest.raises(WorkloadError, match="non-empty 'containers'"):
        recommend_workload({"containers": []})


def test_render_yaml_contains_requests_and_limits():
    rendered = render_yaml(recommend_workload(payload()))

    assert "resources:" in rendered
    assert "cpu: 350m" in rendered
    assert "memory: 336Mi" in rendered
    assert "limits:" in rendered


def test_gib_price_uses_gib_not_bytes():
    options = Options(memory_price_per_gib_hour=1.0, hours_per_month=1.0)
    result = recommend_workload(payload(), options)

    assert result.containers[0].monthly_cost_current == pytest.approx(0.5)
from __future__ import annotations

import json
from pathlib import Path

import pytest

from sysopt_rightsize.cli import main
from sysopt_rightsize.units import MIB

WORKLOAD = {
    "workload": "checkout",
    "namespace": "prod",
    "pricing": {"cpu_core_hour": 0.04, "memory_gib_hour": 0.005},
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
                "cpu": [0.1, 0.2, 0.3],
                "memory": [100 * MIB, 200 * MIB, 300 * MIB],
            },
        }
    ],
}


def write(tmp_path: Path, payload) -> str:
    path = tmp_path / "workload.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return str(path)


def test_text_output(tmp_path, capsys):
    code = main([write(tmp_path, WORKLOAD)])

    output = capsys.readouterr().out
    assert code == 0
    assert "total:" in output
    assert "500m -> 350m" in output


def test_json_output(tmp_path, capsys):
    code = main([write(tmp_path, WORKLOAD), "--format", "json"])

    payload = json.loads(capsys.readouterr().out)
    assert code == 0
    assert payload["workload"] == "checkout"
    assert payload["containers"][0]["recommended"]["cpu_request"] == "350m"
    assert payload["totals"]["monthly_savings"] > 0


def test_yaml_output(tmp_path, capsys):
    code = main([write(tmp_path, WORKLOAD), "--format", "yaml"])

    output = capsys.readouterr().out
    assert code == 0
    assert "cpu: 350m" in output
    assert "memory: 336Mi" in output


def test_cli_price_overrides_payload(tmp_path, capsys):
    code = main([write(tmp_path, WORKLOAD), "--format", "json", "--cpu-price", "1"])

    payload = json.loads(capsys.readouterr().out)
    assert code == 0
    assert payload["pricing"]["cpu_core_hour"] == 1.0


def test_fail_on_risk(tmp_path, capsys):
    risky = json.loads(json.dumps(WORKLOAD))
    risky["containers"][0]["current"]["memory_limit"] = "256Mi"

    code = main([write(tmp_path, risky), "--fail-on-risk"])

    assert code == 1
    assert "memory_oom_risk" in capsys.readouterr().out


def test_invalid_workload_returns_two(tmp_path, capsys):
    code = main([write(tmp_path, {"containers": []})])

    assert code == 2
    assert "non-empty 'containers'" in capsys.readouterr().err


def test_invalid_json_exits(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text("{", encoding="utf-8")

    with pytest.raises(SystemExit, match="invalid JSON"):
        main([str(path)])
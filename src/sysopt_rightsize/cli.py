"""Command line entry point for sysopt-rightsize."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from .recommend import (
    Options,
    WorkloadError,
    WorkloadResult,
    recommend_workload,
    render_yaml,
)
from .units import MIB, format_cpu, format_memory


def _load(path: str) -> dict:
    try:
        text = sys.stdin.read() if path == "-" else Path(path).read_text(encoding="utf-8")
    except OSError as exc:
        raise SystemExit(f"error: cannot read {path}: {exc}") from exc
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"error: invalid JSON in {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise SystemExit("error: workload must be a JSON object")
    return payload


def _render_text(result: WorkloadResult) -> str:
    options = result.options
    header = (
        f"{'container':<18} {'cpu p95':>8} {'cpu request':<18} "
        f"{'mem p95':>9} {'memory request':<20} {'flags':<38} {'$/mo':>9}"
    )
    lines = [
        f"workload: {result.namespace}/{result.workload}",
        (
            f"pricing:  ${options.cpu_price_per_core_hour:.4f}/core-h + "
            f"${options.memory_price_per_gib_hour:.4f}/GiB-h x {options.hours_per_month:.0f}h"
        ),
        "",
        header,
        "-" * len(header),
    ]
    for item in result.containers:
        current = item.current
        recommended = item.recommended
        cpu_p95 = "-" if item.cpu_p95 is None else f"{item.cpu_p95:.3f}"
        mem_p95 = "-" if item.memory_p95 is None else f"{item.memory_p95 / MIB:.1f}Mi"
        if recommended is None:
            cpu_change = "insufficient samples"
            mem_change = "insufficient samples"
        else:
            cpu_change = (
                f"{format_cpu(current.cpu_request_millicores or 0)} -> "
                f"{format_cpu(recommended.cpu_request_millicores or 0)}"
            )
            mem_change = (
                f"{format_memory(current.memory_request_bytes or 0)} -> "
                f"{format_memory(recommended.memory_request_bytes or 0)}"
            )
        flags = ", ".join(item.flags) if item.flags else "-"
        lines.append(
            f"{item.name:<18} {cpu_p95:>8} {cpu_change:<18} "
            f"{mem_p95:>9} {mem_change:<20} {flags:<38} {item.monthly_savings:>+9.2f}"
        )

    lines.append("")
    savings = result.monthly_savings
    percent = (savings / result.monthly_cost_current * 100) if result.monthly_cost_current else 0.0
    lines.append(
        f"total: ${result.monthly_cost_current:.2f} -> ${result.monthly_cost_recommended:.2f} "
        f"per month (save ${savings:.2f}, {percent:.1f}%)"
    )
    if result.risk_flags:
        lines.append(f"risk:  {', '.join(result.risk_flags)}")
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="sysopt-rightsize",
        description="Recommend Kubernetes CPU and memory requests from observed usage.",
    )
    parser.add_argument("workload", help="workload JSON file, or '-' for stdin")
    parser.add_argument(
        "--format", choices=("text", "json", "yaml"), default="text", help="output format"
    )
    parser.add_argument("--cpu-headroom", type=float, help="multiplier over CPU p95 (default 1.20)")
    parser.add_argument(
        "--memory-headroom", type=float, help="multiplier over memory p95 (default 1.15)"
    )
    parser.add_argument(
        "--cpu-limit-headroom", type=float, help="multiplier over CPU max for limits"
    )
    parser.add_argument(
        "--memory-limit-headroom", type=float, help="multiplier over memory max for limits"
    )
    parser.add_argument("--cpu-price", type=float, help="price per CPU core-hour")
    parser.add_argument("--memory-price", type=float, help="price per GiB-hour")
    parser.add_argument("--hours-per-month", type=float, help="billing hours per month")
    parser.add_argument(
        "--fail-on-risk",
        action="store_true",
        help="exit 1 when a container is close to its CPU limit or memory limit",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    payload = _load(args.workload)

    options = Options()
    pricing = payload.get("pricing") or {}
    if isinstance(pricing, dict):
        if "cpu_core_hour" in pricing:
            options.cpu_price_per_core_hour = float(pricing["cpu_core_hour"])
        if "memory_gib_hour" in pricing:
            options.memory_price_per_gib_hour = float(pricing["memory_gib_hour"])
        if "hours_per_month" in pricing:
            options.hours_per_month = float(pricing["hours_per_month"])
    if args.cpu_price is not None:
        options.cpu_price_per_core_hour = args.cpu_price
    if args.memory_price is not None:
        options.memory_price_per_gib_hour = args.memory_price
    if args.hours_per_month is not None:
        options.hours_per_month = args.hours_per_month
    if args.cpu_headroom is not None:
        options.cpu_headroom = args.cpu_headroom
    if args.memory_headroom is not None:
        options.memory_headroom = args.memory_headroom
    if args.cpu_limit_headroom is not None:
        options.cpu_limit_headroom = args.cpu_limit_headroom
    if args.memory_limit_headroom is not None:
        options.memory_limit_headroom = args.memory_limit_headroom

    try:
        result = recommend_workload(payload, options)
    except (WorkloadError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if args.format == "json":
        print(json.dumps(result.to_dict(), indent=2))
    elif args.format == "yaml":
        print(render_yaml(result))
    else:
        print(_render_text(result))

    if args.fail_on_risk and result.risk_flags:
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
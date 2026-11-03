"""Right-sizing recommendations from historical CPU and memory samples."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .stats import maximum, quantile
from .units import (
    GIB,
    MIB,
    format_cpu,
    format_memory,
    parse_cpu,
    parse_memory,
    round_up_cpu,
    round_up_memory,
)


class WorkloadError(ValueError):
    """Raised when a workload description cannot be parsed."""


@dataclass
class Options:
    cpu_headroom: float = 1.20
    memory_headroom: float = 1.15
    cpu_limit_headroom: float = 1.50
    memory_limit_headroom: float = 1.25
    min_cpu_millicores: int = 10
    min_memory_bytes: int = 32 * MIB
    cpu_step_millicores: int = 10
    memory_step_bytes: int = 16 * MIB
    cpu_price_per_core_hour: float = 0.0
    memory_price_per_gib_hour: float = 0.0
    hours_per_month: float = 730.0
    over_provision_factor: float = 2.0
    risk_threshold: float = 0.90


@dataclass
class Resources:
    cpu_request_millicores: int | None = None
    cpu_limit_millicores: int | None = None
    memory_request_bytes: int | None = None
    memory_limit_bytes: int | None = None

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> Resources:
        if not isinstance(payload, dict):
            raise WorkloadError("'current' must be a mapping")
        return cls(
            cpu_request_millicores=_cpu_millicores(payload.get("cpu_request")),
            cpu_limit_millicores=_cpu_millicores(payload.get("cpu_limit")),
            memory_request_bytes=_memory_bytes(payload.get("memory_request")),
            memory_limit_bytes=_memory_bytes(payload.get("memory_limit")),
        )

    def to_dict(self) -> dict[str, str | None]:
        return {
            "cpu_request": _fmt_cpu(self.cpu_request_millicores),
            "cpu_limit": _fmt_cpu(self.cpu_limit_millicores),
            "memory_request": _fmt_memory(self.memory_request_bytes),
            "memory_limit": _fmt_memory(self.memory_limit_bytes),
        }


@dataclass
class ContainerInput:
    name: str
    current: Resources
    cpu_samples: list[float] = field(default_factory=list)
    memory_samples: list[float] = field(default_factory=list)


@dataclass
class Recommendation:
    name: str
    current: Resources
    recommended: Resources | None
    cpu_p50: float | None
    cpu_p95: float | None
    cpu_p99: float | None
    cpu_max: float | None
    memory_p50: float | None
    memory_p95: float | None
    memory_p99: float | None
    memory_max: float | None
    cpu_samples: int
    memory_samples: int
    flags: list[str] = field(default_factory=list)
    monthly_cost_current: float = 0.0
    monthly_cost_recommended: float = 0.0

    @property
    def monthly_savings(self) -> float:
        return self.monthly_cost_current - self.monthly_cost_recommended

    @property
    def risk_flags(self) -> list[str]:
        return [flag for flag in self.flags if flag.endswith("_risk")]

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "samples": {"cpu": self.cpu_samples, "memory": self.memory_samples},
            "current": self.current.to_dict(),
            "recommended": self.recommended.to_dict() if self.recommended else None,
            "observed": {
                "cpu": {
                    "p50": _round(self.cpu_p50),
                    "p95": _round(self.cpu_p95),
                    "p99": _round(self.cpu_p99),
                    "max": _round(self.cpu_max),
                },
                "memory_bytes": {
                    "p50": self.memory_p50,
                    "p95": self.memory_p95,
                    "p99": self.memory_p99,
                    "max": self.memory_max,
                },
            },
            "flags": self.flags,
            "monthly_cost_current": round(self.monthly_cost_current, 4),
            "monthly_cost_recommended": round(self.monthly_cost_recommended, 4),
            "monthly_savings": round(self.monthly_savings, 4),
        }


@dataclass
class WorkloadResult:
    workload: str
    namespace: str
    containers: list[Recommendation]
    options: Options

    @property
    def monthly_cost_current(self) -> float:
        return sum(item.monthly_cost_current for item in self.containers)

    @property
    def monthly_cost_recommended(self) -> float:
        return sum(item.monthly_cost_recommended for item in self.containers)

    @property
    def monthly_savings(self) -> float:
        return self.monthly_cost_current - self.monthly_cost_recommended

    @property
    def risk_flags(self) -> list[str]:
        return [f"{item.name}:{flag}" for item in self.containers for flag in item.risk_flags]

    def to_dict(self) -> dict[str, Any]:
        return {
            "workload": self.workload,
            "namespace": self.namespace,
            "pricing": {
                "cpu_core_hour": self.options.cpu_price_per_core_hour,
                "memory_gib_hour": self.options.memory_price_per_gib_hour,
                "hours_per_month": self.options.hours_per_month,
            },
            "containers": [item.to_dict() for item in self.containers],
            "totals": {
                "monthly_cost_current": round(self.monthly_cost_current, 4),
                "monthly_cost_recommended": round(self.monthly_cost_recommended, 4),
                "monthly_savings": round(self.monthly_savings, 4),
                "risk_flags": self.risk_flags,
            },
        }


def _round(value: float | None) -> float | None:
    return None if value is None else round(value, 6)


def _fmt_cpu(millicores: int | None) -> str | None:
    return None if millicores is None else format_cpu(millicores)


def _fmt_memory(byte_count: int | None) -> str | None:
    return None if byte_count is None else format_memory(byte_count)


def _cpu_millicores(value: Any) -> int | None:
    if value is None:
        return None
    return round_up_cpu(parse_cpu(value), 1)


def _memory_bytes(value: Any) -> int | None:
    if value is None:
        return None
    return parse_memory(value)


def _samples(raw: Any) -> list[float]:
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise WorkloadError("metric series must be a list")
    values: list[float] = []
    for item in raw:
        if isinstance(item, (list, tuple)):
            if len(item) < 2:
                raise WorkloadError("sample pair must be [timestamp, value]")
            value = item[1]
        else:
            value = item
        if isinstance(value, bool) or not isinstance(value, (int, float, str)):
            raise WorkloadError(f"invalid sample value {value!r}")
        values.append(float(value))
    return values


def monthly_cost(resources: Resources, options: Options) -> float:
    cpu = resources.cpu_request_millicores or 0
    memory = resources.memory_request_bytes or 0
    cores = cpu / 1000.0
    gib = memory / GIB
    hourly = cores * options.cpu_price_per_core_hour + gib * options.memory_price_per_gib_hour
    return hourly * options.hours_per_month


def recommend_container(container: ContainerInput, options: Options) -> Recommendation:
    cpu = container.cpu_samples
    memory = container.memory_samples
    flags: list[str] = []

    if cpu:
        cpu_p50 = quantile(cpu, 0.50)
        cpu_p95 = quantile(cpu, 0.95)
        cpu_p99 = quantile(cpu, 0.99)
        cpu_max = maximum(cpu)
        cpu_request = round_up_cpu(
            max(cpu_p95 * options.cpu_headroom, options.min_cpu_millicores / 1000.0),
            options.cpu_step_millicores,
        )
        cpu_limit = None
        if container.current.cpu_limit_millicores is not None:
            cpu_limit = round_up_cpu(
                max(
                    cpu_max * options.cpu_limit_headroom,
                    cpu_request / 1000.0,
                ),
                options.cpu_step_millicores,
            )
    else:
        cpu_p50 = cpu_p95 = cpu_p99 = cpu_max = None
        cpu_request = cpu_limit = None
        flags.append("no_cpu_samples")

    if memory:
        memory_p50 = quantile(memory, 0.50)
        memory_p95 = quantile(memory, 0.95)
        memory_p99 = quantile(memory, 0.99)
        memory_max = maximum(memory)
        memory_request = round_up_memory(
            max(memory_p95 * options.memory_headroom, options.min_memory_bytes),
            options.memory_step_bytes,
        )
        memory_limit = None
        if container.current.memory_limit_bytes is not None:
            memory_limit = round_up_memory(
                max(memory_max * options.memory_limit_headroom, memory_request),
                options.memory_step_bytes,
            )
    else:
        memory_p50 = memory_p95 = memory_p99 = memory_max = None
        memory_request = memory_limit = None
        flags.append("no_memory_samples")

    recommended = None
    if cpu_request is not None and memory_request is not None:
        recommended = Resources(
            cpu_request_millicores=cpu_request,
            cpu_limit_millicores=cpu_limit,
            memory_request_bytes=memory_request,
            memory_limit_bytes=memory_limit,
        )

    current = container.current
    threshold = options.risk_threshold
    if (
        cpu_p99 is not None
        and current.cpu_limit_millicores
        and cpu_p99 >= current.cpu_limit_millicores / 1000.0 * threshold
    ):
        flags.append("cpu_throttle_risk")
    if (
        memory_max is not None
        and current.memory_limit_bytes
        and memory_max >= current.memory_limit_bytes * threshold
    ):
        flags.append("memory_oom_risk")
    if (
        cpu_p95 is not None
        and current.cpu_request_millicores
        and cpu_p95 > current.cpu_request_millicores / 1000.0
    ):
        flags.append("cpu_under_requested")
    if (
        memory_p95 is not None
        and current.memory_request_bytes
        and memory_p95 > current.memory_request_bytes
    ):
        flags.append("memory_under_requested")
    if (
        cpu_request is not None
        and current.cpu_request_millicores
        and cpu_request < current.cpu_request_millicores / options.over_provision_factor
    ):
        flags.append("cpu_over_requested")
    if (
        memory_request is not None
        and current.memory_request_bytes
        and memory_request < current.memory_request_bytes / options.over_provision_factor
    ):
        flags.append("memory_over_requested")

    current_cost = monthly_cost(current, options)
    recommended_cost = monthly_cost(recommended or current, options)
    return Recommendation(
        name=container.name,
        current=current,
        recommended=recommended,
        cpu_p50=cpu_p50,
        cpu_p95=cpu_p95,
        cpu_p99=cpu_p99,
        cpu_max=cpu_max,
        memory_p50=memory_p50,
        memory_p95=memory_p95,
        memory_p99=memory_p99,
        memory_max=memory_max,
        cpu_samples=len(cpu),
        memory_samples=len(memory),
        flags=flags,
        monthly_cost_current=current_cost,
        monthly_cost_recommended=recommended_cost,
    )


def recommend_workload(payload: dict[str, Any], options: Options | None = None) -> WorkloadResult:
    if not isinstance(payload, dict):
        raise WorkloadError("workload must be a JSON object")

    if options is None:
        options = Options()
        pricing = payload.get("pricing") or {}
        if not isinstance(pricing, dict):
            raise WorkloadError("'pricing' must be a mapping")
        if "cpu_core_hour" in pricing:
            options.cpu_price_per_core_hour = float(pricing["cpu_core_hour"])
        if "memory_gib_hour" in pricing:
            options.memory_price_per_gib_hour = float(pricing["memory_gib_hour"])
        if "hours_per_month" in pricing:
            options.hours_per_month = float(pricing["hours_per_month"])

    raw_containers = payload.get("containers")
    if not isinstance(raw_containers, list) or not raw_containers:
        raise WorkloadError("workload must contain a non-empty 'containers' list")

    containers: list[ContainerInput] = []
    names: set[str] = set()
    for raw in raw_containers:
        if not isinstance(raw, dict):
            raise WorkloadError("each container must be a mapping")
        name = raw.get("name")
        if not isinstance(name, str) or not name:
            raise WorkloadError("each container needs a non-empty 'name'")
        if name in names:
            raise WorkloadError(f"duplicate container name {name!r}")
        names.add(name)
        metrics = raw.get("metrics") or {}
        if not isinstance(metrics, dict):
            raise WorkloadError(f"'metrics' for {name!r} must be a mapping")
        containers.append(
            ContainerInput(
                name=name,
                current=Resources.from_dict(raw.get("current") or {}),
                cpu_samples=_samples(metrics.get("cpu")),
                memory_samples=_samples(metrics.get("memory")),
            )
        )

    return WorkloadResult(
        workload=str(payload.get("workload") or "workload"),
        namespace=str(payload.get("namespace") or "default"),
        containers=[recommend_container(item, options) for item in containers],
        options=options,
    )


def render_yaml(result: WorkloadResult) -> str:
    lines = [
        f"# {result.namespace}/{result.workload}",
        "containers:",
    ]
    for item in result.containers:
        lines.append(f"  - name: {item.name}")
        lines.append("    resources:")
        if item.recommended is None:
            lines.append("      # insufficient samples to recommend resources")
            continue
        lines.append("      requests:")
        lines.append(f"        cpu: {format_cpu(item.recommended.cpu_request_millicores or 0)}")
        lines.append(
            f"        memory: {format_memory(item.recommended.memory_request_bytes or 0)}"
        )
        if item.recommended.cpu_limit_millicores is not None:
            lines.append("      limits:")
            lines.append(f"        cpu: {format_cpu(item.recommended.cpu_limit_millicores)}")
            if item.recommended.memory_limit_bytes is not None:
                memory_limit = format_memory(item.recommended.memory_limit_bytes)
                lines.append(f"        memory: {memory_limit}")
    return "\n".join(lines)
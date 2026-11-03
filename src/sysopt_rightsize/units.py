"""Kubernetes resource quantity parsing and formatting."""

from __future__ import annotations

from math import ceil

MIB = 1024**2
GIB = 1024**3
TIB = 1024**4
KIB = 1024

_MEMORY_SUFFIXES = {
    "Ki": KIB,
    "Mi": MIB,
    "Gi": GIB,
    "Ti": TIB,
    "K": 1000,
    "M": 1000**2,
    "G": 1000**3,
    "T": 1000**4,
}


def parse_cpu(value: str | int | float) -> float:
    """Parse a Kubernetes CPU quantity into cores."""
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    text = str(value).strip()
    if not text:
        raise ValueError("empty CPU quantity")
    if text.endswith("m"):
        return float(text[:-1]) / 1000.0
    if text.endswith("u"):
        return float(text[:-1]) / 1_000_000.0
    if text.endswith("n"):
        return float(text[:-1]) / 1_000_000_000.0
    return float(text)


def parse_memory(value: str | int | float) -> int:
    """Parse a Kubernetes memory quantity into bytes."""
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return int(value)
    text = str(value).strip()
    if not text:
        raise ValueError("empty memory quantity")
    for suffix, factor in _MEMORY_SUFFIXES.items():
        if text.endswith(suffix):
            return int(float(text[: -len(suffix)]) * factor)
    return int(float(text))


def round_up_cpu(cores: float, step_millicores: int = 10) -> int:
    """Round cores up to a millicore step and return millicores."""
    millicores = cores * 1000.0
    step = max(1, step_millicores)
    return int(ceil(millicores / step) * step)


def round_up_memory(byte_count: float, step_bytes: int = 16 * MIB) -> int:
    step = max(1, step_bytes)
    return int(ceil(byte_count / step) * step)


def format_cpu(millicores: int) -> str:
    if millicores % 1000 == 0:
        return str(millicores // 1000)
    return f"{millicores}m"


def format_memory(byte_count: int) -> str:
    if byte_count % GIB == 0:
        return f"{byte_count // GIB}Gi"
    if byte_count % MIB == 0:
        return f"{byte_count // MIB}Mi"
    if byte_count % KIB == 0:
        return f"{byte_count // KIB}Ki"
    return str(byte_count)
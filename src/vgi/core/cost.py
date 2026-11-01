"""Cost accounting from API usage and electricity."""
from __future__ import annotations

from typing import Any


def claude_cost_usd(pricing: dict[str, Any], model: str, usage: dict[str, int]) -> float:
    table = (pricing.get("claude") or {}).get(model)
    if not table:
        return 0.0
    m = 1_000_000
    return round(
        usage.get("input_tokens", 0) / m * table.get("input", 0)
        + usage.get("output_tokens", 0) / m * table.get("output", 0)
        + usage.get("cache_read_input_tokens", 0) / m * table.get("cache_read", 0)
        + usage.get("cache_creation_input_tokens", 0) / m * table.get("cache_write", 0),
        6,
    )


def electricity_cost_usd(pricing: dict[str, Any], power_watts: float, krw_per_kwh: float, seconds: float) -> float:
    kwh = power_watts / 1000.0 * seconds / 3600.0
    return round(kwh * krw_per_kwh * float(pricing.get("usd_per_krw", 0.00071)), 6)

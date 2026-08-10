# File: custom_components/solar_energy_controller/decision_log.py
# Timestamp: 2026-08-10 23:25 CEST

from __future__ import annotations

from collections import deque
from typing import Any

MAX_LOG_ENTRIES = 192  # 48 h at 15-minute intervals


def append_decision_log(log: list[dict[str, Any]], entry: dict[str, Any]) -> list[dict[str, Any]]:
    """Append one simulation decision and keep a bounded history."""
    bounded = deque(log, maxlen=MAX_LOG_ENTRIES)
    bounded.append(entry)
    return list(bounded)


def format_decision(entry: dict[str, Any] | None) -> str:
    """Compact human-readable representation for the HA sensor state."""
    if not entry:
        return "No decision yet"
    return (
        f"{entry.get('time_local', '--:--')} | {entry.get('recommendation', 'UNKNOWN')} | "
        f"SOC {entry.get('virtual_soc', 0):.1f}% → {entry.get('target_soc', 0):.1f}% | "
        f"EPEX {entry.get('export_price_ct', 0):.2f} ct/kWh | "
        f"Miner {'ON' if entry.get('miner_on') else 'OFF'}"
    )

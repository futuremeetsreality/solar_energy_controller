# File: custom_components/solar_energy_controller/price_parser.py
# Timestamp: 2026-08-10 20:29 CEST

from __future__ import annotations

from datetime import datetime
from typing import Any

from homeassistant.util import dt as dt_util

_TIME_KEYS = ("start_time", "start", "time", "timestamp", "datetime", "date")
_PRICE_KEYS = ("price", "value", "market_price", "marketprice", "price_ct_kwh", "ct_kwh")


def _parse_time(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, (int, float)):
        try:
            dt = datetime.fromtimestamp(float(value), tz=dt_util.UTC)
        except (ValueError, OSError, OverflowError):
            return None
    elif isinstance(value, str):
        dt = dt_util.parse_datetime(value)
        if dt is None:
            try:
                dt = datetime.fromtimestamp(float(value), tz=dt_util.UTC)
            except (ValueError, OSError, OverflowError):
                return None
    else:
        return None

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=dt_util.DEFAULT_TIME_ZONE)
    return dt_util.as_local(dt)


def _as_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def extract_price_series(attributes: dict[str, Any]) -> list[tuple[datetime, float]]:
    """Find timestamp/price pairs in common EPEX attribute layouts.

    Prices are returned exactly in the source unit. The controller assumes ct/kWh
    for the configured EPEX entity, matching the reference installation.
    """
    results: list[tuple[datetime, float]] = []

    def visit(value: Any) -> None:
        if isinstance(value, dict):
            time_value = next((value.get(k) for k in _TIME_KEYS if value.get(k) is not None), None)
            price_value = next((value.get(k) for k in _PRICE_KEYS if value.get(k) is not None), None)
            if time_value is not None and price_value is not None:
                dt = _parse_time(time_value)
                price = _as_float(price_value)
                if dt is not None and price is not None:
                    results.append((dt, price))
            for nested in value.values():
                if isinstance(nested, (dict, list, tuple)):
                    visit(nested)
        elif isinstance(value, (list, tuple)):
            for item in value:
                visit(item)

    visit(attributes)

    deduplicated: dict[datetime, float] = {}
    for dt, price in results:
        deduplicated[dt] = price
    return sorted(deduplicated.items(), key=lambda item: item[0])


def future_prices(
    attributes: dict[str, Any], now: datetime, horizon_hours: int
) -> list[tuple[datetime, float]]:
    end = now.timestamp() + horizon_hours * 3600
    return [
        (dt, price)
        for dt, price in extract_price_series(attributes)
        if now.timestamp() - 900 <= dt.timestamp() <= end
    ]

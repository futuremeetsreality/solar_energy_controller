# File: custom_components/solar_energy_controller/price_parser.py
# Timestamp: 2026-08-11 07:38 CEST

from __future__ import annotations

from datetime import datetime
from typing import Any

from homeassistant.util import dt as dt_util

_TIME_KEYS = (
    "start_time", "start", "starts_at", "from", "time", "timestamp",
    "datetime", "date", "startTime", "start_time_local",
)
_PRICE_KEYS = (
    "price", "value", "market_price", "marketprice", "marketPrice",
    "price_ct_kwh", "ct_kwh", "price_per_kwh", "total",
)
_SERIES_KEYS = (
    "data", "prices", "values", "today", "tomorrow", "raw_today",
    "raw_tomorrow", "market_prices", "price_data", "entries",
)


def _parse_time(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, (int, float)):
        try:
            stamp = float(value)
            if stamp > 10_000_000_000:
                stamp /= 1000.0
            dt = datetime.fromtimestamp(stamp, tz=dt_util.UTC)
        except (ValueError, OSError, OverflowError):
            return None
    elif isinstance(value, str):
        dt = dt_util.parse_datetime(value)
        if dt is None:
            try:
                stamp = float(value)
                if stamp > 10_000_000_000:
                    stamp /= 1000.0
                dt = datetime.fromtimestamp(stamp, tz=dt_util.UTC)
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
    """Extract timestamp/price pairs and normalize EPEX values to ct/kWh.

    The reference EPEX entity exposes its quarter-hour values in attribute
    ``data`` using ``price_per_kwh`` in EUR/kWh. Those values are multiplied by
    100 so the controller consistently receives ct/kWh. Other supported price
    keys keep their existing value to preserve compatibility with sources that
    already expose ct/kWh.
    """
    results: list[tuple[datetime, float]] = []

    def add_pair(time_value: Any, price_value: Any, *, multiplier: float = 1.0) -> None:
        dt = _parse_time(time_value)
        price = _as_float(price_value)
        if dt is not None and price is not None:
            results.append((dt, price * multiplier))

    def visit(value: Any) -> None:
        if isinstance(value, dict):
            time_value = next((value.get(k) for k in _TIME_KEYS if value.get(k) is not None), None)
            price_key = next((k for k in _PRICE_KEYS if value.get(k) is not None), None)
            if time_value is not None and price_key is not None:
                multiplier = 100.0 if price_key == "price_per_kwh" else 1.0
                add_pair(time_value, value.get(price_key), multiplier=multiplier)

            for key, nested in value.items():
                if not isinstance(nested, (dict, list, tuple)):
                    parsed_key = _parse_time(key)
                    numeric_value = _as_float(nested)
                    if parsed_key is not None and numeric_value is not None:
                        results.append((parsed_key, numeric_value))

            for key in _SERIES_KEYS:
                nested = value.get(key)
                if isinstance(nested, (dict, list, tuple)):
                    visit(nested)
            for key, nested in value.items():
                if key not in _SERIES_KEYS and isinstance(nested, (dict, list, tuple)):
                    visit(nested)

        elif isinstance(value, (list, tuple)):
            if len(value) == 2 and not isinstance(value[0], (dict, list, tuple)):
                dt = _parse_time(value[0])
                price = _as_float(value[1])
                if dt is not None and price is not None:
                    results.append((dt, price))
                    return
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
    """Return price points in ct/kWh from the current quarter through the horizon."""
    now_local = dt_util.as_local(now)
    end_ts = now_local.timestamp() + horizon_hours * 3600
    return [
        (dt, price)
        for dt, price in extract_price_series(attributes)
        if now_local.timestamp() - 900 <= dt.timestamp() <= end_ts
    ]

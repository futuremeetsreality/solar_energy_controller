# File: custom_components/solar_energy_controller/price_parser.py
# Timestamp: 2026-08-10 21:10 CEST

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
            if stamp > 10_000_000_000:  # milliseconds since epoch
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
    """Extract timestamp/price pairs from common EPEX attribute layouts.

    The source entity in the reference installation contains today + tomorrow
    quarter-hour values. Prices are kept in their source unit; the controller
    expects ct/kWh for this EPEX entity.
    """
    results: list[tuple[datetime, float]] = []

    def add_pair(time_value: Any, price_value: Any) -> None:
        dt = _parse_time(time_value)
        price = _as_float(price_value)
        if dt is not None and price is not None:
            results.append((dt, price))

    def visit(value: Any) -> None:
        if isinstance(value, dict):
            time_value = next((value.get(k) for k in _TIME_KEYS if value.get(k) is not None), None)
            price_value = next((value.get(k) for k in _PRICE_KEYS if value.get(k) is not None), None)
            if time_value is not None and price_value is not None:
                add_pair(time_value, price_value)

            # Some integrations expose {timestamp: price} dictionaries.
            for key, nested in value.items():
                if not isinstance(nested, (dict, list, tuple)):
                    parsed_key = _parse_time(key)
                    numeric_value = _as_float(nested)
                    if parsed_key is not None and numeric_value is not None:
                        results.append((parsed_key, numeric_value))

            # Prefer likely series attributes, then recursively inspect others.
            for key in _SERIES_KEYS:
                nested = value.get(key)
                if isinstance(nested, (dict, list, tuple)):
                    visit(nested)
            for key, nested in value.items():
                if key not in _SERIES_KEYS and isinstance(nested, (dict, list, tuple)):
                    visit(nested)

        elif isinstance(value, (list, tuple)):
            # Also support [timestamp, price] pairs.
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
    """Return price points from the current quarter through the horizon."""
    now_local = dt_util.as_local(now)
    end_ts = now_local.timestamp() + horizon_hours * 3600
    return [
        (dt, price)
        for dt, price in extract_price_series(attributes)
        if now_local.timestamp() - 900 <= dt.timestamp() <= end_ts
    ]

# File: custom_components/solar_energy_controller/coordinator.py
# Timestamp: 2026-08-10 22:10 CEST

from __future__ import annotations

from datetime import datetime, timedelta
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from .const import *
from .decision_log import append_decision_log, format_decision
from .price_parser import future_prices

_LOGGER = logging.getLogger(__name__)


class SolarEnergyControllerCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Economic shadow controller. 0.1.x never writes to devices."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.entry = entry
        self.cfg = {**DEFAULTS, **entry.data, **entry.options}
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(minutes=int(self.cfg[CONF_INTERVAL_MIN])),
        )
        self._store = Store(hass, STORAGE_VERSION, f"{STORAGE_KEY}_{entry.entry_id}")
        self._loaded = False
        self.simulation_enabled = True
        self.virtual_energy_kwh: float | None = None
        self.miner_simulated_on = False
        self.miner_locked_until: datetime | None = None
        self.accumulation_date = dt_util.now().date().isoformat()
        self.accumulation_start = dt_util.now().isoformat()
        self.last_update: datetime | None = None
        self.last_actual_export_energy: float | None = None
        self.last_actual_import_energy: float | None = None
        self.metrics = self._fresh_metrics()
        self.decision_log: list[dict[str, Any]] = []

    @staticmethod
    def _fresh_metrics() -> dict[str, float]:
        return {
            key: 0.0
            for key in (
                "sim_export_kwh",
                "sim_export_revenue_eur",
                "sim_import_kwh",
                "sim_import_cost_eur",
                "sim_self_supply_kwh",
                "sim_self_supply_value_eur",
                "sim_miner_hours",
                "sim_doge",
                "sim_mining_value_eur",
                "actual_export_revenue_eur",
                "actual_import_cost_eur",
                "actual_self_supply_value_eur",
                "actual_miner_hours",
                "actual_doge",
                "actual_mining_value_eur",
            )
        }

    def _entity(self, key: str) -> str:
        """Resolve configured entity, then fall back to the known default."""
        configured = str(self.cfg.get(key, "") or "").strip()
        if configured and self.hass.states.get(configured) is not None:
            return configured
        fallback = str(DEFAULTS.get(key, "") or "").strip()
        if fallback and self.hass.states.get(fallback) is not None:
            return fallback
        return configured or fallback

    def _forecast_entity(self, key: str) -> str:
        """Resolve Forecast.Solar input and never allow a self-reference."""
        fallback = str(DEFAULTS.get(key, "") or "").strip()
        if fallback and self.hass.states.get(fallback) is not None:
            return fallback

        configured = str(self.cfg.get(key, "") or "").strip()
        if (
            configured
            and "solar_energy_controller" not in configured
            and self.hass.states.get(configured) is not None
        ):
            return configured
        return fallback or configured

    async def _async_load(self) -> None:
        if self._loaded:
            return
        saved = await self._store.async_load() or {}
        self.simulation_enabled = bool(saved.get("simulation_enabled", True))
        self.virtual_energy_kwh = saved.get("virtual_energy_kwh")
        self.miner_simulated_on = bool(saved.get("miner_simulated_on", False))
        locked = saved.get("miner_locked_until")
        self.miner_locked_until = dt_util.parse_datetime(locked) if locked else None
        self.accumulation_date = saved.get("accumulation_date", self.accumulation_date)
        self.accumulation_start = saved.get("accumulation_start", self.accumulation_start)
        self.metrics.update(saved.get("metrics", {}))
        self.decision_log = list(saved.get("decision_log", []))[-192:]
        self._loaded = True

    async def async_set_simulation_enabled(self, enabled: bool) -> None:
        self.simulation_enabled = enabled
        await self._async_save()
        await self.async_request_refresh()

    async def _async_save(self) -> None:
        await self._store.async_save(
            {
                "simulation_enabled": self.simulation_enabled,
                "virtual_energy_kwh": self.virtual_energy_kwh,
                "miner_simulated_on": self.miner_simulated_on,
                "miner_locked_until": self.miner_locked_until.isoformat()
                if self.miner_locked_until
                else None,
                "accumulation_date": self.accumulation_date,
                "accumulation_start": self.accumulation_start,
                "metrics": self.metrics,
                "decision_log": self.decision_log,
            }
        )

    def _state_float(self, entity_id: str) -> float | None:
        if not entity_id:
            return None
        state = self.hass.states.get(entity_id)
        if state is None or state.state in ("unknown", "unavailable", "none", ""):
            return None
        try:
            return float(state.state)
        except (TypeError, ValueError):
            return None

    def _raw_state(self, entity_id: str) -> str | None:
        state = self.hass.states.get(entity_id) if entity_id else None
        return state.state if state is not None else None

    def _power_kw(self, entity_id: str) -> float:
        value = self._state_float(entity_id)
        if value is None:
            return 0.0
        state = self.hass.states.get(entity_id)
        unit = str(state.attributes.get("unit_of_measurement", "W")) if state else "W"
        return max(0.0, value if unit.lower() == "kw" else value / 1000.0)

    def _energy_kwh(self, entity_id: str) -> float | None:
        value = self._state_float(entity_id)
        if value is None:
            return None
        state = self.hass.states.get(entity_id)
        unit = str(state.attributes.get("unit_of_measurement", "kWh")) if state else "kWh"
        return value / 1000.0 if unit.lower() == "wh" else value

    def _price_ct(self, entity_id: str) -> float | None:
        value = self._state_float(entity_id)
        if value is None:
            return None
        state = self.hass.states.get(entity_id)
        unit = str(state.attributes.get("unit_of_measurement", "ct/kWh")) if state else "ct/kWh"
        normalized = unit.lower().replace(" ", "")
        return value * 100.0 if "€/kwh" in normalized or "eur/kwh" in normalized else value

    def _sum_energy(self, *entities: str) -> float:
        return sum(
            value
            for value in (self._energy_kwh(entity_id) for entity_id in entities)
            if value is not None
        )

    def _timestamp(self, entity_id: str) -> datetime | None:
        state = self.hass.states.get(entity_id) if entity_id else None
        if not state:
            return None
        parsed = dt_util.parse_datetime(state.state)
        return dt_util.as_local(parsed) if parsed else None

    def _forecast_sources(self) -> dict[str, str]:
        return {
            "today_1": self._forecast_entity(CONF_FORECAST_TODAY_1),
            "today_2": self._forecast_entity(CONF_FORECAST_TODAY_2),
            "remaining_1": self._forecast_entity(CONF_FORECAST_REMAINING_1),
            "remaining_2": self._forecast_entity(CONF_FORECAST_REMAINING_2),
            "tomorrow_1": self._forecast_entity(CONF_FORECAST_TOMORROW_1),
            "tomorrow_2": self._forecast_entity(CONF_FORECAST_TOMORROW_2),
            "next_hour_1": self._forecast_entity(CONF_FORECAST_NEXT_HOUR_1),
            "next_hour_2": self._forecast_entity(CONF_FORECAST_NEXT_HOUR_2),
            "peak_tomorrow_1": self._forecast_entity(CONF_FORECAST_PEAK_TOMORROW_1),
            "peak_tomorrow_2": self._forecast_entity(CONF_FORECAST_PEAK_TOMORROW_2),
        }

    def _forecast(self) -> tuple[dict[str, Any], dict[str, str]]:
        sources = self._forecast_sources()
        forecast = {
            "today": self._sum_energy(sources["today_1"], sources["today_2"]),
            "remaining": self._sum_energy(sources["remaining_1"], sources["remaining_2"]),
            "tomorrow": self._sum_energy(sources["tomorrow_1"], sources["tomorrow_2"]),
            "next_hour": self._sum_energy(sources["next_hour_1"], sources["next_hour_2"]),
            "peak_tomorrow": self._timestamp(sources["peak_tomorrow_1"])
            or self._timestamp(sources["peak_tomorrow_2"]),
        }
        return forecast, sources

    def _actual_miner_on(self) -> bool:
        state = self.hass.states.get(self._entity(CONF_MINER_SWITCH))
        return bool(state and state.state == "on")

    def _current_export_price_ct(self) -> float:
        # A separately configured effective export entity wins if it is valid.
        configured_effective = str(self.cfg.get(CONF_EFFECTIVE_EXPORT_PRICE, "") or "").strip()
        if configured_effective:
            effective = self._price_ct(self._entity(CONF_EFFECTIVE_EXPORT_PRICE))
            if effective is not None:
                return effective

        # The EPEX Spot Data entity's own state is the current market price.
        current = self._price_ct(self._entity(CONF_EPEX_PRICE))
        if current is not None:
            return current

        # Compatibility fallback for earlier config entries.
        current = self._price_ct(self._entity(CONF_EPEX_CURRENT_PRICE))
        return current if current is not None else 0.0

    def _current_import_price_eur(self) -> float:
        configured_total = str(self.cfg.get(CONF_IMPORT_TOTAL_PRICE, "") or "").strip()
        total_entity = self._entity(CONF_IMPORT_TOTAL_PRICE) if configured_total else ""
        price_ct = self._price_ct(total_entity) if total_entity else None
        return (
            price_ct / 100.0
            if price_ct is not None
            else float(self.cfg[CONF_IMPORT_FALLBACK_EUR_KWH])
        )

    def _miner_break_even_ct(self) -> float:
        hourly_value = (
            float(self.cfg[CONF_DOGE_PER_DAY])
            / 24.0
            * float(self.cfg[CONF_DOGE_TARGET_EUR])
        )
        return hourly_value / max(0.001, float(self.cfg[CONF_MINER_NOMINAL_POWER_KW])) * 100.0

    def _future_price_stats(
        self, now: datetime
    ) -> tuple[list[tuple[datetime, float]], float | None, float | None, float | None]:
        series_entity = self._entity(CONF_EPEX_PRICE)
        state = self.hass.states.get(series_entity)
        series = (
            future_prices(state.attributes, now, int(self.cfg[CONF_HORIZON_H]))
            if state
            else []
        )
        values = [price for _, price in series]
        if not values:
            return [], None, None, None
        ordered = sorted(values)
        low_quartile = ordered[max(0, int(len(ordered) * 0.25) - 1)]
        return series, min(values), max(values), low_quartile

    def _target_soc(
        self,
        current: float,
        series: list[tuple[datetime, float]],
        forecast: dict[str, Any],
    ) -> tuple[float, str]:
        minimum = float(self.cfg[CONF_BATTERY_MIN_SOC])
        tomorrow = float(forecast["tomorrow"])
        remaining = float(forecast["remaining"])
        if not series:
            return minimum, "No future EPEX series; minimum reserve."

        prices = sorted(price for _, price in series)
        p25 = prices[int((len(prices) - 1) * 0.25)]
        p50 = prices[int((len(prices) - 1) * 0.50)]
        p75 = prices[int((len(prices) - 1) * 0.75)]
        peak = max(prices)
        spread = peak - current

        if current <= p25 and spread >= 5:
            base, why = 95, "current price is in the cheapest quartile"
        elif current <= p50 and spread >= 3:
            base, why = 75, "current price is below the future median"
        elif current < p75 and spread >= 1.5:
            base, why = 55, "current price is moderately cheap"
        else:
            base, why = minimum, "current price offers no strong storage advantage"

        if tomorrow <= 25:
            pv_adj, pvwhy = 20, f"weak tomorrow forecast ({tomorrow:.1f} kWh)"
        elif tomorrow <= 45:
            pv_adj, pvwhy = 10, f"moderate tomorrow forecast ({tomorrow:.1f} kWh)"
        elif tomorrow >= 75:
            pv_adj, pvwhy = -20, f"strong tomorrow forecast ({tomorrow:.1f} kWh)"
        elif tomorrow >= 55:
            pv_adj, pvwhy = -10, f"good tomorrow forecast ({tomorrow:.1f} kWh)"
        else:
            pv_adj, pvwhy = 0, f"neutral tomorrow forecast ({tomorrow:.1f} kWh)"

        if remaining >= 15:
            pv_adj -= 10
            pvwhy += f", plus {remaining:.1f} kWh remaining today"

        target = max(minimum, min(95.0, base + pv_adj))
        return target, f"{why}; {pvwhy}. Future peak {peak:.2f} ct/kWh."

    def _miner_should_start(
        self,
        now: datetime,
        price: float,
        surplus: float,
        series: list[tuple[datetime, float]],
    ) -> bool:
        break_even = self._miner_break_even_ct()
        nominal = float(self.cfg[CONF_MINER_NOMINAL_POWER_KW])
        if price >= break_even or surplus < nominal:
            return False
        end = now + timedelta(minutes=int(self.cfg[CONF_MINER_MIN_RUNTIME_MIN]))
        window = [future_price for dt, future_price in series if now <= dt < end]
        return not window or max(window) < break_even

    def _reset_if_new_day(self, now: datetime) -> None:
        today = now.date().isoformat()
        if today != self.accumulation_date:
            self.accumulation_date = today
            self.accumulation_start = now.isoformat()
            self.metrics = self._fresh_metrics()
            self.last_actual_export_energy = None
            self.last_actual_import_energy = None

    async def _async_update_data(self) -> dict[str, Any]:
        await self._async_load()
        now = dt_util.now()
        self._reset_if_new_day(now)

        capacity = float(self.cfg[CONF_BATTERY_CAPACITY_KWH])
        min_soc = float(self.cfg[CONF_BATTERY_MIN_SOC])
        min_energy = capacity * min_soc / 100.0
        actual_soc = self._state_float(self._entity(CONF_BATTERY_SOC))

        if self.virtual_energy_kwh is None:
            start_soc = actual_soc if actual_soc is not None else min_soc
            self.virtual_energy_kwh = (
                capacity * max(min_soc, min(100.0, start_soc)) / 100.0
            )

        interval_h = float(self.cfg[CONF_INTERVAL_MIN]) / 60.0
        if self.last_update is not None:
            elapsed = (now - self.last_update).total_seconds() / 3600.0
            if 0 < elapsed < interval_h * 2.5:
                interval_h = elapsed
        self.last_update = now

        pv_kw = self._power_kw(self._entity(CONF_PV_POWER))
        house_kw = self._power_kw(self._entity(CONF_HOUSE_LOAD))
        actual_grid_import_kw = self._power_kw(self._entity(CONF_GRID_IMPORT_POWER))
        export_price_ct = self._current_export_price_ct()
        import_price_eur = self._current_import_price_eur()
        series, future_min, future_max, low_quartile = self._future_price_stats(now)
        forecast, forecast_sources = self._forecast()
        target_soc, target_reason = self._target_soc(
            export_price_ct, series, forecast
        )
        target_energy = capacity * target_soc / 100.0
        pv_surplus_kw = max(0.0, pv_kw - house_kw)

        locked = bool(self.miner_locked_until and now < self.miner_locked_until)
        if self.simulation_enabled:
            if locked:
                self.miner_simulated_on = True
            elif self._miner_should_start(
                now, export_price_ct, pv_surplus_kw, series
            ):
                self.miner_simulated_on = True
                self.miner_locked_until = now + timedelta(
                    minutes=int(self.cfg[CONF_MINER_MIN_RUNTIME_MIN])
                )
            else:
                self.miner_simulated_on = False
                self.miner_locked_until = None
        else:
            self.miner_simulated_on = False
            self.miner_locked_until = None

        sim_export_kw = 0.0
        sim_import_kw = 0.0
        sim_battery_charge_kw = 0.0
        sim_battery_discharge_kw = 0.0
        sim_self_supply_kw = 0.0
        miner_kw = (
            float(self.cfg[CONF_MINER_NOMINAL_POWER_KW])
            if self.miner_simulated_on
            else 0.0
        )

        if self.simulation_enabled:
            direct_house_kw = min(pv_kw, house_kw)
            sim_self_supply_kw += direct_house_kw
            house_deficit_kw = max(0.0, house_kw - pv_kw)

            if house_deficit_kw > 0 and self.virtual_energy_kwh > min_energy:
                available_kw = min(
                    float(self.cfg[CONF_BATTERY_MAX_DISCHARGE_KW]),
                    (self.virtual_energy_kwh - min_energy)
                    * float(self.cfg[CONF_BATTERY_DISCHARGE_EFFICIENCY])
                    / max(interval_h, 0.001),
                )
                sim_battery_discharge_kw = min(house_deficit_kw, available_kw)
                house_deficit_kw -= sim_battery_discharge_kw
                sim_self_supply_kw += sim_battery_discharge_kw
                self.virtual_energy_kwh -= (
                    sim_battery_discharge_kw
                    * interval_h
                    / float(self.cfg[CONF_BATTERY_DISCHARGE_EFFICIENCY])
                )

            sim_import_kw += house_deficit_kw
            remaining_pv_kw = max(0.0, pv_kw - house_kw)
            miner_from_pv_kw = min(remaining_pv_kw, miner_kw)
            remaining_pv_kw -= miner_from_pv_kw
            sim_import_kw += max(0.0, miner_kw - miner_from_pv_kw)

            if (
                self.virtual_energy_kwh < target_energy
                and remaining_pv_kw > 0
                and self.virtual_energy_kwh < capacity
            ):
                max_by_capacity_kw = (
                    (capacity - self.virtual_energy_kwh)
                    / max(interval_h, 0.001)
                    / float(self.cfg[CONF_BATTERY_CHARGE_EFFICIENCY])
                )
                sim_battery_charge_kw = min(
                    remaining_pv_kw,
                    float(self.cfg[CONF_BATTERY_MAX_CHARGE_KW]),
                    max_by_capacity_kw,
                )
                self.virtual_energy_kwh += (
                    sim_battery_charge_kw
                    * interval_h
                    * float(self.cfg[CONF_BATTERY_CHARGE_EFFICIENCY])
                )
                remaining_pv_kw -= sim_battery_charge_kw

            sim_export_kw = max(0.0, remaining_pv_kw)
            self.virtual_energy_kwh = min(
                capacity, max(min_energy, self.virtual_energy_kwh)
            )

            self.metrics["sim_export_kwh"] += sim_export_kw * interval_h
            self.metrics["sim_export_revenue_eur"] += (
                sim_export_kw * interval_h * export_price_ct / 100.0
            )
            self.metrics["sim_import_kwh"] += sim_import_kw * interval_h
            self.metrics["sim_import_cost_eur"] += (
                sim_import_kw * interval_h * import_price_eur
            )
            self.metrics["sim_self_supply_kwh"] += sim_self_supply_kw * interval_h
            self.metrics["sim_self_supply_value_eur"] += (
                sim_self_supply_kw * interval_h * import_price_eur
            )

            if self.miner_simulated_on:
                doge = float(self.cfg[CONF_DOGE_PER_DAY]) / 24.0 * interval_h
                self.metrics["sim_miner_hours"] += interval_h
                self.metrics["sim_doge"] += doge
                self.metrics["sim_mining_value_eur"] += (
                    doge * float(self.cfg[CONF_DOGE_TARGET_EUR])
                )

            self.metrics["actual_self_supply_value_eur"] += (
                max(0.0, house_kw - actual_grid_import_kw)
                * interval_h
                * import_price_eur
            )

            if self._actual_miner_on():
                doge = float(self.cfg[CONF_DOGE_PER_DAY]) / 24.0 * interval_h
                self.metrics["actual_miner_hours"] += interval_h
                self.metrics["actual_doge"] += doge
                self.metrics["actual_mining_value_eur"] += (
                    doge * float(self.cfg[CONF_DOGE_TARGET_EUR])
                )

            current_export_energy = self._energy_kwh(
                self._entity(CONF_GRID_EXPORT_ENERGY_TODAY)
            )
            current_import_energy = self._energy_kwh(
                self._entity(CONF_GRID_IMPORT_ENERGY_TODAY)
            )

            if (
                current_export_energy is not None
                and self.last_actual_export_energy is not None
            ):
                self.metrics["actual_export_revenue_eur"] += (
                    max(0.0, current_export_energy - self.last_actual_export_energy)
                    * export_price_ct
                    / 100.0
                )
            if (
                current_import_energy is not None
                and self.last_actual_import_energy is not None
            ):
                self.metrics["actual_import_cost_eur"] += (
                    max(0.0, current_import_energy - self.last_actual_import_energy)
                    * import_price_eur
                )

            self.last_actual_export_energy = current_export_energy
            self.last_actual_import_energy = current_import_energy

        simulated_benefit = (
            self.metrics["sim_export_revenue_eur"]
            + self.metrics["sim_self_supply_value_eur"]
            + self.metrics["sim_mining_value_eur"]
            - self.metrics["sim_import_cost_eur"]
        )
        actual_benefit = (
            self.metrics["actual_export_revenue_eur"]
            + self.metrics["actual_self_supply_value_eur"]
            + self.metrics["actual_mining_value_eur"]
            - self.metrics["actual_import_cost_eur"]
        )

        recommendation = "PAUSED"
        reason = "Simulation is off; no live control exists."
        if self.simulation_enabled:
            if self.miner_simulated_on:
                recommendation = "MINING_PRIORITY"
                reason = (
                    f"Mining value {self._miner_break_even_ct():.2f} ct/kWh exceeds "
                    f"export {export_price_ct:.2f} ct/kWh."
                )
            elif self.virtual_energy_kwh < target_energy and pv_surplus_kw > 0:
                recommendation = "CHARGE_PRIORITY"
                reason = f"Target SOC {target_soc:.0f}%. {target_reason}"
            elif pv_surplus_kw > 0:
                recommendation = "EXPORT_PRIORITY"
                reason = f"Reserve satisfied. {target_reason}"
            else:
                recommendation = "HOUSE_RESERVE"
                reason = (
                    f"No PV surplus; battery may serve house load down to "
                    f"{min_soc:.0f}%. {target_reason}"
                )

        epex_series_entity = self._entity(CONF_EPEX_PRICE)
        input_issues: list[str] = []
        if export_price_ct <= 0:
            input_issues.append("current EPEX price missing/zero")
        if not series:
            input_issues.append("future EPEX series missing")
        if float(forecast["today"]) <= 0:
            input_issues.append("Forecast.Solar today missing/zero")
        if float(forecast["tomorrow"]) <= 0:
            input_issues.append("Forecast.Solar tomorrow missing/zero")
        input_status = "OK" if not input_issues else "CHECK"

        log_entry = {
            "timestamp": now.isoformat(),
            "time_local": now.strftime("%H:%M"),
            "recommendation": recommendation,
            "reason": reason,
            "pv_kw": round(pv_kw, 3),
            "house_kw": round(house_kw, 3),
            "actual_soc": None if actual_soc is None else round(actual_soc, 1),
            "virtual_soc": round(self.virtual_energy_kwh / capacity * 100.0, 1),
            "target_soc": round(target_soc, 1),
            "export_price_ct": round(export_price_ct, 3),
            "import_price_eur": round(import_price_eur, 4),
            "future_min_ct": future_min,
            "future_max_ct": future_max,
            "forecast_remaining_kwh": round(float(forecast["remaining"]), 2),
            "forecast_tomorrow_kwh": round(float(forecast["tomorrow"]), 2),
            "miner_on": self.miner_simulated_on,
            "sim_export_kw": round(sim_export_kw, 3),
            "sim_import_kw": round(sim_import_kw, 3),
            "sim_battery_charge_kw": round(sim_battery_charge_kw, 3),
            "sim_battery_discharge_kw": round(sim_battery_discharge_kw, 3),
            "simulated_net_benefit_eur": round(simulated_benefit, 3),
            "observed_net_benefit_eur": round(actual_benefit, 3),
            "advantage_eur": round(simulated_benefit - actual_benefit, 3),
        }
        self.decision_log = append_decision_log(self.decision_log, log_entry)

        data = {
            **self.metrics,
            "build_version": BUILD_VERSION,
            "input_status": input_status,
            "input_issues": input_issues,
            "simulation_enabled": self.simulation_enabled,
            "recommendation": recommendation,
            "reason": reason,
            "target_reason": target_reason,
            "virtual_soc": self.virtual_energy_kwh / capacity * 100.0,
            "target_soc": target_soc,
            "actual_soc": actual_soc,
            "pv_kw": pv_kw,
            "house_kw": house_kw,
            "sim_export_kw": sim_export_kw,
            "sim_import_kw": sim_import_kw,
            "sim_battery_charge_kw": sim_battery_charge_kw,
            "sim_battery_discharge_kw": sim_battery_discharge_kw,
            "miner_simulated_on": self.miner_simulated_on,
            "miner_break_even_ct": self._miner_break_even_ct(),
            "export_price_ct": export_price_ct,
            "import_price_eur": import_price_eur,
            "future_price_points": len(series),
            "future_min_ct": future_min,
            "future_max_ct": future_max,
            "low_quartile_ct": low_quartile,
            "forecast_today_kwh": forecast["today"],
            "forecast_remaining_today_kwh": forecast["remaining"],
            "forecast_tomorrow_kwh": forecast["tomorrow"],
            "forecast_next_hour_kwh": forecast["next_hour"],
            "forecast_peak_tomorrow": forecast["peak_tomorrow"].isoformat()
            if forecast["peak_tomorrow"]
            else None,
            "simulated_benefit_eur": simulated_benefit,
            "actual_benefit_eur": actual_benefit,
            "advantage_eur": simulated_benefit - actual_benefit,
            "accumulation_start": self.accumulation_start,
            "last_decision": format_decision(log_entry),
            "decision_log": self.decision_log,
            "decision_log_count": len(self.decision_log),
            "resolved_epex_series_entity": epex_series_entity,
            "raw_epex_state": self._raw_state(epex_series_entity),
            "resolved_forecast_today_1": forecast_sources["today_1"],
            "resolved_forecast_today_2": forecast_sources["today_2"],
            "resolved_forecast_tomorrow_1": forecast_sources["tomorrow_1"],
            "resolved_forecast_tomorrow_2": forecast_sources["tomorrow_2"],
            "raw_forecast_today_1": self._raw_state(forecast_sources["today_1"]),
            "raw_forecast_today_2": self._raw_state(forecast_sources["today_2"]),
            "raw_forecast_tomorrow_1": self._raw_state(forecast_sources["tomorrow_1"]),
            "raw_forecast_tomorrow_2": self._raw_state(forecast_sources["tomorrow_2"]),
        }
        await self._async_save()
        return data

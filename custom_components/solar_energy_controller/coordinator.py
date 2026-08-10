# File: custom_components/solar_energy_controller/coordinator.py
# Timestamp: 2026-08-10 22:00 CEST

from __future__ import annotations

from datetime import datetime, timedelta
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from .const import (
    CONF_BATTERY_CAPACITY_KWH, CONF_BATTERY_CHARGE_EFFICIENCY,
    CONF_BATTERY_DISCHARGE_EFFICIENCY, CONF_BATTERY_MAX_CHARGE_KW,
    CONF_BATTERY_MAX_DISCHARGE_KW, CONF_BATTERY_MIN_SOC, CONF_BATTERY_SOC,
    CONF_DOGE_PER_DAY, CONF_DOGE_TARGET_EUR, CONF_EFFECTIVE_EXPORT_PRICE,
    CONF_EPEX_PRICE, CONF_GRID_EXPORT_ENERGY_TODAY, CONF_GRID_IMPORT_ENERGY_TODAY,
    CONF_GRID_IMPORT_POWER, CONF_HORIZON_H, CONF_HOUSE_LOAD,
    CONF_IMPORT_FALLBACK_EUR_KWH, CONF_IMPORT_TOTAL_PRICE, CONF_INTERVAL_MIN,
    CONF_MINER_MIN_RUNTIME_MIN, CONF_MINER_NOMINAL_POWER_KW, CONF_MINER_SWITCH,
    CONF_PV_POWER, DEFAULTS, DOMAIN, STORAGE_KEY, STORAGE_VERSION,
)
from .price_parser import future_prices

_LOGGER = logging.getLogger(__name__)


class SolarEnergyControllerCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Economic shadow controller. Version 0.1.x never writes to devices."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.entry = entry
        self.cfg = {**DEFAULTS, **entry.data, **entry.options}
        super().__init__(hass, _LOGGER, name=DOMAIN,
                         update_interval=timedelta(minutes=int(self.cfg[CONF_INTERVAL_MIN])))
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

    @staticmethod
    def _fresh_metrics() -> dict[str, float]:
        return {k: 0.0 for k in (
            "sim_export_kwh", "sim_export_revenue_eur", "sim_import_kwh", "sim_import_cost_eur",
            "sim_self_supply_kwh", "sim_self_supply_value_eur", "sim_miner_hours", "sim_doge",
            "sim_mining_value_eur", "actual_export_revenue_eur", "actual_import_cost_eur",
            "actual_self_supply_value_eur", "actual_miner_hours", "actual_doge", "actual_mining_value_eur")}

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
        self._loaded = True

    async def async_set_simulation_enabled(self, enabled: bool) -> None:
        self.simulation_enabled = enabled
        await self._async_save()
        await self.async_request_refresh()

    async def _async_save(self) -> None:
        await self._store.async_save({
            "simulation_enabled": self.simulation_enabled,
            "virtual_energy_kwh": self.virtual_energy_kwh,
            "miner_simulated_on": self.miner_simulated_on,
            "miner_locked_until": self.miner_locked_until.isoformat() if self.miner_locked_until else None,
            "accumulation_date": self.accumulation_date,
            "accumulation_start": self.accumulation_start,
            "metrics": self.metrics,
        })

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
        lowered = unit.lower().replace(" ", "")
        return value * 100.0 if "€/kwh" in lowered or "eur/kwh" in lowered else value

    def _actual_miner_on(self) -> bool:
        state = self.hass.states.get(self.cfg[CONF_MINER_SWITCH]) if self.cfg[CONF_MINER_SWITCH] else None
        return bool(state and state.state == "on")

    def _current_export_price_ct(self) -> float:
        effective = self._price_ct(self.cfg[CONF_EFFECTIVE_EXPORT_PRICE])
        return effective if effective is not None else (self._price_ct(self.cfg[CONF_EPEX_PRICE]) or 0.0)

    def _current_import_price_eur(self) -> float:
        entity = self.cfg[CONF_IMPORT_TOTAL_PRICE]
        price_ct = self._price_ct(entity) if entity else None
        return price_ct / 100.0 if price_ct is not None else float(self.cfg[CONF_IMPORT_FALLBACK_EUR_KWH])

    def _miner_break_even_ct(self) -> float:
        power_kw = max(0.001, float(self.cfg[CONF_MINER_NOMINAL_POWER_KW]))
        eur_per_hour = float(self.cfg[CONF_DOGE_PER_DAY]) / 24.0 * float(self.cfg[CONF_DOGE_TARGET_EUR])
        return eur_per_hour / power_kw * 100.0

    def _future_price_stats(self, now: datetime):
        state = self.hass.states.get(self.cfg[CONF_EPEX_PRICE])
        if state is None:
            return [], None, None, None
        series = future_prices(state.attributes, now, int(self.cfg[CONF_HORIZON_H]))
        values = [p for _, p in series]
        if not values:
            return [], None, None, None
        ordered = sorted(values)
        low = ordered[max(0, int(len(ordered) * 0.25) - 1)]
        return series, min(values), max(values), low

    def _target_soc(self, current_price_ct: float, series: list[tuple[datetime, float]]) -> tuple[float, str]:
        """Derive reserve from upcoming prices instead of a fixed time-of-day SOC schedule."""
        minimum = float(self.cfg[CONF_BATTERY_MIN_SOC])
        if not series:
            return minimum, "No future EPEX series available; keep minimum reserve."

        prices = sorted(price for _, price in series)
        p25 = prices[max(0, int((len(prices) - 1) * 0.25))]
        p50 = prices[max(0, int((len(prices) - 1) * 0.50))]
        p75 = prices[max(0, int((len(prices) - 1) * 0.75))]
        future_peak = max(prices)
        spread = future_peak - current_price_ct

        # Cheap energy now and a meaningful expensive period ahead: build reserve.
        if current_price_ct <= p25 and spread >= 5.0:
            target = 95.0
            reason = f"Current price is in the cheapest quartile and a {future_peak:.2f} ct/kWh peak is ahead."
        elif current_price_ct <= p50 and spread >= 3.0:
            target = 75.0
            reason = f"Current price is below the future median with {spread:.2f} ct/kWh upside ahead."
        elif current_price_ct < p75 and spread >= 1.5:
            target = 55.0
            reason = "Moderately cheap current price; retain a medium battery reserve for higher prices."
        else:
            target = minimum
            reason = "Current energy is not cheap enough versus the forecast; no extra battery reserve."

        return min(100.0, max(minimum, target)), reason

    def _miner_should_start(self, now: datetime, export_price_ct: float, pv_surplus_kw: float,
                            series: list[tuple[datetime, float]]) -> bool:
        break_even = self._miner_break_even_ct()
        nominal = float(self.cfg[CONF_MINER_NOMINAL_POWER_KW])
        if export_price_ct >= break_even or pv_surplus_kw < nominal:
            return False
        window_end = now + timedelta(minutes=int(self.cfg[CONF_MINER_MIN_RUNTIME_MIN]))
        future_window = [price for dt, price in series if now <= dt < window_end]
        return not future_window or max(future_window) < break_even

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
        actual_soc = self._state_float(self.cfg[CONF_BATTERY_SOC])
        if self.virtual_energy_kwh is None:
            start_soc = actual_soc if actual_soc is not None else min_soc
            self.virtual_energy_kwh = capacity * max(min_soc, min(100.0, start_soc)) / 100.0

        interval_h = float(self.cfg[CONF_INTERVAL_MIN]) / 60.0
        if self.last_update is not None:
            elapsed = (now - self.last_update).total_seconds() / 3600.0
            if 0 < elapsed < interval_h * 2.5:
                interval_h = elapsed
        self.last_update = now

        pv_kw = self._power_kw(self.cfg[CONF_PV_POWER])
        house_kw = self._power_kw(self.cfg[CONF_HOUSE_LOAD])
        actual_grid_import_kw = self._power_kw(self.cfg[CONF_GRID_IMPORT_POWER])
        export_price_ct = self._current_export_price_ct()
        import_price_eur = self._current_import_price_eur()
        series, future_min, future_max, low_quartile = self._future_price_stats(now)
        target_soc, target_reason = self._target_soc(export_price_ct, series)
        target_energy = capacity * target_soc / 100.0
        pv_surplus_kw = max(0.0, pv_kw - house_kw)

        locked = bool(self.miner_locked_until and now < self.miner_locked_until)
        if self.simulation_enabled:
            if locked:
                self.miner_simulated_on = True
            elif self._miner_should_start(now, export_price_ct, pv_surplus_kw, series):
                self.miner_simulated_on = True
                self.miner_locked_until = now + timedelta(minutes=int(self.cfg[CONF_MINER_MIN_RUNTIME_MIN]))
            else:
                self.miner_simulated_on = False
                self.miner_locked_until = None
        else:
            self.miner_simulated_on = False
            self.miner_locked_until = None

        sim_export_kw = sim_import_kw = sim_battery_charge_kw = sim_battery_discharge_kw = sim_self_supply_kw = 0.0
        miner_kw = float(self.cfg[CONF_MINER_NOMINAL_POWER_KW]) if self.miner_simulated_on else 0.0

        if self.simulation_enabled:
            direct_house_kw = min(pv_kw, house_kw)
            sim_self_supply_kw += direct_house_kw
            house_deficit_kw = max(0.0, house_kw - pv_kw)
            if house_deficit_kw > 0 and self.virtual_energy_kwh > min_energy:
                available_kw = min(float(self.cfg[CONF_BATTERY_MAX_DISCHARGE_KW]),
                    (self.virtual_energy_kwh - min_energy) * float(self.cfg[CONF_BATTERY_DISCHARGE_EFFICIENCY]) / max(interval_h, 0.001))
                sim_battery_discharge_kw = min(house_deficit_kw, available_kw)
                house_deficit_kw -= sim_battery_discharge_kw
                sim_self_supply_kw += sim_battery_discharge_kw
                self.virtual_energy_kwh -= sim_battery_discharge_kw * interval_h / float(self.cfg[CONF_BATTERY_DISCHARGE_EFFICIENCY])
            sim_import_kw += house_deficit_kw

            remaining_pv_kw = max(0.0, pv_kw - house_kw)
            miner_from_pv_kw = min(remaining_pv_kw, miner_kw)
            remaining_pv_kw -= miner_from_pv_kw
            sim_import_kw += max(0.0, miner_kw - miner_from_pv_kw)

            if self.virtual_energy_kwh < target_energy and remaining_pv_kw > 0 and self.virtual_energy_kwh < capacity:
                max_by_capacity_kw = (capacity - self.virtual_energy_kwh) / max(interval_h, 0.001) / float(self.cfg[CONF_BATTERY_CHARGE_EFFICIENCY])
                sim_battery_charge_kw = min(remaining_pv_kw, float(self.cfg[CONF_BATTERY_MAX_CHARGE_KW]), max_by_capacity_kw)
                self.virtual_energy_kwh += sim_battery_charge_kw * interval_h * float(self.cfg[CONF_BATTERY_CHARGE_EFFICIENCY])
                remaining_pv_kw -= sim_battery_charge_kw
            sim_export_kw = max(0.0, remaining_pv_kw)
            self.virtual_energy_kwh = min(capacity, max(min_energy, self.virtual_energy_kwh))

            self.metrics["sim_export_kwh"] += sim_export_kw * interval_h
            self.metrics["sim_export_revenue_eur"] += sim_export_kw * interval_h * export_price_ct / 100.0
            self.metrics["sim_import_kwh"] += sim_import_kw * interval_h
            self.metrics["sim_import_cost_eur"] += sim_import_kw * interval_h * import_price_eur
            self.metrics["sim_self_supply_kwh"] += sim_self_supply_kw * interval_h
            self.metrics["sim_self_supply_value_eur"] += sim_self_supply_kw * interval_h * import_price_eur
            if self.miner_simulated_on:
                doge = float(self.cfg[CONF_DOGE_PER_DAY]) / 24.0 * interval_h
                self.metrics["sim_miner_hours"] += interval_h
                self.metrics["sim_doge"] += doge
                self.metrics["sim_mining_value_eur"] += doge * float(self.cfg[CONF_DOGE_TARGET_EUR])

            actual_local_supply_kw = max(0.0, house_kw - actual_grid_import_kw)
            self.metrics["actual_self_supply_value_eur"] += actual_local_supply_kw * interval_h * import_price_eur
            if self._actual_miner_on():
                doge = float(self.cfg[CONF_DOGE_PER_DAY]) / 24.0 * interval_h
                self.metrics["actual_miner_hours"] += interval_h
                self.metrics["actual_doge"] += doge
                self.metrics["actual_mining_value_eur"] += doge * float(self.cfg[CONF_DOGE_TARGET_EUR])

            current_export_energy = self._energy_kwh(self.cfg[CONF_GRID_EXPORT_ENERGY_TODAY])
            if current_export_energy is not None and self.last_actual_export_energy is not None:
                self.metrics["actual_export_revenue_eur"] += max(0.0, current_export_energy - self.last_actual_export_energy) * export_price_ct / 100.0
            self.last_actual_export_energy = current_export_energy
            current_import_energy = self._energy_kwh(self.cfg[CONF_GRID_IMPORT_ENERGY_TODAY])
            if current_import_energy is not None and self.last_actual_import_energy is not None:
                self.metrics["actual_import_cost_eur"] += max(0.0, current_import_energy - self.last_actual_import_energy) * import_price_eur
            self.last_actual_import_energy = current_import_energy

        simulated_benefit = self.metrics["sim_export_revenue_eur"] + self.metrics["sim_self_supply_value_eur"] + self.metrics["sim_mining_value_eur"]
        actual_benefit = self.metrics["actual_export_revenue_eur"] + self.metrics["actual_self_supply_value_eur"] + self.metrics["actual_mining_value_eur"]
        recommendation, reason = "PAUSED", "Simulation is switched off; no live control is available."
        if self.simulation_enabled:
            if self.miner_simulated_on:
                recommendation = "MINING_PRIORITY"
                reason = f"Miner simulated ON: export {export_price_ct:.2f} ct/kWh is below mining value {self._miner_break_even_ct():.2f} ct/kWh."
            elif self.virtual_energy_kwh < target_energy and pv_surplus_kw > 0:
                recommendation = "CHARGE_PRIORITY"
                reason = f"Price-aware target SOC is {target_soc:.0f}%. {target_reason}"
            elif pv_surplus_kw > 0:
                recommendation = "EXPORT_PRIORITY"
                reason = f"Battery reserve target is satisfied. {target_reason}"
            else:
                recommendation = "HOUSE_RESERVE"
                reason = f"No PV surplus; battery is available for house load down to {min_soc:.0f}% minimum SOC."

        data = {**self.metrics, "simulation_enabled": self.simulation_enabled, "recommendation": recommendation,
            "reason": reason, "target_reason": target_reason, "virtual_soc": self.virtual_energy_kwh / capacity * 100.0,
            "target_soc": target_soc, "actual_soc": actual_soc, "pv_kw": pv_kw, "house_kw": house_kw,
            "sim_export_kw": sim_export_kw, "sim_import_kw": sim_import_kw,
            "sim_battery_charge_kw": sim_battery_charge_kw, "sim_battery_discharge_kw": sim_battery_discharge_kw,
            "miner_simulated_on": self.miner_simulated_on,
            "miner_locked_until": self.miner_locked_until.isoformat() if self.miner_locked_until else None,
            "miner_break_even_ct": self._miner_break_even_ct(), "export_price_ct": export_price_ct,
            "import_price_eur": import_price_eur, "future_price_points": len(series), "future_min_ct": future_min,
            "future_max_ct": future_max, "low_quartile_ct": low_quartile,
            "simulated_benefit_eur": simulated_benefit, "actual_benefit_eur": actual_benefit,
            "advantage_eur": simulated_benefit - actual_benefit, "accumulation_start": self.accumulation_start}
        await self._async_save()
        return data

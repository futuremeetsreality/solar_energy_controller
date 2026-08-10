# File: custom_components/solar_energy_controller/config_flow.py
# Timestamp: 2026-08-10 20:29 CEST

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.selector import NumberSelector, NumberSelectorConfig, TextSelector

from .const import (
    CONF_BATTERY_CAPACITY_KWH,
    CONF_BATTERY_CHARGE_EFFICIENCY,
    CONF_BATTERY_DISCHARGE_EFFICIENCY,
    CONF_BATTERY_MAX_CHARGE_KW,
    CONF_BATTERY_MAX_DISCHARGE_KW,
    CONF_BATTERY_MIN_SOC,
    CONF_BATTERY_POWER,
    CONF_BATTERY_SOC,
    CONF_DOGE_PER_DAY,
    CONF_DOGE_TARGET_EUR,
    CONF_EFFECTIVE_EXPORT_PRICE,
    CONF_EPEX_PRICE,
    CONF_GRID_EXPORT_ENERGY_TODAY,
    CONF_GRID_EXPORT_POWER,
    CONF_GRID_IMPORT_ENERGY_TODAY,
    CONF_GRID_IMPORT_POWER,
    CONF_HORIZON_H,
    CONF_HOUSE_LOAD,
    CONF_IMPORT_FALLBACK_EUR_KWH,
    CONF_IMPORT_TOTAL_PRICE,
    CONF_INTERVAL_MIN,
    CONF_MINER_MIN_RUNTIME_MIN,
    CONF_MINER_NOMINAL_POWER_KW,
    CONF_MINER_POWER,
    CONF_MINER_SWITCH,
    CONF_PV_ENERGY_TODAY,
    CONF_PV_POWER,
    DEFAULTS,
    DOMAIN,
)


def _text(key: str) -> Any:
    return vol.Required(key, default=DEFAULTS[key])


class SolarEnergyControllerConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Configure Solar Energy Controller."""

    VERSION = 1

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        if user_input is not None:
            self._data.update(user_input)
            return await self.async_step_battery()

        schema = vol.Schema(
            {
                _text(CONF_PV_POWER): TextSelector(),
                _text(CONF_PV_ENERGY_TODAY): TextSelector(),
                _text(CONF_HOUSE_LOAD): TextSelector(),
                _text(CONF_GRID_EXPORT_POWER): TextSelector(),
                _text(CONF_GRID_IMPORT_POWER): TextSelector(),
                _text(CONF_GRID_EXPORT_ENERGY_TODAY): TextSelector(),
                _text(CONF_GRID_IMPORT_ENERGY_TODAY): TextSelector(),
                _text(CONF_BATTERY_SOC): TextSelector(),
                _text(CONF_BATTERY_POWER): TextSelector(),
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema)

    async def async_step_battery(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        if user_input is not None:
            self._data.update(user_input)
            return await self.async_step_prices()

        schema = vol.Schema(
            {
                vol.Required(CONF_BATTERY_CAPACITY_KWH, default=12.5): NumberSelector(NumberSelectorConfig(min=1, max=100, step=0.1, unit_of_measurement="kWh")),
                vol.Required(CONF_BATTERY_MIN_SOC, default=25): NumberSelector(NumberSelectorConfig(min=0, max=100, step=1, unit_of_measurement="%")),
                vol.Required(CONF_BATTERY_MAX_CHARGE_KW, default=8): NumberSelector(NumberSelectorConfig(min=0.1, max=50, step=0.1, unit_of_measurement="kW")),
                vol.Required(CONF_BATTERY_MAX_DISCHARGE_KW, default=8): NumberSelector(NumberSelectorConfig(min=0.1, max=50, step=0.1, unit_of_measurement="kW")),
                vol.Required(CONF_BATTERY_CHARGE_EFFICIENCY, default=0.95): NumberSelector(NumberSelectorConfig(min=0.5, max=1.0, step=0.01)),
                vol.Required(CONF_BATTERY_DISCHARGE_EFFICIENCY, default=0.95): NumberSelector(NumberSelectorConfig(min=0.5, max=1.0, step=0.01)),
            }
        )
        return self.async_show_form(step_id="battery", data_schema=schema)

    async def async_step_prices(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        if user_input is not None:
            self._data.update(user_input)
            return await self.async_step_miner()

        schema = vol.Schema(
            {
                _text(CONF_EPEX_PRICE): TextSelector(),
                vol.Optional(CONF_EFFECTIVE_EXPORT_PRICE, default=""): TextSelector(),
                vol.Optional(CONF_IMPORT_TOTAL_PRICE, default=""): TextSelector(),
                vol.Required(CONF_IMPORT_FALLBACK_EUR_KWH, default=0.348): NumberSelector(NumberSelectorConfig(min=0, max=2, step=0.001, unit_of_measurement="€/kWh")),
            }
        )
        return self.async_show_form(step_id="prices", data_schema=schema)

    async def async_step_miner(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        if user_input is not None:
            self._data.update(user_input)
            return await self.async_step_controller()

        schema = vol.Schema(
            {
                _text(CONF_MINER_SWITCH): TextSelector(),
                _text(CONF_MINER_POWER): TextSelector(),
                vol.Required(CONF_MINER_NOMINAL_POWER_KW, default=1.0): NumberSelector(NumberSelectorConfig(min=0.05, max=20, step=0.05, unit_of_measurement="kW")),
                vol.Required(CONF_MINER_MIN_RUNTIME_MIN, default=60): NumberSelector(NumberSelectorConfig(min=15, max=720, step=15, unit_of_measurement="min")),
                vol.Required(CONF_DOGE_PER_DAY, default=12.0): NumberSelector(NumberSelectorConfig(min=0, max=10000, step=0.1, unit_of_measurement="DOGE/day")),
                vol.Required(CONF_DOGE_TARGET_EUR, default=0.20): NumberSelector(NumberSelectorConfig(min=0, max=10, step=0.01, unit_of_measurement="€/DOGE")),
            }
        )
        return self.async_show_form(step_id="miner", data_schema=schema)

    async def async_step_controller(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        if user_input is not None:
            self._data.update(user_input)
            await self.async_set_unique_id(DOMAIN)
            self._abort_if_unique_id_configured()
            return self.async_create_entry(title="Solar Energy Controller", data=self._data)

        schema = vol.Schema(
            {
                vol.Required(CONF_INTERVAL_MIN, default=15): NumberSelector(NumberSelectorConfig(min=5, max=60, step=5, unit_of_measurement="min")),
                vol.Required(CONF_HORIZON_H, default=24): NumberSelector(NumberSelectorConfig(min=6, max=48, step=1, unit_of_measurement="h")),
            }
        )
        return self.async_show_form(step_id="controller", data_schema=schema)

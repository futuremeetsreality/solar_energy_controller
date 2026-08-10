# File: custom_components/solar_energy_controller/switch.py
# Timestamp: 2026-08-10 20:29 CEST

from __future__ import annotations

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import SolarEnergyControllerCoordinator


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    coordinator: SolarEnergyControllerCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([SimulationSwitch(coordinator, entry)])


class SimulationSwitch(CoordinatorEntity[SolarEnergyControllerCoordinator], SwitchEntity):
    """Enable or pause the shadow simulation.

    Version 0.1.0 never performs live writes, regardless of switch state.
    """

    _attr_name = "Simulation"
    _attr_icon = "mdi:test-tube"
    _attr_has_entity_name = True

    def __init__(self, coordinator: SolarEnergyControllerCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_simulation"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name="Solar Energy Controller",
            manufacturer="futuremeetsreality",
            model="Simulation Controller",
            sw_version="0.1.0",
        )

    @property
    def is_on(self) -> bool:
        return self.coordinator.simulation_enabled

    async def async_turn_on(self, **kwargs) -> None:
        await self.coordinator.async_set_simulation_enabled(True)

    async def async_turn_off(self, **kwargs) -> None:
        await self.coordinator.async_set_simulation_enabled(False)

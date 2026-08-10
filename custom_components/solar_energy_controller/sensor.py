# File: custom_components/solar_energy_controller/sensor.py
# Timestamp: 2026-08-10 20:29 CEST

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorEntityDescription, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, UnitOfEnergy, UnitOfPower
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import SolarEnergyControllerCoordinator


@dataclass(frozen=True, kw_only=True)
class SECSensorDescription(SensorEntityDescription):
    value_fn: Callable[[dict[str, Any]], Any]


SENSORS: tuple[SECSensorDescription, ...] = (
    SECSensorDescription(key="recommendation", name="Recommended mode", value_fn=lambda d: d.get("recommendation"), icon="mdi:state-machine"),
    SECSensorDescription(key="virtual_soc", name="Simulated battery SOC", native_unit_of_measurement=PERCENTAGE, device_class=SensorDeviceClass.BATTERY, state_class=SensorStateClass.MEASUREMENT, value_fn=lambda d: round(d.get("virtual_soc", 0), 1)),
    SECSensorDescription(key="target_soc", name="Target battery SOC", native_unit_of_measurement=PERCENTAGE, device_class=SensorDeviceClass.BATTERY, state_class=SensorStateClass.MEASUREMENT, value_fn=lambda d: round(d.get("target_soc", 0), 1)),
    SECSensorDescription(key="sim_export_power", name="Simulated export power", native_unit_of_measurement=UnitOfPower.KILO_WATT, device_class=SensorDeviceClass.POWER, state_class=SensorStateClass.MEASUREMENT, value_fn=lambda d: round(d.get("sim_export_kw", 0), 3)),
    SECSensorDescription(key="sim_import_power", name="Simulated import power", native_unit_of_measurement=UnitOfPower.KILO_WATT, device_class=SensorDeviceClass.POWER, state_class=SensorStateClass.MEASUREMENT, value_fn=lambda d: round(d.get("sim_import_kw", 0), 3)),
    SECSensorDescription(key="sim_battery_charge_power", name="Simulated battery charge power", native_unit_of_measurement=UnitOfPower.KILO_WATT, device_class=SensorDeviceClass.POWER, state_class=SensorStateClass.MEASUREMENT, value_fn=lambda d: round(d.get("sim_battery_charge_kw", 0), 3)),
    SECSensorDescription(key="sim_battery_discharge_power", name="Simulated battery discharge power", native_unit_of_measurement=UnitOfPower.KILO_WATT, device_class=SensorDeviceClass.POWER, state_class=SensorStateClass.MEASUREMENT, value_fn=lambda d: round(d.get("sim_battery_discharge_kw", 0), 3)),
    SECSensorDescription(key="sim_export_energy", name="Simulated export energy today", native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR, device_class=SensorDeviceClass.ENERGY, state_class=SensorStateClass.TOTAL_INCREASING, value_fn=lambda d: round(d.get("sim_export_kwh", 0), 3)),
    SECSensorDescription(key="sim_import_energy", name="Simulated import energy today", native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR, device_class=SensorDeviceClass.ENERGY, state_class=SensorStateClass.TOTAL_INCREASING, value_fn=lambda d: round(d.get("sim_import_kwh", 0), 3)),
    SECSensorDescription(key="sim_export_revenue", name="Simulated export revenue today", native_unit_of_measurement="€", device_class=SensorDeviceClass.MONETARY, state_class=SensorStateClass.TOTAL, value_fn=lambda d: round(d.get("sim_export_revenue_eur", 0), 3)),
    SECSensorDescription(key="sim_self_supply_value", name="Simulated self-consumption saving today", native_unit_of_measurement="€", device_class=SensorDeviceClass.MONETARY, state_class=SensorStateClass.TOTAL, value_fn=lambda d: round(d.get("sim_self_supply_value_eur", 0), 3)),
    SECSensorDescription(key="sim_mining_value", name="Simulated mining value today", native_unit_of_measurement="€", device_class=SensorDeviceClass.MONETARY, state_class=SensorStateClass.TOTAL, value_fn=lambda d: round(d.get("sim_mining_value_eur", 0), 3)),
    SECSensorDescription(key="sim_doge", name="Simulated DOGE today", native_unit_of_measurement="DOGE", state_class=SensorStateClass.TOTAL, value_fn=lambda d: round(d.get("sim_doge", 0), 3)),
    SECSensorDescription(key="sim_miner_hours", name="Simulated miner runtime today", native_unit_of_measurement="h", state_class=SensorStateClass.TOTAL, value_fn=lambda d: round(d.get("sim_miner_hours", 0), 2)),
    SECSensorDescription(key="mining_break_even", name="Mining break-even export price", native_unit_of_measurement="ct/kWh", state_class=SensorStateClass.MEASUREMENT, value_fn=lambda d: round(d.get("miner_break_even_ct", 0), 3)),
    SECSensorDescription(key="export_price", name="Effective export price", native_unit_of_measurement="ct/kWh", state_class=SensorStateClass.MEASUREMENT, value_fn=lambda d: round(d.get("export_price_ct", 0), 3)),
    SECSensorDescription(key="simulated_benefit", name="Simulated total benefit today", native_unit_of_measurement="€", device_class=SensorDeviceClass.MONETARY, state_class=SensorStateClass.TOTAL, value_fn=lambda d: round(d.get("simulated_benefit_eur", 0), 3)),
    SECSensorDescription(key="actual_benefit", name="Observed total benefit today", native_unit_of_measurement="€", device_class=SensorDeviceClass.MONETARY, state_class=SensorStateClass.TOTAL, value_fn=lambda d: round(d.get("actual_benefit_eur", 0), 3)),
    SECSensorDescription(key="advantage", name="Simulation advantage today", native_unit_of_measurement="€", device_class=SensorDeviceClass.MONETARY, state_class=SensorStateClass.MEASUREMENT, value_fn=lambda d: round(d.get("advantage_eur", 0), 3)),
    SECSensorDescription(key="future_min_price", name="Future minimum EPEX price", native_unit_of_measurement="ct/kWh", state_class=SensorStateClass.MEASUREMENT, value_fn=lambda d: None if d.get("future_min_ct") is None else round(d["future_min_ct"], 3)),
    SECSensorDescription(key="future_max_price", name="Future maximum EPEX price", native_unit_of_measurement="ct/kWh", state_class=SensorStateClass.MEASUREMENT, value_fn=lambda d: None if d.get("future_max_ct") is None else round(d["future_max_ct"], 3)),
)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    coordinator: SolarEnergyControllerCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(SECSensor(coordinator, entry, description) for description in SENSORS)


class SECSensor(CoordinatorEntity[SolarEnergyControllerCoordinator], SensorEntity):
    entity_description: SECSensorDescription
    _attr_has_entity_name = True

    def __init__(self, coordinator: SolarEnergyControllerCoordinator, entry: ConfigEntry, description: SECSensorDescription) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{entry.entry_id}_{description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name="Solar Energy Controller",
            manufacturer="futuremeetsreality",
            model="Simulation Controller",
            sw_version="0.1.0",
        )

    @property
    def native_value(self) -> Any:
        return self.entity_description.value_fn(self.coordinator.data or {})

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        if self.entity_description.key != "recommendation":
            return None
        data = self.coordinator.data or {}
        return {
            "reason": data.get("reason"),
            "simulation_enabled": data.get("simulation_enabled"),
            "miner_simulated_on": data.get("miner_simulated_on"),
            "miner_locked_until": data.get("miner_locked_until"),
            "future_price_points": data.get("future_price_points"),
            "accumulation_start": data.get("accumulation_start"),
        }

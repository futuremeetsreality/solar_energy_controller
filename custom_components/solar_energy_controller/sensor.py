# File: custom_components/solar_energy_controller/sensor.py
# Timestamp: 2026-08-11 07:38 CEST
from __future__ import annotations
from dataclasses import dataclass
from typing import Any,Callable
from homeassistant.components.sensor import SensorDeviceClass,SensorEntity,SensorEntityDescription,SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE,UnitOfEnergy,UnitOfPower
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from .const import DOMAIN
from .coordinator import SolarEnergyControllerCoordinator
@dataclass(frozen=True,kw_only=True)
class SECSensorDescription(SensorEntityDescription): value_fn:Callable[[dict[str,Any]],Any]
SENSORS=(
SECSensorDescription(key="recommendation",name="Recommended mode",value_fn=lambda d:d.get("recommendation"),icon="mdi:state-machine"),
SECSensorDescription(key="decision_log",name="Simulation decision log",value_fn=lambda d:d.get("last_decision","No decision yet"),icon="mdi:text-box-search-outline"),
SECSensorDescription(key="virtual_soc",name="Simulated battery SOC",native_unit_of_measurement=PERCENTAGE,device_class=SensorDeviceClass.BATTERY,state_class=SensorStateClass.MEASUREMENT,value_fn=lambda d:round(d.get("virtual_soc",0),1)),
SECSensorDescription(key="target_soc",name="Target battery SOC",native_unit_of_measurement=PERCENTAGE,device_class=SensorDeviceClass.BATTERY,state_class=SensorStateClass.MEASUREMENT,value_fn=lambda d:round(d.get("target_soc",0),1)),
SECSensorDescription(key="sim_export_power",name="Simulated export power",native_unit_of_measurement=UnitOfPower.KILO_WATT,device_class=SensorDeviceClass.POWER,state_class=SensorStateClass.MEASUREMENT,value_fn=lambda d:round(d.get("sim_export_kw",0),3)),
SECSensorDescription(key="sim_import_power",name="Simulated import power",native_unit_of_measurement=UnitOfPower.KILO_WATT,device_class=SensorDeviceClass.POWER,state_class=SensorStateClass.MEASUREMENT,value_fn=lambda d:round(d.get("sim_import_kw",0),3)),
SECSensorDescription(key="sim_battery_charge_power",name="Simulated battery charge power",native_unit_of_measurement=UnitOfPower.KILO_WATT,device_class=SensorDeviceClass.POWER,state_class=SensorStateClass.MEASUREMENT,value_fn=lambda d:round(d.get("sim_battery_charge_kw",0),3)),
SECSensorDescription(key="sim_battery_discharge_power",name="Simulated battery discharge power",native_unit_of_measurement=UnitOfPower.KILO_WATT,device_class=SensorDeviceClass.POWER,state_class=SensorStateClass.MEASUREMENT,value_fn=lambda d:round(d.get("sim_battery_discharge_kw",0),3)),
SECSensorDescription(key="sim_export_energy",name="Simulated export energy today",native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,device_class=SensorDeviceClass.ENERGY,state_class=SensorStateClass.TOTAL,value_fn=lambda d:round(d.get("sim_export_kwh",0),3)),
SECSensorDescription(key="sim_import_energy",name="Simulated import energy today",native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,device_class=SensorDeviceClass.ENERGY,state_class=SensorStateClass.TOTAL,value_fn=lambda d:round(d.get("sim_import_kwh",0),3)),
SECSensorDescription(key="sim_export_revenue",name="Simulated export revenue today",native_unit_of_measurement="€",device_class=SensorDeviceClass.MONETARY,state_class=SensorStateClass.TOTAL,value_fn=lambda d:round(d.get("sim_export_revenue_eur",0),3)),
SECSensorDescription(key="sim_self_supply_value",name="Simulated self-consumption saving today",native_unit_of_measurement="€",device_class=SensorDeviceClass.MONETARY,state_class=SensorStateClass.TOTAL,value_fn=lambda d:round(d.get("sim_self_supply_value_eur",0),3)),
SECSensorDescription(key="sim_mining_value",name="Simulated mining value today",native_unit_of_measurement="€",device_class=SensorDeviceClass.MONETARY,state_class=SensorStateClass.TOTAL,value_fn=lambda d:round(d.get("sim_mining_value_eur",0),3)),
SECSensorDescription(key="sim_doge",name="Simulated DOGE today",native_unit_of_measurement="DOGE",state_class=SensorStateClass.TOTAL,value_fn=lambda d:round(d.get("sim_doge",0),3)),
SECSensorDescription(key="sim_miner_hours",name="Simulated miner runtime today",native_unit_of_measurement="h",state_class=SensorStateClass.TOTAL,value_fn=lambda d:round(d.get("sim_miner_hours",0),2)),
SECSensorDescription(key="mining_break_even",name="Mining break-even export price",native_unit_of_measurement="ct/kWh",state_class=SensorStateClass.MEASUREMENT,value_fn=lambda d:round(d.get("miner_break_even_ct",0),3)),
SECSensorDescription(key="export_price",name="Effective export price",native_unit_of_measurement="ct/kWh",state_class=SensorStateClass.MEASUREMENT,value_fn=lambda d:round(d.get("export_price_ct",0),3)),
SECSensorDescription(key="simulated_benefit",name="Simulated net benefit today",native_unit_of_measurement="€",device_class=SensorDeviceClass.MONETARY,state_class=SensorStateClass.TOTAL,value_fn=lambda d:round(d.get("simulated_benefit_eur",0),3)),
SECSensorDescription(key="actual_benefit",name="Observed net benefit today",native_unit_of_measurement="€",device_class=SensorDeviceClass.MONETARY,state_class=SensorStateClass.TOTAL,value_fn=lambda d:round(d.get("actual_benefit_eur",0),3)),
SECSensorDescription(key="advantage",name="Simulation advantage today",native_unit_of_measurement="€",device_class=SensorDeviceClass.MONETARY,state_class=SensorStateClass.MEASUREMENT,value_fn=lambda d:round(d.get("advantage_eur",0),3)),
SECSensorDescription(key="future_min_price",name="Future minimum EPEX price",native_unit_of_measurement="ct/kWh",state_class=SensorStateClass.MEASUREMENT,value_fn=lambda d:None if d.get("future_min_ct") is None else round(d["future_min_ct"],3)),
SECSensorDescription(key="future_max_price",name="Future maximum EPEX price",native_unit_of_measurement="ct/kWh",state_class=SensorStateClass.MEASUREMENT,value_fn=lambda d:None if d.get("future_max_ct") is None else round(d["future_max_ct"],3)),
SECSensorDescription(key="forecast_today",name="PV forecast today",native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,device_class=SensorDeviceClass.ENERGY,state_class=SensorStateClass.MEASUREMENT,value_fn=lambda d:round(d.get("forecast_today_kwh",0),3)),
SECSensorDescription(key="forecast_remaining_today",name="PV forecast remaining today",native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,device_class=SensorDeviceClass.ENERGY,state_class=SensorStateClass.MEASUREMENT,value_fn=lambda d:round(d.get("forecast_remaining_today_kwh",0),3)),
SECSensorDescription(key="forecast_tomorrow",name="PV forecast tomorrow",native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,device_class=SensorDeviceClass.ENERGY,state_class=SensorStateClass.MEASUREMENT,value_fn=lambda d:round(d.get("forecast_tomorrow_kwh",0),3)),
SECSensorDescription(key="forecast_next_hour",name="PV forecast next hour",native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,device_class=SensorDeviceClass.ENERGY,state_class=SensorStateClass.MEASUREMENT,value_fn=lambda d:round(d.get("forecast_next_hour_kwh",0),3)),)
async def async_setup_entry(hass:HomeAssistant,entry:ConfigEntry,async_add_entities:AddEntitiesCallback)->None:
    c=hass.data[DOMAIN][entry.entry_id];async_add_entities(SECSensor(c,entry,x) for x in SENSORS)
class SECSensor(CoordinatorEntity[SolarEnergyControllerCoordinator],SensorEntity):
    _attr_has_entity_name=True
    def __init__(self,c,entry,description):
        super().__init__(c);self.entity_description=description;self._attr_unique_id=f"{entry.entry_id}_{description.key}";self._attr_device_info=DeviceInfo(identifiers={(DOMAIN,entry.entry_id)},name="Solar Energy Controller",manufacturer="futuremeetsreality",model="Simulation Controller",sw_version="0.1.10")
    @property
    def native_value(self):return self.entity_description.value_fn(self.coordinator.data or {})
    @property
    def extra_state_attributes(self):
        d=self.coordinator.data or {}
        if self.entity_description.key=="recommendation":return {"reason":d.get("reason"),"target_reason":d.get("target_reason"),"simulation_enabled":d.get("simulation_enabled"),"miner_simulated_on":d.get("miner_simulated_on"),"miner_locked_until":d.get("miner_locked_until"),"future_price_points":d.get("future_price_points"),"forecast_peak_tomorrow":d.get("forecast_peak_tomorrow"),"accumulation_start":d.get("accumulation_start")}
        if self.entity_description.key=="decision_log":return {"entries":d.get("decision_log",[]),"entry_count":d.get("decision_log_count",0),"retention":"192 entries / approx. 48 h at 15 min","latest_reason":d.get("reason")}
        return None

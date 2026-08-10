# File: custom_components/solar_energy_controller/const.py
# Timestamp: 2026-08-11 00:22 CEST

from __future__ import annotations

DOMAIN = "solar_energy_controller"
PLATFORMS = ["sensor", "switch"]

CONF_PV_POWER = "pv_power_entity"
CONF_PV_ENERGY_TODAY = "pv_energy_today_entity"
CONF_HOUSE_LOAD = "house_load_entity"
CONF_GRID_EXPORT_POWER = "grid_export_power_entity"
CONF_GRID_IMPORT_POWER = "grid_import_power_entity"
CONF_GRID_EXPORT_ENERGY_TODAY = "grid_export_energy_today_entity"
CONF_GRID_IMPORT_ENERGY_TODAY = "grid_import_energy_today_entity"
CONF_BATTERY_SOC = "battery_soc_entity"
CONF_BATTERY_POWER = "battery_power_entity"
CONF_EPEX_CURRENT_PRICE = "epex_current_price_entity"
CONF_EPEX_PRICE = "epex_price_entity"
CONF_EFFECTIVE_EXPORT_PRICE = "effective_export_price_entity"
CONF_IMPORT_TOTAL_PRICE = "import_total_price_entity"
CONF_MINER_SWITCH = "miner_switch_entity"
CONF_MINER_POWER = "miner_power_entity"

CONF_FORECAST_TODAY_1 = "forecast_today_mppt1_entity"
CONF_FORECAST_TODAY_2 = "forecast_today_mppt2_entity"
CONF_FORECAST_REMAINING_1 = "forecast_remaining_today_mppt1_entity"
CONF_FORECAST_REMAINING_2 = "forecast_remaining_today_mppt2_entity"
CONF_FORECAST_TOMORROW_1 = "forecast_tomorrow_mppt1_entity"
CONF_FORECAST_TOMORROW_2 = "forecast_tomorrow_mppt2_entity"
CONF_FORECAST_NEXT_HOUR_1 = "forecast_next_hour_mppt1_entity"
CONF_FORECAST_NEXT_HOUR_2 = "forecast_next_hour_mppt2_entity"
CONF_FORECAST_PEAK_TOMORROW_1 = "forecast_peak_tomorrow_mppt1_entity"
CONF_FORECAST_PEAK_TOMORROW_2 = "forecast_peak_tomorrow_mppt2_entity"

CONF_BATTERY_CAPACITY_KWH = "battery_capacity_kwh"
CONF_BATTERY_MIN_SOC = "battery_min_soc"
CONF_BATTERY_MAX_CHARGE_KW = "battery_max_charge_kw"
CONF_BATTERY_MAX_DISCHARGE_KW = "battery_max_discharge_kw"
CONF_BATTERY_CHARGE_EFFICIENCY = "battery_charge_efficiency"
CONF_BATTERY_DISCHARGE_EFFICIENCY = "battery_discharge_efficiency"
CONF_MINER_NOMINAL_POWER_KW = "miner_nominal_power_kw"
CONF_MINER_MIN_RUNTIME_MIN = "miner_min_runtime_min"
CONF_DOGE_PER_DAY = "doge_per_day"
CONF_DOGE_TARGET_EUR = "doge_target_eur"
CONF_IMPORT_FALLBACK_EUR_KWH = "import_fallback_eur_kwh"
CONF_INTERVAL_MIN = "interval_min"
CONF_HORIZON_H = "horizon_h"

DEFAULTS = {
    CONF_PV_POWER: "sensor.solax_inverter_pv_power_total",
    CONF_PV_ENERGY_TODAY: "sensor.solax_inverter_today_s_solar_energy",
    CONF_HOUSE_LOAD: "sensor.solax_inverter_house_load",
    CONF_GRID_EXPORT_POWER: "sensor.solax_inverter_grid_export",
    CONF_GRID_IMPORT_POWER: "sensor.solax_inverter_grid_import",
    CONF_GRID_EXPORT_ENERGY_TODAY: "sensor.solax_inverter_today_s_export_energy",
    CONF_GRID_IMPORT_ENERGY_TODAY: "sensor.solax_inverter_today_s_import_energy",
    CONF_BATTERY_SOC: "sensor.solax_inverter_battery_1_capacity",
    CONF_BATTERY_POWER: "sensor.solax_inverter_battery_1_power_charge",
    CONF_EPEX_CURRENT_PRICE: "sensor.strompreis_ct",
    CONF_EPEX_PRICE: "sensor.epex_spot_data_market_price",
    CONF_EFFECTIVE_EXPORT_PRICE: "",
    CONF_IMPORT_TOTAL_PRICE: "",
    CONF_MINER_SWITCH: "switch.steckdose_mining",
    CONF_MINER_POWER: "sensor.steckdose_mining_power",
    CONF_FORECAST_TODAY_1: "sensor.energy_production_today",
    CONF_FORECAST_TODAY_2: "sensor.energy_production_today_2",
    CONF_FORECAST_REMAINING_1: "sensor.energy_production_today_remaining",
    CONF_FORECAST_REMAINING_2: "sensor.energy_production_today_remaining_2",
    CONF_FORECAST_TOMORROW_1: "sensor.energy_production_tomorrow",
    CONF_FORECAST_TOMORROW_2: "sensor.energy_production_tomorrow_2",
    CONF_FORECAST_NEXT_HOUR_1: "sensor.energy_next_hour",
    CONF_FORECAST_NEXT_HOUR_2: "sensor.energy_next_hour_2",
    CONF_FORECAST_PEAK_TOMORROW_1: "sensor.power_highest_peak_time_tomorrow",
    CONF_FORECAST_PEAK_TOMORROW_2: "sensor.power_highest_peak_time_tomorrow_2",
    CONF_BATTERY_CAPACITY_KWH: 12.5,
    CONF_BATTERY_MIN_SOC: 25.0,
    CONF_BATTERY_MAX_CHARGE_KW: 8.0,
    CONF_BATTERY_MAX_DISCHARGE_KW: 8.0,
    CONF_BATTERY_CHARGE_EFFICIENCY: 0.95,
    CONF_BATTERY_DISCHARGE_EFFICIENCY: 0.95,
    CONF_MINER_NOMINAL_POWER_KW: 1.0,
    CONF_MINER_MIN_RUNTIME_MIN: 60,
    CONF_DOGE_PER_DAY: 12.0,
    CONF_DOGE_TARGET_EUR: 0.20,
    CONF_IMPORT_FALLBACK_EUR_KWH: 0.348,
    CONF_INTERVAL_MIN: 15,
    CONF_HORIZON_H: 24,
}

STORAGE_VERSION = 1
STORAGE_KEY = f"{DOMAIN}_state"

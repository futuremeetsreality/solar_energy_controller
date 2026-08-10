# Solar Energy Controller

Home Assistant custom integration for economic PV, battery and miner optimization.

## Current build: 0.1.7

Version 0.1.7 is still **simulation-only** and adds explicit runtime diagnostics for the two data sources that matter most for planning:

- EPEX Spot Data: `sensor.epex_spot_data_market_price`
  - current state is used as the current EPEX price
  - attribute `data` is read as the 192 quarter-hour values for today + tomorrow
  - `price_per_kwh` is normalized from EUR/kWh to ct/kWh
- Forecast.Solar MPPT 1 + MPPT 2
  - today, remaining today, tomorrow and next-hour values are read from the original Forecast.Solar sensors
  - generated `solar_energy_controller` forecast sensors are explicitly rejected as input sources to prevent circular reads

New diagnostic entities in 0.1.7:

- `Controller build`
- `Input diagnostics`

The `Input diagnostics` entity exposes the resolved source entity IDs, their raw states and the number of future EPEX price points. This makes it possible to distinguish a calculation problem from a stale/not-updated HACS installation immediately.

## Simulation first

The controller observes the configured Home Assistant entities, builds a virtual battery/miner state, evaluates the current and upcoming electricity prices and exposes what the controller would do. It does **not** write to the SolaX inverter or the miner switch.

Main goals:

- 15-minute optimization cycle
- virtual battery SOC and energy-flow simulation
- DOGE-only miner valuation with configurable DOGE/day and target price
- minimum miner runtime support (default 60 min)
- comparison of simulated export/mining/import economics
- recommendations for SolaX mode and miner state
- safe default: Simulation = ON
- persistent decision log
- Forecast.Solar-aware target SOC
- 24-hour EPEX planning
- groundwork for replay and later assisted/automatic control

## Default installation assumptions

The defaults are tailored to the current reference installation and can be changed in the Home Assistant setup flow:

- Battery: 12.5 kWh
- Minimum SOC: 25 %
- Max battery charge/discharge power: 8 kW
- Charge efficiency: 95 %
- Discharge efficiency: 95 %
- Planning interval: 15 min
- Planning horizon: 24 h
- Miner nominal power: 1.0 kW
- Miner minimum runtime: 60 min
- DOGE production: 12 DOGE/day
- DOGE target value: 0.20 EUR/DOGE
- LTC value: intentionally ignored

## Expected Home Assistant entities

Defaults used by the setup flow/controller:

- `sensor.solax_inverter_pv_power_total`
- `sensor.solax_inverter_today_s_solar_energy`
- `sensor.solax_inverter_house_load`
- `sensor.solax_inverter_grid_export`
- `sensor.solax_inverter_grid_import`
- `sensor.solax_inverter_today_s_export_energy`
- `sensor.solax_inverter_today_s_import_energy`
- `sensor.solax_inverter_battery_1_capacity`
- `sensor.solax_inverter_battery_1_power_charge`
- `sensor.epex_spot_data_market_price`
- `sensor.energy_production_today`
- `sensor.energy_production_today_2`
- `sensor.energy_production_today_remaining`
- `sensor.energy_production_today_remaining_2`
- `sensor.energy_production_tomorrow`
- `sensor.energy_production_tomorrow_2`
- `sensor.energy_next_hour`
- `sensor.energy_next_hour_2`
- `switch.steckdose_mining`
- `sensor.steckdose_mining_power`

Optional price entities can be selected for effective export revenue and total import price. If no effective export entity is configured, the current state of the EPEX Spot Data entity is used directly for the simulation.

## Safety

0.1.x never calls `switch.turn_on`, `switch.turn_off`, changes SolaX selects/numbers, or performs any other write to the installation. Turning the Simulation switch off pauses the shadow simulation; it does not enable live control.

Live control will only be introduced in a later version after the simulation has been validated against real operating data.

## Installation via HACS

Add this repository as a custom HACS integration, install **Solar Energy Controller**, restart Home Assistant and add the integration under **Settings → Devices & services**.

After updating to 0.1.7, verify that the entity **Controller build** reports `0.1.7`. If it does not, Home Assistant is still running an older copy of the integration.

## Dashboard

A complete dashboard is available under `examples/dashboard.yaml`. The strategy explanation block remains between **Aktuelle Strategie** and **Letzte Simulationsentscheidung** and documents all five controller states:

- `CHARGE_PRIORITY`
- `EXPORT_PRIORITY`
- `MINING_PRIORITY`
- `HOUSE_RESERVE`
- `PAUSED`

## Repository name

Domain and repository are intentionally named `solar_energy_controller`.

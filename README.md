# Solar Energy Controller

Home Assistant custom integration for economic PV, battery and miner optimization.

## Version 0.1.0 – simulation first

The first release is intentionally **simulation-only**. It observes the configured Home Assistant entities, builds a virtual battery/miner state, evaluates the current and upcoming electricity prices and exposes what the controller would do. It does **not** write to the SolaX inverter or the miner switch.

Main goals:

- 15-minute optimization cycle
- virtual battery SOC and energy-flow simulation
- DOGE-only miner valuation with configurable DOGE/day and target price
- minimum miner runtime support (default 60 min)
- comparison of simulated export/mining/import economics
- recommendations for SolaX mode and miner state
- safe default: Simulation = ON
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
- LTC value: intentionally ignored in 0.1.0

## Expected Home Assistant entities

Defaults used by the setup flow:

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
- `switch.steckdose_mining`
- `sensor.steckdose_mining_power`

Optional price entities can be selected for effective export revenue and total import price. If no effective export entity is configured, the EPEX value is used directly for the simulation.

## Safety

0.1.0 never calls `switch.turn_on`, `switch.turn_off`, changes SolaX selects/numbers, or performs any other write to the installation. Turning the Simulation switch off pauses the shadow simulation; it does not enable live control.

Live control will only be introduced in a later version after the simulation has been validated against real operating data.

## Installation via HACS

Add this repository as a custom HACS integration, install **Solar Energy Controller**, restart Home Assistant and add the integration under **Settings → Devices & services**.

## Repository name

Domain and repository are intentionally named `solar_energy_controller`.

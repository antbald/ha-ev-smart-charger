# EV Smart Charger

[![GitHub Release](https://img.shields.io/github/v/release/antbald/ha-ev-smart-charger)](https://github.com/antbald/ha-ev-smart-charger/releases)
[![HACS Custom](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/custom-components/hacs)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

Smart EV charging orchestration for Home Assistant.

This custom integration helps you charge your EV with surplus solar energy, coordinate EV and home battery priorities, automate night charging, run temporary boost sessions, and block unwanted charging outside your preferred window.

Current integration version: `1.6.5`

## Table of Contents

- [Highlights](#highlights)
- [Supported Languages](#supported-languages)
- [How It Works](#how-it-works)
- [Requirements](#requirements)
- [Installation](#installation)
- [Configuration](#configuration)
- [Created Entities](#created-entities)
- [Charging Profiles and Automations](#charging-profiles-and-automations)
- [Dashboard Card](#dashboard-card)
- [Troubleshooting](#troubleshooting)
- [Documentation](#documentation)

## Highlights

- Solar Surplus charging with dynamic amperage adjustment from `6A` to `32A`
- Priority Balancer for EV vs home battery daily targets
- Night Smart Charge driven by tomorrow's PV forecast
- Boost Charge with automatic stop at a target EV SOC
- Smart Charger Blocker to prevent unwanted charging at night
- Cached EV SOC sensor for unreliable cloud-based car integrations
- Built-in diagnostic entities, file logging, and trace logging
- Native reconfigure flow for existing config entries
- Bundled Lovelace dashboard module served directly by the integration

## Supported Languages

The integration currently ships translated UI and runtime messages for:

- English (`en`)
- Italian (`it`)
- Dutch (`nl`)

Available documentation languages:

- English: this README
- Dutch setup guide: [docs/README.nl.md](docs/README.nl.md)

## How It Works

EV Smart Charger exposes a small public control surface and keeps the rest of the behavior behind helper entities.

- Public charging profiles: `manual`, `solar_surplus`
- Dedicated helpers control Night Smart Charge, Boost Charge, Smart Blocker, notifications, targets, thresholds, and schedules
- The integration coordinates all automation owners internally to avoid charger conflicts

Recent reliability improvements reflected in the current codebase:

- `v1.6.0`: restored helper/select/time state is written back immediately after restart, avoiding long `unavailable` periods
- `v1.6.1`: Night Smart Charge retries charger start with backoff before giving up

## Requirements

You need:

- Home Assistant with custom integrations enabled
- An EV charger that can be controlled with:
  - a `switch` entity for on/off
  - a current control entity in one of these domains: `number`, `input_number`, `select`, `input_select`
  - a status `sensor`
- Energy sensors for:
  - EV SOC
  - home battery SOC
  - solar production
  - home consumption
  - grid import

Optional but recommended:

- A PV forecast sensor for Night Smart Charge
- Mobile App notify services
- A `person` entity for presence-aware notifications
- A `number` or `input_number` helper to store the nightly energy forecast target

Expected charger status values:

- `charger_charging`
- `charger_free`
- `charger_end`
- `charger_wait`

## Installation

### HACS

1. Open HACS in Home Assistant.
2. Go to `Integrations`.
3. Open the custom repositories dialog.
4. Add `https://github.com/antbald/ha-ev-smart-charger` as category `Integration`.
5. Search for `EV Smart Charger`.
6. Install it.
7. Restart Home Assistant.

### Manual

1. Download the latest release from [GitHub Releases](https://github.com/antbald/ha-ev-smart-charger/releases).
2. Extract `custom_components/ev_smart_charger`.
3. Copy it to:

```text
/config/custom_components/ev_smart_charger/
```

4. Restart Home Assistant.

## Configuration

Add the integration from `Settings -> Devices & Services -> Add Integration` and search for `EV Smart Charger`.

The setup wizard has 6 steps:

1. Integration name
2. Charger entities
3. Energy sensors
4. Optional PV forecast
5. Notifications and car owner
6. Optional external connectors

### Step 1: Name

Choose the display name used in Home Assistant.

### Step 2: Charger Entities

Required mappings:

- Charger switch
- Charging current control
- Charger status sensor

### Step 3: Energy Sensors

Required mappings:

- EV battery SOC
- Home battery SOC
- Solar production
- Home consumption
- Grid import

### Step 4: Solar Forecast

Optional sensor in `kWh` used by Night Smart Charge to decide between home battery and public grid.

### Step 5: Notifications

Optional configuration:

- one or more `notify.mobile_app_*` services
- one `person` entity representing the car owner

### Step 6: External Connectors

Optional configuration:

- EV battery capacity in `kWh`
- a `number` or `input_number` helper where the integration writes the calculated nightly energy forecast target

### Reconfigure Existing Entries

The integration supports native reconfiguration for existing entries, so you can remap charger entities, sensors, notifications, PV forecast, and external connectors without deleting the integration.

## Created Entities

After setup, the integration creates `57` entities per config entry:

- `20` switches
- `25` numbers
- `1` select
- `2` time entities
- `7` sensors

Main examples:

- `select.<prefix>_evsc_charging_profile`
- `switch.<prefix>_evsc_boost_charge_enabled`
- `switch.<prefix>_evsc_night_smart_charge_enabled`
- `switch.<prefix>_evsc_smart_charger_blocker_enabled`
- `number.<prefix>_evsc_grid_import_threshold`
- `number.<prefix>_evsc_home_battery_min_soc`
- `time.<prefix>_evsc_night_charge_time`
- `time.<prefix>_evsc_car_ready_time`
- `sensor.<prefix>_evsc_priority_daily_state`
- `sensor.<prefix>_evsc_cached_ev_soc`
- `sensor.<prefix>_evsc_log_file_path`

`<prefix>` depends on the config entry id generated by Home Assistant.

## Charging Profiles and Automations

### Charging Profiles

#### `manual`

No automatic charging decisions. You control the charger directly.

#### `solar_surplus`

Uses excess PV production and dynamically adjusts amperage while protecting against unwanted grid import.

### Solar Surplus

Core behavior:

- calculates available surplus from production and consumption
- converts surplus to the nearest supported amperage step
- uses delays and hysteresis to reduce oscillations
- can optionally fall back to home battery support when enabled

Important entities:

- `number.*_evsc_check_interval`
- `number.*_evsc_grid_import_threshold`
- `number.*_evsc_grid_import_delay`
- `number.*_evsc_surplus_drop_delay`
- `switch.*_evsc_use_home_battery`
- `number.*_evsc_home_battery_min_soc`
- `number.*_evsc_battery_support_amperage`

### Priority Balancer

Priority Balancer compares the current EV SOC and home battery SOC against daily targets.

Possible states:

- `EV`: charge the car first
- `Home`: preserve or prioritize the home battery
- `EV_Free`: both daily targets are satisfied

Key helpers:

- `number.*_evsc_ev_min_soc_monday` through `sunday`
- `number.*_evsc_home_min_soc_monday` through `sunday`
- `sensor.*_evsc_priority_daily_state`

### Night Smart Charge

Night Smart Charge checks tomorrow's solar forecast at the configured time and decides whether to charge overnight from:

- home battery, when forecast is high enough
- grid, when forecast is too low

Key behaviors:

- late-arrival detection for cars plugged in after the scheduled start
- per-day `Car Ready` flags
- configurable `Car Ready Time`
- automatic handoff from night logic back to `solar_surplus`
- charger start retry logic with backoff in the current release

Key helpers:

- `switch.*_evsc_night_smart_charge_enabled`
- `time.*_evsc_night_charge_time`
- `time.*_evsc_car_ready_time`
- `number.*_evsc_min_solar_forecast_threshold`
- `number.*_evsc_night_charge_amperage`
- `switch.*_evsc_car_ready_monday` through `sunday`

### Boost Charge

Boost Charge is a temporary manual override that:

- starts charging immediately
- uses a fixed amperage
- stops automatically at the configured EV SOC target
- returns control to the normal automation flow after completion

Key helpers:

- `switch.*_evsc_boost_charge_enabled`
- `number.*_evsc_boost_charge_amperage`
- `number.*_evsc_boost_target_soc`

### Smart Charger Blocker

Smart Charger Blocker prevents charging outside the allowed time window unless an override is active.

It allows charging when:

- `Force Charge` is enabled
- Night Smart Charge owns the session
- the blocker is disabled

It blocks charging when:

- charging starts during the configured night blocking window
- no override applies

Key helpers:

- `switch.*_evsc_smart_charger_blocker_enabled`
- `switch.*_evsc_forza_ricarica`
- `switch.*_evsc_notify_smart_blocker_enabled`

### Cached EV SOC

For integrations that expose unstable EV SOC values via cloud APIs, EV Smart Charger maintains a cached sensor:

- source sensor is polled every `5s`
- last valid value is preserved when the source becomes `unknown` or `unavailable`
- downstream automations read the cached value instead of failing hard

Key sensor:

- `sensor.*_evsc_cached_ev_soc`

## Dashboard Card

The repository includes a bundled Lovelace module:

```yaml
lovelace:
  resources:
    - url: /api/ev_smart_charger/frontend/ev-smart-charger-dashboard.js
      type: module
```

Minimal example:

```yaml
type: custom:ev-smart-charger-dashboard
title: EV Smart Charger
entity_prefix: ev_smart_charger_<entry_id>
charging_power_entity: sensor.current_charging_power
ev_soc_entity: sensor.ev_battery_soc
home_battery_soc_entity: sensor.home_battery_soc
solar_power_entity: sensor.solar_production
grid_import_entity: sensor.grid_import
current_entity: number.wallbox_current
```

Notes:

- `entity_prefix` is required
- the card works with the integration-owned helpers created for that config entry
- telemetry entities such as live charging power or EV SOC are optional enrichments

## Troubleshooting

Start with these checks:

1. Confirm that the mapped charger switch works manually in Home Assistant.
2. Confirm that the charger status sensor exposes one of the supported values.
3. Confirm that solar production, home consumption, and grid import sensors use sensible units and values.
4. Confirm that EV SOC is valid, especially if it comes from a cloud integration.
5. Inspect the diagnostic sensors and the log file path sensor.

Useful entities:

- `sensor.*_evsc_diagnostic`
- `sensor.*_evsc_solar_surplus_diagnostic`
- `sensor.*_evsc_priority_daily_state`
- `sensor.*_evsc_log_file_path`
- `sensor.*_evsc_cached_ev_soc`

Useful toggles:

- `switch.*_evsc_enable_file_logging`
- `switch.*_evsc_trace_logging_enabled`

If notifications do not arrive:

- verify `notify.mobile_app_*` services exist
- verify the configured `person` entity is correct

## Documentation

User-facing:

- Main guide: this README
- [Dutch guide](docs/README.nl.md)

Technical and maintenance:

- [Documentation index](docs/README.md)
- [Architecture SSOT](docs/SSOT.md)
- [Codebase map](docs/CODEBASE_MAP.md)
- [Refactor plan / hardening record](docs/REFACTOR_PLAN.md)

## Analytics & Privacy

EV Smart Charger sends an anonymous ping once per day to help the maintainer understand how many active installations exist, which versions are in use, and which regions use the integration.

**What is sent:**

| Field | Example | Purpose |
|-------|---------|---------|
| `installation_id` | `a3f2...` (random UUID) | Count unique installs (never reused across uninstalls) |
| `version` | `1.6.4` | Version adoption tracking |
| `ha_version` | `2026.4.0` | HA compatibility insight |
| `timezone` | `Europe/Rome` | Approximate region (country/continent) |
| `country` | `IT` | Derived from timezone — no geolocation |
| `continent` | `EU` | Aggregate geographic distribution |

**What is NOT sent:** IP address, hostname, entity names, configuration, credentials, or any personally identifiable information.

Data is stored in a private Google Sheet accessible only to the maintainer. Aggregated statistics may be published publicly.

**Opt-out:** Set the environment variable `EVSC_DISABLE_TELEMETRY=true` on your Home Assistant host (e.g. in `/etc/environment` or your Docker compose file).

## License

MIT. See [LICENSE](LICENSE).

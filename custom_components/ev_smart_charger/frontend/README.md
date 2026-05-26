# EV Smart Charger Dashboard Frontend

> **Updated for v1.8.0** — surfaces all 64 helper entities (or 51 in PV-only mode) including the new Hybrid Inverter Mode panel.

This integration serves a bundled Lovelace module at:

- `/api/ev_smart_charger/frontend/ev-smart-charger-dashboard.js`

Add it as a dashboard resource:

```yaml
lovelace:
  resources:
    - url: /api/ev_smart_charger/frontend/ev-smart-charger-dashboard.js
      type: module
```

Then add the card:

```yaml
type: custom:ev-smart-charger-dashboard
title: Tesla Charge Deck
entity_prefix: ev_smart_charger_<entry_id>
charging_power_entity: sensor.current_charging_power_tesla
ev_soc_entity: sensor.tesla_battery
home_battery_soc_entity: sensor.stato_batteria_luxpower
solar_power_entity: sensor.produzione_solare_totale
grid_import_entity: sensor.grid_power_import_w
current_entity: number.wallbox_current
```

> **Note on `entity_prefix`** (v1.6.23+): newer Home Assistant installs use a uppercase ULID `entry_id`, but the integration always lowercases it when composing entity IDs. The dashboard `entity_prefix` must use the **lowercase** form, e.g. `ev_smart_charger_01kjsybka3arm5xq65d9b56tzk`.

## What the card surfaces

The dashboard is organized in stacked module panels and exposes **every helper entity** the integration creates. Sections:

| Section | Entities |
|---|---|
| **Hero metrics** | live charging power, EV SOC, home battery SOC, grid import, solar power, charger current (user-mapped sensors via card config) |
| **Priority spotlight** | `evsc_priority_daily_state` + today's EV / home targets |
| **Main Controls** | `evsc_forza_ricarica`, `evsc_charging_profile` |
| **Boost Charge** | `evsc_boost_charge_enabled`, `evsc_boost_charge_amperage`, `evsc_boost_target_soc` |
| **Boost Schedule** | `evsc_boost_schedule_enabled`, `evsc_boost_schedule_start_time`, `evsc_boost_schedule_end_time` |
| **Night Smart Charge** | `evsc_night_smart_charge_enabled`, `evsc_preserve_home_battery`, `evsc_night_charge_time`, `evsc_car_ready_time`, `evsc_min_solar_forecast_threshold`, `evsc_night_charge_amperage` |
| **Car Ready (weekly planner)** | `evsc_car_ready_<day>` × 7 in a compact day grid |
| **Daily SOC Targets** | `evsc_ev_min_soc_<day>` × 7 + `evsc_home_min_soc_<day>` × 7 in compact +/− steppers |
| **Solar Surplus** | check interval, grid import threshold/delay, surplus drop delay, **solar max amperage**, use home battery, home battery min SOC, battery support amperage, **battery support sunset buffer** |
| **Hybrid Inverter Mode** (v1.8.0) | `evsc_hybrid_inverter_mode`, `evsc_hybrid_battery_full_threshold`, `evsc_hybrid_probe_duration`, `evsc_hybrid_max_import_duration`, `evsc_hybrid_max_failed_probes` |
| **Safety / Protection** | `evsc_priority_balancer_enabled`, `evsc_smart_charger_blocker_enabled` |
| **Notifications** (v1.3.20) | `evsc_notify_smart_blocker_enabled`, `evsc_notify_priority_balancer_enabled`, `evsc_notify_night_charge_enabled` |
| **Logging** (v1.3.25 / v1.4.15) | `evsc_trace_logging_enabled`, `evsc_enable_file_logging`, displays current `evsc_log_file_path` |
| **Diagnostics panel** | `evsc_diagnostic`, `evsc_solar_surplus_diagnostic`, **`evsc_hybrid_inverter_diagnostic`** (v1.8.0), **`evsc_cached_ev_soc`** (v1.4.0) |

PV-only mode (no home battery configured): the dashboard still renders all sections — entities that don't exist gracefully show "Unavailable" / fallback labels.

Notes:

- `entity_prefix` is required and must match the helper entity prefix created by this integration (lowercase since v1.6.23).
- Optional telemetry entities (`charging_power_entity`, `ev_soc_entity`, etc.) enrich the hero metrics but are not required.
- The card calls native Home Assistant services directly (`switch.toggle`, `number.set_value`, `select.select_option`, `time.set_value`).
- Day grids use locale-aware initials (Mon-Sun in EN, Lun-Dom in IT, Maa-Zon in NL).

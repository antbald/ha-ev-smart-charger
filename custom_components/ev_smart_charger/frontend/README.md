# EV Smart Charger Dashboard Frontend

> **Updated for v1.9.0** — auto-generated Liquid Glass dashboard (iOS 18 style).
> The integration now bootstraps a ready-to-go Lovelace dashboard for you. No
> YAML required. The bundled card is still usable on your own dashboards too.
>
> **Design system reference**: see [DESIGN.md](DESIGN.md) for the full
> "Liquid Aurora" token reference, component recipes, anti-patterns and
> responsive principles introduced in v1.11.0. Required reading before
> adding or changing visual tokens.

## Zero-config auto-dashboard (v1.9.0+)

When you add the integration, the last step of the config flow asks:

> Auto-generate sidebar dashboard — ON

If you leave it on (default), the integration:

1. Registers `/api/ev_smart_charger/frontend/ev-smart-charger-dashboard.js`
   as a Lovelace resource for you.
2. Creates a panel-mode Lovelace dashboard named **EV Smart Charger** with the
   icon `mdi:ev-station`, accessible at `/ev-smart-charger`. It shows up in the
   left sidebar automatically.
3. Pre-populates the card with the **lowercased entity_prefix** of your config
   entry and every user-mapped energy sensor (EV SOC, home battery SOC, solar
   production, grid import, charger status, and — v2.2.0 — the measured EV
   charging-power sensor(s), single or per-phase). You don't have to type a
   single YAML line.

> **Charging detection (v2.2.0)**: the green "EV charging" banner, the SOC ring
> and the charging-power tile derive "is the car charging?" from the **measured
> charging-power** sensor when mapped (`charging_power_entity`, or the per-phase
> `charging_power_entities` array summed in three-phase), otherwise from a
> **tolerant** charger-status check (so a wallbox reporting any charging string,
> not just `charger_charging`, lights the banner). `charger_status_entity` is
> optional since v2.2.0.

You can toggle this off at any time via the integration's options. Disabling
removes the sidebar entry; re-enabling recreates it with the current mapping.

## Look — Liquid Glass iOS 18

Visual language:

- **Activity-style dual SOC ring** in the hero: outer arc EV SOC
  (`--evsc-sys-green`), inner arc Home Battery SOC (`--evsc-sys-purple`).
  The center shows live charging power when the car is drawing (measured-power
  SSOT, v2.2.0), otherwise the EV SOC percentage. A pulsing green dot indicates
  active charging.
- **Live charging banner** (v2.2.0): when the car is charging, the green hero
  banner animates — the aurora green breathes while a white energy current
  sweeps across it and a charge-pulse ring radiates from the dot (all neutralized
  under `prefers-reduced-motion`).
- **Liquid Glass cards**: `backdrop-filter: saturate(180%) blur(40px)` over a
  layered gradient background with two soft auroras that float continuously.
  Cards lift on hover (1px translateY + softer-to-stronger shadow).
- **Apple System Colors** throughout: blue `#007aff` for selected profile,
  green `#34c759` for toggles ON and EV SOC, purple `#5856d6`/`#af52de` for
  home battery and EV_Free priority state.
- **iOS-spec toggles**: 51×31 pill with 27px thumb, 280ms spring transition.
- **SF Pro typography stack** with tabular numerals (`tnum`) on metric values.
- **Native dark/light**: `@media (prefers-color-scheme)` swaps the entire
  palette. No theme configuration required.
- **Reduced motion** respected (`prefers-reduced-motion: reduce`).

## Card config (for manual usage on your own dashboards)

The card is still usable as a standalone Lovelace card. Add the resource:

```yaml
lovelace:
  resources:
    - url: /api/ev_smart_charger/frontend/ev-smart-charger-dashboard.js?v=1.11.4
      type: module
```

> Replace `1.11.4` with the current value of `custom_components/ev_smart_charger/const.py:VERSION` on every upgrade — otherwise the browser may keep serving the cached previous bundle. The auto-dashboard (enabled by default in the config flow) does this for you. See [DEPLOY.md](DEPLOY.md) for the full cache-busting strategy.

Then add it to a view:

```yaml
type: custom:ev-smart-charger-dashboard
title: EV Smart Charger
entity_prefix: ev_smart_charger_<entry_id_lowercased>
ev_soc_entity: sensor.tesla_battery
home_battery_soc_entity: sensor.home_battery_soc
solar_power_entity: sensor.solar_production
grid_import_entity: sensor.grid_import_w
charger_status_entity: sensor.wallbox_status
current_entity: number.wallbox_current
charger_switch_entity: switch.wallbox_charging
charging_power_entity: sensor.current_charging_power
pv_forecast_entity: sensor.pv_forecast_tomorrow
```

> **Lowercase `entity_prefix`** (since v1.6.23) — newer HA installs use an
> uppercase ULID `entry_id`, but the integration always lowercases it when
> composing entity IDs.

## Sections surfaced (every helper entity)

| Section | Entities |
|---|---|
| **Hero ring** | EV SOC + Home Battery SOC (dual concentric activity ring), live charging power, pulsing charge indicator |
| **Hero metrics** | solar power, grid import, charger current, charging power (user-mapped) |
| **Priority spotlight** | `evsc_priority_daily_state` (colored pill) + today's EV / home targets |
| **Main Controls** | `evsc_forza_ricarica`, `evsc_charging_profile` |
| **Boost Charge** | `evsc_boost_charge_enabled`, `evsc_boost_charge_amperage`, `evsc_boost_target_soc` |
| **Boost Schedule** | `evsc_boost_schedule_enabled`, `evsc_boost_schedule_start_time`, `evsc_boost_schedule_end_time` |
| **Night Smart Charge** | `evsc_night_smart_charge_enabled`, `evsc_preserve_home_battery`, `evsc_night_charge_time`, `evsc_car_ready_time`, `evsc_min_solar_forecast_threshold`, `evsc_night_charge_amperage` |
| **Car Ready (weekly planner)** | `evsc_car_ready_<day>` × 7 day-chip grid |
| **Daily SOC Targets** | `evsc_ev_min_soc_<day>` × 7 + `evsc_home_min_soc_<day>` × 7 in micro-steppers |
| **Solar Surplus** | check interval, grid import threshold/delay, surplus drop delay, solar max amperage, use home battery, home battery min SOC, battery support amperage, battery support sunset buffer |
| **Hybrid Inverter Mode** (v1.8.0) | `evsc_hybrid_inverter_mode`, `evsc_hybrid_battery_full_threshold`, `evsc_hybrid_probe_duration`, `evsc_hybrid_max_import_duration`, `evsc_hybrid_max_failed_probes` |
| **Safety / Protection** | `evsc_priority_balancer_enabled`, `evsc_smart_charger_blocker_enabled` |
| **Notifications** | `evsc_notify_smart_blocker_enabled`, `evsc_notify_priority_balancer_enabled`, `evsc_notify_night_charge_enabled`, `evsc_live_activities_enabled` (default OFF) |
| **Logging** | `evsc_trace_logging_enabled`, `evsc_enable_file_logging`, displays current `evsc_log_file_path` |
| **Diagnostics panel** | `evsc_diagnostic`, `evsc_solar_surplus_diagnostic`, `evsc_hybrid_inverter_diagnostic`, `evsc_cached_ev_soc` |

PV-only mode (no home battery configured): the inner SOC ring is hidden, the
home battery legend disappears, and battery-only sections gracefully show
"Unavailable" placeholders.

## Notes

- The card calls native Home Assistant services (`switch.toggle`,
  `number.set_value`, `select.select_option`, `time.set_value`).
- Day grids use locale-aware initials (Mon-Sun in EN, Lun-Dom in IT, Maa-Zon
  in NL). The card automatically picks the active HA language.
- Designed for panel-mode (full bleed). If you embed it in a multi-card view,
  the surrounding `ha-card` chrome remains visible — the design will still
  work but the immersive look is best in panel/dedicated views.

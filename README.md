# EV Smart Charger

[![GitHub Release](https://img.shields.io/github/v/release/antbald/ha-ev-smart-charger)](https://github.com/antbald/ha-ev-smart-charger/releases)
[![HACS Custom](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/custom-components/hacs)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Home Assistant](https://img.shields.io/badge/Home%20Assistant-2024.4%2B-blue)](https://www.home-assistant.io/)
[![Code owner](https://img.shields.io/badge/maintainer-%40antbald-blue)](https://github.com/antbald)

**Intelligent EV charging orchestration for Home Assistant.**

This custom integration maximises solar self-consumption by charging your EV with surplus PV energy, balances daily SOC targets between the car and a home battery, automates overnight charging driven by tomorrow's forecast, and protects the system from unsafe or unwanted charger activations.

**Key features at a glance:**

- Solar Surplus charging with dynamic amperage control (`6–32 A`) and a per-wallbox ceiling
- Priority Balancer — daily EV vs home battery SOC targets, automatically resolved
- Night Smart Charge — overnight charging from home battery or grid based on PV forecast
- Boost Charge — immediate high-priority session with automatic SOC stop, manual or scheduled
- Smart Charger Blocker — blocks charging outside your allowed window
- Cached EV SOC — reliable fallback for cloud-based car integrations
- Built-in diagnostic sensors, file logging, and trace logging
- Bundled Lovelace dashboard module served directly by the integration

---

## Table of Contents

- [How It Works](#how-it-works)
  - [Automation Priority System](#automation-priority-system)
- [Requirements](#requirements)
- [Installation](#installation)
  - [HACS (Recommended)](#hacs-recommended)
  - [Manual](#manual)
- [Configuration](#configuration)
  - [Step 1 — Name](#step-1--name)
  - [Step 2 — Charger Entities](#step-2--charger-entities)
  - [Step 3 — Energy Sensors](#step-3--energy-sensors)
  - [Step 4 — PV Forecast](#step-4--pv-forecast)
  - [Step 5 — Notifications](#step-5--notifications)
  - [Step 6 — External Connectors](#step-6--external-connectors)
  - [Reconfigure](#reconfigure)
- [Created Entities](#created-entities)
  - [Charging Profile](#charging-profile)
  - [Switches — Control](#switches--control)
  - [Switches — Notifications](#switches--notifications)
  - [Switches — Car Ready (daily)](#switches--car-ready-daily)
  - [Numbers — Solar Surplus](#numbers--solar-surplus)
  - [Numbers — Night Smart Charge](#numbers--night-smart-charge)
  - [Numbers — Boost Charge](#numbers--boost-charge)
  - [Numbers — Daily EV SOC Targets](#numbers--daily-ev-soc-targets)
  - [Numbers — Daily Home Battery SOC Targets](#numbers--daily-home-battery-soc-targets)
  - [Time Controls](#time-controls)
  - [Sensors — Diagnostics](#sensors--diagnostics)
- [Automation Details](#automation-details)
  - [Solar Surplus](#solar-surplus)
  - [Priority Balancer](#priority-balancer)
  - [Night Smart Charge](#night-smart-charge)
  - [Boost Charge](#boost-charge)
  - [Smart Charger Blocker](#smart-charger-blocker)
  - [Cached EV SOC](#cached-ev-soc)
- [Dashboard Card](#dashboard-card)
- [Logging & Diagnostics](#logging--diagnostics)
- [Notifications & Presence](#notifications--presence)
- [Analytics & Privacy](#analytics--privacy)
- [Troubleshooting](#troubleshooting)
- [Supported Languages](#supported-languages)
- [Documentation](#documentation)
- [License](#license)

---

## How It Works

EV Smart Charger sits between your hardware (charger, inverter, home battery) and Home Assistant. You map your existing sensor and switch entities during setup; the integration then creates ~60 helper entities that drive all automation logic.

Only two charging profiles are selectable by the user: **`manual`** (no automation) and **`solar_surplus`** (automatic). All other features — Night Smart Charge, Boost Charge, Smart Charger Blocker, Priority Balancer — are independent modules that activate on top of the selected profile according to a fixed priority hierarchy.

```mermaid
graph TD
    subgraph inputs["Your Home Assistant Entities (you map these)"]
        S1[☀️ Solar Production]
        S2[🏠 Home Consumption]
        S3[⚡ Grid Import]
        S4[🔋 Home Battery SOC]
        S5[🚗 EV Battery SOC]
    end

    subgraph integration["EV Smart Charger Integration"]
        direction TB
        PB["⚖️ Priority Balancer\n(EV vs Home targets)"]
        NSC["🌙 Night Smart Charge\n(forecast-driven)"]
        BC["⚡ Boost Charge\n(manual / scheduled)"]
        SCB["🛡️ Smart Charger Blocker\n(time window guard)"]
        SS["☀️ Solar Surplus\n(dynamic amperage)"]
        FC["🔴 Force Charge\n(override)"]
        CC["🎛️ Charger Controller\n(rate-limited, queued)"]

        FC -->|priority 1| CC
        BC -->|priority 2| CC
        SCB -->|priority 3| CC
        NSC -->|priority 4| CC
        PB -.->|informs| NSC
        PB -.->|informs| SS
        SS -->|priority 6| CC
    end

    subgraph charger["Your Wallbox"]
        SW["switch: on/off"]
        AMP["number/select: amperage"]
    end

    inputs --> integration
    CC --> SW
    CC --> AMP
```

### Automation Priority System

When multiple automations could act on the charger simultaneously, the integration resolves conflicts using this execution order:

| Priority | Component | Activation Condition |
|:---:|---|---|
| **1** | Force Charge (`evsc_forza_ricarica`) | Switch turned ON — overrides everything |
| **2** | Boost Charge | `evsc_boost_charge_enabled` ON or scheduled window active |
| **3** | Smart Charger Blocker | Charger starts outside allowed time window |
| **4** | Night Smart Charge | Current time ≥ `evsc_night_charge_time`, before sunrise |
| **5** | Priority Balancer | Evaluated inside Solar Surplus and Night Charge |
| **6** | Solar Surplus | Profile = `solar_surplus`, daytime hours |

Lower-priority automations only act when none of the higher-priority ones hold ownership of the charger.

```mermaid
flowchart TD
    START([Charger event / periodic tick]) --> P1{Force Charge ON?}
    P1 -->|Yes| ACT1[Keep charger ON\nat configured amps]
    P1 -->|No| P2{Boost Charge\nactive?}
    P2 -->|Yes| ACT2[Charge at boost amperage\nStop at target SOC]
    P2 -->|No| P3{Smart Charger\nBlocker triggered?}
    P3 -->|Yes| ACT3[Stop charger\nSend notification]
    P3 -->|No| P4{Night Smart\nCharge window?}
    P4 -->|Yes| ACT4[Battery or Grid mode\nat night amperage]
    P4 -->|No| P5{Profile =\nsolar_surplus?}
    P5 -->|No| ACT5[No action\nmanual mode]
    P5 -->|Yes| P6{Priority\nBalancer state?}
    P6 -->|Home| ACT6[Pause charger\nHome battery charges itself]
    P6 -->|EV or EV_Free| ACT7[Solar Surplus\ndynamic amperage control]

    style ACT1 fill:#e74c3c,color:#fff
    style ACT2 fill:#e67e22,color:#fff
    style ACT3 fill:#8e44ad,color:#fff
    style ACT4 fill:#2980b9,color:#fff
    style ACT5 fill:#7f8c8d,color:#fff
    style ACT6 fill:#27ae60,color:#fff
    style ACT7 fill:#f39c12,color:#fff
```

---

## Requirements

**Mandatory — Charger:**

- A `switch` entity to turn the charger on/off
- A current control entity in one of: `number`, `input_number`, `select`, `input_select` (range `6–32 A`)
- A status sensor that reports one of the four accepted values:

  | Status Value | Meaning |
  |---|---|
  | `charger_charging` | Actively charging |
  | `charger_free` | Connected and idle / unplugged |
  | `charger_end` | Session finished |
  | `charger_wait` | Paused / waiting |

**Mandatory — Energy Sensors:**

- EV battery SOC (`%`)
- Home battery SOC (`%`)
- Solar production (`W`)
- Home consumption (`W`)
- Grid import (`W`, positive = importing, negative = exporting)

**Optional but recommended:**

- A PV forecast sensor (`kWh`) for Night Smart Charge decision logic
- One or more `notify.mobile_app_*` services for push notifications
- A `person` entity for presence-aware notification filtering
- A `number` or `input_number` helper to receive the calculated nightly energy target

---

## Installation

### HACS (Recommended)

1. Open **HACS** in Home Assistant.
2. Go to **Integrations**.
3. Open the **Custom Repositories** dialog (three-dot menu).
4. Add `https://github.com/antbald/ha-ev-smart-charger` as category **Integration**.
5. Search for `EV Smart Charger` and install it.
6. Restart Home Assistant.

### Manual

1. Download the [latest release](https://github.com/antbald/ha-ev-smart-charger/releases).
2. Extract `custom_components/ev_smart_charger`.
3. Copy the folder to:

```
/config/custom_components/ev_smart_charger/
```

4. Restart Home Assistant.

---

## Configuration

Add the integration from **Settings → Devices & Services → Add Integration** and search for `EV Smart Charger`. The setup wizard has **6 steps**.

### Step 1 — Name

| Field | Required | Default |
|---|:---:|---|
| Integration name | No | `EV Smart Charger` |

Choose the display name used in the Home Assistant UI.

### Step 2 — Charger Entities

| Field | Required | Accepted Domains |
|---|:---:|---|
| Charger switch | Yes | `switch` |
| Charging current control | Yes | `number`, `input_number`, `select`, `input_select` |
| Charger status sensor | Yes | `sensor` |

The charger switch entity is used as the unique ID for the config entry. Adding the same charger twice is prevented automatically.

### Step 3 — Energy Sensors

| Field | Required | Unit |
|---|:---:|---|
| EV battery SOC | Yes | `%` |
| Home battery SOC | Yes | `%` |
| Solar production | Yes | `W` |
| Home consumption | Yes | `W` |
| Grid import | Yes | `W` |

### Step 4 — PV Forecast

| Field | Required | Unit |
|---|:---:|---|
| PV forecast sensor | No | `kWh` |

Used by Night Smart Charge to decide between home battery and grid charging. If omitted, Night Smart Charge will always fall back to grid mode.

### Step 5 — Notifications

| Field | Required | Notes |
|---|:---:|---|
| Notify services | No | Multiple `notify.mobile_app_*` services |
| Car owner | Yes | A `person` entity |

The `person` entity enables presence-based filtering: notifications are only sent when the car owner is home. If the entity is unavailable, notifications are sent anyway as a fail-safe.

### Step 6 — External Connectors

| Field | Required | Default | Validation |
|---|:---:|---|---|
| Battery capacity | Yes | `50.0 kWh` | `10–200 kWh` |
| Energy forecast target | No | — | `number` or `input_number` domain |

The energy forecast target is an external helper entity where the integration writes the calculated nightly forecast value. Useful for automations or dashboards that need this figure.

### Reconfigure

The integration supports native reconfiguration for existing entries. Navigate to **Settings → Devices & Services**, click on the integration entry, and select **Reconfigure** to update any mapping without deleting the entry and losing your helper entity states.

---

## Created Entities

After setup, the integration creates **60 entities** grouped under a single `EV Smart Charger` device:

| Platform | Count |
|---|:---:|
| `switch` | 20 |
| `number` | 27 |
| `select` | 1 |
| `time` | 4 |
| `sensor` | 7 |
| **Total** | **60** |

Entity IDs follow the pattern `<platform>.ev_smart_charger_<entry_id_fragment>_<suffix>`. The sections below use the suffix alone for brevity.

All helper entities persist their state across Home Assistant restarts via `RestoreEntity`.

---

### Charging Profile

| Suffix | Options | Default | Description |
|---|---|:---:|---|
| `evsc_charging_profile` | `manual`, `solar_surplus` | `manual` | Active charging mode |

---

### Switches — Control

| Suffix | Default | Description |
|---|:---:|---|
| `evsc_forza_ricarica` | OFF | **Force Charge** — global override. When ON, bypasses all automation decisions and keeps the charger running. |
| `evsc_boost_charge_enabled` | OFF | Enables a manual Boost Charge session immediately. Auto-clears when the SOC target is reached. |
| `evsc_boost_schedule_enabled` | OFF | Enables the daily Boost Charge schedule. Runs between `evsc_boost_schedule_start_time` and `evsc_boost_schedule_end_time`. |
| `evsc_smart_charger_blocker_enabled` | OFF | Enables the Smart Charger Blocker to prevent charging outside the allowed window. |
| `evsc_use_home_battery` | OFF | Allows Solar Surplus to draw from the home battery when solar alone is insufficient (requires Priority = EV). |
| `evsc_preserve_home_battery` | OFF | Prevents Night Smart Charge from discharging the home battery regardless of forecast. |
| `evsc_priority_balancer_enabled` | OFF | Enables the Priority Balancer to evaluate daily SOC targets. |
| `evsc_night_smart_charge_enabled` | OFF | Enables overnight automatic charging at the configured time. |
| `evsc_enable_file_logging` | OFF | Enables daily file logging to `logs/<year>/<month>/<day>.log`. Toggle on to capture a session, off when done. |
| `evsc_trace_logging_enabled` | OFF | Enables verbose trace-level logging for deep debugging. |

---

### Switches — Notifications

| Suffix | Default | Description |
|---|:---:|---|
| `evsc_notify_smart_blocker_enabled` | ON | Send notification when Smart Charger Blocker stops the charger. |
| `evsc_notify_priority_balancer_enabled` | ON | Send notification when Priority Balancer state changes. |
| `evsc_notify_night_charge_enabled` | ON | Send notification when Night Smart Charge starts or stops. |

---

### Switches — Car Ready (daily)

One switch per weekday. Controls whether Night Smart Charge should ensure the car is ready (charged to target) by the `evsc_car_ready_time` deadline, even if this means continuing past sunrise.

| Suffix | Default | Applies to |
|---|:---:|---|
| `evsc_car_ready_monday` | ON | Monday |
| `evsc_car_ready_tuesday` | ON | Tuesday |
| `evsc_car_ready_wednesday` | ON | Wednesday |
| `evsc_car_ready_thursday` | ON | Thursday |
| `evsc_car_ready_friday` | ON | Friday |
| `evsc_car_ready_saturday` | OFF | Saturday |
| `evsc_car_ready_sunday` | OFF | Sunday |

When a day's flag is **ON** and the EV target is not yet reached at sunrise, Night Smart Charge continues until target or deadline — whichever comes first. When the flag is **OFF**, charging always stops at sunrise.

---

### Numbers — Solar Surplus

| Suffix | Default | Range | Unit | Description |
|---|:---:|---|:---:|---|
| `evsc_check_interval` | `1` | `1–60` | min | How often Solar Surplus recalculates. |
| `evsc_grid_import_threshold` | `50` | `0–1000` | W | Grid import above this level triggers amperage reduction. |
| `evsc_grid_import_delay` | `30` | `0–120` | s | How long grid import must persist before acting. |
| `evsc_surplus_drop_delay` | `30` | `0–120` | s | How long surplus must be insufficient before stopping the charger. |
| `evsc_solar_max_amperage` | `32` | `6–32` | A | Hard ceiling on Solar Surplus amperage. Lower this if your wallbox rejects currents above a certain value (e.g. set to `16` for wallboxes limited to 16 A). |
| `evsc_home_battery_min_soc` | `20` | `0–100` | % | Home battery must be above this SOC before battery support activates. |
| `evsc_battery_support_amperage` | `16` | `6–32` | A | Amperage used when the home battery supplements solar charging. |

---

### Numbers — Night Smart Charge

| Suffix | Default | Range | Unit | Description |
|---|:---:|---|:---:|---|
| `evsc_night_charge_amperage` | `16` | `6–32` | A | Amperage for overnight charging sessions. |
| `evsc_min_solar_forecast_threshold` | `20` | `0–100` | kWh | If tomorrow's forecast ≥ this value, Night Smart Charge uses home battery mode instead of grid mode. |

---

### Numbers — Boost Charge

| Suffix | Default | Range | Unit | Description |
|---|:---:|---|:---:|---|
| `evsc_boost_charge_amperage` | `16` | `6–32` | A | Amperage used during a Boost Charge session. |
| `evsc_boost_target_soc` | `80` | `0–100` | % | Boost Charge stops automatically when EV SOC reaches this value. |

---

### Numbers — Daily EV SOC Targets

Target EV SOC for each day of the week. Used by the Priority Balancer and Night Smart Charge to decide when the car is "done".

| Suffix | Default |
|---|:---:|
| `evsc_ev_min_soc_monday` | `50 %` |
| `evsc_ev_min_soc_tuesday` | `50 %` |
| `evsc_ev_min_soc_wednesday` | `50 %` |
| `evsc_ev_min_soc_thursday` | `50 %` |
| `evsc_ev_min_soc_friday` | `50 %` |
| `evsc_ev_min_soc_saturday` | `80 %` |
| `evsc_ev_min_soc_sunday` | `80 %` |

---

### Numbers — Daily Home Battery SOC Targets

Target home battery SOC for each day. Used by the Priority Balancer to determine when the home battery is satisfied.

| Suffix | Default |
|---|:---:|
| `evsc_home_min_soc_monday` | `50 %` |
| `evsc_home_min_soc_tuesday` | `50 %` |
| `evsc_home_min_soc_wednesday` | `50 %` |
| `evsc_home_min_soc_thursday` | `50 %` |
| `evsc_home_min_soc_friday` | `50 %` |
| `evsc_home_min_soc_saturday` | `50 %` |
| `evsc_home_min_soc_sunday` | `50 %` |

---

### Time Controls

| Suffix | Default | Description |
|---|:---:|---|
| `evsc_night_charge_time` | `01:00` | Time at which Night Smart Charge activates. |
| `evsc_car_ready_time` | `08:00` | Absolute deadline for car readiness on "Car Ready" days. Charging stops at this time even if the target SOC is not yet reached. |
| `evsc_boost_schedule_start_time` | `07:00` | Daily Boost Charge session start time. |
| `evsc_boost_schedule_end_time` | `08:00` | Daily Boost Charge session end time (hard stop). |

---

### Sensors — Diagnostics

All diagnostic sensors are **read-only**. They are updated continuously by the integration and are the first place to look when troubleshooting.

| Suffix | Description |
|---|---|
| `evsc_diagnostic` | General decision variables: current profile, active automation, charger state, last action. |
| `evsc_priority_daily_state` | Priority Balancer state (`EV` / `Home` / `EV_Free`), today's targets, current SOC values. |
| `evsc_solar_surplus_diagnostic` | Solar Surplus details: surplus watts, target amps, battery support state, delay timers. |
| `evsc_today_ev_target` | Today's EV SOC target (derived from the current weekday). |
| `evsc_today_home_target` | Today's home battery SOC target (derived from the current weekday). |
| `evsc_cached_ev_soc` | Last valid EV SOC value. Preserved when the source sensor becomes `unknown` or `unavailable`. |
| `evsc_log_file_path` | Full path to the active daily log file. Useful for SSH/Samba access. |

---

## Automation Details

### Solar Surplus

Solar Surplus runs every `evsc_check_interval` minutes during **daytime hours only** (sunrise → sunset). It computes the instantaneous surplus (`solar production − home consumption`) and converts it to the nearest supported amperage level from `[6, 8, 10, 13, 16, 20, 24, 32] A` using 230 V as the conversion voltage.

**Hysteresis and stability protection:**

- Charger does not start until surplus is ≥ 6.5 A (`~1495 W`) for at least 60 s (cloud protection)
- A dead-band timer: if surplus stays ≥ 5.5 A (`~1265 W`) for 120 consecutive seconds while the charger is off, charging starts at 6 A (opportunistic dead-band start)
- Charger stops only if surplus drops below 5.5 A for `evsc_surplus_drop_delay` seconds
- Amperage increases require 60 s of stable surplus; decreases require only `evsc_surplus_drop_delay`

The diagram below shows how the surplus (in amps) maps to charging decisions. Thresholds are fixed; only the dead-band start delay is configurable via `SURPLUS_DEADBAND_START_DELAY`.

```
Surplus (A)
  │
  32 ┤━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  ← max level (capped by evsc_solar_max_amperage)
  24 ┤
  20 ┤
  16 ┤────────────────────────────── ← amperage steps [6,8,10,13,16,20,24,32]
  13 ┤
  10 ┤
   8 ┤
   6 ┤
     │
 6.5 ┤╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌  ← START threshold (needs 60s stable)
 5.5 ┤╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌  ← STOP threshold / dead-band floor
     │    ↕ dead band (no action    ← dead-band start after 120s
     │      unless timer expires)
   0 ┤─────────────────────────────→ time
```

```mermaid
flowchart TD
    CHECK([Periodic check every N minutes]) --> NIGHT{Daytime?}
    NIGHT -->|No| SKIP([Skip — nighttime])
    NIGHT -->|Yes| CALC[Calculate surplus\nsolar − consumption]

    CALC --> PB{Priority\nBalancer state?}
    PB -->|Home| STOP_H([Stop charger\nHome battery needs energy])
    PB -->|EV_Free| STOP_F([Stop charger\nBoth targets met])
    PB -->|EV or disabled| SURPLUS{Surplus ≥ 6.5 A\n~1495 W?}

    SURPLUS -->|Yes| INC[Start or increase\namperage 60s stability]
    SURPLUS -->|No| DEAD{Surplus ≥ 5.5 A\nfor 120s?}
    DEAD -->|Yes| START6[Start at 6 A\ndead-band opportunistic]
    DEAD -->|No| BATT{Battery support\nactive?}
    BATT -->|Yes| FIXED[Charge at\nevsc_battery_support_amperage]
    BATT -->|No| DROP{Below 5.5 A\nfor drop delay?}
    DROP -->|Yes| STOP([Stop charger])
    DROP -->|No| HOLD([Hold current amperage])

    GRID{Grid import\n> threshold?} -->|Yes, after delay| REDUCE[Reduce amperage\none step]
    INC --> GRID
    START6 --> GRID
    FIXED --> GRID

    style STOP_H fill:#27ae60,color:#fff
    style STOP_F fill:#27ae60,color:#fff
    style STOP fill:#e74c3c,color:#fff
    style START6 fill:#f39c12,color:#fff
    style INC fill:#2980b9,color:#fff
    style FIXED fill:#8e44ad,color:#fff
```

**Grid import protection:**

If grid import exceeds `evsc_grid_import_threshold` for more than `evsc_grid_import_delay` seconds, amperage is reduced by one step. Recovery requires surplus to drop below 50 % of the threshold and remain there for 60 s before amperage is restored one step at a time.

**Home battery support** (optional):

When `evsc_use_home_battery` is ON, home battery SOC ≥ `evsc_home_battery_min_soc`, and Priority Balancer state = `EV`, the home battery supplements solar. If surplus < 6 A but battery support is active, the charger runs at `evsc_battery_support_amperage` instead of stopping.

**Solar max amperage cap:**

`evsc_solar_max_amperage` (default `32 A`) sets a hard ceiling so Solar Surplus never exceeds what your wallbox accepts. Set this to `16` if your wallbox rejects `20 A` or higher commands.

---

### Priority Balancer

The Priority Balancer reads today's EV and home battery SOC targets (from the daily entities) and compares them against current sensor values. It resolves to one of three states:

| State | Meaning | Effect on Solar Surplus |
|---|---|---|
| `EV` | EV SOC below today's target | Solar charges EV; home battery support may activate |
| `Home` | EV target met, home battery below target | Solar Surplus pauses; home battery charges itself |
| `EV_Free` | Both targets met | Solar Surplus stops immediately; opportunistic charging only if profile allows |

```mermaid
stateDiagram-v2
    direction LR
    [*] --> EV : Day starts\nEV SOC below target

    EV --> Home : EV target ✅\nHome SOC below target
    EV --> EV_Free : Both targets ✅

    Home --> EV_Free : Home target ✅
    Home --> EV : New day\n(targets reset)

    EV_Free --> EV : New day\n(EV below new target)

    state EV {
        ev1 : 🚗 Charge EV first
        ev2 : Home battery support\nmay supplement solar
        ev1 --> ev2
    }

    state Home {
        h1 : 🔋 Protect home battery
        h2 : Solar Surplus paused\nHome charges itself
        h1 --> h2
    }

    state EV_Free {
        f1 : ✅ Both targets met
        f2 : Opportunistic solar only\nNo battery support
        f1 --> f2
    }
```

When the balancer is **disabled**, Solar Surplus treats the charger as always having `EV` priority.

**Key entities:** `evsc_priority_balancer_enabled`, `evsc_ev_min_soc_<day>`, `evsc_home_min_soc_<day>`, `sensor.evsc_priority_daily_state`

---

### Night Smart Charge

Night Smart Charge activates at `evsc_night_charge_time` (default `01:00`) and runs until the EV reaches its daily SOC target or sunrise, whichever comes first.

**Mode selection** (evaluated at activation):

| Condition | Mode |
|---|---|
| PV forecast ≥ `evsc_min_solar_forecast_threshold` AND `evsc_use_home_battery` ON AND `evsc_preserve_home_battery` OFF | **Battery mode** — charges from home battery |
| Any other condition | **Grid mode** — charges from grid |

```mermaid
flowchart TD
    T([evsc_night_charge_time reached]) --> EN{Night Smart Charge\nenabled?}
    EN -->|No| SKIP([Skip — no action])
    EN -->|Yes| EV{EV SOC ≥\ndaily target?}
    EV -->|Yes| SKIP
    EV -->|No| F1{PV forecast ≥\nthreshold?}

    F1 -->|No| GRID
    F1 -->|Yes| F2{use_home_battery\nON?}
    F2 -->|No| GRID
    F2 -->|Yes| F3{preserve_home_battery\nOFF?}
    F3 -->|No| GRID
    F3 -->|Yes| F4{Home battery SOC\n> min threshold?}

    F4 -->|Yes| BAT([🔋 Battery Mode\nCharge from home battery])
    F4 -->|No| F5{car_ready\ntoday?}
    F5 -->|Yes| GRID([⚡ Grid Mode\nCharge from grid])
    F5 -->|No| SKIP

    GRID --> MONITOR{Monitor every 15s\nEV target reached\nor sunrise?}
    BAT --> MONITOR
    MONITOR -->|EV target ✅| DONE([Session complete\nHandoff to Solar Surplus])
    MONITOR -->|Sunrise + car_ready OFF| DONE
    MONITOR -->|Sunrise + car_ready ON| EXT{car_ready_time\nreached?}
    EXT -->|No| MONITOR
    EXT -->|Yes| DONE

    style BAT fill:#2980b9,color:#fff
    style GRID fill:#e67e22,color:#fff
    style DONE fill:#27ae60,color:#fff
    style SKIP fill:#7f8c8d,color:#fff
```

**Battery mode pre-check:** Before starting, the home battery SOC is validated. If it is already ≤ `evsc_home_battery_min_soc`, the session checks the day's `evsc_car_ready_<day>` flag:
- Flag **ON** → falls back to grid mode to ensure car is ready
- Flag **OFF** → skips charging entirely (waits for solar surplus)

**Car Ready extension:** On days where `evsc_car_ready_<day>` is ON, if the EV target is not reached at sunrise, charging continues from the grid until the target is met or `evsc_car_ready_time` is reached.

**Late-arrival detection:** If the car is plugged in after `evsc_night_charge_time` but before sunrise, Night Smart Charge detects the late arrival and starts a session immediately.

**Charger start retry:** If the charger fails to start on the first attempt, Night Smart Charge retries with exponential backoff before giving up and logging an error.

**Key entities:** `evsc_night_smart_charge_enabled`, `evsc_night_charge_time`, `evsc_night_charge_amperage`, `evsc_min_solar_forecast_threshold`, `evsc_car_ready_<day>`, `evsc_car_ready_time`, `evsc_preserve_home_battery`

---

### Boost Charge

Boost Charge is a high-priority override that guarantees the EV reaches `evsc_boost_target_soc` as quickly as possible at `evsc_boost_charge_amperage`.

**Manual mode:** Toggle `evsc_boost_charge_enabled` ON at any time. The session starts immediately, runs at full configured amperage, and stops automatically when the SOC target is reached. The switch reverts to OFF on completion.

**Scheduled mode:** Enable `evsc_boost_schedule_enabled` and configure `evsc_boost_schedule_start_time` / `evsc_boost_schedule_end_time`. Every day at the start time the integration checks:
- Car plugged in? If not, the session is silently skipped.
- EV SOC already ≥ target? If so, the session is silently skipped.
- Otherwise, charging starts at `evsc_boost_charge_amperage`.

If the car is plugged in *after* the start time but while still within the scheduled window, the session starts immediately on plug-in — no manual intervention needed.

The session ends at the configured end time even if the SOC target has not been reached. Disabling the schedule toggle mid-session stops the charger immediately.

**Key entities:** `evsc_boost_charge_enabled`, `evsc_boost_schedule_enabled`, `evsc_boost_charge_amperage`, `evsc_boost_target_soc`, `evsc_boost_schedule_start_time`, `evsc_boost_schedule_end_time`

---

### Smart Charger Blocker

Smart Charger Blocker listens for `charger_charging` status events and stops the charger if the activation occurs inside the blocking window.

**Blocking window:**

- When Night Smart Charge is **enabled**: sunset → `evsc_night_charge_time`
- When Night Smart Charge is **disabled**: sunset → sunrise

**Charging is allowed when any of the following apply:**

- `evsc_forza_ricarica` is ON (Force Charge override)
- Night Smart Charge owns the active session
- A Boost Charge session is active
- `evsc_smart_charger_blocker_enabled` is OFF

When the blocker stops the charger, it sends a push notification (if `evsc_notify_smart_blocker_enabled` is ON and the car owner is home) and enforces a 30-minute re-check window to prevent log spam.

**Key entities:** `evsc_smart_charger_blocker_enabled`, `evsc_forza_ricarica`, `evsc_notify_smart_blocker_enabled`

---

### Cached EV SOC

Many cloud-based EV integrations (e.g., manufacturer apps) expose SOC sensors that temporarily go `unknown` or `unavailable` due to API rate limits or connectivity issues. This causes downstream automations to fail or make wrong decisions.

The Cached EV SOC component polls the source EV SOC sensor every **5 seconds** and writes the last valid value to `sensor.evsc_cached_ev_soc`. When the source goes unavailable, the cached value is preserved until a new valid reading arrives. All internal logic uses the cached sensor, not the source directly.

**Key entity:** `sensor.evsc_cached_ev_soc`

---

## Dashboard Card

The integration bundles a Lovelace custom card served directly from the integration's HTTP endpoint. No external CDN or separate download is needed.

**Step 1 — Register the resource**

Add to your Lovelace resources (edit mode → Manage Resources, or directly in `ui-lovelace.yaml`):

```yaml
lovelace:
  resources:
    - url: /api/ev_smart_charger/frontend/ev-smart-charger-dashboard.js
      type: module
```

**Step 2 — Add the card**

```yaml
type: custom:ev-smart-charger-dashboard
title: EV Smart Charger
entity_prefix: ev_smart_charger_<entry_id>
```

**Full configuration reference:**

| Parameter | Required | Description |
|---|:---:|---|
| `entity_prefix` | **Yes** | Prefix that matches the integration's config entry. Find it in your entity IDs (part between `ev_smart_charger_` and `_evsc_*`). |
| `title` | No | Card title shown in the header. |
| `charging_power_entity` | No | Sensor for live charging power (shown in hero metrics). |
| `ev_soc_entity` | No | Sensor for current EV battery level (shown in hero metrics). |
| `home_battery_soc_entity` | No | Sensor for current home battery level (shown in hero metrics). |
| `solar_power_entity` | No | Sensor for solar production (shown in hero metrics). |
| `grid_import_entity` | No | Sensor for grid import/export (shown in hero metrics). |
| `current_entity` | No | Number entity for current wallbox amperage (shown in hero metrics). |

The card calls Home Assistant services directly (`switch.toggle`, `number.set_value`, `select.select_option`, `time.set_value`) using the entity prefix to resolve helper entities.

---

## Logging & Diagnostics

### Diagnostic Sensors

The quickest way to understand what the integration is doing is to inspect the diagnostic sensors in **Developer Tools → States**:

- `evsc_diagnostic` — overall decision state
- `evsc_solar_surplus_diagnostic` — solar surplus calculation details
- `evsc_priority_daily_state` — today's priority state and SOC comparisons

### File Logging

Enable `evsc_enable_file_logging` to write all integration activity to a dedicated daily file. Logs are stored at:

```
/config/custom_components/ev_smart_charger/logs/<year>/<month>/<day>.log
```

A new file is created automatically at midnight. Previous days are kept indefinitely. Access log files via SSH, the File Editor add-on, or Samba share.

When troubleshooting is complete, disable the toggle to stop writing. Existing log files are preserved.

### Trace Logging

Enable `evsc_trace_logging_enabled` for verbose output including every sensor read, every calculation step, and every state transition. Intended for short diagnostic sessions — disable immediately after use to avoid performance impact.

### HA Debug Logging

For lower-level Home Assistant framework logging, add to `configuration.yaml`:

```yaml
logger:
  default: info
  logs:
    custom_components.ev_smart_charger: debug
```

Restart Home Assistant for the change to take effect. Logs appear in **Settings → System → Logs** (search for `evsc`).

---

## Notifications & Presence

Push notifications are sent via the `notify.mobile_app_*` services configured during setup. The car owner `person` entity enables **presence-aware filtering**: a notification is only dispatched when the person's state is `home`.

If the `person` entity is unavailable, notifications are always sent (fail-safe default). If no notify services are configured, no notifications are sent.

**Per-feature notification toggles:**

| Switch | Default | Controls |
|---|:---:|---|
| `evsc_notify_smart_blocker_enabled` | ON | Notifications when Smart Charger Blocker stops the charger |
| `evsc_notify_priority_balancer_enabled` | ON | Notifications when Priority Balancer state changes |
| `evsc_notify_night_charge_enabled` | ON | Notifications when Night Smart Charge starts or completes |

---

## Analytics & Privacy

EV Smart Charger sends one anonymous ping per day to help the maintainer track active installations, version adoption, and approximate geographic distribution.

**What is sent:**

| Field | Example | Purpose |
|---|---|---|
| `installation_id` | `a3f2…` (random UUID) | Count unique installs — never reused across uninstalls |
| `version` | `1.6.18` | Version adoption tracking |
| `ha_version` | `2026.4.0` | HA compatibility insight |
| `timezone` | `Europe/Rome` | Approximate region |
| `country` | `IT` | Derived from timezone — no geolocation |
| `continent` | `EU` | Aggregate geographic distribution |

**What is NOT sent:** IP address, hostname, entity IDs, sensor values, configuration data, credentials, or any personally identifiable information.

Data is stored in a private sheet accessible only to the maintainer. Aggregated statistics may be published publicly.

**Opt-out:** Set the environment variable `EVSC_DISABLE_TELEMETRY=true` on your Home Assistant host (e.g., in `/etc/environment` or your Docker Compose file).

---

## Troubleshooting

**Start with these checks:**

1. Confirm the mapped charger switch can be toggled manually in **Developer Tools → Services**.
2. Confirm the charger status sensor returns one of the four accepted values (`charger_charging`, `charger_free`, `charger_end`, `charger_wait`). Custom or localised values will not be recognised.
3. Confirm solar production, home consumption, and grid import sensors report values in Watts (`W`). kW-scale sensors will result in wrong surplus calculations.
4. If EV SOC comes from a cloud integration, check `sensor.evsc_cached_ev_soc` — the source may be intermittently unavailable.
5. Check the diagnostic sensors and, if needed, enable file logging for a full session trace.

**Common mistakes:**

| Symptom | Likely Cause |
|---|---|
| Night Smart Charge never activates | `evsc_night_smart_charge_enabled` is OFF, or EV target already met at `01:00` |
| Solar Surplus starts late or not at all | Surplus below 1495 W (6.5 A threshold), or profile not set to `solar_surplus` |
| Charger keeps getting blocked | Smart Charger Blocker is ON and charger started during the blocking window |
| Notifications not arriving | `person` entity is not `home`, or notify service name is wrong |
| Amperage stuck at low value | `evsc_solar_max_amperage` is set lower than expected, or grid import protection is active |

**Useful entities for investigation:**

- `sensor.*_evsc_diagnostic`
- `sensor.*_evsc_solar_surplus_diagnostic`
- `sensor.*_evsc_priority_daily_state`
- `sensor.*_evsc_log_file_path`
- `sensor.*_evsc_cached_ev_soc`

---

## Supported Languages

The integration ships translated UI strings and runtime messages for:

| Language | Code | Status |
|---|:---:|:---:|
| English | `en` | ✅ Full |
| Italian | `it` | ✅ Full |
| Dutch | `nl` | ✅ Full |

Available documentation:

- English: this README
- Dutch: [docs/README.nl.md](docs/README.nl.md)

---

## Documentation

**User-facing:**

- Main guide: this README
- [Dutch guide](docs/README.nl.md)

**Technical and maintenance:**

- [Documentation index](docs/README.md)
- [Architecture SSOT](docs/SSOT.md)
- [Codebase map](docs/CODEBASE_MAP.md)
- [Refactor plan / hardening record](docs/REFACTOR_PLAN.md)

---

## License

MIT. See [LICENSE](LICENSE).

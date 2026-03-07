# 🚗⚡ EV Smart Charger

[![GitHub Release](https://img.shields.io/github/v/release/antbald/ha-ev-smart-charger)](https://github.com/antbald/ha-ev-smart-charger/releases)
[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/custom-components/hacs)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

**Intelligent EV charging automation for Home Assistant** - Maximize solar energy usage, optimize battery balance, and automate overnight charging with complete control over your EV charger.

---

## 📋 Table of Contents

- [Quick Start](#-quick-start)
- [Key Features](#-key-features)
- [Installation](#-installation)
- [Configuration](#-configuration)
- [Charging Modes](#-charging-modes)
- [Automation Features](#-automation-features)
- [Dashboard Setup](#-dashboard-setup)
- [Documentation](#-documentation)
- [Troubleshooting](#-troubleshooting)
- [Version History](#-version-history)

---

## 🚀 Quick Start

### What This Integration Does

EV Smart Charger transforms your Home Assistant into an intelligent EV charging controller that:

✅ **Charges your EV using only excess solar energy** (Solar Surplus mode)
✅ **Balances charging between EV and home battery** (Priority Balancer)
✅ **Automates overnight charging** based on solar forecast (Night Smart Charge)
✅ **Runs manual boost sessions with auto-stop on EV SOC** (Boost Charge)
✅ **Prevents nighttime charging** when solar is unavailable (Smart Blocker)
✅ **Protects against unreliable cloud sensors** (Cache layer for cloud-based car integrations)

### Requirements

- **Home Assistant** 2024.4+
- **EV charger** with switch and amperage control (6-32A)
- **Solar system** with production monitoring
- **Home battery** (optional, for advanced features)
- **EV integration** (Tesla, BMW, VW, etc.)

### 5-Minute Setup

1. **Install via HACS** (recommended) or manual installation
2. **Add integration**: Settings → Devices & Services → Add Integration → "EV Smart Charger"
3. **Configure entities** in the 6-step wizard (name, charger, sensors, PV forecast, notifications, external connectors)
4. **Enable features** you want via dashboard switches
5. **Start charging!** 🎉

Supported charging profiles in the UI: `manual` and `solar_surplus`. Night Smart Charge and Boost Charge are enabled through their dedicated helper entities.

---

## ✨ Key Features

### 🌞 Solar Surplus Charging
Charge your EV **only** when excess solar energy is available. Never import from grid.
- **Automatic amperage adjustment** (6-32A) based on surplus
- **Grid import protection** with configurable thresholds
- **Cloud protection** with stability delays (prevents oscillations)
- **Home battery support** (optional fallback when surplus drops)

### ⚖️ Priority Balancer
**Intelligent charging prioritization** between EV and home battery.
- **Daily SOC targets** for EV (configurable per day of week)
- **Daily SOC targets** for home battery (configurable per day of week)
- **Three priority modes:**
  - 🚗 **EV Priority**: Charge EV first until target reached
  - 🏠 **Home Priority**: Charge home battery first, EV waits
  - 🆓 **EV_Free**: Both targets met, opportunistic EV charging
- **Real-time priority tracking** via diagnostic sensor

### 🌙 Night Smart Charge
**Intelligent overnight charging** based on next-day solar forecast.
- **Automatic mode selection:**
  - ☀️ **High forecast** (≥ threshold): Charge from home battery
  - 🌧️ **Low forecast** (< threshold): Charge from grid
- **Daily car ready flags** (weekdays vs weekends)
- **Seamless transition** to solar surplus at sunrise
- **Late arrival detection** (car plugged in after scheduled time)

### ⚡ Boost Charge
**Manual override charging with automatic stop at a target EV SOC.**
- **Dedicated boost switch** separate from `Forza Ricarica`
- **Configurable fixed amperage** (6-32A)
- **Configurable EV SOC target** (0-100%)
- **Automatic return** to normal automations when the target is reached

### 🚫 Smart Blocker
**Automatic nighttime charging prevention** when solar is unavailable.
- **Sunset to sunrise blocking** (with Night Smart Charge integration)
- **Override protection** for Night Smart Charge mode
- **Persistent notifications** when charging blocked

### 🛡️ Cloud Sensor Reliability (v1.4.0)
**Automatic caching layer** for unreliable cloud-based car sensors.
- **5-second polling** of cloud sensor
- **Automatic caching** maintains last valid value during outages
- **Silent operation** when sensor working normally
- **Zero configuration** - works automatically after restart

---

## 📦 Installation

### Option 1: HACS (Recommended)

1. Open **HACS** in Home Assistant
2. Click **Integrations**
3. Click **⋮** (three dots) → **Custom repositories**
4. Add repository URL: `https://github.com/antbald/ha-ev-smart-charger`
5. Category: **Integration**
6. Click **Add**
7. Search for **"EV Smart Charger"**
8. Click **Download**
9. **Restart Home Assistant**

### Option 2: Manual Installation

1. Download the latest release from [GitHub Releases](https://github.com/antbald/ha-ev-smart-charger/releases)
2. Extract `custom_components/ev_smart_charger` folder
3. Copy to your Home Assistant `custom_components` directory:
   ```
   /config/custom_components/ev_smart_charger/
   ```
4. **Restart Home Assistant**

---

## ⚙️ Configuration

### Step 1: Add Integration

1. Go to **Settings → Devices & Services**
2. Click **+ Add Integration**
3. Search for **"EV Smart Charger"**
4. Click to start setup wizard

### Step 2: Setup Wizard (6 Steps)

#### 📝 Step 1: Name Your Integration
- Enter a friendly name (e.g., "EV Smart Charger")
- This name appears in Home Assistant UI

#### 🔌 Step 2: Configure Charger Entities
Map your existing charger entities:

| Field | Description | Example |
|-------|-------------|---------|
| **EV Charger Switch** | Switch that controls charger on/off | `switch.wallbox_charger` |
| **EV Charger Current** | Number/Select for amperage (6-32A) | `number.wallbox_amperage` |
| **EV Charger Status** | Sensor showing charger state | `sensor.wallbox_status` |

**Charger Status Values:**
- `charger_charging` - Actively charging
- `charger_free` - No car connected
- `charger_end` - Charging complete
- `charger_wait` - Ready to charge

#### 📊 Step 3: Configure Monitoring Sensors
Map your existing monitoring sensors:

| Field | Description | Unit | Example |
|-------|-------------|------|---------|
| **Car Battery SOC** | EV battery level | % | `sensor.tesla_battery_level` |
| **Home Battery SOC** | Home battery level | % | `sensor.powerwall_battery_level` |
| **Solar Production** | Current PV production | W | `sensor.solar_production` |
| **Home Consumption** | Current home power usage | W | `sensor.home_consumption` |
| **Grid Import** | Power from grid (+ = import) | W | `sensor.grid_import` |

#### ☀️ Step 4: Configure PV Forecast (Optional)
For Night Smart Charge feature:

| Field | Description | Unit | Example |
|-------|-------------|------|---------|
| **PV Forecast** | Next-day solar forecast | kWh | `sensor.solcast_forecast_tomorrow` |

**Popular Forecast Integrations:**
- Solcast Solar
- Forecast.Solar
- OpenWeatherMap (with solar forecast)

**Skip this step** if you don't want Night Smart Charge feature.

#### 📱 Step 5: Configure Notifications
- Select mobile app notify services (optional)
- Select the person entity representing the car owner

#### 🔗 Step 6: Configure External Connectors
- Set EV battery capacity in kWh
- Optionally choose a `number` or `input_number` helper for the energy forecast output

### Step 3: Automatic Helper Entities

After setup, the integration **automatically creates 51 entities**:

- 🔘 **17 Switches** (feature toggles, car ready flags, notifications)
- 🔢 **24 Numbers** (intervals, thresholds, delays, targets, boost controls)
- ⏰ **2 Time** entities (night charge start time, car ready deadline)
- 📋 **1 Select** (charging profile selector)
- 📊 **7 Sensors** (diagnostics, targets, cached EV SOC, log path)

**No manual setup required!** All entities persist across restarts.

---

## 🔋 Charging Modes

### 1. Manual Mode
**Standard charging without automation** - Full manual control.

**When to use:**
- Testing charger functionality
- Override all automations
- Emergency charging

**How to enable:**
1. Set **Charging Profile** to `manual`
2. Control charger manually via its native switch

---

### 2. Solar Surplus Mode ☀️

**Charge your EV using ONLY excess solar energy.**

#### How It Works

```
1. Calculate Surplus = Solar Production - Home Consumption
2. Convert to Amperage = Surplus (W) / 230V
3. Find Closest Level = [6, 8, 10, 13, 16, 20, 24, 32]A
4. Start/Adjust Charger
```

---

### 3. Boost Charge ⚡

**Force charging immediately at a fixed amperage until a target EV SOC is reached.**

**When to use:**
- Urgent top-up before a trip
- Override solar-only logic temporarily
- Avoid forgetting a manual stop after enabling an override

**How it works:**
1. Turn ON **Boost Charge**
2. Set **Boost Charge Amperage**
3. Set **Boost Target SOC**
4. Charging starts immediately and stops automatically at the target
5. The system disables Boost Charge and returns to normal automations

**Important:**
- `Boost Charge` is independent from `Forza Ricarica`
- `Forza Ricarica` remains a manual continuous override
- `Boost Charge` auto-disables itself when the configured target is reached

#### Key Features

✅ **Never imports from grid** - Grid import protection with configurable threshold
✅ **Smooth transitions** - Gradual amperage changes prevent charger stress
✅ **Cloud protection** - Stability delays prevent oscillations from passing clouds
✅ **Home battery support** - Optional fallback when surplus drops

#### Configuration Entities

---

## 📚 Documentation

User guides:

- [Dutch setup and usage guide](docs/README.nl.md)

For maintainers and deeper technical analysis:

- [Documentation index](docs/README.md)
- [Architecture SSOT](docs/SSOT.md)
- [Codebase map](docs/CODEBASE_MAP.md)
- [Hardening cycle status](docs/REFACTOR_PLAN.md)

| Entity | Default | Range | Description |
|--------|---------|-------|-------------|
| **Check Interval** | 1 min | 1-60 min | How often to recalculate |
| **Grid Import Threshold** | 50 W | 0-1000 W | Max import before reducing |
| **Grid Import Delay** | 30 s | 0-120 s | Delay before reacting to import |
| **Surplus Drop Delay** | 30 s | 0-120 s | Delay before reducing on drop |
| **Use Home Battery** | OFF | ON/OFF | Enable battery support fallback |
| **Home Battery Min SOC** | 20% | 0-100% | Min battery level for support |
| **Battery Support Amperage** | 16A | 6-32A | Fixed amperage when using battery |

#### Example Scenario

```
☀️ 12:00 PM - Solar 8000W, Home 2000W
   → Surplus: 6000W (26A)
   → Start charging at 24A

☁️ 12:30 PM - Cloud passes, Solar 4000W
   → Surplus: 2000W (8A)
   → Wait 30s (surplus drop delay)
   → Reduce to 8A

☀️ 12:35 PM - Cloud clears, Solar 7000W
   → Surplus: 5000W (21A)
   → Increase to 20A

🌙 Sunset - Solar 0W
   → Sunset transition guard
   → Try handover to Night Smart Charge
   → If handover rejected: safe stop
```

#### Requirements

- Charging profile set to `solar_surplus`
- Charger status: `charger_charging`, `charger_end`, or `charger_wait`
- Does NOT activate when `charger_free` (car not connected)

---

## 🤖 Automation Features

### ⚖️ Priority Balancer

**Intelligent prioritization between EV and home battery charging.**

#### How It Works

Every check interval, Priority Balancer calculates:

1. **Get today's targets** from daily SOC configuration
2. **Compare current SOCs** vs targets
3. **Determine priority:**
   - 🚗 **EV Priority**: EV < target → Charge EV first
   - 🏠 **Home Priority**: EV ≥ target, Home < target → Charge Home first
   - 🆓 **EV_Free**: Both ≥ targets → Opportunistic EV charging

#### Configuration

**EV Daily Targets** (7 number entities):
- `number.evsc_ev_min_soc_monday` through `sunday`
- Default: 50% (weekdays), 80% (weekends)
- Range: 0-100% in 5% steps

**Home Daily Targets** (7 number entities):
- `number.evsc_home_min_soc_monday` through `sunday`
- Default: 50% (all days)
- Range: 0-100% in 5% steps

#### Example Scenarios

| Day | EV SOC | EV Target | Home SOC | Home Target | Priority | Action |
|-----|--------|-----------|----------|-------------|----------|--------|
| Monday | 40% | 50% | 60% | 50% | **EV** | Charge EV first |
| Tuesday | 55% | 50% | 45% | 50% | **Home** | Stop EV, charge Home |
| Wednesday | 60% | 50% | 55% | 50% | **EV_Free** | Both met, opportunistic |
| Thursday | unavailable | 50% | 60% | 50% | **EV** | Safe fallback |

#### Sensor Monitoring

**Priority State Sensor**: `sensor.evsc_priority_daily_state`

**States:**
- `"EV"` - EV charging priority
- `"Home"` - Home battery charging priority
- `"EV_Free"` - Both targets met

**Attributes:**
- `current_ev_soc`: Current EV battery %
- `target_ev_soc`: Today's EV target %
- `current_home_soc`: Current home battery %
- `target_home_soc`: Today's home target %
- `reason`: Explanation of priority decision
- `today`: Current day of week

---

### 🌙 Night Smart Charge

**Intelligent overnight charging based on next-day solar forecast.**

#### How It Works

```
1. At configured time (default 01:00):
   ├─ Check next-day PV forecast
   ├─ Check current EV SOC vs target
   └─ Decide charging mode:
      ├─ ☀️ High Forecast (≥ threshold)
      │  └─ BATTERY MODE: Charge from home battery
      │     - Fixed amperage (default 16A)
      │     - Stops when EV target OR home battery min reached
      │
      └─ 🌧️ Low Forecast (< threshold)
         └─ GRID MODE: Charge from grid
            - Fixed amperage (default 16A)
            - Stops when EV target reached

2. Monitor until sunrise:
   └─ Check every minute
      ├─ Stop when target reached
      └─ Detect late arrivals

3. At sunrise:
   └─ Transition to Solar Surplus mode
```

**Sunset transition safety (Solar Surplus → Night):**
- If Solar Surplus is still charging at night, the integration does not just skip checks.
- It first enforces EV target hard cap.
- Then it tries an explicit handover to Night Smart Charge.
- If handover is not accepted, charger is stopped immediately (safe fallback).

#### Configuration Entities

| Entity | Default | Range | Description |
|--------|---------|-------|-------------|
| **Enable Night Charge** | OFF | ON/OFF | Master switch |
| **Night Charge Time** | 01:00 | 00:00-23:59 | When to start check |
| **Min Solar Forecast Threshold** | 20 kWh | 0-100 kWh | Forecast to use battery |
| **Night Charge Amperage** | 16A | 6-32A | Fixed charging amperage |

#### Car Ready Flags (v1.3.13+)

**Purpose:** Control fallback behavior when home battery is below threshold.

**7 Switch Entities:**
- `switch.evsc_car_ready_monday` through `sunday`
- Default: ON (weekdays), OFF (weekends)

**Behavior:**

| Car Ready | Home Battery | Action |
|-----------|--------------|--------|
| **ON** (weekday) | Below threshold | **GRID MODE** fallback - ensures car ready |
| **OFF** (weekend) | Below threshold | **SKIP** charging - wait for solar surplus |

When Night Smart Charge is already active in BATTERY mode and home battery drops to min SOC:
- **Car Ready ON**: transition from BATTERY to GRID in the same night session (no daily lock).
- **Car Ready OFF**: stop session and mark it as terminal for today (`completed_today`).

`completed_today` is set only for terminal stop reasons (deadline/sunrise, EV target reached, charger no longer charging, unrecoverable fallback failure).

**Use Cases:**
- 📅 **Weekdays**: Car needed for work → Flag ON → Grid fallback ensures ready
- 🏖️ **Weekends**: No rush → Flag OFF → Skip charging, wait for sun

#### Example Scenarios

**Scenario 1: Sunny Day Forecast**
```
01:00 - Forecast: 25 kWh (> 20 kWh threshold)
     → Mode: BATTERY
     → Start charging at 16A from home battery
06:45 - EV reaches 80% target
     → Stop charging
06:50 - Sunrise
     → Solar Surplus takes over if needed
```

**Scenario 2: Cloudy Day Forecast**
```
01:00 - Forecast: 12 kWh (< 20 kWh threshold)
     → Mode: GRID
     → Start charging at 16A from grid
06:30 - EV reaches 80% target
     → Stop charging
06:50 - Sunrise
     → Solar Surplus takes over
```

**Scenario 3: Late Arrival**
```
01:00 - No car connected
     → Skip check
02:30 - Car plugged in
     → Detect connection
     → Forecast: 30 kWh
     → Mode: BATTERY
     → Start charging at 16A
```

**Scenario 4: Weekend, Low Battery**
```
01:00 - Saturday, Forecast: 28 kWh
     → Mode: BATTERY
     → Home battery: 15% (< 20% threshold)
     → Car Ready: OFF (weekend)
     → SKIP charging (wait for solar)
```

#### Integration with Other Features

- **Overrides Smart Blocker** during active night charging
- **Works with Priority Balancer** for SOC monitoring
- **Grid import disabled** only during night charging
- **Transitions to Solar Surplus** automatically at sunrise

---

### 🚫 Smart Blocker

**Automatic nighttime charging prevention.**

#### How It Works

```
1. Monitor charger status changes
2. When charger starts:
   ├─ Check: Is "Forza Ricarica" ON?
   │  └─ YES → Allow (manual override)
   ├─ Check: Is Night Smart Charge active?
   │  └─ YES → Allow (night mode)
   ├─ Check: Is Smart Blocker enabled?
   │  └─ NO → Allow
   └─ Check: Is it nighttime?
      ├─ Nighttime → BLOCK + notify
      └─ Daytime → Allow
```

#### Blocking Windows

| Night Charge Enabled | Blocking Window |
|---------------------|-----------------|
| ✅ **ON** | Sunset → Night Charge Time |
| ❌ **OFF** | Sunset → Sunrise |

**Example:**
- Night Charge Time: 01:00
- Sunset: 18:30
- Sunrise: 06:50

**Blocking Window (Night Charge ON):** 18:30 → 01:00
**Blocking Window (Night Charge OFF):** 18:30 → 06:50

#### Configuration

**Enable/Disable:**
- `switch.evsc_smart_charger_blocker_enabled` (default: OFF)

**Override:**
- `switch.evsc_forza_ricarica` - Global override, disables ALL automations

---

### 🛡️ Cloud Sensor Reliability (v1.4.0)

**Automatic caching layer for unreliable cloud-based car sensors.**

#### Problem Solved

Cloud-based car integrations (Tesla, BMW, VW) often show "unknown" or "unavailable" states, causing:
- ❌ Priority Balancer calculation failures
- ❌ Night Charge using incorrect default SOC
- ❌ Solar Surplus battery support errors
- ❌ False "target reached" preventing charging

#### How It Works

```
1. EV SOC Monitor polls cloud sensor every 5 seconds
2. When cloud sensor has valid value:
   └─ Update cache sensor (silent)
3. When cloud sensor is unavailable:
   └─ Maintain last valid value in cache
   └─ Log warning (once per state change)
4. All components read from cache sensor:
   └─ Priority Balancer
   └─ Night Smart Charge
   └─ Solar Surplus
```

#### Architecture

```
Cloud Sensor (unreliable)
    ↓ poll every 5s
EV SOC Monitor
    ↓ update on valid values
Cache Sensor (reliable)
    ↓ always available
All Components
```

#### New Entities

**Cached EV SOC Sensor**: `sensor.evsc_cached_ev_soc`

**Attributes:**
- `source_entity`: Original cloud sensor
- `last_valid_update`: Timestamp of last valid update
- `is_cached`: Boolean (using cached value?)
- `cache_age_seconds`: How old is cached value

#### Logging Behavior

**Normal Operation (Silent):**
```
# No logs when cloud sensor working normally
# Cache updates every 5 seconds silently
```

**Outage Detected (Warning):**
```
⚠️ [EV SOC MONITOR] Using cached EV SOC: 65%
   (source sensor unavailable: unknown)
```

**Recovery (Info):**
```
✅ [PRIORITY BALANCER] Using cached EV SOC sensor:
   sensor.evsc_cached_ev_soc
   (source: sensor.tesla_battery_level)
```

#### Benefits

✅ **No more calculation failures** from unreliable cloud sensors
✅ **Priority Balancer always has valid SOC** for decisions
✅ **Night Charge no longer skips** due to "unknown" EV SOC
✅ **Solar Surplus battery support** more reliable
✅ **Zero configuration** - automatic after restart
✅ **Seamless recovery** when cloud sensor available

---

## 📱 Dashboard Setup

### Modern Dashboard (Mushroom Cards)

Use this layout if the dashboard is primarily used on mobile. It is organized for one-thumb use, fast scanning, and minimal horizontal compression:

- no `horizontal-stack` blocks that become cramped on phones
- quick-glance status at the top
- two columns maximum for tappable cards
- weekly planning grouped by **day** so EV target, Home target, and Ready flag live together

```yaml
type: vertical-stack
cards:
  - type: custom:mushroom-template-card
    primary: EV Smart Charger
    secondary: >
      Priority {{ states('sensor.ev_smart_charger_YOUR_ENTRY_ID_evsc_priority_daily_state') }}
      • Profile {{ states('select.ev_smart_charger_YOUR_ENTRY_ID_evsc_charging_profile') }}
      • EV {{ states('sensor.ev_smart_charger_YOUR_ENTRY_ID_evsc_today_ev_target') }}
      • Home {{ states('sensor.ev_smart_charger_YOUR_ENTRY_ID_evsc_today_home_target') }}
    icon: mdi:ev-station
    icon_color: teal
    layout: horizontal
    multiline_secondary: true
    fill_container: true

  - type: custom:mushroom-chips-card
    alignment: justify
    chips:
      - type: entity
        entity: sensor.ev_smart_charger_YOUR_ENTRY_ID_evsc_priority_daily_state
        icon_color: teal
      - type: entity
        entity: select.ev_smart_charger_YOUR_ENTRY_ID_evsc_charging_profile
        icon_color: blue
      - type: entity
        entity: sensor.ev_smart_charger_YOUR_ENTRY_ID_evsc_today_ev_target
        icon_color: amber
      - type: entity
        entity: sensor.ev_smart_charger_YOUR_ENTRY_ID_evsc_today_home_target
        icon_color: green

  - type: grid
    columns: 2
    square: false
    cards:
      - type: custom:mushroom-entity-card
        entity: switch.ev_smart_charger_YOUR_ENTRY_ID_evsc_forza_ricarica
        name: Forza Ricarica
        icon_color: red
        secondary_info: state
        fill_container: true
      - type: custom:mushroom-entity-card
        entity: switch.ev_smart_charger_YOUR_ENTRY_ID_evsc_boost_charge_enabled
        name: Boost Charge
        icon_color: amber
        secondary_info: state
        fill_container: true
      - type: custom:mushroom-entity-card
        entity: switch.ev_smart_charger_YOUR_ENTRY_ID_evsc_night_smart_charge_enabled
        name: Night Smart Charge
        icon_color: indigo
        secondary_info: state
        fill_container: true
      - type: custom:mushroom-entity-card
        entity: switch.ev_smart_charger_YOUR_ENTRY_ID_evsc_priority_balancer_enabled
        name: Priority Balancer
        icon_color: teal
        secondary_info: state
        fill_container: true
      - type: custom:mushroom-entity-card
        entity: switch.ev_smart_charger_YOUR_ENTRY_ID_evsc_smart_charger_blocker_enabled
        name: Smart Blocker
        icon_color: red
        secondary_info: state
        fill_container: true
      - type: custom:mushroom-entity-card
        entity: switch.ev_smart_charger_YOUR_ENTRY_ID_evsc_use_home_battery
        name: Battery Support
        icon_color: green
        secondary_info: state
        fill_container: true

  - type: custom:mushroom-title-card
    title: Core Controls
    subtitle: Global overrides, scheduling, and energy behavior

  - type: custom:mushroom-select-card
    entity: select.ev_smart_charger_YOUR_ENTRY_ID_evsc_charging_profile
    name: Charging Profile
    icon_color: blue

  - type: entities
    title: Boost Charge
    show_header_toggle: false
    state_color: true
    entities:
      - entity: switch.ev_smart_charger_YOUR_ENTRY_ID_evsc_boost_charge_enabled
        name: Enable Boost
      - entity: number.ev_smart_charger_YOUR_ENTRY_ID_evsc_boost_charge_amperage
        name: Boost Amperage
      - entity: number.ev_smart_charger_YOUR_ENTRY_ID_evsc_boost_target_soc
        name: Boost Target SOC

  - type: entities
    title: Night Smart Charge
    show_header_toggle: false
    state_color: true
    entities:
      - entity: switch.ev_smart_charger_YOUR_ENTRY_ID_evsc_night_smart_charge_enabled
        name: Enable Night Smart Charge
      - entity: time.ev_smart_charger_YOUR_ENTRY_ID_evsc_night_charge_time
        name: Night Charge Start
      - entity: time.ev_smart_charger_YOUR_ENTRY_ID_evsc_car_ready_time
        name: Ready In The Morning Time
      - entity: number.ev_smart_charger_YOUR_ENTRY_ID_evsc_min_solar_forecast_threshold
        name: Min Solar Forecast Threshold
      - entity: number.ev_smart_charger_YOUR_ENTRY_ID_evsc_night_charge_amperage
        name: Night Charge Amperage

  - type: entities
    title: Solar Surplus Studio
    show_header_toggle: false
    entities:
      - entity: number.ev_smart_charger_YOUR_ENTRY_ID_evsc_check_interval
        name: Check Interval
      - entity: number.ev_smart_charger_YOUR_ENTRY_ID_evsc_grid_import_threshold
        name: Grid Import Threshold
      - entity: number.ev_smart_charger_YOUR_ENTRY_ID_evsc_grid_import_delay
        name: Grid Import Delay
      - entity: number.ev_smart_charger_YOUR_ENTRY_ID_evsc_surplus_drop_delay
        name: Surplus Drop Delay
      - entity: number.ev_smart_charger_YOUR_ENTRY_ID_evsc_home_battery_min_soc
        name: Home Battery Min SOC
      - entity: number.ev_smart_charger_YOUR_ENTRY_ID_evsc_battery_support_amperage
        name: Battery Support Amperage

  - type: entities
    title: Notifications & Serviceability
    show_header_toggle: false
    state_color: true
    entities:
      - entity: switch.ev_smart_charger_YOUR_ENTRY_ID_evsc_notify_priority_balancer_enabled
        name: Notify Priority Balancer
      - entity: switch.ev_smart_charger_YOUR_ENTRY_ID_evsc_notify_night_charge_enabled
        name: Notify Night Charge
      - entity: switch.ev_smart_charger_YOUR_ENTRY_ID_evsc_notify_smart_blocker_enabled
        name: Notify Smart Blocker
      - entity: switch.ev_smart_charger_YOUR_ENTRY_ID_evsc_enable_file_logging
        name: File Logging

  - type: custom:mushroom-title-card
    title: Weekly Planner
    subtitle: Each day keeps EV target, Home target, and morning readiness together

  - type: grid
    columns: 2
    square: false
    cards:
      - type: entities
        title: Monday
        show_header_toggle: false
        entities:
          - entity: number.ev_smart_charger_YOUR_ENTRY_ID_evsc_ev_min_soc_monday
            name: EV Target
          - entity: number.ev_smart_charger_YOUR_ENTRY_ID_evsc_home_min_soc_monday
            name: Home Target
          - entity: switch.ev_smart_charger_YOUR_ENTRY_ID_evsc_car_ready_monday
            name: Ready In The Morning
      - type: entities
        title: Tuesday
        show_header_toggle: false
        entities:
          - entity: number.ev_smart_charger_YOUR_ENTRY_ID_evsc_ev_min_soc_tuesday
            name: EV Target
          - entity: number.ev_smart_charger_YOUR_ENTRY_ID_evsc_home_min_soc_tuesday
            name: Home Target
          - entity: switch.ev_smart_charger_YOUR_ENTRY_ID_evsc_car_ready_tuesday
            name: Ready In The Morning
      - type: entities
        title: Wednesday
        show_header_toggle: false
        entities:
          - entity: number.ev_smart_charger_YOUR_ENTRY_ID_evsc_ev_min_soc_wednesday
            name: EV Target
          - entity: number.ev_smart_charger_YOUR_ENTRY_ID_evsc_home_min_soc_wednesday
            name: Home Target
          - entity: switch.ev_smart_charger_YOUR_ENTRY_ID_evsc_car_ready_wednesday
            name: Ready In The Morning
      - type: entities
        title: Thursday
        show_header_toggle: false
        entities:
          - entity: number.ev_smart_charger_YOUR_ENTRY_ID_evsc_ev_min_soc_thursday
            name: EV Target
          - entity: number.ev_smart_charger_YOUR_ENTRY_ID_evsc_home_min_soc_thursday
            name: Home Target
          - entity: switch.ev_smart_charger_YOUR_ENTRY_ID_evsc_car_ready_thursday
            name: Ready In The Morning
      - type: entities
        title: Friday
        show_header_toggle: false
        entities:
          - entity: number.ev_smart_charger_YOUR_ENTRY_ID_evsc_ev_min_soc_friday
            name: EV Target
          - entity: number.ev_smart_charger_YOUR_ENTRY_ID_evsc_home_min_soc_friday
            name: Home Target
          - entity: switch.ev_smart_charger_YOUR_ENTRY_ID_evsc_car_ready_friday
            name: Ready In The Morning
      - type: entities
        title: Saturday
        show_header_toggle: false
        entities:
          - entity: number.ev_smart_charger_YOUR_ENTRY_ID_evsc_ev_min_soc_saturday
            name: EV Target
          - entity: number.ev_smart_charger_YOUR_ENTRY_ID_evsc_home_min_soc_saturday
            name: Home Target
          - entity: switch.ev_smart_charger_YOUR_ENTRY_ID_evsc_car_ready_saturday
            name: Ready In The Morning
      - type: entities
        title: Sunday
        show_header_toggle: false
        entities:
          - entity: number.ev_smart_charger_YOUR_ENTRY_ID_evsc_ev_min_soc_sunday
            name: EV Target
          - entity: number.ev_smart_charger_YOUR_ENTRY_ID_evsc_home_min_soc_sunday
            name: Home Target
          - entity: switch.ev_smart_charger_YOUR_ENTRY_ID_evsc_car_ready_sunday
            name: Ready In The Morning

  - type: entities
    title: Diagnostics
    show_header_toggle: false
    entities:
      - entity: sensor.ev_smart_charger_YOUR_ENTRY_ID_evsc_diagnostic
        name: Core Diagnostic
      - entity: sensor.ev_smart_charger_YOUR_ENTRY_ID_evsc_solar_surplus_diagnostic
        name: Solar Surplus Diagnostic
      - entity: sensor.ev_smart_charger_YOUR_ENTRY_ID_evsc_cached_ev_soc
        name: Cached EV SOC
      - entity: sensor.ev_smart_charger_YOUR_ENTRY_ID_evsc_log_file_path
        name: Log File Path
```

### Mobile-First Full View (Best Option)

The strongest mobile pattern here is **not** one giant page. It is:

1. A compact **home view** for the actions you use every day
2. A **weekly planner subview** for day-by-day preferences
3. A **diagnostics subview** for serviceability and logs

This keeps the first screen fast and visually clean, while still exposing every preference.

#### Main View

```yaml
- title: EV Mobile
  path: ev-mobile
  icon: mdi:car-electric
  type: sidebar
  cards:
    - type: custom:mushroom-template-card
      primary: Tesla Charge Deck
      secondary: >
        Priority {{ states('sensor.ev_smart_charger_YOUR_ENTRY_ID_evsc_priority_daily_state') }}
        • Profile {{ states('select.ev_smart_charger_YOUR_ENTRY_ID_evsc_charging_profile') }}
        • EV {{ states('sensor.ev_smart_charger_YOUR_ENTRY_ID_evsc_today_ev_target') }}
        • Home {{ states('sensor.ev_smart_charger_YOUR_ENTRY_ID_evsc_today_home_target') }}
      icon: mdi:ev-station
      icon_color: teal
      multiline_secondary: true
      fill_container: true

    - type: custom:mushroom-chips-card
      alignment: justify
      chips:
        - type: entity
          entity: sensor.ev_smart_charger_YOUR_ENTRY_ID_evsc_priority_daily_state
          icon_color: teal
        - type: entity
          entity: sensor.ev_smart_charger_YOUR_ENTRY_ID_evsc_today_ev_target
          icon_color: amber
        - type: entity
          entity: sensor.ev_smart_charger_YOUR_ENTRY_ID_evsc_today_home_target
          icon_color: green
        - type: entity
          entity: sensor.ev_smart_charger_YOUR_ENTRY_ID_evsc_cached_ev_soc
          icon_color: blue

    - type: grid
      columns: 2
      square: false
      cards:
        - type: custom:mushroom-entity-card
          entity: switch.ev_smart_charger_YOUR_ENTRY_ID_evsc_forza_ricarica
          name: Forza Ricarica
          icon_color: red
          secondary_info: state
          fill_container: true
        - type: custom:mushroom-select-card
          entity: select.ev_smart_charger_YOUR_ENTRY_ID_evsc_charging_profile
          name: Charging Profile
          fill_container: true
        - type: custom:mushroom-entity-card
          entity: switch.ev_smart_charger_YOUR_ENTRY_ID_evsc_boost_charge_enabled
          name: Boost
          icon_color: amber
          secondary_info: state
          fill_container: true
        - type: custom:mushroom-entity-card
          entity: switch.ev_smart_charger_YOUR_ENTRY_ID_evsc_night_smart_charge_enabled
          name: Night Smart Charge
          icon_color: indigo
          secondary_info: state
          fill_container: true
        - type: custom:mushroom-entity-card
          entity: switch.ev_smart_charger_YOUR_ENTRY_ID_evsc_priority_balancer_enabled
          name: Priority Balancer
          icon_color: teal
          secondary_info: state
          fill_container: true
        - type: custom:mushroom-entity-card
          entity: switch.ev_smart_charger_YOUR_ENTRY_ID_evsc_use_home_battery
          name: Battery Support
          icon_color: green
          secondary_info: state
          fill_container: true

    - type: entities
      title: Daily Controls
      show_header_toggle: false
      entities:
        - entity: number.ev_smart_charger_YOUR_ENTRY_ID_evsc_boost_charge_amperage
          name: Boost Amperage
        - entity: number.ev_smart_charger_YOUR_ENTRY_ID_evsc_boost_target_soc
          name: Boost Target SOC
        - entity: time.ev_smart_charger_YOUR_ENTRY_ID_evsc_night_charge_time
          name: Night Charge Start
        - entity: time.ev_smart_charger_YOUR_ENTRY_ID_evsc_car_ready_time
          name: Ready In The Morning Time
        - entity: number.ev_smart_charger_YOUR_ENTRY_ID_evsc_night_charge_amperage
          name: Night Charge Amperage
        - entity: number.ev_smart_charger_YOUR_ENTRY_ID_evsc_min_solar_forecast_threshold
          name: Min Solar Forecast Threshold

    - type: grid
      columns: 2
      square: false
      cards:
        - type: custom:mushroom-template-card
          primary: Weekly Planner
          secondary: Open day-by-day EV, Home, and Ready settings
          icon: mdi:calendar-week
          icon_color: amber
          fill_container: true
          tap_action:
            action: navigate
            navigation_path: /lovelace/ev-planner
        - type: custom:mushroom-template-card
          primary: Diagnostics
          secondary: Open logs, diagnostics, notifications, and service tools
          icon: mdi:stethoscope
          icon_color: blue
          fill_container: true
          tap_action:
            action: navigate
            navigation_path: /lovelace/ev-diagnostics

    - type: entities
      title: Quick Diagnostics
      show_header_toggle: false
      entities:
        - entity: sensor.ev_smart_charger_YOUR_ENTRY_ID_evsc_diagnostic
          name: Core Diagnostic
        - entity: sensor.ev_smart_charger_YOUR_ENTRY_ID_evsc_solar_surplus_diagnostic
          name: Solar Surplus Diagnostic
      view_layout:
        position: sidebar
```

#### Weekly Planner Subview

```yaml
- title: EV Planner
  path: ev-planner
  subview: true
  back_path: /lovelace/ev-mobile
  cards:
    - type: custom:mushroom-title-card
      title: Weekly Planner
      subtitle: Each day groups EV target, Home target, and morning readiness

    - type: entities
      title: Monday
      show_header_toggle: false
      entities:
        - entity: number.ev_smart_charger_YOUR_ENTRY_ID_evsc_ev_min_soc_monday
          name: EV Target
        - entity: number.ev_smart_charger_YOUR_ENTRY_ID_evsc_home_min_soc_monday
          name: Home Target
        - entity: switch.ev_smart_charger_YOUR_ENTRY_ID_evsc_car_ready_monday
          name: Ready In The Morning

    - type: entities
      title: Tuesday
      show_header_toggle: false
      entities:
        - entity: number.ev_smart_charger_YOUR_ENTRY_ID_evsc_ev_min_soc_tuesday
          name: EV Target
        - entity: number.ev_smart_charger_YOUR_ENTRY_ID_evsc_home_min_soc_tuesday
          name: Home Target
        - entity: switch.ev_smart_charger_YOUR_ENTRY_ID_evsc_car_ready_tuesday
          name: Ready In The Morning

    - type: entities
      title: Wednesday
      show_header_toggle: false
      entities:
        - entity: number.ev_smart_charger_YOUR_ENTRY_ID_evsc_ev_min_soc_wednesday
          name: EV Target
        - entity: number.ev_smart_charger_YOUR_ENTRY_ID_evsc_home_min_soc_wednesday
          name: Home Target
        - entity: switch.ev_smart_charger_YOUR_ENTRY_ID_evsc_car_ready_wednesday
          name: Ready In The Morning

    - type: entities
      title: Thursday
      show_header_toggle: false
      entities:
        - entity: number.ev_smart_charger_YOUR_ENTRY_ID_evsc_ev_min_soc_thursday
          name: EV Target
        - entity: number.ev_smart_charger_YOUR_ENTRY_ID_evsc_home_min_soc_thursday
          name: Home Target
        - entity: switch.ev_smart_charger_YOUR_ENTRY_ID_evsc_car_ready_thursday
          name: Ready In The Morning

    - type: entities
      title: Friday
      show_header_toggle: false
      entities:
        - entity: number.ev_smart_charger_YOUR_ENTRY_ID_evsc_ev_min_soc_friday
          name: EV Target
        - entity: number.ev_smart_charger_YOUR_ENTRY_ID_evsc_home_min_soc_friday
          name: Home Target
        - entity: switch.ev_smart_charger_YOUR_ENTRY_ID_evsc_car_ready_friday
          name: Ready In The Morning

    - type: entities
      title: Saturday
      show_header_toggle: false
      entities:
        - entity: number.ev_smart_charger_YOUR_ENTRY_ID_evsc_ev_min_soc_saturday
          name: EV Target
        - entity: number.ev_smart_charger_YOUR_ENTRY_ID_evsc_home_min_soc_saturday
          name: Home Target
        - entity: switch.ev_smart_charger_YOUR_ENTRY_ID_evsc_car_ready_saturday
          name: Ready In The Morning

    - type: entities
      title: Sunday
      show_header_toggle: false
      entities:
        - entity: number.ev_smart_charger_YOUR_ENTRY_ID_evsc_ev_min_soc_sunday
          name: EV Target
        - entity: number.ev_smart_charger_YOUR_ENTRY_ID_evsc_home_min_soc_sunday
          name: Home Target
        - entity: switch.ev_smart_charger_YOUR_ENTRY_ID_evsc_car_ready_sunday
          name: Ready In The Morning
```

#### Diagnostics Subview

```yaml
- title: EV Diagnostics
  path: ev-diagnostics
  subview: true
  back_path: /lovelace/ev-mobile
  cards:
    - type: custom:mushroom-title-card
      title: Diagnostics & Serviceability
      subtitle: Deep settings, logs, notifications, and solar tuning

    - type: entities
      title: Solar Surplus Studio
      show_header_toggle: false
      entities:
        - entity: number.ev_smart_charger_YOUR_ENTRY_ID_evsc_check_interval
          name: Check Interval
        - entity: number.ev_smart_charger_YOUR_ENTRY_ID_evsc_grid_import_threshold
          name: Grid Import Threshold
        - entity: number.ev_smart_charger_YOUR_ENTRY_ID_evsc_grid_import_delay
          name: Grid Import Delay
        - entity: number.ev_smart_charger_YOUR_ENTRY_ID_evsc_surplus_drop_delay
          name: Surplus Drop Delay
        - entity: number.ev_smart_charger_YOUR_ENTRY_ID_evsc_home_battery_min_soc
          name: Home Battery Min SOC
        - entity: number.ev_smart_charger_YOUR_ENTRY_ID_evsc_battery_support_amperage
          name: Battery Support Amperage

    - type: entities
      title: Notifications & Logging
      show_header_toggle: false
      entities:
        - entity: switch.ev_smart_charger_YOUR_ENTRY_ID_evsc_notify_priority_balancer_enabled
          name: Notify Priority Balancer
        - entity: switch.ev_smart_charger_YOUR_ENTRY_ID_evsc_notify_night_charge_enabled
          name: Notify Night Charge
        - entity: switch.ev_smart_charger_YOUR_ENTRY_ID_evsc_notify_smart_blocker_enabled
          name: Notify Smart Blocker
        - entity: switch.ev_smart_charger_YOUR_ENTRY_ID_evsc_enable_file_logging
          name: File Logging

    - type: entities
      title: Diagnostic Sensors
      show_header_toggle: false
      entities:
        - entity: sensor.ev_smart_charger_YOUR_ENTRY_ID_evsc_diagnostic
          name: Core Diagnostic
        - entity: sensor.ev_smart_charger_YOUR_ENTRY_ID_evsc_solar_surplus_diagnostic
          name: Solar Surplus Diagnostic
        - entity: sensor.ev_smart_charger_YOUR_ENTRY_ID_evsc_cached_ev_soc
          name: Cached EV SOC
        - entity: sensor.ev_smart_charger_YOUR_ENTRY_ID_evsc_log_file_path
          name: Log File Path
```

### Vertical Stack Custom Dashboard

This integration now ships a bundled frontend module for a custom Lovelace dashboard card with animated HTML/CSS UI, but the layout is intentionally a strict vertical stack instead of a wide pannable surface.

1. Add the resource:

```yaml
lovelace:
  resources:
    - url: /api/ev_smart_charger/frontend/ev-smart-charger-dashboard.js
      type: module
```

2. Add the card inside a standard `vertical-stack`:

```yaml
type: vertical-stack
cards:
  - type: custom:ev-smart-charger-dashboard
    title: Tesla Charge Deck
    entity_prefix: ev_smart_charger_YOUR_ENTRY_ID
    charging_power_entity: sensor.current_charging_power_tesla
    ev_soc_entity: sensor.tesla_battery
    home_battery_soc_entity: sensor.stato_batteria_luxpower
    solar_power_entity: sensor.produzione_solare_totale
    grid_import_entity: sensor.grid_power_import_w
    current_entity: number.wallbox_current
```

The custom card exposes the integration helpers with a single animated control surface:

- stacked telemetry cards in one column
- native toggles for override, boost, night charge, solar surplus, and blockers
- stepper controls for number entities
- selectable charging profile chips
- direct Home Assistant service calls from the UI

Recommended placement:

- use it as a normal card in a standard dashboard view
- keep it in one column or inside `vertical-stack`
- avoid panel-style layouts if you want a phone-like stacked view with no horizontal panning

### Complete Control Dashboard

Copy this YAML to your dashboard for a full control center that exposes every configurable preference plus the core diagnostics:

```yaml
type: vertical-stack
cards:
  - type: markdown
    content: |
      # EV Smart Charger
      A premium control wall for every EV Smart Charger preference: overrides, solar tuning, weekly planning, night logic, notifications, and diagnostics.

  - type: grid
    title: Command Center
    columns: 3
    square: false
    cards:
      - type: tile
        entity: switch.ev_smart_charger_YOUR_ENTRY_ID_evsc_forza_ricarica
        name: Forza Ricarica
        icon: mdi:flash-alert
        color: red
        vertical: true
      - type: tile
        entity: select.ev_smart_charger_YOUR_ENTRY_ID_evsc_charging_profile
        name: Charging Profile
        icon: mdi:ev-station
        vertical: true
      - type: tile
        entity: sensor.ev_smart_charger_YOUR_ENTRY_ID_evsc_priority_daily_state
        name: Priority State
        icon: mdi:scale-balance
        vertical: true
      - type: tile
        entity: sensor.ev_smart_charger_YOUR_ENTRY_ID_evsc_today_ev_target
        name: Today EV Target
        icon: mdi:car-electric
        vertical: true
      - type: tile
        entity: sensor.ev_smart_charger_YOUR_ENTRY_ID_evsc_today_home_target
        name: Today Home Target
        icon: mdi:home-battery
        vertical: true
      - type: tile
        entity: sensor.ev_smart_charger_YOUR_ENTRY_ID_evsc_solar_surplus_diagnostic
        name: Solar Diagnostic
        icon: mdi:solar-power-variant
        vertical: true
      - type: tile
        entity: sensor.ev_smart_charger_YOUR_ENTRY_ID_evsc_diagnostic
        name: Core Diagnostic
        icon: mdi:information-outline
        vertical: true

  - type: grid
    title: High Priority Controls
    columns: 2
    square: false
    cards:
      - type: entities
        title: Boost Charge
        show_header_toggle: false
        entities:
          - entity: switch.ev_smart_charger_YOUR_ENTRY_ID_evsc_boost_charge_enabled
            name: Boost Session
          - entity: number.ev_smart_charger_YOUR_ENTRY_ID_evsc_boost_charge_amperage
            name: Boost Amperage
          - entity: number.ev_smart_charger_YOUR_ENTRY_ID_evsc_boost_target_soc
            name: Boost Target SOC
      - type: entities
        title: Night Smart Charge
        show_header_toggle: false
        entities:
          - entity: switch.ev_smart_charger_YOUR_ENTRY_ID_evsc_night_smart_charge_enabled
            name: Enable Night Smart Charge
          - entity: time.ev_smart_charger_YOUR_ENTRY_ID_evsc_night_charge_time
            name: Start Time
          - entity: time.ev_smart_charger_YOUR_ENTRY_ID_evsc_car_ready_time
            name: Ready In The Morning Time
          - entity: number.ev_smart_charger_YOUR_ENTRY_ID_evsc_min_solar_forecast_threshold
            name: Min Solar Forecast
          - entity: number.ev_smart_charger_YOUR_ENTRY_ID_evsc_night_charge_amperage
            name: Night Charge Amperage

  - type: grid
    title: Automation Matrix
    columns: 2
    square: false
    cards:
      - type: entities
        title: Automation Toggles
        show_header_toggle: false
        entities:
          - entity: switch.ev_smart_charger_YOUR_ENTRY_ID_evsc_priority_balancer_enabled
            name: Priority Balancer
          - entity: switch.ev_smart_charger_YOUR_ENTRY_ID_evsc_night_smart_charge_enabled
            name: Night Smart Charge
          - entity: switch.ev_smart_charger_YOUR_ENTRY_ID_evsc_smart_charger_blocker_enabled
            name: Smart Charger Blocker
          - entity: switch.ev_smart_charger_YOUR_ENTRY_ID_evsc_use_home_battery
            name: Use Home Battery
          - entity: switch.ev_smart_charger_YOUR_ENTRY_ID_evsc_enable_file_logging
            name: File Logging
      - type: entities
        title: Notification Toggles
        show_header_toggle: false
        entities:
          - entity: switch.ev_smart_charger_YOUR_ENTRY_ID_evsc_notify_priority_balancer_enabled
            name: Notify Priority Balancer
          - entity: switch.ev_smart_charger_YOUR_ENTRY_ID_evsc_notify_night_charge_enabled
            name: Notify Night Charge
          - entity: switch.ev_smart_charger_YOUR_ENTRY_ID_evsc_notify_smart_blocker_enabled
            name: Notify Smart Blocker

  - type: grid
    title: Solar Surplus Studio
    columns: 2
    square: false
    cards:
      - type: entities
        title: Response & Protection
        show_header_toggle: false
        entities:
          - entity: number.ev_smart_charger_YOUR_ENTRY_ID_evsc_check_interval
            name: Check Interval
          - entity: number.ev_smart_charger_YOUR_ENTRY_ID_evsc_grid_import_threshold
            name: Grid Import Threshold
          - entity: number.ev_smart_charger_YOUR_ENTRY_ID_evsc_grid_import_delay
            name: Grid Import Delay
          - entity: number.ev_smart_charger_YOUR_ENTRY_ID_evsc_surplus_drop_delay
            name: Surplus Drop Delay
      - type: entities
        title: Battery Support
        show_header_toggle: false
        entities:
          - entity: switch.ev_smart_charger_YOUR_ENTRY_ID_evsc_use_home_battery
            name: Enable Battery Support
          - entity: number.ev_smart_charger_YOUR_ENTRY_ID_evsc_home_battery_min_soc
            name: Home Battery Min SOC
          - entity: number.ev_smart_charger_YOUR_ENTRY_ID_evsc_battery_support_amperage
            name: Battery Support Amperage

  - type: grid
    title: Weekly Charging Planner
    columns: 2
    square: false
    cards:
      - type: entities
        title: EV Daily Targets
        show_header_toggle: false
        entities:
          - entity: number.ev_smart_charger_YOUR_ENTRY_ID_evsc_ev_min_soc_monday
            name: Monday
          - entity: number.ev_smart_charger_YOUR_ENTRY_ID_evsc_ev_min_soc_tuesday
            name: Tuesday
          - entity: number.ev_smart_charger_YOUR_ENTRY_ID_evsc_ev_min_soc_wednesday
            name: Wednesday
          - entity: number.ev_smart_charger_YOUR_ENTRY_ID_evsc_ev_min_soc_thursday
            name: Thursday
          - entity: number.ev_smart_charger_YOUR_ENTRY_ID_evsc_ev_min_soc_friday
            name: Friday
          - entity: number.ev_smart_charger_YOUR_ENTRY_ID_evsc_ev_min_soc_saturday
            name: Saturday
          - entity: number.ev_smart_charger_YOUR_ENTRY_ID_evsc_ev_min_soc_sunday
            name: Sunday
      - type: entities
        title: Home Battery Daily Targets
        show_header_toggle: false
        entities:
          - entity: number.ev_smart_charger_YOUR_ENTRY_ID_evsc_home_min_soc_monday
            name: Monday
          - entity: number.ev_smart_charger_YOUR_ENTRY_ID_evsc_home_min_soc_tuesday
            name: Tuesday
          - entity: number.ev_smart_charger_YOUR_ENTRY_ID_evsc_home_min_soc_wednesday
            name: Wednesday
          - entity: number.ev_smart_charger_YOUR_ENTRY_ID_evsc_home_min_soc_thursday
            name: Thursday
          - entity: number.ev_smart_charger_YOUR_ENTRY_ID_evsc_home_min_soc_friday
            name: Friday
          - entity: number.ev_smart_charger_YOUR_ENTRY_ID_evsc_home_min_soc_saturday
            name: Saturday
          - entity: number.ev_smart_charger_YOUR_ENTRY_ID_evsc_home_min_soc_sunday
            name: Sunday

  - type: grid
    title: Departure Planner
    columns: 2
    square: false
    cards:
      - type: entities
        title: Morning Deadline
        show_header_toggle: false
        entities:
          - entity: time.ev_smart_charger_YOUR_ENTRY_ID_evsc_car_ready_time
            name: Departure Deadline
          - entity: time.ev_smart_charger_YOUR_ENTRY_ID_evsc_night_charge_time
            name: Night Charge Start
      - type: entities
        title: Ready In The Morning Flags
        show_header_toggle: false
        entities:
          - entity: switch.ev_smart_charger_YOUR_ENTRY_ID_evsc_car_ready_monday
            name: Monday Ready
          - entity: switch.ev_smart_charger_YOUR_ENTRY_ID_evsc_car_ready_tuesday
            name: Tuesday Ready
          - entity: switch.ev_smart_charger_YOUR_ENTRY_ID_evsc_car_ready_wednesday
            name: Wednesday Ready
          - entity: switch.ev_smart_charger_YOUR_ENTRY_ID_evsc_car_ready_thursday
            name: Thursday Ready
          - entity: switch.ev_smart_charger_YOUR_ENTRY_ID_evsc_car_ready_friday
            name: Friday Ready
          - entity: switch.ev_smart_charger_YOUR_ENTRY_ID_evsc_car_ready_saturday
            name: Saturday Ready
          - entity: switch.ev_smart_charger_YOUR_ENTRY_ID_evsc_car_ready_sunday
            name: Sunday Ready

  - type: grid
    title: Diagnostics & Serviceability
    columns: 2
    square: false
    cards:
      - type: entities
        title: Runtime Diagnostics
        show_header_toggle: false
        entities:
          - entity: sensor.ev_smart_charger_YOUR_ENTRY_ID_evsc_diagnostic
            name: Core Diagnostic
          - entity: sensor.ev_smart_charger_YOUR_ENTRY_ID_evsc_priority_daily_state
            name: Priority State
          - entity: sensor.ev_smart_charger_YOUR_ENTRY_ID_evsc_solar_surplus_diagnostic
            name: Solar Surplus Diagnostic
          - entity: sensor.ev_smart_charger_YOUR_ENTRY_ID_evsc_cached_ev_soc
            name: Cached EV SOC
      - type: entities
        title: Logging & Targets
        show_header_toggle: false
        entities:
          - entity: sensor.ev_smart_charger_YOUR_ENTRY_ID_evsc_today_ev_target
            name: Today EV Target
          - entity: sensor.ev_smart_charger_YOUR_ENTRY_ID_evsc_today_home_target
            name: Today Home Target
          - entity: sensor.ev_smart_charger_YOUR_ENTRY_ID_evsc_log_file_path
            name: Log File Path
```

### Setup Instructions

`Boost Charge` is independent from `Forza Ricarica`: the boost stops automatically at the configured SOC target, while `Forza Ricarica` remains a manual continuous override.

1. **Find Your Entry ID:**
   - Go to **Developer Tools → States**
   - Search for "evsc"
   - Example entity: `switch.ev_smart_charger_abc123_evsc_forza_ricarica`
   - Your entry ID: `abc123` (between `ev_smart_charger_` and `_evsc`)

2. **Replace in YAML:**
   - Find & Replace: `YOUR_ENTRY_ID` → `abc123`

3. **Add to Dashboard:**
   - Edit Dashboard → Add Card → Manual
   - Paste YAML
   - Save

**Full YAML with all entities:** See [README (Usage section)](https://github.com/antbald/ha-ev-smart-charger#usage)

---

## 🔍 Troubleshooting

### Integration Won't Start

**Check logs:**
- Settings → System → Logs
- Search for "evsc"

**Common issues:**
1. **Helper entities not created**
   - Wait 2 seconds after restart
   - Check: Developer Tools → States → search "evsc"
   - Should see 51 entities

2. **Entity mappings incorrect**
   - Settings → Devices & Services → EV Smart Charger → Configure
   - Verify all entity IDs are correct

3. **Charger status sensor wrong**
   - Must report: `charger_charging`, `charger_free`, `charger_end`, or `charger_wait`
   - Check current value in Developer Tools → States

### Charging Not Starting

**Solar Surplus Mode:**
1. Check **Charging Profile** = `solar_surplus`
2. Check **Forza Ricarica** = OFF
3. Check charger status ≠ `charger_free` (car connected)
4. Check solar surplus ≥ 1380W (6A minimum)
5. Check Priority Balancer state:
   - If `Home` → EV won't charge (home battery priority)
   - If `EV` or `EV_Free` → Should charge with surplus

**Night Smart Charge:**
1. Check **Night Charge Enabled** = ON
2. Check current time ≥ configured time
3. Check PV forecast sensor available
4. Check EV SOC < today's target
5. Check home battery SOC (if battery mode)
6. If battery mode hits home battery min:
   - `car_ready=ON` → fallback to GRID (session continues)
   - `car_ready=OFF` → terminal stop (`completed_today`)

**Expected diagnostic patterns in logs:**
- Transition case: `Home battery threshold reached` + `switching to GRID fallback` + `Grid charge mode`
- Terminal case: `Session state: completed_today`
- Sunset transition: `Sunset transition` + `Handover accepted` or safe stop fallback
- Target cap: `Target hard cap enforced`
- Stale SOC policy: `SOC stale (continue)` + decision continues by policy
- No duplicate lines for the same event when file logging is enabled

### Cloud Sensor Issues (v1.4.0)

**Symptoms:**
- Priority Balancer using default values
- Night Charge skipping without reason
- "Unknown" SOC in logs

**Solution:**
✅ v1.4.0 automatically fixes this with cache layer!

**Verify cache working:**
1. Check sensor exists: `sensor.evsc_cached_ev_soc`
2. Check logs for: "✅ Using cached EV SOC sensor"
3. Check cache attributes:
   - `is_cached`: Should be `false` when cloud working
   - `last_valid_update`: Should update every 5 seconds

**If cloud sensor down:**
- Cache maintains last valid value
- Warning log once: "⚠️ Using cached EV SOC: X% (source unavailable)"
- System continues working normally
- If EV SOC age becomes old, diagnostics log `SOC stale (continue)` (policy: no auto-stop)

### Enable Debug Logging

Add to `configuration.yaml`:

```yaml
logger:
  default: info
  logs:
    custom_components.ev_smart_charger: debug
```

Restart Home Assistant, then check logs.

### Common Questions

**Q: Why isn't Solar Surplus starting charging?**
A: Check Priority Balancer state. If `Home`, it won't charge EV until home battery target met.

**Q: How do I disable all automations temporarily?**
A: Turn ON `switch.evsc_forza_ricarica` (global override).

**Q: Can I change daily targets while integration is running?**
A: Yes! Changes take effect at next check interval (default 1 minute).

**Q: Why did Night Charge skip charging?**
A: Check logs. Common reasons:
- EV already at target
- Home battery below threshold (check car_ready flag)
- PV forecast sensor unavailable
- Session already completed for terminal reason (`completed_today`)

**Q: How do I test the integration without my car?**
A: Set **Charging Profile** to `manual` and use charger's native controls.

### Need More Help?

- 📖 **Full Troubleshooting Guide:** [TROUBLESHOOTING.md](TROUBLESHOOTING.md)
- 🐛 **Report Issues:** [GitHub Issues](https://github.com/antbald/ha-ev-smart-charger/issues)
- 💬 **Discussions:** [GitHub Discussions](https://github.com/antbald/ha-ev-smart-charger/discussions)

---

## 📚 Version History

### Latest: v1.4.0 (2025-11-14) - Cloud Sensor Reliability Layer

**🎯 Major Feature: Automatic Cache for Unreliable Cloud Sensors**

**Problem Solved:**
Cloud-based car integrations (Tesla, BMW, VW) frequently show "unknown"/"unavailable" states, causing calculation failures and incorrect charging decisions.

**Solution:**
New monitoring service polls cloud sensor every 5 seconds and maintains reliable cached value during outages. All components now use cached sensor automatically.

**New Components:**
- **EV SOC Monitor** - 5-second polling service
- **Cached EV SOC Sensor** - Reliable cache with state persistence
- **Automatic fallback** - Uses direct cloud sensor if cache unavailable

**Architecture:**
```
Cloud Sensor (unreliable) → Monitor (5s) → Cache (reliable) → Components
```

**Benefits:**
✅ No more calculation failures from cloud sensors
✅ Priority Balancer always has valid SOC
✅ Night Charge no longer skips due to "unknown"
✅ Zero configuration - automatic after restart

**Files Changed:**
- NEW: `ev_soc_monitor.py` (172 lines)
- Modified: `sensor.py`, `priority_balancer.py`, `__init__.py`, `night_smart_charge.py`
- Updated: `const.py`, `manifest.json`

**Upgrade:** 🟢 RECOMMENDED - Significantly improves reliability for cloud-based car integrations

---

### Recent Updates

#### v1.3.26 (2025-11-11) - Today's Target Sensors
- NEW: `sensor.evsc_today_ev_target` - Shows today's EV SOC target
- NEW: `sensor.evsc_today_home_target` - Shows today's home battery SOC target
- Dashboard integration: Easy dashboard cards showing daily targets

#### v1.3.25 (2025-11-12) - Toggle-Controlled File Logging
- NEW: `switch.evsc_enable_file_logging` - Toggle file logging on/off
- NEW: `sensor.evsc_log_file_path` - Shows log file path
- Daily log files under `logs/<year>/<month>/<day>.log`
- Single global file handler (no duplicate log lines across components)
- Easy troubleshooting and log sharing

#### v1.3.24 (2025-11-12) - Solar Surplus PRIORITY_EV_FREE Fix
- CRITICAL: Fixed infinite charging from home battery when both targets met
- Solar Surplus now stops immediately in PRIORITY_EV_FREE mode
- Prevents home battery over-discharge

#### v1.3.23 (2025-11-12) - Dynamic Amperage Recovery
- Night Smart Charge now has grid import protection
- Automatic amperage recovery when conditions improve
- Shared utilities with Solar Surplus (code deduplication)

#### v1.3.22 (2025-11-12) - Critical State Restoration Fix
- CRITICAL: Fixed number entities showing "unavailable" after restart
- Priority Balancer now reads configured targets correctly
- Night Smart Charge activates reliably after HA restart

### Full Changelog

**See [CHANGELOG.md](CHANGELOG.md) for complete version history**

---

## 📄 License

MIT License - See [LICENSE](LICENSE) file for details.

---

## 🤝 Contributing

Contributions are welcome! Please:

1. **Fork the repository**
2. **Create a feature branch** (`git checkout -b feature/amazing-feature`)
3. **Commit your changes** (`git commit -m 'Add amazing feature'`)
4. **Push to the branch** (`git push origin feature/amazing-feature`)
5. **Open a Pull Request**

### Development Guidelines

- Follow Home Assistant coding standards
- Add tests for new features
- Update documentation
- Test with Home Assistant 2024.4+

---

## 🙏 Credits

Developed with ❤️ using [Claude Code](https://claude.com/claude-code)

**Special Thanks:**
- Home Assistant community
- All contributors and testers
- Users providing feedback and bug reports

---

## 🔗 Links

- **GitHub Repository:** [antbald/ha-ev-smart-charger](https://github.com/antbald/ha-ev-smart-charger)
- **Issue Tracker:** [GitHub Issues](https://github.com/antbald/ha-ev-smart-charger/issues)
- **Discussions:** [GitHub Discussions](https://github.com/antbald/ha-ev-smart-charger/discussions)
- **Latest Release:** [GitHub Releases](https://github.com/antbald/ha-ev-smart-charger/releases)
- **HACS:** Add as custom repository

---

**Made with 🔋 for the Home Assistant community**

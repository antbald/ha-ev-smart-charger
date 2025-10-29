# EV Smart Charger

A Home Assistant integration for intelligent EV charging control based on solar production, time of day, and battery levels.

## Current Version: 0.9.11

[![GitHub Release](https://img.shields.io/github/v/release/antbald/ha-ev-smart-charger)](https://github.com/antbald/ha-ev-smart-charger/releases)
[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/custom-components/hacs)

---

## Features

### ⚡ Charging Profiles (v0.6.0+)

Choose from multiple intelligent charging modes via the **Charging Profile** selector:

#### 1. Manual Mode
Standard charging without automation - full manual control.

#### 2. Solar Surplus Mode ☀️ (v0.6.0+, Enhanced in v0.7.0)
**Charge your EV using only excess solar energy - never import from the grid!**

**How it works:**
- Calculates available surplus: `Solar Production - Home Consumption`
- Automatically adjusts charging amperage based on available surplus
- Uses European 230V standard to convert watts to amps
- Adjusts every X minutes (configurable, default: 1 minute)
- **Grid Import Protection:** Monitors grid import and reduces charging if importing power
- Always starts with minimum 6A when surplus is available

**🆕 v0.7.0 Enhancements:**

**1. Smooth Charge-Speed Reduction**
- Gradual step-down instead of instant drops (e.g., 20A → 16A → 13A → 10A)
- Reduces stress on charger and solar inverter
- Prevents oscillations in the charging cycle
- Each step follows safe sequence: stop → wait 5s → set → wait 1s → start
- Next check interval determines if further reduction is needed

**2. Fluctuation Management (Solar Swing Protection)**
- **Grid Import Delay:** Only reacts to grid import after it stays above threshold for configured delay (default: 30s)
- **Surplus Drop Delay:** Waits for configured delay (default: 30s) before reducing speed when surplus drops
- Both delays are user-configurable (0-120 seconds in 5s steps)
- Prevents overreaction to temporary cloud cover or brief consumption spikes
- Reduces unnecessary charge speed changes and system stress

**3. Home Battery Support**
- **NEW:** Optional feature to use home battery energy when surplus drops
- Enable via `switch.evsc_use_home_battery`
- Configure minimum battery SoC threshold (default: 20%)
- When enabled and battery SoC > minimum:
  - Sets fixed 16A charging speed
  - Allows home battery to bridge the gap and support EV charging
  - Prevents charging speed reduction during temporary surplus drops
- Example: Charging at 20A but surplus drops → if battery available, charge at 16A instead of stopping

**Smart Amperage Adjustment:**
- **Increasing:** Instant adjustment when more surplus is available
- **Decreasing:** Gradual one-step-at-a-time reduction with delays (v0.7.0)
- **Battery Mode:** Fixed 16A when home battery can help (v0.7.0)

**Available Amperage Steps:** 6A, 8A, 10A, 13A, 16A, 20A, 24A, 32A

**Controls:**
- `select.evsc_charging_profile` - Choose charging mode
- `number.evsc_check_interval` - How often to recalculate (1-60 minutes)
- `number.evsc_grid_import_threshold` - Max grid import before reducing charge (W)
- `number.evsc_grid_import_delay` - *(v0.7.0)* Delay before reacting to grid import (0-120s)
- `number.evsc_surplus_drop_delay` - *(v0.7.0)* Delay before reducing on surplus drop (0-120s)
- `switch.evsc_use_home_battery` - *(v0.7.0)* Enable home battery support mode
- `number.evsc_home_battery_min_soc` - *(v0.7.0)* Minimum home battery SoC to allow support (0-100%)

**Requirements:**
- Charger must be in status: `charger_charging`, `charger_end`, or `charger_wait`
- Does NOT activate when charger status is `charger_free` (not connected)

**4. Priority Daily Charging Balancer** *(v0.8.0+)*
- **NEW:** Intelligent prioritization between EV and home battery charging
- Decides which device charges first based on daily minimum SOC targets
- Enable via `switch.evsc_priority_balancer_enabled`
- Configure daily EV SOC targets for each day of week (Monday-Sunday)
- Uses existing home battery minimum SOC as daily target for all days
- Only active when Solar Surplus mode is enabled

**How Priority Balancer Works:**

The system calculates priority at every check interval:

1. **Priority = EV**: EV charges first until reaching today's target SOC
   - All solar surplus goes to EV
   - Home battery charging is deferred
   - Normal solar surplus algorithm applies to EV

2. **Priority = Home**: Home battery charges first until reaching target SOC
   - EV charging is **STOPPED** completely
   - All solar surplus goes to home battery
   - EV resumes automatically when home battery target is met

3. **Priority = EV_Free**: Both devices have met their daily targets
   - Opportunistic EV charging from surplus
   - Home battery already satisfied
   - Normal solar surplus algorithm applies

**Fallback Safety Mechanisms:**
- If EV SOC sensor unavailable/invalid → defaults to Priority = EV
- If Home SOC sensor unavailable/invalid → defaults to Priority = EV
- If SOC values out of range (< 0 or > 100) → defaults to Priority = EV
- Ensures charging never gets blocked due to sensor issues
- When in doubt, system always prioritizes EV charging

**Configuration:**
- 7 number helpers for EV daily targets: `number.evsc_ev_min_soc_[monday...sunday]`
- Reuses existing: `number.evsc_home_battery_min_soc` (applies to all days)
- Priority state visible in: `sensor.evsc_priority_daily_state`
- Sensor attributes include current/target SOCs, reason, and day of week

**Interaction with Battery Support (v0.7.0):**
- Both features can work together independently
- Battery Support only activates when Priority = EV or EV_Free
- When Priority = Home, Battery Support is ignored
- Allows battery to help EV charging at 16A when appropriate priority

**Example Scenarios:**
- **Monday, EV 40%, Target 50%** → Priority = EV (EV charges first)
- **Tuesday, EV 60%, Home 15%, Targets 50%/20%** → Priority = Home (EV stops, home charges)
- **Wednesday, EV 55%, Home 25%, Targets 50%/20%** → Priority = EV_Free (both met, opportunistic EV charging)
- **Thursday, EV SOC unavailable** → Priority = EV (safe fallback, charging continues)

**Controls:**
- `select.evsc_charging_profile` - Choose charging mode
- `number.evsc_check_interval` - How often to recalculate (1-60 minutes)
- `number.evsc_grid_import_threshold` - Max grid import before reducing charge (W)
- `number.evsc_grid_import_delay` - *(v0.7.0)* Delay before reacting to grid import (0-120s)
- `number.evsc_surplus_drop_delay` - *(v0.7.0)* Delay before reducing on surplus drop (0-120s)
- `switch.evsc_use_home_battery` - *(v0.7.0)* Enable home battery support mode
- `number.evsc_home_battery_min_soc` - *(v0.7.0)* Minimum home battery SoC to allow support (0-100%)
- `switch.evsc_priority_balancer_enabled` - *(v0.8.0)* Enable priority-based charging balancer
- `number.evsc_ev_min_soc_[day]` - *(v0.8.0)* Daily EV SOC targets (7 helpers, Monday-Sunday)
- `sensor.evsc_priority_daily_state` - *(v0.8.0)* Current priority state (EV/Home/EV_Free)

**Requirements:**
- Charger must be in status: `charger_charging`, `charger_end`, or `charger_wait`
- Does NOT activate when charger status is `charger_free` (not connected)

**Enhanced Logging (v0.7.0/v0.8.0):**
- Every decision is logged with reasoning
- Comprehensive state information at each check
- Priority balancer decisions fully traced
- Easy debugging and understanding of algorithm behavior

#### 3. Charge Target Mode (Coming Soon)
Charge to a specific battery percentage by a target time.

#### 4. Cheapest Mode (Coming Soon)
Charge during the cheapest electricity price hours.

---

### 🚫 Smart Charger Blocker (v0.4.0+, Simplified in v0.8.6)
Automatically prevents EV charging during nighttime.

**How it works:**
- Monitors your charger status in real-time
- Blocks charging when current time is after sunset AND before sunrise
- Sends persistent notifications when charging is blocked
- Fully configurable via helper entities

**Controls:**
- `switch.evsc_forza_ricarica` - **Global Kill Switch**: When ON, disables ALL smart features (manual mode)
- `switch.evsc_smart_charger_blocker_enabled` - Enable/disable Smart Charger Blocker

---

### 🌙 Night Smart Charge (v0.9.0)
**Intelligent overnight charging that optimizes energy source based on next-day solar forecast.**

The Night Smart Charge feature automatically charges your EV overnight using the most economical energy source, determined by your solar production forecast for the next day. It works alongside the Priority Balancer to ensure both your EV and home battery are ready for the day ahead.

**How it works:**

1. **Scheduled Check**: At your configured time (default 01:00), the system evaluates:
   - Next day's PV (solar) forecast from your configured sensor
   - Current EV State of Charge (SOC)
   - Today's EV target SOC (from Priority Balancer configuration)

2. **Smart Decision Making**:
   - **High Solar Forecast** (≥ threshold, default 20 kWh):
     - Charges from **home battery** at fixed amperage (default 16A)
     - Rationale: Tomorrow's abundant solar will recharge the home battery
     - Priority Balancer monitors and stops when either:
       - EV reaches target SOC, OR
       - Home battery reaches minimum SOC

   - **Low/No Solar Forecast** (< threshold):
     - Charges from **grid** at fixed amperage (default 16A)
     - Charges until EV reaches target SOC
     - Grid import detection is disabled during night charging
     - Rationale: Preserve home battery for tomorrow since solar won't replenish it

3. **Active Monitoring**: After the scheduled check:
   - Continues checking every minute until sunrise
   - Automatically detects late arrivals (car plugged in after scheduled time)
   - Seamlessly transitions to Solar Surplus mode at sunrise

4. **Integration with Existing Features**:
   - **Overrides Smart Blocker**: Night charge bypasses nighttime blocking
   - **Works with Priority Balancer**: Respects daily SOC targets and battery limits
   - **Transitions to Solar Surplus**: Automatically switches when sun rises
   - **Comprehensive Logging**: All decisions logged with 🌙 prefix for easy debugging

**Configuration:**
- `switch.evsc_night_smart_charge_enabled` - Enable/disable Night Smart Charge
- `time.evsc_night_charge_time` - Time to start check (default: 01:00)
- `number.evsc_min_solar_forecast_threshold` - Minimum forecast to use battery (0-100 kWh, default: 20)
- `number.evsc_night_charge_amperage` - Fixed charging amperage (6-32A, default: 16)

**Setup Requirements:**
1. Configure a PV forecast sensor during integration setup (Step 4)
   - Sensor should provide next-day solar forecast in kWh
   - If unavailable, system falls back to grid charging mode
2. Configure daily EV SOC targets in Priority Balancer
3. Set your preferred night charge time and threshold

**Example Scenarios:**

| Scenario | PV Forecast | Decision | Reasoning |
|----------|-------------|----------|-----------|
| Clear day ahead | 25 kWh | Battery Mode (16A) | Tomorrow's 25 kWh will easily recharge home battery |
| Cloudy day ahead | 12 kWh | Grid Mode (16A) | Preserve home battery - 12 kWh won't fully recharge it |
| Forecast unavailable | N/A | Grid Mode (16A) | Safe fallback - protect home battery |
| Late arrival (02:30) | 30 kWh | Battery Mode (16A) | Detected connection, still before sunrise |

**Morning Behavior:**
```
01:00 - Night charge starts (battery mode, forecast 28 kWh)
01:00-06:45 - Charging at 16A, Priority Balancer monitoring
06:45 - EV reaches 80% target, charging stops
06:50 - Sunrise occurs
07:00 - Solar production begins, Solar Surplus takes over if needed
```

**Logging Examples:**
```
🌙 Night Smart Charge: Scheduled check triggered at 01:00
🌙 Active window check: now=2024-01-15 01:00:00, scheduled=01:00, sunrise=06:50, active=True
🌙 Checking if charging needed: current EV SOC=45%, target=80%
🌙 PV forecast for next day: 28.5 kWh
🌙 Decision: forecast 28.5 >= threshold 20.0 → BATTERY mode selected
🔋 Starting BATTERY charge mode at 16A
✅ BATTERY charge started - Balancer will monitor and stop when:
   1. EV reaches target SOC (80%)
   2. Home battery reaches minimum SOC (20%)
```

**Safety Features:**
- PV forecast sensor unavailable → defaults to grid mode
- Priority Balancer monitors all charging to prevent over-discharge
- Grid import detection disabled only during night charging
- Smart Blocker overridden only when night charge active
- Automatically stops at sunrise and hands off to Solar Surplus

---

## Installation

### HACS (Recommended)

1. Add this repository as a custom repository in HACS
2. Search for "EV Smart Charger" in HACS
3. Click Install
4. Restart Home Assistant

### Manual Installation

1. Copy the `custom_components/ev_smart_charger` folder to your Home Assistant `custom_components` directory
2. Restart Home Assistant

---

## Configuration

### Initial Setup

1. Go to **Settings → Devices & Services → Add Integration**
2. Search for "EV Smart Charger"
3. Follow the 4-step setup wizard:
   - **Step 1:** Name your integration
   - **Step 2:** Configure charger entities (switch, current, status)
   - **Step 3:** Configure monitoring sensors (SOC car/home, solar, consumption, grid import)
   - **Step 4:** Configure PV forecast sensor (optional, for Night Smart Charge)

### Required Entities

During setup, you'll map your existing Home Assistant entities to these roles:

**Charger Controls:**
- **EV Charger Switch** - Switch entity that controls charger on/off
- **EV Charger Current** - Number/Select entity for charging amperage (6-32A)
- **EV Charger Status** - Sensor showing charger state: `charger_charging`, `charger_free`, `charger_end`

**Monitoring Sensors:**
- **Car Battery SOC** - EV battery level (%)
- **Home Battery SOC** - Home battery level (%)
- **Solar Production** - Current PV production (W)
- **Home Consumption** - Current home power usage (W)
- **Grid Import** - Power being imported from grid (W) - Positive = importing
- **PV Forecast** *(Optional, v0.9.0+)* - Next-day solar forecast (kWh) for Night Smart Charge

### Helper Entities (Auto-Created)

The integration **automatically creates 29 helper entities** when you add it:

#### Switches (5)

**1. EVSC Forza Ricarica**
- **Entity ID:** `switch.ev_smart_charger_<entry_id>_evsc_forza_ricarica`
- **Purpose:** Global kill switch - When ON, all smart features are disabled
- **Icon:** `mdi:power`

**2. EVSC Smart Charger Blocker**
- **Entity ID:** `switch.ev_smart_charger_<entry_id>_evsc_smart_charger_blocker_enabled`
- **Purpose:** Enable/disable the Smart Charger Blocker feature
- **Icon:** `mdi:solar-power`

**3. EVSC Use Home Battery** *(v0.7.0+)*
- **Entity ID:** `switch.ev_smart_charger_<entry_id>_evsc_use_home_battery`
- **Purpose:** Enable home battery support in Solar Surplus mode
- **Icon:** `mdi:home-battery`

**4. EVSC Priority Balancer** *(v0.8.0+)*
- **Entity ID:** `switch.ev_smart_charger_<entry_id>_evsc_priority_balancer_enabled`
- **Purpose:** Enable intelligent priority-based charging between EV and home battery
- **Icon:** `mdi:scale-balance`

**5. EVSC Night Smart Charge** *(v0.9.0+)*
- **Entity ID:** `switch.ev_smart_charger_<entry_id>_evsc_night_smart_charge_enabled`
- **Purpose:** Enable/disable Night Smart Charge automation
- **Icon:** `mdi:moon-waning-crescent`

#### Numbers (21)

**1. EVSC Check Interval** *(v0.6.0+)*
- **Entity ID:** `number.ev_smart_charger_<entry_id>_evsc_check_interval`
- **Purpose:** How often Solar Surplus recalculates charging power (minutes)
- **Default:** 1 min | **Range:** 1-60 min (step: 1 min)
- **Icon:** `mdi:timer-outline`

**2. EVSC Grid Import Threshold** *(v0.6.0+)*
- **Entity ID:** `number.ev_smart_charger_<entry_id>_evsc_grid_import_threshold`
- **Purpose:** Maximum allowed grid import (W) before reducing charging
- **Default:** 50W | **Range:** 0-1000W (step: 10W)
- **Icon:** `mdi:transmission-tower`

**3. EVSC Grid Import Delay** *(v0.7.0+)*
- **Entity ID:** `number.ev_smart_charger_<entry_id>_evsc_grid_import_delay`
- **Purpose:** Delay (seconds) before reacting to grid import exceeding threshold
- **Default:** 30s | **Range:** 0-120s (step: 5s)
- **Icon:** `mdi:timer-sand`
- **Use:** Prevents overreaction to brief grid import spikes

**4. EVSC Surplus Drop Delay** *(v0.7.0+)*
- **Entity ID:** `number.ev_smart_charger_<entry_id>_evsc_surplus_drop_delay`
- **Purpose:** Delay (seconds) before reducing charging when surplus drops
- **Default:** 30s | **Range:** 0-120s (step: 5s)
- **Icon:** `mdi:timer-sand`
- **Use:** Prevents overreaction to temporary cloud cover or consumption spikes

**5. EVSC Home Battery Min SOC** *(v0.7.0+)*
- **Entity ID:** `number.ev_smart_charger_<entry_id>_evsc_home_battery_min_soc`
- **Purpose:** Minimum home battery charge level (%) to enable Battery Support feature
- **Default:** 20% | **Range:** 0-100% (step: 5%)
- **Icon:** `mdi:battery-50`
- **Use:** Protects home battery from over-discharge while supporting EV charging (Battery Support feature only)

**6-12. EVSC EV Min SOC [Day]** *(v0.8.0+)*
- **Entity IDs:**
  - `number.ev_smart_charger_<entry_id>_evsc_ev_min_soc_monday`
  - `number.ev_smart_charger_<entry_id>_evsc_ev_min_soc_tuesday`
  - `number.ev_smart_charger_<entry_id>_evsc_ev_min_soc_wednesday`
  - `number.ev_smart_charger_<entry_id>_evsc_ev_min_soc_thursday`
  - `number.ev_smart_charger_<entry_id>_evsc_ev_min_soc_friday`
  - `number.ev_smart_charger_<entry_id>_evsc_ev_min_soc_saturday`
  - `number.ev_smart_charger_<entry_id>_evsc_ev_min_soc_sunday`
- **Purpose:** Daily minimum EV SOC targets for Priority Balancer
- **Default:** 50% (weekdays), 80% (weekends)
- **Range:** 0-100% (step: 5%)
- **Icons:** `mdi:calendar-monday` through `mdi:calendar-sunday`
- **Use:** System compares current EV SOC against today's target to determine charging priority

**13-19. EVSC Home Min SOC [Day]** *(v0.8.7+)*
- **Entity IDs:**
  - `number.ev_smart_charger_<entry_id>_evsc_home_min_soc_monday`
  - `number.ev_smart_charger_<entry_id>_evsc_home_min_soc_tuesday`
  - `number.ev_smart_charger_<entry_id>_evsc_home_min_soc_wednesday`
  - `number.ev_smart_charger_<entry_id>_evsc_home_min_soc_thursday`
  - `number.ev_smart_charger_<entry_id>_evsc_home_min_soc_friday`
  - `number.ev_smart_charger_<entry_id>_evsc_home_min_soc_saturday`
  - `number.ev_smart_charger_<entry_id>_evsc_home_min_soc_sunday`
- **Purpose:** Daily home battery SOC targets for Priority Balancer
- **Default:** 50% (all days)
- **Range:** 0-100% (step: 5%)
- **Icons:** `mdi:calendar-monday` through `mdi:calendar-sunday`
- **Use:** System compares current home battery SOC against today's target to determine charging priority

**20. EVSC Min Solar Forecast Threshold** *(v0.9.0+)*
- **Entity ID:** `number.ev_smart_charger_<entry_id>_evsc_min_solar_forecast_threshold`
- **Purpose:** Minimum PV forecast (kWh) to enable battery charging mode
- **Default:** 20 kWh
- **Range:** 0-100 kWh (step: 1)
- **Icon:** `mdi:solar-power-variant`
- **Use:** If forecast ≥ threshold, charge from battery; if < threshold, charge from grid

**21. EVSC Night Charge Amperage** *(v0.9.0+)*
- **Entity ID:** `number.ev_smart_charger_<entry_id>_evsc_night_charge_amperage`
- **Purpose:** Fixed amperage for Night Smart Charge
- **Default:** 16A
- **Range:** 6-32A (step: 2)
- **Icon:** `mdi:current-ac`

#### Time (1)

**1. EVSC Night Charge Time** *(v0.9.3+)*
- **Entity ID:** `time.ev_smart_charger_<entry_id>_evsc_night_charge_time`
- **Purpose:** Time of day to start Night Smart Charge check
- **Default:** 01:00:00
- **Icon:** `mdi:clock-time-one`
- **Note:** Provides native time picker UI in Home Assistant

#### Selects (1)

**1. EVSC Charging Profile** *(v0.6.0+)*
- **Entity ID:** `select.ev_smart_charger_<entry_id>_evsc_charging_profile`
- **Purpose:** Choose charging mode (manual, solar_surplus, charge_target, cheapest)
- **Default:** manual
- **Icon:** `mdi:ev-station`

#### Sensors (2)

**1. EVSC Diagnostic Status**
- **Entity ID:** `sensor.ev_smart_charger_<entry_id>_evsc_diagnostic`
- **Purpose:** Real-time automation status and diagnostic information
- **Icon:** `mdi:information-outline`

**2. EVSC Priority Daily State** *(v0.8.0+)*
- **Entity ID:** `sensor.ev_smart_charger_<entry_id>_evsc_priority_daily_state`
- **Purpose:** Current charging priority state
- **Values:** `"EV"`, `"Home"`, `"EV_Free"`
- **Icon:** `mdi:priority-high`
- **Attributes:**
  - `current_ev_soc`: Current EV battery level
  - `current_home_soc`: Current home battery level
  - `target_ev_soc`: Today's EV target
  - `target_home_soc`: Home battery target
  - `reason`: Explanation of priority decision
  - `balancer_enabled`: Whether feature is active
  - `today`: Current day of week

**Note:** These entities are created automatically - no manual setup required!

---

## Usage

### Dashboard Card

Copy this complete vertical stack card to your Lovelace dashboard for full control:

```yaml
type: vertical-stack
cards:
  # ============= MAIN CONTROLS =============
  - type: entities
    title: ⚡ EV Smart Charger - Main Controls
    show_header_toggle: false
    entities:
      # Global Override
      - entity: switch.ev_smart_charger_YOUR_ENTRY_ID_evsc_forza_ricarica
        name: 🔴 Forza Ricarica (Override All)
        icon: mdi:power

      # Charging Profile Selector
      - type: divider
      - entity: select.ev_smart_charger_YOUR_ENTRY_ID_evsc_charging_profile
        name: ⚡ Charging Profile
        icon: mdi:ev-station

      # Priority State (read-only)
      - type: divider
      - entity: sensor.ev_smart_charger_YOUR_ENTRY_ID_evsc_priority_daily_state
        name: 🎯 Current Priority
        icon: mdi:priority-high

  # ============= NIGHT SMART CHARGE =============
  - type: entities
    title: 🌙 Night Smart Charge Settings
    show_header_toggle: false
    entities:
      # Enable/Disable
      - entity: switch.ev_smart_charger_YOUR_ENTRY_ID_evsc_night_smart_charge_enabled
        name: Enable Night Smart Charge
        icon: mdi:moon-waning-crescent

      # Time Configuration
      - type: divider
      - entity: time.ev_smart_charger_YOUR_ENTRY_ID_evsc_night_charge_time
        name: ⏰ Start Time
        icon: mdi:clock-time-one

      # Threshold & Amperage
      - entity: number.ev_smart_charger_YOUR_ENTRY_ID_evsc_min_solar_forecast_threshold
        name: ☀️ Min Solar Forecast (kWh)
        icon: mdi:solar-power-variant
      - entity: number.ev_smart_charger_YOUR_ENTRY_ID_evsc_night_charge_amperage
        name: ⚡ Night Charge Amperage
        icon: mdi:current-ac

  # ============= SOLAR SURPLUS SETTINGS =============
  - type: entities
    title: ☀️ Solar Surplus Settings
    show_header_toggle: false
    entities:
      # Basic Settings
      - entity: number.ev_smart_charger_YOUR_ENTRY_ID_evsc_check_interval
        name: ⏱️ Check Interval (min)
        icon: mdi:timer-outline
      - entity: number.ev_smart_charger_YOUR_ENTRY_ID_evsc_grid_import_threshold
        name: 🔌 Grid Import Threshold (W)
        icon: mdi:transmission-tower

      # Advanced Delays
      - type: divider
      - entity: number.ev_smart_charger_YOUR_ENTRY_ID_evsc_grid_import_delay
        name: ⏳ Grid Import Delay (s)
        icon: mdi:timer-sand
      - entity: number.ev_smart_charger_YOUR_ENTRY_ID_evsc_surplus_drop_delay
        name: ⏳ Surplus Drop Delay (s)
        icon: mdi:timer-sand-empty

      # Battery Support
      - type: divider
      - entity: switch.ev_smart_charger_YOUR_ENTRY_ID_evsc_use_home_battery
        name: 🔋 Use Home Battery
        icon: mdi:home-battery
      - entity: number.ev_smart_charger_YOUR_ENTRY_ID_evsc_home_battery_min_soc
        name: 🔋 Home Battery Min SOC (%)
        icon: mdi:battery-30

  # ============= PRIORITY BALANCER =============
  - type: entities
    title: ⚖️ Priority Balancer Settings
    show_header_toggle: false
    entities:
      # Enable/Disable
      - entity: switch.ev_smart_charger_YOUR_ENTRY_ID_evsc_priority_balancer_enabled
        name: Enable Priority Balancer
        icon: mdi:scale-balance

      # EV Daily Targets
      - type: divider
      - type: section
        label: "🚗 EV Daily Targets"
      - entity: number.ev_smart_charger_YOUR_ENTRY_ID_evsc_ev_min_soc_monday
        name: Monday
        icon: mdi:calendar-monday
      - entity: number.ev_smart_charger_YOUR_ENTRY_ID_evsc_ev_min_soc_tuesday
        name: Tuesday
        icon: mdi:calendar-tuesday
      - entity: number.ev_smart_charger_YOUR_ENTRY_ID_evsc_ev_min_soc_wednesday
        name: Wednesday
        icon: mdi:calendar-wednesday
      - entity: number.ev_smart_charger_YOUR_ENTRY_ID_evsc_ev_min_soc_thursday
        name: Thursday
        icon: mdi:calendar-thursday
      - entity: number.ev_smart_charger_YOUR_ENTRY_ID_evsc_ev_min_soc_friday
        name: Friday
        icon: mdi:calendar-friday
      - entity: number.ev_smart_charger_YOUR_ENTRY_ID_evsc_ev_min_soc_saturday
        name: Saturday
        icon: mdi:calendar-saturday
      - entity: number.ev_smart_charger_YOUR_ENTRY_ID_evsc_ev_min_soc_sunday
        name: Sunday
        icon: mdi:calendar-sunday

      # Home Battery Daily Targets
      - type: divider
      - type: section
        label: "🏠 Home Battery Daily Targets"
      - entity: number.ev_smart_charger_YOUR_ENTRY_ID_evsc_home_min_soc_monday
        name: Monday
        icon: mdi:calendar-monday
      - entity: number.ev_smart_charger_YOUR_ENTRY_ID_evsc_home_min_soc_tuesday
        name: Tuesday
        icon: mdi:calendar-tuesday
      - entity: number.ev_smart_charger_YOUR_ENTRY_ID_evsc_home_min_soc_wednesday
        name: Wednesday
        icon: mdi:calendar-wednesday
      - entity: number.ev_smart_charger_YOUR_ENTRY_ID_evsc_home_min_soc_thursday
        name: Thursday
        icon: mdi:calendar-thursday
      - entity: number.ev_smart_charger_YOUR_ENTRY_ID_evsc_home_min_soc_friday
        name: Friday
        icon: mdi:calendar-friday
      - entity: number.ev_smart_charger_YOUR_ENTRY_ID_evsc_home_min_soc_saturday
        name: Saturday
        icon: mdi:calendar-saturday
      - entity: number.ev_smart_charger_YOUR_ENTRY_ID_evsc_home_min_soc_sunday
        name: Sunday
        icon: mdi:calendar-sunday

  # ============= SMART BLOCKER =============
  - type: entities
    title: 🚫 Smart Charger Blocker
    show_header_toggle: false
    entities:
      - entity: switch.ev_smart_charger_YOUR_ENTRY_ID_evsc_smart_charger_blocker_enabled
        name: Enable Smart Blocker
        icon: mdi:solar-power
```

**📝 Setup Instructions:**

1. **Find Your Entry ID:**
   - Go to **Developer Tools → States**
   - Search for "evsc"
   - Look at any entity ID, example: `switch.ev_smart_charger_abc123_evsc_forza_ricarica`
   - Your entry ID is the part between `ev_smart_charger_` and `_evsc` (e.g., `abc123`)

2. **Replace in YAML:**
   - Replace all instances of `YOUR_ENTRY_ID` with your actual entry ID
   - Use Find & Replace in your text editor for speed

3. **Add to Dashboard:**
   - Go to your dashboard
   - Click **Edit Dashboard** → **Add Card** → **Manual**
   - Paste the YAML code
   - Save

4. **Optional Customization:**
   - Remove sections you don't use (e.g., Priority Balancer if disabled)
   - Adjust card order to your preference
   - Add to a dedicated "EV Charging" view/tab

**💡 Pro Tips:**

- **Collapsible Sections:** Can't collapse? Use `state_color: true` on switches for visual feedback
- **Quick Access:** Pin frequently used controls (Forza Ricarica, Charging Profile) to a separate card
- **Mobile Friendly:** The vertical stack works great on mobile devices
- **Monitoring:** Add sensor cards above this stack to monitor charging status, SOC levels, etc.

### How Smart Charger Blocker Works

```
Car plugged in → Charger status = "charger_charging"
  ↓
Check: Is "Forza Ricarica" ON?
  → YES: Allow charging (manual override)
  → NO: Continue
  ↓
Check: Is "Smart Charger Blocker" enabled?
  → NO: Allow charging
  → YES: Continue
  ↓
Check: Is it nighttime (after sunset)?
  → YES: Block charging + send notification
  → NO: Allow charging
```

### Typical Scenarios

**Scenario 1: Daytime**
- Time: 2:00 PM (after sunrise, before sunset)
- Result: ✅ Charging allowed

**Scenario 2: Nighttime**
- Time: 11:00 PM (after sunset, before sunrise)
- Result: 🚫 Charging blocked

**Scenario 3: Manual Override**
- "Forza Ricarica" is ON
- Any time
- Result: ✅ Charging allowed (all automations disabled)

---

## Troubleshooting

### Integration Won't Start

See [TROUBLESHOOTING.md](TROUBLESHOOTING.md) for detailed debugging steps.

**Quick checks:**
1. **View logs:** Settings → System → Logs (search for "evsc")
2. **Verify helpers exist:** Settings → Devices & Services → Helpers
3. **Check entity mappings:** Settings → Devices & Services → EV Smart Charger → Configure

### Enable Debug Logging

Add to your `configuration.yaml`:

```yaml
logger:
  default: info
  logs:
    custom_components.ev_smart_charger: debug
```

Then restart Home Assistant.

### Charging Not Being Blocked

1. Verify `input_boolean.evsc_smart_charger_blocker_enabled` is ON
2. Verify `input_boolean.evsc_forza_ricarica` is OFF
3. Check that your charger status sensor reports `charger_charging` when car is plugged in
4. Check logs for blocking events

---

## Roadmap / Planned Features

- [ ] **Cheap Mode:** Charge during lowest electricity price hours
- [ ] **PV Hybrid Mode:** Charge from solar excess, use grid as backup
- [ ] **SOC-Based Charging:** Smart charging based on car/home battery levels
- [ ] **Time-of-Use Optimization:** Schedule charging based on TOU tariffs
- [ ] **Configurable Schedules:** User-defined charging windows
- [ ] **Energy Cost Tracking:** Monitor charging costs over time

---

## Changelog

### v0.9.11 (2025-10-29) - Current - Diagnostic Sensor & Detailed Error Reporting
- **NEW: Solar Surplus Diagnostic Sensor** (`sensor.evsc_solar_surplus_diagnostic`)
  - Real-time diagnostic information about solar surplus checks
  - Shows current state (OK, ERROR, WAITING, etc.)
  - Detailed attributes with all sensor values and check results
  - Helps troubleshoot "unknown" sensor value errors
  - Updates on every periodic check with comprehensive data

- **FIX: Detailed error reporting for "unknown" sensor values**
  - Previously: Generic error "could not convert string to float: 'unknown'"
  - Now: **Specific identification of WHICH sensor has invalid value**
  - Logs show:
    - Sensor entity ID
    - Current sensor value (e.g., "unknown", "unavailable", etc.)
    - Exact error message
  - Makes troubleshooting much easier

- **Enhanced Error Logging:**
  - Each sensor parsed individually with try/catch
  - Collects all sensor errors before reporting
  - Detailed error block shows:
    - Solar Production entity & value
    - Home Consumption entity & value
    - Grid Import entity & value
    - Specific error for each invalid sensor
  - Diagnostic sensor updated with error details

- **Example Error Output:**
  ```
  ❌ SENSOR ERROR DETAILS:
     Solar Production (sensor.solar_production): 'unknown' - could not convert string to float: 'unknown'
     Entity IDs to check:
     - Solar Production: sensor.solar_production
     - Home Consumption: sensor.home_consumption
     - Grid Import: sensor.grid_import
  ```

- **Diagnostic Sensor Attributes:**
  - `last_check`: ISO timestamp of last check
  - `errors`: List of all sensor errors (if any)
  - `solar_production_entity`: Entity ID
  - `solar_production_value`: Current value
  - `home_consumption_entity`: Entity ID
  - `home_consumption_value`: Current value
  - `grid_import_entity`: Entity ID
  - `grid_import_value`: Current value
  - *(More attributes added as development continues)*

- **Files Modified:**
  - `sensor.py` - Added `EVSCSolarSurplusDiagnosticSensor` class
  - `solar_surplus.py` - Enhanced error handling, added diagnostic sensor updates, added datetime import
  - `manifest.json` - Version 0.9.11

### v0.9.10 (2025-10-29) - Critical: Charger Start Fix in EV_FREE Mode
- **FIX: Charger now treats amperage as 0 when OFF, enabling proper start logic**
  - **Critical Issue**: When charger was OFF, `current_amps` was read from charger setting (e.g., 16A from previous session)
  - Solar surplus logic compared `target_amps` (e.g., 26A) vs `current_amps` (16A) → triggered increase (correct)
  - BUT if `target_amps` (6A) < `current_amps` (16A), charger would NOT start despite having surplus
  - **v0.9.9 incomplete fix**: Only removed early return, didn't fix amperage comparison

- **Root Cause Identified:**
  - User correctly pointed out: "If priority switches from HOME to EV_FREE, it should start charging"
  - When Priority Balancer transitions HOME → EV_FREE, charger is OFF (was stopped for home battery)
  - Solar surplus available (6000W = 26A), but comparison logic failed because charger OFF state not handled
  - System read stored amperage setting instead of treating OFF charger as 0A

- **Complete Fix:**
  - Modified amperage detection logic (lines 557-573) to check charger switch state FIRST
  - If charger is **ON**: Read actual amperage from sensor (normal operation)
  - If charger is **OFF**: Set `current_amps = 0` (allows ANY surplus to trigger start)
  - Now comparison works correctly: `target_amps (26A) > current_amps (0A)` = TRUE → starts charger

- **Impact:**
  - **Priority transitions now work**: HOME → EV_FREE automatically starts charging with available solar
  - **Fresh installations work**: Charger OFF + solar surplus → starts automatically
  - **All surplus levels work**: Even low surplus (6A) will start charger when OFF
  - **Proper state machine**: OFF (0A) → any surplus → ON at target amperage

- **Technical Details:**
  - Added charger switch state check before reading amperage
  - Treats OFF charger as 0A for comparison logic
  - Ensures line 677 condition `target_amps > current_amps` always evaluates correctly
  - Complements v0.9.9 EV_FREE fall-through fix

- **Files Modified:**
  - `solar_surplus.py` - Amperage detection logic (lines 557-573)
  - `manifest.json` - Version 0.9.10

### v0.9.9 (2025-10-29) - EV_FREE Solar Surplus Charging Fix (Incomplete)
- **FIX: EV_FREE priority now allows solar surplus charging when charger is OFF**
  - Previously, when Priority Balancer set priority to EV_FREE (both EV and home battery targets met), the automation would stop charging if charger was ON and then exit early
  - This prevented the charger from starting when it was OFF, even with abundant solar surplus available
  - Now, when charger is OFF in EV_FREE mode, the solar surplus logic continues to evaluate whether to start charging
  - Allows excess solar energy to charge EV even after daily targets are met (maximizing solar usage)
  - Fixed fresh installation scenario where charger was OFF, targets met, but 6000W solar surplus was not being used

- **Technical Details:**
  - Modified `solar_surplus.py` EV_FREE priority check (lines 479-503)
  - Added else clause to allow fall-through when charger is OFF
  - Only returns early (exits automation) when charger is ON and successfully stopped
  - When charger is OFF, logs informational message and continues to solar surplus calculation logic

- **Impact:**
  - Users with Priority Balancer enabled will now see charger start automatically with solar surplus, even after daily targets met
  - Maximizes solar energy utilization by using excess production
  - Resolves reported issue where fresh v0.9.8 installation wasn't starting charger despite 6000W available solar

- **Files Modified:**
  - `solar_surplus.py` - EV_FREE priority logic
  - `manifest.json` - Version 0.9.9

### v0.9.8 (2025-10-29) - Critical Automation Conflict Resolution
- **NEW: Automation Coordinator system with priority-based control**
  - Centralized coordinator prevents conflicts between automations
  - Priority hierarchy: Override (1) > Smart Blocker (2) > Night Charge (3) > Priority Balancer (4) > Solar Surplus (5)
  - All automations request permission before controlling charger
  - Tracks action history (last 50 actions) for debugging

- **FIX: Smart Blocker enforcement mode exit conditions**
  - Added 30-minute timeout to automatically exit enforcement
  - Exits when evsc_forza_ricarica override enabled
  - Exits when Smart Charger Blocker disabled
  - Exits when blocking conditions no longer apply (e.g., sunrise)

- **FIX: Enforcement re-checks blocking conditions**
  - Before re-blocking, now validates conditions are still true
  - Respects override switch during all enforcement operations
  - Releases control when conditions change

- **FIX: Endless conflict loop between Smart Blocker and Priority Balancer**
  - Eliminated 64+ repeated blocking attempts in logs
  - Priority Balancer can no longer override Smart Blocker's safety rules
  - Coordinator manages priority and prevents conflicting turn_on/turn_off

- **FIX: Override switch now works during enforcement**
  - evsc_forza_ricarica has highest priority (Priority 1)
  - Coordinator blocks any turn_off attempts when override active
  - User can force charging at any time

- **FIX: EV_FREE mode now works correctly at night**
  - Priority Balancer respects Smart Blocker's active enforcement
  - After enforcement timeout or sunrise, Priority Balancer can enable charging
  - No more endless conflict loops

### v0.9.7 (2025-10-29) - Critical Automation Fixes
- **FIX: Smart Blocker enforcement with retry logic and continuous monitoring**
  - Added retry logic (3 attempts) with verification after each turn_off command
  - Implemented continuous enforcement monitoring to prevent external re-enable
  - Enhanced logging: every blocking attempt includes timestamp, reason, current state, verification result
  - Conflict detection: warns if Night Smart Charge is active when blocking
  - Sends detailed notifications on blocking success or failure

- **FIX: Night Smart Charge window logic and comprehensive logging**
  - Fixed sunrise calculation bug: now correctly determines today vs tomorrow's sunrise
  - Window check logs detailed information: current time, scheduled time, sunrise, boolean result
  - Initialization logs now show all configuration values (enabled, time, threshold, amperage)
  - Each evaluation step logs detailed progress and decisions
  - Added explicit logging when evaluation is skipped (not in window, disabled, etc.)

- **FIX: Home battery monitoring during Night Smart Charge battery mode**
  - Implemented continuous monitoring every 1 minute during battery mode charging
  - Monitors home battery SOC vs minimum threshold
  - Monitors EV SOC vs target threshold
  - Automatically stops charging when home battery reaches minimum (CRITICAL FIX for Problem 3)
  - Automatically stops charging when EV reaches target
  - Detailed logging every minute showing battery levels and thresholds

- **FIX: Enhanced Priority Balancer logging**
  - Comprehensive decision logging with structured format
  - Clear action confirmations when stopping EV charger
  - Logs priority decisions with full context (current vs target SOC for both EV and home)
  - Added logging for EV_FREE state (both targets met)
  - Every state transition now logged with reason and action taken

- **Files Modified:**
  - `automations.py` - Smart Blocker enforcement logic
  - `night_smart_charge.py` - Window logic, logging, battery monitoring
  - `solar_surplus.py` - Priority Balancer logging enhancements
  - `manifest.json` - Version 0.9.7

### v0.9.6 (2025-10-28) - Entity ID Pattern Fix (BREAKING CHANGE)
- **FIX: Enforced consistent entity_id pattern across all platforms**
  - **⚠️ BREAKING CHANGE:** All entities now have explicit entity_id format
  - Pattern: `{platform}.ev_smart_charger_{entry_id}_evsc_{suffix}`
  - Example: `switch.ev_smart_charger_abc123_evsc_forza_ricarica`
  - Fixed inconsistent entity_id generation that was causing dashboard YAML issues

- **Why This Change:**
  - Previous versions relied on Home Assistant's automatic entity_id generation
  - This created unpredictable entity IDs based on entity names
  - New explicit format ensures consistency and matches dashboard YAML

- **Migration Required:**
  - After updating, entity IDs will change for all helper entities
  - You'll need to update automations, scripts, and dashboards referencing old entity IDs
  - Old entity IDs may have been: `switch.evsc_smart_charger_blocker`
  - New entity IDs will be: `switch.ev_smart_charger_{entry_id}_evsc_smart_charger_blocker_enabled`

- **Files Modified:**
  - `switch.py` - Added explicit entity_id assignment
  - `number.py` - Added explicit entity_id assignment
  - `select.py` - Added explicit entity_id assignment
  - `time.py` - Added explicit entity_id assignment
  - `sensor.py` - Added explicit entity_id assignment
  - `manifest.json` - Version 0.9.6

### v0.9.5 (2025-10-28) - Entity ID Fix
- **FIX: Corrected time entity unique_id pattern**
  - Fixed unique_id to follow same pattern as other entities
  - Pattern: `{DOMAIN}_{entry_id}_{suffix}` instead of `{entry_id}_{suffix}`
  - Entity ID will now be: `time.ev_smart_charger_{entry_id}_evsc_night_charge_time`
  - Ensures consistent entity ID generation across all platforms

- **Files Modified:**
  - `time.py` - Fixed unique_id generation
  - `manifest.json` - Version 0.9.5

### v0.9.4 (2025-10-28) - Dashboard YAML
- **DOCS: Added comprehensive dashboard card**
  - Complete vertical-stack YAML with all 29 entities
  - 5 organized sections: Main Controls, Night Smart Charge, Solar Surplus, Priority Balancer, Smart Blocker
  - Copy-paste ready with clear setup instructions
  - Mobile-friendly layout

### v0.9.3 (2025-10-28) - Time Entity Refactor
- **IMPROVEMENT: Replaced hour/minute numbers with time entity**
  - Replaced `number.evsc_night_charge_hour` and `number.evsc_night_charge_minute` with single `time.evsc_night_charge_time`
  - Provides native time picker UI in Home Assistant
  - More user-friendly configuration experience
  - Default time: 01:00:00

- **Entity Count Changes:**
  - Total: 30 → 29 entities
  - Breakdown: 5 switches, 21 numbers (-2), 1 time (+1), 1 select, 2 sensors

- **Files Modified:**
  - `const.py` - Added time platform, updated constants
  - `time.py` - NEW: Time platform implementation
  - `number.py` - Removed hour/minute entities
  - `night_smart_charge.py` - Updated to use time entity
  - `manifest.json` - Version 0.9.3

### v0.9.2 (2025-10-28) - Translation Improvements
- **FIX: Added missing PV forecast translations**
  - Added comprehensive help text for Step 4 (PV forecast)
  - Examples of popular solar forecast integrations
  - Clear indication that step is optional

### v0.9.1 (2025-10-28) - Icon Support
- **FIX: Added integration icon support**
  - Added `"icon": "mdi:ev-station"` to manifest.json
  - Placed brand assets in proper locations for HACS

### v0.9.0 (2025-10-28) - Night Smart Charge
- **NEW FEATURE: Night Smart Charge** 🌙
  - Intelligent overnight charging based on next-day solar forecast
  - Automatically chooses between battery mode or grid mode
  - **Battery Mode:** Uses home battery when forecast ≥ threshold (preserving grid energy)
  - **Grid Mode:** Uses grid when forecast < threshold (preserving home battery)
  - Scheduled check at configurable time (default 01:00)
  - Continues monitoring every minute until sunrise
  - Detects late arrivals (car plugged in after scheduled time)
  - Seamlessly transitions to Solar Surplus mode at sunrise
  - Works alongside Priority Balancer for SOC monitoring
  - Overrides Smart Blocker during active night charging
  - Grid import detection disabled during night charging

- **New Entities (5):**
  - `switch.evsc_night_smart_charge_enabled` - Enable/disable feature
  - `number.evsc_night_charge_hour` - Hour to start (replaced in v0.9.3)
  - `number.evsc_night_charge_minute` - Minute to start (replaced in v0.9.3)
  - `number.evsc_min_solar_forecast_threshold` - Min forecast for battery mode (0-100 kWh, default: 20)
  - `number.evsc_night_charge_amperage` - Fixed amperage (6-32A, default: 16)

- **Configuration Enhancements:**
  - Added Step 4 to config flow: Optional PV forecast sensor selection
  - PV forecast sensor provides next-day solar forecast in kWh
  - Fallback to grid mode if sensor unavailable

- **Integration Improvements:**
  - Solar Surplus automation checks for active night charge before running
  - Smart Blocker overridden when night charge is active
  - Comprehensive logging with 🌙 prefix for all night charge events
  - Total entity count increased from 25 to 30 (5 switches, 23 numbers, 1 select, 2 sensors)

- **Files Added:**
  - `night_smart_charge.py` - Complete Night Smart Charge automation logic

- **Files Modified:**
  - `const.py` - Added Night Smart Charge constants and PV forecast configuration
  - `config_flow.py` - Added 4-step wizard with PV forecast sensor selection
  - `switch.py` - Added night charge enable switch
  - `number.py` - Added 4 new number entities for night charge configuration
  - `solar_surplus.py` - Added night charge detection to skip when active
  - `automations.py` - Added night charge detection to override Smart Blocker
  - `__init__.py` - Initialize Night Smart Charge and pass to other automations
  - `manifest.json` - Version bump to 0.9.0

### v0.8.9 (2025-10-28) - Cleanup and Icon Verification
- **Cleanup:** Removed unused solar production threshold entity
  - Entity `evsc_solar_production_threshold` was not used by any automation since v0.8.6
  - Removed from number.py entity creation
  - Removed constants from const.py (DEFAULT_SOLAR_THRESHOLD, HELPER_SOLAR_THRESHOLD_SUFFIX)
  - Total entity count reduced from 26 to 25
- **Verification:** Confirmed all entities have proper icons assigned
  - All 4 switches have icons
  - All 19 numbers have icons
  - 1 select has icon
  - All 2 sensors have icons
- **Documentation:** Updated README to reflect removed entity and correct entity count
- **Files Modified:**
  - `number.py` - Removed solar threshold entity creation and import
  - `const.py` - Removed unused solar threshold constants
  - `manifest.json` - Version bumped to 0.8.9
  - `README.md` - Updated entity count (25) and removed solar threshold documentation

### v0.8.8 (2025-10-28) - Custom Logo and Branding
- **Visual Enhancement:** Added custom logo and branding for the integration
  - Created stylish black/gray logo with solar energy symbolism
  - Designed flat, modern icon featuring EV charger, solar rays, and lightning bolt
  - Added logo with "EV SMART CHARGER" text and tagline
- **Assets Created:**
  - `icons/icon.png` (256x256) - Integration icon
  - `icons/icon@2x.png` (512x512) - High-resolution icon
  - `icons/logo.png` (512x256) - Integration logo with text
  - `icons/logo@2x.png` (1024x512) - High-resolution logo
  - Source SVG files included for future modifications
- **Appearance:** Logo now appears in:
  - Home Assistant Devices & Services integration card
  - Device cards when viewing integration devices
  - HACS integration listing
- **Files Modified:**
  - `manifest.json` - Version bumped to 0.8.8
  - `README.md` - Updated version
  - New directory: `icons/` with all branding assets

### v0.8.7 (2025-10-28) - Separate Daily Home Battery Targets
- **Feature:** Split home battery SOC configuration into two independent systems
  - **Battery Support feature** now uses `number.evsc_home_battery_min_soc` (minimum safety threshold, default 20%)
  - **Priority Balancer** now uses 7 new daily targets: `number.evsc_home_min_soc_[day]` (Monday-Sunday, default 50%)
- **New Entities:** Added 7 home battery daily target number helpers (total entity count: 26)
  - `evsc_home_min_soc_monday` through `evsc_home_min_soc_sunday`
  - Each configurable 0-100% in 5% steps
  - Allows different home battery charging goals for each day
- **Priority Balancer Enhancement:** Now reads today's home battery target from appropriate daily entity
  - More flexibility in daily energy management
  - Can prioritize home battery differently on weekdays vs weekends
- **Conceptual Clarity:**
  - Battery Support: "Don't discharge home battery below X%" (safety threshold)
  - Priority Balancer: "Charge home battery to X% today" (daily target)
- **Files Modified:**
  - `number.py` - Added 7 new home battery daily target entities
  - `solar_surplus.py` - Updated Priority Balancer to use daily home battery targets
  - `manifest.json` - Version bumped to 0.8.7
  - `README.md` - Updated documentation with new entities

### v0.8.6 (2025-10-28) - Smart Charger Blocker Simplification
- **Simplification:** Removed solar threshold condition from Smart Charger Blocker
  - Now ONLY blocks charging during nighttime (after sunset, before sunrise)
  - Removed solar production threshold check entirely
  - Simplified blocking logic for more predictable behavior
  - Removed `_is_solar_below_threshold()` method
  - Removed `_solar_threshold_entity` helper entity requirement
  - Removed CONF_FV_PRODUCTION import (no longer needed)
- **Impact:** Smart Charger Blocker is now easier to understand and more consistent
- **Migration:** Users can still use Solar Production Threshold number helper for other automations, but it no longer affects Smart Charger Blocker
- **Files Modified:**
  - `automations.py` - Simplified blocking logic and removed solar threshold checks
  - `manifest.json` - Version bumped to 0.8.6
  - `README.md` - Updated documentation to reflect simplified behavior

### v0.8.5 (2025-10-27) - Complete Entity Registration Fix
- **Critical Fix:** Removed `_attr_has_entity_name = True` that was causing entity ID mismatch
  - **Root Cause:** With `_attr_has_entity_name = True`, HA generated entity IDs as `switch.evsc_forza_ricarica` (no entry_id)
  - **Root Cause:** `_find_entity_by_suffix()` searched ALL entities in registry, not just our integration's entities
  - **Impact:** Helper entities not found even though they existed in registry
- **Solution 1:** Removed `_attr_has_entity_name = True` from all entity classes
  - Entities now have standard IDs: `switch.ev_smart_charger_{entry_id}_evsc_forza_ricarica`
  - Entity IDs are unique per integration instance
  - Compatible with Home Assistant's default entity_id generation
- **Solution 2:** Updated `_find_entity_by_suffix()` to filter by `config_entry_id`
  - Searches only entities belonging to THIS integration instance
  - Checks `unique_id` instead of `entity_id` (more reliable)
  - Prevents finding entities from other integrations or multiple instances
- **Files Modified:**
  - `switch.py`, `number.py`, `select.py`, `sensor.py` - Removed `_attr_has_entity_name = True`
  - `automations.py` - Updated entity search to filter by config_entry_id and check unique_id
  - `solar_surplus.py` - Updated entity search to filter by config_entry_id and check unique_id
- **Impact:** Users on v0.8.2, v0.8.3, v0.8.4 experienced entity lookup failures
- **Resolution:** Users must upgrade to v0.8.5 and restart Home Assistant

### v0.8.4 (2025-10-27) - Broken - Helper Entity Lookup Fix
- **Critical Fix:** Helper entities not found during startup (v0.8.3 regression)
  - **Root Cause:** `_find_entity_by_suffix()` searched state machine before entities wrote initial state
  - **Impact:** Both Smart Charger Blocker and Solar Surplus failed to initialize
  - Errors: "Helper entity with suffix '...' not found" and "Cannot set up Smart Charger Blocker"
- **Solution:** Use Entity Registry instead of State Machine for entity lookup
  - Entity Registry contains entities immediately after registration
  - State Machine only gets entities after they write their first state
  - Added fallback to state machine if registry lookup fails
  - Works reliably regardless of timing
- **Files Modified:**
  - `automations.py` - Updated `_find_entity_by_suffix()` to use entity registry
  - `solar_surplus.py` - Updated `_find_entity_by_suffix()` to use entity registry
  - Added import for `entity_registry as er` in both files
- **Enhanced Logging:** Shows whether entity was found in registry or state machine
- **Impact:** Users on v0.8.3 experienced failed initialization
- **Resolution:** Users must upgrade to v0.8.4 and restart Home Assistant

### v0.8.3 (2025-10-27) - Broken - Smart Charger Blocker Attempted Fix
- **Critical Fix:** Smart Charger Blocker was not working - now fully functional
  - **Root Cause:** Helper entities were never initialized (defined but not set in async_setup)
  - **Root Cause:** Only listened to status changes, not charger switch changes
  - **Root Cause:** No immediate check when blocker was enabled with charger already on
- **New Event Listeners:**
  - Now monitors charger **switch state** changes (off → on)
  - Now monitors charger **status** changes (any → charger_charging)
  - Now monitors **blocker enable switch** (checks immediately if charger already on)
- **Immediate Blocking:** Blocker now triggers in all these scenarios:
  - ✅ Charger switch turns ON while blocker is enabled
  - ✅ Charger status changes to "charging" while blocker is enabled
  - ✅ Blocker is enabled while charger is already ON
- **Enhanced Logging:**
  - Shows which trigger activated the blocker (switch ON, status change, blocker enabled)
  - Logs helper entity discovery on startup
  - Detailed blocking condition checks with reasons
- **Unified Logic:** Created `_check_and_block_if_needed()` method to avoid code duplication
- **Impact:** Users on v0.8.0-v0.8.2 experienced non-functional Smart Charger Blocker
- **Resolution:** Users must upgrade to v0.8.3 and restart Home Assistant

### v0.8.2 (2025-10-27) - Entity Registration Fix
- **Critical Fix:** Corrected entity registration pattern for Home Assistant compatibility
  - Removed incorrect `self.entity_id` assignments that conflicted with HA's entity registry
  - Added `_attr_has_entity_name = True` to all entity classes (modern HA pattern)
  - Allows Home Assistant to generate entity_id automatically from unique_id
  - Fixes "NO ENTITIES CREATED" error that persisted in v0.8.1
- **Enhanced Entity Detection:**
  - Now checks both Entity Registry and State Machine for comprehensive verification
  - Improved logging shows registration status in both systems
  - Better diagnostics when entities are registered but not yet in state machine
  - Reduced wait time from 3s to 2s (sufficient with proper registry checks)
- **Lifecycle Logging:**
  - Added `async_added_to_hass()` logging for all entity types
  - Shows entity_id and unique_id when each entity successfully registers
  - Helps debug entity creation issues in real-time
- **Root Cause:** v0.8.1's approach of setting `entity_id` directly conflicted with HA's entity registry system
- **Impact:** Users on v0.8.0 and v0.8.1 experienced non-functional integration due to entity creation failure
- **Resolution:** Users must upgrade to v0.8.2 and restart Home Assistant

### v0.8.1 (2025-10-27) - Broken - Do Not Use
- **Critical Fix:** Entity registration issue causing "NO ENTITIES CREATED" error
  - Added explicit `entity_id` property to all entity classes (switch, number, select, sensor)
  - Ensures proper registration in Home Assistant state machine
  - Fixes Priority Balancer and all other features not working
- **Enhancement:** Reinforced Priority Balancer engine
  - Added explicit logging when reading helper values (home battery min SOC, EV daily targets)
  - Confirms fresh values are read from state machine at every check
  - Added debug logging to trace priority decision-making
  - Verifies that helper value changes (like home battery min SOC) are detected immediately at next check
- **Logging Improvements:**
  - Added `_LOGGER.debug()` for detailed value reading traces
  - Added `_LOGGER.info()` for priority decisions
  - Added `_LOGGER.warning()` for missing or invalid helper values
  - All priority calculations now fully traceable in logs
- **Issue:** v0.8.0 entities were not being created due to missing entity_id registration
- **Impact:** All users upgrading from v0.7.0 to v0.8.0 experienced broken integration
- **Resolution:** Users must upgrade to v0.8.1 and restart Home Assistant

### v0.8.0 (2025-10-27) - Broken - Do Not Use
- **Major Feature:** Priority Daily Charging Balancer
- Intelligent EV vs. Home Battery charging prioritization based on daily SOC targets
- Configure daily EV SOC targets for each day of week (Monday-Sunday)
- Reuses existing home battery minimum SOC as daily target for all days
- Three priority states:
  - **Priority = EV**: EV charges first until reaching daily target
  - **Priority = Home**: EV stops completely, home battery charges first
  - **Priority = EV_Free**: Both targets met, opportunistic EV charging
- Comprehensive fallback mechanisms for sensor failures
  - Missing/invalid EV SOC → defaults to Priority = EV
  - Missing/invalid Home SOC → defaults to Priority = EV
  - Out of range values → defaults to Priority = EV
- Integration with existing Battery Support feature
  - Battery Support only activates when Priority = EV or EV_Free
  - When Priority = Home, Battery Support is ignored
- New priority state sensor with detailed attributes
  - Current/target SOCs for both devices
  - Decision reason and day of week
  - Real-time priority tracking
- Enhanced logging for priority decisions
- Added 1 new switch: Priority Balancer Enable
- Added 7 new numbers: EV Min SOC for each day (Monday-Sunday)
- Added 1 new sensor: Priority Daily State
- Total integration entities: 19 (4 switches, 13 numbers, 1 select, 2 sensors)

### v0.7.0 (2025-01-XX)
- **Major Enhancement:** Solar Surplus algorithm v2 with three major improvements
- **Smooth Charge-Speed Reduction:** Gradual step-down instead of instant drops (20A → 16A → 13A...)
  - Reduces stress on charger and solar inverter
  - Prevents oscillations in charging cycle
  - Next check interval determines if further reduction needed
- **Fluctuation Management:** Solar swing protection with configurable delays
  - Grid Import Delay (0-120s, default 30s): Only react after sustained grid import
  - Surplus Drop Delay (0-120s, default 30s): Wait before reducing on surplus drop
  - Prevents overreaction to clouds/consumption spikes
- **Home Battery Support:** Optional use of home battery energy
  - New switch: "Use Home Battery" to enable feature
  - New number: "Home Battery Min SOC" (0-100%, default 20%)
  - Fixed 16A fallback when battery available and surplus drops
  - Allows battery to bridge gap during temporary surplus reductions
- **Enhanced Logging:** Every decision logged with comprehensive reasoning
  - Current measurements displayed at each check
  - Configuration values shown
  - Decision explanations for debugging
- Added 3 new number helpers: Grid Import Delay, Surplus Drop Delay, Home Battery Min SOC
- Added 1 new switch helper: Use Home Battery

### v0.6.1 (2025-01-XX)
- **UI Enhancement:** Dramatically improved configuration flow experience
- Added progress indicators to all setup steps (Step X/Y)
- Rich, detailed descriptions for every entity selector
- Visual improvements with emojis and better formatting
- Comprehensive help text explaining what each sensor does
- Added usage examples for common entity naming patterns
- Better error messaging and field validation feedback
- Enhanced reconfiguration (options) flow with same improvements

### v0.6.0 (2025-01-XX)
- **Major Feature:** Solar Surplus Charging Profile
- Smart charging using only excess solar energy
- Automatic amperage adjustment based on available surplus
- Grid import protection - never import from grid while charging
- Safe amperage decrease sequence (stop → wait → adjust → start)
- Configurable check interval (1-60 minutes)
- Configurable grid import threshold
- New helper entities: Charging Profile selector, Check Interval, Grid Import Threshold
- Robust charger status checking (works with charger_charging, charger_end, charger_wait)
- European 230V standard with amperage steps: 6, 8, 10, 13, 16, 20, 24, 32A

### v0.5.0 (2025-01-XX)
- **Major Feature:** Automatic helper entity creation
- Helper entities (switches/numbers) now created automatically by the integration
- No more manual helper creation required
- Entities persist across restarts and retain their state
- Dynamic entity discovery in automations
- Simplified setup process

### v0.4.2 (2025-01-XX)
- **Fixed:** Critical integration loading issue
- Simplified helper creation to manual process
- Added prominent log messages with setup instructions
- Integration now guaranteed to load successfully

### v0.4.0 (2025-01-XX)
- **New Feature:** Smart Charger Blocker automation
- Auto-created helper entities
- Global kill switch (Forza Ricarica)
- Persistent notifications when charging blocked
- Nighttime and solar-based charging prevention

### v0.3.0 (2025-01-XX)
- Enhanced configuration UI with 3-step flow
- All entity fields now required
- Added detailed field descriptions
- Improved validation

### v0.2.0 (2025-01-XX)
- Entity selection configuration panel
- Two-step setup flow
- Options flow for reconfiguration

### v0.1.0 (2025-01-XX)
- Initial release
- Basic integration structure

---

## Support

- **Issues:** [GitHub Issues](https://github.com/antbald/ha-ev-smart-charger/issues)
- **Documentation:** [Troubleshooting Guide](TROUBLESHOOTING.md)

---

## License

MIT License - See [LICENSE](LICENSE) file for details

---

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

---

## Credits

Developed with ❤️ using [Claude Code](https://claude.com/claude-code)

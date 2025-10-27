# EV Smart Charger

A Home Assistant integration for intelligent EV charging control based on solar production, time of day, and battery levels.

## Current Version: 0.8.0

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

### 🚫 Smart Charger Blocker (v0.4.0+)
Automatically prevents EV charging during nighttime or when solar production is insufficient.

**How it works:**
- Monitors your charger status in real-time
- Blocks charging when:
  - Current time is after sunset AND before sunrise, OR
  - Solar production is below the configured threshold (default: 50W)
- Sends persistent notifications when charging is blocked
- Fully configurable via helper entities

**Controls:**
- `switch.evsc_forza_ricarica` - **Global Kill Switch**: When ON, disables ALL smart features (manual mode)
- `switch.evsc_smart_charger_blocker_enabled` - Enable/disable Smart Charger Blocker
- `number.evsc_solar_production_threshold` - Minimum solar production (W) to allow charging

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
3. Follow the 3-step setup wizard:
   - **Step 1:** Name your integration
   - **Step 2:** Configure charger entities (switch, current, status)
   - **Step 3:** Configure monitoring sensors (SOC car/home, solar, consumption)

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

### Helper Entities (Auto-Created)

The integration **automatically creates 19 helper entities** when you add it:

#### Switches (4)

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

#### Numbers (13)

**1. EVSC Solar Production Threshold**
- **Entity ID:** `number.ev_smart_charger_<entry_id>_evsc_solar_production_threshold`
- **Purpose:** Minimum solar production (W) required to allow charging
- **Default:** 50W | **Range:** 0-1000W (step: 10W)
- **Icon:** `mdi:solar-power-variant`

**2. EVSC Check Interval** *(v0.6.0+)*
- **Entity ID:** `number.ev_smart_charger_<entry_id>_evsc_check_interval`
- **Purpose:** How often Solar Surplus recalculates charging power (minutes)
- **Default:** 1 min | **Range:** 1-60 min (step: 1 min)
- **Icon:** `mdi:timer-outline`

**3. EVSC Grid Import Threshold** *(v0.6.0+)*
- **Entity ID:** `number.ev_smart_charger_<entry_id>_evsc_grid_import_threshold`
- **Purpose:** Maximum allowed grid import (W) before reducing charging
- **Default:** 50W | **Range:** 0-1000W (step: 10W)
- **Icon:** `mdi:transmission-tower`

**4. EVSC Grid Import Delay** *(v0.7.0+)*
- **Entity ID:** `number.ev_smart_charger_<entry_id>_evsc_grid_import_delay`
- **Purpose:** Delay (seconds) before reacting to grid import exceeding threshold
- **Default:** 30s | **Range:** 0-120s (step: 5s)
- **Icon:** `mdi:timer-sand`
- **Use:** Prevents overreaction to brief grid import spikes

**5. EVSC Surplus Drop Delay** *(v0.7.0+)*
- **Entity ID:** `number.ev_smart_charger_<entry_id>_evsc_surplus_drop_delay`
- **Purpose:** Delay (seconds) before reducing charging when surplus drops
- **Default:** 30s | **Range:** 0-120s (step: 5s)
- **Icon:** `mdi:timer-sand`
- **Use:** Prevents overreaction to temporary cloud cover or consumption spikes

**6. EVSC Home Battery Min SOC** *(v0.7.0+)*
- **Entity ID:** `number.ev_smart_charger_<entry_id>_evsc_home_battery_min_soc`
- **Purpose:** Minimum home battery charge level (%) to enable battery support / daily target for Priority Balancer
- **Default:** 20% | **Range:** 0-100% (step: 5%)
- **Icon:** `mdi:battery-50`
- **Use:** Protects home battery from over-discharge while supporting EV charging / Used as home battery target for Priority Balancer

**7-13. EVSC EV Min SOC [Day]** *(v0.8.0+)*
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

### Dashboard Example

Add these entities to your Lovelace dashboard for easy control:

```yaml
type: entities
title: EV Smart Charger
entities:
  # Global Controls
  - entity: switch.ev_smart_charger_YOUR_ENTRY_ID_evsc_forza_ricarica
    name: 🔴 Forza Ricarica (Override All)

  # Charging Profile (v0.6.0+)
  - entity: select.ev_smart_charger_YOUR_ENTRY_ID_evsc_charging_profile
    name: ⚡ Charging Profile

  # Solar Surplus Settings (v0.6.0+)
  - entity: number.ev_smart_charger_YOUR_ENTRY_ID_evsc_check_interval
    name: ⏱️ Check Interval (min)
  - entity: number.ev_smart_charger_YOUR_ENTRY_ID_evsc_grid_import_threshold
    name: 🔌 Max Grid Import (W)

  # Smart Charger Blocker
  - entity: switch.ev_smart_charger_YOUR_ENTRY_ID_evsc_smart_charger_blocker_enabled
    name: 🚫 Smart Charger Blocker
  - entity: number.ev_smart_charger_YOUR_ENTRY_ID_evsc_solar_production_threshold
    name: ☀️ Solar Threshold (W)
```

**Tip:** Find your actual entity IDs by searching for "evsc" in Developer Tools → States.

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
Check: Is it nighttime OR solar < threshold?
  → YES: BLOCK charging + Send notification
  → NO: Allow charging
```

### Typical Scenarios

**Scenario 1: Daytime with Good Solar**
- Solar production: 800W
- Time: 2:00 PM
- Result: ✅ Charging allowed

**Scenario 2: Nighttime**
- Solar production: 0W
- Time: 11:00 PM
- Result: 🚫 Charging blocked

**Scenario 3: Cloudy Day**
- Solar production: 30W (below 50W threshold)
- Time: 12:00 PM
- Result: 🚫 Charging blocked

**Scenario 4: Manual Override**
- "Forza Ricarica" is ON
- Any time, any solar production
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

### v0.8.0 (2025-01-XX) - Current
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

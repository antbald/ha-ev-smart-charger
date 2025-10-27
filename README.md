# EV Smart Charger

A Home Assistant integration for intelligent EV charging control based on solar production, time of day, and battery levels.

## Current Version: 0.6.0

[![GitHub Release](https://img.shields.io/github/v/release/antbald/ha-ev-smart-charger)](https://github.com/antbald/ha-ev-smart-charger/releases)
[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/custom-components/hacs)

---

## Features

### ⚡ Charging Profiles (v0.6.0+)

Choose from multiple intelligent charging modes via the **Charging Profile** selector:

#### 1. Manual Mode
Standard charging without automation - full manual control.

#### 2. Solar Surplus Mode ☀️ (v0.6.0+)
**Charge your EV using only excess solar energy - never import from the grid!**

**How it works:**
- Calculates available surplus: `Solar Production - Home Consumption`
- Automatically adjusts charging amperage based on available surplus
- Uses European 230V standard to convert watts to amps
- Adjusts every X minutes (configurable, default: 1 minute)
- **Grid Import Protection:** Monitors grid import and reduces charging if importing power
- Always starts with minimum 6A when surplus is available

**Smart Amperage Adjustment:**
- **Increasing:** Instant adjustment when more surplus is available
- **Decreasing:** Safe sequence to prevent charger issues:
  1. Stop charger
  2. Wait 5 seconds
  3. Set new amperage
  4. Wait 1 second
  5. Restart charger

**Available Amperage Steps:** 6A, 8A, 10A, 13A, 16A, 20A, 24A, 32A

**Controls:**
- `select.evsc_charging_profile` - Choose charging mode
- `number.evsc_check_interval` - How often to recalculate (1-60 minutes)
- `number.evsc_grid_import_threshold` - Max grid import before reducing charge (W)

**Requirements:**
- Charger must be in status: `charger_charging`, `charger_end`, or `charger_wait`
- Does NOT activate when charger status is `charger_free` (not connected)

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

The integration **automatically creates 7 helper entities** when you add it:

#### Switches (2)

**1. EVSC Forza Ricarica**
- **Entity ID:** `switch.ev_smart_charger_<entry_id>_evsc_forza_ricarica`
- **Purpose:** Global kill switch - When ON, all smart features are disabled
- **Icon:** `mdi:power`

**2. EVSC Smart Charger Blocker**
- **Entity ID:** `switch.ev_smart_charger_<entry_id>_evsc_smart_charger_blocker_enabled`
- **Purpose:** Enable/disable the Smart Charger Blocker feature
- **Icon:** `mdi:solar-power`

#### Numbers (3)

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

#### Selects (1)

**1. EVSC Charging Profile** *(v0.6.0+)*
- **Entity ID:** `select.ev_smart_charger_<entry_id>_evsc_charging_profile`
- **Purpose:** Choose charging mode (manual, solar_surplus, charge_target, cheapest)
- **Default:** manual
- **Icon:** `mdi:ev-station`

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

### v0.6.0 (2025-01-XX) - Current
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

# EV Smart Charger

A Home Assistant integration for intelligent EV charging control based on solar production, time of day, and battery levels.

## Current Version: 0.4.2

[![GitHub Release](https://img.shields.io/github/v/release/antbald/ha-ev-smart-charger)](https://github.com/antbald/ha-ev-smart-charger/releases)
[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/custom-components/hacs)

---

## Features

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
- `input_boolean.evsc_forza_ricarica` - **Global Kill Switch**: When ON, disables ALL smart features (manual mode)
- `input_boolean.evsc_smart_charger_blocker_enabled` - Enable/disable Smart Charger Blocker
- `input_number.evsc_solar_production_threshold` - Minimum solar production (W) to allow charging

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

### Helper Entities Setup

After initial configuration, **create these 3 helper entities manually**:

1. Go to **Settings → Devices & Services → Helpers**
2. Click **"+ CREATE HELPER"**
3. Create these helpers:

#### Helper 1: EVSC Forza Ricarica
- **Type:** Toggle
- **Name:** `EVSC Forza Ricarica`
- **Entity ID:** `input_boolean.evsc_forza_ricarica`
- **Icon:** `mdi:power`
- **Purpose:** Global kill switch - When ON, all smart features are disabled

#### Helper 2: EVSC Smart Charger Blocker
- **Type:** Toggle
- **Name:** `EVSC Smart Charger Blocker`
- **Entity ID:** `input_boolean.evsc_smart_charger_blocker_enabled`
- **Icon:** `mdi:solar-power`
- **Purpose:** Enable/disable the Smart Charger Blocker feature

#### Helper 3: EVSC Solar Production Threshold
- **Type:** Number
- **Name:** `EVSC Solar Production Threshold`
- **Entity ID:** `input_number.evsc_solar_production_threshold`
- **Minimum:** `0`
- **Maximum:** `1000`
- **Step:** `10`
- **Unit:** `W`
- **Icon:** `mdi:solar-power-variant`
- **Purpose:** Minimum solar production required to allow charging

4. **Restart Home Assistant** after creating helpers

---

## Usage

### Dashboard Example

Add these entities to your Lovelace dashboard for easy control:

```yaml
type: entities
title: EV Smart Charger
entities:
  - entity: input_boolean.evsc_forza_ricarica
    name: 🔴 Forza Ricarica (Override All)
  - entity: input_boolean.evsc_smart_charger_blocker_enabled
    name: 🚫 Smart Charger Blocker
  - entity: input_number.evsc_solar_production_threshold
    name: ☀️ Solar Threshold (W)
```

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

### v0.4.2 (2025-01-XX) - Current
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

# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a **Home Assistant custom integration** for intelligent EV charging control. It manages EV charger automation based on solar production, time of day, battery levels, and grid import protection.

**Domain:** `ev_smart_charger`
**Current Version:** 0.6.6
**Installation:** HACS custom repository or manual installation to `custom_components/ev_smart_charger`

## Development Commands

Since this is a Home Assistant custom integration, there are no build/test commands. Development workflow:

1. **Testing changes:**
   - Copy integration to Home Assistant instance: `cp -r custom_components/ev_smart_charger /path/to/homeassistant/custom_components/`
   - Restart Home Assistant
   - Check logs: Settings → System → Logs (search for "evsc")

2. **Enable debug logging** (add to `configuration.yaml`):
   ```yaml
   logger:
     default: info
     logs:
       custom_components.ev_smart_charger: debug
   ```

3. **Version updates:**
   - Update version in `custom_components/ev_smart_charger/manifest.json`
   - Update changelog in `README.md`
   - Tag release: `git tag v0.X.X && git push origin v0.X.X`

## Architecture

### Core Components

**Entry Point (`__init__.py`):**
- Sets up platforms: `["switch", "number", "select", "sensor"]`
- Creates helper entities via platform setup
- Initializes two automation systems: Smart Charger Blocker and Solar Surplus
- Waits 3 seconds after platform setup for entity registration before automation setup

**Configuration Flow (`config_flow.py`):**
- 3-step wizard: Name → Charger Entities → Monitoring Sensors
- User maps existing HA entities to integration roles
- Options flow allows reconfiguration

### Helper Entities (Auto-Created)

The integration creates 7 helper entities automatically via platform files:

**Switches (`switch.py`):**
- `evsc_forza_ricarica` - Global kill switch (disables all automations)
- `evsc_smart_charger_blocker_enabled` - Enable/disable Smart Charger Blocker

**Numbers (`number.py`):**
- `evsc_solar_production_threshold` - Min solar (W) to allow charging (0-1000W)
- `evsc_check_interval` - Solar Surplus recalculation interval (1-60 min)
- `evsc_grid_import_threshold` - Max grid import (W) before reducing charge (0-1000W)

**Selects (`select.py`):**
- `evsc_charging_profile` - Charging mode selector (manual, solar_surplus, charge_target, cheapest)

**Sensors (`sensor.py`):**
- Currently creates diagnostic sensors if needed

All helper entities use `RestoreEntity` to persist state across restarts.

### Automation Systems

#### 1. Smart Charger Blocker (`automations.py`)

**Purpose:** Prevents charging during nighttime or when solar production is insufficient.

**Trigger:** Charger status changes to `charger_charging`

**Logic:**
1. Check if `evsc_forza_ricarica` is ON → allow charging (override)
2. Check if `evsc_smart_charger_blocker_enabled` is OFF → allow charging
3. Calculate if nighttime (after sunset, before sunrise)
4. Check if solar production < threshold
5. If either condition true → turn off charger + send notification

**Key Methods:**
- `_async_charger_status_changed()` - Event handler
- `_should_block_charging()` - Decision logic
- `_is_nighttime()` - Uses Home Assistant's astral events
- `_is_solar_below_threshold()` - Compares sensor value to threshold
- `_block_charging()` - Turns off charger, sends persistent notification

#### 2. Solar Surplus Automation (`solar_surplus.py`)

**Purpose:** Charge EV using only excess solar energy without grid import.

**Trigger:** Periodic timer (configurable interval, default 1 minute)

**Logic:**
1. Check if `evsc_forza_ricarica` is ON → skip (override)
2. Check if profile is `solar_surplus` → skip if not
3. Check charger status is NOT `charger_free` → skip if unplugged
4. Calculate surplus: `Solar Production - Home Consumption`
5. Check if grid import > threshold → reduce amperage if true
6. Find target amperage from available steps: [6, 8, 10, 13, 16, 20, 24, 32]A
7. Adjust charging:
   - **Increase:** Instant adjustment
   - **Decrease:** Stop charger → wait 5s → set amperage → wait 1s → start charger

**Key Methods:**
- `async_setup()` - Discovers helper entities, starts timer
- `_async_periodic_check()` - Main logic loop (runs every X minutes)
- `_find_target_amperage()` - Converts surplus watts to amps (using 230V)
- `_set_amperage()` - Instant increase
- `_adjust_amperage_down()` - Safe decrease sequence

**European Standard:** Uses 230V for watt-to-amp conversion

### Entity Discovery Pattern

Both automation systems use dynamic entity discovery:
```python
def _find_entity_by_suffix(self, suffix: str) -> str | None:
    """Find an entity by its suffix."""
    for entity_id in self.hass.states.async_entity_ids():
        if entity_id.endswith(suffix):
            return entity_id
    return None
```

This allows automations to find helper entities regardless of entry_id.

### Configuration Constants (`const.py`)

**User-Mapped Entities (from config flow):**
- `CONF_EV_CHARGER_SWITCH` - Switch to control charger on/off
- `CONF_EV_CHARGER_CURRENT` - Number/Select for amperage (6-32A)
- `CONF_EV_CHARGER_STATUS` - Sensor showing charger state
- `CONF_SOC_CAR` - EV battery level (%)
- `CONF_SOC_HOME` - Home battery level (%)
- `CONF_FV_PRODUCTION` - Solar production (W)
- `CONF_HOME_CONSUMPTION` - Home power consumption (W)
- `CONF_GRID_IMPORT` - Grid import (W, positive = importing)

**Charger Status Values:**
- `charger_charging` - Actively charging
- `charger_free` - Not connected
- `charger_end` - Charging completed
- `charger_wait` - Connected but not charging

**Amperage Levels:** `[6, 8, 10, 13, 16, 20, 24, 32]` - European standard charging rates

## Common Development Patterns

### Adding a New Helper Entity

1. Add constant to `const.py`:
   ```python
   HELPER_NEW_FEATURE_SUFFIX = "evsc_new_feature"
   DEFAULT_NEW_FEATURE_VALUE = 100
   ```

2. Create entity in appropriate platform file (`switch.py`, `number.py`, or `select.py`):
   ```python
   entities.append(
       EVSCSwitch(  # or EVSCNumber, EVSCSelect
           entry.entry_id,
           "evsc_new_feature",
           "EVSC New Feature",
           "mdi:icon-name",
       )
   )
   ```

3. Entity ID will be: `{platform}.ev_smart_charger_{entry_id}_evsc_new_feature`

### Adding a New Charging Profile

1. Add profile constant to `const.py`:
   ```python
   PROFILE_NEW_MODE = "new_mode"
   CHARGING_PROFILES = [..., PROFILE_NEW_MODE]
   ```

2. Create automation class in new file (like `solar_surplus.py`):
   ```python
   class NewModeAutomation:
       def __init__(self, hass, entry_id, config): ...
       async def async_setup(self): ...
       async def async_remove(self): ...
   ```

3. Register in `__init__.py`:
   ```python
   new_mode = NewModeAutomation(hass, entry.entry_id, entry.data)
   await new_mode.async_setup()
   hass.data[DOMAIN][entry.entry_id]["new_mode"] = new_mode
   ```

### Accessing User-Configured Entities

Always get from config:
```python
charger_switch = self.config.get(CONF_EV_CHARGER_SWITCH)
charger_state = self.hass.states.get(charger_switch)
```

### Calling Services

```python
# Turn on/off switch
await self.hass.services.async_call(
    "switch",
    "turn_on",  # or "turn_off"
    {"entity_id": self._charger_switch},
    blocking=True,
)

# Set number value
await self.hass.services.async_call(
    "number",
    "set_value",
    {"entity_id": self._charger_current, "value": 16},
    blocking=True,
)
```

## Important Notes

- **3-second delay:** After platform setup, wait 3 seconds for entity registration (`__init__.py:45`)
- **Blocking vs Non-Blocking:** Use `blocking=True` for critical service calls to ensure they complete
- **State Restoration:** All helper entities extend `RestoreEntity` to persist across restarts
- **Entity Naming:** Format is `{domain}.ev_smart_charger_{entry_id}_{suffix}`
- **Logging:** Use emoji prefixes for key events (🔄 processing, ✅ success, ❌ error, ⚠️ warning)
- **Grid Import:** Positive values = importing from grid, negative = exporting to grid
- **Safe Amperage Decrease:** Always use stop → wait → adjust → wait → start sequence to prevent charger issues

## Debugging Entity Creation Issues

If helper entities don't appear:

1. Check platform registration in `const.py` PLATFORMS list
2. Verify `async_add_entities()` is called in platform files
3. Look for entity creation logs (search for "Created X EVSC")
4. Check entity registry: Developer Tools → States (search for "evsc")
5. Entity IDs contain entry_id, find via: `hass.states.async_entity_ids()`
- update CLAUDE.md when features are added or removed
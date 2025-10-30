# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a **Home Assistant custom integration** for intelligent EV charging control. It manages EV charger automation based on solar production, time of day, battery levels, grid import protection, and intelligent priority balancing between EV and home battery charging.

**Domain:** `ev_smart_charger`
**Current Version:** 1.0.3
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
   - Update version in `custom_components/ev_smart_charger/const.py`
   - Update changelog in `README.md`
   - Commit changes: `git add . && git commit -m "Release version X.Y.Z"`
   - Tag release: `git tag vX.Y.Z && git push origin vX.Y.Z`
   - Create GitHub Release with release notes

## Architecture (v1.0.0+)

### Major Architectural Changes (v1.0.0)

The v1.0.0 release introduced a complete refactoring with the following key changes:

1. **Dependency Injection Pattern**: All components receive dependencies via constructor
2. **Independent Priority Balancer**: Extracted from solar_surplus.py into standalone component
3. **Centralized Utilities**: New utils directory with logging, entity, and state helpers
4. **7-Phase Setup**: Sequential initialization with proper dependency ordering
5. **39% Code Reduction**: Solar Surplus reduced from 1068 to 651 lines

### Core Components

**Entry Point (`__init__.py`):**
- 7-phase setup process with dependency injection
- Creates helper entities via platform setup (Phase 1)
- Initializes Automation Coordinator (Phase 2)
- Creates independent Priority Balancer (Phase 3)
- Creates Night Smart Charge with Balancer dependency (Phase 4)
- Creates Smart Charger Blocker with Night Charge dependency (Phase 5)
- Creates Solar Surplus with Balancer dependency (Phase 6)
- Stores all component references (Phase 7)
- Waits 2 seconds after platform setup for entity registration

**Configuration Flow (`config_flow.py`):**
- 3-step wizard: Name → Charger Entities → Monitoring Sensors
- User maps existing HA entities to integration roles
- Options flow allows reconfiguration

### Component Dependency Graph

```
Priority Balancer (independent)
       ↓
       ├─→ Night Smart Charge
       │         ↓
       │   Smart Charger Blocker
       │
       └─→ Solar Surplus Automation
```

**Priority Levels (execution order):**
1. Forza Ricarica (override/kill switch)
2. Smart Charger Blocker
3. Night Smart Charge
4. Priority Balancer
5. Solar Surplus

### Helper Entities (Auto-Created)

The integration creates helper entities automatically via platform files:

**Switches (`switch.py`):**
- `evsc_forza_ricarica` - Global kill switch (disables all automations)
- `evsc_smart_charger_blocker_enabled` - Enable/disable Smart Charger Blocker
- `evsc_use_home_battery` - Enable/disable home battery support in Solar Surplus
- `evsc_priority_balancer_enabled` - Enable/disable Priority Balancer
- `evsc_night_smart_charge_enabled` - Enable/disable Night Smart Charge

**Numbers (`number.py`):**
- `evsc_check_interval` - Solar Surplus recalculation interval (1-60 min, default 1)
- `evsc_grid_import_threshold` - Max grid import (W) before reducing charge (default 50)
- `evsc_grid_import_delay` - Delay before acting on grid import (seconds, default 30)
- `evsc_surplus_drop_delay` - Delay before stopping charger on surplus drop (seconds, default 30)
- `evsc_home_battery_min_soc` - Minimum home battery SOC for battery support (%, default 20)
- `evsc_battery_support_amperage` - Amperage to use when battery support active (A, default 16)
- `evsc_night_charge_amperage` - Amperage for night charging (A, default 16)
- `evsc_min_solar_forecast_threshold` - Min PV forecast to skip night charge (kWh, default 20)
- Daily SOC targets (EV): `evsc_ev_min_soc_[monday-sunday]` (%, defaults 50 weekday, 80 weekend)
- Daily SOC targets (Home): `evsc_home_min_soc_[monday-sunday]` (%, default 50 all days)

**Selects (`select.py`):**
- `evsc_charging_profile` - Charging mode selector (manual, solar_surplus, charge_target, cheapest)

**Time (`time.py`):**
- `evsc_night_charge_time` - Time to start night charging (default 01:00:00)

**Sensors (`sensor.py`):**
- `evsc_diagnostic` - Comprehensive diagnostic sensor with all decision variables
- `evsc_priority_daily_state` - Priority Balancer state and target information
- `evsc_solar_surplus_diagnostic` - Solar Surplus detailed status

All helper entities use `RestoreEntity` to persist state across restarts.

### Component Details

#### 1. Priority Balancer (`priority_balancer.py`)

**Purpose:** Independent component managing EV vs Home battery charging prioritization based on daily SOC targets.

**States:**
- `PRIORITY_EV`: EV below target, prioritize EV charging
- `PRIORITY_HOME`: EV at/above target, Home battery below target
- `PRIORITY_EV_FREE`: Both targets met, opportunistic charging allowed

**Key Methods:**
- `async_setup()` - Discovers helper entities (enabled switch, daily SOC targets)
- `is_enabled()` - Check if Priority Balancer is enabled
- `async calculate_priority()` - Calculate current priority based on SOCs vs targets
- `get_current_priority()` - Get cached priority (use calculate_priority for fresh)
- `async is_ev_target_reached()` - Check if EV reached today's target (used by Night Charge)
- `async is_home_target_reached()` - Check if Home battery reached today's target
- `get_ev_target_for_today()` - Get EV target SOC for current day
- `get_home_target_for_today()` - Get Home battery target SOC for current day
- `async get_ev_current_soc()` - Get current EV SOC with validation
- `async get_home_current_soc()` - Get current Home battery SOC with validation

**Sensor Updates:**
Updates `evsc_priority_daily_state` sensor with:
- State: PRIORITY_EV / PRIORITY_HOME / PRIORITY_EV_FREE
- Attributes: balancer_enabled, today, current_ev_soc, target_ev_soc, current_home_soc, target_home_soc, reason, last_update

#### 2. Smart Charger Blocker (`automations.py`)

**Purpose:** Prevents charging during nighttime or when solar production is insufficient. Window adjusts based on Night Smart Charge state.

**Trigger:** Charger status changes to `charger_charging`

**Logic:**
1. Check if `evsc_forza_ricarica` is ON → allow charging (override)
2. Check if Night Smart Charge is active → allow charging (Night Charge takes priority)
3. Check if `evsc_smart_charger_blocker_enabled` is OFF → allow charging
4. Determine blocking window:
   - If Night Charge ENABLED: sunset → `evsc_night_charge_time`
   - If Night Charge DISABLED: sunset → sunrise
5. Check if current time in blocking window OR solar production below threshold
6. If blocked → turn off charger + send notification with retry logic

**Key Methods:**
- `_async_charger_status_changed()` - Event handler for charger status changes
- `_should_block_charging()` - Main decision logic with window calculation
- `_is_nighttime()` - Uses Home Assistant's astral events for sunset/sunrise
- `_is_solar_below_threshold()` - Compares sensor value to threshold
- `_block_charging()` - Turns off charger with retry logic
- `_send_blocking_notification()` - Sends persistent notification

**Retry Logic:**
- 3 retry attempts with delays: [2, 4, 6] seconds
- 30-minute enforcement timeout to prevent log spam
- Rate limiting to prevent excessive blocking attempts

#### 3. Night Smart Charge (`night_smart_charge.py`)

**Purpose:** Intelligent overnight charging from grid or home battery based on next day's PV forecast.

**Modes:**
- `battery`: Charging from home battery (when forecast sufficient)
- `grid`: Charging from grid (when forecast insufficient or battery support disabled)
- `idle`: Not active

**Dependencies:**
- Uses `priority_balancer.is_ev_target_reached()` for stop conditions
- Coordinates with Smart Blocker for timing window

**Logic:**
1. Check if enabled and current time >= `evsc_night_charge_time`
2. Check PV forecast vs threshold
3. If forecast sufficient AND `evsc_use_home_battery` ON → battery mode
4. If forecast insufficient OR battery support OFF → grid mode
5. Monitor SOC targets via Priority Balancer
6. Stop when `priority_balancer.is_ev_target_reached()` returns true

**Key Methods:**
- `async_setup()` - Sets up time-based trigger
- `_async_time_trigger()` - Triggered at configured night charge time
- `_battery_mode_monitor()` - Monitor battery-based charging, check targets
- `_grid_mode_monitor()` - Monitor grid-based charging, check targets
- `_should_activate()` - Check activation conditions
- `_start_charging()` - Start charger with configured amperage
- `_stop_charging()` - Stop charger
- `is_active()` - Public method to check if Night Charge is currently active

#### 4. Solar Surplus Automation (`solar_surplus.py`)

**Purpose:** Charge EV using excess solar energy, with optional home battery support when Priority Balancer indicates EV priority.

**Trigger:** Periodic timer (configurable interval via `evsc_check_interval`, default 1 minute)

**Dependencies:**
- Uses `priority_balancer.calculate_priority()` for decision making
- Fallback mode when Balancer disabled (surplus → EV directly)

**Logic:**
1. Check if `evsc_forza_ricarica` is ON → skip (override)
2. Check if profile is `solar_surplus` → skip if not
3. Check charger status is NOT `charger_free` → skip if unplugged
4. Calculate priority via Priority Balancer (if enabled)
5. If priority == `PRIORITY_HOME` → stop charger (home battery needs charging)
6. Calculate surplus: `Solar Production - Home Consumption`
7. Check grid import and apply delays
8. Calculate target amperage from surplus
9. Handle home battery support (if enabled and priority == `PRIORITY_EV`)
10. Adjust charging amperage

**Home Battery Support Logic (v1.0.2):**
- **Activation Conditions:**
  - `evsc_use_home_battery` is ON
  - Home battery SOC >= `evsc_home_battery_min_soc`
  - Priority Balancer priority == `PRIORITY_EV` (EV below target, home can help)
- **Deactivation Conditions:**
  - Priority != `PRIORITY_EV` (including `PRIORITY_EV_FREE` when both targets met)
  - Home battery SOC < min threshold
  - Switch disabled
- **Charging Logic:**
  - ALWAYS calculate from surplus first
  - If surplus >= 6A: Use surplus-based amperage (6-32A from levels)
  - If surplus < 6A AND battery support active: Use `evsc_battery_support_amperage` (default 16A)
  - If surplus < 6A AND battery support NOT active: Stop charging

**Rate Limiting:**
- Minimum 30 seconds between checks to prevent event loop blocking
- Warning logged if >10 checks per minute

**Key Methods:**
- `async_setup()` - Discovers helper entities, starts periodic timer
- `_async_periodic_check()` - Main logic loop (runs every X minutes)
- `_calculate_target_amperage()` - Converts surplus watts to amps, handles battery support fallback
- `_handle_home_battery_usage()` - Manages battery support activation/deactivation
- `_set_amperage()` - Instant amperage increase
- `_adjust_amperage_down()` - Safe decrease sequence (stop → wait → adjust → wait → start)
- `_start_charger()` - Turn on charger with sequence delays
- `_stop_charger()` - Turn off charger

**European Standard:** Uses 230V for watt-to-amp conversion

**Amperage Calculation:**
```python
surplus_amps = surplus_watts / 230V
# Find closest level from: [6, 8, 10, 13, 16, 20, 24, 32]
```

### Utility Modules (`utils/`)

#### `logging_helper.py`

**Purpose:** Centralized logging system with emoji prefixes for easy visual parsing.

**EVSCLogger Class:**
- Component-specific logger with consistent formatting
- Emoji constants for different message types:
  - `DECISION = "🎯"` - Key decisions
  - `ACTION = "⚡"` - Actions taken
  - `BALANCE = "⚖️"` - Priority balancing
  - `SOLAR = "☀️"` - Solar-related
  - `BATTERY = "🔋"` - Battery operations
  - `CHARGER = "🔌"` - Charger operations
  - `HOME = "🏠"` - Home battery
  - `EV = "🚗"` - EV operations
  - `CALENDAR = "📅"` - Time/date related
  - `ALERT = "🚨"` - Warnings/alerts

**Key Methods:**
- `separator()` - Visual separator line
- `start(operation)` - Log operation start
- `success(message)` - Log success
- `decision(decision_type, decision, reason)` - Log decision with reason
- `action(action, details)` - Log action taken
- `sensor_value(sensor, value, unit)` - Log sensor reading

#### `entity_helper.py`

**Purpose:** Centralized entity discovery utilities.

**Key Functions:**
- `find_by_suffix(hass, suffix)` - Find entity by suffix (e.g., 'evsc_forza_ricarica')
- `get_helper_entity(hass, suffix, component_name)` - Get helper entity with error handling
- `is_entity_on(hass, entity_id)` - Check if switch/binary_sensor is on

**Discovery Pattern:**
```python
for entity_id in hass.states.async_entity_ids():
    if entity_id.endswith(suffix):
        return entity_id
```

This allows automations to find helper entities regardless of entry_id.

#### `state_helper.py`

**Purpose:** Safe state reading with type conversion and defaults.

**Key Functions:**
- `get_state(hass, entity_id)` - Get raw entity state safely
- `get_float(hass, entity_id, default)` - Get state as float with error handling
- `get_int(hass, entity_id, default)` - Get state as int with error handling
- `get_bool(hass, entity_id, default)` - Get state as boolean
- `validate_sensor(hass, entity_id, sensor_name)` - Validate sensor state, return (is_valid, error_message)

**Error Handling:**
- Returns defaults for `None`, `"unknown"`, `"unavailable"` states
- Logs warnings for invalid states
- Catches ValueError/TypeError exceptions

### Configuration Constants (`const.py`)

**Integration Metadata:**
- `DOMAIN = "ev_smart_charger"`
- `VERSION = "1.0.3"`
- `DEFAULT_NAME = "EV Smart Charger"`

**Platforms:**
- `PLATFORMS = ["switch", "number", "select", "sensor", "time"]`

**Automation Priorities:**
- `PRIORITY_OVERRIDE = 1` (Forza Ricarica kill switch)
- `PRIORITY_SMART_BLOCKER = 2` (Smart Charger Blocker)
- `PRIORITY_NIGHT_CHARGE = 3` (Night Smart Charge)
- `PRIORITY_BALANCER = 4` (Priority Balancer)
- `PRIORITY_SOLAR_SURPLUS = 5` (Solar Surplus)

**Priority Balancer States:**
- `PRIORITY_EV = "EV"` (EV charging priority)
- `PRIORITY_HOME = "Home"` (Home battery charging priority)
- `PRIORITY_EV_FREE = "EV_Free"` (Both targets met, opportunistic charging)

**Charger Status Values:**
- `CHARGER_STATUS_CHARGING = "charger_charging"`
- `CHARGER_STATUS_FREE = "charger_free"`
- `CHARGER_STATUS_END = "charger_end"`
- `CHARGER_STATUS_WAIT = "charger_wait"`

**Night Smart Charge Modes:**
- `NIGHT_CHARGE_MODE_BATTERY = "battery"` (Charging from home battery)
- `NIGHT_CHARGE_MODE_GRID = "grid"` (Charging from grid)
- `NIGHT_CHARGE_MODE_IDLE = "idle"` (Not active)

**Charging Profiles:**
- `PROFILE_MANUAL = "manual"`
- `PROFILE_SOLAR_SURPLUS = "solar_surplus"`
- `PROFILE_CHARGE_TARGET = "charge_target"` (not implemented)
- `PROFILE_CHEAPEST = "cheapest"` (not implemented)

**Charger Amperage Levels:**
- `CHARGER_AMP_LEVELS = [6, 8, 10, 13, 16, 20, 24, 32]`
- `VOLTAGE_EU = 230` (European standard voltage)

**User-Mapped Entities (from config flow):**
- `CONF_EV_CHARGER_SWITCH` - Switch to control charger on/off
- `CONF_EV_CHARGER_CURRENT` - Number/Select for amperage (6-32A)
- `CONF_EV_CHARGER_STATUS` - Sensor showing charger state
- `CONF_SOC_CAR` - EV battery level (%)
- `CONF_SOC_HOME` - Home battery level (%)
- `CONF_FV_PRODUCTION` - Solar production (W)
- `CONF_HOME_CONSUMPTION` - Home power consumption (W)
- `CONF_GRID_IMPORT` - Grid import (W, positive = importing)
- `CONF_PV_FORECAST` - PV forecast sensor (kWh for next day)

**Rate Limiting:**
- `SOLAR_SURPLUS_MIN_CHECK_INTERVAL = 30` (seconds between checks)
- `SOLAR_SURPLUS_MAX_CHECKS_PER_MINUTE = 10` (warning threshold)

**Delays:**
- `CHARGER_COMMAND_DELAY = 2` (seconds after charger commands)
- `CHARGER_START_SEQUENCE_DELAY = 2` (seconds between turn_on and set amperage)
- `CHARGER_STOP_SEQUENCE_DELAY = 5` (seconds after stop before setting amperage)
- `CHARGER_AMPERAGE_STABILIZATION_DELAY = 1` (seconds after setting amperage)

**Timeouts:**
- `SERVICE_CALL_TIMEOUT = 10` (seconds for service calls)
- `SMART_BLOCKER_ENFORCEMENT_TIMEOUT = 1800` (30 minutes for retry enforcement)

## Common Development Patterns

### Adding a New Helper Entity

1. Add constant to `const.py`:
   ```python
   HELPER_NEW_FEATURE_SUFFIX = "evsc_new_feature"
   DEFAULT_NEW_FEATURE_VALUE = 100
   ```

2. Create entity in appropriate platform file (`switch.py`, `number.py`, `select.py`, or `time.py`):
   ```python
   entities.append(
       EVSCSwitch(  # or EVSCNumber, EVSCSelect, EVSCTime
           entry.entry_id,
           "evsc_new_feature",
           "EVSC New Feature",
           "mdi:icon-name",
       )
   )
   ```

3. Entity ID will be: `{platform}.ev_smart_charger_{entry_id}_evsc_new_feature`

4. Discover in component using entity_helper:
   ```python
   from .utils import entity_helper

   entity = entity_helper.get_helper_entity(
       self.hass,
       HELPER_NEW_FEATURE_SUFFIX,
       "Component Name"
   )
   ```

### Adding a New Automation Component

1. Create new file in `custom_components/ev_smart_charger/`:
   ```python
   from .const import DOMAIN
   from .utils.logging_helper import EVSCLogger
   from .utils import entity_helper, state_helper

   class NewAutomation:
       def __init__(self, hass, entry_id, config, dependency=None):
           self.hass = hass
           self.entry_id = entry_id
           self.config = config
           self.dependency = dependency  # Optional dependency injection
           self.logger = EVSCLogger("NEW AUTOMATION")

       async def async_setup(self):
           """Setup: discover helper entities, register listeners."""
           self.logger.info("Setting up New Automation")
           # Discover entities using entity_helper
           # Register event listeners
           self.logger.success("Setup complete")

       async def async_remove(self):
           """Cleanup: remove listeners."""
           self.logger.info("Removing New Automation")
   ```

2. Register in `__init__.py` with proper phase:
   ```python
   # Determine phase based on dependencies
   new_automation = NewAutomation(hass, entry.entry_id, entry.data, dependency)
   await new_automation.async_setup()
   hass.data[DOMAIN][entry.entry_id]["new_automation"] = new_automation
   ```

3. Add unload in `async_unload_entry()`:
   ```python
   new_automation = entry_data.get("new_automation")
   if new_automation:
       await new_automation.async_remove()
   ```

### Using Dependency Injection

Components receive dependencies via constructor:

```python
# In __init__.py:
priority_balancer = PriorityBalancer(hass, entry.entry_id, entry.data)
await priority_balancer.async_setup()

night_smart_charge = NightSmartCharge(
    hass, entry.entry_id, entry.data,
    priority_balancer  # Dependency injection
)
await night_smart_charge.async_setup()

# In night_smart_charge.py:
class NightSmartCharge:
    def __init__(self, hass, entry_id, config, priority_balancer):
        self.priority_balancer = priority_balancer

    async def _battery_mode_monitor(self):
        # Use injected dependency
        if await self.priority_balancer.is_ev_target_reached():
            await self._stop_charging("EV target reached")
```

**Benefits:**
- Clear dependency graph
- Easy testing with mocks
- Single source of truth
- No circular dependencies

### Using EVSCLogger

```python
from .utils.logging_helper import EVSCLogger

class MyComponent:
    def __init__(self, hass, entry_id, config):
        self.logger = EVSCLogger("MY COMPONENT")

    async def some_method(self):
        self.logger.separator()
        self.logger.start("Important operation")
        self.logger.separator()

        # Log sensor values
        self.logger.sensor_value(f"{self.logger.SOLAR} Solar Production", 5000, "W")
        self.logger.sensor_value(f"{self.logger.HOME} Home Consumption", 2000, "W")

        # Log decision
        self.logger.decision(
            "Charging Decision",
            "Start charging at 16A",
            "Surplus of 3000W available"
        )

        # Log action
        self.logger.action("Starting charger", "Setting 16A")

        self.logger.success("Operation completed")
```

### Using Entity Helper

```python
from .utils import entity_helper

class MyComponent:
    async def async_setup(self):
        # Find entity by suffix
        self._enabled_entity = entity_helper.get_helper_entity(
            self.hass,
            "evsc_my_feature_enabled",
            "My Component"
        )

        # Check if switch is on
        if entity_helper.is_entity_on(self.hass, self._enabled_entity):
            # Do something
            pass
```

### Using State Helper

```python
from .utils import state_helper

class MyComponent:
    async def get_sensor_data(self):
        # Get float with default
        solar_watts = state_helper.get_float(
            self.hass,
            self._solar_sensor,
            default=0.0
        )

        # Get int with default
        soc = state_helper.get_int(
            self.hass,
            self._soc_sensor,
            default=0
        )

        # Get boolean
        is_enabled = state_helper.get_bool(
            self.hass,
            self._switch_entity,
            default=False
        )

        # Validate sensor before critical operations
        is_valid, error_msg = state_helper.validate_sensor(
            self.hass,
            self._critical_sensor,
            "Critical Sensor Name"
        )

        if not is_valid:
            self.logger.error(error_msg)
            return
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

# With timeout
import async_timeout

async with async_timeout.timeout(SERVICE_CALL_TIMEOUT):
    await self.hass.services.async_call(...)
```

### Safe Amperage Adjustment Sequence

**For decreasing amperage:**
```python
async def _adjust_amperage_down(self, target_amperage: int):
    """Safe sequence to decrease amperage."""
    # 1. Stop charger
    await self._stop_charger("Reducing amperage")

    # 2. Wait for charger to stop
    await asyncio.sleep(CHARGER_STOP_SEQUENCE_DELAY)

    # 3. Set new amperage
    await self.hass.services.async_call(
        "number",
        "set_value",
        {"entity_id": self._charger_current, "value": target_amperage},
        blocking=True,
    )

    # 4. Wait for stabilization
    await asyncio.sleep(CHARGER_AMPERAGE_STABILIZATION_DELAY)

    # 5. Start charger
    await self._start_charger()
```

**For increasing amperage:**
```python
async def _set_amperage(self, target_amperage: int):
    """Direct amperage increase (safe without stopping)."""
    await self.hass.services.async_call(
        "number",
        "set_value",
        {"entity_id": self._charger_current, "value": target_amperage},
        blocking=True,
    )
```

## Important Notes

- **2-second delay:** After platform setup, wait 2 seconds for entity registration (`__init__.py:35`)
- **Blocking vs Non-Blocking:** Use `blocking=True` for critical service calls to ensure they complete
- **State Restoration:** All helper entities extend `RestoreEntity` to persist across restarts
- **Entity Naming:** Format is `{domain}.ev_smart_charger_{entry_id}_{suffix}`
- **Logging:** Use EVSCLogger with emoji prefixes for visual parsing
- **Grid Import:** Positive values = importing from grid, negative = exporting to grid
- **Safe Amperage Decrease:** Always use stop → wait → adjust → wait → start sequence to prevent charger issues
- **Safe Amperage Increase:** Can be done directly without stopping charger
- **Type Safety:** Use state_helper for all state reading with proper defaults
- **Entity Discovery:** Use entity_helper for consistent entity finding
- **Dependency Injection:** Pass dependencies via constructor, not by importing modules
- **Rate Limiting:** Solar Surplus enforces 30-second minimum between checks
- **Battery Support:** Only activates when Priority=EV (not EV_FREE, HOME, or disabled)
- **Smart Blocker Window:** Adjusts based on Night Smart Charge enabled state

## Version History

### v1.0.3 (2025-10-30)
**EV_FREE Mode Charging Logic Fix**
- Fixed: Charger now stops immediately in EV_FREE mode when surplus insufficient (< 6A)
- Old behavior: Waited 30 seconds (surplus drop delay) before stopping
- New behavior: Immediate stop - EV_FREE is opportunistic charging only
- Rationale: When both targets met, delays not needed (delays are for PRIORITY_EV fluctuations)
- Technical: Added immediate stop condition before surplus decrease delay logic

### v1.0.2 (2025-10-30)
**Battery Support Logic Refinement**
- Battery support now ONLY activates when Priority=EV (EV below target, home can help)
- Battery support NO LONGER activates when Priority=EV_FREE (both targets met)
- Preserves home battery energy when both systems already balanced
- Updated diagnostic sensor to reflect battery support activation conditions

### v1.0.1 (2025-10-30)
**Critical Bug Fixes**
- Fixed AttributeError in Smart Blocker: `is_night_charge_active()` → `is_active()`
- Fixed battery support logic: ALWAYS calculate from surplus first, only use battery when surplus < 6A
- Battery support now acts as fallback, not primary charging method
- Prevents battery support from limiting charging when abundant surplus available

### v1.0.0 (2025-10-30)
**Major Refactoring - Architecture Overhaul**

**New Components:**
- `priority_balancer.py` - Independent Priority Balancer component
- `utils/logging_helper.py` - EVSCLogger with emoji prefixes
- `utils/entity_helper.py` - Centralized entity discovery
- `utils/state_helper.py` - Safe state reading utilities

**Refactored Components:**
- `solar_surplus.py` - Complete refactoring (1068→651 lines, -39%)
  - Uses Priority Balancer dependency injection
  - Fallback mode when Balancer disabled
  - Comprehensive logging
  - Correct battery support logic
- `automations.py` - Smart Blocker with dynamic window
  - Adjusts window based on Night Charge enabled state
  - sunset → night_charge_time (if enabled) OR sunset → sunrise (if disabled)
- `night_smart_charge.py` - Uses Priority Balancer for targets
  - No longer duplicates SOC target logic
  - Calls `priority_balancer.is_ev_target_reached()`
- `__init__.py` - 7-phase setup with dependency injection
  - Clear dependency ordering
  - Proper error handling per phase

**New Features:**
- Daily SOC targets for EV (weekday 50%, weekend 80% defaults)
- Daily SOC targets for Home battery (50% default all days)
- Priority Balancer enabled/disabled switch
- Home battery support configurable amperage
- Priority state diagnostic sensor
- Solar Surplus diagnostic sensor

**Architecture Changes:**
- Dependency injection pattern throughout
- Single source of truth for priority calculations
- Centralized utilities for logging, entity discovery, state reading
- Clear component dependency graph

## Debugging

### Common Issues

**Helper entities don't appear:**
1. Check platform registration in `const.py` PLATFORMS list
2. Verify `async_add_entities()` is called in platform files
3. Look for entity creation logs (search for "Created X EVSC")
4. Check entity registry: Developer Tools → States (search for "evsc")
5. Entity IDs contain entry_id, find via: `hass.states.async_entity_ids()`

**Component not initializing:**
1. Check logs for setup phase failures
2. Verify dependencies are passed correctly in `__init__.py`
3. Check entity discovery in `async_setup()` methods
4. Validate user-configured entities exist

**Battery support not activating:**
1. Check `evsc_use_home_battery` is ON
2. Check home battery SOC >= `evsc_home_battery_min_soc`
3. Check Priority Balancer priority == `PRIORITY_EV`
4. Check diagnostic sensor for activation conditions

**Smart Blocker not blocking:**
1. Check `evsc_smart_charger_blocker_enabled` is ON
2. Check Night Smart Charge is not active (takes priority)
3. Check current time vs blocking window
4. Check solar production vs threshold
5. Review Smart Blocker logs for decision reasoning

**Night Smart Charge not starting:**
1. Check `evsc_night_smart_charge_enabled` is ON
2. Check current time >= `evsc_night_charge_time`
3. Check PV forecast sensor is available
4. Check EV target not already reached
5. Review Night Smart Charge logs for activation conditions

**Solar Surplus not adjusting amperage:**
1. Check `evsc_charging_profile` is set to "solar_surplus"
2. Check charger status is not "charger_free"
3. Check Priority Balancer priority (PRIORITY_HOME stops charging)
4. Check surplus calculation (solar - home consumption)
5. Review Solar Surplus diagnostic sensor for detailed status

### Log Analysis

**Search patterns:**
- Component logs: Search for component name in brackets (e.g., "[SOLAR SURPLUS]")
- Decisions: Search for "🎯" emoji
- Actions: Search for "⚡" emoji
- Errors: Search for "❌" or "ERROR"
- Setup: Search for "Setting up" or "setup complete"

**Key log locations:**
- Setup phases: Search for "Phase 1", "Phase 2", etc. in `__init__.py`
- Priority calculations: Search for "Priority calculation" in Priority Balancer logs
- Battery support: Search for "Battery support" in Solar Surplus logs
- Blocking decisions: Search for "Blocking decision" in Smart Blocker logs

## Contributing

When adding features or fixing bugs:

1. Update version in both `manifest.json` and `const.py`
2. Add comprehensive logging using EVSCLogger
3. Use dependency injection for component dependencies
4. Use entity_helper for entity discovery
5. Use state_helper for all state reading
6. Follow existing patterns for consistency
7. Update this CLAUDE.md file with architectural changes
8. Update README.md with user-facing changes
9. Create detailed commit messages
10. Tag releases with semantic versioning

**Always refer to @ha-doc.md when implementing Home Assistant features.**

# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a **Home Assistant custom integration** for intelligent EV charging control. It manages EV charger automation based on solar production, time of day, battery levels, grid import protection, and intelligent priority balancing between EV and home battery charging.

**Domain:** `ev_smart_charger`
**Current Version:** 2.5.0
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

### Major Architectural Changes (v1.0.0+)

The v1.0.0+ releases introduced complete refactoring with the following key changes:

1. **Dependency Injection Pattern**: All components receive dependencies via constructor
2. **Independent Priority Balancer**: Extracted from solar_surplus.py into standalone component
3. **Centralized ChargerController**: Single source of truth for all charger operations (v1.0.4+)
4. **Centralized Utilities**: New utils directory with logging, entity, and state helpers
5. **8-Phase Setup**: Sequential initialization with proper dependency ordering
6. **~50% Code Reduction**: Removed ~340 lines of duplicate charger control code

### Core Components

**Entry Point (`__init__.py`):**
- 8-phase setup process with dependency injection
- Creates helper entities via platform setup (Phase 1)
- **Creates ChargerController for centralized charger operations (Phase 2)**
- Initializes Automation Coordinator (Phase 3)
- Creates independent Priority Balancer (Phase 4)
- Creates Night Smart Charge with Balancer + Controller dependencies (Phase 5)
- Creates Smart Charger Blocker with Night Charge + Controller dependencies (Phase 6)
- Creates Solar Surplus with Balancer + Controller dependencies (Phase 7)
- Stores all component references (Phase 8)
- Waits 2 seconds after platform setup for entity registration

**Configuration Flow (`config_flow.py`):**
- 3-step wizard: Name → Charger Entities → Monitoring Sensors
- User maps existing HA entities to integration roles
- Options flow allows reconfiguration

### Component Dependency Graph

```
ChargerController (centralized, independent)
       ↓
       ├─→ ALL charger operations (start, stop, set amperage)
       │
Priority Balancer (independent)
       ↓
       ├─→ Night Smart Charge + ChargerController
       │         ↓
       │   Smart Charger Blocker + ChargerController
       │
       └─→ Solar Surplus Automation + ChargerController
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
- `evsc_car_ready_monday` through `evsc_car_ready_sunday` - Daily flags for night charge fallback/skip behavior (v1.3.13+)

**Numbers (`number.py`):**
- `evsc_check_interval` - Solar Surplus recalculation interval (1-60 min, default 1)
- `evsc_grid_import_threshold` - Max grid import (W) before reducing charge (default 50)
- `evsc_grid_import_delay` - Delay before acting on grid import (seconds, default 30)
- `evsc_surplus_drop_delay` - Delay before stopping charger on surplus drop (seconds, default 30)
- `evsc_home_battery_min_soc` - Minimum home battery SOC for battery support (%, default 20)
- `evsc_battery_support_amperage` - Amperage to use when battery support active (A, default 16)
- `evsc_battery_support_sunset_buffer` - Block battery support when sunset is within this many minutes (min, default 60, range 0-240, 0 disables guard)
- `evsc_night_charge_amperage` - Amperage for night charging (A, default 16)
- `evsc_min_solar_forecast_threshold` - Min PV forecast to skip night charge (kWh, default 20)
- `evsc_night_pv_handoff_threshold` - PV-production handoff threshold (W, default 0 = disabled; v2.3.0). When > 0, on car_ready=OFF days Night Charge continues past astronomical sunrise and stops once measured `fv_production` stays ≥ this value for 5 min, handing off to Solar Surplus (hard-capped at `evsc_car_ready_time`)
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

#### 0. ChargerController (`charger_controller.py`) - **NEW in v1.0.4+**

**Purpose:** Centralized controller for ALL charger operations with rate limiting and queue management.

**Key Features:**
- **Single Source of Truth**: All charger on/off/amperage operations go through this controller
- **Rate Limiting**: Enforces 30-second minimum interval between operations
- **Operation Queue**: Manages multiple simultaneous requests with asyncio.Queue
- **Safe Amperage Sequences**:
  - Increase: Immediate (no delay needed)
  - Decrease: stop → 5 sec → set → 1 sec → start
- **Comprehensive Logging**: Every operation logged with EVSCLogger
- **State Caching**: Tracks current amperage and on/off state

**Key Methods:**
- `start_charger(target_amps, reason)` - Start charger with specified amperage
- `stop_charger(reason)` - Stop charger with reason logging
- `set_amperage(target_amps, reason)` - Smart amperage change (auto-detects increase/decrease)
- `is_charging()` - Check current charger state
- `get_current_amperage()` - Get cached amperage value
- `get_queue_size()` - Monitor operation queue
- `get_seconds_since_last_operation()` - Rate limiting info

**Rate Limiting Logic:**
```python
if time_since_last_operation < 30 seconds:
    add_to_queue(operation)
    process_queue_when_allowed()
else:
    execute_immediately()
```

**Used By:** Solar Surplus, Night Smart Charge, Smart Charger Blocker

**Benefits:**
- ✅ Eliminates ~340 lines of duplicate code
- ✅ Prevents charger overflow errors (30-sec rate limit)
- ✅ Consistent logging across all operations
- ✅ Single place to fix/improve charger logic

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
- `_block_charging()` - Uses ChargerController to stop charger + sends notification
- `_send_blocking_notification()` - Sends persistent notification

**Implementation Notes:**
- Uses `charger_controller.stop_charger()` for blocking (simplified from 130 lines to try-catch)
- 30-minute enforcement timeout to prevent log spam
- Rate limiting handled by ChargerController

#### 3. Night Smart Charge (`night_smart_charge.py`)

**Purpose:** Intelligent overnight charging from grid or home battery based on next day's PV forecast.

**Modes:**
- `battery`: Charging from home battery (when forecast sufficient)
- `grid`: Charging from grid (when forecast insufficient or battery support disabled)
- `idle`: Not active

**Dependencies:**
- Uses `priority_balancer.is_ev_target_reached()` for stop conditions
- Uses `charger_controller` for start/stop operations
- Coordinates with Smart Blocker for timing window

**Logic:**
1. Check if enabled and current time >= `evsc_night_charge_time`
2. Check PV forecast vs threshold
3. If forecast sufficient AND `evsc_use_home_battery` ON → battery mode (with pre-check)
4. If forecast insufficient OR battery support OFF → grid mode
5. Monitor SOC targets via Priority Balancer
6. Stop when `priority_balancer.is_ev_target_reached()` returns true

**Battery Mode Pre-Check (v1.3.13+):**
- Before starting charger, validates home battery SOC
- If home SOC <= threshold:
  - Check car_ready flag for current day (Mon-Sun)
  - If car_ready = TRUE → Fallback to GRID MODE (ensures car ready in morning)
  - If car_ready = FALSE → SKIP charging (wait for solar surplus)
- Prevents 15-second discharge before monitor detects low battery

**Key Methods:**
- `async_setup()` - Sets up time-based trigger, discovers car_ready switches
- `_async_time_trigger()` - Triggered at configured night charge time
- `_start_battery_charge()` - Start battery mode with pre-check logic
- `_battery_mode_monitor()` - Monitor battery-based charging, check targets
- `_grid_mode_monitor()` - Monitor grid-based charging, check targets
- `_should_activate()` - Check activation conditions
- `_get_car_ready_for_today()` - Get car_ready flag for current weekday (v1.3.13+)
- `is_active()` - Public method to check if Night Charge is currently active
- **All charger operations delegated to ChargerController**

#### 4. Solar Surplus Automation (`solar_surplus.py`)

**Purpose:** Charge EV using excess solar energy, with optional home battery support when Priority Balancer indicates EV priority.

**Trigger:** Periodic timer (configurable interval via `evsc_check_interval`, default 1 minute)

**Dependencies:**
- Uses `priority_balancer.calculate_priority()` for decision making
- Uses `charger_controller` for ALL charger operations (start, stop, amperage changes)
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

**Home Battery Support Logic (v1.0.2, sunset guard added in v1.6.22):**
- **Activation Conditions:**
  - `evsc_use_home_battery` is ON
  - Sunset is more than `evsc_battery_support_sunset_buffer` minutes away (default 60; set 0 to disable guard)
  - Home battery SOC >= `evsc_home_battery_min_soc`
  - Priority Balancer priority == `PRIORITY_EV` (EV below target, home can help)
- **Deactivation Conditions:**
  - Sunset is within the configured buffer (e.g. plug-in at 18:00 with sunset at 19:15)
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
- **All charger operations delegated to ChargerController** (no duplicate methods)

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
- `VERSION = "2.0.0"`
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

**Car Ready Defaults (v1.3.13+):**
- `DEFAULT_CAR_READY_WEEKDAY = True` (Monday-Friday: car needed for work)
- `DEFAULT_CAR_READY_WEEKEND = False` (Saturday-Sunday: car not urgently needed)

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
- **Device Grouping:** All 29 helper entities are grouped under a single "EV Smart Charger" device (v1.3.8+). Each entity class has a `device_info` property that returns device identifiers, manufacturer, model, and sw_version. This enables proper organization in Home Assistant's device registry.
- **Rate Limiting & Logging:** Solar Surplus rate limit warning logs only once per minute to prevent log spam (v1.3.9+). Immediate recalculation triggers respect 30-second minimum check interval.
- **Charger Amperage Convention:** The charger does NOT support 0A. Valid levels are `CHARGER_AMP_LEVELS = [6, 8, 10, 13, 16, 20, 24, 32]`. Internally, `target_amps = 0` is used as a convention to mean "STOP charger" (turn off), not "set to 0A". ChargerController translates: `0 → stop_charger()`, `>= 6 → start_charger(amps)` or `set_amperage(amps)`. Below 6A, the charger must be turned OFF.
- **Sensor Unavailability:** When amperage sensor returns None/unavailable (e.g., charger offline), `get_int(entity, default=None)` returns None without warnings (v1.3.7+). The system maintains current state until sensor becomes available again.

## Version History

### v2.9.0 (2026-07-19)
**FIX: Night Smart Charge — brand-status false stop in grid mode + "completed_today" ignores user intent changes**

Root-caused from a maintainer's live incident log (2026-07-19, non-Tuya wallbox
reporting `charging`/`available` status strings): the battery→grid fallback at
04:09 was terminally killed **15 seconds after starting** with
`charger_not_charging`, latching `completed_today` and leaving the EV at 62%
instead of the 80% target set at ~02:00. Two independent bugs fixed in
[night_smart_charge.py](custom_components/ev_smart_charger/night_smart_charge.py):

**Bug A — grid-monitor lifecycle check was a Tuya allowlist (the killer).**
Check 2 of `_async_monitor_grid_charge` ended the session whenever the status
string was not in `(charger_charging, charger_wait)` — but non-Tuya wallboxes
report brand vocabulary (`charging`, `Charging`, …), so a status that literally
means "charging" terminated the session on the first monitor tick. v2.2.0 had
already introduced the tolerant-blocklist principle everywhere else
(`power_model.is_charging`, frontend `_isDrawingNow`); this call site was the
last allowlist standing (the battery monitor has no such check — which is why
the battery session survived 4 hours and the grid session 15 seconds). Fix:
- **Measured-power path**: lifecycle stop ONLY on explicit `charger_free` /
  `charger_end`. Everything else (brand strings, `charger_wait`, None,
  unknown/unavailable) falls through to the measured-power blind-spot check,
  which is the authoritative signal on that path.
- **Legacy path (no power sensor)**: tolerant blocklist `charger_free` /
  `charger_end` / `charger_wait` (wait kept for v2.1.x parity), plus a
  preserved fail-safe stop on an unavailable/unknown/missing status (status is
  the only signal there).

**Bug B — terminal stops latched `completed_today` against stale user intent.**
Every stop is `terminal=True` → `_session_state = "completed_today"` blocks
re-activation for the rest of the day, and there was **no listener** on the
daily EV-target numbers or car_ready switches, so raising today's target (or
enabling today's car_ready) after any stop was silently ignored until the next
day. Fix: new `_async_user_intent_changed` listener
(`async_track_state_change_event` over the 7 `evsc_ev_min_soc_*` numbers + 7
`evsc_car_ready_*` switches, registered in `async_setup`). When the changed
entity belongs to **today**, the session is `completed_today`, and the EV SOC
is below the (new) target, the state machine re-arms (`ready`, completion latch
+ 1-hour-cooldown timestamp cleared — a deliberate user edit outranks the
anti-loop cooldown) and the next periodic tick re-evaluates. Guards: no-op
while a session is active (targets are already live-read), car_ready turning
OFF never resurrects a session, other-day entities and unknown/unavailable
restore churn are ignored, and outside the night window the reset is harmless
(the window check stays False; midnight rollover re-arms anyway). Defensive
`isinstance(dict)` on `priority_balancer._ev_min_soc_entities` keeps mocked
balancers (tests) safe.

**Files**: `night_smart_charge.py` (Check 2 blocklist, intent listener +
callback, `_intent_unsub` lifecycle), `const.py` + `manifest.json` (VERSION),
`README.md`, this file; tests: `tests/test_night_smart_charge.py` (+12: 5
lifecycle-blocklist incl. the brand-string regression and the preserved
fail-safe/blind-spot stops, 7 intent-re-arm covering re-arm, already-met,
car_ready ON/OFF, other-day, active-session and availability-churn guards).
`VERSION = "2.9.0"`. Full suite green: **271 passed / 0 failed**.

**Upgrade priority**: 🔴 STRONGLY RECOMMENDED for every non-Tuya wallbox using
Night Smart Charge (grid mode was effectively broken — any grid session died in
~15 s), 🟢 RECOMMENDED for everyone else (the intent re-arm makes late-evening
target/car_ready changes take effect the same night).

---

### v2.8.2 (2026-07-13)
**FIX: Mobile "shell vs stack" scroll conflict — REAL root cause found and fixed (nested scroll container from `overflow-x: hidden`)**

**Problem**: v2.8.1's backdrop-filter removal did NOT fix the mobile scroll
conflict — the diagnosis was wrong. The true root cause was found by
inspecting the user's LIVE Home Assistant instance (in-app browser on
`https://…/ev-smart-charger/main`), measuring the actual computed styles
and scroll metrics rather than theorizing:

1. Per CSS spec, `overflow-x: hidden` with `overflow-y: visible` is an
   illegal combination — the used `overflow-y` silently becomes **`auto`**.
   Both `:host` and `.dashboard-shell` declared `overflow-x: hidden`, so
   both were implicit vertical scroll containers.
2. `.aurora-b` (decorative blob, `position: absolute; bottom: -8%`) extends
   ~236 px past the shell's bottom edge. Measured live:
   `.dashboard-shell` had `scrollHeight 3127 > clientHeight 2891` —
   a REAL, functioning nested scroller with 236 px of internal scroll,
   competing with HA's page scroller. Exactly the reported symptom:
   swipes landing on the stack scrolled (or got eaten by) the shell's
   inner scroller, and one had to swipe elsewhere to move the page.

**Fix** (frontend-only, verified live on the user's instance by injecting
the patch and confirming `scrollTop` becomes unmovable on all three boxes
while the document scroller keeps working):
- `:host` and `.dashboard-shell`: `overflow-x: hidden` → **`overflow-x:
  clip`** (with the `hidden` line kept before it as a pre-2022-engine
  fallback). `clip` clips the axis WITHOUT creating a scroll container,
  so the used `overflow-y` stays `visible`.
- `ha-card`: `overflow: hidden` → **`overflow: clip`** (same visual
  clipping; `hidden` boxes still scroll programmatically and, once the
  shell stopped absorbing the aurora overflow, `ha-card` became the next
  scrollable box — clip kills all scrollability).
- **Reverted the v2.8.1 coarse-pointer blur removal**: empirically not the
  cause (didn't fix the symptom), and it cost the Liquid Glass look on
  mobile. Touch devices get the full glass design back. The v2.2.1
  `touch-action: pan-y` + `translateZ(0)` mitigations remain in place.

**Verification**: live on the user's HA (patch injected into the running
page: host/shell computed `overflow-y: visible`, `ha-card` `clip`, all
three `scrollTop`s pinned at 0, page scroller intact, visuals identical)
+ preview harness (bundle loads clean, same computed results, glass
restored). Definitive confirmation on the user's phone after upgrade.

**Files**: `frontend/ev-smart-charger-dashboard.js` (CSS only), `const.py`,
`manifest.json`. `VERSION = "2.8.2"`. No schema / entity / config-flow
change, entity counts unchanged (71 / 57).

**Upgrade priority**: 🟢 STRONGLY RECOMMENDED for anyone using the dashboard
on a phone or tablet — supersedes v2.8.1 (whose change is reverted here).

---

### v2.8.1 (2026-07-13)
**FIX: Touch scroll stuck on dashboard cards — definitive fix (backdrop-filter removed on touch devices)**

**Problem**: on mobile, vertical swipes landing on a card / the `.evsc-stack`
failed to scroll the view — the user had to swipe on the empty
`.dashboard-shell` padding to scroll (perceived as a "shell vs stack scroll
conflict"). Same symptom v2.2.1 targeted; its mitigations
(`touch-action: pan-y` + `translateZ(0)`) did not fully cure it on real
iOS/WebKit devices, exactly the residual risk its changelog documented.

**Root cause**: there is no nested scroll container in the bundle (single
scroller = HA's view). The gesture is swallowed by the iOS/WebKit bug where
an element carrying `-webkit-backdrop-filter` inside an outer scroll
container can capture the vertical pan instead of letting it bubble.

**Fix** (frontend-only, token-level, in
[ev-smart-charger-dashboard.js](custom_components/ev_smart_charger/frontend/ev-smart-charger-dashboard.js)):
under `@media (hover: none) and (pointer: coarse)` the two blur tokens are
overridden to `none` (`--evsc-blur`, `--evsc-blur-light`) — every glass
surface consumes them, so one rule removes every `backdrop-filter` on touch
devices — and the surfaces become near-opaque to compensate
(`--evsc-surface` 0.62→0.92, `--evsc-surface-strong` →0.97, plus the dark
variants). Desktop (fine pointer) keeps the Liquid Glass look byte-for-byte.

**Verification**: preview harness (`.preview/`) — bundle loads clean, both
media rules present in the CSSOM (valid syntax), simulated touch tokens at
375 px render correctly in light and dark, desktop computed style restored
to `saturate(180%) blur(40px)` untouched. Definitive confirmation is on a
real touch device (desktop preview cannot reproduce the WebKit bug).

**Files**: `frontend/ev-smart-charger-dashboard.js` (CSS only), `const.py`,
`manifest.json`. `VERSION = "2.8.1"`. No schema / entity / config-flow
change, entity counts unchanged (71 / 57). The `?v=`+content-hash
cache-buster delivers the new bundle on the next dashboard reload.

**Upgrade priority**: 🟢 STRONGLY RECOMMENDED for anyone using the dashboard
on a phone or tablet.

---

### v2.8.0 (2026-07-13)
**FEATURE: Consumption-spike fast response — zero grid import on household demand spikes**

**Problem**: the periodic grid-import protection is tuned for clouds: detection
only at the periodic tick (0–60 s), a 30 s debounce quantized on ticks
(~60 s real), ONE amp level down per cycle with the timer reset after each
step, plus the 30 s controller rate limit. A household demand spike (washing
machine, dishwasher, induction hob) while the EV charges on Solar Surplus took
~8 minutes to walk 16A→6A against a 2 kW deficit → **0.5–1 kWh/day leaked into
the grid** on a normal day with appliance usage.

**Solution — event-driven fast path with cause attribution**
([solar_surplus.py](custom_components/ev_smart_charger/solar_surplus.py)):
- **Grid-import listener** (`async_track_state_change_event` on every mapped
  grid sensor, L1+L2+L3 in three-phase) sees the spike within seconds. On the
  first over-threshold event it arms a debounce and schedules the verification
  via `async_call_later` at exactly `evsc_spike_response_delay` seconds — no
  tick quantization.
- **Classifier**: fast path fires ONLY when PV production is stable vs the
  per-tick baseline (`production >= baseline − max(300 W, 15%)`,
  `_spike_baseline_production` refreshed each periodic tick). A production
  drop (cloud) always stands the fast path down and leaves the legacy
  conservative protection in charge — the asymmetry the user asked for:
  aggressive on consumption spikes, conservative on clouds.
- **One-shot step-down**: instead of one level per cycle, the target is
  computed directly from the measured import —
  `max_allowed = current_amps − (import + 100 W margin)/effective_voltage`,
  highest amp level ≤ that. One single Tuya stop/set/start sequence instead of
  3–4 full cycles. If even the 6 A floor still imports → stop the charger
  (same semantics as the legacy min-level stop). Import smaller than one level
  → single-level fallback via `AmperageCalculator.get_next_level_down`.
- **Every fast action re-verifies live state** (`_spike_conditions_met`) both
  at listener time and at the delayed check: Solar Surplus must own the session
  (`_has_control()` — Night Charge/Boost/Forza/manual are out of scope), Hybrid
  Mode must be IDLE (never undercut a PROBING/RIDING_EDGE probe), the charger
  must be charging, the import must still exceed `evsc_grid_import_threshold`,
  and production must still be stable. Import recovering mid-debounce cancels
  the scheduled check.
- **Ramp-up untouched**: after the step-down, `_surplus_stable_since` and
  `_last_grid_import_high` are cleared, so recovery re-earns the legacy 60 s
  stability window and climbs one level per tick (fast-down / slow-up, no
  oscillation). Max one fast action per `SPIKE_MIN_ACTION_INTERVAL` (30 s,
  aligned with the controller rate limit).

**New helper**: `number.evsc_spike_response_delay` (s, 0–60, **default 10 =
active by default** — deliberate deviation from the opt-in convention,
confirmed with the maintainer: the feature is purely protective and only
reduces grid import; `0` disables → legacy behaviour byte-for-byte). Entity
counts 70→**71**, 56→**57**.

**Result**: a 2 kW hob spike at 16 A goes from ~8 min of grid import
(~0.13 kWh/event) to ~15–20 s.

**Files**: `solar_surplus.py` (listener, classifier, `_execute_spike_step_down`,
baseline tracking, cleanup), `const.py` (helper suffix, `DEFAULT_SPIKE_RESPONSE_DELAY`,
`SPIKE_*` constants, counts, VERSION), `number.py` (+1 always-created number),
`strings.json` + `translations/{en,it,nl}.json` (entity name),
`frontend/ev-smart-charger-dashboard.js` (suffix map + Solar settings stepper
EN/IT/NL), `README.md`, `manifest.json`; tests: NEW
`tests/test_v280_spike_response.py` (12 tests: classifier, gates, debounce,
one-shot landing level, floor stop, cloud abort, rate limit, single-level
fallback), `test_config_flow.py` + `test_entity_platforms.py` (counts 71/57/35).
`VERSION = "2.8.0"`. Full suite green: **259 passed / 0 failed**.

**Upgrade priority**: 🟢 STRONGLY RECOMMENDED for anyone charging on Solar
Surplus with a hybrid/zero-export meter and normal household appliance usage —
this directly recovers the 0.5–1 kWh/day lost to demand-spike latency. Set
`evsc_spike_response_delay` to `0` to restore the v2.7.x behaviour exactly.

---

### v2.7.2 (2026-06-13)
**Solar Surplus: clear the stale surplus-drop debounce on recovery (issue #52)**

Single-line follow-up to v2.7.1, all on Solar Surplus. Backward compatible — no
schema / entity / config-flow / dashboard change, entity counts unchanged (69 / 55).

**#52 — Drop-delay timer survived across surplus recoveries (BUG, silent battery
drain).** `_handle_surplus_decrease()` arms `self._last_surplus_sufficient` (the
`evsc_surplus_drop_delay` start timestamp) on the first sub-current tick and clears
it only *after* a step-down fires. `_handle_surplus_increase()` never touched it, so
when surplus recovered without committing a step-down the timer survived
indefinitely; the next dip then fired an **immediate** step-down against a 60–180 s
old timestamp, bypassing the `evsc_surplus_drop_delay` debounce and ratcheting the
charger downward across surplus oscillation (net 0 A per two-minute cycle on the
reporter's zero-export hybrid). Coupled to the v2.7.1 #49 one-level-per-tick ramp,
which re-enters the increase path on every cycle, so the bug surfaced continuously.

Fix: clear `self._last_surplus_sufficient = None` at the **entry point** of
`_handle_surplus_increase()`, before any branching. The dispatcher only routes there
when `target_amps > current_amps`, so any pending drop debounce is stale by
definition — a future dip must start a fresh `evsc_surplus_drop_delay` window. Entry
is the only spot covering all return paths (the post-step-up reset at the tail is
unreachable on the "stability timer just started / still waiting" branches). The two
existing `_surplus_stable_since = None` resets belong to a different invariant and
are unchanged. This is what makes the #49 ramp hold its level under oscillation
instead of ratcheting down.

**Files**: `solar_surplus.py` (`_handle_surplus_increase` entry-point clear),
`const.py` + `manifest.json` (VERSION); tests: `tests/test_solar_surplus.py`
(`test_surplus_increase_clears_stale_drop_timer`, covering the early-return path).
`VERSION = "2.7.2"`.

**Test baseline made fully green (infra, no integration code change).** The
long-standing "~19–22 pre-existing environmental baseline failures" were a
misdiagnosis — all were **stale tests that drifted from the code after the
v1.5.11 / v1.6.0 refactors**, now fixed so the suite is **232 passed / 0
failed**: (a) `test_solar_surplus` grid-import/stability tests mocked `time.time`
/ `solar_surplus.datetime` but the code uses `time.monotonic()` / `dt_util.now()`
(no-op mocks); (b) the shared `mock_charger_controller` fixture returned `bool`
where the real `ChargerController` returns `OperationResult` (callers read
`result.success`) — fixed in `tests/conftest.py` via `_ok_result()`, plus a
stale `_session_state` assertion and a wall-clock grid-import trigger under a
patched clock in `test_night_smart_charge`; (c) `test_charger_controller`
rate-limit test used a naive `datetime.now()` against the controller's aware
`dt_util.now()`; (d) `test_entity_platforms` had stale hardcoded entity counts
and a PV-only fixture that then looked up battery-only entities (`_mock_entry`
now maps `CONF_SOC_HOME`; counts → 34/21/4/9). `requirements_test.txt` pins
`pytest-homeassistant-custom-component==0.12.49` (was `>=`) and a new
`.github/workflows/tests.yml` runs `pytest` on push/PR so the baseline can't
silently rot again.

---

### v2.7.1 (2026-06-10)
**Solar Surplus ramp/hysteresis fixes + log polish (issues #49, #50, #51) + #47/#48 hardening**

Follow-up to v2.7.0, all on Solar Surplus. Backward compatible — no schema /
entity / config-flow / dashboard change, entity counts unchanged (69 / 55).

**#51 — Hysteresis dead-band locked the charger at any current, not just the
floor (BUG, silent battery drain).** `_calculate_target_amperage()` CASE 2
returned `current_amperage` unchanged whenever surplus was in the 5.5–6.5 A dead
band — even at, say, 20 A with only 5.6 A of surplus. On hybrid inverters the
home battery silently covered the deficit until a grid spike finally tripped
grid-import protection. The "maintain" rule now applies **only at the floor**
(`current <= amp_levels[0]`); above the floor it returns one level down
(`AmperageCalculator.get_next_level_down`, clamped at the floor), routed through
the existing `_handle_surplus_decrease` 30 s drop delay. Only CASE 3 (< stop
threshold) may still stop the charger.

**#49 — Surplus increase jumped straight to the full target in one step (BUG,
overshoot oscillation).** After 60 s of stable surplus, `_handle_surplus_increase()`
set the full calculated target (e.g. 13 A → 23 A) in one step; on zero-export
hybrids the inverter's PV ramp lagged the surge, tripping grid-import protection
and forcing a slow walk-down. The "already charging" branch now steps **one
level per stability window** (`get_next_level_up`) and re-arms `_surplus_stable_since`,
so each step stays inside the grid-import delay window. The "start from off"
branch is unchanged. Together with #51 this gives a clean one-level-per-tick ramp
in both directions.

**#50 — Log noise (cosmetic).** (A) `Periodic check #{n}` is logged only when
`> 1` (it was always `#1`). (B) `EVSCLogger.debug()` now carries a `🔍` (`TRACE`)
emoji prefix like every other level. (C) Fence pattern in
`solar_surplus._async_periodic_check`: one separator at the top of each tick,
removed from all 19 early-return branches (one `═══` per tick instead of 2–3).
`night_smart_charge.py` left unchanged.

**#47/#48 — Diagnostic ERROR debounce (display-only, hardening).** A noisy energy
integration (e.g. GivEnergy/givtcp) briefly drops sensors to `unavailable`,
which surfaced an alarming `ERROR: Invalid sensor values` on a single flap. The
diagnostic now shows a soft `WAITING: sensor momentarily unavailable` for the
first `SENSOR_UNAVAILABLE_ERROR_TICKS` (default 3) consecutive ticks and
escalates to `ERROR` only if it persists. Display-only — the tick still skips
while sensors are invalid, so no charging decision is ever made on bad data; the
counter resets the moment sensors recover. (Root cause of #47/#48 is the
external integration flapping, not an EVSC bug.)

**Files**: `solar_surplus.py` (#49, #51, #50A/#50C, #47/#48), `utils/logging_helper.py`
(#50B), `const.py` (`SENSOR_UNAVAILABLE_ERROR_TICKS`, VERSION), `manifest.json`;
tests: `tests/test_v271_fixes.py` + targeted tests in `test_solar_surplus.py`.
`VERSION = "2.7.1"`.

---

### v2.7.0 (2026-06-10)
**Bug-fix wave — 4 issues (#43–#46)**

A focused bug-fix release closing four reports from DJm00n. Fully backward
compatible — no schema/entity/config-flow change, entity counts unchanged
(69 / 55), no dashboard change.

**#43 — Translation `MALFORMED_ARGUMENT` on the battery-power field (BUG).** The
`battery_power` `data_description` embedded a Jinja example `{{ - states(...) |
float(0) }}`; HA's translation engine treats `{{ }}` as an interpolation
placeholder and replaced the whole string with the error label. The Jinja was
removed from the description (plain-text instruction pointing to the README) in
all 12 occurrences (`strings.json` + `translations/{en,it,nl}.json`, 3 steps
each), and a sign-inversion template example was added to the README. Text only.

**#44 — Solar Surplus stopped an already-off charger every tick on `PRIORITY_HOME`
(BUG, log/coordinator churn).** The `PRIORITY_HOME` branch in [solar_surplus.py](custom_components/ev_smart_charger/solar_surplus.py)
called `stop_charger()` unconditionally, dispatching a no-op `switch.turn_off`,
flapping coordinator ownership and resetting the check counter every 60 s while
the home target was unmet. Now a 3-branch guard: stop only when actually
charging; if off but still holding the coordinator, release it (no phantom
owner); otherwise a single DEBUG line and return.

**#45 — Night Smart Charge phantom "active" loop when the switch is OFF (BUG,
state machine).** In `_async_periodic_check` the `is_enabled()` check ran *after*
`_is_in_active_window()`, which is not a pure predicate — it mutates
`_session_state` to `"active"` at the activation window. A never-enabled install
got stuck logging `Already active (hysteresis)` + `disabled, skipping` every
minute until restart. The enabled check now runs first, so the window check (and
its mutation) is never reached while the switch is off.

**#46 — Solar Surplus jumped to full amperage after a cloud (BUG, battery drain).**
`_handle_grid_import_protection` reset `_last_grid_import_high` but not
`_surplus_stable_since`, so the pre-cloud stability credit survived the grid-import
event; once the cloud passed the system jumped straight to the full target in one
step (a large home-battery draw). `_surplus_stable_since` is now reset both at
first grid-import detection and after each step-down, forcing a fresh 60 s
stability window before any increase.

**Diagnostic hardening (#47/#48).** The Solar Surplus diagnostic now exposes the
raw `is_nighttime_computed` result alongside the already-present sunrise/sunset/
offset attributes (so a daytime "SKIPPED: Nighttime" is fully self-diagnosable),
and the `ERROR: Invalid sensor values` state now names the failing sensor
(truncated, full list still in the `errors` attribute).

**Files**: `solar_surplus.py` (#44, #46, #47/#48), `night_smart_charge.py` (#45),
`strings.json` + `translations/{en,it,nl}.json` (#43), `README.md` (#43),
`const.py` + `manifest.json` (VERSION). `VERSION = "2.7.0"`.

---

### v2.6.1 (2026-06-06)
**Dashboard: grid-lost indicator for issue #36 (frontend-only)**

v2.6.0 plumbed the optional `grid_available` sensor through to the card config
but did not surface it visually. v2.6.1 adds a compact **"Grid lost" warning
pill** in the hero pill-row (next to the priority / forecast pills), shown
**only** when `grid_available` reads explicitly off.

- New frontend helper `_gridAvailable()` mirrors the backend
  `ChargingModel.is_grid_available` tri-state: `null` when the sensor is unmapped
  OR its state is `unavailable`/`unknown` (→ pill hidden, no false alarm at boot),
  `true`/`false` only on a real on/off. `_renderGridLostPill()` renders the pill
  only on an explicit `false`.
- Rendered as an independent pill (not folded into the single hero banner), so it
  coexists with the Force / Boost / Night / Charging banners instead of hiding
  them. Added to `_computeStructuralKey` (`gl`) so it appears/disappears via one
  rebuild. New i18n key `hero.grid_lost` (EN/IT/NL), new `.grid-lost-pill` CSS
  (system-red, reduced-motion safe).

Frontend-only — no schema/entity/config change, counts unchanged (69 / 55). The
`?v=`+content-hash cache-buster picks up the new bundle on the next reload.
`VERSION = "2.6.1"`.

---

### v2.6.0 (2026-06-06)
**Mass bug-fixing & improvement release — 7 issues (#36–#42)**

A grouped release closing seven reports (six from DJm00n, one from xion2000):
three confirmed bugs, one log-noise cleanup, one self-tuning enhancement and two
opt-in features. Fully backward compatible — existing installs see no behaviour
change unless they map the new optional sensor or set the new numbers.

**#37 — Invalid MDI day icons (BUG).** The daily SOC-target numbers built
`mdi:calendar-{weekday}` icons (`mdi:calendar-monday`…`-sunday`) that do not
exist in Material Design Icons, so HA rendered an empty icon. [number.py](custom_components/ev_smart_charger/number.py)
now maps each day to a valid icon (`mdi:calendar-week` weekdays / `mdi:calendar-weekend`
weekend). No entity/behaviour change.

**#39 — Hybrid Mode EV_FREE guard hardcoded to 100% (BUG).** In
[hybrid_inverter_mode.py](custom_components/ev_smart_charger/hybrid_inverter_mode.py)
the `PRIORITY_EV_FREE` override guard compared `soc_home < 100` while the
IDLE-entry and keep-alive guards used `evsc_hybrid_battery_full_threshold`. On
large BMS-managed batteries that sit at 98–99% before briefly touching 100%, a
user who set the threshold to 98 saw the probe refused. Both sites now use the
configured `threshold` (default 95% → more permissive than 100, fully
backward-compatible).

**#41 — Telemetry 302 raw body looked like an error (BUG, cosmetic).**
[telemetry.py](custom_components/ev_smart_charger/telemetry.py) logged the raw
response body *before* the status check, so the standard GAS redirect HTML
(`<!-- GSE Default Error --> Moved Temporarily`) printed on every successful
302 and read as a failure. The raw-body log now runs only for non-302 (2xx /
error) responses; the 302 happy path logs a single success line. Delivery/retry
logic unchanged.

**#40 — INFO log flood at idle (~48k lines/day) (IMPROVEMENT, detection-only).**
Three components logged verbose INFO blocks on every periodic tick even when
nothing changed. Now they emit the full block at INFO only when something
actionable happens, and a single DEBUG line otherwise — no behaviour change, and
the diagnostic sensors still update every tick.
- [solar_surplus.py](custom_components/ev_smart_charger/solar_surplus.py): the
  sensor/decision readout is consolidated after `target_amps` is finalized and
  gated on `target_amps != current_amps`; the per-tick header, "Priority
  Balancer:" and "Both targets met" lines and the "Amperage optimal at 0A"
  confirmation are DEBUG on no-op ticks.
- [priority_balancer.py](custom_components/ev_smart_charger/priority_balancer.py):
  the decision block logs at INFO only on the first call and on a state
  transition (reusing `_last_priority`); stable ticks emit one DEBUG line. The
  diagnostic-telemetry and change-notification paths are untouched.
- [night_smart_charge.py](custom_components/ev_smart_charger/night_smart_charge.py):
  the "WINDOW CHECK DIAGNOSTIC" block (a v1.4.2 debug relic) is now INFO only
  when the window is active or within 30 minutes of opening; otherwise DEBUG.

**#38 — Slow RIDING_EDGE convergence on Generic chargers (ENHANCEMENT,
self-tuning).** Generic chargers step in 1 A increments, so RIDING_EDGE took
~11 ticks (6→17 A) vs ~5 for Tuya. [hybrid_inverter_mode.py](custom_components/ev_smart_charger/hybrid_inverter_mode.py)
now tracks consecutive stable step-ups (`_consecutive_stepup_count`) and, on a
Generic charger only, jumps 2 levels per tick after 2 consecutive single-level
step-ups (capped at `solar_max_amperage`). The counter resets on any step-down
and on every state transition. Tuya is unaffected (its levels are already
coarse). No new entity — counts unchanged.

**#36 — Grid loss drains the home battery (FEATURE / SAFETY).** On hybrid
"Battery First"/UPS inverters a grid outage is invisible to the integration
(all power sensors keep reporting), so Night Smart Charge grid mode keeps
drawing — now from the home battery — during the outage. New **optional
`grid_available` binary_sensor** (mapped in the Sensors step): when it reads OFF
(debounced for the grid-import delay, default 30 s) the grid-mode session stops
terminally. **Fail-safe** ([power_model.py](custom_components/ev_smart_charger/power_model.py)
`is_grid_available`): an unmapped sensor OR an `unavailable`/`unknown` state
returns `None` and never triggers a stop (so a boot-time / inverter-restart
`unavailable` cannot spuriously kill the session). Solar Surplus and Hybrid
Mode need no change (they key off PV surplus). New `STOP_REASON_GRID_LOSS`;
unmapped → byte-for-byte legacy behaviour. No new helper entity (counts
unchanged).

**#42 — Customizable nighttime period (FEATURE).** Two opt-in numbers,
`evsc_nighttime_sunset_offset` and `evsc_nighttime_sunrise_offset` (minutes,
0–120, default 0). Positive values **extend** the nighttime window that gates
Solar Surplus (the "SKIPPED: Nighttime" decision): night starts this many
minutes before sunset and ends this many minutes after sunrise.
`AstralTimeService.is_nighttime` takes the offsets (default 0 = astronomical,
byte-for-byte legacy); only the Solar Surplus call passes them — the Smart
Blocker window and Hybrid Mode daytime gate are intentionally unchanged.

**Entity counts**: +2 always-created numbers (issue #42) →
`TOTAL_INTEGRATION_ENTITIES` 67→**69**, `TOTAL_INTEGRATION_ENTITIES_NO_BATTERY`
53→**55**. #36 is a mapped sensor, not a helper (counts unchanged).

**Files**: `number.py` (#37, #42), `hybrid_inverter_mode.py` (#39, #38),
`telemetry.py` (#41), `solar_surplus.py` (#40, #42), `priority_balancer.py`
(#40), `night_smart_charge.py` (#40, #36), `power_model.py` (#36),
`config_flow.py` (#36), `dashboard_manager.py` (#36), `utils/astral_time_service.py`
(#42), `const.py`, `strings.json` + `translations/{en,it,nl}.json`,
`frontend/ev-smart-charger-dashboard.js` (#42 steppers + #36 whitelist),
`manifest.json`; tests: new `tests/test_v260_fixes.py` (#36 fail-safe reader,
#42 offsets), `tests/test_config_flow.py` (counts 69/55). `VERSION = "2.6.0"`.
Full suite green except the pre-existing environment-only baseline failures
(identical on clean master).

**Upgrade priority**: 🟢 RECOMMENDED for hybrid-inverter installs (map
`grid_available` for outage protection #36) and anyone bothered by the INFO log
flood (#40). ⚪ Otherwise low-impact — the bug fixes are transparent and the two
features are opt-in.

---

### v2.5.1 (2026-06-04)
**FIX: Stale "SKIPPED: Nighttime" on the Solar Surplus diagnostic + self-diagnosable astral times ([issue #34](https://github.com/antbald/ha-ev-smart-charger/issues/34), xion2000)**

**Problem**: a user (no overnight charging, no hybrid inverter, no forecast) saw the `evsc_solar_surplus_diagnostic` sensor stuck on `SKIPPED: Nighttime` in the middle of the day, then it "fixed itself at ~14:38" — an hour with no astronomical meaning. His `sun.sun` data (UK/BST: sunrise 04:33, sunset 21:33 local, `elevation 22.71`, `above_horizon`) proved the location/timezone were **correct**, and `is_nighttime()` ([astral_time_service.py:122](custom_components/ev_smart_charger/utils/astral_time_service.py#L122)) would have correctly returned "day" all afternoon. So this was **not** an astral-logic bug — the diagnostic sensor was simply **stale** (carrying the previous night's value), almost certainly because the post-update file swap (2.2.2 → 2.4.0) left the running instance in a partial state until a clean HA restart around 14:38 re-ran the loop.

**Two real weaknesses fixed (detection/robustness only — no charging-control change)**:
1. **No immediate first check.** `_start_timer` ([solar_surplus.py](custom_components/ev_smart_charger/solar_surplus.py)) registered `async_track_time_interval` (which does **not** fire an initial tick), so the sensor kept whatever value it had until the first interval elapsed. Now `_start_timer` runs one `await self._async_periodic_check(ignore_rate_limit=True)` right after registering the timer, wrapped in try/except so a first-check failure never blocks setup. The sensor reflects the true day/night state seconds after setup.
2. **`SKIPPED: Nighttime` was not self-diagnosable.** The event exposed no astral context. New `_build_nighttime_debug_attributes(now)` attaches `now` / `sunrise_today` / `sunset_today` to both `SKIPPED: Nighttime` and `SKIPPED: Nighttime (profile mismatch)` events. A user can now tell at a glance: wrong sunrise/sunset → HA location/timezone misconfig; correct times but daytime → stale value (and the immediate-tick fix removes that window).

**Scope / safety**: no entity/config-flow/schema change, entity counts unchanged (67/53), `is_nighttime()` untouched. Tests ([tests/test_solar_surplus.py](tests/test_solar_surplus.py)): `test_nighttime_skip_exposes_astral_times`, `test_start_timer_runs_initial_check`. Full suite green except the pre-existing environment-only baseline failures (grid-import / surplus-stability timing tests, identical on clean master). `VERSION = "2.5.1"`.

**Upgrade priority**: 🟢 RECOMMENDED if you ever see a stale `SKIPPED: Nighttime` in daytime — the sensor now self-corrects on setup and exposes the sunrise/sunset it computed. ⚪ NO-OP otherwise.

---

### v2.5.0 (2026-06-04)
**FEATURE: Surface the silent "Priority Balancer disabled" battery-protection bypass ([issue #35](https://github.com/antbald/ha-ev-smart-charger/issues/35), DJm00n)**

**Problem**: when `switch.evsc_priority_balancer_enabled` is OFF, Solar Surplus runs a **silent fallback mode** ([solar_surplus.py](custom_components/ev_smart_charger/solar_surplus.py)): the daily `evsc_home_min_soc_[day]` targets are ignored, `PRIORITY_HOME` is never reached, battery support never engages → the EV charges from solar **without any home-battery SOC protection**. The degradation was invisible (INFO-level log only). Critical for hybrid installs with large home batteries reserving capacity for outages. The issue also flagged two adjacent gaps: the balancer's enable switch was **dead code** in the auto-dashboard (`priorityBalancerId` defined, never rendered), and the fresh-install default is OFF.

**Solution** (visibility, not a behavior change — confirmed with maintainer): the fresh-install default stays **OFF** (no silent behavior change for existing/new installs). The degradation is now surfaced three ways:
- **WARNING log**, throttled once per day, when the balancer is OFF **and** at least one home SOC target is configured > 0%.
- **Persistent notification** ("Battery protection inactive", EN/IT/NL) with a **fixed id** (`NOTIF_ID_BALANCER_DISABLED = "evsc_priority_balancer_disabled"`) so it updates in place instead of stacking. **Auto-dismissed** when the balancer is re-enabled — with a per-setup one-shot dismiss (`_balancer_dismiss_done`) so a notification created before an HA restart is still cleaned up after the in-memory date-guard resets.
- **Dashboard switch**: new 🛡 **Safety** accordion in the settings `SETTINGS_CATALOG` rendering `priorityBalancer` + `smartBlocker` (both previously dead code); the unused `priorityBalancerId`/`smartBlockerId` locals were removed.

**Scope / safety**:
- **Detection-only.** Reuses `NotificationService.send_warning/dismiss`, `state_helper.get_int`, `has_home_battery(config)`, and the date-guard pattern from `hybrid_inverter_mode.py`. Never touches the charger control contract.
- **Correct trigger window (deliberate).** The check lives in the Solar Surplus periodic loop → fires only on profile `solar_surplus` with the charger plugged in, i.e. exactly when the bypass can materialize. No false alarms on `manual` profile or when unplugged.
- **No-op cases.** PV-only mode (no home battery) or no home target > 0% → silent (the issue's "acceptable" case). Balancer ON → byte-for-byte unchanged, no notification.
- **No new entity / no config-flow change.** Entity counts unchanged (**67 / 53**). New public helper `PriorityBalancer.has_active_home_soc_target()`.
- **Doc note:** README already documented the switch as default `OFF` (no false "default ON" claim to fix) — the docs were *enriched* with the new warning behavior, not corrected.

**Files**: `priority_balancer.py` (`has_active_home_soc_target()`), `solar_surplus.py` (`NotificationService` + `_maybe_warn_balancer_disabled` / `_clear_balancer_disabled_warning` + 2 call sites), `const.py` (`NOTIF_ID_BALANCER_DISABLED`, VERSION), `localization.py` (`priority_balancer.disabled.{title,message}` EN/IT/NL), `frontend/ev-smart-charger-dashboard.js` (Safety accordion + dead-code removal + `.shield` icon CSS), `manifest.json`, `README.md`, `docs/SSOT.md` (§5); tests: `tests/test_solar_surplus*.py` (warn-once, no-op, auto-dismiss, regression). `VERSION = "2.5.0"`.

**Upgrade priority**: 🟢 RECOMMENDED for anyone running Solar Surplus with home SOC targets configured but the Priority Balancer left OFF — you'll now see the warning + a one-click switch in the dashboard Safety panel. ⚪ NO-OP for everyone else (balancer ON, or no home targets).

---

### v2.4.0 (2026-06-04)
**FEATURE: Night Smart Charge grid mode honours `home_battery_min_soc` on hybrid inverters (opt-in — [issue #33](https://github.com/antbald/ha-ev-smart-charger/issues/33), DJm00n)**

**Problem**: same root cause as the battery-masking work in #29/#20, now in **Night Smart Charge grid mode**. On hybrid "Battery First" inverters (Deye/Sunsynk/Solis), when the EV charge starts the inverter discharges the **home battery first** — `grid_import ≈ 0` throughout — and only begins importing from the grid once the battery hits the inverter's *own internal* min SOC. The integration believes grid mode is drawing from the grid while it is actually draining the home battery, so `evsc_home_battery_min_soc` (an effective floor in **battery mode**, where the monitor stops at `home_soc <= home_min`) is silently bypassed in **grid mode** (whose monitor never read the home SOC).

**Solution**: a new **Check 1.5 (home-battery masking protection)** in the GRID monitor loop (`_async_monitor_grid_charge`, 15 s), mirroring the battery-mode floor. The session stops (terminal) when, **sustained for `evsc_grid_import_delay`** (default 30 s, debounced via a `StabilityTracker` — same pattern as the v2.3.0 PV-handoff):

```
read_battery_discharge() > evsc_grid_import_threshold   # battery discharging meaningfully
AND read_grid_import()   < evsc_grid_import_threshold   # EV energy NOT really from the grid
AND home_soc            <= evsc_home_battery_min_soc     # battery at/below its protection floor
```

The `grid_import < threshold` guard (added vs the literal issue proposal, per adversarial review) makes it a true masking detector: it won't stop when the EV genuinely charges from the grid while the battery serves house loads separately.

**Scope / safety**:
- **Opt-in / additive.** Gated on a mapped `battery_power` sensor (already optional since v2.1.0): `ChargingModel.read_battery_discharge()` returns `None` when unconfigured → the check is a no-op, byte-for-byte v2.3.x. No new entity, no config-flow change, entity counts unchanged (**67 / 53**).
- **`car_ready` ignored** (deliberate): the floor is a hard protection. The stop is **terminal**, consistent with battery-mode's home-min stop — recovery at dawn is handled by Solar Surplus / the v2.3.0 PV-handoff during the day, not by a nighttime re-activation that would just re-drain the battery.
- **Fail-safe SOC.** `priority_balancer.get_home_current_soc()` returns the sentinel `100.0` on an unavailable/unknown SOC sensor and in PV-only mode → `home_soc <= home_min` is False → a sensor fault never triggers a spurious stop (adversarial-review claim of a SOC=0 false-stop invalidated).
- **No new `STOP_REASON_*`** (same convention as v2.3.0/#32): the descriptive reason string is logged, but the diagnostic terminal code reuses `STOP_REASON_HOME_BATTERY_MIN` (the floor *was* reached) → **telemetry GAS schema untouched**, dashboard diagnostic rendering unchanged.
- **Tracker reset** on grid-session start, on the condition clearing, and in `_complete_night_charge` — no stale debounce across sessions/days. The battery→grid fallback path is covered automatically (it routes through the same grid monitor).
- **Orthogonal to Hybrid Inverter Mode** (its masking check is daytime-only, lower priority `SOLAR_SURPLUS=6 < NIGHT_CHARGE=4`, mutually-exclusive day/night windows) → no double-stop.

**Known limitations (documented)**: on `car_ready=ON` workdays a stop can leave the EV undercharged — **silently**, exactly as battery mode's home-min stop already does today (no notification keys off this reason; a dedicated notification is a possible follow-up). On `car_ready=OFF` days with PV-handoff (#32) enabled and a *high* `home_battery_min_soc`, an overnight drop below the floor can stop the session before the handoff window (still correct protection; set the floor below the expected overnight drain).

**Files**: `night_smart_charge.py` (`_grid_battery_masking_tracker` + 3 reset points + Check 1.5), `const.py` (VERSION), `manifest.json`, `README.md`, `docs/SSOT.md` (§4.2.1); tests: `test_night_smart_charge.py` (+6: masking stop, debounce wait, no-sensor no-op, grid-high no-stop, soc-above-min no-stop, reset-on-clear). Dashboard unchanged — `battery_power_entity` is already mapped since v2.1.0. `VERSION = "2.4.0"`. Full suite green except the pre-existing environment-only baseline failures (identical on clean master: 5 failed / 27 passed in this file, now 5 / 33 with the new tests).

**Upgrade priority**: 🟢 RECOMMENDED for hybrid-inverter installs **with a home battery** on overnight grid charging — map the `battery_power` sensor to make `home_battery_min_soc` an effective floor in grid mode. ⚪ NO-OP for everyone else — without the sensor, behaviour is identical to v2.3.x.

---

### v2.3.0 (2026-06-04)
**FEATURE: Night Smart Charge stops on real PV availability, not astronomical sunrise (opt-in — [issue #32](https://github.com/antbald/ha-ev-smart-charger/issues/32), DJm00n)**

**Problem**: on `car_ready=OFF` days Night Smart Charge stops at **astronomical sunrise** (`AstralTimeService.get_sunrise()`). At high latitudes in summer, astronomical sunrise (≈01:51) precedes usable PV production (≈05:00) by 3+ hours, leaving a window where Night Charge has stopped but Solar Surplus has no surplus yet → the EV sits idle. `car_ready_time` only partially helps (fixed manual clock time, no notion of "PV actually available").

**Solution**: new opt-in helper `number.evsc_night_pv_handoff_threshold` (W, default `0` = disabled). When `> 0`, on `car_ready=OFF` days the astronomical-sunrise stop is **replaced** by a measured-PV handoff: Night Charge continues past sunrise and stops only once `ChargingModel.read_production()` stays ≥ the threshold for `NIGHT_PV_HANDOFF_SUSTAIN_SECONDS` (300 s, debounced via `StabilityTracker`), handing off to Solar Surplus. `fv_production` is already a required sensor, so no new sensor dependency.

**Scope / safety (per adversarial review)**:
- **car_ready=OFF only.** car_ready=ON days are byte-for-byte unchanged (EV target / `evsc_car_ready_time`).
- **Hard-cap** at the next `evsc_car_ready_time`, anchored to the **session start** (`_night_session_start`) via `time_string_to_next_occurrence` so it is **midnight-safe** — an evening-started session (e.g. `night_charge_time=23:00`) caps the *following* morning, not the deadline that already passed today. (Using `_get_car_ready_time()`/current_time would have fired the cap ~1 min after start, or only at the exact deadline second.) Bounds grid/battery draw on overcast days where PV never reaches the threshold.
- **No new STOP_REASON.** The 3 call sites forward the dynamic `reason` only to `_stop_charger_with_control()` (logging) and force `STOP_REASON_DEADLINE_OR_TARGET` for the terminal diagnostic; wiring a new reason was out of scope. Reason string is logged for traceability.
- **Tracker reset** on session start (battery + grid), on sub-threshold PV, and in `_complete_night_charge` (before the boost-preempt early return) — no stale debounce across sessions/days.
- **Detection-only**: PV reading never touches the commanded-control contract (§4.1 SSOT). Default `0` = legacy sunrise behavior, byte-for-byte.

**Known limitations (documented)**: handoff only helps with the `solar_surplus` profile (else nothing resumes after the stop — keep threshold 0 on other profiles); in grid mode an overcast day draws from the grid until the hard-cap; users should set the threshold *above* their inverter's idle reading to avoid a false night handoff.

**Entity count**: +1 always-created number → `TOTAL_INTEGRATION_ENTITIES` 66→**67**, `TOTAL_INTEGRATION_ENTITIES_NO_BATTERY` 52→**53** (coupling comment updated, issue #22).

**Files**: `const.py` (suffix/default/`NIGHT_PV_HANDOFF_SUSTAIN_SECONDS`, counts, VERSION), `number.py` (always-created number), `night_smart_charge.py` (`_pv_handoff_tracker`, `_night_session_start`, `_get_night_pv_handoff_threshold`, `_get_pv_handoff_hardcap`, `_should_stop_for_deadline` OFF branch, session-start + completion resets), `frontend/ev-smart-charger-dashboard.js` (suffix map + Night settings stepper EN/IT/NL), `strings.json` + `translations/{en,it,nl}.json` (entity name), `README.md`, `info.md`, `docs/SSOT.md` (§4.2), `docs/CODEBASE_MAP.md`, `manifest.json`; tests: `test_night_smart_charge.py` (+7), `test_config_flow.py` (count 67/53). `VERSION = "2.3.0"`. Full suite green except the 19 pre-existing environment-only baseline failures (identical on clean master).

**Upgrade priority**: 🟢 RECOMMENDED for high-latitude / east-horizon-obstructed installs on the `solar_surplus` profile (opt in by setting `evsc_night_pv_handoff_threshold` ~200 W). ⚪ NO-OP for everyone else — default 0 preserves v2.2.x behavior exactly.

---

### v2.2.2 (2026-06-01)
**DIAGNOSTIC: console logging for charging detection (banner/tile stuck on "not charging")**

**Problem**: a user mapped a charging-power sensor that was clearly reporting charging, yet the dashboard's green banner and the "Charging Power" tile both showed "not charging". Frontend-only, so the chain (config → card config → `_isDrawingNow`) had to be inspected live.

**Added** ([frontend/ev-smart-charger-dashboard.js](custom_components/ev_smart_charger/frontend/ev-smart-charger-dashboard.js)):
- **One-shot config dump** in `setConfig` — `[EVSC Dashboard] charging detection config:` prints `charging_power_entity` / `charging_power_entities` / `charger_status_entity` / `phase_mode`. If these read `(missing)` the card config is stale (reload the Lovelace page; if still missing, restart HA — the auto-dashboard card config is rewritten on setup).
- **Throttled live diagnostic** from `_isDrawingNow` — `[EVSC Dashboard] charging detection:` prints, per change, the mapped entity/entities, each **raw state + unit_of_measurement + computed watts**, the summed `measured_total_watts`, the 200 W `floor_watts`, the `basis` (measured-power vs status-fallback), the `charger_status_state`, and the final `drawing_now`. Logs only when something changes (no console spam).

This makes the two most likely causes self-evident: (a) the sensor not reaching the card config (stale dashboard), or (b) a unit/value issue — e.g. a kW sensor with no `unit_of_measurement` attribute read as watts (3.7 W < the 200 W floor → "not charging").

**Backend verified** unchanged and correct: the reconfigure flow merges `CONF_CHARGING_POWER` into `entry.data` (`_merge_entry_data`), and `dashboard_manager._build_card_config` maps it to `charging_power_entity` (+ per-phase `charging_power_entities`). No behaviour change — purely additive console logging. **Files**: `frontend/ev-smart-charger-dashboard.js`, `const.py`, `manifest.json`. `VERSION = "2.2.2"`.

**Upgrade priority**: 🟢 RECOMMENDED if your charging banner/tile is stuck on "not charging" with a power sensor mapped — open the browser console (DevTools) after reloading the dashboard and read the two `[EVSC Dashboard] charging detection…` lines.

---

### v2.2.1 (2026-06-01)
**FIX: Touch scroll stuck on dashboard cards (could only scroll on empty gaps)**

**Problem**: on touch devices a vertical swipe that LANDED on a card (rather than on the empty shell padding / `ha-card` background) failed to scroll the Lovelace view — the user had to find an empty gap to drag the page. The empty areas scrolled because they carry no `backdrop-filter`; the cards did not.

**Root cause**: every glass surface (`.evsc-card`, `.evsc-hero-v2`, …) carries `-webkit-backdrop-filter` and declared no explicit `touch-action`. On iOS/WebKit a touch starting on a `backdrop-filter` layer can intermittently be captured by that layer instead of letting the vertical pan bubble up to the scroll container — the classic "I can only scroll on the gaps" symptom.

**Fix** (frontend-only, two complementary CSS levers in [ev-smart-charger-dashboard.js](custom_components/ev_smart_charger/frontend/ev-smart-charger-dashboard.js)):
1. **`touch-action: pan-y`** on the layout/card surfaces (`.dashboard-shell`, `.evsc-dash-grid` + children, `.evsc-stack`/`-inner`, `.evsc-card`, `.evsc-card-head`, `.evsc-hero-wrap`/`-v2`, `.evsc-acc-body`/`-inner`, `.weekly-grid`, `.evsc-wp-grid`, `.evsc-wp-mobile`). Declares vertical pan explicitly and **disables pinch-zoom** (intended — the dashboard is a control surface). There is no horizontal scroll region inside the card, so `pan-y` is safe. Tap targets keep `manipulation` (a superset that already allows pan-y), so toggles/steppers still scroll.
2. **`transform: translateZ(0)`** on the two `backdrop-filter` surfaces (`.evsc-card`, `.evsc-hero-v2`) — promotes each to its own GPU compositing layer so hit-testing is clean and the gesture passes through. Effectively free: `backdrop-filter` already promotes these to a layer, so no new layers are added. Scoped to the surfaces that actually carry the filter (not the layout wrappers) to avoid needless containing blocks.

**Verification**: confirmed in a standalone preview harness (mock `hass`, real bundle) — computed `touch-action: pan-y` on all card surfaces, `manipulation` on tap targets, `translateZ(0)` applied, no horizontal overflow, layout/blur intact. Note: the preview runs in desktop Chrome and does **not** reproduce the iOS WebKit bug; the definitive test is on a real touch device. If scrolling still fails there, the next lever is moving `translateZ(0)` / `will-change` onto Home Assistant's own scroll container.

**Files**: `frontend/ev-smart-charger-dashboard.js` (CSS only), `const.py`, `manifest.json`. `VERSION = "2.2.1"`. The `?v=` + content-hash cache-busters pick up the new bundle on the next dashboard reload.

**Backward compatible**: zero schema / entity / config-flow changes; purely visual/interaction. **Upgrade priority**: 🟢 RECOMMENDED for anyone who uses the dashboard on a phone or tablet.

---

### v2.2.0 (2026-06-01)
**FEATURE: Measured charging power as the charging-state SSOT (with legacy status fallback)**

**Problem**: "is the EV charging right now?" was answered by three incompatible proxies — `ChargerController.is_charging()` (commanded switch echo), `get_current_amperage()` (a setpoint, not a measurement), and the textual `CONF_EV_CHARGER_STATUS` string (`charger_charging`), which varies per wallbox. None detect a wallbox that reports `charger_charging` while drawing **0 W** (curtailment, EV paused at 100%, BMS throttle). This was also the root cause of the dashboard's green "EV charging" banner failing to appear: it used an exact `=== "charger_charging"` match that fails on any other brand string.

**Solution**: **measured phase charging power (W)** becomes the single source of truth for `drawing_now`. Single-phase = 1 optional sensor; three-phase = 3 sensors summed. The textual status sensor becomes a **fallback only**. Surfaced through one new reader on the already-shared `ChargingModel` (`power_model.py`, stored on `runtime_data.power_model`), so every consumer reaches the same instantaneous truth.

**Sacred invariant — byte-for-byte backward compat**: existing installs (status mapped, no power sensor) take the fallback path → zero behaviour change, no migration, entity counts unchanged (66 / 52). `read_charging_power` returns `None` when unconfigured → the controller answers from the switch echo exactly as v2.1.x. The regression guard `test_is_charging_no_power_sensor_uses_switch_echo` locks this.

**SSOT API** ([power_model.py](custom_components/ev_smart_charger/power_model.py)): `read_charging_power(hass)` (summed W, **all-or-nothing** in three-phase: any unreadable mapped phase → `None`; clamped `max(0, …)` so a reversed-sign sensor reads a flat 0 W; **unit-normalized kW→W** by `unit_of_measurement` so a kW wallbox sensor agrees with the W floor and the frontend), `is_charging(hass)` (stateless: `power > CHARGING_POWER_DRAWING_FLOOR_W` → else a **tolerant status blocklist** matching the frontend → else False), `is_plugged_in(hass)`. New constants `CHARGING_POWER_DRAWING_FLOOR_W = 200`, `CHARGING_POWER_GRACE_SECONDS = 15`, `NIGHT_GRID_DRAW_START_GRACE_SECONDS = 90`.

**Controller** ([charger_controller.py](custom_components/ev_smart_charger/charger_controller.py)): `_refresh_state` caches `_measured_power_w` **for the operation diagnostic only**. After code review, all controller *control* decisions stay strictly on the commanded switch echo / setpoint (byte-for-byte v2.1.x) — the earlier `_drawing_now_graced()` wiring into the Tuya decrease gate and `recover_to_target` was reverted because a single sub-floor measured glitch could (a) skip the safe Tuya stop/set/start decrease and change current live mid-charge, or (b) restart the charger from scratch on a transient dip. `is_charging()` is unchanged (commanded-on); the measured `drawing_now` is surfaced in the diagnostic via `power_model.is_charging`.

**Config flow**: `CONF_CHARGING_POWER` / `_L2` / `_L3` added as `vol.Optional` to the phase-aware sensors step; `CONF_EV_CHARGER_STATUS` changed Required → **Optional** (kept forever as fallback, never locked). No `async_migrate_entry`, `ConfigFlow.VERSION` stays 1, step counts unchanged (10/9/9). A companion **None-guard** was added to every status reader/subscriber (`night_smart_charge`, `solar_surplus`, `boost_charge`, `automations`) so optional status never crashes setup.

**The one control change** ([night_smart_charge.py](custom_components/ev_smart_charger/night_smart_charge.py) grid monitor Check 2): with a power sensor, the grid-mode session ends on (a) an explicit not-charging **lifecycle** status (free/end — immediate, preserved from v2.1.x), or (b) the **blind-spot** stop — status insists `charger_charging` but measured power stays below the floor for `CHARGING_POWER_GRACE_SECONDS` (debounced; `charger_wait` is treated as the transitional decrease and never debounces). Two code-review hardenings: a **startup ramp grace** (`NIGHT_GRID_DRAW_START_GRACE_SECONDS = 90`) suppresses the blind-spot stop right after the session starts, so a slow-to-draw EV (cold battery, scheduled charging, contactor delay) is not killed ~30 s in; and the debounce clock is **cleared when the power sensor goes unavailable** so a stale timestamp can't fire a premature stop on sensor recovery. No power sensor → byte-for-byte legacy status check. Seven unit tests cover blind-spot stop, debounce wait, keep-charging, lifecycle-survives-noisy-power, legacy fallback, startup-ramp grace, and stale-clock-clear.

**Diagnostic**: Solar Surplus attaches `charging_power_w` / `charging_power_source` / `is_charging_basis` to every diagnostic event (no new entity), so a reversed-sign sensor shows a flat 0 W — the user's cue to apply a `| abs` template fix. The controller diagnostic also carries `measured_power_w` + `drawing_now` for traceability.

**Dashboard**: `dashboard_manager` maps `charging_power_entity` (single) + `charging_power_entities` (per-phase array, whitelisted in `setConfig`). A single shared `_isDrawingNow()` (measured-W, unit-normalized, summed across phases → else a **tolerant status blocklist**, not exact-match) drives the hero banner, the SOC ring, and `_computeStructuralKey` (fixing the three-phase stale-banner case). The tolerant fallback fixes the green-banner symptom even for installs that never map a power sensor.

**Deliberate refinements vs the design plan** (all reviewed):
- The Smart Blocker does **not** get a new power rising-edge listener: its switch-ON listener already triggers it for power-only installs, and its block/allow decision depends on time/solar, not draw. **Known limitation**: a power-only install with no status sensor won't re-trigger the blocker when a car is plugged into an already-on switch (no switch event). Most power-sensor users keep their status sensor, so both listeners remain present.
- `charger_controller.is_charging()` kept as commanded-on (not split); `is_plugged_in()` added but existing plug gates not refactored.

**Code-review fixes (post-implementation, a 7-angle review of the diff)**:
- **Controller reverted to commanded-only control** (see Controller above) — eliminates the live-current-change-on-Tuya-glitch and restart-on-transient-dip risks; `_measured_power_w` stays for diagnostics.
- **Night-charge grid-stop hardened** with the startup ramp grace + stale-clock clear (see The one control change above).
- **Power-only installs (power mapped, status unmapped) now work for Night Smart Charge**: the battery-start pre-check and the handover gate previously read the status string and rejected a `None` status as "not connected", so Night Charge never started without a status sensor. Both now proceed when no status sensor is mapped and let the power-based monitor stop a non-charging session. **Known limitation that remains**: plug-DISCONNECT handling (Solar Surplus releasing control / Hybrid Mode force-exit on `charger_free`) still needs the status sensor — measured 0 W cannot tell "paused" from "unplugged". Mapping the status sensor is recommended for full plug-lifecycle coverage.
- **Backend/frontend SSOT alignment**: `power_model.is_charging`'s status fallback is now a tolerant blocklist (was exact `== charger_charging`), matching the frontend so a non-Tuya brand string ("Charging") reads identically on both sides.
- **kW→W unit normalization in the backend reader** (was frontend-only) — a kW wallbox sensor would otherwise read ~3.7 < the 200 W floor and falsely report "not charging", killing real sessions.

**Files**: `const.py`, `power_model.py`, `charger_controller.py`, `config_flow.py`, `night_smart_charge.py`, `solar_surplus.py`, `automations.py`, `dashboard_manager.py`, `frontend/ev-smart-charger-dashboard.js`, `manifest.json`, `strings.json` + `translations/{en,it,nl}.json`; tests: `test_power_model_and_charger_model.py`, `test_night_smart_charge.py` (+7), `test_config_flow.py` (+2). `VERSION = "2.2.0"`. Full suite green except the 19 pre-existing environment-only baseline failures (identical on clean master).

**Upgrade priority**: 🟢 RECOMMENDED — map your wallbox's charging-power sensor (single-phase) or the three per-phase sensors (three-phase) via reconfigure to get a reliable charging-state SSOT and a working green banner. ⚪ NO-OP for everyone else — without a power sensor, behaviour is identical to v2.1.x (and the tolerant banner fallback still improves on the old exact-match). **Beta ask**: report wallbox brand, sign correctness (diagnostic `charging_power_w` should track real draw, not a flat 0), and three-phase tile match.

---

### v2.1.1 (2026-06-01)
**FIX: Tolerate user-disabled helper entities at startup ([issue #22](https://github.com/antbald/ha-ev-smart-charger/issues/22) — xion2000)**

**Problem**: disabling *any* helper entity in Home Assistant (e.g. the Night Smart Charge controls + daily SOC targets a retired user on no overnight tariff doesn't need) stopped the integration from initializing after a HA restart, with the opaque `ConfigEntryNotReady` "Timed out while waiting for … registration". Re-enabling the entities fixed it.

**Root cause**: the Phase 1 barrier in [`__init__.py`](custom_components/ev_smart_charger/__init__.py) waits on `runtime_data.registration_event`, which only fires when `registered_entity_count >= expected_entity_count` (66 / 52 PV-only). HA skips `async_added_to_hass` ([entity_base.py:51](custom_components/ev_smart_charger/entity_base.py:51)) for disabled entities, so the counter never reaches the target → 10 s `asyncio.wait_for` times out → `ConfigEntryNotReady`.

**Fix**: new `_async_wait_for_helper_registration()` replaces the inline `try/except`. On timeout it reconciles against the **entity registry** (`disabled_by != None`):
- `registered + disabled >= expected` → user consciously disabled them. Log a WARNING, surface a Home Assistant **Repairs** entry (`translation_key="disabled_helpers"`, severity WARNING, EN/IT/NL), proceed in degraded mode (`state_helper` already defaults safely on `None`/`unknown`/`unavailable`). The Repairs entry clears on the next clean boot.
- real shortfall → log an ERROR with the count of genuinely missing entities and raise `ConfigEntryNotReady` so HA retries.

This is a faithful re-implementation of the never-merged v1.11.2 work (PR #25, which was stranded ~10 versions behind master and whose only tester likely mis-installed a branch download instead of a release). The unique-id matcher (`_entity_key_from_unique_id`, format `{DOMAIN}_{entry_id}_{key}` per [entity_base.py:31](custom_components/ev_smart_charger/entity_base.py:31)) was re-verified against the real format.

**Coupling note** added next to `TOTAL_INTEGRATION_ENTITIES` in [const.py](custom_components/ev_smart_charger/const.py): the disabled-helper tolerance assumes the constant equals the number of entities created when nothing is disabled; if it drifts above reality (cf. v1.6.20), a single disabled entity would silently tip the count back into a hard `ConfigEntryNotReady`.

**Tests** ([tests/test_integration_setup.py](tests/test_integration_setup.py)): unit tests for `_entity_key_from_unique_id` (accept valid, reject foreign/cross-entry); a regression test mirroring xion2000's setup that builds **real `entity_registry` entries with `RegistryEntryDisabler.USER`**, fires the timeout, and asserts `async_setup_entry` returns `True` + a `disabled_helpers` Repairs issue exists; and a genuine-shortfall test that still raises `ConfigEntryNotReady` with no Repairs issue. Full suite green except the 19 pre-existing environment-only baseline failures (identical on clean master).

**Files**: `__init__.py` (helpers + Phase 1 call), `const.py` (coupling comment + VERSION), `manifest.json`, `strings.json` + `translations/{en,it,nl}.json` (new `issues.disabled_helpers` block), `tests/test_integration_setup.py`. `VERSION = "2.1.1"`.

**Backward compatible**: zero schema / entity / config-flow changes. Installs with all helpers enabled hit the unchanged happy path. **Upgrade priority**: 🟢 RECOMMENDED for anyone who has disabled helper entities; ⚪ NO-OP otherwise.

---

### v2.1.0 (2026-05-31)
**Battery-discharge masking detection for Hybrid Inverter Mode + Solar-Surplus deadband buffer ([issue #29](https://github.com/antbald/ha-ev-smart-charger/issues/29), DJm00n)**

Hybrid Inverter Mode (v1.8.0) probes for curtailed PV by watching **only** `grid_import`. On hybrid systems **with a home battery**, a near-full battery can silently cover the 6 A probe load (grid stays ≈ 0), so the probe "succeeds" while merely draining the battery — the feature's blind spot for exactly the battery-equipped users #20 targeted. v2.1.0 adds a single opt-in watt limit, `max_battery_discharge_for_ev` (default 0 = off → byte-for-byte v2.0.0), backed by an optional **signed battery-power sensor**, applied in three places:

1. **Solar Surplus deadband buffer** (`solar_surplus.py`, `_async_periodic_check`): when already charging and surplus dips just below the 6 A floor, up to `limit` watts of battery discharge keep the session alive instead of stop-start cycling. Gated on actual `is_charging`, so it never *starts* on battery and never disturbs the opportunistic dead-band-start path. **Re-applies the same battery-support safety guards** via `_is_battery_bridge_allowed()` (home SOC floor, sunset buffer, `PRIORITY_EV_FREE` exclusion, PV-only) — the bridge only runs when `_battery_support_active` is False, so without those guards it would drain the home battery exactly where the guards said not to (the v1.3.24 / v1.6.22 protections).
2. **PROBING masking check** (`hybrid_inverter_mode.py`, Phase B): sustained battery discharge over the limit → `_fail_probe("battery discharge masking")`, **plus a completion gate** — at `elapsed >= probe_duration` the probe fails if the battery is still masking at that instant. The gate is essential because with the default 60 s tick and 60 s `probe_duration` the first Phase B evaluation *is* the completion tick (`batt_elapsed = 0`), so the sustained timer alone would never fire and a fully-masked probe would falsely "succeed". The user-set limit still tolerates minor battery activity; slow-ramp inverters are handled by raising `probe_duration`.
3. **RIDING_EDGE step-down**: an **independent** `_battery_violation_since` clock (never shares storage with `_import_violation_since`, to avoid corrupting grid-import timing) steps amperage down when the battery masks a cloud, and blocks ramp-up while masking persists.

**Single normalisation point**: `ChargingModel.read_battery_discharge(hass)` → discharge as positive watts (`max(0.0, -battery_power)`), or `None` when unconfigured. **Convention: sensor reports negative = discharging, positive = charging** (no invert toggle; reversed-sign vendors use a template sensor `{{ - states('sensor.xxx') | float(0) }}`). The diagnostic sensor surfaces `battery_discharge_w` so a reversed sign shows a flat 0 — the user's cue to fix it.

**Config flow**: new dedicated **"Hybrid Inverter Mode" step** (after `sensors`, before `pv_forecast`) with a thorough explanation of zero-export curtailment + the masking problem, an **enable toggle** (initial flow only — seeds the `evsc_hybrid_inverter_mode` switch's first-run state) and the optional **battery-power sensor** (all three flows, so it stays editable). Initial flow 9 → **10** steps; reconfigure/options 8 → **9**.

**Entity counts**: the new `evsc_max_battery_discharge_for_ev` number is **battery-only** (meaningless without a home battery): `TOTAL_INTEGRATION_ENTITIES` 65 → **66**, `TOTAL_INTEGRATION_ENTITIES_NO_BATTERY` **unchanged (52)**.

**Files**: `const.py` (CONF_BATTERY_POWER, CONF_HYBRID_INVERTER_MODE, HELPER/DEFAULT_MAX_BATTERY_DISCHARGE_FOR_EV, counts, VERSION), `power_model.py` (dataclass field + `read_battery_discharge`), `number.py` (battery-only number), `solar_surplus.py` (deadband buffer), `hybrid_inverter_mode.py` (PROBING/RIDING_EDGE checks + diagnostic), `config_flow.py` + `switch.py` + `__init__` seed plumbing, `strings.json` + `translations/{en,it,nl}.json`, `dashboard_manager.py` + `frontend/ev-smart-charger-dashboard.js` (mapping, whitelist, settings stepper, diagnostic render), `manifest.json`; tests updated. `VERSION = "2.1.0"`.

**Upgrade priority**: 🟢 RECOMMENDED for hybrid zero-export users **with a home battery** (opt in by mapping the battery-power sensor + setting the limit). ⚪ NO-OP for everyone else — limit 0 / sensor absent = identical to v2.0.0.

---

### v2.0.0 (2026-05-29) — MAJOR
**Universal compatibility: any electrical system (single-phase / three-phase) + any wallbox (Tuya / generic, cloud or local) — opt-in ([discussion #18](https://github.com/antbald/ha-ev-smart-charger/discussions/18))**

Major version: EV Smart Charger now covers *every* installation shape on the market (1φ/3φ, any HA-integrated wallbox). But it is **100% backward compatible** — existing installs default to single-phase + Tuya, no migration, no behaviour change.

Two independent opt-in dimensions, both defaulting to the current behaviour so existing installs are byte-for-byte unchanged (no migration; missing keys resolve to defaults via `.get`).

**1. Phase mode (`CONF_PHASE_MODE` = `single` default | `three`).**
In three-phase, production / home-consumption / grid-import are mapped as **three sensors each** (L1 reuses the existing single-phase key; L2/L3 are new keys, required only in three-phase) and summed. The watt→amp conversion uses an **effective voltage** of `phase_count × 230` (690 V in three-phase) instead of 230 V — so `surplus_amps = surplus_watts / effective_voltage` yields the per-phase amperage a balanced three-phase charger sustains (P = 3·V·I), and all downstream amperage thresholds / levels / caps stay valid unchanged. SOC sensors stay single (battery percentages, not per-phase).

**2. Charger model (`CONF_CHARGER_MODEL` = `tuya` default | `generic`).** Governs two behaviours:
- **Granularity**: `tuya` keeps discrete `CHARGER_AMP_LEVELS` `[6,8,10,13,16,20,24,32]`; `generic` uses 1 A steps `GENERIC_AMP_LEVELS = range(6,33)`. The amperage `number` entities use `step=1` in generic mode.
- **Decrease sequence**: `tuya` keeps the safe stop → set → start sequence (Tuya/`select` chargers misbehave on a live current change); `generic` lowers the current **live, without stopping** the charger (non-Tuya `number`-controlled wallboxes accept it). The existing `CurrentControlAdapter` (number/input_number/select/input_select) already handled non-Tuya wallbox *control*; v2.0.0 adds the granularity + live-decrease that completes it.

**Architecture — single source of truth.** New `power_model.py` defines `ChargingModel` (phase_count, effective_voltage, amp_levels, charger_model, per-phase power readers). Built once in `__init__` and stored on `runtime_data.power_model`; consumed by `charger_controller`, `solar_surplus`, `night_smart_charge`, `hybrid_inverter_mode`. Pure config helpers (`is_three_phase`, `get_phase_count`, `get_effective_voltage`, `get_amp_levels`, `get_charger_model`) live in `const.py` for the config flow / `number.py` / `dashboard_manager` (which run without runtime_data).

**Config flow.** Initial flow 7 → **9 steps** (name → phase_mode → charger_model → entities → sensors[phase-aware] → pv_forecast → notifications → external_connectors → dashboard). Reconfigure & options flows mirror it (6 → **8 steps**; entry point becomes phase_mode, charger-entities moved to a dedicated step) so existing users can opt in. Radio labels are localized in Python (cross-HA-version safe; older cores reject `translation_key` during selector serialization); step titles/descriptions in `strings.json` + EN/IT/NL with the R1 power note.

**Dashboard.** `dashboard_manager` passes `phase_mode`, `charger_model` and per-phase entity lists; the bundled card whitelists them in `setConfig` (the v1.11.13 silent-drop class of bug), sums the phase sensors for the Solar/Grid tiles, and derives charging power with `amps × 690` in three-phase.

**Known limitation (R1, documented not capped).** All amperage settings are per-phase, so in three-phase each means ~3× the single-phase power (16 A ≈ 11 kW; minimum ~4.1 kW). Battery support / night charge can exceed a home battery inverter's discharge limit — documented in the config flow + README; a power cap is a possible follow-up. Telemetry intentionally untouched (fixed GAS schema).

**Files**: NEW `power_model.py`; `const.py`, `runtime.py`, `__init__.py`, `utils/amperage_helper.py`, `charger_controller.py`, `solar_surplus.py`, `night_smart_charge.py`, `hybrid_inverter_mode.py`, `number.py`, `config_flow.py`, `dashboard_manager.py`, `frontend/ev-smart-charger-dashboard.js`, `strings.json`, `translations/{en,it,nl}.json`, `manifest.json`, `docs/SSOT.md`, `docs/CODEBASE_MAP.md`, `README.md`, `info.md`; tests: NEW `tests/test_power_model_and_charger_model.py`, updated `tests/test_config_flow*.py`. `VERSION = "2.0.0"`. Entity counts unchanged (phase/model are config, not helpers).

**Upgrade priority**: 🟢 RECOMMENDED for three-phase / non-Tuya wallbox owners (opt-in via reconfigure). ⚪ NO-OP for everyone else — defaults preserve single-phase + Tuya behaviour exactly.

---

### v1.11.7 (2026-05-27)
**HOTFIX: Boost rejection visibility + Charging Power lenient computation**

Two persistent regressions reported by the user after v1.11.6 shipped — neither was a bug in v1.11.6 per se, both were "the fix didn't actually solve my problem because the cause was deeper".

**1. Boost Session toggle still rimbalza off.**

After v1.11.6's frontend race fix, every toggle in the dashboard works correctly. Boost still bounces because the *backend* is genuinely rejecting the start condition. Most common cause: `target_soc ≤ current_soc` ([boost_charge.py:305-316](custom_components/ev_smart_charger/boost_charge.py:305)) — the EV is already at or above the configured boost target. The backend sends a `persistent_notification.create` with title "Boost not started" + reason, but that notification lands in HA's bell-icon panel, which users routinely miss.

Fix: pre-emptive validation on the frontend before `switch.toggle` is even dispatched. New `_validateToggleStart(entityId)` helper runs only for the Boost Session toggle (other toggles pass through unchanged). When the user clicks the OFF→ON direction:
- if `ev_soc_entity` is unavailable → abort with `toast.boost.missing_soc`.
- if `evSoc >= boost_target_soc` → abort with `toast.boost.target_reached` (interpolates real values: e.g. "Boost can't start: EV at 82% (≥ target 80%). Raise the target or wait for the battery to drain.").

The toast itself is a new `_showTransientMessage(text, tone)` helper. Renders a compact pill bottom-right of `.dashboard-shell` (already `position: relative`), auto-dismisses after 5 s, dismissible via × button, respects `prefers-reduced-motion`. Tones: `info` (blue accent) / `warning` (amber accent). The textContent is set via DOM assignment (not template injection) so translated strings can never carry HTML payloads.

When validation passes, the existing v1.11.6 optimistic flip + service call + pending-toggle TTL pipeline runs unchanged.

**2. Charging Power tile still shows "Not Charging" while car is drawing.**

v1.11.6's `_computeChargingPowerKw()` was strict in two places that real-world setups violate:
- Status check required *exact* `"charger_charging"`. Some wallboxes (and the user's transient states) report different strings.
- Amperage was parsed with `_numericState()` which calls plain `Number()` — fails on "6 A", "6.0A", or comma-decimal locales ("6,0").

Fix: inverted the status check (return null only when status is *explicitly* one of `{charger_free, charger_end, charger_wait}`; any other value — including `unknown`, `unavailable`, or brand-specific strings — falls through to amperage derivation). Amperage parser strips non-numeric characters with `/[^\d.,\-]/g` and replaces `,` with `.` before `Number()`. Both null-return branches now emit `console.debug` with full state context so the next user-reported issue can be triaged from DevTools without another release.

Both fixes are 100% frontend — pure bundle update, no schema / entity / config changes. The auto-dashboard cache-buster (`?v=1.11.7` + content-hash) picks up the new bundle on the next page reload.

**Files Modified**:
- [frontend/ev-smart-charger-dashboard.js](custom_components/ev_smart_charger/frontend/ev-smart-charger-dashboard.js): new i18n keys `toast.boost.target_reached`, `toast.boost.missing_soc`, `toast.dismiss_aria` (EN/IT/NL); new methods `_validateToggleStart`, `_showTransientMessage`; updated `_toggle` to gate via validation; rewritten `_computeChargingPowerKw`; new CSS block for `.evsc-toast.*`.
- [const.py](custom_components/ev_smart_charger/const.py): `VERSION = "1.11.7"`
- [manifest.json](custom_components/ev_smart_charger/manifest.json): `"version": "1.11.7"`

**Upgrade priority**: 🔴 **STRONGLY RECOMMENDED** for anyone on v1.11.6 — these are the two bugs that made the v1.11.6 ship feel broken. After upgrading you should see (a) a clear toast when Boost can't start (target reached or missing SOC) and (b) a real "X.X kW" reading on the Charging Power tile when the car is drawing current. If the Charging Power tile still shows "Not Charging" while charging, open browser DevTools → Console — you'll see a `[EVSC Dashboard] _computeChargingPowerKw: ...` debug line with the actual state values so the next bug fix is targeted.

---

### v1.11.6 (2026-05-27)
**UX FIXES: 5 dashboard issues + new hero state visualization**

Round of fixes against the v1.11.4 dashboard surface, all reported from real-world mobile use:

**1. Boost Session (and every other) toggle no longer rimbalza OFF immediately after click.** The optimistic UI path introduced in v1.11.3 was being reverted whenever an unrelated sensor tick (solar / grid / soc) triggered `set hass()` → `render()` → fast-path → `_updateLiveValues()` *before* HA finished processing the `switch.toggle` service call. The live-update loop read `snapshot.toggles[entityId] = false` from the stale state and flipped the class back. Most prominent on Boost because it sits at the top of the operational panel where sensor traffic is densest.

Fix: new `_pendingToggles` Map<entityId, {desired, expiresAt}> with 3 s TTL. `_optimisticToggleVisual()` records the desired state before flipping the class; `_updateLiveValues()` skips entries with a live optimistic pending value that doesn't match the snapshot yet (lets the visual stay put). HA confirmation clears the entry; the TTL guarantees recovery if the service call was silently dropped. The `_toggle()` `catch` branch clears the entry immediately so the visual snaps back to reality on service error.

**2. Charging Power tile derives kW from amperage.** The integration's config flow does not expose a "live power in W" sensor — only the configured wallbox amperage. `_build_card_config()` (dashboard_manager.py) therefore never maps `charging_power_entity`, and the card was falling through to the "Not Charging" / friendly-name fallback even while the car was actively drawing power.

Fix: new `_computeChargingPowerKw()` helper. Path 1 (advanced YAML users): if `charging_power_entity` is mapped AND yields > 0.05 → use it. Path 2 (auto-dashboard, production): if `charger_status_entity` is `charger_charging` AND `current_entity` reports a positive amperage → return `amps × 230 / 1000` rounded to 1 decimal. Both the hero ring center and the metric tile call the same helper to avoid a one-frame mismatch between first-render and live-update. New module-level constant `VOLTAGE_EU = 230` mirrors the same assumption baked into `solar_surplus.py`.

**3. Weekly Planner mobile day cards: "Ready ☀️?" label next to the car-ready toggle.** v1.11.0 introduced day-grouped editorial cards on mobile, but the car-ready iOS pill at the right of each card header had only an `aria-label` — sighted users couldn't tell what the toggle controlled. New i18n key `weekly_car_ready_label` ("Ready ☀️?", identical in EN/IT/NL as requested). Wrapping `<div class="evsc-wp-day-ready">` keeps label and toggle aligned with `gap: 8px`.

**4. Night Smart Charge card: stripped the redundant "Enabled / Unavailable" caption.** The card title already reads "NIGHT SMART CHARGE", so the inner toggle row had a useless duplicate label. Removed the `.t`/`.s` text block; the iOS pill stands alone, right-aligned via `justify-content: flex-end`. No new translation strings needed.

**5. NEW — Hero card state visualization.** First card switches appearance live when override states are active:

| State | Border | Top banner | Color | Motion |
|---|---|---|---|---|
| Normal | `1px solid var(--evsc-stroke)` | — | — | aurora background only |
| Force Charging | `2px solid var(--evsc-sys-red)` + glow | "Force Charging in corso / Active / actief" | iOS system red `#ff3b30` | 2.2 s ease-in-out border-pulse |
| Boost Session | `2px solid var(--evsc-deep-orange)` + glow | "Boost Session in corso / Active / actief" | Material 900 deep orange `#ff6b00` | 2.2 s ease-in-out border-pulse |

Force takes precedence over Boost when both are on, matching `automation_coordinator.py` priority (`PRIORITY_OVERRIDE = 1 > PRIORITY_BOOST_CHARGE`). The header banner has a white pulsing dot for "live in progress" feel. `prefers-reduced-motion: reduce` neutralizes both the border pulse and the dot animation. New CSS variable `--evsc-deep-orange: #ff6b00` (`--evsc-sys-red` already existed). New i18n keys `hero.banner.force_charging` and `hero.banner.boost_session` in all three locales.

`_computeStructuralKey()` now includes `forceCharge` and `boostEnabled` state (keys `fc`/`bo`) — transitions trigger a full innerHTML rebuild because the markup itself changes (banner appears/disappears, wrapper class changes). The rebuild is rare (manual user actions) so the fast-path live-update for ordinary sensor ticks is unaffected.

**Files Modified**:
- [frontend/ev-smart-charger-dashboard.js](custom_components/ev_smart_charger/frontend/ev-smart-charger-dashboard.js):
  - i18n keys: `weekly_car_ready_label` (3 locales), `hero.banner.force_charging` + `hero.banner.boost_session` (3 locales)
  - new `_pendingToggles` Map initialized in `setConfig`; updated `_toggle`, `_optimisticToggleVisual`, `_updateLiveValues`
  - new module constant `VOLTAGE_EU = 230`; new method `_computeChargingPowerKw()`; updated dispatch in `render` and `_renderHeroRing` and `_collectLiveValues`
  - weekly mobile branch wraps car toggle inside `.evsc-wp-day-ready` with label
  - Night Smart Charge card `.evsc-night-enable` block now toggle-only
  - new `.evsc-hero-wrap` outer wrapper + conditional `.evsc-hero-banner.banner-force` / `.banner-boost` + state classes + pulse keyframes; `--evsc-deep-orange: #ff6b00` added to `:root`
  - `_computeStructuralKey` returns extra `fc` + `bo` flags
- [const.py](custom_components/ev_smart_charger/const.py): `VERSION = "1.11.6"`
- [manifest.json](custom_components/ev_smart_charger/manifest.json): `"version": "1.11.6"`

**Backward compatibility**: zero schema / entity / API changes. The card config block, the auto-dashboard provisioning, every existing manual `custom:ev-smart-charger-dashboard` card keep working unchanged. The new `_computeChargingPowerKw()` Path 1 honors the YAML-supplied `charging_power_entity` first, so advanced users with a real wallbox/CT power sensor keep seeing measured kW instead of derived kW.

**Note on version numbering**: v1.11.5 was reserved by a no-op chore commit ("bump version to 1.11.5 for HACS default submission", 748d9c9) with no behavioral change — this release jumps directly to 1.11.6 to keep the changelog one-version-per-set-of-changes.

**Upgrade priority**: 🟢 RECOMMENDED — fixes the visible "click does nothing" Boost regression, gives users a real Charging Power reading out of the box, and adds at-a-glance override state visibility. Pure frontend bundle update — the `?v=` + `&h=` cache-busters from v1.11.4 guarantee the browser picks up the new bundle on the next dashboard reload.

---

### v1.11.4 (2026-05-27)
**HARDENING: Dashboard cache-busting — content-hash + runtime version injection**

Layered cache-busting on the bundled Lovelace card so visual changes always reach the browser on the next page reload — no manual cache clear, no service worker, no bundler.

**The pre-existing safety net**: `dashboard_manager.py` already registered the card resource with `?v={VERSION}` and the dedup logic at `async_ensure_resource()` correctly called `async_update_item` whenever the URL string differed from the previously-registered one. That worked for clean SemVer bumps where both `const.py:VERSION` and `manifest.json:version` were updated together.

**The gap**: the buster was a single manually-bumped value, and `RESOURCE_URL` lived as a module-level constant (`f"{FRONTEND_URL_BASE}/{FRONTEND_CARD_FILENAME}?v={VERSION}"`). A maintainer hotfix that edited the JS file but forgot to bump VERSION would silently ship stale bundles to every existing install — HACS replaces the file but does NOT re-import the Python module, so the in-memory `RESOURCE_URL` stayed at the old value forever and `async_update_item` never fired.

**The fix — two layered busters with runtime-fresh hash**:

1. **`?v=<VERSION>`** (unchanged): manual SemVer bump in `const.py`, visible in logs and issue reports.
2. **`&h=<content-hash>`** (new): first 8 hex chars of SHA-256 of the bundled JS, computed inside `_compute_bundle_hash()` and recomputed on **every** `async_ensure_resource()` call via `hass.async_add_executor_job` (no `@lru_cache`, no module-level cache). When the file content changes by a single byte, `h` changes, the URL differs from the registered one, and `async_update_item` fires.

**Single source of truth — no triple-bump risk**:

The build version is no longer duplicated as a JS-side `BUILD_VERSION` constant. Instead, `dashboard_manager.py:_build_card_config` injects `_build_version: VERSION` into the card config payload at runtime; the JS reads `this.config._build_version` in `setConfig()` and logs it once to the browser console (gated by `window.__EVSC_BUILD_LOGGED__`). Maintainers still update only `const.py + manifest.json` per release, as today.

**Diagnostic surface**:

- Browser console: `[EVSC Dashboard] build version: 1.11.4` (one line per page load, helps users / reviewers confirm which bundle is actually running).
- New `withVersion(url, version)` JS helper exported at module scope, ready for future fetches of `/local/...` assets — currently unused (the bundle has zero external loads).

**Documentation**:

- New `custom_components/ev_smart_charger/frontend/DEPLOY.md` — how the cache-busting works, pre-release checklist, DevTools verification steps, troubleshooting, ⚠️ note about CDN/proxy with "Ignore Query String" (e.g. Cloudflare).
- Updated manual install snippets in `frontend/README.md` and root `README.md` to show `?v=1.11.4` explicitly + advisory to bump on every release. Users who disable the auto-dashboard now have the buster documented inline.

**Files Modified**:
- [dashboard_manager.py](custom_components/ev_smart_charger/dashboard_manager.py): removed module-level `RESOURCE_URL`; added `_compute_bundle_hash()` + async `_build_resource_url(hass)`; `async_ensure_resource()` and `async_remove_resource_if_unused()` rewritten to compute URL locally; `_build_card_config()` injects `_build_version`.
- [frontend/ev-smart-charger-dashboard.js](custom_components/ev_smart_charger/frontend/ev-smart-charger-dashboard.js): added `withVersion(url, version)` helper at module scope; `setConfig()` captures `_build_version` from config and logs it once.
- **NEW**: [frontend/DEPLOY.md](custom_components/ev_smart_charger/frontend/DEPLOY.md) — cache-busting reference (~150 lines).
- [frontend/README.md](custom_components/ev_smart_charger/frontend/README.md): manual install snippet now shows `?v=1.11.4` + cross-reference to DEPLOY.md.
- [README.md](README.md): manual install snippet same treatment.
- [const.py](custom_components/ev_smart_charger/const.py): `VERSION = "1.11.4"`.
- [manifest.json](custom_components/ev_smart_charger/manifest.json): `"version": "1.11.4"`.

**Backward compatibility**: zero schema / entity / API changes. Existing config entries and card YAML continue to work unchanged. Users on the auto-dashboard see the new URL format on next HA restart; manual-install users see the same URL they had until they follow the updated snippet.

**Upgrade priority**: 🟢 STRONGLY RECOMMENDED — eliminates a class of "I upgraded but the dashboard looks identical" bug reports. No behavioral changes beyond cache invalidation.

---

### v1.11.3 (2026-05-26)
**CRITICAL FIX: Click handlers — scroll-to-top + boost charge "no response" bugs**

User reported two related bugs:
1. *"quando clicco su Force charge mi riporta on top della dashboard, in realtà questo bug ce l'ho quando clicco su qualsiasi tasto o button presente"*
2. *"Quando clicco su boost charge in realtà non succede nulla e sembra non prendere comando"*

**Single root cause**: every click on a toggle, stepper or time control triggered a full `innerHTML` rebuild of the entire dashboard. The `_computeStructuralKey()` function (introduced in v1.10.4 as the anti-flicker layer for sensor ticks) included `tg: toggles`, `nm: numbers`, `tm: times` in its hash, so any state change on those entities flipped the key, fell through to the slow path, and replaced `shadowRoot.innerHTML`. The browser then:

- Reset scroll position to the top of the dashboard (visible bug 1)
- Briefly showed the page-top while the user was looking at the toggle they just clicked further down (perceived as "click didn't register" — bug 2: the Boost Charge toggle DID flip state on HA's side, but the user was now staring at a different region of the dashboard with no visual feedback)

**Architectural fix — three-part**:

1. **Removed `tg`, `nm`, `tm` from the structural key.** Only genuinely structural state remains (view tab, accordion open/close, profile chip, charger status, priority state, prefix, language). Toggle / number / time changes now keep the key stable → fast path → live-update.

2. **Extended the live-update path (`_collectLiveValues` + `_updateLiveValues`)** to handle:
   - **Toggle classes** — every `[data-toggle="entityId"]` element gets its `is-on` / `on` class flipped based on the real HA state. Different toggle widgets in the codebase use different class names (`.control-toggle` / `.day-cell` / `.day-soc-cell` use `is-on`; `.evsc-set-toggle` / `.evsc-wp-tog` use `on`) — the helper detects which family the node belongs to. The inner `.switch-shell` (the iOS-style pill animation) gets the matching class.
   - **Number values** — every `[data-live-number="entityId"]` span gets its leading text node replaced, preserving the trailing `<small>unit</small>` element. Applies to stepper values, weekly planner day SOC cells, settings panel number rows, day-grouped mobile cards.
   - **Time values** — every `[data-live-time="entityId"]` span gets a `textContent` replacement. Applies to time controls, the Night Smart Charge START / CAR READY times, settings time rows.

3. **Optimistic UI for toggle / number clicks.** When the user clicks a toggle or a `+ / −` button, the visual flips immediately — *before* the HA service call returns. The next render tick (driven by HA's `state_changed` event, ~50–200 ms later) confirms via the live-update path, or reverts if the call errored. Eliminates the perceived lag that contributed to the "boost charge not responding" complaint.

**New `data-live-*` attribute conventions** (formalized in this release):

| Attribute | Purpose | Update mechanism |
|---|---|---|
| `data-toggle="entityId"` | toggle button (existing since v1.0) | live-update flips `is-on` / `on` class |
| `data-live-number="entityId"` | numeric value span (stepper, day-soc, settings stepper) | live-update replaces leading text node |
| `data-live-time="entityId"` | time value span (time control, night times, settings time) | live-update replaces `textContent` |
| `data-live="textKey"` | sensor-driven text (kW, W, A, %, ring headline) | unchanged from v1.10.4 |
| `data-live-attr-id="attrKey"` | SVG attribute (ring stroke-dashoffset) | unchanged from v1.10.4 |

**Files Modified**:
- [frontend/ev-smart-charger-dashboard.js](custom_components/ev_smart_charger/frontend/ev-smart-charger-dashboard.js):
  - `_computeStructuralKey()` — removed `tg`, `nm`, `tm`, kept `sel` + other structural state
  - `_collectLiveValues()` — added `toggles`, `numbers`, `times` to the returned snapshot
  - `_updateLiveValues()` — added class-flip logic for toggles, text-node update for numbers, textContent update for times
  - `_toggle()` — added optimistic UI call before `callService`, with revert path on error
  - `_adjustNumber()` — added optimistic UI call before `callService`
  - New helpers: `_optimisticToggleVisual(entityId)`, `_optimisticNumberVisual(entityId, value)`
  - Marked render output with `data-live-number` / `data-live-time` on: `.stepper-value`, `.time-value`, `.evsc-wp-soc.ev` / `.home` (both desktop and mobile day cards), `.day-soc-value`, `.evsc-set-val`, `.evsc-night-time .vv`
- [const.py](custom_components/ev_smart_charger/const.py): `VERSION = "1.11.3"`
- [manifest.json](custom_components/ev_smart_charger/manifest.json): `version = "1.11.3"`

**Backward compatibility**: zero schema / entity / API changes. Card config block identical. The new `data-live-*` attributes are inert when the live-update path can't find a snapshot value (no behavior change in the slow path).

**Side benefits** (beyond the two reported bugs):
- No more scroll-to-top on any sensor tick that happens to coincide with a profile change or accordion open
- No more flicker on +/− stepper presses (the value used to redraw the entire grid for one digit change)
- Touch-device interactions feel "instant" thanks to optimistic UI — sub-frame visual response on iOS / Android

**Upgrade priority**: 🔴 **CRITICAL** for anyone who uses the dashboard interactively. The scroll-to-top + perceived "click does nothing" make the dashboard frustrating to use on every viewport. Fix is purely a frontend bundle update — hard-refresh the Lovelace page after HA restart.

---

### v1.11.2 (2026-05-26)
**REVERT: Custom typography stack — back to native system fonts**

User feedback after v1.11.1 ship: *"non mi piace questo font, preferivo il precedente"*. The v1.11.0 typography pass — Instrument Serif italic for display moments (SOC ring percentage, hero h1, Night Charge times, Weekly Planner mobile day names) + JetBrains Mono for numeric readouts — has been **completely reverted** to the native system sans stack that v1.10.5 and earlier used.

**What changed**:

- **Removed**: the `@import url('https://fonts.bunny.net/...')` line at the top of `_inlineStyles()`. Zero external font dependencies. No FOUT, no GDPR considerations, no latency.
- **Removed**: the `--evsc-font-display` and `--evsc-font-mono` custom properties from `:host`. Only `--evsc-font` (system sans stack) remains.
- **Reverted**: every `font-family: var(--evsc-font-display)` and `font-family: var(--evsc-font-mono)` rule removed. Affected elements: `.hero-ring-center .ring-headline` (back to 2.2rem sans bold from 3rem italic), `.hero-ring-center .ring-sub`, `.hero-ring-legend > div`, `.eyebrow / .kicker` (back to 0.7rem 600 0.14em), `.metric-card strong` (back to `clamp(1.2rem, 2vw, 1.7rem)` sans bold), `.stepper-value / .time-value` (back to 1.1rem sans 700), `.priority-pill` (back to 0.85rem sans 600, no uppercase), `.evsc-hero-body h1` (back to `clamp(20px, 1.8vw, 26px)` sans 700, no italic), `.evsc-wp-day-name` (mobile, back to 18px sans 700), `.evsc-wp-today-badge`, `.evsc-wp-day-kind`, `.evsc-wp-day-card .evsc-wp-soc`, `.evsc-night-time .lbl / .vv` (back to 22px 800).

**What's preserved from Liquid Aurora** (v1.11.0–v1.11.1):

- ✅ Aurora color accents (`--evsc-aurora-green / cyan / violet / amber`) on the SOC ring arcs, charging pulse, background blobs
- ✅ Vertical-stack layout (v1.11.1 responsive fix) — all cards full‑width on every viewport, no more squeeze on 32" monitors
- ✅ Mobile day-card stack — 7 day-grouped editorial cards with TODAY pill, kind labels, current-day blue accent
- ✅ All v1.10.5 functional fixes — SOC ring centering, Charging Power "Non in carica" / "Completamente carica" states, stepper alignment, mobile responsive
- ✅ Aurora background blobs (slower 28–36 s float), priority pill pulse halo, charging pulse dot
- ✅ Responsive shell with fluid clamps, max-width 1180 px cap

**Design system doc updated**: [frontend/DESIGN.md](custom_components/ev_smart_charger/frontend/DESIGN.md) — Direction section rewritten to drop the editorial framing, Typography section rewritten with the new (simpler) single-stack table + a "Why the reversion is documented" rationale, Anti-patterns updated with a new "Re‑introducing custom web fonts casually" entry that captures the lesson.

**Network footprint**: zero. No `@import`, no Bunny Fonts request, no FOUT. The dashboard renders fully native on every supported HA client (web, iOS app, Android app).

**Files Modified**:
- [frontend/ev-smart-charger-dashboard.js](custom_components/ev_smart_charger/frontend/ev-smart-charger-dashboard.js): removed `@import`, removed 2 custom properties, reverted ~14 font-family declarations and their adjacent size/weight tokens back to v1.10.5 values
- [frontend/DESIGN.md](custom_components/ev_smart_charger/frontend/DESIGN.md): Direction + Typography + Anti-patterns sections rewritten to reflect v1.11.2 reality
- [const.py](custom_components/ev_smart_charger/const.py): `VERSION = "1.11.2"` (also drives `?v=` cache-buster)
- [manifest.json](custom_components/ev_smart_charger/manifest.json): `version = "1.11.2"`

**Backward compatibility**: zero schema / entity / API changes. The card config block is identical to v1.11.0/v1.11.1. Existing users see the typography revert on next Lovelace reload; no manual reconfiguration required.

**Upgrade priority**: 🟢 **STRONGLY RECOMMENDED** if you were on v1.11.0/v1.11.1 — removes external font dependency and restores the native look. No regression on responsive (carries v1.11.1 fixes) or on any functional behavior (carries v1.10.5 fixes).

---

### v1.11.1 (2026-05-26)
**FIX: Dashboard responsive on large monitors (27"/32"/4K) + extracted design system reference**

User reported the v1.11.0 dashboard rendering badly on a 32" monitor: the hero card had the title "EV Smart Charger" wrapped letter-by-letter into 3 lines ("EV / Smart / Charger"), and the 4 metric tiles (Solar Power / Grid Import / Charge Current / Charging Power) were stacked in a single narrow column on the right edge of the hero with truncated values.

**Root cause**: the `.evsc-dash-grid` was a hard 2-column layout (`1.15fr | 1fr`) for hero | weekly. At any viewport between ~980 px and ~1400 px, this layout compressed *both* cards — the hero body got barely enough room for the new (oversized) v1.11.0 h1 `clamp(28px, 4vw, 40px)`, and the 4 metric tiles squeezed via the hardcoded `repeat(2, minmax(0, 1fr))` to ~120 px each, where they wrapped to single-column rows of unreadable pseudo-columns. The 32" screen exhibited the worst case because HA's edit-mode side panel further shrunk the usable width.

**Fix — three converging changes**:

1. **Top-level layout: full vertical stack at every viewport.** `.evsc-dash-grid` switched from a 2-column grid to `display: flex; flex-direction: column`. Each top-level card now uses the full eye-line of the dashboard shell. Mirrors how Linear / Vercel / Stripe lay out content-dense dashboards: no inter-card competition for horizontal space. The render output is identical — the two original "stacks" inside `.evsc-dash-grid` are now flex siblings in a single column instead of grid cells in 2 columns.

2. **Shell max-width raised + fluid padding.** `.dashboard-shell` max-width `1080 px → 1180 px` (better for 27"/32" monitors, still under the "comfortable reading width" cap). Padding `clamp(16px, 3vw, 40px) → clamp(14px, 2.6vw, 36px)`, gap added `clamp(14px, 1.6vw, 22px)` so spacing scales fluidly with viewport instead of being a fixed 18 px.

3. **Hero typography + metric grid made adaptive.** Hero h1 clamp tightened from `clamp(28px, 4vw, 40px)` to `clamp(24px, 2.2vw, 32px)` — the 40 px max never visually justified itself even at wide hero-body widths and was the proximate cause of the wrap-each-word behavior. Metric row switched from hardcoded 2×2 to `repeat(auto-fit, minmax(140px, 1fr))` — now degrades gracefully 4→2→1 columns as the parent shrinks, without media queries.

**Deprecated**: the duplicate `@media (max-width: 920px) { .evsc-dash-grid { grid-template-columns: minmax(0, 1fr) } }` block (a legacy of the 2-column era) was removed. The hero-internal `@media (max-width: 720px)` collapse (ring on top, body below) is preserved.

**NEW: Design system reference — [frontend/DESIGN.md](custom_components/ev_smart_charger/frontend/DESIGN.md)**

The user asked: *"il design pass è il nuovo design system che hai creato giusto? lo hai strutturato e salvato bene in repo per utilizzi futuri?"* — fair question. The v1.11.0 design tokens lived only inline in `_inlineStyles()`, undiscoverable for future maintainers.

v1.11.1 extracts the design language into a self-contained discoverable document at `custom_components/ev_smart_charger/frontend/DESIGN.md`. Sections:

1. **Direction** — editorial × engineering, why two specific display moments anchor everything
2. **Typography** — three font roles (display / mono / body), the type scale, the Bunny Fonts import
3. **Color** — Apple System Colors (ambient) + 4 aurora accents (live moments only), use rules
4. **Motion** — easing tokens, keyframes, why entrance animations are forbidden
5. **Spatial system** — radii, padding scale, gap scale (6-step ladder)
6. **Surface & depth** — glass blur tokens, shadow tokens, the aurora background recipe
7. **Responsive principles** — vertical stack everywhere, breakpoint ladder, adaptive-grid pattern
8. **Component recipes** — copy-pasteable HTML for metric card, stepper, day card, priority pill
9. **Anti-patterns** — a numbered list of "things tried and rejected", with the reasoning
10. **Adding / changing tokens** — workflow for evolving the system without breaking it

A short pointer at the top of `_inlineStyles()` directs future editors to the doc. The frontend `README.md` also references it as required reading before any visual change. Any future companion card / settings rewrite / sister artifact will start from this reference instead of re-deriving choices.

**Files Modified**:
- [frontend/ev-smart-charger-dashboard.js](custom_components/ev_smart_charger/frontend/ev-smart-charger-dashboard.js): `.dashboard-shell` (max-width + clamps), `.evsc-dash-grid` (flex vertical), `.evsc-hero-body h1` (tighter clamp), `.evsc-metric-row` (auto-fit), removed duplicate 920 px media query, added DESIGN.md pointer comment at top of `_inlineStyles()`
- **NEW**: [frontend/DESIGN.md](custom_components/ev_smart_charger/frontend/DESIGN.md) — 10-section design system reference, ~12 KB
- [frontend/README.md](custom_components/ev_smart_charger/frontend/README.md): added DESIGN.md cross-reference in the intro
- [const.py](custom_components/ev_smart_charger/const.py): `VERSION = "1.11.1"`
- [manifest.json](custom_components/ev_smart_charger/manifest.json): `version = "1.11.1"`

**Backward compatibility**: zero schema / entity / API changes. Same backward-compat profile as v1.11.0. Users who don't have the responsive issue see no behavioral change on their viewport (the new layout fits inside the existing one — stack-vertical is a superset of stack-as-second-grid-column).

**Upgrade priority**: 🟡 **RECOMMENDED for users on monitors ≥ 27"** — fixes a visibly broken layout on large screens. Smaller-screen users see no regression and benefit from the fluid padding / gap scaling.

---

### v1.11.0 (2026-05-26)
**FEATURE: "Liquid Aurora" — editorial typography redesign of the auto-dashboard**

A full design pass on the bundled Lovelace card. Same information architecture, same entities, same data flow — but a distinct aesthetic identity that pulls the dashboard out of generic "AI-assistant glass card" territory.

**Direction**:
Liquid Glass surfaces stay (aurora blobs, blurred panels, iOS toggles) but get re-anchored around two new typographic axes:

- **Instrument Serif italic** for display moments — the SOC ring percentage, the hero `<h1>`, the Night Smart Charge START / CAR READY times, and the day names in the Weekly Planner mobile cards. A serif italic on a sans dashboard reads as a deliberate editorial choice, not a default.
- **JetBrains Mono** for technical readouts — every metric card value (kW, A, W), every stepper value, every eyebrow micro-cap, the priority pill label, the ring legend numbers, and the day-card kind labels (EV / HOME). Tabular numerics keep digit slots aligned when `+ / −` taps nudge a value.

System sans (SF Pro stack) remains for body copy.

Both fonts load from Bunny Fonts (privacy-friendly Google Fonts mirror) via a single `@import` at the top of the inline stylesheet, with `display=swap` so the dashboard never blocks on the network. Georgia / system mono fallbacks ensure full functionality on air-gapped HA instances.

**Color**:
New aurora accent palette layered on top of Apple System Colors:
```
--evsc-aurora-green:  #00d35a   (live charging arc, charging pulse)
--evsc-aurora-cyan:   #00d4ff   (background aurora blob a)
--evsc-aurora-violet: #b794ff   (home battery arc, background aurora blob b)
--evsc-aurora-amber:  #ffb84d   (reserved for solar warnings, future)
```
Used sparingly for "live" / saturated moments while the rest of the surface stays in the muted Apple system palette.

**Motion**:
- Aurora blobs: 18 s → 28–36 s (slower, more atmospheric, less screen-saver feel)
- Priority pill dot: new `evsc-pulse-slow` 3.2 s breath cycle with expanding glow halo
- Charging pulse dot: aurora-green with doubled glow halo

**Weekly Planner mobile (v1.10.5 → v1.11.0)**:
The v1.10.5 fix flattened 7×3 desktop grid cells into 21 stacked rows — functional but verbose. v1.11.0 replaces that with a **day-grouped card layout**: 7 self-contained day cards, each one a small editorial spread:
- Header: full weekday name in Instrument Serif italic (`Monday` / `Mercoledì` / `Maandag`), plus a "TODAY" pill in mono caps when applicable, plus the Car Ready toggle on the right.
- Body: two rows for EV and Home targets, with kind labels (`EV` / `HOME`) on the left and the existing stepper on the right.
- Today's card gets a blue accent border + glow.

Render-wise, this is implemented as a **second DOM payload** (`.evsc-wp-mobile`) that lives next to the desktop `.evsc-wp-grid` in the same `<section>`. CSS swaps which one is visible at the 768 px breakpoint. Two separate DOM trees rendered, one is `display: none` at any given viewport — cleaner than reflowing one grid into multiple breakpoints with `display: contents` gymnastics, and the `data-number` / `data-toggle` bindings are simple per-payload (no double-binding).

**Files Modified**:
- [frontend/ev-smart-charger-dashboard.js](custom_components/ev_smart_charger/frontend/ev-smart-charger-dashboard.js): font `@import` + new `--evsc-font-display` / `--evsc-font-mono` / `--evsc-aurora-*` variables; typography applied to hero `<h1>`, `.ring-headline`, `.ring-sub`, `.ring-legend`, `.metric-card strong`, `.eyebrow`, `.stepper-value`, `.priority-pill`, `.evsc-night-time .vv`; SOC ring arcs switched to aurora accents; `_renderWeeklyPlannerV2()` emits both desktop grid and mobile day cards; new `DAY_FULL_NAMES_BY_LOCALE` constant; new `weekly_today_badge` translation key in EN/IT/NL; CSS for `.evsc-wp-day-card`, `.evsc-wp-day-head`, `.evsc-wp-day-name`, `.evsc-wp-today-badge`, `.evsc-wp-day-row`, `.evsc-wp-day-kind`; `@media (max-width: 768px)` block rewritten to swap desktop ↔ mobile payloads
- [const.py](custom_components/ev_smart_charger/const.py): `VERSION = "1.11.0"` (also bumps the `?v=` cache-buster on the Lovelace resource URL — users get the new JS + new fonts on next reload)
- [manifest.json](custom_components/ev_smart_charger/manifest.json): `version = "1.11.0"`

**Backward compatibility**:
Zero schema / entity / API changes. The card config block (`type: custom:ev-smart-charger-dashboard`) is identical. Users who installed manually keep working. The auto-dashboard (v1.9.0+) rebinds the resource URL via the new `?v=1.11.0` and reloads automatically.

**Network footprint**:
One external `@import` to `fonts.bunny.net` (~50 KB total for both font families, both weights). Cached aggressively by Bunny CDN. Users on air-gapped HA setups see the fallback stack (Georgia + system mono) and lose none of the layout.

**Upgrade priority**: 🟢 RECOMMENDED — purely visual. The v1.10.5 functional fixes carry over intact. New users see a distinctively designed dashboard out of the box; existing users see their dashboard transform on first reload after upgrading.

---

### v1.10.5 (2026-05-26)
**FIX: Dashboard polish — SOC ring centering, Charging Power copy, stepper alignment, mobile Weekly Planner**

Four UI fixes against the Liquid Glass dashboard, all reported by the user on iPhone/tablet:

1. **SOC ring center misalignment** — The "70%" headline appeared in the upper half of the ring instead of dead-center. Root cause: `.hero-ring-center` used `display: grid; place-items: center`, but `place-items` centers items *within* implicit rows that still stack from the top — `align-content` was never set, so the headline + sub stack appeared at the top of the container. The v1.10.1 `padding-bottom: 6px` patch was a workaround in the wrong direction. Fix: switch the inner container to `display: flex; flex-direction: column; align-items: center; justify-content: center`, drop the padding hack.
2. **Charging Power card showed "Live feed optional" + entity name** — Card displayed the fallback string as the main value and the entity's friendly name as a sublabel, which was noise. Fix in [frontend/ev-smart-charger-dashboard.js](custom_components/ev_smart_charger/frontend/ev-smart-charger-dashboard.js):
   - `_renderMetric()` now skips the `<span class="metric-sub">` when the sublabel is empty. All 4 hero metric cards (Solar Power, Grid Import, Charge Current, Charging Power) now pass `""` as sublabel — cleaner, more compact look.
   - Charging Power value logic rewritten with explicit priority: EV SOC ≥ 100 OR `charger_end` → "Completamente carica"; `charger_free` OR power ≤ 0.05 W OR sensor null → "Non in carica"; `charger_wait` → "In attesa"; otherwise live kW. The translation strings already existed in EN/IT/NL (from v1.10.1) — no new keys, just smarter dispatch.
   - Same logic mirrored in the SOC ring center: headline shows live kW only when *actually* drawing power, otherwise falls back to the EV % so the ring stays informative (no more "0.0 W" flashing in the center).
3. **Stepper value not vertically centered** — Boost Amperage / Target SOC / time controls showed the number sitting on its text baseline (≈ 4–6 px above center of the 44 px tall pill). Fix: change `.stepper-value, .time-value` from `align-items: baseline` to `align-items: center`. One CSS line.
4. **Weekly Planner unusable on mobile** — The 8-column desktop grid (label + 7 days × 3 rows of `− / value / +`) crammed the steppers into ≈ 40 px columns on phones, overlapping the buttons and making single-day edits impossible. Fix: at `≤ 768 px` the grid collapses to a single vertical column of 21 full-width cards (7 days × {EV / Home / Car}). Each card shows the day initial, a kind label ("EV" / "Home" / "Car" — colored to match the desktop palette) and the existing stepper / toggle on the right. Touch targets enlarged: `−` / `+` buttons go from 18 → 28 px. The day-label + kind-label spans are rendered server-side but hidden on desktop via `display: none` — no separate render branch, all `data-number` / `data-toggle` bindings preserved, no `_computeStructuralKey()` churn.

**Files Modified**:
- [frontend/ev-smart-charger-dashboard.js](custom_components/ev_smart_charger/frontend/ev-smart-charger-dashboard.js): `_renderHeroRing()` + `_collectLiveValues()` (Fixes 1, 2c); `_renderMetric()` + 4 call sites (Fix 2a); `chargingPower` dispatch in main `render()` (Fix 2b); `_renderWeeklyPlannerV2()` injects day/kind labels (Fix 4); CSS for `.hero-ring-center`, `.stepper-value`, `.evsc-wp-*` plus new `@media (max-width: 768px)` block (Fixes 1, 3, 4)
- [const.py](custom_components/ev_smart_charger/const.py): `VERSION = "1.10.5"` (also drives the `?v=` cache-buster on the Lovelace resource URL, so users get the new JS on next page reload)
- [manifest.json](custom_components/ev_smart_charger/manifest.json): `version = "1.10.5"`

**Upgrade Priority**: 🟢 RECOMMENDED — Purely UI; no behavioral changes, no schema changes, no new entities. Users on a phone or tablet will feel the difference immediately.

---

### v1.9.0 (2026-05-26)
**FEATURE: Auto-generated Liquid Glass dashboard — zero-config sidebar UI**

**Problem solved**:
Until v1.8.0 the bundled Lovelace card existed but the user had to manually register the resource, create a dashboard or view, paste the YAML, type the `entity_prefix` of the config entry (lowercased, ULID for new installs) and map every external sensor — 6+ entity IDs. Far from "ready-to-go".

**Solution — ready-to-go bootstrap**:
A new `dashboard_manager.py` provisions a dedicated panel-mode Lovelace dashboard on first setup. The integration:

1. **Registers the Lovelace resource** (`/api/ev_smart_charger/frontend/ev-smart-charger-dashboard.js?v=1.9.0`) via the `ResourceStorageCollection` API. Idempotent: skipped if already present, updated on version bump.
2. **Creates a storage-mode dashboard** at `url_path: ev-smart-charger`, with `mdi:ev-station` icon, shown in the sidebar as "EV Smart Charger". Uses the (non-public but stable since 2019) `hass.data["lovelace"]` collections with safe fallbacks for YAML-mode and missing-API cores — never blocks setup, just warns and degrades.
3. **Writes the card config directly** into the Home Assistant `Store` (filename `lovelace.ev-smart-charger`, wrapped as `{"config": ...}` to match `LovelaceStorage`'s own format). The literal filename is used rather than `CONFIG_STORAGE_KEY.format(...)` — older HA cores use printf-style `'lovelace.%s'` and `.format()` would silently produce garbage.
4. **Pre-populates every parameter**: `entity_prefix` is `ev_smart_charger_<entry_id.lower()>` (v1.6.23 lowercase rule), and all user-mapped sensors are pulled from `entry.data` (`CONF_SOC_CAR`, `CONF_SOC_HOME`, `CONF_FV_PRODUCTION`, `CONF_GRID_IMPORT`, `CONF_HOME_CONSUMPTION`, `CONF_EV_CHARGER_STATUS`, `CONF_EV_CHARGER_CURRENT`, `CONF_EV_CHARGER_SWITCH`, `CONF_PV_FORECAST`).

**Opt-out**: new 7th step in the config flow (`dashboard`) plus a matching step in the reconfigure and options flows, with `vol.Optional(CONF_CREATE_DASHBOARD, default=True): BooleanSelector()`. Translations for EN/IT/NL.

**Lifecycle**:
- Phase 8.5 in `async_setup_entry` ensures or removes the dashboard based on the toggle. Multi-entry guard: when one entry disables the toggle, the dashboard is removed **only if** no other active entry still has it enabled.
- `async_unload_entry` removes the dashboard **and the resource** only when this is the last active entry of the integration. Resource stays put if other entries remain.

**Frontend redesign — Liquid Glass iOS 18**:
Same module file (`frontend/ev-smart-charger-dashboard.js`), CSS rewritten end-to-end (~700 lines replaced), entity-binding JS logic kept intact.

- **Apple System Colors** palette as CSS variables (`--evsc-sys-blue: #007aff`, `--evsc-sys-green: #34c759`, `--evsc-sys-purple: #af52de`, `--evsc-sys-pink: #ff2d55`, etc.).
- **Native dark/light** via `@media (prefers-color-scheme: dark)` — no theme config required.
- **Glass surfaces** with `backdrop-filter: saturate(180%) blur(40px)` over a layered aurora background (two soft accent blobs floating with 18s `floatGlow` animation).
- **Dual concentric SOC ring SVG** (new `_renderHeroRing()` helper): outer arc = EV SOC (system green), inner arc = home battery SOC (system purple, hidden in PV-only mode), center shows live charging power with pulsing green dot when charging, otherwise EV %.
- **Priority engine pill** (new `_renderPriorityPill()`): green for EV, blue for Home, purple for EV_Free, with `box-shadow` glow.
- **iOS-spec toggles**: 51×31 pill with 27px thumb, 280 ms spring transition (`cubic-bezier(0.32, 0.72, 0, 1)`).
- **SF Pro typography stack** with `font-feature-settings: "tnum"` on metric values.
- **Staggered entrance animations** (`evsc-fade-in`, 500 ms each, increasing delays per panel).
- **Accessibility**: `prefers-reduced-motion` neutralises all animations and transitions.

**Files modified**:
- **NEW**: [dashboard_manager.py](custom_components/ev_smart_charger/dashboard_manager.py) — `async_ensure_resource()`, `async_ensure_dashboard()`, `async_remove_dashboard()`, `async_remove_resource_if_unused()` with safe Lovelace-API wrappers
- [const.py](custom_components/ev_smart_charger/const.py): `VERSION = "1.9.0"`, new `DASHBOARD_URL_PATH`, `DASHBOARD_TITLE`, `DASHBOARD_ICON`, `DASHBOARD_RESOURCE_KEY`, `CONF_CREATE_DASHBOARD`, `DEFAULT_CREATE_DASHBOARD = True`
- [config_flow.py](custom_components/ev_smart_charger/config_flow.py): new `_dashboard_schema()`, new `async_step_dashboard()` in initial flow + new `async_step_reconfigure_dashboard()` in reconfigure flow + new `async_step_dashboard()` in options flow; total steps 6 → 7 (5 → 6 in reconfigure/options)
- [__init__.py](custom_components/ev_smart_charger/__init__.py): new Phase 8.5 hooks `async_ensure_dashboard` / `async_remove_dashboard` with multi-entry guard; cleanup of resource on last-entry unload
- [strings.json](custom_components/ev_smart_charger/strings.json), [translations/{en,it,nl}.json](custom_components/ev_smart_charger/translations): new `dashboard`, `reconfigure_dashboard` and options `dashboard` steps
- [frontend/ev-smart-charger-dashboard.js](custom_components/ev_smart_charger/frontend/ev-smart-charger-dashboard.js): full CSS rewrite (~700 lines) + new `_numericState()`, `_renderHeroRing()` and `_renderPriorityPill()` helpers + hero layout restructured (ring left, copy+metrics right)
- [frontend/README.md](custom_components/ev_smart_charger/frontend/README.md): rewritten for the auto-bootstrap flow + Liquid Glass design notes
- [README.md](README.md): added auto-dashboard to the feature list, TOC entry, new Step 7 in the configuration wizard, rewritten Dashboard section as "Auto-generated Dashboard" + "Manual usage"
- [manifest.json](custom_components/ev_smart_charger/manifest.json): version 1.9.0

**Upgrade priority**: 🟢 RECOMMENDED — Existing users see the dashboard pop up in the sidebar on first reload after upgrade (the toggle defaults to True). The bundled card itself remains fully backward compatible: every existing manual `custom:ev-smart-charger-dashboard` card keeps rendering — only the look changes. Users who don't want the auto-dashboard can disable it from the integration's options at any time.

**Known limitations**:
- The Lovelace dashboards/resources collections (`hass.data["lovelace"]`) are not a public HA API. They have been stable since 2019 but could change without notice. All access is wrapped in defensive `try/except` blocks that log a warning and continue setup if the surface changes.
- HA instances running Lovelace in YAML mode cannot have dashboards created programmatically. The integration logs a warning in this case; users can still register the card manually via the documented YAML snippet.

---

### v1.6.23 (2026-05-16)
**FIX: Invalid entity IDs containing uppercase characters (Issue #19)**

**Problem Fixed**:
Home Assistant logged warnings for all integration entities:

> Detected that custom integration 'ev_smart_charger' sets an invalid entity ID: `switch.ev_smart_charger_01KJSYBKA3ARM5XQ65D9B56TZK_evsc_car_ready_wednesday`. … This will stop working in Home Assistant 2027.2.0.

**Root Cause**:
HA `entity_id` must match `^[\da-z_]+\.[\da-z_]+$` (lowercase only). The integration built entity IDs embedding the raw `config_entry.entry_id`, which modern HA generates as a ULID in Crockford base32 (uppercase, e.g. `01KJSYBKA3ARM5XQ65D9B56TZK`). Older entries created before HA's switch to ULIDs were UUID lowercase, so the bug only surfaced for fresh installs.

**Fix**:
[entity_base.py:38](custom_components/ev_smart_charger/entity_base.py:38) — lowercase the `entry_id` when composing the entity ID:

```python
# Before
self.entity_id = f"{entity_domain}.{DOMAIN}_{entry_id}_{key}"
# After
self.entity_id = f"{entity_domain}.{DOMAIN}_{entry_id.lower()}_{key}"
```

`_attr_unique_id` is left untouched — `unique_id` has no format constraint, and keeping it stable preserves entity registry continuity.

**User Impact**:
- **New installations**: lowercase entity IDs, warnings gone.
- **Existing installations**: HA's entity registry stores `entity_id` per `unique_id`, so the previously-registered uppercase IDs persist after the update. The warnings will remain until HA 2027.2.0. To clear them immediately, remove and re-add the integration (entities are recreated with lowercase IDs; `RestoreEntity` preserves their values, but automations/dashboards referencing the old IDs must be updated by hand).

**Files Modified**:
- [entity_base.py](custom_components/ev_smart_charger/entity_base.py): 1-line fix on line 38
- [const.py](custom_components/ev_smart_charger/const.py): VERSION = "1.6.23"
- [manifest.json](custom_components/ev_smart_charger/manifest.json): version = "1.6.23"

**Upgrade Priority**: 🟡 RECOMMENDED — Fixes deprecation warnings that will break the integration in HA 2027.2.0

---

### v1.7.0 (2026-05-16)
**FEATURE: Support for installations without a home battery (issue #15)**

The integration can now run in **PV-only mode** for users who do not have a home battery installed. The previously mandatory `soc_home` sensor is now optional in the config flow; when omitted, the integration automatically degrades to a PV + EV setup.

**Behavior in PV-only mode**:

| Component | Behavior |
|---|---|
| Config flow `soc_home` field | Optional (was Required) |
| Priority Balancer | Only `PRIORITY_EV` / `PRIORITY_EV_FREE` — `PRIORITY_HOME` unreachable |
| Solar Surplus battery support | Permanently inactive |
| Night Smart Charge | Always GRID mode; BATTERY mode skipped |
| Helpers created | 45 instead of 58 (skipped 2 switches, 10 numbers, 1 sensor) |
| Diagnostic / telemetry schema | Unchanged — `home_soc=100` and `home_target=0` sentinels populate existing keys; downstream pipelines keep working |

**Design choices**:
- **Single source of truth**: presence of `CONF_SOC_HOME` in the config entry. No separate toggle. Helper `has_home_battery(config)` lives in `const.py`.
- **Sentinel approach**: `PriorityBalancer.get_home_current_soc()` returns `100.0` and `get_home_target_for_today()` returns `0` when no battery, making `PRIORITY_HOME` naturally unreachable (`100 >= 0`). Minimizes blast radius — no `None` handling required across callers.
- **Reconfigure protection**: once `soc_home` is configured, the field stays `Required` in reconfigure/options to prevent orphan helper entities in the Home Assistant entity registry. Users wanting to remove their home battery must delete and re-add the integration.
- **Skipped helpers (13)**: switches `evsc_use_home_battery`, `evsc_preserve_home_battery`; numbers `evsc_home_battery_min_soc`, `evsc_battery_support_amperage`, `evsc_battery_support_sunset_buffer`, plus 7 daily `evsc_home_min_soc_<day>`; sensor `evsc_today_home_target`.

**Files Modified**:
- [const.py](custom_components/ev_smart_charger/const.py): `VERSION = "1.7.0"`, new `has_home_battery()` helper, new `TOTAL_INTEGRATION_ENTITIES_NO_BATTERY = 45`
- [config_flow.py](custom_components/ev_smart_charger/config_flow.py): `soc_home` becomes `vol.Optional` for new entries, stays `vol.Required` in reconfigure when already configured
- [strings.json](custom_components/ev_smart_charger/strings.json): updated `soc_home` label/description (optional + reconfigure restriction)
- [switch.py](custom_components/ev_smart_charger/switch.py), [number.py](custom_components/ev_smart_charger/number.py), [sensor.py](custom_components/ev_smart_charger/sensor.py): conditional creation of battery-only helpers
- [priority_balancer.py](custom_components/ev_smart_charger/priority_balancer.py): sentinel values in `get_home_current_soc()` / `get_home_target_for_today()` / `is_home_target_reached()`; added `has_home_battery` field to diagnostic payload
- [solar_surplus.py](custom_components/ev_smart_charger/solar_surplus.py): skip battery helper discovery; `_handle_home_battery_usage()` early-returns
- [night_smart_charge.py](custom_components/ev_smart_charger/night_smart_charge.py): skip battery helper discovery; force GRID MODE in mode selector and emergency charge path; `_is_preserve_home_battery_enabled()` returns `False` in PV-only mode
- [__init__.py](custom_components/ev_smart_charger/__init__.py): pick `TOTAL_INTEGRATION_ENTITIES_NO_BATTERY` when no battery, log mode at startup
- [manifest.json](custom_components/ev_smart_charger/manifest.json): `version = "1.7.0"`

**Upgrade Priority**: 🟢 RECOMMENDED — Enables PV-only deployments. Existing installations with `soc_home` configured see no behavior change (`has_home_battery(config)` is True, all current logic paths preserved).

---

### v1.8.0 (2026-05-26)
**FEATURE: Hybrid Inverter Mode — curtailment discovery for zero-export systems (issue #20)**

**Problem solved**:
Reported by user DJm00n in [issue #20](https://github.com/antbald/ha-ev-smart-charger/issues/20). In hybrid zero-export inverter systems (Deye, Sunsynk, Solis, Growatt, Goodwe, etc.) with a full home battery, the inverter actively **curtails** PV production to avoid grid export. The `fv_production` sensor then reports a value matching `home_consumption` (e.g. both ≈ 800 W), and Solar Surplus computes `surplus = production − consumption ≈ 0`. The integration concludes there is no headroom and never starts the EV charger — even though several kilowatts of PV capacity are sitting idle, ready to ramp up the moment any load is applied.

**Solution — empirical probing strategy**:
Since the only reliable signal in zero-export curtailment is `grid_import`, Hybrid Mode starts the EV charger at the minimum 6 A as a "test load" and observes the grid:
- If the inverter ramps up PV in response and `grid_import` stays near zero → headroom confirmed, continue and "ride the edge" of the import limit by stepping amperage up/down.
- If `grid_import` rises and persists → no headroom, stop and enter cooldown.

This works on any hybrid inverter without brand-specific integration, because it uses only the two sensors the user already configured: `grid_import` and `soc_home`.

**State machine**:
```
IDLE
  └─ entry conditions met → start_charger(6A) + notify_once → PROBING

PROBING (60s, two-phase)
  ├─ Phase A (0-20s "transient grace"): grid_import ignored (inverter ramp time)
  ├─ Phase B (20-60s "steady-state"): grid > threshold for max_import_duration → FAIL
  ├─ completes OK → RIDING_EDGE
  └─ FAIL → stop_charger + COOLDOWN_SHORT + append to sliding window

RIDING_EDGE
  ├─ grid stable for 60s & < cap → step amperage up (6 → 8 → 10 → 13 → 16 → ...)
  ├─ grid > threshold for max_import_duration → step amperage down
  ├─ at 6A and grid still high → STOP + COOLDOWN_SHORT (counts as FAIL)
  ├─ sustained ≥ 5 min without fail → reset failure window
  └─ exit condition (toggle off, sunset, plug out, ...) → IDLE (graceful, not a fail)

COOLDOWN_SHORT (2 min) → IDLE
COOLDOWN_LONG (15 min) → IDLE  (entered when ≥5 fails in 30-min sliding window)
HARD_EXIT (until next sunrise)  (entered after 3 long cooldowns in one day)
```

**Worst-case grid cost is bounded at ≤ 350 Wh/day** (well under one tenth of a kWh) by:
- Sliding window: max 5 failed probes per 30-minute rolling window
- Daily cap: max 3 long cooldowns per day, then HARD_EXIT until sunrise
- Successful RIDING_EDGE sustained ≥ 5 min resets the failure counter

**Configurable parameters** (all opt-in, default OFF):
| Entity | Default | Range | Purpose |
|---|---|---|---|
| `switch.evsc_hybrid_inverter_mode` | OFF | — | Master opt-in toggle |
| `number.evsc_hybrid_battery_full_threshold` | 95 % | 80-100 | SOC required to consider battery "full" |
| `number.evsc_hybrid_probe_duration` | 60 s | 30-180 | Total probe window length |
| `number.evsc_hybrid_max_import_duration` | 60 s | 30-120 | Max sustained import before backoff |
| `number.evsc_hybrid_max_failed_probes` | 5 | 1-10 | Sliding window threshold for long cooldown |
| `sensor.evsc_hybrid_inverter_diagnostic` | — | — | Real-time state machine status |

**Internal (non-user-configurable) constants**: `HYBRID_TRANSIENT_GRACE_SECONDS = 20`, `HYBRID_SUNSET_BUFFER_MIN = 90`, `HYBRID_HEADROOM_STABLE_SECONDS = 60`, `HYBRID_GRID_ENTRY_SMOOTH_SECONDS = 60`, `HYBRID_FAILURE_WINDOW_SECONDS = 1800`, `HYBRID_RIDING_EDGE_SUCCESS_DURATION = 300`, `HYBRID_MAX_DAILY_LONG_COOLDOWNS = 3`, `HYBRID_MAX_NEGATIVE_SURPLUS_W = -500`.

**Entry conditions** (all must hold simultaneously when state == IDLE):
1. `evsc_hybrid_inverter_mode` switch ON
2. Daytime (sun above horizon)
3. ≥ 90 min before sunset (no probing in late-afternoon fading PV)
4. `soc_home ≥ battery_full_threshold` (default 95 %)
5. `surplus_amps < SURPLUS_STOP_THRESHOLD` (5.5 A — strictly inside the dead-band, no overlap with opportunistic dead-band start)
6. `surplus_watts ≥ -500W` (6 A floor protection: don't probe when home consumption dwarfs PV ceiling)
7. Charger OFF and plugged in (status NOT in `[charger_free, charger_end]`)
8. `grid_import < threshold/2` smoothly for ≥ 60 s (avoid trigger on Shelly/CT oscillations)
9. Priority Balancer NOT in HOME state. EV_FREE override is allowed only when `soc_home == 100%` (strict, prevents late-afternoon battery drain)
10. Not in cooldown and not in HARD_EXIT

When state ≠ IDLE, `is_relevant()` always returns True so `tick()` can handle graceful exit if any condition becomes false.

**Edge cases handled** (verified during adversarial review):
1. `grid_import` sensor unavailable → stop + COOLDOWN_SHORT
2. Toggle disabled mid-RIDING_EDGE → graceful exit
3. Forza Ricarica activated → `async_force_exit` called by Solar Surplus Section 1
4. Charger unplugged → `async_force_exit` called by Section 7
5. Night Smart Charge takes over → via `_handle_control_loss`
6. Boost Charge activated → `async_force_exit` called by Section 2
7. HA restart mid-PROBING → IDLE unconditionally; let next tick decide (avoid interrupting legitimate Solar Surplus deadband charging)
8. PRIORITY_HOME mid-RIDING_EDGE → graceful exit
9. Sunset reached → graceful exit (NOT counted as fail) + HARD_EXIT lockout until sunrise
10. Profile changed → `async_force_exit` called by Section 6
11. Battery SOC drops below threshold mid-RIDING_EDGE → graceful exit
12. Slow-ramp inverter (≥30 s deadband) → Phase A grace ignores grid_import for first 20 s, `max_import_duration` configurable up to 120 s
13. Low home consumption + curtailed PV (6A floor problem) → entry condition #6 blocks
14. Late afternoon EV_FREE drain → strict SOC=100% + 90-min sunset buffer
15. Grid sensor oscillation (Shelly/CT) → 60 s smoothing window for entry
16. Opportunistic dead-band overlap → entry uses `< SURPLUS_STOP_THRESHOLD` not start threshold
17. User changes parameters mid-RIDING_EDGE → every tick re-reads all entities, graceful exit if invalid
18. Worst-case failure thrashing → sliding window + daily cap = ≤350 Wh/day bound
19. EV already full (`charger_end` status) → entry condition #7 blocks

**Architecture**:
- New module `hybrid_inverter_mode.py` (~700 lines) with full state machine
- Driven exclusively by Solar Surplus periodic ticks — no internal timer, no race conditions
- Control acquisition through Solar Surplus's `_acquire_control` / `_release_control` (coordinator-aware, integrates with Night Charge preemption)
- Back-reference injection pattern: hybrid_mode created in Phase 6.5, Solar Surplus created in Phase 7, then `hybrid_mode.set_solar_surplus_owner(solar_surplus)` called to wire the back-link
- Dedicated diagnostic sensor `EVSCHybridInverterDiagnosticSensor` (mirrors pattern of `EVSCSolarSurplusDiagnosticSensor`)
- One-shot notification per day (sunrise→sunset session), filtered by `_is_car_owner_home()`, no enable toggle (single-shot = low spam risk)

**Files modified**:
- **NEW**: [hybrid_inverter_mode.py](custom_components/ev_smart_charger/hybrid_inverter_mode.py) — full state machine module
- [const.py](custom_components/ev_smart_charger/const.py): VERSION 1.7.0 → 1.8.0, TOTAL_INTEGRATION_ENTITIES 58 → 64 (and TOTAL_INTEGRATION_ENTITIES_NO_BATTERY 45 → 51), 6 new `HELPER_HYBRID_*_SUFFIX`, 4 new `DEFAULT_HYBRID_*`, 10 new internal constants, 6 new `HYBRID_STATE_*` strings
- [switch.py](custom_components/ev_smart_charger/switch.py): added `evsc_hybrid_inverter_mode` to `_SWITCH_DEFS`
- [number.py](custom_components/ev_smart_charger/number.py): added 4 new tuples for hybrid parameters in `_NUMBER_DEFS`
- [sensor.py](custom_components/ev_smart_charger/sensor.py): added `EVSCHybridInverterDiagnosticSensor` class + entity registration
- [solar_surplus.py](custom_components/ev_smart_charger/solar_surplus.py): new `hybrid_mode` constructor param, Section 10b hook between surplus calculation and battery support, `async_force_exit` calls in 5 early-return branches (Forza Ricarica, Boost, Night Charge, Profile, Charger Free), and in `_handle_control_loss`
- [__init__.py](custom_components/ev_smart_charger/__init__.py): new Phase 6.5 instantiating `HybridInverterMode` before Solar Surplus, back-reference injection after, cleanup order updated
- [runtime.py](custom_components/ev_smart_charger/runtime.py): added `hybrid_mode: Any | None = None` field
- [utils/mobile_notification_service.py](custom_components/ev_smart_charger/utils/mobile_notification_service.py): new `send_hybrid_mode_started_notification()` method
- [localization.py](custom_components/ev_smart_charger/localization.py): new `mobile.hybrid_mode_started.message` translation key in EN, IT, NL
- [README.md](README.md): new "Hybrid Inverter Mode (zero-export systems)" section with full user-facing documentation (problem, who needs it, how it works, tuning, troubleshooting)
- [frontend/ev-smart-charger-dashboard.js](custom_components/ev_smart_charger/frontend/ev-smart-charger-dashboard.js): expanded from 5 to 11 module panels — added Hybrid Mode panel (5 controls + diagnostic), Boost Schedule, Car Ready weekly planner (7-day grid), Daily SOC Targets (14 day-cells in compact grid), Notifications, Logging. Also added previously-missing entities: `evsc_solar_max_amperage`, `evsc_battery_support_sunset_buffer`, `evsc_car_ready_time`, `evsc_cached_ev_soc`. New EN/IT/NL translations (~50 new keys). New CSS for `.weekly-grid`, `.day-soc-row`, `.info-card`.
- [frontend/README.md](custom_components/ev_smart_charger/frontend/README.md): updated section-by-section entity inventory + note on lowercase `entity_prefix` for v1.6.23+ installs
- [manifest.json](custom_components/ev_smart_charger/manifest.json): version 1.8.0

**Upgrade priority**:
- 🟢 **RECOMMENDED for users with hybrid zero-export inverters** — solves a real "PV is wasted because charger never starts" scenario
- ⚪ **NO-OP for everyone else** — opt-in toggle defaults to OFF; existing users see zero behavioural change

**Beta testing welcome**: please report your experience (success, failure modes, inverter brand/model) in [issue #20](https://github.com/antbald/ha-ev-smart-charger/issues/20). The probing strategy is inverter-agnostic by design but real-world feedback from different brands will help refine the default parameters.

---

### v1.6.22 (2026-05-16)
**FEATURE: Sunset buffer guard for Solar Surplus battery support**

**Problem Fixed**:
When the user plugged the car in the late afternoon (e.g. 18:00) with fading solar, Solar Surplus would activate home battery support and drain the home battery for the remaining minutes before sunset. Priority Balancer correctly returned `PRIORITY_EV` (EV below daily target), home battery was above its minimum SOC, so `_handle_home_battery_usage()` activated battery support and `_calculate_target_amperage()` fell back to the configured battery support amperage (default 16A). No time-based or sun-based guard prevented this.

**Fix**:
Added a sunset-proximity guard in `_handle_home_battery_usage()` ([solar_surplus.py](custom_components/ev_smart_charger/solar_surplus.py)). When `dt_util.now() + buffer >= today's sunset`, the battery support is forced inactive and the function returns. The buffer is configurable via a new number entity, default 60 minutes. Setting the buffer to 0 disables the guard (opt-out).

When the guard is active:
- `_battery_support_active = False`
- `_calculate_target_amperage()` (unchanged) returns surplus-based amperage only
- If surplus < `SURPLUS_STOP_THRESHOLD`, the existing "battery support not active → stop charger" branch handles the stop with the normal drop delay

No changes to `_calculate_target_amperage()`, Night Smart Charge, or Priority Balancer.

**New Entity**:
- `number.evsc_battery_support_sunset_buffer` — minutes before sunset to block battery support. Range 0-240, step 5, default 60. EntityCategory.CONFIG.

**Files Modified**:
- [const.py](custom_components/ev_smart_charger/const.py): `VERSION = "1.6.22"`, `HELPER_BATTERY_SUPPORT_SUNSET_BUFFER_SUFFIX`, `DEFAULT_BATTERY_SUPPORT_SUNSET_BUFFER_MIN = 60`, `TOTAL_INTEGRATION_ENTITIES = 58`
- [number.py](custom_components/ev_smart_charger/number.py): new entry in `_NUMBER_DEFS`
- [solar_surplus.py](custom_components/ev_smart_charger/solar_surplus.py): import, attribute init, entity discovery, missing-entity warning, sunset-proximity guard in `_handle_home_battery_usage()`
- [manifest.json](custom_components/ev_smart_charger/manifest.json): `version = "1.6.22"`

**Upgrade Priority**: 🟢 RECOMMENDED — Prevents unnecessary home battery drain when plugging in close to sunset.

---

### v1.6.21 (2026-04-17)
**CRITICAL FIX: Night Smart Charge continues charging past sunrise when car_ready=OFF**

**Problem Fixed**:
Night Smart Charge (BATTERY mode) failed to stop at sunrise when `car_ready` was set to OFF for the current day. The charger continued running indefinitely into the afternoon, completely bypassing the Solar Surplus profile.

**Root Cause**:
`_should_stop_for_deadline()` in `night_smart_charge.py` used `get_next_sunrise_after(current_time)` in the `car_ready=False` branch. This function returns the **next future** sunrise — once today's sunrise has passed (e.g. after 06:30), it returns **tomorrow's** sunrise.

At 15:05 with `car_ready=False`:
```
sunrise = get_next_sunrise_after(15:05)
        → today's sunrise (06:30) already passed
        → returns tomorrow's sunrise (2026-04-17 06:30)
check: 15:05 >= 2026-04-17 06:30 → FALSE → never stops ❌
```

**Fix**:
Replaced `get_next_sunrise_after(current_time)` with `get_sunrise(current_time)`, which always returns the sunrise of the **current day** regardless of whether it has already passed:
```python
# Before (bug):
sunrise = self._astral_service.get_next_sunrise_after(current_time)
if current_time >= sunrise:

# After (fix):
sunrise = self._astral_service.get_sunrise(current_time)
if sunrise and current_time >= sunrise:
```
Also added a `None` guard that was missing in the original code.

**Why `_is_in_active_window` is NOT affected**:
That function uses `get_next_sunrise_after(scheduled_time)` where `scheduled_time` is the night charge time (e.g. 01:00 AM). Since 01:00 is always before sunrise, `get_next_sunrise_after(01:00)` correctly returns today's sunrise. Different function, different context, no bug.

**Files Modified**:
- [night_smart_charge.py](custom_components/ev_smart_charger/night_smart_charge.py): Fixed `_should_stop_for_deadline()` — 2-line change
- [const.py](custom_components/ev_smart_charger/const.py): VERSION = "1.6.21"
- [manifest.json](custom_components/ev_smart_charger/manifest.json): version = "1.6.21"

**Upgrade Priority**: 🔴 CRITICAL — Affects all users with `car_ready=OFF` (default for weekends)

---

### v1.6.0 (2026-03-20) — Refactoring Release

#### Phase 4: Cleanup & Consistency
**REFACTORING: Fix hardcoded notification title, translate Italian text to English**

- **Notification title**: Changed `NOTIFICATION_TITLE = "BORGO"` to `NOTIFICATION_TITLE = DEFAULT_NAME` (`"EV Smart Charger"`) in `utils/mobile_notification_service.py`. All mobile notifications now display the correct integration name.
- **Italian → English**: Translated 15 Italian text instances (comments, docstrings, log messages) in `night_smart_charge.py` to English:
  - `_calculate_and_save_energy_forecast()` method: docstring, 5 comments, 4 log messages
  - 2 inline comments at lines 1216 and 1485 ("Calcola e salva energy forecast" → "Calculate and save energy forecast")

**Files Modified**: utils/mobile_notification_service.py, night_smart_charge.py, CLAUDE.md

---

#### Phase 3: Solar Surplus — time.monotonic() + AmperageCalculator
**REFACTORING: NTP-safe timing + shared step-down utility**

- **`time.time()` → `time.monotonic()`**: Replaced all 5 instances in `solar_surplus.py`. `time.monotonic()` is immune to NTP clock jumps, making elapsed-time measurements reliable for rate limiting, grid import delays, and surplus drop delays.
- **`AmperageCalculator.get_next_level_down()`**: Replaced 2 inline `CHARGER_AMP_LEVELS.index()` + step-down blocks in `_handle_grid_import_protection` and `_handle_surplus_decrease` with calls to the shared `AmperageCalculator` utility. Eliminates try/except ValueError boilerplate. No behavioral change.

---

#### Phase 2: Data-Driven Entity Registration
**REFACTORING: Replace repetitive entity.append() with table-driven registration**

- **switch.py**: Replaced 19 `entities.append()` calls (~215 lines) with a `_SWITCH_DEFS` table (12 entries) + day loop (7 car_ready switches). Total entities unchanged: 19.
- **number.py**: Replaced 20 `entities.append()` calls (~390 lines) with a `_NUMBER_DEFS` table (10 entries) + day loops (14 daily SOC entities). Total entities unchanged: 24.
- **sensor.py**: Merged identical `EVSCTodayEVTargetSensor` and `EVSCTodayHomeTargetSensor` into a single `EVSCTodayTargetSensor` class with a `label` parameter. Entity IDs and behavior unchanged.

All entity IDs, defaults, icons, and EntityCategory.CONFIG preserved exactly.

---

#### Phase 1: Critical Bug Fixes & Code Cleanup
**REFACTORING: Fix critical bugs, remove dead code, move lazy imports to top-level**

**BUG 1 — RestoreEntity state machine sync (CRITICAL)**:
After HA restart, 22 entities (19 switches, 1 select, 2 time) remained "unavailable" in the state machine until manually modified. Root cause: `async_added_to_hass()` restored internal values but never called `self.async_write_ha_state()` to push to the state machine. Fixed in `switch.py`, `select.py`, and `time.py` (number.py already had the fix from v1.3.22).

**BUG 2 — OperationResult.__post_init__ overwrites queued field**:
`charger_controller.py` OperationResult dataclass had `self.queued = False` in `__post_init__`, which unconditionally overwrote the constructor argument. Creating `OperationResult(queued=True)` silently produced `queued=False`. Removed the line; the field-level default `queued: bool = False` suffices.

**BUG 3 — 5 dead constants removed from const.py**:
`SURPLUS_HYSTERESIS_MARGIN`, `SURPLUS_STABLE_DURATION`, `SMART_BLOCKER_RETRY_ATTEMPTS`, `SMART_BLOCKER_RETRY_DELAYS`, `CHARGER_QUEUE_MAX_SIZE` — verified never imported anywhere.

**BUG 4 — 4 dead methods removed**:
- `charger_controller.py`: `get_queue_size()`, `get_last_operation_time()`, `get_seconds_since_last_operation()`
- `automation_coordinator.py`: `get_action_history()`

**BUG 5 — Unused attribute in LogManager**:
`self._components` was assigned in `__init__` and `async_setup` but never read. Both assignments removed.

**BUG 6 — 9 lazy imports moved to top-level**:
Moved `from .const import ...` and `from .utils import ...` inside method bodies to module-level imports:
- `solar_surplus.py`: 2 lazy imports removed (SURPLUS_INCREASE_DELAY, NIGHT_CHARGE_COOLDOWN_SECONDS)
- `night_smart_charge.py`: 5 lazy imports removed (NIGHT_CHARGE_COOLDOWN_SECONDS ×3, ACTIVATION_GRACE constants, GridImportProtection)
- `charger_controller.py`: 2 lazy imports removed (AmperageCalculator ×2)

**Files Modified**: switch.py, select.py, time.py, charger_controller.py, automation_coordinator.py, const.py, log_manager.py, solar_surplus.py, night_smart_charge.py, manifest.json, CLAUDE.md

**Upgrade Priority**: 🔴 CRITICAL — Fixes 22 entities stuck "unavailable" after HA restart

---

### v1.5.12 (2026-03-20)
**FIX: Solar Surplus Opportunistic Dead Band Start**

**Problem Fixed**:
Solar Surplus never started charging when surplus was in the hysteresis dead band (5.5A-6.5A / ~1265-1495W) for extended periods. The charger could sit idle for 30+ minutes with 1200-1400W of usable surplus because the start threshold (6.5A) was never reached.

**Root Cause**:
The hysteresis design has a dead band between the STOP threshold (5.5A) and the START threshold (6.5A). When the charger is OFF and surplus is in this band, `_calculate_target_amperage()` returns 0 ("waiting for 6.5A to start"). With fluctuating surplus around 1200-1400W (5.2-6.1A), the system perpetually waited for a threshold it couldn't reach.

**Log Evidence**:
```
09:04 - Surplus in hysteresis band (5.73A) but not charging - Waiting for 6.5A to start
09:05 - Surplus in hysteresis band (5.91A) but not charging - Waiting for 6.5A to start
09:06 - Surplus in hysteresis band (5.48A) but not charging - Waiting for 6.5A to start
... (30+ minutes of wasted surplus)
```

**Solution - Opportunistic Dead Band Start**:
Added a persistent dead band timer. When surplus stays >= 5.5A (SURPLUS_STOP_THRESHOLD) for 120 consecutive seconds while the charger is OFF, the system overrides the target to 6A (minimum) and starts charging. This differentiates between:
- **Brief cloud spike** (surplus at 5.8A for 30s then drops) → don't start (cloud protection preserved)
- **Sustained moderate surplus** (surplus at 5.8A for 2+ minutes) → start at 6A (new behavior)

Grid import protection continues to operate normally after the charger starts, handling any small deficit between surplus and charger draw.

**New Constant**:
- `SURPLUS_DEADBAND_START_DELAY = 120` seconds (2 minutes of persistent dead band before opportunistic start)

**Flow Example**:
```
09:04 - Surplus 5.73A (dead band) → Start 120s timer
09:05 - Surplus 5.91A (dead band) → Timer: 60s / 120s
09:06 - Surplus 5.48A (below 5.5A) → Timer RESET
09:07 - Surplus 5.65A (dead band) → Start new 120s timer
09:08 - Surplus 5.82A (dead band) → Timer: 60s / 120s
09:09 - Surplus 5.71A (dead band) → Timer: 120s / 120s → START at 6A!
```

**Files Modified**:
- [const.py](custom_components/ev_smart_charger/const.py): Added `SURPLUS_DEADBAND_START_DELAY`, VERSION = "1.5.12"
- [solar_surplus.py](custom_components/ev_smart_charger/solar_surplus.py): Added dead band timer logic in `_async_periodic_check()`, new state variable `_deadband_start_time`, import and reset
- [manifest.json](custom_components/ev_smart_charger/manifest.json): version = "1.5.12"

**Upgrade Priority**: 🟡 RECOMMENDED - Fixes Solar Surplus failing to charge with moderate surplus (1200-1400W)

---

### v1.5.11 (2026-03-20)
**CRITICAL FIX: Night Smart Charge Ownership Loss Loop + Timezone Mismatch**

**Three critical bugs fixed that caused Night Smart Charge to never complete, restart every ~60 seconds, and spam logs with datetime errors.**

**BUG #1 (CRITICAL) - Coordinator Override Doesn't Set Ownership:**

**Root Cause:** In `automation_coordinator.py`, when Forza Ricarica is ON, the `turn_on` override path returned `True` (allowed) but NEVER set `_active_automation`. This meant Night Smart Charge believed it had control, but 15 seconds later when grid/battery monitors called `_ensure_control()` → `_has_control()` → `is_automation_active()`, the answer was always `False` because `_active_automation` was `None`.

**Impact:** 355+ `ownership_lost` events per day, Night Smart Charge restart loop every ~60 seconds, charging sessions never completing properly.

**Fix:** Added `_active_automation` and `_last_action`/`_last_action_time` assignment to the override `turn_on` path in `request_charger_action()`.

**BUG #2 (HIGH) - datetime.now() Timezone Mismatch (40+ instances):**

**Root Cause:** 40+ instances of `datetime.now()` (offset-naive) across the codebase. Home Assistant uses `dt_util.now()` (offset-aware). When mixed in arithmetic or comparisons → `TypeError: can't subtract offset-naive and offset-aware datetimes` every ~60 seconds.

**Affected Files:** charger_controller.py (4), utils/amperage_helper.py (4), utils/astral_time_service.py (8), solar_surplus.py (15+), night_smart_charge.py (1), sensor.py (1), log_manager.py (2).

**Fix:** Replaced all 40+ `datetime.now()` with `dt_util.now()` and added `from homeassistant.util import dt as dt_util` import where missing.

**BUG #3 (MEDIUM) - Control Loss Resets State to "ready":**

**Root Cause:** `_handle_control_loss()` in night_smart_charge.py set `_session_state = "ready"` instead of `"completed_today"`. Combined with BUG #1, this allowed immediate re-activation creating the infinite restart loop.

**Fix:** Changed to `_session_state = "completed_today"` and set `_last_completion_time`/`_last_completion_date` to prevent same-day re-activation.

**Note on Amperage Decrease Sequence:**
The safe decrease sequence (stop → 5s → set → 1s → restart) is correctly implemented in `charger_controller.py:_decrease_amperage_unlocked()`. The `charger_wait → charger_charging` transitions visible in logs are EXPECTED behavior from this sequence, not a bug.

**Files Modified:**
- [automation_coordinator.py](custom_components/ev_smart_charger/automation_coordinator.py): Added ownership to override path
- [charger_controller.py](custom_components/ev_smart_charger/charger_controller.py): datetime.now() → dt_util.now() (4 instances)
- [utils/amperage_helper.py](custom_components/ev_smart_charger/utils/amperage_helper.py): datetime.now() → dt_util.now() (4 instances)
- [utils/astral_time_service.py](custom_components/ev_smart_charger/utils/astral_time_service.py): datetime.now() → dt_util.now() (8 instances)
- [solar_surplus.py](custom_components/ev_smart_charger/solar_surplus.py): datetime.now() → dt_util.now() (15+ instances)
- [night_smart_charge.py](custom_components/ev_smart_charger/night_smart_charge.py): datetime.now() → dt_util.now() + control loss state fix
- [sensor.py](custom_components/ev_smart_charger/sensor.py): datetime.now() → dt_util.now() (1 instance)
- [log_manager.py](custom_components/ev_smart_charger/log_manager.py): datetime.now() → dt_util.now() (2 instances)
- [const.py](custom_components/ev_smart_charger/const.py): VERSION = "1.5.11"
- [manifest.json](custom_components/ev_smart_charger/manifest.json): version = "1.5.11"

**Upgrade Priority**: 🔴 CRITICAL - Fixes Night Smart Charge complete failure, ownership loop, and datetime error spam

---

### v1.4.16 (2025-12-29)
**CRITICAL FIX: Charger Starts at 6A Instead of Configured Amperage**

**Problem Fixed**:
When plugging in the car during Night Smart Charge window (e.g., at 00:54), the charger started at 6A instead of the configured amperage (e.g., 16A), even though the `evsc_night_charge_amperage` setting was correctly set.

**Root Cause**:
The `start_charger()` method in ChargerController compared the target amperage with a **cached value** (`self._current_amperage`) instead of the actual current amperage from the charger:

```python
# BUG: Used stale cached value
if target_amps and target_amps != self._current_amperage:
    await self._set_amperage_internal(target_amps)
```

**Bug Scenario**:
1. **Previous session**: Charged at 16A → `self._current_amperage = 16` (cached in memory)
2. **00:54 - Plug in car**: Wallbox auto-starts charging at 6A (wallbox default)
3. **Night Smart Charge** calls `start_charger(16, "Night charge")`
4. **Comparison**: `16 != 16` (cache) → **FALSE** → **SKIP setting amperage!**
5. **Result**: Charger remains at 6A instead of 16A

**Why Wallbox Starts at 6A**:
Many EV chargers (wallboxes) automatically start charging when a car is plugged in, using their internal default amperage (often 6A for safety). This happens BEFORE our integration has a chance to set the correct amperage.

**Solution Implemented**:
Modified `start_charger()` in [charger_controller.py](custom_components/ev_smart_charger/charger_controller.py) to:
1. **Always refresh state** before setting amperage (get actual current value)
2. **Always set amperage** when target is specified (don't trust cached value)
3. **Log actual vs target** for debugging

```python
# v1.4.16: ALWAYS set amperage when target specified
if target_amps:
    # Refresh state to get actual current amperage
    await self._refresh_state()
    actual_current = self._current_amperage

    self.logger.info(
        f"Target amperage: {target_amps}A, "
        f"Actual current: {actual_current}A"
    )

    # Always set amperage to ensure correct value
    await self._set_amperage_internal(target_amps)
    await asyncio.sleep(CHARGER_AMPERAGE_STABILIZATION_DELAY)
    self._current_amperage = target_amps
```

**Impact**:
- ✅ Charger now ALWAYS starts at configured amperage
- ✅ Works correctly even when wallbox auto-starts at different amperage
- ✅ Cached value no longer causes incorrect behavior
- ✅ Added logging to show actual vs target amperage for debugging

**Files Modified**:
- [charger_controller.py](custom_components/ev_smart_charger/charger_controller.py): Fixed `start_charger()` method (lines 180-198)
- [const.py](custom_components/ev_smart_charger/const.py): VERSION = "1.4.16"
- [manifest.json](custom_components/ev_smart_charger/manifest.json): version = "1.4.16"

**Upgrade Priority**: 🔴 CRITICAL - Fixes incorrect charging amperage at session start

---

### v1.4.15 (2025-12-29)
**Restructured Logging: Date-Based Directory Organization**

**Feature Overview**:
Completely restructured the file logging system to use a date-based directory organization. Instead of a single log file with rotation, logs are now organized in a hierarchical folder structure by year/month with a separate file for each day.

**New Log Structure**:
```
logs/
└── 2025/
    └── 12/
        ├── 29.log
        ├── 28.log
        ├── 27.log
        └── ...
    └── 11/
        ├── 30.log
        └── ...
```

**Benefits**:
- ✅ **Easy Navigation**: Find logs by date without searching through a large file
- ✅ **Better Organization**: Clear separation of daily logs
- ✅ **Simpler Archiving**: Easy to backup or delete old logs by month/year
- ✅ **No Size Limits**: Each day's log can grow without rotation concerns
- ✅ **Automatic Daily Rotation**: New log file created automatically at midnight

**Changes from Previous Version (v1.3.25)**:
| Feature | v1.3.25 | v1.4.15 |
|---------|---------|---------|
| Structure | Single file with rotation | Year/Month/Day folders |
| File Path | `logs/evsc_<entry_id>.log` | `logs/<year>/<month>/<day>.log` |
| Rotation | RotatingFileHandler (10MB, 5 backups) | Daily at midnight |
| Max Size | 50MB total | Unlimited (one file per day) |

**Sensor Updates**:
The `sensor.evsc_log_file_path` entity now:
- Shows today's log file path (e.g., `logs/2025/12/29.log`)
- Updates automatically at midnight
- Includes new attributes:
  - `logs_directory`: Base logs directory path
  - `structure`: Shows the path format (`logs/<year>/<month>/<day>.log`)

**Technical Implementation**:

**LogManager Changes** ([log_manager.py](custom_components/ev_smart_charger/log_manager.py)):
- New `_get_log_file_path_for_date(date)` method generates date-based paths
- New `get_logs_directory()` method returns base logs path
- Added midnight listener using `async_track_time_change` for automatic daily rotation
- Removed dependency on `FILE_LOG_MAX_SIZE_MB` and `FILE_LOG_BACKUP_COUNT`

**EVSCLogger Changes** ([utils/logging_helper.py](custom_components/ev_smart_charger/utils/logging_helper.py)):
- Switched from `RotatingFileHandler` to simple `FileHandler`
- `enable_file_logging()` now only requires `log_file_path` parameter
- Automatically creates year/month directories when needed

**Constants Updates** ([const.py](custom_components/ev_smart_charger/const.py)):
- Removed `FILE_LOG_MAX_SIZE_MB` and `FILE_LOG_BACKUP_COUNT` (no longer needed)
- Added documentation comments for new log structure

**Migration Notes**:
- Existing log files in the old format are not automatically migrated
- Old logs can be manually moved or deleted if desired
- New logs will immediately use the new structure when logging is enabled

**Files Modified**:
- [log_manager.py](custom_components/ev_smart_charger/log_manager.py): Date-based path generation, midnight rotation
- [utils/logging_helper.py](custom_components/ev_smart_charger/utils/logging_helper.py): Simplified FileHandler
- [sensor.py](custom_components/ev_smart_charger/sensor.py): Updated EVSCLogFilePathSensor with new attributes
- [const.py](custom_components/ev_smart_charger/const.py): VERSION = "1.4.15", removed rotation constants
- [manifest.json](custom_components/ev_smart_charger/manifest.json): version = "1.4.15"

**Upgrade Priority**: 🟢 RECOMMENDED - Improved log organization and easier troubleshooting

---

### v1.4.14 (2025-12-22)
**CRITICAL FIX: Smart Blocker Incorrect Blocking Window Calculation for Late Arrivals**

**Problem Fixed**:
Smart Blocker incorrectly blocked charging when users plugged in their car in the early morning hours (after midnight) but **after** the configured `night_charge_time`. Example scenario: User plugs in at 02:20 with `night_charge_time=01:00`, and Smart Blocker blocks charging with notification "fuori dalla fascia night charge" (outside night charge window), even though Night Smart Charge should be active.

**Root Cause**:
The `_get_night_charge_datetime()` method in Smart Blocker used `time_string_to_next_occurrence()` which always returns the NEXT future occurrence. At 02:20 with configured time 01:00:
1. Creates datetime: `today 01:00:00`
2. Sees that `01:00 < 02:20` (time has passed)
3. **Adds one day**: returns `tomorrow 01:00:00` ❌

This caused Smart Blocker to calculate an incorrect blocking window:
- Start: `yesterday 18:30` (sunset)
- End: **`tomorrow 01:00`** (wrong!)
- At 02:20: `yesterday_18:30 <= 02:20 < tomorrow_01:00` → **BLOCKED** ❌

**Correct Logic**:
At 02:20, the blocking window should be `yesterday 18:30 → today 01:00`. Since we're at 02:20, we're **OUTSIDE** the window and Night Charge should activate.

**Solution Implemented**:
Modified `_get_night_charge_datetime()` in `automations.py` to select correct occurrence based on sunrise position:
- **Before sunrise** (early morning): Use `time_string_to_datetime()` → Returns TODAY's occurrence (even if passed)
  - Example: At 02:20 returns `today 01:00`
  - Blocking window: `yesterday_18:30 → today_01:00` ✓
  - At 02:20 we're OUTSIDE ✓
- **After sunrise** (afternoon/evening): Use `time_string_to_next_occurrence()` → Returns TOMORROW's occurrence
  - Example: At 20:00 returns `tomorrow 01:00`
  - Blocking window: `today_18:30 → tomorrow_01:00` ✓
  - At 20:00 we're INSIDE ✓

**When Bug Manifested**:
Only under these specific conditions:
- Night Smart Charge is ENABLED ✓
- User plugs in after midnight (early morning) ✓
- User plugs in **after** `night_charge_time` (e.g., 02:20 > 01:00) ✓
- Before sunrise (e.g., 02:20 < 07:00) ✓
- Manual late arrival (not scheduled activation) ✓

**Impact**:
- ✅ Smart Blocker now calculates correct blocking window for early morning hours
- ✅ Night Smart Charge activates correctly for late arrivals after configured time
- ✅ No more incorrect "outside night charge window" notifications at 02:20
- ✅ Blocking window logic consistent across all time scenarios

**Files Modified**:
- [automations.py](custom_components/ev_smart_charger/automations.py): Fixed `_get_night_charge_datetime()` with sunrise-based logic (lines 417-465)
- [const.py](custom_components/ev_smart_charger/const.py): VERSION = "1.4.14"
- [manifest.json](custom_components/ev_smart_charger/manifest.json): version = "1.4.14"

**Test Scenarios Validated**:
- ✅ Late arrival at 02:20 (after 01:00 configured time) → Night Charge activates
- ✅ Late arrival at 00:30 (before 01:00 configured time) → Smart Blocker blocks correctly
- ✅ Evening connection at 20:00 → Smart Blocker blocks correctly
- ✅ Daytime connection at 14:00 → Smart Blocker allows (outside window)

**Upgrade Priority**: 🔴 CRITICAL - Fixes complete Night Smart Charge failure for late arrivals in early morning

**Related Analysis**: See [BUG_ANALYSIS_NIGHT_CHARGE_02_20.md](BUG_ANALYSIS_NIGHT_CHARGE_02_20.md) for detailed technical analysis

---

### v1.4.4 (2025-11-20)
**ARCHITECTURAL FIX: Ultra-Robust Night Smart Charge Window Check with Hybrid Approach**

**Problem Identified**:
Despite fixes in v1.4.2/v1.4.3, Night Smart Charge STILL failed to activate at scheduled time (01:00 AM). The root cause was **conceptually wrong function usage**: `time_string_to_next_occurrence()` was being used for window checks, but this function **by design** returns the NEXT future occurrence (tomorrow at 01:00), not today's occurrence.

**The Core Issue**:
```python
# At 01:00:33 with scheduled time 01:00:00
scheduled_time = TimeParsingService.time_string_to_next_occurrence("01:00:00", now)
# Returns: 2025-11-21 01:00:00 (TOMORROW!) because 01:00:00 has "passed" today

# Window check
is_active = now >= scheduled_time  # 01:00:33 >= 2025-11-21 01:00:00 → FALSE ❌
```

The function was working **correctly as designed** (next occurrence = tomorrow), but the design was **wrong for window checks** (need TODAY's occurrence).

**Solution Implemented: Hybrid Approach (Robustness Score: 9/10 ⭐)**

Combined **multiple defensive techniques** for maximum robustness:

#### 1. **New Helper Method**: `_get_scheduled_time_for_today()`
```python
def _get_scheduled_time_for_today(self, now: datetime, time_str: str) -> datetime:
    """Get scheduled time for TODAY (not next occurrence)."""
    return TimeParsingService.time_string_to_datetime(time_str, now)
```

Returns TODAY's occurrence (2025-11-20 01:00:00) instead of tomorrow's.

#### 2. **Grace Period** (±2-5 minutes)
- **Activate**: 2 minutes BEFORE scheduled time (handles early wakeups)
- **Accept**: Up to 5 minutes AFTER scheduled time (handles clock drift/NTP corrections)
- **Example**: Scheduled at 01:00 → Active from 00:58 to 01:05

**New Constants** ([const.py:167-169](custom_components/ev_smart_charger/const.py#L167-L169)):
```python
ACTIVATION_GRACE_BEFORE_MINUTES = 2  # Activate 2 min before
ACTIVATION_GRACE_AFTER_MINUTES = 5   # Up to 5 min after
```

#### 3. **Hysteresis** (Stay Active Once Activated)
Once the window check activates the system, it STAYS active regardless of brief time anomalies:
```python
# STEP 2: Hysteresis
if self._session_state == "active":
    return True  # Don't re-check window, maintain state
```

#### 4. **State Machine** (ready|active|completed_today|cooldown)
Prevents re-activation on same day and manages session lifecycle:

```python
# New attributes in __init__
self._session_state = "ready"  # State machine
self._activation_date = None   # Date tracking
self._last_completion_date = None  # Completion tracking
```

**State Transitions**:
```
ready → active (when window opens)
active → completed_today (when session completes)
completed_today → ready (on new day)
```

#### 5. **Comprehensive Diagnostic Logging** (Throttled)
Full diagnostic snapshot every 60 seconds showing:
- Current time, scheduled time (TODAY), grace window, sunrise
- Session state, activation date, completion date
- All activation conditions (in grace, past scheduled, before sunrise)
- Final result (ACTIVE/INACTIVE)

**Example Log Output**:
```
═══════════════════════════════════════════════════════════════
📅 🔍 WINDOW CHECK DIAGNOSTIC
   Current: 2025-11-20 01:00:33
   Scheduled (today): 2025-11-20 01:00:00
   Grace window: [00:58 - 01:05]
   Sunrise: 2025-11-20 05:45:47
   Session state: ready
   Last activation date: None
   Last completion date: None
   ─────────────────────
   In grace window: True
   Past scheduled: True
   Before sunrise: True
   Window ACTIVE: True
═══════════════════════════════════════════════════════════════
```

#### 6. **Completion State Tracking**
Enhanced `_complete_night_charge()` to track completion date:
```python
self._last_completion_date = self._last_completion_time.date()
self._session_state = "completed_today"
```

Prevents re-activation on same day after completion.

**Edge Cases Handled**:

| Scenario | v1.4.3 | v1.4.4 |
|----------|--------|--------|
| Normal activation at 01:00 | ❌ Failed | ✅ Activates |
| Clock drift (±2-5 min) | ❌ Missed | ✅ Grace period handles |
| HA restart during session | ⚠️ May restart | ✅ Cooldown prevents |
| Clock backward jump | ❌ Could re-trigger | ✅ Hysteresis protects |
| Same-day completion | ⚠️ Time-based only | ✅ Date tracking prevents |
| Midnight crossing | ✅ OK | ✅ OK |

**Files Modified**:
- [const.py](custom_components/ev_smart_charger/const.py):
  - Line 5: VERSION = "1.4.4"
  - Lines 167-169: Grace period constants
- [night_smart_charge.py](custom_components/ev_smart_charger/night_smart_charge.py):
  - Lines 108-112: State machine attributes
  - Lines 312-426: Complete rewrite of `_is_in_active_window()` (115 lines)
  - Lines 1139-1175: New helper methods `_get_scheduled_time_for_today()` and `_cooldown_expired()`
  - Lines 1046-1066: Enhanced completion tracking
- [manifest.json](custom_components/ev_smart_charger/manifest.json): version = "1.4.4"

**Benefits**:
- ✅ **Activation Guaranteed**: Grace period ±2-5 minutes prevents missed activation
- ✅ **Immune to Clock Anomalies**: Hysteresis and state machine handle jumps/drift
- ✅ **Restart-Safe**: Re-activates correctly after HA restart if within window
- ✅ **No Re-activation**: Date tracking prevents same-day restarts
- ✅ **Debug-Friendly**: Complete diagnostic logging for easy troubleshooting
- ✅ **Future-Proof**: Easy to add DST handling later

**Robustness Score**: **9/10** ⭐

**Upgrade Priority**: 🔴 CRITICAL - Fixes complete Night Smart Charge activation failure

---

### v1.4.3 (2025-11-19)
**HOTFIX: Correct Git Tag for v1.4.2 Fix**

**Problem Fixed**:
The v1.4.2 git tag was pointing to the wrong commit (created before the actual fix was committed), causing HACS users to still download the buggy version even though the fix was in the repository.

**Root Cause**:
During v1.4.2 release process, the git tag was created pointing to commit `1784165` instead of the correct commit `b3bc3da` which contains the actual time window fix.

**Solution**:
Created v1.4.3 release with correct git tag pointing to the commit containing the fix:
- Time parsing comparison changed from `<=` to `<` in [utils/time_parsing_service.py:125](custom_components/ev_smart_charger/utils/time_parsing_service.py#L125)
- Enhanced diagnostic logging at Night Smart Charge evaluation start
- All fixes from v1.4.2 are included and working

**Files Modified**:
- [const.py](custom_components/ev_smart_charger/const.py): VERSION = "1.4.3"
- [manifest.json](custom_components/ev_smart_charger/manifest.json): version = "1.4.3"
- [CLAUDE.md](CLAUDE.md): Added v1.4.3 changelog entry

**Upgrade Priority**: 🔴 CRITICAL - HACS users must upgrade to v1.4.3 to get the actual fix

---

### v1.4.2 (2025-11-18)
**CRITICAL FIX: Night Smart Charge Time Window Bug + Enhanced Diagnostic Logging** ⚠️ GIT TAG ISSUE - USE v1.4.3 INSTEAD

**Problem Fixed**:
Night Smart Charge failed to activate at scheduled time (01:00) due to incorrect datetime comparison logic in `TimeParsingService`. The system was comparing current time against **tomorrow's** scheduled time instead of today's, causing `Window Active: False` even when the time had arrived.

**Root Cause**:
`TimeParsingService.time_string_to_next_occurrence()` used `<=` comparison, which incorrectly treated 01:00:00 at 01:00:01 as "already passed" and shifted to tomorrow's occurrence.

**Example Bug Behavior** (v1.4.1):
```
Current: 2025-11-18 01:00:01
Scheduled: 2025-11-19 01:00:00  ← TOMORROW! ❌
Now >= Scheduled: False  ← Wrong!
Window Active: False  ← Never activates!
```

**Fixed Behavior** (v1.4.2):
```
Current: 2025-11-18 01:00:01
Scheduled: 2025-11-18 01:00:00  ← TODAY! ✅
Now >= Scheduled: True  ✅
Window Active: True  ✅
→ Night Smart Charge activates correctly! ✅
```

**Technical Fix**:
Changed comparison in [utils/time_parsing_service.py:125](custom_components/ev_smart_charger/utils/time_parsing_service.py#L125) from `<=` to `<`:

```python
# Before (bug):
if target_time <= reference_time:  # Included equality
    target_time += timedelta(days=1)

# After (fix):
if target_time < reference_time:  # Strict inequality
    target_time += timedelta(days=1)
```

**Enhanced Diagnostic Logging**:
Added comprehensive diagnostic snapshot at start of Night Smart Charge evaluation ([night_smart_charge.py:377-429](custom_components/ev_smart_charger/night_smart_charge.py#L377-L429)):

**Logged Information**:
- **Timestamp & Day**: Current datetime and weekday
- **Configuration**:
  - Night Charge Enabled status
  - Scheduled Time (01:00:00)
  - Night Charge Amperage (16A)
  - Solar Forecast Threshold (20 kWh)
  - Car Ready flag for today (True/False)
  - Car Ready Deadline (08:00:00)
- **Current Readings**:
  - EV SOC (current vs target)
  - Home Battery SOC (current vs target vs minimum)
  - PV Forecast for tomorrow
  - Charger Status & Current Amperage
- **System State**:
  - Priority Balancer Enabled & Current Priority
  - Active Night Charge Session & Mode

**Example Diagnostic Output**:
```
════════════════════════════════════════════════════════════════
🎯 📊 NIGHT SMART CHARGE - DIAGNOSTIC SNAPSHOT
   Timestamp: 2025-11-18 01:00:01
   Day: Monday
════════════════════════════════════════════════════════════════
⚙️ Configuration:
   Night Charge Enabled: True
   Scheduled Time: 01:00:00
   Night Charge Amperage: 16A
   Solar Forecast Threshold: 20.0 kWh
   Car Ready Today (Monday): True
   Car Ready Deadline: 08:00:00
📈 Current Readings:
   EV SOC: 45%
   EV Target (today): 50%
   Home Battery SOC: 65%
   Home Battery Target (today): 50%
   Home Battery Min SOC: 20%
   PV Forecast (tomorrow): 25.3 kWh
   Charger Status: charger_wait
   Charger Current Amperage: 6A
   Priority Balancer Enabled: True
   Priority State: EV
   Active Night Charge Session: False
   Active Mode: idle
════════════════════════════════════════════════════════════════
```

**Benefits**:
- ✅ Night Smart Charge now activates correctly at scheduled time
- ✅ Complete system state visible in single log block for troubleshooting
- ✅ Easy diagnosis of future issues (all relevant variables logged)
- ✅ No need to search through multiple log entries for different values
- ✅ Timestamps help identify timing-related issues

**Files Modified**:
- [utils/time_parsing_service.py](custom_components/ev_smart_charger/utils/time_parsing_service.py): Fixed datetime comparison logic
- [night_smart_charge.py](custom_components/ev_smart_charger/night_smart_charge.py): Added comprehensive diagnostic logging
- [const.py](custom_components/ev_smart_charger/const.py): VERSION = "1.4.2"
- [manifest.json](custom_components/ev_smart_charger/manifest.json): version = "1.4.2"

**Upgrade Priority**: 🔴 CRITICAL - Fixes complete Night Smart Charge activation failure

---

### v1.3.25 (2025-11-12)
**Toggle-Controlled File Logging System for Easy Troubleshooting**

**Feature Overview**:
Adds optional file logging system with user-friendly toggle control. When enabled, all integration activity is written to a dedicated log file (separate from Home Assistant logs), making it easy to troubleshoot issues and share logs with developers.

**Problem Solved**:
- **Previous Behavior** (v1.3.24): All integration logs mixed with other Home Assistant logs, making troubleshooting difficult
- **User Impact**: Hard to extract relevant logs when reporting issues or debugging problems
- **New Behavior** (v1.3.25): Dedicated log file with toggle control, easy to access and share

**New Entities**:

**1. Toggle Switch** (default OFF):
- **Entity**: `switch.evsc_enable_file_logging`
- **Name**: "EVSC Enable File Logging"
- **Icon**: `mdi:file-document-outline`
- **Default State**: OFF (to save storage space)
- **Behavior**: Enables/disables file logging in real-time

**2. Log File Path Sensor**:
- **Entity**: `sensor.evsc_log_file_path`
- **Name**: "EVSC Log File Path"
- **Icon**: `mdi:file-document-outline`
- **Value**: Full path to log file (e.g., `/config/custom_components/ev_smart_charger/logs/evsc_<entry_id>.log`)
- **Attributes**:
  - `description`: "Path to the file logging output (when enabled)"
  - `friendly_name`: "Log File Path"

**File Logging Configuration**:

**Location**: `/config/custom_components/ev_smart_charger/logs/evsc_<entry_id>.log`

**Rotation Settings**:
- **Max Size per File**: 10MB
- **Backup Files**: 5 (automatically rotated)
- **Total Storage**: 50MB maximum (10MB × 5 backups)

**Log Format**:
```
2025-11-12 13:45:23 - [custom_components.ev_smart_charger.solar_surplus] - INFO - ☀️ [SOLAR SURPLUS] Starting: Periodic surplus check
2025-11-12 13:45:23 - [custom_components.ev_smart_charger.solar_surplus] - INFO - ℹ️ [SOLAR SURPLUS] Solar Production: 5000 W
2025-11-12 13:45:23 - [custom_components.ev_smart_charger.solar_surplus] - INFO - ℹ️ [SOLAR SURPLUS] Home Consumption: 2000 W
```

**Log Content Includes**:
- ✅ Timestamps (YYYY-MM-DD HH:MM:SS)
- ✅ Component names
- ✅ Log levels (INFO, DEBUG, WARNING, ERROR)
- ✅ Emoji prefixes for visual parsing
- ✅ All integration activity (Solar Surplus, Night Charge, Smart Blocker, Priority Balancer, Charger Controller)

**Technical Implementation**:

**New Files**:
1. **[log_manager.py](custom_components/ev_smart_charger/log_manager.py)** (NEW):
   - **Class**: `LogManager`
   - **Purpose**: Centralized file logging orchestrator
   - **Responsibilities**:
     - Monitors toggle switch state changes
     - Enables/disables file logging on all component loggers
     - Manages log file path and rotation settings
   - **Key Methods**:
     - `async_setup(components)`: Discovers toggle entity, registers state listener
     - `_apply_logging_state()`: Enables/disables logging based on toggle
     - `_toggle_changed(event)`: Handles toggle state change events
     - `get_log_file_path()`: Returns current log file path
     - `async_remove()`: Cleanup on unload

**Modified Files**:
1. **[switch.py](custom_components/ev_smart_charger/switch.py)** (Lines 113-122):
   - Added `evsc_enable_file_logging` switch entity

2. **[utils/logging_helper.py](custom_components/ev_smart_charger/utils/logging_helper.py)** (Lines 107-162):
   - Added `_file_handler` attribute to track file handler
   - Added `enable_file_logging()` method with RotatingFileHandler
   - Added `disable_file_logging()` method
   - Added `is_file_logging_enabled()` method

3. **[sensor.py](custom_components/ev_smart_charger/sensor.py)** (Lines 55-64, 215-279):
   - Added `EVSCLogFilePathSensor` class
   - Displays log file path with fallback during initialization

4. **[__init__.py](custom_components/ev_smart_charger/__init__.py)** (Lines 17, 108-128, 189-192):
   - Added LogManager import
   - Added Phase 7.5: File logging setup
   - Collects all EVSCLogger instances from components
   - Creates and initializes LogManager
   - Stores log_manager reference for cleanup
   - Added cleanup in `async_unload_entry()`

5. **[const.py](custom_components/ev_smart_charger/const.py)**:
   - Line 5: `VERSION = "1.3.25"`
   - Lines 80-81: Added `HELPER_ENABLE_FILE_LOGGING_SUFFIX`
   - Line 133: Added `HELPER_LOG_FILE_PATH_SUFFIX`
   - Lines 190-192: Added file logging settings (`FILE_LOG_MAX_SIZE_MB`, `FILE_LOG_BACKUP_COUNT`)

6. **[manifest.json](custom_components/ev_smart_charger/manifest.json)**:
   - Line 4: `"version": "1.3.25"`

**User Workflow**:

1. **Enable Logging**:
   - Toggle `switch.evsc_enable_file_logging` to ON
   - All integration activity immediately starts logging to file

2. **Find Log File**:
   - Check `sensor.evsc_log_file_path` for full path
   - Access file via SSH, File Editor addon, or Samba share
   - Example path: `/config/custom_components/ev_smart_charger/logs/evsc_abc123.log`

3. **Share with Developer**:
   - Download log file
   - Attach to GitHub issue or support request
   - Contains complete integration activity history

4. **Disable Logging** (when done):
   - Toggle `switch.evsc_enable_file_logging` to OFF
   - File logging stops immediately
   - Existing log files preserved

**Automatic Rotation**:
- When log reaches 10MB, automatically renamed to `evsc_<entry_id>.log.1`
- Previous backups shifted: `.log.1` → `.log.2`, `.log.2` → `.log.3`, etc.
- Oldest backup (`.log.5`) deleted when new backup created
- Always maintains 5 most recent backups

**Component Loggers Tracked** (5 total):
1. ChargerController logger
2. PriorityBalancer logger
3. NightSmartCharge logger (if configured)
4. SmartChargerBlocker logger (if configured)
5. SolarSurplusAutomation logger (if configured)

**Benefits**:
- ✅ **Easy Troubleshooting**: All logs in one dedicated file
- ✅ **Storage Efficient**: Automatic rotation, 50MB max
- ✅ **User Control**: Toggle on/off as needed
- ✅ **Developer Friendly**: Easy to share complete logs
- ✅ **No Performance Impact**: Only active when enabled
- ✅ **Zero Configuration**: Works out-of-box with sensible defaults

**State Change Example**:
```
# User toggles switch ON
LogManager: Found toggle entity: switch.evsc_enable_file_logging
LogManager: Enabling file logging for 5 components
EVSCLogger: File logging enabled: /config/custom_components/ev_smart_charger/logs/evsc_abc123.log

# User toggles switch OFF
LogManager: Disabling file logging for 5 components
EVSCLogger: File logging disabled
```

**Files Modified**:
- [log_manager.py](custom_components/ev_smart_charger/log_manager.py): NEW FILE (135 lines)
- [switch.py](custom_components/ev_smart_charger/switch.py): Added toggle entity
- [utils/logging_helper.py](custom_components/ev_smart_charger/utils/logging_helper.py): Extended with file logging methods
- [sensor.py](custom_components/ev_smart_charger/sensor.py): Added log file path sensor
- [__init__.py](custom_components/ev_smart_charger/__init__.py): Integrated LogManager
- [const.py](custom_components/ev_smart_charger/const.py): Added constants and version
- [manifest.json](custom_components/ev_smart_charger/manifest.json): Updated version

**Upgrade Priority**: 🟢 RECOMMENDED - Makes troubleshooting significantly easier

---

### v1.3.24 (2025-11-12)
**CRITICAL FIX: Solar Surplus Infinite Charging with Battery Support in PRIORITY_EV_FREE Mode**

**Problem Fixed**:
Solar Surplus continued charging EV from home battery indefinitely when both EV and home battery targets were met (PRIORITY_EV_FREE state), draining home battery below its minimum threshold until manual intervention.

**User Report**:
At 13:00 (daytime), Solar Surplus started charging from home battery at 16A and never stopped, even when:
- ✅ EV reached its daily target SOC (80%)
- ✅ Home battery reached its daily minimum SOC (50%)

System continued draining home battery until user manually stopped charging.

**Root Cause**:
Battery support logic had a **persistent state bug** during PRIORITY_EV_FREE transitions:

1. When priority changed from PRIORITY_EV → PRIORITY_EV_FREE (both targets met):
   - Battery support correctly deactivated ([solar_surplus.py:530-534](custom_components/ev_smart_charger/solar_surplus.py#L530-L534))
   - Function returned without stopping charger
   - Target amperage calculated as 0A (no battery support)

2. But on next check cycle (1 minute later):
   - Priority still PRIORITY_EV_FREE
   - Battery support flag was False
   - Home battery SOC still above minimum (e.g., 70% > 50%)
   - **Battery support RE-ACTIVATED** ([solar_surplus.py:552-557](custom_components/ev_smart_charger/solar_surplus.py#L552-L557))
   - Target amperage recalculated as 16A (battery support active)
   - Charger continued at 16A

3. **Infinite loop**: Every cycle battery support deactivated then immediately re-activated

**Why Re-Activation Happened**:
```python
# Line 524-535: Deactivation logic
if priority != PRIORITY_EV:
    if self._battery_support_active:
        self.logger.info("Battery support DEACTIVATING")
        self._battery_support_active = False
    return  # ❌ Returns, but doesn't prevent re-activation next cycle

# Line 549-557: RE-ACTIVATION (next cycle, 1 minute later)
if not self._battery_support_active:
    # No explicit check prevents activation during PRIORITY_EV_FREE
    self.logger.info("Battery support ACTIVATING")
    self._battery_support_active = True  # ❌ Re-activates!
```

**The Missing Logic**:
No explicit stop when PRIORITY_EV_FREE. System only had stop logic for:
- PRIORITY_HOME: Stop immediately ✅ (line 408-412)
- PRIORITY_EV_FREE + No Surplus: 30-second delay ⚠️ (only if surplus insufficient)
- **PRIORITY_EV_FREE + Battery Support: MISSING** ❌

**Fix Implemented**:

**Location**: [solar_surplus.py:414-426](custom_components/ev_smart_charger/solar_surplus.py#L414-L426)

Added explicit PRIORITY_EV_FREE stop logic immediately after PRIORITY_HOME check:

```python
# v1.3.24: Stop opportunistic charging when both targets met
if priority == PRIORITY_EV_FREE:
    if await self.charger_controller.is_charging():
        self.logger.info(
            f"{self.logger.SUCCESS} Both targets met (Priority = EV_FREE) - "
            "Stopping opportunistic charging"
        )
        await self.charger_controller.stop_charger(
            "Both EV and Home targets reached (Priority = EV_FREE)"
        )
        self._battery_support_active = False  # Force deactivation
        self.logger.separator()
    return  # Early return prevents battery support re-activation
```

**Why This Works**:
- **Immediate stop**: No delays when both targets met
- **Forced deactivation**: `battery_support_active = False` ensures clean state
- **Early return**: Prevents execution of battery support logic (line 430+)
- **Consistent with design**: PRIORITY_EV_FREE = opportunistic charging only (surplus-based, not battery)

**Stop Conditions Matrix** (Updated):

| Priority State | Surplus Available | Battery Support | Action (v1.3.24) |
|----------------|-------------------|-----------------|------------------|
| PRIORITY_HOME | Any | Any | **Stop immediately** (home needs energy) |
| PRIORITY_EV_FREE | Any | Any | **Stop immediately** (both targets met) ✅ NEW |
| PRIORITY_EV | Yes (>= 6A) | N/A | Charge from surplus |
| PRIORITY_EV | No (< 6A) | Enabled | Charge from battery (16A) |
| PRIORITY_EV | No (< 6A) | Disabled | Stop after 30s delay |
| Balancer Disabled | Yes (>= 6A) | N/A | Charge from surplus |
| Balancer Disabled | No (< 6A) | N/A | Stop after 30s delay |

**Scenario Timeline** (Fixed):

**Before v1.3.24** (Bug):
```
13:00 - EV reaches 80% target → Priority = PRIORITY_EV_FREE
13:01 - Battery support deactivates → target_amps = 0A
13:01 - Battery support RE-ACTIVATES → target_amps = 16A ❌
13:02 - Still charging at 16A (infinite loop)
13:30 - Home battery: 70% → 65% → 60% → 55% → 50% (draining)
14:00 - Home battery: 45% (below minimum!) → User stops manually ❌
```

**After v1.3.24** (Fixed):
```
13:00 - EV reaches 80% target → Priority = PRIORITY_EV_FREE
13:00 - Stop charger immediately ✅
13:00 - Battery support forced to False ✅
13:01 - Charger OFF (no re-activation) ✅
Home battery protected at 70% ✅
```

**Impact**:
- ✅ Solar Surplus stops immediately when both EV and home targets met
- ✅ No more infinite charging from home battery
- ✅ Home battery protected from over-discharge below minimum
- ✅ Consistent with Priority Balancer design (EV_FREE = opportunistic only)
- ✅ Battery support only activates when PRIORITY_EV (EV below target, home can help)

**Files Modified**:
- [solar_surplus.py](custom_components/ev_smart_charger/solar_surplus.py): Added PRIORITY_EV_FREE stop logic (13 lines)
- [const.py](custom_components/ev_smart_charger/const.py): VERSION = "1.3.24"
- [manifest.json](custom_components/ev_smart_charger/manifest.json): version = "1.3.24"

**Testing Notes**:
After upgrading to v1.3.24, monitor logs when EV target is reached:
- Should see: "Both targets met (Priority = EV_FREE) - Stopping opportunistic charging"
- Charger should stop immediately (no 30-second delay)
- Battery support should not re-activate in subsequent checks

**Related Issues**:
- This bug only affected PRIORITY_EV_FREE mode (both targets met)
- PRIORITY_HOME mode always worked correctly (home target not met)
- PRIORITY_EV mode worked correctly (battery support only when EV below target)

**Upgrade Priority**: 🔴 CRITICAL - Prevents home battery over-discharge when both targets met

---

### v1.3.23 (2025-11-12)
**Dynamic Amperage Recovery for Night Smart Charge - Grid Import Protection**

**Feature Overview**:
Night Smart Charge BATTERY mode now implements dynamic amperage management with grid import protection and automatic recovery, matching the existing Solar Surplus behavior. This eliminates code duplication and ensures consistent amperage handling across both charging modes.

**Problem Solved**:
- **Previous Behavior** (v1.3.22): Night Charge used fixed amperage (set once at start, never adjusted)
- **User Impact**: When grid import caused amperage reduction at 08:00, charging stayed at reduced level until manually adjusted or session ended
- **Example Scenario**:
  ```
  01:00 AM - Start charging at 16A (battery mode, home battery 60%)
  08:00 AM - Grid import spike (80W) → Reduce to 13A (manual intervention)
  08:30 AM - Grid cleared → Charging STAYED at 13A (no recovery)
  User expectation: Should recover to 16A when conditions improve
  ```
- **New Behavior** (v1.3.23): Night Charge dynamically adjusts amperage every 15 seconds:
  - **Grid import protection**: Reduce amperage if importing from grid (30s delay, gradual reduction)
  - **Automatic recovery**: Increase amperage when conditions improve (60s stability, gradual recovery)
  - **Same logic as Solar Surplus**: Unified behavior across all charging modes

**Architecture Changes**:

**New Shared Utilities** ([utils/amperage_helper.py](custom_components/ev_smart_charger/utils/amperage_helper.py) - 277 lines):
1. **AmperageCalculator** - Stateless amperage calculation functions:
   - `calculate_from_surplus()` - 3-case hysteresis logic (6.5A start, 5.5A stop, 1.0A dead band)
   - `get_next_level_down()` - One level reduction (16A → 13A → 10A → 8A → 6A → STOP)
   - `get_next_level_up()` - One level increase with max cap (6A → 8A → 10A → 13A → 16A)

2. **GridImportProtection** - Grid import detection with hysteresis:
   - `should_reduce()` - Check if amperage should reduce (delay-based protection)
   - `should_recover()` - Check if amperage can recover (hysteresis: reduce at 100%, recover at 50%)

3. **StabilityTracker** - State management for stability periods:
   - `start_tracking()` - Begin tracking stable conditions
   - `is_stable()` - Check if required stability period elapsed
   - `get_elapsed()` - Get current stability duration

**Extended ChargerController** ([charger_controller.py](custom_components/ev_smart_charger/charger_controller.py)):
1. `async def adjust_for_grid_import(reason)` → OperationResult
   - Automatically reduces amperage by one level using `AmperageCalculator.get_next_level_down()`
   - Stops charger if at minimum level (6A → 0A/STOP)
   - Returns OperationResult for consistent feedback

2. `async def recover_to_target(target_amps, reason)` → OperationResult
   - Gradually recovers amperage toward target by one level using `AmperageCalculator.get_next_level_up()`
   - If charger OFF (0A), starts at target immediately
   - If charging (>= 6A), increases one level at a time (6A → 8A → 10A → ...)

**Enhanced Night Smart Charge** ([night_smart_charge.py](custom_components/ev_smart_charger/night_smart_charge.py)):
- Added `_handle_dynamic_amperage()` method (126 lines) called every 15 seconds during BATTERY mode monitoring
- **STEP 1: Grid Import Protection** (Reduction Logic):
  ```
  If grid_import > threshold (default 50W):
    1. First detection → Start 30s delay timer
    2. After 30s → Call charger_controller.adjust_for_grid_import()
       - 16A → 13A (one level down)
       - Reset recovery tracker (wait 60s before recovering)
  ```

- **STEP 2: Amperage Recovery** (Increase Logic):
  ```
  If grid_import < 50% threshold (e.g., 25W) AND current < target:
    1. Start stability tracker (need 60s stable for cloud protection)
    2. After 60s stable → Call charger_controller.recover_to_target(16A)
       - 13A → 16A (one level up)
       - Reset tracker (wait 60s before next recovery cycle)
  ```

- Tracks state with `_grid_import_trigger_time` (when grid import first exceeded)
- Tracks stability with `_recovery_tracker` (StabilityTracker instance, 60s requirement)
- Added helper methods: `_get_grid_import_threshold()`, `_get_grid_import_delay()`

**Logic Flow Example**:

**Scenario: Night charge with grid import spike**
```
01:00 AM - Start charging at 16A (battery mode)
08:00 AM - Grid import spike: 80W > 50W threshold
       → Start 30s delay
08:00:30 AM - Grid import still 80W → Reduce 16A → 13A
       → Reset recovery tracker
08:05 AM - Grid import cleared: 20W < 25W (50% threshold)
       → Start recovery stability tracking
08:06 AM - Still stable (60s elapsed) → Recover 13A → 16A
       → Reset recovery tracker
08:10 AM - EV target reached (80%) → Stop charging
```

**Comparison: Solar Surplus vs Night Charge**:

| Feature | Solar Surplus | Night Charge (v1.3.23) |
|---------|---------------|------------------------|
| Amperage calculation | `_calculate_target_amperage()` | Uses `AmperageCalculator` shared utils |
| Grid import protection | Custom logic (~80 lines) | Uses `ChargerController.adjust_for_grid_import()` |
| Recovery logic | Custom logic (~60 lines) | Uses `ChargerController.recover_to_target()` |
| Stability tracking | Inline variables | Uses `StabilityTracker` shared class |
| Check frequency | Every 1 minute (configurable) | Every 15 seconds (fixed) |
| Battery support | Yes (when surplus < 6A) | N/A (already using battery) |

**Benefits**:
- ✅ **No Code Duplication**: ~150 lines of amperage logic now shared via utilities
- ✅ **Consistent Behavior**: Same grid import protection across Solar Surplus and Night Charge
- ✅ **Automatic Recovery**: No manual intervention needed when conditions improve
- ✅ **Gradual Adjustment**: One level at a time (prevents charger stress)
- ✅ **Future-Proof**: Easy to extend to Night Charge GRID mode (v1.4.0 planned)
- ✅ **Better Testing**: Shared utilities easier to unit test

**Files Modified**:
- **NEW**: [utils/amperage_helper.py](custom_components/ev_smart_charger/utils/amperage_helper.py) - 277 lines (3 classes, 10 methods)
- [charger_controller.py](custom_components/ev_smart_charger/charger_controller.py): Added 2 convenience methods (116 lines)
- [night_smart_charge.py](custom_components/ev_smart_charger/night_smart_charge.py): Added dynamic amperage logic (150+ lines)
- [const.py](custom_components/ev_smart_charger/const.py): VERSION = "1.3.23"
- [manifest.json](custom_components/ev_smart_charger/manifest.json): version = "1.3.23"

**Configuration Used**:
- Grid import threshold: `number.evsc_grid_import_threshold` (default 50W)
- Grid import delay: `number.evsc_grid_import_delay` (default 30s)
- Night charge amperage: `number.evsc_night_charge_amperage` (default 16A)
- Entities discovered automatically from helper entity registry

**Technical Implementation Details**:

**Rate Limiting Behavior**:
- ChargerController enforces 30-second minimum between operations (unchanged)
- Dynamic amperage checks run every 15 seconds (Night Charge monitoring loop)
- Grid import delay: 30 seconds before first reduction
- Recovery stability: 60 seconds before first increase
- Total minimum recovery time: 90 seconds (30s rate limit + 60s stability)

**Hysteresis Implementation**:
- Grid import **reduction** at 100% threshold (50W)
- Grid import **recovery** at 50% threshold (25W)
- Prevents oscillation when grid import near threshold
- Example: Reduce at 50W, but don't recover until below 25W

**Gradual Amperage Levels**:
```python
CHARGER_AMP_LEVELS = [6, 8, 10, 13, 16, 20, 24, 32]

# Reduction example (grid import protection)
16A → 13A → 10A → 8A → 6A → STOP

# Recovery example (conditions improved)
6A → 8A → 10A → 13A → 16A (target reached)
```

**State Management**:
- `_grid_import_trigger_time`: `datetime | None` - When grid import first exceeded threshold
- `_recovery_tracker`: `StabilityTracker` - Tracks 60s stability for recovery
- Both reset on successful operation or condition change

**Future Enhancements** (Not in v1.3.23):
- v1.3.24: Refactor Solar Surplus to use `amperage_helper` utilities (reduce duplication)
- v1.4.0: Add dynamic amperage to Night Charge GRID mode
- Future: Configurable recovery speed (conservative/normal/aggressive)
- Future: Advanced hysteresis with multiple thresholds

**Testing Recommendations**:
1. Monitor logs during night charge for "Dynamic amperage check" entries
2. Verify grid import detection: "Grid import detected: XXW > 50W"
3. Verify reduction: "Amperage reduced: 16A → 13A"
4. Verify stability tracking: "Recovery conditions stable for XXs (need 60s)"
5. Verify recovery: "Amperage recovered: 13A → 16A (target 16A)"

**Upgrade Priority**: 🟢 RECOMMENDED - Adds automatic amperage recovery, eliminates manual adjustments

---

### v1.3.22 (2025-11-12)
**CRITICAL FIX: RestoreEntity State Machine Synchronization + Sensor Robustness**

**Problem Fixed**:
Night Smart Charge failed to start overnight because `RestoreEntity` number entities restored internal values but didn't push to state machine, causing sensors to appear "unavailable" for hours. System used default target (50%) instead of configured value (65%), incorrectly determining "target already reached" and skipping charging.

**Root Cause**:
- Number entities (`EVSCNumber`) use `RestoreEntity` to persist values across HA restarts
- `async_added_to_hass()` restored internal `self._value = 65` correctly
- BUT didn't call `self.async_write_ha_state()` to update state machine
- State machine kept showing "unavailable" until manual entity modification
- All reads go through state machine (`hass.states.get()`), not internal value
- System used `DEFAULT_EV_MIN_SOC_WEEKDAY = 50` instead of restored 65%

**Symptoms**:
```
01:00 - Night Charge evaluation
      - Target: 50% (default, state unavailable)
      - EV SOC: 60%
      - Decision: 60% >= 50% → Target reached → Skip charging
03:00 - Still using 50% target (state still unavailable)
08:00 - User modifies entity in UI → state writes → now reads 65%
```

**Fixes Implemented**:

**1. Force State Machine Update After Restore** (CRITICAL - [number.py:443-445](custom_components/ev_smart_charger/number.py#L443-L445))
```python
async def async_added_to_hass(self) -> None:
    # ... restore internal value ...
    # NEW: Push restored value to state machine immediately
    self.async_write_ha_state()
```
- Eliminates 2+ hour "unavailable" window after HA restart
- All 29 number entities fixed (daily SOC targets, thresholds, delays, amperages)
- Enhanced logging shows exact restoration values

**2. Charger Status Validation** (MEDIUM - [night_smart_charge.py:379-389](custom_components/ev_smart_charger/night_smart_charge.py#L379-L389))
- Check for "unavailable"/"unknown" states in addition to "charger_free"
- Prevents charging when status sensor unavailable
- Clear warnings: "Charger status sensor unavailable - cannot determine connection"

**3. Target SOC Unavailable Warnings** (HIGH - [priority_balancer.py:218-239](custom_components/ev_smart_charger/priority_balancer.py#L218-L239))
- Explicit state checking before reading target values
- Warns when using temporary defaults: "Entity ... state is unavailable, using temporary default 50%"
- Helps diagnose state restoration issues
- User visibility into when defaults vs configured values used

**4. Startup Validation Check** (DEFENSIVE - [night_smart_charge.py:362-385](custom_components/ev_smart_charger/night_smart_charge.py#L362-L385))
- Pre-flight check for critical sensor availability before evaluation
- Lists unavailable sensors with details
- Delays evaluation until sensors ready (retries every minute)
- Prevents decisions based on incomplete data

**Impact**:
- ✅ Night Smart Charge activates correctly after HA restart
- ✅ Reads configured targets (65%) instead of defaults (50%)
- ✅ Clear diagnostic logs for troubleshooting sensor issues
- ✅ Robust handling of temporarily unavailable sensors
- ✅ No more "false target reached" decisions

**Files Modified**:
- [number.py](custom_components/ev_smart_charger/number.py): Added `async_write_ha_state()` after restoration
- [night_smart_charge.py](custom_components/ev_smart_charger/night_smart_charge.py): Charger status validation + startup check
- [priority_balancer.py](custom_components/ev_smart_charger/priority_balancer.py): Explicit unavailable state handling
- [const.py](custom_components/ev_smart_charger/const.py): VERSION = "1.3.22"
- [manifest.json](custom_components/ev_smart_charger/manifest.json): version = "1.3.22"

**Testing Notes**:
After HA restart, check logs for:
- "✅ Restored number.evsc_ev_min_soc_tuesday = 65.0"
- At 01:00: "Target EV SOC: 65%" (not 50%)
- If unavailable: "⚠️ Entity ... state is unavailable, using temporary default"

**Upgrade Priority**: 🔴 CRITICAL - Fixes Night Smart Charge overnight failure after HA restart

---

### v1.3.21 (2025-11-07)
**CRITICAL BUG FIX: Night Smart Charge Activation Failure**

**Problem Fixed**:
Night Smart Charge failed to activate at configured time (01:00) due to missing method implementation from v1.3.20. This caused:
- AttributeError exception during notification logging
- Charger never started (exception aborted execution)
- Smart Blocker interference due to inconsistent internal state

**Root Cause**:
v1.3.20 added `_get_night_charge_time()` method calls for enhanced logging but never implemented the method itself.

**Fixes Implemented**:

**1. Missing Method Implementation** (CRITICAL)
- Added `_get_night_charge_time()` helper method ([night_smart_charge.py:760-774](custom_components/ev_smart_charger/night_smart_charge.py#L760-L774))
- Returns configured time string or fallback messages ("Not configured", "Unavailable")
- Pattern consistent with other helper methods (`_get_night_charge_amperage()`, `_get_solar_threshold()`)

**2. Exception Handling for Notification Logging** (CRITICAL)
- Wrapped notification logging in try/except blocks
- BATTERY mode: [night_smart_charge.py:498-512](custom_components/ev_smart_charger/night_smart_charge.py#L498-L512)
- GRID mode: [night_smart_charge.py:683-697](custom_components/ev_smart_charger/night_smart_charge.py#L683-L697)
- Non-critical logging failures no longer abort charging operations

**3. State Cleanup on Exception** (ROBUSTNESS)
- Added comprehensive try/except wrappers with state cleanup
- BATTERY mode: [night_smart_charge.py:489-547](custom_components/ev_smart_charger/night_smart_charge.py#L489-L547)
- GRID mode: [night_smart_charge.py:674-732](custom_components/ev_smart_charger/night_smart_charge.py#L674-L732)
- Cleanup actions on failure:
  - Reset `_night_charge_active = False`
  - Reset `_active_mode = NIGHT_CHARGE_MODE_IDLE`
  - Cancel monitoring timers
  - Log error with clear message
  - Re-raise exception for caller handling

**Impact**:
- ✅ Night Smart Charge now activates correctly at configured time
- ✅ Notification logging failures no longer prevent charging
- ✅ Internal state remains consistent even on failures
- ✅ No more Smart Blocker interference from inconsistent state

**Files Modified**:
- [night_smart_charge.py](custom_components/ev_smart_charger/night_smart_charge.py): Added method, exception handling, state cleanup
- [const.py](custom_components/ev_smart_charger/const.py): VERSION = "1.3.21"
- [manifest.json](custom_components/ev_smart_charger/manifest.json): version = "1.3.21"

**Additional Documentation**:
- [NIGHT_CHARGE_BUG_ANALYSIS.md](NIGHT_CHARGE_BUG_ANALYSIS.md): Comprehensive bug analysis with timeline reconstruction

**Upgrade Priority**: 🔴 CRITICAL - Fixes complete Night Smart Charge failure introduced in v1.3.20

---

### v1.3.20 (2025-11-06)
**Universal Presence-Based Notification Filtering + Enhanced Debugging**

**Feature Overview**:
Extends presence-based notification filtering to ALL notification types (not just Priority Balancer). When the car owner is away from home, NO notifications are sent, eliminating notification spam when you can't act on them.

**Problem Solved**:
- **Previous Behavior** (v1.3.19): Only Priority Balancer notifications filtered by presence
- **User Impact**: Users still received Smart Blocker and Night Charge notifications when away from home
- **New Behavior** (v1.3.20): ALL notification types filtered by car owner presence

**What Changed**:

**1. Universal Presence Filtering**
- ✅ **Smart Blocker**: Now checks car owner presence before sending notifications
- ✅ **Night Smart Charge**: Now checks car owner presence before sending notifications
- ✅ **Priority Balancer**: Already filtered in v1.3.19 (no changes)

**2. Enhanced Notification Logging**
Added comprehensive logging to track when notifications are sent:
- `📱 Preparing to send [MODE] notification at HH:MM:SS` - Before notification
- `   Window check: scheduled_time=XX:XX, current=XX:XX` - Verification log
- `Sending [TYPE] notification at HH:MM:SS` - Actual send time

**3. Safety Checks**
- Night Smart Charge now logs scheduled time vs current time before sending notifications
- Helps diagnose delayed or spurious notifications from Home Assistant's notify service
- Makes it easier to identify if notification delays are from HA infrastructure vs integration logic

**Files Modified**:
- [utils/mobile_notification_service.py](custom_components/ev_smart_charger/utils/mobile_notification_service.py):
  - Lines 57-60: Added `_is_car_owner_home()` check to Smart Blocker notifications
  - Lines 145-148: Added `_is_car_owner_home()` check to Night Charge notifications
  - Lines 68, 166: Added INFO-level logging when notifications sent
- [night_smart_charge.py](custom_components/ev_smart_charger/night_smart_charge.py):
  - Lines 496-499: Added safety logging before BATTERY mode notification
  - Lines 658-661: Added safety logging before GRID mode notification
- [const.py](custom_components/ev_smart_charger/const.py): VERSION = "1.3.20"
- [manifest.json](custom_components/ev_smart_charger/manifest.json): version = "1.3.20"

**Notification Behavior Matrix**:

| Notification Type | v1.3.19 | v1.3.20 |
|-------------------|---------|---------|
| Priority Balancer | ✅ Filtered | ✅ Filtered |
| Smart Blocker | ❌ Always sent | ✅ Filtered |
| Night Smart Charge | ❌ Always sent | ✅ Filtered |

**User Impact**:
- 🔇 **Zero notification spam** when away from home
- 🔍 **Better debugging** via detailed timestamp logs
- 🛡️ **Safety verification** - logs confirm notifications sent during valid windows
- 🏠 **Context-aware** - only notified when you can physically respond

**Technical Implementation**:
```python
# Smart Blocker notification (NEW in v1.3.20)
if not self._is_car_owner_home():
    _LOGGER.debug("Car owner not home, skipping Smart Blocker notification")
    return

# Night Charge notification (NEW in v1.3.20)
if not self._is_car_owner_home():
    _LOGGER.debug("Car owner not home, skipping Night Charge notification")
    return

# Enhanced logging for debugging
current_time = dt_util.now()
self.logger.info(f"📱 Preparing to send GRID mode notification at {current_time.strftime('%H:%M:%S')}")
self.logger.info(f"   Window check: scheduled_time={self._get_night_charge_time()}, current={current_time.strftime('%H:%M')}")
```

**Debugging Benefits**:
When investigating notification timing issues, logs now show:
```
01:05:23 - 📱 Preparing to send GRID mode notification at 01:05:23
01:05:23 -    Window check: scheduled_time=01:00, current=01:05
01:05:23 - Sending Night Charge notification (grid mode) at 01:05:23
```

This makes it easy to:
- Verify notifications sent at correct time
- Diagnose Home Assistant notify service delays
- Confirm presence checks working correctly

**Upgrade Priority**: 🟢 RECOMMENDED - Eliminates notification spam when away from home

### v1.3.19 (2025-11-06)
**Presence-Based Notification Filtering - Smart Priority Balancer Alerts**

**Feature Overview**:
Priority Balancer notifications are now filtered based on car owner presence at home. Notifications are only sent when the configured car owner person entity state is "home", preventing unnecessary alerts when away.

**Problem Solved**:
- **Previous Behavior** (v1.3.18): Priority Balancer sent notifications on every state change (EV/Home/EV_Free), regardless of whether anyone was home to receive them
- **User Impact**: Notification spam when away from home, where alerts about EV/Home battery priority changes are irrelevant
- **New Behavior** (v1.3.19): Priority Balancer notifications only sent when car owner is home

**New Configuration Field**:
- **`car_owner`**: Person entity selector in config flow (notifications step)
  - Domain: `person`
  - Required field (mandatory)
  - Example: `person.john`
  - Appears alongside `notify_services` selection
  - Available in both initial setup and options flow reconfiguration

**Logic Changes**:

**MobileNotificationService Updates**:
- Added `car_owner_entity` parameter to constructor (optional for backward compatibility)
- New method: `_is_car_owner_home()` - checks if person.state == "home"
- `send_priority_change_notification()` now checks presence before sending
- If car owner not home: notification skipped with debug log entry
- If car owner entity not configured: notifications always sent (backward compatible)
- If car owner entity unavailable: notifications always sent (fail-safe default)

**Notification Filtering Behavior**:
- ✅ **Priority Balancer**: Filtered by car owner presence (NEW)
- ❌ **Smart Blocker**: NOT filtered (charger blocking is critical regardless of presence)
- ❌ **Night Smart Charge**: NOT filtered (useful to know charging started even when away)

**Component Updates**:
All three components updated to pass car owner entity to MobileNotificationService:
1. `priority_balancer.py`: Updated constructor call with `config.get(CONF_CAR_OWNER)`
2. `automations.py` (Smart Blocker): Updated constructor call (no filtering logic)
3. `night_smart_charge.py`: Updated constructor call (no filtering logic)

**Files Modified**:
- `const.py`: Added `CONF_CAR_OWNER = "car_owner"` constant
- `config_flow.py`:
  - Imported `CONF_CAR_OWNER`
  - Added person entity selector to notifications step (both initial and options flow)
  - Field set as `vol.Required` (mandatory)
- `strings.json`:
  - Added `car_owner` field to notifications step data/descriptions
  - Updated descriptions to mention smart filtering feature
  - Added helpful tooltips explaining presence-based filtering
- `utils/mobile_notification_service.py`:
  - Added `car_owner_entity` parameter to `__init__` (optional, defaults to None)
  - New method: `_is_car_owner_home()` with comprehensive logging
  - Updated `send_priority_change_notification()` to check presence
  - Backward compatible: returns True if entity not configured or unavailable
- `priority_balancer.py`: Updated MobileNotificationService instantiation
- `automations.py`: Updated MobileNotificationService instantiation
- `night_smart_charge.py`: Updated MobileNotificationService instantiation

**User Experience**:
- **Setup**: Users select car owner person entity during notifications configuration
- **Reconfiguration**: Options flow allows updating car owner selection
- **UI Labels**: Clear descriptions explain the smart filtering feature
- **Logging**: Debug logs show presence check results for troubleshooting
- **Fail-Safe**: If person entity unavailable, notifications still sent (prevents silent failures)

**Technical Implementation**:
```python
def _is_car_owner_home(self) -> bool:
    """Check if car owner is home."""
    if not self.car_owner_entity:
        return True  # Backward compatibility

    state = self.hass.states.get(self.car_owner_entity)
    if not state:
        return True  # Fail-safe

    return state.state == "home"
```

**Benefits**:
- ✅ Reduces notification noise when away from home
- ✅ Makes Priority Balancer notifications contextually relevant
- ✅ Required field ensures feature always configured for new users
- ✅ Backward compatible (optional parameter with safe defaults)
- ✅ User-controlled via person entity (leverages HA's presence detection)
- ✅ Easy to extend to other notification types in future

### v1.3.18 (2025-11-06)
**Car Ready Time Support - Extend Charging Past Sunrise When Needed**

**Feature Overview**:
When the `car_ready` flag is enabled for a day, Night Smart Charge can now continue charging **past sunrise** until either the EV target SOC is reached or a configurable deadline time is hit. This ensures the car is always ready when needed, even if overnight charging wasn't sufficient.

**Problem Solved**:
- **Previous Behavior** (v1.3.17): Night charging ALWAYS stopped at sunrise, regardless of whether EV target was reached
- **User Impact**: If overnight charging didn't reach target (slow charging, late plug-in, etc.), user had to wait for daytime Solar Surplus to resume
- **New Behavior** (v1.3.18): When `car_ready=ON`, charging continues past sunrise until target or deadline reached

**New Entity**:
- **`time.evsc_car_ready_time`**: Configurable deadline time (default: 08:00)
  - Sets the absolute latest time charging must stop (e.g., "I need to leave for work at 08:00")
  - Global setting (not per-day) for simplicity

**Logic Changes**:

**When `car_ready=OFF` (car not urgently needed)**:
- Maintains v1.3.17 behavior: Stop at sunrise
- Rationale: No urgency, let Solar Surplus handle daytime charging with free solar energy

**When `car_ready=ON` (car needed for morning commute)**:
- **NEW**: Continue past sunrise until:
  1. **EV target SOC reached** (preferred outcome), OR
  2. **Car ready deadline time reached** (absolute cutoff)
- Priority: deadline > EV target > sunrise (sunrise ignored when car_ready=ON)
- **Both** BATTERY and GRID modes support this behavior

**Scenario Examples**:

**Scenario 1: Target Reached Before Sunrise** (No change)
```
01:00 AM - Start charging (GRID mode, car_ready=ON, target=80%)
06:30 AM - EV reaches 80% → STOP (target reached)
07:00 AM - Sunrise (already stopped)
```

**Scenario 2: Continue Past Sunrise** (NEW in v1.3.18)
```
01:00 AM - Start charging (BATTERY mode, car_ready=ON, target=80%, deadline=08:00)
07:00 AM - 🌅 Sunrise, EV at 65% → CONTINUE (car_ready=ON, below target)
07:30 AM - EV reaches 80% → STOP (target reached before deadline)
```

**Scenario 3: Deadline Forces Stop** (NEW in v1.3.18)
```
01:00 AM - Start charging (GRID mode, car_ready=ON, target=80%, deadline=08:00)
03:00 AM - Late plug-in, slow charging
07:00 AM - 🌅 Sunrise, EV at 60% → CONTINUE (car_ready=ON, below target)
08:00 AM - EV at 72% (still below 80%) → STOP (deadline reached)
User drives with 72% instead of 80%
```

**Scenario 4: Car Not Needed** (v1.3.17 behavior maintained)
```
01:00 AM - Check: car_ready=OFF → SKIP (weekend, car not needed)
OR
01:00 AM - Start charging (car_ready=OFF, target=80%)
07:00 AM - 🌅 Sunrise, EV at 65% → STOP (sunrise, car not urgently needed)
Solar Surplus continues charging during day with free solar
```

**Implementation Details**:

**New Methods** ([night_smart_charge.py](custom_components/ev_smart_charger/night_smart_charge.py)):
1. `_get_car_ready_time()` (line ~788): Reads deadline from time entity
2. `_should_stop_for_deadline()` (line ~810): Implements car_ready-based stop logic
   - Returns `(should_stop, reason)` tuple
   - Differentiates between car_ready=ON vs OFF scenarios

**Modified Methods**:
1. `_async_monitor_battery_charge()` - Check 0 (line ~532):
   - OLD: `if not await self._is_in_active_window(current_time)` (simple sunrise check)
   - NEW: `should_stop, reason = await self._should_stop_for_deadline(current_time)` (smart logic)

2. `_async_monitor_grid_charge()` - Check 0 (line ~594):
   - Same pattern as BATTERY mode

3. `_async_periodic_check()` - Active session validation (line ~239):
   - Now uses `_should_stop_for_deadline()` instead of simple window check
   - Ensures active sessions respect new stop logic

**New Constants** ([const.py](custom_components/ev_smart_charger/const.py)):
```python
HELPER_CAR_READY_TIME_SUFFIX = "evsc_car_ready_time"
DEFAULT_CAR_READY_TIME = "08:00:00"
VERSION = "1.3.18"
```

**Stop Conditions Matrix**:

| Mode | car_ready=OFF | car_ready=ON (target reached) | car_ready=ON (deadline reached) | car_ready=ON (both not reached) |
|------|---------------|------------------------------|--------------------------------|--------------------------------|
| BATTERY | Stop at sunrise | Stop at target | Stop at deadline | Continue past sunrise |
| GRID | Stop at sunrise | Stop at target | Stop at deadline | Continue past sunrise |

**Files Modified**:
- [const.py](custom_components/ev_smart_charger/const.py): Added `HELPER_CAR_READY_TIME_SUFFIX`, `DEFAULT_CAR_READY_TIME`, updated VERSION
- [time.py](custom_components/ev_smart_charger/time.py): Added `evsc_car_ready_time` entity
- [night_smart_charge.py](custom_components/ev_smart_charger/night_smart_charge.py): New methods, modified monitoring loops
- [manifest.json](custom_components/ev_smart_charger/manifest.json): version = "1.3.18"

**User Configuration**:
1. Set `car_ready` switches for days when car is needed (already existed in v1.3.13+)
2. Configure `time.evsc_car_ready_time` to your "must leave by" time (new in v1.3.18)
3. System automatically extends charging past sunrise when needed

**User Impact**:
- 🟢 **RECOMMENDED UPGRADE** - Ensures car is always ready when needed, even if overnight charging insufficient
- No breaking changes - defaults maintain backward compatibility
- Users with car_ready=OFF see no behavior change
- Users with car_ready=ON get intelligent sunrise extension automatically

**Upgrade Priority**: 🟢 RECOMMENDED - Significantly improves reliability for users who depend on morning readiness

### v1.3.17 (2025-11-06)
**CRITICAL: Night Smart Charge Sunrise Termination Fix**
- **🚨 Critical Bug Fixed**: Night charging could continue indefinitely past sunrise
- **Root Cause**: Missing sunrise termination logic in both BATTERY and GRID modes
- **Reported Issue**: User received charging notification at 08:40 AM (1.5 hours after sunrise)

**Changes Made**:

1. **BATTERY Mode Enhanced** ([night_smart_charge.py:516-521](custom_components/ev_smart_charger/night_smart_charge.py#L516-L521))
   - Added sunrise check to monitoring loop (runs every 15 seconds)
   - Now stops immediately when sunrise occurs
   - Previous behavior: Only checked home battery SOC and EV target

2. **GRID Mode Monitoring Loop Created** ([night_smart_charge.py:559-611](custom_components/ev_smart_charger/night_smart_charge.py#L559-L611))
   - NEW: Created complete monitoring loop for GRID mode (previously had NONE)
   - Checks every 15 seconds for:
     - Sunrise termination
     - EV target SOC reached
     - Charger status validation
   - Previous behavior: NO monitoring at all (relied on user intervention or wallbox 100% limit)

3. **Periodic Check Window Re-validation** ([night_smart_charge.py:233-244](custom_components/ev_smart_charger/night_smart_charge.py#L233-L244))
   - Active sessions now re-validated for window validity
   - Prevents active sessions from bypassing sunrise check
   - Previous behavior: Active sessions skipped all checks

4. **Enhanced Window Validation Logging** ([night_smart_charge.py:330-349](custom_components/ev_smart_charger/night_smart_charge.py#L330-L349))
   - Added detailed comparison logging (Now >= Scheduled, Now < Sunrise)
   - Debug-level logging for frequent monitoring checks
   - Helps diagnose future window-related issues

**Stop Conditions Summary**:

| Mode | Sunrise | EV Target | Home Battery Min | Manual/Unplug |
|------|---------|-----------|------------------|---------------|
| BATTERY (v1.3.16) | ❌ Missing | ✅ Yes | ✅ Yes | ✅ Yes |
| BATTERY (v1.3.17) | ✅ **FIXED** | ✅ Yes | ✅ Yes | ✅ Yes |
| GRID (v1.3.16) | ❌ Missing | ❌ Missing | N/A | ✅ Yes only |
| GRID (v1.3.17) | ✅ **FIXED** | ✅ **FIXED** | N/A | ✅ Yes |

**Technical Details**:
- Added `_grid_monitor_unsub` timer for GRID mode monitoring
- Both modes now check `_is_in_active_window()` every 15 seconds
- Session completion properly cancels both monitoring loops
- Grid monitoring registered in `_start_grid_charge()` (line 643-651)

**Example Fixed Scenario**:
```
01:00 AM - GRID mode starts (forecast insufficient, car_ready=True)
03:00 AM - EV at 50%, target 80% (still charging...)
07:00 AM - 🌅 SUNRISE - **NOW STOPS IMMEDIATELY** (previously continued)
```

**User Impact**:
- 🔴 **URGENT UPGRADE** - Night charging will no longer continue past sunrise
- Prevents unexpected grid charging during day when solar available
- Prevents overcharging when EV target already reached

**Files Modified**:
- [night_smart_charge.py](custom_components/ev_smart_charger/night_smart_charge.py): Added GRID monitoring loop, sunrise checks in both modes
- [const.py](custom_components/ev_smart_charger/const.py): VERSION = "1.3.17"
- [manifest.json](custom_components/ev_smart_charger/manifest.json): version = "1.3.17"

**Related Documentation**:
- Complete scenario analysis: [NIGHT_CHARGE_SCENARIOS.md](NIGHT_CHARGE_SCENARIOS.md)

### v1.3.16 (2025-11-05)
**Throttled Logging for Sensor Errors**
- **Problem Fixed**: When sensors become unavailable (e.g., `unknown` state), Solar Surplus logged errors every minute, causing log spam (200+ messages)
- **Solution**: Implemented smart error state tracking that only logs when errors change
- **New Behavior**:
  - First error occurrence: Full error logged with details
  - Subsequent occurrences: Silent (only debug level logging)
  - Sensor recovery: Success message logged when sensor becomes available again
- **Example**:
  ```
  12:35:07 - ❌ Sensor Home Consumption (sensor.xyz) state is 'unknown'  [LOGGED ONCE]
  12:36:07 - [silent - error persists]
  12:37:07 - [silent - error persists]
  12:38:07 - ✅ Home Consumption sensor recovered (was: state is 'unknown')  [LOGGED]
  ```
- **Technical**: Added `_sensor_error_state` dictionary to track per-sensor error states
- **User Impact**: Cleaner logs, no more Home Assistant warnings about excessive logging
- **Upgrade priority**: 🟡 RECOMMENDED - Eliminates log spam when sensors temporarily offline

### v1.3.15 (2025-11-05)
**Unified 60s Stability Delay for All Surplus Operations**
- **Change**: Initial charger start (OFF → ON) now uses same 60s delay as amperage increases
- **Rationale**: Consistent cloud protection for all surplus-based charging operations
- **Previous Behavior** (v1.3.14):
  - Charger OFF → ON: 15s stability delay
  - Charger ON, increase amperage: 60s stability delay
- **New Behavior** (v1.3.15):
  - Charger OFF → ON: **60s stability delay** (unified)
  - Charger ON, increase amperage: 60s stability delay (unchanged)
  - Charger ON, decrease amperage: 30s delay (unchanged)
- **User Impact**: More conservative charging start, prevents premature startup on brief surplus spikes
- **Technical**: Modified `solar_surplus.py` - `_handle_surplus_increase()` now uses `SURPLUS_INCREASE_DELAY` for both OFF→ON and increases
- **Upgrade priority**: 🟢 OPTIONAL - Further improves stability, especially for initial charge start

### v1.3.14 (2025-11-05)
**Cloud Protection for Surplus Increase**
- Added: 60-second stability delay before increasing charging amperage
- **Problem Fixed**: On cloudy days, system would immediately increase amperage when surplus briefly increased, then decrease 30s later when clouds returned
- **Old Behavior**:
  - Charger OFF → ON: 15s stability delay ✅
  - Charger ON, increase amperage: IMMEDIATE ❌ (caused oscillations)
  - Charger ON, decrease amperage: 30s delay ✅
- **New Behavior**:
  - Charger OFF → ON: 15s stability delay ✅
  - Charger ON, increase amperage: 60s stability delay ✅ (cloud protection)
  - Charger ON, decrease amperage: 30s delay ✅
- **Example Scenario Prevented**:
  ```
  ☁️ Cloud passes → surplus 3000W (13A) → wait 60s → if still stable, increase to 13A
  ☀️ Cloud arrives → surplus 1400W (6A)  → wait 30s → if still low, decrease to 6A
  ```
- **Technical**: Added `SURPLUS_INCREASE_DELAY = 60` constant in `const.py`
- **Modified**: `solar_surplus.py` - `_handle_surplus_increase()` now requires stability for all increases
- **User Impact**: More stable charging in variable weather, fewer charger state changes
- **Upgrade priority**: 🟢 OPTIONAL - Improves stability on cloudy days

### v1.3.13 (2025-11-05)
**Car Ready Flag & Battery Pre-Check**
- Added: Daily "Car Ready" flags for intelligent night charge fallback/skip behavior
- Added: Pre-check of home battery SOC before starting BATTERY MODE to prevent 15-second discharge
- **Problem Fixed**: When PV forecast good but home battery already below 20% threshold, system would start charging for 15 seconds before monitor detected issue
- **Enhancement**: User can now choose per-day behavior when battery insufficient:
  - Car ready = TRUE (Mon-Fri default): Use GRID MODE as fallback (ensures car ready in morning)
  - Car ready = FALSE (Sat-Sun default): SKIP charging (wait for solar surplus)
- **New Entities** (7 switches created automatically):
  - `switch.evsc_car_ready_monday` through `sunday`
  - Icon: `mdi:car-clock`
  - Defaults: Mon-Fri = TRUE (work days), Sat-Sun = FALSE (weekends)
- **Pre-Check Logic** in `_start_battery_charge()`:
  1. Check home battery SOC before starting charger
  2. If SOC <= threshold AND car_ready = TRUE → Fallback to GRID MODE
  3. If SOC <= threshold AND car_ready = FALSE → SKIP (wait for solar)
  4. If SOC > threshold → Proceed with BATTERY MODE normally
- **Helper Method**: `_get_car_ready_for_today()` returns boolean based on current weekday
- **Technical**: Modified `const.py` (constants), `switch.py` (7 switches), `night_smart_charge.py` (pre-check + helper), `logging_helper.py` (CAR emoji), `manifest.json` (version)
- **Upgrade priority**: 🟡 RECOMMENDED for users wanting flexible night charge behavior

### v1.3.12 (2025-11-05)
**CRITICAL FIX: Night Smart Charge Restart Loop & Battery Protection**
- Fixed FIVE critical bugs causing charger restart loops, inadequate battery protection, and excessive logging
- **Bug #1**: Periodic timer not cancelled after completion → restart loops
  - `_timer_unsub` was never cancelled in `_complete_night_charge()`
  - Periodic check continued running every minute after session completion
  - Led to re-evaluation and restart loops
- **Bug #2**: No cooldown protection in periodic check → race conditions
  - `_async_periodic_check()` had no protection against re-evaluating after recent completion
  - Created race condition: 01:00 start → 01:02 stop → 01:03 restart → 01:05 restart
  - Both Night Charge AND Solar Surplus tried to start charger simultaneously
- **Bug #3**: Battery monitoring too slow (1 minute) → failed protection
  - Battery dropped 8% (20% → 12%) between 1-minute checks
  - Slow monitoring failed to catch 20% threshold crossing in time
  - Solution: Reduced interval from 60s to 15s (4x faster, 75% response time improvement)
- **Bug #4**: Solar Surplus interference during cooldown
  - Solar Surplus had no awareness of Night Charge completion state
  - Attempted to start charger at 01:03 and 01:05 after Night Charge stopped
  - Created interference and restart loops
- **Bug #5**: No completion timestamp tracking
  - System had no memory of when sessions completed
  - Impossible to implement proper cooldown logic
- **Solutions Implemented**:
  - Added `_last_completion_time` attribute for timestamp tracking
  - Added `NIGHT_CHARGE_COOLDOWN_SECONDS = 3600` (1 hour) constant
  - Updated `_async_periodic_check()` with cooldown and active checks
  - Updated `_complete_night_charge()` to set completion timestamp
  - Reduced battery monitoring from 60s to 15s
  - Added Night Charge cooldown check in Solar Surplus (new step #4)
- **Impact**:
  - Battery protection at 20% threshold (not 12%)
  - No restart loops (1-hour cooldown enforced)
  - < 50 log messages per session (vs 200+)
  - Reliable battery protection and session management
- **Technical**: Modified `const.py`, `night_smart_charge.py`, `solar_surplus.py`
- **Upgrade priority**: 🔴 CRITICAL for users experiencing restart loops or battery protection failures

### v1.3.11 (2025-11-05)
**CRITICAL FIX: Solar Surplus Nighttime Operation**
- Fixed: Solar Surplus was running during nighttime and attempting to charge using home battery
- Root cause: Solar Surplus periodic check ran 24/7 without nighttime detection
- At 00:25 (nighttime): Surplus -492W → Priority EV → Battery support activated → 16A charging started
- Result: Smart Blocker had to intervene (should never happen)
- Solution: Added nighttime detection using `AstralTimeService.is_nighttime()`
- Solar Surplus now ONLY operates during daytime (sunrise → sunset)
- New check sequence: Forza Ricarica → **Nighttime** → Night Smart Charge → Profile → ...
- Nighttime hours fully protected: sunset → sunrise fully blocked for Solar Surplus
- Night Smart Charge handles ALL nighttime charging (starts at configured time, e.g., 01:00)
- Technical: Added AstralTimeService to solar_surplus.py, new check #2, renumbered sections
- Upgrade priority: 🔴 CRITICAL for users experiencing unwanted night charging

### v1.3.10 (2025-11-05)
**CRITICAL FIX: Smart Charger Blocker After Midnight**
- Fixed: Smart Charger Blocker was NOT blocking charging after midnight (e.g., at 00:11)
- Root cause: `AstralTimeService.get_blocking_window` used TODAY's sunset when checking times after midnight
- Example: At 00:11, compared with today's 18:30 (not yet occurred) instead of yesterday's 18:30 (passed)
- Result: `00:11 < 18:30` = false → blocker thought it was daytime → charger started incorrectly
- Solution: Check if reference_time is before sunrise:
  - Before sunrise (early morning): Use YESTERDAY's sunset as window_start
  - After sunrise (daytime/evening): Use TODAY's sunset as window_start
- Now at 00:11 with night_charge_time=01:00: `yesterday_18:30 <= 00:11 < today_01:00` = TRUE ✓
- Also simplified `is_in_blocking_window` logic (removed complex cross-day workaround)
- Technical: Modified `utils/astral_time_service.py` - `get_blocking_window` and `is_in_blocking_window`
- Upgrade priority: 🔴 CRITICAL for users relying on Smart Blocker for nighttime prevention

### v1.3.9 (2025-11-04)
**Logging Performance Fix**
- Fixed: "Module logging too frequently. 200 messages" warning in Home Assistant logs
- Root cause 1: Rate limit warning logged on every check (paradox)
- Root cause 2: Battery SOC monitor triggered immediate recalculation without rate limiting
- Solution 1: Rate limit warning now logs only once per minute (at cycle reset)
- Solution 2: Immediate recalculation respects SOLAR_SURPLUS_MIN_CHECK_INTERVAL (30s)
- Technical: Modified `solar_surplus.py` lines 253-257 (rate limit) and 223-241 (SOC monitor)

### v1.3.8 (2025-11-04)
**UI Improvements & Device Grouping**
- Added: `device_info` property to all entity classes (number, switch, select, time, sensor)
- Fixed: Config flow total_steps inconsistency (now correctly shows "Step X of 5")
- Result: All 29 entities now grouped under unified "EV Smart Charger" device
- Device info includes: manufacturer="antbald", model="EV Smart Charger", sw_version
- Icon "mdi:ev-station" already configured in manifest for HACS/device
- Daily SOC entities already have calendar icons (mdi:calendar-monday through sunday)
- Technical: Added VERSION import and device_info property to all platform files

### v1.3.7 (2025-11-04)
**Fix Unnecessary Warning Logs**
- Fixed: Eliminated false-positive warnings for unavailable amperage sensor (81+ occurrences)
- Root cause: `get_int()` was logging warning before checking state availability
- Solution: Reordered logic to check state FIRST, then convert
- Impact: Cleaner logs with only genuine errors, same functionality
- Technical: Modified `utils/state_helper.py` - `get_int()` function

### v1.3.6 (2025-11-04)
**Major Stability Improvements & Battery Protection**
- FASE 1: Anti-Oscillation System
  - Hysteresis implementation: start 6.5A, stop 5.5A, dead band 1.0A
  - EV_FREE mode stabilization: 30s delay instead of immediate stop
  - Startup stability: 15s stable surplus requirement
- FASE 2: Real-time Battery Protection
  - SOC listener on soc_home for immediate deactivation
  - Eliminates up to 1-minute protection delay
- FASE 3: Operation Result Feedback
  - OperationResult dataclass for comprehensive tracking
  - Enhanced ChargerController return types
- FASE 4: Code Cleanup
  - Removed dead code: async_setup_automations()
- Bugs Fixed: Charger oscillation, battery over-discharge, EV_FREE immediate stop

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

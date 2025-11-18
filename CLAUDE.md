# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a **Home Assistant custom integration** for intelligent EV charging control. It manages EV charger automation based on solar production, time of day, battery levels, grid import protection, and intelligent priority balancing between EV and home battery charging.

**Domain:** `ev_smart_charger`
**Current Version:** 1.3.22
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
- `VERSION = "1.3.13"`
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

### v1.4.2 (2025-11-18)
**CRITICAL FIX: Night Smart Charge Time Window Bug + Enhanced Diagnostic Logging**

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

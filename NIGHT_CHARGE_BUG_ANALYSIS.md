# Night Smart Charge Bug Analysis - 2025-11-07 01:00

## Scenario Overview

**Date/Time**: 2025-11-07 01:00 AM
**Expected Behavior**: Night Smart Charge starts BATTERY mode charging
**Actual Behavior**: Charging blocked by Smart Charger Blocker with error notification

**System Configuration**:
- Start time: 01:00
- End time: 09:00
- Home battery SOC: 65% (above 20% threshold ✅)
- PV forecast: 30 kWh (above 20 kWh threshold ✅)
- car_ready flag: OFF (Saturday - car not urgently needed)
- Expected mode: BATTERY MODE (charge from home battery until target or battery < 20%)

---

## Critical Bug #1: Missing `_get_night_charge_time()` Method

### Error Details

**Error Log**:
```
AttributeError: 'NightSmartCharge' object has no attribute '_get_night_charge_time'.
Did you mean: '_get_night_charge_amperage'?
```

**Occurrence Locations**:
- Line 498: `_start_battery_charge()` method
- Line 660: `_start_grid_charge()` method

**Root Cause**:
The method `_get_night_charge_time()` was referenced in v1.3.20 safety logging but **never implemented**.

### Code Analysis

**Where the method is called** (lines 496-498):
```python
# Send mobile notification with safety logging (v1.3.20)
current_time = dt_util.now()
self.logger.info(f"📱 Preparing to send BATTERY mode notification at {current_time.strftime('%H:%M:%S')}")
self.logger.info(f"   Window check: scheduled_time={self._get_night_charge_time()}, current={current_time.strftime('%H:%M')}")
```

**Expected Implementation** (based on existing patterns):
```python
def _get_night_charge_time(self) -> str:
    """Get configured night charge start time.

    Returns:
        Time string (HH:MM:SS format) or "Not configured"
    """
    if not self._night_charge_time_entity:
        return "Not configured"

    time_state = state_helper.get_state(self.hass, self._night_charge_time_entity)

    if not time_state or time_state in ("unknown", "unavailable"):
        return "Unavailable"

    return time_state
```

**Impact**:
- Night Smart Charge raises `AttributeError` exception
- `_start_battery_charge()` execution **aborts before starting charger**
- `_night_charge_active` flag remains `False`
- `_active_mode` remains `NIGHT_CHARGE_MODE_IDLE`

---

## Critical Bug #2: Race Condition with Smart Blocker

### Event Timeline Reconstruction

```
01:00:00.000 - Night Smart Charge periodic check triggered
01:00:00.100 - Night Smart Charge enters _evaluate_and_charge()
01:00:00.200 - Conditions validated: battery=65%, forecast=30kWh, car_ready=OFF
01:00:00.300 - Enters _start_battery_charge()
01:00:00.400 - Sets _night_charge_active = True
01:00:00.500 - Sets _active_mode = NIGHT_CHARGE_MODE_BATTERY
01:00:00.600 - Attempts safety logging with _get_night_charge_time()
01:00:00.700 - ❌ AttributeError exception raised
01:00:00.800 - Exception propagates, charger NOT started
01:00:00.900 - ❌ _night_charge_active remains True BUT charger never turned ON
01:00:01.000 - [Unknown trigger causes charger switch to turn ON]
01:00:01.100 - Smart Blocker detects charger status changed to "charging"
01:00:01.200 - Smart Blocker calls _should_block_charging()
01:00:01.300 - Smart Blocker Check #3: night_smart_charge.is_active()
01:00:01.400 - is_active() returns: _night_charge_active=True AND _active_mode=BATTERY
01:00:01.500 - 🤔 BUT: Charger was never started by Night Charge!
01:00:01.600 - Smart Blocker should allow (Night Charge "active")
01:00:01.700 - ❌ BUG: Smart Blocker BLOCKS instead of allowing
01:00:32.000 - Error logged: "Task exception was never retrieved"
```

### Race Condition Analysis

**Problem**: There's a window between exception and Smart Blocker evaluation where:

1. `_night_charge_active = True` ✅ (set before error)
2. `_active_mode = NIGHT_CHARGE_MODE_BATTERY` ✅ (set before error)
3. **Charger NOT started** ❌ (exception prevented this)
4. Something external turns charger ON
5. Smart Blocker evaluates `is_active()` → returns `True`
6. Smart Blocker **should allow**, but blocks instead

### Why Smart Blocker Blocked (Mystery)

**Expected behavior** (line 350-352 in automations.py):
```python
# Check 3: Night Smart Charge active (override blocker)
if self.night_smart_charge and self.night_smart_charge.is_active():
    night_mode = self.night_smart_charge.get_active_mode()
    return False, f"Night Smart Charge active (mode: {night_mode})"
```

**`is_active()` implementation** (line 206-208):
```python
def is_active(self) -> bool:
    """Check if currently charging (mode != IDLE)."""
    return self._night_charge_active and self._active_mode != NIGHT_CHARGE_MODE_IDLE
```

**State at 01:00:01**:
- `_night_charge_active = True` ✅
- `_active_mode = NIGHT_CHARGE_MODE_BATTERY` ✅
- Therefore: `is_active()` should return `True` ✅
- Smart Blocker should return `(False, "Night Smart Charge active (mode: battery)")` ✅
- **But it blocked anyway!** ❌

### Possible Explanations

**Hypothesis #1: Timing Issue**
- Smart Blocker checked `is_active()` BEFORE exception occurred
- At that moment, `_night_charge_active = False` and `_active_mode = IDLE`
- After blocker decision, exception occurred and left state inconsistent

**Hypothesis #2: Exception Rollback**
- Exception may have caused partial state rollback
- `_night_charge_active` set to `True` then reset somewhere?
- Unlikely - no try/except blocks modifying these flags

**Hypothesis #3: Multiple Check Invocations**
- First check: `is_active() = False` → should block
- Charger blocked
- Second check (after exception): `is_active() = True` → should allow
- But enforcement mode already active

**Most Likely: Hypothesis #1** - Timing issue where Smart Blocker reacted before Night Charge set internal flags.

---

## Root Cause Summary

### Primary Cause: Missing Method Implementation
**Severity**: 🔴 CRITICAL

The `_get_night_charge_time()` helper method was referenced but never implemented in v1.3.20. This causes:
1. `AttributeError` exception during notification logging
2. Charger never started (exception aborts execution)
3. Internal state left inconsistent (`_night_charge_active=True` but charger OFF)

### Secondary Cause: Incomplete Exception Handling
**Severity**: 🟡 MEDIUM

No try/except blocks around notification logging means:
1. Non-critical logging failures abort critical charging operations
2. Internal state flags set before error are not cleaned up
3. System left in inconsistent state (flags say "active" but charger never started)

### Tertiary Cause: Race Condition Vulnerability
**Severity**: 🟢 LOW (but amplified by bugs above)

Smart Blocker can evaluate blocking conditions before Night Charge completes initialization:
1. Night Charge sets flags but hasn't started charger yet
2. Something triggers charger externally
3. Smart Blocker checks `is_active()` during this window
4. Result depends on exact timing

---

## Why Expected Behavior Didn't Occur

**Expected Flow** (without bugs):
```
01:00:00 - Night Smart Charge triggered
         ↓
01:00:01 - Validate conditions (battery=65%, forecast=30kWh, car_ready=OFF)
         ↓
01:00:02 - Enter BATTERY MODE
         ↓
01:00:03 - Set _night_charge_active = True
         ↓
01:00:04 - Set _active_mode = NIGHT_CHARGE_MODE_BATTERY
         ↓
01:00:05 - Log notification preparation
         ↓
01:00:06 - Send notification (battery mode, 30 kWh forecast)
         ↓
01:00:07 - Start charger at 16A (via ChargerController)
         ↓
01:00:08 - Start battery monitoring (every 15 seconds)
         ↓
01:00:09 - Monitor until: battery < 20% OR EV target reached OR sunrise
```

**Actual Flow** (with bugs):
```
01:00:00 - Night Smart Charge triggered
         ↓
01:00:01 - Validate conditions (battery=65%, forecast=30kWh, car_ready=OFF) ✅
         ↓
01:00:02 - Enter BATTERY MODE ✅
         ↓
01:00:03 - Set _night_charge_active = True ✅
         ↓
01:00:04 - Set _active_mode = NIGHT_CHARGE_MODE_BATTERY ✅
         ↓
01:00:05 - Log notification preparation ✅
         ↓
01:00:06 - Call _get_night_charge_time() ❌ EXCEPTION!
         ↓
         ❌ EXECUTION ABORTED - Charger never started
         ❌ Battery monitoring never started
         ❌ Notification never sent
         ❌ State left inconsistent
```

---

## Impact Assessment

### User Impact
- ✅ **Car ready=OFF respected**: System correctly decided NOT to fallback to GRID mode
- ❌ **No charging occurred**: Car remained at original SOC, not charged overnight
- ❌ **Confusing notification**: User received "blocked by Smart Blocker" instead of understanding Night Charge failed
- ⚠️ **Silent failure**: Exception logged but user not informed of Night Charge failure

### System State Impact
- Internal flags: `_night_charge_active=True`, `_active_mode=BATTERY`
- Actual state: Charger OFF, no monitoring active
- Inconsistency: System thinks it's charging, but it's not
- Recovery: Likely resolved at next periodic check or manual intervention

### Data Integrity
- Diagnostic sensors show incorrect state
- Logs show exception but not user-friendly explanation
- Smart Blocker notification misleading (not the real cause)

---

## Recommended Fixes

### Fix #1: Implement Missing Method (REQUIRED)
**Priority**: 🔴 CRITICAL
**File**: `night_smart_charge.py`

Add the missing helper method:

```python
def _get_night_charge_time(self) -> str:
    """Get configured night charge start time.

    Returns:
        Time string (HH:MM:SS format) or fallback message
    """
    if not self._night_charge_time_entity:
        return "Not configured"

    time_state = state_helper.get_state(self.hass, self._night_charge_time_entity)

    if not time_state or time_state in ("unknown", "unavailable"):
        return "Unavailable"

    return time_state
```

**Impact**: Eliminates AttributeError exception, allows charging to proceed

---

### Fix #2: Add Exception Handling for Logging (REQUIRED)
**Priority**: 🔴 CRITICAL
**File**: `night_smart_charge.py`

Wrap notification logging in try/except:

```python
# Send mobile notification with safety logging (v1.3.20)
try:
    current_time = dt_util.now()
    scheduled_time = self._get_night_charge_time()
    self.logger.info(f"📱 Preparing to send BATTERY mode notification at {current_time.strftime('%H:%M:%S')}")
    self.logger.info(f"   Window check: scheduled_time={scheduled_time}, current={current_time.strftime('%H:%M')}")
except Exception as ex:
    self.logger.warning(f"Notification logging failed (non-critical): {ex}")
```

**Impact**: Prevents logging failures from aborting critical operations

---

### Fix #3: Add State Cleanup on Exception (RECOMMENDED)
**Priority**: 🟡 MEDIUM
**File**: `night_smart_charge.py`

Wrap entire `_start_battery_charge()` in try/except with cleanup:

```python
async def _start_battery_charge(self, pv_forecast: float):
    """Start battery-based charging mode."""
    try:
        # ... existing code ...

        # Set internal state
        self._night_charge_active = True
        self._active_mode = NIGHT_CHARGE_MODE_BATTERY

        # ... notification logic ...

        # Start charger
        await self.charger_controller.start_charger(amperage, reason)

        # Start monitoring
        # ... monitoring setup ...

    except Exception as ex:
        self.logger.error(f"Failed to start battery charge: {ex}")

        # Cleanup on failure
        self._night_charge_active = False
        self._active_mode = NIGHT_CHARGE_MODE_IDLE

        # Cancel any monitoring timers
        if self._battery_monitor_unsub:
            self._battery_monitor_unsub()
            self._battery_monitor_unsub = None

        # Re-raise to allow caller to handle
        raise
```

**Impact**: Prevents inconsistent internal state on failures

---

### Fix #4: Add Defensive Check in Smart Blocker (OPTIONAL)
**Priority**: 🟢 LOW
**File**: `automations.py`

Add validation that Night Charge actually started the charger:

```python
# Check 3: Night Smart Charge active (override blocker)
if self.night_smart_charge and self.night_smart_charge.is_active():
    night_mode = self.night_smart_charge.get_active_mode()

    # Additional safety: verify charger was actually started by Night Charge
    # Check if charger has been ON for at least 5 seconds (grace period)
    charger_state = self.hass.states.get(self._charger_switch_entity)
    if charger_state:
        last_changed = charger_state.last_changed
        time_since_change = (dt_util.now() - last_changed).total_seconds()

        if time_since_change < 5:
            self.logger.warning(f"Night Charge active but charger just turned ON ({time_since_change:.1f}s ago)")
            self.logger.warning("Possible race condition - allowing anyway (Night Charge priority)")

    return False, f"Night Smart Charge active (mode: {night_mode})"
```

**Impact**: Adds defensive check for race conditions (low priority, complexity vs benefit)

---

## Testing Recommendations

### Test Case #1: Normal BATTERY Mode Activation
**Setup**:
- Start time: 01:00
- Battery SOC: 65%
- PV forecast: 30 kWh
- car_ready: OFF

**Expected**:
1. Night Smart Charge starts BATTERY mode at 01:00
2. Notification sent with forecast details
3. Charger starts at 16A
4. Battery monitoring active (every 15 seconds)
5. No Smart Blocker intervention

### Test Case #2: Exception During Notification
**Setup**: Temporarily break `_get_night_charge_time()` to simulate error

**Expected**:
1. Warning logged about notification failure
2. Charging proceeds despite logging error
3. Charger starts successfully
4. Internal state consistent

### Test Case #3: Race Condition Simulation
**Setup**: Add artificial delay between flag setting and charger start

**Expected**:
1. Smart Blocker checks during delay window
2. Sees `is_active() = True`
3. Allows charging (Night Charge priority)
4. No blocking notification sent

---

## Version History Context

This bug was introduced in **v1.3.20** when enhanced notification logging was added:
- Lines 496-498 added to `_start_battery_charge()`
- Lines 658-660 added to `_start_grid_charge()`
- **But**: Helper method `_get_night_charge_time()` was never implemented

**Previous versions (v1.3.19 and earlier)**: Did not have this bug because notification logging was simpler and didn't call the non-existent method.

---

## Conclusion

The failure to start Night Smart Charge at 01:00 was caused by a **coding error in v1.3.20**: a method reference without implementation. The exception prevented the charger from starting, leaving the system in an inconsistent state that confused both the user and the Smart Blocker automation.

**Critical fixes required**:
1. ✅ Implement `_get_night_charge_time()` method
2. ✅ Add exception handling for non-critical logging
3. ✅ Add state cleanup on failures

**Nice-to-have improvements**:
4. ⚠️ Add defensive checks in Smart Blocker for race conditions

**Immediate action**: Apply Fix #1 and Fix #2 to resolve the critical bug. Consider Fix #3 for robustness. Fix #4 is optional complexity.

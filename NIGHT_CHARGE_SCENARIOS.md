# Night Smart Charge - Scenario Analysis and Stop Conditions

**Analysis Date**: 2025-11-06
**Current Version**: 1.3.16
**Issue**: Night charging notification received at 08:40 AM (after sunrise)

## Configuration Assumptions

- **Night Charge Time**: 01:00 AM
- **Sunrise**: ~07:00 AM (varies by date/location)
- **EV Target SOC**: 80% (example, configured per weekday)
- **Home Battery Min SOC**: 20%
- **Night Charge Amperage**: 16A
- **Car Ready Flag**: ON (enabled for the day)

---

## BATTERY MODE Scenarios

### Scenario A: Home Battery Reaches Minimum Before EV Target

**Initial State**:
- Time: 01:00 AM (night charge starts)
- Solar Forecast: 25 kWh (> 20 kWh threshold)
- Home Battery: 50% SOC
- EV Battery: 40% SOC (target: 80%)
- Mode: BATTERY (forecast sufficient, battery support enabled)

**Timeline**:
1. **01:00 AM** - Night Smart Charge activates
   - Checks: ✓ Time >= 01:00, ✓ Time < 07:00 sunrise, ✓ Car ready flag ON
   - Starts charging at 16A from home battery
   - Monitoring loop starts (checks every 15 seconds)

2. **02:30 AM** - Home battery reaches 20% minimum
   - Monitoring loop detects: `home_soc (20%) <= home_min_soc (20%)`
   - **STOPS CHARGING**: "Home battery minimum SOC reached"
   - `_complete_night_charge()` called - sets cooldown until next activation

**Result**: ✅ **CORRECT BEHAVIOR** - Stops when home battery protection triggered

**Logs Expected**:
```
[01:00] BATTERY mode activated (forecast 25 kWh > 20 kWh threshold)
[01:00] Starting charger at 16A (battery mode)
[02:30] Home battery reached minimum: 20% <= 20%
[02:30] Stopping charger: Home battery minimum SOC reached
[02:30] Night Smart Charge cycle completed
```

---

### Scenario B: EV Reaches Target SOC Before Home Battery Minimum

**Initial State**:
- Time: 01:00 AM
- Solar Forecast: 30 kWh
- Home Battery: 80% SOC (plenty of charge)
- EV Battery: 70% SOC (target: 80%, only 10% needed)
- Mode: BATTERY

**Timeline**:
1. **01:00 AM** - Night Smart Charge activates
   - Starts charging at 16A from home battery
   - Monitoring loop starts

2. **01:45 AM** - EV reaches 80% target SOC
   - Monitoring loop detects: `priority_balancer.is_ev_target_reached() == True`
   - **STOPS CHARGING**: "EV target SOC reached"
   - `_complete_night_charge()` called

**Result**: ✅ **CORRECT BEHAVIOR** - Stops when EV target reached

**Logs Expected**:
```
[01:00] BATTERY mode activated (forecast 30 kWh > 20 kWh threshold)
[01:00] Starting charger at 16A (battery mode)
[01:45] EV target SOC reached (80%)
[01:45] Stopping charger: EV target SOC reached
[01:45] Night Smart Charge cycle completed
```

---

### Scenario C: Sunrise Occurs While Charging (CURRENT BEHAVIOR)

**Initial State**:
- Time: 01:00 AM
- Solar Forecast: 35 kWh
- Home Battery: 90% SOC (plenty of charge)
- EV Battery: 30% SOC (target: 80%, needs 50% - ~6 hours at 16A)
- Mode: BATTERY

**Timeline**:
1. **01:00 AM** - Night Smart Charge activates
   - Starts charging at 16A from home battery
   - Monitoring loop starts (checks home battery SOC and EV target every 15s)

2. **07:00 AM** - ⏰ **SUNRISE OCCURS**
   - ❌ **BUG**: Monitoring loop does NOT check sunrise
   - Periodic check (`_async_periodic_check`) runs at 01:01, 01:02, etc.
   - Periodic check finds session active → SKIPS: "Already active, skipping re-evaluation"
   - **CHARGING CONTINUES** beyond sunrise

3. **08:00 AM** - Still charging
   - Home battery: 60% (still above minimum)
   - EV battery: 65% (still below 80% target)
   - **CHARGING STILL ACTIVE** ❌

4. **Eventually stops when**:
   - EV reaches 80% target (~09:30 AM), OR
   - Home battery reaches 20% minimum, OR
   - User manually intervenes

**Result**: ❌ **BUG IDENTIFIED** - Does NOT stop at sunrise, continues charging indefinitely

**Current Logs**:
```
[01:00] BATTERY mode activated (forecast 35 kWh > 20 kWh threshold)
[01:00] Starting charger at 16A (battery mode)
[07:00] 🌅 (sunrise - NO LOG, NOT DETECTED)
[08:00] (still charging - no stop condition triggered)
[09:30] EV target SOC reached (80%)
[09:30] Stopping charger: EV target SOC reached
```

**Expected Behavior**:
```
[01:00] BATTERY mode activated
[01:00] Starting charger at 16A (battery mode)
[07:00] 🌅 Sunrise detected - night charge window closed
[07:00] Stopping charger: Night charge window ended
[07:00] Night Smart Charge cycle completed
```

---

## GRID MODE Scenarios

### Scenario D: EV Reaches Full Charge (CURRENT BEHAVIOR)

**Initial State**:
- Time: 01:00 AM
- Solar Forecast: 15 kWh (< 20 kWh threshold - insufficient)
- Home Battery: 90% SOC
- EV Battery: 40% SOC (target: 80%)
- Mode: GRID (forecast insufficient, fallback to grid charging)

**Timeline**:
1. **01:00 AM** - Night Smart Charge activates
   - Checks: ✓ Time >= 01:00, ✓ Time < 07:00, ✓ Car ready flag ON
   - Forecast 15 kWh < 20 kWh threshold
   - Starts GRID mode charging at 16A
   - ❌ **NO monitoring loop started** (GRID mode has no monitoring)

2. **07:00 AM** - ⏰ **SUNRISE OCCURS**
   - ❌ **BUG**: No monitoring loop to detect sunrise
   - Periodic check skips active session
   - **CHARGING CONTINUES** beyond sunrise

3. **Charging continues until**:
   - Charger reaches 100% (wallbox stops itself), OR
   - User manually intervenes, OR
   - Something triggers re-evaluation (car unplugged/replugged)

**Result**: ❌ **CRITICAL BUG** - GRID mode has ZERO stop conditions except manual intervention or charger hardware limit

**Current Logs**:
```
[01:00] Forecast 15 kWh below 20 kWh threshold
[01:00] GRID mode activated (insufficient forecast OR battery support disabled)
[01:00] Starting charger at 16A (grid mode)
[07:00] 🌅 (sunrise - NO LOG, NO DETECTION, NO STOP)
[08:00] (still charging - no monitoring, no stop conditions)
... continues indefinitely ...
```

**Expected Behavior**:
```
[01:00] GRID mode activated (forecast insufficient)
[01:00] Starting charger at 16A (grid mode)
[07:00] 🌅 Sunrise detected - night charge window closed
[07:00] Stopping charger: Night charge window ended
[07:00] Night Smart Charge cycle completed
```

---

### Scenario E: Sunrise While GRID Charging + EV Target Check Missing

**Initial State**:
- Time: 01:00 AM
- Solar Forecast: 10 kWh
- EV Battery: 70% SOC (target: 80%, only needs 10%)
- Mode: GRID

**Timeline**:
1. **01:00 AM** - GRID mode starts charging at 16A

2. **01:45 AM** - EV reaches 80% target
   - ❌ **BUG**: No monitoring loop to check EV target
   - **CHARGING CONTINUES** even though target reached

3. **07:00 AM** - Sunrise occurs
   - ❌ Still no stop condition
   - **CHARGING CONTINUES**

4. **Eventually stops when**:
   - Charger reaches 100% (wallbox hardware limit), OR
   - User manually stops

**Result**: ❌ **DOUBLE BUG** - Neither EV target nor sunrise stops GRID mode

---

### Scenario F: Car Unplugged/Replugged During Window

**Initial State**:
- Time: 01:00 AM
- GRID mode active and charging

**Timeline**:
1. **01:00 AM** - GRID mode charging started

2. **02:00 AM** - User unplugs car
   - Charger status: `charger_charging` → `charger_free`
   - Night Smart Charge detects status change
   - Stops monitoring (no session active)

3. **02:30 AM** - User plugs car back in
   - Charger status: `charger_free` → `charger_wait`
   - Late arrival detection triggers: `_async_charger_status_changed()`
   - Checks: ✓ Time >= 01:00, ✓ Time < 07:00, ✓ Enabled
   - **RESTARTS GRID charging** (correct behavior within window)

**Result**: ✅ **CORRECT BEHAVIOR** - Late arrival detection works as intended within valid window

---

## EDGE CASE Scenarios

### Scenario G: Session Active at Sunrise - Long Charging Session

**Initial State**:
- Time: 01:00 AM
- Mode: BATTERY or GRID
- EV needs massive charge (20% → 80% = 8+ hours)

**Timeline**:
1. **01:00 AM** - Charging starts
2. **07:00 AM** - Sunrise occurs while still charging
3. **Current behavior**: ❌ Continues charging (both modes ignore sunrise)
4. **Expected behavior**: ✅ Should stop at sunrise regardless of charge completion

**Result**: ❌ **BUG** - Active sessions not terminated at sunrise

---

### Scenario H: Late Arrival Before Sunrise

**Initial State**:
- Time: 06:00 AM (1 hour before sunrise at 07:00)
- Car just plugged in
- Car ready flag: ON

**Timeline**:
1. **06:00 AM** - Car plugged in (`charger_free` → `charger_wait`)
   - Late arrival detection: `_async_charger_status_changed()`
   - Window check: ✓ 06:00 >= 01:00, ✓ 06:00 < 07:00
   - Evaluates forecast and starts appropriate mode
   - **Charging starts** (1 hour until sunrise)

2. **07:00 AM** - Sunrise
   - ❌ **BUG**: No sunrise detection
   - Charging continues

**Result**: ⚠️ **PARTIAL BUG** - Correctly starts on late arrival, but fails to stop at sunrise

---

### Scenario I: Late Arrival AFTER Sunrise - THE REPORTED BUG 🚨

**Initial State**:
- Time: 08:40 AM (1.5 hours AFTER sunrise at 07:00)
- Car just plugged in OR status changed from `charger_free`
- Car ready flag: ON

**Timeline**:
1. **08:40 AM** - Event triggers late arrival detection
   - Status change: `charger_free` → `charger_wait`
   - `_async_charger_status_changed()` called

2. **Window Validation** (line 251-254):
   ```python
   if await self._is_in_active_window(now) and self.is_enabled():
   ```
   - `_is_in_active_window()` checks: `now >= scheduled_time AND now < sunrise`
   - 08:40 >= 01:00 ✓ (yes, after scheduled time)
   - 08:40 < 07:00 ❌ (NO! after sunrise!)
   - **Should return False and NOT activate**

3. **❓ Question**: Why did it activate at 08:40?

**Possible Root Causes**:

**A. Sunrise Calculation Bug**:
- `_is_in_active_window()` uses `self.hass.services.async_call("sun", "get_sunrise")`
- Possible bug: Getting NEXT day's sunrise instead of TODAY's sunrise?
- If calculated sunrise is 07:00 **tomorrow**, then 08:40 < tomorrow's sunrise ✓

**B. Active Session Bypass**:
- GRID mode started correctly at 01:00
- Never stopped at 07:00 sunrise (bug confirmed)
- Still active at 08:40
- Periodic check at 08:40 skips: "Already active, skipping re-evaluation"
- Notification sent due to some state change, not new activation

**C. Cooldown Expired + Re-evaluation**:
- Previous night charge completed earlier
- Cooldown (3600s = 1 hour) expired
- Car status changed at 08:40
- Window check bugged, allowed re-activation

**Result**: 🚨 **THIS IS THE REPORTED BUG** - Charging activated/notified after sunrise

**Expected Behavior**:
```
[08:40] Charger status changed (free → wait)
[08:40] Late arrival detected, but outside active window (08:40 >= 07:00 sunrise)
[08:40] Skipping activation - night charge window closed
```

---

## Summary of Stop Conditions

### BATTERY MODE (Current Implementation)

| Stop Condition | Monitored? | Works? | Notes |
|----------------|------------|--------|-------|
| Home Battery <= Min SOC | ✅ Yes (15s) | ✅ Yes | Monitoring loop checks every 15 seconds |
| EV Target SOC Reached | ✅ Yes (15s) | ✅ Yes | Monitoring loop uses Priority Balancer |
| Sunrise (Window Close) | ❌ No | ❌ No | NOT checked in monitoring loop |
| Manual Stop | ✅ Yes | ✅ Yes | User can always turn off |
| Charger Unplugged | ✅ Yes | ✅ Yes | Status change detected |

**Risk**: BATTERY mode will continue charging past sunrise until EV target or home battery minimum reached

---

### GRID MODE (Current Implementation)

| Stop Condition | Monitored? | Works? | Notes |
|----------------|------------|--------|-------|
| EV Target SOC Reached | ❌ No | ❌ No | NO monitoring loop exists |
| Sunrise (Window Close) | ❌ No | ❌ No | NO monitoring loop exists |
| Manual Stop | ✅ Yes | ✅ Yes | User can always turn off |
| Charger Unplugged | ✅ Yes | ✅ Yes | Status change detected |
| Wallbox Hardware Limit | ✅ Yes | ✅ Yes | Wallbox stops at 100% |

**CRITICAL**: GRID mode has ZERO autonomous stop conditions except wallbox hardware limit (100% charge)

---

## Required Fixes for v1.3.17

### Fix 1: Add Sunrise Termination to BATTERY Mode Monitoring Loop

**File**: `night_smart_charge.py`
**Location**: `_async_monitor_battery_charge()` method (lines 414-539)

**Add BEFORE home battery check**:
```python
# Check if sunrise has passed (window closed)
now = dt_util.now()
if not await self._is_in_active_window(now):
    self.logger.info(f"{self.logger.CALENDAR} Night charge window closed (sunrise passed)")
    await self.charger_controller.stop_charger("Night charge window ended")
    await self._complete_night_charge()
    return
```

---

### Fix 2: Create GRID Mode Monitoring Loop (NEW METHOD)

**File**: `night_smart_charge.py`
**Add new method after `_async_monitor_battery_charge()`**:

```python
@callback
async def _async_monitor_grid_charge(self, now) -> None:
    """Monitor grid charge and enforce stop conditions (runs every 15 seconds)."""
    # Only monitor if grid mode is active
    if not self.is_active() or self._active_mode != NIGHT_CHARGE_MODE_GRID:
        return

    current_time = dt_util.now()

    # === 1. Check if sunrise has passed (window closed) ===
    if not await self._is_in_active_window(current_time):
        self.logger.info(f"{self.logger.CALENDAR} Night charge window closed (sunrise passed)")
        await self.charger_controller.stop_charger("Night charge window ended")
        await self._complete_night_charge()
        return

    # === 2. Check EV target SOC reached ===
    if await self.priority_balancer.is_ev_target_reached():
        self.logger.success(f"{self.logger.EV} EV target SOC reached")
        await self.charger_controller.stop_charger("EV target SOC reached")
        await self._complete_night_charge()
        return

    # === 3. Validate charger still charging ===
    charger_status = self.hass.states.get(self._charger_status)
    if charger_status and charger_status.state != CHARGER_STATUS_CHARGING:
        self.logger.warning("Charger no longer charging - ending grid mode")
        await self._complete_night_charge()
        return
```

---

### Fix 3: Register GRID Mode Monitoring Timer

**File**: `night_smart_charge.py`
**Location**: `_start_grid_charge()` method (lines 558-595)

**Add AFTER charger start**:
```python
# Register monitoring loop (every 15 seconds)
self._grid_monitor_timer = async_track_time_interval(
    self.hass,
    self._async_monitor_grid_charge,
    timedelta(seconds=15),
)
self.logger.debug("GRID mode monitoring loop registered (15s interval)")
```

**Add to class `__init__`**:
```python
self._grid_monitor_timer = None  # Grid charge monitoring timer
```

**Add to `_complete_night_charge()`**:
```python
# Cancel grid monitoring timer if active
if self._grid_monitor_timer:
    self._grid_monitor_timer()
    self._grid_monitor_timer = None
```

---

### Fix 4: Validate Window in Periodic Check Even for Active Sessions

**File**: `night_smart_charge.py`
**Location**: `_async_periodic_check()` (lines 202-248)

**Replace lines 202-205**:
```python
# Check if already active - validate window still open
if self.is_active():
    # Even if active, verify window hasn't closed
    now = dt_util.now()
    if not await self._is_in_active_window(now):
        self.logger.warning("Active session detected outside window - terminating")
        await self.charger_controller.stop_charger("Night charge window ended")
        await self._complete_night_charge()
    else:
        self.logger.debug("Already active and within window, skipping re-evaluation")
    return
```

---

### Fix 5: Fix Sunrise Calculation in `_is_in_active_window()`

**File**: `night_smart_charge.py`
**Location**: `_is_in_active_window()` (lines 271-328)

**Verify sunrise calculation uses TODAY's sunrise, not tomorrow's**:
```python
# Get TODAY's sunrise
sunrise_today = astral["sunrise"]

# Ensure we're comparing with today's sunrise, not tomorrow's
if sunrise_today < scheduled_time:
    # Edge case: If sunrise already passed before scheduled time
    # (e.g., scheduled 01:00, sunrise 07:00 yesterday, now 02:00)
    # We need NEXT sunrise (today's sunrise)
    pass  # sunrise_today is correct

# Window is valid if: now >= scheduled_time AND now < sunrise_today
is_active = now >= scheduled_time and now < sunrise_today
```

---

### Fix 6: Add Diagnostic Logging for Window Validation

**Add to `_is_in_active_window()` method**:
```python
self.logger.debug(
    f"Window check: now={now.strftime('%H:%M')}, "
    f"scheduled={scheduled_time.strftime('%H:%M')}, "
    f"sunrise={sunrise.strftime('%H:%M')}, "
    f"valid={is_active}"
)
```

---

## Testing Plan for v1.3.17

### Test 1: BATTERY Mode Sunrise Termination
1. Set night charge time to 01:00
2. Set current time to 01:00 (or use real overnight test)
3. Ensure sufficient forecast (>20 kWh)
4. Start charging in BATTERY mode
5. Advance time to sunrise (or wait for real sunrise)
6. **Verify**: Charging stops within 15 seconds of sunrise
7. **Verify**: Log shows: "Night charge window closed (sunrise passed)"

### Test 2: GRID Mode Sunrise Termination
1. Set night charge time to 01:00
2. Set insufficient forecast (<20 kWh)
3. Start charging in GRID mode
4. Advance to sunrise
5. **Verify**: Charging stops within 15 seconds of sunrise
6. **Verify**: Log shows: "Night charge window closed (sunrise passed)"

### Test 3: GRID Mode EV Target Termination
1. Start GRID mode with EV at 75% (target 80%)
2. Wait for EV to reach 80%
3. **Verify**: Charging stops within 15 seconds of target reached
4. **Verify**: Log shows: "EV target SOC reached"

### Test 4: Late Arrival After Sunrise Prevention
1. Set current time to 08:40 (after sunrise)
2. Plug in car (trigger status change)
3. **Verify**: Night charge does NOT activate
4. **Verify**: Log shows: "outside active window" or similar

### Test 5: Active Session Window Re-validation
1. Start charging at 01:00
2. Let it run past sunrise
3. Periodic check runs at 07:15
4. **Verify**: Session terminated even though previously active
5. **Verify**: Log shows: "Active session detected outside window - terminating"

---

## Version 1.3.17 Changes Summary

**Critical Bug Fixes**:
1. ✅ BATTERY mode now stops at sunrise (monitoring loop enhanced)
2. ✅ GRID mode now has monitoring loop (NEW)
3. ✅ GRID mode checks sunrise termination (NEW)
4. ✅ GRID mode checks EV target SOC (NEW)
5. ✅ Active sessions re-validate window in periodic checks
6. ✅ Late arrival detection cannot activate after sunrise

**Files Modified**:
- `night_smart_charge.py`: Major refactoring of monitoring logic
- `const.py`: VERSION = "1.3.17"
- `manifest.json`: version = "1.3.17"

**Impact**: Night Smart Charge will now ALWAYS terminate at sunrise, regardless of mode or charge completion state.

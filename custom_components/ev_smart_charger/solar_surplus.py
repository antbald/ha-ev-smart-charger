"""Solar Surplus Charging Profile automation."""
from __future__ import annotations
import logging
from datetime import timedelta

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers import entity_registry as er

from .const import (
    CHARGER_AMP_LEVELS,
    CHARGER_STATUS_FREE,
    VOLTAGE_EU,
    CONF_EV_CHARGER_SWITCH,
    CONF_EV_CHARGER_CURRENT,
    CONF_EV_CHARGER_STATUS,
    CONF_FV_PRODUCTION,
    CONF_HOME_CONSUMPTION,
    CONF_GRID_IMPORT,
    CONF_SOC_CAR,
    CONF_SOC_HOME,
    FALLBACK_AMPERAGE_WITH_BATTERY,
    PRIORITY_EV,
    PRIORITY_HOME,
    PRIORITY_EV_FREE,
)

_LOGGER = logging.getLogger(__name__)


class SolarSurplusAutomation:
    """Manages Solar Surplus charging profile."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry_id: str,
        config: dict,
    ) -> None:
        """Initialize the Solar Surplus automation."""
        self.hass = hass
        self.entry_id = entry_id
        self.config = config

        # User-configured entities
        self._charger_switch = config.get(CONF_EV_CHARGER_SWITCH)
        self._charger_current = config.get(CONF_EV_CHARGER_CURRENT)
        self._charger_status = config.get(CONF_EV_CHARGER_STATUS)
        self._fv_production = config.get(CONF_FV_PRODUCTION)
        self._home_consumption = config.get(CONF_HOME_CONSUMPTION)
        self._grid_import = config.get(CONF_GRID_IMPORT)
        self._soc_car = config.get(CONF_SOC_CAR)
        self._soc_home = config.get(CONF_SOC_HOME)

        # Helper entities (will be discovered)
        self._forza_ricarica_entity = None
        self._charging_profile_entity = None
        self._check_interval_entity = None
        self._grid_import_threshold_entity = None
        self._grid_import_delay_entity = None
        self._surplus_drop_delay_entity = None
        self._use_home_battery_entity = None
        self._home_battery_min_soc_entity = None
        self._priority_balancer_enabled_entity = None
        self._ev_min_soc_monday_entity = None
        self._ev_min_soc_tuesday_entity = None
        self._ev_min_soc_wednesday_entity = None
        self._ev_min_soc_thursday_entity = None
        self._ev_min_soc_friday_entity = None
        self._ev_min_soc_saturday_entity = None
        self._ev_min_soc_sunday_entity = None
        self._priority_state_sensor_entity = None

        # Timer for periodic checks
        self._timer_unsub = None

        # Current charger state tracking
        self._current_amperage = 6  # Always start with 6A

        # State tracking for v0.7.0 enhancements
        self._last_grid_import_high = None  # Timestamp when grid import exceeded threshold
        self._last_surplus_sufficient = None  # Timestamp when surplus was last sufficient
        self._is_ramping_down = False  # Flag for gradual ramp-down in progress
        self._target_ramp_amperage = None  # Target amperage for ramp-down

        # State tracking for v0.8.0 Priority Balancer
        self._current_priority = PRIORITY_EV_FREE  # Current charging priority

    def _find_entity_by_suffix(self, suffix: str) -> str | None:
        """Find an entity by its suffix using entity registry."""
        # Use entity registry instead of state machine for reliability
        entity_registry = er.async_get(self.hass)

        # Search through all entities in the registry
        for entity in entity_registry.entities.values():
            if entity.entity_id.endswith(suffix):
                _LOGGER.debug(f"Found helper entity in registry: {entity.entity_id}")
                return entity.entity_id

        # Fallback: try state machine if not in registry yet
        for entity_id in self.hass.states.async_entity_ids():
            if entity_id.endswith(suffix):
                _LOGGER.debug(f"Found helper entity in state machine: {entity_id}")
                return entity_id

        _LOGGER.warning(f"Helper entity with suffix '{suffix}' not found: {suffix}")
        return None

    async def async_setup(self) -> None:
        """Set up the Solar Surplus automation."""
        # Find helper entities
        self._forza_ricarica_entity = self._find_entity_by_suffix("evsc_forza_ricarica")
        self._charging_profile_entity = self._find_entity_by_suffix("evsc_charging_profile")
        self._check_interval_entity = self._find_entity_by_suffix("evsc_check_interval")
        self._grid_import_threshold_entity = self._find_entity_by_suffix("evsc_grid_import_threshold")
        self._grid_import_delay_entity = self._find_entity_by_suffix("evsc_grid_import_delay")
        self._surplus_drop_delay_entity = self._find_entity_by_suffix("evsc_surplus_drop_delay")
        self._use_home_battery_entity = self._find_entity_by_suffix("evsc_use_home_battery")
        self._home_battery_min_soc_entity = self._find_entity_by_suffix("evsc_home_battery_min_soc")
        self._priority_balancer_enabled_entity = self._find_entity_by_suffix("evsc_priority_balancer_enabled")
        self._ev_min_soc_monday_entity = self._find_entity_by_suffix("evsc_ev_min_soc_monday")
        self._ev_min_soc_tuesday_entity = self._find_entity_by_suffix("evsc_ev_min_soc_tuesday")
        self._ev_min_soc_wednesday_entity = self._find_entity_by_suffix("evsc_ev_min_soc_wednesday")
        self._ev_min_soc_thursday_entity = self._find_entity_by_suffix("evsc_ev_min_soc_thursday")
        self._ev_min_soc_friday_entity = self._find_entity_by_suffix("evsc_ev_min_soc_friday")
        self._ev_min_soc_saturday_entity = self._find_entity_by_suffix("evsc_ev_min_soc_saturday")
        self._ev_min_soc_sunday_entity = self._find_entity_by_suffix("evsc_ev_min_soc_sunday")
        self._priority_state_sensor_entity = self._find_entity_by_suffix("evsc_priority_daily_state")

        if not all([
            self._forza_ricarica_entity,
            self._charging_profile_entity,
            self._check_interval_entity,
            self._grid_import_threshold_entity,
            self._grid_import_delay_entity,
            self._surplus_drop_delay_entity,
            self._use_home_battery_entity,
            self._home_battery_min_soc_entity,
            self._priority_balancer_enabled_entity,
            self._ev_min_soc_monday_entity,
            self._ev_min_soc_tuesday_entity,
            self._ev_min_soc_wednesday_entity,
            self._ev_min_soc_thursday_entity,
            self._ev_min_soc_friday_entity,
            self._ev_min_soc_saturday_entity,
            self._ev_min_soc_sunday_entity,
            self._priority_state_sensor_entity,
        ]):
            _LOGGER.error("❌ Solar Surplus: Required helper entities not found")
            return

        _LOGGER.info("✅ Solar Surplus automation initialized")

        # Start the periodic check timer
        await self._start_timer()

    async def _start_timer(self) -> None:
        """Start the periodic check timer."""
        # Get check interval from helper (in minutes)
        check_interval_state = self.hass.states.get(self._check_interval_entity)
        if check_interval_state:
            try:
                interval_minutes = int(float(check_interval_state.state))
            except (ValueError, TypeError):
                interval_minutes = 1  # Default to 1 minute
        else:
            interval_minutes = 1

        # Convert to timedelta
        interval = timedelta(minutes=interval_minutes)

        # Cancel existing timer if any
        if self._timer_unsub:
            self._timer_unsub()

        # Start new timer
        self._timer_unsub = async_track_time_interval(
            self.hass,
            self._async_periodic_check,
            interval,
        )

        _LOGGER.info(f"⏱️ Solar Surplus: Timer started with {interval_minutes} minute interval")

    async def _calculate_priority(self) -> tuple[str, dict]:
        """Calculate current charging priority based on daily SOC targets (v0.8.0).

        Returns:
            tuple: (priority_state, attributes_dict)
        """
        from datetime import datetime

        # Check if Priority Balancer is enabled
        balancer_state = self.hass.states.get(self._priority_balancer_enabled_entity)
        balancer_enabled = balancer_state and balancer_state.state == "on"

        # Get current day of week (0=Monday, 6=Sunday)
        today_idx = datetime.now().weekday()
        day_names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        day_name = day_names[today_idx]

        # Map day index to entity
        day_entities = [
            self._ev_min_soc_monday_entity,
            self._ev_min_soc_tuesday_entity,
            self._ev_min_soc_wednesday_entity,
            self._ev_min_soc_thursday_entity,
            self._ev_min_soc_friday_entity,
            self._ev_min_soc_saturday_entity,
            self._ev_min_soc_sunday_entity,
        ]

        # Initialize attributes dictionary
        attributes = {
            "balancer_enabled": balancer_enabled,
            "today": day_name,
        }

        # If balancer is not enabled, return EV_Free
        if not balancer_enabled:
            attributes["reason"] = "Priority Balancer disabled"
            return PRIORITY_EV_FREE, attributes

        # Get today's EV target SOC (ALWAYS reads fresh value from state machine)
        ev_target_state = self.hass.states.get(day_entities[today_idx])
        if not ev_target_state:
            attributes["reason"] = f"EV target SOC helper not found for {day_name}"
            _LOGGER.warning(f"⚠️ Priority Balancer: EV target SOC entity not found for {day_name}: {day_entities[today_idx]}")
            return PRIORITY_EV, attributes

        try:
            target_ev_soc = float(ev_target_state.state)
            _LOGGER.debug(f"🔄 Priority Balancer: Read fresh EV target SOC for {day_name}: {target_ev_soc}% from {day_entities[today_idx]}")
        except (ValueError, TypeError):
            attributes["reason"] = f"Invalid EV target SOC value for {day_name}"
            _LOGGER.warning(f"⚠️ Priority Balancer: Invalid EV target SOC value for {day_name}: {ev_target_state.state}")
            return PRIORITY_EV, attributes

        # Get home battery target SOC (ALWAYS reads fresh value from state machine)
        home_target_state = self.hass.states.get(self._home_battery_min_soc_entity)
        if not home_target_state:
            attributes["reason"] = "Home battery target SOC helper not found"
            _LOGGER.warning(f"⚠️ Priority Balancer: Home battery target SOC entity not found: {self._home_battery_min_soc_entity}")
            return PRIORITY_EV, attributes

        try:
            target_home_soc = float(home_target_state.state)
            _LOGGER.debug(f"🔄 Priority Balancer: Read fresh home battery target SOC: {target_home_soc}% from {self._home_battery_min_soc_entity}")
        except (ValueError, TypeError):
            attributes["reason"] = "Invalid home battery target SOC value"
            _LOGGER.warning(f"⚠️ Priority Balancer: Invalid home battery target SOC value: {home_target_state.state}")
            return PRIORITY_EV, attributes

        # Get current EV SOC
        ev_soc_state = self.hass.states.get(self._soc_car)
        if not ev_soc_state or ev_soc_state.state in ["unknown", "unavailable", "none", ""]:
            attributes["current_ev_soc"] = "unknown"
            attributes["target_ev_soc"] = target_ev_soc
            attributes["target_home_soc"] = target_home_soc
            attributes["reason"] = "EV SOC sensor unavailable - defaulting to EV priority"
            return PRIORITY_EV, attributes

        try:
            current_ev_soc = float(ev_soc_state.state)
            if current_ev_soc < 0 or current_ev_soc > 100:
                attributes["current_ev_soc"] = current_ev_soc
                attributes["target_ev_soc"] = target_ev_soc
                attributes["target_home_soc"] = target_home_soc
                attributes["reason"] = f"EV SOC out of range ({current_ev_soc}%) - defaulting to EV priority"
                return PRIORITY_EV, attributes
        except (ValueError, TypeError):
            attributes["current_ev_soc"] = "invalid"
            attributes["target_ev_soc"] = target_ev_soc
            attributes["target_home_soc"] = target_home_soc
            attributes["reason"] = "Invalid EV SOC value - defaulting to EV priority"
            return PRIORITY_EV, attributes

        # Get current Home Battery SOC
        home_soc_state = self.hass.states.get(self._soc_home)
        if not home_soc_state or home_soc_state.state in ["unknown", "unavailable", "none", ""]:
            attributes["current_ev_soc"] = current_ev_soc
            attributes["current_home_soc"] = "unknown"
            attributes["target_ev_soc"] = target_ev_soc
            attributes["target_home_soc"] = target_home_soc
            attributes["reason"] = "Home Battery SOC sensor unavailable - defaulting to EV priority"
            return PRIORITY_EV, attributes

        try:
            current_home_soc = float(home_soc_state.state)
            if current_home_soc < 0 or current_home_soc > 100:
                attributes["current_ev_soc"] = current_ev_soc
                attributes["current_home_soc"] = current_home_soc
                attributes["target_ev_soc"] = target_ev_soc
                attributes["target_home_soc"] = target_home_soc
                attributes["reason"] = f"Home SOC out of range ({current_home_soc}%) - defaulting to EV priority"
                return PRIORITY_EV, attributes
        except (ValueError, TypeError):
            attributes["current_ev_soc"] = current_ev_soc
            attributes["current_home_soc"] = "invalid"
            attributes["target_ev_soc"] = target_ev_soc
            attributes["target_home_soc"] = target_home_soc
            attributes["reason"] = "Invalid Home Battery SOC value - defaulting to EV priority"
            return PRIORITY_EV, attributes

        # All sensors valid - populate attributes
        attributes["current_ev_soc"] = current_ev_soc
        attributes["current_home_soc"] = current_home_soc
        attributes["target_ev_soc"] = target_ev_soc
        attributes["target_home_soc"] = target_home_soc

        # Decision logic (uses FRESH values read from state machine this cycle)
        _LOGGER.debug(f"🔄 Priority Balancer: Making decision with fresh values - EV: {current_ev_soc}% vs {target_ev_soc}%, Home: {current_home_soc}% vs {target_home_soc}%")

        if current_ev_soc < target_ev_soc:
            attributes["reason"] = f"EV below target ({current_ev_soc:.1f}% < {target_ev_soc}%)"
            _LOGGER.info(f"✅ Priority Balancer: Decision = PRIORITY_EV (EV {current_ev_soc:.1f}% < target {target_ev_soc}%)")
            return PRIORITY_EV, attributes
        elif current_home_soc < target_home_soc:
            attributes["reason"] = f"Home battery below target ({current_home_soc:.1f}% < {target_home_soc}%)"
            _LOGGER.info(f"✅ Priority Balancer: Decision = PRIORITY_HOME (Home {current_home_soc:.1f}% < target {target_home_soc}%)")
            return PRIORITY_HOME, attributes
        else:
            attributes["reason"] = f"Both targets met (EV: {current_ev_soc:.1f}% >= {target_ev_soc}%, Home: {current_home_soc:.1f}% >= {target_home_soc}%)"
            _LOGGER.info(f"✅ Priority Balancer: Decision = PRIORITY_EV_FREE (Both targets met)")
            return PRIORITY_EV_FREE, attributes

    async def _update_priority_sensor(self, priority: str, attributes: dict) -> None:
        """Update the priority state sensor with new value and attributes."""
        if not self._priority_state_sensor_entity:
            return

        self.hass.states.async_set(
            self._priority_state_sensor_entity,
            priority,
            attributes=attributes,
        )

    @callback
    async def _async_periodic_check(self, now=None) -> None:
        """Periodic check for solar surplus charging with v0.7.0 and v0.8.0 enhancements."""
        import time

        _LOGGER.info("=" * 80)
        _LOGGER.info("🔄 Solar Surplus v0.8.0: Starting periodic check")

        # Check if Forza Ricarica is ON (kill switch)
        forza_state = self.hass.states.get(self._forza_ricarica_entity)
        forza_on = forza_state and forza_state.state == "on"

        if forza_on:
            _LOGGER.info("🛑 Decision: Forza Ricarica is ON, skipping check")
            _LOGGER.info("=" * 80)
            return

        # Check if Solar Surplus profile is selected
        profile_state = self.hass.states.get(self._charging_profile_entity)
        current_profile = profile_state.state if profile_state else "unknown"

        if not profile_state or current_profile != "solar_surplus":
            _LOGGER.info(f"⏭️ Decision: Profile not 'solar_surplus' (current: {current_profile}), skipping")
            _LOGGER.info("=" * 80)
            return

        # Check charger status - only skip if charger_free
        charger_status_state = self.hass.states.get(self._charger_status)
        if not charger_status_state:
            _LOGGER.warning("⚠️ Decision: Charger status unavailable, skipping")
            _LOGGER.info("=" * 80)
            return

        charger_status = charger_status_state.state

        if charger_status == CHARGER_STATUS_FREE:
            _LOGGER.info("🔌 Decision: Charger is free (not connected), skipping")
            _LOGGER.info("=" * 80)
            return

        _LOGGER.info(f"✅ Charger status: '{charger_status}' - proceeding with check")

        # === PRIORITY DAILY CHARGING BALANCER (v0.8.0) ===
        priority, priority_attrs = await self._calculate_priority()
        self._current_priority = priority

        # Update priority state sensor
        await self._update_priority_sensor(priority, priority_attrs)

        _LOGGER.info("🎯 Priority Balancer Decision:")
        _LOGGER.info(f"   - Balancer Enabled: {priority_attrs.get('balancer_enabled', False)}")
        _LOGGER.info(f"   - Today: {priority_attrs.get('today', 'unknown')}")
        _LOGGER.info(f"   - Current EV SOC: {priority_attrs.get('current_ev_soc', 'N/A')}")
        _LOGGER.info(f"   - Target EV SOC: {priority_attrs.get('target_ev_soc', 'N/A')}")
        _LOGGER.info(f"   - Current Home SOC: {priority_attrs.get('current_home_soc', 'N/A')}")
        _LOGGER.info(f"   - Target Home SOC: {priority_attrs.get('target_home_soc', 'N/A')}")
        _LOGGER.info(f"   - Decision: Priority = {priority}")
        _LOGGER.info(f"   - Reason: {priority_attrs.get('reason', 'N/A')}")

        # If priority is HOME, stop EV charging
        if priority == PRIORITY_HOME:
            _LOGGER.info("🏠 Priority is HOME - stopping EV charging to prioritize home battery")
            _LOGGER.info("   EV charging will resume when home battery reaches target")

            # Stop EV charger
            charger_state = self.hass.states.get(self._charger_switch)
            if charger_state and charger_state.state == "on":
                await self.hass.services.async_call(
                    "switch",
                    "turn_off",
                    {"entity_id": self._charger_switch},
                    blocking=True,
                )
                _LOGGER.info("   ✅ EV charger stopped")
            else:
                _LOGGER.info("   ✅ EV charger already off")

            _LOGGER.info("=" * 80)
            return

        # Get all sensor and configuration values
        fv_state = self.hass.states.get(self._fv_production)
        consumption_state = self.hass.states.get(self._home_consumption)
        grid_import_state = self.hass.states.get(self._grid_import)
        grid_threshold_state = self.hass.states.get(self._grid_import_threshold_entity)
        grid_delay_state = self.hass.states.get(self._grid_import_delay_entity)
        surplus_delay_state = self.hass.states.get(self._surplus_drop_delay_entity)
        use_battery_state = self.hass.states.get(self._use_home_battery_entity)
        battery_min_soc_state = self.hass.states.get(self._home_battery_min_soc_entity)
        soc_home_state = self.hass.states.get(self._soc_home) if self._soc_home else None

        # Check for missing sensors
        if not all([fv_state, consumption_state, grid_import_state, grid_threshold_state,
                   grid_delay_state, surplus_delay_state, use_battery_state, battery_min_soc_state]):
            missing = []
            if not fv_state: missing.append("Solar Production")
            if not consumption_state: missing.append("Home Consumption")
            if not grid_import_state: missing.append("Grid Import")
            if not grid_threshold_state: missing.append("Grid Threshold")
            if not grid_delay_state: missing.append("Grid Import Delay")
            if not surplus_delay_state: missing.append("Surplus Drop Delay")
            if not use_battery_state: missing.append("Use Home Battery")
            if not battery_min_soc_state: missing.append("Home Battery Min SOC")

            _LOGGER.warning(f"⚠️ Decision: Sensors unavailable: {', '.join(missing)}")
            _LOGGER.info("=" * 80)
            return

        # Parse values
        try:
            fv_production = float(fv_state.state)
            home_consumption = float(consumption_state.state)
            grid_import = float(grid_import_state.state)
            grid_threshold = float(grid_threshold_state.state)
            grid_import_delay = float(grid_delay_state.state)
            surplus_drop_delay = float(surplus_delay_state.state)
            use_home_battery = use_battery_state.state == "on"
            battery_min_soc = float(battery_min_soc_state.state)

            # Home battery SOC (optional)
            home_battery_soc = None
            if soc_home_state and use_home_battery:
                try:
                    home_battery_soc = float(soc_home_state.state)
                except (ValueError, TypeError):
                    _LOGGER.warning("⚠️ Home Battery SOC value invalid, treating as unavailable")

        except (ValueError, TypeError) as e:
            _LOGGER.warning(f"⚠️ Decision: Invalid sensor values: {e}")
            _LOGGER.info("=" * 80)
            return

        # Get current amperage setting
        current_setting_state = self.hass.states.get(self._charger_current)
        if current_setting_state:
            try:
                current_amps = int(float(current_setting_state.state))
            except (ValueError, TypeError):
                current_amps = 6
        else:
            current_amps = 6

        # Calculate surplus
        surplus_watts = fv_production - home_consumption
        surplus_amps = surplus_watts / VOLTAGE_EU

        # Log comprehensive state
        _LOGGER.info("📊 Current Measurements:")
        _LOGGER.info(f"  - Solar Production: {fv_production}W")
        _LOGGER.info(f"  - Home Consumption: {home_consumption}W")
        _LOGGER.info(f"  - Surplus: {surplus_watts}W ({surplus_amps:.2f}A)")
        _LOGGER.info(f"  - Grid Import: {grid_import}W")
        _LOGGER.info(f"  - Current Charging: {current_amps}A")

        _LOGGER.info("⚙️ Configuration:")
        _LOGGER.info(f"  - Grid Import Threshold: {grid_threshold}W")
        _LOGGER.info(f"  - Grid Import Delay: {grid_import_delay}s")
        _LOGGER.info(f"  - Surplus Drop Delay: {surplus_drop_delay}s")
        _LOGGER.info(f"  - Use Home Battery: {use_home_battery}")
        if use_home_battery:
            _LOGGER.info(f"  - Home Battery Min SOC: {battery_min_soc}%")
            _LOGGER.info(f"  - Home Battery Current SOC: {home_battery_soc}%" if home_battery_soc is not None else "  - Home Battery SOC: unavailable")

        # === ENHANCEMENT 2A: Grid Import Delay Protection ===
        current_time = time.time()

        if grid_import > grid_threshold:
            # Grid import is high
            if self._last_grid_import_high is None:
                # First detection
                self._last_grid_import_high = current_time
                _LOGGER.info(f"⚠️ Grid import ({grid_import}W) > threshold ({grid_threshold}W) - Starting {grid_import_delay}s delay")
                _LOGGER.info(f"🕐 Decision: WAITING for grid import delay before reducing charging")
                _LOGGER.info("=" * 80)
                return
            else:
                # Check if delay has elapsed
                elapsed = current_time - self._last_grid_import_high
                if elapsed < grid_import_delay:
                    _LOGGER.info(f"⚠️ Grid import high, delay in progress: {elapsed:.1f}s / {grid_import_delay}s")
                    _LOGGER.info(f"🕐 Decision: WAITING (still {grid_import_delay - elapsed:.1f}s remaining)")
                    _LOGGER.info("=" * 80)
                    return
                else:
                    # Delay elapsed, take action
                    _LOGGER.warning(f"❌ Grid import delay ELAPSED ({elapsed:.1f}s >= {grid_import_delay}s)")
                    _LOGGER.info(f"⬇️ Decision: REDUCING charging to prevent grid import")
                    self._last_grid_import_high = None  # Reset for next time
                    await self._gradual_ramp_down(current_amps)
                    _LOGGER.info("=" * 80)
                    return
        else:
            # Grid import is acceptable, reset timer
            if self._last_grid_import_high is not None:
                _LOGGER.info(f"✅ Grid import now acceptable ({grid_import}W <= {grid_threshold}W), canceling delay")
            self._last_grid_import_high = None

        # === ENHANCEMENT 2B: Surplus Drop Delay + Home Battery Support ===
        target_amps = self._find_target_amperage(surplus_amps)

        _LOGGER.info(f"🎯 Target amperage based on surplus: {target_amps}A")

        # Check if we're in a ramp-down scenario
        if target_amps < current_amps:
            # Surplus has dropped

            # === ENHANCEMENT 3: Home Battery Support (v0.7.0) ===
            # Only activate if priority is EV or EV_Free (v0.8.0 integration)
            if use_home_battery and home_battery_soc is not None and home_battery_soc > battery_min_soc:
                if self._current_priority in [PRIORITY_EV, PRIORITY_EV_FREE]:
                    _LOGGER.info(f"🔋 Home battery available (SOC {home_battery_soc}% > {battery_min_soc}%)")
                    _LOGGER.info(f"💡 Decision: Using BATTERY SUPPORT mode - setting fixed {FALLBACK_AMPERAGE_WITH_BATTERY}A")
                    _LOGGER.info(f"   Reasoning: Battery can help bridge the gap between {target_amps}A and {FALLBACK_AMPERAGE_WITH_BATTERY}A")
                    _LOGGER.info(f"   Priority: {self._current_priority} (Battery Support allowed)")

                    if current_amps != FALLBACK_AMPERAGE_WITH_BATTERY:
                        await self._set_amperage(FALLBACK_AMPERAGE_WITH_BATTERY)
                    else:
                        _LOGGER.info(f"   Already at {FALLBACK_AMPERAGE_WITH_BATTERY}A, no change needed")

                    self._last_surplus_sufficient = None  # Reset surplus delay
                    self._is_ramping_down = False
                    self._target_ramp_amperage = None
                    _LOGGER.info("=" * 80)
                    return
                else:
                    _LOGGER.info(f"🔋 Battery support available but skipped (Priority={self._current_priority}, Battery Support only for EV/EV_Free)")

            # No battery support, check surplus drop delay
            if self._last_surplus_sufficient is None:
                # First detection of insufficient surplus
                self._last_surplus_sufficient = current_time
                _LOGGER.info(f"⚠️ Surplus dropped ({surplus_amps:.2f}A < {current_amps}A) - Starting {surplus_drop_delay}s delay")
                _LOGGER.info(f"🕐 Decision: WAITING for surplus drop delay before reducing")
                _LOGGER.info("=" * 80)
                return
            else:
                # Check if delay has elapsed
                elapsed = current_time - self._last_surplus_sufficient
                if elapsed < surplus_drop_delay:
                    _LOGGER.info(f"⚠️ Surplus drop delay in progress: {elapsed:.1f}s / {surplus_drop_delay}s")
                    _LOGGER.info(f"🕐 Decision: WAITING (still {surplus_drop_delay - elapsed:.1f}s remaining)")
                    _LOGGER.info("=" * 80)
                    return
                else:
                    # Delay elapsed, initiate gradual ramp-down
                    _LOGGER.warning(f"❌ Surplus drop delay ELAPSED ({elapsed:.1f}s >= {surplus_drop_delay}s)")
                    _LOGGER.info(f"⬇️ Decision: Starting GRADUAL RAMP-DOWN from {current_amps}A toward {target_amps}A")
                    self._last_surplus_sufficient = None  # Reset for next time
                    await self._gradual_ramp_down(current_amps)
                    _LOGGER.info("=" * 80)
                    return
        elif target_amps > current_amps:
            # Surplus has increased - immediate increase
            _LOGGER.info(f"⬆️ Surplus sufficient for increase ({surplus_amps:.2f}A >= {target_amps}A)")
            _LOGGER.info(f"💡 Decision: INCREASING amperage from {current_amps}A to {target_amps}A (immediate)")
            self._last_surplus_sufficient = None  # Reset
            self._is_ramping_down = False
            self._target_ramp_amperage = None
            await self._set_amperage(target_amps)
            _LOGGER.info("=" * 80)
            return
        else:
            # Target equals current - optimal
            _LOGGER.info(f"✅ Amperage optimal at {current_amps}A")
            _LOGGER.info(f"💡 Decision: NO CHANGE needed")
            self._last_surplus_sufficient = None  # Reset
            self._is_ramping_down = False
            self._target_ramp_amperage = None
            _LOGGER.info("=" * 80)
            return

    def _find_target_amperage(self, surplus_amps: float) -> int:
        """Find the appropriate amperage level from available steps."""
        # If surplus is less than minimum (6A), return 0 (stop charging)
        if surplus_amps < CHARGER_AMP_LEVELS[0]:
            return 0

        # Find the highest level that doesn't exceed surplus
        target = CHARGER_AMP_LEVELS[0]  # Start with minimum
        for level in CHARGER_AMP_LEVELS:
            if level <= surplus_amps:
                target = level
            else:
                break

        return target

    async def _set_amperage(self, amps: int) -> None:
        """Set charger amperage (instant increase)."""
        if amps == 0:
            # Stop charging
            _LOGGER.info("Solar Surplus: Insufficient surplus, stopping charger")
            await self.hass.services.async_call(
                "switch",
                "turn_off",
                {"entity_id": self._charger_switch},
                blocking=True,
            )
            return

        _LOGGER.info(f"Solar Surplus: Setting amperage to {amps}A")
        await self.hass.services.async_call(
            "number",
            "set_value",
            {"entity_id": self._charger_current, "value": amps},
            blocking=True,
        )

        # Ensure charger is on
        charger_state = self.hass.states.get(self._charger_switch)
        if charger_state and charger_state.state == "off":
            _LOGGER.info("Solar Surplus: Starting charger")
            await self.hass.services.async_call(
                "switch",
                "turn_on",
                {"entity_id": self._charger_switch},
                blocking=True,
            )

    async def _gradual_ramp_down(self, current_amps: int) -> None:
        """ENHANCEMENT 1: Gradually ramp down charging one step at a time.

        This prevents oscillations by reducing amperage step-by-step rather than
        jumping directly to the target. Each step requires the sequence:
        stop → wait 5s → set new value → wait 1s → start

        The next check interval will determine if we need to step down further.
        """
        _LOGGER.info(f"🔽 Starting gradual ramp-down from {current_amps}A")

        # Find current level index
        try:
            current_index = CHARGER_AMP_LEVELS.index(current_amps)
        except ValueError:
            _LOGGER.warning(f"⚠️ Current amperage {current_amps}A not in standard levels, defaulting to 6A")
            await self._adjust_amperage_down_one_step(6)
            return

        # Step down one level
        if current_index > 0:
            next_amps = CHARGER_AMP_LEVELS[current_index - 1]
            _LOGGER.info(f"📉 Stepping down ONE level: {current_amps}A → {next_amps}A")
            _LOGGER.info(f"   Next check will determine if further reduction is needed")
            await self._adjust_amperage_down_one_step(next_amps)
        else:
            # Already at minimum, stop charging
            _LOGGER.info(f"📉 Already at minimum level, stopping charger")
            await self._adjust_amperage_down_one_step(0)

    async def _adjust_amperage_down_one_step(self, target_amps: int) -> None:
        """Decrease amperage with proper sequence: stop → wait 5s → set → wait 1s → start.

        This is a single step reduction used by the gradual ramp-down feature.
        """
        import asyncio

        _LOGGER.info(f"🔧 Executing amperage change to {target_amps}A")

        # Step 1: Stop charger
        _LOGGER.info("   1/5: Stopping charger")
        await self.hass.services.async_call(
            "switch",
            "turn_off",
            {"entity_id": self._charger_switch},
            blocking=True,
        )

        # Step 2: Wait 5 seconds
        _LOGGER.info("   2/5: Waiting 5 seconds")
        await asyncio.sleep(5)

        # Step 3: Set new amperage
        if target_amps > 0:
            _LOGGER.info(f"   3/5: Setting amperage to {target_amps}A")
            await self.hass.services.async_call(
                "number",
                "set_value",
                {"entity_id": self._charger_current, "value": target_amps},
                blocking=True,
            )

            # Step 4: Wait 1 second
            _LOGGER.info("   4/5: Waiting 1 second")
            await asyncio.sleep(1)

            # Step 5: Start charger
            _LOGGER.info("   5/5: Restarting charger")
            await self.hass.services.async_call(
                "switch",
                "turn_on",
                {"entity_id": self._charger_switch},
                blocking=True,
            )
            _LOGGER.info(f"✅ Amperage successfully changed to {target_amps}A")
        else:
            _LOGGER.info("   3/5: Target is 0A, keeping charger off")
            _LOGGER.info("✅ Charger stopped")

    async def async_remove(self) -> None:
        """Remove the automation."""
        if self._timer_unsub:
            self._timer_unsub()
            self._timer_unsub = None
        _LOGGER.info("Solar Surplus automation removed")

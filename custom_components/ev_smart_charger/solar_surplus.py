"""Solar Surplus Charging Profile automation."""
from __future__ import annotations

import time
from datetime import timedelta, datetime

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.event import async_track_time_interval, async_track_state_change_event

from .const import (
    CHARGER_AMP_LEVELS,
    CHARGER_STATUS_FREE,
    VOLTAGE_EU,
    CONF_EV_CHARGER_STATUS,
    CONF_FV_PRODUCTION,
    CONF_HOME_CONSUMPTION,
    CONF_GRID_IMPORT,
    CONF_SOC_HOME,
    PRIORITY_EV,
    PRIORITY_HOME,
    PRIORITY_EV_FREE,
    SOLAR_SURPLUS_MIN_CHECK_INTERVAL,
    SOLAR_SURPLUS_MAX_CHECKS_PER_MINUTE,
    HELPER_BATTERY_SUPPORT_AMPERAGE_SUFFIX,
    SURPLUS_START_THRESHOLD,
    SURPLUS_STOP_THRESHOLD,
)
from .utils.logging_helper import EVSCLogger
from .utils.state_helper import get_state, get_float, get_bool, validate_sensor
from .utils.entity_registry_service import EntityRegistryService
from .utils.astral_time_service import AstralTimeService


class SolarSurplusAutomation:
    """Manages Solar Surplus charging profile with Priority Balancer integration."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry_id: str,
        config: dict,
        priority_balancer,
        charger_controller,
        night_smart_charge=None,
    ) -> None:
        """Initialize the Solar Surplus automation.

        Args:
            hass: Home Assistant instance
            entry_id: Config entry ID
            config: User configuration
            priority_balancer: PriorityBalancer instance for priority decisions
            charger_controller: ChargerController instance for charger operations
            night_smart_charge: Night Smart Charge instance (optional)
        """
        self.hass = hass
        self.entry_id = entry_id
        self.config = config
        self.priority_balancer = priority_balancer
        self.charger_controller = charger_controller
        self._night_smart_charge = night_smart_charge

        # Initialize logger, registry service, and astral time service
        self.logger = EVSCLogger("SOLAR SURPLUS")
        self._registry_service = EntityRegistryService(hass, entry_id)
        self._astral_service = AstralTimeService(hass)

        # User-configured entities
        self._charger_status = config.get(CONF_EV_CHARGER_STATUS)
        self._fv_production = config.get(CONF_FV_PRODUCTION)
        self._home_consumption = config.get(CONF_HOME_CONSUMPTION)
        self._grid_import = config.get(CONF_GRID_IMPORT)
        self._soc_home = config.get(CONF_SOC_HOME)

        # Helper entities (discovered during setup)
        self._forza_ricarica_entity = None
        self._charging_profile_entity = None
        self._check_interval_entity = None
        self._grid_import_threshold_entity = None
        self._grid_import_delay_entity = None
        self._surplus_drop_delay_entity = None
        self._use_home_battery_entity = None
        self._home_battery_min_soc_entity = None
        self._battery_support_amperage_entity = None
        self._solar_surplus_diagnostic_sensor_entity = None

        # Timer for periodic checks
        self._timer_unsub = None

        # SOC listener for real-time battery monitoring
        self._soc_listener_unsub = None

        # State tracking
        self._last_grid_import_high = None  # Timestamp when grid import exceeded threshold
        self._last_surplus_sufficient = None  # Timestamp when surplus was last sufficient
        self._battery_support_active = False  # Flag for home battery support mode
        self._surplus_stable_since = None  # Timestamp when surplus became stable (for hysteresis)
        self._waiting_for_surplus_decrease = False  # Flag for surplus drop delay in EV_FREE mode
        self._surplus_decrease_start_time = None  # Timestamp when surplus drop started

        # Rate limiting
        self._last_check_time = None
        self._check_count = 0
        self._check_count_reset_time = None

        # Sensor error tracking (prevent log spam)
        self._sensor_error_state = {}  # {sensor_entity_id: error_message}

    def _find_entity_by_suffix(self, suffix: str) -> str | None:
        """Find an entity by its suffix using EntityRegistryService."""
        entity_id = self._registry_service.find_by_suffix_filtered(suffix)

        if entity_id:
            self.logger.debug(f"Found helper entity: {entity_id}")
        else:
            self.logger.warning(
                f"Helper entity with suffix '{suffix}' not found for config_entry {self.entry_id}"
            )

        return entity_id

    async def async_setup(self) -> None:
        """Set up the Solar Surplus automation."""
        # Find helper entities (optional for backward compatibility)
        self._forza_ricarica_entity = self._find_entity_by_suffix("evsc_forza_ricarica")
        self._charging_profile_entity = self._find_entity_by_suffix("evsc_charging_profile")
        self._check_interval_entity = self._find_entity_by_suffix("evsc_check_interval")
        self._grid_import_threshold_entity = self._find_entity_by_suffix("evsc_grid_import_threshold")
        self._grid_import_delay_entity = self._find_entity_by_suffix("evsc_grid_import_delay")
        self._surplus_drop_delay_entity = self._find_entity_by_suffix("evsc_surplus_drop_delay")
        self._use_home_battery_entity = self._find_entity_by_suffix("evsc_use_home_battery")
        self._home_battery_min_soc_entity = self._find_entity_by_suffix("evsc_home_battery_min_soc")
        self._battery_support_amperage_entity = self._find_entity_by_suffix(HELPER_BATTERY_SUPPORT_AMPERAGE_SUFFIX)
        self._solar_surplus_diagnostic_sensor_entity = self._find_entity_by_suffix("evsc_solar_surplus_diagnostic")

        # Warn about missing entities (backward compatibility)
        missing_entities = []
        if not self._forza_ricarica_entity:
            missing_entities.append("evsc_forza_ricarica")
        if not self._charging_profile_entity:
            missing_entities.append("evsc_charging_profile")
        if not self._check_interval_entity:
            missing_entities.append("evsc_check_interval")
        if not self._grid_import_threshold_entity:
            missing_entities.append("evsc_grid_import_threshold")
        if not self._grid_import_delay_entity:
            missing_entities.append("evsc_grid_import_delay")
        if not self._surplus_drop_delay_entity:
            missing_entities.append("evsc_surplus_drop_delay")
        if not self._use_home_battery_entity:
            missing_entities.append("evsc_use_home_battery")
        if not self._home_battery_min_soc_entity:
            missing_entities.append("evsc_home_battery_min_soc")
        if not self._battery_support_amperage_entity:
            missing_entities.append(HELPER_BATTERY_SUPPORT_AMPERAGE_SUFFIX)

        if missing_entities:
            self.logger.warning(
                f"Helper entities not found: {', '.join(missing_entities)} - "
                f"Using default values. Restart Home Assistant to create missing helper entities."
            )

        # Register listener for real-time home battery SOC monitoring
        if self._soc_home:
            self._soc_listener_unsub = async_track_state_change_event(
                self.hass,
                [self._soc_home],
                self._async_home_battery_soc_changed,
            )
            self.logger.info(f"Real-time SOC listener registered on {self._soc_home}")
        else:
            self.logger.warning("Home battery SOC sensor not configured - real-time monitoring disabled")

        self.logger.success("Solar Surplus automation initialized")
        await self._start_timer()

    async def _start_timer(self) -> None:
        """Start the periodic check timer."""
        interval_minutes = get_float(self.hass, self._check_interval_entity, 1)
        interval = timedelta(minutes=interval_minutes)

        if self._timer_unsub:
            self._timer_unsub()

        self._timer_unsub = async_track_time_interval(
            self.hass,
            self._async_periodic_check,
            interval,
        )

        self.logger.info(f"Timer started with {interval_minutes} minute interval")

    @callback
    async def _async_home_battery_soc_changed(self, event) -> None:
        """Handle home battery SOC state changes for immediate battery protection.

        This listener provides real-time monitoring of home battery SOC to ensure
        immediate deactivation of battery support when SOC drops below minimum threshold.

        Without this listener, there would be up to 1 minute delay (periodic check interval)
        between SOC dropping below minimum and battery support deactivation, potentially
        draining the battery below the user's configured minimum.

        Args:
            event: State change event containing old_state and new_state
        """
        # Skip if battery support is not currently active
        if not self._battery_support_active:
            return

        # Get new SOC value
        new_state = event.data.get("new_state")
        if not new_state or new_state.state in ("unknown", "unavailable"):
            return

        try:
            new_soc = float(new_state.state)
        except (ValueError, TypeError):
            self.logger.warning(f"Invalid SOC value: {new_state.state}")
            return

        # Get minimum SOC threshold
        min_soc = get_float(self.hass, self._home_battery_min_soc_entity, 20)

        # Check if SOC dropped below minimum
        if new_soc <= min_soc and self._battery_support_active:
            self.logger.warning(
                f"{self.logger.BATTERY} Home battery SOC dropped to {new_soc:.1f}% "
                f"(minimum: {min_soc:.0f}%) - Deactivating battery support"
            )

            # Deactivate battery support immediately
            self._battery_support_active = False

            # Trigger immediate recalculation ONLY if rate limit allows
            # Avoid triggering if last check was too recent
            current_time = time.time()
            if not self._last_check_time or (current_time - self._last_check_time) >= SOLAR_SURPLUS_MIN_CHECK_INTERVAL:
                self.hass.async_create_task(self._async_periodic_check())
            else:
                self.logger.debug(
                    f"{self.logger.BATTERY} Skipping immediate check due to rate limit "
                    f"({current_time - self._last_check_time:.1f}s since last check)"
                )

    @callback
    async def _async_periodic_check(self, now=None) -> None:
        """Periodic check for solar surplus charging."""
        # === Rate Limiting ===
        current_time = time.time()
        if self._last_check_time and (current_time - self._last_check_time) < SOLAR_SURPLUS_MIN_CHECK_INTERVAL:
            return

        self._last_check_time = current_time

        # Count checks per minute
        if self._check_count_reset_time is None or (current_time - self._check_count_reset_time) > 60:
            # Log rate limit warning only once per minute
            if self._check_count > SOLAR_SURPLUS_MAX_CHECKS_PER_MINUTE:
                self.logger.warning(f"⚠️ Rate limit exceeded: {self._check_count} checks in last minute")
            self._check_count = 0
            self._check_count_reset_time = current_time

        self._check_count += 1

        self.logger.separator()
        self.logger.start(f"Periodic check #{self._check_count}")

        # === 1. Check Forza Ricarica (Kill Switch) ===
        if get_bool(self.hass, self._forza_ricarica_entity):
            self.logger.skip("Forza Ricarica is ON")
            await self._update_diagnostic_sensor(
                "SKIPPED: Forza Ricarica ON",
                {"reason": "Override switch enabled", "last_check": datetime.now().isoformat()}
            )
            self.logger.separator()
            return

        # === 2. Check Nighttime (Solar Surplus only works during daytime) ===
        from homeassistant.util import dt as dt_util
        from .const import NIGHT_CHARGE_COOLDOWN_SECONDS
        now = dt_util.now()

        if self._astral_service.is_nighttime(now):
            self.logger.skip("Nighttime - Solar Surplus only operates during daytime (sunrise to sunset)")
            await self._update_diagnostic_sensor(
                "SKIPPED: Nighttime",
                {"reason": "Solar production unavailable at night", "last_check": datetime.now().isoformat()}
            )
            self.logger.separator()
            return

        # === 3. Check Night Smart Charge ===
        if self._night_smart_charge and self._night_smart_charge.is_active():
            night_mode = self._night_smart_charge.get_active_mode()
            self.logger.skip(f"Night Smart Charge active (mode: {night_mode})")
            await self._update_diagnostic_sensor(
                "SKIPPED: Night Smart Charge Active",
                {"night_mode": night_mode, "last_check": datetime.now().isoformat()}
            )
            self.logger.separator()
            return

        # === 4. Check Night Smart Charge Cooldown ===
        if self._night_smart_charge and hasattr(self._night_smart_charge, '_last_completion_time') and \
           self._night_smart_charge._last_completion_time:
            time_since = (now - self._night_smart_charge._last_completion_time).total_seconds()
            if time_since < NIGHT_CHARGE_COOLDOWN_SECONDS:
                self.logger.skip(
                    f"Night Charge completed {time_since:.0f}s ago "
                    f"(cooldown: {NIGHT_CHARGE_COOLDOWN_SECONDS}s) - respecting cooldown period"
                )
                await self._update_diagnostic_sensor(
                    "SKIPPED: Night Charge Cooldown",
                    {
                        "reason": f"Cooldown active ({time_since:.0f}s / {NIGHT_CHARGE_COOLDOWN_SECONDS}s)",
                        "last_check": datetime.now().isoformat()
                    }
                )
                self.logger.separator()
                return

        # === 5. Check Charging Profile ===
        current_profile = get_state(self.hass, self._charging_profile_entity)
        if current_profile != "solar_surplus":
            self.logger.skip(f"Profile not 'solar_surplus' (current: {current_profile})")
            await self._update_diagnostic_sensor(
                "SKIPPED: Wrong Profile",
                {"profile": current_profile, "last_check": datetime.now().isoformat()}
            )
            self.logger.separator()
            return

        # === 6. Check Charger Status ===
        charger_status = get_state(self.hass, self._charger_status)
        if not charger_status:
            self.logger.warning("Charger status unavailable")
            self.logger.separator()
            return

        if charger_status == CHARGER_STATUS_FREE:
            self.logger.skip("Charger is free (not connected)")
            self.logger.separator()
            return

        self.logger.info(f"Charger status: '{charger_status}' - proceeding")

        # === 7. Validate Sensors (with throttled logging to prevent spam) ===
        sensor_errors = []
        sensors_to_validate = [
            (self._fv_production, "Solar Production"),
            (self._home_consumption, "Home Consumption"),
            (self._grid_import, "Grid Import"),
        ]

        # Check each sensor and track error state changes
        new_errors = False
        for entity_id, sensor_name in sensors_to_validate:
            is_valid, error_msg = validate_sensor(self.hass, entity_id, sensor_name)

            if not is_valid:
                sensor_errors.append(error_msg)
                # Only log if this is a NEW error or error message changed
                if entity_id not in self._sensor_error_state or self._sensor_error_state[entity_id] != error_msg:
                    self._sensor_error_state[entity_id] = error_msg
                    new_errors = True
            else:
                # Sensor is now valid - check if it was previously in error state
                if entity_id in self._sensor_error_state:
                    self.logger.info(f"✅ {sensor_name} sensor recovered (was: {self._sensor_error_state[entity_id]})")
                    del self._sensor_error_state[entity_id]

        if sensor_errors:
            # Only log full error details if there are NEW errors
            if new_errors:
                self.logger.error("Sensor validation failed:")
                for error in sensor_errors:
                    self.logger.error(f"  - {error}")
            else:
                # Existing errors - just update diagnostic sensor quietly
                self.logger.debug(f"Sensor errors still present ({len(sensor_errors)} sensors unavailable)")

            await self._update_diagnostic_sensor(
                "ERROR: Invalid sensor values",
                {"errors": sensor_errors, "last_check": datetime.now().isoformat()}
            )
            self.logger.separator()
            return

        # === 8. Calculate Surplus ===
        fv_production = get_float(self.hass, self._fv_production)
        home_consumption = get_float(self.hass, self._home_consumption)
        grid_import = get_float(self.hass, self._grid_import)
        surplus_watts = fv_production - home_consumption
        surplus_amps = surplus_watts / VOLTAGE_EU

        self.logger.info(f"Solar Production: {fv_production}W")
        self.logger.info(f"Home Consumption: {home_consumption}W")
        self.logger.info(f"Surplus: {surplus_watts}W ({surplus_amps:.2f}A)")
        self.logger.info(f"Grid Import: {grid_import}W")

        # === 9. Priority Balancer Decision ===
        priority = None
        if self.priority_balancer.is_enabled():
            priority = await self.priority_balancer.calculate_priority()
            self.logger.info(f"Priority Balancer: {priority}")

            if priority == PRIORITY_HOME:
                self.logger.warning("Priority = HOME - Stopping EV charger")
                await self.charger_controller.stop_charger("Home battery needs charging (Priority = HOME)")
                self.logger.separator()
                return

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
                return
        else:
            self.logger.info("Priority Balancer disabled - using fallback mode")

        # === 10. Handle Home Battery Usage ===
        await self._handle_home_battery_usage(surplus_watts, priority)

        # === 11. Get Current Amperage (needed for hysteresis) ===
        charger_is_on = await self.charger_controller.is_charging()
        if charger_is_on:
            current_amps = await self.charger_controller.get_current_amperage() or 6
        else:
            current_amps = 0

        self.logger.info(f"Current charging: {current_amps}A (charger {'ON' if charger_is_on else 'OFF'})")

        # === 12. Calculate Target Amperage (with hysteresis) ===
        target_amps = self._calculate_target_amperage(surplus_watts, current_amps)
        self.logger.info(f"Target amperage: {target_amps}A")

        # === 13. Get Configuration Values ===
        grid_threshold = get_float(self.hass, self._grid_import_threshold_entity)
        grid_import_delay = get_float(self.hass, self._grid_import_delay_entity)
        surplus_drop_delay = get_float(self.hass, self._surplus_drop_delay_entity)

        # Update diagnostic sensor
        await self._update_diagnostic_sensor(
            f"CHECKING: {surplus_watts}W surplus ({surplus_amps:.1f}A)",
            {
                "last_check": datetime.now().isoformat(),
                "priority": priority if priority else "DISABLED",
                "solar_production_w": fv_production,
                "home_consumption_w": home_consumption,
                "surplus_w": surplus_watts,
                "surplus_a": round(surplus_amps, 2),
                "grid_import_w": grid_import,
                "current_charging_a": current_amps,
                "target_charging_a": target_amps,
                "charger_on": charger_is_on,
                "battery_support_active": self._battery_support_active,
            }
        )

        # === 14. Apply Charging Logic ===

        # Start charger if OFF and we have target amperage
        if not charger_is_on and target_amps > 0:
            self.logger.action(f"Starting charger with {target_amps}A")
            await self.charger_controller.start_charger(target_amps, "Solar surplus available")
            self.logger.separator()
            return

        # Grid Import Protection
        if grid_import > grid_threshold:
            await self._handle_grid_import_protection(grid_import, grid_threshold, grid_import_delay, current_amps)
            self.logger.separator()
            return

        # EV_FREE Mode: Apply delay before stopping (same as PRIORITY_EV)
        if priority == PRIORITY_EV_FREE and target_amps == 0 and charger_is_on:
            # Start delay countdown if not already waiting
            if not self._waiting_for_surplus_decrease:
                self._surplus_decrease_start_time = datetime.now()
                self._waiting_for_surplus_decrease = True
                self.logger.warning(
                    f"EV_FREE mode: Insufficient surplus ({surplus_amps:.2f}A < {SURPLUS_STOP_THRESHOLD}A) - "
                    f"Starting {surplus_drop_delay}s delay before stopping"
                )
                self.logger.separator()
                return

            # Check if delay elapsed
            elapsed = (datetime.now() - self._surplus_decrease_start_time).total_seconds()
            if elapsed < surplus_drop_delay:
                self.logger.info(
                    f"EV_FREE mode: Waiting for surplus drop delay ({elapsed:.1f}s / {surplus_drop_delay}s)"
                )
                self.logger.separator()
                return

            # Delay elapsed, stop charging
            self.logger.warning(
                f"EV_FREE mode: Delay elapsed - Stopping (insufficient surplus for {surplus_drop_delay}s)"
            )
            await self.charger_controller.stop_charger("EV_FREE: Insufficient surplus confirmed after delay")
            self._reset_state_tracking()
            self.logger.separator()
            return

        # Surplus-based adjustment
        if target_amps < current_amps:
            await self._handle_surplus_decrease(target_amps, current_amps, surplus_amps, surplus_drop_delay)
        elif target_amps > current_amps:
            await self._handle_surplus_increase(target_amps, current_amps)
        else:
            self.logger.success(f"Amperage optimal at {current_amps}A")
            self._reset_state_tracking()

        self.logger.separator()

    async def _handle_home_battery_usage(self, surplus_watts: float, priority: str | None) -> None:
        """Handle home battery support mode.

        Args:
            surplus_watts: Current surplus in watts
            priority: Current priority (EV, HOME, EV_FREE, or None if balancer disabled)
        """
        use_battery = get_bool(self.hass, self._use_home_battery_entity)
        if not use_battery:
            self._battery_support_active = False
            return

        # Check if priority allows battery support
        # ONLY allow when Priority = EV (EV below target, home can help)
        # NOT allowed when:
        # - Priority = HOME (home needs charging)
        # - Priority = EV_FREE (both targets met, only opportunistic charging with surplus)
        # - Balancer disabled (no targets defined, only surplus charging)
        if priority != PRIORITY_EV:
            if self._battery_support_active:
                reason = "both targets met" if priority == PRIORITY_EV_FREE else f"Priority={priority or 'Balancer disabled'}"
                self.logger.info(f"Battery support DEACTIVATING ({reason})")
                self._battery_support_active = False
            return

        # Check home battery SOC
        home_battery_soc = get_float(self.hass, self._soc_home, 0)
        battery_min_soc = get_float(self.hass, self._home_battery_min_soc_entity, 20)

        if home_battery_soc <= battery_min_soc:
            if self._battery_support_active:
                self.logger.warning(
                    f"Battery support DEACTIVATING (SOC {home_battery_soc}% <= min {battery_min_soc}%)"
                )
                self._battery_support_active = False
            return

        # Battery support can activate (even without surplus)
        battery_support_amps = get_float(self.hass, self._battery_support_amperage_entity, 16)

        if not self._battery_support_active:
            self.logger.info(
                f"Battery support ACTIVATING (SOC {home_battery_soc}% > min {battery_min_soc}%)"
            )
            self.logger.info(f"Using configured amperage: {battery_support_amps}A")
            self._battery_support_active = True

    def _calculate_target_amperage(self, surplus_watts: float, current_amperage: int = 0) -> int:
        """Calculate target amperage with hysteresis to prevent oscillation.

        Args:
            surplus_watts: Current surplus in watts
            current_amperage: Current charging amperage (0 if not charging)

        Returns:
            Target amperage in amps

        Hysteresis Logic:
        - Start threshold: 6.5A (SURPLUS_START_THRESHOLD)
        - Stop threshold: 5.5A (SURPLUS_STOP_THRESHOLD)
        - Dead band: 5.5A - 6.5A (maintain current level, no changes)
        """
        # ALWAYS calculate from surplus first
        surplus_amps = surplus_watts / VOLTAGE_EU
        is_charging = current_amperage > 0

        # CASE 1: Surplus sufficient to START or INCREASE (>= 6.5A)
        if surplus_amps >= SURPLUS_START_THRESHOLD:
            target = CHARGER_AMP_LEVELS[0]
            for level in CHARGER_AMP_LEVELS:
                if level <= surplus_amps:
                    target = level
                else:
                    break
            return target

        # CASE 2: Surplus in DEAD BAND (5.5A - 6.5A)
        # Maintain current level - don't increase, don't decrease
        if surplus_amps >= SURPLUS_STOP_THRESHOLD:
            if is_charging:
                # Continue at current level (prevent oscillation)
                self.logger.debug(
                    f"Surplus in hysteresis band ({surplus_amps:.2f}A, "
                    f"range {SURPLUS_STOP_THRESHOLD}-{SURPLUS_START_THRESHOLD}A) - "
                    f"Maintaining current {current_amperage}A"
                )
                return current_amperage
            else:
                # Not charging yet - wait for surplus to exceed START threshold
                self.logger.debug(
                    f"Surplus in hysteresis band ({surplus_amps:.2f}A) but not charging - "
                    f"Waiting for {SURPLUS_START_THRESHOLD}A to start"
                )
                # Check if battery support can activate
                if self._battery_support_active:
                    battery_amps = int(get_float(self.hass, self._battery_support_amperage_entity, 16))
                    self.logger.info(
                        f"Surplus insufficient ({surplus_amps:.1f}A), using battery support at {battery_amps}A"
                    )
                    return battery_amps
                return 0

        # CASE 3: Surplus below STOP threshold (< 5.5A)
        # Stop or fallback to battery support
        if self._battery_support_active:
            battery_amps = int(get_float(self.hass, self._battery_support_amperage_entity, 16))
            self.logger.info(
                f"Surplus insufficient ({surplus_amps:.1f}A < {SURPLUS_STOP_THRESHOLD}A), "
                f"using battery support at {battery_amps}A"
            )
            return battery_amps

        # No surplus, no battery support - stop charging
        return 0

    async def _handle_grid_import_protection(
        self,
        grid_import: float,
        grid_threshold: float,
        grid_import_delay: float,
        current_amps: int,
    ) -> None:
        """Handle grid import protection with delay."""
        current_time = time.time()

        if self._last_grid_import_high is None:
            self._last_grid_import_high = current_time
            self.logger.warning(
                f"Grid import ({grid_import}W) > threshold ({grid_threshold}W) - Starting {grid_import_delay}s delay"
            )
            return

        elapsed = current_time - self._last_grid_import_high
        if elapsed < grid_import_delay:
            self.logger.info(f"Grid import delay: {elapsed:.1f}s / {grid_import_delay}s")
            return

        self.logger.warning("Grid import delay ELAPSED - Reducing charging")
        self._last_grid_import_high = None

        # Gradual ramp down: one level at a time
        try:
            current_index = CHARGER_AMP_LEVELS.index(current_amps)
            if current_index > 0:
                next_amps = CHARGER_AMP_LEVELS[current_index - 1]
                self.logger.info(f"Stepping down ONE level: {current_amps}A -> {next_amps}A")
                await self.charger_controller.set_amperage(next_amps, "Grid import protection")
            else:
                self.logger.info("Already at minimum level - stopping charger")
                await self.charger_controller.stop_charger("Grid import protection - minimum level reached")
        except ValueError:
            # Handle 0A (charger off) or other non-standard levels
            if current_amps == 0:
                self.logger.warning("Charger is off (0A) - starting at minimum 6A")
                await self.charger_controller.set_amperage(6, "Grid import protection - charger was off, starting at 6A")
            else:
                self.logger.warning(f"Current amperage {current_amps}A not in standard levels")
                await self.charger_controller.set_amperage(6, "Grid import protection - fallback to 6A")

    async def _handle_surplus_decrease(
        self,
        target_amps: int,
        current_amps: int,
        surplus_amps: float,
        surplus_drop_delay: float,
    ) -> None:
        """Handle surplus decrease with delay."""
        current_time = time.time()

        if self._last_surplus_sufficient is None:
            self._last_surplus_sufficient = current_time
            self.logger.warning(
                f"Surplus dropped ({surplus_amps:.2f}A < {current_amps}A) - Starting {surplus_drop_delay}s delay"
            )
            return

        elapsed = current_time - self._last_surplus_sufficient
        if elapsed < surplus_drop_delay:
            self.logger.info(f"Surplus drop delay: {elapsed:.1f}s / {surplus_drop_delay}s")
            return

        self.logger.warning("Surplus drop delay ELAPSED - Starting gradual ramp-down")
        self._last_surplus_sufficient = None

        # Gradual ramp down: one level at a time
        try:
            current_index = CHARGER_AMP_LEVELS.index(current_amps)
            if current_index > 0:
                next_amps = CHARGER_AMP_LEVELS[current_index - 1]
                self.logger.info(f"Stepping down ONE level: {current_amps}A -> {next_amps}A")
                await self.charger_controller.set_amperage(next_amps, "Surplus decrease")
            else:
                self.logger.info("Already at minimum level - stopping charger")
                await self.charger_controller.stop_charger("Surplus decrease - minimum level reached")
        except ValueError:
            # Handle 0A (charger off) or other non-standard levels
            if current_amps == 0:
                self.logger.warning("Charger is off (0A) - starting at minimum 6A")
                await self.charger_controller.set_amperage(6, "Surplus decrease - charger was off, starting at 6A")
            else:
                self.logger.warning(f"Current amperage {current_amps}A not in standard levels")
                await self.charger_controller.set_amperage(6, "Surplus decrease - fallback to 6A")

    async def _handle_surplus_increase(self, target_amps: int, current_amps: int) -> None:
        """Handle surplus increase with stability requirement.

        Args:
            target_amps: Target amperage to set
            current_amps: Current amperage (0 if charger off)
        """
        from .const import SURPLUS_INCREASE_DELAY

        # Starting from 0A (charger off) requires 60s stability (cloud protection)
        if current_amps == 0:
            # Start stability tracking if not already started
            if self._surplus_stable_since is None:
                self._surplus_stable_since = datetime.now()
                self.logger.info(
                    f"Surplus sufficient ({target_amps}A available) - "
                    f"Waiting {SURPLUS_INCREASE_DELAY}s for stability before starting (cloud protection)"
                )
                return

            # Check stability duration
            stable_duration = (datetime.now() - self._surplus_stable_since).total_seconds()
            if stable_duration < SURPLUS_INCREASE_DELAY:
                self.logger.debug(
                    f"Waiting for stable surplus: {stable_duration:.1f}s / {SURPLUS_INCREASE_DELAY}s"
                )
                return

            # Stability confirmed, start charging
            self.logger.action(
                f"Surplus stable for {SURPLUS_INCREASE_DELAY}s - Starting at {target_amps}A"
            )
            self._reset_state_tracking()
            await self.charger_controller.start_charger(target_amps, "Stable surplus confirmed")
        else:
            # Already charging, require stability for INCREASES (cloud protection)
            if self._surplus_stable_since is None:
                self._surplus_stable_since = datetime.now()
                self.logger.info(
                    f"Surplus increase detected ({current_amps}A → {target_amps}A) - "
                    f"Waiting {SURPLUS_INCREASE_DELAY}s for stability (cloud protection)"
                )
                return

            # Check stability duration
            stable_duration = (datetime.now() - self._surplus_stable_since).total_seconds()
            if stable_duration < SURPLUS_INCREASE_DELAY:
                self.logger.debug(
                    f"Waiting for stable increase: {stable_duration:.1f}s / {SURPLUS_INCREASE_DELAY}s"
                )
                return

            # Stability confirmed, increase amperage
            self.logger.action(
                f"Surplus stable for {SURPLUS_INCREASE_DELAY}s - "
                f"Increasing from {current_amps}A to {target_amps}A"
            )
            self._reset_state_tracking()
            await self.charger_controller.set_amperage(target_amps, "Stable surplus increase")

    def _reset_state_tracking(self) -> None:
        """Reset state tracking flags."""
        self._last_surplus_sufficient = None
        self._last_grid_import_high = None
        self._surplus_stable_since = None
        self._waiting_for_surplus_decrease = False
        self._surplus_decrease_start_time = None

    async def _update_diagnostic_sensor(self, state: str, attributes: dict) -> None:
        """Update the solar surplus diagnostic sensor.

        Args:
            state: Sensor state
            attributes: Additional attributes
        """
        if not self._solar_surplus_diagnostic_sensor_entity:
            return

        self.hass.states.async_set(
            self._solar_surplus_diagnostic_sensor_entity,
            state,
            attributes,
        )

    async def async_remove(self) -> None:
        """Remove the automation."""
        if self._timer_unsub:
            self._timer_unsub()
            self._timer_unsub = None

        if self._soc_listener_unsub:
            self._soc_listener_unsub()
            self._soc_listener_unsub = None

        self.logger.info("Solar Surplus automation removed")

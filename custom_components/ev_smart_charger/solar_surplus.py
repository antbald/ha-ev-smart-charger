"""Solar Surplus Charging Profile automation."""
from __future__ import annotations

import asyncio
import time
from datetime import timedelta, datetime

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
    CONF_SOC_HOME,
    PRIORITY_EV,
    PRIORITY_HOME,
    PRIORITY_EV_FREE,
    SOLAR_SURPLUS_MIN_CHECK_INTERVAL,
    SOLAR_SURPLUS_MAX_CHECKS_PER_MINUTE,
    CHARGER_START_SEQUENCE_DELAY,
    CHARGER_STOP_SEQUENCE_DELAY,
    CHARGER_AMPERAGE_STABILIZATION_DELAY,
    HELPER_BATTERY_SUPPORT_AMPERAGE_SUFFIX,
)
from .utils.logging_helper import EVSCLogger
from .utils.entity_helper import find_by_suffix
from .utils.state_helper import get_state, get_float, get_bool, validate_sensor


class SolarSurplusAutomation:
    """Manages Solar Surplus charging profile with Priority Balancer integration."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry_id: str,
        config: dict,
        priority_balancer,
        night_smart_charge=None,
    ) -> None:
        """Initialize the Solar Surplus automation.

        Args:
            hass: Home Assistant instance
            entry_id: Config entry ID
            config: User configuration
            priority_balancer: PriorityBalancer instance for priority decisions
            night_smart_charge: Night Smart Charge instance (optional)
        """
        self.hass = hass
        self.entry_id = entry_id
        self.config = config
        self.priority_balancer = priority_balancer
        self._night_smart_charge = night_smart_charge

        # Initialize logger
        self.logger = EVSCLogger("SOLAR SURPLUS")

        # User-configured entities
        self._charger_switch = config.get(CONF_EV_CHARGER_SWITCH)
        self._charger_current = config.get(CONF_EV_CHARGER_CURRENT)
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

        # State tracking
        self._last_grid_import_high = None  # Timestamp when grid import exceeded threshold
        self._last_surplus_sufficient = None  # Timestamp when surplus was last sufficient
        self._battery_support_active = False  # Flag for home battery support mode

        # Rate limiting
        self._last_check_time = None
        self._check_count = 0
        self._check_count_reset_time = None

    def _find_entity_by_suffix(self, suffix: str) -> str | None:
        """Find an entity by its suffix, filtering by this integration's config_entry_id."""
        entity_registry = er.async_get(self.hass)

        for entity in entity_registry.entities.values():
            if entity.config_entry_id == self.entry_id:
                if entity.unique_id and entity.unique_id.endswith(suffix):
                    self.logger.debug(
                        f"Found helper entity: {entity.entity_id} (unique_id: {entity.unique_id})"
                    )
                    return entity.entity_id

        self.logger.warning(
            f"Helper entity with suffix '{suffix}' not found for config_entry {self.entry_id}"
        )
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
        self._battery_support_amperage_entity = self._find_entity_by_suffix(HELPER_BATTERY_SUPPORT_AMPERAGE_SUFFIX)
        self._solar_surplus_diagnostic_sensor_entity = self._find_entity_by_suffix("evsc_solar_surplus_diagnostic")

        if not all([
            self._forza_ricarica_entity,
            self._charging_profile_entity,
            self._check_interval_entity,
            self._grid_import_threshold_entity,
            self._grid_import_delay_entity,
            self._surplus_drop_delay_entity,
            self._use_home_battery_entity,
            self._home_battery_min_soc_entity,
            self._battery_support_amperage_entity,
        ]):
            self.logger.error("Required helper entities not found")
            return

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
    async def _async_periodic_check(self, now=None) -> None:
        """Periodic check for solar surplus charging."""
        # === Rate Limiting ===
        current_time = time.time()
        if self._last_check_time and (current_time - self._last_check_time) < SOLAR_SURPLUS_MIN_CHECK_INTERVAL:
            return

        self._last_check_time = current_time

        # Count checks per minute
        if self._check_count_reset_time is None or (current_time - self._check_count_reset_time) > 60:
            self._check_count = 0
            self._check_count_reset_time = current_time

        self._check_count += 1

        if self._check_count > SOLAR_SURPLUS_MAX_CHECKS_PER_MINUTE:
            self.logger.warning(f"Checking very frequently: {self._check_count} checks in last minute")

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

        # === 2. Check Night Smart Charge ===
        if self._night_smart_charge and self._night_smart_charge.is_night_charge_active():
            night_mode = self._night_smart_charge.get_active_mode()
            self.logger.skip(f"Night Smart Charge active (mode: {night_mode})")
            await self._update_diagnostic_sensor(
                "SKIPPED: Night Smart Charge Active",
                {"night_mode": night_mode, "last_check": datetime.now().isoformat()}
            )
            self.logger.separator()
            return

        # === 3. Check Charging Profile ===
        current_profile = get_state(self.hass, self._charging_profile_entity)
        if current_profile != "solar_surplus":
            self.logger.skip(f"Profile not 'solar_surplus' (current: {current_profile})")
            await self._update_diagnostic_sensor(
                "SKIPPED: Wrong Profile",
                {"profile": current_profile, "last_check": datetime.now().isoformat()}
            )
            self.logger.separator()
            return

        # === 4. Check Charger Status ===
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

        # === 5. Validate Sensors ===
        sensor_errors = []
        sensors_to_validate = [
            (self._fv_production, "Solar Production"),
            (self._home_consumption, "Home Consumption"),
            (self._grid_import, "Grid Import"),
        ]

        for entity_id, sensor_name in sensors_to_validate:
            is_valid, error_msg = validate_sensor(self.hass, entity_id, sensor_name)
            if not is_valid:
                sensor_errors.append(error_msg)

        if sensor_errors:
            self.logger.error("Sensor validation failed:")
            for error in sensor_errors:
                self.logger.error(f"  - {error}")
            await self._update_diagnostic_sensor(
                "ERROR: Invalid sensor values",
                {"errors": sensor_errors, "last_check": datetime.now().isoformat()}
            )
            self.logger.separator()
            return

        # === 6. Calculate Surplus ===
        fv_production = get_float(self.hass, self._fv_production)
        home_consumption = get_float(self.hass, self._home_consumption)
        grid_import = get_float(self.hass, self._grid_import)
        surplus_watts = fv_production - home_consumption
        surplus_amps = surplus_watts / VOLTAGE_EU

        self.logger.info(f"Solar Production: {fv_production}W")
        self.logger.info(f"Home Consumption: {home_consumption}W")
        self.logger.info(f"Surplus: {surplus_watts}W ({surplus_amps:.2f}A)")
        self.logger.info(f"Grid Import: {grid_import}W")

        # === 7. Priority Balancer Decision ===
        priority = None
        if self.priority_balancer.is_enabled():
            priority = await self.priority_balancer.calculate_priority()
            self.logger.info(f"Priority Balancer: {priority}")

            if priority == PRIORITY_HOME:
                self.logger.warning("Priority = HOME - Stopping EV charger")
                await self._stop_charger("Home battery needs charging")
                self.logger.separator()
                return
        else:
            self.logger.info("Priority Balancer disabled - using fallback mode")

        # === 8. Handle Home Battery Usage ===
        await self._handle_home_battery_usage(surplus_watts, priority)

        # === 9. Calculate Target Amperage ===
        target_amps = self._calculate_target_amperage(surplus_watts)
        self.logger.info(f"Target amperage: {target_amps}A")

        # === 10. Get Current Amperage ===
        charger_is_on = get_bool(self.hass, self._charger_switch)
        if charger_is_on:
            current_amps = get_float(self.hass, self._charger_current, 6)
        else:
            current_amps = 0

        self.logger.info(f"Current charging: {current_amps}A (charger {'ON' if charger_is_on else 'OFF'})")

        # === 11. Get Configuration Values ===
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

        # === 12. Apply Charging Logic ===

        # Start charger if OFF and we have target amperage
        if not charger_is_on and target_amps > 0:
            self.logger.action(f"Starting charger with {target_amps}A")
            await self._start_charger(target_amps)
            self.logger.separator()
            return

        # Grid Import Protection
        if grid_import > grid_threshold:
            await self._handle_grid_import_protection(grid_import, grid_threshold, grid_import_delay, current_amps)
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
        # Allow if: balancer disabled (priority=None), or priority is EV/EV_FREE
        if priority is not None and priority not in [PRIORITY_EV, PRIORITY_EV_FREE]:
            self.logger.info(f"Battery support skipped (Priority={priority})")
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

    def _calculate_target_amperage(self, surplus_watts: float) -> int:
        """Calculate target amperage based on surplus or battery support mode.

        Args:
            surplus_watts: Current surplus in watts

        Returns:
            Target amperage in amps
        """
        # If battery support is active, use configured amperage
        if self._battery_support_active:
            return int(get_float(self.hass, self._battery_support_amperage_entity, 16))

        # Otherwise, calculate from surplus
        surplus_amps = surplus_watts / VOLTAGE_EU

        if surplus_amps < CHARGER_AMP_LEVELS[0]:
            return 0

        target = CHARGER_AMP_LEVELS[0]
        for level in CHARGER_AMP_LEVELS:
            if level <= surplus_amps:
                target = level
            else:
                break

        return target

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

        self.logger.warning(f"Grid import delay ELAPSED - Reducing charging")
        self._last_grid_import_high = None
        await self._gradual_ramp_down(current_amps)

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
        await self._gradual_ramp_down(current_amps)

    async def _handle_surplus_increase(self, target_amps: int, current_amps: int) -> None:
        """Handle surplus increase (immediate adjustment)."""
        self.logger.action(f"Increasing amperage from {current_amps}A to {target_amps}A (immediate)")
        self._reset_state_tracking()
        await self._set_amperage(target_amps)

    async def _start_charger(self, target_amps: int) -> None:
        """Start charger with specified amperage.

        Args:
            target_amps: Target amperage to set
        """
        try:
            # Turn ON charger
            self.logger.action(f"Turning ON charger")
            await self.hass.services.async_call(
                "switch",
                "turn_on",
                {"entity_id": self._charger_switch},
                blocking=True,
            )

            # Wait for charger to be ready
            await asyncio.sleep(CHARGER_START_SEQUENCE_DELAY)

            # Set amperage
            self.logger.action(f"Setting amperage to {target_amps}A")
            await self.hass.services.async_call(
                "number",
                "set_value",
                {"entity_id": self._charger_current, "value": target_amps},
                blocking=True,
            )

            self.logger.success(f"Charger started at {target_amps}A")

        except Exception as e:
            self.logger.error(f"Failed to start charger: {e}")

    async def _stop_charger(self, reason: str) -> None:
        """Stop the charger.

        Args:
            reason: Reason for stopping
        """
        charger_state = get_state(self.hass, self._charger_switch)

        if charger_state == "on":
            await self.hass.services.async_call(
                "switch",
                "turn_off",
                {"entity_id": self._charger_switch},
                blocking=True,
            )
            self.logger.success(f"Charger stopped - {reason}")
        else:
            self.logger.info(f"Charger already OFF - {reason}")

    async def _set_amperage(self, amps: int) -> None:
        """Set charger amperage (instant increase).

        Args:
            amps: Target amperage (0 to stop)
        """
        if amps == 0:
            await self._stop_charger("Insufficient surplus")
            return

        self.logger.action(f"Setting amperage to {amps}A")
        await self.hass.services.async_call(
            "number",
            "set_value",
            {"entity_id": self._charger_current, "value": amps},
            blocking=True,
        )

        # Ensure charger is on
        if not get_bool(self.hass, self._charger_switch):
            self.logger.action("Starting charger")
            await self.hass.services.async_call(
                "switch",
                "turn_on",
                {"entity_id": self._charger_switch},
                blocking=True,
            )

    async def _gradual_ramp_down(self, current_amps: int) -> None:
        """Gradually ramp down charging one step at a time.

        Args:
            current_amps: Current amperage
        """
        self.logger.info(f"Starting gradual ramp-down from {current_amps}A")

        try:
            current_index = CHARGER_AMP_LEVELS.index(current_amps)
        except ValueError:
            self.logger.warning(f"Current amperage {current_amps}A not in standard levels")
            await self._adjust_amperage_down(6)
            return

        if current_index > 0:
            next_amps = CHARGER_AMP_LEVELS[current_index - 1]
            self.logger.info(f"Stepping down ONE level: {current_amps}A -> {next_amps}A")
            await self._adjust_amperage_down(next_amps)
        else:
            self.logger.info("Already at minimum level - stopping charger")
            await self._adjust_amperage_down(0)

    async def _adjust_amperage_down(self, target_amps: int) -> None:
        """Decrease amperage with proper sequence: stop -> wait 5s -> set -> wait 1s -> start.

        Args:
            target_amps: Target amperage
        """
        self.logger.info(f"Executing amperage change to {target_amps}A")

        # Stop charger
        self.logger.info("Step 1/5: Stopping charger")
        await self.hass.services.async_call(
            "switch",
            "turn_off",
            {"entity_id": self._charger_switch},
            blocking=True,
        )

        # Wait
        self.logger.info("Step 2/5: Waiting 5 seconds")
        await asyncio.sleep(CHARGER_STOP_SEQUENCE_DELAY)

        # Set new amperage or stop
        if target_amps > 0:
            self.logger.info(f"Step 3/5: Setting amperage to {target_amps}A")
            await self.hass.services.async_call(
                "number",
                "set_value",
                {"entity_id": self._charger_current, "value": target_amps},
                blocking=True,
            )

            self.logger.info("Step 4/5: Waiting 1 second")
            await asyncio.sleep(CHARGER_AMPERAGE_STABILIZATION_DELAY)

            self.logger.info("Step 5/5: Restarting charger")
            await self.hass.services.async_call(
                "switch",
                "turn_on",
                {"entity_id": self._charger_switch},
                blocking=True,
            )
            self.logger.success(f"Amperage changed to {target_amps}A")
        else:
            self.logger.info("Step 3/5: Target is 0A - keeping charger off")
            self.logger.success("Charger stopped")

    def _reset_state_tracking(self) -> None:
        """Reset state tracking flags."""
        self._last_surplus_sufficient = None
        self._last_grid_import_high = None

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
        self.logger.info("Solar Surplus automation removed")

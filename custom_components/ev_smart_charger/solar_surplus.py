"""Solar Surplus management for EV Smart Charger."""
from __future__ import annotations

import time
from datetime import timedelta, datetime

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.event import async_track_time_interval, async_track_state_change_event
from homeassistant.util import dt as dt_util

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
    PRIORITY_SOLAR_SURPLUS,
    SOLAR_SURPLUS_MIN_CHECK_INTERVAL,
    SOLAR_SURPLUS_MAX_CHECKS_PER_MINUTE,
    HELPER_BATTERY_SUPPORT_AMPERAGE_SUFFIX,
    SURPLUS_START_THRESHOLD,
    SURPLUS_STOP_THRESHOLD,
)
from .runtime import EVSCRuntimeData
from .utils.logging_helper import EVSCLogger
from .utils.state_helper import get_state, get_float, get_bool, validate_sensor
from .utils.astral_time_service import AstralTimeService

EV_SOC_STALE_WARNING_SECONDS = 300


class SolarSurplusAutomation:
    """Manages Solar Surplus charging profile with Priority Balancer integration."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry_id: str,
        config: dict,
        priority_balancer,
        charger_controller,
        runtime_data: EVSCRuntimeData | None = None,
        night_smart_charge=None,
        coordinator=None,
        boost_charge=None,
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
        self._runtime_data = runtime_data
        self._night_smart_charge = night_smart_charge
        self._coordinator = coordinator
        self._boost_charge = boost_charge

        # Initialize logger and astral time service
        self.logger = EVSCLogger("SOLAR SURPLUS")
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
        self._solar_surplus_diagnostic_sensor_obj = None

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

    @property
    def _automation_name(self) -> str:
        """Return the coordinator owner name for Solar Surplus."""
        return "Solar Surplus"

    def _has_control(self) -> bool:
        """Return True when Solar Surplus currently owns the session."""
        if self._coordinator is None:
            return True
        return self._coordinator.is_automation_active(self._automation_name)

    async def _emit_diagnostic(
        self,
        *,
        event: str,
        result: str,
        reason_code: str,
        reason_detail: str,
        raw_values: dict | None = None,
        severity: str = "info",
        external_cause: str | None = None,
    ) -> None:
        """Publish structured solar surplus diagnostics when available."""
        if self._runtime_data is None or self._runtime_data.diagnostic_manager is None:
            return

        await self._runtime_data.diagnostic_manager.async_emit_event(
            component="Solar Surplus",
            event=event,
            result=result,
            reason_code=reason_code,
            reason_detail=reason_detail,
            raw_values=raw_values,
            severity=severity,
            external_cause=external_cause,
        )

    async def _acquire_control(self, action: str, reason: str) -> bool:
        """Acquire coordinator ownership for a start/stop action."""
        if self._coordinator is None or self._has_control():
            return True

        allowed, denial_reason = await self._coordinator.request_charger_action(
            automation_name=self._automation_name,
            action=action,
            reason=reason,
            priority=PRIORITY_SOLAR_SURPLUS,
        )
        if not allowed:
            self.logger.info(f"Coordinator denied Solar Surplus action: {denial_reason}")
            active = self._coordinator.get_active_automation()
            snapshot = self._coordinator.get_debug_snapshot()
            if active:
                timestamp = active.get("timestamp")
                since = timestamp.strftime("%Y-%m-%d %H:%M:%S") if timestamp else "unknown"
                self.logger.info(
                    "Coordinator owner snapshot: "
                    f"name={active.get('name')}, "
                    f"priority={active.get('priority')}, "
                    f"action={active.get('action')}, "
                    f"reason={active.get('reason')}, "
                    f"since={since}"
                )
            self._handle_control_loss(denial_reason)
            await self._emit_diagnostic(
                event="coordinator_denied",
                result="denied",
                reason_code="coordinator_denied",
                reason_detail=denial_reason,
                raw_values={
                    "action": action,
                    "reason": reason,
                    "active_owner": active,
                    "coordinator_snapshot": snapshot,
                },
                severity="warning",
                external_cause="stale_owner_detected" if "health=stale" in denial_reason else None,
            )
            return False
        return True

    async def _ensure_control(self, reason: str) -> bool:
        """Ensure Solar Surplus owns the session before mutating the charger."""
        return await self._acquire_control("turn_on", reason)

    def _release_control(self, reason: str) -> None:
        """Release coordinator ownership when Solar Surplus is done."""
        if self._coordinator is not None:
            self._coordinator.release_control(self._automation_name, reason)

    def _handle_control_loss(self, reason: str) -> None:
        """Reset transient session state after Solar Surplus loses ownership."""
        self._battery_support_active = False
        self._reset_state_tracking()
        self.logger.info(f"Solar Surplus standing down: {reason}")
        if self._runtime_data is not None and self._runtime_data.diagnostic_manager is not None:
            self.hass.async_create_task(
                self._emit_diagnostic(
                    event="standing_down",
                    result="stopped",
                    reason_code="control_released",
                    reason_detail=reason,
                    severity="warning" if "denied" in reason.lower() else "info",
                )
            )

    def _find_entity_by_suffix(self, suffix: str) -> str | None:
        """Resolve an integration-owned helper entity from runtime data."""
        if self._runtime_data is None:
            return None
        return self._runtime_data.get_entity_id(suffix)

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
        if self._runtime_data is not None:
            self._solar_surplus_diagnostic_sensor_obj = self._runtime_data.get_entity(
                "evsc_solar_surplus_diagnostic"
            )

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
    async def _async_periodic_check(self, now=None, ignore_rate_limit: bool = False) -> None:
        """Periodic check for solar surplus charging."""
        # === Rate Limiting ===
        current_time = time.time()
        if (
            not ignore_rate_limit
            and self._last_check_time
            and (current_time - self._last_check_time) < SOLAR_SURPLUS_MIN_CHECK_INTERVAL
        ):
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
            await self._emit_diagnostic(
                event="periodic_check",
                result="skipped",
                reason_code="manual_override",
                reason_detail="Forza Ricarica is ON",
                external_cause="manual_override",
            )
            await self._update_diagnostic_sensor(
                "SKIPPED: Forza Ricarica ON",
                {"reason": "Override switch enabled", "last_check": datetime.now().isoformat()}
            )
            self.logger.separator()
            return

        # === 2. Check Boost Charge (manual override) ===
        if self._boost_charge and self._boost_charge.is_active():
            if self._has_control():
                self._release_control("Boost Charge active")
                self._handle_control_loss("Boost Charge active")
            self.logger.skip("Boost Charge active")
            await self._emit_diagnostic(
                event="periodic_check",
                result="skipped",
                reason_code="manual_override",
                reason_detail="Boost Charge active",
                external_cause="manual_override",
            )
            await self._update_diagnostic_sensor(
                "SKIPPED: Boost Charge Active",
                {"reason": "Boost override enabled", "last_check": datetime.now().isoformat()}
            )
            self.logger.separator()
            return

        # === 3. Check Nighttime (Solar Surplus only works during daytime) ===
        from .const import NIGHT_CHARGE_COOLDOWN_SECONDS
        now = dt_util.now()
        current_profile = get_state(self.hass, self._charging_profile_entity)

        if self._astral_service.is_nighttime(now):
            await self._handle_nighttime_transition(now, current_profile)
            self.logger.separator()
            return

        # === 4. Check Night Smart Charge ===
        if self._night_smart_charge and self._night_smart_charge.is_active():
            if self._has_control():
                self._release_control("Night Smart Charge active")
                self._handle_control_loss("Night Smart Charge active")
            night_mode = self._night_smart_charge.get_active_mode()
            self.logger.skip(f"Night Smart Charge active (mode: {night_mode})")
            await self._emit_diagnostic(
                event="periodic_check",
                result="skipped",
                reason_code="night_window",
                reason_detail=f"Night Smart Charge active (mode: {night_mode})",
                external_cause="night_window",
            )
            await self._update_diagnostic_sensor(
                "SKIPPED: Night Smart Charge Active",
                {"night_mode": night_mode, "last_check": datetime.now().isoformat()}
            )
            self.logger.separator()
            return

        # === 5. Check Night Smart Charge Cooldown ===
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

        # === 6. Check Charging Profile ===
        if current_profile != "solar_surplus":
            if self._has_control():
                self._release_control("Charging profile changed away from solar_surplus")
                self._handle_control_loss("Charging profile changed")
            self.logger.skip(f"Profile not 'solar_surplus' (current: {current_profile})")
            await self._emit_diagnostic(
                event="periodic_check",
                result="skipped",
                reason_code="profile_mismatch",
                reason_detail=f"Profile not 'solar_surplus' (current: {current_profile})",
                external_cause="profile_mismatch",
            )
            await self._update_diagnostic_sensor(
                "SKIPPED: Wrong Profile",
                {"profile": current_profile, "last_check": datetime.now().isoformat()}
            )
            self.logger.separator()
            return

        # === 7. Check Charger Status ===
        charger_status = get_state(self.hass, self._charger_status)
        if not charger_status:
            self.logger.warning("Charger status unavailable")
            self.logger.separator()
            return

        if charger_status == CHARGER_STATUS_FREE:
            if self._has_control():
                self._release_control("Charger disconnected")
                self._handle_control_loss("Charger disconnected")
            self.logger.skip("Charger is free (not connected)")
            await self._emit_diagnostic(
                event="periodic_check",
                result="skipped",
                reason_code="charger_disconnected",
                reason_detail="Charger is free (not connected)",
                external_cause="charger_disconnected",
            )
            self.logger.separator()
            return

        self.logger.info(f"Charger status: '{charger_status}' - proceeding")
        charger_is_on = await self.charger_controller.is_charging()

        # === 7.1 EV Target Hard Cap (always enforced, even before energy checks) ===
        if await self._enforce_ev_target_hard_cap(
            context="periodic_check",
            charger_is_on=charger_is_on,
        ):
            self._battery_support_active = False
            self.logger.separator()
            return

        # === 8. Priority Balancer Decision (target enforcement must run even if energy sensors fail) ===
        priority = None
        if self.priority_balancer.is_enabled():
            priority = await self.priority_balancer.calculate_priority()
            self.logger.info(f"Priority Balancer: {priority}")

            if priority == PRIORITY_HOME:
                self.logger.warning("Priority = HOME - Stopping EV charger")
                if await self._acquire_control(
                    "turn_off",
                    "Home battery needs charging (Priority = HOME)",
                ):
                    await self.charger_controller.stop_charger(
                        "Home battery needs charging (Priority = HOME)"
                    )
                    self._release_control("Priority = HOME")
                    self._handle_control_loss("Priority = HOME")
                self.logger.separator()
                return

            # v1.3.24: Stop opportunistic charging when both targets met
            if priority == PRIORITY_EV_FREE:
                if charger_is_on:
                    self.logger.info(
                        f"{self.logger.SUCCESS} Both targets met (Priority = EV_FREE) - "
                        "Stopping opportunistic charging"
                    )
                    if await self._acquire_control(
                        "turn_off",
                        "Both EV and Home targets reached (Priority = EV_FREE)",
                    ):
                        await self.charger_controller.stop_charger(
                            "Both EV and Home targets reached (Priority = EV_FREE)"
                        )
                        self._release_control("Priority = EV_FREE")
                        self._handle_control_loss("Priority = EV_FREE")
                    self.logger.separator()
                return
        else:
            self.logger.info("Priority Balancer disabled - using fallback mode")

        # === 9. Validate Sensors (with throttled logging to prevent spam) ===
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

        # === 10. Calculate Surplus ===
        fv_production = get_float(self.hass, self._fv_production)
        home_consumption = get_float(self.hass, self._home_consumption)
        grid_import = get_float(self.hass, self._grid_import)
        surplus_watts = fv_production - home_consumption
        surplus_amps = surplus_watts / VOLTAGE_EU

        self.logger.info(f"Solar Production: {fv_production}W")
        self.logger.info(f"Home Consumption: {home_consumption}W")
        self.logger.info(f"Surplus: {surplus_watts}W ({surplus_amps:.2f}A)")
        self.logger.info(f"Grid Import: {grid_import}W")

        # === 10. Handle Home Battery Usage ===
        await self._handle_home_battery_usage(surplus_watts, priority)

        # === 11. Get Current Amperage (needed for hysteresis) ===
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

        # Grid Import Protection
        if grid_import > grid_threshold:
            await self._handle_grid_import_protection(grid_import, grid_threshold, grid_import_delay, current_amps)
            self.logger.separator()
            return
        else:
            # Reset timer when import goes back below threshold
            self._last_grid_import_high = None

        # Start charger if OFF and we have target amperage
        if not charger_is_on and target_amps > 0:
            self.logger.action(f"Starting charger with {target_amps}A")
            if await self._acquire_control("turn_on", "Solar surplus available"):
                await self.charger_controller.start_charger(
                    target_amps,
                    "Solar surplus available",
                )
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
            if await self._acquire_control(
                "turn_off",
                "EV_FREE: Insufficient surplus confirmed after delay",
            ):
                await self.charger_controller.stop_charger(
                    "EV_FREE: Insufficient surplus confirmed after delay"
                )
                self._release_control("EV_FREE stop after delay")
                self._handle_control_loss("EV_FREE stop after delay")
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

    def _get_ev_soc_staleness(self) -> dict:
        """Return EV SOC freshness metadata based on cached sensor update age."""
        soc_entity = getattr(self.priority_balancer, "_soc_car", None)
        if not soc_entity:
            return {
                "entity": None,
                "age_seconds": None,
                "is_stale": False,
            }

        soc_state = self.hass.states.get(soc_entity)
        if not soc_state or not soc_state.last_updated:
            return {
                "entity": soc_entity,
                "age_seconds": None,
                "is_stale": False,
            }

        age_seconds = max(0.0, (dt_util.now() - soc_state.last_updated).total_seconds())
        return {
            "entity": soc_entity,
            "age_seconds": age_seconds,
            "is_stale": age_seconds >= EV_SOC_STALE_WARNING_SECONDS,
        }

    def _build_ev_soc_stale_attributes(self, stale_info: dict) -> dict:
        """Build diagnostic attributes for SOC stale visibility."""
        return {
            "ev_soc_entity": stale_info.get("entity"),
            "ev_soc_age_seconds": stale_info.get("age_seconds"),
            "ev_soc_is_stale": stale_info.get("is_stale", False),
            "ev_soc_stale_policy": "continue_charge",
        }

    def _log_ev_soc_stale_continue_policy(self, stale_info: dict, context: str) -> None:
        """Log stale SOC warning while explicitly continuing by policy."""
        if not stale_info.get("is_stale"):
            return

        age_seconds = stale_info.get("age_seconds")
        age_label = f"{age_seconds:.0f}s" if age_seconds is not None else "unknown"
        self.logger.warning(
            f"SOC stale (continue) [{context}] - age={age_label}, "
            f"entity={stale_info.get('entity')} - continuing by policy"
        )

    async def _enforce_ev_target_hard_cap(self, context: str, charger_is_on: bool | None = None) -> bool:
        """
        Enforce EV target as a hard cap.

        Returns True when hard-cap logic handled the cycle (target reached path).
        """
        if not self.priority_balancer:
            return False

        stale_info = self._get_ev_soc_staleness()
        self._log_ev_soc_stale_continue_policy(stale_info, context)

        try:
            ev_target_reached = await self.priority_balancer.is_ev_target_reached()
            ev_soc = await self.priority_balancer.get_ev_current_soc()
            ev_target = self.priority_balancer.get_ev_target_for_today()
        except Exception as ex:
            self.logger.error(f"Target hard cap check failed [{context}]: {ex}")
            return False

        if not ev_target_reached:
            return False

        if charger_is_on is None:
            charger_is_on = await self.charger_controller.is_charging()

        if charger_is_on:
            reason = (
                f"Target hard cap enforced ({context}): EV target reached "
                f"({ev_soc}% >= {ev_target}%)"
            )
            self.logger.warning(f"Target hard cap enforced [{context}] - stopping charger")
            if await self._acquire_control("turn_off", reason):
                await self.charger_controller.stop_charger(reason)
                self._release_control("Target hard cap enforced")
                self._handle_control_loss("Target hard cap enforced")
                await self._update_diagnostic_sensor(
                    "STOPPED: Target hard cap enforced",
                    {
                        "reason": reason,
                        "context": context,
                        "ev_soc": ev_soc,
                        "ev_target": ev_target,
                        "last_check": datetime.now().isoformat(),
                        **self._build_ev_soc_stale_attributes(stale_info),
                    },
                )
            return True

        self.logger.info(
            f"Target hard cap enforced [{context}] - charger already OFF ({ev_soc}% >= {ev_target}%)"
        )
        await self._update_diagnostic_sensor(
            "SKIPPED: Target already reached (charger OFF)",
            {
                "reason": "Target hard cap enforced with charger OFF",
                "context": context,
                "ev_soc": ev_soc,
                "ev_target": ev_target,
                "last_check": datetime.now().isoformat(),
                **self._build_ev_soc_stale_attributes(stale_info),
            },
        )
        return True

    async def _handle_nighttime_transition(self, now: datetime, current_profile: str | None) -> None:
        """Handle sunset transition when Solar Surplus is no longer allowed to run."""
        charger_is_on = await self.charger_controller.is_charging()

        if not charger_is_on:
            if self._has_control():
                self._release_control("Nighttime with charger off")
                self._handle_control_loss("Nighttime with charger off")
            self.logger.skip("Nighttime - Solar Surplus only operates during daytime (sunrise to sunset)")
            await self._update_diagnostic_sensor(
                "SKIPPED: Nighttime",
                {"reason": "Solar production unavailable at night", "last_check": datetime.now().isoformat()},
            )
            return

        if current_profile != "solar_surplus":
            self.logger.skip(
                f"Nighttime with charger ON but profile is '{current_profile}' - no sunset transition needed"
            )
            await self._update_diagnostic_sensor(
                "SKIPPED: Nighttime (profile mismatch)",
                {
                    "reason": "Charger active but profile is not solar_surplus",
                    "profile": current_profile,
                    "last_check": datetime.now().isoformat(),
                },
            )
            return

        self.logger.warning(
            f"Sunset transition detected at {now.strftime('%H:%M:%S')} with charger ON in Solar Surplus"
        )

        if await self._enforce_ev_target_hard_cap(
            context="sunset_transition",
            charger_is_on=charger_is_on,
        ):
            self._battery_support_active = False
            return

        handover_accepted = False
        if self._night_smart_charge and hasattr(
            self._night_smart_charge, "async_try_handover_from_solar_surplus"
        ):
            try:
                handover_accepted = bool(
                    await self._night_smart_charge.async_try_handover_from_solar_surplus(
                        "sunset_transition"
                    )
                )
            except Exception as ex:
                self.logger.error(f"Sunset transition handover failed: {ex}")
        else:
            self.logger.warning("Sunset transition - Night Smart Charge handover API unavailable")

        if handover_accepted:
            self._release_control("Night Smart Charge accepted sunset handover")
            self._handle_control_loss("Night Smart Charge accepted sunset handover")
            self.logger.success("Sunset transition - Handover accepted by Night Smart Charge")
            await self._update_diagnostic_sensor(
                "TRANSITION: Sunset handover accepted",
                {
                    "reason": "Sunset transition",
                    "handover": "accepted",
                    "last_check": datetime.now().isoformat(),
                },
            )
            return

        stop_reason = (
            "Sunset transition safe stop: Solar Surplus cannot continue at night and handover was rejected"
        )
        self.logger.warning("Sunset transition - Handover rejected, applying safe stop")
        if await self._acquire_control("turn_off", stop_reason):
            await self.charger_controller.stop_charger(stop_reason)
            self._release_control("Sunset transition safe stop")
            self._handle_control_loss("Sunset transition safe stop")
            await self._update_diagnostic_sensor(
                "STOPPED: Sunset transition safe stop",
                {
                    "reason": stop_reason,
                    "handover": "rejected_or_failed",
                    "last_check": datetime.now().isoformat(),
                },
            )

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
                if await self._ensure_control("Grid import protection"):
                    await self.charger_controller.set_amperage(next_amps, "Grid import protection")
            else:
                self.logger.info("Already at minimum level - stopping charger")
                if await self._acquire_control(
                    "turn_off",
                    "Grid import protection - minimum level reached",
                ):
                    await self.charger_controller.stop_charger(
                        "Grid import protection - minimum level reached"
                    )
                    self._release_control("Grid import protection stop")
                    self._handle_control_loss("Grid import protection stop")
        except ValueError:
            # Handle 0A (charger off) or other non-standard levels
            if current_amps == 0:
                self.logger.info("Charger is already off (0A) - keeping charger stopped")
            else:
                self.logger.warning(f"Current amperage {current_amps}A not in standard levels")
                if await self._acquire_control(
                    "turn_off",
                    "Grid import protection - invalid amperage level",
                ):
                    await self.charger_controller.stop_charger(
                        "Grid import protection - invalid amperage level"
                    )
                    self._release_control("Grid import invalid amperage")
                    self._handle_control_loss("Grid import invalid amperage")

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
                if await self._ensure_control("Surplus decrease"):
                    await self.charger_controller.set_amperage(next_amps, "Surplus decrease")
            else:
                self.logger.info("Already at minimum level - stopping charger")
                if await self._acquire_control(
                    "turn_off",
                    "Surplus decrease - minimum level reached",
                ):
                    await self.charger_controller.stop_charger(
                        "Surplus decrease - minimum level reached"
                    )
                    self._release_control("Surplus decrease stop")
                    self._handle_control_loss("Surplus decrease stop")
        except ValueError:
            # Handle 0A (charger off) or other non-standard levels
            if current_amps == 0:
                self.logger.warning("Charger is off (0A) - starting at minimum 6A")
                if await self._ensure_control("Surplus decrease - start at 6A"):
                    await self.charger_controller.set_amperage(
                        6,
                        "Surplus decrease - charger was off, starting at 6A",
                    )
            else:
                self.logger.warning(f"Current amperage {current_amps}A not in standard levels")
                if await self._ensure_control("Surplus decrease - fallback to 6A"):
                    await self.charger_controller.set_amperage(
                        6,
                        "Surplus decrease - fallback to 6A",
                    )

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
            if await self._acquire_control("turn_on", "Stable surplus confirmed"):
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
            if await self._ensure_control("Stable surplus increase"):
                await self.charger_controller.set_amperage(target_amps, "Stable surplus increase")

    def _reset_state_tracking(self) -> None:
        """Reset state tracking flags."""
        self._last_surplus_sufficient = None
        self._last_grid_import_high = None
        self._surplus_stable_since = None
        self._waiting_for_surplus_decrease = False
        self._surplus_decrease_start_time = None

    def _build_standard_diagnostic_attributes(
        self,
        state: str,
        attributes: dict,
    ) -> dict:
        """Align solar diagnostic attributes with the unified diagnostic schema."""
        normalized = dict(attributes)
        reason_detail = (
            normalized.get("last_reason_detail")
            or normalized.get("reason")
            or normalized.get("night_mode")
            or normalized.get("profile")
            or normalized.get("errors")
            or state
        )
        reason_code = normalized.get("last_reason_code") or (
            "sensor_unavailable" if normalized.get("errors") else "status_update"
        )

        normalized.setdefault("last_decision_component", "Solar Surplus")
        normalized.setdefault("last_decision_result", state)
        normalized.setdefault("last_reason_code", reason_code)
        normalized.setdefault("last_reason_detail", reason_detail)
        normalized.setdefault("last_external_cause", normalized.get("external_cause"))
        if self._coordinator is not None:
            normalized.setdefault("active_owner", self._coordinator.get_active_automation_name())
        return normalized

    async def _update_diagnostic_sensor(self, state: str, attributes: dict) -> None:
        """Update the solar surplus diagnostic sensor.

        Args:
            state: Sensor state
            attributes: Additional attributes
        """
        if not self._solar_surplus_diagnostic_sensor_entity:
            return

        payload = self._build_standard_diagnostic_attributes(state, attributes)

        if self._solar_surplus_diagnostic_sensor_obj and hasattr(
            self._solar_surplus_diagnostic_sensor_obj, "async_publish"
        ):
            await self._solar_surplus_diagnostic_sensor_obj.async_publish(state, payload)
            return
        self.logger.warning("Solar Surplus diagnostic entity object not registered in runtime data")

    async def async_request_immediate_check(self, reason: str = "") -> None:
        """Force an immediate periodic check, bypassing the rate limit."""
        if reason:
            self.logger.info(f"Immediate Solar Surplus check requested: {reason}")
        await self._async_periodic_check(ignore_rate_limit=True)

    async def async_remove(self) -> None:
        """Remove the automation."""
        if self._timer_unsub:
            self._timer_unsub()
            self._timer_unsub = None

        if self._soc_listener_unsub:
            self._soc_listener_unsub()
            self._soc_listener_unsub = None

        self.logger.info("Solar Surplus automation removed")

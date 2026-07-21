"""Solar Surplus management for EV Smart Charger."""
from __future__ import annotations

import time
from datetime import timedelta, datetime

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.event import (
    async_call_later,
    async_track_time_interval,
    async_track_state_change_event,
)
from homeassistant.util import dt as dt_util

from .const import (
    CONF_EV_CHARGER_STATUS,
    CONF_FV_PRODUCTION,
    CONF_HOME_CONSUMPTION,
    CONF_GRID_IMPORT,
    CONF_GRID_IMPORT_L2,
    CONF_GRID_IMPORT_L3,
    CONF_SOC_HOME,
    PRIORITY_EV,
    PRIORITY_HOME,
    PRIORITY_EV_FREE,
    PRIORITY_SOLAR_SURPLUS,
    SOLAR_SURPLUS_MIN_CHECK_INTERVAL,
    SOLAR_SURPLUS_MAX_CHECKS_PER_MINUTE,
    SENSOR_UNAVAILABLE_ERROR_TICKS,
    HELPER_BATTERY_SUPPORT_AMPERAGE_SUFFIX,
    HELPER_BATTERY_SUPPORT_SUNSET_BUFFER_SUFFIX,
    HELPER_MAX_BATTERY_DISCHARGE_FOR_EV_SUFFIX,
    HELPER_SOLAR_MAX_AMPERAGE_SUFFIX,
    HELPER_NIGHTTIME_SUNSET_OFFSET_SUFFIX,
    HELPER_NIGHTTIME_SUNRISE_OFFSET_SUFFIX,
    HELPER_SPIKE_RESPONSE_DELAY_SUFFIX,
    DEFAULT_SPIKE_RESPONSE_DELAY,
    SPIKE_PRODUCTION_STABILITY_TOLERANCE_W,
    SPIKE_PRODUCTION_STABILITY_TOLERANCE_RATIO,
    SPIKE_MIN_ACTION_INTERVAL,
    SPIKE_STEP_DOWN_MARGIN_W,
    DEFAULT_BATTERY_SUPPORT_SUNSET_BUFFER_MIN,
    DEFAULT_SOLAR_MAX_AMPERAGE,
    SURPLUS_START_THRESHOLD,
    SURPLUS_STOP_THRESHOLD,
    SURPLUS_DEADBAND_START_DELAY,
    SURPLUS_INCREASE_DELAY,
    NIGHT_CHARGE_COOLDOWN_SECONDS,
    NOTIF_ID_BALANCER_DISABLED,
    has_home_battery,
)
from .localization import translate_runtime
from .power_model import ChargingModel, is_disconnected_status
from .runtime import EVSCRuntimeData
from .utils.logging_helper import EVSCLogger
from .utils.notification_service import NotificationService
from .utils.state_helper import get_state, get_float, get_bool, validate_sensor
from .utils.amperage_helper import AmperageCalculator
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
        hybrid_mode=None,
    ) -> None:
        """Initialize the Solar Surplus automation.

        Args:
            hass: Home Assistant instance
            entry_id: Config entry ID
            config: User configuration
            priority_balancer: PriorityBalancer instance for priority decisions
            charger_controller: ChargerController instance for charger operations
            night_smart_charge: Night Smart Charge instance (optional)
            hybrid_mode: HybridInverterMode instance (optional, v1.8.0 — issue #20)
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
        self._hybrid_mode = hybrid_mode

        # Initialize logger and astral time service
        self.logger = EVSCLogger("SOLAR SURPLUS")
        self._astral_service = AstralTimeService(hass)

        # User-configured entities
        self._charger_status = config.get(CONF_EV_CHARGER_STATUS)
        self._fv_production = config.get(CONF_FV_PRODUCTION)
        self._home_consumption = config.get(CONF_HOME_CONSUMPTION)
        self._grid_import = config.get(CONF_GRID_IMPORT)
        self._soc_home = config.get(CONF_SOC_HOME)
        # v1.7.0: PV-only mode (no home battery configured)
        self._has_home_battery = has_home_battery(config)

        # v2.0.0: phase mode + charger model. Single source = runtime power_model
        # (built once in __init__.py); fall back to building from config so direct
        # construction in tests still works. Single-phase + Tuya = unchanged values.
        _pm = runtime_data.power_model if runtime_data is not None else None
        self._power_model = (
            _pm if isinstance(_pm, ChargingModel) else ChargingModel.from_config(config)
        )
        self._effective_voltage = self._power_model.effective_voltage
        self._amp_levels = self._power_model.amp_levels

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
        self._battery_support_sunset_buffer_entity = None
        self._solar_max_amperage_entity = None
        # v2.6.0 (issue #42): nighttime window offsets (minutes). 0 = astronomical.
        self._nighttime_sunset_offset_entity = None
        self._nighttime_sunrise_offset_entity = None
        # v2.1.0 (issue #29): battery-only deadband buffer limit (W). 0 = off.
        self._max_battery_discharge_entity = None
        self._solar_surplus_diagnostic_sensor_entity = None
        self._solar_surplus_diagnostic_sensor_obj = None

        # Timer for periodic checks
        self._timer_unsub = None

        # SOC listener for real-time battery monitoring
        self._soc_listener_unsub = None

        # v2.8.0 — consumption-spike fast response (event-driven grid listener)
        self._spike_response_delay_entity = None
        self._grid_listener_unsub = None       # grid-import state-change listener
        self._spike_high_since = None          # monotonic ts of first over-threshold event
        self._spike_check_unsub = None         # async_call_later cancel handle
        self._spike_baseline_production = None # last per-tick production reading (W)
        self._last_spike_action = None         # monotonic ts of last fast step-down

        # State tracking
        self._last_grid_import_high = None  # Timestamp when grid import exceeded threshold
        self._last_surplus_sufficient = None  # Timestamp when surplus was last sufficient
        self._battery_support_active = False  # Flag for home battery support mode
        self._surplus_stable_since = None  # Timestamp when surplus became stable (for hysteresis)
        self._deadband_start_time = None  # Timestamp when dead band first detected (opportunistic start)
        self._waiting_for_surplus_decrease = False  # Flag for surplus drop delay in EV_FREE mode
        self._surplus_decrease_start_time = None  # Timestamp when surplus drop started

        # Rate limiting
        self._last_check_time = None
        self._check_count = 0
        self._check_count_reset_time = None

        # Sensor error tracking (prevent log spam)
        self._sensor_error_state = {}  # {sensor_entity_id: error_message}
        # issue #47/#48: consecutive ticks with at least one invalid sensor.
        # Used to debounce the diagnostic ERROR label (display-only).
        self._sensor_error_consecutive = 0

        # v2.5.0 (issue #35): surface the silent "Priority Balancer disabled"
        # degradation when home SOC targets are configured. Persistent notification
        # (fixed id, auto-dismissed on re-enable) + WARNING throttled once per day.
        self._notification_service = NotificationService(hass)
        self._balancer_disabled_warned_date = None  # date-guard for the daily WARNING
        self._balancer_dismiss_done = False  # one-shot stale-notification cleanup per setup

    @property
    def _automation_name(self) -> str:
        """Return the coordinator owner name for Solar Surplus."""
        return "Solar Surplus"

    def _has_control(self) -> bool:
        """Return True when Solar Surplus currently owns the session."""
        if self._coordinator is None:
            return True
        return self._coordinator.is_automation_active(self._automation_name)

    async def _maybe_warn_balancer_disabled(self) -> None:
        """Surface the silent Priority-Balancer-disabled degradation (issue #35).

        When the balancer is off AND the user has configured home-battery SOC
        targets, the home-battery protection is silently bypassed. Emit a WARNING
        (throttled once per day) plus a persistent notification with a fixed id
        (so it updates in place instead of stacking). No-op in PV-only mode or
        when no home target is configured (the "acceptable" case in the issue).
        """
        if not self._has_home_battery:
            return
        if not self.priority_balancer.has_active_home_soc_target():
            return

        today = dt_util.now().date()
        if today == self._balancer_disabled_warned_date:
            return  # already warned today

        self.logger.warning(
            "Priority Balancer is DISABLED but home SOC targets are configured - "
            "home-battery protection is INACTIVE. Enable "
            "evsc_priority_balancer_enabled to restore it."
        )
        try:
            await self._notification_service.send_warning(
                translate_runtime(self.hass, "priority_balancer.disabled.title"),
                translate_runtime(self.hass, "priority_balancer.disabled.message"),
                notification_id=NOTIF_ID_BALANCER_DISABLED,
            )
        except Exception as err:  # notification must never break the control loop
            self.logger.debug(f"Balancer-disabled notification failed: {err}")
        self._balancer_disabled_warned_date = today

    async def _clear_balancer_disabled_warning(self) -> None:
        """Dismiss the balancer-disabled persistent notification (issue #35).

        Called when the balancer is enabled. Runs at least once per setup
        (``_balancer_dismiss_done``) so a notification created before an HA
        restart is cleaned up even though the in-memory date-guard reset to None.
        Dismissing a non-existent notification is a harmless no-op.
        """
        if self._balancer_disabled_warned_date is None and self._balancer_dismiss_done:
            return
        self._balancer_dismiss_done = True
        self._balancer_disabled_warned_date = None
        try:
            await self._notification_service.dismiss(NOTIF_ID_BALANCER_DISABLED)
        except Exception as err:
            self.logger.debug(f"Balancer-disabled dismiss failed: {err}")

    def _charging_power_snapshot(self) -> dict:
        """v2.2.0 charging-state observability for the diagnostic sensor.

        Surfaces the MEASURED charging power (so a reversed-sign sensor shows a
        flat 0 W — the user's cue to apply a ``| abs`` template fix) and which
        signal the charging verdict rests on. Synchronous and defensive: never
        raises into the diagnostic path.
        """
        measured = None
        try:
            power_model = (
                self._runtime_data.power_model if self._runtime_data else None
            )
            if power_model is not None:
                measured = power_model.read_charging_power(self.hass)
        except Exception:  # pragma: no cover - diagnostics must never break flow
            measured = None

        if measured is not None:
            return {
                "charging_power_w": round(measured, 1),
                "charging_power_source": "measured",
                "is_charging_basis": "measured",
            }
        return {
            "charging_power_w": None,
            "charging_power_source": "none",
            "is_charging_basis": "status" if self._charger_status else "command",
        }

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

        # v2.2.0: always attach the charging-power snapshot so the measured
        # reading / source / basis are visible on the diagnostic sensor each tick.
        merged_raw = {**self._charging_power_snapshot(), **(raw_values or {})}

        await self._runtime_data.diagnostic_manager.async_emit_event(
            component="Solar Surplus",
            event=event,
            result=result,
            reason_code=reason_code,
            reason_detail=reason_detail,
            raw_values=merged_raw,
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
        # v1.7.0 — force Hybrid Inverter Mode out of any active state
        if self._hybrid_mode is not None:
            self.hass.async_create_task(
                self._hybrid_mode.async_force_exit(f"Control lost: {reason}")
            )
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
        # v2.6.0 (issue #42): nighttime window offsets
        self._nighttime_sunset_offset_entity = self._find_entity_by_suffix(
            HELPER_NIGHTTIME_SUNSET_OFFSET_SUFFIX
        )
        self._nighttime_sunrise_offset_entity = self._find_entity_by_suffix(
            HELPER_NIGHTTIME_SUNRISE_OFFSET_SUFFIX
        )
        # v2.8.0: consumption-spike fast response debounce
        self._spike_response_delay_entity = self._find_entity_by_suffix(
            HELPER_SPIKE_RESPONSE_DELAY_SUFFIX
        )
        # v1.7.0: skip battery helper discovery in PV-only mode
        if self._has_home_battery:
            self._use_home_battery_entity = self._find_entity_by_suffix("evsc_use_home_battery")
            self._home_battery_min_soc_entity = self._find_entity_by_suffix("evsc_home_battery_min_soc")
            self._battery_support_amperage_entity = self._find_entity_by_suffix(HELPER_BATTERY_SUPPORT_AMPERAGE_SUFFIX)
            self._battery_support_sunset_buffer_entity = self._find_entity_by_suffix(HELPER_BATTERY_SUPPORT_SUNSET_BUFFER_SUFFIX)
            # v2.1.0 (issue #29): battery-only deadband buffer limit helper
            self._max_battery_discharge_entity = self._find_entity_by_suffix(HELPER_MAX_BATTERY_DISCHARGE_FOR_EV_SUFFIX)
        self._solar_max_amperage_entity = self._find_entity_by_suffix(HELPER_SOLAR_MAX_AMPERAGE_SUFFIX)
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
        # v1.7.0: only flag battery helpers as missing when home battery is configured
        if self._has_home_battery:
            if not self._use_home_battery_entity:
                missing_entities.append("evsc_use_home_battery")
            if not self._home_battery_min_soc_entity:
                missing_entities.append("evsc_home_battery_min_soc")
            if not self._battery_support_amperage_entity:
                missing_entities.append(HELPER_BATTERY_SUPPORT_AMPERAGE_SUFFIX)
            if not self._battery_support_sunset_buffer_entity:
                missing_entities.append(HELPER_BATTERY_SUPPORT_SUNSET_BUFFER_SUFFIX)
            if not self._max_battery_discharge_entity:
                missing_entities.append(HELPER_MAX_BATTERY_DISCHARGE_FOR_EV_SUFFIX)

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
        elif self._has_home_battery:
            self.logger.warning("Home battery SOC sensor not configured - real-time monitoring disabled")
        else:
            # v1.7.0: PV-only mode — no home battery configured, nothing to monitor
            self.logger.info("PV-only mode: real-time home battery monitoring disabled (no battery configured)")

        # v2.8.0: event-driven grid-import listener for consumption-spike fast
        # response. Registered on every mapped grid sensor (L1 + optional L2/L3
        # in three-phase) so a demand spike is seen within seconds instead of
        # at the next periodic tick. The handler itself is a no-op unless a
        # Solar-Surplus-owned charging session is active AND the spike delay
        # helper is > 0 (0 = legacy behaviour, byte-for-byte).
        grid_sensors = [
            sensor
            for sensor in (
                self.config.get(CONF_GRID_IMPORT),
                self.config.get(CONF_GRID_IMPORT_L2),
                self.config.get(CONF_GRID_IMPORT_L3),
            )
            if sensor
        ]
        if grid_sensors:
            self._grid_listener_unsub = async_track_state_change_event(
                self.hass,
                grid_sensors,
                self._async_grid_import_changed,
            )
            self.logger.info(
                f"Consumption-spike listener registered on {', '.join(grid_sensors)}"
            )

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

        # Run one check immediately so the diagnostic sensor reflects the
        # current day/night state right after setup instead of carrying a
        # stale value (e.g. last night's "SKIPPED: Nighttime") until the
        # first timer tick fires `interval_minutes` later (issue #34).
        try:
            await self._async_periodic_check(ignore_rate_limit=True)
        except Exception as err:  # noqa: BLE001 - never block setup on first check
            self.logger.warning(f"Initial periodic check failed: {err}")

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
            current_time = time.monotonic()
            if not self._last_check_time or (current_time - self._last_check_time) >= SOLAR_SURPLUS_MIN_CHECK_INTERVAL:
                self.hass.async_create_task(self._async_periodic_check())
            else:
                self.logger.debug(
                    f"{self.logger.BATTERY} Skipping immediate check due to rate limit "
                    f"({current_time - self._last_check_time:.1f}s since last check)"
                )

    # ─────────────────────────────────────────────────────────────
    # v2.8.0 — Consumption-spike fast response
    #
    # Problem: the periodic grid-import protection is tuned for clouds
    # (60s tick + 30s debounce + ONE level per cycle ≈ 2 min per level),
    # so a household demand spike (washing machine, induction hob, ...)
    # while the EV charges on surplus leaks 0.5–1 kWh/day into the grid.
    #
    # Fast path: an event-driven listener on the grid-import sensor(s)
    # detects the spike within seconds; when PV production is STABLE vs
    # the last per-tick baseline (i.e. the deficit comes from consumption,
    # not a cloud) and the import persists for `evsc_spike_response_delay`
    # seconds, the charger steps down in ONE operation to the amp level
    # that zeroes the measured import. Ramp-up stays on the legacy slow
    # path (60s stability window, one level per tick) — asymmetric
    # fast-down / slow-up. Production drops always take the legacy path.
    # ─────────────────────────────────────────────────────────────

    def _get_spike_response_delay(self) -> float:
        """Return the configured spike debounce in seconds (0 = disabled)."""
        return get_float(
            self.hass, self._spike_response_delay_entity, DEFAULT_SPIKE_RESPONSE_DELAY
        )

    def _reset_spike_tracking(self) -> None:
        """Clear the spike debounce timer and any scheduled verification."""
        self._spike_high_since = None
        if self._spike_check_unsub:
            self._spike_check_unsub()
            self._spike_check_unsub = None

    def _is_production_stable(self, production: float) -> bool:
        """Return True when PV production has not dropped vs the tick baseline.

        Stable production while grid import rises means the deficit comes from
        home consumption — the case where an aggressive step-down is safe. A
        material production drop (cloud) returns False and the legacy
        conservative protection keeps handling the event.
        """
        baseline = self._spike_baseline_production
        if baseline is None:
            return False  # no baseline yet → stay on the legacy path
        tolerance = max(
            SPIKE_PRODUCTION_STABILITY_TOLERANCE_W,
            SPIKE_PRODUCTION_STABILITY_TOLERANCE_RATIO * baseline,
        )
        return production >= baseline - tolerance

    async def _spike_conditions_met(self) -> tuple[bool, float, float]:
        """Re-verify every fast-path precondition against live state.

        Returns (ok, grid_import, grid_threshold). Called both on listener
        events and on the delayed verification, so a condition that lapsed
        mid-debounce (session lost, import recovered, cloud arrived) always
        stands the fast path down.
        """
        grid_import = self._power_model.read_grid_import(self.hass)
        grid_threshold = get_float(self.hass, self._grid_import_threshold_entity)

        if self._get_spike_response_delay() <= 0:
            return False, grid_import, grid_threshold
        # Only act on a session Solar Surplus currently owns; every other
        # owner (Night Charge, Boost, Forza Ricarica, manual) is out of scope.
        if not self._has_control():
            return False, grid_import, grid_threshold
        # Hybrid Mode PROBING/RIDING_EDGE deliberately rides the import edge —
        # never undercut its probe with a fast step-down.
        if self._hybrid_mode is not None and self._hybrid_mode.is_active():
            return False, grid_import, grid_threshold
        if not await self.charger_controller.is_charging():
            return False, grid_import, grid_threshold
        if grid_import <= grid_threshold:
            return False, grid_import, grid_threshold
        production = self._power_model.read_production(self.hass)
        if not self._is_production_stable(production):
            return False, grid_import, grid_threshold
        return True, grid_import, grid_threshold

    @callback
    async def _async_grid_import_changed(self, event) -> None:
        """Event-driven grid-import listener (consumption-spike fast path)."""
        new_state = event.data.get("new_state")
        if not new_state or new_state.state in ("unknown", "unavailable"):
            return

        ok, grid_import, grid_threshold = await self._spike_conditions_met()
        if not ok:
            if self._spike_high_since is not None:
                self.logger.debug(
                    "Spike tracking reset (conditions no longer met, "
                    f"import={grid_import:.0f}W threshold={grid_threshold:.0f}W)"
                )
            self._reset_spike_tracking()
            return

        if self._spike_high_since is not None:
            return  # debounce already armed; the scheduled check will decide

        delay = self._get_spike_response_delay()
        self._spike_high_since = time.monotonic()
        self.logger.info(
            f"{self.logger.ALERT} Consumption spike detected: grid import "
            f"{grid_import:.0f}W > {grid_threshold:.0f}W with stable PV - "
            f"fast step-down in {delay:.0f}s unless it recovers"
        )
        self._spike_check_unsub = async_call_later(
            self.hass, delay, self._async_spike_delayed_check
        )

    async def _async_spike_delayed_check(self, _now=None) -> None:
        """Fire `spike_response_delay` seconds after the first spike event."""
        self._spike_check_unsub = None
        if self._spike_high_since is None:
            return
        await self._execute_spike_step_down()

    async def _execute_spike_step_down(self) -> None:
        """One-shot step-down to the amp level that zeroes the measured import."""
        now = time.monotonic()
        if (
            self._last_spike_action is not None
            and (now - self._last_spike_action) < SPIKE_MIN_ACTION_INTERVAL
        ):
            self._reset_spike_tracking()
            return

        ok, grid_import, grid_threshold = await self._spike_conditions_met()
        self._reset_spike_tracking()
        if not ok:
            self.logger.debug("Spike step-down aborted (conditions recovered)")
            return

        current_amps = await self.charger_controller.get_current_amperage() or 0
        if current_amps <= 0:
            return

        # Level that zeroes the import: new draw = current draw - import (plus
        # a small margin so the landing level doesn't leave a residual trickle).
        import_amps = (grid_import + SPIKE_STEP_DOWN_MARGIN_W) / self._effective_voltage
        max_allowed = current_amps - import_amps
        candidates = [level for level in self._amp_levels if level <= max_allowed]
        target = candidates[-1] if candidates else 0
        if target >= current_amps:
            # Import smaller than one level step — fall back to a single step.
            target = AmperageCalculator.get_next_level_down(current_amps, self._amp_levels)

        self._last_spike_action = now
        # Require a fresh stability window before any ramp back up, and clear
        # the periodic protection timer so it can't double-fire on a stale ts.
        self._surplus_stable_since = None
        self._last_grid_import_high = None

        await self._update_diagnostic_sensor(
            "SPIKE_STEP_DOWN",
            {
                "last_check": dt_util.now().isoformat(),
                "decision": "consumption_spike_step_down",
                "reason": "Grid import from home-consumption spike (stable PV)",
                "grid_import_w": grid_import,
                "grid_threshold_w": grid_threshold,
                "current_charging_a": current_amps,
                "target_charging_a": target,
            },
        )

        if target > 0:
            self.logger.warning(
                f"{self.logger.ACTION} Consumption spike fast response: "
                f"{current_amps}A -> {target}A in one step "
                f"(import {grid_import:.0f}W, margin {SPIKE_STEP_DOWN_MARGIN_W}W)"
            )
            if await self._ensure_control("Consumption spike fast response"):
                await self.charger_controller.set_amperage(
                    target, "Consumption spike fast response"
                )
        else:
            self.logger.warning(
                f"{self.logger.ACTION} Consumption spike fast response: import "
                f"{grid_import:.0f}W exceeds minimum-level draw - stopping charger"
            )
            if await self._ensure_control("Consumption spike fast response"):
                await self.charger_controller.stop_charger(
                    "Consumption spike fast response - minimum level still imports"
                )

    @callback
    async def _async_periodic_check(self, now=None, ignore_rate_limit: bool = False) -> None:
        """Periodic check for solar surplus charging."""
        # === Rate Limiting ===
        current_time = time.monotonic()
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

        # issue #50C: one separator per tick (fence pattern). Early-return
        # branches below no longer emit their own separator, so a single tick
        # produces exactly one ═══ at the top regardless of which branch fires.
        self.logger.separator()

        # issue #40: this header (and most per-tick readout below) is DEBUG now.
        # On idle no-op ticks nothing actionable happens, so INFO is reserved for
        # ticks that take an action; the diagnostic sensor still updates every tick.
        # issue #50A: the counter is reset every 60s and there is one tick per
        # 60s window, so it is always #1 — only log it when it is genuinely > 1
        # (i.e. something triggered extra checks within the window).
        if self._check_count > 1:
            self.logger.debug(f"Periodic check #{self._check_count}")

        # === 1. Check Forza Ricarica (Kill Switch) ===
        if get_bool(self.hass, self._forza_ricarica_entity):
            if self._hybrid_mode is not None:
                await self._hybrid_mode.async_force_exit("Forza Ricarica ON")
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
                {"reason": "Override switch enabled", "last_check": dt_util.now().isoformat()}
            )
            return

        # === 2. Check Boost Charge (manual override) ===
        if self._boost_charge and self._boost_charge.is_active():
            if self._hybrid_mode is not None:
                await self._hybrid_mode.async_force_exit("Boost Charge active")
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
                {"reason": "Boost override enabled", "last_check": dt_util.now().isoformat()}
            )
            return

        # === 3. Check Nighttime (Solar Surplus only works during daytime) ===
        now = dt_util.now()
        current_profile = get_state(self.hass, self._charging_profile_entity)

        # issue #42: optional user offsets extend the nighttime window (start
        # before sunset / end after sunrise). 0 = astronomical (legacy).
        sunset_offset = int(get_float(self.hass, self._nighttime_sunset_offset_entity, 0))
        sunrise_offset = int(get_float(self.hass, self._nighttime_sunrise_offset_entity, 0))
        if self._astral_service.is_nighttime(now, sunset_offset, sunrise_offset):
            await self._handle_nighttime_transition(now, current_profile)
            return

        # === 4. Check Night Smart Charge ===
        if self._night_smart_charge and self._night_smart_charge.is_active():
            if self._hybrid_mode is not None:
                await self._hybrid_mode.async_force_exit("Night Smart Charge active")
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
                {"night_mode": night_mode, "last_check": dt_util.now().isoformat()}
            )
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
                        "last_check": dt_util.now().isoformat()
                    }
                )
                return

        # === 6. Check Charging Profile ===
        if current_profile != "solar_surplus":
            if self._hybrid_mode is not None:
                await self._hybrid_mode.async_force_exit("Charging profile changed")
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
                {"profile": current_profile, "last_check": dt_util.now().isoformat()}
            )
            return

        # === 7. Check Charger Status ===
        # v2.2.0: CONF_EV_CHARGER_STATUS is optional. When mapped it remains the
        # plug-state source (FREE = unplugged → skip). When NOT mapped we cannot
        # read plug state from status, so we proceed — the charger switch and
        # measured power drive the loop. A mapped-but-unavailable sensor still
        # warns + returns (transient sensor outage, unchanged behaviour).
        if self._charger_status:
            charger_status = get_state(self.hass, self._charger_status)
            if not charger_status:
                self.logger.warning("Charger status unavailable")
                return

            # v2.9.2: brand-vocabulary aware (companion to v2.9.1). The exact
            # CHARGER_STATUS_FREE comparison let OCPP 'available' (= no EV
            # connected) pass as "connected": on 2026-07-21 Solar Surplus ran a
            # 125-tick battery-support start loop (05:38-07:46) against an
            # empty plug. is_disconnected_status() covers 'charger_free' plus
            # the unambiguous disconnected synonyms; unknown strings still
            # default to "connected" (safe failure mode, unchanged).
            if is_disconnected_status(charger_status):
                if self._hybrid_mode is not None:
                    await self._hybrid_mode.async_force_exit("Charger disconnected")
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
                return

            self.logger.info(f"Charger status: '{charger_status}' - proceeding")
        else:
            self.logger.info("No charger status sensor - proceeding (status optional)")
        charger_is_on = await self.charger_controller.is_charging()

        # === 8. Priority Balancer Decision ===
        priority = None
        if self.priority_balancer.is_enabled():
            # v2.5.0 (issue #35): balancer back ON → clear any stale
            # "disabled" warning surfaced while it was off.
            await self._clear_balancer_disabled_warning()
            priority = await self.priority_balancer.calculate_priority()
            self.logger.debug(f"Priority Balancer: {priority}")

            if priority == PRIORITY_HOME:
                # issue #44: only act when there is something to do. Calling
                # stop_charger() every tick on an already-off charger floods the
                # log, churns coordinator ownership and dispatches a no-op
                # switch.turn_off. Guard on the real charger state.
                if await self.charger_controller.is_charging():
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
                elif self._has_control():
                    # Charger already off but we still hold the coordinator —
                    # release it so we don't leave a phantom owner.
                    self._release_control("Priority = HOME (charger already off)")
                    self._handle_control_loss("Priority = HOME (charger already off)")
                    self.logger.debug(
                        "Priority = HOME, charger already off — released stale control"
                    )
                else:
                    self.logger.debug(
                        "Priority = HOME, charger already off — skipping stop"
                    )
                return

            if priority == PRIORITY_EV_FREE:
                self.logger.debug(
                    f"{self.logger.SUCCESS} Both targets met (Priority = EV_FREE) - "
                    "allowing opportunistic solar charging"
                )
        else:
            self.logger.info("Priority Balancer disabled - using fallback mode")
            # v2.5.0 (issue #35): the fallback ignores home SOC targets, so the
            # configured home-battery protection is silently bypassed. Surface it.
            await self._maybe_warn_balancer_disabled()

        # === 9. Validate Sensors (with throttled logging to prevent spam) ===
        # v2.0.0: validate EVERY mapped phase sensor (L1/L2/L3 in three-phase)
        # BEFORE summing — a single unavailable phase would otherwise be read as
        # 0 W by get_float and silently halve production/consumption.
        sensor_errors = []
        failed_entities = []  # issue #48: which sensors failed (for the state string)
        sensors_to_validate = self._power_model.labelled_power_entities()

        # Check each sensor and track error state changes
        new_errors = False
        for entity_id, sensor_name in sensors_to_validate:
            is_valid, error_msg = validate_sensor(self.hass, entity_id, sensor_name)

            if not is_valid:
                sensor_errors.append(error_msg)
                failed_entities.append(entity_id)
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
            # issue #47/#48: debounce the hard ERROR label. Noisy integrations
            # (e.g. GivEnergy/givtcp) briefly drop sensors to unavailable; a
            # single flap should not surface a scary "ERROR" or a stale-looking
            # value. Show a soft WAITING state for the first few consecutive
            # ticks, escalate to ERROR only if it persists. Display-only — the
            # tick still skips (returns) while sensors are unavailable, so no
            # charging decision is ever made on invalid data.
            self._sensor_error_consecutive += 1

            # Only log full error details if there are NEW errors
            if new_errors:
                self.logger.error("Sensor validation failed:")
                for error in sensor_errors:
                    self.logger.error(f"  - {error}")
            else:
                # Existing errors - just update diagnostic sensor quietly
                self.logger.debug(f"Sensor errors still present ({len(sensor_errors)} sensors unavailable)")

            if self._sensor_error_consecutive < SENSOR_UNAVAILABLE_ERROR_TICKS:
                state_str = "WAITING: sensor momentarily unavailable"
            elif len(failed_entities) == 1:
                # issue #48: name the failing sensor at a glance (full list in
                # the `errors` attribute). HA state is capped at 255 chars.
                state_str = f"ERROR: Invalid sensor ({failed_entities[0]})"
            else:
                state_str = (
                    f"ERROR: Invalid sensor ({failed_entities[0]} +"
                    f"{len(failed_entities) - 1} more)"
                )
            await self._update_diagnostic_sensor(
                state_str[:200],
                {
                    "errors": sensor_errors,
                    "consecutive_error_ticks": self._sensor_error_consecutive,
                    "last_check": dt_util.now().isoformat(),
                },
            )
            return

        # All sensors valid — reset the debounce counter (issue #47/#48).
        self._sensor_error_consecutive = 0

        # === 10. Calculate Surplus ===
        # v2.0.0: power readers sum across phases (single-phase = single sensor),
        # and the watt→amp conversion uses the effective voltage (230 V single,
        # 690 V three-phase) so surplus_amps stays a valid per-phase amperage.
        fv_production = self._power_model.read_production(self.hass)
        home_consumption = self._power_model.read_consumption(self.hass)
        grid_import = self._power_model.read_grid_import(self.hass)
        surplus_watts = fv_production - home_consumption
        surplus_amps = surplus_watts / self._effective_voltage
        # v2.8.0: refresh the production baseline used by the consumption-spike
        # classifier. Sampled once per tick: during a genuine production drop
        # (cloud) the live reading falls below this baseline and the fast path
        # stands down in favour of the legacy conservative protection.
        self._spike_baseline_production = fv_production
        # issue #40: the full sensor readout is logged once, conditionally, after
        # target_amps is finalized (see "issue #40 readout" block below).

        # === 10b. Hybrid Inverter Mode (v1.8.0 — issue #20) ===
        # In hybrid zero-export systems, when the home battery is full the
        # inverter curtails PV to match home_consumption → surplus reads ≈ 0
        # even when kilowatts of PV capacity are available. Hybrid Mode probes
        # for this hidden headroom by starting the charger at 6A and observing
        # grid_import. If the inverter ramps PV in response, we ride the edge
        # of the import limit; otherwise we back off.
        if self._hybrid_mode is not None:
            current_amps_for_hybrid = (
                await self.charger_controller.get_current_amperage() or 0
            ) if charger_is_on else 0
            if await self._hybrid_mode.is_relevant(
                surplus_amps=surplus_amps,
                surplus_watts=surplus_watts,
                grid_import=grid_import,
                charger_is_on=charger_is_on,
                priority=priority,
                now=now,
            ):
                handled = await self._hybrid_mode.tick(
                    surplus_amps=surplus_amps,
                    surplus_watts=surplus_watts,
                    grid_import=grid_import,
                    charger_is_on=charger_is_on,
                    current_amps=current_amps_for_hybrid,
                    priority=priority,
                    now=now,
                )
                if handled:
                    self.logger.info("Hybrid Inverter Mode handled this tick")
                    return

        # === 11. Handle Home Battery Usage ===
        await self._handle_home_battery_usage(surplus_watts, priority)

        # === 11. Get Current Amperage (needed for hysteresis) ===
        if charger_is_on:
            current_amps = await self.charger_controller.get_current_amperage() or 6
        else:
            current_amps = 0

        # === 12. Calculate Target Amperage (with hysteresis) ===
        target_amps = self._calculate_target_amperage(surplus_watts, current_amps)

        # === 12a. Battery-discharge deadband buffer (v2.1.0 — issue #29) ===
        # On hybrid systems the inverter can curtail PV so surplus briefly dips
        # below the 6A floor while the home battery silently covers the gap. If
        # the user opted in (limit > 0) and mapped a battery-power sensor, let up
        # to `limit` watts of battery discharge keep an ALREADY-charging session
        # alive instead of stop-start cycling. Gated on charger_is_on so it never
        # *starts* charging off the battery (start still needs the 6.5A threshold),
        # which also leaves the opportunistic dead-band-start path (12b, requires
        # not charger_is_on) completely untouched. No-op when the helper/sensor is
        # absent (limit 0 / discharge None) — byte-for-byte v2.0.0.
        if target_amps == 0 and charger_is_on:
            limit = get_float(self.hass, self._max_battery_discharge_entity, default=0)
            # Re-apply the battery-support safety guards (SOC floor / sunset /
            # EV_FREE): the bridge only runs when battery support is *inactive*,
            # so without this it would drain the home battery exactly where the
            # guards said not to.
            if limit > 0 and self._is_battery_bridge_allowed(priority):
                discharge = self._power_model.read_battery_discharge(self.hass)
                if discharge is not None:
                    buffer = min(discharge, limit)
                    # 6A floor in watts: ≈1380W single-phase, ≈4140W three-phase.
                    min_charging_watts = self._amp_levels[0] * self._effective_voltage
                    if surplus_watts + buffer >= min_charging_watts:
                        target_amps = current_amps
                        self.logger.info(
                            f"Deadband buffer: surplus {surplus_watts:.0f}W + battery "
                            f"{buffer:.0f}W (limit {limit:.0f}W) >= floor "
                            f"{min_charging_watts:.0f}W → keep charging at {current_amps}A"
                        )

        # Apply user-configured maximum amperage cap (issue #11: wallboxes with <32A limit).
        # Always cap to the highest valid amp level that doesn't exceed max_amps
        # to avoid sending non-standard amperages to the wallbox.
        if target_amps > 0:
            max_amps = int(get_float(self.hass, self._solar_max_amperage_entity, DEFAULT_SOLAR_MAX_AMPERAGE))
            if target_amps > max_amps:
                valid_below_max = [l for l in self._amp_levels if l <= max_amps]
                capped = valid_below_max[-1] if valid_below_max else self._amp_levels[0]
                self.logger.info(f"Target capped: {target_amps}A → {capped}A (solar max amperage: {max_amps}A)")
                target_amps = capped

        # === 12b. Opportunistic Dead Band Start ===
        # When charger is OFF and surplus is in dead band (5.5-6.5A) for a prolonged
        # period, override target to 6A. This prevents the charger from sitting idle
        # for 30+ minutes when there's ~1200-1400W of usable surplus.
        if not charger_is_on and target_amps == 0 and surplus_amps >= SURPLUS_STOP_THRESHOLD:
            if self._deadband_start_time is None:
                self._deadband_start_time = dt_util.now()
                self.logger.info(
                    f"Surplus in dead band ({surplus_amps:.2f}A, "
                    f"range {SURPLUS_STOP_THRESHOLD}-{SURPLUS_START_THRESHOLD}A) - "
                    f"Starting {SURPLUS_DEADBAND_START_DELAY}s timer for opportunistic start"
                )
            else:
                elapsed = (dt_util.now() - self._deadband_start_time).total_seconds()
                if elapsed >= SURPLUS_DEADBAND_START_DELAY:
                    target_amps = self._amp_levels[0]  # 6A minimum
                    self.logger.info(
                        f"Dead band surplus persistent for {elapsed:.0f}s >= "
                        f"{SURPLUS_DEADBAND_START_DELAY}s - "
                        f"Opportunistic start at {target_amps}A"
                    )
                    self._deadband_start_time = None
                else:
                    self.logger.info(
                        f"Dead band timer: {elapsed:.0f}s / "
                        f"{SURPLUS_DEADBAND_START_DELAY}s "
                        f"(surplus {surplus_amps:.2f}A)"
                    )
        else:
            # Reset dead band timer when conditions no longer match:
            # - Charger is ON (already charging)
            # - Surplus above start threshold (normal start path)
            # - Surplus below stop threshold (insufficient)
            if self._deadband_start_time is not None:
                self.logger.debug("Dead band timer reset (conditions changed)")
                self._deadband_start_time = None

        # === issue #40 readout ===
        # target_amps is now final. Emit the full sensor/decision block at INFO
        # only when an action will be taken (target != current). On stable no-op
        # ticks emit a single DEBUG line. The diagnostic sensor (section below)
        # still updates every tick regardless.
        if target_amps != current_amps:
            self.logger.info(f"Solar Production: {fv_production}W")
            self.logger.info(f"Home Consumption: {home_consumption}W")
            self.logger.info(f"Surplus: {surplus_watts}W ({surplus_amps:.2f}A)")
            self.logger.info(f"Grid Import: {grid_import}W")
            self.logger.info(
                f"Current charging: {current_amps}A "
                f"(charger {'ON' if charger_is_on else 'OFF'})"
            )
            self.logger.info(f"Target amperage: {target_amps}A")
        else:
            self.logger.debug(
                f"No action: surplus={surplus_watts:.0f}W ({surplus_amps:.2f}A), "
                f"current={current_amps}A, target={target_amps}A, "
                f"grid={grid_import}W, priority={priority if priority else 'DISABLED'}"
            )

        # === 13. Get Configuration Values ===
        grid_threshold = get_float(self.hass, self._grid_import_threshold_entity)
        grid_import_delay = get_float(self.hass, self._grid_import_delay_entity)
        surplus_drop_delay = get_float(self.hass, self._surplus_drop_delay_entity)

        # Update diagnostic sensor
        await self._update_diagnostic_sensor(
            f"CHECKING: {surplus_watts}W surplus ({surplus_amps:.1f}A)",
            {
                "last_check": dt_util.now().isoformat(),
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
                "use_home_battery_enabled": get_bool(self.hass, self._use_home_battery_entity),
                "grid_threshold_w": grid_threshold,
                "grid_import_delay_s": grid_import_delay,
                "grid_import_timer_started_ts": self._last_grid_import_high,
                "grid_import_elapsed_s": None,
                "grid_import_remaining_s": None,
            }
        )

        # === 14. Apply Charging Logic ===

        # Grid Import Protection
        if grid_import > grid_threshold:
            debug_context = self._get_grid_import_debug_context(
                grid_import=grid_import,
                grid_threshold=grid_threshold,
                grid_import_delay=grid_import_delay,
                current_amps=current_amps,
                target_amps=target_amps,
            )
            self.logger.warning(
                "Grid import protection gate: import=%sW threshold=%sW delay=%ss "
                "elapsed=%ss remaining=%ss current=%sA target=%sA battery_support=%s use_home_battery=%s",
                round(debug_context["grid_import_w"], 1),
                round(debug_context["grid_threshold_w"], 1),
                round(debug_context["grid_import_delay_s"], 1),
                debug_context["grid_import_elapsed_s"],
                debug_context["grid_import_remaining_s"],
                debug_context["current_charging_a"],
                debug_context["target_charging_a"],
                debug_context["battery_support_active"],
                debug_context["use_home_battery_enabled"],
            )
            await self._update_diagnostic_sensor(
                "GRID_IMPORT_PROTECTION",
                {
                    "last_check": dt_util.now().isoformat(),
                    "priority": priority if priority else "DISABLED",
                    "decision": "grid_import_protection_active",
                    **debug_context,
                },
            )
            await self._handle_grid_import_protection(grid_import, grid_threshold, grid_import_delay, current_amps)
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
            return

        # EV_FREE Mode: Apply delay before stopping (same as PRIORITY_EV)
        if priority == PRIORITY_EV_FREE and target_amps == 0 and charger_is_on:
            # Start delay countdown if not already waiting
            if not self._waiting_for_surplus_decrease:
                self._surplus_decrease_start_time = dt_util.now()
                self._waiting_for_surplus_decrease = True
                self.logger.warning(
                    f"EV_FREE mode: Insufficient surplus ({surplus_amps:.2f}A < {SURPLUS_STOP_THRESHOLD}A) - "
                    f"Starting {surplus_drop_delay}s delay before stopping"
                )
                return

            # Check if delay elapsed
            elapsed = (dt_util.now() - self._surplus_decrease_start_time).total_seconds()
            if elapsed < surplus_drop_delay:
                self.logger.info(
                    f"EV_FREE mode: Waiting for surplus drop delay ({elapsed:.1f}s / {surplus_drop_delay}s)"
                )
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
            return

        # Surplus-based adjustment
        if target_amps < current_amps:
            await self._handle_surplus_decrease(target_amps, current_amps, surplus_amps, surplus_drop_delay)
        elif target_amps > current_amps:
            await self._handle_surplus_increase(target_amps, current_amps)
        else:
            # issue #40: charger already off and nothing to confirm → DEBUG, no
            # separator (keeps idle no-op ticks to a single DEBUG line). When
            # actually charging at the optimal level, keep the INFO confirmation.
            if current_amps == 0:
                self.logger.debug("Amperage optimal at 0A (charger off — nothing to confirm)")
            else:
                self.logger.success(f"Amperage optimal at {current_amps}A")
            self._reset_state_tracking()

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
                        "last_check": dt_util.now().isoformat(),
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
                "last_check": dt_util.now().isoformat(),
                **self._build_ev_soc_stale_attributes(stale_info),
            },
        )
        return True

    def _build_nighttime_debug_attributes(self, now: datetime) -> dict:
        """Expose the astral times behind a nighttime decision.

        Lets users self-diagnose a "SKIPPED: Nighttime" shown in daytime:
        if these sunrise/sunset times look wrong, the HA location/timezone is
        misconfigured; if they look right, the value is stale (issue #34).

        Sunrise/sunset are the RAW astronomical times. The nighttime-window
        offsets (issue #42) are reported alongside so the effective window can
        be reconstructed: night starts (sunset - sunset_offset) and ends
        (sunrise + sunrise_offset).
        """
        sunset = self._astral_service.get_sunset(now)
        sunrise = self._astral_service.get_sunrise(now)
        sunset_offset = int(get_float(self.hass, self._nighttime_sunset_offset_entity, 0))
        sunrise_offset = int(get_float(self.hass, self._nighttime_sunrise_offset_entity, 0))
        return {
            "now": now.isoformat(),
            "sunrise_today": sunrise.isoformat() if sunrise else None,
            "sunset_today": sunset.isoformat() if sunset else None,
            "nighttime_sunset_offset_min": sunset_offset,
            "nighttime_sunrise_offset_min": sunrise_offset,
            # issue #47: expose the raw computed result so a "SKIPPED: Nighttime"
            # in daytime is fully self-diagnosable (right times + True here =>
            # genuine logic input; otherwise location/tz misconfig or stale).
            "is_nighttime_computed": self._astral_service.is_nighttime(
                now, sunset_offset, sunrise_offset
            ),
        }

    async def _handle_nighttime_transition(self, now: datetime, current_profile: str | None) -> None:
        """Handle sunset transition when Solar Surplus is no longer allowed to run."""
        charger_is_on = await self.charger_controller.is_charging()
        nighttime_debug = self._build_nighttime_debug_attributes(now)

        if not charger_is_on:
            if self._has_control():
                self._release_control("Nighttime with charger off")
                self._handle_control_loss("Nighttime with charger off")
            self.logger.skip("Nighttime - Solar Surplus only operates during daytime (sunrise to sunset)")
            await self._update_diagnostic_sensor(
                "SKIPPED: Nighttime",
                {
                    "reason": "Solar production unavailable at night",
                    "last_check": dt_util.now().isoformat(),
                    **nighttime_debug,
                },
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
                    "last_check": dt_util.now().isoformat(),
                    **nighttime_debug,
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
                    "last_check": dt_util.now().isoformat(),
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
                    "last_check": dt_util.now().isoformat(),
                },
            )

    async def _handle_home_battery_usage(self, surplus_watts: float, priority: str | None) -> None:
        """Handle home battery support mode.

        Args:
            surplus_watts: Current surplus in watts
            priority: Current priority (EV, HOME, EV_FREE, or None if balancer disabled)
        """
        # v1.7.0: PV-only mode — battery support is permanently inactive.
        if not self._has_home_battery:
            self._battery_support_active = False
            return

        use_battery = get_bool(self.hass, self._use_home_battery_entity)
        if not use_battery:
            self._battery_support_active = False
            return

        # v1.6.22: Sunset buffer guard
        # Block battery support when sunset is imminent — avoid draining home battery
        # for the few remaining minutes of fading solar. Charging continues on solar
        # surplus only; when surplus drops below threshold, normal stop logic applies.
        # Guard the get_float call: on upgrade the entity may not exist yet until the
        # next HA restart registers it — avoid log spam from state_helper.
        if self._battery_support_sunset_buffer_entity:
            buffer_min = get_float(
                self.hass,
                self._battery_support_sunset_buffer_entity,
                DEFAULT_BATTERY_SUPPORT_SUNSET_BUFFER_MIN,
            )
        else:
            buffer_min = DEFAULT_BATTERY_SUPPORT_SUNSET_BUFFER_MIN
        if buffer_min > 0:
            now = dt_util.now()
            sunset = self._astral_service.get_sunset(now)
            if sunset and now + timedelta(minutes=buffer_min) >= sunset:
                if self._battery_support_active:
                    self.logger.info(
                        f"Battery support DEACTIVATING — sunset in <{int(buffer_min)} min "
                        f"(sunset={sunset.strftime('%H:%M')})"
                    )
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

    def _is_battery_bridge_allowed(self, priority: str | None) -> bool:
        """Safety guards for the v2.1.0 deadband battery bridge (issue #29).

        The bridge (section 12a) keeps an already-charging session alive off
        capped battery discharge. It only runs when ``_calculate_target_amperage``
        returned 0 — i.e. exactly when ``_battery_support_active`` is False — so it
        must re-apply the same guards ``_handle_home_battery_usage`` uses, or it
        would drain the home battery in situations the user opted out of:
        - no home battery configured (PV-only),
        - both SOC targets already met (PRIORITY_EV_FREE) — regression class fixed
          in v1.3.24 (PRIORITY_HOME already returns earlier in the periodic check),
        - sunset imminent (sunset buffer guard) — v1.6.22,
        - home SOC at/below the configured minimum.
        Balancer-disabled (priority None) is allowed: the explicit watt limit is the
        opt-in and the SOC floor still bounds the drain.
        """
        if not self._has_home_battery:
            return False
        if priority == PRIORITY_EV_FREE:
            return False
        if self._battery_support_sunset_buffer_entity:
            buffer_min = get_float(
                self.hass,
                self._battery_support_sunset_buffer_entity,
                DEFAULT_BATTERY_SUPPORT_SUNSET_BUFFER_MIN,
            )
        else:
            buffer_min = DEFAULT_BATTERY_SUPPORT_SUNSET_BUFFER_MIN
        if buffer_min > 0:
            now = dt_util.now()
            sunset = self._astral_service.get_sunset(now)
            if sunset and now + timedelta(minutes=buffer_min) >= sunset:
                return False
        home_soc = get_float(self.hass, self._soc_home, 0)
        min_soc = get_float(self.hass, self._home_battery_min_soc_entity, 20)
        if home_soc <= min_soc:
            return False
        return True

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
        # ALWAYS calculate from surplus first (effective voltage = 230 V single,
        # 690 V three-phase → surplus_amps stays a valid per-phase amperage)
        surplus_amps = surplus_watts / self._effective_voltage
        is_charging = current_amperage > 0

        # CASE 1: Surplus sufficient to START or INCREASE (>= 6.5A)
        if surplus_amps >= SURPLUS_START_THRESHOLD:
            target = self._amp_levels[0]
            for level in self._amp_levels:
                if level <= surplus_amps:
                    target = level
                else:
                    break
            return target

        # CASE 2: Surplus in DEAD BAND (5.5A - 6.5A)
        # Maintain current level - don't increase, don't decrease
        if surplus_amps >= SURPLUS_STOP_THRESHOLD:
            if is_charging:
                # issue #51: the dead-band "maintain" rule is only valid at the
                # FLOOR — it exists to prevent stop/start oscillation around the
                # 6 A minimum. Applied to a higher current (e.g. 20 A with only
                # 5.6 A of surplus) it locks an over-sized level and the home
                # battery silently covers the deficit on hybrid inverters until
                # a grid spike finally fires grid-import protection.
                floor = self._amp_levels[0]
                if current_amperage <= floor:
                    # At the floor — maintain to prevent oscillation (original intent).
                    self.logger.debug(
                        f"Surplus in hysteresis band ({surplus_amps:.2f}A, "
                        f"range {SURPLUS_STOP_THRESHOLD}-{SURPLUS_START_THRESHOLD}A) "
                        f"and at floor {floor}A - maintaining"
                    )
                    return current_amperage
                # Above the floor: surplus is a clear deficit. Return one level
                # down so the surplus-decrease path applies its 30s drop delay.
                # Clamp at the floor — only CASE 3 (< stop threshold) may stop.
                next_amps = AmperageCalculator.get_next_level_down(
                    current_amperage, self._amp_levels
                )
                next_amps = next_amps if next_amps >= floor else floor
                self.logger.info(
                    f"Surplus in hysteresis band ({surplus_amps:.2f}A) but current "
                    f"{current_amperage}A is above floor {floor}A - "
                    f"requesting step down to {next_amps}A"
                )
                return next_amps
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
        current_time = time.monotonic()

        if self._last_grid_import_high is None:
            self._last_grid_import_high = current_time
            # issue #46: invalidate any pre-cloud stability credit the moment
            # grid import is first detected. Otherwise _surplus_stable_since
            # keeps accumulating through the cloud and, once it passes, the
            # system jumps straight to full target amperage in one step (large
            # battery draw) instead of re-earning a fresh 60s stability window.
            self._surplus_stable_since = None
            self.logger.warning(
                f"Grid import ({grid_import}W) > threshold ({grid_threshold}W) - Starting {grid_import_delay}s delay"
            )
            await self._update_diagnostic_sensor(
                "GRID_IMPORT_DELAY",
                {
                    "decision": "start_delay",
                    "reason": "Grid import above threshold",
                    **self._get_grid_import_debug_context(
                        grid_import=grid_import,
                        grid_threshold=grid_threshold,
                        grid_import_delay=grid_import_delay,
                        current_amps=current_amps,
                    ),
                },
            )
            return

        elapsed = current_time - self._last_grid_import_high
        if elapsed < grid_import_delay:
            self.logger.info(f"Grid import delay: {elapsed:.1f}s / {grid_import_delay}s")
            await self._update_diagnostic_sensor(
                "GRID_IMPORT_DELAY",
                {
                    "decision": "waiting_delay",
                    "reason": "Grid import still above threshold",
                    **self._get_grid_import_debug_context(
                        grid_import=grid_import,
                        grid_threshold=grid_threshold,
                        grid_import_delay=grid_import_delay,
                        current_amps=current_amps,
                    ),
                },
            )
            return

        self.logger.warning("Grid import delay ELAPSED - Reducing charging")
        self._last_grid_import_high = None
        # issue #46: belt-and-suspenders — require a fresh stability window
        # after each step-down too, so the ramp can't jump back up in one step.
        self._surplus_stable_since = None

        # Gradual ramp down: one level at a time via AmperageCalculator
        next_amps = AmperageCalculator.get_next_level_down(current_amps, self._amp_levels)

        if next_amps > 0:
            self.logger.info(f"Stepping down ONE level: {current_amps}A -> {next_amps}A")
            self.logger.warning(
                "Grid import protection action: step_down current=%sA next=%sA import=%sW threshold=%sW",
                current_amps,
                next_amps,
                round(grid_import, 1),
                round(grid_threshold, 1),
            )
            await self._update_diagnostic_sensor(
                "GRID_IMPORT_STEP_DOWN",
                {
                    "decision": "step_down",
                    "reason": "Grid import persisted above threshold",
                    **self._get_grid_import_debug_context(
                        grid_import=grid_import,
                        grid_threshold=grid_threshold,
                        grid_import_delay=grid_import_delay,
                        current_amps=current_amps,
                        target_amps=next_amps,
                    ),
                },
            )
            if await self._ensure_control("Grid import protection"):
                await self.charger_controller.set_amperage(next_amps, "Grid import protection")
        elif current_amps == 0:
            self.logger.info("Charger is already off (0A) - keeping charger stopped")
            await self._update_diagnostic_sensor(
                "GRID_IMPORT_NOOP",
                {
                    "decision": "charger_already_off",
                    "reason": "Grid import high but charger was already off",
                    **self._get_grid_import_debug_context(
                        grid_import=grid_import,
                        grid_threshold=grid_threshold,
                        grid_import_delay=grid_import_delay,
                        current_amps=current_amps,
                        target_amps=0,
                    ),
                },
            )
        else:
            # At minimum level or non-standard level — stop charger
            reason = (
                "Grid import protection - minimum level reached"
                if current_amps in self._amp_levels
                else f"Grid import protection - non-standard level {current_amps}A"
            )
            self.logger.info(f"Stopping charger: {reason}")
            self.logger.warning(
                "Grid import protection action: stop current=%sA import=%sW threshold=%sW",
                current_amps,
                round(grid_import, 1),
                round(grid_threshold, 1),
            )
            await self._update_diagnostic_sensor(
                "GRID_IMPORT_STOP",
                {
                    "decision": "stop_at_minimum",
                    "reason": reason,
                    **self._get_grid_import_debug_context(
                        grid_import=grid_import,
                        grid_threshold=grid_threshold,
                        grid_import_delay=grid_import_delay,
                        current_amps=current_amps,
                        target_amps=0,
                    ),
                },
            )
            if await self._acquire_control("turn_off", reason):
                await self.charger_controller.stop_charger(reason)
                self._release_control("Grid import protection stop")
                self._handle_control_loss("Grid import protection stop")

    async def _handle_surplus_decrease(
        self,
        target_amps: int,
        current_amps: int,
        surplus_amps: float,
        surplus_drop_delay: float,
    ) -> None:
        """Handle surplus decrease with delay."""
        current_time = time.monotonic()

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

        # Gradual ramp down: one level at a time via AmperageCalculator
        next_amps = AmperageCalculator.get_next_level_down(current_amps, self._amp_levels)

        if next_amps > 0:
            self.logger.info(f"Stepping down ONE level: {current_amps}A -> {next_amps}A")
            if await self._ensure_control("Surplus decrease"):
                await self.charger_controller.set_amperage(next_amps, "Surplus decrease")
        elif current_amps == 0:
            self.logger.warning("Charger is off (0A) - starting at minimum 6A")
            if await self._ensure_control("Surplus decrease - start at 6A"):
                await self.charger_controller.set_amperage(
                    6,
                    "Surplus decrease - charger was off, starting at 6A",
                )
        else:
            # At minimum level or non-standard level — stop charger
            self.logger.info(f"At minimum/non-standard level ({current_amps}A) - stopping charger")
            if await self._acquire_control(
                "turn_off",
                "Surplus decrease - minimum level reached",
            ):
                await self.charger_controller.stop_charger(
                    "Surplus decrease - minimum level reached"
                )
                self._release_control("Surplus decrease stop")
                self._handle_control_loss("Surplus decrease stop")

    async def _handle_surplus_increase(self, target_amps: int, current_amps: int) -> None:
        """Handle surplus increase with stability requirement.

        Args:
            target_amps: Target amperage to set
            current_amps: Current amperage (0 if charger off)
        """

        # issue #52: the dispatcher routed here because target_amps > current_amps,
        # so any pending surplus-drop debounce is stale by definition. Clear it at
        # the entry point (the only spot covering all return paths below) so a future
        # dip starts a fresh evsc_surplus_drop_delay window instead of firing an
        # immediate step-down against an old timestamp. This is what makes the
        # one-level-per-tick ramp (#49) hold its level under surplus oscillation
        # instead of ratcheting downward.
        self._last_surplus_sufficient = None

        # Starting from 0A (charger off) requires 60s stability (cloud protection)
        if current_amps == 0:
            # Start stability tracking if not already started
            if self._surplus_stable_since is None:
                self._surplus_stable_since = dt_util.now()
                self.logger.info(
                    f"Surplus sufficient ({target_amps}A available) - "
                    f"Waiting {SURPLUS_INCREASE_DELAY}s for stability before starting (cloud protection)"
                )
                return

            # Check stability duration
            stable_duration = (dt_util.now() - self._surplus_stable_since).total_seconds()
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
                self._surplus_stable_since = dt_util.now()
                self.logger.info(
                    f"Surplus increase detected ({current_amps}A → {target_amps}A) - "
                    f"Waiting {SURPLUS_INCREASE_DELAY}s for stability (cloud protection)"
                )
                return

            # Check stability duration
            stable_duration = (dt_util.now() - self._surplus_stable_since).total_seconds()
            if stable_duration < SURPLUS_INCREASE_DELAY:
                self.logger.debug(
                    f"Waiting for stable increase: {stable_duration:.1f}s / {SURPLUS_INCREASE_DELAY}s"
                )
                return

            # Stability confirmed — step up ONE level only (issue #49).
            # Jumping straight to target_amps (e.g. 13A → 23A) overshoots the
            # inverter's PV ramp on zero-export hybrids, triggers grid-import
            # protection, and forces a slow walk-down. One level per stability
            # window keeps each step inside the grid-import delay window.
            next_amps = AmperageCalculator.get_next_level_up(
                current_amps, target_amps, self._power_model.amp_levels
            )
            self.logger.action(
                f"Surplus stable for {SURPLUS_INCREASE_DELAY}s - "
                f"stepping {current_amps}A → {next_amps}A (target {target_amps}A)"
            )
            # Re-arm the stability window so the next step needs another 60s.
            self._surplus_stable_since = None
            if await self._ensure_control("Stable surplus increase"):
                await self.charger_controller.set_amperage(next_amps, "Stable surplus step-up")

    def _reset_state_tracking(self) -> None:
        """Reset state tracking flags."""
        self._last_surplus_sufficient = None
        self._last_grid_import_high = None
        self._surplus_stable_since = None
        self._deadband_start_time = None
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

    def _get_grid_import_debug_context(
        self,
        *,
        grid_import: float,
        grid_threshold: float,
        grid_import_delay: float,
        current_amps: int,
        target_amps: int | None = None,
    ) -> dict:
        """Return a debug snapshot for grid import protection decisions."""
        now_ts = time.monotonic()
        timer_started = self._last_grid_import_high
        elapsed = None
        remaining = None

        if timer_started is not None:
            elapsed = max(0.0, now_ts - timer_started)
            remaining = max(0.0, grid_import_delay - elapsed)

        return {
            "grid_import_w": grid_import,
            "grid_threshold_w": grid_threshold,
            "grid_import_delay_s": grid_import_delay,
            "grid_import_timer_started_ts": timer_started,
            "grid_import_elapsed_s": round(elapsed, 1) if elapsed is not None else None,
            "grid_import_remaining_s": round(remaining, 1) if remaining is not None else None,
            "battery_support_active": self._battery_support_active,
            "use_home_battery_enabled": get_bool(self.hass, self._use_home_battery_entity),
            "current_charging_a": current_amps,
            "target_charging_a": target_amps,
        }

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

        # v2.8.0: consumption-spike fast response cleanup
        if self._grid_listener_unsub:
            self._grid_listener_unsub()
            self._grid_listener_unsub = None
        self._reset_spike_tracking()

        self.logger.info("Solar Surplus automation removed")

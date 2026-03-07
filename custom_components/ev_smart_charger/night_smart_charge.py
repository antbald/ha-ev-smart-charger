"""Night Smart Charge automation for EV Smart Charger."""
from __future__ import annotations
from datetime import datetime, timedelta

from homeassistant.core import HomeAssistant, State, callback
from homeassistant.helpers.event import async_track_time_interval, async_track_state_change_event
from homeassistant.util import dt as dt_util

from .const import (
    CONF_CAR_OWNER,
    CONF_EV_CHARGER_STATUS,
    CONF_EV_CHARGER_SWITCH,
    CONF_SOC_HOME,
    CONF_PV_FORECAST,
    CONF_GRID_IMPORT,
    CONF_NOTIFY_SERVICES,
    CONF_EV_CHARGER_CURRENT,
    CONF_BATTERY_CAPACITY,
    CONF_ENERGY_FORECAST_TARGET,
    CHARGER_STATUS_CHARGING,
    CHARGER_STATUS_FREE,
    NIGHT_CHARGE_MODE_BATTERY,
    NIGHT_CHARGE_MODE_GRID,
    NIGHT_CHARGE_MODE_IDLE,
    HELPER_NIGHT_CHARGE_ENABLED_SUFFIX,
    HELPER_NIGHT_CHARGE_TIME_SUFFIX,
    HELPER_CAR_READY_TIME_SUFFIX,
    HELPER_MIN_SOLAR_FORECAST_THRESHOLD_SUFFIX,
    HELPER_NIGHT_CHARGE_AMPERAGE_SUFFIX,
    HELPER_HOME_BATTERY_MIN_SOC_SUFFIX,
    HELPER_GRID_IMPORT_THRESHOLD_SUFFIX,
    HELPER_GRID_IMPORT_DELAY_SUFFIX,
    HELPER_CAR_READY_MONDAY_SUFFIX,
    HELPER_CAR_READY_TUESDAY_SUFFIX,
    HELPER_CAR_READY_WEDNESDAY_SUFFIX,
    HELPER_CAR_READY_THURSDAY_SUFFIX,
    HELPER_CAR_READY_FRIDAY_SUFFIX,
    HELPER_CAR_READY_SATURDAY_SUFFIX,
    HELPER_CAR_READY_SUNDAY_SUFFIX,
    DEFAULT_CAR_READY_TIME,
    PRIORITY_NIGHT_CHARGE,
)
from .runtime import EVSCRuntimeData
from .charger_controller import CurrentControlAdapter
from .utils.logging_helper import EVSCLogger
from .utils import state_helper
from .utils.mobile_notification_service import MobileNotificationService
from .utils.astral_time_service import AstralTimeService
from .utils.time_parsing_service import TimeParsingService

STOP_REASON_DEADLINE_OR_TARGET = "deadline_or_target_reached"
STOP_REASON_HOME_BATTERY_MIN = "home_battery_min_reached"
STOP_REASON_EV_TARGET = "ev_target_reached"
STOP_REASON_CHARGER_NOT_CHARGING = "charger_not_charging"
STOP_REASON_GRID_FALLBACK_FAILED = "grid_fallback_failed"
STOP_REASON_GRID_IMPORT_CAR_NOT_READY = "grid_import_detected_car_not_ready"
STOP_REASON_BOOST_PREEMPTED = "boost_preempted"


class NightSmartCharge:
    """Manages Night Smart Charge automation with Priority Balancer integration."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry_id: str,
        config: dict,
        priority_balancer,
        charger_controller,
        runtime_data: EVSCRuntimeData | None = None,
        coordinator=None,
        boost_charge=None,
    ) -> None:
        """
        Initialize Night Smart Charge.

        Args:
            hass: Home Assistant instance
            entry_id: Config entry ID
            config: User configuration
            priority_balancer: PriorityBalancer instance for target checks
            charger_controller: ChargerController instance for charger operations
        """
        self.hass = hass
        self.entry_id = entry_id
        self.config = config
        self.priority_balancer = priority_balancer
        self.charger_controller = charger_controller
        self._runtime_data = runtime_data
        self._coordinator = coordinator
        self._boost_charge = boost_charge
        self.logger = EVSCLogger("NIGHT SMART CHARGE")
        self._astral_service = AstralTimeService(hass)
        self._mobile_notifier = MobileNotificationService(
            hass,
            config.get(CONF_NOTIFY_SERVICES, []),
            entry_id,
            config.get(CONF_CAR_OWNER),
            runtime_data=runtime_data,
        )

        # User-configured entities
        self._charger_status = config.get(CONF_EV_CHARGER_STATUS)
        self._charger_current = config.get(CONF_EV_CHARGER_CURRENT)
        self._charger_switch = config.get(CONF_EV_CHARGER_SWITCH)  # v1.4.11: Fixed missing initialization
        self._soc_home = config.get(CONF_SOC_HOME)
        self._pv_forecast_entity = config.get(CONF_PV_FORECAST)
        self._grid_import = config.get(CONF_GRID_IMPORT)  # v1.3.23: Grid import sensor

        # Helper entities (discovered in async_setup)
        self._night_charge_enabled_entity = None
        self._night_charge_time_entity = None
        self._car_ready_time_entity = None  # v1.3.18: Car ready deadline
        self._solar_forecast_threshold_entity = None
        self._night_charge_amperage_entity = None
        self._home_battery_min_soc_entity = None
        self._grid_import_threshold_entity = None  # v1.3.23: Grid import max threshold
        self._grid_import_delay_entity = None  # v1.3.23: Grid import protection delay
        self._car_ready_entities = {}  # Dict: {0: monday_entity, ..., 6: sunday_entity}

        # Timer and state tracking
        self._timer_unsub = None
        self._charger_status_unsub = None
        self._battery_monitor_unsub = None
        self._grid_monitor_unsub = None  # Grid charge monitoring timer (v1.3.17)
        self._night_charge_active = False
        self._active_mode = NIGHT_CHARGE_MODE_IDLE
        self._last_window_check_time = None
        self._last_completion_time = None  # Track when session completed

        # v1.3.23: Dynamic amperage management state
        from .utils.amperage_helper import StabilityTracker
        self._grid_import_trigger_time = None  # When grid import first exceeded threshold
        self._recovery_tracker = StabilityTracker()  # Track stability for recovery (60s)

        # v1.4.4: Robust window check state machine
        self._session_state = "ready"  # ready|active|completed_today|cooldown
        self._activation_date = None  # Date when last activated (prevents re-activation same day)
        self._last_completion_date = None  # Date when last completed
        self._last_diagnostic_log_time = None  # For throttling diagnostic logs

    @property
    def _automation_name(self) -> str:
        """Return the coordinator owner name for Night Smart Charge."""
        return "Night Smart Charge"

    def _has_control(self) -> bool:
        """Return True when Night Smart Charge currently owns the session."""
        if self._coordinator is None:
            return True
        return self._coordinator.is_automation_active(self._automation_name)

    async def _acquire_control(self, action: str, reason: str) -> bool:
        """Acquire coordinator ownership for a charger action."""
        if self._coordinator is None or self._has_control():
            return True

        allowed, denial_reason = await self._coordinator.request_charger_action(
            automation_name=self._automation_name,
            action=action,
            reason=reason,
            priority=PRIORITY_NIGHT_CHARGE,
        )
        if not allowed:
            self.logger.info(f"Coordinator denied Night Smart Charge action: {denial_reason}")
            return False
        return True

    async def _ensure_control(self, reason: str) -> bool:
        """Ensure Night Smart Charge still owns the active session."""
        if self._coordinator is None:
            return True
        if self._has_control():
            return True
        await self._handle_control_loss(f"Ownership lost: {reason}")
        return False

    def _release_control(self, reason: str) -> None:
        """Release coordinator ownership when Night Smart Charge completes."""
        if self._coordinator is not None:
            self._coordinator.release_control(self._automation_name, reason)

    async def _handle_control_loss(self, reason: str) -> None:
        """Stand down after another automation preempts Night Smart Charge."""
        if self._battery_monitor_unsub:
            self._battery_monitor_unsub()
            self._battery_monitor_unsub = None

        if self._grid_monitor_unsub:
            self._grid_monitor_unsub()
            self._grid_monitor_unsub = None

        if self.is_active():
            self.logger.warning(f"Night Smart Charge lost ownership: {reason}")

        self._night_charge_active = False
        self._active_mode = NIGHT_CHARGE_MODE_IDLE
        self._session_state = "ready"

    async def _stop_charger_with_control(self, reason: str) -> bool:
        """Stop the charger only while Night Smart Charge still owns the session."""
        if not await self._ensure_control(reason):
            return False
        if not await self._acquire_control("turn_off", reason):
            return False
        result = await self.charger_controller.stop_charger(reason)
        return self._operation_succeeded(result)

    async def _adjust_for_grid_import_with_control(self, reason: str):
        """Adjust charger amperage only while Night Smart Charge owns the session."""
        if not await self._ensure_control(reason):
            return None
        return await self.charger_controller.adjust_for_grid_import(reason=reason)

    async def _recover_to_target_with_control(self, target_amps: int, reason: str):
        """Recover charger amperage only while Night Smart Charge owns the session."""
        if not await self._ensure_control(reason):
            return None
        return await self.charger_controller.recover_to_target(
            target_amps=target_amps,
            reason=reason,
        )

    @staticmethod
    def _operation_succeeded(result) -> bool:
        """Handle both OperationResult and boolean-like mocks."""
        if hasattr(result, "success"):
            return result.success
        return bool(result)

    async def async_setup(self) -> None:
        """Set up Night Smart Charge automation."""
        self.logger.separator()
        self.logger.start("Night Smart Charge initialization")
        self.logger.separator()

        # Discover helper entities (optional for backward compatibility)
        self._night_charge_enabled_entity = self._resolve_entity(HELPER_NIGHT_CHARGE_ENABLED_SUFFIX)
        self._night_charge_time_entity = self._resolve_entity(HELPER_NIGHT_CHARGE_TIME_SUFFIX)
        self._car_ready_time_entity = self._resolve_entity(HELPER_CAR_READY_TIME_SUFFIX)
        self._solar_forecast_threshold_entity = self._resolve_entity(
            HELPER_MIN_SOLAR_FORECAST_THRESHOLD_SUFFIX
        )
        self._night_charge_amperage_entity = self._resolve_entity(
            HELPER_NIGHT_CHARGE_AMPERAGE_SUFFIX
        )
        self._home_battery_min_soc_entity = self._resolve_entity(
            HELPER_HOME_BATTERY_MIN_SOC_SUFFIX
        )
        self._grid_import_threshold_entity = self._resolve_entity(
            HELPER_GRID_IMPORT_THRESHOLD_SUFFIX
        )
        self._grid_import_delay_entity = self._resolve_entity(
            HELPER_GRID_IMPORT_DELAY_SUFFIX
        )

        # Discover car_ready switches for each day (v1.3.13+)
        days_suffixes = [
            HELPER_CAR_READY_MONDAY_SUFFIX,
            HELPER_CAR_READY_TUESDAY_SUFFIX,
            HELPER_CAR_READY_WEDNESDAY_SUFFIX,
            HELPER_CAR_READY_THURSDAY_SUFFIX,
            HELPER_CAR_READY_FRIDAY_SUFFIX,
            HELPER_CAR_READY_SATURDAY_SUFFIX,
            HELPER_CAR_READY_SUNDAY_SUFFIX,
        ]

        for idx, suffix in enumerate(days_suffixes):
            entity = self._resolve_entity(suffix)
            if entity:
                self._car_ready_entities[idx] = entity
                self.logger.info(f"Found car_ready entity for day {idx}: {entity}")
            else:
                self.logger.warning(f"Car ready entity not found for day {idx} (suffix: {suffix})")

        # Warn about missing entities (backward compatibility)
        missing_entities = []
        if not self._night_charge_enabled_entity:
            missing_entities.append(HELPER_NIGHT_CHARGE_ENABLED_SUFFIX)
        if not self._night_charge_time_entity:
            missing_entities.append(HELPER_NIGHT_CHARGE_TIME_SUFFIX)
        if not self._solar_forecast_threshold_entity:
            missing_entities.append(HELPER_MIN_SOLAR_FORECAST_THRESHOLD_SUFFIX)
        if not self._night_charge_amperage_entity:
            missing_entities.append(HELPER_NIGHT_CHARGE_AMPERAGE_SUFFIX)
        if not self._home_battery_min_soc_entity:
            missing_entities.append(HELPER_HOME_BATTERY_MIN_SOC_SUFFIX)

        if missing_entities:
            self.logger.warning(
                f"Helper entities not found: {', '.join(missing_entities)} - "
                f"Using default values. Restart Home Assistant to create missing helper entities."
            )

        # Log configuration
        self._log_configuration()

        # Start periodic check timer (every 1 minute)
        self._timer_unsub = async_track_time_interval(
            self.hass,
            self._async_periodic_check,
            timedelta(minutes=1),
        )

        # Listen to charger status changes for late arrival detection
        self._charger_status_unsub = async_track_state_change_event(
            self.hass,
            self._charger_status,
            self._async_charger_status_changed
        )

        self.logger.success("Night Smart Charge setup completed successfully")
        self.logger.info("Periodic check interval: 1 minute")
        self.logger.info("Late arrival detection: Enabled")
        self.logger.separator()

    def _resolve_entity(self, key: str) -> str | None:
        """Resolve an integration-owned helper entity."""
        if self._runtime_data is None:
            return None
        return self._runtime_data.get_entity_id(key)

    async def async_remove(self) -> None:
        """Remove Night Smart Charge automation."""
        self.logger.info("Removing Night Smart Charge")

        if self._timer_unsub:
            self._timer_unsub()
        if self._charger_status_unsub:
            self._charger_status_unsub()
        if self._battery_monitor_unsub:
            self._battery_monitor_unsub()
        if self._grid_monitor_unsub:
            self._grid_monitor_unsub()

        self.logger.success("Night Smart Charge removed")

    # ========== PUBLIC INTERFACE ==========

    def is_enabled(self) -> bool:
        """Check if Night Smart Charge is enabled."""
        if not self._night_charge_enabled_entity:
            return False
        return state_helper.get_bool(self.hass, self._night_charge_enabled_entity)

    def is_active(self) -> bool:
        """Check if currently charging (mode != IDLE)."""
        return self._night_charge_active and self._active_mode != NIGHT_CHARGE_MODE_IDLE

    def get_active_mode(self) -> str:
        """
        Get current night charge mode.

        Returns:
            NIGHT_CHARGE_MODE_BATTERY, NIGHT_CHARGE_MODE_GRID, or NIGHT_CHARGE_MODE_IDLE
        """
        return self._active_mode

    async def async_request_immediate_check(self, reason: str = "") -> None:
        """Force an immediate evaluation cycle."""
        if reason:
            self.logger.info(f"Immediate Night Smart Charge check requested: {reason}")
        await self._async_periodic_check(dt_util.now())

    async def async_pause_for_external_override(self, reason: str = "") -> None:
        """Pause an active night charge session because another override took control."""
        if not self.is_active():
            return

        self.logger.info(
            f"Pausing Night Smart Charge due to external override: {reason or 'No reason provided'}"
        )
        self._release_control(reason or "External override")
        await self._handle_control_loss(reason or "External override")

    def _is_in_active_window_for_handover(self, now: datetime) -> tuple[bool, str]:
        """
        Check handover window without mutating the session state machine.

        This is used by Solar Surplus sunset handover validation and must stay side-effect free.
        """
        from .const import (
            ACTIVATION_GRACE_BEFORE_MINUTES,
            ACTIVATION_GRACE_AFTER_MINUTES,
            NIGHT_CHARGE_COOLDOWN_SECONDS,
        )

        if self._session_state == "completed_today" and self._last_completion_date == now.date():
            return False, "already_completed_today"

        if self._session_state == "cooldown" and self._last_completion_time:
            elapsed = (now - self._last_completion_time).total_seconds()
            if elapsed < NIGHT_CHARGE_COOLDOWN_SECONDS:
                return False, "cooldown_active"

        if self._session_state == "active":
            return True, "session_already_active"

        if not self._night_charge_time_entity:
            return False, "night_charge_time_not_configured"

        time_state = state_helper.get_state(self.hass, self._night_charge_time_entity)
        if not time_state or time_state in ("unknown", "unavailable"):
            return False, "night_charge_time_unavailable"

        try:
            scheduled_time = self._get_scheduled_time_for_today(now, time_state)
        except (ValueError, TypeError, IndexError):
            return False, "invalid_night_charge_time"

        sunrise = self._astral_service.get_next_sunrise_after(scheduled_time)
        if not sunrise:
            return False, "sunrise_unavailable"

        grace_start = scheduled_time - timedelta(minutes=ACTIVATION_GRACE_BEFORE_MINUTES)
        grace_end = scheduled_time + timedelta(minutes=ACTIVATION_GRACE_AFTER_MINUTES)

        in_grace = grace_start <= now < grace_end
        past_scheduled = now >= scheduled_time
        before_sunrise = now < sunrise
        in_window = in_grace or (past_scheduled and before_sunrise)

        if not in_window:
            return False, "outside_active_window"

        return True, "ok"

    async def async_try_handover_from_solar_surplus(self, reason: str = "") -> bool:
        """
        Try to hand over control from Solar Surplus to Night Smart Charge.

        Returns:
            True when Night Smart Charge accepted control and is active, False otherwise.
        """
        handover_reason = reason or "unspecified"
        self.logger.info(f"Sunset transition - handover requested (reason: {handover_reason})")

        if self._boost_charge and self._boost_charge.is_active():
            self.logger.info("Handover rejected - Boost Charge is active")
            return False

        if not self.is_enabled():
            self.logger.info("Handover rejected - Night Smart Charge disabled")
            return False

        now = dt_util.now()
        in_window, window_reason = self._is_in_active_window_for_handover(now)
        if not in_window:
            self.logger.info(f"Handover rejected - window validation failed ({window_reason})")
            return False

        charger_status = state_helper.get_state(self.hass, self._charger_status)
        if not charger_status or charger_status in ("unknown", "unavailable", CHARGER_STATUS_FREE):
            self.logger.info(f"Handover rejected - charger not ready (status: {charger_status})")
            return False

        ev_target_reached = await self.priority_balancer.is_ev_target_reached()
        if ev_target_reached:
            ev_soc = await self.priority_balancer.get_ev_current_soc()
            ev_target = self.priority_balancer.get_ev_target_for_today()
            self.logger.info(
                f"Handover rejected - EV target already reached ({ev_soc}% >= {ev_target}%)"
            )
            return False

        if self.is_active():
            self.logger.success("Handover accepted - Night Smart Charge already active")
            return True

        previous_session_state = self._session_state
        previous_activation_date = self._activation_date

        # Mirror standard activation transition without waiting for periodic tick.
        if self._session_state == "ready":
            self._session_state = "active"
            self._activation_date = now.date()

        try:
            await self._evaluate_and_charge()
        except Exception as ex:
            self._session_state = previous_session_state
            self._activation_date = previous_activation_date
            self.logger.error(f"Handover rejected - evaluation failed: {ex}")
            return False

        if self.is_active():
            self.logger.success("Sunset transition - Handover accepted")
            return True

        self._session_state = previous_session_state
        self._activation_date = previous_activation_date
        self.logger.info("Handover rejected - evaluation completed without starting Night Smart Charge")
        return False

    # ========== PERIODIC MONITORING ==========

    @callback
    async def _async_periodic_check(self, now) -> None:
        """Periodic check every minute."""
        from .const import NIGHT_CHARGE_COOLDOWN_SECONDS

        current_time = dt_util.now()
        self.logger.debug(f"Periodic check at {current_time.strftime('%H:%M:%S')}")

        if self._boost_charge and self._boost_charge.is_active():
            self.logger.debug("Boost Charge active - skipping Night Smart Charge check")
            return

        if not self.is_active() and self._has_control():
            self._release_control("Night Smart Charge idle without an active session")

        # Check if session recently completed (within 1 hour cooldown)
        if self._last_completion_time:
            time_since = (current_time - self._last_completion_time).total_seconds()
            if time_since < NIGHT_CHARGE_COOLDOWN_SECONDS:
                self.logger.debug(
                    f"Session completed {time_since:.0f}s ago "
                    f"(cooldown: {NIGHT_CHARGE_COOLDOWN_SECONDS}s) - skipping re-evaluation"
                )
                return

        # Check if already active - validate stop conditions (v1.3.18)
        if self.is_active():
            if not await self._ensure_control("periodic_check_active_session"):
                return
            # Validate stop conditions (deadline/sunrise based on car_ready flag)
            should_stop, reason = await self._should_stop_for_deadline(current_time)
            if should_stop:
                self.logger.warning(
                    f"{self.logger.ALERT} Active session detected past stop condition - terminating"
                )
                if await self._stop_charger_with_control(reason):
                    await self._complete_night_charge(STOP_REASON_DEADLINE_OR_TARGET, terminal=True)
            else:
                self.logger.debug("Already active and within valid window, skipping re-evaluation")
            return

        # Check if we're in active window
        if not await self._is_in_active_window(current_time):
            self.logger.debug("Not in active window, skipping")
            return

        # Check if enabled
        if not self.is_enabled():
            self.logger.debug("Night Smart Charge disabled, skipping")
            return

        # Run evaluation
        self.logger.separator()
        self.logger.start(f"Night charge evaluation at {current_time.strftime('%H:%M:%S')}")
        await self._evaluate_and_charge()

    @callback
    async def _async_charger_status_changed(self, event) -> None:
        """Handle charger status changes for late arrival detection."""
        new_state: State = event.data.get("new_state")
        old_state: State = event.data.get("old_state")

        if not new_state or not old_state:
            return

        # Detect car just plugged in (from free to any other state)
        if old_state.state == CHARGER_STATUS_FREE and new_state.state != CHARGER_STATUS_FREE:
            self.logger.info(f"{self.logger.EV} Car plugged in (status: {new_state.state})")

            # Check if we're in active window and enabled
            now = dt_util.now()
            if self._boost_charge and self._boost_charge.is_active():
                self.logger.info("Boost Charge active - skipping late arrival handling")
            elif await self._is_in_active_window(now) and self.is_enabled():
                self.logger.info("Late arrival detected - running immediate check")
                await self._evaluate_and_charge()

    # ========== ACTIVE WINDOW DETECTION ==========

    async def _is_in_active_window(self, now: datetime) -> bool:
        """
        ROBUST window check with hybrid approach (v1.4.4).

        Features:
        - Grace period (±2-5 minutes) for clock drift tolerance
        - Hysteresis (stay active once activated)
        - Date-based completion tracking (prevents re-activation same day)
        - State machine (ready|active|completed_today|cooldown)
        - Comprehensive diagnostic logging

        Args:
            now: Current datetime

        Returns:
            True if in active window
        """
        from .const import ACTIVATION_GRACE_BEFORE_MINUTES, ACTIVATION_GRACE_AFTER_MINUTES

        # === STEP 1: State-based protection ===
        if self._session_state == "completed_today":
            if self._last_completion_date != now.date():
                # New day - reset to ready
                self._session_state = "ready"
                self.logger.info("🔄 New day detected - reset to ready state")
            else:
                self.logger.debug("Already completed today - inactive")
                return False

        if self._session_state == "cooldown":
            if self._cooldown_expired(now):
                self._session_state = "ready"
                self.logger.info("✅ Cooldown expired - ready for activation")
            else:
                elapsed = (now - self._last_completion_time).total_seconds()
                from .const import NIGHT_CHARGE_COOLDOWN_SECONDS
                remaining = NIGHT_CHARGE_COOLDOWN_SECONDS - elapsed
                self.logger.debug(f"Cooldown active - {remaining:.0f}s remaining")
                return False

        # === STEP 2: Hysteresis - stay active once activated ===
        if self._session_state == "active":
            self.logger.debug("Already active - maintaining state (hysteresis)")
            return True

        # === STEP 3: Time range validation with grace period ===
        if not self._night_charge_time_entity:
            self.logger.warning("Night charge time entity not configured")
            return False

        time_state = state_helper.get_state(self.hass, self._night_charge_time_entity)

        if not time_state or time_state in ("unknown", "unavailable"):
            self.logger.warning("Time entity unavailable for window check")
            return False

        # Get scheduled time for TODAY (not next occurrence)
        try:
            scheduled_time = self._get_scheduled_time_for_today(now, time_state)
        except (ValueError, TypeError, IndexError) as e:
            self.logger.error(f"Invalid time configuration: {time_state} - {e}")
            return False

        # Get next sunrise
        sunrise = self._astral_service.get_next_sunrise_after(scheduled_time)

        if not sunrise:
            self.logger.warning("Could not determine sunrise time")
            return False

        # Grace window: activate 2 min before → 5 min after scheduled time
        grace_start = scheduled_time - timedelta(minutes=ACTIVATION_GRACE_BEFORE_MINUTES)
        grace_end = scheduled_time + timedelta(minutes=ACTIVATION_GRACE_AFTER_MINUTES)

        # Check activation conditions
        in_grace = grace_start <= now < grace_end
        past_scheduled = now >= scheduled_time
        before_sunrise = now < sunrise

        is_active = (in_grace or (past_scheduled and before_sunrise))

        # === STEP 4: Comprehensive diagnostic logging (throttled) ===
        if self._last_diagnostic_log_time is None or (now - self._last_diagnostic_log_time).total_seconds() >= 60:
            self.logger.separator()
            self.logger.info(f"{self.logger.CALENDAR} 🔍 WINDOW CHECK DIAGNOSTIC")
            self.logger.info(f"   Current: {now.strftime('%Y-%m-%d %H:%M:%S')}")
            self.logger.info(f"   Scheduled (today): {scheduled_time.strftime('%Y-%m-%d %H:%M:%S')}")
            self.logger.info(f"   Grace window: [{grace_start.strftime('%H:%M')} - {grace_end.strftime('%H:%M')}]")
            self.logger.info(f"   Sunrise: {sunrise.strftime('%Y-%m-%d %H:%M:%S')}")
            self.logger.info(f"   Session state: {self._session_state}")
            self.logger.info(f"   Last activation date: {self._activation_date}")
            self.logger.info(f"   Last completion date: {self._last_completion_date}")
            self.logger.info("   ─────────────────────")
            self.logger.info(f"   In grace window: {in_grace}")
            self.logger.info(f"   Past scheduled: {past_scheduled}")
            self.logger.info(f"   Before sunrise: {before_sunrise}")
            self.logger.info(f"   Window ACTIVE: {is_active}")
            self.logger.separator()
            self._last_diagnostic_log_time = now
        else:
            # Frequent checks - debug level
            self.logger.debug(
                f"Window check: now={now.strftime('%H:%M')}, "
                f"scheduled={scheduled_time.strftime('%H:%M')}, "
                f"grace=[{grace_start.strftime('%H:%M')}-{grace_end.strftime('%H:%M')}], "
                f"state={self._session_state}, active={is_active}"
            )

        # === STEP 5: State transition ===
        if is_active and self._session_state == "ready":
            self.logger.info(f"{self.logger.SUCCESS} Activation window detected - marking as ACTIVE")
            self._session_state = "active"
            self._activation_date = now.date()

        return is_active

    # ========== MAIN EVALUATION LOGIC ==========

    async def _evaluate_and_charge(self) -> None:
        """Main decision logic for Night Smart Charge."""
        # v1.4.11: Comprehensive exception handling to prevent silent failures
        try:
            if self._boost_charge and self._boost_charge.is_active():
                self.logger.info("Boost Charge active - skipping Night Smart Charge evaluation")
                return

            # v1.4.2: Diagnostic snapshot at evaluation start
            now = dt_util.now()
            today = now.strftime("%A").lower()

            self.logger.separator()
            self.logger.info(f"{self.logger.DECISION} 📊 NIGHT SMART CHARGE - DIAGNOSTIC SNAPSHOT")
            self.logger.info(f"   Timestamp: {now.strftime('%Y-%m-%d %H:%M:%S')}")
            self.logger.info(f"   Day: {today.capitalize()}")
            self.logger.separator()

            # Configuration values
            try:
                self.logger.info("⚙️ Configuration:")

                # Safe retrieval of values
                is_enabled = state_helper.get_bool(self.hass, self._night_charge_enabled_entity) if self._night_charge_enabled_entity else False
                scheduled_time = self._get_night_charge_time()
                amperage = self._get_night_charge_amperage()
                solar_threshold = self._get_solar_threshold()

                # Get car ready status (this method logs internally too)
                car_ready_today = self._get_car_ready_for_today()
                car_ready_deadline = self._get_car_ready_time()

                self.logger.info(f"   Night Charge Enabled: {is_enabled}")
                self.logger.info(f"   Scheduled Time: {scheduled_time}")
                self.logger.info(f"   Night Charge Amperage: {amperage}A")
                self.logger.info(f"   Solar Forecast Threshold: {solar_threshold} kWh")
                self.logger.info(f"   Car Ready Today ({today.capitalize()}): {car_ready_today}")
                self.logger.info(f"   Car Ready Deadline: {car_ready_deadline}")
            except Exception as e:
                self.logger.error(f"Error logging configuration: {e}")
                # Continue execution even if logging fails

            # Current readings
            self.logger.info("📈 Current Readings:")
            ev_soc = await self.priority_balancer.get_ev_current_soc()
            home_soc = await self.priority_balancer.get_home_current_soc()
            ev_target = self.priority_balancer.get_ev_target_for_today()
            home_target = self.priority_balancer.get_home_target_for_today()
            pv_forecast = await self._get_pv_forecast()

            self.logger.info(f"   EV SOC: {ev_soc}%")
            self.logger.info(f"   EV Target (today): {ev_target}%")
            self.logger.info(f"   Home Battery SOC: {home_soc}%")
            self.logger.info(f"   Home Battery Target (today): {home_target}%")
            self.logger.info(f"   Home Battery Min SOC: {self._get_home_battery_min_soc()}%")
            self.logger.info(f"   PV Forecast (tomorrow): {pv_forecast} kWh")

            # Charger status
            charger_status = state_helper.get_state(self.hass, self._charger_status)
            charger_amperage = state_helper.get_int(self.hass, self._charger_current, default=0)
            self.logger.info(f"   Charger Status: {charger_status}")
            self.logger.info(f"   Charger Current Amperage: {charger_amperage}A")

            # Priority Balancer state
            priority_enabled = self.priority_balancer.is_enabled()
            priority_state = self.priority_balancer.get_current_priority() if priority_enabled else "N/A"
            self.logger.info(f"   Priority Balancer Enabled: {priority_enabled}")
            self.logger.info(f"   Priority State: {priority_state}")

            # Active session state
            self.logger.info(f"   Active Night Charge Session: {self.is_active()}")
            self.logger.info(f"   Active Mode: {self._active_mode}")

            self.logger.separator()

            # v1.4.10: Enhanced pre-flight check with car_ready emergency override
            car_ready_today = self._get_car_ready_for_today()
            ev_target_entity = self.priority_balancer._ev_min_soc_entities.get(today)

            # EMERGENCY OVERRIDE: When car_ready=True, bypass validation and force charge
            if car_ready_today:
                self.logger.warning(
                    f"{self.logger.ALERT} car_ready=True detected - PRIORITY: Ensure car is charged"
                )
    
                # Only check ABSOLUTE essentials (control entities must exist)
                if not self._charger_switch:
                    self.logger.error("❌ CRITICAL: Charger switch entity not configured - cannot charge")
                    return
    
                if not self._charger_current:
                    self.logger.error("❌ CRITICAL: Charger amperage entity not configured - cannot charge")
                    return
    
                # Check if control entities are available (not the sensors, the control entities)
                switch_state = self.hass.states.get(self._charger_switch)
                current_state = self.hass.states.get(self._charger_current)
    
                if not switch_state:
                    self.logger.error(
                        f"❌ CRITICAL: Charger switch entity unavailable: {self._charger_switch}"
                    )
                    return
    
                if not current_state:
                    self.logger.error(
                        f"❌ CRITICAL: Charger amperage entity unavailable: {self._charger_current}"
                    )
                    return
    
                # Control entities OK - proceed with emergency charging
                self.logger.success("✅ Essential control entities available")
    
                # Check if monitoring sensors are available (informational only)
                monitoring_sensors = {
                    "Charger Status": self._charger_status,
                    "EV SOC": self.priority_balancer._soc_car,
                    f"EV Target ({today.capitalize()})": ev_target_entity,
                }
    
                unavailable_monitoring = []
                for name, entity_id in monitoring_sensors.items():
                    if entity_id:
                        state = state_helper.get_state(self.hass, entity_id)
                        if state in ["unavailable", "unknown", None]:
                            unavailable_monitoring.append(f"{name}: {entity_id} (state={state})")
    
                if unavailable_monitoring:
                    self.logger.warning("⚠️ Monitoring sensors unavailable (will use defaults):")
                    for item in unavailable_monitoring:
                        self.logger.warning(f"   • {item}")
    
                    # Use emergency charge with defaults
                    await self._emergency_charge_with_defaults()
                    return
                else:
                    self.logger.success("✅ All monitoring sensors available")
                    # Continue with normal logic below
    
            # NORMAL MODE: car_ready=False - use relaxed validation with fallbacks
            else:
                self.logger.info("car_ready=False - using normal validation with fallbacks")
    
                # Check monitoring sensors with fallback logic
                critical_sensors = {
                    "Charger Status": self._charger_status,
                    "EV SOC": self.priority_balancer._soc_car,
                    f"EV Target ({today.capitalize()})": ev_target_entity,
                }
    
                unavailable = []
                for name, entity_id in critical_sensors.items():
                    if entity_id:
                        state = state_helper.get_state(self.hass, entity_id)
                        if state in ["unavailable", "unknown", None]:
                            unavailable.append(f"{name}: {entity_id} (state={state})")
    
                if unavailable:
                    self.logger.warning("⚠️ Monitoring sensors unavailable:")
                    for item in unavailable:
                        self.logger.warning(f"   • {item}")
    
                    # For non-car_ready scenarios, still delay if sensors unavailable
                    # (User doesn't need car urgently, better to wait for sensors)
                    self.logger.warning("car_ready=False - delaying evaluation until sensors available")
                    self.logger.warning("Will retry at next periodic check (1 minute)")
                    self.logger.separator()
                    return
    
            # Step 1: Check if Priority Balancer is enabled
            self.logger.info(f"{self.logger.BALANCE} Step 1: Check Priority Balancer")
    
            if not self.priority_balancer.is_enabled():
                self.logger.warning("Priority Balancer disabled - SKIPPING")
                self.logger.warning("Night Smart Charge requires Priority Balancer to be enabled")
                self.logger.separator()
                return
    
            self.logger.success("Priority Balancer enabled")
    
            # Step 2: Check if charger is connected
            self.logger.info(f"{self.logger.EV} Step 2: Check charger connection")
    
            charger_status = state_helper.get_state(self.hass, self._charger_status)
            self.logger.info(f"   Charger status: {charger_status}")
    
            # v1.3.22: Check for invalid/unavailable states
            if not charger_status or charger_status in ["unavailable", "unknown", CHARGER_STATUS_FREE]:
                if charger_status in ["unavailable", "unknown"]:
                    self.logger.warning(f"{self.logger.ALERT} Charger status sensor {charger_status} - cannot determine connection")
                    reason = f"sensor {charger_status}"
                else:
                    reason = "not connected"
    
                self.logger.skip(f"Charger {reason}")
                self.logger.separator()
                return
    
            self.logger.success("Charger connected")
    
            # Step 3: Check if EV target reached
            self.logger.info(f"{self.logger.EV} Step 3: Check EV target SOC")
    
            ev_target_reached = await self.priority_balancer.is_ev_target_reached()
            ev_soc = await self.priority_balancer.get_ev_current_soc()
            ev_target = self.priority_balancer.get_ev_target_for_today()
    
            self.logger.sensor_value("Current EV SOC", ev_soc, "%")
            self.logger.sensor_value("Target EV SOC", ev_target, "%")
    
            if ev_target_reached:
                self.logger.success(f"EV at or above target ({ev_soc}% >= {ev_target}%)")
                self.logger.info("No charging needed")
    
                # If we were charging, mark as complete
                if self.is_active():
                    self.logger.info("Completing active night charge session")
                    await self._complete_night_charge(STOP_REASON_EV_TARGET, terminal=True)
    
                self.logger.separator()
                return
    
            self.logger.info(f"{self.logger.ACTION} EV below target ({ev_soc}% < {ev_target}%) - CHARGING NEEDED")
    
            # Step 4: Evaluate energy source
            self.logger.info(f"{self.logger.SOLAR} Step 4: Evaluate energy source")
    
            pv_forecast = await self._get_pv_forecast()
            threshold = self._get_solar_threshold()
    
            self.logger.sensor_value("PV Forecast", pv_forecast, "kWh")
            self.logger.sensor_value("Threshold", threshold, "kWh")
    
            # Step 5: Decide charging mode
            self.logger.info(f"{self.logger.DECISION} Step 5: Decide charging mode")
    
            if pv_forecast >= threshold:
                self.logger.decision(
                    "Charging mode",
                    "BATTERY MODE",
                    f"Good solar forecast ({pv_forecast} kWh >= {threshold} kWh)"
                )
                await self._start_battery_charge(pv_forecast)
            else:
                self.logger.decision(
                    "Charging mode",
                    "GRID MODE",
                    f"Low/no solar forecast ({pv_forecast} kWh < {threshold} kWh)"
                )
                await self._start_grid_charge(pv_forecast)

        except AttributeError as ex:
            # v1.4.11: Catch missing attribute errors (e.g., self._charger_switch)
            self.logger.error(f"❌ CRITICAL: Missing attribute during evaluation: {ex}")
            self.logger.error("This indicates a configuration error or incomplete initialization")
            self._night_charge_active = False
            self._active_mode = NIGHT_CHARGE_MODE_IDLE
            raise  # Re-raise to surface the error

        except Exception as ex:
            # v1.4.11: Catch all other exceptions to prevent silent failures
            self.logger.error(f"❌ FATAL: Unexpected error in evaluate_and_charge: {ex}")
            self.logger.error("Stack trace:", exc_info=True)
            self._night_charge_active = False
            self._active_mode = NIGHT_CHARGE_MODE_IDLE
            raise

    # ========== BATTERY CHARGE MODE ==========

    async def _start_battery_charge(self, pv_forecast: float) -> None:
        """Start charging using home battery at configured amperage with continuous monitoring."""
        self.logger.separator()
        self.logger.start(f"{self.logger.BATTERY} Battery charge mode")

        amperage = self._get_night_charge_amperage()
        home_min_soc = self._get_home_battery_min_soc()
        ev_target = self.priority_balancer.get_ev_target_for_today()
        threshold = self._get_solar_threshold()

        # ========== PRE-CHECK: Home Battery SOC (v1.3.13+) ==========
        self.logger.info(f"{self.logger.BATTERY} Pre-check: Validating home battery SOC...")
        home_soc = await self.priority_balancer.get_home_current_soc()

        if home_soc <= home_min_soc:
            # Battery below threshold!
            self.logger.warning(
                f"{self.logger.ALERT} Home battery below threshold: "
                f"{home_soc}% <= {home_min_soc}%"
            )

            # Check car_ready flag for today
            car_ready_today = self._get_car_ready_for_today()

            if car_ready_today:
                # Car needed → Fallback to GRID
                self.logger.warning(
                    f"{self.logger.CAR} Car ready flag is ON for today → "
                    f"Fallback to GRID MODE to ensure EV is ready in the morning"
                )
                await self._start_grid_charge(pv_forecast)
                return
            else:
                # Car not needed → SKIP
                self.logger.info(
                    f"{self.logger.CAR} Car ready flag is OFF for today → "
                    f"Skipping night charge, will rely on tomorrow's solar surplus"
                )
                self.logger.info("Night charge session cancelled (waiting for solar)")
                self.logger.separator()
                return

        self.logger.success(f"Home battery SOC check passed: {home_soc}% > {home_min_soc}%")
        # ========== END PRE-CHECK ==========

        self.logger.info(f"   Charger amperage: {amperage}A")
        self.logger.info(f"   EV target SOC: {ev_target}%")
        self.logger.info(f"   Home battery minimum SOC: {home_min_soc}%")

        if not await self._acquire_control("turn_on", "Night charge - Battery mode"):
            self.logger.warning("Night Smart Charge battery start blocked by coordinator")
            self.logger.separator()
            return

        # Start charger with exception handling and state cleanup (v1.3.21)
        try:
            # Set internal state BEFORE starting charger to prevent race condition with Smart Blocker
            # The Smart Blocker listens to the switch turn_on event, so we must be "active" before that happens.
            self._night_charge_active = True
            self._active_mode = NIGHT_CHARGE_MODE_BATTERY

            # Calcola e salva energy forecast (non bloccante) (v1.4.8+)
            await self._calculate_and_save_energy_forecast(NIGHT_CHARGE_MODE_BATTERY)

            # Start charger with specified amperage
            await self.charger_controller.start_charger(amperage, "Night charge - Battery mode")

            # Send mobile notification with safety logging (v1.3.20, v1.3.21 exception handling)
            try:
                current_time = dt_util.now()
                scheduled_time = self._get_night_charge_time()
                self.logger.info(f"📱 Preparing to send BATTERY mode notification at {current_time.strftime('%H:%M:%S')}")
                self.logger.info(f"   Window check: scheduled_time={scheduled_time}, current={current_time.strftime('%H:%M')}")

                reason = (
                    f"Sufficient solar forecast ({pv_forecast:.1f} kWh >= {threshold} kWh)"
                )
                await self._mobile_notifier.send_night_charge_notification(
                    mode=NIGHT_CHARGE_MODE_BATTERY,
                    reason=reason,
                    amperage=amperage,
                    forecast=pv_forecast
                )
            except Exception as ex:
                self.logger.warning(f"Notification logging failed (non-critical): {ex}")

            # Start continuous battery monitoring (every 15 seconds for faster protection)
            if self._battery_monitor_unsub:
                self._battery_monitor_unsub()  # Cancel existing monitor if any

            self._battery_monitor_unsub = async_track_time_interval(
                self.hass,
                self._async_monitor_battery_charge,
                timedelta(seconds=15),
            )

            self.logger.success("Battery charge started successfully")
            self.logger.info("Monitoring: Continuous (every 15 seconds)")
            self.logger.info("Will stop when:")
            self.logger.info(f"  1. EV reaches target SOC ({ev_target}%)")
            self.logger.info(f"  2. Home battery reaches minimum SOC ({home_min_soc}%)")
            self.logger.info("  3. Sunrise occurs")
            self.logger.separator()

        except Exception as ex:
            # Critical failure during battery charge start - cleanup state (v1.3.21)
            self.logger.error(f"Failed to start battery charge: {ex}")

            # Cleanup internal state
            self._night_charge_active = False
            self._active_mode = NIGHT_CHARGE_MODE_IDLE

            # Cancel any monitoring timers
            if self._battery_monitor_unsub:
                self._battery_monitor_unsub()
                self._battery_monitor_unsub = None

            self._release_control(f"Battery start failed: {ex}")
            self.logger.error("Battery charge start aborted - state cleaned up")
            self.logger.separator()
            raise  # Re-raise to allow caller to handle

    @callback
    async def _async_monitor_battery_charge(self, now) -> None:
        """
        Monitor battery charge with dynamic amperage management (v1.3.23).

        Runs every 15 seconds to check:
        - Stop conditions (deadline, home battery min, EV target)
        - Grid import protection (reduce amperage if importing)
        - Amperage recovery (increase when conditions improve)
        """
        # Only monitor if battery mode is active
        if not self.is_active() or self._active_mode != NIGHT_CHARGE_MODE_BATTERY:
            return

        if self._boost_charge and self._boost_charge.is_active():
            return

        if not await self._ensure_control("battery_monitor"):
            return

        current_time = dt_util.now()
        self.logger.separator()
        self.logger.info(f"{self.logger.BATTERY} Battery monitoring at {current_time.strftime('%H:%M:%S')}")

        # Check 0: Car ready deadline / sunrise (v1.3.18)
        should_stop, reason = await self._should_stop_for_deadline(current_time)
        if should_stop:
            self.logger.info(f"{self.logger.CALENDAR} Stop condition: {reason}")
            if await self._stop_charger_with_control(reason):
                await self._complete_night_charge(STOP_REASON_DEADLINE_OR_TARGET, terminal=True)
            return

        # Check 1: Home battery SOC threshold
        home_soc = await self.priority_balancer.get_home_current_soc()
        home_min = self._get_home_battery_min_soc()

        self.logger.sensor_value(f"{self.logger.HOME} Home Battery SOC", home_soc, "%")
        self.logger.sensor_value("   Minimum threshold", home_min, "%")

        if home_soc <= home_min:
            self.logger.warning(f"{self.logger.STOP} Home battery threshold reached!")
            self.logger.warning(f"   Current: {home_soc}% <= Minimum: {home_min}%")
            car_ready_today = self._get_car_ready_for_today()

            if car_ready_today:
                self.logger.warning("   Car ready is ON - switching to GRID fallback")

                # Stop battery monitor before transition to avoid overlapping callbacks.
                if self._battery_monitor_unsub:
                    self._battery_monitor_unsub()
                    self._battery_monitor_unsub = None

                await self._stop_charger_with_control(
                    f"Battery min reached ({home_soc}% <= {home_min}%) - switching to grid"
                )

                try:
                    pv_forecast = await self._get_pv_forecast()
                    await self._start_grid_charge(pv_forecast)
                    self.logger.success("Battery→Grid fallback completed successfully")
                except Exception as ex:
                    self.logger.error(f"Grid fallback failed after battery threshold stop: {ex}")
                    await self._complete_night_charge(STOP_REASON_GRID_FALLBACK_FAILED, terminal=True)
                return

            self.logger.warning("   Car ready is OFF - stopping session to protect home battery")
            await self._stop_charger_with_control(
                f"Home battery protection ({home_soc}% <= {home_min}%)"
            )
            await self._complete_night_charge(STOP_REASON_HOME_BATTERY_MIN, terminal=True)
            return

        self.logger.success(f"Home battery above minimum ({home_soc}% > {home_min}%)")

        # Check 2: EV SOC target (via Priority Balancer)
        ev_target_reached = await self.priority_balancer.is_ev_target_reached()
        ev_soc = await self.priority_balancer.get_ev_current_soc()
        ev_target = self.priority_balancer.get_ev_target_for_today()

        self.logger.sensor_value(f"{self.logger.EV} EV Battery SOC", ev_soc, "%")
        self.logger.sensor_value("   Target", ev_target, "%")

        if ev_target_reached:
            self.logger.success(f"{self.logger.SUCCESS} EV target reached!")
            self.logger.info(f"   Current: {ev_soc}% >= Target: {ev_target}%")
            self.logger.warning("Target hard cap enforced [night_smart_charge:battery_monitor]")
            await self._stop_charger_with_control(
                f"Target hard cap enforced (Night Smart Charge battery): {ev_soc}% >= {ev_target}%"
            )
            await self._complete_night_charge(STOP_REASON_EV_TARGET, terminal=True)
            return

        self.logger.info(f"   {self.logger.ACTION} EV below target ({ev_soc}% < {ev_target}%) - continuing charge")

        # Check 3: Dynamic amperage management (v1.3.23)
        await self._handle_dynamic_amperage()

        self.logger.info("Monitoring will continue...")
        self.logger.separator()

    @callback
    async def _async_monitor_grid_charge(self, now) -> None:
        """
        Monitor grid charge and enforce stop conditions (runs every 15 seconds).

        New in v1.3.17: GRID mode now has monitoring loop to check:
        - Sunrise termination
        - EV target SOC reached
        - Charger status validation
        """
        # Only monitor if grid mode is active
        if not self.is_active() or self._active_mode != NIGHT_CHARGE_MODE_GRID:
            return

        if self._boost_charge and self._boost_charge.is_active():
            return

        if not await self._ensure_control("grid_monitor"):
            return

        current_time = dt_util.now()
        self.logger.separator()
        self.logger.info(f"{self.logger.GRID} Grid monitoring at {current_time.strftime('%H:%M:%S')}")

        # Check 0: Car ready deadline / sunrise (v1.3.18)
        should_stop, reason = await self._should_stop_for_deadline(current_time)
        if should_stop:
            self.logger.info(f"{self.logger.CALENDAR} Stop condition: {reason}")
            if await self._stop_charger_with_control(reason):
                await self._complete_night_charge(STOP_REASON_DEADLINE_OR_TARGET, terminal=True)
            return

        # Check 1: EV target SOC reached
        ev_target_reached = await self.priority_balancer.is_ev_target_reached()
        ev_soc = await self.priority_balancer.get_ev_current_soc()
        ev_target = self.priority_balancer.get_ev_target_for_today()

        self.logger.sensor_value(f"{self.logger.EV} EV Battery SOC", ev_soc, "%")
        self.logger.sensor_value("   Target", ev_target, "%")

        if ev_target_reached:
            self.logger.success(f"{self.logger.SUCCESS} EV target reached!")
            self.logger.info(f"   Current: {ev_soc}% >= Target: {ev_target}%")
            self.logger.warning("Target hard cap enforced [night_smart_charge:grid_monitor]")
            await self._stop_charger_with_control(
                f"Target hard cap enforced (Night Smart Charge grid): {ev_soc}% >= {ev_target}%"
            )
            await self._complete_night_charge(STOP_REASON_EV_TARGET, terminal=True)
            return

        self.logger.info(f"   {self.logger.ACTION} EV below target ({ev_soc}% < {ev_target}%) - continuing charge")

        # Check 2: Validate charger still charging
        charger_status = state_helper.get_state(self.hass, self._charger_status)

        if charger_status != CHARGER_STATUS_CHARGING:
            self.logger.warning(f"Charger no longer charging (status: {charger_status}) - ending grid mode")
            await self._complete_night_charge(STOP_REASON_CHARGER_NOT_CHARGING, terminal=True)
            return

        self.logger.info("Monitoring will continue...")
        self.logger.separator()

    # ========== GRID CHARGE MODE ==========

    async def _start_grid_charge(self, pv_forecast: float) -> None:
        """Start charging from grid at configured amperage."""
        self.logger.separator()
        self.logger.start(f"{self.logger.GRID} Grid charge mode")

        amperage = self._get_night_charge_amperage()
        ev_target = self.priority_balancer.get_ev_target_for_today()
        threshold = self._get_solar_threshold()

        self.logger.info(f"   Charger amperage: {amperage}A")
        self.logger.info(f"   EV target SOC: {ev_target}%")

        if not await self._acquire_control("turn_on", "Night charge - Grid mode"):
            self.logger.warning("Night Smart Charge grid start blocked by coordinator")
            self.logger.separator()
            return

        # Start charger with exception handling and state cleanup (v1.3.21)
        try:
            # Set internal state BEFORE starting charger to prevent race condition with Smart Blocker
            # The Smart Blocker listens to the switch turn_on event, so we must be "active" before that happens.
            self._night_charge_active = True
            self._active_mode = NIGHT_CHARGE_MODE_GRID

            # Calcola e salva energy forecast (non bloccante) (v1.4.8+)
            await self._calculate_and_save_energy_forecast(NIGHT_CHARGE_MODE_GRID)

            # Start charger with specified amperage
            await self.charger_controller.start_charger(amperage, "Night charge - Grid mode")

            # Send mobile notification with safety logging (v1.3.20, v1.3.21 exception handling)
            try:
                current_time = dt_util.now()
                scheduled_time = self._get_night_charge_time()
                self.logger.info(f"📱 Preparing to send GRID mode notification at {current_time.strftime('%H:%M:%S')}")
                self.logger.info(f"   Window check: scheduled_time={scheduled_time}, current={current_time.strftime('%H:%M')}")

                reason = (
                    f"Insufficient solar forecast ({pv_forecast:.1f} kWh < {threshold} kWh)"
                )
                await self._mobile_notifier.send_night_charge_notification(
                    mode=NIGHT_CHARGE_MODE_GRID,
                    reason=reason,
                    amperage=amperage,
                    forecast=pv_forecast
                )
            except Exception as ex:
                self.logger.warning(f"Notification logging failed (non-critical): {ex}")

            # Start continuous grid monitoring (v1.3.17 - NEW)
            if self._grid_monitor_unsub:
                self._grid_monitor_unsub()  # Cancel existing monitor if any

            self._grid_monitor_unsub = async_track_time_interval(
                self.hass,
                self._async_monitor_grid_charge,
                timedelta(seconds=15),
            )

            self.logger.success("Grid charge started successfully")
            self.logger.info("Monitoring: Continuous (every 15 seconds)")
            self.logger.info("Will stop when:")
            self.logger.info(f"  1. EV reaches target SOC ({ev_target}%)")
            self.logger.info("  2. Sunrise occurs")
            self.logger.info("Grid import detection is disabled for night charging")
            self.logger.separator()

        except Exception as ex:
            # Critical failure during grid charge start - cleanup state (v1.3.21)
            self.logger.error(f"Failed to start grid charge: {ex}")

            # Cleanup internal state
            self._night_charge_active = False
            self._active_mode = NIGHT_CHARGE_MODE_IDLE

            # Cancel any monitoring timers
            if self._grid_monitor_unsub:
                self._grid_monitor_unsub()
                self._grid_monitor_unsub = None

            self._release_control(f"Grid start failed: {ex}")
            self.logger.error("Grid charge start aborted - state cleaned up")
            self.logger.separator()
            raise  # Re-raise to allow caller to handle

    # ========== DYNAMIC AMPERAGE MANAGEMENT (v1.3.23) ==========

    async def _handle_dynamic_amperage(self) -> None:
        """
        Handle dynamic amperage adjustments during BATTERY mode.

        Logic:
        1. Check grid import (reduce if importing from grid)
        2. Check recovery conditions (increase if stable and below target)

        Uses ChargerController convenience methods:
        - adjust_for_grid_import() - Gradual reduction
        - recover_to_target() - Gradual recovery
        """
        from .utils.amperage_helper import GridImportProtection

        # Get current amperage
        if not await self._ensure_control("dynamic_amperage"):
            return

        current_amps = await self.charger_controller.get_current_amperage()
        if current_amps is None:
            self.logger.warning("Cannot read current amperage, skipping dynamic adjustment")
            return

        # Get configuration
        target_amps = self._get_night_charge_amperage()
        grid_threshold = self._get_grid_import_threshold()
        grid_delay = self._get_grid_import_delay()

        # Read grid import
        grid_import = state_helper.get_float(self.hass, self._grid_import, default=0.0)

        self.logger.info(f"{self.logger.CHARGER} Dynamic amperage check:")
        self.logger.info(f"   Current: {current_amps}A, Target: {target_amps}A")
        self.logger.info(f"   Grid import: {grid_import:.0f}W (threshold: {grid_threshold:.0f}W)")

        # STEP 1: Check grid import protection (REDUCTION)
        should_reduce = GridImportProtection.should_reduce(
            grid_import=grid_import,
            threshold=grid_threshold,
            delay_seconds=grid_delay,
            last_trigger_time=self._grid_import_trigger_time,
        )

        if should_reduce:
            # First detection or delay elapsed
            if self._grid_import_trigger_time is None:
                # First detection - start tracking
                self._grid_import_trigger_time = datetime.now()
                self.logger.warning(
                    f"{self.logger.ALERT} Grid import detected: {grid_import:.0f}W > {grid_threshold:.0f}W"
                )
                self.logger.info(f"   Waiting {grid_delay}s before reducing amperage...")
                self._recovery_tracker.reset()  # Reset recovery tracker
                return

            # Delay elapsed - reduce amperage
            self.logger.warning(
                f"{self.logger.ALERT} Grid import persistent: {grid_import:.0f}W > {grid_threshold:.0f}W "
                f"({grid_delay}s elapsed)"
            )

            car_ready_today = self._get_car_ready_for_today()
            if not car_ready_today:
                self.logger.warning(
                    "   Car ready is OFF - stopping session to avoid importing from public grid"
                )
                self._grid_import_trigger_time = None
                self._recovery_tracker.reset()

                if await self._stop_charger_with_control(
                    f"Grid import detected with car_ready OFF ({grid_import:.0f}W > {grid_threshold:.0f}W)"
                ):
                    await self._complete_night_charge(
                        STOP_REASON_GRID_IMPORT_CAR_NOT_READY,
                        terminal=True,
                    )
                else:
                    self.logger.error(
                        "Failed to stop charger after persistent grid import with car_ready OFF"
                    )
                return

            result = await self._adjust_for_grid_import_with_control(
                reason=f"Grid import protection ({grid_import:.0f}W > {grid_threshold:.0f}W)"
            )

            if result and result.success:
                self.logger.success(f"Amperage reduced: {current_amps}A → {result.amperage}A")
                self._grid_import_trigger_time = None  # Reset for next detection
                self._recovery_tracker.reset()  # Reset recovery tracker
            elif result is not None:
                self.logger.error(f"Failed to reduce amperage: {result.error_message}")

            return

        # Grid import normal - reset trigger
        if self._grid_import_trigger_time is not None:
            self.logger.info(f"   Grid import cleared (was above threshold)")
            self._grid_import_trigger_time = None

        # STEP 2: Check recovery conditions (INCREASE)
        if current_amps >= target_amps:
            # Already at target
            self.logger.info(f"   At target amperage ({current_amps}A)")
            self._recovery_tracker.reset()
            return

        # Check if conditions allow recovery
        can_recover = GridImportProtection.should_recover(
            grid_import=grid_import,
            threshold=grid_threshold,
            hysteresis_factor=0.5,  # Recover at 50% of threshold
        )

        if not can_recover:
            recovery_threshold = grid_threshold * 0.5
            self.logger.info(
                f"   Cannot recover yet: grid {grid_import:.0f}W >= {recovery_threshold:.0f}W "
                f"(50% threshold)"
            )
            self._recovery_tracker.reset()
            return

        # Conditions good - track stability (60s required)
        self._recovery_tracker.start_tracking()
        elapsed = self._recovery_tracker.get_elapsed()

        if not self._recovery_tracker.is_stable(60):
            self.logger.info(
                f"   Recovery conditions stable for {elapsed:.0f}s (need 60s for cloud protection)"
            )
            return

        # Stable for 60s - recover one level
        self.logger.info(
            f"{self.logger.SUCCESS} Conditions stable for 60s, recovering amperage..."
        )

        result = await self._recover_to_target_with_control(
            target_amps,
            reason=f"Conditions improved (grid {grid_import:.0f}W, stable 60s)"
        )

        if result and result.success:
            self.logger.success(
                f"Amperage recovered: {current_amps}A → {result.amperage}A (target {target_amps}A)"
            )
            self._recovery_tracker.reset()  # Reset for next recovery cycle
        elif result is not None:
            self.logger.error(f"Failed to recover amperage: {result.error_message}")

    # ========== SESSION COMPLETION ==========

    def _is_terminal_stop_reason(self, stop_reason: str) -> bool:
        """Return True when a stop reason should lock the day as completed."""
        terminal_reasons = {
            STOP_REASON_DEADLINE_OR_TARGET,
            STOP_REASON_HOME_BATTERY_MIN,
            STOP_REASON_EV_TARGET,
            STOP_REASON_CHARGER_NOT_CHARGING,
            STOP_REASON_GRID_FALLBACK_FAILED,
            STOP_REASON_GRID_IMPORT_CAR_NOT_READY,
        }
        non_terminal_reasons = {
            STOP_REASON_BOOST_PREEMPTED,
        }

        if stop_reason in terminal_reasons:
            return True
        if stop_reason in non_terminal_reasons:
            return False

        # Safety default: unknown reason is treated as terminal.
        self.logger.warning(f"Unknown stop reason '{stop_reason}' - defaulting to terminal completion")
        return True

    async def _complete_night_charge(self, stop_reason: str, terminal: bool | None = None) -> None:
        """Complete night charge and clean up session state."""
        if terminal is None:
            terminal = self._is_terminal_stop_reason(stop_reason)

        self.logger.separator()
        self.logger.info(f"{self.logger.SUCCESS} Completing night charge session")
        self.logger.info(f"   Stop reason: {stop_reason}")
        self.logger.info(f"   Terminal completion: {terminal}")

        # Stop battery monitoring if active
        if self._battery_monitor_unsub:
            self._battery_monitor_unsub()
            self._battery_monitor_unsub = None
            self.logger.info("Battery monitoring stopped")

        # Stop grid monitoring if active (v1.3.17)
        if self._grid_monitor_unsub:
            self._grid_monitor_unsub()
            self._grid_monitor_unsub = None
            self.logger.info("Grid monitoring stopped")

        # Boost Charge can preempt Night Smart Charge while a monitor callback is already
        # running. In that race, this cleanup must not mark the night session as completed
        # or enable cooldown, otherwise Solar Surplus will be skipped after Boost ends.
        if self._boost_charge and self._boost_charge.is_active():
            previous_mode = self._active_mode
            self._night_charge_active = False
            self._active_mode = NIGHT_CHARGE_MODE_IDLE
            self._session_state = "ready"
            self._release_control(STOP_REASON_BOOST_PREEMPTED)
            self.logger.info("Boost Charge override detected during completion - clearing state without cooldown")
            self.logger.info(f"   Previous mode: {previous_mode}")
            self.logger.separator()
            return

        # Reset state flags
        previous_mode = self._active_mode
        self._night_charge_active = False
        self._active_mode = NIGHT_CHARGE_MODE_IDLE

        if terminal:
            # Track completion time for cooldown only on terminal stop reasons.
            self._last_completion_time = dt_util.now()
            self._last_completion_date = self._last_completion_time.date()
            self.logger.info(f"Completion time recorded: {self._last_completion_time.strftime('%H:%M:%S')}")

            self._session_state = "completed_today"
            self.logger.info(f"Session state: {self._session_state}")

            self.logger.success("Session completed (terminal)")
            self.logger.info(f"   Previous mode: {previous_mode}")
            self.logger.info(f"   Completion date: {self._last_completion_date}")
            self.logger.info("   1-hour cooldown period active")
            self.logger.info("   Will not re-activate today")
            self.logger.info("   Smart Blocker will resume normal operation")
        else:
            self._session_state = "ready"
            self._last_completion_time = None
            self._last_completion_date = None
            self.logger.success("Session completed (non-terminal)")
            self.logger.info(f"   Previous mode: {previous_mode}")
            self.logger.info("   State reset to ready (no daily lock)")
        self._release_control(stop_reason)
        self.logger.separator()

    async def _emergency_charge_with_defaults(self) -> None:
        """
        Emergency charging mode when car_ready=True and sensors unavailable (v1.4.10).

        Uses safe defaults and bypasses normal validation to GUARANTEE charging.

        This is triggered when:
        - car_ready=True (car needed for morning)
        - Critical sensors unavailable
        - We MUST charge regardless of sensor issues
        """
        self.logger.separator()
        self.logger.warning(f"{self.logger.ALERT} 🚨 EMERGENCY CHARGE MODE ACTIVATED 🚨")
        self.logger.warning("car_ready=True - Charging MUST proceed despite sensor issues")
        self.logger.separator()

        # Get amperage from config (with fallback)
        amperage = self._get_night_charge_amperage()
        if not amperage or amperage < 6:
            amperage = 16  # Safe default
            self.logger.warning(f"Using default amperage: {amperage}A")

        # Determine mode: prefer BATTERY if forecast good, else GRID
        pv_forecast = 0.0
        try:
            pv_forecast = await self._get_pv_forecast()
            solar_threshold = self._get_solar_threshold()

            if pv_forecast and solar_threshold and pv_forecast >= solar_threshold:
                self.logger.info(
                    f"PV forecast sufficient ({pv_forecast} >= {solar_threshold} kWh) - "
                    f"attempting BATTERY mode"
                )
                mode = NIGHT_CHARGE_MODE_BATTERY
            else:
                self.logger.info(
                    f"PV forecast insufficient or unavailable - using GRID mode"
                )
                mode = NIGHT_CHARGE_MODE_GRID
        except Exception as ex:
            self.logger.warning(f"Could not determine PV forecast: {ex} - defaulting to GRID mode")
            mode = NIGHT_CHARGE_MODE_GRID

        # Start charging with determined mode
        try:
            if mode == NIGHT_CHARGE_MODE_BATTERY:
                await self._start_battery_charge(pv_forecast)
            else:
                await self._start_grid_charge(pv_forecast)

            self.logger.success("Emergency charge started successfully")
        except Exception as ex:
            self.logger.error(f"Emergency charge failed: {ex}")
            # Try GRID mode as last resort if BATTERY failed
            if mode == NIGHT_CHARGE_MODE_BATTERY:
                self.logger.warning("Retrying with GRID mode as fallback")
                try:
                    await self._start_grid_charge(pv_forecast)
                    self.logger.success("Emergency charge started (GRID fallback)")
                except Exception as ex2:
                    self.logger.error(f"GRID fallback also failed: {ex2}")
                    raise

    # ========== HELPER METHODS ==========

    async def _get_pv_forecast(self) -> float:
        """Get PV forecast value from configured entity."""
        if not self._pv_forecast_entity:
            self.logger.warning("No PV forecast entity configured - fallback to 0 kWh")
            return 0.0

        pv_state = state_helper.get_state(self.hass, self._pv_forecast_entity)

        if not pv_state or pv_state in ["unknown", "unavailable"]:
            self.logger.warning("PV forecast entity unavailable - fallback to 0 kWh")
            return 0.0

        try:
            value = float(pv_state)
            self.logger.debug(f"PV forecast retrieved: {value} kWh")
            return value
        except (ValueError, TypeError):
            self.logger.error(f"PV forecast invalid value: {pv_state} - fallback to 0 kWh")
            return 0.0

    def _get_solar_threshold(self) -> float:
        """Get solar forecast threshold."""
        return state_helper.get_float(
            self.hass,
            self._solar_forecast_threshold_entity,
            20.0
        )

    def _get_night_charge_amperage(self) -> int:
        """Get configured night charge amperage."""
        return state_helper.get_int(
            self.hass,
            self._night_charge_amperage_entity,
            16
        )

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

    def _get_home_battery_min_soc(self) -> float:
        """Get home battery minimum SOC."""
        return state_helper.get_float(
            self.hass,
            self._home_battery_min_soc_entity,
            20.0
        )

    def _get_grid_import_threshold(self) -> float:
        """Get grid import threshold (v1.3.23)."""
        return state_helper.get_float(
            self.hass,
            self._grid_import_threshold_entity,
            50.0
        )

    def _get_grid_import_delay(self) -> int:
        """Get grid import protection delay in seconds (v1.3.23)."""
        return state_helper.get_int(
            self.hass,
            self._grid_import_delay_entity,
            30
        )

    def _get_scheduled_time_for_today(self, now: datetime, time_str: str) -> datetime:
        """
        Get scheduled time for TODAY (not next occurrence).

        This is the correct function for window checks, which need to know
        if we're past the scheduled time TODAY, not when the next occurrence will be.

        Args:
            now: Current datetime
            time_str: Time string in "HH:MM:SS" format

        Returns:
            Datetime for TODAY at the scheduled time

        Example:
            At 01:00:33 with scheduled time "01:00:00":
            - Returns: 2025-11-20 01:00:00 (TODAY)
            - NOT: 2025-11-21 01:00:00 (tomorrow)
        """
        return TimeParsingService.time_string_to_datetime(time_str, now)

    def _cooldown_expired(self, now: datetime) -> bool:
        """
        Check if cooldown period has expired (v1.4.4).

        Args:
            now: Current datetime

        Returns:
            True if cooldown expired or not active
        """
        if not self._last_completion_time:
            return True

        from .const import NIGHT_CHARGE_COOLDOWN_SECONDS
        elapsed = (now - self._last_completion_time).total_seconds()
        return elapsed >= NIGHT_CHARGE_COOLDOWN_SECONDS

    def _get_car_ready_for_today(self) -> bool:
        """
        Get car_ready flag for current day (v1.3.13+).

        Returns:
            True if car needs to be ready in the morning (use grid as fallback)
            False if car not needed (skip charging, wait for solar)
        """
        # Use HA timezone-aware clock to avoid day mismatches around midnight.
        # This is critical when night charge starts shortly after 00:00.
        current_day = dt_util.now().weekday()

        # Get entity for today
        entity_id = self._car_ready_entities.get(current_day)

        if not entity_id:
            # Fallback: weekday=True, weekend=False
            self.logger.warning(
                f"Car ready entity not found for day {current_day}, "
                f"using default (weekday=True, weekend=False)"
            )
            return current_day < 5  # Monday-Friday = True

        # Get switch state
        car_ready = state_helper.get_bool(self.hass, entity_id, default=True)

        day_names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        day_name = day_names[current_day]
        self.logger.info(f"{self.logger.CALENDAR} Car ready flag for {day_name}: {car_ready}")

        return car_ready

    def _get_car_ready_time(self) -> datetime:
        """
        Get car ready deadline time for today (v1.3.18+).

        Returns:
            datetime: Today at the configured car ready time
        """
        time_state = state_helper.get_state(self.hass, self._car_ready_time_entity)
        if not time_state or time_state in ("unknown", "unavailable"):
            time_state = DEFAULT_CAR_READY_TIME

        # Convert to datetime (today at specified time)
        now = dt_util.now()
        time_parts = time_state.split(":")
        car_ready_time = now.replace(
            hour=int(time_parts[0]),
            minute=int(time_parts[1]),
            second=int(time_parts[2]) if len(time_parts) > 2 else 0,
            microsecond=0
        )
        return car_ready_time

    async def _should_stop_for_deadline(self, current_time: datetime) -> tuple[bool, str]:
        """
        Check if charging should stop based on car ready configuration (v1.3.18+).

        Logic:
        - If car_ready=ON: Continue past sunrise until min(ev_target, deadline)
        - If car_ready=OFF: Stop at sunrise (v1.3.17 behavior)

        Args:
            current_time: Current datetime to check against

        Returns:
            (should_stop, reason) tuple
        """
        car_ready_today = self._get_car_ready_for_today()

        if car_ready_today:
            # Car needed - check deadline first
            car_ready_time = self._get_car_ready_time()

            if current_time >= car_ready_time:
                # Past deadline - stop immediately
                return True, f"Car ready deadline reached ({car_ready_time.strftime('%H:%M')})"

            # Before deadline - check EV target
            ev_target_reached = await self.priority_balancer.is_ev_target_reached()
            if ev_target_reached:
                return True, "EV target reached"

            # Before deadline + target not reached - CONTINUE
            return False, ""
        else:
            # Car not needed - stop at sunrise
            sunrise = self._astral_service.get_next_sunrise_after(current_time)
            if current_time >= sunrise:
                return True, "Sunrise reached (car not needed urgently)"

            return False, ""

    async def _calculate_and_save_energy_forecast(self, mode: str) -> None:
        """
        Calcola la previsione energetica e salva nel sensore target (v1.4.8+).

        Formula: Energia (kWh) = (Target SOC % - Current SOC %) × Capacità Batteria (kWh) / 100

        Args:
            mode: Modalità di ricarica (BATTERY o GRID) per logging
        """
        # Controlla se la funzionalità è configurata
        battery_capacity = self.config.get(CONF_BATTERY_CAPACITY)
        energy_target_entity = self.config.get(CONF_ENERGY_FORECAST_TARGET)

        if not battery_capacity or not energy_target_entity:
            self.logger.debug(
                "Energy forecast non configurato (battery_capacity o sensore target mancante), skip"
            )
            return

        try:
            # Ottieni SOC corrente e target
            current_soc = await self.priority_balancer.get_ev_current_soc()
            target_soc = self.priority_balancer.get_ev_target_for_today()

            if current_soc is None:
                self.logger.warning(
                    "⚠️ Unable to calculate energy forecast: current EV SOC unavailable"
                )
                return

            if target_soc is None:
                self.logger.warning(
                    "⚠️ Unable to calculate energy forecast: target EV SOC unavailable"
                )
                return

            # Calculate required energy
            soc_delta = target_soc - current_soc

            # Gestisci edge cases
            if soc_delta <= 0:
                self.logger.info(
                    f"📊 Energy forecast: EV già al target o sopra "
                    f"(corrente={current_soc}%, target={target_soc}%), imposto 0 kWh"
                )
                energy_required = 0.0
            else:
                energy_required = (soc_delta * battery_capacity) / 100.0

                # Sanity check: required energy must not exceed battery capacity
                if energy_required > battery_capacity:
                    self.logger.warning(
                        f"⚠️ Calculated energy ({energy_required:.2f} kWh) exceeds "
                        f"battery capacity ({battery_capacity} kWh), clamping to capacity"
                    )
                    energy_required = battery_capacity

            # Validate that the target sensor exists
            target_state = self.hass.states.get(energy_target_entity)
            if target_state is None:
                self.logger.warning(
                    f"⚠️ Sensore target energy forecast ({energy_target_entity}) "
                    f"non trovato, impossibile salvare previsione"
                )
                return

            adapter = CurrentControlAdapter(self.hass, energy_target_entity)
            await adapter.async_validate()
            service_domain, service_name, service_data = adapter.build_service_call(
                round(energy_required, 2)
            )
            await self.hass.services.async_call(
                service_domain,
                service_name,
                service_data,
                blocking=True,
            )

            # Log successo
            self.logger.info(
                f"📊 Energy forecast calcolato e salvato: {energy_required:.2f} kWh "
                f"(corrente={current_soc}%, target={target_soc}%, capacità={battery_capacity} kWh)"
            )

        except Exception as ex:
            # Errore non critico, log warning ma non bloccare la ricarica
            self.logger.warning(
                f"⚠️ Errore nel calcolo energy forecast: {ex}. La ricarica procederà normalmente."
            )

    def _log_configuration(self) -> None:
        """Log current configuration."""
        enabled = state_helper.get_bool(self.hass, self._night_charge_enabled_entity) if self._night_charge_enabled_entity else False
        scheduled_time = state_helper.get_state(self.hass, self._night_charge_time_entity) if self._night_charge_time_entity else "Not configured"
        threshold = self._get_solar_threshold()
        amperage = self._get_night_charge_amperage()

        self.logger.info("Configuration:")
        self.logger.info(f"   Enabled: {enabled}")
        self.logger.info(f"   Scheduled Time: {scheduled_time}")
        self.logger.info(f"   Solar Forecast Threshold: {threshold} kWh")
        self.logger.info(f"   Night Charge Amperage: {amperage} A")
        self.logger.info(f"   PV Forecast Entity: {self._pv_forecast_entity or 'Not configured'}")

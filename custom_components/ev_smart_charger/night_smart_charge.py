"""Night Smart Charge automation for EV Smart Charger."""
from __future__ import annotations
from datetime import datetime, timedelta

from homeassistant.core import HomeAssistant, State, callback
from homeassistant.helpers.event import async_track_time_interval, async_track_state_change_event
from homeassistant.util import dt as dt_util

from .const import (
    CONF_EV_CHARGER_STATUS,
    CONF_SOC_HOME,
    CONF_PV_FORECAST,
    CONF_GRID_IMPORT,
    CONF_NOTIFY_SERVICES,
    CONF_CAR_OWNER,
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
)
from .utils.logging_helper import EVSCLogger
from .utils import entity_helper, state_helper
from .utils.mobile_notification_service import MobileNotificationService
from .utils.astral_time_service import AstralTimeService
from .utils.time_parsing_service import TimeParsingService


class NightSmartCharge:
    """Manages Night Smart Charge automation with Priority Balancer integration."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry_id: str,
        config: dict,
        priority_balancer,
        charger_controller,
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
        self.logger = EVSCLogger("NIGHT SMART CHARGE")
        self._astral_service = AstralTimeService(hass)
        self._mobile_notifier = MobileNotificationService(
            hass, config.get(CONF_NOTIFY_SERVICES, []), entry_id, config.get(CONF_CAR_OWNER)
        )

        # User-configured entities
        self._charger_status = config.get(CONF_EV_CHARGER_STATUS)
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

    async def async_setup(self) -> None:
        """Set up Night Smart Charge automation."""
        self.logger.separator()
        self.logger.start("Night Smart Charge initialization")
        self.logger.separator()

        # Discover helper entities (optional for backward compatibility)
        self._night_charge_enabled_entity = entity_helper.find_by_suffix(
            self.hass, HELPER_NIGHT_CHARGE_ENABLED_SUFFIX
        )
        self._night_charge_time_entity = entity_helper.find_by_suffix(
            self.hass, HELPER_NIGHT_CHARGE_TIME_SUFFIX
        )
        self._car_ready_time_entity = entity_helper.find_by_suffix(
            self.hass, HELPER_CAR_READY_TIME_SUFFIX
        )
        self._solar_forecast_threshold_entity = entity_helper.find_by_suffix(
            self.hass, HELPER_MIN_SOLAR_FORECAST_THRESHOLD_SUFFIX
        )
        self._night_charge_amperage_entity = entity_helper.find_by_suffix(
            self.hass, HELPER_NIGHT_CHARGE_AMPERAGE_SUFFIX
        )
        self._home_battery_min_soc_entity = entity_helper.find_by_suffix(
            self.hass, HELPER_HOME_BATTERY_MIN_SOC_SUFFIX
        )
        self._grid_import_threshold_entity = entity_helper.find_by_suffix(
            self.hass, HELPER_GRID_IMPORT_THRESHOLD_SUFFIX
        )
        self._grid_import_delay_entity = entity_helper.find_by_suffix(
            self.hass, HELPER_GRID_IMPORT_DELAY_SUFFIX
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
            entity = entity_helper.find_by_suffix(self.hass, suffix)
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

    # ========== PERIODIC MONITORING ==========

    @callback
    async def _async_periodic_check(self, now) -> None:
        """Periodic check every minute."""
        from .const import NIGHT_CHARGE_COOLDOWN_SECONDS

        current_time = dt_util.now()
        self.logger.debug(f"Periodic check at {current_time.strftime('%H:%M:%S')}")

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
            # Validate stop conditions (deadline/sunrise based on car_ready flag)
            should_stop, reason = await self._should_stop_for_deadline(current_time)
            if should_stop:
                self.logger.warning(
                    f"{self.logger.ALERT} Active session detected past stop condition - terminating"
                )
                await self.charger_controller.stop_charger(reason)
                await self._complete_night_charge()
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
            if await self._is_in_active_window(now) and self.is_enabled():
                self.logger.info("Late arrival detected - running immediate check")
                await self._evaluate_and_charge()

    # ========== ACTIVE WINDOW DETECTION ==========

    async def _is_in_active_window(self, now: datetime) -> bool:
        """
        Check if current time is between scheduled time and sunrise.

        Uses TimeParsingService for time parsing and AstralTimeService for sunrise.

        Logic:
        - Scheduled time is typically after midnight (e.g., 01:00)
        - Active if: now >= scheduled_time AND now < sunrise
        - Handles sunrise calculation for today vs tomorrow

        Args:
            now: Current datetime

        Returns:
            True if in active window
        """
        # Get scheduled time configuration
        if not self._night_charge_time_entity:
            self.logger.warning("Night charge time entity not configured")
            return False

        time_state = state_helper.get_state(self.hass, self._night_charge_time_entity)

        if not time_state or time_state in ("unknown", "unavailable"):
            self.logger.warning("Time entity unavailable for window check")
            return False

        # Parse time string using TimeParsingService
        try:
            scheduled_time = TimeParsingService.time_string_to_next_occurrence(time_state, now)
        except (ValueError, TypeError, IndexError) as e:
            self.logger.error(f"Invalid time configuration: {time_state} - {e}")
            return False

        # Get next sunrise using AstralTimeService
        sunrise = self._astral_service.get_next_sunrise_after(now)

        if not sunrise:
            self.logger.warning("Could not determine sunrise time")
            return False

        # Determine sunrise label for logging
        sunrise_label = "today" if sunrise.date() == now.date() else "tomorrow"

        # Check if we're in the active window
        is_active = now >= scheduled_time and now < sunrise

        # Log detailed window check (throttled to once per minute)
        if self._last_window_check_time is None or (now - self._last_window_check_time).total_seconds() >= 60:
            self.logger.info(f"{self.logger.CALENDAR} Window check:")
            self.logger.info(f"   Current: {now.strftime('%Y-%m-%d %H:%M:%S')}")
            self.logger.info(f"   Scheduled: {scheduled_time.strftime('%Y-%m-%d %H:%M:%S')}")
            self.logger.info(f"   Sunrise ({sunrise_label}): {sunrise.strftime('%Y-%m-%d %H:%M:%S')}")
            self.logger.info(f"   Now >= Scheduled: {now >= scheduled_time}")
            self.logger.info(f"   Now < Sunrise: {now < sunrise}")
            self.logger.info(f"   Window Active: {is_active}")
            self._last_window_check_time = now
        else:
            # For frequent checks (monitoring loops), log at debug level
            self.logger.debug(
                f"Window check: now={now.strftime('%H:%M')}, "
                f"scheduled={scheduled_time.strftime('%H:%M')}, "
                f"sunrise={sunrise.strftime('%H:%M')}, "
                f"active={is_active}"
            )

        return is_active

    # ========== MAIN EVALUATION LOGIC ==========

    async def _evaluate_and_charge(self) -> None:
        """Main decision logic for Night Smart Charge."""
        # v1.4.2: Diagnostic snapshot at evaluation start
        now = dt_util.now()
        today = now.strftime("%A").lower()

        self.logger.separator()
        self.logger.info(f"{self.logger.DECISION} 📊 NIGHT SMART CHARGE - DIAGNOSTIC SNAPSHOT")
        self.logger.info(f"   Timestamp: {now.strftime('%Y-%m-%d %H:%M:%S')}")
        self.logger.info(f"   Day: {today.capitalize()}")
        self.logger.separator()

        # Configuration values
        self.logger.info("⚙️ Configuration:")
        self.logger.info(f"   Night Charge Enabled: {entity_helper.is_entity_on(self.hass, self._enabled_entity) if self._enabled_entity else 'N/A'}")
        self.logger.info(f"   Scheduled Time: {self._get_night_charge_time()}")
        self.logger.info(f"   Night Charge Amperage: {self._get_night_charge_amperage()}A")
        self.logger.info(f"   Solar Forecast Threshold: {self._get_solar_threshold()} kWh")
        self.logger.info(f"   Car Ready Today ({today.capitalize()}): {self._get_car_ready_for_today()}")
        self.logger.info(f"   Car Ready Deadline: {self._get_car_ready_time()}")

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

        # v1.3.22: Pre-flight check for critical sensor availability
        ev_target_entity = self.priority_balancer._ev_min_soc_entities.get(today)

        critical_sensors = {
            "Charger Status": self._charger_status,
            "EV SOC (cached)": self.priority_balancer._soc_car,  # v1.4.0 - show cached sensor
            f"EV Target ({today.capitalize()})": ev_target_entity,
        }

        unavailable = []
        for name, entity_id in critical_sensors.items():
            if entity_id:
                state = state_helper.get_state(self.hass, entity_id)
                if state in ["unavailable", "unknown", None]:
                    unavailable.append(f"{name}: {entity_id} (state={state})")

        if unavailable:
            self.logger.warning("⚠️ Critical sensors unavailable - delaying evaluation:")
            for item in unavailable:
                self.logger.warning(f"   • {item}")
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
                await self._complete_night_charge()

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

        # Start charger with exception handling and state cleanup (v1.3.21)
        try:
            # Start charger with specified amperage
            await self.charger_controller.start_charger(amperage, "Night charge - Battery mode")

            # Set internal state
            self._night_charge_active = True
            self._active_mode = NIGHT_CHARGE_MODE_BATTERY

            # Send mobile notification with safety logging (v1.3.20, v1.3.21 exception handling)
            try:
                current_time = dt_util.now()
                scheduled_time = self._get_night_charge_time()
                self.logger.info(f"📱 Preparing to send BATTERY mode notification at {current_time.strftime('%H:%M:%S')}")
                self.logger.info(f"   Window check: scheduled_time={scheduled_time}, current={current_time.strftime('%H:%M')}")

                reason = f"Previsione solare sufficiente ({pv_forecast:.1f} kWh >= {threshold} kWh)"
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

        current_time = dt_util.now()
        self.logger.separator()
        self.logger.info(f"{self.logger.BATTERY} Battery monitoring at {current_time.strftime('%H:%M:%S')}")

        # Check 0: Car ready deadline / sunrise (v1.3.18)
        should_stop, reason = await self._should_stop_for_deadline(current_time)
        if should_stop:
            self.logger.info(f"{self.logger.CALENDAR} Stop condition: {reason}")
            await self.charger_controller.stop_charger(reason)
            await self._complete_night_charge()
            return

        # Check 1: Home battery SOC threshold
        home_soc = await self.priority_balancer.get_home_current_soc()
        home_min = self._get_home_battery_min_soc()

        self.logger.sensor_value(f"{self.logger.HOME} Home Battery SOC", home_soc, "%")
        self.logger.sensor_value("   Minimum threshold", home_min, "%")

        if home_soc <= home_min:
            self.logger.warning(f"{self.logger.STOP} Home battery threshold reached!")
            self.logger.warning(f"   Current: {home_soc}% <= Minimum: {home_min}%")
            self.logger.warning("   Stopping EV charging to protect home battery")
            await self.charger_controller.stop_charger(f"Home battery protection ({home_soc}% <= {home_min}%)")
            await self._complete_night_charge()
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
            await self.charger_controller.stop_charger(f"EV target SOC reached ({ev_soc}% >= {ev_target}%)")
            await self._complete_night_charge()
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

        current_time = dt_util.now()
        self.logger.separator()
        self.logger.info(f"{self.logger.GRID} Grid monitoring at {current_time.strftime('%H:%M:%S')}")

        # Check 0: Car ready deadline / sunrise (v1.3.18)
        should_stop, reason = await self._should_stop_for_deadline(current_time)
        if should_stop:
            self.logger.info(f"{self.logger.CALENDAR} Stop condition: {reason}")
            await self.charger_controller.stop_charger(reason)
            await self._complete_night_charge()
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
            await self.charger_controller.stop_charger(f"EV target SOC reached ({ev_soc}% >= {ev_target}%)")
            await self._complete_night_charge()
            return

        self.logger.info(f"   {self.logger.ACTION} EV below target ({ev_soc}% < {ev_target}%) - continuing charge")

        # Check 2: Validate charger still charging
        from .const import CHARGER_STATUS_CHARGING
        charger_status = state_helper.get_state(self.hass, self._charger_status)

        if charger_status != CHARGER_STATUS_CHARGING:
            self.logger.warning(f"Charger no longer charging (status: {charger_status}) - ending grid mode")
            await self._complete_night_charge()
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

        # Start charger with exception handling and state cleanup (v1.3.21)
        try:
            # Start charger with specified amperage
            await self.charger_controller.start_charger(amperage, "Night charge - Grid mode")

            # Set internal state
            self._night_charge_active = True
            self._active_mode = NIGHT_CHARGE_MODE_GRID

            # Send mobile notification with safety logging (v1.3.20, v1.3.21 exception handling)
            try:
                current_time = dt_util.now()
                scheduled_time = self._get_night_charge_time()
                self.logger.info(f"📱 Preparing to send GRID mode notification at {current_time.strftime('%H:%M:%S')}")
                self.logger.info(f"   Window check: scheduled_time={scheduled_time}, current={current_time.strftime('%H:%M')}")

                reason = f"Previsione solare insufficiente ({pv_forecast:.1f} kWh < {threshold} kWh)"
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

            result = await self.charger_controller.adjust_for_grid_import(
                reason=f"Grid import protection ({grid_import:.0f}W > {grid_threshold:.0f}W)"
            )

            if result.success:
                self.logger.success(f"Amperage reduced: {current_amps}A → {result.amperage}A")
                self._grid_import_trigger_time = None  # Reset for next detection
                self._recovery_tracker.reset()  # Reset recovery tracker
            else:
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

        result = await self.charger_controller.recover_to_target(
            target_amps=target_amps,
            reason=f"Conditions improved (grid {grid_import:.0f}W, stable 60s)"
        )

        if result.success:
            self.logger.success(
                f"Amperage recovered: {current_amps}A → {result.amperage}A (target {target_amps}A)"
            )
            self._recovery_tracker.reset()  # Reset for next recovery cycle
        else:
            self.logger.error(f"Failed to recover amperage: {result.error_message}")

    # ========== SESSION COMPLETION ==========

    async def _complete_night_charge(self) -> None:
        """Complete night charge and clean up."""
        self.logger.separator()
        self.logger.info(f"{self.logger.SUCCESS} Completing night charge session")

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

        # Track completion time for cooldown
        self._last_completion_time = dt_util.now()
        self.logger.info(f"Completion time recorded: {self._last_completion_time.strftime('%H:%M:%S')}")

        # Reset state flags
        previous_mode = self._active_mode
        self._night_charge_active = False
        self._active_mode = NIGHT_CHARGE_MODE_IDLE

        self.logger.success("Session completed")
        self.logger.info(f"   Previous mode: {previous_mode}")
        self.logger.info("   1-hour cooldown period active")
        self.logger.info("   Smart Blocker will resume normal operation")
        self.logger.separator()

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

    def _get_car_ready_for_today(self) -> bool:
        """
        Get car_ready flag for current day (v1.3.13+).

        Returns:
            True if car needs to be ready in the morning (use grid as fallback)
            False if car not needed (skip charging, wait for solar)
        """
        # Get current day (0=Monday, 6=Sunday)
        current_day = datetime.now().weekday()

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


async def async_setup_night_smart_charge(
    hass: HomeAssistant,
    entry_id: str,
    config: dict,
    priority_balancer,
) -> NightSmartCharge:
    """Set up Night Smart Charge automation."""
    night_smart_charge = NightSmartCharge(hass, entry_id, config, priority_balancer)
    await night_smart_charge.async_setup()
    return night_smart_charge

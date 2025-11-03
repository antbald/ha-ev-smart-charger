"""Night Smart Charge automation for EV Smart Charger."""
from __future__ import annotations
from datetime import datetime, timedelta

from homeassistant.core import HomeAssistant, State, callback
from homeassistant.const import STATE_ON
from homeassistant.helpers.event import async_track_time_interval, async_track_state_change_event
from homeassistant.util import dt as dt_util

from .const import (
    CONF_EV_CHARGER_STATUS,
    CONF_SOC_HOME,
    CONF_PV_FORECAST,
    CONF_NOTIFY_SERVICES,
    CHARGER_STATUS_FREE,
    NIGHT_CHARGE_MODE_BATTERY,
    NIGHT_CHARGE_MODE_GRID,
    NIGHT_CHARGE_MODE_IDLE,
    HELPER_NIGHT_CHARGE_ENABLED_SUFFIX,
    HELPER_NIGHT_CHARGE_TIME_SUFFIX,
    HELPER_MIN_SOLAR_FORECAST_THRESHOLD_SUFFIX,
    HELPER_NIGHT_CHARGE_AMPERAGE_SUFFIX,
    HELPER_HOME_BATTERY_MIN_SOC_SUFFIX,
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
            hass, config.get(CONF_NOTIFY_SERVICES, []), entry_id
        )

        # User-configured entities
        self._charger_status = config.get(CONF_EV_CHARGER_STATUS)
        self._soc_home = config.get(CONF_SOC_HOME)
        self._pv_forecast_entity = config.get(CONF_PV_FORECAST)

        # Helper entities (discovered in async_setup)
        self._night_charge_enabled_entity = None
        self._night_charge_time_entity = None
        self._solar_forecast_threshold_entity = None
        self._night_charge_amperage_entity = None
        self._home_battery_min_soc_entity = None

        # Timer and state tracking
        self._timer_unsub = None
        self._charger_status_unsub = None
        self._battery_monitor_unsub = None
        self._night_charge_active = False
        self._active_mode = NIGHT_CHARGE_MODE_IDLE
        self._last_window_check_time = None

    async def async_setup(self) -> None:
        """Set up Night Smart Charge automation."""
        self.logger.separator()
        self.logger.start("Night Smart Charge initialization")
        self.logger.separator()

        # Discover helper entities
        try:
            self._night_charge_enabled_entity = entity_helper.get_helper_entity(
                self.hass, HELPER_NIGHT_CHARGE_ENABLED_SUFFIX, "Night Smart Charge"
            )
            self._night_charge_time_entity = entity_helper.get_helper_entity(
                self.hass, HELPER_NIGHT_CHARGE_TIME_SUFFIX, "Night Smart Charge"
            )
            self._solar_forecast_threshold_entity = entity_helper.get_helper_entity(
                self.hass, HELPER_MIN_SOLAR_FORECAST_THRESHOLD_SUFFIX, "Night Smart Charge"
            )
            self._night_charge_amperage_entity = entity_helper.get_helper_entity(
                self.hass, HELPER_NIGHT_CHARGE_AMPERAGE_SUFFIX, "Night Smart Charge"
            )
            self._home_battery_min_soc_entity = entity_helper.get_helper_entity(
                self.hass, HELPER_HOME_BATTERY_MIN_SOC_SUFFIX, "Night Smart Charge"
            )
        except ValueError as e:
            self.logger.error(f"Failed to discover helper entities: {e}")
            return

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
        current_time = dt_util.now()
        self.logger.debug(f"Periodic check at {current_time.strftime('%H:%M:%S')}")

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
        time_state = state_helper.get_state(self.hass, self._night_charge_time_entity)

        if not time_state or time_state in ("unknown", "unavailable"):
            self.logger.warning("Time entity unavailable for window check")
            return False

        # Parse time string using TimeParsingService
        try:
            scheduled_time = TimeParsingService.time_string_to_datetime(time_state, now)
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
            self.logger.info(f"{self.logger.CLOCK} Window check:")
            self.logger.info(f"   Current: {now.strftime('%Y-%m-%d %H:%M:%S')}")
            self.logger.info(f"   Scheduled: {scheduled_time.strftime('%Y-%m-%d %H:%M:%S')}")
            self.logger.info(f"   Sunrise ({sunrise_label}): {sunrise.strftime('%Y-%m-%d %H:%M:%S')}")
            self.logger.info(f"   Active: {is_active}")
            self._last_window_check_time = now

        return is_active

    # ========== MAIN EVALUATION LOGIC ==========

    async def _evaluate_and_charge(self) -> None:
        """Main decision logic for Night Smart Charge."""
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

        if not charger_status or charger_status == CHARGER_STATUS_FREE:
            self.logger.skip("Charger not connected")
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

        self.logger.info(f"   Charger amperage: {amperage}A")
        self.logger.info(f"   EV target SOC: {ev_target}%")
        self.logger.info(f"   Home battery minimum SOC: {home_min_soc}%")

        # Start charger with specified amperage
        await self.charger_controller.start_charger(amperage, "Night charge - Battery mode")

        # Set internal state
        self._night_charge_active = True
        self._active_mode = NIGHT_CHARGE_MODE_BATTERY

        # Send mobile notification
        reason = f"Previsione solare sufficiente ({pv_forecast:.1f} kWh >= {threshold} kWh)"
        await self._mobile_notifier.send_night_charge_notification(
            mode=NIGHT_CHARGE_MODE_BATTERY,
            reason=reason,
            amperage=amperage,
            forecast=pv_forecast
        )

        # Start continuous battery monitoring (every 1 minute)
        if self._battery_monitor_unsub:
            self._battery_monitor_unsub()  # Cancel existing monitor if any

        self._battery_monitor_unsub = async_track_time_interval(
            self.hass,
            self._async_monitor_battery_charge,
            timedelta(minutes=1),
        )

        self.logger.success("Battery charge started successfully")
        self.logger.info("Monitoring: Continuous (every 1 minute)")
        self.logger.info("Will stop when:")
        self.logger.info(f"  1. EV reaches target SOC ({ev_target}%)")
        self.logger.info(f"  2. Home battery reaches minimum SOC ({home_min_soc}%)")
        self.logger.info(f"  3. Sunrise occurs")
        self.logger.separator()

    @callback
    async def _async_monitor_battery_charge(self, now) -> None:
        """Monitor battery charge and enforce thresholds (runs every 1 minute)."""
        # Only monitor if battery mode is active
        if not self.is_active() or self._active_mode != NIGHT_CHARGE_MODE_BATTERY:
            return

        current_time = dt_util.now()
        self.logger.separator()
        self.logger.info(f"{self.logger.BATTERY} Battery monitoring at {current_time.strftime('%H:%M:%S')}")

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

        # Start charger with specified amperage
        await self.charger_controller.start_charger(amperage, "Night charge - Grid mode")

        # Set internal state
        self._night_charge_active = True
        self._active_mode = NIGHT_CHARGE_MODE_GRID

        # Send mobile notification
        reason = f"Previsione solare insufficiente ({pv_forecast:.1f} kWh < {threshold} kWh)"
        await self._mobile_notifier.send_night_charge_notification(
            mode=NIGHT_CHARGE_MODE_GRID,
            reason=reason,
            amperage=amperage,
            forecast=pv_forecast
        )

        self.logger.success("Grid charge started successfully")
        self.logger.info(f"Will charge until EV reaches target SOC ({ev_target}%)")
        self.logger.info("Grid import detection is disabled for night charging")
        self.logger.separator()

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

        # Reset state flags
        previous_mode = self._active_mode
        self._night_charge_active = False
        self._active_mode = NIGHT_CHARGE_MODE_IDLE

        self.logger.success("Session completed")
        self.logger.info(f"   Previous mode: {previous_mode}")
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

    def _get_home_battery_min_soc(self) -> float:
        """Get home battery minimum SOC."""
        return state_helper.get_float(
            self.hass,
            self._home_battery_min_soc_entity,
            20.0
        )

    def _log_configuration(self) -> None:
        """Log current configuration."""
        enabled = state_helper.get_bool(self.hass, self._night_charge_enabled_entity)
        scheduled_time = state_helper.get_state(self.hass, self._night_charge_time_entity)
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

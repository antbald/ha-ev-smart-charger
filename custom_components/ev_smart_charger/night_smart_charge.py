"""Night Smart Charge automation for EV Smart Charger."""
from __future__ import annotations
import asyncio
from datetime import datetime, timedelta

from homeassistant.core import HomeAssistant, State, callback
from homeassistant.const import STATE_ON, STATE_OFF
from homeassistant.helpers.event import async_track_time_interval, async_track_state_change_event
from homeassistant.helpers.sun import get_astral_event_date
from homeassistant.util import dt as dt_util

from .const import (
    CONF_EV_CHARGER_SWITCH,
    CONF_EV_CHARGER_CURRENT,
    CONF_EV_CHARGER_STATUS,
    CONF_SOC_HOME,
    CONF_PV_FORECAST,
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


class NightSmartCharge:
    """Manages Night Smart Charge automation with Priority Balancer integration."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry_id: str,
        config: dict,
        priority_balancer,
    ) -> None:
        """
        Initialize Night Smart Charge.

        Args:
            hass: Home Assistant instance
            entry_id: Config entry ID
            config: User configuration
            priority_balancer: PriorityBalancer instance for target checks
        """
        self.hass = hass
        self.entry_id = entry_id
        self.config = config
        self.priority_balancer = priority_balancer
        self.logger = EVSCLogger("NIGHT SMART CHARGE")

        # User-configured entities
        self._charger_switch = config.get(CONF_EV_CHARGER_SWITCH)
        self._charger_current = config.get(CONF_EV_CHARGER_CURRENT)
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

        # Parse time string "HH:MM:SS"
        try:
            time_parts = time_state.split(":")
            hour = int(time_parts[0])
            minute = int(time_parts[1])
        except (ValueError, TypeError, IndexError) as e:
            self.logger.error(f"Invalid time configuration: {time_state} - {e}")
            return False

        # Create scheduled time for today
        scheduled_time = now.replace(hour=hour, minute=minute, second=0, microsecond=0)

        # Get sunrise time - today's or tomorrow's
        sunrise_today = get_astral_event_date(self.hass, "sunrise", now)

        if not sunrise_today:
            self.logger.warning("Could not determine sunrise time")
            return False

        # Determine which sunrise to use
        if now < sunrise_today:
            sunrise = sunrise_today
            sunrise_label = "today"
        else:
            tomorrow = now + timedelta(days=1)
            sunrise = get_astral_event_date(self.hass, "sunrise", tomorrow)
            sunrise_label = "tomorrow"

            if not sunrise:
                self.logger.warning("Could not determine tomorrow's sunrise")
                return False

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
            await self._start_battery_charge()
        else:
            self.logger.decision(
                "Charging mode",
                "GRID MODE",
                f"Low/no solar forecast ({pv_forecast} kWh < {threshold} kWh)"
            )
            await self._start_grid_charge()

    # ========== BATTERY CHARGE MODE ==========

    async def _start_battery_charge(self) -> None:
        """Start charging using home battery at configured amperage with continuous monitoring."""
        self.logger.separator()
        self.logger.start(f"{self.logger.BATTERY} Battery charge mode")

        amperage = self._get_night_charge_amperage()
        home_min_soc = self._get_home_battery_min_soc()
        ev_target = self.priority_balancer.get_ev_target_for_today()

        self.logger.info(f"   Charger amperage: {amperage}A")
        self.logger.info(f"   EV target SOC: {ev_target}%")
        self.logger.info(f"   Home battery minimum SOC: {home_min_soc}%")

        # Set charger amperage
        await self._set_charger_amperage(amperage)

        # Start charger if not already charging
        await self._ensure_charger_on()

        # Set internal state
        self._night_charge_active = True
        self._active_mode = NIGHT_CHARGE_MODE_BATTERY

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
            await self._stop_charging(f"Home battery protection ({home_soc}% <= {home_min}%)")
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
            await self._stop_charging(f"EV target SOC reached ({ev_soc}% >= {ev_target}%)")
            await self._complete_night_charge()
            return

        self.logger.info(f"   {self.logger.ACTION} EV below target ({ev_soc}% < {ev_target}%) - continuing charge")
        self.logger.info("Monitoring will continue...")
        self.logger.separator()

    # ========== GRID CHARGE MODE ==========

    async def _start_grid_charge(self) -> None:
        """Start charging from grid at configured amperage."""
        self.logger.separator()
        self.logger.start(f"{self.logger.GRID} Grid charge mode")

        amperage = self._get_night_charge_amperage()
        ev_target = self.priority_balancer.get_ev_target_for_today()

        self.logger.info(f"   Charger amperage: {amperage}A")
        self.logger.info(f"   EV target SOC: {ev_target}%")

        # Set charger amperage
        await self._set_charger_amperage(amperage)

        # Start charger if not already charging
        await self._ensure_charger_on()

        # Set internal state
        self._night_charge_active = True
        self._active_mode = NIGHT_CHARGE_MODE_GRID

        self.logger.success("Grid charge started successfully")
        self.logger.info(f"Will charge until EV reaches target SOC ({ev_target}%)")
        self.logger.info("Grid import detection is disabled for night charging")
        self.logger.separator()

    # ========== CHARGER CONTROL ==========

    async def _set_charger_amperage(self, amperage: int) -> None:
        """Set charger amperage."""
        try:
            await self.hass.services.async_call(
                "number",
                "set_value",
                {"entity_id": self._charger_current, "value": amperage},
                blocking=True,
            )
            self.logger.success(f"Charger amperage set to {amperage}A")
        except Exception as e:
            self.logger.error(f"Failed to set charger amperage: {e}")

    async def _ensure_charger_on(self) -> None:
        """Ensure charger is turned on."""
        charger_state = state_helper.get_state(self.hass, self._charger_switch)

        if charger_state == STATE_OFF:
            try:
                await self.hass.services.async_call(
                    "switch",
                    "turn_on",
                    {"entity_id": self._charger_switch},
                    blocking=True,
                )
                self.logger.success("Charger turned ON")
            except Exception as e:
                self.logger.error(f"Failed to turn on charger: {e}")

    async def _stop_charging(self, reason: str) -> None:
        """Stop EV charging with logging and verification."""
        self.logger.separator()
        self.logger.stop("Charger", reason)
        self.logger.info(f"   Timestamp: {dt_util.now().strftime('%Y-%m-%d %H:%M:%S')}")

        # Stop the charger
        try:
            await self.hass.services.async_call(
                "switch",
                "turn_off",
                {"entity_id": self._charger_switch},
                blocking=True,
            )
            self.logger.info(f"   Sent turn_off command to {self._charger_switch}")
        except Exception as e:
            self.logger.error(f"Failed to stop charger: {e}")
            self.logger.separator()
            return

        # Verify charger stopped
        await asyncio.sleep(2)
        verify_state = state_helper.get_state(self.hass, self._charger_switch)

        if verify_state == STATE_OFF:
            self.logger.success(f"Charger successfully stopped (state: {verify_state})")
        else:
            self.logger.warning(f"Charger may still be ON (state: {verify_state})")

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

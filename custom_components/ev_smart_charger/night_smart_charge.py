"""Night Smart Charge automation for EV Smart Charger."""
from __future__ import annotations
import logging
from datetime import datetime, timedelta

from homeassistant.core import HomeAssistant, State, callback
from homeassistant.const import STATE_ON, STATE_OFF
from homeassistant.helpers.event import async_track_time_interval, async_track_state_change_event
from homeassistant.helpers.sun import get_astral_event_date
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util

from .const import (
    DOMAIN,
    CONF_EV_CHARGER_SWITCH,
    CONF_EV_CHARGER_CURRENT,
    CONF_EV_CHARGER_STATUS,
    CONF_SOC_CAR,
    CONF_SOC_HOME,
    CONF_PV_FORECAST,
    CHARGER_STATUS_FREE,
    CHARGER_STATUS_CHARGING,
    NIGHT_CHARGE_MODE_BATTERY,
    NIGHT_CHARGE_MODE_GRID,
    NIGHT_CHARGE_MODE_IDLE,
)

_LOGGER = logging.getLogger(__name__)


class NightSmartCharge:
    """Manages Night Smart Charge automation."""

    def __init__(self, hass: HomeAssistant, entry_id: str, config: dict) -> None:
        """Initialize Night Smart Charge."""
        self.hass = hass
        self.entry_id = entry_id
        self.config = config

        # User-configured entities
        self._charger_switch = config.get(CONF_EV_CHARGER_SWITCH)
        self._charger_current = config.get(CONF_EV_CHARGER_CURRENT)
        self._charger_status = config.get(CONF_EV_CHARGER_STATUS)
        self._soc_car = config.get(CONF_SOC_CAR)
        self._soc_home = config.get(CONF_SOC_HOME)
        self._pv_forecast_entity = config.get(CONF_PV_FORECAST)

        # Helper entities (will be discovered)
        self._night_charge_enabled_entity = None
        self._night_charge_time_entity = None
        self._solar_forecast_threshold_entity = None
        self._night_charge_amperage_entity = None
        self._priority_balancer_enabled_entity = None
        self._ev_min_soc_monday_entity = None
        self._ev_min_soc_tuesday_entity = None
        self._ev_min_soc_wednesday_entity = None
        self._ev_min_soc_thursday_entity = None
        self._ev_min_soc_friday_entity = None
        self._ev_min_soc_saturday_entity = None
        self._ev_min_soc_sunday_entity = None
        self._home_battery_min_soc_entity = None

        # Timer and state tracking
        self._timer_unsub = None
        self._charger_status_unsub = None
        self._night_charge_active = False
        self._active_mode = NIGHT_CHARGE_MODE_IDLE
        self._last_check_time = None

    def _find_entity_by_suffix(self, suffix: str) -> str | None:
        """Find entity ID by suffix, filtering by this integration's config_entry_id."""
        entity_registry = er.async_get(self.hass)

        for entity in entity_registry.entities.values():
            if entity.config_entry_id == self.entry_id:
                if entity.unique_id and entity.unique_id.endswith(suffix):
                    _LOGGER.debug(f"🌙 Found helper entity: {entity.entity_id}")
                    return entity.entity_id

        _LOGGER.warning(f"🌙 Helper entity with suffix '{suffix}' not found")
        return None

    async def async_setup(self) -> None:
        """Set up Night Smart Charge automation."""
        _LOGGER.info("🌙 Night Smart Charge: Initializing...")

        # Find helper entities
        self._night_charge_enabled_entity = self._find_entity_by_suffix("evsc_night_smart_charge_enabled")
        self._night_charge_time_entity = self._find_entity_by_suffix("evsc_night_charge_time")
        self._solar_forecast_threshold_entity = self._find_entity_by_suffix("evsc_min_solar_forecast_threshold")
        self._night_charge_amperage_entity = self._find_entity_by_suffix("evsc_night_charge_amperage")
        self._priority_balancer_enabled_entity = self._find_entity_by_suffix("evsc_priority_balancer_enabled")
        self._ev_min_soc_monday_entity = self._find_entity_by_suffix("evsc_ev_min_soc_monday")
        self._ev_min_soc_tuesday_entity = self._find_entity_by_suffix("evsc_ev_min_soc_tuesday")
        self._ev_min_soc_wednesday_entity = self._find_entity_by_suffix("evsc_ev_min_soc_wednesday")
        self._ev_min_soc_thursday_entity = self._find_entity_by_suffix("evsc_ev_min_soc_thursday")
        self._ev_min_soc_friday_entity = self._find_entity_by_suffix("evsc_ev_min_soc_friday")
        self._ev_min_soc_saturday_entity = self._find_entity_by_suffix("evsc_ev_min_soc_saturday")
        self._ev_min_soc_sunday_entity = self._find_entity_by_suffix("evsc_ev_min_soc_sunday")
        self._home_battery_min_soc_entity = self._find_entity_by_suffix("evsc_home_battery_min_soc")

        if not all([
            self._night_charge_enabled_entity,
            self._night_charge_time_entity,
            self._solar_forecast_threshold_entity,
            self._night_charge_amperage_entity,
            self._priority_balancer_enabled_entity,
        ]):
            _LOGGER.error("❌ Night Smart Charge: Required helper entities not found")
            return

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

        _LOGGER.info("✅ Night Smart Charge: Initialized successfully")

    async def async_remove(self) -> None:
        """Remove Night Smart Charge automation."""
        if self._timer_unsub:
            self._timer_unsub()
        if self._charger_status_unsub:
            self._charger_status_unsub()
        _LOGGER.info("🌙 Night Smart Charge: Removed")

    @callback
    async def _async_periodic_check(self, now) -> None:
        """Periodic check every minute."""
        # Check if we're in active window
        if not await self._is_in_active_window(now):
            return

        # Check if enabled
        if not self._is_night_charge_enabled():
            return

        # Run evaluation
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
            _LOGGER.info(f"🌙 Night Smart Charge: Car plugged in (status: {new_state.state})")

            # Check if we're in active window and enabled
            now = dt_util.now()
            if await self._is_in_active_window(now) and self._is_night_charge_enabled():
                _LOGGER.info("🌙 Late arrival detected - running immediate check")
                await self._evaluate_and_charge()

    async def _is_in_active_window(self, now: datetime) -> bool:
        """Check if current time is between scheduled time and sunrise."""
        # Get scheduled time configuration from time entity
        time_state = self.hass.states.get(self._night_charge_time_entity)

        if not time_state or time_state.state in ("unknown", "unavailable"):
            return False

        try:
            # Parse time string "HH:MM:SS"
            time_parts = time_state.state.split(":")
            hour = int(time_parts[0])
            minute = int(time_parts[1])
        except (ValueError, TypeError, IndexError):
            _LOGGER.error("❌ Invalid time configuration for Night Smart Charge")
            return False

        # Create scheduled time for today
        scheduled_time = now.replace(hour=hour, minute=minute, second=0, microsecond=0)

        # Get sunrise time
        sunrise = get_astral_event_date(self.hass, "sunrise", now)

        if not sunrise:
            _LOGGER.warning("⚠️ Could not determine sunrise time")
            return False

        # Check if we're in the active window
        is_active = now >= scheduled_time and now < sunrise

        # Log only once per minute to avoid spam
        if self._last_check_time is None or (now - self._last_check_time).total_seconds() >= 60:
            _LOGGER.debug(
                f"🌙 Active window check: now={now.strftime('%H:%M')}, "
                f"scheduled={scheduled_time.strftime('%H:%M')}, "
                f"sunrise={sunrise.strftime('%H:%M')}, active={is_active}"
            )
            self._last_check_time = now

        return is_active

    def _is_night_charge_enabled(self) -> bool:
        """Check if Night Smart Charge is enabled."""
        if not self._night_charge_enabled_entity:
            return False

        state = self.hass.states.get(self._night_charge_enabled_entity)
        return state and state.state == STATE_ON

    async def _evaluate_and_charge(self) -> None:
        """Main decision logic for Night Smart Charge."""
        _LOGGER.info("🌙 Night Smart Charge: Starting evaluation")

        # Step 1: Check if Priority Balancer is enabled
        balancer_enabled = self._is_priority_balancer_enabled()
        if not balancer_enabled:
            _LOGGER.info("🌙 Priority Balancer disabled - Night Smart Charge skipped")
            return

        # Step 2: Check if charger is connected
        charger_state = self.hass.states.get(self._charger_status)
        if not charger_state or charger_state.state == CHARGER_STATUS_FREE:
            _LOGGER.debug("🌙 Charger not connected - skipping check")
            return

        # Step 3: Get current EV SOC and today's target
        current_soc, target_soc = await self._get_ev_soc_and_target()

        if current_soc is None or target_soc is None:
            _LOGGER.warning("⚠️ Could not determine EV SOC or target - skipping")
            return

        _LOGGER.info(f"🌙 Current EV SOC: {current_soc}%, Target: {target_soc}%")

        # Step 4: Check if charging needed
        if current_soc >= target_soc:
            _LOGGER.info("🌙 EV already at or above target - no charging needed")
            # If we were charging, mark as complete
            if self._night_charge_active:
                await self._complete_night_charge()
            return

        _LOGGER.info("🌙 EV below target - evaluating energy source")

        # Step 5: Get PV forecast
        pv_forecast = await self._get_pv_forecast()
        threshold = self._get_solar_threshold()

        _LOGGER.info(f"🌙 PV Forecast: {pv_forecast} kWh, Threshold: {threshold} kWh")

        # Step 6: Decide energy source
        if pv_forecast >= threshold:
            _LOGGER.info("🌙 Good solar forecast - using HOME BATTERY mode")
            await self._start_battery_charge(target_soc)
        else:
            _LOGGER.info("🌙 Low/no solar forecast - using GRID mode")
            await self._start_grid_charge(target_soc)

    def _is_priority_balancer_enabled(self) -> bool:
        """Check if Priority Balancer is enabled."""
        if not self._priority_balancer_enabled_entity:
            return False

        state = self.hass.states.get(self._priority_balancer_enabled_entity)
        return state and state.state == STATE_ON

    async def _get_ev_soc_and_target(self) -> tuple[float | None, float | None]:
        """Get current EV SOC and today's target."""
        # Get current SOC
        soc_state = self.hass.states.get(self._soc_car)
        if not soc_state or soc_state.state in ["unknown", "unavailable"]:
            return None, None

        try:
            current_soc = float(soc_state.state)
        except (ValueError, TypeError):
            return None, None

        # Get today's target
        now = datetime.now()
        day_idx = now.weekday()

        day_entities = [
            self._ev_min_soc_monday_entity,
            self._ev_min_soc_tuesday_entity,
            self._ev_min_soc_wednesday_entity,
            self._ev_min_soc_thursday_entity,
            self._ev_min_soc_friday_entity,
            self._ev_min_soc_saturday_entity,
            self._ev_min_soc_sunday_entity,
        ]

        target_entity = day_entities[day_idx]
        if not target_entity:
            return current_soc, None

        target_state = self.hass.states.get(target_entity)
        if not target_state:
            return current_soc, None

        try:
            target_soc = float(target_state.state)
            return current_soc, target_soc
        except (ValueError, TypeError):
            return current_soc, None

    async def _get_pv_forecast(self) -> float:
        """Get PV forecast value from configured entity."""
        if not self._pv_forecast_entity:
            _LOGGER.warning("⚠️ No PV forecast entity configured - fallback to 0 kWh")
            return 0.0

        pv_state = self.hass.states.get(self._pv_forecast_entity)

        if not pv_state or pv_state.state in ["unknown", "unavailable"]:
            _LOGGER.warning(f"⚠️ PV forecast entity unavailable - fallback to 0 kWh")
            return 0.0

        try:
            value = float(pv_state.state)
            _LOGGER.debug(f"✅ PV forecast retrieved: {value} kWh")
            return value
        except (ValueError, TypeError):
            _LOGGER.error(f"❌ PV forecast invalid value: {pv_state.state} - fallback to 0 kWh")
            return 0.0

    def _get_solar_threshold(self) -> float:
        """Get solar forecast threshold."""
        if not self._solar_forecast_threshold_entity:
            return 20.0  # Default

        state = self.hass.states.get(self._solar_forecast_threshold_entity)
        if not state:
            return 20.0

        try:
            return float(state.state)
        except (ValueError, TypeError):
            return 20.0

    def _get_night_charge_amperage(self) -> int:
        """Get configured night charge amperage."""
        if not self._night_charge_amperage_entity:
            return 16  # Default

        state = self.hass.states.get(self._night_charge_amperage_entity)
        if not state:
            return 16

        try:
            return int(float(state.state))
        except (ValueError, TypeError):
            return 16

    async def _start_battery_charge(self, target_soc: float) -> None:
        """Start charging using home battery at configured amperage."""
        _LOGGER.info("🔋 Starting BATTERY charge mode")

        amperage = self._get_night_charge_amperage()
        _LOGGER.info(f"🔋 Setting charger amperage to {amperage}A")

        # Set charger amperage
        await self._set_charger_amperage(amperage)

        # Start charger if not already charging
        await self._ensure_charger_on()

        # Set internal state
        self._night_charge_active = True
        self._active_mode = NIGHT_CHARGE_MODE_BATTERY

        # Get home battery min SOC for logging
        home_min_soc = self._get_home_battery_min_soc()

        _LOGGER.info("✅ BATTERY charge started - Balancer will monitor and stop when:")
        _LOGGER.info(f"   1. EV reaches target SOC ({target_soc}%)")
        _LOGGER.info(f"   2. Home battery reaches minimum SOC ({home_min_soc}%)")

    async def _start_grid_charge(self, target_soc: float) -> None:
        """Start charging from grid at configured amperage."""
        _LOGGER.info("⚡ Starting GRID charge mode")

        amperage = self._get_night_charge_amperage()
        _LOGGER.info(f"⚡ Setting charger amperage to {amperage}A")

        # Set charger amperage
        await self._set_charger_amperage(amperage)

        # Start charger if not already charging
        await self._ensure_charger_on()

        # Set internal state
        self._night_charge_active = True
        self._active_mode = NIGHT_CHARGE_MODE_GRID

        _LOGGER.info(f"✅ GRID charge started - will charge until EV reaches target SOC ({target_soc}%)")
        _LOGGER.info("   Grid import detection is disabled for night charging")

    def _get_home_battery_min_soc(self) -> float:
        """Get home battery minimum SOC."""
        if not self._home_battery_min_soc_entity:
            return 20.0

        state = self.hass.states.get(self._home_battery_min_soc_entity)
        if not state:
            return 20.0

        try:
            return float(state.state)
        except (ValueError, TypeError):
            return 20.0

    async def _set_charger_amperage(self, amperage: int) -> None:
        """Set charger amperage."""
        try:
            await self.hass.services.async_call(
                "number",
                "set_value",
                {"entity_id": self._charger_current, "value": amperage},
                blocking=True,
            )
            _LOGGER.debug(f"✅ Charger amperage set to {amperage}A")
        except Exception as e:
            _LOGGER.error(f"❌ Failed to set charger amperage: {e}")

    async def _ensure_charger_on(self) -> None:
        """Ensure charger is turned on."""
        charger_state = self.hass.states.get(self._charger_switch)

        if charger_state and charger_state.state == STATE_OFF:
            try:
                await self.hass.services.async_call(
                    "switch",
                    "turn_on",
                    {"entity_id": self._charger_switch},
                    blocking=True,
                )
                _LOGGER.info("✅ Charger turned ON")
            except Exception as e:
                _LOGGER.error(f"❌ Failed to turn on charger: {e}")

    async def _complete_night_charge(self) -> None:
        """Complete night charge and clean up."""
        _LOGGER.info("🌙 Night Smart Charge: Completing and cleaning up")

        # Reset state flags
        self._night_charge_active = False
        self._active_mode = NIGHT_CHARGE_MODE_IDLE

        _LOGGER.info("✅ Night Smart Charge completed successfully")
        _LOGGER.info("   Smart Blocker will resume normal operation")

    def is_night_charge_active(self) -> bool:
        """Check if night charge is currently active."""
        return self._night_charge_active

    def get_active_mode(self) -> str:
        """Get current night charge mode."""
        return self._active_mode


async def async_setup_night_smart_charge(hass: HomeAssistant, entry_id: str, config: dict) -> NightSmartCharge:
    """Set up Night Smart Charge automation."""
    night_smart_charge = NightSmartCharge(hass, entry_id, config)
    await night_smart_charge.async_setup()
    return night_smart_charge

"""Automation management for EV Smart Charger."""
from __future__ import annotations
import logging
from datetime import datetime
from homeassistant.core import HomeAssistant, State, callback
from homeassistant.const import STATE_ON, STATE_OFF
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.sun import get_astral_event_date
from homeassistant.util import dt as dt_util
from .const import (
    DOMAIN,
    CONF_EV_CHARGER_SWITCH,
    CONF_EV_CHARGER_STATUS,
    CONF_FV_PRODUCTION,
    CHARGER_STATUS_CHARGING,
    HELPER_FORZA_RICARICA,
    HELPER_SMART_BLOCKER_ENABLED,
    HELPER_SOLAR_THRESHOLD,
)

_LOGGER = logging.getLogger(__name__)


class SmartChargerBlocker:
    """Smart Charger Blocker automation."""

    def __init__(self, hass: HomeAssistant, entry_id: str, config: dict) -> None:
        """Initialize the Smart Charger Blocker."""
        self.hass = hass
        self.entry_id = entry_id
        self.config = config
        self._unsub = None

    async def async_setup(self) -> None:
        """Set up the Smart Charger Blocker automation."""
        charger_status_entity = self.config.get(CONF_EV_CHARGER_STATUS)

        # Listen for charger status changes
        self._unsub = async_track_state_change_event(
            self.hass,
            charger_status_entity,
            self._async_charger_status_changed
        )

        _LOGGER.info("Smart Charger Blocker automation set up successfully")

    async def async_remove(self) -> None:
        """Remove the automation."""
        if self._unsub:
            self._unsub()
        _LOGGER.info("Smart Charger Blocker automation removed")

    @callback
    async def _async_charger_status_changed(self, event) -> None:
        """Handle charger status change events."""
        new_state: State = event.data.get("new_state")
        old_state: State = event.data.get("old_state")

        if not new_state or not old_state:
            return

        # Check if charger just started charging
        if new_state.state != CHARGER_STATUS_CHARGING:
            return

        if old_state.state == CHARGER_STATUS_CHARGING:
            return  # Already charging, ignore

        _LOGGER.debug("Charger started charging, checking if should block...")

        # Check Forza Ricarica (global kill switch)
        forza_ricarica_state = self.hass.states.get(HELPER_FORZA_RICARICA)
        if forza_ricarica_state and forza_ricarica_state.state == STATE_ON:
            _LOGGER.info("Forza Ricarica is ON - Smart Charger Blocker disabled")
            return

        # Check if Smart Charger Blocker is enabled
        blocker_enabled_state = self.hass.states.get(HELPER_SMART_BLOCKER_ENABLED)
        if not blocker_enabled_state or blocker_enabled_state.state != STATE_ON:
            _LOGGER.debug("Smart Charger Blocker is disabled")
            return

        # Check if we should block charging
        should_block, reason = await self._should_block_charging()

        if should_block:
            await self._block_charging(reason)

    async def _should_block_charging(self) -> tuple[bool, str]:
        """Determine if charging should be blocked."""
        now = dt_util.now()

        # Check if it's nighttime (after sunset and before sunrise)
        is_night = await self._is_nighttime(now)

        # Check solar production
        solar_below_threshold = await self._is_solar_below_threshold()

        if is_night and solar_below_threshold:
            return True, "Nighttime and solar production below threshold"
        elif is_night:
            return True, "Nighttime (after sunset)"
        elif solar_below_threshold:
            return True, "Solar production below threshold"

        return False, ""

    async def _is_nighttime(self, now: datetime) -> bool:
        """Check if current time is between sunset and sunrise."""
        try:
            # Get today's sunset
            sunset = get_astral_event_date(self.hass, "sunset", now)
            # Get tomorrow's sunrise
            sunrise = get_astral_event_date(self.hass, "sunrise", now)

            if sunset and sunrise:
                # If sunrise is before sunset, it means it's tomorrow's sunrise
                if sunrise < sunset:
                    # We need tomorrow's sunrise
                    tomorrow = now + dt_util.dt.timedelta(days=1)
                    sunrise = get_astral_event_date(self.hass, "sunrise", tomorrow)

                is_night = now >= sunset or now < sunrise
                _LOGGER.debug(f"Nighttime check: now={now}, sunset={sunset}, sunrise={sunrise}, is_night={is_night}")
                return is_night
        except Exception as e:
            _LOGGER.error(f"Error checking nighttime: {e}")

        return False

    async def _is_solar_below_threshold(self) -> bool:
        """Check if solar production is below threshold."""
        fv_production_entity = self.config.get(CONF_FV_PRODUCTION)
        solar_threshold_state = self.hass.states.get(HELPER_SOLAR_THRESHOLD)

        if not fv_production_entity or not solar_threshold_state:
            _LOGGER.warning("Solar production entity or threshold not configured")
            return True  # Assume no solar if not configured

        fv_state = self.hass.states.get(fv_production_entity)
        if not fv_state:
            _LOGGER.warning(f"Solar production entity {fv_production_entity} not found")
            return True

        try:
            solar_production = float(fv_state.state)
            threshold = float(solar_threshold_state.state)

            is_below = solar_production < threshold
            _LOGGER.debug(f"Solar check: production={solar_production}W, threshold={threshold}W, below={is_below}")
            return is_below
        except (ValueError, TypeError) as e:
            _LOGGER.error(f"Error parsing solar values: {e}")
            return True

    async def _block_charging(self, reason: str) -> None:
        """Block charging by turning off the charger switch."""
        charger_switch = self.config.get(CONF_EV_CHARGER_SWITCH)

        if not charger_switch:
            _LOGGER.error("Charger switch not configured")
            return

        _LOGGER.warning(f"🚫 Blocking charging: {reason}")

        # Turn off the charger
        await self.hass.services.async_call(
            "switch",
            "turn_off",
            {"entity_id": charger_switch},
            blocking=True,
        )

        # Send persistent notification
        await self.hass.services.async_call(
            "persistent_notification",
            "create",
            {
                "title": "⚡ EV Smart Charger: Charging Blocked",
                "message": f"Charging has been automatically blocked.\n\n**Reason:** {reason}\n\nTo override this behavior, enable 'Forza Ricarica' or disable 'Smart Charger Blocker'.",
                "notification_id": f"evsc_blocked_{int(dt_util.now().timestamp())}",
            },
            blocking=False,
        )

        _LOGGER.info(f"Charger blocked successfully - Reason: {reason}")


async def async_setup_automations(hass: HomeAssistant, entry_id: str, config: dict) -> dict:
    """Set up all automations for the integration."""
    automations = {}

    # Set up Smart Charger Blocker
    smart_blocker = SmartChargerBlocker(hass, entry_id, config)
    await smart_blocker.async_setup()
    automations["smart_blocker"] = smart_blocker

    return automations


async def async_remove_automations(automations: dict) -> None:
    """Remove all automations."""
    for automation in automations.values():
        await automation.async_remove()

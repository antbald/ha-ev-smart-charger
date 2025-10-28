"""Automation management for EV Smart Charger."""
from __future__ import annotations
import logging
from datetime import datetime
from homeassistant.core import HomeAssistant, State, callback
from homeassistant.const import STATE_ON, STATE_OFF
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.sun import get_astral_event_date
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util
from .const import (
    DOMAIN,
    CONF_EV_CHARGER_SWITCH,
    CONF_EV_CHARGER_STATUS,
    CHARGER_STATUS_CHARGING,
)

_LOGGER = logging.getLogger(__name__)


class SmartChargerBlocker:
    """Smart Charger Blocker automation."""

    def __init__(self, hass: HomeAssistant, entry_id: str, config: dict, night_smart_charge=None) -> None:
        """Initialize the Smart Charger Blocker."""
        self.hass = hass
        self.entry_id = entry_id
        self.config = config
        self._night_smart_charge = night_smart_charge
        self._unsub_status = None
        self._unsub_switch = None
        self._unsub_blocker = None

        # Helper entities - will be found in async_setup
        self._forza_ricarica_entity = None
        self._blocker_enabled_entity = None

    def _find_entity_by_suffix(self, suffix: str) -> str | None:
        """Find entity ID by suffix, filtering by this integration's config_entry_id."""
        # Use entity registry and filter by our config entry
        entity_registry = er.async_get(self.hass)

        # Search only through entities belonging to this integration instance
        for entity in entity_registry.entities.values():
            # Filter by config_entry_id to get only OUR entities
            if entity.config_entry_id == self.entry_id:
                # Check if unique_id ends with the suffix
                if entity.unique_id and entity.unique_id.endswith(suffix):
                    _LOGGER.debug(f"Found helper entity: {entity.entity_id} (unique_id: {entity.unique_id})")
                    return entity.entity_id

        _LOGGER.warning(f"Helper entity with suffix '{suffix}' not found for config_entry {self.entry_id}")
        return None

    async def async_setup(self) -> None:
        """Set up the Smart Charger Blocker automation."""
        charger_status_entity = self.config.get(CONF_EV_CHARGER_STATUS)
        charger_switch_entity = self.config.get(CONF_EV_CHARGER_SWITCH)

        # Find helper entities
        self._forza_ricarica_entity = self._find_entity_by_suffix(f"evsc_forza_ricarica")
        self._blocker_enabled_entity = self._find_entity_by_suffix(f"evsc_smart_charger_blocker_enabled")

        if not self._blocker_enabled_entity:
            _LOGGER.error("Cannot set up Smart Charger Blocker - helper entities not found")
            return

        # Listen for charger status changes (charger_free -> charger_charging)
        self._unsub_status = async_track_state_change_event(
            self.hass,
            charger_status_entity,
            self._async_charger_status_changed
        )

        # Listen for charger switch turning ON (off -> on)
        self._unsub_switch = async_track_state_change_event(
            self.hass,
            charger_switch_entity,
            self._async_charger_switch_changed
        )

        # Listen for blocker being enabled (check immediately if charger is already on)
        self._unsub_blocker = async_track_state_change_event(
            self.hass,
            self._blocker_enabled_entity,
            self._async_blocker_enabled_changed
        )

        _LOGGER.info("✅ Smart Charger Blocker automation set up successfully")
        _LOGGER.info(f"  - Monitoring charger status: {charger_status_entity}")
        _LOGGER.info(f"  - Monitoring charger switch: {charger_switch_entity}")
        _LOGGER.info(f"  - Monitoring blocker switch: {self._blocker_enabled_entity}")

    async def async_remove(self) -> None:
        """Remove the automation."""
        if self._unsub_status:
            self._unsub_status()
        if self._unsub_switch:
            self._unsub_switch()
        if self._unsub_blocker:
            self._unsub_blocker()
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

        _LOGGER.info(f"🔌 Charger status changed to charging (was: {old_state.state})")
        await self._check_and_block_if_needed("Status changed to charging")

    @callback
    async def _async_charger_switch_changed(self, event) -> None:
        """Handle charger switch state change events."""
        new_state: State = event.data.get("new_state")
        old_state: State = event.data.get("old_state")

        if not new_state or not old_state:
            return

        # Check if charger switch just turned ON
        if new_state.state != STATE_ON:
            return

        if old_state.state == STATE_ON:
            return  # Already on, ignore

        _LOGGER.info(f"🔌 Charger switch turned ON (was: {old_state.state})")
        await self._check_and_block_if_needed("Charger switch turned ON")

    @callback
    async def _async_blocker_enabled_changed(self, event) -> None:
        """Handle blocker enable switch state change events."""
        new_state: State = event.data.get("new_state")
        old_state: State = event.data.get("old_state")

        if not new_state or not old_state:
            return

        # Check if blocker just got enabled
        if new_state.state != STATE_ON:
            return

        if old_state.state == STATE_ON:
            return  # Already enabled, ignore

        _LOGGER.info("🔌 Smart Charger Blocker enabled - checking current charger state")

        # Check if charger is currently ON
        charger_switch = self.config.get(CONF_EV_CHARGER_SWITCH)
        if charger_switch:
            charger_state = self.hass.states.get(charger_switch)
            if charger_state and charger_state.state == STATE_ON:
                await self._check_and_block_if_needed("Blocker enabled while charger was ON")

    async def _check_and_block_if_needed(self, trigger_reason: str) -> None:
        """Common logic to check conditions and block if needed."""
        _LOGGER.debug(f"Checking blocking conditions - Trigger: {trigger_reason}")

        # Check Forza Ricarica (global kill switch)
        if self._forza_ricarica_entity:
            forza_ricarica_state = self.hass.states.get(self._forza_ricarica_entity)
            if forza_ricarica_state and forza_ricarica_state.state == STATE_ON:
                _LOGGER.info("✅ Forza Ricarica is ON - Smart Charger Blocker disabled")
                return

        # Check if Smart Charger Blocker is enabled
        if self._blocker_enabled_entity:
            blocker_enabled_state = self.hass.states.get(self._blocker_enabled_entity)
            if not blocker_enabled_state or blocker_enabled_state.state != STATE_ON:
                _LOGGER.debug("Smart Charger Blocker is disabled")
                return
        else:
            _LOGGER.warning("Smart Charger Blocker helper not found")
            return

        # Check if we should block charging
        should_block, reason = await self._should_block_charging()

        if should_block:
            await self._block_charging(f"{trigger_reason} - {reason}")

    async def _should_block_charging(self) -> tuple[bool, str]:
        """Determine if charging should be blocked."""
        # Check if Night Smart Charge is active (override blocker)
        if self._night_smart_charge and self._night_smart_charge.is_night_charge_active():
            night_mode = self._night_smart_charge.get_active_mode()
            _LOGGER.info(f"🌙 Night Smart Charge is active (mode: {night_mode}) - Smart Blocker overridden")
            return False, "Night Smart Charge active"

        now = dt_util.now()

        # Check if it's nighttime (after sunset and before sunrise)
        is_night = await self._is_nighttime(now)

        if is_night:
            return True, "Nighttime (after sunset)"

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


async def async_setup_automations(hass: HomeAssistant, entry_id: str, config: dict, night_smart_charge=None) -> dict:
    """Set up all automations for the integration."""
    automations = {}

    # Set up Smart Charger Blocker
    smart_blocker = SmartChargerBlocker(hass, entry_id, config, night_smart_charge)
    await smart_blocker.async_setup()
    automations["smart_blocker"] = smart_blocker

    return automations


async def async_remove_automations(automations: dict) -> None:
    """Remove all automations."""
    for automation in automations.values():
        await automation.async_remove()

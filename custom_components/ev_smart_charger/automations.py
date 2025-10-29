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
from .automation_coordinator import PRIORITY_SMART_BLOCKER

_LOGGER = logging.getLogger(__name__)

# Enforcement timeout in minutes - after this time, conditions will be re-checked
ENFORCEMENT_TIMEOUT_MINUTES = 30


class SmartChargerBlocker:
    """Smart Charger Blocker automation."""

    def __init__(self, hass: HomeAssistant, entry_id: str, config: dict, night_smart_charge=None, coordinator=None) -> None:
        """Initialize the Smart Charger Blocker."""
        self.hass = hass
        self.entry_id = entry_id
        self.config = config
        self._night_smart_charge = night_smart_charge
        self._coordinator = coordinator  # Automation coordinator
        self._unsub_status = None
        self._unsub_switch = None
        self._unsub_blocker = None
        self._unsub_enforcement = None  # For continuous enforcement monitoring

        # Helper entities - will be found in async_setup
        self._forza_ricarica_entity = None
        self._blocker_enabled_entity = None

        # Enforcement state tracking
        self._currently_blocking = False  # Flag to indicate active blocking enforcement
        self._enforcement_start_time = None  # Track when enforcement started

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

        # Listen for charger switch state changes during enforcement
        self._unsub_enforcement = async_track_state_change_event(
            self.hass,
            charger_switch_entity,
            self._async_enforcement_monitor
        )

        _LOGGER.info("✅ Smart Charger Blocker automation set up successfully")
        _LOGGER.info(f"  - Monitoring charger status: {charger_status_entity}")
        _LOGGER.info(f"  - Monitoring charger switch: {charger_switch_entity}")
        _LOGGER.info(f"  - Monitoring blocker switch: {self._blocker_enabled_entity}")
        _LOGGER.info(f"  - Continuous enforcement monitoring enabled")

    async def async_remove(self) -> None:
        """Remove the automation."""
        if self._unsub_status:
            self._unsub_status()
        if self._unsub_switch:
            self._unsub_switch()
        if self._unsub_blocker:
            self._unsub_blocker()
        if self._unsub_enforcement:
            self._unsub_enforcement()
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

    @callback
    async def _async_enforcement_monitor(self, event) -> None:
        """Monitor charger switch for external re-enable during active enforcement."""
        new_state: State = event.data.get("new_state")
        old_state: State = event.data.get("old_state")

        if not new_state or not old_state:
            return

        # Only act if we're currently enforcing blocking
        if not self._currently_blocking:
            return

        # First, check if we should exit enforcement mode
        should_exit, exit_reason = await self._should_exit_enforcement_mode()
        if should_exit:
            _LOGGER.info("🔓 [Smart Blocker] [ENFORCEMENT_ENDED] Exiting enforcement mode")
            _LOGGER.info(f"   Reason: {exit_reason}")
            self._currently_blocking = False
            self._enforcement_start_time = None

            # Release control from coordinator
            if self._coordinator:
                self._coordinator.release_control("Smart Charger Blocker", exit_reason)

            return

        # Check if charger just turned ON
        if new_state.state == STATE_ON and old_state.state != STATE_ON:
            _LOGGER.warning("🚨 [Smart Blocker] [ENFORCEMENT] External charger re-enable detected during active blocking!")
            _LOGGER.warning(f"   Charger state: {old_state.state} → {new_state.state}")
            _LOGGER.warning(f"   Enforcement active since previous blocking attempt")

            # Re-check blocking conditions before re-blocking
            should_block, block_reason = await self._should_block_charging()
            if should_block:
                _LOGGER.warning(f"   Blocking still required: {block_reason}")
                await self._block_charging(f"Enforcement - External re-enable detected - {block_reason}")
            else:
                _LOGGER.info(f"✅ [Smart Blocker] [ENFORCEMENT_ENDED] Blocking no longer needed: {block_reason}")
                self._currently_blocking = False
                self._enforcement_start_time = None

                # Release control from coordinator
                if self._coordinator:
                    self._coordinator.release_control("Smart Charger Blocker", f"Blocking no longer needed: {block_reason}")

    async def _check_and_block_if_needed(self, trigger_reason: str) -> None:
        """Common logic to check conditions and block if needed."""
        _LOGGER.info(f"🔍 [Smart Blocker] [CHECK] Evaluating blocking conditions")
        _LOGGER.info(f"   Trigger: {trigger_reason}")

        # Check Forza Ricarica (global kill switch)
        if self._forza_ricarica_entity:
            forza_ricarica_state = self.hass.states.get(self._forza_ricarica_entity)
            if forza_ricarica_state and forza_ricarica_state.state == STATE_ON:
                _LOGGER.info("✅ [Smart Blocker] [CHECK] Forza Ricarica is ON - Smart Charger Blocker disabled")
                self._currently_blocking = False  # Clear enforcement flag
                return

        # Check if Smart Charger Blocker is enabled
        if self._blocker_enabled_entity:
            blocker_enabled_state = self.hass.states.get(self._blocker_enabled_entity)
            if not blocker_enabled_state or blocker_enabled_state.state != STATE_ON:
                _LOGGER.info("ℹ️ [Smart Blocker] [CHECK] Smart Charger Blocker is disabled")
                self._currently_blocking = False  # Clear enforcement flag
                return
        else:
            _LOGGER.warning("⚠️ [Smart Blocker] [CHECK] Smart Charger Blocker helper not found")
            return

        # Check if we should block charging
        should_block, reason = await self._should_block_charging()

        if should_block:
            _LOGGER.info(f"🚫 [Smart Blocker] [DECISION] Blocking required: {reason}")
            await self._block_charging(f"{trigger_reason} - {reason}")
        else:
            _LOGGER.info(f"✅ [Smart Blocker] [DECISION] No blocking needed: {reason}")
            self._currently_blocking = False  # Clear enforcement flag

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
                # Determine if we're in nighttime period
                # Nighttime is: after today's sunset AND before tomorrow's sunrise

                # If current time is before today's sunset, check if we're after yesterday's sunset
                if now < sunset:
                    # Before sunset - check if we're still in nighttime from yesterday
                    # (i.e., before today's sunrise)
                    today_sunrise = get_astral_event_date(self.hass, "sunrise", now)
                    is_night = now < today_sunrise if today_sunrise else False
                else:
                    # After sunset - we're in nighttime
                    is_night = True

                _LOGGER.debug(f"Nighttime check: now={now}, sunset={sunset}, is_night={is_night}")
                return is_night
        except Exception as e:
            _LOGGER.error(f"Error checking nighttime: {e}")

        return False

    async def _should_exit_enforcement_mode(self) -> tuple[bool, str]:
        """Check if enforcement mode should be exited."""
        if not self._currently_blocking:
            return False, "Not in enforcement mode"

        # Check 1: Timeout reached
        if self._enforcement_start_time:
            elapsed = (dt_util.now() - self._enforcement_start_time).total_seconds() / 60
            if elapsed > ENFORCEMENT_TIMEOUT_MINUTES:
                return True, f"Enforcement timeout reached ({elapsed:.1f} minutes)"

        # Check 2: Override switch enabled (Forza Ricarica)
        if self._forza_ricarica_entity:
            forza_ricarica_state = self.hass.states.get(self._forza_ricarica_entity)
            if forza_ricarica_state and forza_ricarica_state.state == STATE_ON:
                return True, "Forza Ricarica override enabled"

        # Check 3: Smart Charger Blocker disabled
        if self._blocker_enabled_entity:
            blocker_state = self.hass.states.get(self._blocker_enabled_entity)
            if not blocker_state or blocker_state.state != STATE_ON:
                return True, "Smart Charger Blocker disabled"

        # Check 4: Blocking conditions no longer apply
        should_block, reason = await self._should_block_charging()
        if not should_block:
            return True, f"Blocking conditions no longer apply: {reason}"

        return False, "Enforcement should continue"

    async def _block_charging(self, reason: str) -> None:
        """Block charging by turning off the charger switch with retry logic and verification."""
        import asyncio

        charger_switch = self.config.get(CONF_EV_CHARGER_SWITCH)

        if not charger_switch:
            _LOGGER.error("❌ [Smart Blocker] [BLOCK] Charger switch not configured")
            return

        # Request permission from coordinator
        if self._coordinator:
            allowed, coord_reason = await self._coordinator.request_charger_action(
                automation_name="Smart Charger Blocker",
                action="turn_off",
                reason=reason,
                priority=PRIORITY_SMART_BLOCKER,
            )

            if not allowed:
                _LOGGER.warning(f"🚫 [Smart Blocker] [BLOCKED BY COORDINATOR] Cannot block charging")
                _LOGGER.warning(f"   Reason: {coord_reason}")
                return

        _LOGGER.warning("=" * 80)
        _LOGGER.warning(f"🚫 [Smart Blocker] [BLOCKING_ATTEMPT] Starting blocking sequence")
        _LOGGER.warning(f"   Reason: {reason}")
        _LOGGER.warning(f"   Timestamp: {dt_util.now().strftime('%Y-%m-%d %H:%M:%S')}")

        # Check for potential conflicts
        if self._night_smart_charge and self._night_smart_charge.is_night_charge_active():
            night_mode = self._night_smart_charge.get_active_mode()
            _LOGGER.warning(f"   ⚠️ Conflict detected: Night Smart Charge is active (mode: {night_mode})")
            _LOGGER.warning(f"   Smart Blocker will override Night Smart Charge")

        # Retry logic with verification
        max_attempts = 3
        for attempt in range(1, max_attempts + 1):
            _LOGGER.warning(f"🔄 [Smart Blocker] [BLOCKING_ATTEMPT] Attempt {attempt}/{max_attempts}")

            # Get current state before turning off
            current_state = self.hass.states.get(charger_switch)
            current_status = current_state.state if current_state else "unknown"
            _LOGGER.warning(f"   Current charger state: {current_status}")

            # Turn off the charger
            await self.hass.services.async_call(
                "switch",
                "turn_off",
                {"entity_id": charger_switch},
                blocking=True,
            )
            _LOGGER.warning(f"   Sent turn_off command to {charger_switch}")

            # Wait for state to propagate
            await asyncio.sleep(2)

            # Verify charger is actually OFF
            verify_state = self.hass.states.get(charger_switch)
            verify_status = verify_state.state if verify_state else "unknown"
            _LOGGER.warning(f"   Verification: charger state is now '{verify_status}'")

            if verify_status == STATE_OFF:
                _LOGGER.warning("✅ [Smart Blocker] [BLOCKING_SUCCESS] Charger successfully turned OFF")
                _LOGGER.warning(f"   Attempt: {attempt}/{max_attempts}")
                _LOGGER.warning(f"   Enforcement: ACTIVE (continuous monitoring enabled)")
                _LOGGER.warning(f"   Enforcement timeout: {ENFORCEMENT_TIMEOUT_MINUTES} minutes")

                # Set enforcement flag and timestamp
                self._currently_blocking = True
                self._enforcement_start_time = dt_util.now()

                # Send persistent notification
                await self.hass.services.async_call(
                    "persistent_notification",
                    "create",
                    {
                        "title": "⚡ EV Smart Charger: Charging Blocked",
                        "message": f"Charging has been automatically blocked.\n\n**Reason:** {reason}\n\n**Timestamp:** {dt_util.now().strftime('%H:%M:%S')}\n\nTo override this behavior, enable 'Forza Ricarica' or disable 'Smart Charger Blocker'.\n\n**Continuous monitoring:** Any external attempt to re-enable charging will be immediately blocked.",
                        "notification_id": f"evsc_blocked_{int(dt_util.now().timestamp())}",
                    },
                    blocking=False,
                )

                _LOGGER.warning("=" * 80)
                return
            else:
                _LOGGER.error(f"❌ [Smart Blocker] [BLOCKING_FAILED] Charger still ON after attempt {attempt}")
                _LOGGER.error(f"   Expected: {STATE_OFF}, Actual: {verify_status}")

                if attempt < max_attempts:
                    retry_delay = 2 * attempt  # Increasing delay: 2s, 4s, 6s
                    _LOGGER.error(f"   Retrying in {retry_delay} seconds...")
                    await asyncio.sleep(retry_delay)
                else:
                    _LOGGER.error("❌ [Smart Blocker] [BLOCKING_FAILED] All attempts exhausted!")
                    _LOGGER.error(f"   Charger remains ON after {max_attempts} attempts")
                    _LOGGER.error("   Possible causes:")
                    _LOGGER.error("   1. Charger switch entity not responding to commands")
                    _LOGGER.error("   2. External automation overriding this action")
                    _LOGGER.error("   3. Charger hardware issue")
                    _LOGGER.error("   4. Home Assistant service call failure")

                    # Send error notification
                    await self.hass.services.async_call(
                        "persistent_notification",
                        "create",
                        {
                            "title": "⚠️ EV Smart Charger: Blocking Failed",
                            "message": f"Failed to block charging after {max_attempts} attempts.\n\n**Reason:** {reason}\n\n**Issue:** Charger switch did not respond to turn_off commands.\n\nPlease check:\n- Charger switch entity is functioning\n- No conflicting automations\n- Charger hardware status",
                            "notification_id": f"evsc_block_failed_{int(dt_util.now().timestamp())}",
                        },
                        blocking=False,
                    )
                    _LOGGER.warning("=" * 80)
                    return


async def async_setup_automations(hass: HomeAssistant, entry_id: str, config: dict, night_smart_charge=None, coordinator=None) -> dict:
    """Set up all automations for the integration."""
    automations = {}

    # Set up Smart Charger Blocker
    smart_blocker = SmartChargerBlocker(hass, entry_id, config, night_smart_charge, coordinator)
    await smart_blocker.async_setup()
    automations["smart_blocker"] = smart_blocker

    return automations


async def async_remove_automations(automations: dict) -> None:
    """Remove all automations."""
    for automation in automations.values():
        await automation.async_remove()

"""Automation management for EV Smart Charger."""
from __future__ import annotations
from datetime import datetime, timedelta
import asyncio

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
    HELPER_NIGHT_CHARGE_TIME_SUFFIX,
    SMART_BLOCKER_ENFORCEMENT_TIMEOUT,
    SMART_BLOCKER_RETRY_ATTEMPTS,
    SMART_BLOCKER_RETRY_DELAYS,
)
from .automation_coordinator import PRIORITY_SMART_BLOCKER
from .utils.logging_helper import EVSCLogger
from .utils.entity_helper import find_by_suffix
from .utils.state_helper import get_state

# Enforcement timeout in seconds
ENFORCEMENT_TIMEOUT_SECONDS = SMART_BLOCKER_ENFORCEMENT_TIMEOUT


class SmartChargerBlocker:
    """Smart Charger Blocker automation with dependency injection."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry_id: str,
        config: dict,
        night_smart_charge,
        coordinator=None,
    ) -> None:
        """Initialize the Smart Charger Blocker.

        Args:
            hass: Home Assistant instance
            entry_id: Config entry ID
            config: User configuration
            night_smart_charge: Night Smart Charge instance for coordination
            coordinator: Automation coordinator for conflict resolution
        """
        self.hass = hass
        self.entry_id = entry_id
        self.config = config
        self.night_smart_charge = night_smart_charge
        self._coordinator = coordinator
        self.logger = EVSCLogger("SMART BLOCKER")

        # Listeners
        self._unsub_status = None
        self._unsub_switch = None
        self._unsub_blocker = None
        self._unsub_enforcement = None

        # Helper entities - will be found in async_setup
        self._forza_ricarica_entity = None
        self._blocker_enabled_entity = None
        self._night_charge_time_entity = None

        # Enforcement state tracking
        self._currently_blocking = False
        self._enforcement_start_time = None

    def _find_entity_by_suffix(self, suffix: str) -> str | None:
        """Find entity ID by suffix, filtering by this integration's config_entry_id."""
        entity_registry = er.async_get(self.hass)

        for entity in entity_registry.entities.values():
            if entity.config_entry_id == self.entry_id:
                if entity.unique_id and entity.unique_id.endswith(suffix):
                    self.logger.debug(
                        f"Found helper entity: {entity.entity_id} (unique_id: {entity.unique_id})"
                    )
                    return entity.entity_id

        self.logger.warning(
            f"Helper entity with suffix '{suffix}' not found for config_entry {self.entry_id}"
        )
        return None

    async def async_setup(self) -> None:
        """Set up the Smart Charger Blocker automation."""
        self.logger.separator()
        self.logger.start("Smart Charger Blocker setup")

        charger_status_entity = self.config.get(CONF_EV_CHARGER_STATUS)
        charger_switch_entity = self.config.get(CONF_EV_CHARGER_SWITCH)

        # Find helper entities
        self._forza_ricarica_entity = self._find_entity_by_suffix("evsc_forza_ricarica")
        self._blocker_enabled_entity = self._find_entity_by_suffix(
            "evsc_smart_charger_blocker_enabled"
        )
        self._night_charge_time_entity = self._find_entity_by_suffix(
            HELPER_NIGHT_CHARGE_TIME_SUFFIX
        )

        if not self._blocker_enabled_entity:
            self.logger.error("Cannot set up - helper entities not found")
            return

        # Listen for charger status changes (charger_free -> charger_charging)
        self._unsub_status = async_track_state_change_event(
            self.hass, charger_status_entity, self._async_charger_status_changed
        )

        # Listen for charger switch turning ON (off -> on)
        self._unsub_switch = async_track_state_change_event(
            self.hass, charger_switch_entity, self._async_charger_switch_changed
        )

        # Listen for blocker being enabled (check immediately if charger is already on)
        self._unsub_blocker = async_track_state_change_event(
            self.hass, self._blocker_enabled_entity, self._async_blocker_enabled_changed
        )

        # Listen for charger switch state changes during enforcement
        self._unsub_enforcement = async_track_state_change_event(
            self.hass, charger_switch_entity, self._async_enforcement_monitor
        )

        self.logger.success("Setup completed")
        self.logger.info(f"Monitoring charger status: {charger_status_entity}")
        self.logger.info(f"Monitoring charger switch: {charger_switch_entity}")
        self.logger.info(f"Monitoring blocker switch: {self._blocker_enabled_entity}")
        self.logger.info("Continuous enforcement monitoring enabled")
        self.logger.separator()

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
        self.logger.info("Smart Charger Blocker automation removed")

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

        self.logger.state_change(
            "Charger status", old_state.state, new_state.state
        )
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

        self.logger.state_change(
            "Charger switch", old_state.state, new_state.state
        )
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

        self.logger.info("Blocker enabled - checking current charger state")

        # Check if charger is currently ON
        charger_switch = self.config.get(CONF_EV_CHARGER_SWITCH)
        if charger_switch:
            charger_state = self.hass.states.get(charger_switch)
            if charger_state and charger_state.state == STATE_ON:
                await self._check_and_block_if_needed(
                    "Blocker enabled while charger was ON"
                )

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
            self.logger.info("Exiting enforcement mode")
            self.logger.info(f"Reason: {exit_reason}")
            self._currently_blocking = False
            self._enforcement_start_time = None

            # Release control from coordinator
            if self._coordinator:
                self._coordinator.release_control("Smart Charger Blocker", exit_reason)

            return

        # Check if charger just turned ON
        if new_state.state == STATE_ON and old_state.state != STATE_ON:
            self.logger.warning(
                "External charger re-enable detected during active blocking!"
            )
            self.logger.warning(f"Charger state: {old_state.state} → {new_state.state}")

            # Re-check blocking conditions before re-blocking
            should_block, block_reason = await self._should_block_charging()
            if should_block:
                self.logger.warning(f"Blocking still required: {block_reason}")
                await self._block_charging(
                    f"Enforcement - External re-enable detected - {block_reason}"
                )
            else:
                self.logger.success(f"Blocking no longer needed: {block_reason}")
                self._currently_blocking = False
                self._enforcement_start_time = None

                # Release control from coordinator
                if self._coordinator:
                    self._coordinator.release_control(
                        "Smart Charger Blocker",
                        f"Blocking no longer needed: {block_reason}",
                    )

    async def _check_and_block_if_needed(self, trigger_reason: str) -> None:
        """Common logic to check conditions and block if needed."""
        self.logger.separator()
        self.logger.info("Evaluating blocking conditions")
        self.logger.info(f"Trigger: {trigger_reason}")

        # Check Forza Ricarica (global kill switch)
        if self._forza_ricarica_entity:
            forza_ricarica_state = self.hass.states.get(self._forza_ricarica_entity)
            if forza_ricarica_state and forza_ricarica_state.state == STATE_ON:
                self.logger.skip("Forza Ricarica is ON - blocker disabled")
                self._currently_blocking = False
                self.logger.separator()
                return

        # Check if Smart Charger Blocker is enabled
        if self._blocker_enabled_entity:
            blocker_enabled_state = self.hass.states.get(self._blocker_enabled_entity)
            if not blocker_enabled_state or blocker_enabled_state.state != STATE_ON:
                self.logger.skip("Smart Charger Blocker is disabled")
                self._currently_blocking = False
                self.logger.separator()
                return
        else:
            self.logger.warning("Smart Charger Blocker helper not found")
            self.logger.separator()
            return

        # Check if we should block charging
        should_block, reason = await self._should_block_charging()

        if should_block:
            self.logger.decision("Blocking", "BLOCK CHARGING", reason)
            await self._block_charging(f"{trigger_reason} - {reason}")
        else:
            self.logger.decision("Allowing", "ALLOW CHARGING", reason)
            self._currently_blocking = False

        self.logger.separator()

    async def _should_block_charging(self) -> tuple[bool, str]:
        """Determine if charging should be blocked.

        Returns:
            (should_block, reason) tuple
        """
        # Check 1: Forza Ricarica override
        if self._forza_ricarica_entity:
            state = get_state(self.hass, self._forza_ricarica_entity)
            if state == STATE_ON:
                return False, "Forza Ricarica ON (global override)"

        # Check 2: Blocker disabled
        if self._blocker_enabled_entity:
            state = get_state(self.hass, self._blocker_enabled_entity)
            if state != STATE_ON:
                return False, "Blocker disabled"
        else:
            return False, "Blocker entity not found"

        # Check 3: Night Smart Charge active (override blocker)
        if self.night_smart_charge and self.night_smart_charge.is_night_charge_active():
            night_mode = self.night_smart_charge.get_active_mode()
            return False, f"Night Smart Charge active (mode: {night_mode})"

        # Check 4: Determine blocking window based on Night Charge configuration
        now = dt_util.now()
        in_blocking_window, window_reason = await self._is_in_blocking_window(now)

        if in_blocking_window:
            return True, window_reason

        return False, "Outside blocking window (daytime allowed)"

    async def _is_in_blocking_window(self, now: datetime) -> tuple[bool, str]:
        """Check if current time is within the blocking window.

        Blocking window logic:
        - If Night Smart Charge ENABLED: Block from sunset to night_charge_time
        - If Night Smart Charge DISABLED: Block from sunset to sunrise

        Args:
            now: Current datetime

        Returns:
            (is_blocked, reason) tuple
        """
        try:
            # Get today's sunset
            sunset = get_astral_event_date(self.hass, "sunset", now)
            if not sunset:
                self.logger.warning("Unable to determine sunset time")
                return False, "Sunset time unavailable"

            # Determine window end based on Night Smart Charge configuration
            if self._is_night_charge_enabled():
                # Window ends at night_charge_time
                window_end = await self._get_night_charge_datetime(now)
                if not window_end:
                    # Fallback to sunrise if night_charge_time not available
                    sunrise_tomorrow = get_astral_event_date(
                        self.hass, "sunrise", now + timedelta(days=1)
                    )
                    window_end = sunrise_tomorrow
                    window_type = "sunset → sunrise (fallback)"
                else:
                    window_type = "sunset → night_charge_time"
            else:
                # Window ends at sunrise tomorrow
                sunrise_tomorrow = get_astral_event_date(
                    self.hass, "sunrise", now + timedelta(days=1)
                )
                window_end = sunrise_tomorrow
                window_type = "sunset → sunrise"

            if not window_end:
                self.logger.warning("Unable to determine blocking window end")
                return False, "Window end time unavailable"

            # Determine if we're in the blocking window
            # The window spans from sunset to window_end (which might be next day)

            # Case 1: Before today's sunset - check if we're after yesterday's sunset
            if now < sunset:
                # Check if we're still in the window from yesterday
                yesterday_sunset = get_astral_event_date(
                    self.hass, "sunset", now - timedelta(days=1)
                )

                if self._is_night_charge_enabled():
                    yesterday_window_end = await self._get_night_charge_datetime(
                        now - timedelta(days=1)
                    )
                    if not yesterday_window_end:
                        yesterday_window_end = get_astral_event_date(
                            self.hass, "sunrise", now
                        )
                else:
                    yesterday_window_end = get_astral_event_date(
                        self.hass, "sunrise", now
                    )

                if yesterday_sunset and yesterday_window_end:
                    if yesterday_sunset <= now < yesterday_window_end:
                        self.logger.debug(
                            f"In blocking window (from yesterday): "
                            f"{yesterday_sunset.strftime('%H:%M')} → {yesterday_window_end.strftime('%H:%M')}"
                        )
                        return True, f"Nighttime blocking active ({window_type})"

                # Not in yesterday's window and before today's sunset = daytime
                self.logger.debug(
                    f"Daytime (before sunset at {sunset.strftime('%H:%M')})"
                )
                return False, "Daytime (before sunset)"

            # Case 2: After today's sunset - we're in the blocking window
            if now >= sunset:
                self.logger.debug(
                    f"In blocking window: {sunset.strftime('%H:%M')} → {window_end.strftime('%H:%M')}"
                )
                return True, f"Nighttime blocking active ({window_type})"

        except Exception as e:
            self.logger.error(f"Error checking blocking window: {e}")
            return False, f"Error: {e}"

        return False, "Outside blocking window"

    def _is_night_charge_enabled(self) -> bool:
        """Check if Night Smart Charge is enabled."""
        if not self.night_smart_charge:
            return False

        # Check the helper entity directly
        night_charge_entity = self._find_entity_by_suffix(
            "evsc_night_smart_charge_enabled"
        )
        if not night_charge_entity:
            return False

        state = get_state(self.hass, night_charge_entity)
        return state == STATE_ON

    async def _get_night_charge_datetime(self, reference_date: datetime) -> datetime | None:
        """Get the night charge time as a datetime object.

        Args:
            reference_date: Reference date to build the datetime

        Returns:
            datetime object for night_charge_time, or None if unavailable
        """
        if not self._night_charge_time_entity:
            return None

        time_state = get_state(self.hass, self._night_charge_time_entity)
        if not time_state or time_state in ["unknown", "unavailable"]:
            return None

        try:
            # Parse time string (format: "HH:MM:SS")
            time_parts = time_state.split(":")
            if len(time_parts) != 3:
                self.logger.warning(
                    f"Invalid night_charge_time format: {time_state}"
                )
                return None

            hour = int(time_parts[0])
            minute = int(time_parts[1])
            second = int(time_parts[2])

            # Create datetime for today at night_charge_time
            night_charge_dt = reference_date.replace(
                hour=hour, minute=minute, second=second, microsecond=0
            )

            # If the time has already passed today, use tomorrow
            if night_charge_dt <= reference_date:
                night_charge_dt += timedelta(days=1)

            return night_charge_dt

        except (ValueError, AttributeError) as e:
            self.logger.warning(
                f"Error parsing night_charge_time '{time_state}': {e}"
            )
            return None

    async def _should_exit_enforcement_mode(self) -> tuple[bool, str]:
        """Check if enforcement mode should be exited."""
        if not self._currently_blocking:
            return False, "Not in enforcement mode"

        # Check 1: Timeout reached
        if self._enforcement_start_time:
            elapsed = (dt_util.now() - self._enforcement_start_time).total_seconds()
            if elapsed > ENFORCEMENT_TIMEOUT_SECONDS:
                return True, f"Enforcement timeout reached ({elapsed / 60:.1f} minutes)"

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
        """Block charging by turning off the charger switch with retry logic."""
        charger_switch = self.config.get(CONF_EV_CHARGER_SWITCH)

        if not charger_switch:
            self.logger.error("Charger switch not configured")
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
                self.logger.warning("Blocked by coordinator")
                self.logger.warning(f"Reason: {coord_reason}")
                return

        self.logger.separator()
        self.logger.warning(f"{self.logger.BLOCKER} Starting blocking sequence")
        self.logger.warning(f"Reason: {reason}")
        self.logger.warning(f"Timestamp: {dt_util.now().strftime('%Y-%m-%d %H:%M:%S')}")

        # Check for potential conflicts
        if self.night_smart_charge and self.night_smart_charge.is_night_charge_active():
            night_mode = self.night_smart_charge.get_active_mode()
            self.logger.warning(
                f"Conflict detected: Night Smart Charge is active (mode: {night_mode})"
            )
            self.logger.warning("Smart Blocker will override Night Smart Charge")

        # Retry logic with verification
        for attempt in range(1, SMART_BLOCKER_RETRY_ATTEMPTS + 1):
            self.logger.warning(f"Blocking attempt {attempt}/{SMART_BLOCKER_RETRY_ATTEMPTS}")

            # Get current state before turning off
            current_state = self.hass.states.get(charger_switch)
            current_status = current_state.state if current_state else "unknown"
            self.logger.warning(f"Current charger state: {current_status}")

            # Turn off the charger
            await self.hass.services.async_call(
                "switch",
                "turn_off",
                {"entity_id": charger_switch},
                blocking=True,
            )
            self.logger.warning(f"Sent turn_off command to {charger_switch}")

            # Wait for state to propagate
            await asyncio.sleep(2)

            # Verify charger is actually OFF
            verify_state = self.hass.states.get(charger_switch)
            verify_status = verify_state.state if verify_state else "unknown"
            self.logger.warning(f"Verification: charger state is now '{verify_status}'")

            if verify_status == STATE_OFF:
                self.logger.success("Charger successfully turned OFF")
                self.logger.info(f"Attempt: {attempt}/{SMART_BLOCKER_RETRY_ATTEMPTS}")
                self.logger.info("Enforcement: ACTIVE (continuous monitoring enabled)")
                self.logger.info(
                    f"Enforcement timeout: {ENFORCEMENT_TIMEOUT_SECONDS / 60:.0f} minutes"
                )

                # Set enforcement flag and timestamp
                self._currently_blocking = True
                self._enforcement_start_time = dt_util.now()

                # Send persistent notification
                await self.hass.services.async_call(
                    "persistent_notification",
                    "create",
                    {
                        "title": "⚡ EV Smart Charger: Charging Blocked",
                        "message": f"Charging has been automatically blocked.\n\n"
                        f"**Reason:** {reason}\n\n"
                        f"**Timestamp:** {dt_util.now().strftime('%H:%M:%S')}\n\n"
                        f"To override this behavior, enable 'Forza Ricarica' or disable 'Smart Charger Blocker'.\n\n"
                        f"**Continuous monitoring:** Any external attempt to re-enable charging will be immediately blocked.",
                        "notification_id": f"evsc_blocked_{int(dt_util.now().timestamp())}",
                    },
                    blocking=False,
                )

                self.logger.separator()
                return
            else:
                self.logger.error(
                    f"Charger still ON after attempt {attempt}"
                )
                self.logger.error(f"Expected: {STATE_OFF}, Actual: {verify_status}")

                if attempt < SMART_BLOCKER_RETRY_ATTEMPTS:
                    retry_delay = SMART_BLOCKER_RETRY_DELAYS[attempt - 1]
                    self.logger.error(f"Retrying in {retry_delay} seconds...")
                    await asyncio.sleep(retry_delay)
                else:
                    self.logger.error("All attempts exhausted!")
                    self.logger.error(
                        f"Charger remains ON after {SMART_BLOCKER_RETRY_ATTEMPTS} attempts"
                    )
                    self.logger.error("Possible causes:")
                    self.logger.error("1. Charger switch entity not responding to commands")
                    self.logger.error("2. External automation overriding this action")
                    self.logger.error("3. Charger hardware issue")
                    self.logger.error("4. Home Assistant service call failure")

                    # Send error notification
                    await self.hass.services.async_call(
                        "persistent_notification",
                        "create",
                        {
                            "title": "⚠️ EV Smart Charger: Blocking Failed",
                            "message": f"Failed to block charging after {SMART_BLOCKER_RETRY_ATTEMPTS} attempts.\n\n"
                            f"**Reason:** {reason}\n\n"
                            f"**Issue:** Charger switch did not respond to turn_off commands.\n\n"
                            f"Please check:\n"
                            f"- Charger switch entity is functioning\n"
                            f"- No conflicting automations\n"
                            f"- Charger hardware status",
                            "notification_id": f"evsc_block_failed_{int(dt_util.now().timestamp())}",
                        },
                        blocking=False,
                    )
                    self.logger.separator()
                    return


async def async_setup_automations(
    hass: HomeAssistant,
    entry_id: str,
    config: dict,
    night_smart_charge=None,
    coordinator=None,
) -> dict:
    """Set up all automations for the integration."""
    automations = {}

    # Set up Smart Charger Blocker with dependency injection
    smart_blocker = SmartChargerBlocker(
        hass, entry_id, config, night_smart_charge, coordinator
    )
    await smart_blocker.async_setup()
    automations["smart_blocker"] = smart_blocker

    return automations


async def async_remove_automations(automations: dict) -> None:
    """Remove all automations."""
    for automation in automations.values():
        await automation.async_remove()

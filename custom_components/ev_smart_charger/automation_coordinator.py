"""Automation Coordinator for EV Smart Charger."""
from __future__ import annotations
import logging
from homeassistant.core import HomeAssistant
from homeassistant.const import STATE_ON
from homeassistant.util import dt as dt_util

from .runtime import EVSCRuntimeData
from .const import (
    PRIORITY_OVERRIDE,
    PRIORITY_BOOST_CHARGE,
    PRIORITY_SMART_BLOCKER,
    PRIORITY_NIGHT_CHARGE,
    PRIORITY_BALANCER,
    PRIORITY_SOLAR_SURPLUS,
)

_LOGGER = logging.getLogger(__name__)

__all__ = [
    "AutomationCoordinator",
    "PRIORITY_OVERRIDE",
    "PRIORITY_BOOST_CHARGE",
    "PRIORITY_SMART_BLOCKER",
    "PRIORITY_NIGHT_CHARGE",
    "PRIORITY_BALANCER",
    "PRIORITY_SOLAR_SURPLUS",
]


class AutomationCoordinator:
    """Coordinates all automations to prevent conflicts."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry_id: str,
        runtime_data: EVSCRuntimeData | None = None,
    ) -> None:
        """Initialize the coordinator."""
        self.hass = hass
        self.entry_id = entry_id
        self._runtime_data = runtime_data
        self._active_automation = None
        self._last_action = None
        self._last_action_time = None
        self._action_history = []  # Track recent actions for debugging

    def _find_entity_by_suffix(self, suffix: str) -> str | None:
        """Resolve an integration-owned entity from runtime data."""
        if self._runtime_data is None:
            return None
        return self._runtime_data.get_entity_id(suffix)

    def _is_override_active(self) -> bool:
        """Check if the override switch (Forza Ricarica) is active."""
        forza_ricarica_entity = self._find_entity_by_suffix("evsc_forza_ricarica")
        if forza_ricarica_entity:
            state = self.hass.states.get(forza_ricarica_entity)
            if state and state.state == STATE_ON:
                return True
        return False

    async def request_charger_action(
        self,
        automation_name: str,
        action: str,  # "turn_on" or "turn_off"
        reason: str,
        priority: int,
    ) -> tuple[bool, str]:
        """
        Centralized charger control coordination.

        Returns:
            tuple[bool, str]: (allowed, reason)
                - allowed: True if action is allowed, False if blocked
                - reason: Explanation of the decision
        """
        _LOGGER.debug(f"[Coordinator] {automation_name} requests {action}: {reason} (priority={priority})")

        # Check override switch first
        if self._is_override_active():
            if action == "turn_off":
                decision_reason = "Override active (Forza Ricarica ON) - blocking not allowed"
                _LOGGER.info(f"⚠️ [Coordinator] {automation_name} blocked: {decision_reason}")
                self._log_action_denied(automation_name, action, reason, priority, decision_reason)
                return False, decision_reason
            else:
                # Override allows turn_on from any automation
                decision_reason = "Override active (Forza Ricarica ON) - allowing turn_on"
                _LOGGER.info(f"✅ [Coordinator] {automation_name} allowed: {decision_reason}")
                self._log_action_allowed(automation_name, action, reason, priority)
                return True, decision_reason

        active = self._active_automation
        if active:
            if active["name"] == automation_name:
                self._active_automation = {
                    "name": automation_name,
                    "priority": priority,
                    "reason": reason,
                    "action": action,
                    "timestamp": dt_util.now(),
                }
                self._last_action = action
                self._last_action_time = dt_util.now()
                decision_reason = "Action allowed (existing owner)"
                self._log_action_allowed(automation_name, action, reason, priority)
                return True, decision_reason

            if priority >= active["priority"]:
                decision_reason = (
                    f"Blocked by active automation: {active['name']} "
                    f"(priority {active['priority']})"
                )
                _LOGGER.info(f"⚠️ [Coordinator] {automation_name} blocked by {active['name']}")
                _LOGGER.debug(f"   Current priority: {active['priority']}, Requested: {priority}")
                _LOGGER.debug(f"   Current action: {active['action']}, Requested: {action}")
                self._log_action_denied(automation_name, action, reason, priority, decision_reason)
                return False, decision_reason

            _LOGGER.info(
                "🔁 [Coordinator] %s preempting %s (priority=%s -> %s)",
                automation_name,
                active["name"],
                active["priority"],
                priority,
            )

        # Allow the action
        self._active_automation = {
            "name": automation_name,
            "priority": priority,
            "reason": reason,
            "action": action,
            "timestamp": dt_util.now(),
        }
        self._last_action = action
        self._last_action_time = dt_util.now()

        decision_reason = "Action allowed"
        _LOGGER.info(f"✅ [Coordinator] {automation_name} taking control (priority={priority})")
        _LOGGER.debug(f"   Action: {action}, Reason: {reason}")
        self._log_action_allowed(automation_name, action, reason, priority)

        return True, decision_reason

    def release_control(self, automation_name: str, reason: str = "") -> None:
        """Release control from an automation."""
        if self._active_automation and self._active_automation["name"] == automation_name:
            _LOGGER.info(f"🔓 [Coordinator] {automation_name} releasing control")
            if reason:
                _LOGGER.debug(f"   Reason: {reason}")
            self._active_automation = None

    def get_active_automation(self) -> dict | None:
        """Get information about currently active automation."""
        return self._active_automation

    def get_active_automation_name(self) -> str | None:
        """Return the name of the active automation owner, if any."""
        if self._active_automation:
            return self._active_automation["name"]
        return None

    def is_automation_active(self, automation_name: str) -> bool:
        """Check if a specific automation is currently in control."""
        if self._active_automation:
            return self._active_automation["name"] == automation_name
        return False

    def is_controlled_by_other(self, automation_name: str) -> bool:
        """Return True when another automation currently owns the session."""
        active_name = self.get_active_automation_name()
        return active_name is not None and active_name != automation_name

    def _log_action_allowed(self, automation_name: str, action: str, reason: str, priority: int) -> None:
        """Log an allowed action to history."""
        self._action_history.append({
            "timestamp": dt_util.now(),
            "automation": automation_name,
            "action": action,
            "reason": reason,
            "priority": priority,
            "result": "allowed",
        })
        # Keep only last 50 actions
        if len(self._action_history) > 50:
            self._action_history.pop(0)

    def _log_action_denied(
        self,
        automation_name: str,
        action: str,
        reason: str,
        priority: int,
        denial_reason: str,
    ) -> None:
        """Log a denied action to history."""
        self._action_history.append({
            "timestamp": dt_util.now(),
            "automation": automation_name,
            "action": action,
            "reason": reason,
            "priority": priority,
            "result": "denied",
            "denial_reason": denial_reason,
        })
        # Keep only last 50 actions
        if len(self._action_history) > 50:
            self._action_history.pop(0)

    def get_action_history(self, limit: int = 10) -> list[dict]:
        """Get recent action history for debugging."""
        return self._action_history[-limit:] if limit > 0 else self._action_history

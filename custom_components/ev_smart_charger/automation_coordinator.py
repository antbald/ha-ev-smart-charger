"""Automation Coordinator to prevent conflicts between automations."""
from __future__ import annotations
import logging
from homeassistant.core import HomeAssistant
from homeassistant.const import STATE_ON
from homeassistant.util import dt as dt_util

from .utils.entity_registry_service import EntityRegistryService

_LOGGER = logging.getLogger(__name__)

# Priority levels for automations (lower number = higher priority)
PRIORITY_OVERRIDE = 1  # evsc_forza_ricarica (always wins)
PRIORITY_SMART_BLOCKER = 2  # Smart Charger Blocker (safety rules)
PRIORITY_NIGHT_CHARGE = 3  # Night Smart Charge (scheduled charging)
PRIORITY_BALANCER = 4  # Priority Balancer (EV vs Home battery)
PRIORITY_SOLAR_SURPLUS = 5  # Solar Surplus (optimization)


class AutomationCoordinator:
    """Coordinates all automations to prevent conflicts."""

    def __init__(self, hass: HomeAssistant, entry_id: str) -> None:
        """Initialize the coordinator."""
        self.hass = hass
        self.entry_id = entry_id
        self._registry_service = EntityRegistryService(hass, entry_id)
        self._active_automation = None
        self._last_action = None
        self._last_action_time = None
        self._action_history = []  # Track recent actions for debugging

    def _find_entity_by_suffix(self, suffix: str) -> str | None:
        """Find entity ID by suffix using EntityRegistryService."""
        return self._registry_service.find_by_suffix_filtered(suffix)

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

        # Check priority against currently active automation
        if self._active_automation:
            if priority > self._active_automation["priority"]:
                # Lower priority (higher number) - check if it conflicts
                if self._would_conflict(action):
                    decision_reason = f"Blocked by higher priority automation: {self._active_automation['name']}"
                    _LOGGER.info(f"⚠️ [Coordinator] {automation_name} blocked by {self._active_automation['name']}")
                    _LOGGER.debug(f"   Current priority: {self._active_automation['priority']}, Requested: {priority}")
                    _LOGGER.debug(f"   Current action: {self._active_automation['action']}, Requested: {action}")
                    self._log_action_denied(automation_name, action, reason, priority, decision_reason)
                    return False, decision_reason

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

    def _would_conflict(self, requested_action: str) -> bool:
        """Check if requested action would conflict with current active automation's action."""
        if not self._active_automation:
            return False

        current_action = self._active_automation.get("action")

        # Conflict if opposite actions (turn_on vs turn_off)
        if current_action == "turn_off" and requested_action == "turn_on":
            return True
        if current_action == "turn_on" and requested_action == "turn_off":
            return True

        return False

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

    def is_automation_active(self, automation_name: str) -> bool:
        """Check if a specific automation is currently in control."""
        if self._active_automation:
            return self._active_automation["name"] == automation_name
        return False

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

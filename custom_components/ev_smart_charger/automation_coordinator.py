"""Automation Coordinator for EV Smart Charger."""
from __future__ import annotations
from collections import deque
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
from .utils.logging_helper import EVSCLogger

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

    _ACTION_HISTORY_LIMIT = 200
    _SNAPSHOT_HISTORY_LIMIT = 10

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
        self._last_denial = None
        self._last_release = None
        self._action_history = deque(maxlen=self._ACTION_HISTORY_LIMIT)
        self._event_logger = EVSCLogger("COORDINATOR")

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

    def _serialize_timestamp(self, timestamp):
        """Return an ISO timestamp or None."""
        if timestamp is None:
            return None
        return timestamp.isoformat()

    def _owner_health_snapshot(self, owner_name: str | None) -> str:
        """Return best-effort health information for the active owner."""
        if owner_name is None or self._runtime_data is None:
            return "unknown"

        if owner_name == "Smart Charger Blocker":
            blocker = self._runtime_data.smart_blocker
            if blocker is None:
                return "unknown"
            return (
                "active"
                if (
                    getattr(blocker, "_currently_blocking", False)
                    or getattr(blocker, "_blocking_sequence_in_progress", False)
                )
                else "stale"
            )

        if owner_name == "Night Smart Charge":
            automation = self._runtime_data.night_smart_charge
            if automation is None:
                return "unknown"
            return "active" if automation.is_active() else "stale"

        if owner_name == "Boost Charge":
            automation = self._runtime_data.boost_charge
            if automation is None:
                return "unknown"
            return "active" if automation.is_active() else "stale"

        return "unknown"

    def _snapshot_active_automation(self) -> dict | None:
        """Return a serialized snapshot of the active owner."""
        if not self._active_automation:
            return None

        active = dict(self._active_automation)
        active["timestamp"] = self._serialize_timestamp(active.get("timestamp"))
        active["health"] = self._owner_health_snapshot(active.get("name"))
        return active

    def _schedule_diagnostic_event(
        self,
        *,
        event: str,
        result: str,
        reason_code: str,
        reason_detail: str,
        action: str,
        requester: str,
        priority: int,
        external_cause: str | None = None,
    ) -> None:
        """Publish a structured diagnostic event asynchronously when available."""
        if self._runtime_data is None or self._runtime_data.diagnostic_manager is None:
            return

        self.hass.async_create_task(
            self._runtime_data.diagnostic_manager.async_emit_event(
                component="Coordinator",
                event=event,
                result=result,
                reason_code=reason_code,
                reason_detail=reason_detail,
                external_cause=external_cause,
                owner=self._snapshot_active_automation(),
                raw_values={
                    "requester": requester,
                    "action": action,
                    "priority": priority,
                },
            )
        )

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
                self._schedule_diagnostic_event(
                    event="request_charger_action",
                    result="denied",
                    reason_code="manual_override",
                    reason_detail=decision_reason,
                    action=action,
                    requester=automation_name,
                    priority=priority,
                    external_cause="manual_override",
                )
                return False, decision_reason
            else:
                # Override allows turn_on from any automation
                decision_reason = "Override active (Forza Ricarica ON) - allowing turn_on"
                _LOGGER.info(f"✅ [Coordinator] {automation_name} allowed: {decision_reason}")
                self._log_action_allowed(automation_name, action, reason, priority)
                self._schedule_diagnostic_event(
                    event="request_charger_action",
                    result="allowed",
                    reason_code="manual_override",
                    reason_detail=decision_reason,
                    action=action,
                    requester=automation_name,
                    priority=priority,
                    external_cause="manual_override",
                )
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
                self._schedule_diagnostic_event(
                    event="request_charger_action",
                    result="allowed",
                    reason_code="existing_owner",
                    reason_detail=decision_reason,
                    action=action,
                    requester=automation_name,
                    priority=priority,
                )
                return True, decision_reason

            if priority >= active["priority"]:
                owner_health = self._owner_health_snapshot(active["name"])
                decision_reason = (
                    f"Blocked by active automation: {active['name']} "
                    f"(priority {active['priority']}, health={owner_health})"
                )
                _LOGGER.info(f"⚠️ [Coordinator] {automation_name} blocked by {active['name']}")
                _LOGGER.debug(f"   Current priority: {active['priority']}, Requested: {priority}")
                _LOGGER.debug(f"   Current action: {active['action']}, Requested: {action}")
                self._log_action_denied(automation_name, action, reason, priority, decision_reason)
                self._schedule_diagnostic_event(
                    event="request_charger_action",
                    result="denied",
                    reason_code="coordinator_denied",
                    reason_detail=decision_reason,
                    action=action,
                    requester=automation_name,
                    priority=priority,
                    external_cause="stale_owner_detected" if owner_health == "stale" else None,
                )
                return False, decision_reason

            _LOGGER.info(
                "🔁 [Coordinator] %s preempting %s (priority=%s -> %s)",
                automation_name,
                active["name"],
                active["priority"],
                priority,
            )
            self._schedule_diagnostic_event(
                event="request_charger_action",
                result="preempting",
                reason_code="priority_preemption",
                reason_detail=(
                    f"{automation_name} preempting {active['name']} "
                    f"(priority {active['priority']} -> {priority})"
                ),
                action=action,
                requester=automation_name,
                priority=priority,
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
        self._schedule_diagnostic_event(
            event="request_charger_action",
            result="allowed",
            reason_code="control_acquired",
            reason_detail=f"{automation_name} taking control",
            action=action,
            requester=automation_name,
            priority=priority,
        )

        return True, decision_reason

    def release_control(self, automation_name: str, reason: str = "") -> None:
        """Release control from an automation."""
        if self._active_automation and self._active_automation["name"] == automation_name:
            _LOGGER.info(f"🔓 [Coordinator] {automation_name} releasing control")
            if reason:
                _LOGGER.debug(f"   Reason: {reason}")
            self._last_release = {
                "timestamp": self._serialize_timestamp(dt_util.now()),
                "automation": automation_name,
                "reason": reason or None,
            }
            self._schedule_diagnostic_event(
                event="release_control",
                result="released",
                reason_code="control_released",
                reason_detail=reason or "Owner released control",
                action=self._active_automation.get("action", "unknown"),
                requester=automation_name,
                priority=self._active_automation.get("priority", -1),
            )
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

    def get_recent_history(self, limit: int = 10) -> list[dict]:
        """Return recent coordinator decisions as plain dicts."""
        history = list(self._action_history)
        if limit > 0:
            history = history[-limit:]
        return history

    def get_debug_snapshot(self) -> dict:
        """Return coordinator ownership snapshot for diagnostics."""
        return {
            "active_automation": self._snapshot_active_automation(),
            "last_action": self._last_action,
            "last_action_time": self._serialize_timestamp(self._last_action_time),
            "owner_health": self._owner_health_snapshot(self.get_active_automation_name()),
            "last_denial": self._last_denial,
            "last_release": self._last_release,
            "recent_history": self.get_recent_history(self._SNAPSHOT_HISTORY_LIMIT),
        }

    def _log_action_allowed(self, automation_name: str, action: str, reason: str, priority: int) -> None:
        """Log an allowed action to history."""
        entry = {
            "timestamp": self._serialize_timestamp(dt_util.now()),
            "automation": automation_name,
            "action": action,
            "reason": reason,
            "priority": priority,
            "result": "allowed",
            "active_owner_health": self._owner_health_snapshot(self.get_active_automation_name()),
        }
        self._action_history.append(entry)
        self._event_logger.event(
            event="coordinator_action",
            result="allowed",
            reason_code="control_acquired",
            reason_detail=reason,
            owner=self._snapshot_active_automation(),
            raw_values=entry,
        )

    def _log_action_denied(
        self,
        automation_name: str,
        action: str,
        reason: str,
        priority: int,
        denial_reason: str,
    ) -> None:
        """Log a denied action to history."""
        entry = {
            "timestamp": self._serialize_timestamp(dt_util.now()),
            "automation": automation_name,
            "action": action,
            "reason": reason,
            "priority": priority,
            "result": "denied",
            "denial_reason": denial_reason,
            "active_owner": self.get_active_automation_name(),
            "active_owner_health": self._owner_health_snapshot(self.get_active_automation_name()),
        }
        self._last_denial = entry
        self._action_history.append(entry)
        self._event_logger.event(
            event="coordinator_action",
            result="denied",
            reason_code="coordinator_denied",
            reason_detail=denial_reason,
            owner=self._snapshot_active_automation(),
            raw_values=entry,
            severity="warning",
        )

    def get_action_history(self, limit: int = 10) -> list[dict]:
        """Get recent action history for debugging."""
        return self.get_recent_history(limit=limit)

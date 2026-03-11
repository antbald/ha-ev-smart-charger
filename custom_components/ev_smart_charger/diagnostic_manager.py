"""Unified diagnostics manager for EV Smart Charger."""
from __future__ import annotations

from collections import deque
from datetime import datetime
from typing import Any

from homeassistant.const import STATE_ON
from homeassistant.core import HomeAssistant, State, callback
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.util import dt as dt_util

from .const import (
    HELPER_DIAGNOSTIC_SENSOR_SUFFIX,
    HELPER_TRACE_LOGGING_ENABLED_SUFFIX,
)
from .runtime import EVSCRuntimeData
from .utils.logging_helper import EVSCLogger


class DiagnosticManager:
    """Publish unified runtime diagnostics and structured events."""

    _RECENT_EVENTS_LIMIT = 15
    _COORDINATOR_HISTORY_LIMIT = 10

    def __init__(
        self,
        hass: HomeAssistant,
        entry_id: str,
        runtime_data: EVSCRuntimeData,
    ) -> None:
        """Initialize diagnostics manager."""
        self.hass = hass
        self.entry_id = entry_id
        self._runtime_data = runtime_data
        self._logger = EVSCLogger("DIAGNOSTICS")

        self._diagnostic_sensor_entity: str | None = None
        self._diagnostic_sensor_obj = None
        self._trace_switch_entity: str | None = None
        self._trace_switch_unsub = None

        self._recent_events: deque[dict[str, Any]] = deque(maxlen=self._RECENT_EVENTS_LIMIT)
        self._state = "Ready"
        self._attributes: dict[str, Any] = {
            "active_owner": None,
            "active_owner_since": None,
            "active_owner_health": "unknown",
            "last_decision_component": None,
            "last_decision_result": None,
            "last_reason_code": None,
            "last_reason_detail": None,
            "last_external_cause": None,
            "last_denial": None,
            "last_release": None,
            "trace_enabled": False,
            "log_file_path": None,
            "recent_events": [],
            "coordinator_history": [],
            "last_update": None,
        }

    async def async_setup(self) -> None:
        """Resolve runtime entities and publish initial state."""
        self._diagnostic_sensor_entity = self._runtime_data.get_entity_id(
            HELPER_DIAGNOSTIC_SENSOR_SUFFIX
        )
        self._diagnostic_sensor_obj = self._runtime_data.get_entity(
            HELPER_DIAGNOSTIC_SENSOR_SUFFIX
        )
        self._trace_switch_entity = self._runtime_data.get_entity_id(
            HELPER_TRACE_LOGGING_ENABLED_SUFFIX
        )

        if self._trace_switch_entity:
            self._trace_switch_unsub = async_track_state_change_event(
                self.hass,
                self._trace_switch_entity,
                self._async_trace_switch_changed,
            )

        await self.async_refresh()

    async def async_remove(self) -> None:
        """Cleanup listeners."""
        if self._trace_switch_unsub:
            self._trace_switch_unsub()
            self._trace_switch_unsub = None

    def is_trace_enabled(self) -> bool:
        """Return whether deep trace logging is enabled."""
        if not self._trace_switch_entity:
            return False
        state = self.hass.states.get(self._trace_switch_entity)
        return state is not None and state.state == STATE_ON

    def _get_log_file_path(self) -> str | None:
        """Return current log file path when available."""
        if not EVSCLogger.is_global_file_logging_enabled():
            return None
        log_manager = self._runtime_data.log_manager
        if log_manager and hasattr(log_manager, "get_log_file_path"):
            return log_manager.get_log_file_path()
        return EVSCLogger.get_global_log_file_path()

    def _serialize(self, value: Any) -> Any:
        """Convert runtime values into Home Assistant state-safe structures."""
        if isinstance(value, datetime):
            return value.isoformat()
        if isinstance(value, dict):
            return {str(key): self._serialize(inner) for key, inner in value.items()}
        if isinstance(value, (list, tuple, deque)):
            return [self._serialize(item) for item in value]
        return value

    def _coordinator_snapshot(self) -> dict[str, Any]:
        """Return normalized coordinator snapshot for attributes."""
        coordinator = self._runtime_data.coordinator
        if coordinator and hasattr(coordinator, "get_debug_snapshot"):
            return self._serialize(coordinator.get_debug_snapshot())
        return {}

    async def async_refresh(self) -> None:
        """Refresh attributes derived from runtime state."""
        snapshot = self._coordinator_snapshot()
        active = snapshot.get("active_automation") or {}

        self._attributes.update(
            {
                "active_owner": active.get("name"),
                "active_owner_since": active.get("timestamp"),
                "active_owner_health": snapshot.get("owner_health", "unknown"),
                "last_denial": snapshot.get("last_denial"),
                "last_release": snapshot.get("last_release"),
                "trace_enabled": self.is_trace_enabled(),
                "log_file_path": self._get_log_file_path(),
                "coordinator_history": snapshot.get("recent_history", [])[
                    -self._COORDINATOR_HISTORY_LIMIT :
                ],
                "recent_events": list(self._recent_events),
                "last_update": dt_util.now().isoformat(),
            }
        )
        await self._publish()

    async def async_emit_event(
        self,
        component: str,
        event: str,
        result: str,
        reason_code: str,
        *,
        reason_detail: str = "",
        owner: Any = None,
        trigger: str | None = None,
        entity_ids: dict[str, Any] | list[str] | None = None,
        raw_values: dict[str, Any] | list[Any] | None = None,
        external_cause: str | None = None,
        severity: str = "info",
        session_id: str | None = None,
        trace_payload: dict[str, Any] | None = None,
        extra: dict[str, Any] | None = None,
    ) -> str:
        """Emit a structured log event and publish it to the diagnostic sensor."""
        event_logger = EVSCLogger(component)
        decision_id = event_logger.event(
            event=event,
            result=result,
            reason_code=reason_code,
            reason_detail=reason_detail,
            owner=owner,
            trigger=trigger,
            entity_ids=entity_ids,
            raw_values=raw_values,
            external_cause=external_cause,
            severity=severity,
            session_id=session_id or f"{self.entry_id}:{event_logger._component_slug}",
            extra=extra,
        )

        if self.is_trace_enabled():
            event_logger.trace_event(
                title=event,
                payload={
                    "result": result,
                    "reason_code": reason_code,
                    "reason_detail": reason_detail,
                    "owner": owner,
                    "trigger": trigger,
                    "external_cause": external_cause,
                    "entity_ids": entity_ids,
                    "raw_values": raw_values,
                    **(trace_payload or {}),
                },
                decision_id=decision_id,
                session_id=session_id or f"{self.entry_id}:{event_logger._component_slug}",
            )

        event_data = self._serialize(
            {
                "timestamp": dt_util.now().isoformat(),
                "component": component,
                "event": event,
                "result": result,
                "reason_code": reason_code,
                "reason_detail": reason_detail,
                "external_cause": external_cause,
                "owner": owner,
                "trigger": trigger,
                "decision_id": decision_id,
            }
        )
        self._recent_events.append(event_data)
        self._state = f"{component}: {result}"
        self._attributes.update(
            {
                "last_decision_component": component,
                "last_decision_result": result,
                "last_reason_code": reason_code,
                "last_reason_detail": reason_detail or None,
                "last_external_cause": external_cause,
                "recent_events": list(self._recent_events),
            }
        )
        await self.async_refresh()
        return decision_id

    async def _publish(self) -> None:
        """Publish the current diagnostic state to the HA sensor entity."""
        if self._diagnostic_sensor_obj and hasattr(self._diagnostic_sensor_obj, "async_publish"):
            await self._diagnostic_sensor_obj.async_publish(self._state, self._attributes)
            return
        if self._diagnostic_sensor_entity:
            self.hass.states.async_set(self._diagnostic_sensor_entity, self._state, self._attributes)

    async def _async_handle_trace_switch_changed(self, enabled: bool) -> None:
        """Persist trace toggle changes through the unified diagnostic pipeline."""
        await self.async_emit_event(
            component="Diagnostics",
            event="trace_mode_changed",
            result="enabled" if enabled else "disabled",
            reason_code="manual_toggle",
            reason_detail="Trace logging switch changed",
            severity="info",
            raw_values={
                "trace_enabled": enabled,
                "entity": self._trace_switch_entity,
            },
        )

    @callback
    def _async_trace_switch_changed(self, event) -> None:
        """Handle trace mode switch changes."""
        new_state: State | None = event.data.get("new_state")
        old_state: State | None = event.data.get("old_state")
        if not new_state or (old_state and old_state.state == new_state.state):
            return

        enabled = new_state.state == STATE_ON
        self.hass.async_create_task(self._async_handle_trace_switch_changed(enabled))

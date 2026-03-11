"""Tests for unified diagnostic manager."""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from homeassistant.core import State

from custom_components.ev_smart_charger.diagnostic_manager import DiagnosticManager
from custom_components.ev_smart_charger.runtime import EVSCRuntimeData


async def test_diagnostic_manager_publishes_event_with_coordinator_snapshot(hass):
    """Structured events should update the HA diagnostic sensor with coordinator context."""
    runtime_data = EVSCRuntimeData(config={}, expected_entity_count=0)
    diagnostic_sensor = Mock(async_publish=AsyncMock())
    runtime_data.register_entity("evsc_diagnostic", "sensor.evsc_diagnostic", diagnostic_sensor)
    runtime_data.register_entity("evsc_trace_logging_enabled", "switch.evsc_trace_logging", object())
    runtime_data.log_manager = Mock(get_log_file_path=Mock(return_value="/tmp/evsc.log"))
    runtime_data.coordinator = Mock(
        get_debug_snapshot=Mock(
            return_value={
                "active_automation": {
                    "name": "Smart Charger Blocker",
                    "timestamp": "2026-03-11T00:00:47+01:00",
                    "health": "stale",
                },
                "owner_health": "stale",
                "last_denial": {"denial_reason": "Blocked by active automation"},
                "last_release": {"reason": "Released"},
                "recent_history": [{"automation": "Night Smart Charge", "result": "denied"}],
            }
        )
    )
    hass.states.async_set("switch.evsc_trace_logging", "off")

    manager = DiagnosticManager(hass, "entry-1", runtime_data)
    await manager.async_setup()
    diagnostic_sensor.async_publish.reset_mock()

    await manager.async_emit_event(
        component="Night Smart Charge",
        event="coordinator_denied",
        result="denied",
        reason_code="coordinator_denied",
        reason_detail="Blocked by active automation: Smart Charger Blocker",
        raw_values={"requested_action": "turn_on"},
    )

    diagnostic_sensor.async_publish.assert_awaited()
    state, attributes = diagnostic_sensor.async_publish.await_args.args
    assert state == "Night Smart Charge: denied"
    assert attributes["active_owner"] == "Smart Charger Blocker"
    assert attributes["active_owner_health"] == "stale"
    assert attributes["last_decision_component"] == "Night Smart Charge"
    assert attributes["last_reason_code"] == "coordinator_denied"
    assert attributes["log_file_path"] is None
    assert len(attributes["recent_events"]) == 1


async def test_diagnostic_manager_trace_toggle_updates_sensor(hass):
    """Trace logging toggle should update sensor attributes and emit a manual toggle event."""
    runtime_data = EVSCRuntimeData(config={}, expected_entity_count=0)
    diagnostic_sensor = Mock(async_publish=AsyncMock())
    runtime_data.register_entity("evsc_diagnostic", "sensor.evsc_diagnostic", diagnostic_sensor)
    runtime_data.register_entity("evsc_trace_logging_enabled", "switch.evsc_trace_logging", object())
    runtime_data.coordinator = Mock(get_debug_snapshot=Mock(return_value={}))

    hass.states.async_set("switch.evsc_trace_logging", "off")
    manager = DiagnosticManager(hass, "entry-1", runtime_data)
    await manager.async_setup()
    diagnostic_sensor.async_publish.reset_mock()

    old_state = State("switch.evsc_trace_logging", "off")
    hass.states.async_set("switch.evsc_trace_logging", "on")
    new_state = hass.states.get("switch.evsc_trace_logging")

    manager._async_trace_switch_changed(
        SimpleNamespace(
            data={
                "old_state": old_state,
                "new_state": new_state,
            }
        )
    )
    await hass.async_block_till_done()

    state, attributes = diagnostic_sensor.async_publish.await_args.args
    assert state == "Diagnostics: enabled"
    assert attributes["trace_enabled"] is True
    assert attributes["last_reason_code"] == "manual_toggle"
    assert attributes["last_external_cause"] is None

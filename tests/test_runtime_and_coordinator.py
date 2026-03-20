"""Tests for runtime helpers and automation coordinator."""
from __future__ import annotations

from unittest.mock import Mock

from custom_components.ev_smart_charger.automation_coordinator import (
    AutomationCoordinator,
    PRIORITY_BOOST_CHARGE,
    PRIORITY_NIGHT_CHARGE,
    PRIORITY_SMART_BLOCKER,
)
from custom_components.ev_smart_charger.runtime import EVSCRuntimeData


def test_runtime_data_registers_entities_and_exposes_lookup():
    """Runtime data tracks entity ids, objects, and registration progress."""
    runtime_data = EVSCRuntimeData(config={}, expected_entity_count=2)
    entity_one = Mock()
    entity_two = Mock()

    runtime_data.register_entity("evsc_forza_ricarica", "switch.entry_evsc_forza_ricarica", entity_one)
    assert runtime_data.registration_event.is_set() is False
    assert runtime_data.get_entity_id("evsc_forza_ricarica") == "switch.entry_evsc_forza_ricarica"
    assert runtime_data.get_entity("evsc_forza_ricarica") is entity_one

    runtime_data.register_entity("evsc_priority_daily_state", "sensor.entry_evsc_priority_daily_state", entity_two)
    assert runtime_data.registration_event.is_set() is True
    assert runtime_data.registered_entity_count == 2


async def test_automation_coordinator_uses_runtime_entity_for_override(hass):
    """Override checks should use runtime_data entities instead of global scans."""
    runtime_data = EVSCRuntimeData(config={}, expected_entity_count=1)
    runtime_data.register_entity(
        "evsc_forza_ricarica",
        "switch.entry_evsc_forza_ricarica",
        Mock(),
    )
    hass.states.async_set("switch.entry_evsc_forza_ricarica", "on")

    coordinator = AutomationCoordinator(hass, "entry-id", runtime_data=runtime_data)

    allowed, reason = await coordinator.request_charger_action(
        automation_name="Smart Blocker",
        action="turn_off",
        reason="Nighttime block",
        priority=PRIORITY_SMART_BLOCKER,
    )
    assert allowed is False
    assert "Override active" in reason

    allowed, reason = await coordinator.request_charger_action(
        automation_name="Night Smart Charge",
        action="turn_on",
        reason="Scheduled night charge",
        priority=PRIORITY_NIGHT_CHARGE,
    )
    assert allowed is True
    assert "Override active" in reason


async def test_automation_coordinator_blocks_lower_priority_conflicts(hass):
    """A lower-priority conflicting action is denied until control is released."""
    coordinator = AutomationCoordinator(hass, "entry-id")

    allowed, _ = await coordinator.request_charger_action(
        automation_name="Boost Charge",
        action="turn_on",
        reason="User requested boost",
        priority=PRIORITY_BOOST_CHARGE,
    )
    assert allowed is True
    assert coordinator.is_automation_active("Boost Charge") is True

    allowed, reason = await coordinator.request_charger_action(
        automation_name="Smart Blocker",
        action="turn_off",
        reason="Nighttime block",
        priority=PRIORITY_SMART_BLOCKER,
    )
    assert allowed is False
    assert "Boost Charge" in reason
    assert coordinator.get_active_automation()["name"] == "Boost Charge"

    coordinator.release_control("Boost Charge", "Boost completed")
    assert coordinator.get_active_automation() is None

    # get_action_history() was removed in v1.6.0 (dead method)
    # Verify the coordinator still tracks actions internally
    assert len(coordinator._action_history) >= 2
    assert {item["result"] for item in coordinator._action_history} == {"allowed", "denied"}

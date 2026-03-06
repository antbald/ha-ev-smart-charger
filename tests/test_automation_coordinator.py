"""Tests for the automation coordinator."""
from __future__ import annotations

import pytest

from custom_components.ev_smart_charger.automation_coordinator import (
    AutomationCoordinator,
    PRIORITY_BOOST_CHARGE,
    PRIORITY_SOLAR_SURPLUS,
)
from custom_components.ev_smart_charger.runtime import EVSCRuntimeData


@pytest.fixture
def runtime_data() -> EVSCRuntimeData:
    """Create runtime data with the override entity registered."""
    data = EVSCRuntimeData(config={}, expected_entity_count=1)
    data.register_entity("evsc_forza_ricarica", "switch.evsc_override", object())
    return data


async def test_override_allows_turn_on_but_blocks_turn_off(hass, runtime_data) -> None:
    """Forza Ricarica ON allows start requests and blocks stop requests."""
    hass.states.async_set("switch.evsc_override", "on")
    coordinator = AutomationCoordinator(hass, "entry-1", runtime_data=runtime_data)

    allowed_on, reason_on = await coordinator.request_charger_action(
        "Solar Surplus",
        "turn_on",
        "Surplus available",
        PRIORITY_SOLAR_SURPLUS,
    )
    blocked_off, reason_off = await coordinator.request_charger_action(
        "Solar Surplus",
        "turn_off",
        "Need to stop",
        PRIORITY_SOLAR_SURPLUS,
    )

    assert allowed_on is True
    assert "allowing turn_on" in reason_on
    assert blocked_off is False
    assert "blocking not allowed" in reason_off


async def test_lower_priority_conflicting_action_is_blocked(hass) -> None:
    """Conflicting lower-priority actions are denied while a higher-priority owner is active."""
    coordinator = AutomationCoordinator(hass, "entry-1")

    allowed, _ = await coordinator.request_charger_action(
        "Boost Charge",
        "turn_on",
        "Boost session",
        PRIORITY_BOOST_CHARGE,
    )
    blocked, reason = await coordinator.request_charger_action(
        "Solar Surplus",
        "turn_off",
        "Clouds",
        PRIORITY_SOLAR_SURPLUS,
    )

    assert allowed is True
    assert blocked is False
    assert "Boost Charge" in reason
    assert coordinator.is_automation_active("Boost Charge") is True


async def test_higher_priority_takes_control_and_release_is_owner_only(hass) -> None:
    """A higher-priority automation can replace the active owner and only the owner can release."""
    coordinator = AutomationCoordinator(hass, "entry-1")

    await coordinator.request_charger_action(
        "Solar Surplus",
        "turn_on",
        "Start solar",
        PRIORITY_SOLAR_SURPLUS,
    )
    allowed, _ = await coordinator.request_charger_action(
        "Boost Charge",
        "turn_off",
        "User boost stop",
        PRIORITY_BOOST_CHARGE,
    )

    assert allowed is True
    assert coordinator.get_active_automation()["name"] == "Boost Charge"

    coordinator.release_control("Solar Surplus", "Not owner")
    assert coordinator.get_active_automation()["name"] == "Boost Charge"

    coordinator.release_control("Boost Charge", "Completed")
    assert coordinator.get_active_automation() is None


def test_runtime_lookup_is_entry_scoped_only(hass, runtime_data) -> None:
    """Coordinator helper lookup is resolved strictly from runtime_data."""
    coordinator = AutomationCoordinator(hass, "entry-1", runtime_data=runtime_data)

    entity_id = coordinator._find_entity_by_suffix("evsc_forza_ricarica")

    assert entity_id == "switch.evsc_override"
    assert coordinator._find_entity_by_suffix("missing_suffix") is None


async def test_action_history_limit_and_queries(hass) -> None:
    """Action history is capped and can be queried with a limit."""
    coordinator = AutomationCoordinator(hass, "entry-1")

    for idx in range(55):
        await coordinator.request_charger_action(
            f"Automation {idx}",
            "turn_on",
            f"reason {idx}",
            PRIORITY_SOLAR_SURPLUS,
        )

    history = coordinator.get_action_history(limit=5)

    assert len(coordinator.get_action_history(limit=0)) == 50
    assert len(history) == 5
    assert history[-1]["automation"] == "Automation 54"

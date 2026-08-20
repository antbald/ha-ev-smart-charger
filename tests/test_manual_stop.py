"""Tests for the manual Stop Charging control (v2.10.0 — issue #55)."""
from unittest.mock import AsyncMock

import pytest
from homeassistant.core import Event

from custom_components.ev_smart_charger.automation_coordinator import AutomationCoordinator
from custom_components.ev_smart_charger.const import (
    HELPER_STOP_CHARGING_SUFFIX,
    PRIORITY_NIGHT_CHARGE,
    PRIORITY_OVERRIDE,
    PRIORITY_SOLAR_SURPLUS,
)
from custom_components.ev_smart_charger.manual_stop import ManualStopControl
from custom_components.ev_smart_charger.runtime import EVSCRuntimeData

STOP_ENTITY = "switch.ev_smart_charger_test_evsc_stop_charging"
FORZA_ENTITY = "switch.ev_smart_charger_test_evsc_forza_ricarica"


@pytest.fixture
def runtime_data():
    """Runtime data with the two override switches registered."""
    data = EVSCRuntimeData(config={}, expected_entity_count=100)
    data.entity_ids_by_key[HELPER_STOP_CHARGING_SUFFIX] = STOP_ENTITY
    data.entity_ids_by_key["evsc_forza_ricarica"] = FORZA_ENTITY
    return data


@pytest.fixture
def coordinator(hass, runtime_data):
    """Coordinator wired to the runtime data."""
    return AutomationCoordinator(hass, "test", runtime_data=runtime_data)


@pytest.fixture
def manual_stop(hass, runtime_data, coordinator, mock_charger_controller):
    """ManualStopControl instance with mocked charger controller."""
    control = ManualStopControl(
        hass,
        "test",
        {},
        mock_charger_controller,
        runtime_data=runtime_data,
        coordinator=coordinator,
    )
    runtime_data.manual_stop = control
    return control


# ── Coordinator veto ──────────────────────────────────────────────


async def test_coordinator_denies_turn_on_while_manual_stop_active(hass, coordinator):
    """Every automation turn_on must be denied while the switch is ON."""
    hass.states.async_set(STOP_ENTITY, "on")

    allowed, reason = await coordinator.request_charger_action(
        automation_name="Solar Surplus",
        action="turn_on",
        reason="Surplus available",
        priority=PRIORITY_SOLAR_SURPLUS,
    )

    assert allowed is False
    assert "Manual stop active" in reason


async def test_coordinator_allows_turn_off_while_manual_stop_active(hass, coordinator):
    """turn_off is exactly what the override wants — always allowed."""
    hass.states.async_set(STOP_ENTITY, "on")

    allowed, reason = await coordinator.request_charger_action(
        automation_name="Night Smart Charge",
        action="turn_off",
        reason="Target reached",
        priority=PRIORITY_NIGHT_CHARGE,
    )

    assert allowed is True
    assert "Manual stop active" in reason


async def test_manual_stop_outranks_forza_ricarica(hass, coordinator):
    """A manual stop must win even when Forza Ricarica is also ON."""
    hass.states.async_set(STOP_ENTITY, "on")
    hass.states.async_set(FORZA_ENTITY, "on")

    allowed, reason = await coordinator.request_charger_action(
        automation_name="Solar Surplus",
        action="turn_on",
        reason="Surplus available",
        priority=PRIORITY_SOLAR_SURPLUS,
    )
    assert allowed is False
    assert "Manual stop active" in reason

    # And a stop request is allowed, where Forza Ricarica alone would deny it.
    allowed, _ = await coordinator.request_charger_action(
        automation_name="Smart Charger Blocker",
        action="turn_off",
        reason="Nighttime",
        priority=PRIORITY_OVERRIDE,
    )
    assert allowed is True


async def test_coordinator_unaffected_when_manual_stop_off(hass, coordinator):
    """Switch OFF → byte-for-byte legacy arbitration."""
    hass.states.async_set(STOP_ENTITY, "off")

    allowed, reason = await coordinator.request_charger_action(
        automation_name="Solar Surplus",
        action="turn_on",
        reason="Surplus available",
        priority=PRIORITY_SOLAR_SURPLUS,
    )

    assert allowed is True
    assert reason == "Action allowed"


# ── ManualStopControl behaviour ───────────────────────────────────


def _toggle_event(hass, old, new):
    """Build a state_changed-like event for the stop switch."""
    hass.states.async_set(STOP_ENTITY, new)
    return Event(
        "state_changed",
        {
            "entity_id": STOP_ENTITY,
            "old_state": hass.states.get(STOP_ENTITY).__class__(STOP_ENTITY, old),
            "new_state": hass.states.get(STOP_ENTITY),
        },
    )


async def test_toggle_on_stops_charger_immediately(hass, manual_stop, coordinator):
    """Flipping the switch ON must stop the charger without waiting for a tick."""
    hass.states.async_set(STOP_ENTITY, "off")
    manual_stop._switch_entity = STOP_ENTITY

    await manual_stop._async_switch_changed(_toggle_event(hass, "off", "on"))

    manual_stop.charger_controller.stop_charger.assert_awaited_once()
    assert manual_stop.is_active() is True
    assert coordinator.is_automation_active("Manual Stop") is True


async def test_toggle_off_releases_control_without_restart(hass, manual_stop, coordinator):
    """Flipping the switch OFF releases ownership and starts nothing."""
    hass.states.async_set(STOP_ENTITY, "off")
    manual_stop._switch_entity = STOP_ENTITY
    await manual_stop._async_switch_changed(_toggle_event(hass, "off", "on"))

    await manual_stop._async_switch_changed(_toggle_event(hass, "on", "off"))

    assert coordinator.get_active_automation() is None
    assert manual_stop.is_active() is False
    manual_stop.charger_controller.start_charger.assert_not_called()


async def test_periodic_hold_restops_external_restart(hass, manual_stop):
    """Charging started outside the integration is stopped again by the hold."""
    hass.states.async_set(STOP_ENTITY, "on")
    manual_stop._switch_entity = STOP_ENTITY
    manual_stop.charger_controller.is_charging = AsyncMock(return_value=True)

    await manual_stop._async_periodic_hold_check(None)

    manual_stop.charger_controller.stop_charger.assert_awaited_once()


async def test_periodic_hold_noop_when_not_charging(hass, manual_stop):
    """No redundant stop commands while the charger is already idle."""
    hass.states.async_set(STOP_ENTITY, "on")
    manual_stop._switch_entity = STOP_ENTITY
    manual_stop.charger_controller.is_charging = AsyncMock(return_value=False)

    await manual_stop._async_periodic_hold_check(None)

    manual_stop.charger_controller.stop_charger.assert_not_called()


async def test_periodic_hold_noop_when_switch_off(hass, manual_stop):
    """Switch OFF → the hold is a no-op."""
    hass.states.async_set(STOP_ENTITY, "off")
    manual_stop._switch_entity = STOP_ENTITY
    manual_stop.charger_controller.is_charging = AsyncMock(return_value=True)

    await manual_stop._async_periodic_hold_check(None)

    manual_stop.charger_controller.stop_charger.assert_not_called()


async def test_setup_enforces_hold_when_restored_on(hass, manual_stop):
    """A restart with the switch already ON must re-assert the stop."""
    hass.states.async_set(STOP_ENTITY, "on")

    await manual_stop.async_setup()

    manual_stop.charger_controller.stop_charger.assert_awaited_once()
    await manual_stop.async_remove()


async def test_setup_is_noop_when_switch_off(hass, manual_stop):
    """A restart with the switch OFF must not touch the charger."""
    hass.states.async_set(STOP_ENTITY, "off")

    await manual_stop.async_setup()

    manual_stop.charger_controller.stop_charger.assert_not_called()
    await manual_stop.async_remove()

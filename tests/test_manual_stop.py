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


# ── v2.10.2: Stop Charging / Forza Ricarica interlock ─────────────


@pytest.fixture
def switch_calls(hass):
    """Record switch.turn_off service calls."""
    calls = []

    async def _handler(call):
        calls.append(call.data.get("entity_id"))
        entity_id = call.data.get("entity_id")
        if isinstance(entity_id, str):
            hass.states.async_set(entity_id, "off")

    hass.services.async_register("switch", "turn_off", _handler)
    return calls


async def test_engaging_manual_stop_turns_off_force_charge(
    hass, manual_stop, switch_calls
):
    """The two overrides are opposites — engaging one must clear the other."""
    hass.states.async_set(STOP_ENTITY, "off")
    hass.states.async_set(FORZA_ENTITY, "on")
    manual_stop._switch_entity = STOP_ENTITY
    manual_stop._forza_entity = FORZA_ENTITY

    await manual_stop._async_switch_changed(_toggle_event(hass, "off", "on"))

    assert FORZA_ENTITY in switch_calls
    assert hass.states.get(FORZA_ENTITY).state == "off"
    manual_stop.charger_controller.stop_charger.assert_awaited_once()


async def test_engaging_force_charge_turns_off_manual_stop(
    hass, manual_stop, switch_calls
):
    """The other half of the interlock."""
    hass.states.async_set(STOP_ENTITY, "on")
    hass.states.async_set(FORZA_ENTITY, "off")
    manual_stop._switch_entity = STOP_ENTITY
    manual_stop._forza_entity = FORZA_ENTITY

    hass.states.async_set(FORZA_ENTITY, "on")
    await manual_stop._async_forza_changed(
        Event(
            "state_changed",
            {
                "entity_id": FORZA_ENTITY,
                "old_state": hass.states.get(FORZA_ENTITY).__class__(
                    FORZA_ENTITY, "off"
                ),
                "new_state": hass.states.get(FORZA_ENTITY),
            },
        )
    )

    assert STOP_ENTITY in switch_calls
    assert hass.states.get(STOP_ENTITY).state == "off"


async def test_force_charge_no_op_when_manual_stop_already_off(
    hass, manual_stop, switch_calls
):
    """No spurious service calls when there is nothing to clear."""
    hass.states.async_set(STOP_ENTITY, "off")
    hass.states.async_set(FORZA_ENTITY, "off")
    manual_stop._switch_entity = STOP_ENTITY
    manual_stop._forza_entity = FORZA_ENTITY

    hass.states.async_set(FORZA_ENTITY, "on")
    await manual_stop._async_forza_changed(
        Event(
            "state_changed",
            {
                "entity_id": FORZA_ENTITY,
                "old_state": hass.states.get(FORZA_ENTITY).__class__(
                    FORZA_ENTITY, "off"
                ),
                "new_state": hass.states.get(FORZA_ENTITY),
            },
        )
    )

    assert switch_calls == []


async def test_setup_resolves_both_switches_on(hass, manual_stop, switch_calls):
    """Both restored ON (pre-interlock state): manual stop wins."""
    hass.states.async_set(STOP_ENTITY, "on")
    hass.states.async_set(FORZA_ENTITY, "on")

    await manual_stop.async_setup()

    assert FORZA_ENTITY in switch_calls
    assert hass.states.get(FORZA_ENTITY).state == "off"
    assert hass.states.get(STOP_ENTITY).state == "on"
    manual_stop.charger_controller.stop_charger.assert_awaited_once()
    await manual_stop.async_remove()


# ── v2.11.0: Force Charge auto-disarm on unplug ───────────────────

AUTO_DISARM_ENTITY = "switch.ev_smart_charger_test_evsc_force_charge_auto_disarm"
STATUS_ENTITY = "sensor.charger_status"


def _status_event(hass, old, new):
    """Build a state_changed-like event for the charger status sensor."""
    hass.states.async_set(STATUS_ENTITY, new)
    return Event(
        "state_changed",
        {
            "entity_id": STATUS_ENTITY,
            "old_state": hass.states.get(STATUS_ENTITY).__class__(STATUS_ENTITY, old),
            "new_state": hass.states.get(STATUS_ENTITY),
        },
    )


@pytest.fixture
def auto_disarm(hass, manual_stop):
    """Manual stop wired for the auto-disarm path."""
    manual_stop._switch_entity = STOP_ENTITY
    manual_stop._forza_entity = FORZA_ENTITY
    manual_stop._auto_disarm_entity = AUTO_DISARM_ENTITY
    manual_stop._charger_status_entity = STATUS_ENTITY
    hass.states.async_set(STOP_ENTITY, "off")
    hass.states.async_set(FORZA_ENTITY, "on")
    hass.states.async_set(AUTO_DISARM_ENTITY, "on")
    return manual_stop


async def test_unplug_disarms_force_charge(hass, auto_disarm, switch_calls):
    """Unplugging the EV turns Force Charge off when the setting is ON."""
    await auto_disarm._async_charger_status_changed(
        _status_event(hass, "charger_charging", "charger_free")
    )

    assert FORZA_ENTITY in switch_calls
    assert hass.states.get(FORZA_ENTITY).state == "off"


async def test_unplug_disarms_on_brand_status(hass, auto_disarm, switch_calls):
    """OCPP-style `available` is a disconnect too (v2.9.1 classifier)."""
    await auto_disarm._async_charger_status_changed(
        _status_event(hass, "Charging", "Available")
    )

    assert FORZA_ENTITY in switch_calls


async def test_unplug_no_op_when_setting_off(hass, auto_disarm, switch_calls):
    """Opt-in: with the setting OFF, Force Charge survives the unplug."""
    hass.states.async_set(AUTO_DISARM_ENTITY, "off")

    await auto_disarm._async_charger_status_changed(
        _status_event(hass, "charger_charging", "charger_free")
    )

    assert switch_calls == []
    assert hass.states.get(FORZA_ENTITY).state == "on"


async def test_unavailable_status_does_not_disarm(hass, auto_disarm, switch_calls):
    """A sensor glitch must never cancel a Force Charge the user relies on."""
    await auto_disarm._async_charger_status_changed(
        _status_event(hass, "charger_charging", "unavailable")
    )

    assert switch_calls == []
    assert hass.states.get(FORZA_ENTITY).state == "on"


async def test_disarm_acts_on_the_unplug_edge_only(hass, auto_disarm, switch_calls):
    """Already-disconnected → still disconnected is not an unplug event.

    Otherwise turning Force Charge ON with the cable out (to prepare a later
    session) would be cancelled by the next status refresh.
    """
    await auto_disarm._async_charger_status_changed(
        _status_event(hass, "charger_free", "available")
    )

    assert switch_calls == []
    assert hass.states.get(FORZA_ENTITY).state == "on"


async def test_disarm_no_op_when_force_charge_already_off(
    hass, auto_disarm, switch_calls
):
    """Nothing to disarm → no service call."""
    hass.states.async_set(FORZA_ENTITY, "off")

    await auto_disarm._async_charger_status_changed(
        _status_event(hass, "charger_charging", "charger_free")
    )

    assert switch_calls == []


async def test_setup_skips_status_listener_without_status_sensor(hass, manual_stop):
    """No status sensor mapped → the setting stays inert, setup still succeeds."""
    hass.states.async_set(STOP_ENTITY, "off")
    manual_stop.config = {}

    await manual_stop.async_setup()

    assert manual_stop._status_unsub is None
    await manual_stop.async_remove()

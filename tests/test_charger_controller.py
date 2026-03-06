"""Tests for ChargerController."""
from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest

from custom_components.ev_smart_charger.charger_controller import ChargerController
from custom_components.ev_smart_charger.const import (
    CHARGER_MIN_OPERATION_INTERVAL,
    CONF_EV_CHARGER_CURRENT,
    CONF_EV_CHARGER_SWITCH,
)


@pytest.fixture
def service_recorder(hass):
    """Register fake Home Assistant services used by the controller."""
    calls: list[tuple[str, str, dict]] = []

    async def switch_turn_on(call):
        calls.append(("switch", "turn_on", dict(call.data)))
        hass.states.async_set(call.data["entity_id"], "on")

    async def switch_turn_off(call):
        calls.append(("switch", "turn_off", dict(call.data)))
        hass.states.async_set(call.data["entity_id"], "off")

    async def number_set_value(call):
        calls.append(("number", "set_value", dict(call.data)))
        hass.states.async_set(call.data["entity_id"], str(call.data["value"]))

    async def input_number_set_value(call):
        calls.append(("input_number", "set_value", dict(call.data)))
        hass.states.async_set(call.data["entity_id"], str(call.data["value"]))

    async def select_select_option(call):
        calls.append(("select", "select_option", dict(call.data)))
        hass.states.async_set(call.data["entity_id"], str(call.data["option"]))

    async def input_select_select_option(call):
        calls.append(("input_select", "select_option", dict(call.data)))
        hass.states.async_set(call.data["entity_id"], str(call.data["option"]))

    hass.services.async_register("switch", "turn_on", switch_turn_on)
    hass.services.async_register("switch", "turn_off", switch_turn_off)
    hass.services.async_register("number", "set_value", number_set_value)
    hass.services.async_register("input_number", "set_value", input_number_set_value)
    hass.services.async_register("select", "select_option", select_select_option)
    hass.services.async_register("input_select", "select_option", input_select_select_option)

    return calls


@pytest.fixture
def controller_factory(hass, service_recorder):
    """Create controllers with different current-control domains."""

    def _build(current_entity_id: str = "number.charger_current") -> ChargerController:
        config = {
            CONF_EV_CHARGER_SWITCH: "switch.charger",
            CONF_EV_CHARGER_CURRENT: current_entity_id,
        }
        return ChargerController(hass, "test_entry", config)

    return _build


async def test_initial_state(hass, controller_factory):
    """Controller reads initial switch and current state."""
    hass.states.async_set("switch.charger", "off")
    hass.states.async_set("number.charger_current", "10")
    controller = controller_factory()

    await controller.async_setup()

    assert controller._is_on is False
    assert controller._current_amperage == 10


async def test_start_charger_with_number_control(hass, controller_factory, service_recorder):
    """Starting the charger sets target amperage before turning on."""
    hass.states.async_set("switch.charger", "off")
    hass.states.async_set("number.charger_current", "6")
    controller = controller_factory()
    await controller.async_setup()

    with patch("asyncio.sleep", new=AsyncMock()) as sleep_mock:
        result = await controller.start_charger(target_amps=16, reason="Test")

    assert result.success is True
    assert result.operation == "start"
    assert result.amperage == 16
    assert result.queued is False
    assert service_recorder[:2] == [
        ("number", "set_value", {"entity_id": "number.charger_current", "value": 16}),
        ("switch", "turn_on", {"entity_id": "switch.charger"}),
    ]
    assert sleep_mock.await_count >= 2


async def test_set_amperage_decrease_uses_safe_sequence(
    hass,
    controller_factory,
    service_recorder,
):
    """Decreasing amperage while charging uses stop/set/start sequence."""
    hass.states.async_set("switch.charger", "on")
    hass.states.async_set("number.charger_current", "16")
    controller = controller_factory()
    await controller.async_setup()

    with patch("asyncio.sleep", new=AsyncMock()):
        result = await controller.set_amperage(6, reason="Decrease")

    assert result.success is True
    assert result.operation == "adjust_down"
    assert service_recorder == [
        ("switch", "turn_off", {"entity_id": "switch.charger"}),
        ("number", "set_value", {"entity_id": "number.charger_current", "value": 6}),
        ("switch", "turn_on", {"entity_id": "switch.charger"}),
    ]


async def test_rate_limiting_waits_instead_of_queue(
    hass,
    controller_factory,
    service_recorder,
):
    """Second operation waits for the rate limit and never returns queued."""
    hass.states.async_set("switch.charger", "off")
    hass.states.async_set("number.charger_current", "6")
    controller = controller_factory()
    await controller.async_setup()
    controller._last_operation_time = datetime.now()

    with patch("asyncio.sleep", new=AsyncMock()) as sleep_mock:
        result = await controller.start_charger(10, reason="Rate limited")

    assert result.success is True
    assert result.queued is False
    assert controller.get_queue_size() == 0
    assert sleep_mock.await_args_list[0].args[0] == pytest.approx(
        CHARGER_MIN_OPERATION_INTERVAL,
        rel=0.1,
    )
    assert service_recorder[:2] == [
        ("number", "set_value", {"entity_id": "number.charger_current", "value": 10}),
        ("switch", "turn_on", {"entity_id": "switch.charger"}),
    ]


@pytest.mark.parametrize(
    ("entity_id", "expected_service_domain", "expected_service", "expected_field", "expected_value"),
    [
        ("number.charger_current", "number", "set_value", "value", 16),
        ("input_number.charger_current", "input_number", "set_value", "value", 16),
        ("select.charger_current", "select", "select_option", "option", "16"),
        ("input_select.charger_current", "input_select", "select_option", "option", "16"),
    ],
)
async def test_supported_current_control_domains(
    hass,
    controller_factory,
    service_recorder,
    entity_id,
    expected_service_domain,
    expected_service,
    expected_field,
    expected_value,
):
    """Current control adapter supports all configured domains."""
    hass.states.async_set("switch.charger", "off")
    hass.states.async_set(entity_id, "6")
    controller = controller_factory(entity_id)
    await controller.async_setup()

    with patch("asyncio.sleep", new=AsyncMock()):
        result = await controller.start_charger(16, reason="Domain support")

    assert result.success is True
    assert service_recorder[0] == (
        expected_service_domain,
        expected_service,
        {"entity_id": entity_id, expected_field: expected_value},
    )


async def test_adjust_and_recover_do_not_deadlock(
    hass,
    controller_factory,
    service_recorder,
):
    """Grid-import adjustment and recovery complete without nested-lock deadlocks."""
    hass.states.async_set("switch.charger", "on")
    hass.states.async_set("number.charger_current", "16")
    controller = controller_factory()
    await controller.async_setup()

    with patch("asyncio.sleep", new=AsyncMock()):
        adjust_result = await controller.adjust_for_grid_import("Grid import high")
        recover_result = await controller.recover_to_target(16, "Grid clear")

    assert adjust_result.success is True
    assert adjust_result.operation == "adjust_down"
    assert recover_result.success is True
    assert recover_result.amperage == 16
    assert ("number", "set_value", {"entity_id": "number.charger_current", "value": 13}) in service_recorder
    assert ("number", "set_value", {"entity_id": "number.charger_current", "value": 16}) in service_recorder


async def test_service_error_is_reported(hass, controller_factory):
    """Service failures are surfaced in OperationResult."""
    hass.states.async_set("switch.charger", "on")
    hass.states.async_set("number.charger_current", "6")
    hass.services.async_register("switch", "turn_on", lambda call: None)
    hass.services.async_register("switch", "turn_off", lambda call: None)
    hass.services.async_register("number", "set_value", lambda call: None)
    controller = controller_factory()
    await controller.async_setup()

    with patch.object(
        controller,
        "_call_service",
        side_effect=RuntimeError("boom"),
    ):
        result = await controller.set_amperage(16, reason="Failure")

    assert result.success is False
    assert result.error_message == "boom"


async def test_invalid_current_control_domain_is_rejected(hass):
    """Unsupported current-control domains fail setup explicitly."""
    hass.states.async_set("switch.charger", "off")
    hass.states.async_set("sensor.charger_current", "6")

    controller = ChargerController(
        hass,
        "test_entry",
        {
            CONF_EV_CHARGER_SWITCH: "switch.charger",
            CONF_EV_CHARGER_CURRENT: "sensor.charger_current",
        },
    )

    with pytest.raises(ValueError, match="Unsupported charger current control domain"):
        await controller.async_setup()

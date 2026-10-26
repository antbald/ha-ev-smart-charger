"""v2.14.0 — native support for chargers controlled by start/stop buttons (issue #65).

Some wallboxes (Growatt THOR) expose ``button.*_start_charging`` and
``button.*_stop_charging`` instead of an on/off switch. When the switch is left
unmapped and both buttons are mapped, every charger on/off operation presses the
corresponding button.
"""
from __future__ import annotations

from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant import config_entries, data_entry_flow
from homeassistant.const import CONF_NAME
from homeassistant.util import dt as dt_util

from custom_components.ev_smart_charger.charger_controller import ChargerController
from custom_components.ev_smart_charger.config_flow import _normalize_charger_input
from custom_components.ev_smart_charger.const import (
    CHARGER_BUTTON_STATE_SETTLE_SECONDS,
    CONF_CHARGER_MODEL,
    CONF_EV_CHARGER_CURRENT,
    CONF_EV_CHARGER_START_BUTTON,
    CONF_EV_CHARGER_STATUS,
    CONF_EV_CHARGER_STOP_BUTTON,
    CONF_EV_CHARGER_SWITCH,
    CHARGER_MODEL_TUYA,
    DOMAIN,
    uses_charger_buttons,
)

from .test_config_flow import _advance_mode_steps

START = "button.thor_start_charging"
STOP = "button.thor_stop_charging"

BUTTON_CONFIG = {
    CONF_EV_CHARGER_START_BUTTON: START,
    CONF_EV_CHARGER_STOP_BUTTON: STOP,
    CONF_EV_CHARGER_CURRENT: "number.thor_current",
    CONF_CHARGER_MODEL: CHARGER_MODEL_TUYA,
}


@pytest.fixture
def services(hass):
    """Record button presses, switch calls and amperage sets."""
    calls: list[tuple[str, str, dict]] = []

    def _recorder(domain, service):
        async def _handler(call):
            calls.append((domain, service, dict(call.data)))
            if domain == "number":
                hass.states.async_set(
                    call.data["entity_id"], str(call.data["value"])
                )

        return _handler

    for domain, service in (
        ("button", "press"),
        ("switch", "turn_on"),
        ("switch", "turn_off"),
        ("number", "set_value"),
    ):
        hass.services.async_register(domain, service, _recorder(domain, service))
    return calls


def _runtime(watts: float | None):
    power_model = MagicMock()
    power_model.read_charging_power.return_value = watts
    power_model.is_charging.return_value = bool(watts and watts > 200)
    return SimpleNamespace(power_model=power_model, diagnostic_manager=None)


def _presses(calls):
    return [c[2]["entity_id"] for c in calls if c[:2] == ("button", "press")]


def test_uses_charger_buttons():
    assert uses_charger_buttons(BUTTON_CONFIG) is True
    assert uses_charger_buttons({**BUTTON_CONFIG, CONF_EV_CHARGER_SWITCH: "switch.x"}) is False
    assert uses_charger_buttons({CONF_EV_CHARGER_START_BUTTON: START}) is False


async def test_start_and_stop_press_buttons(hass, services):
    hass.states.async_set("number.thor_current", "6")
    controller = ChargerController(hass, "e", BUTTON_CONFIG, runtime_data=_runtime(0.0))
    await controller.async_setup()

    with patch("asyncio.sleep", new=AsyncMock()):
        result = await controller.start_charger(target_amps=16, reason="test")
        assert result.success is True
        assert await controller.is_charging() is True  # commanded, within settle
        controller._last_operation_time = None
        result = await controller.stop_charger(reason="test")

    assert result.success is True
    assert _presses(services) == [START, STOP]
    assert not [c for c in services if c[0] == "switch"]


async def test_decrease_sequence_uses_buttons(hass, services):
    hass.states.async_set("number.thor_current", "16")
    controller = ChargerController(hass, "e", BUTTON_CONFIG, runtime_data=_runtime(3600.0))
    await controller.async_setup()
    controller._record_command(True)

    with patch("asyncio.sleep", new=AsyncMock()):
        result = await controller.set_amperage(10, reason="decrease")

    assert result.success is True
    assert _presses(services) == [STOP, START]
    assert ("number", "set_value", {"entity_id": "number.thor_current", "value": 10}) in services


async def test_state_follows_measurement_after_settle(hass, services):
    hass.states.async_set("number.thor_current", "16")
    controller = ChargerController(hass, "e", BUTTON_CONFIG, runtime_data=_runtime(0.0))
    await controller.async_setup()
    controller._record_command(True)
    assert await controller.is_charging() is True

    controller._last_command_time = dt_util.now() - timedelta(
        seconds=CHARGER_BUTTON_STATE_SETTLE_SECONDS + 1
    )
    assert await controller.is_charging() is False  # 0 W measured wins


async def test_state_is_commanded_without_any_sensor(hass, services):
    hass.states.async_set("number.thor_current", "16")
    controller = ChargerController(hass, "e", BUTTON_CONFIG)
    await controller.async_setup()
    controller._record_command(True)
    controller._last_command_time = dt_util.now() - timedelta(hours=1)
    assert await controller.is_charging() is True


def test_normalize_charger_input():
    data, errors = _normalize_charger_input(
        {CONF_EV_CHARGER_START_BUTTON: START, CONF_EV_CHARGER_STOP_BUTTON: STOP}
    )
    assert errors == {}
    assert data[CONF_EV_CHARGER_SWITCH] is None

    data, errors = _normalize_charger_input(
        {CONF_EV_CHARGER_SWITCH: "switch.c", CONF_EV_CHARGER_START_BUTTON: START}
    )
    assert errors == {}
    assert data[CONF_EV_CHARGER_START_BUTTON] is None

    _, errors = _normalize_charger_input({CONF_EV_CHARGER_START_BUTTON: START})
    assert errors == {"base": "charger_control_required"}


async def _entities_step(hass):
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_NAME: "Thor"}
    )
    return await _advance_mode_steps(hass, result["flow_id"])


async def test_config_flow_accepts_buttons_only(hass):
    result = await _entities_step(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_EV_CHARGER_START_BUTTON: START,
            CONF_EV_CHARGER_STOP_BUTTON: STOP,
            CONF_EV_CHARGER_CURRENT: "number.thor_current",
            CONF_EV_CHARGER_STATUS: "sensor.thor_status",
        },
    )
    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert result["step_id"] == "sensors"


async def test_config_flow_requires_a_control(hass):
    result = await _entities_step(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_EV_CHARGER_START_BUTTON: START,
            CONF_EV_CHARGER_CURRENT: "number.thor_current",
        },
    )
    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert result["step_id"] == "entities"
    assert result["errors"] == {"base": "charger_control_required"}

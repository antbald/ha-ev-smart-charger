"""v2.13.1 — a redundant switch.turn_on rejection is not a start failure (issue #60).

Some charger integrations (Tesla Fleet) reject ``switch.turn_on`` when the
vehicle is already charging ("Command was unsuccessful: is_charging"). Boost
Charge enabled on top of an already-running session must not abort because of
it: the desired outcome is already achieved.
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.exceptions import HomeAssistantError

from custom_components.ev_smart_charger.charger_controller import ChargerController
from custom_components.ev_smart_charger.const import (
    CONF_EV_CHARGER_CURRENT,
    CONF_EV_CHARGER_SWITCH,
)

CONFIG = {
    CONF_EV_CHARGER_SWITCH: "switch.charger",
    CONF_EV_CHARGER_CURRENT: "number.charger_current",
}


@pytest.fixture
def rejecting_services(hass):
    """Register a switch.turn_on that always rejects, like Tesla Fleet does."""
    calls: list[tuple[str, str, dict]] = []

    async def switch_turn_on(call):
        calls.append(("switch", "turn_on", dict(call.data)))
        raise HomeAssistantError("Command was unsuccessful: is_charging")

    async def switch_turn_off(call):
        calls.append(("switch", "turn_off", dict(call.data)))
        hass.states.async_set(call.data["entity_id"], "off")

    async def number_set_value(call):
        calls.append(("number", "set_value", dict(call.data)))
        hass.states.async_set(call.data["entity_id"], str(call.data["value"]))

    hass.services.async_register("switch", "turn_on", switch_turn_on)
    hass.services.async_register("switch", "turn_off", switch_turn_off)
    hass.services.async_register("number", "set_value", number_set_value)
    return calls


def _runtime_with_power(watts: float | None):
    power_model = MagicMock()
    power_model.read_charging_power.return_value = watts
    power_model.is_charging.return_value = bool(watts and watts > 200)
    return SimpleNamespace(power_model=power_model, diagnostic_manager=None)


async def test_rejected_start_while_switch_on_is_success(
    hass, rejecting_services
):
    """Switch already ON + rejected turn_on → start succeeds, amperage applied."""
    hass.states.async_set("switch.charger", "on")
    hass.states.async_set("number.charger_current", "6")
    controller = ChargerController(hass, "test_entry", CONFIG)
    await controller.async_setup()

    with patch("asyncio.sleep", new=AsyncMock()):
        result = await controller.start_charger(target_amps=16, reason="Boost charge")

    assert result.success is True
    assert result.amperage == 16
    assert (
        "number",
        "set_value",
        {"entity_id": "number.charger_current", "value": 16},
    ) in rejecting_services
    assert ("switch", "turn_on", {"entity_id": "switch.charger"}) in rejecting_services


async def test_rejected_start_with_measured_draw_is_success(
    hass, rejecting_services
):
    """Stale OFF switch but the car measurably draws power → still a success."""
    hass.states.async_set("switch.charger", "off")
    hass.states.async_set("number.charger_current", "16")
    controller = ChargerController(
        hass, "test_entry", CONFIG, runtime_data=_runtime_with_power(11224.0)
    )
    await controller.async_setup()

    with patch("asyncio.sleep", new=AsyncMock()):
        result = await controller.start_charger(target_amps=16, reason="Boost charge")

    assert result.success is True


async def test_rejected_start_while_really_off_is_failure(
    hass, rejecting_services
):
    """Switch OFF and no power draw → the rejection is a genuine failure."""
    hass.states.async_set("switch.charger", "off")
    hass.states.async_set("number.charger_current", "6")
    controller = ChargerController(
        hass, "test_entry", CONFIG, runtime_data=_runtime_with_power(0.0)
    )
    await controller.async_setup()

    with patch("asyncio.sleep", new=AsyncMock()):
        result = await controller.start_charger(target_amps=16, reason="Boost charge")

    assert result.success is False
    assert "is_charging" in (result.error_message or "")


async def test_power_below_floor_does_not_mask_failure(hass, rejecting_services):
    """Standby power below the drawing floor is not evidence of charging."""
    hass.states.async_set("switch.charger", "off")
    hass.states.async_set("number.charger_current", "6")
    controller = ChargerController(
        hass, "test_entry", CONFIG, runtime_data=_runtime_with_power(40.0)
    )
    await controller.async_setup()

    with patch("asyncio.sleep", new=AsyncMock()):
        result = await controller.start_charger(target_amps=16, reason="Boost charge")

    assert result.success is False


async def test_rejected_turn_on_is_tolerated_in_recover_path(
    hass, rejecting_services
):
    """recover_to_target from OFF uses the same tolerant turn_on."""
    hass.states.async_set("switch.charger", "on")
    hass.states.async_set("number.charger_current", "6")
    controller = ChargerController(hass, "test_entry", CONFIG)
    await controller.async_setup()

    with patch("asyncio.sleep", new=AsyncMock()):
        await controller._start_charger_unlocked(16)

    assert hass.states.get("number.charger_current").state == "16"

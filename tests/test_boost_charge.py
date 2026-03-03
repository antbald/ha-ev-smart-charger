"""Tests for Boost Charge automation."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.ev_smart_charger.boost_charge import BoostCharge
from custom_components.ev_smart_charger.const import CONF_NOTIFY_SERVICES


@pytest.fixture
def boost(hass, mock_priority_balancer, mock_charger_controller):
    """Create a BoostCharge instance with mocked dependencies."""
    mock_coordinator = MagicMock()
    mock_coordinator.request_charger_action = AsyncMock(return_value=(True, "Action allowed"))

    mock_night = MagicMock()
    mock_night.async_request_immediate_check = AsyncMock()
    mock_night.async_pause_for_external_override = AsyncMock()

    mock_solar = MagicMock()
    mock_solar.async_request_immediate_check = AsyncMock()

    boost = BoostCharge(
        hass,
        "test_entry",
        {CONF_NOTIFY_SERVICES: []},
        mock_priority_balancer,
        mock_charger_controller,
        coordinator=mock_coordinator,
        night_smart_charge=mock_night,
        solar_surplus=mock_solar,
    )

    boost._boost_switch_entity = "switch.test_evsc_boost_charge_enabled"
    boost._boost_amperage_entity = "number.test_evsc_boost_charge_amperage"
    boost._boost_target_soc_entity = "number.test_evsc_boost_target_soc"

    hass.states.async_set("switch.test_evsc_boost_charge_enabled", "off")
    hass.states.async_set("number.test_evsc_boost_charge_amperage", "16")
    hass.states.async_set("number.test_evsc_boost_target_soc", "80")
    hass.states.async_set("sensor.ev_soc", "40")

    boost.priority_balancer._soc_car = "sensor.ev_soc"
    boost.priority_balancer.get_ev_current_soc = AsyncMock(return_value=40)
    boost._notification_service.send_warning = AsyncMock()
    boost._notification_service.send_info = AsyncMock()
    boost._notification_service.send_success = AsyncMock()
    boost._mobile_notifier.send_boost_charge_started_notification = AsyncMock()
    boost._mobile_notifier.send_boost_charge_completed_notification = AsyncMock()

    async def set_switch(enabled: bool) -> None:
        hass.states.async_set(
            "switch.test_evsc_boost_charge_enabled",
            "on" if enabled else "off",
        )

    boost._set_boost_switch = AsyncMock(side_effect=set_switch)
    return boost


async def test_boost_starts_when_switch_turns_on(hass, boost):
    """Boost Charge should start a fixed-amperage session below target SOC."""
    with patch(
        "custom_components.ev_smart_charger.boost_charge.async_track_time_interval",
        return_value=lambda: None,
    ):
        await boost._start_boost_charge()

    assert boost.is_active() is True
    boost._coordinator.request_charger_action.assert_awaited_once()
    boost.charger_controller.start_charger.assert_awaited_once_with(16, "Boost charge")
    boost._mobile_notifier.send_boost_charge_started_notification.assert_awaited_once_with(
        amperage=16,
        start_soc=40,
        target_soc=80,
    )


async def test_boost_does_not_start_if_target_already_reached(hass, boost):
    """Boost Charge should abort when current EV SOC is already at target."""
    hass.states.async_set("sensor.ev_soc", "85")
    boost.priority_balancer.get_ev_current_soc = AsyncMock(return_value=85)

    await boost._start_boost_charge()

    assert boost.is_active() is False
    boost.charger_controller.start_charger.assert_not_awaited()
    boost._set_boost_switch.assert_awaited_once_with(False)
    boost._notification_service.send_info.assert_awaited_once()


async def test_boost_stops_when_target_soc_reached(hass, boost):
    """Boost Charge should stop and request immediate rechecks at target SOC."""
    boost._boost_active = True
    boost._monitor_unsub = lambda: None
    hass.states.async_set("switch.test_evsc_boost_charge_enabled", "on")
    hass.states.async_set("sensor.ev_soc", "80")
    boost.priority_balancer.get_ev_current_soc = AsyncMock(return_value=80)
    boost.charger_controller.get_current_amperage.return_value = 16

    await boost._async_monitor_boost_charge(None)

    assert boost.is_active() is False
    boost.charger_controller.stop_charger.assert_awaited_once()
    boost._set_boost_switch.assert_awaited_with(False)
    boost._mobile_notifier.send_boost_charge_completed_notification.assert_awaited_once()
    boost._night_smart_charge.async_request_immediate_check.assert_awaited_once_with(
        "Boost Charge completed"
    )
    boost._solar_surplus.async_request_immediate_check.assert_awaited_once_with(
        "Boost Charge completed"
    )


async def test_boost_stops_when_user_turns_switch_off(hass, boost):
    """Turning OFF the switch should cancel an active boost session."""
    from homeassistant.core import State

    boost._boost_active = True
    boost._monitor_unsub = lambda: None

    event = MagicMock()
    event.data = {
        "old_state": State("switch.test_evsc_boost_charge_enabled", "on"),
        "new_state": State("switch.test_evsc_boost_charge_enabled", "off"),
    }

    await boost._async_boost_switch_changed(event)

    assert boost.is_active() is False
    boost.charger_controller.stop_charger.assert_awaited_once()
    boost._notification_service.send_warning.assert_awaited_once()


async def test_boost_applies_updated_amperage_during_active_session(hass, boost):
    """Boost Charge should apply a new amperage value while active."""
    boost._boost_active = True
    boost._monitor_unsub = lambda: None
    hass.states.async_set("sensor.ev_soc", "50")
    hass.states.async_set("number.test_evsc_boost_charge_amperage", "20")
    boost.priority_balancer.get_ev_current_soc = AsyncMock(return_value=50)
    boost.charger_controller.get_current_amperage.return_value = 16

    await boost._async_monitor_boost_charge(None)

    boost.charger_controller.set_amperage.assert_awaited_once_with(
        20, "Boost configuration updated"
    )


async def test_boost_uses_updated_target_during_active_session(hass, boost):
    """Boost Charge should evaluate the latest target SOC on every monitor cycle."""
    boost._boost_active = True
    boost._monitor_unsub = lambda: None
    hass.states.async_set("switch.test_evsc_boost_charge_enabled", "on")
    hass.states.async_set("sensor.ev_soc", "79")
    hass.states.async_set("number.test_evsc_boost_target_soc", "75")
    boost.priority_balancer.get_ev_current_soc = AsyncMock(return_value=79)
    boost.charger_controller.get_current_amperage.return_value = 16

    await boost._async_monitor_boost_charge(None)

    boost.charger_controller.stop_charger.assert_awaited_once()


async def test_boost_fails_safe_when_ev_soc_unavailable_too_long(hass, boost):
    """Boost Charge should stop after repeated SOC read failures."""
    boost._boost_active = True
    boost._monitor_unsub = lambda: None
    hass.states.async_set("switch.test_evsc_boost_charge_enabled", "on")
    hass.states.async_set("sensor.ev_soc", "unavailable")
    boost.charger_controller.get_current_amperage.return_value = 16

    for _ in range(4):
        await boost._async_monitor_boost_charge(None)

    assert boost.is_active() is False
    boost.charger_controller.stop_charger.assert_awaited_once()
    boost._notification_service.send_warning.assert_awaited_once()

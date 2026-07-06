"""Runtime monitor for EV charging Live Activities."""
from __future__ import annotations

from datetime import timedelta
from unittest.mock import AsyncMock, Mock, patch

from homeassistant.const import STATE_OFF, STATE_ON

from custom_components.ev_smart_charger.const import (
    CONF_NOTIFY_SERVICES,
    HELPER_CHARGING_PROFILE_SUFFIX,
    HELPER_FORZA_RICARICA_SUFFIX,
)
from custom_components.ev_smart_charger.live_activity_monitor import (
    LIVE_ACTIVITY_MONITOR_INTERVAL_SECONDS,
    EVChargingLiveActivityMonitor,
)
from custom_components.ev_smart_charger.runtime import EVSCRuntimeData
from custom_components.ev_smart_charger.utils.mobile_notification_service import (
    LIVE_ACTIVITY_TAG,
)


def _runtime_data(*, charging: bool = True) -> EVSCRuntimeData:
    runtime_data = EVSCRuntimeData(
        config={CONF_NOTIFY_SERVICES: ["mobile_app_test_phone"]},
        expected_entity_count=2,
    )
    runtime_data.power_model = Mock(
        is_charging=Mock(return_value=charging),
        read_charging_power=Mock(return_value=None),
    )
    runtime_data.boost_charge = Mock(is_active=Mock(return_value=False))
    runtime_data.night_smart_charge = Mock(is_active=Mock(return_value=False))
    runtime_data.coordinator = Mock(get_active_automation_name=Mock(return_value=None))
    return runtime_data


def _monitor(hass, runtime_data: EVSCRuntimeData) -> EVChargingLiveActivityMonitor:
    return EVChargingLiveActivityMonitor(
        hass,
        "entry_123",
        runtime_data.config,
        runtime_data,
    )


async def test_monitor_starts_normal_live_activity_when_charging(hass) -> None:
    """Normal charging opens the shared EV charging Live Activity."""
    hass.services.async_call = AsyncMock()
    runtime_data = _runtime_data(charging=True)
    monitor = _monitor(hass, runtime_data)

    await monitor._async_tick()

    payload = hass.services.async_call.await_args.args[2]
    assert payload["title"] == "EV Charging"
    assert payload["message"].startswith("Charging ·")
    assert payload["data"]["tag"] == LIVE_ACTIVITY_TAG
    assert payload["data"]["live_update"] is True


async def test_monitor_skips_when_boost_is_active(hass) -> None:
    """Boost owns the Live Activity while active."""
    hass.services.async_call = AsyncMock()
    runtime_data = _runtime_data(charging=True)
    runtime_data.boost_charge.is_active.return_value = True
    monitor = _monitor(hass, runtime_data)

    await monitor._async_tick()

    hass.services.async_call.assert_not_awaited()


async def test_monitor_skips_when_night_charge_is_active(hass) -> None:
    """Night Smart Charge owns the Live Activity while active."""
    hass.services.async_call = AsyncMock()
    runtime_data = _runtime_data(charging=True)
    runtime_data.night_smart_charge.is_active.return_value = True
    monitor = _monitor(hass, runtime_data)

    await monitor._async_tick()

    hass.services.async_call.assert_not_awaited()


async def test_monitor_clears_after_two_inactive_ticks(hass) -> None:
    """A brief not-charging dip does not immediately close the Live Activity."""
    hass.services.async_call = AsyncMock()
    runtime_data = _runtime_data(charging=True)
    monitor = _monitor(hass, runtime_data)

    await monitor._async_tick()
    runtime_data.power_model.is_charging.return_value = False
    await monitor._async_tick()
    assert hass.services.async_call.call_count == 1

    await monitor._async_tick()

    assert hass.services.async_call.call_count == 2
    payload = hass.services.async_call.await_args.args[2]
    assert payload["message"] == "clear_notification"
    assert payload["data"]["tag"] == LIVE_ACTIVITY_TAG


async def test_monitor_mode_label_force_charge(hass) -> None:
    """Force Charge label wins when the override helper is ON."""
    hass.services.async_call = AsyncMock()
    runtime_data = _runtime_data(charging=True)
    runtime_data.register_entity(
        HELPER_FORZA_RICARICA_SUFFIX,
        "switch.evsc_forza_ricarica",
        object(),
    )
    hass.states.async_set("switch.evsc_forza_ricarica", STATE_ON)
    monitor = _monitor(hass, runtime_data)

    await monitor._async_tick()

    payload = hass.services.async_call.await_args.args[2]
    assert payload["message"].startswith("Force Charge ·")


async def test_monitor_mode_label_solar_surplus_from_coordinator(hass) -> None:
    """Solar Surplus label follows the active coordinator owner."""
    hass.services.async_call = AsyncMock()
    runtime_data = _runtime_data(charging=True)
    runtime_data.coordinator.get_active_automation_name.return_value = "Solar Surplus"
    monitor = _monitor(hass, runtime_data)

    await monitor._async_tick()

    payload = hass.services.async_call.await_args.args[2]
    assert payload["message"].startswith("Solar Surplus ·")


async def test_monitor_mode_label_solar_surplus_from_profile(hass) -> None:
    """Solar Surplus label also follows the charging profile helper."""
    hass.services.async_call = AsyncMock()
    runtime_data = _runtime_data(charging=True)
    runtime_data.register_entity(
        HELPER_CHARGING_PROFILE_SUFFIX,
        "select.evsc_charging_profile",
        object(),
    )
    hass.states.async_set("select.evsc_charging_profile", "solar_surplus")
    monitor = _monitor(hass, runtime_data)

    await monitor._async_tick()

    payload = hass.services.async_call.await_args.args[2]
    assert payload["message"].startswith("Solar Surplus ·")


async def test_monitor_mode_label_fallback_charging(hass) -> None:
    """Fallback label is Charging when no specific normal-charge context applies."""
    hass.services.async_call = AsyncMock()
    runtime_data = _runtime_data(charging=True)
    runtime_data.register_entity(
        HELPER_FORZA_RICARICA_SUFFIX,
        "switch.evsc_forza_ricarica",
        object(),
    )
    hass.states.async_set("switch.evsc_forza_ricarica", STATE_OFF)
    monitor = _monitor(hass, runtime_data)

    await monitor._async_tick()

    payload = hass.services.async_call.await_args.args[2]
    assert payload["message"].startswith("Charging ·")


async def test_monitor_async_remove_cancels_timer(hass) -> None:
    """Monitor cleanup cancels the registered interval listener."""
    runtime_data = _runtime_data(charging=False)
    runtime_data.config = {CONF_NOTIFY_SERVICES: []}
    monitor = _monitor(hass, runtime_data)
    cancel = Mock()

    with patch(
        "custom_components.ev_smart_charger.live_activity_monitor.async_track_time_interval",
        return_value=cancel,
    ) as track_interval:
        await monitor.async_setup()
        await monitor.async_remove()

    track_interval.assert_called_once()
    assert track_interval.call_args.args[2] == timedelta(
        seconds=LIVE_ACTIVITY_MONITOR_INTERVAL_SECONDS
    )
    cancel.assert_called_once()

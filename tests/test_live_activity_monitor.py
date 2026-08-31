"""Runtime monitor for EV charging Live Activities."""
from __future__ import annotations

from datetime import timedelta
from unittest.mock import AsyncMock, Mock, patch

from homeassistant.const import STATE_OFF, STATE_ON
from homeassistant.util import dt as dt_util

from custom_components.ev_smart_charger.const import (
    CHARGER_STATUS_CHARGING,
    CHARGER_STATUS_END,
    CHARGER_STATUS_FREE,
    CONF_EV_CHARGER_STATUS,
    CONF_EV_CHARGER_SWITCH,
    CONF_NOTIFY_SERVICES,
    HELPER_CHARGING_PROFILE_SUFFIX,
    HELPER_FORZA_RICARICA_SUFFIX,
    HELPER_LIVE_ACTIVITIES_ENABLED_SUFFIX,
    HELPER_STOP_CHARGING_SUFFIX,
    LIVE_ACTIVITY_CLEAR_GRACE_SECONDS,
    LIVE_ACTIVITY_STOP_GRACE_SECONDS,
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
    runtime_data.register_entity(
        HELPER_LIVE_ACTIVITIES_ENABLED_SUFFIX,
        "switch.evsc_live_activities_enabled",
        object(),
    )
    return runtime_data


def _monitor(hass, runtime_data: EVSCRuntimeData) -> EVChargingLiveActivityMonitor:
    return EVChargingLiveActivityMonitor(
        hass,
        "entry_123",
        runtime_data.config,
        runtime_data,
    )


def _enable_live_activities(hass) -> None:
    hass.states.async_set("switch.evsc_live_activities_enabled", STATE_ON)


async def test_monitor_starts_normal_live_activity_when_charging(hass) -> None:
    """Normal charging opens the shared EV charging Live Activity."""
    hass.services.async_call = AsyncMock()
    runtime_data = _runtime_data(charging=True)
    _enable_live_activities(hass)
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
    _enable_live_activities(hass)
    monitor = _monitor(hass, runtime_data)

    await monitor._async_tick()

    hass.services.async_call.assert_not_awaited()


async def test_monitor_skips_when_night_charge_is_active(hass) -> None:
    """Night Smart Charge owns the Live Activity while active."""
    hass.services.async_call = AsyncMock()
    runtime_data = _runtime_data(charging=True)
    runtime_data.night_smart_charge.is_active.return_value = True
    _enable_live_activities(hass)
    monitor = _monitor(hass, runtime_data)

    await monitor._async_tick()

    hass.services.async_call.assert_not_awaited()


async def test_monitor_keeps_activity_during_a_short_charging_gap(hass) -> None:
    """The Tuya stop→set→start decrease sequence must not close the card.

    Each restart costs push-to-start budget, and exhausting it makes new
    activities fail silently, so a few not-charging ticks are tolerated.
    """
    hass.services.async_call = AsyncMock()
    runtime_data = _runtime_data(charging=True)
    _enable_live_activities(hass)
    monitor = _monitor(hass, runtime_data)

    await monitor._async_tick()
    runtime_data.power_model.is_charging.return_value = False
    await monitor._async_tick()
    await monitor._async_tick()
    await monitor._async_tick()

    assert hass.services.async_call.call_count == 1
    assert runtime_data.live_activity.active is True


async def test_monitor_clears_after_the_grace_period(hass) -> None:
    """A sustained charging gap closes the Live Activity."""
    hass.services.async_call = AsyncMock()
    runtime_data = _runtime_data(charging=True)
    _enable_live_activities(hass)
    monitor = _monitor(hass, runtime_data)

    await monitor._async_tick()
    runtime_data.power_model.is_charging.return_value = False
    await monitor._async_tick()
    monitor._not_charging_since = dt_util.utcnow() - timedelta(
        seconds=LIVE_ACTIVITY_CLEAR_GRACE_SECONDS + 1
    )
    await monitor._async_tick()

    assert hass.services.async_call.call_count == 2
    payload = hass.services.async_call.await_args.args[2]
    assert payload["message"] == "clear_notification"
    assert payload["data"]["tag"] == LIVE_ACTIVITY_TAG
    assert runtime_data.live_activity.active is False


async def test_monitor_does_not_clear_when_nothing_is_open(hass) -> None:
    """An idle monitor never sends a clear push."""
    hass.services.async_call = AsyncMock()
    runtime_data = _runtime_data(charging=False)
    _enable_live_activities(hass)
    monitor = _monitor(hass, runtime_data)

    await monitor._async_tick()
    await monitor._async_tick()

    hass.services.async_call.assert_not_awaited()


async def test_monitor_does_not_repush_on_every_tick(hass) -> None:
    """A steady charge keeps ticking without burning a push per minute."""
    hass.services.async_call = AsyncMock()
    runtime_data = _runtime_data(charging=True)
    _enable_live_activities(hass)
    monitor = _monitor(hass, runtime_data)

    for _ in range(10):
        await monitor._async_tick()

    assert hass.services.async_call.call_count == 1


async def test_monitor_mode_label_force_charge(hass) -> None:
    """Force Charge label wins when the override helper is ON."""
    hass.services.async_call = AsyncMock()
    runtime_data = _runtime_data(charging=True)
    _enable_live_activities(hass)
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
    _enable_live_activities(hass)
    runtime_data.coordinator.get_active_automation_name.return_value = "Solar Surplus"
    monitor = _monitor(hass, runtime_data)

    await monitor._async_tick()

    payload = hass.services.async_call.await_args.args[2]
    assert payload["message"].startswith("Solar Surplus ·")


async def test_monitor_mode_label_solar_surplus_from_profile(hass) -> None:
    """Solar Surplus label also follows the charging profile helper."""
    hass.services.async_call = AsyncMock()
    runtime_data = _runtime_data(charging=True)
    _enable_live_activities(hass)
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
    _enable_live_activities(hass)
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


async def test_monitor_is_inert_while_the_helper_switch_is_off(hass) -> None:
    """Normal charging Live Activity monitor is inert while the helper is OFF."""
    hass.services.async_call = AsyncMock()
    runtime_data = _runtime_data(charging=True)
    hass.states.async_set("switch.evsc_live_activities_enabled", STATE_OFF)
    monitor = _monitor(hass, runtime_data)

    await monitor._async_tick()

    hass.services.async_call.assert_not_awaited()


async def test_monitor_clears_once_when_live_activities_are_disabled(hass) -> None:
    """Turning the helper OFF clears any previously monitor-owned activity."""
    hass.services.async_call = AsyncMock()
    runtime_data = _runtime_data(charging=True)
    _enable_live_activities(hass)
    monitor = _monitor(hass, runtime_data)

    await monitor._async_tick()
    hass.states.async_set("switch.evsc_live_activities_enabled", STATE_OFF)
    await monitor._async_tick()
    await monitor._async_tick()

    assert hass.services.async_call.call_count == 2
    payload = hass.services.async_call.await_args.args[2]
    assert payload["message"] == "clear_notification"


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


async def test_monitor_async_remove_closes_an_open_activity(hass) -> None:
    """Unloading the integration must not leave a frozen card on screen."""
    hass.services.async_call = AsyncMock()
    runtime_data = _runtime_data(charging=True)
    _enable_live_activities(hass)
    monitor = _monitor(hass, runtime_data)

    await monitor._async_tick()
    await monitor.async_remove()

    assert hass.services.async_call.call_count == 2
    payload = hass.services.async_call.await_args.args[2]
    assert payload["message"] == "clear_notification"


# ---------------------------------------------------------------------------
# v2.12.1 — the activity must end when the SESSION ends, not when a sensor
# happens to agree. Reported failure: the card stayed on "charging" after the
# charge was interrupted.
# ---------------------------------------------------------------------------

CHARGER_SWITCH = "switch.wallbox"
CHARGER_STATUS = "sensor.wallbox_status"


def _runtime_data_with_charger(*, charging: bool = True) -> EVSCRuntimeData:
    """Runtime data with the charger switch/status actually mapped."""
    runtime_data = _runtime_data(charging=charging)
    runtime_data.config[CONF_EV_CHARGER_SWITCH] = CHARGER_SWITCH
    runtime_data.config[CONF_EV_CHARGER_STATUS] = CHARGER_STATUS
    runtime_data.register_entity(
        HELPER_STOP_CHARGING_SUFFIX,
        "switch.evsc_stop_charging",
        object(),
    )
    return runtime_data


def _charging_wallbox(hass) -> None:
    hass.states.async_set(CHARGER_SWITCH, STATE_ON)
    hass.states.async_set(CHARGER_STATUS, CHARGER_STATUS_CHARGING)
    hass.states.async_set("switch.evsc_stop_charging", STATE_OFF)


async def test_unplugging_ends_the_activity_immediately(hass) -> None:
    """A cable out is definitive: no amperage step can produce it."""
    hass.services.async_call = AsyncMock()
    runtime_data = _runtime_data_with_charger(charging=True)
    _enable_live_activities(hass)
    _charging_wallbox(hass)
    monitor = _monitor(hass, runtime_data)

    await monitor._async_tick()
    hass.states.async_set(CHARGER_STATUS, CHARGER_STATUS_FREE)
    runtime_data.power_model.is_charging.return_value = False
    await monitor._async_tick()

    assert hass.services.async_call.call_count == 2
    assert hass.services.async_call.await_args.args[2]["message"] == "clear_notification"
    assert runtime_data.live_activity.active is False


async def test_charge_complete_ends_the_activity_immediately(hass) -> None:
    """`charger_end` means the session is over, not that power dipped."""
    hass.services.async_call = AsyncMock()
    runtime_data = _runtime_data_with_charger(charging=True)
    _enable_live_activities(hass)
    _charging_wallbox(hass)
    monitor = _monitor(hass, runtime_data)

    await monitor._async_tick()
    hass.states.async_set(CHARGER_STATUS, CHARGER_STATUS_END)
    await monitor._async_tick()

    assert runtime_data.live_activity.active is False


async def test_manual_stop_hold_ends_the_activity_immediately(hass) -> None:
    """Engaging Stop Charging is an explicit end-of-session intent."""
    hass.services.async_call = AsyncMock()
    runtime_data = _runtime_data_with_charger(charging=True)
    _enable_live_activities(hass)
    _charging_wallbox(hass)
    monitor = _monitor(hass, runtime_data)

    await monitor._async_tick()
    hass.states.async_set("switch.evsc_stop_charging", STATE_ON)
    await monitor._async_tick()

    assert runtime_data.live_activity.active is False


async def test_stale_power_sensor_no_longer_pins_the_card(hass) -> None:
    """Regression: the reported "stuck on charging" card.

    A wallbox power sensor that keeps its last value once the charger is
    switched off made ``is_charging()`` answer True forever, so the clear path
    was never reached. The classified stop signal now outranks the reading.
    """
    hass.services.async_call = AsyncMock()
    runtime_data = _runtime_data_with_charger(charging=True)
    _enable_live_activities(hass)
    _charging_wallbox(hass)
    monitor = _monitor(hass, runtime_data)

    await monitor._async_tick()
    # Charger commanded off; the power sensor keeps reporting the old draw.
    hass.states.async_set(CHARGER_SWITCH, STATE_OFF)
    assert runtime_data.power_model.is_charging.return_value is True

    await monitor._async_tick()
    monitor._not_charging_since = dt_util.utcnow() - timedelta(
        seconds=LIVE_ACTIVITY_STOP_GRACE_SECONDS + 1
    )
    await monitor._async_tick()

    assert runtime_data.live_activity.active is False
    assert hass.services.async_call.await_args.args[2]["message"] == "clear_notification"


async def test_charger_off_waits_out_the_tuya_decrease_sequence(hass) -> None:
    """The switch drops for ~6 s on every amperage step — that is not a stop."""
    hass.services.async_call = AsyncMock()
    runtime_data = _runtime_data_with_charger(charging=True)
    _enable_live_activities(hass)
    _charging_wallbox(hass)
    monitor = _monitor(hass, runtime_data)

    await monitor._async_tick()
    hass.states.async_set(CHARGER_SWITCH, STATE_OFF)
    await monitor._async_tick()
    hass.states.async_set(CHARGER_SWITCH, STATE_ON)
    await monitor._async_tick()

    assert runtime_data.live_activity.active is True
    assert hass.services.async_call.call_count == 1


async def test_ambiguous_power_dip_keeps_the_long_grace(hass) -> None:
    """With the charger still on, only the 300 s grace may close the card."""
    hass.services.async_call = AsyncMock()
    runtime_data = _runtime_data_with_charger(charging=True)
    _enable_live_activities(hass)
    _charging_wallbox(hass)
    monitor = _monitor(hass, runtime_data)

    await monitor._async_tick()
    runtime_data.power_model.is_charging.return_value = False
    await monitor._async_tick()
    monitor._not_charging_since = dt_util.utcnow() - timedelta(
        seconds=LIVE_ACTIVITY_STOP_GRACE_SECONDS + 1
    )
    await monitor._async_tick()
    assert runtime_data.live_activity.active is True

    monitor._not_charging_since = dt_util.utcnow() - timedelta(
        seconds=LIVE_ACTIVITY_CLEAR_GRACE_SECONDS + 1
    )
    await monitor._async_tick()
    assert runtime_data.live_activity.active is False


async def test_definitive_stop_closes_a_lingering_night_session_card(hass) -> None:
    """A session object stuck "active" must not pin a stale card."""
    hass.services.async_call = AsyncMock()
    runtime_data = _runtime_data_with_charger(charging=True)
    _enable_live_activities(hass)
    _charging_wallbox(hass)
    monitor = _monitor(hass, runtime_data)

    await monitor._async_tick()
    runtime_data.night_smart_charge.is_active.return_value = True
    hass.states.async_set(CHARGER_STATUS, CHARGER_STATUS_FREE)
    runtime_data.power_model.is_charging.return_value = False
    await monitor._async_tick()

    assert runtime_data.live_activity.active is False


async def test_night_session_still_owns_the_tag_on_an_ambiguous_gap(hass) -> None:
    """Boost / Night keep the tag while the evidence is only a power dip."""
    hass.services.async_call = AsyncMock()
    runtime_data = _runtime_data_with_charger(charging=True)
    _enable_live_activities(hass)
    _charging_wallbox(hass)
    monitor = _monitor(hass, runtime_data)

    await monitor._async_tick()
    runtime_data.night_smart_charge.is_active.return_value = True
    runtime_data.power_model.is_charging.return_value = False
    monitor._not_charging_since = dt_util.utcnow() - timedelta(
        seconds=LIVE_ACTIVITY_CLEAR_GRACE_SECONDS + 1
    )
    await monitor._async_tick()

    assert runtime_data.live_activity.active is True


async def test_setup_registers_and_removes_stop_listeners(hass) -> None:
    """Stop detection is event-driven, not only polled once a minute."""
    runtime_data = _runtime_data_with_charger(charging=False)
    runtime_data.config[CONF_NOTIFY_SERVICES] = []
    monitor = _monitor(hass, runtime_data)
    cancel_state = Mock()

    with patch(
        "custom_components.ev_smart_charger.live_activity_monitor.async_track_time_interval",
        return_value=Mock(),
    ), patch(
        "custom_components.ev_smart_charger.live_activity_monitor."
        "async_track_state_change_event",
        return_value=cancel_state,
    ) as track_state:
        await monitor.async_setup()
        tracked = track_state.call_args.args[1]
        await monitor.async_remove()

    assert CHARGER_SWITCH in tracked
    assert CHARGER_STATUS in tracked
    assert "switch.evsc_stop_charging" in tracked
    cancel_state.assert_called_once()


async def test_state_event_reevaluates_immediately(hass) -> None:
    """A discrete state change runs a tick without waiting for the interval."""
    hass.services.async_call = AsyncMock()
    runtime_data = _runtime_data_with_charger(charging=True)
    _enable_live_activities(hass)
    _charging_wallbox(hass)
    monitor = _monitor(hass, runtime_data)

    await monitor._async_tick()
    hass.states.async_set(CHARGER_STATUS, CHARGER_STATUS_FREE)
    runtime_data.power_model.is_charging.return_value = False
    await monitor._async_state_event(None)

    assert runtime_data.live_activity.active is False

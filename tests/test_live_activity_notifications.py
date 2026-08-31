"""Live Activity notification payloads and update policy (v2.12.0)."""
from __future__ import annotations

from datetime import timedelta
from unittest.mock import AsyncMock, Mock

from homeassistant.util import dt as dt_util

from custom_components.ev_smart_charger.const import (
    CONF_EV_CHARGER_CURRENT,
    CONF_EV_CHARGER_STATUS,
    HELPER_CACHED_EV_SOC_SUFFIX,
    HELPER_LIVE_ACTIVITIES_ENABLED_SUFFIX,
    HELPER_TODAY_EV_TARGET_SUFFIX,
    LIVE_ACTIVITY_MIN_UPDATE_SECONDS,
    LIVE_ACTIVITY_MODE_BOOST,
    LIVE_ACTIVITY_MODE_NIGHT_GRID,
    LIVE_ACTIVITY_RESTART_COOLDOWN_SECONDS,
)
from custom_components.ev_smart_charger.runtime import EVSCRuntimeData
from custom_components.ev_smart_charger.utils.mobile_notification_service import (
    LIVE_ACTIVITY_TAG,
    MobileNotificationService,
)


def _runtime_data(power: float | None = 7300.0) -> EVSCRuntimeData:
    runtime_data = EVSCRuntimeData(
        config={
            CONF_EV_CHARGER_CURRENT: "number.wallbox_current",
            CONF_EV_CHARGER_STATUS: "sensor.wallbox_status",
        },
        expected_entity_count=2,
    )
    runtime_data.register_entity(
        HELPER_CACHED_EV_SOC_SUFFIX,
        "sensor.evsc_cached_ev_soc",
        object(),
    )
    runtime_data.register_entity(
        HELPER_TODAY_EV_TARGET_SUFFIX,
        "sensor.evsc_today_ev_target",
        object(),
    )
    runtime_data.register_entity(
        HELPER_LIVE_ACTIVITIES_ENABLED_SUFFIX,
        "switch.evsc_live_activities_enabled",
        object(),
    )
    runtime_data.power_model = Mock(read_charging_power=Mock(return_value=power))
    return runtime_data


def _service(hass, runtime_data: EVSCRuntimeData) -> MobileNotificationService:
    return MobileNotificationService(
        hass,
        notify_services=["mobile_app_test_phone"],
        entry_id="entry_123",
        runtime_data=runtime_data,
    )


def _enable_live_activities(hass) -> None:
    hass.states.async_set("switch.evsc_live_activities_enabled", "on")


def _charging_states(hass, *, soc: str = "62.4", target: str = "80") -> None:
    hass.states.async_set("sensor.evsc_cached_ev_soc", soc)
    hass.states.async_set("sensor.evsc_today_ev_target", target)
    hass.states.async_set("number.wallbox_current", "16")
    hass.states.async_set("sensor.wallbox_status", "charger_charging")


async def test_ev_charging_live_activity_payload_uses_current_snapshot(hass) -> None:
    """Live Activity payload exposes SOC, target, speed, and tap URL."""
    hass.services.async_call = AsyncMock()
    _charging_states(hass)
    _enable_live_activities(hass)

    service = _service(hass, _runtime_data())
    await service.send_ev_charging_live_activity(mode=LIVE_ACTIVITY_MODE_BOOST)

    notify_call = hass.services.async_call.await_args
    payload = notify_call.args[2]
    data = payload["data"]
    assert notify_call.args[0] == "notify"
    assert notify_call.args[1] == "mobile_app_test_phone"
    assert payload["title"] == "EV Charging"
    # Status suffix is omitted while plainly charging (the mode already says it)
    assert payload["message"] == "Boost · 7.3 kW · Target 80%"
    assert data["tag"] == LIVE_ACTIVITY_TAG
    assert data["live_update"] is True
    assert data["critical_text"] == "62%"
    assert data["progress"] == 62
    assert data["progress_max"] == 100
    assert data["notification_icon"] == "mdi:ev-station"
    assert data["url"] == "/ev-smart-charger"
    # The first push starts the activity: audible-once, never "silent"
    assert data["alert_once"] is True
    assert "silent" not in data


async def test_non_charging_status_is_appended_to_the_message(hass) -> None:
    """A non-charging wallbox status still reaches the lock screen."""
    hass.services.async_call = AsyncMock()
    _charging_states(hass)
    hass.states.async_set("sensor.wallbox_status", "charger_wait")
    _enable_live_activities(hass)

    service = _service(hass, _runtime_data())
    await service.send_ev_charging_live_activity(mode=LIVE_ACTIVITY_MODE_BOOST)

    payload = hass.services.async_call.await_args.args[2]
    assert payload["message"] == "Boost · 7.3 kW · Target 80% · Waiting"


async def test_refresh_of_an_open_activity_is_marked_silent(hass) -> None:
    """Updates to an on-screen card use the low-priority silent path."""
    hass.services.async_call = AsyncMock()
    _charging_states(hass, soc="60")
    _enable_live_activities(hass)
    runtime_data = _runtime_data()
    service = _service(hass, runtime_data)

    await service.send_ev_charging_live_activity(mode=LIVE_ACTIVITY_MODE_BOOST)
    # SOC step crossed and the min interval already elapsed
    runtime_data.live_activity.last_update = dt_util.utcnow() - timedelta(
        seconds=LIVE_ACTIVITY_MIN_UPDATE_SECONDS + 1
    )
    hass.states.async_set("sensor.evsc_cached_ev_soc", "66")
    await service.send_ev_charging_live_activity(mode=LIVE_ACTIVITY_MODE_BOOST)

    assert hass.services.async_call.call_count == 2
    data = hass.services.async_call.await_args.args[2]["data"]
    assert data["silent"] is True
    assert data["alert_once"] is True


async def test_clear_ev_charging_live_activity_uses_clear_notification(hass) -> None:
    """An open Live Activity is closed with the companion clear command."""
    hass.services.async_call = AsyncMock()
    _charging_states(hass)
    _enable_live_activities(hass)
    service = _service(hass, _runtime_data())

    await service.send_ev_charging_live_activity(mode=LIVE_ACTIVITY_MODE_BOOST)
    await service.clear_ev_charging_live_activity()

    notify_call = hass.services.async_call.await_args
    payload = notify_call.args[2]
    assert payload["message"] == "clear_notification"
    assert payload["data"]["tag"] == LIVE_ACTIVITY_TAG
    assert "live_update" not in payload["data"]


async def test_clear_is_a_no_op_when_no_activity_is_open(hass) -> None:
    """Repeated stop paths must not burn a push per call."""
    hass.services.async_call = AsyncMock()
    service = _service(hass, _runtime_data())

    await service.clear_ev_charging_live_activity()

    hass.services.async_call.assert_not_awaited()


async def test_amperage_power_and_status_do_not_trigger_updates(hass) -> None:
    """Display-only values never schedule a push of their own (v2.12.0).

    The Tuya safe-decrease sequence flaps the status on every amperage step and
    solar surplus moves the wattage continuously; before v2.12.0 both were part
    of the trigger set, which produced roughly one push per minute.
    """
    hass.services.async_call = AsyncMock()
    _charging_states(hass, soc="60")
    _enable_live_activities(hass)
    runtime_data = _runtime_data()
    service = _service(hass, runtime_data)

    await service.send_ev_charging_live_activity(mode=LIVE_ACTIVITY_MODE_BOOST)
    assert hass.services.async_call.call_count == 1

    # Pretend plenty of time has passed, then churn every display-only value.
    runtime_data.live_activity.last_update = dt_util.utcnow() - timedelta(hours=1)
    for amps, watts, status in (
        ("13", 3000.0, "charger_wait"),
        ("10", 2300.0, "charger_charging"),
        ("20", 4600.0, "charger_wait"),
    ):
        hass.states.async_set("number.wallbox_current", amps)
        hass.states.async_set("sensor.wallbox_status", status)
        runtime_data.power_model.read_charging_power.return_value = watts
        await service.send_ev_charging_live_activity(mode=LIVE_ACTIVITY_MODE_BOOST)

    assert hass.services.async_call.call_count == 1


async def test_soc_update_needs_both_a_full_step_and_the_min_interval(hass) -> None:
    """SOC pushes honour a 5-point hysteresis and the 5-minute floor."""
    hass.services.async_call = AsyncMock()
    _charging_states(hass, soc="60")
    _enable_live_activities(hass)
    runtime_data = _runtime_data()
    service = _service(hass, runtime_data)

    await service.send_ev_charging_live_activity(mode=LIVE_ACTIVITY_MODE_BOOST)

    # Step crossed but the interval has not elapsed → no push.
    hass.states.async_set("sensor.evsc_cached_ev_soc", "66")
    await service.send_ev_charging_live_activity(mode=LIVE_ACTIVITY_MODE_BOOST)
    assert hass.services.async_call.call_count == 1

    # Interval elapsed but the SOC only crept 2 points → still no push.
    runtime_data.live_activity.last_update = dt_util.utcnow() - timedelta(hours=1)
    hass.states.async_set("sensor.evsc_cached_ev_soc", "62")
    await service.send_ev_charging_live_activity(mode=LIVE_ACTIVITY_MODE_BOOST)
    assert hass.services.async_call.call_count == 1

    # Both conditions met.
    hass.states.async_set("sensor.evsc_cached_ev_soc", "65")
    await service.send_ev_charging_live_activity(mode=LIVE_ACTIVITY_MODE_BOOST)
    assert hass.services.async_call.call_count == 2


async def test_soc_hysteresis_is_measured_from_the_last_pushed_value(hass) -> None:
    """An oscillating reading cannot flap across a fixed bucket boundary."""
    hass.services.async_call = AsyncMock()
    _charging_states(hass, soc="49")
    _enable_live_activities(hass)
    runtime_data = _runtime_data()
    service = _service(hass, runtime_data)

    await service.send_ev_charging_live_activity(mode=LIVE_ACTIVITY_MODE_BOOST)

    for soc in ("51", "49", "52", "48", "51"):
        runtime_data.live_activity.last_update = dt_util.utcnow() - timedelta(hours=1)
        hass.states.async_set("sensor.evsc_cached_ev_soc", soc)
        await service.send_ev_charging_live_activity(mode=LIVE_ACTIVITY_MODE_BOOST)

    assert hass.services.async_call.call_count == 1


async def test_mode_change_pushes_promptly(hass) -> None:
    """A real transition is worth an immediate refresh."""
    hass.services.async_call = AsyncMock()
    _charging_states(hass, soc="60")
    _enable_live_activities(hass)
    runtime_data = _runtime_data()
    service = _service(hass, runtime_data)

    await service.send_ev_charging_live_activity(mode=LIVE_ACTIVITY_MODE_BOOST)
    runtime_data.live_activity.last_update = dt_util.utcnow() - timedelta(minutes=1)
    await service.send_ev_charging_live_activity(mode=LIVE_ACTIVITY_MODE_NIGHT_GRID)

    assert hass.services.async_call.call_count == 2
    assert hass.services.async_call.await_args.args[2]["message"].startswith(
        "Night · Grid ·"
    )


async def test_state_is_shared_across_notification_services(hass) -> None:
    """Boost, Night Charge and the monitor throttle against one shared clock."""
    hass.services.async_call = AsyncMock()
    _charging_states(hass, soc="60")
    _enable_live_activities(hass)
    runtime_data = _runtime_data()
    boost_notifier = _service(hass, runtime_data)
    monitor_notifier = _service(hass, runtime_data)

    await boost_notifier.send_ev_charging_live_activity(mode=LIVE_ACTIVITY_MODE_BOOST)
    await monitor_notifier.send_ev_charging_live_activity(mode=LIVE_ACTIVITY_MODE_BOOST)

    assert hass.services.async_call.call_count == 1


async def test_restart_cooldown_protects_the_push_to_start_budget(hass) -> None:
    """A just-ended activity is not immediately restarted."""
    hass.services.async_call = AsyncMock()
    _charging_states(hass, soc="60")
    _enable_live_activities(hass)
    runtime_data = _runtime_data()
    service = _service(hass, runtime_data)

    await service.send_ev_charging_live_activity(mode=LIVE_ACTIVITY_MODE_BOOST)
    await service.clear_ev_charging_live_activity()
    assert hass.services.async_call.call_count == 2

    await service.send_ev_charging_live_activity(mode=LIVE_ACTIVITY_MODE_BOOST)
    assert hass.services.async_call.call_count == 2

    runtime_data.live_activity.ended_at = dt_util.utcnow() - timedelta(
        seconds=LIVE_ACTIVITY_RESTART_COOLDOWN_SECONDS + 1
    )
    await service.send_ev_charging_live_activity(mode=LIVE_ACTIVITY_MODE_BOOST)
    assert hass.services.async_call.call_count == 3


async def test_owner_presence_gates_the_start_but_not_the_refresh(hass) -> None:
    """An open card must keep tracking the session even once the owner leaves."""
    hass.services.async_call = AsyncMock()
    _charging_states(hass, soc="60")
    _enable_live_activities(hass)
    hass.states.async_set("person.owner", "home")
    runtime_data = _runtime_data()
    service = MobileNotificationService(
        hass,
        notify_services=["mobile_app_test_phone"],
        entry_id="entry_123",
        car_owner_entity="person.owner",
        runtime_data=runtime_data,
    )

    await service.send_ev_charging_live_activity(mode=LIVE_ACTIVITY_MODE_BOOST)
    assert hass.services.async_call.call_count == 1

    hass.states.async_set("person.owner", "not_home")
    runtime_data.live_activity.last_update = dt_util.utcnow() - timedelta(hours=1)
    hass.states.async_set("sensor.evsc_cached_ev_soc", "70")
    await service.send_ev_charging_live_activity(mode=LIVE_ACTIVITY_MODE_BOOST)

    assert hass.services.async_call.call_count == 2


async def test_start_is_suppressed_while_the_owner_is_away(hass) -> None:
    """No new card is opened for someone who is not home."""
    hass.services.async_call = AsyncMock()
    _charging_states(hass)
    _enable_live_activities(hass)
    hass.states.async_set("person.owner", "not_home")
    service = MobileNotificationService(
        hass,
        notify_services=["mobile_app_test_phone"],
        entry_id="entry_123",
        car_owner_entity="person.owner",
        runtime_data=_runtime_data(),
    )

    await service.send_ev_charging_live_activity(mode=LIVE_ACTIVITY_MODE_BOOST)

    hass.services.async_call.assert_not_awaited()


async def test_ev_charging_live_activity_respects_the_helper_switch(hass) -> None:
    """Live Activity payloads are suppressed while the helper switch is OFF."""
    hass.services.async_call = AsyncMock()
    hass.states.async_set("switch.evsc_live_activities_enabled", "off")
    service = _service(hass, _runtime_data())

    await service.send_ev_charging_live_activity(
        mode=LIVE_ACTIVITY_MODE_BOOST, force=True
    )

    hass.services.async_call.assert_not_awaited()


async def test_soc_recovery_after_an_unavailable_sensor_still_refreshes(hass) -> None:
    """An activity opened without a readable SOC must not freeze permanently."""
    hass.services.async_call = AsyncMock()
    hass.states.async_set("sensor.evsc_cached_ev_soc", "unavailable")
    hass.states.async_set("sensor.evsc_today_ev_target", "80")
    hass.states.async_set("number.wallbox_current", "16")
    hass.states.async_set("sensor.wallbox_status", "charger_charging")
    _enable_live_activities(hass)
    runtime_data = _runtime_data()
    service = _service(hass, runtime_data)

    await service.send_ev_charging_live_activity(mode=LIVE_ACTIVITY_MODE_BOOST)
    assert hass.services.async_call.call_count == 1
    assert runtime_data.live_activity.last_pushed_soc is None

    runtime_data.live_activity.last_update = dt_util.utcnow() - timedelta(hours=1)
    hass.states.async_set("sensor.evsc_cached_ev_soc", "61")
    await service.send_ev_charging_live_activity(mode=LIVE_ACTIVITY_MODE_BOOST)

    assert hass.services.async_call.call_count == 2
    assert runtime_data.live_activity.last_pushed_soc == 61.0


async def test_no_notify_services_never_marks_an_activity_open(hass) -> None:
    """Without notify services nothing is dispatched, so nothing is 'open'."""
    hass.services.async_call = AsyncMock()
    _charging_states(hass)
    _enable_live_activities(hass)
    runtime_data = _runtime_data()
    service = MobileNotificationService(
        hass,
        notify_services=[],
        entry_id="entry_123",
        runtime_data=runtime_data,
    )

    await service.send_ev_charging_live_activity(mode=LIVE_ACTIVITY_MODE_BOOST)

    hass.services.async_call.assert_not_awaited()
    assert runtime_data.live_activity.active is False

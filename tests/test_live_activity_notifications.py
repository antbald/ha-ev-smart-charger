"""Live Activity notification payloads."""
from __future__ import annotations

from unittest.mock import AsyncMock, Mock

from custom_components.ev_smart_charger.const import (
    CONF_EV_CHARGER_CURRENT,
    CONF_EV_CHARGER_STATUS,
    HELPER_CACHED_EV_SOC_SUFFIX,
    HELPER_TODAY_EV_TARGET_SUFFIX,
)
from custom_components.ev_smart_charger.runtime import EVSCRuntimeData
from custom_components.ev_smart_charger.utils.mobile_notification_service import (
    LIVE_ACTIVITY_TAG,
    MobileNotificationService,
)


def _runtime_data() -> EVSCRuntimeData:
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
    runtime_data.power_model = Mock(read_charging_power=Mock(return_value=7300.0))
    return runtime_data


async def test_ev_charging_live_activity_payload_uses_current_snapshot(hass) -> None:
    """Live Activity payload exposes SOC, target, status, speed, and tap URL."""
    hass.services.async_call = AsyncMock()
    hass.states.async_set("sensor.evsc_cached_ev_soc", "62.4")
    hass.states.async_set("sensor.evsc_today_ev_target", "80")
    hass.states.async_set("number.wallbox_current", "16")
    hass.states.async_set("sensor.wallbox_status", "charger_charging")

    service = MobileNotificationService(
        hass,
        notify_services=["mobile_app_test_phone"],
        entry_id="entry_123",
        runtime_data=_runtime_data(),
    )

    await service.send_ev_charging_live_activity(mode="Boost", force=True)

    notify_call = hass.services.async_call.await_args
    payload = notify_call.args[2]
    data = payload["data"]
    assert notify_call.args[0] == "notify"
    assert notify_call.args[1] == "mobile_app_test_phone"
    assert payload["title"] == "EV Charging"
    assert payload["message"] == "Boost · Charging · 7.3 kW · Target 80%"
    assert data["tag"] == LIVE_ACTIVITY_TAG
    assert data["live_update"] is True
    assert data["critical_text"] == "62%"
    assert data["progress"] == 62
    assert data["progress_max"] == 100
    assert data["notification_icon"] == "mdi:ev-station"
    assert data["url"] == "/ev-smart-charger"


async def test_clear_ev_charging_live_activity_uses_clear_notification(hass) -> None:
    """Live Activity is closed with the companion clear command."""
    hass.services.async_call = AsyncMock()
    service = MobileNotificationService(
        hass,
        notify_services=["mobile_app_test_phone"],
        entry_id="entry_123",
    )

    await service.clear_ev_charging_live_activity()

    notify_call = hass.services.async_call.await_args
    payload = notify_call.args[2]
    assert payload["message"] == "clear_notification"
    assert payload["data"]["tag"] == LIVE_ACTIVITY_TAG
    assert "live_update" not in payload["data"]


async def test_ev_charging_live_activity_skips_unchanged_signature(hass) -> None:
    """Repeated unchanged snapshots do not burn notification budget."""
    hass.services.async_call = AsyncMock()
    hass.states.async_set("sensor.evsc_cached_ev_soc", "60")
    hass.states.async_set("sensor.evsc_today_ev_target", "80")
    hass.states.async_set("number.wallbox_current", "16")
    hass.states.async_set("sensor.wallbox_status", "charger_charging")
    service = MobileNotificationService(
        hass,
        notify_services=["mobile_app_test_phone"],
        entry_id="entry_123",
        runtime_data=_runtime_data(),
    )

    await service.send_ev_charging_live_activity(mode="Boost")
    await service.send_ev_charging_live_activity(mode="Boost")

    assert hass.services.async_call.call_count == 1

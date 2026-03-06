"""Tests for EVSOCMonitor and AstralTimeService."""
from __future__ import annotations

from datetime import datetime, time, timedelta
from unittest.mock import AsyncMock, Mock, patch

from custom_components.ev_smart_charger.const import CONF_SOC_CAR, HELPER_CACHED_EV_SOC_SUFFIX
from custom_components.ev_smart_charger.ev_soc_monitor import EVSOCMonitor
from custom_components.ev_smart_charger.runtime import EVSCRuntimeData
from custom_components.ev_smart_charger.utils.astral_time_service import AstralTimeService


async def test_ev_soc_monitor_setup_uses_runtime_registry(hass):
    """Monitor setup resolves cache sensor from runtime_data and starts polling."""
    runtime_data = EVSCRuntimeData(config={}, expected_entity_count=0)
    cache_sensor = AsyncMock()
    runtime_data.entity_ids_by_key[HELPER_CACHED_EV_SOC_SUFFIX] = "sensor.evsc_cached_ev_soc"
    runtime_data.entities_by_key[HELPER_CACHED_EV_SOC_SUFFIX] = cache_sensor

    monitor = EVSOCMonitor(
        hass,
        "entry-1",
        {CONF_SOC_CAR: "sensor.ev_source_soc"},
        runtime_data=runtime_data,
    )

    with patch(
        "custom_components.ev_smart_charger.ev_soc_monitor.async_track_time_interval",
        return_value=lambda: None,
    ) as track_mock:
        await monitor.async_setup()

    assert monitor._cache_entity == "sensor.evsc_cached_ev_soc"
    assert monitor._cache_sensor is cache_sensor
    track_mock.assert_called_once()


async def test_ev_soc_monitor_publishes_valid_source_updates(hass):
    """Valid source values update the runtime-owned cache sensor entity."""
    runtime_data = EVSCRuntimeData(config={}, expected_entity_count=0)
    cache_sensor = AsyncMock()
    runtime_data.entity_ids_by_key[HELPER_CACHED_EV_SOC_SUFFIX] = "sensor.evsc_cached_ev_soc"
    runtime_data.entities_by_key[HELPER_CACHED_EV_SOC_SUFFIX] = cache_sensor
    hass.states.async_set("sensor.ev_source_soc", "55")

    monitor = EVSOCMonitor(
        hass,
        "entry-1",
        {CONF_SOC_CAR: "sensor.ev_source_soc"},
        runtime_data=runtime_data,
    )

    with patch(
        "custom_components.ev_smart_charger.ev_soc_monitor.async_track_time_interval",
        return_value=lambda: None,
    ):
        await monitor.async_setup()

    await monitor._async_poll_source_sensor()

    cache_sensor.async_publish_cache.assert_awaited_once()
    assert monitor._last_valid_value == 55.0
    assert monitor._last_source_state == "valid"


async def test_ev_soc_monitor_keeps_cache_for_invalid_source_state(hass):
    """Unavailable source values do not overwrite the cached SOC."""
    runtime_data = EVSCRuntimeData(config={}, expected_entity_count=0)
    cache_sensor = AsyncMock()
    runtime_data.entity_ids_by_key[HELPER_CACHED_EV_SOC_SUFFIX] = "sensor.evsc_cached_ev_soc"
    runtime_data.entities_by_key[HELPER_CACHED_EV_SOC_SUFFIX] = cache_sensor
    hass.states.async_set("sensor.ev_source_soc", "unavailable")

    monitor = EVSOCMonitor(
        hass,
        "entry-1",
        {CONF_SOC_CAR: "sensor.ev_source_soc"},
        runtime_data=runtime_data,
    )
    monitor._last_valid_value = 42.0

    with patch(
        "custom_components.ev_smart_charger.ev_soc_monitor.async_track_time_interval",
        return_value=lambda: None,
    ):
        await monitor.async_setup()

    await monitor._async_poll_source_sensor()

    cache_sensor.async_publish_cache.assert_not_awaited()
    assert monitor._last_valid_value == 42.0
    assert monitor._last_source_state == "unavailable"


async def test_ev_soc_monitor_remove_cleans_up_timer(hass):
    """Monitor cleanup unsubscribes the timer."""
    runtime_data = EVSCRuntimeData(config={}, expected_entity_count=0)
    runtime_data.entity_ids_by_key[HELPER_CACHED_EV_SOC_SUFFIX] = "sensor.evsc_cached_ev_soc"
    runtime_data.entities_by_key[HELPER_CACHED_EV_SOC_SUFFIX] = AsyncMock()
    unsub = Mock()

    monitor = EVSOCMonitor(
        hass,
        "entry-1",
        {CONF_SOC_CAR: "sensor.ev_source_soc"},
        runtime_data=runtime_data,
    )
    monitor._timer_unsub = unsub

    await monitor.async_remove()

    unsub.assert_called_once()
    assert monitor._timer_unsub is None


def _fake_astral_event(_hass, event_name: str, reference_date: datetime):
    """Return deterministic sunrise/sunset values for tests."""
    base_date = reference_date.date()
    if event_name == "sunset":
        return datetime.combine(base_date, time(18, 0))
    return datetime.combine(base_date, time(7, 0))


def test_astral_time_service_day_and_night_calculations(hass):
    """Nighttime helpers cover the main sunrise/sunset branches."""
    service = AstralTimeService(hass)

    with patch(
        "custom_components.ev_smart_charger.utils.astral_time_service.get_astral_event_date",
        side_effect=_fake_astral_event,
    ):
        assert service.get_sunset(datetime(2026, 3, 6, 12, 0)) == datetime(2026, 3, 6, 18, 0)
        assert service.get_sunrise(datetime(2026, 3, 6, 12, 0)) == datetime(2026, 3, 6, 7, 0)
        assert service.is_after_sunset(datetime(2026, 3, 6, 19, 0)) is True
        assert service.is_before_sunrise(datetime(2026, 3, 6, 6, 0)) is True
        assert service.is_nighttime(datetime(2026, 3, 6, 22, 0)) is True
        assert service.is_nighttime(datetime(2026, 3, 6, 6, 0)) is True
        assert service.is_nighttime(datetime(2026, 3, 6, 12, 0)) is False


def test_astral_time_service_next_sunrise_and_blocking_window(hass):
    """Blocking-window calculations handle before-sunrise and night-charge cases."""
    service = AstralTimeService(hass)
    reference_time = datetime(2026, 3, 6, 5, 30)
    night_charge_time = datetime(2026, 3, 6, 1, 0)

    with patch(
        "custom_components.ev_smart_charger.utils.astral_time_service.get_astral_event_date",
        side_effect=_fake_astral_event,
    ):
        assert service.get_next_sunrise_after(reference_time) == datetime(2026, 3, 6, 7, 0)
        assert service.get_next_sunrise_after(datetime(2026, 3, 6, 8, 0)) == datetime(2026, 3, 7, 7, 0)

        window_start, window_end, description = service.get_blocking_window(reference_time)
        assert window_start == datetime(2026, 3, 5, 18, 0)
        assert window_end == datetime(2026, 3, 6, 7, 0)
        assert description == "sunset → sunrise"

        window_start, window_end, description = service.get_blocking_window(
            datetime(2026, 3, 6, 20, 0),
            night_charge_enabled=True,
            night_charge_time=night_charge_time,
        )
        assert window_start == datetime(2026, 3, 6, 18, 0)
        assert window_end == night_charge_time
        assert description == "sunset → night_charge_time"


def test_astral_time_service_blocking_window_states(hass):
    """Window state helper returns clear reasons for each branch."""
    service = AstralTimeService(hass)

    with patch.object(
        service,
        "get_blocking_window",
        return_value=(None, None, "Unable to determine sunset time"),
    ):
        assert service.is_in_blocking_window(datetime(2026, 3, 6, 12, 0)) == (
            False,
            "Window calculation failed: Unable to determine sunset time",
        )

    with patch.object(
        service,
        "get_blocking_window",
        return_value=(
            datetime(2026, 3, 6, 18, 0),
            datetime(2026, 3, 7, 7, 0),
            "sunset → sunrise",
        ),
    ):
        assert service.is_in_blocking_window(datetime(2026, 3, 6, 17, 0)) == (
            False,
            "Before blocking window",
        )
        assert service.is_in_blocking_window(datetime(2026, 3, 6, 21, 0)) == (
            True,
            "Nighttime blocking active (sunset → sunrise)",
        )
        assert service.is_in_blocking_window(datetime(2026, 3, 7, 8, 0)) == (
            False,
            "After blocking window (charging allowed)",
        )

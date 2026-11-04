"""Tests for v2.15.0 — issues #66, #67, #68.

- #66: a sustained grid loss pauses Night Smart Charge grid mode instead of
  ending the night; charging resumes once the grid is stable again, and the
  night window survives midnight.
- #67: off-grid with no surplus, Solar Surplus stops in one action, and a
  flickering "disconnected" status no longer orphans a running charger.
- #68: Boost Charge home-battery floor (default ON), optional grid-loss
  pause/resume and optional stale EV SOC guard.
"""
import time
from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.util import dt as dt_util

from custom_components.ev_smart_charger.boost_charge import (
    BOOST_MAX_SOC_READ_FAILURES,
    BoostCharge,
)
from custom_components.ev_smart_charger.const import (
    CONF_EV_CHARGER_STATUS,
    CONF_FV_PRODUCTION,
    CONF_GRID_AVAILABLE,
    CONF_GRID_IMPORT,
    CONF_HOME_CONSUMPTION,
    CONF_NOTIFY_SERVICES,
    CONF_SOC_HOME,
    GRID_RESTORE_STABLE_SECONDS,
    NIGHT_CHARGE_MODE_GRID,
    SOLAR_DISCONNECT_RELEASE_SECONDS,
)
from custom_components.ev_smart_charger.night_smart_charge import (
    STOP_REASON_GRID_LOSS,
)
from custom_components.ev_smart_charger.solar_surplus import SolarSurplusAutomation

from .test_night_smart_charge import night_charge  # noqa: F401  (fixture)


def _ago(seconds: float):
    return dt_util.now() - timedelta(seconds=seconds)


# ============================================================================
# #66 — Night Smart Charge: grid loss pauses, grid restore resumes
# ============================================================================


def _prime_night_grid(night_charge, grid_available):
    night_charge._active_mode = NIGHT_CHARGE_MODE_GRID
    night_charge.is_active = MagicMock(return_value=True)
    night_charge._boost_charge = None
    night_charge._ensure_control = AsyncMock(return_value=True)
    night_charge._acquire_control = AsyncMock(return_value=True)
    night_charge._should_stop_for_deadline = AsyncMock(return_value=(False, ""))
    night_charge._complete_night_charge = AsyncMock()
    night_charge._mobile_notifier.clear_ev_charging_live_activity = AsyncMock()
    night_charge.priority_balancer.is_ev_target_reached = AsyncMock(return_value=False)
    model = MagicMock()
    model.is_grid_available = MagicMock(return_value=grid_available)
    night_charge._power_model = model
    return model


async def test_night_grid_loss_pauses_without_completing(hass, night_charge):
    _prime_night_grid(night_charge, grid_available=False)
    night_charge._grid_loss_tracker._stable_since = _ago(45)

    await night_charge._async_monitor_grid_charge(None)

    night_charge.charger_controller.stop_charger.assert_awaited_once()
    night_charge._complete_night_charge.assert_not_awaited()
    assert night_charge._waiting_for_grid is True


async def test_night_grid_loss_debounce_does_not_pause(hass, night_charge):
    _prime_night_grid(night_charge, grid_available=False)
    night_charge._grid_loss_tracker._stable_since = _ago(5)

    assert await night_charge._handle_grid_availability(dt_util.now()) is False

    night_charge.charger_controller.stop_charger.assert_not_awaited()
    assert night_charge._waiting_for_grid is False


async def test_night_waits_until_grid_stable_then_resumes(hass, night_charge):
    model = _prime_night_grid(night_charge, grid_available=True)
    night_charge._waiting_for_grid = True

    # Grid just came back: no restart yet (anti-flap).
    await night_charge._async_monitor_grid_charge(None)
    night_charge.charger_controller.start_charger.assert_not_awaited()
    assert night_charge._waiting_for_grid is True

    # Flap: grid off again resets the stability window.
    model.is_grid_available.return_value = False
    await night_charge._async_monitor_grid_charge(None)
    assert night_charge._grid_restore_tracker._stable_since is None

    # Stable for the restore delay → resume.
    model.is_grid_available.return_value = True
    night_charge._grid_restore_tracker._stable_since = _ago(
        GRID_RESTORE_STABLE_SECONDS + 1
    )
    await night_charge._async_monitor_grid_charge(None)
    night_charge.charger_controller.start_charger.assert_awaited_once()
    assert night_charge._waiting_for_grid is False
    night_charge._complete_night_charge.assert_not_awaited()


async def test_night_waiting_session_still_ends_at_deadline(hass, night_charge):
    _prime_night_grid(night_charge, grid_available=False)
    night_charge._waiting_for_grid = True
    night_charge._should_stop_for_deadline = AsyncMock(return_value=(True, "Sunrise"))

    await night_charge._async_monitor_grid_charge(None)

    night_charge._complete_night_charge.assert_awaited_once()
    night_charge.charger_controller.start_charger.assert_not_awaited()


async def test_night_complete_clears_waiting_state(hass, night_charge):
    night_charge._waiting_for_grid = True
    await night_charge._complete_night_charge(STOP_REASON_GRID_LOSS, terminal=True)
    assert night_charge._waiting_for_grid is False


async def test_night_window_survives_midnight(hass, night_charge):
    """A 23:15 window evaluated at 01:30 belongs to the night that began yesterday."""
    hass.states.async_set("input_datetime.test_evsc_night_charge_time", "23:15:00")
    now = dt_util.now().replace(hour=1, minute=30, second=0, microsecond=0)
    sunrise = now.replace(hour=6, minute=30)
    night_charge._astral_service.get_next_sunrise_after = MagicMock(return_value=sunrise)

    start = night_charge._resolve_night_window_start(now, "23:15:00")

    assert start.date() == (now - timedelta(days=1)).date()
    assert (start.hour, start.minute) == (23, 15)
    assert await night_charge._is_in_active_window(now) is True


async def test_night_early_window_keeps_today_occurrence(hass, night_charge):
    """A 01:00 window at 00:30 must not reach back to yesterday's (ended) night."""
    now = dt_util.now().replace(hour=0, minute=30, second=0, microsecond=0)
    yesterday_sunrise = (now - timedelta(days=1)).replace(hour=6, minute=30)
    night_charge._astral_service.get_next_sunrise_after = MagicMock(
        return_value=yesterday_sunrise
    )

    start = night_charge._resolve_night_window_start(now, "01:00:00")

    assert start.date() == now.date()
    assert start.hour == 1


async def test_night_completion_latch_follows_the_night(hass, night_charge):
    hass.states.async_set("input_datetime.test_evsc_night_charge_time", "23:15:00")
    now = dt_util.now().replace(hour=0, minute=20, second=0, microsecond=0)
    night_charge._astral_service.get_next_sunrise_after = MagicMock(
        return_value=now.replace(hour=6, minute=30)
    )
    # Terminal stop at 23:50 yesterday → still latched after midnight.
    night_charge._last_completion_time = (now - timedelta(days=1)).replace(
        hour=23, minute=50
    )
    assert night_charge._completion_in_current_night(now) is True

    # A 06:50 morning stop does not block the same evening's window.
    evening = now.replace(hour=23, minute=20)
    night_charge._last_completion_time = now.replace(hour=6, minute=50)
    assert night_charge._completion_in_current_night(evening) is False


# ============================================================================
# #67 — Solar Surplus off-grid stop + status glitch
# ============================================================================

GRID_ENTITY = "binary_sensor.grid_available"


@pytest.fixture
def surplus(hass, mock_charger_controller, mock_priority_balancer):
    config = {
        CONF_EV_CHARGER_STATUS: "sensor.charger_status",
        CONF_FV_PRODUCTION: "sensor.solar",
        CONF_HOME_CONSUMPTION: "sensor.consumption",
        CONF_GRID_IMPORT: "sensor.grid",
        CONF_SOC_HOME: "sensor.home_soc",
        CONF_GRID_AVAILABLE: GRID_ENTITY,
    }
    with patch(
        "custom_components.ev_smart_charger.solar_surplus.AstralTimeService"
    ) as astral:
        astral.return_value.is_nighttime.return_value = False
        auto = SolarSurplusAutomation(
            hass, "test_entry", config, mock_priority_balancer, mock_charger_controller
        )
    auto._acquire_control = AsyncMock(return_value=True)
    auto._ensure_control = AsyncMock(return_value=True)
    return auto


async def test_offgrid_zero_surplus_stops_in_one_action(hass, surplus):
    hass.states.async_set(GRID_ENTITY, "off")
    surplus._last_surplus_sufficient = time.monotonic() - 100  # delay elapsed

    await surplus._handle_surplus_decrease(0, 17, -0.25, 30)

    surplus.charger_controller.stop_charger.assert_awaited_once()
    surplus.charger_controller.set_amperage.assert_not_awaited()


async def test_grid_present_keeps_gradual_ramp(hass, surplus):
    hass.states.async_set(GRID_ENTITY, "on")
    surplus._last_surplus_sufficient = time.monotonic() - 100

    await surplus._handle_surplus_decrease(0, 16, -0.25, 30)

    surplus.charger_controller.stop_charger.assert_not_awaited()
    surplus.charger_controller.set_amperage.assert_awaited_once()


async def test_offgrid_stop_still_respects_drop_delay(hass, surplus):
    hass.states.async_set(GRID_ENTITY, "off")

    await surplus._handle_surplus_decrease(0, 17, -0.25, 30)  # arms the delay

    surplus.charger_controller.stop_charger.assert_not_awaited()


async def test_disconnect_flicker_with_charger_on_is_a_glitch(hass, surplus):
    surplus.charger_controller.is_charging = AsyncMock(return_value=True)

    assert await surplus._is_disconnect_glitch() is True
    # Held past the release window → genuine disconnect.
    surplus._disconnected_since -= SOLAR_DISCONNECT_RELEASE_SECONDS + 1
    assert await surplus._is_disconnect_glitch() is False


async def test_disconnect_with_charger_off_is_never_a_glitch(hass, surplus):
    surplus.charger_controller.is_charging = AsyncMock(return_value=False)
    assert await surplus._is_disconnect_glitch() is False


# ============================================================================
# #68 — Boost Charge protections
# ============================================================================

HELPERS = {
    "evsc_boost_home_battery_protection": "switch.boost_home_prot",
    "evsc_boost_stop_on_grid_loss": "switch.boost_grid_loss",
    "evsc_boost_stale_soc_guard": "switch.boost_stale",
    "evsc_boost_stale_soc_minutes": "number.boost_stale_minutes",
    "evsc_home_battery_min_soc": "number.home_min",
    "evsc_grid_import_threshold": "number.grid_threshold",
    "evsc_grid_import_delay": "number.grid_delay",
}


@pytest.fixture
def boost(hass, mock_priority_balancer, mock_charger_controller):
    coordinator = MagicMock()
    coordinator.request_charger_action = AsyncMock(return_value=(True, "ok"))
    b = BoostCharge(
        hass,
        "test_entry",
        {CONF_NOTIFY_SERVICES: [], CONF_SOC_HOME: "sensor.home_soc"},
        mock_priority_balancer,
        mock_charger_controller,
        coordinator=coordinator,
    )
    b._resolve_entity = lambda key: HELPERS.get(key)
    b._boost_amperage_entity = "number.boost_amps"
    b._boost_target_soc_entity = "number.boost_target"
    b._boost_active = True
    b._monitor_unsub = lambda: None
    b._set_boost_switch = AsyncMock()
    b._request_normal_recheck = AsyncMock()
    b._notification_service.send_warning = AsyncMock()
    b._notification_service.send_success = AsyncMock()
    b._mobile_notifier.send_boost_charge_completed_notification = AsyncMock()
    b._mobile_notifier.send_ev_charging_live_activity = AsyncMock()
    b._mobile_notifier.clear_ev_charging_live_activity = AsyncMock()
    b.priority_balancer._soc_car = "sensor.ev_soc"
    b.priority_balancer.get_ev_current_soc = AsyncMock(return_value=31)
    b.charger_controller.get_current_amperage.return_value = 16

    model = MagicMock()
    model.is_grid_available = MagicMock(return_value=True)
    model.read_grid_import = MagicMock(return_value=0.0)
    model.read_battery_discharge = MagicMock(return_value=3800.0)
    b._runtime_data = MagicMock()
    b._runtime_data.power_model = model
    b._runtime_data.diagnostic_manager = None

    for entity, state in {
        "switch.boost_home_prot": "on",
        "switch.boost_grid_loss": "off",
        "switch.boost_stale": "off",
        "number.boost_stale_minutes": "60",
        "number.home_min": "35",
        "number.grid_threshold": "50",
        "number.grid_delay": "30",
        "number.boost_amps": "16",
        "number.boost_target": "50",
        "sensor.ev_soc": "31",
        "sensor.home_soc": "60",
    }.items():
        hass.states.async_set(entity, state)
    return b


async def test_boost_home_floor_stops_after_debounce(hass, boost):
    hass.states.async_set("sensor.home_soc", "35")

    await boost._async_monitor_boost_charge(None)  # arms the debounce
    assert boost.is_active() is True

    boost._home_floor_tracker._stable_since = _ago(31)
    await boost._async_monitor_boost_charge(None)

    assert boost.is_active() is False
    boost.charger_controller.stop_charger.assert_awaited_once()
    boost._notification_service.send_warning.assert_awaited_once()


@pytest.mark.parametrize("grid_loss_switch", ["on", "off"])
async def test_boost_home_floor_independent_of_grid_loss_switch(
    hass, boost, grid_loss_switch
):
    hass.states.async_set("switch.boost_grid_loss", grid_loss_switch)
    hass.states.async_set("sensor.home_soc", "30")
    boost._home_floor_tracker._stable_since = _ago(31)
    # Grid present (no pause): the SOC floor alone decides.
    await boost._async_monitor_boost_charge(None)
    assert boost.is_active() is False


async def test_boost_home_floor_disabled_by_switch(hass, boost):
    hass.states.async_set("switch.boost_home_prot", "off")
    hass.states.async_set("sensor.home_soc", "10")
    boost._home_floor_tracker._stable_since = _ago(300)

    await boost._async_monitor_boost_charge(None)

    assert boost.is_active() is True


async def test_boost_home_floor_ignored_while_grid_supplies(hass, boost):
    hass.states.async_set("sensor.home_soc", "20")
    boost._runtime_data.power_model.read_grid_import.return_value = 3800.0
    boost._home_floor_tracker._stable_since = _ago(300)

    await boost._async_monitor_boost_charge(None)

    assert boost.is_active() is True


async def test_boost_home_soc_unavailable_stops_after_failures(hass, boost):
    hass.states.async_set("sensor.home_soc", "unavailable")
    for _ in range(BOOST_MAX_SOC_READ_FAILURES - 1):
        await boost._async_monitor_boost_charge(None)
        assert boost.is_active() is True
    await boost._async_monitor_boost_charge(None)
    assert boost.is_active() is False


async def test_boost_grid_loss_pauses_and_resumes(hass, boost):
    hass.states.async_set("switch.boost_grid_loss", "on")
    model = boost._runtime_data.power_model
    model.is_grid_available.return_value = False
    boost._grid_loss_tracker._stable_since = _ago(31)

    await boost._async_monitor_boost_charge(None)
    assert boost.is_active() is True
    assert boost.is_waiting_for_grid() is True
    boost.charger_controller.stop_charger.assert_awaited_once()

    # Grid back but not yet stable → still paused.
    model.is_grid_available.return_value = True
    await boost._async_monitor_boost_charge(None)
    boost.charger_controller.start_charger.assert_not_awaited()

    boost._grid_restore_tracker._stable_since = _ago(GRID_RESTORE_STABLE_SECONDS + 1)
    await boost._async_monitor_boost_charge(None)
    boost.charger_controller.start_charger.assert_awaited_once()
    assert boost.is_waiting_for_grid() is False


async def test_boost_grid_loss_ignored_when_switch_off(hass, boost):
    boost._runtime_data.power_model.is_grid_available.return_value = False
    boost._grid_loss_tracker._stable_since = _ago(300)

    await boost._async_monitor_boost_charge(None)

    boost.charger_controller.stop_charger.assert_not_awaited()
    assert boost.is_waiting_for_grid() is False


async def test_boost_stale_soc_guard_stops(hass, boost):
    hass.states.async_set("switch.boost_stale", "on")
    boost.charger_controller.is_charging = AsyncMock(return_value=True)

    await boost._async_monitor_boost_charge(None)  # records 31%
    assert boost.is_active() is True

    boost._soc_last_change = _ago(61 * 60)
    await boost._async_monitor_boost_charge(None)

    assert boost.is_active() is False


async def test_boost_stale_soc_guard_off_by_default(hass, boost):
    boost.charger_controller.is_charging = AsyncMock(return_value=True)
    await boost._async_monitor_boost_charge(None)
    boost._soc_last_change = _ago(600 * 60)
    await boost._async_monitor_boost_charge(None)
    assert boost.is_active() is True

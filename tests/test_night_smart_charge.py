"""Tests for Night Smart Charge automation - WORKING VERSION."""
import asyncio
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from custom_components.ev_smart_charger.night_smart_charge import (
    NightSmartCharge,
    STOP_REASON_BOOST_PREEMPTED,
    STOP_REASON_EV_TARGET,
    STOP_REASON_HOME_BATTERY_MIN,
)
from custom_components.ev_smart_charger.runtime import EVSCRuntimeData
from custom_components.ev_smart_charger.const import (
    CONF_EV_CHARGER_STATUS,
    CONF_EV_CHARGER_SWITCH,
    CONF_EV_CHARGER_CURRENT,
    CONF_GRID_IMPORT,
    CONF_FV_PRODUCTION,
    CONF_SOC_HOME,
    CONF_PV_FORECAST,
    CONF_NOTIFY_SERVICES,
    CHARGER_STATUS_CHARGING,
    CHARGER_STATUS_FREE,
    CHARGER_STATUS_WAIT,
    CHARGING_POWER_DRAWING_FLOOR_W,
    NIGHT_CHARGE_MODE_BATTERY,
    NIGHT_CHARGE_MODE_GRID,
    NIGHT_CHARGE_MODE_IDLE,
)
from homeassistant.util import dt as dt_util


@pytest.fixture
async def night_charge(hass, mock_priority_balancer, mock_charger_controller):
    """Create NightSmartCharge instance with mocked dependencies."""
    config = {
        CONF_EV_CHARGER_STATUS: "sensor.charger_status",
        CONF_EV_CHARGER_SWITCH: "switch.charger_switch",
        CONF_EV_CHARGER_CURRENT: "sensor.charger_current",
        CONF_GRID_IMPORT: "sensor.grid_import",
        CONF_FV_PRODUCTION: "sensor.fv_production",
        CONF_SOC_HOME: "sensor.home_soc",
        CONF_PV_FORECAST: "sensor.pv_forecast",
        CONF_NOTIFY_SERVICES: [],
    }
    runtime_data = EVSCRuntimeData(config=config, expected_entity_count=0)
    helper_map = {
        "evsc_night_smart_charge_enabled": "switch.test_evsc_night_smart_charge_enabled",
        "evsc_preserve_home_battery": "switch.test_evsc_preserve_home_battery",
        "evsc_night_charge_time": "input_datetime.test_evsc_night_charge_time",
        "evsc_car_ready_time": "input_datetime.test_evsc_car_ready_time",
        "evsc_night_charge_amperage": "number.test_evsc_night_charge_amperage",
        "evsc_min_solar_forecast_threshold": "number.test_evsc_min_solar_forecast_threshold",
        "evsc_night_pv_handoff_threshold": "number.test_evsc_night_pv_handoff_threshold",
        "evsc_home_battery_min_soc": "number.test_evsc_home_battery_min_soc",
        "evsc_grid_import_threshold": "number.test_evsc_grid_import_threshold",
        "evsc_grid_import_delay": "number.test_evsc_grid_import_delay",
        "evsc_car_ready_monday": "input_boolean.test_evsc_car_ready_monday",
        "evsc_car_ready_tuesday": "input_boolean.test_evsc_car_ready_tuesday",
        "evsc_car_ready_wednesday": "input_boolean.test_evsc_car_ready_wednesday",
        "evsc_car_ready_thursday": "input_boolean.test_evsc_car_ready_thursday",
        "evsc_car_ready_friday": "input_boolean.test_evsc_car_ready_friday",
        "evsc_car_ready_saturday": "input_boolean.test_evsc_car_ready_saturday",
        "evsc_car_ready_sunday": "input_boolean.test_evsc_car_ready_sunday",
    }
    for key, entity_id in helper_map.items():
        runtime_data.register_entity(key, entity_id, object())

    night_charge = NightSmartCharge(
        hass,
        "test_entry",
        config,
        mock_priority_balancer,
        mock_charger_controller,
        runtime_data=runtime_data,
    )
    
    # Setup helper entities
    hass.states.async_set("switch.test_evsc_night_smart_charge_enabled", "on")
    hass.states.async_set("switch.test_evsc_preserve_home_battery", "off")
    hass.states.async_set("switch.charger_switch", "off")
    hass.states.async_set("sensor.charger_current", "0")
    hass.states.async_set("input_datetime.test_evsc_night_charge_time", "01:00:00")
    hass.states.async_set("input_datetime.test_evsc_car_ready_time", "08:00:00")
    hass.states.async_set("number.test_evsc_night_charge_amperage", "10")
    hass.states.async_set("number.test_evsc_min_solar_forecast_threshold", "10.0")
    hass.states.async_set("number.test_evsc_night_pv_handoff_threshold", "0")
    hass.states.async_set("number.test_evsc_home_battery_min_soc", "20.0")
    hass.states.async_set("number.test_evsc_grid_import_threshold", "50")
    hass.states.async_set("number.test_evsc_grid_import_delay", "30")
    hass.states.async_set("sensor.grid_import", "0")
    hass.states.async_set("sensor.fv_production", "0")
    for day in [
        "monday",
        "tuesday",
        "wednesday",
        "thursday",
        "friday",
        "saturday",
        "sunday",
    ]:
        hass.states.async_set(f"input_boolean.test_evsc_car_ready_{day}", "on")

    await night_charge.async_setup()
    return night_charge


# ============================================================================
# WORKING TESTS - Battery & Grid Mode
# ============================================================================

async def test_evaluate_and_charge_battery_mode(hass, night_charge):
    """Test evaluation leading to battery mode."""
    # Setup states
    hass.states.async_set("switch.test_evsc_night_smart_charge_enabled", "on")
    hass.states.async_set("sensor.charger_status", "Charging")
    hass.states.async_set("sensor.pv_forecast", "20.0")  # High forecast
    hass.states.async_set("number.test_evsc_min_solar_forecast_threshold", "10.0")
    hass.states.async_set("number.test_evsc_night_charge_amperage", "10")
    hass.states.async_set("sensor.home_soc", "80")
    hass.states.async_set("number.test_evsc_home_battery_min_soc", "20")
    
    # Configure Priority Balancer attributes for critical sensor check
    night_charge.priority_balancer._soc_car = "sensor.ev_soc"
    night_charge.priority_balancer._ev_min_soc_entities = {6: "number.ev_target"}  # Sunday
    hass.states.async_set("sensor.ev_soc", "40")
    hass.states.async_set("number.ev_target", "80")
    
    # Mock dependencies
    future = asyncio.Future()
    future.set_result(40)
    night_charge.priority_balancer.get_ev_current_soc.return_value = future
    
    night_charge.priority_balancer.get_home_current_soc = AsyncMock(return_value=80)
    night_charge.priority_balancer.get_ev_target_for_today.return_value = 80
    night_charge.priority_balancer.is_ev_target_reached.return_value = False
    
    # Mock _is_in_active_window to return True
    async def mock_is_in_active_window(now):
        return True
    night_charge._is_in_active_window = mock_is_in_active_window
    
    # Run evaluation
    with patch("custom_components.ev_smart_charger.night_smart_charge.dt_util.now", return_value=datetime(2023, 1, 1, 2, 0, 0)):
        await night_charge._evaluate_and_charge()
        
    # Verify
    assert night_charge.is_active() is True
    assert night_charge.get_active_mode() == NIGHT_CHARGE_MODE_BATTERY
    night_charge.charger_controller.start_charger.assert_called_with(10, "Night charge - Battery mode")


async def test_evaluate_and_charge_grid_mode(hass, night_charge):
    """Test evaluation leading to grid mode."""
    # Setup states
    hass.states.async_set("switch.test_evsc_night_smart_charge_enabled", "on")
    hass.states.async_set("input_boolean.test_evsc_car_ready_sunday", "on")
    hass.states.async_set("sensor.charger_status", "Charging")
    hass.states.async_set("sensor.home_soc", "10")  # Low home battery
    hass.states.async_set("sensor.pv_forecast", "5")  # Low solar
    hass.states.async_set("number.test_evsc_min_solar_forecast_threshold", "10")
    hass.states.async_set("number.test_evsc_night_charge_amperage", "10")
    hass.states.async_set("number.test_evsc_home_battery_min_soc", "20")
    
    # Configure Priority Balancer attributes for critical sensor check
    night_charge.priority_balancer._soc_car = "sensor.ev_soc"
    night_charge.priority_balancer._ev_min_soc_entities = {6: "number.ev_target"}  # Sunday
    hass.states.async_set("sensor.ev_soc", "40")
    hass.states.async_set("number.ev_target", "80")
    
    # Mock dependencies
    future = asyncio.Future()
    future.set_result(40)
    night_charge.priority_balancer.get_ev_current_soc.return_value = future
    
    night_charge.priority_balancer.get_home_current_soc = AsyncMock(return_value=10)
    night_charge.priority_balancer.get_ev_target_for_today.return_value = 80
    night_charge.priority_balancer.is_ev_target_reached.return_value = False
    
    # Mock _is_in_active_window to return True
    async def mock_is_in_active_window(now):
        return True
    night_charge._is_in_active_window = mock_is_in_active_window
    
    # Run evaluation
    with patch("custom_components.ev_smart_charger.night_smart_charge.dt_util.now", return_value=datetime(2023, 1, 1, 2, 0, 0)):
        await night_charge._evaluate_and_charge()
        
    # Verify
    assert night_charge.is_active() is True
    assert night_charge.get_active_mode() == NIGHT_CHARGE_MODE_GRID
    night_charge.charger_controller.start_charger.assert_called_with(10, "Night charge - Grid mode")


async def test_evaluate_and_charge_uses_battery_only_when_car_ready_off_and_forecast_low(
    hass, night_charge
):
    """car_ready OFF must force battery-only overnight charging even with low forecast."""
    hass.states.async_set("switch.test_evsc_night_smart_charge_enabled", "on")
    hass.states.async_set("input_boolean.test_evsc_car_ready_sunday", "off")
    hass.states.async_set("sensor.charger_status", "Charging")
    hass.states.async_set("sensor.home_soc", "40")
    hass.states.async_set("sensor.pv_forecast", "5")
    hass.states.async_set("number.test_evsc_min_solar_forecast_threshold", "10")
    hass.states.async_set("number.test_evsc_night_charge_amperage", "10")
    hass.states.async_set("number.test_evsc_home_battery_min_soc", "20")

    night_charge.priority_balancer._soc_car = "sensor.ev_soc"
    night_charge.priority_balancer._ev_min_soc_entities = {"sunday": "number.ev_target"}
    hass.states.async_set("sensor.ev_soc", "40")
    hass.states.async_set("number.ev_target", "80")

    future = asyncio.Future()
    future.set_result(40)
    night_charge.priority_balancer.get_ev_current_soc.return_value = future
    night_charge.priority_balancer.get_home_current_soc = AsyncMock(return_value=40)
    night_charge.priority_balancer.get_ev_target_for_today.return_value = 80
    night_charge.priority_balancer.is_ev_target_reached.return_value = False
    night_charge._start_grid_charge = AsyncMock()
    night_charge._mobile_notifier.send_night_charge_notification = AsyncMock()

    async def mock_is_in_active_window(now):
        return True

    night_charge._is_in_active_window = mock_is_in_active_window

    with patch(
        "custom_components.ev_smart_charger.night_smart_charge.dt_util.now",
        return_value=datetime(2023, 1, 1, 2, 0, 0),
    ):
        await night_charge._evaluate_and_charge()

    assert night_charge.is_active() is True
    assert night_charge.get_active_mode() == NIGHT_CHARGE_MODE_BATTERY
    night_charge._start_grid_charge.assert_not_awaited()
    night_charge.charger_controller.start_charger.assert_awaited_once_with(
        10, "Night charge - Battery mode"
    )
    reason = night_charge._mobile_notifier.send_night_charge_notification.await_args.kwargs["reason"]
    assert "battery-only overnight charging" in reason
    assert "grid disabled" in reason


async def test_evaluate_and_charge_skips_when_car_ready_off_and_home_battery_at_min(
    hass, night_charge
):
    """car_ready OFF must skip overnight charging when home battery is already at minimum."""
    hass.states.async_set("switch.test_evsc_night_smart_charge_enabled", "on")
    hass.states.async_set("input_boolean.test_evsc_car_ready_sunday", "off")
    hass.states.async_set("sensor.charger_status", "Charging")
    hass.states.async_set("sensor.home_soc", "20")
    hass.states.async_set("sensor.pv_forecast", "5")
    hass.states.async_set("number.test_evsc_min_solar_forecast_threshold", "10")
    hass.states.async_set("number.test_evsc_night_charge_amperage", "10")
    hass.states.async_set("number.test_evsc_home_battery_min_soc", "20")

    night_charge.priority_balancer._soc_car = "sensor.ev_soc"
    night_charge.priority_balancer._ev_min_soc_entities = {"sunday": "number.ev_target"}
    hass.states.async_set("sensor.ev_soc", "40")
    hass.states.async_set("number.ev_target", "80")

    future = asyncio.Future()
    future.set_result(40)
    night_charge.priority_balancer.get_ev_current_soc.return_value = future
    night_charge.priority_balancer.get_home_current_soc = AsyncMock(return_value=20)
    night_charge.priority_balancer.get_ev_target_for_today.return_value = 80
    night_charge.priority_balancer.is_ev_target_reached.return_value = False
    night_charge._start_grid_charge = AsyncMock()
    night_charge._mobile_notifier.send_night_charge_notification = AsyncMock()

    async def mock_is_in_active_window(now):
        return True

    night_charge._is_in_active_window = mock_is_in_active_window

    with patch(
        "custom_components.ev_smart_charger.night_smart_charge.dt_util.now",
        return_value=datetime(2023, 1, 1, 2, 0, 0),
    ):
        await night_charge._evaluate_and_charge()

    assert night_charge.is_active() is False
    assert night_charge.get_active_mode() == NIGHT_CHARGE_MODE_IDLE
    night_charge._start_grid_charge.assert_not_awaited()
    night_charge.charger_controller.start_charger.assert_not_called()
    night_charge._mobile_notifier.send_night_charge_notification.assert_not_awaited()


async def test_evaluate_and_charge_skips_when_preserve_home_battery_enabled(
    hass, night_charge
):
    """car_ready OFF + preserve flag ON must skip the overnight session."""
    hass.states.async_set("switch.test_evsc_night_smart_charge_enabled", "on")
    hass.states.async_set("switch.test_evsc_preserve_home_battery", "on")
    hass.states.async_set("input_boolean.test_evsc_car_ready_sunday", "off")
    hass.states.async_set("sensor.charger_status", "Charging")
    hass.states.async_set("sensor.home_soc", "60")
    hass.states.async_set("sensor.pv_forecast", "5")
    hass.states.async_set("number.test_evsc_min_solar_forecast_threshold", "10")
    hass.states.async_set("number.test_evsc_night_charge_amperage", "10")
    hass.states.async_set("number.test_evsc_home_battery_min_soc", "20")

    night_charge.priority_balancer._soc_car = "sensor.ev_soc"
    night_charge.priority_balancer._ev_min_soc_entities = {"sunday": "number.ev_target"}
    hass.states.async_set("sensor.ev_soc", "40")
    hass.states.async_set("number.ev_target", "80")

    future = asyncio.Future()
    future.set_result(40)
    night_charge.priority_balancer.get_ev_current_soc.return_value = future
    night_charge.priority_balancer.get_home_current_soc = AsyncMock(return_value=60)
    night_charge.priority_balancer.get_ev_target_for_today.return_value = 80
    night_charge.priority_balancer.is_ev_target_reached.return_value = False
    night_charge._start_grid_charge = AsyncMock()
    night_charge._start_battery_charge = AsyncMock()
    night_charge._emit_diagnostic = AsyncMock()
    night_charge._mobile_notifier.send_night_charge_skipped_notification = AsyncMock()

    async def mock_is_in_active_window(now):
        return True

    night_charge._is_in_active_window = mock_is_in_active_window

    with patch(
        "custom_components.ev_smart_charger.night_smart_charge.dt_util.now",
        return_value=datetime(2023, 1, 1, 2, 0, 0),
    ):
        await night_charge._evaluate_and_charge()

    assert night_charge.is_active() is False
    assert night_charge.get_active_mode() == NIGHT_CHARGE_MODE_IDLE
    night_charge._start_grid_charge.assert_not_awaited()
    night_charge._start_battery_charge.assert_not_awaited()
    night_charge.charger_controller.start_charger.assert_not_called()
    night_charge._emit_diagnostic.assert_awaited_once()
    assert (
        night_charge._emit_diagnostic.await_args.kwargs["reason_code"]
        == "preserve_home_battery"
    )
    assert night_charge._emit_diagnostic.await_args.kwargs["result"] == "skipped"
    night_charge._mobile_notifier.send_night_charge_skipped_notification.assert_awaited_once()


async def test_evaluate_and_charge_preserve_flag_does_not_interrupt_active_session(
    hass, night_charge
):
    """Turning the preserve flag on mid-session must not stop the current charge."""
    hass.states.async_set("switch.test_evsc_night_smart_charge_enabled", "on")
    hass.states.async_set("switch.test_evsc_preserve_home_battery", "on")
    hass.states.async_set("input_boolean.test_evsc_car_ready_sunday", "off")
    hass.states.async_set("sensor.charger_status", "Charging")
    hass.states.async_set("sensor.home_soc", "60")
    hass.states.async_set("sensor.pv_forecast", "5")
    hass.states.async_set("number.test_evsc_min_solar_forecast_threshold", "10")
    hass.states.async_set("number.test_evsc_night_charge_amperage", "10")
    hass.states.async_set("number.test_evsc_home_battery_min_soc", "20")

    night_charge.priority_balancer._soc_car = "sensor.ev_soc"
    night_charge.priority_balancer._ev_min_soc_entities = {"sunday": "number.ev_target"}
    hass.states.async_set("sensor.ev_soc", "40")
    hass.states.async_set("number.ev_target", "80")

    future = asyncio.Future()
    future.set_result(40)
    night_charge.priority_balancer.get_ev_current_soc.return_value = future
    night_charge.priority_balancer.get_home_current_soc = AsyncMock(return_value=60)
    night_charge.priority_balancer.get_ev_target_for_today.return_value = 80
    night_charge.priority_balancer.is_ev_target_reached.return_value = False
    night_charge._emit_diagnostic = AsyncMock()
    night_charge._mobile_notifier.send_night_charge_skipped_notification = AsyncMock()
    night_charge.charger_controller.stop_charger = AsyncMock()
    night_charge._night_charge_active = True
    night_charge._active_mode = NIGHT_CHARGE_MODE_BATTERY

    async def mock_is_in_active_window(now):
        return True

    night_charge._is_in_active_window = mock_is_in_active_window

    with patch(
        "custom_components.ev_smart_charger.night_smart_charge.dt_util.now",
        return_value=datetime(2023, 1, 1, 2, 0, 0),
    ):
        await night_charge._evaluate_and_charge()

    assert night_charge.is_active() is True
    assert night_charge.get_active_mode() == NIGHT_CHARGE_MODE_BATTERY
    night_charge.charger_controller.stop_charger.assert_not_awaited()
    night_charge._mobile_notifier.send_night_charge_skipped_notification.assert_not_awaited()


# ============================================================================
# PRIORITY 1: EDGE CASES - SKIP/GUARD CONDITIONS
# ============================================================================

async def test_evaluate_skip_when_target_already_reached(hass, night_charge):
    """Test that evaluation skips when EV target is already reached."""
    # Setup states
    hass.states.async_set("switch.test_evsc_night_smart_charge_enabled", "on")
    hass.states.async_set("sensor.charger_status", "Charging")
    hass.states.async_set("sensor.pv_forecast", "20.0")
    hass.states.async_set("number.test_evsc_min_solar_forecast_threshold", "10.0")
    hass.states.async_set("number.test_evsc_night_charge_amperage", "10")
    hass.states.async_set("sensor.home_soc", "80")
    hass.states.async_set("number.test_evsc_home_battery_min_soc", "20")
    
    # Configure Priority Balancer
    night_charge.priority_balancer._soc_car = "sensor.ev_soc"
    night_charge.priority_balancer._ev_min_soc_entities = {6: "number.ev_target"}
    hass.states.async_set("sensor.ev_soc", "85")  # Already above target
    hass.states.async_set("number.ev_target", "80")
    
    # Mock - target already reached
    future = asyncio.Future()
    future.set_result(85)
    night_charge.priority_balancer.get_ev_current_soc.return_value = future
    night_charge.priority_balancer.get_home_current_soc = AsyncMock(return_value=80)
    night_charge.priority_balancer.get_ev_target_for_today.return_value = 80
    night_charge.priority_balancer.is_ev_target_reached.return_value = True  # Target reached!
    
    # Run evaluation
    with patch("custom_components.ev_smart_charger.night_smart_charge.dt_util.now", return_value=datetime(2023, 1, 1, 2, 0, 0)):
        await night_charge._evaluate_and_charge()
    
    # Verify - should not start charging
    assert night_charge.is_active() is False
    night_charge.charger_controller.start_charger.assert_not_called()


async def test_evaluate_skip_when_charger_status_free(hass, night_charge):
    """Test that evaluation skips when charger status is FREE (unplugged)."""
    # Setup states
    hass.states.async_set("switch.test_evsc_night_smart_charge_enabled", "on")
    hass.states.async_set("sensor.charger_status", CHARGER_STATUS_FREE)  # Unplugged!
    hass.states.async_set("sensor.pv_forecast", "20.0")
    hass.states.async_set("number.test_evsc_min_solar_forecast_threshold", "10.0")
    hass.states.async_set("number.test_evsc_night_charge_amperage", "10")
    hass.states.async_set("sensor.home_soc", "80")
    hass.states.async_set("number.test_evsc_home_battery_min_soc", "20")
    
    # Configure Priority Balancer
    night_charge.priority_balancer._soc_car = "sensor.ev_soc"
    night_charge.priority_balancer._ev_min_soc_entities = {6: "number.ev_target"}
    hass.states.async_set("sensor.ev_soc", "40")
    hass.states.async_set("number.ev_target", "80")
    
    future = asyncio.Future()
    future.set_result(40)
    night_charge.priority_balancer.get_ev_current_soc.return_value = future
    night_charge.priority_balancer.get_home_current_soc = AsyncMock(return_value=80)
    night_charge.priority_balancer.is_ev_target_reached.return_value = False
    
    # Run evaluation
    with patch("custom_components.ev_smart_charger.night_smart_charge.dt_util.now", return_value=datetime(2023, 1, 1, 2, 0, 0)):
        await night_charge._evaluate_and_charge()
    
    # Verify - should not start charging
    assert night_charge.is_active() is False
    night_charge.charger_controller.start_charger.assert_not_called()


async def test_evaluate_skip_when_boost_active(hass, night_charge):
    """Night Smart Charge should skip evaluation while Boost Charge is active."""
    night_charge._boost_charge = MagicMock()
    night_charge._boost_charge.is_active.return_value = True

    await night_charge._evaluate_and_charge()

    night_charge.charger_controller.start_charger.assert_not_called()


async def test_complete_night_charge_skips_cooldown_when_boost_is_active(hass, night_charge):
    """Boost preemption must not mark the night session as completed."""
    night_charge._night_charge_active = True
    night_charge._active_mode = NIGHT_CHARGE_MODE_GRID
    night_charge._session_state = "active"
    night_charge._last_completion_time = None
    night_charge._last_completion_date = None
    night_charge._boost_charge = MagicMock()
    night_charge._boost_charge.is_active.return_value = True

    await night_charge._complete_night_charge(STOP_REASON_EV_TARGET, terminal=True)

    assert night_charge.is_active() is False
    assert night_charge.get_active_mode() == NIGHT_CHARGE_MODE_IDLE
    assert night_charge._session_state == "ready"
    assert night_charge._last_completion_time is None
    assert night_charge._last_completion_date is None


async def test_get_car_ready_for_today_uses_ha_timezone(hass, night_charge):
    """Car-ready day selection must use Home Assistant timezone clock."""
    # Wednesday OFF, Thursday ON
    hass.states.async_set("switch.test_evsc_car_ready_wednesday", "off")
    hass.states.async_set("switch.test_evsc_car_ready_thursday", "on")
    night_charge._car_ready_entities = {
        2: "switch.test_evsc_car_ready_wednesday",
        3: "switch.test_evsc_car_ready_thursday",
    }

    # If HA time says Thursday, we must read Thursday flag (ON).
    with patch(
        "custom_components.ev_smart_charger.night_smart_charge.dt_util.now",
        return_value=datetime(2026, 3, 5, 0, 1, 0),
    ):
        assert night_charge._get_car_ready_for_today() is True


async def test_monitor_battery_fallbacks_to_grid_when_car_ready_on(hass, night_charge):
    """Home battery min in battery mode must transition to grid when car_ready is ON."""
    night_charge._night_charge_active = True
    night_charge._active_mode = NIGHT_CHARGE_MODE_BATTERY
    night_charge._session_state = "active"
    night_charge._last_completion_time = None
    night_charge._last_completion_date = None
    night_charge._battery_monitor_unsub = MagicMock()

    hass.states.async_set("number.test_evsc_home_battery_min_soc", "20")

    night_charge._get_car_ready_for_today = MagicMock(return_value=True)
    night_charge._should_stop_for_deadline = AsyncMock(return_value=(False, ""))
    night_charge.priority_balancer.get_home_current_soc = AsyncMock(return_value=20)
    night_charge.priority_balancer.is_ev_target_reached = AsyncMock(return_value=False)
    night_charge.priority_balancer.get_ev_current_soc = AsyncMock(return_value=40)
    night_charge.priority_balancer.get_ev_target_for_today = MagicMock(return_value=80)
    night_charge._get_pv_forecast = AsyncMock(return_value=5.0)

    async def _fake_grid_start(_pv_forecast):
        night_charge._night_charge_active = True
        night_charge._active_mode = NIGHT_CHARGE_MODE_GRID

    night_charge._start_grid_charge = AsyncMock(side_effect=_fake_grid_start)

    await night_charge._async_monitor_battery_charge(None)

    night_charge.charger_controller.stop_charger.assert_awaited_once()
    night_charge._start_grid_charge.assert_awaited_once_with(5.0)
    assert night_charge.is_active() is True
    assert night_charge.get_active_mode() == NIGHT_CHARGE_MODE_GRID
    assert night_charge._session_state == "active"
    assert night_charge._last_completion_time is None
    assert night_charge._last_completion_date is None


async def test_monitor_battery_stops_terminal_when_car_ready_off(hass, night_charge):
    """Home battery min in battery mode must complete day when car_ready is OFF."""
    night_charge._night_charge_active = True
    night_charge._active_mode = NIGHT_CHARGE_MODE_BATTERY
    night_charge._session_state = "active"
    night_charge._last_completion_time = None
    night_charge._last_completion_date = None

    hass.states.async_set("number.test_evsc_home_battery_min_soc", "20")

    night_charge._get_car_ready_for_today = MagicMock(return_value=False)
    night_charge._should_stop_for_deadline = AsyncMock(return_value=(False, ""))
    night_charge.priority_balancer.get_home_current_soc = AsyncMock(return_value=20)
    night_charge.priority_balancer.is_ev_target_reached = AsyncMock(return_value=False)
    night_charge.priority_balancer.get_ev_current_soc = AsyncMock(return_value=40)
    night_charge.priority_balancer.get_ev_target_for_today = MagicMock(return_value=80)

    with patch(
        "custom_components.ev_smart_charger.night_smart_charge.dt_util.now",
        return_value=datetime(2026, 3, 5, 0, 10, 0),
    ):
        await night_charge._async_monitor_battery_charge(None)

    night_charge.charger_controller.stop_charger.assert_awaited_once()
    assert night_charge.is_active() is False
    assert night_charge.get_active_mode() == NIGHT_CHARGE_MODE_IDLE
    assert night_charge._session_state == "completed_today"
    assert night_charge._last_completion_time is not None
    assert night_charge._last_completion_date is not None


async def test_monitor_battery_stops_terminal_on_persistent_grid_import_when_car_ready_off(
    hass, night_charge
):
    """Persistent grid import in battery mode must stop the session when car_ready is OFF."""
    night_charge._night_charge_active = True
    night_charge._active_mode = NIGHT_CHARGE_MODE_BATTERY
    night_charge._session_state = "active"
    night_charge._last_completion_time = None
    night_charge._last_completion_date = None
    # Must be relative to the PATCHED dt_util.now below (2026-03-07 02:00), not
    # the real clock — should_reduce() computes elapsed against dt_util.now(),
    # so a wall-clock trigger here yields a huge negative elapsed and never fires.
    night_charge._grid_import_trigger_time = datetime(2026, 3, 7, 2, 0, 0) - timedelta(seconds=60)

    hass.states.async_set("sensor.grid_import", "120")
    hass.states.async_set("number.test_evsc_grid_import_threshold", "50")
    hass.states.async_set("number.test_evsc_grid_import_delay", "30")
    hass.states.async_set("number.test_evsc_home_battery_min_soc", "20")

    night_charge._get_car_ready_for_today = MagicMock(return_value=False)
    night_charge._should_stop_for_deadline = AsyncMock(return_value=(False, ""))
    night_charge.priority_balancer.get_home_current_soc = AsyncMock(return_value=40)
    night_charge.priority_balancer.is_ev_target_reached = AsyncMock(return_value=False)
    night_charge.priority_balancer.get_ev_current_soc = AsyncMock(return_value=40)
    night_charge.priority_balancer.get_ev_target_for_today = MagicMock(return_value=80)
    night_charge.charger_controller.get_current_amperage = AsyncMock(return_value=10)
    night_charge.charger_controller.adjust_for_grid_import = AsyncMock()

    with patch(
        "custom_components.ev_smart_charger.night_smart_charge.dt_util.now",
        return_value=datetime(2026, 3, 7, 2, 0, 0),
    ):
        await night_charge._async_monitor_battery_charge(None)

    night_charge.charger_controller.stop_charger.assert_awaited_once()
    night_charge.charger_controller.adjust_for_grid_import.assert_not_awaited()
    assert night_charge.is_active() is False
    assert night_charge.get_active_mode() == NIGHT_CHARGE_MODE_IDLE
    assert night_charge._session_state == "completed_today"
    assert night_charge._last_completion_time is not None
    assert night_charge._last_completion_date is not None


async def test_complete_night_charge_terminal_vs_non_terminal_semantics(hass, night_charge):
    """completed_today must be set only for terminal completions."""
    night_charge._night_charge_active = True
    night_charge._active_mode = NIGHT_CHARGE_MODE_GRID
    night_charge._session_state = "active"

    with patch(
        "custom_components.ev_smart_charger.night_smart_charge.dt_util.now",
        return_value=datetime(2026, 3, 5, 0, 30, 0),
    ):
        await night_charge._complete_night_charge(STOP_REASON_EV_TARGET, terminal=True)

    assert night_charge._session_state == "completed_today"
    assert night_charge._last_completion_time is not None
    assert night_charge._last_completion_date is not None

    night_charge._night_charge_active = True
    night_charge._active_mode = NIGHT_CHARGE_MODE_GRID
    night_charge._session_state = "active"

    await night_charge._complete_night_charge(STOP_REASON_BOOST_PREEMPTED, terminal=False)

    assert night_charge._session_state == "ready"
    assert night_charge._last_completion_time is None
    assert night_charge._last_completion_date is None


async def test_handover_from_solar_surplus_accepts_and_activates(hass, night_charge):
    """Structured handover should activate Night Smart Charge when validation passes."""
    hass.states.async_set("switch.test_evsc_night_smart_charge_enabled", "on")
    hass.states.async_set("sensor.charger_status", "Charging")

    night_charge._session_state = "ready"
    night_charge._activation_date = None
    night_charge._is_in_active_window_for_handover = MagicMock(return_value=(True, "ok"))
    night_charge.priority_balancer.is_ev_target_reached = AsyncMock(return_value=False)

    async def _fake_evaluate():
        night_charge._night_charge_active = True
        night_charge._active_mode = NIGHT_CHARGE_MODE_GRID

    night_charge._evaluate_and_charge = AsyncMock(side_effect=_fake_evaluate)

    result = await night_charge.async_try_handover_from_solar_surplus("sunset_transition")

    assert result is True
    night_charge._evaluate_and_charge.assert_awaited_once()
    assert night_charge.is_active() is True
    assert night_charge.get_active_mode() == NIGHT_CHARGE_MODE_GRID
    assert night_charge._session_state == "active"
    assert night_charge._activation_date is not None


async def test_handover_from_solar_surplus_rejects_without_side_effect_when_target_reached(hass, night_charge):
    """Handover must reject cleanly when EV target is already reached."""
    hass.states.async_set("switch.test_evsc_night_smart_charge_enabled", "on")
    hass.states.async_set("sensor.charger_status", "Charging")

    night_charge._night_charge_active = False
    night_charge._active_mode = NIGHT_CHARGE_MODE_IDLE
    night_charge._session_state = "ready"
    night_charge._activation_date = None
    night_charge._is_in_active_window_for_handover = MagicMock(return_value=(True, "ok"))
    night_charge.priority_balancer.is_ev_target_reached = AsyncMock(return_value=True)
    night_charge.priority_balancer.get_ev_current_soc = AsyncMock(return_value=60)
    night_charge.priority_balancer.get_ev_target_for_today = MagicMock(return_value=60)
    night_charge._evaluate_and_charge = AsyncMock()

    result = await night_charge.async_try_handover_from_solar_surplus("sunset_transition")

    assert result is False
    night_charge._evaluate_and_charge.assert_not_awaited()
    assert night_charge._night_charge_active is False
    assert night_charge.get_active_mode() == NIGHT_CHARGE_MODE_IDLE
    assert night_charge._session_state == "ready"
    assert night_charge._activation_date is None


async def test_battery_monitor_stands_down_when_coordinator_ownership_is_lost(hass, night_charge):
    """Night Smart Charge must stop its monitor loop and reset state after preemption."""
    night_charge._coordinator = MagicMock()
    night_charge._coordinator.is_automation_active.return_value = False
    night_charge._night_charge_active = True
    night_charge._active_mode = NIGHT_CHARGE_MODE_BATTERY
    unsub = MagicMock()
    night_charge._battery_monitor_unsub = unsub

    await night_charge._async_monitor_battery_charge(None)

    unsub.assert_called_once()
    assert night_charge.is_active() is False
    assert night_charge.get_active_mode() == NIGHT_CHARGE_MODE_IDLE
    # Control loss routes through _handle_control_loss, which sets
    # "completed_today" (not "ready") to block same-day re-activation and the
    # restart loop fixed in v1.5.11.
    assert night_charge._session_state == "completed_today"


# ============================================================================
# v2.2.0 — grid-monitor Check 2: measured-power drawing-now stop
# ============================================================================


async def _prime_grid_monitor(hass, night_charge, *, status, measured):
    """Arrange the grid monitor so execution reaches Check 2.

    measured=None simulates 'no charging-power sensor mapped'.
    """
    night_charge._active_mode = NIGHT_CHARGE_MODE_GRID
    night_charge.is_active = MagicMock(return_value=True)
    night_charge._boost_charge = None
    night_charge._ensure_control = AsyncMock(return_value=True)
    night_charge._should_stop_for_deadline = AsyncMock(return_value=(False, ""))
    night_charge._complete_night_charge = AsyncMock()
    night_charge.priority_balancer.is_ev_target_reached = AsyncMock(return_value=False)
    night_charge.priority_balancer.get_ev_current_soc = AsyncMock(return_value=50)
    night_charge.priority_balancer.get_ev_target_for_today = MagicMock(return_value=80)

    if status is None:
        night_charge._charger_status = None
    else:
        night_charge._charger_status = "sensor.charger_status"
        hass.states.async_set("sensor.charger_status", status)

    power_model = MagicMock()
    power_model.read_charging_power = MagicMock(return_value=measured)
    night_charge._runtime_data.power_model = power_model


async def test_grid_monitor_blind_spot_stops_after_sustained_low_draw(hass, night_charge):
    """status='charger_charging' but measured 0 W sustained → terminal stop."""
    await _prime_grid_monitor(
        hass, night_charge, status=CHARGER_STATUS_CHARGING, measured=0.0
    )
    # Pretend the low-draw clock started well past the grace window.
    night_charge._grid_drawing_low_since = dt_util.now() - timedelta(seconds=30)

    await night_charge._async_monitor_grid_charge(None)

    night_charge._complete_night_charge.assert_awaited_once()


async def test_grid_monitor_blind_spot_waits_within_debounce(hass, night_charge):
    """First low-draw tick only arms the debounce; no stop yet."""
    await _prime_grid_monitor(
        hass, night_charge, status=CHARGER_STATUS_CHARGING, measured=0.0
    )
    night_charge._grid_drawing_low_since = None  # fresh

    await night_charge._async_monitor_grid_charge(None)

    night_charge._complete_night_charge.assert_not_awaited()
    assert night_charge._grid_drawing_low_since is not None


async def test_grid_monitor_keeps_charging_when_drawing(hass, night_charge):
    """status charging + real draw → never stops, clock stays clear."""
    await _prime_grid_monitor(
        hass,
        night_charge,
        status=CHARGER_STATUS_CHARGING,
        measured=CHARGING_POWER_DRAWING_FLOOR_W + 3000,
    )
    night_charge._grid_drawing_low_since = dt_util.now() - timedelta(seconds=30)

    await night_charge._async_monitor_grid_charge(None)

    night_charge._complete_night_charge.assert_not_awaited()
    assert night_charge._grid_drawing_low_since is None


async def test_grid_monitor_lifecycle_stop_survives_noisy_power(hass, night_charge):
    """status='charger_free' with a noisy >floor reading → immediate lifecycle
    stop (the advisor's bypass case must NOT regress)."""
    await _prime_grid_monitor(
        hass,
        night_charge,
        status=CHARGER_STATUS_FREE,
        measured=CHARGING_POWER_DRAWING_FLOOR_W + 500,
    )

    await night_charge._async_monitor_grid_charge(None)

    night_charge._complete_night_charge.assert_awaited_once()


async def test_grid_monitor_no_power_sensor_uses_legacy_status(hass, night_charge):
    """No power sensor → legacy status check, which stops on 'charger_wait'."""
    await _prime_grid_monitor(
        hass, night_charge, status=CHARGER_STATUS_WAIT, measured=None
    )

    await night_charge._async_monitor_grid_charge(None)

    night_charge._complete_night_charge.assert_awaited_once()


async def test_grid_monitor_startup_ramp_grace_suppresses_stop(hass, night_charge):
    """A freshly-started session whose EV is still ramping (0 W) must NOT be
    killed during the startup grace, even with a stale low-draw clock."""
    await _prime_grid_monitor(
        hass, night_charge, status=CHARGER_STATUS_CHARGING, measured=0.0
    )
    night_charge._grid_session_start = dt_util.now()  # just started → in grace
    night_charge._grid_drawing_low_since = dt_util.now() - timedelta(seconds=60)

    await night_charge._async_monitor_grid_charge(None)

    night_charge._complete_night_charge.assert_not_awaited()
    # the clock is reset while in the startup window
    assert night_charge._grid_drawing_low_since is None


async def test_grid_monitor_clears_stale_clock_on_sensor_unavailable(hass, night_charge):
    """When the power sensor goes unavailable (measured None), the low-draw clock
    is cleared so it can't fire a premature stop the instant the sensor recovers."""
    await _prime_grid_monitor(
        hass, night_charge, status=CHARGER_STATUS_CHARGING, measured=None
    )
    night_charge._grid_drawing_low_since = dt_util.now() - timedelta(seconds=60)

    await night_charge._async_monitor_grid_charge(None)

    night_charge._complete_night_charge.assert_not_awaited()
    assert night_charge._grid_drawing_low_since is None


# ============================================================================
# v2.4.0 (issue #33) — grid-mode home-battery masking protection (Check 1.5)
# ============================================================================


async def _prime_grid_masking(
    hass, night_charge, *, discharge, grid_import, home_soc
):
    """Arrange the grid monitor so execution reaches Check 1.5.

    Check 2 is made to pass (status charging + real draw) so any non-stop
    outcome is attributable to the masking check alone. ``discharge=None``
    simulates 'no battery-power sensor mapped'.
    """
    # Make Check 2 a no-op (status charging, drawing well above the floor).
    await _prime_grid_monitor(
        hass,
        night_charge,
        status=CHARGER_STATUS_CHARGING,
        measured=CHARGING_POWER_DRAWING_FLOOR_W + 3000,
    )
    night_charge._grid_session_start = dt_util.now() - timedelta(seconds=300)

    # Check 1.5 reads from self._power_model (distinct from the Check-2 model).
    masking_model = MagicMock()
    masking_model.read_battery_discharge = MagicMock(return_value=discharge)
    masking_model.read_grid_import = MagicMock(return_value=grid_import)
    night_charge._power_model = masking_model

    night_charge.priority_balancer.get_home_current_soc = AsyncMock(
        return_value=home_soc
    )
    # Helper entities (min=20, threshold=50, delay=30) come from the fixture.


async def test_grid_masking_stops_when_sustained(hass, night_charge):
    """Battery draining (grid ~0) with SOC at/below floor, sustained → stop."""
    await _prime_grid_masking(
        hass, night_charge, discharge=3500, grid_import=0, home_soc=15
    )
    # Pre-arm the debounce past the 30 s sustain window.
    night_charge._grid_battery_masking_tracker._stable_since = (
        dt_util.now() - timedelta(seconds=35)
    )

    await night_charge._async_monitor_grid_charge(None)

    night_charge._complete_night_charge.assert_awaited_once()
    assert (
        night_charge._complete_night_charge.await_args.args[0]
        == STOP_REASON_HOME_BATTERY_MIN
    )
    assert night_charge._complete_night_charge.await_args.kwargs["terminal"] is True


async def test_grid_masking_waits_within_debounce(hass, night_charge):
    """First masking tick only arms the debounce; no stop yet."""
    await _prime_grid_masking(
        hass, night_charge, discharge=3500, grid_import=0, home_soc=15
    )
    night_charge._grid_battery_masking_tracker.reset()  # fresh

    await night_charge._async_monitor_grid_charge(None)

    night_charge._complete_night_charge.assert_not_awaited()
    assert night_charge._grid_battery_masking_tracker.get_elapsed() >= 0
    assert night_charge._grid_battery_masking_tracker._stable_since is not None


async def test_grid_masking_no_battery_sensor_is_noop(hass, night_charge):
    """No battery-power sensor (read_battery_discharge None) → no stop, byte-for-byte."""
    await _prime_grid_masking(
        hass, night_charge, discharge=None, grid_import=0, home_soc=15
    )
    night_charge._grid_battery_masking_tracker._stable_since = (
        dt_util.now() - timedelta(seconds=120)
    )

    await night_charge._async_monitor_grid_charge(None)

    night_charge._complete_night_charge.assert_not_awaited()
    assert night_charge._grid_battery_masking_tracker._stable_since is None


async def test_grid_masking_no_stop_when_grid_high(hass, night_charge):
    """Battery discharging but grid_import >= threshold → EV genuinely on grid → no stop."""
    await _prime_grid_masking(
        hass, night_charge, discharge=3500, grid_import=100, home_soc=15
    )
    night_charge._grid_battery_masking_tracker._stable_since = (
        dt_util.now() - timedelta(seconds=120)
    )

    await night_charge._async_monitor_grid_charge(None)

    night_charge._complete_night_charge.assert_not_awaited()
    assert night_charge._grid_battery_masking_tracker._stable_since is None


async def test_grid_masking_no_stop_when_soc_above_min(hass, night_charge):
    """SOC above the floor → no stop even with high discharge and low grid."""
    await _prime_grid_masking(
        hass, night_charge, discharge=3500, grid_import=0, home_soc=50
    )
    night_charge._grid_battery_masking_tracker._stable_since = (
        dt_util.now() - timedelta(seconds=120)
    )

    await night_charge._async_monitor_grid_charge(None)

    night_charge._complete_night_charge.assert_not_awaited()
    assert night_charge._grid_battery_masking_tracker._stable_since is None


async def test_grid_masking_resets_when_condition_clears(hass, night_charge):
    """A previously-armed debounce is reset when the condition stops holding."""
    await _prime_grid_masking(
        hass, night_charge, discharge=3500, grid_import=200, home_soc=15
    )
    night_charge._grid_battery_masking_tracker._stable_since = (
        dt_util.now() - timedelta(seconds=20)
    )

    await night_charge._async_monitor_grid_charge(None)

    night_charge._complete_night_charge.assert_not_awaited()
    assert night_charge._grid_battery_masking_tracker._stable_since is None


# ============================================================================
# v2.3.0 (issue #32) - PV-production handoff stop condition (car_ready=OFF)
# ============================================================================

def _set_car_ready_all(hass, value: str) -> None:
    """Force every car_ready day switch to the given state (weekday-agnostic)."""
    for day in [
        "monday", "tuesday", "wednesday", "thursday",
        "friday", "saturday", "sunday",
    ]:
        hass.states.async_set(f"input_boolean.test_evsc_car_ready_{day}", value)


async def test_pv_handoff_stops_when_sustained(hass, night_charge):
    """car_ready=OFF + threshold>0 + PV sustained over threshold → stop & hand off."""
    _set_car_ready_all(hass, "off")
    hass.states.async_set("number.test_evsc_night_pv_handoff_threshold", "200")
    hass.states.async_set("sensor.fv_production", "3000")

    now = dt_util.now()
    night_charge._night_session_start = now.replace(hour=1, minute=0, second=0, microsecond=0)
    current = now.replace(hour=2, minute=0, second=0, microsecond=0)  # before 08:00 cap

    # Simulate PV already sustained for > 5 minutes.
    night_charge._pv_handoff_tracker.reset()
    night_charge._pv_handoff_tracker._stable_since = now - timedelta(seconds=301)

    should_stop, reason = await night_charge._should_stop_for_deadline(current)

    assert should_stop is True
    assert "handing off" in reason.lower()


async def test_pv_handoff_waits_for_debounce(hass, night_charge):
    """PV above threshold but not yet sustained → keep charging."""
    _set_car_ready_all(hass, "off")
    hass.states.async_set("number.test_evsc_night_pv_handoff_threshold", "200")
    hass.states.async_set("sensor.fv_production", "3000")

    now = dt_util.now()
    night_charge._night_session_start = now.replace(hour=1, minute=0, second=0, microsecond=0)
    current = now.replace(hour=2, minute=0, second=0, microsecond=0)

    night_charge._pv_handoff_tracker.reset()  # fresh: just crossed threshold

    should_stop, reason = await night_charge._should_stop_for_deadline(current)

    assert should_stop is False


async def test_pv_handoff_below_threshold_continues_past_sunrise(hass, night_charge):
    """car_ready=OFF + threshold>0 + PV below threshold past sunrise → keep charging."""
    _set_car_ready_all(hass, "off")
    hass.states.async_set("number.test_evsc_night_pv_handoff_threshold", "200")
    hass.states.async_set("sensor.fv_production", "150")  # below threshold

    now = dt_util.now()
    night_charge._night_session_start = now.replace(hour=1, minute=0, second=0, microsecond=0)
    current = now.replace(hour=6, minute=0, second=0, microsecond=0)  # past sunrise, before cap

    # Sunrise already passed - legacy behavior would stop here; PV path must not.
    night_charge._astral_service.get_sunrise = MagicMock(
        return_value=now.replace(hour=2, minute=0, second=0, microsecond=0)
    )
    # Seed a stale tracker to prove sub-threshold resets it.
    night_charge._pv_handoff_tracker._stable_since = now - timedelta(seconds=301)

    should_stop, reason = await night_charge._should_stop_for_deadline(current)

    assert should_stop is False
    assert night_charge._pv_handoff_tracker._stable_since is None  # reset on sub-threshold


async def test_pv_handoff_hard_cap(hass, night_charge):
    """car_ready=OFF + threshold>0 + overcast (PV=0) → stop at car_ready_time hard-cap."""
    _set_car_ready_all(hass, "off")
    hass.states.async_set("number.test_evsc_night_pv_handoff_threshold", "200")
    hass.states.async_set("sensor.fv_production", "0")
    hass.states.async_set("input_datetime.test_evsc_car_ready_time", "08:00:00")

    now = dt_util.now()
    night_charge._night_session_start = now.replace(hour=1, minute=0, second=0, microsecond=0)
    current = now.replace(hour=9, minute=0, second=0, microsecond=0)  # past 08:00 cap

    should_stop, reason = await night_charge._should_stop_for_deadline(current)

    assert should_stop is True
    assert "hard-cap" in reason.lower()


async def test_pv_handoff_hardcap_midnight_safe(hass, night_charge):
    """Evening-started session (23:15) must NOT cap immediately (regression: BLOCKER #1)."""
    _set_car_ready_all(hass, "off")
    hass.states.async_set("number.test_evsc_night_pv_handoff_threshold", "200")
    hass.states.async_set("sensor.fv_production", "0")
    hass.states.async_set("input_datetime.test_evsc_car_ready_time", "08:00:00")

    now = dt_util.now()
    night_charge._night_session_start = now.replace(hour=23, minute=15, second=0, microsecond=0)
    current = now.replace(hour=23, minute=30, second=0, microsecond=0)

    should_stop, reason = await night_charge._should_stop_for_deadline(current)

    assert should_stop is False  # cap is tomorrow 08:00, not reached


async def test_pv_handoff_disabled_uses_sunrise(hass, night_charge):
    """threshold=0 (default) → legacy astronomical-sunrise stop unchanged."""
    _set_car_ready_all(hass, "off")
    hass.states.async_set("number.test_evsc_night_pv_handoff_threshold", "0")
    hass.states.async_set("sensor.fv_production", "3000")  # irrelevant when disabled

    now = dt_util.now()
    current = now.replace(hour=6, minute=0, second=0, microsecond=0)
    night_charge._astral_service.get_sunrise = MagicMock(
        return_value=now.replace(hour=5, minute=0, second=0, microsecond=0)
    )

    should_stop, reason = await night_charge._should_stop_for_deadline(current)

    assert should_stop is True
    assert "sunrise" in reason.lower()


async def test_pv_handoff_ignored_when_car_ready_on(hass, night_charge):
    """car_ready=ON → ON branch (deadline/target) unchanged; PV handoff never runs."""
    _set_car_ready_all(hass, "on")
    hass.states.async_set("number.test_evsc_night_pv_handoff_threshold", "200")
    hass.states.async_set("sensor.fv_production", "3000")
    hass.states.async_set("input_datetime.test_evsc_car_ready_time", "08:00:00")

    night_charge.priority_balancer.is_ev_target_reached = AsyncMock(return_value=False)

    now = dt_util.now()
    current = now.replace(hour=3, minute=0, second=0, microsecond=0)  # before deadline

    should_stop, reason = await night_charge._should_stop_for_deadline(current)

    assert should_stop is False
    assert "handing off" not in reason.lower()


async def test_disabled_switch_does_not_mutate_session_state(hass, night_charge):
    """issue #45: with the enable switch OFF, the enabled check must short-circuit
    BEFORE _is_in_active_window() (which mutates _session_state to 'active').

    Regression for the phantom 'Already active (hysteresis)' + 'disabled, skipping'
    loop on never-enabled installs.
    """
    hass.states.async_set("switch.test_evsc_night_smart_charge_enabled", "off")
    night_charge._session_state = "ready"

    # Spy: the window check must NOT be reached while disabled.
    night_charge._is_in_active_window = AsyncMock(return_value=True)

    await night_charge._async_periodic_check(dt_util.now())

    night_charge._is_in_active_window.assert_not_called()
    assert night_charge._session_state == "ready"


# ============================================================================
# v2.9.0 — grid-monitor lifecycle check: tolerant blocklist (non-Tuya wallboxes)
# ============================================================================


async def test_grid_monitor_brand_charging_status_is_not_a_lifecycle_stop(
    hass, night_charge
):
    """A brand-specific status like 'charging' (non-Tuya vocabulary) with real
    measured draw must NOT end the session. Regression for the 2026-07-19
    incident: the old (CHARGING, WAIT) allowlist terminally killed a grid
    session 15 s after the battery→grid fallback because the wallbox reported
    'charging' instead of 'charger_charging'."""
    await _prime_grid_monitor(
        hass,
        night_charge,
        status="charging",
        measured=CHARGING_POWER_DRAWING_FLOOR_W + 4000,
    )

    await night_charge._async_monitor_grid_charge(None)

    night_charge._complete_night_charge.assert_not_awaited()
    assert night_charge._grid_drawing_low_since is None


async def test_grid_monitor_brand_status_still_protected_by_blind_spot(
    hass, night_charge
):
    """With a brand status string, protection moves to the measured-power
    blind-spot check: sustained 0 W (outside the startup grace) still stops."""
    await _prime_grid_monitor(hass, night_charge, status="charging", measured=0.0)
    night_charge._grid_session_start = dt_util.now() - timedelta(seconds=300)
    night_charge._grid_drawing_low_since = dt_util.now() - timedelta(seconds=30)

    await night_charge._async_monitor_grid_charge(None)

    night_charge._complete_night_charge.assert_awaited_once()


async def test_grid_monitor_lifecycle_stop_on_end_status(hass, night_charge):
    """'charger_end' is an explicit lifecycle stop even with noisy power."""
    await _prime_grid_monitor(
        hass,
        night_charge,
        status="charger_end",
        measured=CHARGING_POWER_DRAWING_FLOOR_W + 500,
    )

    await night_charge._async_monitor_grid_charge(None)

    night_charge._complete_night_charge.assert_awaited_once()


async def test_grid_monitor_legacy_brand_charging_keeps_running(hass, night_charge):
    """No power sensor + brand status 'charging' → session keeps running
    (the old `!= charger_charging` check would have killed it)."""
    await _prime_grid_monitor(hass, night_charge, status="charging", measured=None)

    await night_charge._async_monitor_grid_charge(None)

    night_charge._complete_night_charge.assert_not_awaited()


async def test_grid_monitor_legacy_unavailable_status_stops(hass, night_charge):
    """No power sensor + unavailable status → fail-safe stop is preserved
    (status is the only signal on the legacy path)."""
    await _prime_grid_monitor(hass, night_charge, status="unavailable", measured=None)

    await night_charge._async_monitor_grid_charge(None)

    night_charge._complete_night_charge.assert_awaited_once()


# ============================================================================
# v2.9.0 — re-arm completed session on user intent change (target / car_ready)
# ============================================================================


def _today_keys():
    now = dt_util.now()
    idx = now.weekday()
    name = [
        "monday", "tuesday", "wednesday", "thursday",
        "friday", "saturday", "sunday",
    ][idx]
    return idx, name


def _intent_event(entity_id, old, new):
    event = MagicMock()
    event.data = {
        "entity_id": entity_id,
        "old_state": MagicMock(state=old),
        "new_state": MagicMock(state=new),
    }
    return event


def _prime_completed_session(night_charge, *, ev_soc=62.0, ev_target=80):
    idx, name = _today_keys()
    night_charge._session_state = "completed_today"
    night_charge._last_completion_time = dt_util.now()
    night_charge._last_completion_date = dt_util.now().date()
    night_charge.is_active = MagicMock(return_value=False)
    night_charge.priority_balancer.get_ev_current_soc = AsyncMock(return_value=ev_soc)
    night_charge.priority_balancer.get_ev_target_for_today = MagicMock(
        return_value=ev_target
    )
    night_charge.priority_balancer._ev_min_soc_entities = {
        name: "number.ev_target_today"
    }
    return idx, name


async def test_intent_rearm_on_target_raise(hass, night_charge):
    """Raising TODAY's target above the current SOC after a terminal stop must
    re-arm the state machine (completed_today → ready, cooldown cleared)."""
    _prime_completed_session(night_charge, ev_soc=62.0, ev_target=80)

    await night_charge._async_user_intent_changed(
        _intent_event("number.ev_target_today", "50", "80")
    )

    assert night_charge._session_state == "ready"
    assert night_charge._last_completion_time is None
    assert night_charge._last_completion_date is None


async def test_intent_no_rearm_when_target_already_met(hass, night_charge):
    """Target change with EV SOC already at/above the new target → no re-arm."""
    _prime_completed_session(night_charge, ev_soc=85.0, ev_target=80)

    await night_charge._async_user_intent_changed(
        _intent_event("number.ev_target_today", "50", "80")
    )

    assert night_charge._session_state == "completed_today"
    assert night_charge._last_completion_time is not None


async def test_intent_rearm_on_car_ready_on(hass, night_charge):
    """Turning TODAY's car_ready ON with the EV below target → re-arm."""
    idx, _ = _prime_completed_session(night_charge, ev_soc=62.0, ev_target=80)
    car_ready_entity = night_charge._car_ready_entities[idx]

    await night_charge._async_user_intent_changed(
        _intent_event(car_ready_entity, "off", "on")
    )

    assert night_charge._session_state == "ready"


async def test_intent_no_rearm_on_car_ready_off(hass, night_charge):
    """Turning car_ready OFF lowers urgency — never resurrects a session."""
    idx, _ = _prime_completed_session(night_charge, ev_soc=62.0, ev_target=80)
    car_ready_entity = night_charge._car_ready_entities[idx]

    await night_charge._async_user_intent_changed(
        _intent_event(car_ready_entity, "on", "off")
    )

    assert night_charge._session_state == "completed_today"


async def test_intent_ignores_other_days_entities(hass, night_charge):
    """A change on ANOTHER day's target must not resurrect today's session."""
    _prime_completed_session(night_charge, ev_soc=62.0, ev_target=80)

    await night_charge._async_user_intent_changed(
        _intent_event("number.ev_target_tomorrow", "50", "90")
    )

    assert night_charge._session_state == "completed_today"


async def test_intent_noop_while_session_active(hass, night_charge):
    """An active session already live-reads targets — no state mutation."""
    _prime_completed_session(night_charge, ev_soc=62.0, ev_target=80)
    night_charge._session_state = "active"

    await night_charge._async_user_intent_changed(
        _intent_event("number.ev_target_today", "50", "80")
    )

    assert night_charge._session_state == "active"


async def test_intent_ignores_availability_churn(hass, night_charge):
    """unknown/unavailable transitions (restore churn) are not user intent."""
    _prime_completed_session(night_charge, ev_soc=62.0, ev_target=80)

    await night_charge._async_user_intent_changed(
        _intent_event("number.ev_target_today", "unavailable", "80")
    )

    assert night_charge._session_state == "completed_today"


# ============================================================================
# v2.9.1 — brand-vocabulary status classifiers (OCPP 'available', 'charged', …)
# ============================================================================

from custom_components.ev_smart_charger.power_model import (
    is_charge_complete_status,
    is_disconnected_status,
)


def test_disconnected_status_classifier():
    """Tolerant, case-insensitive; unknown strings default to connected."""
    assert is_disconnected_status("charger_free") is True
    assert is_disconnected_status("available") is True  # OCPP: not occupied
    assert is_disconnected_status("Available") is True
    assert is_disconnected_status(" unplugged ") is True
    assert is_disconnected_status("charging") is False
    assert is_disconnected_status("charged") is False
    assert is_disconnected_status("SuspendedEV") is False  # OCPP: plugged
    assert is_disconnected_status(None) is False
    assert is_disconnected_status("") is False


def test_charge_complete_status_classifier():
    assert is_charge_complete_status("charger_end") is True
    assert is_charge_complete_status("charged") is True
    assert is_charge_complete_status("Finishing") is True  # OCPP wrap-up
    assert is_charge_complete_status("charging") is False
    assert is_charge_complete_status("available") is False
    assert is_charge_complete_status(None) is False


async def test_grid_monitor_lifecycle_stop_on_brand_disconnected(hass, night_charge):
    """'available' (OCPP = unplugged) mid-session → immediate lifecycle stop,
    even with a noisy >floor power reading."""
    await _prime_grid_monitor(
        hass,
        night_charge,
        status="available",
        measured=CHARGING_POWER_DRAWING_FLOOR_W + 500,
    )

    await night_charge._async_monitor_grid_charge(None)

    night_charge._complete_night_charge.assert_awaited_once()


async def test_grid_monitor_lifecycle_stop_on_brand_charged(hass, night_charge):
    """'charged' (brand synonym of charger_end) → immediate lifecycle stop."""
    await _prime_grid_monitor(
        hass,
        night_charge,
        status="charged",
        measured=CHARGING_POWER_DRAWING_FLOOR_W + 500,
    )

    await night_charge._async_monitor_grid_charge(None)

    night_charge._complete_night_charge.assert_awaited_once()


async def test_grid_monitor_legacy_brand_disconnected_stops(hass, night_charge):
    """Legacy path (no power sensor): brand 'available' → lifecycle stop."""
    await _prime_grid_monitor(hass, night_charge, status="available", measured=None)

    await night_charge._async_monitor_grid_charge(None)

    night_charge._complete_night_charge.assert_awaited_once()


async def test_late_arrival_fires_on_brand_disconnected_transition(hass, night_charge):
    """Plug-in detection must fire on 'available' → 'charging', not only on the
    Tuya 'charger_free' transition (the 2026-07-19 wallbox vocabulary)."""
    night_charge._boost_charge = None
    night_charge._is_in_active_window = AsyncMock(return_value=True)
    night_charge.is_enabled = MagicMock(return_value=True)
    night_charge._evaluate_and_charge = AsyncMock()

    event = MagicMock()
    event.data = {
        "old_state": MagicMock(state="available"),
        "new_state": MagicMock(state="charging"),
    }
    await night_charge._async_charger_status_changed(event)

    night_charge._evaluate_and_charge.assert_awaited_once()


async def test_late_arrival_ignores_connected_to_connected_transition(
    hass, night_charge
):
    """'charging' → 'charged' is not a plug-in event."""
    night_charge._boost_charge = None
    night_charge._evaluate_and_charge = AsyncMock()

    event = MagicMock()
    event.data = {
        "old_state": MagicMock(state="charging"),
        "new_state": MagicMock(state="charged"),
    }
    await night_charge._async_charger_status_changed(event)

    night_charge._evaluate_and_charge.assert_not_awaited()

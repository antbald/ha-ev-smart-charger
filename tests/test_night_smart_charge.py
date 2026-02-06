"""Tests for Night Smart Charge automation - WORKING VERSION."""
import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from custom_components.ev_smart_charger.night_smart_charge import NightSmartCharge
from custom_components.ev_smart_charger.const import (
    CONF_EV_CHARGER_STATUS,
    CONF_EV_CHARGER_SWITCH,
    CONF_EV_CHARGER_CURRENT,
    CONF_SOC_HOME,
    CONF_PV_FORECAST,
    CONF_NOTIFY_SERVICES,
    CHARGER_STATUS_FREE,
    NIGHT_CHARGE_MODE_BATTERY,
    NIGHT_CHARGE_MODE_GRID,
    NIGHT_CHARGE_MODE_IDLE,
)


@pytest.fixture
async def night_charge(hass, mock_priority_balancer, mock_charger_controller):
    """Create NightSmartCharge instance with mocked dependencies."""
    config = {
        CONF_EV_CHARGER_STATUS: "sensor.charger_status",
        CONF_EV_CHARGER_SWITCH: "switch.charger_switch",
        CONF_EV_CHARGER_CURRENT: "sensor.charger_current",
        CONF_SOC_HOME: "sensor.home_soc",
        CONF_PV_FORECAST: "sensor.pv_forecast",
        CONF_NOTIFY_SERVICES: [],
    }
    
    night_charge = NightSmartCharge(
        hass, "test_entry", config, mock_priority_balancer, mock_charger_controller
    )
    
    # Setup helper entities
    hass.states.async_set("switch.test_evsc_night_smart_charge_enabled", "on")
    hass.states.async_set("switch.charger_switch", "off")
    hass.states.async_set("sensor.charger_current", "0")
    hass.states.async_set("input_datetime.test_evsc_night_charge_time", "01:00:00")
    hass.states.async_set("input_datetime.test_evsc_car_ready_time", "08:00:00")
    hass.states.async_set("number.test_evsc_night_charge_amperage", "10")
    hass.states.async_set("number.test_evsc_min_solar_forecast_threshold", "10.0")
    hass.states.async_set("number.test_evsc_home_battery_min_soc", "20.0")
    
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

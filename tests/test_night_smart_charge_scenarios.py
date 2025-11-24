"""Tests for Night Smart Charge Scenarios."""
import asyncio
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from custom_components.ev_smart_charger.night_smart_charge import NightSmartCharge
from custom_components.ev_smart_charger.const import (
    CONF_EV_CHARGER_STATUS,
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
    hass.states.async_set("input_datetime.test_evsc_night_charge_time", "01:00:00")
    hass.states.async_set("input_datetime.test_evsc_car_ready_time", "08:00:00")
    hass.states.async_set("number.test_evsc_night_charge_amperage", "16")
    hass.states.async_set("number.test_evsc_min_solar_forecast_threshold", "20.0")
    hass.states.async_set("number.test_evsc_home_battery_min_soc", "20.0")
    
    # Setup critical sensors for Priority Balancer check
    hass.states.async_set("sensor.ev_soc", "50")
    hass.states.async_set("number.ev_target", "80")
    
    # Configure Priority Balancer mock attributes
    night_charge.priority_balancer._soc_car = "sensor.ev_soc"
    night_charge.priority_balancer._ev_min_soc_entities = {
        "monday": "number.ev_target",
        "tuesday": "number.ev_target",
        "wednesday": "number.ev_target",
        "thursday": "number.ev_target",
        "friday": "number.ev_target",
        "saturday": "number.ev_target",
        "sunday": "number.ev_target",
    }
    
    # Setup car ready entities for all days (default to True)
    days = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
    for day in days:
        hass.states.async_set(f"input_boolean.test_evsc_car_ready_{day}", "on")
    
    await night_charge.async_setup()
    return night_charge

# ============================================================================
# SCENARIO 1: Standard Grid Charge
# Forecast < Threshold, EV SOC < Target
# ============================================================================
async def test_scenario_1_grid_charge(hass, night_charge):
    """
    Scenario 1: Standard Grid Charge
    - Time: 01:00 (Scheduled time)
    - PV Forecast: 10.0 kWh (Below threshold 20.0)
    - EV SOC: 40% (Target 80%)
    - Home Battery: 50% (Above min 20%)
    - Expectation: Start Grid Charge
    """
    # Setup states
    hass.states.async_set("sensor.charger_status", "Charging")
    hass.states.async_set("sensor.pv_forecast", "10.0")
    hass.states.async_set("sensor.home_soc", "50")
    
    # Mock Priority Balancer
    night_charge.priority_balancer.get_ev_current_soc = AsyncMock(return_value=40)
    night_charge.priority_balancer.get_home_current_soc = AsyncMock(return_value=50)
    night_charge.priority_balancer.get_ev_target_for_today.return_value = 80
    night_charge.priority_balancer.is_ev_target_reached.return_value = False
    
    # Mock window check
    night_charge._is_in_active_window = AsyncMock(return_value=True)
    
    # Run evaluation
    with patch("custom_components.ev_smart_charger.night_smart_charge.dt_util.now", return_value=datetime(2023, 1, 1, 1, 0, 0)):
        await night_charge._evaluate_and_charge()
        
    # Verify
    assert night_charge.is_active() is True
    assert night_charge.get_active_mode() == NIGHT_CHARGE_MODE_GRID
    night_charge.charger_controller.start_charger.assert_called_with(16, "Night charge - Grid mode")

# ============================================================================
# SCENARIO 2: Standard Battery Charge
# Forecast > Threshold, EV SOC < Target, Home Battery > Min
# ============================================================================
async def test_scenario_2_battery_charge(hass, night_charge):
    """
    Scenario 2: Standard Battery Charge
    - Time: 01:00
    - PV Forecast: 30.0 kWh (Above threshold 20.0)
    - EV SOC: 40% (Target 80%)
    - Home Battery: 80% (Above min 20%)
    - Expectation: Start Battery Charge
    """
    # Setup states
    hass.states.async_set("sensor.charger_status", "Charging")
    hass.states.async_set("sensor.pv_forecast", "30.0")
    hass.states.async_set("sensor.home_soc", "80")
    
    # Mock Priority Balancer
    night_charge.priority_balancer.get_ev_current_soc = AsyncMock(return_value=40)
    night_charge.priority_balancer.get_home_current_soc = AsyncMock(return_value=80)
    night_charge.priority_balancer.get_ev_target_for_today.return_value = 80
    night_charge.priority_balancer.is_ev_target_reached.return_value = False
    
    # Mock window check
    night_charge._is_in_active_window = AsyncMock(return_value=True)
    
    # Run evaluation
    with patch("custom_components.ev_smart_charger.night_smart_charge.dt_util.now", return_value=datetime(2023, 1, 1, 1, 0, 0)):
        await night_charge._evaluate_and_charge()
        
    # Verify
    assert night_charge.is_active() is True
    assert night_charge.get_active_mode() == NIGHT_CHARGE_MODE_BATTERY
    night_charge.charger_controller.start_charger.assert_called_with(16, "Night charge - Battery mode")

# ============================================================================
# SCENARIO 3a: Battery Low Fallback (Car Needed)
# Forecast > Threshold, Home Battery < Min, Car Ready = ON
# ============================================================================
async def test_scenario_3a_battery_low_fallback(hass, night_charge):
    """
    Scenario 3a: Battery Low Fallback (Car Needed)
    - PV Forecast: 30.0 kWh (Good)
    - Home Battery: 10% (Below min 20%)
    - Car Ready Flag: ON
    - Expectation: Fallback to Grid Charge
    """
    # Setup states
    hass.states.async_set("sensor.charger_status", "Charging")
    hass.states.async_set("sensor.pv_forecast", "30.0")
    hass.states.async_set("sensor.home_soc", "10")
    
    # Mock Priority Balancer
    night_charge.priority_balancer.get_ev_current_soc = AsyncMock(return_value=40)
    night_charge.priority_balancer.get_home_current_soc = AsyncMock(return_value=10)
    night_charge.priority_balancer.get_ev_target_for_today.return_value = 80
    night_charge.priority_balancer.is_ev_target_reached.return_value = False
    
    # Mock car ready for today (Sunday=6)
    night_charge._get_car_ready_for_today = MagicMock(return_value=True)
    
    # Mock window check
    night_charge._is_in_active_window = AsyncMock(return_value=True)
    
    # Run evaluation
    with patch("custom_components.ev_smart_charger.night_smart_charge.dt_util.now", return_value=datetime(2023, 1, 1, 1, 0, 0)):
        await night_charge._evaluate_and_charge()
        
    # Verify
    assert night_charge.is_active() is True
    assert night_charge.get_active_mode() == NIGHT_CHARGE_MODE_GRID
    night_charge.charger_controller.start_charger.assert_called_with(16, "Night charge - Grid mode")

# ============================================================================
# SCENARIO 3b: Battery Low Skip (Car Not Needed)
# Forecast > Threshold, Home Battery < Min, Car Ready = OFF
# ============================================================================
async def test_scenario_3b_battery_low_skip(hass, night_charge):
    """
    Scenario 3b: Battery Low Skip (Car Not Needed)
    - PV Forecast: 30.0 kWh (Good)
    - Home Battery: 10% (Below min 20%)
    - Car Ready Flag: OFF
    - Expectation: Skip Charge (Wait for solar)
    """
    # Setup states
    hass.states.async_set("sensor.charger_status", "Charging")
    hass.states.async_set("sensor.pv_forecast", "30.0")
    hass.states.async_set("sensor.home_soc", "10")
    
    # Mock Priority Balancer
    night_charge.priority_balancer.get_ev_current_soc = AsyncMock(return_value=40)
    night_charge.priority_balancer.get_home_current_soc = AsyncMock(return_value=10)
    night_charge.priority_balancer.get_ev_target_for_today.return_value = 80
    night_charge.priority_balancer.is_ev_target_reached.return_value = False
    
    # Mock car ready for today
    night_charge._get_car_ready_for_today = MagicMock(return_value=False)
    
    # Mock window check
    night_charge._is_in_active_window = AsyncMock(return_value=True)
    
    # Run evaluation
    with patch("custom_components.ev_smart_charger.night_smart_charge.dt_util.now", return_value=datetime(2023, 1, 1, 1, 0, 0)):
        await night_charge._evaluate_and_charge()
        
    # Verify
    assert night_charge.is_active() is False
    night_charge.charger_controller.start_charger.assert_not_called()

# ============================================================================
# SCENARIO 4: EV Already Full
# EV SOC >= Target
# ============================================================================
async def test_scenario_4_ev_full(hass, night_charge):
    """
    Scenario 4: EV Already Full
    - EV SOC: 85% (Target 80%)
    - Expectation: No Action
    """
    # Setup states
    hass.states.async_set("sensor.charger_status", "Charging")
    hass.states.async_set("sensor.pv_forecast", "10.0")
    hass.states.async_set("sensor.home_soc", "50")
    
    # Mock Priority Balancer
    night_charge.priority_balancer.get_ev_current_soc = AsyncMock(return_value=85)
    night_charge.priority_balancer.get_home_current_soc = AsyncMock(return_value=50)
    night_charge.priority_balancer.get_ev_target_for_today.return_value = 80
    night_charge.priority_balancer.is_ev_target_reached.return_value = True
    
    # Mock window check
    night_charge._is_in_active_window = AsyncMock(return_value=True)
    
    # Run evaluation
    with patch("custom_components.ev_smart_charger.night_smart_charge.dt_util.now", return_value=datetime(2023, 1, 1, 1, 0, 0)):
        await night_charge._evaluate_and_charge()
        
    # Verify
    assert night_charge.is_active() is False
    night_charge.charger_controller.start_charger.assert_not_called()

# ============================================================================
# SCENARIO 5: Late Arrival
# Plug in at 02:00 AM (Inside window)
# ============================================================================
async def test_scenario_5_late_arrival(hass, night_charge):
    """
    Scenario 5: Late Arrival
    - Time: 02:00 AM
    - Event: Charger status changes from Free to Charging
    - Expectation: Immediate evaluation and start
    """
    # Setup states
    hass.states.async_set("sensor.charger_status", "Charging")
    hass.states.async_set("sensor.pv_forecast", "10.0")
    hass.states.async_set("sensor.home_soc", "50")
    
    # Mock Priority Balancer
    night_charge.priority_balancer.get_ev_current_soc = AsyncMock(return_value=40)
    night_charge.priority_balancer.get_home_current_soc = AsyncMock(return_value=50)
    night_charge.priority_balancer.get_ev_target_for_today.return_value = 80
    night_charge.priority_balancer.is_ev_target_reached.return_value = False
    
    # Mock window check
    night_charge._is_in_active_window = AsyncMock(return_value=True)
    
    # Simulate event
    from homeassistant.core import State
    event = MagicMock()
    event.data = {
        "old_state": State("sensor.charger_status", CHARGER_STATUS_FREE),
        "new_state": State("sensor.charger_status", "Charging")
    }
    
    # Run event handler
    with patch("custom_components.ev_smart_charger.night_smart_charge.dt_util.now", return_value=datetime(2023, 1, 1, 2, 0, 0)):
        await night_charge._async_charger_status_changed(event)
        
    # Verify
    assert night_charge.is_active() is True
    night_charge.charger_controller.start_charger.assert_called()

# ============================================================================
# SCENARIO 6: Race Condition Check
# Verify internal state is set BEFORE charger start
# ============================================================================
async def test_scenario_6_race_condition(hass, night_charge):
    """
    Scenario 6: Race Condition Check
    - Verify that self._night_charge_active is True BEFORE start_charger completes
    - This simulates the fix for the Smart Blocker race condition
    """
    # Setup states
    hass.states.async_set("sensor.charger_status", "Charging")
    hass.states.async_set("sensor.pv_forecast", "10.0")
    hass.states.async_set("sensor.home_soc", "50")
    
    # Mock Priority Balancer
    night_charge.priority_balancer.get_ev_current_soc = AsyncMock(return_value=40)
    night_charge.priority_balancer.get_home_current_soc = AsyncMock(return_value=50)
    night_charge.priority_balancer.get_ev_target_for_today.return_value = 80
    night_charge.priority_balancer.is_ev_target_reached.return_value = False
    
    # Mock window check
    night_charge._is_in_active_window = AsyncMock(return_value=True)
    
    # Custom mock for start_charger to check state during execution
    original_start_charger = night_charge.charger_controller.start_charger
    
    async def mock_start_charger_side_effect(*args, **kwargs):
        # CHECK: State must be active HERE, inside the start command
        assert night_charge.is_active() is True
        assert night_charge.get_active_mode() == NIGHT_CHARGE_MODE_GRID
        return True
        
    night_charge.charger_controller.start_charger = AsyncMock(side_effect=mock_start_charger_side_effect)
    
    # Run evaluation
    with patch("custom_components.ev_smart_charger.night_smart_charge.dt_util.now", return_value=datetime(2023, 1, 1, 1, 0, 0)):
        await night_charge._evaluate_and_charge()
        
    # Verify call happened
    night_charge.charger_controller.start_charger.assert_called()

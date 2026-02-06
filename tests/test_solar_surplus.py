"""Test SolarSurplusAutomation logic."""
import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from datetime import datetime
from custom_components.ev_smart_charger.solar_surplus import SolarSurplusAutomation
from custom_components.ev_smart_charger.const import (
    CONF_EV_CHARGER_STATUS,
    CONF_FV_PRODUCTION,
    CONF_HOME_CONSUMPTION,
    CONF_GRID_IMPORT,
    CONF_SOC_HOME,
    CHARGER_STATUS_CHARGING,
    CHARGER_STATUS_FREE,
    PRIORITY_EV,
    PRIORITY_HOME,
    PRIORITY_EV_FREE,
)

@pytest.fixture
def automation(hass, mock_charger_controller, mock_priority_balancer):
    """Create a SolarSurplusAutomation instance."""
    config = {
        CONF_EV_CHARGER_STATUS: "sensor.charger_status",
        CONF_FV_PRODUCTION: "sensor.solar",
        CONF_HOME_CONSUMPTION: "sensor.consumption",
        CONF_GRID_IMPORT: "sensor.grid",
        CONF_SOC_HOME: "sensor.home_soc",
    }
    
    # Mock dependencies
    with patch("custom_components.ev_smart_charger.solar_surplus.EntityRegistryService"), \
         patch("custom_components.ev_smart_charger.solar_surplus.AstralTimeService") as mock_astral:
        
        mock_astral.return_value.is_nighttime.return_value = False
        
        auto = SolarSurplusAutomation(
            hass, "test_entry", config, mock_priority_balancer, mock_charger_controller
        )
        
        # Mock helper entities discovery
        auto._charging_profile_entity = "select.profile"
        auto._check_interval_entity = "number.interval"
        auto._grid_import_threshold_entity = "number.grid_threshold"
        auto._grid_import_delay_entity = "number.grid_delay"
        auto._surplus_drop_delay_entity = "number.surplus_delay"
        auto._use_home_battery_entity = "switch.use_battery"
        auto._home_battery_min_soc_entity = "number.min_soc"
        auto._battery_support_amperage_entity = "number.battery_amps"
        auto._forza_ricarica_entity = "switch.force"
        
        return auto

async def test_calculate_target_amperage(hass, automation):
    """Test target amperage calculation with hysteresis."""
    # 230V * 6A = 1380W
    # 230V * 10A = 2300W
    
    # Case 1: Surplus sufficient to start (>= 6.5A)
    # 7A * 230V = 1610W
    target = automation._calculate_target_amperage(1610, current_amperage=0)
    assert target == 6  # Should start at min level (6A)
    
    # Case 2: Surplus in dead band (6A) - Not charging
    # 6A * 230V = 1380W
    target = automation._calculate_target_amperage(1380, current_amperage=0)
    assert target == 0  # Should wait for start threshold
    
    # Case 3: Surplus in dead band (6A) - Charging
    target = automation._calculate_target_amperage(1380, current_amperage=6)
    assert target == 6  # Should maintain current
    
    # Case 4: Surplus below stop threshold (5A)
    # 5A * 230V = 1150W
    target = automation._calculate_target_amperage(1150, current_amperage=6)
    assert target == 0  # Should stop

async def test_grid_import_protection(hass, automation):
    """Test grid import protection logic."""
    # Setup
    hass.states.async_set("number.grid_threshold", "50")
    hass.states.async_set("number.grid_delay", "30")
    
    # Initial high import - should start timer
    with patch("time.time", return_value=1000):
        await automation._handle_grid_import_protection(
            grid_import=100, grid_threshold=50, grid_import_delay=30, current_amps=16
        )
        assert automation._last_grid_import_high == 1000
        automation.charger_controller.set_amperage.assert_not_called()
    
    # Still high, delay not elapsed
    with patch("time.time", return_value=1020): # +20s
        await automation._handle_grid_import_protection(
            grid_import=100, grid_threshold=50, grid_import_delay=30, current_amps=16
        )
        automation.charger_controller.set_amperage.assert_not_called()
        
    # Delay elapsed - should reduce amperage
    with patch("time.time", return_value=1031): # +31s
        await automation._handle_grid_import_protection(
            grid_import=100, grid_threshold=50, grid_import_delay=30, current_amps=16
        )
        assert automation._last_grid_import_high is None
        automation.charger_controller.set_amperage.assert_called_with(13, "Grid import protection")

async def test_grid_import_protection_keeps_charger_off_when_already_off(hass, automation):
    """When import is high and charger is OFF, protection must not start charging."""
    # Initial high import - start timer
    with patch("time.time", return_value=2000):
        await automation._handle_grid_import_protection(
            grid_import=100, grid_threshold=50, grid_import_delay=30, current_amps=0
        )
        assert automation._last_grid_import_high == 2000

    # Delay elapsed - charger should remain OFF
    with patch("time.time", return_value=2031):
        await automation._handle_grid_import_protection(
            grid_import=100, grid_threshold=50, grid_import_delay=30, current_amps=0
        )

    automation.charger_controller.set_amperage.assert_not_called()
    automation.charger_controller.stop_charger.assert_not_called()
    assert automation._last_grid_import_high is None

async def test_surplus_increase_stability(hass, automation):
    """Test surplus increase stability delay."""
    # Setup
    automation.charger_controller.is_charging.return_value = True
    
    # Initial increase detection
    with patch("custom_components.ev_smart_charger.solar_surplus.datetime") as mock_dt:
        mock_dt.now.return_value = datetime(2023, 1, 1, 12, 0, 0)
        
        await automation._handle_surplus_increase(target_amps=16, current_amps=10)
        
        assert automation._surplus_stable_since == datetime(2023, 1, 1, 12, 0, 0)
        automation.charger_controller.set_amperage.assert_not_called()
        
        # Not enough time passed
        mock_dt.now.return_value = datetime(2023, 1, 1, 12, 0, 30)
        await automation._handle_surplus_increase(target_amps=16, current_amps=10)
        automation.charger_controller.set_amperage.assert_not_called()
        
        # Stability confirmed (> 60s)
        mock_dt.now.return_value = datetime(2023, 1, 1, 12, 1, 1)
        await automation._handle_surplus_increase(target_amps=16, current_amps=10)
        
        automation.charger_controller.set_amperage.assert_called_with(16, "Stable surplus increase")
        assert automation._surplus_stable_since is None

async def test_priority_stop_runs_even_if_energy_sensors_invalid(hass, automation):
    """Priority EV_FREE must stop charging even if solar/grid sensors are unavailable."""
    # Preconditions for periodic flow
    hass.states.async_set("switch.force", "off")
    hass.states.async_set("select.profile", "solar_surplus")
    hass.states.async_set("sensor.charger_status", CHARGER_STATUS_CHARGING)

    # Make energy sensors invalid: logic should still enforce target stop before validation
    hass.states.async_set("sensor.solar", "unavailable")
    hass.states.async_set("sensor.consumption", "unavailable")
    hass.states.async_set("sensor.grid", "unavailable")

    automation.priority_balancer.is_enabled.return_value = True
    automation.priority_balancer.calculate_priority = AsyncMock(return_value=PRIORITY_EV_FREE)
    automation.charger_controller.is_charging.return_value = True

    await automation._async_periodic_check()

    automation.charger_controller.stop_charger.assert_called_with(
        "Both EV and Home targets reached (Priority = EV_FREE)"
    )

async def test_no_start_when_grid_import_is_above_threshold(hass, automation):
    """Do not start charger in solar window when grid import is above threshold."""
    # Preconditions for periodic flow
    hass.states.async_set("switch.force", "off")
    hass.states.async_set("select.profile", "solar_surplus")
    hass.states.async_set("sensor.charger_status", CHARGER_STATUS_CHARGING)
    hass.states.async_set("sensor.solar", "4000")
    hass.states.async_set("sensor.consumption", "1000")
    hass.states.async_set("sensor.grid", "200")
    hass.states.async_set("number.grid_threshold", "50")
    hass.states.async_set("number.grid_delay", "30")
    hass.states.async_set("number.surplus_delay", "30")
    hass.states.async_set("switch.use_battery", "off")

    automation.priority_balancer.is_enabled.return_value = False
    automation.charger_controller.is_charging.return_value = False
    automation.charger_controller.get_current_amperage.return_value = 0

    # Force a positive target amperage to verify start is blocked by grid import protection
    with patch.object(automation, "_calculate_target_amperage", return_value=6):
        await automation._async_periodic_check()

    automation.charger_controller.start_charger.assert_not_called()
    assert automation._last_grid_import_high is not None

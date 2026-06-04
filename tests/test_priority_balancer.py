"""Test PriorityBalancer logic."""
import pytest
from unittest.mock import patch, MagicMock
from custom_components.ev_smart_charger.priority_balancer import PriorityBalancer
from custom_components.ev_smart_charger.const import (
    CONF_SOC_CAR,
    CONF_SOC_HOME,
    PRIORITY_EV,
    PRIORITY_HOME,
    PRIORITY_EV_FREE,
)

@pytest.fixture
def balancer(hass):
    """Create a PriorityBalancer instance."""
    config = {
        CONF_SOC_CAR: "sensor.car_soc",
        CONF_SOC_HOME: "sensor.home_soc",
    }
    balancer = PriorityBalancer(hass, "test_entry", config)
    balancer._soc_car = "sensor.car_soc"
    return balancer

async def test_calculate_priority_ev(hass, balancer):
    """Test priority calculation: EV below target."""
    # Setup helper entities
    balancer._ev_min_soc_entities = {"monday": "number.ev_target"}
    balancer._home_min_soc_entities = {"monday": "number.home_target"}
    
    # Mock states
    hass.states.async_set("sensor.car_soc", "40")
    hass.states.async_set("sensor.home_soc", "60")
    hass.states.async_set("number.ev_target", "50")
    hass.states.async_set("number.home_target", "50")
    
    # Mock day to Monday
    with patch("custom_components.ev_smart_charger.priority_balancer.dt_util.now") as mock_now:
        mock_now.return_value.strftime.return_value = "Monday"
        mock_now.return_value.isoformat.return_value = "2023-01-01T12:00:00"
        
        priority = await balancer.calculate_priority()
        
        assert priority == PRIORITY_EV

async def test_calculate_priority_home(hass, balancer):
    """Test priority calculation: EV met, Home below target."""
    # Setup helper entities
    balancer._ev_min_soc_entities = {"monday": "number.ev_target"}
    balancer._home_min_soc_entities = {"monday": "number.home_target"}
    
    # Mock states
    hass.states.async_set("sensor.car_soc", "60")  # > 50
    hass.states.async_set("sensor.home_soc", "40") # < 50
    hass.states.async_set("number.ev_target", "50")
    hass.states.async_set("number.home_target", "50")
    
    # Mock day to Monday
    with patch("custom_components.ev_smart_charger.priority_balancer.dt_util.now") as mock_now:
        mock_now.return_value.strftime.return_value = "Monday"
        mock_now.return_value.isoformat.return_value = "2023-01-01T12:00:00"
        
        priority = await balancer.calculate_priority()
        
        assert priority == PRIORITY_HOME

async def test_calculate_priority_free(hass, balancer):
    """Test priority calculation: Both targets met."""
    # Setup helper entities
    balancer._ev_min_soc_entities = {"monday": "number.ev_target"}
    balancer._home_min_soc_entities = {"monday": "number.home_target"}
    
    # Mock states
    hass.states.async_set("sensor.car_soc", "60")  # > 50
    hass.states.async_set("sensor.home_soc", "60") # > 50
    hass.states.async_set("number.ev_target", "50")
    hass.states.async_set("number.home_target", "50")
    
    # Mock day to Monday
    with patch("custom_components.ev_smart_charger.priority_balancer.dt_util.now") as mock_now:
        mock_now.return_value.strftime.return_value = "Monday"
        mock_now.return_value.isoformat.return_value = "2023-01-01T12:00:00"
        
        priority = await balancer.calculate_priority()
        
        assert priority == PRIORITY_EV_FREE

async def test_target_reached_checks(hass, balancer):
    """Test target reached helper methods."""
    balancer._ev_min_soc_entities = {"monday": "number.ev_target"}
    
    hass.states.async_set("sensor.car_soc", "60")
    hass.states.async_set("number.ev_target", "50")
    
    with patch("custom_components.ev_smart_charger.priority_balancer.dt_util.now") as mock_now:
        mock_now.return_value.strftime.return_value = "Monday"
        
        assert await balancer.is_ev_target_reached() is True
        
        # Change target
        hass.states.async_set("number.ev_target", "70")
        assert await balancer.is_ev_target_reached() is False


async def test_has_active_home_soc_target_true(hass, balancer):
    """v2.5.0 (issue #35): at least one daily home target > 0 → True."""
    balancer._home_min_soc_entities = {
        "monday": "number.home_target_mon",
        "tuesday": "number.home_target_tue",
    }
    hass.states.async_set("number.home_target_mon", "0")
    hass.states.async_set("number.home_target_tue", "90")

    assert balancer.has_active_home_soc_target() is True


async def test_has_active_home_soc_target_all_zero(hass, balancer):
    """All daily home targets at 0% → False (nothing to protect)."""
    balancer._home_min_soc_entities = {"monday": "number.home_target_mon"}
    hass.states.async_set("number.home_target_mon", "0")

    assert balancer.has_active_home_soc_target() is False


async def test_has_active_home_soc_target_pv_only(hass):
    """PV-only mode (no home battery) → always False."""
    config = {CONF_SOC_CAR: "sensor.car_soc"}  # no CONF_SOC_HOME
    pv_balancer = PriorityBalancer(hass, "test_entry", config)
    pv_balancer._home_min_soc_entities = {"monday": "number.home_target_mon"}
    hass.states.async_set("number.home_target_mon", "90")

    assert pv_balancer.has_active_home_soc_target() is False

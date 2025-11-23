"""Test SmartChargerBlocker logic."""
import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime
from custom_components.ev_smart_charger.automations import SmartChargerBlocker
from custom_components.ev_smart_charger.const import (
    CONF_EV_CHARGER_SWITCH,
    CONF_EV_CHARGER_STATUS,
)

@pytest.fixture
def blocker(hass, mock_charger_controller):
    """Create a SmartChargerBlocker instance."""
    config = {
        CONF_EV_CHARGER_SWITCH: "switch.charger",
        CONF_EV_CHARGER_STATUS: "sensor.charger_status",
    }
    
    # Mock NightSmartCharge dependency
    mock_nsc = MagicMock()
    mock_nsc.is_active.return_value = False
    
    with patch("custom_components.ev_smart_charger.automations.AstralTimeService") as mock_astral:
        instance = SmartChargerBlocker(
            hass, "test_entry", config, mock_nsc, mock_charger_controller
        )
        
        # Mock helper entities
        instance._forza_ricarica_entity = "switch.force_charge"
        instance._blocker_enabled_entity = "switch.blocker_enabled"
        instance._night_charge_time_entity = "input_datetime.night_charge_time"
        
        return instance

async def test_should_block_charging_normal(hass, blocker):
    """Test blocking logic in normal conditions."""
    # Setup
    hass.states.async_set("switch.force_charge", "off")
    hass.states.async_set("switch.blocker_enabled", "on")
    
    # Case 1: In blocking window
    blocker._astral_service.is_in_blocking_window.return_value = (True, "Sunset")
    should_block, reason = await blocker._should_block_charging()
    assert should_block is True
    assert "Sunset" in reason
    
    # Case 2: Outside blocking window
    blocker._astral_service.is_in_blocking_window.return_value = (False, "Daytime")
    should_block, reason = await blocker._should_block_charging()
    assert should_block is False

async def test_should_block_overrides(hass, blocker):
    """Test overrides (Forza Ricarica, Blocker Disabled)."""
    # Case 1: Forza Ricarica ON
    hass.states.async_set("switch.force_charge", "on")
    hass.states.async_set("switch.blocker_enabled", "on")
    blocker._astral_service.is_in_blocking_window.return_value = (True, "Sunset")
    
    should_block, reason = await blocker._should_block_charging()
    assert should_block is False
    assert "Forza Ricarica" in reason
    
    # Case 2: Blocker Disabled
    hass.states.async_set("switch.force_charge", "off")
    hass.states.async_set("switch.blocker_enabled", "off")
    
    should_block, reason = await blocker._should_block_charging()
    assert should_block is False
    assert "disabled" in reason

async def test_check_and_block_execution(hass, blocker):
    """Test the execution of blocking action."""
    hass.states.async_set("switch.force_charge", "off")
    hass.states.async_set("switch.blocker_enabled", "on")
    blocker._astral_service.is_in_blocking_window.return_value = (True, "Sunset")
    
    # Register persistent_notification.create service
    hass.services.async_register("persistent_notification", "create", lambda service: None)
    
    await blocker._check_and_block_if_needed("Test Trigger")
    
    # Verify charger stopped
    blocker.charger_controller.stop_charger.assert_called_once()
    assert blocker._currently_blocking is True

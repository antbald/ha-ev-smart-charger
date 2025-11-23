"""Test ChargerController logic."""
import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime, timedelta
from custom_components.ev_smart_charger.charger_controller import ChargerController
from custom_components.ev_smart_charger.const import (
    CONF_EV_CHARGER_SWITCH,
    CONF_EV_CHARGER_CURRENT,
    CHARGER_AMP_LEVELS,
)

@pytest.fixture
def controller(hass):
    """Create a ChargerController instance."""
    config = {
        CONF_EV_CHARGER_SWITCH: "switch.charger",
        CONF_EV_CHARGER_CURRENT: "number.charger_current",
    }
    return ChargerController(hass, "test_entry", config)

async def test_initial_state(hass, controller):
    """Test initial state reading."""
    # Mock HA state
    hass.states.async_set("switch.charger", "off")
    hass.states.async_set("number.charger_current", "10")

    await controller.async_setup()

    assert controller._is_on is False
    assert controller._current_amperage == 10

async def test_start_charger(hass, controller):
    """Test starting the charger."""
    hass.states.async_set("switch.charger", "off")
    hass.states.async_set("number.charger_current", "6")
    await controller.async_setup()

    # Mock service calls
    with patch.object(hass.services, "async_call") as mock_call:
        # Update state when service is called
        async def mock_service_side_effect(domain, service, service_data=None, **kwargs):
            if domain == "number" and service == "set_value":
                hass.states.async_set("number.charger_current", str(service_data["value"]))
        
        mock_call.side_effect = mock_service_side_effect

        result = await controller.start_charger(target_amps=16, reason="Test")
        
        assert result.success
        assert result.operation == "start"
        assert result.amperage == 16
        
        # Verify sequence: set amps -> turn on
        assert mock_call.call_count == 2
        
        # Check set amperage call
        call1 = mock_call.call_args_list[0]
        assert call1[0][0] == "number"
        assert call1[0][1] == "set_value"
        assert call1[0][2]["value"] == 16
        
        # Check turn on call
        call2 = mock_call.call_args_list[1]
        assert call2[0][0] == "switch"
        assert call2[0][1] == "turn_on"

async def test_stop_charger(hass, controller):
    """Test stopping the charger."""
    hass.states.async_set("switch.charger", "on")
    await controller.async_setup()

    with patch.object(hass.services, "async_call") as mock_call:
        result = await controller.stop_charger(reason="Test")
        
        assert result.success
        assert result.operation == "stop"
        
        mock_call.assert_called_once_with(
            "switch", "turn_off", {"entity_id": "switch.charger"}, blocking=True
        )

async def test_set_amperage_increase(hass, controller):
    """Test increasing amperage (direct)."""
    hass.states.async_set("switch.charger", "on")
    hass.states.async_set("number.charger_current", "6")
    await controller.async_setup()

    with patch.object(hass.services, "async_call") as mock_call:
        result = await controller.set_amperage(16, reason="Increase")
        
        assert result.success
        assert result.operation == "set_amperage"
        
        # Should be direct call
        mock_call.assert_called_once()
        # Check positional args: domain, service, service_data
        args = mock_call.call_args[0]
        assert args[2]["value"] == 16

async def test_set_amperage_decrease(hass, controller):
    """Test decreasing amperage (safe sequence)."""
    hass.states.async_set("switch.charger", "on")
    hass.states.async_set("number.charger_current", "16")
    await controller.async_setup()

    with patch.object(hass.services, "async_call") as mock_call:
        # Mock sleep to speed up test
        with patch("asyncio.sleep"):
            result = await controller.set_amperage(6, reason="Decrease")
        
        assert result.success
        assert result.operation == "adjust_down"
        
        # Should be sequence: stop -> set -> start
        assert mock_call.call_count == 3
        
        calls = mock_call.call_args_list
        assert calls[0][0][1] == "turn_off"
        assert calls[1][0][1] == "set_value"
        assert calls[1][0][2]["value"] == 6
        assert calls[2][0][1] == "turn_on"

async def test_rate_limiting(hass, controller):
    """Test rate limiting logic."""
    hass.states.async_set("switch.charger", "off")
    await controller.async_setup()

    # First operation
    with patch.object(hass.services, "async_call"):
        await controller.start_charger(6)
    
    # Immediate second operation should be queued
    result = await controller.start_charger(10)
    assert result.queued is True
    assert controller.get_queue_size() == 1

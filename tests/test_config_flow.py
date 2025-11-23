"""Test ev_smart_charger config flow."""
from unittest.mock import patch
import pytest
from homeassistant import config_entries, data_entry_flow
from homeassistant.core import HomeAssistant
from homeassistant.const import CONF_NAME

from custom_components.ev_smart_charger.const import (
    DOMAIN,
    CONF_EV_CHARGER_SWITCH,
    CONF_EV_CHARGER_CURRENT,
    CONF_EV_CHARGER_STATUS,
    CONF_SOC_CAR,
    CONF_SOC_HOME,
    CONF_FV_PRODUCTION,
    CONF_HOME_CONSUMPTION,
    CONF_GRID_IMPORT,
    CONF_PV_FORECAST,
)

async def test_form(hass: HomeAssistant):
    """Test we get the form."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert result["step_id"] == "user"

    # Simulate user input for the first step (Name)
    result2 = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_NAME: "Test Charger"},
    )
    assert result2["type"] == data_entry_flow.FlowResultType.FORM
    assert result2["step_id"] == "entities"

    # Simulate user input for the second step (Charger Entities)
    result3 = await hass.config_entries.flow.async_configure(
        result2["flow_id"],
        {
            CONF_EV_CHARGER_SWITCH: "switch.charger",
            CONF_EV_CHARGER_CURRENT: "number.charger_current",
            CONF_EV_CHARGER_STATUS: "sensor.charger_status",
        },
    )
    assert result3["type"] == data_entry_flow.FlowResultType.FORM
    assert result3["step_id"] == "sensors"

    # Simulate user input for the third step (Sensors)
    result4 = await hass.config_entries.flow.async_configure(
        result3["flow_id"],
        {
            CONF_SOC_CAR: "sensor.car_soc",
            CONF_SOC_HOME: "sensor.home_soc",
            CONF_FV_PRODUCTION: "sensor.solar",
            CONF_HOME_CONSUMPTION: "sensor.consumption",
            CONF_GRID_IMPORT: "sensor.grid",
        },
    )
    assert result4["type"] == data_entry_flow.FlowResultType.FORM
    assert result4["step_id"] == "pv_forecast"

    # Simulate user input for the fourth step (PV Forecast)
    result5 = await hass.config_entries.flow.async_configure(
        result4["flow_id"],
        {
            CONF_PV_FORECAST: "sensor.forecast",
        },
    )
    assert result5["type"] == data_entry_flow.FlowResultType.FORM
    assert result5["step_id"] == "notifications"

    # Simulate user input for the fifth step (Notifications)
    with patch(
        "custom_components.ev_smart_charger.async_setup_entry",
        return_value=True,
    ) as mock_setup_entry:
        result6 = await hass.config_entries.flow.async_configure(
            result5["flow_id"],
            {
                "car_owner": "person.test",
            },
        )
        assert result6["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
        assert result6["title"] == "Test Charger"
        assert result6["data"][CONF_NAME] == "Test Charger"
        assert result6["data"][CONF_EV_CHARGER_SWITCH] == "switch.charger"
        
        await hass.async_block_till_done()
        assert len(mock_setup_entry.mock_calls) == 1

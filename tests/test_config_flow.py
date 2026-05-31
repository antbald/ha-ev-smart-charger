"""Test ev_smart_charger config flow."""
from unittest.mock import patch
import pytest
from homeassistant import config_entries, data_entry_flow
from homeassistant.core import HomeAssistant
from homeassistant.const import CONF_NAME
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ev_smart_charger.const import (
    DOMAIN,
    DEFAULT_BATTERY_CAPACITY,
    CONF_CHARGER_MODEL,
    CONF_EV_CHARGER_SWITCH,
    CONF_EV_CHARGER_CURRENT,
    CONF_EV_CHARGER_STATUS,
    CONF_PHASE_MODE,
    CONF_SOC_CAR,
    CONF_SOC_HOME,
    CONF_FV_PRODUCTION,
    CONF_FV_PRODUCTION_L2,
    CONF_FV_PRODUCTION_L3,
    CONF_HOME_CONSUMPTION,
    CONF_HOME_CONSUMPTION_L2,
    CONF_HOME_CONSUMPTION_L3,
    CONF_GRID_IMPORT,
    CONF_GRID_IMPORT_L2,
    CONF_GRID_IMPORT_L3,
    CONF_PV_FORECAST,
    CONF_NOTIFY_SERVICES,
    CONF_BATTERY_CAPACITY,
    CONF_BATTERY_POWER,
    CONF_HYBRID_INVERTER_MODE,
    CONF_CAR_OWNER,
    CONF_ENERGY_FORECAST_TARGET,
    CHARGER_MODEL_GENERIC,
    CHARGER_MODEL_TUYA,
    PHASE_MODE_SINGLE,
    PHASE_MODE_THREE,
)


async def _advance_mode_steps(hass: HomeAssistant, flow_id: str):
    """v2.0.0: submit the phase_mode + charger_model steps (single + tuya).

    These two steps now sit between the name step and the charger-entities step.
    """
    result = await hass.config_entries.flow.async_configure(
        flow_id, {CONF_PHASE_MODE: PHASE_MODE_SINGLE}
    )
    assert result["step_id"] == "charger_model"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_CHARGER_MODEL: CHARGER_MODEL_TUYA}
    )
    return result


async def test_form(hass: HomeAssistant):
    """Test we get the form and can walk the full 9-step flow."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert result["step_id"] == "user"

    # Step 1: name → phase_mode
    result2 = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_NAME: "Test Charger"},
    )
    assert result2["type"] == data_entry_flow.FlowResultType.FORM
    assert result2["step_id"] == "phase_mode"

    # Steps 2-3: phase_mode + charger_model → entities
    result3 = await _advance_mode_steps(hass, result2["flow_id"])
    assert result3["type"] == data_entry_flow.FlowResultType.FORM
    assert result3["step_id"] == "entities"

    # Step 4: Charger Entities → sensors
    result4 = await hass.config_entries.flow.async_configure(
        result3["flow_id"],
        {
            CONF_EV_CHARGER_SWITCH: "switch.charger",
            CONF_EV_CHARGER_CURRENT: "number.charger_current",
            CONF_EV_CHARGER_STATUS: "sensor.charger_status",
        },
    )
    assert result4["type"] == data_entry_flow.FlowResultType.FORM
    assert result4["step_id"] == "sensors"

    # Step 5: Sensors → hybrid_inverter
    result5 = await hass.config_entries.flow.async_configure(
        result4["flow_id"],
        {
            CONF_SOC_CAR: "sensor.car_soc",
            CONF_SOC_HOME: "sensor.home_soc",
            CONF_FV_PRODUCTION: "sensor.solar",
            CONF_HOME_CONSUMPTION: "sensor.consumption",
            CONF_GRID_IMPORT: "sensor.grid",
        },
    )
    assert result5["type"] == data_entry_flow.FlowResultType.FORM
    assert result5["step_id"] == "hybrid_inverter"

    # Step 6: Hybrid Inverter (v2.1.0 — issue #29) → pv_forecast
    result5b = await hass.config_entries.flow.async_configure(
        result5["flow_id"],
        {CONF_HYBRID_INVERTER_MODE: True, CONF_BATTERY_POWER: "sensor.battery_power"},
    )
    assert result5b["type"] == data_entry_flow.FlowResultType.FORM
    assert result5b["step_id"] == "pv_forecast"

    # Step 7: PV Forecast → notifications
    result6 = await hass.config_entries.flow.async_configure(
        result5b["flow_id"],
        {
            CONF_PV_FORECAST: "sensor.forecast",
        },
    )
    assert result6["type"] == data_entry_flow.FlowResultType.FORM
    assert result6["step_id"] == "notifications"

    # Step 8: Notifications → external_connectors
    with patch(
        "custom_components.ev_smart_charger.async_setup_entry",
        return_value=True,
    ) as mock_setup_entry:
        result7 = await hass.config_entries.flow.async_configure(
            result6["flow_id"],
            {
                CONF_NOTIFY_SERVICES: [],
                "car_owner": "person.test",
            },
        )
        assert result7["type"] == data_entry_flow.FlowResultType.FORM
        assert result7["step_id"] == "external_connectors"

        # Step 9: External connectors → dashboard
        result8 = await hass.config_entries.flow.async_configure(
            result7["flow_id"],
            {
                CONF_BATTERY_CAPACITY: 13.5,
            },
        )
        assert result8["type"] == data_entry_flow.FlowResultType.FORM
        assert result8["step_id"] == "dashboard"

        # Step 10: Dashboard → create entry
        result9 = await hass.config_entries.flow.async_configure(
            result8["flow_id"],
            {"create_dashboard": False},
        )

        assert result9["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
        assert result9["title"] == "Test Charger"
        assert result9["data"][CONF_NAME] == "Test Charger"
        assert result9["data"][CONF_EV_CHARGER_SWITCH] == "switch.charger"
        assert result9["data"][CONF_PHASE_MODE] == PHASE_MODE_SINGLE
        assert result9["data"][CONF_CHARGER_MODEL] == CHARGER_MODEL_TUYA
        # v2.1.0 (issue #29): hybrid step values round-trip into entry.data
        assert result9["data"][CONF_HYBRID_INVERTER_MODE] is True
        assert result9["data"][CONF_BATTERY_POWER] == "sensor.battery_power"

        await hass.async_block_till_done()
        assert len(mock_setup_entry.mock_calls) == 1


async def test_duplicate_config_entry_aborts_on_entities_step(hass: HomeAssistant):
    """The charger switch is used as unique_id and duplicates are rejected."""
    existing_entry = MockConfigEntry(
        domain=DOMAIN,
        title="Existing Charger",
        data={CONF_EV_CHARGER_SWITCH: "switch.charger"},
        source=config_entries.SOURCE_USER,
        unique_id="switch.charger",
    )
    existing_entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_NAME: "Duplicate Charger"},
    )
    result = await _advance_mode_steps(hass, result["flow_id"])
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_EV_CHARGER_SWITCH: "switch.charger",
            CONF_EV_CHARGER_CURRENT: "number.charger_current",
            CONF_EV_CHARGER_STATUS: "sensor.charger_status",
        },
    )

    assert result["type"] == data_entry_flow.FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_external_connectors_validates_energy_target_entity_exists(hass: HomeAssistant):
    """Energy forecast target must refer to an existing entity."""

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_NAME: "Test Charger"},
    )
    result = await _advance_mode_steps(hass, result["flow_id"])
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_EV_CHARGER_SWITCH: "switch.charger_2",
            CONF_EV_CHARGER_CURRENT: "number.charger_current",
            CONF_EV_CHARGER_STATUS: "sensor.charger_status",
        },
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_SOC_CAR: "sensor.car_soc",
            CONF_SOC_HOME: "sensor.home_soc",
            CONF_FV_PRODUCTION: "sensor.solar",
            CONF_HOME_CONSUMPTION: "sensor.consumption",
            CONF_GRID_IMPORT: "sensor.grid",
        },
    )
    # v2.1.0 (issue #29): hybrid_inverter step between sensors and pv_forecast
    assert result["step_id"] == "hybrid_inverter"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {},
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_PV_FORECAST: "sensor.forecast",
        },
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_NOTIFY_SERVICES: [],
            CONF_CAR_OWNER: "person.test",
        },
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_BATTERY_CAPACITY: DEFAULT_BATTERY_CAPACITY,
            CONF_ENERGY_FORECAST_TARGET: "number.missing_energy_target",
        },
    )

    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert result["errors"] == {"energy_forecast_target": "entity_not_found"}


def _schema_keys(result) -> set[str]:
    """Return the set of field names in a shown form's data schema."""
    return {
        getattr(marker, "schema", marker)
        for marker in result["data_schema"].schema
    }


async def test_three_phase_generic_flow(hass: HomeAssistant):
    """End-to-end: three-phase + generic creates an entry with all L2/L3 keys.

    This is the primary path for the feature's target users — exercised through
    the real flow (not a hand-built config dict).
    """
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_NAME: "Three Phase"}
    )
    assert result["step_id"] == "phase_mode"

    # phase_mode = three → charger_model
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_PHASE_MODE: PHASE_MODE_THREE}
    )
    assert result["step_id"] == "charger_model"

    # charger_model = generic → entities
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_CHARGER_MODEL: CHARGER_MODEL_GENERIC}
    )
    assert result["step_id"] == "entities"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_EV_CHARGER_SWITCH: "switch.charger3",
            CONF_EV_CHARGER_CURRENT: "number.charger_current",
            CONF_EV_CHARGER_STATUS: "sensor.charger_status",
        },
    )
    assert result["step_id"] == "sensors"

    # The three-phase sensors form must expose all six L2/L3 power fields.
    keys = _schema_keys(result)
    for key in (
        CONF_FV_PRODUCTION_L2, CONF_FV_PRODUCTION_L3,
        CONF_HOME_CONSUMPTION_L2, CONF_HOME_CONSUMPTION_L3,
        CONF_GRID_IMPORT_L2, CONF_GRID_IMPORT_L3,
    ):
        assert key in keys, f"three-phase sensors form is missing {key}"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_SOC_CAR: "sensor.car_soc",
            CONF_SOC_HOME: "sensor.home_soc",
            CONF_FV_PRODUCTION: "sensor.pv1",
            CONF_FV_PRODUCTION_L2: "sensor.pv2",
            CONF_FV_PRODUCTION_L3: "sensor.pv3",
            CONF_HOME_CONSUMPTION: "sensor.cons1",
            CONF_HOME_CONSUMPTION_L2: "sensor.cons2",
            CONF_HOME_CONSUMPTION_L3: "sensor.cons3",
            CONF_GRID_IMPORT: "sensor.grid1",
            CONF_GRID_IMPORT_L2: "sensor.grid2",
            CONF_GRID_IMPORT_L3: "sensor.grid3",
        },
    )
    # v2.1.0 (issue #29): hybrid_inverter step (battery_power stays single, not per-phase)
    assert result["step_id"] == "hybrid_inverter"
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["step_id"] == "pv_forecast"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_PV_FORECAST: "sensor.forecast"}
    )
    assert result["step_id"] == "notifications"

    with patch(
        "custom_components.ev_smart_charger.async_setup_entry",
        return_value=True,
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_NOTIFY_SERVICES: [], "car_owner": "person.test"},
        )
        assert result["step_id"] == "external_connectors"

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_BATTERY_CAPACITY: 13.5}
        )
        assert result["step_id"] == "dashboard"

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"create_dashboard": False}
        )

    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    data = result["data"]
    assert data[CONF_PHASE_MODE] == PHASE_MODE_THREE
    assert data[CONF_CHARGER_MODEL] == CHARGER_MODEL_GENERIC
    # all six per-phase keys persisted
    assert data[CONF_FV_PRODUCTION_L2] == "sensor.pv2"
    assert data[CONF_FV_PRODUCTION_L3] == "sensor.pv3"
    assert data[CONF_HOME_CONSUMPTION_L2] == "sensor.cons2"
    assert data[CONF_HOME_CONSUMPTION_L3] == "sensor.cons3"
    assert data[CONF_GRID_IMPORT_L2] == "sensor.grid2"
    assert data[CONF_GRID_IMPORT_L3] == "sensor.grid3"

"""Additional tests for the EVSC config and options flow."""
from __future__ import annotations

from unittest.mock import patch

import pytest
from homeassistant import config_entries, data_entry_flow
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ev_smart_charger.config_flow import EVSCConfigFlow, EVSCOptionsFlow
from custom_components.ev_smart_charger.const import (
    CONF_BATTERY_CAPACITY,
    CONF_CAR_OWNER,
    CONF_ENERGY_FORECAST_TARGET,
    CONF_EV_CHARGER_CURRENT,
    CONF_EV_CHARGER_STATUS,
    CONF_EV_CHARGER_SWITCH,
    CONF_FV_PRODUCTION,
    CONF_GRID_IMPORT,
    CONF_HOME_CONSUMPTION,
    CONF_NOTIFY_SERVICES,
    CONF_PV_FORECAST,
    CONF_SOC_CAR,
    CONF_SOC_HOME,
    DEFAULT_BATTERY_CAPACITY,
    DOMAIN,
)


def _base_flow_payloads() -> tuple[dict, dict, dict, dict, dict]:
    """Return the five payload blocks needed before external connectors."""
    return (
        {"name": "Test Charger"},
        {
            CONF_EV_CHARGER_SWITCH: "switch.charger",
            CONF_EV_CHARGER_CURRENT: "number.charger_current",
            CONF_EV_CHARGER_STATUS: "sensor.charger_status",
        },
        {
            CONF_SOC_CAR: "sensor.car_soc",
            CONF_SOC_HOME: "sensor.home_soc",
            CONF_FV_PRODUCTION: "sensor.solar",
            CONF_HOME_CONSUMPTION: "sensor.home_use",
            CONF_GRID_IMPORT: "sensor.grid",
        },
        {CONF_PV_FORECAST: "sensor.forecast"},
        {
            CONF_NOTIFY_SERVICES: ["mobile_app_phone"],
            CONF_CAR_OWNER: "person.owner",
        },
    )


async def _init_flow_to_external_connectors(hass) -> str:
    """Advance the config flow to the final step and return the flow id."""
    name_payload, entities_payload, sensors_payload, pv_payload, notifications_payload = (
        _base_flow_payloads()
    )

    hass.services.async_register("notify", "mobile_app_phone", lambda call: None)
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_USER},
    )
    result = await hass.config_entries.flow.async_configure(result["flow_id"], name_payload)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], entities_payload)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], sensors_payload)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], pv_payload)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], notifications_payload)

    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert result["step_id"] == "external_connectors"
    return result["flow_id"]


async def test_config_flow_validates_missing_energy_target_entity(hass) -> None:
    """Final step rejects an energy forecast target that does not exist."""
    flow_id = await _init_flow_to_external_connectors(hass)

    result = await hass.config_entries.flow.async_configure(
        flow_id,
        {
            CONF_BATTERY_CAPACITY: DEFAULT_BATTERY_CAPACITY,
            CONF_ENERGY_FORECAST_TARGET: "number.missing_target",
        },
    )

    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert result["errors"] == {"energy_forecast_target": "entity_not_found"}


async def test_config_flow_validates_energy_target_domain(hass) -> None:
    """Final step rejects energy target entities outside number/input_number."""
    hass.states.async_set("sensor.invalid_target", "1")
    flow = EVSCConfigFlow()
    flow.hass = hass
    name_payload, entities_payload, sensors_payload, pv_payload, notifications_payload = (
        _base_flow_payloads()
    )
    flow.init_info = name_payload
    flow.charger_info = entities_payload
    flow.sensor_info = sensors_payload
    flow.pv_forecast_info = pv_payload
    flow.notifications_info = notifications_payload

    result = await flow.async_step_external_connectors(
        {
            CONF_BATTERY_CAPACITY: DEFAULT_BATTERY_CAPACITY,
            CONF_ENERGY_FORECAST_TARGET: "sensor.invalid_target",
        }
    )

    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert result["errors"] == {"energy_forecast_target": "invalid_domain"}


async def test_mobile_notify_services_are_filtered_by_prefix(hass) -> None:
    """Only mobile_app notify services are returned for selection."""
    hass.services.async_register("notify", "mobile_app_alice", lambda call: None)
    hass.services.async_register("notify", "notify_everyone", lambda call: None)

    flow = EVSCConfigFlow()
    flow.hass = hass

    assert flow._get_mobile_notify_services() == ["mobile_app_alice"]


async def test_options_flow_updates_entry_data(hass) -> None:
    """Options flow merges updated data into the config entry."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_EV_CHARGER_SWITCH: "switch.old",
            CONF_EV_CHARGER_CURRENT: "number.old_current",
            CONF_EV_CHARGER_STATUS: "sensor.old_status",
            CONF_SOC_CAR: "sensor.old_car_soc",
            CONF_SOC_HOME: "sensor.old_home_soc",
            CONF_FV_PRODUCTION: "sensor.old_solar",
            CONF_HOME_CONSUMPTION: "sensor.old_home_use",
            CONF_GRID_IMPORT: "sensor.old_grid",
            CONF_PV_FORECAST: "sensor.old_forecast",
            CONF_NOTIFY_SERVICES: [],
            CONF_CAR_OWNER: "person.old_owner",
            CONF_BATTERY_CAPACITY: DEFAULT_BATTERY_CAPACITY,
        },
    )
    entry.add_to_hass(hass)
    hass.services.async_register("notify", "mobile_app_phone", lambda call: None)
    hass.states.async_set("number.energy_target", "1")

    flow = EVSCOptionsFlow(entry)
    flow.hass = hass

    result = await flow.async_step_init(
        {
            CONF_EV_CHARGER_SWITCH: "switch.new",
            CONF_EV_CHARGER_CURRENT: "number.new_current",
            CONF_EV_CHARGER_STATUS: "sensor.new_status",
        }
    )
    assert result["step_id"] == "sensors"

    result = await flow.async_step_sensors(
        {
            CONF_SOC_CAR: "sensor.new_car_soc",
            CONF_SOC_HOME: "sensor.new_home_soc",
            CONF_FV_PRODUCTION: "sensor.new_solar",
            CONF_HOME_CONSUMPTION: "sensor.new_home_use",
            CONF_GRID_IMPORT: "sensor.new_grid",
        }
    )
    assert result["step_id"] == "pv_forecast"

    result = await flow.async_step_pv_forecast({CONF_PV_FORECAST: "sensor.new_forecast"})
    assert result["step_id"] == "notifications"

    result = await flow.async_step_notifications(
        {
            CONF_NOTIFY_SERVICES: ["mobile_app_phone"],
            CONF_CAR_OWNER: "person.new_owner",
        }
    )
    assert result["step_id"] == "external_connectors"

    with patch.object(hass.config_entries, "async_update_entry") as update_entry:
        result = await flow.async_step_external_connectors(
            {
                CONF_BATTERY_CAPACITY: 15.0,
                CONF_ENERGY_FORECAST_TARGET: "number.energy_target",
            }
        )

    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    update_entry.assert_called_once()
    updated_data = update_entry.call_args.kwargs["data"]
    assert updated_data[CONF_EV_CHARGER_SWITCH] == "switch.new"
    assert updated_data[CONF_CAR_OWNER] == "person.new_owner"
    assert updated_data[CONF_ENERGY_FORECAST_TARGET] == "number.energy_target"


async def test_options_flow_manager_can_open_init_step(hass) -> None:
    """The real Home Assistant options flow manager can open the first step."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_EV_CHARGER_SWITCH: "switch.old",
            CONF_EV_CHARGER_CURRENT: "number.old_current",
            CONF_EV_CHARGER_STATUS: "sensor.old_status",
            CONF_SOC_CAR: "sensor.old_car_soc",
            CONF_SOC_HOME: "sensor.old_home_soc",
            CONF_FV_PRODUCTION: "sensor.old_solar",
            CONF_HOME_CONSUMPTION: "sensor.old_home_use",
            CONF_GRID_IMPORT: "sensor.old_grid",
            CONF_PV_FORECAST: "sensor.old_forecast",
            CONF_NOTIFY_SERVICES: [],
            CONF_CAR_OWNER: "person.old_owner",
            CONF_BATTERY_CAPACITY: DEFAULT_BATTERY_CAPACITY,
        },
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)

    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert result["step_id"] == "init"


async def test_options_flow_manager_can_open_init_step_with_legacy_sensor_current(hass) -> None:
    """Legacy entries using sensor.* for charger current must still open options."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_EV_CHARGER_SWITCH: "switch.old",
            CONF_EV_CHARGER_CURRENT: "sensor.old_current",
            CONF_EV_CHARGER_STATUS: "sensor.old_status",
            CONF_SOC_CAR: "sensor.old_car_soc",
            CONF_SOC_HOME: "sensor.old_home_soc",
            CONF_FV_PRODUCTION: "sensor.old_solar",
            CONF_HOME_CONSUMPTION: "sensor.old_home_use",
            CONF_GRID_IMPORT: "sensor.old_grid",
            CONF_PV_FORECAST: "sensor.old_forecast",
            CONF_NOTIFY_SERVICES: [],
            CONF_CAR_OWNER: "person.old_owner",
            CONF_BATTERY_CAPACITY: DEFAULT_BATTERY_CAPACITY,
        },
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)

    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert result["step_id"] == "init"


async def test_async_get_options_flow_returns_expected_type() -> None:
    """Config flow exposes the EVSC options flow class."""
    entry = MockConfigEntry(domain=DOMAIN, data={})

    flow = EVSCConfigFlow.async_get_options_flow(entry)

    assert isinstance(flow, EVSCOptionsFlow)


def test_options_flow_uses_home_assistant_config_entry_helper() -> None:
    """Options flow must use HA's config-entry-aware base class."""
    assert issubclass(EVSCOptionsFlow, config_entries.OptionsFlowWithConfigEntry)


async def test_reconfigure_flow_updates_entry_data(hass) -> None:
    """The native reconfigure flow updates entry data and unique_id."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="switch.old",
        data={
            CONF_EV_CHARGER_SWITCH: "switch.old",
            CONF_EV_CHARGER_CURRENT: "number.old_current",
            CONF_EV_CHARGER_STATUS: "sensor.old_status",
            CONF_SOC_CAR: "sensor.old_car_soc",
            CONF_SOC_HOME: "sensor.old_home_soc",
            CONF_FV_PRODUCTION: "sensor.old_solar",
            CONF_HOME_CONSUMPTION: "sensor.old_home_use",
            CONF_GRID_IMPORT: "sensor.old_grid",
            CONF_PV_FORECAST: "sensor.old_forecast",
            CONF_NOTIFY_SERVICES: [],
            CONF_CAR_OWNER: "person.old_owner",
            CONF_BATTERY_CAPACITY: DEFAULT_BATTERY_CAPACITY,
        },
    )
    entry.add_to_hass(hass)
    hass.services.async_register("notify", "mobile_app_phone", lambda call: None)
    hass.states.async_set("number.energy_target", "1")

    flow = EVSCConfigFlow()
    flow.hass = hass
    flow.context = {"entry_id": entry.entry_id}
    flow._reconfigure_entry = entry

    result = await flow.async_step_reconfigure(
        {
            CONF_EV_CHARGER_SWITCH: "switch.new",
            CONF_EV_CHARGER_CURRENT: "number.new_current",
            CONF_EV_CHARGER_STATUS: "sensor.new_status",
        }
    )
    assert result["step_id"] == "reconfigure_sensors"

    result = await flow.async_step_reconfigure_sensors(
        {
            CONF_SOC_CAR: "sensor.new_car_soc",
            CONF_SOC_HOME: "sensor.new_home_soc",
            CONF_FV_PRODUCTION: "sensor.new_solar",
            CONF_HOME_CONSUMPTION: "sensor.new_home_use",
            CONF_GRID_IMPORT: "sensor.new_grid",
        }
    )
    assert result["step_id"] == "reconfigure_pv_forecast"

    result = await flow.async_step_reconfigure_pv_forecast(
        {CONF_PV_FORECAST: "sensor.new_forecast"}
    )
    assert result["step_id"] == "reconfigure_notifications"

    result = await flow.async_step_reconfigure_notifications(
        {
            CONF_NOTIFY_SERVICES: ["mobile_app_phone"],
            CONF_CAR_OWNER: "person.new_owner",
        }
    )
    assert result["step_id"] == "reconfigure_external_connectors"

    with patch.object(hass.config_entries, "async_update_entry") as update_entry:
        result = await flow.async_step_reconfigure_external_connectors(
            {
                CONF_BATTERY_CAPACITY: 15.0,
                CONF_ENERGY_FORECAST_TARGET: "number.energy_target",
            }
        )

    assert result["type"] == data_entry_flow.FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    update_entry.assert_called_once()
    updated_data = update_entry.call_args.kwargs["data"]
    assert update_entry.call_args.kwargs["unique_id"] == "switch.new"
    assert updated_data[CONF_EV_CHARGER_SWITCH] == "switch.new"
    assert updated_data[CONF_CAR_OWNER] == "person.new_owner"
    assert updated_data[CONF_ENERGY_FORECAST_TARGET] == "number.energy_target"


async def test_reconfigure_flow_rejects_duplicate_switch(hass) -> None:
    """Reconfigure cannot reuse the unique_id of another entry."""
    target_entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="switch.target",
        data={CONF_EV_CHARGER_SWITCH: "switch.target"},
    )
    other_entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="switch.duplicate",
        data={CONF_EV_CHARGER_SWITCH: "switch.duplicate"},
    )
    target_entry.add_to_hass(hass)
    other_entry.add_to_hass(hass)

    flow = EVSCConfigFlow()
    flow.hass = hass
    flow.context = {"entry_id": target_entry.entry_id}
    flow._reconfigure_entry = target_entry

    result = await flow.async_step_reconfigure(
        {
            CONF_EV_CHARGER_SWITCH: "switch.duplicate",
            CONF_EV_CHARGER_CURRENT: "number.new_current",
            CONF_EV_CHARGER_STATUS: "sensor.new_status",
        }
    )

    assert result["type"] == data_entry_flow.FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_reconfigure_flow_manager_can_open_first_step(hass) -> None:
    """The real flow manager can open the native reconfigure step."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="switch.old",
        data={
            CONF_EV_CHARGER_SWITCH: "switch.old",
            CONF_EV_CHARGER_CURRENT: "number.old_current",
            CONF_EV_CHARGER_STATUS: "sensor.old_status",
            CONF_SOC_CAR: "sensor.old_car_soc",
            CONF_SOC_HOME: "sensor.old_home_soc",
            CONF_FV_PRODUCTION: "sensor.old_solar",
            CONF_HOME_CONSUMPTION: "sensor.old_home_use",
            CONF_GRID_IMPORT: "sensor.old_grid",
            CONF_PV_FORECAST: "sensor.old_forecast",
            CONF_NOTIFY_SERVICES: [],
            CONF_CAR_OWNER: "person.old_owner",
            CONF_BATTERY_CAPACITY: DEFAULT_BATTERY_CAPACITY,
        },
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": "reconfigure", "entry_id": entry.entry_id},
    )

    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert result["step_id"] == "reconfigure"

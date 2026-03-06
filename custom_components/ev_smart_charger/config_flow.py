from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_NAME
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import (
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
    DEFAULT_NAME,
    DOMAIN,
    MAX_BATTERY_CAPACITY,
    MIN_BATTERY_CAPACITY,
)

CURRENT_CONTROL_DOMAINS = ["number", "select", "input_number", "input_select"]
ENERGY_TARGET_DOMAINS = ["input_number", "number"]


def _get_mobile_notify_services(hass) -> list[str]:
    """Get list of available mobile_app notify services."""
    notify_services = hass.services.async_services().get("notify", {})
    return sorted(
        service
        for service in notify_services
        if service.startswith("mobile_app_")
    )


def _validate_external_connectors(hass, user_input: dict[str, Any]) -> dict[str, str]:
    """Validate shared external connector settings."""
    errors: dict[str, str] = {}

    battery_capacity = user_input.get(CONF_BATTERY_CAPACITY, DEFAULT_BATTERY_CAPACITY)
    if battery_capacity < MIN_BATTERY_CAPACITY or battery_capacity > MAX_BATTERY_CAPACITY:
        errors["battery_capacity"] = "invalid_battery_capacity"

    energy_target = user_input.get(CONF_ENERGY_FORECAST_TARGET)
    if energy_target:
        state = hass.states.get(energy_target)
        if state is None:
            errors["energy_forecast_target"] = "entity_not_found"
        elif state.domain not in ENERGY_TARGET_DOMAINS:
            errors["energy_forecast_target"] = "invalid_domain"

    return errors


def _is_duplicate_charger_switch(
    hass,
    charger_switch: str,
    *,
    exclude_entry_id: str | None = None,
) -> bool:
    """Return True when another entry already owns the same charger switch."""
    for entry in hass.config_entries.async_entries(DOMAIN):
        if exclude_entry_id is not None and entry.entry_id == exclude_entry_id:
            continue
        if entry.data.get(CONF_EV_CHARGER_SWITCH) == charger_switch:
            return True
    return False


def _merge_entry_data(base_data: dict[str, Any], *sections: dict[str, Any]) -> dict[str, Any]:
    """Merge config sections into a single payload."""
    merged = dict(base_data)
    for section in sections:
        merged.update(section)
    return merged


def _entity_selector(domains: str | list[str]) -> selector.EntitySelector:
    """Create an entity selector for one or more domains."""
    return selector.EntitySelector(selector.EntitySelectorConfig(domain=domains))


def _field_config(default: Any) -> dict[str, Any]:
    """Return voluptuous field kwargs only when a real default is available."""
    if default is None:
        return {}
    return {"default": default}


def _charger_schema(current_data: dict[str, Any] | None = None) -> vol.Schema:
    """Build the charger entities schema."""
    current_data = current_data or {}
    return vol.Schema(
        {
            vol.Required(
                CONF_EV_CHARGER_SWITCH,
                **_field_config(current_data.get(CONF_EV_CHARGER_SWITCH)),
            ): _entity_selector("switch"),
            vol.Required(
                CONF_EV_CHARGER_CURRENT,
                **_field_config(current_data.get(CONF_EV_CHARGER_CURRENT)),
            ): _entity_selector(CURRENT_CONTROL_DOMAINS),
            vol.Required(
                CONF_EV_CHARGER_STATUS,
                **_field_config(current_data.get(CONF_EV_CHARGER_STATUS)),
            ): _entity_selector("sensor"),
        }
    )


def _sensor_schema(current_data: dict[str, Any] | None = None) -> vol.Schema:
    """Build the sensor mapping schema."""
    current_data = current_data or {}
    return vol.Schema(
        {
            vol.Required(CONF_SOC_CAR, **_field_config(current_data.get(CONF_SOC_CAR))): _entity_selector("sensor"),
            vol.Required(CONF_SOC_HOME, **_field_config(current_data.get(CONF_SOC_HOME))): _entity_selector("sensor"),
            vol.Required(CONF_FV_PRODUCTION, **_field_config(current_data.get(CONF_FV_PRODUCTION))): _entity_selector("sensor"),
            vol.Required(
                CONF_HOME_CONSUMPTION,
                **_field_config(current_data.get(CONF_HOME_CONSUMPTION)),
            ): _entity_selector("sensor"),
            vol.Required(CONF_GRID_IMPORT, **_field_config(current_data.get(CONF_GRID_IMPORT))): _entity_selector("sensor"),
        }
    )


def _pv_forecast_schema(current_data: dict[str, Any] | None = None) -> vol.Schema:
    """Build the PV forecast schema."""
    current_data = current_data or {}
    return vol.Schema(
        {
            vol.Optional(
                CONF_PV_FORECAST,
                **_field_config(current_data.get(CONF_PV_FORECAST)),
            ): _entity_selector("sensor")
        }
    )


def _notifications_schema(hass, current_data: dict[str, Any] | None = None) -> vol.Schema:
    """Build the notifications schema."""
    current_data = current_data or {}
    return vol.Schema(
        {
            vol.Optional(
                CONF_NOTIFY_SERVICES,
                **_field_config(current_data.get(CONF_NOTIFY_SERVICES, [])),
            ): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=_get_mobile_notify_services(hass),
                    multiple=True,
                    mode=selector.SelectSelectorMode.DROPDOWN,
                )
            ),
            vol.Required(
                CONF_CAR_OWNER,
                **_field_config(current_data.get(CONF_CAR_OWNER)),
            ): _entity_selector("person"),
        }
    )


def _external_connectors_schema(current_data: dict[str, Any] | None = None) -> vol.Schema:
    """Build the external connectors schema."""
    current_data = current_data or {}
    return vol.Schema(
        {
            vol.Required(
                CONF_BATTERY_CAPACITY,
                **_field_config(
                    current_data.get(CONF_BATTERY_CAPACITY, DEFAULT_BATTERY_CAPACITY)
                ),
            ): vol.All(
                vol.Coerce(float),
                vol.Range(min=MIN_BATTERY_CAPACITY, max=MAX_BATTERY_CAPACITY),
            ),
            vol.Optional(
                CONF_ENERGY_FORECAST_TARGET,
                **_field_config(current_data.get(CONF_ENERGY_FORECAST_TARGET)),
            ): _entity_selector(ENERGY_TARGET_DOMAINS),
        }
    )


class EVSCConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle the EV Smart Charger config flow."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize mutable flow state."""
        self.init_info: dict[str, Any] = {}
        self.charger_info: dict[str, Any] = {}
        self.sensor_info: dict[str, Any] = {}
        self.pv_forecast_info: dict[str, Any] = {}
        self.notifications_info: dict[str, Any] = {}
        self._reconfigure_entry = None

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        """Handle the initial step where user provides a name."""
        if user_input is not None:
            self.init_info = user_input
            return await self.async_step_entities()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({vol.Optional(CONF_NAME, default=DEFAULT_NAME): str}),
            errors={},
            description_placeholders={"step": "1", "total_steps": "6"},
        )

    async def async_step_entities(self, user_input: dict[str, Any] | None = None):
        """Handle charger entity selection step."""
        errors = {}

        if user_input is not None:
            await self.async_set_unique_id(user_input[CONF_EV_CHARGER_SWITCH])
            self._abort_if_unique_id_configured()
            self.charger_info = user_input
            return await self.async_step_sensors()

        return self.async_show_form(
            step_id="entities",
            data_schema=_charger_schema(),
            errors=errors,
            description_placeholders={"step": "2", "total_steps": "6"},
        )

    async def async_step_sensors(self, user_input: dict[str, Any] | None = None):
        """Handle sensor entity selection step."""
        if user_input is not None:
            self.sensor_info = user_input
            return await self.async_step_pv_forecast()

        return self.async_show_form(
            step_id="sensors",
            data_schema=_sensor_schema(),
            errors={},
            description_placeholders={"step": "3", "total_steps": "6"},
        )

    async def async_step_pv_forecast(self, user_input: dict[str, Any] | None = None):
        """Handle PV forecast entity selection step."""
        if user_input is not None:
            self.pv_forecast_info = user_input
            return await self.async_step_notifications()

        return self.async_show_form(
            step_id="pv_forecast",
            data_schema=_pv_forecast_schema(),
            errors={},
            description_placeholders={"step": "4", "total_steps": "6"},
        )

    async def async_step_notifications(self, user_input: dict[str, Any] | None = None):
        """Handle mobile notification services selection step."""
        if user_input is not None:
            self.notifications_info = user_input
            return await self.async_step_external_connectors()

        return self.async_show_form(
            step_id="notifications",
            data_schema=_notifications_schema(self.hass),
            errors={},
            description_placeholders={"step": "5", "total_steps": "6"},
        )

    async def async_step_external_connectors(self, user_input: dict[str, Any] | None = None):
        """Handle external connector configuration step."""
        errors = {}

        if user_input is not None:
            errors = _validate_external_connectors(self.hass, user_input)
            if not errors:
                data = _merge_entry_data(
                    {},
                    self.init_info,
                    self.charger_info,
                    self.sensor_info,
                    self.pv_forecast_info,
                    self.notifications_info,
                    user_input,
                )
                title = self.init_info.get(CONF_NAME, DEFAULT_NAME)
                return self.async_create_entry(title=title, data=data)

        return self.async_show_form(
            step_id="external_connectors",
            data_schema=_external_connectors_schema(),
            errors=errors,
            description_placeholders={"step": "6", "total_steps": "6"},
        )

    async def async_step_reconfigure(self, user_input: dict[str, Any] | None = None):
        """Handle native reconfiguration for existing config entries."""
        self._reconfigure_entry = self.hass.config_entries.async_get_entry(
            self.context["entry_id"]
        )
        if self._reconfigure_entry is None:
            return self.async_abort(reason="unknown_entry")

        if user_input is not None:
            if _is_duplicate_charger_switch(
                self.hass,
                user_input[CONF_EV_CHARGER_SWITCH],
                exclude_entry_id=self._reconfigure_entry.entry_id,
            ):
                return self.async_abort(reason="already_configured")
            self.charger_info = user_input
            return await self.async_step_reconfigure_sensors()

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=_charger_schema(self._reconfigure_entry.data),
            errors={},
            description_placeholders={"step": "1", "total_steps": "5"},
        )

    async def async_step_reconfigure_sensors(self, user_input: dict[str, Any] | None = None):
        """Handle sensor remapping during reconfigure."""
        if user_input is not None:
            self.sensor_info = user_input
            return await self.async_step_reconfigure_pv_forecast()

        return self.async_show_form(
            step_id="reconfigure_sensors",
            data_schema=_sensor_schema(self._reconfigure_entry.data),
            errors={},
            description_placeholders={"step": "2", "total_steps": "5"},
        )

    async def async_step_reconfigure_pv_forecast(self, user_input: dict[str, Any] | None = None):
        """Handle PV forecast remapping during reconfigure."""
        if user_input is not None:
            self.pv_forecast_info = user_input
            return await self.async_step_reconfigure_notifications()

        return self.async_show_form(
            step_id="reconfigure_pv_forecast",
            data_schema=_pv_forecast_schema(self._reconfigure_entry.data),
            errors={},
            description_placeholders={"step": "3", "total_steps": "5"},
        )

    async def async_step_reconfigure_notifications(self, user_input: dict[str, Any] | None = None):
        """Handle notification remapping during reconfigure."""
        if user_input is not None:
            self.notifications_info = user_input
            return await self.async_step_reconfigure_external_connectors()

        return self.async_show_form(
            step_id="reconfigure_notifications",
            data_schema=_notifications_schema(self.hass, self._reconfigure_entry.data),
            errors={},
            description_placeholders={"step": "4", "total_steps": "5"},
        )

    async def async_step_reconfigure_external_connectors(
        self,
        user_input: dict[str, Any] | None = None,
    ):
        """Handle external connector remapping during reconfigure."""
        errors = {}

        if user_input is not None:
            errors = _validate_external_connectors(self.hass, user_input)
            if not errors:
                updated_data = _merge_entry_data(
                    self._reconfigure_entry.data,
                    self.charger_info,
                    self.sensor_info,
                    self.pv_forecast_info,
                    self.notifications_info,
                    user_input,
                )
                self.hass.config_entries.async_update_entry(
                    self._reconfigure_entry,
                    data=updated_data,
                    unique_id=updated_data[CONF_EV_CHARGER_SWITCH],
                )
                return self.async_abort(reason="reconfigure_successful")

        return self.async_show_form(
            step_id="reconfigure_external_connectors",
            data_schema=_external_connectors_schema(self._reconfigure_entry.data),
            errors=errors,
            description_placeholders={"step": "5", "total_steps": "5"},
        )

    def _get_mobile_notify_services(self) -> list[str]:
        """Get list of available mobile_app notify services."""
        return _get_mobile_notify_services(self.hass)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """Get the options flow for this handler."""
        return EVSCOptionsFlow(config_entry)


class EVSCOptionsFlow(config_entries.OptionsFlow):
    """Compatibility wrapper around the canonical reconfigure fields."""

    def __init__(self, config_entry):
        """Initialize options flow."""
        self.config_entry = config_entry
        self.charger_info: dict[str, Any] = {}
        self.sensor_info: dict[str, Any] = {}
        self.pv_forecast_info: dict[str, Any] = {}
        self.notifications_info: dict[str, Any] = {}

    async def async_step_init(self, user_input: dict[str, Any] | None = None):
        """Manage charger entities options."""
        if user_input is not None:
            if _is_duplicate_charger_switch(
                self.hass,
                user_input[CONF_EV_CHARGER_SWITCH],
                exclude_entry_id=self.config_entry.entry_id,
            ):
                return self.async_abort(reason="already_configured")
            self.charger_info = user_input
            return await self.async_step_sensors()

        return self.async_show_form(
            step_id="init",
            data_schema=_charger_schema(self.config_entry.data),
            description_placeholders={"step": "1", "total_steps": "5"},
        )

    async def async_step_sensors(self, user_input: dict[str, Any] | None = None):
        """Manage sensor entities options."""
        if user_input is not None:
            self.sensor_info = user_input
            return await self.async_step_pv_forecast()

        return self.async_show_form(
            step_id="sensors",
            data_schema=_sensor_schema(self.config_entry.data),
            description_placeholders={"step": "2", "total_steps": "5"},
        )

    async def async_step_pv_forecast(self, user_input: dict[str, Any] | None = None):
        """Manage PV forecast entity options."""
        if user_input is not None:
            self.pv_forecast_info = user_input
            return await self.async_step_notifications()

        return self.async_show_form(
            step_id="pv_forecast",
            data_schema=_pv_forecast_schema(self.config_entry.data),
            description_placeholders={"step": "3", "total_steps": "5"},
        )

    async def async_step_notifications(self, user_input: dict[str, Any] | None = None):
        """Manage mobile notification services options."""
        if user_input is not None:
            self.notifications_info = user_input
            return await self.async_step_external_connectors()

        return self.async_show_form(
            step_id="notifications",
            data_schema=_notifications_schema(self.hass, self.config_entry.data),
            description_placeholders={"step": "4", "total_steps": "5"},
        )

    async def async_step_external_connectors(self, user_input: dict[str, Any] | None = None):
        """Handle external connector updates from the compatibility options flow."""
        errors = {}

        if user_input is not None:
            errors = _validate_external_connectors(self.hass, user_input)
            if not errors:
                updated_data = _merge_entry_data(
                    self.config_entry.data,
                    self.charger_info,
                    self.sensor_info,
                    self.pv_forecast_info,
                    self.notifications_info,
                    user_input,
                )
                self.hass.config_entries.async_update_entry(
                    self.config_entry,
                    data=updated_data,
                    unique_id=updated_data[CONF_EV_CHARGER_SWITCH],
                )
                return self.async_create_entry(title="", data={})

        return self.async_show_form(
            step_id="external_connectors",
            data_schema=_external_connectors_schema(self.config_entry.data),
            errors=errors,
            description_placeholders={"step": "5", "total_steps": "5"},
        )

    def _get_mobile_notify_services(self) -> list[str]:
        """Get list of available mobile_app notify services."""
        return _get_mobile_notify_services(self.hass)

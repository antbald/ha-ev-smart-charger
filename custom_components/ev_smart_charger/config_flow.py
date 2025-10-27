from __future__ import annotations
from typing import Any
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_NAME
from homeassistant.helpers import selector
from homeassistant.core import callback
from .const import (
    DOMAIN,
    DEFAULT_NAME,
    CONF_EV_CHARGER_SWITCH,
    CONF_EV_CHARGER_CURRENT,
    CONF_EV_CHARGER_STATUS,
    CONF_SOC_CAR,
    CONF_SOC_HOME,
    CONF_FV_PRODUCTION,
    CONF_HOME_CONSUMPTION,
    CONF_GRID_IMPORT,
)

class EVSCConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        """Handle the initial step where user provides a name."""
        errors = {}

        if user_input is not None:
            # Store the name and move to entity selection
            self.init_info = user_input
            return await self.async_step_entities()

        schema = vol.Schema({
            vol.Optional(CONF_NAME, default=DEFAULT_NAME): str
        })
        return self.async_show_form(
            step_id="user",
            data_schema=schema,
            errors=errors,
            description_placeholders={
                "step": "1",
                "total_steps": "3"
            }
        )

    async def async_step_entities(self, user_input: dict[str, Any] | None = None):
        """Handle charger entity selection step."""
        errors = {}

        if user_input is not None:
            # Store charger entities and move to next step
            self.charger_info = user_input
            return await self.async_step_sensors()

        schema = vol.Schema({
            vol.Required(CONF_EV_CHARGER_SWITCH): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="switch")
            ),
            vol.Required(CONF_EV_CHARGER_CURRENT): selector.EntitySelector(
                selector.EntitySelectorConfig(domain=["number", "select", "input_number", "input_select"])
            ),
            vol.Required(CONF_EV_CHARGER_STATUS): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="sensor")
            ),
        })

        return self.async_show_form(
            step_id="entities",
            data_schema=schema,
            errors=errors,
            description_placeholders={
                "step": "2",
                "total_steps": "3"
            }
        )

    async def async_step_sensors(self, user_input: dict[str, Any] | None = None):
        """Handle sensor entity selection step."""
        errors = {}

        if user_input is not None:
            # Merge all data and create entry
            data = {**self.init_info, **self.charger_info, **user_input}
            title = self.init_info.get(CONF_NAME, DEFAULT_NAME)
            return self.async_create_entry(title=title, data=data)

        schema = vol.Schema({
            vol.Required(CONF_SOC_CAR): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="sensor")
            ),
            vol.Required(CONF_SOC_HOME): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="sensor")
            ),
            vol.Required(CONF_FV_PRODUCTION): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="sensor")
            ),
            vol.Required(CONF_HOME_CONSUMPTION): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="sensor")
            ),
            vol.Required(CONF_GRID_IMPORT): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="sensor")
            ),
        })

        return self.async_show_form(
            step_id="sensors",
            data_schema=schema,
            errors=errors,
            description_placeholders={
                "step": "3",
                "total_steps": "3"
            }
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """Get the options flow for this handler."""
        return EVSCOptionsFlow(config_entry)


class EVSCOptionsFlow(config_entries.OptionsFlow):
    """Handle options flow for EV Smart Charger."""

    def __init__(self, config_entry):
        """Initialize options flow."""
        self.config_entry = config_entry

    async def async_step_init(self, user_input: dict[str, Any] | None = None):
        """Manage charger entities options."""
        if user_input is not None:
            # Store charger entities and move to sensors
            self.charger_info = user_input
            return await self.async_step_sensors()

        # Get current values
        current_data = self.config_entry.data

        schema = vol.Schema({
            vol.Required(
                CONF_EV_CHARGER_SWITCH,
                default=current_data.get(CONF_EV_CHARGER_SWITCH)
            ): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="switch")
            ),
            vol.Required(
                CONF_EV_CHARGER_CURRENT,
                default=current_data.get(CONF_EV_CHARGER_CURRENT)
            ): selector.EntitySelector(
                selector.EntitySelectorConfig(domain=["number", "select", "input_number", "input_select"])
            ),
            vol.Required(
                CONF_EV_CHARGER_STATUS,
                default=current_data.get(CONF_EV_CHARGER_STATUS)
            ): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="sensor")
            ),
        })

        return self.async_show_form(
            step_id="init",
            data_schema=schema,
            description_placeholders={
                "step": "1",
                "total_steps": "2"
            }
        )

    async def async_step_sensors(self, user_input: dict[str, Any] | None = None):
        """Manage sensor entities options."""
        if user_input is not None:
            # Merge all data and update entry
            data = {**self.config_entry.data, **self.charger_info, **user_input}
            self.hass.config_entries.async_update_entry(
                self.config_entry, data=data
            )
            return self.async_create_entry(title="", data={})

        # Get current values
        current_data = self.config_entry.data

        schema = vol.Schema({
            vol.Required(
                CONF_SOC_CAR,
                default=current_data.get(CONF_SOC_CAR)
            ): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="sensor")
            ),
            vol.Required(
                CONF_SOC_HOME,
                default=current_data.get(CONF_SOC_HOME)
            ): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="sensor")
            ),
            vol.Required(
                CONF_FV_PRODUCTION,
                default=current_data.get(CONF_FV_PRODUCTION)
            ): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="sensor")
            ),
            vol.Required(
                CONF_HOME_CONSUMPTION,
                default=current_data.get(CONF_HOME_CONSUMPTION)
            ): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="sensor")
            ),
            vol.Required(
                CONF_GRID_IMPORT,
                default=current_data.get(CONF_GRID_IMPORT)
            ): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="sensor")
            ),
        })

        return self.async_show_form(
            step_id="sensors",
            data_schema=schema,
            description_placeholders={
                "step": "2",
                "total_steps": "2"
            }
        )

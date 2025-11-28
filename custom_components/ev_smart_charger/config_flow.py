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
    CONF_PV_FORECAST,
    CONF_NOTIFY_SERVICES,
    CONF_CAR_OWNER,
    CONF_BATTERY_CAPACITY,
    CONF_ENERGY_FORECAST_TARGET,
    DEFAULT_BATTERY_CAPACITY,
    MIN_BATTERY_CAPACITY,
    MAX_BATTERY_CAPACITY,
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
                "total_steps": "6"
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
                "total_steps": "6"
            }
        )

    async def async_step_sensors(self, user_input: dict[str, Any] | None = None):
        """Handle sensor entity selection step."""
        errors = {}

        if user_input is not None:
            # Store sensor entities and move to PV forecast step
            self.sensor_info = user_input
            return await self.async_step_pv_forecast()

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
                "total_steps": "6"
            }
        )

    async def async_step_pv_forecast(self, user_input: dict[str, Any] | None = None):
        """Handle PV forecast entity selection step (optional)."""
        errors = {}

        if user_input is not None:
            # Store PV forecast info and move to notifications step
            self.pv_forecast_info = user_input
            return await self.async_step_notifications()

        schema = vol.Schema({
            vol.Optional(CONF_PV_FORECAST): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="sensor")
            ),
        })

        return self.async_show_form(
            step_id="pv_forecast",
            data_schema=schema,
            errors=errors,
            description_placeholders={
                "step": "4",
                "total_steps": "6"
            }
        )

    async def async_step_notifications(self, user_input: dict[str, Any] | None = None):
        """Handle mobile notification services selection step."""
        errors = {}

        if user_input is not None:
            # Store notifications info and move to external connectors step
            self.notifications_info = user_input
            return await self.async_step_external_connectors()

        # Discover available mobile notify services
        notify_services = self._get_mobile_notify_services()

        schema = vol.Schema({
            vol.Optional(CONF_NOTIFY_SERVICES, default=[]): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=notify_services,
                    multiple=True,
                    mode=selector.SelectSelectorMode.DROPDOWN
                )
            ),
            vol.Required(CONF_CAR_OWNER): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="person")
            ),
        })

        return self.async_show_form(
            step_id="notifications",
            data_schema=schema,
            errors=errors,
            description_placeholders={
                "step": "5",
                "total_steps": "6"
            }
        )

    async def async_step_external_connectors(self, user_input: dict[str, Any] | None = None):
        """Handle external connectors configuration step (energy forecast)."""
        errors = {}

        if user_input is not None:
            # Validazione capacità batteria
            battery_capacity = user_input.get(CONF_BATTERY_CAPACITY, DEFAULT_BATTERY_CAPACITY)
            if battery_capacity < MIN_BATTERY_CAPACITY or battery_capacity > MAX_BATTERY_CAPACITY:
                errors["battery_capacity"] = "invalid_battery_capacity"

            # Validazione sensore target (opzionale)
            energy_target = user_input.get(CONF_ENERGY_FORECAST_TARGET)
            if energy_target:
                state = self.hass.states.get(energy_target)
                if state is None:
                    errors["energy_forecast_target"] = "entity_not_found"
                elif state.domain != "input_number":
                    errors["energy_forecast_target"] = "invalid_domain"

            if not errors:
                # Merge all data and create entry
                data = {
                    **self.init_info,
                    **self.charger_info,
                    **self.sensor_info,
                    **self.pv_forecast_info,
                    **self.notifications_info,
                    **user_input
                }
                title = self.init_info.get(CONF_NAME, DEFAULT_NAME)
                return self.async_create_entry(title=title, data=data)

        # Schema con defaults
        schema = vol.Schema({
            vol.Required(
                CONF_BATTERY_CAPACITY,
                default=DEFAULT_BATTERY_CAPACITY
            ): vol.All(
                vol.Coerce(float),
                vol.Range(min=MIN_BATTERY_CAPACITY, max=MAX_BATTERY_CAPACITY)
            ),
            vol.Optional(CONF_ENERGY_FORECAST_TARGET): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="input_number")
            ),
        })

        return self.async_show_form(
            step_id="external_connectors",
            data_schema=schema,
            errors=errors,
            description_placeholders={
                "step": "6",
                "total_steps": "6"
            }
        )

    def _get_mobile_notify_services(self) -> list[str]:
        """Get list of available mobile_app notify services."""
        notify_services = self.hass.services.async_services().get("notify", {})
        mobile_services = [
            service
            for service in notify_services.keys()
            if service.startswith("mobile_app_")
        ]
        return mobile_services if mobile_services else []

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
                "total_steps": "5"
            }
        )

    async def async_step_sensors(self, user_input: dict[str, Any] | None = None):
        """Manage sensor entities options."""
        if user_input is not None:
            # Store sensor entities and move to PV forecast step
            self.sensor_info = user_input
            return await self.async_step_pv_forecast()

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
                "total_steps": "5"
            }
        )

    async def async_step_pv_forecast(self, user_input: dict[str, Any] | None = None):
        """Manage PV forecast entity options (optional)."""
        if user_input is not None:
            # Store PV forecast info and move to notifications step
            self.pv_forecast_info = user_input
            return await self.async_step_notifications()

        # Get current values
        current_data = self.config_entry.data

        schema = vol.Schema({
            vol.Optional(
                CONF_PV_FORECAST,
                default=current_data.get(CONF_PV_FORECAST)
            ): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="sensor")
            ),
        })

        return self.async_show_form(
            step_id="pv_forecast",
            data_schema=schema,
            description_placeholders={
                "step": "3",
                "total_steps": "5"
            }
        )

    async def async_step_notifications(self, user_input: dict[str, Any] | None = None):
        """Manage mobile notification services options."""
        if user_input is not None:
            # Store notifications info and move to external connectors step
            self.notifications_info = user_input
            return await self.async_step_external_connectors()

        # Get current values
        current_data = self.config_entry.data
        notify_services = self._get_mobile_notify_services()

        schema = vol.Schema({
            vol.Optional(
                CONF_NOTIFY_SERVICES,
                default=current_data.get(CONF_NOTIFY_SERVICES, [])
            ): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=notify_services,
                    multiple=True,
                    mode=selector.SelectSelectorMode.DROPDOWN
                )
            ),
            vol.Required(
                CONF_CAR_OWNER,
                default=current_data.get(CONF_CAR_OWNER)
            ): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="person")
            ),
        })

        return self.async_show_form(
            step_id="notifications",
            data_schema=schema,
            description_placeholders={
                "step": "4",
                "total_steps": "5"
            }
        )

    async def async_step_external_connectors(self, user_input: dict[str, Any] | None = None):
        """Handle external connectors reconfiguration (energy forecast)."""
        errors = {}

        if user_input is not None:
            # Stessa validazione del flow iniziale
            battery_capacity = user_input.get(CONF_BATTERY_CAPACITY, DEFAULT_BATTERY_CAPACITY)
            if battery_capacity < MIN_BATTERY_CAPACITY or battery_capacity > MAX_BATTERY_CAPACITY:
                errors["battery_capacity"] = "invalid_battery_capacity"

            energy_target = user_input.get(CONF_ENERGY_FORECAST_TARGET)
            if energy_target:
                state = self.hass.states.get(energy_target)
                if state is None:
                    errors["energy_forecast_target"] = "entity_not_found"
                elif state.domain != "input_number":
                    errors["energy_forecast_target"] = "invalid_domain"

            if not errors:
                # Merge all data and update entry
                data = {
                    **self.config_entry.data,
                    **self.charger_info,
                    **self.sensor_info,
                    **self.pv_forecast_info,
                    **self.notifications_info,
                    **user_input
                }
                self.hass.config_entries.async_update_entry(
                    self.config_entry, data=data
                )
                return self.async_create_entry(title="", data={})

        # Valori correnti
        current_data = self.config_entry.data
        battery_capacity = current_data.get(CONF_BATTERY_CAPACITY, DEFAULT_BATTERY_CAPACITY)
        energy_target = current_data.get(CONF_ENERGY_FORECAST_TARGET)

        schema = vol.Schema({
            vol.Required(
                CONF_BATTERY_CAPACITY,
                default=battery_capacity
            ): vol.All(
                vol.Coerce(float),
                vol.Range(min=MIN_BATTERY_CAPACITY, max=MAX_BATTERY_CAPACITY)
            ),
            vol.Optional(
                CONF_ENERGY_FORECAST_TARGET,
                default=energy_target
            ): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="input_number")
            ),
        })

        return self.async_show_form(
            step_id="external_connectors",
            data_schema=schema,
            errors=errors,
            description_placeholders={
                "step": "5",
                "total_steps": "5"
            }
        )

    def _get_mobile_notify_services(self) -> list[str]:
        """Get list of available mobile_app notify services."""
        notify_services = self.hass.services.async_services().get("notify", {})
        mobile_services = [
            service
            for service in notify_services.keys()
            if service.startswith("mobile_app_")
        ]
        return mobile_services if mobile_services else []
